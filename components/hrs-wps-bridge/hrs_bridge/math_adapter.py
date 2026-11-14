"""Use Pandoc's math converter only; HRS remains the Markdown parser."""
from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
import json
import re
import subprocess
from zipfile import BadZipFile, ZipFile
from docx.oxml.ns import qn
from lxml import etree as E
from .ooxml import M, N, element
from .runtime import BridgeError

NATIVE_MATH_FONT = 'Cambria Math'
INLINE_TEXT_FONT = 'Times New Roman'
MATH_CONTROLS = {qn('m:' + name): qn('m:' + name + 'Pr') for name in (
    'acc', 'bar', 'borderBox', 'box', 'd', 'eqArr', 'f', 'func', 'groupChr',
    'limLow', 'limUpp', 'm', 'nary', 'phant', 'rad', 'sPre', 'sSub', 'sSubSup', 'sSup',
)}
BATCH_ITEMS=64
BATCH_TEX_CHARS=64*1024
BATCH_OMML_BYTES=1024*1024
PANDOC_TIMEOUT_SECONDS=30
TEX_SPECIAL = re.compile(r'[\\%{}]')
LEGACY_ROMAN = re.compile(r'(\s*)\\rm(?![A-Za-z])\s*')
TEX_TEXT_COMMANDS = frozenset({
    'text', 'textrm', 'textnormal', 'textsf', 'texttt', 'textbf',
    'textit', 'textsc', 'mbox', 'operatorname',
})


def set_native_math_font(omml):
    """Set fonts on both the visible runs and the math structure controls."""
    for structure in list(omml.iter(*MATH_CONTROLS)):
        property_tag = MATH_CONTROLS[structure.tag]
        properties = structure.find(property_tag)
        if properties is None:
            properties = E.Element(property_tag)
            structure.insert(0, properties)
        if properties.find('m:ctrlPr', N) is None:
            E.SubElement(properties, qn('m:ctrlPr'))
    for node in omml.xpath('.//m:r | .//m:ctrlPr', namespaces=N):
        properties = node.find('w:rPr', N)
        if properties is None:
            properties = element('w:rPr')
            math_properties = node.find('m:rPr', N)
            node.insert(node.index(math_properties) + 1 if math_properties is not None else 0, properties)
        fonts = properties.find('w:rFonts', N)
        if fonts is None:
            fonts = element('w:rFonts')
            style = properties.find('w:rStyle', N)
            properties.insert(properties.index(style) + 1 if style is not None else 0, fonts)
        for attribute in ('asciiTheme', 'hAnsiTheme'):
            fonts.attrib.pop(qn('w:' + attribute), None)
        for attribute in ('ascii', 'hAnsi'):
            fonts.set(qn('w:' + attribute), NATIVE_MATH_FONT)


@dataclass(frozen=True)
class MathTextRun:
    text: str
    bold: bool = False
    italic: bool = False
    script: str | None = None


