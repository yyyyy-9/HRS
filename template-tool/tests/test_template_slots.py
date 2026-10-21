"""A report may replace its marked tail without erasing its cover or TOC."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree as E

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from wps_pipeline.resolve_styles import inspect_template
from wps_pipeline.assemble_reports import Assembler
from wps_pipeline.verify_report_build import verify

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
N = {'w': W}
Q = lambda name: '{' + W + '}' + name
BASE = ROOT / 'templates/target_template.docx'


def read_parts(path):
    with ZipFile(path) as z:
        return {name: z.read(name) for name in z.namelist()}


def save_parts(path, parts):
    with ZipFile(path, 'x', ZIP_DEFLATED) as z:
        for name, raw in parts.items():
            z.writestr(name, raw)


def raw_xml(node):
    return E.tostring(node, xml_declaration=True, encoding='UTF-8', standalone=True)


def marked_template(path):
    parts = read_parts(BASE)
    root = E.fromstring(parts['word/document.xml'])
    body = root.find(Q('body'))
    old = [deepcopy(n) for n in body if n.tag != Q('sectPr')]
    for n in list(body)[:-1]:
        body.remove(n)
    cover = E.Element(Q('p'))
    E.SubElement(E.SubElement(cover, Q('r')), Q('t')).text = '封面必须保留'
    body.insert(0, cover)
    slot = E.Element(Q('sdt'))
    pr = E.SubElement(slot, Q('sdtPr'))
    E.SubElement(pr, Q('tag')).set(Q('val'), 'wps-report-body-v1')
    content = E.SubElement(slot, Q('sdtContent'))
    content.extend(old)
    body.insert(1, slot)
    parts['word/document.xml'] = raw_xml(root)
    save_parts(path, parts)


class TemplateSlots(unittest.TestCase):
    def test_public_cover_preserves_toc_header_and_plain_body_bookmark(self):
        """OSS-PREP-01: the generated generic cover remains a usable template."""
        sample=ROOT/'templates/cover_template_v0311.docx'
        before=read_parts(sample)
        profile=inspect_template(sample)
        self.assertEqual(profile['body_slot']['kind'],'bookmark')
        output=self.folder/'public-cover-output.docx'
        Assembler(sample,master=True,master_title='合成报告').save(output)
        checked=verify(output.with_suffix('.assembly.json'))
        self.assertEqual(checked['status'],'PASS',checked['errors'])
        parts=read_parts(output)
        root=E.fromstring(parts['word/document.xml'])
        self.assertIn('HRS 通用工程报告',root.xpath('//w:t/text()',namespaces=N))
        self.assertIn('合成报告',root.xpath('//w:t/text()',namespaces=N))
        self.assertTrue(root.xpath('//w:fldSimple[contains(@w:instr,"TOC")]',namespaces=N))
        self.assertEqual(parts['word/header_hrs_public.xml'],before['word/header_hrs_public.xml'])
        self.assertEqual(E.fromstring(before['docProps/core.xml']).xpath('//*[local-name()="creator"]/text()'),['yyyyy-9'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wps-template-test-')
        self.folder = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def test_prepared_shell_imports_template_numbering_dependencies(self):
        """v0.3.11: copied heading styles must not point at absent/foreign numbering definitions."""
        from wps_pipeline.template_prepare import prepare_template
        parts=read_parts(BASE);styles=E.fromstring(parts['word/styles.xml'])
        for num in styles.findall('.//'+Q('numPr')):num.getparent().remove(num)
        parts['word/styles.xml']=raw_xml(styles);parts.pop('word/numbering.xml',None)
        for name,tag,attribute,match in [('word/_rels/document.xml.rels','Relationship','Type','/numbering'),('[Content_Types].xml','Override','PartName','/word/numbering.xml')]:
            root=E.fromstring(parts[name])
            for n in list(root):
                if (n.get(attribute) or '').endswith(match):root.remove(n)
            parts[name]=raw_xml(root)
        source=self.folder/'shell.docx';save_parts(source,parts);before=hashlib.sha256(source.read_bytes()).hexdigest()
        output=self.folder/'prepared.docx';prepare_template(source,output,0,before)
        result=read_parts(output);self.assertIn('word/numbering.xml',list(result))
        styles=E.fromstring(result['word/styles.xml']);numbers=E.fromstring(result['word/numbering.xml'])
        for style in styles.findall(Q('style')):
            name=style.find(Q('name'))
            if name is not None and name.get(Q('val')).casefold().startswith('heading '):
                num=style.find('.//'+Q('numId'))
                if num is not None:self.assertIsNotNone(numbers.find(Q('num')+'[@'+Q('numId')+'="'+num.get(Q('val'))+'"]'))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)

    def test_marked_template_accepts_frontmatter(self):
        """A known empty body slot permits the cover outside it to survive."""
        path = self.folder / 'marked.docx'
        marked_template(path)
        profile = inspect_template(path)
        self.assertEqual(profile['body_slot']['kind'], 'marked')
        self.assertEqual(profile['body_slot']['index'], 1)

    def test_assembler_preserves_cover_and_accounts_for_it(self):
        """Master title is inserted after the cover; independent verification passes."""
        path = self.folder / 'marked.docx'
        marked_template(path)
        output = self.folder / 'out.docx'
        Assembler(path, master=True, master_title='新报告').save(output)
        result = verify(output.with_suffix('.assembly.json'))
        self.assertEqual(result['status'], 'PASS', result['errors'])
        root = E.fromstring(read_parts(output)['word/document.xml'])
        self.assertEqual(root.xpath('//w:body/w:p//w:t/text()', namespaces=N),
                         ['封面必须保留', '新报告'])

    def test_frontmatter_tamper_is_rejected_independently(self):
        """Rebinding an edited output hash must not hide altered cover text."""
        path = self.folder / 'marked.docx'
        marked_template(path)
        output = self.folder / 'out.docx'
        Assembler(path, master=True).save(output)
        parts = read_parts(output)
        root = E.fromstring(parts['word/document.xml'])
        root.find('.//' + Q('t')).text = '错误的封面'
        parts['word/document.xml'] = raw_xml(root)
        changed = self.folder / 'changed.docx'
        save_parts(changed, parts)
        receipt = json.loads(output.with_suffix('.assembly.json').read_text('utf-8'))
        receipt['output'] = str(changed)
        receipt['output_sha256'] = hashlib.sha256(changed.read_bytes()).hexdigest()
        record = self.folder / 'changed.assembly.json'
        record.write_text(json.dumps(receipt), encoding='utf-8')
        result = verify(record)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('preserved_template_frontmatter', result['errors'])

    def test_unmarked_legacy_contract_still_works(self):
        """The shipped two-paragraph template keeps its existing contract and output."""
        output = self.folder / 'legacy.docx'
        Assembler(BASE, master=True, master_title='原流程').save(output)
        self.assertEqual(verify(output.with_suffix('.assembly.json'))['status'], 'PASS')
        self.assertEqual(inspect_template(BASE)['body_slot']['kind'], 'legacy')

    def test_arbitrary_unmarked_document_is_not_cleared(self):
        """Only an explicit slot authorizes removal; arbitrary template content is refused."""
        parts = read_parts(BASE)
        root = E.fromstring(parts['word/document.xml'])
        root.find('.//' + Q('t')).text = '用户自己的内容'
        parts['word/document.xml'] = raw_xml(root)
        path = self.folder / 'unknown.docx'
        save_parts(path, parts)
        with self.assertRaises(ValueError):
            inspect_template(path)

    def test_duplicate_or_non_tail_slot_is_rejected(self):
        """An ambiguous slot cannot silently choose which region to replace."""
        path = self.folder / 'marked.docx'
        marked_template(path)
        for duplicate in (False, True):
            parts = read_parts(path)
            root = E.fromstring(parts['word/document.xml'])
            body = root.find(Q('body'))
            body.insert(len(body)-1, deepcopy(body[1]) if duplicate else E.Element(Q('p')))
            parts['word/document.xml'] = raw_xml(root)
            candidate = self.folder / ('duplicate.docx' if duplicate else 'not-tail.docx')
            save_parts(candidate, parts)
            with self.assertRaises(ValueError):
                inspect_template(candidate)

    def test_prepare_keeps_original_and_protects_cover_inheritance(self):
        """Body style normalization must not change cover fonts inherited from Normal."""
        from wps_pipeline.template_prepare import prepare_template
        source = self.folder / 'source.docx'
        marked_template(source)
        parts = read_parts(source)
        root = E.fromstring(parts['word/document.xml'])
        body = root.find(Q('body'))
        slot = body[1]
        for i, node in enumerate(list(slot.find(Q('sdtContent')))):
            body.insert(1+i, node)
        body.remove(slot)
        styles = E.fromstring(parts['word/styles.xml'])
        normal = next(s for s in styles.findall(Q('style'))
                      if s.find(Q('name')).get(Q('val')).lower() == 'normal')
        rp = normal.find(Q('rPr'))
        if rp is None:
            rp = E.SubElement(normal, Q('rPr'))
        for old in list(rp):
            rp.remove(old)
        E.SubElement(rp, Q('sz')).set(Q('val'), '36')
        parts['word/styles.xml'] = raw_xml(styles)
        parts['word/document.xml'] = raw_xml(root)
        source.unlink()
        save_parts(source, parts)
        before = source.read_bytes()
        output = self.folder / 'prepared.docx'
        result = prepare_template(source, output, 1, hashlib.sha256(before).hexdigest())
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(inspect_template(output)['body_slot']['kind'], 'bookmark')
        prepared = read_parts(output)
        proot = E.fromstring(prepared['word/document.xml'])
        sid = proot.find('.//' + Q('pStyle')).get(Q('val'))
        ps = E.fromstring(prepared['word/styles.xml'])
        protected = ps.find(Q('style') + '[@' + Q('styleId') + '="' + sid + '"]')
        self.assertEqual(protected.find(Q('rPr') + '/' + Q('sz')).get(Q('val')), '36')
        self.assertTrue(result['preserved_style_ids'])
        with self.assertRaises(FileExistsError):
            prepare_template(source, output, 1, hashlib.sha256(before).hexdigest())

    def test_prepare_rejects_stale_locator_before_writing(self):
        """A body index is bound to the actual input bytes, not an older inspection."""
        from wps_pipeline.template_prepare import prepare_template
        output = self.folder / 'out.docx'
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            prepare_template(BASE, output, 0, '0'*64)
        self.assertFalse(output.exists())

    def test_math_stage_preserves_frontmatter_and_its_page_break(self):
        """Cover formulas and page breaks are preserved; body-only policy stays strict."""
        from wps_pipeline.native_math_text import convert
        from wps_pipeline.verify_native_math import verify as verify_math
        path = self.folder / 'marked.docx'
        marked_template(path)
        parts = read_parts(path)
        root = E.fromstring(parts['word/document.xml'])
        body = root.find(Q('body'))
        body[0].find('.//' + Q('t')).text = 'x = y + 1'
        p = E.Element(Q('p'))
        E.SubElement(E.SubElement(p, Q('r')), Q('br')).set(Q('type'), 'page')
        body.insert(1, p)
        parts['word/document.xml'] = raw_xml(root)
        marked = self.folder / 'math-frontmatter.docx'
        save_parts(marked, parts)
        assembled = self.folder / 'assembled.docx'
        Assembler(marked, master=True).save(assembled)
        output = self.folder / 'math-output.docx'
        receipt = convert(assembled, output, protected_prefix_blocks=2)
        self.assertEqual(receipt['conversions'], [])
        checked = verify_math(output.with_suffix('.math.json'), assembled.with_suffix('.assembly.json'))
        self.assertEqual(checked['status'], 'PASS', checked['errors'])


if __name__ == '__main__':
    unittest.main()
