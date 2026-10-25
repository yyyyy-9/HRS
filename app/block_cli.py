"""Snapshot-bound block plan/apply over report_contract and agent_readonly.

Plan is read-only. Only the explicit apply command commits report.md, through
the same lock, backup and atomic replacement used by the editor.
"""
from __future__ import annotations
import argparse,base64,difflib,hashlib,json,re,sys
from pathlib import Path
from report_contract import analyze
from agent_readonly import project
from project_workspace import is_link
from project_commit import report_lock,commit_report_locked
from asset_paths import asset_file

SCHEMA='hrs-block-plan-v1'

class BlockCommandError(ValueError):pass
def sha(raw):return hashlib.sha256(raw).hexdigest()

def source_path(source):
    source=Path(source)
    if source.is_dir():source=source/'report.md'
    if is_link(source) or is_link(source.parent):raise BlockCommandError('Source must be a regular project file')
    return source.resolve(strict=True)

def resource_snapshot(folder,resources):
    from studio import check_image,clean_asset_name
    root=folder/'assets';result={}
    if is_link(root):raise BlockCommandError('Assets directory may not be a link')
    for resource in sorted(set(resources)):
        if not resource.startswith('assets/'):raise BlockCommandError('Invalid asset path')
        name=clean_asset_name(resource[7:]);path=asset_file(root,name)
        if is_link(path) or not path.is_file():raise BlockCommandError('MISSING_ASSET: '+resource)
        data=path.read_bytes();check_image(path.suffix.lower(),data)
        result[resource]=sha(data)
    return result

def plan(source,expected,replacement,*,object_id=None,index=None,operation='replace'):
    source=source_path(source);raw=source.read_bytes();text=raw.decode('utf8')
    if not expected:raise BlockCommandError('MISSING_SNAPSHOT_PRECONDITION')
    if expected!=sha(raw):raise BlockCommandError('STALE_SNAPSHOT')
    if not isinstance(replacement,str) or len(replacement.encode('utf8'))>10*1024*1024:raise BlockCommandError('Replacement must be UTF-8 text up to 10 MiB')
    if (object_id is None)==(index is None):raise BlockCommandError('Select one stable ID or snapshot-local index')
    ir=analyze(text,assets=source.parent/'assets')
    found=project(ir,'get' if object_id is not None else 'get-block',object_id=object_id,block_index=index,expected_sha256=expected)
    if not found.get('found'):raise BlockCommandError(found['lookupStatus'])
    block=found['block'];a,b=block['start'],block['end']
    if operation=='insert-before':b=a
    elif operation=='insert-after':a=b
    elif operation!='replace':raise BlockCommandError('Unsupported candidate operation')
    utf16=text.encode('utf-16-le');prefix=utf16[:a*2].decode('utf-16-le');suffix=utf16[b*2:].decode('utf-16-le')
    candidate=(prefix+replacement+suffix).encode('utf8')
    if len(candidate)>10*1024*1024:raise BlockCommandError('Candidate exceeds the existing 10 MiB source limit')
    after=analyze(candidate.decode('utf8'),assets=source.parent/'assets')
    if not project(after)['sourceContractValid']:
        raise BlockCommandError('Candidate rejected: '+','.join(d['code'] for d in after['diagnostics']))
    assets=resource_snapshot(source.parent,ir['assets']+after['assets'])
    if source.read_bytes()!=raw:raise BlockCommandError('STALE_SNAPSHOT')
    diff=''.join(difflib.unified_diff(text.splitlines(True),candidate.decode('utf8').splitlines(True),fromfile='report.md',tofile='candidate.md'))
    replacement_raw=replacement.encode('utf8')
    return {'schema':SCHEMA,'source':str(source),'ok':True,'operation':'dry-run:'+operation,
        'source_sha256':sha(raw),'candidate_sha256':sha(candidate),
        'target':{'id':object_id,'index':index,'offset_unit':'utf16','start':a,'end':b},
        'unchanged_prefix_sha256':sha(prefix.encode('utf8')),'unchanged_suffix_sha256':sha(suffix.encode('utf8')),
        'replacement_b64':base64.b64encode(replacement_raw).decode('ascii'),'replacement_sha256':sha(replacement_raw),
        'asset_hashes':assets,'original_unchanged':True,'diagnostics':after['diagnostics'],'diff':diff},candidate

