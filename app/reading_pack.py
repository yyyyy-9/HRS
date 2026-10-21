"""Read-only multi-Markdown bundle viewer, with strictly relative local resources.

One trusted ZIP uploaded via the app, or a directory explicitly selected through
Windows shell dialog. Never extracts ZIP files, never touches current report.md,
assets, or project registry. No file://, network or absolute path support.
"""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import posixpath
import re
import secrets
import stat
import threading
import time
import zipfile

from project_workspace import is_link

MAX_ZIP_BYTES = 24 * 1024 * 1024
MAX_TOTAL_BYTES = 120 * 1024 * 1024
MAX_MEMBERS = 350
MAX_MARKDOWN = 4 * 1024 * 1024
MAX_IMAGE = 14 * 1024 * 1024
MAX_PDF = 24 * 1024 * 1024
MAX_FOLDER_FILES = 750
MIME = {'.md': 'text/markdown; charset=utf-8', '.markdown': 'text/markdown; charset=utf-8',
        '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
        '.pdf': 'application/pdf', '.json': 'application/json; charset=utf-8',
        '.csv': 'text/csv; charset=utf-8', '.txt': 'text/plain; charset=utf-8'}


def member_name(value: str) -> str:
    """Validate a ZIP member name independent of OS path interpretation."""
    if not isinstance(value, str) or not value or len(value) > 500 or '\x00' in value or '\\' in value:
        raise ValueError('阅读包文件名不合法')
    if value.startswith('/') or re.match(r'^[a-zA-Z]:', value) or '//' in value:
        raise ValueError('阅读包包含绝对路径或异常路径')
    bits = value.split('/')
    if any(x in ('', '.', '..') for x in bits):
        raise ValueError('阅读包文件路径包含 . 或 ..')
    if any(':' in part or '\x00' in part for part in bits):
        raise ValueError('阅读包文件路径包含不允许的字符')
    return '/'.join(bits)


def normalized_reference(base: str, reference: str) -> str:
    """Resolve a Markdown relative file path against its owning Markdown file."""
    if not isinstance(reference, str) or not reference or len(reference) > 600:
        raise ValueError('引用路径为空或过长')
    # The HTTP query is decoded by parse_qs once. Never unquote it again.
    if reference.startswith(('/', '\\', '//')) or '\\' in reference or '\x00' in reference:
        raise ValueError('不支持绝对路径或反斜杠引用')
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', reference):
        raise ValueError('不支持文件系统或网络协议引用')
    if '?' in reference or '#' in reference:
        raise ValueError('仅支持文档与资源文件路径，锚点请单独传递')
    if re.search(r'%[0-9a-fA-F]{2}', reference):
        raise ValueError('请使用解码后的路径，禁止双重 URL 编码')
    if not isinstance(base, str) or ('/' in base and base.startswith('/')):
        raise ValueError('基础路径无效')
    if base:
        member_name(base)
    output = [] if not base else base.split('/')[:-1]
    for part in reference.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            if not output:
                raise ValueError('引用超出阅读包目录')
            output.pop()
        elif ':' in part or part in ('.', '..'):
            raise ValueError('引用路径不安全')
        else:
            output.append(part)
    if not output:
        raise ValueError('引用路径不能为空')
    return member_name('/'.join(output))


