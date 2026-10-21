"""A0 read-only, local Agent interface for HTML Report Studio.

This is not an HTTP RPC, mutation API, autonomous editor, or DOCX compiler.
All commands write JSON to stdout only; source and assets are never modified.
Usage: python agent_readonly.py objects /path/to/report.md
       python agent_readonly.py get /path/to/project --id tbl-example
       python agent_readonly.py outline /path/to/report.md
       python agent_readonly.py get-block /path/to/report.md --index 0 --expect-sha256 <outline snapshot text_utf8_sha256>
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

from report_contract import analyze

VERSION = 'hrs-agent-read-v1'
BLOCKED_DIAGNOSTICS = {'UNSUPPORTED_OBJECT_FIELDS'}


def project(ir: dict, action: str = 'summary', object_id: str | None = None,
            block_index: int | None = None, expected_sha256: str | None = None) -> dict:
    """Expose a stable JSON projection, preserving snapshot and error state."""
    safe = ir['ok'] and not any(d['code'] in BLOCKED_DIAGNOSTICS for d in ir['diagnostics'])
    base = {
        'schema': VERSION,
        'source_format': ir['source_format'],
        'offset_unit': ir['offset_unit'],
        'snapshot': ir['source_snapshot'],
        'ok': ir['ok'],
        'sourceContractValid': safe,
        'safeToCompile': False,
        'preflight': {'scope':'source-contract', 'complete':False, 'next':'hrs check SOURCE --render-profile engineering'},
        'errors': [d for d in ir['diagnostics'] if d['severity'] == 'error'],
        'warnings': [d for d in ir['diagnostics'] if d['severity'] != 'error'],
    }
    if action == 'summary':
        base.update({'stats': ir['stats'], 'objectCount': len(ir['objects']['entries']),
                     'referenceCount': len(ir['references'])})
    elif action == 'objects':
        base['objects'] = ir['objects']['entries']
    elif action == 'references':
        base['references'] = ir['references']
    elif action == 'diagnostics':
        base['diagnostics'] = ir['diagnostics']
    elif action == 'outline':
        # Even without a persistent object ID, equation/heading/table blocks
        # can be inspected by snapshot-scoped UTF-16 source ranges. Indices
        # MUST NOT be treated as stable identifiers after a document edit.
        base['blocks'] = [
            {'index': i, 'type': block['type'], 'line': block['line'],
             'start': block['start'], 'end': block['end'],
             'id': block.get('id'), 'numbered': block.get('numbered', False),
             **({'level': block['level']} if 'level' in block else {}),
             **({'sourceKind': block['sourceKind']} if 'sourceKind' in block else {}),
             **({'delimiter': block['delimiter']} if 'delimiter' in block else {})}
            for i, block in enumerate(ir['blocks'])]
    elif action == 'get-block':
        # Indices are not identities. Do not ever disclose a new block to a
        # caller holding an index from another document revision.
        current = ir['source_snapshot']['text_utf8_sha256']
        if expected_sha256 is None:
            base.update({'ok': False, 'found': False, 'index': block_index,
                         'lookupStatus':'MISSING_SNAPSHOT_PRECONDITION'})
        elif expected_sha256 != current:
            base.update({'ok': False, 'found': False, 'index': block_index,
                         'lookupStatus':'STALE_SNAPSHOT'})
        elif block_index is None or block_index < 0 or block_index >= len(ir['blocks']):
            base.update({'found': False, 'index': block_index, 'lookupStatus':'NOT_FOUND'})
        else:
            base.update({'found': True, 'index': block_index,
                         'lookupStatus':'FOUND', 'block': ir['blocks'][block_index]})
        if base['lookupStatus'] in ('MISSING_SNAPSHOT_PRECONDITION','STALE_SNAPSHOT'):
            base['safeToCompile'] = False
            base['errors'].append({'severity':'error','code':base['lookupStatus'],
                                   'message':'临时块索引要求匹配 outline 返回的文稿 SHA-256'})
    elif action == 'get':
        matches = [b for b in ir['blocks'] if b.get('id') == object_id]
        entries = [e for e in ir['objects']['entries'] if e['id'] == object_id]
        if len(matches) > 1 or len(entries) > 1:
            base.update({'ok':False,'safeToCompile':False, 'found':False,
                         'ambiguous':True,'lookupStatus':'AMBIGUOUS_ID','id':object_id})
            if not any(e['code']=='DUPLICATE_ID' for e in base['errors']):
                base['errors'].append({'severity':'error','code':'AMBIGUOUS_ID',
                                      'message':'对象 ID 不是唯一定位键：'+str(object_id)})
        elif len(matches) == 1 and len(entries) == 1:
            base.update({'found':True,'ambiguous':False,'lookupStatus':'FOUND',
                         'object':entries[0],'block':matches[0]})
        else:
            base.update({'found':False,'ambiguous':False,'lookupStatus':'NOT_FOUND','id':object_id})
    else:
        raise ValueError('Unsupported read action')
    return base


def analyze_file(file: Path, *, assets: Path | None = None) -> dict:
    path = file / 'report.md' if file.is_dir() else file
    raw = path.read_bytes()
    # Decode before adding a snapshot, never rewrite/normalize the raw bytes.
    ir = analyze(raw.decode('utf-8'), assets=assets)
    ir['source_snapshot'].update({'file_sha256': hashlib.sha256(raw).hexdigest(),
                                  'file_bytes': len(raw), 'encoding': 'utf-8'})
    return ir


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only object and reference inspection; stdout JSON only')
    parser.add_argument('action', choices=('summary','objects','references','diagnostics','get','outline','get-block'))
    parser.add_argument('source', type=Path, help='UTF-8 report.md or containing project folder')
    parser.add_argument('--id', dest='object_id', help='Stable ID; required with get')
    parser.add_argument('--index', dest='block_index', type=int, help='Snapshot-scoped index; required with get-block')
    parser.add_argument('--expect-sha256', help='Required for get-block: text_utf8_sha256 from outline snapshot')
    parser.add_argument('--check-assets', action='store_true', help='Also verify referenced assets exist')
    args = parser.parse_args(argv)
    if args.action == 'get' and not args.object_id:parser.error('get requires --id')
    if args.action != 'get' and args.object_id:parser.error('--id is only supported for get')
    if args.action == 'get-block' and args.block_index is None:parser.error('get-block requires --index')
    if args.action != 'get-block' and args.block_index is not None:parser.error('--index is only supported for get-block')
    if args.action != 'get-block' and args.expect_sha256 is not None:parser.error('--expect-sha256 is only supported for get-block')
    if args.expect_sha256 is not None and (len(args.expect_sha256)!=64 or any(c not in '0123456789abcdef' for c in args.expect_sha256)):
        parser.error('--expect-sha256 requires a lowercase SHA-256 digest')
    path = args.source / 'report.md' if args.source.is_dir() else args.source
    try:
        ir = analyze_file(path, assets=path.parent/'assets' if args.check_assets else None)
        result = project(ir, args.action, args.object_id, args.block_index, args.expect_sha256)
    except (OSError, UnicodeError, ValueError) as exc:
        result = {'schema': VERSION, 'ok': False, 'safeToCompile': False,
                  'errors': [{'severity':'error', 'code':'SOURCE_UNREADABLE', 'message':str(exc)}],
                  'warnings': []}
    print(json.dumps(result, ensure_ascii=False, separators=(',',':')))
    return 0 if result['ok'] and result.get('found',True) else 1


if __name__ == '__main__':raise SystemExit(main())
