/* Compact UTF-16 closing changes bound to a server-confirmed recovery snapshot. */
(function(root){
'use strict';
function closeDelta(draft,base){
 if(!draft||!base||typeof draft.markdown!=='string'||typeof base.markdown!=='string'||!/^([a-f0-9]{64})$/.test(base.markdown_sha256||''))return null;
 for(const key of ['draft_id','document_id','template','base_revision'])if(draft[key]!==base[key])return null;
 const old=base.markdown,next=draft.markdown;let from=0,suffix=0;
 while(from<old.length&&from<next.length&&old.charCodeAt(from)===next.charCodeAt(from))from++;
 // Never split surrogate pairs when an emoji changes only its low surrogate.
 if(from&&from<old.length&&old.charCodeAt(from)>=0xdc00&&old.charCodeAt(from)<=0xdfff)from--;
 while(suffix<old.length-from&&suffix<next.length-from&&old.charCodeAt(old.length-1-suffix)===next.charCodeAt(next.length-1-suffix))suffix++;
 const boundary=old.length-suffix;
 if(suffix&&old.charCodeAt(boundary)>=0xdc00&&old.charCodeAt(boundary)<=0xdfff)suffix--;
 const {markdown,...metadata}=draft;
 return {...metadata,base_sha256:base.markdown_sha256,from,to:old.length-suffix,insert:next.slice(from,next.length-suffix)};
}
const api={closeDelta};root.DraftSnapshot=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
