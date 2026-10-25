/* Local application navigation must never be replaced by a document's URL. */
(function(root){
'use strict';
function localPath(href){
 if(typeof href!=='string'||!href||href.length>8192||/[\x00-\x1f\x7f-\x9f]/.test(href))return null;
 if(/^file:\/\//i.test(href)||/^[A-Za-z]:[\\/]/.test(href)||href.startsWith('\\\\'))return href;
 if(/^(?:[A-Za-z][A-Za-z0-9+.-]*:|#|\/)/.test(href))return null;
 return href;
}
function safeLink(href){
 if(typeof href!=='string'||/[\x00-\x1f\x7f-\x9f]/.test(href))return null;
 if(localPath(href)){
  if(/^[A-Za-z]:[\\/]/.test(href)){
   let path;try{path=decodeURIComponent(href);}catch{return null;}
   const parts=path.replace(/\\/g,'/').split('/');return 'file:///'+parts.map((part,i)=>i?encodeURIComponent(part):part).join('/');
  }
  return href;
 }
 if(/[\x20]/.test(href))return null;
 if(/^(?:https?:\/\/|mailto:|#)/i.test(href))return href;
 return href.startsWith('/')&&!href.startsWith('//')&&!href.includes('\\')?href:null;
}
function externalURL(href){
 try{const url=new URL(href,root.location.href);return /^https?:$/.test(url.protocol)&&url.origin!==root.location.origin?url.href:null;}catch{return null;}
}
function decorate(container){
 for(const anchor of container.querySelectorAll('a[href]'))if(externalURL(anchor.getAttribute('href'))||localPath(anchor.getAttribute('href'))){anchor.target='_blank';anchor.rel='noopener noreferrer';}
}
function attach(container,{open,openPath,onError}={}){
 container.addEventListener('click',event=>{
  const a=event.target.closest('a[href]');if(!a||!container.contains(a)||a.hasAttribute('download'))return;
  const href=a.getAttribute('href'),path=localPath(href),url=externalURL(href);if(!url&&!(path&&openPath))return;
  event.preventDefault();event.stopPropagation();
  Promise.resolve().then(()=>path?openPath(path):open(url)).catch(error=>onError?.((path?'无法打开路径：':'无法调用系统浏览器：')+error.message));
 },true);
 // Middle-button activation must follow the same application boundary.
 container.addEventListener('auxclick',event=>{const a=event.target.closest('a[href]');if(event.button===1&&a&&(externalURL(a.getAttribute('href'))||openPath&&localPath(a.getAttribute('href')))){event.preventDefault();a.click();}},true);
}
root.ReportLinks={attach,decorate,externalURL,localPath,safeLink};
if(typeof module!=='undefined'&&module.exports)module.exports=root.ReportLinks;
})(typeof window==='undefined'?globalThis:window);
