"""PASTE-01: real OS HTML/plain clipboard and Ctrl+V through the shipped editor.

No document, upload, source-map or clipboard endpoint is replaced. Fixtures are
generated here; native Word/WPS application copying is a separate integration.
"""
import base64
import json
import unittest
from browser_support import ManualService, value, select, source
from report_contract import analyze

PNG = 'iVBORw0KGgoAAAANSUhEUgAAABgAAAAQCAIAAACDRijCAAAAI0lEQVR4nGPUjephoAZgooopDKMGEQNGA5swGA0jwmDwhREAMgYBM6jouUsAAAAASUVORK5CYII='


class WordClipboard(ManualService):
    initial_markdown = '# 粘贴目标\n\n原有正文。\n\n'

    def paste(self, html, plain='Word 混合内容'):
        self.page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
        self.page.evaluate('''async data=>{
            await navigator.clipboard.write([new ClipboardItem({
                'text/plain':new Blob([data.plain],{type:'text/plain'}),
                'text/html':new Blob([data.html],{type:'text/html'})})]);
        }''', {'html': html, 'plain': plain})
        self.page.keyboard.press('Control+V')

    def test_01_order_objects_literal_text_save_and_single_undo(self):
        self.page.evaluate("()=>ReportStudioProgrammatic.open('new')")
        source(self.page,self.initial_markdown)
        before = value(self.page)
        select(self.page, len(before), len(before))
        rich = ('<div class="MsoNormal"><p><b>前文 **纯文字** 1.20 nm</b></p>'
                f'<p><img src="data:image/png;base64,{PNG}" alt="第一个图"></p>'
                '<p>中段 @fig:fig-outside $5.00</p>'
                '<table><tr><td colspan="2">合并表头</td></tr>'
                '<tr><td>甲 **原样**</td><td>12.34</td></tr></table>'
                f'<p><img src="data:image/png;base64,{PNG}"></p><p>末段。</p></div>')
        self.paste(rich)
        self.page.wait_for_function("document.querySelectorAll('#preview-content .report-figure-wrap').length===2 && document.querySelectorAll('#preview-content .report-table-wrap').length===1")
        after = value(self.page)
        ir = analyze(after)
        self.assertTrue(ir['ok'], ir['diagnostics'])
        self.assertEqual(len(ir['objects']['ids']), 3)
        self.assertTrue(after.index('前文') < after.index('第一个图') < after.index('中段') < after.index('合并表头') < after.index('末段'))
        self.assertEqual(self.page.locator('#preview-content strong').count(), 0)
        self.assertIn('**纯文字** 1.20 nm', self.page.locator('#preview-content').inner_text())
        self.assertIn('@fig:fig-outside $5.00', self.page.locator('#preview-content').inner_text())
        self.assertEqual(self.page.locator('#preview-content [colspan="2"]').count(), 1)
        self.page.wait_for_function("[...document.querySelectorAll('#preview-content img')].every(i=>i.naturalWidth>0)")
        self.page.keyboard.press('Control+Z')
        self.page.wait_for_function('text=>document.querySelector("#markdown").value===text', arg=before)
        self.page.keyboard.press('Control+Shift+Z')
        self.page.wait_for_function('text=>document.querySelector("#markdown").value===text', arg=after)
        self.page.locator('#btn-save').click()
        self.page.locator('#modal-body input').first.fill('Word混合粘贴')
        self.page.locator('#modal-ok').click()
        self.page.locator('.confirm-window button').filter(has_text='确认位置').click()
        self.page.wait_for_function("document.querySelector('#save-indicator').textContent.includes('已保存')")
        target = self.destination / 'Word混合粘贴'
        self.assertEqual((target / 'report.md').read_bytes(), after.encode('utf8'))
        self.assertEqual(len(list((target / 'assets').glob('*.png'))), 1)
        self.assertEqual(next((target / 'assets').glob('*.png')).read_bytes(), base64.b64decode(PNG))
        html = self.document.export()
        restored=self.page.evaluate('''async html=>{
            const t=document.createElement('template');t.innerHTML=html;
            return ReportExportArchive.readArchive(JSON.parse(t.content.getElementById('report-source').textContent),t.content);
        }''',html)
        self.assertEqual(restored['markdown'],after)
        if self.evidence:
            self.page.screenshot(path=str(self.evidence / 'mixed-paste.png'))
            (self.evidence / 'source.md').write_text(after, encoding='utf8')

    def test_02_tabs_crlf_and_literal_code_paste(self):
        before = '# Tab\r\n\r\n正文\r\n\t第二行😀\r\n\r\n'
        source(self.page, before)
        # CodeMirror normalizes source newlines to its configured separator.
        actual = value(self.page)
        select(self.page, len(actual), len(actual))
        self.page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
        plain = '文字\n\t缩进\n尾段'
        self.page.evaluate('text=>navigator.clipboard.writeText(text)', plain)
        self.page.keyboard.press('Control+V')
        self.page.wait_for_function("document.querySelector('#preview-content').textContent.includes('尾段')")
        self.assertNotIn('无法可靠定位', self.page.locator('#toast').inner_text())
        code = '# 示例\n\n```html\n\n```\n'
        source(self.page, code)
        at = code.index('```html\n') + len('```html\n')
        select(self.page, at, at)
        self.paste(f'<p><img src="data:image/png;base64,{PNG}"></p>', '<img example>')
        self.page.wait_for_function("document.querySelector('#markdown').value.includes('<img example>')")
        self.assertNotIn('report-figure', value(self.page))

    def test_03_missing_resources_and_unsupported_table_preserve_source(self):
        external=[]
        self.page.on('request',lambda req:external.append(req.url) if req.url.startswith('https://example.invalid/') else None)
        before = value(self.page)
        select(self.page, len(before), len(before))
        self.paste(f'<p>不能只贴这一段</p><table><tr><td><img src="data:image/png;base64,{PNG}"></td></tr></table>')
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('表内图片')")
        self.assertEqual(value(self.page), before)
        self.paste('<p>不能漏图</p><img src="https://example.invalid/image.png">')
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('外部')")
        self.assertEqual(value(self.page), before)
        self.assertEqual(external,[])

    def test_04_source_change_while_preparing_and_invalid_image_are_atomic(self):
        before=value(self.page);select(self.page,len(before),len(before))
        pending=[]
        self.page.route('**/api/objects/paste',lambda route:pending.append(route))
        self.paste(f'<p>迟到的粘贴</p><img src="data:image/png;base64,{PNG}">')
        self.page.wait_for_timeout(50)
        self.assertEqual(len(pending),1)
        updated=before+'新的输入\n'
        source(self.page,updated)
        pending.pop().continue_()
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('文稿或选区')")
        self.assertEqual(value(self.page),updated)
        self.page.unroute('**/api/objects/paste')
        select(self.page,len(updated),len(updated))
        self.paste('<p>不能只贴文字</p><img src="data:image/png;base64,YmFk">')
        self.page.wait_for_function("/PNG|图片/.test(document.querySelector('#toast').textContent)")
        self.assertEqual(value(self.page),updated)

    def test_05_native_clipboard_requires_explicit_action_and_no_paths(self):
        result=self.page.evaluate("async()=>{const r=await fetch('/api/clipboard/document',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:null})});return r.status}")
        self.assertEqual(result,403)
        result=self.page.evaluate("async()=>{const r=await fetch('/api/clipboard/document',{method:'POST',headers:{'Content-Type':'application/json','X-Report-Studio-Clipboard':'user-action'},body:JSON.stringify({path:'C:/arbitrary.png',text:null})});return r.status}")
        self.assertEqual(result,400)


if __name__ == '__main__':
    unittest.main()
