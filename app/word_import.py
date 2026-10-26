"""DOCX UI adapter: isolated existing Bridge, page-owned serializers, new projects.

The child reads a frozen DOCX. Its bounded JSON channel delegates only existing
HRS serializers to the open page; no Word/Markdown parser is implemented here.
"""
from __future__ import annotations
from contextlib import redirect_stdout
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from project_workspace import copy_project_tree,is_link

MAX_DOCX_BYTES=64*1024*1024
MAX_EXPANDED_BYTES=256*1024*1024
MAX_WIRE_BYTES=16*1024*1024
IMPORT_SECONDS=180
READY_SECONDS=1800


def digest(raw):return hashlib.sha256(raw).hexdigest()


def selected_source(path):
    path=Path(path)
    if path.suffix.lower()!='.docx' or is_link(path) or not path.is_file():
        raise ValueError('请选择普通 .docx 文件；旧 .doc 请先在 WPS／Word 中另存为 DOCX')
    if path.stat().st_size>MAX_DOCX_BYTES:raise ValueError('Word 文档超过 64 MiB')
    with path.open('rb') as stream:raw=stream.read(MAX_DOCX_BYTES+1)
    if len(raw)>MAX_DOCX_BYTES:raise ValueError('Word 文档超过 64 MiB')
    try:
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            entries=archive.infolist();names=[e.filename for e in entries]
            if (len(entries)>5000 or sum(e.file_size for e in entries)>MAX_EXPANDED_BYTES or
                len(names)!=len(set(names)) or not {'[Content_Types].xml','word/document.xml'}<=set(names)):
                raise ValueError('Word 压缩结构无效或展开超过限制')
    except zipfile.BadZipFile:
        raise ValueError('所选文件不是可读取的 DOCX；请用 WPS／Word 另存为普通 DOCX 后导入') from None
    companion=Path(str(path)+'.hrs-bridge.json')
    mapping=None
    if companion.exists() or is_link(companion):
        if is_link(companion) or not companion.is_file() or companion.stat().st_size>MAX_DOCX_BYTES:
            raise ValueError('Word 同名来源映射无效或超过 64 MiB')
        with companion.open('rb') as stream:mapping=stream.read(MAX_DOCX_BYTES+1)
        if len(mapping)>MAX_DOCX_BYTES:raise ValueError('Word 来源映射超过 64 MiB')
    return path.resolve(),raw,mapping


