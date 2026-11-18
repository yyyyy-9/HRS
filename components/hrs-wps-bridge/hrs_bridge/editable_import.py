"""Editable Word import adapters over the WPS scan, never an alternate recognizer.

Normal import retains readable content and reports local layout losses. The
strict provenance reader is unchanged. The original DOCX accompanies the project.
"""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree as E

from .ooxml import M, W
from .runtime import BridgeError

MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
PIC = 'http://schemas.openxmlformats.org/drawingml/2006/picture'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
V = 'urn:schemas-microsoft-com:vml'
O = 'urn:schemas-microsoft-com:office:office'
ASVG = 'http://schemas.microsoft.com/office/drawing/2016/svg/main'

DIRECT_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')
RASTER_IMAGE_EXTS = ('.bmp', '.tif', '.tiff', '.emf', '.wmf', '.jfif', '.dib', '.ico')
SUPPORTED_IMAGE_EXTS = DIRECT_IMAGE_EXTS + RASTER_IMAGE_EXTS

METADATA_MARKERS = {
    'permStart', 'permEnd', 'commentRangeStart', 'commentRangeEnd', 'commentReference',
    'customXmlInsRangeStart', 'customXmlInsRangeEnd', 'customXmlDelRangeStart', 'customXmlDelRangeEnd',
    'customXmlMoveFromRangeStart', 'customXmlMoveFromRangeEnd',
    'customXmlMoveToRangeStart', 'customXmlMoveToRangeEnd',
    'moveFromRangeStart', 'moveFromRangeEnd', 'moveToRangeStart', 'moveToRangeEnd',
    'proofErr', 'lastRenderedPageBreak',
}


def warn(reader, code, message, **detail):
    item={'code':code,'block':reader.current_block,'message':message,'review':True,**detail}
    if item not in reader.diagnostics:reader.diagnostics.append(item)
    return item


def _vml_length_emu(value, default_emu):
    if not value:
        return default_emu
    match = re.match(r'^\s*([0-9]+(?:\.[0-9]+)?)\s*(pt|px|in|cm|mm)?\s*$', str(value), re.I)
    if not match:
        return default_emu
    amount = float(match.group(1))
    unit = (match.group(2) or 'pt').lower()
    scale = {'pt': 12700, 'px': 9525, 'in': 914400, 'cm': 360000, 'mm': 36000}[unit]
    emu = round(amount * scale)
    return emu if emu > 0 else default_emu


def _vml_extent_emu(node):
    cx, cy = 3657600, 2743200
    current = node
    while current is not None:
        style = current.get('style') or ''
        if style:
            w_match = re.search(r'(?:^|;)\s*width\s*:\s*([^;]+)', style, re.I)
            h_match = re.search(r'(?:^|;)\s*height\s*:\s*([^;]+)', style, re.I)
            if w_match and h_match:
                return _vml_length_emu(w_match.group(1), cx), _vml_length_emu(h_match.group(1), cy)
        if isinstance(current.tag, str) and E.QName(current).localname in ('pict', 'object', 'r', 'p'):
            break
        current = current.getparent()
    return cx, cy


def _make_inline_drawing(rid, cx=3657600, cy=2743200):
    xml = (
        f'<w:drawing xmlns:w="{W}" xmlns:wp="{WP}" xmlns:a="{A}" xmlns:pic="{PIC}" xmlns:r="{R}">'
        f'<wp:inline><wp:extent cx="{int(cx)}" cy="{int(cy)}"/>'
        f'<a:graphic><a:graphicData uri="{PIC}">'
        f'<pic:pic><pic:blipFill><a:blip r:embed="{rid}"/></pic:blipFill></pic:pic>'
        f'</a:graphicData></a:graphic></wp:inline></w:drawing>'
    )
    return E.fromstring(xml)


def _make_pic_drawing(pic_node, default_cx=3657600, default_cy=2743200):
    cx, cy = default_cx, default_cy
    ext = pic_node.find(f'.//{{{A}}}xfrm/{{{A}}}ext')
    if ext is not None:
        try:
            w_val, h_val = int(ext.get('cx', '0')), int(ext.get('cy', '0'))
            if w_val > 0 and h_val > 0:
                cx, cy = w_val, h_val
        except ValueError:
            pass
    xml = (
        f'<w:drawing xmlns:w="{W}" xmlns:wp="{WP}" xmlns:a="{A}" xmlns:pic="{PIC}" xmlns:r="{R}">'
        f'<wp:inline><wp:extent cx="{int(cx)}" cy="{int(cy)}"/>'
        f'<a:graphic><a:graphicData uri="{PIC}"/></a:graphic></wp:inline></w:drawing>'
    )
    drawing = E.fromstring(xml)
    drawing.find(f'.//{{{A}}}graphicData').append(deepcopy(pic_node))
    return drawing


