"""MDI-01: actual import button, server, assets, drafts and first-save flow.

Only the native OS picker result is substituted. The reading-pack entry is
never used and no import endpoint is stubbed.
"""
from pathlib import Path
import json,os,sys,unittest,hashlib,tempfile,subprocess
from browser_support import ManualService
from test_pf1310_rc2_browser import value
from test_pf1310_rc2_browser import source
import studio

SAMPLE=Path(os.environ.get('HRS_MD_SAMPLE',str(Path(__file__).resolve().parent/'fixtures/fp_hartmann/REPORT.md')))

class LocalImport(ManualService):
    def setUp(self):
        super().setUp();self.old_picker=getattr(studio,'pick_import_file',None);self.picks=[];self.selected=SAMPLE
        def choose():self.picks.append(True);return self.selected
        studio.pick_import_file=choose
    def tearDown(self):
        if self.old_picker is not None:studio.pick_import_file=self.old_picker
        super().tearDown()
    def click_import(self):
        self.page.locator('#menu-open>summary').click();self.page.locator('#btn-import').click()
    def wait_images(self):
        try:
            self.page.wait_for_function("document.querySelectorAll('#preview-content img').length===7")
            # Request the existing lazy resources for this availability check;
            # an off-screen deferred image is not a missing file. The product
            # keeps its normal lazy-loading policy.
            self.page.wait_for_function("()=>{const images=[...document.querySelectorAll('#preview-content img')];for(const i of images)i.loading='eager';return images.length===7&&images.every(i=>i.naturalWidth>0)}")
        except Exception:
            print('IMPORT DEBUG',json.dumps(self.page.evaluate("()=>({url:location.href,source:document.querySelector('#markdown').value?.slice(0,180),images:[...document.querySelectorAll('#preview-content img')].map(i=>({src:i.src,width:i.naturalWidth,complete:i.complete})),modal:document.querySelector('#modal-layer').textContent,confirm:document.querySelector('.confirm-window')?.textContent})"),ensure_ascii=False),flush=True)
            if self.evidence:self.page.screenshot(path=str(self.evidence/'failed.png'))
            raise
        self.assertEqual(len(self.picks),1);self.assertFalse(self.page.locator('#modal-layer').is_visible())
        self.assertEqual(self.page.locator('#reader-overlay').count(),1)
        self.assertFalse(self.page.locator('#reader-overlay').is_visible())

    def test_01_real_report_one_selection_preview_save_reopen_export(self):
        raw=SAMPLE.read_bytes();self.click_import();self.wait_images();imported=value(self.page)
        self.assertNotIn('](figures/',imported);self.assertIn('](assets/',imported)
        self.page.locator('#btn-save').click();self.page.wait_for_selector('#modal-body input')
        self.page.locator('#modal-body input').first.fill('MD相对图片导入')
        self.page.locator('#modal-ok').click();self.page.locator('.confirm-window button').filter(has_text='确认位置').click()
        self.page.wait_for_function("/已保存|正式保存失败/.test(document.querySelector('#save-indicator').textContent)")
        self.assertNotIn('失败',self.page.locator('#save-indicator').inner_text(),self.page.locator('#toast').inner_text())
        saved=self.destination/'MD相对图片导入';normalized=value(self.page)
        self.assertEqual(normalized.count('"schema": "report-figure-v1"'),7)
        self.assertEqual(self.page.locator('.report-figure-wrap').count(),7)
        self.assertEqual((saved/'report.md').read_bytes(),normalized.encode('utf8'))
        self.assertEqual(len(list((saved/'assets').glob('*.png'))),7)
        self.page.reload();self.page.evaluate('()=>ReportStudioProgrammatic.ready()')
        self.page.locator('#recent-list button').filter(has_text='波监 FP').first.click();self.wait_images()
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        from studio import audit_export
        audit_export(html)
        output=self.folder/'imported.html';output.write_bytes(html.encode('utf8'));restored=self.folder/'restored'
        subprocess.run([sys.executable,'-X','utf8','-B',str(Path(studio.__file__).with_name('html_cli.py')),
                        'recover',str(output),'--output',str(restored)],check=True,capture_output=True,timeout=40)
        self.assertEqual((restored/'report.md').read_bytes(),normalized.encode('utf8'))
        self.assertEqual({p.name:p.read_bytes() for p in (saved/'assets').iterdir()},
                         {p.name:p.read_bytes() for p in (restored/'assets').iterdir()})
        self.assertEqual(SAMPLE.read_bytes(),raw)
        if self.evidence:
            self.page.screenshot(path=str(self.evidence/'imported.png'))
            (self.evidence/'result.json').write_text(json.dumps({'images':7,'native_file_selections':1,'per_image_prompts':0,'source_sha256':hashlib.sha256(raw).hexdigest(),'source_unchanged':True,'saved_and_recovered':True,'reading_pack_used':False},ensure_ascii=False,indent=2),encoding='utf8')

    def test_02_cancel_keeps_current_source_and_draft(self):
        source(self.page,'# 当前未保存的稿件\n\n请保留。\n')
        before=value(self.page);self.selected=None;self.click_import()
        self.page.wait_for_function("!document.querySelector('#btn-import').disabled")
        self.assertEqual(value(self.page),before);self.assertEqual(len(self.picks),1)
        self.assertFalse(self.page.locator('#modal-layer').is_visible())

    def test_03_missing_images_preserve_current_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.selected=Path(tmp)/'bad.md';self.selected.write_bytes(b'# Bad\n\n![A](missing-a.png)\n![B](missing-b.png)\n')
            source(self.page,'# 当前未保存的稿件\n\n请保留。\n')
            before=value(self.page);self.click_import();self.page.wait_for_function("document.querySelector('#toast').textContent.includes('2 项')")
            self.assertEqual(value(self.page),before);self.assertFalse(self.page.locator('#modal-layer').is_visible())

    def test_04_picker_requires_same_origin_and_rejects_supplied_paths(self):
        result=self.page.evaluate("async()=>{const r=await fetch('/api/import/local-file',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});return r.status}")
        self.assertEqual(result,403);self.assertEqual(self.picks,[])
        result=self.page.evaluate("async()=>{const r=await fetch('/api/import/local-file',{method:'POST',headers:{'Content-Type':'application/json','X-HRS-Project-Action':'user-action'},body:JSON.stringify({path:'C:/arbitrary.md'})});return r.status}")
        self.assertEqual(result,400);self.assertEqual(self.picks,[])

    def test_05_same_import_menu_keeps_html_archive_profile_and_source(self):
        original=value(self.page)
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        self.selected=self.folder/'archive.html';self.selected.write_bytes(html.encode('utf8'))
        self.click_import();self.page.wait_for_function("document.querySelector('#toast').textContent.includes('已导入为未保存草稿')")
        self.assertEqual(value(self.page),original);self.assertEqual(len(self.picks),1)
        self.assertEqual(self.page.locator('#render-profile').input_value(),'free')

    def test_06_invalid_html_does_not_discard_unsaved_source(self):
        source(self.page,'# 当前未保存的稿件\n\n请保留。\n');before=value(self.page)
        self.selected=self.folder/'unrelated.html';self.selected.write_bytes(b'<p>Not an HRS archive</p>')
        self.click_import();self.page.wait_for_function("document.querySelector('#toast').textContent.includes('这不是由本工具导出')")
        self.assertEqual(value(self.page),before);self.assertFalse(self.page.locator('#modal-layer').is_visible())

    def test_07_cancel_first_save_keeps_plain_image_source_until_commit(self):
        """RELEASE-REVIEW-01: cancelling the folder dialog must not rewrite images."""
        self.click_import();self.wait_images();before=value(self.page)
        projects=set(self.destination.iterdir())
        self.page.locator('#btn-save').click()
        self.page.wait_for_selector('#modal-body input[aria-label="项目文件夹名称"]')
        self.page.locator('#modal-cancel').click()
        self.page.wait_for_function('!document.querySelector("#modal-layer").checkVisibility()')
        self.assertEqual(value(self.page),before)
        self.assertEqual(self.page.locator('.report-figure-wrap').count(),0)
        self.assertEqual(set(self.destination.iterdir()),projects)

if __name__=='__main__':unittest.main()