def inline_math_text(omml):
    """Project supported OMML into Word text runs, or keep the whole equation.

    Consume Pandoc's parsed structure. Never flatten an unknown construct by
    concatenating its m:t nodes, which would lose fractions, limits or grouping.
    """
    runs = []
    scripts = {'sSub': ('e', 'sub'), 'sSup': ('e', 'sup'), 'sSubSup': ('e', 'sub', 'sup')}
    alignment = {'e': None, 'sub': 'subscript', 'sup': 'superscript'}

    def collect(node, script=None):
        tag = E.QName(node)
        if tag.namespace != M:
            return False
        kind = tag.localname
        if kind == 'r':
            texts = node.findall('m:t', N)
            if len(texts) != 1 or not texts[0].text:
                return False
            if any(child.tag not in (qn('m:t'), qn('m:rPr'), qn('w:rPr')) for child in node):
                return False
            text = texts[0].text
            math_style = node.find('m:rPr', N)
            if math_style is not None and any(child.tag not in (qn('m:sty'), qn('m:scr'), qn('m:nor')) for child in math_style):
                return False
            alphabet = node.find('m:rPr/m:scr', N)
            if alphabet is not None and alphabet.get(qn('m:val')) != 'roman':
                return False
            style = node.find('m:rPr/m:sty', N)
            normal = node.find('m:rPr/m:nor', N)
            upright = normal is not None and normal.get(qn('m:val'), '1') not in ('0', 'false', 'off')
            variant = 'i' if not upright and any(c.isalpha() for c in text) else 'p'
            if style is not None:
                variant = style.get(qn('m:val'))
            if variant not in ('p', 'b', 'i', 'bi'):
                return False
            runs.append(MathTextRun(text, 'b' in variant, 'i' in variant, script))
            return True
        if kind in ('oMath', 'e', 'sub', 'sup'):
            return bool(len(node)) and all(collect(child, script) for child in node)
        if kind in scripts and script is None:
            parts = [child for child in node if child.tag != qn('m:' + kind + 'Pr')]
            names = scripts[kind]
            return [child.tag for child in parts] == [qn('m:' + name) for name in names] and all(
                collect(child, alignment[name]) for child, name in zip(parts, names))
        if kind == 'd':
            arguments = node.findall('m:e', N)
            if len(arguments) != 1 or any(child.tag not in (qn('m:dPr'), qn('m:e')) for child in node):
                return False
            for position, default in (('begChr', '('), ('endChr', ')')):
                prop = node.find('m:dPr/m:' + position, N)
                char = prop.get(qn('m:val'), default) if prop is not None else default
                if char:
                    runs.append(MathTextRun(char, script=script))
                if position == 'begChr' and not collect(arguments[0], script):
                    return False
            return True
        return False

    return runs if collect(omml) and runs else None


def tex_special_spans(tex):
    """Yield whole controls and comments so their braces are never delimiters."""
    end = 0
    while match := TEX_SPECIAL.search(tex, end):
        start, end = match.span()
        if tex[start] == '\\' and end < len(tex):
            if tex[end].isalpha():
                while end < len(tex) and tex[end].isalpha():
                    end += 1
            else:
                end += 1
        elif tex[start] == '%':
            newline = tex.find('\n', end)
            end = len(tex) if newline == -1 else newline + 1
        yield start, end


def normalize_tex_for_pandoc(tex):
    r"""Adapt scoped old roman declarations and escaped math whitespace.

    Only the converter input changes; source/provenance and cache keys retain
    the original TeX. The complete formula is also a bounded math scope.
    Mid-expression declarations remain available for literal export if Pandoc
    cannot convert them. Escaped braces, comments and text arguments stay intact.
    An escaped line end or tab becomes a TeX control space.
    """
    if not re.search(r'\\(?:rm|[\n\r\t])', tex):
        return tex

    spans = list(tex_special_spans(tex))
    openings, group_ends = [], {}
    for start, _ in spans:
        if tex[start] == '{':
            openings.append(start)
        elif tex[start] == '}' and openings:
            group_ends[openings.pop()] = start

    parts, roman_ends = [], set()

    def open_scope(start, end):
        declaration = LEGACY_ROMAN.match(tex, start, end)
        if declaration is None:
            return start
        parts.extend((declaration.group(1), r'\mathrm{'))
        roman_ends.add(end)
        return declaration.end()

    cursor = open_scope(0, len(tex))
    for start, end in spans:
        if start < cursor:
            continue
        parts.append(tex[cursor:start])
        char = tex[start]
        if char == '{':
            closing = group_ends.get(start)
            if closing is None:
                cursor = start  # Keep the incomplete group literal for Pandoc.
                break
            parts.append(char)
            cursor = open_scope(end, closing)
            continue
        if char == '\\':
            command = tex[start+1:end]
            if command in {'\n', '\r', '\t'}:
                parts.append('\\ ')
                cursor = end
                continue
            if command in TEX_TEXT_COMMANDS:
                argument = end + tex.startswith('*', end)
                while argument < len(tex) and tex[argument].isspace():
                    argument += 1
                if argument in group_ends:
                    end = group_ends[argument] + 1
        if start in roman_ends:
            parts.append('}')
        parts.append(tex[start:end])
        cursor = end
    parts.append(tex[cursor:])
    if len(tex) in roman_ends:
        parts.append('}')
    return ''.join(parts)


