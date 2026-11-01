/* Section ranges over the existing SourceMap, not a second Markdown parser. */
(function(root){
'use strict';
function index(source,map){
 if(map.source!==source)throw Error('章节定位已过期，请重新操作');
 const headings=map.blocks.filter(record=>record.type==='heading'),stack=[],counts=new Map();
 const sections=headings.map((record,i)=>{
  const level=record.token.depth;while(stack.length&&stack[stack.length-1].level>=level)stack.pop();
  const title=root.ReportNotebook.title(record.token),path=[...(stack[stack.length-1]?.path||[]),title];
  const ordinal=(counts.get(JSON.stringify(path))||0)+1;counts.set(JSON.stringify(path),ordinal);
  const raw=record.raw.replace(/(?:\r?\n[ \t]*)+$/,'');
  const tail=record.raw.slice(raw.length),newline=tail.startsWith('\r\n')?'\r\n':tail.startsWith('\n')?'\n':'';
  const next=headings.slice(i+1).find(item=>item.token.depth<=level);
  const item={start:record.start,end:next?.start??source.length,bodyStart:record.start+raw.length+newline.length,level,title,path,
   parent:stack[stack.length-1]?.start??null,id:record.objectId||null,key:record.objectId||JSON.stringify([path,ordinal])};
  stack.push(item);return item;
 });
 return sections;
}
function joined(left,middle,right,newline){
 const gap=text=>!text||/(?:\r?\n){2}$/.test(text)?'':text.endsWith('\n')?newline:newline+newline;
 return left+gap(left)+middle+(right?gap(middle):'')+right;
}
function move(source,sections,from,target,side='before'){
 const section=sections.find(item=>item.start===from),other=sections.find(item=>item.start===target);
 if(!section||!other)throw Error('章节位置已变化，请重新拖动');
 if(section.level!==other.level)throw Error('请拖到同级标题前后；升降级需明确操作');
 if(side!=='before'&&side!=='after')throw Error('无效的目录落点');
 if(section===other)return source;
 const destination=side==='before'?other.start:other.end;
 if(section.start<=destination&&destination<=section.end)return source;
 const part=source.slice(section.start,section.end),rest=source.slice(0,section.start)+source.slice(section.end);
 const at=destination>section.end?destination-(section.end-section.start):destination,newline=source.includes('\r\n')?'\r\n':'\n';
 return joined(rest.slice(0,at),part,rest.slice(at),newline);
}
function locate(sections,path){
 const choices=sections.filter(item=>path.length<=item.path.length&&path.every((title,i)=>item.path[item.path.length-path.length+i]===title));
 if(choices.length!==1)throw Error(choices.length?'标题不唯一，请选择完整专题/标题路径':'未找到目标标题');
 return choices[0];
}
function edit(source,section,text,operation){
 const newline=source.includes('\r\n')?'\r\n':'\n';text=String(text).replace(/\r\n?|\n/g,newline);
 let start=section.bodyStart,end=section.end;
 if(operation==='append')start=end;
 else if(operation==='prepend')end=start;
 else if(operation!=='replace-body')throw Error('不支持的整节操作');
 const left=source.slice(0,start),right=source.slice(end);
 const leading=left&&!left.endsWith('\n\n')&&!left.endsWith('\r\n\r\n')?newline:'';
 const trailing=right&&text&&!text.endsWith(newline+newline)?(text.endsWith(newline)?newline:newline+newline):'';
 return {start,end,replacement:leading+text+trailing};
}
const api={index,move,locate,edit};root.ReportSections=api;
if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
