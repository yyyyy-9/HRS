"""FRONTEND-03: shared browser/Python rules, canonical IR and bounded files."""
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from asset_paths import normalize_asset,asset_file
from report_contract import analyze
from object_clipboard import copy_bundle,paste_bundle

CASES={
 'assets/a.png':'assets/a.png', './assets/a.png':'assets/a.png',
 'assets/sub/a.png':'assets/sub/a.png', './assets/sub/two/a.PNG':'assets/sub/two/a.PNG',
 '../assets/a.png':None, 'assets/../a.png':None, 'assets/sub/../../a.png':None,
 '/assets/a.png':None, 'file:///assets/a.png':None, 'https://example.invalid/a.png':None,
 'assets//a.png':None, 'assets/./a.png':None, 'assets/a.png?x=1':None,
 'assets/%2e%2e/a.png':None, 'assets/a%2epng':None, 'assets/sub\\a.png':None,
 'assets/sub./a.png':None,'assets/CON/a.png':None,'assets/sub/CON.png':None,
 'assets/a.exe':None, 'assets/a.pdf':None, '././assets/a.png':None,
 'assets/'+'a/'*8+'a.png':'assets/'+'a/'*8+'a.png', 'assets/'+'a/'*9+'a.png':None,
}


class AssetPaths(unittest.TestCase):
    def test_browser_and_python_use_same_declared_rules(self):
        self.assertEqual({x:normalize_asset(x) for x in CASES},CASES)
        node=os.environ.get('HRS_BRIDGE_NODE') or shutil.which('node')
        self.assertTrue(node,'Node is required by the declared contract suite')
        script='const p=require("./app/web/asset_paths.js");let s="";process.stdin.on("data",x=>s+=x);process.stdin.on("end",()=>process.stdout.write(JSON.stringify(Object.fromEntries(JSON.parse(s).map(x=>[x,p.normalize(x)])))));'
        result=subprocess.run([node,'-e',script],cwd=ROOT,input=json.dumps(list(CASES)),text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout),CASES)

    def test_ir_has_canonical_dependencies_and_exact_original_source(self):
        text='# Path\r\n\r\n![One](./assets/sub/a.png)\r\n\r\nInline ![Two](assets/b.png).\r\n\r\n<img src="./assets/sub/a.png">\r\n'
        ir=analyze(text)
        self.assertTrue(ir['ok'],ir['diagnostics'])
        self.assertEqual(ir['assets'],['assets/b.png','assets/sub/a.png'])
        self.assertEqual(''.join(b['source'] for b in ir['blocks']),text)

    def test_parent_links_and_unsafe_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'sub').mkdir();(root/'sub/a.png').write_bytes(b'owned')
            self.assertEqual(asset_file(root,'sub/a.png'),root/'sub/a.png')
            with patch('asset_paths.is_link',side_effect=lambda p:Path(p)==root/'sub'):
                with self.assertRaisesRegex(ValueError,'链接'):asset_file(root,'sub/a.png')
                ir=analyze('![x](assets/sub/a.png)',assets=root)
                self.assertTrue(any(d['code']=='INVALID_ASSET' for d in ir['diagnostics']))
            for value in ['../a.png','sub/../../a.png','sub/a.png:stream','sub\\a.png']:
                with self.assertRaises(ValueError):asset_file(root,value)

    def test_clipboard_nested_basenames_never_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source';target=Path(folder)/'target';source.mkdir();target.mkdir()
            for name,data in [('one/a.png',b'first'),('two/a.png',b'second')]:
                p=source/name;p.parent.mkdir();p.write_bytes(data)
            text='![One](./assets/one/a.png)\n\n![Two](assets/two/a.png)\n'
            bundle=copy_bundle(text,[source],'from')
            out=paste_bundle(bundle,'',[target],'to',lambda ext,data:None)
            self.assertEqual(out['assets'],{'one/a.png':b'first','two/a.png':b'second'})
            self.assertEqual(out['markdown'],text)


if __name__=='__main__':unittest.main(verbosity=2)
