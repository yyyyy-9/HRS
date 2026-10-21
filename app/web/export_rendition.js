/* Read-only, browser-side raster renditions for HTML export.
 * The original project assets are never overwritten or re-encoded.
 */
(function(root){
'use strict';
async function imagePixels(blob){
 if(typeof createImageBitmap==='function'){
  const bitmap=await createImageBitmap(blob);
  return {width:bitmap.width,height:bitmap.height,paint:(ctx,w,h)=>{ctx.drawImage(bitmap,0,0,w,h);bitmap.close();}};
 }
 const url=URL.createObjectURL(blob),img=new Image();
 try{
  await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('原图无法解码'));img.src=url;});
  return {width:img.naturalWidth,height:img.naturalHeight,paint:(ctx,w,h)=>ctx.drawImage(img,0,0,w,h)};
 }finally{URL.revokeObjectURL(url);}
}
async function rendition(bytes,name,widthMm,config){
 const helper=root.ReportExportArchive;
 const originalMime=helper.guessMime(name);
 if(!originalMime||!originalMime.startsWith('image/'))throw Error('图片资源类型无效：'+name);
 // SVG is displayed natively. GIF animations are never silently flattened.
 if(config.dpi===null||/\.(?:svg|gif)$/i.test(name))return {bytes,mime:originalMime,modified:false};
 const bitmap=await imagePixels(new Blob([bytes],{type:originalMime}));
 const size=helper.targetSize(bitmap.width,bitmap.height,widthMm,config);
 if(!size.modified)return {bytes,mime:originalMime,modified:false,belowTarget:!!size.belowTarget};
 const canvas=document.createElement('canvas');canvas.width=size.width;canvas.height=size.height;
 const context=canvas.getContext('2d',{alpha:true});if(!context)throw Error('Canvas 不可用，无法生成图片衍生图');
 context.imageSmoothingEnabled=true;context.imageSmoothingQuality='high';
 bitmap.paint(context,size.width,size.height);
 // For engineering line plots use lossless PNG, not lossy WebP by default.
 const outMime=/\.jpe?g$/i.test(name)?'image/jpeg':'image/png';
 const converted=await new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(Error('无法生成导出图片')),outMime,0.92));
 const data=new Uint8Array(await converted.arrayBuffer());
 if(data.byteLength>12*1024*1024)throw Error('导出预览图超出单图大小限制');
 // Resampling a sparse scientific line chart can create thousands of
 // antialiased colors: a smaller image may cost MORE bytes. Prefer the
 // unchanged original if the new rendition isn't actually smaller.
 if(data.byteLength>=bytes.byteLength)
  return {bytes,mime:originalMime,modified:false,largerRenditionSkipped:true,
   belowTarget:!!size.belowTarget,width:bitmap.width,height:bitmap.height};
 return {bytes:data,mime:outMime,modified:true,width:size.width,height:size.height,belowTarget:!!size.belowTarget};
}
root.ReportExportRendition={rendition};
if(typeof module==='object'&&module.exports)module.exports=root.ReportExportRendition;
})(typeof window!=='undefined'?window:globalThis);
