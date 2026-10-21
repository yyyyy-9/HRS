"""RC2: real local service, current editor and affected browser interactions."""
from pathlib import Path
import os,sys,tempfile,threading,json,argparse,base64
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from studio import StudioServer
from portable_host import PortableHandler,WindowSessions
import studio

from browser_support import source, select, value, wait_rich_clipboard, artifact_directory

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--probe-menu',action='store_true');args=parser.parse_args()
 out=artifact_directory(__file__,'HRS_RC2_EVIDENCE',prefix='hrs-rc2-evidence-')
 with tempfile.TemporaryDirectory(prefix='hrs-rc2-') as d,tempfile.TemporaryDirectory(prefix='hrs-rc2-save-') as destination_name:
  folder=Path(d);project=folder/'source';(project/'assets').mkdir(parents=True);(project/'report.md').write_text('# 报告\n\n## 背景\n\n普通文字。\n',encoding='utf8')
  # Replace only the native folder dialog with this test-owned directory.
  # The real selection token, save endpoint and editor save path still execute.
  destination=Path(destination_name);studio.pick_project_parent=lambda:destination
  (project/'assets/1234567890abcdef.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAABgAAAAQCAIAAACDRijCAAAAI0lEQVR4nGPUjephoAZgooopDKMGEQNGA5swGA0jwmDwhREAMgYBM6jouUsAAAAASUVORK5CYII='))
  cases=[]
  class Quiet(PortableHandler):
   def log_message(self,*args):pass
  server=StudioServer(('127.0.0.1',0),project,folder/'workspace');server.RequestHandlerClass=Quiet
  server.portable_lifecycle=WindowSessions('rc2-test',enabled=False)
  worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
  try:
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH',r'C:/Program Files/Google/Chrome/Application/chrome.exe'),headless=True)
    context=browser.new_context(viewport={'width':1920,'height':1080},permissions=['clipboard-read','clipboard-write'])
    page=context.new_page();page.set_default_timeout(15000)
    page.on('requestfailed',lambda r:print('REQUEST_FAILED',r.url,r.failure,flush=True))
    page.on('pageerror',lambda e:print('PAGE_ERROR',str(e),flush=True))
    page.goto(f'http://127.0.0.1:{server.server_port}/web/index.html?programmatic=1')
    page.evaluate("async()=>{await ReportStudioProgrammatic.ready();await ReportStudioProgrammatic.open('legacy')}")
    page.locator('#highlight-picker > summary').click()
    hit=page.locator('[data-highlight-color]').evaluate_all('''buttons=>buttons.map(b=>{const r=b.getBoundingClientRect();return {color:b.dataset.highlightColor,hit:document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('[data-highlight-color]')===b}})''')
    (out/'menu-hit.json').write_text(json.dumps(hit,ensure_ascii=False,indent=2),encoding='utf8')
    page.screenshot(path=str(out/'menu.png'))
    assert all(x['hit'] for x in hit),hit
    if args.probe_menu:return
    assert len(hit)==9,hit # eight colors and clear
    page.keyboard.press('Escape')
    for width in (1366,900):
     page.set_viewport_size({'width':width,'height':900});page.locator('#highlight-picker > summary').click()
     assert page.locator('[data-highlight-color]').evaluate_all("xs=>xs.every(b=>{const r=b.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('[data-highlight-color]')===b})")
     page.keyboard.press('Escape')
    page.set_viewport_size({'width':1920,'height':1080});cases.append('highlight-menu-1920-1366-900')
    original='# 报告\n\n## 背景\n\n普通文字。\n';source(page,original);a=original.index('普通');select(page,a,a+4)
    page.locator('#highlight-picker > summary').click();page.locator('[data-highlight-color=purple]').click()
    page.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('#e7d7fa')")
    highlighted=value(page);start=highlighted.index('普通');select(page,start,start+4)
    page.locator('#highlight-picker > summary').click();page.locator('[data-highlight-color=clear]').click()
    page.wait_for_function("!document.querySelector('#markdown').sourceEditor.value.includes('<mark')")
    assert value(page)==original;cases.append('highlight-selection-color-clear')
    select(page,a+4,a+4);page.locator('#ref-picker > summary').click();page.locator('[data-insert=footnote]').click()
    page.locator('#modal-body textarea').fill('本次脚注说明');page.locator('#modal-ok').click()
    page.wait_for_selector('.hrs-note-link');assert '[^fn1]: 本次脚注说明' in value(page)
    page.locator('.hrs-note-link').first.click();page.locator('.hrs-note-back').click();cases.append('footnote-insert-follow-return')
    bad='# 主标题\n\n## 正文\n\n#### 跳级\n\n# 第二主标题\n';source(page,bad)
    page.locator('#render-profile').select_option('engineering');page.locator('#btn-validate').click()
    page.wait_for_selector('[data-code=MULTIPLE_H1][data-severity=error]');assert page.locator('[data-code=HEADING_LEVEL_GAP][data-severity=error]').count()==1
    error=page.evaluate("async()=>{try{await ReportStudioProgrammatic.exportHTML({renderProfile:'engineering'});return null}catch(e){return e.message}}")
    assert '阻止' in error,error;cases.append('engineering-heading-diagnostics-and-export-block')
    page.locator('#render-profile').select_option('free')
    obj={'schema':'report-figure-v1','id':'fig-one','caption':'单图测试','kind':'image','src':'assets/1234567890abcdef.png','alt':''}
    raw='```report-figure\n'+json.dumps(obj,ensure_ascii=False)+'\n```\n'
    source(page,'# 对象稿\n\n'+raw)
    page.wait_for_selector('.source-fold-summary');card=page.locator('.source-fold-summary').first
    page.evaluate("async()=>await navigator.clipboard.writeText('HRS RC2 card copy pending')")
    card.click(button='right');copied=page.evaluate("()=>{const e=document.querySelector('#markdown').sourceEditor;return e.value.slice(e.selectionStart,e.selectionEnd)}")
    page.locator('.source-object-menu [data-action=copy]').click()
    wait_rich_clipboard(page,copied);page.wait_for_selector('.source-object-menu',state='hidden')
    end=len(value(page));select(page,end,end);page.keyboard.press('Control+V')
    try:page.wait_for_function("document.querySelectorAll('#preview-content .report-figure-wrap').length===2")
    except Exception:
     page.screenshot(path=str(out/'copy-failure.png'));(out/'copy-failure.json').write_text(json.dumps({'source':value(page),'toast':page.locator('#toast').inner_text(),'clipboard':page.evaluate('async()=>(await navigator.clipboard.read()).map(x=>x.types)')},ensure_ascii=False,indent=2),encoding='utf8');raise
    data=page.locator('#preview-content .report-figure-wrap').evaluate_all('xs=>xs.map(x=>x.dataset.figureId)')
    assert len(set(data))==2,data;assert page.locator('.source-fold-summary').count()==2
    page.keyboard.press('Control+Z');page.wait_for_function("document.querySelectorAll('#preview-content .report-figure-wrap').length===1")
    page.keyboard.press('Control+Y');page.wait_for_function("document.querySelectorAll('#preview-content .report-figure-wrap').length===2")
    cases.append('same-project-copy-new-id-fold-undo-redo')
    # The clipboard contains source bytes and its image, independent of this project.
    page.evaluate("async()=>await ReportStudioProgrammatic.open('new')");page.locator('#render-profile').select_option('free')
    source(page,'# 新工程\n\n');select(page,len(value(page)),len(value(page)));page.keyboard.press('Control+V')
    page.wait_for_selector('#preview-content .report-figure-wrap img');page.wait_for_function("[...document.querySelectorAll('#preview-content .report-figure-wrap img')].every(i=>i.complete&&i.naturalWidth>0)")
    assert 'fig-one' not in value(page);cases.append('cross-project-unsaved-preview-with-assets')
    page.locator('#show-object-numbers').uncheck();page.wait_for_function("document.querySelector('#preview-content figcaption')?.textContent==='单图测试'")
    # Delete before first save; save must retain staged bytes for undo.
    page.locator('.source-fold-summary').click();page.keyboard.press('Delete');page.wait_for_function("!document.querySelector('#preview-content .report-figure-wrap')")
    page.locator('#btn-save').click();page.locator('#modal-ok').click();page.get_by_role('button',name='确认位置',exact=True).click()
    page.wait_for_function("document.querySelector('#save-indicator').textContent.includes('已保存')")
    page.keyboard.press('Control+Z');page.wait_for_selector('#preview-content .report-figure-wrap img')
    page.wait_for_function("[...document.querySelectorAll('#preview-content .report-figure-wrap img')].every(i=>i.complete&&i.naturalWidth>0)")
    saved=list(destination.glob('*/meta.json'));assert len(saved)==1
    meta=json.loads(saved[0].read_text(encoding='utf8'));assert meta['render_options']=={'show_object_numbers':False,'show_heading_numbers':False,'preserve_blank_lines':True}
    assert list(saved[0].parent.joinpath('assets').glob('*.png'));cases.append('first-save-retains-undo-assets-and-options')
    html=page.evaluate("async()=>await ReportStudioProgrammatic.exportHTML({quality:'original',sourceMode:'recompilable'})")
    (out/'free-hidden.html').write_text(html,encoding='utf8')
    offline=context.new_page();offline.goto((out/'free-hidden.html').as_uri());offline.wait_for_selector('figcaption')
    assert offline.locator('figcaption').inner_text()=='单图测试';assert offline.locator('#report-source').evaluate('e=>JSON.parse(e.textContent).renderOptions.show_object_numbers') is False
    cases.append('hidden-number-export-archive-and-reader')
    # Exercise the real confirmation dialog; unchanged snapshots reuse it once.
    page.evaluate("history.replaceState(null,'','/web/index.html')")
    numbered='# 编号提醒回归\n\n## 1 背景\n\n正文。\n';source(page,numbered)
    page.locator('#render-profile').select_option('engineering')
    for snapshot in (numbered,numbered+'\n补充。\n'):
     source(page,snapshot)
     page.evaluate("()=>{window.headingExportDone=null;ReportStudioProgrammatic.exportHTML({renderProfile:'engineering',quality:'original',sourceMode:'recompilable'}).then(()=>window.headingExportDone=true,e=>window.headingExportDone=e.message)}")
     page.wait_for_function("window.headingExportDone!==null||[...document.querySelectorAll('button')].some(b=>b.textContent==='已核对，继续导出')")
     assert page.evaluate('window.headingExportDone') is None,page.evaluate('window.headingExportDone')
     page.get_by_role('button',name='已核对，继续导出',exact=True).click()
     page.wait_for_function('window.headingExportDone!==null');assert page.evaluate('window.headingExportDone') is True
     assert page.evaluate("async()=>{await ReportStudioProgrammatic.exportHTML({renderProfile:'engineering',quality:'original',sourceMode:'recompilable'});return true}")
     assert not page.get_by_role('button',name='已核对，继续导出',exact=True).is_visible()
    cases.append('manual-heading-confirmation-once-per-source-snapshot')
    page.screenshot(path=str(out/'final.png'));(out/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf8')
    browser.close()
  finally:server.shutdown();server.server_close();worker.join(timeout=3)
 print('RC2 affected browser checks PASS')

if __name__=='__main__':main()
