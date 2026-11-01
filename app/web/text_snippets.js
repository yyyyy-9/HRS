/* Declarative user text, with explicit fields and no executable expressions. */
(function(root){
'use strict';
const pattern=/\{\{(date|cursor|field:([^{}\n]+))\}\}/g;
function fields(text){return [...new Set([...text.matchAll(pattern)].map(m=>m[2]).filter(Boolean))];}
function expand(text,values,date,marker){return text.replace(pattern,(raw,key,name)=>key==='date'?date:key==='cursor'?marker:values[name]??'');}
async function open({modal,request,sections,insert}){
 const data=await request({}),items=data.snippets.map(item=>({...item}));let selected=null,name,body,variables,target,list,revision=data.revision;
 const current=()=>({id:selected||'snippet-'+Date.now().toString(36),title:name.value.trim(),text:body.value});
 function variablesFor(){const previous=Object.fromEntries([...variables.querySelectorAll('input')].map(n=>[n.dataset.field,n.value]));variables.replaceChildren();
  for(const key of fields(body.value)){const label=document.createElement('label');label.textContent=key+' ';const input=document.createElement('input');input.dataset.field=key;input.value=previous[key]||'';label.append(input);variables.append(label);}}
 function refresh(){list.replaceChildren(new Option('临时记录 / 新片段',''),...items.map(item=>new Option(item.title,item.id)));list.value=selected||'';}
 async function persist(){const reply=await request({snippets:items,revision});revision=reply.revision;refresh();}
 const result=await modal({title:'片段与快速记录',kicker:'Markdown',note:'{{field:名称}} 填写字段，{{date}} 插入日期，{{cursor}} 设置光标。内容按普通 Markdown 插入。',okText:'插入文稿',body:outer=>{
  const tools=document.createElement('div');tools.className='snippet-tools';list=document.createElement('select');list.setAttribute('aria-label','选择片段');refresh();
  const save=document.createElement('button');save.type='button';save.textContent='保存片段';const remove=document.createElement('button');remove.type='button';remove.textContent='删除片段';
  const message=document.createElement('span');message.setAttribute('role','status');tools.append(list,save,remove,message);outer.append(tools);
  name=document.createElement('input');name.placeholder='片段名称（保存时填写）';name.setAttribute('aria-label','片段名称');outer.append(name);
  body=document.createElement('textarea');body.rows=9;body.setAttribute('aria-label','片段 Markdown');body.placeholder='直接写入 Markdown，或选择已有片段';outer.append(body);
  variables=document.createElement('div');variables.className='snippet-fields';outer.append(variables);body.oninput=variablesFor;
  target=document.createElement('select');target.setAttribute('aria-label','插入位置');target.append(new Option('当前光标 / 选区','cursor'));
  sections.forEach((section,i)=>target.append(new Option('追加到：'+section.path.join(' › '),String(i))));outer.append(target);
  list.onchange=()=>{selected=list.value||null;const item=items.find(n=>n.id===selected);name.value=item?.title||'';body.value=item?.text||'';variablesFor();};
  save.onclick=async()=>{try{const item=current();if(!item.title)throw Error('请填写片段名称');const i=items.findIndex(n=>n.id===item.id);if(i<0)items.push(item);else items[i]=item;selected=item.id;await persist();message.textContent='已保存';}catch(error){message.textContent=error.message;}};
  remove.onclick=async()=>{try{const i=items.findIndex(n=>n.id===selected);if(i<0)return;items.splice(i,1);selected=null;await persist();message.textContent='已删除片段，当前文字仍可插入';}catch(error){message.textContent=error.message;}};
 },onOk:()=>{if(!body.value.trim())throw Error('请填写要插入的内容');return {text:body.value,values:Object.fromEntries([...variables.querySelectorAll('input')].map(n=>[n.dataset.field,n.value])),section:target.value==='cursor'?null:sections[+target.value]};}});
 if(result)await insert(result);
}
root.ReportSnippets={open,fields,expand};
if(typeof module!=='undefined'&&module.exports)module.exports=root.ReportSnippets;
})(typeof window==='undefined'?globalThis:window);
