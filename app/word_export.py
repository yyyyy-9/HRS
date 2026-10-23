"""Thin, standard-library HRS UI adapter to the separately installed Bridge/WPS.

Native-selected paths stay on the server. The child delegates to the canonical
Bridge/WPS component with embedded Python; the open HRS page supplies its model.
No duplicate parser, style mapping or numbering system lives here.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from project_workspace import is_link


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def runtime_paths(root,app=None):
    root=Path(root).resolve()
    if (root/'word_support/MANIFEST.json').is_file():root=root/'word_support'
    if (root/'MANIFEST.json').is_file():
        info=json.loads((root/'MANIFEST.json').read_text('utf8'))
        if not isinstance(info,dict):raise ValueError('组件清单格式无效')
        if info.get('schema')=='hrs-word-support-v1':
            if info.get('python')!='3.13' or info.get('platform')!='win_amd64':raise ValueError('Word 组件的 Python 版本不匹配')
            if sys.version_info[:2]!=(3,13) and not os.environ.get('HRS_WORD_PYTHON'):
                raise ValueError('本组件用于 HRS 便携版自带的 Python 3.13；当前 Full 请使用自身配套环境')
            python=Path(os.environ.get('HRS_WORD_PYTHON') or sys.executable)
            if python.name.lower()=='pythonw.exe':python=python.with_name('python.exe')
            paths={'root':root,'python':python,'bridge':root/'bridge','wps':root/'wps','libs':root/'libs',
                   'kind':'standalone','pandoc':None,'browser':None,'node':None}
            required=[python,paths['bridge']/'hrs_bridge/browser_model.js',paths['wps']/'config.json',
                      paths['libs']/'docx/__init__.py',paths['libs']/'PIL/Image.py']
            if not all(p.is_file() for p in required):raise ValueError('独立 Word 组件不完整，请重新解压完整便携包')
            if app is not None and sha((Path(app)/'web/bridge_model.js').read_bytes())!=info['browser_model_sha256']:
                raise ValueError('Word 组件与当前 HRS 的模型版本不匹配，请使用同版组件')
            return paths
    paths={'root':root,'python':root/'environment/python-bridge/python.exe',
           'bridge':root/'projects/hrs-wps-bridge','wps':root/'projects/WPS_Document_Tool',
           'node':root/'environment/node/node.exe','browser':root/'environment/browser/chrome-win/chrome.exe',
           'pandoc':root/'environment/pandoc/pandoc.exe','libs':None,'kind':'full'}
    required=[paths['python'],paths['bridge']/'hrs_bridge/docx_export.py',paths['wps']/'config.json',
              paths['wps']/'src/wps_pipeline/figure_layout.py',paths['bridge']/'hrs_bridge/browser_model.js']
    if not all(p.is_file() for p in required):
        raise ValueError('请选择与当前页面模型匹配的独立 Word 组件或配套 Full 根目录')
    if app is not None and (paths['bridge']/'hrs_bridge/browser_model.js').read_bytes()!=(Path(app)/'web/bridge_model.js').read_bytes():
        raise ValueError('Full 与当前 HRS 的 Word 模型版本不匹配')
    return paths


def check_template(path):
    path=Path(path)
    if path.suffix.lower()!='.docx' or is_link(path) or not path.is_file():
        raise ValueError('请选择本机已有的 .docx 母模板')
    if path.stat().st_size>64*1024*1024:raise ValueError('母模板超过 64 MiB')
    try:
        with zipfile.ZipFile(path) as archive:
            if not {'word/document.xml','word/styles.xml'}<=set(archive.namelist()):raise ValueError()
    except (ValueError,zipfile.BadZipFile):raise ValueError('所选文件不是有效的 Word 模板文档') from None
    return path.resolve(),sha(path.read_bytes())


class WordExport:
    def __init__(self,app,workspace):
        self.app=Path(app).resolve();self.config=Path(workspace)/'.word-export-settings.json'
        try:self.settings=json.loads(self.config.read_text(encoding='utf8'))
        except (OSError,ValueError):self.settings={}
        if not isinstance(self.settings,dict):self.settings={}
        self.selections={};self.results={};self.jobs={};self.guard=threading.RLock();self.running=threading.Lock()

    def _save(self):
        temporary=self.config.with_name(self.config.name+'.'+secrets.token_hex(6)+'.tmp')
        try:
            temporary.write_bytes((json.dumps(self.settings,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
            os.replace(temporary,self.config)
        finally:temporary.unlink(missing_ok=True)

    def runtime(self):
        candidates=[]
        explicit=os.environ.get('HRS_WORD_SUPPORT') or os.environ.get('HRS_WORD_BUNDLE')
        if explicit:candidates.append(Path(explicit))
        if self.settings.get('bundle'):candidates.append(Path(self.settings['bundle']))
        candidates.append(self.app.parent/'word_support')
        for parent in self.app.parents:
            if (parent/'projects/hrs-wps-bridge').is_dir():candidates.append(parent)
            runtime=parent/'integration/runtime'
            if (parent/'PROJECT_STATE.md').is_file() and runtime.is_dir():
                candidates.extend(sorted(runtime.iterdir(),key=lambda p:p.name,reverse=True))
        for root in candidates:
            try:return runtime_paths(root,self.app)
            except (ValueError,OSError):continue
        return None

    def pandoc(self,rt):
        choices=[os.environ.get('HRS_WORD_PANDOC'),self.settings.get('pandoc'),
                 self.app.parent/'word_formula/pandoc.exe',rt.get('pandoc') if rt else None]
        for value in choices:
            if value and Path(value).is_file():return Path(value).resolve()
        return None

    def select_formula(self,path):
        path=Path(path)
        if path.name.lower()!='pandoc.exe' or is_link(path) or not path.is_file():raise ValueError('请选择已有的 pandoc.exe')
        with path.open('rb') as stream:
            if stream.read(2)!=b'MZ':raise ValueError('所选文件不是 Windows 公式转换器')
        with self.guard:self.settings['pandoc']=str(path.resolve());self._save()

    def describe(self,key):
        with self.guard:
            self.expire()
            rt=self.runtime();selected=self.settings.get('templates',{}).get(key)
            missing=bool(selected and not Path(selected).is_file())
            default=None
            if rt:
                config=json.loads((rt['wps']/'config.json').read_text(encoding='utf-8-sig'))
                default=str(rt['wps']/config.get('template','templates/target_template.docx'))
            managed=self.settings.get('default_template',{}).get('path')
            if not selected and managed and not Path(managed).is_file():missing=True
            return {'available':bool(rt),'bundle':str(rt['root']) if rt else None,
                    'template':selected or managed or default,'template_choice':'saved' if selected else 'managed' if managed else 'default',
                    'template_missing':missing,'default_template':default,
                    'managed_default_template':managed,'word_options':self.settings.get('word_options',{'notes_mode':'footnotes','preserve_emphasis':False}),
                    'runtime_kind':rt['kind'] if rt else None,'formula_available':bool(self.pandoc(rt))}

    def select_bundle(self,root):
        rt=runtime_paths(root,self.app)
        with self.guard:
            self.settings['bundle']=str(rt['root']);self._save()

    def select_template(self,key,path):
        path,digest=check_template(path)
        with self.guard:
            now=time.monotonic()
            self.selections={t:v for t,v in self.selections.items() if now-v['at']<1800}
            token=secrets.token_hex(24)
            self.selections[token]={'key':key,'path':path,'sha256':digest,'at':now}
            return {'template':str(path),'template_token':token,'template_sha256':digest}

    def template(self,key,choice):
        with self.guard:
            if not isinstance(choice,str):raise ValueError('模板选择无效，请重新选择')
            if choice=='default':return None,None
            if choice=='managed':
                value=self.settings.get('default_template',{})
                if not value.get('path'):raise ValueError('尚未设置自选默认模板')
                path,digest=check_template(value['path'])
                if digest!=value.get('sha256'):raise ValueError('软件保管的默认模板已改变，请重新选择并设为默认')
                return path,digest
            if choice=='saved':
                value=self.settings.get('templates',{}).get(key)
                if not value:raise ValueError('本工程没有已记住的 Word 模板，请重新选择')
                if value==self.settings.get('default_template',{}).get('path'):return self.template(key,'managed')
                return check_template(value)
            selected=self.selections.get(choice)
            if not selected or selected['key']!=key or time.monotonic()-selected['at']>=1800:
                raise ValueError('模板选择已过期或不属于本工程，请重新选择')
            path,digest=check_template(selected['path'])
            if digest!=selected['sha256']:raise RuntimeError('母模板在选择后已经改变，请重新选择并导出')
            return path,digest

    def set_default(self,key,choice):
        path,digest=self.template(key,choice)
        if choice=='managed':return {'template':str(path),'template_token':'managed','managed_default_template':str(path),'template_sha256':digest}
        if path is None:
            original=self.describe(key)['default_template']
            if not original:raise ValueError('程序原始模板尚未安装')
            path,digest=check_template(original)
        with tempfile.TemporaryDirectory(prefix='template-check-',dir=self.config.parent) as temp:
            self._worker(Path(temp)/'snapshot',path,digest,False,action='inspect-template')
        raw=path.read_bytes()
        if sha(raw)!=digest:raise ValueError('模板在检查期间改变，请重新选择')
        directory=self.config.parent/'word-templates'
        if is_link(directory):raise ValueError('默认模板目录不能指向链接')
        directory.mkdir(exist_ok=True)
        target=directory/(path.stem[:45]+'_'+digest[:16]+'.docx')
        if is_link(target):raise ValueError('默认模板文件不能指向链接')
        if target.exists():
            if sha(target.read_bytes())!=digest:raise ValueError('已保管的同名模板内容改变，请先检查模板文件')
        else:
            try:
                with target.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            except Exception:target.unlink(missing_ok=True);raise
        with self.guard:
            previous=dict(self.settings)
            self.settings['default_template']={'path':str(target.resolve()),'sha256':digest}
            self.settings['templates']={**self.settings.get('templates',{}),key:str(target.resolve())}
            try:self._save()
            except Exception:self.settings=previous;raise
        return {'template':str(target),'template_token':'managed','managed_default_template':str(target),'template_sha256':digest}

    def remember(self,key,template,options=None):
        with self.guard:
            templates=self.settings.setdefault('templates',{})
            if template:templates[key]=str(template)
            else:templates.pop(key,None)
            if options is not None:self.settings['word_options']=options
            self._save()

    def _worker(self,snapshot,template,template_sha256,accept,*,action,output=None,model=None,options=None):
        rt=self.runtime()
        if rt is None:raise ValueError('Word 基础组件未找到，请使用带 Word 组件的完整便携版，或选择当前配套 Full')
        request={'app':str(self.app),'bridge':str(rt['bridge']),'wps':str(rt['wps']),
                 'libs':str(rt['libs']) if rt['libs'] else None,'pandoc':str(self.pandoc(rt)) if self.pandoc(rt) else None,
                 'source':str(snapshot),'output':str(output) if output else None,'template':str(template) if template else None,
                 'template_sha256':template_sha256,'accept_numbered_headings':accept,'action':action,'model':model,'word_options':options}
        request_path=Path(snapshot).parent/(action+'-request.json');result_path=Path(snapshot).parent/(action+'-result.json')
        request_path.write_bytes(json.dumps(request,ensure_ascii=False).encode('utf8'))
        # Embedded Python ignores PYTHONPATH: the worker inserts only the declared
        # source roots. No shell command or installed system interpreter is used.
        try:
            completed=subprocess.run([str(rt['python']),'-X','utf8','-B',str(self.app/'word_export.py'),
                                      '--worker',str(request_path),str(result_path)],
                                     cwd=rt['root'],capture_output=True,timeout=180,
                                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired:
            raise RuntimeError('Word 导出超过 180 秒；本次输出未确认，请检查 output/ 后重试') from None
        if not result_path.is_file():
            detail=completed.stderr.decode('utf8',errors='replace')[-1800:]
            raise RuntimeError('配套 Word 运行环境启动失败：'+detail)
        result=json.loads(result_path.read_text(encoding='utf8'))
        if not result.get('ok'):raise ValueError(result.get('error','Word 导出失败'))
        if completed.returncode:raise RuntimeError('Word 子进程退出异常，输出未确认')
        return result['receipt']

    def expire(self):
        with self.guard:
            stale=[token for token,job in self.jobs.items() if time.monotonic()-job['at']>300]
            for token in stale:self.jobs.pop(token)['temporary'].cleanup()

    def clipboard_math(self,items):
        if not isinstance(items,list) or not 1<=len(items)<=100:raise ValueError('粘贴公式数量无效')
        from clipboard_math import xml
        for item in items:
            if not isinstance(item,dict) or set(item)!={'format','source'} or item['format'] not in ('omml','mathml') or not isinstance(item['source'],str):raise ValueError('公式转换请求无效')
            root=xml(item['source'].encode('utf8'))
            local=root.tag.rsplit('}',1)[-1]
            if local not in ('oMath','oMathPara','math'):raise ValueError('公式根节点无效')
            if any(n.tag.rsplit('}',1)[-1] in ('script','img','iframe','object','annotation-xml') for n in root.iter()):raise ValueError('公式含不支持的外部内容')
        if sum(len(item['source']) for item in items)>2_000_000:raise ValueError('公式数据超过限制')
        with tempfile.TemporaryDirectory(prefix='clipboard-math-',dir=self.config.parent) as folder:
            return self._worker(Path(folder)/'snapshot',None,None,False,action='clipboard-math',model=items)

    def prepare(self,key,temporary,request,freeze,template,template_sha):
        snapshot=Path(temporary.name)/'snapshot'
        try:
            model_request=self._worker(snapshot,template,template_sha,request.get('accept_numbered_headings') is True,action='prepare',options=request.get('word_options'))
            with self.guard:
                self.expire()
                if len(self.jobs)>=4:raise RuntimeError('待导出的 Word 快照过多，请关闭其他导出窗口后重试')
                token=secrets.token_hex(24)
                self.jobs[token]={'key':key,'temporary':temporary,'request':request,'freeze':freeze,'template':template,
                                 'template_sha':template_sha,'at':time.monotonic(),'model_request':model_request}
            return {'job_token':token,'model_request':model_request,'formula_available':bool(self.pandoc(self.runtime()))}
        except Exception:temporary.cleanup();raise

    def take(self,key,token):
        with self.guard:
            self.expire();job=self.jobs.get(token)
            if not job or job['key']!=key:raise ValueError('Word 工作快照已过期或不属于本工程，请重新生成')
            return self.jobs.pop(token)

    def discard(self,key,token):
        with self.guard:
            job=self.jobs.get(token)
            if job and job['key']==key:self.jobs.pop(token)['temporary'].cleanup()

    def convert(self,job,output,model):
        return self._worker(Path(job['temporary'].name)/'snapshot',job['template'],job['template_sha'],
                            job['request'].get('accept_numbered_headings') is True,action='convert',output=output,model=model,options=job['request'].get('word_options'))

    def result(self,path):
        with self.guard:
            now=time.monotonic();self.results={t:v for t,v in self.results.items() if now-v[1]<86400}
            token=secrets.token_hex(24);self.results[token]=(Path(path),now)
            return token

    def open_result(self,token,folder=False):
        with self.guard:
            item=self.results.get(token)
            if not item or time.monotonic()-item[1]>=86400 or not item[0].is_file():
                raise ValueError('导出文件已经移动或本次打开凭据已过期')
            path=item[0].parent if folder else item[0]
        if os.name!='nt':raise ValueError('自动打开 Word／文件夹目前仅支持 Windows')
        os.startfile(str(path))


def worker(request_path,result_path):
    try:
        req=json.loads(Path(request_path).read_text(encoding='utf8'))
        if req.get('libs'):sys.path.insert(0,req['libs'])
        sys.path.insert(0,req['bridge'])
        from hrs_bridge.runtime import Runtime
        from hrs_bridge.docx_export import convert,prepare
        if req['template'] and sha(Path(req['template']).read_bytes())!=req['template_sha256']:
            raise ValueError('母模板在导出前已改变，请重新选择')
        rt=Runtime(Path(req['app']),Path(req['wps']),pandoc=req['pandoc'])
        # The GUI has an explicit formula selection; an ambient PATH or a test
        # process's PANDOC_PATH must not silently supply another converter.
        rt.pandoc=req['pandoc']
        if req['action']=='clipboard-math':
            from hrs_bridge.math_adapter import MathAdapter
            from lxml import etree as E
            adapter=MathAdapter(rt);items=req['model'];receipt=[None]*len(items)
            for kind in ('omml','mathml'):
                selected=[(i,x['source']) for i,x in enumerate(items) if x['format']==kind]
                if not selected:continue
                values=adapter.tex_many([E.fromstring(x.encode('utf8'),E.XMLParser(resolve_entities=False,no_network=True)) for _,x in selected]) if kind=='omml' else adapter.mathml_many([x for _,x in selected])
                for (i,_),value in zip(selected,values):receipt[i]=value
        elif req['action']=='inspect-template':
            from wps_pipeline.resolve_styles import inspect_template
            receipt=inspect_template(req['template'])
        elif req['action']=='prepare':
            receipt=prepare(rt,Path(req['source']),template=req['template'],accept_numbered_headings=req['accept_numbered_headings'],options=req.get('word_options'))
        else:
            if req.get('model') is None:raise ValueError('Word 导出缺少本次页面解析结果，请重新生成')
            receipt=convert(rt,Path(req['source']),Path(req['output']),template=req['template'],
                            accept_numbered_headings=req['accept_numbered_headings'],model=req['model'],options=req.get('word_options'))
        result={'ok':True,'receipt':receipt}
    except Exception as error:
        result={'ok':False,'error':str(error) or type(error).__name__}
    Path(result_path).write_bytes(json.dumps(result,ensure_ascii=False).encode('utf8'))


if __name__=='__main__' and len(sys.argv)==4 and sys.argv[1]=='--worker':
    worker(sys.argv[2],sys.argv[3])
