"""HRS-owned plan/apply: only the selected range may change in the original."""
from pathlib import Path
import sys,tempfile,unittest,json,hashlib
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from block_cli import plan,write_plan,apply_plan,BlockCommandError
from project_commit import report_lock

def sha(raw):return hashlib.sha256(raw).hexdigest()
def table(caption='原题',ident='tbl-one'):
 return '```report-table\r\n'+json.dumps({'schema':'report-table-v1','id':ident,'caption':caption,'rows':[[{'text':'参数 😀','rowspan':1,'colspan':1}]]},ensure_ascii=False)+'\r\n```\r\n'

class BlockCommit(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  self.project=self.root/'project';(self.project/'assets').mkdir(parents=True)
  self.file=self.project/'report.md';self.raw=('\ufeff# 报告 😀\r\n\r\n'+table()+'\r\n见 @tbl:tbl-one。\r\n尾部 `\\` $ 和 < >。\r\n').encode('utf8');self.file.write_bytes(self.raw)
 def test_section_plan_relocates_exact_path_and_preserves_other_sections(self):
  raw='\ufeff# 甲\r\n\r\n## 结果\r\n\r\n旧结果😀。\r\n\r\n# 乙\r\n\r\n## 结果\r\n\r\n保留。\r\n'
  self.file.write_bytes(raw.encode())
  # UX-2.5: metadata follows the common CLI commit, with unknown old dates
  # retained and only edited sections/ancestors changing. Dates are not source.
  import document_timestamps as times
  baseline=times.reconcile(raw.removeprefix('\ufeff'),fresh=True,now='2020-01-01T00:00+00:00');times.store(self.project,baseline)
  with self.assertRaisesRegex(ValueError,'AMBIGUOUS_SECTION'):plan(self.file,sha(raw.encode()),'新增',section=['结果'],operation='append')
  result,candidate=plan(self.file,sha(raw.encode()),'测量 $x=2$。\n第二行。\n',section=['甲','结果'],operation='append')
  self.assertEqual(candidate.decode(),raw.replace('# 乙','测量 $x=2$。\r\n第二行。\r\n\r\n# 乙',1))
  path=self.root/'section.json';receipt=write_plan(path,result,candidate);out=apply_plan(path,receipt['plan_sha256'])
  self.assertEqual(self.file.read_bytes(),candidate);self.assertEqual(Path(out['backup']).read_bytes(),raw.encode())
  saved=times.load(self.project,candidate.decode('utf-8-sig'))
  self.assertEqual([r['key'] for r in saved['records']],[r['key'] for r in baseline['records']])
  for n in (0,1):
   self.assertEqual(saved['records'][n]['created'],baseline['records'][n]['created'])
   self.assertNotEqual(saved['records'][n]['modified'],baseline['records'][n]['modified'])
  for before,after in zip(baseline['records'][2:],saved['records'][2:]):
   self.assertEqual((after['key'],after['created'],after['modified']),(before['key'],before['created'],before['modified']))
  moved='# 乙\r\n\r\n## 结果\r\n\r\n保留。\r\n\r\n# 甲\r\n\r\n## 结果\r\n\r\n旧结果😀。\r\n'
  reordered=times.reconcile(moved,baseline)
  self.assertEqual(reordered['records'][0]['key'],baseline['records'][2]['key'])
  self.assertEqual(reordered['records'][2]['key'],baseline['records'][0]['key'])
  # New body offsets never require timestamp text in Markdown.
  self.assertNotIn('2020-',candidate.decode('utf-8-sig'))
  self.assertIsNone(times.load(None,raw)['records'][0]['created'])
 def test_section_prepend_replace_and_rejected_missing_reference(self):
  raw='# 文章\n\n## 结果 {#sec-result}\n\n旧内容。\n\n## 结论\n\n保留。\n';self.file.write_bytes(raw.encode())
  for operation in ('prepend','replace-body'):
   result,candidate=plan(self.file,sha(raw.encode()),'新内容。\n',section=['结果'],operation=operation)
   self.assertTrue(candidate.startswith(b'# '));self.assertTrue(candidate.decode().endswith('## 结论\n\n保留。\n'))
   self.assertIn('旧内容',candidate.decode()) if operation=='prepend' else self.assertNotIn('旧内容',candidate.decode())
  with self.assertRaisesRegex(ValueError,'MISSING_REFERENCE'):plan(self.file,sha(raw.encode()),'见 @fig:fig-absent',section=['结果'],operation='append')
  self.assertEqual(self.file.read_bytes(),raw.encode())
 def create(self,replacement=None,operation='replace'):
  result,candidate=plan(self.project,sha(self.raw),table('新题') if replacement is None else replacement,object_id='tbl-one',operation=operation)
  path=self.root/'plan.json';receipt=write_plan(path,result,candidate);return path,receipt,candidate
 def test_apply_preserves_outside_bytes_crlf_bom_unicode_and_backup(self):
  import document_timestamps as times
  baseline=times.reconcile(self.raw.decode('utf-8-sig'),fresh=True,now='2020-01-01T00:00+00:00');times.store(self.project,baseline)
  path,receipt,candidate=self.create();self.assertEqual(self.file.read_bytes(),self.raw)
  result=apply_plan(path,receipt['plan_sha256'])
  self.assertEqual(self.file.read_bytes(),self.raw.replace('原题'.encode(),'新题'.encode()))
  self.assertEqual(Path(result['backup']).read_bytes(),self.raw);self.assertEqual(candidate,self.file.read_bytes())
  current=candidate.decode('utf-8-sig');saved=times.load(self.project,current)
  self.assertEqual([r['key'] for r in saved['records']],[r['key'] for r in baseline['records']])
  broken=current.replace('"schema": "report-table-v1"','"schema":',1)
  pending=times.advance(current,broken,saved)
  self.assertTrue(pending['records'][1]['pending']);self.assertEqual(pending['records'][1]['key'],saved['records'][1]['key'])
  repaired=times.advance(broken,current,pending)
  self.assertEqual(repaired['records'][1]['key'],saved['records'][1]['key'])
  record=saved['records'][1];encoded=current.encode('utf-16-le')
  removed=(encoded[:record['start']*2]+encoded[record['end']*2:]).decode('utf-16-le')
  self.assertEqual(len(times.advance(current,removed,saved)['records']),1)
  copied=times.advance(current,current+'\r\n'+table('副本','tbl-new'),saved)
  self.assertEqual(copied['records'][1]['key'],saved['records'][1]['key'])
  self.assertNotEqual(copied['records'][2]['key'],saved['records'][1]['key'])
  self.assertIsNotNone(copied['records'][2]['created'])
 def test_stale_source_is_rejected_and_new_source_is_kept(self):
  path,receipt,_=self.create();changed=self.raw+b'new\r\n';self.file.write_bytes(changed)
  with self.assertRaisesRegex(ValueError,'STALE_SNAPSHOT'):apply_plan(path,receipt['plan_sha256'])
  self.assertEqual(self.file.read_bytes(),changed)
 def test_candidate_and_reviewed_plan_tampering_are_rejected(self):
  path,receipt,_=self.create();candidate=Path(receipt['candidate']);candidate.write_bytes(candidate.read_bytes()+b'outside')
  with self.assertRaisesRegex(ValueError,'CANDIDATE_CHANGED'):apply_plan(path,receipt['plan_sha256'])
  path.write_bytes(path.read_bytes()+b' ')
  with self.assertRaisesRegex(ValueError,'PLAN_CHANGED'):apply_plan(path,receipt['plan_sha256'])
  self.assertEqual(self.file.read_bytes(),self.raw)
 def test_candidate_scope_is_recomputed_not_trusted(self):
  path,receipt,_=self.create();data=json.loads(path.read_text(encoding='utf8'));data['target']['start']=0;path.write_text(json.dumps(data),encoding='utf8')
  with self.assertRaisesRegex(ValueError,'PLAN_SCOPE_CHANGED'):apply_plan(path,sha(path.read_bytes()))
  self.assertEqual(self.file.read_bytes(),self.raw)
 def test_insert_before_and_after_share_the_commit_path(self):
  for operation in ('insert-before','insert-after'):
   with self.subTest(operation=operation):
    self.file.write_bytes(self.raw)
    result,candidate=plan(self.project,sha(self.raw),table('新增','tbl-new'),object_id='tbl-one',operation=operation)
    path=self.root/(operation+'.json');receipt=write_plan(path,result,candidate);apply_plan(path,receipt['plan_sha256'])
    self.assertEqual(self.file.read_bytes(),candidate);self.assertIn(self.raw[:self.raw.index(b'```')],candidate)
 def test_missing_asset_and_removed_reference_target_are_rejected(self):
  with self.assertRaisesRegex(ValueError,'MISSING_REFERENCE'):self.create(table('别的','tbl-other'))
  with self.assertRaisesRegex(ValueError,'MISSING_ASSET'):self.create('![图](assets/absent.png)\r\n'+table('新题'))
  self.assertEqual(self.file.read_bytes(),self.raw)
 def test_cooperating_writer_lock_and_failed_replace_keep_original(self):
  path,receipt,_=self.create()
  with report_lock(self.project):
   with self.assertRaisesRegex(ValueError,'WRITE_BUSY'):apply_plan(path,receipt['plan_sha256'])
  import studio
  original=studio.atomic_write
  def blocked(target,data):
   if target==self.file:raise PermissionError('file occupied')
   return original(target,data)
  with patch('project_commit.atomic_write',blocked):
   with self.assertRaises(PermissionError):apply_plan(path,receipt['plan_sha256'])
  self.assertEqual(self.file.read_bytes(),self.raw)
 def test_source_changed_during_backup_is_not_overwritten(self):
  path,receipt,_=self.create()
  def changed(folder):self.file.write_bytes(self.raw+b'changed');return self.root/'unused'
  with patch('project_commit.backup_report',changed):
   with self.assertRaisesRegex(ValueError,'STALE_SNAPSHOT'):apply_plan(path,receipt['plan_sha256'])
  self.assertEqual(self.file.read_bytes(),self.raw+b'changed')
 def test_changed_resource_is_rejected_without_writing_assets(self):
  file=self.project/'assets/a.svg';file.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="16"><rect width="24" height="16" fill="blue"/></svg>')
  path,receipt,_=self.create(table('新题')+'\r\n![图](assets/a.svg)\r\n')
  file.write_bytes(file.read_bytes().replace(b'blue',b'red'))
  with self.assertRaisesRegex(ValueError,'ASSET_CHANGED'):apply_plan(path,receipt['plan_sha256'])
  self.assertEqual(self.file.read_bytes(),self.raw)
 @unittest.skipUnless(sys.platform=='win32','Windows file sharing contract')
 def test_actual_windows_file_occupation_keeps_source_and_cleans_temp(self):
  import ctypes
  from ctypes import wintypes
  path,receipt,_=self.create();kernel=ctypes.WinDLL('kernel32',use_last_error=True)
  kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];kernel.CreateFileW.restype=wintypes.HANDLE
  handle=kernel.CreateFileW(str(self.file),0x80000000,1,None,3,128,None)
  self.assertNotEqual(handle,wintypes.HANDLE(-1).value)
  try:
   with self.assertRaises(PermissionError):apply_plan(path,receipt['plan_sha256'])
  finally:kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(handle)
  self.assertEqual(self.file.read_bytes(),self.raw);self.assertEqual(list(self.project.glob('.tmp_*')),[])

if __name__=='__main__':unittest.main()
