"""RC3-01: save validates the IR's attachments, not literal tutorial paths."""
from pathlib import Path
import json, sys, tempfile, threading, unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app'))
from studio import StudioServer, Handler

class SaveAssets(unittest.TestCase):
 def test_code_and_prose_paths_are_not_attachments_but_real_missing_images_fail(self):
  with tempfile.TemporaryDirectory(prefix='hrs-rc3-save-api-') as d:
   folder=Path(d);project=folder/'project';(project/'assets').mkdir(parents=True)
   (project/'report.md').write_bytes(b'# Report\n')
   class Quiet(Handler):
    def log_message(self,*args):pass
   server=StudioServer(('127.0.0.1',0),project,folder/'workspace');server.RequestHandlerClass=Quiet
   worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
   base='http://127.0.0.1:'+str(server.server_port)
   def post(path,data):
    try:
     with urlopen(Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})) as response:return response.status,json.load(response)
    except HTTPError as error:return error.code,json.load(error)
   try:
    with urlopen(base+'/api/doc?document_id=legacy') as response:revision=json.load(response)['revision']
    md='# Report\n\n```markdown\n![example](.assets/photo.png)\n<img src="assets/code.png">\n```\n\n`![inline](assets/inline.png)` and assets/plain.png\n\n<!-- ![comment](assets/comment.png) -->\n'
    draft={'document_id':'legacy','draft_id':'c'*32,'template':'engineering','base_revision':revision,'seq':1,'markdown':md}
    self.assertEqual(post('/api/draft',draft)[0],200)
    status,result=post('/api/save',{**draft,'revision':revision})
    self.assertEqual(status,200,result);self.assertEqual((project/'report.md').read_bytes(),md.encode())
    revision=result['revision']
    for extra in ('![actual](assets/missing.png)','<img src="assets/missing.png">'):
     candidate=md+'\n'+extra+'\n'
     self.assertEqual(post('/api/draft',{**draft,'seq':2,'base_revision':revision,'markdown':candidate})[0],200)
     status,result=post('/api/save',{**draft,'revision':revision,'markdown':candidate})
     self.assertEqual(status,400,result);self.assertIn('missing.png',result['error'])
     self.assertEqual((project/'report.md').read_bytes(),md.encode())
   finally:server.shutdown();server.server_close();worker.join(timeout=3)

if __name__=='__main__':unittest.main()
