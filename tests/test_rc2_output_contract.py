"""RC2-03/07: engineering output policy is separate from valid source saving."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from report_contract import analyze
import render_profile as policy

class OutputPolicy(unittest.TestCase):
 def codes(self,text,profile='engineering'):
  return {d['code']:d for d in policy.output_checks(analyze(text),profile)}
 def test_multiple_h1_blocks_output_but_not_core_source(self):
  source='# 报告\n\n## 章节\n\n# 又一主标题\n'
  self.assertTrue(analyze(source)['ok'])
  self.assertEqual(self.codes(source)['MULTIPLE_H1']['severity'],'error')
 def test_downward_gap_is_error_but_ascending_to_parent_is_valid(self):
  self.assertEqual(self.codes('# 报告\n\n## 一\n\n#### 跳级\n')['HEADING_LEVEL_GAP']['severity'],'error')
  self.assertNotIn('HEADING_LEVEL_GAP',self.codes('# 报告\n\n## 一\n\n### 子\n\n## 二\n'))
 def test_numbered_body_title_is_warning_not_rewritten(self):
  source='# 2026 报告\n\n## 1 手工章号\n'
  notice=self.codes(source)['HEADING_SOURCE_PREFIX']
  self.assertEqual(notice['severity'],'warning');self.assertEqual(notice['line'],3)
 def test_free_and_code_examples_do_not_activate_engineering_errors(self):
  self.assertEqual(self.codes('# 一\n\n# 二\n\n##### 五\n','free'),{})
  self.assertEqual(self.codes('# 一\n\n```markdown\n# 二\n##### 五\n```\n'),{})
 def test_options_default_show_and_validate_boolean(self):
  self.assertEqual(policy.normalize_options(None),{'show_object_numbers':True,'show_heading_numbers':False,'preserve_blank_lines':False})
  self.assertEqual(policy.normalize_options({'show_object_numbers':False}),{'show_object_numbers':False,'show_heading_numbers':False,'preserve_blank_lines':False})
  with self.assertRaises(ValueError):policy.normalize_options({'show_object_numbers':'no'})
  self.assertEqual(policy.normalize_options({'show_heading_numbers':True}),{'show_object_numbers':True,'show_heading_numbers':True,'preserve_blank_lines':False})
  with self.assertRaises(ValueError):policy.normalize_options({'show_heading_numbers':1})
 def test_real_feedback_has_both_heading_failures(self):
  fixture=Path(__file__).with_name('fixtures')/'rc2_feedback'
  ir=analyze((fixture/'report.md').read_text(encoding='utf8'),assets=fixture/'assets')
  self.assertTrue(ir['ok'],ir['diagnostics'])
  codes={d['code'] for d in policy.output_checks(ir,'engineering')}
  self.assertTrue({'MULTIPLE_H1','HEADING_LEVEL_GAP'}<=codes)

if __name__=='__main__':unittest.main()
