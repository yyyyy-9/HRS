/* Offline editor orchestration; product/release values belong to their catalogs. */
(() => {
'use strict';
const $=x=>document.getElementById(x);
const RENDER_CONTROLS=[['show-object-numbers','show_object_numbers'],['show-heading-numbers','show_heading_numbers'],['show-equation-numbers','show_equation_numbers'],['preserve-blank-lines','preserve_blank_lines']];
// Check bundled scripts before touching any of them, so a missing file shows
// a readable message instead of a silent ReferenceError on "正在加载".
const REQUIRED_SCRIPTS=['marked','Flow','ReportClone','ReportTableContent','ReportTables','ReportPipeTables','ReportTableEditor','ReportDialogs','ReportLayout','ReportListStyles','ReportEquations','SourceEditor','ReportSourceProjection','SourceBlocks','SourceActions','ReportObjectClipboard','ReportRichClipboard','SourceMap','ScrollFollow','ReportNotes','ReportLinks','ReportWordExport','ReportWorkspace','ReportBridgeModel'];
REQUIRED_SCRIPTS.push('ReportDocumentSearch','ReportSettings','ReportProfile','ReportTheme','ReportNotebook','ReportPreviewImages','ReportPreflight','ReportOperations','ReportPreviewCommit');
const missingScripts=REQUIRED_SCRIPTS.filter(name=>typeof window[name]==='undefined');
if(missingScripts.length){
 const indicator=$('save-indicator');if(indicator){indicator.className='status error';indicator.textContent='本地静态依赖缺失';}
 const note=$('toast');if(note){note.textContent='程序文件不完整，缺少：'+missingScripts.join('、')+'。请重新解压完整便携包。';note.classList.add('show');}
 return;
}
const cloneReport=ReportClone.clone;
const editor=window.SourceEditor&&window.SourceBlocks?SourceEditor.attach($('markdown'),{onEdit:editSourceObject,onLocate:position=>locateFromSource(position).catch(e=>toast(e.message))}):$('markdown'), preview=$('preview-content'), indicator=$('save-indicator');
const sourceProjection=ReportSourceProjection.attach(editor,{onBoundary:toast});
const escapeHTML=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={projectPath:null,externalProject:false,md:'',savedMd:'',revision:null,documentId:'new',template:'engineering',theme:'engineering',view:'split',saving:false,dirty:false,rendering:0,renderErrors:[],selectedBlock:null,visualFocused:null,visualPending:false,draftId:null,draftSeq:0,draftQueue:Promise.resolve(),draftError:false,draftSnapshot:null,exiting:false,exitReady:false,session:0};
state.renderProfile=ReportProfile.normalize();state.renderOptions=ReportProfile.normalizeOptions();
state.colorTheme=ReportTheme.normalize();
state.hasNumberPreference=false;
const operations=ReportOperations.create({editor,onEditing:locked=>{$('app').inert=locked;$('app').toggleAttribute('data-operation-locked',locked);setPreviewEditingEnabled(!locked);}});
const urlColorTheme=ReportTheme.fromURL(location.search);
let acceptedHeadingSnapshot=null,activeHeadingAcceptance=false;
function syncRenderControls(){document.body.dataset.renderProfile=state.renderProfile;const free=state.renderProfile==='free';$('number-display-options').hidden=false;for(const [control,option] of RENDER_CONTROLS){const field=$(control);field.checked=(!free&&['show_heading_numbers','show_object_numbers'].includes(option))||state.renderOptions[option];operations.setDisabled(field,!free&&['show_heading_numbers','show_object_numbers'].includes(option));}}
async function setColorTheme(value){state.colorTheme=await ReportTheme.apply(document,value);$('color-theme').value=state.colorTheme;}
let debounceDraft=null,debounceRender=null,toastTimer=null,mathRecords=new Map();
let exportPreferences={quality:'standard',sourceMode:'recompilable',includePdfOriginals:false},lastExportStats=null,lastExportRequest=null;
let positionMap=null,sourceMapCache=null,pipeTableIndex=[],navigationTimer=null,checks=null,checkSequence=0,referenceRecords=new WeakMap(),scrollFollow=null;
let documentSearch=null,captionEditor=null,previewImages=null,activeLinks=null,presentationWait=Promise.resolve();
const displayChanges=[];
const portableWindow=window.PortableWindow?.attach();
const history={items:[],index:0,lastKind:null,lastAt:0,limit:120};
ReportLayout.installMarked(marked);
ReportListStyles.installMarked(marked);
ReportEquations.installMarked(marked);
ReportNotes.installMarked(marked);
ReportNotes.bindNavigation(preview);
ReportLinks.attach(document.body,{open:url=>api('/api/external/open','POST',{url},{'X-HRS-External-Link':'user-action'}),onError:toast});
const objectClipboard=ReportObjectClipboard.attach(editor,{
 request:(path,data)=>api(path,'POST',data,{'X-Report-Studio-Clipboard':'user-action'}),
 context:()=>({session:state.session,markdown:state.md,document_id:state.documentId,draft_id:state.draftId,start:editor.selectionStart,end:editor.selectionEnd}),
 commit:(from,to,text,kind)=>{if(state.saving)return;editor.setRangeText(text,from,to,'end');changed(editor.value,kind,true);},
 prepareRich:(html,plain,nativeReply=null)=>ReportRichClipboard.prepare(html,plain,{
  convertMath:formulas=>api('/api/clipboard/math','POST',{formulas},{'X-Report-Studio-Clipboard':'user-action'}).then(r=>r.formulas),
  native:text=>api('/api/clipboard/document','POST',{text},{'X-Report-Studio-Clipboard':'user-action'}),
  figure:path=>{const object=figureDefault('image',path);object.caption='';return object;},figureSnippet,
  table:rows=>({...tableDefault(rows.length,rows[0].length),rows}),tableSnippet,nativeReply
 }),
 chooseImage:async url=>{
  let field;const file=await modal({title:'选择图片来源',kicker:'本地 Markdown 图片',note:'无法确定 '+url+' 的来源。请选择这张图片；程序不会猜测其他目录。',body:outer=>{field=document.createElement('input');field.type='file';field.accept='.png,.jpg,.jpeg,.gif,.webp,.svg';outer.append(field);},onOk:()=>{if(!field.files[0])throw Error('请选择对应图片');return field.files[0];},okText:'导入所选图片'});
  return file?await blobToB64(file):null;
 },onError:toast
});
const sourceActions=SourceActions.attach(editor,{copy:objectClipboard.copy,onError:toast,replace:(from,to,text,kind)=>{
 if(state.saving)return;
 editor.setRangeText(text,from,to,'end');changed(editor.value,kind,true);
}});
function freshID(){const a=new Uint8Array(16);crypto.getRandomValues(a);return [...a].map(v=>v.toString(16).padStart(2,'0')).join('');}
function toast(msg,action=null){
 const el=$('toast');clearTimeout(toastTimer);el.textContent=msg;el.classList.toggle('has-action',!!action);
 const arm=()=>{clearTimeout(toastTimer);toastTimer=setTimeout(clearToast,action?8000:4200);};
 if(action){
  const button=document.createElement('button');button.type='button';button.className='toast-action';button.textContent=action.label;
  button.onclick=async()=>{clearTimeout(toastTimer);button.disabled=true;try{await action.run();}catch(error){toast('无法打开文件夹：'+error.message);}finally{if(button.isConnected){button.disabled=false;arm();}}};
  el.append(document.createTextNode(' · '),button);
 }
 el.onmouseenter=el.onfocusin=()=>clearTimeout(toastTimer);
 el.onmouseleave=()=>{if(!el.contains(document.activeElement))arm();};
 el.onfocusout=()=>{if(!el.matches(':hover'))arm();};
 el.classList.add('show');arm();
}
function exportToast(message,result){
 toast(message,{label:'打开所在文件夹',run:()=>api('/api/export/open-folder','POST',{result_token:result.result_token},{'X-HRS-Project-Action':'user-action'})});
}
function clearToast(){clearTimeout(toastTimer);toastTimer=null;const el=$('toast');el.classList.remove('show','has-action');el.textContent='';}
function status(type,msg){indicator.className='status '+type;indicator.innerHTML='<i></i> '+escapeHTML(msg);}
const api=ReportOperations.request;
function persistPresentation(changes,onApplied=async()=>{}){
 const session=state.session;
 const release=operations.acquire({nodes:['render-profile','color-theme',...RENDER_CONTROLS.map(([control])=>control)].map($)});
 const task=(async()=>{try{
  await api('/api/render-profile','POST',{document_id:state.documentId,template:state.template,revision:state.revision,
   render_profile:state.renderProfile,render_options:state.renderOptions,...changes});
  if(session===state.session)await onApplied();
  return session===state.session;
 }finally{release();syncRenderControls();}})();
 presentationWait=task.catch(()=>{});return task;
}
function updateDirty(){state.dirty=state.md!==state.savedMd;if(state.draftError){status('error','草稿备份失败 · 请重试或手动保存');return;}if(state.exiting){status('','正在备份草稿并退出…');return;}if(state.saving){status('','正在保存正式文档…');return;}if(state.dirty){status('draft',state.draftSnapshot?.markdown===state.md?'未正式保存 · 草稿已备份':'未正式保存 · 草稿备份中…');return;}status('saved',state.documentId==='new'?'新文档 · 尚未创建正式文件':'已保存');}
function snapshot(){return {md:state.md,start:editor.selectionStart,end:editor.selectionEnd,top:editor.scrollTop,left:editor.scrollLeft};}
function updateHistoryButtons(){operations.setDisabled($('btn-undo'),history.index<=0);operations.setDisabled($('btn-redo'),history.index>=history.items.length-1);}
function resetHistory(){history.items=[snapshot()];history.index=0;history.lastKind=null;history.lastAt=0;updateHistoryButtons();}
function recordHistory(kind){
 const value=snapshot(),now=Date.now();
 if(history.index<history.items.length-1)history.items.splice(history.index+1);
 const merge=(kind==='typing'||kind.startsWith('visual-typing:'))&&history.lastKind===kind&&now-history.lastAt<550&&history.index>0;
 if(merge)history.items[history.index]=value;
 else{history.items.push(value);history.index++;if(history.items.length>history.limit){history.items.shift();history.index--;}}
 history.lastKind=kind;history.lastAt=now;updateHistoryButtons();
}
function restoreHistory(entry){
 state.md=entry.md;editor.value=entry.md;
 editor.setSelectionRange(Math.min(entry.start,entry.md.length),Math.min(entry.end,entry.md.length));
 editor.scrollTop=entry.top;editor.scrollLeft=entry.left;
 updateDirty();updateStats();scheduleRender();scheduleDraft();
}
function undo(){if(state.saving)return;if(state.visualFocused)commitFocusedVisual();if(history.index<=0)return;history.index--;history.lastKind=null;restoreHistory(history.items[history.index]);updateHistoryButtons();}
function redo(){if(state.saving)return;if(state.visualFocused)commitFocusedVisual();if(history.index>=history.items.length-1)return;history.index++;history.lastKind=null;restoreHistory(history.items[history.index]);updateHistoryButtons();}
function clearTimers(){clearTimeout(debounceDraft);clearTimeout(debounceRender);}
function updateStats(){$('source-stats').textContent=state.md.length.toLocaleString()+' 字符 · '+state.md.split('\n').length+' 行';}
function scheduleRender(){clearTimeout(debounceRender);debounceRender=setTimeout(()=>{render().catch(e=>toast('预览失败：'+e.message));},200);}
function queueDraft(){
 if(!state.dirty||state.saving)return state.draftQueue;
 const args={draft_id:state.draftId,document_id:state.documentId,template:state.template,
   base_revision:state.revision,seq:++state.draftSeq,markdown:state.md,render_profile:state.renderProfile,render_options:state.renderOptions,color_theme:state.colorTheme};
 const session=state.session;
 state.draftQueue=state.draftQueue.catch(()=>{}).then(()=>api('/api/draft','POST',args))
  .then(reply=>{if(session===state.session){
   if(reply.accepted&&reply.seq===args.seq&&args.draft_id===state.draftId)state.draftSnapshot={...args,markdown_sha256:reply.markdown_sha256};
   state.draftError=false;updateDirty();
  }})
  .catch(e=>{if(session===state.session){state.draftError=true;updateDirty();toast('恢复草稿保存失败：'+e.message);}});
 return state.draftQueue;
}
function scheduleDraft(){clearTimeout(debounceDraft);if(state.dirty)debounceDraft=setTimeout(()=>queueDraft(),1150);}
async function finishDraftWrites(){clearTimeout(debounceDraft);if(state.dirty)await queueDraft();await state.draftQueue;if(state.draftError)throw Error('草稿备份失败；可以重试手动保存，但请勿在修复前直接关闭页面');}
async function prepareWindowExit(){
 await presentationWait;
 if(state.saving||operations.busy){toast('请等待当前操作完成后再退出');return false;}
 commitSource();commitFocusedVisual();
 const snapshot=state.md,session=state.session,flush=finishDraftWrites();
 const release=operations.acquire({nodes:document.querySelectorAll('button'),editing:true});
 state.exiting=true;state.saving=true;updateDirty();
 try{
  await flush;
  if(session!==state.session||snapshot!==state.md||state.dirty&&state.draftSnapshot?.markdown!==snapshot)throw Error('尚未确认当前草稿快照，请重试或正式保存');
  state.exitReady=true;
  return true;
 }catch(error){toast('草稿未确认，窗口已保留：'+error.message);return false;}
 finally{
  if(!state.exitReady){state.exiting=false;state.saving=false;release();updateHistoryButtons();updateDirty();}
 }
}
async function saveDraftAndExit(){
 if(window.HRSHost){window.HRSHost.requestClose();return;}
 if(await prepareWindowExit())window.location.replace('about:blank');
}
function changed(md,kind='command',fromEditor=false){
 if(md===state.md)return;
 displayChanges.push({before:state.md,after:md});if(displayChanges.length>120)displayChanges.shift();
 state.md=md;if(!fromEditor)editor.value=md;
 if(fromEditor&&editor.hasFocus()&&topicFocus)pendingTopicPosition=editor.selectionStart;
 documentSearch?.refresh();
 invalidateChecks();clearPreviewHighlight();
 scrollFollow?.suspend();
 recordHistory(kind);state.draftError=false;updateDirty();updateStats();scheduleRender();scheduleDraft();
}
async function load(documentId='new',template='engineering',{recover=true,draftId=null}={}){
 const release=operations.acquire({nodes:document.querySelectorAll('#app button,#app input,#app select'),editing:true});
 scrollFollow?.suspend();
 clearTimers();
 status('','正在载入文档…');
 clearToast();checks=null;checkSequence++;sourceMapCache=null;const session=++state.session;
 $('problems-panel').hidden=true;$('problem-list').replaceChildren();$('problems-summary').textContent='';
 $('bottom-left').textContent='实时预览 · 草稿自动恢复 · Ctrl+S 正式保存';$('bottom-left').title='';
 $('bottom-right').textContent='离线渲染 · 无 CDN';
 try{
  const data=await api('/api/doc?document_id='+encodeURIComponent(documentId)+'&template='+encodeURIComponent(template));
  if(session!==state.session)return;
  clearDocumentRenderCaches();sourceProjection.set(null);
  acceptedHeadingSnapshot=null;state.md=data.markdown;state.savedMd=data.markdown;state.revision=data.revision;state.documentId=data.document_id;
  state.renderProfile=ReportProfile.normalize(data.render_profile);state.renderOptions=ReportProfile.normalizeOptions(data.render_options);$("render-profile").value=state.renderProfile;syncRenderControls();
  state.hasNumberPreference=data.document_id!=='new';state.reportWorkspace=data.report_workspace||null;syncReportWorkspace();
  await setColorTheme(urlColorTheme||data.color_theme);
   state.template=data.template;state.theme=data.theme;state.projectPath=data.project_path||null;state.externalProject=!!data.external_project;state.dirty=false;state.saving=false;state.draftError=false;
  state.selectedBlock=null;state.visualFocused=null;state.visualPending=false;state.draftId=freshID();state.draftSeq=0;state.draftQueue=Promise.resolve();state.draftSnapshot=null;state.exitReady=false;
  checks=null;checkSequence++;$('problems-panel').hidden=true;clearPreviewHighlight();
  editor.value=state.md;editor.resetObjects();editor.setSelectionRange(state.md.length);editor.scrollTop=0;$('project-label').textContent=data.project;
  document.body.dataset.reportTheme=data.theme;
  resetHistory();updateDirty();await render();await refreshRecent();
  if(recover&&documentId!=='new')await recoverDocumentDraft(documentId,{draftId,session});
 }catch(e){status('error','无法加载');toast(e.message);throw e;}finally{release();}
}
async function refreshRecent(){
 const host=$('recent-list');
 try{
  const data=await api('/api/recent');host.replaceChildren();
  if(!data.documents.length){host.textContent='暂无已保存的文档';host.className='recent-list muted';return;}
  host.className='recent-list';
  for(const item of data.documents.slice(0,9)){
   const b=document.createElement('button');b.type='button';b.className='recent-doc';
   if(item.id===state.documentId)b.classList.add('active');
   const title=document.createElement('strong');title.textContent=(item.report_workspace?'临时稿 · ':'')+item.title;
   const small=document.createElement('small');const dt=new Date(item.updated);
   small.textContent=isNaN(dt.valueOf())?'已保存':dt.toLocaleDateString('zh-CN')+' '+dt.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});
   b.append(title,small);b.addEventListener('click',()=>openRecent(item.id));host.append(b);
  }
 }catch(e){host.textContent='最近打开加载失败';}
}
function commitFocusedVisual(){captionEditor?.commit();if(!state.visualFocused)return;const b=state.visualFocused;state.visualFocused=null;state.visualPending=false;commitVisual(b);if(state.visualTarget)state.visualTarget.contentEditable='false';state.visualTarget=null;}
function commitSource(){if(!state.saving&&editor.value!==state.md)changed(editor.value,'typing',true);}
async function discardDraft(){
 clearTimeout(debounceDraft);await state.draftQueue;
 await api('/api/draft-discard','POST',{draft_id:state.draftId});
 state.dirty=false;state.md=state.savedMd;state.draftError=false;state.draftSnapshot=null;
}
async function askLeave(){
 commitFocusedVisual();if(!state.dirty)return true;
 const decision=await modal({title:'有未保存的修改',kicker:'未保存 · 正式文件尚未更新',
  note:'“不保存”仅丢弃此文档未提交的编辑与暂存图片，不修改磁盘上的正式报告。',
  okText:'保存并继续',extraText:'不保存',cancelText:'取消',
  body:outer=>{const p=document.createElement('p');p.textContent='当前内容已实时预览，并可能已有后台恢复草稿，但尚未正式保存。你想怎么处理？';outer.append(p);},
  onOk:()=> 'save'});
 if(decision==='save'){
  try{await save(true);return true;}catch(e){toast('无法切换：'+e.message);return false;}
 }
 if(decision==='discard'){
  try{await discardDraft();return true;}catch(e){toast('丢弃失败：'+e.message);return false;}
 }
 return false;
}
async function openRecent(id){
 if(id===state.documentId)return;
 try{if(!await askLeave())return;await load(id);}catch(e){toast('切换中止：'+e.message);}
}
async function newDocument(){
 let template='engineering';
 const chosen=await modal({title:'新建报告',kicker:'新建 · 从模板创建',note:'新文档不会覆盖旧报告；只在手动保存后进入“最近打开”。',body:outer=>{
  const holder=document.createElement('div');holder.className='template-grid';outer.append(holder);
  const items=[['engineering','工程技术报告','标准技术章节与蓝色排版'],['academic','论文与研究笔记','论文结构与纸质排版'],['brief','项目说明 / 会议纪要','简洁紧凑的工作记录'],['blank','空白文档','仅有标题，自由编写']];
  items.forEach(([id,name,detail],i)=>{
   const label=document.createElement('label');label.className='template-option';
   const radio=document.createElement('input');radio.type='radio';radio.name='new-template';radio.value=id;radio.checked=i===0;
   radio.addEventListener('change',()=>{template=id;});
   const info=document.createElement('span');const title=document.createElement('strong');title.textContent=name;
   const sub=document.createElement('small');sub.textContent=detail;info.append(title,sub);label.append(radio,info);holder.append(label);
  });
 },onOk:()=>template});
 if(!chosen)return;
 try{if(!await askLeave())return;await load('new',chosen);toast('新文档已准备好；编辑后按 Ctrl+S 才正式保存');}
 catch(e){toast('新建失败：'+e.message);}
}
function projectFolderSuggestion(){
 const head=state.md.match(/^#\s+(.+?)(?:\r?\n|$)/m);
 let value=(head?.[1]||'未命名工程').replace(/[<>:\"/\\|?*\u0000-\u001f]/g,'_').trim().replace(/[. ]+$/,'').slice(0,60);
 return value||'未命名工程';
}
async function askProjectFolder(action='create',documentId=state.documentId){
 let field;
 const chosen=await modal({title:action==='create'?'首次正式保存 · 建立文档工程':'迁移项目到独立目录',
  kicker:'工程目录 · 使用 Windows 文件夹选择器',
  note:'只复制或新建用户指定的项目目录；旧项目与 data/ 恢复文件不会自动删除。',
  okText:'选择项目的父目录',body:outer=>{
   const detail=document.createElement('p');detail.className='modal-help';
   detail.textContent='选择保存工程的父目录，软件会在其中新建下面命名的项目文件夹（包含 report.md、assets/、output/）。';outer.append(detail);
   const label=document.createElement('label');label.className='modal-help';label.textContent='项目文件夹名称（不要输入完整路径）';outer.append(label);
   field=document.createElement('input');field.className='table-caption-input';field.maxLength=70;field.value=projectFolderSuggestion();field.setAttribute('aria-label','项目文件夹名称');outer.append(field);
  },onOk:async()=>{
   const name=field.value.trim();if(!name)throw Error('请输入工程文件夹名称');
   if(/[\\/:]/.test(name))throw Error('此处只能填写项目文件夹名称（例如：未命名技术报告），不能填写 D:\\GAME\\未命名技术报告；请在 Windows 文件夹选择器中选父目录 D:\\GAME。');
   const result=await api('/api/project/pick','POST',{document_id:documentId,action,project_name:name},
    {'X-HRS-Project-Action':'user-action'});
   if(!await ReportDialogs.confirm('工程将保存到：\n'+result.target_path+'\n\n不会覆盖任何已有目录。',{title:'确认工程位置',okText:'确认位置'}))return false;
   return result;
  }});
 return chosen&&typeof chosen==='object'?chosen:null;
}
async function migrateProject(){
 if(state.documentId==='new')return toast('请先正式保存新项目');
 const before=state.documentId,revision=state.revision;
 const target=await askProjectFolder('migrate');if(!target)return null;
 if(before!==state.documentId||revision!==state.revision)throw Error('文稿已切换，请重新迁移');
 const reply=await api('/api/project/migrate','POST',{document_id:before,revision,selection_token:target.selection_token});
 state.projectPath=reply.project_path;state.externalProject=true;
 toast('项目已迁移；旧项目保留为备份，输出目录在：'+reply.project_path+'/output');
 await refreshRecent();return reply;
}
const reportOriginViews=new Map();let workspaceBusy=false;
async function runWorkspaceOperation(action){
 if(workspaceBusy)throw Error('工作页正在切换，请稍候');
 workspaceBusy=true;const release=operations.acquire({nodes:document.querySelectorAll('#app button,#app input,#app select'),editing:true});
 $('workspace-operation').hidden=false;$('workspace-operation-text').textContent='正在切换工作页，请稍候…';
 try{return await action();}
 finally{workspaceBusy=false;$('workspace-operation').hidden=true;$('workspace-operation-cancel').hidden=true;release();updateHistoryButtons();}
}
function syncReportWorkspace(){
 const info=state.reportWorkspace;$('report-workspace-bar').hidden=!info;
 $('report-workspace-origin').textContent=info?'来源：'+info.title+' · 默认只保存临时稿，可显式同步回源稿':'';
 operations.setDisabled($('btn-workspace-sync'),!info?.sync_available);
 $('btn-workspace-sync').title=info?.sync_available?'查看修改差异后同步；来源变化时拒绝覆盖':'此稿没有已保存来源范围；请先保存源稿，再重新准备临时稿';
}
async function syncReportOrigin(){
 await presentationWait;commitSource();commitFocusedVisual();await finishDraftWrites();
 const info=state.reportWorkspace;if(!info?.sync_available)throw Error('此稿没有可同步的已保存来源范围');
 const markdown=state.md,session=state.session,model=documentModel(markdown);
 const request={...exportRequest(markdown),edits:ReportNotebook.syncEdits(markdown,model.map,info.sync)};
 const plan=await api('/api/report-workspace','POST',{...request,action:'sync-plan'},{'X-HRS-Project-Action':'user-action'});
 if(!plan.changed)return toast('本稿与来源范围没有内容差异');
 const accepted=await modal({title:'同步回源稿',kicker:'显式提交 · 原稿保留备份',wide:true,
  note:'只修改已确认的来源正文范围及共享定义。同步新增附件，保留其他专题；来源、临时稿或附件变化时拒绝提交。',okText:'确认同步源文件',
  body:outer=>{const diff=document.createElement('pre');diff.className='sync-diff';diff.textContent=plan.diff;outer.append(diff);},onOk:()=>true});
 if(!accepted)return;
 if(state.session!==session||state.md!==markdown)throw Error('查看差异期间临时稿已变化，请重新同步');
 await runWorkspaceOperation(async()=>{
  const reply=await api('/api/report-workspace','POST',{...request,action:'sync-apply',plan_id:plan.plan_id,plan_sha256:plan.plan_sha256},{'X-HRS-Project-Action':'user-action'});
  state.reportWorkspace=reply.report_workspace;reportOriginViews.delete(state.documentId);syncReportWorkspace();
  toast('已同步源文件；原稿已备份，临时稿仍保留');
 });
}
async function resumeReportWorkspace(id){
 await load(id);
 await render();await validateCurrent();
}
async function prepareReportWorkspace({force=false}={}){
 await presentationWait;if(state.saving)return toast('请等待当前保存完成');
 commitSource();commitFocusedVisual();
 if(state.reportWorkspace){
  await persistPresentation({render_profile:'engineering'},async()=>{state.renderProfile='engineering';$('render-profile').value='engineering';syncRenderControls();await render();});
  await validateCurrent();return toast('已显示工程效果，请检查后点击“导出 Word”');
 }
 const model=documentModel(state.md),snapshot=state.md,session=state.session,context=exportRequest(snapshot);
 if(!force&&model.map.blocks.filter(r=>r.type==='heading'&&r.token.depth===1).length<=1){
  await persistPresentation({render_profile:'engineering'},async()=>{state.renderProfile='engineering';$('render-profile').value='engineering';syncRenderControls();invalidateChecks();await switchView('split');await render();await queueDraft();});
  await validateCurrent();return toast('已切换工程模式，请核对预览和检查后再导出 Word；未创建临时稿');
 }
 const sourceSha256=await ReportExportArchive.hash(new TextEncoder().encode(snapshot));
 const listMore=(offset=0,all=false)=>api('/api/report-workspace','POST',{...context,action:'list',source_sha256:sourceSha256,offset,include_archived:all,include_trash:all},{'X-HRS-Project-Action':'user-action'});
 const listed=await listMore();
 const choice=await ReportWorkspace.choose({modal,topics:model.notebook.topics,selected:currentTopic(model)?.key,
  reports:listed.reports,total:listed.total,nextOffset:listed.next_offset,listMore,
  manage:(report,action)=>api('/api/report-workspace','POST',{...context,action,target_document_id:report.document_id,target_revision:report.revision},{'X-HRS-Project-Action':'user-action'})});
 if(!choice)return;
 if(state.md!==snapshot||state.session!==session)throw Error('选择期间文稿已变化，请重新准备');
 await finishDraftWrites();
 if(choice.startsWith('resume:'))return runWorkspaceOperation(()=>resumeReportWorkspace(choice.slice(7)));
 return runWorkspaceOperation(async()=>{
 const key=choice.startsWith('topic:')?choice.slice(6):null;
 const extracted=key?model.notebook.extract(key,{forEditing:true}):{markdown:snapshot,topic:{title:projectFolderSuggestion()},sync:{start:0,end:snapshot.length,dependencies:[]}};
 const originView={topic:currentTopic(model)?.key,start:editor.selectionStart,end:editor.selectionEnd,sourceTop:editor.scrollTop,previewTop:preview.closest('.page-scroll').scrollTop,view:state.view};
 const created=await ReportWorkspace.createJob({full_markdown:snapshot,
  source_sha256:sourceSha256,markdown:extracted.markdown,title:extracted.topic.title,color_theme:state.colorTheme,sync:extracted.sync},context,
  {progress:$('workspace-operation-text'),cancelButton:$('workspace-operation-cancel')});
 if(state.md!==snapshot||state.session!==session){await refreshRecent();throw Error('提取期间原稿已变化；已生成的快照可从最近打开继续，当前编辑保留');}
 reportOriginViews.set(created.document_id,originView);if(reportOriginViews.size>30)reportOriginViews.delete(reportOriginViews.keys().next().value);
 await load(created.document_id);await switchView('split');
 preview.closest('.page-scroll').scrollTop=0;editor.scrollTop=0;
 await validateCurrent();toast('已进入临时工程页：先核对预览和检查，再导出 Word；原台账未改动');
 });
}
async function returnToReportOrigin(){return runWorkspaceOperation(returnToReportOriginCurrent);}
async function returnToReportOriginCurrent(){
 const info=state.reportWorkspace;if(!info)return;
 commitSource();commitFocusedVisual();await finishDraftWrites();
 const view=reportOriginViews.get(state.documentId);
 await load(info.origin_document_id,info.origin_template,{draftId:info.origin_draft_id});
 if(view&&await ReportExportArchive.hash(new TextEncoder().encode(state.md))===info.source_sha256){
  const model=documentModel(state.md);focusTopic(model.notebook.topics.find(t=>t.key===view.topic)||null,model);
  await switchView(view.view);await render();editor.setSelectionRange(view.start,view.end);editor.scrollTop=view.sourceTop;preview.closest('.page-scroll').scrollTop=view.previewTop;
 }
 toast('已返回原台账；临时稿的修改已保留，可从 Word 准备窗口继续');
}
async function saveReportIndependent(){
 await presentationWait;commitSource();commitFocusedVisual();await finishDraftWrites();
 const session=state.session,snapshot=state.md,selection=await askProjectFolder('create','new');
 if(!selection)return;
 if(session!==state.session||snapshot!==state.md)throw Error('选择期间文稿已变化，请重新保存');
 await runWorkspaceOperation(async()=>{
  normalizeLocalImageObjects();await finishDraftWrites();const markdown=state.md;
  const reply=await api('/api/report-workspace','POST',{...exportRequest(markdown),action:'save-independent',selection_token:selection.selection_token,
   render_options:state.renderOptions,color_theme:state.colorTheme},{'X-HRS-Project-Action':'user-action'});
  await load(reply.document_id);toast('已保存为独立工程：'+reply.project_path+'；原台账和临时稿保留');
 });
}
async function manageCurrentReport(action){
 commitSource();commitFocusedVisual();await finishDraftWrites();
 const target=state.documentId,revision=state.revision,info=state.reportWorkspace;
 if(!info)return;
 await runWorkspaceOperation(async()=>{
  // Preserve the current view/draft first. A failed switch cannot hide the
  // active report or put the user's current draft out of reach.
  await returnToReportOriginCurrent();
  await api('/api/report-workspace','POST',{...exportRequest(state.md),action,target_document_id:target,target_revision:revision},
    {'X-HRS-Project-Action':'user-action'});
  await refreshRecent();toast(action==='trash'?'临时稿已移入回收站；可在 Word 准备窗口恢复':'临时稿已归档；可在 Word 准备窗口查看');
 });
}
async function ensureProjectForExport(){
 await presentationWait;
 if(state.reportWorkspace)return true;
 if(state.documentId==='new'){
  if(!await ReportDialogs.confirm('首次导出需要先创建独立工程并正式保存报告。现在选择工程目录吗？',{title:'先建立工程',okText:'选择工程目录'}))return false;
  await save(true);
 }
 if(!state.externalProject){
  if(!await ReportDialogs.confirm('当前是升级前保存在 data/ 中的旧报告。\n需要先复制到独立工程目录，然后导出到该工程的 output/。',{title:'迁移旧报告',okText:'继续迁移'}))return false;
  const moved=await migrateProject();if(!moved)return false;
 }
 if(state.dirty){
  const decision=await modal({title:'当前文稿存在未保存修改',kicker:'导出 · 快照与正式保存分离',
   note:'工作快照不会覆盖项目 report.md；归档文件会标记为 working-copy。',
   okText:'导出当前工作快照',extraText:'先正式保存',cancelText:'取消',
   body:outer=>{const tip=document.createElement('p');tip.textContent='导出未保存文稿，还是先正式保存再导出？两种选择都不会自动覆盖原图。';outer.append(tip);},
   onOk:()=> 'working'});
  if(!decision)return false;
  if(decision==='discard')await save(true);
 }
 return true;
}
async function openProjectFolder(){
 try{
  if(!await askLeave())return;
  const reply=await api('/api/project/open','POST',{}, {'X-HRS-Project-Action':'user-action'});
  await load(reply.document_id);toast('已打开项目目录：'+reply.project_path);
 }catch(e){toast('打开项目失败：'+e.message);}
}
function localImageObjectEdits(){
 return SourceBlocks.promoteImages(state.md,documentModel(state.md).map,{create:src=>figureDefault('image',src),serialize:figureSnippet});
}
function normalizeLocalImageObjects(images=localImageObjectEdits()){
 if(images.skipped.length)toast(images.skipped.length+' 张图片说明超过图对象长度限制，保留原Markdown写法；可缩短说明后再次保存');
 if(images.edits.length){
  const selection={start:editor.selectionStart,end:editor.selectionEnd};
  sourceProjection.set(null);editor.value=images.markdown;
  const moved=position=>{let shift=0;for(const edit of images.edits){if(position>=edit.end)shift+=edit.text.length-(edit.end-edit.start);else if(position>edit.start)return edit.start+shift+edit.text.length;else break;}return position+shift;};
  editor.setSelectionRange(moved(selection.start),moved(selection.end));changed(images.markdown,'normalize-images',true);
 }
}
async function save(force=false){
 await presentationWait;
 commitSource();
 clearTimeout(debounceDraft);
 commitFocusedVisual();
 if(state.saving)throw Error('上一笔正式保存尚未完成');
 const snapshot=state.md,session=state.session,images=localImageObjectEdits();
 if(!state.dirty&&!force&&state.documentId!=='new'&&!images.edits.length){updateDirty();return;}
 if(!state.revision)throw Error('文档尚未加载');
 let selected=null;
 if(state.documentId==='new'){
  selected=await askProjectFolder('create');if(!selected)throw Error('未选择工程目录，正式保存已取消');
  if(session!==state.session||snapshot!==state.md)throw Error('选择期间文稿已变化，请重新保存');
 }
 else if(!state.externalProject&&!state.reportWorkspace){const moved=await migrateProject();if(!moved)throw Error('尚未迁移到独立工程目录，正式保存已取消');}
 normalizeLocalImageObjects(snapshot===state.md?images:undefined);
 state.saving=true;const release=operations.acquire({nodes:document.querySelectorAll('[data-insert]'),editing:true});
 updateDirty();
 try{
  await state.draftQueue; // Never race a draft write against the official commit and cleanup.
  const md=state.md,docId=state.documentId,did=state.draftId;
  const res=await api('/api/save','POST',{markdown:md,revision:state.revision,document_id:docId,
   draft_id:did,template:state.template,render_profile:state.renderProfile,render_options:state.renderOptions,color_theme:state.colorTheme,...(selected?{selection_token:selected.selection_token}:{})});
  state.documentId=res.document_id;state.revision=res.revision;state.savedMd=md;state.draftError=false;
  state.draftId=freshID();state.draftSeq=0;state.draftQueue=Promise.resolve();state.draftSnapshot=null;history.lastKind=null;
  if(selected){state.projectPath=selected.target_path;state.externalProject=true;}
  $('project-label').textContent=res.title;updateDirty();await refreshRecent();
  if(positionMap?.source===state.md){
   const anchor=previewViewportAnchor();
   for(const node of preview.querySelectorAll('img[src],a[href]')){const attr=node.tagName==='IMG'?'src':'href',url=new URL(node.getAttribute(attr),location.href);if(url.origin===location.origin&&url.pathname.startsWith('/assets/')){url.searchParams.set('document_id',state.documentId);url.searchParams.set('draft_id',state.draftId);node.setAttribute(attr,url.href);}}
   renderedKey=documentViewKey();restorePreviewViewport(anchor);previewImages?.committed();
  }else await render();
 }catch(e){state.draftError=e.status===409?false:state.draftError;
  status('error',e.status===409?'正式稿冲突 · 草稿仍在':'正式保存失败');
  if(e.status===409)toast('正式文件已被另一程序修改；保留恢复草稿。请检查后再提交，不能覆盖外部变更。');
  throw e;
 }finally{state.saving=false;release();
  if(!state.draftError&&state.md===state.savedMd)updateDirty();}
}
async function promptRecovery(){
 try{
  const data=await api('/api/drafts');if(!data.drafts.length)return;
  let chosen=data.drafts[0].draft_id;
  const found=await modal({title:'发现未正式保存的恢复草稿',kicker:'草稿恢复 · 不会自动覆盖新文档',
   note:'选择“稍后”会保留草稿。草稿与正式文件是分开的。',okText:'恢复所选草稿',cancelText:'稍后再说',body:outer=>{
    const select=document.createElement('select');select.className='draft-picker';
    for(const d of data.drafts){const opt=document.createElement('option');opt.value=d.draft_id;
      opt.textContent=d.title+' · '+(d.document_id==='new'?'未命名新文档':'已有报告')+' · '+new Date(d.updated).toLocaleString('zh-CN');select.append(opt);}
    select.onchange=()=>{chosen=select.value;};outer.append(select);
    const note=document.createElement('p');note.className='modal-help';note.textContent='恢复后仍需点击“保存”才会改动正式报告。如果正式文件已被其他程序修改，提交时会提示冲突。';outer.append(note);
   },onOk:()=>chosen});
  if(!found)return;
  const reply=await api('/api/draft?draft_id='+encodeURIComponent(found));const draft=reply.draft;
  await restoreDraft(draft,reply.markdown_sha256);
 }catch(e){toast('恢复草稿失败：'+e.message);}
}
async function recoverDocumentDraft(documentId,{draftId=null,session=state.session}={}){
 const pending=await api('/api/drafts?document_id='+encodeURIComponent(documentId));
 const entries=pending.drafts.filter(d=>d.document_id===documentId&&(!draftId||d.draft_id===draftId));
 if(!entries.length||session!==state.session)return;
 let chosen=entries[0].draft_id;
 if(entries.length>1||!state.reportWorkspace&&!draftId){
  const overlay=$('workspace-operation'),visible=!overlay.hidden;overlay.hidden=true;
  try{chosen=await modal({title:'发现此文档的恢复草稿',note:'正式文件不变；恢复后仍需正式保存。',okText:'恢复草稿',cancelText:'稍后',
   body:outer=>{const select=document.createElement('select');for(const d of entries){const option=document.createElement('option');option.value=d.draft_id;option.textContent=d.title+' · '+new Date(d.updated).toLocaleString('zh-CN');select.append(option);}select.onchange=()=>{chosen=select.value;};outer.append(select);},onOk:()=>chosen});}
  finally{if(visible&&workspaceBusy)overlay.hidden=false;}
 }
 if(!chosen||session!==state.session)return;
 const reply=await api('/api/draft?draft_id='+encodeURIComponent(chosen));
 if(session!==state.session)return;
 if(reply.draft.document_id!==documentId)throw Error('恢复草稿不属于当前文档');
 await restoreDraft(reply.draft,reply.markdown_sha256);
}
async function restoreDraft(draft,markdownSha256){
  await load(draft.document_id,draft.template,{recover:false});
  const officialRevision=state.revision;
  state.renderProfile=ReportProfile.normalize(draft.render_profile);state.renderOptions=ReportProfile.normalizeOptions(draft.render_options);$("render-profile").value=state.renderProfile;syncRenderControls();
  state.hasNumberPreference=true;
  await setColorTheme(ReportTheme.normalize(draft.color_theme));
  state.draftId=draft.draft_id;state.draftSeq=draft.seq;state.revision=draft.base_revision;
  state.draftSnapshot={...draft,markdown_sha256:markdownSha256};
  changed(draft.markdown,'restore');
  if(draft.markdown===state.savedMd){state.dirty=false;updateDirty();}
  if(officialRevision!==draft.base_revision)toast('注意：正式文件在草稿产生后已变化；保存时会检查冲突，不会覆盖。');
  else toast('已恢复草稿；尚未正式保存。');
 await render();
}
const renderer=new marked.Renderer();
// Raw HTML is only parsed inside ReportSafeHTML's inert template. No source
// markup reaches the live DOM before that shared allowlist boundary.
renderer.html=(source)=>ReportProfile.html(source,state.renderProfile);
renderer.link=(href,title,text)=>{
 const allowed=/^(https?:\/\/|mailto:|#|\/)/i.test(href||'');
 return `<a href="${escapeHTML(allowed?href:'#')}"${title?' title="'+escapeHTML(title)+'"':''} rel="noopener noreferrer">${text}</a>`;
};
renderer.image=(href,title,text)=>{
 const safe=/^assets\/[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$/.test(href||'');
 if(!safe)return `<span class="warning-pill">外部图片未嵌入：${escapeHTML(text||href)}</span>`;
 return `<img src="${escapeHTML(href)}" alt="${escapeHTML(text||'图片')}" ${title?'title="'+escapeHTML(title)+'"':''} loading="lazy">`;
};
function safeMarkdownFragment(html,options={}){
 return ReportSafeHTML.fragment(html,{...options,imageURL:href=>ReportSafeHTML.assetPath(href)?
  '/'+href+'?document_id='+encodeURIComponent(state.documentId)+'&draft_id='+encodeURIComponent(state.draftId):null});
}
marked.setOptions({renderer,gfm:true,breaks:false,headerIds:false,mangle:false,smartLists:true});
function maskInlineMath(source,records,offset=0){
 // Protect inline TeX before Marked treats \( / \) as ordinary escapes.
 // This shared lexer is also used for native and enhanced table cells.
 const parts=ReportTableContent.tokenize(source);
 let out='';
 for(const part of parts){
  if(part.kind!=='math'||part.display){out+=part.text??part.raw;continue;}
  const id='MATHHOLDER'+offset+'P'+records.length+'HOLDER';
  records.push({id,tex:part.tex,raw:part.raw,start:offset+part.from,end:offset+part.to,display:false});
  out+=id;
 }
 return out;
}

function makeMathElement(item){
 const span=document.createElement('span');span.className='markdown-math '+(item.display?'math-display':'math-inline');
 span.dataset.tex=item.tex;span.dataset.mathId=item.id;span.dataset.display=item.display?'1':'0';span.dataset.raw=item.raw;
 span.setAttribute('contenteditable','false');span.title='双击修改公式';span.textContent=item.tex;
 return span;
}
function replaceMathMarkers(root,records){
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
 const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
 for (const textNode of nodes){
   let s=textNode.nodeValue; const hits=records.filter(r=>s.includes(r.id));
   if(!hits.length)continue;
   const fragment=document.createDocumentFragment();
   while(s){let best=null,pos=Infinity;
     for(const r of hits){const x=s.indexOf(r.id);if(x>=0&&x<pos){pos=x;best=r;}}
     if(!best){fragment.appendChild(document.createTextNode(s));break;}
     if(pos)fragment.appendChild(document.createTextNode(s.slice(0,pos)));
     fragment.appendChild(makeMathElement(best));s=s.slice(pos+best.id.length);
   }
   textNode.replaceWith(fragment);
 }
}

// Engineering table v1: lossless structured table inside a fenced Markdown object.
const TABLE_LANG='report-table';
function tableDefault(rows,cols){return {schema:'report-table-v1',id:'tbl-'+freshID().slice(0,12),caption:'',rows:Array.from({length:rows},()=>Array.from({length:cols},()=>({text:'',rowspan:1,colspan:1}))) };}
function tableValidate(obj){return ReportObjectCatalog.tableValidate(obj);}
function tableSnippet(obj){tableValidate(obj);return '```'+TABLE_LANG+'\n'+JSON.stringify(obj,null,2)+'\n```';}
function parseTableBlock(raw){return tableValidate(SourceBlocks.readObject(raw,TABLE_LANG));}
/** PF12: safe inline GFM tokens. Text is always created by DOM text nodes;
 * links only support local anchors and standard non-executable schemes.
 * Legacy MathJax cells still pass through ReportTableContent.tokenize(). */
function appendSafeTableInline(target,raw){
 // The original Marked inline parser and the same allowlist serve both table
 // kinds. Text/math source stays in the existing cell model and TSV metadata.
 const inlineRenderer=new marked.Renderer();
 inlineRenderer.html=source=>ReportProfile.html(source,state.renderProfile);
 // Engineering cells remain text/math cells, not a new image/object container.
 inlineRenderer.image=(href,title,text)=>escapeHTML('!['+(text||'')+']('+(href||'')+')');
 const options={...marked.defaults,renderer:inlineRenderer,gfm:true,mangle:false,hrsRenderProfile:state.renderProfile};
 const lexer=SourceBlocks.lexer(options,activeLinks);
 const html=marked.Parser.parseInline(lexer.inlineTokens(String(raw)),options);
 target.append(ReportSafeHTML.fragment(html,{inlineOnly:true,images:false}));
}
function appendCaptionInline(target,raw,identity){
 for(const part of ReportTableContent.tokenize(raw)){
  if(part.kind==='text')appendSafeTableInline(target,part.text);
  else target.append(makeMathElement({...part,id:identity+'-'+part.from}));
 }
}

/** TSV is deliberately text/plain so Excel/WPS can place one value in each cell.
 * Merged spans become a rectangular grid with covered positions empty.
 * Quoted CR/LF/Tab cells use the Excel/TSV double-quote convention. */
function tableToTSV(table){
 const grid=[];let width=0;
 for(const [r,tr] of [...table.rows].entries()){
  grid[r]??=[];let col=0;
  for(const cell of [...tr.cells]){
   while(grid[r][col]!==undefined)col++;
   const rowspan=Math.max(1,cell.rowSpan||1),colspan=Math.max(1,cell.colSpan||1);
   const value=cell.dataset.cellRaw??cell.innerText??cell.textContent??'';
   for(let y=r;y<r+rowspan;y++){
    grid[y]??=[];
    for(let x=col;x<col+colspan;x++)grid[y][x]=(y===r&&x===col)?value:'';
   }
   col+=colspan;width=Math.max(width,col);
  }
 }
 const quote=value=>/[\t\r\n"]/.test(value)?'"'+String(value).replace(/"/g,'""')+'"':String(value);
 return grid.map(row=>Array.from({length:width},(_,i)=>quote(row?.[i]??'')).join('\t')).join('\n');
}
/** PF13: escaped, presentation-only syntax colors for original pipe Markdown.
 * The concatenated textContent of the code node remains the EXACT source.
 * Code spans and escaped pipes are not interpreted as column separators. */
function highlightPipeSource(raw){
 const esc=ReportCodeHighlight.escapeHTML;
 const span=(kind,text)=>'<span class="hrs-table-syntax-'+kind+'">'+esc(text)+'</span>';
 const rows=String(raw).split(/(\r?\n)/);let lineNumber=0;
 return rows.map(line=>{
  if(/^\r?\n$/.test(line))return esc(line);
  const isDelimiter=/^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
  const isCaption=/^\s*:[ \t]+/.test(line);
  if(isCaption)return span('caption',line);
  if(isDelimiter)return span('delimiter',line);
  const match=/(\\\||`+[^`\r\n]+`+|\|)/g;
  let at=0,out='';
  for(const token of line.matchAll(match)){
   out+=esc(line.slice(at,token.index));
   const text=token[0];out+=text==='|'?span('pipe',text):text.startsWith('`')?span('inline',text):esc(text);
   at=token.index+text.length;
  }
  out+=esc(line.slice(at));
  // The first pipe row is the literal header; no source rewriting.
  if(lineNumber++===0)return '<span class="hrs-table-syntax-header">'+out+'</span>';
  return out;
 }).join('');
}
function highlightTableSource(raw,kind){
 if(kind==='gfm-pipe')return highlightPipeSource(raw);
 const lines=String(raw).split(/(\r?\n)/),esc=ReportCodeHighlight.escapeHTML;
 return lines.map(line=>/^ {0,3}`{3,}report-table\s*$|^ {0,3}`{3,}\s*$/.test(line)?
  '<span class="hrs-table-syntax-delimiter">'+esc(line)+'</span>':
  ReportCodeHighlight.highlightHTML(line,'json')).join('');
}
function attachTableCard(outer,source,kind){
 const doc=outer.ownerDocument,table=outer.querySelector('table');
 const tools=doc.createElement('div');tools.className='hrs-table-tools';
 const title=doc.createElement('span');title.className='hrs-table-kind';title.textContent='表格';
 const actions=doc.createElement('div');actions.className='hrs-table-actions';
 const toggle=doc.createElement('button');toggle.type='button';toggle.className='hrs-table-toggle';
 toggle.dataset.tableToggle='1';toggle.textContent='查看 MD';toggle.setAttribute('aria-pressed','false');
 const copy=doc.createElement('button');copy.type='button';copy.className='hrs-table-copy';
 copy.dataset.tableCopy='1';copy.textContent='复制表格';copy.title='复制为 Excel / WPS 可分单元格粘贴的 TSV';
 actions.append(toggle,copy);tools.append(title,actions);outer.prepend(tools);
 const sourcePanel=doc.createElement('div');sourcePanel.className='hrs-table-source';sourcePanel.hidden=true;
 const sourceBar=doc.createElement('div');sourceBar.className='hrs-table-source-bar';
 const language=doc.createElement('span');language.className='hrs-table-source-language';
 language.textContent=kind==='gfm-pipe'?'Markdown · 原生管道表':'Markdown · report-table JSON';
 const fold=doc.createElement('button');fold.type='button';fold.className='hrs-table-fold';
 fold.dataset.tableFold='1';fold.textContent='折叠源码';fold.setAttribute('aria-expanded','true');
 fold.title='折叠或展开表格的原始 Markdown 代码块';
 sourceBar.append(language,fold);
 const pre=doc.createElement('pre');pre.className='hrs-table-source-pre';
 const code=doc.createElement('code');code.className='hrs-table-source-code';
 code.innerHTML=highlightTableSource(source,kind);pre.append(code);
 sourcePanel.append(sourceBar,pre);outer.append(sourcePanel);
 // The switch is purely a display preference, never converts source data.
 // Enhanced tables show their lossless report-table Markdown fenced block.
 table.classList.add('hrs-table-rendered');
 return outer;
}
async function copyTSVToClipboard(text){
 if(navigator.clipboard?.writeText){try{await navigator.clipboard.writeText(text);return true;}catch{}}
 const input=document.createElement('textarea');input.value=text;input.readOnly=true;
 input.style.cssText='position:fixed;left:-9999px;top:0;width:1px;height:1px';document.body.append(input);
 input.focus();input.select();let ok=false;try{ok=!!document.execCommand('copy');}finally{input.remove();}return ok;
}
function renderTableObject(obj){
 tableValidate(obj);
 const outer=document.createElement('div');outer.className='report-table-wrap';outer.dataset.table='1';outer.dataset.tableId=obj.id;outer.title='双击编辑表格';
 const table=document.createElement('table');table.className='structured-table';
 if(obj.caption.trim()){const caption=document.createElement('caption');caption.className='report-table-caption';caption.dataset.captionText=obj.caption;table.append(caption);}
 const colgroup=document.createElement('colgroup');ReportTables.getColumnWidths(obj).forEach(width=>{const col=document.createElement('col');col.style.width=width+'%';colgroup.append(col);});table.append(colgroup);
 obj.rows.forEach((row,r)=>{const tr=document.createElement('tr');row.forEach((cell,c)=>{if(cell===null)return;const td=document.createElement(r===0?'th':'td');
  const content=document.createElement('div');content.className='table-cell-content';
  for(const part of ReportTableContent.tokenize(ReportTables.compactDisplayText(cell.text))){
   if(part.kind==='text')appendSafeTableInline(content,part.text);
   else content.append(makeMathElement({...part,id:'cell-'+obj.id+'-'+r+'-'+c+'-'+part.from}));
  }
  td.append(content);td.dataset.cellRaw=cell.text;td.rowSpan=cell.rowspan;td.colSpan=cell.colspan;
  if(obj.align?.[c])td.style.textAlign=obj.align[c];
  if(obj.verticalAlign)td.style.verticalAlign=obj.verticalAlign;
  tr.append(td);});table.append(tr);});outer.append(table);
 const hint=document.createElement('div');hint.className='chart-note';hint.textContent='表格 · 双击编辑 / Excel 区域粘贴';outer.append(hint);return outer;
}
const FIGURE_LANG='report-figure';
function figureDefault(kind='mermaid',src=''){
 const obj={schema:'report-figure-v1',id:'fig-'+freshID().slice(0,12),caption:'',kind};
 if(kind==='image'){obj.src=src;obj.alt='';}
 else obj.source='flowchart LR\n    A[开始] --> B[结束]';
 return obj;
}
function figureValidate(obj){return ReportObjectCatalog.figureValidate(obj);}
function figureSnippet(obj){figureValidate(obj);return '```'+FIGURE_LANG+'\n'+JSON.stringify(obj,null,2)+'\n```';}
function parseFigureBlock(raw){return figureValidate(SourceBlocks.readObject(raw,FIGURE_LANG));}
function figureElement(obj){
 const figure=document.createElement('figure');figure.className='report-figure-wrap';figure.dataset.figureId=obj.id;figure.title='双击修改图题或图形';
 if(obj.kind==='image'){
  const img=document.createElement('img');img.alt=obj.alt||obj.caption;const name=obj.src.substring(7);
  img.src='/assets/'+encodeURIComponent(name)+'?document_id='+encodeURIComponent(state.documentId)+'&draft_id='+encodeURIComponent(state.draftId);
  ReportPreviewImages.dimensions(img,obj.rendition);
  const media=document.createElement('div');media.className='figure-media-stage';media.append(img);figure.append(media);
  if(obj.sourceAsset?.toLowerCase().endsWith('.pdf')){
   // Opens the OS/browser PDF viewer only after the user clicks; no extra
   // PDF plugin, iframe, external URL or altered project resource is needed.
   const pdf=document.createElement('a');pdf.className='figure-source-link';
   pdf.href='/assets/'+encodeURIComponent(obj.sourceAsset.slice(7))+'?document_id='+encodeURIComponent(state.documentId)+'&draft_id='+encodeURIComponent(state.draftId);
   pdf.target='_blank';pdf.rel='noopener noreferrer';pdf.dataset.figureSource='pdf';pdf.dataset.pdfAsset=obj.sourceAsset.slice(7);img.dataset.pdfAsset=obj.sourceAsset.slice(7);img.title='单击放大预览，双击打开 PDF 原件';
   pdf.textContent='PDF ↗';pdf.title='打开原始 PDF（新窗口；图片本身可放大）';pdf.setAttribute('aria-label','打开这张图的原始 PDF');pdf.classList.add('figure-source-chip');media.append(pdf);
  }
 }else{
  const graph=document.createElement('div');graph.className='report-figure-graph';
  graph.dataset.hrsMermaid='1';graph._mermaidSource=obj.source;
  figure.append(graph);
 }
 if(obj.caption.trim()){const caption=document.createElement('figcaption');caption.className='report-figure-caption';caption.dataset.captionText=obj.caption;figure.append(caption);}
 if(obj.kind==='mermaid'){const note=document.createElement('div');note.className='chart-note';note.textContent='流程图 · 双击编辑节点或源码';figure.append(note);}
 if(obj.kind==='image'){const edit=document.createElement('button');edit.type='button';edit.className='chart-note figure-edit-button';edit.textContent='编辑图题 / 属性';edit.dataset.editFigure='1';figure.append(edit);}
 return figure;
}
async function insertFigureDialog(){
 let select,caption;
 const obj=await modal({title:'插入带图题的流程图',kicker:'图 · 可自动编号',body:outer=>{
  const p=document.createElement('p');p.className='modal-help';p.textContent='可先生成一个可编辑流程图，也可以通过“图片”按钮插入带题注的图片。图号将由最终位置自动计算。';outer.append(p);
  caption=document.createElement('input');caption.className='table-caption-input';caption.placeholder='图题（不需要输入图号）';caption.value='数据处理流程';outer.append(caption);
 },onOk:()=>{const obj=figureDefault('mermaid');obj.caption=caption.value;return obj;},okText:'插入图形'});
 if(obj)insertAtSelection('\n'+figureSnippet(obj)+'\n');
}
async function editFigure(block){
 if(!block||state.saving)return;
 try{currentBlockRange(block);}catch(e){toast(e.message);scheduleRender();return;}
 const start=+block.dataset.start,end=+block.dataset.end,original=state.md.slice(start,end);
 let obj;try{obj=parseFigureBlock(original.trim());}catch(e){toast('图形解析失败：'+e.message);return;}
 if(obj.kind==='mermaid'){
  const snapshot=state.md,session=state.session;
  const result=await diagramDialog(obj.source,{caption:obj.caption});
  if(!result)return;
  try{if(state.md!==snapshot||state.session!==session)throw Error('文稿已变化，请重新打开图形');SourceMap.assertRange(state.md,{start,end},original,snapshot);}catch(e){toast(e.message);scheduleRender();return;}
  const working=cloneReport(obj);working.caption=result.caption;working.source=result.source;
  if(working.caption===obj.caption&&working.source===obj.source)return;
  changed(state.md.slice(0,start)+SourceBlocks.replacement(original,figureSnippet(working))+state.md.slice(end),'figure');await render();return;
 }
 const working=cloneReport(obj);let titleField,field;
 const accepted=await modal({title:'编辑图形及图题',kicker:'图 · 保留源 ID',note:'调整位置后会自动重新编号；图题无需手填编号',wide:true,body:outer=>{
  titleField=document.createElement('input');titleField.className='table-caption-input';titleField.placeholder='图题';titleField.value=working.caption;outer.append(titleField);
  if(working.kind==='image'){
   const extras=document.createElement('details');extras.className='figure-alt-advanced';
   const trigger=document.createElement('summary');trigger.textContent='高级设置 · 图片替代文字（无障碍阅读）';extras.append(trigger);
   const note=document.createElement('p');note.className='modal-help';note.textContent='此项供读屏软件或图片加载失败时使用，不是图题。不填写就使用上方图题作为替代说明，不改变图片资源位置。';extras.append(note);
   field=document.createElement('textarea');field.setAttribute('aria-label','图片替代文字');field.placeholder='可留空，默认使用图题';field.value=working.alt==='图片说明'?'':working.alt;field.rows=2;extras.append(field);outer.append(extras);
  }
  else field=modalTextarea(outer,'Mermaid 流程图源码',working.source,230);
 },onOk:()=>{working.caption=titleField.value;if(working.kind==='image')working.alt=field.value;else working.source=field.value;return figureValidate(working);},okText:'应用图形修改'});
 if(!accepted)return;
 try{currentBlockRange(block);}catch(e){toast(e.message);scheduleRender();return;}
 changed(state.md.slice(0,start)+SourceBlocks.replacement(original,figureSnippet(accepted))+state.md.slice(end),'figure');await render();
}
function groupElement(obj){
 const figure=document.createElement('figure');figure.className='report-figure-wrap report-image-group';figure.dataset.figureId=obj.id;figure.title='双击编辑组图、行列、子图顺序及说明';
 const grid=document.createElement('div');grid.className='image-group-grid';grid.style.setProperty('--group-columns',obj.columns);
 obj.images.forEach((item,index)=>{
  const cell=document.createElement('div');cell.className='image-group-cell';
  const img=document.createElement('img');img.alt=item.caption;img.src='/assets/'+encodeURIComponent(item.src.slice(7))+'?document_id='+encodeURIComponent(state.documentId)+'&draft_id='+encodeURIComponent(state.draftId);
  ReportPreviewImages.dimensions(img,item.rendition);cell.append(img);
  if(item.sourceAsset?.toLowerCase().endsWith('.pdf')){const pdf=document.createElement('a');pdf.href='/assets/'+encodeURIComponent(item.sourceAsset.slice(7))+'?document_id='+encodeURIComponent(state.documentId)+'&draft_id='+encodeURIComponent(state.draftId);pdf.target='_blank';pdf.rel='noopener noreferrer';pdf.className='figure-source-link';pdf.dataset.figureSource='pdf';pdf.dataset.pdfAsset=item.sourceAsset.slice(7);img.dataset.pdfAsset=item.sourceAsset.slice(7);pdf.textContent='PDF ↗';pdf.title='打开子图的原始 PDF（新窗口）';pdf.setAttribute('aria-label','打开子图原始 PDF');pdf.classList.add('figure-source-chip');cell.append(pdf);}
  if(obj.showSubfigureLabels!==false||item.caption){
   const sub=document.createElement('div');sub.className='image-group-subcaption';
   sub.textContent=obj.showSubfigureLabels===false?'':'('+String.fromCharCode(97+index)+')'+(item.caption?' ':'');
   if(item.caption)appendCaptionInline(sub,item.caption,'caption-'+obj.id+'-sub-'+index);cell.append(sub);
  }
  grid.append(cell);
 });
 if(obj.rows!==undefined){
  const vacant=obj.rows*obj.columns-obj.images.length;
  for(let i=0;i<vacant;i++){
   const blank=document.createElement('div');blank.className='image-group-empty';blank.setAttribute('aria-hidden','true');grid.append(blank);
  }
 }
 figure.append(grid);
 if(obj.caption.trim()){const caption=document.createElement('figcaption');caption.className='report-figure-caption';caption.dataset.captionText=obj.caption;figure.append(caption);}const edit=document.createElement('button');edit.type='button';edit.className='chart-note figure-edit-button';edit.dataset.editFigure='1';edit.textContent='编辑组图 / 图题';figure.append(edit);return figure;
}
async function groupDialog(original=null){
 const working=original?cloneReport(original):{schema:'report-image-group-v1',id:'fig-'+freshID().slice(0,12),columns:3,caption:'组图说明',images:[]};
 const snapshot=state.md,session=state.session,docId=state.documentId,draftId=state.draftId;
 let pending=0,columns,rowsSelect,labels,caption,entries,addButton,fileInput,status;
 return modal({title:original?'编辑组图':'插入组图',kicker:'组图 · 最多 12 张，支持 MATLAB/Origin 粘贴',
  note:'先选行列，再选择文件或粘贴图形；Ctrl+V 图片会进入组图，文字粘贴不受影响。',wide:true,
  okText:original?'应用组图修改':'插入组图',body:outer=>{
  const pane=document.createElement('div');pane.className='group-editor-pane';outer.append(pane);
  const id=document.createElement('p');id.className='modal-help';id.textContent='整组 ID：'+working.id;pane.append(id);
  const options=document.createElement('div');options.className='group-layout-options';
  const colLabel=document.createElement('label');colLabel.textContent='列数';
  columns=document.createElement('select');columns.setAttribute('aria-label','组图每行列数');
  for(const count of [1,2,3,4]){const option=document.createElement('option');option.value=count;option.textContent=count+' 列';columns.append(option);}columns.value=working.columns;colLabel.append(columns);
  const rowLabel=document.createElement('label');rowLabel.textContent='行数';
  rowsSelect=document.createElement('select');rowsSelect.setAttribute('aria-label','组图行数');
  for(const [value,title] of [['auto','自动'],['1','1 行'],['2','2 行'],['3','3 行']]){const option=document.createElement('option');option.value=value;option.textContent=title;rowsSelect.append(option);}rowsSelect.value=String(working.rows||'auto');rowLabel.append(rowsSelect);
  const lab=document.createElement('label');lab.className='group-subfig-toggle';
  labels=document.createElement('input');labels.type='checkbox';labels.checked=working.showSubfigureLabels!==false;labels.setAttribute('aria-label','显示子图序号');lab.append(labels,document.createTextNode('显示子图序号 (a)(b)…'));
  options.append(colLabel,rowLabel,lab);pane.append(options);
  caption=document.createElement('input');caption.className='table-caption-input';caption.setAttribute('aria-label','组图题');caption.placeholder='整组图题（无需图号）';caption.maxLength=300;caption.value=working.caption;pane.append(caption);
  entries=document.createElement('div');entries.className='group-editor-rows';pane.append(entries);
  const actions=document.createElement('div');actions.className='group-upload-actions';
  const picker=document.createElement('label');picker.className='group-files-label';picker.textContent='添加图片文件（可多选）';
  fileInput=document.createElement('input');fileInput.type='file';fileInput.multiple=true;fileInput.accept='image/png,image/jpeg,image/gif,image/webp,image/svg+xml,.emf,.pdf,application/pdf';fileInput.setAttribute('aria-label','添加组图图片');picker.append(fileInput);
  addButton=document.createElement('button');addButton.type='button';addButton.className='btn btn-quiet';addButton.textContent='⎘ 粘贴一张图（原生 EMF）';addButton.setAttribute('aria-label','组图粘贴图形');
  status=document.createElement('span');status.className='group-upload-status';status.setAttribute('role','status');
  actions.append(picker,addButton,status);pane.append(actions);
  function consistent(){return !state.saving&&state.session===session&&state.md===snapshot&&state.documentId===docId&&state.draftId===draftId&&!$('modal-layer').hidden&&entries.isConnected;}
  function busy(on){pending+=on?1:-1;const uploading=pending>0;fileInput.disabled=uploading;addButton.disabled=uploading;$('modal-ok').disabled=uploading;status.textContent=uploading?'图片读取中，请稍候…':'';}
  function paint(){entries.replaceChildren();working.images.forEach((item,index)=>{
   const row=document.createElement('div');row.className='group-editor-row';
   const img=document.createElement('img');img.alt=item.caption;img.src='/assets/'+encodeURIComponent(item.src.slice(7))+'?document_id='+encodeURIComponent(docId)+'&draft_id='+encodeURIComponent(draftId);row.append(img);
   const info=document.createElement('div'),name=document.createElement('small');name.textContent='('+String.fromCharCode(97+index)+') '+item.src.slice(7)+(item.sourceAsset?' · 原件：'+item.sourceAsset.slice(7):'');
   const text=document.createElement('input');text.value=item.caption;text.maxLength=300;text.setAttribute('aria-label','子图 '+(index+1)+' 说明');text.placeholder='子图说明（可空）';text.oninput=()=>{item.caption=text.value;};info.append(name,text);row.append(info);
   for(const [title,delta] of [['上移',-1],['下移',1],['移除',0]]){
    const button=document.createElement('button');button.type='button';button.textContent=title;button.className='btn btn-quiet';button.disabled=delta!==0&&(index+delta<0||index+delta>=working.images.length);
    button.onclick=()=>{if(pending)return;if(delta)[working.images[index],working.images[index+delta]]=[working.images[index+delta],working.images[index]];else working.images.splice(index,1);paint();};row.append(button);
   }entries.append(row);
  });
   status.textContent=working.images.length+'/12 张；当前 '+columns.value+' 列、'+(rowsSelect.value==='auto'?'自动行数':rowsSelect.value+' 行');
  }
  columns.onchange=paint;rowsSelect.onchange=paint;labels.onchange=()=>{};
  function assetFromReply(reply){
   if(!reply?.path||!/^assets\/[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.(?:png|jpe?g|gif|webp|svg)$/i.test(reply.path))throw Error('组图上传结果不是合法图片路径');
   return {src:reply.path,caption:'',...(reply.source_asset||reply.vector_source?{sourceAsset:reply.source_asset||reply.vector_source}:{}),
    ...(reply.raster_fallback?{rasterFallback:reply.raster_fallback}:{}),...(reply.rendition?{rendition:reply.rendition}:{})};
  }
  async function uploadBrowserFile(file,linked=[]){
   const req={name:file.name,base64:await fileToB64(file),document_id:docId,draft_id:draftId};
   if(file.name.toLowerCase().endsWith('.pdf')&&linked.length===1&&/\.png$/i.test(linked[0].name))req.preview_base64=await fileToB64(linked[0]);
   if(file.name.toLowerCase().endsWith('.svg')&&linked.length){req.linked_assets={};for(const other of linked)req.linked_assets[other.name]=await fileToB64(other);}
   return assetFromReply(await api('/api/upload','POST',req));
  }
  async function runTransfer(operation){
   if(pending)return;
   if(working.images.length>=12)return toast('组图最多 12 张图片');
   if(!consistent())return toast('文稿或组图窗口已变化，请重新打开组图');
   busy(true);
   try{
    const uploaded=await operation();
    if(!consistent())throw Error('文稿或组图窗口已变化，本次结果不会插入原文');
    if(working.images.length+uploaded.length>12)throw Error('组图最多 12 张图片');
    working.images.push(...uploaded);paint();
   }catch(error){if(!$('modal-layer').hidden)toast('组图图片导入失败：'+error.message);}
   finally{busy(false);if(!consistent())status.textContent='';}
  }
  async function nativeClipboard(fallbackFile=null){
   return runTransfer(async()=>{
    try{
     const res=await fetch('/api/clipboard/paste',{method:'POST',headers:{'Content-Type':'application/json','X-Report-Studio-Clipboard':'user-action'},body:JSON.stringify({document_id:docId,draft_id:draftId})});
     const reply=await res.json();if(!res.ok||!reply.ok)throw Error(reply.error||`HTTP ${res.status}`);
     return [assetFromReply(reply)];
    }catch(error){if(fallbackFile)return [await uploadBrowserFile(fallbackFile)];throw error;}
   });
  }
  fileInput.onchange=()=>{
   const files=[...fileInput.files];fileInput.value='';
   const svgs=files.filter(f=>/\.svg$/i.test(f.name)),pdfs=files.filter(f=>/\.pdf$/i.test(f.name));
   if(svgs.length+pdfs.length>1)return toast('每次只选择一份 SVG/PDF 与它的关联图片；其他图片可一次多选');
   const primary=svgs[0]||pdfs[0];
   const addedCount=primary?1:files.length;
   if(!addedCount)return;
   if(working.images.length+addedCount>12)return toast('组图最多 12 张图片');
   runTransfer(async()=>{
    if(primary){const rest=files.filter(f=>f!==primary);
     if(/\.pdf$/i.test(primary.name)&&rest.length&&!(rest.length===1&&/\.png$/i.test(rest[0].name)))throw Error('PDF 仅可搭配一张 PNG 预览');
     return [await uploadBrowserFile(primary,rest)];
    }
    const added=[];for(const file of files)added.push(await uploadBrowserFile(file));return added;
   });
  };
  addButton.onclick=()=>nativeClipboard();
  // This handler lives only on this dialog content. Plain-text paste in
  // captions / other modal controls is not intercepted.
  pane.addEventListener('paste',event=>{
   if(event.defaultPrevented||pending)return;
   const data=event.clipboardData,file=[...(data?.files||[])].find(f=>f.type?.startsWith('image/')||/\.(?:emf|svg)$/i.test(f.name));
   const plain=data?.getData('text/plain')||'',rich=data?.getData('text/html')||'';
   if(file||(!plain&&(!rich||/<(?:img|svg)\b/i.test(rich)))){
    event.preventDefault();event.stopPropagation();nativeClipboard(file);
   }
  });
  paint();
 },onOk:()=>{
  if(pending)throw Error('图形仍在读取，请稍候');
  if(state.saving||state.session!==session||state.md!==snapshot||state.draftId!==draftId||state.documentId!==docId)throw Error('文稿已变化，请重新打开组图');
  working.caption=caption.value;working.columns=+columns.value;
  if(rowsSelect.value==='auto')delete working.rows;else working.rows=+rowsSelect.value;
  if(!labels.checked)working.showSubfigureLabels=false;else delete working.showSubfigureLabels;
  return ReportLayout.validateGroup(working);
 }});
}
async function insertGroup(){
 commitSource();commitFocusedVisual();const snapshot=state.md,session=state.session,bookmark={start:editor.selectionStart,end:editor.selectionEnd};
 const obj=await groupDialog();if(!obj)return;
 if(state.session!==session||state.md!==snapshot)return toast('文稿已变化，请重新插入组图');
 insertAtSelection('\n'+ReportLayout.groupSnippet(obj)+'\n',bookmark);toast('组图已暂存；按“保存”写入正式文档');
}
async function editGroup(block){
 if(!block||state.saving)return;
 try{
  currentBlockRange(block);const original=block._sourceRaw,obj=ReportLayout.parseGroup(original),accepted=await groupDialog(obj);
  if(!accepted||JSON.stringify(obj)===JSON.stringify(accepted))return;
  currentBlockRange(block);await replaceInBlock(block,()=>SourceBlocks.replacement(original,ReportLayout.groupSnippet(accepted)));
 }catch(error){toast(error.message);scheduleRender();}
}
async function insertSectionReference(){
 commitSource();commitFocusedVisual();if(positionMap?.source!==state.md)await render();
 const sections=positionMap.blocks.filter(block=>block.section?.valid&&block.section.title);
 if(!sections.length)return toast('请先添加 # 至 ###### 的章节标题');
 const snapshot=state.md,session=state.session,bookmark={start:editor.selectionStart,end:editor.selectionEnd};let picker;
 const choice=await modal({title:'插入章节标题引用',kicker:'稳定章节 ID',note:'引用显示当前标题；改名或调序后仍指向同一章节。尚无 ID 的标题会补一个 sec- ID。',body:outer=>{
  picker=document.createElement('select');picker.className='draft-picker';picker.setAttribute('aria-label','引用章节');
  for(const block of sections){const option=document.createElement('option');option.value=block.index;option.textContent='H'+block.token.depth+' · '+block.section.title+(block.section.id?' ['+block.section.id+']':'');picker.append(option);}outer.append(picker);
 },onOk:()=>sections.find(block=>block.index===+picker.value),okText:'插入引用'});
 if(!choice)return;
 try{
  if(state.saving||state.session!==session)throw Error('文档已切换或正在保存');SourceMap.assertRange(state.md,choice,choice.raw,snapshot);
  let md=state.md,a=bookmark.start,b=bookmark.end,id=choice.section.id;
  if(!id){
   id='sec-'+freshID().slice(0,12);const frame=SourceMap.textFrame(choice.raw,choice.token.depth);
   if(a>choice.start&&a<choice.end||b>choice.start&&b<choice.end)throw Error('请把插入位置放在被引用标题之外的正文中');
   const raw=frame.prefix+frame.body+' {#'+id+'}'+frame.suffix,delta=raw.length-choice.raw.length;
   md=md.slice(0,choice.start)+raw+md.slice(choice.end);if(a>=choice.end)a+=delta;if(b>=choice.end)b+=delta;
  }
  const reference='@sec:'+id;changed(md.slice(0,a)+reference+md.slice(b),'section-reference');editor.setSelectionRange(a+reference.length);await render();
 }catch(error){toast(error.message);}
}
/** Choose a validated local figure/table and insert its stable ID marker.
 * Word pipeline note: @fig/@tbl identifiers are source semantics; displayed
 * "图 1"/"表 1" is derived from document order, not stored in Markdown.
 */
async function insertObjectReference(){
 commitSource();commitFocusedVisual();if(state.saving)return toast('正在正式保存，请稍候');
 if(positionMap?.source!==state.md)await render();
 const snapshot=state.md,session=state.session,bookmark={start:editor.selectionStart,end:editor.selectionEnd};
 if(SourceBlocks.scan(snapshot).some(b=>bookmark.start>b.from&&bookmark.start<b.to)||positionMap.at(bookmark.start)?.type==='reportEquation')return toast('请把光标放在普通正文里');
 const choices=[];
 for(const entry of documentModel(snapshot).catalog.items){
  if(!entry.valid||entry.duplicate)continue;
  const block=entry.record,kind={figure:'fig',table:'tbl',equation:'eq'}[entry.kind];if(!kind)continue;
  const id=entry.id||kind+'-'+freshID().slice(0,12),node=preview.querySelector(`[data-map-index="${block.index}"]`);
  const caption=entry.caption||node?.querySelector('figcaption,caption')?.textContent||block.token.equation?.tex.trim()||entry.rows?.[0]?.map(c=>c?.text||'').join(' · ')||entry.label;
  choices.push({id,kind,caption,entry,materialize:!entry.id});
 }
 if(!choices.length)return toast('请先插入图表或块公式；已有普通对象可先打开编辑窗口确认身份');
 let picker,category=choices[0].kind;
 const selected=await modal({title:'选择引用对象',kicker:'按题注选择 · 编号自动更新',note:'显示编号随文档设置和顺序更新；源码保存对象 ID。',body:outer=>{
  const tabs=document.createElement('div');tabs.className='reference-tabs';tabs.setAttribute('role','tablist');outer.append(tabs);
  picker=document.createElement('select');picker.className='draft-picker';picker.setAttribute('aria-label','选择引用对象');outer.append(picker);
  function paint(){picker.replaceChildren();for(const entry of choices.filter(x=>x.kind===category)){
   const option=document.createElement('option');option.value=entry.id;option.textContent=entry.caption.slice(0,140)+' ['+entry.id+']';picker.append(option);
  }tabs.querySelectorAll('button').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.kind===category)));$('modal-ok').disabled=!picker.options.length;}
  for(const [kind,label] of [['fig','图'],['tbl','表'],['eq','公式']]){
   const tab=document.createElement('button');tab.type='button';tab.className='reference-tab';tab.setAttribute('role','tab');tab.dataset.kind=kind;tab.textContent=label+' · '+choices.filter(x=>x.kind===kind).length;tab.onclick=()=>{category=kind;paint();};tabs.append(tab);
  }paint();
 },onOk:()=>choices.find(x=>x.id===picker.value),okText:'插入引用'});
 if(!selected)return;
 if(state.saving||state.session!==session||state.md!==snapshot)return toast('文稿已变化，请重新选择引用');
 let md=snapshot,a=bookmark.start,b=bookmark.end;
 if(selected.materialize){
  const entry=selected.entry,record=entry.record;let end=record.end,next;
  if(a>record.start&&a<end||b>record.start&&b<end)return toast('请把引用插入位置放在对象之外');
  if(selected.kind==='eq')next=ReportEquations.snippet(record.token.equation.tex,selected.id,snapshot.includes('\r\n')?'\r\n':'\n',record.token.equation.delimiter);
  else if(selected.kind==='tbl'){
   const following=positionMap.blocks[record.index+1];if(following?.type==='paragraph'&&ReportPipeTables.parseCaption(following.raw.trim()))end=following.end;
   next=ReportPipeTables.stringify(entry,{id:selected.id,withCaption:true});
  }else{const object=figureDefault('mermaid');object.id=selected.id;object.caption='';object.source=record.token.text;next=figureSnippet(object);}
  next=SourceBlocks.replacement(md.slice(record.start,end),next);const delta=next.length-(end-record.start);
  md=md.slice(0,record.start)+next+md.slice(end);if(a>=end)a+=delta;if(b>=end)b+=delta;
 }
 const token='@'+selected.kind+':'+selected.id,left=/[A-Za-z0-9_@-]$/.test(md.slice(0,a))?' ':'',right=/^[A-Za-z0-9_@-]/.test(md.slice(b))?' ':'';
 changed(md.slice(0,a)+left+token+right+md.slice(b),'object-reference');editor.setSelectionRange(a+left.length+token.length+right.length);await render();

}
function numberObjects(root,map=positionMap,context={}){
 const profile=context.profile??state.renderProfile,options=context.options??state.renderOptions;
 const error=context.error||(message=>state.renderErrors.push(message));
 const captionInline=context.captionInline||appendCaptionInline;
 const remember=context.remember||((link,reference)=>referenceRecords.set(link,reference));
 const objects=new Map(),catalog=ReportObjectCatalog.indexDOM(root);
 const showObjects=profile==='engineering'||options.show_object_numbers,showEquations=options.show_equation_numbers;
 const sections=new Map();for(const record of map?.blocks||[])if(record.section?.id&&record.section.valid)sections.set(record.section.id,(sections.get(record.section.id)||0)+1);
 for(const entry of root._sourceObjectCatalog?.items||[]){
  if(!entry.id||!entry.valid||entry.duplicate)continue;
  const name=entry.caption||entry.rows?.[0]?.filter(Boolean).map(c=>c.text).join(' · ')||(entry.kind==='equation'?'该公式':entry.kind==='table'?'表':'图');
  const show=entry.kind==='equation'?showEquations:showObjects;
  objects.set(entry.id,{label:show?entry.label:name,kind:{table:'tbl',figure:'fig',equation:'eq'}[entry.kind]});
 }
 for(const record of map?.blocks||[])if(record.section?.id)objects.set(record.section.id,{label:'“'+ReportNotebook.title(record.token)+'”节',kind:'sec'});
 for(const entry of catalog.items){
  const node=entry.node,id=entry.id,kind=entry.kind;
  if(!entry.valid||entry.duplicate){error('对象 ID 重复或无效：'+id);continue;}
  if(kind==='table'||kind==='figure'){
   let caption=node.querySelector(kind==='table'?'caption':'figcaption');
   if(!caption){caption=document.createElement(kind==='table'?'caption':'figcaption');caption.className=kind==='table'?'report-table-caption':'report-figure-caption';caption.dataset.captionText='';if(kind==='table')node.querySelector('table')?.prepend(caption);else node.insertBefore(caption,node.querySelector('.chart-note'));}
   const text=caption.dataset.captionText||'',content=document.createElement('span');content.className='hrs-caption-content';
   captionInline(content,text,'caption-'+(id||node.closest('.doc-block')?.dataset.mapIndex||'object'));caption.replaceChildren(content);
   ReportObjectCatalog.captionDisplay(caption,showObjects?entry.label+(text?'  ':''):'');
  }else if(kind==='equation'){
   node.querySelectorAll('.equation-number').forEach(n=>n.remove());
   const numberNode=document.createElement('span');numberNode.className='equation-number';numberNode.hidden=!showEquations;numberNode.textContent='('+entry.number+')';node.append(numberNode);
  }
  node.id=id?'object-'+id:'hrs-object-'+(node.closest('.doc-block')?.dataset.mapIndex||catalog.items.indexOf(entry));
  if(id)objects.set(id,{label:kind==='equation'?(showEquations?entry.label:'该公式'):showObjects?entry.label:(node.querySelector(kind==='table'?'caption':'figcaption')?.dataset.captionText||(kind==='figure'?'图':'表')),kind:{table:'tbl',figure:'fig',equation:'eq'}[kind]});
 }
 for(const heading of root.querySelectorAll('[data-section-id]')){
   const id=heading.dataset.sectionId;if(sections.get(id)>1){error('章节 ID 重复：'+id);continue;}
  heading.id='object-'+id;const label=heading.cloneNode(true);label.querySelectorAll('.hrs-heading-number').forEach(n=>n.remove());objects.set(id,{label:'“'+label.textContent+'”节',kind:'sec'});
 }
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
 const candidates=[];let node;
 while((node=walker.nextNode())){
  if(!/@(?:fig|tbl|sec|eq):[A-Za-z][A-Za-z0-9_-]{0,63}\b/.test(node.textContent))continue;
  if(node.parentElement?.closest('pre,code,.report-table-wrap,figure,.mermaid-card,.markdown-math'))continue;
  candidates.push(node);
 }
 const usedReferences=new Set();
 for(const textNode of candidates){
  const content=textNode.textContent,regexp=/@(fig|tbl|sec|eq):([A-Za-z][A-Za-z0-9_-]{0,63})\b/g,frag=document.createDocumentFragment();
  let off=0,m;
  while((m=regexp.exec(content))){
   frag.append(document.createTextNode(content.slice(off,m.index)));
   const id=m[2];
   const block=textNode.parentElement.closest('.doc-block'),mapped=map?.blocks[+block?.dataset.mapIndex];
   const reference=mapped?.references.find(ref=>ref.raw===m[0]&&!usedReferences.has(ref));if(reference)usedReferences.add(reference);
   if(!reference){frag.append(document.createTextNode(m[0]));off=m.index+m[0].length;continue;}
   const entry=map?.object(id)?objects.get(id):null;
   const link=document.createElement(entry&&entry.kind===m[1]&&!textNode.parentElement.closest('a')?'a':'span');
   if(entry&&entry.kind===m[1]){link.className='object-xref';link.textContent=entry.label;link.href='#object-'+id;}
   else{error('无效图表引用：@'+m[1]+':'+id);link.className='object-xref-invalid';link.textContent='[无效引用 '+m[0]+']';}
   link.dataset.xrefRaw=m[0];link.dataset.xrefTarget=id;link.dataset.xrefKind=m[1];link.contentEditable='false';link.title='单击定位对象；双击修改引用 ID';
   if(reference)remember(link,{...reference,source:map.source});frag.append(link);
   off=m.index+m[0].length;
  }
  frag.append(document.createTextNode(content.slice(off)));textNode.replaceWith(frag);
 }
 root.dataset.hrsRenderProfile=profile;
 ReportObjectCatalog.applyDisplay(root,showObjects,showEquations);
 if(context.editable!==false)ReportObjectCatalog.tableChrome(root,profile,table=>table.dispatchEvent(new MouseEvent('dblclick',{bubbles:true})));
 return objects;
}
window.ReportObjectNumbering={apply:numberObjects};

async function insertTableDialog(){
 let rInput,cInput;const obj=await modal({title:'插入表格',kicker:'表格 · 支持 Excel 矩形粘贴',body:outer=>{
  const row=document.createElement('div');row.className='table-setup';outer.append(row);
  for(const [label,value,onSet] of [['行数',4,x=>rInput=x],['列数',3,x=>cInput=x]]){
   const wrap=document.createElement('label');wrap.textContent=label+' ';const field=document.createElement('input');field.type='number';field.min=1;field.max=label==='行数'?100:30;field.value=value;wrap.append(field);row.append(wrap);onSet(field);
  }
  const p=document.createElement('p');p.className='modal-help';p.textContent='生成后双击表格，可粘贴 Excel 多格区域或合并首行。';outer.append(p);
 },onOk:()=>{const r=Number(rInput.value),c=Number(cInput.value);if(!Number.isInteger(r)||!Number.isInteger(c)||r<1||r>100||c<1||c>30)throw Error('行数须为 1–100，列数须为 1–30');return tableDefault(r,c);},okText:'插入表格'});
 if(obj)insertAtSelection('\n'+tableSnippet(obj)+'\n');
}
function tablePasteMatrix(text){return ReportTables.parseTSV(text).map(row=>row.map(cell=>cell.text));}
async function editStructuredTable(block){
 if(!block||state.saving)return;
 try{currentBlockRange(block);}catch(e){toast(e.message);scheduleRender();return;}
 const start=+block.dataset.start,end=+block.dataset.end,original=state.md.slice(start,end),session=state.session,sourceSnapshot=state.md;
 if(!block.isConnected||original!==block._sourceRaw){toast('表格位置已变化，请等待预览刷新后重试');scheduleRender();return;}
  const scroller=preview.closest('.page-scroll'),viewportTop=block.getBoundingClientRect().top-scroller.getBoundingClientRect().top;
 const isPipe=block.dataset.pipeTable==='1';
 let parsed=null,model;
 try{
  if(isPipe){parsed=ReportPipeTables.parseRaw(original);model=parsed.model;}
  else model=parseTableBlock(original);
 }catch(e){toast('表格解析失败：'+e.message);return;}
 const accepted=await ReportTableEditor.open(model,{modal,toast});
 if(!accepted)return;
 // Both table kinds can be re-rendered while the dialog is open. Bind the
 // transaction to the complete source/session, rather than an old DOM node.
 if(state.session!==session||state.md!==sourceSnapshot||state.md.slice(start,end)!==original){toast('表格位置已变化，请重新打开');return;}
 try{tableValidate(accepted);}catch(e){toast(e.message);return;}
 if(JSON.stringify(accepted)===JSON.stringify(model))return;
 let result;
 if(isPipe){
  let id=parsed.id;
  if(!id&&accepted.caption.trim())id='tbl-'+freshID().slice(0,12);
  if(ReportPipeTables.requiresPromotion(accepted)){
   const ok=await ReportDialogs.confirm('合并单元格、多行内容、精确列宽或垂直对齐不能保存为原生 Markdown 表格。转换成增强表格（仍可编辑）吗？取消不会修改正文。',{title:'转换为增强表格',okText:'确认转换',cancelText:'取消'});
   if(!ok)return;
   result=tableSnippet(ReportPipeTables.promoted(accepted,id||'tbl-'+freshID().slice(0,12)));
  }else{
   if(parsed.overflow?.length){
    const okay=await ReportDialogs.confirm('原表格含有超出表头列数的数据。标准 GFM 显示时会忽略这些列；保存编辑将不再保留被忽略的文字。确认继续吗？',{title:'确认 Markdown 表格数据范围',okText:'已了解，继续保存',cancelText:'取消'});
    if(!okay)return;
   }
   result=ReportPipeTables.stringify(accepted,{newline:parsed.newline,id});
  }
 }else result=tableSnippet(accepted);
  const updated=state.md.slice(0,start)+SourceBlocks.replacement(original,result)+state.md.slice(end);
  changed(updated,'table');
  // This transaction renders immediately. A second debounced render, or
  // restoring scrollTop before diagrams/math regain their height, loses the
  // edited table through browser scroll anchoring. Restore its source anchor
  // only after the complete render, and never over a newer render/document.
  clearTimeout(debounceRender);
  const pending=render(),run=state.rendering;await pending;
  if(state.session!==session||state.md!==updated||state.rendering!==run)return;
  const current=preview.querySelector(`.doc-block[data-start="${start}"]`);
  if(current)scroller.scrollTop+=current.getBoundingClientRect().top-scroller.getBoundingClientRect().top-viewportTop;
}

function markedBlock(token,offset,sourceRaw){
 const records=[];
 const original=sourceRaw??token.raw??'';
 if(token.type==='reportImageGroup'){
  const holder=document.createElement('div');try{holder.append(groupElement(ReportLayout.parseGroup(original)));}
  catch(error){state.renderErrors.push('组图：'+error.message);holder.className='diagram-error';holder.textContent='组图格式错误：'+error.message;}return holder;
 }
 if(token.type==='reportEquation'){
  const eq=ReportEquations.parse(original),item={id:'block'+offset,tex:eq.tex.trim(),raw:original,start:offset,end:offset+original.length,display:true,equationId:eq.id};
  const div=document.createElement('div');div.className='report-equation';if(eq.id)div.dataset.equationId=eq.id;
  div.append(makeMathElement(item));mathRecords.set(item.id,item);const holder=document.createElement('div');holder.append(div);return holder;
 }
 const mathMatch=original.match(/^\s*\$\$\s*\n?([\s\S]*?)\n?\s*\$\$\s*$/);
 if(mathMatch){
  const item={id:'block'+offset,tex:mathMatch[1].trim(),raw:original.trim(),start:offset+original.indexOf('$$'),end:offset+original.lastIndexOf('$$')+2,display:true};
  const div=document.createElement('div');div.appendChild(makeMathElement(item)); mathRecords.set(item.id,item);return div;
 }
 if(token.type==='code'&&String(token.lang||'').trim().toLowerCase()===TABLE_LANG){
  try{const holder=document.createElement('div');holder.append(attachTableCard(renderTableObject(parseTableBlock(original.trim())),original,'enhanced'));return holder;}
  catch(e){state.renderErrors.push('表格：'+e.message);const el=document.createElement('div');el.className='diagram-error';el.textContent='表格数据错误：'+e.message;return el;}
 }
 if(token.type==='code'&&String(token.lang||'').trim().toLowerCase()===FIGURE_LANG){
  try{const holder=document.createElement('div');holder.append(figureElement(parseFigureBlock(original.trim())));return holder;}
  catch(e){state.renderErrors.push('图形对象：'+e.message);const el=document.createElement('div');el.className='diagram-error';el.textContent='图形对象错误：'+e.message;return el;}
 }
 if(token.type==='code'&&String(token.lang||'').trim().toLowerCase()==='mermaid'){
   const card=document.createElement('div');card.className='mermaid-card report-figure-wrap';card.title='双击编辑流程图';card.dataset.mermaid='1';
   const graph=document.createElement('div');graph.className='hrs-mermaid-render';graph.dataset.hrsMermaid='1';graph._mermaidSource=token.text;
   const note=document.createElement('span');note.className='chart-note';note.textContent='Mermaid · 双击编辑';card.append(graph,note);
   const holder=document.createElement('div');holder.appendChild(card);return holder;
 }
 let rendered=original;
 const section=token.type==='heading'?ReportLayout.heading(original,token.depth):null;
 if(section?.id&&section.valid){const frame=SourceMap.textFrame(original,token.depth);rendered=frame.prefix+frame.body+frame.suffix.replace(section.anchor,'');}
 const masked=(token.type==='code')?rendered:maskInlineMath(rendered,records,offset);
 if(token.type==='code'&&window.ReportCodeHighlight){const holder=document.createElement('div');holder.append(ReportCodeHighlight.buildCodeCard(token.text||'',token.lang||''));return holder;}
 const wrapper=document.createElement('div');
 try{wrapper.append(safeMarkdownFragment(marked.parser(SourceBlocks.lexer({},activeLinks).lex(masked),{...marked.defaults,hrsRenderProfile:state.renderProfile})));}catch(e){wrapper.textContent='渲染错误：'+e.message;state.renderErrors.push('Markdown：'+e.message);}
 replaceMathMarkers(wrapper,records);records.forEach(r=>mathRecords.set(r.id,r));
 if(section?.id&&section.valid&&wrapper.firstElementChild)wrapper.firstElementChild.dataset.sectionId=section.id;
 return wrapper;
}
function checkTeX(tex){
 if(/\\(?:href|url|require|includegraphics|htmlClass|htmlId|htmlStyle|htmlData|html)\b/i.test(tex)) throw Error('出于离线安全要求，公式不能使用外部链接或 HTML 扩展命令');
}
// Rendered formula SVGs keyed by display mode + TeX. Each keystroke re-renders
// the preview; unchanged formulas are cloned instead of re-typeset by MathJax.
const mathCache=new Map(),MATH_CACHE_LIMIT=800;
let mathCacheGeneration=0;
function clearDocumentRenderCaches(){
 mathCacheGeneration++;mathCache.clear();ReportMermaid.clearCache();previewImages?.clear();parsedDocument=null;topicFocus=null;pendingTopicPosition=null;
}
async function formulaSVG(tex,display){
 const key=(display?'D':'I')+tex,generation=mathCacheGeneration;
 let svg=mathCache.get(key);
 if(svg){mathCache.delete(key);mathCache.set(key,svg);return svg;}
 const node=await MathJax.tex2svgPromise(tex,{display});
 if(node.querySelector('merror,[data-mml-node="merror"],[data-mjx-error]'))throw Error('LaTeX 语法错误');
 svg=node.querySelector('svg');if(!svg)throw Error('未生成 SVG');
 // An older asynchronous render must not repopulate the next document's cache.
 if(generation===mathCacheGeneration){
  mathCache.set(key,svg);
  if(mathCache.size>MATH_CACHE_LIMIT)mathCache.delete(mathCache.keys().next().value);
 }
 return svg;
}
async function typesetMath(root,isCurrent=()=>true){
 await (window.MathJax?.startup?.promise||Promise.reject(Error('MathJax 尚未加载')));
 let failures=[];
 for (const span of root.querySelectorAll('.markdown-math')){
   if(!isCurrent())break;
   const tex=span.dataset.tex,display=span.dataset.display==='1';
   try{
     checkTeX(tex);
     const svg=await formulaSVG(tex,display);
     span.textContent='';span.appendChild(svg.cloneNode(true));
   }catch(e){span.innerHTML='<code class="math-error">'+escapeHTML(tex)+'</code>';span.title=e.message;failures.push('公式 '+tex.slice(0,22)+'：'+e.message);}
 }
 return failures;
}
let lastTOC=[];
function previewViewportAnchor(){
 const scroller=preview.closest('.page-scroll'),top=scroller.getBoundingClientRect().top;
 const node=[...preview.querySelectorAll(':scope > .doc-block')].find(n=>n.getBoundingClientRect().bottom>top+2);
 return {scroller,top:scroller.scrollTop,node,start:node?+node.dataset.start:0,offset:node?node.getBoundingClientRect().top-top:0,source:positionMap?.source};
}
function restorePreviewViewport(anchor){
 if(!anchor?.node){if(anchor)anchor.scroller.scrollTop=anchor.top;return;}
 let position=anchor.start;
 if(anchor.source!==state.md&&typeof anchor.source==='string'){
  const a=anchor.source,b=state.md;let prefix=0,x=a.length,y=b.length;
  while(prefix<x&&prefix<y&&a[prefix]===b[prefix])prefix++;
  while(x>prefix&&y>prefix&&a[x-1]===b[y-1]){x--;y--;}
  position=position>=x?position+y-x:position>prefix?prefix:position;
 }
 const record=positionMap?.at(Math.min(position,state.md.length));
 const node=record&&preview.querySelector(`[data-map-index="${record.index}"]`);
 if(node)anchor.scroller.scrollTop+=node.getBoundingClientRect().top-anchor.scroller.getBoundingClientRect().top-anchor.offset;
 else anchor.scroller.scrollTop=anchor.top;
}
let renderedKey='',renderContext='';
let parsedDocument=null,topicFocus=null,pendingTopicPosition=null;
function documentModel(source){
 if(parsedDocument?.source===source)return parsedDocument;
 const tokens=marked.lexer(SourceBlocks.normalized(source).text),map=SourceMap.create(source,tokens);
 const catalog=ReportObjectCatalog.indexSource(map);
 for(const entry of catalog.items)if(entry.id&&entry.valid)map.setObjectId(entry.record,entry.id);
 const model={source,tokens,map,notebook:ReportNotebook.index(source,map,tokens,catalog),catalog,notes:ReportNotes.prepare(marked,tokens,{source,records:map.blocks,catalog,map})};
 if(source===state.md)parsedDocument=model;
 return model;
}
function focusTopic(topic,model=documentModel(state.md)){
 if(!topic){topicFocus=null;return;}
 const record=model.map.at(topic.headingStart??topic.start),raw=record?.raw.replace(/(?:\r?\n[ \t]*)+$/,'')||'';
 topicFocus={key:topic.key,source:state.md,start:record?.start??topic.start,end:(record?.start??topic.start)+raw.length,raw};
}
function currentTopic(model){
 if(!topicFocus||state.renderProfile!=='free')return null;
 if(pendingTopicPosition!==null){focusTopic(model.notebook.at(pendingTopicPosition),model);pendingTopicPosition=null;}
 if(topicFocus.source!==state.md){
  try{const next=SourceMap.rebaseUnchanged(state.md,topicFocus.source,topicFocus,topicFocus.raw);focusTopic(model.notebook.at(next.start),model);}
  catch{const record=model.map.at(topicFocus.start);focusTopic(record?.start===topicFocus.start&&record.type==='heading'&&record.token.depth===1?model.notebook.at(record.start):null,model);}
 }
 return model.notebook.topics.find(t=>t.key===topicFocus?.key)||null;
}
function documentViewKey(){return JSON.stringify([state.md,state.view,state.renderProfile,state.renderOptions,state.colorTheme,state.documentId,state.draftId,currentTopic(documentModel(state.md))?.key]);}
function syncSourceNotes(model,topic){
 sourceProjection.setNotes(Array.from(model.notes.definitionRecords.values()).flat().sort((a,b)=>a.start-b.start));
 const panel=$('source-notes'),list=$('source-notes-list'),used=new Set(Array.from(preview.querySelectorAll('[data-hrs-note-key]'),n=>n.dataset.hrsNoteKey));
 const previous=new Map(Array.from(list.children,n=>[n.dataset.rowKey,n])),nodes=[];
 for(const [key,records] of model.notes.definitionRecords){
  if(topic&&!used.has(key))continue;
  records.forEach((record,index)=>{
   const rowKey=key+':'+index;let row=previous.get(rowKey);
   if(!row){
    row=document.createElement('div');row.className='source-note-row';
    const label=document.createElement('button');label.type='button';label.className='source-note-locate';
    label.onclick=()=>locateRange(row._record,{origin:'source'}).catch(e=>toast(e.message));
    const edit=document.createElement('button');edit.type='button';edit.textContent='编辑';edit.className='source-fold-tool';edit.onclick=()=>editBlockSource(row);
    row.append(label,edit);
   }
   Object.assign(row.dataset,{start:String(record.start),end:String(record.end),mapIndex:String(record.index),type:record.type,noteKey:key,rowKey});
   row._record=record;row._sourceDocument=state.md;row._sourceRaw=state.md.slice(record.start,record.end);
   const text='[^'+key+'] '+(records.length>1?'同名定义 '+(index+1)+' · ':'')+record.token.body.replace(/\s+/g,' ').slice(0,100);
   if(row.firstChild.textContent!==text)row.firstChild.textContent=text;nodes.push(row);
  });
 }
 let cursor=list.firstChild;for(const node of nodes){if(node===cursor)cursor=cursor.nextSibling;else list.insertBefore(node,cursor);}
 while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
 panel.hidden=!nodes.length;$('source-notes-title').textContent=(topic?'本专题':'全文')+'注释与参考 · '+nodes.length+' 个定义';
}

function revealSourceNote(record){
 scrollFollow?.suspend();
 const row=Array.from($('source-notes-list').children).find(n=>Number(n.dataset.start)===record.start);
 if(row){$('source-notes').open=true;row.scrollIntoView({block:'nearest'});row.classList.add('navigation-highlight');setTimeout(()=>row.classList.remove('navigation-highlight'),3000);}
}
function syncTopics(model){
 const area=$('topic-controls'),select=$('topic-select');area.hidden=state.renderProfile!=='free';
 const topic=currentTopic(model),signature=JSON.stringify(model.notebook.topics.map(t=>[t.key,t.title]));
 if(select._topicsSignature!==signature){
  const all=document.createElement('option');all.value='';all.textContent='全部专题';select.replaceChildren(all);
  model.notebook.topics.forEach((t,i)=>{const option=document.createElement('option');option.value=t.key;option.textContent=(i+1)+' · '+t.title;select.append(option);});select._topicsSignature=signature;
 }
 // Trailing blank lines belong to this topic too. Clipping to the last
 // non-space token traps the caret at a folded end object after every render.
 select.value=topic?.key||'';sourceProjection.set(topic);syncSourceNotes(model,topic);
}
async function buildDocumentView(source,{focus=null,isCurrent=()=>true,reuse=new Map()}={}){
 const previousErrors=state.renderErrors,previousMath=mathRecords,previousReferences=referenceRecords,previousLinks=activeLinks;
 state.renderErrors=[];mathRecords=new Map();referenceRecords=new WeakMap();
 let stagedResult,nextMapResult,modelResult,headingsResult,pipeResult,profileResult,notesMath,references,errors;
 try{
 const frag=document.createDocumentFragment();
 const model=documentModel(source),{tokens,map:nextMap,notebook,catalog}=model;
 activeLinks=tokens.links;
 const notes=model.notes,headings=[];
 const selected=focus?notebook.topics.find(t=>t.key===focus):null;
 if(focus&&!selected)throw Error('专题选择已过期，请重新选择');
 const gaps=new Map(notebook.gaps.map(g=>[g.after,g]));
 const shown=nextMap.blocks.filter(r=>!selected||selected.start<=r.start&&r.start<selected.end);
 const profilePlan=ReportProfile.plan(source,state.renderProfile,nextMap.blocks,state.renderOptions);
 const headingNumbers=new Map(profilePlan.headings.map(h=>[h.start,h.number])),abstractStarts=new Set(profilePlan.abstracts.map(a=>a.start));
  const nextPipeIndex=[];let pipeCaptionConsumed=-1;
 for (const record of shown){
   if(record.type==='hrsFootnoteDef')continue;
   if(record.index===pipeCaptionConsumed)continue;
   const {token,raw,start:pos,end,index:id}=record;
   const block=document.createElement('div');block.className='doc-block';block.id='docblock-'+id;block.dataset.mapIndex=String(id);
   block.dataset.start=String(pos);block.dataset.end=String(end);block.dataset.type=token.type;
   block._sourceRaw=source.slice(pos,end); // validate stale preview ranges before any mutation
   block._sourceDocument=source;
   let inner;
   if(token.type==='table'){
    let finish=end;
    const sibling=nextMap.blocks[id+1];
    // Quarto caption appears in a separate Marked paragraph when a blank line
    // separates it from the pipe table. Do not render that paragraph twice.
    if(sibling?.type==='paragraph'&&ReportPipeTables.parseCaption(sibling.raw.trim())){
     finish=sibling.end;pipeCaptionConsumed=sibling.index;
    }
    const tableSource=source.slice(pos,finish);
    try{
     const parsed=ReportPipeTables.parseRaw(tableSource),model=parsed.model;
     inner=document.createElement('div');const node=attachTableCard(renderTableObject(model),tableSource,'gfm-pipe');node.dataset.pipeTable='1';
     if(!parsed.id)delete node.dataset.tableId;
     inner.append(node);
     block.dataset.pipeTable='1';block.dataset.end=String(finish);
     block._sourceRaw=tableSource;block._pipeModel=parsed;
     if(parsed.id)nextMap.setObjectId(record,parsed.id);
     nextPipeIndex.push({id:parsed.id,caption:parsed.caption,start:pos,end:finish});
    }catch(error){state.renderErrors.push('Markdown 表格：'+error.message);inner=document.createElement('div');inner.className='diagram-error';inner.textContent='Markdown 表格格式错误：'+error.message;}
   }else if(reuse.has(id)){
    const old=reuse.get(id);inner=document.createElement('div');
    inner.append(...Array.from(old.childNodes,n=>n.cloneNode(true)));block._reuseExisting=old;
   }else inner=markedBlock(token,pos,block._sourceRaw);
   while(inner.firstChild)block.appendChild(inner.firstChild);
   const tasks=SourceMap.taskRanges(source,record,marked);
   const inputs=[...block.querySelectorAll('li > input[type="checkbox"],li > p > input[type="checkbox"]')];
   if(tasks.length&&inputs.length===tasks.length&&inputs.every((input,i)=>input.checked===tasks[i].checked))inputs.forEach((input,i)=>{
    input._taskRange={...tasks[i],source:source};input.disabled=state.saving;
    input.classList.add('hrs-task-checkbox');input.setAttribute('aria-label','完成任务：'+input.closest('li').textContent.trim().slice(0,160));
   });
   const simple=token.type==='paragraph'||token.type==='heading';
   // Block math is edited through its equation modal, not as ordinary prose.
  const visual= state.view!=='reading' && simple && !ReportSafeHTML.hasHTML(token) && !/^\s*\$\$/.test(raw) && block.childElementCount===1 && ['P','H1','H2','H3','H4','H5','H6'].includes(block.firstElementChild?.tagName);
   block.dataset.editable=visual?'1':'0';
   if(visual)block.firstElementChild.dataset.blockEditor='1';
   if(token.type==='heading'){
    const number=headingNumbers.get(pos),heading=block.firstElementChild;
    if(number&&heading){
     const prefix=document.createElement('span');prefix.className='hrs-heading-number';prefix.contentEditable='false';prefix.textContent=number+' ';heading.prepend(prefix);
    }
   }
   if(abstractStarts.has(pos))block.dataset.outputRole='abstract';
   if(token.type==='heading')headings.push({level:token.depth||1,text:block.firstElementChild?.textContent||token.text||'',id:block.id,start:pos,end});
   frag.appendChild(block);
   const gap=gaps.get(pipeCaptionConsumed===id+1?pipeCaptionConsumed:id);
   if(gap&&state.renderProfile==='free'&&state.renderOptions.preserve_blank_lines){
    const spacer=document.createElement('div');spacer.className='hrs-blank-space';spacer.setAttribute('aria-hidden','true');
    spacer.style.setProperty('--hrs-blank-lines',gap.lines);frag.append(spacer);
   }
 }
  const staged=document.createElement('article');staged.className=preview.className;
  staged.dataset.hrsRenderProfile=state.renderProfile;staged.dataset.hrsShowObjectNumbers=preview.dataset.hrsShowObjectNumbers;
  staged.append(frag);
  const previousReferences=referenceRecords;referenceRecords=new WeakMap();
  staged._sourceObjectCatalog=catalog;numberObjects(staged,nextMap);const nextReferences=referenceRecords;referenceRecords=previousReferences;
  state.renderErrors.push(...ReportNotes.finalize(staged,notes,{render:body=>markedBlock({type:'paragraph',raw:body},0,body)}));
  const nextMath=mathRecords;mathRecords=previousMath;
  staged.querySelectorAll('.report-table-wrap').forEach(ReportObjectCatalog.tableHeading);
  ReportLinks.decorate(staged);
  previewImages?.prepare(staged);
  stagedResult=staged;nextMapResult=nextMap;modelResult=model;headingsResult=headings;pipeResult=nextPipeIndex;profileResult=profilePlan;
  notesMath=nextMath;references=nextReferences;errors=state.renderErrors;
 }finally{state.renderErrors=previousErrors;mathRecords=previousMath;referenceRecords=previousReferences;activeLinks=previousLinks;}
 const diagramFailures=await ReportMermaid.renderAll(stagedResult,isCurrent);if(!isCurrent())return null;
 errors.push(...diagramFailures);errors.push(...await typesetMath(stagedResult,isCurrent));if(!isCurrent())return null;
 return {article:stagedResult,map:nextMapResult,model:modelResult,headings:headingsResult,pipe:pipeResult,profile:profileResult,math:notesMath,references,errors};
}
async function render(){
 if(state.visualFocused||captionEditor)return;
 clearTimeout(debounceRender);
 const sourceSnapshot=state.md,model=documentModel(sourceSnapshot),topic=currentTopic(model);
 const key=documentViewKey();
 if(renderedKey===key&&positionMap?.source===sourceSnapshot)return;
 documentSearch?.invalidate();scrollFollow?.suspend();const run=++state.rendering;
 const context=JSON.stringify([state.view,state.renderProfile,state.renderOptions,state.colorTheme,state.documentId,state.draftId,topic?.key]);
 const reuse=ReportPreviewCommit.reusable(preview,model,positionMap,context===renderContext);
 const view=await buildDocumentView(sourceSnapshot,{focus:topic?.key,isCurrent:()=>run===state.rendering,reuse});
 if(!view||run!==state.rendering||sourceSnapshot!==state.md||state.visualFocused||captionEditor)return;
 const anchor=previewViewportAnchor(),staged=view.article;
 ReportPreviewCommit.commit(preview,staged);renderContext=context;preview._sourceObjectCatalog=view.model.catalog;
 preview.dataset.hrsRenderProfile=staged.dataset.hrsRenderProfile;preview.dataset.hrsShowObjectNumbers=staged.dataset.hrsShowObjectNumbers;preview.dataset.hrsShowEquationNumbers=staged.dataset.hrsShowEquationNumbers;
 positionMap=view.map;sourceMapCache=null;pipeTableIndex=view.pipe;referenceRecords=view.references;mathRecords=view.math;state.renderErrors=view.errors;
 const headingNumbers=new Map(view.profile.headings.map(h=>[h.start,h.number]));
 lastTOC=view.model.map.blocks.filter(r=>r.type==='heading').map(r=>({level:r.token.depth,text:(headingNumbers.get(r.start)?headingNumbers.get(r.start)+' ':'')+ReportNotebook.title(r.token),start:r.start,end:r.end,id:'docblock-'+r.index}));
 renderedKey=key;buildTOC(lastTOC);syncTopics(view.model);updateStats();prepareVisualBlocks();restorePreviewViewport(anchor);previewImages?.committed();
 $('bottom-right').title=view.profile.diagnostics.map(d=>d.message).join('；');
 $('bottom-right').textContent=state.renderErrors.length?'⚠ '+state.renderErrors.length+' 处需要处理':view.profile.diagnostics.length?'⚠ '+view.profile.diagnostics.length+' 项工程输出提醒（文档检查可查看）':'离线渲染 · 无 CDN · '+preview.querySelectorAll('svg').length+' 个 SVG';
 $('preview-hint').textContent=topic?'当前专题：'+topic.title:state.view==='reading'?'单栏阅读；双击图表可打开编辑窗口':'单击定位源码；双击正文或对象编辑';
 $('follow-scroll').closest('label').hidden=state.view!=='split';documentSearch?.refresh();
}
function buildTOC(headings){
 const toc=$('toc');
 if(!headings.length){if(toc.textContent!=='尚无 Markdown 标题')toc.textContent='尚无 Markdown 标题';return;}
 const previous=new Map(Array.from(toc.querySelectorAll('a'),n=>[n.getAttribute('href'),n])),nodes=[];
 for(const h of headings){
  const href='#'+h.id,a=previous.get(href)||document.createElement('a');
  a._heading=h;a.href=href;a.className='level-'+Math.min(6,h.level);
  const text=h.text.replace(/\$[^$]*\$/g,'∑').slice(0,46);if(a.textContent!==text)a.textContent=text;
  if(!a.onclick)a.onclick=e=>{e.preventDefault();locateRange(a._heading,{origin:'toc'}).catch(error=>toast(error.message));};nodes.push(a);
 }
 let cursor=toc.firstChild;for(const node of nodes){if(node===cursor)cursor=cursor.nextSibling;else toc.insertBefore(node,cursor);}
 while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
}

function clearPreviewHighlight(){clearTimeout(navigationTimer);preview.querySelectorAll('.navigation-highlight').forEach(el=>el.classList.remove('navigation-highlight'));}
function invalidateChecks(){
 if(!checks||checks.source===state.md)return;
 $('problems-summary').textContent='结果已过期，请重新检查';
 $('bottom-left').textContent='文稿已修改，检查结果已过期；请重新检查';$('bottom-left').title=$('bottom-left').textContent;
 $('problem-list').querySelectorAll('button').forEach(button=>{button.disabled=true;button.classList.remove('selected');});
}
async function locateRange(range,{origin='problem',detail=''}={}){
 scrollFollow?.suspend();
 const snapshot=state.md;
 if((['problem','source'].includes(origin)||origin==='toc'&&state.view!=='reading')&&state.view!=='split')switchView('split');
 if(positionMap?.source!==state.md){if(state.visualFocused)commitFocusedVisual();await render();}
 SourceMap.assertRange(state.md,range,null,snapshot);
 if(positionMap?.source!==state.md)throw Error('预览正在更新，请稍候定位');
 const sourceRecord=positionMap.at(range.start),isNote=sourceRecord?.type==='hrsFootnoteDef',visibleNote=isNote&&Array.from(preview.querySelectorAll('[data-hrs-note-key]')).some(n=>n.dataset.hrsNoteKey===sourceRecord.token.key);
 if(topicFocus&&!visibleNote){
  const model=documentModel(state.md),target=model.notebook.at(range.start);
  if(isNote){focusTopic(null,model);await render();}
  else if(target&&target.key!==topicFocus.key){focusTopic(target,model);await render();}
 }
 const record=positionMap.at(range.start),block=record?.type==='hrsFootnoteDef'?Array.from(preview.querySelectorAll('[data-hrs-note-key]')).find(n=>n.dataset.hrsNoteKey===record.token.key):record?preview.querySelector(`[data-map-index="${record.index}"]`):null;
 if(state.view!=='reading'){
  const limit=sourceProjection.range;
  if(isNote&&limit)revealSourceNote(sourceRecord);
  else editor.highlightRange(range.start,range.end,{select:!['preview','reference'].includes(origin)});
 }
 clearPreviewHighlight();if(block){
  block.classList.add('navigation-highlight');
  if(origin!=='preview'){
   // Scroll only this pane. Two simultaneous scrollIntoView operations can
   // cancel each other through shared ancestors in Edge.
   const scroller=preview.closest('.page-scroll'),target=block.getBoundingClientRect(),viewport=scroller.getBoundingClientRect();
   scroller.scrollTo({top:scroller.scrollTop+target.top-viewport.top-(scroller.clientHeight-target.height)/2,behavior:'instant'});
  }
 }
 navigationTimer=setTimeout(clearPreviewHighlight,3000);
 if(detail){$('bottom-left').textContent=detail;$('bottom-left').title=detail;clearTimeout(toastTimer);$('toast').classList.remove('show');}
}
async function locateFromSource(position){
 if(state.visualFocused)commitFocusedVisual();if(positionMap?.source!==state.md)await render();
 const record=positionMap?.at(position);if(record)await locateRange(record,{origin:'source'});
}
function locatePreview(block){
 if(positionMap?.source!==state.md||!block.isConnected||block._sourceDocument!==state.md){if(block!==state.visualFocused){toast('预览正在更新，请稍候重新定位');scheduleRender();}return;}
 const record=positionMap.blocks[+block.dataset.mapIndex];if(record)locateRange(record,{origin:'preview'}).catch(error=>toast(error.message));
}
function toMDInline(node){
 if(node.nodeType===Node.TEXT_NODE)return (node.nodeValue||'').replace(/([\\*_`[\]])/g,'\\$1');
 if(node.nodeType!==Node.ELEMENT_NODE)return '';
 const e=node,tag=e.tagName;
 if(e.classList.contains('hrs-heading-number'))return '';
 if(tag==='INPUT'&&e.type==='checkbox')return '';
 if(tag==='SUP'&&e.querySelector('[data-hrs-footnote-ref]'))return '[^'+e.querySelector('[data-hrs-footnote-ref]').dataset.hrsFootnoteRef+']';
 const reference=referenceRecords.get(e);if(reference)return reference.raw;
 if(e.classList.contains('markdown-math'))return e.dataset.raw|| (e.dataset.display==='1'?'$$'+e.dataset.tex+'$$':'$'+e.dataset.tex+'$');
 const inner=()=>Array.from(e.childNodes).map(toMDInline).join('');
 if(e.dataset.hrsHighlight==='markdown')return '=='+inner()+'==';
 if(tag==='STRONG'||tag==='B')return '**'+inner()+'**';
 if(tag==='EM'||tag==='I')return '*'+inner()+'*';
 if(tag==='DEL'||tag==='S')return '~~'+inner()+'~~';
 if(tag==='CODE')return '`'+e.textContent.replace(/`/g,'')+'`';
 if(tag==='BR')return '  \n';
 if(tag==='MARK'){
  const color=e.style.backgroundColor||highlightColors[ReportSettings.highlights.default];
  return '<mark style="background-color:'+escapeHTML(color)+'">'+inner()+'</mark>';
 }
 if(tag==='A')return '['+inner()+']('+e.getAttribute('href')+')';
 if(tag==='DIV')return inner()+'\n';
 return inner();
}
function currentBlockRange(block,map=null){
 if(!block?.isConnected)throw Error('原预览块已更新，请重新打开编辑');
 if(block._sourceDocument!==state.md){
  const oldStart=+block.dataset.start,next=rebaseDisplayedRange(block._sourceDocument,{start:oldStart,end:+block.dataset.end},block._sourceRaw);
  const record=(map||currentSourceMap()).at(next.start);
  if(!record||record.start!==next.start||record.type!==block.dataset.type)throw Error('该处的 Markdown 结构已变化，请等待预览刷新');
  block.dataset.start=String(next.start);block.dataset.end=String(next.end);block._sourceDocument=state.md;
  for(const target of block.querySelectorAll('[data-block-editor]'))if(target._listFrame){target._listFrame.start+=next.start-oldStart;target._listFrame.end+=next.start-oldStart;}
 }
 const range={start:+block.dataset.start,end:+block.dataset.end};
 return SourceMap.assertRange(state.md,range,block._sourceRaw,block._sourceDocument);
}
function currentSourceMap(){
 if(positionMap?.source===state.md)return positionMap;
 if(sourceMapCache?.source===state.md&&sourceMapCache.profile===state.renderProfile)return sourceMapCache.map;
 const map=SourceMap.create(state.md,marked.lexer(SourceBlocks.normalized(state.md).text));
 sourceMapCache={source:state.md,profile:state.renderProfile,map};return map;
}
function rebaseDisplayedRange(snapshot,range,raw){
 if(snapshot===state.md)return SourceMap.assertRange(state.md,range,raw,snapshot);
 let index=-1;for(let i=displayChanges.length-1;i>=0;i--)if(displayChanges[i].before===snapshot){index=i;break;}
 let next={...range},current=snapshot;
 if(index>=0)for(const change of displayChanges.slice(index)){
  if(change.before!==current)break;
  next=SourceMap.rebaseUnchanged(change.after,current,next,raw);current=change.after;
  if(current===state.md)return next;
 }
 return SourceMap.rebaseUnchanged(state.md,current,next,raw);
}
// A selection is writable only when this exact DOM serializes to the source
// frame. Formatting delimiters are counted, not guessed from visible text.
function syncPreviewSelection(){
 if(state.view!=='split'||state.saving)return false;
 const selection=window.getSelection();if(!selection?.rangeCount)return false;
 const parent=node=>node?.nodeType===1?node:node?.parentElement;
 const target=parent(selection.anchorNode)?.closest('[data-block-editor]'),block=target?.closest('.doc-block');
 if(!target||!preview.contains(target)||!target.contains(selection.focusNode))return false;
 const frame=target._visualFrame,body=[...target.childNodes].map(toMDInline).join('');
 if(!frame||body!==frame.body)return false;
 const serial=node=>toMDInline(node);
 function offset(node,at,bias){
  function find(element,base){
   if(element===node){
    if(element.nodeType===Node.TEXT_NODE)return base+serial(document.createTextNode(element.nodeValue.slice(0,at))).length;
    const children=[...element.childNodes],inner=children.map(serial).join(''),all=serial(element),head=all.indexOf(inner);
    return base+Math.max(0,head)+children.slice(0,at).map(serial).join('').length;
   }
   if(element.nodeType!==Node.ELEMENT_NODE||!element.contains(node))return null;
   const children=[...element.childNodes],inner=children.map(serial).join(''),all=serial(element),head=all.indexOf(inner);
   if(element.matches('.markdown-math,[data-xref-raw]')||element.tagName==='SUP'&&element.querySelector('[data-hrs-footnote-ref]')||head<0)return base+(bias==='end'?all.length:0);
   let cursor=base+head;for(const child of children){const result=find(child,cursor);if(result!==null)return result;cursor+=serial(child).length;}return null;
  }
  // The root's frame owns its heading/list markers; they are outside body.
  let cursor=0;for(const child of target.childNodes){const result=find(child,cursor);if(result!==null)return result;cursor+=serial(child).length;}
  return node===target?[...target.childNodes].slice(0,at).map(serial).join('').length:null;
 }
 const range=selection.getRangeAt(0),a=offset(range.startContainer,range.startOffset,'start'),b=offset(range.endContainer,range.endOffset,'end');
 if(a===null||b===null)return false;
 const start=target._listFrame?.start??(+block.dataset.start+frame.prefix.length);
 const sourceOffset=value=>body.slice(0,value).replace(/\n/g,frame.newline).length;
 const old=block._sourceDocument,oldRange={start:start+sourceOffset(a),end:start+sourceOffset(b)};
 let next;try{next=rebaseDisplayedRange(old,oldRange,old.slice(oldRange.start,oldRange.end));}catch{return false;}
 if(currentSourceMap().at(next.start)?.type!==block.dataset.type)return false;
 sourceActions?.clear();if(editor.selectionStart!==next.start||editor.selectionEnd!==next.end)editor.setSelectionRange(next.start,next.end);
 return true;
}
function prepareVisualBlocks(){
 if(state.view==='reading')return;
 for(const block of preview.querySelectorAll('.doc-block[data-type="list"]')){
  const record=positionMap?.blocks[+block.dataset.mapIndex];if(!record)continue;
  const frames=SourceMap.listFrames(state.md,record,marked),items=[...block.querySelectorAll('li')];
  if(frames.length!==items.length)continue;
  items.forEach((item,index)=>{
   let target=item.querySelector(':scope > p');
   if(!target){target=document.createElement('span');target.className='list-inline-editor';
    const nodes=[];for(const node of [...item.childNodes]){if(['UL','OL'].includes(node.nodeName))break;if(node.nodeName!=='INPUT')nodes.push(node);}
    target.append(...nodes);item.insertBefore(target,item.querySelector(':scope > ul,:scope > ol'));
    if(item.querySelector(':scope > input')&&target.firstChild?.nodeType===Node.TEXT_NODE&&target.firstChild.nodeValue.startsWith(' '))target.firstChild.nodeValue=target.firstChild.nodeValue.slice(1);
   }
   const frame=frames[index];if(Array.from(target.childNodes).map(toMDInline).join('')!==frame.body)return;
   target.dataset.blockEditor='1';target._listFrame=frame;block.dataset.editable='1';
  });
 }
 for(const block of preview.querySelectorAll('.doc-block')){
  for(const target of block.querySelectorAll('[data-block-editor]')){
  const level=target.tagName.match(/^H([1-6])$/),frame=target._listFrame?{prefix:'',body:target._listFrame.body,suffix:'',newline:state.md.includes('\r\n')?'\r\n':'\n'}:SourceMap.textFrame(block._sourceRaw,level?+level[1]:null);
  const serialized=Array.from(target.childNodes).map(toMDInline).join('');
  if(!frame||serialized!==frame.body){target.removeAttribute('data-block-editor');block.dataset.editable='0';block.title='双击编辑原始 Markdown 块';continue;}
  target._visualFrame=frame;target._visualHTML=target.innerHTML;target.classList.add('preview-text-editor');target.tabIndex=0;
  target.contentEditable='false';target.title='双击编辑文字；修改写回同一份 Markdown';
  target.addEventListener('focus',()=>{if(target.isContentEditable&&!state.saving)beginVisual(block,false,target);});
  target.addEventListener('input',event=>{state.visualPending=true;if(!event.isComposing&&!block._composing)commitVisual(block,{typing:true});});
  target.addEventListener('compositionstart',()=>{block._composing=true;});
  target.addEventListener('compositionend',()=>{block._composing=false;commitVisual(block,{typing:true});});
  target.addEventListener('blur',()=>{if(state.visualTarget===target){commitVisual(block);state.visualFocused=null;state.visualTarget=null;target.contentEditable='false';scheduleRender();}});
  target.addEventListener('beforeinput',event=>{if(event.inputType==='insertParagraph'){
   event.preventDefault();if(level)toast('标题保持一行；长标题会自动换行显示');
   else if(target._listFrame)insertListItem(target).catch(error=>toast(error.message));
   else document.execCommand('insertLineBreak');
  }});
  target.addEventListener('paste',event=>{
   event.preventDefault();const text=event.clipboardData?.getData('text/plain')||'';
   if((level||target._listFrame)&&/[\r\n]/.test(text)){toast('此处编辑一行内容；多行结构可在 Markdown 中粘贴');return;}
   document.execCommand('insertText',false,text);
  });
  target.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&['z','y'].includes(event.key.toLowerCase())){
   event.preventDefault();event.stopPropagation();commitFocusedVisual();if(event.key.toLowerCase()==='y'||event.shiftKey)redo();else undo();
  }});
  }
 }
}
function setPreviewEditingEnabled(enabled){
 for(const target of preview.querySelectorAll('[data-block-editor]'))target.contentEditable='false';
 for(const input of preview.querySelectorAll('.hrs-task-checkbox'))input.disabled=!enabled;
}
async function insertListItem(target){
 if(!syncPreviewSelection())return toast('列表位置正在更新，请稍后再换行');
 const marker=target._listFrame.marker.replace(/\[[ xX]\]/,'[ ]').replace(/(\d+)([.)])([ \t]+)$/,(all,n,ending,space)=>(Number(n)+1)+ending+space);
 const newline=target._visualFrame.newline,session=state.session;
 commitFocusedVisual();insertAtSelection(newline+marker);
 const position=editor.selectionEnd,snapshot=state.md;clearTimeout(debounceRender);await render();
 if(state.md!==snapshot||state.session!==session)return;
 const next=[...preview.querySelectorAll('[data-block-editor]')].find(node=>node._listFrame&&node._listFrame.start<=position&&position<=node._listFrame.end);
 if(next){beginVisual(next.closest('.doc-block'),true,next);const range=document.createRange();range.selectNodeContents(next);range.collapse(true);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);}
}
function beginVisual(block,focus=true,target=null){
 if(state.view==='reading')return;
 if(state.saving)return toast('正式保存中，请稍后编辑');
 target=target||block.querySelector('[data-block-editor]');if(!target)return;
 try{currentBlockRange(block);}catch(e){toast(e.message);scheduleRender();return;}
 if(state.visualFocused&&(state.visualFocused!==block||state.visualTarget!==target))commitFocusedVisual();
 const selection=window.getSelection(),saved=focus&&selection?.rangeCount&&target.contains(selection.anchorNode)&&target.contains(selection.focusNode)?selection.getRangeAt(0).cloneRange():null;
 state.visualFocused=block;state.visualTarget=target;state.selectedBlock=block;target.contentEditable='true';
 if(focus){target.focus({preventScroll:true});if(saved){selection.removeAllRanges();selection.addRange(saved);}}
}
function commitVisual(block,{typing=false}={}){
 if(!block||state.view!=='split')return;
 const target=state.visualTarget&&block.contains(state.visualTarget)?state.visualTarget:block.querySelector('[data-block-editor]'),frame=target?._visualFrame;if(!target||!frame)return;
 if(state.saving){state.visualPending=false;return;}
 let range;try{range=currentBlockRange(block);}catch(e){state.visualPending=false;toast(e.message);scheduleRender();return;}
 if(target.innerHTML===target._visualHTML){state.visualPending=false;updateDirty();return;}
 let inline=Array.from(target.childNodes).map(toMDInline).join('');
 if(!inline)inline=' ';
 if(target.tagName==='P'||target._listFrame)inline=inline.replace(/^( {0,3})([#>]|[-+](?=\s)|\d+[.)](?=\s))/gm,(_,space,marker)=>space+(marker.length>1?marker.slice(0,-1)+'\\'+marker.slice(-1):'\\'+marker));
 const text=inline.replace(/\r?\n/g,frame.newline),item=target._listFrame;
 const newRaw=item?block._sourceRaw.slice(0,item.start-range.start)+text+block._sourceRaw.slice(item.end-range.start):frame.prefix+text+frame.suffix;
 state.visualPending=false;
 if(newRaw!==block._sourceRaw){
  changed(state.md.slice(0,range.start)+newRaw+state.md.slice(range.end),typing?'visual-typing:'+block.id:'visual');
  if(item){const delta=text.length-(item.end-item.start);for(const node of block.querySelectorAll('[data-block-editor]')){const f=node._listFrame;if(f&&f!==item&&f.start>=item.end){f.start+=delta;f.end+=delta;}}item.end=item.start+text.length;item.body=text;}
  block.dataset.end=String(range.start+newRaw.length);block._sourceRaw=newRaw;block._sourceDocument=state.md;target._visualFrame={...frame,body:inline};
 }
 target._visualHTML=target.innerHTML;updateDirty();
}
function switchView(view){
 if(!['split','source','reading'].includes(view))return;
 scrollFollow?.suspend();
 if(state.visualFocused){commitFocusedVisual();}
 state.view=view;
 $('edit-layout').className='edit-layout '+view;
 document.querySelectorAll('.view-mode').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
 editor.requestMeasure();
  return render();
}
function sourceEditRequested(){
 if(state.view!=='reading')return false;
 switchView('split');toast('已切换到分屏；请先在 Markdown 中选择文字或指定插入位置，再执行编辑');return true;
}
function insertAtSelection(text,bookmark=null){
 scrollFollow?.suspend();
 if(state.saving)return toast('正式保存过程中，请稍后插入');
 if(state.selectedBlock&&!state.selectedBlock.isConnected)state.selectedBlock=null;
 if(state.view==='reading'&&!bookmark&&sourceEditRequested())return;
 const a=bookmark?.start??editor.selectionStart,b=bookmark?.end??editor.selectionEnd;
 const scrollTop=editor.scrollTop,scrollLeft=editor.scrollLeft;
 const scroller=$('preview-pane').querySelector('.page-scroll'),previewScroll=scroller.scrollTop;
 const oldWindowY=window.scrollY,oldWindowX=window.scrollX;
 editor.setRangeText(text,a,b,'end');
 changed(editor.value,'insert',true);
 editor.focus({preventScroll:true});
 editor.scrollTop=scrollTop;editor.scrollLeft=scrollLeft;
 scroller.scrollTop=previewScroll;
 if(window.scrollY!==oldWindowY||window.scrollX!==oldWindowX)window.scrollTo(oldWindowX,oldWindowY);
}
function insertStyledList(style){
 if(sourceEditRequested())return;
 if(state.saving)return toast('正式保存中，请稍后插入列表');
 const sel=editor.value.slice(editor.selectionStart,editor.selectionEnd);
 insertAtSelection(ReportListStyles.listSnippet(style,sel));
}
function insertInlineMath(){
 if(sourceEditRequested())return;
 if(state.saving)return toast('正式保存中，稍后再插入公式');
 const start=editor.selectionStart,end=editor.selectionEnd;
 let result;
 try{result=ReportInlineMath.inlineSnippet(editor.value.slice(start,end));}
 catch(error){return toast(error.message);}
 insertAtSelection(result.markdown);
 // Select only the TeX body, leaving surrounding $ delimiters untouched.
 editor.setSelectionRange(start+result.selectionStart,start+result.selectionEnd);
}
const highlightColors=Object.fromEntries(ReportSettings.highlights.choices.map(c=>[c.id,c.color]));
function insertHighlight(color=ReportSettings.highlights.default){
 if(sourceEditRequested())return;
 if(state.renderProfile!=='free')return toast('高亮属于自由笔记；工程报告保留文字，不使用彩色装饰');
 if(state.saving)return toast('保存中，请稍后高亮');
 const mapped=syncPreviewSelection();if(mapped)commitFocusedVisual();
 const selection=mapped?null:window.getSelection(),node=selection?.anchorNode;
 const block=(node?.nodeType===1?node:node?.parentElement)?.closest('.doc-block');
 if(block&&preview.contains(block)&&!selection.isCollapsed){
  if(!block||!preview.contains(block)||!block.contains(selection.focusNode)||selection.isCollapsed||block.dataset.editable!=='1')return toast('请选中同一正文段落中的文字，或在 Markdown 中选择源码');
  const mark=document.createElement(color==='clear'?'span':'mark');if(color!=='clear')mark.style.backgroundColor=highlightColors[color];
  const range=selection.getRangeAt(0);mark.append(range.extractContents());range.insertNode(mark);
  // Preserve the existing paragraph frame, object refs and derived-heading
  // exclusions through the established visual serializer and history path.
  commitVisual(block);state.visualFocused=null;state.visualPending=false;scheduleRender();return;
 }
 const a=editor.selectionStart,b=editor.selectionEnd,text=editor.value.slice(a,b)||'重点文字';
 if(color==='clear'){
  const result=ReportNotes.clearHighlight(editor.value,a,b,marked);
  if(!result)return toast('请选择高亮文字或将光标放在高亮文字内');
  insertAtSelection(result.text,{start:result.from,end:result.to});return;
 }
 const plain=text.replace(/^==([\s\S]*)==$/,'$1').replace(/^<mark\b[^>]*>([\s\S]*)<\/mark>$/i,'$1');
 const value=color===ReportSettings.highlights.default?'=='+plain+'==':'<mark style="background-color:'+highlightColors[color]+'">'+plain+'</mark>';
 insertAtSelection(value,{start:a,end:b});
}
async function insertFootnote(){
 if(sourceEditRequested())return;
 if(state.saving)return;commitSource();commitFocusedVisual();
 const source=state.md,session=state.session,position=editor.selectionEnd;
 let field;
 const body=await modal({title:'插入脚注说明',kicker:'引用 · 脚注',note:'生成当前位置的脚注引用和文末定义。Word 导出为原生脚注；表题中也可使用同一引用。',body:outer=>{field=document.createElement('textarea');field.rows=4;field.placeholder='脚注说明';outer.append(field);},onOk:()=>{const value=field.value.trim();if(!value)throw Error('请填写脚注说明');return value;},okText:'插入脚注'});
 if(!body)return;if(state.session!==session||source!==state.md)return toast('文稿已变化，请重新插入脚注');
 let number=1;while(new RegExp('\\[\\^fn'+number+'\\]').test(source))number++;
 const key='fn'+number,newline=source.includes('\r\n')?'\r\n':'\n';
 const next=source.slice(0,position)+'[^'+key+']'+source.slice(position)+newline+newline+'[^'+key+']: '+body.replace(/\r?\n/g,newline+'    ')+newline;
 changed(next,'insert-footnote');editor.setSelectionRange(position+key.length+3);editor.focus();
}
function insertCommand(type){
 if(sourceEditRequested())return;
 const selection=window.getSelection(),previewIntent=selection?.anchorNode&&preview.contains(selection.anchorNode);
 if(syncPreviewSelection())commitFocusedVisual();
 else if(previewIntent)return toast('请在同一正文段落或列表项内选择文字；复杂布局可在 Markdown 中定位后插入');
 const sel=editor.value.slice(editor.selectionStart,editor.selectionEnd);
 const snippets={h1:'\n# 一级标题\n',h2:'\n## 二级标题\n',h3:'\n### 三级标题\n',h4:'\n#### 四级标题\n',h5:'\n##### 五级标题\n',h6:'\n###### 六级标题\n',bold:sel?'**'+sel+'**':'**加粗文字**',italic:sel?'*'+sel+'*':'*斜体文字*',list:'\n- 第一项\n- 第二项\n',table:'\n| 项目 | 结果 |\n| :--- | ---: |\n| 样本 A | 12.5 |\n| 样本 B | 14.2 |\n',code:'\n```python\nprint("hello")\n```\n'};
 if(type==='math'){
  const id='eq-'+freshID().slice(0,12);
  insertAtSelection('\n'+ReportEquations.snippet('\\eta=\\frac{\\Delta L}{L_0}',id)+'\n');
  toast('已插入块公式；编号由文档的「公式编号」设置控制');return;
 }
 if(type==='inline-math'){insertInlineMath();return;}
 if(type==='highlight'){insertHighlight();return;}
 if(type==='footnote'){$('ref-picker').open=false;insertFootnote().catch(e=>toast(e.message));return;}
 if(type==='table'){insertTableDialog();return;}
 if(type==='figure'){insertFigureDialog();return;}
 if(type==='image'){$('file-image').click();return;}
 if(type==='image-group'){insertGroup().catch(error=>toast(error.message));return;}
 if(type==='section-ref'){insertSectionReference().catch(error=>toast(error.message));return;}
 if(type==='object-ref'){insertObjectReference().catch(error=>toast(error.message));return;}
 if(snippets[type])insertAtSelection(snippets[type]);
}
function modal({title,kicker='编辑',note='',wide=false,body,onOk,okText='应用修改',cancelText='取消',extraText=null}){
 return new Promise(resolve=>{
  const layer=$('modal-layer'),windowEl=layer.querySelector('.modal-window'),previous=document.activeElement;
  layer.hidden=false;windowEl.classList.toggle('wide',!!wide);$('modal-title').textContent=title;$('modal-kicker').textContent=kicker;$('modal-note').textContent=note;
  $('modal-body').replaceChildren();body($('modal-body'));
  const ok=$('modal-ok'),cancel=$('modal-cancel'),close=$('modal-close'),extra=$('modal-extra');
  ok.textContent=okText;cancel.textContent=cancelText;extra.hidden=!extraText;if(extraText)extra.textContent=extraText;
  ok.disabled=false;
  const finish=(val)=>{layer.hidden=true;ok.disabled=false;ok.onclick=null;cancel.onclick=null;close.onclick=null;extra.onclick=null;extra.hidden=true;document.removeEventListener('keydown',keys);
   if(previous&&previous.isConnected&&typeof previous.focus==='function'&&!previous.closest?.('#modal-layer'))previous.focus({preventScroll:true});
   resolve(val);};
  async function submit(){try{const v=await onOk();if(v!==false)finish(v??true);}catch(e){toast(e.message);}}
  function keys(e){
   if(ReportDialogs.isOpen())return;
   if(e.key==='Escape'&&!ok.disabled)finish(null);
   else if(e.key==='Tab')ReportDialogs.trapFocus(windowEl,e);
  }
  ok.onclick=submit;cancel.onclick=()=>finish(null);close.onclick=()=>finish(null);extra.onclick=()=>finish('discard');document.addEventListener('keydown',keys);
  // Start keyboard focus inside the dialog: first field if any, else the main button.
  requestAnimationFrame(()=>{
   if(layer.hidden||windowEl.contains(document.activeElement))return;
   const field=$('modal-body').querySelector('input:not([type="hidden"]):not([disabled]),textarea:not([disabled]),select:not([disabled])');
   (field||ok).focus({preventScroll:true});
  });
 });
}
function modalTextarea(container,label,text,height=230){
 const tip=document.createElement('p');tip.className='modal-help';tip.textContent=label;container.appendChild(tip);
 const ta=document.createElement('textarea');ta.value=text;ta.style.height=height+'px';container.appendChild(ta);return ta;
}
async function replaceInBlock(block,modifier){
 const {start,end}=currentBlockRange(block),old=state.md.slice(start,end);
 const next=modifier(old);if(typeof next!=='string')throw Error('修改结果不是文本');
 changed(state.md.slice(0,start)+next+state.md.slice(end));await render();
}
async function editMath(span){
 const block=span.closest('.doc-block');if(!block||state.saving)return;
 try{currentBlockRange(block);}catch(e){toast(e.message);scheduleRender();return;}
 const anchor=mathRecords.get(span.dataset.mathId),oldTex=span.dataset.tex,oldRaw=span.dataset.raw;
 if(!anchor||state.md.slice(anchor.start,anchor.end).trim()!==oldRaw.trim()){toast('公式原文已变化，请重新打开');await render();return;}
 const snapshot=state.md,session=state.session,display=span.dataset.display==='1';let field,idField,example;
 const accepted=await modal({title:'修改 LaTeX 公式',kicker:'公式 · 原始 LaTeX 与稳定 ID',note:'块公式编号由文档设置控制；行内公式不编号。公式内容与稳定 ID 分别保存。',body:outer=>{
  field=modalTextarea(outer,'输入 LaTeX（不需要输入 $ 或 $$）',oldTex,110);
  if(display){
   idField=document.createElement('input');idField.setAttribute('aria-label','公式 ID');idField.value=anchor.equationId||'eq-'+freshID().slice(0,12);idField.readOnly=!!anchor.equationId;outer.append(idField);
  }
  example=document.createElement('div');example.className='modal-preview';outer.append(example);let revision=0;
  const paint=async()=>{const current=++revision;try{checkTeX(field.value);const node=await MathJax.tex2svgPromise(field.value,{display});if(current===revision&&example.isConnected)example.replaceChildren(node.querySelector('svg').cloneNode(true));}catch(e){if(current===revision)example.textContent='公式错误：'+e.message;}};
  field.oninput=()=>{clearTimeout(example._t);example._t=setTimeout(paint,170);};paint();
 },onOk:async()=>{
  const tex=field.value.trim(),id=display?idField.value.trim():null;
  if(!tex)throw Error('公式不能为空');ReportEquations.snippet(tex,id);checkTeX(tex);await MathJax.tex2svgPromise(tex,{display});
  if(id&&id!==anchor.equationId&&positionMap.blocks.some(x=>x.objectId===id))throw Error('公式 ID 已被使用');
  return {tex,id};
 }});
 if(!accepted)return;
 try{currentBlockRange(block);}catch(e){toast(e.message);scheduleRender();return;}
 if(state.md!==snapshot||state.session!==session)return toast('文稿已变化，请重新打开公式');
 if(accepted.tex===oldTex&&accepted.id===(anchor.equationId||null))return;
 const nl=oldRaw.includes('\r\n')?'\r\n':'\n';
 let next=display?ReportEquations.snippet(accepted.tex,accepted.id,nl):(oldRaw.startsWith('\\(')?'\\('+accepted.tex+'\\)':'$'+accepted.tex+'$');
 if(display)next=SourceBlocks.replacement(oldRaw,next);
 changed(state.md.slice(0,anchor.start)+next+state.md.slice(anchor.end),'equation');await render();
}
async function diagramDialog(originalSource,options={}){
 let graph;try{graph=Flow.parse(originalSource);}catch{graph=null;}
 const info={selected:graph?.nodes[0]?.id||null};let source,canvas,nameField,shapeField,statusP,titleField,edgePicker,buttons=[];
 return modal({title:options.caption===undefined?'编辑 Mermaid 图形':'编辑图形及图题',kicker:'Mermaid · 官方完整渲染',wide:true,
   note:'右侧使用官方引擎自动布局；简单流程图可改节点与连线，其他图形直接修改源码',
   body:outer=>{
    if(options.caption!==undefined){titleField=document.createElement('input');titleField.className='table-caption-input';titleField.placeholder='图题（不手填编号）';titleField.value=options.caption;outer.append(titleField);}
    const grid=document.createElement('div');grid.className='diagram-modal-grid';outer.append(grid);
    const left=document.createElement('div'),right=document.createElement('div');grid.append(left,right);
    const label=document.createElement('label');label.textContent='选中节点';left.append(label);
    nameField=document.createElement('textarea');nameField.placeholder='节点文字（可换行）';nameField.rows=3;nameField.setAttribute('aria-label','节点文字');left.append(nameField);
    shapeField=document.createElement('select');shapeField.innerHTML='<option value="box">矩形</option><option value="round">圆角</option><option value="decision">判断菱形</option>';shapeField.style.cssText='margin:10px 0;padding:8px;width:100%;border:1px solid #d9e1ec;border-radius:8px';left.append(shapeField);
    const controls=document.createElement('div');controls.className='diagram-forms';left.append(controls);
    const addBtn=(text,fn)=>{const b=document.createElement('button');b.type='button';b.textContent=text;b.onclick=()=>{if(!graph)return;try{fn();}catch(e){toast(e.message);}};controls.append(b);buttons.push(b);};
    addBtn('＋ 节点',()=>{if(graph.nodes.length>=90)throw Error('当前最多支持 90 个节点');let i=1;while(graph.nodes.some(n=>n.id==='N'+i))i++;const node={id:'N'+i,label:'新节点',shape:'box',x:45+graph.nodes.length*90,y:60};graph.nodes.push(node);info.selected=node.id;sync();});
    addBtn('－ 删除',()=>{if(!info.selected)return;graph.nodes=graph.nodes.filter(n=>n.id!==info.selected);graph.edges=graph.edges.filter(e=>e.from!==info.selected&&e.to!==info.selected);info.selected=graph.nodes[0]?.id||null;sync();});
    const group=document.createElement('div');group.className='diagram-forms';left.append(group);
    const from=document.createElement('input'),to=document.createElement('input');from.placeholder='起点 ID，如 A';to.placeholder='终点 ID，如 B';group.append(from,to);
    addBtn('→ 添加连线',()=>{const a=from.value.trim(),b=to.value.trim();if(!graph.nodes.some(n=>n.id===a)||!graph.nodes.some(n=>n.id===b))return toast('请填写已有节点 ID');if(graph.edges.length>=100)throw Error('当前最多支持 100 条连线');graph.edges.push({from:a,to:b,label:'',dashed:false});sync();});
    edgePicker=document.createElement('select');edgePicker.className='diagram-edge-picker';edgePicker.setAttribute('aria-label','选择连线');left.append(edgePicker);
    addBtn('删除选中连线',()=>{const index=Number(edgePicker.value);if(!Number.isInteger(index)||!graph.edges[index])return;graph.edges.splice(index,1);sync();});
    const hint=document.createElement('p');hint.className='diagram-help';hint.textContent='简单流程图可单击右侧节点后改字；Enter 为节点文字换行。布局由 Mermaid 自动计算。子图、时序图等完整语法请直接改下方源码，预览和导出沿用原文。';left.append(hint);
    source=modalTextarea(left,'Mermaid 源码（可交给 AI 修改）',originalSource,165);source.className='diagram-source-input';
    statusP=document.createElement('p');statusP.className='diagram-help';left.append(statusP);
    const rt=document.createElement('label');rt.textContent='官方引擎预览 · 自动布局';right.append(rt);
    canvas=document.createElement('div');canvas.className='modal-diagram-svg';right.append(canvas);
    function select(id){info.selected=id;const n=graph?.nodes.find(x=>x.id===id);nameField.value=n?.label||'';shapeField.value=n?.shape||'box';
      canvas.querySelectorAll('[data-node]').forEach(x=>x.classList.toggle('selected',x.dataset.node===id));}
    function paint(){
     nameField.disabled=!graph;shapeField.disabled=!graph;buttons.forEach(b=>b.disabled=!graph);edgePicker.disabled=!graph;edgePicker.replaceChildren();
     if(graph)graph.edges.forEach((edge,index)=>{const option=document.createElement('option');option.value=index;option.textContent=edge.from+' → '+edge.to+(edge.label?'（'+edge.label+'）':'');edgePicker.append(option);});
     select(info.selected);
     ReportMermaid.into(canvas,source.value).then(()=>{
      if(!graph)return;
      canvas.querySelectorAll('g.node').forEach(node=>{const id=node.dataset.id||node.id.replace(/^.*?flowchart-/, '').replace(/-\d+$/,'');if(graph.nodes.some(n=>n.id===id))node.dataset.node=id;});select(info.selected);
     }).catch(error=>{statusP.textContent=error.message;});
    }
    function sync(){source.value=Flow.serialize(graph,{positions:false});paint();statusP.textContent='';}
    nameField.oninput=()=>{const node=graph?.nodes.find(n=>n.id===info.selected);if(node){const old=node.label;node.label=nameField.value;try{sync();}catch(e){node.label=old;toast(e.message);}nameField.focus();nameField.setSelectionRange(nameField.value.length,nameField.value.length);}};
    shapeField.onchange=()=>{const node=graph?.nodes.find(n=>n.id===info.selected);if(node){const old=node.shape;node.shape=shapeField.value;try{sync();}catch(e){node.shape=old;paint();toast(e.message);}}};
    source.oninput=()=>{try{graph=Flow.parse(source.value);info.selected=graph.nodes[0]?.id||null;statusP.textContent='';}catch{graph=null;statusP.textContent='请在源码中编辑此图；完整预览不受节点编辑范围限制。';}paint();};
    canvas.addEventListener('click',ev=>{const node=ev.target.closest('[data-node]');if(node&&graph)select(node.dataset.node);});
    paint();
   },
   onOk:()=>{if(!source.value.trim()||source.value.length>50000)throw Error('Mermaid 源码必须非空，且不超过 50000 字符');return {source:source.value,caption:titleField?.value};}
 });
}
async function editDiagram(block){
 if(!block||state.saving)return;
 const start=+block.dataset.start,end=+block.dataset.end,raw=state.md.slice(start,end);
 if(!block.isConnected||raw!==block._sourceRaw)return toast('流程图定位已过期，请等待预览刷新后重试');
 const fence=SourceBlocks.scan(raw).find(b=>b.language==='mermaid');
 if(!fence)return toast('无法定位 Mermaid 源码');
 const original=raw.slice(fence.bodyFrom,fence.bodyTo).replace(/\r?\n$/,'');
 const snapshot=state.md,session=state.session;
 const accepted=await diagramDialog(original);
 if(!accepted||accepted.source===original)return;
 try{if(state.md!==snapshot||state.session!==session)throw Error('文稿已变化，请重新打开图形');SourceMap.assertRange(state.md,{start,end},raw,snapshot);}catch(e){toast(e.message);scheduleRender();return;}
 const next=raw.slice(0,fence.bodyFrom)+accepted.source+'\n'+raw.slice(fence.bodyTo);
 changed(state.md.slice(0,start)+next+state.md.slice(end),'diagram');await render();
 toast('流程图已经更新，保存后自动进入 HTML 交付。');
}
async function editSourceObject(fence){
 try{
 const raw=state.md.slice(fence.from,fence.to);
 if(raw!==editor.value.slice(fence.from,fence.to))return toast('源码位置已变化，请重试');
 commitFocusedVisual();
 if(positionMap?.source!==state.md)await render();
 const block=preview.querySelector(`.doc-block[data-start="${fence.from}"]`);
 if(!block||!block._sourceRaw.startsWith(raw.trimEnd()))return toast('对象位置已变化，请重新选择');
 const work=fence.language===TABLE_LANG?editStructuredTable(block):fence.language===FIGURE_LANG?editFigure(block):fence.language==='report-image-group'?editGroup(block):fence.language==='mermaid'?editDiagram(block):editBlockSource(block);
 await work;
 }catch(e){toast('编辑未执行：'+e.message);}
}
async function editBlockSource(block){
 if(state.saving)return;try{currentBlockRange(block);}catch(e){toast(e.message);scheduleRender();return;}
 const start=+block.dataset.start,end=+block.dataset.end,old=state.md.slice(start,end);let field;
 const note=block.dataset.type==='hrsFootnoteDef',tail=note?old.match(/(?:\r?\n[ \t]*)+$/)?.[0]||'':'';
 const value=await modal({title:note?'编辑脚注定义':'编辑 Markdown 块',kicker:'源码',body:outer=>{field=modalTextarea(outer,'这里只修改选中块，不影响其它段落',note?old.trimEnd():old,280);},onOk:()=>field.value});
 if(typeof value==='string')try{await replaceInBlock(block,()=>SourceMap.replaceNormalizedText(old,note?value.trimEnd()+tail:value));}catch(e){toast(e.message);scheduleRender();}
}
async function editReference(element){
 if(state.saving)return;
 commitFocusedVisual();const reference=referenceRecords.get(element),block=element.closest('.doc-block');
 try{currentBlockRange(block);if(!reference)return editBlockSource(block);SourceMap.assertRange(state.md,reference,reference.raw,reference.source);}catch(e){toast(e.message);scheduleRender();return;}
 const snapshot=state.md,session=state.session;let kind,id;
 const accepted=await modal({title:'修改交叉引用',kicker:'引用对象 ID',note:'显示编号由对象顺序计算；此处保存稳定对象 ID',body:outer=>{
  const label=document.createElement('label');label.className='xref-editor-kind';label.textContent='对象类型 ';
  kind=document.createElement('select');kind.setAttribute('aria-label','引用类型');for(const [value,text] of [['fig','图'],['tbl','表'],['sec','章节'],['eq','公式']]){const option=document.createElement('option');option.value=value;option.textContent=text;kind.append(option);}kind.value=reference.kind;label.append(kind);outer.append(label);
  id=document.createElement('input');id.className='xref-id-input';id.setAttribute('aria-label','引用对象 ID');id.value=reference.target;id.maxLength=64;outer.append(id);
  const help=document.createElement('p');help.className='modal-help';help.textContent='例如 fig-flow001、tbl-test001、eq-energy 或 sec-result；章节在标题末尾写 {#sec-result}。目标不存在时正式保存会拒绝。';outer.append(help);
 },onOk:()=>{const value=id.value.trim();if(!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(value)||!value.startsWith(kind.value+'-')||value.length<=kind.value.length+1)throw Error('ID 须以所选类型 fig-、tbl-、eq- 或 sec- 开头');return '@'+kind.value+':'+value;}});
 if(typeof accepted!=='string'||accepted===reference.raw)return;
 try{if(state.session!==session)throw Error('文档已切换');SourceMap.assertRange(state.md,reference,reference.raw,snapshot);}catch(e){toast(e.message);scheduleRender();return;}
 changed(state.md.slice(0,reference.start)+accepted+state.md.slice(reference.end),'reference');await render();
}
// Display preferences never insert line breaks or edit the source document.
function initEditorLayout(){
 const layout=$('edit-layout'),divider=$('split-divider'),wrap=$('source-wrap');
 const host=editor.view?.dom?.closest('.source-code-editor');
 const read=(key,fallback)=>{try{return localStorage.getItem(key)??fallback;}catch{return fallback;}};
 const store=(key,value)=>{try{localStorage.setItem(key,String(value));}catch{}};
 const setWrap=value=>{
  wrap.checked=!!value;host?.classList.toggle('source-soft-wrap',wrap.checked);
  $('markdown').style.whiteSpace=wrap.checked?'pre-wrap':'pre';editor.requestMeasure?.();store('hrs-source-wrap',wrap.checked);
 };
 setWrap(read('hrs-source-wrap','true')!=='false');wrap.onchange=()=>setWrap(wrap.checked);
 let ratio=50,dragging=false;
 const setRatio=value=>{
  ratio=Math.max(30,Math.min(70,Number(value)||50));
  layout.style.setProperty('--source-ratio',ratio+'%');divider.setAttribute('aria-valuenow',String(Math.round(ratio)));
  editor.requestMeasure?.();store('hrs-source-ratio',ratio);
 };
 setRatio(read('hrs-source-ratio',50));
 divider.onpointerdown=event=>{if(event.button!==0)return;event.preventDefault();dragging=true;divider.setPointerCapture(event.pointerId);layout.classList.add('resizing');scrollFollow?.suspend();};
 divider.onpointermove=event=>{if(dragging){const box=layout.getBoundingClientRect();setRatio((event.clientX-box.left)/box.width*100);}};
 const stop=()=>{dragging=false;layout.classList.remove('resizing');editor.requestMeasure?.();};
 divider.onpointerup=stop;divider.onlostpointercapture=stop;divider.ondblclick=()=>setRatio(50);
 divider.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home'].includes(event.key))return;event.preventDefault();setRatio(event.key==='Home'?50:ratio+(event.key==='ArrowLeft'?-2:2));};
}
function initScrollFollow(){
 initEditorLayout();
 const scroller=preview.closest('.page-scroll');scroller.tabIndex=0;scroller.setAttribute('aria-label','文档预览滚动区');
 scrollFollow=ScrollFollow.attach({sourceScroller:editor.scrollDOM,previewScroller:scroller,
  ready:()=>state.view==='split'&&!state.saving&&!state.visualPending&&!state.visualFocused?._composing&&$('modal-layer').hidden&&(positionMap?.source===state.md||!!state.visualFocused),
  sourceAnchor:()=>editor.viewportAnchor(currentSourceMap()),
  previewAnchor:()=>{
   const rect=scroller.getBoundingClientRect(),center=rect.top+scroller.clientHeight/2;
   const nodes=[...preview.querySelectorAll(':scope > .doc-block,.hrs-footnotes li[data-map-index]')].filter(n=>n.getBoundingClientRect().height>0);if(!nodes.length)return null;
   const node=nodes.find(node=>node.getBoundingClientRect().bottom>=center)||nodes.at(-1),bounds=node.getBoundingClientRect();
   let block;try{block=currentBlockRange(node,currentSourceMap());}catch{return null;}
   const max=scroller.scrollHeight-scroller.clientHeight,edge=max>1?(scroller.scrollTop<=1?'start':scroller.scrollTop>=max-1?'end':null):null;
   return {block,progress:Math.max(0,Math.min(1,(center-bounds.top)/Math.max(1,bounds.height))),edge};
  },
  scrollSource:anchor=>{
   const topic=currentTopic(documentModel(state.md));
   if(topic&&anchor.edge){const limit=sourceProjection.range,position=anchor.edge==='start'?limit.from:limit.to;editor.scrollToBlock({block:{start:position,end:Math.min(state.md.length,position+1)},progress:anchor.edge==='start'?0:1,edge:null});}
   else if(topic&&anchor.block.type==='hrsFootnoteDef')revealSourceNote(anchor.block);
   else editor.scrollToBlock(topic?{...anchor,edge:null}:anchor);
  },
  scrollPreview:({block,progress,edge})=>{
   const topic=currentTopic(documentModel(state.md));if(topic&&(block.start<topic.start||block.start>=topic.end))return;
   if(edge){scroller.scrollTo({top:edge==='start'?0:scroller.scrollHeight,behavior:'instant'});return;}
   const map=currentSourceMap();let node,range;
   for(const candidate of preview.querySelectorAll(':scope > .doc-block,.hrs-footnotes li[data-map-index]')){
    try{const current=currentBlockRange(candidate,map);if(current.start<=block.start&&block.start<current.end){node=candidate;range=current;break;}}catch{}
   }
   if(!node)return;
   const bounds=node.getBoundingClientRect(),rect=scroller.getBoundingClientRect();
   const offset=(block.start-range.start+(block.end-block.start)*progress)/Math.max(1,range.end-range.start);
   scroller.scrollTo({top:scroller.scrollTop+bounds.top+bounds.height*Math.max(0,Math.min(1,offset))-rect.top-scroller.clientHeight/2,behavior:'instant'});
  }
 });
 $('follow-scroll').onchange=()=>scrollFollow.setEnabled($('follow-scroll').checked);
 preview.addEventListener('load',()=>scrollFollow.suspend(),true);
}
function selectPreviewObject(block){
 try{const range=currentBlockRange(block);return sourceActions?.selectRange({from:range.start,to:range.end},block);}
 catch(error){toast('预览正在更新，请稍候重新选择');scheduleRender();return null;}
}
function editCaption(block,target){
 if(!block||state.saving||captionEditor)return;
 commitFocusedVisual();let range;try{range=currentBlockRange(block);}catch(error){toast(error.message);scheduleRender();return;}
 let model,parsed,language;
 try{
  if(block.dataset.pipeTable==='1'){parsed=ReportPipeTables.parseRaw(block._sourceRaw);model=parsed.model;}
  else {language=SourceBlocks.scan(block._sourceRaw)[0]?.language;if(!['report-figure','report-table','report-image-group'].includes(language))return;model=language==='report-image-group'?ReportLayout.parseGroup(block._sourceRaw):SourceBlocks.readObject(block._sourceRaw,language);}
 }catch(error){toast(error.message);return;}
 sourceActions?.clear();const snapshot=state.md,session=state.session,children=[...target.childNodes];
 const field=document.createElement('input');field.className='inline-caption-field';field.setAttribute('aria-label','编辑题注');field.maxLength=300;field.value=model.caption||'';field.placeholder='输入题注；支持 $公式$、加粗和脚注';
 target.replaceChildren(field);let finished=false;
 const finish=commit=>{
  if(finished)return;finished=true;captionEditor=null;target.replaceChildren(...children);
  if(!commit||field.value===(model.caption||'')){scheduleRender();return;}
  if(state.md!==snapshot||state.session!==session){toast('文稿已变化，请重新修改题注');scheduleRender();return;}
  try{
   model.caption=field.value;let text;
   if(parsed||language==='report-table')tableValidate(model);
   else if(language==='report-figure')figureValidate(model);
   else ReportLayout.validateGroup(model);
   if(parsed)text=ReportPipeTables.stringify(model,{newline:parsed.newline,id:parsed.id||(field.value.trim()?'tbl-'+freshID().slice(0,12):null)});
   else if(language==='report-image-group')text=ReportLayout.groupSnippet(model);
   else text='```'+language+'\n'+JSON.stringify(model,null,2)+'\n```';
   changed(snapshot.slice(0,range.start)+SourceBlocks.replacement(block._sourceRaw,text)+snapshot.slice(range.end),'caption');
  }catch(error){toast('题注未修改：'+error.message);scheduleRender();}
 };
 captionEditor={commit:()=>finish(true)};
 field.onblur=()=>finish(true);field.onkeydown=event=>{if(event.isComposing)return;if(event.key==='Enter'||event.key==='Escape'){event.preventDefault();event.stopPropagation();finish(event.key==='Enter');}};
 field.onclick=event=>event.stopPropagation();field.ondblclick=event=>event.stopPropagation();field.focus({preventScroll:true});field.select();
}
function bindPreview(){
 let zoomTimer=null,referenceTimer=null;
 preview.addEventListener('change',event=>{
  const input=event.target,range=input._taskRange;if(!range)return;
  try{
   if(state.saving)throw Error('正在保存，请稍后勾选');
    const next=rebaseDisplayedRange(range.source,range,range.source.slice(range.start,range.end));
    const record=currentSourceMap().at(next.start);
    if(!record||!SourceMap.taskRanges(state.md,record,marked).some(task=>task.start===next.start))throw Error('任务结构已变化，请等待预览刷新');
    insertAtSelection(input.checked?'x':' ',next);
  }catch(error){input.checked=range.checked;toast(error.message);scheduleRender();}
 });
 const clearZoom=()=>{clearTimeout(zoomTimer);document.querySelector('.editor-image-lightbox')?.remove();};
 function zoomImage(img){
  clearZoom();const box=document.createElement('div');box.className='editor-image-lightbox';box.setAttribute('role','dialog');box.setAttribute('aria-label','查看图片');
  const image=document.createElement('img');image.src=img.src;image.alt=img.alt;const close=document.createElement('button');close.textContent='关闭';close.onclick=clearZoom;box.append(close,image);box.onclick=e=>{if(e.target===box)clearZoom();};document.body.append(box);close.focus();
 }
 document.addEventListener('keydown',e=>{if(e.key==='Escape')clearZoom();});

  preview.addEventListener('mouseup',()=>{if(!captionEditor)syncPreviewSelection();});
  preview.addEventListener('keyup',()=>{if(!captionEditor)syncPreviewSelection();});
  document.addEventListener('selectionchange',()=>{if(!captionEditor)syncPreviewSelection();});
  preview.addEventListener('contextmenu',event=>{
   if(state.view==='reading'||event.target.closest('input,textarea,[contenteditable="true"]'))return;
   const block=event.target.closest('.doc-block');if(!block||!block.querySelector('.report-figure-wrap,.report-table-wrap,.report-equation,.mermaid-card'))return;
   if(!window.getSelection()?.isCollapsed)return;
   if(selectPreviewObject(block))sourceActions.showMenu(event);
  });
  preview.addEventListener('dblclick',ev=>{
  if(ev.target._taskRange)return;
  clearTimeout(referenceTimer);
  const pdfImage=ev.target.closest('img[data-pdf-asset]');if(pdfImage){ev.preventDefault();clearZoom();const link=(pdfImage.closest('.image-group-cell')||pdfImage.closest('figure'))?.querySelector('a[data-figure-source]');if(link)window.open(link.href,'_blank','noopener,noreferrer');return;}
  clearTimeout(zoomTimer);
 const reference=ev.target.closest('[data-xref-raw]');if(reference){if(state.view==='reading')return;ev.preventDefault();editReference(reference).catch(error=>toast(error.message));return;}
   if(state.view!=='reading'&&ev.target.closest('figcaption,caption,.hrs-table-heading-caption,.hrs-table-kind')){ev.preventDefault();editCaption(ev.target.closest('.doc-block'),ev.target.closest('figcaption,caption,.hrs-table-heading-caption,.hrs-table-kind'));return;}
   if(ev.target.closest('.hrs-table-tools'))return;
  const table=ev.target.closest('.report-table-wrap');if(table){ev.preventDefault();editStructuredTable(table.closest('.doc-block'));return;}
  const chart=ev.target.closest('.mermaid-card');if(chart){ev.preventDefault();editDiagram(chart.closest('.doc-block'));return;}
  const figure=ev.target.closest('.report-figure-wrap');if(figure){ev.preventDefault();if(figure.classList.contains('report-image-group'))editGroup(figure.closest('.doc-block'));else editFigure(figure.closest('.doc-block'));return;}
  const formula=ev.target.closest('.markdown-math');if(formula){ev.preventDefault();editMath(formula);return;}
  if(state.view==='reading')return;
   const block=ev.target.closest('.doc-block');if(block){ev.preventDefault();const target=ev.target.closest('[data-block-editor]');if(target)beginVisual(block,true,target);else editBlockSource(block);}
 });
 preview.addEventListener('click',async e=>{
  const note=e.target.closest('.hrs-footnotes li[data-map-index]');
  if(note&&!e.target.closest('a,button')&&state.view!=='reading'){locateRange({start:+note.dataset.start,end:+note.dataset.end},{origin:'preview'}).catch(e=>toast(e.message));return;}
  if(e.target._taskRange)return;
  const tableAction=e.target.closest('[data-table-toggle],[data-table-copy],[data-table-fold]');
  if(tableAction&&preview.contains(tableAction)){
   e.preventDefault();e.stopPropagation();
   const wrap=tableAction.closest('.report-table-wrap'),table=wrap?.querySelector('table.structured-table');
   const source=wrap?.querySelector('.hrs-table-source');if(!table)return;
   if(tableAction.dataset.tableFold){
    const code=source?.querySelector('.hrs-table-source-pre');if(!code)return;
    code.hidden=!code.hidden;tableAction.setAttribute('aria-expanded',String(!code.hidden));
    tableAction.textContent=code.hidden?'展开源码':'折叠源码';return;
   }
   if(tableAction.dataset.tableToggle){
    if(!source)return;
    const showing=source.hidden;source.hidden=!showing;table.hidden=showing;
    tableAction.textContent=showing?'查看表格':'查看 MD';tableAction.setAttribute('aria-pressed',String(showing));
   }else{
    const saved=tableAction.textContent;
    try{tableAction.textContent=await copyTSVToClipboard(tableToTSV(table))?'已复制 TSV':'复制失败';}
    catch{tableAction.textContent='复制失败';}
    setTimeout(()=>{if(tableAction.isConnected)tableAction.textContent=saved;},1300);
   }return;
  }
  const b=e.target.closest('.doc-block');if(b)state.selectedBlock=b;
  if(e.target.closest('[data-edit-figure]')){e.preventDefault();if(b?.querySelector('.report-image-group'))editGroup(b);else editFigure(b);return;}
  if(e.target.closest('[data-figure-source]'))return;
  const img=e.target.closest('img');if(img){clearTimeout(zoomTimer);if(e.detail<2)zoomTimer=setTimeout(()=>zoomImage(img),320);}
  const reference=e.target.closest('[data-xref-raw]');
  if(reference&&!e.ctrlKey&&!e.metaKey){e.preventDefault();const record=positionMap?.object(reference.dataset.xrefTarget);
   if(record){clearTimeout(referenceTimer);const snapshot=state.md;if(e.detail===1)referenceTimer=setTimeout(()=>{if(state.md===snapshot)locateRange(record,{origin:'reference'}).catch(error=>toast(error.message));},320);}else toast('找不到唯一的引用对象，请运行文档检查');return;}
   if(b&&state.view!=='reading'){
    if(!e.target.closest('img,button,a,input,textarea,[data-block-editor]')&&b.querySelector('.report-figure-wrap,.report-table-wrap,.report-equation,.mermaid-card')&&window.getSelection()?.isCollapsed)selectPreviewObject(b);
    else if(!captionEditor&&!e.target.closest('[data-block-editor]'))locatePreview(b);
   }
 });
}
function fileToB64(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(file);});}
function addUploadedFigure(reply,{bookmark,docId,draftId,md}){
 if(state.documentId!==docId||state.draftId!==draftId||state.md!==md)throw Error('文稿在图片读取时已变化，请重新插入');
 const fig=figureDefault('image',reply.path);fig.caption='';
 if(reply.vector_source)fig.vectorSource=reply.vector_source;
 if(reply.source_asset)fig.sourceAsset=reply.source_asset;
 if(reply.raster_fallback)fig.rasterFallback=reply.raster_fallback;
 if(reply.rendition)fig.rendition=reply.rendition;
 insertAtSelection('\n'+figureSnippet(fig)+'\n',bookmark);
 if(reply.warnings?.length)toast(reply.warnings.join('；').slice(0,260));
 else toast(reply.vector_source?'EMF 原件已保留；预览格式：'+(reply.path.endsWith('.svg')?'SVG 矢量':'PNG 备用'):'图片已暂存；按「保存正式稿」后写入正式文档');
}
function imageInsertionContext(){return {
 bookmark:{start:editor.selectionStart,end:editor.selectionEnd},
 docId:state.documentId,draftId:state.draftId,md:state.md
};}
async function insertImage(file,linkedFiles=[],context=imageInsertionContext()){
 if(state.saving)return toast('正式保存中，请稍后添加图片');
 try{
  const args={name:file.name,base64:await fileToB64(file),document_id:context.docId,draft_id:context.draftId};
  if(file.name.toLowerCase().endsWith('.pdf')&&linkedFiles.length){
   if(linkedFiles.length!==1||(!linkedFiles[0].name.toLowerCase().endsWith('.png')))
    throw Error('PDF 的备用预览只接受一张 PNG 文件');
   args.preview_base64=await fileToB64(linkedFiles[0]);
  }
  if(file.name.toLowerCase().endsWith('.svg')&&linkedFiles.length){
   args.linked_assets={};
   for(const linked of linkedFiles){
    if(linked.name in args.linked_assets)throw Error('附属图片有重名文件');
    args.linked_assets[linked.name]=await fileToB64(linked);
   }
  }
  const reply=await api('/api/upload','POST',args);
  addUploadedFigure(reply,context);
 }catch(e){toast('图片插入失败：'+e.message);}
}
async function pasteNativeGraphic({fallbackFile=null,manual=false,mixed=false}={}){
 if(state.saving)return toast('正式保存过程中，请稍后粘贴图片');
 const context=imageInsertionContext();
 try{
  if(mixed){
   const document=await api('/api/clipboard/document','POST',{text:null},{'X-Report-Studio-Clipboard':'user-action'});
   const block=documentModel(context.md).map.at(context.bookmark.start);
   const literal=block?.type==='code'&&block.start<context.bookmark.start&&block.end>context.bookmark.start&&!/^report-(?:figure|table|image-group)$/.test(block.token.lang||'');
   if(literal&&!document.available)throw Error('普通代码块内只能粘贴文字，请先复制所需文本');
   if(document.available){
    if(state.documentId!==context.docId||state.draftId!==context.draftId||state.md!==context.md||editor.selectionStart!==context.bookmark.start||editor.selectionEnd!==context.bookmark.end)throw Error('文稿或选区在粘贴期间变化，请重新操作');
    if(literal){insertAtSelection(document.text,context.bookmark);return;}
    await objectClipboard.pasteRich(document);return;
   }
   mixed=false;
  }
  const response=await fetch('/api/clipboard/paste',{
   method:'POST',headers:{'Content-Type':'application/json','X-Report-Studio-Clipboard':'user-action'},
   body:JSON.stringify({document_id:context.docId,draft_id:context.draftId})});
  const reply=await response.json();
  if(!response.ok||!reply.ok)throw Error(reply.error||`HTTP ${response.status}`);
  addUploadedFigure(reply,context);
 }catch(error){
  if(fallbackFile&&!mixed)await insertImage(fallbackFile,[],context);
  else if(manual||!/没有可读取的|仅在 Windows/.test(error.message))toast('原生图形粘贴失败：'+error.message);
 }
}
function handleGraphicsPaste(event){
 if(event.defaultPrevented||state.saving)return;
 const data=event.clipboardData;
 const file=[...(data?.files||[])].find(f=>f.type.startsWith('image/')||/\.(?:emf|svg)$/i.test(f.name));
 const plain=data?.getData('text/plain')||'';
 const rich=data?.getData('text/html')||'';
 // Only intercept graphic-oriented clipboard formats. Ordinary text/Excel
 // and rich-text paragraph paste must retain CodeMirror's normal behavior.
 if(file||(!plain&&(!rich||/<(?:img|svg)\b/i.test(rich)))){
  event.preventDefault();pasteNativeGraphic({fallbackFile:file,mixed:!plain&&!rich});
 }
}
async function blobToB64(blob){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(blob);});}
const formatBytes=size=>size<1024?size+' B':size<1024*1024?(size/1024).toFixed(1)+' KiB':(size/(1024*1024)).toFixed(2)+' MiB';
function displayedAssetNames(article=preview){
 const found=[];
 for(const img of article.querySelectorAll('img')){
  const match=img.getAttribute('src')?.match(/^\/assets\/([A-Za-z0-9_.-]+)/i);
  if(match)found.push(match[1]);
 }
 return [...new Set(found)].sort();
}
const exportRequest=(md,mode='recompilable',includePdfOriginals=false,article=preview)=>({markdown:md,document_id:state.documentId,draft_id:state.draftId,
 revision:state.revision,template:state.template,render_profile:state.renderProfile,render_options:state.renderOptions,accept_numbered_headings:activeHeadingAcceptance,source_mode:mode,...(mode==='reading'?{display_assets:[...new Set([...displayedAssetNames(article),...(includePdfOriginals?[...article.querySelectorAll('[data-pdf-asset]')].map(e=>e.dataset.pdfAsset):[])])]}:{})});
function figureWidthMm(img){
 const group=img.closest('.image-group-grid');
 const count=group?Number(group.style.getPropertyValue('--group-columns'))||2:1;
 // Fixed printable layout width; independent from the current Edge window size.
 return group?Math.max(32,(160-(count-1)*4)/count):160;
}
async function buildExport(preferences={quality:'standard',sourceMode:'reading'}){
 await presentationWait;
 const previous=state.renderProfile,previousOptions=state.renderOptions,active=ReportProfile.normalize(preferences.renderProfile??previous);
 state.renderProfile=active;state.renderOptions=ReportProfile.normalizeOptions(preferences.renderOptions??previousOptions);
 try{
  commitSource();commitFocusedVisual();
  const source=state.md,session=state.session;
  if(preferences.topicKey&&active!=='free')throw Error('专题分册只适用于自由笔记');
  if(preferences.topicKey&&preferences.expectSourceSha256!==await ReportExportArchive.hash(new TextEncoder().encode(source)))throw Error('专题源快照已变化，请重新取得专题列表');
  const exportSource=preferences.topicKey?documentModel(source).notebook.extract(preferences.topicKey).markdown:source;
  const reply=await preflightCurrent(exportSource,active,state.renderOptions);
  const errors=reply.diagnostics.filter(d=>d.severity==='error');
  if(errors.length){await validateCurrent();throw Error('工程输出已阻止：'+errors[0].message);}
  activeHeadingAcceptance=preferences.acceptNumberedHeadings===true;
  if(reply.diagnostics.some(d=>d.code==='HEADING_SOURCE_PREFIX')&&!activeHeadingAcceptance){
   if(new URLSearchParams(location.search).get('programmatic')==='1')throw Error('HEADING_SOURCE_PREFIX：程序化导出须显式接受本次手工章号提醒');
   if(acceptedHeadingSnapshot!==source){
    const ok=await ReportDialogs.confirm('标题中存在手工章号。输出会自动编号，请先核对，避免重复编号。是否接受本次源稿的提醒并继续？',{title:'核对手工章号',okText:'已核对，继续导出',cancelText:'返回检查'});
    if(!ok)throw Error('导出已取消');acceptedHeadingSnapshot=source;
   }
   activeHeadingAcceptance=true;
  }
  if(state.md!==source||state.session!==session)throw Error('文稿已变化，请重新导出');
  return await buildExportCurrent(preferences,exportSource);
 }finally{activeHeadingAcceptance=false;state.renderOptions=previousOptions;if(state.renderProfile===active){state.renderProfile=previous;if(previous!==active||preferences.renderOptions)await render();}}

}
async function buildExportCurrent(preferences,exportSource=state.md){
 const archive=window.ReportExportArchive,rendition=window.ReportExportRendition;
 if(!archive||!rendition)throw Error('本地导出模块缺失');
 const options=archive.options(preferences);
 commitSource();commitFocusedVisual();
 const freeze={md:state.md,exportSource,docId:state.documentId,draftId:state.draftId,revision:state.revision,session:state.session,renderProfile:state.renderProfile,renderOptions:JSON.stringify(state.renderOptions),colorTheme:state.colorTheme};
 const exportView=await buildDocumentView(exportSource,{isCurrent:()=>state.md===freeze.md&&state.session===freeze.session});
 if(!exportView)throw Error('文稿已变化，请重新导出');
 if(exportView.errors.length)throw Error('存在渲染失败，暂不导出：'+exportView.errors.join('；').slice(0,170));
 const requireSame=()=>{
  if(state.md!==freeze.md||state.documentId!==freeze.docId||state.draftId!==freeze.draftId||state.session!==freeze.session||state.revision!==freeze.revision||state.renderProfile!==freeze.renderProfile||JSON.stringify(state.renderOptions)!==freeze.renderOptions||state.colorTheme!==freeze.colorTheme)
   throw Error('导出过程中工作文稿已变化，请重新导出');
 };
 requireSame();
 const preflight=await api('/api/export-preflight','POST',exportRequest(freeze.exportSource,options.sourceMode,options.includePdfOriginals,exportView.article));
 const expectedNames=Object.keys(preflight.files).sort();
 const assets={};let sourceBytes=0,displayBytes=0,generated=0,belowTarget=0;
 for(const name of expectedNames){
  const url='/assets/'+encodeURIComponent(name)+'?document_id='+encodeURIComponent(freeze.docId)+'&draft_id='+encodeURIComponent(freeze.draftId);
  const response=await fetch(url,{cache:'no-store'});
  if(!response.ok)throw Error('导出原始资源读取失败：assets/'+name);
  const bytes=new Uint8Array(await response.arrayBuffer());
  if(bytes.length!==preflight.files[name].bytes||await archive.hash(bytes)!==preflight.files[name].sha256)
    throw Error('资源在导出过程中变化或校验失败：assets/'+name);
  assets[name]={bytes,role:/\.(?:emf|pdf)$/i.test(name)?'source':'display'};
  sourceBytes+=bytes.length;
 }
 requireSame();
 const clone=exportView.article.cloneNode(true);
 // Archive state always comes from Markdown. Optional free-reader state is
 // separate and bound to this source snapshot and original task position.
 clone.querySelectorAll('input[type="checkbox"]').forEach(input=>{input.disabled=true;});
 clone.dataset.hrsTaskSnapshot=preflight.markdown_sha256;
 exportView.article.querySelectorAll('.hrs-task-checkbox').forEach((input,index)=>{const output=clone.querySelectorAll('.hrs-task-checkbox')[index];if(output)output.dataset.hrsTaskKey=String(input._taskRange.start);});
 clone.dataset.hrsRenderProfile=state.renderProfile;
 clone.querySelectorAll('[data-table-edit]').forEach(button=>button.remove());
 ReportLinks.decorate(clone);
 for(const wrap of clone.querySelectorAll('.report-table-wrap')){
  const view=wrap.querySelector('.hrs-table-source'),table=wrap.querySelector('.hrs-table-rendered');
  if(view)view.hidden=true;if(table)table.hidden=false;
  const button=wrap.querySelector('[data-table-toggle]');if(button){button.textContent='查看 MD';button.setAttribute('aria-pressed','false');}
 }

 clone.removeAttribute('id');clone.querySelectorAll('[contenteditable]').forEach(e=>e.removeAttribute('contenteditable'));
 clone.querySelectorAll('.chart-note').forEach(e=>e.remove());
 clone.querySelectorAll('[data-block-editor]').forEach(e=>e.removeAttribute('data-block-editor'));
 const pdfOriginals={};
 clone.querySelectorAll('a[data-figure-source]').forEach(link=>{
  const name=link.dataset.pdfAsset;
  if(options.includePdfOriginals&&assets[name]){
   // The re-compilable v2 source archive will already contain and verify this
   // exact PDF blob. Don't copy the uncompressed PDF base64 a second time.
   if(options.sourceMode==='reading')pdfOriginals[name]={base64:archive.bytesToBase64(assets[name].bytes),bytes:assets[name].bytes.length,sha256:preflight.files[name].sha256};
   link.removeAttribute('href');link.removeAttribute('target');link.setAttribute('role','button');link.tabIndex=0;link.textContent='PDF ↗';link.title='打开这张图的原始 PDF';link.classList.add('figure-source-chip');
  }else link.remove();
 });
 clone.querySelectorAll('[data-pdf-asset]').forEach(e=>{if(!options.includePdfOriginals||!assets[e.dataset.pdfAsset])e.removeAttribute('data-pdf-asset');});
 clone.querySelectorAll('.navigation-highlight,.preview-object-selected').forEach(e=>e.classList.remove('navigation-highlight','preview-object-selected'));
 clone.querySelectorAll('.hrs-code-copy').forEach(e=>e.remove());
 clone.querySelectorAll('[data-map-index]').forEach(e=>e.removeAttribute('data-map-index'));
 clone.querySelectorAll('.preview-text-editor').forEach(e=>{e.classList.remove('preview-text-editor');e.removeAttribute('tabindex');e.removeAttribute('title');e.removeAttribute('data-block-editor');});
 clone.querySelectorAll('[data-xref-raw]').forEach(e=>{e.removeAttribute('data-xref-raw');e.removeAttribute('data-xref-kind');e.removeAttribute('data-xref-target');e.removeAttribute('title');});
 clone.querySelectorAll('.doc-block').forEach(e=>{e.removeAttribute('id');e.removeAttribute('title');e.removeAttribute('tabindex');e.removeAttribute('data-start');e.removeAttribute('data-end');e.removeAttribute('data-type');e.removeAttribute('data-editable');});
 // Every static exported heading gets a stable reader anchor; IR/Markdown and
 // existing sec-* cross-reference metadata stay completely unchanged.
 let headingCount=0;
 clone.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(h=>{if(!h.id)h.id='hrs-section-'+(++headingCount);});
 clone.querySelectorAll('[data-math-id]').forEach(e=>{e.removeAttribute('data-math-id');e.removeAttribute('data-tex');e.removeAttribute('data-display');e.removeAttribute('data-raw');e.removeAttribute('title');});
 clone.querySelectorAll('[data-mermaid],[data-hrs-mermaid]').forEach(e=>{e.removeAttribute('data-mermaid');e.removeAttribute('data-hrs-mermaid');});
 const allImages=[...clone.querySelectorAll('img')],counts={};
 for(const img of allImages){
  const src=img.getAttribute('src');
  const match=src?.match(/^\/assets\/([A-Za-z0-9_.-]+)(?:\?document_id=[a-z0-9]+&draft_id=[a-z0-9]+)?$/i);
  if(!match||!assets[match[1]])throw Error('存在无法离线嵌入的图片：'+src);
  counts[match[1]]=(counts[match[1]]||0)+1;
 }
 const domRefs={},domCandidates=[],renditionCache=new Map();
 for(const img of allImages){
  const name=img.getAttribute('src').match(/^\/assets\/([A-Za-z0-9_.-]+)/i)[1];
  const original=assets[name].bytes,physicalWidth=figureWidthMm(img),key=preflight.files[name].sha256+'|'+name.split('.').at(-1).toLowerCase()+'|'+physicalWidth+'|'+options.quality;
  if(!renditionCache.has(key))renditionCache.set(key,await rendition.rendition(original,name,physicalWidth,options));
  const output=renditionCache.get(key);
  if(output.modified)generated++;
  if(output.belowTarget)belowTarget++;
  const base64=archive.bytesToBase64(output.bytes);
  img.classList.remove('hrs-image-pending');img.setAttribute('src',`data:${output.mime};base64,${base64}`);
  // A dom-ref avoids embedding identical base64 twice, but only when the
  // visible data is exactly the original asset bytes and occurs once.
  if(options.sourceMode==='recompilable'&&counts[name]===1&&!output.modified)
   domCandidates.push({img,name,id:'sha256:'+preflight.files[name].sha256});
  displayBytes+=output.bytes.length;
 }
 // Only create DOM references when exactly ONE visible IMG owns a blob hash.
 // Two different asset names can have identical bytes; a filename-only count
 // would make both IMG nodes point to the same hash and break re-import.
 const digestCounts={};
 for(const ref of domCandidates)digestCounts[ref.id]=(digestCounts[ref.id]||0)+1;
 for(const ref of domCandidates)if(digestCounts[ref.id]===1){ref.img.setAttribute('data-report-blob',ref.id);domRefs[ref.name]=ref.id;}
 // MathJax may nest SVG nodes inside a single displayed equation. Verify each
 // formula has its own direct rendered SVG instead of comparing total SVG tags.
 if([...clone.querySelectorAll('.markdown-math')].some(node=>!node.querySelector(':scope > svg')))
  throw Error('部分公式没有生成 SVG');
 // Single canonical visual tokens/components for editor, standalone HTML and help.
 const loadCSS=async path=>{const response=await fetch(path,{cache:'no-store'});if(!response.ok)throw Error('无法读取共享离线样式：'+path);return response.text();};
 const css=await loadCSS('/web/print.css');
 const colorCSS=await loadCSS(ReportTheme.path(state.colorTheme));
 const designCSS=await loadCSS('/web/design_tokens.css');
 const surfaceCSS=await loadCSS('/web/surface_components.css');
 const readerStyle=await fetch('/web/report_reader.css',{cache:'no-store'});
 if(!readerStyle.ok)throw Error('离线阅读样式缺失，无法导出');
 const readerCSS=await readerStyle.text();
 const readerScript=await fetch('/web/report_reader.js',{cache:'no-store'});
 if(!readerScript.ok)throw Error('离线阅读模块缺失，无法导出');
 const readerJS=await readerScript.text();
 const title=(exportView.headings[0]?.text||'离线技术报告').replace(/<[^>]+>/g,'');
 const payload=await archive.buildArchive({md:freeze.exportSource,assetRecords:assets,domRefs,opts:options,
  template:state.template,theme:state.theme,renderProfile:state.renderProfile,renderOptions:state.renderOptions,colorTheme:state.colorTheme,savedMd:state.savedMd,projectRevision:state.revision});
 const source=archive.safeJson(payload),pdfData=Object.keys(pdfOriginals).length?'<script type="application/json" id="hrs-pdf-originals">'+archive.safeJson(pdfOriginals)+'</script>':'';
 const html='<!doctype html>\n<!-- HRS render-profile: '+state.renderProfile+' -->\n<html lang="zh-CN" data-hrs-render-profile="'+state.renderProfile+'" data-hrs-color-theme="'+state.colorTheme+'"><head><meta charset="utf-8"><meta name="hrs-render-profile" content="'+state.renderProfile+'"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escapeHTML(title)+'</title><style>'+colorCSS+'\n'+css+'\n'+readerCSS+'\n'+designCSS+'\n'+surfaceCSS+'</style></head>\n<body class="theme-'+escapeHTML(state.theme)+' hrs-profile-'+state.renderProfile+'" data-render-profile="'+state.renderProfile+'"><main data-hrs-reader-root="1" data-hrs-render-profile="'+state.renderProfile+'" data-hrs-task-snapshot="'+preflight.markdown_sha256+'" data-hrs-show-object-numbers="'+(clone.dataset.hrsShowObjectNumbers||'1')+'" data-hrs-show-equation-numbers="'+(clone.dataset.hrsShowEquationNumbers||'0')+'">'+clone.innerHTML+'</main><footer class="report-footer"></footer><script type="application/json" id="report-source">'+source+'</script>'+pdfData+'<script id="hrs-reader-runtime">'+readerJS+'</script></body></html>';
 const totalBytes=new TextEncoder().encode(html).byteLength;
 if(totalBytes>archive.MAX_HTML)throw Error('导出 HTML 超过 36 MiB 兼容上限。请改用纯阅读或较低图像质量，完整工程可单独备份');
 requireSame();
 await api('/api/export-verify','POST',{...exportRequest(freeze.exportSource,options.sourceMode,options.includePdfOriginals,exportView.article),asset_hashes:Object.fromEntries(expectedNames.map(name=>[name,preflight.files[name].sha256])),markdown_sha256:preflight.markdown_sha256});
 requireSame();
 lastExportStats={originalBytes:sourceBytes,displayBytes,totalBytes,generated,belowTarget,assets:expectedNames.length,quality:options.quality,sourceMode:options.sourceMode};
 lastExportRequest={...exportRequest(freeze.exportSource,options.sourceMode,options.includePdfOriginals,exportView.article),asset_hashes:Object.fromEntries(expectedNames.map(name=>[name,preflight.files[name].sha256])),markdown_sha256:preflight.markdown_sha256,quality:options.quality};
 return html;
}
function downloadBlob(blob,filename){
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),20000);
}
async function exportModules(keys,preferences){
 await presentationWait;
 commitSource();commitFocusedVisual();
 if(state.renderProfile!=='free')throw Error('专题分册只适用于自由笔记');
 const source=state.md,session=state.session,model=documentModel(source),selected=model.notebook.topics.filter(t=>keys.includes(t.key));
 if(!selected.length||selected.length!==new Set(keys).size)throw Error('请选择有效专题');
 const failures=[];
 for(const topic of selected)try{
  const part=model.notebook.extract(topic.key);
  await api('/api/export-preflight','POST',exportRequest(part.markdown));
 }catch(error){failures.push(topic.title+'：'+error.message);}
 if(failures.length)throw Error('未写入任何分册：\n'+failures.join('\n'));
 const sourceHash=await ReportExportArchive.hash(new TextEncoder().encode(source));
 const presentation=JSON.stringify([state.renderOptions,state.renderProfile,state.colorTheme,state.template,state.revision]);
 const context={document_id:state.documentId,draft_id:state.draftId,revision:state.revision,source_sha256:sourceHash,template:state.template};
 const requireSame=()=>{if(state.md!==source||state.session!==session||state.documentId!==context.document_id||state.draftId!==context.draft_id||presentation!==JSON.stringify([state.renderOptions,state.renderProfile,state.colorTheme,state.template,state.revision]))throw Error('文稿或显示设置已变化，分册导出已取消');};
 requireSame();
 const begin=await api('/api/export/modules/begin','POST',{...context,markdown:source,render_profile:'free',titles:selected.map(t=>t.title)});
 const binding={...context,token:begin.token};
 try{
  for(let index=0;index<selected.length;index++){
   requireSame();
   const html=await buildExport({...preferences,topicKey:selected[index].key,expectSourceSha256:sourceHash});requireSame();
   await api('/api/export/modules/stage','POST',{...lastExportRequest,...binding,index,html});
  }
  requireSame();return await api('/api/export/modules/finish','POST',binding);
 }catch(error){await api('/api/export/modules/cancel','POST',binding).catch(()=>{});throw error;}
}
async function exportFile(){
 if(state.saving)return toast('保存中，请稍后导出');
 commitSource();commitFocusedVisual();
 try{if(!await ensureProjectForExport())return;}catch(e){return toast('请先确定工程位置：'+e.message);}
 let quality=exportPreferences.quality,sourceMode=exportPreferences.sourceMode,includePdfOriginals=!!exportPreferences.includePdfOriginals,estimate,busy=false,assetBusy=false;
 const notebookModel=documentModel(state.md),selectedTopics=new Set(topicFocus?[topicFocus.key]:[]);let exportScope='whole';
 const result=await modal({title:'导出 HTML',kicker:'导出 · 离线单文件',
   note:'整篇或按一级标题勾选分册。分册均可独立回编；多个分册统一为 ZIP。结果写入项目 output/。',
  okText:'生成 HTML',body:outer=>{
   const host=document.createElement('div');host.className='export-options';outer.append(host);
   const addGroup=(legend,choices,current,onChange)=>{
    const field=document.createElement('fieldset'),label=document.createElement('legend');label.textContent=legend;field.append(label);
    choices.forEach(([value,text,description])=>{
     const option=document.createElement('label');option.className='export-choice';
     const radio=document.createElement('input');radio.type='radio';radio.name={'图像质量':'export-quality','源文件策略':'export-source','导出范围':'export-scope'}[legend];radio.value=value;radio.checked=current===value;
     radio.addEventListener('change',()=>{if(radio.checked)onChange(value);});
     const detail=document.createElement('span'),name=document.createElement('strong'),desc=document.createElement('small');
     name.textContent=text;desc.textContent=description;detail.append(name,desc);option.append(radio,detail);field.append(option);
    });host.append(field);
   };
   if(state.renderProfile==='free'){
    let list;
    addGroup('导出范围',[
     ['whole','整篇文档','与当前聚焦范围无关，导出完整源稿。'],
     ['modules','勾选专题分册','每个一级标题独立为一份 HTML；可选择仅阅读或可回编，跨专题引用会提前提示。']
    ],exportScope,value=>{
     exportScope=value;list.hidden=value!=='modules';
     $('modal-ok').textContent=value==='modules'?'生成分册':'生成 HTML';
    });
    list=document.createElement('fieldset');list.className='export-topic-list';list.hidden=true;
    const legend=document.createElement('legend');legend.textContent='选择专题';list.append(legend);
    const actions=document.createElement('div');actions.className='export-topic-actions';
    for(const [label,checked] of [['全选',true],['清空',false]]){const button=document.createElement('button');button.type='button';button.className='btn btn-quiet';button.textContent=label;button.onclick=()=>list.querySelectorAll('input[data-topic-key]').forEach(input=>{input.checked=checked;if(checked)selectedTopics.add(input.dataset.topicKey);else selectedTopics.delete(input.dataset.topicKey);});actions.append(button);}list.append(actions);
    notebookModel.notebook.topics.forEach((topic,i)=>{
     const label=document.createElement('label'),input=document.createElement('input');label.className='export-choice';input.type='checkbox';input.dataset.topicKey=topic.key;input.checked=selectedTopics.has(topic.key);input.onchange=()=>{if(input.checked)selectedTopics.add(topic.key);else selectedTopics.delete(topic.key);};label.append(input,document.createTextNode((i+1)+' · '+topic.title));list.append(label);
    });host.append(list);
   }
   addGroup('图像质量',[
    ['compact','轻量发布 · 150 DPI','缩小大尺寸栅格图；保留矢量图。'],
    ['standard','标准发布 · 200 DPI','默认，兼顾工程细线、文字和体积。'],
    ['print','高清发布 · 300 DPI','适合高清审阅，输出文件可能更大。'],
    ['original','原生质量 · 不重采样','保留原始显示资源分辨率；EMF 仍用其已有预览。']
   ],quality,v=>{quality=v;});
   addGroup('源文件策略',[
    ['recompilable','可回编归档','保存 Markdown 和所有被引用原始附件；支持重新导入。'],
    ['reading','纯阅读发布','不附带 Markdown 或 EMF 原件；可另勾选 PDF 原件打开入口。']
   ],sourceMode,v=>{sourceMode=v;});
   const pdfLabel=document.createElement('label');pdfLabel.className='export-choice';const pdfCheck=document.createElement('input');pdfCheck.type='checkbox';pdfCheck.checked=includePdfOriginals;pdfCheck.setAttribute('aria-label','提供 PDF 原件打开入口');pdfCheck.onchange=()=>{includePdfOriginals=pdfCheck.checked;};pdfLabel.append(pdfCheck,document.createTextNode('提供 PDF 原件打开入口（阅读版同时携带 PDF；可回编归档始终保留全部原件）'));host.append(pdfLabel);
   estimate=document.createElement('div');estimate.className='export-estimate';estimate.textContent='正在检查源图片体积和完整性…';host.append(estimate);
   // Asset housekeeping only lives inside the export dialog. It is never
   // part of Ctrl+S, PDF printing or normal HTML generation.
   const housekeeping=document.createElement('details');housekeeping.className='export-asset-housekeeping';
   const summary=document.createElement('summary');summary.textContent='工程素材整理（可选，不影响导出）';housekeeping.append(summary);
   const housekeepingBody=document.createElement('div');housekeepingBody.className='export-asset-body';housekeeping.append(housekeepingBody);
   const explanation=document.createElement('p');explanation.textContent='扫描已正式保存的 assets/。未使用的素材需手动勾选才能移入项目回收区；历史备份用过的素材将特别提示。默认不删除任何文件。';housekeepingBody.append(explanation);
   const scanButton=document.createElement('button');scanButton.type='button';scanButton.className='btn btn-quiet';scanButton.textContent='检查未使用的素材';
   const resultArea=document.createElement('div');resultArea.className='asset-housekeeping-results';resultArea.setAttribute('aria-live','polite');
   const actionRow=document.createElement('div');actionRow.className='asset-housekeeping-actions';
   const trashButton=document.createElement('button');trashButton.type='button';trashButton.className='btn btn-quiet';trashButton.textContent='把选中素材移入回收区';trashButton.hidden=true;
    const purgeButton=document.createElement('button');purgeButton.type='button';purgeButton.className='btn btn-quiet';purgeButton.textContent='清空回收区';purgeButton.hidden=true;
    const batchesArea=document.createElement('div');batchesArea.className='asset-housekeeping-batches';
    actionRow.append(scanButton,trashButton,purgeButton);housekeepingBody.append(actionRow,resultArea,batchesArea);host.append(housekeeping);
   let lastScan=null;
   const checked=new Set();
   function checkSafe(){
    if(state.saving||busy||assetBusy)throw Error('有操作正在进行，请稍后整理素材');
    if(state.dirty||state.md!==state.savedMd)throw Error('请先正式保存 Markdown，再扫描或整理未引用素材；工作快照不作为清理依据');
    if(state.documentId==='new'||!state.externalProject)throw Error('请先正式保存到独立工程目录');
   }
   async function assetAction(endpoint,payload){
    return api('/api/project/assets/'+endpoint,'POST',{document_id:state.documentId,revision:state.revision,...payload},{'X-HRS-Asset-Action':'user-action'});
   }
   function assetButtons(b){
     assetBusy=b;scanButton.disabled=b;trashButton.disabled=b||!checked.size;purgeButton.disabled=b||!lastScan?.trash?.batch_count;
     batchesArea.querySelectorAll('button').forEach(button=>button.disabled=b);
    $('modal-ok').disabled=b;$('modal-cancel').disabled=b;$('modal-close').disabled=b;
   }
   function renderSummary(scan){
     resultArea.replaceChildren();batchesArea.replaceChildren();checked.clear();
     purgeButton.hidden=!scan.trash?.batch_count;
     if(scan.trash?.batch_count){const total=document.createElement('p');total.className='asset-housekeeping-summary';total.textContent='回收区共 '+scan.trash.batch_count+' 批 · '+scan.trash.file_count+' 个附件 · '+formatBytes(scan.trash.total_bytes);batchesArea.append(total);}
    const totals=document.createElement('p');totals.className='asset-housekeeping-summary';
    const summaryStats=scan.summary;
    totals.textContent=`当前使用 ${summaryStats.in_use.groups} 组 · 草稿保护 ${summaryStats.draft.groups} 组 · 历史引用 ${summaryStats.history.groups} 组 · 未引用 ${summaryStats.unused.groups} 组 (${formatBytes(summaryStats.unused.bytes)})`;
    resultArea.append(totals);
    if(scan.excluded){const note=document.createElement('p');note.className='modal-help';note.textContent=`另有 ${scan.excluded} 项非标准素材／子目录未纳入整理，不会被删除。`;resultArea.append(note);}
    const options=scan.groups.filter(item=>item.status==='unused'||item.status==='history');
    if(options.length){
     const list=document.createElement('div');list.className='asset-housekeeping-list';
     for(const group of options){
      const label=document.createElement('label');label.className='asset-housekeeping-item';
      const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.value=group.id;
      checkbox.setAttribute('aria-label','选择素材组 '+group.id);
      checkbox.onchange=()=>{checkbox.checked?checked.add(group.id):checked.delete(group.id);trashButton.disabled=assetBusy||!checked.size;};
      const description=document.createElement('span');const title=document.createElement('strong'),files=document.createElement('small');
      title.textContent=(group.status==='history'?'历史备份引用过 · ':'未被引用 · ')+group.id+' · '+formatBytes(group.total_bytes);
      files.textContent=group.files.map(f=>f.name).join(' + ');
      description.append(title,files);label.append(checkbox,description);list.append(label);
     }resultArea.append(list);trashButton.hidden=false;trashButton.disabled=true;
    }else{const empty=document.createElement('p');empty.textContent='目前没有适合整理的附件；工程原件均保持不变。';resultArea.append(empty);trashButton.hidden=true;}
    if(scan.batches?.length){
     const head=document.createElement('p');head.className='asset-housekeeping-summary';head.textContent='项目回收区（可恢复）';batchesArea.append(head);
     for(const batch of scan.batches){
      const row=document.createElement('div');row.className='asset-housekeeping-batch';
      const label=document.createElement('span');label.textContent=batch.file_count+' 个文件 · '+formatBytes(batch.total_bytes)+' · '+batch.created_at.slice(0,16).replace('T',' ');
      const restore=document.createElement('button');restore.type='button';restore.className='btn btn-quiet';restore.textContent='恢复';restore.setAttribute('aria-label','恢复回收批次 '+batch.batch_id);
      restore.onclick=async()=>{
       try{checkSafe();if(!await ReportDialogs.confirm('将这批素材恢复到当前项目 assets/。若有同名文件，恢复会被拒绝。',{title:'恢复素材',okText:'恢复'}))return;
        assetButtons(true);await assetAction('restore',{batch_id:batch.batch_id});toast('已恢复 '+batch.file_count+' 个附件到 assets/');
        assetButtons(false);await refreshAssetScan();
       }catch(err){toast('恢复失败：'+err.message);}finally{assetButtons(false);}
      };
      row.append(label,restore);batchesArea.append(row);
     }
    }
   }
   async function refreshAssetScan(){
    try{checkSafe();assetButtons(true);resultArea.textContent='正在检查已保存的报告、草稿及历史备份…';
     lastScan=await assetAction('scan',{});renderSummary(lastScan);
    }catch(err){resultArea.textContent='素材检查：'+err.message;}
    finally{assetButtons(false);}
   }
   scanButton.onclick=refreshAssetScan;
    purgeButton.onclick=async()=>{
     try{
      checkSafe();const scanned=lastScan;if(!scanned?.trash?.batch_count)throw Error('请先检查回收区');
      const accepted=await ReportDialogs.confirm('永久删除本项目回收区的 '+scanned.trash.file_count+' 个附件（'+formatBytes(scanned.trash.total_bytes)+'），并清理 '+scanned.trash.batch_count+' 个回收批次。\n清空后无法恢复；历史备份如仍引用这些附件，也将无法显示。\n当前 assets/、正式报告和草稿不会被删除。',{title:'清空回收区',okText:'永久清空',danger:true});
      if(!accepted)return;
      checkSafe();assetButtons(true);
      const result=await assetAction('purge',{confirmed:true,trash_revision:scanned.trash.revision});
      toast('已清空回收区：'+result.removed_files+' 个附件 · '+formatBytes(result.removed_bytes));
     }catch(err){toast('清空未完成：'+err.message);}finally{assetButtons(false);await refreshAssetScan();}
    };
   trashButton.onclick=async()=>{
    try{
     checkSafe();if(!lastScan||!checked.size)throw Error('请先扫描并勾选要整理的素材');
     const picked=lastScan.groups.filter(group=>checked.has(group.id));
     const bytes=picked.reduce((sum,group)=>sum+group.total_bytes,0);
     const risky=picked.some(group=>group.status==='history');
     let detail='准备把 '+picked.length+' 组素材（'+formatBytes(bytes)+'）移入本项目 .asset-trash/ 回收区。\n不会直接永久删除，且不会更改 report.md。继续吗？';
     if(risky)detail+='\n\n注意：其中有历史版本引用过的图片。移走后，历史 Markdown 可能暂时无法显示这些图（可以从回收区恢复）。';
     if(!await ReportDialogs.confirm(detail,{title:'移入回收区',okText:'移入回收区',danger:risky}))return;
     if(risky&&!await ReportDialogs.confirm('已了解历史报告可能引用这些原始图形，仍然移入回收区？',{title:'再次确认',okText:'仍然移入',danger:true}))return;
     const selected=Object.fromEntries(picked.map(group=>[group.id,Object.fromEntries(group.files.map(file=>[file.name,file.sha256]))]));
     assetButtons(true);const response=await assetAction('trash',{selected,include_history:risky});
     toast('已移入回收区：'+response.moved_files+' 个附件，可在此窗口恢复');
     assetButtons(false);await refreshAssetScan();
    }catch(err){toast('整理失败：'+err.message);}finally{assetButtons(false);}
   };

   const snapshot=state.md;
   api('/api/export-preflight','POST',exportRequest(snapshot)).then(reply=>{
    if(snapshot!==state.md||!estimate.isConnected)return;
    estimate.textContent=`引用资源：${reply.asset_count} 个；原件合计 ${formatBytes(reply.source_bytes)}。\n可回编模式对适合的附件使用无损 Deflate；轻量预览若比原图更大则保留原图。\n导出将写入项目 output/，不会修改正式稿。`;
   }).catch(err=>{if(estimate.isConnected)estimate.textContent='导出前检查：'+err.message;});
  },onOk:async()=>{
   if(busy||assetBusy)return false;
   busy=true;
   const ok=$('modal-ok'),cancel=$('modal-cancel'),close=$('modal-close');
   ok.disabled=true;cancel.disabled=true;close.disabled=true;
   try{
    const selected={quality,sourceMode,includePdfOriginals};
    if(exportScope==='modules'){
     if(notebookModel.source!==state.md)throw Error('文稿已变化，请重新打开导出窗口选择专题');
     const stored=await exportModules([...selectedTopics],selected);exportPreferences=selected;
      exportToast('已写入项目 output/：'+stored.filename+' · '+stored.modules.length+' 个分册',stored);return true;
    }
    const snapshot=state.md,html=await buildExport(selected);
    if(snapshot!==state.md)throw Error('文稿变化，已取消导出');
    if(lastExportStats.totalBytes>31*1024*1024&&!await ReportDialogs.confirm('导出文件约 '+formatBytes(lastExportStats.totalBytes)+'，接近 36 MiB 兼容上限。仍要导出吗？',{title:'文件较大',okText:'仍然导出'}))return false;
    const stored=await api('/api/export/store','POST',{...lastExportRequest,html});
    exportPreferences=selected;
     exportToast(`已写入项目 output/：${stored.filename} · ${formatBytes(stored.bytes)} · 原始工程未改变`,stored);
    return true;
   }finally{busy=false;ok.disabled=false;cancel.disabled=false;close.disabled=false;}
  }});
 return result;
}
async function exportPDF(){
 try{commitSource();commitFocusedVisual();if(!await ensureProjectForExport())return;}catch(e){return toast('请先确认工程位置：'+e.message);}
 const btn=$('btn-pdf'),label=btn.innerHTML;btn.disabled=true;btn.textContent='正在生成 PDF…';status('','正在生成 PDF…');
 try{
  const snapshot=state.md,html=await buildExport({quality:'standard',sourceMode:'reading'});
  if(snapshot!==state.md)throw Error('编辑内容已改变，请重新导出');
  try{
   const stored=await api('/api/pdf/store','POST',{...lastExportRequest,html});
    exportToast('PDF 已保存到项目 output/：'+stored.filename+'；不会提交正式报告',stored);
  }catch(e){
   if(window.HRSHost)throw Error('内置 PDF 生成失败：'+e.message);
   const url=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'}));
   const win=window.open(url,'_blank');setTimeout(()=>URL.revokeObjectURL(url),90000);
   if(!win)toast('自动 PDF 失败，且弹窗被阻止：请点击打印按钮重试');
   else toast('自动 PDF 失败：已打开打印版；按 Ctrl+P 另存 PDF');
  }
 }catch(e){toast('PDF 导出失败：'+e.message);}
 finally{btn.disabled=false;btn.innerHTML=label;updateDirty();}
}
async function printSnapshot(){
 try{const html=await buildExport({quality:'standard',sourceMode:'reading'});
  if(window.HRSHost){await window.HRSHost.print(html);return;}
  const url=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'}));
  const win=window.open(url,'_blank');setTimeout(()=>URL.revokeObjectURL(url),90000);
  if(!win)toast('打印页弹窗被浏览器拦截');else toast('打印版已打开，Ctrl+P 后选择另存 PDF');
 }catch(e){toast('打印预览失败：'+e.message);}
}
let importingLocalFile=false;
async function importLocalFile(){
 if(importingLocalFile)return;
 try{
  importingLocalFile=true;$('btn-import').disabled=true;
  const before={markdown:state.md,session:state.session};
  let result;
  try{result=await api('/api/import/local-file','POST',{}, {'X-HRS-Project-Action':'user-action'});}
  catch(error){if(error.status===501){$('file-import').click();return;}throw error;}
  if(result.cancelled)return;
  if(before.markdown!==state.md||before.session!==state.session)throw Error('选择文件期间当前文稿已变化，导入已取消');
  if(result.kind==='markdown')await importFile({name:result.filename},{prepared:result});
  else await importFile(new File([result.source],result.filename,{type:'text/html'}));
 }catch(error){toast('导入失败：'+error.message);}
 finally{importingLocalFile=false;$('btn-import').disabled=false;}
}
async function importFile(file,{prepared=null}={}){
 try{
  let md,assets={},sourceTemplate='engineering',archiveVersion=null;
  if(prepared){
   md=prepared.markdown;assets=prepared.assets;
   file._hrsRenderProfile='free';file._hrsRenderOptions=ReportProfile.newOptions('free');file._hrsColorTheme=state.colorTheme;
  }else if(/\.html?$/i.test(file.name)){
   const source=await file.text(),inert=document.createElement('template');inert.innerHTML=source;
   const doc=inert.content,data=doc.getElementById('report-source');
   if(!data)throw Error('这不是由本工具导出的可重新编辑 HTML；普通 HTML 自由编辑仍属后续计划');
   const payload=JSON.parse(data.textContent);
   if(payload.format==='html-report-studio-v1'){
    md=payload.markdown;assets=payload.assets;
   }else if(payload.format==='html-report-studio-v2'){
    archiveVersion='v2';const restored=await ReportExportArchive.readArchive(payload,doc);
    md=restored.markdown;assets=restored.assets;
   }else throw Error('HTML 源数据版本不兼容');
   sourceTemplate=['engineering','academic','brief','blank'].includes(payload.template)?payload.template:'engineering';
   file._hrsRenderProfile=ReportProfile.normalize(payload.renderProfile);file._hrsRenderOptions=ReportProfile.normalizeOptions(payload.renderOptions);file._hrsColorTheme=ReportTheme.normalize(payload.colorTheme);
  }else{
   if(!await askLeave())return;
   md=await file.text();await load('new',sourceTemplate);
   state.renderProfile='free';state.renderOptions=ReportProfile.newOptions('free');$('render-profile').value='free';syncRenderControls();
   if(!await objectClipboard.importMarkdown(md))return;
   await render();toast('已导入 Markdown 及所选本地图片；尚未正式保存。');return;
  }
  if(!await askLeave())return;
  const did=freshID();
  const res=await api('/api/draft-import','POST',{draft_id:did,document_id:'new',template:sourceTemplate,markdown:md,assets,archive_version:archiveVersion,render_profile:file._hrsRenderProfile||'free',render_options:file._hrsRenderOptions,color_theme:file._hrsColorTheme});
  await load('new',sourceTemplate);
  state.draftId=did;state.draftSeq=res.seq;state.renderProfile=file._hrsRenderProfile||'free';state.renderOptions=ReportProfile.normalizeOptions(file._hrsRenderOptions);$('render-profile').value=state.renderProfile;syncRenderControls();
  await setColorTheme(ReportTheme.normalize(file._hrsColorTheme));
  changed(md,'import');await render();
  toast('已导入为未保存草稿；按 Ctrl+S 才创建正式报告。');
 }catch(e){toast('导入失败：'+e.message);}
}
async function preflightCurrent(source=state.md,profile=state.renderProfile,options=state.renderOptions){
 const current=state.md,session=state.session;
 const contract=await api('/api/validate','POST',{markdown:source,render_profile:profile});
 if(current!==state.md||session!==state.session)throw Error('STALE_SNAPSHOT：检查期间文稿已变化');
 return ReportPreflight.complete(contract,documentModel(source),profile,options);
}
async function validateCurrent(){
 commitSource();commitFocusedVisual();
 const source=state.md,session=state.session,sequence=++checkSequence;
 try{await render();const reply=await preflightCurrent(source);
  if(sequence!==checkSequence||session!==state.session)return;
  if(source!==state.md){toast('文稿已变化，请重新检查');return;}
  checks={source,reply};$('problems-panel').hidden=false;$('problem-list').replaceChildren();
  const errors=reply.diagnostics.filter(x=>x.severity==='error').length,warnings=reply.diagnostics.length-errors;
  $('problems-summary').textContent=`${errors} 个错误 · ${warnings} 个提醒`;
  for(const problem of reply.diagnostics){
   const item=document.createElement('li'),button=document.createElement('button');button.type='button';button.className='problem-item';button.dataset.code=problem.code;button.dataset.severity=problem.severity;
   for(const [className,text] of [['problem-severity',problem.severity==='error'?'错误':'提醒'],['problem-line',`第 ${problem.line} 行`],['problem-message',problem.message]]){const span=document.createElement('span');span.className=className;span.textContent=text;button.append(span);}
   button.onclick=async()=>{if(checks?.source!==state.md)return invalidateChecks();try{
    const range=positionMap.problemRange(problem,reply.offset_unit);await locateRange(range,{detail:`第 ${problem.line} 行 · ${problem.code} · ${problem.message}`});
    $('problem-list').querySelectorAll('button').forEach(el=>el.classList.toggle('selected',el===button));
   }catch(error){toast(error.message);}};item.append(button);$('problem-list').append(item);
  }
  if(!reply.diagnostics.length){const empty=document.createElement('li');empty.className='problem-empty';empty.textContent='结构检查通过，没有发现问题。';$('problem-list').append(empty);}
  if(reply.valid)toast(`结构检查通过：${reply.object_count} 个对象，${reply.diagnostics.length} 条提醒`);
  else toast('结构检查失败：'+reply.diagnostics.filter(x=>x.severity==='error').slice(0,2).map(x=>`第${x.line}行 ${x.message}`).join('；'));
  const panel=$('bottom-right');panel.textContent=`结构检查：${reply.valid?'通过':'失败'} · 错误 ${reply.diagnostics.filter(x=>x.severity==='error').length} · 提醒 ${reply.diagnostics.filter(x=>x.severity==='warning').length}`;
 }catch(e){if(sequence===checkSequence&&session===state.session)toast('结构检查服务不可用：'+e.message);}
}
// Grouped top-bar menus (open / save options / export). The lists are fixed-
// positioned so the narrow-window scrolling top bar cannot clip them.
function initTopMenus(){
 const menus=[...document.querySelectorAll('details.top-menu')];
 const place=menu=>{
  const list=menu.querySelector('.top-menu-list'),box=menu.querySelector('summary').getBoundingClientRect();
  const width=list.offsetWidth||280;
  const left=list.classList.contains('align-right')?box.right-width:box.left;
  list.style.left=Math.max(8,Math.min(left,innerWidth-width-8))+'px';
  list.style.top=(box.bottom+6)+'px';
 };
 for(const menu of menus){
  menu.addEventListener('toggle',()=>{
   if(!menu.open)return;
   menus.forEach(other=>{if(other!==menu)other.open=false;});
   place(menu);
   menu.querySelector('.menu-item:not([disabled])')?.focus({preventScroll:true});
  });
  menu.querySelectorAll('.menu-item').forEach(item=>item.addEventListener('click',()=>{menu.open=false;}));
  menu.addEventListener('keydown',event=>{
   if(event.key==='Escape'&&menu.open){event.preventDefault();menu.open=false;menu.querySelector('summary').focus();return;}
   if(event.key!=='ArrowDown'&&event.key!=='ArrowUp')return;
   const items=[...menu.querySelectorAll('.menu-item:not([disabled])')];if(!items.length)return;
   event.preventDefault();
   if(!menu.open){menu.open=true;return;}
   const at=items.indexOf(document.activeElement);
   items[(at+(event.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();
  });
 }
 document.addEventListener('click',event=>{menus.forEach(menu=>{if(menu.open&&!menu.contains(event.target))menu.open=false;});});
 window.addEventListener('resize',()=>menus.forEach(menu=>{if(menu.open)place(menu);}));
}
// Grouped editing tools (formula / image / diagram / reference) share one menu style.
function initToolPickers(){
 const pickers=[...document.querySelectorAll('details.tool-picker')];
 for(const picker of pickers){
  const menu=picker.querySelector('.tool-menu'),summary=picker.querySelector('summary');
  summary.addEventListener('mousedown',event=>event.preventDefault()); // keep the editor selection
  picker.addEventListener('toggle',()=>{
   if(!picker.open)return;
   pickers.forEach(other=>{if(other!==picker)other.open=false;});
   const box=summary.getBoundingClientRect(),width=menu.offsetWidth||220,height=menu.offsetHeight||160;
   menu.style.left=Math.max(8,Math.min(box.left,innerWidth-width-8))+'px';
   menu.style.top=Math.max(8,Math.min(innerHeight-height-8,box.bottom+5))+'px';
  });
  menu.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{picker.open=false;}));
  picker.addEventListener('keydown',event=>{if(event.key==='Escape'&&picker.open){event.preventDefault();picker.open=false;summary.focus();}});
 }
 document.addEventListener('click',event=>{pickers.forEach(picker=>{if(picker.open&&!picker.contains(event.target))picker.open=false;});});
}
function init(){
 window.HRSHost?.onClose(prepareWindowExit);
 window.HRSHost?.onCommand(command=>{if(command==='print')printSnapshot();else if(command==='pdf')exportPDF();});
 if(window.HRSHost){
  $('btn-pdf').querySelector('small').textContent='使用内置渲染内核，写入项目 output/';
  $('btn-print').querySelector('small').textContent='使用内置渲染内核打开系统打印对话框';
 }
 for(const [id,choices] of [['color-theme',ReportSettings.color_themes.choices],['render-profile',ReportSettings.render_profiles.choices]]){
  $(id).replaceChildren(...choices.map(item=>new Option(item.label,item.id)));
 }
 for(const label of document.querySelectorAll('[data-render-option-label]'))label.textContent=ReportSettings.render_options[label.dataset.renderOptionLabel].label;
 window.addEventListener('beforeunload',e=>{
  if(state.exitReady)return;
  commitSource();commitFocusedVisual();
  if(state.dirty||state.visualPending||state.saving){clearTimeout(debounceDraft);queueDraft();e.preventDefault();e.returnValue='';}
 });
 document.addEventListener('visibilitychange',()=>{if(document.hidden){commitSource();commitFocusedVisual();clearTimeout(debounceDraft);queueDraft();}});
 window.addEventListener('pagehide',()=>{
  if(state.exitReady){portableWindow?.leave(null);return;}
  commitSource();commitFocusedVisual();
  const payload=state.dirty&&!state.saving&&state.draftId?{draft_id:state.draftId,document_id:state.documentId,template:state.template,
   base_revision:state.revision,seq:++state.draftSeq,markdown:state.md,render_profile:state.renderProfile,render_options:state.renderOptions,color_theme:state.colorTheme}:null;
  if(portableWindow?.leave(payload,state.draftSnapshot))return;
  if(!payload)return;
  try{
   navigator.sendBeacon('/api/draft',new Blob([JSON.stringify(payload)],{type:'application/json'}));
  }catch{}
 });
 editor.addEventListener('input',e=>{if(!e.isComposing)changed(editor.value,'typing',true);});
 editor.addEventListener('compositionend',()=>changed(editor.value,'typing',true));
 editor.addEventListener('keydown',e=>{if(e.key==='Tab'){e.preventDefault();const top=editor.scrollTop,left=editor.scrollLeft;
  editor.setRangeText('    ',editor.selectionStart,editor.selectionEnd,'end');changed(editor.value,'insert',true);
  editor.scrollTop=top;editor.scrollLeft=left;}});
 document.querySelectorAll('[data-view]').forEach(btn=>btn.addEventListener('click',()=>switchView(btn.dataset.view)));
 document.querySelectorAll('[data-insert]').forEach(btn=>{
   btn.addEventListener('mousedown',ev=>{syncPreviewSelection();ev.preventDefault();}); // retain the actual preview/source selection
  btn.addEventListener('click',()=>{insertCommand(btn.dataset.insert);if(btn.closest('#heading-picker'))$('heading-picker').open=false;if(btn.closest('#list-picker'))$('list-picker').open=false;});
 });
 document.querySelectorAll('[data-list-style]').forEach(btn=>{
  btn.addEventListener('mousedown',e=>e.preventDefault());
  btn.addEventListener('click',()=>{insertStyledList(btn.dataset.listStyle);$('list-picker').open=false;});
 });
 const highlighter=$('highlight-picker'),highMenu=highlighter.querySelector('.highlight-menu');
 const clear=highMenu.querySelector('[data-highlight-color="clear"]');
 for(const choice of ReportSettings.highlights.choices){
  const button=document.createElement('button'),swatch=document.createElement('i');button.className='tool';button.dataset.highlightColor=choice.id;button.setAttribute('role','menuitem');
  swatch.className='highlight-swatch';swatch.style.backgroundColor=choice.color;button.append(swatch,document.createTextNode(choice.label));highMenu.insertBefore(button,clear);
 }
 const placeHighlight=()=>{if(!highlighter.open)return;const rect=highlighter.querySelector('summary').getBoundingClientRect();highMenu.style.left=Math.max(8,Math.min(rect.left,innerWidth-highMenu.offsetWidth-8))+'px';highMenu.style.top=Math.max(8,Math.min(rect.bottom+5,innerHeight-highMenu.offsetHeight-8))+'px';};
 highlighter.addEventListener('toggle',placeHighlight);highlighter.querySelector('summary').addEventListener('mousedown',e=>e.preventDefault());
 window.addEventListener('resize',placeHighlight);document.addEventListener('scroll',placeHighlight,true);
 document.querySelectorAll('[data-highlight-color]').forEach(btn=>{
  btn.addEventListener('mousedown',e=>e.preventDefault());
  btn.addEventListener('click',()=>{insertHighlight(btn.dataset.highlightColor);$('highlight-picker').open=false;});
 });
 document.addEventListener('click',e=>{if(!$('highlight-picker').contains(e.target))$('highlight-picker').open=false;});
 document.addEventListener('keydown',e=>{if(e.key==='Escape')$('highlight-picker').open=false;});
 const listPicker=$('list-picker'),listMenu=$('list-menu');
 listPicker.addEventListener('toggle',()=>{
  if(!listPicker.open)return;
  const rect=listPicker.querySelector('summary').getBoundingClientRect();
  listMenu.style.left=Math.max(8,Math.min(rect.left,innerWidth-230))+'px';
  listMenu.style.top=Math.max(8,Math.min(innerHeight-235,rect.bottom+5))+'px';
 });
 document.addEventListener('click',e=>{if(!listPicker.contains(e.target))listPicker.open=false;});
 document.addEventListener('keydown',e=>{if(e.key==='Escape')listPicker.open=false;});
 const headingPicker=$('heading-picker'),headingMenu=$('heading-menu');
 headingPicker.addEventListener('toggle',()=>{
  if(!headingPicker.open)return;
  const box=headingPicker.querySelector('summary').getBoundingClientRect();
  headingMenu.style.left=Math.max(8,Math.min(box.left,innerWidth-264))+'px';
  headingMenu.style.top=Math.max(8,Math.min(innerHeight-245,box.bottom+5))+'px';
 });
 document.addEventListener('click',event=>{if(!headingPicker.contains(event.target))headingPicker.open=false;});
 document.addEventListener('keydown',event=>{if(event.key==='Escape')headingPicker.open=false;});
 initTopMenus();initToolPickers();
 $('btn-undo').addEventListener('click',undo);$('btn-redo').addEventListener('click',redo);
 $('btn-save').addEventListener('click',()=>save(true).then(()=>toast('正式保存成功')).catch(e=>toast('保存失败：'+e.message)));
 $('btn-project-open').addEventListener('click',openProjectFolder);
 $('btn-project-migrate').addEventListener('click',()=>migrateProject().catch(e=>toast('项目迁移失败：'+e.message)));
 $('btn-new').addEventListener('click',newDocument);
 $('btn-recent').addEventListener('click',refreshRecent);
 $('btn-export').addEventListener('click',exportFile);
 $('btn-export-word').addEventListener('click',async()=>{
  await presentationWait;
  if(state.renderProfile==='free'){try{await prepareReportWorkspace();}catch(e){toast('准备工程报告失败：'+e.message);}return;}
  if(state.saving)return toast('保存中，请稍后导出');
  commitSource();commitFocusedVisual();
  try{
   if(!await ensureProjectForExport())return;
   await ReportWordExport.open({api,modal,toast,validate:async()=>{
    await validateCurrent();if(!checks||checks.source!==state.md)throw Error('当前文稿尚未完成检查，请重试');
    const problem=checks.reply.diagnostics.find(d=>d.severity==='error');if(problem)throw Error(problem.message);
    return checks.reply;
   },getRequest:()=>{
    commitSource();commitFocusedVisual();return exportRequest(state.md);
   }});
  }catch(error){toast('Word 导出失败：'+error.message);}
 });
 $('btn-workspace-check').onclick=validateCurrent;
 $('btn-prepare-report').onclick=()=>prepareReportWorkspace({force:true}).catch(e=>toast('准备工程预览失败：'+e.message));
 $('btn-workspace-sync').onclick=()=>syncReportOrigin().catch(e=>toast('同步未完成：'+e.message));
 $('btn-workspace-save').onclick=()=>saveReportIndependent().catch(e=>toast(e.message));
 $('btn-workspace-archive').onclick=()=>manageCurrentReport('archive').catch(e=>toast(e.message));
 $('btn-workspace-trash').onclick=()=>manageCurrentReport('trash').catch(e=>toast(e.message));
 $('btn-workspace-export').onclick=()=>$('btn-export-word').click();
 $('btn-workspace-return').onclick=()=>returnToReportOrigin().catch(e=>toast('返回未完成：'+e.message));
 $('btn-pdf').addEventListener('click',exportPDF);
 $('btn-print').addEventListener('click',printSnapshot);
 $('btn-exit').addEventListener('click',saveDraftAndExit);
 $('btn-rebuild-toc').addEventListener('click',()=>render());
 $('btn-validate').addEventListener('click',validateCurrent);
 $('btn-problems-close').addEventListener('click',()=>{$('problems-panel').hidden=true;});
 $('btn-fold-all').addEventListener('click',()=>{scrollFollow.suspend();editor.foldAll();});
 $('btn-unfold-all').addEventListener('click',()=>{scrollFollow.suspend();editor.unfoldAll();});
 $('btn-import').addEventListener('click',importLocalFile);
 $('file-import').addEventListener('change',async e=>{const f=e.target.files[0];if(f)await importFile(f);e.target.value='';});
 $('file-image').addEventListener('change',async e=>{
  const files=[...e.target.files];e.target.value='';if(!files.length)return;
  const svgs=files.filter(file=>file.name.toLowerCase().endsWith('.svg'));
  const pdfs=files.filter(file=>file.name.toLowerCase().endsWith('.pdf'));
  if(svgs.length>1||pdfs.length>1||svgs.length&&pdfs.length)return toast('每次只能选一个 SVG 或 PDF 原件');
  const primary=svgs[0]||pdfs[0]||files[0];
  if(files.length>1&&!svgs.length&&!pdfs.length)return toast('一次导入一张图片，或将 SVG/PDF 和关联图片一起选中');
  if(pdfs.length&&files.length>1&&(files.length!==2||files.filter(f=>f!==primary)[0].name.toLowerCase().endsWith('.png')===false))
   return toast('PDF 可同时选择一张 PNG 备用预览；其他文件请分别导入');
  await insertImage(primary,files.filter(file=>file!==primary));
 });
 $('btn-paste-graphic').addEventListener('mousedown',event=>event.preventDefault());
 $('btn-paste-graphic').addEventListener('click',()=>{if(!sourceEditRequested())pasteNativeGraphic({manual:true});});
 editor.addEventListener('paste',handleGraphicsPaste);
 // When the source isn't focused, the toolbar provides an explicit paste
 // action. Don't hijack ordinary contentEditable/table/modal clipboard flows.
 document.addEventListener('paste',event=>{
  if(state.view==='reading'||editor.hasFocus()||!$('modal-layer').hidden||document.activeElement?.isContentEditable)return;
  handleGraphicsPaste(event);
 });
 document.addEventListener('keydown',e=>{
  if(!$('modal-layer').hidden||ReportDialogs.isOpen())return; // allow native text editing undo in a modal
  if(state.exiting||workspaceBusy||operations.editing){e.preventDefault();return;}
  if((e.ctrlKey||e.metaKey)&&e.altKey&&e.key.toLowerCase()==='m'&&editor.hasFocus()){e.preventDefault();insertInlineMath();return;}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();save(true).catch(err=>toast('保存失败：'+err.message));}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='e'){e.preventDefault();exportFile();}
  if((e.ctrlKey||e.metaKey)&&(editor.hasFocus()||!document.activeElement?.isContentEditable)&&e.key.toLowerCase()==='z'){
   e.preventDefault();if(e.shiftKey)redo();else undo();
  }
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'&&(editor.hasFocus()||!document.activeElement?.isContentEditable)){e.preventDefault();redo();}
  if((e.ctrlKey||e.metaKey)&&['b','i'].includes(e.key.toLowerCase())&&editor.hasFocus()){e.preventDefault();insertCommand(e.key.toLowerCase()==='b'?'bold':'italic');}
 });
 $('render-profile').addEventListener('change',async()=>{
   const previous=state.renderProfile,selected=$('render-profile').value,session=state.session;
   try{commitSource();commitFocusedVisual();const options=selected==='free'&&!state.hasNumberPreference?ReportProfile.newOptions('free'):state.renderOptions;await persistPresentation({render_profile:selected,render_options:options},async()=>{state.renderOptions=options;state.renderProfile=selected;syncRenderControls();invalidateChecks();await render();await queueDraft();});}
   catch(error){if(session===state.session){$('render-profile').value=previous;toast(error.message);}}
  });
 $('color-theme').addEventListener('change',async()=>{
  const previous=state.colorTheme,session=state.session;
  try{const selected=ReportTheme.normalize($('color-theme').value);await persistPresentation({color_theme:selected},async()=>{await setColorTheme(selected);await queueDraft();});}
  catch(error){if(session===state.session){await setColorTheme(previous);try{await persistPresentation({color_theme:previous});}catch(rollback){toast(error.message+'；恢复配色设置失败：'+rollback.message);return;}toast(error.message);}}
 });
 for(const [control,option] of RENDER_CONTROLS)$(control).addEventListener('change',async()=>{
  commitSource();commitFocusedVisual();
  const previous=state.renderOptions,session=state.session;state.renderOptions={...state.renderOptions,[option]:$(control).checked};
  state.hasNumberPreference=true;
  try{await persistPresentation({},async()=>{await render();await queueDraft();});}
  catch(error){if(session===state.session){state.renderOptions=previous;syncRenderControls();toast(error.message);}}
 });
  previewImages=ReportPreviewImages.attach({preview,scroller:preview.closest('.page-scroll'),capture:previewViewportAnchor,restore:restorePreviewViewport});
  $('topic-select').onchange=async()=>{try{commitSource();commitFocusedVisual();const model=documentModel(state.md),topic=model.notebook.topics.find(t=>t.key===$('topic-select').value);focusTopic(topic,model);await render();if(topic)await locateRange({start:topic.start,end:topic.start},{origin:'reference'});else preview.closest('.page-scroll').scrollTop=0;}catch(error){toast(error.message);}};
  initScrollFollow();bindPreview();
  documentSearch=ReportDocumentSearch.attach({panel:$('document-search'),button:$('btn-search'),editor,preview,
   getSource:()=>state.md,getView:()=>state.view,onError:toast,
   canOpen:()=>!state.exiting&&$('modal-layer').hidden&&!ReportDialogs.isOpen()&&$('reader-overlay').hidden,
   prepare:async scope=>{
    commitFocusedVisual();scrollFollow?.suspend();
    if(scope==='source'&&state.view==='reading'||scope==='preview'&&state.view==='source')await switchView('split');
    if(scope==='preview'&&topicFocus){focusTopic(null);await render();}
    if(positionMap?.source!==state.md)await render();
   },revealSource:match=>locateRange(match,{origin:'reference'})});
 const ready=Promise.all([api('/api/health').then(identity=>{const badge=$('release-badge');badge.textContent=identity.release;badge.title='HTML Report Studio '+identity.release+' · 独立 Word beta';}),load('new','engineering')]).then(()=>promptRecovery());
 // Explicit local automation context only. The normal editor receives no new
 // controls or workflow. Export retains the original renderer, archive and
 // snapshot/asset preflight checks; this boundary never saves the report.
 if(new URLSearchParams(location.search).get('programmatic')==='1'){
  let busy=false;
  window.ReportStudioProgrammatic=Object.freeze({
   schema:'hrs-programmatic-v1',
   check:async({renderProfile=state.renderProfile,renderOptions=state.renderOptions,expectSourceSha256}={})=>{await ready;if(busy||workspaceBusy||operations.editing)throw Error('Programmatic operation in progress');busy=true;try{const source=state.md;if(expectSourceSha256&&expectSourceSha256!==await ReportExportArchive.hash(new TextEncoder().encode(source)))throw Error('STALE_SNAPSHOT');return await preflightCurrent(source,renderProfile,renderOptions);}finally{busy=false;}},
   topics:async()=>{await ready;if(busy||workspaceBusy||operations.editing)throw Error('工作页正在切换，请稍候');const source=state.md,model=documentModel(source),documentId=state.documentId,revision=state.revision;return {documentId,revision,sourceSha256:await ReportExportArchive.hash(new TextEncoder().encode(source)),topics:model.notebook.topics.map(t=>({...t}))};},
   exportModules:async(keys,preferences={quality:'original'})=>{await ready;if(busy||workspaceBusy||operations.editing)throw Error('Programmatic operation in progress');busy=true;try{if(preferences.expectSourceSha256!==await ReportExportArchive.hash(new TextEncoder().encode(state.md)))throw Error('专题源快照已变化，请重新取得专题列表');return await exportModules(keys,preferences);}finally{busy=false;}},
   ready:()=>ready,
   open:async id=>{await ready;if(busy||workspaceBusy||operations.editing)throw Error('Programmatic operation in progress');busy=true;try{await load(id,'engineering',{recover:false});return {documentId:state.documentId,revision:state.revision};}finally{busy=false;}},
   exportHTML:async preferences=>{await ready;if(busy||workspaceBusy||operations.editing)throw Error('Programmatic operation in progress');busy=true;try{return await buildExport(preferences);}finally{busy=false;}}
  });
 }
 portableWindow?.start();
}
init();
})();
