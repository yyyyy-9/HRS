"""PF13.3: bracketed display TeX, lossless IR, snapshot-based Agent A0 outline."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
from equation_contract import parse_equation
from report_contract import analyze
from agent_readonly import project


class BracketDisplayAndAgent(unittest.TestCase):
    def test_delimiters_and_source_bytes(self):
        for nl in ('\n', '\r\n'):
            with self.subTest(nl=nl):
                raw=nl.join([r'\[',r'K=\left|\frac{d\beta}{d\lambda}\right|',r'\]', ''])
                parsed=parse_equation(raw)
                self.assertEqual(parsed['source'],raw)
                self.assertEqual(parsed['delimiter'],'bracket')
                self.assertFalse(parsed['numbered'])
                self.assertIsNone(parsed['id'])
                self.assertIn('\\frac',parsed['latex'])
                doc='## 源文件 {#sec-demo}'+nl+nl+raw
                ir=analyze(doc)
                self.assertTrue(ir['ok'],ir['diagnostics'])
                equations=[b for b in ir['blocks'] if b['type']=='equation']
                self.assertEqual(len(equations),1)
                self.assertEqual(equations[0]['source'],raw)
                self.assertEqual(equations[0]['start'],len(('## 源文件 {#sec-demo}'+nl+nl).encode('utf-16-le'))//2)
                self.assertEqual(equations[0]['end']-equations[0]['start'],len(raw.encode('utf-16-le'))//2)

    def test_old_delimiters_numbering_and_bad_input(self):
        dollar='$$\nE=mc^2\n$$\n'
        numbered='<!-- hrs:eq id=eq-old -->\n'+dollar
        for src,numbered_flag in [(dollar,False),(numbered,True)]:
            p=parse_equation(src)
            self.assertEqual(p['source'],src)
            self.assertEqual(p['delimiter'],'dollar')
            self.assertEqual(p['numbered'],numbered_flag)
        self.assertIsNone(parse_equation('<!-- hrs:eq id=eq-demo -->\n\\[\nE=mc^2\n\\]\n'))
        self.assertIsNone(parse_equation('\\[\nE=mc^2\n'))
        ir=analyze('\\[\nE=mc^2\n')
        self.assertFalse(ir['ok'])
        self.assertIn('UNCLOSED_DISPLAY_MATH',[d['code'] for d in ir['diagnostics']])
        self.assertEqual(analyze('```text\n\\[\nnot formula\n\\]\n```')['stats'].get('equation',0),0)
        self.assertEqual(analyze('\\[\n\\alpha=2\\] still text\n')['stats'].get('equation',0),0)

    def test_agent_snapshot_scoped_block_lookup(self):
        raw='## 测试 {#sec-demo}\n\n\\[\nK=1.5\\,\\mathrm{pm}\n\\]\n\n| A | B |\n|---|---|\n| 2 | 3 |\n'
        original=raw.encode('utf-8')
        ir=analyze(raw)
        catalog=project(ir,'objects')['objects']
        self.assertEqual(len(catalog),1)
        self.assertEqual(catalog[0]['id'],'sec-demo')
        outline=project(ir,'outline')['blocks']
        eq=next(x for x in outline if x['type']=='equation')
        self.assertIsNone(eq['id'])
        self.assertEqual(eq['delimiter'],'bracket')
        result=project(ir,'get-block',block_index=eq['index'],expected_sha256=ir['source_snapshot']['text_utf8_sha256'])
        self.assertTrue(result['found'])
        self.assertEqual(result['block']['source'],'\\[\nK=1.5\\,\\mathrm{pm}\n\\]\n')
        self.assertFalse(project(ir,'get-block',block_index=100000,expected_sha256=ir['source_snapshot']['text_utf8_sha256'])['found'])
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'report.md';source.write_bytes(original)
            cmd=[sys.executable,str(ROOT/'app/agent_readonly.py'),'outline',str(source)]
            answer=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(answer.returncode,0,answer.stderr)
            data=json.loads(answer.stdout)
            self.assertEqual(data['snapshot']['file_sha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(data['blocks'][eq['index']]['delimiter'],'bracket')
            cmd=[sys.executable,str(ROOT/'app/agent_readonly.py'),'get-block',str(source),'--index',str(eq['index']),'--expect-sha256',ir['source_snapshot']['text_utf8_sha256']]
            answer=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(json.loads(answer.stdout)['block']['source'],result['block']['source'])
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual(list(Path(folder).iterdir()),[source])

if __name__=='__main__':unittest.main(verbosity=2)
