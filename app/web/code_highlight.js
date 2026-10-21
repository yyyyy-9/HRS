/* HF8: small offline *lexical* highlighter. No user code evaluation, CDN, or DOM parser. */
(function(root){
'use strict';
const LANGS={
 python:{label:'Python',keywords:'and as assert async await break class continue def del elif else except False finally for from global if import in is lambda nonlocal not or pass raise return True try while with yield None match case',comment:'#',strings:true},
 java:{label:'Java',keywords:'abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while record var sealed permits true false null',comment:'//',block:'/*',strings:true},
 matlab:{label:'MATLAB',keywords:'break case catch classdef continue else elseif end for function global if otherwise parfor persistent return spmd switch try while methods properties events true false NaN Inf',comment:'%',block:'%{',strings:true},
 powershell:{label:'PowerShell',keywords:'begin break catch class continue data do dynamicparam else elseif end enum exit filter finally for foreach from function hidden if in inlinescript param process return switch throw trap try until using var while workflow true false null',comment:'#',block:'<#',strings:true},
 javascript:{label:'JavaScript',keywords:'async await break case catch class const continue debugger default delete do else export extends false finally for from function if import in instanceof let new null of return static super switch this throw true try typeof undefined var void while yield',comment:'//',block:'/*',strings:true},
 json:{label:'JSON',keywords:'true false null',comment:'',strings:true},
 bash:{label:'Bash',keywords:'if then else elif fi for do done while until case esac in function select return local export readonly declare break continue',comment:'#',strings:true}
};
const ALIASES={python:'python',py:'python',python3:'python',m:'matlab',mlx:'matlab',matlab:'matlab',ps:'powershell',ps1:'powershell',pwsh:'powershell',powershell:'powershell',java:'java',js:'javascript',node:'javascript',javascript:'javascript',json:'json',sh:'bash',shell:'bash',zsh:'bash',bash:'bash'};
const sets={};for(const [name,item] of Object.entries(LANGS))sets[name]=new Set(item.keywords.split(/\s+/).map(x=>name==='powershell'?x.toLowerCase():x));
const escapeHTML=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function language(code){let name=String(code||'').trim().split(/\s+/)[0].toLowerCase().replace(/^language-/, '');return ALIASES[name]||'';}
function label(raw){const normalized=language(raw);return normalized?LANGS[normalized].label:(String(raw||'').trim().split(/\s+/)[0].match(/^[a-z0-9+.#_-]{1,30}$/i)?.[0]||'纯文本');}
function lex(input,lang,opts={}){
 const text=String(input||''),name=language(lang)||lang;
 if(!Object.prototype.hasOwnProperty.call(LANGS,name)||!text)return [];
 const conf=LANGS[name],max=Number.isInteger(opts.maxTokens)?opts.maxTokens:15000;
 const tokens=[];let i=0,block=opts.initialBlock||'';
 const add=(from,to,kind)=>{if(to>from)tokens.push({from,to,kind});};
 while(i<text.length&&tokens.length<max){
  const from=i,rest=text.slice(i);
  if(block){const end=text.indexOf(block,i);i=end<0?text.length:end+block.length;add(from,i,'comment');if(end>=0)block='';continue;}
  if(conf.block&&text.startsWith(conf.block,i)){
    const terminator=conf.block==='/*'?'*/':conf.block==='%{'?'%}':'#>';
    const end=text.indexOf(terminator,i+conf.block.length);i=end<0?text.length:end+terminator.length;
    add(from,i,'comment');if(end<0)block=terminator;continue;
  }
  if(conf.comment&&text.startsWith(conf.comment,i)){
   const end=text.indexOf('\n',i);i=end<0?text.length:end;add(from,i,'comment');continue;
  }
  const ch=text[i];
  if(ch==='"'||ch==="'"||ch==='`'){
   if(ch==='`'&&name!=='javascript'&&name!=='bash'){i++;continue;}
   if(name==='matlab'&&ch==="'"&&i>0&&/[\w)\]]/.test(text[i-1])){i++;continue;} // Matlab transpose
   const triple=name==='python'&&text.slice(i,i+3)===ch.repeat(3),delimiter=triple?ch.repeat(3):ch;
   i+=delimiter.length;
   while(i<text.length){
    if(text[i]==='\\'&&i+1<text.length){i+=2;continue;}
    if(text.startsWith(delimiter,i)){i+=delimiter.length;break;}
    // Doubled single quotes in MATLAB / PowerShell are escaped quotes.
    if((name==='matlab'||name==='powershell')&&text[i]===ch&&text[i+1]===ch){i+=2;continue;}
    i++;
   }
   add(from,i,'string');continue;
  }
  if(ch==='$'&&(name==='powershell'||name==='bash')){
   const m=rest.match(/^\$(?:\{[A-Za-z_][\w:.-]*\}|[A-Za-z_][\w:]*|\d+|\?)/);
   if(m){i+=m[0].length;add(from,i,'variable');continue;}
  }
  const number=rest.match(/^(?:0[xX][\dA-Fa-f]+|\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)(?![\w])/);
  if(number&&!(i>0&&/[\w.]/.test(text[i-1]))){i+=number[0].length;add(from,i,'number');continue;}
  const ident=rest.match(/^[A-Za-z_][\w-]*/);
  if(ident){i+=ident[0].length;const raw=ident[0],word=name==='powershell'?raw.toLowerCase():raw;
   if(sets[name].has(word))add(from,i,'keyword');
   else if(name==='powershell'&&/^[A-Za-z]+-[A-Za-z]+$/.test(raw))add(from,i,'function');
   else if(name!=='json'&&/^\s*\(/.test(text.slice(i,i+25)))add(from,i,'function');
   else if(name==='json'&&/^\s*:/.test(text.slice(i,i+12)))add(from,i,'property');
   continue;
  }
  i++;
 }
 tokens.endBlock=block;
 return tokens;
}
function highlightHTML(code,lang){
 const raw=String(code||'');let out='',at=0;
 for(const mark of lex(raw,lang)){
  out+=escapeHTML(raw.slice(at,mark.from))+'<span class="hrs-syntax-'+mark.kind+'">'+escapeHTML(raw.slice(mark.from,mark.to))+'</span>';
  at=mark.to;
 }
 return out+escapeHTML(raw.slice(at));
}
function buildCodeCard(code,lang,{copy=true}={}){
 const wrapper=document.createElement('div');wrapper.className='hrs-code-panel';
 const head=document.createElement('div');head.className='hrs-code-head';
 const badge=document.createElement('span');badge.className='hrs-code-language';badge.textContent=label(lang);head.append(badge);
 if(copy){const button=document.createElement('button');button.className='hrs-code-copy';button.type='button';button.textContent='复制';button.setAttribute('aria-label','复制 '+label(lang)+' 代码');
   button.addEventListener('click',async()=>{
    try{if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(String(code));
     else{const area=document.createElement('textarea');area.value=String(code);area.style.position='fixed';area.style.opacity='0';document.body.append(area);try{area.select();if(!document.execCommand('copy'))throw Error('当前浏览器不允许复制');}finally{area.remove();}}
     button.textContent='已复制';setTimeout(()=>button.textContent='复制',1250);
    }catch{button.textContent='请选中代码复制';setTimeout(()=>button.textContent='复制',1900);}
   });head.append(button);
 }
 const pre=document.createElement('pre');pre.className='hrs-code-pre';const el=document.createElement('code');
 el.className='hrs-code-content';el.dataset.language=language(lang)||'plain';el.innerHTML=highlightHTML(code,lang);pre.append(el);
 wrapper.append(head,pre);return wrapper;
}
function decorateDOM(root){
 root.querySelectorAll('pre > code').forEach(code=>{
  if(code.closest('.hrs-code-panel,.diagram-error,.report-table-wrap,.report-figure-wrap'))return;
  const cls=Array.from(code.classList).find(c=>c.startsWith('language-'))||'';
  const lang=cls.replace(/^language-/,'');const pre=code.parentElement;
  if(pre.parentElement?.closest('.hrs-code-panel'))return;
  pre.replaceWith(buildCodeCard(code.textContent,lang));
 });
}
// CM6 decorations use UTF-16 offsets, the same encoding as JS slice and CodeMirror.
// Return only visible-range marks; never touch the editor DOM or source bytes.
// HF8 PF1: index Markdown fences once per source text so visible-range
// CodeMirror decorations keep working even in very long code blocks.
let lastFenceSource=null,lastFenceRanges=[];
function fenceRegions(input){
 const text=String(input||'');if(lastFenceSource===text)return lastFenceRanges;
 const ranges=[];let active=null,at=0,lineCount=0;
 while(at<text.length&&lineCount++<40000){
  let stop=text.indexOf('\n',at);if(stop<0)stop=text.length;
  const raw=text.slice(at,stop).replace(/\r$/,'');
  const opener=raw.match(/^ {0,3}(`{3,}|~{3,})([^\r]*)$/);
  if(opener){
   if(!active){active={openStart:at,bodyStart:stop<text.length?stop+1:stop,
       openEnd:stop,closeStart:text.length,closeEnd:text.length,
       lang:language(opener[2].trim()),char:opener[1][0],length:opener[1].length};}
   else if(opener[1][0]===active.char&&opener[1].length>=active.length&&!opener[2].trim()){
    active.closeStart=at;active.closeEnd=stop;ranges.push(active);active=null;
   }
  }
  if(stop===text.length)break;at=stop+1;
 }
 if(active)ranges.push(active);
 lastFenceSource=text;lastFenceRanges=ranges;
 return ranges;
}
let lastPipeSource=null,lastPipeRanges=[];
function pipeRegions(input){
 const text=String(input||'');if(text===lastPipeSource)return lastPipeRanges;
 lastPipeSource=text;
 lastPipeRanges=root.SourceBlocks?root.SourceBlocks.scan(text).filter(block=>block.language==='gfm-pipe'):[];
 return lastPipeRanges;
}
function sourcePipes(line){
 const positions=[];let tick=0;
 for(let i=0;i<line.length;i++){
  if(line[i]==='\\'){
   let j=i+1;while(line[j]==='\\')j++;
   if(line[j]==='|'&&((j-i)%2)){i=j;continue;}
   i=j-1;continue;
  }
  if(line[i]==='`'){
   let n=1;while(line[i+n]==='`')n++;
   if(!tick)tick=n;else if(tick===n)tick=0;
   i+=n-1;continue;
  }
  if(line[i]==='|'&&!tick)positions.push(i);
 }
 return positions;
}
function sourceLineDecorations(input,start=0,end=String(input).length){
 const text=String(input||''),output=[];
 start=Math.max(0,Math.min(text.length,Math.floor(start)||0));
 end=Math.max(start,Math.min(text.length,Math.floor(end)||0));
 const regions=fenceRegions(text),tables=pipeRegions(text);
 for(const table of tables){
  if(table.to<start||table.from>=end)continue;
  let at=table.from,number=0;
  while(at<=table.to&&output.length<1600){
   let stop=text.indexOf('\n',at);if(stop<0)stop=text.length;
   if(at>table.to)break;
   const raw=text.slice(at,stop).replace(/\r$/,'');
   const kind=number===0?'table-head-line':number===1?'table-separator-line':
    /^ {0,3}:[ \t]+/.test(raw)?'table-caption-line':raw.trim()?'table-body-line':null;
   if(kind&&stop>=start&&at<end)output.push({from:at,kind});
   if(stop===text.length)break;at=stop+1;number++;
  }
 }
 let at=text.lastIndexOf('\n',Math.max(0,start-1))+1;
 while(at<end&&output.length<1600){
  let stop=text.indexOf('\n',at);if(stop<0)stop=text.length;
  const heading=text.slice(at,stop).match(/^ {0,3}(#{1,6})(?=\s|$)/);
  if(heading&&!regions.some(r=>at>=r.openStart&&at<r.closeEnd))output.push({from:at,kind:'heading-'+heading[1].length});
  if(stop===text.length)break;at=stop+1;
 }
 for(const region of regions){
  if(region.openStart>=end)break;
  if(region.closeEnd<start)continue;
  if(region.openStart<end&&region.openEnd>=start)output.push({from:region.openStart,kind:'fence-line'});
  if(region.bodyStart<region.closeStart){
   let at=Math.max(region.bodyStart,text.lastIndexOf('\n',Math.max(region.bodyStart,start)-1)+1);
   if(at<region.bodyStart)at=region.bodyStart;
   while(at<region.closeStart&&at<end&&output.length<1600){
    let stop=text.indexOf('\n',at);if(stop<0)stop=text.length;
    if(stop>=start)output.push({from:at,kind:'code-line'});
    if(stop===text.length)break;
    at=stop+1;
   }
  }
  if(region.closeStart<text.length&&region.closeStart<end&&region.closeEnd>=start)
   output.push({from:region.closeStart,kind:'fence-line'});
  if(output.length>=1600)break;
 }
 return output;
}
const isEscaped=(text,index)=>{let slashes=0;for(let k=index-1;k>=0&&text[k]==='\\';k--)slashes++;return slashes%2===1;};
function sourceMathTokens(line){
 const text=String(line||''),marks=[];
 for(const part of root.ReportTableContent?.tokenize(text)||[]){
  if(part.kind!=='math'||part.display)continue;
  // Dollar amounts such as "$10 and $20" should stay plain prose.
  if(part.raw[0]==='$'&&/^\d+(?:[.,]\d+)?(?:\s+(?:and|to|or)\s+\d+)?$/i.test(part.tex))continue;
  const open=part.raw.startsWith('\\(')?2:1,close=open;
  marks.push({from:part.from,to:part.from+open,kind:'math-marker'},
   {from:part.from+open,to:part.to-close,kind:'math'},
   {from:part.to-close,to:part.to,kind:'math-marker'});
  const command=/\\[A-Za-z]+/g;let found;
  while((found=command.exec(part.tex))!==null)
   marks.push({from:part.from+open+found.index,to:part.from+open+found.index+found[0].length,kind:'math-command'});
 }
 return marks;
}

function sourceTokens(input,start=0,end=String(input).length){
 const text=String(input);start=Math.max(0,start|0);end=Math.min(text.length,Math.max(0,end|0));
 const from=Math.max(0,start-48000);let lineStart=from?text.lastIndexOf('\n',from)+1:0;
 const enclosing=fenceRegions(text).find(region=>region.bodyStart<=lineStart&&region.closeStart>=lineStart);
 const tables=pipeRegions(text);

 const result=[];let fence=enclosing?{char:enclosing.char,length:enclosing.length,lang:enclosing.lang}:null,maxLines=32000;
 const add=(a,b,kind)=>{if(b>a&&a<end&&b>start&&result.length<2200)result.push({from:Math.max(a,start),to:Math.min(b,end),kind});};
 while(lineStart<end&&maxLines-->0&&result.length<2100){
  let stop=text.indexOf('\n',lineStart);if(stop<0)stop=text.length;
  const line=text.slice(lineStart,stop),raw=line.match(/^ {0,3}(`{3,}|~{3,})([^\r]*)$/);
  if(fence){
   if(raw&&raw[1][0]===fence.char&&raw[1].length>=fence.length&&/^\s*$/.test(raw[2])){add(lineStart,lineStart+raw[1].length,'fence');fence=null;}
   else if(fence.lang){const tokens=lex(line,fence.lang,{maxTokens:300,initialBlock:fence.commentBlock});if(stop>start){for(const token of tokens){add(lineStart+token.from,lineStart+token.to,token.kind);}}fence.commentBlock=tokens.endBlock;}
  }else if(raw){fence={char:raw[1][0],length:raw[1].length,lang:language(raw[2].trim())};add(lineStart,lineStart+raw[1].length,'fence');add(lineStart+raw[1].length,stop,'language');}
  else{
   const h=line.match(/^ {0,3}(#{1,6})(?=\s|$)/);if(h){add(lineStart,lineStart+h[0].length,'heading');}
   else {const li=line.match(/^\s*(?:[-*+]|\d+[.)])(?=\s)/);if(li)add(lineStart,lineStart+li[0].length,'list');
    const bq=line.match(/^\s*>+/);if(bq)add(lineStart,lineStart+bq[0].length,'quote');}
   const table=tables.find(block=>block.from<=lineStart&&block.to>=lineStart);
   if(table){
    const row=text.slice(table.from,lineStart).split('\n').length-1;
    if(row===1){add(lineStart,stop,'table-divider');}
    else if(/^ {0,3}:[ \t]+/.test(line)){add(lineStart,stop,'table-caption');}
    else for(const column of sourcePipes(line))add(lineStart+column,lineStart+column+1,'table-pipe');
   }
   // Source code spans, markdown links and emphasis are distinct but non-destructive.
   const link=/!?\[[^\]\n]{0,400}\]\([^\s\n)]{1,300}(?:\s+"[^"\n]{0,150}")?\)/g;let m;
   while((m=link.exec(line)))add(lineStart+m.index,lineStart+m.index+m[0].length,'link');
   const inline=/`+[^`\n]+`+/g;while((m=inline.exec(line)))add(lineStart+m.index,lineStart+m.index+m[0].length,'inline');
   for(const math of sourceMathTokens(line))add(lineStart+math.from,lineStart+math.to,math.kind);
  }
  if(stop===text.length)break;lineStart=stop+1;
 }
 return result;
}
const api={language,label,lex,highlightHTML,buildCodeCard,decorateDOM,sourceTokens,sourceLineDecorations,sourceMathTokens,fenceRegions,escapeHTML};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.ReportCodeHighlight=api;
})(typeof window!=='undefined'?window:globalThis);
