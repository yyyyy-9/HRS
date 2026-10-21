"""Build Source/Portable from an explicitly pinned current portable.
No downloads or source writes. Independent verification lives in verify_release.
"""
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, sys, zipfile

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from release_info import load_release
ROOT_FILES={'.gitattributes','.gitignore','AGENTS.md','AGENT_TASK.md','README.md','README_TESTS.txt','requirements-dev.txt','pyproject.toml','setup.py','MANIFEST.in','LICENSE','PUBLIC_SOURCE_POLICY.json','CONTRIBUTING.md','SECURITY.md','COPYRIGHT'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8')


def source_files(root):
    result={}
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        relative=path.relative_to(root)
        if relative.parts[0] in ('build','dist') or relative.parts[0].endswith('.egg-info'):
            continue  # Standard Python build outputs are not release source.
        if '.git' in relative.parts or '__pycache__' in relative.parts or path.suffix in ('.pyc','.pyo'):
            continue
        if relative.as_posix()=='MANIFEST.json':
            continue
        if relative.parts[0] not in ('app','tests','tools','history','packaging','desktop','template-tool','components','.github','examples') and relative.as_posix() not in ROOT_FILES:
            raise ValueError('Unexpected source file: '+str(relative))
        if path.is_symlink() or any(piece in ('node_modules','.venv','.dev-env','test-artifacts') for piece in relative.parts):
            raise ValueError('Cache/dependency/link in source: '+str(relative))
        result[relative.as_posix()]=path.read_bytes()
    return result


def manifest(files,stage,timestamp,identity):
    return {'version':identity['version'],'package_revision':identity['package_revision'],
            'stage':stage,'generated_utc':timestamp,'file_count_without_manifest':len(files),
            'files':[{'path':n,'bytes':len(raw),'sha256':digest(raw)} for n,raw in sorted(files.items())]}



def seal_app(root):
    """Explicitly prepare the canonical manifest; same bytes are a no-op."""
    identity=load_release(root/'app/release.json')
    app={name[4:]:raw for name,raw in source_files(root).items() if name.startswith('app/') and name!='app/MANIFEST.json'}
    target=root/'app/MANIFEST.json'
    sealed=manifest(app,identity['release']+' app',datetime.now(timezone.utc).isoformat(),identity)
    if target.is_file():
        old=json.loads(target.read_text('utf8'))
        if all(old.get(key)==sealed[key] for key in ('version','package_revision','files','file_count_without_manifest')):
            return {'ok':True,'updated':False,'identity':identity,'files':len(app)}
    target.write_bytes(encoded(sealed))
    return {'ok':True,'updated':True,'identity':identity,'files':len(app)}


def read_zip(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError('Input ZIP CRC failure')
        result,roots,normalized={},set(),set()
        for item in archive.infolist():
            if item.is_dir():
                continue
            name=PurePosixPath(item.filename)
            if name.is_absolute() or '..' in name.parts or len(name.parts)<2 or ':' in item.filename or '\\' in item.filename:
                raise ValueError('Unsafe/non-wrapped ZIP member: '+item.filename)
            roots.add(name.parts[0])
            relative=PurePosixPath(*name.parts[1:]).as_posix()
            if relative.casefold() in normalized:
                raise ValueError('Duplicate/case-colliding ZIP member: '+relative)
            normalized.add(relative.casefold())
            result[relative]=archive.read(item)
        if len(roots)!=1:
            raise ValueError('ZIP must have one wrapper directory')
        return result


def validate_manifest(files,key='MANIFEST.json'):
    data=json.loads(files[key])
    expected={item['path']:item for item in data['files']}
    if set(expected)!=set(files)-{key} or len(expected)!=len(data['files']):
        raise ValueError('Manifest membership mismatch: '+key)
    for name,item in expected.items():
        if digest(files[name])!=item['sha256'] or len(files[name])!=item['bytes']:
            raise ValueError('Manifest digest mismatch: '+name)
    return data


def write_zip(path,files,wrapper,timestamp):
    dt=datetime.fromisoformat(timestamp)
    stamp=dt.year,dt.month,dt.day,dt.hour,dt.minute,dt.second//2*2
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,raw in sorted(files.items()):
            item=zipfile.ZipInfo(wrapper+'/'+name,stamp)
            item.compress_type=zipfile.ZIP_DEFLATED
            item.create_system=3
            item.external_attr=0o100644<<16
            archive.writestr(item,raw,compresslevel=9)


def build(root,baseline_path,expected_sha,output,word_support=None,desktop_runtime=None):
    if digest(baseline_path.read_bytes())!=expected_sha:
        raise ValueError('Baseline SHA differs from explicit declaration')
    baseline=read_zip(baseline_path)
    validate_manifest(baseline)
    files=source_files(root)
    identity=load_release(root/'app/release.json')
    app={name[4:]:raw for name,raw in files.items() if name.startswith('app/')}
    app_meta=validate_manifest(app)
    if any(app_meta[key]!=identity[key] for key in ('version','package_revision')):
        raise ValueError('Source app manifest identity is stale; prepare before building')
    timestamp=app_meta['generated_utc']
    support=read_zip(word_support) if word_support else {
        name[len('word_support/'):]:raw for name,raw in baseline.items() if name.startswith('word_support/')}
    component=validate_manifest(support)
    if component.get('schema')!='hrs-word-support-v1' or component.get('python')!='3.13':
        raise ValueError('Expected Python 3.13 Word component')
    if component['browser_model_sha256']!=digest(app['web/bridge_model.js']):
        raise ValueError('Current browser model requires matching Word support')
    portable={name:raw for name,raw in baseline.items()
              if not name.startswith(('app/','word_support/')) and name!='MANIFEST.json'}
    portable.update({'word_support/'+name:raw for name,raw in support.items()})
    portable.update({name:raw for name,raw in files.items() if name.startswith('app/')})
    portable['AGENTS.md']=files['AGENTS.md']
    portable['BUILD-INFO.txt']=(identity['release']+'\nPinned current input; actual validation in RELEASE_MANIFEST.json and app/docs/CURRENT_STATUS.md.\n').encode('utf8')
    portable['README_Portable.txt']=(identity['release']+''' · Windows Chrome 优先便携版

完整解压到新目录，双击“启动编辑器.vbs”。保留旧程序、report.md、assets和草稿。
Word beta沿用匹配的独立Bridge/WPS组件；公式可选已有Pandoc，无需第二个浏览器。
行为/验收范围见app/docs/CURRENT_STATUS.md，变更见app/CHANGELOG.md，帮助见app/web/help.html。
普通使用不需要测试依赖。源码/测试另包；选择和未测范围见源码README_TESTS.txt。
自有代码采用GPL-3.0-or-later，第三方与外部素材权利见app/LICENSING.md。
''').encode('utf8')
    portable['使用说明_先看这个.txt']=portable['README_Portable.txt']
    portable['Chrome优先_测试说明.txt']='浏览器、Office/WPS、系统窗口和打印兼容性以实际运行结果为准。\n'.encode('utf8')
    protected=[n for n in baseline if n.startswith('runtime/') or n.lower().endswith(('.vbs','.cmd'))]
    if any(portable.get(n)!=baseline[n] for n in protected):
        raise ValueError('Protected runtime/launcher changed')
    portable['MANIFEST.json']=encoded(manifest(portable,identity['release']+' portable',timestamp,identity))
    files['MANIFEST.json']=encoded(manifest(files,identity['release']+' source and tests',timestamp,identity))
    output.mkdir(parents=True,exist_ok=False)
    products=[]
    for suffix,contents in [('Source_and_Tests',files),('ChromeFirst_Win64_Portable',portable)]:
        target=output/(identity['stem']+'_'+suffix+'.zip')
        write_zip(target,contents,identity['stem']+'_'+suffix,timestamp)
        products.append({'file':target.name,'bytes':target.stat().st_size,'sha256':digest(target.read_bytes()),'files':len(contents)})
    if desktop_runtime:
        from build_desktop import build as desktop_build
        portable_zip=output/(identity['stem']+'_ChromeFirst_Win64_Portable.zip')
        desktop=desktop_build(root,portable_zip,desktop_runtime,output/(identity['stem']+'_Desktop_Win64'))
        products.append({'file':desktop['zip'],'bytes':desktop['zip_bytes'],'sha256':desktop['zip_sha256'],
                         'files':len(desktop['files'])+1,'same_core_manifest_sha256':desktop['core_manifest_sha256']})
    result={'schema':'hrs-release-build-v2','version':identity['version'],'package_revision':identity['package_revision'],
            'baseline_portable_sha256':expected_sha,'source_unchanged_by_build':True,
            'runtime_and_launchers_preserved':len(protected),'full_packages_only':True,'packages':products}
    (output/'RELEASE_MANIFEST.json').write_bytes(encoded(result))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--seal-app',action='store_true',help='Explicitly prepare app/MANIFEST.json from release.json and current bytes; no ZIP build')
    parser.add_argument('--baseline-portable',type=Path)
    parser.add_argument('--baseline-sha256')
    parser.add_argument('--word-support',type=Path,help='Optional replacement, otherwise validated current support')
    parser.add_argument('--desktop-runtime',type=Path,help='Optional fixed Electron directory; builds desktop from the same frozen Portable core')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.seal_app:
        if args.output or args.baseline_portable or args.word_support:parser.error('--seal-app cannot also build ZIPs')
        print(json.dumps(seal_app(args.source.resolve()),ensure_ascii=False,indent=2));return
    if not all((args.output,args.baseline_portable,args.baseline_sha256)):parser.error('Build requires --output, --baseline-portable and --baseline-sha256')
    if args.output.resolve().is_relative_to(args.source.resolve()):
        parser.error('Packages must be outside source')
    print(json.dumps(build(args.source.resolve(),args.baseline_portable,args.baseline_sha256,args.output,args.word_support,args.desktop_runtime),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
