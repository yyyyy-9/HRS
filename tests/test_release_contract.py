"""TEST-SYSTEM-01: independent checks must reject self-consistent bad packages."""
from pathlib import Path
import copy
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


BUILD = module('release_producer_test', ROOT/'tools/build_release.py')
VERIFY = module('release_consumer_test', ROOT/'tools/verify_release.py')
IDENTITY = {'version':'9.8.7','package_revision':'R42'}


def seal(files):
    app = {name[4:]:raw for name,raw in files.items() if name.startswith('app/') and name!='app/MANIFEST.json'}
    files['app/MANIFEST.json'] = BUILD.encoded(BUILD.manifest(app,'synthetic','2020-01-01T00:00:00+00:00',IDENTITY))
    files.pop('MANIFEST.json',None)
    files['MANIFEST.json'] = BUILD.encoded(BUILD.manifest(files,'synthetic','2020-01-01T00:00:00+00:00',IDENTITY))
    return files


class ReleaseContracts(unittest.TestCase):
    def test_word_runtime_reuse_rejects_a_different_baseline_before_building(self):
        """WORD-HYPERLINK-01: reusing pinned libraries must bind the actual input ZIP."""
        producer=module('word_support_producer_test',ROOT/'tools/build_word_support.py')
        with tempfile.TemporaryDirectory() as directory,patch.dict('sys.modules',{'build_release':BUILD}):
            root=Path(directory);baseline=root/'baseline.zip';baseline.write_bytes(b'different input')
            output=root/'new.zip'
            with self.assertRaisesRegex(ValueError,'Baseline portable SHA mismatch'):
                producer.build(root/'bridge',root/'wps',None,output,baseline_portable=baseline,baseline_sha256='0'*64)
            self.assertFalse(output.exists())

    def test_renderer_vendor_migration_is_exact_and_cannot_change_other_vendors(self):
        """PELE-01: additions/removals must both be bound to actual bytes."""
        source,baseline=self.fixture();old='app/web/vendor/mermaid/mermaid.min.js';new='app/web/vendor/pele/pele.global.js'
        baseline[old]=b'old renderer';seal(baseline)
        portable=copy.deepcopy(baseline);portable.pop(old);portable[new]=b'new renderer'
        source[new]=portable[new];seal(source);seal(portable)
        policy={'schema':'hrs-release-policy-v1','allowed_application_changes':['app/*'],
                'approved_renderer_vendor_changes':{
                    old:{'baseline_sha256':BUILD.digest(baseline[old]),'sha256':None},
                    new:{'baseline_sha256':None,'sha256':BUILD.digest(portable[new])}}}
        self.assertEqual(set(VERIFY.verify(source,portable,baseline,policy)['approved_renderer_vendor_changes']),{old,new})
        for key in ('baseline_sha256','sha256'):
            bad=copy.deepcopy(policy);bad['approved_renderer_vendor_changes'][new][key]='0'*64
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'renderer vendor'):
                VERIFY.verify(source,portable,baseline,bad)
        bad=copy.deepcopy(policy);bad['approved_renderer_vendor_changes']['app/web/vendor/marked.js']={'baseline_sha256':None,'sha256':None}
        with self.assertRaisesRegex(ValueError,'renderer vendor'):VERIFY.verify(source,portable,baseline,bad)

    def test_editor_adapter_approval_cannot_authorize_upstream_payload_edits(self):
        source,baseline=self.fixture();name='app/web/vendor/source-editor.js'
        old=b'window.SourceEditor={attach:Yu};})();\n'
        new=b'window.SourceEditor={attach:Yu,extensionAPI:{StateEffect:W,StateField:he,Decoration:F,EditorState:z,EditorView:D,EditorSelection:w,external:ei}};})();\n'
        baseline[name]=b'pinned payload\n'+old;seal(baseline)
        source[name]=b'pinned payload\n'+new;portable=copy.deepcopy(baseline);portable[name]=source[name];seal(source);seal(portable)
        policy={'schema':'hrs-release-policy-v1','allowed_application_changes':['app/*'],
                'approved_editor_adapter_export':{'baseline_sha256':BUILD.digest(baseline[name]),'sha256':BUILD.digest(portable[name])}}
        self.assertEqual(VERIFY.verify(source,portable,baseline,policy)['approved_editor_adapter_exports'],[name])
        source[name]=portable[name]=b'changed library\n'+new;seal(source);seal(portable)
        policy['approved_editor_adapter_export']['sha256']=BUILD.digest(portable[name])
        with self.assertRaisesRegex(ValueError,'Protected editor payload'):
            VERIFY.verify(source,portable,baseline,policy)

    def fixture(self):
        source = seal({'AGENTS.md':b'rules','history/ARCHIVE_MANIFEST.json':b'{"files":[]}',
            'app/release.json':BUILD.encoded(IDENTITY),'app/studio.py':b'LEGACY_READER_SHA256={"old"}',
            'app/web/bridge_model.js':b'model','app/web/report_reader.js':b'reader','app/web/style.css':b'fixed css'})
        files={'bridge/hrs_bridge/browser_model.js':b'model'}
        component={'schema':'hrs-word-support-v1','python':'3.13','browser_model_sha256':BUILD.digest(b'model'),
                   'files':[{'path':n,'bytes':len(raw),'sha256':BUILD.digest(raw)} for n,raw in files.items()]}
        baseline=seal({**{n:raw for n,raw in source.items() if not n.startswith('history/')},
                       'runtime/python.exe':b'fixed runtime','start.vbs':b'fixed launcher',
                       'word_support/MANIFEST.json':BUILD.encoded(component),
                       **{'word_support/'+n:raw for n,raw in files.items()}})
        return source,baseline

    def test_explicit_seal_is_idempotent_and_uses_canonical_identity(self):
        source,_=self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,raw in source.items():
                if name=='MANIFEST.json':continue
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            changed=root/'app/new.txt';changed.write_bytes(b'new application byte')
            first=BUILD.seal_app(root);before=(root/'app/MANIFEST.json').read_bytes()
            second=BUILD.seal_app(root)
            self.assertTrue(first['updated']);self.assertFalse(second['updated'])
            self.assertEqual((root/'app/MANIFEST.json').read_bytes(),before)
            self.assertEqual(json.loads(before)['version'],IDENTITY['version'])

    def test_build_is_reproducible_and_never_rewrites_the_source(self):
        source,baseline=self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tree=root/'source';tree.mkdir();base=root/'base.zip'
            for name,raw in source.items():
                if name=='MANIFEST.json':continue
                path=tree/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            with zipfile.ZipFile(base,'w') as archive:
                for name,raw in baseline.items():archive.writestr('B/'+name,raw)
            before=BUILD.source_files(tree)
            first=BUILD.build(tree,base,BUILD.digest(base.read_bytes()),root/'first')
            second=BUILD.build(tree,base,BUILD.digest(base.read_bytes()),root/'second')
            self.assertEqual(BUILD.source_files(tree),before)
            self.assertEqual([item['sha256'] for item in first['packages']],[item['sha256'] for item in second['packages']])
            self.assertEqual(first['package_revision'],'R42')
            actual=[VERIFY.entries(root/'first'/item['file']) for item in first['packages']]
            self.assertEqual(VERIFY.verify(*actual,baseline,{'schema':'hrs-release-policy-v1','allowed_application_changes':[]})['overall'],'PASS')
            with self.assertRaisesRegex(ValueError,'Baseline SHA'):
                BUILD.build(tree,base,'0'*64,root/'wrong')

    def test_independent_verifier_rejects_valid_manifests_with_protected_or_undeclared_changes(self):
        source,baseline=self.fixture()
        for name,allowed,message in [('app/web/style.css',['app/*'],'Protected payload'),
                                     ('app/web/unknown.js',[],'Undeclared application')]:
            with self.subTest(name=name):
                changed_source=copy.deepcopy(source);changed_portable=copy.deepcopy(baseline)
                changed_source[name]=changed_portable[name]=b'unauthorized but accurately inventoried'
                seal(changed_source);seal(changed_portable)
                with self.assertRaisesRegex(ValueError,message):
                    VERIFY.verify(changed_source,changed_portable,baseline,
                                  {'schema':'hrs-release-policy-v1','allowed_application_changes':allowed})

    def test_word_adapter_approval_requires_both_exact_fingerprints(self):
        for relative in ('bridge/hrs_bridge/runtime.py','bridge/hrs_bridge/__main__.py',
                         'bridge/hrs_bridge/ooxml.py','wps/src/wps_pipeline/scan_docx.py',
                         'wps/src/wps_pipeline/verify_scan_fidelity.py'):
            with self.subTest(adapter=relative):
                source,baseline=self.fixture();name='word_support/'+relative
                baseline[name]=b'old adapter';seal(baseline)
                portable=copy.deepcopy(baseline);portable[name]=b'new adapter'
                component=json.loads(portable['word_support/MANIFEST.json'])
                for key,raw in portable.items():
                    if key.startswith('word_support/') and key!='word_support/MANIFEST.json':
                        component['files']=[item for item in component['files'] if item['path']!=key[len('word_support/'):]]
                        component['files'].append({'path':key[len('word_support/'):],'bytes':len(raw),'sha256':BUILD.digest(raw)})
                portable['word_support/MANIFEST.json']=BUILD.encoded(component);seal(portable)
                names=[name,'word_support/MANIFEST.json']
                policy={'schema':'hrs-release-policy-v1','allowed_application_changes':[],
                        'approved_word_contract_adapter_changes':{key:{'baseline_sha256':BUILD.digest(baseline[key]),'sha256':BUILD.digest(portable[key])} for key in names}}
                self.assertEqual(set(VERIFY.verify(source,portable,baseline,policy)['approved_word_contract_adapter_changes']),set(names))
                policy['approved_word_contract_adapter_changes'][name]['sha256']='0'*64
                with self.assertRaisesRegex(ValueError,'Protected Word'):VERIFY.verify(source,portable,baseline,policy)

    def test_zip_windows_case_collision_and_multiple_wrappers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for index,names in enumerate([['B/app/A','B/app/a'],['B/a','C/b'],['B/../outside']]):
                path=Path(directory)/(str(index)+'.zip')
                with zipfile.ZipFile(path,'w') as archive:
                    for name in names:archive.writestr(name,b'payload')
                for reader in (BUILD.read_zip,VERIFY.entries):
                    with self.subTest(reader=reader.__module__,names=names),self.assertRaises(ValueError):reader(path)

    def test_css_approval_requires_both_exact_fingerprints(self):
        source,baseline=self.fixture();portable=copy.deepcopy(baseline)
        name='app/web/style.css';source[name]=portable[name]=b'approved new notebook layout'
        seal(source);seal(portable)
        policy={'schema':'hrs-release-policy-v1','allowed_application_changes':[name,'app/MANIFEST.json'],
                'approved_css_changes':{name:{'baseline_sha256':BUILD.digest(baseline[name]),'sha256':BUILD.digest(portable[name])}}}
        self.assertEqual(VERIFY.verify(source,portable,baseline,policy)['approved_css_changes'],[name])
        policy['approved_css_changes'][name]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Protected payload'):
            VERIFY.verify(source,portable,baseline,policy)


if __name__=='__main__':unittest.main(verbosity=2)
