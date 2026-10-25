/* Asset spelling shared by preview, objects and archives. Rules are generated. */
(function(root){
'use strict';
const rules=root.ReportAssetPathRules||(typeof module!=='undefined'&&module.exports?require('./asset_paths_data.js'):null);
const segment=new RegExp(rules.segment_pattern),reserved=new Set(rules.reserved_names);
function normalize(value,{originals=false}={}){
 if(typeof value!=='string')return null;
 if(value.startsWith('./'))value=value.slice(2);
 if(!value.startsWith(rules.prefix))return null;
 const parts=value.slice(rules.prefix.length).split('/');
 if(parts.length>rules.max_directories+1||parts.some(p=>!segment.test(p)||p.endsWith('.')||reserved.has(p.split('.')[0].toUpperCase())))return null;
 const extensions=originals?[...rules.image_extensions,...rules.original_extensions]:rules.image_extensions;
 if(!parts.at(-1).includes('.')||!extensions.includes(parts.at(-1).split('.').at(-1).toLowerCase()))return null;
 return value;
}
const api={normalize};root.ReportAssetPaths=api;
if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
