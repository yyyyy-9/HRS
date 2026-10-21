#!/usr/bin/env node
/* PF13.1 — deterministic offline doc exporter; the project documentation
 * dogfoods the bundled Marked parser and the same HTML report reader.
 * Separate theme CSS only customizes presentation, never markdown semantics.
 * No runtime network, no report.md mutation, no external Markdown parser.
 * Usage: node app/tools/build_readable_docs.js [--write|--check]
 */
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'..'), DOC=path.join(ROOT,'docs');
const marked=require(path.join(ROOT,'web/vendor/marked.js'));
const reader=fs.readFileSync(path.join(ROOT,'web/report_reader.js'),'utf8');
const designTokens=fs.readFileSync(path.join(ROOT,'web/design_tokens.css'),'utf8');
// Help keeps its established blue appearance independently of document palette.
const colorTheme=fs.readFileSync(path.join(ROOT,'web/theme.css'),'utf8');
const printStyle=fs.readFileSync(path.join(ROOT,'web/print.css'),'utf8');
const readerStyle=fs.readFileSync(path.join(ROOT,'web/report_reader.css'),'utf8');
const helpLayout=fs.readFileSync(path.join(__dirname,'readable_docs_theme.css'),'utf8');
const surfaces=fs.readFileSync(path.join(ROOT,'web/surface_components.css'),'utf8');
const theme=[colorTheme,printStyle,readerStyle,helpLayout,designTokens,surfaces].join('\n');
const VERSION='v'+JSON.parse(fs.readFileSync(path.join(ROOT,'release.json'),'utf8')).version;
const documents=[
 ['USER_GUIDE.md','使用手册','USER_GUIDE.html','help.html'],
 ['CHANGELOG_READABLE.md','更新记录','CHANGELOG_READABLE.html','CHANGELOG_READABLE.html'],
 ['MODULE_OVERVIEW.md','模块说明','MODULE_OVERVIEW.html','MODULE_OVERVIEW.html'],
 ['WORD_COMPILER_HANDOFF.md','Word 数据交接','WORD_COMPILER_HANDOFF.html','WORD_COMPILER_HANDOFF.html'],
 ['CURRENT_STATUS.md','当前版本状态','CURRENT_STATUS.html'],
 ['SHORT_TERM_PLAN.md','短期计划','SHORT_TERM_PLAN.html'],
 ['LONG_TERM_ROADMAP.md','长期发展路线','LONG_TERM_ROADMAP.html'],
];
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
function imageData(href){
 // Allow only local guide-assets; no local absolute paths or network fetches.
 if(!/^guide-assets\/[A-Za-z0-9._-]+\.(png|jpe?g|webp|svg)$/i.test(href)){
  throw Error('Offline doc has nonlocal image: '+href);
 }
 const real=path.join(DOC,href);
 const suffix=path.extname(real).slice(1).toLowerCase();
 const type={png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',svg:'image/svg+xml'}[suffix];
 return 'data:'+type+';base64,'+fs.readFileSync(real).toString('base64');
}
function destination(href,scope){
 if(/^(?:https?:|mailto:|#)/i.test(href))return href;
 if(/^(?:javascript:|data:|file:|\/|\\|[A-Za-z]:)/i.test(href))throw Error('Unsafe documentation link: '+href);
 // Resolve every link from its Markdown source, then make it relative to the
 // generated page. This works for both file:// and the real /web, /docs routes.
 const [,reference,suffix='']=href.match(/^([^?#]*)([?#].*)?$/);
 let target=path.resolve(DOC,decodeURIComponent(reference));
 const relative=path.relative(ROOT,target);
 if(relative==='..'||relative.startsWith('..'+path.sep)||path.isAbsolute(relative)){
  throw Error('Documentation link outside App: '+href);
 }
 const canonical=documents.find(doc=>target===path.join(DOC,doc[0])||target===path.join(DOC,doc[2]));
 if(canonical){
  target=scope==='web'&&canonical[3]?path.join(ROOT,'web',canonical[3]):path.join(DOC,canonical[2]);
 }
 return path.relative(scope==='web'?path.join(ROOT,'web'):DOC,target).split(path.sep).join('/')+suffix;
}
function build(name,title,scope){
 const markdown=fs.readFileSync(path.join(DOC,name),'utf8');
 const sourceHash=crypto.createHash('sha256').update(markdown,'utf8').digest('hex');
 let headingCount=0,nav=[];
 const renderer=new marked.Renderer();
 renderer.heading=(text,level)=>{
  const id='section-'+(++headingCount);
  if(level>=2&&level<=4)nav.push(`<a class="level${level}" href="#${id}">${text.replace(/<[^>]+>/g,'')}</a>`);
  return `<h${level} id="${id}">${text}</h${level}>\n`;
 };
 renderer.image=(href,title,text)=>`<img src="${esc(imageData(href))}" alt="${esc(text)}"${title?` title="${esc(title)}"`:''}>`;
 renderer.link=(href,title,text)=>`<a href="${esc(destination(href,scope))}"${title?` title="${esc(title)}"`:''}>${text}</a>`;
 const htmlBody=marked.parse(markdown,{renderer,gfm:true,headerIds:false,mangle:false});
 const navText=nav.join('\n');
 const actions=`<div class="docs-actions"><a href="${scope==='web'?'help.html':'USER_GUIDE.html'}">使用手册</a><a href="CHANGELOG_READABLE.html">更新记录</a><a href="MODULE_OVERVIEW.html">模块说明</a></div>`;
 // Do not move the original MD content into a JS literal: this is the same
 // safe, static HTML + first-party DOM enhancements used by exported reports.
 const result='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+
  `<title>${esc(title)} · HTML Report Studio</title><meta name="hrs-markdown-sha256" content="${sourceHash}"><style>${theme}</style></head>`+
  '<body class="theme-engineering"><div class="docs-shell"><nav class="docs-nav">'+
  `<div class="docs-brand">R. HTML Report Studio</div><div class="docs-desc">离线文档 · ${VERSION}<br>不需要联网，也不会读取你的报告</div>`+
  actions+navText+'</nav><main class="docs-main"><article class="docs-paper" data-hrs-reader-root="1">'+
  htmlBody+'</article><div class="docs-bottom">HTML Report Studio · 来自项目 Markdown · 离线 Marked</div></main></div>'+
  `<script id="hrs-reader-runtime">${reader}</script></body></html>`;
 if(result.includes('</script>')===false)throw Error('Reader runtime was not injected');
 return result;
}
function main(){
 const action=process.argv[2];
 if(action!=='--check'&&action!=='--write')throw Error('Choose --check or --write');
 let problem=0,checked=0;
 for(const [name,title,...targets] of documents){
  for(const [i,relative] of targets.entries()){
   const expected=build(name,title,i===1?'web':'docs');
   const real=path.join(i===1?path.join(ROOT,'web'):DOC,relative);
   if(action==='--write'){
    fs.writeFileSync(real,expected,'utf8');
   }else if(!fs.existsSync(real)||fs.readFileSync(real,'utf8')!==expected){
    console.error('STALE GENERATED DOC:',path.relative(ROOT,real),'from',name);problem++;
   }
   checked++;
  }
 }
 console.log(`Readable Docs ${action}: ${checked} offline HTML targets, canonical Markdown + reader + embedded local images`);
 if(problem)process.exitCode=1;
}
try{main();}catch(err){console.error(err.stack);process.exitCode=1;}
