/* Reconcile unchanged prose without moving live object/editor DOM prematurely. */
(function(root){
'use strict';
function reusable(preview,model,previous,compatible){
 const result=new Map();
 if(!compatible||!previous||previous.blocks.length!==model.map.blocks.length)return result;
 if(previous.blocks.some((r,i)=>r.type!==model.map.blocks[i].type||r.objectId!==model.map.blocks[i].objectId))return result;
 for(const node of preview.children){
  const record=model.map.blocks[Number(node.dataset.mapIndex)];
  if(!record||!['paragraph','blockquote'].includes(record.type)||record.raw!==node._sourceRaw)continue;
  if(/[\[$\\@<]/.test(record.raw)||node.querySelector('a,img,svg,math,input,pre,[contenteditable="true"],.report-table-wrap'))continue;
  result.set(record.index,node);
 }
 return result;
}
function commit(preview,staged){
 const nodes=Array.from(staged.childNodes,n=>{
  const old=n._reuseExisting;
  if(!old||n.innerHTML!==old.innerHTML)return n;
  for(const key of Object.keys(old.dataset))if(!(key in n.dataset))delete old.dataset[key];
  Object.assign(old.dataset,n.dataset);
  old._sourceRaw=n._sourceRaw;old._sourceDocument=n._sourceDocument;
  return old;
 });
 const wanted=new Set(nodes);let cursor=preview.firstChild;
 for(const node of nodes){
  if(node===cursor)cursor=cursor.nextSibling;
  else if(cursor&&!wanted.has(cursor)){const next=cursor.nextSibling;preview.replaceChild(node,cursor);cursor=next;}
  else preview.insertBefore(node,cursor);
 }
 while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
}
root.ReportPreviewCommit={reusable,commit};
if(typeof module!=='undefined'&&module.exports)module.exports=root.ReportPreviewCommit;
})(typeof window==='undefined'?globalThis:window);
