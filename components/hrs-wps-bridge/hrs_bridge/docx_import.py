"""Restricted native DOCX recovery, using WPS facts and the existing HRS contract."""
import base64
from collections import Counter, defaultdict
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import re
from shutil import copyfile
import tempfile
from urllib.parse import quote,unquote,urlsplit

from docx import Document
from docx.oxml.ns import qn
from lxml import etree as E

from .browser import call
from .math_adapter import MathAdapter
from .ooxml import N, W, TEXT_SCRIPT_TAGS, bookmark_regions, read_provenance, native_hasher, drawing_extents, number_name
from .runtime import BridgeError, new_path, sha

MATH_SEGMENTS=frozenset({'math_inline','math_display','legacy_equation'})
EQUATION_FIELD=re.compile(r'^\s*SEQ\s+(?:公式|Equation|MTEquation|MTEqn)(?=\s|$)',re.I)
CAPTION_SEQUENCE_NAMES={'图':('图','figure','hrsfigure'), '表':('表','table','hrstable')}
MATHTYPE_MACRO=re.compile(r'\s*MACROBUTTON\s+MTPlaceRef(?:\s+\\\*\s+MERGEFORMAT)?\s*',re.I)
MATHTYPE_SEQ=re.compile(r'\s*SEQ\s+(MTEqn|MTChap|MTSec)(?:\s+(?:\\[hc]|\\r\s+\d+|\\\*\s+(?:ARABIC|MERGEFORMAT)))*\s*',re.I)
MATHTYPE_REF=re.compile(r'\s*REF\s+(ZEqnNum[0-9]+)(?:\s+(?:\\h|\\!|\\\*\s+(?:CHARFORMAT|MERGEFORMAT)))*\s*',re.I)
MATHTYPE_GOTO=re.compile(r'\s*GOTOBUTTON\s+(ZEqnNum[0-9]+)(?:\s+\\\*\s+MERGEFORMAT)?\s*',re.I)
EQUATION_NUMBER=re.compile(r'[（(]\s*([0-9]+(?:[.\-][0-9]+)*)\s*[)）]')
WRAPPED_EQUATION_REF=re.compile(r'(?:式[ \t]*)?[（(][ \t]*(@eq:eq-[A-Za-z0-9_-]+)[ \t]*[)）]')
WRAPPED_FIGURE_REF=re.compile(r'图[ \t]*(@fig:fig-[A-Za-z0-9_-]+)')
WRAPPED_TABLE_REF=re.compile(r'表[ \t]*(@tbl:tbl-[A-Za-z0-9_-]+)')
INLINE_CODE_STYLES=frozenset({'hrs code char','hrscodechar','verbatim char','verbatimchar','code char','codechar','inline code','source text'})
CODE_BLOCK_STYLES=frozenset({'hrs code','hrscode','source code','sourcecode'})


def _split_outer_hspace(value):
    stripped_l = value.lstrip(' \t')
    if not stripped_l:
        return value, '', ''
    lead = value[:len(value) - len(stripped_l)]
    stripped_r = stripped_l.rstrip(' \t')
    trail = stripped_l[len(stripped_r):]
    return lead, stripped_r, trail


@contextmanager
def import_stage(name,label):
    """Keep the primary filesystem error identifiable across the worker channel."""
    try:yield
    except OSError as cause:
        error=BridgeError(label+'失败：'+str(cause))
        error.import_stage=name;error.io_error=cause
        raise error from cause


def read_document(path):
    with import_stage('snapshot_read','读取Word工作副本'):
        # Explicit ownership avoids the path existence/is_zipfile probes that
        # can turn access denial into python-docx's generic PackageNotFound.
        with Path(path).open('rb') as stream:return Document(stream)


@contextmanager
def import_workspace(parent,maintenance):
    with import_stage('workspace_create','创建转换临时目录'):
        temporary=tempfile.TemporaryDirectory(prefix='bridge-import-',dir=parent,ignore_cleanup_errors=True)
    try:yield Path(temporary.name)
    finally:
        try:temporary.cleanup()
        except OSError as error:maintenance['cleanup_error']=str(error)
        try:maintenance['cleanup_pending']=Path(temporary.name).exists()
        except OSError:maintenance['cleanup_pending']=True
        if maintenance['cleanup_pending']:maintenance['cleanup_path']=temporary.name


def escaped(text):
    # Serialization of observed Word text, not an alternative Markdown parser.
    # Leave ']' unescaped so '[text]' becomes '\[text]' rather than LaTeX '\[text\]'.
    return re.sub(r'([\\`*_\[<>|@$=#!~])', r'\\\1', text)


def fenced(kind, data):
    return '```' + kind + '\n' + json.dumps(data, ensure_ascii=False, indent=2) + '\n```\n'


def without_segments(block, excluded):
    kept=[];positions=[0]
    for segment in block['segments']:
        if not excluded(segment):kept.append(segment)
        positions.append(len(kept))
    if len(kept)==len(block['segments']):return block
    result={**block,'segments':kept}
    if block.get('hyperlink_ranges'):
        result['hyperlink_ranges']=[{**span,'start':positions[span['start']],'end':positions[span['end']]}
                                    for span in block['hyperlink_ranges']]
    return result


def legacy_payload(node,relations,parts,store):
    from legacy_math import LIMIT,embedded_equation,equation_part
    ole=embedded_equation(node)
    if ole is None:return None
    try:
        name=equation_part(ole,relations)
        if name not in parts:raise ValueError('旧公式数学部件缺失')
        if len(parts[name])>LIMIT:raise ValueError('旧公式数学部件超过大小限制')
        return {'equation_media':store(name)}
    except ValueError as error:
        return {'equation_error':str(error)}


@dataclass(frozen=True)
class DisplayEquation:
    segment: dict
    number: str | None
    anchors: tuple[str,...]
    number_label: str


def mathtype_number_suffix(reader,segments):
    # Interpret the saved results of known MathType fields as data. The
    # original template may use nested MTEqn/MTSec/MTChap sequence counters.
    stack=[];visible=[]
    for s in segments:
        kind=s['kind']
        if kind=='field_evidence':
            node=reader.object_xml(s['object_id']);local=E.QName(node).localname
            if local=='fldSimple':
                if len(stack)!=1 or not stack[0][1] or not MATHTYPE_SEQ.fullmatch(node.get(qn('w:instr'),'')):return None
                visible.extend(t.text or '' for t in node.iter(qn('w:t')))
            elif local=='instrText' and stack and not stack[-1][1]:
                stack[-1][0].append(node.text or '')
            elif local=='fldChar':
                mode=node.get(qn('w:fldCharType'))
                if mode=='begin' and len(stack)<2 and (not stack or stack[0][1]):
                    stack.append(([],False))
                elif mode=='separate' and stack and not stack[-1][1]:
                    instruction=''.join(stack[-1][0])
                    rule=MATHTYPE_MACRO if len(stack)==1 else MATHTYPE_SEQ
                    if not rule.fullmatch(instruction):return None
                    stack[-1]=(stack[-1][0],True)
                elif mode=='end' and stack and stack[-1][1]:stack.pop()
                else:return None
            else:return None
        elif kind=='text' and all(frame[1] for frame in stack):visible.append(s['text'])
    if stack:return None
    return EQUATION_NUMBER.fullmatch(''.join(visible).strip())


def display_equation(reader,block):
    """Recognize a standalone equation from Word layout and explicit fields."""
    if (block['kind']!='paragraph' or block.get('hyperlinks')
            or block.get('outline_level_raw') in range(6)
            or block.get('numbering_effective',{}).get('num_id') not in (None,'0')):
        return None
    segments=block['segments']
    math=[(i,s) for i,s in enumerate(segments) if s['kind'] in MATH_SEGMENTS]
    if len(math)!=1:return None
    position,segment=math[0]
    before=[];after=[];anchors={}
    closing={s['bookmark_id']:i for i,s in enumerate(segments) if s['kind']=='bookmarkEnd'}
    has_field=False;has_tab=False
    for i,s in enumerate(segments):
        kind=s['kind']
        if kind=='bookmarkStart':anchors[s['bookmark_id']]=(i,s['name'])
        elif kind=='bookmarkEnd':continue
        elif kind=='field_evidence':
            if i<position:return None
            has_field=True
        elif kind=='text':(before if i<position else after).append(s['text'])
        elif kind=='tab':
            if i>position:has_tab=True
        elif i!=position:return None
    if ''.join(before).strip():return None
    enclosing=[name for ident,(start,name) in anchors.items() if start<position<closing.get(ident,-1) and name]
    suffix=''.join(after).strip()
    number=None
    if has_field:
        if block.get('container_id') is not None:return None
        from wps_pipeline.native_output import SEQ_FIELD,field_views,number_bookmarks
        p=reader.body[block['source_locator']['body_child_index']]
        views=field_views(p)
        if len(views)==1 and EQUATION_FIELD.match(views[0]['instruction']):
            view=views[0];cache=view['cache'].strip()
            if not SEQ_FIELD.fullmatch(view['instruction']) or not re.fullmatch(r'[0-9]+',cache):return None
            # In a complex field the cache also appears as text in the scan.
            expected='[（(][ \t]*'+(re.escape(cache) if view['simple'] is None else '')+'[ \t]*[)）]'
            if suffix and not re.fullmatch(expected,suffix) and (view['simple'] is not None or suffix!=cache):
                return None
            number=cache
        elif has_tab and segment['kind']=='legacy_equation':
            label=mathtype_number_suffix(reader,segments[position+1:])
            if label is None:return None
            number=label[1];suffix=label[0]
        else:return None
        # MathType may bookmark the digits or the entire parenthesized label.
        for label in {number,suffix}:
            enclosing.extend(name for name in number_bookmarks(p,label) if name and label)
    elif suffix:
        label=EQUATION_NUMBER.fullmatch(suffix)
        if not label or not has_tab:return None
        number=label[1]
    if segment['kind']=='math_inline' and not number and (block.get('style_name') or '').casefold()!='公式':
        return None
    if segment['kind']=='legacy_equation' and not number:
        try:
            if reader.legacy(segment['object_id']).inline is True:return None
        except BridgeError:return None
    if segment['kind']!='legacy_equation':
        # WPS may move a bookmark from around the formula into its first and
        # last slots on Save As. Preserve its target at the enclosing equation.
        native=reader.object_xml(segment['object_id'])
        inner_ends={n.get(qn('w:id')) for n in native.iter(qn('w:bookmarkEnd'))}
        enclosing.extend(n.get(qn('w:name')) for n in native.iter(qn('w:bookmarkStart'))
                         if (n.get(qn('w:id')) in inner_ends or closing.get(n.get(qn('w:id')),-1)>position)
                         and n.get(qn('w:name')))
        enclosing.extend(name for ident,(start,name) in anchors.items() if start<position and ident in inner_ends and name)
    return DisplayEquation(segment,number,tuple(dict.fromkeys(enclosing)),suffix)


