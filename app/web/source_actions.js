/* Operate on the editor's current ranges, never on the card's visible label. */
(function(root){
'use strict';
function attach(editor,{copy,replace,onError}={}){
 const host=editor.view?.dom;if(!host)return null;
 let selected=null,busy=false;
 const menu=document.createElement('div');menu.className='source-object-menu';menu.hidden=true;menu.setAttribute('role','menu');menu.setAttribute('aria-label','源码对象操作');document.body.append(menu);
 let surface=null;
 const clear=()=>{selected=null;surface?.classList.remove('preview-object-selected');surface=null;host.querySelectorAll('.source-object-selected').forEach(el=>el.classList.remove('source-object-selected'));menu.hidden=true;};
 function selectRange(range,node=null){
  if(!range||range.from<0||range.to>editor.value.length||range.to<range.from)return null;
  clear();selected={...range,source:editor.value,raw:editor.value.slice(range.from,range.to)};
  editor.setSelectionRange(range.from,range.to);
  if(node){surface=node;node.classList.add('preview-object-selected');node.tabIndex=0;node.focus({preventScroll:true});root.getSelection?.().removeAllRanges();}
  return selected;
 }
 function select(card){
  let from;try{from=editor.view.posAtDOM(card);}catch{return null;}
  const range=SourceBlocks.scan(editor.value).find(r=>r.from===from);
  if(!range)return null;
  selectRange(range);editor.focus();card.classList.add('source-object-selected');return selected;
 }
 function current(){
  if(!selected||selected.source!==editor.value||editor.selectionStart!==selected.from||editor.selectionEnd!==selected.to)throw Error('对象或选区已经变化，请重新选择');
  return selected;
 }
 async function action(kind){
  if(busy)return;busy=true;
  try{
   const item=current();if(editor.readOnly&&kind!=='copy')return;
   if(kind!=='delete'&&!await copy(item.raw,item,kind))throw Error('未能写入剪贴板；可选中对象后使用 Ctrl+C');
   if(kind!=='copy'){current();replace(item.from,item.to,'',kind==='cut'?'object-cut':'object-delete');}
   clear();editor.focus();
  }catch(error){onError?.(error.message);}finally{busy=false;menu.hidden=true;}
 }
 for(const [kind,label] of [['copy','复制源码 · Ctrl+C'],['cut','剪切 · Ctrl+X'],['delete','删除 · Delete']]){
  const button=document.createElement('button');button.type='button';button.textContent=label;button.setAttribute('role','menuitem');button.dataset.action=kind;
  button.addEventListener('mousedown',e=>e.preventDefault());button.addEventListener('click',()=>action(kind));menu.append(button);
 }
 host.addEventListener('mousedown',event=>{
  const card=event.target.closest('.source-fold-summary');
  if(card&&!event.target.closest('button')){event.preventDefault();event.stopPropagation();select(card);}else clear();
 },true);
 function showMenu(event){
  event.preventDefault();event.stopPropagation();
  menu.hidden=false;menu.querySelectorAll('[data-action]').forEach(b=>{b.disabled=editor.readOnly&&b.dataset.action!=='copy';});
  menu.style.left=Math.max(4,Math.min(event.clientX,innerWidth-menu.offsetWidth-4))+'px';
  menu.style.top=Math.max(4,Math.min(event.clientY,innerHeight-menu.offsetHeight-4))+'px';
 }
 host.addEventListener('contextmenu',event=>{
  const card=event.target.closest('.source-fold-summary');if(!card)return;
  event.preventDefault();event.stopPropagation();if(!select(card))return;
  showMenu(event);
 },true);
 function keydown(event){
  if(!selected)return;
  if(event.key==='Escape'){clear();return;}
  const command=(event.ctrlKey||event.metaKey)&&!event.altKey?({c:'copy',x:'cut'}[event.key.toLowerCase()]):['Delete','Backspace'].includes(event.key)?'delete':null;
  if(command){try{current();}catch{clear();return;}event.preventDefault();event.stopPropagation();action(command);}
  else clear();
 }
 host.addEventListener('keydown',keydown,true);
 document.addEventListener('keydown',event=>{if(surface&&surface.contains(event.target))keydown(event);},true);
 document.addEventListener('mousedown',event=>{if(!menu.contains(event.target)&&!host.contains(event.target)&&!surface?.contains(event.target))clear();},true);
 editor.view.dom.addEventListener('input',clear);window.addEventListener('blur',clear);
 return {clear,selectRange,showMenu};
}
root.SourceActions={attach};
})(typeof window==='undefined'?globalThis:window);
