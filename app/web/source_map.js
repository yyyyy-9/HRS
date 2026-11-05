/* One UTF-16 range map for preview blocks, navigation, diagnostics and edits. */
(function(root){
'use strict';
function assertRange(source,range,raw=null,snapshot=source){
 if(snapshot!==source||!Number.isInteger(range.start)||!Number.isInteger(range.end)||range.start<0||range.end<range.start||range.end>source.length||raw!==null&&source.slice(range.start,range.end)!==raw)throw Error('源稿已变化，原定位范围过期；请重新定位或打开编辑');
 return range;
}
function changedRange(before,after){
 let start=0,oldEnd=before.length,end=after.length;
 while(start<oldEnd&&start<end&&before[start]===after[start])start++;
 if(start>0&&/[\uDC00-\uDFFF]/.test((before[start]||'')+(after[start]||'')))start--;
 while(oldEnd>start&&end>start&&before[oldEnd-1]===after[end-1]){oldEnd--;end--;}
 if(end<after.length&&/[\uDC00-\uDFFF]/.test(after[end])){end++;oldEnd++;}
 return {start,end,oldEnd};
}
function referenceRanges(tokens,source,base,normalized){
 const result=[];let cursor=0;
 for(const token of tokens||[]){
  const raw=token.raw||'',at=source.indexOf(raw,cursor);if(!raw||at<0)continue;cursor=at+raw.length;
  if(token.type==='reportImageGroup'||token.type==='reportEquation'||token.type==='code'||token.type==='codespan'||token.type==='html'||token.type==='image')continue;
  if(token.type==='link'&&!raw.startsWith('['))continue; // auto-linked URLs are destinations
  if(token.type==='table'){
   const cells=[...(token.header||[]),...(token.rows||[]).flat()].map(cell=>({...cell,raw:cell.text}));
   result.push(...referenceRanges(cells,raw,base+at,normalized));continue;
  }
  if(token.tokens){result.push(...referenceRanges(token.tokens,raw,base+at,normalized));continue;}
  if(token.items){result.push(...referenceRanges(token.items,raw,base+at,normalized));continue;}
  if(token.type!=='text'&&token.type!=='escape')continue;
  for(const match of raw.matchAll(/(?<![A-Za-z0-9_\\-])@(fig|tbl|sec|eq):([A-Za-z][A-Za-z0-9_-]{0,63})\b/g)){
   if(normalized.text[base+at+match.index-1]==='\\')continue;
   if(normalized.mathRanges?.some(part=>base+at+match.index>=part.from&&base+at+match.index<part.to))continue;
   result.push({raw:match[0],kind:match[1],target:match[2],start:normalized.sourceOffset(base+at+match.index),end:normalized.sourceOffset(base+at+match.index+match[0].length)});
  }
 }
 return result;
}
function create(source,tokens){
 const normalized=root.SourceBlocks.normalized(source,{tabs:true}),fences=root.SourceBlocks.scan(source,tokens)
  .filter(f=>['report-table','report-figure','report-image-group'].includes(f.language)),blocks=[];
 // One document-wide lexical mask: Marked may split \( and \) into
 // separate escape/text tokens, so masking per token is NOT reliable.
 normalized.mathRanges=(root.ReportTableContent?.tokenize(normalized.text)||[])
  .filter(part=>part.kind==='math').map(part=>({from:part.from,to:part.to}));
 const linkDefinitions=[];
 function skippedDefinitions(from,to){
  if(from>=to||!normalized.text.slice(from,to).trim())return;
  const tokenizer=root.SourceBlocks.lexer().tokenizer;
  while(from<to){
   const rest=normalized.text.slice(from,to),token=tokenizer.space(rest)||tokenizer.def(rest);
   if(!token?.raw)break;
   const end=from+token.raw.length;
   if(token.type==='def')linkDefinitions.push({key:token.tag,start:normalized.sourceOffset(from),end:normalized.sourceOffset(end),raw:source.slice(normalized.sourceOffset(from),normalized.sourceOffset(end))});
   from=end;
  }
 }
 let offset=0,fenceIndex=0,objectIndex=null;
 for(const token of tokens){
  const raw=token.raw||'',from=normalized.text.indexOf(raw,offset);if(!raw||from<0)throw Error('Markdown 块无法可靠定位');
  skippedDefinitions(offset,from);
  offset=from+raw.length;if(token.type==='space')continue;
  const start=normalized.sourceOffset(from),end=normalized.sourceOffset(offset);
  while(fenceIndex<fences.length&&fences[fenceIndex].from<start)fenceIndex++;
  const candidate=fences[fenceIndex],fence=candidate?.to<=end?candidate:null;
  const section=token.type==='heading'?root.ReportLayout?.heading(source.slice(start,end),token.depth):null;
  blocks.push({index:blocks.length,start,end,type:token.type,token,raw:source.slice(start,end),
   section,objectId:token.equation?.id||section?.id||(typeof fence?.object?.id==='string'?fence.object.id:null),
   references:referenceRanges([token],normalized.text.slice(from,offset),from,normalized)});
 }
 skippedDefinitions(offset,normalized.text.length);
 const lineStarts=[0];for(let i=0;i<source.length;i++)if(source[i]==='\n')lineStarts.push(i+1);
 function at(position){
  const pos=Math.max(0,Math.min(source.length,position));
  if(Number.isNaN(pos))return blocks.at(-1)||null;
  let lo=0,hi=blocks.length;
  while(lo<hi){const middle=(lo+hi)>>>1;if(blocks[middle].start<=pos)lo=middle+1;else hi=middle;}
  const previous=blocks[lo-1];
  return previous&&pos<previous.end?previous:blocks[lo]||blocks.at(-1)||null;
 }
 function lineRange(line){
  if(!Number.isInteger(line)||line<1||line>lineStarts.length)throw Error('检查行号不在当前文稿中');
  const start=lineStarts[line-1],end=(lineStarts[line]??source.length);
  return {start,end:Math.max(start,end-(source.slice(start,end).endsWith('\r\n')?2:source[end-1]==='\n'?1:0))};
 }
 function lineAt(position){
  const pos=Math.max(0,Math.min(source.length,Number(position)||0));let lo=0,hi=lineStarts.length;
  while(lo<hi){const middle=(lo+hi)>>>1;if(lineStarts[middle]<=pos)lo=middle+1;else hi=middle;}
  return lo;
 }
 function problemRange(problem,unit){
  const range=unit==='utf16'&&Number.isInteger(problem.start)&&Number.isInteger(problem.end)?{start:problem.start,end:problem.end}:lineRange(problem.line);
  assertRange(source,range);return {...range,objectId:problem.objectId||null,block:at(range.start)};
 }
 function setObjectId(record,id){
  if(blocks[record?.index]!==record)throw Error('对象记录不属于当前源码范围映射');
  record.objectId=id;objectIndex=null;
 }
 function object(id){
  if(!objectIndex){
   objectIndex=new Map();
   for(const block of blocks)if(block.objectId)objectIndex.set(block.objectId,objectIndex.has(block.objectId)?null:block);
  }
  return objectIndex.get(id)||null;
 }
 return {source,blocks,linkDefinitions,at,lineAt,lineRange,problemRange,setObjectId,object};
}
/* GFM task markers are nominated by Marked list_item tokens. Map the lexer's
 * de-indented item/quote text back through the existing UTF-16 source map;
 * neither code examples nor arbitrary HTML inputs become editable tasks. */
function taskRanges(source,record,marked,{frames=false,literals=false}={}){
 if(!['list','blockquote','hrsStyledList'].includes(record.type))return [];
 const normalized=root.SourceBlocks.normalized(record.raw,{tabs:true}),result=[];
 const positions=Array.from({length:normalized.text.length+1},(_,i)=>record.start+normalized.sourceOffset(i));
 // Marked trims trailing spaces from empty nested items. Align that token's
 // own characters through the parent's map; it remains the sole nominator.
 function trimMap(text){
  let out='',at=0;const indices=[],offsets=Array(text.length+1);
  for(const line of text.split('\n')){
   const kept=line.replace(/[ \t]+$/,'');
   for(let j=0;j<line.length;j++){offsets[at+j]=out.length;if(j<kept.length){indices.push(at+j);out+=line[j];}}
   at+=line.length;offsets[at]=out.length;
   if(at<text.length){indices.push(at);out+='\n';at++;}
  }
  offsets[text.length]=out.length;indices.push(text.length);return {text:out,indices,offsets};
 }
 function locate(raw,parent,map,cursor){
  let at=parent.indexOf(raw,cursor);
  if(at>=0)return {cursor:at+raw.length,map:map.slice(at,at+raw.length+1)};
  const original=trimMap(parent),token=trimMap(raw),core=token.text.replace(/\n+$/,'');
  if(!core)return null;
  at=original.text.indexOf(core,original.offsets[cursor]??original.text.length);
  if(at<0||original.indices[at]<cursor)return null;
  const local=token.offsets.map(offset=>map[original.indices[Math.min(at+offset,at+core.length)]]);
  return {cursor:original.indices[at+core.length],map:local};
 }
 function bodyMap(raw,body,map){
  const original=raw.split('\n'),lines=body.split('\n'),out=[];let at=0;
  if(lines.length>original.length)return null;
  for(let i=0;i<lines.length;i++){
   const line=lines[i],offset=line?original[i].indexOf(line):original[i].length;
   if(offset<0)return null;
   for(let j=0;j<line.length;j++)out.push(map[at+offset+j]);
   if(i<lines.length-1)out.push(map[at+original[i].length]);
   at+=original[i].length+1;
  }
  out.push(map[Math.min(raw.length,at-1)]);return out;
 }
 function visit(tokens,parent,map){
  let cursor=0;
  for(const token of tokens||[]){
   const raw=token.raw||'',found=raw&&locate(raw,parent,map,cursor);if(!found)continue;
   cursor=found.cursor;const local=found.map;
   if(literals&&['code','html','table','reportEquation','reportImageGroup'].includes(token.type)){
    if(Number.isInteger(local[0])&&Number.isInteger(local[raw.length]))result.push({start:local[0],end:local[raw.length]});
    continue;
   }
   if(token.type==='list')visit(token.items,raw,local);
   else if(token.type==='list_item'||token.type==='blockquote'){
    if(frames&&token.type==='list_item'){
     const first=raw.match(/^([ \t]*(?:[-+*]|\d{1,9}[.)])(?:[ \t]+(?:\[[ xX]\](?:[ \t]+|$))?|$))([^\n]*)/);
     if(first){const start=local[first[1].length],end=local[first[0].length];
      if(Number.isInteger(start)&&Number.isInteger(end))result.push({start,end,body:source.slice(start,end),marker:source.slice(source.lastIndexOf('\n',start-1)+1,start)});
     }
    }
    if(!frames&&!literals&&token.type==='list_item'&&token.task){
     const prefix=raw.match(/^ {0,3}(?:[-+*]|\d{1,9}[.)])[ \t]+\[([ xX])\](?:[ \t]+|$)/);
     if(prefix){const offset=prefix[0].indexOf('[')+1,start=local[offset];
      if(Number.isInteger(start)&&source[start-1]==='['&&source[start+1]===']')result.push({start,end:start+1,checked:!!token.checked});
     }
    }
    const projected=bodyMap(raw,token.text,local);if(projected)visit(token.tokens,token.text,projected);
   }else if(token.type==='hrsStyledList'){
    const offset=raw.indexOf(token.body);if(offset>=0)visit(marked.lexer(token.body),token.body,local.slice(offset));
   }
  }
 }
 visit([record.token],normalized.text,positions);return result;
}
function deindentCode(record){
 if(record?.type!=='code'||record.token?.codeBlockStyle!=='indented')throw Error('只能转换当前缩进代码块');
 return record.raw.replace(/^[ \t]+/gm,'');
}
/* Shared DOM endpoints for read-only source copying and existing prose edits. */
function inlineOffsets(target,range,serial){
 if(!target.contains(range.startContainer)||!target.contains(range.endContainer))return null;
 function offset(node,at,bias){
  function find(element,base){
   if(element===node){
    if(element.nodeType===3)return base+serial(element.ownerDocument.createTextNode(element.nodeValue.slice(0,at))).length;
    const children=[...element.childNodes],inner=children.map(serial).join(''),all=serial(element),head=all.indexOf(inner);
    return base+Math.max(0,head)+children.slice(0,at).map(serial).join('').length;
   }
   if(element.nodeType!==1||!element.contains(node))return null;
   const children=[...element.childNodes],inner=children.map(serial).join(''),all=serial(element),head=all.indexOf(inner);
   if(element.matches('.markdown-math,[data-xref-raw]')||element.tagName==='SUP'&&element.querySelector('[data-hrs-footnote-ref]')||head<0)return base+(bias==='end'?all.length:0);
   let cursor=base+head;for(const child of children){const result=find(child,cursor);if(result!==null)return result;cursor+=serial(child).length;}return null;
  }
  let cursor=0;for(const child of target.childNodes){const result=find(child,cursor);if(result!==null)return result;cursor+=serial(child).length;}
  return node===target?[...target.childNodes].slice(0,at).map(serial).join('').length:null;
 }
 const start=offset(range.startContainer,range.startOffset,'start'),end=offset(range.endContainer,range.endOffset,'end');
 return start===null||end===null?null:{start,end};
}
function textFrame(raw,headingLevel=null){
 const trailing=raw.match(/(?:\r?\n)+$/)?.[0]||'',line=raw.slice(0,raw.length-trailing.length);
 let prefix='',body=line,suffix='';
 if(headingLevel){
  const heading=line.match(/^ {0,3}(#{1,6})[ \t]+/);if(!heading||heading[1].length!==headingLevel)return null;
  prefix=heading[0];body=line.slice(prefix.length);
  const closing=body.match(/[ \t]+#+[ \t]*$/);if(closing){suffix=closing[0];body=body.slice(0,-suffix.length);}
  const anchor=body.match(/[ \t]+\{#sec-[A-Za-z0-9_-]{1,60}\}[ \t]*$/);if(anchor){suffix=anchor[0]+suffix;body=body.slice(0,-anchor[0].length);}
 }
 const leading=body.match(/^[ \t]*/)[0],ending=body.match(/[ \t]*$/)[0];
 prefix+=leading;body=body.slice(leading.length);if(ending.length<=body.length){body=body.slice(0,body.length-ending.length);suffix=ending+suffix;}
 return {prefix,body:root.SourceBlocks.normalized(body).text,suffix:suffix+trailing,newline:raw.includes('\r\n')?'\r\n':'\n'};
}
function replaceNormalizedText(original,next){
 const normalized=root.SourceBlocks.normalized(original),text=normalized.text;next=root.SourceBlocks.normalized(next).text;
 let from=0;while(from<text.length&&from<next.length&&text[from]===next[from])from++;
 let oldEnd=text.length,newEnd=next.length;while(oldEnd>from&&newEnd>from&&text[oldEnd-1]===next[newEnd-1]){oldEnd--;newEnd--;}
 const insert=next.slice(from,newEnd).replace(/\n/g,original.includes('\r\n')?'\r\n':'\n');
 return original.slice(0,normalized.sourceOffset(from))+insert+original.slice(normalized.sourceOffset(oldEnd));
}
function rebaseUnchanged(source,snapshot,range,raw){
 assertRange(snapshot,range,raw,snapshot);if(source===snapshot)return {...range};
 let prefix=0,a=snapshot.length,b=source.length;
 while(prefix<a&&prefix<b&&source[prefix]===snapshot[prefix])prefix++;
 while(a>prefix&&b>prefix&&snapshot[a-1]===source[b-1]){a--;b--;}
 let next;
 if(range.end<=prefix)next={...range};
 else if(range.start>=a)next={start:range.start+b-a,end:range.end+b-a};
 else throw Error('当前预览块的源文已变化，请等待刷新后编辑');
 return assertRange(source,next,raw,source);
}
const api={create,assertRange,changedRange,rebaseUnchanged,taskRanges,listFrames:(source,record,marked)=>taskRanges(source,record,marked,{frames:true}),literalRanges:(source,record,marked)=>taskRanges(source,record,marked,{literals:true}),textFrame,replaceNormalizedText,inlineOffsets,deindentCode};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.SourceMap=api;
})(typeof window!=='undefined'?window:globalThis);