class NativeReader:
    def __init__(self, rt, docx, work, assets, identities=None, editable=False, *, object_seed=None, relationship_part=None):
        from wps_pipeline.scan_docx import Scanner
        self.rt, self.path, self.work, self.assets = rt, Path(docx), Path(work), Path(assets)
        with import_stage('scan','扫描Word工作副本'):
            scanner=Scanner(self.path, self.work/'scan',equation_payload=legacy_payload,
                            relationship_part=relationship_part)
            self.scan=scanner.run()
            self.body=scanner.body
            self.word_bookmarks=Counter(n.get(qn('w:name')) for n in self.body.iter(qn('w:bookmarkStart')))
        self.stored_images=set()
        self.prepared_images={}
        self.picture_ids={}
        self.object_seed=object_seed or self.scan['source_sha256'][:16]
        self.char_styles={}
        try:
            from zipfile import ZipFile
            with ZipFile(self.path) as archive:
                if 'word/styles.xml' in archive.namelist():
                    for st in E.fromstring(archive.read('word/styles.xml')).findall('w:style', N):
                        sid = (st.get(qn('w:styleId')) or '').strip()
                        sname_el = st.find('w:name', N)
                        sname = (sname_el.get(qn('w:val')) if sname_el is not None else '') or ''
                        if sid:
                            self.char_styles[sid] = sname.strip().casefold() or sid.casefold()
        except Exception:
            pass
        self.diagnostics = []
        self.editable = editable
        self.detached = []
        self.current_block = None
        self.notes = None
        # These empty Word editing/rendering markers have no document content.
        # Keep the original scan on disk; adapt only the reader's event stream.
        ignored = Counter();nonempty_markers=[]
        def editor_marker(block,segment):
            kind=segment['kind']
            if kind not in ('unsupported','layout_marker'):return False
            node=self.object_xml(segment['object_id']);local=E.QName(node).localname
            if node.tag in (qn('w:proofErr'),qn('w:lastRenderedPageBreak')) and not len(node) and not (node.text or '').strip():
                if kind=='unsupported':ignored[(block['block_id'],local)]+=1
                self.diagnostics.append({'code':'WORD_EDITOR_MARKER_IGNORED','block':block['block_id'],'marker':local})
                return True
            if kind=='layout_marker':
                nonempty_markers.append({'block_id':block['block_id'],'reason':local,'object_id':segment['object_id']})
            return False
        for i,block in enumerate(self.scan['blocks']):
            if 'segments' in block:
                self.scan['blocks'][i]=without_segments(block,lambda segment:editor_marker(block,segment))
        unsupported = []
        for item in self.scan['unsupported']:
            key = (item['block_id'], item['reason'])
            if ignored[key]: ignored[key] -= 1
            else: unsupported.append(item)
        self.scan['unsupported'] = unsupported+nonempty_markers
        if self.scan['unsupported'] and not editable:
            raise BridgeError('UNSUPPORTED_NATIVE_CONTENT: ' + json.dumps(self.scan['unsupported'], ensure_ascii=False))
        self.facts = {b['block_id']:b for b in self.scan['blocks']}
        self.top = [self.facts[i] for i in self.scan['top_level_ids'] if self.facts[i]['kind'] != 'boundary']
        self.math = None
        self.import_math = None
        self.legacy_math = {}
        self.identities = identities or {}
        self.link_targets=dict(self.identities);self.link_heading_ids={};self.link_review={}

    def _scan_field_bookmarks(self, block):
        from wps_pipeline.assemble_reports import REF_FIELD
        names = set()
        stack = []
        for s in block.get('segments', []):
            if s['kind'] != 'field_evidence':
                continue
            node = self.object_xml(s['object_id'])
            local = E.QName(node).localname
            instructions = []
            if local == 'fldSimple':
                instructions.append(node.get(qn('w:instr'), ''))
            elif local == 'fldChar':
                mode = node.get(qn('w:fldCharType'))
                if mode == 'begin':
                    stack.append([])
                elif mode == 'end' and stack:
                    instructions.append(''.join(stack.pop()))
            elif local == 'instrText' and stack:
                stack[-1].append(node.text or '')
            for instr in instructions:
                m = REF_FIELD.fullmatch(instr)
                if m:
                    names.add(m[1])
                    continue
                m_link = re.fullmatch(r'\s*HYPERLINK\s+\\l\s+"([\w]+)"\s*', instr, re.I)
                if m_link:
                    names.add(m_link[1])
        return names

    def map_hyperlink_targets(self,recognition,decisions):
        """Adapt existing confirmed roles/bookmarks, never infer new roles."""
        roles={r['block_id']:r for r in recognition['roles']}
        captions={v['block']:target for target,v in recognition['captions'].items()}
        groups={b:g['blocks'][0] for g in decisions.get('groups',[]) for b in g['blocks']}
        referenced=set()
        for b in self.scan['blocks']:
            for item in b.get('hyperlinks',[]):
                referenced.update(item['attributes'].get(qn('w:'+attribute)) for attribute in ('anchor','docLocation'))
                value=(item.get('relationship') or {}).get('Target','')
                if value.startswith('#'):referenced.add(unquote(value[1:]))
            referenced.update(self._scan_field_bookmarks(b))
        referenced.discard(None)
        targets={};prepared_pictures=set(self.picture_ids.values())
        for b in self.top:
            r=roles[b['block_id']];kind=None
            if r['status']!='review' and (r['role']=='document_title' or r['role']=='heading' and 1<=r.get('level',0)<=5):kind='sec'
            elif b['kind']=='table':kind='fig' if r.get('figure_layout') else 'tbl'
            elif r['role']=='figure' or b['block_id'] in groups:kind='fig'
            if kind:
                target=self.object_id(kind,groups.get(b['block_id'],b['block_id']))
                if kind!='fig' or not self.editable or target in prepared_pictures:
                    targets[b['block_id']]=(kind,target)
        if not referenced:return targets
        counts=self.word_bookmarks
        for b in self.top:
            target_block=captions.get(b['block_id'],b['block_id'])
            target=targets.get(target_block)
            if not target:continue
            for s in b.get('segments',[]):
                name=s.get('name') if s['kind']=='bookmarkStart' else None
                if not name or name not in referenced or counts[name]!=1:continue
                if name in self.link_targets and self.link_targets[name]!=target:raise BridgeError('WORD_BOOKMARK_AMBIGUOUS: '+name)
                self.link_targets[name]=target
                if b['block_id'] not in captions:self.identities.setdefault(name,target)
                if target[0]=='sec':self.link_heading_ids[target_block]=target[1]
        return targets

    def link_destination(self,record):
        attrs=record['attributes'];relation=record.get('relationship');anchor=attrs.get(qn('w:anchor')) or attrs.get(qn('w:docLocation'))
        if attrs.get(qn('w:anchor')) and attrs.get(qn('w:docLocation')) and attrs[qn('w:anchor')]!=attrs[qn('w:docLocation')]:return None
        target=(relation or {}).get('Target')
        if not target and anchor:
            mapped=self.link_targets.get(anchor)
            return '#object-'+mapped[1] if mapped else None
        if not isinstance(target,str) or len(target)>8192 or re.search(r'[\x00-\x1f\x7f-\x9f]',target):return None
        if target.startswith('#') and not anchor:
            mapped=self.link_targets.get(unquote(target[1:]))
            if mapped:return '#object-'+mapped[1]
            if target.startswith('#object-') and target[8:] in {v[1] for v in self.link_targets.values()}:return target
            return None
        try:parsed=urlsplit(target)
        except ValueError:return None
        if not relation.get('Type','').endswith('/hyperlink') or relation.get('TargetMode')!='External':return None
        scheme=parsed.scheme.lower()
        if not ((scheme in ('http','https') and parsed.netloc) or (scheme=='mailto' and parsed.path) or (scheme=='file' and parsed.path.startswith('/'))):return None
        if anchor:
            if parsed.fragment and parsed.fragment!=anchor:return None
            target=target.split('#',1)[0]+'#'+anchor
        return quote(target,safe=":/?#[]@!$&'()*+,;=%")

    def _segment_style_flags(self, s, suppress_bold=False):
        props = s.get('run_properties_raw')
        props = {E.QName(p[0]).localname: dict(p[1]).get(qn('w:val'), '1') for p in props[3]} if props else {}
        rstyle = (props.get('rStyle') or '').strip()
        style_name = self.char_styles.get(rstyle, rstyle.casefold()) if rstyle else ''
        bold = False if suppress_bold else props.get('b') not in (None, '0', 'false', 'off')
        italic = props.get('i') not in (None, '0', 'false', 'off')
        strike = props.get('strike') not in (None, '0', 'false', 'off')
        underline = props.get('u') not in (None, 'none', '0', 'false', 'off')
        script = TEXT_SCRIPT_TAGS.get(props.get('vertAlign'))
        is_code = style_name in INLINE_CODE_STYLES or rstyle.casefold() in INLINE_CODE_STYLES
        return (bold, italic, strike, underline, script, is_code)

    def _all_text_bold(self, segments, text_skip=0):
        rem = text_skip
        non_ws = []
        for s in segments:
            if s.get('kind') != 'text':
                continue
            val = s.get('text', '')
            if rem:
                cut = min(rem, len(val))
                val = val[cut:]
                rem -= cut
            if val.strip():
                non_ws.append(s)
        return bool(non_ws) and all(self._segment_style_flags(s)[0] for s in non_ws)

    def _format_text_buffer(self, runs, plain, formatting):
        if not runs:
            return ''
        if plain:
            return ''.join(raw for raw, _ in runs)
        if not formatting:
            return ''.join(escaped(raw) for raw, _ in runs)
        out = []
        idx = 0
        while idx < len(runs):
            outer = runs[idx][1][:5]
            group = []
            while idx < len(runs) and runs[idx][1][:5] == outer:
                raw_val, flags = runs[idx]
                is_code = flags[5]
                if group and group[-1][0] == is_code:
                    group[-1] = (is_code, group[-1][1] + raw_val)
                else:
                    group.append((is_code, raw_val))
                idx += 1
            pieces = []
            for is_code, sub in group:
                if not sub:
                    continue
                if is_code and sub.strip():
                    lead_c, core_c, trail_c = _split_outer_hspace(sub)
                    ticks = '`' * (max((len(m.group(0)) for m in re.finditer(r'`+', core_c)), default=0) + 1)
                    pad = ' ' if core_c.startswith('`') or core_c.endswith('`') else ''
                    pieces.append(f'{lead_c}{ticks}{pad}{core_c}{pad}{ticks}{trail_c}')
                else:
                    pieces.append(escaped(sub))
            inner = ''.join(pieces)
            if not inner.strip() or not any(outer):
                out.append(inner)
                continue
            bold, italic, strike, underline, script = outer
            lines = inner.split('\n')
            formatted_lines = []
            for line in lines:
                if not line.strip():
                    formatted_lines.append(line)
                    continue
                lead, core, trail = _split_outer_hspace(line)
                if bold:
                    core = '**' + core + '**'
                if italic:
                    core = '*' + core + '*'
                if strike:
                    core = '~~' + core + '~~'
                if underline:
                    core = '<u>' + core + '</u>'
                if script:
                    core = f'<{script}>{core}</{script}>'
                formatted_lines.append(lead + core + trail)
            out.append('\n'.join(formatted_lines))
        return ''.join(out)

    def linked_paragraph(self,b,caption,plain,text_skip,formatting,*,suppress_bold=False):
        records=b['hyperlinks'];ranges=b.get('hyperlink_ranges');segments=b.get('segments',[])
        if not isinstance(ranges,list) or len(ranges)!=len(records):raise BridgeError('WORD_LINK_COMPONENT_OUTDATED: 请使用支持超链接范围的配套 Word 组件')
        if not all(isinstance(r,dict) for r in ranges):raise BridgeError('WORD_LINK_RANGE_INVALID: '+b.get('block_id',''))
        cursor=0;parts=[]
        if {s.get('link_index') for s in ranges}!=set(range(len(records))):raise BridgeError('WORD_LINK_RANGE_INVALID: '+b.get('block_id',''))
        def part(items):
            nonlocal text_skip
            count=sum(len(s['text']) for s in items if s['kind']=='text');skip=min(text_skip,count);text_skip-=skip
            return self.paragraph({'segments':items},caption=caption,plain=plain,text_skip=skip,formatting=formatting,suppress_bold=suppress_bold)
        for span in ranges:
            start,end,index=(span.get(k) for k in ('start','end','link_index'))
            if any(type(v) is not int for v in (start,end,index)) or not cursor<=start<=end<=len(segments) or not 0<=index<len(records):
                raise BridgeError('WORD_LINK_RANGE_INVALID: '+b.get('block_id',''))
            parts.append(part(segments[cursor:start]));label=part(segments[start:end]);record=records[index]
            href=self.link_destination(record)
            safe_label=re.sub(r'(?<!\\)\]', '&#93;', label) if label and href and not plain and ']' in label else label
            parts.append('['+safe_label+'](<'+href+'>)' if label and href and not plain else label)
            if not href and not plain:
                target=(record.get('relationship') or {}).get('Target');anchor=record['attributes'].get(qn('w:anchor'))
                key=(b.get('block_id'),index)
                if key not in self.link_review:
                    message='超链接目标未可靠映射，保留原文字及目标记录；请核对该链接。'
                    location=record['attributes'].get(qn('w:docLocation'))
                    self.link_review[key]={'block':b.get('block_id'),'text':label,'role':'hyperlink','evidence':['WORD_HYPERLINK_UNRESOLVED'],'target':target,'anchor':anchor,'doc_location':location}
                    self.diagnostics.append({'code':'WORD_HYPERLINK_UNRESOLVED','block':b.get('block_id'),'text':label,'target':target,'anchor':anchor,'doc_location':location,'message':message})
            cursor=end
        parts.append(part(segments[cursor:]));return ''.join(parts)

    def object_xml(self, ident):
        return E.fromstring(self.payload(self.scan['objects'][ident]['payload_ref']).read_bytes())

    def object_id(self, kind, ident):
        return kind+'-'+self.object_seed+'-'+ident

    def tex(self, ident):
        if self.scan['objects'][ident]['kind']=='legacy_equation':
            return self.legacy(ident).tex
        if self.editable:
            if self.import_math is None:
                self.math=MathAdapter(self.rt)
                expressions={}
                for obj in self.scan['objects'].values():
                    if obj['kind'] in ('math_inline','math_display'):
                        expressions.setdefault(obj['xml_sha256'],obj['payload_ref'])
                payloads=((self.payload(path).read_bytes(),digest) for digest,path in expressions.items())
                self.import_math=dict(self.math.tex_import(payloads))
            result=self.import_math[self.scan['objects'][ident]['xml_sha256']]
            if result.reason:raise BridgeError(result.reason)
            return result.tex
        if self.math is None: self.math = MathAdapter(self.rt)
        return self.math.tex(self.object_xml(ident))

    def legacy(self,ident):
        from legacy_math import read_ole
        obj=self.scan['objects'][ident]
        if 'equation_error' in obj:raise BridgeError(obj['equation_error'])
        source=obj['equation_media']
        key=source['sha256']
        if key not in self.legacy_math:
            try:self.legacy_math[key]=read_ole(self.payload(source['payload_ref']).read_bytes())
            except ValueError as error:self.legacy_math[key]=str(error)
        value=self.legacy_math[key]
        if isinstance(value,str):raise BridgeError(value)
        return value

    def payload(self, name):
        return self.work/'scan'/name

    def field(self, instruction, caption=False, *, nested_reference=None, cached=''):
        from wps_pipeline.assemble_reports import REF_FIELD
        from wps_pipeline.native_output import SEQ_FIELD
        if SEQ_FIELD.fullmatch(instruction):
            if caption and cached: return cached
            raise BridgeError('SEQ field outside a known caption')
        match = REF_FIELD.fullmatch(instruction)
        if match and match[1] in self.identities:
            kind, ident = self.identities[match[1]]
            if kind=='eq':return ' @eq:'+ident+' '
            return '@'+kind+':'+ident
        link=re.fullmatch(r'\s*HYPERLINK\s+\\l\s+"([\w]+)"\s*',instruction,re.I)
        if link and (target:=self.identities.get(link[1])) and target[0]=='eq':
            return ' @eq:'+target[1]+' '
        ref=MATHTYPE_REF.fullmatch(instruction)
        if nested_reference:
            jump=MATHTYPE_GOTO.fullmatch(instruction)
            if jump and jump[1]==nested_reference:ref=jump
        if ref and (target:=self.identities.get(ref[1])) and target[0]=='eq':
            return ' @eq:'+target[1]+' '
        raise BridgeError('UNSUPPORTED_NATIVE_FIELD: ' + instruction.strip())

    def paragraph(self, b, caption=False, plain=False, text_skip=0, formatting=True, *, strip_heading_bold=False, suppress_bold=False):
        if strip_heading_bold and not suppress_bold and self._all_text_bold(b.get('segments', []), text_skip=text_skip):
            suppress_bold = True
        if self.editable:
            from .editable_import import paragraph
            text=paragraph(self,b,caption,plain,text_skip,formatting,suppress_bold=suppress_bold)
        else:text=self._paragraph(b,caption,plain,text_skip,formatting,suppress_bold=suppress_bold)
        text=WRAPPED_FIGURE_REF.sub(r'\1',text)
        text=WRAPPED_TABLE_REF.sub(r'\1',text)
        text=WRAPPED_EQUATION_REF.sub(r' \1 ',text)
        text=re.sub(r'(?<=[ \t]) (@eq:eq-[A-Za-z0-9_-]+)',r'\1',text)
        return re.sub(r'(@eq:eq-[A-Za-z0-9_-]+) (?=[ \t]|[，。！？、；：,.!?;:）)]|$)',r'\1',text)

    def _paragraph(self, b, caption=False, plain=False, text_skip=0, formatting=True, *, suppress_bold=False):
        if b.get('hyperlinks'):return self.linked_paragraph(b,caption,plain,text_skip,formatting,suppress_bold=suppress_bold)
        text=[];stack=[];text_buf=[]
        def flush_text():
            if text_buf:
                text.append(self._format_text_buffer(text_buf, plain, formatting))
                text_buf.clear()
        for s in b.get('segments', []):
            kind=s['kind']
            if kind=='field_evidence':
                flush_text()
                node=self.object_xml(s['object_id']);local=E.QName(node).localname
                if local=='fldSimple':
                    cached=''.join(t.text or '' for t in node.iter(qn('w:t'))) if caption else ''
                    text.append(self.field(node.get(qn('w:instr'),''),caption,cached=cached if plain else escaped(cached)));continue
                if local=='fldChar':
                    mode=node.get(qn('w:fldCharType'))
                    if mode=='begin':stack.append({'instruction':[], 'cache':[], 'result':False})
                    elif mode=='separate' and stack:stack[-1]['result']=True
                    elif mode=='end' and stack:
                        frame=stack.pop()
                        if not stack:
                            cached=''.join(frame['cache'])
                            text.append(self.field(''.join(frame['instruction']),caption,cached=cached if plain else escaped(cached)))
                    continue
                if local=='instrText' and stack:stack[-1]['instruction'].append(node.text or '')
                continue
            if stack:
                if caption and stack[-1]['result'] and kind=='text':stack[-1]['cache'].append(s['text'])
                continue
            if kind=='text':
                value=s['text']
                if text_skip:
                    count=min(text_skip,len(value));value=value[count:];text_skip-=count
                if value:
                    text_buf.append((value, self._segment_style_flags(s, suppress_bold=suppress_bold)))
            elif kind in MATH_SEGMENTS:
                flush_text()
                if plain:raise BridgeError('Native equation in a plain HRS caption needs an explicit mapping')
                tex=self.tex(s['object_id'])
                text.append(('$$\n'+tex+'\n$$') if kind=='math_display' else '$'+tex+'$')
            elif kind in ('bookmarkStart','bookmarkEnd'):continue
            elif kind in ('br','cr'):flush_text();text.append('\n')
            elif kind=='tab':flush_text();text.append('\t')
            elif kind in ('noBreakHyphen','softHyphen'):flush_text();text.append('-')
            elif kind=='drawing':raise BridgeError('Mixed text/drawing paragraph requires an explicit structure mapping')
            else:raise BridgeError('Unsupported native paragraph event: '+kind)
        if stack:raise BridgeError('Unclosed native field')
        flush_text()
        return ''.join(text)

    def leading_field(self, b):
        """Read the first complete, non-nested field after a text-only prefix."""
        segments = b.get('segments', [])
        start = next((i for i, s in enumerate(segments) if s['kind'] not in ('text','tab','bookmarkStart','bookmarkEnd')), None)
        if start is None or segments[start]['kind'] != 'field_evidence':
            return None
        node = self.object_xml(segments[start]['object_id'])
        if node.tag == qn('w:fldSimple'):
            return start, start+1, node.get(qn('w:instr'),''), ''.join(t.text or '' for t in node.iter(qn('w:t')))
        if node.tag != qn('w:fldChar') or node.get(qn('w:fldCharType')) != 'begin':
            return None
        instruction, cache = [], []
        result = False
        for i in range(start+1, len(segments)):
            segment = segments[i]
            if segment['kind'] == 'field_evidence':
                node = self.object_xml(segment['object_id'])
                if node.tag == qn('w:instrText') and not result:
                    instruction.append(node.text or '')
                elif node.tag == qn('w:fldChar') and node.get(qn('w:fldCharType')) == 'separate' and not result:
                    result = True
                elif node.tag == qn('w:fldChar') and node.get(qn('w:fldCharType')) == 'end' and result:
                    return start, i+1, ''.join(instruction), ''.join(cache)
                else:
                    return None
            elif segment['kind'] == 'text' and result:
                cache.append(segment['text'])
            elif segment['kind'] not in ('bookmarkStart','bookmarkEnd'):
                return None

    @staticmethod
    def field_bookmarks(segments, start, end):
        before = {}
        for segment in reversed(segments[:start]):
            if segment['kind'] == 'bookmarkStart':
                before[segment['bookmark_id']] = segment.get('name')
            elif segment['kind'] != 'text' or segment['text']:
                break
        for segment in segments[end:]:
            if segment['kind'] == 'bookmarkEnd':
                name = before.get(segment['bookmark_id'])
                if name: yield name
            elif segment['kind'] != 'text' or segment['text']:
                break

    def caption_number(self, b, marker):
        from wps_pipeline.native_output import SEQ_FIELD

        leading = self.leading_field(b)
        if not leading:
            return None
        start, _, instruction, cached = leading
        names = CAPTION_SEQUENCE_NAMES[marker]
        if not SEQ_FIELD.fullmatch(instruction) or instruction.split()[1].casefold() not in names or not cached.strip().isdigit():
            return None
        prefix = ''.join(s.get('text', '\t' if s['kind']=='tab' else '') for s in b['segments'][:start])
        label = '|'.join(names)
        if re.fullmatch(r'\s*(?:'+label+r')?\s*(?:\d+(?:[.．\-]\d+)*[.．\-])?\s*', prefix, re.I):
            return leading

    def caption(self, b, marker):
        from wps_pipeline.numbered_candidates import caption_prefix
        sequence = self.caption_number(b, marker)
        if sequence:
            excluded = {id(s) for s in b['segments'][:sequence[1]]}
            tail = self.paragraph(without_segments(b, lambda s: id(s) in excluded), caption=True, formatting=True, strip_heading_bold=True)
            return re.sub(r'^[ \t\u3000]*(?:[:：、]|[.．](?!\d))?[ \t\u3000]*', '', tail).strip()
        # A static number must be wholly in text before the first field or object.
        leading = []
        for s in b.get('segments', ()):
            if s['kind']=='text':leading.append(s['text'])
            elif s['kind'] not in ('bookmarkStart','bookmarkEnd'):break
        raw = ''.join(leading)
        parsed = caption_prefix(b.get('plain_text','').lstrip())
        skip = 0
        if parsed and parsed['label']==marker and raw.lstrip().startswith(parsed['prefix']):
            skip = len(raw) - len(raw.lstrip()) + len(parsed['prefix'])
            self.diagnostics.append({'code':'STATIC_CAPTION_NUMBER_NORMALIZED','block':b['block_id'],
                                     'message':'Original caption number is display text; HRS derives object numbering.'})
        return self.paragraph(b,caption=True,formatting=True,text_skip=skip,strip_heading_bold=True).strip()

    def image(self, drawing):
        if self.editable:
            from .editable_import import image
            if drawing not in self.prepared_images:
                self.prepared_images[drawing]=image(self,drawing)
            return dict(self.prepared_images[drawing])
        self.check_drawing(drawing)
        obj=self.scan['objects'][drawing]
        if len(obj['media'])!=1 or obj.get('layout')!='inline':
            raise BridgeError('Only one embedded inline image per drawing is supported')
        media=obj['media'][0]
        ext=Path(media['part']).suffix.lower()
        if ext not in ('.png','.jpg','.jpeg','.gif','.webp','.svg'):
            raise BridgeError('Edited/external '+ext+' image requires a verified PNG rendition; original source is not substituted')
        return self.store_image(media,ext)

    def store_image(self, media, ext, raw=None):
        digest=media['sha256'] if raw is None else sha(raw)
        name=digest[:16]+ext
        if name not in self.stored_images:
            target=self.assets/name
            if raw is None:copyfile(self.payload(media['payload_ref']),target)
            else:target.write_bytes(raw)
            self.stored_images.add(name)
        return {'src':'assets/'+name,'caption':''}

    def check_drawing(self, drawing):
        node=self.object_xml(drawing)
        for child in node.iter():
            local=E.QName(child).localname
            if local=='srcRect' and any(v not in ('0','0.0') for v in child.attrib.values()):
                raise BridgeError('CROPPED_IMAGE_UNSUPPORTED: preserve the edited DOCX; no uncropped source is substituted')
            if local=='xfrm' and any(v not in ('0','false','off') for k,v in child.attrib.items() if k in ('rot','flipH','flipV')):
                raise BridgeError('TRANSFORMED_IMAGE_UNSUPPORTED: native rotation/flip requires an explicit HRS representation')

    def table(self, b):
        grid=[[None for _ in range(b['columns'])] for _ in range(b['rows'])]
        if not grid or not grid[0]:raise BridgeError('Native table has no grid')
        anchors={}
        for ident in b['cells']:
            c=self.facts[ident];ri,ci=c['row'],c['col'];span=c['col_span']
            if ci+span>b['columns']:raise BridgeError('Native table grid is inconsistent')
            if c['v_merge_raw']=='continue':
                anchor=anchors.get(ci)
                if anchor is None:raise BridgeError('Native vertical merge has no restart')
                grid[anchor[0]][anchor[1]]['rowspan']+=1
                continue
            texts=[]
            for child in c['children']:
                p=self.facts[child]
                if p['kind']!='paragraph':
                    if self.editable:
                        from .editable_import import detached_table
                        texts.append(detached_table(self,p));continue
                    raise BridgeError('Nested native data table is not supported by the HRS table schema')
                if any(s['kind']=='drawing' for s in p.get('segments',[])):
                    if not self.editable:raise BridgeError('IMAGE_IN_DATA_TABLE_UNSUPPORTED: table-captioned image cells require a verified HRS data-table mapping')
                texts.append(self.paragraph(p))
            grid[ri][ci]={'text':'\n'.join(texts),'rowspan':1,'colspan':span}
            for col in range(ci,ci+span):
                if c['v_merge_raw']=='restart':anchors[col]=(ri,ci)
                else:anchors.pop(col,None)
        return grid

    def group(self, b, original):
        d=deepcopy(original)
        cols=d['columns']
        rows=d.get('rows') or (len(d['images'])+cols-1)//cols
        separate_captions=b['rows']==rows*2
        if b['rows'] not in (rows,rows*2) or b['columns']!=cols or len(b['cells'])!=b['rows']*cols:
            raise BridgeError('Edited group grid geometry is not yet supported; source is not restored')

        def content(ident):
            c=self.facts[ident]
            if c['col_span']!=1 or c['v_merge_raw'] is not None:raise BridgeError('Group grid merges are unsupported')
            paragraphs=[self.facts[i] for i in c['children']]
            if any(p['kind']!='paragraph' for p in paragraphs):raise BridgeError('Nested group cell content is unsupported')
            drawings=[s['object_id'] for p in paragraphs for s in p.get('segments',[]) if s['kind']=='drawing']
            return paragraphs,drawings

        for index in range(rows*cols):
            row,column=divmod(index,cols)
            cell_index=(row*2 if separate_captions else row)*cols+column
            paragraphs,drawings=content(b['cells'][cell_index])
            if separate_captions:
                caption_paragraphs,caption_drawings=content(b['cells'][cell_index+cols])
                if caption_drawings:raise BridgeError('Group caption row must not contain drawings')
                if any(p.get('plain_text','').strip() or any(s['kind'] in MATH_SEGMENTS or s['kind'] in ('field_evidence','unsupported') for s in p.get('segments',[])) for p in paragraphs):
                    raise BridgeError('Unexpected text in group image row; move it to the caption row')
            else:
                # Existing exports placed each caption below its picture in
                # the same cell. Preserve that bounded legacy read path.
                caption_paragraphs=[p for p in paragraphs if not any(s['kind']=='drawing' for s in p.get('segments',[]))]
            if index>=len(d['images']):
                if drawings or any(p.get('plain_text','').strip() for p in paragraphs+caption_paragraphs):raise BridgeError('Unexpected group content in empty cell')
                continue
            if len(drawings)!=1:raise BridgeError('Group cell requires exactly one current drawing')
            self.check_drawing(drawings[0])
            item=d['images'][index]
            media=self.scan['objects'][drawings[0]]['media']
            if len(media)!=1:raise BridgeError('Group image relationship is ambiguous')
            observed=media[0]['sha256']
            candidates=[item.get('sourceAsset'),item['src']]
            unchanged=any(name and (self.assets/Path(name).name).is_file() and sha((self.assets/Path(name).name).read_bytes())==observed for name in candidates)
            if not unchanged:
                item=self.image(drawings[0]);d['images'][index]=item
            captions=[self.paragraph(p,formatting=False).strip() for p in caption_paragraphs]
            text='\n'.join(s for s in captions if s)
            if d.get('showSubfigureLabels',True):text=text.removeprefix('('+chr(97+index)+')').strip()
            item['caption']=text
        return d


