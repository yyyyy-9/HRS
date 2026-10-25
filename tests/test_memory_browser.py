"""MEMORY-01: reuse current-document graphics, release them across document loads."""
from pathlib import Path
import tempfile
import unittest
from browser_support import LiveDocument, browser_session, source


class DocumentCacheLifetime(unittest.TestCase):
    def test_same_document_reuses_but_next_document_rebuilds_formula_and_diagram(self):
        with tempfile.TemporaryDirectory() as folder, browser_session() as browser, LiveDocument(browser, Path(folder)) as doc:
            page = doc.page
            page.evaluate('''() => {
              window._mathCount=0; window._diagramCount=0;
              const math=MathJax.tex2svgPromise.bind(MathJax);
              MathJax.tex2svgPromise=(...args)=>{window._mathCount++;return math(...args)};
              const runtime=window.pele;
              window.pele={...runtime,render:(...args)=>{window._diagramCount++;return runtime.render(...args)}};
            }''')
            body = '\n\n$\\boldsymbol{v}=\\alpha+1$\n\n```mermaid\nflowchart LR\n A[开始]-->B[结束]\n```\n'
            for number in [1, 2]:
                project = Path(folder) / ('document' + str(number))
                (project / 'assets').mkdir(parents=True)
                text = '# Document ' + str(number) + body
                (project / 'report.md').write_text(text, encoding='utf8')
                did = f'{number:032x}'
                doc.server.registry.register(did, project)
                page.evaluate('id=>ReportStudioProgrammatic.open(id)', did)
                self.assertEqual(page.locator('#preview-content .markdown-math > svg').count(), 1)
                self.assertEqual(page.locator('#preview-content .mermaid-card svg').count(), 1)
                self.assertEqual(page.evaluate('[window._mathCount,window._diagramCount]'), [number, number])
                source(page, text + '\n普通文字修改\n')
                page.wait_for_function('document.querySelector("#preview-content").textContent.includes("普通文字修改")')
                self.assertEqual(page.evaluate('[window._mathCount,window._diagramCount]'), [number, number])
                self.assertEqual((project / 'report.md').read_text('utf8'), text)
            self.assertEqual(doc.errors, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
