"""Report roles over source facts, with conflicts queued for bounded review."""
import re
from .recognize_structure import recognize
from .numbered_candidates import rebuild_structure,authorize,list_introduction,VERSION

ABSTRACT={'摘要','执行摘要','abstract'}
REFERENCES={'参考文献','参考资料','参考记录','references','bibliography'}

def predict(scan,overrides=None):
    overrides=overrides or {}
    c=recognize(scan,overrides=overrides)
    byid={b['block_id']:b for b in scan['blocks']};rows=c['blocks']
    def visible(i):return byid[rows[i]['block_id']].get('display_text','').strip()
    first=next((i for i in range(len(rows)) if visible(i)),None)
    anchors=[i for i,r in enumerate(rows) if (r.get('number_candidate') or {}).get('kind') in ('manual','automatic') and r['role']!='list_item']
    first_number=min(anchors,default=len(rows))
    for i,r in enumerate(rows):
        if r['block_id'] in overrides:continue
        b=byid[r['block_id']];text=visible(i);style=(b.get('style_name') or '').casefold()
        if b['kind']!='paragraph' or r.get('number_candidate') is not None:continue
        after=[visible(j) for j in range(i+1,min(i+4,len(rows))) if visible(j)]
        def role(name,why,level=None,status='auto_rule'):
            r.update(role=name,level=level,title=text if name in ('heading','front_heading','document_title') else None,status=status,evidence=[why],source_number_prefix='')
            r.pop('level_pending',None)
        outline=b.get('outline_level_raw')
        prose=len(text)>90 or (bool(re.search('[。；;！？!?]$',text)) and len(text)>30)
        if outline is not None and 0<=outline<5 and prose:
            # A style is evidence, not semantic truth. Genuine long headings
            # remain reviewable rather than being forced into body text.
            role('heading','effective_outline_conflicts_with_prose',outline+1,'review')
            r.update(possible_roles=['heading','body'],possible_levels=list(range(1,6)))
        elif text.casefold() in ABSTRACT and i<first_number and i<8:
            role('front_heading','opening_abstract_label_with_document_position')
        elif text.casefold() in REFERENCES and any(re.match(r'^\[\d+\]',x) for x in after):
            role('front_heading','reference_heading_before_bibliographic_items')
        elif style=='title':role('document_title','explicit_title_style')
        elif i==first and i<first_number and len(text)<=90 and not re.match(r'^\d',text) and not re.search('[。；;！？!?]',text) and not list_introduction(text) and any(x.casefold() in ABSTRACT for x in after):
            role('document_title','opening_title_before_abstract')
        elif '\t' in text and r['role'] not in ('table','figure','equation'):
            role('table_text','tab_delimited_visible_cells')
        elif 'list' in style and r['role']=='body':role('list_item','source_list_style')
        if r['role'] in ('figure_caption','table_caption','equation_description') and r['status']=='review' and not r.get('association_candidates'):
            r['status']='retained_unpaired';r['evidence'].append('preserve_caption_without_asserting_object_pair')
    for i,r in enumerate(rows):
        if r.get('status')!='auto_rule' or r.get('role')!='list_item':continue
        numbers=(r.get('number_candidate') or {}).get('numbers') or []
        outline=byid[r['block_id']].get('outline_level_raw')
        parent=next((p for p in reversed(rows[:i]) if (p.get('number_candidate') or {}).get('numbers')==numbers[:-1]),None) if len(numbers)>1 else None
        if (outline is not None and 0<=outline<5) or (parent is not None and parent.get('role')=='heading'):
            r.update(status='review',possible_roles=['heading','list_item','body'],possible_levels=list(range(1,6)))
            r['evidence'].append('automatic_list_conflicts_with_outline_or_heading_parent')
    from .figure_layout import apply as apply_figure_layouts
    apply_figure_layouts(scan,c,overrides)
    rebuild_structure(rows);authorize(rows,scan)
    c.update(recognizer_version=VERSION,review=[dict(block_id=r['block_id'],text=byid[r['block_id']].get('display_text'),role=r['role'],level=r['level'],evidence=r['evidence']) for r in rows if r['status']=='review'],confirmed_ir=False)
    c['status']='REVIEW_REQUIRED' if c['review'] else 'RULE_CANDIDATES_READY'
    return c
