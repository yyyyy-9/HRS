"""PROFILE-01: real service, local browser, profile metadata and original archive/CLI."""
import json
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import zipfile
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(ROOT))
from studio import StudioServer,TEMPLATES
from portable_host import PortableHandler,WindowSessions
from html_cli import export_html,recover_html

SOURCE='# 报告\r\n\r\n> 摘要：说明范围。\r\n\r\n## 背景\r\n\r\n### 方法\r\n\r\n1. 第一个\r\n2. 第二个\r\n\r\n## 结论\r\n\r\n<div style="display:flex"><p>自由卡片</p></div>\r\n'

def main():
    assert '## 摘要' not in TEMPLATES['engineering']['markdown']
    assert '> 摘要：' in TEMPLATES['engineering']['markdown']
    with tempfile.TemporaryDirectory(prefix='hrs-profile-') as d:
        folder=Path(d);project=folder/'project';project.mkdir();(project/'assets').mkdir()
        original=SOURCE.encode('utf8');(project/'report.md').write_bytes(original)
        class Quiet(PortableHandler):
            def log_message(self,*args):pass
        server=StudioServer(('127.0.0.1',0),project,folder/'workspace');server.RequestHandlerClass=Quiet
        server.portable_lifecycle=WindowSessions('profile-test',enabled=False)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        browser=os.environ.get('CHROMIUM_PATH',r'C:\Program Files\Google\Chrome\Application\chrome.exe')
        try:
            with sync_playwright() as p:
                client=p.chromium.launch(executable_path=browser,headless=True)
                page=client.new_page(viewport={'width':1440,'height':1000})
                page.goto(f'http://127.0.0.1:{server.server_port}/web/index.html?programmatic=1')
                page.evaluate("async()=>{await ReportStudioProgrammatic.ready();await ReportStudioProgrammatic.open('legacy')}")
                # Old projects stay free until explicitly selected; profile alone never rewrites source.
                assert page.locator('#render-profile').input_value()=='free'
                assert page.locator('#preview-content [style*="display: flex"]').count()==1
                page.select_option('#render-profile','engineering')
                page.wait_for_function("document.querySelector('#toc').textContent.includes('1 背景')")
                assert page.locator('#preview-content .hrs-heading-number').all_text_contents()==['1 ','1.1 ','2 ']
                assert page.locator('#preview-content [style*="display: flex"]').count()==0
                assert page.locator('#preview-content [data-output-role="abstract"]').count()==1
                assert page.locator('#preview-content li').count()==2
                assert (project/'report.md').read_bytes()==original
                assert json.loads((project/'meta.json').read_text(encoding='utf8'))['render_profile']=='engineering'
                html=page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
                restored=page.evaluate("async html=>{const t=document.createElement('template');t.innerHTML=html;return ReportExportArchive.readArchive(JSON.parse(t.content.querySelector('#report-source').textContent),t.content)}",html)
                assert restored['markdown'].encode('utf8')==original
                assert restored['renderProfile']=='engineering'
                # Derived chapter text is excluded from the existing visual serializer.
                heading=page.locator('#preview-content h2').first
                heading.click();heading.evaluate("e=>{e.lastChild.textContent='背景修改';e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText'}));e.blur()}")
                page.wait_for_function("document.querySelector('#markdown').value.includes('## 背景修改')")
                assert '## 1 背景修改' not in page.locator('#markdown').input_value()
                memory=io.BytesIO()
                with zipfile.ZipFile(memory,'w') as archive:
                    archive.writestr('report.md',original)
                    archive.writestr('meta.json',json.dumps({'render_profile':'engineering'}))
                page.locator('#menu-open > summary').click();page.locator('#btn-readpack').click()
                page.locator('#file-reader-zip').set_input_files({'name':'report.zip','mimeType':'application/zip','buffer':memory.getvalue()})
                page.wait_for_function("document.querySelector('#reader-article h2')||document.querySelector('#reader-status')?.dataset.bad==='1'")
                assert page.locator('#reader-article h2').first.inner_text()=='1 背景',page.locator('#reader-status').inner_text()
                assert page.locator('#reader-article [style*="display: flex"]').count()==0
                page.locator('#reader-close').click()
                client.close()
        finally:server.shutdown();server.server_close();worker.join(timeout=3)
        # CLI consumes the saved profile; an explicit override is temporary and recovery preserves it.
        out=folder/'report.html';export_html(project,out,browser=browser)
        recover_html(out,folder/'recovered',browser=browser)
        assert (folder/'recovered/report.md').read_bytes()==original
        assert json.loads((folder/'recovered/meta.json').read_text())['render_profile']=='engineering'
        override=folder/'free.html';export_html(project,override,browser=browser,render_profile='free')
        assert json.loads((project/'meta.json').read_text(encoding='utf8'))['render_profile']=='engineering'
        assert (project/'report.md').read_bytes()==original
    print('PF13.9 profiles, heading/TOC, literal HTML, abstract, visual source and CLI roundtrip PASS')

if __name__=='__main__':main()
