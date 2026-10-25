"""Object clipboard transport over the existing contract and resource graph.

No alternate document model: IDs/ranges come from report_contract. Only actual
object declarations, parsed references and image destinations are rewritten.
"""
from __future__ import annotations
import base64,hashlib,json,re,uuid
from pathlib import Path
from urllib.parse import unquote,urlsplit
from report_contract import analyze,ANY_IMAGE,ASSET
from reference_context import masked_context
from project_workspace import is_link
from asset_paths import normalize_asset, asset_file

FORMAT='hrs-object-clipboard-v1'
MAX_TOTAL=30*1024*1024

def sha(data):return hashlib.sha256(data).hexdigest()
def char_index(text,offset):
    raw=text.encode('utf-16-le');return len(raw[:offset*2].decode('utf-16-le'))

def _fragment(text):
    if not isinstance(text,str) or len(text.encode('utf8'))>10*1024*1024:raise ValueError('剪贴板正文过大或格式无效')
    ir=analyze(text)
    bad=[d for d in ir['diagnostics'] if d['severity']=='error' and d['code'] not in ('MISSING_REFERENCE','EXTERNAL_IMAGE')]
    if bad:raise ValueError('剪贴板对象结构错误：'+bad[0]['message'])
    return ir

def _file(folder,name):
    if folder is None:return None
    path=asset_file(folder,name)
    if is_link(folder) or is_link(path):raise ValueError('剪贴板资源不能是链接文件')
    return path if path.is_file() else None

def _read(name,roots):
    for folder in roots:
        path=_file(folder,name)
        if path:return path.read_bytes()
    raise ValueError('找不到复制对象的附件：assets/'+name)

def local_urls(ir):
    from html_assets import references
    urls=set()
    for block in ir['blocks']:
        if block['type'] in ('code','mermaid','figure','equation') or block['type']=='table' and block.get('sourceKind')!='gfm-pipe':continue
        raw=block['source'];visible=masked_context(raw,mask_images=False)
        urls.update(m[1].split(' "',1)[0] for m in ANY_IMAGE.finditer(visible))
        urls.update(row[0] for row in references(raw))
    return {url for url in urls if normalize_asset(url) not in ir['assets']}

def local_path(folder,url):
    if folder is None or urlsplit(url).scheme or Path(url).is_absolute():return None
    root=Path(folder).resolve();path=(root/unquote(url)).resolve()
    if path.is_relative_to(root) and not is_link(path) and path.is_file():return path
    return None

def copy_bundle(text,roots,source_key,operation='copy',source_folder=None):
    ir=_fragment(text);files={};total=0
    for resource in ir['assets']:
        name=resource.removeprefix('assets/');data=_read(name,roots);total+=len(data)
        if total>MAX_TOTAL:raise ValueError('剪贴板资源总量超过 30 MiB')
        files[name]={'base64':base64.b64encode(data).decode('ascii'),'sha256':sha(data)}
    local={}
    for url in local_urls(ir):
        path=local_path(source_folder,url)
        if path:
            data=path.read_bytes();total+=len(data)
            if total>MAX_TOTAL:raise ValueError('剪贴板资源总量超过 30 MiB')
            local[url]={'base64':base64.b64encode(data).decode('ascii'),'sha256':sha(data)}
    return {'format':FORMAT,'markdown':text,'source_key':source_key,
        'operation':'cut' if operation=='cut' else 'copy','assets':files,'local_images':local}

def _json_fields(raw):
    """Offsets of root JSON values, preserving whitespace and unrelated bytes."""
    decoder=json.JSONDecoder();start=raw.index('{');i=start+1
    while True:
        while raw[i].isspace() or raw[i]==',':i+=1
        if raw[i]=='}':break
        key,end=decoder.raw_decode(raw,i);i=end
        while raw[i].isspace() or raw[i]==':':i+=1
        start=i;value,i=decoder.raw_decode(raw,i)
        yield key,start,i,value

def _patch(text,edits):
    for start,end,value in sorted(edits,reverse=True):text=text[:start]+value+text[end:]
    return text

