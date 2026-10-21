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
console.log('PF13.9 profile source ranges, numbering, abstract and HTML policy PASS');
