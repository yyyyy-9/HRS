/* NUMBERING-02: ordinary and structured objects share document order. */
const assert=require('node:assert/strict');
const catalog=require('../app/web/object_catalog.js');
const numbered=catalog.numbering([
 {kind:'table',sourceKind:'gfm-pipe'},
 {kind:'table',id:'tbl-second',sourceKind:'enhanced'},
 {kind:'equation'}, {kind:'equation',id:'eq-second'},
 {kind:'figure',sourceKind:'mermaid'}, {kind:'figure',id:'fig-second'},
 {kind:'figure',id:'fig-second'}]);
assert.deepEqual(numbered.items.map(x=>x.number),[1,2,1,2,1,2,null]);
assert.deepEqual(numbered.counts,{figure:2,table:2,equation:2});
// SourceMap already owns intervening newlines: legacy blank-line captions
// must not disappear from the source catalog and restart the table count.
global.ReportPipeTables=require('../app/web/pipe_tables.js');
require('../app/web/report_layout.js');require('../app/web/report_equations.js');
global.SourceBlocks=require('../app/web/source_blocks.js');
const map=require('../app/web/source_map.js'),marked=require('../app/web/vendor/marked.js');
const enhanced='```report-table\n'+JSON.stringify({schema:'report-table-v1',id:'tbl-enhanced',caption:'',rows:[[{text:'2.30 V',rowspan:1,colspan:1}]]})+'\n```\n';
for(const separator of ['\n','\n\n']){
 const md='| A |\n|---|\n| 1 |'+separator+': 名称 {#tbl-native}\n\n'+enhanced;
 const result=catalog.indexSource(map.create(md,marked.lexer(md)));
 assert.deepEqual(result.items.map(x=>[x.id,x.number]),[['tbl-native',1],['tbl-enhanced',2]]);
}
console.log('NUMBERING-02 unified sequences and duplicate identity: PASS');
