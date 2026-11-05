/* A bounded view of the same CodeMirror document. No alternate text buffer. */
(function(root){
'use strict';
function attach(editor,{onBoundary=()=>{}}={}){
 let typographyMap=null;
 const {StateEffect,StateField,Decoration,EditorState,EditorView,EditorSelection,external}=root.SourceEditor.extensionAPI;
 const set=StateEffect.define(),setNotes=StateEffect.define(),setEquations=StateEffect.define(),setTypography=StateEffect.define(),clamp=(n,r)=>Math.max(r.from,Math.min(r.to,n));
 // A hidden block must not absorb the next visible line's typography.
 const hidden=Decoration.replace({block:true,inclusiveEnd:false});
 function mapRange(r,changes){return r?{from:changes.mapPos(r.from,-1),to:changes.mapPos(r.to,1),hideTo:changes.mapPos(r.hideTo,1)}:null;}
 const field=StateField.define({
  create:()=>null,
  update(value,tr){
   let range=mapRange(value?.range,tr.changes);
   let notes=(value?.notes||[]).map(n=>({...n,start:tr.changes.mapPos(n.start,-1),end:tr.changes.mapPos(n.end,1)}));
   let equations=(value?.equations||[]).map(n=>({start:tr.changes.mapPos(n.start,-1),end:tr.changes.mapPos(n.end,1)}));
   let fixed=(value?.fixed||[]).map(n=>({start:tr.changes.mapPos(n.start,-1),end:tr.changes.mapPos(n.end,1)}));
   for(const effect of tr.effects)if(effect.is(set))range=effect.value;
   for(const effect of tr.effects)if(effect.is(setNotes))notes=effect.value;
   for(const effect of tr.effects)if(effect.is(setEquations))equations=effect.value;
   for(const effect of tr.effects)if(effect.is(setTypography))fixed=effect.value;
   const marks=[];
   if(range?.from>0)marks.push(hidden.range(0,range.from));
   if(range&&range.hideTo<tr.newDoc.length)marks.push(hidden.range(range.hideTo,tr.newDoc.length));
   const hiddenNotes=[];
   for(let i=0;i<notes.length;i++){
    const n=notes[i];if(n.start>tr.newDoc.length||range&&(n.start<range.from||n.start>=range.hideTo))continue;
    if(range){const end=Math.min(n.end,range.hideTo);if(end>n.start){marks.push(hidden.range(n.start,end));hiddenNotes.push({from:n.start,to:end});}continue;}
    const boundary=i===0||n.start>notes[i-1].end+2;
    marks.push(Decoration.line({class:'cm-note-definition'+(boundary?' cm-note-boundary':''),attributes:{title:'脚注定义 [^'+n.key+']；可在下方注释面板中单独编辑'}}).range(tr.newDoc.lineAt(n.start).from));
   }
   return {range,notes,equations,fixed,hiddenNotes,decorations:Decoration.set(marks,true)};
  },
  provide:f=>[EditorView.decorations.from(f,v=>v?.decorations||Decoration.none),EditorView.atomicRanges.of(view=>view.state.field(f)?.decorations||Decoration.none)]
 });
 const filter=EditorState.transactionFilter.of(tr=>{
  let range=mapRange(tr.startState.field(field)?.range,tr.changes);
  for(const effect of tr.effects)if(effect.is(set))range=effect.value;
  if(!range||tr.annotation(external))return tr;
  const old=tr.startState.field(field)?.range;
  if(old&&tr.docChanged&&(tr.isUserEvent('input')||tr.isUserEvent('delete')||tr.isUserEvent('move'))){
   let allowed=true,crossNote=false;tr.changes.iterChangedRanges((from,to)=>{
    if(from<old.from||to>old.to)allowed=false;
    if((tr.startState.field(field)?.hiddenNotes||[]).some(n=>from<n.to&&to>n.from)){allowed=false;crossNote=true;}
   });
   if(!allowed){if(crossNote)queueMicrotask(()=>onBoundary('选择跨过了隐藏的全局脚注，未修改。请分段编辑，或返回全部专题查看源码。'));return [];}
  }
  const selection=tr.newSelection.main,a=clamp(selection.anchor,range),b=clamp(selection.head,range);
  return a===selection.anchor&&b===selection.head?tr:[tr,{selection:EditorSelection.single(a,b)}];
 });
 const equationMarks=EditorView.decorations.of(view=>{
  const marks=[],seen=new Set(),equations=view.state.field(field)?.equations||[];
  for(const visible of view.visibleRanges)for(const equation of equations){
   if(equation.end<visible.from||equation.start>visible.to)continue;
   let line=view.state.doc.lineAt(Math.max(equation.start,visible.from));
   while(line.from<equation.end&&line.from<=visible.to&&marks.length<1600){
    if(!seen.has(line.from)){seen.add(line.from);marks.push(Decoration.line({class:'cm-hf8-equation-line'}).range(line.from));}
    if(line.to>=view.state.doc.length)break;line=view.state.doc.lineAt(line.to+1);
   }
  }
  return Decoration.set(marks,true);
 });
 const typographyMarks=EditorView.decorations.of(view=>{
  const marks=[],seen=new Set(),fixed=view.state.field(field)?.fixed||[];
  for(const visible of view.visibleRanges)for(const region of fixed){
   if(region.end<=visible.from||region.start>visible.to)continue;
   let line=view.state.doc.lineAt(Math.max(region.start,visible.from));
   while(line.from<region.end&&line.from<=visible.to&&marks.length<1600){
    if(!seen.has(line.from)){seen.add(line.from);marks.push(Decoration.line({class:'cm-source-fixed-size'}).range(line.from));}
    if(line.to>=view.state.doc.length)break;line=view.state.doc.lineAt(line.to+1);
   }
  }
  return Decoration.set(marks,true);
 });
 editor.view.dispatch({effects:StateEffect.appendConfig.of([field,filter,equationMarks,typographyMarks])});
 return {
  reveal(start,end,{select=true}={}){
   // Each pane owns its scroll position. Native scrollIntoView may walk
   // shared ancestors and cancel the preview's simultaneous navigation.
   editor.highlightRange(start,end,{select,scroll:false});
   const view=editor.view,doc=view.state.doc,range=view.state.field(field)?.range;
   const current=()=>{const next=view.state.field(field)?.range;return view.state.doc===doc&&(!range?!next:next?.from===range.from&&next?.to===range.to&&next?.hideTo===range.hideTo);};
   view.requestMeasure({
    read:measure=>current()?measure.lineBlockAt(start):null,
    write:line=>{if(line&&current())editor.scrollTop=Math.max(0,line.top+(line.height-view.scrollDOM.clientHeight)/2);}
   });
  },
  set(topic){
   const text=editor.value,range=topic?{from:topic.start,to:topic.end,hideTo:topic.end}:null;
   if(range&&range.hideTo<text.length&&text[range.to-1]==='\n'){range.to--;if(text[range.to-1]==='\r')range.to--;}
   const previous=editor.view.state.field(field)?.range;
   if(JSON.stringify(previous||null)===JSON.stringify(range))return;
   editor.view.dispatch({effects:set.of(range)});editor.requestMeasure();
  },
  setNotes(records){
   const notes=records.map(r=>({start:r.start,end:r.end,key:r.token.key}));
   if(JSON.stringify(editor.view.state.field(field)?.notes||[])!==JSON.stringify(notes))editor.view.dispatch({effects:setNotes.of(notes)});
  },
  setEquations(records){
   const equations=records.map(r=>({start:r.start,end:r.end}));
   if(JSON.stringify(editor.view.state.field(field)?.equations||[])!==JSON.stringify(equations))editor.view.dispatch({effects:setEquations.of(equations)});
  },
  setTypography(map){
   if(typographyMap===map)return;typographyMap=map;
   const fixed=[];
   for(const record of map.blocks){
    if(['code','html','table','reportEquation','reportImageGroup'].includes(record.type))fixed.push({start:record.start,end:record.end});
    else fixed.push(...root.SourceMap.literalRanges(map.source,record,root.marked));
   }
   if(JSON.stringify(editor.view.state.field(field)?.fixed||[])!==JSON.stringify(fixed))editor.view.dispatch({effects:setTypography.of(fixed)});
  },
  get range(){return editor.view.state.field(field)?.range||null;}
 };
}
root.ReportSourceProjection={attach};
})(window);
