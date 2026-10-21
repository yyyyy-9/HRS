/* Only the side receiving user scroll input drives the shared block map. */
(function(root){
'use strict';
function attach({sourceScroller,previewScroller,ready,sourceAnchor,previewAnchor,scrollSource,scrollPreview}){
 let enabled=false,driver=null,until=0,blocked=0,frame=0;
 const now=()=>performance.now();
 function suspend(){driver=null;until=0;blocked=now()+250;if(frame){cancelAnimationFrame(frame);frame=0;}}
 function drive(side,event){
  if(event.type==='keydown'&&!['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key))return;
  driver=side;until=now()+900;blocked=0;
 }
 function follow(side){
  if(!enabled||side!==driver||now()>until||now()<blocked||!ready()||frame)return;
  until=now()+900;frame=requestAnimationFrame(()=>{
   frame=0;if(!enabled||side!==driver||now()<blocked||!ready())return;
   const anchor=side==='source'?sourceAnchor():previewAnchor();
   if(anchor)(side==='source'?scrollPreview:scrollSource)(anchor);
  });
 }
 const disposers=[];
 for(const [side,scroller] of [['source',sourceScroller],['preview',previewScroller]]){
  for(const type of ['wheel','touchstart','touchmove','pointerdown','keydown']){
   const listener=event=>drive(side,event);scroller.addEventListener(type,listener,{passive:true});disposers.push(()=>scroller.removeEventListener(type,listener));
  }
  const listener=()=>follow(side);scroller.addEventListener('scroll',listener,{passive:true});disposers.push(()=>scroller.removeEventListener('scroll',listener));
 }
 window.addEventListener('resize',suspend);disposers.push(()=>window.removeEventListener('resize',suspend));
 return {setEnabled(value){enabled=!!value;suspend();},suspend,destroy(){suspend();disposers.forEach(dispose=>dispose());}};
}
const api={attach};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.ScrollFollow=api;
})(typeof window!=='undefined'?window:globalThis);
