/* Official local Mermaid renderer. Markdown/source identities stay in HRS.
 * The small Flow model is only used by the optional simple-node editor.
 */
(function(root){
'use strict';
let queue=Promise.resolve(),serial=0;
const cache=new Map(),limit=48;
const escapeRE=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
function localResources(diagram){
 const vertices=diagram.db.getVertices?.();
 if(vertices?.values)for(const node of vertices.values()){
  if(node.img&&!/^data:image\/(?:png|jpeg|gif|webp);base64,[a-z0-9+/=\s]+$/i.test(node.img))throw Error('Mermaid 外部图片未进入HRS资源审计，请使用已有图片/组图对象或内嵌位图');
 }
 const seen=new Set();
 function check(value,style=false){
  if(typeof value==='string'){
   if(style&&/@import\b/i.test(value))throw Error('Mermaid 样式不能加载外部文件');
   if(style)for(const item of value.matchAll(/\burl\s*\(([^)]*)\)/gi))if(!item[1].trim().replace(/^["']|["']$/g,'').startsWith('#'))throw Error('Mermaid 样式不能加载外部文件');
   return;
  }
  if(!value||typeof value!=='object'||seen.has(value))return;seen.add(value);
  if(value instanceof Map)for(const item of value.values())check(item,style);
  else for(const [key,item] of Object.entries(value))check(item,style||/style/i.test(key));
 }
 check(vertices);check(diagram.db.getClasses?.());check(diagram.db.getEdges?.());
}
function configuration(){
 const css=getComputedStyle(document.documentElement),color=(name,fallback)=>{
  const value=css.getPropertyValue(name).trim();return /^#[0-9a-f]{3,8}$/i.test(value)?value:fallback;
 };
 return {startOnLoad:false,securityLevel:'strict',suppressErrorRendering:true,
  htmlLabels:false,fontFamily:'Segoe UI, Microsoft Yahei, sans-serif',
  maxTextSize:50000,maxEdges:500,theme:'base',themeCSS:'',
  themeVariables:{primaryColor:color('--hrs-diagram-bg','#eef3ff'),primaryTextColor:color('--hrs-diagram-ink','#334664'),
   primaryBorderColor:color('--hrs-diagram-line','#91a8dd'),lineColor:color('--hrs-diagram-muted','#91a0b9'),
   secondaryColor:color('--hrs-diagram-alt','#e6f5ed'),tertiaryColor:color('--hrs-diagram-soft','#f4efff'),
   fontFamily:'Segoe UI, Microsoft Yahei, sans-serif'},
  flowchart:{htmlLabels:false},
  secure:['secure','securityLevel','startOnLoad','maxTextSize','maxEdges','suppressErrorRendering','themeCSS','themeVariables','fontFamily','htmlLabels','flowchart']};
}
function instance(svg){
 const doc=new DOMParser().parseFromString(svg,'image/svg+xml'),node=doc.documentElement;
 if(node.localName!=='svg'||doc.querySelector('parsererror'))throw Error('Mermaid 未生成有效 SVG');
 const prefix='hrs-mmd-'+(++serial)+'-',ids=[node,...node.querySelectorAll('[id]')].filter(e=>e.id).map(e=>e.id).sort((a,b)=>b.length-a.length);
 let result=svg;
 // Cached/duplicated diagrams need distinct CSS, marker and node identities.
 for(const id of ids)result=result.replace(new RegExp('([#"\\\'])'+escapeRE(id)+'(?=["\\\'\\s):;,.{])','g'),(_,before)=>before+prefix+id);
 const safe=new DOMParser().parseFromString(result,'image/svg+xml').documentElement;
 const used=new Set();
 for(const e of [safe,...safe.querySelectorAll('[id]')])if(e.id){
  const id=e.id;let next=id,index=1;while(used.has(next))next=id+'--'+(++index);
  if(next!==id)e.id=next;used.add(next);
 }
 safe.querySelectorAll('script,iframe,object,embed').forEach(e=>e.remove());
 for(const e of [safe,...safe.querySelectorAll('*')])for(const a of [...e.attributes]){
  if(/^on/i.test(a.name))e.removeAttribute(a.name);
  if(/^(?:href|xlink:href)$/i.test(a.name)&&!a.value.startsWith('#')&&!/^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(a.value))e.removeAttribute(a.name);
 }
 return new XMLSerializer().serializeToString(safe);
}
async function render(source){
 if(typeof source!=='string'||!source.trim()||source.length>50000)throw Error('Mermaid 源码须非空，且不超过 50000 字符');
 const config=configuration(),key=JSON.stringify(config)+'\n'+source;
 let pending=cache.get(key);
 if(!pending){
  pending=queue.then(async()=>{
   if(!root.mermaid?.render)throw Error('本地 Mermaid 运行库未加载');
   root.mermaid.initialize(config);
   // Inspect official parsed facts, rather than guessing image semantics from
   // punctuation. Unmanaged remote assets must not bypass HRS's offline rules.
   localResources(await root.mermaid.mermaidAPI.getDiagramFromText(source));
   const {svg}=await root.mermaid.render('hrs-mermaid-render-'+(++serial),source);
   return svg;
  });
  // Serialize work without retaining the last completed SVG through the queue.
  queue=pending.then(()=>undefined,()=>undefined);cache.set(key,pending);
  pending.catch(()=>{if(cache.get(key)===pending)cache.delete(key);});
  if(cache.size>limit)cache.delete(cache.keys().next().value);
 }
 return instance(await pending);
}
async function into(host,source){
 const ticket=(host._mermaidTicket||0)+1;host._mermaidTicket=ticket;
 host.setAttribute('aria-busy','true');
 try{
  const svg=await render(source);
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
root.ReportMermaid={render,into,renderAll,clearCache};
})(window);
