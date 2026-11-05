"""PREVIEW-FOLLOW/NOTE-CHECK: native input, real scroll, canonical tokens/map."""
import json
from pathlib import Path
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
        self.assertGreaterEqual(measured[0]['styles'][0]['height']/measured[0]['styles'][0]['line'],1.9)
        self.assertLess(measured[2]['styles'][0]['height']/measured[2]['styles'][0]['line'],2.2)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'free-quote-spacing.png'))
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        path=self.folder/'quote.html';path.write_text(html,'utf8',newline='')
        reader=self.browser.new_page();reader.goto(path.as_uri())
        offline=reader.locator('main').evaluate(measure);reader.close()
        self.assertEqual([x['paragraphs'] for x in offline],[1,2,1])
        self.assertAlmostEqual(offline[0]['styles'][0]['line']/offline[0]['styles'][0]['size'],1.5,places=2)
        # MD-QUOTE-EXPORT-01: matching line-height is insufficient: the
        # standalone main must actually preserve the single source newline.
        self.assertGreaterEqual(offline[0]['styles'][0]['height']/offline[0]['styles'][0]['line'],1.9)
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
        raw=self.long_source()+'\n';source(self.page,raw)
        target=self.page.locator('#preview-content [data-block-editor]').filter(has_text='段落1，').first
        target.dblclick();self.page.keyboard.press('End')
        target.evaluate("n=>n.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}))")
        self.page.keyboard.insert_text('输入法测试')
        self.assertEqual(value(self.page),raw)
        # UX-2.5: an autosave/metadata reply during composition must not
        # replace the live editor DOM or consume the pending selection.
        self.page.wait_for_function("document.querySelector('#save-indicator').textContent.includes('草稿已备份')")
        self.assertEqual(value(self.page),raw)
        self.assertIn('输入法测试',target.inner_text())
        before=self.page.locator('.cm-scroller').evaluate('n=>n.scrollTop');self.preview_wheel(650)
        self.page.wait_for_function('document.querySelector(".page-scroll").scrollTop>500')
        self.assertAlmostEqual(self.page.locator('.cm-scroller').evaluate('n=>n.scrollTop'),before,delta=2)
        target.evaluate("n=>n.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'输入法测试'}))")
        self.assertIn('输入法测试',value(self.page));self.preview_wheel(650)
        self.page.wait_for_function('before=>document.querySelector(".cm-scroller").scrollTop>before+100',arg=before,timeout=3000)
        self.assertEqual(value(self.page).replace('输入法测试',''),raw)

    def test_07_unchanged_images_and_math_survive_text_edits_but_changed_content_refreshes(self):
        """RENDER-UX-01: reuse live leaves, never a stale source or asset URL."""
        picture=Path(__file__).parent/'fixtures/fp_hartmann/figures/synthetic-1.png'
        for name in ['reuse-a.png','reuse-b.png']:(self.project/'assets'/name).write_bytes(picture.read_bytes())
        raw='# 保留节点\n\n正文原样。\n\n![图](assets/reuse-a.png)\n\n公式 $x+1$。\n\n稳定公式 $k+3$。\n\n<!-- hrs:eq id=eq-stable -->\n\\[\na+b\n\\]\n\n- 稳定列表 $m+4$。\n- 后项。\n'
        self.free(raw);self.page.wait_for_function('document.querySelector("#preview-content img")?.complete && document.querySelector("#preview-content .markdown-math svg")')
        self.page.evaluate('window.uxLeaves=[document.querySelector("#preview-content img"),document.querySelector("#preview-content .markdown-math svg")]')
        self.page.evaluate('window.uxMathBlocks=[...document.querySelectorAll("#preview-content .doc-block")].filter(b=>b.textContent.includes("稳定公式")||b.querySelector(".report-equation")||b.dataset.type==="list")')
        measurements=[]
        for marker in ['甲','乙','丙']:
            source(self.page,raw.replace('正文原样。','正文'+marker+'。').replace('公式 $x+1$','公式'+marker+' $x+1$'))
            self.page.wait_for_function('s=>document.querySelector("#preview-content").textContent.includes(s)',arg='正文'+marker+'。')
            self.assertTrue(self.page.evaluate('uxLeaves[0]===document.querySelector("#preview-content img")'),'Unchanged picture was rebuilt')
            self.assertTrue(self.page.evaluate('uxLeaves[1]===document.querySelector("#preview-content .markdown-math svg")'),'Unchanged equation was rebuilt')
            self.assertTrue(self.page.evaluate('uxMathBlocks.every(b=>b.isConnected&&b._sourceDocument===document.querySelector("#markdown").sourceEditor.value)'),'Unchanged math blocks lost their current source binding')
            measurements.append(self.page.evaluate('document.querySelector("#preview-content")._hrsRenderStats'))
        if self.evidence:(self.evidence/'node-reuse.json').write_text(json.dumps({'browser':self.browser.version,'samples':measurements},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        source(self.page,raw.replace('reuse-a.png','reuse-b.png').replace('$x+1$','$y+2$'))
        self.page.wait_for_function('document.querySelector("#preview-content img")?.src.includes("reuse-b.png") && document.querySelector("#preview-content .markdown-math")?.dataset.tex==="y+2"')
        self.assertFalse(self.page.evaluate('uxLeaves[0]===document.querySelector("#preview-content img")'))
        self.assertFalse(self.page.evaluate('uxLeaves[1]===document.querySelector("#preview-content .markdown-math svg")'))
        # Offsets changed before a retained formula. Its editor must still write
        # only that formula, and the number display must invalidate reuse.
        self.page.locator('#preview-content .report-equation .markdown-math').dblclick()
        field=self.page.locator('[data-formula-source]');field.fill('a+c')
        self.page.locator('#modal-ok').click()
        self.page.wait_for_function('document.querySelector("#markdown").sourceEditor.value.includes("a+c")')
        self.assertIn('稳定公式 $k+3$',value(self.page))
        self.page.locator('#show-equation-numbers').check()
        self.page.wait_for_function('document.querySelector("#preview-content .equation-number")?.hidden===false')
        self.assertFalse(self.page.evaluate('uxMathBlocks[1].isConnected'))
        item=self.page.locator('#preview-content .list-inline-editor').filter(has_text='稳定列表')
        self.assertEqual(item.count(),1);item.dblclick();self.page.keyboard.press('End');self.page.keyboard.insert_text('追加')
        self.assertIn('稳定列表 $m+4$。追加',value(self.page))

    def test_08_indented_code_conversion_is_explicit_scoped_and_undoable(self):
        """INDENT-PROSE-01: change only the nominated top-level indented block."""
        code='\t正文😀。\r\n    第二行。\r\n'
        raw='# 缩进\r\n\r\n'+code+'\r\n```text\r\n    围栏代码\r\n```\r\n\r\n- 项目\r\n\r\n    列表续段。\r\n\r\n说明[^n]\r\n\r\n[^n]: 注释\r\n    脚注续行。\r\n'
        self.free(raw);self.page.wait_for_selector('#preview-content .hrs-code-panel')
        button=self.page.locator('#preview-content .hrs-code-to-prose')
        self.assertEqual(button.count(),1)
        self.assertEqual(button.locator('..').locator('.hrs-code-language').inner_text(),'缩进代码块')
        self.assertIn('4 个空格',button.locator('..').get_attribute('title'))
        self.assertEqual(value(self.page),raw)
        button.click();expected=raw.replace(code,'正文😀。\r\n第二行。\r\n',1)
        self.assertEqual(value(self.page),expected)
        self.page.locator('#markdown').evaluate('n=>n.sourceEditor.focus()');self.page.keyboard.press('Control+z')
        self.assertEqual(value(self.page),raw)
        self.page.keyboard.press('Control+Shift+z');self.assertEqual(value(self.page),expected)
        source(self.page,raw);self.page.wait_for_selector('#preview-content .hrs-code-to-prose')
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        self.assertIn('缩进代码块',html);self.assertNotIn('hrs-code-to-prose',html)
        self.page.wait_for_function('document.querySelector(".cm-note-definition")?.textContent.includes("[^n]")')
        if self.evidence:self.page.screenshot(path=str(self.evidence/'indented-code-action.png'))

    def test_09_preview_copy_markdown_in_split_reading_and_legacy_clipboard(self):
        """RENDER-UX-01: source copy is explicit and works without modern clipboard."""
        paragraph='前段😀，**加粗 $x+1$** 与 [链接](https://example.com)。'
        raw='# 复制\r\n\r\n'+paragraph+'\r\n\r\n后段。\r\n'
        self.free(raw);self.page.context.grant_permissions(['clipboard-read','clipboard-write'])
        def select_paragraph():
            self.page.locator('#preview-content p').filter(has_text='前段😀').evaluate('p=>{const r=document.createRange();r.selectNodeContents(p);getSelection().removeAllRanges();getSelection().addRange(r);document.dispatchEvent(new Event("selectionchange"));}')
        for reading,legacy in [(False,False),(True,False),(True,True)]:
            if reading:self.page.get_by_role('button',name='阅读',exact=True).click()
            if legacy:self.page.evaluate('()=>{window.savedUXClipboard=navigator.clipboard;Object.defineProperty(navigator,"clipboard",{value:undefined,configurable:true});}')
            select_paragraph();button=self.page.locator('#btn-preview-copy-markdown')
            self.assertEqual(button.count(),1);button.wait_for(state='visible')
            button.click()
            self.page.wait_for_function('expected=>(window.savedUXClipboard||navigator.clipboard).readText().then(value=>value===expected)',arg=paragraph)
            self.assertEqual(value(self.page),raw)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'preview-copy-markdown.png'))

    def test_10_reused_prose_binds_editing_handlers_once(self):
        """RENDER-UX-01: repeated commits must not multiply Enter handlers."""
        raw='# 事件\n\n稳定正文。\n\n后段0。\n';self.free(raw)
        for i in range(1,5):
            source(self.page,raw.replace('后段0。','后段'+str(i)+'。'))
            self.page.wait_for_function('text=>document.querySelector("#preview-content").textContent.includes(text)',arg='后段'+str(i)+'。')
        target=self.page.locator('#preview-content [data-block-editor]').filter(has_text='稳定正文。')
        target.dblclick();self.page.keyboard.press('End');self.page.keyboard.press('Enter');self.page.keyboard.insert_text('新行')
        body=value(self.page).split('稳定正文。',1)[1].split('后段',1)[0]
        self.assertEqual(body,'\n新行\n\n')

    def test_11_complex_preview_copy_uses_existing_resource_bundle(self):
        """RENDER-UX-01: a figure selection copies its whole source and assets."""
        picture=Path(__file__).parent/'fixtures/fp_hartmann/figures/synthetic-1.png'
        (self.project/'assets/copy-source.png').write_bytes(picture.read_bytes())
        raw='# 资源复制\n\n![资源](assets/copy-source.png)\n\n后段保留。\n'
        self.free(raw);self.page.context.grant_permissions(['clipboard-read','clipboard-write'])
        self.page.wait_for_selector('#preview-content img')
        expected=self.page.locator('#preview-content img').evaluate('img=>{const block=img.closest(".doc-block"),r=document.createRange();r.selectNodeContents(block);getSelection().removeAllRanges();getSelection().addRange(r);document.dispatchEvent(new Event("selectionchange"));return block._sourceRaw;}')
        button=self.page.locator('#btn-preview-copy-markdown');button.wait_for(state='visible')
        self.assertEqual(button.inner_text(),'复制整块 Markdown');button.click()
        self.page.wait_for_function('document.querySelector("#toast").textContent.includes("已复制 Markdown")')
        # Consume the actual native paste formats, including on old Chromium
        # where clipboard.read() rejects HTML that ClipboardEvent can expose.
        self.page.evaluate('''()=>{
          window.uxPasted=null;window.uxPasteReceived=false;
          function receive(event){
            window.uxPasteReceived=true;
            window.uxPasted=ReportObjectClipboard.parse(event.clipboardData.getData('text/html'),event.clipboardData.getData('text/plain'));
            event.preventDefault();event.stopImmediatePropagation();document.removeEventListener('paste',receive,true);
          }
          document.addEventListener('paste',receive,true);document.querySelector('#markdown').sourceEditor.focus();
        }''')
        self.page.keyboard.press('Control+v');self.page.wait_for_function('window.uxPasteReceived')
        self.assertTrue(self.page.evaluate('!!window.uxPasted'),'Native paste did not carry the HRS resource bundle')
        self.assertEqual(self.page.evaluate('uxPasted.markdown'),expected)
        self.assertTrue(self.page.evaluate('Object.keys(uxPasted.assets).length>0'))
        self.assertEqual(value(self.page),raw)

    def test_12_resource_reuse_survives_new_blocks_and_palette_but_not_mode_change(self):
        """RENDER-UX-01: changed offsets keep fresh wrappers and display ownership."""
        picture=Path(__file__).parent/'fixtures/fp_hartmann/figures/synthetic-1.png'
        (self.project/'assets/context.png').write_bytes(picture.read_bytes())
        raw='# 上下文\n\n![图片](assets/context.png)\n\n$\\alpha+1$\n'
        self.free(raw);self.page.wait_for_function('document.querySelector("#preview-content img")?.complete && document.querySelector("#preview-content .markdown-math svg")')
        self.page.evaluate('window.contextLeaves=[document.querySelector("#preview-content img"),document.querySelector("#preview-content .markdown-math svg")]')
        updated=raw.replace('![图片]','前插段落。\n\n![图片]');source(self.page,updated)
        self.page.wait_for_function('document.querySelector("#preview-content").textContent.includes("前插段落")')
        self.assertTrue(self.page.evaluate('contextLeaves[0]===document.querySelector("#preview-content img") && contextLeaves[1]===document.querySelector("#preview-content .markdown-math svg")'))
        self.page.locator('#color-theme').select_option('celadon')
        self.page.wait_for_function('document.documentElement.dataset.colorTheme==="celadon"')
        self.assertTrue(self.page.evaluate('contextLeaves[0]===document.querySelector("#preview-content img")'))
        self.assertEqual(value(self.page),updated)
        self.page.locator('#render-profile').select_option('engineering')
        self.page.wait_for_function('document.querySelector("#preview-content").dataset.hrsRenderProfile==="engineering"')
        self.assertFalse(self.page.evaluate('contextLeaves[0]===document.querySelector("#preview-content img")'))
        self.assertEqual(value(self.page),updated)

    def test_13_preview_source_copy_keeps_plain_offsets_and_complete_inline_syntax(self):
        """RENDER-UX-01: never copy half of an emphasis/link delimiter pair."""
        paragraph='普通😀前文，**加粗文字**和尾部。'
        raw='# 选区\n\n'+paragraph+'\n\n后段。\n'
        self.free(raw);self.page.context.grant_permissions(['clipboard-read','clipboard-write'])
        target=self.page.locator('#preview-content p').filter(has_text='普通😀')
        def copy_selected(expression,label,expected):
            target.evaluate('p=>{'+expression+';getSelection().removeAllRanges();getSelection().addRange(r);document.dispatchEvent(new Event("selectionchange"));}')
            button=self.page.locator('#btn-preview-copy-markdown');button.wait_for(state='visible')
            self.assertEqual(button.inner_text(),label);button.click()
            self.page.wait_for_function('expected=>navigator.clipboard.readText().then(value=>value===expected)',arg=expected)
        copy_selected('const n=p.firstChild,r=document.createRange(),a=n.nodeValue.indexOf("前文");r.setStart(n,a);r.setEnd(n,a+2)',
                      '复制 Markdown','前文')
        copy_selected('const n=p.querySelector("strong").firstChild,r=document.createRange();r.setStart(n,1);r.setEnd(n,3)',
                      '复制整块 Markdown',paragraph)
        self.assertEqual(value(self.page),raw)

if __name__=='__main__':
    import unittest
    unittest.main()
