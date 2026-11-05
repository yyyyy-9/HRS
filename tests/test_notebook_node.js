/* NOTEBOOK-01 / SPACE-01: source-derived scope and standalone dependency closure. */
'use strict';
const assert=require('node:assert/strict'),path=require('node:path');
const web=path.join(__dirname,'../app/web');
global.marked=require(web+'/vendor/marked.js');
for(const name of ['table_content','report_tables','pipe_tables','report_layout','list_styles','object_catalog','source_blocks','report_equations','source_map','note_syntax'])require(web+'/'+name+'.js');
ReportLayout.installMarked(marked);ReportEquations.installMarked(marked);ReportNotes.installMarked(marked);
const Notebook=require(web+'/notebook_view.js');
function view(source){const tokens=marked.lexer(SourceBlocks.normalized(source).text),map=SourceMap.create(source,tokens);return Notebook.index(source,map,tokens,ReportObjectCatalog.indexSource(map));}
const text='前言\r\n\r\n# 重名\r\n\r\n\r\n第一段[^n]\r\n\r\n\r\n第二段\r\n\r\n```md\r\n# 不是专题\r\n\r\n\r\n```\r\n\r\n# 重名\r\n\r\n目标 {#sec-b}\r\n\r\n[^n]: 外部说明\r\n';
const model=view(text);
assert.equal(model.topics.length,3);assert.equal(model.topics[0].title,'前言／未分组内容');
assert.equal(model.topics[1].title,model.topics[2].title);assert.notEqual(model.topics[1].key,model.topics[2].key);
assert.equal(model.at(text.indexOf('第一段')).key,model.topics[1].key);
assert.equal(model.extract(model.topics[1].key).markdown.includes('[^n]: 外部说明'),true);
assert.equal(model.extract(model.topics[1].key).markdown.includes('# 重名\r\n\r\n目标'),false);
assert.equal(model.gaps.filter(g=>g.lines===1).length,2);
assert.equal(view('# H\n\nA\n\nB').gaps.length,0);
assert.equal(view('> a\n>\n> b\n\n- a\n\n- b\n').gaps.length,0);
assert.equal(view('without heading\n').topics.length,1);
const cross=view('# A\n\n见 @sec:sec-b。\n\n# B {#sec-b}\n\n内容\n');
// Standard paragraph, hard break and Setext precedence stay owned by Marked.
assert.equal(marked.lexer('正文\n---\n')[0].type,'heading');
assert.equal(marked.lexer('正文\n\n---\n').at(-1).type,'hr');
assert.equal(marked.lexer('甲\n乙')[0].type,'paragraph');
assert.equal(marked.lexer('甲\n\n  乙').filter(t=>t.type==='paragraph').length,2);
assert.equal(marked.lexer('甲  \n乙')[0].tokens.some(t=>t.type==='br'),true);
for(const [before,after] of [['a😀b','a😃b'],['甲\r\n乙','甲\r\n  乙'],['abc',''],['','新增']]){
 const r=SourceMap.changedRange(before,after);
 assert.equal(before.slice(0,r.start)+after.slice(r.start,r.end)+before.slice(r.oldEnd),after);
 assert.equal(/[\uDC00-\uDFFF]/.test(after[r.start]||''),false);
}
assert.throws(()=>cross.extract(cross.topics[0].key),/跨专题.*sec-b/);
const links=view('# A\n\n[链接][ref]\n\n# B\n\n[ref]: https://example.org/ "标题"\n');
assert.equal(marked.lexer(links.extract(links.topics[0].key).markdown).links.ref.href,'https://example.org/');
assert.equal(text,model.source);console.log('NOTEBOOK-01 / SPACE-01: source, gaps, references and definitions PASS');
const figure=id=>'```report-figure\n'+JSON.stringify({schema:'report-figure-v1',id:'fig-'+id,kind:'mermaid',caption:'',source:'flowchart LR\nA-->B'})+'\n```\n';
const scoped=view('# A\n\n'+figure('a')+'\n# B\n\n'+figure('b')+'\n'+figure('a'));
const local=scoped.presentation(scoped.topics[1].key);
assert.equal(local.catalog.items[0].number,1);
assert.equal(local.catalog.items[1].duplicate,true);assert.equal(local.catalog.items[1].number,null);
assert.equal(local.catalog.byId.has('fig-a'),false);
assert.equal(local,scoped.presentation(scoped.topics[1].key));
assert.equal(scoped.presentation(scoped.topics[0].key).catalog.items[0].number,1);
console.log('TOPIC-LINKS-01: local numbering retains full-document duplicate identity and cached projection PASS');
