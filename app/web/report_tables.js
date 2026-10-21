/* HTML Report Studio: table operations. Shared by browser UI and Node tests. */
(function(root){
'use strict';
const cloneReport=(typeof module!=='undefined'&&module.exports ? require('./report_clone.js') : root.ReportClone).clone;
const cell=(text='')=>({text:String(text),rowspan:1,colspan:1});
// A clipboard cell may include empty paragraph wrappers from Excel/WPS.
// Remove only entirely-blank lines at the *edges*. Never collapse interior
// newlines or strip meaningful indentation in code/formulas.
function cleanPastedCellText(text){
 const lines=String(text).replace(/\r\n?/g,'\n').split('\n');
 while(lines.length>1&&!lines[0].trim())lines.shift();
 while(lines.length>1&&!lines[lines.length-1].trim())lines.pop();
 return lines.join('\n');
}

// Keep real cell.text untouched (including a deliberate final <br> from
// WPS/Excel). The *preview* hides only empty surrounding visual lines, so
// import/round-trip still preserves the original source byte-for-byte.
function compactDisplayText(value){
 const lines=String(value).split(/\r\n|\r|\n/);
 while(lines.length>1&&!lines[0].trim())lines.shift();
 while(lines.length>1&&!lines.at(-1).trim())lines.pop();
 return lines.join('\n');
}
function parseTSV(input){
 const text=String(input).replace(/\r\n?/g,'\n');
 if(text.length>650000)throw Error('粘贴文本超过 650 KB');
 const rows=[];let row=[],value='',quoted=false,started=false,afterQuote=false;
 function field(){row.push(value);value='';quoted=false;started=false;afterQuote=false;}
 function line(){field();rows.push(row);row=[];}
 for(let i=0;i<text.length;i++){
  const x=text[i];
  if(quoted){
   if(x==='"'){if(text[i+1]==='"'){value+='"';i++;}else{quoted=false;afterQuote=true;}}
   else value+=x;
  }else if(x==='\t'){field();}
  else if(x==='\n'){line();}
  else if(x==='"'&&!started){quoted=true;started=true;}
  else{value+=x;started=true;}
 }
 if(quoted)throw Error('Excel 引号单元格没有正确闭合');
 // Excel appends one record separator to the whole copied selection.
 if(row.length||value!==''||text.length===0||text[text.length-1]!=='\n')line();
 if(rows.length<1)rows.push(['']);
 const max=Math.max(...rows.map(r=>r.length));
 rows.forEach(r=>{while(r.length<max)r.push('');});
 return rows.map(r=>r.map(v=>cell(cleanPastedCellText(v))));
}
function parseHTML(input){
 if(typeof DOMParser==='undefined')return null;
 const html=String(input||'');if(!html.trim()||html.length>1100000)return null;
 // Keep only a single table. Excel often puts external stylesheet links,
 // conditional-formatting images and metadata before it. A detached DOMParser
 // document may still fetch resources, so NEVER parse these active nodes/URLs.
 const fragment=html.match(/<table\b[^>]*>[\s\S]*?<\/table\s*>/i)?.[0];
 if(!fragment)return null;
 if(/<\s*(?:script|style|img|iframe|object|embed|link|form|svg|video|audio|source|base|meta)\b/i.test(fragment) ||
    /\b(?:src|srcset|href|poster|background)\s*=/i.test(fragment) ||
    /url\s*\(|@import|expression\s*\(/i.test(fragment))return null;
 const doc=new DOMParser().parseFromString(fragment,'text/html');
 const table=doc.querySelector('table');if(!table)return null;
 const trs=[...table.rows];if(!trs.length)return null;
 const rows=[];let max=0;
 // Preserve explicit BR while trimming only generated empty paragraph separators.
 let explicitBreak='\uE000';while(fragment.includes(explicitBreak))explicitBreak+='\uE000';
 function textOnly(node){
  if(node.nodeType===3)return node.nodeValue||'';
  if(node.nodeType!==1)return '';
  const name=node.tagName.toLowerCase();
  if(['script','style','iframe','object','svg','img','form'].includes(name))return '';
  if(name==='br')return explicitBreak;
  const children=[...node.childNodes];
  // Block containers separate following content. An explicit final <br> is
  // author content and must not be trimmed together with a generated separator.
  return children.map((child,index)=>textOnly(child)+
   (index<children.length-1&&child.nodeType===1&&['p','div'].includes(child.tagName.toLowerCase())?'\n':'')).join('');
 }
 trs.forEach((tr,r)=>{
  if(!rows[r])rows[r]=[];
  let c=0;
  for(const td of tr.cells){
   while(rows[r][c]!==undefined)c++;
   let rs=td.rowSpan||1,cs=td.colSpan||1;
   if(rs<1||cs<1||r+rs>100||cs>30)throw Error('Excel 合并单元格范围超限');
   const value=cleanPastedCellText(textOnly(td)).split(explicitBreak).join('\n');
   if(value.length>30000)throw Error('单元格内容过长');
   rows[r][c]={text:value,rowspan:rs,colspan:cs};
   for(let rr=r;rr<r+rs;rr++){
    if(!rows[rr])rows[rr]=[];
    for(let cc=c;cc<c+cs;cc++){
     if(rr===r&&cc===c)continue;
     if(rows[rr][cc]!==undefined)throw Error('Excel HTML 合并区域重叠');
     rows[rr][cc]=null;
    }
   }
   c+=cs;max=Math.max(max,c);
  }
 });
 if(rows.length>100||max>30)throw Error('Excel 区域超过 100×30');
 rows.forEach(row=>{for(let c=0;c<max;c++)if(row[c]===undefined)row[c]=cell('');});
 return rows;
}
function matrixDimensions(matrix){
 if(!Array.isArray(matrix)||!matrix.length||matrix.length>100||!Array.isArray(matrix[0]))throw Error('粘贴区域无效');
 let cols=matrix[0].length;
 if(cols<1||cols>30||matrix.some(row=>!Array.isArray(row)||row.length!==cols))throw Error('粘贴区域须为规则网格');
 return [matrix.length,cols];
}
function logicalGrid(table){
 const rows=table.rows,[height,width]=matrixDimensions(rows);
 const owners=Array.from({length:height},()=>Array(width).fill(null)),anchors=[];
 for(let r=0;r<height;r++)for(let c=0;c<width;c++){
  const value=rows[r][c];
  if(value===null){if(!owners[r][c])throw Error('合并占位没有主单元格');continue;}
  if(!value||typeof value.text!=='string'||value.text.length>30000||!Number.isInteger(value.rowspan)||!Number.isInteger(value.colspan)||value.rowspan<1||value.colspan<1||r+value.rowspan>height||c+value.colspan>width)throw Error('单元格内容或合并范围无效');
  const anchor={r,c,value};anchors.push(anchor);
  for(let rr=r;rr<r+value.rowspan;rr++)for(let cc=c;cc<c+value.colspan;cc++){
   if(owners[rr][cc])throw Error('合并区域重叠');
   if((rr!==r||cc!==c)&&rows[rr][cc]!==null)throw Error('合并区域必须使用 null 占位');
   owners[rr][cc]=anchor;
  }
 }
 return {height,width,owners,anchors};
}
function validateWidths(widths,cols){
 if(widths===undefined)return;
 if(!Array.isArray(widths)||widths.length!==cols||widths.some(w=>typeof w!=='number'||!Number.isFinite(w)||w<=0||w>100)||Math.abs(widths.reduce((a,b)=>a+b,0)-100)>0.000001)throw Error('列宽须为与列数相同的正数百分比，合计 100');
}
function normalizeWidths(weights){
 if(!weights.length||weights.some(w=>typeof w!=='number'||!Number.isFinite(w)||w<=0))throw Error('列宽权重无效');
 const total=weights.reduce((a,b)=>a+b,0),next=weights.map(w=>100*w/total);
 next[next.length-1]=100-next.slice(0,-1).reduce((a,b)=>a+b,0);validateWidths(next,next.length);return next;
}
function getColumnWidths(table){
 const cols=table.rows[0].length;validateWidths(table.columnWidths,cols);
 return table.columnWidths?table.columnWidths.slice():normalizeWidths(Array(cols).fill(1));
}
function makeRows(height,width,anchors){
 const rows=Array.from({length:height},()=>Array(width));
 for(const anchor of anchors){
  const {r,c,value}=anchor;
  for(let rr=r;rr<r+value.rowspan;rr++)for(let cc=c;cc<c+value.colspan;cc++){
   if(rr>=height||cc>=width||rows[rr][cc]!==undefined)throw Error('操作后的合并范围越界或重叠');
   rows[rr][cc]=(rr===r&&cc===c)?cloneReport(value):null;
  }
 }
 for(const row of rows)for(let c=0;c<width;c++)if(row[c]===undefined)row[c]=cell();
 logicalGrid({rows});return rows;
}
function axisIndex(grid,axis,index,inserting=false){
 if(axis!=='row'&&axis!=='column')throw Error('操作轴无效');
 const size=axis==='row'?grid.height:grid.width;
 if(!Number.isInteger(index)||index<0||index>size-(inserting?0:1))throw Error('行列位置无效');
 return size;
}
function insertAxis(table,axis,index){
 const grid=logicalGrid(table),size=axisIndex(grid,axis,index,true),isRow=axis==='row';
 validateWidths(table.columnWidths,grid.width);
 if(size>=(isRow?100:30))throw Error(isRow?'最多 100 行':'最多 30 列');
 const anchors=grid.anchors.map(original=>{
  const anchor=cloneReport(original),key=isRow?'r':'c',span=isRow?'rowspan':'colspan',start=anchor[key];
  if(start>=index)anchor[key]++;
  else if(start+anchor.value[span]>index)anchor.value[span]++;
  return anchor;
 });
 const rows=makeRows(grid.height+(isRow?1:0),grid.width+(isRow?0:1),anchors);
 let widths;
 if(!isRow&&table.columnWidths){const share=100/(grid.width+1);widths=getColumnWidths(table).map(w=>w*(100-share)/100);widths.splice(index,0,share);widths=normalizeWidths(widths);}
 table.rows=rows;if(widths)table.columnWidths=widths;
 if(!isRow&&Array.isArray(table.align))table.align.splice(index,0,null);
 return {index};
}
function deletionPlan(table,axis,index){
 const grid=logicalGrid(table),size=axisIndex(grid,axis,index),isRow=axis==='row';
 if(size<=1)throw Error(isRow?'至少保留一行':'至少保留一列');
 validateWidths(table.columnWidths,grid.width);
 const anchors=[],removed=[];
 for(const original of grid.anchors){
  const anchor=cloneReport(original),key=isRow?'r':'c',span=isRow?'rowspan':'colspan',start=anchor[key];
  if(start>index)anchor[key]--;
  else if(start+anchor.value[span]>index){
   if(anchor.value[span]===1){removed.push(anchor);continue;}
   anchor.value[span]--; // Deleting the anchor moves its text to the surviving part.
  }
  anchors.push(anchor);
 }
 const rows=makeRows(grid.height-(isRow?1:0),grid.width-(isRow?0:1),anchors);
 let widths;if(!isRow&&table.columnWidths){widths=getColumnWidths(table);widths.splice(index,1);widths=normalizeWidths(widths);}
 const align=!isRow&&Array.isArray(table.align)?table.align.filter((_,c)=>c!==index):null;
 return {rows,widths,align,removed,nonempty:removed.filter(a=>a.value.text.length>0)};
}
function deleteAxis(table,axis,index,options={}){
 const plan=deletionPlan(table,axis,index);
 if(plan.nonempty.length&&options.allowContentLoss!==true)throw Error('将删除含内容的单元格，需要明确确认');
 table.rows=plan.rows;if(plan.widths)table.columnWidths=plan.widths;
 if(plan.align)table.align=plan.align;
 return {removed:plan.removed};
}
const insertRow=(table,index)=>insertAxis(table,'row',index),insertColumn=(table,index)=>insertAxis(table,'column',index);
const deleteRow=(table,index,options)=>deleteAxis(table,'row',index,options),deleteColumn=(table,index,options)=>deleteAxis(table,'column',index,options);
function resizeBoundary(table,index,delta){
 const widths=getColumnWidths(table);
 if(!Number.isInteger(index)||index<0||index>=widths.length-1||typeof delta!=='number'||!Number.isFinite(delta))throw Error('列宽调整参数无效');
 const pair=widths[index]+widths[index+1],minimum=Math.min(1,pair/4);
 const left=Math.max(minimum,Math.min(pair-minimum,widths[index]+delta));
 widths[index]=left;widths[index+1]=pair-left;validateWidths(widths,widths.length);table.columnWidths=widths;return widths;
}
function clipboardMatrix(html,text){
 // HTML provides real cell boundaries, including one-column and merged ranges.
 const rich=parseHTML(html);if(rich)return rich;
 text=String(text||'');
 const math=root.ReportTableContent?.tokenize(text).filter(part=>part.kind==='math')||[];
 let quoted=false,fieldStart=true,delimiter=false;
 for(let i=0;i<text.length;i++){
  const ch=text[i];
  if(quoted){if(ch==='"'){if(text[i+1]==='"')i++;else quoted=false;}continue;}
  const formula=math.find(part=>part.from===i);if(formula){i=formula.to-1;fieldStart=false;continue;}
  if(ch==='"'&&fieldStart){quoted=true;continue;}
  if(ch==='\t'){delimiter=true;fieldStart=true;}
  else if(ch==='\n'||ch==='\r')fieldStart=true;
  else fieldStart=false;
 }
 // A newline alone does not prove that the author copied an Excel rectangle.
 return delimiter?parseTSV(text):null;
}
function applyPaste(table,r,c,matrix){
 const [n,m]=matrixDimensions(matrix),rows=table.rows;
 logicalGrid(table);logicalGrid({rows:matrix});
 if(!Number.isInteger(r)||!Number.isInteger(c)||r<0||c<0||r>=rows.length||c>=rows[0].length)throw Error('粘贴起点无效');
 validateWidths(table.columnWidths,rows[0].length);
 const oldRows=rows.length,oldCols=rows[0].length;
 const newRows=Math.max(oldRows,r+n),newCols=Math.max(oldCols,c+m);
 if(newRows>100||newCols>30)throw Error('粘贴范围超出表格的 100 行/30 列限制');
 // A paste may not partially replace any existing merged cell.
 for(let rr=0;rr<oldRows;rr++)for(let cc=0;cc<oldCols;cc++){
  const cell=rows[rr][cc];
  if(!cell|| (cell.rowspan===1&&cell.colspan===1))continue;
  const intersects=rr<r+n&&rr+cell.rowspan>r&&cc<c+m&&cc+cell.colspan>c;
  if(intersects)throw Error('目标区域与合并单元格冲突，请先拆分再粘贴');
 }
 for(let rr=r;rr<r+n;rr++)for(let cc=c;cc<c+m;cc++){
  if(rr<oldRows&&cc<oldCols&&rows[rr][cc]===null)throw Error('目标区域包含合并占位，请先拆分');
 }
 const next=cloneReport(rows);
 next.forEach(row=>{while(row.length<newCols)row.push(cell());});
 while(next.length<newRows)next.push(Array.from({length:newCols},()=>cell()));
 for(let i=0;i<n;i++)for(let j=0;j<m;j++)next[r+i][c+j]=cloneReport(matrix[i][j]);
 // Validate pasted merge anchors against themselves; covered blanks are null.
 let widths;
 if(table.columnWidths&&newCols>oldCols){const scale=oldCols/newCols;widths=getColumnWidths(table).map(w=>w*scale);while(widths.length<newCols)widths.push(100/newCols);widths=normalizeWidths(widths);}
 table.rows=next;if(widths)table.columnWidths=widths;
 if(Array.isArray(table.align)&&newCols>oldCols)while(table.align.length<newCols)table.align.push(null);
 return [n,m];
}
function mergeRect(table,r0,c0,r1,c1){
 const rows=table.rows;const minr=Math.min(r0,r1),maxr=Math.max(r0,r1);
 const minc=Math.min(c0,c1),maxc=Math.max(c0,c1);
 if(minr===maxr&&minc===maxc)throw Error('至少选择两个单元格才能合并');
 if(minr<0||minc<0||maxr>=rows.length||maxc>=rows[0].length)throw Error('合并范围无效');
 const grid=logicalGrid(table),selected=new Set();
 for(let r=minr;r<=maxr;r++)for(let c=minc;c<=maxc;c++)selected.add(grid.owners[r][c]);
 for(const anchor of selected){
  if(anchor.r<minr||anchor.c<minc||anchor.r+anchor.value.rowspan>maxr+1||anchor.c+anchor.value.colspan>maxc+1)throw Error('选区仅覆盖部分合并单元格，请扩大选区或先拆分');
  if((anchor.r!==minr||anchor.c!==minc)&&anchor.value.text.length)throw Error('合并不会丢失数据；请先清空其他选中单元格');
 }
 rows[minr][minc].rowspan=maxr-minr+1;rows[minr][minc].colspan=maxc-minc+1;
 for(let r=minr;r<=maxr;r++)for(let c=minc;c<=maxc;c++)if(r!==minr||c!==minc)rows[r][c]=null;
}
function splitCell(table,r,c){
 const rows=table.rows;const v=rows[r]?.[c];
 if(!v||v.rowspan===1&&v.colspan===1)throw Error('请选中一个已合并的主单元格');
 for(let rr=r;rr<r+v.rowspan;rr++)for(let cc=c;cc<c+v.colspan;cc++){
  if(rr===r&&cc===c)continue;rows[rr][cc]=cell();
 }
 v.rowspan=1;v.colspan=1;
}
const api={cell,cleanPastedCellText,compactDisplayText,parseTSV,parseHTML,clipboardMatrix,matrixDimensions,logicalGrid,validateWidths,normalizeWidths,getColumnWidths,
 insertion:insertAxis,deletionPlan,insertRow,insertColumn,deleteRow,deleteColumn,resizeBoundary,applyPaste,mergeRect,splitCell};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.ReportTables=api;
})(typeof window!=='undefined'?window:globalThis);
