"""Map the current HRS IR into the independently configured WPS template."""
import base64
from bisect import bisect_right
from copy import deepcopy
from io import BytesIO
from itertools import chain, takewhile
import html
import json
from pathlib import Path
import re
import tempfile
from typing import NamedTuple

from docx import Document
from docx.oxml.ns import qn
from docx.oxml import parse_xml
from docx.shared import Twips, Emu
from docx.text.paragraph import Paragraph
from lxml import etree as E
from PIL import Image

from .browser import call
from .math_adapter import INLINE_TEXT_FONT, MathAdapter, inline_unit_text
from .ooxml import N, W, element, zero_indent, field, native_hasher, provenance_path, drawing_extents, number_name
from .runtime import BridgeError, new_path, sha, source_contract_valid

INLINE_FORMAT = {
    'strong': ('bold', True), 'em': ('italic', True), 'del': ('strike', True),
    'hrsUnderline': ('underline', True), 'hrsSubscript': ('script', 'subscript'),
    'hrsSuperscript': ('script', 'superscript'),
}
TEXT_FALLBACK = 'WORD_TEXT_FALLBACK'
FALLBACK_REASONS = {
    'markup': '此 Markdown 或 HTML 片段没有对应的 Word 格式。',
    'nested_script': 'Word 文字上下标无法叠加。',
    'math_in_script': '行内公式位于 HTML 上下标内。',
    'math_unconverted': 'Pandoc 未生成完整的原生公式。',
    'math_invalid_output': '公式转换器未返回可核对的结果。',
    'math_unavailable': '公式转换器无法运行。',
    'math_timeout': '公式转换器等待超时。',
    'math_not_configured': '未配置 Pandoc。',
    'diagram_rendition': '流程图无法生成预览，已保留 Mermaid 原文。',
    'svg_rendition': 'SVG 无法生成预览，已保留原件路径。',
    'nested_note': '嵌套脚注保留引用及可找到的说明原文。',
    'note_image': '页底脚注中的图片保留为原文链接。',
    'empty_note': '脚注正文为空，已保留条目及其编号。',
    'broken_link': '普通链接的目标已失效，已保留链接原文。',
}
GRAPHIC_FIELDS = {'diagrams': 'diagram_sources', 'svgAssets': 'svg_sources'}


def word_tokens(value):
    if isinstance(value, list):
        for item in value:
            yield from word_tokens(item)
    elif isinstance(value, dict):
        if 'type' in value:
            yield value
        for item in value.values():
            if isinstance(item, (dict, list)):
                yield from word_tokens(item)


def note_keys(value):
    return dict.fromkeys(token['key'] for token in word_tokens(value) if token['type'] == 'hrsFootnoteRef')


def output_options(value=None):
    """Output policy is snapshot-bound and never rewrites Markdown."""
    value={} if value is None else value
    if not isinstance(value,dict) or set(value)-{'notes_mode','preserve_emphasis','inline_math_mode'}:raise BridgeError('Word 输出选项无效')
    mode=value.get('notes_mode','footnotes');keep=value.get('preserve_emphasis',True)
    if mode not in ('footnotes','references') or type(keep) is not bool:raise BridgeError('Word 脚注或正文强调选项无效')
    inline_math_mode = value.get('inline_math_mode', 'native')
    if inline_math_mode not in ('native', 'text'):
        raise BridgeError('Word 行内公式选项无效')
    return {'notes_mode':mode,'preserve_emphasis':keep,'inline_math_mode':inline_math_mode}


class Picture(NamedTuple):
    blob: bytes
    width: int
    height: int


class NoteBody:
    """Use python-docx paragraphs with the note's own OPC relationships."""
    def __init__(self, node, part):
        self._element=node
        self._part = part

    @property
    def part(self):
        return self._part


