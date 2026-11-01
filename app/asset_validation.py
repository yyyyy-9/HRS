"""Image byte validation and safe SVG normalization; no service dependency."""
import base64
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

from asset_paths import normalize_asset
from clipboard_graphics import validate_emf
from pdf_graphics import validate_pdf
from svg_prolog import safe_svg_prolog

LIMIT_IMAGE = 12 * 1024 * 1024
ALLOWED_IMAGE = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.gif':'image/gif', '.webp':'image/webp', '.svg':'image/svg+xml'}
ALLOWED_ASSET = {**ALLOWED_IMAGE,'.emf':'application/octet-stream','.pdf':'application/pdf'}

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
    if not isinstance(name,str) or normalize_asset('assets/'+name,originals=True)!='assets/'+name:
        raise ValueError('附件名不合法')
    if Path(name).suffix.lower() not in ALLOWED_ASSET:raise ValueError('附件格式不受支持')
    return name
