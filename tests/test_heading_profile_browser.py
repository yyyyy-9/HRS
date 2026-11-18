"""IDENTITY-01 / SECTION-READ-01 / HEADING-OPTION-01 / SESSION-TOAST-01.

Real local service + Chromium; source text is never changed by display policy.
"""
import io,json,zipfile
from pathlib import Path
from browser_support import ManualService
from browser_support import select, source, value, default_render_options


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
        # EDITOR-UX-2.6: path labels identify duplicate chapter titles.
        fresh='# 报告\r\n\r\n## 目的\r\n\r\n## 目的\r\n\r\n参见：\r\n'
        source(self.page,fresh)
        self.page.locator('[data-view="source"]').click()
        point=fresh.index('参见：')+len('参见：')
        select(self.page,point,point)
        self.page.locator('#ref-picker summary').click()
        self.page.locator('[data-insert="section-ref"]').click()
        picker=self.page.get_by_label('引用章节')
        self.assertEqual(picker.locator('option').all_text_contents(),['报告','报告 · 目的 · 第 3 行','报告 · 目的 · 第 5 行'])
        picker.select_option(index=2);self.page.locator('#modal-ok').click()
        written=value(self.page)
        self.assertRegex(written,r'## 目的\r\n\r\n## 目的 \{#(sec-[a-f0-9]+)\}\r\n\r\n参见：@sec:\1\r\n')
        self.page.locator('[data-view="split"]').click()
        self.page.wait_for_selector('#preview-content a.object-xref')
        self.assertEqual(self.page.locator('#preview-content a.object-xref').inner_text(),'“目的”节')
        self.page.locator('#btn-undo').click()
        self.assertEqual(value(self.page),fresh)

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
        self.assertEqual(archive['renderOptions'],default_render_options(show_object_numbers=False,show_heading_numbers=True,show_equation_numbers=False,preserve_blank_lines=False))
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
        self.assertEqual(meta['render_options'],default_render_options(show_object_numbers=False,show_heading_numbers=False,show_equation_numbers=False,preserve_blank_lines=False))
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

    def test_06_live_validation_coalesces_input_and_ignores_closed_results(self):
        """DOCUMENT-CHECK-LIVE: serialize automatic requests, catch up, then stop on close."""
        p=self.page
        raw='# 标题\n\n## 一节\n\n正文'
        source(p,raw);p.locator('#render-profile').select_option('engineering')
        p.locator('#btn-validate').click()
        p.wait_for_function("document.querySelector('#problems-summary').textContent==='0 个错误 · 0 个提醒'")
        pending=[]
        p.route('**/api/validate',lambda route: pending.append(route))

        first=raw+'\n\n#### 跳级\n'
        with p.expect_request('**/api/validate') as request:
            source(p,first)
        self.assertEqual(request.value.post_data_json['markdown'],first)
        self.assertEqual(p.locator('#problems-summary').inner_text(),'正在更新检查…')
        latest='# 标题\n\n# 第二标题\n\n正文'
        source(p,latest+'甲');source(p,latest+'甲乙');source(p,latest)
        p.wait_for_timeout(550)
        self.assertEqual(len(pending),1)
        with p.expect_request('**/api/validate') as request, p.expect_response('**/api/validate'):
            pending[0].continue_()
        self.assertEqual(request.value.post_data_json['markdown'],latest)
        self.assertEqual(p.locator('[data-code="HEADING_LEVEL_GAP"]').count(),0)
        pending[1].continue_()
        p.locator('[data-code="MULTIPLE_H1"]').wait_for()
        self.assertEqual(p.locator('#toast').inner_text(),'')

        # Collapsing ignores an in-flight result and stops checks on further edits.
        with p.expect_request('**/api/validate'):
            source(p,raw)
        p.locator('#btn-problems-close').click()
        source(p,first)
        pending[2].continue_()
        p.wait_for_timeout(550)
        self.assertEqual(len(pending),3)
        self.assertTrue(p.locator('#problems-panel').is_hidden())
        self.assertEqual(p.locator('#problem-list').inner_text(),'')
        p.unroute('**/api/validate')
        p.locator('#btn-validate').click()
        gap=p.locator('[data-code="HEADING_LEVEL_GAP"]')
        gap.wait_for()
        source(p,raw)
        self.assertTrue(gap.is_disabled())
        p.locator('#btn-problems-close').click()
        p.locator('#btn-validate').click()
        p.wait_for_function("document.querySelector('#problems-summary').textContent.startsWith('0 个错误')")

    def test_07_quickfixes_and_lossless_table_conversion(self):
        """QUICKFIX-01 / TABLE-CONVERT-01: undoable heading/currency quick-fixes and lossless GFM <-> report-table switch."""
        p=self.page
        raw=(
            '# 成本与光谱报告\n\n'
            '#### 跳级标题\n\n'
            '单套预算 $120。\n\n'
            '批量从 $1,200 降至 $980。\n\n'
            '| 参数 | 指标 |\n'
            '| --- | --- |\n'
            '| 波长 | $248.33\\ \\mathrm{nm}$ |\n'
            ': 标定表 {#tbl-cal}\n'
        )
        source(p,raw);p.locator('#render-profile').select_option('engineering')
        p.locator('#btn-validate').click()
        p.wait_for_selector('[data-quickfix="HEADING_LEVEL_GAP"]')
        self.assertEqual(p.locator('[data-quickfix="HEADING_LEVEL_GAP"]').inner_text(),'改为 H2')
        self.assertEqual(p.locator('[data-quickfix="UNESCAPED_CURRENCY"]').count(),2)
        p.locator('[data-quickfix="HEADING_LEVEL_GAP"]').click()
        p.wait_for_function("document.querySelectorAll('[data-code=HEADING_LEVEL_GAP]').length===0")
        self.assertIn('\n## 跳级标题\n',value(p))
        p.locator('[data-quickfix="UNESCAPED_CURRENCY"]').first.click()
        p.wait_for_function("document.querySelectorAll('[data-code=UNESCAPED_CURRENCY]').length===1")
        p.locator('[data-quickfix="UNESCAPED_CURRENCY"]').first.click()
        p.wait_for_function("document.querySelectorAll('[data-code=UNESCAPED_CURRENCY]').length===0")
        self.assertIn('单套预算 \\$120。',value(p))
        self.assertIn('批量从 \\$1,200 降至 \\$980。',value(p))

        # GFM pipe table -> report-table -> GFM pipe table + Undo
        p.wait_for_selector('[data-table-convert="to-structured"]')
        p.locator('[data-table-convert="to-structured"]').click()
        p.wait_for_selector('[data-table-convert="to-pipe"]')
        self.assertIn('"schema": "report-table-v1"',value(p))
        self.assertIn('"id": "tbl-cal"',value(p))
        p.locator('[data-table-convert="to-pipe"]').click()
        p.wait_for_selector('[data-table-convert="to-structured"]')
        self.assertNotIn('"schema": "report-table-v1"',value(p))
        self.assertIn(': 标定表 {#tbl-cal}',value(p))
        p.locator('#btn-undo').click()
        p.wait_for_selector('[data-table-convert="to-pipe"]')
        self.assertIn('"schema": "report-table-v1"',value(p))
        p.locator('[data-view="reading"]').click()
        self.assertEqual(p.locator('[data-table-convert]').count(),0)
        p.locator('[data-view="split"]').click()
        exported_html=p.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        self.assertNotIn('data-table-convert',exported_html)


if __name__=='__main__':
    import unittest
    unittest.main()
