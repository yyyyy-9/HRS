/* Cell text is the source. Math tokens describe display ranges only. */
(function(root){
'use strict';
function escaped(text,position){let n=0;while(position>0&&text[--position]==='\\')n++;return n%2===1;}
function tokenize(input){
 const text=String(input),parts=[];let plain=0,i=0;
 while(i<text.length){
  if(text[i]==='`'){
   let count=1;while(text[i+count]==='`')count++;
   const close=text.indexOf('`'.repeat(count),i+count);
   if(close>=0){i=close+count;continue;}
  }
  let opener='',closer='',display=false;
  if(text[i]==='$'&&!escaped(text,i)){
   display=text[i+1]==='$';opener=display?'$$':'$';closer=opener;
  }else if(text[i]==='\\'&&text[i+1]==='('&&!escaped(text,i)){
   opener='\\(';closer='\\)';
  }else if(text[i]==='\\'&&text[i+1]==='['&&!escaped(text,i)){
   opener='\\[';closer='\\]';display=true;
  }
  if(!opener){i++;continue;}
  let close=i+opener.length;
  while((close=text.indexOf(closer,close))>=0){
   if(escaped(text,close)){close+=closer.length;continue;}
   if(closer==='$'&&(text[close-1]==='$'||text[close+1]==='$')){close++;continue;}
   break;
  }
  if(close<0){i+=opener.length;continue;}
  const tex=text.slice(i+opener.length,close);
  if(!tex.trim()||(!display&&/[\r\n]/.test(tex))){i+=opener.length;continue;}
  if(i>plain)parts.push({kind:'text',text:text.slice(plain,i)});
  const end=close+closer.length;
  parts.push({kind:'math',tex,display,raw:text.slice(i,end),from:i,to:end});
  i=plain=end;
 }
 if(plain<text.length)parts.push({kind:'text',text:text.slice(plain)});
 return parts;
}

const api={tokenize};if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.ReportTableContent=api;
})(typeof window!=='undefined'?window:globalThis);
