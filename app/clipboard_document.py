"""Explicit Word clipboard images; HRS's original object transport owns writes.

Only the live, text-matched CF_HTML snapshot supplies local image paths. The
HTTP caller cannot name a file to read. RTF pict data is used in document order
only when its logical image count agrees with that same HTML snapshot.
"""
from __future__ import annotations

import base64
import hashlib
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from clipboard_graphics import read_windows_formats, emf_to_png, dib_to_png, MAX_SOURCE
from clipboard_math import ListLabel, native_formulas, normalize_text

MAX_TOTAL = 30 * 1024 * 1024


def html_fragment(data):
    header=data[:4096]
    offsets={key.decode():int(value) for key,value in re.findall(rb'(StartFragment|EndFragment):\s*(\d+)',header)}
    start,end=offsets.get('StartFragment',-1),offsets.get('EndFragment',-1)
    if not 0<=start<end<=len(data) or end-start>2_000_000:
        raise ValueError('Windows HTML 剪贴板范围无效或超过 2 MB')
    try:return data[start:end].decode('utf8')
    except UnicodeDecodeError as error:raise ValueError('Windows HTML 剪贴板不是有效 UTF-8') from error


LIST_IGNORE = re.compile(r'(?:^|;)\s*mso-list\s*:\s*ignore\s*(?:!important\s*)?(?=;|$)', re.I)
NON_CONTENT = {'head', 'script', 'style'}
PARAGRAPH_TAGS = {'p', 'li', 'div', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br'}


class DocumentFragment(HTMLParser):
    """Collect image positions and Office's explicit generated-label spans."""

    def __init__(self, html, *, collect_text=False):
        super().__init__(convert_charrefs=True)
        self.collect_text = collect_text
        self.sources = []
        self.parts = []
        self.image_in_list = []
        self.span_depth = 0
        self.label_depth = 0
        self.label_parts = []
        self.label_start = -1
        self.label_spans = []
        self.ignored_tag = None
        self.list_item_start = False
        self.line_starts = [0, *(match.end() for match in re.finditer('\n', html))] if collect_text else None
        self.feed(html)
        self.close()

    def source_offset(self):
        line, column = self.getpos()
        return self.line_starts[line-1] + column

    def handle_starttag(self, tag, attrs):
        if self.ignored_tag is not None:
            return
        if tag in NON_CONTENT:
            self.ignored_tag = tag
            return
        if tag in PARAGRAPH_TAGS:
            self.list_item_start = False
        attrs = dict(attrs)
        if tag == 'img':
            self.sources.append(attrs.get('src', ''))
            if self.collect_text:
                self.image_in_list.append(self.list_item_start)
                self.parts.append(None)
        elif tag == 'span' and self.collect_text:
            self.span_depth += 1
            if not self.label_depth and LIST_IGNORE.search(attrs.get('style') or ''):
                self.label_depth = self.span_depth
                self.label_start = self.source_offset() + len(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.ignored_tag is not None:
            if self.ignored_tag == tag:
                self.ignored_tag = None
            return
        if tag in PARAGRAPH_TAGS:
            self.list_item_start = False
        if tag != 'span' or not self.span_depth:
            return
        if self.label_depth == self.span_depth:
            label = normalize_text(''.join(self.label_parts))
            if label:
                part = ListLabel(label)
                self.parts.append(part)
                self.label_spans.append((self.label_start, self.source_offset(), part))
                self.list_item_start = True
            self.label_parts.clear()
            self.label_depth = 0
        self.span_depth -= 1

    def handle_data(self, data):
        if not self.collect_text or self.ignored_tag is not None:
            return
        if self.label_depth:
            self.label_parts.append(data)
        elif data := normalize_text(data):
            self.parts.append(data)

    def with_display_labels(self, html):
        """Keep the plain clipboard's source ordinals when Office HTML renumbers."""
        parts = []
        cursor = 0
        for start, end, label in self.label_spans:
            if label.display is not None and label.display != label.text:
                parts.extend((html[cursor:start], escape(label.display) + '&nbsp;'))
                cursor = end
        parts.append(html[cursor:])
        return ''.join(parts)


_RTF_TOKEN=re.compile(rb'\\([a-zA-Z]+)(-?\d+)? ?|\\(.)|[{}]|[^{}\\]+',re.S)
_RTF_DEST=re.compile(rb'(?:\\\*\s*)?\\([a-zA-Z]+)')


def rtf_pictures(data):
    """Read pict payloads, ignoring fallback copies and nested blipuid metadata.

    This is an image extractor, not an RTF text/layout interpreter. Binary pict
    bytes are skipped by their declared length, so braces in images are data.
    """
    if not data.startswith(b'{\\rtf') or len(data)>64*1024*1024:
        raise ValueError('RTF 剪贴板无效或超过限制')
    stack=[];pictures=[];i=0;total=0
    while i<len(data):
        token=_RTF_TOKEN.match(data,i)
        if not token:raise ValueError('RTF 剪贴板结构无效')
        raw=token.group();i=token.end()
        if raw==b'{':
            if len(stack)>=128:raise ValueError('RTF 嵌套超过限制')
            match=_RTF_DEST.match(data,i);dest=match[1] if match else b''
            skip=(stack[-1]['skip'] if stack else False) or dest==b'nonshppict'
            stack.append({'skip':skip,'pict':dest==b'pict','kind':None,'hex':[],'binary':[]})
        elif raw==b'}':
            if not stack:
                if data[i:].strip(b'\x00 \r\n\t'):raise ValueError('RTF 剪贴板括号不匹配')
                break
            frame=stack.pop()
            if frame['pict'] and not frame['skip']:
                try:payload=bytes.fromhex(b''.join(frame['hex']).decode('ascii'))+b''.join(frame['binary'])
                except ValueError as error:raise ValueError('RTF 图片编码无效') from error
                total+=len(payload)
                if not payload or len(payload)>MAX_SOURCE or total>MAX_TOTAL or len(pictures)>=100:
                    raise ValueError('RTF 图片为空或超过大小/数量限制')
                pictures.append((frame['kind'],payload))
        elif token[1]:
            word=token[1];frame=stack[-1] if stack else None
            if word==b'bin':
                count=int(token[2] or b'-1')
                if count<0 or count>MAX_SOURCE or i+count>len(data):raise ValueError('RTF 二进制图片范围无效')
                if frame and frame['pict'] and not frame['skip']:frame['binary'].append(data[i:i+count])
                i+=count
            elif frame and frame['pict'] and word in (b'pngblip',b'jpegblip',b'emfblip',b'dibitmap',b'wmetafile'):
                frame['kind']=word.decode()
        elif stack and stack[-1]['pict'] and not stack[-1]['skip'] and not token[2]:
            if not re.fullmatch(rb'[a-fA-F0-9\s]*',raw):raise ValueError('RTF 图片含非十六进制数据')
            stack[-1]['hex'].append(raw)
    if stack:raise ValueError('RTF 剪贴板没有闭合')
    return pictures


def _file_image(url):
    parsed=urlsplit(url)
    if parsed.scheme.lower()!='file' or parsed.netloc not in ('','localhost'):
        return None
    path=unquote(parsed.path).replace('\\','/')
    if path.startswith('//'):return None
    if re.match(r'^/[A-Za-z]:/',path):path=path[1:]
    candidate=Path(path)
    if not candidate.is_absolute() or candidate.is_symlink() or not candidate.is_file():return None
    if candidate.suffix.lower() not in ('.png','.jpg','.jpeg','.gif','.webp','.svg','.emf'):return None
    if candidate.stat().st_size>MAX_SOURCE:raise ValueError('剪贴板图片超过 12 MiB')
    return candidate.suffix.lower(),candidate.read_bytes()


def _image_record(ext,data,check_image):
    original=None
    if ext=='.emf':original=data;data=emf_to_png(data);ext='.png'
    check_image(ext,data)
    sha=hashlib.sha256(data).hexdigest();stem=sha[:16];name=stem+ext
    def item(blob):return {'base64':base64.b64encode(blob).decode('ascii'),'sha256':hashlib.sha256(blob).hexdigest()}
    record={'path':'assets/'+name,'assets':{name:item(data)}}
    if original:
        record['assets'][stem+'.emf']=item(original)
        record.update(sourceAsset='assets/'+stem+'.emf',vectorSource='assets/'+stem+'.emf',
                      rendition={'format':'png','dpi':300,'page':1,'engine':'win-gdi'})
    return record


def prepare_document(snapshot,expected_text,check_image,convert_math=None):
    """Pure preparation: verifies one native snapshot and returns transport data."""
    if not isinstance(expected_text,str) or len(expected_text)>2_000_000:raise ValueError('粘贴文字无效或过长')
    native=snapshot.get(13)
    if native is None or 'HTML Format' not in snapshot:raise ValueError('剪贴板没有完整的 Word HTML 和文字，请重新复制')
    try:text=native.decode('utf-16le').rstrip('\0')
    except UnicodeDecodeError as error:raise ValueError('Windows 剪贴板文字无效') from error
    normalize=lambda value:re.sub(r'\r\n?','\n',value)
    if normalize(text)!=normalize(expected_text):raise ValueError('剪贴板在粘贴期间已变化，整段未插入；请重新复制')
    html = html_fragment(snapshot['HTML Format'])
    native_math = snapshot.get('Kingsoft WPS 9.0 Format')
    fragment = DocumentFragment(html, collect_text=bool(native_math and 'mso-list' in html.lower()))
    sources = fragment.sources
    if len(sources)>100:raise ValueError('Windows 剪贴板图片数量超限')
    if not sources:return {'html':html,'images':{}}
    math_images = native_formulas(native_math, sources, expected_text, convert_math,
                                  list_parts=fragment.parts if fragment.label_spans else (),
                                  list_images=fragment.image_in_list if fragment.label_spans else ())
    if math_images and fragment.label_spans:
        html = fragment.with_display_labels(html)
    pictures=None
    if snapshot.get('Rich Text Format'):
        try:
            candidates=rtf_pictures(snapshot['Rich Text Format'])
            if len(candidates)==len(sources) and all(kind in ('pngblip','jpegblip','emfblip','dibitmap') for kind,_ in candidates):pictures=candidates
        except ValueError:
            # A valid HTML-declared local image remains usable without RTF.
            # Missing files still fail below; a broken RTF never drops an image.
            pass
    prepared={};assets={};total=0
    def retain(url,record):
        nonlocal total
        if url in prepared and prepared[url]!=record:raise ValueError('Word 同名图片内容冲突，整段未插入')
        for name,asset in record['assets'].items():
            if name in assets:
                if assets[name]!=asset:raise ValueError('Word 图片附件名称冲突，整段未插入')
                continue
            encoded=asset['base64'];padding=len(encoded)-len(encoded.rstrip('='))
            total+=len(encoded)//4*3-padding
            if total>MAX_TOTAL:raise ValueError('剪贴板图片总量超过 30 MiB')
            assets[name]=asset
        prepared[url]=record
    for index,url in enumerate(sources):
        if url in math_images:continue
        if urlsplit(url).scheme.lower() in ('http','https'):raise ValueError('不自动下载剪贴板中的外部图片，整段未插入')
        if pictures:
            kind,blob=pictures[index]
            if kind=='dibitmap':blob=dib_to_png(blob);kind='pngblip'
            record=_image_record({'pngblip':'.png','jpegblip':'.jpg','emfblip':'.emf'}[kind],blob,check_image)
            retain(url,record);continue
        if url in prepared:continue
        match=re.fullmatch(r'data:(image/(?:png|jpeg|gif|webp|svg\+xml));base64,([\s\S]+)',url,re.I)
        if match:
            ext={'png':'.png','jpeg':'.jpg','gif':'.gif','webp':'.webp','svg+xml':'.svg'}[match[1].split('/')[1].lower()]
            try:blob=base64.b64decode(re.sub(r'\s','',match[2]),validate=True)
            except ValueError as error:raise ValueError('剪贴板图片编码无效') from error
            if len(blob)>MAX_SOURCE:raise ValueError('剪贴板图片超过 12 MiB')
            retain(url,_image_record(ext,blob,check_image));continue
        local=_file_image(url)
        if not local:raise ValueError('Word 图片与 HTML 无法一一对应，整段未插入；请将图片分别复制后插入')
        retain(url,_image_record(*local,check_image))
    return {'html':html,'images':prepared,'math_images':math_images}


def read_document(expected_text,check_image,convert_math=None):
    snapshot=read_windows_formats([13,'HTML Format','Rich Text Format','Kingsoft WPS 9.0 Format'])
    # Chromium sometimes exposes only Office's whole-selection bitmap. This
    # explicit probe still uses one atomic native snapshot, never caller paths.
    if expected_text is None:
        if 13 not in snapshot or 'HTML Format' not in snapshot:return None
        expected_text=snapshot[13].decode('utf-16le').rstrip('\0')
    return {'text':expected_text,**prepare_document(snapshot,expected_text,check_image,convert_math)}
