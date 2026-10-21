"""TPL-EXE-01: identical backend in a selected Python, plus useful read failures."""
from pathlib import Path
from zipfile import BadZipFile, ZipFile
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from wps_pipeline.template_runtime import TemplateBackend, TOOL_VERSION
from test_template_slots import BASE, marked_template


class TemplateRuntime(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='模板运行 比较 ')
        self.folder = Path(self.tmp.name).resolve()
        self.local = TemplateBackend()
        self.python = TemplateBackend(sys.executable)

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_python_runs_same_inspection_even_if_gui_process_reading_fails(self):
        original = self.local.run('inspect', document=str(BASE))
        with patch('wps_pipeline.template_prepare.inspect_document', side_effect=BadZipFile('parent-process-only')):
            parent = self.local.run('inspect', document=str(BASE))
            child = self.python.run('inspect', document=str(BASE))
        self.assertEqual(parent['status'], 'FAIL')
        self.assertEqual(child['status'], 'INSPECTED', child)
        self.assertEqual(original['document'], child['document'])
        self.assertEqual(original['styles'], child['styles'])
        self.assertEqual(Path(child['runtime']['executable']).resolve(), Path(sys.executable).resolve())
        self.assertEqual(child['runtime']['tool_version'], TOOL_VERSION)
        self.assertNotEqual(original['runtime']['pid'], child['runtime']['pid'])

    def test_invalid_cover_and_donor_report_the_correct_input_and_read_facts(self):
        bad = self.folder / '无效容器.docx'
        raw = b'this is not an OOXML container'
        bad.write_bytes(raw)
        for role, params, phase in (
            ('source', {'source': str(bad)}, 'read_cover_template'),
            ('style_source', {'source': str(BASE), 'style_source': str(bad)}, 'read_style_source'),
        ):
            with self.subTest(role=role):
                result = self.python.run('inspect-pair', **params)
                self.assertEqual(result['status'], 'FAIL')
                details = result['error_details']
                self.assertEqual(details['phase'], phase)
                self.assertEqual(details['failed_role'], role)
                self.assertEqual(details['failed_path'], str(bad.resolve()))
                facts = next(item for item in details['inputs'] if item['role'] == role)
                self.assertFalse(facts['zip_valid'])
                self.assertEqual(facts['bytes_read'], len(raw))
                self.assertEqual(facts['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertNotIn(raw.decode(), json.dumps(result))
        self.assertEqual(bad.read_bytes(), raw)

    def test_read_only_diagnostics_compare_both_processes_without_document_body(self):
        before = BASE.read_bytes()
        result = self.python.diagnose(source=str(BASE))
        self.assertEqual(result['status'], 'DIAGNOSTICS')
        self.assertEqual(result['selected_python']['backend_import']['status'], 'READY')
        self.assertTrue(all(row['same_sha256'] and row['same_read_bytes'] for row in result['comparison']))
        self.assertEqual(len(result['comparison']), 2)
        for runtime in ('embedded', 'selected_python'):
            self.assertTrue(all(row['zip_valid'] and row['has_document'] for row in result[runtime]['inputs']))
        self.assertEqual(BASE.read_bytes(), before)
        self.assertNotIn('blocks', json.dumps(result))

    def test_prepare_in_real_python_keeps_original_protection_and_native_template_bytes(self):
        shell = self.folder / '封面及目录.docx'
        marked_template(shell)
        original = shell.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        donor_digest = hashlib.sha256(BASE.read_bytes()).hexdigest()
        params = dict(source=str(shell), body_start=1, expected_sha256=digest,
                      style_source=str(BASE), expected_style_sha256=donor_digest)
        local_out, child_out = self.folder / '本地.docx', self.folder / '指定 Python.docx'
        local = self.local.run('prepare', output=str(local_out), **params)
        child = self.python.run('prepare', output=str(child_out), **params)
        self.assertEqual(local['status'], 'PREPARED', local)
        self.assertEqual(child['status'], 'PREPARED', child)
        with ZipFile(local_out) as a, ZipFile(child_out) as b:
            self.assertEqual(a.namelist(), b.namelist())
            for name in a.namelist():
                self.assertEqual(a.read(name), b.read(name), name)
        output_bytes = child_out.read_bytes()
        duplicate = self.python.run('prepare', output=str(child_out), **params)
        self.assertEqual(duplicate['status'], 'FAIL')
        self.assertEqual(child_out.read_bytes(), output_bytes)
        for field in ('expected_sha256', 'expected_style_sha256'):
            target = self.folder / (field + '.docx')
            stale = self.python.run('prepare', output=str(target), **{**params, field: '0' * 64})
            self.assertEqual(stale['status'], 'FAIL')
            self.assertIn('changed', stale['error'])
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.template.json').exists())
        self.assertEqual(shell.read_bytes(), original)

    def test_missing_python_and_missing_backend_have_actionable_failures(self):
        missing = TemplateBackend(self.folder / 'missing/python.exe').run('inspect', document=str(BASE))
        self.assertEqual(missing['status'], 'FAIL')
        self.assertEqual(missing['error_details']['phase'], 'launch_python')
        import wps_pipeline.template_runtime as runtime
        with patch.dict(sys.modules, {'wps_pipeline.template_prepare': None}):
            failure = self.local.run('inspect', document=str(BASE))
        self.assertEqual(failure['status'], 'FAIL')
        self.assertEqual(failure['error_details']['phase'], 'load_backend')
        self.assertIn('template_tool.py', failure['error'])


if __name__ == '__main__':
    unittest.main()
