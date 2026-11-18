'use strict';
// PROFILE-01: one source map supplies derived heading numbers and the bounded abstract role.
const assert=require('node:assert/strict');
global.marked=require('../app/web/vendor/marked.js');
require('../app/web/report_layout.js');require('../app/web/table_content.js');
require('../app/web/source_blocks.js');require('../app/web/source_map.js');
const profile=require('../app/web/render_profile.js');
const source='# Report\r\n\r\n> 摘要：范围明确。\r\n\r\n## First\r\n\r\n### Detail\r\n\r\n```text\r\n## literal\r\n```\r\n\r\n## Last\r\n';
const plan=profile.plan(source,'engineering');
assert.deepEqual(plan.headings.map(x=>x.number),['','1','1.1','2']);
assert.equal(plan.abstracts.length,1);assert.equal(source.slice(plan.abstracts[0].start,plan.abstracts[0].end).trim(),'> 摘要：范围明确。');
assert.equal(profile.plan(source,'free').headings.every(x=>x.number===''),true);
assert.equal(profile.plan('# T\n\n> 普通说明\n\n## A\n\n> 摘要：这是正文中的引用\n','engineering').abstracts.length,0);
assert.equal(profile.plan('# T\n\n```md\n> 摘要：示例\n```\n\n## A\n','engineering').abstracts.length,0);
assert.equal(profile.html('<div>card</div>','engineering'),'&lt;div&gt;card&lt;/div&gt;');
assert.equal(profile.html('<div>card</div>','free'),'<div>card</div>');
assert.throws(()=>profile.normalize('unknown'),/模式|profile/i);
assert.equal(ReportTableContent.tokenize('literal \\$E=mc^2\\$').some(t=>t.kind==='math'),false);
require('../app/web/pipe_tables.js');
const preflight=require('../app/web/preflight.js');
const currencyDoc=[
 '# 成本与波长核对',
 '',
 '## 1.1 方案报价',
 '',
 '单套预算 $100。',
 '',
 '批量从 $1,200 降至 $980。',
 '',
 '优惠至 $950，波长 $248.33\\ \\mathrm{nm}$ 与 $2\\text{阶系统}$，已转义 \\$50，代码 `$60`。',
 '',
 '| 部件 | 初版 | 终版 |',
 '| --- | --- | --- |',
 '| 探测器 | $1,200 | $950 |',
 '',
 '```python',
 'cost = "$999"',
 '```',
 ''
].join('\n');
const currencyTokens=marked.lexer(SourceBlocks.normalized(currencyDoc).text);
const currencyMap=SourceMap.create(currencyDoc,currencyTokens);
const currencyWarnings=preflight.scanCurrencyWarnings({source:currencyDoc,tokens:currencyTokens,map:currencyMap});
assert.equal(currencyWarnings.length,5,JSON.stringify(currencyWarnings));
assert.equal(currencyDoc.slice(currencyWarnings[0].start,currencyWarnings[0].end),'$100');
assert.equal(currencyDoc.slice(currencyWarnings[1].start,currencyWarnings[1].end),'$1,200 降至 $');
assert.equal(currencyDoc.slice(currencyWarnings[2].start,currencyWarnings[2].end),'$950');
assert.equal(currencyDoc.slice(currencyWarnings[3].start,currencyWarnings[3].end),'$1,200');
assert.equal(currencyDoc.slice(currencyWarnings[4].start,currencyWarnings[4].end),'$950');
const stubContract={diagnostics:[{code:'HEADING_SOURCE_PREFIX',severity:'warning',line:3,start:10,end:18,message:'手工章号'}],output_blockers:[],source_snapshot:{utf16_length:currencyDoc.length}};
const checkedDefault=preflight.complete(stubContract,{source:currencyDoc,tokens:currencyTokens,map:currencyMap,notes:{problems:[]}},'engineering',{});
assert.equal(checkedDefault.valid,true);
assert.equal(checkedDefault.safeToCompile,false);
assert.equal(checkedDefault.word_compile_ready,false);
const checkedAccepted=preflight.complete(stubContract,{source:currencyDoc,tokens:currencyTokens,map:currencyMap,notes:{problems:[]}},'engineering',{acceptNumberedHeadings:true});
assert.equal(checkedAccepted.safeToCompile,true);
assert.equal(checkedAccepted.word_compile_ready,true);
console.log('PF13.9 profile source ranges, numbering, abstract and HTML policy PASS');
