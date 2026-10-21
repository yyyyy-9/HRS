/* Small, explicit Markdown extensions. No Quarto runtime or copied parser. */
(function(root){
'use strict';
const groupOpen=/^ {0,3}:::[ \t]+\{([^\r\n]*)\}[ \t]*$/;
const asset=/^assets\/[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.(?:png|jpe?g|gif|webp|svg)$/i;
const sourceAsset=/^assets\/([a-f0-9]{16})\.(emf|pdf|svg|png|jpe?g|webp)$/i;
const imageLine=/^!\[((?:\\.|[^\]\\])*)\]\(([^\s()]+)\)(?:\s+\{([^\r\n{}]+)\})?$/;
const rendKeys=['format','dpi','page','width','height','engine'];
function isGroupOpen(line){const m=String(line).replace(/\r$/,'').match(groupOpen);return !!m&&/(?:#fig-|layout-ncol)/.test(m[1]);}
function plain(value){return value.replace(/\\([\\\[\]])/g,'$1');}
function escapeLabel(value){return value.replace(/([\\\[\]])/g,'\\$1');}
function validateGroup(obj){
 if(!obj||obj.schema!=='report-image-group-v1'||!/^fig-[A-Za-z0-9_-]{1,60}$/.test(obj.id))throw Error('组图 ID 必须为 fig- 开头的稳定标识');
 const count=obj.images?.length;
 if(![1,2,3,4].includes(obj.columns)||!Array.isArray(obj.images)||count<2||count>12)throw Error('组图支持 2–12 张图片、每行 1–4 列');
 if(obj.rows!==undefined&&(!Number.isInteger(obj.rows)||obj.rows<1||obj.rows>3))throw Error('组图指定行数必须是 1–3');
 if(obj.showSubfigureLabels!==undefined&&typeof obj.showSubfigureLabels!=='boolean')throw Error('子图序号必须为显示或隐藏');
 if(count>obj.columns*(obj.rows||3))throw Error('组图图片超过行列容量；请增大行列数或移除图片');
 for(const text of [obj.caption,...obj.images.map(img=>img.caption)])if(typeof text!=='string'||text.length>300||/[\r\n]/.test(text))throw Error('图题/子图说明须为一行文字，最多 300 字');
 if(obj.caption.trim()!==obj.caption||obj.caption.startsWith(':::')||obj.caption.startsWith('!['))throw Error('组图题不能有首尾空白或以 ::: / ![ 开头');
 for(const img of obj.images){
  if(!img||!asset.test(img.src))throw Error('组图图片必须位于本项目 assets/ 下');
  if(img.sourceAsset!==undefined){
   const m=String(img.sourceAsset).match(sourceAsset);
   if(!m)throw Error('组图原件路径无效');
   if(['emf','pdf'].includes(m[2].toLowerCase())&&img.src.toLowerCase()!==`assets/${m[1].toLowerCase()}.png`)throw Error('EMF/PDF 原件与 PNG 预览必须同名');
  }
  if(img.rasterFallback!==undefined){
   const m=img.src.match(/^assets\/([a-f0-9]{16})\.svg$/i);
   if(!m||img.rasterFallback.toLowerCase()!==`assets/${m[1].toLowerCase()}.png`)throw Error('备用 PNG 必须与 SVG 同名');
  }
  if(img.rendition!==undefined){
   const info=img.rendition;
   if(!info||typeof info!=='object'||Array.isArray(info)||Object.keys(info).some(k=>!rendKeys.includes(k)))throw Error('组图预览元数据字段无效');
   if(info.dpi!==undefined&&(!Number.isFinite(info.dpi)||info.dpi<=0||info.dpi>600))throw Error('组图预览 DPI 无效');
   for(const key of ['page','width','height'])if(info[key]!==undefined&&(!Number.isInteger(info[key])||info[key]<1||info[key]>20000))throw Error('组图预览尺寸或 DPI 无效');
   if(info.format!==undefined&&!['png','svg','jpeg','webp'].includes(info.format))throw Error('组图预览格式无效');
   if(info.engine!==undefined&&!/^[A-Za-z0-9_-]{1,36}$/.test(info.engine))throw Error('组图预览引擎标识无效');
  }
 }
 return obj;
}
function parseGroup(raw){
 const lines=String(raw).replace(/\r\n?/g,'\n').trimEnd().split('\n'),open=lines[0]?.match(groupOpen);
 if(!open||!/^ {0,3}:::[ \t]*$/.test(lines.at(-1)))throw Error('组图围栏未闭合或格式错误');
 const attributes=open[1].trim().split(/\s+/);let id,columns,rows,showSubfigureLabels;
 for(const part of attributes){
  if(part.startsWith('#')&&id===undefined)id=part.slice(1);
  else if(/^layout-ncol=[1-4]$/.test(part)&&columns===undefined)columns=+part.at(-1);
  else if(/^layout-nrow=[1-3]$/.test(part)&&rows===undefined)rows=+part.at(-1);
  else if(part==='subfig-labels=off'&&showSubfigureLabels===undefined)showSubfigureLabels=false;
  else if(part==='subfig-labels=on'&&showSubfigureLabels===undefined)showSubfigureLabels=true;
  else throw Error('组图包含未支持的围栏属性');
 }
 const images=[];let caption='',seenCaption=false;
 for(const line of lines.slice(1,-1)){
  if(!line.trim())continue;
  const image=line.match(imageLine);
  if(image&&!seenCaption){
   const obj={src:image[2],caption:plain(image[1])};
   if(image[3]){
    const props=image[3].trim().split(/\s+/);
    const meta={};
    for(const pair of props){const match=pair.match(/^(source|fallback|format|dpi|page|width|height|engine)=([^\s{}]+)$/);if(!match||meta[match[1]]!==undefined)throw Error('组图图片元数据包含未知或重复字段');meta[match[1]]=match[2];}
    if(meta.source)obj.sourceAsset=meta.source;
    if(meta.fallback)obj.rasterFallback=meta.fallback;
    const rend={};for(const k of rendKeys)if(meta[k]!==undefined)rend[k]=['engine','format'].includes(k)?meta[k]:Number(meta[k]);
    if(Object.keys(rend).length)obj.rendition=rend;
   }
   images.push(obj);continue;
  }
  if(seenCaption||line.startsWith(':::')||line.startsWith('!['))throw Error('组图只允许本地图片行和最后一行组图题；复杂内容请保留源码');
  seenCaption=true;caption=line;
 }
 return validateGroup({schema:'report-image-group-v1',id,columns,...(rows===undefined?{}:{rows}),...(showSubfigureLabels===undefined?{}:{showSubfigureLabels}),caption,images});
}
function groupSnippet(obj){
 validateGroup(obj);
 const attrs=[`#${obj.id}`,`layout-ncol=${obj.columns}`];
 if(obj.rows!==undefined)attrs.push(`layout-nrow=${obj.rows}`);
 if(obj.showSubfigureLabels===false)attrs.push('subfig-labels=off');
 const pictures=obj.images.map(img=>{
  const meta=[];if(img.sourceAsset)meta.push(`source=${img.sourceAsset}`);
  if(img.rasterFallback)meta.push(`fallback=${img.rasterFallback}`);
  for(const key of rendKeys)if(img.rendition?.[key]!==undefined)meta.push(`${key}=${img.rendition[key]}`);
  return `![${escapeLabel(img.caption)}](${img.src})`+(meta.length?' {'+meta.join(' ')+'}':'');
 });
 return `::: {${attrs.join(' ')}}\n\n`+pictures.join('\n\n')+`\n\n${obj.caption}\n\n:::`;
}

function heading(raw,depth){
 const line=String(raw).replace(/[\r\n]+$/,''),opening=line.match(/^ {0,3}(#{1,6})[ \t]+/);
 if(!opening||opening[1].length!==depth)return null;
 let body=line.slice(opening[0].length),closing=body.match(/[ \t]+#+[ \t]*$/)?.[0]||'';
 if(closing)body=body.slice(0,-closing.length);
 const anchor=body.match(/[ \t]+\{#([^{}\s]+)\}[ \t]*$/);
 const id=anchor?.[1]||null,valid=!id||/^sec-[A-Za-z0-9_-]{1,60}$/.test(id);
 const title=(anchor?body.slice(0,-anchor[0].length):body).trim();
 return {id,valid,title,anchor:anchor?.[0]||'',closing};
}
function installMarked(marked){marked.use({extensions:[{name:'reportImageGroup',level:'block',
 start:src=>{const match=src.match(/^ {0,3}:::[ \t]+\{[^\r\n]*(?:#fig-|layout-ncol)[^\r\n]*\}/m);return match?.index;},
 tokenizer(src){const first=src.split('\n',1)[0];if(!isGroupOpen(first))return;
  const close=/^ {0,3}:::[ \t]*(?:\n|$)/gm;close.lastIndex=first.length+1;const match=close.exec(src);
  return {type:'reportImageGroup',raw:match?src.slice(0,match.index+match[0].length):src};
 } }]});}
const api={isGroupOpen,parseGroup,validateGroup,groupSnippet,heading,installMarked};
if(typeof module!=='undefined'&&module.exports)module.exports=api;root.ReportLayout=api;
})(typeof window!=='undefined'?window:globalThis);
