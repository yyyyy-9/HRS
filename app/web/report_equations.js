/* Numbering is metadata; raw LaTeX stays the source for future Word IR. */
(function(root){
'use strict';
const marker=/^ {0,3}<!-- hrs:eq id=(eq-[A-Za-z0-9_-]{1,60}) -->[ \t]*\r?\n/;
function parse(source){
 if(String(source).startsWith('\uFEFF')){const value=parse(String(source).slice(1));if(value)value.raw='\uFEFF'+value.raw;return value;}
 const text=String(source),meta=text.match(marker),offset=meta?meta[0].length:0;
 const rest=text.slice(offset);
 // Delimiters carry content; the optional marker supplies stable identity.
 // Number visibility is a document render setting.
 let open=rest.match(/^ {0,3}\$\$/),bracket=false;
 if(!open){open=rest.match(/^ {0,3}\\\[/);bracket=!!open;}
 if(!open)return null;
 const begin=open[0].length;
 // The closing delimiter must be at the end of its line; escaped closers
 // and delimiters inside the formula body are not structure.
 const close=bracket?/(?<!\\)\\\][ \t]*(?:\r?\n|$)/g:/(?<!\\)\$\$[ \t]*(?:\r?\n|$)/g;
 close.lastIndex=begin;
 const match=close.exec(rest);if(!match)return null;
 const tex=rest.slice(begin,match.index);if(!tex.trim())return null;
 const length=offset+match.index+match[0].length;
 return {raw:text.slice(0,length),tex,id:meta?.[1]||null,delimiter:bracket?'bracket':'dollar'};
}
function snippet(tex,id=null,newline='\n',delimiter='dollar'){
 if(id&&!/^eq-[A-Za-z0-9_-]{1,60}$/.test(id))throw Error('公式 ID 必须符合 eq-…，最多 63 字符');
 const bracket=delimiter==='bracket';
 return (id?'<!-- hrs:eq id='+id+' -->'+newline:'')+(bracket?'\\[':'$$')+newline+String(tex).replace(/\r\n?/g,'\n').replace(/\n/g,newline)+newline+(bracket?'\\]':'$$');
}
// TeX tags belong to source provenance; display numbers belong to HRS.
function presentation(input){
 const source=String(input),tags=[];let depth=0,i=0,from=0,tex='';
 while(i<source.length){
  const ch=source[i];
  if(ch==='%'){const end=source.indexOf('\n',i);i=end<0?source.length:end+1;continue;}
  if(ch==='\\'){
   const command=source.slice(i).match(/^\\([A-Za-z]+|.)/s);if(!command){i++;continue;}
   const name=command[1],end=i+command[0].length;
   if(name==='verb'){const at=source[end]==='*'?end+1:end,stop=source.indexOf(source[at],at+1);i=stop<0?source.length:stop+1;continue;}
   if(name==='tag'&&depth===0){
    let at=end;if(source[at]==='*')at++;while(at<source.length&&/\s/.test(source[at]))at++;
    if(source[at]==='{'){
     let nested=1,cursor=at+1;
     for(;cursor<source.length&&nested;cursor++){
      if(source[cursor]==='\\'){cursor++;continue;}
      if(source[cursor]==='{')nested++;else if(source[cursor]==='}')nested--;
     }
     if(!nested){tex+=source.slice(from,i);tags.push(source.slice(i,cursor));from=cursor;i=cursor;continue;}
    }
   }
   i=end;continue;
  }
  if(ch==='{')depth++;else if(ch==='}')depth=Math.max(0,depth-1);i++;
 }
 tex+=source.slice(from);return {tex,tags};
}
function installMarked(marked){marked.use({extensions:[{name:'reportEquation',level:'block',
 start:src=>src.match(/^\uFEFF? {0,3}(?:\$\$|\\\[|<!-- hrs:eq id=)/m)?.index,
 tokenizer(src){const equation=parse(src);if(equation)return {type:'reportEquation',raw:equation.raw,equation};},
 renderer(token){return '<pre>'+token.raw.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))+'</pre>';}
}]});}
const api={parse,snippet,presentation,installMarked};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.ReportEquations=api;
})(typeof window!=='undefined'?window:globalThis);
