/* A separate-process protocol peer. This is not a manual browser UI test. */
'use strict';
const fs=require('node:fs'),path=require('node:path');
const [url,out]=process.argv.slice(2);
const post=async(route,body)=>{
 const response=await fetch(url+'/api/portable/'+route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const data=await response.json();if(!response.ok)throw Error(data.error);return data;
};
(async()=>{
 const credentials=await post('join',{launch:'',desktop:false});
 const ws=new WebSocket(url.replace('http:','ws:')+'/api/portable/events?'+new URLSearchParams({instance:credentials.instance,window:credentials.window,secret:credentials.secret}));
 await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 fs.writeFileSync(path.join(out,'EXTERNAL_LEASE_READY.json'),JSON.stringify({pid:process.pid,boundary:'separate-process protocol client'}));
 await new Promise(resolve=>{const timer=setInterval(()=>{if(fs.existsSync(path.join(out,'RELEASE_LEASE.json'))){clearInterval(timer);resolve();}},80);});
 await post('leave',credentials);ws.close();
 console.log('PASS separate lease released');
})().catch(error=>{console.error(error);process.exitCode=1;});
