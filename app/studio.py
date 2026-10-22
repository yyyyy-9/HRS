#!/usr/bin/env python3
"""HTML Report Studio - offline localhost report editor.

Requires only Python standard library. PDF generation uses an installed Edge/Chrome/
Chromium browser if available (fallback: browser print-to-PDF).
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit
import uuid
import webbrowser
import xml.etree.ElementTree as ET
import zipfile
from report_contract import analyze as analyze_report_contract
from agent_readonly import project as project_contract, BLOCKED_DIAGNOSTICS
from project_workspace import ProjectRegistry,pick_project_parent,pick_import_file,copy_project_tree,_trusted_project_directory,is_link,validate_project_name
from clipboard_graphics import ClipboardGraphic, read_windows_graphic, emf_to_png, validate_emf
from svg_prolog import safe_svg_prolog
from pdf_graphics import validate_pdf, png_dimensions, render_pdf_preview
from reading_pack import ReadBundle, ReadPackManager, MIME as READER_MIME, MAX_ZIP_BYTES, MAX_IMAGE as READER_MAX_IMAGE, MAX_PDF as READER_MAX_PDF
from asset_housekeeping import AssetHousekeeper
from word_export import WordExport

HERE = Path(__file__).resolve().parent
APP_MANIFEST_SHA256 = hashlib.sha256((HERE/'MANIFEST.json').read_bytes()).hexdigest() if (HERE/'MANIFEST.json').is_file() else None
from release_info import load_release, SOURCE_SPEC
_identity = load_release()
VERSION = _identity['version']
PACKAGE_REVISION = _identity['package_revision']
RELEASE = _identity['release']
WEB = HERE / 'web'
DEFAULT = HERE / 'projects' / 'demo'   # v0.1 compatibility; never auto-open on new UI launch
LIMIT_JSON = 45 * 1024 * 1024
LIMIT_IMAGE = 12 * 1024 * 1024
DOC_ID = re.compile(r'^[a-f0-9]{32}$')
DRAFT_ID = DOC_ID
ALLOWED_IMAGE = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.gif':'image/gif', '.webp':'image/webp', '.svg':'image/svg+xml'}
ALLOWED_ASSET = {**ALLOWED_IMAGE,'.emf':'application/octet-stream','.pdf':'application/pdf'}
WINDOWS_RESERVED = {'CON','PRN','AUX','NUL'} | {f'{p}{n}' for p in ('COM','LPT') for n in range(1,10)}
# Byte-exact first-party reader scripts shipped by earlier releases, so HTML
# already exported to output/ by them can still pass the delivery audit.
LEGACY_READER_SHA256 = {'1275a6830b70fb59cf07ac16be15e2dc5ce9c87b2af2345db2c3d2bf27dbeee8','4386a8a446949233a9e5170f96e453eb58e962b876451e4de88501084e0252db','43c2ccdad84ddf525d2b5f4a6bba651c37b94c53d9c65ac28dcd5c8317a3330a','4f06e316f1bdd62d20e5173f56af0ade63b8d9e326918d2b55e3e76ad96e4036','6feb1c196b0f5f231ce9fb11d68642fecd0f810ddf035284902f8778bb4b93b4','764f4333c55c29de9affc2cf53e5322f48443d400ab6cc212e6124812eb74219','782a99c76ee2b047239bc460cca74fc2895e9c275f415f3e967e40eb20a25bde','7f217047cc92ebc99211c63201762a3f89050564c20d5b5b38fb927d77ec74c3','8769a7ce7557c2c68b62c9ac1ec6e03c60c34b65e6757f3cd6121ca080bfe833','906c8d3447b0ccda8b7e71055e3bf7ef66e064506a27d33d05ad5e701a322473','949267a8c0f7b6615f723176597cc68baddfd689f3f964e8715d74d3c6dcc0c5','bb6ecd6c41f23bd618bbf109377f2895ec3fe35fa22c4d96b65da4ea818cb577','bd7ed68acf2f5d849a16142cece55b3bd5efa8dd033cb70ea7fb5d6d6a7344a3','c8ac801ae44f87fd341b1243654f33b8e867f0592e72e95435c35653fae26a97','dc69801f4091638ea113c99e29156ebac1c24ee6711f78d16b28af766f6a32c0','e311b36e32036747723d519fd7d15d341e8d69a494d5642dfa1bccefc035ff1f','f478329753af6f59b00426e060dc2c12f95cb0000652433a861d09b0b5cce7ec','f85efdc2182e7b211fec5b39e7a840d3cefdf7ac9bbf03f1b219161ce139d144'}
SVG_DOCUMENT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"

from project_commit import commit_report, backup_report, report_lock
from render_profile import (normalize as normalize_profile, read as read_profile,
    normalize_options, new_options, read_options, output_checks, require_output)
from color_theme import normalize as normalize_color_theme, read as read_color_theme

TEMPLATES = {
    'engineering': {
        'label': '工程技术报告', 'description': '摘要、技术方案、分析、结论，清爽蓝色样式', 'theme': 'engineering',
        'markdown': '''# 未命名技术报告

**项目：** 待填写　　**日期：** 待填写

> 摘要：在这里填写摘要。不需要摘要时，删除本段。

## 背景与目标

在这里编写正文。

## 技术方案

### 方法与步骤

填写实验过程、算法或设计说明。

### 参数与公式

在这里插入公式、表格或流程图。

## 结果与讨论

写入数据、分析与图表。

## 结论

填写主要结论与下一步工作。
'''
    },
    'academic': {
        'label': '论文与研究笔记', 'description': '研究背景、方法、实验、讨论，偏纸质排版', 'theme': 'academic',
        'markdown': '''# 研究报告标题

**作者：** 待填写　　**日期：** 待填写

## 摘要

简要介绍研究问题与主要贡献。

**关键词：** 关键词一；关键词二

## 引言

介绍研究背景、目标及相关工作。

## 方法

### 原理

介绍关键方法及公式。

### 实验设置

列出数据和实验步骤。

## 结果

插入图表，讨论实验结果。

## 讨论

分析限制和可能的改进。

## 结论

总结研究成果。

## 参考资料

- 资料一
'''
    },
    'brief': {
        'label': '项目说明 / 会议纪要', 'description': '简洁紧凑，适合方案、记录与快速分享', 'theme': 'brief',
        'markdown': '''# 项目说明

**主题：** 待填写　　**日期：** 待填写

## 背景

概述本次事项。

## 关键要点

- 要点一
- 要点二

## 方案与安排

| 事项 | 负责人 | 时间 |
| --- | --- | --- |
| 待填写 | 待填写 | 待填写 |

## 决定与后续

- [ ] 待办事项
'''
    },
    'blank': {
        'label': '空白文档', 'description': '只有标题，保留预设的 6 级标题等样式', 'theme': 'engineering',
        'markdown': '# 新文档\n\n从这里开始写。\n'
    },
}


def native_clipboard_available() -> bool:
    return os.name=='nt'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tempname = tempfile.mkstemp(prefix='.tmp_', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tempname, path)
    finally:
        if os.path.exists(tempname): os.unlink(tempname)


def write_json(path: Path, obj: dict) -> None:
    atomic_write(path, (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def normalize_svg(blob: bytes, *, linked_assets: dict[str, bytes] | None=None,
                  warnings: list[str] | None=None) -> bytes:
    """Validate offline SVG and inline explicitly supplied referenced raster files.

    Never follows SVG file/http URLs. Relative image references can only resolve
    against browser-selected bytes supplied in linked_assets. Ordinary local
    defs/use and local hyperlinks remain intact; outbound hyperlinks are removed
    while retaining their visible shapes (no network dependency in exported HTML).
    """
    from pathlib import PurePosixPath
    blob=safe_svg_prolog(blob,warnings=warnings)
    original=blob
    try:root=ET.fromstring(blob)
    except ET.ParseError as exc:raise ValueError('SVG XML 无效，可能使用了未定义实体') from exc
    if root.tag.split('}')[-1].lower()!='svg':raise ValueError('不是 SVG 文件')
    # Never look up a path, load an external URL, or allow uncontrolled entities.
    # A file picker provides only basenames; require unique, bounded explicitly
    # supplied bitmap bytes. The image file itself is inlined as a data URI.
    supplied={}
    total=0
    if linked_assets is not None:
        if not isinstance(linked_assets,dict) or len(linked_assets)>32:
            raise ValueError('SVG 附属图片数量无效')
        for name,data in linked_assets.items():
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_ .()\-]{1,150}\.(png|jpe?g|gif|webp)',name,re.I):
                raise ValueError('SVG 附属图片名称不合法')
            if not isinstance(data,bytes):raise ValueError('SVG 附属图片内容无效')
            total+=len(data)
            if total>24*1024*1024:raise ValueError('SVG 附属图片总大小超过 24 MB')
            check_image('.'+name.rsplit('.',1)[1].lower(),data)
            lowered=name.casefold()
            if lowered in supplied:raise ValueError('SVG 附属图片有重名文件')
            supplied[lowered]=(name,data)
    disallowed={'script','foreignobject','iframe','object','embed',
                'animate','animatetransform','animatemotion','set',
                'audio','video','feimage'}
    ids=set();references=[];modified=False
    removed=[]
    def strip_unsafe(parent):
        nonlocal modified
        for child in list(parent):
            tag=child.tag.split('}')[-1].lower() if isinstance(child.tag,str) else ''
            if tag in disallowed:
                parent.remove(child);removed.append(tag);modified=True
            else:strip_unsafe(child)
    strip_unsafe(root)
    # Matplotlib/Inkscape place descriptive RDF / DC metadata here; URI values
    # (e.g. http://purl.org/...) are *identifiers*, not render-time fetches.
    # Dropping the entire non-rendered subtree avoids false external-resource
    # errors without relaxing URLs on actual SVG image/style/use elements.
    removed_metadata=[]
    def strip_metadata(parent):
        nonlocal modified
        for child in list(parent):
            if not isinstance(child.tag,str):continue
            local=child.tag.split('}')[-1].lower()
            ns=child.tag.split('}')[0][1:] if '}' in child.tag else ''
            if local=='metadata' or ns in {'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
                                           'http://purl.org/dc/elements/1.1/',
                                           'http://creativecommons.org/ns#'}:
                parent.remove(child);modified=True;removed_metadata.append(local)
            else:strip_metadata(child)
    strip_metadata(root)
    if removed_metadata and warnings is not None:
        warnings.append('已移除不参与绘图的 SVG/RDF 元数据，不访问元数据网址')
    if removed and warnings is not None:
        warnings.append('SVG 中的不安全/动态元素已移除：'+', '.join(sorted(set(removed))))
    # Do not create a silently blank image after removing a script-only graph.
    visible={'path','rect','circle','ellipse','line','polyline','polygon','text','image','use'}
    if removed and not any(isinstance(n.tag,str) and n.tag.split('}')[-1].lower() in visible for n in root.iter()):
        raise ValueError('SVG 图形完全依赖脚本或动态对象，无法安全保留；请导出静态 SVG')
    for node in root.iter():
        name=node.tag.split('}')[-1].lower() if isinstance(node.tag,str) else '' 
        if name=='style':
            css=''.join(node.itertext())
            if re.search(r'@import|expression\s*\(|url\s*\(\s*(?!["\']?\s*#)',css,re.I):
                raise ValueError('SVG 样式包含非本地资源（不自动加载网络文件）')
            for m in re.finditer(r'url\s*\(\s*([^)]+)\)',css,re.I):
                references.append(m[1].strip().strip('"\'').strip()[1:])
        for key,value in list(node.attrib.items()):
            attr=key.split('}')[-1].lower()
            if attr=='id':ids.add(value)
            if attr.startswith('on') or attr in {'src','base','action','formaction'}:
                del node.attrib[key];modified=True
                if warnings is not None:warnings.append('SVG 事件或外部资源属性已移除：'+attr)
                continue
            if re.search(r'@import|expression\s*\(',value,re.I):
                raise ValueError('SVG 包含危险 CSS 内容')
            for m in re.finditer(r'url\s*\(\s*([^)]+)\)',value,re.I):
                destination=m[1].strip().strip('"\'').strip()
                if not destination.startswith('#') or not re.fullmatch(r'#[A-Za-z_][\w.-]*',destination):
                    raise ValueError('SVG 包含外部 CSS 资源')
                references.append(destination[1:])
            if attr=='href':
                if name in {'use','textpath','lineargradient','radialgradient','pattern',
                            'filter','mask','clippath','symbol'}:
                    if not re.fullmatch(r'#[A-Za-z_][\w.-]*',value):
                        raise ValueError('SVG 内部图形引用必须为 #id')
                    references.append(value[1:])
                elif name=='image':
                    m=re.fullmatch(r'data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=]+)',value,re.I)
                    if m:
                        try:embedded=base64.b64decode(m[2],validate=True)
                        except Exception as exc:raise ValueError('SVG 内嵌图片 Base64 错误') from exc
                        ext={b'png':'.png',b'jpeg':'.jpeg',b'gif':'.gif',b'webp':'.webp'}[m[1].encode('ascii').lower()]
                        check_image(ext,embedded)
                    else:
                        url=urlsplit(value)
                        if url.scheme.lower() in {'javascript','data','ftp','blob'}:
                            raise ValueError('SVG 包含不安全图片协议：'+value[:100])
                        if url.scheme and url.scheme.lower() not in {'https','http','file'}:
                            raise ValueError('SVG 图片协议未受支持：'+value[:100])
                        # The source file may contain file:///... emitted by Origin.
                        # Only its basename is used to match a user-selected file.
                        path=unquote(url.path if url.scheme.lower() in {'file','http','https'} else value).replace('\\','/')
                        parts=PurePosixPath(path).parts
                        if not parts or path.endswith('/') or '..' in parts or (url.scheme.lower() not in {'http','https','file'} and ('?' in path or '#' in path)):
                            raise ValueError('SVG 图片路径无效：'+value[:110])
                        lookup=parts[-1].casefold()
                        if lookup not in supplied:
                            raise ValueError('SVG 引用了本地图片「'+parts[-1]+'」，请同时选中 SVG 和该图片文件导入')
                        fname,data=supplied[lookup]
                        mime={'png':'png','jpg':'jpeg','jpeg':'jpeg','gif':'gif','webp':'webp'}[fname.rsplit('.',1)[1].lower()]
                        node.attrib[key]='data:image/'+mime+';base64,'+base64.b64encode(data).decode('ascii')
                        modified=True
                        if warnings is not None:warnings.append('已将 SVG 引用图片「'+fname+'」内嵌，不依赖原路径')
                elif name=='a':
                    if re.fullmatch(r'#[A-Za-z_][\w.-]*',value):references.append(value[1:])
                    elif value.startswith('#'):
                        del node.attrib[key];modified=True
                    else:
                        # External *hyperlinks* aren't image dependencies. Make
                        # the SVG readable offline without click-through URLs.
                        del node.attrib[key];modified=True
                        if warnings is not None:warnings.append('SVG 中的外部超链接已去除，图形内容保留')
                else:raise ValueError('SVG 含不允许的链接属性')
            if attr!='href' and re.search(r'(?:https?:|file:|javascript:|//)',value,re.I):
                raise ValueError('SVG 包含外部资源或脚本协议')
    missing=set(references)-ids
    if missing:raise ValueError('SVG 内部引用不存在：'+next(iter(sorted(missing))))
    if modified:
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        ET.register_namespace('xlink','http://www.w3.org/1999/xlink')
        blob=ET.tostring(root,encoding='utf-8',xml_declaration=True)
        if len(blob)>LIMIT_IMAGE:raise ValueError('引用图片内嵌后 SVG 超过 12 MB')
    return blob


def guard_svg(blob: bytes) -> None:
    normalize_svg(blob)


def check_image(ext: str, blob: bytes, limit: int = LIMIT_IMAGE) -> None:
    if len(blob)>limit: raise ValueError(f'图片超过 {limit//(1024*1024)} MB')
    if ext=='.png' and not blob.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('PNG 格式不匹配')
    if ext in {'.jpg','.jpeg'} and not blob.startswith(b'\xff\xd8\xff'):raise ValueError('JPEG 格式不匹配')
    if ext=='.gif' and blob[:6] not in (b'GIF87a',b'GIF89a'):raise ValueError('GIF 格式不匹配')
    if ext=='.webp' and not(blob[:4]==b'RIFF' and blob[8:12]==b'WEBP'):raise ValueError('WEBP 格式不匹配')
    if ext=='.svg':guard_svg(blob)
    if ext=='.emf':validate_emf(blob)
    if ext=='.pdf':validate_pdf(blob)


def clean_asset_name(name: str) -> str:
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,120}',name):
        raise ValueError('附件名不合法')
    if Path(name).suffix.lower() not in ALLOWED_ASSET:raise ValueError('附件格式不受支持')
    if name.split('.')[0].upper() in WINDOWS_RESERVED:raise ValueError('附件名是 Windows 保留名称')
    return name


EXTERNAL_CSS=re.compile(r'@import\s+|url\s*\(\s*["\']?\s*(?:https?://|//|file:|javascript:)',re.I)


class HtmlAudit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False);self.errors=[];self.reader_scripts=0;self.pdf_blocks=[];self.in_pdf=False;self.in_style=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='style':self.in_style=True
        if tag in {'iframe','object','embed','link','form','base','meta'}:
            if not(tag=='meta' and (a.get('charset','').lower()=='utf-8' or
                (a.get('name','').lower()=='viewport' and a.get('content','')=='width=device-width,initial-scale=1') or
                (len(attrs)==2 and set(a)=={'name','content'} and a.get('name','').lower()=='hrs-render-profile' and a.get('content','') in ('free','engineering')))):
                self.errors.append('禁止的 HTML 元素：'+tag)
        if tag=='script':
            if a.get('id')=='hrs-pdf-originals':self.pdf_blocks.append('');self.in_pdf=True
            first_party_reader=a.get('id')=='hrs-reader-runtime' and len(a)==1
            if first_party_reader:self.reader_scripts+=1
            elif not(a.get('id') in {'report-source','hrs-pdf-originals'} and a.get('type')=='application/json' and len(a)==2):
                self.errors.append('可执行 JavaScript 不允许出现在交付 HTML')
        for k,v in attrs:
            k=k.lower();v=v or ''
            if k=='style' and EXTERNAL_CSS.search(v):self.errors.append('CSS 引用了外部文件')
            if k.startswith('on'):self.errors.append('事件处理属性不允许')
            if k in {'src','href','xlink:href'}:
                if tag=='a' and k=='href':
                    if re.match(r'\s*(javascript:|data:|file:)',v,re.I):self.errors.append('链接协议不安全')
                elif tag in {'use','a'} and v.startswith('#'):pass
                elif tag=='img' and k=='src' and re.match(r'^data:image/(png|jpeg|gif|webp|svg\+xml);base64,',v):pass
                else:self.errors.append(f'有外部文件依赖：{tag}.{k}')

    def handle_data(self,data):
        if self.in_pdf:self.pdf_blocks[-1]+=data
        if self.in_style and EXTERNAL_CSS.search(data):self.errors.append('CSS 引用了外部文件')

    def handle_endtag(self,tag):
        if tag=='script':self.in_pdf=False
        if tag=='style':self.in_style=False


def audit_export(html_document: str) -> None:
    if not html_document.lstrip().lower().startswith('<!doctype html>'):
        raise ValueError('交付文档缺少 HTML doctype')
    parser=HtmlAudit();parser.feed(html_document)
    # Interactive reports may execute exactly one trusted, local reader script.
    # Content must match the shipped module BYTE FOR BYTE. A different script,
    # extra attributes, network links, handlers, or a modified copy is rejected.
    allowed_reader=re.findall(r'<script\s+id=["\']hrs-reader-runtime["\']\s*>([\s\S]*?)</script\s*>',html_document,re.I)
    if parser.reader_scripts or allowed_reader:
        canonical=(WEB/'report_reader.js').read_bytes().decode('utf-8')
        if parser.reader_scripts!=1 or len(allowed_reader)!=1 or (allowed_reader[0]!=canonical and digest(allowed_reader[0].encode('utf-8')) not in LEGACY_READER_SHA256):
            parser.errors.append('交互阅读模块不符合当前软件的完整性校验，拒绝加载未知脚本')
    # Check actual style nodes/attributes, not inert Markdown in source JSON or
    # escaped code examples. Unsafe source must remain recoverable byte-for-byte.
    # Optional read-only PDF attachments are separately bounded and authenticated.
    pdf_blocks=parser.pdf_blocks
    if len(pdf_blocks)>1:raise ValueError('PDF 附件数据块重复')
    if pdf_blocks:
        entries=json.loads(pdf_blocks[0]);total=0
        if not isinstance(entries,dict) or len(entries)>100:raise ValueError('PDF 附件清单无效')
        for name,item in entries.items():
            if not re.fullmatch(r'[a-f0-9]{16}\.pdf',name,re.I) or not isinstance(item,dict) or set(item)!={'base64','bytes','sha256'}:raise ValueError('PDF 附件字段无效')
            encoded=item['base64']
            if not isinstance(encoded,str) or len(encoded)>16*1024*1024:raise ValueError('PDF 附件超限')
            try:raw=base64.b64decode(encoded,validate=True)
            except ValueError as exc:raise ValueError('PDF 附件编码无效') from exc
            validate_pdf(raw);total+=len(raw)
            if total>30*1024*1024 or type(item['bytes']) is not int or len(raw)!=item['bytes'] or digest(raw)!=item['sha256']:raise ValueError('PDF 附件大小或摘要不符')
    if parser.errors:raise ValueError('; '.join(parser.errors[:5]))
    if not re.search(r'id=["\']report-source["\']',html_document):
        raise ValueError('缺少可再次编辑的源数据')


def pick_browser() -> str | None:
    override=os.environ.get('STUDIO_BROWSER_PATH')
    if override:
        if Path(override).is_file():return str(Path(override))
        raise ValueError('STUDIO_BROWSER_PATH 指向的浏览器不存在')

    # Windows portable: prefer installed Google Chrome before any older Edge.
    # This changes browser selection only, not the JavaScript/runtime contracts.
    if os.name=='nt':
        for envvar in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
            home=os.environ.get(envvar)
            if not home:continue
            chrome=Path(home)/'Google/Chrome/Application/chrome.exe'
            if chrome.is_file():return str(chrome)

    for name in ('chrome','chrome.exe','google-chrome','google-chrome-stable',
                 'chromium','chromium-browser'):
        found=shutil.which(name)
        if found:return found

    # Keep Edge as a fallback when Chrome/Chromium is not installed.
    for name in ('msedge','msedge.exe'):
        found=shutil.which(name)
        if found:return found
    if os.name=='nt':
        for envvar in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
            home=os.environ.get(envvar)
            if not home:continue
            edge=Path(home)/'Microsoft/Edge/Application/msedge.exe'
            if edge.is_file():return str(edge)
    return None


def render_pdf(html_file: Path, pdf_file: Path) -> None:
    """Print a fully self-contained HTML using installed Chromium/Edge, offline."""
    from host_services import render_desktop_pdf
    if render_desktop_pdf(html_file,pdf_file):return
    browser=pick_browser()
    if not browser:raise RuntimeError('找不到 Edge/Chrome/Chromium，请使用浏览器的“打印→另存为 PDF”')
    with tempfile.TemporaryDirectory(prefix='report_studio_pdf_') as profile:
        args=[browser,'--headless=new','--disable-gpu','--no-first-run',
              '--no-default-browser-check','--disable-background-networking',
              '--disable-extensions','--disable-sync','--no-pdf-header-footer',
              '--user-data-dir='+profile,'--print-to-pdf='+str(pdf_file),
              html_file.resolve().as_uri()]
        # Chromium refuses root on Linux without this flag. Never needed on Windows.
        if os.name!='nt' and hasattr(os,'geteuid') and os.geteuid()==0:args.insert(1,'--no-sandbox')
        try:
            # Do not capture browser pipes: child processes could inherit descriptors and
            # cause subprocess.run to wait beyond timeout after the parent has exited.
            result=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                  timeout=30,check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('本机浏览器 PDF 导出超时；请改用“打印→另存为 PDF”') from exc
        if result.returncode!=0 or not pdf_file.is_file() or pdf_file.stat().st_size<100:
            raise RuntimeError('浏览器生成 PDF 失败；可以使用“打印→另存为 PDF”备用方式')
        if not pdf_file.read_bytes().startswith(b'%PDF-'):
            raise RuntimeError('浏览器未生成有效的 PDF 文件')


def template_info(template_id: str) -> dict:
    if template_id not in TEMPLATES:raise ValueError('未知的新建模板')
    return TEMPLATES[template_id]


def document_title(text: str) -> str:
    match=re.search(r'^#\s+(.+?)\s*$',text,re.M)
    return (match.group(1).strip() if match else '未命名报告')[:90]


from report_workspace import (info as report_workspace_info, list_reports, lifecycle as report_lifecycle,
    CopyAsset, Progress, WorkspaceJobs, SCHEMA as REPORT_WORKSPACE_SCHEMA,
    freeze_origin, plan_sync, apply_sync, ORIGIN_FILE)


class StudioServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets another process bind the same port.
    allow_reuse_address=os.name!='nt'
    def __init__(self, addr, project: Path=DEFAULT, workspace: Path | None=None,
                 require_project_location: bool=False):
        self.project=project.resolve()          # legacy v0.1 directory, keeps existing data intact
        self.workspace=(workspace or self.project.parent).resolve()
        self.workspace.mkdir(parents=True,exist_ok=True)
        self.project.mkdir(parents=True,exist_ok=True)
        (self.project/'assets').mkdir(exist_ok=True)
        (self.project/'output').mkdir(exist_ok=True)
        self.drafts=self.workspace/'.drafts'
        self.drafts.mkdir(exist_ok=True)
        self.doc=self.project/'report.md'       # compatibility with v0.1 API tests
        if not self.doc.exists():atomic_write(self.doc,b'# New report\n\n')
        self.registry=ProjectRegistry(self.workspace)
        # Standalone Test API calls preserve v0.5.x compatibility. The actual
        # Windows portable launcher and source CLI enforce explicit selection.
        self.require_project_location=require_project_location
        self.lock=threading.RLock()
        self.readpacks=ReadPackManager()  # Read-only external bundles; never registered as editable projects.
        self.word_export=WordExport(HERE,self.workspace)
        from module_exports import ModuleExports
        self.module_exports=ModuleExports(self.workspace)
        self.workspace_jobs=WorkspaceJobs()
        from native_picker import configure as configure_picker_memory
        configure_picker_memory(self.workspace)
        super().__init__(addr,Handler)

    def server_close(self):
        try:
            super().server_close()
        finally:
            self.workspace_jobs.close()
            self.module_exports.close()

    def project_path(self, doc_id: str) -> Path | None:
        if doc_id=='new':return None
        if doc_id=='legacy':return self.project
        if not isinstance(doc_id,str) or not DOC_ID.fullmatch(doc_id):raise ValueError('文档 ID 无效')
        registered=self.registry.lookup(doc_id)
        if registered is not None:return registered
        result=self.workspace/doc_id
        if is_link(result) or not result.is_dir() or not (result/'report.md').is_file():
            raise ValueError('文档不存在或已移动')
        return result

    def draft_path(self, draft_id: str) -> Path:
        if not isinstance(draft_id, str) or not DRAFT_ID.fullmatch(draft_id):
            raise ValueError('草稿 ID 无效')
        path=self.drafts/draft_id
        if is_link(path):raise ValueError('草稿目录不可为符号链接')
        return path

    def read_draft(self, draft_id: str) -> dict:
        path=self.draft_path(draft_id)/'state.json'
        if not path.is_file() or is_link(path):raise ValueError('找不到恢复草稿')
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('draft_id')!=draft_id or data.get('document_id') not in ('new','legacy') and not DOC_ID.fullmatch(str(data.get('document_id',''))):
            raise ValueError('草稿的文档绑定无效')
        return data

    def pending_drafts(self,document_id=None) -> list:
        out=[]
        for path in self.drafts.iterdir():
            if not path.is_dir() or is_link(path) or not DRAFT_ID.fullmatch(path.name):continue
            try:
                item=self.read_draft(path.name)
                doc_id=item['document_id']
                if document_id is not None and doc_id!=document_id:continue
                if doc_id!='new':
                    actual=self.project_path(doc_id)
                    if digest((actual/'report.md').read_bytes())==digest(item['markdown'].encode('utf-8')):
                        continue  # Already committed before an interrupted cleanup.
                out.append({'draft_id':path.name,'document_id':doc_id,'template':item['template'],
                            'title':document_title(item['markdown']),'updated':item.get('updated',''),
                            'seq':item.get('seq',0)})
            except (ValueError,TypeError,OSError,UnicodeError,KeyError,json.JSONDecodeError):continue
        out.sort(key=lambda d:d['updated'],reverse=True)
        return out if document_id is not None else out[:30]

    def recent(self) -> list:
        projects=[];paths=[('legacy',self.project)]
        for child in self.workspace.iterdir():
            if child.is_dir() and not is_link(child) and DOC_ID.fullmatch(child.name) and child.name not in self.registry.mapping:
                paths.append((child.name,child))
        for doc_id in self.registry.mapping:
            try:paths.append((doc_id,self.project_path(doc_id)))
            except (ValueError,OSError):continue  # Missing drive: keep registry, do not fall back to stale source.
        for doc_id,p in paths:
            doc=p/'report.md'
            if not doc.is_file() or is_link(doc):continue
            try:
                meta=json.loads((p/'meta.json').read_text(encoding='utf-8')) if (p/'meta.json').is_file() else {}
                if report_workspace_info(p,self.workspace) and meta.get('workspace_state')=='archived':continue
                title=meta.get('title') or document_title(doc.read_text(encoding='utf-8'))
                updated=meta.get('updated') or datetime.fromtimestamp(doc.stat().st_mtime,timezone.utc).isoformat()
                projects.append({'id':doc_id,'title':title,'updated':updated,
                                 'template':meta.get('template','engineering'),
                                 'theme':meta.get('theme','engineering'),
                                 'external_project':doc_id in self.registry.mapping,'report_workspace':report_workspace_info(p,self.workspace)})
            except (OSError,UnicodeError,ValueError,TypeError,json.JSONDecodeError):continue
        projects.sort(key=lambda x:x['updated'],reverse=True)
        return projects[:15]


class Handler(BaseHTTPRequestHandler):
    server:StudioServer
    def log_message(self,fmt,*args):print('[local] '+fmt%args)
    def bytes(self,data,typ,status=200,filename=None):
        self.send_response(status)
        self.send_header('Content-Type',typ)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        # SVG opened directly (e.g. "open original") must never run scripts in
        # the editor origin, even from an external project that skipped import.
        if typ.startswith('image/svg+xml'):self.send_header('Content-Security-Policy',SVG_DOCUMENT_CSP)
        if filename:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(filename))
        self.end_headers();self.wfile.write(data)
    def resp(self,obj,status=200):
        self.bytes(json.dumps(obj,ensure_ascii=False).encode('utf-8'),'application/json; charset=utf-8',status)
    def fail(self,message,status=400):self.resp({'ok':False,'error':str(message)},status)
    def _origin_ok(self):
        host=self.headers.get('Host','')
        if not re.fullmatch(r'(127\.0\.0\.1|localhost)(:\d+)?',host):return False
        origin=self.headers.get('Origin')
        return not origin or bool(re.fullmatch(r'http://(127\.0\.0\.1|localhost):\d+',origin))
    def _parameters(self):
        return parse_qs(urlsplit(self.path).query)
    def _docid(self, req=None):
        if req is None:return self._parameters().get('document_id',['legacy'])[0]
        return req.get('document_id','legacy')
    def _template(self, req=None):
        if req is None:return self._parameters().get('template',['engineering'])[0]
        return req.get('template','engineering')
    def _context(self,doc_id,template='engineering'):
        if doc_id=='new':
            info=template_info(template)
            raw=info['markdown'].encode('utf-8')
            return None,raw,template,info['theme']
        p=self.server.project_path(doc_id)
        raw=(p/'report.md').read_bytes()
        try:meta=json.loads((p/'meta.json').read_text(encoding='utf-8'))
        except (FileNotFoundError,json.JSONDecodeError,OSError):meta={}
        return p,raw,meta.get('template','engineering'),meta.get('theme','engineering')
    def _check_revision(self,req,raw):
        if req.get('revision')!=digest(raw):
            self.resp({'ok':False,'error':'源文件已由其他窗口或程序修改；请重新载入，避免覆盖。','revision':digest(raw)},409)
            return False
        return True
    def _conflict(self,req):
        try: _,raw,_,_=self._context(self._docid(req),self._template(req))
        except ValueError:return True
        return not self._check_revision(req,raw)
    def _draft_id(self,req):
        did=req.get('draft_id')
        if not isinstance(did,str) or not DRAFT_ID.fullmatch(did):raise ValueError('草稿 ID 无效')
        return did
    def _verify_draft_owner(self,draft_id,doc_id):
        try:old=self.server.read_draft(draft_id)
        except ValueError:return
        if old['document_id']!=doc_id:raise ValueError('草稿与来源文档不匹配')
    def _clear_draft(self,draft_id):
        folder=self.server.draft_path(draft_id)
        if folder.is_dir():shutil.rmtree(folder)
    def _write_draft(self,req):
        did=self._draft_id(req);doc_id=self._docid(req)
        self.server.project_path(doc_id)  # validate/locate without touching the report
        self._verify_draft_owner(did,doc_id)
        markdown=req.get('markdown');seq=req.get('seq');template=self._template(req)
        template_info(template)
        if not isinstance(markdown,str) or len(markdown.encode('utf-8'))>10*1024*1024:
            raise ValueError('草稿正文必须是不超过 10 MB 的字符串')
        if type(seq) is not int or not (1<=seq<=2147483647):raise ValueError('草稿版本号无效')
        base=req.get('base_revision')
        if not isinstance(base,str) or not re.fullmatch('[a-f0-9]{64}',base):raise ValueError('原正式版本绑定无效')
        folder=self.server.draft_path(did)
        try:previous=self.server.read_draft(did)
        except ValueError:previous=None
        if previous and seq<=previous['seq']:
            return self.resp({'ok':True,'accepted':False,'seq':previous['seq'],'markdown_sha256':digest(previous['markdown'].encode('utf-8'))})
        profile=normalize_profile(req.get('render_profile',(previous or {}).get('render_profile')))
        folder.mkdir(exist_ok=True)
        write_json(folder/'state.json',{'format':'html-report-studio-draft-v1','draft_id':did,
            'document_id':doc_id,'template':template,'base_revision':base,'seq':seq,
            'render_profile':profile,'render_options':normalize_options(req.get('render_options',(previous or {}).get('render_options'))),
            'color_theme':normalize_color_theme(req.get('color_theme',(previous or {}).get('color_theme'))),
            'markdown':markdown,'updated':datetime.now(timezone.utc).isoformat()})
        self.resp({'ok':True,'accepted':True,'seq':seq,'markdown_sha256':digest(markdown.encode('utf-8'))})
    def _picker_origin_ok(self):
        # Explicit interaction header + same-origin Origin required for file dialog.
        if self.headers.get('X-HRS-Project-Action')!='user-action':return False
        origin=self.headers.get('Origin')
        if not origin:return False
        host=self.headers.get('Host','')
        return bool(re.fullmatch(r'(127\.0\.0\.1|localhost):\d+',host)) and origin=='http://'+host

    def _reader_action_ok(self):
        # Native folder chooser and ZIP upload require an explicit same-origin
        # user action. A custom header forces CORS preflight on foreign sites.
        if self.headers.get('X-HRS-Reader-Action') != 'user-action':return False
        host=self.headers.get('Host','')
        origin=self.headers.get('Origin')
        return bool(re.fullmatch(r'(127\.0\.0\.1|localhost):\d+',host)) and origin=='http://'+host

    def import_local_file(self,req):
        if not self._picker_origin_ok():return self.fail('请通过编辑器的导入按钮选择文稿',403)
        if req:raise ValueError('导入路径只能来自本机文件选择窗口')
        try:source=pick_import_file()
        except NotImplementedError as exc:return self.fail(str(exc),501)
        if source is None:return self.resp({'ok':True,'cancelled':True})
        source=Path(source)
        if is_link(source) or not source.is_file():raise ValueError('所选文稿不是普通文件')
        if source.suffix.lower() in ('.md','.markdown'):
            from markdown_import import prepare_markdown_import
            result=prepare_markdown_import(source,check_image)
        elif source.suffix.lower() in ('.html','.htm'):
            if source.stat().st_size>36*1024*1024:raise ValueError('HTML 超过 36 MiB')
            result={'kind':'html','filename':source.name,'source':source.read_bytes().decode('utf-8-sig')}
        else:raise ValueError('只接受 Markdown 或可回编 HTML')
        return self.resp({'ok':True,**result})

    def readpack_open_zip(self,req):
        if not self._reader_action_ok():return self.fail('阅读包必须在编辑器内主动选择',403)
        encoded=req.get('base64')
        if not isinstance(encoded,str) or len(encoded)>MAX_ZIP_BYTES*2:
            raise ValueError('阅读包 ZIP 大小无效或超过 24 MiB')
        try:payload=base64.b64decode(encoded,validate=True)
        except Exception as exc:raise ValueError('阅读包 ZIP Base64 无效') from exc
        if len(payload)>MAX_ZIP_BYTES:raise ValueError('阅读包 ZIP 超过 24 MiB')
        try:bundle=ReadBundle(source='zip',archive=payload)
        except zipfile.BadZipFile as exc:raise ValueError('阅读包不是有效 ZIP 文件') from exc
        self.resp(self.server.readpacks.register(bundle))

    def readpack_close(self,req):
        if not self._reader_action_ok():return self.fail('只能通过当前编辑器关闭阅读包',403)
        self.server.readpacks.close(req.get('reader_id'))
        return self.resp({'ok':True})

    def readpack_open_folder(self,req):
        if not self._reader_action_ok():return self.fail('阅读包必须在编辑器内主动选择',403)
        directory=pick_project_parent(reading_pack=True)
        if directory is None:return self.fail('已取消选择阅读包文件夹',409)
        bundle=ReadBundle(source='folder',root=directory)
        self.resp(self.server.readpacks.register(bundle))

    def readpack_document(self):
        params=self._parameters()
        rid=params.get('reader_id',[''])[0]
        bundle=self.server.readpacks.get(rid)
        path=params.get('path',[bundle.main])[0]
        item=bundle.document(path)
        self.resp({'ok':True,**item})

    def readpack_file(self):
        params=self._parameters()
        rid=params.get('reader_id',[''])[0]
        bundle=self.server.readpacks.get(rid)
        path=params.get('path',[''])[0]
        data=bundle.read(path)
        extension=Path(path).suffix.lower()
        if extension=='.svg':
            # Rendering SVG as an <img> is sandboxed by the browser, but direct
            # opening should be safe too: use exactly the project SVG sanitizer.
            data=normalize_svg(data)
        # Read-only packs have their own (larger) per-file limits in reading_pack.
        if extension in ALLOWED_IMAGE:
            check_image(extension,data,limit=READER_MAX_IMAGE)
        if extension=='.pdf':validate_pdf(data,limit=READER_MAX_PDF)
        self.bytes(data,READER_MIME[extension])

    def project_pick(self,req):
        if not self._picker_origin_ok():return self.fail('只有当前编辑器明确点击才能选择本机文件夹',403)
        operation=req.get('action');doc_id=self._docid(req)
        if operation not in ('create','migrate'):raise ValueError('未知目录选择操作')
        if operation=='migrate' and self.server.project_path(doc_id) is None:
            raise ValueError('不能迁移未正式保存的项目')
        parent=pick_project_parent()
        if parent is None:return self.resp({'ok':False,'error':'用户取消选择工程父目录'},409)
        with self.server.lock:
            selection=self.server.registry.new_selection(operation,doc_id,parent,req.get('project_name',''))
        self.resp({'ok':True,**selection})

    def project_migrate(self,req):
        doc_id=self._docid(req)
        if doc_id in ('new','legacy'):
            raise ValueError('请先打开有项目 ID 的报告进行迁移')
        folder,old,_,_=self._context(doc_id)
        if not self._check_revision(req,old):return
        target=self.server.registry.consume_selection(req.get('selection_token'),'migrate',doc_id)
        files=copy_project_tree(folder,target)
        try:self.server.registry.register(doc_id,target)
        except Exception:
            # The target is a verified copy and safe to retain for recovery;
            # registry still points to original project after an index failure.
            raise RuntimeError('项目复制完成但登记位置失败；新目录仍在，请核对后再处理')
        self.resp({'ok':True,'document_id':doc_id,'project_path':str(target),
                   'backup_original':str(folder),'files_verified':files,
                   'revision':digest((target/'report.md').read_bytes())})

    def project_open(self,req):
        if not self._picker_origin_ok():return self.fail('仅允许编辑器显式选择已存在工程',403)
        directory=pick_project_parent(open_existing=True)
        if directory is None:return self.fail('已取消打开工程',409)
        project=_trusted_project_directory(directory)
        if project==self.server.workspace or self.server.workspace in project.parents:
            raise ValueError('这是旧版内部目录，请通过最近打开并迁移')
        with self.server.lock:
            for doc_id,root in self.server.registry.mapping.items():
                if Path(root)==project:return self.resp({'ok':True,'document_id':doc_id,'project_path':str(project),'already_open':True})
            raw=(project/'report.md').read_bytes()
            if len(raw)>10*1024*1024:raise ValueError('report.md 超过编辑器支持大小')
            raw.decode('utf-8')
            doc_id=uuid.uuid4().hex
            self.server.registry.register(doc_id,project)
        self.resp({'ok':True,'document_id':doc_id,'project_path':str(project)})

    def _export_output(self,req):
        doc_id=self._docid(req)
        folder,raw,_,_=self._context(doc_id,self._template(req))
        if folder is None:raise ValueError('请先创建工程目录，导出不能直接放在 Downloads')
        if self.server.require_project_location and doc_id not in self.server.registry.mapping:
            raise ValueError('请先把旧文档迁移到独立工程目录后再导出')
        # read-only source and asset dependency validation, same as preflight
        snap=self._checked_export_snapshot(req)
        html=self._checked_export_html(req)
        kind='归档' if req.get('source_mode')=='recompilable' else '阅读'
        quality=req.get('quality','standard')
        if quality not in ('compact','standard','print','original'):
            raise ValueError('导出图像质量无效')
        date=datetime.now().strftime('%Y%m%d_%H%M%S')
        prefix='笔记' if normalize_profile(req.get('render_profile'))=='free' else '报告'
        filename=f'{prefix}_{kind}_{quality}_{date}.html'
        output=folder/'output'
        if is_link(output):raise ValueError('output 目录不能指向符号链接')
        output.mkdir(exist_ok=True)
        target=output/filename
        if target.exists():target=output/f'{prefix}_{kind}_{quality}_{date}_{uuid.uuid4().hex[:6]}.html'
        atomic_write(target,html.encode('utf-8'))
        # A concurrent outside process may have changed assets during write.
        # Do not report success if post-write snapshot no longer matches.
        try:
            after=self._readonly_export_snapshot(req)
            if after['files']!=snap['files'] or after['revision']!=snap['revision']:
                raise RuntimeError('导出后检测到工程文件变更；输出不作为可靠归档')
        except Exception:
            try:target.unlink()
            except OSError:pass
            raise
        self.resp({'ok':True,'path':str(target),'filename':target.name,'bytes':target.stat().st_size,
                   'document_id':doc_id,'quality':quality,'source_mode':req.get('source_mode'),
                   'result_token':self.server.word_export.result(target)})

    def _backup(self,p):
        return backup_report(p)
    def _store_meta(self,p,doc_id,text,template,theme,render_profile=None,render_options=None,color_theme=None):
        path=p/'meta.json'
        try:existing=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        except (OSError,ValueError):existing={}
        if not isinstance(existing,dict):existing={}
        now=datetime.now(timezone.utc).isoformat()
        # Keep fields written by other tools; only the managed keys are refreshed.
        info={**existing,'version':2,'title':document_title(text),'template':template,'theme':theme,
              'render_profile':normalize_profile(render_profile if render_profile is not None else existing.get('render_profile')),
              'render_options':normalize_options(render_options if render_options is not None else existing.get('render_options')),
              'color_theme':normalize_color_theme(color_theme if color_theme is not None else existing.get('color_theme')),
              'created':existing.get('created',now),'updated':now}
        write_json(path,info)
    def do_GET(self):
        if not self._origin_ok():return self.fail('仅允许本机访问',403)
        p=unquote(urlsplit(self.path).path)
        try:
            if p in ('/','/index.html'):return self.static('index.html')
            if p.startswith('/web/'):return self.static(p[len('/web/'):])
            if p.startswith('/docs/'):
                return self.static(p[len('/docs/'):],HERE/'docs',
                                   {'.html','.md','.json','.png','.jpg','.jpeg','.webp','.svg'})
            if p=='/工程报告源格式_v1_规范.md':p='/'+SOURCE_SPEC
            if p in ('/README.md','/CHANGELOG.md','/'+SOURCE_SPEC):
                return self.static(p[1:],HERE,{'.md'})
            if p=='/api/readpack/document':return self.readpack_document()
            if p=='/api/readpack/file':return self.readpack_file()
            if p.startswith('/assets/'):
                name=clean_asset_name(p[len('/assets/'):]);doc_id=self._docid()
                folder=self.server.project_path(doc_id)
                requested_draft=self._parameters().get('draft_id',[None])[0]
                if requested_draft:
                    draft_dir=self.server.draft_path(requested_draft)
                    self._verify_draft_owner(requested_draft,doc_id)
                    image=draft_dir/'assets'/name
                    if image.is_file() and not is_link(image):
                        return self.bytes(image.read_bytes(),ALLOWED_ASSET[image.suffix.lower()])
                if folder is None:return self.fail('图片尚未暂存',404)
                image=folder/'assets'/name
                if not image.is_file() or is_link(image):return self.fail('图片不存在',404)
                return self.bytes(image.read_bytes(),ALLOWED_ASSET[image.suffix.lower()])
            if p=='/api/health':return self.resp({'ok':True,'version':VERSION,'package_revision':PACKAGE_REVISION,'release':RELEASE,'offline':True,'pdf_browser_found':bool(os.environ.get('HRS_DESKTOP_BRIDGE') or pick_browser()),
                'portable':bool(getattr(getattr(self.server,'portable_lifecycle',None),'enabled',False)),
                'portable_instance':getattr(self.server,'portable_instance',None),'app_manifest_sha256':APP_MANIFEST_SHA256,
                'desktop':bool(os.environ.get('HRS_DESKTOP_BRIDGE'))})
            if p=='/api/templates':
                return self.resp({'ok':True,'templates':[dict(id=k,label=v['label'],description=v['description'],theme=v['theme']) for k,v in TEMPLATES.items()]})
            if p=='/api/recent':return self.resp({'ok':True,'documents':self.server.recent()})
            if p=='/api/drafts':return self.resp({'ok':True,'drafts':self.server.pending_drafts(self._parameters().get('document_id',[None])[0])})
            if p=='/api/draft':
                did=self._parameters().get('draft_id',[''])[0]
                draft=self.server.read_draft(did)
                return self.resp({'ok':True,'draft':draft,'markdown_sha256':digest(draft['markdown'].encode('utf-8'))})
            if p=='/api/doc':
                doc_id=self._docid();folder,raw,template,theme=self._context(doc_id,self._template())
                return self.resp({'ok':True,'document_id':doc_id,'markdown':raw.decode('utf-8'),
                                  'revision':digest(raw),'title':document_title(raw.decode('utf-8')),
                                  'project':('新建 · '+TEMPLATES[template]['label'] if folder is None else document_title(raw.decode('utf-8'))),
                                  'template':template,'theme':theme,
                                  'render_profile':read_profile(folder,'engineering' if folder is None and template=='engineering' else None),
                                  'render_options':read_options(folder) if folder is not None else new_options('engineering' if template=='engineering' else 'free'),
                                  'color_theme':read_color_theme(folder),
                                  'project_path':str(folder) if folder else None,
                                  'external_project':doc_id in self.server.registry.mapping,
                                  'report_workspace':report_workspace_info(folder,self.server.workspace)})
            if p in ('/api/download','/api/download-pdf','/api/print'):
                doc_id=self._docid();folder=self.server.project_path(doc_id)
                if folder is None:return self.fail('请先保存报告',409)
                ext='pdf' if p=='/api/download-pdf' else 'html'
                target=folder/'output'/('报告_单文件.'+ext)
                if not target.is_file() or is_link(target):return self.fail('请先生成'+ext.upper(),404)
                content=target.read_bytes()
                typ='application/pdf' if ext=='pdf' else 'text/html; charset=utf-8'
                return self.bytes(content,typ,filename=(target.name if p!='/api/print' else None))
            return self.fail('页面不存在',404)
        except (ValueError,TypeError,UnicodeError) as exc:return self.fail(str(exc),400)
    def static(self,name,root=WEB,allowed_extensions=None):
        root=root.resolve()
        dest=(root/name).resolve()
        if (not dest.is_relative_to(root) or not dest.is_file() or
                (allowed_extensions is not None and dest.suffix.lower() not in allowed_extensions)):
            return self.fail('资源不存在',404)
        typ={'.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8',
             '.html':'text/html; charset=utf-8','.txt':'text/plain; charset=utf-8',
             '.md':'text/plain; charset=utf-8','.json':'application/json; charset=utf-8',
             '.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg',
             '.webp':'image/webp','.svg':'image/svg+xml','.ico':'image/x-icon',
             '.webmanifest':'application/manifest+json'}.get(dest.suffix.lower(),'application/octet-stream')
        self.bytes(dest.read_bytes(),typ)
    def do_POST(self):
        if not self._origin_ok():return self.fail('仅允许本机访问',403)
        if not self.headers.get('Content-Type','').startswith('application/json'):return self.fail('仅接受 JSON',415)
        try:count=int(self.headers.get('Content-Length','0'))
        except ValueError:return self.fail('Content-Length 无效',400)
        if not (0<count<=LIMIT_JSON):return self.fail('请求体为空或过大',413)
        try:
            req=json.loads(self.rfile.read(count))
            if not isinstance(req,dict):raise ValueError('请求必须是 JSON 对象')
            p=urlsplit(self.path).path
            if p=='/api/external/open':return self.open_external_link(req)
            if p=='/api/readpack/open-zip':return self.readpack_open_zip(req)
            if p=='/api/readpack/open-folder':return self.readpack_open_folder(req)
            if p=='/api/readpack/close':return self.readpack_close(req)
            if p=='/api/project/pick':return self.project_pick(req)
            if p=='/api/project/open':return self.project_open(req)
            if p=='/api/import/local-file':return self.import_local_file(req)
            if p=='/api/export/open-folder':
                if not self._picker_origin_ok():return self.fail('仅接受当前编辑器的打开文件夹操作',403)
                self.server.word_export.open_result(req.get('result_token'),folder=True)
                return self.resp({'ok':True})
            if p.startswith('/api/word/'):return self.word_export_action(p,req)
            # Slow, read-only or self-locking operations stay outside the global
            # lock so autosave and window-close drafts are not queued behind them.
            if p=='/api/report-workspace':return self.report_workspace_action(req)
            if p=='/api/validate':return self.validate(req)
            if p=='/api/pdf-snapshot':return self.pdf_snapshot(req)
            if p=='/api/pdf/store':return self.pdf_store_to_project(req)
            if p=='/api/upload':return self.upload(req)
            if p=='/api/clipboard/paste':return self.paste_native_clipboard(req)
            if p=='/api/clipboard/document':return self.paste_native_document(req)
            with self.server.lock:
                if p.startswith('/api/export/modules/'):return self.export_modules(p.rsplit('/',1)[1],req)
                if p=='/api/project/migrate':return self.project_migrate(req)
                if p=='/api/export/store':return self._export_output(req)
                if p=='/api/project/assets/scan':return self.assets_housekeeping_scan(req)
                if p=='/api/project/assets/trash':return self.assets_housekeeping_trash(req)
                if p=='/api/project/assets/restore':return self.assets_housekeeping_restore(req)
                if p=='/api/project/assets/purge':return self.assets_housekeeping_purge(req)
                if p=='/api/export-preflight':return self.export_preflight(req)
                if p=='/api/export-verify':return self.export_verify(req)
                if p=='/api/render-profile':return self.set_render_profile(req)
                if p=='/api/objects/copy':return self.objects_copy(req)
                if p=='/api/objects/paste':return self.objects_paste(req)
                if p=='/api/save':return self.save(req)
                if p=='/api/draft':return self._write_draft(req)
                if p=='/api/draft-discard':
                    did=self._draft_id(req)
                    if 'document_id' in req:self._verify_draft_owner(did,self._docid(req))
                    self._clear_draft(did)
                    return self.resp({'ok':True})
                if p=='/api/draft-import':return self.import_draft(req)
                if p=='/api/export':return self.export(req)
                if p=='/api/pdf':return self.pdf(req)
                if p=='/api/import':return self.import_report(req)
                return self.fail('接口不存在',404)
        except (ValueError,TypeError,UnicodeError) as exc:return self.fail(str(exc),400)
        except RuntimeError as exc:return self.fail(str(exc),409)
        except Exception as exc:
            print('[ERROR]',repr(exc))
            return self.fail('服务端操作失败：'+type(exc).__name__,500)
    def word_export_action(self,endpoint,req):
        # Native paths can only be selected by an explicit same-origin action;
        # later requests carry server tokens, never arbitrary filesystem paths.
        if not self._picker_origin_ok():return self.fail('仅接受当前编辑器的显式 Word 导出操作',403)
        exporter=self.server.word_export
        if endpoint=='/api/word/open':
            exporter.open_result(req.get('result_token'),req.get('folder') is True)
            return self.resp({'ok':True})
        with self.server.lock:
            folder,_,_,_=self._context(self._docid(req),self._template(req))
            key=str(folder) if folder is not None else 'new:'+self._draft_id(req)
        if endpoint=='/api/word/options':
            return self.resp({'ok':True,**exporter.describe(key),'output_directory':str(self.report_output(folder)) if folder else None})
        if endpoint=='/api/word/set-default-template':
            return self.resp({'ok':True,**exporter.set_default(key,req.get('template_token','default'))})
        if endpoint=='/api/word/pick-runtime':
            chosen=pick_project_parent(title='选择当前版 word_support 组件目录，或解压后的配套 Full 根目录')
            if chosen is None:return self.resp({'ok':True,'cancelled':True})
            exporter.select_bundle(chosen)
            return self.resp({'ok':True,**exporter.describe(key)})
        if endpoint=='/api/word/pick-formula':
            chosen=pick_import_file(word_formula=True)
            if chosen is None:return self.resp({'ok':True,'cancelled':True})
            exporter.select_formula(chosen)
            return self.resp({'ok':True,**exporter.describe(key)})
        if endpoint=='/api/word/pick-template':
            chosen=pick_import_file(word_template=True)
            if chosen is None:return self.resp({'ok':True,'cancelled':True})
            return self.resp({'ok':True,**exporter.select_template(key,chosen)})
        if endpoint=='/api/word/discard':
            exporter.discard(key,req.get('job_token'));return self.resp({'ok':True})
        if endpoint not in ('/api/word/prepare','/api/word/export'):return self.fail('Word 接口不存在',404)
        if endpoint=='/api/word/prepare':
            temporary=tempfile.TemporaryDirectory(prefix='hrs-word-export-')
            try:
                snapshot=Path(temporary.name)/'snapshot';snapshot.mkdir();(snapshot/'assets').mkdir()
                with self.server.lock:
                    folder,_,_,_=self._context(self._docid(req),self._template(req))
                    if folder is None:raise ValueError('请先创建独立工程，再导出到工程 output/ 目录')
                    if self.server.require_project_location and self._docid(req) not in self.server.registry.mapping and not report_workspace_info(folder,self.server.workspace):
                        raise ValueError('请先把旧文档迁移到独立工程目录后再导出')
                    checked={**req,'render_profile':'engineering','source_mode':'recompilable'}
                    freeze=self._readonly_export_snapshot(checked);key=str(folder)
                    template,template_sha=exporter.template(key,req.get('template_token','default'))
                    draft_assets=self.server.draft_path(self._draft_id(req))/'assets'
                    for name,info in freeze['files'].items():
                        staged=draft_assets/name
                        source=staged if staged.is_file() and not is_link(staged) else folder/'assets'/name
                        raw=source.read_bytes()
                        if digest(raw)!=info['sha256']:raise RuntimeError('冻结 Word 附件时源图发生变化，请重新导出')
                        (snapshot/'assets'/name).write_bytes(raw)
                    (snapshot/'report.md').write_bytes(req['markdown'].encode('utf8'))
                    write_json(snapshot/'meta.json',{'render_profile':normalize_profile(req.get('render_profile')),
                               'render_options':normalize_options(req.get('render_options'))})
                    origin=folder/'bridge-origin.json'
                    if origin.is_file() and not is_link(origin):shutil.copyfile(origin,snapshot/origin.name)
                    if self._readonly_export_snapshot(checked)!=freeze:raise RuntimeError('冻结期间工程已变化，请重新导出')
                prepared=exporter.prepare(key,temporary,dict(req),freeze,template,template_sha)
                return self.resp({'ok':True,**prepared})
            except Exception:temporary.cleanup();raise
        if not exporter.running.acquire(blocking=False):raise RuntimeError('已有 Word 导出正在进行，请稍后再试')
        job=None
        try:
            job=exporter.take(key,req.get('job_token'))
            with self.server.lock:
                current=self._readonly_export_snapshot({**job['request'],'render_profile':'engineering','source_mode':'recompilable'})
                if current!=job['freeze']:raise RuntimeError('Word 准备后附件或源文件已改变，请重新生成')
                output=self.report_output(folder)
                if is_link(output):raise ValueError('output 目录不能指向符号链接')
                output.mkdir(exist_ok=True)
                stem=validate_project_name(req.get('filename','报告_Word'))
                target=output/(stem+'_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]+'.docx')
                working_copy=job['request']['markdown'].encode('utf8')!=(folder/'report.md').read_bytes()
            receipt=exporter.convert(job,target,req.get('model'))
            preference_warning=None
            try:exporter.remember(key,job['template'],job['request'].get('word_options'))
            except OSError:preference_warning='Word 已生成，但本次模板偏好未能保存'
            return self.resp({'ok':True,'path':str(target),'filename':target.name,'bytes':target.stat().st_size,
                              'result_token':exporter.result(target),'markdown_sha256':job['freeze']['markdown_sha256'],
                              'working_copy':working_copy,'preference_warning':preference_warning,'receipt':receipt})
        finally:
            if job is not None:job['temporary'].cleanup()
            exporter.running.release()

    def open_external_link(self,req):
        origin=urlsplit(self.headers.get('Origin') or self.headers.get('Referer') or '')
        if (self.headers.get('X-HRS-External-Link')!='user-action' or
            origin.scheme!='http' or origin.netloc!=self.headers.get('Host')):
            return self.fail('仅接受当前编辑器的显式外链点击',403)
        url=req.get('url')
        if not isinstance(url,str) or not (1<=len(url)<=8192) or re.search(r'[\x00-\x20\x7f-\x9f]',url):
            raise ValueError('外链 URL 无效')
        parsed=urlsplit(url)
        if parsed.scheme.lower() not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('外链仅允许无登录信息的 HTTP / HTTPS 地址')
        if os.name=='nt':os.startfile(url)
        elif not webbrowser.open(url,new=2):raise RuntimeError('系统浏览器未能启动')
        return self.resp({'ok':True,'opened_by':'system-default-browser'})

    def validate(self,req):
        ir=analyze_report_contract(req.get('markdown'))
        diagnostics=output_checks(ir,normalize_profile(req.get('render_profile')))+ir['diagnostics']
        valid=project_contract(ir)['sourceContractValid'] and not any(d['severity']=='error' for d in diagnostics)
        return self.resp({'ok':True,'valid':False,'source_contract_valid':valid,'safeToCompile':False,
           'output_blockers':sorted(BLOCKED_DIAGNOSTICS),
           'preflight':{'scope':'source-contract','complete':False,'next':'hrs check SOURCE --render-profile engineering'},'schema':ir['schema'],
           'diagnostics':diagnostics, 'stats':ir['stats'],
           'object_count':len(ir['objects']['ids']),'references':ir['references'],'offset_unit':ir['offset_unit'],'source_snapshot':ir['source_snapshot']})
    def _asset_housekeeping_origin_ok(self):
        # Unlike normal report preview, scanning/trashing project source files
        # requires an explicit same-origin POST with an action header.
        if self.headers.get('X-HRS-Asset-Action')!='user-action':return False
        host=self.headers.get('Host','')
        origin=self.headers.get('Origin') or self.headers.get('Referer')
        if not origin or not re.fullmatch(r'(127\.0\.0\.1|localhost):\d+',host):return False
        url=urlsplit(origin)
        return url.scheme=='http' and url.netloc==host and not url.username and not url.password

    def _asset_housekeeper(self,req):
        if not self._asset_housekeeping_origin_ok():
            self.fail('只有当前编辑器主动操作才能整理工程素材',403)
            return None
        doc_id=self._docid(req)
        folder,original,_,_=self._context(doc_id,self._template(req))
        if folder is None:raise ValueError('请先正式保存工程再检查素材')
        if self.server.require_project_location and doc_id not in self.server.registry.mapping:
            raise ValueError('请先将工程迁移到独立项目目录')
        if req.get('revision')!=digest(original):
            self.fail('正式报告在扫描期间发生变化，请刷新后重试',409)
            return None
        return AssetHousekeeper(folder,self.server.drafts,doc_id)

    def assets_housekeeping_scan(self,req):
        helper=self._asset_housekeeper(req)
        if helper is None:return
        result=helper.scan()
        result['batches']=helper.batches()
        result['trash']=helper.trash_snapshot()
        return self.resp(result)

    def assets_housekeeping_trash(self,req):
        helper=self._asset_housekeeper(req)
        if helper is None:return
        moved=helper.move_to_trash(req.get('selected'),include_history=req.get('include_history') is True)
        return self.resp(moved)

    def assets_housekeeping_restore(self,req):
        helper=self._asset_housekeeper(req)
        if helper is None:return
        recovered=helper.restore(req.get('batch_id'))
        return self.resp(recovered)

    def assets_housekeeping_purge(self,req):
        helper=self._asset_housekeeper(req)
        if helper is None:return
        if req.get('confirmed') is not True:raise ValueError('请先确认永久清空回收区')
        with report_lock(helper.root):
            if digest((helper.root/'report.md').read_bytes())!=req.get('revision'):
                raise RuntimeError('正式报告已变化，请重新检查')
            return self.resp(helper.purge(req.get('trash_revision')))

    def _checked_export_html(self,req):
        html=req.get('html')
        if not isinstance(html,str) or len(html.encode('utf-8'))>36*1024*1024:
            raise ValueError('导出 HTML 超过 36 MiB')
        audit_export(html)
        return html

    def _checked_export_snapshot(self,req):
        snap=self._readonly_export_snapshot(req)
        expected=req.get('asset_hashes')
        if not isinstance(expected,dict) or expected!={name:info['sha256'] for name,info in snap['files'].items()}:
            raise RuntimeError('导出前后原始附件校验不一致')
        if req.get('markdown_sha256')!=snap['markdown_sha256']:
            raise RuntimeError('导出时 Markdown 快照发生变化')
        return snap

    def export_modules(self,action,req):
        store=self.server.module_exports
        if action=='begin':
            if normalize_profile(req.get('render_profile'))!='free':raise ValueError('专题分册只适用于自由笔记')
            doc_id=self._docid(req)
            folder,original,_,_=self._context(doc_id,self._template(req))
            if folder is None or self.server.require_project_location and doc_id not in self.server.registry.mapping:
                raise ValueError('请先确定工程目录')
            if req.get('revision')!=digest(original):raise RuntimeError('正式文档已变化，请重新载入')
            text=req.get('markdown')
            if not isinstance(text,str) or len(text.encode('utf8'))>10*1024*1024 or digest(text.encode('utf8'))!=req.get('source_sha256'):
                raise ValueError('分册源快照无效')
            self._verify_draft_owner(self._draft_id(req),doc_id)
            context={key:req.get(key) for key in ('document_id','draft_id','revision','source_sha256')}
            context['folder']=folder
            token=store.begin(context,req.get('titles'))
            return self.resp({'ok':True,'token':token})
        token=req.get('token')
        job=store.get(token)
        for key in ('document_id','draft_id','revision','source_sha256'):
            if req.get(key)!=job['context'][key]:raise RuntimeError('分册源绑定已变化，请重新导出')
        if action=='cancel':
            store.cancel(token)
            return self.resp({'ok':True})
        if action=='stage':
            self._checked_export_snapshot(req)
            html=self._checked_export_html(req)
            if req.get('source_mode') not in ('reading','recompilable') or normalize_profile(req.get('render_profile'))!='free':
                raise ValueError('分册必须为自由笔记 HTML')
            request={key:value for key,value in req.items() if key not in ('html','token','index')}
            store.stage(token,req.get('index'),html.encode('utf8'),request)
            return self.resp({'ok':True,'staged':len(job['parts'])})
        if action=='finish':
            count=len(job['names'])
            stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
            filename=('笔记_分册_'+stamp+'.zip') if count>1 else job['names'][0][4:-5]+'_'+stamp+'.html'
            stem,suffix=Path(filename).stem,Path(filename).suffix;attempt=2
            while (job['context']['folder']/'output'/filename).exists():
                filename=f'{stem}_{attempt}{suffix}';attempt+=1
            target,names=store.finish(token,job['context']['folder']/'output',filename,self._checked_export_snapshot)
            return self.resp({'ok':True,'filename':target.name,'path':str(target),'bytes':target.stat().st_size,'modules':names,'document_id':req['document_id'],
                              'result_token':self.server.word_export.result(target)})
        raise ValueError('未知分册导出操作')

    def _readonly_export_snapshot(self,req,*,validate=True,progress=None):
        """Freeze/check the asset dependency graph without changing any project files."""
        doc_id=self._docid(req)
        folder,original,_,_=self._context(doc_id,self._template(req))
        if req.get('revision')!=digest(original):
            raise RuntimeError('正式文档版本已经变化，导出已中止，请重新载入')
        text=req.get('markdown')
        if not isinstance(text,str) or len(text.encode('utf-8'))>10*1024*1024:
            raise ValueError('待导出的 Markdown 大小无效')
        ir=analyze_report_contract(text)
        invalid=[d for d in ir['diagnostics'] if d['severity']=='error']
        if validate:
            if invalid:raise ValueError('导出结构错误：'+invalid[0]['message'])
            require_output(ir,req.get('render_profile',read_profile(folder)),req.get('accept_numbered_headings') is True)
        draft_id=self._draft_id(req)
        self._verify_draft_owner(draft_id,doc_id)
        draft_assets=self.server.draft_path(draft_id)/'assets'
        mode=req.get('source_mode','recompilable')
        if mode not in ('reading','recompilable'):raise ValueError('源文件策略不支持')
        if mode=='reading':
            # Reading-only exports need *only* the visible images. They do not
            # require sidecar EMF/fallback files that are not delivered.
            names=req.get('display_assets')
            if not isinstance(names,list) or len(names)>100 or not all(isinstance(x,str) for x in names):
                raise ValueError('阅读版显示附件列表无效')
            permitted=set(ir['assets'])
            resources=sorted({'assets/'+clean_asset_name(name) for name in names})
            if not set(resources)<=permitted:raise ValueError('显示附件不属于当前 Markdown')
        else:
            resources=ir['assets']
        result={}
        for resource in resources:
            if progress:progress.check()
            if not isinstance(resource,str) or not resource.startswith('assets/'):
                raise ValueError('导出资源路径不合法')
            name=clean_asset_name(resource[len('assets/'):])
            staged=draft_assets/name
            current=(folder/'assets'/name) if folder is not None else None
            if staged.is_file() and not is_link(staged):asset=staged
            elif current is not None and current.is_file() and not is_link(current):asset=current
            else:raise ValueError('导出资源不存在：assets/'+name)
            if asset.stat().st_size>LIMIT_IMAGE:
                raise ValueError('原始附件超过单图大小限制：assets/'+name)
            raw=asset.read_bytes()
            check_image(asset.suffix.lower(),raw)
            result[name]={'sha256':digest(raw),'bytes':len(raw)}
        return {'files':result,'revision':digest(original),'markdown_sha256':digest(text.encode('utf-8'))}

    def export_preflight(self,req):
        snap=self._readonly_export_snapshot(req)
        total=sum(meta['bytes'] for meta in snap['files'].values())
        self.resp({'ok':True,'files':snap['files'],'asset_count':len(snap['files']),
                   'source_bytes':total,'revision':snap['revision'],
                   'markdown_sha256':snap['markdown_sha256']})

    def export_verify(self,req):
        snap=self._readonly_export_snapshot(req)
        expected=req.get('asset_hashes')
        if not isinstance(expected,dict) or expected!={key:item['sha256'] for key,item in snap['files'].items()}:
            raise RuntimeError('导出过程中工程附件被修改，请重新导出')
        if req.get('markdown_sha256')!=snap['markdown_sha256']:
            raise RuntimeError('导出过程中 Markdown 快照发生变化')
        self.resp({'ok':True,'verified':len(snap['files']),'revision':snap['revision']})

    def pdf_store_to_project(self,req):
        # Same source/version/resource guarantee as HTML, followed by an isolated
        # PDF renderer. Only output/ can be written; never the project source.
        # Called without the server lock: the snapshot check and the final write
        # take it, while the slow headless-browser render (up to 30 s) does not
        # block draft autosave. The second snapshot rejects any change meanwhile.
        doc_id=self._docid(req)
        with self.server.lock:
            folder,raw,_,_=self._context(doc_id,self._template(req))
            if folder is None:raise ValueError('请先建立工程再输出 PDF')
            if self.server.require_project_location and doc_id not in self.server.registry.mapping:
                raise ValueError('请先迁移旧报告的独立工程目录')
            snap=self._readonly_export_snapshot(req)
            if req.get('markdown_sha256')!=snap['markdown_sha256'] or req.get('asset_hashes')!={name:info['sha256'] for name,info in snap['files'].items()}:
                raise RuntimeError('PDF 编译前 Markdown 或附件版本发生变化')
        html=req.get('html')
        if not isinstance(html,str) or len(html.encode('utf-8'))>36*1024*1024:
            raise ValueError('生成 PDF 的 HTML 超过 36 MiB')
        audit_export(html)
        with tempfile.TemporaryDirectory(prefix='hrs_pdf_output_') as tmp:
            html_path=Path(tmp)/'source.html';pdf_path=Path(tmp)/'result.pdf'
            atomic_write(html_path,html.encode('utf-8'))
            render_pdf(html_path,pdf_path)
            body=pdf_path.read_bytes()
            if not body.startswith(b'%PDF-'):raise RuntimeError('浏览器未生成 PDF 文件')
        with self.server.lock:
            if self._readonly_export_snapshot(req)!=snap:raise RuntimeError('PDF 生成期间正式稿或附件发生变化，请重新导出')
            output=folder/'output'
            if is_link(output):raise ValueError('项目 output 目录不能是链接')
            output.mkdir(exist_ok=True)
            prefix='笔记' if normalize_profile(req.get('render_profile'))=='free' else '报告'
            name=prefix+'_当前快照_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.pdf'
            target=output/name
            if target.exists():target=output/(prefix+'_当前快照_'+uuid.uuid4().hex[:8]+'.pdf')
            atomic_write(target,body)
            try:
                after=self._readonly_export_snapshot(req)
                if snap!=after:raise RuntimeError('PDF 输出后正式稿或附件发生变化')
            except Exception:
                try:target.unlink()
                except OSError:pass
                raise
        self.resp({'ok':True,'path':str(target),'filename':target.name,'bytes':len(body),'document_id':doc_id,
                   'result_token':self.server.word_export.result(target)})

    def _asset_preflight(self,req,asset_paths,p):
        draft_id=req.get('draft_id')
        if not draft_id:return {}
        did=self._draft_id(req)
        self._verify_draft_owner(did,self._docid(req))
        folder=self.server.draft_path(did)/'assets'
        prepared={}
        # Consume the already validated IR dependency list. A tutorial URL in
        # code, a comment or prose is not an attachment of this document.
        for path in asset_paths:
            name=path.removeprefix('assets/')
            clean_asset_name(name)
            current=(p/'assets'/name) if p else None
            stage=folder/name
            if stage.is_file() and not is_link(stage):
                data=stage.read_bytes();check_image(Path(name).suffix.lower(),data)
                if current and current.is_file() and current.read_bytes()!=data:
                    raise ValueError('附件同名且内容不同：'+name)
                prepared[name]=data
            elif current and current.is_file() and not is_link(current):pass
            else:raise ValueError('正式保存前找不到图片：assets/'+name)
        return prepared
    def _create_with_assets(self,text,template,theme,assets,project_target=None,meta_extra=None,progress=None,before_commit=None):
        doc_id=uuid.uuid4().hex
        final=project_target if project_target is not None else self.server.workspace/doc_id
        staging=final.parent/('.new_'+doc_id)
        if final.exists() or is_link(final):raise ValueError('项目目录已存在')
        staging.mkdir(exist_ok=False)
        try:
            (staging/'assets').mkdir()
            (staging/'output').mkdir()
            for name,data in assets.items():
                if progress:progress.check()
                if isinstance(data,CopyAsset):data.copy_to(staging/'assets'/name)
                else:atomic_write(staging/'assets'/name,data)
            atomic_write(staging/'report.md',text.encode('utf-8'))
            self._store_meta(staging,doc_id,text,template,theme)
            if meta_extra:
                meta=json.loads((staging/'meta.json').read_text('utf8'))
                atomic_write(staging/'meta.json',(json.dumps({**meta,**meta_extra},ensure_ascii=False,indent=2)+'\n').encode('utf8'))
            if progress:progress.check()
            if before_commit:before_commit()
            if final.exists() or is_link(final):raise ValueError('目标项目目录已被其他程序占用')
            os.replace(staging,final)
            if project_target is not None:
                with self.server.lock:self.server.registry.register(doc_id,final)
        except Exception:
            shutil.rmtree(staging,ignore_errors=True)
            # Only delete the target if it is the newly created path and has
            # not been committed to a usable registry mapping.
            if project_target is not None and doc_id not in self.server.registry.mapping:
                shutil.rmtree(final,ignore_errors=True)
            raise
        return final,doc_id
    def report_workspace_action(self,req):
        if not self._picker_origin_ok():return self.fail('临时工程页需要当前编辑器主动操作',403)
        doc_id=self._docid(req);draft_id=self._draft_id(req);owner=(doc_id,draft_id)
        action=req.get('action')
        if action in ('status','cancel'):
            return self.resp({'ok':True,**self.server.workspace_jobs.status(req.get('job_token'),owner,cancel=action=='cancel')})
        self._verify_draft_owner(draft_id,doc_id)
        if action in ('sync-plan','sync-apply'):
            folder,original,template,_=self._context(doc_id,self._template(req))
            descriptor=report_workspace_info(folder,self.server.workspace)
            if descriptor is None:raise ValueError('仅本机临时工程稿可以同步来源')
            if not self._check_revision(req,original):return
            self._readonly_export_snapshot({**req,'source_mode':'recompilable'},validate=False)
            origin,source_raw,origin_template,origin_theme=self._context(descriptor['origin_document_id'],descriptor['origin_template'])
            if origin is None:raise ValueError('请先正式保存来源工程')
            for item in self.server.pending_drafts(descriptor['origin_document_id']):
                draft=self.server.read_draft(item['draft_id'])
                if draft['base_revision']==digest(source_raw) and draft['markdown'].encode('utf8')!=source_raw:
                    raise ValueError('来源有未保存的恢复草稿，请先处理源稿修改；不会覆盖该草稿')
            roots=[self.server.draft_path(draft_id)/'assets',folder/'assets']
            if action=='sync-plan':result=plan_sync(folder,origin,descriptor,req,roots)
            else:result=apply_sync(folder,origin,descriptor,req,roots,
                after_commit=lambda candidate:self._store_meta(origin,descriptor['origin_document_id'],candidate.decode('utf8'),origin_template,origin_theme,
                    read_profile(origin),read_options(origin),read_color_theme(origin)))
            return self.resp({'ok':True,**result})
        if action=='list':
            return self.resp({'ok':True,**list_reports(self.server.workspace,doc_id,draft_id,
                offset=req.get('offset',0),limit=req.get('limit',30),include_archived=req.get('include_archived') is True,
                include_trash=req.get('include_trash') is True,source_sha256=req.get('source_sha256'))})

        if action in ('archive','unarchive','trash','restore'):
            target=req.get('target_document_id')
            # Bind management to the selected origin; never accept a registry or
            # externally supplied folder just because it carries this metadata.
            # Pagination is presentation only; target ownership is checked directly.
            root=self.server.workspace/('.report-workspace-trash' if action=='restore' else '')
            descriptor=report_workspace_info(root/str(target),root)
            if descriptor is None or descriptor['origin_document_id']!=doc_id or doc_id=='new' and descriptor.get('origin_draft_id')!=draft_id:
                raise ValueError('临时稿不属于当前来源')
            with self.server.lock:
                result=report_lifecycle(self.server.workspace,target,action,req.get('target_revision'))
            return self.resp({'ok':True,**result})
        if action=='save-independent':
            folder,original,template,theme=self._context(doc_id,self._template(req))
            if report_workspace_info(folder,self.server.workspace) is None:raise ValueError('仅临时工程稿使用此独立保存入口')
            ir=analyze_report_contract(req.get('markdown'))
            invalid=[d for d in ir['diagnostics'] if d['severity']=='error']
            if invalid:raise ValueError('工程文档结构错误：'+invalid[0]['message'])
            snapshot=self._readonly_export_snapshot({**req,'source_mode':'recompilable'},validate=False)
            with self.server.lock:target=self.server.registry.consume_selection(req.get('selection_token'),'create','new')
            roots=[self.server.draft_path(draft_id)/'assets',folder/'assets'];progress=Progress();assets={}
            for name,expected in snapshot['files'].items():
                asset=next((root/name for root in roots if (root/name).is_file() and not is_link(root/name)),None)
                if asset is None:raise ValueError('附件缺失：'+name)
                assets[name]=CopyAsset(asset,expected['sha256'],progress)
            def verify():
                if self._readonly_export_snapshot({**req,'source_mode':'recompilable'},validate=False)!=snapshot:
                    raise RuntimeError('独立保存期间来源或附件已变化')
            final,new_id=self._create_with_assets(req['markdown'],template,theme,assets,target,
                meta_extra={'render_profile':'engineering','render_options':normalize_options(req.get('render_options')),
                            'color_theme':normalize_color_theme(req.get('color_theme'))},before_commit=verify)
            return self.resp({'ok':True,'document_id':new_id,'project_path':str(final)})
        if action=='start':
            token=self.server.workspace_jobs.submit(owner,lambda progress:self._create_report_workspace(dict(req),progress))
            return self.resp({'ok':True,'job_token':token})
        if action=='create':return self.resp(self._create_report_workspace(req,Progress()))
        raise ValueError('未知临时工程页操作')

    def _create_report_workspace(self,req,progress):
        doc_id=self._docid(req);draft_id=self._draft_id(req)
        progress.check(phase='验证来源')
        folder,original,template,_=self._context(doc_id,self._template(req))
        if req.get('revision')!=digest(original):raise RuntimeError('原稿版本已变化，请重新载入后提取')
        full=req.get('full_markdown')
        if not isinstance(full,str) or len(full.encode('utf8'))>10*1024*1024 or digest(full.encode('utf8'))!=req.get('source_sha256'):
            raise ValueError('临时稿来源快照无效')
        def same_source():
            if digest(self._context(doc_id,template)[1])!=req['revision']:return False
            if full.encode('utf8')==original:return True
            draft=self.server.read_draft(draft_id)
            return draft['document_id']==doc_id and draft['base_revision']==req['revision'] and draft['markdown']==full
        if not same_source():raise RuntimeError('来源草稿尚未确认或已变化，请重新提取')
        transfer={**req,'source_mode':'recompilable','render_profile':'free'}
        snapshot=self._readonly_export_snapshot(transfer,validate=False,progress=progress)
        total=sum(entry['bytes'] for entry in snapshot['files'].values())
        if total>512*1024*1024:raise ValueError('临时报告附件超过512 MiB')
        progress.check(phase='复制附件',bytes_total=total)
        assets={};roots=[self.server.draft_path(draft_id)/'assets',folder/'assets' if folder else None]
        for name,expected in snapshot['files'].items():
            asset=next((root/name for root in roots if root and (root/name).is_file() and not is_link(root/name)),None)
            if asset is None:raise ValueError('附件缺失：'+name)
            assets[name]=CopyAsset(asset,expected['sha256'],progress)
        descriptor={'schema':REPORT_WORKSPACE_SCHEMA,'origin_document_id':doc_id,'origin_draft_id':draft_id,
                    'origin_revision':req['revision'],'origin_template':template,'source_sha256':req['source_sha256'],
                    'title':str(req.get('title','临时工程报告'))[:500]}
        origin_snapshot=freeze_origin(full,req['markdown'],req.get('sync'),doc_id)
        descriptor['sync_available']=origin_snapshot is not None and folder is not None and original==full.encode('utf8')
        if origin_snapshot:descriptor['sync']=origin_snapshot['mapping']
        target,new_id=self._create_with_assets(req['markdown'],'engineering','engineering',assets,progress=progress,
            meta_extra={'report_workspace':descriptor,'render_profile':'engineering',
                        'render_options':new_options('engineering'),'color_theme':normalize_color_theme(req.get('color_theme'))})
        def rollback():
            if target.parent.resolve()!=self.server.workspace.resolve() or target.name!=new_id or is_link(target):
                raise OSError('取消清理目标不属于本次创建')
            shutil.rmtree(target)
        progress.rollback=rollback
        try:
            if origin_snapshot:atomic_write(target/ORIGIN_FILE,(json.dumps(origin_snapshot,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
            progress.check(phase='核对快照')
            if not same_source() or self._readonly_export_snapshot(transfer,validate=False,progress=progress)!=snapshot:
                raise RuntimeError('提取完成前来源或资源已变化')
        except Exception:
            rollback();progress.rollback=None
            raise
        return {'ok':True,'document_id':new_id,'report_workspace':descriptor,'assets':snapshot['files']}

    def report_output(self,folder):
        info=report_workspace_info(folder,self.server.workspace)
        if info and info['origin_document_id']!='new':
            try:return self.server.project_path(info['origin_document_id'])/'output'
            except (ValueError,OSError):pass
        return folder/'output'

    def set_render_profile(self,req):
        profile=normalize_profile(req.get('render_profile'))
        doc_id=self._docid(req);folder,raw,template,theme=self._context(doc_id,self._template(req))
        if not self._check_revision(req,raw):return
        options=normalize_options(req.get('render_options',read_options(folder)))
        color=normalize_color_theme(req.get('color_theme',read_color_theme(folder)))
        if folder is not None:self._store_meta(folder,doc_id,raw.decode('utf8'),template,theme,profile,options,color)
        self.resp({'ok':True,'render_profile':profile,'render_options':options,'color_theme':color,'revision':digest(raw)})

    def save(self,req):
        text=req.get('markdown')
        if 'render_profile' in req:normalize_profile(req['render_profile'])
        if 'render_options' in req:normalize_options(req['render_options'])
        if 'color_theme' in req:normalize_color_theme(req['color_theme'])
        if not isinstance(text,str) or len(text.encode('utf-8'))>10*1024*1024:raise ValueError('正文必须为不超过 10 MB 的字符串')
        ir=analyze_report_contract(text)
        invalid=[d for d in ir['diagnostics'] if d['severity']=='error']
        doc_id=self._docid(req);p,old,template,theme=self._context(doc_id,self._template(req))
        if invalid and not report_workspace_info(p,self.server.workspace):raise ValueError('工程文档结构错误：'+invalid[0]['message'])
        if not self._check_revision(req,old):return
        assets=self._retain_draft_assets(req,p,self._asset_preflight(req,ir['assets'],p))
        raw=text.encode('utf-8')
        if p is None:
            target=None
            if req.get('selection_token'):
                target=self.server.registry.consume_selection(req['selection_token'],'create','new')
            elif self.server.require_project_location:
                raise ValueError('首次正式保存必须选择独立工程文件夹')
            p,doc_id=self._create_with_assets(text,template,theme,assets,target)
            updated=True
        else:
            # Attach validated images first. If the report write fails, at worst
            # unused assets remain; a new formal Markdown never references missing files.
            for name,data in assets.items():
                target=p/'assets'/name
                if not target.exists():atomic_write(target,data)
            updated=raw!=old
            if updated:
                try:commit_report(p,raw,digest(old))
                except ValueError as error:
                    if str(error).startswith(('STALE_SNAPSHOT','WRITE_BUSY')):return self.fail(str(error),409)
                    raise
            if updated or not (p/'meta.json').exists():self._store_meta(p,doc_id,text,template,theme)
        if req.get('draft_id'):
            self._clear_draft(req['draft_id'])
        if 'render_profile' in req or 'render_options' in req:
            self._store_meta(p,doc_id,text,template,theme,req.get('render_profile',read_profile(p)),req.get('render_options',read_options(p)),req.get('color_theme',read_color_theme(p)))
        self.resp({'ok':True,'document_id':doc_id,'revision':digest(raw),'saved':updated,
                   'title':document_title(text),'theme':theme})
    def _native_origin_ok(self):
        # Prevent an arbitrary site from reading the local Windows clipboard
        # through the localhost service. A custom header forces CORS preflight
        # for cross-origin browser requests, which this server never allows.
        if self.headers.get('X-Report-Studio-Clipboard')!='user-action':return False
        host=self.headers.get('Host','')
        origin=self.headers.get('Origin') or self.headers.get('Referer')
        if not origin or not re.fullmatch(r'(127\.0\.0\.1|localhost):\d+',host):return False
        parts=urlsplit(origin)
        return parts.scheme=='http' and parts.netloc==host and not parts.username and not parts.password

    def _object_clipboard_context(self,req):
        if not self._native_origin_ok():raise ValueError('对象剪贴板需要当前编辑器主动操作')
        doc_id=self._docid(req);folder=self.server.project_path(doc_id)
        did=self._draft_id(req);self._verify_draft_owner(did,doc_id)
        roots=[self.server.draft_path(did)/'assets',folder/'assets' if folder else None]
        key=str(folder.resolve()).casefold() if folder else 'draft:'+did
        return folder,roots,key

    def objects_copy(self,req):
        from object_clipboard import copy_bundle
        folder,roots,key=self._object_clipboard_context(req)
        bundle=copy_bundle(req.get('markdown'),roots,key,req.get('operation'),folder)
        return self.resp({'ok':True,'bundle':bundle})

    def objects_paste(self,req):
        from object_clipboard import paste_bundle
        folder,roots,key=self._object_clipboard_context(req)
        result=paste_bundle(req.get('bundle'),req.get('target_markdown'),roots,key,check_image,
            req.get('local_files'),folder)
        target=self._graphic_dir(req)
        for name,data in result.pop('assets').items():
            path=target/name
            if not path.exists():atomic_write(path,data)
            elif path.read_bytes()!=data:raise ValueError('粘贴期间暂存附件发生冲突')
        return self.resp({'ok':True,**result})

    def _retain_draft_assets(self,req,current,assets):
        # Undo/redo may still reference an image removed before formal save.
        # Promote valid staged files as well; resource housekeeping later handles
        # genuinely unused files. Deleting an object never deletes shared bytes.
        if not req.get('draft_id'):return assets
        doc_id=self._docid(req);did=self._draft_id(req);self._verify_draft_owner(did,doc_id)
        folder=self.server.draft_path(did)/'assets'
        if folder.is_dir():
            for path in folder.iterdir():
                name=clean_asset_name(path.name)
                if is_link(path) or not path.is_file():raise ValueError('暂存附件必须是普通文件')
                data=path.read_bytes();check_image(path.suffix.lower(),data)
                existing=current/'assets'/name if current else None
                if existing and existing.exists() and existing.read_bytes()!=data:raise ValueError('暂存附件与正式附件冲突：'+name)
                assets[name]=data
        return assets

    def _graphic_dir(self,req,*,create=True,missing='新报告插图必须关联恢复草稿'):
        # Original EMF lives beside the preview PNG in the same draft/project.
        doc_id=self._docid(req)
        folder=self.server.project_path(doc_id)
        did=req.get('draft_id')
        if did:
            did=self._draft_id(req)
            self._verify_draft_owner(did,doc_id)
            target=self.server.draft_path(did)/'assets'
        else:
            if folder is None:raise ValueError(missing)
            target=folder/'assets'
        if is_link(target):raise ValueError('assets 目录不能是链接')
        if create:target.mkdir(parents=True,exist_ok=True)
        return target

    def _store_clipboard_graphic(self,req,graphic:ClipboardGraphic):
        if not isinstance(graphic,ClipboardGraphic):raise ValueError('剪贴板图片格式无效')
        png=graphic.png;check_image('.png',png)
        if graphic.emf is not None:validate_emf(graphic.emf)
        # MATLAB scientific EMF/EMF+ is NOT reliably preserved by generic
        # SVG converters (gridlines, glyphs and color bars differ). HF6 defaults
        # to PNG for browser display and preserves exact EMF source bytes.
        name=uuid.uuid4().hex[:16]
        # Preserve all source and preview assets in the draft; the formal report
        # and exported HTML only include assets referenced by its object model.
        # Conversion happens before this point; only the writes hold the lock.
        with self.server.lock:
            folder=self._graphic_dir(req)
            if graphic.emf:atomic_write(folder/(name+'.emf'),graphic.emf)
            atomic_write(folder/(name+'.png'),png)
        self.resp({'ok':True,'path':'assets/'+name+'.png',
                   'vector_source':('assets/'+name+'.emf') if graphic.emf else None,
                   'source_asset':('assets/'+name+'.emf') if graphic.emf else None,
                   'rendition':{'format':'png','dpi':300,'page':1,'engine':'win-gdi'} if graphic.emf else None,
                   'origin_format':graphic.origin,'bytes':len(png),
                   'warnings':['已保存原始 EMF；浏览器采用 300 DPI 有界 PNG 预览，不自动转换为 SVG'] if graphic.emf else []})

    def paste_native_clipboard(self,req):
        if not self._native_origin_ok():return self.fail('剪贴板接口仅接受当前编辑器的显式粘贴操作',403)
        if not native_clipboard_available():return self.fail('Windows 原生图形剪贴板仅在 Windows 便携版可用',404)
        graphic=read_windows_graphic()
        if graphic is None:return self.fail('剪贴板中没有可读取的 EMF/PNG/DIB 图形',404)
        return self._store_clipboard_graphic(req,graphic)

    def paste_native_document(self,req):
        if not self._native_origin_ok():return self.fail('剪贴板接口仅接受当前编辑器的显式粘贴操作',403)
        if set(req)-{'text'}:raise ValueError('剪贴板接口不接受文件路径或其他参数')
        if not native_clipboard_available():
            if req.get('text') is None:return self.resp({'ok':True,'available':False})
            return self.fail('读取本地 Word 图片需要 Windows 剪贴板',404)
        from clipboard_document import read_document
        # Returns a prepared resource bundle only. The original objects/paste
        # endpoint validates/stages all assets before one source transaction.
        prepared=read_document(req.get('text'),check_image)
        return self.resp({'ok':True,'available':prepared is not None,**(prepared or {})})

    def upload(self,req):
        # Validate the destination first, but only create/write it under the
        # server lock after slow decoding, EMF conversion or PDF rendering.
        self._graphic_dir(req,create=False,missing='先保存新文档，再导入图片')
        def commit(files):
            with self.server.lock:
                target_assets=self._graphic_dir(req,missing='先保存新文档，再导入图片')
                for filename,blob in files:atomic_write(target_assets/filename,blob)
        name=req.get('name','')
        if not isinstance(name,str) or not name or '/' in name or '\\' in name or '..' in name or len(name)>180:
            raise ValueError('图片文件名不合法')
        ext=Path(name).suffix.lower()
        if ext not in ALLOWED_IMAGE and ext not in {'.emf','.pdf'}:raise ValueError('只支持 PNG/JPEG/GIF/WEBP/SVG/EMF/PDF 图形')
        payload=req.get('base64')
        if not isinstance(payload,str) or len(payload)>LIMIT_IMAGE*2:raise ValueError('图片数据无效或过大')
        try:data=base64.b64decode(payload,validate=True)
        except Exception as exc:raise ValueError('Base64 无效') from exc
        if ext=='.emf':
            validate_emf(data)
            return self._store_clipboard_graphic(req,ClipboardGraphic(emf_to_png(data),'Windows EMF 文件',data))
        if ext=='.pdf':
            # Original vector PDF survives unchanged. Only the preview is
            # rasterized; this runs before writing either sidecar, so errors
            # do not create orphan PDF files or alter a formal project.
            validate_pdf(data)
            supplied=req.get('preview_base64')
            if supplied is not None:
                if not isinstance(supplied,str) or len(supplied)>LIMIT_IMAGE*2:
                    raise ValueError('PDF 关联 PNG 预览过大')
                try:png=base64.b64decode(supplied,validate=True)
                except Exception as exc:raise ValueError('PDF 关联 PNG Base64 无效') from exc
                w,h=png_dimensions(png)
                info={'format':'png','page':1,'width':w,'height':h,'engine':'provided'}
                warnings=['使用同时提供的 PNG 作为 PDF 预览；原始 PDF 未修改']
            else:
                preview=render_pdf_preview(data,dpi=300)
                png=preview.png
                info={'format':'png','dpi':preview.dpi,'page':1,'width':preview.width,'height':preview.height,'engine':preview.engine}
                warnings=['PDF 仅预览第 1 页，全部原始页面仍在 PDF 原件内'] if preview.pages>1 else []
            if len(png)>LIMIT_IMAGE:raise ValueError('PDF 预览 PNG 体积过大')
            stem=uuid.uuid4().hex[:16]
            commit([(stem+'.pdf',data),(stem+'.png',png)])
            return self.resp({'ok':True,'path':'assets/'+stem+'.png',
                   'source_asset':'assets/'+stem+'.pdf','rendition':info,
                   'bytes':len(png),'source_bytes':len(data),'warnings':warnings})
        warnings=[]
        if ext=='.svg':
            links=req.get('linked_assets',{})
            if not isinstance(links,dict) or len(links)>32:raise ValueError('SVG 附属图片清单无效')
            linked={}
            total=0
            for key,value in links.items():
                if not isinstance(value,str) or len(value)>LIMIT_IMAGE*2:raise ValueError('SVG 附属图片数据无效')
                try:raw=base64.b64decode(value,validate=True)
                except Exception as exc:raise ValueError('SVG 附属图片 Base64 无效') from exc
                total+=len(raw)
                if total>24*1024*1024:raise ValueError('SVG 附属资源超过 24 MB')
                linked[key]=raw
            data=normalize_svg(data,linked_assets=linked,warnings=warnings)
        check_image(ext,data)
        dest=uuid.uuid4().hex[:16]+ext
        commit([(dest,data)])
        self.resp({'ok':True,'path':'assets/'+dest,'bytes':len(data),'warnings':warnings})
    def import_draft(self,req):
        # Importing a prior studio HTML must not create/modify a formal document.
        did=self._draft_id(req)
        doc_id=self._docid(req)
        if doc_id!='new':raise ValueError('导入草稿只能创建独立的新文档')
        text=req.get('markdown');assets=req.get('assets',{})
        if not isinstance(text,str) or len(text.encode('utf-8'))>10*1024*1024:raise ValueError('正文过大')
        if not isinstance(assets,dict) or len(assets)>100:raise ValueError('附件清单无效')
        prepared={};total=0
        for name,payload in assets.items():
            name=clean_asset_name(name)
            if not isinstance(payload,str):raise ValueError('附件数据无效')
            try:blob=base64.b64decode(payload,validate=True)
            except Exception as exc:raise ValueError('图片 Base64 无效') from exc
            if Path(name).suffix.lower()=='.svg':
                normalized=normalize_svg(blob)
                if req.get('archive_version')=='v2' and normalized!=blob:
                    raise ValueError('v2 归档 SVG 需要安全规范化，但原件不可自动改写：'+name)
                blob=normalized
            check_image(Path(name).suffix.lower(),blob)
            total+=len(blob)
            if total>30*1024*1024:raise ValueError('附件总量过大')
            prepared[name]=blob
        folder=self.server.draft_path(did)
        if folder.exists():raise ValueError('导入草稿 ID 已存在')
        profile=normalize_profile(req.get('render_profile'))
        template=self._template(req);template_info(template)
        base=digest(template_info(template)['markdown'].encode('utf-8'))
        folder.mkdir()
        (folder/'assets').mkdir()
        try:
            for name,data in prepared.items():atomic_write(folder/'assets'/name,data)
            write_json(folder/'state.json',{'format':'html-report-studio-draft-v1','draft_id':did,
                'document_id':'new','template':template,'base_revision':base,
                'render_profile':profile,'render_options':normalize_options(req.get('render_options')),
                'color_theme':normalize_color_theme(req.get('color_theme')),
                'seq':1,'markdown':text,'updated':datetime.now(timezone.utc).isoformat()})
        except Exception:
            shutil.rmtree(folder,ignore_errors=True);raise
        self.resp({'ok':True,'draft_id':did,'seq':1,'assets_imported':len(prepared)})

    def pdf_snapshot(self,req):
        source=req.get('html')
        if not isinstance(source,str) or len(source.encode('utf-8'))>36*1024*1024:raise ValueError('HTML 太大')
        audit_export(source)
        with tempfile.TemporaryDirectory(prefix='studio_pdf_snapshot_') as tmp:
            html_file=Path(tmp)/'report.html';pdf_file=Path(tmp)/'report.pdf'
            atomic_write(html_file,source.encode('utf-8'))
            render_pdf(html_file,pdf_file)
            self.bytes(pdf_file.read_bytes(),'application/pdf',filename='报告_当前快照.pdf')

    def _legacy_output(self,doc_id,folder):
        # Older single-file endpoints follow the same output rules as /api/export/store.
        if self.server.require_project_location and doc_id not in self.server.registry.mapping:
            raise ValueError('请先把旧文档迁移到独立工程目录后再导出')
        output=folder/'output'
        if is_link(output):raise ValueError('output 目录不能指向链接')
        output.mkdir(exist_ok=True)
        return output
    def export(self,req):
        source=req.get('html')
        if not isinstance(source,str) or len(source.encode('utf-8'))>36*1024*1024:raise ValueError('HTML 太大')
        audit_export(source)
        doc_id=self._docid(req);p,old,_,_=self._context(doc_id,self._template(req))
        if p is None:raise ValueError('请先保存新文档')
        if not self._check_revision(req,old):return
        target=self._legacy_output(doc_id,p)/'报告_单文件.html'
        atomic_write(target,source.encode('utf-8'))
        self.resp({'ok':True,'document_id':doc_id,'filename':target.name,'bytes':target.stat().st_size,'path':str(target)})
    def pdf(self,req):
        doc_id=self._docid(req);p,old,_,_=self._context(doc_id,self._template(req))
        if p is None:raise ValueError('请先保存新文档')
        if not self._check_revision(req,old):return
        output=self._legacy_output(doc_id,p)
        html_file=output/'报告_单文件.html'
        if not html_file.is_file() or is_link(html_file):raise ValueError('请先导出最新 HTML，再生成 PDF')
        raw=html_file.read_text(encoding='utf-8');audit_export(raw)
        pdf_file=output/'报告_单文件.pdf'
        # Generate into a temporary destination; failed print never damages an existing PDF.
        with tempfile.TemporaryDirectory(prefix='studio_pdf_') as tmp:
            target=Path(tmp)/'report.pdf'
            render_pdf(html_file,target)
            atomic_write(pdf_file,target.read_bytes())
        self.resp({'ok':True,'document_id':doc_id,'filename':pdf_file.name,'bytes':pdf_file.stat().st_size,'path':str(pdf_file)})
    def import_report(self,req):
        text=req.get('markdown');assets=req.get('assets',{})
        if not isinstance(text,str) or len(text.encode('utf-8'))>10*1024*1024:raise ValueError('导入 Markdown 过大')
        if not isinstance(assets,dict) or len(assets)>100:raise ValueError('附件清单无效或过多')
        ir=analyze_report_contract(text)
        invalid=[d for d in ir['diagnostics'] if d['severity']=='error']
        if invalid:raise ValueError('工程文档结构错误：'+invalid[0]['message'])
        doc_id=self._docid(req);p,old,template,theme=self._context(doc_id,self._template(req))
        if p is None and self.server.require_project_location:
            raise ValueError('导入为新报告时请先在编辑器中新建并选择独立工程文件夹')
        if not self._check_revision(req,old):return
        prepared={};total=0
        for name,payload in assets.items():
            name=clean_asset_name(name)
            if not isinstance(payload,str):raise ValueError('附件数据无效')
            try:data=base64.b64decode(payload,validate=True)
            except Exception as exc:raise ValueError('附件 Base64 无效：'+name) from exc
            if Path(name).suffix.lower()=='.svg':data=normalize_svg(data)
            check_image(Path(name).suffix.lower(),data)
            total+=len(data)
            if total>30*1024*1024:raise ValueError('导入附件总量超过 30 MB')
            if p is not None:
                existing=p/'assets'/name
                if existing.is_file() and existing.read_bytes()!=data:raise ValueError('同名附件内容不同，拒绝覆盖：'+name)
            prepared[name]=data
        if p is None:
            # Staged create: report and attachments appear together or not at all.
            p,doc_id=self._create_with_assets(text,template,theme,prepared)
        else:
            for name,data in prepared.items():
                dest=p/'assets'/name
                if not dest.exists():atomic_write(dest,data)
            new=text.encode('utf-8')
            if new!=old:self._backup(p);atomic_write(p/'report.md',new)
            self._store_meta(p,doc_id,text,template,theme)
        self.resp({'ok':True,'document_id':doc_id,'revision':digest(text.encode('utf-8')),
                   'assets_imported':len(prepared),'title':document_title(text)})


def main():
    parser=argparse.ArgumentParser(description='本地 HTML/Markdown 报告编辑器（仅监听 127.0.0.1）')
    parser.add_argument('--project',type=Path,default=DEFAULT,help='兼容 v0.1 旧项目路径；在“最近打开”中访问')
    parser.add_argument('--workspace',type=Path,default=None,help='新建报告存储根目录（默认 projects/）')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    server=StudioServer(('127.0.0.1',args.port),args.project,args.workspace,require_project_location=True)
    url=f'http://127.0.0.1:{args.port}'
    print(f'HTML Report Studio {RELEASE} | 完全本地运行')
    print('新建项目目录：',server.workspace)
    print('旧版项目目录：',server.project)
    print('浏览器地址：',url)
    print('按 Ctrl+C 退出')
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:print('\n已停止')
    finally:server.server_close()


if __name__=='__main__':main()
