"""TEST-SYSTEM-01: retained regression assertions, now using the actual local API."""
from pathlib import Path
import json, os, re, tempfile, unittest
from browser_support import LiveDocument, browser_session, css_color

MD='''# PF13.2 合成验收

正文公式 \\(E=mc^2\\)，以及代码 `\\(literal\\)` 不应渲染。

| TCC 元素 | 含义 |
|---|---|
| \\(T_{11}\\) | 第一个分量 |
| \\(T_{22}\\) | 第二个分量 |
| a\\|b | 转义管道 |

: TCC 含义 {#tbl-tcc}

```report-table
{"schema":"report-table-v1","id":"tbl-enhanced","caption":"增强表题","rows":[[{"text":"TCC 元素","rowspan":1,"colspan":1},{"text":"含义","rowspan":1,"colspan":1}],[{"text":"\\\\(T_{12}\\\\)","rowspan":1,"colspan":1},{"text":"交叉项","rowspan":1,"colspan":1}]]}
```

| A | B |
|---|---|
| 1 | 2 |
'''

class TableMath(unittest.TestCase):
    def test_original_preview_export_and_reader_regression(self):
      with browser_session() as browser, tempfile.TemporaryDirectory(prefix='hrs-retained-') as directory:
       with LiveDocument(browser,Path(directory),MD,profile='engineering',registered=True) as document:
        page=document.page; errors=document.errors
        page.locator('.report-table-wrap').first.wait_for(timeout=14000)
        page.locator('.markdown-math svg').first.wait_for(timeout=14000)
        assert page.locator('.report-table-wrap').count()==3,page.locator('.report-table-wrap').count()
        assert page.locator('.markdown-math svg').count()>=4,page.locator('.markdown-math svg').count()
        assert page.locator('.report-table-wrap').first.locator('.markdown-math svg').count()==2
        assert page.locator('.report-table-wrap').nth(1).locator('.markdown-math svg').count()==1
        assert page.locator('.doc-block p .markdown-math svg').count()==1
        assert page.locator('.doc-block p code').filter(has_text=r'\(literal\)').count()==1
        assert page.locator('.report-table-wrap').first.locator('caption').text_content().startswith('表 1  TCC')
        assert page.locator('.report-table-wrap').first.locator('[data-table-copy]').count()==1
        assert page.evaluate('document.querySelector("#markdown").value')==MD
        page.locator('#btn-fold-all').click()
        folded=page.locator('.source-fold-summary[data-language="gfm-pipe"]')
        folded.first.wait_for(timeout=8000)
        assert '表 1' in folded.first.text_content()
        assert page.evaluate('document.querySelector("#markdown").value')==MD
        folded.first.locator('button').last.click()
        assert folded.count()==1
        page.evaluate('document.querySelector(".cm-scroller").scrollTop=0')
        page.wait_for_timeout(250)
        assert page.locator('.cm-hf8-table-head-line').count()>0
        assert page.locator('.cm-hf8-table-separator-line').count()>0
        assert page.evaluate('document.querySelector("#markdown").value')==MD
        assert page.locator('.report-table-wrap .hrs-table-rendered').first.evaluate('(n)=>getComputedStyle(n).marginTop')=='0px'
        folder=Path(os.environ.get('TEST_ARTIFACT_DIR',str(document.folder/'screens')));folder.mkdir(exist_ok=True,parents=True)
        page.screenshot(path=str(folder/'pf132_app.png'))
        exported=document.export(via_ui=True)
        outputs=list((document.project/'output').glob('*.html'))
        assert len(outputs)==1,[path.name for path in outputs]
        assert outputs[0].read_bytes()==exported.encode('utf8'),'UI output must preserve the actual HTML bytes, including embedded CSS newlines'
        assert (document.project/'report.md').read_bytes()==MD.encode('utf8')
        archive=json.loads(re.search(r'<script type="application/json" id="report-source">(.*?)</script>',exported,re.S)[1])
        assert archive['markdown']==MD,'HTML archive must preserve exact report.md text'
        assert 'hrs-table-tools' in exported and 'report-table-caption' in exported
        assert exported.count('class="markdown-math')>=4
        # Re-open the generated standalone HTML with no network.
        offline=browser.new_page(viewport={'width':1280,'height':900})
        offline_errors=[];offline.on('pageerror',lambda err:offline_errors.append(str(err)))
        offline.set_content(exported,wait_until='load')
        assert offline.locator('.report-table-wrap').count()==3
        assert offline.locator('.markdown-math svg').count()>=4
        assert offline.locator('[data-table-copy]').count()==3
        assert r'\(T_{11}\)' in offline.locator('.report-table-wrap').first.locator('.hrs-table-source-code').text_content()
        assert offline.locator('.report-table-wrap').first.locator('.hrs-table-rendered').evaluate('(n)=>getComputedStyle(n).marginTop')=='0px'
        assert offline.locator('.report-table-wrap').nth(1).locator('caption').evaluate('(n)=>getComputedStyle(n).backgroundColor')==css_color(page,'table-heading')
        assert offline.locator('.report-table-wrap').nth(2).locator('caption').inner_text().strip()=='表 3', 'uncaptioned native GFM has a derived number, without a fabricated title'
        offline.emulate_media(media='print')
        assert offline.locator('.report-table-wrap').nth(1).locator('caption').evaluate('(n)=>getComputedStyle(n).backgroundColor')==css_color(page,'table-heading')
        assert offline.locator('.hrs-table-tools').first.evaluate('(n)=>getComputedStyle(n).display')=='none'
        assert not errors,errors
        assert not offline_errors,offline_errors
        print('PF13.2 Browser: CodeMirror GFM fold, MathJax paragraph/pipe/enhanced, byte preservation, HTML export/offline/print OK')


if __name__=='__main__': unittest.main(verbosity=2)
