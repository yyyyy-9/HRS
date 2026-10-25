"""Engineering report source contract v1 and deterministic block IR.

Only Python stdlib; safe to import from the offline editor and future DOCX assembler.
This parser deliberately validates the engineering extensions rather than claiming a
complete CommonMark/GFM AST. Markdown paragraphs remain exact source ranges.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import dataclass
import json
import hashlib
import math
from pathlib import Path
import re
import sys
from reference_context import masked_context
from html_assets import references as html_image_references
from pipe_table_contract import parse_at as parse_pipe_table_at
from equation_contract import parse_equation
from asset_paths import ASSET, normalize_asset, asset_file

FORMAT='engineering-report-v1'
IR_VERSION='engineering-report-ir-v1'
ID=re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
EMF_ASSET=re.compile(r'^assets/([a-f0-9]{16})\.emf$',re.I)
SOURCE_ASSET=re.compile(r'^assets/([a-f0-9]{16})\.(pdf|emf|svg|png|jpe?g|webp)$',re.I)
FENCE_OPEN=re.compile(r'^ {0,3}(`{3,}|~{3,})([^\r\n]*)$')
HEADING=re.compile(r'^ {0,3}(#{1,6})(?:[ \t]+|$)(.*?)(?:[ \t]+#+[ \t]*)?$')
REF=re.compile(r'(?<![A-Za-z0-9_\\-])@(fig|tbl|sec|eq):([A-Za-z][A-Za-z0-9_-]{0,63})\b')
GROUP_OPEN=re.compile(r'^ {0,3}:::[ \t]+\{([^\r\n]*)\}[ \t]*$')
GROUP_CLOSE=re.compile(r'^ {0,3}:::[ \t]*$')
GROUP_IMAGE=re.compile(r'^!\[((?:\\.|[^\]\\])*)\]\(([^\s()]+)\)(?:\s+\{([^\r\n{}]+)\})?$')
SECTION_ANCHOR=re.compile(r'[ \t]+\{#([^{}\s]+)\}[ \t]*$')
IMAGE=re.compile(r'!\[[^\]]*\]\((assets/[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.(?:png|jpe?g|gif|webp|svg))(?:\s+"[^"]*")?\)',re.I)
LIST_MARKER=re.compile(r'^ {0,3}<!-- hrs:list style=([A-Za-z-]+) -->[ \t]*$')
LIST_STYLES={'bullet','decimal','lower-alpha','paren-decimal','paren-lower-alpha'}
ANY_IMAGE=re.compile(r'!\[[^\]]*\]\(([^)]+)\)')

class ContractError(ValueError): pass


def _check_id(value, prefix):
    if (not isinstance(value,str) or not ID.fullmatch(value) or
            not value.startswith(prefix+'-') or len(value)<=len(prefix)+1):
        raise ContractError('对象 ID 必须符合 '+prefix+'-… 的稳定标识规则')


def validate_table(obj):
    if not isinstance(obj,dict) or obj.get('schema')!='report-table-v1':
        raise ContractError('应为 report-table-v1 对象')
    _check_id(obj.get('id'),'tbl')
    if not isinstance(obj.get('caption'),str) or len(obj['caption'])>300:
        raise ContractError('表题长度不能超过 300 字')
    rows=obj.get('rows')
    if not isinstance(rows,list) or not 1<=len(rows)<=100:
        raise ContractError('表格行数必须为 1–100')
    cols=len(rows[0]) if isinstance(rows[0],list) else 0
    if not 1<=cols<=30 or any(not isinstance(r,list) or len(r)!=cols for r in rows):
        raise ContractError('表格列数必须为 1–30，且所有行等宽')
    covered=set()
    for r,row in enumerate(rows):
        for c,cell in enumerate(row):
            if cell is None:
                if (r,c) not in covered: raise ContractError('无主单元格的空占位')
                continue
            if not isinstance(cell,dict) or not isinstance(cell.get('text'),str) or len(cell['text'])>30000:
                raise ContractError(f'单元格 {r+1}:{c+1} 内容无效')
            rs=cell.get('rowspan');cs=cell.get('colspan')
            if type(rs)!=int or type(cs)!=int or rs<1 or cs<1 or r+rs>len(rows) or c+cs>cols:
                raise ContractError(f'单元格 {r+1}:{c+1} 跨度无效')
            for rr in range(r,r+rs):
                for cc in range(c,c+cs):
                    if (rr,cc) in covered:raise ContractError('单元格合并区域重叠')
                    covered.add((rr,cc))
                    if (rr,cc)!=(r,c) and rows[rr][cc] is not None:
                        raise ContractError('合并区域其他位置必须是 null')
    result={'schema':obj['schema'],'id':obj['id'],'caption':obj['caption'],'rows':rows}
    if 'columnWidths' in obj:
        widths=obj['columnWidths']
        if (not isinstance(widths,list) or len(widths)!=cols or
            any(type(value) not in (int,float) or not 0<value<=100 or not math.isfinite(value) for value in widths) or
            abs(sum(widths)-100)>0.000001):
            raise ContractError('列宽须为与列数相同的正数百分比，合计 100')
        result['columnWidths']=widths[:]
    if 'align' in obj:
        align=obj['align']
        if not isinstance(align,list) or len(align)!=cols or any(value is not None and value not in ('left','right','center') for value in align):
            raise ContractError('表格列对齐信息无效')
        result['align']=align[:]
    if 'verticalAlign' in obj:
        if obj['verticalAlign'] not in ('top','middle','bottom'):
            raise ContractError('单元格垂直对齐须为 top / middle / bottom')
        result['verticalAlign']=obj['verticalAlign']
    # Unknown extension fields are not silently dropped from normalized IR.
    # The caller also produces a diagnostic so formal compilers can reject
    # unsupported semantics explicitly instead of fabricating an output.
    extras={key:value for key,value in obj.items() if key not in
            {'schema','id','caption','rows','columnWidths','align','verticalAlign'}}
    if extras:result['extensions']=extras
    return result


def validate_figure(obj):
    if not isinstance(obj,dict) or obj.get('schema')!='report-figure-v1':
        raise ContractError('应为 report-figure-v1 对象')
    _check_id(obj.get('id'),'fig')
    if not isinstance(obj.get('caption'),str) or len(obj['caption'])>300:
        raise ContractError('图题长度不能超过 300 字')
    kind=obj.get('kind')
    if kind=='image':
        if not isinstance(obj.get('src'),str) or normalize_asset(obj['src'])!=obj['src']:
            raise ContractError('图片路径必须位于本项目 assets/ 下')
        if not isinstance(obj.get('alt',''),str) or len(obj.get('alt',''))>300:
            raise ContractError('图片替代文字无效')
        result={'schema':obj['schema'],'id':obj['id'],'caption':obj['caption'],
                'kind':'image','src':obj['src'],'alt':obj.get('alt','')}
        vector=obj.get('vectorSource')
        if vector is not None:
            matched=EMF_ASSET.fullmatch(vector)
            if not matched or obj['src'].lower() not in {'assets/'+matched[1].lower()+ext for ext in ('.png','.svg')}:
                raise ContractError('EMF 源图必须与同名 SVG/PNG 预览关联')
            result['vectorSource']=vector
        fallback=obj.get('rasterFallback')
        if fallback is not None:
            name=re.fullmatch(r'assets/([a-f0-9]{16})\.svg',obj['src'],re.I)
            if not name or not isinstance(fallback,str) or fallback.lower()!='assets/'+name[1].lower()+'.png':
                raise ContractError('矢量 SVG 的备用 PNG 必须是同名附件')
            result['rasterFallback']=fallback
        # New optional source/preview relationship (old objects remain valid).
        # An original source is stored as its exact bytes under the same stem
        # as the display rendition, independent of Word/HTML output decisions.
        source=obj.get('sourceAsset')
        if source is not None:
            source_match=SOURCE_ASSET.fullmatch(source) if isinstance(source,str) else None
            preview_match=re.fullmatch(r'assets/([a-f0-9]{16})\.(png|jpe?g|webp|svg)',obj['src'],re.I)
            if not source_match or not preview_match or source_match[1].lower()!=preview_match[1].lower():
                raise ContractError('图形原件与预览必须位于 assets/，具有相同的 16 位资源 ID')
            ext=source_match[2].lower();visible=preview_match[2].lower()
            if ext=='pdf' and visible!='png':
                raise ContractError('PDF 原件必须使用同名 PNG 作为排版预览')
            if ext=='emf' and visible not in ('png','svg'):
                raise ContractError('EMF 原件只能对应同名 PNG/SVG 预览')
            if vector is not None and source.lower()!=vector.lower():
                raise ContractError('sourceAsset 与原有 vectorSource 不一致')
            result['sourceAsset']=source
        rendition=obj.get('rendition')
        if rendition is not None:
            if not isinstance(rendition,dict) or set(rendition)-{'format','dpi','page','width','height','engine'}:
                raise ContractError('图形预览元数据字段无效')
            if rendition.get('format') not in ('png','svg','webp','jpeg'):
                raise ContractError('图形预览格式无效')
            if 'dpi' in rendition and (isinstance(rendition['dpi'],bool) or not isinstance(rendition['dpi'],(int,float)) or not math.isfinite(rendition['dpi']) or not 0<rendition['dpi']<=600):
                raise ContractError('图形预览有效 DPI 必须大于 0 且不超过 600；未知时省略')
            if not isinstance(rendition.get('page'),int) or rendition['page']!=1:
                raise ContractError('图形预览当前仅支持 PDF 第 1 页')
            if rendition['format']!=obj['src'].rsplit('.',1)[-1].lower().replace('jpg','jpeg'):
                raise ContractError('图形预览格式与 src 后缀不一致')
            for field in ('width','height'):
                if field in rendition and (not isinstance(rendition[field],int) or not 1<=rendition[field]<=4096):
                    raise ContractError('图形预览像素尺寸超出限制')
            if 'engine' in rendition and (not isinstance(rendition['engine'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,36}',rendition['engine'])):
                raise ContractError('图形预览渲染引擎名称无效')
            result['rendition']=dict(rendition)
        extras={key:value for key,value in obj.items() if key not in
                {'schema','id','caption','kind','src','alt','vectorSource','rasterFallback','sourceAsset','rendition'}}
        if extras:result['extensions']=extras
        return result
    if kind=='mermaid':
        if not isinstance(obj.get('source'),str) or not obj['source'].strip() or len(obj['source'])>50000:
            raise ContractError('Mermaid 图形源数据无效')
        result={'schema':obj['schema'],'id':obj['id'],'caption':obj['caption'],
                'kind':'mermaid','source':obj['source']}
        extras={key:value for key,value in obj.items() if key not in
                {'schema','id','caption','kind','source'}}
        if extras:result['extensions']=extras
        return result
    raise ContractError('图形 kind 只能为 image 或 mermaid')


def parse_image_group(source):
    lines=source.replace('\r\n','\n').replace('\r','\n').rstrip().split('\n')
    opening=GROUP_OPEN.fullmatch(lines[0])
    if not opening or not GROUP_CLOSE.fullmatch(lines[-1]):raise ContractError('组图围栏未闭合或格式错误')
    oid=None;columns=None;rows=None;labels=None
    for item in opening[1].split():
        if item.startswith('#') and oid is None:oid=item[1:]
        elif re.fullmatch(r'layout-ncol=[1-4]',item) and columns is None:columns=int(item[-1])
        elif re.fullmatch(r'layout-nrow=[1-3]',item) and rows is None:rows=int(item[-1])
        elif item in ('subfig-labels=on','subfig-labels=off') and labels is None:labels=item.endswith('on')
        else:raise ContractError('组图围栏包含未知或重复属性')
    _check_id(oid,'fig')
    if not re.fullmatch(r'fig-[A-Za-z0-9_-]{1,60}',oid):raise ContractError('组图 ID 必须为 fig- 开头的稳定标识')
    if columns is None:raise ContractError('组图必须指定每行 1–4 列')
    images=[];caption='';seen_caption=False
    for line in lines[1:-1]:
        if not line.strip():continue
        image=GROUP_IMAGE.fullmatch(line)
        if image and not seen_caption:
            if normalize_asset(image[2])!=image[2]:raise ContractError('组图图片必须位于本项目 assets/ 下')
            text=re.sub(r'\\([\\\[\]])',r'\1',image[1])
            if len(text)>300:raise ContractError('子图说明最多 300 字')
            item={'src':image[2],'caption':text}
            if image[3]:
                props={}
                for chunk in image[3].split():
                    m=re.fullmatch(r'(source|fallback|format|dpi|page|width|height|engine)=([^\s{}]+)',chunk)
                    if not m or m[1] in props:raise ContractError('组图图片元数据包含未知或重复属性')
                    props[m[1]]=m[2]
                if 'source' in props:
                    original=props['source']
                    mat=SOURCE_ASSET.fullmatch(original)
                    if not mat:raise ContractError('组图原始资源路径无效')
                    if mat[2].lower() in ('pdf','emf') and image[2].lower()!='assets/'+mat[1].lower()+'.png':
                        raise ContractError('组图 EMF/PDF 原件必须与 PNG 预览同名')
                    item['sourceAsset']=original
                if 'fallback' in props:
                    mat=re.fullmatch(r'assets/([a-f0-9]{16})\.svg',image[2],re.I)
                    if not mat or props['fallback'].lower()!='assets/'+mat[1].lower()+'.png':
                        raise ContractError('组图备用 PNG 必须与 SVG 同名')
                    item['rasterFallback']=props['fallback']
                rendition={}
                if 'dpi' in props:
                    if not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,4})?',props['dpi']) or not 0<float(props['dpi'])<=600:raise ContractError('组图有效 DPI 无效')
                    rendition['dpi']=float(props['dpi'])
                for key in ('page','width','height'):
                    if key in props:
                        if not re.fullmatch(r'[0-9]{1,5}',props[key]) or not 1<=int(props[key])<=20000:
                            raise ContractError('组图预览尺寸/分辨率参数无效')
                        rendition[key]=int(props[key])
                if 'format' in props:
                    if props['format'] not in ('png','svg','jpeg','webp'):raise ContractError('组图预览格式无效')
                    rendition['format']=props['format']
                if 'engine' in props:
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,36}',props['engine']):raise ContractError('组图渲染引擎名称无效')
                    rendition['engine']=props['engine']
                if rendition:item['rendition']=rendition
            images.append(item);continue
        if seen_caption or line.startswith((':::','![')):raise ContractError('组图只允许本地图片行和最后一行组图题')
        if line!=line.strip() or len(line)>300:raise ContractError('组图题须为一行文字，最多 300 字，无首尾空白')
        caption=line;seen_caption=True
    if not 2<=len(images)<=12:raise ContractError('组图支持 2–12 张图片')
    if len(images)>columns*(rows or 3):raise ContractError('组图图片超过行列容量，请增加行数或列数')
    return {'schema':'report-image-group-v1','id':oid,'columns':columns,
            **({'rows':rows} if rows is not None else {}),
            **({'showSubfigureLabels':labels} if labels is not None else {}),
            'caption':caption,'images':images}


def _reference_mask(text):
    return masked_context(text)


def analyze(markdown: str, assets: Path | None = None) -> dict:
    if not isinstance(markdown,str): raise ContractError('Markdown 应为文本')
    if len(markdown.encode('utf-8'))>10*1024*1024:raise ContractError('Markdown 超过 10 MB')
    lines=markdown.splitlines(keepends=True)
    # JavaScript/CodeMirror offsets count UTF-16 code units, including CRLF.
    line_starts=[0]
    for raw in lines:line_starts.append(line_starts[-1]+len(raw.encode('utf-16-le'))//2)
    def line_range(line,start=0,end=None):
        raw=lines[line-1] if line<=len(lines) else ''
        end=len(raw.rstrip('\r\n')) if end is None else end
        base=line_starts[min(line-1,len(lines))]
        return {'start':base+len(raw[:start].encode('utf-16-le'))//2,
                'end':base+len(raw[:end].encode('utf-16-le'))//2}
    blocks=[];diagnostics=[];ids={};references=[];assets_used=[];styled_lists=[]
    def diag(severity,code,message,line,location=None):
        diagnostics.append({'severity':severity,'code':code,'message':message,'line':line,**(location or line_range(line))})
    def add_object(kind,obj,line,location):
        oid=obj['id'];bk='table' if kind=='report-table' else 'figure'
        location={**location,'objectId':oid}
        if oid in ids:diag('error','DUPLICATE_ID',f'对象 ID 重复：{oid}（之前在第 {ids[oid]} 行）',line,location)
        else:ids[oid]=line
        if not obj['caption'].strip():diag('warning','MISSING_CAPTION',f'{oid} 没有题注',line,location)
        if bk=='figure' and obj['kind']=='image':
            assets_used.append((obj['src'],line,location))
            if obj.get('vectorSource'):assets_used.append((obj['vectorSource'],line,location))
            if obj.get('rasterFallback'):assets_used.append((obj['rasterFallback'],line,location))
            if obj.get('sourceAsset'):assets_used.append((obj['sourceAsset'],line,location))
        return bk
    def outside_piece(text,startline):
        # Preserve all non-special Markdown, including inline math, verbatim.
        pending=[];pending_line=startline
        def flush():
            nonlocal pending
            if pending:
                blocks.append({'type':'markdown','source':''.join(pending),'line':pending_line})
                pending=[]
        reference_lines=_reference_mask(text).splitlines(keepends=True)
        asset_lines=masked_context(text,mask_images=False).splitlines(keepends=True)
        piece_lines=text.splitlines(keepends=True)
        for url, relative_line, column, length in html_image_references(text):
            number=startline+relative_line-1
            location=line_range(number,column,column+length)
            if (canonical:=normalize_asset(url)):assets_used.append((canonical,number,location))
            else:diag('error','EXTERNAL_IMAGE','图片路径不是本地 assets/ 文件：'+url[:80],number,location)
        for index,raw in enumerate(piece_lines):
            line=startline+index
            if re.match(r'^ {0,3}<!--\s*hrs:list\b',raw):
                matched=LIST_MARKER.fullmatch(raw.rstrip('\r\n'))
                style=matched[1] if matched else None
                next_line=piece_lines[index+1].rstrip('\r\n') if index+1<len(piece_lines) else ''
                wanted=r'^ {0,3}[-+*][ \t]+' if style=='bullet' else r'^ {0,3}[0-9]{1,9}[.)][ \t]+'
                if style not in LIST_STYLES or not re.match(wanted,next_line):
                    diag('error','INVALID_LIST_STYLE','列表样式声明不合法或未紧接标准 Markdown 列表',line)
                else:
                    styled_lists.append({'style':style,'line':line,**line_range(line)})
            syntax=raw[1:] if line==1 and raw.startswith('\ufeff') else raw
            heading=HEADING.match(syntax.rstrip('\r\n'))
            if heading:
                flush();title=heading[2].strip();anchor=SECTION_ANCHOR.search(' '+title)
                section={'type':'heading','level':len(heading[1]),'text':title,'source':raw,'line':line}
                if anchor:
                    oid=anchor[1];section['text']=(' '+title)[:anchor.start()].strip()
                    location={**line_range(line),'objectId':oid}
                    try:
                        _check_id(oid,'sec')
                        if not re.fullmatch(r'sec-[A-Za-z0-9_-]{1,60}',oid):raise ContractError('章节 ID 必须符合 sec-… 的稳定标识规则')
                    except ContractError as exc:diag('error','INVALID_SECTION_ID',str(exc),line,location)
                    else:
                        section['id']=oid
                        if oid in ids:diag('error','DUPLICATE_ID',f'对象 ID 重复：{oid}（之前在第 {ids[oid]} 行）',line,location)
                        else:ids[oid]=line
                        if not section['text']:diag('warning','EMPTY_SECTION_TITLE','引用章节标题为空',line,location)
                blocks.append(section)
                pending_line=line+1
            else:
                if not pending:pending_line=line
                pending.append(raw)
            # Only analyze references in ordinary text, not inside inline code spans.
            clean=reference_lines[index]
            if not re.match(r'^\s{0,3}(?:>{0,1}\s*)?```',clean):
                references.extend({'kind':m[1],'target':m[2],'line':line,**line_range(line,m.start(),m.end())} for m in REF.finditer(clean))
            for img in ANY_IMAGE.finditer(asset_lines[index]):
                url=img[1].split(' "',1)[0]
                location=line_range(line,img.start(),img.end())
                if (canonical:=normalize_asset(url)):assets_used.append((canonical,line,location))
                else:diag('error','EXTERNAL_IMAGE','图片路径不是本地 assets/ 文件：'+url[:80],line,location)
        flush()
    idx=0;buffer=[];buffer_start=1
    char_starts=[0]
    for raw in lines:char_starts.append(char_starts[-1]+len(raw))
    while idx<len(lines):
        line=lines[idx].rstrip('\r\n')
        if idx==0 and line.startswith('\ufeff'):line=line[1:]
        equation=parse_equation(markdown,char_starts[idx]) if re.match(r'^ {0,3}(?:\$\$|\\\[|<!-- hrs:eq\b)',line) else None
        if equation:
            if buffer:outside_piece(''.join(buffer),buffer_start);buffer=[]
            start=idx;idx+=len(equation['source'].splitlines(keepends=True))
            oid=equation['id'];block={'type':'equation','line':start+1,**equation,'numbered':True}
            if oid:
                location={'start':line_starts[start],'end':line_starts[idx],'objectId':oid}
                if oid in ids:diag('error','DUPLICATE_ID',f'对象 ID 重复：{oid}',start+1,location)
                else:ids[oid]=start+1
                block['number']=1+sum(b['type']=='equation' and b.get('numbered',False) for b in blocks)
            blocks.append(block);continue
        if re.match(r'^ {0,3}\\\[[ \t]*$',line) and not equation:
            diag('error','UNCLOSED_DISPLAY_MATH','\\[ 行间公式缺少完整的 \\] 结束行',idx+1)
        if re.match(r'^ {0,3}<!--\s*hrs:eq\b',line):
            diag('error','INVALID_EQUATION','公式声明无效或未紧接完整的 $$ 块公式',idx+1)
        group=GROUP_OPEN.fullmatch(line)
        if group and re.search(r'#fig-|layout-ncol',group[1]):
            if buffer:outside_piece(''.join(buffer),buffer_start);buffer=[]
            start=idx;idx+=1
            while idx<len(lines) and not GROUP_CLOSE.fullmatch(lines[idx].rstrip('\r\n')):idx+=1
            closed=idx<len(lines)
            if closed:idx+=1
            source=''.join(lines[start:idx]);location={'start':line_starts[start],'end':line_starts[idx]}
            try:
                if not closed:raise ContractError('组图围栏未闭合')
                obj=parse_image_group(source[1:] if start==0 and source.startswith('\ufeff') else source);oid=obj['id']
                if oid in ids:diag('error','DUPLICATE_ID',f'对象 ID 重复：{oid}（之前在第 {ids[oid]} 行）',start+1,{**location,'objectId':oid})
                else:ids[oid]=start+1
                if not obj['caption']:diag('warning','MISSING_CAPTION',f'{oid} 没有题注',start+1,{**location,'objectId':oid})
                for image in obj['images']:
                    assets_used.append((image['src'],start+1,{**location,'objectId':oid}))
                    for key in ('sourceAsset','rasterFallback'):
                        if image.get(key):assets_used.append((image[key],start+1,{**location,'objectId':oid}))
                blocks.append({'type':'image-group','id':oid,'numbered':True,'data':obj,'source':source,'line':start+1})
            except ContractError as exc:
                diag('error','INVALID_IMAGE_GROUP',str(exc),start+1,location)
                blocks.append({'type':'invalid-object','source':source,'line':start+1})
            continue
        # PF11: a native GFM pipe table is a semantic IR table, not an HTML
        # screenshot and not an automatically migrated report-table JSON block.
        # Only author-supplied tbl-id is registered as a stable cross-reference.
        try:pipe=parse_pipe_table_at(lines,idx)
        except ValueError as exc:
            diag('error','INVALID_PIPE_TABLE',str(exc),idx+1)
            pipe=None
        if pipe:
            if buffer:outside_piece(''.join(buffer),buffer_start);buffer=[]
            start=idx;idx+=pipe['lines'];oid=pipe['id']
            if oid:
                loc={'start':line_starts[start],'end':line_starts[idx],'objectId':oid}
                if oid in ids:diag('error','DUPLICATE_ID',f'对象 ID 重复：{oid}',start+1,loc)
                else:ids[oid]=start+1
            # Pipe cells remain Markdown text: preserve references and image
            # dependencies inside them (but mask URL, inline-code and other
            # non-reference spans exactly as ordinary Markdown does).
            source_lines=pipe['source'].splitlines(keepends=True)
            ref_lines=_reference_mask(pipe['source']).splitlines(keepends=True)
            asset_lines=masked_context(pipe['source'],mask_images=False).splitlines(keepends=True)
            for offset,raw in enumerate(source_lines):
                lineno=start+offset+1
                if offset<len(ref_lines):
                    references.extend({'kind':m[1],'target':m[2],'line':lineno,**line_range(lineno,m.start(),m.end())}
                                      for m in REF.finditer(ref_lines[offset]))
                if offset<len(asset_lines):
                    for image in ANY_IMAGE.finditer(asset_lines[offset]):
                        url=image[1].split(' "',1)[0]
                        loc=line_range(lineno,image.start(),image.end())
                        if (canonical:=normalize_asset(url)):assets_used.append((canonical,lineno,loc))
                        else:diag('error','EXTERNAL_IMAGE','图片路径不是本地 assets/ 文件：'+url[:80],lineno,loc)
            blocks.append({'type':'table','sourceKind':'gfm-pipe','numbered':True,**({'id':oid} if oid else {}),
                          'data':pipe['data'],'source':pipe['source'],'line':start+1})
            continue
        m=FENCE_OPEN.match(line)
        if not m:
            if not buffer:buffer_start=idx+1
            buffer.append(lines[idx]);idx+=1;continue
        if buffer:outside_piece(''.join(buffer),buffer_start);buffer=[]
        token=m[1];language=m[2].strip().split(' ',1)[0].lower()
        start=idx;idx+=1;data=[]
        # CommonMark closing fence may be longer than opener, up to 3-space indent.
        close=re.compile(r'^ {0,3}'+re.escape(token[0])+r'{'+str(len(token))+r',}\s*$')
        while idx<len(lines) and not close.fullmatch(lines[idx].rstrip('\r\n')):
            data.append(lines[idx]);idx+=1
        if idx>=len(lines):
            diag('error','UNCLOSED_FENCE','代码围栏未闭合',start+1,{'start':line_starts[start],'end':line_starts[-1]})
            blocks.append({'type':'markdown','source':''.join(lines[start:]),'line':start+1})
            break
        end=idx;idx+=1
        source=''.join(lines[start:idx]);body=''.join(data)
        location={'start':line_starts[start],'end':line_starts[idx]}
        if language in ('report-table','report-figure'):
            try:
                obj=json.loads(body)
                obj=validate_table(obj) if language=='report-table' else validate_figure(obj)
                typ=add_object(language,obj,start+1,location)
                # Nested cell extensions are preserved in rows verbatim, but
                # must also be visible in generic Agent diagnostics.
                if typ=='table':
                    unknown_cells=[f'{ri+1}:{ci+1}:'+','.join(sorted(set(cell)-{'text','rowspan','colspan'}))
                        for ri,row in enumerate(obj['rows']) for ci,cell in enumerate(row)
                        if isinstance(cell,dict) and set(cell)-{'text','rowspan','colspan'}]
                    if unknown_cells:
                        diag('warning','UNSUPPORTED_OBJECT_FIELDS',
                             f'{obj["id"]} 存在未识别单元格字段：'+', '.join(unknown_cells[:12]),
                             start+1,{**location,'objectId':obj['id']})
                if obj.get('extensions'):
                    diag('warning','UNSUPPORTED_OBJECT_FIELDS',
                         f'{obj["id"]} 含当前编译器不认识的字段：'+', '.join(sorted(obj['extensions'])),
                         start+1,{**location,'objectId':obj['id']})
                blocks.append({'type':typ,'id':obj['id'],
                    **({'sourceKind':'enhanced','numbered':True} if typ=='table' else {'numbered':True}),
                    'data':obj,'source':source,'line':start+1})
            except (ValueError,TypeError,KeyError) as exc:
                diag('error','INVALID_OBJECT',f'{language}：{exc}',start+1,location)
                blocks.append({'type':'invalid-object','source':source,'line':start+1})
        elif language.startswith('report-'):
            diag('error','UNKNOWN_OBJECT','未识别的工程对象：'+language,start+1,location)
            blocks.append({'type':'invalid-object','source':source,'line':start+1})
        else:
            blocks.append({'type':'mermaid' if language=='mermaid' else 'code',
                           'language':language,'source':source,'body':body,'line':start+1})
    if buffer:outside_piece(''.join(buffer),buffer_start)
    for ref in references:
        if ref['target'] not in ids:
            diag('error','MISSING_REFERENCE',f'找不到引用对象：{ref["kind"]}:{ref["target"]}',ref['line'],{'start':ref['start'],'end':ref['end'],'objectId':ref['target']})
        elif not ref['target'].startswith(ref['kind']+'-'):
            diag('error','WRONG_REFERENCE_KIND',f'交叉引用类型不匹配：{ref["kind"]}:{ref["target"]}',ref['line'],{'start':ref['start'],'end':ref['end'],'objectId':ref['target']})
    if assets is not None:
        root=Path(assets)
        for path,line,location in assets_used:
            name=ASSET.fullmatch(path)
            if name is None:
                source=SOURCE_ASSET.fullmatch(path)
                if source is None:
                    diag('error','INVALID_ASSET','附件路径无效：'+path,line,location)
                elif not (root/path.removeprefix('assets/')).is_file():
                    diag('error','MISSING_ASSET','找不到原始图形附件：'+path,line,location)
            else:
                try:present=asset_file(root,name[1]).is_file()
                except ValueError:
                    diag('error','INVALID_ASSET','附件路径不允许包含链接：'+path,line,location)
                    continue
                if not present:diag('error','MISSING_ASSET','找不到附件：'+path,line,location)
    for block in blocks:
        block['start']=line_starts[block['line']-1]
        block['end']=block['start']+len(block['source'].encode('utf-16-le'))//2
    # Semantic sequence is derived exactly once from validated object blocks;
    # headings and GFM tables (even with stable IDs) do not consume numbers.
    sequence_counts={'figure':0,'table':0,'equation':0}
    sequence_ids=set()
    for block in blocks:
        if block['type'] not in ('figure','image-group','table','equation','mermaid'):continue
        oid=block.get('id');kind='figure' if block['type'] in ('image-group','mermaid') else block['type']
        if oid and oid in sequence_ids:
            block['number']=None  # duplicate identity is never a numbered target
            continue
        if oid:sequence_ids.add(oid)
        if kind in sequence_counts:
            sequence_counts[kind]+=1;block['number']=sequence_counts[kind]
    # A0 read-only object catalog: IDs are stable; rendered numbers are not.
    # Legacy objects.ids mapping intentionally retained for existing consumers.
    # An uncaptioned GFM table without an ID is still in blocks[], but not in
    # the persistent catalog: an Agent must not invent an ID for it.
    entries=[]
    for block in blocks:
        oid=block.get('id')
        if not oid:continue
        kind={'heading':'section','image-group':'figure'}.get(block['type'],block['type'])
        numbered=bool(block.get('numbered',block['type']=='figure'))
        entry={'id':oid,'kind':kind,'line':block['line'],'start':block['start'],'end':block['end'],
               'numbered':numbered,'number':block.get('number') if numbered else None,
               'sequence':{'figure':'figure','table':'table','equation':'equation'}.get(kind) if numbered else None,
               'scope':'document' if numbered else None}
        if kind=='section':entry['level']=block['level']
        if kind=='table':entry['sourceKind']=block.get('sourceKind','enhanced')
        entry['referencedBy']=[{'kind':ref['kind'],'start':ref['start'],'end':ref['end']}
                                for ref in references if ref['target']==oid]
        entries.append(entry)
    return {'schema':IR_VERSION,'source_format':FORMAT,'offset_unit':'utf16',
            'source_snapshot':{'text_utf8_sha256':hashlib.sha256(markdown.encode('utf-8')).hexdigest(),
                'utf16_length':len(markdown.encode('utf-16-le'))//2,'newline_mode':'preserved',
                'bom_preserved':markdown.startswith('\ufeff')},'blocks':blocks,
            'objects':{'ids':ids,'entries':entries},'references':references,
            'assets':sorted(set(item[0] for item in assets_used)),'list_styles':styled_lists,
            'diagnostics':diagnostics,'ok':not any(d['severity']=='error' for d in diagnostics),
            'stats':dict(Counter(b['type'] for b in blocks))}


def main(argv=None):
    p=argparse.ArgumentParser(description='Validate HTML Report Studio Markdown engineering source')
    p.add_argument('action',choices=['validate','ir'])
    p.add_argument('source',type=Path,help='a report.md file or report project directory')
    p.add_argument('--output',type=Path,help='IR JSON output path (not the source project)')
    p.add_argument('--json',action='store_true',help='print validation JSON')
    args=p.parse_args(argv)
    source=args.source/'report.md' if args.source.is_dir() else args.source
    try:
        raw=source.read_bytes()
        result=analyze(raw.decode('utf-8'),assets=source.parent/'assets')
        result['source_snapshot'].update({'file_sha256':hashlib.sha256(raw).hexdigest(),
            'file_bytes':len(raw),'source_path':str(source.resolve()),'encoding':'utf-8'})
    except (OSError,UnicodeError,ValueError) as exc:
        print('ERROR:',str(exc),file=sys.stderr);return 2
    if args.action=='ir':
        if args.output is None:p.error('ir action requires --output')
        if args.output.resolve()==source.resolve():p.error('Cannot overwrite report.md')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.json:print(json.dumps(result if args.action=='ir' else {'ok':result['ok'],'diagnostics':result['diagnostics'],'stats':result['stats']},ensure_ascii=False,indent=2))
    else:
        print('工程报告结构：'+('通过' if result['ok'] else '失败')+f'；共 {len(result["blocks"])} 个块，{len(result["diagnostics"])} 条诊断')
        for d in result['diagnostics']:print(f'  {d["severity"]} L{d["line"]} {d["code"]}: {d["message"]}')
    return 0 if result['ok'] else 1

if __name__=='__main__':raise SystemExit(main())