def scan_range(rt, path, nodes, work, assets, identities, editable=False, *, object_seed=None, relationship_part=None):
    doc=read_document(path);body=doc._element.body;section=body.find(qn('w:sectPr'))
    section=deepcopy(section) if section is not None else None
    for child in list(body):body.remove(child)
    for node in nodes:body.append(deepcopy(node))
    if section is not None:body.append(section)
    work.mkdir()
    scoped=work/'range.docx'
    with import_stage('range_write','写入Word局部副本'):doc.save(scoped)
    return NativeReader(rt,scoped,work,assets,identities,editable=editable,object_seed=object_seed,
                        relationship_part=relationship_part)


def restore_provenance(rt, path, meta, work, staged):
    from asset_paths import RESERVED, asset_file
    raw=base64.b64decode(meta['source_b64'],validate=True)
    if sha(raw)!=meta['source_sha256']:raise BridgeError('Provenance source hash mismatch')
    if meta.get('document_key')!=sha(raw)[:16]:raise BridgeError('Provenance document binding mismatch')
    if len(raw)>10*1024*1024:raise BridgeError('Provenance source exceeds HRS limit')
    assets_root=(staged/'assets').resolve()
    total=0
    for name,digest in meta['assets'].items():
        if not name.startswith('assets/'):
            raise BridgeError('Unsafe provenance asset path')
        relative=name.removeprefix('assets/')
        if '/' in relative:
            try:
                target=asset_file(assets_root,relative)
            except ValueError as error:
                raise BridgeError('Unsafe provenance asset path: '+name) from error
        else:
            # Older sidecars also include incidental flat files in assets/.
            target=(assets_root/relative).resolve()
            if (target.parent!=assets_root or '\\' in relative or ':' in relative
                    or relative.rstrip(' .')!=relative or relative.split('.')[0].upper() in RESERVED):
                raise BridgeError('Unsafe provenance asset path: '+name)
        data=base64.b64decode(meta['blobs'][digest],validate=True)
        total+=len(data)
        if total>30*1024*1024 or sha(data)!=digest:raise BridgeError('Provenance asset limit/hash mismatch')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as output:
            output.write(data)
    ir=rt.analyze(raw,staged/'assets')
    if not ir['ok']:raise BridgeError('Provenance source fails the current HRS contract')
    blocks=ir['blocks'];mapping=meta['blocks']
    if len(mapping)!=len(blocks):raise BridgeError('Provenance block map is incomplete')
    scope=meta.get('body_scope')
    if scope is not None and scope!={'bookmark':'HBD_'+meta['document_key'],'kind':'wps-report-body-v1'}:raise BridgeError('Invalid provenance body scope')
    doc=read_document(path);regions=bookmark_regions(doc,(scope or {}).get('bookmark'))
    text_scripts = meta.get('native_text_scripts', False)
    if type(text_scripts) is not bool:
        raise BridgeError('Invalid native text script fingerprint policy')
    digest_native = native_hasher(doc.part, text_scripts=text_scripts)
    derived=meta.get('derived_sections',[])
    if not isinstance(derived,list) or len(derived)>1:raise BridgeError('Invalid derived section map')
    for section in derived:
        expected='HB_'+meta['document_key']+'_references'
        if not isinstance(section,dict) or section.get('kind')!='references' or section.get('bookmark')!=expected:
            raise BridgeError('Invalid references identity')
        nodes=regions.pop(expected,None)
        if nodes is None or digest_native(nodes)!=section.get('native_sha256'):
            raise BridgeError('REFERENCE_EDIT_UNSUPPORTED: 文末参考文献已修改或身份丢失，不能用旧源文覆盖当前内容')
    if set(regions)!={b['bookmark'] for b in mapping}:raise BridgeError('BRIDGE_IDENTITY_LOST or unknown block bookmarks')
    identities={}
    for b in blocks:
        if b.get('id'):
            identities[number_name(b['id'])]=({'table':'tbl','figure':'fig','image-group':'fig','heading':'sec','equation':'eq'}[b['type']],b['id'])
    result=[];changed=[];serializers=[];diagnostics=[]
    for entry in mapping:
        index=entry['index']
        if not isinstance(index,int) or not 0<=index<len(blocks):raise BridgeError('Invalid provenance block index')
        original=blocks[index]
        if entry['bookmark']!='HB_'+meta['document_key']+'_'+str(index) or original['type']!=entry['type'] or original.get('id')!=entry.get('id'):
            raise BridgeError('Provenance identity does not match original HRS source')
    byname={entry['bookmark']:entry for entry in mapping}
    for name,nodes in regions.items():
        entry=byname[name];index=entry['index'];original=blocks[index]
        if entry.get('native_drawing_extents')!=[list(e) for e in drawing_extents(nodes)]:
            raise BridgeError('IMAGE_LAYOUT_EDIT_UNSUPPORTED: current image dimensions differ from the mapped native layout')
        if digest_native(nodes)==entry['native_sha256']:
            result.append(original['source']);continue
        if any(n.tag==qn('w:footnoteReference') or (n.tag==qn('w:fldSimple') and 'NOTEREF' in n.get(qn('w:instr'),'').split()) for node in nodes for n in node.iter()):
            raise BridgeError('FOOTNOTE_EDIT_UNSUPPORTED: Word 中的脚注或含脚注块已经修改，当前不能准确回编；原文件保留。')
        changed.append({'index':index,'type':original['type'],'id':original.get('id')})
        reader=scan_range(rt,path,nodes,work/('block-'+str(index)),staged/'assets',identities)
        kind=original['type']
        paragraphs=[b for b in reader.top if b['kind']=='paragraph']
        tables=[b for b in reader.top if b['kind']=='table']
        if kind=='table':
            if len(tables)!=1:raise BridgeError('Edited data table requires one native table')
            data=deepcopy(original['data']);data['rows']=reader.table(tables[0])
            caption=next((p for p in paragraphs if p.get('style_name')=='表题'),None)
            if caption is None or any(p is not caption and p.get('display_text','').strip() for p in paragraphs):
                raise BridgeError('Edited table caption or extra surrounding content needs an explicit mapping')
            data['caption']=reader.caption(caption,'表')
            if data['schema']=='gfm-pipe-table-v1':
                serializers.append({'type':'gfm','data':{'caption':data['caption'],'rows':data['rows'],'align':data['align']},'id':original.get('id')})
                result.append(('serialize',len(serializers)-1))
            else:result.append(fenced('report-table',data))
        elif kind=='image-group':
            if len(tables)!=1:raise BridgeError('Edited group requires its native layout table')
            data=reader.group(tables[0],original['data'])
            caption=next((p for p in paragraphs if p.get('style_name')=='图题'),None)
            if caption is None or any(p is not caption and p.get('display_text','').strip() for p in paragraphs):
                raise BridgeError('Edited group caption or extra surrounding content needs an explicit mapping')
            data['caption']=reader.caption(caption,'图')
            serializers.append({'type':'image-group','data':data});result.append(('serialize',len(serializers)-1))
        elif kind=='equation':
            equation=display_equation(reader,paragraphs[0]) if len(paragraphs)==1 and not tables else None
            if equation is None:
                raise BridgeError('Edited block equation requires one native equation without discarded prose')
            serializers.append({'type':'equation','tex':reader.tex(equation.segment['object_id']),'id':original.get('id'),
                                'delimiter':original.get('delimiter','dollar')})
            result.append(('serialize',len(serializers)-1))
        elif kind=='heading':
            if len(paragraphs)!=1 or tables:raise BridgeError('Edited heading requires one native paragraph')
            p=paragraphs[0]
            if 'word_heading_level' in entry and entry['word_heading_level'] is None:
                if (p.get('style_name') or '').casefold()!='title':
                    raise BridgeError('Changing the document title role requires explicit organization')
                level=original['level']
            else:
                outline=p.get('outline_level_raw')
                if outline is None or not 0<=outline<=5:raise BridgeError('Edited heading has no supported real outline style')
                level=outline+1
                if 'word_heading_level' in entry:
                    target=entry['word_heading_level']
                    if type(target) is not int or not 1<=target<=6:raise BridgeError('Invalid mapped Word heading level')
                    level+=original['level']-target
                if not 1<=level<=6:raise BridgeError('Edited heading exceeds the source heading range')
            result.append('#'*level+' '+reader.paragraph(p)+((' {#'+original['id']+'}') if original.get('id') else '')+'\n')
        elif kind=='markdown':
            if tables:raise BridgeError('A new table in an ordinary block needs an explicit source object mapping')
            if any(p.get('numbering',{}).get('num_id') for p in paragraphs):raise BridgeError('Edited native list import is not yet supported')
            result.append('\n\n'.join(reader.paragraph(p) for p in paragraphs)+'\n\n')
        elif kind=='figure':
            drawings=[s['object_id'] for p in paragraphs for s in p.get('segments',[]) if s['kind']=='drawing']
            if len(drawings)!=1:raise BridgeError('Edited figure requires one native drawing')
            reader.check_drawing(drawings[0])
            d=deepcopy(original['data']);obj=reader.scan['objects'][drawings[0]]
            observed=obj['media'][0]['sha256'] if len(obj['media'])==1 else None
            unchanged=any(name and (staged/name).is_file() and sha((staged/name).read_bytes())==observed for name in (d.get('sourceAsset'),d.get('src')))
            if not unchanged:
                if d['kind']=='mermaid':raise BridgeError('Edited Mermaid rendition cannot be reverse-engineered as source')
                image=reader.image(drawings[0]);d={k:v for k,v in d.items() if k not in ('sourceAsset','rendition','rasterFallback')};d['src']=image['src']
            caption=next((p for p in paragraphs if p.get('style_name')=='图题'),None)
            if caption is None or any(p is not caption and p.get('plain_text','').strip() for p in paragraphs):
                raise BridgeError('Edited figure caption or extra surrounding content needs an explicit mapping')
            d['caption']=reader.caption(caption,'图')
            result.append(fenced('report-figure',d))
        else:raise BridgeError('Edited native block type is unsupported: '+kind)
        diagnostics.extend(reader.diagnostics)
    if serializers:
        serialized=call(rt,'serialize',items=serializers)
        result=[serialized[v[1]] if isinstance(v,tuple) else v for v in result]
    text=''.join(result)
    # Preserve BOM and all source bytes on a genuinely unchanged ordered document.
    if not changed and list(regions)==[entry['bookmark'] for entry in mapping]:candidate=raw
    else:candidate=text.encode('utf8')
    origin=meta.get('word_origin') if not changed and candidate==raw else None
    return candidate,changed,diagnostics,origin


