'use strict';
// V1-MAINTENANCE-01: line indices, palette and nested leases share real modules.
const assert=require('node:assert/strict');
global.marked=require('../app/web/vendor/marked.js');
global.ReportTableContent=require('../app/web/table_content.js');
global.ReportLayout=require('../app/web/report_layout.js');
global.SourceBlocks=require('../app/web/source_blocks.js');
global.SourceMap=require('../app/web/source_map.js');
global.ReportNotes=require('../app/web/note_syntax.js');
ReportNotes.installMarked(marked);
const settings=require('../app/web/product_settings.js');
const Catalog=require('../app/web/object_catalog.js');
assert.deepEqual(Catalog.sourceTexts({}, {rows:2,images:[{caption:'Subfigure[^n]'}],caption:'Group'}),['Subfigure[^n]','Group']);
assert.deepEqual(Catalog.sourceTexts({}, {rows:[[{text:'Cell[^n]'}]],caption:'Table'}),['Table','Cell[^n]']);
const text='# Test😀\r\n\r\nText[^a]\r\n\r\n[^a]: First\r\n[^a]: Duplicate\r\n\r\nText[^missing]\r\n';
const tokens=marked.lexer(SourceBlocks.normalized(text).text),map=SourceMap.create(text,tokens);
for(let i=0;i<=text.length;i++)assert.equal(map.lineAt(i),text.slice(0,i).split('\n').length);
const notes=ReportNotes.prepare(marked,tokens,{source:text,records:map.blocks,map});
assert.deepEqual(notes.problems.map(p=>[p.code,p.line]),[['DUPLICATE_FOOTNOTE',6],['UNDEFINED_FOOTNOTE',8]]);
for(const c of settings.highlights.choices.filter(c=>c.marker)){
 const html=marked.parse('=='+c.marker+'Text==');
 assert(html.includes(c.color),c.id+' marker must use the same palette as UI');
}
const Operations=require('../app/web/operations.js'),editor={},node={disabled:false},other={disabled:true};
const locks=Operations.create({editor});
const outer=locks.acquire({nodes:[node,other],editing:true}),inner=locks.acquire({nodes:[node],editing:true});
outer();assert.equal(node.disabled,true);assert.equal(editor.readOnly,true);assert.equal(other.disabled,true);
locks.setDisabled(node,true);inner();assert.equal(editor.readOnly,false);assert.equal(node.disabled,true);
const lease=locks.acquire({nodes:[node]});locks.setDisabled(node,false);lease();assert.equal(node.disabled,false);lease();assert.equal(node.disabled,false);
console.log('Maintenance: CRLF/UTF16 note lines, shared eight-color palette and nested UI leases PASS');
