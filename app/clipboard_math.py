"""Mathematics in the same native clipboard snapshot as HTML/text/images."""
from dataclasses import dataclass
from io import BytesIO
import re
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as E
from legacy_math import embedded_equation,equation_part,ole_to_tex

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M='http://schemas.openxmlformats.org/officeDocument/2006/math'
LABEL=re.compile(r'^\s*[（(]\s*\d+(?:[.\-]\d+)*\s*[)）]\s*$')
TEXT_MISMATCH = '原生公式片段与本次复制文字不一致；整段未插入'
IGNORED_TEXT = re.compile(r'[\s\x07\ufffc]+')
SYMBOL_BULLETS = {'\uf0b7': '•', '\uf0a7': '▪', '\uf06f': '○', '·': '•'}
ORDINAL_PART = r'(?:\d+|[A-Za-z]{1,8}|[零〇一二三四五六七八九十百千]+)'
ORDINAL_LABEL = re.compile(r'(?:[（(])?' + ORDINAL_PART + r'(?:[.．-]' + ORDINAL_PART + r')*[.．、)）]')
ORDINAL_SHAPE = re.compile(r'\d+|[A-Za-z]+|[零〇一二三四五六七八九十百千]+')


@dataclass
class ListLabel:
    text: str
    display: str | None = None


def normalize_text(text):
    return IGNORED_TEXT.sub('', text)


def display_list_label(label):
    return SYMBOL_BULLETS.get(label, label)


def ordinal_shape(label):
    def kind(match):
        part = match[0]
        if part.isdecimal():
            return '0'
        if part.isascii():
            return 'a'
        return '一'

    return ORDINAL_SHAPE.sub(kind, label)


def label_end(label, plain, start):
    end = start + len(label)
    actual = plain[start:end]
    if display_list_label(actual) == display_list_label(label):
        return end
    # WPS's text can retain the original ordinal while its HTML renumbers a
    # copied subset. Match only the same label form at this verified position.
    if ORDINAL_LABEL.fullmatch(label):
        match = ORDINAL_LABEL.match(plain, start, start + 64)
        if match and ordinal_shape(match[0]) == ordinal_shape(label):
            return match.end()
    raise ValueError(TEXT_MISMATCH)


def verify_list_items(html_parts, expected, native_parts, visual_text, *, include_labels):
    """Match visible text between the same images, then verify the full plain text.

    The HTML gives the displayed ordinal even when WPS resets the native list
    definition for a copied subset. Only Office's explicitly marked label spans
    may be additional text. Math and ordinary numbers match at their own positions.
    """
    chunks = [[]]
    for part in html_parts:
        if part is None:
            chunks.append([])
        else:
            chunks[-1].append(part)
    if len(chunks) != len(native_parts) or any(
            ''.join(part for part in html if isinstance(part, str)) != ''.join(native)
            for html, native in zip(chunks, native_parts)):
        raise ValueError(TEXT_MISMATCH)
    if include_labels:
        cursor = 0
        for chunk, math in zip(chunks, visual_text):
            for part in chunk + [math]:
                if isinstance(part, ListLabel):
                    end = label_end(part.text, expected, cursor)
                    part.display = display_list_label(expected[cursor:end])
                    cursor = end
                else:
                    if not expected.startswith(part, cursor):
                        raise ValueError(TEXT_MISMATCH)
                    cursor += len(part)
        if cursor != len(expected):
            raise ValueError(TEXT_MISMATCH)
    else:
        for part in html_parts:
            if isinstance(part, ListLabel):
                part.display = display_list_label(part.text)


def xml(data):
    if len(data)>4*1024*1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('公式 XML 无效或超过限制')
    try:return E.fromstring(data)
    except E.ParseError as error:raise ValueError('公式 XML 不完整') from error