def _branch_has_rich_payload(branch):
    if branch is None:
        return False
    for child in branch.iter():
        if not isinstance(child.tag, str):
            continue
        local = E.QName(child).localname
        space = E.QName(child).namespace
        if space == A and local == 'blip' and (child.get(f'{{{R}}}embed') or child.find(f'.//{{{ASVG}}}svgBlip') is not None):
            return True
        if space == V and local == 'imagedata' and (child.get(f'{{{R}}}id') or child.get(f'{{{O}}}relid')):
            return True
        if space == M and local in ('oMath', 'oMathPara'):
            return True
        if space == W and local == 'tbl':
            return True
    return False


def project(source, target):
    """Unwrap transparent Word containers before the existing scanner runs.

    Keep tracked deleted text visibly struck through; do not accept revisions or
    silently discard control contents. ZIP parts and relationships are copied.
    """
    from .docx_import import import_stage
    from legacy_math import embedded_equation
    diagnostics=[]
    wrappers={'sdt','customXml','smartTag','ins','moveTo','del','moveFrom'}

    def unwrap(parent, node, content):
        children = list(content) if content is not None else []
        for child in children:
            node.addprevious(child)
        parent.remove(node)

    def adapt(parent):
        changed=False
        for node in list(parent):
            if not isinstance(node.tag,str):continue
            local=E.QName(node).localname;space=E.QName(node).namespace
            if space==MC and local=='AlternateContent':
                choice = node.find(f'{{{MC}}}Choice')
                fallback = node.find(f'{{{MC}}}Fallback')
                if choice is not None and _branch_has_rich_payload(choice):
                    chosen = choice
                elif fallback is not None:
                    chosen = fallback
                else:
                    chosen = choice
                if chosen is not None:
                    adapt(chosen)
                unwrap(parent, node, chosen)
                changed=True
                diagnostics.append({'code':'WORD_ALTERNATE_CONTENT','message':'采用 Word 保存的兼容显示内容；原对象保留在源 Word。'})
            elif space==W and local in wrappers:
                content=node.find(qn('w:sdtContent')) if local=='sdt' else node
                if content is not None:adapt(content)
                if local in ('del','moveFrom'):
                    for child in node.iter(qn('w:delText')):child.tag=qn('w:t')
                    for run in node.iter(qn('w:r')):
                        props=run.find(qn('w:rPr'))
                        if props is None:props=OxmlElement('w:rPr');run.insert(0,props)
                        props.append(OxmlElement('w:strike'))
                unwrap(parent, node, content)
                changed=True
                if local in ('ins','del','moveFrom','moveTo'):
                    diagnostics.append({'code':'WORD_TRACKED_CHANGE_RETAINED','message':'修订文字已保留，删除项以删除线显示；请确认修订。'})
            elif space==W and local=='pict':
                if len(node)==1 and node[0].tag==f'{{{V}}}rect' and node[0].get(f'{{{O}}}hr')=='t':
                    continue
                imagedata=[img for img in node.iter(f'{{{V}}}imagedata') if img.get(f'{{{R}}}id') or img.get(f'{{{O}}}relid')]
                texts=[''.join(t.text or '' for t in txbx.iter(qn('w:t'))).strip() for txbx in node.iter(qn('w:txbxContent'))]
                texts=[t for t in texts if t]
                if imagedata or texts:
                    for img in imagedata:
                        rid=img.get(f'{{{R}}}id') or img.get(f'{{{O}}}relid')
                        cx,cy=_vml_extent_emu(img)
                        node.addprevious(_make_inline_drawing(rid,cx,cy))
                    for text_val in texts:
                        t_el=OxmlElement('w:t');t_el.text=text_val
                        node.addprevious(t_el)
                    parent.remove(node)
                    changed=True
                    diagnostics.append({'code':'WORD_VML_PICTURE_CONVERTED','message':'旧版 VML 图形已按内嵌图片或文字导入。'})
            elif space==W and local=='object':
                if embedded_equation(node) is not None:
                    continue
                imagedata=[img for img in node.iter(f'{{{V}}}imagedata') if img.get(f'{{{R}}}id') or img.get(f'{{{O}}}relid')]
                if imagedata:
                    for img in imagedata:
                        rid=img.get(f'{{{R}}}id') or img.get(f'{{{O}}}relid')
                        cx,cy=_vml_extent_emu(img)
                        node.addprevious(_make_inline_drawing(rid,cx,cy))
                    parent.remove(node)
                    changed=True
                    diagnostics.append({'code':'WORD_OLE_PREVIEW_IMPORTED','message':'内嵌 OLE 对象已按其预览图像导入；原对象保留在源 Word。'})
            elif space==W and local=='drawing':
                for blip in node.iter(f'{{{A}}}blip'):
                    if not blip.get(f'{{{R}}}embed'):
                        svg_blip=blip.find(f'.//{{{ASVG}}}svgBlip')
                        if svg_blip is not None and svg_blip.get(f'{{{R}}}embed'):
                            blip.set(f'{{{R}}}embed',svg_blip.get(f'{{{R}}}embed'))
                            changed=True
                pics=[pic for pic in node.iter(f'{{{PIC}}}pic') if any(b.get(f'{{{R}}}embed') for b in pic.iter(f'{{{A}}}blip'))]
                if len(pics)>1:
                    extent=node.find(f'.//{{{WP}}}extent')
                    default_cx=int(extent.get('cx','3657600')) if extent is not None and str(extent.get('cx','')).isdigit() else 3657600
                    default_cy=int(extent.get('cy','2743200')) if extent is not None and str(extent.get('cy','')).isdigit() else 2743200
                    for pic in pics:
                        node.addprevious(_make_pic_drawing(pic,default_cx,default_cy))
                    extra_text=' '.join(t.strip() for t in (n.text or '' for n in node.iter() if n.tag in (qn('w:t'),f'{{{A}}}t')) if t.strip())
                    if extra_text:
                        t_el=OxmlElement('w:t');t_el.text=' '+extra_text
                        node.addprevious(t_el)
                    parent.remove(node)
                    changed=True
                    diagnostics.append({'code':'WORD_GROUP_DRAWING_UNPACKED','message':'组合图形中的多张子图已按顺序展开导入。'})
            elif space==W and local in METADATA_MARKERS and not len(node) and not (node.text or '').strip():
                parent.remove(node)
                changed=True
                if local=='commentReference':diagnostics.append({'code':'WORD_COMMENT_RETAINED_IN_SOURCE','message':'批注保留在源 Word，未转成正文。'})
            elif adapt(node):changed=True
        return changed

    def adapt_body(root):
        body = root.find(qn('w:body'))
        if body is None:
            raise BridgeError('Word 文档缺少正文区域')
        changed=False
        for child in list(body):
            if not isinstance(child.tag, str):
                body.remove(child)
                changed=True
                continue
            if child.tag in (qn('w:p'), qn('w:tbl'), qn('w:sectPr'), qn('w:bookmarkStart'), qn('w:bookmarkEnd')):
                continue
            paragraph = OxmlElement('w:p')
            body.replace(child, paragraph)
            changed=True
            if child.tag in (f'{{{M}}}oMath', f'{{{M}}}oMathPara'):
                paragraph.append(child)
                continue
            # Generic lxml elements are read by expanded QName. Unknown objects
            # keep their visible text and a reference to the unchanged source.
            if child.tag == qn('w:altChunk'):
                label = ''.join(child.itertext()).strip()
            else:
                label = ''.join(node.text or '' for node in child.iter(qn('w:t'), qn('a:t')))
            run = OxmlElement('w:r')
            text = OxmlElement('w:t')
            text.text = (label+' ' if label else '')+'[Word '+E.QName(child).localname+' 对象待确认，见源 Word]'
            run.append(text);paragraph.append(run)
            diagnostics.append({'code':'WORD_BODY_OBJECT_RETAINED_IN_SOURCE','message':text.text})
        return changed

    with import_stage('snapshot_read','读取Word工作副本'),ZipFile(source) as zin:
        replacements={}
        for name in ('word/document.xml','word/footnotes.xml','word/endnotes.xml'):
            try:raw=zin.read(name)
            except KeyError:continue
            root=E.fromstring(raw);changed=adapt(root)
            if name=='word/document.xml':changed=adapt_body(root) or changed
            if changed:replacements[name]=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
        if not replacements:return source,[]
        with import_stage('projection_write','写入转换副本'),ZipFile(target,'w') as zout:
            for info in zin.infolist():
                raw=replacements.get(info.filename)
                if raw is None:
                    with import_stage('snapshot_read','读取Word工作副本'):raw=zin.read(info)
                zout.writestr(info,raw)
    return target,[{**item,'review':True} for item in diagnostics]


