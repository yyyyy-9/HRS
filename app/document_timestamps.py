"""Optional presentation metadata over the existing IR, never Markdown content.

Dates describe observed edits, not an audit trail. Unknown pre-existing dates
stay null. IDs here identify metadata only; author object IDs remain unchanged.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import uuid

from file_io import digest, write_json
from project_workspace import is_link
from report_contract import analyze
from section_operations import sections

SCHEMA='hrs-block-times-v1'
KINDS={'heading','figure','image-group','table','mermaid'}
MAX_RECORDS=20000


def _hash(text):return digest(text.encode('utf-8'))


def _date(value):
    if value is None:return None
    if not isinstance(value,str) or len(value)>32:raise ValueError('时间信息日期无效')
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('时间信息缺少时区')
    return parsed.astimezone(timezone.utc).isoformat(timespec='minutes')


def validate(value):
    """Validate optional transport/archive metadata without trusting HTML."""
    if value is None:return None
    if not isinstance(value,dict) or value.get('schema')!=SCHEMA:raise ValueError('时间信息格式无效')
    sha=value.get('source_sha256');items=value.get('records')
    if not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('时间信息源摘要无效')
    if not isinstance(items,list) or len(items)>MAX_RECORDS:raise ValueError('时间信息数量超限')
    records=[];seen=set()
    for item in items:
        if not isinstance(item,dict):raise ValueError('时间信息条目无效')
        key=item.get('key');kind=item.get('kind');start=item.get('start');end=item.get('end')
        if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{32}',key) or key in seen:raise ValueError('时间信息身份无效')
        if kind not in KINDS or type(start) is not int or type(end) is not int or not 0<=start<end<=20*1024*1024:raise ValueError('时间信息范围无效')
        for field in ('own_sha256','content_sha256'):
            if not isinstance(item.get(field),str) or not re.fullmatch('[a-f0-9]{64}',item[field]):raise ValueError('时间信息内容摘要无效')
        oid=item.get('id')
        if oid is not None and (not isinstance(oid,str) or len(oid)>100):raise ValueError('时间信息对象无效')
        created,modified=_date(item.get('created')),_date(item.get('modified'))
        if created and modified and modified<created:raise ValueError('修改时间早于创建时间')
        seen.add(key);records.append({k:item[k] for k in ('key','kind','start','end','own_sha256','content_sha256')})
        records[-1].update(id=oid,created=created,modified=modified)
        if item.get('pending') is True:records[-1]['pending']=True
    return {'schema':SCHEMA,'source_sha256':sha,'records':records}


def describe(text,ir=None):
    ir=ir or analyze(text);raw=text.encode('utf-16-le')
    section_ends={s['start']:s['end'] for s in sections(ir)}
    result=[]
    for block in ir['blocks']:
        kind=block['type']
        if kind not in KINDS:continue
        start,end=block['start'],block['end']
        own=raw[start*2:end*2].decode('utf-16-le')
        content=raw[start*2:section_ends.get(start,end)*2].decode('utf-16-le') if kind=='heading' else own
        result.append({'kind':kind,'id':block.get('id'),'start':start,'end':end,
                       'own_sha256':_hash(own.replace('\r\n','\n')),'content_sha256':_hash(content.replace('\r\n','\n'))})
    if len(result)>MAX_RECORDS:raise ValueError('时间信息数量超限')
    return result


def reconcile(text,previous=None,*,hints=None,fresh=False,observed=True,now=None,ir=None,projection=False):
    """Match stable objects, mapped editor positions, then unchanged sequences.

    CodeMirror hints only attribute an existing key to a new source range;
    dates and semantic hashes are always derived here. No fuzzy title guessing.
    """
    previous=validate(previous);old=(previous or {}).get('records',[]);ir=ir or analyze(text);new=describe(text,ir)
    instant=now or datetime.now(timezone.utc).isoformat(timespec='minutes')
    pairs={};used=set()
    def pair(a,b):
        if a not in used and b not in pairs and old[a]['kind']==new[b]['kind']:
            pairs[b]=old[a];used.add(a)
    old_ids=Counter((r['kind'],r['id']) for r in old if r['id'])
    new_ids=Counter((r['kind'],r['id']) for r in new if r['id'])
    lookup={(r['kind'],r['id']):i for i,r in enumerate(old) if r['id'] and old_ids[r['kind'],r['id']]==1}
    for b,item in enumerate(new):
        key=(item['kind'],item['id'])
        if key in lookup and new_ids[key]==1:pair(lookup[key],b)
    # Hints are bounded, unique keys from the previous owned snapshot. Start
    # association +1 keeps an inserted copy before an original a new object.
    if isinstance(hints,list) and len(hints)<=MAX_RECORDS:
        by_key={r['key']:i for i,r in enumerate(old)}
        by_start={(r['kind'],r['start']):b for b,r in enumerate(new)}
        for h in hints:
            if not isinstance(h,dict) or h.get('key') not in by_key:continue
            if type(h.get('start')) is not int or type(h.get('end')) is not int:continue
            a=by_key[h['key']];b=by_start.get((old[a]['kind'],h.get('start')))
            if b is not None and type(h.get('end')) is int and h['end']>h.get('start',0):pair(a,b)
    signature=lambda r:(r['kind'],r['id'],r['own_sha256'])
    # A unique unchanged heading/table keeps its dates when moved across the
    # sequence. Duplicate text is left to the ordered matcher, never guessed.
    old_signatures=Counter(signature(r) for i,r in enumerate(old) if i not in used)
    new_signatures=Counter(signature(r) for i,r in enumerate(new) if i not in pairs)
    unchanged={signature(r):i for i,r in enumerate(old) if i not in used and old_signatures[signature(r)]==1}
    for b,item in enumerate(new):
        key=signature(item)
        if b not in pairs and key in unchanged and new_signatures[key]==1:pair(unchanged[key],b)
    remaining_old=[i for i in range(len(old)) if i not in used]
    remaining_new=[i for i in range(len(new)) if i not in pairs]
    matcher=SequenceMatcher(None,[signature(old[i]) for i in remaining_old],[signature(new[i]) for i in remaining_new],autojunk=True)
    for a,b,size in matcher.get_matching_blocks():
        for offset in range(size):pair(remaining_old[a+offset],remaining_new[b+offset])
    records=[]
    for b,item in enumerate(new):
        prior=pairs.get(b)
        if prior:
            changed=prior['content_sha256']!=item['content_sha256']
            records.append({**item,'key':prior['key'],'created':prior['created'],
                            'modified':prior['modified'] if projection else max(instant,prior['created'] or instant,prior['modified'] or instant) if changed and observed else None if changed else prior['modified']})
        else:records.append({**item,'key':uuid.uuid4().hex,'created':instant if fresh else None,'modified':instant if fresh else None})
    # Editing JSON/fences can temporarily make a known object invalid. Keep
    # its dates only while that carrier still exists; a real deletion prunes
    # them. No hidden history or source text is kept in project metadata.
    invalid=[b for b in ir['blocks'] if b['type']=='invalid-object']
    mapped={h['key']:h for h in hints or [] if isinstance(h,dict) and isinstance(h.get('key'),str)} if isinstance(hints,list) else {}
    for a,prior in enumerate(old):
        if a in used:continue
        hint=mapped.get(prior['key'],prior);start,end=hint.get('start'),hint.get('end')
        if type(start) is not int or type(end) is not int or end<=start:continue
        carrier=next((b for b in invalid if start<b['end'] and end>b['start']),None)
        if carrier:records.append({**prior,'start':carrier['start'],'end':carrier['end'],'pending':True})
    records.sort(key=lambda r:(r['start'],r['end'],r['key']))
    return {'schema':SCHEMA,'source_sha256':_hash(text),'records':records}


def load(folder,text,*,fresh=False,ir=None):
    value=None
    if folder is not None:
        path=Path(folder)/'meta.json'
        try:
            if not is_link(path):value=json.loads(path.read_text(encoding='utf-8')).get('block_timestamps')
            value=validate(value)
        except (OSError,ValueError,TypeError,AttributeError):value=None
    if value and value['source_sha256']==_hash(text):return value
    return reconcile(text,value,fresh=fresh,observed=False,ir=ir)


def advance(old_text,text,previous=None,*,hints=None,ir=None):
    # Without editor hints, map unchanged lines through a bounded line diff.
    # This covers CLI edits and heading renames without adding source IDs.
    baseline=previous or reconcile(old_text,observed=False)
    if hints is None and old_text!=text:
        before=old_text.splitlines(keepends=True);after=text.splitlines(keepends=True)
        if len(before)+len(after)<=60000:
            def offsets(lines):
                result=[0]
                for line in lines:result.append(result[-1]+len(line.encode('utf-16-le'))//2)
                return result
            aa,bb=offsets(before),offsets(after);positions={}
            for tag,a,z,b,y in SequenceMatcher(None,before,after,autojunk=True).get_opcodes():
                if tag=='equal':
                    for offset in range(z-a):positions[aa[a+offset]]=bb[b+offset]
                elif tag=='replace' and z-a==y-b:
                    for offset in range(z-a):positions[aa[a+offset]]=bb[b+offset]
            hints=[{'key':r['key'],'start':positions[r['start']],'end':positions[r['start']]+r['end']-r['start']}
                   for r in baseline['records'] if r['start'] in positions]
    result=reconcile(text,baseline,hints=hints,observed=True,ir=ir)
    prior_keys={r['key'] for r in baseline['records']};now=datetime.now(timezone.utc).isoformat(timespec='minutes')
    for r in result['records']:
        if r['key'] not in prior_keys:r.update(created=now,modified=now)
    return result


def store(folder,value):
    value=validate(value);path=Path(folder)/'meta.json'
    if is_link(path):raise ValueError('时间信息文件不能是链接')
    try:meta=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    except ValueError:meta={}
    if not isinstance(meta,dict):meta={}
    write_json(path,{**meta,'block_timestamps':value})
