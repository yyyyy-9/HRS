/* Explicit scroll gestures drive the shared block map. A committed source
 * edit may also reveal its block when the preview is available. */
(function(root){
'use strict';
function attach({sourceScroller,previewScroller,ready,sourceAnchor,previewAnchor,scrollSource,scrollPreview}){
 const driverWindow=900,settleWindow=250;
 let enabled=false,driver=null,until=0,blocked=0,frame=0,scrollIntent=0,previewUntil=0;
 const now=()=>performance.now();
 function suspend(){driver=null;until=0;blocked=now()+settleWindow;if(frame){cancelAnimationFrame(frame);frame=0;}}
 function drive(side,event){
  if(event.type==='keydown'&&!['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key))return;
  driver=side;until=now()+driverWindow;blocked=0;scrollIntent++;
  if(side==='preview')previewUntil=until;
 }
 function follow(side){
  if(!enabled||side!==driver||now()>until||now()<blocked||!ready()||frame)return;
  until=now()+driverWindow;
  if(side==='preview')previewUntil=until;
  frame=requestAnimationFrame(()=>{
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
 return {
  setEnabled(value){enabled=!!value;scrollIntent++;previewUntil=0;suspend();},
  get scrollIntent(){return scrollIntent;},
  followEdit(intent,reveal){
   if(!enabled||intent!==scrollIntent||now()<previewUntil||!ready())return;
   suspend();reveal();
  },
  suspend,destroy(){suspend();disposers.forEach(dispose=>dispose());}
 };
}
const api={attach};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.ScrollFollow=api;
})(typeof window!=='undefined'?window:globalThis);