def _is_note_style_segment(reader, seg):
    if seg.get('kind') != 'text':
        return False
    props = seg.get('run_properties_raw')
    props = {E.QName(p[0]).localname: dict(p[1]).get(qn('w:val'), '1') for p in props[3]} if props else {}
    if props.get('vertAlign') == 'superscript':
        return True
    rstyle = (props.get('rStyle') or '').strip()
    if not rstyle:
        return False
    sname = reader.char_styles.get(rstyle, rstyle.casefold())
    return sname in ('footnote reference', 'footnotereference', 'endnote reference', 'endnotereference') or rstyle.casefold() in ('footnotereference', 'endnotereference')


def field(reader, instruction, cached, caption, *, nested_reference=None):
    from .docx_import import escaped
    from wps_pipeline.assemble_reports import REF_FIELD

    match = REF_FIELD.fullmatch(instruction)
    if match and reader.notes and match[1] in reader.notes.references:
        return reader.notes.reference('reference', match[1])
    try:return reader.field(instruction,caption,nested_reference=nested_reference,cached=cached)
    except BridgeError:
        noteref = re.match(r'^\s*NOTEREF\s+"?([A-Za-z0-9_]+)"?(?=\s|$)', instruction, re.I)
        if noteref:
            if reader.notes is None:
                reader.notes = Notes(reader)
            target = reader.notes.bookmarks.get(noteref.group(1))
            if target is not None:
                return reader.notes.reference(*target)
        # Unknown fields are not discarded. Their stored result is ordinary
        # editable text; it is not represented as a live Word field in HRS.
        warn(reader,'WORD_FIELD_AS_TEXT','Word 域已按保存的显示结果导入；不再自动更新。',instruction=instruction.strip())
        return cached or escaped('[Word 域待确认：'+instruction.strip()+']')


