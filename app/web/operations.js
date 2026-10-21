/* Shared UI leases and bounded requests. Nested operations cannot unlock peers. */
(function(root){
'use strict';
function create({editor,onEditing=()=>{}}){
 const leases=new Set(),controls=new Map();
 function refresh(){const locked=[...leases].some(l=>l.editing);editor.readOnly=locked;onEditing(locked);}
 function acquire({nodes=[],editing=false}={}){
  const lease={nodes:[...new Set(nodes)].filter(Boolean),editing,released:false};
  for(const node of lease.nodes){let entry=controls.get(node);if(!entry){entry={count:0,disabled:node.disabled};controls.set(node,entry);}entry.count++;node.disabled=true;}
  leases.add(lease);refresh();
  return ()=>{if(lease.released)return;lease.released=true;leases.delete(lease);
   for(const node of lease.nodes){const entry=controls.get(node);if(--entry.count===0){node.disabled=entry.disabled;controls.delete(node);}}
   refresh();
  };
 }
 function setDisabled(node,value){const entry=controls.get(node);if(entry)entry.disabled=value;node.disabled=entry?true:value;}
 return {acquire,setDisabled,get busy(){return leases.size>0;},get editing(){return [...leases].some(l=>l.editing);}};
}
async function request(path,method='GET',data,extraHeaders={},options={}){
 const controller=new AbortController(),timeout=options.timeout??120000;let timedOut=false;
 const abort=()=>controller.abort(options.signal.reason);
 if(options.signal?.aborted)abort();else options.signal?.addEventListener('abort',abort,{once:true});
 const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeout);
 try{
  const res=await fetch(path,{method,headers:{...(data?{'Content-Type':'application/json'}:{}),...extraHeaders},
   body:data?JSON.stringify(data):undefined,signal:controller.signal});
  let payload;try{payload=await res.json();}catch{throw Error('服务返回了无法读取的响应，请查看服务状态');}
  if(!res.ok||!payload.ok){const error=Error(payload.error||'HTTP '+res.status);error.status=res.status;error.code=payload.code||'REQUEST_REJECTED';throw error;}
  return payload;
 }catch(error){
  if(controller.signal.aborted){const aborted=Error(timedOut?'请求超时；请核对服务状态后再操作':'请求已取消');aborted.code=timedOut?'REQUEST_TIMEOUT':'REQUEST_CANCELLED';throw aborted;}
  throw error;
 }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',abort);}
}
root.ReportOperations={create,request};
if(typeof module!=='undefined'&&module.exports)module.exports=root.ReportOperations;
})(typeof window==='undefined'?globalThis:window);
