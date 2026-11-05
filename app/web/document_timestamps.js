/* Dates are server-derived metadata. This view only maps positions and paints. */
(function(root){
'use strict';
function date(value){
 if(!value)return '未记录';const d=new Date(value);if(!Number.isFinite(d.getTime()))return '未记录';
 const pad=n=>String(n).padStart(2,'0');
 return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes());
}
function paint(article,snapshot,show=true){
 article.dataset.hrsShowTimestamps=show?'1':'0';
 const records=new Map((snapshot?.records||[]).map(r=>[r.start,r]));
 for(const block of article.querySelectorAll('.doc-block[data-start]')){
  const record=records.get(Number(block.dataset.start));let row=block.querySelector(':scope > .hrs-block-times');
  if(!record){row?.remove();continue;}
  if(!row){row=document.createElement('div');row.className='hrs-block-times';row.contentEditable='false';row.setAttribute('role','note');block.append(row);}
  if(row.dataset.timeKey===record.key&&row.dataset.created===(record.created||'')&&row.dataset.modified===(record.modified||''))continue;
  row.dataset.timeKey=record.key;row.dataset.created=record.created||'';row.dataset.modified=record.modified||'';row.replaceChildren();
  for(const [label,value] of [['创建',record.created],['修改',record.modified]]){
   const line=document.createElement('span');line.append(label+' ');
   const time=document.createElement('time');time.textContent=date(value);if(value)time.dateTime=value;line.append(time);row.append(line);
  }
 }
}
function attach(editor){
 const {StateEffect,StateField,Decoration,EditorView,foldedRanges}=root.SourceEditor.extensionAPI;
 const set=StateEffect.define(),show=StateEffect.define();
 const field=StateField.define({create:()=>({snapshot:null,visible:true}),update(value,tr){
  if(tr.docChanged&&value.snapshot)value={...value,snapshot:{...value.snapshot,records:value.snapshot.records.map(r=>{
   const start=tr.changes.mapPos(r.start,1),end=tr.changes.mapPos(r.end,-1);
   // Targets begin on block lines. An inserted copy stays before the original;
   // editing its #/fence prefix still belongs to that original line.
   return {...r,start:end>start?tr.newDoc.lineAt(start).from:start,end};
  }).filter(r=>r.end>r.start)}};
  for(const effect of tr.effects){if(effect.is(set))value={...value,snapshot:effect.value};if(effect.is(show))value={...value,visible:effect.value};}
  return value;
 }});
 const marks=EditorView.decorations.of(view=>{
  const value=view.state.field(field);if(!value.visible)return Decoration.none;
  const folds=[];foldedRanges(view.state).between(0,view.state.doc.length,(from,to)=>folds.push({from,to}));
  const decorations=[],seen=new Set();let foldIndex=0;
  for(const record of value.snapshot?.records||[]){
   if(record.start>=view.state.doc.length)continue;
   while(foldIndex<folds.length&&folds[foldIndex].to<record.start)foldIndex++;
   const candidate=folds[foldIndex],fold=candidate&&candidate.from<=record.start+1&&candidate.to>=record.end-2?candidate:null;
   const pos=fold?record.start:Math.max(record.start,Math.min(record.end-1,view.state.doc.length));
   // Trailing newline belongs to the preceding object, never the next block.
   const line=view.state.doc.lineAt(pos);if(seen.has(line.from))continue;seen.add(line.from);
   decorations.push(Decoration.line({class:'cm-block-times',attributes:{'data-created':'创建 '+date(record.created),'data-modified':'修改 '+date(record.modified)}}).range(line.from));
  }
  return Decoration.set(decorations,true);
 });
 editor.view.dispatch({effects:StateEffect.appendConfig.of([field,marks])});
 return {
  get snapshot(){return editor.view.state.field(field).snapshot;},
  set(snapshot){editor.view.dispatch({effects:set.of(snapshot||null)});},
  show(value){if(editor.view.state.field(field).visible!==value)editor.view.dispatch({effects:show.of(value)});},
  payload(){const snapshot=this.snapshot;return {block_timestamps:snapshot,timestamp_hints:snapshot?.records.map(({key,start,end})=>({key,start,end}))||[]};}
 };
}
root.ReportTimestamps={attach,paint,date};
})(window);