def unavailable_math(reader,segment,error):
    warn(reader,'WORD_MATH_RETAINED_IN_SOURCE','此公式暂不能转为 LaTeX，原公式保留在源 Word。',
         object=segment['object_id'],detail=str(error))
    return '【公式待确认，见源 Word】'


def math_text(reader,segment):
    try:tex=reader.tex(segment['object_id'])
    except (BridgeError,ValueError,RuntimeError,OSError) as error:
        return unavailable_math(reader,segment,error)
    return '$'+tex+'$'


def paragraph(reader, block, caption=False, plain=False, text_skip=0, formatting=True, *, suppress_bold=False):
    from .docx_import import MATHTYPE_GOTO,MATHTYPE_REF,MATH_SEGMENTS,escaped
    if block.get('hyperlinks'):return reader.linked_paragraph(block,caption,plain,text_skip,formatting,suppress_bold=suppress_bold)
    previous=reader.current_block;reader.current_block=block.get('block_id',previous)
    result=[];stack=[];seg_buf=[]
    segments = [dict(s) if s.get('kind') == 'text' else s for s in block.get('segments', [])]

    def emit(value):
        if stack:
            if stack[-1]['result']:stack[-1]['text'].append(value)
        else:result.append(value)

    def flush_buf():
        if seg_buf:
            result.append(reader._paragraph({'segments': seg_buf}, caption, plain, 0, formatting, suppress_bold=suppress_bold))
            seg_buf.clear()

    def emit_maybe_note(value, current_idx):
        note = re.fullmatch(r'\[\^word-(note|ref)-\d+\]', value) if not stack else None
        if note:
            def bracket(segment, mark, matches):
                return segment['kind']=='text' and matches(segment['text'],mark) and (note[1]=='ref' or _is_note_style_segment(reader,segment))

            if seg_buf and bracket(seg_buf[-1], '[', str.endswith):
                peek = current_idx + 1
                while peek < len(segments) and segments[peek].get('kind') in ('bookmarkStart', 'bookmarkEnd'):
                    peek += 1
                if peek < len(segments) and bracket(segments[peek], ']', str.startswith):
                    left_txt = seg_buf[-1]['text'][:-1]
                    if left_txt:
                        seg_buf[-1] = {**seg_buf[-1], 'text': left_txt}
                    else:
                        seg_buf.pop()
                    segments[peek] = {**segments[peek], 'text': segments[peek]['text'][1:]}
        flush_buf()
        emit(value)

    def finish_field(instruction,cached,current_idx,nested=()):
        if stack and stack[-1]['result'] and MATHTYPE_GOTO.fullmatch(''.join(stack[-1]['instruction'])):
            ref=MATHTYPE_REF.fullmatch(instruction)
            stack[-1]['references'].append(ref[1] if ref else None)
            emit(cached)
        else:
            val = field(reader,instruction,cached,caption,nested_reference=nested[0] if len(nested)==1 else None)
            emit_maybe_note(val, current_idx)

    try:
        for idx, segment in enumerate(segments):
            kind=segment['kind']
            if kind=='field_evidence':
                node=reader.object_xml(segment['object_id']);local=E.QName(node).localname
                if local=='fldSimple':
                    cached=''.join(n.text or '' for n in node.iter(qn('w:t')))
                    finish_field(node.get(qn('w:instr'),''),cached if plain else escaped(cached), idx)
                elif local=='fldChar':
                    mode=node.get(qn('w:fldCharType'))
                    if mode=='begin':
                        stack.append({'instruction':[],'text':[],'result':False,'references':[]})
                    elif mode=='separate' and stack:stack[-1]['result']=True
                    elif mode=='end' and stack:
                        frame=stack.pop();finish_field(''.join(frame['instruction']),''.join(frame['text']),idx,frame['references'])
                elif local=='instrText' and stack:stack[-1]['instruction'].append(node.text or '')
                continue
            if stack and not stack[-1]['result']:continue
            if kind in ('bookmarkStart','bookmarkEnd'):continue
            if kind=='drawing':
                flush_buf()
                emit(detached_image(reader,segment['object_id']));continue
            if kind in MATH_SEGMENTS:
                flush_buf()
                emit(math_text(reader,segment))
                continue
            if kind in ('unsupported','legacy_picture','embedded_object','legacy_separator'):
                node=reader.object_xml(segment['object_id']);local=E.QName(node).localname
                if local in ('footnoteReference','endnoteReference'):
                    if reader.notes is None:reader.notes=Notes(reader)
                    emit_maybe_note(reader.notes.reference(local,node.get(qn('w:id'))), idx);continue
                if local in ('footnoteRef','endnoteRef','pgNum'):continue
                flush_buf()
                if local=='sym':
                    try:character=chr(int(node.get(qn('w:char')),16))
                    except (ValueError,TypeError):character='[符号待确认]'
                    emit(character if plain else escaped(character))
                    warn(reader,'WORD_FONT_SYMBOL','字体符号按字符值导入，请核对字形。',font=node.get(qn('w:font')));continue
                if kind=='legacy_separator':emit('\n---\n');continue
                text=''.join(n.text or '' for n in node.iter(qn('w:t')))
                emit((text if plain else escaped(text))+' 【Word '+local+' 对象待确认，见源 Word】')
                warn(reader,'WORD_INLINE_OBJECT_RETAINED_IN_SOURCE','局部对象暂不支持编辑转换，其位置和原件已保留。',object=segment['object_id'],kind=kind)
                continue
            if kind=='text':
                if text_skip:
                    count=min(text_skip,len(segment['text']));segment={**segment,'text':segment['text'][count:]};text_skip-=count
                if not segment['text']:
                    continue
            if stack:
                emit(reader._paragraph({'segments':[segment]},caption,plain,0,formatting,suppress_bold=suppress_bold))
            else:
                seg_buf.append(segment)
        flush_buf()
        while stack:
            frame=stack.pop();emit(''.join(frame['text']) or escaped('[未闭合 Word 域，见源 Word]'))
            warn(reader,'WORD_FIELD_UNCLOSED','未闭合域的显示文字已保留，请核对源 Word。')
        return ''.join(result)
    finally:reader.current_block=previous


