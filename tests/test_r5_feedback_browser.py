"""R5 feedback: actual shared editor, exact source and bounded display changes."""
import json
from browser_support import ManualService
from browser_support import source, value

TABLE={'schema':'report-table-v1','id':'tbl-r5','caption':'表题 $E=mc^2$',
       'rows':[[{'text':'参数','rowspan':1,'colspan':1}], [{'text':'内容','rowspan':1,'colspan':1}]]}
FIGURE={'schema':'report-figure-v1','id':'fig-r5','caption':'原图题', 'kind':'mermaid','source':'flowchart LR\n A[开始] --> B[结束]'}
def fence(lang,obj):return '```'+lang+'\n'+json.dumps(obj,ensure_ascii=False,indent=2)+'\n```\n'

class R5Editor(ManualService):
    def select_text(self,needle,start=0,end=None):
        self.page.wait_for_function("needle=>[...document.querySelectorAll('#preview-content [data-block-editor]')].some(n=>n.textContent.includes(needle))",arg=needle)
        self.page.evaluate('''({needle,start,end})=>{
          const target=[...document.querySelectorAll('#preview-content [data-block-editor]')].find(n=>n.textContent.includes(needle));
          target.focus({preventScroll:true});
          const walker=document.createTreeWalker(target,NodeFilter.SHOW_TEXT);const nodes=[];let n;while(n=walker.nextNode())nodes.push(n);
          const text=nodes.map(n=>n.nodeValue).join(''),at=text.indexOf(needle);let offset=0,a,b;
          for(const node of nodes){if(!a&&offset+node.length>=at+start)a=[node,at+start-offset];if(!b&&offset+node.length>=at+end)b=[node,at+end-offset];offset+=node.length;}
          const r=document.createRange();r.setStart(...a);r.setEnd(...b);const s=getSelection();s.removeAllRanges();s.addRange(r);
        }''',{'needle':needle,'start':start,'end':len(needle.encode('utf-16-le'))//2 if end is None else end})

    def test_01_quote_wrap_split_and_chinese_italic(self):
        raw='# 显示\n\n>s\n>x\n\n*中文斜体* *abcd*\n\n'+'长段文字😀'*90+'\n'
        source(self.page,raw)
        self.assertEqual(self.page.locator('#preview-content blockquote p').evaluate('n=>getComputedStyle(n).whiteSpace'),'pre-line')
        self.assertIn('style',self.page.locator('#preview-content em').first.evaluate('n=>getComputedStyle(n).fontSynthesis'))
        self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.view.lineWrapping")
        self.assertLess(self.page.locator('.cm-scroller').evaluate('n=>n.scrollWidth-n.clientWidth'),6)
        self.page.locator('#source-wrap').uncheck();self.page.wait_for_function("!document.querySelector('#markdown').sourceEditor.view.lineWrapping")
        self.assertGreater(self.page.locator('.cm-scroller').evaluate('n=>n.scrollWidth-n.clientWidth'),1000)
        self.page.locator('#source-wrap').check();self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.view.lineWrapping")
        divider=self.page.locator('#split-divider');divider.focus()
        for _ in range(18):self.page.keyboard.press('ArrowLeft')
        self.assertEqual(divider.get_attribute('aria-valuenow'),'30')
        for _ in range(25):self.page.keyboard.press('ArrowRight')
        self.assertEqual(divider.get_attribute('aria-valuenow'),'70')
        self.page.set_viewport_size({'width':700,'height':900});self.assertFalse(divider.is_visible())
        self.assertEqual(value(self.page),raw)

    def test_02_preview_selection_formats_and_inserts_at_real_position(self):
        raw='# 编辑😀\r\n\r\n## 章节\r\n\r\n前文 **加粗文字** 和 *斜体文字*，结尾。\r\n'
        source(self.page,raw)
        self.page.evaluate("document.querySelector('#markdown').sourceEditor.setSelectionRange(0)")
        self.select_text('结尾')
        self.page.locator('[data-insert=bold]').click()
        self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('**结尾**')")
        self.select_text('前文')
        self.page.locator('[data-insert=italic]').click()
        self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('*前文*')")
        self.select_text('加粗文字',2,2)
        self.page.locator('[data-insert=inline-math]').click()
        self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('加粗$E=mc^2$文字')")
        self.assertTrue(value(self.page).startswith('# 编辑😀\r\n'))
        self.assertIn('和 *斜体文字*',value(self.page))

    def test_03_folded_table_edit_and_preview_object_delete_undo(self):
        raw='# 对象\n\n## 章节\n\n'+fence('report-table',TABLE)
        source(self.page,raw)
        self.page.locator('.source-fold-summary button').filter(has_text='编辑').click()
        self.page.locator('#modal-ok').wait_for(state='visible')
        self.page.locator('#modal-cancel').click()
        self.page.locator('#preview-content .hrs-table-tools').click(position={'x':8,'y':8})
        self.page.wait_for_function("document.querySelector('.preview-object-selected')!==null")
        self.page.keyboard.press('Delete')
        self.page.wait_for_function("!document.querySelector('#markdown').sourceEditor.value.includes('tbl-r5')")
        self.page.locator('#btn-undo').click()
        self.page.wait_for_function("document.querySelector('#preview-content table')!==null")
        self.assertEqual(value(self.page),raw)

    def test_04_list_inline_edit_keeps_markers_nested_task_and_other_bytes(self):
        raw='# 清单\r\n\r\n## 章节\r\n\r\n- 第一项\r\n  - 子项目\r\n- [ ] 待办事项\r\n\r\n保留 **正文**。\r\n'
        source(self.page,raw)
        target=self.page.locator('#preview-content [data-block-editor]').filter(has_text='第一项')
        target.dblclick();self.assertEqual(target.get_attribute('contenteditable'),'true')
        self.page.keyboard.press('Control+a');self.page.keyboard.insert_text('改过的第一项')
        self.page.locator('#source-wrap').click()
        self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('- 改过的第一项\\r\\n')")
        self.assertIn('  - 子项目\r\n- [ ] 待办事项',value(self.page))
        self.assertTrue(value(self.page).endswith('保留 **正文**。\r\n'))
        nested=self.page.locator('#preview-content [data-block-editor]').filter(has_text='子项目')
        nested.dblclick();self.page.keyboard.press('End');self.page.keyboard.press('Enter')
        try:self.page.wait_for_function("document.activeElement?.classList.contains('preview-text-editor')&&document.activeElement.isContentEditable")
        except Exception:
            print('LIST_ENTER_DEBUG',value(self.page),self.page.locator('#preview-content .doc-block[data-type=list]').inner_html(),self.page.evaluate('document.activeElement.outerHTML'),flush=True);raise
        self.page.keyboard.insert_text('新增细节')
        self.page.locator('#preview-content input.hrs-task-checkbox').check()
        self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('  - 子项目\\r\\n  - 新增细节\\r\\n- [x] 待办事项')")

    def test_05_caption_inline_math_and_undo(self):
        raw='# 题注\n\n## 章节\n\n'+fence('report-figure',FIGURE)+'\n'+fence('report-table',TABLE)
        source(self.page,raw)
        self.page.wait_for_function("document.querySelector('#preview-content caption .markdown-math > svg')!==null")
        self.page.locator('#preview-content figcaption').dblclick()
        field=self.page.get_by_role('textbox',name='编辑题注');field.fill('新图题 $x^2$');field.press('Enter')
        self.page.wait_for_function("document.querySelector('#preview-content figcaption .markdown-math > svg')!==null")
        self.assertIn('新图题 $x^2$',value(self.page))
        self.page.locator('#btn-undo').click();self.page.wait_for_function("document.querySelector('#preview-content figcaption').textContent.includes('原图题')")
        self.assertEqual(value(self.page),raw)
        self.page.locator('[data-view=reading]').click();self.page.locator('#preview-content figcaption').click()
        self.assertFalse(self.page.locator('.preview-object-selected').count())

    def test_06_typing_and_same_source_render_keep_preview_anchor(self):
        key='a'*32;self.server.registry.register(key,self.project)
        self.page.evaluate('id=>ReportStudioProgrammatic.open(id)',key)
        text='# 长稿\n\n## 章节\n\n'+('\n\n'.join('段落%d：保持滚动位置。'%i for i in range(100)))+'\n\n'+fence('report-figure',FIGURE)
        source(self.page,text)
        self.page.locator('#follow-scroll').check()
        self.page.evaluate("()=>{const p=document.querySelector('#preview-content');p.closest('.page-scroll').scrollTop=1800;const e=document.querySelector('#markdown').sourceEditor;e.setSelectionRange(e.value.indexOf('段落0'));e.focus();}")
        before=self.page.locator('.page-scroll').first.evaluate('n=>n.scrollTop')
        self.page.keyboard.insert_text('新输入😀')
        self.page.wait_for_timeout(650)
        after=self.page.locator('.page-scroll').first.evaluate('n=>n.scrollTop')
        self.assertLess(abs(after-before),3)
        self.page.locator('#btn-save').click()
        self.page.wait_for_function("document.querySelector('#save-indicator').textContent.includes('已保存')&&!document.querySelector('#markdown').sourceEditor.readOnly")
        saved=self.page.locator('.page-scroll').first.evaluate('n=>n.scrollTop')
        self.assertLess(abs(saved-after),3)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'editor-layout.png'))

    def test_07_pipe_caption_formula_note_and_late_dom_range_guard(self):
        raw='# 题注\n\n## 内容\n\n| 参数 | 说明 |\n| --- | --- |\n| A | 文本 |\n\n[^a]: 说明来源。\n'
        source(self.page,raw)
        self.page.locator('#preview-content .hrs-table-kind').dblclick()
        field=self.page.get_by_role('textbox',name='编辑题注');field.fill('新表题 $x^2$[^a]');field.press('Enter')
        self.page.wait_for_function("document.querySelector('#preview-content caption .markdown-math > svg')!==null")
        self.assertIn(': 新表题 $x^2$[^a] {#tbl-',value(self.page))
        self.assertEqual(self.page.locator('#preview-content .hrs-footnotes li').count(),1)
        guard=self.page.evaluate(r'''()=>{
          const old='前文😀\r\n同名内容\r\n尾部';const start=old.indexOf('同名');
          const shifted=SourceMap.rebaseUnchanged('增加'+old,old,{start,end:start+4},'同名内容');
          let denied=false;try{SourceMap.rebaseUnchanged(old.replace('同名内容','已改内容'),old,{start,end:start+4},'同名内容')}catch{denied=true}
          return {shifted,denied,start};
        }''')
        self.assertEqual(guard['shifted']['start'],guard['start']+2);self.assertTrue(guard['denied'])

    def test_08_image_zoom_group_caption_and_export_have_no_editor_selection(self):
        from PIL import Image
        for name,color in [('a.png','blue'),('b.png','green')]:Image.new('RGB',(60,30),color).save(self.project/'assets'/name)
        image={'schema':'report-figure-v1','id':'fig-photo','caption':'单图题','kind':'image','src':'assets/a.png','alt':'单图'}
        raw='# 图形\n\n## 内容\n\n'+fence('report-figure',image)+'\n::: {#fig-group layout-ncol=2}\n\n![子图 $x^2$](assets/a.png)\n\n![第二张](assets/b.png)\n\n组图题\n\n:::\n'
        source(self.page,raw)
        self.page.wait_for_function("document.querySelector('#preview-content .image-group-subcaption .markdown-math > svg')!==null")
        self.page.locator('#preview-content .report-figure-wrap:not(.report-image-group) img').click()
        self.page.get_by_role('dialog',name='查看图片').wait_for(state='visible');self.page.get_by_role('button',name='关闭',exact=True).click()
        self.page.locator('#preview-content .report-image-group figcaption').dblclick()
        field=self.page.get_by_role('textbox',name='编辑题注');field.fill('组图新题 $E=mc^2$');field.press('Enter')
        self.page.wait_for_function("document.querySelector('#preview-content .report-image-group figcaption .markdown-math > svg')!==null")
        self.assertIn('::: {#fig-group layout-ncol=2}',value(self.page));self.assertNotIn('```report-image-group',value(self.page))
        self.page.locator('#preview-content .report-image-group figcaption').click(position={'x':4,'y':4})
        self.assertEqual(self.page.locator('.preview-object-selected').count(),1)
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        offline=self.browser.new_page();offline.set_content(html)
        self.assertEqual(offline.locator('.preview-object-selected,[data-block-editor],[contenteditable]').count(),0)
        self.assertEqual(offline.locator('.image-group-subcaption .markdown-math > svg').count(),1);offline.close()
