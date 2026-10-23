"""TESTENTRY-01: retained real HTML CLI roundtrip belongs to browser checks.

The original assertions are unchanged. Explicit selection requires a local
browser and loopback access; a missing environment is an error, never a pass.
"""
from pathlib import Path
import hashlib,json,os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from html_cli import export_html,recover_html,HTMLCommandError

class ThemeCLIBrowser(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  browser=os.environ.get('CHROMIUM_PATH')
  if not browser or not Path(browser).is_file():
   raise RuntimeError('此浏览器专项需要有效 CHROMIUM_PATH；可用 tools/run_checks.py --browsers-only --browser 本机Chrome路径 --evidence 新目录')

 def test_real_export_exact_path_palette_recovery_and_collision(self):
  with tempfile.TemporaryDirectory(prefix='hrs-v060-cli-') as d:
   folder=Path(d);project=folder/'source';(project/'assets').mkdir(parents=True)
   raw='# 工程😀\r\n\r\n## 正文\r\n\r\n- [ ] 原任务\r\n\r\n$E=mc^2$\r\n'.encode()
   (project/'report.md').write_bytes(raw)
   meta={'render_profile':'free','render_options':{'show_object_numbers':False},'color_theme':'warm'}
   (project/'meta.json').write_bytes(json.dumps(meta).encode());original_meta=(project/'meta.json').read_bytes()
   sentinel=folder/'笔记-explicit.html';sentinel.write_bytes(b'KEEP EXISTING')
   output=folder/'explicit.html';result=export_html(project,output,browser=os.environ['CHROMIUM_PATH'],theme='blue')
   self.assertEqual(result['output'],str(output));self.assertEqual(result['color_theme'],'blue')
   self.assertEqual(sentinel.read_bytes(),b'KEEP EXISTING');self.assertTrue(output.exists())
   self.assertEqual((project/'report.md').read_bytes(),raw);self.assertEqual((project/'meta.json').read_bytes(),original_meta)
   saved=output.read_bytes()
   with self.assertRaises(HTMLCommandError):export_html(project,output,browser=os.environ['CHROMIUM_PATH'])
   self.assertEqual(output.read_bytes(),saved)
   recovered=folder/'restored';receipt=recover_html(output,recovered,browser=os.environ['CHROMIUM_PATH'])
   self.assertEqual(receipt['markdown_sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual((recovered/'report.md').read_bytes(),raw)
   settings=json.loads((recovered/'meta.json').read_text('utf8'))
   self.assertEqual(settings,{'render_profile':'free','render_options':{'show_object_numbers':False,'show_heading_numbers':False,'show_equation_numbers':False,'preserve_blank_lines':False},'color_theme':'blue'})

if __name__=='__main__':unittest.main()
