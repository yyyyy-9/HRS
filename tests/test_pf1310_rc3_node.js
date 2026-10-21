/* RC3-04: ranges come from the shared Marked AST, never from code examples. */
'use strict';
const assert=require('node:assert/strict');
const marked=require('../app/web/vendor/marked.js');
global.SourceBlocks=require('../app/web/source_blocks.js');
global.ReportLayout=require('../app/web/report_layout.js');
const SourceMap=require('../app/web/source_map.js');
const lists=require('../app/web/list_styles.js');lists.installMarked(marked);
const samples=[
 '# 标题😀\r\n\r\n- 捕捉一个念头\r\n  - [X] 任务😀\r\n    - [ ] 深层\r\n- [x] 重复\r\n- [ ] 重复\r\n',
 '- [ ] outer\n\n  ```md\n  - [ ] example\n  ```\n\n  - [x] inner\n\n- [ ] last\n',
 '> - [ ] quoted\n>   - [x] nested\n',
 '<!-- hrs:list style=decimal -->\n1. [ ] first\n1. [x] next\n',
 '```md\n- [ ] fenced\n```\n\n`- [ ] code`\n\n    - [ ] indented code\n\n<div><input type="checkbox" disabled></div>\n'
];
const counts=[4,3,2,2,0];
samples.forEach((source,i)=>{
 const records=SourceMap.create(source,marked.lexer(SourceBlocks.normalized(source).text)).blocks;
 const tasks=records.flatMap(record=>SourceMap.taskRanges(source,record,marked));
 assert.equal(tasks.length,counts[i],JSON.stringify(tasks));
 for(const task of tasks){
  assert.match(source.slice(task.start-1,task.end+1),/^\[[ xX]\]$/);
  assert.equal(task.checked,/x/i.test(source.slice(task.start,task.end)));
  assert.equal(task.end-task.start,1);
 }
});
console.log('RC3 task ranges PASS: 5 Markdown/CRLF/Unicode/nested/code scopes');
