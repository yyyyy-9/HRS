/* Explicit Electron integration driver; shipped only with Source/Full tests. */
'use strict';
const {app,dialog,shell,clipboard,ClipboardItem}=require('electron');
const fs=require('node:fs'),path=require('node:path');
const {launch}=require('../desktop/main.cjs'),{until,delay}=require('../desktop/host.cjs');
const argument=process.argv.find(x=>x.startsWith('--test-config='));
if(!argument)throw Error('Explicit test config required');
const cfg=JSON.parse(fs.readFileSync(argument.slice(14),'utf8'));
const report={status:'RUNNING',boundaries:{system_print:'NOT_RUN',external_browser:'NOT_RUN',IME:'NOT_RUN'}};
let host,clipboardBackup;
dialog.showMessageBox=async()=>({response:0});dialog.showErrorBox=(title,detail)=>{report.host_error={title,detail};};
shell.openExternal=async target=>{report.external_target=target;};
(async()=>{
 try{
  host=await launch({root:cfg.layout,dataRoot:cfg.state,show:false,programmatic:true,quitOnClose:false});
  const win=host.window,evaluate=code=>win.webContents.executeJavaScript(code,true);
  await evaluate(`(async()=>{await ReportStudioProgrammatic.ready();await ReportStudioProgrammatic.open(${JSON.stringify(cfg.document_id)});})()`);
  await until(()=>evaluate("document.querySelector('#preview-content .markdown-math svg')&&document.querySelector('#preview-content img')&&[...document.querySelectorAll('#preview-content img')].every(i=>i.complete&&i.naturalWidth)"),'rendered core',25000);
  report.health=await(await fetch(host.service.url+'/api/health')).json();
  fs.writeFileSync(path.join(cfg.out,'DESKTOP_READY.json'),JSON.stringify({pid:process.pid,service_pid:host.service.child.pid,url:host.service.url}));
  report.node_isolated=await evaluate("typeof require==='undefined'&&typeof process==='undefined'&&HRSHost.protocol===1");
  if(!report.node_isolated)throw Error('Renderer isolation missing');
  if(cfg.mode==='crash'){
   fs.writeFileSync(path.join(cfg.out,'CRASH_READY.json'),JSON.stringify({pid:process.pid,service_pid:host.service.child.pid,url:host.service.url}));
   return; // The parent test terminates only this test's Electron main process.
  }
  if(cfg.mode==='restart'){
   win.close();report.restart_close=await host.closed;report.status='PASS';return;
  }
  await evaluate("(()=>{const e=document.querySelector('#markdown').sourceEditor;e.view.dispatch({changes:{from:e.value.length,insert:'\\n正式保存😀\\n'}});document.querySelector('#btn-save').click()})()");
  await until(()=>fs.readFileSync(path.join(cfg.project,'report.md'),'utf8').includes('正式保存😀'),'formal save');report.formal_save=true;
  report.stage='clipboard-backup';
  clipboardBackup=await Promise.all((await clipboard.read()).map(async item=>new ClipboardItem(Object.fromEntries(await Promise.all(item.types.map(async type=>[type,await item.getType(type)]))))));
  report.stage='clipboard-write';
  await clipboard.writeText('桌面剪贴板😀');
  report.stage='clipboard-read';
  win.show();win.focus();
  await until(()=>evaluate('document.hasFocus()'),'actual clipboard window focus');report.window_visible_for_clipboard=true;
  report.clipboard_result=await evaluate("(async()=>{try{return {value:await navigator.clipboard.readText()}}catch(e){return {name:e.name,error:e.message}}})()");
  report.clipboard=report.clipboard_result.value === '桌面剪贴板😀';
  if(!report.clipboard)throw Error('Clipboard unavailable');
  await evaluate("(()=>{const e=document.querySelector('#markdown').sourceEditor,a=e.value.indexOf('```report-figure'),b=e.value.indexOf('```',a+3)+3;e.setSelectionRange(a,b);e.focus()})()");
  win.webContents.copy();
  await until(()=>evaluate("(async()=>{const items=await navigator.clipboard.read();return items[0]?.types.includes('text/html')&&(await(await items[0].getType('text/html')).text()).includes('data-hrs-clipboard')})()"),'original rich object clipboard');
  report.rich_object_clipboard=true;
  await evaluate("(()=>{const e=document.querySelector('#markdown').sourceEditor;e.setSelectionRange(e.value.length,e.value.length)})()");
  win.hide();
  win.webContents.setZoomFactor(1.25);if(win.webContents.getZoomFactor()!==1.25)throw Error('Zoom failed');win.webContents.setZoomFactor(1);report.zoom=true;
  await evaluate("window.open('https://example.com/hrs-test','_blank')");
  await until(()=>report.external_target,'external interception');
  if(!win.webContents.getURL().startsWith(host.service.url))throw Error('External navigation replaced editor');
  report.external_preserves_window=true;
  report.boundaries.external_browser='INTERCEPTED';
  const before=fs.existsSync(path.join(cfg.project,'output'))?fs.readdirSync(path.join(cfg.project,'output')):[];
  report.stage='pdf-export';
  await evaluate("document.querySelector('#btn-pdf').click()");
  await until(async()=>{
   const toast=await evaluate("document.querySelector('#toast').textContent");
   if(/PDF.*失败|工程输出已阻止/.test(toast))throw Error(toast);
   return fs.existsSync(path.join(cfg.project,'output'))&&fs.readdirSync(path.join(cfg.project,'output')).some(n=>n.endsWith('.pdf')&&!before.includes(n));
  },'original PDF export',60000);
  const pdf=fs.readdirSync(path.join(cfg.project,'output')).find(n=>n.endsWith('.pdf')&&!before.includes(n));
  report.pdf=path.join(cfg.project,'output',pdf);if(fs.readFileSync(report.pdf).subarray(0,5).toString()!=='%PDF-')throw Error('Invalid PDF');
  await evaluate("(()=>{window.pdfOriginalFetch=window.fetch;window.fetch=(url,...args)=>String(url)==='/api/pdf/store'?Promise.resolve(new Response(JSON.stringify({ok:false,error:'test PDF refusal'}),{status:409})):window.pdfOriginalFetch(url,...args);document.querySelector('#btn-pdf').click()})()");
  await until(()=>evaluate("document.querySelector('#toast').textContent.includes('内置 PDF 生成失败')"),'native PDF refusal');
  await evaluate('void(window.fetch=window.pdfOriginalFetch)');report.pdf_failure_keeps_editor=win.webContents.getURL().startsWith(host.service.url);
  app.once('browser-window-created',(_event,w)=>{w.webContents.print=(options,callback)=>{report.boundaries.system_print='INTERCEPTED';report.print_dialog_options=options;callback(false,'Print job canceled');};});
  await evaluate("document.querySelector('#btn-print').click()");
  await until(()=>report.boundaries.system_print==='INTERCEPTED','native print call');
  await evaluate("document.querySelector('#btn-export-word').click()");
  await until(()=>evaluate("!!document.querySelector('#word-filename')"),'Word dialog');
  await evaluate("document.querySelector('#word-filename').value='Desktop_Native';document.querySelector('#modal-ok').click()");
  await until(()=>fs.readdirSync(path.join(cfg.project,'output')).some(n=>n.endsWith('.docx')),'native Word',100000);
  report.word=path.join(cfg.project,'output',fs.readdirSync(path.join(cfg.project,'output')).find(n=>n.endsWith('.docx')));
  await until(()=>evaluate("document.querySelector('#modal-title').textContent.includes('Word 已生成')"),'Word result');
  await evaluate("document.querySelector('#modal-ok').click()");
  // Fail only the next original draft request. Core must refuse window-X close.
  await evaluate("window.originalFetch=window.fetch;window.fetch=(url,...args)=>String(url)==='/api/draft'?Promise.resolve(new Response(JSON.stringify({ok:false,error:'test occupied draft'}),{status:409})):window.originalFetch(url,...args);const e=document.querySelector('#markdown').sourceEditor;e.view.dispatch({changes:{from:e.value.length,insert:'\\n窗口关闭恢复草稿😀\\n'}})");
  win.close();await until(()=>evaluate("document.querySelector('#toast').textContent.includes('窗口已保留')"),'close refusal');
  if(win.isDestroyed())throw Error('Window lost on failed draft');report.failed_close_retains_window=true;
  await evaluate('void(window.fetch=window.originalFetch)');
  // A protocol client owned by the external Python test parent survives actual
  // Electron exit. A second Electron window would not prove that boundary.
  await until(()=>fs.existsSync(path.join(cfg.out,'EXTERNAL_LEASE_READY.json')),'independent lease client');
  await until(async()=>{const s=await(await fetch(host.service.url+'/api/portable/status')).json();return s.windows>=2;},'second page lease');
  report.stage='capture-visible-window';console.log('[desktop test]',report.stage);
  win.show();win.focus();
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  const capture=await Promise.race([win.webContents.capturePage(),delay(8000).then(()=>{throw Error('Desktop capture timeout')})]);
  fs.writeFileSync(path.join(cfg.out,'DESKTOP.png'),capture.toPNG());
  report.stage='close-main';console.log('[desktop test]',report.stage);
  win.close();const closed=await Promise.race([host.closed,delay(40000).then(()=>{throw Error('Main close timeout')})]);
  if(!closed.shared)throw Error('Other window service was stopped');
  report.other_window_preserved=(await(await fetch(host.service.url+'/api/health')).json()).ok;
  const drafts=path.join(cfg.state,'data/projects/.drafts');
  report.close_draft=fs.readdirSync(drafts).some(n=>{try{return JSON.parse(fs.readFileSync(path.join(drafts,n,'state.json'),'utf8')).markdown.includes('窗口关闭恢复草稿😀');}catch{return false;}});
  if(!report.close_draft||fs.readFileSync(path.join(cfg.project,'report.md'),'utf8').includes('窗口关闭恢复草稿'))throw Error('Draft/formal separation failed');
  report.boundaries.other_window='separate-process protocol client; not browser UI';
  report.status='PASS';
 }catch(error){report.status='FAIL';report.error=error?.stack||String(error);
  if(host?.window&&!host.window.isDestroyed())try{report.ui=await host.window.webContents.executeJavaScript("({toast:document.querySelector('#toast')?.textContent,problems:document.querySelector('#problems-list')?.textContent,modal:document.querySelector('#modal-title')?.textContent})");}catch{}
 }
 finally{
  if(cfg.mode==='crash'&&report.status==='RUNNING')return;
  if(clipboardBackup){if(clipboardBackup.length)await clipboard.write(clipboardBackup);else clipboard.clear();}
  if(host?.window&&!host.window.isDestroyed()){
   try{await host.window.webContents.executeJavaScript('void(window.originalFetch&&(window.fetch=window.originalFetch))');host.window.close();await Promise.race([host.closed,delay(35000)]);}catch{}
  }
  fs.writeFileSync(path.join(cfg.out,'RESULT.json'),JSON.stringify(report,null,2)+'\n');app.exit(report.status==='PASS'?0:1);
 }
})().catch(error=>{fs.writeFileSync(path.join(cfg.out,'RESULT.json'),JSON.stringify({status:'FAIL',error:error.stack}));app.exit(1);});
