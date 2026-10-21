"""Word UI adapter boundaries; the existing converter is exercised by the UI suite."""
from pathlib import Path
import json,os,sys,tempfile,threading,unittest,urllib.request,urllib.error,zipfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from studio import StudioServer,Handler,digest
from word_export import WordExport,check_template,runtime_paths


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


if __name__=='__main__':unittest.main()
