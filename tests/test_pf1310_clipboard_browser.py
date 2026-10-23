"""Only the clipboard/table/options paths added in RC2, through real editor events."""
from pathlib import Path
import sys,os,tempfile,json,base64
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from html_cli import browser_session
from report_contract import analyze
from browser_support import source,select,value,wait_rich_clipboard,artifact_directory

def main():
 out=artifact_directory(__file__,'HRS_RC2_EVIDENCE',prefix='hrs-rc2-extra-')
 with tempfile.TemporaryDirectory(prefix='hrs-rc2-clipboard-') as d:
  project=Path(d)/'project';(project/'assets').mkdir(parents=True)
  (project/'assets/1234567890abcdef.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAABgAAAAQCAIAAACDRijCAAAAI0lEQVR4nGPUjephoAZgooopDKMGEQNGA5swGA0jwmDwhREAMgYBM6jouUsAAAAASUVORK5CYII='))
  figure={'schema':'report-figure-v1','id':'fig-one','caption':'单图','kind':'image','src':'assets/1234567890abcdef.png','alt':''}
  caption='长表题用于检查中间区域自动换行而左右操作保持位置。'*6
  table={'schema':'report-table-v1','id':'tbl-one','caption':caption,'rows':[[{'text':'甲','rowspan':1,'colspan':1},{'text':'乙','rowspan':1,'colspan':1}]]}
  raw='```report-figure\n'+json.dumps(figure,ensure_ascii=False)+'\n```\n\n```report-table\n'+json.dumps(table,ensure_ascii=False)+'\n```\n\n'
  raw+='::: {#fig-group layout-ncol=2 subfig-labels=off}\n![一](assets/1234567890abcdef.png)\n![二](assets/1234567890abcdef.png)\n组图说明\n:::\n\n'
  raw+='参见 @fig:fig-one、@tbl:tbl-one、@fig:fig-group。`@fig:fig-one` 是代码示例。\n'
  text='# 原稿\n\n'+raw;(project/'report.md').write_bytes(text.encode('utf8'));cases=[]
  with browser_session(project) as page:
   page.context.grant_permissions(['clipboard-read','clipboard-write'])
   page.set_default_timeout(15000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.evaluate("async()=>{await ReportStudioProgrammatic.ready();await ReportStudioProgrammatic.open('legacy')}")
   # Engineering chrome owns the long caption/control layout since THEME-08;
   # the later free-note paste and recovery checks keep their original mode.
   page.locator('#render-profile').select_option('engineering')
   page.wait_for_function("document.body.dataset.renderProfile==='engineering'")
   page.wait_for_selector('.hrs-table-heading-caption');assert page.locator('.hrs-table-heading-caption').inner_text().endswith(caption)
   boxes=page.locator('.hrs-table-tools').evaluate('e=>[...e.children].map(c=>{const r=c.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})')
   assert boxes[0]['x']<boxes[1]['x']<boxes[2]['x'];assert boxes[1]['height']>25;cases.append('long-table-caption-wrap-controls-fixed')
   # The OS clipboard can still contain an identical fixture from a previous
   # browser run. A sentinel prevents that old payload satisfying this wait
   # before the current asynchronous resource copy has completed.
   page.evaluate("async()=>await navigator.clipboard.writeText('HRS RC2 copy pending')")
   select(page,len('# 原稿\n\n'),len(text));page.keyboard.press('Control+C')
   wait_rich_clipboard(page,raw)
   page.evaluate("async()=>await ReportStudioProgrammatic.open('new')");page.locator('#render-profile').select_option('free')
   page.wait_for_function("document.body.dataset.renderProfile==='free'")
   source(page,'# 目标\n\n');select(page,len(value(page)),len(value(page)));page.keyboard.press('Control+V')
   try:page.wait_for_function("document.querySelectorAll('#preview-content .report-figure-wrap').length===2&&document.querySelectorAll('#preview-content .report-table-wrap').length===1")
   except Exception:
    (out/'failure.json').write_text(json.dumps({'source':value(page),'toast':page.locator('#toast').inner_text(),'preview':page.locator('#preview-content').inner_text()},ensure_ascii=False,indent=2),encoding='utf8');page.screenshot(path=str(out/'failure.png'));raise
   first=analyze(value(page));assert first['ok'],first['diagnostics'];assert len(first['objects']['ids'])==3
   assert not {'fig-one','tbl-one','fig-group'}&set(first['objects']['ids']),value(page)
   assert '`@fig:fig-one`' in value(page),value(page)
   assert {r['target'] for r in first['references']}==set(first['objects']['ids']);cases.append('fragment-copy-group-table-internal-reference-map-code-literal')
   assert page.locator('.image-group-label').count()==0
   page.locator('#show-object-numbers').uncheck();page.wait_for_function("[...document.querySelectorAll('.object-xref')].map(x=>x.textContent).join('|').includes('组图说明')")
   assert page.locator('.object-xref').all_text_contents()==['单图',caption,'组图说明'];cases.append('hidden-captions-and-references-all-object-types')
   end=len(value(page));select(page,end,end);page.keyboard.press('Control+V')
   page.wait_for_function("document.querySelectorAll('#preview-content .report-figure-wrap').length===4")
   second=analyze(value(page));assert second['ok'];assert len(second['objects']['ids'])==6;cases.append('repeat-fragment-paste-six-unique-identities')
   card=page.locator('.source-fold-summary[data-language=report-image-group]').last;old=card.get_attribute('data-object-id')
   card.click();page.keyboard.press('Control+X');page.wait_for_function("document.querySelectorAll('#preview-content .image-group-grid').length===1")
   end=len(value(page));select(page,end,end);page.keyboard.press('Control+V')
   page.wait_for_function("document.querySelectorAll('#preview-content .image-group-grid').length===2")
   assert old in analyze(value(page))['objects']['ids'];cases.append('same-project-cut-preserves-group-identity')
   snapshot=value(page);page.wait_for_function("document.querySelector('#save-indicator').textContent.includes('草稿已备份')")
   page.reload();page.wait_for_selector('.draft-picker');
   options=page.locator('.draft-picker option').evaluate_all('xs=>xs.map(x=>({id:x.value,text:x.textContent}))')
   chosen=next(x['id'] for x in options if x['text'].startswith('目标'))
   page.locator('.draft-picker').select_option(chosen);page.locator('#modal-ok').click();page.wait_for_function('md=>document.querySelector("#markdown").sourceEditor.value===md',arg=snapshot)
   page.wait_for_function("[...document.querySelectorAll('#preview-content img')].length===6&&[...document.querySelectorAll('#preview-content img')].every(i=>i.complete&&i.naturalWidth>0)")
   assert not page.locator('#show-object-numbers').is_checked();cases.append('draft-recovery-source-options-and-staged-images')
   html=page.evaluate("async()=>await ReportStudioProgrammatic.exportHTML({quality:'original',sourceMode:'recompilable'})")
   restored=page.evaluate("async html=>{const t=document.createElement('template');t.innerHTML=html;return ReportExportArchive.readArchive(JSON.parse(t.content.querySelector('#report-source').textContent),t.content)}",html)
   assert restored['markdown']==snapshot;assert restored['renderOptions']=={'show_object_numbers':False,'show_heading_numbers':False,'show_equation_numbers':False,'preserve_blank_lines':True};cases.append('archive-restores-source-and-hidden-number-option')
   (out/'all-objects.html').write_text(html,encoding='utf8');page.screenshot(path=str(out/'table-caption.png'))
   assert not errors,errors
  (out/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf8')
 print('RC2 clipboard, tables and options browser cases PASS:',len(cases))

if __name__=='__main__':main()
