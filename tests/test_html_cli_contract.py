"""API-02: the independent HRS distribution owns the HTML command adapter."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'app'


class HTMLCLI(unittest.TestCase):
    def test_independent_cli_describes_export_and_recover(self):
        """A source-only HRS package exposes both commands without the bridge project."""
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'html_cli.py'), '--help'],
                                capture_output=True, text=True, encoding='utf8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('export', result.stdout)
        self.assertIn('recover', result.stdout)

    def test_cli_input_error_is_json_and_does_not_start_a_browser(self):
        """Bad paths fail before browser setup and produce a usable error receipt."""
        import json
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'html_cli.py'),
                                 'export', str(ROOT / 'not-a-project'), '--output',
                                 str(ROOT / 'must-not-exist.html')],
                                capture_output=True, text=True, encoding='utf8')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stdout)['ok'])
        self.assertFalse((ROOT / 'must-not-exist.html').exists())


if __name__ == '__main__':
    unittest.main()
