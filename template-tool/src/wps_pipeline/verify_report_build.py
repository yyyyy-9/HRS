"""Independent read-only verifier of frozen-source to assembled-output content.

Does not import the assembler. Replays declared narrow text operations, then
compares ordered math/media/link/bookmark/table content and package invariants.
"""
from pathlib import Path
from zipfile import ZipFile
from copy import deepcopy
from collections import Counter
import json,hashlib,posixpath,re,argparse
from lxml import etree as E
from .verify_number_edits import heading_edit_error

N={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def q(k):a,b=k.split(':');return '{'+N[a]+'}'+b
def digest(b):return hashlib.sha256(b).hexdigest()
def tree(n):return [n.tag,sorted(n.attrib.items()),n.text if not len(n) else None,[tree(c) for c in n]]
def ordinary(n):return ''.join(n.xpath('.//w:t[not(ancestor::m:oMath)]/text()',namespaces=N))
class Package:
 def __init__(self,path):
  self.path=Path(path)
  with ZipFile(path) as z:self.parts={n:z.read(n) for n in z.namelist()}
  self.root=E.fromstring(self.parts['word/document.xml']);self.body=self.root.find('w:body',N);self.rels={x.get('Id'):dict(x.attrib) for x in E.fromstring(self.parts['word/_rels/document.xml.rels'])}
 def relationship(self,rid):
  r=self.rels[rid];target=r['Target']
  if r.get('TargetMode')=='External':return [r['Type'],'External',target]
  path=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('word',target))
  return [r['Type'],'Internal',digest(self.parts[path])]
 def content(self,n,bmids=None,bmnames=None):
  bmids=bmids or {};bmnames=bmnames or {}
  if n.tag==q('w:tbl'):
   rows=[]
   for tr in n.findall('w:tr',N):
    cells=[]
    for tc in tr.findall('w:tc',N):
     span=tc.find('w:tcPr/w:gridSpan',N);vm=tc.find('w:tcPr/w:vMerge',N)
     cells.append([int(span.get(q('w:val'))) if span is not None else 1,None if vm is None else vm.get(q('w:val'),'continue'),[self.content(c,bmids,bmnames) for c in tc if c.tag in (q('w:p'),q('w:tbl'))]])
    rows.append(cells)
   return ['table',len(n.findall('w:tblGrid/w:gridCol',N)),rows]
  events=[]
  def push(k,v):
   if k=='text' and events and events[-1][0]=='text':events[-1][1]+=v
   else:events.append([k,v])
  def walk(x):
   local=E.QName(x).localname;space=E.QName(x).namespace
   if space==N['w'] and local in ('pPr','rPr'):return
   if space==N['m'] and local in ('oMath','oMathPara'):
    m=deepcopy(x)
    for col in m.findall('.//w:color',N):col.attrib.clear();col.set(q('w:val'),'000000')
    push(local,tree(m));return
   if space==N['wp'] and local in ('inline','anchor'):
    push('drawing',[local,[self.relationship(v) for v in x.xpath('.//a:blip/@r:embed',namespaces=N)]]);return
   if x.tag==q('w:pict'):push('legacy',tree(x));return
   if x.tag==q('w:t'):push('text',x.text or '');return
   if x.tag in (q('w:bookmarkStart'),q('w:bookmarkEnd')):
    attrs=dict(x.attrib);old=attrs.get(q('w:id'));attrs[q('w:id')]=bmids.get(old,old)
    if q('w:name') in attrs:attrs[q('w:name')]=bmnames.get(attrs[q('w:name')],attrs[q('w:name')])
    push(local,sorted(attrs.items()));return
   if x.tag==q('w:hyperlink'):
    attrs=dict(x.attrib);rid=attrs.pop(q('r:id'),None)
    if q('w:anchor') in attrs:attrs[q('w:anchor')]=bmnames.get(attrs[q('w:anchor')],attrs[q('w:anchor')])
    push('link_start',[sorted(attrs.items()),self.relationship(rid) if rid else None])
    for c in x:walk(c)
    push('link_end',None);return
   if x.tag==q('w:fldSimple'):
    copy=deepcopy(x)
    for prop in copy.findall('.//w:rPr',N):prop.getparent().remove(prop)
    push(local,tree(copy));return
   if space==N['w'] and local in ('tab','br','cr','noBreakHyphen','softHyphen','fldChar','instrText'):push(local,tree(x));return
   for c in x:walk(c)
  if n.tag==q('w:p'):
   for x in n:walk(x)
  else:walk(n)
  return [E.QName(n).localname,events]

def checked_fields(node):
 answer=[]
 for p in ([node] if node.tag==q('w:p') else node.findall('.//w:p',N)):
  start=None;middle=None;items=[]
  for i,child in enumerate(p):
   if child.tag==q('w:fldSimple'):items.append((i,dict(simple=child,first=child,last=child,codes=[],texts=child.findall('.//w:t',N))))
   flags=child.findall('w:fldChar',N) if child.tag==q('w:r') else []
   for flag in flags:
    kind=flag.get(q('w:fldCharType'))
    if kind=='begin':start=i;middle=None
    elif kind=='separate':middle=i
    elif kind=='end' and start is not None and middle is not None:
     span=list(p);items.append((start,dict(simple=None,first=span[start],last=child,codes=[t for c in span[start:middle] for t in c.findall('w:instrText',N)],texts=[t for c in span[middle:i+1] for t in c.findall('w:t',N)])));start=None
  for _,f in sorted(items,key=lambda x:x[0]):
   f['p']=p;f['instruction']=f['simple'].get(q('w:instr'),'') if f['simple'] is not None else ''.join(t.text or '' for t in f['codes']);f['cache']=''.join(t.text or '' for t in f['texts']);answer.append(f)
 return answer