def _convert_single_media(reader, drawing, media, node, layout):
    from PIL import Image, ImageOps
    ext = Path(media['part']).suffix.lower()
    if ext not in SUPPORTED_IMAGE_EXTS:
        raise BridgeError('图片 ' + ext + ' 需要兼容预览；原对象保留在源 Word')
    crop = next((n for n in node.iter() if E.QName(n).localname == 'srcRect'), None)
    transform = next((n for n in node.iter() if E.QName(n).localname == 'xfrm' and any(k in n.attrib for k in ('rot', 'flipH', 'flipV'))), None)
    cropped = crop is not None and any(float(v) != 0 for v in crop.attrib.values() if re.match(r'^-?\d+(?:\.\d+)?$', str(v)))
    transformed = transform is not None and any(v not in ('0', '0.0', 'false', 'off') for k, v in transform.attrib.items() if k in ('rot', 'flipH', 'flipV'))
    raw = None
    if ext == '.svg':
        if cropped or transformed:
            warn(reader, 'WORD_IMAGE_RENDITION', 'SVG 矢量图已按完整原图导入。', object=drawing)
    elif cropped or transformed or ext in RASTER_IMAGE_EXTS:
        with Image.open(reader.work / 'scan' / media['payload_ref']) as original:
            if ext in ('.emf', '.wmf'):
                try:
                    original.load(dpi=300)
                except Exception:
                    original.load()
            picture = original.convert('RGBA')
            if cropped:
                width, height = picture.size
                sides = {k: float(crop.get(k, '0')) / 100000 for k in ('l', 't', 'r', 'b')}
                x0 = max(0, min(width, round(width * sides['l'])))
                y0 = max(0, min(height, round(height * sides['t'])))
                x1 = max(0, min(width, round(width * (1 - sides['r']))))
                y1 = max(0, min(height, round(height * (1 - sides['b']))))
                if x1 > x0 and y1 > y0:
                    picture = picture.crop((x0, y0, x1, y1))
            if transform is not None:
                if transform.get('flipH') in ('1', 'true', 'on'):
                    picture = ImageOps.mirror(picture)
                if transform.get('flipV') in ('1', 'true', 'on'):
                    picture = ImageOps.flip(picture)
                angle = float(transform.get('rot', '0')) / 60000
                if angle:
                    picture = picture.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
            buffer = BytesIO()
            picture.save(buffer, format='PNG')
            raw = buffer.getvalue()
            ext = '.png'
        warn(reader, 'WORD_IMAGE_RENDITION', '图片裁切、旋转或矢量/位图格式已固化到兼容预览。', object=drawing)
    if layout != 'inline':
        warn(reader, 'WORD_FLOATING_IMAGE', '浮动图片已按正文图片导入，请核对位置。', object=drawing)
    return reader.store_image(media, ext, raw)


