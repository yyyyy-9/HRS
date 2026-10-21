/* HF6 PF2 — read-only, offline Markdown bundle viewer.
 * It does not mutate the editor's Markdown, drafts, assets or project registry.
 * All relative files are resolved inside one ZIP or user-selected folder.
 */
(function(root){
'use strict';
const $=id=>document.getElementById(id);
const state={session:null,active:'',history:[]};
const escape=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
function resolveRelative(current,href){
 if(typeof href!=='string'||!href||href.length>600||href[0]==='/'||href.includes('\\')||/^[a-z][a-z0-9+.-]*:/i.test(href)||href.startsWith('//'))return null;
 let clean=href.split('#')[0].split('?')[0];
 if(!clean||clean.includes('%'))return null; // No ambiguous double decoding.
 const path=current.split('/').slice(0,-1);
 for(const segment of clean.split('/')){
  if(!segment||segment==='.')continue;
  if(segment==='..'){
   if(!path.length)return null;
   path.pop();
  }else if(segment.includes(':')||segment.includes('\0'))return null;
  else path.push(segment);
 }
 return path.length?path.join('/'):null;
}
function assetUrl(path){
 return '/api/readpack/file?reader_id='+encodeURIComponent(state.session.reader_id)+'&path='+encodeURIComponent(path);
}
function status(message,bad=false){const p=$('reader-status');p.textContent=message||'';p.dataset.bad=bad?'1':'0';}
async function post(path,data){
 const response=await fetch('/api/readpack/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-HRS-Reader-Action':'user-action'},body:JSON.stringify(data)});
 const result=await response.json();
 if(!response.ok||!result.ok)throw Error(result.error||'HTTP '+response.status);
 return result;
}
async function getDocument(path){
 const reply=await fetch('/api/readpack/document?reader_id='+encodeURIComponent(state.session.reader_id)+'&path='+encodeURIComponent(path),{cache:'no-store'});
 const result=await reply.json();
 if(!reply.ok||!result.ok)throw Error(result.error||'无法打开 Markdown');
 return result;
}
async function showDocument(path,addHistory=true){
 if(!state.session)return;
 try{
  status('正在打开 '+path);
  const doc=await getDocument(path);
  if(addHistory&&state.active&&state.active!==doc.path)state.history.push(state.active);
  state.active=doc.path;
  $('reader-current').textContent=doc.path;
  $('reader-back').disabled=!state.history.length;
  const article=$('reader-article');
  const renderer=new marked.Renderer();
  const profile=ReportProfile.normalize(doc.render_profile);
  renderer.html=raw=>ReportProfile.html(raw,profile);
  renderer.image=(href,title,text)=>{
   const file=resolveRelative(doc.path,href);
   if(!file||!/^.+\.(?:png|jpg|jpeg|gif|webp|svg)$/i.test(file))return '<span class="reader-warning">图片路径不安全或格式不支持：'+escape(text||href)+'</span>';
   return '<img loading="lazy" alt="'+escape(text||'图片')+'" src="'+escape(href)+'"'+(title?' title="'+escape(title)+'"':'')+'>';
  };
  renderer.link=(href,title,label)=>{
   return '<a href="'+escape(href||'')+'"'+(title?' title="'+escape(title)+'"':'')+'>'+label+'</a>';
  };
  const slugger=new marked.Slugger(),tokens=marked.lexer(SourceBlocks.normalized(doc.markdown).text);
  const records=SourceMap.create(doc.markdown,tokens).blocks,plan=ReportProfile.plan(doc.markdown,profile,records,doc.render_options);
  const numbers=new Map(plan.headings.map(h=>[records[h.index].token,h.number])),ordered=[];
  marked.walkTokens(tokens,t=>{if(t.type==='heading')ordered.push(numbers.get(t)||'');});
  const safeOptions={
   headingID:text=>'hrs-pack-heading-'+slugger.slug(text),
   imageURL:href=>{const file=resolveRelative(doc.path,href);return file&&/^.+\.(?:png|jpe?g|gif|webp|svg)$/i.test(file)?assetUrl(file):null;},
   linkAttrs:href=>{
    if(/^https?:\/\//i.test(href))return {href:ReportSafeHTML.safeLink(href),target:'_blank'};
    if(href.startsWith('#')){let anchor=href.slice(1);try{anchor=decodeURIComponent(anchor);}catch{}return {href:'#hrs-pack-heading-'+anchor};}
    const file=resolveRelative(doc.path,href);
    if(file&&/\.(?:md|markdown)$/i.test(file))return {href:'#',packDoc:file};
    if(file&&/\.(?:png|jpe?g|gif|webp|svg|pdf|json|csv|txt)$/i.test(file))return {href:assetUrl(file),target:'_blank'};
    return {className:'reader-unresolved'};
   }
  };
  // The low-level token parser does not merge Marked's defaults itself. Keep
  // the same installed extension renderers that produced these tokens.
  article.replaceChildren(ReportSafeHTML.fragment(marked.parser(tokens,{...marked.defaults,renderer,gfm:true,breaks:false,headerIds:true,mangle:false,hrsRenderProfile:profile}),safeOptions));
  ReportNotes.finalize(article,ReportNotes.prepare(marked,tokens),{prefix:'hrs-pack-note',render:body=>ReportSafeHTML.fragment(marked.parse(body,{renderer,hrsRenderProfile:profile}),safeOptions)});
  ReportLinks.decorate(article);
  article.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((heading,i)=>{if(ordered[i])heading.prepend(document.createTextNode(ordered[i]+' '));});
  article.querySelectorAll('img').forEach(image=>image.classList.add('reader-image'));
  for(const code of article.querySelectorAll('pre > code.language-mermaid')){
   const host=document.createElement('div');host.className='hrs-mermaid-render';host.dataset.hrsMermaid='1';host._mermaidSource=code.textContent;code.closest('pre').replaceWith(host);
  }
  const diagramErrors=await root.ReportMermaid.renderAll(article);
  if(diagramErrors.length)throw Error(diagramErrors.join('；'));
  if(root.ReportCodeHighlight)root.ReportCodeHighlight.decorateDOM(article);
  article.querySelectorAll('img.reader-image').forEach(image=>image.addEventListener('error',()=>{
   const warn=document.createElement('span');warn.className='reader-warning';warn.textContent='图片未能安全显示：'+(image.alt||image.src);image.replaceWith(warn);
  }));
  $('reader-nav').querySelectorAll('button[data-pack-doc]').forEach(btn=>btn.classList.toggle('active',btn.dataset.packDoc===doc.path));
  $('reader-scroll').scrollTop=0;
  status('只读 · 文档：'+state.session.documents.length+' 份 · 文件：'+state.session.file_count+' 项');
  // Marked's engineering equation extension renders source as safe <pre>.
  // Read-only bundles must turn those formula blocks into MathJax SVG too,
  // without changing raw Markdown or treating fenced code as mathematics.
  if(root.MathJax?.startup?.promise){
   root.MathJax.startup.promise.then(async()=>{
    for(const pre of [...article.querySelectorAll('pre')]){
     if(pre.querySelector('code'))continue;
     const eq=root.ReportEquations?.parse(pre.textContent);
     if(!eq||eq.raw.trim()!==pre.textContent.trim())continue;
     const span=document.createElement('span');span.className='markdown-math math-display';
     span.dataset.raw=eq.raw;span.dataset.tex=eq.tex;span.dataset.display='1';
     pre.replaceWith(span);
     if(/\\(?:href|url|require|includegraphics|htmlClass|htmlId|htmlStyle|htmlData|html)\b/i.test(eq.tex)){
      span.textContent='不支持的公式命令';continue;
     }
     try{
      const math=await root.MathJax.tex2svgPromise(eq.tex,{display:true});
      if(math.querySelector('merror,[data-mml-node="merror"],[data-mjx-error]')||!math.querySelector('svg'))throw Error('公式不合法');
      if(span.isConnected)span.append(math.querySelector('svg').cloneNode(true));
     }catch{if(span.isConnected)span.textContent='公式未能渲染';}
    }
    if(root.MathJax.typesetPromise)await root.MathJax.typesetPromise([article]);
   }).catch(()=>status('Markdown 已显示；部分公式无法排版',true));
  }
 }catch(error){status('打开失败：'+error.message,true);}
}
function showBundle(info){
 state.session=info;state.active='';state.history=[];
 $('reader-overlay').hidden=false;
 $('reader-title').textContent=info.source==='zip'?'ZIP 文档阅读包':'本地文件夹阅读包';
 const nav=$('reader-nav');nav.replaceChildren();
 for(const file of info.documents){
  const btn=document.createElement('button');btn.type='button';btn.textContent=file;btn.dataset.packDoc=file;
  btn.title=file;btn.onclick=()=>showDocument(file);
  nav.append(btn);
 }
 showDocument(info.main);
}
function toBase64(buffer){
 const bytes=new Uint8Array(buffer);const block=16384;let result='';
 for(let i=0;i<bytes.length;i+=block)result+=String.fromCharCode(...bytes.subarray(i,i+block));
 return btoa(result);
}
async function loadZip(file){
 if(!file)return;
 if(!/\.zip$/i.test(file.name)){status('请选择 ZIP 文件',true);return;}
 if(file.size>24*1024*1024){status('阅读包 ZIP 不能超过 24 MiB',true);return;}
 try{status('读取 ZIP 中，请稍候…');const base64=toBase64(await file.arrayBuffer());
  const info=await post('open-zip',{base64});showBundle(info);
 }catch(error){status('ZIP 打开失败：'+error.message,true);}
}
async function loadFolder(){
 try{status('请选择阅读包所在文件夹…');const info=await post('open-folder',{});showBundle(info);
 }catch(error){status('打开文件夹失败：'+error.message,true);}
}
function closeReader(){
 if(!state.session){$('reader-overlay').hidden=true;return;}
 const old=state.session.reader_id;
 state.session=null;state.active='';state.history=[];
 $('reader-overlay').hidden=true;$('reader-article').textContent='';$('reader-nav').replaceChildren();
 // Explicit release frees any uploaded ZIP bytes from local server memory.
 // No document project or disk file is touched.
 post('close',{reader_id:old}).catch(()=>{});
}
function init(){
 const opener=$('btn-readpack');if(!opener)return;
 ReportNotes.bindNavigation($('reader-article'));
 opener.addEventListener('click',()=>{$('reader-overlay').hidden=false;status('选择 ZIP 或本地文件夹，预览模式不会改变当前工程。');});
 $('reader-openzip').addEventListener('click',()=>$('file-reader-zip').click());
 $('file-reader-zip').addEventListener('change',e=>{const f=e.target.files?.[0];e.target.value='';if(f)loadZip(f);});
 $('reader-openfolder').addEventListener('click',loadFolder);
 $('reader-close').addEventListener('click',closeReader);
 $('reader-back').addEventListener('click',()=>{if(state.history.length)showDocument(state.history.pop(),false);});
 $('reader-article').addEventListener('click',event=>{
  const anchor=event.target.closest('a[data-pack-doc]');if(!anchor)return;
  event.preventDefault();showDocument(anchor.dataset.packDoc);
 });
 document.addEventListener('keydown',event=>{
  if($('reader-overlay').hidden)return;
  if(event.key==='Escape'){
   event.preventDefault();event.stopImmediatePropagation();closeReader();return;
  }
  // While the independent read-only panel is open, never let the hidden
  // editor receive Ctrl+S/E/Z/Y and silently alter report.md or drafts.
  if((event.ctrlKey||event.metaKey)&&['s','e','z','y'].includes(event.key.toLowerCase())){
   event.preventDefault();event.stopImmediatePropagation();
  }
 },true);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
root.HRSReadingPack={resolveRelative,closeReader};
})(window);
