"""Independent desktop ZIP checks, including same-core and pinned component bytes."""
from pathlib import Path,PurePosixPath
import argparse
import hashlib
import json
import zipfile


def sha(raw):return hashlib.sha256(raw).hexdigest()


def members(archive):
    result={};roots=set();folded=set()
    for item in archive.infolist():
        if item.is_dir():continue
        path=PurePosixPath(item.filename)
        if len(path.parts)<2 or path.is_absolute() or '..' in path.parts or ':' in item.filename or '\\' in item.filename:raise ValueError('Unsafe ZIP path')
        roots.add(path.parts[0]);name='/'.join(path.parts[1:])
        if name.casefold() in folded:raise ValueError('Case-colliding ZIP path')
        folded.add(name.casefold());result[name]=item
    if len(roots)!=1:raise ValueError('Expected one ZIP wrapper')
    return result


def file_hash(archive,item):
    h=hashlib.sha256()
    with archive.open(item) as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def verify(desktop,portable,source):
    with zipfile.ZipFile(desktop) as d,zipfile.ZipFile(portable) as p,zipfile.ZipFile(source) as s:
        dm,pm,sm=members(d),members(p),members(s)
        manifest=json.loads(d.read(dm['DESKTOP_MANIFEST.json']))
        if manifest.get('schema')!='hrs-desktop-layout-v1' or manifest.get('protocol')!=1:raise ValueError('Invalid desktop schema')
        records={i['path']:i for i in manifest['files']}
        if set(records)!=set(dm)-{'DESKTOP_MANIFEST.json'} or len(records)!=len(manifest['files']):raise ValueError('Desktop membership mismatch')
        for name,record in records.items():
            if dm[name].file_size!=record['bytes'] or file_hash(d,dm[name])!=record['sha256']:raise ValueError('Desktop hash mismatch: '+name)
        core={n:i for n,i in dm.items() if n.startswith('resources/hrs/app/')}
        if {n[len('resources/hrs/'):]:file_hash(d,i) for n,i in core.items()}!={n:file_hash(p,i) for n,i in pm.items() if n.startswith('app/')}:
            raise ValueError('Desktop/browser core drift')
        for name,item in pm.items():
            if name.startswith(('runtime/','word_support/')) and file_hash(p,item)!=file_hash(d,dm['resources/hrs/'+name]):raise ValueError('Shared component drift: '+name)
        for name in ['main.cjs','host.cjs','preload.cjs','update.py','config.json']:
            if d.read(dm['resources/app/'+name])!=s.read(sm['desktop/'+name]):raise ValueError('Source/host drift: '+name)
        identity=json.loads(d.read(dm['resources/hrs/app/release.json']))
        if identity!=manifest['identity'] or sha(d.read(dm['resources/hrs/app/MANIFEST.json']))!=manifest['core_manifest_sha256']:raise ValueError('Core identity drift')
        if json.loads(d.read(dm['resources/app/package.json']))['version']!=identity['version']:raise ValueError('Shell version drift')
        lock=json.loads(s.read(sm['desktop/runtime.lock.json']))
        branding=manifest['exe_branding']
        for entry in lock['files']:
            name='HRS.exe' if entry['path']=='electron.exe' else entry['path']
            if name=='HRS.exe':
                if branding['official_input_sha256']!=entry['sha256'] or branding['product_version']!=identity['version']:raise ValueError('Undeclared EXE branding')
            elif records[name]['sha256']!=entry['sha256']:raise ValueError('Fixed Electron payload drift: '+name)
        if not {'LICENSE','LICENSES.chromium.html'}<=set(dm):raise ValueError('Missing Electron/Chromium notices')
        return {'status':'PASS','version':identity,'desktop_files':len(dm),'same_core_files':len(core),
                'shared_python_word_files':sum(n.startswith(('runtime/','word_support/')) for n in pm),
                'electron_version':lock['version'],'host_protocol':manifest['protocol']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--desktop',type=Path,required=True);p.add_argument('--portable',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path)
    args=p.parse_args();result=verify(args.desktop,args.portable,args.source)
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
