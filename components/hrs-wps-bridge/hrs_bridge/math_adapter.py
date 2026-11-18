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
PREFIXABLE_UNITS = frozenset('m g s A K mol cd Hz N Pa J W C V F Ω Ω S Wb T H lm lx Bq Gy Sv kat rad sr L eV bar'.split())
UNIT_PREFIXES = 'q r y z a f p n μ µ m c d da h k M G T P E Z Y R Q'.split()
TEXT_UNITS = PREFIXABLE_UNITS | {prefix + unit for prefix in UNIT_PREFIXES for unit in PREFIXABLE_UNITS} | set(
    '% ‰ ° °C °F ℃ ℉ min h d rpm dB dBm dBc ppm ppb px Å atm'.split()
)
COMPOUND_TEXT_UNITS = frozenset({'r/min', 'r/s', 'lines/mm', 'lp/mm', 'grooves/mm'})
UNIT_ATOM = re.compile(r'([A-Za-zµμΩΩÅ]+|°[CF]?|[%‰℃℉])(?:\^[+−-]?[0-9]+)?')
UNIT_SEPARATOR = re.compile(r'\s*[/·⋅]\s*|\s+')
UNIT_POWER = re.compile(r'[+−-]?[0-9]+')
SCALAR = r'(?:[±∓+−-])?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)'
POWER10 = r'10\^[+−-]?[0-9]+'
SINGLE_QUANTITY = r'(?:' + POWER10 + r'|' + SCALAR + r'(?:[eE][+−-]?[0-9]+|\s*[×⋅]\s*' + POWER10 + r')?)'
QUANTITY_PREFIX = re.compile(SINGLE_QUANTITY + r'(?:\s*[~～∼–—-]\s*' + SINGLE_QUANTITY + r')?\s*')
UPRIGHT_UNIT = re.compile(r'\\(?:mathrm|textrm|textnormal|text|rm)(?![A-Za-z])')
STANDARD_MATH_OPS = frozenset({
    'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'arcsin', 'arccos', 'arctan',
    'sinh', 'cosh', 'tanh', 'coth', 'ln', 'log', 'exp', 'lim', 'limsup', 'liminf',
    'max', 'min', 'sup', 'inf', 'det', 'dim', 'ker', 'gcd', 'deg', 'arg', 'Pr',
    'hom', 'mod', 'bmod', 'pmod',
})
UPRIGHT_SENTINEL_RE = re.compile(r'(?:\\text\{HRSUPRIGHTSTART([A-Za-z]+)HRSUPRIGHTEND\}|HRSUPRIGHTSTART([A-Za-z]+)HRSUPRIGHTEND)')


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
    script: str | None = None