@dataclass(frozen=True)
class NativeMathResult:
    node: E._Element | None = None
    reason: str | None = None


@dataclass(frozen=True)
class TexMathResult:
    tex: str | None = None
    reason: str | None = None


def math_batches(keys, *, limit=BATCH_TEX_CHARS):
    batch, chars = [], 0
    for key in keys:
        size=len(key[0])
        if batch and (len(batch) >= BATCH_ITEMS or chars + size > limit):
            yield batch
            batch, chars = [], 0
        batch.append(key)
        chars += size
    if batch:
        yield batch


def empty_word_run(node):
    # Pandoc may append an invisible U+200B run after inline OMML.
    return (node.tag == qn('w:r')
            and all(child.tag in (qn('w:rPr'), qn('w:t')) for child in node)
            and all(not (text.text or '').replace('\u200b', '').strip() for text in node.findall('w:t', N)))


class MathAdapter:
    def __init__(self,runtime):
        if not runtime.pandoc:raise BridgeError('PANDOC_PATH is required for native TeX/OMML conversion')
        self.exe = runtime.pandoc

    def _native_batch(self, keys, version):
        blocks = [{'t': 'Para', 'c': [{'t': 'Math', 'c': [
            {'t': 'DisplayMath' if display else 'InlineMath'}, normalize_tex_for_pandoc(tex)
        ]}]} for tex, display in keys]
        ast = {'pandoc-api-version': version, 'meta': {}, 'blocks': blocks}
        # Pandoc emits a plain TeX run for a rejected expression. The paragraph
        # boundary lets us verify every result while retaining the valid ones.
        result = subprocess.run([self.exe, '-f', 'json', '-t', 'docx', '-o', '-'],
                                input=json.dumps(ast).encode('utf8'), capture_output=True,
                                check=True, timeout=PANDOC_TIMEOUT_SECONDS)
        with ZipFile(BytesIO(result.stdout)) as archive:
            document = E.fromstring(archive.read('word/document.xml'))
        paragraphs = document.xpath('/w:document/w:body/w:p', namespaces=N)
        if len(paragraphs) != len(keys):
            raise BridgeError('Native math conversion changed the number of formula paragraphs')
        converted = {}
        for key, paragraph in zip(keys, paragraphs):
            nodes = [node for node in paragraph if node.tag != qn('w:pPr') and not empty_word_run(node)]
            display = key[1]
            expected = qn('m:oMathPara' if display else 'm:oMath')
            if (len(nodes) != 1 or nodes[0].tag != expected
                    or len(paragraph.xpath('.//m:oMath', namespaces=N)) != 1):
                converted[key] = NativeMathResult(reason='math_unconverted')
                continue
            node = deepcopy(nodes[0])
            if not display:
                set_native_math_font(node)
            converted[key] = NativeMathResult(node=node)
        return converted

    def native_many(self, expressions):
        """Convert each unique source expression once and keep its outcome."""
        keys = dict.fromkeys(expressions)
        if not keys:
            return {}
        try:
            probe = subprocess.run([self.exe, '-f', 'markdown', '-t', 'json'], input=b'',
                                   capture_output=True, check=True, timeout=PANDOC_TIMEOUT_SECONDS)
            version = json.loads(probe.stdout)['pandoc-api-version']
            if not isinstance(version, list) or not version or any(type(part) is not int for part in version):
                raise ValueError('Invalid Pandoc JSON API version')
        except subprocess.TimeoutExpired:
            return dict.fromkeys(keys, NativeMathResult(reason='math_timeout'))
        except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError):
            return dict.fromkeys(keys, NativeMathResult(reason='math_unavailable'))
        converted = {}
        try:
            for batch in math_batches(keys):
                try:
                    converted.update(self._native_batch(batch, version))
                except (subprocess.CalledProcessError, BadZipFile, KeyError, E.XMLSyntaxError, BridgeError):
                    converted.update(dict.fromkeys(batch, NativeMathResult(reason='math_invalid_output')))
        except subprocess.TimeoutExpired:
            converted.update(dict.fromkeys(keys.keys() - converted.keys(), NativeMathResult(reason='math_timeout')))
        except OSError:
            converted.update(dict.fromkeys(keys.keys() - converted.keys(), NativeMathResult(reason='math_unavailable')))
        return converted

    def tex(self,omml):
        return self.tex_many([omml])[0]

    @staticmethod
    def math_values(result, count):
        if result.returncode:raise BridgeError('Math conversion rejected: '+result.stderr.decode('utf8'))
        found=[]
        def walk(n):
            if isinstance(n,dict):
                if n.get('t')=='Math':found.append(n['c'][1])
                for v in n.values():walk(v)
            elif isinstance(n,list):
                for v in n:walk(v)
        walk(json.loads(result.stdout))
        if len(found)!=count or any(not text.strip() for text in found):raise BridgeError('Math conversion changed the number of formulas')
        return found

    def _omml_json(self, expressions, markers=()):
        from docx import Document
        doc=Document()
        for index,omml in enumerate(expressions):
            paragraph=doc.add_paragraph()
            if markers:paragraph.add_run(markers[index])
            paragraph._p.append(deepcopy(omml))
        data=BytesIO();doc.save(data)
        return subprocess.run([self.exe,'--fail-if-warnings','-f','docx','-t','json'],
                              input=data.getvalue(),capture_output=True,timeout=PANDOC_TIMEOUT_SECONDS)

    def tex_many(self,expressions):
        # Strict clipboard and roundtrip conversion require every result.
        result=self._omml_json(expressions)
        return self.math_values(result,len(expressions))

    def _tex_import_batch(self, batch):
        markers={f'HRSFormulaBoundary{index}':key for index,(_,key) in enumerate(batch)}
        nodes=[E.fromstring(raw) for raw,_ in batch]
        result=self._omml_json(nodes,tuple(markers))
        if result.returncode:
            if len(batch)>1 and b'WARNING' in result.stderr:
                # A converter warning is not reliably tied to its formula by Pandoc.
                # Reuse the same batch protocol on either side of the split.
                middle=len(batch)//2
                return {**self._tex_import_batch(batch[:middle]),**self._tex_import_batch(batch[middle:])}
            return dict.fromkeys(markers.values(),TexMathResult(reason='Pandoc 拒绝转换这批公式'))
        outputs={};seen=set()
        for block in json.loads(result.stdout)['blocks']:
            if block['t']!='Para' or not block['c']:continue
            first,*rest=block['c']
            if first['t']!='Str' or first['c'] not in markers:continue
            key=markers[first['c']]
            if key in seen:outputs.pop(key,None)
            elif len(rest)==1 and rest[0]['t']=='Math' and rest[0]['c'][1].strip():
                outputs[key]=TexMathResult(tex=rest[0]['c'][1])
            seen.add(key)
        return {key:outputs.get(key,TexMathResult(reason='Pandoc 未返回对应的可编辑公式')) for key in markers.values()}

    def tex_import(self, expressions):
        """Convert unique OMML payloads without shifting results over empty formulas."""
        unavailable=None
        for batch in math_batches(expressions,limit=BATCH_OMML_BYTES):
            if not unavailable:
                try:
                    yield from self._tex_import_batch(batch).items()
                    continue
                except subprocess.TimeoutExpired:unavailable='Pandoc 公式转换超时'
                except OSError:unavailable='无法启动 Pandoc 公式转换'
                except (ValueError,KeyError,TypeError,IndexError,E.XMLSyntaxError):
                    yield from dict.fromkeys((key for _,key in batch),TexMathResult(reason='Pandoc 公式输出无法读取')).items()
                    continue
            yield from dict.fromkeys((key for _,key in batch),TexMathResult(reason=unavailable)).items()

    def mathml_many(self,expressions):
        body='<!doctype html><html><body>'+''.join('<p>'+x+'</p>' for x in expressions)+'</body></html>'
        result=subprocess.run([self.exe,'--fail-if-warnings','-f','html','-t','json'],input=body.encode('utf8'),capture_output=True,timeout=PANDOC_TIMEOUT_SECONDS)
        return self.math_values(result,len(expressions))
