"""MATH-UX-02/CAPTURE-01: real fragment import and persistent declarative settings."""
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from object_clipboard import paste_bundle,FORMAT
from text_snippets import read,write
from studio import check_image

class EquationOutlineContract(unittest.TestCase):
 def test_anonymous_bracket_and_dollar_paste_gain_unique_ids_without_changing_tex(self):
  text='\\[\n\\frac{a}{b}\\tag{2}\n\\]\n\n$$\nx^2\n$$\n'
  bundle={'format':FORMAT,'markdown':text,'assets':{},'operation':'copy'}
  first=paste_bundle(bundle,'',[],'draft:test',check_image);second=paste_bundle(bundle,first['markdown'],[],'draft:test',check_image)
  import re
  ids=re.findall(r'hrs:eq id=(eq-[\w-]+)',first['markdown']+second['markdown']);self.assertEqual(len(set(ids)),4)
  self.assertIn('\\frac{a}{b}\\tag{2}',first['markdown']);self.assertIn('\\[',first['markdown'])
 def test_equation_fragment_internal_references_remap_external_stays_literal(self):
  raw='<!-- hrs:eq id=eq-one -->\n$$\nx=1\n$$\n\n见 @eq:eq-one 和 @eq:eq-external。\n'
  reply=paste_bundle({'format':FORMAT,'markdown':raw,'assets':{},'operation':'copy'},'',[],'target',check_image)
  self.assertIn('@eq:'+reply['id_map']['eq-one'],reply['markdown']);self.assertIn('@eq:eq-external',reply['markdown'])
 def test_cut_preserves_identity_until_repeated_paste_collides(self):
  raw='<!-- hrs:eq id=eq-one -->\n$$\nx=1\n$$\n'
  bundle={'format':FORMAT,'markdown':raw,'assets':{},'operation':'cut','source_key':'target'}
  self.assertEqual(paste_bundle(bundle,'',[],'target',check_image)['markdown'],raw)
  self.assertNotEqual(paste_bundle(bundle,raw,[],'target',check_image)['markdown'],raw)
 def test_snippet_settings_reopen_conflict_and_validation(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);before=read(root);items=[{'id':'sample','title':'记录','text':'{{field:样品}} {{date}} {{cursor}}'}]
   saved=write(root,items,before['revision']);self.assertEqual(read(root),saved)
   with self.assertRaisesRegex(ValueError,'其他窗口'):write(root,[],before['revision'])
   with self.assertRaises(ValueError):write(root,[{**items[0],'execute':'code'}],saved['revision'])
   self.assertEqual(read(root),saved)

if __name__=='__main__':unittest.main()
