/* HTML Report Studio HF4 export archive v2.
 * Browser and Node compatible. Pure JSON helpers; not part of the rendered HTML.
 */
(function(root){
'use strict';
const profiles=root.ReportProfile||(typeof module!=='undefined'&&module.exports?require('./render_profile.js'):null);
const themes=root.ReportTheme||(typeof module!=='undefined'&&module.exports?require('./color_theme.js'):null);
if(!profiles||!themes)return;
const QUALITY={compact:{label:'轻量发布',dpi:150},standard:{label:'标准发布',dpi:200},print:{label:'高清发布',dpi:300},original:{label:'原生质量',dpi:null}};
const MODE={recompilable:'可回编归档',reading:'纯阅读发布'};
const IMAGE_MIME={png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',gif:'image/gif',webp:'image/webp',svg:'image/svg+xml',emf:'application/octet-stream',pdf:'application/pdf'};
const MAX_ARCHIVE_SOURCE=30*1024*1024;
const MAX_HTML=36*1024*1024;
const paths=root.ReportAssetPaths||(typeof module!=='undefined'&&module.exports?require('./asset_paths.js'):null);
const validName={test:value=>!!paths.normalize(value,{originals:true})&&paths.normalize(value,{originals:true})===value};
function options(opts={}){
 const quality=opts.quality||'standard',sourceMode=opts.sourceMode||'recompilable';
 if(!Object.prototype.hasOwnProperty.call(QUALITY,quality)||!Object.prototype.hasOwnProperty.call(MODE,sourceMode))throw Error('HTML 导出设置不合法');
 if(opts.includePdfOriginals!==undefined&&typeof opts.includePdfOriginals!=='boolean')throw Error('PDF 原件选项无效');
 return {quality,sourceMode,dpi:QUALITY[quality].dpi,includePdfOriginals:!!opts.includePdfOriginals};
}
function bytesToBase64(bytes){
 let out='';for(let i=0;i<bytes.length;i+=12000)out+=String.fromCharCode(...bytes.subarray(i,i+12000));
 return btoa(out);
}
function base64ToBytes(text){
 if(typeof text!=='string'||text.length>MAX_ARCHIVE_SOURCE*2||text.length%4!==0)throw Error('归档附件 Base64 不合法');
 // The original large repeated-regex overflows JS stack on 6 MiB+ EMFs.
 // Validate in bounded chunks instead, including padding only at the end.
 for(let i=0;i<text.length;i+=12000){
  const chunk=text.slice(i,i+12000);
  if(!/^[A-Za-z0-9+/=]*$/.test(chunk))throw Error('归档附件 Base64 含非法字符');
 }
 if((text.slice(0,-4).includes('='))||!/^([A-Za-z0-9+/]{4}|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{2}==)$/.test(text.slice(-4)))
  throw Error('归档附件 Base64 填充不合法');
 const decoded=atob(text),out=new Uint8Array(decoded.length);
 for(let i=0;i<decoded.length;i++)out[i]=decoded.charCodeAt(i);
 return out;
}
async function deflateBytes(input){
 // Browser CompressionStream uses zlib-wrapped DEFLATE. The source is never
 // transformed in place. Environments lacking the API keep the old v2 layout.
 if(typeof root.CompressionStream!=='function')return null;
 const chunks=[],reader=new Blob([input]).stream().pipeThrough(new root.CompressionStream('deflate')).getReader();
 let count=0;
 for(;;){const {done,value}=await reader.read();if(done)break;count+=value.length;
  if(count>input.length){await reader.cancel();return null;}chunks.push(value);}
 const result=new Uint8Array(count);let pos=0;
 for(const item of chunks){result.set(item,pos);pos+=item.length;}
 return result;
}
async function inflateBytes(packed,limit){
 if(typeof root.DecompressionStream!=='function')throw Error('浏览器不支持无损归档解压，无法恢复工程原件');
 const chunks=[],reader=new Blob([packed]).stream().pipeThrough(new root.DecompressionStream('deflate')).getReader();
 let count=0;
 try{
  for(;;){const {done,value}=await reader.read();if(done)break;count+=value.length;
   if(count>limit||count>12*1024*1024)throw Error('归档附件解压超出原始大小限制');chunks.push(value);}
 }catch(e){try{await reader.cancel();}catch{}throw Error('归档 Deflate 解压失败或存在过量展开：'+e.message);}
 const out=new Uint8Array(count);let offset=0;for(const chunk of chunks){out.set(chunk,offset);offset+=chunk.length;}return out;
}
async function hash(bytes){
 if(!root.crypto?.subtle)throw Error('当前浏览器不支持 SHA-256；不可生成可校验归档');
 const digest=new Uint8Array(await root.crypto.subtle.digest('SHA-256',bytes));
 return [...digest].map(x=>x.toString(16).padStart(2,'0')).join('');
}
function targetSize(width,height,widthMm,opts){
 if(width<=0||height<=0||!Number.isFinite(widthMm)||widthMm<=0)throw Error('图片尺寸无效');
 if(opts.dpi===null)return {width,height,modified:false};
 let w=Math.ceil(widthMm/25.4*opts.dpi);
 // Never invent sharpness by upscaling an existing low-resolution preview.
 w=Math.min(w,width);
 let h=Math.max(1,Math.round(height*w/width));
 const factor=Math.min(1,4096/w,4096/h,Math.sqrt(12000000/(w*h)));
 if(factor<1){w=Math.max(1,Math.floor(w*factor));h=Math.max(1,Math.floor(h*factor));}
 return {width:w,height:h,modified:w!==width||h!==height,belowTarget:width < Math.ceil(widthMm/25.4*opts.dpi)};
}
function guessMime(name){return IMAGE_MIME[name.split('.').at(-1).toLowerCase()]||'';}
function snapshotProfile(opts){return {quality:opts.quality,targetDpi:opts.dpi,sourceMode:opts.sourceMode};}
function safeJson(payload){return JSON.stringify(payload).replace(/</g,'\\u003c').replace(/>/g,'\\u003e').replace(/&/g,'\\u0026').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');}
async function buildArchive({md,assetRecords,domRefs,opts,template,theme,renderProfile,renderOptions,colorTheme,savedMd,projectRevision}){
 renderProfile=profiles.normalize(renderProfile);renderOptions=profiles.normalizeOptions(renderOptions);colorTheme=themes.normalize(colorTheme);
  const config=options(opts);
 const profile=snapshotProfile(config);
 if(config.sourceMode==='reading')return {format:'html-report-studio-v2',profile,snapshot:{kind:'reading-only'},template,theme,renderProfile,renderOptions,colorTheme};
 if(typeof md!=='string')throw Error('工程 Markdown 缺失');
 const assetIndex={},blobs={},domHashes=new Set(Object.values(domRefs));let total=0;
 for(const name of Object.keys(assetRecords).sort()){
  if(!validName.test('assets/'+name))throw Error('资源路径不安全：'+name);
  const entry=assetRecords[name];
  if(!(entry.bytes instanceof Uint8Array)||!entry.bytes.length)throw Error('资源字节为空：'+name);
  total+=entry.bytes.length;
  if(total>MAX_ARCHIVE_SOURCE)throw Error('回编所需原始资源超过 30 MiB；请改用轻量发布或工程 ZIP，不会悄悄丢弃原件');
  const sha=await hash(entry.bytes),id='sha256:'+sha,mime=guessMime(name);
  if(!mime)throw Error('不支持的资源类型：'+name);
  const role=entry.role||(/\.(?:emf|pdf)$/i.test(name)?'source':'display');
  assetIndex['assets/'+name]={blobId:id,role};
  if(!blobs[id]){
   if(domHashes.has(id))blobs[id]={mime,bytes:entry.bytes.length,domRef:id};
   else{
    let packed=null;
    try{packed=await deflateBytes(entry.bytes);}catch{} // Keep raw if the browser's encoder fails.
    if(packed&&packed.byteLength+96 < entry.bytes.byteLength*0.93)
     blobs[id]={mime,bytes:entry.bytes.length,codec:'deflate',base64:bytesToBase64(packed)};
    else blobs[id]={mime,bytes:entry.bytes.length,base64:bytesToBase64(entry.bytes)};
   }
  }
 }
 const bodyBytes=new TextEncoder().encode(md);
 return {format:'html-report-studio-v2',profile,snapshot:{kind:md===savedMd?'saved':'working-copy',markdownSha256:await hash(bodyBytes),projectRevision:projectRevision||null},markdown:md,template,theme,renderProfile,renderOptions,colorTheme,assetIndex,blobs};
}
async function readArchive(payload,doc){
 if(!payload||payload.format!=='html-report-studio-v2')throw Error('HTML 不是 v2 归档');
 if(payload.profile?.sourceMode==='reading')throw Error('这是纯阅读 HTML，没有嵌入可恢复的 Markdown 工程数据');
 if(payload.profile?.sourceMode!=='recompilable')throw Error('源文件策略未受支持');
 const index=payload.assetIndex,blobs=payload.blobs;
 if(typeof payload.markdown!=='string'||!index||typeof index!=='object'||Array.isArray(index)||!blobs||typeof blobs!=='object'||Array.isArray(blobs))throw Error('归档源数据或附件索引缺失');
 if(new TextEncoder().encode(payload.markdown).length>10*1024*1024)throw Error('归档 Markdown 超限');
 if(payload.snapshot?.markdownSha256!==await hash(new TextEncoder().encode(payload.markdown)))throw Error('Markdown SHA-256 校验失败');
 const names=Object.keys(index);if(names.length>100)throw Error('附件数量超限');
 const blobKeys=Object.keys(blobs);if(blobKeys.length>100)throw Error('归档块数量超限');
 const data={};let total=0;
 for(const name of names){
  if(!validName.test(name))throw Error('归档文件名不安全：'+name);
  const item=index[name];if(!item||typeof item.blobId!=='string')throw Error('归档附件索引无效');
  const id=item.blobId,meta=blobs[id];
  if(!/^sha256:[a-f0-9]{64}$/.test(id)||!meta||typeof meta!=='object')throw Error('归档资源哈希无效：'+name);
  const suffixMime=guessMime(name.slice(7));
  if(meta.mime!==suffixMime||!Number.isSafeInteger(meta.bytes)||meta.bytes<1||meta.bytes>12*1024*1024)throw Error('归档资源类型或尺寸不合法：'+name);
  let encoded;
  if(Object.prototype.hasOwnProperty.call(meta,'domRef')){
   if(meta.domRef!==id)throw Error('DOM 图片引用哈希不一致：'+name);
   const imgs=[...doc.querySelectorAll('img[data-report-blob]')].filter(img=>img.getAttribute('data-report-blob')===id);
   if(imgs.length!==1)throw Error('DOM 图片哈希引用不存在或不唯一：'+name);
   const uri=imgs[0].getAttribute('src')||'';
   const prefix=`data:${meta.mime};base64,`;
   if(!uri.startsWith(prefix))throw Error('DOM 图片 MIME 与资源索引不匹配：'+name);
   encoded=uri.slice(prefix.length);
  }else{
   if(typeof meta.base64!=='string')throw Error('归档附件正文缺失：'+name);
   encoded=meta.base64;
  }
  const stored=base64ToBytes(encoded);
  if(meta.codec!==undefined && meta.codec!=='deflate')throw Error('不支持的归档压缩格式：'+name);
  if(meta.codec==='deflate'&&Object.prototype.hasOwnProperty.call(meta,'domRef'))throw Error('DOM 资源不能同时被压缩');
  const bytes=meta.codec==='deflate'?await inflateBytes(stored,meta.bytes):stored;
  if(bytes.length!==meta.bytes||await hash(bytes)!==id.slice(7))throw Error('归档附件 SHA-256 校验失败：'+name);
  total+=bytes.length;if(total>MAX_ARCHIVE_SOURCE)throw Error('归档附件总大小超过 30 MiB');
  data[name.slice(7)]=meta.codec==='deflate'?bytesToBase64(bytes):encoded;
 }
 // Every blob must have a referenced asset index (no orphan source blocks).
 const linked=new Set(names.map(name=>index[name].blobId));
 if(blobKeys.some(x=>!linked.has(x)))throw Error('归档包含未引用的数据块');
 if(payload.renderProfile!==undefined&&payload.renderProfile!==profiles.normalize(payload.renderProfile))throw Error('归档渲染模式无效');
 if(payload.renderOptions!==undefined&&typeof payload.renderOptions?.show_object_numbers!=='boolean')throw Error('归档显示选项无效');
 const renderOptions=profiles.normalizeOptions(payload.renderOptions),colorTheme=themes.normalize(payload.colorTheme);
 if(payload.colorTheme!==undefined&&payload.colorTheme!==colorTheme)throw Error('归档配色主题无效');
 return {markdown:payload.markdown,assets:data,template:payload.template,colorTheme,renderOptions,...(payload.renderProfile===undefined?{}:{renderProfile:payload.renderProfile})};
}
root.ReportExportArchive={QUALITY,MODE,MAX_HTML,options,targetSize,guessMime,hash,bytesToBase64,base64ToBytes,safeJson,buildArchive,readArchive};
if(typeof module==='object'&&module.exports)module.exports=root.ReportExportArchive;
})(typeof window!=='undefined'?window:globalThis);