def image(reader, drawing):
    obj = reader.scan['objects'][drawing]
    node = reader.object_xml(drawing)
    media_list = obj.get('media', [])
    if not media_list:
        raise BridgeError('图形不含内嵌位图资源；原对象保留在源 Word')
    # When a single picture carries multiple blips (e.g. PNG preview + SVG/HD/effect
    # blip), prefer direct web-native formats first, then rasterizable formats.
    ordered = sorted(
        media_list,
        key=lambda m: (
            0 if Path(m['part']).suffix.lower() in DIRECT_IMAGE_EXTS
            else 1 if Path(m['part']).suffix.lower() in RASTER_IMAGE_EXTS
            else 2
        ),
    )
    last_error = None
    for media in ordered:
        try:
            result = _convert_single_media(reader, drawing, media, node, obj.get('layout'))
            if len(media_list) > 1:
                warn(reader, 'WORD_MULTI_BLIP_RESOLVED', '复合图元包含多份资源，已选用兼容图像导入。', object=drawing)
            return result
        except (BridgeError, ValueError, OSError) as error:
            last_error = error
    raise last_error or BridgeError('图片资源无法读取；原对象保留在源 Word')


def detached_image(reader, ident):
    from .docx_import import fenced, escaped
    obj = reader.scan['objects'][ident]
    node = reader.object_xml(ident)
    text = ' '.join(
        part.strip()
        for part in (n.text or '' for n in node.iter() if n.tag in (qn('w:t'), qn('a:t')))
        if part.strip()
    )
    if not obj.get('media'):
        if text:
            warn(reader, 'WORD_SHAPE_TEXT_IMPORTED', '文本框或图形中的文字已按正文保留。', object=ident)
            return escaped(text)
        warn(reader, 'WORD_DECORATIVE_SHAPE_IGNORED', '无文字的装饰图形未转入正文；原件保留在源 Word。', object=ident)
        return ''
    key = reader.picture_ids.get(ident) or reader.object_id('fig', ident)
    try:
        data = reader.image(ident)
    except (BridgeError, ValueError, OSError) as error:
        warn(reader, 'WORD_IMAGE_RETAINED_IN_SOURCE', str(error), object=ident)
        return escaped((text + ' ' if text else '') + '[图片待确认，见源 Word]')
    data.update(schema='report-figure-v1', id=key, kind='image', alt='')
    reader.detached.append(fenced('report-figure', data))
    warn(reader, 'WORD_INLINE_IMAGE_RELOCATED', '混排或单元格中的图片已保留为相邻图片对象，原位置留下引用。', object=ident)
    return (escaped(text) + ' ' if text else '') + '@fig:' + key


def detached_table(reader, block):
    from .docx_import import fenced
    key=reader.object_id('tbl',block['block_id'])
    data={'schema':'report-table-v1','id':key,'caption':'','rows':reader.table(block)}
    reader.detached.append(fenced('report-table',data))
    warn(reader,'WORD_NESTED_TABLE_RELOCATED','嵌套表已保留为相邻表格对象，原单元格留下引用。',object=block['block_id'])
    return '@tbl:'+key


def list_text(block,text):
    """Use WPS effective numbering facts, including style inheritance."""
    from .docx_import import escaped
    number=block.get('numbering_effective') or {};definition=number.get('definition') or {}
    label=number.get('label');level=number.get('ilvl') or 0
    if number.get('status')!='resolved' or not label:return None
    if definition.get('format')=='bullet':return '    '*level+'- '+text+'\n'
    if definition.get('format')=='decimal' and re.fullmatch(r'\d+[.)]',label):return '    '*level+label+' '+text+'\n'
    # Markdown cannot express every Word numbering alphabet/restart hierarchy.
    # Preserve the actual visible label rather than inventing a decimal series.
    return '    '*level+escaped(label)+' '+text+'\n'