class WordImport:
    def __init__(self,exporter,workspace):
        self.exporter=exporter;self.workspace=Path(workspace)
        self.jobs={};self.guard=threading.RLock();self.closed=False

    def _get(self,token):
        job=self.jobs.get(token) if isinstance(token,str) else None
        if not job:raise ValueError('Word 导入会话已结束，请重新选择文件')
        if time.monotonic()-job['at']>READY_SECONDS:raise ValueError('Word 导入会话已过期，请重新选择文件')
        return job

    def begin(self,source):
        with self.guard:
            expired=[t for t,j in self.jobs.items() if time.monotonic()-j['at']>READY_SECONDS or j['state']=='error']
        for token in expired:self.cancel(token)
        rt=self.exporter.runtime()
        if rt is None:raise ValueError('Word 基础组件未找到，请在导入窗口选择匹配组件')
        path,raw,mapping=selected_source(source)
        with self.guard:
            if self.closed or self.jobs:raise RuntimeError('已有 Word 导入正在进行，请先完成或取消')
            if not self.exporter.running.acquire(blocking=False):raise RuntimeError('Word 转换正在进行，请稍后导入')
            temporary=None;token=None
            try:
                temporary=tempfile.TemporaryDirectory(prefix='.hrs-word-import-',dir=self.workspace)
                folder=Path(temporary.name);frozen=folder/path.name;frozen.write_bytes(raw)
                if mapping is not None:Path(str(frozen)+'.hrs-bridge.json').write_bytes(mapping)
                req={'app':str(self.exporter.app),'bridge':str(rt['bridge']),'wps':str(rt['wps']),
                     'libs':str(rt['libs']) if rt['libs'] else None,
                     'pandoc':str(self.exporter.pandoc(rt)) if self.exporter.pandoc(rt) else None,
                     'source':str(frozen),'output':str(folder/'project')}
                request=folder/'request.json';request.write_text(json.dumps(req,ensure_ascii=False),encoding='utf8')
                token=secrets.token_hex(24)
                job={'at':time.monotonic(),'temporary':temporary,'source':path,'sha256':digest(raw),
                     'mapping_sha256':digest(mapping) if mapping is not None else None,'state':'working',
                     'seq':0,'pending':None,'answer':None,'process':None,'cancelled':threading.Event(),
                     'wake':threading.Event(),'request':request,'runtime':rt}
                self.jobs[token]=job
                thread=threading.Thread(target=self._run,args=(job,),daemon=True,name='hrs-word-import')
                expiry=threading.Timer(READY_SECONDS,lambda:self.cancel(token));expiry.daemon=True;job['expiry']=expiry
                job['thread']=thread;thread.start()
                expiry.start()
                return {'job_token':token,'filename':path.name,'state':'working'}
            except Exception:
                if token:self.jobs.pop(token,None)
                self.exporter.running.release()
                if temporary:temporary.cleanup()
                raise

    def _run(self,job):
        process=None;timer=None
        try:
            folder=Path(job['temporary'].name)
            with (folder/'worker.stderr').open('wb') as error_log:
                process=subprocess.Popen([str(job['runtime']['python']),'-X','utf8','-B',
                    str(self.exporter.app/'word_import.py'),'--worker',str(job['request'])],
                    cwd=job['runtime']['root'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=error_log,
                    start_new_session=os.name!='nt',
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                with self.guard:job['process']=process
                timer=threading.Timer(IMPORT_SECONDS,lambda:self._stop(job));timer.daemon=True;timer.start()
                if job['cancelled'].is_set():self._stop(job)
                while True:
                    line=process.stdout.readline(MAX_WIRE_BYTES+1)
                    if not line:
                        detail=(folder/'worker.stderr').read_bytes()[-1800:].decode('utf8',errors='replace')
                        raise RuntimeError('Word 导入子进程提前退出；请核对组件和文档。'+detail)
                    if len(line)>MAX_WIRE_BYTES:raise ValueError('Word 导入数据超过会话限制')
                    message=json.loads(line)
                    if message.get('kind')=='serialize':
                        items=message.get('items')
                        if not isinstance(items,list) or not 1<=len(items)<=1000 or any(not isinstance(x,dict) or x.get('type') not in ('image-group','gfm','equation') for x in items):
                            raise ValueError('Word 组件请求了不支持的页面操作')
                        with self.guard:
                            job['seq']+=1;job['pending']={'seq':job['seq'],'items':items};job['state']='page'
                        if not job['wake'].wait(IMPORT_SECONDS):raise RuntimeError('Word 导入等待页面响应超时')
                        job['wake'].clear()
                        with self.guard:
                            if job['cancelled'].is_set():raise RuntimeError('Word 导入已取消或超过 180 秒')
                            answer=job['answer'];job['answer']=None;job['pending']=None;job['state']='working'
                        process.stdin.write((json.dumps(answer,ensure_ascii=False)+'\n').encode('utf8'));process.stdin.flush()
                    elif message.get('kind')=='result':
                        if not message.get('ok'):raise ValueError(message.get('error','Word 导入失败'))
                        process.wait(timeout=5)
                        if process.returncode:raise RuntimeError('Word 导入子进程退出异常')
                        receipt=message['receipt'];project=folder/'project'
                        if not (project/'report.md').is_file() or not (project/'assets').is_dir():raise ValueError('Word 组件没有交付完整工程')
                        receipt['status']=receipt.get('status','COMPLETE')
                        if receipt['status'] not in ('COMPLETE','NEEDS_REVIEW'):raise ValueError('Word 导入状态无效')
                        receipt['source_filename']=job['source'].name;receipt['source_sha256']=job['sha256'];receipt['output']='.'
                        if 'recognition' in receipt:receipt['recognition']['path']='word-recognition.json'
                        (project/'output').mkdir(exist_ok=True)
                        (project/'word-import.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
                        with self.guard:
                            if job['cancelled'].is_set():raise RuntimeError('Word 导入已取消')
                            job['receipt']=receipt
                            record=project/'word-recognition.json'
                            job['review']=json.loads(record.read_text('utf8')).get('review',[]) if record.is_file() else []
                            job['files']={p.relative_to(project).as_posix():digest(p.read_bytes()) for p in project.rglob('*') if p.is_file()}
                            job['state']='ready'
                        break
                    else:raise ValueError('Word 组件响应协议无效')
        except Exception as error:
            with self.guard:job['state']='error';job['error']=str(error) or type(error).__name__
        finally:
            if timer:timer.cancel()
            if process:
                if process.poll() is None:self._stop(job)
                process.wait(timeout=5)
                for stream in (process.stdin,process.stdout):
                    if stream:stream.close()
            self.exporter.running.release()

    def step(self,token,seq=None,result=None):
        with self.guard:
            job=self._get(token)
            if (seq is None)!=(result is None):raise ValueError('Word 导入响应必须绑定当前序号')
            if seq is not None:
                pending=job['pending']
                if job['state']!='page' or not pending or type(seq) is not int or pending['seq']!=seq or job['answer'] is not None:
                    raise ValueError('Word 导入页面响应已过期或重复')
                if not isinstance(result,list) or len(result)!=len(pending['items']) or any(not isinstance(v,str) for v in result) or len(json.dumps(result).encode('utf8'))>MAX_WIRE_BYTES:
                    raise ValueError('Word 导入页面序列化结果无效')
                job['answer']=result;job['state']='working';job['wake'].set()
                return {'state':'working'}
            value={'state':job['state']}
            if job['state']=='page':value['request']=job['pending']
            elif job['state']=='error':value['error']=job['error']
            elif job['state']=='ready':value.update(receipt=job['receipt'],filename=job['source'].name,review=job['review'])
            return value

    def commit(self,token,target,register):
        with self.guard:
            job=self._get(token)
            if job['state']!='ready':raise ValueError('Word 导入尚未完成，不能建立工程')
            _,raw,mapping=selected_source(job['source'])
            if digest(raw)!=job['sha256'] or (digest(mapping) if mapping is not None else None)!=job['mapping_sha256']:
                raise RuntimeError('所选 Word 或来源映射已变化，请重新导入；当前文稿保持')
            project=Path(job['temporary'].name)/'project'
            if {p.relative_to(project).as_posix():digest(p.read_bytes()) for p in project.rglob('*') if p.is_file()}!=job['files']:
                raise RuntimeError('Word 导入暂存内容已变化，拒绝提交')
            target=Path(target)
            copy_project_tree(project,target)
            # Keep a verified standalone project if registering fails. Never
            # remove a new user-owned directory to conceal an index error.
            try:document_id=register(target)
            except Exception as error:raise RuntimeError('工程已完整保存到 '+str(target)+'，但登记失败；可用“打开工程”重开。'+str(error)) from error
            receipt=job['receipt']
        self.cancel(token)
        return {'document_id':document_id,'project_path':str(target),'receipt':receipt}

    @staticmethod
    def _stop(job):
        job['cancelled'].set();job['wake'].set()
        process=job.get('process')
        if process and process.poll() is None:
            try:
                if os.name=='nt':
                    # Kill only this owned child tree, including a Pandoc that
                    # is converting when the user cancels. No process-name kill.
                    subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],
                        capture_output=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                else:os.killpg(process.pid,signal.SIGKILL)
                if process.poll() is None:process.kill()
            except (OSError,subprocess.TimeoutExpired):
                try:process.kill()
                except OSError:pass

    def cancel(self,token):
        with self.guard:job=self.jobs.pop(token,None)
        if not job:return
        job['expiry'].cancel()
        self._stop(job);job['thread'].join(timeout=6)
        if job['thread'].is_alive():raise RuntimeError('Word 导入子进程尚未退出，暂存文件保留')
        job['temporary'].cleanup()

    def close(self):
        with self.guard:self.closed=True;tokens=list(self.jobs)
        for token in tokens:self.cancel(token)


def worker(request_path):
    wire=sys.stdout
    def send(value):wire.write(json.dumps(value,ensure_ascii=False)+'\n');wire.flush()
    try:
        req=json.loads(Path(request_path).read_text('utf8'))
        with redirect_stdout(sys.stderr):
            if req['libs']:sys.path.insert(0,req['libs'])
            sys.path.insert(0,req['bridge'])
            from hrs_bridge.runtime import Runtime
            from hrs_bridge import docx_import
            rt=Runtime(Path(req['app']),Path(req['wps']),pandoc=req['pandoc']);rt.pandoc=req['pandoc']
            def page_call(runtime,operation,**arguments):
                if operation!='serialize':raise ValueError('Word 导入仅允许现有页面序列化操作')
                send({'kind':'serialize','items':arguments['items']})
                line=sys.stdin.buffer.readline(MAX_WIRE_BYTES+1)
                if not line or len(line)>MAX_WIRE_BYTES:raise ValueError('Word 导入页面响应中断或超限')
                return json.loads(line)
            docx_import.call=page_call
            receipt=docx_import.convert(rt,Path(req['source']),Path(req['output']))
        send({'kind':'result','ok':True,'receipt':receipt})
    except Exception as error:
        detail=str(error) or type(error).__name__
        if detail.startswith('PANDOC_PATH is required'):
            detail='此 Word 含原生公式，请在导入窗口选择 Pandoc 后重试。'
        elif detail=='Native hyperlink import needs a destination-preserving mapping':
            detail='所选 Word 组件不含超链接导入，请选择本版配套 Word 组件后重试。'
        send({'kind':'result','ok':False,'error':detail})


if __name__=='__main__' and len(sys.argv)==3 and sys.argv[1]=='--worker':worker(sys.argv[2])
