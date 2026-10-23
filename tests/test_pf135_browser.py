"""PF13.5 offline Chromium: one semantic object catalog, no duplicate numbering source."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import os,shutil
WEB=Path(__file__).resolve().parents[1]/'app/web'
CHROMIUM=os.getenv('CHROMIUM_PATH') or shutil.which('chromium')
assert CHROMIUM
page_html='''<!doctype html><html><body>
<main data-hrs-reader-root="1">
  <div class="doc-block"><h2>目录计数检查</h2></div>
  <div class="report-table-wrap" data-table-id="tbl-one"><table><caption data-caption-text="增强表">表 1  增强表</caption><tr><td>值1</td></tr></table></div>
  <div class="report-table-wrap" data-pipe-table="1"><table><caption data-caption-text="原生表题">原生表题</caption><tr><td>GFM</td></tr></table></div>
  <figure class="report-figure-wrap" data-figure-id="fig-one"><figcaption>图 1</figcaption><svg></svg></figure>
  <div class="report-table-wrap" data-table-id="tbl-two"><table><caption data-caption-text="第二表">表 2  第二表</caption><tr><td>值2</td></tr></table></div>
  <div class="report-equation" data-equation-id="eq-e"><span class="equation-number">(1)</span></div>
</main></body></html>'''
with sync_playwright() as playwright:
 browser=playwright.chromium.launch(executable_path=CHROMIUM,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 page=browser.new_page(viewport={'width':1100,'height':850})
 errors=[]
 page.on('pageerror',lambda error:errors.append(str(error)))
 page.set_content(page_html)
 page.add_script_tag(content=(WEB/'report_reader.js').read_text('utf8'))
 page.wait_for_function('window.HRSReportReader && document.querySelector("[data-hrs-reader-root]").dataset.hrsReaderReady === "1"')
 result=page.evaluate('''() => {
  const catalog=ReportObjectCatalog.indexDOM(document.querySelector('[data-hrs-reader-root]'));
  const outline=HRSReportReader.objectOutline(document.querySelector('[data-hrs-reader-root]'));
  return {numbers:catalog.items.map(x=>x.number),types:catalog.items.map(x=>x.kind),titles:outline.map(x=>x.title),navCount:document.querySelectorAll('.hrs-reader-object').length};
 }''')
 assert result['numbers']==[1,2,1,3,1],result
 assert result['types']==['table','table','figure','table','equation'],result
 assert result['titles'][1].startswith('表 2') and '原生表题' in result['titles'][1],result
 assert result['navCount']==10,result  # chronological and grouped modes
 assert not errors,errors
 browser.close()
print('PF13.5 Chromium: shared offline semantic index, caption/nav and separate numbering OK')
