/* Local application navigation must never be replaced by a document's URL. */
(function(root){
'use strict';
function externalURL(href){
 try{const url=new URL(href,root.location.href);return /^https?:$/.test(url.protocol)&&url.origin!==root.location.origin?url.href:null;}catch{return null;}
}
function decorate(container){
 for(const anchor of container.querySelectorAll('a[href]'))if(externalURL(anchor.getAttribute('href'))){anchor.target='_blank';anchor.rel='noopener noreferrer';}
}
function attach(container,{open,onError}={}){
 container.addEventListener('click',event=>{
  const a=event.target.closest('a[href]');if(!a||!container.contains(a)||a.hasAttribute('download'))return;
  const url=externalURL(a.getAttribute('href'));if(!url)return;
  event.preventDefault();event.stopPropagation();
  Promise.resolve().then(()=>open(url)).catch(error=>onError?.('无法调用系统浏览器：'+error.message));
 },true);
 // Middle-button activation must follow the same application boundary.
 container.addEventListener('auxclick',event=>{if(event.button===1&&event.target.closest('a[href]')&&externalURL(event.target.closest('a').getAttribute('href'))){event.preventDefault();event.target.closest('a').click();}},true);
}
root.ReportLinks={attach,decorate,externalURL};
})(typeof window==='undefined'?globalThis:window);
