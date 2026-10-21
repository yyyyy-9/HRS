'use strict';
// Integrity checks must read archive bytes, not Electron's virtual ASAR folders.
const fs=process.versions.electron?require('original-fs'):require('node:fs'),fsp=fs.promises,path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const HOST=require('./config.json');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(check,label,timeout=25000){
 const end=Date.now()+timeout;
 do{const result=await check();if(result)return result;await delay(60);}while(Date.now()<end);
 throw Error('等待超时：'+label);
}
const readJSON=file=>JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
async function fileSHA(file){const hash=crypto.createHash('sha256');for await(const chunk of fs.createReadStream(file))hash.update(chunk);return hash.digest('hex');}
function inside(root,file){const rel=path.relative(root,file);return rel!==''&&!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel);}
async function verifyFiles(root,entries){
 const seen=new Set();
 for(const entry of entries){
  if(typeof entry.path!=='string'||entry.path.includes('\\')||entry.path.includes(':')||entry.path.split('/').some(x=>!x||x==='.'||x==='..'))throw Error('清单路径无效');
  if(seen.has(entry.path.toLowerCase()))throw Error('清单路径重复');seen.add(entry.path.toLowerCase());
  const target=path.join(root,...entry.path.split('/'));if(!inside(root,target))throw Error('清单越界');
  let cursor=root;for(const piece of entry.path.split('/')){cursor=path.join(cursor,piece);if((await fsp.lstat(cursor)).isSymbolicLink())throw Error('清单包含链接');}
  const stat=await fsp.stat(target);
  if(!stat.isFile()||stat.size!==entry.bytes||await fileSHA(target)!==entry.sha256)throw Error('文件校验失败：'+entry.path);
 }
}
async function verifyMembership(root,expected){
 const found=[],wanted=new Set(expected);
 async function walk(folder){for(const entry of await fsp.readdir(folder,{withFileTypes:true})){
  const target=path.join(folder,entry.name);if(entry.isSymbolicLink())throw Error('负载包含链接');
  if(entry.isDirectory())await walk(target);else found.push(path.relative(root,target).split(path.sep).join('/'));
 }}
 await walk(root);
 if(found.length!==wanted.size||found.some(name=>!wanted.has(name)))throw Error('负载有缺失或额外文件');
}
async function resolveCore(root,layout){
 let core=path.join(root,'resources','hrs','app'),expected=layout.core_manifest_sha256;
 const active=path.join(root,'resources','hrs','active.json');
 if(fs.existsSync(active)){
  const pointer=readJSON(active);
  if(!/^[a-f0-9]{64}$/.test(pointer.sha256))throw Error('核心更新指针无效');
  if(pointer.sha256!==layout.core_manifest_sha256)core=path.join(root,'resources','hrs','updates',pointer.sha256,'app');
  expected=pointer.sha256;
 }
 const manifest=readJSON(path.join(core,'MANIFEST.json'));
 if(await fileSHA(path.join(core,'MANIFEST.json'))!==expected)throw Error('核心清单摘要不匹配');
 await verifyFiles(core,manifest.files);
 await verifyMembership(core,['MANIFEST.json',...manifest.files.map(i=>i.path)]);
 const identity=readJSON(path.join(core,'release.json'));
 const capability=readJSON(path.join(core,'host_capabilities.json'));
 if(capability.schema!=='hrs-host-capabilities-v1'||capability.desktop_protocol!==HOST.protocol)throw Error('核心不支持当前桌面协议');
 if(identity.version!==manifest.version||identity.package_revision!==manifest.package_revision)throw Error('核心身份不匹配');
 const support=readJSON(path.join(root,'resources','hrs','word_support','MANIFEST.json'));
 if(support.browser_model_sha256!==await fileSHA(path.join(core,'web','bridge_model.js')))throw Error('核心与Word组件不兼容，请使用完整发行包');
 return {core,identity,manifestSHA:expected};
}
async function validateLayout(root){
 const layout=readJSON(path.join(root,'DESKTOP_MANIFEST.json'));
 if(layout.schema!=='hrs-desktop-layout-v1'||layout.protocol!==HOST.protocol)throw Error('桌面宿主协议不匹配');
 await verifyFiles(root,layout.files);
 for(const prefix of ['resources/app/','resources/hrs/runtime/','resources/hrs/word_support/']){
  await verifyMembership(path.join(root,...prefix.split('/').filter(Boolean)),layout.files.filter(i=>i.path.startsWith(prefix)).map(i=>i.path.slice(prefix.length)));
 }
 return {...await resolveCore(root,layout),layout};
}
async function startService({root,dataRoot,core,identity,manifestSHA,bridge,hwnd}){
 const python=path.join(root,'resources','hrs','runtime','python.exe');
 const stateFile=path.join(dataRoot,'data','.portable-instance.json');
 fs.mkdirSync(path.join(dataRoot,'data','logs'),{recursive:true});
 const bootstrap='import os,runpy,sys;core=sys.argv.pop(1);sys.path.insert(0,core);sys.argv[0]=os.path.join(core,"portable_host.py");runpy.run_path(sys.argv[0],run_name="__main__")';
 const env={...process.env,STUDIO_PORTABLE_NO_DIALOG:'1',PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',
  HRS_DESKTOP_BRIDGE:JSON.stringify(bridge),HRS_DESKTOP_HWND:hwnd,
  HRS_DESKTOP_PARENT_PID:String(process.pid),
  HRS_WORD_SUPPORT:path.join(root,'resources','hrs','word_support'),HRS_WORD_PYTHON:python};
 const pandoc=path.join(root,'resources','hrs','word_formula','pandoc.exe');if(fs.existsSync(pandoc))env.HRS_WORD_PANDOC=pandoc;
 const temp=path.join(dataRoot,'tmp');fs.mkdirSync(temp,{recursive:true});env.TEMP=temp;env.TMP=temp;
 delete env.PYTHONPATH;delete env.PYTHONHOME;
 const child=spawn(python,['-B','-c',bootstrap,core,'start','--root',dataRoot,'--no-browser'],{env,windowsHide:true,detached:true,stdio:['ignore','pipe','pipe']});
 let spawnError;child.on('error',error=>{spawnError=error;});
 const log=fs.createWriteStream(path.join(dataRoot,'data','logs','desktop-bootstrap.log'),{flags:'a'});
 child.stdout.pipe(log,{end:false});child.stderr.pipe(log,{end:false});child.on('close',()=>log.end());
 let state,url;
 try{
  state=await until(async()=>{
   if(spawnError)throw spawnError;
   if(child.exitCode!==null)throw Error('该数据目录已被另一服务使用，或Python启动失败；请查看日志并使用独立数据目录');
   try{const value=readJSON(stateFile);return value.pid===child.pid?value:false;}catch{return false;}
  },'本机服务启动');
  url='http://127.0.0.1:'+state.port;
  const health=await (await fetch(url+'/api/health',{signal:AbortSignal.timeout(5000)})).json();
  if(health.version!==identity.version||health.package_revision!==identity.package_revision||health.app_manifest_sha256!==manifestSHA||!health.desktop)throw Error('服务与所选核心不一致');
 }catch(error){
  if(state?.pid===child.pid)try{await fetch(url+'/api/portable/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:state.token}),signal:AbortSignal.timeout(3000)});}catch{}
  throw error;
 }
 async function closeOwned(){
  // A browser opened on this service owns its own page lease. Never stop it.
  const end=Date.now()+7000;
  while(child.exitCode===null&&Date.now()<end)await delay(60);
  if(child.exitCode===null){
   const summary=await (await fetch(url+'/api/portable/status',{signal:AbortSignal.timeout(3000)})).json();
   if(summary.windows>0){child.unref();child.stdout.unpipe(log);child.stderr.unpipe(log);child.stdout.destroy();child.stderr.destroy();log.end();return {shared:true};}
   await fetch(url+'/api/portable/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:state.token}),signal:AbortSignal.timeout(3000)});
   await until(()=>child.exitCode!==null,'所属服务退出',7000);
  }
  return {shared:false,exitCode:child.exitCode};
 }
 return {child,state,url,closeOwned,temp};
}
module.exports={validateLayout,verifyFiles,verifyMembership,resolveCore,startService,fileSHA,inside,readJSON,until,delay};
