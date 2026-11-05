/* HF8 PF11: GFM pipe tables are editable views of the original Markdown.
 * No migration on open/save. Only advanced unsupported edits prompt promotion.
 * Parse raw source, not old Marked cell tokens (which mishandle `a|b`).
 */
(function(root){
'use strict';
const CAPTION=/^ {0,3}:[ \t]+([^\r\n]*?)(?:[ \t]+\{#(tbl-[A-Za-z0-9_-]{1,60})\})?[ \t]*$/;
const DELIMITER=/^:?-{3,}:?$/;
const MAX_ROWS=100,MAX_COLS=30;
const content=root.ReportTableContent||(typeof require==='function'?require('./table_content.js'):null);
function mathRanges(text){return new Map(content.tokenize(text,{table:true}).filter(p=>p.kind==='math').map(p=>[p.from,p.to]));}
function split(line){
 let text=String(line).replace(/\r$/,'').trim();
 if(text.startsWith('|'))text=text.slice(1);
 if(text.endsWith('|')){
  let n=0;for(let i=text.length-2;i>=0&&text[i]==='\\';i--)n++;
  if(n%2===0)text=text.slice(0,-1);
 }
 const cells=[],math=mathRanges(text);let part='',ticks=0;
 for(let i=0;i<text.length;i++){
  if(!ticks&&math.has(i)){
   const end=math.get(i);
   // Keep the existing GFM escape layer, including tables saved by older HRS.
   // Complete math protects the boundary; it does not bypass Markdown escapes.
   part+=text.slice(i,end).replace(/\\+\|/g,value=>'\\'.repeat(Math.floor((value.length-1)/2))+'|');i=end-1;continue;
  }
  const c=text[i];
  if(c==='\\'){
   let j=i+1;while(j<text.length&&text[j]==='\\')j++;
   const n=j-i;
   if(text[j]==='|'&&!ticks){
    part+='\\'.repeat(Math.floor(n/2));
    if(n%2){part+='|';i=j;continue;}
    i=j-1;continue;
   }
   part+='\\'.repeat(n);i=j-1;continue;
  }
  if(c==='`'){
   let n=1;while(text[i+n]==='`')n++;
   if(!ticks)ticks=n;else if(ticks===n)ticks=0;
   part+=text.slice(i,i+n);i+=n-1;continue;
  }
  if(c==='|'&&!ticks){cells.push(part.trim());part='';continue;}
  part+=c;
 }
 cells.push(part.trim());return cells;
}
function parseCaption(raw){
 const identity=String(raw).trim().match(/^:[ \t]+\{#(tbl-[A-Za-z0-9_-]{1,60})\}$/);if(identity)return {caption:'',id:identity[1]};
 const found=String(raw).trimEnd().match(CAPTION);
 if(!found)return null;
 const caption=found[1].trim();if(!caption||caption.length>300)throw Error('表题须是 1–300 字的单行文字');
 return {caption,id:found[2]||null};
}
function parseRaw(raw){
 if(typeof raw!=='string'||raw.length>750000)throw Error('Markdown 表格内容超过限制');
 const newline=raw.includes('\r\n')?'\r\n':'\n';
 const lines=raw.replace(/\r\n?/g,'\n').split('\n');
 while(lines.length&&!lines[0].trim())lines.shift();
 const header=split(lines[0]||'');const sep=split(lines[1]||'');
 if(header.length<1||header.length>MAX_COLS||sep.length!==header.length||sep.some(x=>!DELIMITER.test(x)))throw Error('不是完整的 GFM 管道表格');
 const align=sep.map(x=>x.startsWith(':')&&x.endsWith(':')?'center':x.endsWith(':')?'right':x.startsWith(':')?'left':null);
 const rows=[header],overflow=[];let caption=null,seenCaption=false,blankLines=0;
 for(let i=2;i<lines.length;i++){
  const rawLine=lines[i];if(!rawLine.trim()){blankLines++;continue;}
  if(CAPTION.test(rawLine)){
   if(blankLines>1)throw Error('表题必须紧贴表格；旧稿最多允许一个空行');
   if(seenCaption)throw Error('重复的表题');caption=parseCaption(rawLine);seenCaption=true;continue;
  }
  if(seenCaption)throw Error('表题后不能附加新的表格内容');
  if(blankLines)throw Error('表格数据行之间不能插入空行');
  const cells=split(rawLine);
  if(cells.length>header.length)overflow.push({row:rows.length,cells:cells.slice(header.length)});
  while(cells.length<header.length)cells.push('');
  cells.length=header.length;
  if(rows.length>=MAX_ROWS)throw Error('Markdown 表格最多 100 行（含表头）');
  if(cells.some(x=>x.length>30000||/[\r\n]/.test(x)))throw Error('表格单元格不合法');
  rows.push(cells);
 }
 const model={schema:'report-table-v1',id:caption?.id||'tbl-pipe-preview',caption:caption?.caption||'',rows:rows.map(row=>row.map(text=>({text,rowspan:1,colspan:1}))),align,sourceKind:'gfm-pipe'};
 return {model,hasStableId:!!caption?.id,caption:caption?.caption||'',id:caption?.id||null,newline,overflow};
}
function at(lines,index,{caption:includeCaption=true}={}){
 if(index+1>=lines.length)return null;
 const header=lines[index].text,delimiter=lines[index+1].text;
 if(/^ {4}|^\s*>/.test(header)||/^ {4}|^\s*>/.test(delimiter)||!header.includes('|')||!delimiter.includes('|'))return null;
 const cols=split(header),seps=split(delimiter);
 if(!cols.length||cols.length>MAX_COLS||seps.length!==cols.length||!seps.every(cell=>DELIMITER.test(cell)))return null;
 let last=index+1,rows=1;
 while(last+1<lines.length&&rows<MAX_ROWS){
  const next=lines[last+1].text;
  if(!next.trim()||/^ {4}|^\s*>/.test(next)||!next.includes('|')||/^ {0,3}(?:#{1,6}\s|[`~]{3,}|:::\s*)/.test(next))break;
  last++;rows++;
 }
 if(rows===MAX_ROWS&&lines[last+1]?.text.trim()&&lines[last+1].text.includes('|'))return null;
 let caption=null,captionLine=last+1;
 if(includeCaption){
  if(captionLine<lines.length&&!lines[captionLine].text.trim())captionLine++;
  if(captionLine<lines.length&&captionLine<=last+2){try{caption=parseCaption(lines[captionLine].text);}catch{}if(caption)last=captionLine;}
 }
 const raw=lines.slice(index,last+1).map(item=>item.text).join('\n');
 try{parseRaw(raw);}catch{return null;}
 return {last,rows,columns:cols.length,caption};
}
const installed=new WeakSet();
function installMarked(marked){
 if(installed.has(marked))return;installed.add(marked);
 marked.use({tokenizer:{table(src){
  // Fast negative path; never scan a whole document for every paragraph.
  const first=src.indexOf('\n');if(first<0||!src.slice(0,first).includes('|'))return false;
  const second=src.indexOf('\n',first+1),sep=src.slice(first+1,second<0?src.length:second);
  if(!sep.includes('|')||!split(sep).every(cell=>DELIMITER.test(cell)))return false;
  const lines=[];let cursor=0;
  while(cursor<src.length&&lines.length<MAX_ROWS+3){
   const end=src.indexOf('\n',cursor),to=end<0?src.length:end+1,raw=src.slice(cursor,to);lines.push({text:raw.replace(/\r?\n$/,''),raw});cursor=to;
  }
  const extent=at(lines,0,{caption:false});if(!extent)return false;
  const raw=lines.slice(0,extent.last+1).map(line=>line.raw).join(''),parsed=parseRaw(raw),inline=text=>({text,tokens:this.lexer.inline(text)});
  return {type:'table',raw,header:parsed.model.rows[0].map(cell=>inline(cell.text)),align:parsed.model.align,rows:parsed.model.rows.slice(1).map(row=>row.map(cell=>inline(cell.text)))};
 }}});
}
function formatCell(value){
 const text=String(value);if(/[\r\n]/.test(text))throw Error('单元格中有多行内容，必须转换为增强表格');
 let ticks=0,out='';
 for(let i=0;i<text.length;i++){
  if(text[i]==='`'){
   let n=1;while(text[i+n]==='`')n++;
   if(!ticks)ticks=n;else if(ticks===n)ticks=0;
   out+=text.slice(i,i+n);i+=n-1;
  }else if(text[i]==='\\'&&!ticks){
   let j=i+1;while(text[j]==='\\')j++;
   const n=j-i;
   // Literal slashes before a cell pipe need doubled escapes plus \|.
   if(text[j]==='|'){
    out+='\\'.repeat(2*n+1)+'|';i=j;
   }else{out+='\\'.repeat(n);i=j-1;}
  }else if(text[i]==='|'&&!ticks){out+='\\|';}
  else out+=text[i];
 }
 return out;
}
function requiresPromotion(model){
 if(model.columnWidths!==undefined||model.verticalAlign!==undefined)return true;
 if(model.rows.some(row=>row.some(cell=>!cell||cell.rowspan!==1||cell.colspan!==1||/[\r\n]/.test(cell.text))))return true;
 return false;
}
function stringify(model,{newline='\n',id=null,withCaption=false}={}){
 if(requiresPromotion(model))throw Error('合并单元格、多行块、精确列宽或垂直对齐不能保存为管道表格');
 const rows=model.rows,columns=rows[0]?.length;
 if(!columns||columns>MAX_COLS||rows.length>MAX_ROWS||rows.some(row=>row.length!==columns))throw Error('不规则的 Markdown 表格');
 const align=Array.isArray(model.align)?model.align:[];
 const sep=Array.from({length:columns},(_,i)=>({left:':---',right:'---:',center:':---:',null:'---'})[align[i]||'null']||'---');
 const line=row=>'| '+row.map(cell=>formatCell(cell.text)).join(' | ')+' |';
 const lines=[line(rows[0]),'| '+sep.join(' | ')+' |',...rows.slice(1).map(line)];
 if(withCaption||model.caption.trim()||id){
  if(model.caption.trim()||id)lines.push(': '+model.caption.trim()+(id?' {#'+id+'}':''));
 }
 return lines.join(newline);
}
function promoted(model,id){
 const obj={schema:'report-table-v1',id,caption:model.caption,rows:model.rows};
 if(model.columnWidths!==undefined)obj.columnWidths=model.columnWidths;
 if(Array.isArray(model.align)&&model.align.some(Boolean))obj.align=model.align.slice();
 if(model.verticalAlign!==undefined)obj.verticalAlign=model.verticalAlign;
 return obj;
}
const api={split,parseCaption,parseRaw,at,installMarked,stringify,promoted,requiresPromotion};
if(typeof module!=='undefined'&&module.exports)module.exports=api;root.ReportPipeTables=api;
if(root.marked)installMarked(root.marked);
})(typeof window!=='undefined'?window:globalThis);
