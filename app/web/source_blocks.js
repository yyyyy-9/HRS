/* Source ranges only. Folding never rewrites the Markdown or object JSON. */
(function(root){
'use strict';
// GFM tables are foldable source ranges, not extra fenced objects. A fold
// never changes report.md or participates in formal table numbering.
const catalog=root.ReportObjectCatalog||(typeof module!=='undefined'&&module.exports?require('./object_catalog.js'):null);
function pipeTableAt(lines,index){
 const parser=root.ReportPipeTables;
 if(!parser||index+1>=lines.length)return null;
 const header=lines[index].text,delimiter=lines[index+1].text;
 if(/^ {4}|^\s*>/.test(header)||/^ {4}|^\s*>/.test(delimiter)||
    !header.includes('|')||!delimiter.includes('|'))return null;
 const cols=parser.split(header),seps=parser.split(delimiter);
 if(!cols.length||cols.length>30||seps.length!==cols.length||
    !seps.every(cell=>/^:?-{3,}:?$/.test(cell)))return null;
 let last=index+1,rows=1;
 while(last+1<lines.length&&rows<100){
  const next=lines[last+1].text;
  if(!next.trim()||/^ {4}|^\s*>/.test(next)||!next.includes('|'))break;
  // Never absorb Markdown structures or a later, independent table.
  if(/^ {0,3}(?:#{1,6}\s|[`~]{3,}|:::\s*)/.test(next))break;
  last++;rows++;
 }
 // Quarto caption belongs to the table only if the grammar recognizes it.
 let caption=null;
 // Directly adjacent is canonical. Historical one-blank captions are still
 // readable; the editor folds both as one object without modifying the source.
 let captionLine=last+1;
 if(captionLine<lines.length&&!lines[captionLine].text.trim())captionLine++;
 if(captionLine<lines.length&&captionLine<=last+2){
  try{caption=parser.parseCaption(lines[captionLine].text);}catch{}
  if(caption)last=captionLine;
 }
 const raw=lines.slice(index,last+1).map(item=>item.text).join('\n');
 try{parser.parseRaw(raw);}catch{return null;}
 return {last,rows,columns:cols.length,caption};
}
function scan(markdown,tokens=null){
 markdown=String(markdown);
 const lines=[];let from=0;
 for(const raw of String(markdown).split('\n')){lines.push({from,to:from+raw.length,text:raw.replace(/\r$/,'')});from+=raw.length+1;}
 // Only the existing Markdown lexer may nominate a raw HTML block. Balance
 // its outer element so a blank line inside a card does not split the fold.
 const htmlStarts=new Map();
 if(root.marked&&/^ {0,3}<(?:div|details|table|section|article|aside|figure|blockquote|pre)\b/im.test(markdown))try{
  const norm=normalized(markdown,{tabs:true});let at=0;
  for(const token of tokens||root.marked.lexer(norm.text)){
   if(token.type==='html')htmlStarts.set(norm.sourceOffset(at),token.raw);
   at+=token.raw.length;
  }
 }catch{}
 const blocks=[];
 for(let i=0;i<lines.length;i++){
  const html=htmlStarts.get(lines[i].from),outer=html?.match(/^ {0,3}<([a-z][a-z0-9-]*)\b/i);
  if(outer&&/^(div|details|table|section|article|aside|figure|blockquote|pre)$/i.test(outer[1])){
   const source=markdown.slice(lines[i].from),tags=/<!--[\s\S]*?-->|<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>|<\/?([a-z][a-z0-9-]*)\b(?:"[^"]*"|'[^']*'|[^'">])*>/gi;
   let depth=0,finish=0,match;
   while((match=tags.exec(source))){
    if(match[2]?.toLowerCase()!==outer[1].toLowerCase())continue;
    if(/^<\//.test(match[0]))depth--;else if(!/\/\s*>$/.test(match[0]))depth++;
    if(depth===0){finish=tags.lastIndex;break;}
   }
   if(finish){
    const to=lines[i].from+finish;let end=i;while(end+1<lines.length&&lines[end+1].from<to)end++;
    if(end>i){blocks.push({from:lines[i].from,to,bodyFrom:lines[i].from,bodyTo:to,body:markdown.slice(lines[i].from,to),language:'html',object:null,line:i+1,lines:end-i+1,automatic:true,summary:'HTML <'+outer[1].toLowerCase()+'> · '+(end-i+1)+' 行'});i=end;continue;}
   }
  }
  if(root.ReportLayout?.isGroupOpen(lines[i].text)){
   let end=i+1;while(end<lines.length&&!/^ {0,3}:::[ \t]*$/.test(lines[end].text))end++;
   if(end===lines.length)break;
   const to=lines[end].from+lines[end].text.length;
   const block={from:lines[i].from,to,bodyFrom:lines[i].to+1,bodyTo:lines[end].from,language:'report-image-group',body:markdown.slice(lines[i].from,to),line:i+1,lines:end-i+1,automatic:true,object:null};
   try{block.object=root.ReportLayout.parseGroup(block.body);}catch{}
   block.summary=block.object?'并排组图 · 已识别':'并排组图 · 源码待检查';
   blocks.push(block);i=end;continue;
  }
  const pipe=pipeTableAt(lines,i);
  if(pipe){
   const last=lines[pipe.last],first=lines[i],to=last.from+last.text.length;
   blocks.push({from:first.from,to,bodyFrom:first.from,bodyTo:to,
    body:markdown.slice(first.from,to),language:'gfm-pipe',object:null,
    line:i+1,lines:pipe.last-i+1,automatic:false,
    summary:'Markdown 表格 · '+pipe.rows+' 行 × '+pipe.columns+' 列'+
      (pipe.caption?' · '+pipe.caption.caption:'')});
   i=pipe.last;continue;
  }
  const opening=lines[i].text.match(/^ {0,3}(`{3,}|~{3,})([^\r\n]*)$/);
  if(!opening)continue;
  const marker=opening[1],language=opening[2].trim().split(/\s+/)[0].toLowerCase();
  if(marker[0]==='`'&&opening[2].includes('`'))continue;
  const closing=new RegExp('^ {0,3}'+marker[0]+'{'+marker.length+',}[ \\t]*$');
  let end=i+1;while(end<lines.length&&!closing.test(lines[end].text))end++;
  // Do not hide an unfinished fence (or interpret its inner lines as new blocks).
  if(end===lines.length)break;
  const bodyFrom=lines[i].to+1,bodyTo=lines[end].from;
  const block={from:lines[i].from,to:lines[end].from+lines[end].text.length,bodyFrom,bodyTo,language,
   body:markdown.slice(bodyFrom,bodyTo),line:i+1,lines:end-i+1,object:null,automatic:false};
  if(language==='report-table'||language==='report-figure'){
   block.automatic=true;
   try{const object=JSON.parse(block.body);if(object&&typeof object==='object'&&!Array.isArray(object))block.object=object;}catch{}
  }else if(language==='mermaid')block.automatic=true;
  if(language==='report-table'){
   const data=block.object,valid=data?.schema==='report-table-v1'&&Array.isArray(data.rows)&&data.rows.length&&Array.isArray(data.rows[0]);
   block.summary=valid?'增强表格 · 已识别':'结构化表格 · 源码待检查';
  }else if(language==='report-figure'){
   const data=block.object,valid=data?.schema==='report-figure-v1'&&['mermaid','image'].includes(data.kind);
   block.summary=valid?'图形对象 · 已识别':'图形对象 · 源码待检查';
  }else block.summary=(language==='mermaid'?'Mermaid 流程图':(language||'普通')+' 代码')+' · '+(end-i-1)+' 行';
  blocks.push(block);i=end;
 }
 // Derived fold numbers share the same policy as the editable preview
 // and the exported offline reader; never count merely parseable JSON.
 if(catalog){
  const indexed=catalog.numbering(blocks.map(block=>{
   const {language,object}=block;
   const kind=language==='report-table'||language==='gfm-pipe'?'table':
    language==='report-figure'||language==='report-image-group'||language==='mermaid'?'figure':null;
   return {kind,id:object?.id||null,
    sourceKind:language==='gfm-pipe'?'gfm-pipe':language==='report-table'?'enhanced':null,
    numbered:true,
    valid:['gfm-pipe','mermaid'].includes(language)?true:!!(kind&&object&&catalog.validObject(language,object))};
  })).items;
  blocks.forEach((block,i)=>{
   const entry=indexed[i],obj=block.object;
   if(!entry.valid){
    if(block.language==='report-table')block.summary='结构化表格 · 源码待检查';
    else if(block.language==='report-figure')block.summary='图形对象 · 源码待检查';
    else if(block.language==='report-image-group')block.summary='并排组图 · 源码待检查';
   }
   if(!entry.number)return;
   if(block.language==='report-table')block.summary=`表 ${entry.number}：${obj.caption||'未填写表题'} · ${obj.rows.length} 行 × ${obj.rows[0].length} 列`;
   else if(block.language==='gfm-pipe')block.summary=`表 ${entry.number}：${block.summary}`;
   else if(block.language==='mermaid')block.summary=`图 ${entry.number}：Mermaid 流程图`;
   else if(block.language==='report-figure')block.summary=`图 ${entry.number}：${obj.caption||'未填写图题'} · ${obj.kind==='mermaid'?'Mermaid 流程图':'图片对象'}`;
   else if(block.language==='report-image-group')block.summary=`图 ${entry.number}：${obj.caption||'未填写图题'} · ${obj.images.length} 张组图 / 每行 ${obj.columns} 列`;
  });
 }
 return blocks;
}
function readObject(raw,language){
 const blocks=scan(raw),block=blocks[0];
 if(blocks.length!==1||!block||block.language!==language||raw.slice(0,block.from).trim()||raw.slice(block.to).trim())throw Error('对象代码块格式错误');
 return JSON.parse(block.body);
}
function normalized(markdown,{tabs=false}={}){
 // Marked's block lexer expands only the first run of indentation tabs.
 // Map that same lexical view back to the unchanged UTF-16 source, including
 // CRLF and positions after mixed tabs/spaces. Interior tabs stay literal.
 const changes=[],parts=[];let cursor=0,length=0;
 for(const match of markdown.matchAll(/\r\n?|^( *)(\t+)/gm)){
  if(match[2]&&!tabs)continue;
  const leading=match[1]||'',start=match.index+leading.length;
  const prefix=markdown.slice(cursor,start);parts.push(prefix);length+=prefix.length;
  if(match[2]){
   for(let i=0;i<match[2].length;i++){
    changes.push({start:length,end:length+4,source:start+i,after:start+i+1});parts.push('    ');length+=4;
   }
  }else{
   changes.push({start:length,end:length+1,source:start,after:start+match[0].length});parts.push('\n');length++;
  }
  cursor=match.index+match[0].length;
 }
 parts.push(markdown.slice(cursor));const text=parts.join('');
 return {text,sourceOffset(position){
  let lo=0,hi=changes.length;while(lo<hi){const middle=(lo+hi)>>>1;if(changes[middle].end<=position)lo=middle+1;else hi=middle;}
  if(changes[lo]?.start<=position)return changes[lo].source;
  return position+(lo?changes[lo-1].after-changes[lo-1].end:0);
 }};
}
function replacement(original,snippet){
 const newline=original.includes('\r\n')?'\r\n':'\n';
 const trailing=original.match(/(?:\r?\n)+$/)?.[0]||'';
 return snippet.replace(/\r?\n/g,newline)+trailing;
}
function promoteImages(source,map,{create,serialize}){
 if(map.source!==source)throw Error('图片定位与源稿快照不一致');
 const edits=[],skipped=[];
 for(const record of map.blocks){
  if(record.type!=='paragraph')continue;
  const tokens=(record.token.tokens||[]).filter(t=>t.raw?.trim());
  if(tokens.length!==1||tokens[0].type!=='image')continue;
  const image=tokens[0];if(!/^assets\/[A-Za-z0-9_.-]+$/.test(image.href))continue;
  const alt=image.text||'',caption=image.title||image.text||'';
  if(alt.length>300||caption.length>300){skipped.push(record.start);continue;}
  const object=create(image.href);object.alt=alt;object.caption=caption;
  edits.push({start:record.start,end:record.end,text:replacement(record.raw,serialize(object))});
 }
 let markdown=source;for(const edit of edits.slice().reverse())markdown=markdown.slice(0,edit.start)+edit.text+markdown.slice(edit.end);
 return {markdown,edits,skipped};
}
function lexer(options={},links=null){
 const instance=new root.marked.Lexer({...root.marked.defaults,...options});
 if(links)Object.assign(instance.tokens.links,links);
 return instance;
}
const api={scan,readObject,normalized,replacement,lexer,promoteImages};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.SourceBlocks=api;
})(typeof window!=='undefined'?window:globalThis);
