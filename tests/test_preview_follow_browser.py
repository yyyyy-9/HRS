"""PREVIEW-FOLLOW/NOTE-CHECK: native input, real scroll, canonical tokens/map."""
import json
from browser_support import ManualService
from browser_support import source,value

class PreviewFollow(ManualService):
    def free(self,raw):
        source(self.page,raw);self.page.locator('#render-profile').select_option('free')
        self.page.wait_for_function("document.querySelector('#preview-content').dataset.hrsRenderProfile==='free'")

    def test_01_quote_single_lines_paragraphs_and_explicit_break_share_offline_style(self):
        raw='# 引用\r\n\r\n> s\r\n> x\r\n\r\n分段示例\r\n\r\n> 第一段\r\n>\r\n> 第二段\r\n\r\n硬换行示例\r\n\r\n> hard  \r\n> break\r\n'
        self.free(raw)
        measure="""root=>[...root.querySelectorAll('blockquote')].map(q=>({paragraphs:q.querySelectorAll('p').length,br:q.querySelectorAll('br').length,text:q.innerText,styles:[...q.querySelectorAll('p')].map(p=>({height:p.getBoundingClientRect().height,size:parseFloat(getComputedStyle(p).fontSize),line:parseFloat(getComputedStyle(p).lineHeight),margin:parseFloat(getComputedStyle(p).marginTop)}))}))"""
        self.page.wait_for_selector('#preview-content blockquote p')
        measured=self.page.locator('#preview-content').evaluate(measure)
        self.assertEqual([x['paragraphs'] for x in measured],[1,2,1])
        self.assertAlmostEqual(measured[0]['styles'][0]['line']/measured[0]['styles'][0]['size'],1.5,places=2)
        self.assertAlmostEqual(measured[1]['styles'][1]['margin']/measured[1]['styles'][1]['size'],.7,places=2)
        self.assertEqual(measured[2]['br'],1)
        self.assertLess(measured[2]['styles'][0]['height']/measured[2]['styles'][0]['line'],2.2)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'free-quote-spacing.png'))
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        path=self.folder/'quote.html';path.write_text(html,'utf8',newline='')
        reader=self.browser.new_page();reader.goto(path.as_uri())
        offline=reader.locator('main').evaluate(measure);reader.close()
        self.assertEqual([x['paragraphs'] for x in offline],[1,2,1])
        self.assertAlmostEqual(offline[0]['styles'][0]['line']/offline[0]['styles'][0]['size'],1.5,places=2)
        self.page.locator('#render-profile').select_option('engineering')
        self.page.wait_for_function("document.querySelector('#preview-content').dataset.hrsRenderProfile==='engineering'")
        self.assertNotAlmostEqual(self.page.locator('#preview-content blockquote p').first.evaluate('p=>parseFloat(getComputedStyle(p).lineHeight)/parseFloat(getComputedStyle(p).fontSize)'),1.5,places=2)
        self.assertEqual(value(self.page),raw)

    def test_02_duplicate_note_check_locates_real_definition_and_keeps_examples_literal(self):
        raw='# 重复脚注😀\r\n\r\n来源[^same]，再次[^same]。\r\n\r\n```md\r\n[^same]: 代码示例\r\n```\r\n\r\n`[^same]: 行内示例`\r\n\r\n[^same]: 第一条来源\r\n\r\n[^same]: 第二条来源\r\n'
        self.free(raw);self.page.locator('#btn-validate').click()
        errors=self.page.locator('#problem-list [data-code="DUPLICATE_FOOTNOTE"]')
        if errors.count()!=1:print('NOTE_DEBUG',self.page.locator('#problem-list').inner_text(),self.page.evaluate("()=>SourceMap.create(document.querySelector('#markdown').sourceEditor.value,marked.lexer(SourceBlocks.normalized(document.querySelector('#markdown').sourceEditor.value).text)).blocks.map(r=>({type:r.type,raw:r.raw,key:r.token.key,start:r.start,end:r.end}))"),flush=True)
        self.assertEqual(errors.count(),1)
        self.assertEqual(errors.first.get_attribute('data-severity'),'error')
        self.assertIn('第 13 行',errors.first.inner_text());self.assertIn('第 11 行',errors.first.inner_text())
        if self.evidence:self.page.screenshot(path=str(self.evidence/'duplicate-footnote-check.png'))
        errors.first.click();self.assertEqual(self.page.locator('#markdown').evaluate('n=>n.sourceEditor.selectionStart'),len(raw[:raw.index('[^same]: 第二条来源')].encode('utf-16-le'))//2)
        self.assertEqual(value(self.page),raw)
        self.free(raw.replace('[^same]: 第二条来源','[^other]: 第二条来源'))
        self.page.locator('#btn-validate').click();self.page.wait_for_function("document.querySelector('#problems-summary').textContent.startsWith('0 个错误')")
        self.assertEqual(self.page.locator('#problem-list [data-code="DUPLICATE_FOOTNOTE"]').count(),0)

    def long_source(self):
        raw='# 滚动编辑\n\n'+'\n\n'.join('## 第'+str(i)+'节\n\n段落'+str(i)+'，这里是需要保持位置的正文。'*14 for i in range(1,66))+'\n'
        self.free(raw);self.page.locator('#follow-scroll').check();return raw

    def preview_wheel(self,delta):
        self.page.locator('.page-scroll').hover();self.page.mouse.wheel(0,delta)

    def test_03_wheel_follow_keeps_running_with_editing_focus_and_source_changes(self):
        raw=self.long_source();target=self.page.locator('#preview-content [data-block-editor]').filter(has_text='段落1，').first
        target.dblclick();self.assertEqual(target.get_attribute('contenteditable'),'true')
        before=self.page.locator('.cm-scroller').evaluate('n=>n.scrollTop')
        self.preview_wheel(630)
        self.page.wait_for_function('before=>document.querySelector(".cm-scroller").scrollTop>before+100',arg=before,timeout=3000)
        self.assertTrue(self.page.evaluate('document.activeElement.isContentEditable'))
        self.page.keyboard.press('End');self.page.keyboard.insert_text('持续编辑测试')
        self.assertIn('持续编辑测试',value(self.page))
        before=self.page.locator('.cm-scroller').evaluate('n=>n.scrollTop');self.preview_wheel(680)
        self.page.wait_for_function('before=>document.querySelector(".cm-scroller").scrollTop>before+100',arg=before,timeout=3000)
        self.assertTrue(self.page.evaluate('document.activeElement.isContentEditable'))
        # Moving the other pane takes over as driver without losing the input.
        prev=self.page.locator('.page-scroll').evaluate('n=>n.scrollTop')
        self.page.locator('.cm-scroller').hover();self.page.mouse.wheel(0,710)
        self.page.wait_for_function('before=>document.querySelector(".page-scroll").scrollTop>before+60',arg=prev,timeout=3000)
        self.assertEqual(value(self.page).replace('持续编辑测试',''),raw)

    def test_04_disabled_follow_does_not_move_other_pane(self):
        self.long_source();target=self.page.locator('#preview-content [data-block-editor]').filter(has_text='段落1，').first
        target.dblclick();self.page.locator('#follow-scroll').uncheck();target.dblclick()
        before=self.page.locator('.cm-scroller').evaluate('n=>n.scrollTop');self.preview_wheel(700)
        self.page.wait_for_function('document.querySelector(".page-scroll").scrollTop>500')
        self.assertAlmostEqual(self.page.locator('.cm-scroller').evaluate('n=>n.scrollTop'),before,delta=2)
        self.assertTrue(self.page.evaluate('document.activeElement.isContentEditable'))

    def test_05_clicking_editable_text_preserves_precise_source_selection(self):
        raw='# 点击\n\n前段，**加粗位置**与中文😀末尾文字。\n'
        self.free(raw);target=self.page.locator('#preview-content [data-block-editor]').filter(has_text='前段，')
        strong=target.locator('strong');box=strong.bounding_box();self.page.mouse.dblclick(box['x']+box['width']/2,box['y']+box['height']/2)
        self.assertEqual(target.get_attribute('contenteditable'),'true')
        self.assertTrue(self.page.evaluate('document.querySelector("#preview-content [contenteditable=true]").contains(getSelection().anchorNode)'))
        selected=self.page.evaluate('getSelection().toString()');self.assertTrue(selected)
        self.assertIn(selected,'加粗位置')
        # Real mouse click after entering editing must not reset the source
        # caret to the beginning of the containing block.
        self.page.mouse.click(box['x']+box['width']-2,box['y']+box['height']/2)
        point=raw.index('加粗位置')+len('加粗位置')
        try:self.page.wait_for_function('point=>{const e=document.querySelector("#markdown").sourceEditor;return e.selectionStart===point&&e.selectionEnd===point}',arg=point,timeout=1500)
        except Exception:
            print('CLICK_DEBUG',self.page.evaluate("()=>({start:document.querySelector('#markdown').sourceEditor.selectionStart,end:document.querySelector('#markdown').sourceEditor.selectionEnd,node:getSelection().anchorNode?.nodeValue,offset:getSelection().anchorOffset,active:document.activeElement.outerHTML})"),flush=True);raise
        self.page.keyboard.insert_text('插入')
        self.assertIn('加粗位置插入',value(self.page));self.assertTrue(value(self.page).endswith('与中文😀末尾文字。\n'))

    def test_06_pending_composition_is_not_committed_by_scroll_then_follow_resumes(self):
        raw=self.long_source();target=self.page.locator('#preview-content [data-block-editor]').filter(has_text='段落1，').first
        target.dblclick();self.page.keyboard.press('End')
        target.evaluate("n=>n.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}))")
        self.page.keyboard.insert_text('输入法测试')
        self.assertEqual(value(self.page),raw)
        before=self.page.locator('.cm-scroller').evaluate('n=>n.scrollTop');self.preview_wheel(650)
        self.page.wait_for_function('document.querySelector(".page-scroll").scrollTop>500')
        self.assertAlmostEqual(self.page.locator('.cm-scroller').evaluate('n=>n.scrollTop'),before,delta=2)
        target.evaluate("n=>n.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'输入法测试'}))")
        self.assertIn('输入法测试',value(self.page));self.preview_wheel(650)
        self.page.wait_for_function('before=>document.querySelector(".cm-scroller").scrollTop>before+100',arg=before,timeout=3000)
        self.assertEqual(value(self.page).replace('输入法测试',''),raw)

if __name__=='__main__':
    import unittest
    unittest.main()
