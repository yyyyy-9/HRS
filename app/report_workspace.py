"""Owned report-workspace metadata, reversible lifecycle and bounded copy jobs."""
from pathlib import Path
import hashlib
import json
import os
import re
import secrets
import threading
import time
from project_workspace import is_link
from asset_paths import asset_file

SCHEMA = 'hrs-report-workspace-v1'
ID = re.compile(r'^[a-f0-9]{32}$')


def metadata(project, workspace):
    project,workspace=Path(project),Path(workspace)
    if project.parent.resolve()!=workspace.resolve() or is_link(project):return None
    try:
        path=project/'meta.json'
        if is_link(path):return None
        meta=json.loads(path.read_text('utf8'))
        if not isinstance(meta,dict):return None
        value=meta.get('report_workspace')
        if not isinstance(value,dict) or value.get('schema')!=SCHEMA:return None
        if not re.fullmatch(r'new|legacy|[a-f0-9]{32}',value.get('origin_document_id','')):return None
        if not re.fullmatch(r'[a-f0-9]{64}',value.get('source_sha256','')):return None
        return meta
    except (OSError,ValueError,TypeError):return None


def info(project, workspace):
    if project is None:return None
    meta=metadata(project,workspace)
    return meta['report_workspace'] if meta else None


def list_reports(workspace,document_id,draft_id=None,*,offset=0,limit=30,
                 include_archived=False,include_trash=False,source_sha256=None):
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=50:
        raise ValueError('工作页分页范围无效')
    workspace=Path(workspace);items=[];roots=[(workspace,False)]
    trash=workspace/'.report-workspace-trash'
    if include_trash and trash.is_dir() and not is_link(trash):roots.append((trash,True))
    for root,trashed in roots:
        for project in root.iterdir():
            if not ID.fullmatch(project.name) or not project.is_dir():continue
            meta=metadata(project,root)
            if meta is None:continue
            descriptor=meta['report_workspace']
            if descriptor['origin_document_id']!=document_id:continue
            if document_id=='new' and descriptor.get('origin_draft_id')!=draft_id:continue
            state='trashed' if trashed else meta.get('workspace_state','active')
            if state=='archived' and not include_archived:continue
            items.append({'document_id':project.name,'title':meta.get('title','临时工程稿'),
                          'updated':meta.get('updated',''),'created':meta.get('created',''),
                          'origin':descriptor.get('title',''),'state':state,'_path':project,
                          'source_current':None if source_sha256 is None else descriptor['source_sha256']==source_sha256})
    items.sort(key=lambda item:item['updated'],reverse=True);end=offset+limit
    page=[]
    for item in items[offset:end]:
        project=item.pop('_path')
        try:
            # Size and revision need I/O only for the visible page. An archive
            # or restore in another window may invalidate an individual row.
            size=0
            for folder,dirs,names in os.walk(project,followlinks=False):
                dirs[:]=[d for d in dirs if not is_link(Path(folder)/d)]
                for name in names:
                    file=Path(folder)/name
                    if file.is_file() and not is_link(file):size+=file.stat().st_size
            item.update(bytes=size,revision=hashlib.sha256((project/'report.md').read_bytes()).hexdigest())
        except OSError:continue
        page.append(item)
    return {'reports':page,'total':len(items),'next_offset':end if end<len(items) else None}


