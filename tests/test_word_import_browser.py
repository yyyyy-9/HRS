"""WORD-IMPORT-UI-01: native-selected DOCX through the real Bridge and page.

Only the system file/folder selection is substituted. The shipped component,
scanner, recognition, OMML adapter, serializers and project API all execute.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,os,unittest
from unittest.mock import patch
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.shared import Inches
from docx.text.paragraph import Paragraph
from lxml import etree as E
from PIL import Image
from browser_support import ManualService,source,value
from test_numbering_v2_contract import compound_math, native_math_fixture
import studio


def native_link(p,label,target=None,anchor=None,bold=False):
    node=OxmlElement('w:hyperlink')
    if target is not None:node.set(qn('r:id'),p.part.relate_to(target,RT.HYPERLINK,is_external=True))
    if anchor is not None:node.set(qn('w:anchor'),anchor)
    for part in label if isinstance(label,list) else [label]:
        run=OxmlElement('w:r')
        if bold:
            properties=OxmlElement('w:rPr');properties.append(OxmlElement('w:b'));run.append(properties)
        text=OxmlElement('w:t');text.text=part;run.append(text);node.append(run)
    p._p.append(node)
    return node


def native_bookmark(p,name,ident):
    start=OxmlElement('w:bookmarkStart');start.set(qn('w:id'),str(ident));start.set(qn('w:name'),name)
    end=OxmlElement('w:bookmarkEnd');end.set(qn('w:id'),str(ident));p._p.insert(0,start);p._p.append(end)


class WordImport(ManualService):
    def setUp(self):
        super().setUp()
        self.input=self.folder/(self._testMethodName+'.docx')
        self.png=self.folder/(self._testMethodName+'.png')
        Image.new('RGB',(48,24),'navy').save(self.png)
        doc=Document();doc.add_paragraph('导入报告',style='Title');doc.add_heading('目的',level=1)
        doc.add_paragraph('保留量值 12.34 nm，普通 @fig:literal 不激活。')
        doc.add_paragraph('表1 参数表')
        table=doc.add_table(rows=2,cols=2)
        table.cell(0,0).text='参数';table.cell(0,1).text='数值'
        table.cell(1,0).text='行内公式 '
        math=OxmlElement('m:oMath');run=OxmlElement('m:r');text=OxmlElement('m:t');text.text='x'
        run.append(text);math.append(run);table.cell(1,0).paragraphs[0]._p.append(math)
        table.cell(1,1).text='12.34'
        p=doc.add_paragraph();p.add_run().add_picture(str(self.png));p.add_run('   ');p.add_run().add_picture(str(self.png))
        doc.add_paragraph('图1 两幅原图')
        doc.save(self.input);self.original=self.input.read_bytes()
        self.picker=patch.object(studio,'pick_import_file',return_value=self.input)
        self.picker.start();self.addCleanup(self.picker.stop)

    def read_word(self):
        self.page.locator('#menu-open>summary').click();self.page.locator('#btn-import-word').click()
        self.page.wait_for_function("document.querySelector('#modal-title').firstChild.textContent==='导入 Word'")
        self.assertEqual(self.page.locator('#modal-title .beta-badge').inner_text(),'beta')
        self.page.locator('#modal-ok').click()
        self.page.wait_for_function("document.querySelector('#modal-title').firstChild.textContent==='核对 Word 导入结果'||document.querySelector('#toast').textContent.includes('导入失败')",timeout=90000)
        self.assertEqual(self.page.locator('#modal-title').evaluate('n=>n.firstChild.textContent'),'核对 Word 导入结果',self.page.locator('#toast').inner_text())
        self.assertEqual(self.page.locator('#modal-title .beta-badge').inner_text(),'beta')

    def save_import(self,name):
        # Bind the result to this import, including failures after an earlier
        # successful import has already displayed a toast.
        self.page.locator('#toast').evaluate('n=>{n.textContent=""}')
        self.choose_destination(name)
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('Word 已导入')||document.querySelector('#toast').textContent.includes('导入失败')",timeout=30000)

    def choose_destination(self,name):
        self.page.locator('#modal-ok').click()
        self.page.wait_for_selector('#modal-body input[aria-label="项目文件夹名称"]')
        self.page.locator('#modal-body input').fill(name);self.page.locator('#modal-ok').click()
        self.page.locator('.confirm-window button').filter(has_text='确认位置').click()

    def test_real_docx_table_math_group_save_reopen_and_archive_without_node(self):
        # WORD-IMPORT-GROUPS-01: an inline-only paragraph is still a group
        # when the two native extents exceed the page width before scaling.
        doc=Document(self.input);row=doc.paragraphs[-2];row.clear()
        row.add_run().add_picture(str(self.png),width=Inches(3.4));row.add_run('\t');row.add_run().add_picture(str(self.png),width=Inches(3.4))
        doc.save(self.input);self.original=self.input.read_bytes()
        # The page's browser is already running; GUI import must never launch
        # another one or depend on a system Node executable.
        with patch.dict(os.environ,{'HRS_BRIDGE_NODE':'Z:/absent-node.exe','CHROMIUM_PATH':'Z:/absent-browser.exe'}):
            self.read_word()
            self.assertIn('结构转换完成',self.page.locator('#word-import-summary').inner_text())
            self.save_import('Word导入专项')
        target=self.destination/'Word导入专项';self.assertTrue(target.is_dir(),self.page.locator('#toast').inner_text())
        md=value(self.page);self.assertIn('12.34 nm',md);self.assertIn('\\@fig:literal',md)
        self.assertIn('$x$',md);self.assertIn('report-table-v1',md)
        model=studio.analyze_report_contract(md,assets=target/'assets')
        self.assertEqual(len([b for b in model['blocks'] if b['type']=='image-group']),1)
        self.page.wait_for_function("()=>{const a=[...document.querySelectorAll('#preview-content img')];a.forEach(i=>i.loading='eager');return a.length===2&&a.every(i=>i.naturalWidth>0)}")
        self.assertEqual((target/'report.md').read_bytes(),md.encode('utf8'))
        assets=list((target/'assets').glob('*.png'));self.assertEqual(len(assets),1)
        self.assertEqual(assets[0].read_bytes(),self.png.read_bytes())
        receipt=json.loads((target/'word-import.json').read_text('utf8'))
        self.assertEqual(receipt['source_sha256'],hashlib.sha256(self.original).hexdigest())
        self.assertEqual(receipt['status'],'COMPLETE');self.assertEqual(receipt['recognition']['model_calls'],0)
        self.assertEqual(self.input.read_bytes(),self.original)
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
        studio.audit_export(html);self.assertIn('report-source',html)
        self.page.reload();self.page.evaluate('()=>ReportStudioProgrammatic.ready()')
        self.page.locator('#recent-list button').filter(has_text='导入报告').first.click()
        self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('12.34 nm')")
        self.assertEqual(value(self.page),md);self.assertFalse(self.server.word_import.jobs)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'imported.png'))

    def test_cancel_review_keeps_current_source_and_draft(self):
        source(self.page,'# 当前未保存稿\n\n保留😀\n');before=value(self.page)
        self.read_word();self.page.locator('#modal-cancel').click()
        self.page.wait_for_function("!document.querySelector('#app').inert")
        self.assertEqual(value(self.page),before);self.assertEqual(self.input.read_bytes(),self.original)
        self.assertFalse(self.server.word_import.jobs)

    def test_figure_tables_keep_subcaptions_and_do_not_take_the_next_table_title(self):
        """WORD-IMPORT-GROUPS-01: layout tables, literal tables and local failure."""
        doc=Document();doc.add_paragraph('布局表导入',style='Title')
        wrapped=doc.add_paragraph()
        for _ in range(5):wrapped.add_run().add_picture(str(self.png))
        second=self.folder/'second.png';Image.new('RGB',(40,30),'gold').save(second)
        layout=doc.add_table(rows=2,cols=2);wide=layout.cell(0,0).merge(layout.cell(0,1))
        paragraph=wide.paragraphs[0];paragraph.add_run().add_picture(str(self.png));paragraph.add_run('\t');paragraph.add_run().add_picture(str(second))
        layout.cell(1,0).text='（a）信号 12.34';layout.cell(1,1).text='（b）背景 56.78'
        native_bookmark(doc.add_paragraph('图2 光路  对照'),'layout-photo',17)
        doc.add_paragraph('表3.2.1 实测参数')
        data=doc.add_table(rows=1,cols=2);data.cell(0,0).text='实测 1.25 nm';data.cell(0,1).paragraphs[0].add_run().add_picture(str(second))
        doc.add_paragraph('独立段落。')
        untitled=doc.add_table(rows=2,cols=1);p=untitled.cell(0,0).paragraphs[0]
        p.add_run().add_picture(str(second));p.add_run().add_picture(str(self.png))
        untitled.cell(1,0).text='整行共用说明 7.81'
        doc.add_paragraph('另一段正文。')
        not_a_row=doc.add_paragraph();not_a_row.add_run().add_picture(str(second));not_a_row.add_run().add_break();not_a_row.add_run().add_picture(str(self.png))
        unrepresentable=doc.add_table(rows=1,cols=5)
        for cell in unrepresentable.rows[0].cells:cell.paragraphs[0].add_run().add_picture(str(self.png))
        native_bookmark(doc.add_paragraph('图4 五幅原图'),'five-photos',18)
        p=doc.add_paragraph('对照 ');native_link(p,'组图',anchor='layout-photo');native_link(p,'五幅图',anchor='five-photos')
        doc.save(self.input);self.original=self.input.read_bytes();self.read_word();self.save_import('布局表和数据表')
        target=self.destination/'布局表和数据表';model=studio.analyze_report_contract(value(self.page),assets=target/'assets')
        self.assertTrue(model['ok'],model['diagnostics'])
        groups=[b['data'] for b in model['blocks'] if b['type']=='image-group']
        self.assertEqual([(g['caption'],g['rows'],g['columns']) for g in groups],[('',2,4),('光路  对照',1,2),('',1,2)])
        self.assertEqual(len(groups[0]['images']),5)
        self.assertEqual([i['caption'] for i in groups[1]['images']],['（a）信号 12.34','（b）背景 56.78'])
        self.assertEqual([(target/i['src']).read_bytes() for i in groups[1]['images']],[self.png.read_bytes(),second.read_bytes()])
        self.assertEqual([(target/i['src']).read_bytes() for i in groups[2]['images']],[second.read_bytes(),self.png.read_bytes()])
        self.assertEqual([i['caption'] for i in groups[2]['images']],['',''])
        self.assertIn('\n整行共用说明 7.81\n',value(self.page))
        self.assertEqual([b['data']['caption'] for b in model['blocks'] if b['type']=='table'],['实测参数'])
        self.assertEqual(len([b for b in model['blocks'] if b['type']=='figure']),8)
        self.assertIn('[组图](<#object-'+groups[1]['id']+'>)',value(self.page))
        fallback=next(b['id'] for b in model['blocks'] if b['type']=='figure' and '[五幅图](<#object-'+b['id']+'>)' in value(self.page))
        self.assertIn('五幅原图',value(self.page));self.assertNotEqual(fallback,groups[1]['id'])
        self.assertIn('实测 1.25 nm',value(self.page));self.assertIn('另一段正文。',value(self.page))
        self.assertEqual((target/'output/word-import-source.docx').read_bytes(),self.original)

    def test_changed_original_is_rejected_before_project_commit(self):
        before=value(self.page);self.read_word()
        self.input.write_bytes(self.original+b'changed')
        self.save_import('来源已变不可导入')
        self.assertIn('已变化',self.page.locator('#toast').inner_text())
        self.assertEqual(value(self.page),before);self.assertFalse((self.destination/'来源已变不可导入').exists())
        self.assertFalse(self.server.word_import.jobs)

    def test_nested_table_imports_without_reading_source_in_the_host(self):
        """WORD-IMPORT-OPEN-01: nested content is editable; all Word I/O uses the worker Python."""
        doc=Document();doc.add_paragraph('嵌套表试验',style='Title');cell=doc.add_table(rows=1,cols=1).cell(0,0)
        cell.text='外层 12.34';cell.add_table(rows=1,cols=1).cell(0,0).text='内层 98.76';doc.save(self.input)
        self.original=self.input.read_bytes();before=value(self.page)
        original_read=Path.read_bytes
        def host_read(path):
            if path.suffix.lower()=='.docx':raise AssertionError('Host must not read Word bytes')
            return original_read(path)
        with patch('word_import.selected_source',side_effect=AssertionError('Host must not read the Word')),patch.object(Path,'read_bytes',host_read):
            self.read_word();self.assertEqual(value(self.page),before)
            job=next(iter(self.server.word_import.jobs.values()));folder=Path(job['temporary'].name)
            self.assertFalse(folder.resolve().is_relative_to(Path(self.server.workspace).resolve()))
            self.assertEqual(Path(json.loads(job['request'].read_text('utf8'))['frozen']).name,'input.docx')
            self.assertIn('待确认',self.page.locator('#word-import-summary').inner_text())
            self.save_import('嵌套表正常导入')
        target=self.destination/'嵌套表正常导入';md=value(self.page)
        self.assertIn('外层 12.34',md);self.assertIn('内层 98.76',md)
        model=studio.analyze_report_contract(md,assets=target/'assets')
        self.assertEqual(len([b for b in model['blocks'] if b['type']=='table']),2)
        self.assertEqual((target/'output/word-import-source.docx').read_bytes(),self.original)
        self.assertFalse(self.server.word_import.jobs)

    @unittest.skipUnless(os.name=='nt','Windows file sharing semantics')
    def test_temporary_file_lock_shows_saved_project_and_deferred_cleanup(self):
        """WORD-IMPORT-ACCESS-01: actual UI must not show failure after successful save."""
        from test_word_export import held_word_file
        self.read_word();job=next(iter(self.server.word_import.jobs.values()));folder=Path(job['temporary'].name)
        with held_word_file(Path(json.loads(job['request'].read_text('utf8'))['frozen'])):
            self.save_import('临时占用仍保存成功')
            self.assertIn('Word 已导入',self.page.locator('#toast').inner_text())
            self.assertIn('延后清理',self.page.locator('#toast').inner_text());self.assertTrue(folder.exists())
        self.server.word_import.close();self.assertFalse(folder.exists())
        target=self.destination/'临时占用仍保存成功'
        self.assertEqual((target/'output/word-import-source.docx').read_bytes(),self.original)
        self.assertIn('12.34 nm',value(self.page));self.assertEqual(self.input.read_bytes(),self.original)

    def test_lists_controls_and_cached_fields_import_from_actual_dialog(self):
        """Ordinary Word is no longer refused for field/control/list content."""
        doc=Document();p=doc.add_paragraph('控件内文字 12.34 nm。');body=p._p.getparent();body.remove(p._p)
        wrapper=OxmlElement('w:sdt');content=OxmlElement('w:sdtContent');content.append(p._p);wrapper.append(content);body.insert(0,wrapper)
        # WORD-IMPORT-NAMESPACE-01: body markers and extension elements are
        # plain lxml nodes. They do not inherit python-docx's XPath prefix map.
        move=OxmlElement('w:moveFromRangeStart');move.set(qn('w:id'),'17');move.set(qn('w:name'),'move-17');wrapper.addprevious(move)
        end=OxmlElement('w:moveFromRangeEnd');end.set(qn('w:id'),'17');wrapper.addnext(end)
        start=OxmlElement('w:bookmarkStart');start.set(qn('w:id'),'19');start.set(qn('w:name'),'body-bookmark');move.addprevious(start)
        bookmark_end=OxmlElement('w:bookmarkEnd');bookmark_end.set(qn('w:id'),'19');end.addnext(bookmark_end)
        extension=OxmlElement('w:contentPart');body[-1].addprevious(extension)
        display=OxmlElement('m:oMathPara');math=OxmlElement('m:oMath');run=OxmlElement('m:r');text=OxmlElement('m:t');text.text='q=7'
        run.append(text);math.append(run);display.append(math);body[-1].addprevious(display)
        doc.add_paragraph('自动列表第一项',style='List Number');doc.add_paragraph('自动列表第二项',style='List Number')
        p=doc.add_paragraph('日期：');field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),' DATE ')
        r=OxmlElement('w:r');t=OxmlElement('w:t');t.text='2026-10-29';r.append(t);field.append(r);p._p.append(field)
        # WORD-IMPORT-MATH-01: cross a batch boundary, with an empty formula
        # before it, to check per-formula matching in a genuinely editable import.
        for index in range(66):
            p=doc.add_paragraph('第 '+str(index)+' 条公式 ');math=OxmlElement('m:oMath')
            if index!=62:
                r=OxmlElement('m:r');t=OxmlElement('m:t');t.text='x='+str(index);r.append(t);math.append(r)
            p._p.append(math);p.add_run('，保留相邻文字。')
        doc.save(self.input)
        self.original=self.input.read_bytes();self.read_word();self.save_import('普通Word兼容导入')
        md=value(self.page)
        for text in ('控件内文字 12.34 nm。','1. 自动列表第一项','2. 自动列表第二项','2026-10-29','$$\nq = 7\n$$','contentPart'):self.assertIn(text,md)
        self.assertNotIn('moveFromRange',md)
        self.assertNotIn('bookmarkEnd',md)
        for index in range(66):
            expected='【公式待确认，见源 Word】' if index==62 else '$x = '+str(index)+'$'
            self.assertIn('第 '+str(index)+' 条公式 '+expected+'，保留相邻文字。',md)
        self.assertEqual(self.page.locator('#render-profile').input_value(),'free')
        target=self.destination/'普通Word兼容导入';receipt=json.loads((target/'word-import.json').read_text('utf8'))
        self.assertEqual(receipt['status'],'NEEDS_REVIEW');self.assertEqual(self.input.read_bytes(),self.original)
        self.assertEqual((target/'output/word-import-source.docx').read_bytes(),self.original)

    def test_needs_review_keeps_unconfirmed_prose_and_lists_it(self):
        text='这是被误用标题样式的一段完整正文，需要保留全部文字而不能强制认作章节。'*6
        doc=Document();doc.add_paragraph('待确认样本',style='Title');doc.add_heading(text,level=1);doc.save(self.input)
        self.original=self.input.read_bytes();self.read_word()
        self.assertIn('待确认',self.page.locator('#word-import-summary').inner_text())
        self.assertIn(text,self.page.locator('#word-import-diagnostics').inner_text())
        self.save_import('Word待确认项')
        md=value(self.page);self.assertIn(text,md);self.assertNotIn('## '+text,md)
        receipt=json.loads((self.destination/'Word待确认项/word-import.json').read_text('utf8'))
        self.assertEqual(receipt['status'],'NEEDS_REVIEW');self.assertEqual(receipt['recognition']['unresolved'],1)
        self.assertIn('待确认',self.page.locator('#toast').inner_text())

    def test_missing_formula_tool_and_runtime_leave_original_unchanged(self):
        before=value(self.page)
        with patch.object(self.server.word_export,'pandoc',return_value=None):
            self.read_word()
            self.assertIn('待确认',self.page.locator('#word-import-summary').inner_text())
            self.assertIn('原公式保留在源 Word',self.page.locator('#word-import-diagnostics').inner_text())
            self.page.locator('#modal-cancel').click()
        self.assertEqual(value(self.page),before)
        with patch.object(self.server.word_export,'runtime',return_value=None):
            self.page.locator('#menu-open>summary').click();self.page.locator('#btn-import-word').click();self.page.locator('#modal-ok').click()
            self.assertTrue(self.page.locator('#modal-layer').is_visible())
            self.assertIn('请先选择',self.page.locator('#word-import-runtime-state').inner_text())
            self.page.locator('#modal-cancel').click()
        self.assertFalse(self.server.word_import.jobs);self.assertEqual(self.input.read_bytes(),self.original)

    def test_cancel_waiting_serializer_stops_owned_process_and_releases_component(self):
        before=value(self.page)
        result=self.page.evaluate("""async()=>{const r=await fetch('/api/import/word/start',{method:'POST',headers:{'Content-Type':'application/json','X-HRS-Project-Action':'user-action'},body:'{}'});return r.json()}""")
        self.assertTrue(result['ok'],result);token=result['job_token']
        pending=self.page.evaluate("""async token=>{for(let i=0;i<100;i++){const r=await fetch('/api/import/word/step',{method:'POST',headers:{'Content-Type':'application/json','X-HRS-Project-Action':'user-action'},body:JSON.stringify({job_token:token})});const v=await r.json();if(v.state==='page'||v.state==='error')return v;await new Promise(r=>setTimeout(r,50));}throw Error('No serializer request')}""",token)
        self.assertEqual(pending['state'],'page',pending)
        job=self.server.word_import.jobs[token];process=job['process'];folder=Path(job['temporary'].name)
        stale=self.page.evaluate("""async token=>{const r=await fetch('/api/import/word/step',{method:'POST',headers:{'Content-Type':'application/json','X-HRS-Project-Action':'user-action'},body:JSON.stringify({job_token:token,seq:99999,result:[]})});return {status:r.status,...await r.json()}}""",token)
        self.assertEqual(stale['status'],400);self.assertIsNone(process.poll())
        cancelled=self.page.evaluate("""async token=>{const r=await fetch('/api/import/word/cancel',{method:'POST',headers:{'Content-Type':'application/json','X-HRS-Project-Action':'user-action'},body:JSON.stringify({job_token:token})});return r.json()}""",token)
        self.assertTrue(cancelled['ok'],cancelled);self.assertIsNotNone(process.poll())
        self.assertFalse(folder.exists());self.assertFalse(self.server.word_export.running.locked())
        self.assertEqual(value(self.page),before);self.assertFalse(self.server.word_import.jobs)

    def test_registry_write_failure_keeps_verified_new_project_and_current_source(self):
        before=value(self.page);self.read_word()
        with patch.object(self.server.registry,'register',side_effect=OSError('test index lock')):
            self.save_import('登记失败保留工程')
        target=self.destination/'登记失败保留工程'
        self.assertIn('工程已完整保存',self.page.locator('#toast').inner_text())
        self.assertEqual(value(self.page),before);self.assertTrue((target/'assets').is_dir())
        self.assertIn('12.34', (target/'report.md').read_text('utf8'))
        self.assertFalse(self.server.word_import.jobs)
        with patch.object(studio,'pick_project_parent',return_value=target):
            self.page.locator('#menu-open>summary').click();self.page.locator('#btn-project-open').click()
            self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('12.34')")
        self.assertEqual(self.input.read_bytes(),self.original)

    def test_cancel_switch_after_success_preserves_dirty_current_draft(self):
        text='# 当前未保存稿\n\n请保留源稿和草稿😀。\n';source(self.page,text)
        self.read_word();self.choose_destination('导入成功但暂不切换')
        self.page.wait_for_function("document.querySelector('#modal-title').textContent==='有未保存的修改'")
        self.page.locator('#modal-cancel').click()
        self.page.wait_for_function("document.querySelector('#toast').textContent.includes('当前文稿保持')")
        self.assertEqual(value(self.page),text);self.assertEqual((self.project/'report.md').read_bytes(),b'# Initial\n')
        self.assertTrue((self.destination/'导入成功但暂不切换/report.md').is_file())
        self.assertFalse(self.server.word_import.jobs)

    def test_own_export_uses_companion_mapping_for_exact_unchanged_source(self):
        from test_word_export_browser import WordUI
        self.docid='f'*32;self.server.registry.register(self.docid,self.project)
        self.page.evaluate('id=>ReportStudioProgrammatic.open(id)',self.docid)
        source(self.page,'# 自身导出回编\n\n## 目的\n\n**强调** 与 $x^2$，中文😀。\n\n| 参数 | 数值 |\n| --- | --- |\n| 长度 | 12.34 |\n')
        self.page.locator('#btn-save').click();self.page.wait_for_function("document.querySelector('#save-indicator').textContent.trim()==='已保存'")
        expected=value(self.page);WordUI.open_word(self);output=WordUI.compile(self)
        raw=output.read_bytes();companion=Path(str(output)+'.hrs-bridge.json');mapping=companion.read_bytes()
        with patch.object(studio,'pick_import_file',return_value=output):
            self.read_word();self.save_import('自身Word恢复')
        restored=self.destination/'自身Word恢复';self.assertEqual((restored/'report.md').read_bytes(),expected.encode('utf8'))
        receipt=json.loads((restored/'word-import.json').read_text('utf8'))
        self.assertEqual(receipt['mode'],'provenance-aware');self.assertEqual(output.read_bytes(),raw)
        self.assertEqual(companion.read_bytes(),mapping);self.assertFalse(self.server.word_import.jobs)

    def test_legacy_and_native_equations_roundtrip_with_and_without_companion(self):
        """WORD-MATH-ROUNDTRIP-01: actual import/export commands in both directions."""
        from test_word_export_browser import WordUI
        doc=Document();doc.add_paragraph('公式双向核对',style='Title');doc.add_heading('正文',level=1)
        para=doc.add_paragraph('行内 ',style='List Bullet')
        def embed(p, number, progid, payload):
            part=Part(PackURI(f'/word/embeddings/oleObject{number}.bin'),
                      'application/vnd.openxmlformats-officedocument.oleObject',payload,p.part.package)
            obj=OxmlElement('w:object')
            ole=obj.makeelement('{urn:schemas-microsoft-com:office:office}OLEObject',
                               {'ProgID':progid,'Type':'Embed',qn('r:id'):p.part.relate_to(part,RT.OLE_OBJECT)})
            obj.append(ole);p.add_run()._r.append(obj)
        old=bytes.fromhex('1c000000020097c42200000000000000e00c990054ac980000000000030101031e0a010281790002863d00030e0000010288310000010288320000000000')
        embed(para,1,'Equation.3',compound_math(old));para.add_run('，后续文字保留。')
        def start_field(p,code):
            marker(p,'begin')
            instruction=OxmlElement('w:instrText');instruction.text=code;p.add_run()._r.append(instruction)
            marker(p,'separate')

        def marker(p,kind):
            node=OxmlElement('w:fldChar');node.set(qn('w:fldCharType'),kind);p.add_run()._r.append(node)

        p=doc.add_paragraph('参见')
        start_field(p,' GOTOBUTTON ZEqnNum42 ')
        start_field(p,' REF ZEqnNum42 \\* Charformat \\! \\* MERGEFORMAT ')
        p.add_run('(7)');marker(p,'end');marker(p,'end');p.add_run('。')
        p=doc.add_paragraph();embed(p,2,'Equation.DSMT4',native_math_fixture())
        tab=p.add_run('\t')
        start_field(p,' MACROBUTTON MTPlaceRef \\* MERGEFORMAT ')
        start_field(p,' SEQ MTEqn \\h \\* MERGEFORMAT ');marker(p,'end')
        p.add_run('(')
        start_field(p,' SEQ MTEqn \\c \\* Arabic ');p.add_run('7');marker(p,'end')
        p.add_run(')');marker(p,'end')
        native_bookmark(p,'ZEqnNum42',120);tab._r.addnext(p._p.find(qn('w:bookmarkStart')))
        table=doc.add_table(rows=1,cols=2);table.cell(0,0).text='单元格'
        p=table.cell(0,1).paragraphs[0];embed(p,3,'Equation.DSMT4',native_math_fixture(inline=True))
        p=doc.add_paragraph('坏式后仍继续导入。');embed(p,4,'Equation.DSMT4',compound_math(b'incomplete'))
        p=doc.add_paragraph('最后一句。')
        footnote=OxmlElement('w:footnoteReference');footnote.set(qn('w:id'),'1');p.add_run()._r.append(footnote)
        notes=OxmlElement('w:footnotes');note=OxmlElement('w:footnote');note.set(qn('w:id'),'1');notes.append(note)
        xml_paragraph=OxmlElement('w:p');note.append(xml_paragraph)
        note_part=Part(PackURI('/word/footnotes.xml'),
                       'application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml',b'',doc.part.package)
        doc.part.relate_to(note_part,RT.FOOTNOTES)
        np=Paragraph(xml_paragraph,SimpleNamespace(part=note_part));np.add_run('注内 ')
        embed(np,5,'Equation.DSMT4',native_math_fixture(inline=True))
        note_part._blob=E.tostring(notes,encoding='UTF-8')
        doc.save(self.input);self.original=self.input.read_bytes()

        self.read_word();self.save_import('旧公式')
        project=self.destination/'旧公式';expected=value(self.page)
        model=studio.analyze_report_contract(expected,assets=project/'assets')
        equations=[b for b in model['blocks'] if b['type']=='equation']
        self.assertEqual(len(equations),1,expected)
        self.assertEqual(equations[0]['latex'].strip(),r'\frac{x_{i}^{2}}{y}')
        self.assertIn(r'$\mathrm{y}=\frac{1}{2}$',expected)
        self.assertEqual(next(b for b in model['blocks'] if b['type']=='table')['data']['rows'][0][1]['text'],r'$\frac{x_{i}^{2}}{y}$')
        self.assertIn('参见 @eq:'+equations[0]['id']+'。',expected)
        self.assertIn('最后一句。[^word-note-1]',expected)
        self.assertIn(r'[^word-note-1]: 注内 $\frac{x_{i}^{2}}{y}$',expected)
        self.assertIn('WORD_MATH_RETAINED_IN_SOURCE',[d['code'] for d in json.loads((project/'word-import.json').read_text('utf8'))['diagnostics']])
        self.assertTrue(self.page.locator('#show-equation-numbers').is_checked())
        self.assertEqual((project/'output/word-import-source.docx').read_bytes(),self.original)
        self.project=project

        for numbered in (True,False):
            with self.subTest(numbered=numbered):
                self.page.locator('#show-equation-numbers').set_checked(numbered)
                self.page.wait_for_function('!document.querySelector("#show-equation-numbers").disabled')
                WordUI.open_word(self)
                self.assertEqual(self.page.locator('#show-equation-numbers').is_checked(),numbered)
                output=WordUI.compile(self)
                word=Document(output)
                self.assertEqual(len(word._element.xpath('//m:oMathPara')),1)
                self.assertEqual(len(word._element.xpath('//m:oMath')),3)
                note_xml=next(part.blob for part in word.part.package.parts if str(part.partname)=='/word/footnotes.xml')
                self.assertEqual(len(list(E.fromstring(note_xml).iter(qn('m:oMath')))),1)
                self.assertEqual(len(word._element.xpath('//w:object')),0)
                codes=word._element.xpath('//w:fldSimple/@w:instr')
                self.assertEqual(any('SEQ 公式' in c for c in codes),numbered)
                if numbered:
                    edited=next(t for t in word._element.xpath('//m:oMathPara//m:t') if t.text=='y')
                    edited.text='z';edited_path=self.folder/'现有Word编辑.docx'
                    word.save(edited_path)
                    Path(str(edited_path)+'.hrs-bridge.json').write_bytes(Path(str(output)+'.hrs-bridge.json').read_bytes())
                name='带映射回编'+str(numbered)
                with patch.object(studio,'pick_import_file',return_value=output):
                    self.read_word();self.save_import(name)
                self.assertEqual((self.destination/name/'report.md').read_text('utf8'),expected)
                self.assertEqual(value(self.page),expected)
                name='仅Word回编'+str(numbered);bare=self.folder/(name+'.docx')
                bare_doc=Document(output)
                if not numbered:
                    # WPS Save As may place the target bookmark inside the
                    # native equation rather than around m:oMathPara.
                    native=bare_doc._element.xpath('//m:oMathPara/m:oMath')[0]
                    outer=native.getparent().getparent()
                    start=next(n for n in outer if n.tag==qn('w:bookmarkStart') and n.get(qn('w:name'),'').startswith('HN_'))
                    native.insert(0,start)
                bare_doc.save(bare)
                with patch.object(studio,'pick_import_file',return_value=bare):
                    self.read_word();self.save_import(name)
                new=self.destination/name
                self.assertTrue((new/'report.md').is_file(),self.page.locator('#toast').inner_text())
                ir=studio.analyze_report_contract((new/'report.md').read_text('utf8'),assets=new/'assets')
                self.assertEqual([r['kind'] for r in ir['references']],['eq'])
                self.assertEqual([b['id'] for b in ir['blocks'] if b['type']=='equation'],[ir['references'][0]['target']])
                self.assertEqual(json.loads((new/'meta.json').read_text('utf8'))['render_options']['show_equation_numbers'],numbered)
                self.assertIn('注内 $', (new/'report.md').read_text('utf8'))
                if numbered:
                    with patch.object(studio,'pick_import_file',return_value=edited_path):
                        self.read_word();self.save_import('Word实际编辑回编')
                    edited_project=self.destination/'Word实际编辑回编'
                    edited_source=(edited_project/'report.md').read_text('utf8')
                    self.assertIn('}{z}',edited_source)
                    receipt=json.loads((edited_project/'word-import.json').read_text('utf8'))
                    self.assertEqual(receipt['mode'],'provenance-aware')
                    self.assertIn('@eq:'+equations[0]['id'],edited_source)
                # Keep exporting the same original project and options independently.
                entry=next(k for k,v in self.server.registry.mapping.items() if Path(v)==project)
                self.page.evaluate('id=>ReportStudioProgrammatic.open(id)',entry)
        self.assertEqual(self.input.read_bytes(),self.original)

    def test_hyperlinks_beta_preview_html_and_native_word_keep_real_destinations(self):
        """WORD-HYPERLINK-01: labels/OMML/runs and forward targets survive the actual UI."""
        doc=Document();doc.add_paragraph('链接完整链',style='Title')
        p=doc.add_paragraph('参考');native_link(p,['外部','资料'],'https://example.org/data?x=1&y=2',bold=True);p.add_run('，请');native_link(p,'跳至目的',anchor='_Purpose');p.add_run('或');native_link(p,'跳至结果',anchor='_Results');p.add_run('。')
        p=doc.add_heading('目的',level=1);native_bookmark(p,'_Purpose',50)
        p=doc.add_paragraph();native_link(p,'表1 参数表','https://example.org/table')
        table=doc.add_table(rows=1,cols=1);node=native_link(table.cell(0,0).paragraphs[0],'公式 ','https://example.org/math')
        math=OxmlElement('m:oMath');run=OxmlElement('m:r');text=OxmlElement('m:t');text.text='x';run.append(text);math.append(run);node.append(math)
        p=doc.add_heading('结果',level=1);native_bookmark(p,'_Results',51);doc.add_paragraph('结果正文保持。')
        doc.save(self.input);self.original=self.input.read_bytes()
        for theme in ('blue','warm','navy'):
            self.page.locator('#color-theme').select_option(theme)
            self.page.wait_for_function('t=>document.documentElement.dataset.colorTheme===t',arg=theme)
            self.page.locator('#menu-open>summary').click()
            badge=self.page.locator('#btn-import-word .beta-badge');self.assertEqual(badge.inner_text(),'beta')
            self.assertEqual(badge.evaluate('e=>getComputedStyle(e).color'),self.page.locator('#btn-export-word .beta-badge').evaluate('e=>getComputedStyle(e).color'))
            metric=badge.evaluate('e=>{const r=e.getBoundingClientRect(),b=e.parentElement.getBoundingClientRect();return {right:r.right,top:r.top,parentTop:b.top,width:innerWidth}}')
            self.assertLess(metric['top'],metric['parentTop']+8);self.assertLessEqual(metric['right'],metric['width'])
            self.page.locator('#menu-open>summary').click()
        self.read_word();self.save_import('链接完整链')
        project=self.destination/'链接完整链';md=value(self.page)
        model=studio.analyze_report_contract(md,assets=project/'assets')
        ids={b['text']:b['id'] for b in model['blocks'] if b['type']=='heading' and b.get('id')}
        href='#object-'+ids['目的'];target=self.page.locator('#object-'+ids['目的'])
        self.assertEqual(target.count(),1);self.page.locator('#preview-content a').filter(has_text='跳至目的').click()
        self.page.wait_for_function('href=>location.hash===href',arg=href)
        self.assertEqual(self.page.locator('#preview-content a').filter(has_text='外部资料').get_attribute('href'),'https://example.org/data?x=1&y=2')
        self.assertEqual(self.page.locator('#preview-content a').filter(has_text='外部资料').locator('strong').inner_text(),'外部资料')
        self.assertIn('[公式 $x$](<https://example.org/math>)',md)
        html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})");studio.audit_export(html)
        offline=self.folder/'links.html';offline.write_text(html,encoding='utf8')
        reader=self.page.context.new_page()
        try:
            reader.goto(offline.as_uri());reader.locator('a').filter(has_text='跳至结果').first.click()
            reader.wait_for_function('id=>location.hash==="#object-"+id',arg=ids['结果'])
        finally:reader.close()
        from test_word_export_browser import WordUI
        old_project=self.project;self.project=project
        try:WordUI.open_word(self);output=WordUI.compile(self)
        finally:self.project=old_project
        word=Document(output);links=word._element.xpath('//w:hyperlink');names=set(word._element.xpath('//w:bookmarkStart/@w:name'))
        internal={''.join(n.xpath('.//w:t/text()')):n.get(qn('w:anchor')) for n in links if n.get(qn('w:anchor'))}
        self.assertIn(internal['跳至目的'],names);self.assertIn(internal['跳至结果'],names)
        destinations={word.part.rels[n.get(qn('r:id'))].target_ref for n in links if n.get(qn('r:id'))}
        self.assertIn('https://example.org/data?x=1&y=2',destinations)
        self.assertEqual(len(word._element.xpath('//w:hyperlink//m:oMath')),1)
        # Changing only the target must be read from Word, never restored from
        # the old Markdown snapshot just because the visible text is unchanged.
        next(n for n in links if ''.join(n.xpath('.//w:t/text()'))=='跳至目的').set(qn('w:anchor'),internal['跳至结果'])
        word.save(output)
        with patch.object(studio,'pick_import_file',return_value=output):
            self.read_word();self.save_import('修改链接目标后回编')
        self.assertIn('[跳至目的](<#object-'+ids['结果']+'>)',value(self.page))
        self.assertEqual(self.input.read_bytes(),self.original)
        if self.evidence:self.page.screenshot(path=str(self.evidence/'links.png'))

    def test_unknown_and_unsafe_link_targets_are_shown_and_saved_for_review(self):
        doc=Document();doc.add_paragraph('待确认链接',style='Title');p=doc.add_paragraph('参见')
        native_link(p,'未知内部目标',anchor='_Unknown');p.add_run('、');native_link(p,'危险目标','javascript:alert(1)');p.add_run('、');native_link(p,'相对原目标','../docs/paper.pdf');p.add_run('。')
        doc.save(self.input);self.original=self.input.read_bytes();self.read_word()
        details=self.page.locator('#word-import-diagnostics').inner_text()
        for text in ('#_Unknown','javascript:alert(1)','../docs/paper.pdf'):self.assertIn(text,details)
        self.save_import('待确认链接');md=value(self.page)
        self.assertIn('未知内部目标、危险目标、相对原目标。',md);self.assertNotIn('](',md)
        receipt=json.loads((self.destination/'待确认链接/word-import.json').read_text('utf8'))
        self.assertEqual(receipt['status'],'NEEDS_REVIEW');self.assertEqual(receipt['recognition']['unresolved'],3)
        self.assertEqual(self.input.read_bytes(),self.original)

    def test_bidirectional_roundtrip_captions_xrefs_notes_code_and_headings(self):
        """WORD-ROUNDTRIP-FIDELITY-01: bare DOCX <-> HRS MD preserves numeric captions, xrefs, notes, code and chapter headings."""
        from test_word_export_browser import WordUI
        doc=Document();doc.add_paragraph('双向互转综合核对',style='Title')
        doc.add_heading('阅读说明',level=1)
        for level,label in ((1,'0. 符号说明'),(2,'0.1 基准参数'),(1,'1. 光栅基础'),(2,'1.1 Littrow 条件'),(1,'2. FW 双模形式')):
            h=doc.add_heading('',level=level);r=h.add_run(label);r.bold=True
        for expr,bm,desc in (('a=1','eq_5','式5 局部周期与渐变率'),('b=2','eq_6','式6 中心周期失配')):
            mp=doc.add_paragraph()._p
            omath_para=OxmlElement('m:oMathPara');omath=OxmlElement('m:oMath');mr=OxmlElement('m:r');mt=OxmlElement('m:t');mt.text=expr
            mr.append(mt);omath.append(mr);omath_para.append(omath);mp.append(omath_para)
            dp=doc.add_paragraph(desc);native_bookmark(dp,bm,200+len(bm)+int(bm[-1]))
        ref_p=doc.add_paragraph('公式内跳见 ');native_link(ref_p,'式5',anchor='eq_5');ref_p.add_run(' 与 ');native_link(ref_p,'式6',anchor='eq_6');ref_p.add_run('。')
        doc.save(self.input);self.original=self.input.read_bytes()

        self.read_word();self.save_import('外部公式书签与标题')
        ext_proj=self.destination/'外部公式书签与标题';ext_md=value(self.page)
        self.assertIn('## 0. 符号说明\n',ext_md);self.assertIn('### 1.1 Littrow 条件\n',ext_md);self.assertIn('## 2. FW 双模形式\n',ext_md)
        self.assertNotIn('## **',ext_md)
        ext_ir=studio.analyze_report_contract(ext_md,assets=ext_proj/'assets')
        eq_ids=[b['id'] for b in ext_ir['blocks'] if b['type']=='equation']
        self.assertEqual(len(eq_ids),2)
        self.assertIn('[式5](<#object-'+eq_ids[0]+'>)',ext_md)
        self.assertIn('[式6](<#object-'+eq_ids[1]+'>)',ext_md)
        ext_receipt=json.loads((ext_proj/'word-import.json').read_text('utf8'))
        self.assertNotIn('WORD_HYPERLINK_UNRESOLVED',[d['code'] for d in ext_receipt['diagnostics']])

        # Round-trip rich HRS Markdown -> Word -> bare Word import (without companion sidecar)
        self.docid='e'*32;self.server.registry.register(self.docid,self.project)
        self.page.evaluate('id=>ReportStudioProgrammatic.open(id)',self.docid)
        asset_img=self.project/'assets/probe.png';asset_img.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(48,24),'teal').save(asset_img)
        rich_md=(
            '# 工程双向探针\n\n'
            '## 阅读说明\n\n用途与背景。\n\n'
            '## 1. 工况说明\n\n转台工况。\n\n'
            '## 2 rpm 稳态转速\n\n观察每分钟转速。\n\n'
            '## 系统参数 {#sec-sys}\n\n'
            '参见 @fig:fig-slit、@tbl:tbl-cal、@eq:eq-main 与 @sec:sec-algo。'
            '首次引用[^n1]，再次引用[^n1]，含 **粗体 `code` 混排**。\n\n'
            '---\n\n'
            '```report-figure\n'
            '{"schema":"report-figure-v1","id":"fig-slit","kind":"image","src":"assets/probe.png","caption":"0.25 mm 狭缝图像","alt":"slit"}\n'
            '```\n\n'
            '| 端口 | 标识 |\n| --- | --- |\n| 反射 | `s21` |\n: 248.33 nm 标定表 {#tbl-cal}\n\n'
            '<!-- hrs:eq id=eq-main -->\n$$\ny = x^2\n$$\n\n'
            '## 重建算法 {#sec-algo}\n\n'
            '回引 @sec:sec-sys：\n\n'
            '```python\ndef calc(x, pitch=0.512):\n    return x / pitch\n```\n\n'
            '[^n1]: 引用 `CITATION.cff` 说明。\n'
        )
        source(self.page,rich_md)
        self.page.locator('#btn-save').click();self.page.wait_for_function("document.querySelector('#save-indicator').textContent.trim()==='已保存'")
        WordUI.open_word(self)
        self.page.locator('#word-keep-emphasis').check()
        exported=WordUI.compile(self,numbered=True)
        native=Document(exported)
        self.assertIn('2 rpm 稳态转速',[p.text for p in native.paragraphs])
        self.assertIn('工况说明',[p.text for p in native.paragraphs])
        bare_copy=self.folder/'bare_roundtrip.docx'
        cap=next(p for p in native.paragraphs if '0.25 mm 狭缝图像' in p.text)
        cap.add_run('，方案 ')
        fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),' SEQ Scheme \\* ARABIC ')
        fld.append(cap.add_run('5')._r);cap._p.append(fld);cap.add_run(' 的布局')
        native.save(bare_copy)
        with patch.object(studio,'pick_import_file',return_value=bare_copy):
            self.read_word();self.save_import('无映射双向回编')
        re_proj=self.destination/'无映射双向回编';re_md=(re_proj/'report.md').read_text('utf8')
        re_receipt=json.loads((re_proj/'word-import.json').read_text('utf8'))
        self.assertEqual(re_receipt['status'],'COMPLETE',re_receipt)
        self.assertNotIn('WORD_FIELD_AS_TEXT',[d['code'] for d in re_receipt['diagnostics']])
        self.assertIn('"caption": "0.25 mm 狭缝图像，方案 5 的布局"',re_md)
        self.assertIn('"caption": "248.33 nm 标定表"',re_md)
        self.assertIn('"`s21`"',re_md)
        self.assertIn('**粗体 `code` 混排**',re_md)
        self.assertIn('首次引用[^word-note-1]，再次引用[^word-note-1]',re_md)
        self.assertIn('`CITATION.cff`',re_md)
        self.assertIn('\n---\n',re_md)
        self.assertIn('```\ndef calc(x, pitch=0.512):\n    return x / pitch\n```',re_md)
        self.assertNotIn('图 @fig:',re_md);self.assertNotIn('表 @tbl:',re_md)
        re_ir=studio.analyze_report_contract(re_md,assets=re_proj/'assets')
        self.assertEqual(sorted(r['kind'] for r in re_ir['references']),['eq','fig','sec','sec','tbl'])

        self.project=re_proj;WordUI.open_word(self)
        self.page.locator('#word-notes-mode').select_option('references')
        references=WordUI.compile(self,numbered=True)
        bare_refs=self.folder/'bare_references.docx';bare_refs.write_bytes(references.read_bytes())
        with patch.object(studio,'pick_import_file',return_value=bare_refs):
            self.read_word();self.save_import('无映射参考文献')
        refs_proj=self.destination/'无映射参考文献';refs_md=(refs_proj/'report.md').read_text('utf8')
        self.assertIn('首次引用[^word-ref-1]，再次引用[^word-ref-1]',refs_md)
        self.assertIn('[^word-ref-1]: 引用 `CITATION.cff` 说明。',refs_md)
        self.assertNotIn('## 参考文献',refs_md)
        self.project=refs_proj;WordUI.open_word(self)
        self.assertEqual(self.page.locator('#word-notes-mode').input_value(),'references')
        second=Document(WordUI.compile(self,numbered=True))
        fields=second._element.xpath('//w:fldSimple/@w:instr')
        self.assertEqual(sum(' SEQ HRSReference ' in x for x in fields),1)
        self.assertEqual(sum(' REF HR_' in x for x in fields),2)

    def test_r5_cover_roundtrip_math_units_captions_and_ack_notices(self):
        """WORD-R5-FIDELITY-01: cover template bare reimport, mathrm/units, rich captions, quote/TOC and Word notice ack."""
        from test_word_export_browser import WordUI
        # 1. Word notice snapshot lifecycle + persistent acknowledgment
        warn_text='被误用标题样式的完整长句，用于检验告警核对状态持久化。'*4
        doc=Document();doc.add_paragraph('告警生命周期样本',style='Title');doc.add_heading(warn_text,level=1);doc.save(self.input)
        self.original=self.input.read_bytes();self.read_word();self.save_import('Word告警核对')
        ack_proj=self.destination/'Word告警核对'
        self.page.wait_for_selector('#problems-panel:not([hidden])')
        self.page.wait_for_function("document.querySelector('#problem-list .problem-severity')?.textContent==='Word导入'")
        self.assertFalse(self.page.locator('#btn-ack-word-notices').is_hidden())
        edited=value(self.page)+'\n补充一行正文。\n'
        source(self.page,edited)
        self.page.wait_for_function("document.querySelector('#problem-list .problem-severity')?.textContent==='上次 Word 导入'")
        self.page.locator('#btn-ack-word-notices').click()
        self.page.wait_for_function("!document.querySelector('#problems-summary').textContent.includes('Word 告警')")
        self.assertTrue((ack_proj/'word-notices-ack.json').is_file())
        self.page.locator('#btn-save').click();self.page.wait_for_function("document.querySelector('#save-indicator').textContent.trim()==='已保存'")
        doc_id=self.page.evaluate('async()=>(await ReportStudioProgrammatic.topics()).documentId')
        self.page.evaluate('id=>ReportStudioProgrammatic.open(id)',doc_id)
        self.page.locator('#btn-validate').click()
        self.page.wait_for_function("document.querySelector('#problems-summary').textContent.startsWith('0 个错误')")
        self.assertNotIn('Word 告警',self.page.locator('#problems-summary').inner_text())

        # 2. Cover template + inline_math_mode=text + rich captions + blockquote + [[TOC]] + lead-in prose
        self.project=ack_proj
        Image.new('RGB',(16,16),'navy').save(ack_proj/'assets/probe.png')
        r5_md=(
            '# 封面与公式综合报告\n\n'
            '## 1.7 0 级与高阶衍射抑制 {#sec-zero}\n\n'
            '目录字面量 \\[TOC] 与 \\[[TOC]]。\n\n'
            '> 工程备注：环境温度 $20\\,^\\circ\\mathrm{C}$，转速 $300\\ \\mathrm{r/min}$，偏差 $\\pm 0.05\\ \\mathrm{pm}$。\n\n'
            '自由度 $N_{\\mathrm{dof}} = 12$，见 @fig:fig-r5：\n\n'
            '```report-figure\n'
            '{"schema":"report-figure-v1","id":"fig-r5","kind":"image","src":"assets/probe.png","caption":"H<sub>2</sub>O 与 `calib_v2` **峰值**","alt":"r5"}\n'
            '```\n\n'
            '固定入射场取\n\n'
            '<!-- hrs:eq id=eq-r5 -->\n$$\nE_0 = A\\exp(ikz)\n$$\n'
        )
        source(self.page,r5_md)
        self.page.locator('#render-profile').select_option('engineering')
        self.page.locator('#btn-save').click();self.page.wait_for_function("document.querySelector('#save-indicator').textContent.trim()==='已保存'")
        rt_info=self.server.word_export.runtime()
        cover_tpl=rt_info['wps']/'templates/cover_template_v0311.docx'
        with patch.object(studio,'pick_import_file',return_value=cover_tpl):
            WordUI.open_word(self)
            self.page.locator('#word-pick-template').click()
            self.page.wait_for_function("document.querySelector('#word-template').value.includes('cover_template')")
            self.page.locator('#word-keep-emphasis').check()
            self.page.locator('#word-inline-math-mode').select_option('text')
            exported=WordUI.compile(self,numbered=True)
        self.assertIn('行内单位或量值按正文输出',self.page.locator('#toast').inner_text())
        bare_cover=self.folder/'bare_cover_r5.docx';bare_cover.write_bytes(exported.read_bytes())
        with patch.object(studio,'pick_import_file',return_value=bare_cover):
            self.read_word();self.save_import('封面无映射回编')
        re_proj=self.destination/'封面无映射回编';re_md=(re_proj/'report.md').read_text('utf8')
        re_rec=json.loads((re_proj/'word-import.json').read_text('utf8'))
        self.assertEqual(re_rec['status'],'COMPLETE',re_rec)
        self.assertNotIn('在此输入报告标题',re_md)
        self.assertTrue(re_md.lstrip().startswith('# 封面与公式综合报告'))
        self.assertIn('0 级与高阶衍射抑制',re_md)
        self.assertIn('> 工程备注：环境温度',re_md)
        self.assertIn('<sub>2</sub>',re_md);self.assertIn('`calib_v2`',re_md);self.assertIn('**峰值**',re_md)
        self.assertIn('\\mathrm{dof}',re_md)


if __name__=='__main__':unittest.main()
