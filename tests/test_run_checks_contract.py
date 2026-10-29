"""HAR-02: exercise the real check entry using isolated synthetic child suites."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('hrs_run_checks', ROOT / 'tools/run_checks.py')
CHECKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKS)


class CheckResults(unittest.TestCase):
    def test_native_word_environment_is_rejected_before_starting_unavailable_work(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'evidence'
            env={key:value for key,value in os.environ.items() if not key.startswith('HRS_WORD_')}
            result=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'tools/run_checks.py'),'--groups','word',
                '--browser',sys.executable,'--evidence',str(output)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf8')
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertIn('Native Word checks require',result.stderr)
            self.assertFalse(output.exists())
            desktop=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'tools/run_checks.py'),'--groups','desktop_runtime','--evidence',str(output)],cwd=ROOT,env={k:v for k,v in env.items() if not k.startswith('HRS_DESKTOP_') and k!='HRS_ELECTRON'},capture_output=True,text=True,encoding='utf8')
            from test_catalog import FEATURES
            self.assertEqual(desktop.returncode,2,desktop.stderr)
            self.assertIn('Desktop integration requires' if 'desktop_runtime' in FEATURES else 'Unknown test groups',desktop.stderr)
            self.assertFalse(output.exists())

    def test_native_word_integration_is_explicit_in_the_same_catalog(self):
        from test_catalog import select_tests
        for groups in [['full'],['browsers'],['contracts']]:
            defaults=select_tests(ROOT,groups)
            self.assertNotIn('test_report_workspace_word_browser',[t['id'] for t in defaults])
            self.assertNotIn('test_word_import_browser',[t['id'] for t in defaults])
            self.assertNotIn('test_desktop_runtime',[t['id'] for t in defaults])
            for item in defaults:
                if item['id']=='test_numbering_v2_browser':
                    self.assertNotIn('UnifiedNumbering.test_04_word_formula_numbers_and_reference_policy',item['selectors'])
                    self.assertNotIn('UnifiedNumbering.test_03_mathml_mixed_paste_preserves_inline_math_and_table',item['selectors'])
        selected=select_tests(ROOT,['report_word'])
        self.assertEqual({t['id'] for t in selected},{'test_numbering_v2_browser','test_report_workspace_word_browser','test_word_import_browser'})
        native=next(t for t in selected if t['id']=='test_numbering_v2_browser')
        self.assertEqual(native['selectors'],['UnifiedNumbering.test_03_mathml_mixed_paste_preserves_inline_math_and_table','UnifiedNumbering.test_04_word_formula_numbers_and_reference_policy','UnifiedNumbering.test_07_plain_markdown_figures_and_tables_use_native_word_numbers'])
        self.assertTrue(next(t for t in selected if t['id']=='test_report_workspace_word_browser')['explicit_selection_required'])
        self.assertTrue(next(t for t in selected if t['id']=='test_word_import_browser')['explicit_selection_required'])
        from test_catalog import FEATURES
        if 'desktop_runtime' in FEATURES:
            desktop=select_tests(ROOT,['desktop_runtime']);self.assertEqual([t['id'] for t in desktop],['test_desktop_runtime'])
            self.assertTrue(desktop[0]['explicit_selection_required'])
        else:
            with self.assertRaisesRegex(ValueError,'Unknown test groups'):
                select_tests(ROOT,['desktop_runtime'])

    def test_multiple_selectors_for_one_feature_are_unioned_once(self):
        from test_catalog import FEATURES,select_tests
        selected='heading_profile_browser:Case.first heading_profile_browser:Case.second heading_profile_browser:Case.first'
        with patch.dict(FEATURES,{'selector-probe':('selected cases',selected)}):
            item=select_tests(ROOT,['selector-probe'])[0]
            self.assertEqual(item['selectors'],['Case.first','Case.second'])
            self.assertEqual(item['features'].count('selector-probe'),1)
        with patch.dict(FEATURES,{'selector-probe':('all overrides selected cases',selected+' heading_profile_browser')}):
            self.assertIsNone(select_tests(ROOT,['selector-probe'])[0]['selectors'])

    def test_empty_module_cannot_silently_disappear_in_a_mixed_batch(self):
        """TEST-SYSTEM-01: a passing sibling must not hide an empty selected file."""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'tests').mkdir()
            (root/'tests/test_valid.py').write_text('import unittest\nclass Valid(unittest.TestCase):\n def test_ok(self): pass\n',encoding='utf8')
            (root/'tests/test_empty.py').write_text('# no cases\n',encoding='utf8')
            program=('import importlib.util,pathlib;'
                     's=importlib.util.spec_from_file_location("batch",'+repr(str(ROOT/'tools/run_python_tests.py'))+');'
                     'm=importlib.util.module_from_spec(s);s.loader.exec_module(m);'
                     'm.ROOT=pathlib.Path('+repr(str(root))+');m.main()')
            result=subprocess.run([sys.executable,'-X','utf8','-B','-c',program,'--files','tests/test_valid.py','tests/test_empty.py'],capture_output=True,text=True,encoding='utf8')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('No unittest cases in selected module',result.stderr)
    def test_browser_cli_is_selected_only_in_browser_group(self):
        """TESTENTRY-01: retain the real case once without requiring Chrome for contracts."""
        contracts=CHECKS.selected_plan(ROOT,'node','python',contracts=True,browsers=False)
        browsers=CHECKS.selected_plan(ROOT,'node','python',contracts=False,browsers=True)
        contract_ids=[test['id'] for entry in contracts for test in entry['tests']]
        browser_ids=[test['id'] for entry in browsers for test in entry['tests']]
        self.assertFalse(any(name.endswith('_browser') for name in contract_ids))
        self.assertEqual(browser_ids.count('test_v060_cli_browser'),1)
        self.assertNotIn('test_v060_cli_browser',contract_ids)

    def test_contract_discovery_needs_no_browser_environment(self):
        """TESTENTRY-01: discovery includes pure palette checks, excludes the moved real export."""
        suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*_contract.py')
        def ids(group):
            for item in group:
                if isinstance(item,unittest.TestSuite):yield from ids(item)
                else:yield item.id()
        selected=list(ids(suite))
        self.assertIn('test_v060_contract.ThemeContract.test_palette_and_legacy_options',selected)
        self.assertFalse(any('test_real_export_exact_path_palette_recovery_and_collision' in name for name in selected))

    def run_fixture(self, body):
        # A real child unittest process reports results; no app, network, or user data.
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'
            tests = source / 'tests'
            tests.mkdir(parents=True)
            content = 'import unittest\nclass Fixture(unittest.TestCase):\n' + textwrap.indent(textwrap.dedent(body), '    ')
            (tests / 'test_pf139_contract.py').write_bytes(content.encode('utf8'))
            evidence = Path(folder) / 'evidence'
            argv = ['run_checks.py', '--source', str(source), '--evidence', str(evidence), '--contracts-only']
            plan=[{'name':'python_contracts','command':[sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-p','test_*_contract.py','-v'],'tests':[]}]
            with patch.object(sys, 'argv', argv), patch.object(CHECKS,'selected_plan',return_value=plan), contextlib.redirect_stdout(io.StringIO()):
                exit_code = CHECKS.main()
            return exit_code, json.loads((evidence / 'RESULTS.json').read_text('utf8'))

    def test_nonzero_exit_with_skip_text_remains_failure(self):
        """HAR-02: a failing child prints SKIP; failure must retain precedence."""
        code, report = self.run_fixture('''
            def test_failure(self):
                print('SKIP optional dependency example')
                self.fail('intentional reproduction')
        ''')
        self.assertNotEqual(code, 0)
        self.assertEqual(report['commands'][0]['status'], 'FAIL')
        self.assertNotEqual(report['commands'][0]['exit_code'], 0)

    def test_mixed_unittest_pass_and_skip_preserves_counts(self):
        """HAR-02: one pass and one skip stay distinct; required coverage is incomplete."""
        code, report = self.run_fixture('''
            def test_pass(self):
                self.assertTrue(True)
            @unittest.skip('optional dependency absent')
            def test_skip(self):
                self.fail('must not execute')
        ''')
        item = report['commands'][0]
        self.assertNotEqual(code, 0)
        self.assertEqual(item['status'], 'SKIP')
        self.assertEqual((item['tests_run'], item['tests_passed'], item['tests_skipped']), (2, 1, 1))
        self.assertIn('optional dependency absent', item['skip_reasons'])
        self.assertFalse(report['full_regression_complete'])

    def test_zero_discovered_required_tests_cannot_pass(self):
        """HAR-02: empty discovery never satisfies required coverage on any Python."""
        code, report = self.run_fixture('pass\n')
        self.assertNotEqual(code, 0)
        # Python versions may exit nonzero for empty discovery; either outcome rejects it.
        self.assertIn(report['commands'][0]['status'], ('FAIL', 'NOT_RUN'))
        self.assertEqual(report['commands'][0]['tests_run'], 0)
        self.assertFalse(report['full_regression_complete'])

    def test_explicit_optional_dependency_skip_records_reason(self):
        """HAR-02: a standalone skip marker describes missing coverage and its cause."""
        result = CHECKS.classify_result(0, 'SKIP browser: optional Playwright unavailable\n')
        self.assertEqual(result['status'], 'SKIP')
        self.assertIn('Playwright unavailable', result['reason'])
        self.assertEqual(result['skip_reasons'], ['SKIP browser: optional Playwright unavailable'])
        self.assertIsNone(result['tests_passed'])

    def test_skip_word_in_successful_test_output_does_not_skip_suite(self):
        """HAR-02: log text is not a skip result when unittest reports completed cases."""
        result = CHECKS.classify_result(0, 'SKIP is a word in this assertion\nRan 2 tests in 0.1s\nOK\n')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual((result['tests_passed'], result['tests_skipped']), (2, 0))

    def test_older_unittest_zero_exit_empty_suite_is_not_run(self):
        """HAR-02: empty discovery is rejected even on Python versions exiting zero."""
        self.assertEqual(CHECKS.classify_result(0, 'Ran 0 tests in 0.0s\nOK\n')['status'], 'NOT_RUN')

    def test_missing_executable_is_not_run(self):
        """HAR-02: a selected check that cannot start is NOT_RUN, with a reason."""
        with patch.object(CHECKS.subprocess, 'run', side_effect=FileNotFoundError('missing tool')):
            _, result = CHECKS.run_command(['missing-tool'], ROOT, {})
        self.assertEqual(result['status'], 'NOT_RUN')
        self.assertIsNone(result['exit_code'])
        self.assertIn('missing tool', result['reason'])

    def test_timeout_is_failure_not_a_success_or_skip(self):
        """HAR-02: timeout is a failure cause, not a fifth ambiguous result status."""
        error = CHECKS.subprocess.TimeoutExpired(['tool'], 1, output=b'partial evidence', stderr=b'error context')
        with patch.object(CHECKS.subprocess, 'run', side_effect=error):
            output, result = CHECKS.run_command(['tool'], ROOT, {}, timeout=1)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('TIMEOUT', result['reason'])
        self.assertIn('partial evidence', output)
        self.assertIn('error context', output)

    def test_expected_failures_are_not_counted_as_completed_acceptance(self):
        result = CHECKS.classify_result(0, 'Ran 3 tests in 0.1s\nOK (expected failures=1)\n')
        self.assertEqual(result['status'], 'SKIP')
        self.assertEqual((result['tests_passed'], result['expected_failures']), (2, 1))

    def test_final_suite_counts_and_partial_passes_survive_child_logs(self):
        result = CHECKS.classify_result(1, 'Ran 1 test in 0.1s\nOK\nNOT_SELECTED source-only history: source.case\nRan 5 tests in 0.2s\nFAILED (failures=1, errors=1, skipped=1)\n')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual((result['tests_run'], result['tests_passed'], result['tests_skipped']), (5, 2, 1))
        self.assertEqual(result['non_required_omissions'][0]['test'], 'source.case')
        self.assertFalse(result['non_required_omissions'][0]['required_for_this_distribution'])

    def test_required_skip_or_not_run_prevents_acceptance(self):
        """HAR-02: required checks missing coverage cannot yield overall PASS."""
        for status in ('FAIL', 'SKIP', 'NOT_RUN'):
            with self.subTest(status=status):
                self.assertNotEqual(CHECKS.overall_status([{'status': 'PASS'}, {'status': status}], []), 'PASS')
        self.assertEqual(CHECKS.overall_status([], []), 'NOT_RUN')
        self.assertEqual(CHECKS.overall_status([{'status': 'PASS'}], ['modified.py']), 'FAIL')
        self.assertEqual(CHECKS.overall_status([{'status': 'PASS'}], []), 'PASS')


if __name__ == '__main__':
    unittest.main(verbosity=2)
