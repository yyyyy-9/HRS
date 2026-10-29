"""MD-FILE-01: chosen UTF-8 files, no sibling metadata, guarded commits."""
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))

class MarkdownFileContract(unittest.TestCase):
    # Resolve TEMP once so identity checks and failure-injection mocks agree
    # with the canonical paths used by the registry on Windows (including 8.3).
    def test_eol_expansion_limit_rejects_before_committing(self):
        from markdown_file import MarkdownFiles
        from studio import digest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();source=root/'large.md';original=b'# T\r\n';source.write_bytes(original)
            files=MarkdownFiles(root/'data');identity=files.register(source)
            with patch('markdown_file.MAX_MARKDOWN_BYTES',100):
                with self.assertRaisesRegex(ValueError,'按原换行格式'):
                    files.save(identity,'a\n'*40,digest(original))
            self.assertEqual(source.read_bytes(),original)
            self.assertFalse((files.folder(identity)/'.history').exists())

    def test_file_commit_uses_original_eol_and_preserves_existing_terminal_newline(self):
        # MD-FILE-EOL-01: API callers and native Enter can supply LF even
        # though the selected file's existing lines use CRLF.
        from markdown_file import MarkdownFiles
        from studio import digest
        cases=[
            (b'\xef\xbb\xbf', '\r\n', True),
            (b'', '\n', True),
            (b'', '\r\n', False),
            (b'', '\r', True),
            (b'\xef\xbb\xbf', '\n', False),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();files=MarkdownFiles(root/'data')
            for number,(bom,eol,terminal) in enumerate(cases):
                with self.subTest(eol=repr(eol),terminal=terminal,bom=bool(bom)):
                    source=root/(str(number)+'.md')
                    original=bom+('# 中文😀'+eol+eol+'直接编辑原文。'+(eol if terminal else '')).encode('utf8')
                    source.write_bytes(original);identity=files.register(source)
                    edited=original.decode('utf-8-sig')+'\nUI_SAVE_MARKER'
                    expected=bom+(edited.replace('\r\n','\n').replace('\r','\n').replace('\n',eol)+(eol if terminal else '')).encode('utf8')
                    actual=files.save(identity,edited,digest(original))
                    self.assertEqual(actual,expected);self.assertEqual(source.read_bytes(),expected)
                    repeated=files.save(identity,actual.decode('utf-8-sig'),digest(actual))
                    self.assertEqual(repeated,actual)
                    self.assertEqual(len(list((files.folder(identity)/'.history').glob('*.md'))),1)

    def test_source_stays_single_and_bom_crlf_backup_conflict_are_preserved(self):
        from markdown_file import MarkdownFiles
        from studio import digest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();user=root/'notes';user.mkdir();workspace=root/'data';workspace.mkdir()
            source=user/'中文😀.md';original=b'\xef\xbb\xbf'+('# 标题\r\n\r\n中文😀\r\n').encode('utf8');source.write_bytes(original)
            files=MarkdownFiles(workspace);identity=files.register(source)
            self.assertEqual(files.register(source),identity)
            self.assertEqual(files.source(identity),source)
            self.assertEqual(list(user.iterdir()),[source])
            storage=files.folder(identity)
            self.assertFalse((storage/'report.md').exists())
            text='# 标题\r\n\r\n更改中文😀\r\n'
            result=files.save(identity,text,digest(original))
            expected=b'\xef\xbb\xbf'+text.encode('utf8')
            self.assertEqual(source.read_bytes(),expected);self.assertEqual(result,expected)
            self.assertEqual(next((storage/'.history').glob('*.md')).read_bytes(),original)
            with self.assertRaisesRegex(ValueError,'STALE_SNAPSHOT'):
                files.save(identity,'stale',digest(original))
            self.assertEqual(source.read_bytes(),expected)
            from studio import atomic_write
            def blocked_target(path,data):
                if Path(path)==source:raise PermissionError('shared lock')
                return atomic_write(path,data)
            with patch('studio.atomic_write',side_effect=blocked_target):
                with self.assertRaises(PermissionError):files.save(identity,'failed',digest(expected))
            self.assertEqual(source.read_bytes(),expected)
            reloaded=MarkdownFiles(workspace);self.assertEqual(reloaded.source(identity),source)
            self.assertEqual(list(user.iterdir()),[source])

    def test_real_attachments_require_project_but_code_examples_and_tables_do_not(self):
        from markdown_file import require_text_only
        for text in ['![图](a.png)','![图](assets/a.png)','<img src="a.png">']:
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'HRS 工程'):require_text_only(text)
        for text in ['```md\n![示例](a.png)\n```\n','`![示例](a.png)`','| A | B |\n|---|---|\n| $x$ | **值** |\n','> a\n> b\n']:
            with self.subTest(text=text):require_text_only(text)

    def test_invalid_source_and_symlink_never_register(self):
        from markdown_file import MarkdownFiles
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();files=MarkdownFiles(root/'data');source=root/'test.docx';source.write_bytes(b'not md')
            with self.assertRaises(ValueError):files.register(source)
            source=root/'bad.md';source.write_bytes(b'\xff')
            with self.assertRaises(ValueError):files.register(source)
            source.write_bytes(b'![missing](image.png)')
            with self.assertRaisesRegex(ValueError,'HRS 工程'):files.register(source)
            source.write_bytes(b'# Plain\n')
            with patch('markdown_file.is_link',side_effect=lambda p:Path(p)==source):
                with self.assertRaisesRegex(ValueError,'链接'):files.register(source)
            self.assertFalse(files.mapping)

if __name__=='__main__':unittest.main()
