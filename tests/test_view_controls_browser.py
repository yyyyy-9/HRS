"""VIEW-UX-01: view controls change presentation without editing the document."""
from pathlib import Path
import re
from browser_support import ManualService,source,value,fold_source,LiveDocument


class ViewControls(ManualService):
    def test_08_fold_toggle_tracks_individual_actions_and_visible_topic(self):
        table='| 表头 |\n| --- |\n| 内容 |\n'
        raw='# 第一专题\n\n'+table+'\n'+table.replace('表头','另表')+'\n# 第二专题\n\n'+table+'\n# 无对象\n\n正文\n'
        self.page.locator('#render-profile').select_option('free');self.free(raw)
        button=self.page.locator('#btn-source-fold')
        fold_source(self.page)
        self.page.wait_for_function('document.querySelector("#btn-source-fold").dataset.foldState==="collapsed"')
        button.click();self.assertEqual(button.inner_text(),'折叠')
        self.assertEqual(self.page.locator('.source-fold-summary').count(),0)
        button.click();self.assertEqual(button.inner_text(),'展开')
        self.page.locator('.source-fold-summary').first.get_by_role('button',name='展开',exact=True).click()
        self.assertEqual(button.get_attribute('data-fold-state'),'mixed');self.assertEqual(button.inner_text(),'折叠')
        button.click();self.assertEqual(button.inner_text(),'展开')
        self.page.locator('#topic-select').select_option(label='2 · 第二专题')
        self.page.wait_for_function('document.querySelectorAll("#preview-content .report-table-wrap").length===1')
        button.click();self.assertEqual(button.inner_text(),'折叠')
        self.page.locator('#topic-select').select_option(label='1 · 第一专题')
        self.page.wait_for_function('document.querySelectorAll("#preview-content .report-table-wrap").length===2')
        self.assertEqual(button.inner_text(),'展开','Other topics stay folded')
        self.page.locator('#topic-select').select_option(label='3 · 无对象')
        self.page.wait_for_function('document.querySelector("#btn-source-fold").disabled')
        self.page.locator('#topic-select').select_option('')
        self.assertEqual(button.inner_text(),'折叠');self.assertEqual(value(self.page),raw)
        self.free('# 新稿\n\n正文\n');self.assertTrue(button.is_disabled())

    def test_01_shared_controls_are_available_without_topic_mode(self):
        self.page.locator('#render-profile').select_option('engineering')
        self.page.wait_for_function('document.body.dataset.renderProfile==="engineering"')
        self.assertTrue(self.page.locator('#source-wrap').is_visible())
        self.assertTrue(self.page.locator('#source-font-increase').is_visible())
        self.assertTrue(self.page.locator('#preview-zoom').is_visible())
        self.assertTrue(self.page.locator('#btn-source-fold').is_visible())
        self.assertEqual(self.page.locator('#source-fold-menu,.side-card,.local-dot').count(),0)
        self.assertNotIn('工作台',self.page.locator('.sidebar').inner_text())
        self.assertLess(self.page.locator('.recent-section').bounding_box()['y'],110)

    def free(self,raw):
        source(self.page,raw)
        self.page.wait_for_function('raw=>document.querySelector("#preview-content .doc-block")?._sourceDocument===raw',arg=raw)

    def font_at(self,needle):
        self.page.evaluate('needle=>{const e=document.querySelector("#markdown").sourceEditor;e.view.dispatch({selection:{anchor:e.value.indexOf(needle)},scrollIntoView:true});}',needle)
        self.page.wait_for_function('needle=>[...document.querySelectorAll(".cm-line")].some(n=>n.textContent.includes(needle))',arg=needle)
        return self.page.evaluate('needle=>{const n=[...document.querySelectorAll(".cm-line")].find(n=>n.textContent.includes(needle));return {size:parseFloat(getComputedStyle(n).fontSize),fixed:n.classList.contains("cm-source-fixed-size")};}',needle)

    def test_02_font_changes_only_prose_and_headings_and_preserves_objects(self):
        raw='# 一级标题\r\n\r\n正文与中文😀。\r\n\r\n'
        raw+='\r\n\r\n'.join('#'*level+' 第'+str(level)+'级标题' for level in range(2,7))+'\r\n\r\n'
        raw+='```text\r\n围栏内容\r\n```\r\n\r\n    缩进代码\r\n\r\n<div>\r\nHTML内容\r\n</div>\r\n\r\n'
        raw+='| 表头固定 |\r\n| --- |\r\n| 表格固定 |\r\n\r\n$$\r\nx_{fixed}=1\r\n$$\r\n\r\n'
        raw+='- [ ] 正常任务\r\n\r\n    ```text\r\n    嵌套代码\r\n    ```\r\n\r\n末段正文。\r\n'
        self.free(raw);fold_source(self.page,expand=True)
        before={needle:self.font_at(needle) for needle in ('# 一级标题','正文与中文','围栏内容','缩进代码','HTML内容','表格固定','x_{fixed}','嵌套代码')}
        for _ in range(4):self.page.locator('#source-font-increase').click()
        self.assertEqual(self.page.locator('#source-font-value').inner_text(),'17px')
        self.assertAlmostEqual(self.font_at('正文与中文')['size'],17,delta=.05)
        self.assertAlmostEqual(self.font_at('# 一级标题')['size']/before['# 一级标题']['size'],17/13,delta=.02)
        for level,factor in ((2,1.28),(3,1.16),(4,1.08),(5,1.02),(6,1)):
            self.assertAlmostEqual(self.font_at('第'+str(level)+'级标题')['size'],17*factor,delta=.05)
        for needle in ('围栏内容','缩进代码','HTML内容','表格固定','x_{fixed}','嵌套代码'):
            actual=self.font_at(needle);self.assertTrue(actual['fixed'],needle);self.assertAlmostEqual(actual['size'],13,delta=.05,msg=needle)
        self.assertFalse(self.font_at('正常任务')['fixed'])
        self.assertAlmostEqual(self.page.locator('.cm-gutters').evaluate('n=>parseFloat(getComputedStyle(n).fontSize)'),13,delta=.05)
        fold_source(self.page)
        self.assertAlmostEqual(self.page.locator('.source-fold-summary').first.evaluate('n=>parseFloat(getComputedStyle(n).fontSize)'),12,delta=.05)
        self.assertEqual(value(self.page),raw)
        rows=self.page.locator('.cm-lineNumbers .cm-gutterElement').evaluate_all('xs=>xs.filter(n=>getComputedStyle(n).visibility!=="hidden").map(n=>({text:n.textContent,top:n.getBoundingClientRect().top,bottom:n.getBoundingClientRect().bottom}))')
        for previous,current in zip(rows,rows[1:]):self.assertGreaterEqual(current['top'],previous['bottom']-.5,(previous,current))
        if self.evidence:self.page.screenshot(path=str(self.evidence/'source-font-17.png'))

    def test_03_zoom_preserves_layout_leaves_export_and_reading(self):
        picture=Path(__file__).parent/'fixtures/fp_hartmann/figures/synthetic-1.png'
        (self.project/'assets/view.png').write_bytes(picture.read_bytes())
        raw='# 放大预览\n\n段落原文。\n\n![图片](assets/view.png)\n\n公式 $x+1$。\n\n'+''.join('段落'+str(i)+'，用于核对缩放与滚动。\n\n' for i in range(70))
        self.free(raw);self.page.wait_for_function('document.querySelector("#preview-content img")?.complete&&document.querySelector("#preview-content .markdown-math svg")')
        self.page.evaluate('window.viewLeaves=[document.querySelector("#preview-content img"),document.querySelector("#preview-content .markdown-math svg")]')
        width=self.page.locator('#preview-content').evaluate('n=>n.offsetWidth')
        self.assertTrue(self.page.locator('#preview-zoom-decrease').is_disabled())
        self.page.locator('#preview-zoom-increase').click();self.assertEqual(self.page.locator('#preview-zoom').input_value(),'125')
        self.page.locator('#preview-zoom-decrease').click();self.assertEqual(self.page.locator('#preview-zoom').input_value(),'100')
        reader=self.browser.new_page()
        reader.set_content(self.page.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})'))
        exported_size=reader.locator('[data-hrs-reader-root]').evaluate('n=>getComputedStyle(n).fontSize')
        reader.close()
        for zoom in (100,125,150,175,200):
            self.page.locator('#preview-zoom').select_option(str(zoom))
            self.page.wait_for_function('z=>Math.abs(document.querySelector("#preview-content").getBoundingClientRect().width/document.querySelector("#preview-content").offsetWidth-z/100)<.01',arg=zoom)
            self.assertAlmostEqual(self.page.locator('#preview-content').evaluate('n=>n.offsetWidth'),width,delta=1)
            self.assertTrue(self.page.evaluate('viewLeaves[0]===document.querySelector("#preview-content img")&&viewLeaves[1]===document.querySelector("#preview-content .markdown-math svg")'))
            size=self.page.evaluate('()=>{const c=document.querySelector("#preview-scale-content"),s=document.querySelector("#preview-scale-stage");return [c.offsetHeight,s.offsetHeight]}')
            self.assertAlmostEqual(size[1],size[0]*zoom/100,delta=1)
        self.assertTrue(self.page.locator('.page-scroll').evaluate('n=>n.scrollWidth>n.clientWidth+100'))
        self.assertTrue(self.page.locator('#preview-zoom-increase').is_disabled())
        self.page.locator('[data-view="reading"]').click()
        self.page.wait_for_function('document.querySelector("#edit-layout").classList.contains("reading")')
        self.assertEqual(self.page.locator('#preview-zoom').input_value(),'200')
        self.page.locator('#toc a').first.click()
        heading=self.page.locator('#preview-content h1');box=heading.bounding_box()
        self.assertTrue(self.page.evaluate('p=>!!document.elementFromPoint(p.x,p.y)?.closest("h1")',{'x':box['x']+10,'y':box['y']+10}))
        html=self.page.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})')
        self.assertFalse(re.search(r'<[^>]+id=[\"\x27]preview-scale-',html))
        reader=self.browser.new_page();reader.set_content(html)
        self.assertEqual(reader.locator('[data-hrs-reader-root]').evaluate('n=>getComputedStyle(n).transform'),'none')
        self.assertEqual(reader.locator('[data-hrs-reader-root]').evaluate('n=>getComputedStyle(n).fontSize'),exported_size)
        reader.close();self.assertEqual(value(self.page),raw)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'reading-200.png'))
        self.page.emulate_media(media='print')
        self.assertEqual(self.page.locator('#preview-scale-content').evaluate('n=>getComputedStyle(n).transform'),'none')
        self.assertEqual(self.page.locator('#preview-scale-content').evaluate('n=>getComputedStyle(n).position'),'static')
        self.page.emulate_media(media='screen')

    def test_04_legacy_preferences_migrate_and_view_settings_survive_reload(self):
        seed='localStorage.setItem("hrs-source-wrap","false");localStorage.setItem("hrs-source-ratio","62")'
        with LiveDocument(self.browser,self.folder/'legacy-view',init_script=seed) as document:
            page=document.page
            self.assertFalse(page.locator('#source-wrap').is_checked())
            self.assertEqual(page.locator('#split-divider').get_attribute('aria-valuenow'),'62')
            page.locator('#source-font-increase').click();page.locator('#preview-zoom').select_option('175')
            stored=page.evaluate('JSON.parse(localStorage.getItem(ReportSettings.view_options.storage_key))')
            self.assertEqual(stored,{'source_font_size':14,'source_wrap':False,'source_ratio':62,'preview_zoom':175})
            page.reload();page.wait_for_function('typeof ReportStudioProgrammatic!=="undefined"')
            page.evaluate('()=>ReportStudioProgrammatic.ready()')
            self.assertEqual(page.locator('#source-font-value').inner_text(),'14px')
            self.assertEqual(page.locator('#preview-zoom').input_value(),'175')
            self.assertFalse(page.locator('#source-wrap').is_checked())
            self.assertFalse(document.errors)

    def test_05_zoom_follow_reaches_tail_and_header_buttons_are_not_covered(self):
        raw='# 滚动\n\n'+''.join('## 标题'+str(i)+'\n\n正文'+str(i)+'，滚动和点击。\n\n' for i in range(60))
        self.free(raw);self.page.locator('#preview-zoom').select_option('150');self.page.locator('#follow-scroll').check()
        self.page.locator('.page-scroll').hover();self.page.mouse.wheel(0,850)
        self.page.wait_for_function('document.querySelector(".cm-scroller").scrollTop>100')
        self.page.locator('#toc a').last.click()
        self.page.wait_for_function('document.querySelector("#preview-content .navigation-highlight")')
        box=self.page.locator('#preview-content .navigation-highlight').bounding_box();scroll=self.page.locator('.page-scroll').bounding_box()
        self.assertLess(box['y'],scroll['y']+scroll['height']);self.assertGreater(box['y']+box['height'],scroll['y'])
        self.assertTrue(self.page.locator('.page-scroll').evaluate('n=>n.scrollHeight-n.scrollTop<n.clientHeight+250'))
        for width in (1600,1000):
            self.page.set_viewport_size({'width':width,'height':900})
            self.page.locator('#btn-snippets').click();self.page.locator('#modal-cancel').click()
            centers=self.page.evaluate('()=>["#btn-snippets","#btn-source-fold","#source-font-increase"].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return r.top+r.height/2})')
            self.assertLess(max(centers)-min(centers),2)
        self.assertEqual(value(self.page),raw)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'source-header-narrow.png'))

    def test_06_scaled_object_hit_targets_and_roundtrip_anchor_are_stable(self):
        """VIEW-UX-01: real object editing stays unscaled and repeated zoom does not drift."""
        raw='# 缩放交互\n\n'+''.join('段落'+str(i)+'，核对源和显示位置。\n\n' for i in range(45))
        raw+='## 对象 {#sec-tools}\n\n$$\nx=1\n$$\n\n| 列 |\n| --- |\n| 内容 |\n\n'
        raw+=''.join('后文'+str(i)+'。\n\n' for i in range(35));self.free(raw)
        self.page.locator('#toc a').filter(has_text='对象').click()
        self.page.wait_for_function('document.querySelector("#preview-content .navigation-highlight")')
        position=self.page.locator('.page-scroll').evaluate('n=>n.scrollTop')
        for _ in range(10):
            self.page.locator('#preview-zoom').select_option('200')
            self.page.locator('#preview-zoom').select_option('100')
        self.assertAlmostEqual(self.page.locator('.page-scroll').evaluate('n=>n.scrollTop'),position,delta=2)
        self.page.locator('#preview-zoom').select_option('200')
        self.page.locator('#preview-content .math-display').dblclick()
        self.page.locator('math-field[data-ready="1"]').wait_for()
        self.assertAlmostEqual(self.page.locator('.modal-window').evaluate('n=>n.getBoundingClientRect().width/n.offsetWidth'),1,delta=.01)
        self.page.locator('#modal-cancel').click()
        self.page.locator('#preview-content .report-table-wrap').dblclick()
        self.assertTrue(self.page.locator('#modal-layer').is_visible())
        self.assertAlmostEqual(self.page.locator('.modal-window').evaluate('n=>n.getBoundingClientRect().width/n.offsetWidth'),1,delta=.01)
        self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)
        self.page.locator('#follow-scroll').check()
        source_scroller=self.page.locator('.cm-scroller');source_scroller.hover()
        self.page.mouse.wheel(0,-5000)
        self.page.wait_for_function('document.querySelector(".page-scroll").scrollTop<200')

    def test_07_storage_denied_still_allows_view_changes_and_source_undo(self):
        """VIEW-UX-01: storage restrictions retain in-memory controls, not document settings."""
        seed='for(const name of ["getItem","setItem","removeItem"])Storage.prototype[name]=()=>{throw new DOMException("blocked","SecurityError")} '
        with LiveDocument(self.browser,self.folder/'blocked-view',init_script=seed) as document:
            page=document.page;raw=value(page)
            page.locator('#markdown').evaluate('n=>{const e=n.sourceEditor;e.setSelectionRange(e.value.length,e.value.length);e.focus()}')
            page.keyboard.type('view-marker')
            page.locator('#source-font-increase').click();page.locator('#preview-zoom-increase').click()
            self.assertEqual(page.locator('#source-font-value').inner_text(),'14px')
            self.assertEqual(page.locator('#preview-zoom').input_value(),'125')
            page.locator('#markdown').evaluate('n=>n.sourceEditor.focus()');page.keyboard.press('Control+z')
            self.assertEqual(value(page),raw);self.assertFalse(document.errors)


if __name__=='__main__':
    import unittest
    unittest.main()
