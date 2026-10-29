"""Word UI adapter boundaries; the existing converter is exercised by the UI suite."""
from pathlib import Path
from contextlib import contextmanager,redirect_stdout
import io,time
import json,os,sys,tempfile,threading,unittest,urllib.request,urllib.error,zipfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from studio import StudioServer,Handler,digest
from word_export import WordExport,check_template,runtime_paths
from word_import import selected_source


@contextmanager
def held_word_file(path,allow_read=True):
    """Real Windows sharing; neither mode grants deletion to another handle."""
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE;kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.CreateFileW(str(path),0x80000000,3 if allow_read else 0,None,3,0x80,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:yield
    finally:kernel.CloseHandle(handle)


class WordBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='hrs-word-boundary-');self.root=Path(self.tmp.name).resolve()
        self.project=self.root/'project';self.project.mkdir();self.raw=b'# Source\n\n## Chapter\n'
        (self.project/'report.md').write_bytes(self.raw)
        class Quiet(Handler):
            def log_message(self,*args):pass
        self.server=StudioServer(('127.0.0.1',0),self.project,self.root/'workspace');self.server.RequestHandlerClass=Quiet
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.payload={'document_id':'legacy','draft_id':'d'*32,'revision':digest(self.raw),'markdown':self.raw.decode(),'filename':'UI导出'}

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3);self.tmp.cleanup()

    def post(self,action,data=None,authorized=True):
        headers={'Content-Type':'application/json','Origin':self.base}
        if authorized:headers['X-HRS-Project-Action']='user-action'
        req=urllib.request.Request(self.base+'/api/word/'+action,data=json.dumps(data or self.payload).encode(),headers=headers)
        try:response=urllib.request.urlopen(req)
        except urllib.error.HTTPError as error:response=error
        with response:return response.status,json.loads(response.read())

    def test_native_path_authority_and_engineering_checks(self):
        self.assertEqual(self.post('options',authorized=False)[0],403)
        status,result=self.post('prepare',{**self.payload,'template_token':'C:/arbitrary.docx'})
        self.assertEqual(status,400);self.assertIn('模板选择',result['error'])
        for source in ['# A\n\n# B\n','# A\n\n## B\n\n#### Jump\n']:
            status,result=self.post('prepare',{**self.payload,'markdown':source,'render_profile':'free'})
            self.assertEqual(status,400);self.assertFalse(result['ok'])
        self.assertEqual((self.project/'report.md').read_bytes(),self.raw)
        self.assertEqual(list((self.project/'output').iterdir()),[])

    def test_template_token_binding_snapshot_and_persistence(self):
        path=self.root/'模板.docx'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('word/document.xml','<x/>');archive.writestr('word/styles.xml','<x/>')
        exporter=self.server.word_export;selected=exporter.select_template('one',path)
        token=selected['template_token']
        with self.assertRaisesRegex(ValueError,'不属于'):exporter.template('two',token)
        self.assertEqual(exporter.template('one',token)[0],path)
        exporter.remember('one',path)
        restored=WordExport(ROOT/'app',self.server.workspace)
        self.assertEqual(restored.template('one','saved')[0],path)
        with path.open('ab') as stream:stream.write(b'changed')
        with self.assertRaisesRegex(RuntimeError,'已经改变'):exporter.template('one',token)
        exporter.remember('one',None)
        with self.assertRaises(ValueError):exporter.template('one','saved')
        with self.assertRaises(ValueError):check_template(self.project/'report.md')

    def test_missing_runtime_and_revision_fail_without_source_changes(self):
        with self.assertRaises(ValueError):runtime_paths(self.root)
        with patch.object(self.server.word_export,'runtime',return_value=None):
            status,result=self.post('prepare');self.assertEqual(status,400);self.assertIn('Word',result['error'])
        status,result=self.post('prepare',{**self.payload,'revision':'0'*64})
        self.assertEqual(status,409);self.assertIn('版本已经变化',result['error'])
        self.assertFalse(self.server.word_export.running.locked())
        self.assertEqual((self.project/'report.md').read_bytes(),self.raw)
        self.assertEqual(list((self.project/'output').iterdir()),[])

    def test_word_import_requires_native_selection_origin_and_valid_session(self):
        """WORD-IMPORT-UI-01: browser paths and foreign-origin writes are refused."""
        def request(action,body,authorized=True):
            headers={'Content-Type':'application/json','Origin':self.base}
            if authorized:headers['X-HRS-Project-Action']='user-action'
            req=urllib.request.Request(self.base+'/api/import/word/'+action,data=json.dumps(body).encode(),headers=headers)
            try:response=urllib.request.urlopen(req)
            except urllib.error.HTTPError as error:response=error
            with response:return response.status,json.loads(response.read())
        with patch('studio.pick_import_file') as picker:
            for action in ('start','step','finish','cancel'):
                self.assertEqual(request(action,{},False)[0],403)
            self.assertEqual(request('start',{'source':'C:/arbitrary.docx'})[0],400)
            self.assertEqual(request('finish',{'job_token':'unknown','target':'C:/arbitrary'})[0],400)
            self.assertEqual(request('step',{'job_token':'unknown'})[0],400)
            picker.assert_not_called()
        self.assertFalse(self.server.word_import.jobs)
        self.assertEqual((self.project/'report.md').read_bytes(),self.raw)

    def test_word_import_source_zip_and_companion_limits(self):
        """A bounded frozen DOCX is required before starting native conversion."""
        path=self.root/'输入.docx';path.write_bytes(b'not a zip')
        with self.assertRaisesRegex(ValueError,'不是可读取'):selected_source(path)
        def docx(data=b'<x/>'):
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('[Content_Types].xml','<x/>');archive.writestr('word/document.xml',data)
        docx();original=path.read_bytes()
        self.assertEqual(selected_source(path)[1:],(original,None))
        mapping=Path(str(path)+'.hrs-bridge.json');mapping.write_bytes(b'{"source":"mapping"}')
        self.assertEqual(selected_source(path)[2],mapping.read_bytes())
        with patch('word_import.MAX_EXPANDED_BYTES',2):
            with self.assertRaisesRegex(ValueError,'展开超过'):selected_source(path)
        with patch('word_import.MAX_DOCX_BYTES',len(original)-1):
            with self.assertRaisesRegex(ValueError,'超过 64'):selected_source(path)
        self.assertEqual(path.read_bytes(),original)

    def test_project_copy_keeps_empty_assets_and_output_and_never_overwrites(self):
        from project_workspace import copy_project_tree
        target=self.root/'copied'
        copy_project_tree(self.project,target)
        self.assertTrue((target/'assets').is_dir());self.assertTrue((target/'output').is_dir())
        self.assertEqual((target/'report.md').read_bytes(),self.raw)
        with self.assertRaisesRegex(ValueError,'拒绝覆盖'):copy_project_tree(self.project,target)

    def staged_import(self):
        """Only conversion is pre-staged; actual source recheck/copy/registration run."""
        from unittest.mock import Mock
        temporary=tempfile.TemporaryDirectory(prefix='hrs-import-access-',dir=self.root)
        self.addCleanup(temporary.cleanup);folder=Path(temporary.name);word=self.root/'chosen.docx'
        with zipfile.ZipFile(word,'w') as archive:
            archive.writestr('[Content_Types].xml','<x/>');archive.writestr('word/document.xml','<x/>')
        frozen=folder/'input.docx';frozen.write_bytes(word.read_bytes())
        project=folder/'project';(project/'assets').mkdir(parents=True);(project/'output').mkdir()
        (project/'report.md').write_bytes(b'# Imported\n');(project/'output/word-import-source.docx').write_bytes(word.read_bytes())
        request=folder/'request.json';request.write_text(json.dumps({'source':str(word)}),encoding='utf8')
        owner=Mock();owner.is_alive.return_value=False
        importer=self.server.word_import;token='access-test'
        importer.jobs[token]={'at':time.monotonic(),'state':'ready','source':word,'sha256':digest(word.read_bytes()),
            'mapping_sha256':None,'temporary':temporary,'request':request,'runtime':{'python':Path(sys.executable),'root':ROOT},
            'files':{p.relative_to(project).as_posix():digest(p.read_bytes()) for p in project.rglob('*') if p.is_file()},
            'receipt':{'status':'COMPLETE'},'expiry':Mock(),'thread':owner,'process':None,
            'cancelled':threading.Event(),'wake':threading.Event()}
        return importer,token,folder,project,self.root/'imported'

    @unittest.skipUnless(os.name=='nt','Windows file sharing semantics')
    def test_locked_temporary_does_not_turn_a_saved_import_into_failure(self):
        """WORD-IMPORT-ACCESS-01: successful commit survives denied temp deletion."""
        importer,token,folder,project,target=self.staged_import()
        with held_word_file(folder/'input.docx'):
            result=importer.commit(token,target,lambda path:'imported-id')
            self.assertEqual(result['document_id'],'imported-id')
            self.assertTrue(result['cleanup_pending']);self.assertTrue(folder.exists())
        importer.close();self.assertFalse(folder.exists())
        self.assertEqual((target/'report.md').read_bytes(),b'# Imported\n')
        self.assertEqual((self.project/'report.md').read_bytes(),self.raw)

    def test_import_commit_never_reads_or_copies_word_in_the_host(self):
        """Source/project fingerprints and project copy belong to the same conversion Python."""
        importer,token,folder,project,target=self.staged_import()
        original=Path.read_bytes
        def read(path):
            if path.suffix.lower()=='.docx':raise AssertionError('Host must not read Word bytes')
            return original(path)
        with patch('word_import.Path.read_bytes',read),patch('word_import.copy_project_tree',side_effect=AssertionError('Host must not copy project')):
            result=importer.commit(token,target,lambda path:'imported-id')
        self.assertEqual(result['document_id'],'imported-id');self.assertFalse(folder.exists())
        self.assertEqual((target/'output/word-import-source.docx').read_bytes(),(self.root/'chosen.docx').read_bytes())

    def test_changed_staged_project_still_refuses_commit_without_overwriting(self):
        importer,token,folder,project,target=self.staged_import();(project/'report.md').write_bytes(b'# Changed\n')
        with self.assertRaisesRegex(RuntimeError,'暂存内容已变化'):importer.commit(token,target,lambda path:'id')
        self.assertFalse(target.exists());self.assertEqual((self.project/'report.md').read_bytes(),self.raw)

    @unittest.skipUnless(os.name=='nt','Windows file sharing semantics')
    def test_worker_read_denial_reports_source_stage_and_original_error(self):
        import word_import
        importer,token,folder,project,target=self.staged_import();wire=io.StringIO()
        with held_word_file(self.root/'chosen.docx',allow_read=False),redirect_stdout(wire):word_import.worker(folder/'request.json')
        reply=json.loads(wire.getvalue());self.assertFalse(reply['ok'])
        self.assertEqual(reply['details']['stage'],'source_read');self.assertEqual(reply['details']['errno'],13)
        self.assertIn('读取所选Word',reply['error']);self.assertEqual((self.project/'report.md').read_bytes(),self.raw)

    @unittest.skipUnless(os.name=='nt','Windows file sharing semantics')
    def test_worker_write_denial_identifies_snapshot_not_source(self):
        import word_import
        importer,token,folder,project,target=self.staged_import();request=folder/'request.json'
        request.write_text(json.dumps({'source':str(self.root/'chosen.docx'),'frozen':str(folder/'input.docx')}),encoding='utf8')
        wire=io.StringIO()
        with held_word_file(folder/'input.docx',allow_read=False),redirect_stdout(wire):word_import.worker(request)
        reply=json.loads(wire.getvalue());self.assertFalse(reply['ok'])
        self.assertEqual(reply['details']['stage'],'snapshot_write');self.assertEqual(reply['details']['errno'],13)
        self.assertIn('写入导入快照',reply['error']);self.assertTrue((self.root/'chosen.docx').is_file())


if __name__=='__main__':unittest.main()