def inline_unit_text(omml, tex):
    """Project a complete unit or quantity into Word text, using parsed OMML."""
    runs = []

    def collect(node, script=None):
        tag = E.QName(node)
        if tag.namespace != M:
            return None
        kind = tag.localname
        if kind == 'r':
            texts = node.findall('m:t', N)
            if len(texts) != 1 or not texts[0].text:
                return None
            if any(child.tag not in (qn('m:t'), qn('m:rPr'), qn('w:rPr')) for child in node):
                return None
            text = texts[0].text
            math_style = node.find('m:rPr', N)
            if math_style is not None and any(child.tag not in (qn('m:sty'), qn('m:scr'), qn('m:nor')) for child in math_style):
                return None
            alphabet = node.find('m:rPr/m:scr', N)
            if alphabet is not None and alphabet.get(qn('m:val')) != 'roman':
                return None
            style = node.find('m:rPr/m:sty', N)
            normal = node.find('m:rPr/m:nor', N)
            upright = normal is not None and normal.get(qn('m:val'), '1') not in ('0', 'false', 'off')
            if style is not None and style.get(qn('m:val')) != 'p':
                return None
            if style is None and not upright and any(c.isalpha() for c in text):
                return None
            runs.append(MathTextRun(text, script))
            return text
        if kind in ('oMath', 'e', 'sup'):
            parts = []
            for child in node:
                part = collect(child, script)
                if part is None:
                    return None
                parts.append(part)
            return ''.join(parts) if parts else None
        if kind == 'sSup' and script is None:
            parts = [child for child in node if child.tag != qn('m:' + kind + 'Pr')]
            if [child.tag for child in parts] == [qn('m:e'), qn('m:sup')]:
                base = '' if len(parts[0]) == 0 else collect(parts[0])
                sup_start = len(runs)
                power = collect(parts[1], 'superscript')
                if base is not None and power is not None:
                    prior = ''.join(r.text for r in runs[:sup_start]).strip()
                    if power in ('°', '∘') and (re.fullmatch(SCALAR, base.strip()) or (not base.strip() and (not prior or re.fullmatch(SCALAR, prior)))):
                        runs[sup_start:] = [MathTextRun('°', None)]
                        return base + '°'
                    if UNIT_POWER.fullmatch(power) and (base.strip() == '10' or UNIT_ATOM.fullmatch(base.strip())):
                        return base + '^' + power
        return None

    notation = collect(omml)
    if notation is None:
        return None
    notation = notation.strip()
    quantity = QUANTITY_PREFIX.match(notation)
    units = notation[quantity.end():] if quantity else notation
    if not units:
        return None
    # A standalone upright symbol can still be a variable, such as \Omega.
    # A unit label with letters gains that meaning here only when marked upright.
    if quantity is None and any(char.isalpha() for char in units) and not UPRIGHT_UNIT.search(tex):
        return None
    if units in COMPOUND_TEXT_UNITS:
        return runs
    if all((atom := UNIT_ATOM.fullmatch(part)) and atom[1] in TEXT_UNITS for part in UNIT_SEPARATOR.split(units)):
        return runs
    return None


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
    def _restore_upright_tex(tex):
        return UPRIGHT_SENTINEL_RE.sub(lambda m: '\\mathrm{' + (m.group(1) or m.group(2)) + '}', tex)

    @staticmethod
    def _prepare_omml_upright(omml):
        root = deepcopy(omml)
        if 'HRSUPRIGHT' in ''.join(root.itertext()):
            return root

        def is_upright_ascii_run(node):
            if node.tag != qn('m:r'):
                return False
            texts = node.findall('m:t', N)
            if len(texts) != 1 or not texts[0].text or not (texts[0].text.isascii() and texts[0].text.isalpha()):
                return False
            rpr = node.find('m:rPr', N)
            if rpr is None or rpr.find('m:nor', N) is not None:
                return False
            sty = rpr.find('m:sty', N)
            if sty is None or sty.get(qn('m:val')) != 'p':
                return False
            scr = rpr.find('m:scr', N)
            return scr is None or scr.get(qn('m:val')) == 'roman'

        for parent in root.iter():
            if parent.tag == qn('m:fName') or not len(parent):
                continue
            children = list(parent)
            idx = 0
            while idx < len(children):
                if not is_upright_ascii_run(children[idx]):
                    idx += 1
                    continue
                end = idx + 1
                while end < len(children) and is_upright_ascii_run(children[end]):
                    end += 1
                group = children[idx:end]
                word = ''.join(n.find('m:t', N).text for n in group)
                if not (len(group) == 1 and word in STANDARD_MATH_OPS):
                    first = group[0]
                    rpr = first.find('m:rPr', N)
                    for sty in list(rpr.findall('m:sty', N)):
                        rpr.remove(sty)
                    rpr.insert(0, element('m:nor'))
                    first.find('m:t', N).text = f'HRSUPRIGHTSTART{word}HRSUPRIGHTEND'
                    for extra in group[1:]:
                        parent.remove(extra)
                idx = end
        return root

    @classmethod
    def math_values(cls, result, count):
        if result.returncode:raise BridgeError('Math conversion rejected: '+result.stderr.decode('utf8'))
        found=[]
        def walk(n):
            if isinstance(n,dict):
                if n.get('t')=='Math':found.append(cls._restore_upright_tex(n['c'][1]))
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
            paragraph._p.append(self._prepare_omml_upright(omml))
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
                outputs[key]=TexMathResult(tex=self._restore_upright_tex(rest[0]['c'][1]))
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
