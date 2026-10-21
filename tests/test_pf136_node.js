/* PF13.6: one browser object catalog works without Object.hasOwn. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const dir=path.resolve(__dirname,'../app/web');
const catalog=fs.readFileSync(path.join(dir,'object_catalog.js'),'utf8');
const reader=fs.readFileSync(path.join(dir,'report_reader.js'),'utf8');
assert(!catalog.includes('Object.hasOwn('));
assert(!reader.includes('Object.hasOwn('));
assert(reader.includes(catalog));
const ctx=vm.createContext({console});
vm.runInContext('Object.hasOwn = undefined',ctx);
vm.runInContext(fs.readFileSync(path.join(dir,'report_clone.js'),'utf8')+'\n'+fs.readFileSync(path.join(dir,'report_tables.js'),'utf8')+'\n'+catalog,ctx);
const records=[
 {kind:'table',id:'tbl-a',numbered:true},
 {kind:'table',id:'tbl-native',sourceKind:'gfm-pipe',numbered:false},
 {kind:'figure',id:'fig-a',numbered:true},
 {kind:'table',id:'tbl-b',numbered:true},
 {kind:'figure',id:'fig-b',numbered:true},
 {kind:'equation',id:'eq-a',numbered:true},
];
const numbers=ctx.ReportObjectCatalog.numbering(records).items.map(r=>r.number);
assert.deepEqual(Array.from(numbers),[1,null,1,2,2,1]);
assert(ctx.ReportObjectCatalog.validObject('report-table',{
 schema:'report-table-v1',id:'tbl-untitled',caption:'',rows:[[{text:'x',rowspan:1,colspan:1}]]}));
assert(ctx.ReportObjectCatalog.validObject('report-figure',{
 schema:'report-figure-v1',id:'fig-untitled',kind:'image',caption:'',src:'assets/0123456789abcdef.svg',alt:''}));
console.log('PF13.6 Node: Edge92 API emulation, numbered/un-numbered objects and SVG picture OK');
