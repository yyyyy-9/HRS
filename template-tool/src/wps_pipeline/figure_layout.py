"""Shared figure/layout relations over scan facts; no Markdown, model or source edits."""
from collections import Counter
import re

from .numbered_candidates import manual_prefix, numeric_expression, list_introduction


def picture_row(block):
    drawings=[]
    for segment in block.get('segments',[]):
        kind=segment['kind']
        if kind=='drawing':drawings.append(segment['object_id'])
        elif kind in ('bookmarkStart','bookmarkEnd','tab'):continue
        elif kind=='text' and not segment['text'].strip():continue
        else:return []
    return drawings


def descendants(byid, block):
    """Physical order, including nested cells/tables, without duplicating aliases."""
    yield block
    for ident in block.get('cells',block.get('children',[])):
        yield from descendants(byid,byid[ident])


def table_layout(scan, block):
    byid={b['block_id']:b for b in scan['blocks']}
    drawings=[s['object_id'] for b in descendants(byid,block) for s in b.get('segments',[]) if s['kind']=='drawing']
    if not drawings:return None
    cells=[]
    for ident in block['cells']:
        cell=byid[ident];content=list(descendants(byid,cell))
        cells.append(dict(block_id=ident,row=cell['row'],col=cell['col'],col_span=cell['col_span'],
                          v_merge_raw=cell['v_merge_raw'],
                          paragraphs=[b['block_id'] for b in content if b['kind']=='paragraph'],
                          drawings=[s['object_id'] for b in content for s in b.get('segments',[]) if s['kind']=='drawing']))
    return dict(kind='table',rows=block['rows'],columns=block['columns'],drawings=drawings,cells=cells)


