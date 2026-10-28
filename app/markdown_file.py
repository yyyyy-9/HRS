"""Storage adapter for explicitly selected, attachment-free Markdown files.

The selected file is the only source. Preferences, locks and backups live in
application data; HTTP callers use registered IDs, never arbitrary paths.
"""
from pathlib import Path
import json,re,uuid
from project_workspace import SAFE_ID,is_link
from report_contract import analyze
from object_clipboard import local_urls
from project_commit import report_lock,commit_report_locked

MAX_MARKDOWN_BYTES=10*1024*1024


def needs_project(text):
    if not isinstance(text,str) or len(text.encode('utf8'))>MAX_MARKDOWN_BYTES:
        raise ValueError('Markdown 必须为不超过 10 MiB 的 UTF-8 文本')
    ir=analyze(text)
    return bool(ir['assets'] or local_urls(ir))


def require_text_only(text):
    if needs_project(text):
        raise ValueError('文稿包含图片等附件，请使用“导入 Markdown”或先另存为 HRS 工程')


def encode_saved_text(text,original):
    """One file-save policy, shared by browser/API callers through save()."""
    match=re.search(rb'\r\n|\r|\n',original)
    newline=match[0].decode('ascii') if match else '\n'
    # Bulk string replacements avoid a Python callback/allocation per line
    # when saving a large document with many line boundaries.
    canonical=text.replace('\r\n','\n').replace('\r','\n')
    if newline!='\n':canonical=canonical.replace('\n',newline)
    if canonical and original.endswith((b'\r',b'\n')) and not canonical.endswith(('\r','\n')):
        canonical+=newline
    raw=(b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b'')+canonical.encode('utf8')
    if len(raw)>MAX_MARKDOWN_BYTES:raise ValueError('按原换行格式保存后 Markdown 超过 10 MiB；原文件未修改')
    return raw


def _source(path):
    path=Path(path)
    if not path.is_absolute() or path.suffix.lower() not in ('.md','.markdown'):
        raise ValueError('请选择 Markdown 文件（.md / .markdown）')
    if any(is_link(p) for p in (path,*path.parents)) or not path.is_file():
        raise ValueError('Markdown 文件不存在、已移动或包含链接路径')
    if path.stat().st_size>MAX_MARKDOWN_BYTES:raise ValueError('Markdown 超过 10 MiB')
    return path.resolve(strict=True)


class MarkdownFiles:
    def __init__(self,workspace):
        self.root=Path(workspace)/'.markdown-files'
        self.index=self.root/'index.json';self.mapping={}
        if is_link(self.root) or is_link(self.index):raise ValueError('Markdown 位置索引不能是链接')
        if self.index.exists():
            data=json.loads(self.index.read_text('utf8'))
            if data.get('version')!=1 or not isinstance(data.get('files'),dict):raise ValueError('Markdown 位置索引无效')
            for identity,path in data['files'].items():
                if not SAFE_ID.fullmatch(identity) or not isinstance(path,str) or not Path(path).is_absolute():
                    raise ValueError('Markdown 位置索引含无效绑定')
            self.mapping=data['files']

    def source(self,identity):
        return _source(self.mapping[identity])

    def folder(self,identity):
        if identity not in self.mapping:raise ValueError('Markdown 文件尚未授权')
        folder=self.root/identity
        if is_link(self.root) or is_link(folder):raise ValueError('Markdown 设置目录不能是链接')
        return folder

    def register(self,path):
        from studio import write_json
        from render_profile import new_options
        path=_source(path)
        try:text=path.read_bytes().decode('utf-8-sig')
        except UnicodeDecodeError as exc:raise ValueError('Markdown 不是 UTF-8 编码，请先另存为 UTF-8') from exc
        require_text_only(text)
        for identity,old in self.mapping.items():
            if Path(old)==path:return identity
        identity=uuid.uuid4().hex
        self.root.mkdir(parents=True,exist_ok=True)
        folder=self.root/identity;folder.mkdir()
        write_json(folder/'meta.json',{'template':'blank','theme':'brief','render_profile':'free',
            'render_options':new_options('free')})
        updated={**self.mapping,identity:str(path)}
        write_json(self.index,{'version':1,'files':updated})
        self.mapping=updated
        return identity

    def save(self,identity,text,expected):
        require_text_only(text)
        folder=self.folder(identity)
        with report_lock(folder):
            source=self.source(identity)
            original=source.read_bytes()
            # Native Enter supplies LF. Serialize all line boundaries using
            # the selected file's convention, including its terminal newline.
            raw=encode_saved_text(text,original)
            commit_report_locked(folder,raw,expected,source=source)
        return raw
