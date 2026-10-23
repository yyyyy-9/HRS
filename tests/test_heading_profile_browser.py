"""IDENTITY-01 / SECTION-READ-01 / HEADING-OPTION-01 / SESSION-TOAST-01.

Real local service + Chromium; source text is never changed by display policy.
"""
import io,json,zipfile
from pathlib import Path
from browser_support import ManualService
from browser_support import source, value


class HeadingProfile(ManualService):
    def test_01_health_badge_and_canonical_release_identity(self):
        health=self.page.request.get(f'http://127.0.0.1:{self.server.server_port}/api/health').json()
        manifest=json.loads((Path(__file__).resolve().parents[1]/'app/MANIFEST.json').read_text('utf8'))
        self.assertEqual(health['version'],manifest['version'])
        self.assertEqual(health['release'],f"v{manifest['version']} {manifest['package_revision']}")
        self.assertEqual(health['package_revision'],manifest['package_revision'])
        badge=self.page.locator('#release-badge')
        self.assertEqual(badge.inner_text(),health['release'])
        self.assertIn(health['release'],badge.get_attribute('title'))

    def test_02_section_reference_uses_current_map_in_all_views_and_first_open(self):
        raw='# 报告\r\n\r\n## 目的 {#sec-purpose}\r\n\r\n见 @sec:sec-purpose。\r\n\r\n`@sec:sec-purpose`\r\n'
        source(self.page,raw)
        for view in ['reading','source','split','reading']:
            self.page.locator(f'[data-view="{view}"]').click()
            self.page.wait_for_function("document.querySelector('#preview-content a.object-xref')?.textContent==='“目的”节'",timeout=1800)
            self.assertEqual(self.page.locator('#preview-content code').inner_text(),'@sec:sec-purpose')
        self.page.locator('#preview-content a.object-xref').click()
        self.page.wait_for_timeout(350)
        self.assertIn('reading',self.page.locator('#edit-layout').get_attribute('class'))
        # Fresh document, first render: no previous SourceMap may supply identity.
        (self.project/'report.md').write_bytes(raw.encode('utf8'))
        self.page.reload();self.page.evaluate("async()=>{await ReportStudioProgrammatic.ready();await ReportStudioProgrammatic.open('legacy')}")
        self.assertEqual(self.page.locator('#preview-content a.object-xref').inner_text(),'“目的”节')
        self.assertEqual(value(self.page),raw)

    def test_03_free_heading_toggle_persists_archive_and_engineering_forces_numbers(self):
        raw='# 无手工号\r\n\r\n## 目的\r\n\r\n### 方法\r\n\r\n## 结果\r\n'
        source(self.page,raw)
        option=self.page.locator('#show-heading-numbers');self.assertEqual(option.count(),1)
        self.assertFalse(option.is_checked());self.assertEqual(self.page.locator('.hrs-heading-number').count(),0)
        option.check();self.page.wait_for_function("document.querySelector('#toc').textContent.includes('1.1 方法')")
        self.page.locator('#show-object-numbers').uncheck()
        self.assertTrue(option.is_checked())
        exported=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        archive=self.page.evaluate("async html=>{const t=document.createElement('template');t.innerHTML=html;return ReportExportArchive.readArchive(JSON.parse(t.content.querySelector('#report-source').textContent),t.content)}",exported)
        self.assertEqual(archive['renderOptions'],{'show_object_numbers':False,'show_heading_numbers':True,'show_equation_numbers':False,'preserve_blank_lines':False})
        self.assertEqual(archive['markdown'],raw)
        self.assertEqual(self.page.evaluate("html=>{const t=document.createElement('template');t.innerHTML=html;return [...t.content.querySelectorAll('main .hrs-heading-number')].map(n=>n.textContent)}",exported),['1 ','1.1 ','2 '])
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w') as z:
            z.writestr('report.md',raw)
            z.writestr('meta.json',json.dumps({'render_profile':'free','render_options':archive['renderOptions']}))
        self.page.locator('#menu-open > summary').click();self.page.locator('#btn-readpack').click()
        self.page.locator('#file-reader-zip').set_input_files({'name':'note.zip','mimeType':'application/zip','buffer':memory.getvalue()})
        self.page.wait_for_function("document.querySelector('#reader-article h2')?.textContent==='1 目的'")
        self.assertEqual(self.page.locator('#reader-article h3').inner_text(),'1.1 方法')
        self.page.locator('#reader-close').click()
        option.uncheck();self.page.locator('#render-profile').select_option('engineering')
        self.page.wait_for_function("document.body.dataset.renderProfile==='engineering'")
        self.page.wait_for_function("document.querySelector('#toc').textContent.includes('2 结果')")
        self.assertTrue(self.page.locator('#show-heading-numbers').is_disabled())
        self.page.locator('#render-profile').select_option('free')
        self.page.wait_for_function("document.body.dataset.renderProfile==='free'")
        self.page.wait_for_function("!document.querySelector('#preview-content .hrs-heading-number')")
        self.assertEqual(value(self.page),raw)
        meta=json.loads((self.project/'meta.json').read_text('utf8'))
        self.assertEqual(meta['render_options'],{'show_object_numbers':False,'show_heading_numbers':False,'show_equation_numbers':False,'preserve_blank_lines':False})
        if self.evidence:self.page.screenshot(path=str(self.evidence/'free-controls.png'))
        self.page.set_viewport_size({'width':1000,'height':780})
        for control in ['#heading-number-option','#object-number-option']:
            box=self.page.locator(control).bounding_box();self.assertIsNotNone(box)
            self.assertGreaterEqual(box['x'],0);self.assertLessEqual(box['x']+box['width'],1000)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'free-controls-narrow.png'))

    def test_04_title_digits_are_literal_only_display_switch_adds_labels(self):
        # User decision: never infer or remove a number from title text.
        raw='# 报告\n\n## 目的\n\n## 1.1 错位章节\n\n## 2 结果\n\n### 参数\n\n## 248.33 nm\n\n`## 3 示例`\n'
        source(self.page,raw)
        self.page.wait_for_function("document.querySelectorAll('#preview-content h2').length===4")
        literal=['目的','1.1 错位章节','2 结果','248.33 nm']
        self.assertEqual(self.page.locator('#preview-content h2').all_text_contents(),literal)
        self.page.locator('#show-heading-numbers').check()
        self.page.wait_for_function("document.querySelector('#toc').textContent.includes('3.1 参数')")
        numbered=['1 目的','2 1.1 错位章节','3 2 结果','4 248.33 nm']
        self.assertEqual(self.page.locator('#preview-content h2').all_text_contents(),numbered)
        self.page.locator('#render-profile').select_option('engineering')
        self.page.wait_for_function("document.body.dataset.renderProfile==='engineering'")
        self.assertEqual(self.page.locator('#preview-content h2').all_text_contents(),numbered)
        self.page.locator('#btn-validate').click()
        self.page.wait_for_function("document.querySelector('#problem-list').textContent.includes('手工章号')")
        self.assertIn('1.1 错位章节',self.page.locator('#toc').inner_text())
        self.assertIn('2 1.1 错位章节',self.page.locator('#toc').inner_text())
        self.assertEqual(value(self.page),raw)
        # The diagnostic never mutates text; free display can hide generated
        # labels while retaining every digit typed by the author.
        self.page.locator('#render-profile').select_option('free')
        self.page.wait_for_function("document.body.dataset.renderProfile==='free'")
        self.page.locator('#show-heading-numbers').uncheck()
        self.page.wait_for_function("!document.querySelector('#preview-content .hrs-heading-number')")
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        labels=self.page.evaluate("html=>{const t=document.createElement('template');t.innerHTML=html;return [...t.content.querySelectorAll('main h2')].map(h=>h.textContent)}",html)
        self.assertEqual(labels,literal)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'numbered-headings.png'))

    def test_05_old_validation_toast_is_cleared_on_switch_and_pending_reply_ignored(self):
        raw='# 一个\n\n# 第二个\n\n#### 跳级\n'
        source(self.page,raw);self.page.locator('#render-profile').select_option('engineering')
        self.page.wait_for_function("document.body.dataset.renderProfile==='engineering'")
        self.page.locator('#btn-validate').click()
        self.page.wait_for_selector('#toast.show');self.assertIn('第',self.page.locator('#toast').inner_text())
        self.page.evaluate("()=>ReportStudioProgrammatic.open('new')")
        self.assertFalse(self.page.locator('#toast').evaluate("n=>n.classList.contains('show')"))
        self.assertEqual(self.page.locator('#toast').inner_text(),'')
        # A response (including failure) already in flight belongs to C only.
        pending=[]
        self.page.route('**/api/validate',lambda route: pending.append(route))
        self.page.locator('#btn-validate').click()
        self.page.wait_for_timeout(100)
        self.assertEqual(len(pending),1)
        self.page.evaluate("()=>ReportStudioProgrammatic.open('legacy')")
        pending[0].fulfill(status=503,json={'ok':False,'error':'C 的旧检查'})
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.locator('#toast').inner_text(),'')


if __name__=='__main__':
    import unittest
    unittest.main()
