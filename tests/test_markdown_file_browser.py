"""MD-FILE/QUOTE/STRONG: real local service, original files and offline HTML."""
from pathlib import Path
import base64,json
from unittest.mock import patch
from browser_support import ManualService,source,value

class MarkdownFiles(ManualService):
    def open_file(self,raw=b'# File\r\n\r\nText\r\n'):
        self.notes=self.folder/self._testMethodName/'user notes';self.notes.mkdir()
        self.original=self.notes/'中文对照.md';self.original.write_bytes(raw)
        self.server.require_project_location=True
        with patch('native_picker.choose',return_value=self.original):
            self.page.locator('#menu-open').evaluate('e=>e.open=true')
            self.page.locator('#btn-markdown-open').click()
            self.page.wait_for_function("document.querySelector('#project-label').textContent.startsWith('Markdown · ')")
            self.page.wait_for_function("!document.querySelector('#app').inert&&!document.querySelector('#btn-save').disabled")
        return raw.decode('utf-8-sig')

    def test_direct_save_reopen_draft_and_exports_do_not_create_project(self):
        original=b'\xef\xbb\xbf'+('# 对照\r\n\r\n> 第一行\r\n> 第二行\r\n\r\n**形成联合体 （fin）**\r\n').encode('utf8')
        text=self.open_file(original);self.assertEqual(value(self.page),text)
        changed=text.replace('对照','对照修改');source(self.page,changed);self.page.locator('#markdown').evaluate('e=>e.sourceEditor.focus()')
        self.page.keyboard.press('Control+s')
        self.page.wait_for_function("document.querySelector('#save-indicator').classList.contains('saved')")
        self.assertEqual(self.original.read_bytes(),b'\xef\xbb\xbf'+changed.encode('utf8'))
        self.assertEqual(list(self.notes.iterdir()),[self.original])
        for mode in ['reading','recompilable']:
            self.page.locator('#menu-export').evaluate('e=>e.open=true')
            self.page.locator('#btn-export').click()
            self.page.locator('input[name="export-quality"][value="original"]').check()
            self.page.locator('input[name="export-source"][value="'+mode+'"]').check()
            with self.page.expect_response(lambda r:r.url.endswith('/api/export/store')) as received:
                self.page.locator('#modal-ok').click()
            response=received.value;self.assertTrue(response.ok,response.text())
            result=response.json()
            target=Path(result['path']);self.assertEqual(target.parent,self.notes)
            reader=self.browser.new_page()
            try:
                reader.goto(target.as_uri());p=reader.locator('main blockquote p')
                self.assertEqual(p.evaluate('n=>getComputedStyle(n).whiteSpace'),'pre-line')
                self.assertGreaterEqual(p.evaluate('n=>n.getBoundingClientRect().height/parseFloat(getComputedStyle(n).lineHeight)'),1.9)
                self.assertEqual(reader.locator('main strong').inner_text(),'形成联合体 （fin）')
            finally:reader.close()
        self.assertFalse((self.notes/'assets').exists());self.assertFalse((self.notes/'output').exists());self.assertFalse((self.notes/'meta.json').exists())
        self.assertEqual(self.original.read_bytes(),b'\xef\xbb\xbf'+changed.encode('utf8'))
        # A changed working buffer survives switching/recovery, while the file
        # remains the sole official source and the app owns recovery storage.
        source(self.page,changed+'\r\n恢复内容\r\n')
        self.page.wait_for_function("document.querySelector('#save-indicator').textContent.includes('草稿已备份')")
        identity=next(iter(self.server.markdown_files.mapping));self.page.reload()
        self.page.wait_for_function('typeof ReportStudioProgrammatic!=="undefined"')
        self.page.get_by_role('button',name='恢复所选草稿',exact=True).click()
        self.page.evaluate('()=>ReportStudioProgrammatic.ready()')
        self.assertEqual(value(self.page),changed+'\r\n恢复内容\r\n')
        self.page.evaluate('id=>ReportStudioProgrammatic.open(id)',identity)
        # programmatic open deliberately reads the official snapshot.
        self.assertEqual(value(self.page),changed)
        self.assertTrue(self.server.pending_drafts(identity))

    def test_outside_edits_are_rejected_without_overwrite_or_new_folder(self):
        text=self.open_file();source(self.page,text+'Local\r\n');self.page.locator('#markdown').evaluate('e=>e.sourceEditor.focus()')
        outside=b'# External\n';self.original.write_bytes(outside)
        self.page.keyboard.press('Control+s')
        self.page.wait_for_function("document.querySelector('#save-indicator').classList.contains('error')")
        self.assertEqual(self.original.read_bytes(),outside)
        self.assertEqual(list(self.notes.iterdir()),[self.original])
        self.assertTrue(self.server.pending_drafts(next(iter(self.server.markdown_files.mapping))))

    def test_pdf_and_display_settings_use_file_directory_and_app_data(self):
        text=self.open_file()
        self.page.locator('#color-theme').select_option('celadon')
        self.page.wait_for_function("!document.querySelector('#color-theme').disabled")
        identity=next(iter(self.server.markdown_files.mapping))
        self.page.evaluate('id=>ReportStudioProgrammatic.open(id)',identity)
        self.assertEqual(self.page.locator('#color-theme').input_value(),'celadon')
        self.page.locator('#menu-export').evaluate('e=>e.open=true')
        with self.page.expect_response(lambda r:r.url.endswith('/api/pdf/store'),timeout=45000) as received:
            self.page.locator('#btn-pdf').click()
        response=received.value;self.assertTrue(response.ok,response.text());target=Path(response.json()['path'])
        self.assertEqual(target.parent,self.notes);self.assertTrue(target.read_bytes().startswith(b'%PDF-'))
        self.assertEqual(self.original.read_bytes(),text.encode('utf8'))
        self.assertEqual({p.suffix for p in self.notes.iterdir()},{'.md','.pdf'})

    def test_native_path_cannot_be_supplied_by_http_and_file_binding_is_explicit(self):
        url=self.document.url
        with patch('native_picker.choose',side_effect=AssertionError('Do not open a picker for forged requests')):
            denied=self.page.request.post(url+'/api/markdown-file/open',data={},headers={'Content-Type':'application/json'})
            self.assertEqual(denied.status,403)
            forged=self.page.request.post(url+'/api/markdown-file/open',data={'path':'C:/private.md'},
                headers={'Content-Type':'application/json','Origin':url,'X-HRS-Project-Action':'user-action'})
            self.assertEqual(forged.status,400)
        text=self.open_file();identity=next(iter(self.server.markdown_files.mapping))
        denied=self.page.request.post(url+'/api/upload',data={'document_id':identity,'name':'hidden.png','base64':'AAAA'},
            headers={'Content-Type':'application/json'})
        self.assertEqual(denied.status,409);self.assertEqual(list(self.notes.iterdir()),[self.original])
        self.assertEqual(self.original.read_bytes(),text.encode('utf8'))

    def test_exact_bold_phrase_in_preview_tables_and_export(self):
        # MD-STRONG-01: this supplied spelling must be tested with the shipped
        # math/notes/extensions, rather than only calling stock marked.parse.
        text='# 加粗\n\n**形成联合体 （fin）**\n\n先**形成联合体 （fin）**再执行。\n\n| 说明 |\n| --- |\n| **形成联合体 （fin）** |\n'
        source(self.page,text);self.page.locator('#render-profile').select_option('free')
        self.page.wait_for_function("document.querySelectorAll('#preview-content strong').length===3")
        for node in self.page.locator('#preview-content strong').all():self.assertEqual(node.inner_text(),'形成联合体 （fin）')
        exported=self.document.export();reader=self.browser.new_page()
        try:
            reader.set_content(exported);self.assertEqual(reader.locator('main strong').count(),3)
        finally:reader.close()

    def test_attachment_cancel_then_conversion_keeps_original_and_existing_import(self):
        text=self.open_file();source(self.page,text+'Unsaved\r\n')
        from test_v061_import_contract import PNG
        image=self.folder/self._testMethodName/'image.png';image.write_bytes(PNG)
        self.page.locator('#file-image').set_input_files(str(image))
        self.page.locator('.confirm-layer').wait_for()
        self.page.get_by_role('button',name='取消',exact=True).click();self.assertEqual(value(self.page),text+'Unsaved\r\n')
        self.assertEqual(self.original.read_bytes(),text.encode('utf8'))
        self.page.locator('#file-image').set_input_files(str(image));self.page.get_by_role('button',name='选择工程目录',exact=True).click()
        self.page.get_by_label('项目文件夹名称',exact=True).fill('Direct-file-converted')
        self.page.locator('#modal-ok').click()
        self.page.get_by_role('button',name='确认位置',exact=True).click()
        self.page.wait_for_selector('#preview-content img')
        self.page.keyboard.press('Control+s')
        self.page.wait_for_function("document.querySelector('#save-indicator').classList.contains('saved')")
        project=self.destination/'Direct-file-converted'
        self.assertTrue((project/'report.md').exists());self.assertTrue(list((project/'assets').glob('*.png')))
        self.assertEqual(self.original.read_bytes(),text.encode('utf8'))
        self.assertEqual(list(self.notes.iterdir()),[self.original])

    def test_rich_object_paste_converts_before_staging_and_preserves_source(self):
        # The paste adapter captures its context again only after the explicit
        # document conversion; otherwise assets belong to the old file draft.
        text=self.open_file();responses=[]
        self.page.on('response',lambda r:responses.append((r.url,r.status,r.text()[:1600])) if '/api/objects/paste' in r.url or '/api/markdown-file/to-project' in r.url else None)
        from test_v061_import_contract import PNG
        from object_clipboard import copy_bundle
        assets=self.folder/self._testMethodName/'clipboard-assets';assets.mkdir()
        (assets/'test.png').write_bytes(PNG)
        figure={'schema':'report-figure-v1','id':'fig-copied','kind':'image','src':'assets/test.png','caption':'Copy','alt':''}
        raw='Paste text\n\n```report-figure\n'+json.dumps(figure)+'\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |\n'
        bundle=copy_bundle(raw,[assets],None)
        encoded=base64.b64encode(json.dumps(bundle).encode()).decode()
        html='<span data-hrs-clipboard="'+encoded+'"></span>'
        self.page.context.grant_permissions(['clipboard-read','clipboard-write'])
        self.page.evaluate('''async ({plain,html})=>navigator.clipboard.write([new ClipboardItem({
            'text/plain':new Blob([plain],{type:'text/plain'}),'text/html':new Blob([html],{type:'text/html'})})])''',{'plain':raw,'html':html})
        self.page.locator('#markdown').evaluate('e=>{e.sourceEditor.setSelectionRange(e.sourceEditor.value.length);e.sourceEditor.focus()}')
        self.page.keyboard.press('Control+v')
        self.page.get_by_role('button',name='选择工程目录',exact=True).click()
        self.page.get_by_label('项目文件夹名称',exact=True).fill('Direct-paste-converted')
        self.page.locator('#modal-ok').click();self.page.get_by_role('button',name='确认位置',exact=True).click()
        try:self.page.wait_for_selector('#preview-content img');self.page.wait_for_selector('#preview-content table')
        except Exception:
            print('File paste state:',repr(value(self.page)),self.page.locator('#preview-content').inner_text(),self.page.locator('#toast').inner_text(),responses,flush=True);raise
        self.assertIn('Paste text',value(self.page));self.assertNotIn('fig-copied',value(self.page))
        self.page.keyboard.press('Control+s');self.page.wait_for_function("document.querySelector('#save-indicator').classList.contains('saved')")
        project=self.destination/'Direct-paste-converted'
        self.assertTrue(list((project/'assets').glob('*.png')))
        self.assertEqual(self.original.read_bytes(),text.encode('utf8'))
        self.assertEqual(list(self.notes.iterdir()),[self.original])

if __name__=='__main__':
    import unittest
    unittest.main()