def replay(node,change,converted_nodes=None):
 if change['operation'] in ('native_caption_seq','native_caption_ref','remap_native_reference_field'):
  f=checked_fields(node)[change['field_index']]
  if f['instruction']!=change['instruction'] or f['cache']!=change['old']:raise ValueError('Native field source binding changed')
  new=change['new_instruction']
  if change['operation']=='native_caption_seq':
   if not re.fullmatch(r'\s*SEQ\s+\w+\s*(?:\\r\s+\d+\s*)?(?:\\\*\s+(?:ARABIC|MERGEFORMAT)\s*)*',f['instruction'],re.I) or not re.fullmatch(r' SEQ [图表] \\\* ARABIC ',new) or not change['new'].isdigit():raise ValueError('Invalid native SEQ migration')
  else:
   old=re.fullmatch(r'(\s*(?:REF|PAGEREF|NOTEREF)\s+)(\w+)(.*)',f['instruction'],re.I|re.S);target=re.fullmatch(r'(\s*(?:REF|PAGEREF|NOTEREF)\s+)(\w+)(.*)',new,re.I|re.S)
   if not old or not target or old[1].strip()!=target[1].strip() or old[3].strip()!=target[3].strip():raise ValueError('Reference command or switches changed')
  if f['simple'] is not None:f['simple'].set(q('w:instr'),new);f['simple'].set(q('w:dirty'),'1')
  else:
   f['codes'][0].text=new
   for t in f['codes'][1:]:t.text=''
   f['first'].find('w:fldChar',N).set(q('w:dirty'),'1')
  f['texts'][0].text=change['new']
  for t in f['texts'][1:]:t.text=''
  return
 if change['operation'] in ('promote_caption_number','promote_caption_reference'):
  p=([node] if node.tag==q('w:p') else node.findall('.//w:p',N))[change['paragraph_index']];a,b=change['start'],change['end'];offset=0
  if ordinary(p)[a:b]!=change['new'] or not change['new'].isdigit():raise ValueError('Field promotion may consume only declared digits')
  expression=r' SEQ [图表] \\\* ARABIC ' if change['operation']=='promote_caption_number' else r' REF \w+ \\h '
  if not re.fullmatch(expression,change['instruction']):raise ValueError('Invalid generated field instruction')
  for t in p.xpath('.//w:t[not(ancestor::m:oMath)]',namespaces=N):
   value=t.text or '';end=offset+len(value)
   if offset<=a<end:
    run=t.getparent()
    if b>end or run.getparent() is not p or len(run.findall('w:t',N))!=1:raise ValueError('Unsafe source field span')
    at=p.index(run);p.remove(run)
    for piece in ('prefix','field','suffix'):
     if piece=='field':
      f=E.Element(q('w:fldSimple'));f.set(q('w:instr'),change['instruction']);f.set(q('w:dirty'),'1');r=E.SubElement(f,q('w:r'));rp=run.find('w:rPr',N)
      if rp is not None:r.append(deepcopy(rp))
      E.SubElement(r,q('w:t')).text=change['new'];p.insert(at,f);at+=1
     else:
      text=value[:a-offset] if piece=='prefix' else value[b-offset:]
      if text:r=deepcopy(run);r.find('w:t',N).text=text;p.insert(at,r);at+=1
    return
   offset=end
  raise ValueError('Missing generated field digits')
 if change['operation']=='add_caption_number_bookmark':
  fs=[f for f in checked_fields(node) if re.match(r'\s*SEQ\b',f['instruction'],re.I)]
  if len(fs)!=1:raise ValueError('Bookmark must enclose one native SEQ')
  f=fs[0];p=f['p'];a=p.index(f['first']);b=p.index(f['last']);s=E.Element(q('w:bookmarkStart'));s.set(q('w:id'),change['id']);s.set(q('w:name'),change['name']);e=E.Element(q('w:bookmarkEnd'));e.set(q('w:id'),change['id']);p.insert(b+1,e);p.insert(a,s);return
 if change['operation'] in ('materialize_caption_seq','materialize_caption_ref','remap_simple_reference_field'):
  fields=node.findall('.//w:fldSimple',N);field=fields[change['field_index']]
  instruction=field.get(q('w:instr'),'')
  if instruction!=change['instruction']:raise ValueError('Field instruction fingerprint mismatch')
  if change['operation']=='remap_simple_reference_field':
   old=re.fullmatch(r'(\s*(?:REF|PAGEREF|NOTEREF)\s+)([\w]+)(.*)',instruction,re.I|re.S)
   new=re.fullmatch(r'(\s*(?:REF|PAGEREF|NOTEREF)\s+)([\w]+)(.*)',change['new_instruction'],re.I|re.S)
   if not old or not new or old[1]!=new[1] or old[3]!=new[3]:raise ValueError('Reference rename changed field behavior')
   field.set(q('w:instr'),change['new_instruction']);return
  if ordinary(field)!=change['old'] or not re.fullmatch(r'\d+',change['new']):raise ValueError('Invalid field result conversion')
  if change['operation']=='materialize_caption_seq':
   if not re.fullmatch(r'\s*SEQ\s+\w+\s*(?:\\r\s+\d+\s*)?(?:\\\*\s+(?:ARABIC|MERGEFORMAT)\s*)*',instruction,re.I):raise ValueError('Unsupported SEQ')
  else:
   m=re.fullmatch(r'\s*REF\s+(\w+)\s*((?:\\h\s*|\\\*\s+MERGEFORMAT\s*)*)',instruction,re.I)
   if not m or m[1]!=change['bookmark']:raise ValueError('Unsupported REF')
   if bool(change.get('anchor'))!=bool(re.search(r'\\h\b',instruction,re.I)):raise ValueError('Reference navigation changed')
  texts=field.findall('.//w:t',N)
  if not texts:raise ValueError('Missing field result')
  if converted_nodes is not None:converted_nodes.update(texts)
  texts[0].text=change['new']
  for t in texts[1:]:t.text=''
  parent=field.getparent();at=parent.index(field);children=list(field)
  if change.get('anchor'):
   wrapper=E.Element(q('w:hyperlink'));wrapper.set(q('w:anchor'),change['anchor'])
   for child in children:wrapper.append(child)
   parent.insert(at,wrapper)
  else:
   for i,child in enumerate(children):parent.insert(at+i,child)
  parent.remove(field);return

 if change['operation'] in ('detach_automatic_heading_numbering','preserve_automatic_list_numbering'):
  if change.get('deleted_text_characters')!=0:raise ValueError('Numbering-property change must not delete text')
  return
 if change['operation']=='remove_standalone_page_break':
  if node.tag!=q('w:p') or ordinary(node).strip() or node.xpath('.//m:oMath|.//w:drawing|.//w:pict',namespaces=N):raise ValueError('Page break removal on content paragraph')
  brs=node.xpath('.//w:br[@w:type="page"]',namespaces=N)
  if len(brs)!=change['count']:raise ValueError('Page break count mismatch')
  for br in brs:br.getparent().remove(br)
  return
 if change['operation']=='promote_standalone_math':
  ms=node.findall('m:oMath',N)
  if ordinary(node).strip() or len(ms)!=change['count'] or node.findall('m:oMathPara',N):raise ValueError('Invalid standalone math promotion')
  at=node.index(ms[0]);mp=E.Element(q('m:oMathPara'));pr=E.SubElement(mp,q('m:oMathParaPr'));jc=E.SubElement(pr,q('m:jc'));jc.set(q('m:val'),'center')
  for m in ms:node.remove(m);mp.append(m)
  node.insert(at,mp);return
 ps=[node] if node.tag==q('w:p') else node.findall('.//w:p',N);p=ps[change['paragraph_index']]
 text=ordinary(p);a=change['start'];b=change['end'];old=change['old'];new=change['new']
 if text[a:b]!=old:raise ValueError('Declared source text does not match')
 if converted_nodes:
  cursor=0
  for t in p.xpath('.//w:t[not(ancestor::m:oMath)]',namespaces=N):
   end=cursor+len(t.text or '')
   if t in converted_nodes and a<end and b>cursor:raise ValueError('Text edit reinterprets an already materialized field number')
   cursor=end
 kind=change['operation']
 if kind=='mapped_object_reference' and not (old.isdigit() and new.isdigit()):raise ValueError('Reference operation changed non-number')
 if kind in ('heading_number','source_group_number') and not (re.fullmatch(r'\d+(?:\.\d+)* ',new) or (new=='' and re.fullmatch(r'\d+(?:\.\d+)*',change.get('native_number','')))):raise ValueError('Invalid heading number')
 if kind=='manual_list_prefix':
  from .verify_number_edits import list_edit_error
  error=list_edit_error(text,change)
  if error:raise ValueError(error)
 if kind=='caption_number' and not re.fullmatch(r'[图表] \d+　',new):raise ValueError('Invalid caption number')
 if kind=='mapped_heading_reference' and not all(re.fullmatch(r'\d+(?:\.\d+)*',x) for x in (old,new)):raise ValueError('Invalid chapter reference change')
 if kind=='caption_label' and not (re.fullmatch(r'\s*[图表]\s*',old) and new in ('图 ','表 ')):raise ValueError('Invalid caption label')
 if kind=='caption_separator' and (not re.fullmatch(r'[.．、]?\s*',old) or new!='　'):raise ValueError('Invalid caption spacing')
 if kind=='materialize_inherited_bullet' and (old or new!='• '):raise ValueError('Invalid list marker')
 if kind=='remove_unused_equation_label' and (new or not re.fullmatch(r'\s*式\s*\d+\s*',old)):raise ValueError('Invalid label removal')
 if kind=='remove_equation_number_tail' and (new or not re.fullmatch(r'\s*[（(]\s*\d+\s*[）)]\s*',old) or not p.findall('.//m:oMath',N) or text!=old):raise ValueError('Invalid equation number removal')
 if kind=='adjacent_equation_reference' and (not re.fullmatch(r'式\s*\d+',old) or new!='上述关系'):raise ValueError('Invalid adjacent reference migration')
 if kind not in ('mapped_heading_reference','caption_label','caption_separator','mapped_object_reference','heading_number','source_group_number','manual_list_prefix','caption_number','materialize_inherited_bullet','remove_unused_equation_label','remove_equation_number_tail','adjacent_equation_reference'):raise ValueError('Unknown text operation')
 if a==b and a>0:
  offset=0
  for t in p.xpath('.//w:t[not(ancestor::m:oMath)]',namespaces=N):
   value=t.text or ''
   if offset<=a<offset+len(value):
    t.text=value[:a-offset]+new+value[a-offset:];return
   offset+=len(value)
  if a!=offset:raise ValueError('Insertion beyond paragraph')
  run=E.SubElement(p,q('w:r'));E.SubElement(run,q('w:t')).text=new;return
 if a==b:
  run=E.Element(q('w:r'));t=E.SubElement(run,q('w:t'));t.text=new;t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');p.insert(1 if p.find('w:pPr',N) is not None else 0,run);return
 pos=0;first=True
 for t in p.xpath('.//w:t[not(ancestor::m:oMath)]',namespaces=N):
  value=t.text or '';start=pos;pos+=len(value)
  left=max(a,start);right=min(b,pos)
  if left<right:t.text=value[:left-start]+(new if first else '')+value[right-start:];first=False

