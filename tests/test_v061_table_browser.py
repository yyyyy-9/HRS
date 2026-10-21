"""TABLE-01: padding/minimum rows shared by editor and offline output."""
import json,unittest
from browser_support import ManualService
from test_pf1310_rc2_browser import source

EMPTY={'schema':'report-table-v1','id':'tbl-empty','caption':'22','rows':[[{'text':'','rowspan':1,'colspan':1} for _ in range(3)] for _ in range(4)]}
TEXT={'schema':'report-table-v1','id':'tbl-long','caption':'材料说明','rows':[[{'text':'第一行\n第二行\n第三行','rowspan':1,'colspan':1},{'text':'保留完整内容','rowspan':1,'colspan':1}]]}
MARKDOWN='# 表格效果\n\n| 一点灵感 | 下一步 | 状态 |\n|---|---|---|\n| 一篇旅行随笔 | 放入沿途照片 | 正在写 |\n| 一个小工具 | 画出实现流程 | 待开始 |\n| 今天的你 | 改改这一格 | 出发 |\n\n'
for obj in (EMPTY,TEXT):MARKDOWN+='```report-table\n'+json.dumps(obj,ensure_ascii=False,indent=2)+'\n```\n\n'

MEASURE='''article=>[...article.querySelectorAll('.report-table-wrap')].map(w=>{
 const t=w.querySelector('.hrs-table-tools'),k=t.querySelector('.hrs-table-kind'),r=w.getBoundingClientRect(),kr=k.getBoundingClientRect();
 return {label:k.textContent,inset:kr.left-r.left,align:getComputedStyle(k).textAlign,toolbar:t.getBoundingClientRect().height,
 rows:[...w.querySelectorAll('table tr')].map(x=>x.getBoundingClientRect().height),
 menu_inside:!t.querySelector('.hrs-table-menu')||t.querySelector('.hrs-table-menu').getBoundingClientRect().right<=r.right};})'''

class TableLayout(ManualService):
    def setup_tables(self,profile):
        source(self.page,MARKDOWN);self.page.locator('#render-profile').select_option(profile)
        self.page.wait_for_function("document.querySelectorAll('#preview-content .report-table-wrap').length===3")
        self.page.wait_for_function('p=>document.querySelector("#preview-content .hrs-table-tools").classList.contains("hrs-table-mini")===(p==="free")',arg=profile)
    def assert_rows(self,items):
        self.assertEqual(len(items),3)
        for table in items[:2]:
            self.assertTrue(all(31.5<=h<=34 for h in table['rows']),table)
        self.assertGreater(items[2]['rows'][0],50)
    def test_01_free_titles_are_inset_and_empty_rows_have_writing_space(self):
        self.setup_tables('free');items=self.page.locator('#preview-content').evaluate(MEASURE);self.assert_rows(items)
        for table in items:
            self.assertTrue(12<=table['inset']<=16,table);self.assertEqual(table['align'],'left')
            self.assertTrue(25<=table['toolbar']<=28,table);self.assertTrue(table['menu_inside'],table)
    def test_02_engineering_toolbar_is_compact_and_rows_can_grow(self):
        self.setup_tables('engineering');items=self.page.locator('#preview-content').evaluate(MEASURE);self.assert_rows(items)
        for table in items:self.assertTrue(29<=table['toolbar']<=33,table)
    def test_03_offline_uses_same_table_spacing_without_source_changes(self):
        self.setup_tables('free')
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        file=self.folder/'table.html';file.write_bytes(html.encode('utf8'))
        reader=self.browser.new_page();reader.goto(file.as_uri());items=reader.locator('main').evaluate(MEASURE)
        self.assert_rows(items)
        for table in items:self.assertTrue(12<=table['inset']<=16,table)
        reader.close()

if __name__=='__main__':unittest.main()
