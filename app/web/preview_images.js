/* Small intrinsic-size cache and viewport anchors; never decode a whole report. */
(function(root){
'use strict';
function dimensions(image,info){if(info?.width&&info?.height){image.width=info.width;image.height=info.height;}}
function attach({preview,scroller,capture,restore}){
 const sizes=new Map();let anchor=null,frame=0;
 const key=image=>{const url=new URL(image.src,location.href);url.searchParams.delete('draft_id');return url.href;};
 const remember=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{anchor=capture();});};
 scroller.addEventListener('scroll',remember,{passive:true});root.addEventListener('resize',remember);
 preview.addEventListener('load',event=>{
  const image=event.target;if(image.tagName!=='IMG'||!image.naturalWidth)return;
  sizes.set(key(image),[image.naturalWidth,image.naturalHeight]);if(sizes.size>512)sizes.delete(sizes.keys().next().value);
  if(!image._hrsExplicitDimensions)dimensions(image,{width:image.naturalWidth,height:image.naturalHeight});image.classList.remove('hrs-image-pending');
  if(!image._hrsSourceClassPresent&&!image.getAttribute('class'))image.removeAttribute('class');
  if(anchor)restore(anchor);remember();
 },true);
 function prepare(article){for(const image of article.querySelectorAll('img')){
  image.loading='lazy';image.decoding='async';
  image._hrsExplicitDimensions=image.hasAttribute('width')||image.hasAttribute('height');
  image._hrsSourceClassPresent=image.hasAttribute('class');
  const size=sizes.get(key(image));
  if(!image._hrsExplicitDimensions){if(size)dimensions(image,{width:size[0],height:size[1]});else image.classList.add('hrs-image-pending');}
 }}
 return {prepare,committed:()=>{anchor=capture();},clear:()=>{sizes.clear();anchor=null;}};
}
root.ReportPreviewImages={attach,dimensions};
})(window);
