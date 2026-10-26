/* HRS UI only. Source snapshots and compilation belong to the existing server,
   Bridge and WPS; this module does not interpret Markdown or Word numbering. */
(function(root){
'use strict';
const headers={'X-HRS-Project-Action':'user-action'};
const element=(tag,text,cls)=>{const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e;};
function badge(){return element('span','beta','beta-badge');}
async function open({api,modal,toast,getRequest,validate=async()=>{}}){
 document.querySelector('#menu-export').open=false;
 const context=getRequest();
 const post=(action,body={})=>api('/api/word/'+action,'POST',{document_id:context.document_id,draft_id:context.draft_id,template:context.template,...body},headers);
 let options=await post('options'),choice=options.template_choice,busy=false,picking=false;
 let templateField,filename,status,runState,formulaState,pickTemplate,pickRuntime,pickFormula,useDefault,setDefault,notesMode,keepEmphasis;
 const controls=()=>[pickTemplate,pickRuntime,pickFormula,useDefault,setDefault,notesMode,keepEmphasis,filename,document.querySelector('#modal-ok'),document.querySelector('#modal-cancel'),document.querySelector('#modal-close')];
 function sync(){
  templateField.value=options.template||'尚未配置默认母模板';
  runState.textContent=options.available?'基础 Word 导出已就绪':'基础 Word 组件缺失，请使用完整便携版或选择当前配套组件。';
  runState.dataset.ready=String(!!options.available);
  formulaState.textContent=options.formula_available?'原生公式转换已就绪。':'尚未配置；不含公式的报告可直接导出。';
  document.querySelector('#modal-ok').disabled=busy||picking;
 }
 async function pick(action){
  if(picking||busy)return;
  picking=true;controls().forEach(e=>e.disabled=true);status.textContent='请在本机选择窗口中完成选择…';
  try{
   const reply=await post(action);if(reply.cancelled){status.textContent='已取消选择，原设置保留。';return;}
   const previousTemplate=options.template;options={...options,...reply};
   if(action==='pick-template')choice=reply.template_token;
   else options.template=choice==='default'?reply.default_template:previousTemplate;
   status.textContent=action==='pick-template'?'已选母模板；导出时按现有模板契约校验。':action==='pick-formula'?'原生公式转换器已配置。':'运行环境已更新。';
  }catch(error){status.textContent=error.message;}
  finally{picking=false;controls().forEach(e=>e.disabled=false);sync();}
 }
 const result=await modal({title:'导出 Word',kicker:'导出 · 工程报告',wide:false,
  note:'Word 始终按工程规则输出；模板偏好独立于文稿配色和自由／工程模式。',okText:'生成 Word',
  body:outer=>{
   document.querySelector('#modal-title').classList.add('feature-label');document.querySelector('#modal-title').append(badge());
   const form=element('div',null,'word-export-form');outer.append(form);
   form.append(element('p','将当前文稿编译到母模板正文位置，保留已准备模板中的封面、目录域和页眉。','modal-help'));
   const templateLabel=element('label','Word 母模板');templateLabel.htmlFor='word-template';form.append(templateLabel);
   templateField=element('input');templateField.id='word-template';templateField.readOnly=true;templateField.className='table-caption-input';form.append(templateField);
   const row=element('div',null,'word-export-actions');
   pickTemplate=element('button','选择母模板…','btn btn-quiet');pickTemplate.type='button';pickTemplate.id='word-pick-template';pickTemplate.onclick=()=>pick('pick-template');
   useDefault=element('button','使用程序原始模板','btn btn-quiet');useDefault.type='button';useDefault.id='word-default-template';useDefault.onclick=()=>{choice='default';options.template=options.default_template;status.textContent='本次使用程序自带的原始母模板。';sync();};
   setDefault=element('button','设为默认模板','btn btn-quiet');setDefault.type='button';setDefault.id='word-set-default';
   setDefault.onclick=async()=>{
    if(busy||picking)return;picking=true;controls().forEach(e=>e.disabled=true);status.textContent='正在检查并保存默认模板…';
    try{const reply=await post('set-default-template',{template_token:choice});options={...options,...reply};choice=reply.template_token;status.textContent='默认模板已保管到软件数据目录；原文件移动后仍可使用，新工程将优先使用它。';}
    catch(error){status.textContent=error.message;}finally{picking=false;controls().forEach(e=>e.disabled=false);sync();}
   };
   row.append(pickTemplate,setDefault,useDefault);form.append(row);
   form.append(element('p','选择已经准备好的 .docx 母模板；普通带封面文档需先用模板样式工具准备正文位置。','modal-help'));
   const notesLabel=element('label','注释与参考文献');notesLabel.htmlFor='word-notes-mode';form.append(notesLabel);
   notesMode=element('select');notesMode.id='word-notes-mode';notesMode.className='table-caption-input';
   for(const [value,text] of [['footnotes','页底脚注 [1]（Word 原生脚注）'],['references','文末参考文献 [1]（进入目录，不占章号）']]){const option=element('option',text);option.value=value;notesMode.append(option);}
   notesMode.value=options.word_options?.notes_mode||'footnotes';form.append(notesMode);
   const emphasis=element('label',null,'word-emphasis-option');keepEmphasis=element('input');keepEmphasis.type='checkbox';keepEmphasis.id='word-keep-emphasis';keepEmphasis.checked=options.word_options?.preserve_emphasis===true;
   emphasis.append(keepEmphasis,document.createTextNode('保留正文 Markdown 加粗／斜体'));form.append(emphasis);
   form.append(element('p','默认清除正文的额外加粗、斜体；标题和题注继续使用母模板，公式中的数学粗体／斜体保留。摘要只加粗“摘要：”。','modal-help'));
   const nameLabel=element('label','文件名（自动附加时间，不覆盖已有文件）');nameLabel.htmlFor='word-filename';form.append(nameLabel);
   filename=element('input');filename.id='word-filename';filename.className='table-caption-input';filename.maxLength=60;filename.value='报告_Word';form.append(filename);
   form.append(element('p','输出到：'+(options.output_directory||'当前工程 output/'),'word-export-path'));
   const environment=element('div',null,'word-export-runtime');runState=element('span');runState.id='word-runtime-state';
   pickRuntime=element('button','更换组件…','btn btn-quiet');pickRuntime.id='word-pick-runtime';pickRuntime.type='button';pickRuntime.onclick=()=>pick('pick-runtime');
   environment.append(runState,pickRuntime);form.append(environment);
   const formula=element('details');formula.className='word-export-formula';formula.append(element('summary','公式支持（可选）'));
   const formulaRow=element('div',null,'word-export-runtime');formulaState=element('span');formulaState.id='word-formula-state';
   pickFormula=element('button','选择 Pandoc…','btn btn-quiet');pickFormula.id='word-pick-formula';pickFormula.type='button';pickFormula.onclick=()=>pick('pick-formula');
   formulaRow.append(formulaState,pickFormula);formula.append(formulaRow);form.append(formula);
   status=element('p','请先核对工程预览和文档检查；未通过工程检查时不会生成 Word。','word-export-status');status.id='word-export-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');form.append(status);
   // modal() resets its submit button after body construction.
   queueMicrotask(sync);
  },onOk:async()=>{
   if(busy||picking)return false;
   if(!options.available){status.textContent='请先选择当前 Word 基础组件，或使用包含该组件的完整便携版。';return false;}
   busy=true;controls().forEach(e=>e.disabled=true);status.textContent='正在检查工程输出要求…';
   let jobToken=null;
   try{
    const request={...getRequest(),word_options:{notes_mode:notesMode.value,preserve_emphasis:keepEmphasis.checked}};
    if(request.document_id!==context.document_id)throw Error('工程已切换，请重新打开 Word 导出');
    const validation=await validate();
    if(!validation?.preflight?.complete)throw Error('请先完成当前文稿的工程预检');
    const errors=validation.diagnostics.filter(d=>d.severity==='error');
    if(errors.length)throw Error(errors[0].message);
    if(validation.diagnostics.some(d=>d.code==='HEADING_SOURCE_PREFIX')){
     const accepted=await ReportDialogs.confirm('标题中有手工章号，Word 会按模板自动编号。请核对是否会重复；接受本次源稿的提醒并继续吗？',{title:'核对手工章号',okText:'已核对，继续导出'});
     if(!accepted){status.textContent='已取消导出，可返回源码核对。';return false;}
     request.accept_numbered_headings=true;
    }
    const current=getRequest();
    if(current.markdown!==request.markdown||current.document_id!==request.document_id||current.revision!==request.revision)throw Error('文稿已变化，请重新生成');
    status.textContent='正在准备模板与源稿快照…';
    const prepared=await post('prepare',{...request,template_token:choice});jobToken=prepared.job_token;
    status.textContent='正在使用当前页面解析文稿与图形…';
    const model=await ReportBridgeModel.render(prepared.model_request);
    const latest=getRequest();
    if(latest.markdown!==request.markdown||latest.document_id!==request.document_id||latest.revision!==request.revision)throw Error('文稿已变化，请重新生成');
    status.textContent='正在生成 Word，请稍候…';
    return await post('export',{job_token:jobToken,model,filename:filename.value.trim()});
   }catch(error){status.textContent='导出未完成：'+error.message;return false;}
   finally{
    if(jobToken)try{await post('discard',{job_token:jobToken});}catch{}
    busy=false;controls().forEach(e=>e.disabled=false);sync();
   }
  }});
 document.querySelector('#modal-title').classList.remove('feature-label');
 if(!result)return;
  toast(result.preference_warning||'Word 已生成：'+result.filename,{label:'打开所在文件夹',run:()=>post('open',{result_token:result.result_token,folder:true})});
 await modal({title:'Word 已生成',kicker:'导出 · 工程报告',note:'目录是 Word 原生域；打开后可在 WPS／Word 中更新目录。',okText:'完成',cancelText:'关闭',
  body:outer=>{
   document.querySelector('#modal-title').classList.add('feature-label');document.querySelector('#modal-title').append(badge());
   outer.append(element('p',result.path,'word-export-path'));
   outer.append(element('p',result.working_copy?'已导出当前工作快照，工程 report.md 保持不变。':'已导出当前文稿，工程源文件保持不变。','modal-help'));
   if(result.preference_warning)outer.append(element('p',result.preference_warning,'modal-help'));
   const row=element('div',null,'word-export-actions');
   for(const [text,folder] of [['打开 Word',false],['打开输出文件夹',true]]){
    const button=element('button',text,'btn btn-quiet');button.type='button';button.onclick=async()=>{try{await post('open',{result_token:result.result_token,folder});}catch(error){toast(error.message);}};row.append(button);
   }
   outer.append(row);
  },onOk:()=>true});
 document.querySelector('#modal-title').classList.remove('feature-label');
}
root.ReportWordExport={open,badge};
})(window);