def bookmark_texts(body):
 values={};active={}
 for node in body.iter():
  if node.tag==q('w:bookmarkStart'):
   name=node.get(q('w:name'));active[node.get(q('w:id'))]=name;values[name]=''
  elif node.tag==q('w:bookmarkEnd'):active.pop(node.get(q('w:id')),None)
  elif node.tag==q('w:t'):
   for name in active.values():values[name]+=node.text or ''
 return values

def verify(report_path):
 r=json.loads(Path(report_path).read_text(encoding='utf8'));out=Package(r['output']);template=Package(r['template']);errors=[];count=0
 def ck(v,name):
  nonlocal count
  count+=1
  if not v:errors.append(name)
 ck(digest(out.path.read_bytes())==r['output_sha256'],'output_hash')
 slots=template.body.xpath('.//w:sdt[w:sdtPr/w:tag[@w:val="wps-report-body-v1"]]',namespaces=N)
 anchors=template.body.xpath('.//w:bookmarkStart[@w:name="WPS_ReportBody"]',namespaces=N)
 prefix=[]
 if anchors:
  mark=anchors[0];paragraph=mark.getparent();ident=mark.get(q('w:id'))
  starts=template.body.xpath('.//w:bookmarkStart[@w:id=$ident]',ident=ident,namespaces=N)
  ends=template.body.xpath('.//w:bookmarkEnd[@w:id=$ident]',ident=ident,namespaces=N)
  valid=(not slots and len(anchors)==1 and len(starts)==1 and len(ends)==1 and ident is not None
         and paragraph.tag==q('w:p') and paragraph.getparent() is template.body
         and template.body[-2] is paragraph and ends[0].getparent() is paragraph
         and list(paragraph).index(mark)<list(paragraph).index(ends[0]) and not ''.join(paragraph.xpath('.//w:t/text()',namespaces=N)).strip())
  if valid:
   allowed={q('w:p'),q('w:r'),q('w:t'),q('w:pPr'),q('w:rPr')}
   valid=all(n in (mark,ends[0]) or n.tag in allowed or any(a.tag in (q('w:pPr'),q('w:rPr')) for a in n.iterancestors()) for n in paragraph.iter())
  ck(valid,'unambiguous_template_body_bookmark')
  if valid:prefix=list(template.body)[:list(template.body).index(paragraph)]
  ck(r.get('target_contract')=='preserved-frontmatter-v1','recognized_target_layout_contract')
  ck(not out.body.xpath('.//w:bookmarkStart[@w:name="WPS_ReportBody"]',namespaces=N),'template_body_marker_consumed')
 elif slots:
  valid=len(slots)==1 and len(template.body)>=2 and slots[0].getparent() is template.body and template.body[-2] is slots[0]
  ck(valid,'unambiguous_template_body_slot')
  if valid:prefix=list(template.body)[:list(template.body).index(slots[0])]
  ck(r.get('target_contract')=='preserved-frontmatter-v1','recognized_target_layout_contract')
 else:ck(r.get('target_contract')=='continuous-body-v1','recognized_target_layout_contract')
 ck(len(out.body)>=len(prefix)+1 and all(tree(a)==tree(b) for a,b in zip(prefix,list(out.body)[:len(prefix)])),'preserved_template_frontmatter')
 ck(digest(template.path.read_bytes())==r['template_sha256'],'template_hash')
 editable={'word/document.xml','word/_rels/document.xml.rels','[Content_Types].xml'}
 if r.get('numbering_definitions_imported'):editable.add('word/numbering.xml')
 ck(all(out.parts.get(p)==b for p,b in template.parts.items() if p not in editable),'preserve_only_template_parts')
 ck(tree(out.body.find('w:sectPr',N))==tree(template.body.find('w:sectPr',N)),'target_section')
 styles=E.fromstring(template.parts['word/styles.xml']);style_names={s.find('w:name',N).get(q('w:val')).lower():s.get(q('w:styleId')) for s in styles.findall('w:style',N) if s.find('w:name',N) is not None}
 known_ids=set(style_names.values())
 style_nodes={s.get(q('w:styleId')):s for s in styles.findall('w:style',N)}
 def effective_flag(p,key):
  direct=p.find('w:pPr/w:'+key,N)
  if direct is not None:return direct.get(q('w:val'),'1') not in ('0','false','off')
  st=p.find('w:pPr/w:pStyle',N);sid=st.get(q('w:val')) if st is not None else style_names['normal'];seen=set()
  while sid in style_nodes and sid not in seen:
   seen.add(sid);node=style_nodes[sid];flag=node.find('w:pPr/w:'+key,N)
   if flag is not None:return flag.get(q('w:val'),'1') not in ('0','false','off')
   base=node.find('w:basedOn',N);sid=base.get(q('w:val')) if base is not None else None
  return False
 report_paragraphs=[p for node in list(out.body)[len(prefix):-1] for p in node.iter(q('w:p'))]
 for p in report_paragraphs:
  st=p.find('w:pPr/w:pStyle',N);ck(st is not None and st.get(q('w:val')) in known_ids,'all_paragraph_styles_resolve')
  ck(not effective_flag(p,'pageBreakBefore'),'no_paragraph_forced_page_break')
 generated=r['generated_blocks'];generated_indices=[b['output_index'] for b in generated]
 ck(len(generated_indices)==len(set(generated_indices)),'unique_generated_block_indices')
 ck(len({s['source_id'] for s in r['sources']})==len(r['sources']),'unique_source_ids')
 for b in generated:
  ck(b.get('kind') in (None,'source_group_title','source_gap','source_gap_heading'),'known_generated_block_kind')
  p=out.body[b['output_index']]
  expected_style='normal' if b.get('kind')=='source_gap' else 'heading 1' if b.get('kind') in ('source_group_title','source_gap_heading') else 'title'
  ps=p.find('w:pPr/w:pStyle',N)
  ck(ordinary(p)==b['text'] and ps is not None and ps.get(q('w:val'))==style_names[expected_style],'generated_title_style_and_text')
  if b.get('kind')=='source_group_title':
   ck(bool(r['master']),'source_group_only_in_master')
   src=next((s for s in r['sources'] if s['source_id']==b.get('source_id')),None)
   detail=src.get('generated_group_title') if src else None
   ck(bool(detail) and detail['text']==b['text']==(detail['label'] if r.get('native_chapter_num_id') else str(detail['source_number'])+' '+detail['label']),'source_group_label_provenance')
 gaps=r.get('gaps',[])
 gap_blocks=[b for b in generated if b.get('kind')=='source_gap']
 ck(len(gaps)==len(gap_blocks),'gap_records_match_visible_markers')
 ck(len({g['source_id'] for g in gaps})==len(gaps),'unique_gap_source_ids')
 ck(not {s['source_id'] for s in r['sources']}&{g['source_id'] for g in gaps},'gap_is_not_counted_as_imported')
 scope=sorted([(s.get('source_number',i),s['source_id']) for i,s in enumerate(r['sources'],1)]+[(g['source_number'],g['source_id']) for g in gaps])
 if 'selected_source_ids' in r:
  ck([sid for _,sid in scope]==r['selected_source_ids'],'all_selected_sources_imported_or_explicit_gap_in_order')
 for g in gaps:
  ck(Path(g['path']).is_file() and digest(Path(g['path']).read_bytes())==g['sha256'],g['source_id']+':gap_original_attached')
  ck(any(b['source_id']==g['source_id'] and b['output_index']==g['output_index'] for b in gap_blocks),g['source_id']+':gap_visible_in_document')
 for error in verify_retained_numbering(r,out):ck(False,error)
 output_bookmark_text=bookmark_texts(out.body)
 allout=[];counts=Counter();details=[]
 previous_source_end=-1
 for source_order,src in enumerate(r['sources'],1):
  source=Package(src['path']);sid=src['source_id'];ck(digest(source.path.read_bytes())==src['sha256'],sid+':source_hash')
  source_bookmark_text=bookmark_texts(source.body)
  maps=[x for x in r['mapping'] if x['source_id']==sid];exc=[x for x in r['exclusions'] if x['source_id']==sid]
  groups=[b for b in generated if b.get('kind')=='source_group_title' and b.get('source_id')==sid]
  needs_group=bool(r['master']) and not any(x['role']=='document_title' for x in maps)
  ck(len(groups)==int(needs_group),sid+':exactly_one_required_source_group')
  ck(bool(src.get('generated_group_title'))==needs_group,sid+':source_group_report_presence')
  if groups:
   group=groups[0];detail=src.get('generated_group_title') or {}
   ck(group.get('source_number')==detail.get('source_number')==src.get('source_number',source_order),sid+':source_group_ordinal')
   ck(group['output_index']>previous_source_end and bool(maps) and group['output_index']+1==min(x['output_index'] for x in maps),sid+':source_group_precedes_own_content')
  if maps:
   ck(min(x['output_index'] for x in maps)>previous_source_end,sid+':source_groups_keep_selected_order')
   previous_source_end=max(x['output_index'] for x in maps)
  valid=[i for i,n in enumerate(source.body) if n.tag!=q('w:sectPr')];selected=[x['source_index'] for x in maps]
  ck(len(selected)==len(set(selected)),sid+':no_duplicate_source_blocks')
  ck(set(selected)|{x['source_index'] for x in exc}==set(valid),sid+':all_source_blocks_accounted')
  ck(not exc,sid+':no_implicit_source_exclusions')
  natural=sorted(maps,key=lambda x:x['output_index']);without_moved=[x['source_index'] for x in natural if x['role']!='table_caption']
  ck(without_moved==sorted(without_moved),sid+':source_order_except_declared_table_caption_move')
  ck(digest(Path(src['candidate']).read_bytes())==src['candidate_sha256'],sid+':candidate_hash')
  cand=json.loads(Path(src['candidate']).read_text(encoding='utf8'));byindex={x['source_locator']['body_child_index']:x for x in cand['blocks']}
  # The verifier inspects original physical objects, never the model's role
  # name alone. Missing associations must have a visible preservation record.
  held_roles=set()
  source_exceptions=[x for x in r['exceptions'] if x.get('source_id')==sid]
  for row in maps:
   if row['role'] not in ('figure_caption','table_caption'):continue
   c=byindex[row['source_index']];related=c.get('relates_to')
   ck(row.get('relates_to')==related,f'{sid}:{row["source_index"]}:caption_relation_record_matches_candidate')
   target=next((m for m in maps if m['block_id']==related),None)
   if related:
    physical=source.body[target['source_index']] if target is not None else None
    valid=physical is not None and related!=row['block_id'] and ((row['role']=='table_caption' and physical.tag==q('w:tbl') and not target.get('figure_layout')) or (row['role']=='figure_caption' and bool(physical.findall('.//w:drawing',N)) and (physical.tag==q('w:p') or (physical.tag==q('w:tbl') and target.get('role')=='figure' and target.get('figure_layout',{}).get('kind')=='table'))))
    ck(valid,f'{sid}:{row["source_index"]}:caption_target_physical_type')
   if not related or c['status'] in ('review','retained_unpaired'):
    held_roles.add(row['role'])
    ck(any(x.get('block_id')==row['block_id'] and x.get('kind')=='caption_association_unresolved' for x in source_exceptions),f'{sid}:{row["source_index"]}:unresolved_caption_is_reported')
  for role in held_roles:
   ck(any(x.get('kind')=='caption_numbering_group_retained' and x.get('caption_role')==role for x in source_exceptions),f'{sid}:{role}:retained_numbering_group_reported')
   ck(not any(c['operation'] in ('caption_number','materialize_caption_seq') for m in maps if m['role']==role for c in m['changes']),f'{sid}:{role}:no_partial_numbering_of_unresolved_group')
  for row in maps:
   si=row['source_index'];oi=row['output_index'];allout.append(oi);node=deepcopy(source.body[si]);target=out.body[oi]
   try:
    converted_nodes=set()
    for change in row['changes']:
     numeric_error=heading_edit_error(ordinary(source.body[si]),change)
     ck(numeric_error is None,f'{sid}:{si}:independent_number_guard:{numeric_error}')
     if change['operation']=='adjacent_equation_reference':
      ref=change['target_source_index'];number=re.search(r'\d+',change['old']).group()
      ck(ref==si-1 and bool(re.match(r'^\s*式\s*'+number+r'\s+',ordinary(source.body[ref]))),f'{sid}:{si}:adjacent_equation_reference_target')
     if change['operation'] in ('materialize_caption_seq','materialize_caption_ref','native_caption_seq','native_caption_ref'):
      target_row=next((m for m in maps if m['block_id']==change['target_block_id']),None)
      ck(target_row is not None and target_row['role'] in ('figure_caption','table_caption'),f'{sid}:{si}:field_target_caption')
      if target_row is not None:
       text=ordinary(out.body[target_row['output_index']]);caption=re.match(r'^[图表] (\d+)　',text)
       ck(caption is not None and caption[1]==change['new'],f'{sid}:{si}:field_number_matches_caption')
       if change['operation'] in ('materialize_caption_ref','native_caption_ref'):
        old_target=source.body[target_row['source_index']]
        marks=[m for m in old_target.findall('w:bookmarkStart',N) if m.get(q('w:name'))==change['bookmark']]
        ck(len(marks)==1 and change['old']==source_bookmark_text.get(change['bookmark']),f'{sid}:{si}:source_ref_bookmark_binding')
        mapped=src['bookmark_name_map'].get(change['bookmark'])
        ck(mapped is not None and output_bookmark_text.get(mapped)==change['new'],f'{sid}:{si}:output_bookmark_contains_reference_number')
        if change['operation']=='native_caption_ref':ck(re.match(r'\s*REF\s+'+re.escape(mapped or '?')+r'(?=\s|$)',change['new_instruction'],re.I) is not None,f'{sid}:{si}:native_ref_preserves_bound_target')
     if change['operation'] in ('remap_simple_reference_field','remap_native_reference_field'):
      expected_name=src['bookmark_name_map'].get(change['bookmark'])
      ck(expected_name is not None and re.match(r'\s*(?:REF|PAGEREF|NOTEREF)\s+'+re.escape(expected_name)+r'(?=\s|$)',change['new_instruction'],re.I) is not None,f'{sid}:{si}:reference_field_name_mapping')
     if change['operation']=='mapped_heading_reference':
      matches=[m for m in maps if m['role']=='heading' and (byindex[m['source_index']].get('number_candidate') or {}).get('numbers') and '.'.join(map(str,byindex[m['source_index']]['number_candidate']['numbers']))==change['old']]
      ck(len(matches)==1 and (r.get('native_chapter_num_id') or ordinary(out.body[matches[0]['output_index']]).startswith(change['new']+' ')),f'{sid}:{si}:chapter_reference_unique_target')
     replay(node,change,converted_nodes)
    observed=out.content(target)
    layout=row.get('figure_layout')
    ck(layout==byindex[si].get('figure_layout'),f'{sid}:{si}:figure_layout_matches_candidate')
    if layout and layout.get('kind')=='inline-row':
     drawings=node.findall('.//wp:inline',N)
     ck(node.tag==q('w:p') and not ordinary(node).strip() and 2<=len(drawings)<=4 and len(drawings)==layout.get('columns'),f'{sid}:{si}:physical_inline_group')
     ck(target.tag==q('w:tbl') and len(target.findall('w:tr',N))==1 and len(target.findall('w:tr/w:tc',N))==len(drawings),f'{sid}:{si}:inline_group_cell_count')
     events=[]
     for cell in target.findall('w:tr/w:tc',N):
      ps=cell.findall('w:p',N);ck(len(ps)==1 and len(ps[0].findall('.//wp:inline',N))==1,f'{sid}:{si}:one_picture_per_inline_group_cell')
      for p in ps:
       for kind,value in out.content(p)[1]:
        if kind=='text' and events and events[-1][0]=='text':events[-1][1]+=value
        else:events.append([kind,value])
     observed=['p',events]
    ck(source.content(node,src['bookmark_id_map'],src['bookmark_name_map'])==observed,f'{sid}:{si}:ordered_content_math_links_tables')
   except Exception as e:ck(False,f'{sid}:{si}:replay_error:{e}')
   ck(ordinary(target)==ordinary(node)==row['output_text'],f'{sid}:{si}:text_readback')
   if target.tag==q('w:p'):
    if source.body[si].findall('.//m:oMath',N) and (not ordinary(source.body[si]).strip() or re.fullmatch(r'\s*[（(]\s*\d+\s*[）)]\s*',ordinary(source.body[si]))):
     ck(bool(target.findall('m:oMathPara',N)) and not ordinary(target).strip(),f'{sid}:{si}:independent_standalone_equation_contract')
     ck(target.find('w:pPr/w:pStyle',N).get(q('w:val'))==style_names['公式'],f'{sid}:{si}:independent_formula_style')
    ps=target.find('w:pPr/w:pStyle',N);ck(ps is not None,f'{sid}:{si}:paragraph_style_present')
    roles={'document_title':'heading 1' if r['master'] else 'title','front_heading':'heading 2','body':'normal','spacer':'normal','figure':'图形段','figure_caption':'图题','table_caption':'表题','equation':'公式','equation_description':'normal','list_item':'list paragraph','reference':'参考条目','table_text':'list paragraph','boundary':'normal'}
    expected=('heading '+str(row['level']) if row.get('level') in range(1,6) else 'normal') if row['role']=='heading_retained' else 'heading '+str(row['level']+(1 if r['master'] else 0)) if row['role']=='heading' else roles.get(row['role'])
    ck(expected is not None and ps is not None and ps.get(q('w:val'))==style_names[expected],f'{sid}:{si}:role_style')
    if row['role']=='heading' and not r.get('native_chapter_num_id'):ck(bool(re.match(r'^\d+(?:\.\d+)* \S',ordinary(target))),f'{sid}:{si}:heading_number_flush_left')
   if target.tag==q('w:tbl') and row.get('figure_layout'):
    layout=row['figure_layout'];ck(row['role']=='figure',f'{sid}:{si}:layout_is_figure')
    ck(bool(source.body[si].findall('.//w:drawing',N)),f'{sid}:{si}:source_layout_contains_images')
    ck(not any(m['role']=='table_caption' and m.get('relates_to')==row['block_id'] for m in maps),f'{sid}:{si}:figure_layout_has_no_table_caption')
    if layout['kind']=='table':ck(source.body[si].tag==q('w:tbl'),f'{sid}:{si}:source_is_image_table')
    pr=target.find('w:tblPr',N);borders=pr.find('w:tblBorders',N)
    ck(borders is not None and len(borders)==6 and all(n.get(q('w:val'))=='nil' for n in borders),f'{sid}:{si}:figure_layout_borderless')
    ck(pr.find('w:tblStyle',N) is None and pr.find('w:jc',N).get(q('w:val'))=='center',f'{sid}:{si}:no_data_table_style_on_figure')
    for tr in target.findall('.//w:tr',N):
     ck(not tr.findall('w:trPr/w:tblHeader',N) and not tr.findall('w:trPr/w:trHeight',N),f'{sid}:{si}:figure_no_header_or_fixed_height')
    for cell in target.findall('.//w:tc',N):
     cp=cell.find('w:tcPr',N);ck(cp.find('w:shd',N) is None and cp.find('w:tcBorders',N) is None,f'{sid}:{si}:figure_cell_no_data_decoration')
     for p in cell.findall('w:p',N):
      pp=p.find('w:pPr',N);ind=pp.find('w:ind',N)
      style='图形段' if p.findall('.//w:drawing',N) else '图题'
      ck(pp.find('w:pStyle',N).get(q('w:val'))==style_names[style],f'{sid}:{si}:figure_cell_role_style')
      ck(ind is not None and all(ind.get(q('w:'+key))=='0' for key in ('left','right','firstLine','hanging','leftChars','rightChars','firstLineChars','hangingChars')),f'{sid}:{si}:figure_cell_all_indents_zero')
      ck(pp.find('w:jc',N).get(q('w:val'))=='center',f'{sid}:{si}:figure_cell_center')
     cw=cp.find('w:tcW',N)
     if cw is not None:
      limit=max(200,int(cw.get(q('w:w')))-170)*635
      for image in cell.findall('.//wp:inline/wp:extent',N):ck(int(image.get('cx'))<=limit,f'{sid}:{si}:figure_fits_cell')
   elif target.tag==q('w:tbl'):
    for tr in target.findall('.//w:tr',N):
     flag=tr.find('w:trPr/w:cantSplit',N);ck(flag is None or flag.get(q('w:val'),'1') in ('0','false','off'),f'{sid}:{si}:table_rows_may_split')
    ck(target.find('w:tblPr/w:jc',N).get(q('w:val'))=='center',f'{sid}:{si}:table_center')
    for p in target.findall('.//w:tc/w:p',N):
     pp=p.find('w:pPr',N);space=pp.find('w:spacing',N);ind=pp.find('w:ind',N)
     ck(pp.find('w:pStyle',N).get(q('w:val'))==style_names['表内正文'],f'{sid}:{si}:cell_style')
     ck(space is not None and space.get(q('w:line'))=='240' and space.get(q('w:lineRule'))=='auto',f'{sid}:{si}:cell_single_line')
     ck(ind is not None and ind.get(q('w:firstLine'))=='0' and ind.get(q('w:firstLineChars'))=='0',f'{sid}:{si}:cell_no_indent')
     ck(pp.find('w:jc',N).get(q('w:val'))=='center',f'{sid}:{si}:cell_horizontal_center')
     kn=pp.find('w:keepNext',N);ck(kn is not None and kn.get(q('w:val'))=='0',f'{sid}:{si}:no_table_keep_chain')
    ck(all(c.find('w:tcPr/w:vAlign',N).get(q('w:val'))=='center' for c in target.findall('.//w:tc',N)),f'{sid}:{si}:cell_vertical_center')
   # Direct emphasis is compared per character after replay, with hyperlinks
   # and math still included in the independent ordered-content comparison.
   if row['role'] in ('body','list_item','reference','table_text','table'):
    def emphasis(n,package):
     definitions={s.get(q('w:styleId')):s for s in E.fromstring(package.parts['word/styles.xml']).findall('w:style',N)}
     answer=[]
     for p in ([n] if n.tag==q('w:p') else n.findall('.//w:p',N)):
      tokens=[]
      for run in p.xpath('.//w:r[not(ancestor::m:oMath)]',namespaces=N):
       attrs=[]
       style_ref=run.find('w:rPr/w:rStyle',N);current=style_ref.get(q('w:val')) if style_ref is not None else None
       ancestry=[];visited=set()
       while current in definitions and current not in visited:
        visited.add(current);style=definitions[current];ancestry.insert(0,style)
        base=style.find('w:basedOn',N);current=base.get(q('w:val')) if base is not None else None
       for key in ('b','i','u','strike','dstrike','vertAlign'):
        inherited=None
        for style in ancestry:
         flag=style.find('w:rPr/w:'+key,N)
         if flag is not None:
          value=flag.get(q('w:val'),'1')
          if key in ('b','i','strike','dstrike'):
           if value not in ('0','false','off'):inherited='0' if inherited=='1' else '1'
          else:inherited=value
        e=run.find('w:rPr/w:'+key,N)
        effective=e.get(q('w:val'),'1') if e is not None else inherited
        if effective is not None and effective not in ('0','false','off','none'):attrs.append((key,effective))
       for ch in ''.join(run.xpath('./w:t/text()',namespaces=N)):tokens.append([ch,attrs])
      answer.append(tokens)
     return answer
    ck(emphasis(node,source)==emphasis(target,out),f'{sid}:{si}:effective_character_style_emphasis')
   srcimg=node.findall('.//wp:inline',N);dstimg=target.findall('.//wp:inline',N)
   ck(len(srcimg)==len(dstimg),f'{sid}:{si}:drawing_count')
   for a,b in zip(srcimg,dstimg):
    ae=a.find('wp:extent',N);be=b.find('wp:extent',N);ax,ay=int(ae.get('cx')),int(ae.get('cy'));bx,by=int(be.get('cx')),int(be.get('cy'))
    ck(bx<=ax and by<=ay and abs(bx*ay-by*ax)<=max(ax,ay),f'{sid}:{si}:image_proportions')
   counts['blocks']+=1
  for key,path in [('tables','.//w:tbl'),('math','.//m:oMath'),('drawings','.//wp:inline')]:counts[key]+=len(source.body.findall(path,N))
  details.append({'source':sid,'mapped':len(maps),'excluded':len(exc)})
 ck(len(allout)==len(set(allout)),'unique_output_mapping')
 ck(not set(allout)&set(generated_indices),'generated_blocks_do_not_overlap_source_blocks')
 ck(set(allout)|{x['output_index'] for x in r['generated_blocks']}|set(range(len(prefix)))=={i for i,n in enumerate(out.body) if n.tag!=q('w:sectPr')},'all_output_blocks_accounted')
 ck(not (set(allout)|set(generated_indices))&set(range(len(prefix))),'report_mapping_does_not_overlap_frontmatter')
 caption_ordinals=Counter()
 for row in sorted(r['mapping'],key=lambda x:x['output_index']):
  if any(c['operation'] in ('caption_number','materialize_caption_seq') for c in row['changes']):
   label='图' if row['role']=='figure_caption' else '表';caption_ordinals[label]+=1
   ck(ordinary(out.body[row['output_index']]).startswith(label+' '+str(caption_ordinals[label])+'　'),'caption_numbers_follow_output_order')
 for instr in out.body.xpath('.//w:fldSimple/@w:instr',namespaces=N):
  target=re.match(r'\s*(?:REF|PAGEREF|NOTEREF)\s+(\w+)',instr,re.I)
  if target:ck(target[1] in output_bookmark_text,'remaining_reference_field_target_exists')
 starts=out.body.findall('.//w:bookmarkStart',N);ends=out.body.findall('.//w:bookmarkEnd',N)
 ids=[x.get(q('w:id')) for x in starts];names=[x.get(q('w:name')) for x in starts]
 ck(len(ids)==len(set(ids))==len(ends) and set(ids)=={x.get(q('w:id')) for x in ends},'bookmark_id_pairs_unique')
 ck(len(names)==len(set(names)),'bookmark_names_unique')
 original_unresolved=[]
 for src in r['sources']:
  p=Package(src['path']);bn={x.get(q('w:name')) for x in p.body.findall('.//w:bookmarkStart',N)}
  original_unresolved.extend(x.get(q('w:anchor')) for x in p.body.findall('.//w:hyperlink',N) if x.get(q('w:anchor')) and x.get(q('w:anchor')) not in bn)
 ck(all(x.get(q('w:anchor')) in set(names)|set(original_unresolved) for x in out.body.findall('.//w:hyperlink',N) if x.get(q('w:anchor'))),'no_new_internal_link_breaks')
 for x in out.body.iter():
  for k,v in x.attrib.items():
   if k.startswith('{'+N['r']+'}'):ck(v in out.rels,'relationship_exists:'+v)
 for key,path in [('tables','.//w:tbl'),('math','.//m:oMath'),('drawings','.//wp:inline')]:
  local=path.split(':')[-1]
  namespace=N['wp'] if key=='drawings' else N['m'] if key=='math' else N['w']
  preserved=sum(sum(1 for _ in node.iter('{'+namespace+'}'+local)) for node in prefix)
  generated_layouts=sum(row.get('figure_layout',{}).get('kind')=='inline-row' for row in r['mapping'] if row.get('figure_layout')) if key=='tables' else 0
  ck(len(out.body.findall(path,N))==counts[key]+preserved+generated_layouts,'total_'+key)
 promoted=sum(c['operation']=='promote_standalone_math' for row in r['mapping'] for c in row['changes'])
 ck(len(out.body.findall('.//m:oMathPara',N))==sum(len(Package(s['path']).body.findall('.//m:oMathPara',N)) for s in r['sources'])+promoted+sum(sum(1 for _ in node.iter(q('m:oMathPara'))) for node in prefix),'display_math_wrappers')
 from .verify_native_numbering import verify as verify_native_output
 for error in verify_native_output(r,out):ck(False,error)
 return {'output':r['output'],'status':'PASS' if not errors else 'FAIL','checks':count,'errors':errors,'counts':dict(counts),'source_details':details,'existing_unresolved_internal_links':original_unresolved,'exceptions':r['exceptions'],'wps_status':r['wps_status'],'visual_status':'SKIPPED_BY_USER','scope':'Declared source-bound content transformations, object/link/table integrity, explicit emphasis, template package preservation. Not semantic truth or WPS acceptance.'}


