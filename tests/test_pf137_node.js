/* PF13.7: explicit ID cases are shared with Python; no second validation rule. */
'use strict';
const assert=require('node:assert/strict');
const cases=require('./fixtures/object_id_cases.json').cases;
const catalog=require('../app/web/object_catalog.js');
const model=(kind,id)=>kind==='table'
 ? {schema:'report-table-v1',id,caption:'test',rows:[[{text:'x',rowspan:1,colspan:1}]]}
 : {schema:'report-figure-v1',id,caption:'test',kind:'mermaid',source:'flowchart LR\nA-->B'};
let checked=0;
for(const row of cases)for(const kind of ['table','figure']){
 const obj=model(kind,row[kind+'Id']),before=JSON.stringify(obj);
 assert.equal(catalog.validObject('report-'+kind,obj),row.valid,kind+': '+row.name);
 assert.equal(JSON.stringify(obj),before,'validator must not rewrite input');
 checked++;
}
const tableId='tbl-'+'a'.repeat(60),figureId='fig-'+'a'.repeat(60);
const numbers=catalog.numbering([
 {kind:'table',id:'tbl-native',sourceKind:'gfm-pipe',numbered:false},
 {kind:'table',id:tableId,numbered:true},
 {kind:'figure',id:figureId,numbered:true},
 {kind:'table',id:tableId,numbered:true},
]);
assert.deepEqual(numbers.items.map(item=>item.number),[1,2,1,null]);
assert.equal(numbers.items[3].duplicate,true);
assert.equal(numbers.byId.get(tableId).number,2);
console.log(`PF13.7 Node: ${cases.length} shared cases / ${checked} object validations; ID boundaries, no mutation, GFM/duplicate numbering OK`);