def fallback_block(reader,block,error):
    """Retain every scanned cell/paragraph when its exact grid cannot map."""
    warn(reader,'WORD_LAYOUT_AS_CONTENT','局部版式无法直接表示，按阅读顺序保留内容；请核对源 Word。',detail=str(error))
    if block['kind']=='paragraph':return reader.paragraph(block)+'\n'
    parts=[]
    for ident in block.get('cells',[]):
        cell=reader.facts[ident]
        for child in cell['children']:
            item=reader.facts[child]
            parts.append(reader.paragraph(item) if item['kind']=='paragraph' else fallback_block(reader,item,error))
    return '\n\n'.join(parts)+'\n'


BODY_SCOPE = re.compile(r'HBD_([0-9a-f]{16})')
REFERENCE_SECTION = re.compile(r'HB_([0-9a-f]{16})_references')


def template_front_blocks(reader, marker):
    """Identify template cover/TOC blocks strictly preceding an intact HRS body scope."""
    body = reader.body
    start = next((node for node in body.iter(qn('w:bookmarkStart')) if node.get(qn('w:name')) == marker), None)
    if start is None or start.get(qn('w:id')) is None:
        return set()
    parent = start.getparent()
    if parent is body:
        first = body.index(start)
    elif parent is not None and parent.tag == qn('w:p') and parent.getparent() is body:
        siblings = start.itersiblings(preceding=True)
        if all(n.tag in (qn('w:pPr'), qn('w:bookmarkStart'), qn('w:bookmarkEnd')) for n in siblings):
            first = body.index(parent)
        else:
            return set()
    else:
        return set()
    if not any(b['source_locator']['body_child_index'] >= first for b in reader.top):
        return set()
    return {b['block_id'] for b in reader.top if b['source_locator']['body_child_index'] < first}


def reference_blocks(reader, marker):
    """Select an intact derived section by native bookmarks, including moved edges."""
    body = reader.body
    start = next(node for node in body.iter(qn('w:bookmarkStart')) if node.get(qn('w:name')) == marker)
    ends = [node for node in body.iter(qn('w:bookmarkEnd')) if node.get(qn('w:id')) == start.get(qn('w:id'))]
    if start.get(qn('w:id')) is None or len(ends) != 1:
        return []

    def edge(node, opening):
        parent = node.getparent()
        if parent is body:
            return body.index(node) + int(opening)
        if parent.tag == qn('w:p') and parent.getparent() is body:
            siblings = node.itersiblings(preceding=opening)
            if all(n.tag in (qn('w:pPr'), qn('w:bookmarkStart'), qn('w:bookmarkEnd')) for n in siblings):
                return body.index(parent) + int(not opening)
        return None

    first, last = edge(start, True), edge(ends[0], False)
    if first is None or last is None or first >= last:
        return []
    return [b for b in reader.top if first <= b['source_locator']['body_child_index'] < last]


