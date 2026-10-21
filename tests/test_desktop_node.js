/* DESKTOP-01: validation works without starting Electron or a Python service. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {verifyFiles,verifyMembership,inside}=require('../desktop/host.cjs');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'hrs-host-contract-'));
 try{
  const raw=Buffer.from('中文\r\n😀');fs.writeFileSync(path.join(root,'sample.txt'),raw);
  const entry={path:'sample.txt',bytes:raw.length,sha256:crypto.createHash('sha256').update(raw).digest('hex')};
  await verifyFiles(root,[entry]);
  await verifyMembership(root,['sample.txt']);
  await assert.rejects(()=>verifyMembership(root,[]));
  await assert.rejects(()=>verifyFiles(root,[{...entry,path:'../outside'}]));
  await assert.rejects(()=>verifyFiles(root,[entry,entry]));
  await assert.rejects(()=>verifyFiles(root,[{...entry,sha256:'0'.repeat(64)}]));
  assert(!inside(root,root));assert(!inside(root,path.dirname(root)));assert(inside(root,path.join(root,'child')));
  console.log('PASS desktop manifest boundaries');
 }finally{fs.rmSync(root,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
