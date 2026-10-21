/* Semantic Markdown lists with optional Studio-specific numbering metadata.
 * Source remains standard '- item' / '1. item'; the comment selects display
 * style only and does not insert static visible numbering into the text.
 */
(function(root){
'use strict';
const STYLES=['bullet','decimal','lower-alpha','paren-decimal','paren-lower-alpha'];
const comment=/^ {0,3}<!-- hrs:list style=(bullet|decimal|lower-alpha|paren-decimal|paren-lower-alpha) -->[ \t]*(?:\r?\n|$)/;
const numbered=/^ {0,3}\d{1,9}[.)][ \t]+/;
const bullets=/^ {0,3}[-+*][ \t]+/;
function listSnippet(style,selection=''){
 if(!STYLES.includes(style))throw Error('列表编号样式不合法');
 const lines=String(selection).trim().split(/\r?\n/).filter(s=>s.trim());
 const items=lines.length?lines.map(line=>line.replace(/^(\s*)(?:[-+*]|\d+[.)]|[a-zA-Z][.)])[ \t]+/,'$1')):['第一项','第二项'];
 const prefix=style==='bullet'?'- ':'1. ';
 const body=items.map(text=>prefix+text).join('\n');
 return style==='bullet'?'\n'+body+'\n':'\n<!-- hrs:list style='+style+' -->\n'+body+'\n';
}
function installMarked(marked){
 marked.use({extensions:[{name:'hrsStyledList',level:'block',
  start(src){return src.match(/^ {0,3}<!-- hrs:list style=(?:bullet|decimal|lower-alpha|paren-decimal|paren-lower-alpha) -->/m)?.index;},
  tokenizer(src){
   const m=src.match(comment);if(!m)return;
   const style=m[1],remaining=src.slice(m[0].length);
   const pieces=remaining.split(/\r?\n/),first=pieces[0];
   if(!(style==='bullet'?bullets:numbered).test(first||''))return;
   let len=0,consume=0,blank=false;
   for(const line of pieces){
    const allowed=(style==='bullet'?bullets:numbered).test(line)||(/^\s{2,}\S/.test(line));
    if(allowed){consume++;blank=false;continue;}
    if(!line.trim()&&!blank){consume++;blank=true;continue;}
    break;
   }
   while(consume>0&&!pieces[consume-1].trim())consume--;
   if(!consume)return;
   const body=pieces.slice(0,consume).join('\n')+'\n';
   len=m[0].length+body.length;
   return {type:'hrsStyledList',raw:src.slice(0,len),style,body};
  },
  renderer(token){
   const inner=marked.parse(token.body);
   return `<div class="hrs-list-scope hrs-list-${token.style}" data-hrs-list-style="${token.style}">${inner}</div>`;
  }
 }]});
}
const api={STYLES,listSnippet,installMarked};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.ReportListStyles=api;
})(typeof window!=='undefined'?window:globalThis);
