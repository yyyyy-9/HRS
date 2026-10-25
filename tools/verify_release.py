"""Independent ZIP/manifest/baseline verification; never import the producer."""
from pathlib import Path, PurePosixPath
import argparse, ast, fnmatch, hashlib, json, zipfile


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def approved_word_materials(baseline, portable, approvals):
    """Only the synthetic cover and its licensing/provenance may be replaced."""
    allowed={'word_support/MANIFEST.json', 'word_support/wps/templates/cover_template_v0311.docx',
             'word_support/LICENSE', 'word_support/COPYRIGHT', 'word_support/SOURCE.txt'}
    if set(approvals)-allowed:
        raise ValueError('Word material policy names implementation files')
    for name, approval in approvals.items():
        before, after=baseline.get(name), portable.get(name)
        if after is None or before==after or approval!={
            'baseline_sha256':sha(before) if before is not None else None, 'sha256':sha(after)}:
            raise ValueError('Word public material fingerprint mismatch: '+name)
    return sorted(approvals)


def entries(path):
    result,roots,folded={},set(),set()
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError('ZIP CRC failure')
        for item in archive.infolist():
            if item.is_dir():
                continue
            path=PurePosixPath(item.filename)
            if len(path.parts)<2 or path.is_absolute() or '..' in path.parts or ':' in item.filename or '\\' in item.filename:
                raise ValueError('Unsafe/wrapperless ZIP member')
            roots.add(path.parts[0])
            name='/'.join(path.parts[1:])
            if name.casefold() in folded:
                raise ValueError('Duplicate/case-colliding ZIP member')
            folded.add(name.casefold())
            result[name]=archive.read(item)
    if len(roots)!=1:
        raise ValueError('ZIP wrapper must be unique')
    return result


def approved_renderer_vendors(baseline, portable, approvals):
    """PELE-01: narrowly authorize a pinned renderer replacement, not vendors in general."""
    allowed={f'app/web/vendor/{folder}/{name}' for folder,names in (
        ('mermaid',('LICENSE.txt','RUNTIME.json','mermaid.min.js')),
        ('pele',('LICENSE.txt','RUNTIME.json','pele.global.js'))) for name in names}
    if set(approvals)-allowed:
        raise ValueError('Protected renderer vendor policy names unrelated payloads')
    for name,approval in approvals.items():
        before,after=baseline.get(name),portable.get(name)
        if before==after or approval!={'baseline_sha256':sha(before) if before is not None else None,
                                      'sha256':sha(after) if after is not None else None}:
            raise ValueError('Protected renderer vendor fingerprint mismatch: '+name)
    return sorted(approvals)


def check_manifest(files,prefix=''):
    key=prefix+'MANIFEST.json'
    value=json.loads(files[key])
    records={prefix+item['path']:item for item in value['files']}
    actual={name for name in files if name.startswith(prefix) and name!=key}
    if set(records)!=actual or len(records)!=len(value['files']) or len(records)!=value['file_count_without_manifest']:
        raise ValueError('Manifest membership mismatch: '+prefix)
    for name,record in records.items():
        if sha(files[name])!=record['sha256'] or len(files[name])!=record['bytes']:
            raise ValueError('Manifest hash mismatch: '+name)
    return value


