"""NUMBERING-02: source syntax must not choose a separate number sequence."""
from pathlib import Path
import sys, unittest,struct
from io import BytesIO
from zipfile import ZipFile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from report_contract import analyze
from render_profile import normalize_options
from legacy_math import MTEF3,ole_to_tex
from clipboard_math import native_formulas,xml


def compound_math(stream):
    """Generate a minimal MS-CFB carrier; no external Office file is required."""
    header=bytearray(512);header[:8]=bytes.fromhex('d0cf11e0a1b11ae1')
    for offset,value in [(24,62),(26,3),(28,65534),(30,9),(32,6)]:struct.pack_into('<H',header,offset,value)
    for offset,value in [(44,1),(48,1),(56,4096),(60,2),(64,1),(68,0xfffffffe),(72,0)]:struct.pack_into('<I',header,offset,value)
    struct.pack_into('<109I',header,76,0,*([0xffffffff]*108))
    fat=struct.pack('<128I',0xfffffffd,0xfffffffe,0xfffffffe,0xfffffffe,*([0xffffffff]*124))
    directory=bytearray(512)
    for offset,name,kind,start,size in [(0,'Root Entry',5,3,512),(128,'Equation Native',2,0,len(stream))]:
        text=(name+'\0').encode('utf-16le');directory[offset:offset+len(text)]=text
        struct.pack_into('<H',directory,offset+64,len(text));directory[offset+66]=kind
        struct.pack_into('<I',directory,offset+116,start);struct.pack_into('<Q',directory,offset+120,size)
    count=(len(stream)+63)//64
    mini=struct.pack('<128I',*[i+1 if i<count-1 else 0xfffffffe if i==count-1 else 0xffffffff for i in range(128)])
    return bytes(header)+fat+bytes(directory)+mini+stream.ljust(512,b'\0')


class UnifiedNumbering(unittest.TestCase):
    def test_anonymous_and_identified_display_math_share_sequence(self):
        source = '$$\nx=1\n$$\n\n<!-- hrs:eq id=eq-second -->\n$$\ny=2\n$$\n\n\\[\nz=3\n\\]\n'
        ir = analyze(source)
        self.assertTrue(ir['ok'], ir['diagnostics'])
        self.assertEqual([b.get('number') for b in ir['blocks'] if b['type']=='equation'], [1,2,3])
        self.assertEqual(ir['objects']['entries'][0]['number'], 2)

    def test_plain_pipe_tables_count_without_rewriting_source(self):
        source = '| A | B |\n|---|---|\n| 1 | 2 |\n\n| C | D |\n|---|---|\n| 3 | 4 |\n'
        ir = analyze(source)
        tables = [b for b in ir['blocks'] if b['type']=='table']
        self.assertEqual([b.get('number') for b in tables], [1,2])
        self.assertEqual(''.join(b['source'] for b in tables).replace('\n\n','\n'), source.replace('\n\n','\n'))

    def test_formula_setting_is_document_level_and_boolean(self):
        self.assertFalse(normalize_options()['show_equation_numbers'])
        self.assertTrue(normalize_options({'show_equation_numbers':True})['show_equation_numbers'])
        with self.assertRaises(ValueError):normalize_options({'show_equation_numbers':'true'})

    def test_code_examples_never_consume_object_numbers(self):
        ir=analyze('```text\n$$\nx=1\n$$\n```\n\n$$\ny=2\n$$\n')
        self.assertEqual([b.get('number') for b in ir['blocks'] if b['type']=='equation'],[1])

    def test_actual_wps_editor_fraction_stream(self):
        # Captured from this project's generated y=1/2, entered in KSEE3 UI.
        data=bytes.fromhex('1c000000020097c42200000000000000e00c990054ac980000000000030101031e0a010281790002863d00030e0000010288310000010288320000000000')
        self.assertEqual(ole_to_tex(compound_math(data)),r'\mathrm{y}=\frac{1}{2}')

    def test_legacy_math_rejects_truncation_unknown_templates_and_cycles(self):
        for data in [b'\3\1\1\3\0\1\2', b'\3\1\1\3\0\1\3\xff\0\0\0\0\0',b'\3\1\1\3\0\1\2\x83\x00\xe0\0\0']:
            with self.subTest(data=data),self.assertRaises(ValueError):MTEF3(data).objects()
        carrier=bytearray(compound_math(b'bad'))
        struct.pack_into('<I',carrier,512+4,1)
        with self.assertRaises(ValueError):ole_to_tex(carrier)

    def test_math_structure_is_preserved_or_rejected_not_flattened(self):
        self.assertEqual(MTEF3.template(13,1,['x+1','3']),r'\sqrt[3]{x+1}')
        self.assertEqual(MTEF3.template(15,2,['i','2']),r'_{i}^{2}')
        self.assertEqual(MTEF3.template(1,1,['x']),r'\left( x\right.')
        self.assertEqual(MTEF3.template(14,0,['x+1','2']),r'\frac{x+1}{2}')
        for kind,variation,slots in [(13,2,['x','2']),(14,9,['a','b']),(44,0,['i','j']),(15,0,['wrong'])]:
            with self.subTest(kind=kind,variation=variation),self.assertRaises(ValueError):MTEF3.template(kind,variation,slots)
        # Prime and triple-dot have different mathematical meanings.
        def accented(code):
            parser=MTEF3(bytes.fromhex('0301010300012283780006')+bytes([code,0,0,0]))
            return ''.join(parser.objects())
        self.assertEqual(accented(4),r'\dddot{x}')
        self.assertEqual(accented(5),"{x}'")

    def test_clipboard_native_math_requires_same_text_and_visual_positions(self):
        document='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body><w:p><m:oMath><m:r><m:t>x=2</m:t></m:r></m:oMath><w:r><w:t>(9)</w:t></w:r></w:p></w:body></w:document>'
        buffer=BytesIO()
        with ZipFile(buffer,'w') as archive:archive.writestr('word/document.xml',document)
        calls=[]
        def convert(items):calls.extend(items);return ['x=2']
        data=native_formulas(buffer.getvalue(),['formula.png'],'x=2(9)',convert)
        self.assertEqual(data,{'formula.png':{'display':True,'source_number':'(9)','tex':'x=2'}})
        self.assertEqual(len(calls),1)
        for urls,text in [([], 'x=2(9)'),(['formula.png'],'unrelated text')]:
            with self.subTest(urls=urls,text=text),self.assertRaises(ValueError):native_formulas(buffer.getvalue(),urls,text,convert)
        with self.assertRaises(ValueError):xml(b'<!DOCTYPE x [<!ENTITY y "bad">]><x>&y;</x>')

    def test_bracket_math_identity_does_not_change_delimiter_or_sequence(self):
        raw='<!-- hrs:eq id=eq-bracket -->\r\n\\[\r\nx=2\r\n\\]\r\n'
        equation=next(b for b in analyze(raw)['blocks'] if b['type']=='equation')
        self.assertEqual((equation['id'],equation['number'],equation['delimiter']),('eq-bracket',1,'bracket'))
        self.assertEqual(equation['source'],raw)

if __name__=='__main__':unittest.main()
