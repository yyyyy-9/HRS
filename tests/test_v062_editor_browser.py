"""SEL-01 / READ-01: mouse selection paint, typed highlights and reading view.

Real local service and browser; no renderer/clipboard/source API replacement.
Pillow only reads browser screenshots; it does not create or edit the evidence.
"""
import io,json,unittest
from PIL import Image
from browser_support import ManualService
from browser_support import source,value

TEXT='# 选区与阅读\n\n## 开始 {#sec-start}\n\n普通正文，可以阅读。\n\n```python\nalpha = 1234567890\nbeta = alpha + 42\nprint(beta)\n```\n\n## 表格 {#sec-table}\n\n| 参数 | 数值 |\n|---|---|\n| A | 10 |\n\n参见 @sec:sec-start。\n\n- [ ] 任务\n'

class EditorFeedback(ManualService):
    def typed(self,text):
        source(self.page,'');self.page.locator('.cm-content').click()
        self.page.keyboard.insert_text(text)
        self.page.wait_for_function('t=>document.querySelector("#markdown").sourceEditor.value===t',arg=text)

    def test_01_typed_highlights_and_code_examples_have_same_rules(self):
        text='# 高亮\n\n==重点== ==🔴重要== ==🟢进展== ==🔵信息==\n\n`==🔴代码示例==`\n\n```md\n==🟢代码示例==\n```\n'
        self.typed(text);self.page.wait_for_function('document.querySelectorAll("#preview-content mark").length===4')
        colors=self.page.locator('#preview-content mark').evaluate_all('xs=>xs.map(e=>getComputedStyle(e).backgroundColor)')
        self.assertEqual(colors,['rgb(255, 241, 168)','rgb(255, 215, 215)','rgb(216, 243, 220)','rgb(217, 234, 255)'])
        self.assertEqual(self.page.locator('#preview-content code mark').count(),0)
        self.assertEqual(value(self.page),text)
        html=self.page.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})')
        file=self.folder/'highlights.html';file.write_bytes(html.encode('utf8'))
        reader=self.browser.new_page();reader.goto(file.as_uri())
        self.assertEqual(reader.locator('main mark').evaluate_all('xs=>xs.map(e=>getComputedStyle(e).backgroundColor)'),colors)
        reader.close()
        self.page.locator('#render-profile').select_option('engineering')
        self.page.wait_for_function('document.body.dataset.renderProfile==="engineering"')
        self.assertEqual(self.page.locator('#preview-content mark').count(),0)
        self.assertEqual(value(self.page),text)

    def test_02_mouse_selection_is_visible_and_copy_preserves_code(self):
        source(self.page,TEXT);self.page.locator('#btn-unfold-all').click()
        a=TEXT.index('alpha =');b=TEXT.index('print(beta)')-1
        for theme in ('blue','warm','navy'):
            self.page.locator('#color-theme').select_option(theme)
            self.page.wait_for_function('t=>document.documentElement.dataset.colorTheme===t',arg=theme)
            self.page.evaluate('a=>{const e=document.querySelector("#markdown").sourceEditor;e.setSelectionRange(a,a);e.focus();e.view.dispatch({scrollIntoView:true});}',a)
            self.page.wait_for_function('a=>!!document.querySelector("#markdown").sourceEditor.view.coordsAtPos(a)',arg=a)
            coords=self.page.evaluate('([a,b])=>{const v=document.querySelector("#markdown").sourceEditor.view;return [v.coordsAtPos(a),v.coordsAtPos(b)];}',[a,b])
            start,end=coords
            x=start['left']+30;y=start['bottom']-3
            before=self.page.screenshot()
            self.page.mouse.move(start['left']+0.1,(start['top']+start['bottom'])/2)
            self.page.mouse.down();self.page.mouse.move(end['left'],(end['top']+end['bottom'])/2,steps=14);self.page.mouse.up()
            self.page.wait_for_function('([a,b])=>{const e=document.querySelector("#markdown").sourceEditor;return e.selectionStart===a&&e.selectionEnd===b;}',arg=[a,b])
            self.page.wait_for_function('document.querySelector(".cm-selectionBackground")?.getBoundingClientRect().width>20')
            after=self.page.screenshot()
            p=Image.open(io.BytesIO(before)).convert('RGB').getpixel((int(x),int(y)))
            q=Image.open(io.BytesIO(after)).convert('RGB').getpixel((int(x),int(y)))
            if self.evidence:
                (self.evidence/(theme+'-before.png')).write_bytes(before)
                (self.evidence/(theme+'-selected.png')).write_bytes(after)
                (self.evidence/(theme+'-paint.json')).write_text(json.dumps({'before':p,'selected':q,'point':[x,y],'range':[a,b]},ensure_ascii=False),encoding='utf8')
            self.assertGreater(sum(abs(c-d) for c,d in zip(p,q)),45,(theme,p,q))
            self.page.context.grant_permissions(['clipboard-read','clipboard-write'])
            self.page.evaluate('()=>navigator.clipboard.writeText("selection-sentinel")')
            self.page.keyboard.press('Control+c')
            self.page.wait_for_function(r'expected=>navigator.clipboard.readText().then(t=>t.replace(/\r\n/g,"\n")===expected)',arg=TEXT[a:b])
            self.assertEqual(value(self.page),TEXT)

    def reading(self):
        source(self.page,TEXT);self.page.locator('[data-view=reading]').click()
        self.page.wait_for_selector('#edit-layout.reading')

    def test_03_reading_navigation_stays_reading_and_text_is_not_editable(self):
        self.reading()
        self.assertEqual(self.page.locator('[data-view=visual]').count(),0)
        self.assertFalse(self.page.locator('#source-pane').is_visible())
        self.assertEqual(self.page.locator('#preview-content [contenteditable=true]').count(),0)
        self.assertEqual(self.page.locator('#preview-content [data-block-editor]').count(),0)
        self.page.locator('#toc a').filter(has_text='表格').click()
        self.assertTrue(self.page.locator('#edit-layout.reading').is_visible())
        self.assertFalse(self.page.locator('#source-pane').is_visible())
        paragraph=self.page.locator('#preview-content p').filter(has_text='普通正文').first
        paragraph.dblclick()
        self.assertTrue(self.page.locator('#modal-layer').is_hidden())
        self.assertFalse(paragraph.evaluate('e=>e.isContentEditable'))
        paragraph.hover()
        self.assertEqual(paragraph.evaluate('e=>getComputedStyle(e.closest(".doc-block")).outlineStyle'),'none')
        self.page.locator('#preview-content [data-xref-raw]').click()
        self.assertTrue(self.page.locator('#edit-layout.reading').is_visible())
        self.assertEqual(value(self.page),TEXT)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'reading.png'))

    def test_04_reading_preserves_table_dialog_and_task_transaction(self):
        self.reading();self.page.locator('#preview-content table').dblclick()
        self.page.wait_for_selector('#modal-layer:not([hidden])')
        self.assertIn('表格',self.page.locator('#modal-title').inner_text())
        self.page.locator('#modal-cancel').click()
        self.assertTrue(self.page.locator('#edit-layout.reading').is_visible())
        box=self.page.locator('#preview-content .hrs-task-checkbox');box.check()
        self.page.wait_for_function('document.querySelector("#markdown").sourceEditor.value.includes("- [x] 任务")')
        self.assertTrue(self.page.locator('#edit-layout.reading').is_visible())
        self.page.locator('#btn-undo').click()
        self.page.wait_for_function('t=>document.querySelector("#markdown").sourceEditor.value===t',arg=TEXT)

    def test_05_reading_edit_command_switches_explicitly_and_split_editing_remains(self):
        self.reading();self.page.locator('[data-insert=bold]').click()
        self.assertTrue(self.page.locator('#edit-layout.split').is_visible())
        self.assertEqual(value(self.page),TEXT,'Reading toolbar must first reveal source without editing an unseen caret')
        paragraph=self.page.locator('#preview-content p').filter(has_text='普通正文').first
        paragraph.dblclick();self.assertTrue(paragraph.evaluate('e=>e.isContentEditable'))
        paragraph.fill('已修改的普通正文。');paragraph.blur()
        self.page.wait_for_function('document.querySelector("#markdown").sourceEditor.value.includes("已修改的普通正文。")')

    def test_06_preview_code_selection_and_copy_are_visible(self):
        self.reading()
        code=self.page.locator('#preview-content .hrs-code-content')
        coords=code.evaluate('e=>{const w=document.createTreeWalker(e,NodeFilter.SHOW_TEXT),n=w.nextNode(),r=document.createRange();r.setStart(n,0);r.setEnd(n,n.length);return r.getBoundingClientRect().toJSON()}')
        x=coords['left']+10;y=coords['bottom']-2
        before=self.page.screenshot()
        self.page.mouse.move(coords['left']+0.1,(coords['top']+coords['bottom'])/2)
        self.page.mouse.down();self.page.mouse.move(coords['right']-0.1,(coords['top']+coords['bottom'])/2,steps=10);self.page.mouse.up()
        selected=self.page.evaluate('getSelection().toString()')
        self.assertTrue(selected);self.assertIn(selected,code.inner_text())
        after=self.page.screenshot()
        p=Image.open(io.BytesIO(before)).convert('RGB').getpixel((int(x),int(y)))
        q=Image.open(io.BytesIO(after)).convert('RGB').getpixel((int(x),int(y)))
        self.assertGreater(sum(abs(c-d) for c,d in zip(p,q)),45,(p,q))
        self.page.context.grant_permissions(['clipboard-read','clipboard-write'])
        self.page.evaluate('()=>navigator.clipboard.writeText("preview-sentinel")')
        self.page.keyboard.press('Control+c')
        self.page.wait_for_function('expected=>navigator.clipboard.readText().then(t=>t===expected)',arg=selected)
        self.assertTrue(self.page.locator('#edit-layout.reading').is_visible())
        self.assertEqual(value(self.page),TEXT)

    def test_07_supplied_manual_reading_keeps_source_and_has_no_paragraph_frames(self):
        imported=self.import_manual();self.page.locator('[data-view=reading]').click()
        self.page.wait_for_selector('#edit-layout.reading')
        self.page.locator('#toc a').filter(has_text='顺手的几组按键').click()
        self.assertTrue(self.page.locator('#edit-layout.reading').is_visible())
        self.assertEqual(self.page.locator('#preview-content [data-block-editor]').count(),0)
        self.assertEqual(self.page.locator('#preview-content [contenteditable=true]').count(),0)
        colors=self.page.locator('#preview-content mark').evaluate_all('xs=>xs.map(e=>({text:e.textContent,color:getComputedStyle(e).backgroundColor}))')
        self.assertIn({'text':'🔴重要','color':'rgb(255, 215, 215)'},colors)
        self.assertIn({'text':'🟢进展','color':'rgb(216, 243, 220)'},colors)
        self.assertIn({'text':'🔵信息','color':'rgb(217, 234, 255)'},colors)
        self.page.locator('#color-theme').focus()
        self.assertEqual(value(self.page),imported)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'manual-reading.png'))

if __name__=='__main__':unittest.main()
