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
/* Save the fresh, pre-SVG display structure. Source offsets live in math IDs;
 * they are rebound at commit, never by moving the currently displayed nodes
 * into an asynchronous staging tree. Interactive objects keep the leaf path. */
function prepareMath(preview,staged,compatible){
 const previous=new Map(Array.from(preview.children,node=>[node.dataset.mapIndex,node]));
 for(const block of staged.children){
  if(!['paragraph','blockquote','list','reportEquation'].includes(block.dataset.type)||
     !block.querySelector('.markdown-math')||block.querySelector('a,input,pre,img,table,math,.object-xref-invalid,[data-hrs-footnote-ref]'))continue;
  const copy=block.cloneNode(true);
  copy.querySelectorAll('.markdown-math').forEach(span=>span.removeAttribute('data-math-id'));
  block._mathSignature=copy.innerHTML;
  const old=previous.get(block.dataset.mapIndex);
  if(compatible&&old?.isConnected&&old.dataset.type===block.dataset.type&&old._sourceRaw===block._sourceRaw&&
     old._mathSignature===block._mathSignature&&!old.querySelector('.math-error,[contenteditable="true"]'))block._reuseMath=old;
 }
 if(!compatible)return;
 // Live output is already part of the document's working set, even when a
 // large SVG does not fit the bounded template cache. Reserve it without
 // detaching it until the accepted synchronous commit.
 const retained=new Set(Array.from(staged.children,node=>node._reuseMath).filter(Boolean)),pool=new Map();
 const key=span=>span.dataset.display+'\u0000'+span.dataset.tex;
 for(const svg of preview.querySelectorAll('.markdown-math > svg')){
  if(retained.has(svg.closest('.doc-block')))continue;
  const id=key(svg.parentElement),items=pool.get(id)||[];items.push(svg);pool.set(id,items);
 }
 for(const span of staged.querySelectorAll('.markdown-math')){
  if(span.closest('.doc-block')?._reuseMath)continue;
  const items=pool.get(key(span));if(items?.length)span._reuseSVG=items.shift();
 }
}
function updateSource(old,node){
 for(const key of Object.keys(old.dataset))if(!(key in node.dataset))delete old.dataset[key];
 for(const [key,value] of Object.entries(node.dataset))if(old.dataset[key]!==value)old.dataset[key]=value;
 old._sourceRaw=node._sourceRaw;old._sourceDocument=node._sourceDocument;
}
/* Only move identical display leaves at commit, after async work is accepted.
 * New wrappers keep current source ranges, captions, references and listeners. */
function reuseResources(preview,staged,retained){
 const pools=new Map(),counts={images:0,formulas:0};
 for(const span of staged.querySelectorAll('.markdown-math'))if(span._reuseSVG){span.replaceChildren(span._reuseSVG);counts.formulas++;}
 const key=node=>node.tagName==='IMG'?'image\u0000'+node.getAttribute('src'):'math\u0000'+node.parentElement.dataset.display+'\u0000'+node.parentElement.dataset.tex;
 const eligible=node=>node.tagName!=='IMG'||/^(?:\/assets\/|data:)/.test(node.getAttribute('src')||'');
 for(const node of preview.querySelectorAll('img,.markdown-math > svg')){if(!eligible(node)||retained.has(node.closest('.doc-block')))continue;
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
 const retained=new Set();let math=0;
 const nodes=Array.from(staged.childNodes,n=>{
  const old=n._reuseMath;if(!old||!old.isConnected||old._sourceRaw!==n._sourceRaw)return n;
  const before=old.querySelectorAll('.markdown-math'),after=n.querySelectorAll('.markdown-math');
  if(before.length!==after.length)return n;
  before.forEach((span,i)=>{if(span.dataset.mathId!==after[i].dataset.mathId)span.dataset.mathId=after[i].dataset.mathId;});
  updateSource(old,n);retained.add(old);math+=before.length;return old;
 });
 const counts=resources?reuseResources(preview,staged,retained):{images:0,formulas:0};let prose=0;
 const wantedNodes=nodes.map(n=>{
  const old=n._reuseExisting;
  if(!old||n.innerHTML!==old.innerHTML)return n;
  prose++;
  updateSource(old,n);
  return old;
 });
 const wanted=new Set(wantedNodes);let cursor=preview.firstChild;
 for(const node of wantedNodes){
  // Discard obsolete gaps/wrappers before advancing through retained nodes.
  // replaceChild(node,cursor) may move cursor.nextSibling itself: caching
  // that sibling as the next cursor would later delete the retained node.
  while(cursor&&!wanted.has(cursor)){const next=cursor.nextSibling;cursor.remove();cursor=next;}
  if(node===cursor)cursor=cursor.nextSibling;
  else preview.insertBefore(node,cursor);
 }
 while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
 return {...counts,formulas:counts.formulas+math,prose,mathBlocks:retained.size};
}
root.ReportPreviewCommit={reusable,prepareMath,commit};
if(typeof module!=='undefined'&&module.exports)module.exports=root.ReportPreviewCommit;
})(typeof window==='undefined'?globalThis:window);
