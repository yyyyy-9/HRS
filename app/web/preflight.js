/* Complete text/output checks over the existing IR and current Marked model. */
(function(root){
'use strict';
const CURRENCY_TEXT_BLOCKS=new Set(['paragraph','heading','blockquote','list','hrsStyledList','hrsFootnoteDef','table']);
function isEscaped(text,pos){let n=0;while(pos>0&&text[--pos]==='\\')n++;return n%2===1;}
function scanCurrencyWarnings(model){
 const tokenize=root.ReportTableContent?.tokenize;if(typeof tokenize!=='function')return [];
 const fences=(root.SourceBlocks?.scan(model.source,model.tokens)||[]).filter(f=>f.language&&f.language!=='gfm-pipe');
 const results=[];
 for(const block of model.map?.blocks||[]){
  if(!CURRENCY_TEXT_BLOCKS.has(block.type))continue;
  if(fences.some(f=>block.start>=f.from&&block.end<=f.to))continue;
  const isTable=block.type==='table',lines=String(block.raw||'').split('\n');
  let offset=0,inFence=null;
  for(const rawLine of lines){
   const lineStart=block.start+offset;offset+=rawLine.length+1;
   const line=rawLine.replace(/\r$/,'');
   const fenceMatch=line.match(/^\s*(?:>\s*)*(?:(?:[-*+]|\d+[.)])\s+)?(`{3,}|~{3,})/);
   if(fenceMatch){
    const ch=fenceMatch[1][0],len=fenceMatch[1].length;
    if(!inFence)inFence={ch,len};
    else if(inFence.ch===ch&&len>=inFence.len&&new RegExp('^\\s*(?:>\\s*)*'+ch+'{'+inFence.len+',}[ \\t]*$').test(line))inFence=null;
    continue;
   }
   if(inFence)continue;
   const parts=tokenize(line,{table:isTable});
   let cursor=0;
   for(const part of parts){
    if(part.kind==='text'){
     const text=part.text;
     for(let j=0;j<text.length;j++){
      if(text[j]==='`'){
       let ticks=1;while(text[j+ticks]==='`')ticks++;
       const close=text.indexOf('`'.repeat(ticks),j+ticks);
       if(close>=0){j=close+ticks-1;continue;}
       j+=ticks-1;continue;
      }
      if(text.startsWith('<!--',j)){
       const close=text.indexOf('-->',j+4);
       if(close>=0){j=close+2;continue;}
      }
      if(text[j]==='$'&&!isEscaped(text,j)&&text[j+1]!=='$'&&(j===0||text[j-1]!=='$')){
       const num=text.slice(j+1).match(/^\d[\d,]*(?:\.\d+)?/);
       if(num){
        const start=lineStart+cursor+j,end=start+1+num[0].length;
        results.push({code:'UNESCAPED_CURRENCY',severity:'warning',start,end,line:model.map.lineAt(start),
         message:'疑似未转义的美元金额符号 $；若表示金额请转义为 \\$，以免与公式定界符混淆'});
        j+=num[0].length;
       }
      }
     }
     cursor+=text.length;
    }else{
     if(!part.display&&part.raw.startsWith('$')&&!part.raw.startsWith('$$')){
      const tex=part.tex,after=line.slice(part.to);
      const firstNum=tex.match(/^\d[\d,]*(?:\.\d+)?(?![0-9A-Za-z\\])/);
      const nextAlsoAmount=/^\d[\d,]*(?:\.\d+)?/.test(after);
      const hasTablePipe=(isTable||/^\s*\|/.test(line))&&/(?<!\\)\|/.test(tex);
      const hasBareCjk=/[\u4e00-\u9fff]/.test(tex)&&!/\\(?:text|mathrm|textrm|mbox)\b/.test(tex);
      const hasProseBridge=nextAlsoAmount&&/^\d[\d,]*(?:\.\d+)?(?:\s*(?:k|m|bn|usd)\b)?\s+(?:to|and|or|vs\.?|from|per|at|in|for)\s*$/i.test(tex);
      if(firstNum&&(hasTablePipe||(nextAlsoAmount&&hasBareCjk)||hasProseBridge)){
       const stolenMathDelimiter=/(?<!\\)\$/.test(after);
       const start=lineStart+part.from,end=stolenMathDelimiter?start+1+firstNum[0].length:lineStart+part.to;
       results.push({code:'UNESCAPED_CURRENCY',severity:'warning',start,end,line:model.map.lineAt(start),
        message:stolenMathDelimiter?'疑似未转义的美元金额符号 $ 吞并了后续公式定界符；请转义为 \\$':
         '疑似两处未转义的美元金额符号 $ 被误配对为行内公式；若表示金额请转义为 \\$'});
      }
     }
     cursor=part.to;
    }
   }
  }
 }
 return results;
}
function complete(contract,model,profile,options){
 if(contract.source_snapshot?.utf16_length!==undefined&&contract.source_snapshot.utf16_length!==model.source.length)throw Error('检查快照不一致');
 const blocked=new Set(profile==='engineering'?contract.output_blockers:[]);
 const diagnostics=contract.diagnostics.map(d=>blocked.has(d.code)?{...d,severity:'error'}:d),seen=new Set(diagnostics.map(d=>[d.code,d.start,d.end].join(':')));
 const extras=[...root.ReportProfile.plan(model.source,profile,model.map.blocks,options).diagnostics,...model.notes.problems,...scanCurrencyWarnings(model)];
 for(const item of extras){
  const key=[item.code,item.start,item.end].join(':');if(seen.has(key))continue;seen.add(key);
  diagnostics.push({...item,severity:item.severity||'warning',line:item.line||model.map.lineAt(item.start||0)});
 }
 const valid=!diagnostics.some(d=>d.severity==='error');
 const acceptNumbered=Boolean(options?.acceptNumberedHeadings);
 const ready=Boolean(valid&&profile==='engineering'&&(acceptNumbered||!diagnostics.some(d=>d.code==='HEADING_SOURCE_PREFIX')));
 return {...contract,schema:'hrs-output-preflight-v1',diagnostics,valid,safeToCompile:ready,word_compile_ready:ready,
  preflight:{scope:profile==='engineering'?'engineering-text':'free-text',complete:true,engine:'HRS/Marked',assets_checked:false,downstream_verified:false}};
}
root.ReportPreflight={complete,scanCurrencyWarnings};
if(typeof module!=='undefined'&&module.exports)module.exports=root.ReportPreflight;
})(typeof window==='undefined'?globalThis:window);
