"""TEST-SYSTEM-01: retained regression assertions, now using the actual local API."""
from pathlib import Path
import io, json, re, tempfile, unittest, zipfile
from browser_support import LiveDocument, browser_session

READPACK_MD='\\[\nK=\\frac{d\\beta}{d\\lambda}\n\\]\n\n\\[\nR=0.98\n\\]\n\n```text\n\\[\nnot-a-formula\n\\]\n```\n'

MD='# PF13.3 公式合成验收\n\n正文行内公式 \\(T_{11}\\) 与代码 `\\[ literal \\]`。\n\n\\[\nK=\\left|\\frac{d\\beta}{d\\lambda}\\right|=3.59\\ \\mathrm{\\mu m/pm}\n\\]\n\n\\[\nR=0.98085\\approx98.1\\%\n\\]\n\n| A | B |\n|---|---|\n| \\(T_{11}\\) | 结果 |\n'

class BracketMath(unittest.TestCase):
    def test_original_preview_export_and_reader_regression(self):
      with browser_session() as browser, tempfile.TemporaryDirectory(prefix='hrs-retained-') as directory:
       with LiveDocument(browser,Path(directory),MD,profile='engineering') as document:
        page=document.page; errors=document.errors
        page.locator('.markdown-math.math-display svg').first.wait_for(timeout=16000)
        assert page.locator('.markdown-math.math-display').count()==2
        assert page.locator('.markdown-math.math-inline').count()==2
        assert page.locator('.math-error').count()==0
        assert page.locator('.markdown-math svg').count()>page.locator('.markdown-math').count(), 'nested SVG precondition'
        assert page.evaluate('document.querySelector("#markdown").value')==MD
        exported=document.export()
        archive=json.loads(re.search(r'<script type="application/json" id="report-source">(.*?)</script>',exported,re.S)[1])
        assert archive['markdown']==MD
        offline=browser.new_page()
        offline_errors=[]
        offline.on('pageerror',lambda err:offline_errors.append(str(err)))
        offline.set_content(exported,wait_until='load')
        assert offline.locator('.markdown-math.math-display').count()==2
        assert offline.locator('.markdown-math.math-inline').count()==2
        assert offline.locator('.markdown-math.math-display > svg').count()==2
        assert offline.locator('.report-table-wrap').count()==1
        assert not offline_errors,offline_errors
        # The separate read-only bundle viewer must render math too, but leave
        # fenced code untouched and never change the user's editable document.
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w') as archive:archive.writestr('calc.md',READPACK_MD)
        page.locator('#menu-open > summary').click();page.locator('#btn-readpack').click()
        page.locator('#file-reader-zip').set_input_files({'name':'math.zip','mimeType':'application/zip','buffer':memory.getvalue()})
        page.locator('#reader-article .markdown-math.math-display > svg').first.wait_for(timeout=15000)
        assert page.locator('#reader-article .markdown-math.math-display > svg').count()==2
        assert page.locator('#reader-article pre code').count()==1
        assert 'not-a-formula' in page.locator('#reader-article pre code').inner_text()
        assert page.evaluate('document.querySelector("#markdown").value')==MD
        assert page.locator('#reader-status').get_attribute('data-bad')!='1'
        page.locator('#reader-close').click()
        assert not errors,errors
        print('PF13.3 Browser: bracket display + inline math + nested SVG + export + offline archive + exact source OK')


if __name__=='__main__': unittest.main(verbosity=2)
