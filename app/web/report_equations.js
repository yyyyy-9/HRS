/* Numbering is metadata; raw LaTeX stays the source for future Word IR. */
(function(root){
'use strict';
const marker=/^ {0,3}<!-- hrs:eq id=(eq-[A-Za-z0-9_-]{1,60}) -->[ \t]*\r?\n/;
function parse(source){
 if(String(source).startsWith('\uFEFF')){const value=parse(String(source).slice(1));if(value)value.raw='\uFEFF'+value.raw;return value;}
 const text=String(source),meta=text.match(marker),offset=meta?meta[0].length:0;
 const rest=text.slice(offset);
 // \[ ... \] is conventional display TeX but does NOT imply equation
 // numbering; opt-in numbered equations remain <!-- hrs:eq --> + $$.
 let open=rest.match(/^ {0,3}\$\$/),bracket=false;
 if(!open&&!meta){open=rest.match(/^ {0,3}\\\[/);bracket=!!open;}
 if(!open)return null;
 const begin=open[0].length;
 // The closing delimiter must be at the end of its line; escaped closers
 // and delimiters inside the formula body are not structure.
 const close=bracket?/(?<!\\)\\\][ \t]*(?:\r?\n|$)/g:/(?<!\\)\$\$[ \t]*(?:\r?\n|$)/g;
 close.lastIndex=begin;
 const match=close.exec(rest);if(!match)return null;
 const tex=rest.slice(begin,match.index);if(!tex.trim())return null;
 const length=offset+match.index+match[0].length;
 return {raw:text.slice(0,length),tex,id:meta?.[1]||null,numbered:!!meta,delimiter:bracket?'bracket':'dollar'};
}
function snippet(tex,id=null,newline='\n'){
 if(id&&!/^eq-[A-Za-z0-9_-]{1,60}$/.test(id))throw Error('公式 ID 必须符合 eq-…，最多 63 字符');
 return (id?'<!-- hrs:eq id='+id+' -->'+newline:'')+'$$'+newline+String(tex).replace(/\r\n?/g,'\n').replace(/\n/g,newline)+newline+'$$';
}
function installMarked(marked){marked.use({extensions:[{name:'reportEquation',level:'block',
 start:src=>src.match(/^\uFEFF? {0,3}(?:\$\$|\\\[|<!-- hrs:eq id=)/m)?.index,
 tokenizer(src){const equation=parse(src);if(equation)return {type:'reportEquation',raw:equation.raw,equation};},
 renderer(token){return '<pre>'+token.raw.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))+'</pre>';}
}]});}
const api={parse,snippet,installMarked};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.ReportEquations=api;
})(typeof window!=='undefined'?window:globalThis);