class ReadBundle:
    def __init__(self, *, source: str, archive: bytes | None = None, root: Path | None = None):
        self.source = source
        self.archive = archive
        self.root = root
        self.files: dict[str, str] = {} # normalized display path -> underlying archive member
        self._folded_names: set[str] = set()
        self.total_bytes = 0
        if archive is not None:
            if len(archive) > MAX_ZIP_BYTES:
                raise ValueError('阅读包 ZIP 不得超过 24 MiB')
            with zipfile.ZipFile(io.BytesIO(archive)) as z:
                infos = [i for i in z.infolist() if not i.is_dir()]
                if len(infos) > MAX_MEMBERS:
                    raise ValueError('阅读包文件数量超过 350')
                names = []
                for item in infos:
                    name = member_name(item.filename)
                    if item.create_system == 3 and stat.S_ISLNK(item.external_attr >> 16):
                        raise ValueError('阅读包不得包含符号链接')
                    if item.flag_bits & 1:
                        raise ValueError('阅读包不得包含加密附件')
                    if item.file_size > MAX_PDF and Path(name).suffix.lower() != '.pdf':
                        raise ValueError('阅读包单个附件超过大小限制')
                    self.total_bytes += item.file_size
                    if self.total_bytes > MAX_TOTAL_BYTES:
                        raise ValueError('阅读包解压总量超过 120 MiB')
                    names.append((name, item.filename))
                prefixes = {x[0].split('/', 1)[0] for x in names}
                strip = (next(iter(prefixes)) + '/') if len(prefixes) == 1 and all('/' in x[0] for x in names) else ''
                for name, original in names:
                    short = member_name(name[len(strip):] if strip else name)
                    self._register(short, original)
        else:
            if root is None or not root.is_dir() or is_link(root):
                raise ValueError('所选阅读包目录无效')
            self.root = root.resolve(strict=True)
            files_seen = 0
            folders_seen = 0
            for folder, dirs, names in os.walk(self.root, followlinks=False):
                folders_seen += 1
                if folders_seen > 1000:
                    raise ValueError('阅读包子文件夹过多，建议选择更具体的目录')
                base = Path(folder)
                if len(base.relative_to(self.root).parts) > 16:
                    raise ValueError('阅读包目录层级超过 16 级')
                for d in dirs:
                    if is_link(base / d):
                        raise ValueError('阅读包包含链接目录')
                for name in names:
                    child = base / name
                    if is_link(child) or not child.is_file():
                        raise ValueError('阅读包包含不安全文件')
                    files_seen += 1
                    if files_seen > MAX_FOLDER_FILES:
                        raise ValueError('阅读包文件超过 750 个，建议拆分目录')
                    rel = member_name(child.relative_to(self.root).as_posix())
                    self._register(rel, rel)
                    self.total_bytes += child.stat().st_size
            # Local folder mode has bounded file count; payloads are bounded per request.
        self.documents = sorted((path for path in self.files if Path(path).suffix.lower() in ('.md', '.markdown')),
                                key=lambda p:(len(p.split('/')), p.casefold()))
        if not self.documents:
            raise ValueError('阅读包中没有 Markdown 文件')
        self.main = next((doc for doc in self.documents if doc.casefold() == 'report.md'), None)
        if self.main is None:
            self.main = next((doc for doc in self.documents if doc.casefold() == 'readme.md'), None)
        if self.main is None:
            self.main = self.documents[0]

    def _register(self, relative: str, original: str):
        if relative.casefold() in self._folded_names:
            raise ValueError('阅读包存在大小写不同但同名的附件')
        self.files[relative] = original
        self._folded_names.add(relative.casefold())

    def document(self, path: str | None = None) -> dict:
        path = path or self.main
        if path not in self.files or Path(path).suffix.lower() not in ('.md', '.markdown'):
            raise ValueError('Markdown 文档不存在')
        raw = self.read(path)
        if len(raw) > MAX_MARKDOWN:
            raise ValueError('Markdown 文档超过 4 MiB')
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeError as exc:
            raise ValueError('Markdown 文件必须为 UTF-8') from exc
        from render_profile import normalize,normalize_options
        profile='free';options=normalize_options()
        meta=posixpath.join(posixpath.dirname(path),'meta.json')
        if posixpath.basename(path)=='report.md' and meta in self.files:
            data=json.loads(self.read(meta).decode('utf-8-sig'))
            profile=normalize(data.get('render_profile'));options=normalize_options(data.get('render_options'))
        return {'path': path, 'markdown': text,'render_profile':profile,'render_options':options}

    def read(self, path: str) -> bytes:
        if path not in self.files:
            raise ValueError('阅读包中找不到文件：'+path[:150])
        suffix = Path(path).suffix.lower()
        if suffix not in MIME:
            raise ValueError('此文件类型不允许通过阅读器访问')
        limit = MAX_PDF if suffix == '.pdf' else MAX_IMAGE if suffix in ('.png','.jpg','.jpeg','.gif','.webp','.svg') else MAX_MARKDOWN
        if self.archive is not None:
            with zipfile.ZipFile(io.BytesIO(self.archive)) as z:
                info = z.getinfo(self.files[path])
                if info.file_size > limit:
                    raise ValueError('阅读包附件超过大小限制')
                # Avoid unbounded output even from an invalid compressed stream.
                with z.open(info) as stream:
                    payload = stream.read(limit + 1)
        else:
            candidate = self.root / self.files[path]
            # Disallow every symlink/reparse point across the supplied relative path.
            current = self.root
            for segment in path.split('/'):
                current = current / segment
                if is_link(current):
                    raise ValueError('阅读包内不能读取链接文件')
            if not candidate.resolve(strict=True).is_relative_to(self.root):
                raise ValueError('阅读包资源路径超出了根目录')
            if candidate.stat().st_size > limit:
                raise ValueError('阅读包附件超过大小限制')
            payload = candidate.read_bytes()
        if len(payload) > limit:
            raise ValueError('阅读包附件超过大小限制')
        return payload


class ReadPackManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._sessions: dict[str, tuple[float, ReadBundle]] = {}

    def register(self, bundle: ReadBundle) -> dict:
        with self._lock:
            now = time.monotonic()
            self._sessions = {key:(t,session) for key,(t,session) in self._sessions.items() if now - t < 6 * 3600}
            while len(self._sessions) >= 4:
                oldest=min(self._sessions, key=lambda key:self._sessions[key][0])
                self._sessions.pop(oldest)
            identifier = secrets.token_hex(16)
            self._sessions[identifier] = (now, bundle)
        return {'ok':True, 'reader_id':identifier, 'main':bundle.main, 'documents':bundle.documents,
                'file_count':len(bundle.files), 'source':bundle.source}

    def get(self, identifier: str) -> ReadBundle:
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}',identifier):
            raise ValueError('阅读器会话 ID 无效')
        with self._lock:
            entry = self._sessions.get(identifier)
            if entry is None:
                raise ValueError('阅读包未打开或会话已结束')
            return entry[1]

    def close(self, identifier: str):
        if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9]{32}',identifier):
            raise ValueError('阅读器会话 ID 无效')
        with self._lock:
            self._sessions.pop(identifier, None)
