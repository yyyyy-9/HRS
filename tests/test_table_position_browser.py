"""TABLE-03: applying settings keeps the edited table in the same viewport."""
import json, unittest
from browser_support import ManualService
from browser_support import source, value

UPSTREAM = '\n\n'.join(
    '### 光路 %d\n\n```mermaid\nflowchart TB\n A[光源] --> B[整形] --> C[检测]\n```\n\n说明文字。' % i
    for i in range(1, 9))
PIPE = '| 项目 | 说明 |\n| --- | --- |\n| 检测 | 保留原值 |\n'
ENHANCED = '```report-table\n' + json.dumps({
    'schema':'report-table-v1', 'id':'tbl-position', 'caption':'目标表格',
    'rows':[[{'text':x,'rowspan':1,'colspan':1} for x in row]
            for row in [['项目','说明'],['检测','保留原值']]]
}, ensure_ascii=False) + '\n```\n'


class TablePosition(ManualService):
    def position(self):
        return self.page.locator('#preview-content .report-table-wrap').evaluate('''e=>{
            const s=e.closest('.page-scroll');return {
                top:e.getBoundingClientRect().top-s.getBoundingClientRect().top,
                scroll:s.scrollTop, source:document.querySelector('#markdown').sourceEditor.scrollTop};
        }''')

    def test_apply_settings_stays_at_table_after_diagrams_in_both_views(self):
        """Render completion, including upstream diagrams, must precede anchoring."""
        for view, table in [('split', PIPE), ('reading', ENHANCED)]:
            with self.subTest(view=view):
                raw='# 长文表格定位\n\n## 光路\n\n'+UPSTREAM+'\n\n## 测量\n\n'+table+'\n\n'+'尾部正文。\n\n'*40
                self.page.locator('[data-view="'+view+'"]').click()
                self.page.locator('#render-profile').select_option('engineering' if view=='split' else 'free')
                if view=='split':self.page.locator('#follow-scroll').check()
                source(self.page, raw)
                self.page.wait_for_function("md=>document.querySelector('#preview-content .doc-block')?._sourceDocument===md",arg=raw)
                self.page.wait_for_function("document.querySelectorAll('#preview-content .mermaid-card svg').length===8")
                self.page.wait_for_timeout(300)
                wrap=self.page.locator('#preview-content .report-table-wrap')
                wrap.evaluate("e=>{const s=e.closest('.page-scroll');s.scrollTop+=e.getBoundingClientRect().top-s.getBoundingClientRect().top-150}")
                self.page.wait_for_timeout(350)
                before=self.position()
                self.assertTrue(140<=before['top']<=160,before)
                wrap.locator('td').first.dblclick()
                opened=self.position()
                self.page.get_by_role('button', name='所有列水平居中', exact=True).click()
                self.page.locator('#modal-ok').click()
                self.page.wait_for_function("[...document.querySelectorAll('#preview-content .structured-table td')].every(e=>getComputedStyle(e).textAlign==='center')")
                self.page.wait_for_function("document.querySelectorAll('#preview-content .mermaid-card svg').length===8")
                self.page.wait_for_timeout(700)
                after=self.position()
                if self.evidence:
                    (self.evidence/(view+'.json')).write_text(json.dumps({'before':before,'opened':opened,'after':after},indent=2),encoding='utf8')
                    self.page.screenshot(path=str(self.evidence/(view+'.png')))
                self.assertLess(abs(after['top']-before['top']),4,(view,before,after))
                self.assertIn('保留原值',value(self.page))


if __name__=='__main__':unittest.main()
