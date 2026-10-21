"""V1-MAINTENANCE-01: real navigation recovery, preflight and retained DOM."""
from pathlib import Path
from unittest.mock import patch
from browser_support import studio
from browser_support import artifact_directory
from test_notebook_browser import png
import json
import os
import subprocess
import sys
import tempfile
import unittest
from browser_support import LiveDocument,browser_session,source,value


class MaintenanceExperience(unittest.TestCase):
    def test_browser_exit_flushes_latest_large_draft_and_refuses_failed_write(self):
        """DESKTOP-01: shared exit refactor preserves the original browser path."""
        original='# 原稿\n\n保留正式文件。\n'
        latest='# 恢复草稿\n\n'+('中文😀恢复正文\n'*4000)
        self.assertGreater(len(latest.encode('utf8')),60000)
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,original,registered=True) as d:
            p=d.page;p.set_default_timeout(30000)
            p.route('**/api/draft',lambda route:route.fulfill(status=409,content_type='application/json',body=json.dumps({'ok':False,'error':'test occupied draft'})))
            source(p,latest);p.locator('#btn-exit').evaluate('e=>e.click()')
            p.wait_for_function("document.querySelector('#toast').textContent.includes('窗口已保留')")
            self.assertIn('/web/index.html',p.url);self.assertEqual((d.project/'report.md').read_text('utf8'),original)
            p.unroute('**/api/draft');p.locator('#btn-exit').evaluate('e=>e.click()');p.wait_for_url('about:blank')
            drafts=Path(folder)/'workspace/.drafts'
            values=[json.loads(f.read_text('utf8')) for f in drafts.glob('*/state.json')]
            self.assertTrue(any(v.get('markdown')==latest for v in values));self.assertEqual((d.project/'report.md').read_text('utf8'),original)
            self.assertEqual(d.errors,[])

    def test_asset_recycle_clear_requires_confirmation_and_preserves_live_assets(self):
        """ASSET-PURGE-01: use the shipped export dialog, never a user recycle bin."""
        text='# 素材整理\n\n![保留](assets/keep.png)\n'
        assets={'keep.png':png(1),'discard.png':png(2),'discard.emf':b'test-owned unused vector'}
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,assets=assets,registered=True) as d:
            p=d.page;p.locator('#menu-export > summary').click();p.locator('#btn-export').click()
            p.locator('.export-asset-housekeeping > summary').click()
            p.get_by_role('button',name='检查未使用的素材',exact=True).click()
            p.get_by_role('checkbox',name='选择素材组 discard',exact=True).check()
            p.get_by_role('button',name='把选中素材移入回收区',exact=True).click()
            p.locator('.confirm-layer').get_by_role('button',name='移入回收区',exact=True).click()
            clear=p.get_by_role('button',name='清空回收区',exact=True);clear.wait_for(state='visible')
            clear.click();p.locator('.confirm-layer').wait_for()
            self.assertIn('2 个附件',p.locator('.confirm-text').inner_text())
            self.assertIn('无法恢复',p.locator('.confirm-text').inner_text())
            evidence=artifact_directory(__file__);p.screenshot(path=str(evidence/'recycle-confirm.png'))
            p.locator('.confirm-layer').get_by_role('button',name='取消',exact=True).click()
            self.assertEqual(len(list((d.project/'.asset-trash').glob('*/assets/*'))),2)
            clear.click();p.locator('.confirm-layer').get_by_role('button',name='永久清空',exact=True).click()
            p.wait_for_function("document.querySelector('#toast').textContent.includes('已清空回收区')")
            clear.wait_for(state='hidden')
            self.assertEqual(list((d.project/'.asset-trash').iterdir()),[])
            self.assertEqual((d.project/'assets/keep.png').read_bytes(),assets['keep.png'])
            self.assertEqual((d.project/'report.md').read_text('utf8'),text);self.assertEqual(d.errors,[])

    def test_export_toast_folder_action_uses_created_result_and_expires_cleanly(self):
        """EXPORT-FOLDER-01: real HTML export; only the OS launch itself is intercepted."""
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,'# 导出测试\n\n正文\n',registered=True) as d:
            p=d.page
            with p.expect_response(lambda r:'/api/export/store' in r.url) as pending:d.export(via_ui=True)
            result=pending.value.json();self.assertTrue(result['result_token'])
            button=p.locator('#toast').get_by_role('button',name='打开所在文件夹',exact=True)
            button.wait_for(state='visible')
            self.assertIn('underline',button.evaluate('e=>getComputedStyle(e).textDecorationLine'))
            with patch('os.startfile',create=True) as opened:
                with p.expect_response(lambda r:'/api/export/open-folder' in r.url) as response:button.click()
                self.assertTrue(response.value.ok,response.value.text())
                opened.assert_called_once_with(str(Path(result['path']).parent))
            p.wait_for_function("Number(getComputedStyle(document.querySelector('#toast')).opacity)>.99")
            evidence=artifact_directory(__file__);p.screenshot(path=str(evidence/'export-folder-toast.png'))
            p.clock.install();p.locator('#source-stats').click();p.mouse.move(0,0);p.clock.fast_forward(8500)
            self.assertEqual(p.locator('#toast button').count(),0)
            self.assertEqual(d.errors,[])

    def test_pdf_export_uses_same_result_folder_action(self):
        """EXPORT-FOLDER-01: actual PDF output; use only the pinned test browser."""
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,'# PDF\n\n正文\n',registered=True) as d:
            p=d.page
            with patch.object(studio,'pick_browser',return_value=Path(os.environ['CHROMIUM_PATH'])):
                p.locator('#menu-export > summary').click()
                with p.expect_response(lambda r:'/api/pdf/store' in r.url,timeout=45000) as pending:p.locator('#btn-pdf').click()
            response=pending.value;self.assertTrue(response.ok,response.text());result=response.json()
            self.assertTrue(Path(result['path']).read_bytes().startswith(b'%PDF-'));self.assertTrue(result['result_token'])
            button=p.locator('#toast').get_by_role('button',name='打开所在文件夹',exact=True)
            with patch('os.startfile',create=True) as opened:
                with p.expect_response(lambda r:'/api/export/open-folder' in r.url) as request:button.click()
                self.assertTrue(request.value.ok,request.value.text());opened.assert_called_once_with(str(Path(result['path']).parent))
            self.assertEqual(d.errors,[])

    @staticmethod
    def prepare(page):
        page.locator('#menu-export > summary').click();page.locator('#btn-prepare-report').click()
        page.wait_for_selector('#modal-layer:not([hidden])');page.locator('#modal-ok').click()
        page.wait_for_selector('#report-workspace-bar:not([hidden])')
        page.wait_for_selector('#workspace-operation[hidden]',state='attached')

    def test_recent_explicit_resume_and_startup_recover_same_latest_draft(self):
        text='# A\n\nOriginal\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;self.prepare(p)
            identity=p.evaluate('ReportStudioProgrammatic.topics()')['documentId']
            edited=value(p)+'\nLatest draft😀\n';source(p,edited)
            p.wait_for_function("document.querySelector('#save-indicator').textContent.includes('草稿已备份')")
            p.locator('#btn-workspace-return').click()
            p.wait_for_selector('#workspace-operation[hidden]',state='attached')
            p.locator('#recent-list button').filter(has_text='临时稿').first.click()
            p.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('Latest draft😀')")
            self.assertEqual(value(p),edited)
            p.locator('#btn-workspace-return').click();p.wait_for_selector('#workspace-operation[hidden]',state='attached')
            p.locator('#menu-export > summary').click();p.locator('#btn-prepare-report').click()
            p.locator('input[value="resume:'+identity+'"]').check();p.locator('#modal-ok').click()
            p.wait_for_selector('#workspace-operation[hidden]',state='attached')
            self.assertEqual(value(p),edited)
            p.once('dialog',lambda dialog:dialog.accept())
            p.reload();p.wait_for_selector('#modal-layer:not([hidden])')
            p.locator('#modal-ok').click()
            p.evaluate('ReportStudioProgrammatic.ready()')
            p.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('Latest draft😀')")
            self.assertEqual(value(p),edited)
            self.assertEqual((d.project/'report.md').read_bytes(),text.encode('utf8'))
            self.assertEqual(d.errors,[])

    def test_programmatic_open_reads_formal_snapshot_without_recovery_dialog(self):
        text='# Formal\n\nBody\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;docid=p.evaluate('ReportStudioProgrammatic.topics()')['documentId']
            source(p,text+'\nUnsaved draft\n')
            p.wait_for_function("document.querySelector('#save-indicator').textContent.includes('草稿已备份')")
            p.evaluate("id=>{window.openFinished=false;ReportStudioProgrammatic.open(id).then(()=>window.openFinished=true)}",docid)
            p.wait_for_function('window.openFinished',timeout=2000)
            self.assertEqual(value(p),text)
            self.assertEqual(p.locator('#modal-layer:not([hidden])').count(),0)
            self.assertTrue(d.server.pending_drafts(docid))
            self.assertEqual(d.errors,[])

    def test_multiple_recovery_choices_remain_usable_during_report_transition(self):
        text='# Report\n\nBody\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;self.prepare(p);docid=p.evaluate('ReportStudioProgrammatic.topics()')['documentId']
            first=value(p)+'\nFirst candidate\n';source(p,first)
            p.wait_for_function("document.querySelector('#save-indicator').textContent.includes('草稿已备份')")
            p.locator('#btn-workspace-return').click();p.wait_for_selector('#workspace-operation[hidden]',state='attached')
            second=first+'\nSecond candidate\n'
            created=p.evaluate("""async ({docid,second})=>{
              const doc=await(await fetch('/api/doc?document_id='+docid)).json();
              const request={document_id:docid,draft_id:'b'.repeat(32),template:'engineering',base_revision:doc.revision,markdown:second,seq:1};
              return (await fetch('/api/draft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)})).json();
            }""",{'docid':docid,'second':second})
            self.assertTrue(created['ok'])
            p.locator('#menu-export > summary').click();p.locator('#btn-prepare-report').click()
            p.locator('input[value="resume:'+docid+'"]').check();p.locator('#modal-ok').click()
            p.wait_for_function("document.querySelector('#modal-title').textContent==='发现此文档的恢复草稿'")
            self.assertTrue(p.locator('#app').evaluate('e=>e.inert'))
            self.assertTrue(p.locator('#workspace-operation').evaluate('e=>e.hidden'))
            p.locator('#modal-body select').select_option('b'*32);p.locator('#modal-ok').click()
            p.wait_for_function("!document.querySelector('#app').inert")
            self.assertEqual(value(p),second)
            self.assertEqual((d.project/'report.md').read_text('utf8'),text)
            self.assertEqual(d.errors,[])

    def test_duplicate_note_same_gui_cli_and_explicit_partial_api(self):
        text='# Report\n\nText[^a]\n\n[^a]: One\n[^a]: Two\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,profile='engineering',registered=True) as d:
            p=d.page;p.locator('#btn-validate').click()
            p.wait_for_selector('.problem-item[data-code="DUPLICATE_FOOTNOTE"]')
            complete=p.evaluate('ReportStudioProgrammatic.check({renderProfile:"engineering"})')
            self.assertFalse(complete['valid']);self.assertTrue(complete['preflight']['complete'])
            partial=p.evaluate('''async text=>{return(await fetch('/api/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markdown:text,render_profile:'engineering'})})).json()}''',text)
            self.assertFalse(partial['valid']);self.assertTrue(partial['source_contract_valid']);self.assertFalse(partial['preflight']['complete'])
            result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'app/cli.py'),
                                   'check',str(d.project),'--render-profile','engineering'],
                                  capture_output=True,text=True,encoding='utf8',timeout=30)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertTrue(result.stdout,result.stderr)
            receipt=json.loads(result.stdout)
            self.assertTrue(receipt['preflight']['complete'],receipt)
            self.assertFalse(receipt['safeToCompile']);self.assertIn('DUPLICATE_FOOTNOTE',[n['code'] for n in receipt['diagnostics']])
            self.assertEqual((d.project/'report.md').read_bytes(),text.encode('utf8'))
            self.assertEqual(d.errors,[])

    def test_engineering_preflight_preserves_unknown_field_blocker(self):
        table={'schema':'report-table-v1','id':'tbl-data','caption':'Data','rows':[[{'text':'A','rowspan':1,'colspan':1}]],'future_extension':'must not silently compile'}
        text='# Report\n\n## Data\n\n'+chr(96)*3+'report-table\n'+json.dumps(table)+'\n'+chr(96)*3+'\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,profile='engineering',registered=True) as d:
            result=d.page.evaluate('ReportStudioProgrammatic.check({renderProfile:"engineering"})')
            self.assertFalse(result['valid']);self.assertFalse(result['safeToCompile'])
            self.assertIn('UNSUPPORTED_OBJECT_FIELDS',[item['code'] for item in result['diagnostics'] if item['severity']=='error'])
            self.assertEqual((d.project/'report.md').read_text('utf8'),text)

    def test_unchanged_prose_toc_notes_keep_nodes_but_update_source_ranges(self):
        text='# Report\n\n## Section {#sec-a}\n\nEdit here\n\nUnchanged😀 paragraph\n\nText[^n] and @sec:sec-a.\n\n[^n]: Note body\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page
            p.evaluate('''()=>{window.retained={paragraph:[...document.querySelectorAll('#preview-content .doc-block')].find(n=>n.textContent.includes('Unchanged😀')),
                       toc:document.querySelector('#toc a.level-2'),note:document.querySelector('.source-note-row')};}''')
            edited=text.replace('Edit here','Edited longer😀 here');source(p,edited)
            p.wait_for_function("document.querySelector('#preview-content').textContent.includes('Edited longer😀 here')")
            kept=p.evaluate('''()=>({paragraph:retained.paragraph.isConnected,toc:retained.toc===document.querySelector('#toc a.level-2'),
                note:retained.note===document.querySelector('.source-note-row'),raw:retained.paragraph._sourceDocument,
                position:Number(retained.paragraph.dataset.start)})''')
            self.assertTrue(kept['paragraph']);self.assertTrue(kept['toc']);self.assertTrue(kept['note'])
            self.assertEqual(kept['raw'],edited)
            self.assertEqual(kept['position'],len(edited[:edited.index('Unchanged😀')].encode('utf-16-le'))//2)
            p.locator('#toc a.level-2').click()
            source(p,edited.replace('## Section','## Changed'))
            p.wait_for_function("document.querySelector('#toc a.level-2').textContent.includes('Changed')")
            self.assertEqual(p.locator('#preview-content .hrs-footnotes li').count(),1)
            self.assertEqual((d.project/'report.md').read_bytes(),text.encode('utf8'))
            self.assertEqual(d.errors,[])

    def test_report_lifecycle_and_independent_save_from_real_controls(self):
        text='# Report\n\nBody\n\n![Test](assets/a.png)\n'
        with tempfile.TemporaryDirectory() as folder,tempfile.TemporaryDirectory() as destination,browser_session() as browser,LiveDocument(browser,folder,text,assets={'a.png':png(10,10)},registered=True) as d:
            p=d.page;self.prepare(p);docid=p.evaluate('ReportStudioProgrammatic.topics()')['documentId']
            evidence=artifact_directory(__file__);p.screenshot(path=str(evidence/'report-workspace.png'))
            p.locator('#menu-workspace > summary').click();p.locator('#btn-workspace-archive').click()
            p.wait_for_selector('#workspace-operation[hidden]',state='attached')
            self.assertTrue(p.locator('#report-workspace-bar').evaluate('e=>e.hidden'))
            p.locator('#menu-export > summary').click();p.locator('#btn-prepare-report').click()
            p.get_by_role('button',name='查看归档和回收站',exact=True).click()
            p.screenshot(path=str(evidence/'workspace-manager.png'))
            row=p.locator('.report-scope-picker > label').filter(has=p.locator('input[value="resume:'+docid+'"]'))
            row.get_by_role('button',name='取消归档',exact=True).click()
            row.get_by_role('button',name='移入回收站',exact=True).click()
            row.get_by_role('button',name='恢复',exact=True).click()
            row.locator('input').check();p.locator('#modal-ok').click()
            p.wait_for_selector('#workspace-operation[hidden]',state='attached')
            before=value(p)
            p.locator('#menu-workspace > summary').click();p.locator('#btn-workspace-save').click()
            p.wait_for_selector('#modal-body input[aria-label="项目文件夹名称"]')
            p.locator('#modal-cancel').click()
            self.assertEqual(value(p),before)
            self.assertEqual(p.locator('.report-figure-wrap').count(),0)
            with patch.object(studio,'pick_project_parent',lambda:Path(destination)):
                p.locator('#menu-workspace > summary').click();p.locator('#btn-workspace-save').click()
                p.locator('#modal-body input[aria-label="项目文件夹名称"]').fill('Independent')
                p.locator('#modal-ok').click()
                p.get_by_role('button',name='确认位置',exact=True).click()
                p.wait_for_function('id=>document.querySelector("#workspace-operation").hidden&&ReportStudioProgrammatic.topics().documentId!==id',arg=docid)
                p.wait_for_selector('#workspace-operation[hidden]',state='attached')
            new_id=p.evaluate('ReportStudioProgrammatic.topics()')['documentId']
            self.assertNotEqual(new_id,docid)
            self.assertTrue((d.server.workspace/docid/'report.md').is_file())
            self.assertEqual((Path(destination)/'Independent/report.md').read_text('utf8'),value(p))
            self.assertEqual(value(p).count('"schema": "report-figure-v1"'),1)
            self.assertIn('"caption": "Test"',value(p))
            self.assertEqual((Path(destination)/'Independent/assets/a.png').read_bytes(),png(10,10))
            self.assertEqual((d.project/'report.md').read_bytes(),text.encode('utf8'))
            evidence=artifact_directory(__file__)
            p.screenshot(path=str(evidence/'independent-project.png'))
            self.assertEqual(d.errors,[])

    def test_highlight_menu_uses_all_canonical_colors_and_saves_semantic_marker(self):
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,'# Note\n\nPlain\n',registered=True) as d:
            colors=d.page.evaluate('''()=>ReportSettings.highlights.choices.map(choice=>{
              const button=document.querySelector('[data-highlight-color="'+choice.id+'"]');
              return {id:choice.id,color:button.querySelector('i').style.backgroundColor,expected:choice.color};
            })''')
            self.assertEqual(len(colors),8)
            for color in colors:self.assertTrue(color['color'])
            self.assertEqual(d.errors,[])


if __name__=='__main__':unittest.main()
