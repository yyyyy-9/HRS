"""R8-EXPERIENCE-01: source/draft binding and isolated incomplete report saves."""
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import hashlib
import json
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from studio import StudioServer
from report_workspace import info


class WorkspaceService(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.project=self.root/'original';self.project.mkdir()
        self.full='# 总台账\r\n\r\n# 单篇\r\n\r\n中文正文\r\n'
        (self.project/'report.md').write_bytes(self.full.encode('utf8'))
        self.server=StudioServer(('127.0.0.1',0),self.project,self.root/'state',require_project_location=True)
        thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.05},daemon=True);thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(thread.join,3);self.addCleanup(self.server.shutdown)
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.request={'document_id':'legacy','draft_id':'a'*32,'template':'engineering','revision':self.sha(self.full),
                      'full_markdown':self.full,'source_sha256':self.sha(self.full),'markdown':'# 单篇\r\n\r\n中文正文\r\n',
                      'title':'单篇','color_theme':'blue','action':'create'}

    @staticmethod
    def sha(text):return hashlib.sha256(text.encode('utf8')).hexdigest()

    def post(self,path,body,authorized=True):
        headers={'Content-Type':'application/json','Origin':self.url}
        if authorized:headers['X-HRS-Project-Action']='user-action'
        request=Request(self.url+path,json.dumps(body).encode('utf8'),headers,method='POST')
        try:
            with urlopen(request,timeout=5) as response:return response.status,json.load(response)
        except HTTPError as error:return error.code,json.load(error)


class WorkspaceTransaction(WorkspaceService):
    def test_create_is_source_bound_and_does_not_write_origin(self):
        status,result=self.post('/api/report-workspace',self.request)
        self.assertEqual(status,200,result);p=self.server.project_path(result['document_id'])
        self.assertEqual((p/'report.md').read_bytes(),self.request['markdown'].encode('utf8'))
        self.assertEqual((self.project/'report.md').read_bytes(),self.full.encode('utf8'))
        metadata=info(p,self.server.workspace);self.assertEqual(metadata['source_sha256'],self.sha(self.full))
        self.assertEqual(json.loads((p/'meta.json').read_text('utf8'))['render_profile'],'engineering')
        self.assertEqual(list((self.project/'output').iterdir()),[])

    def test_stale_or_unconfirmed_draft_and_missing_action_cannot_create(self):
        for changed in [dict(source_sha256='0'*64),dict(full_markdown=self.full+'changed',source_sha256=self.sha(self.full+'changed')),dict(revision='0'*64)]:
            with self.subTest(changed=changed):
                status,result=self.post('/api/report-workspace',{**self.request,**changed})
                self.assertGreaterEqual(status,400,result)
        status,_=self.post('/api/report-workspace',self.request,authorized=False);self.assertEqual(status,403)
        self.assertEqual([p for p in self.server.workspace.iterdir() if p.is_dir() and len(p.name)==32],[])
        self.assertEqual((self.project/'report.md').read_bytes(),self.full.encode('utf8'))

    def test_incomplete_temporary_text_can_be_saved_without_writing_origin(self):
        incomplete='# 单篇\n\nText[^a]\n\n[^a]: One\n[^a]: Two\n'
        _,created=self.post('/api/report-workspace',{**self.request,'markdown':incomplete})
        p=self.server.project_path(created['document_id']);edited=incomplete+'\nMore editing\n'
        status,result=self.post('/api/save',{'document_id':created['document_id'],'draft_id':'b'*32,'template':'engineering',
                                            'revision':self.sha(incomplete),'markdown':edited})
        self.assertEqual(status,200,result);self.assertEqual((p/'report.md').read_text('utf8'),edited)
        self.assertIsNotNone(info(p,self.server.workspace));self.assertEqual((self.project/'report.md').read_bytes(),self.full.encode('utf8'))

    def test_external_metadata_cannot_claim_internal_workspace_privilege(self):
        _,created=self.post('/api/report-workspace',self.request)
        p=self.server.project_path(created['document_id'])
        (self.project/'meta.json').write_bytes((p/'meta.json').read_bytes())
        self.assertIsNone(info(self.project,self.server.workspace))


if __name__=='__main__':unittest.main()