def verify(source,portable,baseline,policy,baseline_source=None):
    if policy.get('schema')!='hrs-release-policy-v1':
        raise ValueError('Unknown release policy')
    for files in (source,portable):
        check_manifest(files)
        app_meta=check_manifest(files,'app/')
        identity=json.loads(files['app/release.json'])
        if any(app_meta[key]!=identity[key] or json.loads(files['MANIFEST.json'])[key]!=identity[key]
               for key in ('version','package_revision')):
            raise ValueError('Release identity drift')
    check_manifest(baseline)
    app=lambda files:{name:raw for name,raw in files.items() if name.startswith('app/')}
    if app(source)!=app(portable):
        raise ValueError('Source and portable app trees differ')
    changed=sorted(name for name in app(baseline).keys()|app(portable).keys() if baseline.get(name)!=portable.get(name))
    patterns=policy['allowed_application_changes']
    if any(not any(fnmatch.fnmatchcase(name,pattern) for pattern in patterns) for name in changed):
        raise ValueError('Undeclared application changes: '+', '.join(changed))
    protected=[name for name in baseline if name.startswith(('runtime/','word_support/','app/web/vendor/'))
               or name.lower().endswith(('.vbs','.cmd')) or name.startswith('app/web/') and name.endswith('.css')]
    approved_css=[];approved_adapter=[];approved_word=[]
    renderer_vendors=approved_renderer_vendors(baseline,portable,policy.get('approved_renderer_vendor_changes',{}))
    added_vendors={name for name in portable.keys()-baseline.keys() if name.startswith('app/web/vendor/')}
    if added_vendors-set(renderer_vendors):raise ValueError('Protected vendor additions lack exact renderer approval')
    materials=approved_word_materials(baseline,portable,policy.get('approved_word_material_changes',{}))
    added_word={n for n in portable.keys()-baseline.keys() if n.startswith('word_support/')}
    if added_word-set(materials):raise ValueError('Undeclared Word component additions')
    word_adapters={'word_support/MANIFEST.json',*('word_support/bridge/hrs_bridge/'+name for name in
                   ('__init__.py','__main__.py','runtime.py','docx_export.py','docx_import.py','workflow.py','browser_model.js','math_adapter.py'))}
    for name in protected:
        if portable.get(name)!=baseline[name]:
            if name in renderer_vendors:continue
            approval=policy.get('approved_css_changes',{}).get(name)
            if (name.startswith('app/web/') and not name.startswith('app/web/vendor/') and name.endswith('.css')
                and approval=={'baseline_sha256':sha(baseline[name]),'sha256':sha(portable.get(name,b''))}):
                approved_css.append(name)
            elif name in materials:
                continue  # Exact before/after fingerprints were independently checked above.
            elif name in word_adapters:
                approval=policy.get('approved_word_contract_adapter_changes',{}).get(name)
                if approval!={'baseline_sha256':sha(baseline[name]),'sha256':sha(portable.get(name,b''))}:
                    raise ValueError('Protected Word contract adapter changed without both exact fingerprints: '+name)
                approved_word.append(name)
            elif name=='app/web/vendor/source-editor.js':
                old=b'window.SourceEditor={attach:Yu};})();\n'
                new=b'window.SourceEditor={attach:Yu,extensionAPI:{StateEffect:W,StateField:he,Decoration:F,EditorState:z,EditorView:D,EditorSelection:w,external:ei}};})();\n'
                after=portable.get(name,b'')
                approval=policy.get('approved_editor_adapter_export')
                if (approval!={'baseline_sha256':sha(baseline[name]),'sha256':sha(after)} or
                    not baseline[name].endswith(old) or not after.endswith(new) or
                    baseline[name][:-len(old)]!=after[:-len(new)]):
                    raise ValueError('Protected editor payload changed beyond the approved adapter export')
                approved_adapter.append(name)
            else:
                raise ValueError('Protected payload changed: '+name)
    if any(name.startswith(('tests/','tools/','history/','data/','.git/','app/docs/history/'))
           or '__pycache__' in name for name in portable):
        raise ValueError('Development/user material in portable')
    support={name[len('word_support/'):]:raw for name,raw in portable.items() if name.startswith('word_support/')}
    component=json.loads(support['MANIFEST.json'])
    if component.get('schema')!='hrs-word-support-v1' or component.get('python')!='3.13':
        raise ValueError('Unsupported Word component')
    expected={item['path']:item for item in component['files']}
    if set(support)!=set(expected)|{'MANIFEST.json'} or len(expected)!=len(component['files']):
        raise ValueError('Word support membership mismatch')
    for name,record in expected.items():
        if sha(support[name])!=record['sha256'] or len(support[name])!=record['bytes']:
            raise ValueError('Word support hash mismatch')
    if component['browser_model_sha256']!=sha(portable['app/web/bridge_model.js']):
        raise ValueError('Word component/browser model mismatch')
    def legacy(raw):
        for node in ast.parse(raw).body:
            if isinstance(node,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='LEGACY_READER_SHA256' for x in node.targets):
                return set(ast.literal_eval(node.value))
        raise ValueError('Legacy reader trust declaration missing')
    before,after=legacy(baseline['app/studio.py']),legacy(portable['app/studio.py'])
    if not before<=after:
        raise ValueError('Legacy reader trust removed')
    old_reader=baseline['app/web/report_reader.js']
    if old_reader!=portable['app/web/report_reader.js'] and sha(old_reader) not in after:
        raise ValueError('Previous current reader not trusted')
    public=json.loads(source['PUBLIC_SOURCE_POLICY.json']) if 'PUBLIC_SOURCE_POLICY.json' in source else None
    if public:
        if public.get('schema')!='hrs-public-source-policy-v1' or public.get('private_history')!='preserved-locally-not-published':raise ValueError('Invalid public source policy')
        if any(n.startswith('history/') for n in source):raise ValueError('Private development history in public source')
        archived=[]
    else:
        history=json.loads(source['history/ARCHIVE_MANIFEST.json'])
        archived=history['files']+history.get('maintenance_files',[])
        for item in archived:
            name=PurePosixPath(item['archived'])
            if not name.parts or name.parts[0]!='history' or '..' in name.parts:
                raise ValueError('Unsafe source history')
            if sha(source[item['archived']])!=item['archived_sha256']:
                raise ValueError('Source history changed')
        if baseline_source:
            check_manifest(baseline_source)
            for name,raw in baseline_source.items():
                if name.startswith('history/') and name!='history/ARCHIVE_MANIFEST.json' and source.get(name)!=raw:
                    raise ValueError('Previously retained history changed: '+name)
    return {'overall':'PASS','identity':identity,'application_changes':changed,
            'protected_payload_files':len(protected)-len(approved_css)-len(approved_adapter)-len(approved_word)-len(set(renderer_vendors)&set(protected)),'archived_entries':len(archived),
            'source_app_equals_portable':True,'runtime_css_vendors_word_support_unchanged':not (approved_css or approved_adapter or approved_word or materials or renderer_vendors),
            'runtime_vendors_word_support_unchanged':not (approved_adapter or approved_word or materials or renderer_vendors),
            'word_implementation_unchanged':not approved_word, 'approved_word_material_changes':materials,
            'approved_word_contract_adapter_changes':approved_word,'approved_css_changes':approved_css,
            'approved_renderer_vendor_changes':renderer_vendors,
            'upstream_editor_payload_unchanged':True,'approved_editor_adapter_exports':approved_adapter,
            'source_only_history_preserved':not bool(public),'public_source_policy':bool(public),'legacy_reader_trust_retained':True}


