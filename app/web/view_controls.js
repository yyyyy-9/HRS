/* Local display preferences only. Document source, output and renderer identity stay separate. */
(function(root){
'use strict';
function preferences(storage){
 const rules=root.ReportSettings.view_options,key=rules.storage_key;
 const read=name=>{try{return storage.getItem(name);}catch{return null;}};
 let saved;try{saved=JSON.parse(read(key)||'null');}catch{}
 const original=saved&&typeof saved==='object'&&!Array.isArray(saved)?saved:null;
 saved=original||{};
 const bounded=(value,rule,whole=true)=>typeof value==='number'&&Number.isFinite(value)?Math.max(rule.min,Math.min(rule.max,whole?Math.round((value-rule.min)/rule.step)*rule.step+rule.min:value)):rule.default;
 const legacyWrap=read('hrs-source-wrap'),legacyRatio=read('hrs-source-ratio');
 const values={source_font_size:bounded(saved.source_font_size,rules.source_font_size),
  source_wrap:typeof saved.source_wrap==='boolean'?saved.source_wrap:!original&&legacyWrap!==null?legacyWrap!=='false':rules.source_wrap.default,
  source_ratio:bounded(!original&&legacyRatio!==null?Number(legacyRatio):saved.source_ratio,rules.source_ratio,false),
  preview_zoom:rules.preview_zoom.choices.includes(saved.preview_zoom)?saved.preview_zoom:rules.preview_zoom.default};
 function persist(){try{storage.setItem(key,JSON.stringify(values));storage.removeItem('hrs-source-wrap');storage.removeItem('hrs-source-ratio');}catch{}}
 persist();
 return {rules,values,set(name,value){values[name]=name==='source_wrap'?!!value:name==='preview_zoom'?(rules.preview_zoom.choices.includes(value)?value:rules.preview_zoom.default):bounded(value,rules[name],name!=='source_ratio');persist();return values[name];}};
}
function attach({editor,preview,capture,restore,getSourceMap,setDisabled,getSourceRange=()=>null,suspend=()=>{},committed=()=>{}}){
 const doc=preview.ownerDocument,$=id=>doc.getElementById(id);
 let storage;try{storage=root.localStorage;}catch{}
 const prefs=preferences(storage),{rules,values}=prefs,host=editor.view.dom.closest('.source-code-editor');
 const wrap=$('source-wrap'),font=$('source-font-value'),smaller=$('source-font-decrease'),larger=$('source-font-increase');
 const zoom=$('preview-zoom'),stage=$('preview-scale-stage'),content=$('preview-scale-content'),scroller=preview.closest('.page-scroll');
 const zoomOut=$('preview-zoom-decrease'),zoomIn=$('preview-zoom-increase');
 const layout=$('edit-layout'),divider=$('split-divider'),foldButton=$('btn-source-fold');
 let frame=0,sourceRestore=0,dragging=false,destroyed=false;
 const api=root.SourceEditor.extensionAPI;
 let foldInput=null,foldState=null;
 function refreshFold(){
  const state=editor.view.state,blocks=state.field(api.sourceBlocks),ranges=api.foldedRanges(state),limit=getSourceRange()||{from:0,to:state.doc.length};
  if(foldInput?.blocks===blocks&&foldInput.ranges===ranges&&foldInput.from===limit.from&&foldInput.to===limit.to)return;
  foldInput={blocks,ranges,from:limit.from,to:limit.to};
  const visible=blocks.filter(block=>block.from>=limit.from&&block.to<=limit.to),folds=[];
  ranges.between(limit.from,limit.to,(from,to)=>folds.push({from,to}));
  let index=0,coveredTo=-1;
  const collapsed=visible.length>0&&visible.every(block=>{
   while(index<folds.length&&folds[index].from<=block.from)coveredTo=Math.max(coveredTo,folds[index++].to);
   return coveredTo>=block.to;
  });
  // load() releases its UI lease after rendering. Store the desired state in
  // that same lease; a direct DOM assignment would be replaced by its old value.
  foldState={visible,folds,collapsed};setDisabled(foldButton,!visible.length);
  foldButton.textContent=collapsed?'展开':'折叠';foldButton.dataset.foldState=!visible.length?'empty':collapsed?'collapsed':folds.length?'mixed':'expanded';
  foldButton.setAttribute('aria-label',(collapsed?'展开':'折叠')+'当前范围源码块');
  foldButton.title=visible.length?(collapsed?'展开':'折叠')+'当前范围的全部源码块':'当前范围没有可折叠的源码块';
 }
 // Observe the editor's authoritative ranges, including individual card actions
 // and its automatic folding transaction. Scope comes from the same projection.
 editor.view.dispatch({effects:api.StateEffect.appendConfig.of(api.EditorView.updateListener.of(()=>{if(!destroyed)refreshFold();}))});
 foldButton.onclick=()=>{
  refreshFold();if(!foldState.visible.length)return;suspend();
  const visible=new Set(foldState.visible.map(block=>block.from+':'+block.to));
  const effects=foldState.collapsed?foldState.folds.filter(fold=>visible.has(fold.from+':'+fold.to)).map(fold=>api.unfoldEffect.of(fold)):
   foldState.visible.map(block=>api.foldEffect.of({from:block.from,to:block.to}));
  editor.view.dispatch({effects});
 };
 refreshFold();
 function resizePaper(){
  if(!scroller.clientWidth)return;
  const css=getComputedStyle(scroller),paper=getComputedStyle(preview),available=scroller.clientWidth-parseFloat(css.paddingLeft)-parseFloat(css.paddingRight);
  const width=Math.min(available,parseFloat(paper.maxWidth)||available),scale=values.preview_zoom/100;
  if(width<=0)return;
  content.style.width=width+'px';content.style.transform=scale===1?'none':'scale('+scale+')';
  stage.style.width=width*scale+'px';stage.style.height=content.offsetHeight*scale+'px';
 }
 function layoutChange(action,{source=false}={}){
  suspend();const anchor=capture(),sourceAnchor=source?editor.viewportAnchor(getSourceMap()):null,oldZoom=values.preview_zoom;
  action();resizePaper();editor.requestMeasure();
  if(anchor?.node&&oldZoom!==values.preview_zoom){
   // Keep the same point inside the source block, not its previous physical
   // pixel offset. Otherwise old integer scrollTop implementations drift a
   // pixel on every round trip. The scroller's padding is outside the scale.
   const padding=parseFloat(getComputedStyle(scroller).paddingTop)||0;
   anchor.offset=padding+(anchor.offset-padding)*values.preview_zoom/oldZoom;
  }
  restore(anchor);committed();
  if(sourceAnchor){cancelAnimationFrame(sourceRestore);sourceRestore=requestAnimationFrame(()=>{sourceRestore=0;editor.scrollToBlock(sourceAnchor);});}
 }
 function setWrap(value){wrap.checked=prefs.set('source_wrap',value);host.classList.toggle('source-soft-wrap',wrap.checked);$('markdown').style.whiteSpace=wrap.checked?'pre-wrap':'pre';}
 function setFont(value){const size=prefs.set('source_font_size',value);host.style.setProperty('--source-font-size',size+'px');host.style.setProperty('--source-fixed-font-size',rules.source_font_size.default+'px');font.value=size+'px';setDisabled(smaller,size<=rules.source_font_size.min);setDisabled(larger,size>=rules.source_font_size.max);}
 function setRatio(value){const ratio=prefs.set('source_ratio',value);layout.style.setProperty('--source-ratio',ratio+'%');divider.setAttribute('aria-valuenow',String(Math.round(ratio)));}
 function setZoom(value){const current=prefs.set('preview_zoom',value),index=rules.preview_zoom.choices.indexOf(current);zoom.value=String(current);setDisabled(zoomOut,index===0);setDisabled(zoomIn,index===rules.preview_zoom.choices.length-1);}
 for(const value of rules.preview_zoom.choices){const option=doc.createElement('option');option.value=value;option.textContent=value+'%';zoom.append(option);}
 setZoom(values.preview_zoom);
 wrap.onchange=()=>layoutChange(()=>setWrap(wrap.checked),{source:true});
 smaller.onclick=()=>layoutChange(()=>setFont(values.source_font_size-rules.source_font_size.step),{source:true});
 larger.onclick=()=>layoutChange(()=>setFont(values.source_font_size+rules.source_font_size.step),{source:true});
 zoom.onchange=()=>layoutChange(()=>setZoom(Number(zoom.value)));
 zoomOut.onclick=()=>layoutChange(()=>setZoom(rules.preview_zoom.choices[rules.preview_zoom.choices.indexOf(values.preview_zoom)-1]));
 zoomIn.onclick=()=>layoutChange(()=>setZoom(rules.preview_zoom.choices[rules.preview_zoom.choices.indexOf(values.preview_zoom)+1]));
 setWrap(values.source_wrap);setFont(values.source_font_size);setRatio(values.source_ratio);resizePaper();
 function schedule(){if(!frame&&!destroyed)frame=requestAnimationFrame(()=>{frame=0;resizePaper();});}
 const observer=new ResizeObserver(schedule);observer.observe(scroller);observer.observe(content);
 divider.onpointerdown=event=>{if(event.button!==0)return;event.preventDefault();dragging=true;divider.setPointerCapture(event.pointerId);layout.classList.add('resizing');suspend();};
 divider.onpointermove=event=>{if(dragging){const box=layout.getBoundingClientRect();setRatio((event.clientX-box.left)/box.width*100);editor.requestMeasure();schedule();}};
 const stop=()=>{dragging=false;layout.classList.remove('resizing');editor.requestMeasure();schedule();};
 divider.onpointerup=stop;divider.onlostpointercapture=stop;divider.ondblclick=()=>layoutChange(()=>setRatio(rules.source_ratio.default));
 divider.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home'].includes(event.key))return;event.preventDefault();layoutChange(()=>setRatio(event.key==='Home'?rules.source_ratio.default:values.source_ratio+(event.key==='ArrowLeft'?-rules.source_ratio.step:rules.source_ratio.step)));};
 return {refresh(){resizePaper();refreshFold();},destroy(){destroyed=true;foldButton.onclick=null;observer.disconnect();cancelAnimationFrame(frame);cancelAnimationFrame(sourceRestore);}};
}
root.ReportViewControls={attach};
})(window);
