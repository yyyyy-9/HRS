'use strict';
const path=require('node:path');
const {chromium}=require(require.resolve('playwright-core',{paths:[
 process.env.HRS_BRIDGE_NODE_MODULES||path.resolve(__dirname,'..'),path.resolve(path.dirname(process.execPath),'../node_modules')
]}));
(async()=>{
 const chunks=[];for await(const part of process.stdin)chunks.push(part);
 const req=JSON.parse(Buffer.concat(chunks).toString('utf8'));
 const browser=await chromium.launch({executablePath:req.browser,headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:900},deviceScaleFactor:2});
  await page.goto(req.base+'/web/index.html?programmatic=1',{waitUntil:'load'});
  await page.waitForFunction(()=>window.ReportExportArchive);
  let result;
  if(req.operation==='tokens'){
   result=await page.evaluate(source=>marked.lexer(source),req.markdown);
  }else if(req.operation==='model'){
   if(!await page.evaluate(()=>!!window.ReportStudioProgrammatic))throw Error('Programmatic entry unavailable');
   await page.addScriptTag({path:path.join(__dirname,'browser_model.js')});
   result=await page.evaluate(async req=>{
    await ReportStudioProgrammatic.ready();
    await ReportTheme.apply(document,req.color_theme);
    return ReportBridgeModel.render(req);
   },req);
  }else if(req.operation==='serialize'){
   result=await page.evaluate(items=>items.map(item=>{
    if(item.type==='image-group')return ReportLayout.groupSnippet(item.data)+'\n';
    if(item.type==='gfm')return ReportPipeTables.stringify(item.data,{id:item.id,withCaption:!!item.data.caption})+'\n';
    if(item.type==='equation')return ReportEquations.snippet(item.tex,item.id,'\n',item.delimiter)+'\n';
    throw Error('Unknown source serializer');
   }),req.items);
  }else throw Error('Unknown browser operation');
  process.stdout.write(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(error=>{process.stderr.write(error.stack||String(error));process.exitCode=1;});