def extract(files,target):
    target.mkdir(parents=True,exist_ok=False)
    for name,raw in files.items():
        path=(target/name).resolve()
        if not path.is_relative_to(target.resolve()):
            raise ValueError('Extraction path escape')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages',type=Path,required=True)
    parser.add_argument('--baseline-portable',type=Path,required=True)
    parser.add_argument('--baseline-sha256',required=True)
    parser.add_argument('--baseline-source',type=Path)
    parser.add_argument('--baseline-source-sha256')
    parser.add_argument('--policy',type=Path,default=Path(__file__).with_name('release_policy.json'))
    parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args()
    if sha(args.baseline_portable.read_bytes())!=args.baseline_sha256:
        raise ValueError('Baseline portable differs from explicit SHA')
    old_source=None
    if args.baseline_source:
        if sha(args.baseline_source.read_bytes())!=args.baseline_source_sha256:
            raise ValueError('Baseline source differs from explicit SHA')
        old_source=entries(args.baseline_source)
    identity=json.loads((Path(__file__).resolve().parents[1]/'app/release.json').read_text('utf8'))
    stem='HTMLReportStudio_v{version}_{package_revision}'.format(**identity)
    names={key:args.packages/(stem+'_'+suffix+'.zip') for key,suffix in
           [('source','Source_and_Tests'),('portable','ChromeFirst_Win64_Portable')]}
    data={key:entries(path) for key,path in names.items()}
    report=verify(data['source'],data['portable'],entries(args.baseline_portable),json.loads(args.policy.read_text('utf8')),old_source)
    args.evidence.mkdir(parents=True,exist_ok=False)
    for key,files in data.items():
        extract(files,args.evidence/key)
    report['packages']={key:{'file':path.name,'sha256':sha(path.read_bytes()),'files':len(data[key])} for key,path in names.items()}
    report['baseline_portable_sha256']=args.baseline_sha256
    report['baseline_source_sha256']=args.baseline_source_sha256
    (args.evidence/'PACKAGE_VERIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
