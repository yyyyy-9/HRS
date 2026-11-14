/* Canonical Bridge model adapter. HRS ships an exact generated copy; both the
   existing CLI browser and the open editor consume the same HRS lexer/profile. */
(function(root){
'use strict';
const SCHEMA='hrs-word-browser-model-v1';
const WORD_HTML_STYLES={b:'strong',strong:'strong',i:'em',em:'em',s:'del',strike:'del',del:'del',
 u:'hrsUnderline',sub:'hrsSubscript',sup:'hrsSuperscript',kbd:'text'};

function wordInlineHtml(tokens){
 if(!tokens.some(token=>token.type==='html'&&!token.block))return tokens;
 const pending=[],replacements=new Map(),ends=new Set();
 for(const [index,token] of tokens.entries()){
  if(token.type!=='html'||token.block)continue;
  const raw=token.raw.trim();
  if(/^<!--[\s\S]*-->$/.test(raw)){replacements.set(index,null);continue;}
  const tag=/^<(\/?)([a-z][a-z0-9-]*)\s*(\/?)>$/i.exec(raw);
  if(!tag)continue;
  const name=tag[2].toLowerCase();
  if(name==='br'&&!tag[1]){replacements.set(index,{type:'br'});continue;}
  if(tag[3]||!Object.prototype.hasOwnProperty.call(WORD_HTML_STYLES,name))continue;
  if(!tag[1])pending.push({index,name});
  else if(pending[pending.length-1]?.name===name){
   const pair=pending.pop();
   replacements.set(pair.index,{type:WORD_HTML_STYLES[name],tokens:[],opening:tokens[pair.index].raw,closing:token.raw});
   ends.add(index);
  }
 }
 // Keep each unmapped or unmatched token at its own position.
 const output=[],stack=[output];
 for(const [index,token] of tokens.entries()){
  if(ends.has(index)){stack.pop();continue;}
  const mapped=replacements.has(index)?replacements.get(index):token;
  if(mapped)stack[stack.length-1].push(mapped);
  if(replacements.has(index)&&mapped?.tokens)stack.push(mapped.tokens);
 }
 return output;
}

function noteKeys(tokens){
 const keys=new Set();
 marked.walkTokens(tokens,token=>{if(token.type==='hrsFootnoteRef')keys.add(token.key);});
 return keys;
}

function build(req){
 const fullTokens=marked.lexer(SourceBlocks.normalized(req.markdown).text);
 const profilePlan=ReportProfile.plan(req.markdown,'engineering',SourceMap.create(req.markdown,fullTokens).blocks);
 const notes=ReportNotes.prepare(marked,fullTokens);
 if(notes.diagnostics.length)throw Error(notes.diagnostics.join('；'));
 const rich=(source,inline,base=null)=>{
  if(inline)source=ReportTables.compactDisplayText(source);
  const abstractIndices=new Set();
  if(!inline&&base!==null){
   const original=marked.lexer(SourceBlocks.normalized(source).text),records=SourceMap.create(source,original).blocks;
   for(const r of records)if(profilePlan.abstracts.some(a=>a.start===base+r.start))abstractIndices.add(original.indexOf(r.token));
  }
  const math=[],prefix='HRSMATH'+crypto.randomUUID().replaceAll('-','')+'X';
  const protectedSource=ReportTableContent.tokenize(source).map(t=>t.kind==='math'?(math.push(t),prefix+(math.length-1)+'X'):t.text).join('');
  const marker=new RegExp('('+prefix+'[0-9]+X)','g');
  const mathFor=value=>math[Number(value.slice(prefix.length,-1))];
  const restore=value=>typeof value==='string'&&value.includes(prefix)?value.replace(marker,match=>mathFor(match).raw):value;
  const expand=tokens=>wordInlineHtml(tokens.flatMap(token=>{
   const protectedText=token.text;
   // Only Marked's prose leaves may expand a math marker. Every literal field
   // keeps its original characters, including de-indented code inside lists/quotes.
   for(const field of ['raw','text','href','title','body']){
    if(typeof token[field]==='string')token[field]=restore(token[field]);
   }
   if(token.type==='hrsStyledList')token.tokens=rich(token.body,false);
   else if(token.tokens)token.tokens=expand(token.tokens);
   if(token.items)for(const item of token.items){item.raw=restore(item.raw);item.tokens=expand(item.tokens);}
   if(token.type==='text'&&!token.tokens&&typeof protectedText==='string'&&protectedText.includes(prefix)){
    return protectedText.split(marker).filter(Boolean).map(text=>{
     if(!text.startsWith(prefix))return {...token,text};
     const expression=mathFor(text);
     return {type:'hrsMath',...expression,source_offset:base===null?undefined:base+expression.from};
    });
   }
   return [token];
  }));
  const parsed=inline?marked.Lexer.lexInline(protectedSource):marked.lexer(protectedSource);
  for(const index of abstractIndices)if(parsed[index]?.type==='blockquote')parsed[index].type='hrsAbstract';
  return expand(ReportProfile.wordTokens(parsed));
 };
 const result={schema:SCHEMA,numbering_policy:'document-v2',render_options:req.render_options,request_sha256:req.request_sha256,output_options:req.output_options,
  tokens:req.sections.map((source,i)=>rich(source,false,req.sectionStarts[i])),
  inline:req.inline.map(source=>rich(source,true)),profile:profilePlan,
  diagrams:{},svgAssets:{},graphic_errors:{diagrams:{},svgAssets:{}}};
 const wanted=noteKeys([...result.tokens.flat(),...result.inline.flat()]);
 for(const key of wanted)if(!notes.definitions.has(key))throw Error('脚注未定义：'+key);
 const bodies=new Map(),sources=new Map();
 // A Set visits newly discovered targets once, even for self-references or cycles.
 for(const key of wanted){
  if(!notes.definitions.has(key))continue;
  const source=notes.definitions.get(key),tokens=rich(source,false);
  bodies.set(key,tokens);sources.set(key,source);
  for(const nested of noteKeys(tokens))wanted.add(nested);
 }
 result.footnotes=Object.fromEntries(bodies);
 result.footnote_sources=Object.fromEntries(sources);
 return result;
}
async function png(svg){
 const parsed=new DOMParser().parseFromString(svg,'image/svg+xml'),node=parsed.documentElement;
 if(node.localName!=='svg'||parsed.querySelector('parsererror'))throw Error('Word 图形不是有效 SVG');
 // Decode the original viewport. Scaling the decoded image on the canvas
 // preserves drawings that use absolute coordinates and have no viewBox.
 const blob=new Blob([new XMLSerializer().serializeToString(node)],{type:'image/svg+xml'});
 const url=URL.createObjectURL(blob),img=new Image();
 try{
  await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('Word SVG 预览无法解码'));img.src=url;});
  const w=img.naturalWidth,h=img.naturalHeight;
  if(!(w>0&&h>0))throw Error('Word SVG 图像尺寸无效');
  const scale=Math.min(2,4000/w,4000/h,Math.sqrt(16000000/(w*h)));
  const width=Math.max(1,Math.ceil(w*scale)),height=Math.max(1,Math.ceil(h*scale));
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const context=canvas.getContext('2d');if(!context)throw Error('浏览器不能生成 Word 图形');
  context.fillStyle='#fff';context.fillRect(0,0,width,height);context.drawImage(img,0,0,width,height);
  const result=canvas.toDataURL('image/png').split(',')[1];
  if(result.length>16*1024*1024)throw Error('Word 图形预览超过单图上限');
  return result;
 }finally{URL.revokeObjectURL(url);}
}
async function renderGraphics(result,field,items,renderSvg){
 for(const [key,source] of Object.entries(items||{})){
  try{result[field][key]=await png(await renderSvg(source));}
  catch(error){
   const summary=String(error?.message||error||'').trim().split(/\r?\n/,1)[0].slice(0,240);
   result.graphic_errors[field][key]=summary||'图形转换失败';
  }
 }
}
async function render(req){
 const result=build(req);
 await renderGraphics(result,'diagrams',req.diagram_sources,source=>ReportMermaid.render(source));
 await renderGraphics(result,'svgAssets',req.svg_sources,encoded=>{
  const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
 });
 return result;
}
root.ReportBridgeModel={SCHEMA,build,render};
})(window);
