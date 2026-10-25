/* MERMAID-DRAG-01: placement of existing SVG shapes, never a second renderer.
 * The legacy Flow model defines the editable subset; all labels/shapes still
 * come from the complete renderer. The same layout is used before every export.
 */
(function(root){
'use strict';
const scenes=new WeakMap(),shapeTags=new Set(['rect','polygon','ellipse','circle','path']);
const round=n=>Math.round(n*1000)/1000;
function mounted(svg,work){
 // An SVG parsed in an XML document isConnected too, but has no viewport.
 if(svg.isConnected&&svg.ownerDocument===document)return work();
 const host=document.createElement('div');host.style.cssText='position:fixed;left:-100000px;top:0;width:10000px;visibility:hidden;pointer-events:none';
 document.body.append(host);host.append(svg);
 try{return work();}finally{svg.remove();host.remove();}
}
function bounds(svg,element){
 const box=element.getBBox(),matrix=svg.getCTM().inverse().multiply(element.getCTM());
 const corners=[[box.x,box.y],[box.x+box.width,box.y],[box.x,box.y+box.height],[box.x+box.width,box.y+box.height]].map(([x,y])=>{
  const point=svg.createSVGPoint();point.x=x;point.y=y;return point.matrixTransform(matrix);
 });
 const x=Math.min(...corners.map(p=>p.x)),y=Math.min(...corners.map(p=>p.y));
 return {x,y,width:Math.max(...corners.map(p=>p.x))-x,height:Math.max(...corners.map(p=>p.y))-y};
}
function untransformedParent(svg,element){
 const m=svg.getCTM().inverse().multiply(element.parentElement.getCTM());
 if(Math.abs(m.a-1)+Math.abs(m.d-1)+Math.abs(m.b)+Math.abs(m.c)+Math.abs(m.e)+Math.abs(m.f)>0.001)throw Error('此图的分组坐标暂不支持可靠拖动，请保留源码');
}
function scene(svg,graph){
 if(scenes.has(svg))return scenes.get(svg);
 return mounted(svg,()=>{
  const nodes=new Map();
  for(const element of svg.querySelectorAll('.pele-node[data-id]')){
   if(!graph.nodes.some(n=>n.id===element.dataset.id))continue;
   untransformedParent(svg,element);
   const shape=[...element.children].find(e=>shapeTags.has(e.localName));if(!shape)throw Error('流程图节点无法定位');
   const box=bounds(svg,shape);if(!(box.width>0&&box.height>0))throw Error('流程图节点尺寸无效');
   nodes.set(element.dataset.id,{element,...box,shape:graph.nodes.find(n=>n.id===element.dataset.id).shape,baseX:box.x,baseY:box.y,transform:element.getAttribute('transform')||''});
  }
  if(nodes.size!==graph.nodes.length)throw Error('流程图节点不能完整定位，未修改排版');
  const labels=new Map([...svg.querySelectorAll('.pele-edge-label[data-id]')].map(e=>[e.dataset.id,e]));
  const edges=[];
  for(const element of svg.querySelectorAll('.pele-edge[data-hrs-from]')){
   untransformedParent(svg,element);
   const from=nodes.get(element.dataset.hrsFrom),to=nodes.get(element.dataset.hrsTo);
   const path=element.querySelector('path:not(.pele-marker)'),marker=element.querySelector('path.pele-marker');
   const points=(marker?.getAttribute('d')||'').match(/-?\d*\.?\d+(?:e[-+]?\d+)?/gi)?.map(Number);
   if(!from||!to||!path||points?.length!==6)throw Error('流程图连线不能完整定位，未修改排版');
   const length=Math.hypot(points[0]-(points[2]+points[4])/2,points[1]-(points[3]+points[5])/2);
   const half=Math.hypot(points[2]-points[4],points[3]-points[5])/2;
   const label=labels.get(element.dataset.id);if(label)untransformedParent(svg,label);
   const labelBox=label?bounds(svg,label):null;
   edges.push({from,to,path,marker,length,half,label,labelBox,transform:label?.getAttribute('transform')||''});
  }
  if(edges.length!==graph.edges.length)throw Error('流程图连线数不一致，未修改排版');
  const result={svg,nodes,edges,vertical:['TB','TD','BT'].includes(graph.direction)};scenes.set(svg,result);return result;
 });
}
function route(edge,vertical){
 const a=edge.from,b=edge.to,ac={x:a.x+a.width/2,y:a.y+a.height/2},bc={x:b.x+b.width/2,y:b.y+b.height/2};
 let start,tip,c1,c2,unit;
 if(a===b){
  // At .3/.7 height a diamond's boundary is inside its bounding rectangle.
  const right=a.x+a.width*(a.shape==='decision'?.8:1);
  start={x:right,y:a.y+a.height*.3};tip={x:right,y:a.y+a.height*.7};unit={x:-1,y:0};
  const distance=Math.max(36,a.height*.7);c1={x:start.x+distance,y:start.y-distance*.3};c2={x:tip.x+distance,y:tip.y+distance*.3};
 }else if(!vertical&&Math.abs(bc.x-ac.x)>=(a.width+b.width)*.25){
  const sign=bc.x>=ac.x?1:-1;unit={x:sign,y:0};start={x:ac.x+sign*a.width/2,y:ac.y};tip={x:bc.x-sign*b.width/2,y:bc.y};
  const distance=Math.max(28,Math.abs(tip.x-start.x)/2);c1={x:start.x+sign*distance,y:start.y};c2={x:tip.x-sign*distance,y:tip.y};
 }else{
  const sign=bc.y>=ac.y?1:-1;unit={x:0,y:sign};start={x:ac.x,y:ac.y+sign*a.height/2};tip={x:bc.x,y:bc.y-sign*b.height/2};
  const distance=Math.max(28,Math.abs(tip.y-start.y)/2);c1={x:start.x,y:start.y+sign*distance};c2={x:tip.x,y:tip.y-sign*distance};
 }
 const end={x:tip.x-unit.x*edge.length*.87,y:tip.y-unit.y*edge.length*.87};
 const p=point=>round(point.x)+','+round(point.y);
 edge.path.setAttribute('d','M'+p(start)+'C'+p(c1)+' '+p(c2)+' '+p(end));
 const tail={x:tip.x-unit.x*edge.length,y:tip.y-unit.y*edge.length};
 edge.marker.setAttribute('d','M'+p(tip)+'L'+p({x:tail.x-unit.y*edge.half,y:tail.y+unit.x*edge.half})+'L'+p({x:tail.x+unit.y*edge.half,y:tail.y-unit.x*edge.half})+'Z');
 if(edge.label){
  const center={x:(start.x+3*c1.x+3*c2.x+end.x)/8,y:(start.y+3*c1.y+3*c2.y+end.y)/8-12};
  edge.label.setAttribute('transform','translate('+round(center.x-edge.labelBox.x-edge.labelBox.width/2)+' '+round(center.y-edge.labelBox.y-edge.labelBox.height/2)+') '+edge.transform);
 }
}
function draw(context,positions,fit=true){
 const {svg,nodes,edges,vertical}=context;
 for(const [id,node] of nodes){
  const position=positions[id];if(!position)continue;
  node.x=position.x;node.y=position.y;
  node.element.setAttribute('transform','translate('+round(node.x-node.baseX)+' '+round(node.y-node.baseY)+') '+node.transform);
 }
 edges.forEach(edge=>route(edge,vertical));
 if(fit)mounted(svg,()=>{
  const b=svg.getBBox(),pad=16;if(!Number.isFinite(b.x+b.y+b.width+b.height))throw Error('流程图边界无效');
  svg.setAttribute('viewBox',[b.x-pad,b.y-pad,b.width+pad*2,b.height+pad*2].map(round).join(' '));
  svg.setAttribute('width',String(round(b.width+pad*2)));svg.setAttribute('height',String(round(b.height+pad*2)));
 });
}
function positions(context){return Object.fromEntries([...context.nodes].map(([id,n])=>[id,{x:round(n.x),y:round(n.y)}]));}
function apply(svg,graph){if(Object.keys(graph.positions).length)draw(scene(svg,graph),graph.positions);}
function bindDrag(canvas,{getGraph,onSelect,onCommit,onError}){
 let cancel=null;
 function down(event){
  const target=event.target.closest?.('[data-node]'),svg=target?.ownerSVGElement,graph=getGraph();
  if(cancel||event.button!==0||!target||!svg||!graph)return;
  try{
   const context=scene(svg,graph),node=context.nodes.get(target.dataset.node);if(!node)return;
   onSelect(target.dataset.node);event.preventDefault();
   const matrix=svg.getScreenCTM().inverse(),point=e=>new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix);
   const start=point(event),original=positions(context),view=[svg.getAttribute('viewBox'),svg.getAttribute('width'),svg.getAttribute('height')];let moved=false;
   const initial={x:node.x,y:node.y};
   const move=e=>{
    const q=point(e),x=Math.max(0,Math.min(100000,initial.x+q.x-start.x)),y=Math.max(0,Math.min(100000,initial.y+q.y-start.y));
    if(!moved&&Math.hypot(x-initial.x,y-initial.y)<1)return;moved=true;
    const next=positions(context);next[target.dataset.node]={x,y};draw(context,next,false);
   };
   const cleanup=()=>{target.removeEventListener('pointermove',move);target.removeEventListener('pointerup',up);target.removeEventListener('pointercancel',abort);try{target.releasePointerCapture(event.pointerId);}catch{}cancel=null;target.style.cursor='grab';};
   const restore=()=>{draw(context,original,false);['viewBox','width','height'].forEach((key,i)=>svg.setAttribute(key,view[i]));};
   const up=()=>{cleanup();if(!moved)return;try{const next=positions(context);draw(context,next);onCommit(next);}catch(e){restore();onError(e);}};
   const abort=()=>{cleanup();if(moved)restore();};
   cancel=abort;target.setPointerCapture(event.pointerId);target.style.cursor='grabbing';
   target.addEventListener('pointermove',move);target.addEventListener('pointerup',up);target.addEventListener('pointercancel',abort);
  }catch(error){onError(error);}
 }
 canvas.addEventListener('pointerdown',down);
 return ()=>{cancel?.();canvas.removeEventListener('pointerdown',down);};
}
root.ReportDiagramLayout={apply,bindDrag};
})(window);