def external_groups(reader, plan, recognition):
    """Prepare image assets and geometry before resolving captions or references."""
    groups = plan.get('groups',[])
    positions = {b['block_id']:i for i,b in enumerate(reader.top)}
    consumed = set(); prepared = {}
    for group in groups:
        if not isinstance(group, dict): raise BridgeError('Invalid Word image-group mapping')
        blocks = group.get('blocks'); columns = group.get('columns'); rows = group.get('rows')
        if not isinstance(blocks, list) or not blocks or not all(isinstance(v,str) and v in positions for v in blocks):
            raise BridgeError('Word group references unknown paragraph blocks')
        indices = [positions[v] for v in blocks]
        if indices != list(range(indices[0], indices[0]+len(indices))) or consumed.intersection(blocks):
            raise BridgeError('Word group paragraphs must be consecutive, ordered and used once')
        if type(columns) is not int or not 1 <= columns <= 4 or type(rows) is not int or not 1 <= rows <= 3:
            raise BridgeError('Word group geometry exceeds the existing HRS group contract')
        caption = group.get('caption',''); labels = group.get('showSubfigureLabels',False)
        if not isinstance(caption,str) or type(labels) is not bool:
            raise BridgeError('Invalid Word group caption or labels')
        images = []
        for ident in blocks:
            block = reader.facts[ident]
            if block['kind'] != 'paragraph': raise BridgeError('Word group must reference picture-only paragraphs')
            for segment in block['segments']:
                kind = segment['kind']
                if kind == 'drawing': images.append(reader.image(segment['object_id']))
                elif kind in ('bookmarkStart','bookmarkEnd','tab'): continue
                elif kind == 'text' and not segment['text'].strip(): continue
                else: raise BridgeError('Word group would consume non-image content; decision rejected')
        if not 2 <= len(images) <= 12 or not (rows-1)*columns < len(images) <= rows*columns:
            raise BridgeError('Word group image count does not match the declared grid')
        data = {'schema':'report-image-group-v1','id':reader.object_id('fig',blocks[0]),
                'columns':columns,'rows':rows,'showSubfigureLabels':labels,'caption':caption,'images':images}
        prepared[blocks[0]]=data
        consumed.update(blocks)
        reader.diagnostics.append({'code':'EXPLICIT_WORD_GROUP_APPLIED','blocks':blocks,'columns':columns,'rows':rows,
                                   'message':'Source-bound caller decision applied; following paragraphs remain unchanged.'})
    for group in recognition['groups']:
        block=group['blocks'][0];drawings=group['drawings']
        if block in consumed:continue
        reader.current_block=block
        try:images=[reader.image(drawing) for drawing in drawings]
        except (BridgeError,ValueError,OSError) as error:
            if not reader.editable:raise
            from .editable_import import warn
            warn(reader,'WORD_GROUP_AS_INDIVIDUAL_IMAGES','这组图片不能完整组合，已按原顺序保留可读取的图片。',detail=str(error))
            continue
        ident=reader.object_id('fig',block)
        prepared[block]=dict(schema='report-image-group-v1',id=ident,columns=group['columns'],rows=group['rows'],
                             showSubfigureLabels=False,caption='',images=images)
        reader.picture_ids[drawings[0]]=ident
        consumed.add(block)
    return prepared,consumed


