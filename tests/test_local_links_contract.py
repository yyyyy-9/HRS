"""TOPIC-LINKS-01: explicit native path authority and non-executable opening."""
from pathlib import Path
from unittest.mock import patch
import os
from test_report_workspace_contract import WorkspaceService


class LocalLinks(WorkspaceService):
    def test_existing_relative_absolute_and_uri_targets(self):
        folder=self.project/'linked folder';folder.mkdir();file=folder/'文稿.txt';file.write_text('owned',encoding='utf8')
        opened=[]
        with patch('local_links.open_target',side_effect=lambda name:opened.append(Path(name).resolve())):
            for href in ('./linked%20folder',file.as_posix(),file.as_uri()):
                status,result=self.post('/api/local-link/open',{'document_id':'legacy','href':href})
                self.assertEqual(status,200,result)
        self.assertEqual(opened,[folder.resolve(),file.resolve(),file.resolve()])
        self.assertEqual((self.project/'report.md').read_bytes(),self.full.encode('utf8'))

    def test_native_adapter_passes_one_literal_path_or_reports_platform(self):
        from local_links import open_target
        target=self.project/'中文 file.txt'
        if os.name=='nt':
            with patch('local_links.os.startfile') as launch:
                open_target(target);launch.assert_called_once_with(str(target))
        else:
            with self.assertRaisesRegex(ValueError,'Windows'):open_target(target)

    def test_missing_action_unsafe_scheme_and_program_paths_are_refused(self):
        file=self.project/'program.cmd';file.write_text('echo forbidden',encoding='utf8')
        with patch('local_links.open_target') as launch:
            status,_=self.post('/api/local-link/open',{'document_id':'legacy','href':str(file)},authorized=False)
            self.assertEqual(status,403)
            programs=[]
            for suffix in ('.cmd','.exe','.py','.PYW','.ps1','.jar','.lnk','.msix'):
                program=self.project/('program'+suffix);program.write_text('not executed',encoding='utf8');programs.append(str(program))
            for href in ('javascript:alert(1)','https://example.org','file:///C:/bad%00.txt',*programs,'missing.txt'):
                status,_=self.post('/api/local-link/open',{'document_id':'legacy','href':href})
                self.assertGreaterEqual(status,400,href)
            launch.assert_not_called()

    def test_relative_new_draft_has_no_guessed_base(self):
        with patch('local_links.open_target') as launch:
            status,result=self.post('/api/local-link/open',{'document_id':'new','href':'./notes.txt'})
            self.assertNotEqual(status,200);self.assertIn('工程',result['error']);launch.assert_not_called()
