"""SEARCH-01: full source/preview search is independent of virtual viewport."""
import json, unittest
from browser_support import ManualService
from browser_support import source, value

TABLE={'schema':'report-table-v1','id':'tbl-search','caption':'唯一表题关键字',
       'rows':[[{'text':'参数','rowspan':1,'colspan':1},{'text':'说明','rowspan':1,'colspan':1}],
               [{'text':'遥远目标😀','rowspan':1,'colspan':1},{'text':'数值保留','rowspan':1,'colspan':1}]]}
TEXT=('# 内置查找\n\n## 起点\n\n遥远目标😀。跨节点**重点**。测试 [a.b] 和 CaseToken。\n\n'
      +'\n\n'.join('长文正文第%d段，保证匹配项不在初始屏幕。'%i for i in range(450))
      +'\n\n## 终点\n\n跨节点**重点**，casetoken。\n\n```report-table\n'
      +json.dumps(TABLE,ensure_ascii=False,indent=2)+'\n```\n')


class DocumentSearch(ManualService):
    def setUp(self):
        super().setUp();source(self.page,TEXT)
        self.page.wait_for_function("document.querySelector('#preview-content .report-table-wrap')!==null")

    def panel(self):return self.page.locator('#document-search')
    def query(self,text):
        self.page.locator('#search-query').fill(text)
        self.page.wait_for_timeout(180)

    def test_01_full_source_and_folded_object_are_located_without_changes(self):
        """Ctrl+F consumes the event and reaches a match inside a distant fold."""
        self.page.evaluate("document.querySelector('#markdown').sourceEditor.focus()")
        self.page.keyboard.press('Control+f')
        self.panel().wait_for(state='visible')
        self.assertEqual(self.page.locator('#search-scope').input_value(),'source')
        self.query('遥远目标😀')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='1 / 2'")
        self.page.keyboard.press('Enter')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='2 / 2'")
        self.page.wait_for_function("()=>{const e=document.querySelector('#markdown').sourceEditor;return e.value.slice(e.selectionStart,e.selectionEnd)==='遥远目标😀'&&e.selectionStart>10000}")
        self.assertIn('遥远目标😀',self.page.locator('.cm-content').inner_text())
        self.assertEqual(value(self.page),TEXT)
        self.page.keyboard.press('Shift+Enter')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='1 / 2'")
        self.page.keyboard.press('Escape');self.panel().wait_for(state='hidden')
        self.page.keyboard.press('F3');self.panel().wait_for(state='visible')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='2 / 2'")
        self.assertEqual(value(self.page),TEXT)

    def test_02_reading_search_spans_inline_nodes_and_ignores_caption_mirrors(self):
        """Reading stays reading; count excludes hidden caption/tool duplicates."""
        self.page.locator('[data-view=reading]').click()
        self.page.locator('#preview-content p').first.click()
        self.page.keyboard.press('Control+f');self.panel().wait_for(state='visible')
        self.assertEqual(self.page.locator('#search-scope').input_value(),'preview')
        self.query('跨节点重点')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='1 / 2'")
        self.page.keyboard.press('F3')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='2 / 2'")
        self.assertTrue(self.page.locator('#edit-layout').evaluate("e=>e.classList.contains('reading')"))
        self.assertGreater(self.page.locator('#preview-content').evaluate("e=>e.closest('.page-scroll').scrollTop"),1000)
        self.query('唯一表题关键字')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='1 / 1'")
        self.page.locator('#render-profile').select_option('engineering')
        self.page.wait_for_function("document.querySelector('#preview-content').dataset.hrsRenderProfile==='engineering'")
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='1 / 1'")
        self.assertEqual(value(self.page),TEXT)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'reading-search.png'))

    def test_03_literal_case_live_refresh_fallback_and_clean_export(self):
        """No regex inference, no source writes, no search UI in archive output."""
        self.page.locator('#btn-search').click();self.panel().wait_for(state='visible')
        self.page.locator('#search-scope').select_option('preview')
        self.query('[a.b]')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='1 / 1'")
        self.query('CaseToken')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='1 / 2'")
        self.page.locator('#search-case').check()
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='1 / 1'")
        self.page.evaluate('window.Highlight=undefined')
        self.query('数值保留')
        self.page.wait_for_function("document.querySelectorAll('.hrs-search-hit').length>0")
        self.page.set_viewport_size({'width':700,'height':900})
        self.assertLessEqual(self.panel().bounding_box()['x']+self.panel().bounding_box()['width'],701)
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        self.assertNotIn('hrs-search-hit',html);self.assertNotIn('id="document-search"',html)
        self.assertEqual(value(self.page),TEXT)
        source(self.page,'# 新稿\n\n## 内容\n\n没有之前的词。\n')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='0 / 0'")
        self.assertTrue(self.page.locator('#search-next').is_disabled())
        if self.evidence:self.page.screenshot(path=str(self.evidence/'narrow-no-results.png'))

    def test_04_scope_follows_keyboard_focus_and_fast_queries_do_not_reselect_old_ranges(self):
        """Tab/source focus, escaped punctuation, CRLF and rapid input stay literal."""
        self.page.locator('#preview-content p').first.click()
        self.page.evaluate("document.querySelector('#markdown').sourceEditor.focus()")
        self.page.keyboard.press('Control+f');self.panel().wait_for(state='visible')
        self.assertEqual(self.page.locator('#search-scope').input_value(),'source')
        self.page.locator('#search-query').fill('遥远目标😀')
        self.page.locator('#search-query').fill('[a.b]')
        self.page.wait_for_function("()=>{const e=document.querySelector('#markdown').sourceEditor;return e.value.slice(e.selectionStart,e.selectionEnd)==='[a.b]'}")
        self.assertEqual(value(self.page),TEXT)
        raw='# CRLF😀\r\n\r\n## 内容\r\n\r\n前文。😀特殊[点.] 后文\r\n'
        source(self.page,raw);self.query('😀特殊[点.]')
        self.page.wait_for_function("()=>{const e=document.querySelector('#markdown').sourceEditor;return e.value.slice(e.selectionStart,e.selectionEnd)==='😀特殊[点.]'}")
        self.assertEqual(value(self.page),raw)

    def test_05_search_remains_valid_after_applying_table_settings(self):
        """An open search bar must not hold old DOM ranges through table edits."""
        self.page.locator('#btn-search').click();self.page.locator('#search-scope').select_option('preview')
        self.query('唯一表题关键字')
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='1 / 1'")
        self.page.locator('#preview-content .report-table-wrap td').first.dblclick()
        self.page.get_by_role('button',name='所有列水平居中',exact=True).click()
        self.page.locator('#modal-ok').click()
        self.page.wait_for_function("[...document.querySelectorAll('#preview-content .structured-table td')].every(e=>getComputedStyle(e).textAlign==='center')")
        self.page.locator('#search-next').click()
        self.page.wait_for_function("document.querySelector('#search-count').textContent==='1 / 1'&&document.querySelectorAll('.hrs-search-hit').length>0")
        self.assertIn('"center"',value(self.page))
        self.assertIn('遥远目标😀',value(self.page))


if __name__=='__main__':unittest.main()
