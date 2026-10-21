"""Desktop packaging over the canonical browser Portable payload. No core writes.

The existing release builder calls this optional target; native runtime files are
pinned in desktop/runtime.lock.json, not installed/downloaded by this builder.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile

from build_release import read_zip, validate_manifest, encoded, digest


def build(source, portable, runtime, output, *, create_zip=True):
    source=source.resolve();runtime=runtime.resolve();output=output.resolve()
    files=read_zip(portable);validate_manifest(files)
    core={name[4:]:raw for name,raw in files.items() if name.startswith('app/')}
    meta=validate_manifest(core);identity=json.loads(core['release.json'])
    lock=json.loads((source/'desktop/runtime.lock.json').read_text('utf8'))
    host=json.loads((source/'desktop/config.json').read_text('utf8'))
    if lock.get('schema')!='hrs-electron-runtime-v1':raise ValueError('Invalid Electron lock')
    output.mkdir(parents=True,exist_ok=False)
    records=[]
    def put(name,raw):
        dest=output/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        records.append({'path':name,'bytes':len(raw),'sha256':digest(raw)})
    try:
        for record in lock['files']:
            original=runtime/record['path']
            if original.is_symlink() or original.stat().st_size!=record['bytes']:raise ValueError('Runtime file mismatch')
            # Stream large native files; don't hold another Chromium copy in RAM.
            target='HRS.exe' if record['path']=='electron.exe' else record['path']
            dest=output/target;dest.parent.mkdir(parents=True,exist_ok=True)
            sha=hashlib.sha256()
            with original.open('rb') as src,dest.open('xb') as out:
                for chunk in iter(lambda:src.read(1024*1024),b''):sha.update(chunk);out.write(chunk)
            if sha.hexdigest()!=record['sha256']:raise ValueError('Runtime digest mismatch: '+record['path'])
            records.append({**record,'path':target})
        for name,raw in files.items():
            if name.startswith(('app/','runtime/','word_support/')):put('resources/hrs/'+name,raw)
        for name in ['main.cjs','host.cjs','preload.cjs','update.py','config.json']:
            put('resources/app/'+name,(source/'desktop'/name).read_bytes())
        from windows_exe import brand
        brand(output/'HRS.exe',source/'app/web/app-icon.ico',identity['version'],host['product_name'])
        exe=next(r for r in records if r['path']=='HRS.exe')
        runtime_exe_sha=exe['sha256'];exe.update(bytes=(output/'HRS.exe').stat().st_size,sha256=digest((output/'HRS.exe').read_bytes()))
        put('resources/app/package.json',encoded({'name':'html-report-studio','productName':host['product_name'],
            'version':identity['version'],'private':True,'main':'main.cjs'}))
        put('回退核心.cmd',('@echo off\r\nsetlocal\r\n"%~dp0resources\\hrs\\runtime\\python.exe" -B "%~dp0resources\\app\\update.py" --root "%~dp0." --rollback\r\nif errorlevel 1 (pause & exit /b 1)\r\nstart "" "%~dp0HRS.exe"\r\n').encode('ascii'))
        put('README_桌面版.txt',(f'HTML Report Studio {identity["version"]}\n\n完整解压后双击 HRS.exe。无需安装Chrome、Edge、Python或Node。\n默认数据：%LOCALAPPDATA%/HTMLReportStudioDesktop；工程仍保存在你选择的目录。\n窗口关闭会确认恢复草稿；草稿失败保留窗口。正式保存继续用Ctrl+S。\n菜单“文件”可离线更新和回退；更新只切换已校验核心，不删除用户文稿。\n可用 HRS.exe --data-dir=绝对路径 指定独立数据根，不得位于安装目录内。\n当前桌面验收边界见resources/hrs/app/docs/CURRENT_STATUS.md。\n自有代码GPL-3.0-or-later；Electron及Chromium许可保持根目录原文件。\n').encode('utf8'))
        result={'schema':'hrs-desktop-layout-v1','protocol':host['protocol'],'identity':identity,'electron_version':lock['version'],
                'exe_branding':{'official_input_sha256':runtime_exe_sha,'product_version':identity['version'],'icon':'app/web/app-icon.ico'},
                'core_manifest_sha256':digest(core['MANIFEST.json']),'files':sorted(records,key=lambda i:i['path'])}
        (output/'DESKTOP_MANIFEST.json').write_bytes(encoded(result))
        if create_zip:
            target=Path(str(output)+'.zip')
            stamp=__import__('datetime').datetime.fromisoformat(meta['generated_utc'])
            with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
                for file in sorted(output.rglob('*')):
                    if not file.is_file():continue
                    name=output.name+'/'+file.relative_to(output).as_posix()
                    item=zipfile.ZipInfo(name,(stamp.year,stamp.month,stamp.day,stamp.hour,stamp.minute,stamp.second//2*2));item.compress_type=zipfile.ZIP_DEFLATED
                    with file.open('rb') as src,archive.open(item,'w',force_zip64=True) as dest:shutil.copyfileobj(src,dest,1024*1024)
            result={**result,'zip':target.name,'zip_bytes':target.stat().st_size,'zip_sha256':digest(target.read_bytes())}
        return result
    except Exception:
        # Preserve a failed new build for diagnosis; never replace an old output.
        raise


def build_update(source, base_desktop, target_portable, output):
    base=json.loads((base_desktop/'DESKTOP_MANIFEST.json').read_text('utf8'))
    active=base_desktop/'resources/hrs/active.json'
    base_sha=json.loads(active.read_text('utf8'))['sha256'] if active.exists() else base['core_manifest_sha256']
    files=read_zip(target_portable);validate_manifest(files)
    app={name:raw for name,raw in files.items() if name.startswith('app/')};manifest=validate_manifest({n[4:]:raw for n,raw in app.items()})
    capability=json.loads(app.get('app/host_capabilities.json',b'{}'))
    if capability.get('schema')!='hrs-host-capabilities-v1' or capability.get('desktop_protocol')!=base['protocol']:
        raise ValueError('Target core requires another desktop host; use a full release')
    support=json.loads((base_desktop/'resources/hrs/word_support/MANIFEST.json').read_text('utf8'))
    if support['browser_model_sha256']!=digest(app['app/web/bridge_model.js']):raise ValueError('Target needs another Word component; use a full release')
    contract={'schema':'hrs-core-update-v1','host_protocol':base['protocol'],'base_core_sha256':base_sha,
              'target_core_sha256':digest(app['app/MANIFEST.json']),'target_identity':json.loads(app['app/release.json'])}
    payload={**app,'UPDATE.json':encoded(contract)}
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,raw in sorted(payload.items()):archive.writestr(name,raw)
    return {'file':output.name,'sha256':digest(output.read_bytes()),'contract':contract}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--portable',type=Path,required=True);p.add_argument('--electron-root',type=Path);p.add_argument('--base-desktop',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--no-zip',action='store_true');args=p.parse_args()
    if args.base_desktop:result=build_update(args.source,args.base_desktop,args.portable,args.output)
    else:
        if not args.electron_root:p.error('--electron-root required')
        result=build(args.source,args.portable,args.electron_root,args.output,create_zip=not args.no_zip)
    print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
