"""MATH-01: synthetic public equations, native boldsymbol and unchanged math source.

Only formula rendering/export/recovery is exercised. The cases exercise rendering, export and exact source recovery.
"""
from pathlib import Path
import argparse,hashlib,json,os,sys,tempfile,threading,time,shutil
from playwright.sync_api import sync_playwright

SOURCE_ROOT=Path(__file__).resolve().parents[1]
APP=Path(os.environ.get('HRS_MATH_APP',SOURCE_ROOT/'app')).resolve()
sys.path.insert(0,str(APP))
from studio import StudioServer
from portable_host import PortableHandler,WindowSessions
from html_cli import export_html,recover_html
from browser_support import artifact_directory

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--probe',action='store_true');args=parser.parse_args()
 fixture=json.loads((SOURCE_ROOT/'tests/fixtures/pf1310_article_math.json').read_text(encoding='utf8'))
 out=artifact_directory(__file__,'HRS_MATH_EVIDENCE',prefix='hrs-math-evidence-')
 browser=os.environ.get('CHROMIUM_PATH',r'C:/Program Files/Google/Chrome/Application/chrome.exe')
 started=time.perf_counter()
 with tempfile.TemporaryDirectory(prefix='hrs-math-') as d:
  root=Path(d);project=root/'article-math';project.mkdir();(project/'assets').mkdir()
  formulas=[{'tex':r'\boldsymbol{\phi}+\boldsymbol{\mathcal{M}}','display':True}] if args.probe else fixture['formulas']
  md='# 论文公式专项\r\n\r\n'+''.join(('$$\r\n'+f['tex']+'\r\n$$' if f['display'] else '$'+f['tex']+'$')+'\r\n\r\n' for f in formulas)
  # Probe starts with a known working equation, so missing boldsymbol cannot
  # be mistaken for a general app startup failure.
  (project/'report.md').write_bytes(('# 数学基线\n\n$E=mc^2$\n' if args.probe else md).encode())
  original=(project/'report.md').read_bytes()
  class Quiet(PortableHandler):
   def log_message(self,*a):pass
  server=StudioServer(('127.0.0.1',0),project,root/'workspace');server.RequestHandlerClass=Quiet
  server.portable_lifecycle=WindowSessions('math-only',enabled=False)
  worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
  try:
   with sync_playwright() as p:
    client=p.chromium.launch(executable_path=browser,headless=True)
    page=client.new_page(viewport={'width':1366,'height':950});requests=[]
    page.on('request',lambda req:requests.append(req.url))
    page.goto(f'http://127.0.0.1:{server.server_port}/web/index.html?programmatic=1')
    page.evaluate('async()=>{await ReportStudioProgrammatic.ready();await ReportStudioProgrammatic.open("legacy")}')
    result=page.evaluate(r'''async()=>{
     const version=MathJax.version;
     try{
      const node=await Promise.race([MathJax.tex2svgPromise('\\boldsymbol{\\phi}+\\boldsymbol{\\mathcal{M}}',{display:true}),new Promise((_,reject)=>setTimeout(()=>reject(Error('boldsymbol timeout')),8000))]);
      const error=node.querySelector('merror,[data-mml-node="merror"],[data-mjx-error]');
      const mathml=MathJax.tex2mml('\\boldsymbol{\\phi}');
      return {version,error:error?.getAttribute('data-mjx-error')||error?.textContent||null,mathml,svg:node.innerHTML};
     }catch(e){return {version,error:String(e)}}
    }''')
    (out/('probe.json' if args.probe else 'boldsymbol.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'mathjax_version':result['version'],'boldsymbol_error':result['error']},ensure_ascii=False),flush=True)
    assert not result['error'],result['error']
    assert 'bold' in result['mathml'],result['mathml']
    if not args.probe:
     errors=page.locator('#preview-content merror,#preview-content [data-mml-node="merror"],#preview-content [data-mjx-error],#preview-content .math-error').all_text_contents()
     assert not errors,errors
     # Some MathJax expressions contain nested SVGs (e.g. over/under accents).
     # Each source formula must own one direct SVG, not one descendant in total.
     assert page.locator('#preview-content .markdown-math > svg').count()==len(formulas),(page.locator('#preview-content .markdown-math > svg').count(),len(formulas))
     # The real source is still the fixture TeX, not a glyph/font substitution.
     actual=page.locator('#preview-content .markdown-math').evaluate_all('nodes=>nodes.map(n=>n.dataset.tex.trim())')
     assert actual==[f['tex'].strip() for f in formulas]
     page.screenshot(path=str(out/'article-math-preview.png'),full_page=True)
     first_bold=next(i for i,f in enumerate(formulas) if r'\boldsymbol' in f['tex'])
     page.locator('#preview-content .markdown-math').nth(first_bold).scroll_into_view_if_needed()
     page.screenshot(path=str(out/'article-boldsymbol.png'))
    client.close()
  finally:server.shutdown();server.server_close();worker.join(timeout=3)
  if not args.probe:
   html=root/'article-formulas.html';export_html(project,html,browser=browser)
   with sync_playwright() as p:
    client=p.chromium.launch(executable_path=browser,headless=True);page=client.new_page()
    page.goto(html.as_uri());assert page.locator('.markdown-math > svg').count()==len(formulas)
    assert page.locator('merror,[data-mml-node="merror"],[data-mjx-error]').count()==0
    client.close()
   restored=root/'restored';recover_html(html,restored,browser=browser)
   assert (restored/'report.md').read_bytes()==original
   assert (project/'report.md').read_bytes()==original
   shutil.copy2(html,out/'article-formulas.html')
   (out/'article-formulas.md').write_bytes(original)
   report={'status':'PASS','scope':'Formulas only','article_sha256':fixture['source_sha256'],'article_math_nodes':fixture['math_nodes'],
           'unique_formula_cases':len(formulas),'boldsymbol_cases':sum('\\boldsymbol' in f['tex'] for f in formulas),
           'source_sha256':hashlib.sha256(original).hexdigest(),'source_byte_identical_after_roundtrip':True,
           'external_requests':[u for u in requests if not u.startswith(('http://127.0.0.1:','data:'))],
           'other_feature_tests':'NOT_RUN','seconds':round(time.perf_counter()-started,3)}
   report['full_regression_complete']=False
   assert not report['external_requests'],report['external_requests']
   (out/'MATH_RESULT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
