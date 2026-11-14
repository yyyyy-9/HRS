/* A bounded view of the same CodeMirror document. No alternate text buffer. */
(function(root){
'use strict';
function attach(editor,{onBoundary=()=>{}}={}){
 let published=null;
 const {StateEffect,StateField,Decoration,EditorState,EditorView,EditorSelection,external,foldedRanges}=root.SourceEditor.extensionAPI;
 const setRange=StateEffect.define(),setRecords=StateEffect.define(),clamp=(n,r)=>Math.max(r.from,Math.min(r.to,n));
 // A hidden block must not absorb the next visible line's typography.
 const hidden=Decoration.replace({block:true,inclusiveEnd:false});
 const initial={range:null,notes:[],equations:[],fixed:[],hiddenNotes:[],decorations:Decoration.none};
 function mapRange(r,tr){return r&&tr.docChanged?{from:tr.changes.mapPos(r.from,-1),to:tr.changes.mapPos(r.to,1),hideTo:tr.changes.mapPos(r.hideTo,1)}:r;}
 const mapRecords=(records,tr)=>records.map(n=>({...n,start:tr.changes.mapPos(n.start,-1),end:tr.changes.mapPos(n.end,1)}));
 const field=StateField.define({
  create:()=>initial,
  update(value,tr){
   let {range,notes,equations,fixed}=value;
   const records=tr.effects.find(effect=>effect.is(setRecords))?.value;
   if(records){({notes,equations,fixed}=records);}
   else if(tr.docChanged){notes=mapRecords(notes,tr);equations=mapRecords(equations,tr);fixed=mapRecords(fixed,tr);}
   range=mapRange(range,tr);
   for(const effect of tr.effects)if(effect.is(setRange))range=effect.value;
   if(range===value.range&&notes===value.notes)return equations===value.equations&&fixed===value.fixed?value:{...value,equations,fixed};
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
  let range=mapRange(tr.startState.field(field).range,tr);
  for(const effect of tr.effects)if(effect.is(setRange))range=effect.value;
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
  reveal(start,end,{select=true,nearest=false}={}){
   // Each pane owns its scroll position. Native scrollIntoView may walk
   // shared ancestors and cancel the preview's simultaneous navigation.
   const view=editor.view,doc=view.state.doc,range=view.state.field(field)?.range,selection=view.state.selection;
   const visiblePosition=position=>{
    if(!nearest)return position;
    let visible=position;
    foldedRanges(view.state).between(position,position,(from,to)=>{if(from<=position&&position<to)visible=from;});
    return visible;
   };
   const pointAt=visiblePosition(nearest?Math.max(start,Math.min(end,selection.main.head)):start);
   const markFrom=visiblePosition(start);
   editor.highlightRange(markFrom,end,{select,scroll:false});
   const expectedSelection=view.state.selection;
   const current=()=>{const next=view.state.field(field)?.range;return view.state.doc===doc&&(!nearest||view.state.selection.eq(expectedSelection))&&(!range?!next:next?.from===range.from&&next?.to===range.to&&next?.hideTo===range.hideTo);};
   view.requestMeasure({
    read:measure=>{
     if(!current())return null;
     const scroller=view.scrollDOM,height=scroller.clientHeight,line=measure.lineBlockAt(pointAt);
     if(!nearest)return {top:line.top+(line.height-height)/2};
     const point=measure.coordsAtPos(pointAt,1)??measure.coordsAtPos(pointAt,-1);
     const target=point??line;
     const bounds=scroller.getBoundingClientRect(),offset=point?bounds.top:bounds.top-measure.documentTop;
     const margin=12;
     let top=editor.scrollTop,left=editor.scrollLeft;
     if(target.top<offset+margin)top+=target.top-offset-margin;
     else if(target.bottom>offset+height-margin)top+=target.bottom-offset-height+margin;
     if(point){
      const edge=bounds.left+(view.dom.querySelector('.cm-gutters')?.offsetWidth??0);
      if(point.left<edge+margin)left+=point.left-edge-margin;
      else if(point.right>bounds.right-margin)left+=point.right-bounds.right+margin;
     }
     return {top,left};
    },
    write:position=>{
     if(!position||!current())return;
     editor.scrollTop=Math.max(0,position.top);
     if(position.left!==undefined)editor.scrollLeft=Math.max(0,position.left);
    }
   });
  },
  set(topic,model=null){
   const doc=editor.view.state.doc;
   if(model&&model.source!==editor.value)return;
   const range=topic?{from:topic.start,to:topic.end,hideTo:topic.end}:null;
   if(range&&range.hideTo<doc.length&&doc.sliceString(range.to-1,range.to)==='\n'){
    range.to--;if(doc.sliceString(range.to-1,range.to)==='\r')range.to--;
   }
   const previous=editor.view.state.field(field).range,effects=[];
   if(previous?.from!==range?.from||previous?.to!==range?.to||previous?.hideTo!==range?.hideTo)effects.push(setRange.of(range));
   if(model&&(published?.map!==model.map||published?.doc!==doc)){
    const notes=Array.from(model.notes.definitionRecords.values()).flat().sort((a,b)=>a.start-b.start)
     .map(record=>({start:record.start,end:record.end,key:record.token.key}));
    const equations=[],fixed=[];
    for(const record of model.map.blocks){
     const {start,end,type}=record;
     if(type==='reportEquation')equations.push({start,end});
     if(['code','html','table','reportEquation','reportImageGroup'].includes(type))fixed.push({start,end});
     else fixed.push(...root.SourceMap.literalRanges(model.source,record,root.marked));
    }
    effects.push(setRecords.of({notes,equations,fixed}));
   }
   if(!effects.length)return;
   editor.view.dispatch({effects});
   if(model)published={map:model.map,doc};
   editor.requestMeasure();
  },
  get range(){return editor.view.state.field(field)?.range||null;}
 };
}
root.ReportSourceProjection={attach};
})(window);
