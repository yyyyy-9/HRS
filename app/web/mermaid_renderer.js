/* Mermaid-language adapter backed by the complete offline Pele renderer.
 * Source, identity and numbering stay in HRS; Flow only edits simple nodes.
 */
(function(root){
'use strict';
let serial=0;
const cache=new Map(),limit=48,maxSource=50000,maxEdges=500,fontFamily='Segoe UI, Microsoft Yahei, sans-serif';
const palette={
 bg:['paper','#ffffff'],fg:['diagram-ink','#334664'],muted:['diagram-muted','#91a0b9'],
 line:['diagram-muted','#91a0b9'],surface:['diagram-bg','#eef3ff'],
 'surface-alt':['diagram-soft','#f4efff'],border:['diagram-line','#91a8dd'],
 accent:['brand','#3759c6'],critical:['danger','#b34242'],error:['danger','#b34242']
};
// Keep the complete renderer's categorical series colors. Pale node surfaces
// cannot replace series fills whose labels use the contrasting background.
function theme(svg,live){
 const css=getComputedStyle(document.documentElement);
 for(const [name,[token,fallback]] of Object.entries(palette)){
  const value=css.getPropertyValue('--hrs-'+token).trim();
  svg.style.setProperty('--pele-'+name,live?'var(--hrs-'+token+','+fallback+')':(/^#[0-9a-f]{3,8}$/i.test(value)?value:fallback));
 }
 svg.style.setProperty('--pele-font',fontFamily);
}
function freezeTheme(container){
 if(container.matches?.('svg.pele'))theme(container,false);
 container.querySelectorAll('svg.pele').forEach(svg=>theme(svg,false));
}
function localResources(model){
 const bitmap=value=>/^data:image\/(?:png|jpeg|gif|webp);base64,[a-z0-9+/=\s]+$/i.test(value);
 const seen=new Set();
 function check(value,style=false){
  if(typeof value==='string'){
   if(style&&/@import\b/i.test(value))throw Error('Mermaid 样式不能加载外部文件');
   if(style)for(const item of value.matchAll(/\burl\s*\(([^)]*)\)/gi))if(!item[1].trim().replace(/^["']|["']$/g,'').startsWith('#'))throw Error('Mermaid 样式不能加载外部文件');
   return;
  }
  if(!value||typeof value!=='object'||seen.has(value))return;seen.add(value);
  if(value instanceof Map||value instanceof Set){for(const item of value.values())check(item,style);return;}
  for(const [key,item] of Object.entries(value)){
   if(/^(?:img|image)$/i.test(key)&&typeof item==='string'&&item&&!bitmap(item))throw Error('Mermaid 外部图片未进入HRS资源审计，请使用已有图片/组图对象或内嵌位图');
   check(item,style||/style/i.test(key));
  }
 }
 check(model);
}
function instance(svg,live){
 const doc=new DOMParser().parseFromString(svg,'image/svg+xml'),node=doc.documentElement;
 if(node.localName!=='svg'||doc.querySelector('parsererror'))throw Error('Mermaid 未生成有效 SVG');
 const prefix='hrs-mmd-'+(++serial)+'-',ids=new Map(),used=new Set();
 for(const e of [node,...node.querySelectorAll('[id]')])if(e.id){
  const old=e.id;let next=prefix+old,index=1;while(used.has(next))next=prefix+old+'--'+(++index);
  if(!ids.has(old))ids.set(old,next);e.id=next;used.add(next);
 }
 const escapeRE=s=>s.replace(/[.*+?^$()|[\]\\{}]/g,'\\$&');
 const references=text=>{
  for(const [id,next] of ids)text=text.replace(new RegExp('#'+escapeRE(id)+'(?=["\\\'\\s):;,.{]|$)','g'),'#'+next);
  return text;
 };
 node.querySelectorAll('script,iframe,object,embed,foreignObject').forEach(e=>e.remove());
 for(const e of [node,...node.querySelectorAll('*')]){
  if(e.localName==='style'){
   localResources({style:e.textContent});e.textContent=references(e.textContent);
  }
  for(const a of [...e.attributes]){
   if(a.name==='id')continue;
   if(/^on/i.test(a.name)){e.removeAttribute(a.name);continue;}
   if(/^(?:href|xlink:href)$/i.test(a.name)){
    if(a.value.startsWith('#'))e.setAttribute(a.name,'#'+(ids.get(a.value.slice(1))||a.value.slice(1)));
    else if(e.localName==='image'&&!/^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(a.value))throw Error('Mermaid 外部图片未进入HRS资源审计');
    else if(!/^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(a.value))e.removeAttribute(a.name);
   }else if(/^aria-(?:labelledby|describedby)$/.test(a.name))e.setAttribute(a.name,a.value.split(/\s+/).map(id=>ids.get(id)||id).join(' '));
   else {if(a.name==='style')localResources({style:a.value});e.setAttribute(a.name,references(a.value));}
  }
 }
 theme(node,live);
 return new XMLSerializer().serializeToString(node);
}
async function equation(tex,size){
 if(!root.MathJax?.tex2svgPromise)throw Error('流程图公式所需的本地 MathJax 未加载');
 await root.MathJax.startup.promise;
 const result=await root.MathJax.tex2svgPromise(tex,{display:true}),svg=result.querySelector('svg');
 if(!svg||svg.querySelector('[data-mjx-error],[data-mml-node="merror"]'))throw Error('流程图公式无法排版，请检查 TeX 源码');
 const width=parseFloat(svg.getAttribute('width'))*size/2,height=parseFloat(svg.getAttribute('height'))*size/2;
 if(!(width>0&&height>0&&Number.isFinite(width+height)))throw Error('流程图公式尺寸无效');
 svg.setAttribute('width',String(width));svg.setAttribute('height',String(height));svg.removeAttribute('style');
 // Report CSS sizes outer charts with svg { width:100%; height:auto }. Pin
 // the nested equation to its measured box in both preview and export.
 svg.style.width=width+'px';svg.style.height=height+'px';svg.style.maxHeight='none';
 return {svg:svg.outerHTML,width,height};
}
async function geometry(source){
 if(!root.pele?.render||!root.pele?.parse)throw Error('本地 Pele 运行库未加载');
 const model=root.pele.parse(source,{limit:maxSource,maxEdges});localResources(model);
 const equations=new Map(),key=(tex,size)=>JSON.stringify([tex,size]);
 const options={fontFamily,fontSize:16,autoDirection:false,idPrefix:'hrs-pele-'+(++serial),
  limit:maxSource,maxEdges,outputLimit:4000000,links:false,imageSchemes:['data'],
  math:(tex,size)=>{
   const id=key(tex,size);if(!equations.has(id))equations.set(id,{tex,size,value:null});
   return equations.get(id).value;
  }};
 let result=root.pele.render(model,options);
 // The parsed renderer identifies math labels; do not regex source/comments.
 if(equations.size){
  for(const item of equations.values())item.value=await equation(item.tex,item.size);
  result=root.pele.render(model,options);
 }
 return result.svg;
}
async function render(source,{liveTheme=false}={}){
 if(typeof source!=='string'||!source.trim()||source.length>maxSource)throw Error('Mermaid 源码须非空，且不超过 '+maxSource+' 字符');
 let pending=cache.get(source);
 if(!pending){
  pending=geometry(source);cache.set(source,pending);
  pending.catch(()=>{if(cache.get(source)===pending)cache.delete(source);});
  if(cache.size>limit)cache.delete(cache.keys().next().value);
 }
 return instance(await pending,liveTheme);
}
async function into(host,source){
 const ticket=(host._mermaidTicket||0)+1;host._mermaidTicket=ticket;
 host.setAttribute('aria-busy','true');
 try{
  const svg=await render(source,{liveTheme:true});
  if(host._mermaidTicket!==ticket)return;
  host.innerHTML=svg;host.dataset.mermaidState='ready';
 }catch(error){
  if(host._mermaidTicket!==ticket)return;
  host.replaceChildren();const message=document.createElement('div');message.className='diagram-error';
  message.textContent='Mermaid：'+error.message;host.append(message);host.dataset.mermaidState='error';throw error;
 }finally{if(host._mermaidTicket===ticket)host.removeAttribute('aria-busy');}
}
function clearCache(){cache.clear();}
async function renderAll(container,isCurrent=()=>true){
 const errors=[];
 for(const host of container.querySelectorAll('[data-hrs-mermaid]')){
  if(!isCurrent())break;
  try{await into(host,host._mermaidSource);}catch(error){errors.push('Mermaid：'+error.message);}
 }
 return errors;
}
root.ReportMermaid={render,into,renderAll,clearCache,freezeTheme};
})(window);
