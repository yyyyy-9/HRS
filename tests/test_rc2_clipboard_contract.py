"""Clipboard identity/resource invariants; the existing IR defines the objects."""
from pathlib import Path
import sys,tempfile,unittest,json,base64
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from object_clipboard import copy_bundle,paste_bundle,sha,FORMAT
from report_contract import analyze

def figure(oid='fig-one',src='assets/1234567890abcdef.png',**extra):
 return '```report-figure\n'+json.dumps({'schema':'report-figure-v1','id':oid,'caption':'测试','kind':'image','src':src,**extra},ensure_ascii=False)+'\n```\n'
def check(ext,data):
 if not data:raise ValueError('empty')

class ClipboardContract(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.source=Path(self.tmp.name)/'source';self.target=Path(self.tmp.name)/'target'
  self.source.mkdir();self.target.mkdir();(self.source/'1234567890abcdef.png').write_bytes(b'PNG-source')
 def paste(self,bundle,target='# 目标\n',key='target'):
  return paste_bundle(bundle,target,[self.target],key,check)
 def test_copy_creates_new_identity_and_carries_bytes(self):
  text=figure();bundle=copy_bundle(text,[self.source],'source');result=self.paste(bundle)
  self.assertNotEqual(result['id_map']['fig-one'],'fig-one')
  self.assertEqual(result['assets']['1234567890abcdef.png'],b'PNG-source')
  self.assertEqual(analyze(result['markdown'])['objects']['ids'].keys(),{result['id_map']['fig-one']})
 def test_internal_references_remap_external_and_code_examples_stay_literal(self):
  text=figure()+'\n见 @fig:fig-one 和 @fig:fig-outside。`@fig:fig-one`\n\n```text\n@fig:fig-one\n```\n'
  result=self.paste(copy_bundle(text,[self.source],'source'));new=result['id_map']['fig-one']
  self.assertIn('见 @fig:'+new+' 和 @fig:fig-outside',result['markdown'])
  self.assertIn('`@fig:fig-one`',result['markdown']);self.assertIn('```text\n@fig:fig-one',result['markdown'])
 def test_cut_preserves_id_only_with_same_source_and_no_collision(self):
  bundle=copy_bundle(figure(),[self.source],'same','cut')
  self.assertEqual(self.paste(bundle,key='same')['id_map'],{})
  self.assertIn('fig-one',self.paste(bundle,target=figure(),key='same')['id_map'])
  self.assertIn('fig-one',self.paste(bundle,key='other')['id_map'])
 def test_collision_renames_source_and_preview_together(self):
  (self.source/'1234567890abcdef.svg').write_bytes(b'<svg/>')
  (self.target/'1234567890abcdef.png').write_bytes(b'different')
  text=figure(sourceAsset='assets/1234567890abcdef.svg',rendition={'format':'png','dpi':300,'page':1,'engine':'test'})
  result=self.paste(copy_bundle(text,[self.source],'source'))
  self.assertEqual(len(result['assets']),2)
  self.assertEqual(len({Path(name).stem for name in result['assets']}),1)
  self.assertNotIn('assets/1234567890abcdef.png',result['markdown'])
 def test_group_and_table_copy_are_structural_and_ids_independent_from_resource(self):
  group='::: {#fig-group layout-ncol=2 subfig-labels=off}\n![一](assets/1234567890abcdef.png)\n![二](assets/1234567890abcdef.png)\n组图说明\n:::\n'
  table='```report-table\n'+json.dumps({'schema':'report-table-v1','id':'tbl-one','caption':'表','rows':[[{'text':'甲','rowspan':1,'colspan':1}]]},ensure_ascii=False)+'\n```\n'
  bundle=copy_bundle(group+'\n'+table,[self.source],'source');result=self.paste(bundle)
  self.assertEqual(set(result['id_map']),{'fig-group','tbl-one'})
  self.assertEqual(len(result['assets']),1)
 def test_missing_or_tampered_bytes_fail(self):
  bundle=copy_bundle(figure(),[self.source],'source');bundle['assets']['1234567890abcdef.png']['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'摘要'):self.paste(bundle)
  with self.assertRaisesRegex(ValueError,'附件'):self.paste({'format':FORMAT,'markdown':figure(),'assets':{}})
 def test_local_relative_image_and_explicit_selection(self):
  image=Path(self.tmp.name)/'plot.png';image.write_bytes(b'local')
  bundle={'format':FORMAT,'markdown':'![图](plot.png "说明")\n','assets':{}}
  result=paste_bundle(bundle,'',[self.target],'target',check,source_folder=image.parent)
  self.assertIn('assets/'+sha(b'local')[:16]+'.png "说明"',result['markdown'])
  with self.assertRaisesRegex(ValueError,'CHOOSE_IMAGE_SOURCE'):self.paste(bundle)
  result=paste_bundle(bundle,'',[self.target],'target',check,local_files={'plot.png':base64.b64encode(b'local').decode()})
  self.assertIn('assets/',result['markdown'])
 def test_code_images_and_unrelated_caption_text_are_not_rewritten(self):
  text=figure(caption='fig-one assets/1234567890abcdef.png')+'\n```md\n![图](ghost.png)\n```\n'
  result=self.paste(copy_bundle(text,[self.source],'source'))
  self.assertIn('fig-one assets/1234567890abcdef.png',result['markdown']);self.assertIn('![图](ghost.png)',result['markdown'])

if __name__=='__main__':unittest.main()