def external_picture_table(reader, block, layout):
    """Bind unambiguous native cells to HRS slots, in physical drawing order."""
    from .recognition import picture_row
    drawings=layout['drawings'];cells=layout['cells'];ident=reader.object_id('fig',block['block_id'])
    for cell in cells:
        physical=reader.facts[cell['block_id']]
        if physical['children']!=cell['paragraphs'] or cell['v_merge_raw'] is not None:
            raise BridgeError('图片布局含嵌套表或纵向合并')
        for bid in cell['paragraphs']:
            p=reader.facts[bid]
            for span in p.get('hyperlink_ranges',[]):
                if any(s['kind']=='drawing' for s in p['segments'][span['start']:span['end']]):
                    raise BridgeError('图片本身带有链接，需保留其所在段落')
    if len(drawings)==1:
        data=dict(reader.image(drawings[0]),schema='report-figure-v1',id=ident,kind='image',alt='')
        return data,[cells],[]

    rows=defaultdict(list)
    for cell in cells:rows[cell['row']].append(cell)
    physical_columns=layout['columns'];columns=physical_columns
    image_rows=[];last_row={};captions=defaultdict(list);unplaced=[]
    for cells in rows.values():
        if any(cell['drawings'] for cell in cells):
            if len(cells)==1 and cells[0]['col_span']==physical_columns==1:
                columns=max(columns,len(cells[0]['drawings']))
            last_row={}
            for cell in cells:
                col=cell['col'];pictures=cell['drawings'];span=cell['col_span']
                if not pictures:
                    unplaced.append(cell);continue
                if len(pictures)>1:
                    in_one_row=any(picture_row(reader.facts[bid])==pictures for bid in cell['paragraphs'])
                    if not in_one_row or (physical_columns!=1 and len(pictures)!=span):
                        raise BridgeError('单元格内的图片无法按同一行对应到子图')
                    unplaced.append(cell)
                else:captions[pictures[0]].append(cell)
                last_row.update((col+offset,drawing) for offset,drawing in enumerate(pictures))
            if sorted(last_row)!=list(range(len(last_row))):
                raise BridgeError('图片行包含无法保留的空列')
            image_rows.append(list(last_row.values()))
        else:
            for cell in cells:
                single_slot=cell['col_span']==1 and (physical_columns!=1 or len(last_row)==1)
                drawing=last_row.get(cell['col']) if single_slot else None
                if drawing:captions[drawing].append(cell)
                else:unplaced.append(cell)
    if (not 1<=columns<=4 or not 1<=len(image_rows)<=3 or not 2<=len(drawings)<=12
            or any(len(row)!=columns for row in image_rows[:-1]) or len(image_rows[-1])>columns
            or [drawing for row in image_rows for drawing in row]!=drawings):
        raise BridgeError('图片布局超出 3 行、4 列或 12 张图，或无法保持原顺序')
    data=dict(schema='report-image-group-v1',id=ident,columns=columns,rows=len(image_rows),showSubfigureLabels=False,
              caption='',images=[reader.image(drawing) for drawing in drawings])
    return data,[captions[drawing] for drawing in drawings],unplaced


