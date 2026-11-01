/* Formula dialog draft only. LaTeX remains the source; MathJax remains output. */
(function(root){
'use strict';
let loading=null;
async function fontsReady(){
 // MathLive loads detached FontFace objects and registers them only after
 // all have loaded. document.fonts.ready alone can resolve before that batch
 // is registered, leaving the first hit-test bounds based on fallback fonts.
 const deadline=performance.now()+10000;
 while(!Array.from(document.fonts).some(font=>font.family==='KaTeX_Caligraphic'&&font.status==='loaded')){
  if(performance.now()>deadline)throw Error('数学字体未就绪，请先编辑LaTeX源码');
  await new Promise(resolve=>setTimeout(resolve,20));
 }
 await document.fonts.ready;
}
function load(){
 if(loading)return loading;if(root.MathfieldElement)return fontsReady();
 loading=new Promise((resolve,reject)=>{
  const script=document.createElement('script');script.src='/web/vendor/mathlive/mathlive.min.js';
  const timer=setTimeout(()=>{script.remove();loading=null;reject(Error('可视公式编辑器加载超时，仍可编辑LaTeX源码'));},10000);
  script.onload=async()=>{
   clearTimeout(timer);root.MathfieldElement.fontsDirectory=new URL('/web/vendor/mathlive/fonts',location.href).href;root.MathfieldElement.soundsDirectory=null;
   // Desktop editing uses the physical keyboard and the dialog's structure
   // tools. Never open MathLive's separate screen keyboard over the document.
   root.mathVirtualKeyboard.addEventListener('before-virtual-keyboard-toggle',event=>{if(event.detail?.visible)event.preventDefault();});
   root.mathVirtualKeyboard.hide();
   try{await fontsReady();resolve();}catch(error){loading=null;reject(error);}
  };
  script.onerror=()=>{clearTimeout(timer);script.remove();loading=null;reject(Error('可视公式编辑器未加载，仍可编辑LaTeX源码'));};
  document.head.append(script);
 });return loading;
}
const templates=[
 ['分式','\\frac{分子}{分母}',['分子','分母'],'\\frac{#0}{#1}','\\frac{a}{b}'],
 ['上标','{底数}^{指数}',['底数','指数'],'{#0}^{#1}','x^n'],
 ['下标','{主体}_{下标}',['主体','下标'],'{#0}_{#1}','a_j'],
 ['根号','\\sqrt{内容}',['内容'],'\\sqrt{#0}','\\sqrt{x}'],
 ['求和','\\sum_{下限}^{上限} 内容',['下限','上限','内容'],'\\sum_{#0}^{#1}#2','\\sum_{j=1}^{n}a_j'],
 ['积分','\\int_{下限}^{上限} 内容\\,\\mathrm{d}变量',['下限','上限','内容','变量'],'\\int_{#0}^{#1}#2\\,\\mathrm{d}#3','\\int_a^b f(x)\\,\\mathrm{d}x'],
 ['矩阵','\\begin{pmatrix}a & b \\\\\n c & d\\end{pmatrix}',['a','b','c','d'],'\\begin{pmatrix}#0&#1\\\\#2&#3\\end{pmatrix}','\\begin{pmatrix}a&b\\\\c&d\\end{pmatrix}'],
 ['分段函数','\\begin{cases}表达式一 & 条件一 \\\\\n表达式二 & 条件二\\end{cases}',['表达式一','条件一','表达式二','条件二'],'\\begin{cases}#0&#1\\\\#2&#3\\end{cases}','\\begin{cases}x&x>0\\\\0&x\\leq0\\end{cases}'],
 ['多行等号对齐','\\begin{aligned}左式一 &= 右式一 \\\\\n左式二 &= 右式二\\end{aligned}',['左式一','右式一','左式二','右式二'],'\\begin{aligned}#0&=#1\\\\#2&=#3\\end{aligned}','\\begin{aligned}a&=b+c\\\\x&=y\\end{aligned}'],
 ['粗体','\\boldsymbol{内容}',['内容'],'\\boldsymbol{#0}','\\boldsymbol{\\alpha}']
];
function sourceSnippet(field,text,words){
 const from=field.selectionStart,to=field.selectionEnd;
 field.setRangeText(text,from,to,'end');let cursor=0;
 const ranges=words.map(word=>{const at=text.indexOf(word,cursor);cursor=at+word.length;return {start:from+at,end:from+cursor};});
 field._formulaStops=ranges.length?{ranges,index:0,source:field.value}:null;field.focus();if(ranges.length)field.setSelectionRange(ranges[0].start,ranges[0].end);
 field.dispatchEvent(new Event('input',{bubbles:true}));
}
// Source-only row insertion uses TeX delimiters, not a mathematical parser.
// Only insert at the current array's own brace depth; never inside a script,
// fraction or text group. The visual field uses MathLive's native array command.
function rowContext(text,position){
 const stack=[];let depth=0;
 for(let i=0;i<position;i++){
  if(text[i]==='%'){const end=text.indexOf('\n',i);if(end<0||end>=position)break;i=end;continue;}
  if(text[i]==='\\'){
   const env=text.slice(i).match(/^\\(begin|end)\{([a-zA-Z*]+)\}/);
   if(env){if(i+env[0].length>position)return null;if(env[1]==='begin')stack.push({name:env[2],depth});else if(stack.at(-1)?.name===env[2])stack.pop();i+=env[0].length-1;}
   else if(/[A-Za-z]/.test(text[i+1]||'')){while(/[A-Za-z]/.test(text[i+1]||''))i++;}
   else i++;
  }else if(text[i]==='{')depth++;else if(text[i]==='}')depth--;
 }
 const env=stack.at(-1);return env&&env.depth===depth&&/^(?:aligned|alignedat|split|gathered|cases|[pbBvV]?matrix|array)$/.test(env.name)?env:null;
}
function mapStops(field){
 const state=field._formulaStops;if(!state)return;
 const before=state.source,after=field.value;let a=0,x=before.length,y=after.length;
 while(a<x&&a<y&&before[a]===after[a])a++;
 while(x>a&&y>a&&before[x-1]===after[y-1]){x--;y--;}
 const map=(position,end)=>position<a?position:position>x?position+y-x:position===a&&!end?a:y;
 state.ranges=state.ranges.map(range=>({start:map(range.start,false),end:map(range.end,true)}));state.source=after;
}
function scriptSelection(math){
 let gesture=null;
 const down=event=>{if(event.button===0&&!math.readOnly)gesture={id:event.pointerId,x:event.clientX,y:event.clientY,moved:false};};
 const move=event=>{if(gesture?.id===event.pointerId&&Math.hypot(event.clientX-gesture.x,event.clientY-gesture.y)>=5)gesture.moved=true;};
 const finish=event=>{
  const current=gesture;gesture=null;if(!current||current.id!==event.pointerId||!current.moved||math.readOnly)return;
  const selection=math.selection;if(selection.ranges.length!==1)return;
  const [start,end]=selection.ranges[0];if(end-start<3)return;
  const tex=math.getValue([start,end],'latex'),atom=math.getElementInfo(end);
  // Native dragging promotes an entire script's contents to the script
  // wrapper. For that one isolated atom, select its contents so typing a
  // replacement keeps it above/below the baseline. The public model must
  // confirm both the wrapper and exact inner serialization; spanning
  // selections and keyboard/select-all commands retain native behaviour.
  if(!atom||atom.latex!==tex||!['^','_'].includes(tex[0]))return;
  const inner=[start+1,end-1];
  if(tex!==tex[0]+'{'+math.getValue(inner,'latex')+'}')return;
  math.selection={ranges:[inner],direction:event.clientX<current.x?'backward':'forward'};
 };
 const cancel=()=>{gesture=null;};
 math.addEventListener('pointerdown',down,true);root.addEventListener('pointermove',move,true);
 root.addEventListener('pointerup',finish,true);root.addEventListener('pointercancel',cancel,true);
 return ()=>{cancel();math.removeEventListener('pointerdown',down,true);root.removeEventListener('pointermove',move,true);root.removeEventListener('pointerup',finish,true);root.removeEventListener('pointercancel',cancel,true);};
}
// One raw-TeX history for this dialog, never the document or the two native
// editors' separate stacks. Selections are metadata, not editing operations.
function draftHistory(initial,changed){
 let states=[initial],index=0,group=null,time=0;
 const notify=()=>changed(index>0,index<states.length-1);
 return {
  remember(state){
   const current=states[index];
   if(state.side!==current.side||JSON.stringify(state.side==='source'?state.source:state.visual)!==JSON.stringify(state.side==='source'?current.source:current.visual))group=null;
   if(state.tex===current.tex)states[index]=state;
  },
  boundary(){group=null;},
  record(state,key=null){
   if(state.tex===states[index].tex){states[index]=state;notify();return;}
   const now=performance.now(),merge=key&&key===group&&now-time<650&&index===states.length-1&&index>0;
   states.length=index+1;if(merge)states[index]=state;else{states.push(state);index++;}
   if(states.length>101){states.shift();index--;}
   group=key;time=now;notify();
  },
  step(direction,current){
   this.remember(current);this.boundary();const next=index+direction;
   if(next<0||next>=states.length)return null;index=next;notify();return states[index];
  }
 };
}
async function open({modal,tex,id,display,validate,render}){
 let field,idField,math,status,example,stopSelection,clock=0,serial=0,disposed=false,active='source',synchronizing=false,sourceDirty=false;
 let original=tex,draft=tex,history,undo,redo,scope,paintDraft,composing=false,toolDepth=0,inputKey=null,restoreVersion=0;
 const snapshot=()=>({tex:draft,side:active,source:{start:field.selectionStart,end:field.selectionEnd,direction:field.selectionDirection},
  stops:field._formulaStops?JSON.parse(JSON.stringify(field._formulaStops)):null,
  visual:math?JSON.parse(JSON.stringify(math.selection)):null});
 function buttons(canUndo,canRedo){undo.disabled=!canUndo||composing;redo.disabled=!canRedo||composing;}
 function remember(){history?.remember(snapshot());}
 function record(key=null){restoreVersion++;if(!composing&&!toolDepth)history.record(snapshot(),key);}
 function transaction(run){
  remember();history.boundary();toolDepth++;
  try{run();}finally{toolDepth--;record();}
 }
 function step(direction){
  if(composing||disposed)return;
  const target=history.step(direction,snapshot());if(!target)return;
  const version=++restoreVersion;clearTimeout(clock);draft=target.tex;field.value=draft;active=target.side;
  field._formulaStops=target.stops?JSON.parse(JSON.stringify(target.stops)):null;
  paintDraft();field.setSelectionRange(target.source.start,target.source.end,target.source.direction);
  if(active==='visual'&&math&&!math.readOnly){
   math.focus();if(target.visual)math.selection=target.visual;
   requestAnimationFrame(()=>{if(!disposed&&version===restoreVersion&&target.visual)math.selection=target.visual;});
  }else{field.closest('details').open=true;field.focus({preventScroll:true});}
 }
 function keys(event){
  if(event.isComposing||composing||!(event.ctrlKey||event.metaKey)||event.altKey)return;
  const key=event.key.toLowerCase();if(!['z','y'].includes(key))return;
  event.preventDefault();event.stopImmediatePropagation();step(key==='y'||event.shiftKey?1:-1);
 }
 function beforeInput(event){
  if(![field,math].includes(event.target))return;
  if(event.inputType==='historyUndo'||event.inputType==='historyRedo'){
   event.preventDefault();event.stopImmediatePropagation();step(event.inputType==='historyUndo'?-1:1);return;
  }
  if(composing||toolDepth)return;remember();
  inputKey=/^(?:insertText|deleteContentBackward|deleteContentForward)$/.test(event.inputType)?active+':'+event.inputType:null;
 }
 function compositionStart(event){if(![field,math].includes(event.target))return;remember();history.boundary();composing=true;undo.disabled=redo.disabled=true;}
 function compositionEnd(event){if(![field,math].includes(event.target))return;composing=false;record();}
 const dispose=()=>{
  disposed=true;clearTimeout(clock);stopSelection?.();
  if(scope){scope.removeEventListener('keydown',keys,true);scope.removeEventListener('beforeinput',beforeInput,true);scope.removeEventListener('compositionstart',compositionStart,true);scope.removeEventListener('compositionend',compositionEnd,true);}
  if(math){root.mathVirtualKeyboard?.hide();math.blur();math.remove();}
 };
 try{return await modal({title:'编辑公式',kicker:'可视编辑 · LaTeX',wide:true,
  headerActions:slot=>{
   const container=document.createElement('div');slot.append(container);
   container.className='formula-history';container.setAttribute('role','group');container.setAttribute('aria-label','公式撤销与重做');
   for(const [name,direction,shortcut] of [['撤销',-1,'Ctrl+Z'],['重做',1,'Ctrl+Y / Ctrl+Shift+Z']]){
    const button=document.createElement('button');button.type='button';button.className='source-fold-tool';button.textContent=name;button.title=name+' · '+shortcut;button.disabled=true;
    button.onmousedown=event=>event.preventDefault();button.onclick=()=>step(direction);container.append(button);if(direction<0)undo=button;else redo=button;
   }
  },
  note:'可直接编辑上方公式，或修改下方LaTeX，两侧同步；应用后写回当前公式，取消保留原稿。',
  body:outer=>{
   const panel=document.createElement('section');panel.className='formula-editor';
   status=document.createElement('p');status.className='modal-help';status.textContent='正在加载离线可视编辑器…';
   const visual=document.createElement('div');visual.className='formula-visual';
   const selectionTools=document.createElement('div');selectionTools.className='formula-selection-tools';
   const selectionHint=document.createElement('span');selectionHint.textContent='单击定位 · 拖动选择 · Shift+方向键扩选';selectionTools.append(selectionHint);
   const selectionButtons=[];
   for(const [name,command] of [['全选公式','selectAll']]){
    const button=document.createElement('button');button.type='button';button.className='tool';button.textContent=name;button.disabled=true;
    // Retain an existing math selection when the tool is clicked. Keyboard
    // activation can originate outside the field, so execute after its focus
    // handler, using MathLive's public selection commands.
    button.onmousedown=event=>event.preventDefault();button.onclick=()=>{
     if(!math||math.readOnly||disposed)return;math.focus();
     requestAnimationFrame(()=>{if(!disposed&&math.isConnected&&!math.readOnly)math.executeCommand(command);});
    };selectionButtons.push(button);selectionTools.append(button);
   }
   const tools=document.createElement('div');tools.className='formula-tools';tools.setAttribute('aria-label','公式结构');
   field=document.createElement('textarea');field.dataset.formulaSource='1';field.setAttribute('aria-label','LaTeX源码');field.value=tex;field.spellcheck=false;field.rows=5;
   const label=document.createElement('label');label.textContent='LaTeX 源码';label.append(field);
   example=document.createElement('div');example.className='modal-preview formula-final-preview';example.setAttribute('aria-label','最终排版预览');
   for(const [name,text,words,visualText,sample] of templates){
    const button=document.createElement('button');button.type='button';button.className='tool formula-structure';button.setAttribute('aria-label',name);
    const picture=document.createElement('span');picture.className='formula-structure-sample';picture.setAttribute('aria-hidden','true');
    const caption=document.createElement('span');caption.textContent=name;button.append(picture,caption);
    button.title=name==='分段函数'?'左大括号：每一行填写表达式与条件':name==='多行等号对齐'?'多行公式：每行的等号对齐':name;
    const multi=['矩阵','分段函数','多行等号对齐'].includes(name);
    if(multi&&!display){button.disabled=true;button.title='请在行间公式中使用多行结构';}
    // Reuse the existing MathJax renderer, not one MathLive instance per icon.
    render(sample,true).then(node=>{if(!disposed&&picture.isConnected)picture.append(node.cloneNode(true));}).catch(()=>{picture.textContent=sample;});
    button.onmousedown=event=>event.preventDefault();button.onclick=()=>transaction(()=>{
     if(active==='visual'&&math&&!math.readOnly){math.focus();math.insert(visualText,{selectionMode:'placeholder'});}
     else sourceSnippet(field,text,words);
    });tools.append(button);
   }
   const layoutTools=document.createElement('div');layoutTools.className='formula-layout-tools';layoutTools.setAttribute('aria-label','公式间距与换行');
   function action(name,title,run,disabled=false){
    const button=document.createElement('button');button.type='button';button.className='source-fold-tool';button.textContent=name;button.title=title;button.disabled=disabled;
    button.onmousedown=event=>event.preventDefault();button.onclick=()=>transaction(run);layoutTools.append(button);return button;
   }
   for(const [name,command,title] of [['窄空格','\\,','插入较窄的数学间距 \\,'],['宽空格','\\quad ','插入约一个字宽的数学间距 \\quad']]){
    action(name,title,()=>{
     if(active==='visual'&&math&&!math.readOnly){math.focus();math.insert(command);}
     else sourceSnippet(field,command,[]);
    });
   }
   const inlineReason='行内公式保持单行；需要多行时请插入行间公式';
   action('新增一行',display?'在矩阵、分段函数或多行对齐中新增一行；源码中在光标处插入 \\\\':inlineReason,()=>{
    if(active==='visual'&&math&&!math.readOnly){
     // At the root MathLive would silently create a displaylines wrapper.
     // Keep the explicit conversion action, and preserve existing array types.
     const info=math.getElementInfo(math.position),hasRows=/\\begin\{(?:aligned|alignedat|split|gathered|cases|[pbBvV]?matrix|array)\}/.test(math.value);
     math.focus();if(!hasRows||!(info?.depth>0)||!math.executeCommand('addRowAfter'))status.textContent='请先选择多行结构中的一格，或用“转为多行”保留原式并添加新行。';
    }else if(field.selectionStart===field.selectionEnd&&rowContext(field.value,field.selectionStart))sourceSnippet(field,'\\\\\n',[]);
    else status.textContent='请把光标放到多行结构的一行中，避开上下标、分子分母内部；普通公式可先“转为多行”。';
   },!display);
   action('转为多行',display?'保留整个原式作为第一行，增加可填写的第二行，不猜测等号位置':inlineReason,()=>{
    if(/\\begin\{(?:aligned|alignedat|split|gathered|cases|[pbBvV]?matrix|array)\}/.test(field.value)){
     status.textContent='当前公式已有多行结构，请在其中使用“新增一行”。';return;
    }
    const {tex:body,tags}=ReportEquations.presentation(field.value);
    const next='\\begin{aligned}\n'+body+'\n\\\\\n新行\n\\end{aligned}'+(tags.length?'\n'+tags.join('\n'):'');
    field.setSelectionRange(0,field.value.length);sourceSnippet(field,next,['新行']);
   },!display);
   const layoutHint=document.createElement('span');layoutHint.className='formula-layout-hint';layoutHint.textContent=display?'普通空格通常不显示；& 是列对齐位置，\\\\ 用于多行结构内换行。':'普通空格通常不显示；行内公式保持单行。';layoutTools.append(layoutHint);
   const sourceDetails=document.createElement('details');sourceDetails.className='formula-source-details';sourceDetails.open=true;
   const sourceTitle=document.createElement('summary');sourceTitle.textContent='LaTeX 源码';label.firstChild.remove();sourceDetails.append(sourceTitle,label);
   const previewTitle=document.createElement('span');previewTitle.className='formula-preview-title';previewTitle.textContent='文稿中的排版效果';
   panel.append(status,visual,selectionTools,tools,layoutTools,sourceDetails,previewTitle,example);outer.append(panel);
   if(display){
    const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='公式身份';
    idField=document.createElement('input');idField.setAttribute('aria-label','公式 ID');idField.value=id||'';idField.readOnly=!!id;idField.placeholder='未建立引用身份';
    details.append(summary,idField);outer.append(details);
   }
   async function paint(sync=true){
    const revision=++serial;clearTimeout(clock);
    if(sync&&math){
     sourceDirty=false;
     synchronizing=true;math.setValue(ReportEquations.presentation(field.value).tex,{silenceNotifications:true});synchronizing=false;
     const errors=math.errors||[],sourceOnly=errors.length||/\\(?:def|gdef|edef|newcommand|renewcommand|DeclareMathOperator|require|label)\b/.test(field.value);math.readOnly=!!sourceOnly;
     for(const button of selectionButtons)button.disabled=math.readOnly||math.dataset.ready!=='1';
     status.textContent=sourceOnly?'此写法请在LaTeX源码中编辑；原文完整保留。':'可点击分子、分母、上下标等位置直接编辑；也可在下方输入LaTeX。';
    }
    try{validate(field.value);const node=await render(field.value,display);if(!disposed&&revision===serial)example.replaceChildren(node.cloneNode(true));}
    catch(error){if(!disposed&&revision===serial)example.textContent='公式提示：'+error.message;}
   }
   paintDraft=paint;
   history=draftHistory(snapshot(),buttons);
   scope=outer.closest('.modal-window');scope.addEventListener('keydown',keys,true);scope.addEventListener('beforeinput',beforeInput,true);
   scope.addEventListener('compositionstart',compositionStart,true);scope.addEventListener('compositionend',compositionEnd,true);
   field.onfocus=()=>{if(active!=='source')history.boundary();active='source';};
   field.onpointerdown=()=>history.boundary();
   field.oninput=()=>{draft=field.value;sourceDirty=true;mapStops(field);record(inputKey);clearTimeout(clock);clock=setTimeout(()=>paint(),100);};
   field.onkeydown=event=>{
    if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','Tab'].includes(event.key))history.boundary();
    const stops=field._formulaStops;if(event.key!=='Tab'||!stops)return;
    const next=stops.index+(event.shiftKey?-1:1);if(next<0||next>=stops.ranges.length){field._formulaStops=null;return;}
    event.preventDefault();event.stopPropagation();stops.index=next;const range=stops.ranges[next];field.setSelectionRange(range.start,range.end);
   };
   paint();
   load().then(async()=>{
    if(disposed||!visual.isConnected)return;
    math=document.createElement('math-field');math.setAttribute('math-virtual-keyboard-policy','manual');math.setAttribute('aria-label','可视公式编辑');
    math.style.visibility='hidden';math.smartMode=false;math.removeExtraneousParentheses=false;visual.append(math);math.menuItems=[];
    math.keybindings=math.keybindings.filter(binding=>!(Array.isArray(binding.command)?binding.command[0]:binding.command)?.includes('VirtualKeyboard'));
    stopSelection=scriptSelection(math);
    const activate=()=>{if(active!=='visual')history.boundary();active='visual';if(sourceDirty)paint();};
    // MathLive may focus its internal input on a later task. A pointer tool
    // action immediately after clicking the formula already targets this field.
    math.addEventListener('pointerdown',()=>{history.boundary();activate();},true);math.onfocus=activate;
    math.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','Tab'].includes(event.key))history.boundary();});
    math.addEventListener('input',()=>{
     if(synchronizing||disposed)return;clearTimeout(clock);sourceDirty=false;
     const tags=ReportEquations.presentation(field.value).tags;
     field.value=math.getValue('latex')+(tags.length?'\n'+tags.join('\n'):'');draft=field.value;field._formulaStops=null;record(inputKey);paint(false);
    });
    // Mounting and the first source paint can reset the math selection. Do not
    // expose the hit-test surface until local fonts/layout and that paint finish.
    await paint();await document.fonts.ready;
    await new Promise(resolve=>requestAnimationFrame(resolve));
    if(!disposed&&math.isConnected){math.style.visibility='';math.dataset.ready='1';for(const button of selectionButtons)button.disabled=math.readOnly;}
   }).catch(error=>{if(!disposed)status.textContent=error.message;});
  },onOk:async()=>{
   const next=draft.trim(),nextId=display?idField.value.trim()||null:null;
   if(!next)throw Error('公式不能为空');await validate(next,nextId);await render(next,display);
   return {tex:next===original.trim()?original:next,id:nextId};
  }
 });}finally{dispose();}
}
root.ReportFormulaEditor={open,load};
})(window);
