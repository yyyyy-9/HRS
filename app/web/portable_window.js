/* Portable-only page leases. The streamed heartbeat survives hidden timer
   throttling; individual document instances never share a session ID. */
(() => {
'use strict';
function attach() {
 let credentials=null,stream=null,heartbeat=null,retryTimer=null,enabled=false,active=true,joining=null,epoch=0,instance=null;
 const post=(path,body,keepalive=false)=>fetch('/api/portable/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),keepalive,cache:'no-store'});
 function closeConnection(){clearInterval(heartbeat);clearTimeout(retryTimer);heartbeat=null;stream?.close();stream=null;}
 function connect(next){
  if(!active||credentials!==next)return;
  stream=new WebSocket('ws://'+location.host+'/api/portable/events?'+new URLSearchParams(next));
  stream.onclose=()=>{if(active&&credentials===next)retryTimer=setTimeout(()=>connect(next),1000);};
 }
 async function start(){
  active=true;if(joining||credentials)return joining;
  const run=++epoch;
  joining=(async()=>{
   try{
    const reply=await fetch('/api/health',{cache:'no-store'}),health=await reply.json();
    if(!health.portable||!active||run!==epoch)return;
    enabled=true;
    if(instance&&health.portable_instance!==instance)return;
    instance=health.portable_instance;
    const launch=new URLSearchParams(location.search).get('portable_launch')||'';
    const result=await post('join',{launch,desktop:!!window.HRSHost}),joined=await result.json();
    if(!result.ok||!joined.ok)return;
    const next={instance:joined.instance,window:joined.window,secret:joined.secret};
    if(!active||run!==epoch){post('leave',next,true).catch(()=>{});return;}
    credentials=next;
    connect(next);
    // Most liveness is carried by the TCP stream. This pulse also reconnects
    // after an expired lease, for example after a long network interruption.
    heartbeat=setInterval(pulse,15000);
   }catch{}
  })().finally(()=>{joining=null;});
  return joining;
 }
 async function pulse(){
  if(!active||!credentials)return;
  const current=credentials;
  try{
   const reply=await post('pulse',current);
   if(!reply.ok&&credentials===current&&active){credentials=null;closeConnection();await start();}
  }catch{}
 }
 function leave(draft,base){
  active=false;++epoch;closeConnection();
  if(!credentials)return false;
  const current=credentials;credentials=null;
  const payload={...current,...(draft?{draft}:{})};
  try{
   const blob=new Blob([JSON.stringify(payload)],{type:'application/json'});
   if(blob.size<=60000&&navigator.sendBeacon('/api/portable/leave',blob))return true;
   const delta=window.DraftSnapshot?.closeDelta(draft,base);
   if(delta){
    const compact=new Blob([JSON.stringify({...current,draft_delta:delta})],{type:'application/json'});
    if(compact.size<=60000&&navigator.sendBeacon('/api/portable/leave',compact))return true;
   }
   // A large draft exceeds the browser's keepalive budget. Its ordinary draft
   // flush was requested at beforeunload/visibilitychange; try again here and
   // release the lease separately, allowing the host to drain document writes.
   if(draft)fetch('/api/draft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(draft)}).catch(()=>{});
   navigator.sendBeacon('/api/portable/leave',new Blob([JSON.stringify(current)],{type:'application/json'}));
  }catch{}
  return true;
 }
 window.addEventListener('pageshow',event=>{if(event.persisted){active=true;start();}});
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)pulse();});
 return {start,leave,get enabled(){return enabled;}};
}
window.PortableWindow={attach};
})();
