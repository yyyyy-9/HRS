"""Explicit project asset cleanup — never called by save or export.

This module has no UI and no access to arbitrary paths.  The HTTP layer must
resolve a registered project, check its report revision and require a genuine
same-origin user action before calling any mutating method.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from project_workspace import is_link
from report_contract import analyze

ALLOWED_EXTS={'.png','.jpg','.jpeg','.gif','.webp','.svg','.emf','.pdf'}
NAME=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$')
ASSET_TEXT=re.compile(r'(?<![A-Za-z0-9_.-])assets/([A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.(?:png|jpe?g|gif|webp|svg|emf|pdf))(?![A-Za-z0-9_.-])',re.I)
BATCH=re.compile(r'^[a-f0-9]{32}$')
MAX_DOCS=150
MAX_MARKDOWN_BYTES=10*1024*1024


def _sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def _atomic_json(path:Path,value:dict)->None:
    part=path.with_name(path.name+'.'+uuid.uuid4().hex[:8]+'.tmp')
    try:
        with part.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(part,path)
    finally:
        if part.exists():part.unlink()


def _protected_references(text:str)->set[str]:
    # IR captures single figures, image groups, sidecars and plain Markdown
    # images. A conservative raw-text scan additionally protects e.g. PDF
    # hypertext links or asset names cited inside ordinary prose/code.
    ir=analyze(text)
    if not ir['ok']:
        bad=next(d for d in ir['diagnostics'] if d['severity']=='error')
        raise ValueError('工程存在结构问题；修正后再整理附件：'+bad['message'])
    return {path[7:].casefold() for path in ir['assets']} | {name.casefold() for name in ASSET_TEXT.findall(text)}


class AssetHousekeeper:
    def __init__(self,root:Path,drafts_root:Path,doc_id:str):
        self.root=Path(root)
        self.drafts_root=Path(drafts_root)
        self.doc_id=doc_id
        if is_link(self.root) or not self.root.is_dir() or not (self.root/'report.md').is_file():
            raise ValueError('工程目录无效')
        if is_link(self.root/'assets') or not (self.root/'assets').is_dir():
            raise ValueError('工程 assets/ 目录无效')
        if is_link(self.root/'report.md'):raise ValueError('工程 report.md 不允许是链接文件')

    def _used_by(self,raw:bytes,origin:str)->set[str]:
        if len(raw)>MAX_MARKDOWN_BYTES:raise ValueError(origin+' 超过 Markdown 容量限制，暂不清理素材')
        try:text=raw.decode('utf-8')
        except UnicodeError as exc:raise ValueError(origin+' 无法解码为 UTF-8') from exc
        return _protected_references(text)

    def _draft_refs(self)->tuple[set[str],int]:
        matched=set();count=0
        if not self.drafts_root.is_dir():return matched,count
        for folder in self.drafts_root.iterdir():
            if is_link(folder) or not folder.is_dir():continue
            file=folder/'state.json'
            if not file.is_file():continue
            if is_link(file) or file.stat().st_size>MAX_MARKDOWN_BYTES*2:
                raise ValueError('草稿状态无法安全检查，拒绝清理')
            try:item=json.loads(file.read_text(encoding='utf-8'))
            except (ValueError,OSError,UnicodeError) as exc:
                raise ValueError('存在无法解析的草稿文件，清理已停止') from exc
            if item.get('document_id')!=self.doc_id:continue
            text=item.get('markdown')
            if not isinstance(text,str):raise ValueError('工程恢复草稿缺少 Markdown，清理已停止')
            matched.update(self._used_by(text.encode('utf-8'),'恢复草稿'))
            count+=1
            if count>MAX_DOCS:raise ValueError('关联草稿太多，请先整理草稿后再清理')
        return matched,count

    def _history_refs(self)->tuple[set[str],int]:
        items=set();count=0
        history=self.root/'.history'
        if is_link(history):raise ValueError('工程历史目录不允许是链接')
        if history.is_dir():
            for file in history.iterdir():
                if file.suffix.lower()!='.md':continue
                if is_link(file) or not file.is_file():raise ValueError('历史备份含非正常文件，清理已停止')
                count+=1
                if count>MAX_DOCS:raise ValueError('历史备份太多，暂不自动整理附件')
                if file.stat().st_size>MAX_MARKDOWN_BYTES:raise ValueError('历史备份超出 Markdown 容量限制，暂不清理附件')
                items.update(self._used_by(file.read_bytes(),'历史备份'))
        return items,count

    def _current_refs(self,raw):
        current=self._used_by(raw,'正式报告')
        # The registered report is primary, but other top-level .md notes in
        # the same explicitly selected project may mention project assets too.
        # Prefer a false positive (keep image) over breaking a manual note.
        notes=0
        for file in self.root.iterdir():
            if file.name=='report.md' or file.suffix.lower() not in ('.md','.markdown'):continue
            if is_link(file) or not file.is_file():raise ValueError('工程内有异常 Markdown 文件，暂不整理附件')
            if file.stat().st_size>MAX_MARKDOWN_BYTES:raise ValueError('工程内备注过大，暂不整理附件')
            notes+=1
            if notes>MAX_DOCS:raise ValueError('工程备注太多，暂不整理附件')
            current.update(self._used_by(file.read_bytes(),'工程内部 Markdown 备注'))
        return current

    def scan(self)->dict:
        raw=(self.root/'report.md').read_bytes()
        current=self._current_refs(raw)
        drafted,drafts=self._draft_refs()
        history,histories=self._history_refs()
        grouped:dict[str,list[dict]]={}
        excluded=0
        for file in (self.root/'assets').iterdir():
            if is_link(file) or not file.is_file() or not NAME.fullmatch(file.name) or file.suffix.lower() not in ALLOWED_EXTS:
                excluded+=1;continue
            stem=file.stem.casefold()
            grouped.setdefault(stem,[]).append({'name':file.name,'bytes':file.stat().st_size,'sha256':_sha(file)})
        results=[]
        for key,files in sorted(grouped.items()):
            files.sort(key=lambda x:x['name'].lower())
            names={f['name'].casefold() for f in files}
            if names & current:status='in_use'
            elif names & drafted:status='draft'
            elif names & history:status='history'
            else:status='unused'
            results.append({'id':key,'files':files,'status':status,'total_bytes':sum(f['bytes'] for f in files)})
        counts={key:{'groups':0,'bytes':0} for key in ('in_use','draft','history','unused')}
        for group in results:
            counts[group['status']]['groups']+=1
            counts[group['status']]['bytes']+=group['total_bytes']
        return {'ok':True,'revision':hashlib.sha256(raw).hexdigest(),'groups':results,'summary':counts,
                'excluded':excluded,'draft_count':drafts,'history_count':histories}

    def move_to_trash(self,selected:dict[str,dict[str,str]],*,include_history=False)->dict:
        if not isinstance(selected,dict) or not selected or len(selected)>500:
            raise ValueError('请先选择要整理的素材组')
        scan=self.scan()
        group_map={item['id']:item for item in scan['groups']}
        targets=[]
        for key,expected in selected.items():
            item=group_map.get(key)
            if item is None or item['status'] not in ('unused','history'):
                raise ValueError('素材当前仍被报告或草稿引用，请重新扫描')
            if item['status']=='history' and include_history is not True:
                raise ValueError('该素材存在历史引用，必须单独确认')
            check={f['name']:f['sha256'] for f in item['files']}
            if expected!=check:raise ValueError('素材或扫描结果已变化，请重新扫描再整理')
            targets.extend(item['files'])
        folder=self.root/'.asset-trash'
        if is_link(folder):raise ValueError('工程回收区路径不可为链接')
        if not folder.exists():folder.mkdir(mode=0o700)
        if not folder.is_dir():raise ValueError('工程回收区无法使用')
        batch_id=uuid.uuid4().hex
        batch=folder/batch_id
        batch.mkdir(mode=0o700)
        (batch/'assets').mkdir()
        manifest={'version':1,'batch_id':batch_id,'created_at':datetime.now(timezone.utc).isoformat(),
                  'state':'pending','files':targets,'groups':sorted(selected)}
        moved=[]
        try:
            _atomic_json(batch/'manifest.json',manifest)
            for file in targets:
                src=self.root/'assets'/file['name'];dest=batch/'assets'/file['name']
                if is_link(src) or not src.is_file() or src.stat().st_size!=file['bytes'] or _sha(src)!=file['sha256']:
                    raise ValueError('源素材发生变化，整理已停止')
                if dest.exists():raise ValueError('回收区已有同名目标，拒绝覆盖')
                os.replace(src,dest);moved.append((dest,src))
            manifest['state']='stored'
            _atomic_json(batch/'manifest.json',manifest)
        except Exception:
            for dest,src in reversed(moved):
                if dest.exists() and not src.exists():os.replace(dest,src)
            # Keep the manifest if rollback did not succeed. Recovery remains possible.
            if not any(p.exists() for p,_ in moved):
                try:(batch/'manifest.json').unlink();(batch/'assets').rmdir();batch.rmdir()
                except OSError:pass
            raise
        return {'ok':True,'batch_id':batch_id,'moved_files':len(targets),'moved_bytes':sum(x['bytes'] for x in targets)}

    def batches(self)->list[dict]:
        folder=self.root/'.asset-trash'
        if is_link(folder):raise ValueError('工程回收区目录无效')
        if not folder.is_dir():return []
        result=[]
        for path in folder.iterdir():
            if not BATCH.fullmatch(path.name) or is_link(path) or not path.is_dir():continue
            mf=path/'manifest.json'
            if is_link(mf) or not mf.is_file():continue
            data=json.loads(mf.read_text(encoding='utf-8'))
            if data.get('state')!='stored' or data.get('batch_id')!=path.name:continue
            result.append({'batch_id':path.name,'created_at':data.get('created_at',''),
                           'file_count':len(data['files']), 'total_bytes':sum(f['bytes'] for f in data['files'])})
        return sorted(result,key=lambda item:item['created_at'],reverse=True)[:25]

    def _trash_inventory(self):
        """Validate the complete recycle tree, not just the 25 displayed batches."""
        folder=self.root/'.asset-trash';batches=[];snapshot=[]
        if is_link(folder):raise ValueError('工程回收区不可为链接')
        if folder.exists() and not folder.is_dir():raise ValueError('工程回收区目录无效')
        for batch in sorted(folder.iterdir()) if folder.exists() else []:
            if not BATCH.fullmatch(batch.name) or is_link(batch) or not batch.is_dir():
                raise ValueError('回收区有未知文件或链接，拒绝清空')
            mf=batch/'manifest.json';assets=batch/'assets'
            if is_link(mf) or not mf.is_file() or mf.stat().st_size>MAX_MARKDOWN_BYTES or is_link(assets):
                raise ValueError('回收区批次结构异常，拒绝清空')
            data=json.loads(mf.read_text(encoding='utf8'))
            if not isinstance(data,dict):raise ValueError('回收批次清单无效')
            state=data.get('state')
            if data.get('batch_id')!=batch.name or state not in ('stored','restored','purging') or not isinstance(data.get('files'),list):
                raise ValueError('回收区批次不完整，拒绝清空')
            if not assets.is_dir() and not (state=='purging' and not assets.exists()):raise ValueError('回收区附件目录无效')
            if {p.name for p in batch.iterdir()}!=({'manifest.json','assets'} if assets.exists() else {'manifest.json'}):
                raise ValueError('回收区有未知文件，拒绝清空')
            expected={}
            for info in data['files']:
                if not isinstance(info,dict):raise ValueError('回收文件清单无效')
                name=info.get('name')
                if not isinstance(name,str) or not NAME.fullmatch(name) or Path(name).suffix.lower() not in ALLOWED_EXTS or name in expected:
                    raise ValueError('回收文件清单无效')
                expected[name]=info
            actual={p.name:p for p in assets.iterdir()} if assets.exists() else {}
            if (state=='stored' and actual.keys()!=expected.keys() or state=='restored' and actual or not actual.keys()<=expected.keys()):
                raise ValueError('回收区文件与清单不一致，请先处理异常批次')
            files=[]
            for name,file in sorted(actual.items()):
                info=expected[name]
                if is_link(file) or not file.is_file() or file.stat().st_size!=info.get('bytes') or _sha(file)!=info.get('sha256'):
                    raise ValueError('回收附件已变化或损坏，请重新检查')
                files.append((file,info))
            snapshot.append([batch.name,_sha(mf),[(p.name,i['sha256'],i['bytes']) for p,i in files]])
            batches.append((batch,data,files))
        summary={'revision':hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest(),
                 'batch_count':len(batches),'file_count':sum(len(files) for _,_,files in batches),
                 'total_bytes':sum(info['bytes'] for _,_,files in batches for _,info in files)}
        return summary,batches

    def trash_snapshot(self):
        return self._trash_inventory()[0]

    def purge(self,expected_revision):
        summary,batches=self._trash_inventory()
        if not isinstance(expected_revision,str) or expected_revision!=summary['revision']:
            raise ValueError('回收区已变化，请重新检查并确认清空')
        protected=self._current_refs((self.root/'report.md').read_bytes())|self._draft_refs()[0]
        if any(file.name.casefold() in protected for _,_,files in batches for file,_ in files):
            raise ValueError('回收附件被当前文稿、工程备注或恢复草稿引用，请先恢复相应批次')
        removed=0
        try:
            for batch,data,files in batches:
                # Persist a resumable state before irreversible deletion. On an
                # occupied file, a later explicit scan/confirm may clear the rest.
                data['state']='purging';_atomic_json(batch/'manifest.json',data)
                for file,_ in files:
                    if is_link(batch) or is_link(file.parent) or is_link(file):raise ValueError('回收区路径已变化，已停止清理')
                    file.unlink();removed+=1
                if (batch/'assets').exists():(batch/'assets').rmdir()
                (batch/'manifest.json').unlink();batch.rmdir()
        except OSError as error:
            raise RuntimeError(f'回收区清理未完成，已删除 {removed} 个附件；其余保留，请关闭占用文件后重新检查') from error
        return {'ok':True,'removed_files':removed,'removed_bytes':summary['total_bytes'],'removed_batches':len(batches)}

    def restore(self,batch_id:str)->dict:
        if not isinstance(batch_id,str) or not BATCH.fullmatch(batch_id):raise ValueError('回收批次 ID 无效')
        folder=self.root/'.asset-trash'
        if is_link(folder):raise ValueError('工程回收区不可为链接')
        batch=folder/batch_id;manifest_path=batch/'manifest.json'
        if is_link(batch) or is_link(manifest_path) or not manifest_path.is_file():raise ValueError('找不到可恢复的回收批次')
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('state')!='stored' or manifest.get('batch_id')!=batch_id:raise ValueError('批次已恢复或信息不完整')
        files=manifest.get('files')
        if not isinstance(files,list) or not files:raise ValueError('回收批次内容无效')
        moves=[]
        for info in files:
            name=info.get('name')
            if not isinstance(name,str) or not NAME.fullmatch(name) or Path(name).suffix.lower() not in ALLOWED_EXTS:raise ValueError('回收文件名非法')
            src=batch/'assets'/name;dst=self.root/'assets'/name
            if is_link(src) or not src.is_file() or dst.exists() or is_link(dst) or _sha(src)!=info['sha256'] or src.stat().st_size!=info['bytes']:
                raise ValueError('有文件已移动、损坏或项目中出现同名素材，不能安全恢复')
            moves.append((src,dst))
        restored=[]
        try:
            for src,dst in moves:os.replace(src,dst);restored.append((dst,src))
            manifest['state']='restored';_atomic_json(manifest_path,manifest)
        except Exception:
            for dst,src in reversed(restored):
                if dst.exists() and not src.exists():os.replace(dst,src)
            raise
        return {'ok':True,'restored_files':len(restored),'batch_id':batch_id}
