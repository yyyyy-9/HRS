"""DIST-01: installed entry is read-only until start, with state outside resources."""
from pathlib import Path
import contextlib
import importlib.util
import io
import json
import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installed_cli', ROOT / 'app/cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class InstalledCommands(unittest.TestCase):
    def test_packaged_resource_names_can_be_listed_by_a_cp1252_console(self):
        """DIST-03: Windows artifact inspection must not fail printing paths."""
        names = [p.relative_to(ROOT / 'app').as_posix() for p in (ROOT / 'app').rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts]
        self.assertTrue(names)
        '\n'.join(names).encode('cp1252', errors='strict')


    def test_public_licence_inventory_matches_payload_and_authorized_fixtures(self):
        """OSS-PREP-01: a stale size or unreviewed public fixture must fail."""
        policy = json.loads((ROOT / 'PUBLIC_SOURCE_POLICY.json').read_text('utf8'))
        self.assertEqual(policy['public_fixtures'], 'project-owned-synthetic')
        rights = json.loads((ROOT / 'app/RIGHTS.json').read_text('utf8'))
        for item in rights['third_party']:
            for record in [item['notice'], *item['runtime']]:
                raw = (ROOT / 'app' / record['path']).read_bytes()
                self.assertEqual(len(raw), record['bytes'], record['path'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), record['sha256'], record['path'])
        fixtures = json.loads((ROOT / 'tests/fixtures/RIGHTS.json').read_text('utf8'))
        self.assertTrue(fixtures['files'])
        self.assertTrue(all(x['public_distribution'] == 'AUTHORIZED' for x in fixtures['files']))

    def test_packaging_and_root_license_match_canonical_identity(self):
        import tomllib
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text('utf8'))['project']
        rights = json.loads((ROOT / 'app/RIGHTS.json').read_text('utf8'))['own_license']
        self.assertEqual(project['license'], rights['selected'])
        self.assertEqual(project['authors'][0]['name'], rights['holder'])
        self.assertEqual((ROOT / 'LICENSE').read_bytes(), (ROOT / 'app/LICENSE').read_bytes())



    def test_info_and_license_do_not_create_user_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'new user data'
            with patch.dict(os.environ, {'HRS_DATA_DIR': str(data)}):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(cli.main(['info']), 0)
                result = json.loads(output.getvalue())
                self.assertEqual(result['data_dir'], str(data.resolve()))
                self.assertEqual(result['license'], 'GPL-3.0-or-later')
                self.assertEqual(result['author'], 'yyyyy-9')
                self.assertEqual(result['bind'], '127.0.0.1')
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(cli.main(['license']), 0)
                self.assertIn('GNU GENERAL PUBLIC LICENSE', output.getvalue())
                self.assertFalse(data.exists())

    def test_resource_tree_cannot_be_used_for_state(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as failure:
                cli.main(['info', '--data-dir', str(cli.APP / 'data')])
        self.assertEqual(failure.exception.code, 2)
        self.assertFalse((cli.APP / 'data').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
