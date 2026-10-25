"""FRONTEND-02/05: native input ownership and collectible table sessions."""
import unittest
import io,json,sys,subprocess
from pathlib import Path
from PIL import Image
from browser_support import ManualService, source, value, LiveDocument


class FrontendFeedback(ManualService):
    initial_markdown='# Regression\n\nOriginal.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n'

    def test_native_search_undo_redo_does_not_change_document(self):
        p=self.page;changed=self.initial_markdown+'\nAdded paragraph.\n';source(p,changed)
        p.wait_for_function("document.querySelector('#preview-content').textContent.includes('Added paragraph')")
        p.keyboard.press('Control+f');field=p.locator('#search-query');field.press_sequentially('keyword')
        for key in ['Control+z','Control+Shift+z','Control+y']:
            field.press(key)
            self.assertEqual(value(p),changed, 'Native input shortcut modified Markdown: '+key)
            self.assertEqual(p.evaluate('document.activeElement.id'),'search-query')
        p.keyboard.press('Escape');p.evaluate("document.querySelector('#markdown').sourceEditor.focus()")
        p.keyboard.press('Control+z');self.assertEqual(value(p),self.initial_markdown)
        p.keyboard.press('Control+Shift+z');self.assertEqual(value(p),changed)

    def test_repeated_table_sessions_release_handlers_and_old_widgets(self):
        p=self.page;cdp=self.document.context.new_cdp_session(p)
        def listeners():
            group='hrs-table-audit'
            body=cdp.send('Runtime.evaluate',{'expression':'document.querySelector("#modal-body")','objectGroup':group})['result']['objectId']
            try:return len([e for e in cdp.send('DOMDebugger.getEventListeners',{'objectId':body})['listeners'] if e['type']=='keydown'])
            finally:cdp.send('Runtime.releaseObjectGroup',{'objectGroup':group})
        def open_table():
            p.locator('#preview-content .report-table-wrap td').first.dblclick()
            # This pinned driver's Locator.wait_for leaves a remote element
            # handle alive. Await a boolean so the observer cannot retain grids.
            p.wait_for_function("document.querySelector('.table-edit-grid')?.getClientRects().length>0")
        open_table();p.locator('#modal-cancel').click();baseline=listeners()
        # Taking a heap snapshot runs coordinated native/JS collection. A lone
        # HeapProfiler.collectGarbage leaves Blink's idle caches measurable.
        cdp.on('HeapProfiler.addHeapSnapshotChunk',lambda event:None)
        cdp.send('Runtime.discardConsoleEntries')
        cdp.send('HeapProfiler.takeHeapSnapshot',{'reportProgress':False})
        before=cdp.send('Memory.getDOMCounters')
        for n in range(20):
            open_table()
            if n==0:p.evaluate("window._oldTableWidget=new WeakRef(document.querySelector('.table-edit-grid'))")
            p.set_viewport_size({'width':1600+n%2,'height':1000})
            if n%3==0:p.locator('#modal-cancel').click()
            elif n%3==1:p.locator('#modal-close').click()
            else:p.keyboard.press('Escape')
        cdp.send('Runtime.discardConsoleEntries')
        cdp.send('HeapProfiler.takeHeapSnapshot',{'reportProgress':False})
        after=cdp.send('Memory.getDOMCounters')
        print('Table lifetime:',{'before':before,'after':after,'body_keydown_before':baseline,'body_keydown_after':listeners()},flush=True)
        self.assertEqual(listeners(),baseline,'Persistent modal container retains each old table session')
        self.assertFalse(p.evaluate('!!window._oldTableWidget.deref()'),'Detached table widget remains strongly retained')
        self.assertEqual(value(p),self.initial_markdown)
        open_table();title=p.locator('.table-caption-input');title.press_sequentially('Updated')
        title.press('Control+z');self.assertEqual(title.input_value(),'')
        title.press('Control+Shift+z');self.assertEqual(title.input_value(),'Updated')
        p.locator('#modal-ok').click()
        p.wait_for_function("document.querySelector('#preview-content').textContent.includes('Updated')")
        self.assertIn('Updated',value(p))

    def test_relative_images_preview_save_export_and_recovery_share_paths(self):
        data=io.BytesIO();Image.new('RGB',(24,16),'blue').save(data,'PNG');image=data.getvalue()
        raw=('# Paths\r\n\r\n![Flat](./assets/a.png)\r\n\r\n![Nested](assets/sub/a.png)\r\n\r\n'
             'Inline ![icon](./assets/sub/a.png) text.\r\n\r\n<div><img src="./assets/sub/a.png" alt="HTML"></div>\r\n')
        with LiveDocument(self.browser,self.folder/'relative-images',raw,assets={'a.png':image,'sub/a.png':image},registered=True) as doc:
            p=doc.page
            p.wait_for_function("[...document.querySelectorAll('#preview-content img')].length===4")
            p.locator('#preview-content img').last.scroll_into_view_if_needed()
            p.wait_for_function("[...document.querySelectorAll('#preview-content img')].every(n=>n.complete&&n.naturalWidth===24)")
            self.assertEqual(p.locator('#preview-content .warning-pill').count(),0)
            html=doc.export()
            archive=p.evaluate('''async html=>{const t=document.createElement('template');t.innerHTML=html;return ReportExportArchive.readArchive(JSON.parse(t.content.querySelector('#report-source').textContent),t.content)}''',html)
            self.assertEqual(archive['markdown'],raw)
            self.assertEqual(set(archive['assets']),{'a.png','sub/a.png'})
            self.assertEqual((doc.project/'report.md').read_bytes(),raw.encode('utf8'))
            path=self.folder/'relative.html';path.write_bytes(html.encode('utf8'));restored=self.folder/'relative-restored'
            done=subprocess.run([sys.executable,'-X','utf8','-B',str(Path(__file__).resolve().parents[1]/'app/html_cli.py'),
                                 'recover',str(path),'--output',str(restored)],capture_output=True,text=True,encoding='utf8',timeout=40)
            self.assertEqual(done.returncode,0,done.stdout+done.stderr)
            self.assertEqual((restored/'report.md').read_bytes(),raw.encode('utf8'))
            self.assertEqual((restored/'assets/sub/a.png').read_bytes(),image)
            p.locator('#btn-save').click()
            p.wait_for_function("document.querySelector('#save-indicator').textContent.includes('已保存')")
            text=value(p);self.assertEqual(text.count('"schema": "report-figure-v1"'),2)
            self.assertIn('"src": "assets/sub/a.png"',text)
            self.assertEqual((doc.project/'report.md').read_bytes(),text.encode('utf8'))
            # Saved object URLs may encode directory separators; export must
            # embed them just like the original Markdown images.
            self.assertIn('report-source',doc.export())
            p.keyboard.press('Control+z');self.assertEqual(value(p),raw)
            p.keyboard.press('Control+y');self.assertEqual(value(p),text)
            self.assertEqual((doc.project/'assets/sub/a.png').read_bytes(),image)
            self.assertFalse(doc.errors,doc.errors)


if __name__=='__main__':unittest.main(verbosity=2)
