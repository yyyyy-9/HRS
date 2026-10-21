/* HF8 PF7: in-page confirmation dialog shared by the editor and table editor.
   Replaces native window.confirm so every prompt uses the same look, stacks
   above an open editor modal and keeps keyboard focus inside the dialog. */
(function(root){
'use strict';
const FOCUSABLE='button:not([disabled]),[href],input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"]),summary';
function focusables(container){
 return [...container.querySelectorAll(FOCUSABLE)].filter(el=>!el.hidden&&!el.closest('[hidden]')&&el.getClientRects().length);
}
function trapFocus(container,event){
 if(event.key!=='Tab')return;
 const items=focusables(container);if(!items.length){event.preventDefault();return;}
 const first=items[0],last=items[items.length-1],active=document.activeElement;
 if(event.shiftKey&&(active===first||!container.contains(active))){event.preventDefault();last.focus();}
 else if(!event.shiftKey&&(active===last||!container.contains(active))){event.preventDefault();first.focus();}
}
let sequence=0;
function confirmDialog(message,{title='请确认',okText='确定',cancelText='取消',danger=false}={}){
 return new Promise(resolve=>{
  const previous=document.activeElement,id='confirm-'+(++sequence);
  const layer=document.createElement('div');layer.className='confirm-layer';
  const scrim=document.createElement('div');scrim.className='modal-scrim';
  const box=document.createElement('section');box.className='confirm-window'+(danger?' danger':'');
  box.setAttribute('role','alertdialog');box.setAttribute('aria-modal','true');
  box.setAttribute('aria-labelledby',id+'-title');box.setAttribute('aria-describedby',id+'-text');
  const heading=document.createElement('h2');heading.id=id+'-title';heading.textContent=title;
  const text=document.createElement('p');text.id=id+'-text';text.className='confirm-text';text.textContent=String(message);
  const foot=document.createElement('div');foot.className='confirm-foot';
  const cancel=document.createElement('button');cancel.type='button';cancel.className='btn btn-quiet';cancel.textContent=cancelText;
  const ok=document.createElement('button');ok.type='button';ok.className='btn '+(danger?'btn-danger':'btn-primary');ok.textContent=okText;
  foot.append(cancel,ok);box.append(heading,text,foot);layer.append(scrim,box);document.body.append(layer);
  const finish=value=>{
   layer.remove();
   if(previous&&previous.isConnected&&typeof previous.focus==='function')previous.focus();
   resolve(value);
  };
  ok.onclick=()=>finish(true);cancel.onclick=()=>finish(false);
  layer.addEventListener('keydown',event=>{
   // Keep Escape/Tab from reaching an editor modal underneath.
   if(event.key==='Escape'){event.preventDefault();event.stopPropagation();finish(false);return;}
   if(event.key==='Tab'){event.stopPropagation();trapFocus(box,event);}
  });
  (danger?cancel:ok).focus();
 });
}
const isOpen=()=>!!document.querySelector('.confirm-layer');
const api={confirm:confirmDialog,trapFocus,focusables,isOpen};
root.ReportDialogs=api;
if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
