/* Output policy over the existing lexer/source map. No second document model. */
(function(root){
'use strict';
const settings=root.ReportSettings||(typeof module!=='undefined'&&module.exports?require('./product_settings.js'):null);
if(!settings)return;
const profiles=settings.render_profiles,optionDefinitions=settings.render_options;
function normalize(value){if(value==null)return profiles.default;if(profiles.choices.some(item=>item.id===value))return value;throw Error('未知渲染模式 / render profile');}
function html(raw,profile){
 if(normalize(profile)==='free')return raw;
 // Explicit decoration-only downgrade. Other HTML is visible source, never lost.
 if(/^<\/?(?:mark|span)(?:\s[^<>]*)?\s*>$/i.test(raw.trim()))return '';
 return String(raw).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function plan(source,profile=null,records=null,options={}){
 profile=normalize(profile);
 options=normalizeOptions(options);
 records=records||root.SourceMap.create(source,root.marked.lexer(root.SourceBlocks.normalized(source).text)).blocks;
 const headings=[],abstracts=[],diagnostics=[],counts=[0,0,0,0,0];
 const title=records.find(r=>r.type==='heading'&&r.token.depth===1);
 const chapter=records.find(r=>r.type==='heading'&&r.token.depth===2&&(!title||r.start>title.start));
 for(const r of records){
  if(profile==='engineering'){
   let unsupported=false;
   root.marked.walkTokens([r.token],t=>{if(t.type==='html'&&html(t.raw,profile)!=='')unsupported=true;});
   if(unsupported)diagnostics.push({code:'ENGINEERING_HTML_LITERAL',start:r.start,end:r.end,message:'高级 HTML 已按源码显示；工程 Word 只接受已定义的转换范围。'});
  }
  if(r.type==='heading'){
   const level=r.token.depth;let number='';
   if((profile==='engineering'||options.show_heading_numbers)&&level>1){
    counts[level-2]++;counts.fill(0,level-1);number=counts.slice(0,level-1).join('.');
    // Output checks consume Python IR in render_profile.py; this is display only.
   }
   headings.push({start:r.start,end:r.end,level,number,index:r.index});
  }
  if(profile==='engineering'&&title&&r.start>=title.end&&r.start<(chapter?.start??source.length)&&r.type==='blockquote'&&
     r.token.tokens?.[0]?.type==='paragraph'&&r.token.tokens[0].text.startsWith('摘要：')&&
     r.token.tokens.every(t=>['space','paragraph','text'].includes(t.type)))abstracts.push({start:r.start,end:r.end});
 }
 if(abstracts.length>1){diagnostics.push({code:'MULTIPLE_ABSTRACTS',message:'开头存在多个摘要块，按普通引用处理。'});abstracts.length=0;}
 return {profile,headings,abstracts,diagnostics};
}
function wordTokens(tokens){
 return tokens.flatMap(t=>{
  if(t.type==='hrsHighlight')return wordTokens(t.tokens);
  if(t.type==='hrsFootnoteDef')return [];
  if(t.type==='html'&&/^<\/?(?:mark|span)(?:\s[^<>]*)?\s*>$/i.test(t.raw.trim()))return {type:'text',raw:t.raw,text:''};
  const next={...t};if(t.tokens)next.tokens=wordTokens(t.tokens);
  if(t.items)next.items=t.items.map(i=>({...i,tokens:wordTokens(i.tokens)}));return next;
 });
}
function normalizeOptions(value={}){
 if(value==null)value={};
 if(typeof value!=='object'||Array.isArray(value))throw Error('渲染选项必须是对象');
 const result={};
 for(const [name,entry] of Object.entries(optionDefinitions)){
  const setting=Object.prototype.hasOwnProperty.call(value,name)?value[name]:entry.default;
  if(typeof setting!=='boolean')throw Error(entry.label+'显示选项必须为布尔值');
  result[name]=setting;
 }
 return result;
}
function newOptions(profile){const free=normalize(profile)==='free';return Object.fromEntries(Object.entries(optionDefinitions).map(([name,entry])=>[name,free?entry.new_free:entry.default]));}
const api={normalize,normalizeOptions,newOptions,html,plan,wordTokens};root.ReportProfile=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
