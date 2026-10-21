/* Complete text/output checks over the existing IR and current Marked model. */
(function(root){
'use strict';
function complete(contract,model,profile,options){
 if(contract.source_snapshot?.utf16_length!==undefined&&contract.source_snapshot.utf16_length!==model.source.length)throw Error('检查快照不一致');
 const blocked=new Set(profile==='engineering'?contract.output_blockers:[]);
 const diagnostics=contract.diagnostics.map(d=>blocked.has(d.code)?{...d,severity:'error'}:d),seen=new Set(diagnostics.map(d=>[d.code,d.start,d.end].join(':')));
 const extras=[...root.ReportProfile.plan(model.source,profile,model.map.blocks,options).diagnostics,...model.notes.problems];
 for(const item of extras){
  const key=[item.code,item.start,item.end].join(':');if(seen.has(key))continue;seen.add(key);
  diagnostics.push({...item,severity:item.severity||'warning',line:item.line||model.map.lineAt(item.start||0)});
 }
 const valid=!diagnostics.some(d=>d.severity==='error');
 return {...contract,schema:'hrs-output-preflight-v1',diagnostics,valid,safeToCompile:valid&&profile==='engineering',
  preflight:{scope:profile==='engineering'?'engineering-text':'free-text',complete:true,engine:'HRS/Marked',assets_checked:false,downstream_verified:false}};
}
root.ReportPreflight={complete};
if(typeof module!=='undefined'&&module.exports)module.exports=root.ReportPreflight;
})(typeof window==='undefined'?globalThis:window);
