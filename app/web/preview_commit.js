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
/* Only move identical display leaves at commit, after async work is accepted.
 * New wrappers keep current source ranges, captions, references and listeners. */
function reuseResources(preview,staged){
 const pools=new Map(),counts={images:0,formulas:0};
 const key=node=>node.tagName==='IMG'?'image\u0000'+node.getAttribute('src'):'math\u0000'+node.parentElement.dataset.display+'\u0000'+node.parentElement.dataset.tex;
 const eligible=node=>node.tagName!=='IMG'||/^(?:\/assets\/|data:)/.test(node.getAttribute('src')||'');
 for(const node of preview.querySelectorAll('img,.markdown-math > svg')){if(!eligible(node))continue;
  const id=key(node),items=pools.get(id)||[];items.push(node);pools.set(id,items);
 }
 for(const node of staged.querySelectorAll('img,.markdown-math > svg')){
  if(!eligible(node))continue;const items=pools.get(key(node));if(!items?.length)continue;
  const index=items.findIndex(previous=>previous.isEqualNode(node));if(index<0)continue;
  const previous=items.splice(index,1)[0];node.replaceWith(previous);counts[node.tagName==='IMG'?'images':'formulas']++;
 }
 return counts;
}
function commit(preview,staged,{resources=false}={}){
 const counts=resources?reuseResources(preview,staged):{images:0,formulas:0};let prose=0;
 const nodes=Array.from(staged.childNodes,n=>{
  const old=n._reuseExisting;
  if(!old||n.innerHTML!==old.innerHTML)return n;
  prose++;
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
 return {...counts,prose};
}
root.ReportPreviewCommit={reusable,commit};
if(typeof module!=='undefined'&&module.exports)module.exports=root.ReportPreviewCommit;
})(typeof window==='undefined'?globalThis:window);
