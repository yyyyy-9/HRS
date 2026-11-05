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
            # MATH-PERF-01: a document working set larger than the former LRU
            # must not repeatedly compile unchanged math on a prose edit.
            dense = '# Dense\n\n正文。\n\n' + '\n\n'.join(f'$x+{n}$' for n in range(900)) + '\n'
            source(page, dense)
            page.wait_for_function('document.querySelectorAll("#preview-content .markdown-math > svg").length===900')
            count = page.evaluate('window._mathCount')
            source(page, dense.replace('正文。', '正文修改。'))
            page.wait_for_function('document.querySelector("#preview-content").textContent.includes("正文修改")')
            self.assertEqual(page.evaluate('window._mathCount'), count)
            page.get_by_role('button', name='Markdown', exact=True).click()
            hidden = dense.replace('正文。', '正文源码编辑。') + '\n## 隐藏预览时的新标题\n\n$z+901$\n'
            source(page, hidden)
            page.wait_for_function('document.querySelector("#toc").textContent.includes("隐藏预览时的新标题")')
            self.assertEqual(page.evaluate('window._mathCount'), count)
            self.assertNotIn('正文源码编辑', page.locator('#preview-content').text_content())
            page.get_by_role('button', name='分屏', exact=True).click()
            page.wait_for_function('document.querySelectorAll("#preview-content .markdown-math > svg").length===901')
            self.assertEqual(page.evaluate('window._mathCount'), count + 1)
            self.assertIn('正文源码编辑', page.locator('#preview-content').text_content())
            # A conversion already in flight may finish, but must not commit a
            # stale snapshot while the debounce for the newer text is pending.
            page.evaluate('''()=>{
              window.holdNextMath=()=>{delete window.releaseMath;const convert=MathJax.tex2svgPromise;
                MathJax.tex2svgPromise=(...args)=>{MathJax.tex2svgPromise=convert;
                  return convert(...args).then(svg=>new Promise(resolve=>{window.releaseMath=()=>resolve(svg);}));};};
              holdNextMath();
              window.committedSnapshots=[];
              window.commitObserver=new MutationObserver(()=>committedSnapshots.push(document.querySelector('#preview-content').textContent));
              commitObserver.observe(document.querySelector('#preview-content'),{childList:true,subtree:true});
            }''')
            source(page, '# Pending\n\n$u+9999$\n')
            page.wait_for_function('typeof releaseMath==="function"')
            source(page, '# Latest\n\n$v+10000$\n');page.evaluate('releaseMath()')
            page.wait_for_function('document.querySelector("#preview-content .markdown-math")?.dataset.tex==="v+10000"')
            self.assertFalse(page.evaluate('committedSnapshots.some(text=>text.includes("Pending"))'))
            page.evaluate('commitObserver.disconnect()')
            # Export temporarily owns presentation options. A cancelled preview
            # must catch up after they are restored; archive stays source-exact.
            page.evaluate('holdNextMath()')
            export_source = '# Export latest\n\n$w+10001$\n'
            source(page, export_source);page.wait_for_function('typeof releaseMath==="function"')
            archived=page.evaluate('''async()=>{setTimeout(()=>releaseMath(),150);
              const html=await ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'});
              const doc=new DOMParser().parseFromString(html,'text/html');return JSON.parse(doc.querySelector('#report-source').textContent).markdown;
            }''')
            self.assertEqual(archived,export_source)
            page.wait_for_function('document.querySelector("#preview-content .markdown-math")?.dataset.tex==="w+10001"')
            # Definition-bearing source bypasses ordinary reuse. The existing
            # converter, not this cache, determines its macro support/scope.
            macro = '# Macro\n\n$\\gdef\\hrsvar{x}\\hrsvar+1$\n\n$\\hrsvar+2$\n'
            source(page, macro)
            page.wait_for_function('document.querySelectorAll("#preview-content .markdown-math > svg").length===2')
            glyphs = page.locator('#preview-content .markdown-math').first.locator('[data-c]').evaluate_all('xs=>xs.map(x=>x.getAttribute("data-c"))')
            count = page.evaluate('window._mathCount')
            source(page, macro.replace('Macro', 'Macro prose'))
            page.wait_for_function('document.querySelector("#preview-content h1")?.textContent==="Macro prose"')
            self.assertEqual(page.evaluate('window._mathCount'), count + 2)
            source(page, macro.replace('{x}', '{y}'))
            page.wait_for_function('document.querySelector("#preview-content .markdown-math")?.dataset.tex.includes("{y}")')
            changed = page.locator('#preview-content .markdown-math').first.locator('[data-c]').evaluate_all('xs=>xs.map(x=>x.getAttribute("data-c"))')
            self.assertNotEqual(changed, glyphs)
            self.assertEqual(page.locator('#preview-content .math-error').count(), 0)
            self.assertEqual(doc.errors, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
