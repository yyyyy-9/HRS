/* MERMAID-DRAG-01: position metadata preserves code/CRLF and refuses unknowns. */
'use strict';
const assert=require('assert'),fs=require('fs'),path=require('path'),vm=require('vm');
const context={window:{}};vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/web/diagram.js'),'utf8'),context);
const Flow=context.window.Flow;
const original='flowchart LR\r\n\r\n    A["2.30 V<br/>输入"] -->|yes| B{结果}\r\n';
const placed=Flow.writePositions(original,{A:{x:40,y:80},B:{x:320.4,y:120.7}});
assert.equal(placed.replace(/^[ \t]*%% pos[^\r\n]*(?:\r\n|\n|\r)/gm,''),original);
assert.equal(Flow.parse(placed).positions.B.x,320);
assert.equal(Flow.parse(placed).positions.B.y,121);
assert.equal(Flow.writePositions(placed,{}),original);
assert.equal(Flow.placement(placed).source,original.replace(/[\r\n]+$/,''));
assert.equal(Flow.placement(original).source,Flow.placement(placed).source);
const old='graph TB\n A[开始]-->B[结束]\n %% pos A 25 50\n %% pos B 200 400';
assert.equal(Flow.parse(old).positions.B.y,400);
assert(Flow.serialize(Flow.parse(old)).includes('%% pos B 200 400'));
for(const positions of [{Z:{x:1,y:2}},{A:{x:NaN,y:0}},{A:{x:-1,y:0}},{A:{x:100001,y:0}}]){
 assert.throws(()=>Flow.writePositions(original,positions));
}
const complex='flowchart TB\n subgraph 一组\n A-->B\n end';
assert.equal(Flow.placement(complex).graph,null);
assert.equal(Flow.placement(complex).source,complex);
assert.throws(()=>Flow.writePositions(complex,{A:{x:0,y:0}}));
const special='graph LR\n __proto__[first]-->constructor[last]\n %% pos __proto__ 40 80';
assert.equal(Flow.parse(special).positions.__proto__.x,40);
assert.equal(Object.prototype.x,undefined);
console.log('PASS: source-preserving positions, legacy coordinates, bounds and complex-source refusal');
