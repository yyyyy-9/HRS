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

    def test_public_word_material_policy_requires_exact_hashes_and_protects_code(self):
        """OSS-PREP-01: a cover/licence replacement must not permit code edits."""
        import sys
        sys.path.insert(0, str(ROOT / 'tools'))
        from verify_release import approved_word_materials
        name='word_support/wps/templates/cover_template_v0311.docx'
        before, after={name:b'old cover'}, {name:b'synthetic cover'}
        policy={name:{'baseline_sha256':hashlib.sha256(before[name]).hexdigest(),
                      'sha256':hashlib.sha256(after[name]).hexdigest()}}
        self.assertEqual(approved_word_materials(before,after,policy),[name])
        with self.assertRaisesRegex(ValueError,'fingerprint'):
            approved_word_materials(before,{name:b'changed after review'},policy)
        with self.assertRaisesRegex(ValueError,'implementation'):
            approved_word_materials({}, {}, {'word_support/bridge/hrs_bridge/docx_export.py':{}})

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

    def test_conda_recipe_uses_the_same_distribution_identity_and_entry_point(self):
        """DIST-02: local and staged recipes differ only in their source location."""
        import sys
        import tomllib
        sys.path.insert(0, str(ROOT / 'tools'))
        from build_conda_recipe import render
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text('utf8'))['project']
        self.assertEqual(project['name'], 'hrstudio')
        self.assertEqual(project['scripts'], {'hrs': 'html_report_studio.cli:main'})
        local = render(ROOT)
        self.assertEqual((ROOT / 'packaging/conda/recipe.yaml').read_text('utf8'), local)
        self.assertIn('python_version:\n        - ${{ python_min }}.*\n        - "*"', local)
        remote = render(ROOT, source_url='https://example.org/source.tar.gz', source_sha256='a' * 64)
        self.assertEqual(local.replace('  path: ../..',
            '  url: "https://example.org/source.tar.gz"\n  sha256: ' + 'a' * 64), remote)
        self.assertNotIn('source_tag', local)
        self.assertFalse((ROOT / 'packaging/conda/meta.yaml').exists())

    def test_conda_release_source_requires_a_secure_url_and_complete_digest(self):
        """DIST-02: never emit a submission recipe with an unchecked source."""
        import sys
        sys.path.insert(0, str(ROOT / 'tools'))
        from build_conda_recipe import render
        for url, digest in [('https://example.org/a.tar.gz', None), (None, 'a' * 64),
                            ('http://example.org/a.tar.gz', 'a' * 64),
                            ('https://example.org/a.tar.gz', 'a' * 63)]:
            with self.subTest(url=url, digest=digest), self.assertRaises(ValueError):
                render(ROOT, source_url=url, source_sha256=digest)

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
