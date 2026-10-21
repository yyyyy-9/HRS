"""CORE-01/PERF-01: actual catalog consumers and bounded live-map cache."""
import json
from pathlib import Path
from browser_support import ManualService
from browser_support import source,value


class CoreBrowser(ManualService):
    def test_01_choice_labels_and_stylesheets_come_from_the_catalog(self):
        data=json.loads((Path(__file__).resolve().parents[1]/'app/product_settings.json').read_text('utf8'))
        for key,control in [('color_themes','#color-theme'),('render_profiles','#render-profile')]:
            options=self.page.locator(control+' option').evaluate_all('xs=>xs.map(x=>({id:x.value,label:x.textContent}))')
            self.assertEqual(options,[{'id':item['id'],'label':item['label']} for item in data[key]['choices']])
        self.assertTrue(self.page.evaluate('Object.isFrozen(ReportSettings)&&Object.isFrozen(ReportSettings.render_options)'))
        for item in data['color_themes']['choices']:
            self.page.locator('#color-theme').select_option(item['id'])
            self.page.wait_for_function('id=>document.documentElement.dataset.colorTheme===id',arg=item['id'])
            self.assertTrue(self.page.locator('#hrs-theme-link').get_attribute('href').endswith('/'+item['stylesheet']))
        if self.evidence:self.page.screenshot(path=str(self.evidence/'catalog-theme.png'))

    def test_02_live_selection_reuses_one_current_map_and_invalidates_after_edit(self):
        raw='# 当前映射\r\n\r\n'+''.join(f'## 章节{i}\r\n\r\n目标段落{i}，文字😀继续。\r\n\r\n' for i in range(100))
        source(self.page,raw)
        target=self.page.locator('#preview-content [data-block-editor]').filter(has_text='目标段落7，')
        target.dblclick();self.page.keyboard.press('End');self.page.keyboard.insert_text('第一次')
        self.assertIn('第一次',value(self.page))
        self.page.evaluate("()=>{const create=SourceMap.create;window.mapBuilds=0;SourceMap.create=(...args)=>{window.mapBuilds++;return create(...args)}}")
        self.page.evaluate("()=>{for(let i=0;i<40;i++)document.dispatchEvent(new Event('selectionchange'))}")
        self.assertLessEqual(self.page.evaluate('window.mapBuilds'),1)
        self.assertTrue(target.evaluate('n=>n.isContentEditable'))
        first=value(self.page);self.page.keyboard.insert_text('第二次')
        self.assertIn('第一次第二次',value(self.page))
        self.page.evaluate("()=>{window.mapBuilds=0;for(let i=0;i<40;i++)document.dispatchEvent(new Event('selectionchange'))}")
        self.assertLessEqual(self.page.evaluate('window.mapBuilds'),1)
        self.assertNotEqual(first,value(self.page))
        self.assertEqual(value(self.page).replace('第一次第二次',''),raw)

    def test_03_old_palette_request_cannot_restore_or_notify_in_new_document(self):
        pending=[];self.page.route('**/api/render-profile',lambda route:pending.append(route))
        self.page.locator('#color-theme').select_option('violet')
        self.page.wait_for_timeout(100);self.assertEqual(len(pending),1)
        self.page.evaluate("()=>ReportStudioProgrammatic.open('new')")
        pending[0].fulfill(status=503,json={'ok':False,'error':'旧文稿配色请求'})
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.locator('#toast').inner_text(),'')
        self.assertEqual(self.page.locator('#color-theme').input_value(),'blue')


if __name__=='__main__':
    import unittest
    unittest.main()
