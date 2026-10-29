"""CORE-01: authoritative catalogs, validation parity and release derivation."""
from pathlib import Path
import json,os,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from release_info import load_release
from product_settings import load_settings
import render_profile,color_theme


class CoreConsistency(unittest.TestCase):
    def test_version_identity_can_change_without_editing_consumers(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'release.json';p.write_text(json.dumps({'version':'9.8.7','package_revision':'R42'}),encoding='utf8')
            value=load_release(p)
            self.assertEqual(value['release'],'v9.8.7 R42')
            self.assertEqual(value['stem'],'HTMLReportStudio_v9.8.7_R42')
            p.write_text(json.dumps({'version':'9.8','package_revision':'R0'}),encoding='utf8')
            with self.assertRaises(ValueError):load_release(p)

    def test_generated_browser_catalog_is_fresh_and_not_a_second_definition(self):
        node=os.environ.get('HRS_BRIDGE_NODE') or __import__('shutil').which('node')
        self.assertTrue(node,'Node is required for this cross-language contract check')
        reply=subprocess.run([node,'app/tools/build_settings.js','--check'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(reply.returncode,0,reply.stderr)
        data=json.loads(subprocess.check_output([node,'-e',"process.stdout.write(JSON.stringify(require('./app/web/product_settings.js')))"],cwd=ROOT))
        self.assertEqual(data,load_settings())

    def test_python_and_browser_normalizers_have_the_same_boundary(self):
        cases=[None,{},[],True,3,'free',{'show_object_numbers':False},{'show_heading_numbers':True},
               {'show_heading_numbers':None},{'show_object_numbers':None},{'show_heading_numbers':1},
               {'show_object_numbers':'false'},{'unknown':True},{'show_equation_numbers':False,'preserve_blank_lines':True},{'show_equation_numbers':False,'preserve_blank_lines':None},{'show_equation_numbers':False,'preserve_blank_lines':'yes'}]
        def probe(value):
            try:return {'ok':True,'value':render_profile.normalize_options(value)}
            except (ValueError,TypeError):return {'ok':False}
        node=os.environ.get('HRS_BRIDGE_NODE') or __import__('shutil').which('node')
        js="const p=require('./app/web/render_profile.js');process.stdout.write(JSON.stringify(JSON.parse(process.argv[1]).map(v=>{try{return {ok:true,value:p.normalizeOptions(v)}}catch{return {ok:false}}})))"
        actual=json.loads(subprocess.check_output([node,'-e',js,json.dumps(cases)],cwd=ROOT))
        self.assertEqual(actual,[probe(value) for value in cases])
        self.assertEqual(render_profile.new_options('free'),{'show_object_numbers':False,'show_heading_numbers':False,'show_equation_numbers':False,'preserve_blank_lines':True})
        self.assertEqual(render_profile.new_options('engineering'),render_profile.normalize_options())

    def test_palette_and_default_profiles_use_the_catalog(self):
        data=load_settings()
        self.assertEqual(tuple(x['id'] for x in data['color_themes']['choices']),color_theme.NAMES)
        self.assertEqual(color_theme.normalize(),data['color_themes']['default'])
        self.assertEqual(render_profile.normalize(),data['render_profiles']['default'])
        for value in ['javascript:alert(1)','unknown',{},[]]:
            with self.assertRaises((ValueError,TypeError)):color_theme.normalize(value)

    def test_editing_one_catalog_changes_python_and_javascript_consumers(self):
        with tempfile.TemporaryDirectory() as d:
            app=Path(d)/'app';(app/'tools').mkdir(parents=True);(app/'web').mkdir()
            # The shared generator also emits asset rules; carry that canonical
            # input while mutating only the product settings under test.
            for name in ['product_settings.py','asset_paths.json','render_profile.py','color_theme.py','tools/build_settings.js','web/render_profile.js','web/color_theme.js']:
                (app/name).write_bytes((ROOT/'app'/name).read_bytes())
            data=load_settings();data['color_themes']['default']='warm'
            data['color_themes']['choices'][0]['label']='测试标签'
            data['render_options']['show_heading_numbers']['new_free']=True
            (app/'product_settings.json').write_text(json.dumps(data),encoding='utf8')
            node=os.environ.get('HRS_BRIDGE_NODE') or __import__('shutil').which('node')
            subprocess.check_call([node,str(app/'tools/build_settings.js'),'--write'])
            js="const p=require('./web/render_profile.js'),t=require('./web/color_theme.js');process.stdout.write(JSON.stringify([p.newOptions('free'),t.normalize(),t.labels[0]]))"
            browser=json.loads(subprocess.check_output([node,'-e',js],cwd=app))
            # Embedded Python's _pth ignores cwd as an import root; always probe the isolated fixture.
            py="import sys;sys.path.insert(0,sys.argv[1]);import json,render_profile as p,color_theme as t;print(json.dumps([p.new_options('free'),t.normalize()]))"
            python=json.loads(subprocess.check_output([sys.executable,'-X','utf8','-B','-c',py,str(app)],cwd=app))
            self.assertEqual(browser[:2],python)
            self.assertEqual(browser,[{'show_object_numbers':False,'show_heading_numbers':True,'show_equation_numbers':False,'preserve_blank_lines':True},'warm','测试标签'])


if __name__=='__main__':unittest.main()
