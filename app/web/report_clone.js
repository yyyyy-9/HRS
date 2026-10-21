/* JSON-only deep copy for engineering report models; works in older Edge/WebView.
 * Do not polyfill window.structuredClone: this is intentionally limited to JSON data.
 */
(function(root){
'use strict';
function clone(value){
 // Report tables, figures, and modal state contain plain JSON data only.
 // Preserve undefined in selection state; JSON objects/arrays are copied by value.
 return value===undefined ? undefined : JSON.parse(JSON.stringify(value));
}
const api={clone};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.ReportClone=api;
})(typeof window!=='undefined'?window:globalThis);
