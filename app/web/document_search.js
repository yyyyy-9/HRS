/* Source search/replace and read-only rendered search over the same document. */
(function(root){
'use strict';
const frame=()=>new Promise(resolve=>requestAnimationFrame(resolve));
function occurrences(text,query,matchCase){
 if(!query)return [];
 const escaped=query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),pattern=new RegExp(escaped,matchCase?'gu':'giu'),found=[];
 for(const match of text.matchAll(pattern))found.push({start:match.index,end:match.index+match[0].length});
 return found;
}
function renderedMatches(article,query,matchCase){
 const groups=[],visibility=new WeakMap(),walker=document.createTreeWalker(article,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);
 let group=null,lineBreak=false,node;
 function searchable(element){
  if(visibility.has(element))return visibility.get(element);
  let okay=!element.closest('script,style,textarea,input,button,select,option,.hrs-table-source,.hrs-note-back,.hrs-block-times');
  if(element.closest('.hrs-table-tools')&&!element.closest('.hrs-table-kind,.hrs-table-heading-caption'))okay=false;
  if(okay)for(let e=element;e&&e!==article;e=e.parentElement){if(e.hidden||getComputedStyle(e).display==='none'){okay=false;break;}}
  visibility.set(element,okay);return okay;
 }
 while((node=walker.nextNode())){
  if(node.nodeType===Node.ELEMENT_NODE){if(node.tagName==='BR')lineBreak=true;continue;}
  if(!node.data||!searchable(node.parentElement))continue;
  const unit=node.parentElement.closest('p,h1,h2,h3,h4,h5,h6,td,th,li,pre,figcaption,caption,summary,dt,dd,div')||article;
  if(!group||group.unit!==unit){group={unit,text:'',nodes:[]};groups.push(group);}
  else if(lineBreak)group.text+='\n';
  lineBreak=false;group.nodes.push({node,start:group.text.length,end:group.text.length+node.data.length});group.text+=node.data;
 }
 const matches=[];
 for(const item of groups)for(const found of occurrences(item.text,query,matchCase)){
  const a=item.nodes.find(n=>n.start<=found.start&&found.start<n.end),b=item.nodes.find(n=>n.start<found.end&&found.end<=n.end);
  if(!a||!b)continue;
  const range=document.createRange();range.setStart(a.node,found.start-a.start);range.setEnd(b.node,found.end-b.start);matches.push({range});
 }
 return matches;
}
async function revealSource(editor,match,current){
 const snapshot=editor.value;
 editor.highlightRange(match.start,match.end,{select:false});await frame();await frame();
 if(editor.value!==snapshot||!current())return false;
 // Reuse existing fold records and the public Expand action, not a new editor.
 const block=root.SourceBlocks.scan(snapshot).find(b=>b.from<=match.start&&match.start<b.to);
 if(block)for(const card of editor.view.dom.querySelectorAll('.source-fold-summary')){
  let position;try{position=editor.view.posAtDOM(card);}catch{continue;}
  if(position===block.from){[...card.querySelectorAll('button')].find(b=>b.textContent==='展开')?.click();await frame();break;}
 }
 if(editor.value!==snapshot||!current())return false;
 editor.setSelectionRange(match.start,match.end);editor.highlightRange(match.start,match.end,{select:false});
 return true;
}
function attach({panel,editor,preview,getSource,getView,prepare,getRange=()=>({start:0,end:getSource().length}),replace,canReplace=()=>getView()!=='reading',revealSource:reveal=async()=>{},canOpen=()=>true,onError=()=>{}}){
 const query=panel.querySelector('#search-query'),scope=panel.querySelector('#search-scope'),count=panel.querySelector('#search-count');
 const matchCase=panel.querySelector('#search-case'),previous=panel.querySelector('#search-prev'),next=panel.querySelector('#search-next');
 const replacement=panel.querySelector('#replace-query'),replaceScope=panel.querySelector('#replace-scope'),one=panel.querySelector('#replace-current'),all=panel.querySelector('#replace-all'),replaceStatus=panel.querySelector('#replace-status');
 const layer=document.createElement('div');layer.className='hrs-search-layer';layer.setAttribute('aria-hidden','true');document.body.append(layer);
 let matches=[],index=-1,lastSide='source',sequence=0,paintFrame=0;
 const scroller=preview.closest('.page-scroll');
 function clearPaint(){layer.replaceChildren();if(root.CSS?.highlights){CSS.highlights.delete('hrs-search-all');}}
 function paint(){
  clearPaint();if(panel.hidden||scope.value!=='preview')return;
  if(typeof root.Highlight==='function'&&root.CSS?.highlights){
   try{const all=new Highlight();matches.forEach(m=>m.range?.startContainer.isConnected&&all.add(m.range));CSS.highlights.set('hrs-search-all',all);}
   catch{/* Older browsers still get the current-match rectangle below. */}
  }
  const range=matches[index]?.range;if(!range?.startContainer.isConnected)return;
  const bounds=scroller.getBoundingClientRect();
  for(const rect of range.getClientRects()){
   const left=Math.max(rect.left,bounds.left),right=Math.min(rect.right,bounds.right),top=Math.max(rect.top,bounds.top),bottom=Math.min(rect.bottom,bounds.bottom);
   if(right<=left||bottom<=top)continue;
   const hit=document.createElement('div');hit.className='hrs-search-hit';
   Object.assign(hit.style,{left:left+'px',top:top+'px',width:(right-left)+'px',height:(bottom-top)+'px'});layer.append(hit);
  }
 }
 function schedulePaint(){if(!paintFrame)paintFrame=requestAnimationFrame(()=>{paintFrame=0;paint();});}
 function update(){
  if(panel.hidden)return;
  document.body.dataset.hrsSearchScope=scope.value;
  panel.querySelector('.search-help').textContent=scope.value==='source'?(replaceScope.value==='topic'?'当前专题，含折叠源码':'全文查找，含折叠源码'):'按渲染正文全文查找，显示全部专题';
  const range=getRange(replaceScope.value);
  matches=scope.value==='source'?occurrences(getSource(),query.value,matchCase.checked).filter(m=>m.start>=range.start&&m.end<=range.end):renderedMatches(preview,query.value,matchCase.checked);
  index=matches.length?Math.max(0,Math.min(index,matches.length-1)):-1;
  count.textContent=(index+1)+' / '+matches.length;previous.disabled=next.disabled=!matches.length;schedulePaint();
  const editable=scope.value==='source'&&canReplace();replacement.disabled=replaceScope.disabled=!editable;
  one.disabled=all.disabled=!editable||!matches.length;
  replaceStatus.textContent=editable?'仅替换源码 · 可撤销':getView()==='reading'?'阅读视图只查找':'渲染查找不替换；请选择 Markdown 源码';
 }
 async function navigate(step=0,reset=false){
  const run=++sequence;if(!query.value){update();return;}
  try{
   await prepare(scope.value);if(run!==sequence||panel.hidden)return;
   update();if(!matches.length)return;
   index=reset?0:(index+step+matches.length)%matches.length;count.textContent=(index+1)+' / '+matches.length;
   const match=matches[index];
   if(scope.value==='source'){await reveal(match);if(!await revealSource(editor,match,()=>run===sequence&&!panel.hidden))return;}
   else{
    for(let ancestor=match.range.startContainer.parentElement;ancestor&&preview.contains(ancestor);ancestor=ancestor.parentElement)if(ancestor.tagName==='DETAILS')ancestor.open=true;
    const rect=match.range.getBoundingClientRect(),bounds=scroller.getBoundingClientRect();
    scroller.scrollTop+=rect.top-bounds.top-scroller.clientHeight/2+rect.height/2;
   }
   if(run!==sequence||panel.hidden)return;
   paint();query.focus({preventScroll:true});
  }catch(error){onError(error.message);}
 }
 function chooseSide(){return getView()==='reading'?'preview':getView()==='source'||editor.hasFocus()?'source':scroller.contains(document.activeElement)?'preview':lastSide;}
 function open({reuse=false,step=0,replace:focusReplace=false}={}){
  if(!canOpen())return;
  if(panel.hidden){
   const side=chooseSide();if(scope.value!==side)index=-1;scope.value=side;
   if(!reuse){
    const selection=scope.value==='source'?getSource().slice(editor.selectionStart,editor.selectionEnd):
     (preview.contains(window.getSelection()?.anchorNode)?window.getSelection().toString():'');
    if(selection&&selection.length<=200&&!/[\r\n]/.test(selection))query.value=selection;
   }
   panel.hidden=false;document.body.dataset.hrsSearchOpen='1';if(!reuse)index=-1;
  }
  if(focusReplace&&getView()!=='reading')scope.value='source';
  update();query.focus({preventScroll:true});query.select();if(query.value)navigate(step).then(()=>{if(focusReplace&&!replacement.disabled)replacement.focus();});
  else if(focusReplace&&!replacement.disabled)replacement.focus();
 }
 function close(){
  sequence++;panel.hidden=true;delete document.body.dataset.hrsSearchOpen;delete document.body.dataset.hrsSearchScope;clearPaint();editor.clearHighlight();
  if(scope.value==='source')editor.focus();else scroller.focus({preventScroll:true});
 }
 query.addEventListener('input',()=>{index=-1;update();navigate(0,true);});
 query.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing){event.preventDefault();navigate(event.shiftKey?-1:1);}});
 scope.addEventListener('change',()=>{index=-1;update();navigate(0,true);});
 matchCase.addEventListener('change',()=>{index=-1;update();navigate(0,true);});
 async function apply(allMatches){
  if(scope.value!=='source'||!canReplace()||!replace)return;
  const source=getSource();update();const selected=allMatches?matches.slice():matches[index]?[matches[index]]:[];
  if(!selected.length)return;
  const start=selected[0].start;
  try{
   ++sequence;await replace({source,matches:selected,text:replacement.value,all:allMatches,range:getRange(replaceScope.value),scope:replaceScope.value});
   if(panel.hidden)return;update();index=matches.findIndex(m=>m.start>=start+replacement.value.length);if(index<0&&matches.length)index=0;
   count.textContent=(index+1)+' / '+matches.length;replaceStatus.textContent='已替换 '+selected.length+' 处 · Ctrl+Z 撤销';
   replacement.focus({preventScroll:true});
  }catch(error){onError(error.message);}
 }
 one.onclick=()=>apply(false);all.onclick=()=>apply(true);
 replacement.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing){event.preventDefault();apply(false);}});
 replaceScope.onchange=()=>{index=-1;update();navigate(0,true);};
 previous.onclick=()=>navigate(-1);next.onclick=()=>navigate(1);panel.querySelector('#search-close').onclick=close;
 document.addEventListener('pointerdown',event=>{if(editor.view.dom.contains(event.target))lastSide='source';else if(preview.contains(event.target))lastSide='preview';},true);
 document.addEventListener('keydown',event=>{
  if(event.isComposing||!canOpen())return;
  if((event.ctrlKey||event.metaKey)&&!event.altKey&&event.key.toLowerCase()==='f'){event.preventDefault();event.stopPropagation();open();}
  else if((event.ctrlKey||event.metaKey)&&!event.altKey&&event.key.toLowerCase()==='h'){event.preventDefault();event.stopPropagation();open({replace:true});}
  else if(event.key==='F3'){event.preventDefault();event.stopPropagation();if(panel.hidden)open({reuse:true,step:event.shiftKey?-1:1});else navigate(event.shiftKey?-1:1);}
  else if(event.key==='Escape'&&!panel.hidden){event.preventDefault();event.stopPropagation();close();}
 },true);
 scroller.addEventListener('scroll',schedulePaint,{passive:true});window.addEventListener('resize',schedulePaint);
 return {open,close,refresh:update,invalidate:clearPaint};
}
root.ReportDocumentSearch={attach};
})(window);
