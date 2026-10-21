"""Bounded offline SVG XML prolog normalization.

Only an explicitly bounded subset of plain-text internal entities is expanded.
The DTD is removed BEFORE invoking ElementTree, so no external identifiers,
parameter entities, or declarations ever reach the XML parser.
"""
from __future__ import annotations
import html
import re

MAX_SVG = 12*1024*1024
ENTITY_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_.:-]{0,63}')
DECLARATION = re.compile(r'<!ENTITY\s+([A-Za-z_][A-Za-z0-9_.:-]{0,63})\s+([\'\"])(.*?)\2\s*>',re.S|re.I)


def _find_doctype(source: str) -> tuple[int,int] | None:
    """Scan through comments, CDATA, and quoted DTD subsections safely."""
    n=len(source);i=0;seen=None
    while i<n:
        if source.startswith('<!--',i):
            end=source.find('-->',i+4)
            if end<0:raise ValueError('SVG XML 注释未结束')
            i=end+3;continue
        if source.startswith('<![CDATA[',i):
            end=source.find(']]>',i+9)
            if end<0:raise ValueError('SVG CDATA 未结束')
            i=end+3;continue
        if source[i:i+9].lower()=='<!doctype':
            if seen is not None:raise ValueError('SVG 包含重复 DOCTYPE')
            start=i;quote=None;depth=0;i+=9
            while i<n:
                c=source[i]
                if quote:
                    if c==quote:quote=None
                elif c in ('\"',"'"):quote=c
                elif c=='[':depth+=1
                elif c==']':
                    depth-=1
                    if depth<0:raise ValueError('SVG DTD 语法不合法')
                elif c=='>' and depth==0:
                    seen=(start,i+1);i+=1;break
                i+=1
            else:raise ValueError('SVG DTD 未结束')
            continue
        i+=1
    return seen


def safe_svg_prolog(blob:bytes, warnings:list[str] | None=None)->bytes:
    if len(blob)>MAX_SVG:raise ValueError('SVG 文件超过 12 MB')
    if blob.startswith((b'\xff\xfe',b'\xfe\xff')):
        source=blob.decode('utf-16')
        source=re.sub(r'^\s*<\?xml\s+[^?]*\?>','',source,count=1,flags=re.I)
    else:
        try:source=blob.decode('utf-8-sig')
        except UnicodeDecodeError as exc:raise ValueError('SVG 需要 UTF-8/UTF-16 编码') from exc
    doctype=_find_doctype(source)
    if doctype:
        start,end=doctype
        text=source[start:end]
        if not re.match(r'<!DOCTYPE\s+(?:[A-Za-z_][\w.:\-]*:)?svg\b',text,re.I):
            raise ValueError('SVG DTD 根节点不是 svg')
        subset=''
        outer=text
        q=None;index=None
        for i,char in enumerate(text):
            if q:
                if char==q:q=None
            elif char in "'\"":q=char
            elif char=='[':
                index=i;break
        if index is not None:
            closing=text.rfind(']')
            if closing<index:raise ValueError('SVG DTD 内部子集不完整')
            subset=text[index+1:closing]
            outer=text[:index]+text[closing+1:]
        # We never look up SYSTEM or PUBLIC, even for explicitly named identifiers.
        if re.search(r'\b(?:SYSTEM|PUBLIC)\b',outer,re.I) and warnings is not None:
            warnings.append('已移除外部 DTD 声明；没有联网或读取外部实体')
        # An internal subset can hold element/attlist declarations. They are
        # dropped; only simple bounded standalone text entities are expanded.
        entities={}
        for m in re.finditer(r'<!ENTITY\b[^>]*>',subset,re.S|re.I):
            item=m.group()
            parsed=DECLARATION.fullmatch(item)
            if parsed is None:
                # Unsafe entities, including parameter and external entities:
                # no parsing, no expansion, no external access.
                continue
            name,value=parsed.group(1),parsed.group(3)
            if (len(entities)>=24 or len(value)>96 or len(name)>64 or
                '<' in value or '>' in value or '&' in value or '%' in value or
                name in {'amp','lt','gt','quot','apos'}):
                continue
            if name in entities:raise ValueError('SVG DTD 重复实体：'+name)
            entities[name]=value
        source=source[:start]+source[end:]
        # Expand *only* simple standalone text entities, with total output cap.
        counts={}
        def replace(m):
            name=m.group(1)
            if name in entities:
                counts[name]=counts.get(name,0)+1
                if sum(counts.values())>512:raise ValueError('SVG DTD 实体引用过多')
                return html.escape(entities[name],quote=False)
            return m.group()
        source=re.sub(r'&([A-Za-z_][A-Za-z0-9_.:-]{0,63});',replace,source)
        if warnings is not None:
            warnings.append('已剥离 SVG DTD，保留可安全展开的简单文本实体')
    if _find_doctype(source) is not None:raise ValueError('SVG 中存在未移除的 DTD')
    # Any non-XML processing instruction is unusable as an embedded offline
    # image; stripping avoids XML stylesheet network dependencies.
    source,count=re.subn(r'<\?(?!xml\s)[A-Za-z_][\w.:-]*\s[^?]*\?>','',source,flags=re.I)
    if count and warnings is not None:warnings.append('已移除 SVG 外部样式等处理指令')
    return source.encode('utf-8')
