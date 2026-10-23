"""NUMBERING-02 / PASTE-MATH-01: real editor, mode controls and math paste."""
import unittest
import io,json,shutil
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from browser_support import ManualService,source,value,select
from report_contract import analyze
import test_word_export_browser as previous


class UnifiedNumbering(ManualService):
    initial_markdown='# 标题\n\n## 章节\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n$$\nx=1\n$$\n\n<!-- hrs:eq id=eq-two -->\n$$\ny=2\n$$\n\n```mermaid\nflowchart LR\n A-->B\n```\n\n见 @eq:eq-two。\n'

    def test_01_modes_and_formula_switch_share_objects(self):
        p=self.page
        p.wait_for_selector('#preview-content .report-equation')
        self.assertEqual(p.locator('#preview-content .report-equation').count(),2)
        self.assertFalse(p.locator('#show-equation-numbers').is_checked())
        p.locator('#render-profile').select_option('engineering')
        p.wait_for_function("document.body.dataset.renderProfile==='engineering'")
        self.assertTrue(p.locator('#show-object-numbers').is_disabled())
        self.assertTrue(p.locator('#show-heading-numbers').is_checked())
        self.assertIn('表 1',p.locator('#preview-content .hrs-table-heading-caption').inner_text())
        self.assertIn('图 1',p.locator('#preview-content .mermaid-card figcaption').inner_text())
        p.locator('#show-equation-numbers').check()
        p.wait_for_function("document.querySelector('#preview-content').dataset.hrsShowEquationNumbers==='1'")
        self.assertEqual(p.locator('#preview-content .equation-number').all_text_contents(),['(1)','(2)'])
        self.assertEqual(p.locator('#preview-content .object-xref').inner_text(),'式 (2)')
        p.locator('#show-equation-numbers').uncheck()
        p.wait_for_function("document.querySelector('#preview-content .object-xref')?.textContent==='该公式'")
        self.assertEqual(p.locator('#preview-content .equation-number:visible').count(),0)
        self.assertEqual(value(p),self.initial_markdown)
        if self.evidence:p.screenshot(path=str(self.evidence/'engineering.png'))

    def test_02_new_formula_has_identity_without_insert_number_choice(self):
        p=self.page;before=value(p);select(p,len(before),len(before))
        p.locator('[data-command-id="equation.block"]').click()
        p.wait_for_function("document.querySelectorAll('#preview-content .report-equation').length===3")
        after=value(p)
        self.assertIn('<!-- hrs:eq id=eq-',after[len(before):])
        self.assertEqual(p.locator('[data-insert="numbered-math"], [data-command-id="equation.unnumbered"], [data-command-id="diagram.plain"]').count(),0)
        self.assertFalse(p.locator('#show-equation-numbers').is_checked())

    def test_05_plain_objects_gain_identity_only_when_referenced(self):
        p=self.page
        original='# 统一引用\n\n| 参数 | 值 |\n|---|---|\n| 电压 | 2.30 V |\n\n$$\nx=1\n$$\n\n```mermaid\nflowchart LR\n A-->B\n```\n\n参考：\n'
        source(p,original)
        p.wait_for_function("document.querySelectorAll('#preview-content .report-table-wrap,#preview-content .report-equation,#preview-content .mermaid-card').length===3")
        for kind in ['tbl','eq','fig']:
            select(p,len(original),len(original));p.locator('[data-insert="object-ref"]').click()
            p.locator('.reference-tab[data-kind="'+kind+'"]').click();p.locator('#modal-ok').click()
            p.wait_for_function("kind=>document.querySelector('#markdown').sourceEditor.value.includes('@'+kind+':')",arg=kind)
            ir=analyze(value(p));self.assertTrue(ir['ok'],ir['diagnostics'])
            self.assertEqual(len(ir['references']),1)
            self.assertIn(ir['references'][0]['target'],ir['objects']['ids'])
            self.assertIn('2.30 V',value(p))
            p.locator('#btn-undo').click()
            p.wait_for_function("md=>document.querySelector('#markdown').sourceEditor.value===md",arg=original)

    def test_06_formula_option_survives_archive_and_reading_pack(self):
        p=self.page;p.wait_for_selector('#preview-content .report-equation')
        p.locator('#show-equation-numbers').check()
        p.wait_for_function("document.querySelector('#preview-content').dataset.hrsShowEquationNumbers==='1'")
        raw=value(p);html=p.evaluate("()=>ReportStudioProgrammatic.exportHTML({quality:'original',sourceMode:'recompilable'})")
        archive=p.evaluate("async html=>{const t=document.createElement('template');t.innerHTML=html;return ReportExportArchive.readArchive(JSON.parse(t.content.querySelector('#report-source').textContent),t.content)}",html)
        self.assertEqual(archive['markdown'],raw)
        self.assertTrue(archive['renderOptions']['show_equation_numbers'])
        reader=self.browser.new_page()
        try:
            reader.set_content(html,wait_until='load')
            reader.wait_for_function("document.querySelector('main').dataset.hrsShowEquationNumbers==='1'")
            self.assertEqual(reader.locator('main .equation-number:visible').all_text_contents(),['(1)','(2)'])
            self.assertIn('式 (2)',reader.locator('main .object-xref').inner_text())
            self.assertEqual(reader.locator('main .report-table-wrap').count(),1)
        finally:reader.close()
        buffer=io.BytesIO()
        with ZipFile(buffer,'w') as zipped:
            zipped.writestr('report.md',raw)
            zipped.writestr('meta.json',json.dumps({'render_profile':'free','render_options':archive['renderOptions']}))
        p.locator('#menu-open > summary').click();p.locator('#btn-readpack').click()
        p.locator('#file-reader-zip').set_input_files({'name':'numbering.zip','mimeType':'application/zip','buffer':buffer.getvalue()})
        p.wait_for_function("document.querySelector('#reader-article').dataset.hrsShowEquationNumbers==='1'&&document.querySelectorAll('#reader-article .equation-number').length===2")
        self.assertEqual(p.locator('#reader-article .equation-number:visible').all_text_contents(),['(1)','(2)'])
        self.assertEqual(p.locator('#reader-article .object-xref').inner_text(),'式 (2)')
        p.locator('#reader-close').click();self.assertEqual(value(p),raw)

    def test_03_mathml_mixed_paste_preserves_inline_math_and_table(self):
        p=self.page;source(p,'# 粘贴\n\n');p.wait_for_function("document.querySelector('#preview-content h1')?.textContent==='粘贴'");before=value(p);select(p,len(before),len(before))
        p.context.grant_permissions(['clipboard-read','clipboard-write'])
        p.evaluate('''async()=>navigator.clipboard.write([new ClipboardItem({
          'text/plain':new Blob(['公式混合内容'],{type:'text/plain'}),
          'text/html':new Blob(['<div class="MsoNormal"><p>前文 <math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi><msup><mi>y</mi><mn>2</mn></msup></math> 后文</p><table><tr><td>值</td><td><math xmlns="http://www.w3.org/1998/Math/MathML"><mfrac><mn>1</mn><mn>2</mn></mfrac></math></td></tr></table></div>'],{type:'text/html'})})])''')
        select(p,len(before),len(before))
        p.evaluate("()=>document.addEventListener('paste',e=>window.numberingPaste={types:[...e.clipboardData.types],html:e.clipboardData.getData('text/html'),plain:e.clipboardData.getData('text/plain')},{capture:true,once:true})")
        p.keyboard.press('Control+V')
        try:p.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('前文')")
        except Exception:
            print('Math paste diagnostic:',p.evaluate("()=>({paste:window.numberingPaste,source:document.querySelector('#markdown').sourceEditor.value,toast:document.querySelector('#toast').textContent,focus:document.activeElement?.outerHTML?.slice(0,200)})"),flush=True)
            raise
        p.wait_for_function("document.querySelector('#preview-content .report-table-wrap') && document.querySelectorAll('#preview-content .markdown-math').length>=2")
        self.assertIn('前文',p.locator('#preview-content').inner_text())
        self.assertIn('后文',p.locator('#preview-content').inner_text())
        self.assertIn(r'\frac',value(p))
        p.keyboard.press('Control+Z')
        p.wait_for_function("md=>document.querySelector('#markdown').sourceEditor.value===md",arg=before)

    open_word=previous.WordUI.open_word
    compile=previous.WordUI.compile

    def test_04_word_formula_numbers_and_reference_policy(self):
        p=self.page;self.docid='e'*32;self.server.registry.register(self.docid,self.project)
        p.evaluate('id=>ReportStudioProgrammatic.open(id)',self.docid)
        source(p,'# 编号导出\n\n## 说明\n\n<!-- hrs:eq id=eq-first -->\n$$\n\\frac{x+1}{2}=\\boldsymbol{k}\n$$\n\n<!-- hrs:eq id=eq-last -->\n$$\ny=2\n$$\n\n见 @eq:eq-last。\n')
        p.wait_for_function("document.querySelectorAll('#preview-content .report-equation').length===2")
        p.locator('#show-equation-numbers').check();self.open_word();on=self.compile()
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
        with ZipFile(on) as z:root=E.fromstring(z.read('word/document.xml'))
        instructions=root.xpath('//w:instrText/text()|//w:fldSimple/@w:instr',namespaces=ns)
        self.assertEqual(sum('SEQ 公式' in x for x in instructions),2)
        self.assertTrue(any('REF HN_' in x for x in instructions))
        self.assertEqual(len(root.xpath('//m:oMath',namespaces=ns)),2)
        self.assertEqual(len(root.xpath('//m:f',namespaces=ns)),1)
        if self.evidence:shutil.copyfile(on,self.evidence/'equations_numbered.docx')
        p.locator('#show-equation-numbers').uncheck();self.open_word();off=self.compile()
        with ZipFile(off) as z:root=E.fromstring(z.read('word/document.xml'))
        instructions=root.xpath('//w:instrText/text()|//w:fldSimple/@w:instr',namespaces=ns)
        self.assertFalse(any('SEQ 公式' in x for x in instructions))
        self.assertTrue(any('HYPERLINK' in x and 'HN_' in x for x in instructions))
        self.assertIn('该公式',''.join(root.xpath('//w:t/text()',namespaces=ns)))
        self.assertEqual(len(root.xpath('//m:oMath',namespaces=ns)),2)
        if self.evidence:shutil.copyfile(off,self.evidence/'equations_unnumbered.docx')

    def test_07_plain_markdown_figures_and_tables_use_native_word_numbers(self):
        p=self.page;self.docid='e'*32;self.server.registry.register(self.docid,self.project)
        p.evaluate('id=>ReportStudioProgrammatic.open(id)',self.docid)
        original=value(p)
        index=next(i for i,b in enumerate(analyze(original)['blocks']) if b['type']=='mermaid')
        collision={'schema':'report-figure-v1','id':'fig-snapshot-'+str(index),'kind':'mermaid','source':'flowchart TB\n C[Other]-->D[Separate]','caption':'另一个图'}
        source(p,original+'\n```report-figure\n'+json.dumps(collision,ensure_ascii=False)+'\n```\n')
        p.wait_for_selector('#preview-content .mermaid-card svg')
        before=value(p);self.open_word();output=self.compile()
        with ZipFile(output) as z:root=E.fromstring(z.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        instructions=root.xpath('//w:instrText/text()|//w:fldSimple/@w:instr',namespaces=ns)
        self.assertEqual(sum('SEQ 表' in x for x in instructions),1)
        self.assertEqual(sum('SEQ 图' in x for x in instructions),2)
        self.assertFalse(any('SEQ 公式' in x for x in instructions))
        self.assertTrue(root.xpath('//w:drawing',namespaces=ns))
        graphic_ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
        self.assertEqual(len(set(root.xpath('//a:blip/@r:embed',namespaces=graphic_ns))),2,'Snapshot-local graph identities must not collide with authored IDs')
        self.assertTrue(root.xpath('//w:tbl',namespaces=ns))
        self.assertEqual(value(p),before)
        self.assertEqual((self.project/'report.md').read_text('utf8'),original)
        if self.evidence:shutil.copyfile(output,self.evidence/'native_markdown_objects.docx')

if __name__=='__main__':unittest.main()
