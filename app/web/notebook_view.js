/* Free notebook projections over the existing lexer and full UTF-16 map. */
(function(root){
'use strict';
function title(token){
 const text=t=>t.tokens?t.tokens.map(text).join(''):t.type==='image'?(t.text||''):t.text??t.raw??'';
 return (token.tokens?.map(text).join('')||token.text||'未命名专题').replace(/\s+\{#sec-[^{}]+\}\s*$/,'').trim();
}
function definitionText(key,entry){
 const href=entry.href.replace(/[\\<>]/g,c=>'\\'+c),description=entry.title==null?'':' "'+entry.title.replace(/[\\"]/g,c=>'\\'+c)+'"';
 return '['+key+']: <'+href+'>'+description;
}
function index(source,map,tokens,catalog=null){
 if(map.source!==source)throw Error('专题索引与源快照不一致');
 const records=map.blocks,headers=records.filter(r=>r.type==='heading'&&r.token.depth===1),topics=[];
 if(!headers.length)topics.push({key:'all',title:'整篇文档',start:0,end:source.length});
 else{
  if(source.slice(0,headers[0].start).trim())topics.push({key:'preamble',title:'前言／未分组内容',start:0,end:headers[0].start});
  headers.forEach((r,i)=>topics.push({key:'topic-'+r.index,title:title(r.token),start:i===0&&!topics.length?0:r.start,end:headers[i+1]?.start??source.length,headingStart:r.start}));
 }
 const gaps=[];
 for(let i=0;i<records.length-1;i++){
  const record=records[i],next=records[i+1],raw=source.slice(record.start,next.start),tail=raw.match(/(?:\r?\n[ \t]*)+$/)?.[0]||'';
  const lines=Math.max(0,(tail.match(/\n/g)||[]).length-2);
  if(lines)gaps.push({after:record.index,start:next.start-tail.length,end:next.start,lines});
 }
 const definitions=new Map();
 for(const record of records)if(record.type==='hrsFootnoteDef'){
  if(!definitions.has(record.token.key))definitions.set(record.token.key,[]);
  definitions.get(record.token.key).push(record);
 }
 function at(position){return topics.find(t=>t.start<=position&&position<t.end)||topics.at(-1);}
 function extract(key,{forEditing=false}={}){
  const topic=topics.find(t=>t.key===key);if(!topic)throw Error('专题选择已过期，请重新选择');
  const selected=records.filter(r=>topic.start<=r.start&&r.start<topic.end),needed=new Set(),hrefs=new Set();
  function inspect(items){root.marked.walkTokens(items,t=>{if(t.type==='hrsFootnoteRef')needed.add(t.key);if(['image','link'].includes(t.type)&&t.href)hrefs.add(t.href);});}
  for(const record of selected){
   inspect([record.token]);
   for(const text of root.ReportObjectCatalog.sourceTexts(record,catalog?.byRecord.get(record.index)))inspect(root.SourceBlocks.lexer({},tokens.links).lex(text));
   for(const ref of record.references){const target=map.object(ref.target);if(!forEditing&&target&&(target.start<topic.start||target.start>=topic.end))throw Error('跨专题引用 '+ref.kind+':'+ref.target+' → '+at(target.start).title+'；请导出整篇或调整专题范围');}
  }
  const remove=forEditing?[]:selected.filter(r=>r.type==='hrsFootnoteDef');
  let markdown=source.slice(topic.start,topic.end);
  for(const r of remove.slice().reverse())markdown=markdown.slice(0,r.start-topic.start)+markdown.slice(r.end-topic.start);
  const newline=source.includes('\r\n')?'\r\n':'\n',append=[],dependencies=[];
  for(const key of needed){
   const matches=definitions.get(key)||[];
   if(matches.length!==1&&!forEditing)throw Error(matches.length?'脚注定义重复：'+key:'脚注未定义：'+key);
   for(const r of matches){if(forEditing&&r.start>=topic.start&&r.end<=topic.end)continue;append.push(r.raw);if(forEditing)dependencies.push({kind:'footnote',key,start:r.start,end:r.end,newline_tail:r.raw.match(/(?:\r?\n)+$/)?.[0]||''});}
  }
  const local=root.marked.lexer(root.SourceBlocks.normalized(markdown).text).links;
  for(const [key,entry] of Object.entries(tokens.links||{}))if(hrefs.has(entry.href)&&!local[key]){
   const r=forEditing?map.linkDefinitions.find(r=>r.key===key):null;
   append.push(r?r.raw:definitionText(key,entry).replace(/\n/g,newline));
   if(forEditing){if(!r)throw Error('共享链接定义无法可靠定位，请导出整篇或在源稿中整理该定义');dependencies.push({kind:'link',key,start:r.start,end:r.end,newline_tail:r.raw.match(/(?:\r?\n)+$/)?.[0]||''});}
  }
  const separator=append.length&&!markdown.endsWith(newline+newline)?newline+newline:'';
  if(append.length)markdown+=separator+append.join(newline+newline);
  return {topic,markdown,...(forEditing?{sync:{start:topic.start,end:topic.end,dependencies,appended_separator:separator}}:{})};
 }
 return {source,topics,gaps,at,extract};
}
function syncEdits(markdown,map,mapping){
 if(map.source!==markdown)throw Error('同步定位与临时稿快照不一致');
 const remove=[],edits=[];
 for(const dependency of mapping.dependencies){
  const matches=dependency.kind==='footnote'?map.blocks.filter(r=>r.type==='hrsFootnoteDef'&&r.token.key===dependency.key):map.linkDefinitions.filter(r=>r.key===dependency.key);
  if(matches.length>1)throw Error('共享定义重复，无法同步：'+dependency.key);
  if(!matches.length)continue; // Removing a local copy does not delete a shared source definition.
  const r=matches[0];remove.push(r);edits.push({...dependency,text:'newline_tail' in dependency?r.raw.replace(/(?:\r?\n)+$/,'')+dependency.newline_tail:r.raw});
 }
 let body=markdown;for(const r of remove.sort((a,b)=>b.start-a.start))body=body.slice(0,r.start)+body.slice(r.end);
 if(remove.length){
  const first=Math.min(...remove.map(r=>r.start));let tail=markdown.slice(first);
  for(const r of remove)tail=tail.slice(0,r.start-first)+tail.slice(r.end-first);
  if(!tail.trim()){
   body=markdown.slice(0,first);const separator=mapping.appended_separator||'';
   if(separator&&body.endsWith(separator))body=body.slice(0,-separator.length);
  }
 }
 return [{start:mapping.start,end:mapping.end,text:body,kind:'body'},...edits];
}
const api={index,title,syncEdits};root.ReportNotebook=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
