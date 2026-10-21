"""PF13.5: objects, snapshots and syntax policy are document-level, not engineering semantics."""
import json, tempfile, hashlib, pathlib, subprocess, sys, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from report_contract import analyze
from agent_readonly import project
from pipe_table_contract import parse_at
F=json.loads((ROOT/'tests/fixtures/pf135_contract_cases.json').read_text('utf8'))
def table(id, caption=''):
 return '```report-table\n'+json.dumps({'schema':'report-table-v1','id':id,'caption':caption,
   'rows':[[{'text':'1','rowspan':1,'colspan':1}]]})+'\n```\n'
def figure(id,caption=''):
 return '```report-figure\n'+json.dumps({'schema':'report-figure-v1','id':id,'caption':caption,
    'kind':'mermaid','source':'flowchart LR\n A[开始] --> B[结束]'})+'\n```\n'
class PF135(unittest.TestCase):
 def test_caption_adjacent_is_canonical_but_legacy_reads(self):
  for key,oid in [('canonicalCaption','tbl-adjacent'),('legacyCaption','tbl-legacy')]:
   md=F[key];ir=analyze(md)
   self.assertTrue(ir['ok'],ir['diagnostics']);self.assertEqual(ir['blocks'][0]['id'],oid)
   self.assertIn(oid,ir['blocks'][0]['source'])
   self.assertFalse(ir['blocks'][0]['numbered']);self.assertIsNone(ir['objects']['entries'][0]['number'])
  separate=analyze(F['notACaption'])
  self.assertNotIn('id', next(b for b in separate['blocks'] if b['type']=='table'))
 def test_math_ref_exclusions_are_contextual(self):
  ir=analyze(F['canonicalCaption']+'\n'+F['referenceMath'])
  self.assertEqual([r['target'] for r in ir['references']],['tbl-adjacent']);self.assertTrue(ir['ok'],ir['diagnostics'])
  text='Only \\(@tbl:tbl-bogus\\) and $@eq:eq-bogus$ are math.\n'
  self.assertEqual(analyze(text)['references'],[])
  self.assertEqual(analyze('\\\\(@tbl:tbl-bogus\\) is literal')['references'][0]['target'],'tbl-bogus')
 def test_lookup_is_snapshot_bound_and_unique(self):
  ir=analyze(F['canonicalCaption'])
  old=project(ir,'outline');digest=old['snapshot']['text_utf8_sha256']
  self.assertEqual(project(ir,'get-block',block_index=0)['lookupStatus'],'MISSING_SNAPSHOT_PRECONDITION')
  self.assertEqual(project(ir,'get-block',block_index=0,expected_sha256='0'*64)['lookupStatus'],'STALE_SNAPSHOT')
  good=project(ir,'get-block',block_index=0,expected_sha256=digest)
  self.assertTrue(good['found']);self.assertIn('tbl-adjacent',good['block']['source'])
  ir2=analyze('# Inserted\n\n'+F['canonicalCaption'])
  stale=project(ir2,'get-block',block_index=0,expected_sha256=digest)
  self.assertFalse(stale['found']);self.assertNotIn('block',stale)
  same=table('tbl-dup')+'\n'+table('tbl-dup')
  dup=project(analyze(same),'get',object_id='tbl-dup')
  self.assertTrue(dup['ambiguous']);self.assertFalse(dup['found']);self.assertNotIn('block',dup)
  self.assertEqual(dup['lookupStatus'],'AMBIGUOUS_ID')
 def test_numbers_and_unknown_fields(self):
  invalid='```report-table\n'+json.dumps({'schema':'report-table-v1','id':'invalid','caption':'bad','rows':[]})+'\n```\n'
  grouped='::: {#fig-group layout-ncol=2}\n![A](assets/0123456789abcdef.png)\n![B](assets/0123456789abcdee.png)\n:::\n'
  md=invalid+'\n'+F['canonicalCaption']+'\n'+table('tbl-ok')+'\n'+figure('fig-one')+'\n'+grouped+'\n'+table('tbl-second')
  ir=analyze(md)
  self.assertEqual([(b['type'],b.get('number')) for b in ir['blocks'] if b.get('number')],
   [('table',1),('figure',1),('image-group',2),('table',2)])
  self.assertEqual([(e['id'],e['number']) for e in ir['objects']['entries']],
   [('tbl-adjacent',None),('tbl-ok',1),('fig-one',1),('fig-group',2),('tbl-second',2)])
  extra={'schema':'report-table-v1','id':'tbl-extra','caption':'',
   'rows':[[{'text':'1','rowspan':1,'colspan':1,'futureSemantic':'x'}]]}
  out=analyze('```report-table\n'+json.dumps(extra)+'\n```\n')
  self.assertTrue(out['ok']);self.assertIn('futureSemantic',out['blocks'][0]['data']['rows'][0][0]);
  self.assertIn('UNSUPPORTED_OBJECT_FIELDS',[d['code'] for d in out['diagnostics']]);
  self.assertFalse(project(out)['safeToCompile'])
 def test_cli_never_writes_and_rejects_stale(self):
  text=F['canonicalCaption'];
  with tempfile.TemporaryDirectory() as temp:
   path=pathlib.Path(temp)/'report.md';path.write_bytes(text.encode())
   cmd=[sys.executable,str(ROOT/'app/agent_readonly.py')]
   def call(*args):
    result=subprocess.run(cmd+list(args),capture_output=True,text=True)
    return result.returncode,json.loads(result.stdout)
   rc,outline=call('outline',str(path));self.assertEqual(rc,0)
   sha=outline['snapshot']['text_utf8_sha256']
   rc,bad=call('get-block',str(path),'--index','0');self.assertNotEqual(rc,0)
   self.assertEqual(bad['lookupStatus'],'MISSING_SNAPSHOT_PRECONDITION')
   rc,good=call('get-block',str(path),'--index','0','--expect-sha256',sha)
   self.assertEqual(rc,0);self.assertTrue(good['found'])
   path.write_bytes(('# h\n\n'+text).encode())
   rc,stale=call('get-block',str(path),'--index','0','--expect-sha256',sha)
   self.assertNotEqual(rc,0);self.assertEqual(stale['lookupStatus'],'STALE_SNAPSHOT')
   self.assertEqual(list(pathlib.Path(temp).iterdir()),[path])
if __name__=='__main__':unittest.main()
