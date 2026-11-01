/* Shared UI leases and bounded requests. Nested operations cannot unlock peers. */
/// <reference path="./interfaces.d.ts" />
(function(root){
'use strict';
/** @param {HrsOperationOptions} options @returns {HrsOperations} */
function create({editor,onEditing=()=>{}}){
 /** @type {Set<{nodes:HrsControl[],editing:boolean,released:boolean}>} */
 const leases=new Set();
 /** @type {Map<HrsControl,{count:number,disabled:boolean}>} */
 const controls=new Map();
 function refresh(){const locked=[...leases].some(l=>l.editing);editor.readOnly=locked;onEditing(locked);}
 /** @param {HrsLeaseOptions} options */
 function acquire({nodes=[],editing=false}={}){
  const lease={nodes:[...new Set(nodes)].filter(Boolean),editing,released:false};
  for(const node of lease.nodes){let entry=controls.get(node);if(!entry){entry={count:0,disabled:node.disabled};controls.set(node,entry);}entry.count++;node.disabled=true;}
  leases.add(lease);refresh();
  return ()=>{if(lease.released)return;lease.released=true;leases.delete(lease);
   for(const node of lease.nodes){const entry=/** @type {{count:number,disabled:boolean}} */(controls.get(node));if(--entry.count===0){node.disabled=entry.disabled;controls.delete(node);}}
   refresh();
  };
 }
 /** @param {HrsControl} node @param {boolean} value */
 function setDisabled(node,value){const entry=controls.get(node);if(entry)entry.disabled=value;node.disabled=entry?true:value;}
 return {acquire,setDisabled,get busy(){return leases.size>0;},get editing(){return [...leases].some(l=>l.editing);}};
}
/**
 * @param {string} path @param {string} method @param {HrsJsonValue} [data]
 * @param {Record<string,string>} extraHeaders @param {HrsRequestOptions} options
 * @returns {Promise<HrsApiResponse>}
 */
async function request(path,method='GET',data,extraHeaders={},options={}){
 const controller=new AbortController(),timeout=options.timeout??120000;let timedOut=false;
 const abort=()=>controller.abort(options.signal?.reason);
 if(options.signal?.aborted)abort();else options.signal?.addEventListener('abort',abort,{once:true});
 const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeout);
 try{
  const res=await fetch(path,{method,headers:{...(data?{'Content-Type':'application/json'}:{}),...extraHeaders},
   body:data?JSON.stringify(data):undefined,signal:controller.signal});
  /** @type {HrsApiResponse} */
  let payload;try{payload=await res.json();}catch{throw Error('服务返回了无法读取的响应，请查看服务状态');}
  if(!payload||typeof payload!=='object'||Array.isArray(payload)||typeof payload.ok!=='boolean')throw Error('服务返回了无法读取的响应，请查看服务状态');
  if(!res.ok||!payload.ok){const failure=payload.ok?null:payload;const error=/** @type {HrsRequestError} */(Error(failure?.error||'HTTP '+res.status));error.status=res.status;error.code=failure?.code||'REQUEST_REJECTED';throw error;}
  return payload;
 }catch(error){
  if(controller.signal.aborted){const aborted=/** @type {HrsRequestError} */(Error(timedOut?'请求超时；请核对服务状态后再操作':'请求已取消'));aborted.code=timedOut?'REQUEST_TIMEOUT':'REQUEST_CANCELLED';throw aborted;}
  throw error;
 }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',abort);}
}
root.ReportOperations={create,request};
if(typeof module!=='undefined'&&module.exports)module.exports=root.ReportOperations;
})(typeof window==='undefined'?globalThis:window);
