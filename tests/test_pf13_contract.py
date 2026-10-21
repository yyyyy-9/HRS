"""PF13 verticalAlign contract and trusted reader compatibility checks."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(ROOT))
from report_contract import validate_table, ContractError, analyze
import studio

BASE={'schema':'report-table-v1','id':'tbl-demo','caption':'结果','rows':[[{'text':'A','rowspan':1,'colspan':1}]]}

class TestPF13Contract(unittest.TestCase):
 def test_default_keeps_existing_contract_untouched(self):
  obj=validate_table(dict(BASE))
  self.assertNotIn('align',obj)
  self.assertNotIn('verticalAlign',obj)
  self.assertEqual(BASE['rows'],obj['rows'])
 def test_center_horizontally_and_vertically(self):
  obj=validate_table(dict(BASE,align=['center'],verticalAlign='middle'))
  self.assertEqual(obj['align'],['center'])
  self.assertEqual(obj['verticalAlign'],'middle')
 def test_all_vertical_choices(self):
  for value in ('top','middle','bottom'):
   with self.subTest(value=value):
    self.assertEqual(validate_table(dict(BASE,verticalAlign=value))['verticalAlign'],value)
 def test_reject_unknown_and_malformed_vertical_values(self):
  for value in ('justify','auto',None,[],0,True,{'x':1}):
   with self.subTest(value=value),self.assertRaises(ContractError):
    validate_table(dict(BASE,verticalAlign=value))
 def test_ir_preserves_alignment(self):
  obj=dict(BASE,align=['center'],verticalAlign='middle')
  md='```report-table\n'+json.dumps(obj,ensure_ascii=False)+'\n```'
  ir=analyze(md)
  tables=[b for b in ir['blocks'] if b.get('type')=='table']
  self.assertEqual(len(tables),1)
  self.assertEqual(tables[0]['data']['verticalAlign'],'middle')
  self.assertEqual(tables[0]['data']['align'],['center'])
 def test_pf12_offline_reader_remains_importable(self):
  # Official PF12 reader digest is a fixed release fixture, independent of
  # previous developer folders. A bundle import test belongs to release E2E.
  self.assertIn('906c8d3447b0ccda8b7e71055e3bf7ef66e064506a27d33d05ad5e701a322473',studio.LEGACY_READER_SHA256)
 def test_current_offline_runtime_audit(self):
  runtime=(ROOT/'web/report_reader.js').read_text('utf8')
  html='<!doctype html><html><head><meta charset="utf-8"></head><body><div id="report-source"></div><script id="hrs-reader-runtime">'+runtime+'</script></body></html>'
  studio.audit_export(html)

if __name__=='__main__':unittest.main(verbosity=2)
