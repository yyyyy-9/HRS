/* PF13.5: JS follows the same fixture semantics as Python, with one number policy. */
'use strict';
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const root=path.resolve(__dirname,'../app/web');
const cases=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/pf135_contract_cases.json'),'utf8'));
const Pipe=require(path.join(root,'pipe_tables.js'));
require(path.join(root,'report_layout.js'));require(path.join(root,'report_equations.js'));
require(path.join(root,'table_content.js'));
const ObjectCatalog=require(path.join(root,'object_catalog.js'));
const Source=require(path.join(root,'source_blocks.js'));
const Map=require(path.join(root,'source_map.js'));
const markedModule=require(path.join(root,'vendor/marked.js')),marked=markedModule.marked||markedModule;
for(const [key,id] of [['canonicalCaption','tbl-adjacent'],['legacyCaption','tbl-legacy']]){
 const text=cases[key],block=Source.scan(text)[0];
 assert.equal(block.language,'gfm-pipe');assert.equal(text.slice(block.from,block.to).includes(id),true);
 assert.equal(Pipe.parseRaw(text).id,id);
}
assert.equal(Source.scan(cases.notACaption)[0].body.includes('tbl-nope'),false);
const newTable={caption:'canonical',rows:[[{text:'one',rowspan:1,colspan:1}]],align:[null]};
const authored=Pipe.stringify(newTable,{id:'tbl-canonical'});
assert.match(authored,/\| one \|\n\| --- \|\n: canonical \{#tbl-canonical\}$/);
const refs=Map.create(cases.canonicalCaption+'\n'+cases.referenceMath,
  marked.lexer(cases.canonicalCaption+'\n'+cases.referenceMath)).blocks.flatMap(b=>b.references);
assert.deepEqual(refs.map(ref=>ref.target),['tbl-adjacent']);
const standalone=Map.create('\\[\n@tbl:tbl-nope\n\\]\n',marked.lexer('\\[\n@tbl:tbl-nope\n\\]\n'));
assert.equal(standalone.blocks.flatMap(b=>b.references).length,0);
const wrap=(id)=>'```report-table\n'+JSON.stringify({schema:'report-table-v1',id,caption:'',rows:[[{text:'x',rowspan:1,colspan:1}]]})+'\n```\n';
const group='::: {#fig-group layout-ncol=2}\n![A](assets/0123456789abcdef.png)\n![B](assets/0123456789abcdee.png)\n:::\n';
const fig='```report-figure\n'+JSON.stringify({schema:'report-figure-v1',id:'fig-one',kind:'mermaid',caption:'',source:'flowchart LR\nA[Start]-->B[End]'})+'\n```\n';
const str=wrap('invalid')+'\n'+cases.canonicalCaption+'\n'+wrap('tbl-good')+'\n'+fig+'\n'+group+'\n'+wrap('tbl-second');
const blocks=Source.scan(str);
assert.equal(blocks[0].summary,'结构化表格 · 源码待检查');
assert.ok(blocks.find(x=>x.object?.id==='tbl-good').summary.startsWith('表 1'));
assert.ok(blocks.find(x=>x.object?.id==='tbl-second').summary.startsWith('表 2'));
assert.ok(blocks.find(x=>x.object?.id==='fig-one').summary.startsWith('图 1'));
assert.ok(blocks.find(x=>x.object?.id==='fig-group').summary.startsWith('图 2'));
const dup=ObjectCatalog.numbering([{kind:'table',id:'tbl-same',numbered:true},{kind:'table',id:'tbl-same',numbered:true}]);
assert.equal(dup.items[1].duplicate,true);assert.equal(dup.items[1].number,null);
assert.equal(ObjectCatalog.validObject('report-table',{schema:'report-table-v1',id:'invalid',caption:'',rows:[]}),false);
// Semantic core comes from the same source module in the standalone offline reader.
const bundled=fs.readFileSync(path.join(root,'report_reader.js'),'utf8');
assert.ok(bundled.includes(fs.readFileSync(path.join(root,'object_catalog.js'),'utf8')));
console.log('PF13.5 JS contract: captions, references, shared numbering, offline bundle OK');
