"""MERMAID-01: official offline renderer, source-preserving editing and export.

Real local service and Chromium; only the inherited test-owned save chooser
is replaced. Requests are observed, never mocked. User source stays unchanged.
"""
from pathlib import Path
import io,json,os,re,unittest,zipfile
from collections import Counter
from browser_support import ManualService
from browser_support import source,value

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'tests/fixtures/mermaid_full.json').read_text('utf8'))

def manuscript(cases=CASES):
    return '# Mermaid 验证\n\n'+''.join('## '+c['name']+'\n\n```mermaid\n'+c['source']+'\n```\n\n' for c in cases)

class MermaidFull(ManualService):
    def setUp(self):
        super().setUp()
        self.external=[]
        self.page.on('request',lambda r:self.external.append(r.url) if re.match(r'https?://',r.url) and not r.url.startswith(f'http://127.0.0.1:{self.server.server_port}/') else None)

    def load_diagrams(self,cases=CASES):
        text=manuscript(cases);source(self.page,text)
        self.page.wait_for_function('({n,text})=>document.querySelectorAll("#preview-content .mermaid-card svg").length===n&&[...document.querySelectorAll("#preview-content .doc-block")].every(b=>b._sourceDocument===text)',arg={'n':len(cases),'text':text})
        self.assertEqual(self.page.locator('#preview-content .diagram-error').count(),0)
        return text

    def test_01_supplied_three_and_full_engine_diagram_types(self):
        text=self.load_diagrams()
        for i,case in enumerate(CASES[:4]):
            self.assertEqual(self.page.locator('#preview-content .mermaid-card').nth(i).locator('g.node').count(),case['nodes'])
        first=self.page.locator('#preview-content .mermaid-card').first
        self.assertIn('0.5 nm',first.inner_text());self.assertNotIn('<br',first.inner_text())
        boxes=first.locator('g.node').evaluate_all('ns=>ns.map(n=>n.getBoundingClientRect().toJSON())')
        for i,a in enumerate(boxes):
            for b in boxes[i+1:]:
                self.assertFalse(a['left']<b['right']-1 and b['left']<a['right']-1 and a['top']<b['bottom']-1 and b['top']<a['bottom']-1,'Nodes overlap')
        self.assertEqual(value(self.page),text);self.assertEqual(self.external,[])
        ids=self.page.locator('#preview-content svg [id],#preview-content svg[id]').evaluate_all('xs=>xs.map(e=>e.id)')
        self.assertEqual(len(ids),len(set(ids)),str({k:v for k,v in Counter(ids).items() if v>1}))
        if self.evidence:
            self.page.locator('[data-view=reading]').click()
            self.page.wait_for_function('document.querySelectorAll("#preview-content .mermaid-card svg").length===9')
            for i in range(3):self.page.locator('#preview-content .mermaid-card').nth(i).screenshot(path=str(self.evidence/f'user-{i+1}.png'))

    def test_02_edit_multiline_label_and_complex_source_without_loss(self):
        text=self.load_diagrams(CASES[:1]);self.page.locator('#preview-content .mermaid-card').dblclick()
        self.page.wait_for_selector('#modal-layer:not([hidden])')
        self.page.wait_for_selector('#modal-body .modal-diagram-svg svg')
        name=self.page.locator('#modal-body [aria-label="节点文字"]')
        self.assertEqual(name.input_value(),'PLD100L\n0.5 nm')
        name.fill('PLD100L\n0.6 nm')
        self.page.locator('#modal-ok').click()
        self.page.wait_for_function('document.querySelector("#preview-content .mermaid-card")?.textContent.includes("0.6 nm")')
        self.assertIn('<br/>0.6 nm',value(self.page))
        complex_text=self.load_diagrams(CASES[3:4]);self.page.locator('#preview-content .mermaid-card').dblclick()
        self.page.wait_for_selector('#modal-body .modal-diagram-svg svg')
        field=self.page.locator('.diagram-source-input');self.assertEqual(field.input_value(),CASES[3]['source'])
        field.fill(CASES[3]['source'].replace('输入','输入源'))
        self.page.wait_for_function('document.querySelector(".modal-diagram-svg")?.textContent.includes("输入源")')
        self.page.locator('#modal-ok').click()
        self.page.wait_for_function('document.querySelector("#preview-content .mermaid-card")?.textContent.includes("输入源")')
        self.assertEqual(value(self.page),complex_text.replace('输入','输入源'))

    def test_03_recompilable_offline_html_and_native_reading_pack(self):
        text=self.load_diagrams()
        html=self.page.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})')
        self.assertNotIn('mermaid.min.js',html,'Static export must not need the rendering library')
        dest=self.folder/'mermaid.html';dest.write_text(html,encoding='utf8')
        reader=self.browser.new_page();external=[]
        reader.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) else None)
        reader.goto(dest.as_uri());self.assertEqual(reader.locator('main .mermaid-card svg').count(),len(CASES))
        self.assertEqual(external,[]);reader.close()
        restored=self.page.evaluate('async html=>{const doc=new DOMParser().parseFromString(html,"text/html");return (await ReportExportArchive.readArchive(JSON.parse(doc.querySelector("#report-source").textContent),doc)).markdown;}',html)
        self.assertEqual(restored,text)
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w') as archive:archive.writestr('REPORT.md',text.encode('utf8'))
        self.page.locator('#file-reader-zip').set_input_files({'name':'mermaid.zip','mimeType':'application/zip','buffer':memory.getvalue()})
        self.page.wait_for_function('n=>document.querySelectorAll("#reader-article .hrs-mermaid-render svg").length===n',arg=len(CASES))
        self.assertEqual(value(self.page),text);self.assertEqual(self.external,[])

    def test_04_formal_figure_and_error_recovery(self):
        figure={'schema':'report-figure-v1','id':'fig-optics','kind':'mermaid','caption':'测试光路','source':CASES[0]['source']}
        text='# 工程报告\n\n## 光路\n\n```report-figure\n'+json.dumps(figure,ensure_ascii=False)+'\n```\n\n参见 @fig:fig-optics。\n'
        source(self.page,text)
        self.page.wait_for_selector('#preview-content figure[data-figure-id="fig-optics"] svg')
        self.page.locator('#render-profile').select_option('engineering')
        self.page.wait_for_function('document.body.dataset.renderProfile==="engineering"')
        html=self.page.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})')
        self.assertIn('测试光路',html);self.assertEqual(value(self.page),text)
        source(self.page,'# 错误\n\n```mermaid\nflowchart TB\n A[broken\n```\n')
        self.page.wait_for_selector('#preview-content .diagram-error')
        self.assertNotIn('存在渲染失败',self.page.locator('#preview-content').inner_text())
        self.page.evaluate('()=>window._mermaidProbe=0')
        safe='flowchart LR\n A["<script>window._mermaidProbe=1</script>安全"] --> B[结束]\n click B "javascript:window._mermaidProbe=2"'
        source(self.page,manuscript([{'name':'安全标签','source':safe}]))
        self.page.wait_for_selector('#preview-content .mermaid-card svg')
        self.assertEqual(self.page.evaluate('window._mermaidProbe'),0)
        self.assertEqual(self.page.locator('#preview-content svg script,#preview-content svg [onclick],#preview-content svg a[href^="javascript:"]').count(),0)
        self.assertEqual(self.external,[])

    def test_05_unmanaged_resources_are_rejected_before_network(self):
        code='flowchart LR\n A@{ img: "https://example.invalid/a.png", label: "外部图片" }'
        result=self.page.evaluate('async code=>{try{await ReportMermaid.render(code);return "unexpected success";}catch(e){return e.message;}}',code)
        self.assertIn('外部',result)
        override='%%{init: {"themeCSS":"@import url(https://example.invalid/style.css);","securityLevel":"loose"}}%%\nflowchart LR\n A[安全]-->B[文本]'
        svg=self.page.evaluate('code=>ReportMermaid.render(code)',override)
        self.assertNotIn('example.invalid',svg)
        self.assertEqual(self.external,[])

if __name__=='__main__':unittest.main(verbosity=2)