def write_plan(output,result,candidate,*,candidate_path=None):
    output=Path(output).resolve();candidate_path=Path(candidate_path).resolve() if candidate_path else output.with_suffix('.candidate.md')
    if output==candidate_path or output.exists() or candidate_path.exists():raise BlockCommandError('Plan and candidate outputs must be new paths')
    if candidate_path.parent!=output.parent:raise BlockCommandError('Keep the plan and its candidate in the same directory')
    output.parent.mkdir(parents=True,exist_ok=True)
    if result.get('schema')!=SCHEMA or sha(candidate)!=result['candidate_sha256']:raise BlockCommandError('Invalid plan candidate')
    payload={**result,'candidate':candidate_path.name};body=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode('utf8')
    created=[]
    try:
        for path,data in ((candidate_path,candidate),(output,body)):
            with path.open('xb') as stream:created.append(path);stream.write(data)
    except Exception:
        for path in created:path.unlink()
        raise
    return {'ok':True,'operation':'plan','plan':str(output),'plan_sha256':sha(body),'candidate':str(candidate_path),
        'source_sha256':result['source_sha256'],'candidate_sha256':sha(candidate),'original_unchanged':True,'diff':result['diff']}

def apply_plan(plan_path,expected_plan_sha256):
    path=Path(plan_path).resolve(strict=True);body=path.read_bytes()
    if not expected_plan_sha256 or sha(body)!=expected_plan_sha256:raise BlockCommandError('PLAN_CHANGED: use the reviewed plan SHA-256')
    data=json.loads(body.decode('utf8'))
    if data.get('schema')!=SCHEMA:raise BlockCommandError('Unsupported block plan schema')
    source=source_path(data['source'])
    if source.name!='report.md':raise BlockCommandError('Apply only accepts an HRS project report.md')
    filename=data.get('candidate')
    if not isinstance(filename,str) or Path(filename).name!=filename or '/' in filename or '\\' in filename:raise BlockCommandError('Invalid candidate filename')
    candidate_file=path.parent/filename
    if is_link(candidate_file):raise BlockCommandError('Candidate must be a regular file')
    candidate=candidate_file.read_bytes()
    if sha(candidate)!=data['candidate_sha256']:raise BlockCommandError('CANDIDATE_CHANGED')
    replacement=base64.b64decode(data['replacement_b64'],validate=True)
    if sha(replacement)!=data['replacement_sha256']:raise BlockCommandError('PLAN_SCOPE_CHANGED: replacement changed')
    with report_lock(source.parent):
        # Re-locate using current IR, not the old coordinates in the JSON.
        target=data['target'];operation=data['operation'].removeprefix('dry-run:')
        verified,rebuilt=plan(source,data['source_sha256'],replacement.decode('utf8'),object_id=target['id'],index=target['index'],operation=operation)
        if data.get('asset_hashes')!=verified['asset_hashes']:raise BlockCommandError('ASSET_CHANGED: referenced resources changed after planning')
        if any(data.get(key)!=value for key,value in verified.items()) or rebuilt!=candidate:
            raise BlockCommandError('PLAN_SCOPE_CHANGED: candidate is not the declared block edit')
        # Recheck the artifact after reading resources, before the original commit.
        if path.read_bytes()!=body or candidate_file.read_bytes()!=candidate:raise BlockCommandError('PLAN_CHANGED during apply')
        backup=commit_report_locked(source.parent,candidate,data['source_sha256'])
    return {'ok':True,'operation':'apply','source':str(source),'source_sha256':sha(candidate),
        'previous_sha256':data['source_sha256'],'backup':str(backup) if backup else None,'updated':backup is not None,
        'target':verified['target'],'outside_range_unchanged':True,'assets_written':0,'conversion_model_api_calls':0}

def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf8')
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('plan');p.add_argument('source',type=Path)
    target=p.add_mutually_exclusive_group(required=True);target.add_argument('--id');target.add_argument('--index',type=int)
    p.add_argument('--expect-sha256',required=True);p.add_argument('--text-file',type=Path,required=True)
    p.add_argument('--operation',choices=('replace','insert-before','insert-after'),default='replace');p.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('apply');a.add_argument('plan',type=Path);a.add_argument('--expect-plan-sha256',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='plan':
            result,candidate=plan(args.source,args.expect_sha256,args.text_file.read_bytes().decode('utf8'),object_id=args.id,index=args.index,operation=args.operation)
            result=write_plan(args.output,result,candidate)
        else:result=apply_plan(args.plan,args.expect_plan_sha256)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(json.dumps({'ok':False,'operation':args.command,'error':str(error)},ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