def picture_caption(text):
    """Check the caption slot before sending the group to the HRS serializer."""
    return len(text.encode('utf-16-le'))//2<=300 and (not text or text.splitlines()==[text])


def put_picture_caption(value, target, remainder):
    if picture_caption(value) and not value.startswith((':::','![')):
        target['caption']=value
    elif value:
        remainder.append(value+'\n')


def picture_table_captions(reader, picture, cell_captions, unplaced, caption):
    def paragraphs(cells):
        return [value for cell in cells for bid in cell['paragraphs']
                if (value:=reader.paragraph(without_segments(reader.facts[bid],lambda segment:segment['kind']=='drawing'),
                                            caption=True,formatting=False).strip())]

    remainder=[]
    if 'images' in picture:
        for image,cells in zip(picture['images'],cell_captions):
            put_picture_caption(' '.join(paragraphs(cells)),image,remainder)
        put_picture_caption(caption,picture,remainder)
    else:
        put_picture_caption(' '.join(paragraphs(cell_captions[0])+([caption] if caption else [])),picture,remainder)
    remainder.extend(text+'\n' for text in paragraphs(unplaced))
    return remainder


def prepare_pictures(reader,decisions,recognition,roles):
    from .editable_import import warn
    from .recognition import picture_row
    groups,group_blocks=external_groups(reader,decisions,recognition)
    tables={};singles={};failures={}
    for block in reader.top:
        bid=block['block_id'];layout=roles[bid].get('figure_layout')
        if bid in group_blocks:continue
        reader.current_block=bid
        try:
            if block['kind']=='table' and layout:
                tables[bid]=external_picture_table(reader,block,layout)
                reader.picture_ids[layout['drawings'][0]]=tables[bid][0]['id']
            elif block['kind']=='paragraph' and (drawings:=picture_row(block)):
                if len(drawings)==1 and (not reader.editable or (reader.scan['objects'][drawings[0]].get('media') and not block.get('hyperlinks'))):
                    singles[bid]=reader.image(drawings[0])
                    reader.picture_ids[drawings[0]]=reader.object_id('fig',bid)
        except (BridgeError,ValueError,OSError) as error:
            if not reader.editable:raise
            failures[bid]=error
            if block['kind']=='table':
                # When a layout cannot fit, keep the first surviving image as
                # the destination of the original figure's native bookmarks.
                for drawing in layout['drawings']:
                    try:reader.image(drawing)
                    except (ValueError,OSError):continue
                    reader.picture_ids[drawing]=reader.object_id('fig',bid)
                    break
        if bid in failures and block['kind']=='paragraph':
            warn(reader,'WORD_IMAGE_AS_CONTENT','这张图需按原位置核对。',detail=str(failures[bid]))
    # An automatic inline group that could not prepare can still retain the
    # native reference on the first readable image in its paragraph.
    for group in recognition['groups']:
        bid=group['blocks'][0]
        if bid in groups or bid in group_blocks:continue
        reader.current_block=bid
        for drawing in group['drawings']:
            try:reader.image(drawing)
            except (ValueError,OSError):continue
            reader.picture_ids[drawing]=reader.object_id('fig',bid)
            break
    reader.current_block=None
    return groups,group_blocks,tables,singles,failures


def serialize_import_objects(reader, chunks, pending):
    # The page request accepts at most 1000 records. Valid group captions and
    # image slots are bounded by the existing HRS source contract.
    for start in range(0,len(pending),1000):
        batch=pending[start:start+1000]
        sources=call(reader.rt,'serialize',items=[item for _,item in batch])
        if len(sources)!=len(batch):raise BridgeError('HRS 对象序列化结果与导入批次不一致')
        for (index,_),source in zip(batch,sources):chunks[index]=source


