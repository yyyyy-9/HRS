/* PF13.1: Python and JS consume exactly the same GFM fixtures. */
'use strict';
const assert=require('node:assert/strict'),P=require('../app/web/pipe_tables.js'),
 fixture=require('./fixtures/gfm_tables.json');
const marked=require('../app/web/vendor/marked.js');P.installMarked(marked);
for(const row of fixture.splits){
 assert.deepEqual(P.split(row.source),row.cells,'split: '+JSON.stringify(row.source));
}
for(const row of fixture.tables){
 const token=marked.lexer(row.source).find(t=>t.type==='table');
 assert.ok(token,'shared lexer recognizes math in table headers');
 assert.deepEqual([token.header,...token.rows].map(r=>r.map(c=>c.text)),row.rows);
 const actual=P.parseRaw(row.source);
 assert.equal(actual.id,row.id);
 assert.equal(actual.caption,row.caption);
 assert.deepEqual(actual.model.align,row.align);
 assert.deepEqual(actual.model.rows.map(line=>line.map(cell=>cell.text)),row.rows);
 const src=P.stringify(actual.model,{id:row.id,withCaption:!!row.caption});
 const restored=P.parseRaw(src);
 assert.deepEqual(restored.model.rows,actual.model.rows,'stringify/parser roundtrip: '+JSON.stringify(row.source.slice(0,50)));
}
for(let n=0;n<=6;n++){
 const value='a'+'\\'.repeat(n)+'|b';
 const model={rows:[[ {text:'header',rowspan:1,colspan:1}],[{text:value,rowspan:1,colspan:1}]],align:[null],caption:''};
 const source=P.stringify(model);
 assert.equal(P.parseRaw(source).model.rows[1][0].text,value,'roundtrip backslashes '+n);
}
console.log(`PF13.1 GFM cross-language fixtures OK: ${fixture.splits.length} splits and ${fixture.tables.length} tables`);