def apply(scan, candidate, overrides=None):
    """Complete associations before final review/number authorization is generated.

    An image-bearing table without a linked table caption is a figure container.
    Classification does not discard text or require cells to be image-only.
    """
    overrides=overrides or {};byid={b['block_id']:b for b in scan['blocks']}
    top=[byid[i] for i in scan['top_level_ids']];rows={r['block_id']:r for r in candidate['blocks']}
    protected=set(overrides)|{r['block_id'] for r in rows.values() if r.get('decision')}
    positions={b['block_id']:i for i,b in enumerate(top)}
    def heading(b):
        r=rows[b['block_id']]
        return (b.get('outline_level_raw') in range(6) or r['role'] in ('document_title','front_heading')
                or (r['role']=='heading' and (r.get('status')!='review' or r.get('number_candidate'))))
    def nearby(index, direction):
        distance=0;j=index+direction
        while 0<=j<len(top) and distance<3:
            b=top[j]
            if heading(b):break
            if rows[b['block_id']]['role']!='spacer':
                distance+=1;yield b
            j+=direction
    def nearest(index,targets):
        unique={b['block_id']:b for b in targets};ranked=[]
        for b in unique.values():
            j=positions[b['block_id']];a,z=sorted((index,j))
            distance=sum(rows[top[k]['block_id']]['role']!='spacer' for k in range(a+1,z+1))
            ranked.append(((distance,abs(index-j)),b))
        ranked.sort(key=lambda v:v[0])
        return [b for score,b in ranked if score==ranked[0][0]] if ranked else []
    # Explicit table-caption evidence is resolved before the no-table-caption
    # rule. A caption still awaiting a unique table keeps those tables as data.
    for i,b in enumerate(top):
        r=rows[b['block_id']]
        if b['kind']!='paragraph' or b['block_id'] in protected or heading(b):continue
        if (b.get('style_name') or '')=='表题' and r['role']!='table_caption':
            targets=[v for direction in (1,-1) for v in nearby(i,direction) if v['kind']=='table']
            targets=nearest(i,targets)
            if targets:r.update(role='table_caption',level=None,title=None,relates_to=targets[0]['block_id'] if len(targets)==1 else None,
                                status='auto_rule' if len(targets)==1 else 'review',association_candidates=[t['block_id'] for t in targets])
    declared_tables={ident for r in rows.values() if r['role']=='table_caption'
                     for ident in ([r.get('relates_to')]+r.get('association_candidates',[])) if ident}
    for b in top:
        r=rows[b['block_id']]
        if b['kind']=='table' and b['block_id'] in declared_tables:
            r.pop('figure_layout',None);r.update(role='table',level=None,title=None)
        elif b['kind']=='table':
            layout=table_layout(scan,b)
            if layout:
                r.update(role='figure',level=None,title=None,status='auto_rule',figure_layout=layout)
                r['evidence'].append('image_table_without_table_caption')
        elif b['kind']=='paragraph':
            drawings=picture_row(b)
            if not 2<=len(drawings)<=4 or b.get('hyperlinks'):continue
            objects=[scan['objects'][v] for v in drawings]
            if any(o.get('layout')!='inline' for o in objects):continue
            width=sum(int(o.get('extent',{}).get('cx',0)) for o in objects)
            usable=scan.get('body_width_emu')
            if not width or not usable or width>usable:continue
            r.update(role='figure',level=None,title=None,status='auto_rule',
                     figure_layout=dict(kind='inline-row',rows=1,columns=len(drawings),drawings=drawings))
            r['evidence'].append('inline_pictures_fit_single_row')
    def props(b):
        f=b.get('paragraph_format_effective',{})
        return (f.get('alignment') or 'left',)+tuple(str(f.get(k) or '0') for k in ('firstLine','firstLineChars','hanging','hangingChars','left','leftChars','right','rightChars'))
    ordinary=[props(b) for b in top if b['kind']=='paragraph' and b.get('outline_level_raw') is None
              and len(re.sub(r'\s+','',b.get('plain_text','')))>40 and not picture_row(b)]
    baseline=Counter(ordinary).most_common(1)[0][0] if ordinary else tuple(scan.get('normal_paragraph_layout',('left',)+('0',)*8))
    for i,b in enumerate(top):
        r=rows[b['block_id']];text=b.get('display_text','').strip()
        if b['kind']!='paragraph' or b['block_id'] in protected or heading(b) or not text or len(text)>100 or picture_row(b):continue
        explicit=r['role'] in ('figure_caption','table_caption') or (b.get('style_name') or '') in ('图题','表题')
        if not explicit:
            layout=props(b)
            if manual_prefix(text) or numeric_expression(text) or list_introduction(text) or re.search(r'[。；;！？!?：:]$',text):continue
            if layout[0]!='center' and layout[1:]==baseline[1:]:continue
        family='table' if r['role']=='table_caption' or (b.get('style_name') or '')=='表题' else 'figure'
        matches=[]
        if explicit:
            for direction in ((1,-1) if family=='table' else (-1,1)):
                for target in nearby(i,direction):
                    if rows[target['block_id']]['role']==family:
                        matches.append(target);break
        else:
            # Implicit descriptions remain immediately adjacent. Prefer the
            # preceding figure, as in the original Bridge relation heuristic.
            before=top[i-1] if i else None;after=top[i+1] if i+1<len(top) else None
            if before and rows[before['block_id']]['role']=='figure':matches=[before]
            elif after and rows[after['block_id']]['role']=='table':matches=[after];family='table'
        if not matches:continue
        if explicit:
            choices=nearest(i,matches)
            if len(choices)>1:
                r.update(role=family+'_caption',level=None,title=None,status='review',relates_to=None,
                         association_candidates=[v['block_id'] for v in choices])
                r['evidence'].append('ambiguous_object_pair');continue
            matches=choices
        current=r.get('relates_to')
        target=next((v for v in matches if v['block_id']==current),matches[0])
        target_row=rows[target['block_id']]
        r.update(role=family+'_caption',level=None,title=None,status='auto_rule',relates_to=target['block_id'])
        r.pop('level_pending',None)
        r['evidence'].append('adjacent_physical_object_and_'+('caption_style_or_prefix' if explicit else 'distinct_paragraph_layout'))
        descriptor=target_row.get('figure_layout')
        if descriptor:
            descriptor['caption_block']=b['block_id']
            labels=re.split(r'\t+| {2,}',text)
            if descriptor['kind']=='inline-row' and len(labels)==len(descriptor['drawings']) and all(v.strip() for v in labels):
                descriptor['labels']=[v.strip() for v in labels];r['subcaptions']=True
    candidate['figure_layouts']=[dict(block_id=r['block_id'],**r['figure_layout']) for r in candidate['blocks'] if r.get('figure_layout')]
    return candidate
