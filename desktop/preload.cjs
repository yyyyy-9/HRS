'use strict';
const {contextBridge,ipcRenderer}=require('electron');
let closeHandler=null,commandHandler=null;
ipcRenderer.on('hrs:prepare-close',async(_event,id)=>{
 let ok=false;
 try{ok=closeHandler?await closeHandler()===true:false;}catch{}
 ipcRenderer.send('hrs:close-result',{id,ok});
});
ipcRenderer.on('hrs:command',(_event,command)=>commandHandler?.(command));
contextBridge.exposeInMainWorld('HRSHost',Object.freeze({
 protocol:Number(process.argv.find(value=>value.startsWith('--hrs-host-protocol='))?.split('=')[1]),
 onClose:handler=>{if(typeof handler==='function')closeHandler=handler;},
 onCommand:handler=>{if(typeof handler==='function')commandHandler=handler;},
 requestClose:()=>ipcRenderer.send('hrs:request-close'),
 print:html=>ipcRenderer.invoke('hrs:print',html)
}));
