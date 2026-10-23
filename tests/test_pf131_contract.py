"""PF13.1 cross-language fixture, Agent A0 and IR semantics regressions."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'app'))
import agent_readonly
from pipe_table_contract import split_cells, parse_at
from report_contract import analyze, validate_table, validate_figure

FIXTURES = json.loads((BASE / 'tests/fixtures/gfm_tables.json').read_text('utf-8'))
CELL = {'text': 'value', 'rowspan': 1, 'colspan': 1}


class PF131Contract(unittest.TestCase):
    def test_gfm_split_fixtures(self):
        for fixture in FIXTURES['splits']:
            with self.subTest(source=fixture['source']):
                self.assertEqual(split_cells(fixture['source']), fixture['cells'])

    def test_gfm_table_fixtures(self):
        for fixture in FIXTURES['tables']:
            with self.subTest(source=fixture['source'][:25]):
                table = parse_at(fixture['source'].splitlines(keepends=True), 0)
                self.assertIsNotNone(table)
                self.assertEqual(table['id'], fixture['id'])
                for field in ('caption', 'rows', 'align'):
                    self.assertEqual(table['data'][field], fixture[field])
                self.assertEqual(table['source'], fixture['source'])

    def test_enhanced_and_gfm_numbered_semantics(self):
        enhanced = {'schema': 'report-table-v1', 'id': 'tbl-enhanced', 'caption': '增强表',
                    'rows': [[CELL]]}
        md = '| 姓名 |\n| --- |\n| 李 |\n\n: 原始表 {#tbl-pipe}\n\n' + (
            '```report-table\n' + json.dumps(enhanced, ensure_ascii=False) + '\n```\n\n')
        md += '引用 @tbl:tbl-pipe 和 @tbl:tbl-enhanced。'
        ir = analyze(md)
        self.assertTrue(ir['ok'], ir['diagnostics'])
        tables = [b for b in ir['blocks'] if b['type'] == 'table']
        self.assertEqual([(b['numbered'], b['sourceKind']) for b in tables],
                         [(True, 'gfm-pipe'), (True, 'enhanced')])
        self.assertEqual([(x['id'], x['numbered'], x['sourceKind'], x['sequence'])
                          for x in ir['objects']['entries']],
                         [('tbl-pipe', True, 'gfm-pipe', 'table'),
                          ('tbl-enhanced', True, 'enhanced', 'table')])
        self.assertEqual(len(ir['objects']['entries'][0]['referencedBy']), 1)
        self.assertEqual(len(ir['objects']['entries'][1]['referencedBy']), 1)
        self.assertEqual(ir['objects']['ids'], {'tbl-pipe': 1, 'tbl-enhanced': 7})

    def test_unknown_fields_are_visible_and_not_compilable(self):
        obj = {'schema': 'report-table-v1', 'id': 'tbl-ext', 'caption': '',
               'rows': [[CELL]], 'futureLayout': {'example': [1, 2]}}
        data = validate_table(obj)
        self.assertEqual(data['extensions']['futureLayout'], {'example': [1, 2]})
        ir = analyze('```report-table\n' + json.dumps(obj) + '\n```')
        self.assertTrue(ir['ok'])  # old docs can still open/edit
        self.assertIn('UNSUPPORTED_OBJECT_FIELDS', [d['code'] for d in ir['diagnostics']])
        self.assertFalse(agent_readonly.project(ir)['safeToCompile'])

    def test_unknown_figure_is_visible(self):
        obj = {'schema':'report-figure-v1','id':'fig-note','caption':'','kind':'mermaid',
               'source':'flowchart LR\nA-->B', 'future': True}
        self.assertEqual(validate_figure(obj)['extensions'], {'future':True})

    def test_agent_cli_readonly_and_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'report.md'
            text = '## 样本 {#sec-demo}\n\n引用 @sec:sec-demo。\n'
            # A byte-exact LF fixture must not become CRLF on Windows.
            source.write_bytes(text.encode('utf-8'))
            before = source.read_bytes()
            for action in ('summary', 'objects', 'references', 'diagnostics'):
                result = subprocess.run([sys.executable, str(BASE/'app/agent_readonly.py'),
                                         action, str(root)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                obj = json.loads(result.stdout)
                self.assertTrue(obj['sourceContractValid'])
                self.assertFalse(obj['safeToCompile'])  # V1-MAINTENANCE-01: A0 never claims complete renderer/output checks.
                self.assertFalse(obj['preflight']['complete'])
                self.assertEqual(obj['schema'], 'hrs-agent-read-v1')
                self.assertEqual(obj['snapshot']['file_sha256'],hashlib.sha256(before).hexdigest())
            result = subprocess.run([sys.executable, str(BASE/'app/agent_readonly.py'),
                                     'get', str(source), '--id', 'sec-demo'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            obj=json.loads(result.stdout)
            self.assertTrue(obj['found'])
            self.assertEqual(obj['object']['kind'], 'section')
            self.assertEqual(obj['block']['source'], '## 样本 {#sec-demo}\n')
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(list(root.iterdir()), [source])  # no hidden output created

    def test_agent_cli_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'report.md'
            file.write_text('无效引用 @tbl:tbl-absent\n', 'utf-8')
            result = subprocess.run([sys.executable,str(BASE/'app/agent_readonly.py'),
                                     'objects',str(file)],capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            data=json.loads(result.stdout)
            self.assertFalse(data['safeToCompile'])
            self.assertEqual(data['errors'][0]['code'],'MISSING_REFERENCE')

if __name__ == '__main__':unittest.main(verbosity=2)
