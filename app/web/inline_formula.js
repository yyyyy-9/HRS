/* HF8 PF1: zero-dependency inline TeX insertion helper; Markdown remains plain text. */
(function(root){
'use strict';
const MAX_TEX=2048;
function inlineSnippet(selection='',placeholder='E=mc^2'){
 const raw=String(selection);
 if(/[\r\n]/.test(raw))throw Error('行内公式不能跨行，请使用块级公式 $$...$$');
 if(raw.length>MAX_TEX)throw Error('行内公式超过 2048 字符，请使用块级公式');
 if(!raw.trim())return {markdown:'$'+placeholder+'$',selectionStart:1,selectionEnd:placeholder.length+1};
 if(raw.startsWith('$$')&&raw.endsWith('$$'))throw Error('选中的是块级公式，不能直接作为行内公式');
 if(raw.startsWith('$')&&raw.endsWith('$')&&raw.length>2)return {markdown:raw,selectionStart:1,selectionEnd:raw.length-1};
 return {markdown:'$'+raw+'$',selectionStart:1,selectionEnd:raw.length+1};
}
const api={inlineSnippet,MAX_TEX};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.ReportInlineMath=api;
})(typeof window!=='undefined'?window:globalThis);
