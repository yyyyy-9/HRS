"""R8-EXPERIENCE-01: native note/scope/save/export and temporary-report behavior."""
from pathlib import Path
import json
import tempfile
import time
import unittest
from browser_support import LiveDocument, browser_session, source, value, artifact_directory
from test_notebook_browser import png


class ReportExperience(unittest.TestCase):
    def test_scoped_tail_object_allows_new_paragraphs_and_undo(self):
        """TOPIC-TAIL-01: a folded end object must leave an editable trailing line."""
        first='# 前篇😀\r\n\r\n前篇内容\r\n\r\n'
        second='# 当前篇\r\n\r\n本篇内容\r\n'
        third='\r\n# 后篇😀\r\n\r\n后篇内容\r\n'
        text=first+second+third
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;p.locator('#topic-select').select_option(label='2 · 当前篇')
            p.evaluate("()=>{const e=document.querySelector('#markdown').sourceEditor;e.focus()}")
            p.keyboard.press('Control+End')
            p.locator('[data-insert="table"]').click();p.locator('#modal-ok').click()
            p.wait_for_selector('.source-fold-summary')
            inserted=value(p)
            p.keyboard.press('Enter');p.keyboard.insert_text('表后新段😀')
            p.wait_for_function("document.querySelector('#preview-content').textContent.includes('表后新段😀')")
            edited=value(p)
            self.assertTrue(edited.startswith(first));self.assertTrue(edited.endswith(third))
            self.assertIn('```\n表后新段😀',edited.replace('\r\n','\n'))
            p.keyboard.press('Control+z')
            p.wait_for_function('text=>document.querySelector("#markdown").sourceEditor.value===text',arg=inserted)
            self.assertEqual(value(p),inserted)
            p.keyboard.press('Control+Shift+z')
            p.wait_for_function('text=>document.querySelector("#markdown").sourceEditor.value===text',arg=edited)
            p.keyboard.press('Enter');p.keyboard.insert_text('第二行')
            p.wait_for_function("document.querySelector('#preview-content').textContent.includes('第二行')")
            self.assertTrue(value(p).endswith(third))
            self.assertEqual((d.project/'report.md').read_bytes(),text.encode('utf8'))
            self.assertEqual(d.errors,[])

    def test_image_tail_enter_in_scoped_last_topic_and_whole_document(self):
        """TOPIC-TAIL-01: image upload and EOF use the same original buffer."""
        with browser_session() as browser:
            for profile,scoped in [('free',True),('free',False),('engineering',False)]:
                with self.subTest(profile=profile,scoped=scoped),tempfile.TemporaryDirectory() as folder:
                    text=('# 前篇😀\n\n不要改\n\n' if scoped else '')+'# 当前篇\n\n正文'
                    with LiveDocument(browser,folder,text,profile=profile,registered=True) as d:
                        p=d.page
                        if scoped:p.locator('#topic-select').select_option(label='2 · 当前篇')
                        p.evaluate("()=>document.querySelector('#markdown').sourceEditor.focus()")
                        p.keyboard.press('Control+End')
                        p.locator('#file-image').set_input_files({'name':'tail.png','mimeType':'image/png','buffer':png(8)})
                        p.wait_for_selector('.source-fold-summary')
                        p.wait_for_function("document.querySelector('#preview-content img')?.complete")
                        p.keyboard.press('Enter');p.keyboard.insert_text('图后正文😀')
                        p.wait_for_function("document.querySelector('#preview-content').textContent.includes('图后正文😀')")
                        self.assertIn('```\n\n图后正文😀',value(p).replace('\r\n','\n'))
                        if scoped:self.assertTrue(value(p).startswith('# 前篇😀\n\n不要改\n\n'))
                        p.keyboard.press('Control+s');p.wait_for_function("document.querySelector('#save-indicator').textContent.includes('已保存')")
                        self.assertEqual((d.project/'report.md').read_text('utf8'),value(p));self.assertEqual(d.errors,[])
                        if scoped:p.screenshot(path=str(artifact_directory(__file__)/'topic-image-tail.png'))

    def test_topic_first_heading_keeps_source_typography(self):
        """TOPIC-STYLE-01: hiding earlier topics must retain line decorations."""
        first='# 第一专题😀\r\n\r\n## 首篇次级\r\n\r\n'+('前文\r\n\r\n'*100)
        second='# 第二专题标题\r\n\r\n第二篇正文[^n]\r\n\r\n[^n]: 隐藏的全局定义\r\n\r\n## 次级标题\r\n\r\n第二篇结尾\r\n'
        text=first+second+'\r\n# 第三专题\r\n\r\n第三篇\r\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page
            def heading_style(title):
                return p.locator('.cm-line').filter(has_text=title).first.evaluate('''e=>{
                    const s=getComputedStyle(e);return [s.fontSize,s.fontWeight,s.color,e.classList.contains('cm-hf8-heading-1')];
                }''')
            initial=heading_style('第一专题😀')
            secondary=p.locator('.cm-line').filter(has_text='首篇次级').first.evaluate('e=>getComputedStyle(e).fontSize')
            self.assertTrue(initial[-1])
            for label,title in [('2 · 第二专题标题','第二专题标题'),('3 · 第三专题','第三专题'),('1 · 第一专题😀','第一专题😀')]:
                p.locator('#topic-select').select_option(label=label)
                p.wait_for_function('title=>document.querySelector("#preview-content h1")?.textContent===title',arg=title)
                self.assertEqual(heading_style(title),initial)
                if title=='第二专题标题':
                    self.assertEqual(p.locator('.cm-line').filter(has_text='次级标题').first.evaluate('e=>getComputedStyle(e).fontSize'),secondary)
            self.assertEqual(value(p),text)
            self.assertEqual((d.project/'report.md').read_bytes(),text.encode('utf8'))
            self.assertEqual(d.errors,[])

    def test_scoped_edit_undo_preserves_hidden_notes_and_utf16_neighbors(self):
        text='# A\n\n前篇😀\n\n# B\n\n本篇😀[^n]\n\n[^n]: 隐藏的全局定义\n\n后半段\n\n# C\n\n后篇😀\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;p.locator('#topic-select').select_option(label='2 · B')
            p.wait_for_function("document.querySelectorAll('#preview-content h1').length===1")
            self.assertEqual(p.locator('.source-note-row').count(),1)
            self.assertNotIn('隐藏的全局定义',p.locator('.cm-content').inner_text())
            pos=p.evaluate("()=>{const e=document.querySelector('#markdown').sourceEditor;return e.value.indexOf('后半段')+3}")
            p.evaluate('pos=>{const e=document.querySelector("#markdown").sourceEditor;e.setSelectionRange(pos);e.focus()}',pos)
            p.keyboard.insert_text('新增😀');p.wait_for_function("document.querySelector('#preview-content').textContent.includes('新增😀')")
            self.assertEqual(value(p),text.replace('后半段','后半段新增😀'))
            p.keyboard.press('Control+z');p.wait_for_function("!document.querySelector('#markdown').sourceEditor.value.includes('新增😀')")
            self.assertEqual(value(p),text)
            p.keyboard.press('Control+a');p.keyboard.press('Backspace')
            self.assertEqual(value(p),text)
            self.assertEqual((d.project/'report.md').read_text('utf8'),text);self.assertEqual(d.errors,[])

    def test_note_definition_ctrl_click_and_scoped_note_editor(self):
        text = '# First\n\nFirst[^a]\n\n' + '\n\n'.join('Paragraph '+str(i) for i in range(45)) + '\n\n[^a]: '+('Long note. '*120)+'\n\n[^b]: Second note\n\n# Second\n\nSecond[^b]\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page
            start=text.index('[^b]:')
            p.evaluate('pos=>document.querySelector("#markdown").sourceEditor.highlightRange(pos,pos+5)',start)
            p.wait_for_function('pos=>document.querySelector("#markdown").sourceEditor.view.coordsAtPos(pos)!=null',arg=start)
            c=p.evaluate('pos=>document.querySelector("#markdown").sourceEditor.view.coordsAtPos(pos+3)',start)
            p.keyboard.down('Control');p.mouse.click(c['left']+1,(c['top']+c['bottom'])/2);p.keyboard.up('Control')
            p.wait_for_function('''()=>{const n=document.querySelector('[data-hrs-note-key="b"]'),r=n.getBoundingClientRect(),v=n.closest('.page-scroll').getBoundingClientRect();return r.top<v.bottom&&r.bottom>v.top}''')
            p.locator('#topic-select').select_option(label='2 · Second')
            p.wait_for_function("document.querySelectorAll('#preview-content h1').length===1")
            p.locator('#source-notes').evaluate('e=>e.open=true')
            row=p.locator('.source-note-row[data-note-key="b"]')
            row.locator('button').last.click()
            self.assertEqual(p.locator('#modal-title').inner_text(),'编辑脚注定义')
            p.locator('#modal-body textarea').fill('[^b]: Updated note\n');p.locator('#modal-ok').click()
            p.wait_for_function("document.querySelector('#preview-content .hrs-footnotes').textContent.includes('Updated note')")
            self.assertEqual(value(p),text.replace('[^b]: Second note','[^b]: Updated note'))
            self.assertEqual((d.project/'report.md').read_text('utf8'),text)
            self.assertEqual(d.errors,[])

    def test_return_restores_origin_before_allowing_another_topic(self):
        text='# A\n\nA body\n\n# B\n\nB body\n\n# C\n\nC body\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;p.locator('#topic-select').select_option(label='2 · B')
            p.locator('#menu-export > summary').click();p.locator('#btn-export-word').click();p.wait_for_selector('#modal-layer:not([hidden])');p.locator('#modal-ok').click()
            p.wait_for_selector('#report-workspace-bar:not([hidden])');p.wait_for_selector('#workspace-operation[hidden]',state='attached')
            pending=[];p.route('**/api/drafts*',lambda route:pending.append(route))
            p.locator('#btn-workspace-return').click();p.wait_for_function("document.querySelector('#report-workspace-bar').hidden")
            self.assertTrue(p.locator('#topic-select').is_disabled());self.assertTrue(p.locator('#btn-export-word').is_disabled())
            self.assertIn('切换',p.evaluate("()=>ReportStudioProgrammatic.topics().then(()=>'',e=>e.message)"))
            # The source pane appears before the draft-list request is emitted.
            # Pump driver events until that actual boundary, without releasing it.
            deadline=time.monotonic()+3
            while not pending and time.monotonic()<deadline:p.wait_for_timeout(10)
            self.assertEqual(len(pending),1);pending[0].continue_();p.unroute('**/api/drafts*')
            p.wait_for_function("!document.querySelector('#topic-select').disabled")
            p.locator('#topic-select').select_option(label='3 · C')
            p.locator('#menu-export > summary').click();p.locator('#btn-export-word').click();p.wait_for_selector('#modal-layer:not([hidden])');p.locator('#modal-ok').click()
            p.wait_for_selector('#report-workspace-bar:not([hidden])');p.wait_for_selector('#workspace-operation[hidden]',state='attached')
            self.assertIn('C body',value(p));self.assertNotIn('B body',value(p));self.assertEqual(d.errors,[])

    def test_engineering_highlight_is_plain_and_inline_edit_preserves_syntax(self):
        text='# Report\n\n## ==普通== heading\n\nParagraph\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,profile='engineering',registered=True) as d:
            p=d.page;heading=p.locator('#preview-content h2')
            self.assertEqual(p.locator('#preview-content mark').count(),0)
            self.assertEqual(heading.get_attribute('data-block-editor'),'1')
            heading.dblclick();p.wait_for_function("document.querySelector('#preview-content h2').isContentEditable")
            p.keyboard.press('End');p.keyboard.insert_text(' edited');p.locator('#source-stats').click()
            p.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('edited')")
            self.assertIn('==普通==',value(p));self.assertNotIn('<mark',value(p));self.assertEqual(d.errors,[])

    def test_source_projection_edits_and_scrolls_only_current_topic(self):
        section=lambda name:'# '+name+'\n\n'+'\n\n'.join(name+' paragraph '+str(i) for i in range(45))+'\n\n'
        a,b,c=section('Alpha'),section('Beta'),section('Gamma');text=a+b+c
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;p.locator('#topic-select').select_option(label='2 · Beta')
            p.wait_for_function("document.querySelectorAll('#preview-content h1').length===1")
            ranges=p.evaluate("document.querySelector('#markdown').sourceEditor.view.visibleRanges")
            self.assertTrue(all(r['from']>=len(a) and r['to']<=len(a+b) for r in ranges),ranges)
            p.evaluate('pos=>{const e=document.querySelector("#markdown").sourceEditor;e.setSelectionRange(pos);e.focus()}',len(a)+10)
            p.keyboard.press('Control+Home')
            self.assertEqual(p.evaluate("document.querySelector('#markdown').sourceEditor.selectionStart"),len(a))
            p.keyboard.press('Control+End')
            self.assertLess(p.evaluate("document.querySelector('#markdown').sourceEditor.selectionStart"),len(a+b))
            p.keyboard.insert_text('Local edit')
            p.wait_for_function("document.querySelector('#preview-content').textContent.includes('Local edit')")
            self.assertTrue(value(p).startswith(a));self.assertTrue(value(p).endswith(c))
            p.locator('#follow-scroll').check()
            p.locator('#preview-content').evaluate("e=>e.closest('.page-scroll').scrollTop=400")
            box=p.locator('#preview-pane').bounding_box();p.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);p.mouse.wheel(0,-20000)
            p.wait_for_function("document.querySelector('#preview-content').closest('.page-scroll').scrollTop===0")
            self.assertIn('Beta',p.locator('.cm-content').inner_text());self.assertNotIn('Alpha paragraph',p.locator('.cm-content').inner_text())
            self.assertEqual(d.errors,[])

    def test_sidebar_controls_fixed_while_only_toc_scrolls(self):
        text='# Report\n\n'+'\n\n'.join('## Heading '+str(i)+'\n\nText' for i in range(70))
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;before=p.locator('#topic-controls').bounding_box()
            p.locator('#toc').evaluate('e=>e.scrollTop=500');after=p.locator('#topic-controls').bounding_box()
            self.assertAlmostEqual(before['y'],after['y'],delta=1)
            self.assertGreater(p.locator('#toc').evaluate('e=>e.scrollTop'),400)
            self.assertGreaterEqual(p.locator('#btn-rebuild-toc').evaluate('e=>parseFloat(getComputedStyle(e.parentElement).fontSize)'),13)

    def test_save_preserves_rendered_nodes_and_image_geometry(self):
        obj={'schema':'report-figure-v1','id':'fig-photo','kind':'image','src':'assets/a.png','caption':'Photo','alt':'Photo'}
        fence=chr(96)*3;text='# Report\n\n'+fence+'report-figure\n'+json.dumps(obj)+'\n'+fence+'\n\n'+'\n\n'.join('Text '+str(i) for i in range(70))
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,assets={'a.png':png(1,900,540)},registered=True) as d:
            p=d.page;p.wait_for_function("document.querySelector('#preview-content img')?.naturalWidth>0")
            source(p,text+'\n\nChanged\n');p.wait_for_function("document.querySelector('#preview-content').textContent.includes('Changed')")
            before=p.evaluate('''()=>{window.__heading=document.querySelector('#preview-content h1');const s=document.querySelector('#preview-content').closest('.page-scroll');s.scrollTop=1000;return {height:s.scrollHeight,top:s.scrollTop}}''')
            p.keyboard.press('Control+s');p.wait_for_function("document.querySelector('#save-indicator').textContent.includes('已保存')")
            after=p.evaluate('''()=>{const s=document.querySelector('#preview-content').closest('.page-scroll');return {same:window.__heading===document.querySelector('#preview-content h1'),height:s.scrollHeight,top:s.scrollTop}}''')
            self.assertTrue(after['same']);self.assertAlmostEqual(before['top'],after['top'],delta=1);self.assertAlmostEqual(before['height'],after['height'],delta=1)
            self.assertEqual((d.project/'report.md').read_text('utf8'),value(p))

    def test_reading_modules_and_human_filename(self):
        text='# First\n\nOne\n\n# Second\n\nTwo[^a]\n\n[^a]: Reading note\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;p.locator('#topic-select').select_option(label='2 · Second')
            p.locator('#menu-export > summary').click();p.locator('#btn-export').click()
            p.locator('input[name="export-scope"][value="modules"]').check()
            self.assertTrue(p.locator('input[name="export-source"][value="reading"]').is_enabled())
            p.locator('input[name="export-source"][value="reading"]').check()
            with p.expect_response(lambda r:'/api/export/modules/finish' in r.url) as pending:p.locator('#modal-ok').click()
            response=pending.value;self.assertTrue(response.ok,response.text());receipt=response.json()
            self.assertTrue(receipt['result_token'])
            self.assertTrue(p.locator('#toast').get_by_role('button',name='打开所在文件夹',exact=True).is_visible())
            self.assertRegex(receipt['filename'],r'^Second_\d{8}_\d{6}\.html$')
            html=Path(receipt['path']).read_text('utf8');self.assertIn('Two',html)
            self.assertEqual(value(p),text);self.assertEqual(d.errors,[])

    def test_temporary_report_preview_edit_return_resume_and_isolation(self):
        text='# Ledger\n\nLedger body\n\n# Report\n\n## Purpose\n\nReport body[^a]\n\n![Photo](assets/a.png)\n\n[^a]: Shared note\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,assets={'a.png':png(1)},registered=True) as d:
            p=d.page;p.locator('#topic-select').select_option(label='2 · Report')
            p.locator('#menu-export > summary').click();p.locator('#btn-export-word').click()
            p.wait_for_selector('#modal-layer:not([hidden])')
            self.assertEqual(p.locator('#modal-title').inner_text(),'准备工程报告')
            p.locator('#modal-ok').click();p.wait_for_selector('#report-workspace-bar:not([hidden])')
            p.wait_for_function("document.querySelector('#render-profile').value==='engineering'")
            p.wait_for_function("document.querySelector('#problems-summary').textContent.includes('0 个错误')")
            fragment=value(p);self.assertNotIn('Ledger body',fragment);self.assertIn('Shared note',fragment)
            self.assertEqual(p.locator('#preview-content h2 .hrs-heading-number').inner_text(),'1 ')
            source(p,fragment.replace('Report body','Edited body'))
            p.locator('#btn-workspace-return').click()
            p.wait_for_function("document.querySelector('#report-workspace-bar').hidden&&document.querySelector('#markdown').sourceEditor.value.includes('Ledger body')")
            self.assertEqual(value(p),text);self.assertEqual((d.project/'report.md').read_text('utf8'),text)
            p.locator('#menu-export > summary').click();p.locator('#btn-export-word').click()
            p.locator('input[name="report-scope"][value^="resume:"]').check();p.locator('#modal-ok').click()
            p.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('Edited body')")
            self.assertTrue(p.locator('#report-workspace-bar').is_visible());self.assertEqual(d.errors,[])

    def test_temporary_checks_expose_ambiguous_definitions_and_missing_external_target(self):
        text='# Target {#sec-external}\n\nOutside\n\n# Report\n\nSee @sec:sec-external and note[^a], missing[^missing]\n\n[^a]: One\n[^a]: Two\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;p.locator('#topic-select').select_option(label='2 · Report')
            p.locator('#menu-export > summary').click();p.locator('#btn-export-word').click();p.wait_for_selector('#modal-layer:not([hidden])')
            p.locator('#modal-ok').click();p.wait_for_selector('#report-workspace-bar:not([hidden])')
            p.wait_for_function("document.querySelector('#problem-list').textContent.includes('重复定义')")
            self.assertIn('sec-external',p.locator('#problem-list').inner_text());self.assertNotIn('# Target',value(p))
            self.assertIn('[^missing] 未定义',p.locator('#problem-list').inner_text())
            self.assertEqual(value(p).count('[^a]:'),2)
            self.assertEqual((d.project/'report.md').read_text('utf8'),text);self.assertEqual(d.errors,[])


if __name__=='__main__':unittest.main()