def lifecycle(workspace,document_id,action,expected_revision):
    """Only internal report workspaces; recycle is a rename, never a deletion."""
    from studio import atomic_write
    workspace=Path(workspace).resolve()
    if not isinstance(document_id,str) or not ID.fullmatch(document_id):raise ValueError('临时稿 ID 无效')
    trash=workspace/'.report-workspace-trash'
    if is_link(trash):raise ValueError('临时稿回收站不可是链接')
    root=trash if action=='restore' else workspace;project=root/document_id
    meta=metadata(project,root)
    if meta is None:raise ValueError('只能管理本机内部临时工程稿')
    source=project/'report.md'
    if is_link(source) or hashlib.sha256(source.read_bytes()).hexdigest()!=expected_revision:
        raise RuntimeError('临时稿版本已变化，请重新打开后操作')
    if action in ('archive','unarchive'):
        meta['workspace_state']='archived' if action=='archive' else 'active'
        atomic_write(project/'meta.json',(json.dumps(meta,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    elif action in ('trash','restore'):
        target_root=workspace if action=='restore' else trash;target_root.mkdir(exist_ok=True);target=target_root/document_id
        if target.exists() or is_link(target):raise ValueError('目标临时稿已存在，不能覆盖')
        os.replace(project,target)
    else:raise ValueError('未知临时稿管理操作')
    return {'document_id':document_id,'action':action,'original_preserved':True}


class Cancelled(RuntimeError):
    pass


class CopyAsset:
    """One verified file copied in chunks; never retain the whole asset set."""
    def __init__(self,path,expected,progress):
        self.path=Path(path);self.expected=expected;self.progress=progress

    def copy_to(self,target):
        sha=hashlib.sha256()
        if is_link(self.path):raise ValueError('附件不能是链接')
        with self.path.open('rb') as source,target.open('xb') as output:
            while True:
                self.progress.check();chunk=source.read(1024*1024)
                if not chunk:break
                output.write(chunk);sha.update(chunk);self.progress.advance(len(chunk))
        if sha.hexdigest()!=self.expected:raise RuntimeError('提取期间附件已变化：'+self.path.name)


class Progress:
    def __init__(self,event=None,update=None):
        self.event=event or threading.Event();self.update=update or (lambda **values:None);self.rollback=None

    def check(self,**values):
        if values:self.update(**values)
        if self.event.is_set():raise Cancelled('操作已取消，未交付的临时稿已清理')

    def advance(self,count):
        self.check();self.update(increment=count)


class WorkspaceJobs:
    """Max two active local jobs; completed entries expire and release inputs."""
    def __init__(self):
        self.lock=threading.RLock();self.jobs={};self.closed=False

    def submit(self,owner,action):
        with self.lock:
            now=time.monotonic()
            self.jobs={key:job for key,job in self.jobs.items() if not job['done'] or now-job['ended']<1200}
            if self.closed or sum(not job['done'] for job in self.jobs.values())>=2:
                raise RuntimeError('已有两个工作页任务，请等待或取消一个')
            completed=[key for key,job in self.jobs.items() if job['done']]
            while len(self.jobs)>=32 and completed:self.jobs.pop(completed.pop(0))
            token=secrets.token_urlsafe(32);job={'owner':owner,'state':'running','phase':'验证来源','bytes_done':0,'bytes_total':0,
                'done':False,'ended':None,'event':threading.Event(),'result':None,'error':None};self.jobs[token]=job
        def update(**values):
            with self.lock:
                job['bytes_done']+=values.pop('increment',0);job.update(values)
        def run():
            progress=Progress(job['event'],update)
            try:
                result=action(progress)
                with self.lock:
                    progress.check();job.update(state='completed',result=result);progress.rollback=None
            except Exception as exc:
                cleanup_error=None
                if progress.rollback:
                    try:progress.rollback()
                    except OSError as cleanup:cleanup_error=str(cleanup)
                with self.lock:
                    job.update(state='cancelled' if isinstance(exc,Cancelled) and not cleanup_error else 'failed',
                        error=str(exc)+('；清理失败：'+cleanup_error if cleanup_error else ''))
            finally:
                with self.lock:job.update(done=True,ended=time.monotonic())
        thread=threading.Thread(target=run,name='hrs-workspace-copy',daemon=True);job['thread']=thread;thread.start()
        return token

    def status(self,token,owner,cancel=False):
        with self.lock:
            job=self.jobs.get(token)
            if job is None or job['owner']!=owner:raise ValueError('工作页任务不存在或不属于当前来源')
            if cancel and not job['done']:job['event'].set()
            return {key:job[key] for key in ('state','phase','bytes_done','bytes_total','result','error')}

    def close(self):
        with self.lock:
            self.closed=True;active=[job for job in self.jobs.values() if not job['done']]
            for job in active:job['event'].set()
        for job in active:job['thread'].join(timeout=5)


# Explicit report-to-origin plans reuse the existing report lock/backup/commit.
# The source range and copied shared definitions are frozen when the workspace is
# created. No reverse Markdown converter or positional guess is used.
ORIGIN_FILE = '.hrs-report-origin.json'
SYNC_SCHEMA = 'hrs-workspace-sync-v1'


def _encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _slice(text,start,end):
    if type(start) is not int or type(end) is not int or start<0 or end<start:
        raise ValueError('来源范围无效')
    raw=text.encode('utf-16-le')
    if end*2>len(raw):raise ValueError('来源范围越界')
    try:return raw[start*2:end*2].decode('utf-16-le')
    except UnicodeDecodeError as exc:raise ValueError('来源范围截断了字符') from exc


def freeze_origin(full,markdown,mapping,document_id):
    from report_contract import analyze
    if not isinstance(mapping,dict):return None  # Legacy workspaces remain independent.
    start,end=mapping.get('start'),mapping.get('end')
    body=_slice(full,start,end)
    ir=analyze(full)
    boundaries=sorted({0,len(full.encode('utf-16-le'))//2,*[b['start'] for b in ir['blocks'] if b['type']=='heading' and b.get('level')==1]})
    if not (start==0 and end==boundaries[-1]) and not any((start,end)==(a,b) for a,b in zip(boundaries,boundaries[1:])):
        raise ValueError('只能同步整篇或一个已确认的一级标题范围')
    deps=mapping.get('dependencies')
    if not isinstance(deps,list) or len(deps)>5000:raise ValueError('共享定义范围无效')
    ranges=[(start,end)];append=[]
    for dep in deps:
        a,b=dep.get('start'),dep.get('end');raw=_slice(full,a,b)
        if dep.get('kind') not in ('footnote','link') or not isinstance(dep.get('key'),str) or not dep['key']:
            raise ValueError('共享定义身份无效')
        if not re.match(r'^ {0,3}\[[^\]\r\n]+\]:',raw):raise ValueError('共享定义不在原定义位置')
        if 'newline_tail' in dep and dep['newline_tail']!=(re.search(r'(?:\r?\n)+$',raw).group() if re.search(r'(?:\r?\n)+$',raw) else ''):
            raise ValueError('共享定义段落边界不一致')
        if any(a<y and b>x for x,y in ranges):raise ValueError('同步范围互相重叠')
        if any(block['start']<=a<block['end'] and block['type'] in ('code','figure','table','mermaid','equation') for block in ir['blocks']):
            raise ValueError('代码和工程对象不能作为共享定义')
        ranges.append((a,b));append.append(raw)
    newline='\r\n' if '\r\n' in full else '\n'
    if 'appended_separator' in mapping and mapping['appended_separator']!=('' if not append or body.endswith(newline+newline) else newline+newline):
        raise ValueError('共享定义分隔与来源不一致')
    expected=body+('' if not append else ('' if body.endswith(newline+newline) else newline+newline)+ (newline+newline).join(append))
    if markdown!=expected:raise ValueError('临时稿不等于声明的来源范围及共享定义')
    return {'schema':SYNC_SCHEMA,'origin_document_id':document_id,'full_markdown':full,'mapping':mapping}


def _file_sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk:=stream.read(1024*1024):result.update(chunk)
    return result.hexdigest()


def _sync_candidate(project,origin,descriptor,request,asset_roots):
    from report_contract import analyze
    project,origin=Path(project),Path(origin)
    path=project/ORIGIN_FILE
    if not descriptor.get('sync_available') or not path.is_file() or is_link(path):
        raise ValueError('此临时稿没有可同步的已保存来源；请先保存源稿，再重新准备临时稿')
    base=json.loads(path.read_text('utf8'));full=base['full_markdown'];raw=(origin/'report.md').read_bytes()
    if base.get('schema')!=SYNC_SCHEMA or base.get('origin_document_id')!=descriptor['origin_document_id']:
        raise ValueError('来源快照身份不一致')
    if raw!=full.encode('utf8') or _sha(raw)!=descriptor['source_sha256']:
        raise ValueError('源文件已变化，请重新准备；本次不会覆盖源稿')
    text=request.get('markdown')
    if not isinstance(text,str) or len(text.encode('utf8'))>10*1024*1024:raise ValueError('临时稿正文无效')
    edits=request.get('edits');mapping=base['mapping']
    allowed={(mapping['start'],mapping['end'],'body','')}
    allowed.update((d['start'],d['end'],d['kind'],d['key']) for d in mapping['dependencies'])
    if not isinstance(edits,list) or not edits or len(edits)>len(allowed):raise ValueError('同步候选范围无效')
    seen=set()
    for e in edits:
        key=(e.get('start'),e.get('end'),e.get('kind'),e.get('key',''))
        if key not in allowed or key in seen or not isinstance(e.get('text'),str):raise ValueError('候选修改超出已确认来源范围')
        if e['kind']!='body' and not re.match(r'^ {0,3}\[[^\]\r\n]+\]:',e['text']):
            raise ValueError('共享定义不能转换成其他正文')
        seen.add(key)
    if sum(e['kind']=='body' for e in edits)!=1:raise ValueError('同步必须明确正文范围')
    candidate=full
    for e in sorted(edits,key=lambda e:e['start'],reverse=True):
        # UTF-16 is the common HRS range unit; preserve every byte outside edits.
        before=_slice(candidate,0,e['start']);after=_slice(candidate,e['end'],len(candidate.encode('utf-16-le'))//2)
        candidate=before+e['text']+after
    encoded=candidate.encode('utf8')
    if len(encoded)>10*1024*1024:raise ValueError('同步后正文超过10 MiB')
    ir=analyze(candidate)
    invalid=[d for d in ir['diagnostics'] if d['severity']=='error']
    if invalid:raise ValueError('同步候选结构错误：'+invalid[0]['message'])
    if is_link(origin) or is_link(origin/'assets') or is_link(origin/'report.md'):raise ValueError('来源工程不能通过链接写入')
    assets={}
    # Candidate may also contain untouched origin assets outside the topic.
    for url in ir['assets']:
        name=url.removeprefix('assets/')
        choices=[asset_file(r,name) for r in asset_roots]+[asset_file(origin/'assets',name)]
        source=next((p for p in choices if p.is_file() and not is_link(p)),None)
        if source is None:raise ValueError('同步附件缺失：'+name)
        digest=_file_sha(source);target=asset_file(origin/'assets',name)
        if target.exists() and (is_link(target) or _file_sha(target)!=digest):
            raise ValueError('源稿存在同名不同内容附件：'+name)
        assets[name]={'sha256':digest,'source':str(source)}
    import difflib
    plan={'schema':SYNC_SCHEMA,'origin_document_id':descriptor['origin_document_id'],
          'source_sha256':_sha(raw),'candidate_sha256':_sha(encoded),
          'workspace_revision':request.get('revision'),'workspace_text_sha256':_sha(text.encode('utf8')),
          'edits':edits,'asset_hashes':assets,
          'diff':''.join(difflib.unified_diff(full.splitlines(True),candidate.splitlines(True),fromfile='源稿 report.md',tofile='同步候选 report.md'))}
    return plan,encoded,base


def plan_sync(project,origin,descriptor,request,asset_roots):
    from studio import atomic_write
    plan,_,_=_sync_candidate(project,origin,descriptor,request,asset_roots)
    folder=Path(project)/'.sync-plans'
    if is_link(folder):raise ValueError('同步计划目录不能是链接')
    folder.mkdir(exist_ok=True)
    for old in sorted(folder.glob('*.json'),key=lambda p:p.stat().st_mtime)[:-7]:
        if not is_link(old):old.unlink()
    token=secrets.token_hex(16);body=_encoded(plan);atomic_write(folder/(token+'.json'),body)
    return {'plan_id':token,'plan_sha256':_sha(body),'diff':plan['diff'],
            'source_revision':plan['source_sha256'],'candidate_revision':plan['candidate_sha256'],
            'original_unchanged':True,'changed':plan['source_sha256']!=plan['candidate_sha256']}


def apply_sync(project,origin,descriptor,request,asset_roots,*,after_commit=None):
    from project_commit import report_lock,commit_report_locked
    from studio import atomic_write
    import tempfile
    project,origin=Path(project),Path(origin)
    token=request.get('plan_id')
    if not isinstance(token,str) or not ID.fullmatch(token):raise ValueError('同步计划ID无效')
    path=project/'.sync-plans'/(token+'.json')
    if is_link(path) or is_link(path.parent):raise ValueError('同步计划不能是链接')
    raw=path.read_bytes()
    if _sha(raw)!=request.get('plan_sha256'):raise ValueError('同步计划已变化，请重新查看差异')
    reviewed=json.loads(raw)
    with report_lock(origin):
        fresh,candidate,base=_sync_candidate(project,origin,descriptor,request,asset_roots)
        if fresh!=reviewed or path.read_bytes()!=raw:raise ValueError('同步候选或附件已变化，请重新查看差异')
        (origin/'assets').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.hrs-sync-',dir=origin) as temp:
            for name,item in fresh['asset_hashes'].items():
                target=asset_file(origin/'assets',name)
                if target.exists():
                    if is_link(target) or _file_sha(target)!=item['sha256']:raise ValueError('同步期间来源附件变化：'+name)
                    continue
                stage=asset_file(temp,name);stage.parent.mkdir(parents=True,exist_ok=True)
                CopyAsset(item['source'],item['sha256'],Progress()).copy_to(stage)
                target.parent.mkdir(parents=True,exist_ok=True)
                target=asset_file(origin/'assets',name)
                try:
                    if os.name=='nt':os.rename(stage,target)  # Windows rename never replaces an existing target.
                    else:os.link(stage,target)  # Same-volume stage; atomic create without replacement.
                except FileExistsError:
                    if is_link(target) or _file_sha(target)!=item['sha256']:raise ValueError('同步期间出现同名不同内容附件：'+name)
        for name,item in fresh['asset_hashes'].items():
            if _file_sha(asset_file(origin/'assets',name))!=item['sha256']:raise ValueError('提交前来源附件变化：'+name)
        backup=commit_report_locked(origin,candidate,fresh['source_sha256'])
        # Rebase only the explicitly edited ranges, enabling another reviewed sync.
        edits=fresh['edits']
        def rebase(part):
            start,end=part['start'],part['end']
            shift=sum(len(e['text'].encode('utf-16-le'))//2-(e['end']-e['start']) for e in edits if e['end']<=start and e['start']!=start)
            edit=next((e for e in edits if e['start']==start and e['end']==end),None)
            return {**part,'start':start+shift,'end':start+shift+(len(edit['text'].encode('utf-16-le'))//2 if edit else end-start)}
        mapping={**rebase(base['mapping']),'dependencies':[rebase(d) for d in base['mapping']['dependencies']]}
        base.update(full_markdown=candidate.decode('utf8'),mapping=mapping)
        descriptor={**descriptor,'source_sha256':fresh['candidate_sha256'],'origin_revision':fresh['candidate_sha256'],'sync':mapping}
        try:
            atomic_write(project/ORIGIN_FILE,_encoded(base))
            meta=json.loads((project/'meta.json').read_text('utf8'));meta['report_workspace']=descriptor
            atomic_write(project/'meta.json',_encoded(meta))
            if after_commit:after_commit(candidate)
        except OSError as exc:
            raise RuntimeError('源稿已同步且原稿备份保留，但工程元数据更新失败；请返回源稿核对后重新准备') from exc
    return {'origin_document_id':descriptor['origin_document_id'],'origin_revision':fresh['candidate_sha256'],
            'backup':str(backup) if backup else None,'updated':backup is not None,'report_workspace':descriptor,
            'outside_ranges_unchanged':True}
