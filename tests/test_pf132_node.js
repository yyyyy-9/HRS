/* PF13.2: editor GFM block grammar, math tokenizer, highlighter byte ranges. */
'use strict';
const assert=require('node:assert/strict');
const path=require('node:path');
const root=path.resolve(__dirname,'../app/web');
const pipe=require(path.join(root,'pipe_tables.js'));
global.ReportPipeTables=pipe;
global.ReportLayout={isGroupOpen:()=>false};
const source=require(path.join(root,'source_blocks.js'));
global.SourceBlocks=source;
const math=require(path.join(root,'table_content.js'));
global.ReportTableContent=math;
const h=require(path.join(root,'code_highlight.js'));
const raw=String.raw`| TCC 元素 | 含义 |
|---|---|
| \(T_{11}\) | 自身贡献 |
| a\|b | 干涉项 |`;
const md=raw.replaceAll('\\r\\n','\r\n');
const doc='## 测试\n\n'+md+'\n\n: 表题 {#tbl-tcc}\n\n```markdown\n| not | a |\n|---|---|\n```';
const original=doc;
const blocks=source.scan(doc);
assert.equal(blocks.filter(b=>b.language==='gfm-pipe').length,1);
const table=blocks.find(b=>b.language==='gfm-pipe');
assert(table.summary.includes('Markdown 表格'));
assert(!table.automatic);
assert.equal(table.body,doc.slice(table.from,table.to));
assert.equal(doc,original,'fold source scan must be read-only');
const crlfDoc='标题\r\n'+raw.replaceAll('\n','\r\n')+'\r\n结尾';
const crlfBlock=source.scan(crlfDoc).find(b=>b.language==='gfm-pipe');
assert(crlfBlock,'CRLF table must be recognized');
assert.equal(crlfBlock.body,crlfDoc.slice(crlfBlock.from,crlfBlock.to));
assert.equal(crlfDoc.slice(crlfBlock.from,crlfBlock.to).includes('\r\n'),true);
assert.equal(crlfDoc,'标题\r\n'+raw.replaceAll('\n','\r\n')+'\r\n结尾');
assert.equal(source.normalized(doc).text.includes('\r'),false);
assert.equal(blocks.filter(b=>b.language==='markdown').length,1);
assert.equal(source.scan('```text\n| A | B |\n|---|---|\n```').filter(b=>b.language==='gfm-pipe').length,0);
assert.equal(source.scan('正文 \\| 错误\n| :--- | :--- |').filter(b=>b.language==='gfm-pipe').length,0);
const tokens=h.sourceTokens(doc,0,doc.length);
assert(tokens.some(x=>x.kind==='table-pipe'));
assert(tokens.some(x=>x.kind==='table-divider'));
assert(tokens.some(x=>x.kind==='math-marker'));
assert(tokens.some(x=>x.kind==='math'));
const lines=h.sourceLineDecorations(doc,0,doc.length);
assert(lines.some(x=>x.kind==='table-head-line'));
assert(lines.some(x=>x.kind==='table-separator-line'));
assert(lines.some(x=>x.kind==='table-caption-line'));
for(const token of tokens)assert(token.from>=0&&token.from<token.to&&token.to<=doc.length);
for(const line of lines)assert(line.from>=0&&line.from<doc.length);
const cases=[
 [String.raw`\(T_{12},T_{21}\)`,'T_{12},T_{21}'],
 [String.raw`$T_{11}$`,'T_{11}'],
 [String.raw`$E=mc^2$`,'E=mc^2'],
];
for(const [input,tex] of cases){
 const parts=math.tokenize('甲 '+input+' 乙');
 assert.equal(parts.filter(p=>p.kind==='math').length,1,input);
 assert.equal(parts.find(p=>p.kind==='math').tex,tex);
 assert.equal(parts.map(x=>x.raw||x.text).join(''),'甲 '+input+' 乙');
}
for(const input of [String.raw`\\(not math\\)`,'`\\(code\\)`',String.raw`\$5$`,String.raw`\(unclosed`,String.raw`\(broken
multiline\)`])
 assert.equal(math.tokenize(input).filter(p=>p.kind==='math').length,0,input);
const data=pipe.parseRaw(raw.replaceAll('\\r\\n','\r\n'));
assert(data.model.rows[1][0].text.includes('\\(T_{11}\\)'));
assert.equal(pipe.stringify(data.model,{newline:'\r\n'}).includes('\\(T_{11}\\)'),true);
console.log('PF13.2 Node: GFM source fold + syntax offsets + TeX lexing + CRLF + escaped pipe OK');
