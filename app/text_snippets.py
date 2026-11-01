"""User-owned declarative Markdown snippets; no executable template language."""
import hashlib,json,re
from project_workspace import is_link

def read(workspace):
    path=workspace/'.text-snippets.json'
    if is_link(path):raise ValueError('片段设置不能是链接')
    raw=path.read_bytes() if path.exists() else b''
    if len(raw)>2*1024*1024:raise ValueError('片段设置过大')
    data=json.loads(raw) if raw else {'snippets':[]}
    return {'ok':True,'revision':hashlib.sha256(raw).hexdigest(),'snippets':validate(data.get('snippets'))}

def validate(items):
    if not isinstance(items,list) or len(items)>100:raise ValueError('最多保存100个片段')
    seen=set()
    for item in items:
        if not isinstance(item,dict) or set(item)!={'id','title','text'}:raise ValueError('片段字段必须为id/title/text')
        if not isinstance(item['id'],str) or not re.fullmatch(r'[a-z0-9-]{1,64}',item['id']) or item['id'] in seen:raise ValueError('片段身份重复或无效')
        seen.add(item['id'])
        if not isinstance(item['title'],str) or not item['title'].strip() or len(item['title'])>80:raise ValueError('片段名称为1—80字')
        if not isinstance(item['text'],str) or len(item['text'].encode('utf8'))>64*1024:raise ValueError('单片段最多64KiB')
    return items

def write(workspace,items,revision):
    from studio import atomic_write
    current=read(workspace)
    if current['revision']!=revision:raise ValueError('片段已在其他窗口修改，请重新打开')
    raw=(json.dumps({'snippets':validate(items)},ensure_ascii=False,indent=2)+'\n').encode('utf8')
    if len(raw)>2*1024*1024:raise ValueError('片段设置过大')
    atomic_write(workspace/'.text-snippets.json',raw)
    return read(workspace)
