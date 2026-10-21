"""Focused local-image import, output-gate and archive metadata checks."""
from pathlib import Path
import os,sys,tempfile,base64,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from html_cli import browser_session,export_html,recover_html,HTMLCommandError
from browser_support import source,value,select

def main():
 out=Path(os.environ.get('HRS_RC2_EVIDENCE',tempfile.mkdtemp(prefix='hrs-rc2-policy-')));out.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='hrs-rc2-import-') as d:
  folder=Path(d);project=folder/'project';(project/'assets').mkdir(parents=True)
  png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAABgAAAAQCAIAAACDRijCAAAAI0lEQVR4nGPUjephoAZgooopDKMGEQNGA5swGA0jwmDwhREAMgYBM6jouUsAAAAASUVORK5CYII=')
  (project/'report.md').write_bytes(b'# Report\n\n## Chapter\n')
  cases=[]
  with browser_session(project) as page:
   page.context.grant_permissions(['clipboard-read','clipboard-write']);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.evaluate("async()=>{await ReportStudioProgrammatic.ready();await ReportStudioProgrammatic.open('legacy')}")
   assert page.evaluate('!!window.HRSReadingPack');assert not errors,errors
   # Token-aware removal keeps a literal code example intact.
   result=page.evaluate("()=>{const s='# T\\n\\n`==code==` and ==prose==';return ReportNotes.clearHighlight(s,0,s.length,marked)}")
   assert result['text']=='prose',result;cases.append('clear-highlight-skips-code')
   # A browser File carries no trustworthy source directory: ask for the actual image.
   md='# 导入图片\n\n![本地图](pictures/plot.png)\n'
   page.locator('#file-import').set_input_files({'name':'local.md','mimeType':'text/markdown','buffer':md.encode('utf8')})
   page.wait_for_selector('#modal-body input[type=file]');assert 'pictures/plot.png' in page.locator('#modal-note').inner_text()
   page.locator('#modal-body input[type=file]').set_input_files({'name':'plot.png','mimeType':'image/png','buffer':png})
   page.locator('#modal-ok').click();page.wait_for_function("document.querySelector('#preview-content img')?.naturalWidth>0")
   imported=value(page);assert 'pictures/plot.png' not in imported and 'assets/' in imported
   cases.append('markdown-file-explicit-local-image-import')
   # Plain pasted Markdown in this new draft can resolve already staged assets.
   path=imported.split('](',1)[1].split(')',1)[0]
   page.evaluate('text=>navigator.clipboard.writeText(text)','\n![第二处]('+path+')\n');end=len(imported);select(page,end,end);page.keyboard.press('Control+V')
   page.wait_for_function("document.querySelectorAll('#preview-content img').length===2&&[...document.querySelectorAll('#preview-content img')].every(i=>i.naturalWidth>0)")
   cases.append('plain-markdown-paste-uses-known-staged-image')
   # Footnotes in the offline HTML follow and return using ordinary single clicks.
   text=value(page)+'\n正文[^fn1]\n\n[^fn1]: 脚注说明\n';source(page,text)
   html=page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
   file=out/'footnote-local.html';file.write_bytes(html.encode('utf8'))
   offline=page.context.browser.new_page();offline.on('pageerror',lambda e:errors.append(str(e)));offline.goto(file.as_uri());offline.locator('.hrs-note-link').first.click();offline.locator('.hrs-note-back').click();assert not errors,errors
   cases.append('offline-footnote-links-and-initialization')
  # Explicit CLI acceptance is checked before starting a browser.
  numbered='# 报告\n\n## 1 手工章号\n';(project/'report.md').write_bytes(numbered.encode('utf8'))
  try:export_html(project,folder/'rejected.html',render_profile='engineering')
  except ValueError as e:assert 'HEADING_SOURCE_PREFIX' in str(e)
  else:raise AssertionError('missing acceptance was not rejected')
  assert not (folder/'rejected.html').exists()
  receipt=export_html(project,folder/'accepted.html',render_profile='engineering',accept_numbered_headings=True)
  assert any(x['code']=='HEADING_SOURCE_PREFIX' for x in receipt['diagnostics']);assert (project/'report.md').read_bytes()==numbered.encode('utf8')
  cases.append('cli-prefix-notice-requires-explicit-snapshot-acceptance')
  (project/'meta.json').write_text(json.dumps({'render_profile':'free','render_options':{'show_object_numbers':False}}),encoding='utf8')
  export_html(project,folder/'free.html');recover_html(folder/'free.html',folder/'recovered')
  restored=json.loads((folder/'recovered/meta.json').read_text(encoding='utf8'));assert restored['render_options']=={'show_object_numbers':False,'show_heading_numbers':False,'preserve_blank_lines':False}
  cases.append('cli-export-recovery-retains-display-options')
 (out/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf8');print('RC2 import/output focused cases PASS:',len(cases))

if __name__=='__main__':main()
