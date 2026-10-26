"""Explicitly authorized user-owned project folders and safe legacy migration.

No arbitrary user-supplied path may be sent to the local HTTP service: each
filesystem destination comes only from a platform folder chooser and is bound
to a short-lived server-side token. Browser JS may request a selection, but
cannot manufacture or overwrite an arbitrary absolute path.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import time

REGISTRY_VERSION=1
SAFE_ID=re.compile(r'^[a-f0-9]{32}$')
BAD_NAME=re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED={f'{prefix}{n}' for prefix in ('COM','LPT') for n in range(1,10)} | {'CON','PRN','AUX','NUL'}


def is_link(path)->bool:
    """Symlink or Windows directory junction; Path.is_symlink() misses junctions."""
    p=Path(path)
    try:return p.is_symlink() or bool(getattr(p,'is_junction',lambda:False)())
    except OSError:return False


def validate_project_name(value:str)->str:
    if not isinstance(value,str):raise ValueError('项目名称必须是文字')
    text=value.strip()
    if not(1<=len(text)<=70) or text in ('.','..') or text[-1] in '. ' or BAD_NAME.search(text):
        raise ValueError('项目名称包含无效字符或长度超限')
    if text.split('.')[0].upper() in RESERVED:raise ValueError('项目名称是 Windows 保留名称')
    return text


def pick_import_file(*,word_template:bool=False,word_formula:bool=False,word_document:bool=False)->Path|None:
    from native_picker import choose
    if word_document:
        return choose(purpose='word-import',title='导入 Word（.docx，原文件不变）',filters=[('Word 文档','*.docx')])
    purpose='word-formula' if word_formula else 'word-template' if word_template else 'document-import'
    title='选择已有的 pandoc.exe（原生公式转换需要）' if word_formula else '选择已准备好的 Word 母模板（.docx）' if word_template else '导入 Markdown / HTML（相对图片自动读取，原文件不变）'
    filters=[('Pandoc 公式转换器','pandoc.exe')] if word_formula else [('Word 模板文档','*.docx')] if word_template else [('Markdown / 可回编 HTML','*.md;*.markdown;*.html;*.htm'),('Markdown','*.md;*.markdown'),('HTML','*.html;*.htm')]
    return choose(purpose=purpose,title=title,filters=filters)


def pick_project_parent(*,open_existing:bool=False,reading_pack:bool=False,title:str|None=None)->Path|None:
    from native_picker import choose
    purpose='word-runtime' if title else 'reading-pack' if reading_pack else 'project-open' if open_existing else 'project-parent'
    caption=title or ('请选择 Markdown 阅读包所在的文件夹（仅读取，不会改写）' if reading_pack else '请选择已有工程文件夹（包含 report.md 和 assets）' if open_existing else '请选择工程项目的父目录（程序将在其中新建项目文件夹）')
    return choose(purpose=purpose,title=caption,folder=True)


def _sha_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def _trusted_project_directory(root:Path)->Path:
    if not root.is_dir() or is_link(root):raise ValueError('项目根目录不是普通文件夹')
    if not (root/'report.md').is_file() or is_link(root/'report.md'):raise ValueError('目录不包含独立的 report.md')
    if not (root/'assets').is_dir() or is_link(root/'assets'):raise ValueError('工程缺少独立的 assets 目录')
    # Prevent mapped destinations from following symlinks/reparse points in
    # common asset directories or replacing another user's workspace.
    return root.resolve(strict=True)


def copy_project_tree(source:Path,target:Path)->int:
    """Create target atomically, verify every copied byte, leave source alone."""
    source=_trusted_project_directory(source)
    parent=target.parent.resolve(strict=True)
    if target.exists() or is_link(target):raise ValueError('目标项目文件夹已存在，拒绝覆盖')
    if parent==source or source in parent.parents:
        raise ValueError('项目不允许拷贝到自己的子目录或父目录')
    files=[];directories=[]
    for folder,dirs,names in os.walk(source,followlinks=False):
        at=Path(folder)
        directories.append(at.relative_to(source))
        for d in dirs:
            if is_link(at/d):raise ValueError('原项目包含链接目录，迁移中止')
        for n in names:
            file=at/n
            if is_link(file) or not file.is_file():raise ValueError('原项目包含不安全的链接或特殊文件')
            files.append((file,file.relative_to(source),_sha_file(file)))
    if len(files)>5000:raise ValueError('项目文件过多，请人工检查后迁移')
    stage=parent/('.hrs_copy_'+secrets.token_hex(12))
    stage.mkdir(exist_ok=False)
    try:
        # Text-only projects still own empty assets/output directories. Keep
        # directory structure as well as files in copies and migrations.
        for relative in directories:(stage/relative).mkdir(parents=True,exist_ok=True)
        for file,relative,expected in files:
            dest=stage/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(file,dest,follow_symlinks=False)
            if _sha_file(dest)!=expected or _sha_file(file)!=expected:
                raise RuntimeError('项目复制后校验失败，原项目保持不变：'+str(relative))
        # Avoid clobbering a folder created while the copy was in progress.
        if target.exists() or is_link(target):
            raise ValueError('目标目录在迁移期间被其他程序创建，拒绝覆盖')
        os.replace(stage,target)
    except Exception:
        shutil.rmtree(stage,ignore_errors=True)
        raise
    return len(files)


class ProjectRegistry:
    def __init__(self,workspace:Path):
        self.workspace=Path(workspace).resolve()
        self.path=self.workspace/'.registered-projects.json'
        self.selected={}
        self.mapping=self._load()

    def _load(self)->dict:
        if not self.path.exists():return {}
        try:obj=json.loads(self.path.read_text(encoding='utf-8'))
        except (ValueError,OSError) as exc:raise RuntimeError('项目位置索引损坏，请先备份：'+str(self.path)) from exc
        if obj.get('version')!=REGISTRY_VERSION or not isinstance(obj.get('projects'),dict):
            raise RuntimeError('项目索引版本不兼容')
        result={}
        for key,value in obj['projects'].items():
            if not SAFE_ID.fullmatch(key) or not isinstance(value,str) or not Path(value).is_absolute():
                raise RuntimeError('项目索引中包含无效路径')
            result[key]=value
        return result

    def lookup(self,doc_id:str)->Path|None:
        path=self.mapping.get(doc_id)
        if path is None:return None
        return _trusted_project_directory(Path(path))

    def register(self,doc_id:str,root:Path):
        if not SAFE_ID.fullmatch(doc_id):raise ValueError('项目 ID 无效')
        validated=_trusted_project_directory(root)
        for old_id,old_path in self.mapping.items():
            if old_id!=doc_id and Path(old_path)==validated:
                raise ValueError('目标目录已经被其他项目绑定')
        before=self.mapping.copy()
        self.mapping[doc_id]=str(validated)
        try:
            self._atomic_json({'version':REGISTRY_VERSION,'projects':self.mapping})
        except Exception:
            self.mapping=before;raise

    def _atomic_json(self,data):
        encoded=(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
        fd,name=tempfile.mkstemp(prefix='.project_registry_',dir=self.workspace)
        try:
            with os.fdopen(fd,'wb') as f:f.write(encoded);f.flush();os.fsync(f.fileno())
            os.replace(name,self.path)
        finally:
            if os.path.exists(name):os.unlink(name)

    def new_selection(self,action:str,doc_id:str,parent:Path,name:str)->dict:
        name=validate_project_name(name)
        if action not in ('create','migrate'):raise ValueError('项目操作无效')
        if doc_id!='new' and not SAFE_ID.fullmatch(doc_id) and doc_id!='legacy':raise ValueError('文档 ID 无效')
        if action=='create' and doc_id!='new':raise ValueError('创建操作只能用于新报告')
        if action=='migrate' and doc_id=='new':raise ValueError('未创建项目不能迁移')
        parent=Path(parent).resolve(strict=True)
        if not parent.is_dir() or is_link(parent):raise ValueError('必须选择真实的项目父目录')
        forbidden=self.workspace.parent.resolve()
        if parent==forbidden or forbidden in parent.parents or parent==self.workspace or self.workspace in parent.parents:
            raise ValueError('请选择便携软件 data/ 之外的工程目录')
        target=parent/name
        if target.exists() or is_link(target):raise ValueError('目标目录已经存在，请选择新的项目名称')
        token=secrets.token_urlsafe(24)
        self.selected[token]={'action':action,'document_id':doc_id,'target':str(target),'expires':time.monotonic()+300}
        return {'selection_token':token,'selected_parent':str(parent),'target_path':str(target),'project_name':name}

    def consume_selection(self,token:str,action:str,doc_id:str)->Path:
        if not isinstance(token,str):raise ValueError('缺少目录授权')
        item=self.selected.pop(token,None)
        if not item or item['action']!=action or item['document_id']!=doc_id or time.monotonic()>item['expires']:
            raise ValueError('项目目录授权已失效，请重新选择文件夹')
        path=Path(item['target'])
        if path.exists() or is_link(path):raise ValueError('目标项目目录被其他程序占用，拒绝覆盖')
        return path
