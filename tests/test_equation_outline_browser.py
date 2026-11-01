"""MATH-UX-02 / OUTLINE-01: shared real editor and actual native input."""
import base64,json,re,time
from unittest.mock import patch
from browser_support import ManualService,QuietHandler,source,value,select,wait_rich_clipboard

TEX=r'''\begin{aligned}
a_j(p)&=bF_j(0)\\
&\quad+\sum_{r\in W}h_j(r)[M(p-r)-b],\\
I(p)&=\sum_j|a_j(p)|^2.
\end{aligned}\tag{2}'''

class EquationOutline(ManualService):
    def test_26_undo_from_source_only_retains_multiline_crlf_tag_and_identity(self):
        body=r'a_j=\mathcal F^{-1}\{F_j\mathcal F M\},\quad'+'\r\n'+r'h_j=\mathcal F^{-1}F_j.\tag{2}'
        raw='# 原稿\r\n\r\n<!-- hrs:eq id=eq-crlf-history -->\r\n\\[\r\n'+body+'\r\n\\]\r\n'
        self.free(raw);self.page.locator('#preview-content .math-display').dblclick()
        self.page.locator('math-field[data-ready="1"]').wait_for()
        field=self.page.locator('[data-formula-source]');initial=field.input_value()
        field.fill(r'\def\hrsUnknown{x}')
        self.page.wait_for_function('document.querySelector("math-field").readOnly')
        field.press('Control+z');self.assertEqual(field.input_value(),initial)
        self.assertFalse(self.page.locator('math-field').evaluate('m=>m.readOnly'))
        prevented=field.evaluate('f=>!f.dispatchEvent(new InputEvent("beforeinput",{bubbles:true,cancelable:true,inputType:"historyRedo"}))')
        self.assertTrue(prevented);self.assertEqual(field.input_value(),r'\def\hrsUnknown{x}')
        field.press('Control+z');self.page.locator('#modal-ok').click()
        self.assertEqual(value(self.page),raw)

    def test_24_history_restores_selection_and_applies_as_one_host_edit(self):
        raw='# 选区\n\n$$\nx=1\n$$\n';self.free(raw)
        self.page.locator('#preview-content .math-display').dblclick()
        self.page.locator('math-field[data-ready="1"]').wait_for()
        field=self.page.locator('[data-formula-source]');field.focus();field.evaluate('f=>f.setSelectionRange(0,1)')
        self.page.get_by_role('button',name='分式',exact=True).click()
        fraction=field.input_value();self.assertIn(r'\frac{分子}{分母}',fraction)
        self.page.locator('.formula-history').get_by_role('button',name='撤销',exact=True).click()
        self.assertEqual(field.input_value(),'x=1')
        self.assertEqual(field.evaluate('f=>[f.selectionStart,f.selectionEnd]'),[0,1])
        self.page.locator('.formula-history').get_by_role('button',name='重做',exact=True).click()
        self.assertEqual(field.input_value(),fraction)
        self.assertEqual(field.evaluate('f=>f.value.slice(f.selectionStart,f.selectionEnd)'),'分子')
        field.press('1');self.page.keyboard.press('Tab');self.page.keyboard.type('2')
        self.page.get_by_role('button',name='宽空格',exact=True).click()
        final=field.input_value();self.page.locator('#modal-ok').click()
        self.assertIn(final,value(self.page));self.assertNotEqual(value(self.page),raw)
        self.page.locator('#markdown').evaluate('n=>n.sourceEditor.focus()');self.page.keyboard.press('Control+z')
        self.assertEqual(value(self.page),raw)
        self.page.keyboard.press('Control+Shift+z');self.assertIn(final,value(self.page))

    def test_25_composition_is_one_draft_step_and_history_is_session_bounded(self):
        raw='# 输入法\n\n$$\nx=1\n$$\n';self.free(raw)
        self.page.locator('#preview-content .math-display').dblclick()
        self.page.locator('math-field[data-ready="1"]').wait_for()
        field=self.page.locator('[data-formula-source]');field.focus()
        # Browser composition events with intermediate input, not a mocked
        # history API. Native Windows IME still needs its separate manual check.
        field.evaluate('f=>{f.dispatchEvent(new CompositionEvent("compositionstart",{bubbles:true}));for(const text of ["中","中文"]){f.value=text;f.dispatchEvent(new InputEvent("input",{bubbles:true,isComposing:true,inputType:"insertCompositionText"}));}f.dispatchEvent(new CompositionEvent("compositionend",{bubbles:true,data:"中文"}));}')
        field.press('Control+z');self.assertEqual(field.input_value(),'x=1')
        field.press('Control+y');self.assertEqual(field.input_value(),'中文')
        field.evaluate('f=>{f.dispatchEvent(new CompositionEvent("compositionstart",{bubbles:true}));f.dispatchEvent(new CompositionEvent("compositionend",{bubbles:true}));}')
        self.assertFalse(self.page.locator('.formula-history').get_by_role('button',name='撤销',exact=True).is_disabled())
        for i in range(105):field.fill('x='+str(i))
        for _ in range(100):field.press('Control+z')
        self.assertTrue(self.page.locator('.formula-history').get_by_role('button',name='撤销',exact=True).is_disabled())
        self.assertEqual(field.input_value(),'x=4')
        self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)

    def test_23_dialog_history_spans_source_tools_and_visual_without_editing_host(self):
        raw='# 历史\r\n\r\n<!-- hrs:eq id=eq-history -->\r\n\\[\r\nx=1\\tag{7}\r\n\\]\r\n'
        self.free(raw);self.page.locator('#preview-content .math-display').first.dblclick()
        math=self.page.locator('math-field[data-ready="1"]');math.wait_for()
        undo=self.page.locator('.modal-head').get_by_role('button',name='撤销',exact=True)
        redo=self.page.locator('.modal-head').get_by_role('button',name='重做',exact=True)
        self.assertTrue(undo.is_visible());self.assertTrue(undo.is_disabled());self.assertTrue(redo.is_disabled())
        field=self.page.locator('[data-formula-source]');initial=field.input_value()
        field.fill(r'y=2\tag{7}');self.page.get_by_role('button',name='转为多行',exact=True).click()
        multiline=field.input_value();self.assertIn('aligned',multiline)
        undo.click();self.assertEqual(field.input_value(),r'y=2\tag{7}')
        field.focus();self.page.keyboard.press('Control+z');self.assertEqual(field.input_value(),initial)
        self.assertEqual(value(self.page),raw)
        self.page.keyboard.press('Control+Shift+z');self.assertEqual(field.input_value(),r'y=2\tag{7}')
        self.page.keyboard.press('Control+y');self.assertEqual(field.input_value(),multiline)
        undo.click();undo.click();self.assertTrue(undo.is_disabled())
        self.page.locator('#modal-ok').click();self.assertEqual(value(self.page),raw)
        self.page.locator('#preview-content .math-display').first.dblclick();math.wait_for()
        self.assertTrue(undo.is_disabled());self.assertTrue(redo.is_disabled())
        hit=math.locator('.ML__mathit').filter(has_text='x').bounding_box()
        self.page.mouse.click(hit['x']+hit['width']/2,hit['y']+hit['height']/2)
        self.page.wait_for_function('document.activeElement===document.querySelector("math-field")')
        math.evaluate('m=>m.executeCommand("moveToMathfieldEnd")')
        self.page.keyboard.type('+z')
        self.page.wait_for_function('document.querySelector("[data-formula-source]").value.includes("z")')
        visual=field.input_value();self.assertIn('z',visual)
        self.assertTrue(visual.endswith(r'\tag{7}'),'Visual input preserves the tag after the formula')
        if self.evidence:self.page.screenshot(path=str(self.evidence/'formula-title-history.png'))
        math.press('Control+z');self.assertEqual(field.input_value(),initial)
        redo.click();self.assertEqual(field.input_value(),visual)
        undo.click();field.fill(r'\frac{');self.assertTrue(redo.is_disabled())
        undo.click();self.assertEqual(field.input_value(),initial)
        self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)

    def test_20_formula_samples_spacing_and_rows_preserve_the_draft(self):
        """MATH-UX-04: meaningful pictures, spacing and native row insertion."""
        raw='# 公式工具\r\n\r\n<!-- hrs:eq id=eq-tools -->\r\n\\[\r\nx=1\\tag{7}\r\n\\]\r\n'
        self.free(raw);self.page.locator('#preview-content .markdown-math').first.dblclick()
        math=self.page.locator('#modal-body math-field[data-ready="1"]');math.wait_for()
        self.page.get_by_role('button',name='分段函数',exact=True).wait_for(timeout=3000)
        self.page.wait_for_function('document.querySelectorAll(".formula-structure-sample svg").length>=10')
        field=self.page.locator('[data-formula-source]')
        field.focus();field.evaluate('e=>e.setSelectionRange(3,3)')
        self.page.get_by_role('button',name='宽空格',exact=True).click()
        self.assertIn(r'x=1\quad',field.input_value());self.assertIn(r'\tag{7}',field.input_value())
        self.page.get_by_role('button',name='多行等号对齐',exact=True).click()
        self.assertIn(r'\begin{aligned}',field.input_value());self.assertIn('\\\\',field.input_value())
        field.fill(r'\begin{aligned}a&=b\\c&=d\end{aligned}\tag{7}')
        self.page.wait_for_function('document.querySelector("math-field").getValue("latex").includes("aligned")')
        self.page.wait_for_function('document.querySelector("math-field").getValue("latex").includes("c")')
        box=math.locator('.ML__mathit').filter(has_text='a').bounding_box()
        self.page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
        before=field.input_value().count('\\\\')
        self.page.get_by_role('button',name='新增一行',exact=True).click()
        self.page.wait_for_function('a=>document.querySelector("[data-formula-source]").value.split(a.separator).length-1>a.count',arg={'count':before,'separator':r'\\'})
        self.assertNotIn(r'\displaylines',field.input_value());self.assertIn(r'\begin{aligned}',field.input_value())
        self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)

    def test_21_plain_formula_multiline_and_inline_policy(self):
        """MATH-UX-04: explicit wrapping, no guessing equations or inline display mode."""
        raw='# 换行\n\n$$\nx=1\n$$\n\n行内 $y=2$。\n'
        self.free(raw);self.page.locator('#preview-content .math-display').first.dblclick()
        self.page.locator('math-field[data-ready="1"]').wait_for()
        self.page.get_by_role('button',name='转为多行',exact=True).click()
        field=self.page.locator('[data-formula-source]')
        self.assertIn('\\begin{aligned}\nx=1\n',field.input_value())
        self.assertIn('\\\\',field.input_value());self.assertNotIn('x&=1',field.input_value())
        self.page.locator('#modal-ok').click()
        self.assertIn('\\begin{aligned}\nx=1\n',value(self.page))
        self.page.locator('#markdown').evaluate('n=>n.sourceEditor.focus()');self.page.keyboard.press('Control+z')
        self.assertEqual(value(self.page),raw)
        self.page.wait_for_function('raw=>document.querySelector("#preview-content .doc-block")?._sourceDocument===raw',arg=raw)
        self.page.locator('#preview-content .math-inline').first.dblclick()
        self.page.locator('math-field[data-ready="1"]').wait_for()
        for name in ('新增一行','转为多行','多行等号对齐'):
            self.assertTrue(self.page.get_by_role('button',name=name,exact=True).is_disabled())
        self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)

    def test_22_source_row_scope_spacing_export_and_visual_spacing(self):
        """MATH-UX-04: source insertion respects structural groups and really exports TeX."""
        body=r'\begin{cases}\frac{a}{b}&x>0\\0&x\leq0\end{cases}'
        raw='# 分段\n\n$$\n'+body+'\n$$\n';self.free(raw)
        self.page.locator('#preview-content .math-display').first.dblclick()
        math=self.page.locator('math-field[data-ready="1"]');math.wait_for()
        field=self.page.locator('[data-formula-source]');field.focus()
        field.evaluate('(e,at)=>e.setSelectionRange(at,at)',body.index('{a}')+2)
        self.page.get_by_role('button',name='新增一行',exact=True).click()
        self.assertEqual(field.input_value(),body,'No row separator in a numerator')
        field.evaluate('(e,at)=>e.setSelectionRange(at,at)',body.index('x>0')+3)
        self.page.get_by_role('button',name='窄空格',exact=True).click()
        self.assertIn(r'x>0\,',field.input_value())
        self.page.get_by_role('button',name='新增一行',exact=True).click()
        self.assertIn('x>0\\,\\\\\n',field.input_value())
        self.page.locator('#modal-ok').click()
        html=self.page.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})')
        self.assertIn('data-hrs-reader-root',html);self.assertIn('data-mml-node="mtable"',html)
        self.assertNotIn('data-mml-node="merror"',html)
        self.assertIn(r'x>0\,',value(self.page));self.assertIn('\\\\\n',value(self.page))
        self.page.locator('#markdown').evaluate('n=>n.sourceEditor.focus()');self.page.keyboard.press('Control+z')
        self.assertEqual(value(self.page),raw)
        self.page.wait_for_function('raw=>document.querySelector("#preview-content .doc-block")?._sourceDocument===raw',arg=raw)
        self.page.locator('#preview-content .math-display').first.dblclick();math.wait_for()
        box=math.locator('.ML__mathit').filter(has_text='a').bounding_box()
        self.page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
        self.page.get_by_role('button',name='宽空格',exact=True).click()
        self.page.wait_for_function('document.querySelector("[data-formula-source]").value.includes("\\\\quad")')
        self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)

    def free(self,raw):
        source(self.page,raw);self.page.locator('#render-profile').select_option('free')
        self.page.wait_for_function('document.querySelector("#preview-content").dataset.hrsRenderProfile==="free"')
        self.page.wait_for_function('!document.querySelector("#render-profile").disabled')
        self.page.wait_for_function('raw=>document.querySelector("#preview-content .doc-block")?._sourceDocument===raw',arg=raw)

    def test_01_inserted_block_selects_tex_and_source_range_remains_visible(self):
        self.free('# 范围\n\n');select(self.page,len(value(self.page)),len(value(self.page)))
        self.page.locator('[data-insert="math"]').first.click()
        selected=self.page.locator('#markdown').evaluate('n=>n.sourceEditor.value.slice(n.sourceEditor.selectionStart,n.sourceEditor.selectionEnd)')
        self.assertEqual(selected,r'\eta=\frac{\Delta L}{L_0}')
        self.page.wait_for_selector('.cm-hf8-equation-line')
        self.assertGreaterEqual(self.page.locator('.cm-hf8-equation-line').count(),3)
        self.assertIn('$$',self.page.locator('.cm-content').inner_text())

    def test_02_legacy_tag_is_preserved_but_one_math_number_obeys_switch(self):
        raw='# 编号\n\n\\[\n'+TEX+'\n\\]\n\n$$\ny=2\n$$\n'
        self.free(raw);self.page.locator('#show-equation-numbers').check()
        self.page.wait_for_selector('#preview-content .equation-number svg')
        self.assertEqual(self.page.locator('#preview-content .equation-number').all_text_contents(),['(1)','(2)'])
        self.assertEqual(self.page.locator('#preview-content .math-display [data-mml-node="mlabeledtr"]').count(),0)
        self.page.locator('#show-equation-numbers').uncheck()
        self.page.wait_for_function('document.querySelector("#preview-content").dataset.hrsShowEquationNumbers==="0"')
        self.assertEqual(self.page.locator('#preview-content .equation-number:visible').count(),0)
        self.assertEqual(value(self.page),raw)
        html=self.page.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})')
        self.assertIn('\\\\tag{2}',html)

    def test_05_outline_tree_depth_and_grip_move_whole_sections_with_undo(self):
        first='## 第一节 {#sec-first}\r\n\r\n正文😀。\r\n\r\n### 子节\r\n\r\n$$\nx=1\n$$\r\n\r\n'
        second='## 第二节 {#sec-second}\r\n\r\n结果。\r\n'
        raw='# 专题\r\n\r\n'+first+second;self.free(raw)
        self.page.wait_for_selector('#toc .toc-node')
        self.assertEqual(self.page.locator('#toc>.toc-children>.toc-node').count(),1)
        self.page.locator('.toc-level-control select').select_option('2')
        self.assertFalse(self.page.locator('#toc a').filter(has_text='子节').is_visible(),self.page.locator('#toc').inner_html())
        self.page.locator('.toc-level-control select').select_option('all')
        self.assertTrue(self.page.locator('#toc a').filter(has_text='子节').is_visible())
        self.page.get_by_role('button',name='拖动整节：第一节',exact=True).focus()
        self.page.keyboard.press('Alt+ArrowDown')
        self.page.wait_for_function('expected=>document.querySelector("#markdown").sourceEditor.value===expected',arg='# 专题\r\n\r\n'+second+'\r\n'+first)
        self.assertEqual(value(self.page).count('x=1'),1)
        self.page.keyboard.press('Control+z');self.assertEqual(value(self.page),raw)

    def test_03_plain_source_copy_creates_new_formula_identity_and_undo(self):
        equation='<!-- hrs:eq id=eq-original -->\n\\[\nx^2+1\n\\]\n'
        raw='# 复制\n\n'+equation+'\n见 @eq:eq-original。\n'
        self.free(raw);self.page.wait_for_selector('#preview-content .report-equation')
        self.page.context.grant_permissions(['clipboard-read','clipboard-write'])
        start=raw.index('<!-- hrs:eq');select(self.page,start,start+len(equation))
        self.page.keyboard.press('Control+c')
        wait_rich_clipboard(self.page,equation)
        select(self.page,len(raw),len(raw));self.page.keyboard.press('Control+v')
        self.page.wait_for_function('document.querySelectorAll("#preview-content .report-equation").length===2')
        ids=re.findall(r'<!-- hrs:eq id=(eq-[\w-]+) -->',value(self.page))
        self.assertEqual(len(ids),2);self.assertEqual(len(set(ids)),2)
        self.assertTrue(value(self.page).startswith(raw))
        self.page.keyboard.press('Control+z');self.assertEqual(value(self.page),raw)

    def test_04_visual_math_and_source_share_draft_cancel_and_one_commit(self):
        equation='<!-- hrs:eq id=eq-edit -->\r\n\\[\r\n\\frac{a}{b}+\\boldsymbol{\\alpha}\r\n\\]\r\n'
        raw='# 编辑\r\n\r\n'+equation+'\r\n后文😀。\r\n';self.free(raw)
        self.page.locator('#preview-content .markdown-math').first.dblclick()
        math=self.page.locator('#modal-body math-field');math.wait_for(state='visible')
        self.assertEqual(self.page.locator('#modal-body [data-formula-source]').input_value(),r'\frac{a}{b}+\boldsymbol{\alpha}')
        # Use the visible input. Calling focus()+a selection command in the same
        # JS turn races the component's focus handling in old Chromium.
        math.click();self.page.keyboard.press('Control+End');self.page.keyboard.type('+z')
        self.page.wait_for_function('()=>{const text=document.querySelector("[data-formula-source]").value;return text.includes("z")&&text===document.querySelector("math-field").getValue("latex");}')
        self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)
        self.page.locator('#preview-content .markdown-math').first.dblclick();math.wait_for(state='visible')
        field=self.page.locator('#modal-body [data-formula-source]');field.fill(r'\frac{m}{n}+\boldsymbol{\beta}')
        self.page.wait_for_function('document.querySelector("math-field").value.includes("beta")')
        self.page.locator('#modal-ok').click()
        expected=raw.replace(r'\frac{a}{b}+\boldsymbol{\alpha}',r'\frac{m}{n}+\boldsymbol{\beta}')
        self.assertEqual(value(self.page),expected)
        self.page.locator('#markdown').evaluate('n=>n.sourceEditor.focus()');self.page.keyboard.press('Control+z')
        self.assertEqual(value(self.page),raw)

    def test_06_snippet_fields_persist_insert_at_heading_and_undo(self):
        raw='# 专题\r\n\r\n## 实验\r\n\r\n原始数据。\r\n\r\n## 结论\r\n\r\n保留。\r\n';self.free(raw)
        self.page.locator('#btn-snippets').click()
        self.page.get_by_label('片段名称',exact=True).fill('测量记录')
        self.page.get_by_label('片段 Markdown',exact=True).fill('{{date}} {{field:样品}}\n\n结果 {{cursor}}。')
        self.page.get_by_role('button',name='保存片段',exact=True).click()
        self.page.wait_for_function('document.querySelector(".snippet-tools [role=status]").textContent==="已保存"')
        self.page.locator('[data-field="样品"]').fill('S😀')
        self.page.get_by_label('插入位置',exact=True).select_option('1')
        self.page.locator('#modal-ok').click();self.page.wait_for_function('document.querySelector("#markdown").sourceEditor.value.includes("S😀")')
        current=value(self.page);self.assertTrue(current.endswith('## 结论\r\n\r\n保留。\r\n'));self.assertNotIn('{{',current)
        self.assertNotRegex(current,r'(?<!\r)\n');self.assertEqual(self.page.locator('#markdown').evaluate('n=>n.sourceEditor.value[n.sourceEditor.selectionStart]'),'。')
        self.page.keyboard.press('Control+z');self.assertEqual(value(self.page),raw)
        self.page.locator('#btn-snippets').click();self.page.get_by_label('选择片段').select_option(label='测量记录')
        self.assertIn('{{field:样品}}',self.page.get_by_label('片段 Markdown',exact=True).input_value());self.page.locator('#modal-cancel').click()

    def test_07_references_navigate_without_source_hover_or_usage_dialog(self):
        """READING-UX-03: remove the redundant UI, retain normal target links."""
        raw='# 引用\n\n## 目的 {#sec-purpose}\n\n正文。\n\n见 @sec:sec-purpose；说明[^note]。\n\n`@sec:sec-purpose`\n\n[^note]: 来源说明。\n';self.free(raw)
        self.assertEqual(self.page.locator('#btn-reference-uses').count(),0)
        link=self.page.locator('#preview-content [data-xref-target="sec-purpose"]');link.wait_for();link.hover()
        # The former source hover used a 350 ms timer; observe beyond that.
        self.page.wait_for_timeout(450)
        self.assertEqual(self.page.locator('.reference-context,.reference-use-list').count(),0)
        link.click();self.page.wait_for_function('document.querySelector("#preview-content .navigation-highlight h2")')
        self.page.locator('[data-view="reading"]').click()
        self.page.wait_for_function('!document.querySelector("#preview-content [data-block-editor]")')
        self.page.locator('#preview-content [data-xref-target="sec-purpose"]').click()
        self.assertTrue(self.page.locator('#edit-layout').evaluate('n=>n.classList.contains("reading")'))
        self.page.locator('#preview-content a.hrs-note-link:not(.hrs-note-back)').click()
        self.assertFalse(self.page.locator('#modal-layer').is_visible())
        self.assertEqual(value(self.page),raw)

    def test_12_reading_has_no_mutating_objects_tasks_or_outline_grips(self):
        """READING-UX-03: same source, real double-clicks and task inputs."""
        self.project.joinpath('assets','a.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9e8AAAAASUVORK5CYII='))
        figure={'schema':'report-figure-v1','id':'fig-photo','kind':'image','src':'assets/a.png','caption':'图片题注','alt':'图片'}
        table={'schema':'report-table-v1','id':'tbl-data','caption':'增强表题','rows':[[{'text':'内容','rowspan':1,'colspan':1}]]}
        raw='# 阅读\n\n## 目的\n\n普通正文。\n\n- [ ] 保持未完成\n\n'
        for kind,obj in [('report-figure',figure),('report-table',table)]:raw+='```'+kind+'\n'+json.dumps(obj,ensure_ascii=False)+'\n```\n\n'
        raw+='| 列名 |\n| --- |\n| 数据 |\n\n```mermaid\nflowchart LR\n A-->B\n```\n\n$$\n\\frac{a}{b}\n$$\n'
        raw+='\n::: {#fig-group layout-ncol=2}\n![左图](assets/a.png)\n![右图](assets/a.png)\n组图题注\n:::\n'
        self.free(raw);self.page.locator('[data-view="reading"]').click()
        self.page.wait_for_function('!document.querySelector("#preview-content [data-block-editor]")')
        self.assertEqual(self.page.locator('#preview-content [data-edit-figure]:visible,#preview-content [data-table-edit]:visible,#toc .toc-grip:visible').count(),0)
        checkbox=self.page.locator('#preview-content .hrs-task-checkbox');self.assertTrue(checkbox.is_disabled())
        self.assertTrue(self.page.locator('#btn-undo').is_disabled())
        self.page.keyboard.press('Control+z');self.assertEqual(value(self.page),raw)
        for selector in ('p','h2','.report-figure-caption','.report-figure-wrap','.report-table-wrap','.mermaid-card','.markdown-math'):
            for node in self.page.locator('#preview-content '+selector).all():
                node.dblclick()
                self.assertFalse(self.page.locator('#modal-layer').is_visible(),selector)
                self.assertEqual(self.page.locator('#preview-content [contenteditable=true]').count(),0)
                self.assertEqual(value(self.page),raw)
        self.page.locator('[data-view="split"]').click()
        self.page.wait_for_selector('#preview-content [data-edit-figure]')
        self.assertTrue(checkbox.is_enabled())
        self.page.locator('#preview-content .report-table-wrap').first.dblclick()
        self.assertTrue(self.page.locator('#modal-layer').is_visible());self.page.locator('#modal-cancel').click()
        self.assertEqual(value(self.page),raw)

    def test_13_outline_same_level_labels_align_with_or_without_children(self):
        """OUTLINE-02: H1-H6 peer rows reserve disclosure space; collapse is stable."""
        raw=''
        for level in range(1,7):
            if level>1:
                raw+='# Section'+str(level)+'\n\n'
                for parent in range(2,level):raw+='#'*parent+' Ancestor'+str(level)+'-'+str(parent)+'\n\n'
            raw+='#'*level+' Branch'+str(level)+'\n\n'
            if level<6:raw+='#'*(level+1)+' Child'+str(level)+'\n\n'
            raw+='#'*level+' Leaf'+str(level)+'\n\n'
        self.free(raw);self.page.wait_for_selector('#toc .toc-node')
        for level in range(1,7):
            branch=self.page.locator('#toc a').filter(has_text='Branch'+str(level));leaf=self.page.locator('#toc a').filter(has_text='Leaf'+str(level))
            self.assertAlmostEqual(branch.bounding_box()['x'],leaf.bounding_box()['x'],delta=1,msg='H'+str(level))
        branch=self.page.locator('#toc .toc-node').filter(has=self.page.get_by_role('link',name='Branch2',exact=True)).last
        before=self.page.get_by_role('link',name='Leaf2',exact=True).bounding_box()['x']
        branch.locator(':scope > .toc-row > .toc-toggle').click()
        self.assertAlmostEqual(self.page.get_by_role('link',name='Leaf2',exact=True).bounding_box()['x'],before,delta=1)

    def test_14_equation_spacing_shared_and_long_word_stays_one_paragraph(self):
        """MATH-UX-03: layout changes no TeX/source, long words are line wrapping."""
        long_word='d'*140
        raw='# 排版\n\n中文背景 '+long_word+' 后续。\n\n$$\nx=1\n$$\n\n$$\n\\frac{a}{b}\n$$\n'
        self.free(raw);self.page.wait_for_selector('#preview-content .math-display svg')
        measure='''root=>[...root.querySelectorAll('.report-equation>.math-display')].map(n=>({height:n.getBoundingClientRect().height,math:n.querySelector('svg').getBoundingClientRect().height,margin:parseFloat(getComputedStyle(n).marginTop)+parseFloat(getComputedStyle(n).marginBottom),padding:parseFloat(getComputedStyle(n).paddingTop)+parseFloat(getComputedStyle(n).paddingBottom)}))'''
        editor=self.page.locator('#preview-content').evaluate(measure)
        self.assertLess(editor[0]['height']+editor[0]['margin'],65)
        self.assertLessEqual(editor[0]['padding'],16)
        self.assertEqual(self.page.locator('#preview-content p').count(),1)
        self.assertEqual(self.page.locator('#preview-content p br').count(),0)
        self.assertIn(long_word,self.page.locator('#preview-content p').inner_text())
        html=self.document.export();path=self.folder/'spacing.html';path.write_text(html,encoding='utf8',newline='')
        reader=self.browser.new_page();reader.goto(path.as_uri())
        offline=reader.locator('main').evaluate(measure);reader.close()
        self.assertEqual(len(offline),2)
        for live,saved in zip(editor,offline):
            self.assertAlmostEqual(live['padding'],saved['padding'],delta=.1)
            self.assertAlmostEqual(live['margin'],saved['margin'],delta=.1)
        self.assertEqual(value(self.page),raw)

    def test_15_formula_selection_is_visible_and_drag_and_group_keep_focus(self):
        """MATH-UX-03: real pointer selection, visible contrast and whole-group tools."""
        raw='# 选中公式\n\n$$\n\\frac{abc}{def}+x^2\n$$\n';self.free(raw)
        self.page.locator('.markdown-math').first.dblclick();math=self.page.locator('math-field');math.wait_for(state='visible')
        self.assertGreaterEqual(math.evaluate('n=>parseFloat(getComputedStyle(n).fontSize)'),24)
        colors=math.evaluate('n=>{const s=getComputedStyle(n);return [s.getPropertyValue("--selection-background-color").trim(),s.getPropertyValue("--selection-color").trim()]}')
        self.assertNotEqual(colors[0],colors[1]);self.assertTrue(all(colors))
        # Drag over a denominator using physical hit-test coordinates, then
        # replace just that selection. No force events or model selection API.
        start=math.locator('.ML__mathit').filter(has_text=re.compile('^d$')).bounding_box()
        finish=math.locator('.ML__mathit').filter(has_text=re.compile('^f$')).bounding_box()
        self.page.mouse.move(start['x']+.5,start['y']+start['height']/2);self.page.mouse.down()
        self.page.mouse.move(finish['x']+finish['width']-.5,finish['y']+finish['height']/2,steps=12);self.page.mouse.up()
        self.assertFalse(math.evaluate('n=>n.selectionIsCollapsed'))
        self.page.keyboard.type('m')
        self.page.wait_for_function('document.querySelector("[data-formula-source]").value.includes("{m}")')
        self.assertIn(r'\frac{abc}{m}',self.page.locator('[data-formula-source]').input_value())
        # Clicking a selection tool must not discard the math selection or
        # modify the draft; typing afterwards replaces the selected formula.
        self.page.get_by_role('button',name='全选公式',exact=True).click()
        self.assertFalse(math.evaluate('n=>n.selectionIsCollapsed'))
        self.page.keyboard.type('y')
        self.page.wait_for_function('document.querySelector("[data-formula-source]").value==="y"')
        self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)

    def test_16_fourier_formula_mouse_caret_drag_and_replace_inner_expression(self):
        """MATH-UX-03: user's actual mathcal/subscript/inverse-Fourier example."""
        tex=r'''a_j=\mathcal F^{-1}\{F_j\mathcal F M\},\quad
h_j=\mathcal F^{-1}F_j.'''
        raw='# 傅里叶公式\n\n$$\n'+tex+'\n$$\n';self.free(raw)
        self.page.locator('.markdown-math').first.dblclick();math=self.page.locator('math-field');math.wait_for(state='visible')
        self.assertEqual(math.evaluate('n=>n.errors'),[])
        h=math.locator('.ML__mathit').filter(has_text=re.compile('^h$')).bounding_box()
        self.page.mouse.click(h['x']+h['width']*.8,h['y']+h['height']/2)
        # The component hands focus to its keyboard sink after the mouse
        # event. Exercise keys only when native focus has actually arrived.
        self.page.wait_for_function('document.activeElement===document.querySelector("math-field")')
        self.assertTrue(self.page.evaluate('Array.from(document.fonts).some(f=>f.family==="KaTeX_Caligraphic"&&f.status==="loaded")'))
        at=math.evaluate('n=>n.position');self.page.keyboard.press('ArrowLeft')
        self.assertLess(math.evaluate('n=>n.position'),at)
        self.page.keyboard.press('ArrowRight');self.assertEqual(math.evaluate('n=>n.position'),at)
        start=math.locator('.ML__mathit').filter(has_text=re.compile('^F$')).first.bounding_box()
        end=math.locator('.ML__mathit').filter(has_text=re.compile('^M$')).bounding_box()
        self.page.mouse.move(start['x']+.5,start['y']+start['height']/2);self.page.mouse.down()
        self.page.mouse.move(end['x']+end['width']-.5,end['y']+end['height']/2,steps=18);self.page.mouse.up()
        selected=math.evaluate('n=>n.getValue(n.selection,"latex")')
        self.assertIn(r'F_{j}',selected);self.assertIn(r'\mathcal{F}M',selected);self.assertNotIn('h_',selected)
        self.assertEqual(self.page.locator('[data-formula-source]').input_value(),tex)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'fourier-selection.png'))
        self.page.keyboard.type('u')
        self.page.wait_for_function('document.querySelector("[data-formula-source]").value.includes("u")')
        edited=self.page.locator('[data-formula-source]').input_value()
        self.assertIn(r'\{u\}',edited);self.assertIn(r'h_{j}=\mathcal{F}^{-1}F_{j}',edited)
        self.page.locator('#modal-ok').click();self.assertIn(edited,value(self.page))
        self.page.locator('#markdown').evaluate('n=>n.sourceEditor.focus()');self.page.keyboard.press('Control+z')
        self.assertEqual(value(self.page),raw)

    def test_17_first_math_hit_surface_waits_for_real_font_registration(self):
        """MATH-UX-03: slow actual font response must not expose fallback bounds."""
        tex=r'a_j=\mathcal F^{-1}\{F_j\mathcal F M\},\quad h_j=\mathcal F^{-1}F_j.'
        raw='# 字体加载\n\n$$\n'+tex+'\n$$\n';self.free(raw)
        get=QuietHandler.do_GET;requests=[]
        def delayed(handler):
            if handler.path.split('?')[0].endswith('/KaTeX_Caligraphic-Regular.woff2'):
                requests.append(handler.path);time.sleep(2)
            return get(handler)
        with patch.object(QuietHandler,'do_GET',delayed):
            self.page.locator('.markdown-math').first.dblclick()
            self.page.locator('math-field').wait_for(state='visible')
            self.assertEqual(len(requests),1,'The slow real font path was not exercised')
            self.assertTrue(self.page.evaluate('Array.from(document.fonts).some(f=>f.family==="KaTeX_Caligraphic"&&f.status==="loaded")'))
        self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)

    def test_18_mouse_selects_scripts_and_function_without_flattening_neighbor_structure(self):
        """MATH-UX-03: selecting is verified by actual replacement, not highlight."""
        tex=r'a_j=\mathcal F^{-1}\{F_j\mathcal F M\},\quad h_j=\mathcal F^{-1}F_j.'
        raw='# 上下标与函数\n\n$$\n'+tex+'\n$$\n';self.free(raw)
        for kind in ('subscript','superscript','function'):
            with self.subTest(kind=kind):
                if self.page.locator('#modal-layer').is_visible():self.page.locator('#modal-cancel').click()
                self.page.locator('.markdown-math').first.dblclick();math=self.page.locator('math-field');math.wait_for(state='visible')
                if kind=='subscript':
                    box=math.locator('.ML__mathit').filter(has_text=re.compile('^j$')).first.bounding_box()
                    self.page.mouse.dblclick(box['x']+box['width']/2,box['y']+box['height']/2)
                    replacement,expected='k',r'a_{k}=\mathcal{F}^{-1}'
                else:
                    if kind=='superscript':
                        start=math.locator('.ML__cmr').filter(has_text=re.compile('^−$')).first.bounding_box()
                        end=math.locator('.ML__cmr').filter(has_text=re.compile('^1$')).first.bounding_box()
                        replacement,expected='3',r'a_{j}=\mathcal{F}^3'
                    else:
                        start=end=math.locator('.ML__cal').first.bounding_box()
                        replacement,expected='G',r'a_{j}=G^{-1}'
                    self.page.mouse.move(start['x']+.3,start['y']+start['height']/2);self.page.mouse.down()
                    self.page.mouse.move(end['x']+end['width']-.3,end['y']+end['height']/2,steps=12);self.page.mouse.up()
                self.page.wait_for_function('document.activeElement===document.querySelector("math-field")')
                self.assertFalse(math.evaluate('n=>n.selectionIsCollapsed'))
                if self.evidence:self.page.screenshot(path=str(self.evidence/(kind+'-selection.png')))
                self.page.keyboard.type(replacement)
                self.page.wait_for_function('v=>document.querySelector("[data-formula-source]").value.includes(v)',arg=expected)
                edited=self.page.locator('[data-formula-source]').input_value()
                self.assertIn(r'h_{j}=\mathcal{F}^{-1}F_{j}',edited)
                self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)

    def test_19_named_function_and_reverse_script_drag_keep_math_structure(self):
        """MATH-UX-03: predefined function atoms and reverse-direction selection."""
        raw='# 函数\n\n$$\n\\sin x+\\mathcal F^{-1}\n$$\n';self.free(raw)
        self.page.locator('.markdown-math').first.dblclick();math=self.page.locator('math-field');math.wait_for(state='visible')
        function=math.locator('.ML__base').get_by_text('sin',exact=True).last.bounding_box()
        self.page.mouse.dblclick(function['x']+function['width']/2,function['y']+function['height']/2)
        self.page.wait_for_function('document.activeElement===document.querySelector("math-field")')
        self.assertEqual(math.evaluate('n=>n.getValue(n.selection,"latex")'),r'\sin')
        self.page.keyboard.type('cos');self.page.wait_for_function('document.querySelector("[data-formula-source]").value.includes("cos")')
        self.assertIn(r'\cos',self.page.locator('[data-formula-source]').input_value())
        start=math.locator('.ML__cmr').filter(has_text=re.compile('^1$')).bounding_box()
        end=math.locator('.ML__cmr').filter(has_text=re.compile('^−$')).bounding_box()
        self.page.mouse.move(start['x']+start['width']-.3,start['y']+start['height']/2);self.page.mouse.down()
        self.page.mouse.move(end['x']+.3,end['y']+end['height']/2,steps=12);self.page.mouse.up()
        self.assertEqual(math.evaluate('n=>n.getValue(n.selection,"latex")'),'-1')
        self.page.keyboard.type('2');self.page.wait_for_function('document.querySelector("[data-formula-source]").value.includes("\\\\mathcal{F}^2")')
        self.page.locator('#modal-ok').click();self.assertIn(r'\cos x+\mathcal{F}^2',value(self.page))
        self.page.locator('#markdown').evaluate('n=>n.sourceEditor.focus()');self.page.keyboard.press('Control+z');self.assertEqual(value(self.page),raw)

    def test_08_outline_pointer_drag_and_unchanged_tree_reuse(self):
        raw='# 专题\n\n## 第一节\n\n甲。\n\n## 第二节\n\n乙。\n';self.free(raw)
        self.page.wait_for_selector('#toc .toc-node')
        self.page.locator('#toc a').first.evaluate('n=>window.tocAnchor=n')
        select(self.page,raw.index('甲'),raw.index('甲'));self.page.keyboard.type('x')
        self.page.wait_for_function('document.querySelector("#preview-content").textContent.includes("x甲")')
        self.assertTrue(self.page.locator('#toc a').first.evaluate('n=>n===window.tocAnchor'))
        grip=self.page.get_by_role('button',name='拖动整节：第二节',exact=True);target=self.page.get_by_role('link',name='第一节',exact=True)
        grip.drag_to(target,target_position={'x':10,'y':2})
        self.page.wait_for_function('n=>{const v=document.querySelector("#markdown").sourceEditor.value;return v.indexOf("第二节")<v.indexOf("第一节")}',arg=None)
        self.assertIn('x甲',value(self.page));self.page.locator('#markdown').evaluate('n=>n.sourceEditor.focus()');self.page.keyboard.press('Control+z')
        self.assertEqual(value(self.page),raw.replace('甲','x甲'))

    def test_09_visual_noop_preserves_raw_tag_and_source_template_tabs(self):
        raw='# 公式\n\n\\[\n'+TEX+'\n\\]\n';self.free(raw)
        self.page.locator('.markdown-math').first.dblclick();self.page.locator('math-field').wait_for(state='visible');self.page.locator('#modal-ok').click()
        self.assertEqual(value(self.page),raw)
        self.page.locator('.markdown-math').first.dblclick();field=self.page.locator('[data-formula-source]');field.focus();field.press('Control+a');self.page.keyboard.press('Backspace')
        self.page.get_by_role('button',name='分式',exact=True).click();self.page.keyboard.type('a');self.page.keyboard.press('Tab');self.page.keyboard.type('b')
        self.assertEqual(field.input_value(),r'\frac{a}{b}');self.page.locator('#modal-ok').click();self.assertIn(r'\frac{a}{b}',value(self.page))

    def test_10_mouse_edits_denominator_and_unknown_commands_keep_source(self):
        raw='# 公式\n\n$$\n\\frac{a}{b}\n$$\n';self.free(raw)
        self.page.locator('.markdown-math').first.dblclick();math=self.page.locator('math-field');math.wait_for(state='visible')
        # MathLive's hit-test surface intentionally covers its character spans.
        # Use the actual mouse at the displayed denominator, as a user does.
        box=math.locator('.ML__mathit').filter(has_text='b').bounding_box();self.page.mouse.dblclick(box['x']+box['width']/2,box['y']+box['height']/2);self.page.keyboard.type('m')
        self.page.wait_for_function('document.querySelector("[data-formula-source]").value==="\\\\frac{a}{m}"')
        self.page.locator('#modal-ok').click();self.assertIn(r'\frac{a}{m}',value(self.page))
        self.page.locator('.markdown-math').first.dblclick();field=self.page.locator('[data-formula-source]');field.fill(r'\notAnHRSCommand{x}')
        self.page.wait_for_function('document.querySelector("math-field").readOnly')
        self.assertEqual(field.input_value(),r'\notAnHRSCommand{x}');self.page.locator('#modal-cancel').click()

    def test_11_virtual_keyboard_entry_and_automatic_open_are_disabled(self):
        raw='# 实体键盘\n\n$$\nx^2\n$$\n';self.free(raw)
        self.page.locator('.markdown-math').first.dblclick();math=self.page.locator('math-field');math.wait_for(state='visible')
        self.assertFalse(math.locator('[part="virtual-keyboard-toggle"]').is_visible())
        math.click();self.page.keyboard.press('Alt+Shift+Space')
        self.page.evaluate('()=>window.mathVirtualKeyboard.show()')
        self.assertFalse(self.page.evaluate('()=>window.mathVirtualKeyboard.visible'))
        self.page.locator('#modal-cancel').click();self.assertEqual(value(self.page),raw)

if __name__=='__main__':
    import unittest
    unittest.main()
