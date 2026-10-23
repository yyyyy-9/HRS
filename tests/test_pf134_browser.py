"""TEST-SYSTEM-01: retained regression assertions, now using the actual local API."""
from pathlib import Path
import json, os, re, tempfile, unittest
from browser_support import ROOT as SOURCE_ROOT, LiveDocument, browser_session, css_color
ROOT=SOURCE_ROOT/'app'

MD=r'''# 表格主题测试

| A | B |
| --- | ---: |
| 参数 | 248.33 nm |

: 管道表标题 {#tbl-pipe}

```report-table
{"schema":"report-table-v1","id":"tbl-enhanced","caption":"增强表题","rows":[[{"text":"名称","rowspan":1,"colspan":1},{"text":"说明","rowspan":1,"colspan":1}],[{"text":"R1","rowspan":1,"colspan":1},{"text":"一","rowspan":1,"colspan":1}],[{"text":"R2","rowspan":1,"colspan":1},{"text":"二","rowspan":1,"colspan":1}]]}
```

```report-table
{"schema":"report-table-v1","id":"tbl-untitled","caption":"","rows":[[{"text":"列1","rowspan":1,"colspan":1}],[{"text":"数值","rowspan":1,"colspan":1}]]}
```

```report-figure
{"schema":"report-figure-v1","id":"fig-untitled","caption":"","kind":"mermaid","source":"flowchart LR\n A[开始] --> B[结束]"}
```

```report-figure
{"schema":"report-figure-v1","id":"fig-title","caption":"有图题","kind":"mermaid","source":"flowchart LR\n A[开始] --> B[结束]"}
```

| C | D |
|---|---|
| 1 | 2 |

```text
Example source code
```
'''

