"""TEST-SYSTEM-01: retained regression assertions, now using the actual local API."""
from pathlib import Path
import json, re, tempfile, unittest
from browser_support import LiveDocument, browser_session

PNG_NAME='0123456789abcdef.svg'

PNG_NAME2='fedcba9876543210.svg'

ASSET={
 PNG_NAME:b'<svg xmlns="http://www.w3.org/2000/svg" width="90" height="50"><rect width="90" height="50" fill="#314d96"/></svg>',
 PNG_NAME2:b'<svg xmlns="http://www.w3.org/2000/svg" width="90" height="50"><circle cx="40" cy="25" r="20" fill="#1a885b"/></svg>',
}

def fenced(language,obj):
 return '```'+language+'\n'+json.dumps(obj,ensure_ascii=False)+'\n```'

def table(id,caption):
 return fenced('report-table',dict(schema='report-table-v1',id=id,caption=caption,rows=[
  [{'text':'列','rowspan':1,'colspan':1},{'text':'数值','rowspan':1,'colspan':1}],
  [{'text':'样本','rowspan':1,'colspan':1},{'text':'42','rowspan':1,'colspan':1}]
 ]))

def picture(id,caption,kind='image'):
 obj=dict(schema='report-figure-v1',id=id,caption=caption,kind=kind)
 if kind=='image':obj.update(src='assets/'+PNG_NAME,alt='合成 SVG')
 else:obj.update(source='flowchart LR\nA[输入] --> B[输出]')
 return fenced('report-figure',obj)

MD='\n\n'.join([
 '# 混排回归',
 '| 原生列 | 值 |\n|---|---:|\n| A | 1 |\n: GFM 题注 {#tbl-native}',
 table('tbl-a',''),
 picture('fig-picture',''),
 table('tbl-b','有标题的增强表'),
 picture('fig-flow',''),
 '| 未题注 | 数值 |\n|---|---|\n| Z | 9 |',
 '::: {#fig-group layout-ncol=2}\n\n![甲](assets/'+PNG_NAME+')\n\n![乙](assets/'+PNG_NAME2+')\n\n:::',
 '<!-- hrs:eq id=eq-a -->\n$$\nE=mc^2\n$$',
 '引用 @tbl:tbl-a、@fig:fig-picture、@fig:fig-group、@eq:eq-a。'
])+'\n'

class MixedObjects(unittest.TestCase):
    def test_original_preview_export_and_reader_regression(self):
      with browser_session() as browser, tempfile.TemporaryDirectory(prefix='hrs-retained-') as directory:
       with LiveDocument(browser,Path(directory),MD,profile='engineering', assets=ASSET, init_script='Object.hasOwn=undefined') as document:
        page=document.page; errors=document.errors
        assert page.evaluate("typeof mermaid.render==='function' && Object.hasOwn({x:1},'x') && !Object.hasOwn(Object.create({x:1}),'x')"), 'full vendor initialization must complete with the missing-API fallback'
        assert page.evaluate("(()=>{try{Object.hasOwn(null,'x');return false}catch(error){return error instanceof TypeError}})()"), 'fallback must preserve the native null rejection'
        page.locator('.report-table-wrap').first.wait_for(timeout=18000)
        page.locator('#show-equation-numbers').check()
        page.wait_for_function("document.querySelector('#preview-content').dataset.hrsShowEquationNumbers==='1'")
        page.wait_for_function('document.querySelectorAll(".report-figure-wrap").length===3',timeout=16000)
        assert page.locator('.report-table-wrap').count()==4,'2 enhanced + 2 native GFM'
        assert page.locator('.report-figure-wrap').count()==3,'image/mermaid/group'
        assert page.locator('.report-table-wrap').nth(0).locator('caption').inner_text()=='表 1  GFM 题注'
        assert page.locator('.report-table-wrap').nth(1).locator('caption').inner_text().strip()=='表 2'
        assert page.locator('.report-table-wrap').nth(2).locator('caption').inner_text().split()==['表','3','有标题的增强表'],repr(page.locator('.report-table-wrap').nth(2).locator('caption').inner_text())
        assert page.locator('.report-table-wrap').nth(3).locator('caption').inner_text().strip()=='表 4'
        assert page.locator('[data-figure-id="fig-picture"] figcaption').inner_text().strip()=='图 1'
        assert page.locator('[data-figure-id="fig-flow"] figcaption').inner_text().strip()=='图 2'
        assert page.locator('[data-figure-id="fig-group"] figcaption').inner_text().strip()=='图 3'
        assert page.locator('[data-equation-id="eq-a"] .equation-number').inner_text()=='(1)'
        assert '未填写题注' not in page.locator('#preview-content').inner_text()
        assert page.evaluate('document.querySelector("#markdown").value')==MD
        exported=document.export()
        payload=json.loads(re.search(r'<script type="application/json" id="report-source">(.*?)</script>',exported,re.S)[1])
        assert payload['markdown']==MD
        assert len(payload['assetIndex'])==2
        offline=browser.new_page(viewport={'width':1280,'height':900})
        offerrors=[];offline.on('pageerror',lambda e:offerrors.append(str(e)))
        offline.add_init_script('Object.hasOwn = undefined')
        offline.evaluate('Object.hasOwn = undefined')
        offline.set_content(exported,wait_until='load')
        offline.wait_for_function('document.querySelector("[data-hrs-reader-root]").dataset.hrsReaderReady==="1"',timeout=14000)
        assert offline.evaluate('typeof Object.hasOwn')=='undefined','old-Edge API simulation not applied'
        assert offline.locator('[data-figure-id="fig-picture"] figcaption').inner_text().strip()=='图 1'
        assert offline.locator('[data-figure-id="fig-flow"] figcaption').inner_text().strip()=='图 2'
        assert offline.locator('[data-figure-id="fig-group"] figcaption').inner_text().strip()=='图 3'
        assert offline.locator('[data-table-id="tbl-a"] caption').inner_text().strip()=='表 2'
        assert offline.locator('[data-table-id="tbl-b"] caption').inner_text().split()==['表','3','有标题的增强表']
        assert offline.locator('.report-table-wrap[data-pipe-table] caption').count()==2
        assert offline.locator('[data-equation-id="eq-a"] .equation-number').inner_text()=='(1)'
        assert '未填写题注' not in offline.locator('body').inner_text()
        result=offline.evaluate('''()=>{
          const cat=ReportObjectCatalog.indexDOM(document.querySelector('[data-hrs-reader-root]'));
          return {number:cat.items.map(x=>x.number),kinds:cat.items.map(x=>x.kind),
           nav:document.querySelectorAll('.hrs-reader-object').length,
           tabs:document.querySelectorAll('.hrs-reader-object-tab').length,
           index:document.querySelector('[data-hrs-reader-root]').dataset.hrsReaderReady};
        }''')
        assert result['number']==[1,2,1,3,2,4,3,1],result
        assert result['nav']==16 and result['tabs']==2,result
        assert not errors,errors
        assert not offerrors,offerrors
        offline.emulate_media(media='print')
        assert offline.locator('[data-table-id="tbl-a"] caption').evaluate('(n)=>getComputedStyle(n).display')!='none'

       print('PF13.6 Chromium: mixed enhanced/GFM image/flow/group/equation; visible number without title; full export and old-Edge API emulator OK')

if __name__=='__main__': unittest.main(verbosity=2)
