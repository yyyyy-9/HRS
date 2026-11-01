/* Navigation, disclosure and explicit section grips have separate actions. */
(function(root){
'use strict';
function attach(container,{locate,move,editable=()=>true,onError}){
 const controls=document.createElement('label');controls.className='toc-level-control';controls.textContent='目录层级 ';
 const levels=document.createElement('select');levels.setAttribute('aria-label','目录显示层级');
 for(const [value,label] of [['all','全部'],...Array.from({length:6},(_,i)=>[String(i+1),'显示至 H'+(i+1)])]){
  const option=document.createElement('option');option.value=value;option.textContent=label;levels.append(option);
 }
 controls.append(levels);container.before(controls);container.classList.add('toc-tree');
 let records=[],sections=[],source='',documentKey='',signature='',drag=null,collapsed=new Set(),rows=new Map();
 const clearDrop=()=>container.querySelectorAll('.toc-drop-before,.toc-drop-after').forEach(node=>node.classList.remove('toc-drop-before','toc-drop-after'));
 function disclose(item,open){
  if(open)collapsed.delete(item.section.key);else collapsed.add(item.section.key);
  item.children.hidden=!open;item.toggle.setAttribute('aria-expanded',String(open));item.toggle.textContent=open?'▾':'▸';
 }
 function show(){
  for(const row of rows.values())if(row.hasChildren)disclose(row,!collapsed.has(row.section.key));
 }
 levels.onchange=()=>{
  collapsed.clear();const depth=levels.value==='all'?6:+levels.value;
  for(const row of rows.values())if(row.section.level>=depth)collapsed.add(row.section.key);show();
 };
 function render(headings,context){
  if(documentKey!==context.documentKey){collapsed.clear();levels.value='all';documentKey=context.documentKey;signature='';}
  records=headings;sections=context.sections;source=context.source;
  const byStart=new Map(sections.map(item=>[item.start,item]));
  const entries=records.map(heading=>({heading,section:byStart.get(heading.start)})).filter(item=>item.section);
  const nextSignature=JSON.stringify(entries.map(item=>[item.section.key,item.section.level]));
  if(signature===nextSignature&&container.firstElementChild){
   const previous=[...rows.values()];rows=new Map();
   entries.forEach((entry,i)=>{const item=previous[i];item.heading=entry.heading;item.section=entry.section;update(item);rows.set(item.section.start,item);});
   return;
  }
  signature=nextSignature;rows=new Map();
  const list=document.createElement('ul');list.className='toc-children';const stack=[];
  for(const {heading,section} of entries){
   while(stack.length&&stack[stack.length-1].section.level>=section.level)stack.pop();
   const node=document.createElement('li');node.className='toc-node';node.dataset.headingStart=String(heading.start);
   const row=document.createElement('div');row.className='toc-row';
   const toggle=document.createElement('button');toggle.type='button';toggle.className='toc-toggle';toggle.setAttribute('aria-label','展开或收起：'+section.title);
   const anchor=document.createElement('a');
   const grip=document.createElement('button');grip.type='button';grip.className='toc-grip';grip.textContent='≡';grip.setAttribute('aria-label','拖动整节：'+section.title);grip.title='按住拖动整节；Alt+↑/↓ 同级移动';
   const children=document.createElement('ul');children.className='toc-children';
   const item={heading,section,node,row,toggle,anchor,grip,children,hasChildren:false};rows.set(section.start,item);update(item);
   anchor.onclick=event=>{event.preventDefault();locate(item.heading).catch(onError);};
   toggle.onclick=()=>{if(item.hasChildren)disclose(item,children.hidden);};
   const cancelDrag=()=>{drag=null;node.classList.remove('toc-dragging');clearDrop();};
   grip.onpointerdown=event=>{
    if(event.button!==0||!editable())return;event.preventDefault();grip.focus();grip.setPointerCapture(event.pointerId);
    drag={source,start:item.section.start,x:event.clientX,y:event.clientY,pointer:event.pointerId,active:false,target:null};
   };
   grip.onpointermove=event=>{
    if(!drag||drag.pointer!==event.pointerId)return;
    if(!drag.active&&Math.hypot(event.clientX-drag.x,event.clientY-drag.y)<5)return;
    drag.active=true;node.classList.add('toc-dragging');clearDrop();drag.target=null;
    const over=document.elementFromPoint(event.clientX,event.clientY)?.closest('.toc-row');
    if(!over||!container.contains(over))return;
    const start=+over.parentElement.dataset.headingStart;if(start===drag.start)return;
    drag.target=start;drag.side=event.clientY<over.getBoundingClientRect().top+over.offsetHeight/2?'before':'after';over.classList.add('toc-drop-'+drag.side);
    const bounds=container.getBoundingClientRect();if(event.clientY<bounds.top+28)container.scrollTop-=18;else if(event.clientY>bounds.bottom-28)container.scrollTop+=18;
   };
   grip.onpointerup=event=>{
    if(!drag||drag.pointer!==event.pointerId)return;
    const intent=drag.active&&drag.target!==null?{source:drag.source,from:drag.start,target:drag.target,side:drag.side}:null;
    cancelDrag();grip.releasePointerCapture(event.pointerId);if(intent&&editable())Promise.resolve(move(intent)).catch(onError);
   };
   grip.onpointercancel=grip.onlostpointercapture=cancelDrag;
   grip.onkeydown=event=>{
    if(event.key==='Escape'){cancelDrag();return;}
    if(!editable()||!event.altKey||!['ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();
    const peers=records.filter(h=>h.level===item.heading.level),at=peers.indexOf(item.heading),next=peers[at+(event.key==='ArrowUp'?-1:1)];
    if(next)Promise.resolve(move({source,from:item.section.start,target:next.start,side:event.key==='ArrowUp'?'before':'after'})).catch(onError);
   };
   row.append(toggle,anchor,grip);node.append(row,children);
   if(stack.length){const parent=stack[stack.length-1];parent.hasChildren=true;parent.children.append(node);}else list.append(node);
   stack.push(item);
  }
  for(const item of rows.values())if(!item.hasChildren){item.toggle.hidden=true;item.children.hidden=true;}
  container.replaceChildren(list);show();
 }
 function update(item){
  const {heading,section}=item;item.node.dataset.headingStart=String(section.start);
  item.anchor.href='#'+heading.id;item.anchor.className='level-'+heading.level;
  const label=heading.text.replace(/\$[^$]*\$/g,'∑');if(item.anchor.textContent!==label)item.anchor.textContent=label;
  item.anchor.title=section.title;item.toggle.setAttribute('aria-label','展开或收起：'+section.title);item.grip.setAttribute('aria-label','拖动整节：'+section.title);
  item.grip.hidden=!editable();
 }
 function reveal(start){
  const item=rows.get(start);if(!item)return;
  let parent=item.node.parentElement?.closest('.toc-node');while(parent){const row=rows.get(+parent.dataset.headingStart);if(row)disclose(row,true);parent=parent.parentElement?.closest('.toc-node');}
 }
 return {render,reveal};
}
root.ReportOutline={attach};
})(window);
