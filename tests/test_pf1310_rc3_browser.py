"""RC3-01..04: the synthetic public manual, real import/save and read-only ZIP.

Only the native directory chooser is replaced with a test-owned destination.
All import, resource, draft, save, Marked and reading-pack routes are real.
"""
from pathlib import Path
import io, json, re, shutil, sys, unittest, zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from browser_support import ManualService, source, value

FIXTURE = ROOT / 'tests/fixtures/lingmo_manual'
TASK_SOURCE = '# 清单😀\r\n\r\n- 捕捉一个念头\r\n  - 补上一个细节\r\n  - [X] 重复😀\r\n    - [ ] 深层任务\r\n- [x] 打开这份手册\r\n- [ ] 写下自己的第一段\r\n\r\n```md\r\n- [ ] 代码示例\r\n```\r\n\r\n`- [ ] 行内示例`\r\n'


class ManualFeedback(ManualService):
    def project_setup(self):
        return (TASK_SOURCE, True) if self._testMethodName == "test_04_nested_tasks_toggle_only_marker_and_support_undo_redo" else super().project_setup()

    def test_01_manual_saves_without_requiring_code_example_image(self):
        imported = self.import_manual()
        self.assertIn('![图片说明](.assets/photo.png)', imported)
        self.page.locator('#btn-save').click()
        # First-save destination uses the genuine modal and selection token.
        self.page.wait_for_selector('#modal-body input')
        name = self.page.locator('#modal-body input').first
        name.fill('手册保存专项')
        self.page.locator('#modal-ok').click()
        self.page.locator('.confirm-window button').filter(has_text='确认位置').click()
        self.page.wait_for_function("/已保存|正式保存失败/.test(document.querySelector('#save-indicator').textContent)")
        self.assertNotIn('失败', self.page.locator('#save-indicator').inner_text(), self.page.locator('#toast').inner_text())
        saved = self.destination / '手册保存专项'
        # Saved independent MD images now become normal figure objects. Keep
        # the original regression strict about every byte outside that image.
        persisted=(saved / 'report.md').read_bytes().decode('utf8')
        image_lines=re.findall(r'^!\[[^\n]*\]\(assets/[^\n]+\)$',imported,re.M)
        self.assertEqual(len(image_lines),1)
        figures=list(re.finditer(r'^```report-figure\n(.*?)\n```',persisted,re.M|re.S))
        self.assertEqual(len(figures),1)
        figure=json.loads(figures[0].group(1))
        self.assertEqual(figure['kind'],'image');self.assertIn(figure['src'],image_lines[0])
        self.assertTrue((saved / figure['src']).is_file())
        self.assertEqual(persisted,imported.replace(image_lines[0],figures[0].group(0),1))
        self.assertEqual(len(list((saved / 'assets').glob('*.png'))), 1)
        if self.evidence:
            shutil.copytree(saved, self.evidence / '手册保存工程')
            self.page.screenshot(path=str(self.evidence / 'saved.png'))

    def test_02_dark_html_card_inherits_white_in_preview_and_offline(self):
        self.import_manual()
        card = self.page.locator('#preview-content [style*="background-color: rgb(85, 66, 113)"]')
        self.assertEqual(card.locator('p').nth(1).evaluate('e=>getComputedStyle(e).color'), 'rgb(255, 255, 255)')
        if self.evidence: card.screenshot(path=str(self.evidence / 'white-card.png'))
        # A bold child must inherit too; ordinary report typography is unchanged.
        source(self.page, '# Card\n\n<div style="background-color:#554271;color:#fff"><p><strong>白色加粗</strong></p><p style="color:#e5ddf0">淡色</p></div>\n')
        self.page.wait_for_function("document.querySelector('#preview-content strong')?.textContent==='白色加粗'")
        self.assertEqual(self.page.locator('#preview-content strong').evaluate('e=>getComputedStyle(e).color'), 'rgb(255, 255, 255)')
        html = self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        offline = self.folder / 'card.html'; offline.write_bytes(html.encode('utf8'))
        reader = self.browser.new_page(); reader.goto(offline.as_uri())
        self.assertEqual(reader.locator('main strong').evaluate('e=>getComputedStyle(e).color'), 'rgb(255, 255, 255)')
        reader.close()

    def test_03_manual_reading_pack_opens_footnotes_and_keeps_source_readonly(self):
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, 'w') as archive:
            for file in FIXTURE.rglob('*'):
                if file.is_file(): archive.writestr(file.relative_to(FIXTURE).as_posix(), file.read_bytes())
        before = value(self.page)
        self.page.locator('#menu-open > summary').click(); self.page.locator('#btn-readpack').click()
        self.page.locator('#file-reader-zip').set_input_files({'name':'manual.zip','mimeType':'application/zip','buffer':memory.getvalue()})
        self.page.wait_for_function("/只读|打开失败/.test(document.querySelector('#reader-status').textContent)")
        self.assertNotIn('失败', self.page.locator('#reader-status').inner_text())
        self.page.wait_for_function("document.querySelector('#reader-article img')?.naturalWidth>0")
        self.page.wait_for_selector('#reader-article svg')
        # The public fixture has two different notes. Count forward and return
        # links separately so both definitions and their round trips are tested.
        refs = self.page.locator('#reader-article .hrs-note-link:not(.hrs-note-back)')
        backs = self.page.locator('#reader-article .hrs-note-back')
        self.assertEqual(refs.count(), 2)
        self.assertEqual(backs.count(), 2)
        for index in range(2):
            refs.nth(index).click()
            backs.nth(index).click()
        self.assertEqual(self.page.locator('#reader-article input[type=checkbox][disabled]').count(), 2)
        self.assertEqual(self.page.locator('#reader-article input[type=checkbox]').evaluate_all("xs=>xs.map(x=>getComputedStyle(x.closest('li')).listStyleType)"),['none']*2)
        self.page.locator('#reader-close').click()
        self.assertEqual(value(self.page), before)

    def test_04_nested_tasks_toggle_only_marker_and_support_undo_redo(self):
        text = TASK_SOURCE
        self.page.wait_for_function("document.querySelectorAll('#preview-content input[type=checkbox]').length===4")
        boxes = self.page.locator('#preview-content input[type=checkbox]')
        self.assertTrue(boxes.evaluate_all('xs=>xs.every(x=>!x.disabled)'), 'GFM task inputs are still disabled')
        # TASK-01: tasks use the checkbox as their marker; ordinary nested
        # bullets retain theirs. Only presentation changes, not GFM source.
        self.assertEqual(boxes.evaluate_all("xs=>xs.map(x=>getComputedStyle(x.closest('li')).listStyleType)"), ['none']*4)
        ordinary=self.page.locator('#preview-content li').filter(has_text='捕捉一个念头').first
        self.assertNotEqual(ordinary.evaluate('e=>getComputedStyle(e).listStyleType'), 'none')
        boxes.nth(1).click()
        expected = text.replace('- [ ] 深层任务', '- [x] 深层任务')
        self.page.wait_for_function('s=>document.querySelector("#markdown").sourceEditor.value===s', arg=expected)
        self.page.keyboard.press('Control+Z')
        self.page.wait_for_function('s=>document.querySelector("#markdown").sourceEditor.value===s', arg=text)
        self.page.keyboard.press('Control+Y')
        self.page.wait_for_function('s=>document.querySelector("#markdown").sourceEditor.value===s', arg=expected)
        self.assertIn('```md\r\n- [ ] 代码示例', value(self.page))
        # V060: free-reader toggles are local reading state; the archive still
        # recovers the exact checked source and never writes it from the reader.
        html = self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        restored = self.page.evaluate("""async html=>{const t=document.createElement('template');t.innerHTML=html;return (await ReportExportArchive.readArchive(JSON.parse(t.content.querySelector('#report-source').textContent),t.content)).markdown;}""", html)
        self.assertEqual(restored, expected)
        offline = self.folder / 'tasks.html'; offline.write_bytes(html.encode('utf8'))
        reader = self.browser.new_page(); reader.goto(offline.as_uri())
        self.assertEqual(reader.locator('main input[type=checkbox][disabled]').count(), 0)
        self.assertEqual(reader.locator('main input[type=checkbox]').evaluate_all("xs=>xs.map(x=>getComputedStyle(x.closest('li')).listStyleType)"), ['none']*4)
        self.assertTrue(reader.locator('main input[type=checkbox]').nth(1).is_checked()); reader.close()
        # Save the registered project via its real revision/commit path.
        self.page.locator('#btn-save').click()
        self.page.wait_for_function("document.querySelector('#save-indicator').textContent.includes('已保存')")
        self.assertEqual((self.project / 'report.md').read_bytes(), expected.encode('utf8'))
        if self.evidence: self.page.screenshot(path=str(self.evidence / 'checked-tasks.png'))

    def test_05_loose_tasks_keep_ordinary_markers_and_source(self):
        """TASK-01: only real task items lose their bullet, including loose lists."""
        text='# 清单\n\n- 普通列表\n- [ ] 任务\n\n  第二段说明\n\n  - [x] 内层任务\n- \\[ ] 转义标记\n- `[ ]` 行内代码\n\n1. [ ] 有序任务\n2. 普通顺序项\n'
        source(self.page,text)
        self.page.wait_for_function("document.querySelectorAll('#preview-content input[type=checkbox]').length===3")
        self.assertEqual(self.page.locator('#preview-content input[type=checkbox]').evaluate_all("xs=>xs.map(x=>getComputedStyle(x.closest('li')).listStyleType)"),['none']*3)
        self.assertEqual(self.page.locator('#preview-content li').evaluate_all("xs=>xs.filter(e=>!e.classList.contains('hrs-task-item')).every(e=>getComputedStyle(e).listStyleType!=='none')"),True)
        self.assertEqual(value(self.page),text)
        self.assertEqual(self.errors,[])


if __name__ == '__main__': unittest.main()
