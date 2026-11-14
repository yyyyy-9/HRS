"""Editable Word import adapters over the WPS scan, never an alternate recognizer.

Normal import retains readable content and reports local layout losses. The
strict provenance reader is unchanged. The original DOCX accompanies the project.
"""
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


def project(source, target):
    """Unwrap transparent Word containers before the existing scanner runs.

    Keep tracked deleted text visibly struck through; do not accept revisions or
    silently discard control contents. ZIP parts and relationships are copied.
    """
    from .docx_import import import_stage
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
                chosen = node.find(f'{{{MC}}}Fallback')
                if chosen is None:
                    chosen = node.find(f'{{{MC}}}Choice')
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


def field(reader, instruction, cached, caption, *, nested_reference=None):
    from .docx_import import escaped
    try:return reader.field(instruction,caption,nested_reference=nested_reference)
    except BridgeError:
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


def paragraph(reader, block, caption=False, plain=False, text_skip=0, formatting=True):
    from .docx_import import MATHTYPE_GOTO,MATHTYPE_REF,MATH_SEGMENTS,escaped
    if block.get('hyperlinks'):return reader.linked_paragraph(block,caption,plain,text_skip,formatting)
    previous=reader.current_block;reader.current_block=block.get('block_id',previous)
    result=[];stack=[]
    def emit(value):
        if stack:
            if stack[-1]['result']:stack[-1]['text'].append(value)
        else:result.append(value)
    def finish_field(instruction,cached,nested=()):
        if stack and stack[-1]['result'] and MATHTYPE_GOTO.fullmatch(''.join(stack[-1]['instruction'])):
            ref=MATHTYPE_REF.fullmatch(instruction)
            stack[-1]['references'].append(ref[1] if ref else None)
            emit(cached)
        else:
            emit(field(reader,instruction,cached,caption,nested_reference=nested[0] if len(nested)==1 else None))
    try:
        for segment in block.get('segments',[]):
            kind=segment['kind']
            if kind=='field_evidence':
                node=reader.object_xml(segment['object_id']);local=E.QName(node).localname
                if local=='fldSimple':
                    cached=''.join(n.text or '' for n in node.iter(qn('w:t')))
                    finish_field(node.get(qn('w:instr'),''),cached if plain else escaped(cached))
                elif local=='fldChar':
                    mode=node.get(qn('w:fldCharType'))
                    if mode=='begin':stack.append({'instruction':[],'text':[],'result':False,'references':[]})
                    elif mode=='separate' and stack:stack[-1]['result']=True
                    elif mode=='end' and stack:
                        frame=stack.pop();finish_field(''.join(frame['instruction']),''.join(frame['text']),frame['references'])
                elif local=='instrText' and stack:stack[-1]['instruction'].append(node.text or '')
                continue
            if stack and not stack[-1]['result']:continue
            if kind=='drawing':
                emit(detached_image(reader,segment['object_id']));continue
            if kind in MATH_SEGMENTS:
                emit(math_text(reader,segment))
                continue
            if kind in ('unsupported','legacy_picture','embedded_object','legacy_separator'):
                node=reader.object_xml(segment['object_id']);local=E.QName(node).localname
                if local in ('footnoteReference','endnoteReference'):
                    if reader.notes is None:reader.notes=Notes(reader.path)
                    emit(reader.notes.reference(local,node.get(qn('w:id'))));continue
                if local in ('footnoteRef','endnoteRef','pgNum'):continue
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
            if kind=='text' and text_skip:
                segment={**segment};count=min(text_skip,len(segment['text']));segment['text']=segment['text'][count:];text_skip-=count
            emit(reader._paragraph({'segments':[segment]},caption,plain,0,formatting))
        while stack:
            frame=stack.pop();emit(''.join(frame['text']) or escaped('[未闭合 Word 域，见源 Word]'))
            warn(reader,'WORD_FIELD_UNCLOSED','未闭合域的显示文字已保留，请核对源 Word。')
        return ''.join(result)
    finally:reader.current_block=previous


