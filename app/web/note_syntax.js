/* Optional note presentation over the shared Marked lexer. Never rewrites source. */
(function(root){
'use strict';
const installed=new WeakSet();
const settings=root.ReportSettings||(typeof module!=='undefined'&&module.exports?require('./product_settings.js'):null);
const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const keyPattern='[A-Za-z0-9_\u4e00-\u9fff-]{1,80}';
const definition=new RegExp('^ {0,3}\\[\\^('+keyPattern+')\\]:[ \\t]*([^\\n]*)(?:\\n|$)');
const reference=new RegExp('^\\[\\^('+keyPattern+')\\]');
function installMarked(marked){
 if(installed.has(marked))return;installed.add(marked);
 marked.use({extensions:[{
  name:'hrsFootnoteDef',level:'block',
  // Marked calls a block start hint on src.slice(1). An apparent match at
  // offset zero may therefore be inside `[^key]: code`, not a source line.
  // At the true block start tokenizer() handles the definition directly.
  start(src){const match=src.match(new RegExp('\\n {0,3}\\[\\^'+keyPattern+'\\]:'));return match?match.index+1:undefined;},
  tokenizer(src){
   const first=src.match(definition);if(!first)return;
   let raw=first[0],body=first[2];
   const rest=src.slice(raw.length).match(/^(?:(?: {4}|\t)[^\n]*(?:\n|$)|\n(?=(?: {4}|\t)))*/)?.[0]||'';
   if(rest){raw+=rest;body+='\n'+rest.replace(/^(?: {4}|\t)/gm,'').replace(/\n$/,'');}
   return {type:'hrsFootnoteDef',raw,key:first[1],body};
  },renderer(){return '';}
 },{
  name:'hrsFootnoteRef',level:'inline',start(src){return src.indexOf('[^');},
  tokenizer(src){const m=src.match(reference);if(m)return {type:'hrsFootnoteRef',raw:m[0],key:m[1]};},
  renderer(t){return '<sup><a href="#" data-hrs-footnote-ref="'+esc(t.key)+'">'+esc(t.raw)+'</a></sup>';}
 },{
  name:'hrsHighlight',level:'inline',start(src){return src.indexOf('==');},
  tokenizer(src){
   const m=src.match(/^==(?=\S)((?:\\.|[^=\n]|=(?!=))*?\S|\S)==(?![=])/);
   if(m)return {type:'hrsHighlight',raw:m[0],text:m[1],tokens:this.lexer.inlineTokens(m[1])};
  },
  renderer(t){
   const text=this.parser.parseInline(t.tokens);
   if(this.parser.options.hrsRenderProfile==='engineering')return '<span data-hrs-highlight="markdown">'+text+'</span>';
   const palette=settings.highlights,choice=palette.choices.find(c=>c.marker&&t.text.startsWith(c.marker))||palette.choices.find(c=>c.id===palette.default),color=choice.color;
   return '<mark data-hrs-highlight="markdown" style="background-color:'+color+'">'+text+'</mark>';
  }
 }]});
}
function prepare(marked,tokens,{source=null,records=null,catalog=null,map=null}={}){
 // Reuse SourceMap's binary line index. Standalone callers build one prefix
 // index per document, rather than rescanning the source for every footnote.
 let lineAt=map?.lineAt;
 if(!lineAt){const starts=[0];for(let i=0;i<(source?.length||0);i++)if(source[i]==='\n')starts.push(i+1);
  lineAt=position=>{let lo=0,hi=starts.length;while(lo<hi){const mid=(lo+hi)>>>1;if(starts[mid]<=position)lo=mid+1;else hi=mid;}return lo;};}
 const definitions=new Map(),definitionRecords=new Map(),diagnostics=[],problems=[],first=new Map();
 for(const record of records||tokens.map(token=>({token}))){marked.walkTokens([record.token],t=>{
  if(t.type!=='hrsFootnoteDef')return;
  if(!definitionRecords.has(t.key))definitionRecords.set(t.key,[]);
  definitionRecords.get(t.key).push(record);
  if(definitions.has(t.key)){
   diagnostics.push('脚注定义重复：'+t.key);
   if(typeof source==='string'&&Number.isInteger(record.start)){
    const line=lineAt(record.start),firstLine=first.get(t.key);
    problems.push({severity:'error',code:'DUPLICATE_FOOTNOTE',start:record.start,end:record.end,line,
     message:'脚注标识 [^'+t.key+'] 重复定义，首次位于第 '+firstLine+' 行。同一来源可多次引用；不同来源请使用不同标识。'});
   }
  }else{definitions.set(t.key,t.body);if(typeof source==='string')first.set(t.key,lineAt(record.start));}
 });}
 const numbers=catalog?new Map():null,references=new Map();
 const visit=(items,record)=>marked.walkTokens(items,t=>{if(t.type==='hrsFootnoteRef'){
  if(!references.has(t.key))references.set(t.key,record);
  if(numbers&&!numbers.has(t.key))numbers.set(t.key,numbers.size+1);
 }});
 for(const record of records||tokens.map(token=>({token}))){
  if(record.token.type==='hrsFootnoteDef')continue;
  const object=catalog?.byRecord.get(record.index);
  if(object)for(const text of root.ReportObjectCatalog.sourceTexts(record,object))visit(marked.lexer(text),record);
  else visit([record.token],record);
 }
 for(const [key,record] of references)if(!definitions.has(key)&&typeof source==='string'&&Number.isInteger(record.start)){
  problems.push({severity:'error',code:'UNDEFINED_FOOTNOTE',start:record.start,end:record.end,line:lineAt(record.start),
   message:'脚注 [^'+key+'] 未定义；请在本稿补充定义或明确调整引用。'});
 }
 return {definitions,definitionRecords,diagnostics,problems,numbers,source};
}
function finalize(article,context,{render,prefix='hrs-note'}={}){
 const diagnostics=[...context.diagnostics],used=new Map();
 // Definitions are rendered once. Footnotes inside a definition stay literal;
 // recursive notes are not silently expanded into an unbounded graph.
 for(const anchor of [...article.querySelectorAll('a[data-hrs-footnote-ref]')]){
  const key=anchor.dataset.hrsFootnoteRef;
  if(!context.definitions.has(key)){
   anchor.replaceWith(document.createTextNode('[^'+key+']'));diagnostics.push('脚注未定义：'+key);continue;
  }
  if(!used.has(key))used.set(key,{number:context.numbers?.get(key)||used.size+1,refs:[]});
  const item=used.get(key),id=prefix+'-ref-'+item.number+'-'+(item.refs.length+1);
  anchor.id=id;anchor.href='#'+prefix+'-'+item.number;anchor.textContent=String(item.number);
  anchor.setAttribute('aria-label','脚注 '+item.number);anchor.classList.add('hrs-note-link');
  // On screen the real caption is mirrored into its compact/table toolbar.
  // Return to the visible table, rather than focusing a hidden caption link.
  item.refs.push(anchor.closest('caption')?.closest('.report-table-wrap')?.id||id);
 }
 if(used.size){
  const section=document.createElement('section');section.className='hrs-footnotes';section.setAttribute('aria-label','脚注');
  const heading=document.createElement('div');heading.className='hrs-footnotes-title';heading.textContent='注释与参考';
  const list=document.createElement('ol');section.append(heading,list);
  for(const [key,item] of used){
   const li=document.createElement('li');li.id=prefix+'-'+item.number;li.tabIndex=-1;li.value=item.number;li.dataset.hrsNoteKey=key;
   const record=context.definitionRecords?.get(key)?.[0];
   if(record&&Number.isInteger(record.start)){
    Object.assign(li.dataset,{mapIndex:String(record.index),start:String(record.start),end:String(record.end),type:'hrsFootnoteDef'});
    li._sourceRaw=context.source.slice(record.start,record.end);li._sourceDocument=context.source;
   }
   li.append(render(context.definitions.get(key)));
   li.querySelectorAll('[data-hrs-footnote-ref]').forEach(a=>a.replaceWith(document.createTextNode('[^'+a.dataset.hrsFootnoteRef+']')));
   item.refs.forEach((id,i)=>{
    const back=document.createElement('a');back.href='#'+id;back.className='hrs-note-link hrs-note-back';
    back.textContent=item.refs.length>1?'↩'+(i+1):'↩';back.setAttribute('aria-label','返回脚注 '+item.number+' 的引用 '+(i+1));li.append(' ',back);
   });list.append(li);
  }article.append(section);
 }
 return diagnostics;
}
function bindNavigation(container){
 container.addEventListener('click',event=>{
  const anchor=event.target.closest('a.hrs-note-link');if(!anchor||!container.contains(anchor))return;
  const id=anchor.getAttribute('href')?.slice(1),target=id&&document.getElementById(id);
  if(!target||!container.contains(target))return;
  event.preventDefault();event.stopPropagation();target.scrollIntoView({block:'center'});target.focus({preventScroll:true});
 },true);
}
function hasRich(token){return !!token&&(token.type==='hrsHighlight'||token.type==='hrsFootnoteRef'||token.type==='hrsFootnoteDef'||[...(token.tokens||[]),...(token.items||[])].some(hasRich));}
function clearHighlight(source,from,to,marked){
 const records=root.SourceMap.create(source,marked.lexer(root.SourceBlocks.normalized(source).text)).blocks;
 const changes=[];
 for(const block of records){
  if(!['paragraph','heading','blockquote'].includes(block.type)||to<block.start||from>block.end)continue;
  const raw=source.slice(block.start,block.end),norm=root.SourceBlocks.normalized(raw),protectedParts=[];
  function visit(tokens,parent,base=0){let cursor=0;for(const token of tokens||[]){const part=token.raw||'',at=parent.indexOf(part,cursor);if(!part||at<0)continue;cursor=at+part.length;const start=base+at;if(['codespan','code','escape'].includes(token.type))protectedParts.push([norm.sourceOffset(start),norm.sourceOffset(start+part.length)]);else if(token.tokens)visit(token.tokens,part,start);}}
  visit([block.token],norm.text);
  const pattern=/==([^=\n]+)==|<mark\b[^>]*>([\s\S]*?)<\/mark>/gi;let match;
  while((match=pattern.exec(raw))){
   const x=match.index,y=x+match[0].length,a=block.start+x,b=block.start+y;
   if(raw[x-1]==='\\'||protectedParts.some(([p,q])=>p<=x&&y<=q))continue;
   if(from===to?from>=a&&to<=b:from<b&&to>a)changes.push({from:a,to:b,text:match[1]??match[2]});
  }
 }
 if(!changes.length)return null;
 const start=Math.min(...changes.map(x=>x.from)),end=Math.max(...changes.map(x=>x.to));let text=source.slice(start,end);
 for(const change of changes.reverse())text=text.slice(0,change.from-start)+change.text+text.slice(change.to-start);
 return {from:start,to:end,text};
}
const api={installMarked,prepare,finalize,bindNavigation,hasRich,clearHighlight};root.ReportNotes=api;
if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
