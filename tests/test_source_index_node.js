'use strict';
// PERF-01: indexed lookups must equal the original exhaustive source semantics.
const assert=require('node:assert/strict');
global.marked=require('../app/web/vendor/marked.js');
global.ReportTableContent=require('../app/web/table_content.js');
global.ReportLayout=require('../app/web/report_layout.js');
global.SourceBlocks=require('../app/web/source_blocks.js');
const SourceMap=require('../app/web/source_map.js');
const figure=id=>'```report-figure\r\n'+JSON.stringify({schema:'report-figure-v1',id,caption:'保留😀',kind:'image',src:'assets/demo.png',alt:''})+'\r\n```\r\n';
const source='# 测试😀\r\n\r\n## 目的 {#sec-purpose}\r\n\r\n正文 @sec:sec-purpose。\r\n\r\n<div>\r\n\r\n<p>卡片</p>\r\n</div>\r\n\r\n'+figure('fig-one')+'\r\n'+figure('fig-one');
const tokens=marked.lexer(SourceBlocks.normalized(source).text);
const ordinary=SourceBlocks.scan(source),lex=marked.lexer;let calls=0;
marked.lexer=(...args)=>{calls++;return lex(...args);};
const reused=SourceBlocks.scan(source,tokens),map=SourceMap.create(source,tokens);
marked.lexer=lex;
assert.deepEqual(reused,ordinary);assert.equal(calls,0,'Existing tokens must not be lexed again for HTML folding');
for(const position of [-Infinity,Infinity,NaN,-1,0,...Array.from({length:source.length*2+3},(_,i)=>i/2)]){
 const pos=Math.max(0,Math.min(source.length,position));
 const expected=map.blocks.find(b=>pos>=b.start&&pos<b.end)||map.blocks.find(b=>b.start>=pos)||map.blocks.at(-1)||null;
 assert.equal(map.at(position),expected,'Boundary differs at '+position);
}
assert.equal(map.object('fig-one'),null,'Duplicate identities must remain ambiguous');
const figures=map.blocks.filter(b=>b.objectId==='fig-one');assert.equal(figures.length,2);
map.setObjectId(figures[1],'fig-two');assert.equal(map.object('fig-one'),figures[0]);assert.equal(map.object('fig-two'),figures[1]);
map.setObjectId(figures[1],null);assert.equal(map.object('fig-two'),null);
assert.throws(()=>map.setObjectId({...figures[0]},'fig-foreign'),/范围|map|record|记录/i);
const empty=SourceMap.create('',[]);assert.equal(empty.at(0),null);assert.equal(empty.object('nothing'),null);
console.log('Source index boundaries, duplicate identities, index invalidation, HTML token reuse and CRLF/Unicode PASS');