class TablePresentation(unittest.TestCase):
    def test_original_preview_export_and_reader_regression(self):
      with browser_session() as browser, tempfile.TemporaryDirectory(prefix='hrs-retained-') as directory:
       with LiveDocument(browser,Path(directory),MD,profile='engineering',init_script='window.__originalHasOwn=Object.hasOwn') as document:
        page=document.page; errors=document.errors
        assert page.evaluate('Object.hasOwn===window.__originalHasOwn'), 'a native implementation must not be replaced'
        page.locator('.report-table-wrap').first.wait_for(timeout=14000)
        page.wait_for_timeout(250)
        assert page.locator('.report-table-wrap').count()==4,'2 enhanced + 2 native'
        assert page.locator('.report-figure-wrap').count()==2
        assert page.locator('.report-table-wrap').nth(0).locator('caption').inner_text()=='表 1  管道表标题'
        assert page.locator('.report-table-wrap').nth(1).locator('caption').inner_text().startswith('表 2') and '增强表题' in page.locator('.report-table-wrap').nth(1).locator('caption').inner_text()
        assert page.locator('.report-table-wrap').nth(2).locator('caption').inner_text().strip()=='表 3'
        assert page.locator('.report-table-wrap').nth(3).locator('caption').inner_text().strip()=='表 4'
        assert page.locator('.report-figure-wrap').nth(0).locator('figcaption').inner_text().strip()=='图 1'
        assert '有图题' in page.locator('.report-figure-wrap').nth(1).locator('figcaption').inner_text()
        assert '未填写题注' not in page.locator('#preview-content').inner_text()
        assert page.locator('.report-table-wrap [data-table-copy]').count()==4
        def css_report(target):
         return target.evaluate('''node=>{
          const wrap=node.closest('.report-table-wrap'),table=wrap.querySelector('table'),head=wrap.querySelector('.hrs-table-tools'),caption=table.querySelector('caption'),first=table.querySelector('th'),data=table.querySelector('td'),alternate=table.querySelectorAll('tr')[2]?.querySelector('td');
          const c=n=>n?getComputedStyle(n):null;
          const rect=n=>{const r=n.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right}};
          return {toolbarBg:c(head).backgroundColor,titleBg:c(caption)?.backgroundColor||null,headerBg:c(first).backgroundColor,bodyBg:c(data).backgroundColor,alternateBg:c(alternate)?.backgroundColor,grid:c(first).borderTopColor,borderStyle:c(first).borderTopStyle,borderWidth:c(first).borderTopWidth,outer:c(wrap).borderColor,titleInToolbar:!!head.querySelector('.hrs-table-heading-caption'),cellGap:rect(first).top-rect(head).bottom,gridRight:c(first).borderRightWidth,gridLeft:c(first).borderLeftWidth};
         }''')
        for i in (0,1):
         panel=css_report(page.locator('.report-table-wrap').nth(i).locator('table'))
         assert panel['toolbarBg']==css_color(page,'table-toolbar'),panel
         assert panel['titleBg']==css_color(page,'table-heading'),panel
         assert panel['headerBg']==panel['titleBg'],panel
         assert panel['borderStyle']=='solid' and panel['borderWidth']=='1px',panel
         assert panel['gridLeft']=='1px' and panel['gridRight']=='1px',panel
         assert panel['titleInToolbar'],panel
         assert abs(panel['cellGap'])<=1.1,panel
        panel=css_report(page.locator('.report-table-wrap').nth(1).locator('table'))
        assert panel['alternateBg'] is not None and panel['bodyBg']!=panel['alternateBg'],panel
        assert page.evaluate('document.querySelector("#markdown").value')==MD
        # Prove live theme override changes both kinds at once, no hardcoded copy.
        page.evaluate('document.documentElement.style.setProperty("--hrs-table-toolbar","#B2C5D9")')
        assert page.locator('.report-table-wrap .hrs-table-tools').first.evaluate('(n)=>getComputedStyle(n).backgroundColor')=='rgb(178, 197, 217)'
        page.evaluate('document.documentElement.style.removeProperty("--hrs-table-toolbar")')
        artifact=Path(os.environ.get('TEST_ARTIFACT_DIR',str(document.folder/'screens')))
        artifact.mkdir(exist_ok=True,parents=True)
        page.locator('.report-table-wrap').nth(1).screenshot(path=str(artifact/'pf134_enhanced.png'))
        page.locator('.report-table-wrap').nth(0).screenshot(path=str(artifact/'pf134_native.png'))
        html_out=document.export()
        assert '--hrs-table-toolbar:' in html_out
        assert 'surface_components.css' not in html_out  # rule content is embedded
        archive=json.loads(re.search(r'<script type="application/json" id="report-source">(.*?)</script>',html_out,re.S)[1])
        assert archive['markdown']==MD
        offline=browser.new_page(viewport={'width':1280,'height':900})
        offerrors=[];offline.on('pageerror',lambda err:offerrors.append(str(err)))
        offline.set_content(html_out,wait_until='load')
        assert offline.locator('.report-table-wrap').count()==4
        assert offline.locator('.report-table-wrap').nth(0).locator('caption').inner_text()=='表 1  管道表标题'
        assert offline.locator('.report-table-wrap').nth(0).locator('caption').evaluate('(n)=>getComputedStyle(n).backgroundColor')==css_color(page,'table-heading')
        assert offline.locator('.report-figure-wrap').nth(0).locator('figcaption').inner_text().strip()=='图 1'
        assert offline.locator('.report-table-wrap').nth(2).locator('caption').inner_text().strip()=='表 3'
        assert '未填写题注' not in offline.locator('body').inner_text()
        assert offline.locator('.report-table-wrap .hrs-table-tools').count()==4
        offline.emulate_media(media='print')
        assert offline.locator('.hrs-table-tools').first.evaluate('(n)=>getComputedStyle(n).display')=='none'
        assert offline.locator('.report-table-wrap').nth(0).locator('th').first.evaluate('(n)=>getComputedStyle(n).borderTopStyle')=='solid'
        assert offline.locator('.report-table-wrap').nth(0).locator('caption').evaluate('(n)=>getComputedStyle(n).backgroundColor')==css_color(page,'table-heading')
        assert not errors,errors
        assert not offerrors,offerrors
        # Help card: prove high contrast through actual rendered styles (not CSS text checks).
        help=browser.new_page(viewport={'width':1250,'height':950})
        help.set_content((ROOT/'web/help.html').read_text('utf8'),wait_until='load')
        code=help.locator('.docs-paper .hrs-code-panel pre').first
        assert code.count()==1,'help must contain generated code cards'
        contrast=code.evaluate('''node=>{
          const parse=text=>text.match(/[\\d.]+/g).slice(0,3).map(Number).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
          const lum=v=>v[0]*.2126+v[1]*.7152+v[2]*.0722;
          const style=getComputedStyle(node),txt=lum(parse(style.color)),bg=lum(parse(style.backgroundColor));
          return {fg:style.color,bg:style.backgroundColor,ratio:(Math.max(txt,bg)+.05)/(Math.min(txt,bg)+.05)};
        }''')
        assert contrast['ratio']>=7,contrast
        help.locator('.docs-paper .hrs-code-panel').first.screenshot(path=str(artifact/'pf134_help_code.png'))
        assert not offerrors,offerrors
        print('PF13.4/PF13.6 Chromium: caption grouping, full grid, empty title retains number, theme, export/print, help contrast=',round(contrast['ratio'],2),'OK')


if __name__=='__main__': unittest.main(verbosity=2)