def image(reader, drawing):
    from PIL import Image,ImageOps
    obj=reader.scan['objects'][drawing];node=reader.object_xml(drawing)
    if len(obj.get('media',[]))!=1:raise BridgeError('图片没有唯一的内嵌资源；原对象保留在源 Word')
    media=obj['media'][0];ext=Path(media['part']).suffix.lower()
    if ext not in ('.png','.jpg','.jpeg','.gif','.webp','.svg','.bmp','.tif','.tiff'):
        raise BridgeError('图片 '+ext+' 需要兼容预览；原对象保留在源 Word')
    crop=next((n for n in node.iter() if E.QName(n).localname=='srcRect'),None)
    transform=next((n for n in node.iter() if E.QName(n).localname=='xfrm' and any(k in n.attrib for k in ('rot','flipH','flipV'))),None)
    cropped=crop is not None and any(float(v)!=0 for v in crop.attrib.values())
    transformed=transform is not None and any(v not in ('0','0.0','false','off') for k,v in transform.attrib.items() if k in ('rot','flipH','flipV'))
    raw=None
    if cropped or transformed or ext in ('.bmp','.tif','.tiff'):
        with Image.open(reader.work/'scan'/media['payload_ref']) as original:
            picture=original.convert('RGBA')
            if cropped:
                width,height=picture.size
                sides={k:float(crop.get(k,'0'))/100000 for k in ('l','t','r','b')}
                box=(round(width*sides['l']),round(height*sides['t']),round(width*(1-sides['r'])),round(height*(1-sides['b'])))
                if box[2]<=box[0] or box[3]<=box[1]:raise BridgeError('图片裁切范围无效')
                picture=picture.crop(box)
            if transform is not None:
                if transform.get('flipH') in ('1','true','on'):picture=ImageOps.mirror(picture)
                if transform.get('flipV') in ('1','true','on'):picture=ImageOps.flip(picture)
                angle=float(transform.get('rot','0'))/60000
                if angle:picture=picture.rotate(-angle,expand=True,resample=Image.Resampling.BICUBIC)
            buffer=BytesIO();picture.save(buffer,format='PNG');raw=buffer.getvalue();ext='.png'
        warn(reader,'WORD_IMAGE_RENDITION','图片裁切、旋转或格式已固化到兼容预览。',object=drawing)
    if obj.get('layout')!='inline':warn(reader,'WORD_FLOATING_IMAGE','浮动图片已按正文图片导入，请核对位置。',object=drawing)
    return reader.store_image(media,ext,raw)


def detached_image(reader, ident):
    from .docx_import import fenced,escaped
    key=reader.picture_ids.get(ident) or reader.object_id('fig',ident)
    try:data=reader.image(ident)
    except (BridgeError,ValueError,OSError) as error:
        warn(reader,'WORD_IMAGE_RETAINED_IN_SOURCE',str(error),object=ident)
        node=reader.object_xml(ident)
        text=''.join(n.text or '' for n in node.iter() if n.tag in (qn('w:t'),qn('a:t')))
        return escaped(text+' [图片待确认，见源 Word]')
    data.update(schema='report-figure-v1',id=key,kind='image',alt='')
    reader.detached.append(fenced('report-figure',data))
    warn(reader,'WORD_INLINE_IMAGE_RELOCATED','混排或单元格中的图片已保留为相邻图片对象，原位置留下引用。',object=ident)
    return '@fig:'+key


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


class Notes:
    PARTS={'footnoteReference':'footnotes','endnoteReference':'endnotes'}

    def __init__(self,path):
        self.path=path;self.used={};self.nodes={}
        with ZipFile(path) as archive:
            for kind,name in self.PARTS.items():
                part='word/'+name+'.xml'
                if part not in archive.namelist():continue
                root=E.fromstring(archive.read(part))
                for node in root:
                    ident=node.get(qn('w:id'))
                    if ident is not None and not node.get(qn('w:type')):self.nodes[kind,ident]=node

    def reference(self,kind,ident):
        key=(kind,ident)
        if key not in self.used:self.used[key]='word-note-'+str(len(self.used)+1)
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
        for key,label in self.used.items():
            pieces=pieces_by_note.get(key)
            if not pieces:
                pieces=[escaped('[脚注内容待确认，见源 Word]')]
                warn(reader,'WORD_NOTE_MISSING','Word 脚注引用缺少对应定义，请核对源 Word。',note=key[1])
            value='\n\n'.join(pieces).replace('\n','\n    ')
            result.append('[^'+label+']: '+value+'\n')
        return result

    @staticmethod
    def note_text(reader,scanned,blocks):
        pieces=[]
        for b in blocks:
            if b['kind']=='paragraph':pieces.append(scanned.paragraph(b))
            else:
                rows=scanned.table(b)
                pieces.append('\n'.join(' | '.join(c['text'] for c in row if c) for row in rows))
                warn(reader,'WORD_NOTE_TABLE_AS_TEXT','脚注中的表格已按行保留为文字，请核对布局。')
        return pieces
