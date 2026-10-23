"""NOTEBOOK-01/SPACE-01/IMAGE-01: real preview, scope, export and image scheduling."""
from pathlib import Path
import json
import hashlib
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib
from browser_support import LiveDocument, browser_session, source, value

def png(index,width=64,height=40):
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    row=b'\0'+bytes((index%256,80,140))*width
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(row*height))+chunk(b'IEND',b'')


class NotebookViews(unittest.TestCase):
    def test_pending_profile_request_locks_overlapping_display_controls(self):
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,Path(folder),'# A\n\n\nText\n',registered=True) as doc:
            page=doc.page;pending=[]
            page.wait_for_function("!document.querySelector('#render-profile').disabled")
            page.route('**/api/render-profile',lambda route:pending.append(route))
            page.locator('#render-profile').select_option('engineering')
            page.wait_for_function("document.querySelector('#render-profile').disabled")
            self.assertTrue(page.locator('#preserve-blank-lines').is_disabled())
            self.assertTrue(page.locator('#color-theme').is_disabled())
            saves=[];page.on('request',lambda request:saves.append(request) if request.url.endswith('/api/save') else None)
            page.keyboard.press('Control+S');self.assertEqual(saves,[])
            self.assertEqual(len(pending),1);pending[0].continue_();page.unroute('**/api/render-profile')
            page.wait_for_function("!document.querySelector('#render-profile').disabled")
            page.wait_for_function("document.querySelector('#save-indicator').textContent.includes('已保存')")
            self.assertEqual(json.loads((doc.project/'meta.json').read_text('utf8'))['render_profile'],'engineering')
            page.locator('#render-profile').select_option('free')
            page.locator('#preserve-blank-lines').check();page.wait_for_selector('.hrs-blank-space')
            self.assertTrue(json.loads((doc.project/'meta.json').read_text('utf8'))['render_options']['preserve_blank_lines'])

    def test_spaces_scope_global_numbers_and_navigation(self):
        figure=lambda i: '```report-figure\n'+json.dumps({'schema':'report-figure-v1','id':'fig-'+i,'kind':'mermaid','source':'flowchart LR\n A-->B','caption':i})+'\n```\n'
        text='# A {#sec-a}\n\n\n第一段\n\n\n第二段[^a] 与[链接][ref]\n\n| 参数 |\n| --- |\n| x |\n: 参数表 {#tbl-a}\n\n'+figure('a')+'\n# B {#sec-b}\n\n见 @fig:fig-a 和 @sec:sec-a 及 @tbl:tbl-a。\n\n'+figure('b')+'\n[^a]: 注释\n\n[ref]: https://example.com/\n'
        with tempfile.TemporaryDirectory() as folder, browser_session() as browser, LiveDocument(browser, Path(folder), text, registered=True) as doc:
            page=doc.page
            page.locator('#preserve-blank-lines').check()
            page.wait_for_selector('#preview-content .hrs-blank-space')
            self.assertEqual(page.locator('#preview-content .hrs-blank-space').count(),2)
            self.assertGreater(page.locator('.hrs-blank-space').first.bounding_box()['height'],15)
            page.locator('#show-object-numbers').check()
            page.locator('#topic-select').select_option(label='2 · B')
            page.wait_for_function("document.querySelectorAll('#preview-content h1').length===1 && document.querySelector('#preview-content h1').textContent==='B'")
            self.assertEqual(page.locator('#preview-content .report-figure-caption').inner_text(),'图 2 b')
            self.assertEqual(page.locator('#preview-content .object-xref-invalid').count(),0)
            self.assertEqual(page.locator('#preview-content .object-xref').first.inner_text(),'图 1')
            self.assertEqual(page.locator('#preview-content .object-xref').last.inner_text(),'表 1')
            page.locator('#preview-content .object-xref').first.click()
            page.wait_for_function("document.querySelector('#preview-content h1').textContent==='A'")
            self.assertEqual(page.locator('#preview-content a[href="https://example.com/"]').inner_text(),'链接')
            self.assertEqual(value(page),text)
            self.assertEqual((doc.project/'report.md').read_text('utf8'),text)
            self.assertEqual(doc.errors,[])

    def test_whole_export_ignores_focus_and_keeps_source(self):
        text='# One\n\nFirst\n\n# Two\n\nSecond\n'
        with tempfile.TemporaryDirectory() as folder, browser_session() as browser, LiveDocument(browser, Path(folder), text, registered=True) as doc:
            doc.page.locator('#topic-select').select_option(label='2 · Two')
            doc.page.wait_for_function("document.querySelectorAll('#preview-content h1').length===1")
            html=doc.export()
            self.assertIn('First',html);self.assertIn('Second',html)
            self.assertEqual(doc.page.locator('#preview-content h1').inner_text(),'Two')
            self.assertEqual(value(doc.page),text)

    def test_module_ui_zip_dependencies_and_real_recovery(self):
        table={'schema':'report-table-v1','id':'tbl-a','caption':'表题[^n]','rows':[[{'text':'内容','rowspan':1,'colspan':1}]]}
        group='::: {#fig-group layout-ncol=2}\r\n![子图\\[^g\\]](assets/a.png)\r\n![另一张](assets/a.png)\r\n\r\n组图[^n]\r\n:::\r\n'
        text='前言\r\n\r\n# 同名\r\n\r\n![甲](assets/a.png)\r\n\r\n```report-table\r\n'+json.dumps(table,ensure_ascii=False)+'\r\n```\r\n\r\n'+group+'\r\n# 同名\r\n\r\n![乙](assets/b.png)\r\n\r\n[^n]: 外部说明 $\\alpha$\r\n\r\n[^g]: 子图说明\r\n'
        assets={'a.png':png(1),'b.png':png(2),'unused.png':png(3)}
        with tempfile.TemporaryDirectory() as folder, browser_session() as browser, LiveDocument(browser, Path(folder), text, assets=assets, registered=True) as doc:
            page=doc.page
            page.locator('#menu-export > summary').click();page.locator('#btn-export').click()
            page.locator('input[name="export-scope"][value="modules"]').check()
            choices=page.locator('input[data-topic-key]')
            self.assertEqual(choices.count(),3)
            choices.nth(1).check();choices.nth(2).check()
            with page.expect_response(lambda r:'/api/export/modules/finish' in r.url) as pending:
                page.locator('#modal-ok').click()
            receipt=pending.value.json();self.assertTrue(receipt['ok'],receipt)
            with zipfile.ZipFile(receipt['path']) as archive:
                self.assertIsNone(archive.testzip());self.assertEqual(len(archive.namelist()),2)
                self.assertNotEqual(*archive.namelist())
                files=[archive.read(name).decode('utf8') for name in archive.namelist()]
            restored=[]
            for html in files:
                restored.append(page.evaluate('''async html=>{const d=new DOMParser().parseFromString(html,'text/html');return ReportExportArchive.readArchive(JSON.parse(d.querySelector('#report-source').textContent),d)}''',html))
            self.assertEqual(set(restored[0]['assets']),{'a.png'})
            self.assertEqual(set(restored[1]['assets']),{'b.png'})
            self.assertEqual(restored[0]['markdown'].count('[^n]:'),1)
            self.assertEqual(restored[0]['markdown'].count('[^g]:'),1)
            self.assertIn('[^n]: 外部说明',restored[0]['markdown'])
            self.assertNotIn('[^n]:',restored[1]['markdown'])
            self.assertEqual(value(page),text)
            self.assertEqual((doc.project/'report.md').read_bytes(),text.encode('utf8'))
            html_path=Path(folder)/'module.html';html_path.write_text(files[0],encoding='utf8')
            recovered=Path(folder)/'recovered'
            process=subprocess.run([sys.executable,'-X','utf8','-B',str(Path(__file__).resolve().parents[1]/'app/html_cli.py'),'recover',str(html_path),'--output',str(recovered)],capture_output=True,text=True,encoding='utf8',timeout=45)
            self.assertEqual(process.returncode,0,process.stdout+process.stderr)
            self.assertEqual((recovered/'report.md').read_bytes(),restored[0]['markdown'].encode('utf8'))
            self.assertEqual(hashlib.sha256((recovered/'assets/a.png').read_bytes()).digest(),hashlib.sha256(assets['a.png']).digest())
            self.assertEqual(doc.errors,[])

    def test_cross_module_and_changed_source_never_leave_partial_delivery(self):
        with tempfile.TemporaryDirectory() as folder, browser_session() as browser, LiveDocument(browser, Path(folder),'# A\n\n见 @sec:sec-b。\n\n# B {#sec-b}\n\n乙\n',registered=True) as doc:
            page=doc.page
            plan=page.evaluate('()=>ReportStudioProgrammatic.topics()');keys=[t['key'] for t in plan['topics']]
            with self.assertRaisesRegex(Exception,'跨专题'):
                page.evaluate('p=>ReportStudioProgrammatic.exportModules(p.keys,{expectSourceSha256:p.sha})',{'keys':keys,'sha':plan['sourceSha256']})
            self.assertEqual(list((doc.project/'output').iterdir()),[])
            self.assertEqual(doc.server.module_exports.jobs,{})
            clean='# A\n\n甲\n\n# B\n\n乙\n';source(page,clean)
            page.wait_for_function("document.querySelector('#preview-content').textContent.includes('甲')")
            plan=page.evaluate('()=>ReportStudioProgrammatic.topics()');keys=[t['key'] for t in plan['topics']]
            def change_source(route):
                (doc.project/'report.md').write_text('# 外部修改\n',encoding='utf8');route.continue_()
            page.route('**/api/export/modules/finish',change_source)
            with self.assertRaisesRegex(Exception,'变化'):
                page.evaluate('p=>ReportStudioProgrammatic.exportModules(p.keys,{expectSourceSha256:p.sha})',{'keys':keys,'sha':plan['sourceSha256']})
            self.assertEqual(list((doc.project/'output').iterdir()),[])
            self.assertEqual(doc.server.module_exports.jobs,{})
            self.assertEqual((doc.project/'report.md').read_text('utf8'),'# 外部修改\n')

    def test_lazy_images_focus_and_edit_keep_viewport(self):
        assets={f'{i}.png':png(i,960,540) for i in range(50)}
        text=''.join('# Topic '+str(topic)+'\n\n'+''.join(f'![{i}](assets/{i}.png)\n\n' for i in range(topic*10,(topic+1)*10)) for topic in range(5))
        text=text.replace('# Topic 0\n\n','# Topic 0\n\n<img src="assets/0.png" width="64" height="32">\n\n')
        init="window._decodeCalls=0;const original=HTMLImageElement.prototype.decode;HTMLImageElement.prototype.decode=function(){window._decodeCalls++;return original.apply(this,arguments)};"
        with tempfile.TemporaryDirectory() as folder, browser_session() as browser, LiveDocument(browser, Path(folder),text,assets=assets,registered=True,init_script=init) as doc:
            page=doc.page
            page.wait_for_function("document.querySelector('#preview-content img')?.naturalWidth>0")
            self.assertEqual(page.locator('#preview-content img').first.get_attribute('width'),'64')
            self.assertEqual(page.locator('#preview-content img').first.get_attribute('height'),'32')
            self.assertEqual(page.evaluate('window._decodeCalls'),0)
            self.assertLess(page.evaluate("[...document.querySelectorAll('#preview-content img')].filter(i=>i.naturalWidth).length"),50)
            self.assertTrue(page.evaluate("[...document.querySelectorAll('#preview-content img')].every(i=>i.loading==='lazy')"))
            page.locator('#topic-select').select_option(label='4 · Topic 3')
            page.wait_for_function("document.querySelectorAll('#preview-content img').length===10")
            self.assertTrue(page.evaluate("[...document.querySelectorAll('#preview-content img')].every(i=>Number(i.alt)>=30&&Number(i.alt)<40)"))
            page.locator('#follow-scroll').uncheck()
            page.locator('#preview-content img').nth(5).scroll_into_view_if_needed()
            page.wait_for_timeout(150)
            before=page.locator('#preview-content img').nth(5).bounding_box()['y']
            source(page,text+'\n尾部修改\n')
            page.wait_for_timeout(450)
            after=page.locator('#preview-content img').nth(5).bounding_box()['y']
            self.assertLess(abs(after-before),5)
            self.assertEqual(page.evaluate('window._decodeCalls'),0)
            self.assertEqual(doc.errors,[])

    def test_options_modes_search_and_source_bound_selection(self):
        text='# Alpha\n\n\nfirst\n\n# Beta\n\n\nsecond needle\n'
        with tempfile.TemporaryDirectory() as folder, browser_session() as browser, LiveDocument(browser,Path(folder),text,registered=True) as doc:
            page=doc.page
            self.assertFalse(page.locator('#preserve-blank-lines').is_checked())
            page.locator('#preserve-blank-lines').check();page.wait_for_selector('.hrs-blank-space')
            self.assertTrue(json.loads((doc.project/'meta.json').read_text('utf8'))['render_options']['preserve_blank_lines'])
            page.locator('#render-profile').select_option('engineering')
            page.wait_for_function("document.querySelector('#preview-content').dataset.hrsRenderProfile==='engineering'")
            self.assertEqual(page.locator('.hrs-blank-space').count(),0)
            page.locator('#render-profile').select_option('free');page.wait_for_selector('.hrs-blank-space')
            page.locator('#topic-select').select_option(label='1 · Alpha')
            page.wait_for_function("document.querySelectorAll('#preview-content h1').length===1")
            page.locator('#btn-search').click();page.locator('#search-scope').select_option('source');page.locator('#search-query').fill('needle')
            page.wait_for_function("document.querySelector('#topic-select').selectedOptions[0].textContent.includes('Beta')")
            page.locator('#search-close').click()
            plan=page.evaluate('()=>ReportStudioProgrammatic.topics()')
            source(page,text+'\nchanged\n')
            with self.assertRaisesRegex(Exception,'快照已变化'):
                page.evaluate('p=>ReportStudioProgrammatic.exportModules([p.topics[0].key],{expectSourceSha256:p.sourceSha256})',plan)
            self.assertEqual(list((doc.project/'output').iterdir()),[])
            page.evaluate("()=>ReportStudioProgrammatic.open('new')")
            page.locator('#render-profile').select_option('free')
            page.wait_for_function("document.querySelector('#preserve-blank-lines').checked")
            self.assertTrue(page.locator('#preserve-blank-lines').is_checked())
            self.assertEqual(page.locator('#topic-select').input_value(),'')
            self.assertEqual((doc.project/'report.md').read_text('utf8'),text)


if __name__=='__main__':
    unittest.main(verbosity=2)