def rewrite(text,ir,ids,paths):
    edits=[]
    for block in ir['blocks']:
        a=char_index(text,block['start']);b=char_index(text,block['end']);raw=text[a:b];local=[]
        oid=block.get('id');typ=block['type']
        if typ in ('figure','table') and block.get('sourceKind')!='gfm-pipe':
            for key,x,y,value in _json_fields(raw):
                if key=='id' and oid in ids:local.append((x,y,json.dumps(ids[oid])))
                elif key in ('src','sourceAsset','vectorSource','rasterFallback') and value in paths:
                    local.append((x,y,json.dumps(paths[value])))
        else:
            if oid in ids:
                # Anchored declarations only: an occurrence in a title is prose.
                pattern=(r'(?<=#)'+re.escape(oid)+r'\b') if typ=='image-group' else r'(?<=id=")'+re.escape(oid)+r'(?=")'
                if typ=='heading' or block.get('sourceKind')=='gfm-pipe':pattern=r'(?<=#)'+re.escape(oid)+r'\b'
                match=re.search(pattern,raw)
                if not match and typ=='equation':match=re.search(r'\b'+re.escape(oid)+r'\b',raw.split('\n',1)[0])
                if not match:raise ValueError('无法定位对象身份声明：'+oid)
                local.append((match.start(),match.end(),ids[oid]))
            if typ!='code' and typ!='mermaid':
                visible=masked_context(raw,mask_images=False)
                # The existing scanner masks code, mathematics and link targets.
                for match in ANY_IMAGE.finditer(visible):
                    url=raw[match.start(1):match.end(1)].split(' "',1)[0];target=paths.get(url) or paths.get(normalize_asset(url))
                    if target:local.append((match.start(1),match.start(1)+len(url),target))
                if typ=='image-group':
                    for old,new in paths.items():
                        for match in re.finditer(r'(?<==)'+re.escape(old)+r'(?=[\s}])',raw):local.append((match.start(),match.end(),new))
                # Safe HTML images have already been enumerated by report_contract.
                from html_assets import references
                lines=raw.splitlines(keepends=True);prefix=[0]
                for line in lines:prefix.append(prefix[-1]+len(line))
                for url,line,column,length in references(raw):
                    target=paths.get(url) or paths.get(normalize_asset(url))
                    if target:
                        x=prefix[line-1]+column
                        tag=raw[x:x+length]
                        attr=re.search(r'\bsrc\s*=\s*([\"\'])(.*?)\1',tag,re.I|re.S)
                        if attr:local.append((x+attr.start(2),x+attr.end(2),target))
        for ref in ir['references']:
            x=char_index(text,ref['start']);y=char_index(text,ref['end'])
            if ref['target'] in ids and a<=x<y<=b:
                local.append((x-a,y-a,'@'+ref['kind']+':'+ids[ref['target']]))
        if local:edits.append((a,b,_patch(raw,local)))
    return _patch(text,edits)

def paste_bundle(bundle,target_text,roots,target_key,check_image,local_files=None,source_folder=None):
    if not isinstance(bundle,dict) or bundle.get('format')!=FORMAT:raise ValueError('剪贴板格式无效')
    text=bundle.get('markdown');ir=_fragment(text);target=analyze(target_text)
    supplied=bundle.get('assets',{});prepared={};total=0
    if not isinstance(supplied,dict) or len(supplied)>100:raise ValueError('剪贴板附件清单无效')
    for name,record in supplied.items():
        if not ASSET.fullmatch('assets/'+name) and not re.fullmatch(r'[a-f0-9]{16}\.(?:emf|pdf)',name,re.I):raise ValueError('剪贴板附件名无效')
        try:data=base64.b64decode(record['base64'],validate=True)
        except Exception as exc:raise ValueError('剪贴板附件编码无效') from exc
        if sha(data)!=record.get('sha256'):raise ValueError('剪贴板附件摘要不匹配')
        check_image(Path(name).suffix.lower(),data);total+=len(data);prepared[name]=data
    # Plain Markdown copied within a known project can reuse its local assets.
    for resource in ir['assets']:
        name=resource.removeprefix('assets/')
        if name not in prepared:prepared[name]=_read(name,roots)
    paths={};local_files=local_files or {}
    for url in sorted(local_urls(ir)):
        if urlsplit(url).scheme.lower() in ('http','https','data','javascript'):raise ValueError('只导入本地图片，不自动下载外部图片：'+url)
        data=None
        if url in local_files:
            data=base64.b64decode(local_files[url],validate=True)
        elif url in bundle.get('local_images',{}):
            record=bundle['local_images'][url];data=base64.b64decode(record['base64'],validate=True)
            if sha(data)!=record.get('sha256'):raise ValueError('本地图片摘要不匹配')
        elif not bundle.get('source_key') or bundle.get('source_key')==target_key:
            path=local_path(source_folder,url)
            if path:data=path.read_bytes()
        if data is None:raise ValueError('CHOOSE_IMAGE_SOURCE：请选择本地图片来源：'+url)
        ext=Path(url).suffix.lower();check_image(ext,data)
        name=sha(data)[:16]+ext;prepared[name]=data;paths[url]='assets/'+name
    total=sum(map(len,prepared.values()))
    if total>MAX_TOTAL:raise ValueError('剪贴板资源总量超过 30 MiB')
    for name,data in prepared.items():check_image(Path(name).suffix.lower(),data)
    # Keep original/preview basename relationships together when resolving a collision.
    groups={}
    for name in prepared:groups.setdefault(Path(name).with_suffix('').as_posix(),[]).append(name)
    final={}
    for stem,names in groups.items():
        collision=any((path:=_file(root,name)) and path.read_bytes()!=prepared[name] for name in names for root in roots)
        newstem=uuid.uuid4().hex[:16] if collision else stem
        for name in names:
            newname=newstem+Path(name).suffix;final[newname]=prepared[name]
            if newname!=name:paths['assets/'+name]='assets/'+newname
    # Resolve local imports through a collision rename as well.
    paths={old:paths.get(new,new) for old,new in paths.items()}
    preserve=(bundle.get('operation')=='cut' and bundle.get('source_key')==target_key) or (bundle.get('operation')=='import' and not target_text)
    used=set(target['objects']['ids']);ids={}
    for oid in ir['objects']['ids']:
        if preserve and oid not in used:continue
        fresh=oid.split('-',1)[0]+'-'+uuid.uuid4().hex[:12]
        while fresh in used:fresh=oid.split('-',1)[0]+'-'+uuid.uuid4().hex[:12]
        ids[oid]=fresh;used.add(fresh)
    rewritten=rewrite(text,ir,ids,paths)
    checked=_fragment(rewritten)
    if any(d['code']=='EXTERNAL_IMAGE' for d in checked['diagnostics']):raise ValueError('仍有未导入的本地图片')
    return {'markdown':rewritten,'id_map':ids,'asset_map':paths,'assets':final}