class Notes:
    PARTS={'footnoteReference':'footnotes','endnoteReference':'endnotes'}

    def __init__(self,reader):
        self.path=reader.path;self.used={};self.nodes={};self.bookmarks={};self.references={}
        with ZipFile(self.path) as archive:
            for kind,name in self.PARTS.items():
                part='word/'+name+'.xml'
                if part not in archive.namelist():continue
                root=E.fromstring(archive.read(part))
                for node in root:
                    ident=node.get(qn('w:id'))
                    if ident is not None and not node.get(qn('w:type')):self.nodes[kind,ident]=node
        if self.nodes:
            active = {}
            for el in reader.body.iter(qn('w:bookmarkStart'), qn('w:bookmarkEnd'), qn('w:footnoteReference'), qn('w:endnoteReference')):
                ident = el.get(qn('w:id'))
                if ident is None:
                    continue
                if el.tag == qn('w:bookmarkStart'):
                    name = el.get(qn('w:name'))
                    if name:active[ident] = name
                elif el.tag == qn('w:bookmarkEnd'):
                    active.pop(ident, None)
                else:
                    for name in active.values():
                        self.bookmarks.setdefault(name, (E.QName(el).localname, ident))

    def restore_references(self, reader, marker):
        from wps_pipeline.assemble_reports import REF_FIELD
        from wps_pipeline.native_output import SEQ_FIELD, field_views
        from .docx_import import without_segments

        section = reference_blocks(reader, marker)
        if (len(section) < 2 or section[0].get('plain_text','').strip() != '参考文献' or
                section[0].get('outline_level_raw') != 0 or
                any(s['kind'] not in ('text','bookmarkStart','bookmarkEnd') for s in section[0]['segments'])):
            return set()
        name_pattern = re.compile('HR_'+REFERENCE_SECTION.fullmatch(marker)[1]+r'_[0-9a-f]{16}')
        entries = {}
        current = None
        for block in section[1:]:
            segments = block.get('segments', ())
            owned = [s['name'] for s in segments if s['kind']=='bookmarkStart' and name_pattern.fullmatch(s.get('name') or '')]
            if not owned:
                if current is None or re.match(r'\s*\[\s*\d+\s*\]', block.get('display_text','')):
                    return set()
                current[1].append(block)
                continue
            leading = reader.leading_field(block)
            if len(owned)!=1 or reader.word_bookmarks[owned[0]]!=1 or not leading:
                return set()
            start, end, instruction, cached = leading
            prefix = ''.join(s.get('text','') for s in segments[:start]).strip()
            tail = next((s for s in segments[end:] if s['kind'] not in ('bookmarkStart','bookmarkEnd')), {})
            marker_text = re.match(r'\][ \t]?', tail.get('text',''))
            if (prefix!='[' or not marker_text or not cached.strip().isdigit() or
                    not SEQ_FIELD.fullmatch(instruction) or instruction.split()[1].casefold()!='hrsreference' or
                    owned[0] not in reader.field_bookmarks(segments, start, end)):
                return set()
            excluded = {id(s) for s in segments[:end]}
            current = len(marker_text[0]), [without_segments(block, lambda s: id(s) in excluded)]
            entries[owned[0]] = current

        if not entries:
            return set()
        positions = {b['source_locator']['body_child_index'] for b in section}
        citations = {
            match[1] for index, node in enumerate(reader.body) if index not in positions
            for view in field_views(node) if (match := REF_FIELD.fullmatch(view['instruction']))
            and name_pattern.fullmatch(match[1])
        }
        if entries.keys() != citations:
            return set()
        self.references = entries
        return {b['block_id'] for b in section}

    def reference(self,kind,ident):
        key=(kind,ident)
        if key not in self.used:
            self.used[key]=('word-ref-' if kind=='reference' else 'word-note-')+str(len(self.used)+1)
        return '[^'+self.used[key]+']'

    def definitions(self,reader):
        from .docx_import import scan_range,escaped
        notes=list(self.used.items())
        pieces_by_note={}
        for kind,name in self.PARTS.items():
            nodes=[];ranges={}
            for key,_ in notes:
                if key[0]!=kind or key not in self.nodes:continue
                start=len(nodes)
                nodes.extend(n for n in self.nodes[key] if n.tag in (qn('w:p'),qn('w:tbl')))
                ranges[key]=(start,len(nodes))
            if not nodes:continue
            # Footnotes and endnotes own their own relationships. Resolving
            # an rId against the main document can attach a different object.
            scanned=scan_range(reader.rt,self.path,nodes,reader.work/name,reader.assets,reader.identities,
                               editable=True,object_seed=reader.object_seed+'-'+name,
                               relationship_part='word/_rels/'+name+'.xml.rels')
            scanned.notes=self
            for key,(start,end) in ranges.items():
                pieces_by_note[key]=self.note_text(reader,scanned,scanned.top[start:end])
            reader.diagnostics.extend(scanned.diagnostics);reader.detached.extend(scanned.detached)
        result=[]
        for key,label in list(self.used.items()):
            if key[0]=='reference':
                skip, blocks = self.references[key[1]]
                pieces=self.note_text(reader,reader,blocks,first_skip=skip)
            else:
                pieces=pieces_by_note.get(key)
            if not pieces:
                pieces=[escaped('[脚注内容待确认，见源 Word]')]
                warn(reader,'WORD_NOTE_MISSING','Word 脚注引用缺少对应定义，请核对源 Word。',note=key[1])
            value='\n\n'.join(pieces).replace('\n','\n    ')
            result.append('[^'+label+']: '+value+'\n')
        return result

    @staticmethod
    def note_text(reader,scanned,blocks,*,first_skip=0):
        pieces=[]
        for i,b in enumerate(blocks):
            if b['kind']=='paragraph':pieces.append(scanned.paragraph(b,text_skip=first_skip if i==0 else 0))
            else:
                rows=scanned.table(b)
                pieces.append('\n'.join(' | '.join(c['text'] for c in row if c) for row in rows))
                warn(reader,'WORD_NOTE_TABLE_AS_TEXT','脚注中的表格已按行保留为文字，请核对布局。')
        return pieces
