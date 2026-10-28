/* A clipboard adapter around the original editor transactions and HRS IR API. */
(function(root){
'use strict';
const FORMAT='hrs-object-clipboard-v1';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function encode(value){let s='';for(const b of new TextEncoder().encode(JSON.stringify(value)))s+=String.fromCharCode(b);return btoa(s);}
function decode(value){return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(atob(value),c=>c.charCodeAt(0))));}
function parse(html,plain){
 if(!html)return null;const inert=document.createElement('template');inert.innerHTML=html;
 const node=inert.content.querySelector('[data-hrs-clipboard]');if(!node)return null;
 const bundle=decode(node.dataset.hrsClipboard);
 // Windows CF_UNICODETEXT normalizes line endings. Preserve the bundle's exact
 // source bytes, while comparing only the platform newline representation.
 if(bundle.format!==FORMAT||typeof bundle.markdown!=='string'||bundle.markdown.replace(/\r\n?/g,'\n')!==plain.replace(/\r\n?/g,'\n'))throw Error('对象剪贴板的源码与资源包不一致，请重新复制');
 return bundle;
}
function eligible(text){
 if(root.SourceBlocks.scan(text).some(r=>r.object))return true;
 const records=root.SourceMap.create(text,root.marked.lexer(root.SourceBlocks.normalized(text).text)).blocks;
 return records.some(r=>r.type!=='code'&&r.type!=='html'&&/!\[[^\]]*\]\([^)]+\)/.test(r.raw||r.token.raw));
}
function attach(editor,{request,context,commit,chooseImage,prepareRich,beforePaste,onError}={}){
 let pasting=false;
 const same=before=>{const now=context();if(now.session!==before.session||now.markdown!==before.markdown||editor.selectionStart!==before.start||editor.selectionEnd!==before.end)throw Error('文稿或选区在剪贴板处理期间变化，请重新操作');};
 async function copy(text,item,operation='copy'){
  const before=context();
  const result=await request('/api/objects/copy',{...before,markdown:text,operation});
  same(before);
  if(!navigator.clipboard?.write||!root.ClipboardItem)throw Error('当前浏览器不支持携带附件复制，请使用 Chrome / Edge');
  const html='<pre>'+esc(text)+'</pre><span data-hrs-clipboard="'+encode(result.bundle)+'"></span>';
  await navigator.clipboard.write([new ClipboardItem({'text/plain':new Blob([text],{type:'text/plain'}),'text/html':new Blob([html],{type:'text/html'})})]);
  return true;
 }
 async function paste(bundle,replaceAll=false){
  if(pasting)return;pasting=true;let before=context(),local_files={};
  try{
   if(typeof bundle==='function'){bundle=await bundle();same(before);if(!bundle)return;}
   if(beforePaste){same(before);if(await beforePaste(bundle)===false)return;before=context();}
   let result;
   for(;;){
    same(before);
    try{result=await request('/api/objects/paste',{...before,bundle,target_markdown:replaceAll?'':before.markdown.slice(0,before.start)+before.markdown.slice(before.end),local_files});break;}
    catch(error){
     if(!error.message.startsWith('CHOOSE_IMAGE_SOURCE：'))throw error;
     const url=error.message.split('：').slice(2).join('：');
     const data=await chooseImage(url);if(!data)return;
     same(before);local_files[url]=data;
    }
   }
   same(before);
   if(replaceAll){commit(0,before.markdown.length,result.markdown,'import-markdown');return true;}
   const left=before.markdown.slice(0,before.start),right=before.markdown.slice(before.end);
   const value=(left&&!left.endsWith('\n')?'\n\n':'')+result.markdown+(right&&!result.markdown.endsWith('\n')?'\n\n':'');
   commit(before.start,before.end,value,'object-paste');return true;
  }catch(error){onError?.(error.message);}finally{pasting=false;}
 }
 editor.addEventListener('paste',event=>{
  if(event.defaultPrevented||editor.readOnly)return;
  const data=event.clipboardData,plain=data?.getData('text/plain')||'';
  const html=data?.getData('text/html')||'';
  if(!plain&&!html)return;
  try{
  // Pasting source examples inside a normal code fence remains literal text.
  const range=root.SourceMap.create(editor.value,root.marked.lexer(root.SourceBlocks.normalized(editor.value).text)).blocks.find(r=>r.start<editor.selectionStart&&r.end>editor.selectionStart);
  if(range?.type==='code'&&!/^report-(?:figure|table|image-group)$/.test(range.token.lang||''))return;
  const bundle=parse(html,plain);
  if(!bundle&&prepareRich&&root.ReportRichClipboard.matches(html)){
   event.preventDefault();paste(()=>prepareRich(html,plain));return;
  }
  if(!bundle&&!eligible(plain))return;
  event.preventDefault();paste(bundle||{format:FORMAT,markdown:plain,assets:{},operation:'copy'});
  }catch(error){event.preventDefault();onError?.(error.message);}
 });
 for(const operation of ['copy','cut'])editor.view.dom.addEventListener(operation,event=>{
  if(event.defaultPrevented||editor.selectionStart===editor.selectionEnd||editor.readOnly&&operation==='cut')return;
  const before=context(),text=editor.value.slice(before.start,before.end);if(!eligible(text))return;
  event.preventDefault();event.stopImmediatePropagation();copy(text,null,operation).then(()=>{same(before);if(operation==='cut')commit(before.start,before.end,'','object-cut');}).catch(e=>onError?.(e.message));
 },true);
 return {copy,pasteRich:document=>paste(()=>prepareRich(document.html,document.text,document)),
  importMarkdown:text=>paste({format:FORMAT,markdown:text,assets:{},operation:'import'},true)};
}
root.ReportObjectClipboard={attach,parse,eligible};
})(typeof window==='undefined'?globalThis:window);
