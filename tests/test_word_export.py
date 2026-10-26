"""Word UI adapter boundaries; the existing converter is exercised by the UI suite."""
from pathlib import Path
import json,os,sys,tempfile,threading,unittest,urllib.request,urllib.error,zipfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from studio import StudioServer,Handler,digest
from word_export import WordExport,check_template,runtime_paths
from word_import import selected_source


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


if __name__=='__main__':unittest.main()