def import_external(rt,path,work,staged,structure_map=None,editable=False,*,source_sha256=None):
    from .recognition import analyze,load_decisions
    from . import editable_import as ordinary
    projection_diagnostics=[]
    if editable:
        path,projection_diagnostics=ordinary.project(path,work/'editable.docx')
    reader=NativeReader(rt,path,work,staged/'assets',editable=editable,
                        object_seed=source_sha256[:16] if source_sha256 else None)
    reader.diagnostics.extend(projection_diagnostics)
    if editable:
        body_scopes = [name for name in reader.word_bookmarks if name and ordinary.BODY_SCOPE.fullmatch(name)]
        if len(body_scopes) == 1 and reader.word_bookmarks[body_scopes[0]] == 1:
            front_skipped = ordinary.template_front_blocks(reader, body_scopes[0])
            if front_skipped:
                reader.top = [b for b in reader.top if b['block_id'] not in front_skipped]
                reader.scan['top_level_ids'] = [bid for bid in reader.scan['top_level_ids'] if bid not in front_skipped]
                reader.diagnostics.append({'code': 'WORD_TEMPLATE_FRONT_MATTER_SKIPPED', 'message': '已跳过母模板前置封面与目录区域。'})
        sections = [name for name in reader.word_bookmarks if name and ordinary.REFERENCE_SECTION.fullmatch(name)]
        if sections:
            reader.notes = ordinary.Notes(reader)
            recovered = (reader.notes.restore_references(reader, sections[0])
                         if len(sections)==1 and reader.word_bookmarks[sections[0]]==1 else set())
            if recovered:
                reader.top = [b for b in reader.top if b['block_id'] not in recovered]
                reader.scan['top_level_ids'] = [bid for bid in reader.scan['top_level_ids'] if bid not in recovered]
            else:
                ordinary.warn(reader,'WORD_REFERENCE_SECTION_RETAINED','参考文献与正文引用未能可靠配对，已保留 Word 中的文字。')
    decisions=load_decisions(reader,structure_map)
    recognition=analyze(reader,decisions)
    roles={r['block_id']:r for r in recognition['roles']}
    groups,group_blocks,tables,singles,picture_failures=prepare_pictures(reader,decisions,recognition,roles)
    equations={};unavailable={};equation_targets={}
    equation_anchors=[];bookmark_counts=reader.word_bookmarks
    for b in reader.top:
        equation=display_equation(reader,b)
        if equation is None:continue
        bid=b['block_id']
        try:tex=reader.tex(equation.segment['object_id'])
        except (BridgeError,ValueError,RuntimeError,OSError) as error:
            if not editable:raise
            unavailable[bid]=(equation,error)
            continue
        equations[bid]=(equation,tex)
        target=('eq',reader.object_id('eq',bid));equation_targets[bid]=target
        equation_anchors.extend((name,target) for name in equation.anchors if bookmark_counts[name]==1)
    # Map bookmarks placed on equation_description paragraphs (including joint
    # adjacent disambiguation when neighboring equations are claimed by peers).
    claimed_equations={
        r['relates_to']
        for r in recognition['roles']
        if r.get('role')=='equation_description' and r.get('relates_to') in equation_targets
    }
    resolved_eq_reviews=set()
    for idx,b in enumerate(reader.top):
        r=roles.get(b['block_id'])
        if not r or r.get('role')!='equation_description':
            continue
        eq_bid=r.get('relates_to')
        if eq_bid not in equation_targets:
            adj=[
                nb['block_id']
                for nb in (reader.top[idx-1] if idx>0 else None, reader.top[idx+1] if idx+1<len(reader.top) else None)
                if nb is not None and nb['block_id'] in equation_targets and nb['block_id'] not in claimed_equations
            ]
            if len(adj)==1:
                eq_bid=adj[0]
                r['relates_to']=eq_bid
                claimed_equations.add(eq_bid)
                if r.get('status')=='review' and set(r.get('evidence',()))<={'caption_prefix_pending_object_pair','ambiguous_object_pair'}:
                    r['status']='auto_rule'
                    resolved_eq_reviews.add(b['block_id'])
            else:
                eq_bid=None
        if eq_bid in equation_targets:
            eq_target=equation_targets[eq_bid]
            for s in b.get('segments',[]):
                if s['kind']=='bookmarkStart' and s.get('name') and bookmark_counts[s['name']]==1:
                    equation_anchors.append((s['name'],eq_target))
    if resolved_eq_reviews:
        recognition['review']=[it for it in recognition['review'] if it.get('block') not in resolved_eq_reviews]
    targets=reader.map_hyperlink_targets(recognition,decisions)
    for name,target in equation_anchors:
        reader.identities[name]=target;reader.link_targets[name]=target
    chunks=[];style_fragments=[];image_layouts=[];pending=[]
    def heading(text, style, level, prefix=''):
        projection='heading-list' if level>6 else 'heading'
        ident=reader.link_heading_ids.get(b['block_id'])
        source=('- ' if level>6 else '#' * level+' ')+text+(' {#'+ident+'}' if ident else '')+'\n'
        style_fragments.append((len(chunks),style,projection,prefix))
        chunks.append(source)
    def queue(item):
        pending.append((len(chunks),item));chunks.append('')

    def queue_group(data):
        queue({'type':'image-group','data':data})

    explicit_blocks={ident for g in decisions.get('groups',[]) for ident in g['blocks']}
    captions=recognition['captions']
    # Only native number bookmarks of identified captions acquire HRS object
    # semantics. Literal @fig / [[...]] text remains ordinary Word text.
    from wps_pipeline.native_output import sequence_field,number_bookmarks
    for target,cap in captions.items():
        if target not in targets:continue
        b=reader.facts[cap['block']]
        p=reader.body[b['source_locator']['body_child_index']]
        field=sequence_field(p)
        sequence=reader.caption_number(b,'图' if cap['kind']=='figure' else '表')
        names=(number_bookmarks(p,field['cache']) if field is not None and sequence else
               reader.field_bookmarks(b['segments'],*sequence[:2]) if sequence else ())
        for name in names:
            if bookmark_counts[name]==1:reader.identities[name]=targets[target]
    captioned={*groups,*tables,*singles,*(bid for bid,r in roles.items() if r['role']=='table')}-explicit_blocks
    skip={v['block'] for target,v in captions.items() if target in captioned}
    top=reader.top
    for i,b in enumerate(top):
        bid=b['block_id']
        if bid in skip:continue
        reader.current_block=bid
        pending_start=len(reader.detached)
        try:
            if bid in unavailable:
                equation,error=unavailable[bid]
                label=equation.number_label
                if equation.number is not None and (not label or re.fullmatch(r'[（(][ \t]*[)）]',label)):
                    label='（'+equation.number+'）'
                chunks.append(ordinary.unavailable_math(reader,equation.segment,error)+label+'\n')
                continue
            if bid in equations:
                equation,tex=equations[bid]
                queue({'type':'equation','tex':tex,'id':equation_targets[bid][1]})
                if equation.number is not None:
                    reader.diagnostics.append({'code':'WORD_EQUATION_NUMBER_NORMALIZED','block':bid,'source_number':equation.number,
                        'message':'已保留公式引用，显示编号由 HRS 按文档顺序生成。'})
                continue
            if bid in group_blocks:
                if bid not in groups:continue
                group=groups[bid];cap=captions.get(bid) if bid not in explicit_blocks else None
                remainder=[]
                if cap:
                    p=reader.facts[cap['block']]
                    if cap.get('labels') and not p.get('hyperlinks') and all(picture_caption(escaped(label)) for label in cap['labels']):
                        for image,label in zip(group['images'],cap['labels']):image['caption']=escaped(label)
                    else:put_picture_caption(reader.caption(p,'图'),group,remainder)
                queue_group(group);chunks.extend(remainder)
                if bid not in explicit_blocks:reader.diagnostics.append({'code':'WORD_INLINE_ROW_AS_GROUP','block':bid})
                continue
            if bid in picture_failures:raise picture_failures[bid]
            if b['kind']=='table':
                cap=reader.facts[captions[bid]['block']] if bid in captions else None
                if bid in tables:
                    picture,cells,unplaced=tables[bid]
                    remainder=picture_table_captions(reader,picture,cells,unplaced,reader.caption(cap,'图') if cap else '')
                    if 'images' in picture:
                        queue_group(picture)
                        reader.diagnostics.append({'code':'WORD_IMAGE_TABLE_AS_GROUP','block':bid,'images':len(picture['images']),
                                                   'rows':picture['rows'],'columns':picture['columns']})
                    else:
                        chunks.append(fenced('report-figure',picture))
                        reader.diagnostics.append({'code':'WORD_IMAGE_TABLE_AS_FIGURE','block':bid,'images':1})
                    if remainder:
                        ordinary.warn(reader,'WORD_FIGURE_TEXT_AS_PARAGRAPH','图中未能唯一对应的文字保留在图旁，请核对位置。')
                        chunks.extend(remainder)
                    continue
                data={'schema':'report-table-v1','id':reader.object_id('tbl',bid),
                      'caption':'','rows':reader.table(b)}
                if cap:data['caption']=reader.caption(cap,'表')
                chunks.append(fenced('report-table',data));continue
            if b['kind']!='paragraph':raise BridgeError('Unknown native top-level block')
            kinds=[s['kind'] for s in b['segments'] if s['kind'] not in ('bookmarkStart','bookmarkEnd')]
            role=(b.get('style_name') or '').casefold()
            if role=='表题' and not editable:
                if i+1>=len(top) or top[i+1]['kind']!='table':raise BridgeError('Unpaired native table caption')
                continue
            if role=='图题' and not editable:raise BridgeError('Unpaired native figure caption')
            if bid in singles:
                drawing=next(s['object_id'] for s in b['segments'] if s['kind']=='drawing')
                data=singles[bid]
                data.update(schema='report-figure-v1',id=reader.object_id('fig',bid),kind='image',alt='')
                obj=reader.scan['objects'][drawing]
                layout=None
                try:
                    width,height=int(obj['extent']['cx']),int(obj['extent']['cy'])
                    if width<=0 or height<=0:raise ValueError('Nonpositive picture extent')
                    layout={'id':data['id'],'source_sha256':obj['media'][0]['sha256'],'width_emu':width,'height_emu':height}
                except (KeyError,TypeError,ValueError):
                    if not editable:raise
                    ordinary.warn(reader,'WORD_IMAGE_EXTENT_UNRESOLVED','图片缺少有效显示尺寸，按原图比例导入。',object=drawing)
                remainder=[]
                if bid in captions:put_picture_caption(reader.caption(reader.facts[captions[bid]['block']],'图'),data,remainder)
                if layout:image_layouts.append(layout)
                chunks.append(fenced('report-figure',data));chunks.extend(remainder);continue
            if 'drawing' in kinds and not editable:raise BridgeError('Mixed or multiple native drawing paragraph')
            if role in CODE_BLOCK_STYLES and 'drawing' not in kinds and not b.get('hyperlinks'):
                code_lines = [reader.paragraph(b, plain=True, formatting=False)]
                j = i + 1
                while j < len(top) and top[j]['block_id'] not in skip and top[j]['kind'] == 'paragraph':
                    nb = top[j]
                    nrole = (nb.get('style_name') or '').casefold()
                    nkinds = [s['kind'] for s in nb['segments'] if s['kind'] not in ('bookmarkStart', 'bookmarkEnd')]
                    if nrole not in CODE_BLOCK_STYLES or 'drawing' in nkinds or nb.get('hyperlinks'):
                        break
                    skip.add(nb['block_id'])
                    code_lines.append(reader.paragraph(nb, plain=True, formatting=False))
                    j += 1
                code_body = '\n'.join(code_lines)
                if code_body.endswith('\n'):
                    code_body = code_body[:-1]
                ticks = '`' * max(3, max((len(m.group(0)) for m in re.finditer(r'`+', code_body)), default=0) + 1)
                chunks.append(f'{ticks}\n{code_body}\n{ticks}\n')
                continue
            resolved=roles[b['block_id']]
            is_heading_role = resolved['role']=='document_title' or (resolved['role']=='heading' and resolved['status']!='review' and 0<=resolved.get('level',1)-1<=5)
            text=reader.paragraph(b, strip_heading_bold=is_heading_role)
            if editable:
                number=b.get('numbering_effective') or {}
                if number.get('status')!='none' and number.get('num_id') not in (None,'0') and b.get('outline_level_raw') not in range(6):
                    serialized=ordinary.list_text(b,text)
                    if serialized is None:
                        ordinary.warn(reader,'WORD_LIST_LABEL_UNRESOLVED','列表编号定义不完整，正文保留，请核对原序号。')
                        serialized=text+'\n'
                    chunks.append(serialized);continue
            if resolved['role']=='document_title':
                heading(text,'Title',1);continue
            level=resolved.get('level',1)-1 if resolved['role']=='heading' and resolved['status']!='review' else None
            if level is not None and 0<=level<=5:
                prefix=''
                if level==5:
                    from wps_pipeline.numbered_candidates import numeric_expression
                    plain=b.get('plain_text','');parts=plain.split(maxsplit=1)
                    path=parts[0].split('.') if len(parts)==2 else []
                    # WPS's ordinary candidate parser covers up to five components.
                    # This adapter handles only the already confirmed sixth-level
                    # projection, never general prose, values, or Markdown numbering.
                    if len(path)==6 and all(v.isascii() and v.isdecimal() and int(v)>0 for v in path) and numeric_expression(plain) is None:
                        count=len(plain)-len(parts[1]);prefix=plain[:count]
                        text=reader.paragraph(b,text_skip=count,strip_heading_bold=True)
                        reader.diagnostics.append({'code':'OVERFLOW_CHAPTER_PREFIX_REMOVED','block':b['block_id'],'prefix':prefix,
                            'message':'Confirmed six-level chapter path removed from the list; Word native role is retained.'})
                heading(text,'Heading '+str(level+1),level+2,prefix)
                if level==5:reader.diagnostics.append({'code':'WORD_HEADING_OVERFLOW_AS_LIST','block':b['block_id'],
                    'message':'Body Heading 6 exceeds HRS H6 under the report title; emitted as a list with a source-bound role hint.'})
                continue
            if not text.strip() and not kinds and b.get('source_locator', {}).get('body_child_index') is not None:
                p_el = reader.body[b['source_locator']['body_child_index']]
                bottom_bdr = p_el.find(qn('w:pPr') + '/' + qn('w:pBdr') + '/' + qn('w:bottom'))
                if bottom_bdr is not None and bottom_bdr.get(qn('w:val')) not in (None, 'none', 'nil'):
                    chunks.append('---\n')
                    continue
            if b.get('numbering',{}).get('num_id'):raise BridgeError('External native lists require a verified list style mapping')
            if text.strip() and 'drawing' not in kinds and b.get('source_locator', {}).get('body_child_index') is not None:
                p_el = reader.body[b['source_locator']['body_child_index']]
                pbdr = p_el.find(qn('w:pPr') + '/' + qn('w:pBdr'))
                if pbdr is not None:
                    left_bdr = pbdr.find(qn('w:left'))
                    other_bdrs = [pbdr.find(qn('w:' + side)) for side in ('top', 'right', 'bottom')]
                    if left_bdr is not None and left_bdr.get(qn('w:val')) not in (None, 'none', 'nil') and all(
                        ob is None or ob.get(qn('w:val')) in (None, 'none', 'nil') for ob in other_bdrs
                    ):
                        chunks.append('\n'.join('> ' + ln if ln.strip() else '>' for ln in text.split('\n')) + '\n')
                        continue
            # A literal number in a Normal paragraph is not native list evidence.
            # Escape its punctuation so the existing Markdown parser keeps the text.
            literal=re.sub(r'^([ \t]*\d+)([.)])(?=[ \t])',lambda m:m[1]+'\\'+m[2],text)
            if literal!=text:
                reader.diagnostics.append({'code':'LITERAL_NUMBERED_PARAGRAPH_ESCAPED','block':b['block_id'],
                                           'message':'Typed number retained as body text; no list or heading inferred.'})
                text=literal
            chunks.append(text+'\n')
        except (BridgeError,ValueError,OSError) as error:
            if not editable:raise
            del reader.detached[pending_start:]
            chunks.append(ordinary.fallback_block(reader,b,error))
            if bid in captioned and bid in captions:
                chunks.append(reader.paragraph(reader.facts[captions[bid]['block']])+'\n')
        finally:
            chunks.extend(reader.detached);reader.detached.clear()
    if reader.notes:chunks.extend(reader.notes.definitions(reader))
    chunks.extend(reader.detached)
    serialize_import_objects(reader,chunks,pending)
    candidate='\n'.join(chunks).encode('utf8')
    source_sha256=source_sha256 or reader.scan['source_sha256']
    origin={'schema':'hrs-word-origin-v1','markdown_sha256':sha(candidate),'word_styles':[],'image_layouts':image_layouts,'source_docx_sha256':source_sha256}
    if source_sha256!=reader.scan['source_sha256']:recognition['scan_sha256']=reader.scan['source_sha256']
    recognition['source_sha256']=source_sha256
    recognition['review'].extend(reader.link_review.values())
    if editable:
        recognition['review'].extend({'block':d.get('block'),'text':d['message'],'role':'import_difference','evidence':[d['code']]} for d in reader.diagnostics if d.get('review'))
    recognition['unresolved']=len(recognition['review'])
    (staged/'word-recognition.json').write_text(json.dumps(recognition,ensure_ascii=False,indent=2),encoding='utf8')
    if recognition['review']:reader.diagnostics.append({'code':'WORD_STRUCTURE_REVIEW_RETAINED','review':recognition['review'],
        'message':'Unresolved candidate text retained; inspect word-recognition.json before treating its structure as accepted.'})
    offsets=[];offset=0
    for source in chunks:
        offsets.append(offset);offset+=len(source.encode('utf-16-le'))//2+1
    for index,style,projection,prefix in style_fragments:
        source=chunks[index];start=offsets[index]
        origin['word_styles'].append({'start':start,'end':start+len(source.encode('utf-16-le'))//2,
            'source_sha256':sha(source.encode('utf8')),'style':style,'projection':projection,
            **({'source_number_prefix':prefix} if prefix else {})})
    options={'show_equation_numbers':any(equation.number is not None for equation,_ in equations.values())}
    return candidate,[],reader.diagnostics,origin,options


