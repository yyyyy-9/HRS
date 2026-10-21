"""Independent reconstruction of scan facts, checked against original XML content."""
import argparse
from collections import Counter
import json
from pathlib import Path
from lxml import etree as E
from .source_inventory import Oracle,digest,tree_value,NS


def verify(source,scan_dir):
    scan_dir=Path(scan_dir);scan=json.loads((scan_dir/'scan.json').read_text(encoding='utf8'));oracle=Oracle(source)
    errors=[];checks=0;visited=set();used_objects=set()
    byid={b['block_id']:b for b in scan['blocks']}
    def check(test,label):
        nonlocal checks
        checks+=1
        if not test:errors.append(label)
    check(len(byid)==len(scan['blocks']),'unique_block_ids')
    check(scan['source_sha256']==digest(Path(source).read_bytes()),'source_hash')
    check(not scan['unsupported'],'no_unreported_scope_exclusions')
    check(all('role' not in b and 'level' not in b for b in scan['blocks']),'scan_is_facts_only')
    def object_data(oid):
        used_objects.add(oid);o=scan['objects'][oid];raw=(scan_dir/o['payload_ref']).read_bytes();node=E.fromstring(raw)
        check(digest(raw)==o['xml_sha256'],f'{oid}:raw_payload')
        check(digest(tree_value(node))==o['structural_sha256'],f'{oid}:tree_fingerprint')
        return o,node
    def block_value(bid,parent=None):
        b=byid[bid];check(bid not in visited,f'{bid}:no_duplicate_traversal');visited.add(bid)
        check(b['container_id']==parent,f'{bid}:container')
        if b['kind']=='paragraph':
            events=[];reading=[];plain=[]
            def add(kind,value):
                if kind=='text' and events and events[-1][0]=='text':events[-1][1]+=value
                else:events.append([kind,value])
            for s in b['segments']:
                kind=s['kind']
                if kind=='text':add('text',s['text']);reading.append(s['text']);plain.append(s['text'])
                elif kind in ('math_inline','math_display'):
                    o,node=object_data(s['object_id']);add(kind,digest(tree_value(node)))
                    check(node.tag.endswith('}oMathPara')==(kind=='math_display'),f'{s["object_id"]}:math_placement')
                    if o['preview_status']=='exact_simple_symbol':
                        allowed={'oMath','oMathPr','r','t','rPr','sty','nor','scr','rFonts','sz','szCs'}
                        check(kind=='math_inline' and all(E.QName(n).localname in allowed for n in node.iter()),f'{s["object_id"]}:exact_preview_scope')
                        preview=''.join(node.xpath('.//m:t/text()',namespaces=NS))
                    else:preview='[数学:'+s['object_id']+']'
                    check(o['preview']==preview,f'{s["object_id"]}:preview');reading.append(preview)
                elif kind=='drawing':
                    o,node=object_data(s['object_id']);media=[]
                    for m in o['media']:
                        actual=digest((scan_dir/m['payload_ref']).read_bytes());check(actual==m['sha256'],f'{s["object_id"]}:media_payload');media.append(actual)
                    add('drawing',{'layout':o['layout'],'media':media,'extent':o['extent']})
                    reading.append('[图片:'+s['object_id']+']')
                elif kind in ('bookmarkStart','bookmarkEnd'):add(kind,s['bookmark_id'])
                elif kind in ('tab','br','cr','noBreakHyphen','softHyphen'):
                    add(kind,sorted(s['attributes'].items()));reading.append('\t' if kind=='tab' else '\n' if kind in ('br','cr') else '-')
                elif kind=='field_evidence':
                    o,node=object_data(s['object_id']);add(kind,tree_value(node))
                    if node.tag=='{'+NS['w']+'}fldSimple':reading.append(''.join(node.xpath('.//w:t/text()',namespaces=NS)))
                elif kind=='legacy_separator':
                    o,node=object_data(s['object_id']);add(kind,digest(tree_value(node)))
                else:errors.append(f'{bid}:unsupported_segment:{kind}')
            check(''.join(reading)==b['display_text'],f'{bid}:display_text')
            check(''.join(plain)==b['plain_text'],f'{bid}:plain_text')
            source_node=oracle.root.xpath(b['source_locator']['path'],namespaces=NS)[0]
            source_rels=E.fromstring(oracle.parts['word/_rels/document.xml.rels'])
            rels={x.get('Id'):dict(x.attrib) for x in source_rels}
            expected_links=[{'attributes':dict(x.attrib),'relationship':rels.get(x.get('{'+NS['r']+'}id'))} for x in source_node.findall('.//w:hyperlink',NS)]
            check(b.get('hyperlinks',[])==expected_links,f'{bid}:hyperlink_targets_and_attributes')
            return ['paragraph',events]
        if b['kind']=='table':
            rows=[[] for _ in range(b['rows'])]
            current_columns={}
            for cid in b['cells']:
                c=byid[cid];check(cid not in visited,f'{cid}:unique_cell');visited.add(cid)
                check(c['container_id']==bid,f'{cid}:table_parent')
                col=current_columns.get(c['row'],0);check(c['col']==col,f'{cid}:column_position');current_columns[c['row']]=col+c['col_span']
                rows[c['row']].append({'span':c['col_span'],'vmerge':c['v_merge_raw'],'children':[block_value(ch,cid) for ch in c['children']]})
            return ['table',{'columns':b['columns'],'rows':rows}]
        if b['kind']=='boundary':
            o,node=object_data(b['object_id']);return ['boundary',tree_value(node)]
        raise ValueError('Unexpected block kind')
    actual=oracle.inventories()
    check(len(actual)==len(scan['top_level_ids']),'top_level_count')
    observed=[]
    for bid in scan['top_level_ids']:
        b=byid[bid];idx=b['source_locator']['body_child_index'];observed.append(idx)
        check(idx in actual and block_value(bid)==actual[idx],f'{bid}:ordered_content_geometry')
    check(observed==list(actual),'top_level_order')
    check(visited==set(byid),'no_orphan_blocks')
    check(used_objects==set(scan['objects']),'no_orphan_objects')
    declared_marks=[]
    for b in scan['blocks']:
        if b['kind']=='boundary':
            node=E.fromstring((scan_dir/scan['objects'][b['object_id']]['payload_ref']).read_bytes())
            if node.tag=='{'+NS['w']+'}bookmarkStart':declared_marks.append((node.get('{'+NS['w']+'}id'),node.get('{'+NS['w']+'}name')))
        declared_marks.extend((s['bookmark_id'],s['name']) for s in b.get('segments',[]) if s['kind']=='bookmarkStart')
    actual_marks=[(x.get('{'+NS['w']+'}id'),x.get('{'+NS['w']+'}name')) for x in oracle.body.findall('.//w:bookmarkStart',NS)]
    check(declared_marks==actual_marks,'bookmark_names_and_order')
    counts=Counter(o['kind'] for o in scan['objects'].values())
    format_audit=None
    if scan.get('scan_version')=='2.0.0-experimental.4':
        from .verify_number_facts import audit
        format_audit=audit(source,scan);checks+=format_audit['checks'];errors.extend(format_audit['errors'])
    return {'source':Path(source).name,'status':'PASS' if not errors else 'FAIL','checks':checks,'errors':errors,
            'recognition_fact_audit':format_audit,
            'top_level_blocks':len(actual),'paragraphs':sum(b['kind']=='paragraph' for b in scan['blocks']),
            'tables':sum(b['kind']=='table' for b in scan['blocks']),'cells':sum(b['kind']=='cell' for b in scan['blocks']),
            'object_counts':dict(counts),'scope':'Ordered content, math XML tree/payload, media, containers, physical cell spans and bookmark events in these inputs; no visual or WPS validation.'}
