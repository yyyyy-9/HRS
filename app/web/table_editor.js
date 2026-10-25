/* A transactional table dialog. Cancel leaves the Markdown source untouched. */
(function(root){
'use strict';
const cloneReport=root.ReportClone.clone;
async function open(model,{modal,toast}){
 const T=root.ReportTables;
 let working=cloneReport(model),grid,scroll,caption,widthTrack,undoButton,redoButton,horizontalSelect,verticalSelect;
 let selected=null,anchor=null,range=null,index=0,lastKind=null,lastAt=0;
 const entries=[capture()];
 let owner;
 const keys=event=>{if((event.ctrlKey||event.metaKey)&&!event.isComposing&&['z','y'].includes(event.key.toLowerCase())){event.preventDefault();event.stopPropagation();if(event.key.toLowerCase()==='y'||event.shiftKey)redo();else undo();}};
 function capture(){return {model:cloneReport(working),selected:cloneReport(selected),anchor:cloneReport(anchor),range:cloneReport(range)};}
 function record(kind){
  const now=Date.now(),entry=capture();entries.splice(index+1);
  if(kind.startsWith('typing:')&&kind===lastKind&&now-lastAt<550&&index>0)entries[index]=entry;
  else{entries.push(entry);index++;if(entries.length>50){entries.shift();index--;}}
  lastKind=kind;lastAt=now;historyButtons();
 }
 function historyButtons(){if(undoButton){undoButton.disabled=index===0;redoButton.disabled=index===entries.length-1;}}
 function focusInfo(){const element=document.activeElement;return element?.dataset.r!==undefined?{r:+element.dataset.r,c:+element.dataset.c,start:element.selectionStart,end:element.selectionEnd}:element===caption?{caption:true,start:caption.selectionStart,end:caption.selectionEnd}:null;}
 function restore(next){
  const focus=focusInfo(),entry=entries[next];index=next;lastKind=null;
  working=cloneReport(entry.model);selected=cloneReport(entry.selected);anchor=cloneReport(entry.anchor);range=cloneReport(entry.range);
  rebuild();historyButtons();
  const field=focus?.caption?caption:focus?grid.querySelector(`textarea[data-r="${focus.r}"][data-c="${focus.c}"]`):null;
  if(field){field.focus({preventScroll:true});field.setSelectionRange(Math.min(focus.start,field.value.length),Math.min(focus.end,field.value.length));}
 }
 function undo(){if(index>0)restore(index-1);}
 function redo(){if(index<entries.length-1)restore(index+1);}
 function normalizeSelection(){
  if(!selected)return;
  const g=T.logicalGrid(working),r=Math.max(0,Math.min(g.height-1,selected[0])),c=Math.max(0,Math.min(g.width-1,selected[1]));
  const owner=g.owners[r][c];selected=[owner.r,owner.c];anchor=selected;range=null;
 }
 function transact(mutator,kind='command',nextSelection=null){
  try{
   const copy=cloneReport(working);if(mutator(copy)===false)return;
   T.logicalGrid(copy);T.validateWidths(copy.columnWidths,copy.rows[0].length);
   working=copy;if(nextSelection)selected=nextSelection;normalizeSelection();record(kind);rebuild();
  }catch(error){toast(error.message);}
 }
 function selection(){if(!selected)throw Error('请先点击一个单元格选择行或列');return selected;}
 async function remove(axis){
  const at=selection()[axis==='row'?0:1],plan=T.deletionPlan(working,axis,at);
  if(plan.nonempty.length){
   const message=`删除第 ${at+1} ${axis==='row'?'行':'列'}会移除 ${plan.nonempty.length} 个含内容的单元格。确认删除？`;
   const accepted=root.ReportDialogs?await root.ReportDialogs.confirm(message,{title:'删除'+(axis==='row'?'行':'列'),okText:'删除',danger:true}):window.confirm(message);
   if(!accepted)return;
  }
  transact(copy=>(axis==='row'?T.deleteRow:T.deleteColumn)(copy,at,{allowContentLoss:true}),'delete');
 }
 function rectangle(){
  if(!range)throw Error('请单击起点，再按 Shift 点击终点');
  const g=T.logicalGrid(working),a=g.owners[range[0][0]][range[0][1]],b=g.owners[range[1][0]][range[1][1]];
  return [Math.min(a.r,b.r),Math.min(a.c,b.c),Math.max(a.r+a.value.rowspan,b.r+b.value.rowspan)-1,Math.max(a.c+a.value.colspan,b.c+b.value.colspan)-1];
 }
 function highlight(){
  let bounds=null;if(range)try{bounds=rectangle();}catch{}
  grid.querySelectorAll('textarea').forEach(field=>{
   const r=+field.dataset.r,c=+field.dataset.c;
   field.classList.toggle('selected',!!(bounds?r>=bounds[0]&&r<=bounds[2]&&c>=bounds[1]&&c<=bounds[3]:selected&&r===selected[0]&&c===selected[1]));
  });
 }
 function widthStyles(){
  const widths=T.getColumnWidths(working);grid.style.gridTemplateColumns=widths.map(w=>`minmax(0,${w}fr)`).join(' ');
  const columns=widthTrack.querySelectorAll('.table-width-column');let position=0;
  columns.forEach((column,c)=>{column.style.width=widths[c]+'%';column.textContent=`${c+1} 列 ${widths[c].toFixed(1)}%`;position+=widths[c];
   const handle=widthTrack.querySelector(`[data-boundary="${c}"]`);if(handle){handle.style.left=position+'%';handle.setAttribute('aria-valuenow',String(widths[c]));}
  });
 }
 function buildWidths(){
  widthTrack.replaceChildren();const cols=working.rows[0].length;
  for(let c=0;c<cols;c++){const column=document.createElement('div');column.className='table-width-column';widthTrack.append(column);}
  for(let c=0;c<cols-1;c++){
   const handle=document.createElement('button');handle.type='button';handle.className='table-column-resizer';handle.dataset.boundary=c;
   handle.setAttribute('aria-label',`调整第 ${c+1} 与第 ${c+2} 列宽`);handle.title='拖动调整列宽，也可用左右方向键微调';widthTrack.append(handle);
   handle.onkeydown=event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();transact(copy=>T.resizeBoundary(copy,c,event.key==='ArrowLeft'?-1:1),'width');}};
   handle.onpointerdown=event=>{
    if(event.button!==0)return;event.preventDefault();
    const before=cloneReport(working),width=widthTrack.getBoundingClientRect().width,x=event.clientX;
    handle.setPointerCapture(event.pointerId);
    const move=e=>{const copy=cloneReport(before);T.resizeBoundary(copy,c,100*(e.clientX-x)/width);working=copy;widthStyles();};
    const finish=e=>{
     handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',finish);handle.removeEventListener('pointercancel',finish);
     if(e.type==='pointercancel')working=before;
     else if(JSON.stringify(working.columnWidths)!==JSON.stringify(before.columnWidths))record('width');
     rebuild();
    };
    handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',finish);
   };
  }
  widthStyles();
 }
 function rebuild(){
  const top=scroll.scrollTop,left=scroll.scrollLeft;grid.replaceChildren();caption.value=working.caption;
  if(horizontalSelect){const values=working.align||[];
   horizontalSelect.disabled=!selected;horizontalSelect.value=values[selected?.[1]??0]||'default';
   verticalSelect.value=working.verticalAlign||'default';
  }
  grid.style.minWidth=Math.max(520,working.rows[0].length*56)+'px';
  working.rows.forEach((row,r)=>row.forEach((value,c)=>{if(value===null)return;
   const field=document.createElement('textarea');if(r===0)field.classList.add('table-edit-header');field.value=value.text;field.rows=Math.max(1,Math.min(8,value.text.split(/\r?\n/).length));field.maxLength=30000;
   field.dataset.r=r;field.dataset.c=c;field.setAttribute('aria-label',`第 ${r+1} 行第 ${c+1} 列`);
   field.style.gridRow=`${r+1} / span ${value.rowspan}`;field.style.gridColumn=`${c+1} / span ${value.colspan}`;
   field.onclick=event=>{selected=[r,c];if(event.shiftKey&&anchor)range=[anchor,[r,c]];else{anchor=[r,c];range=null;}highlight();horizontalSelect.disabled=false;horizontalSelect.value=working.align?.[c]||'default';};
   field.oninput=()=>{working.rows[r][c].text=field.value;field.rows=Math.max(1,Math.min(8,field.value.split(/\r?\n/).length));record(`typing:${r}:${c}`);};
   field.onpaste=event=>{
    const plain=event.clipboardData?.getData('text/plain')||'',html=event.clipboardData?.getData('text/html')||'';
    if(!plain&&!html)return;event.preventDefault();
    try{
     const matrix=T.clipboardMatrix(html,plain);
     if(matrix){transact(copy=>T.applyPaste(copy,r,c,matrix),'paste',[r,c]);return;}
     const clean=field.selectionStart===0&&field.selectionEnd===field.value.length?T.cleanPastedCellText(plain):plain;
     const text=field.value.slice(0,field.selectionStart)+clean+field.value.slice(field.selectionEnd);
     if(text.length>30000)throw Error('单格内容超过 30000 字符');
     field.setRangeText(clean,field.selectionStart,field.selectionEnd,'end');working.rows[r][c].text=field.value;
     field.rows=Math.max(1,Math.min(8,field.value.split(/\r?\n/).length));record('paste');
    }catch(error){toast('粘贴未执行：'+error.message);}
   };
   grid.append(field);
  }));buildWidths();highlight();historyButtons();scroll.scrollTop=top;scroll.scrollLeft=left;
 }
 try{return await modal({title:'编辑表格',kicker:'表格 · 内容与合并关系保留',wide:true,
  note:'窗口内可逐步撤销；应用后整张表作为一笔文稿修改，取消不修改源稿',
  body:outer=>{
   caption=document.createElement('input');caption.type='text';caption.className='table-caption-input';caption.placeholder='表题（可选，不手工填写编号）';caption.maxLength=300;caption.value=working.caption;
   caption.oninput=()=>{working.caption=caption.value;record('typing:caption');};outer.append(caption);
   const tools=document.createElement('div');tools.className='table-editor-tools';outer.append(tools);
   function button(label,action){const b=document.createElement('button');b.type='button';b.className='btn btn-quiet';b.textContent=label;b.onclick=async()=>{try{await action();}catch(error){toast(error.message);}};tools.append(b);return b;}
   undoButton=button('撤销表格',undo);redoButton=button('重做表格',redo);
   button('所有列水平居中',()=>transact(copy=>{copy.align=Array(copy.rows[0].length).fill('center');},'align-all'));
   const alignment=document.createElement('div');alignment.className='table-editor-alignment';outer.append(alignment);
   const makeSelector=(title,options)=>{
    const label=document.createElement('label');label.textContent=title+' ';const select=document.createElement('select');
    for(const [value,text] of options){const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}
    label.append(select);alignment.append(label);return select;
   };
   horizontalSelect=makeSelector('选中列水平',[
    ['mixed','保留各列设置'],['default','默认左对齐'],['left','左对齐'],['center','水平居中'],['right','右对齐']]);
   verticalSelect=makeSelector('单元格垂直',[
    ['default','保留默认'],['top','顶部对齐'],['middle','垂直居中'],['bottom','底部对齐']]);
   horizontalSelect.onchange=()=>{
    const choice=horizontalSelect.value;if(choice==='mixed')return;
    const [r,c]=selection();
    transact(copy=>{const width=copy.rows[0].length;const arr=(copy.align||Array(width).fill(null)).slice(0,width);
     while(arr.length<width)arr.push(null);arr[c]=choice==='default'?null:choice;
     if(arr.every(x=>!x))delete copy.align;else copy.align=arr;},'align');
   };
   verticalSelect.onchange=()=>{
    const choice=verticalSelect.value;
    transact(copy=>{if(choice==='default')delete copy.verticalAlign;
     else copy.verticalAlign=choice;},'align');
   };
   button('增加一行',()=>transact(copy=>T.insertRow(copy,copy.rows.length),'insert'));
   button('增加一列',()=>transact(copy=>T.insertColumn(copy,copy.rows[0].length),'insert'));
   button('在上方插入行',()=>{const [r,c]=selection();transact(copy=>T.insertRow(copy,r),'insert',[r,c]);});
   button('在下方插入行',()=>{const [r,c]=selection(),at=r+working.rows[r][c].rowspan;transact(copy=>T.insertRow(copy,at),'insert',[at,c]);});
   button('在左侧插入列',()=>{const [r,c]=selection();transact(copy=>T.insertColumn(copy,c),'insert',[r,c]);});
   button('在右侧插入列',()=>{const [r,c]=selection(),at=c+working.rows[r][c].colspan;transact(copy=>T.insertColumn(copy,at),'insert',[r,at]);});
   button('删除选中行',()=>remove('row'));button('删除选中列',()=>remove('column'));
   button('合并第一行',()=>transact(copy=>T.mergeRect(copy,0,0,0,copy.rows[0].length-1),'merge'));
   button('拆分第一行',()=>transact(copy=>T.splitCell(copy,0,0),'split'));
   button('合并选中区域',()=>{const rect=rectangle();transact(copy=>T.mergeRect(copy,...rect),'merge',[rect[0],rect[1]]);});
   button('拆分选中单元格',()=>{const [r,c]=selection();transact(copy=>T.splitCell(copy,r,c),'split');});
   const layout=[['撤销表格','重做表格','所有列水平居中','在上方插入行','在下方插入行','在左侧插入列','在右侧插入列'],['删除选中行','删除选中列','合并选中区域','拆分选中单元格']];
   const byLabel=new Map([...tools.querySelectorAll('button')].map(b=>[b.textContent.trim(),b]));
   tools.textContent='';
   for(const labels of layout){const row=document.createElement('div');row.className='table-editor-row';for(const label of labels){const b=byLabel.get(label);if(b)row.append(b);}tools.append(row);}
   const remaining=[...byLabel.values()].filter(button=>!tools.contains(button));
   if(remaining.length){const more=document.createElement('details');more.className='table-editor-more';const summary=document.createElement('summary');summary.textContent='更多操作';const body=document.createElement('div');body.className='table-editor-more-body';body.append(...remaining);more.append(summary,body);tools.lastElementChild.append(more);}
   const help=document.createElement('p');help.className='modal-help';help.textContent='单格支持多行文字、$行内公式$ 和 $$块公式$$。Excel 表格优先按 HTML 粘贴；粘贴时清理单元格首尾多余空白行，内部换行保留。没有区域格式的多行文本仍在一格。单击起点、Shift 点击终点后可合并。';outer.append(help);
   const widthHelp=document.createElement('p');widthHelp.className='modal-help';widthHelp.textContent='列宽：拖动下方分隔线，或选中分隔线后用 ← / → 微调。行高随内容自动增长。';outer.append(widthHelp);
   widthTrack=document.createElement('div');widthTrack.className='table-width-track';outer.append(widthTrack);
   scroll=document.createElement('div');scroll.className='table-grid-scroll';outer.append(scroll);grid=document.createElement('div');grid.className='table-edit-grid';scroll.append(grid);
   owner=outer;owner.addEventListener('keydown',keys);
   rebuild();
  },onOk:()=>{T.logicalGrid(working);T.validateWidths(working.columnWidths,working.rows[0].length);return cloneReport(working);},okText:'应用表格修改'});
 }finally{owner?.removeEventListener('keydown',keys);}
}
root.ReportTableEditor={open};
})(window);
