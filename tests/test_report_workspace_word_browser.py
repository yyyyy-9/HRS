"""R8 Word workflow integration; explicitly requires matching offline Word components."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from browser_support import LiveDocument,browser_session,source,value,artifact_directory


class NativeReportWord(unittest.TestCase):
    def setUp(self):
        for name in ['HRS_WORD_SUPPORT','HRS_WORD_PYTHON','HRS_WORD_PANDOC']:
            if not os.environ.get(name) or not Path(os.environ[name]).exists():
                raise RuntimeError('This explicit integration group requires '+name)

    def test_preview_edit_native_word_and_duplicate_note_refusal(self):
        figure={'schema':'report-figure-v1','id':'fig-path','kind':'mermaid','source':'flowchart TB\n A["Input<br/>$$\\boldsymbol{k}$$"] --> B[Output]','caption':'Optical path'}
        text='# Ledger\n\nNotes\n\n# Independent report\n\n## Method\n\nSee @fig:fig-path and @tbl:data.\n\n'+r'$\boldsymbol{k}=2\pi/\lambda$'+'\n\n```report-figure\n'+json.dumps(figure)+'\n```\n\n| Parameter | Value |\n| --- | --- |\n| n | 1 |\n: Parameter table[^note] {#tbl-data}\n\n[^note]: Native note.\n\n# Other\n\nOther text\n'
        # Existing object ID convention uses tbl-… in both declaration and reference.
        text=text.replace('@tbl:data','@tbl:tbl-data')
        evidence=artifact_directory(__file__)
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,registered=True) as d:
            p=d.page;p.set_default_timeout(45000)
            p.locator('#topic-select').select_option(label='2 · Independent report')
            p.locator('#menu-export > summary').click();p.locator('#btn-export-word').click();p.wait_for_selector('#modal-layer:not([hidden])')
            choice=p.get_by_role('radio',name='Independent report',exact=True);choice.wait_for(state='visible')
            self.assertTrue(choice.is_checked(),'Word preparation must retain the selected topic')
            p.locator('#modal-ok').click()
            try:p.wait_for_selector('#report-workspace-bar:not([hidden])')
            except Exception:
                print('Report preparation UI:',p.locator('#toast').inner_text(),p.locator('#workspace-operation-text').inner_text(),flush=True)
                p.screenshot(path=str(evidence/'PREPARE_FAILURE.png'));raise
            p.wait_for_function("document.querySelector('#problems-summary').textContent.includes('0 个错误')")
            fragment=value(p);source(p,fragment.replace('See @fig','Edited. See @fig'))
            p.wait_for_function("document.querySelector('#preview-content').textContent.includes('Edited.')")
            p.locator('#btn-workspace-export').click();p.wait_for_selector('#word-filename')
            p.locator('#word-filename').fill('Independent_Report')
            with p.expect_response(lambda r:'/api/word/export' in r.url,timeout=100000) as pending:
                p.locator('#modal-ok').click()
            response=pending.value;receipt=response.json();self.assertTrue(response.ok,receipt)
            path=Path(receipt['path']);self.assertTrue(path.is_file());self.assertEqual(path.parent,d.project/'output')
            shutil.copyfile(path,evidence/'OUTPUT.docx')
            with zipfile.ZipFile(path) as archive:
                document=ET.fromstring(archive.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
                self.assertGreater(len(document.findall('.//m:oMath',ns)),0)
                self.assertGreater(len(document.findall('.//w:footnoteReference',ns)),0)
                instructions=' '.join([n.text or '' for n in document.findall('.//w:instrText',ns)]+[n.get('{'+ns['w']+'}instr','') for n in document.findall('.//w:fldSimple',ns)])
                self.assertIn('SEQ',instructions);self.assertIn('REF',instructions)
                self.assertIn('Edited.',''.join(n.text or '' for n in document.findall('.//w:t',ns)))
            p.wait_for_function("document.querySelector('#modal-title').textContent.includes('Word 已生成')")
            p.locator('#modal-ok').click()
            valid=value(p);source(p,valid+'\n[^note]: Duplicate must be resolved.\n')
            p.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('Duplicate must')")
            requests=[];p.on('request',lambda r:requests.append(r.url) if '/api/word/prepare' in r.url else None)
            p.locator('#btn-workspace-export').click();p.wait_for_selector('#word-filename');p.locator('#modal-ok').click()
            p.wait_for_function("document.querySelector('#word-export-status').textContent.includes('重复定义')")
            self.assertEqual(requests,[]);self.assertEqual(len(list((d.project/'output').glob('*.docx'))),1)
            self.assertEqual((d.project/'report.md').read_text('utf8'),text);self.assertEqual(d.errors,[])
            (evidence/'RESULT.json').write_text(json.dumps({'status':'PASS','source_sha256':hashlib.sha256(text.encode()).hexdigest(),'word_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_unchanged':True,'native_OMML_SEQ_REF_and_footnote':True,'duplicate_refused_before_prepare':True,'Office_page_editing':'NOT_RUN'},indent=2)+'\n',encoding='utf8')

    def test_engineering_group_uses_separate_caption_row_in_native_component(self):
        """GROUP-02: the actual embedded Word worker must use the new group layout."""
        from io import BytesIO
        from PIL import Image
        assets={}
        for name,size in [('tall.png',(20,60)),('wide.png',(60,20))]:
            stream=BytesIO();Image.new('RGB',size,'navy').save(stream,format='PNG');assets[name]=stream.getvalue()
        text='# Native group\n\n## Method\n\n::: {#fig-group layout-ncol=2}\n\n![Tall $x^2$](assets/tall.png)\n\n![Wide](assets/wide.png)\n\nTwo panels\n\n:::\n\nSee @fig:fig-group.\n'
        with tempfile.TemporaryDirectory() as folder,browser_session() as browser,LiveDocument(browser,folder,text,assets=assets,profile='engineering',registered=True) as d:
            p=d.page;p.locator('#menu-export > summary').click();p.locator('#btn-export-word').click();p.wait_for_selector('#word-filename')
            p.locator('#word-filename').fill('Native_Group')
            with p.expect_response(lambda r:'/api/word/export' in r.url,timeout=100000) as pending:
                p.locator('#modal-ok').click()
            receipt=pending.value.json();self.assertTrue(pending.value.ok,receipt)
            path=Path(receipt['path'])
            with zipfile.ZipFile(path) as archive:
                doc=ET.fromstring(archive.read('word/document.xml'))
            ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
            table=doc.find('.//w:tbl',ns);rows=table.findall('w:tr',ns)
            self.assertEqual(len(rows),2)
            self.assertEqual(len(rows[0].findall('.//w:drawing',ns)),2)
            self.assertEqual(len(rows[1].findall('.//w:drawing',ns)),0)
            self.assertTrue(rows[1].findall('.//m:oMath',ns))
            self.assertIn('Wide',''.join(t.text or '' for t in rows[1].findall('.//w:t',ns)))
            self.assertEqual((d.project/'report.md').read_bytes(),text.encode('utf8'))
            self.assertEqual(d.errors,[])
            evidence=artifact_directory(__file__);shutil.copyfile(path,evidence/'GROUP_OUTPUT.docx')


if __name__=='__main__':unittest.main()
