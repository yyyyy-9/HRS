"""MDI-01: one declared source directory, existing IR/resource import rules."""
from pathlib import Path
import base64,json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from markdown_import import prepare_markdown_import
from studio import check_image

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAABgAAAAQCAIAAACDRijCAAAAI0lEQVR4nGPUjephoAZgooopDKMGEQNGA5swGA0jwmDwhREAMgYBM6jouUsAAAAASUVORK5CYII=')
FIXTURE=Path(__file__).resolve().parent/'fixtures/fp_hartmann'

class ImportContract(unittest.TestCase):
    def test_actual_report_resolves_seven_images_and_changes_only_paths(self):
        source=FIXTURE/'REPORT.md';raw=source.read_bytes();result=prepare_markdown_import(source,check_image)
        self.assertEqual(result['image_references'],7);self.assertEqual(len(result['assets']),7)
        restored=result['markdown']
        for old,new in result['asset_map'].items():restored=restored.replace(new,old)
        self.assertEqual(restored.encode('utf8'),raw)
        self.assertEqual(source.read_bytes(),raw)
        for old,new in result['asset_map'].items():
            self.assertEqual(base64.b64decode(result['assets'][new.split('/')[-1]]),(source.parent/old).read_bytes())

    def test_missing_images_are_reported_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'input.md';raw=b'# T\n\n![A](a/missing.png)\n![B](b/missing.png)\n'
            source.write_bytes(raw)
            with self.assertRaises(ValueError) as error:prepare_markdown_import(source,check_image)
            self.assertIn('2 项',str(error.exception));self.assertIn('a/missing.png',str(error.exception));self.assertIn('b/missing.png',str(error.exception))
            self.assertEqual(source.read_bytes(),raw);self.assertEqual(list(source.parent.iterdir()),[source])

    def test_unicode_crlf_spaces_and_url_encoded_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'图 像').mkdir();(folder/'图 像/结果 图.png').write_bytes(PNG)
            raw='# 中文😀\r\n\r\n![说明](./图%20像/结果%20图.png "标题")\r\n\r\n`![例子](missing.png)`\r\n'
            source=folder/'中文.md';source.write_bytes(raw.encode('utf8'));result=prepare_markdown_import(source,check_image)
            self.assertEqual(result['image_references'],1);self.assertEqual(len(result['assets']),1)
            self.assertIn(' "标题")\r\n',result['markdown']);self.assertIn('`![例子](missing.png)`',result['markdown'])
            rewritten=next(iter(result['asset_map'].values()))
            self.assertEqual(result['markdown'].replace(rewritten,'./图%20像/结果%20图.png'),raw)

    def test_code_examples_do_not_require_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'input.md';raw='# T\n\n```md\n![例子](missing.png)\n```\n'
            source.write_bytes(raw.encode());result=prepare_markdown_import(source,check_image)
            self.assertEqual(result['markdown'],raw);self.assertEqual(result['assets'],{})

    def test_parent_escape_does_not_read_an_external_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'outside.png').write_bytes(PNG);(root/'doc').mkdir()
            source=root/'doc/input.md';source.write_bytes(b'# T\n\n![outside](../outside.png)\n')
            with self.assertRaisesRegex(ValueError,'不在 Markdown 所在目录'):prepare_markdown_import(source,check_image)

    def test_invalid_image_rejected_by_existing_image_checker(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'bad.png').write_bytes(b'not a picture');source=folder/'input.md'
            source.write_bytes(b'# T\n\n![bad](bad.png)\n')
            with self.assertRaises(ValueError):prepare_markdown_import(source,check_image)

if __name__=='__main__':unittest.main()