def verify_retained_numbering(report, output):
 errors=[]
 declarations=report.get('numbering_retention',[])
 declared={(d['source_id'],d['source_num_id'],d['target_num_id']) for d in declarations}
 for row in report['mapping']:
  for change in row['changes']:
   if change.get('operation')=='preserve_automatic_list_numbering' and change.get('label_resolved') is False:
    if (row['source_id'],change['source_num_id'],change['target_num_id']) not in declared:
     errors.append('unresolved_numbering_without_preservation_declaration')
 if not declarations:return errors
 target_root=E.fromstring(output.parts['word/numbering.xml'])
 all_targets=[d['target_num_id'] for d in declarations]
 if len(all_targets)!=len(set(all_targets)):errors.append('retained_numbering_instances_must_not_be_shared')
 def definitions(root,nid):
  num=next((n for n in root.findall('w:num',N) if n.get(q('w:numId'))==nid),None)
  if num is None:raise ValueError('Missing numbered instance')
  aid=num.find('w:abstractNumId',N).get(q('w:val'))
  abstract=next((n for n in root.findall('w:abstractNum',N) if n.get(q('w:abstractNumId'))==aid),None)
  if abstract is None:raise ValueError('Missing abstract definition')
  a=deepcopy(abstract);n=deepcopy(num)
  a.set(q('w:abstractNumId'),'IDENTITY');n.set(q('w:numId'),'IDENTITY');n.find('w:abstractNumId',N).set(q('w:val'),'IDENTITY')
  return tree(a),tree(n)
 def usage(package,nid):
  styles={s.get(q('w:styleId')):s for s in E.fromstring(package.parts['word/styles.xml']).findall('w:style',N)}
  default=next((sid for sid,s in styles.items() if s.get(q('w:default'))=='1' and s.get(q('w:type'))=='paragraph'),'Normal')
  def effective(p,key):
   nodes=[p];st=p.find('w:pPr/w:pStyle',N);sid=st.get(q('w:val')) if st is not None else default;seen=set()
   while sid in styles and sid not in seen:
    seen.add(sid);n=styles[sid];nodes.append(n);base=n.find('w:basedOn',N);sid=base.get(q('w:val')) if base is not None else None
   for n in nodes:
    prop=n.find('w:pPr/w:numPr/w:'+key,N)
    if prop is not None:return prop.get(q('w:val'))
   return None
  entries=[]
  for p in package.body.iter(q('w:p')):
   if effective(p,'numId')==nid:
    if p.getparent() is not package.body:raise ValueError('Retained instance has an unsupported nested occurrence')
    entries.append((package.body.index(p),int(effective(p,'ilvl') or 0)))
  return entries
 for d in declarations:
  try:
   sid=d['source_id'];source_info=next(s for s in report['sources'] if s['source_id']==sid)
   source=Package(source_info['path']);root=E.fromstring(source.parts['word/numbering.xml'])
   if definitions(root,d['source_num_id'])!=definitions(target_root,d['target_num_id']):raise ValueError('Numbering definition changed beyond identity')
   mapping={m['source_index']:m for m in report['mapping'] if m['source_id']==sid}
   expected=[]
   for index,level in usage(source,d['source_num_id']):
    row=mapping[index]
    if any(c['operation'] in ('heading_number','detach_automatic_heading_numbering') for c in row['changes']):raise ValueError('Preserved instance contains a renumbered heading')
    expected.append((row['output_index'],level))
   if not expected or expected!=sorted(expected) or usage(output,d['target_num_id'])!=expected:raise ValueError('Complete numbering instance order or level changed')
  except Exception as exc:errors.append('retained_numbering:'+str(d)+':'+str(exc))
 return errors
