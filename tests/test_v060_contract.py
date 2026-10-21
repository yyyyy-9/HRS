"""THEME-03/06: exact CLI paths, archive configuration, palette and meta guard."""
from pathlib import Path
import struct,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from color_theme import normalize,read
from render_profile import read_options
from studio import audit_export

class ThemeContract(unittest.TestCase):
 def test_palette_and_legacy_options(self):
  self.assertEqual(normalize(),'blue');self.assertEqual(normalize('default'),'blue')
  for bad in ('missing','../../outside',False,{},'Blue'):
   with self.assertRaises(ValueError):normalize(bad)
  with tempfile.TemporaryDirectory() as d:
   self.assertEqual(read(d),'blue');self.assertEqual(read_options(d),{'show_object_numbers':True,'show_heading_numbers':False,'preserve_blank_lines':False})

 def test_only_profile_meta_is_allowed(self):
  def html(meta):return '<!doctype html><html><head>'+meta+'</head><body>Text<script id="report-source" type="application/json">{"format":"html-report-studio-v1","markdown":"# Report","assets":{}}</script></body></html>'
  for profile in ('free','engineering'):audit_export(html('<meta name="hrs-render-profile" content="'+profile+'">'))
  for meta in ('<meta name="hrs-render-profile" content="unknown">',
   '<meta name="hrs-render-profile" content="free" http-equiv="refresh">',
   '<meta name="hrs-render-profile" content="free" onclick="alert(1)">',
   '<meta http-equiv="refresh" content="0;url=https://example.com">'):
   with self.assertRaises(ValueError):audit_export(html(meta))

 def test_icon_formats_from_same_svg(self):
  png=(ROOT/'app/web/app-icon.png').read_bytes();ico=(ROOT/'app/web/app-icon.ico').read_bytes()
  self.assertEqual(png[:8],b'\x89PNG\r\n\x1a\n');self.assertEqual(struct.unpack('>II',png[16:24]),(512,512))
  self.assertEqual(struct.unpack('<HHH',ico[:6]),(0,1,7));sizes=[]
  for i in range(7):
   w,h,_,_,planes,bits,length,offset=struct.unpack('<BBBBHHII',ico[6+i*16:22+i*16]);sizes.append(w or 256)
   self.assertEqual((planes,bits),(1,32));self.assertEqual(ico[offset:offset+8],png[:8]);self.assertLessEqual(offset+length,len(ico))
  self.assertEqual(sizes,[16,20,32,48,64,128,256])
  self.assertIn('HRS outline tree mark',(ROOT/'app/web/app-icon.svg').read_text('utf8'))

if __name__=='__main__':unittest.main()
