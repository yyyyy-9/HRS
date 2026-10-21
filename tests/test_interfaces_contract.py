"""NORMS-01: public CLI documentation must describe actual parsers and refusal."""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InterfaceDocumentation(unittest.TestCase):
    def invoke(self, module, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', '-B', str(ROOT / 'app' / module), *args],
                              capture_output=True, text=True, encoding='utf8', timeout=12)

    def test_machine_handoff_and_cli_help_have_the_same_commands(self):
        handoff = json.loads((ROOT / 'app/docs/WORD_IR_HANDOFF.json').read_text('utf8'))
        for module, documented in [('agent_readonly.py', handoff['agent_readonly']['actions']),
                                   ('block_cli.py', handoff['controlled_block_commands']['commands']),
                                   ('html_cli.py', handoff['html_cli']['commands'])]:
            with self.subTest(module=module):
                result = self.invoke(module, '--help')
                self.assertEqual(result.returncode, 0, result.stderr)
                choices = re.findall(r'\{([a-z][a-z,-]+)\}', result.stdout)[0].split(',')
                self.assertEqual(set(choices), set(documented))
        plan = self.invoke('block_cli.py', 'plan', '--help')
        for flag in ('--expect-sha256', '--text-file', '--operation', '--output', '--id', '--index'):
            self.assertIn(flag, plan.stdout)
        self.assertIn('--expect-plan-sha256', self.invoke('block_cli.py', 'apply', '--help').stdout)

    def test_installed_facade_capabilities_and_help_match_machine_contract(self):
        handoff=json.loads((ROOT/'app/docs/WORD_IR_HANDOFF.json').read_text('utf8'))
        result=self.invoke('cli.py','capabilities')
        self.assertEqual(result.returncode,0,result.stderr)
        capabilities=json.loads(result.stdout)
        self.assertEqual(set(capabilities['commands']),set(handoff['installed_cli']['commands'])-{'capabilities'})
        for command in capabilities['commands']:
            args=[command,'--help']
            result=self.invoke('cli.py',*args)
            self.assertEqual(result.returncode,0,(command,result.stderr))
        self.assertIn('check',handoff['programmatic_browser']['operations'])
        self.assertFalse(capabilities['model_api_client'])

    def test_invalid_cli_requests_cannot_be_reported_as_success_or_write_a_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'report.md'
            raw = '# 原稿😀\r\n\r\n正文。\r\n'.encode('utf8')
            path.write_bytes(raw)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            for module, args in [('agent_readonly.py', ['get-block', str(path), '--index', '0', '--expect-sha256', '0'*64]),
                                 ('block_cli.py', ['apply', str(root/'missing.json'), '--expect-plan-sha256', '0'*64])]:
                result = self.invoke(module, *args)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                payload = json.loads(result.stdout)
                self.assertFalse(payload['ok'])
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