def native_formulas(blob,sources,expected_text,convert,*,list_parts=(),list_images=()):
    """Bind native visual positions to exactly the HTML snapshot's images.

    Anonymous source formulas receive identity only in the original HRS paste
    transaction. Numbers beside a standalone formula are outside its math tree.
    """
    if not blob:return {}
    if len(blob)>30*1024*1024:raise ValueError('原生剪贴板文档超过限制')
    try:
        with ZipFile(BytesIO(blob)) as z:
            members=z.infolist()
            if len(members)>1000 or len({m.filename.casefold() for m in members})!=len(members) or sum(m.file_size for m in members)>64*1024*1024:
                raise ValueError('原生剪贴板文档成员无效或超过限制')
            root=xml(z.read('word/document.xml'))
            parents={child:parent for parent in root.iter() for child in parent}
            relations={}
            if 'word/_rels/document.xml.rels' in z.namelist():
                relations={r.get('Id'):r.attrib for r in xml(z.read('word/_rels/document.xml.rels'))}
            visuals = []
            ordinary_text = [[]]

            def add_visual(kind, node, text=''):
                visuals.append((kind, node, normalize_text(text)))
                ordinary_text.append([])

            def walk(node):
                if node.tag in ('{'+M+'}oMath','{'+M+'}oMathPara'):
                    text = ''.join(t.text or '' for t in node.iter('{'+M+'}t'))
                    add_visual('omml', node, text)
                    return
                if node.tag=='{'+W+'}object':
                    if embedded_equation(node) is not None:
                        add_visual('ole', node)
                        return
                    raise ValueError('剪贴板包含尚不支持的嵌入对象，整段未插入')
                if node.tag in ('{'+W+'}drawing','{'+W+'}pict'):
                    add_visual('image', node)
                    return
                if node.tag == '{'+W+'}t':
                    ordinary_text[-1].append(normalize_text(node.text or ''))
                for child in node:walk(child)
            walk(root)
            if not any(kind!='image' for kind,_,_ in visuals):return {}
            if len(visuals)!=len(sources):raise ValueError('公式、图片与本次 HTML 位置无法一一对应；整段未插入')
            expected = normalize_text(expected_text)
            visual_text = [text for _, _, text in visuals] + ['']
            actual = ''.join(''.join(native) + math for native, math in zip(ordinary_text, visual_text))
            if list_parts:
                verify_list_items(list_parts, expected, ordinary_text, visual_text, include_labels=actual != expected)
            elif actual != expected:
                raise ValueError(TEXT_MISMATCH)
            result={};requests=[];pending=[]
            for (kind,node,_),url,in_list in zip(visuals,sources,list_images or [False] * len(visuals),strict=True):
                if kind=='image':continue
                p=node
                while p in parents and p.tag!='{'+W+'}p':p=parents[p]
                prose=''.join(t.text or '' for t in p.iter('{'+W+'}t')).strip()
                display = not in_list and (not prose or bool(LABEL.fullmatch(prose)) or node.tag == '{'+M+'}oMathPara')
                item={'display':display,'source_number':prose if display and LABEL.fullmatch(prose) else ''}
                if not url or sources.count(url) != 1:
                    raise ValueError('公式与 HTML 图像地址无法一一对应；整段未插入')
                if kind=='ole':
                    target=equation_part(embedded_equation(node),relations)
                    item['tex']=ole_to_tex(z.read(target))
                else:
                    requests.append({'format':'omml','source':E.tostring(node,encoding='unicode')});pending.append(item)
                result[url]=item
            if requests:
                if convert is None:raise ValueError('粘贴原生公式需要选择已有 Pandoc（导出 Word → 公式支持）')
                values=convert(requests)
                if len(values)!=len(pending):raise ValueError('公式转换数量不一致；整段未插入')
                for item,tex in zip(pending,values):item['tex']=tex
            return result
    except (BadZipFile,KeyError) as error:raise ValueError('原生剪贴板文档或公式资源不完整') from error
