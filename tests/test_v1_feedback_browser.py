
"""V1-FEEDBACK-01: actual image save, export routing, reviewed sync and theme failure."""
from pathlib import Path
from unittest.mock import patch
import json,tempfile,unittest
from browser_support import LiveDocument,browser_session,source,value,artifact_directory

class FeedbackExperience(unittest.TestCase):
    def test_local_standalone_images_become_normal_objects_on_save(self):
        from test_notebook_browser import png
        raw='# Report\n\n![First](assets/a.png "First title")\n\n![Second](assets/a.png)\n\nInline ![icon](assets/a.png) text.\n\n'+chr(96)*3+'md\n![example](assets/a.png)\n'+chr(96)*3+'\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,raw,assets={'a.png':png(1)},registered=True) as d:
            p=d.page;p.locator('#btn-save').click()
            p.wait_for_function('document.querySelectorAll("#preview-content .report-figure-wrap").length===2')
            p.wait_for_function('document.querySelector("#save-indicator").textContent.includes("已保存")')
            text=value(p);self.assertEqual(text.count('"schema": "report-figure-v1"'),2)
            self.assertEqual(len(set(p.locator('.report-figure-wrap').evaluate_all('xs=>xs.map(x=>x.dataset.figureId)'))),2)
            self.assertIn('Inline ![icon](assets/a.png) text.',text);self.assertIn('![example](assets/a.png)',text)
            self.assertIn('"caption": "First title"',text);self.assertIn('"alt": "First"',text);self.assertEqual((d.project/'report.md').read_text('utf8'),text)
            self.assertTrue(p.locator('.report-figure-wrap').first.inner_text().find('First')>=0)
            p.keyboard.press('Control+z');p.wait_for_function('s=>document.querySelector("#markdown").sourceEditor.value===s',arg=raw)
            p.keyboard.press('Control+y');p.wait_for_function('s=>document.querySelector("#markdown").sourceEditor.value===s',arg=text)
            self.assertEqual(d.errors,[])

    def test_single_h1_free_switches_in_place_and_engineering_opens_word_directly(self):
        text='# One report\n\n## Method\n\nText\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;requests=[];p.on('request',lambda r:requests.append(r.url) if '/api/report-workspace' in r.url else None)
            p.locator('#menu-export > summary').click();p.locator('#btn-export-word').click()
            p.wait_for_function('document.body.dataset.renderProfile==="engineering"&&!document.querySelector("#render-profile").disabled')
            self.assertFalse(p.locator('#report-workspace-bar').is_visible());self.assertEqual(requests,[])
            self.assertEqual(value(p),text)
            p.locator('#menu-export > summary').click();p.locator('#btn-export-word').click();p.wait_for_selector('#word-filename')
            self.assertEqual(requests,[]);self.assertFalse(p.locator('#report-workspace-bar').is_visible())
            self.assertEqual((d.project/'report.md').read_text('utf8'),text);self.assertEqual(d.errors,[])

    def test_topic_sync_reviews_diff_and_preserves_shared_definitions_and_neighbors(self):
        text='# First😀\r\n\r\nKeep\r\n\r\n[^note]: Shared definition\r\n\r\n[site]: https://example.org\r\n\r\n# Selected\r\n\r\nOriginal[^note] [link][site].\r\n\r\n# Last\r\n\r\nKeep last\r\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;p.locator('#topic-select').select_option(label='2 · Selected')
            p.locator('#menu-export > summary').click();p.locator('#btn-export-word').click();p.wait_for_selector('#modal-layer:not([hidden])')
            p.locator('#modal-ok').click();p.wait_for_selector('#report-workspace-bar:not([hidden])')
            p.wait_for_selector('#workspace-operation[hidden]',state='attached')
            self.assertTrue(p.locator('#btn-workspace-sync').is_enabled())
            temp=value(p);source(p,temp.replace('Original','Edited').replace('Shared definition','Changed shared'))
            p.wait_for_function('document.querySelector("#preview-content").textContent.includes("Edited")')
            p.locator('#btn-workspace-sync').click();p.wait_for_selector('.sync-diff')
            self.assertIn('Changed shared',p.locator('.sync-diff').inner_text())
            self.assertEqual((d.project/'report.md').read_bytes(),text.encode('utf8'))
            p.locator('#modal-cancel').click();self.assertEqual((d.project/'report.md').read_bytes(),text.encode('utf8'))
            p.locator('#btn-workspace-sync').click();p.wait_for_selector('.sync-diff')
            with p.expect_response(lambda r:'/api/report-workspace' in r.url and r.request.post_data_json.get('action')=='sync-apply') as response:
                p.locator('#modal-ok').click()
            reply=response.value.json();self.assertTrue(reply['ok'],reply)
            expected=text.replace('Original','Edited').replace('Shared definition','Changed shared')
            actual=(d.project/'report.md').read_text('utf8')
            self.assertEqual((d.project/'report.md').read_bytes(),expected.encode('utf8'))
            self.assertEqual(Path(reply['backup']).read_bytes(),text.encode('utf8'))
            self.assertIn('[site]: https://example.org',actual);self.assertEqual(actual.count('[site]:'),1)
            self.assertEqual(d.errors,[])

    def test_long_toc_rows_and_theme_failed_load_do_not_lock_controls(self):
        text='# Report with a very long title that must wrap fully in the sidebar\n\n'+''.join('## Section '+str(i)+' with a very long heading that wraps across several lines\n\nText\n\n' for i in range(45))
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page
            geometry=p.locator('#toc a').evaluate_all('xs=>xs.map(e=>({h:e.clientHeight,s:e.scrollHeight,shrink:getComputedStyle(e).flexShrink,wrap:getComputedStyle(e).whiteSpace}))')
            self.assertEqual(len(geometry),46);self.assertTrue(all(x['h']>=x['s'] and x['shrink']=='0' and x['wrap']=='normal' for x in geometry),geometry)
            held=[];p.route('**/web/theme-violet.css',lambda route:held.append(route))
            p.evaluate('()=>{const apply=ReportTheme.apply;ReportTheme.apply=(doc,name)=>apply(doc,name,{timeout:120})}')
            p.locator('#color-theme').select_option('violet')
            p.wait_for_function('document.querySelector("#toast").textContent.includes("配色加载超时")')
            p.wait_for_function('!document.querySelector("#color-theme").disabled')
            self.assertEqual(p.locator('#color-theme').input_value(),'blue')
            self.assertEqual(p.locator('#hrs-theme-link').get_attribute('href'),'/web/theme.css')
            self.assertEqual(json.loads((d.project/'meta.json').read_text('utf8'))['color_theme'],'blue')
            for route in held:route.abort()
            p.unroute('**/web/theme-violet.css')
            for theme in ['celadon','violet','azure','navy','warm','blue']:
                p.locator('#color-theme').select_option(theme)
                p.wait_for_function('t=>document.documentElement.dataset.colorTheme===t&&!document.querySelector("#color-theme").disabled',arg=theme)
            p.locator('#btn-validate').click();p.wait_for_selector('#problems-panel:not([hidden])')
            self.assertFalse(p.locator('#app').evaluate('e=>e.inert'))
            p.screenshot(path=str(artifact_directory(__file__)/'toc-theme.png'));self.assertEqual(d.errors,[])

