"""Curate the independent Word component from canonical engines and fixed wheels.

No network, installation, Python interpreter, browser, Node or Pandoc is bundled.
"""
from pathlib import Path,PurePosixPath
from zipfile import ZipFile,ZIP_DEFLATED,ZipInfo
import argparse,ast,hashlib,json,subprocess

def digest(raw):return hashlib.sha256(raw).hexdigest()
def encoded(obj):return (json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf8')
def build(bridge,wps,wheels,output,*,baseline_portable=None,baseline_sha256=None):
    files={};origins=[]
    expected={'python_docx-1.2.0-py3-none-any.whl','lxml-6.1.1-cp313-cp313-win_amd64.whl',
              'pillow-12.3.0-cp313-cp313-win_amd64.whl','typing_extensions-4.16.0-py3-none-any.whl'}
    hashes={'python_docx-1.2.0-py3-none-any.whl':'3fd478f3250fbbbfd3b94fe1e985955737c145627498896a8a6bf81f4baf66c7',
            'lxml-6.1.1-cp313-cp313-win_amd64.whl':'a10bd2fd62e8ce916ececb342f348f190724a098c1faa056fdfb2a22ad5e8660',
            'pillow-12.3.0-cp313-cp313-win_amd64.whl':'1cca606cd25738df4ed873d5ad46bbdb3d83b5cbca291f6b4ff13a4df6b0bbe8',
            'typing_extensions-4.16.0-py3-none-any.whl':'481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8'}
    if baseline_portable is not None:
        from build_release import read_zip,validate_manifest
        if not baseline_sha256 or digest(baseline_portable.read_bytes())!=baseline_sha256:raise ValueError('Baseline portable SHA mismatch')
        original=read_zip(baseline_portable);validate_manifest(original)
        support={n[len('word_support/'):]:raw for n,raw in original.items() if n.startswith('word_support/')}
        manifest=validate_manifest(support)
        if manifest.get('schema')!='hrs-word-support-v1' or manifest.get('python')!='3.13' or manifest.get('platform')!='win_amd64':raise ValueError('Baseline Word runtime mismatch')
        origins=manifest['wheels']
        if {r['wheel']:r['sha256'] for r in origins}!=hashes:raise ValueError('Baseline Word dependencies differ from the pinned wheels')
        files.update({n:raw for n,raw in support.items() if n.startswith('libs/')})
        if not files:raise ValueError('Baseline has no Word dependencies')
    for name in sorted(expected) if wheels is not None else ():
        path=wheels/name
        if not path.is_file():raise ValueError('Missing pinned Python 3.13 wheel: '+name)
        if digest(path.read_bytes())!=hashes[name]:raise ValueError('Pinned wheel digest mismatch: '+name)
        origins.append({'wheel':name,'bytes':path.stat().st_size,'sha256':digest(path.read_bytes()),'origin':'https://pypi.org/'})
        with ZipFile(path) as archive:
            if archive.testzip():raise ValueError('Wheel CRC failure: '+name)
            for info in archive.infolist():
                if info.is_dir():continue
                relative=PurePosixPath(info.filename)
                if relative.is_absolute() or '..' in relative.parts or '\\' in info.filename:raise ValueError('Unsafe wheel path')
                # C/Cython headers and static types support package development,
                # not this installed native-library runtime. Keep all licences.
                if relative.suffix in {'.h','.c','.pyx','.pxd','.pxi','.pyi'}:continue
                if any(p in {'tests','__pycache__'} for p in relative.parts):continue
                target='libs/'+relative.as_posix()
                if target in files:raise ValueError('Duplicate dependency path: '+target)
                files[target]=archive.read(info)
    for root,prefix in ((bridge/'hrs_bridge','bridge/hrs_bridge'),(wps/'src/wps_pipeline','wps/src/wps_pipeline')):
        for path in sorted(root.glob('*')):
            if path.suffix in {'.py','.js','.cjs'}:files[prefix+'/'+path.name]=path.read_bytes()
    for relative in ('config.json','templates/target_template.docx','templates/cover_template_v0311.docx'):
        files['wps/'+relative]=(wps/relative).read_bytes()
    files['README.txt']=('HRS Word support for embedded CPython 3.13 Win64.\n'
       'Canonical Bridge/WPS engines, four pinned libraries and mother templates only.\n'
       'Uses the open HRS page; no separate browser, Node, Playwright or Office.\n'
       'Pandoc is optional and selected separately when native formulas are needed.\n'
       'Third-party licences and metadata are preserved under libs/*.dist-info/.\n').encode('utf8')
    public_root=Path(__file__).resolve().parents[1]
    if (public_root/'PUBLIC_SOURCE_POLICY.json').is_file():
        files['LICENSE']=(public_root/'LICENSE').read_bytes()
        files['COPYRIGHT']=(public_root/'COPYRIGHT').read_bytes()
        files['SOURCE.txt']=('Project-owned code: GPL-3.0-or-later, copyright 2026 yyyyy-9.\n'
            'Corresponding source: https://github.com/yyyyy-9/HRS\n'
            'Bridge: components/hrs-wps-bridge; WPS engine and generic templates: template-tool.\n'
            'Python libraries retain their licences under libs/*.dist-info/.\n').encode('utf8')
    identity={}
    for name,root in (('bridge',bridge),('wps',wps)):
        if (public_root/'PUBLIC_SOURCE_POLICY.json').is_file():
            identity[name]={'source_path':'components/hrs-wps-bridge' if name=='bridge' else 'template-tool'}
        else:
            identity[name]={'commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD']).decode().strip(),
                            'development_dirty':bool(subprocess.check_output(['git','-C',str(root),'status','--porcelain']).strip())}
    def constant(path,name):
        return next(ast.literal_eval(n.value) for n in ast.parse(path.read_text('utf8')).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
    identity['bridge']['version']=constant(bridge/'hrs_bridge/__init__.py','__version__')
    identity['wps']['scan_version']=constant(wps/'src/wps_pipeline/scan_docx.py','VERSION')
    manifest={'schema':'hrs-word-support-v1','python':'3.13','platform':'win_amd64','engines':identity,'wheels':origins,
              'browser_model_sha256':digest(files['bridge/hrs_bridge/browser_model.js']),
              'files':[{'path':name,'bytes':len(raw),'sha256':digest(raw)} for name,raw in sorted(files.items())]}
    files['MANIFEST.json']=encoded(manifest);output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'w',compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for name,raw in sorted(files.items()):
            info=ZipInfo('word_support/'+name,(2026,10,19,0,0,0));info.compress_type=ZIP_DEFLATED
            info.create_system=3;info.external_attr=0o100644<<16;archive.writestr(info,raw,compresslevel=9)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        for item in manifest['files']:assert digest(archive.read('word_support/'+item['path']))==item['sha256']
    result={'file':str(output),'bytes':output.stat().st_size,'sha256':digest(output.read_bytes()),'expanded_bytes':sum(map(len,files.values())),'files':len(files),'engines':identity}
    print(json.dumps(result,ensure_ascii=False,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('bridge','wps','output'):p.add_argument('--'+name,type=Path,required=True)
    sources=p.add_mutually_exclusive_group(required=True);sources.add_argument('--wheels',type=Path);sources.add_argument('--baseline-portable',type=Path)
    p.add_argument('--baseline-sha256')
    a=p.parse_args();build(a.bridge.resolve(),a.wps.resolve(),a.wheels.resolve() if a.wheels else None,a.output.resolve(),baseline_portable=a.baseline_portable,baseline_sha256=a.baseline_sha256)