class Writer:
    def __init__(self, rt, source, template=None, accept_numbered_headings=False, *, model=None, prepare_only=False, options=None):
        from wps_pipeline.resolve_styles import inspect_template, open_template_body
        self.rt = rt
        self.options=output_options(options)
        self.source = Path(source).resolve()
        if self.source.is_file():
            self.source = self.source.parent
        self.raw = (self.source / 'report.md').read_bytes()
        from color_theme import read as read_color_theme
        from render_profile import read as read_profile, read_options, require_output
        self.source_profile=read_profile(self.source);self.source_options=read_options(self.source)
        color_theme = read_color_theme(self.source)
        self.source_sha256 = sha(self.raw)
        self.document_key = self.source_sha256[:16]
        self.ir = rt.analyze(self.raw, self.source / 'assets')
        if not self.ir['ok'] or not source_contract_valid(self.ir):
            raise BridgeError('HRS validation prevents compilation: ' + json.dumps(self.ir['diagnostics'], ensure_ascii=False))
        self.diagnostics=list(require_output(self.ir,'engineering',accept_numbered_headings))
        config = json.loads((rt.wps / 'config.json').read_text('utf-8-sig'))
        self.template = Path(template).resolve() if template is not None else rt.wps / config.get('template', 'templates/target_template.docx')
        # The current WPS configuration resolves the actual mother template.
        if not self.template.is_file():
            raise BridgeError('Configured WPS template does not exist: ' + str(self.template))
        self.template_sha256=sha(self.template.read_bytes())
        self.template_info = inspect_template(self.template)
        self.styles = self.template_info['styles']
        self.width = self.template_info['usable_width_twips']
        self.doc = Document(self.template)
        self.body = self.doc._element.body
        open_template_body(self.body,self.template_info)
        self.section_end = self.body[-1]
        self.front_xml = [E.tostring(node) for node in self.body[:-1]]
        self.heading_counts = [0] * 6
        self.source_heading_counts = [None] * 6
        self.accept_numbered_headings = bool(accept_numbered_headings)
        self.code_char_style = None
        self.math = {}
        self.inline_math_counts = {'converted': 0, 'retained': 0}
        self.note_part = None
        self.note_refs = {}
        self.literal_notes = set()
        self.current_parent = None
        self.current_block = None
        self.current_note = None
        self.line_offsets = None
        self.paragraph_styles = {}
        self.bookmark_id = max([int(n.get(qn('w:id'))) for n in self.body.iter(qn('w:bookmarkStart')) if (n.get(qn('w:id')) or '').isdigit()]+[0])
        self.tables = 0
        self.emf_parts = {}
        self.inline_text = []
        self.block_text = []
        self.block_starts = []
        self.inline_index = {}
        self.markdown_parts = {}
        self.origin_styles = {}
        self.word_origin = None
        self.image_layouts = {}
        origin_path = self.source / 'bridge-origin.json'
        if origin_path.is_file():
            origin = json.loads(origin_path.read_text('utf8'))
            if origin.get('schema') == 'hrs-word-origin-v1' and origin.get('markdown_sha256') == self.source_sha256:
                self.word_origin = origin
                self.origin_styles = {b['start']:b for b in origin.get('word_styles',[])}
                self.image_layouts = {b['id']:b for b in origin.get('image_layouts',[])}
        if self.word_origin is None:
            headings = [b for b in self.ir['blocks'] if b['type'] == 'heading']
            titles = [b for b in headings if b['level'] == 1]
            if len(titles) > 1 or (titles and headings[0] is not titles[0]):
                raise BridgeError('AMBIGUOUS_SINGLE_REPORT_TITLE: a single-report H1 title must precede its chapters; organize multiple reports explicitly')
        self.heading_output = {}
        snapshot_ids=set(self.ir['objects']['ids'])
        for index, b in enumerate(self.ir['blocks']):
            b['index'] = index  # snapshot-local bridge receipt, never a persistent source ID
            if b['type'] == 'markdown':
                self.markdown_parts[index] = self.project_markdown(b)
            if b['type']=='mermaid':
                base='fig-snapshot-'+str(index);key=base;suffix=0
                while key in snapshot_ids:
                    suffix+=1;key=base+'-'+str(suffix)
                snapshot_ids.add(key)
                b.update(word_figure_id=key,data={'kind':'mermaid','source':b['body'],'caption':''})
            texts = list(self.texts(b))
            if b['type'] == 'heading':
                style = self.heading_style(b)
                raw_title = b['text'].strip()
                if raw_title.startswith('**') and raw_title.endswith('**') and len(raw_title) > 4 and '**' not in raw_title[2:-2]:
                    raw_title = raw_title[2:-2].strip()
                text = raw_title if style == 'Title' else self.heading_text(b, int(style.split()[-1]), raw_title)
                self.heading_output[index] = (style, text)
                texts.append(text)
            for text in texts:
                if text not in self.inline_index:
                    self.inline_index[text] = len(self.inline_text)
                    self.inline_text.append(text)
        self.asset_hashes, svg_sources = {}, {}
        for name in sorted(self.ir['assets']):
            raw = self.read_asset(name)
            self.asset_hashes[name] = sha(raw)
            if name.lower().endswith('.svg'):
                svg_sources[name] = base64.b64encode(raw).decode('ascii')
        request={'schema':'hrs-word-model-request-v1','numbering_policy':'document-v2','render_options':self.source_options,'color_theme':color_theme,'markdown':self.raw.decode('utf8'),
                 'sections':self.block_text,'sectionStarts':self.block_starts,'inline':self.inline_text,
                 'template_sha256':self.template_sha256,'source_sha256':self.source_sha256,'output_options':self.options,
                 'assets':self.asset_hashes,'svg_sources':svg_sources,
                 'diagram_sources':{self.identity(b):b['data']['source'] for b in self.ir['blocks'] if b['type'] in ('figure','mermaid') and b['data']['kind']=='mermaid'}}
        request['request_sha256']=sha(json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8'))
        if prepare_only:
            self.model_request = request
        else:
            self.load_model(model if model is not None else call(rt,'model',**request), request)
        self.identities = {b['id']: b for b in self.ir['blocks'] if b.get('id')}

    def load_model(self, m, request):
        """The editor model is bound to this exact source/assets/template request."""
        if not isinstance(m,dict) or m.get('schema')!='hrs-word-browser-model-v1' or m.get('request_sha256')!=request['request_sha256'] or m.get('numbering_policy')!='document-v2':
            raise BridgeError('Word 页面模型与当前源稿、附件或模板快照不一致，请重新导出')
        if m.get('render_options')!=self.source_options:raise BridgeError('Word 页面模型与当前编号设置不一致，请重新导出')
        if m.get('output_options')!=self.options:raise BridgeError('Word 页面模型与当前输出策略不一致，请重新导出')
        for field,expected in (('tokens',len(self.block_text)),('inline',len(self.inline_text))):
            values=m.get(field)
            if not isinstance(values,list) or len(values)!=expected or any(not isinstance(v,list) for v in values):
                raise BridgeError('Word 页面模型的段落范围不完整')
        if not isinstance(m.get('profile'),dict) or not isinstance(m['profile'].get('diagnostics'),list):
            raise BridgeError('Word 页面模型缺少工程预检信息')
        notes=m.get('footnotes',{})
        if not isinstance(notes,dict) or len(notes)>1000 or any(not isinstance(k,str) or not isinstance(v,list) for k,v in notes.items()):
            raise BridgeError('Word 脚注模型无效')
        sources=m.get('footnote_sources',{})
        if not isinstance(sources,dict) or sources.keys()!=notes.keys() or any(not isinstance(v,str) for v in sources.values()):
            raise BridgeError('Word 脚注模型缺少来源文字')
        self.used_notes = note_keys([m['tokens'],m['inline']])
        for key in self.used_notes:
            if key not in notes:raise BridgeError('脚注未定义：'+str(key))
        errors=m.get('graphic_errors',{})
        if not isinstance(errors,dict) or errors.keys()-GRAPHIC_FIELDS.keys():
            raise BridgeError('Word 图形转换结果无效')
        self.graphics: dict[str, dict[str, Picture | str]] = {}
        for field,request_field in GRAPHIC_FIELDS.items():
            expected=request[request_field]
            values=m.get(field)
            failed=errors.get(field,{})
            if (not isinstance(values,dict) or not isinstance(failed,dict) or values.keys() & failed.keys()
                    or (values.keys() | failed.keys()) != expected.keys()):
                raise BridgeError('Word 图形预览不完整')
            if any(not isinstance(v,str) or not v.strip() or len(v)>240 for v in failed.values()):
                raise BridgeError('Word 图形失败信息无效')
            graphics = self.graphics[field] = dict(failed)
            for key, encoded in values.items():
                if not isinstance(encoded,str) or len(encoded)>16*1024*1024:raise BridgeError('Word 图形预览大小无效')
                try:
                    raw=base64.b64decode(encoded,validate=True)
                    with Image.open(BytesIO(raw)) as image:
                        if image.format!='PNG' or image.width*image.height>16000000:raise ValueError()
                        picture = Picture(raw, image.width, image.height)
                        image.verify()
                except (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError):
                    raise BridgeError('Word 图形预览不是有效的有界 PNG') from None
                graphics[key] = picture
        self.model = {'tokens':m['tokens'], 'inline':m['inline'], 'footnotes':notes, 'footnote_sources':sources}
        self.diagnostics.extend(m['profile']['diagnostics'])

    def read_asset(self, source):
        from asset_paths import normalize_asset, asset_file
        name = normalize_asset(source, originals=True)
        if name is None:
            raise BridgeError('Image must be inside project assets: ' + str(source))
        return asset_file(self.source / 'assets', name.removeprefix('assets/')).read_bytes()

    @staticmethod
    def texts(block):
        if block['type'] == 'heading':
            yield block['text']
        data = block.get('data', {})
        if 'caption' in data:
            yield data['caption']
        for item in data.get('images', []):
            yield item.get('caption', '')
        for row in data.get('rows', []) if isinstance(data.get('rows'), list) else []:
            for cell in row:
                if cell is not None:
                    yield cell['text'] if isinstance(cell, dict) else cell

    def diagnostic(self, code, block, message):
        self.diagnostics.append({'code': code, 'block': block['index'], 'id': block.get('id'), 'message': message})

    def line_at(self, offset):
        if self.line_offsets is None:
            self.line_offsets = [0]
            for line in self.raw.decode('utf8').splitlines(keepends=True):
                self.line_offsets.append(self.line_offsets[-1] + len(line.encode('utf-16-le')) // 2)
        return bisect_right(self.line_offsets, offset)

    @staticmethod
    def literal_run(p, raw, **formatting):
        run = p.add_run(raw.replace('\r\n', '\n').replace('\r', '\n'))
        Writer.format_run(run, **formatting)
        return run

    def write_fallback(self, p, raw, *, reason='markup', source_offset=None, formula=False, detail=None, **formatting):
        if not isinstance(raw, str) or not raw.strip():
            raise BridgeError('Word 页面模型缺少可保留的片段原文')
        run = self.literal_run(p, raw, **formatting)
        if formula:
            run.font.name = INLINE_TEXT_FONT
        item = {'code': TEXT_FALLBACK, 'severity': 'warning', 'kind': 'formula' if formula else 'markup',
                'reason': reason, 'message': FALLBACK_REASONS[reason], 'excerpt': ' '.join(raw.split())[:120]}
        if detail:
            item['detail'] = detail
        block = self.current_block
        if self.current_note is not None:
            item['footnote'] = self.current_note
        elif block is not None:
            item.update(block=block['index'], id=block.get('id'))
            if type(source_offset) is int and block['start'] <= source_offset < block['end']:
                item['line'] = self.line_at(source_offset)
            else:
                item.update(line=block['line'], end_line=self.line_at(block['end'] - 1))
        self.diagnostics.append(item)

    def paragraph(self, style='Normal', parent=None):
        from wps_pipeline.docx_formatting import style_paragraph
        parent = parent if parent is not None else self.current_parent
        if isinstance(parent, NoteBody) and style == 'Normal':
            style = 'Footnote Text'
        if style not in self.paragraph_styles:
            style_id = self.styles.get(style)
            if style_id is None:
                if style in self.doc.styles:
                    style_id = self.doc.styles[style].style_id
                elif style.startswith('HRS '):
                    raise BridgeError('Current Word template requires '+style+'; prepare template v0.3.11 before export')
                else:
                    style_id = style
            # Format an empty paragraph through the shared WPS adapter once.
            plain = E.Element(qn('w:p'))
            style_paragraph(plain, style_id)
            formatted = parse_xml(E.tostring(plain))
            if style in ('图形段', '图题', '表题', '表内正文', '公式'):
                zero_indent(formatted)
            self.paragraph_styles[style] = formatted
        node = deepcopy(self.paragraph_styles[style])
        if parent is None:
            self.section_end.addprevious(node)
            parent = self.doc._body
        else:
            parent._element.append(node)
        return Paragraph(node, parent)

    def inline(self, p, tokens, *, pre_wrap=False, **formatting):
        from report_contract import REF
        from reference_context import masked_context

        def write(text):
            self.run(p, text, pre_wrap=pre_wrap, **formatting)

        for t in tokens:
            kind = t['type']
            if kind in INLINE_FORMAT:
                name, value = INLINE_FORMAT[kind]
                style = dict(formatting)
                if name == 'script' and 'script' in style:
                    self.write_fallback(p, t.get('opening'), reason='nested_script', **style)
                    self.inline(p, t['tokens'], pre_wrap=pre_wrap, **style)
                    self.literal_run(p, t['closing'], **style)
                    continue
                if name not in ('bold', 'italic') or self.options['preserve_emphasis']:
                    style[name] = value
                self.inline(p, t['tokens'], pre_wrap=pre_wrap, **style)
            elif kind in ('text', 'escape'):
                if t.get('tokens'):
                    self.inline(p, t['tokens'], pre_wrap=pre_wrap, **formatting)
                    continue
                text = t.get('text', '')
                cursor = 0
                for ref in REF.finditer(masked_context(text)):
                    write(text[cursor:ref.start()])
                    target = self.identities.get(ref[2])
                    if target is None:
                        raise BridgeError('Reference target missing: ' + ref[2])
                    if ref[1] in ('fig', 'tbl'):
                        write('图 ' if ref[1] == 'fig' else '表 ')
                        field(p, ' REF ' + number_name(ref[2]) + ' \\h ', self.output_numbers[ref[2]])
                    elif ref[1] == 'sec':
                        field(p, ' REF ' + number_name(ref[2]) + ' \\h ', target['text'])
                    else:
                        if self.source_options['show_equation_numbers']:
                            write('式（')
                            field(p,' REF '+number_name(ref[2])+' \\h ',self.output_numbers[ref[2]])
                            write('）')
                        else:
                            field(p,' HYPERLINK \\l "'+number_name(ref[2])+'" ','该公式')
                    cursor = ref.end()
                write(text[cursor:])
            elif kind == 'codespan':
                run = self.run(p, t['text'], **formatting)
                if run is not None:
                    run._r.get_or_add_rPr().insert(0, element('w:rStyle', val=self.inline_code_style().style_id))
            elif kind == 'hrsMath':
                self.write_math(p, t['tex'], t['raw'], source_offset=t.get('source_offset'), **formatting)
            elif kind == 'hrsFootnoteRef':
                if self.current_note is None:
                    self.footnote(p,t['key'])
                else:
                    detail = None if t['key'] in self.model['footnotes'] else '该脚注标识没有定义。'
                    self.write_fallback(p,t['raw'],reason='nested_note',detail=detail,**formatting)
            elif kind == 'br':
                p.add_run().add_break()
            elif kind == 'link':
                from docx.opc.constants import RELATIONSHIP_TYPE as RT
                hyperlink = element('w:hyperlink')
                if t['href'].startswith('#object-'):
                    key=t['href'][8:]
                    if key not in self.identities:
                        self.write_fallback(p,t['raw'],reason='broken_link',**formatting)
                        continue
                    hyperlink.set(qn('w:anchor'),number_name(key));hyperlink.set(qn('w:history'),'1')
                else:hyperlink.set(qn('r:id'), p.part.relate_to(t['href'], RT.HYPERLINK, is_external=True))
                start = len(p._p)
                self.inline(p, t.get('tokens', [{'type': 'text', 'text': t['text']}]), pre_wrap=pre_wrap, **formatting)
                for node in list(p._p)[start:]:
                    hyperlink.append(node)
                p._p.append(hyperlink)
            elif kind == 'image':
                if self.current_parent is not None:
                    self.write_fallback(p,t['raw'],reason='note_image',**formatting)
                else:
                    self.picture(p, {'src': t['href'], 'alt': t.get('text', ''), 'raw':t['raw']}, self.width)
                    zero_indent(p._p)
            else:
                self.write_fallback(p, t.get('raw'), **formatting)

    def write_math(self, p, tex, raw, *, display=False, source_offset=None, **formatting):
        result = self.math[(tex, display)] if self.rt.pandoc else None
        reason = result.reason if result is not None else 'math_not_configured'
        if 'script' in formatting:
            reason = 'math_in_script'
        if reason is not None:
            self.write_fallback(p, raw, reason=reason, source_offset=source_offset, formula=True, **formatting)
            return
        if not display and self.options['inline_math_mode'] == 'text':
            pieces = inline_unit_text(result.node, tex)
            if pieces is not None:
                for piece in pieces:
                    run = p.add_run(piece.text)
                    run.font.name = INLINE_TEXT_FONT
                    self.format_run(run, **formatting, script=piece.script)
                self.inline_math_counts['converted'] += 1
                return
            self.inline_math_counts['retained'] += 1
        p._p.append(deepcopy(result.node))

    def write_note_body(self, key):
        self.current_note = key
        parent = self.current_parent
        if parent is None:
            container = self.body
            previous = self.section_end.getprevious()
        else:
            container = parent._element
            previous = container[-1] if len(container) else None
        try:
            self.markdown(self.model['footnotes'][key])
            self.write_nested_note_sources(key)
            added = previous.itersiblings() if previous is not None else iter(container)
            first = next((node for node in added if node.tag==qn('w:p')),None)
            if first is not None:
                return Paragraph(first, parent if parent is not None else self.doc._body)
            paragraph = self.paragraph()
            self.write_fallback(paragraph,f'[^{key}]:',reason='empty_note')
            return paragraph
        finally:
            self.current_note = None

    def write_nested_note_sources(self, key):
        sources = self.model['footnote_sources']
        notes = self.model['footnotes']
        pending = list(note_keys(notes[key]))
        for target in pending:
            if target == key or target in self.literal_notes or target not in sources:
                continue
            self.literal_notes.add(target)
            raw = sources[target]
            self.literal_run(self.paragraph(),f'[^{target}]:' + (' '+raw if raw else ''))
            pending.extend(note_keys(notes[target]))

    def footnote(self,p,key):
        """One native footnote per definition; later mentions are live NOTEREF."""
        from docx.opc.constants import RELATIONSHIP_TYPE as RT, CONTENT_TYPE as CT
        from docx.opc.part import XmlPart
        from docx.opc.packuri import PackURI
        from docx.enum.style import WD_STYLE_TYPE
        from docx.shared import Pt
        if self.current_parent is not None:raise BridgeError('Word 不支持脚注中嵌套脚注')
        if self.options['notes_mode']=='references':
            if key not in self.note_refs:self.note_refs[key]=('HR_'+self.document_key+'_'+sha(key.encode('utf8'))[:16],len(self.note_refs)+1)
            name,number=self.note_refs[key]
            self.run(p,'[');field(p,' REF '+name+' \\h ',number);self.run(p,']')
            return
        if key in self.note_refs:
            name,number=self.note_refs[key]
            self.note_bracket(p,'[')
            field(p,' NOTEREF '+name+' \\h \\f ',number)
            run=p._p[-1].find(qn('w:r'))
            props=element('w:rPr');props.append(element('w:rStyle',val=self.doc.styles['Footnote Reference'].style_id));props.append(element('w:vertAlign',val='superscript'));run.insert(0,props)
            self.note_bracket(p,']')
            return
        if self.note_part is None:
            for name,kind in [('Footnote Text',WD_STYLE_TYPE.PARAGRAPH),('Footnote Reference',WD_STYLE_TYPE.CHARACTER)]:
                if name in self.doc.styles:continue
                style=self.doc.styles.add_style(name,kind)
                if kind==WD_STYLE_TYPE.PARAGRAPH:
                    style.base_style=self.doc.styles['Normal'];style.font.size=Pt(10)
                    style.paragraph_format.first_line_indent=Twips(0)
                    style.paragraph_format.space_before=Pt(0);style.paragraph_format.space_after=Pt(0)
                    style.paragraph_format.line_spacing=1
                else:style.font.superscript=True
            try:
                old=self.doc.part.part_related_by(RT.FOOTNOTES)
                self.note_part=XmlPart(old.partname,old.content_type,parse_xml(old.blob),old.package)
                for rid,rel in old.rels.items():
                    self.note_part.rels.add_relationship(rel.reltype,rel.target_ref if rel.is_external else rel.target_part,rid,rel.is_external)
                for rel in list(self.doc.part.rels.values()):
                    if rel.reltype==RT.FOOTNOTES:self.doc.part.rels.add_relationship(rel.reltype,self.note_part,rel.rId)
            except KeyError:
                root=parse_xml(('<w:footnotes xmlns:w="'+N['w']+'" xmlns:r="'+N['r']+'"/>').encode())
                self.note_part=XmlPart(PackURI('/word/footnotes.xml'),CT.WML_FOOTNOTES,root,self.doc.part.package)
                self.doc.part.relate_to(self.note_part,RT.FOOTNOTES)
            root=self.note_part.element
            for kind,ident in [('separator',-1),('continuationSeparator',0)]:
                if not any(n.get(qn('w:type'))==kind for n in root):
                    note=element('w:footnote',type=kind,id=ident);para=element('w:p');run=element('w:r');run.append(element('w:'+kind));para.append(run);note.append(para);root.insert(0,note)
            self.next_footnote_id=max([int(n.get(qn('w:id'))) for n in root if (n.get(qn('w:id')) or '').lstrip('-').isdigit()]+[0])+1
            self.next_footnote_number=len(self.doc._element.xpath('//w:footnoteReference'))+1
        ident, number = self.next_footnote_id, self.next_footnote_number
        self.next_footnote_id += 1
        self.next_footnote_number += 1
        name='HF_'+self.document_key+'_'+sha(key.encode('utf8'))[:16]
        self.note_refs[key]=(name,number)
        run=element('w:r');props=element('w:rPr');props.append(element('w:rStyle',val=self.doc.styles['Footnote Reference'].style_id));run.append(props)
        run.append(element('w:footnoteReference',id=ident))
        self.note_bracket(p,'[');self.mark_inline(p,name,lambda:p._p.append(run));self.note_bracket(p,']')
        note=element('w:footnote',id=ident);self.note_part.element.append(note)
        self.current_parent=NoteBody(note,self.note_part)
        try:first=self.write_note_body(key)._p
        finally:self.current_parent=None
        marker=element('w:r');props=element('w:rPr');props.append(element('w:rStyle',val=self.doc.styles['Footnote Reference'].style_id));marker.append(props)
        marker.append(element('w:footnoteRef'))
        space=element('w:r');text=element('w:t');text.set('{http://www.w3.org/XML/1998/namespace}space','preserve');text.text=' ';space.append(text)
        at=1 if first.find(qn('w:pPr')) is not None else 0
        first.insert(at,marker);first.insert(at+1,space)

    def note_bracket(self,p,text):
        run=p.add_run(text);run.style=self.doc.styles['Footnote Reference']

    def write_references(self):
        if self.options['notes_mode']!='references' or not self.note_refs:return
        name='HB_'+self.document_key+'_references'
        begin=self.open_body_range(name)
        heading=self.paragraph('Heading 1');heading.add_run('参考文献')
        # The existing TOC consumes its real outline level; numId=0 keeps this
        # unnumbered heading out of the template's chapter sequence.
        pr=heading._p.get_or_add_pPr()
        for key in ('numPr','outlineLvl'):
            for old in list(pr.findall(qn('w:'+key))):pr.remove(old)
        number=element('w:numPr');number.append(element('w:numId',val=0));pr.append(number);pr.append(element('w:outlineLvl',val=0))
        for key,(target,index) in self.note_refs.items():
            first=self.write_note_body(key)
            marker=self.paragraph();self.run(marker,'[')
            self.mark_inline(marker,target,lambda:field(marker,' SEQ HRSReference \\* ARABIC ',index));self.run(marker,'] ')
            at=1 if first._p.find(qn('w:pPr')) is not None else 0
            for node in list(marker._p):
                if node.tag!=qn('w:pPr'):first._p.insert(at,node);at+=1
            marker._p.getparent().remove(marker._p)
            zero_indent(first._p)
        end=self.close_body_range(begin)
        return {'kind':'references','bookmark':name}, self.range_nodes(begin, end)

    @staticmethod
    def format_run(run, *, bold=False, italic=None, strike=False, underline=False, script=None):
        if bold:
            run.bold = True
        if italic is not None:
            run.italic = italic
        if strike:
            run.font.strike = True
        if underline:
            run.underline = True
        if script == 'subscript':
            run.font.subscript = True
        elif script == 'superscript':
            run.font.superscript = True

    def inline_code_style(self):
        if self.code_char_style is None:
            from docx.enum.style import WD_STYLE_TYPE
            name = 'HRS Code Char'
            if name in self.doc.styles:
                style = self.doc.styles[name]
            else:
                style = self.doc.styles.add_style(name, WD_STYLE_TYPE.CHARACTER)
                style.font.name = 'Consolas'
                rpr = style.element.get_or_add_rPr()
                rpr.append(element('w:rFonts', ascii='Consolas', hAnsi='Consolas', cs='Consolas'))
            self.code_char_style = style
        return self.code_char_style

    @staticmethod
    def run(p, text, *, pre_wrap=False, **formatting):
        if text:
            # Marked's soft source newline is whitespace; only its explicit br
            # token is a native line break. This also prevents a justified REF
            # line from stretching its number to the right margin in WPS.
            text=html.unescape(text)
            run = p.add_run(text.replace('\r\n','\n').replace('\r','\n') if pre_wrap else text.replace('\r\n',' ').replace('\n',' '))
            Writer.format_run(run, **formatting)
            return run
        return None

    def rich(self, p, text, pre_wrap=False):
        self.inline(p, self.model['inline'][self.inline_index[text]], pre_wrap=pre_wrap)

    def markdown(self, tokens, level=0, list_style=None, quote_lines=False):
        for token in tokens:
            kind = token['type']
            if kind == 'space':
                continue
            if kind in ('paragraph', 'text'):
                p = self.paragraph()
                if quote_lines:
                    from docx.enum.text import WD_ALIGN_PARAGRAPH
                    p.alignment=WD_ALIGN_PARAGRAPH.LEFT
                    zero_indent(p._p)
                    qpr = p._p.get_or_add_pPr()
                    qbdr = qpr.find(qn('w:pBdr'))
                    if qbdr is None:
                        qbdr = element('w:pBdr')
                        qpr.append(qbdr)
                    qbdr.append(element('w:left', val='single', sz=12, space=8, color='94A3B8'))
                    qind = qpr.find(qn('w:ind'))
                    if qind is not None:
                        qind.set(qn('w:left'), '360')
                self.inline(p, token.get('tokens', [{'type': 'text', 'text': token.get('text', '')}]),pre_wrap=quote_lines)
            elif kind == 'blockquote':
                self.markdown(token['tokens'], level,quote_lines=True)
            elif kind == 'hrsAbstract':
                for part in token['tokens']:
                    if part['type']=='space':continue
                    p=self.paragraph()
                    self.inline(p,part.get('tokens',[{'type':'text','text':part.get('text','')}]))
                    # The label alone is bold. Body keeps the template's normal
                    # paragraph/font; HRS Abstract inherits chapter boldness.
                    import re
                    for run in p.runs:
                        match=re.match(r'^(\s*摘要[:：])',run.text)
                        if match:
                            from docx.text.run import Run
                            suffix=run.text[match.end():]
                            if suffix:
                                rest=Run(deepcopy(run._r),p);rest.text=suffix;run._r.addnext(rest._r)
                            run.text=match[1];run.bold=True
                        if run.text:break
            elif kind == 'code':
                p = self.paragraph('HRS Code')
                p.add_run(token['text'])
                zero_indent(p._p)
            elif kind == 'hr':
                p = self.paragraph()
                pr = p._p.get_or_add_pPr()
                borders = element('w:pBdr')
                borders.append(element('w:bottom', val='single', sz=4, color='auto'))
                pr.append(borders)
            elif kind == 'hrsStyledList':
                self.markdown(token['tokens'], level, token['style'])
            elif kind == 'list':
                num = self.list_numbering(token.get('ordered', False), token.get('start') or 1, list_style)
                for item in token['items']:
                    if item.get('task'):
                        children = item.get('tokens') or []
                        if not any(c.get('type') == 'list' for c in children):
                            self.write_fallback(self.paragraph(), item.get('raw'))
                            continue
                        task_mark = '- [x] ' if item.get('checked') else '- [ ] '
                        wrote_head = False
                        for child in children:
                            if child['type'] == 'space':
                                continue
                            if child['type'] == 'list':
                                self.markdown([child], level + 1)
                            else:
                                head_raw = (task_mark if not wrote_head else '') + (child.get('raw') or child.get('text') or '')
                                wrote_head = True
                                self.write_fallback(self.paragraph(), head_raw)
                        if not wrote_head:
                            self.write_fallback(self.paragraph(), item.get('raw'))
                        continue
                    for child in item['tokens']:
                        if child['type'] == 'space': continue
                        if child['type'] == 'list':
                            self.markdown([child], level + 1)
                            continue
                        if child['type'] not in ('text', 'paragraph'):
                            self.write_fallback(self.paragraph(), child.get('raw'))
                            continue
                        p = self.paragraph()
                        self.inline(p, child.get('tokens', [{'type': 'text', 'text': child.get('text', '')}]))
                        pr = p._p.get_or_add_pPr()
                        number = element('w:numPr')
                        number.extend([element('w:ilvl', val=min(level, 8)), element('w:numId', val=num)])
                        pr.append(number)
                        zero_indent(p._p)
                        indent = pr.find(qn('w:ind'))
                        indent.set(qn('w:left'), str((level + 1) * 420))
                        indent.set(qn('w:hanging'), '210')
            else:
                self.write_fallback(self.paragraph(), token.get('raw'))

    def list_numbering(self, ordered, start, style=None):
        # Project the five existing HRS display styles into Word numbering.
        # The original Marked extension owns the source syntax and list parsing.
        styles = {'bullet':('bullet','•'), 'decimal':('decimal','%n.'),
                  'lower-alpha':('lowerLetter','%n.'), 'paren-decimal':('decimal','（%n）'),
                  'paren-lower-alpha':('lowerLetter','（%n）')}
        if style is not None and style not in styles: raise BridgeError('Unsupported HRS list display style')
        fmt, label = styles[style] if style else (('decimal','%n.') if ordered else ('bullet','•'))
        abstract = element('w:abstractNum')
        abstract.append(element('w:multiLevelType', val='multilevel'))
        for level in range(9):
            lvl = element('w:lvl', ilvl=level)
            lvl.extend([element('w:start', val=start), element('w:numFmt', val=fmt),
                        element('w:lvlText', val=label.replace('%n','%'+str(level+1)))])
            abstract.append(lvl)
        return self.add_numbering(abstract)

    def initialize_numbering(self):
        root = self.numbering = self.doc.part.numbering_part.element
        abstracts = root.findall(qn('w:abstractNum'))
        numbers = root.findall(qn('w:num'))
        self.next_abstract_id = max((int(node.get(qn('w:abstractNumId'))) for node in abstracts), default=-1) + 1
        self.next_number_id = max((int(node.get(qn('w:numId'))) for node in numbers), default=0) + 1
        self.numbering_cleanup = root.find(qn('w:numIdMacAtCleanup'))
        self.first_number = numbers[0] if numbers else self.numbering_cleanup

    def add_numbering(self, abstract):
        abstract_id, number_id = self.next_abstract_id, self.next_number_id
        self.next_abstract_id += 1
        self.next_number_id += 1
        abstract.set(qn('w:abstractNumId'), str(abstract_id))
        number = element('w:num', numId=number_id)
        number.append(element('w:abstractNumId', val=abstract_id))
        # OOXML puts all abstract definitions before instances and cleanup.
        if self.first_number is None:
            self.numbering.append(abstract)
        else:
            self.first_number.addprevious(abstract)
        if self.numbering_cleanup is None:
            self.numbering.append(number)
        else:
            self.numbering_cleanup.addprevious(number)
        if self.first_number is None or self.first_number is self.numbering_cleanup:
            self.first_number = number
        return number_id

    def bind_heading_numbering(self):
        """Reuse a matching template outline or bind the six output styles."""
        root = self.numbering
        # v0.3.11 owns the live outline. Reuse it without rebuilding definitions.
        bindings=[self.doc.styles['Heading '+str(i)].element.find('.//'+qn('w:numId')) for i in range(1,7)]
        if all(n is not None for n in bindings) and len({n.get(qn('w:val')) for n in bindings})==1:
            number=root.find(qn('w:num')+'[@'+qn('w:numId')+'="'+bindings[0].get(qn('w:val'))+'"]')
            aid=number.find(qn('w:abstractNumId')) if number is not None else None
            abstract=root.find(qn('w:abstractNum')+'[@'+qn('w:abstractNumId')+'="'+aid.get(qn('w:val'))+'"]') if aid is not None else None
            levels=abstract.findall(qn('w:lvl')) if abstract is not None else []
            if len(levels)==6 and all(level.find(qn('w:lvlText')) is not None and level.find(qn('w:lvlText')).get(qn('w:val'))=='.'.join('%'+str(j) for j in range(1,i+2)) for i,level in enumerate(levels)):
                return
        abstract = element('w:abstractNum')
        abstract.append(element('w:multiLevelType', val='multilevel'))
        abstract.append(element('w:name', val='HRS Template Headings'))
        heading_styles = []
        for level in range(6):
            style = self.doc.styles['Heading ' + str(level + 1)]
            heading_styles.append(style)
            lvl = element('w:lvl', ilvl=level)
            lvl.extend([element('w:start', val=1), element('w:numFmt', val='decimal')])
            if level:
                lvl.append(element('w:lvlRestart', val=level))
            lvl.extend([element('w:pStyle', val=style.style_id), element('w:suff', val='space'),
                        element('w:lvlText', val='.'.join('%' + str(i) for i in range(1, level + 2))),
                        element('w:lvlJc', val='left')])
            p = element('w:p')
            zero_indent(p)
            lvl.append(p.get_or_add_pPr())
            rp = element('w:rPr')
            rp.append(element('w:rFonts', ascii='Times New Roman', hAnsi='Times New Roman'))
            lvl.append(rp)
            abstract.append(lvl)
        number_id = self.add_numbering(abstract)
        for level, style in enumerate(heading_styles):
            np = style.element.get_or_add_pPr().get_or_add_numPr()
            np.get_or_add_ilvl().val = level
            np.get_or_add_numId().val = number_id

    def heading_style(self, block):
        origin = self.origin_styles.get(block['start'], {})
        if origin.get('source_sha256') == sha(block['source'].encode('utf8')):
            style=origin.get('style')
            if style=='Title' or style in ['Heading '+str(i) for i in range(1,7)]:return style
        if self.word_origin and any(v.get('projection') for v in self.origin_styles.values()):
            return 'Title' if block['level']==1 else 'Heading '+str(block['level']-1)
        if self.word_origin is not None:
            return 'Heading ' + str(block['level'])
        # HRS single report: H1 is its title; H2 starts the first body level.
        return 'Title' if block['level'] == 1 else 'Heading ' + str(block['level'] - 1)

    def project_markdown(self, block):
        """Split only verified derived ranges; all other content uses the original HRS lexer."""
        raw=block['source'].encode('utf-16-le');cursor=0;parts=[]
        def markdown(data):
            if data:
                parts.append(('markdown',len(self.block_text)))
                self.block_text.append(data.decode('utf-16-le'))
                self.block_starts.append(block['start']+cursor//2)
        for start,hint in sorted(self.origin_styles.items()):
            if hint.get('projection')!='heading-list' or not block['start']<=start<block['end']:continue
            lo=(start-block['start'])*2;hi=(hint['end']-block['start'])*2
            source=raw[lo:hi].decode('utf-16-le')
            if lo<cursor or hi>len(raw) or sha(source.encode('utf8'))!=hint['source_sha256'] or not source.startswith('- '):
                raise BridgeError('Invalid source-bound heading projection')
            markdown(raw[cursor:lo]);text=source[2:].rstrip('\r\n')
            style=hint['style']
            if style!='Heading 6':raise BridgeError('Unsupported overflow heading role')
            text=self.heading_text(dict(block,text=text),6)
            if text not in self.inline_index:
                self.inline_index[text]=len(self.inline_text);self.inline_text.append(text)
            parts.append((style,text));cursor=hi
        markdown(raw[cursor:]);return parts

    def _next_peer_heading_numbers(self, start_index, level):
        for item in self.ir['blocks'][start_index + 1:]:
            if item.get('type') != 'heading':
                continue
            style = self.heading_style(item)
            if style == 'Title':
                continue
            item_level = int(style.split()[-1])
            if item_level < level:
                return None
            if item_level == level:
                raw = item.get('text', '').strip()
                if raw.startswith('**') and raw.endswith('**') and len(raw) > 4 and '**' not in raw[2:-2]:
                    raw = raw[2:-2].strip()
                parsed, _ = self._heading_prefix(raw)
                return parsed['numbers'] if parsed else None
        return None

    @staticmethod
    def _heading_prefix(text):
        from .math_adapter import COMPOUND_TEXT_UNITS, QUANTITY_PREFIX, TEXT_UNITS, UNIT_ATOM
        from wps_pipeline.numbered_candidates import numeric_expression,manual_prefix

        def is_leading_quantity(raw):
            literal = raw.lstrip()
            quantity = QUANTITY_PREFIX.match(literal)
            if not quantity or quantity[0].rstrip().endswith('.'):
                return False
            rest = literal[quantity.end():]
            for cu in COMPOUND_TEXT_UNITS:
                if rest.startswith(cu) and (len(rest) == len(cu) or not rest[len(cu)].isalpha()):
                    return True
            unit = UNIT_ATOM.match(literal, quantity.end())
            return bool(unit and unit[1] in TEXT_UNITS)

        parsed = manual_prefix(text)
        expression = numeric_expression(text)
        if parsed is None:
            # Handle multi-level chapter paths or delimited numbers followed by
            # a numeric title (e.g. "1.7 0 级与低阶", "8.5 60 mm 光束").
            m = re.match(r'^\s*(\d+(?:\.\d+)+[.)、]?|\d+[.)、])[ \t]+(?=\d)', text)
            if m and not is_leading_quantity(text):
                nums = [int(x) for x in re.findall(r'\d+', m.group(1))]
                if 1 <= len(nums) <= 6:
                    form = 'decimal_path' if '.' in m.group(1) else 'integer_delimited:' + m.group(1)[-1]
                    return {'numbers': nums, 'prefix': text[:m.end()], 'form': form}, 'ambiguous_numeric_text'
        if expression is None:
            return parsed, expression
        if parsed:
            if is_leading_quantity(text):
                return None, 'numeric_quantity'
            form = parsed['form']
            if form.startswith('integer_delimited:') or (form == 'decimal_path' and parsed['prefix'][-1].isspace()):
                return parsed, 'ambiguous_numeric_text'
        return None, expression

    def heading_text(self, block, level, clean_text=None):
        self.heading_counts[level - 1] += 1
        self.heading_counts[level:] = [0] * (6 - level)
        self.source_heading_counts[level:] = [None] * (6 - level)
        text = clean_text if clean_text is not None else block['text']
        if text.startswith('**') and text.endswith('**') and len(text) > 4 and '**' not in text[2:-2]:
            text = text[2:-2].strip()
        prefix = '.'.join(map(str, self.heading_counts[:level])) + ' '
        parsed, expression = self._heading_prefix(text)
        matched = False
        series_proven = False
        if parsed and len(parsed['numbers']) == level:
            nums = parsed['numbers']
            if nums == self.heading_counts[:level]:
                prefix = parsed['prefix']
                matched = True
            prev = self.source_heading_counts[level - 1]
            if level == 1:
                if (prev is None and nums[0] in (0, 1)) or (prev is not None and nums[0] == prev + 1):
                    prefix = parsed['prefix']
                    matched = True
                    series_proven = prev is not None or self._next_peer_heading_numbers(block.get('index', 0), 1) == [nums[0] + 1]
            else:
                parent = self.source_heading_counts[:level - 1]
                if all(v is not None for v in parent) and nums[:-1] == parent and ((prev is None and nums[-1] in (0, 1)) or (prev is not None and nums[-1] == prev + 1)):
                    prefix = parsed['prefix']
                    matched = True
                    series_proven = True
        if all(self.heading_counts[:level]) and (matched or text.startswith(prefix)):
            if expression is None or (expression == 'ambiguous_numeric_text' and series_proven and self.accept_numbered_headings):
                if matched:
                    self.source_heading_counts[level - 1] = parsed['numbers'][-1]
                self.diagnostic('HEADING_LITERAL_PREFIX_TO_NATIVE', block,
                                'Exact chapter prefix moved to native Word outline numbering; source is retained.')
                return text[len(prefix):]
        if expression is not None:
            self.diagnostic('HEADING_NUMERIC_TEXT_RETAINED', block,
                            'Numeric or ambiguous title text is retained; no chapter prefix deletion was inferred.')
        return text

    def picture_source(self, p, data):
        from asset_paths import normalize_asset
        source = data.get('src')
        if not source:
            raise BridgeError('Word 图片缺少来源路径')
        raster = source
        if Path(source).suffix.lower() == '.svg':
            key = normalize_asset(source)
            if key is None:
                raise BridgeError('Image must be inside project assets: ' + str(source))
            rendition = self.graphics['svgAssets'].get(key)
            if rendition is None:
                raise BridgeError('Word 页面模型缺少 SVG 预览：'+key)
            if isinstance(rendition, Picture):
                return rendition
            raster = data.get('rasterFallback')
            if raster is None:
                raw = data.get('raw') or f"![{data.get('alt') or data.get('caption') or ''}]({source})"
                self.write_fallback(p, raw, reason='svg_rendition', detail=rendition)
                return None
            self.diagnostic('SVG_RASTER_FALLBACK', self.current_block, 'SVG 转换失败，使用文稿声明的位图预览。')
        blob = self.read_asset(raster)
        with Image.open(BytesIO(blob)) as img:
            # python-docx cannot embed WebP; this is a declared display rendition.
            if img.format not in ('PNG', 'JPEG', 'GIF', 'BMP', 'TIFF'):
                buffer = BytesIO()
                img.convert('RGBA').save(buffer, format='PNG')
                blob = buffer.getvalue()
            return Picture(blob, img.width, img.height)

    def picture(self, p, data, width, *, rendition=None):
        from asset_paths import normalize_asset
        if rendition is None:
            rendition = self.picture_source(p, data)
            if rendition is None:
                return
        blob, w, h = rendition
        target_width = max(1, min(width, round(10000 * w / h)))
        shape = p.add_run().add_picture(BytesIO(blob), width=Twips(target_width))
        source = data.get('src')
        layout = self.image_layouts.get(data.get('id'))
        source_digest = self.asset_hashes.get(normalize_asset(source))
        if layout and source_digest is not None and source_digest == layout['source_sha256']:
            original_width,original_height=layout['width_emu'],layout['height_emu']
            if not isinstance(original_width,int) or not isinstance(original_height,int) or min(original_width,original_height)<=0:
                raise BridgeError('Invalid Word-origin image extent')
            scale=min(1,width*635/original_width,10000*635/original_height)
            shape.width=Emu(round(original_width*scale));shape.height=Emu(round(original_height*scale))
        shape._inline.docPr.set('descr', data.get('alt', data.get('caption', '')))
        if source:
            shape._inline.docPr.set('name', source)
        original = data.get('sourceAsset')
        if original and original.lower().endswith('.emf'):
            from docx.opc.packuri import PackURI
            from docx.opc.part import Part
            from docx.opc.constants import RELATIONSHIP_TYPE as RT
            emf = self.read_asset(original)
            digest = sha(emf)
            if digest not in self.emf_parts:
                self.emf_parts[digest] = Part(PackURI('/word/media/hrs_' + digest[:16] + '.emf'), 'image/x-emf', emf, self.doc.part.package)
            rid = self.doc.part.relate_to(self.emf_parts[digest], RT.IMAGE)
            shape._inline.xpath('.//a:blip')[0].set(qn('r:embed'), rid)

    @staticmethod
    def identity(block):
        # Word needs a local bookmark even for anonymous GFM tables. This value
        # never becomes an HRS ID and is meaningful only inside this snapshot.
        return block.get('id') or block.get('word_figure_id') or 'snapshot-table-'+str(block['index'])

    def mark_inline(self, p, name, callback):
        self.bookmark_id += 1
        ident = self.bookmark_id
        p._p.append(element('w:bookmarkStart', id=ident, name=name))
        callback()
        p._p.append(element('w:bookmarkEnd', id=ident))

    def caption(self, b, figure):
        p = self.paragraph('图题' if figure else '表题')
        p.add_run('图 ' if figure else '表 ')
        key=self.identity(b)
        self.mark_inline(p, number_name(key), lambda: field(p,
            ' SEQ ' + ('图' if figure else '表') + ' \\* ARABIC ', self.output_numbers[key]))
        text = b['data'].get('caption', '')
        if text:
            p.add_run(' ')
            self.rich(p,text)
        return p

    def data_table(self, b):
        from wps_pipeline.docx_formatting import style_table
        d = b['data']
        self.caption(b, False)
        rows = d['rows']
        table = self.doc.add_table(rows=len(rows), cols=len(rows[0]))
        for ri, row in enumerate(rows):
            for ci, cell in enumerate(row):
                if cell is None: continue
                target = table.cell(ri, ci)
                rs = cell.get('rowspan', 1) if isinstance(cell, dict) else 1
                cs = cell.get('colspan', 1) if isinstance(cell, dict) else 1
                if rs > 1 or cs > 1:
                    target = target.merge(table.cell(ri + rs - 1, ci + cs - 1))
                text = cell['text'] if isinstance(cell, dict) else cell
                for p in list(target._tc.findall(qn('w:p'))): target._tc.remove(p)
                p = target.add_paragraph()
                self.rich(p, text, pre_wrap=True)
        widths = d.get('columnWidths')
        if widths:
            for col, width in zip(table._tbl.tblGrid, widths): col.set(qn('w:w'), str(round(float(width)*100)))
        plain = E.fromstring(E.tostring(table._tbl))
        non_math_runs = plain.xpath('.//w:r[not(ancestor::m:oMath)]', namespaces=N)
        saved_run_props = [
            [deepcopy(c) for c in (r.find(qn('w:rPr')) if r.find(qn('w:rPr')) is not None else ()) if E.QName(c).localname in ('rStyle', 'rFonts')]
            for r in non_math_runs
        ]
        style_table(plain, self.styles, self.width)
        for r, extras in zip(plain.xpath('.//w:r[not(ancestor::m:oMath)]', namespaces=N), saved_run_props):
            if not extras:
                continue
            rp = r.find(qn('w:rPr'))
            if rp is None:
                rp = E.Element(qn('w:rPr'))
                r.insert(0, rp)
            for c in reversed(extras):
                rp.insert(0, c)
        formatted = parse_xml(E.tostring(plain))
        table._tbl.getparent().replace(table._tbl, formatted)
        for p in formatted.xpath('.//w:p'): zero_indent(p)
        # Explicit per-column source alignment survives template styling; absent
        # values continue to inherit the mother's table paragraph style.
        if d.get('align'):
            for row in formatted.findall(qn('w:tr')):
                column=0
                for cell in row.findall(qn('w:tc')):
                    span=cell.find(qn('w:tcPr')+'/'+qn('w:gridSpan'))
                    choice=d['align'][column] if column<len(d['align']) else None
                    if choice:
                        for p in cell.findall(qn('w:p')):
                            props=p.get_or_add_pPr()
                            for old in list(props):
                                if old.tag==qn('w:jc'):props.remove(old)
                            props.append(element('w:jc',val=choice))
                    column+=int(span.get(qn('w:val'))) if span is not None else 1

    def group(self, b):
        d = b['data']
        cols = d['columns']
        rows = d.get('rows') or (len(d['images']) + cols - 1) // cols
        # Each logical image row has a separate caption row. A shared row
        # boundary aligns child captions even when the pictures differ in height.
        table = self.doc.add_table(rows=rows * 2, cols=cols)
        table.autofit = False
        pr = table._tbl.tblPr
        for child in list(pr): pr.remove(child)
        pr.extend([element('w:tblW', w=self.width, type='dxa'), element('w:jc', val='center'), element('w:tblLayout', type='fixed'), element('w:tblInd', w=0, type='dxa')])
        borders = element('w:tblBorders')
        for edge in ('top','left','bottom','right','insideH','insideV'): borders.append(element('w:'+edge, val='nil'))
        pr.append(borders)
        margins = element('w:tblCellMar')
        for edge, value in [('top',65),('bottom',65),('left',85),('right',85)]: margins.append(element('w:'+edge, w=value, type='dxa'))
        pr.append(margins)
        widths = [self.width // cols] * cols
        widths[-1] += self.width - sum(widths)
        for col, width in zip(table._tbl.tblGrid, widths): col.set(qn('w:w'), str(width))
        for row_index in range(rows):
            image_row, caption_row = table.rows[row_index * 2:row_index * 2 + 2]
            # Keep each pair together when it fits, without chaining the whole
            # group or imposing exact heights that would clip a long caption.
            for row in (image_row, caption_row):
                row._tr.get_or_add_trPr().append(element('w:cantSplit'))
            for column, (cell, caption_cell) in enumerate(zip(image_row.cells, caption_row.cells)):
                for target, alignment in ((cell, 'bottom'), (caption_cell, 'top')):
                    target.width = Twips(widths[column])
                    target._tc.get_or_add_tcPr().append(element('w:vAlign', val=alignment))
                    for old in list(target._tc.findall(qn('w:p'))): target._tc.remove(old)
                p = self.paragraph('图形段', cell)
                p.paragraph_format.keep_with_next = True
                caption = self.paragraph('图题', caption_cell)
                caption.paragraph_format.keep_with_next = False
                i = row_index * cols + column
                if i < len(d['images']):
                    img = d['images'][i]
                    self.picture(p, img, widths[column] - 170)
                    if d.get('showSubfigureLabels', True): caption.add_run('(' + chr(97+i) + ')')
                    if img.get('caption'):
                        if d.get('showSubfigureLabels', True): caption.add_run(' ')
                        self.rich(caption,img['caption'])
        self.caption(b, True)

    def space_after_data_table(self, nodes):
        """Use the template's existing caption gap; do not create source/spacer paragraphs."""
        gap=self.doc.styles['表题'].paragraph_format.space_before
        if gap is None or gap<=0:return
        first=next((n for n in nodes if n.tag in (qn('w:p'),qn('w:tbl'))),None)
        if first is None:return
        paragraphs=[first] if first.tag==qn('w:p') else first.xpath('./w:tr[1]/w:tc/w:p[1]')
        for node in paragraphs:
            p=Paragraph(node,self.doc._body)
            before=p.paragraph_format.space_before
            style=p.style;seen=set()
            while before is None and style is not None and style.style_id not in seen:
                seen.add(style.style_id);before=style.paragraph_format.space_before;style=style.base_style
            if (before or 0)<gap:p.paragraph_format.space_before=gap

    def prepare_math(self):
        """Consume the existing page tokens; do not parse source formulas again."""
        if not self.rt.pandoc:
            return
        notes = [self.model['footnotes'][key] for key in self.used_notes]
        requests = ((token['tex'],False) for token in word_tokens([self.model['tokens'],self.model['inline'],notes])
                    if token['type']=='hrsMath')
        displays = ((block['latex'], True) for block in self.ir['blocks'] if block['type'] == 'equation')
        self.math = MathAdapter(self.rt).native_many(chain(requests, displays))

    def open_body_range(self, name):
        self.bookmark_id += 1
        node = element('w:bookmarkStart', id=self.bookmark_id, name=name)
        self.section_end.addprevious(node)
        return node

    def close_body_range(self, begin):
        end = element('w:bookmarkEnd', id=begin.get(qn('w:id')))
        self.section_end.addprevious(end)
        return end

    @staticmethod
    def range_nodes(begin, end):
        return list(takewhile(lambda node: node is not end, begin.itersiblings()))

    def write(self, output):
        self.prepare_math()
        self.initialize_numbering()
        self.bind_heading_numbering()
        self.output_numbers = {}
        # Output sequence is a WPS profile concern, never a replacement HRS numbering rule.
        table_number = 0
        for b in self.ir['blocks']:
            if b['type'] == 'table':
                table_number += 1
                self.output_numbers[self.identity(b)] = table_number
            elif b['type'] in ('figure','mermaid','image-group','equation'):
                self.output_numbers[self.identity(b)] = b['number']
        scope_name='HBD_'+self.document_key
        scope = self.open_body_range(scope_name)
        regions = []
        previous_data_table=False
        for b in self.ir['blocks']:
            self.current_block = b
            bookmark = 'HB_' + self.document_key + '_' + str(b['index'])
            begin = self.open_body_range(bookmark)
            kind = b['type']
            if kind == 'heading':
                style, heading_text = self.heading_output[b['index']]
                p = self.paragraph(style)
                if b.get('id'):
                    self.mark_inline(p, number_name(b['id']), lambda: self.rich(p, heading_text))
                else: self.rich(p, heading_text)
            elif kind == 'markdown':
                for role,value in self.markdown_parts[b['index']]:
                    if role=='markdown':self.markdown(self.model['tokens'][value])
                    else:self.rich(self.paragraph(role),value)
            elif kind == 'code':
                p=self.paragraph('HRS Code')
                # python-docx maps both CR and LF to separate w:br nodes. A
                # source CRLF is one logical line break, never two Word breaks.
                p.add_run(b['body'].replace('\r\n','\n').replace('\r','\n'))
                zero_indent(p._p)
            elif kind == 'equation':
                p = self.paragraph('公式')
                key=self.identity(b)
                left, right = ('\\[', '\\]') if b['delimiter'] == 'bracket' else ('$$', '$$')
                def write_equation():
                    self.write_math(p, b['latex'], left + b['latex'] + right, display=True)
                if self.source_options['show_equation_numbers']:
                    from docx.enum.text import WD_TAB_ALIGNMENT
                    p.paragraph_format.tab_stops.add_tab_stop(Twips(self.width),WD_TAB_ALIGNMENT.RIGHT)
                    write_equation();p.add_run('\t（')
                    self.mark_inline(p,number_name(key),lambda:field(p,' SEQ 公式 \\* ARABIC ',self.output_numbers[key]))
                    p.add_run('）')
                else:
                    self.mark_inline(p,number_name(key),write_equation)
            elif kind == 'table': self.data_table(b)
            elif kind == 'image-group': self.group(b)
            elif kind in ('figure','mermaid'):
                p = self.paragraph('图形段')
                d = b['data']
                if d['kind'] == 'mermaid':
                    rendition = self.graphics['diagrams'][self.identity(b)]
                    if isinstance(rendition, Picture):
                        self.picture(p, {}, self.width, rendition=rendition)
                        self.diagnostic('DIAGRAM_RENDITION', b, 'Existing HRS renderer provides a PNG view; original Mermaid source is retained.')
                    else:
                        self.write_fallback(p,d['source'],reason='diagram_rendition',detail=rendition)
                elif d['kind'] == 'image': self.picture(p, d, self.width)
                else: raise BridgeError('Unsupported figure kind: ' + d['kind'])
                p.paragraph_format.keep_with_next = True
                self.caption(b, True)
            else: raise BridgeError('Unsupported HRS block: ' + kind)
            nodes = self.range_nodes(begin, self.close_body_range(begin))
            if previous_data_table:self.space_after_data_table(nodes)
            if nodes:previous_data_table=kind=='table'
            entry = {'index': b['index'], 'type':kind, 'id':b.get('id'), 'bookmark':bookmark,
                     'native_drawing_extents':drawing_extents(nodes)}
            if kind == 'heading':
                # Only the output projection is additional metadata; the source
                # level remains in the existing source snapshot/IR.
                entry['word_heading_level'] = None if style == 'Title' else int(style.split()[-1])
            regions.append((entry, nodes))
        self.current_block = None
        reference_region = self.write_references()
        self.close_body_range(scope)
        if [E.tostring(node) for node in self.body[:len(self.front_xml)]] != self.front_xml:
            raise BridgeError('Template front matter changed during assembly')
        digest_native = native_hasher(self.doc.part, text_scripts=True)
        for entry, nodes in chain(regions, (reference_region,) if reference_region else ()):
            entry['native_sha256'] = digest_native(nodes)
        metadata_blocks = [entry for entry, _ in regions]
        derived_sections = [reference_region[0]] if reference_region else []
        update=self.doc.settings.element.find(qn('w:updateFields'))
        if update is None:update=element('w:updateFields');self.doc.settings.element.append(update)
        update.set(qn('w:val'),'true')
        assets, blobs = {}, {}
        for path in sorted((self.source/'assets').rglob('*')):
            if path.is_file():
                raw = path.read_bytes()
                digest = sha(raw)
                assets[path.relative_to(self.source).as_posix()] = digest
                if digest not in blobs:
                    blobs[digest] = base64.b64encode(raw).decode('ascii')
        meta = {'schema':'hrs-wps-bridge-v1', 'document_key':self.document_key,'source_sha256':self.source_sha256, 'source_b64':base64.b64encode(self.raw).decode('ascii'),
                'assets':assets,'blobs':blobs,'blocks':metadata_blocks,'derived_sections':derived_sections,'word_output_options':self.options,
                'native_text_scripts':True,'body_scope':{'bookmark':scope_name,'kind':'wps-report-body-v1'},'template_sha256':self.template_sha256, 'output_profile':'wps-template-v1','source_render_profile':self.source_profile,'source_render_options':self.source_options,'word_origin':self.word_origin}
        fallbacks = [item for item in self.diagnostics if item['code'] == TEXT_FALLBACK]
        if fallbacks:
            meta['output_fallbacks'] = fallbacks
        self.doc.save(output)
        self.preserve_template_parts(output)
        provenance_path(output).write_text(json.dumps(meta,ensure_ascii=False,separators=(',',':')),encoding='utf8')
        if any(self.inline_math_counts.values()):
            converted = self.inline_math_counts['converted']
            retained = self.inline_math_counts['retained']
            self.diagnostics.append({'code':'WORD_INLINE_MATH_TEXT', **self.inline_math_counts,
                'message':f'行内单位或量值按正文输出 {converted} 处，保留原生公式 {retained} 处。'})
        return {'ok':True, 'output':str(output), 'sha256':sha(output.read_bytes()), 'source_sha256':self.source_sha256,
                'template':self.template_info, 'object_styles':[self.styles[n] for n in ('图形段','图题','表题','表内正文','公式')],
                'diagnostics':self.diagnostics, 'blocks':len(metadata_blocks),'word_output_options':self.options}

    def preserve_template_parts(self,output):
        """The original cover/header parts remain byte-exact; only body-owned
        package parts and newly introduced relationships may be regenerated."""
        import zipfile,os
        mutable={'word/document.xml','word/styles.xml','word/numbering.xml','word/settings.xml',
            'word/_rels/document.xml.rels','[Content_Types].xml'}
        if self.note_part is not None:
            name=str(self.note_part.partname).lstrip('/');mutable.add(name)
            part=Path(name);mutable.add(str(part.parent/'_rels'/(part.name+'.rels')).replace('\\','/'))
        with zipfile.ZipFile(self.template) as original,zipfile.ZipFile(output) as generated:
            original_bytes={name:original.read(name) for name in original.namelist() if name not in mutable}
            members={item.filename:(item,generated.read(item.filename)) for item in generated.infolist()}
        temp=output.with_suffix('.preserve.docx')
        try:
            with zipfile.ZipFile(temp,'x',compression=zipfile.ZIP_DEFLATED) as archive:
                for name,(info,data) in members.items():archive.writestr(info,original_bytes.pop(name,data))
                for name,data in original_bytes.items():archive.writestr(name,data)
            os.replace(temp,output)
        finally:
            if temp.exists():temp.unlink()


def prepare(rt, source, *, template=None, accept_numbered_headings=False, options=None):
    return Writer(rt,source,template,accept_numbered_headings,prepare_only=True,options=options).model_request


def convert(rt, source, output, *, template=None, accept_numbered_headings=False, model=None, options=None):
    output = new_path(output)
    sidecar = new_path(provenance_path(output))
    source=Path(source).resolve()
    if source.is_file():source=source.parent
    before={p.relative_to(source).as_posix():sha(p.read_bytes()) for p in source.rglob('*') if p.is_file()}
    writer = Writer(rt, source,template,accept_numbered_headings,model=model,options=options)
    with tempfile.TemporaryDirectory(prefix='bridge-docx-') as temp:
        staged = Path(temp)/'report.docx'
        receipt = writer.write(staged)
        # Publish only a complete, readable OPC package, never half of a conversion.
        Document(staged)
        after={p.relative_to(source).as_posix():sha(p.read_bytes()) for p in source.rglob('*') if p.is_file()}
        if before!=after:raise BridgeError('Source changed during DOCX export')
        if sha(writer.template.read_bytes())!=writer.template_sha256:raise BridgeError('Template changed during DOCX export')
        created=[]
        try:
            for target,raw in ((output,staged.read_bytes()),(sidecar,provenance_path(staged).read_bytes())):
                with target.open('xb') as stream:
                    created.append(target)
                    stream.write(raw)
        except Exception:
            for target in created:target.unlink()
            raise
    receipt.update(output=str(output), sha256=sha(output.read_bytes()),provenance=str(sidecar),provenance_sha256=sha(sidecar.read_bytes()),source_unchanged=True)
    return receipt
