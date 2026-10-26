/* Native-selected Word import. Bridge owns recognition; existing HRS modules
   own source serialization. The page never receives writable native paths. */
(function(root){
'use strict';
const headers={'X-HRS-Project-Action':'user-action'};
const element=(tag,text,cls)=>{const node=document.createElement(tag);if(text)node.textContent=text;if(cls)node.className=cls;return node;};
function serialize(items){
 return items.map(item=>{
  if(item.type==='image-group')return ReportLayout.groupSnippet(item.data)+'\n';
  if(item.type==='gfm')return ReportPipeTables.stringify(item.data,{id:item.id,withCaption:!!item.data.caption})+'\n';
  if(item.type==='equation')return ReportEquations.snippet(item.tex,item.id)+'\n';
  throw Error('Word 组件请求了不支持的序列化操作');
 });
}
async function configure({api,modal,context}){
 const post=(action)=>api('/api/word/'+action,'POST',context,headers);
 let options=await post('options'),picking=false,status,buttons=[];
 const sync=()=>{status.textContent=(options.available?'Word 组件已就绪。':'请选择当前匹配的 Word 组件。')+(options.formula_available?' 原生公式转换已就绪。':' 含原生公式时需配置 Pandoc。');};
 return modal({title:'导入 Word',kicker:'导入 · 新建 HRS 工程',note:'读取 .docx 的内容和可识别结构，原文件不变。',okText:'选择 Word 并读取…',
  body:outer=>{
   outer.append(element('p','将正文、可识别标题、表格、图片及受支持公式转为 report.md 和 assets/。原排版不原样保留；不能表达的结构会明确提示。','modal-help'));
   outer.append(element('p','先查看导入结果，再选择新工程目录。取消或失败不会替换当前文稿。自身导出的 Word 请保留同名 .hrs-bridge.json 来源映射。','modal-help'));
   const row=element('div',null,'word-export-actions');
   for(const [label,action,id] of [['选择 Word 组件…','pick-runtime','word-import-runtime'],['选择 Pandoc…','pick-formula','word-import-formula']]){
    const button=element('button',label,'btn btn-quiet');button.id=id;button.type='button';buttons.push(button);row.append(button);
    button.onclick=async()=>{
     if(picking)return;picking=true;buttons.forEach(b=>b.disabled=true);
     const controls=['modal-ok','modal-cancel','modal-close'].map(id=>document.getElementById(id));controls.forEach(b=>b.disabled=true);
     try{const reply=await post(action);if(!reply.cancelled)options=reply;sync();}
     catch(error){status.textContent=error.message;}
     finally{picking=false;buttons.forEach(b=>b.disabled=false);controls.forEach(b=>b.disabled=false);}
    };
   }
   outer.append(row);status=element('p',null,'word-export-status');status.id='word-import-runtime-state';status.setAttribute('role','status');outer.append(status);sync();
  },onOk:()=>{if(picking)return false;if(!options.available){status.textContent='请先选择匹配的 Word 基础组件，或使用完整便携版。';return false;}return true;}});
}
async function read({api,progress,cancelButton,onToken}){
 const post=(action,data={})=>api('/api/import/word/'+action,'POST',data,headers);
 const started=await post('start');if(started.cancelled)return null;
 const token=started.job_token;onToken(token);let cancelled=false;
 cancelButton.hidden=false;cancelButton.disabled=false;
 cancelButton.onclick=()=>{cancelled=true;cancelButton.disabled=true;progress.textContent='正在取消 Word 导入…';post('cancel',{job_token:token}).catch(()=>{});};
 try{
  const deadline=Date.now()+200000;
  while(!cancelled){
   if(Date.now()>deadline)throw Error('Word 导入等待超时，请核对组件与文档');
   const current=await post('step',{job_token:token});
   if(cancelled)return null;
   if(current.state==='ready')return {...current,job_token:token};
   if(current.state==='error')throw Error(current.error);
   if(current.state==='page'){
    progress.textContent='正在使用当前页面生成图表与公式源码…';
    const request=current.request;
    await post('step',{job_token:token,seq:request.seq,result:serialize(request.items)});
   }else{progress.textContent='正在读取 Word、识别结构与转换公式…';await new Promise(resolve=>setTimeout(resolve,150));}
  }
  return null;
 }catch(error){if(cancelled)return null;throw error;}
 finally{cancelButton.onclick=null;cancelButton.hidden=true;cancelButton.disabled=false;}
}
async function review({modal,result}){
 const receipt=result.receipt,unresolved=receipt.recognition?.unresolved||0;
 return modal({title:'核对 Word 导入结果',kicker:receipt.status==='NEEDS_REVIEW'?'导入 · 有待确认项':'导入 · 已完成',
  note:'确认后保存到新工程目录，再按原有保存提示决定是否切换；当前文稿保持。',okText:'保存为新工程…',
  body:outer=>{
   const summary=element('p',`${result.filename} · ${receipt.status==='NEEDS_REVIEW'?'已生成可编辑稿，待确认 '+unresolved+' 项':'结构转换完成'}。原文件保持不变。`,'modal-help');summary.id='word-import-summary';outer.append(summary);
   const details=[...(result.review||[]).map(item=>`${item.block}：${item.text}（${(item.evidence||[]).join('、')}）`),...(receipt.diagnostics||[]).map(item=>[item.block||item.line,item.code,item.message].filter(Boolean).join(' · '))];
   const host=element('div');host.id='word-import-diagnostics';
   const list=element('ul');for(const text of details.slice(0,100))list.append(element('li',text));host.append(list);
   if(!details.length)host.append(element('p','没有额外诊断。'));
   if(details.length>100)host.append(element('p',`共 ${details.length} 条，完整条目随工程保存到 word-recognition.json / word-import.json。`));
   outer.append(host,element('p','待确认文字按原桥接规则保留，不算已确认标题。导入诊断和来源摘要随新工程保存；本次不调用模型。','modal-help'));
  },onOk:()=>true});
}
root.ReportWordImport={configure,read,review};
})(window);
