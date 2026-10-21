"""An open editor cannot overwrite a block apply made after its saved revision."""
from pathlib import Path
import sys,tempfile,threading,unittest,json,hashlib
from urllib.request import Request,urlopen
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from studio import StudioServer,Handler
from block_cli import plan,write_plan,apply_plan

class SaveInteraction(unittest.TestCase):
 def test_apply_invalidates_old_gui_revision_and_keeps_recovery_draft(self):
  with tempfile.TemporaryDirectory(prefix='hrs-block-api-') as d:
   folder=Path(d);project=folder/'project';(project/'assets').mkdir(parents=True)
   raw=b'# Report\r\n\r\n## Original\r\n';(project/'report.md').write_bytes(raw)
   class Quiet(Handler):
    def log_message(self,*args):pass
   server=StudioServer(('127.0.0.1',0),project,folder/'workspace');server.RequestHandlerClass=Quiet
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   base='http://127.0.0.1:'+str(server.server_port)
   def post(path,payload):
    request=Request(base+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    try:
     with urlopen(request) as response:return response.status,json.load(response)
    except HTTPError as error:return error.code,json.load(error)
   try:
    with urlopen(base+'/api/doc?document_id=legacy') as response:old=json.load(response)
    draft={'document_id':'legacy','draft_id':'a'*32,'template':'engineering','base_revision':old['revision'],'seq':1,'markdown':raw.decode()+'\r\nUncommitted GUI draft.\r\n'}
    self.assertEqual(post('/api/draft',draft)[0],200)
    data,candidate=plan(project,old['revision'],'## Changed\r\n',index=2)
    artifact=write_plan(folder/'plan.json',data,candidate);apply_plan(folder/'plan.json',artifact['plan_sha256'])
    status,reply=post('/api/save',{**draft,'revision':old['revision']});self.assertEqual(status,409,reply)
    self.assertEqual(server.read_draft('a'*32)['markdown'],draft['markdown']);self.assertEqual((project/'report.md').read_bytes(),candidate)
    # Saving incomplete engineering headings is allowed, while output validation fails.
    incomplete='# One\n\n# Two\n';revision=hashlib.sha256(candidate).hexdigest()
    status,reply=post('/api/save',{**draft,'revision':revision,'markdown':incomplete,'render_profile':'engineering'})
    self.assertEqual(status,200,reply);self.assertEqual((project/'report.md').read_bytes(),incomplete.encode())
    self.assertFalse(post('/api/validate',{'markdown':incomplete,'render_profile':'engineering'})[1]['valid'])
   finally:server.shutdown();server.server_close();thread.join(timeout=3)

if __name__=='__main__':unittest.main()
