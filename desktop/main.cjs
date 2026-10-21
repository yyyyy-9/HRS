'use strict';
const {app,BrowserWindow,Menu,ipcMain,dialog,shell}=require('electron');
const fs=require('node:fs'),fsp=fs.promises,path=require('node:path'),crypto=require('node:crypto'),http=require('node:http');
const {validateLayout,startService,inside,delay}=require('./host.cjs');
const HOST=require('./config.json');

function defaultDataRoot(){return path.join(process.env.LOCALAPPDATA||app.getPath('appData'),HOST.data_directory);}
function localTarget(target,origin){try{return new URL(target).origin===origin;}catch{return false;}}
function safeExternal(target){try{const value=new URL(target);return ['https:','http:','mailto:'].includes(value.protocol)&&!value.username&&!value.password;}catch{return false;}}

async function launch(options={}){
 const root=path.resolve(options.root||path.dirname(process.execPath)),dataRoot=path.resolve(options.dataRoot||defaultDataRoot());
 if(dataRoot===root||inside(root,dataRoot))throw Error('用户数据目录必须位于安装资源之外');
 fs.mkdirSync(dataRoot,{recursive:true});
 app.setName(HOST.product_name);
 app.setPath('userData',path.join(dataRoot,'desktop-profile'));
 app.commandLine.appendSwitch('disable-background-networking');
 app.commandLine.appendSwitch('disable-component-update');
 if(!app.requestSingleInstanceLock()){app.quit();return null;}
 await app.whenReady();
 app.setAppUserModelId(HOST.app_user_model_id);
 const selected=await validateLayout(root);
 const win=new BrowserWindow({width:1500,height:950,minWidth:880,minHeight:600,show:options.show!==false,
  title:HOST.product_name,icon:path.join(selected.core,'web','app-icon.png'),backgroundColor:'#ffffff',
  webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,
   partition:'persist:hrs',webSecurity:true,webviewTag:false,spellcheck:false,additionalArguments:['--hrs-host-protocol='+HOST.protocol]}});
 app.on('second-instance',()=>{if(win.isMinimized())win.restore();win.show();win.focus();});
 let service,bridgeServer,closing=false,approved=false,pendingReply=null,afterClose=null;
 const printWindows=new Set();
 const bridgeToken=crypto.randomBytes(32).toString('hex');
 const mainSender=event=>!win.isDestroyed()&&event.sender===win.webContents&&localTarget(event.senderFrame?.url||'',service?.url);

 async function renderHTML(html,{print=false}={}){
  if(typeof html!=='string'||Buffer.byteLength(html)>36*1024*1024)throw Error('打印快照无效或超过36MiB');
  const tmp=await fsp.mkdtemp(path.join(service.temp,'desktop-print-'));
  const htmlFile=path.join(tmp,'snapshot.html');await fsp.writeFile(htmlFile,html,'utf8');
  const printWindow=new BrowserWindow({show:false,parent:win,webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,
   partition:'hrs-print-'+crypto.randomUUID(),webSecurity:true,spellcheck:false}});
  printWindows.add(printWindow);
  printWindow.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  printWindow.webContents.on('will-navigate',event=>event.preventDefault());
  const fileURL=require('node:url').pathToFileURL(htmlFile).href;
  printWindow.webContents.session.webRequest.onBeforeRequest((details,done)=>done({cancel:!['data:','blob:','about:'].some(p=>details.url.startsWith(p))&&details.url!==fileURL}));
  try{
   await printWindow.loadFile(htmlFile);
   await printWindow.webContents.executeJavaScript('document.fonts.ready.then(()=>Promise.all([...document.images].map(i=>i.complete?Promise.resolve():new Promise((ok,no)=>{i.onload=ok;i.onerror=()=>no(Error("打印图片加载失败"))}))))');
   if(print){
    return await new Promise((resolve,reject)=>printWindow.webContents.print({silent:false,printBackground:true},(ok,reason)=>ok?resolve({ok:true}):reason==='Print job canceled'?resolve({ok:true,cancelled:true}):reject(Error(reason))));
   }
   return await printWindow.webContents.printToPDF({printBackground:true,preferCSSPageSize:true,pageSize:'A4'});
  }finally{printWindows.delete(printWindow);if(!printWindow.isDestroyed())printWindow.destroy();await fsp.rm(tmp,{recursive:true,force:true});}
 }
 bridgeServer=http.createServer(async(req,res)=>{
  const reply=(status,value)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(value));};
  if(req.method!=='POST'||req.url!=='/pdf'||req.headers.authorization!=='Bearer '+bridgeToken)return reply(403,{ok:false,error:'Private host capability required'});
  try{
   let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>16384)throw Error('Request too large');}
   const request=JSON.parse(body),html=await fsp.realpath(request.html),pdf=path.resolve(request.pdf);
   if(!service||!inside(service.temp,html)||path.dirname(html)!==path.dirname(pdf)||!['source.html','report.html'].includes(path.basename(html))||!['result.pdf','report.pdf'].includes(path.basename(pdf)))throw Error('Print paths outside owned temporary snapshot');
   if((await fsp.stat(html)).size>36*1024*1024)throw Error('Snapshot too large');
   const result=await renderHTML(await fsp.readFile(html,'utf8'));
   if(result.subarray(0,5).toString()!=='%PDF-')throw Error('No PDF output');
   await fsp.writeFile(pdf,result,{flag:'wx'});reply(200,{ok:true});
  }catch(error){reply(400,{ok:false,error:error.message});}
 });
 await new Promise((resolve,reject)=>{bridgeServer.once('error',reject);bridgeServer.listen(0,'127.0.0.1',resolve);});
 const nativeHandle=win.getNativeWindowHandle();
 const hwnd=(nativeHandle.length>=8?nativeHandle.readBigUInt64LE():BigInt(nativeHandle.readUInt32LE())).toString();
 try{service=await startService({root,dataRoot,...selected,bridge:{protocol:HOST.protocol,url:'http://127.0.0.1:'+bridgeServer.address().port,token:bridgeToken},hwnd});}
 catch(error){bridgeServer.close();win.destroy();throw error;}
 const origin=service.url;
 const clipboardPermissions=['clipboard-read','clipboard-sanitized-write'];
 win.webContents.session.setPermissionRequestHandler((wc,permission,callback,details)=>callback(wc===win.webContents&&localTarget(details.requestingUrl||wc.getURL(),origin)&&clipboardPermissions.includes(permission)));
 win.webContents.session.setPermissionCheckHandler((wc,permission,requestingOrigin)=>wc===win.webContents&&localTarget(requestingOrigin,origin)&&clipboardPermissions.includes(permission));
 win.webContents.session.webRequest.onBeforeRequest((details,done)=>{
  let cancel=false;try{const value=new URL(details.url);cancel=['http:','https:','ws:','wss:'].includes(value.protocol)&&value.host!==new URL(origin).host;}catch{cancel=true;}
  done({cancel});
 });
 const external=target=>{if(safeExternal(target))shell.openExternal(target).catch(error=>dialog.showErrorBox('无法打开链接',error.message));};
 win.webContents.on('will-navigate',(event,target)=>{if(!localTarget(target,origin)){event.preventDefault();external(target);}});
 win.webContents.setWindowOpenHandler(({url})=>{
  if(safeExternal(url)&&!localTarget(url,origin))external(url);
  else if(localTarget(url,origin)){
   const target=new URL(url);
   if(target.pathname.startsWith('/assets/')||['/api/download','/api/download-pdf','/api/print'].includes(target.pathname)){
    const viewer=new BrowserWindow({parent:win,width:1000,height:750,webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,partition:'persist:hrs'}});
    viewer.setMenu(null);viewer.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    viewer.webContents.on('will-navigate',(event,href)=>{if(!localTarget(href,origin))event.preventDefault();});viewer.loadURL(url);
   }
  }
  return {action:'deny'};
 });
 const closeResult=(event,result)=>{if(mainSender(event)&&pendingReply&&result?.id===pendingReply.id){pendingReply.resolve(result.ok===true);}};
 const requestClose=event=>{if(mainSender(event))win.close();};
 ipcMain.on('hrs:close-result',closeResult);ipcMain.on('hrs:request-close',requestClose);
 ipcMain.handle('hrs:print',async(event,html)=>{if(!mainSender(event))throw Error('Unknown print sender');return renderHTML(html,{print:true});});
 async function prepareClose(){
  const id=crypto.randomUUID();
  try{return await Promise.race([new Promise(resolve=>{pendingReply={id,resolve};win.webContents.send('hrs:prepare-close',id);}),delay(30000).then(()=>false)]);}
  finally{pendingReply=null;}
 }
 win.on('close',event=>{
  if(approved)return;
  event.preventDefault();if(closing)return;closing=true;
  prepareClose().then(async ok=>{
   if(!ok){closing=false;afterClose=null;await dialog.showMessageBox(win,{type:'warning',title:'窗口已保留',message:'当前操作或草稿尚未确认，窗口保持打开。',detail:'请等待操作完成，或检查草稿保存提示后重试。',buttons:['返回编辑器']});return;}
   // The core has durably flushed its current snapshot. Navigation releases the
   // original page lease before the window is destroyed; no force-kill of Python.
   await win.webContents.loadURL('about:blank');approved=true;win.destroy();
  }).catch(error=>{closing=false;afterClose=null;dialog.showErrorBox('无法安全退出',error.message);});
 });
 let closeResolve;const closed=new Promise(resolve=>closeResolve=resolve);
 win.on('closed',async()=>{
  ipcMain.removeListener('hrs:close-result',closeResult);ipcMain.removeListener('hrs:request-close',requestClose);ipcMain.removeHandler('hrs:print');
  try{
   for(const w of printWindows)if(!w.isDestroyed())w.destroy();
   const result=await service.closeOwned();
   await new Promise(resolve=>bridgeServer.close(resolve));
   if(afterClose)await afterClose();
   closeResolve(result);if(options.quitOnClose!==false)app.quit();
  }catch(error){dialog.showErrorBox('退出未完成',error.message);closeResolve({error:error.message});if(options.quitOnClose!==false)app.quit();}
 });
 app.on('before-quit',event=>{if(!approved&&!win.isDestroyed()){event.preventDefault();win.close();}});
 app.on('window-all-closed',()=>{});
 win.on('session-end',()=>{}); // OS termination remains protected by recoverable draft/lease expiry.
 Menu.setApplicationMenu(Menu.buildFromTemplate([
  {label:'文件',submenu:[{label:'导出 PDF',click:()=>win.webContents.send('hrs:command','pdf')},{label:'打印…',accelerator:'CmdOrCtrl+P',click:()=>win.webContents.send('hrs:command','print')},{type:'separator'},
   {label:'离线更新…',click:()=>offlineUpdate(false)},{label:'回退上一次核心更新…',click:()=>offlineUpdate(true)},{type:'separator'},
   {label:'退出',accelerator:'Alt+F4',click:()=>win.close()}]},
  {label:'编辑',submenu:[{role:'undo',label:'撤销'},{role:'redo',label:'重做'},{type:'separator'},{role:'cut',label:'剪切'},{role:'copy',label:'复制'},{role:'paste',label:'粘贴'},{role:'selectAll',label:'全选'}]},
  {label:'视图',submenu:[{role:'resetZoom',label:'实际大小'},{role:'zoomIn',label:'放大'},{role:'zoomOut',label:'缩小'},{role:'togglefullscreen',label:'全屏'}]},
  {label:'帮助',submenu:[{label:'关于 HRS',click:()=>dialog.showMessageBox(win,{type:'info',message:'HTML Report Studio '+selected.identity.version,detail:'共用HRS核心 · Electron '+process.versions.electron+'\n核心摘要：'+selected.manifestSHA,buttons:['确定']})}]}
 ]));
 function updateCommand(args){
  const {execFile}=require('node:child_process');
  return new Promise((resolve,reject)=>execFile(path.join(root,'resources','hrs','runtime','python.exe'),['-B',path.join(__dirname,'update.py'),'--root',root,'--data-dir',dataRoot,...args],{windowsHide:true,encoding:'utf8',env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}},(error,stdout,stderr)=>error?reject(Error(stderr||stdout||error.message)):resolve(JSON.parse(stdout))));
 }
 async function offlineUpdate(rollback){
  try{
   let args=['--rollback'];
   if(!rollback){const choice=await dialog.showOpenDialog(win,{title:'选择 HRS 离线核心更新包',properties:['openFile'],filters:[{name:'HRS update',extensions:['zip']}]});if(choice.canceled)return;args=['--package',choice.filePaths[0]];}
   const plan=await updateCommand([...args,'--plan']);
   const choice=await dialog.showMessageBox(win,{type:'question',title:rollback?'回退核心':'离线更新',message:plan.summary,detail:'当前草稿确认保存并退出后执行；工程和草稿保留。\n'+(plan.package_sha256||''),buttons:['取消','继续并重启'],defaultId:0,cancelId:0});
   if(choice.response!==1)return;
   afterClose=async()=>{try{await updateCommand([...args,...(plan.package_sha256?['--sha256',plan.package_sha256]:[])]);}catch(error){dialog.showErrorBox('更新失败，保留当前版本',error.message);}app.relaunch({args:['--data-dir='+dataRoot]});};
   win.close();
  }catch(error){dialog.showErrorBox('无法执行更新',error.message);}
 }
 const parameters=new URLSearchParams({portable_launch:service.state.desktop_launch});if(options.programmatic)parameters.set('programmatic','1');
 await win.loadURL(origin+'/web/index.html?'+parameters);
 return {window:win,service,selected,closed,renderHTML,root,dataRoot};
}

if(require.main===module){
 const argument=process.argv.find(x=>x.startsWith('--data-dir='));
 launch({dataRoot:argument?.slice(11)}).catch(error=>{dialog.showErrorBox('HRS 启动失败',error.message);app.exit(1);});
}
module.exports={launch,safeExternal,localTarget};
