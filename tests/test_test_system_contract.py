"""TEST-SYSTEM-01: registration, non-repeated selection and failed-fixture cleanup."""
from pathlib import Path
import hashlib
import json
import ast
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_catalog import ALIASES, command_plan, registered_tests, select_tests


class TestSelection(unittest.TestCase):
    def test_license_draft_and_third_party_assets_have_separate_complete_inventories(self):
        app = ROOT / 'app'
        rights = json.loads((app / 'RIGHTS.json').read_text('utf8'))
        own = rights['own_license']
        if own['status'] == 'DRAFT_HOLDER_PENDING':
            draft = (app / own['draft_file']).read_text('utf8')
            self.assertIn('[COPYRIGHT HOLDER - TO BE CONFIRMED]', draft)
            self.assertIn('NOT AN EFFECTIVE LICENSE GRANT', draft)
            self.assertIsNone(own['holder'])
        else:
            self.assertEqual(own['status'], 'EFFECTIVE')
            self.assertEqual(own['selected'], 'GPL-3.0-or-later')
            self.assertIn('Version 3, 29 June 2007', (app / own['license_file']).read_text('utf8'))
            notice = (app / own['notice_file']).read_text('utf8')
            self.assertIn(own['holder'], notice)
            self.assertIn('any later version', notice)
            self.assertFalse((app / 'MIT_LICENSE_DRAFT.txt').exists())
        inventory = [item for component in rights['third_party'] for item in [component['notice'], *component['runtime']]]
        for item in inventory:
            raw = (app / item['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'], item['path'])
        self.assertEqual({p.relative_to(app).as_posix() for p in (app/'web/vendor').rglob('*.js')},
                         {item['path'] for item in inventory if item['path'].endswith('.js')})
        base = ROOT / 'tests/fixtures'
        fixtures = json.loads((base/'RIGHTS.json').read_text('utf8'))['files']
        self.assertEqual({item['path'] for item in fixtures}, {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file() and p.name != 'RIGHTS.json'})
        for item in fixtures:
            self.assertEqual(hashlib.sha256((base/item['path']).read_bytes()).hexdigest(), item['sha256'], item['path'])
            self.assertIn(item['public_distribution'], ('UNCONFIRMED', 'AUTHORIZED', 'EXCLUDED'))

    def test_every_test_is_registered_once_and_unknown_group_is_an_error(self):
        actual = {path.relative_to(ROOT).as_posix() for path in (ROOT / 'tests').glob('test_*') if path.suffix in ('.py', '.js')}
        registered = registered_tests()
        self.assertEqual({item['path'] for item in registered.values()}, actual)
        # Explicit native integrations are registered but intentionally absent
        # from default full; together the two sets must cover every file once.
        full={item['path'] for item in select_tests(ROOT,['full'])}
        explicit={item['path'] for item in registered.values() if item['explicit_selection_required']}
        self.assertFalse(full & explicit)
        self.assertEqual(full | explicit,actual)
        for item in registered.values():
            for selectors in item['feature_selectors'].values():
                for selector in selectors or []:
                    class_name,separator,method=selector.partition('.')
                    tree=ast.parse((ROOT/item['path']).read_text('utf8'))
                    matching=[node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==class_name]
                    self.assertEqual(len(matching),1,selector)
                    methods=[node.name for node in matching[0].body if isinstance(node,ast.FunctionDef)]
                    if separator:self.assertIn(method,methods)
                    else:self.assertTrue(any(name.startswith('test_') for name in methods),selector)
        with self.assertRaisesRegex(ValueError, 'Unknown test groups'):
            select_tests(ROOT, ['typo'])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'Selected tests missing'):
                select_tests(directory, ['contracts'])

    def test_overlapping_features_select_each_scenario_and_gate_once(self):
        plan = command_plan(ROOT, 'node', 'python', ['core', 'theme', 'headings', 'core'])
        ids = [test['id'] for entry in plan for test in entry['tests']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('test_core_consistency_browser', ids)
        self.assertEqual(sum(entry['name'] == 'settings_generation' for entry in plan), 1)
        contracts = command_plan(ROOT, 'node', 'python', ['contracts'])
        self.assertFalse(any(test['kind'] == 'browser' for entry in contracts for test in entry['tests']))
        self.assertEqual(sum(entry['name'] == 'python_contracts' for entry in contracts), 1)
        for alias in ALIASES:
            self.assertTrue(select_tests(ROOT, [alias]), alias)

    def test_failed_page_setup_closes_server_and_never_reuses_a_dirty_case(self):
        from browser_support import LiveDocument, ManualService
        server = Mock(server_port=12345)
        browser = Mock()
        browser.new_context.side_effect = RuntimeError('intentional browser startup fault')
        with tempfile.TemporaryDirectory() as directory, patch('browser_support.StudioServer', return_value=server):
            with self.assertRaisesRegex(RuntimeError, 'intentional browser startup fault'):
                LiveDocument(browser, Path(directory))
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        case = ManualService()
        case._testMethodName = 'test_04_unrelated_case'
        self.assertEqual(case.project_setup(), ('# Initial\n', False), 'case numbers must not secretly choose a task fixture')


if __name__ == '__main__':
    unittest.main(verbosity=2)
