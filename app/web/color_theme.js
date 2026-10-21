/* Color is independent of render profile, document template and source text. */
(function(root){
'use strict';
const settings=root.ReportSettings||(typeof module!=='undefined'&&module.exports?require('./product_settings.js'):null);
if(!settings)return;
const choices=settings.color_themes.choices,names=choices.map(item=>item.id),labels=choices.map(item=>item.label),DEFAULT=settings.color_themes.default;
function normalize(value){if(value==null||value==='default')return DEFAULT;if(!names.includes(value))throw Error('未知配色主题');return value;}
function fromURL(search){const q=new URLSearchParams(search);if(!q.has('theme'))return null;try{return normalize(q.get('theme'));}catch{return DEFAULT;}}
function path(value){return '/web/'+choices.find(item=>item.id===normalize(value)).stylesheet;}
const pending=new WeakMap(),LOAD_TIMEOUT_MS=8000;
async function apply(doc,value,{timeout=LOAD_TIMEOUT_MS}={}){
 const name=normalize(value),link=doc.getElementById('hrs-theme-link');
 if(!link)throw Error('配色样式入口缺失');
 const href=path(name);
 pending.get(doc)?.cancel();
 if(link.getAttribute('href')!==href){
  // Keep the last working stylesheet until the new sheet actually loads.
  // Every request owns its handlers; a lost load event cannot hold UI leases forever.
  const candidate=link.cloneNode(false);candidate.removeAttribute('id');candidate.media='not all';candidate.href=href;
  let timer,cancel,committed=false;
  const ready=new Promise((resolve,reject)=>{
   cancel=()=>reject(Error('配色切换已被新的操作替代'));
   candidate.onload=resolve;candidate.onerror=()=>reject(Error('配色文件无法加载：'+name));
   timer=setTimeout(()=>reject(Error('配色加载超时，已保留原主题')),timeout);
  });
  const task={cancel};pending.set(doc,task);doc.head.append(candidate);
  try{await ready;if(pending.get(doc)!==task)throw Error('配色切换已过期');candidate.media=link.media;candidate.id=link.id;link.replaceWith(candidate);committed=true;}
  finally{clearTimeout(timer);candidate.onload=null;candidate.onerror=null;if(!committed)candidate.remove();if(pending.get(doc)===task)pending.delete(doc);}
 }
 doc.documentElement.dataset.colorTheme=name;return name;
}
const api={names,labels,normalize,fromURL,path,apply};root.ReportTheme=api;
if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
