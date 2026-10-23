"""PF13.7 shared ID acceptance cases and unchanged valid-document semantics."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from report_contract import ContractError, analyze, validate_figure, validate_table
from agent_readonly import project

CASES = json.loads((ROOT / 'tests/fixtures/object_id_cases.json').read_text('utf8'))['cases']


def model(kind, ident):
    base = {'schema': 'report-' + kind + '-v1', 'id': ident, 'caption': 'test'}
    if kind == 'table':
        return {**base, 'rows': [[{'text': 'x', 'rowspan': 1, 'colspan': 1}]]}
    return {**base, 'kind': 'mermaid', 'source': 'flowchart LR\nA-->B'}


def fenced(kind, obj, newline='\n'):
    return newline.join(['```report-' + kind, json.dumps(obj, ensure_ascii=False), '```', ''])


class PF137(unittest.TestCase):
    def check_kind(self, kind, validator):
        for case in CASES:
            with self.subTest(kind=kind, case=case['name']):
                obj = model(kind, case[kind + 'Id'])
                before = json.dumps(obj, ensure_ascii=False)
                if case['valid']:
                    self.assertEqual(validator(obj)['id'], case[kind + 'Id'])
                else:
                    with self.assertRaises(ContractError):
                        validator(obj)
                self.assertEqual(json.dumps(obj, ensure_ascii=False), before)

    def test_table_ids_share_explicit_fixture(self):
        self.check_kind('table', validate_table)

    def test_figure_ids_share_explicit_fixture(self):
        self.check_kind('figure', validate_figure)

    def test_rejected_id_cannot_be_numbered_or_agent_compilable(self):
        for case in CASES:
            if case['valid']:
                continue
            for kind in ('table', 'figure'):
                with self.subTest(kind=kind, case=case['name']):
                    ir = analyze(fenced(kind, model(kind, case[kind + 'Id'])))
                    self.assertFalse(ir['ok'])
                    self.assertIn('INVALID_OBJECT', [d['code'] for d in ir['diagnostics']])
                    self.assertEqual(ir['objects']['entries'], [])
                    self.assertFalse(project(ir)['safeToCompile'])

    def test_valid_boundaries_keep_source_positions_numbers_and_references(self):
        table_id, figure_id = 'tbl-' + 'a' * 60, 'fig-' + 'a' * 60
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)):
                header = '\ufeff## 中文与 emoji 😀 {#sec-example}' + newline + newline
                native = newline.join(['| A |', '|---|', '| 1 |', ': 原生表 {#tbl-native}', ''])
                enhanced = fenced('table', model('table', table_id), newline)
                figure = fenced('figure', model('figure', figure_id), newline)
                refs = '引用 @tbl:' + table_id + '、@fig:' + figure_id + ' 和 @tbl:tbl-native。' + newline
                text = header + native + newline + enhanced + newline + figure + newline + refs
                ir = analyze(text)
                self.assertTrue(ir['ok'], ir['diagnostics'])
                entries = {entry['id']: entry for entry in ir['objects']['entries']}
                self.assertEqual(entries[table_id]['number'], 2)
                self.assertEqual(entries[figure_id]['number'], 1)
                self.assertTrue(entries['tbl-native']['numbered'])
                self.assertEqual([r['target'] for r in ir['references']], [table_id, figure_id, 'tbl-native'])
                for entry in (entries[table_id], entries[figure_id]):
                    self.assertEqual(len(entry['referencedBy']), 1)
                self.assertEqual(ir['source_snapshot']['text_utf8_sha256'], hashlib.sha256(text.encode()).hexdigest())
                self.assertTrue(ir['source_snapshot']['bom_preserved'])
                self.assertEqual(ir['source_snapshot']['utf16_length'], len(text.encode('utf-16-le')) // 2)
                for block in ir['blocks']:
                    actual = text.encode('utf-16-le')[block['start'] * 2:block['end'] * 2].decode('utf-16-le')
                    self.assertEqual(actual, block['source'])

    def test_cli_rejects_empty_id_suffix_and_never_rewrites_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'report.md'
            for kind, ident in [('table', 'tbl-'), ('figure', 'fig-')]:
                with self.subTest(kind=kind):
                    original = ('\ufeff# 输入\r\n\r\n' + fenced(kind, model(kind, ident), '\r\n')).encode('utf8')
                    source.write_bytes(original)
                    result = subprocess.run([sys.executable, '-X', 'utf8', '-B',
                        str(ROOT / 'app/agent_readonly.py'), 'summary', str(source)],
                        capture_output=True, text=True, encoding='utf8',
                        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
                    self.assertEqual(result.returncode, 1, result.stderr)
                    answer = json.loads(result.stdout)
                    self.assertFalse(answer['safeToCompile'])
                    self.assertIn('INVALID_OBJECT', [d['code'] for d in answer['errors']])
                    self.assertEqual(source.read_bytes(), original)
                    self.assertEqual(list(Path(folder).iterdir()), [source])


if __name__ == '__main__':
    unittest.main(verbosity=2)
