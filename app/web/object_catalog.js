/* PF13.5: one browser-side contract for object validation and derived numbering.
 * SourceBlocks, editor preview, reference picker and offline reader all call
 * these pure functions; numbers are NEVER stored into Markdown or object JSON.
 * This is separate from Python's independent offline Agent parser, whose
 * semantics are verified with the same cross-language fixture.
 */
(function(root){
'use strict';
const ReportTables=(typeof module!=='undefined'&&module.exports ? require('./report_tables.js') : root.ReportTables);
function tableValidate(obj){
 if(!obj||obj.schema!=='report-table-v1'||typeof obj.id!=='string'||!/^tbl-[A-Za-z0-9_-]{1,60}$/.test(obj.id)||typeof obj.caption!=='string'||obj.caption.length>300)throw Error('表格数据格式或题名无效');
 if(!Array.isArray(obj.rows)||obj.rows.length<1||obj.rows.length>100)throw Error('行数超限');
 const cols=obj.rows[0]?.length;if(!Number.isInteger(cols)||cols<1||cols>30||obj.rows.some(r=>!Array.isArray(r)||r.length!==cols))throw Error('表格必须为规则网格');
 const occupied=new Set();
 for(let r=0;r<obj.rows.length;r++)for(let c=0;c<cols;c++){
  const cell=obj.rows[r][c];if(cell===null){if(!occupied.has(`${r}:${c}`))throw Error('存在未归属的合并单元格');continue;}
  if(!cell||typeof cell.text!=='string'||cell.text.length>30000||!Number.isInteger(cell.rowspan)||!Number.isInteger(cell.colspan)||cell.rowspan<1||cell.colspan<1||r+cell.rowspan>obj.rows.length||c+cell.colspan>cols)throw Error('无效的表格合并或内容');
  for(let rr=r;rr<r+cell.rowspan;rr++)for(let cc=c;cc<c+cell.colspan;cc++){
   const key=`${rr}:${cc}`;if(occupied.has(key))throw Error('合并单元格重叠');occupied.add(key);
   if((rr!==r||cc!==c)&&obj.rows[rr][cc]!==null)throw Error('合并区域必须使用 null 占位');
  }
 }
 ReportTables.validateWidths(obj.columnWidths,cols);
 if(obj.align!==undefined&&(!Array.isArray(obj.align)||obj.align.length!==cols||obj.align.some(x=>x!==null&&!['left','right','center'].includes(x))))throw Error('表格对齐属性无效');
 if(obj.verticalAlign!==undefined&&!['top','middle','bottom'].includes(obj.verticalAlign))throw Error('单元格垂直对齐属性无效');
 return obj;
}
function figureValidate(obj){
 if(!obj||obj.schema!=='report-figure-v1'||typeof obj.id!=='string'||!/^fig-[A-Za-z0-9_-]{1,60}$/.test(obj.id)||typeof obj.caption!=='string'||obj.caption.length>300)throw Error('图形对象 ID 或图题格式无效');
 if(obj.kind==='image'){
  if(!/^assets\/[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.(?:png|jpe?g|gif|webp|svg)$/i.test(obj.src)||typeof obj.alt!=='string'||obj.alt.length>300)throw Error('图片路径/说明无效');
  if(obj.vectorSource!==undefined){
   const match=obj.vectorSource.match(/^assets\/([a-f0-9]{16})\.emf$/i);
   if(!match||!new RegExp(`^assets/${match[1]}\\.(?:png|svg)$`,'i').test(obj.src))throw Error('矢量原图和预览必须同名，预览可以是 SVG 或 PNG');
  }
  if(obj.rasterFallback!==undefined){
   const match=obj.src.match(/^assets\/([a-f0-9]{16})\.svg$/i);
   if(!match||obj.rasterFallback.toLowerCase()!==`assets/${match[1].toLowerCase()}.png`)throw Error('SVG 备用 PNG 路径不匹配');
  }
  if(obj.sourceAsset!==undefined){
   const source=obj.sourceAsset.match(/^assets\/([a-f0-9]{16})\.(pdf|emf|svg|png|jpe?g|webp)$/i),preview=obj.src.match(/^assets\/([a-f0-9]{16})\.(png|svg|jpe?g|webp)$/i);
   if(!source||!preview||source[1].toLowerCase()!==preview[1].toLowerCase())throw Error('源图与预览必须具有相同资源 ID');
   if(source[2].toLowerCase()==='pdf'&&preview[2].toLowerCase()!=='png')throw Error('PDF 需要 PNG 预览');
   if(obj.vectorSource&&obj.sourceAsset.toLowerCase()!==obj.vectorSource.toLowerCase())throw Error('新旧矢量原图字段不一致');
  }
  if(obj.rendition!==undefined){
   const meta=obj.rendition;
   if(!meta||Array.isArray(meta)||typeof meta!=='object'||Object.keys(meta).some(x=>!['format','dpi','page','width','height','engine'].includes(x))||!['png','svg','jpeg','webp'].includes(meta.format)||(meta.dpi!==undefined&&(!Number.isFinite(meta.dpi)||meta.dpi<=0||meta.dpi>600))||meta.page!==1)throw Error('预览图渲染信息不合法');
   if(meta.format!==obj.src.split('.').at(-1).toLowerCase().replace('jpg','jpeg'))throw Error('预览格式不一致');
   for(const field of ['width','height'])if(field in meta&&(!Number.isInteger(meta[field])||meta[field]<1||meta[field]>4096))throw Error('预览尺寸不合法');
   if('engine' in meta&&!/^[A-Za-z0-9_-]{1,36}$/.test(meta.engine))throw Error('渲染器标识不合法');
  }
 }else if(obj.kind==='mermaid'){
  if(typeof obj.source!=='string'||!obj.source.trim()||obj.source.length>50000)throw Error('流程图源数据无效');
 }else throw Error('图形种类不受支持');
 return obj;
}

// Input order is document order; invalid/duplicate IDs never consume a number.
// Object sequence is independent of source representation and display settings.
function numbering(records){
 const counts={figure:0,table:0,equation:0},seen=new Set(),items=[],byId=new Map();
 for(const input of records){
  const type=input.kind==='image-group'?'figure':input.kind;
  const sourceKind=input.sourceKind||null;
  const numbered=Object.prototype.hasOwnProperty.call(counts,type);
  const id=typeof input.id==='string'&&input.id?input.id:null;
  const valid=input.valid!==false && (id ? /^(fig|tbl|eq)-[A-Za-z0-9_-]{1,60}$/.test(id) : true);
  const duplicate=!!id&&seen.has(id);
  if(id&&valid)seen.add(id);
  const countable=valid&&!duplicate&&numbered&&Object.prototype.hasOwnProperty.call(counts,type);
  const number=countable?++counts[type]:null;
  const label=number===null?null:({table:'表 ',figure:'图 ',equation:'式 ('}[type]+number+(type==='equation'?')':''));
  const entry={...input,kind:type,sourceKind,id,valid,duplicate,numbered,number,label};
  items.push(entry);
  if(id&&!duplicate&&valid)byId.set(id,entry);
 }
 return {items,byId,counts};
}
function indexDOM(article){
 const nodes=[...article.querySelectorAll('.report-table-wrap, .report-figure-wrap, .report-equation')];
 const result=numbering(nodes.map(node=>{
  const kind=node.classList.contains('report-equation')?'equation':node.classList.contains('report-table-wrap')?'table':'figure';
  const pipe=kind==='table'&&node.hasAttribute('data-pipe-table');
  return {node,kind,id:node.dataset.equationId||node.dataset.tableId||node.dataset.figureId||null,
   sourceKind:pipe?'gfm-pipe':kind==='table'?'enhanced':null,valid:true};
 }));
 const source=article._sourceObjectCatalog;
 if(source)for(const entry of result.items){
  const original=source.byRecord.get(Number(entry.node.closest('.doc-block')?.dataset.mapIndex));
  if(original)for(const key of ['number','label','valid','duplicate'])entry[key]=original[key];
 }
 return result;
}
function sourceObject(record,next=null){
 const token=record.token;
 if(token.type==='reportEquation')return {kind:'equation',id:token.equation.id};
 if(token.type==='code'&&token.lang?.trim()==='mermaid')return {kind:'figure',id:null,sourceKind:'mermaid'};
 if(token.type==='reportImageGroup')return {kind:'figure',...root.ReportLayout.parseGroup(record.raw)};
 if(token.type==='code'&&['report-table','report-figure'].includes(token.lang?.trim())){
  const object=root.SourceBlocks.readObject(record.raw,token.lang.trim());
  (token.lang.trim()==='report-table'?tableValidate:figureValidate)(object);
  return {...object,kind:token.lang.trim()==='report-table'?'table':'figure'};
 }
 if(token.type==='table'){
  const suffix=next?.type==='paragraph'&&root.ReportPipeTables.parseCaption(next.raw.trim())?next.raw:'';
  let table=root.ReportPipeTables.parseRaw(record.raw);
  // SourceMap raw already includes the original separating newline(s).
  // An unattached caption paragraph must not hide an otherwise valid table.
  if(suffix)try{table=root.ReportPipeTables.parseRaw(record.raw+suffix);}catch{/* The original table remains anonymous. */}
  return {...table.model,id:table.id,kind:'table',sourceKind:'gfm-pipe'};
 }
 return null;
}
function sourceTexts(record,object=null){
 try{object=object||sourceObject(record);}catch{return [];}
 if(!object)return [];
 return [...(object.images||[]).map(image=>image.caption||''),object.caption||'',...(Array.isArray(object.rows)?object.rows:[]).flat().filter(Boolean).map(cell=>cell.text)].filter(Boolean);
}
function indexSource(map){
 const entries=[];
 for(const record of map.blocks)try{
  const object=sourceObject(record,map.blocks[record.index+1]);
  if(object)entries.push({...object,record});
 }catch{/* The original block renderer supplies the precise malformed-object error. */}
 const result=numbering(entries);result.byRecord=new Map(result.items.map(item=>[item.record.index,item]));return result;
}
function validObject(language,obj){
 try{
  if(language==='report-table')tableValidate(obj);
  else if(language==='report-figure')figureValidate(obj);
  else if(language==='report-image-group'){
   const group=root.ReportLayout || (typeof module!=='undefined'&&module.exports ? require('./report_layout.js') : null);
   if(!group?.validateGroup)throw Error('Group validator unavailable');
   group.validateGroup(obj);
  }else return false;
  return true;
 }catch{return false;}
}
function captionDisplay(caption,prefix=''){
 let content=caption.querySelector('.hrs-caption-content');
 if(!content){content=caption.ownerDocument.createElement('span');content.className='hrs-caption-content';content.textContent=caption.dataset.captionText||'';caption.replaceChildren(content);}
 let number=caption.querySelector('.hrs-caption-number');
 if(!number){number=caption.ownerDocument.createElement('span');number.className='hrs-caption-number';caption.prepend(number);}
 number.textContent=prefix;
}
function captionCopy(target,caption){
 target.replaceChildren(...[...caption.childNodes].map(n=>n.cloneNode(true)));
 // These are presentation copies of the real table caption. They navigate to
 // the same note, but must never register duplicate references or duplicate IDs.
 target.querySelectorAll('[id],[data-hrs-footnote-ref]').forEach(n=>{n.removeAttribute('id');n.removeAttribute('data-hrs-footnote-ref');});
}
function tableHeading(wrap){
 const tools=wrap.querySelector('.hrs-table-tools'),caption=wrap.querySelector('caption');if(!tools)return;
 let middle=tools.querySelector('.hrs-table-heading-caption');
 if(!middle){middle=wrap.ownerDocument.createElement('span');middle.className='hrs-table-heading-caption';tools.insertBefore(middle,tools.querySelector('.hrs-table-actions'));}
 if(caption)captionCopy(middle,caption);else middle.textContent='';
 if(tools.classList.contains('hrs-table-mini')&&caption?.dataset.captionText?.trim()){
  const kind=tools.querySelector('.hrs-table-kind');if(kind)captionCopy(kind,caption);
 }
 wrap.dataset.captionInTools='1';
}
function tableName(wrap){
 const caption=wrap.querySelector('caption')?.dataset.captionText?.trim();
 if(caption)return caption;
 const cells=[...(wrap.querySelector('table tr')?.cells||[])];
 const text=cells.map(cell=>cell.textContent.trim().replace(/\s+/g,' ')).filter(Boolean).join(' · ');
 return text.length>80?text.slice(0,79)+'…':text||'表格';
}
function objectTitle(entry,show=true,profile='engineering'){
 const {node,kind}=entry;
 if(kind==='table'){
  const name=tableName(node);
  if(profile==='free')return show&&entry.label?entry.label+(name==='表格'?'':'  '+name):name;
 }
 return node.querySelector(kind==='table'?'caption':'figcaption')?.textContent?.trim()||entry.label||(kind==='table'?'表格':'图');
}
function tableChrome(article,profile='engineering',editTable=null){
 const free=profile==='free',show=article.dataset.hrsShowObjectNumbers!=='0';
 for(const entry of indexDOM(article).items){
  if(entry.kind!=='table')continue;
  const wrap=entry.node,tools=wrap.querySelector('.hrs-table-tools');if(!tools)continue;
  tools.classList.toggle('hrs-table-mini',free);
  const kind=tools.querySelector('.hrs-table-kind');
  if(kind)kind.textContent=free?objectTitle(entry,show,'free'):'表格';
  tableHeading(wrap);
  let menu=tools.querySelector('.hrs-table-menu');
  if(!free){
   if(menu){const actions=tools.ownerDocument.createElement('div');actions.className='hrs-table-actions';
    for(const button of menu.querySelectorAll('button:not([data-table-edit])'))actions.append(button);menu.replaceWith(actions);}
   continue;
  }
  if(!menu){
   const actions=tools.querySelector('.hrs-table-actions');if(!actions)continue;
   menu=tools.ownerDocument.createElement('details');menu.className='hrs-table-menu';
   const summary=tools.ownerDocument.createElement('summary');summary.textContent='⋯';summary.title='表格操作';summary.setAttribute('aria-label','表格操作');
   const body=tools.ownerDocument.createElement('div');body.className='hrs-table-menu-body';
   body.append(...actions.children);menu.append(summary,body);actions.replaceWith(menu);
  }
  if(editTable&&!menu.querySelector('[data-table-edit]')){
   const button=tools.ownerDocument.createElement('button');button.type='button';button.dataset.tableEdit='1';button.textContent='编辑表格';
   button.addEventListener('click',()=>{menu.open=false;editTable(wrap.querySelector('table'));});menu.querySelector('.hrs-table-menu-body').prepend(button);
  }
 }
}
function applyDisplay(article,show=true,showEquations=false){
 article.dataset.hrsShowEquationNumbers=showEquations?'1':'0';
 const entries=indexDOM(article);article.dataset.hrsShowObjectNumbers=show?'1':'0';
 for(const entry of entries.items){
  if(entry.kind==='equation'){
   entry.node.querySelectorAll('.equation-number').forEach(n=>n.hidden=!showEquations);
   for(const link of article.querySelectorAll('a.object-xref'))if(link.getAttribute('href')==='#object-'+entry.id)link.textContent=showEquations?entry.label:'该公式';
   continue;
  }
  if(!['figure','table'].includes(entry.kind))continue;
  const caption=entry.node.querySelector(entry.kind==='table'?'caption':'figcaption');
  const fallback=entry.kind==='figure'?'图':'表';
  const text=caption?.dataset.captionText??'';
  const name=entry.kind==='table'?tableName(entry.node):(text||fallback);
  if(caption)captionDisplay(caption,show?entry.label+(text?'  ':''):'');
  for(const link of article.querySelectorAll('a.object-xref')){
   if(link.getAttribute('href')==='#object-'+entry.id)link.textContent=show?entry.label:name;
  }
 }
 article.querySelectorAll('.report-table-wrap').forEach(tableHeading);
 return entries;
}
const api={tableValidate,figureValidate,validObject,numbering,indexDOM,indexSource,sourceTexts,captionDisplay,tableHeading,tableName,objectTitle,tableChrome,applyDisplay};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.ReportObjectCatalog=api;
})(typeof window!=='undefined'?window:globalThis);
