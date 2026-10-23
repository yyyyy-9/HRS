/* Clipboard HTML is an import adapter, never a second document model.
 * Parse inertly, discard formatting and submit existing HRS objects/assets
 * through the original clipboard transaction. No URL is fetched here. */
(function(root){
'use strict';
const MAX_HTML=2000000,MAX_IMAGES=100;
const dropped=new Set(['script','style','link','meta','head']);
const blocks=new Set(['p','div','section','article','blockquote','li','ul','ol','h1','h2','h3','h4','h5','h6','pre']);
function matches(html){return /<(?:table|img|math)\b|urn:schemas-microsoft-com:office|\bMso(?:Normal|Table)|\bmso-/i.test(html);}
function inspect(html,force=false){
 if(typeof html!=='string'||html.length>MAX_HTML)throw Error('粘贴的富文本超过 2 MB');
 if(!force&&!matches(html))return null;
 const template=document.createElement('template');template.innerHTML=html;
 const content=template.content;let count=0;
 function check(node,depth){
  if(++count>50000||depth>64)throw Error('粘贴内容超过节点或嵌套深度限制');
  if(node.nodeType===1&&dropped.has(node.localName))return;
  for(const child of node.childNodes)check(child,depth+1);
 }
 check(content,0);
 if(content.querySelectorAll('img').length>MAX_IMAGES)throw Error('一次最多粘贴 100 张图片');
 return content;
}
// Literal text must not accidentally create Markdown headings, lists, math,
// references or links. Escapes affect representation only, not visible text.
function literal(text){
 return String(text).replace(/\\/g,'\\\\').replace(/[`*_{}\[\]<>#!|~$=@]/g,'\\$&')
  .replace(/^(\s*)([-+])(?=\s)/gm,'$1\\$2').replace(/^(\s*\d{1,9})([.)])(?=\s)/gm,'$1\\$2');
}
async function resource(data,mime){
 const ext=({'image/png':'.png','image/jpeg':'.jpg','image/gif':'.gif','image/webp':'.webp','image/svg+xml':'.svg'})[mime];
 if(!ext)throw Error('剪贴板图片格式不支持：'+mime);
 if(data.length>17000000)throw Error('剪贴板单张图片超过限制');
 let bytes;try{bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));}catch{throw Error('剪贴板图片编码无效');}
 const digest=await crypto.subtle.digest('SHA-256',bytes),sha=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
 const name=sha.slice(0,16)+ext;
 return {path:'assets/'+name,assets:{[name]:{base64:data,sha256:sha}}};
}
async function prepare(html,plain,{native,figure,figureSnippet,table,tableSnippet,convertMath,nativeReply=null}){
 let content=inspect(html,!!nativeReply);if(!content)return null;
 const elements=[...content.querySelectorAll('img')];
 if(elements.some(img=>/^https?:/i.test(img.getAttribute('src')||'')))throw Error('不自动下载剪贴板中的外部图片，整段未插入');
 if(!nativeReply&&elements.some(img=>!/^data:image\//i.test(img.getAttribute('src')||''))){
  // Browser paste HTML may strip Office's file URLs. The native endpoint
  // verifies the live clipboard text, reads its own HTML and returns only
  // images declared there. It never accepts a caller-supplied local path.
  nativeReply=await native(plain);content=inspect(nativeReply.html,true);
  if(!content)throw Error('Windows 剪贴板没有可转换的富文本内容');
 }
 const mathImages=nativeReply?.math_images||{},mathNodes=new Map();
 const ml=[...content.querySelectorAll('math')];
 if(ml.length){if(!convertMath)throw Error('公式转换器尚未配置');const values=await convertMath(ml.map(node=>({format:'mathml',source:new XMLSerializer().serializeToString(node)})));if(values.length!==ml.length)throw Error('公式转换数量不一致');ml.forEach((node,i)=>mathNodes.set(node,{tex:values[i],display:node.getAttribute('display')==='block'}));}
 const images=new Map(),assets={};
 for(const img of content.querySelectorAll('img')){
  const src=img.getAttribute('src')||'';if(mathImages[src]||images.has(src))continue;
  let item=nativeReply?.images?.[src];
  if(!item){
   const match=src.match(/^data:(image\/(?:png|jpeg|gif|webp|svg\+xml));base64,([\s\S]+)$/i);
   if(!match)throw Error('无法取得剪贴板图片，整段未插入；请重新复制，或将图片分别插入');
   item=await resource(match[2].replace(/\s/g,''),match[1].toLowerCase());
  }
  for(const [name,asset] of Object.entries(item.assets))if(assets[name]&&assets[name].sha256!==asset.sha256)throw Error('剪贴板图片附件名称冲突，整段未插入');
  images.set(src,item);Object.assign(assets,item.assets);
 }
 const chunks=[],inlineMath=new Map(),prefix='HRSPASTEMATH'+crypto.randomUUID().replaceAll('-','')+'X';let buffer='';
 function inline(item){const key=prefix+inlineMath.size+'X';inlineMath.set(key,'$'+item.tex+'$');return key;}
 function textSource(text){let result=literal(text);for(const [key,value] of inlineMath)result=result.replaceAll(key,value);return result;}
 function formula(node){return mathNodes.get(node)||(node.localName==='img'?mathImages[node.getAttribute('src')||'']:null);}
 function blockMath(item){chunks.push(root.ReportEquations.snippet(item.tex,'eq-'+crypto.randomUUID().replaceAll('-','').slice(0,12)));}
 function flush(){const text=buffer.replace(/^[ \t\n]+|[ \t\n]+$/g,'');if(text)chunks.push(textSource(text));buffer='';}
 function visit(node){
  if(node.nodeType===3){buffer+=(node.nodeValue||'').replace(/[\r\n\t ]+/g,' ');return;}
  if(node.nodeType!==1)return;
  const tag=node.localName;if(dropped.has(tag))return;
  const math=formula(node);if(math){if(math.display){flush();blockMath(math);}else buffer+=inline(math);return;}
  if(['p','div','table'].includes(tag)){
   const found=[...node.querySelectorAll('img,math')].map(formula).filter(Boolean);
   if(found.length===1&&found[0].display&&(node.textContent||'').trim()===(found[0].source_number||'').trim()){flush();blockMath(found[0]);return;}
  }
  if(['iframe','object','embed','form'].includes(tag))throw Error('剪贴板包含尚不支持的嵌入对象，整段未插入；请拆开复制所需内容');
  if(tag==='br'){buffer+='\n';return;}
  if(tag==='img'){
   flush();const item=images.get(node.getAttribute('src')||'');if(!item)throw Error('剪贴板图片不完整');
   const obj=figure(item.path);obj.alt=node.getAttribute('alt')||'';
   if(obj.alt.length>300)throw Error('剪贴板图片替代文字超过 300 字符，整段未插入；请缩短后重新复制');
   for(const key of ['sourceAsset','vectorSource','rasterFallback','rendition'])if(item[key])obj[key]=item[key];
   chunks.push(figureSnippet(obj));return;
  }
  if(tag==='table'){
   flush();
   if(node.querySelector('table,object,svg')||[...node.querySelectorAll('img')].some(n=>!formula(n)))throw Error('包含嵌套表格或表内图片的区域需拆开分别粘贴；整段尚未插入');
   // Build a clean, text-only table before using the existing merged-grid
   // parser. No original style, URL, event handler or Office namespace survives.
   const clean=document.createElement('table');
   for(const row of node.rows){const tr=clean.insertRow();
    for(const cell of row.cells){const td=tr.insertCell();td.rowSpan=cell.rowSpan;td.colSpan=cell.colSpan;
     let text='';function cellText(n){
      if(n.nodeType===3){text+=(n.nodeValue||'').replace(/[\r\n\t ]+/g,' ');return;}
      if(n.nodeType!==1||dropped.has(n.localName))return;
      const math=formula(n);if(math){text+=inline(math);return;}
      if(n.localName==='br'){text+='\n';return;}
      const block=blocks.has(n.localName);if(block&&text&&!text.endsWith('\n'))text+='\n';
      for(const child of n.childNodes)cellText(child);
      if(block&&!text.endsWith('\n'))text+='\n';
     }
     for(const child of cell.childNodes)cellText(child);
     td.textContent=textSource(text.trim());
    }
   }
   const rows=root.ReportTables.parseHTML(clean.outerHTML);if(!rows)throw Error('剪贴板表格无法转换');
   const obj=table(rows);root.ReportTables.logicalGrid(obj);chunks.push(tableSnippet(obj));return;
  }
  if(tag==='svg'||tag==='math'||tag.includes(':')){
   if(node.querySelector('img')){for(const child of node.childNodes)visit(child);return;}
   if(/^(?:o:p)$/.test(tag)){for(const child of node.childNodes)visit(child);return;}
   throw Error('剪贴板包含尚不支持的嵌入对象，整段未插入；请拆开复制所需内容');
  }
  const block=blocks.has(tag);if(block&&buffer&&!buffer.endsWith('\n\n'))buffer+='\n\n';
  for(const child of node.childNodes)visit(child);
  if(block&&!buffer.endsWith('\n\n'))buffer+='\n\n';
 }
 for(const child of content.childNodes)visit(child);flush();
 if(!chunks.length)throw Error('剪贴板没有可插入的文字或图表');
 return {format:'hrs-object-clipboard-v1',markdown:chunks.join('\n\n')+'\n\n',assets,operation:'copy'};
}
root.ReportRichClipboard={matches,prepare};
})(typeof window==='undefined'?globalThis:window);
