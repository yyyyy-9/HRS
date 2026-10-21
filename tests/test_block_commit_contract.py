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
 def create(self,replacement=None,operation='replace'):
  result,candidate=plan(self.project,sha(self.raw),table('新题') if replacement is None else replacement,object_id='tbl-one',operation=operation)
  path=self.root/'plan.json';receipt=write_plan(path,result,candidate);return path,receipt,candidate
 def test_apply_preserves_outside_bytes_crlf_bom_unicode_and_backup(self):
  path,receipt,candidate=self.create();self.assertEqual(self.file.read_bytes(),self.raw)
  result=apply_plan(path,receipt['plan_sha256'])
  self.assertEqual(self.file.read_bytes(),self.raw.replace('原题'.encode(),'新题'.encode()))
  self.assertEqual(Path(result['backup']).read_bytes(),self.raw);self.assertEqual(candidate,self.file.read_bytes())
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
  path,receipt,_=self.create();data=json.loads(path.read_text());data['target']['start']=0;path.write_text(json.dumps(data),encoding='utf8')
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
  with patch('studio.atomic_write',blocked):
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