def convert(rt,source,output,provenance=None,structure_map=None,import_mode='roundtrip'):
    if import_mode not in ('roundtrip','editable'):raise BridgeError('Unknown Word import mode')
    editable=import_mode=='editable'
    if editable and structure_map is not None:raise BridgeError('Source-bound structure maps require roundtrip mode')
    source=Path(source).resolve();output=new_path(output)
    with import_stage('snapshot_read','读取Word工作副本'):before=sha(source.read_bytes())
    mapping_diagnostics=[]
    try:meta=read_provenance(source,provenance)
    except (BridgeError,ValueError,KeyError,TypeError,AttributeError,OSError) as error:
        if not editable or provenance is not None:raise
        meta=None;mapping_diagnostics.append({'code':'WORD_MAPPING_NOT_USED','message':'同名来源映射不可用，按当前 Word 内容建立新工程。','detail':str(error)})
    if meta is not None and structure_map is not None:
        raise BridgeError('External structure maps cannot override existing bridge provenance')
    if meta is None and not editable:
        doc=read_document(source)
        if any(b.get(qn('w:name'),'').startswith('HB_') for b in doc._element.iter(qn('w:bookmarkStart'))):
            raise BridgeError('PROVENANCE_REQUIRED: provide the original .hrs-bridge.json for this bridge DOCX')
    maintenance={};imported_options=None
    with import_workspace(output.parent,maintenance) as work:
        staged=work/'project';(staged/'assets').mkdir(parents=True)
        if meta:
            roundtrip_work=work/'roundtrip';roundtrip_work.mkdir()
            try:candidate,changed,diagnostics,origin=restore_provenance(rt,source,meta,roundtrip_work,staged)
            except (BridgeError,ValueError,KeyError,TypeError,IndexError,AttributeError) as error:
                if getattr(error,'import_stage',None):raise
                if not editable or provenance is not None:raise
                meta=None;mapping_diagnostics.append({'code':'WORD_MAPPING_NOT_USED','message':'来源映射不能完整回编当前 Word，已按当前内容建立新工程。','detail':str(error)})
                candidate,changed,diagnostics,origin,imported_options=import_external(rt,source,work,staged,editable=True,source_sha256=before)
        else:candidate,changed,diagnostics,origin,imported_options=import_external(rt,source,work,staged,structure_map,editable=editable,source_sha256=before)
        diagnostics=mapping_diagnostics+diagnostics
        ir=rt.analyze(candidate,staged/'assets')
        from .runtime import source_contract_valid
        if not ir['ok'] or not source_contract_valid(ir):
            raise BridgeError('Recovered source fails HRS validation: '+json.dumps(ir['diagnostics'],ensure_ascii=False))
        if meta:
            original=rt.analyze(base64.b64decode(meta['source_b64'],validate=True))
            ids=lambda model:{b['id'] for b in model['blocks'] if b.get('id')}
            if ids(original)!=ids(ir):raise BridgeError('BRIDGE_IDENTITY_CHANGED: edited content cannot preserve all source identities')
        (staged/'report.md').write_bytes(candidate)
        from render_profile import normalize as normalize_profile, normalize_options
        profile=normalize_profile(meta.get('source_render_profile') if meta else 'free' if editable else 'engineering')
        (staged/'meta.json').write_text(json.dumps({'render_profile':profile,'render_options':normalize_options(meta.get('source_render_options') if meta else imported_options)})+'\n',encoding='utf8')
        if origin:(staged/'bridge-origin.json').write_text(json.dumps(origin,ensure_ascii=False,indent=2),encoding='utf8')
        link_reviews=[{'block':d.get('block'),'text':d['text'],'role':'hyperlink','evidence':[d['code']],'target':d.get('target'),'anchor':d.get('anchor'),'doc_location':d.get('doc_location')} for d in diagnostics if d['code']=='WORD_HYPERLINK_UNRESOLVED']
        if meta and link_reviews:
            record={'schema':'hrs-word-recognition-v1','source_sha256':before,'recognizer_version':'provenance-hyperlinks-v1','model_calls':0,
                    'roles':[],'review':link_reviews,'unresolved':len(link_reviews)}
            (staged/'word-recognition.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
        with import_stage('snapshot_read','核对Word工作副本'):source_copy=source.read_bytes()
        if sha(source_copy)!=before:raise BridgeError('Source DOCX changed during import')
        if editable:
            (staged/'output').mkdir(exist_ok=True)
            (staged/'output/word-import-source.docx').write_bytes(source_copy)
            if mapping_diagnostics:
                record_path=staged/'word-recognition.json'
                record=json.loads(record_path.read_text('utf8')) if record_path.is_file() else {'schema':'hrs-word-recognition-v1','source_sha256':before,'roles':[],'review':[],'model_calls':0}
                record['review'].extend({'role':'import_difference','text':d['message'],'evidence':[d['code']]} for d in mapping_diagnostics)
                record['unresolved']=len(record['review']);record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
        with import_stage('project_publish','交付导入工程'):staged.rename(output)
    result={'ok':True,'output':str(output),'markdown_sha256':sha(candidate),'changed_blocks':changed,
            'mode':'provenance-aware' if meta else 'external-editable' if editable else 'external-structured','diagnostics':diagnostics+ir['diagnostics']}
    if editable:result['source_copy']='output/word-import-source.docx'
    if not meta or link_reviews or mapping_diagnostics:
        record=json.loads((output/'word-recognition.json').read_text('utf8'))
        result['recognition']={'path':str(output/'word-recognition.json'),'unresolved':record['unresolved'],'model_calls':0}
        result['status']='NEEDS_REVIEW' if record['unresolved'] else 'COMPLETE'
    if maintenance.get('cleanup_pending'):
        result.update(cleanup_pending=True,cleanup_path=maintenance['cleanup_path'])
        result['diagnostics'].append({'code':'WORD_IMPORT_TEMP_CLEANUP_DEFERRED',
            'message':'工程已完成；临时文件暂时无法移除，已延后清理。','path':maintenance['cleanup_path']})
    return result
