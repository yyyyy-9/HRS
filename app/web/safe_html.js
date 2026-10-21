/* PF13.8: one inert, allowlisted HTML display boundary for Markdown viewers.
 * Creates fresh HTML nodes. Never adopts source nodes, executes scripts, keeps
 * arbitrary classes/IDs, or creates HRS objects. Source Markdown stays untouched.
 */
(function(root){
'use strict';
const TAGS=new Set(('a abbr b blockquote br caption code col colgroup dd del details div dl dt em figcaption figure h1 h2 h3 h4 h5 h6 hr i img input kbd li mark ol p pre s samp small span strong sub summary sup table tbody td tfoot th thead tr u ul').split(' '));
const INLINE=new Set('a abbr b br code del em i kbd mark s samp small span strong sub sup u'.split(' '));
const DROP=new Set('script style iframe object embed applet base link meta form textarea select option button svg math template noscript head title frameset frame'.split(' '));
const STYLES=new Set(('color background-color font-size font-weight font-style font-family line-height letter-spacing word-spacing text-align text-decoration text-decoration-line text-decoration-color text-indent white-space vertical-align display flex flex-grow flex-shrink flex-basis flex-wrap flex-direction justify-content align-items align-content align-self gap row-gap column-gap width min-width max-width height min-height max-height margin margin-top margin-right margin-bottom margin-left padding padding-top padding-right padding-bottom padding-left border border-top border-right border-bottom border-left border-width border-style border-color border-radius border-collapse border-spacing table-layout').split(' '));
const LIST_STYLES=new Set('bullet decimal lower-alpha paren-decimal paren-lower-alpha'.split(' '));
// Browser CSS parsing expands border shorthands into these longhand names.
for(const side of ['top','right','bottom','left'])for(const part of ['width','style','color'])STYLES.add('border-'+side+'-'+part);
for(const corner of ['top-left','top-right','bottom-left','bottom-right'])STYLES.add('border-'+corner+'-radius');
function assetPath(value){return typeof value==='string'&&/^assets\/[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.(?:png|jpe?g|gif|webp|svg)$/i.test(value)?value:null;}
function safeLink(value){
 if(typeof value!=='string'||/[\x00-\x20\x7f-\x9f]/.test(value))return null;
 if(value.startsWith('#'))return value;
 if(/^https?:\/\//i.test(value)||/^mailto:/i.test(value))return value;
 if(value.startsWith('/')&&!value.startsWith('//')&&!value.includes('\\'))return value;
 return null;
}
function copyStyle(source,target){
 const parsed=document.createElement('span').style;parsed.cssText=source;
 for(const name of parsed){
  const value=parsed.getPropertyValue(name);
  // CSS is parsed first, then confined to properties with no fetch/positioning
  // capability. Escapes, URL-bearing values, variables and !important are denied.
  if(!STYLES.has(name)||parsed.getPropertyPriority(name)||/[\\@<>]/.test(value)||
     /(?:url|expression|var|env|attr|image-set|paint)\s*\(/i.test(value))continue;
  target.style.setProperty(name,value);
 }
}
function fragment(html,options={}){
 const template=document.createElement('template');template.innerHTML=String(html);
 let visited=0;
 function copy(node,depth){
  if(++visited>50000||depth>64)throw Error('HTML 内容超过安全显示深度或节点上限');
  if(node.nodeType===3)return document.createTextNode(node.nodeValue);
  if(node.nodeType!==1)return document.createDocumentFragment();
  const tag=node.localName.toLowerCase();
  if(node.namespaceURI!=='http://www.w3.org/1999/xhtml'||DROP.has(tag))return document.createDocumentFragment();
  const allowed=TAGS.has(tag)&&(!options.inlineOnly||INLINE.has(tag));
  if(!allowed){const part=document.createDocumentFragment();for(const child of node.childNodes)part.append(copy(child,depth+1));return part;}
  if(tag==='input'&&(node.getAttribute('type')?.toLowerCase()!=='checkbox'||!node.hasAttribute('disabled')))return document.createDocumentFragment();
  const out=document.createElement(tag);
  for(const name of ['title','lang','dir'])if(node.hasAttribute(name)){
   const value=node.getAttribute(name);
   if(name!=='dir'||/^(ltr|rtl|auto)$/.test(value))out.setAttribute(name,value);
  }
  if(node.hasAttribute('style'))copyStyle(node.getAttribute('style'),out);
  if(tag==='img'){
   if(options.images===false)return document.createDocumentFragment();
   const source=node.getAttribute('src')||'';
   const url=options.imageURL?options.imageURL(source):assetPath(source);
   if(!url){const warning=document.createElement('span');warning.textContent='图片路径不安全或不支持：'+(node.getAttribute('alt')||source);return warning;}
   out.setAttribute('src',url);out.setAttribute('alt',node.getAttribute('alt')||'图片');out.loading='lazy';
   for(const name of ['width','height'])if(/^[1-9][0-9]{0,3}$/.test(node.getAttribute(name)||''))out.setAttribute(name,node.getAttribute(name));
  }
  if(tag==='a'){
   const href=node.getAttribute('href')||'';
   const attrs=options.linkAttrs?options.linkAttrs(href):{href:safeLink(href)};
   if(attrs?.href)out.setAttribute('href',attrs.href);
   if(attrs?.packDoc)out.dataset.packDoc=attrs.packDoc; // only first-party path resolution can set this
   if(attrs?.className)out.className=attrs.className;
   if(attrs?.target==='_blank'||node.getAttribute('target')==='_blank')out.target='_blank';
   out.rel='noopener noreferrer';
   const note=node.getAttribute('data-hrs-footnote-ref');
   if(note&&/^[A-Za-z0-9_\u4e00-\u9fff-]{1,80}$/.test(note))out.dataset.hrsFootnoteRef=note;
  }
  if(tag==='td'||tag==='th')for(const name of ['rowspan','colspan'])if(/^[1-9][0-9]{0,2}$/.test(node.getAttribute(name)||''))out.setAttribute(name,node.getAttribute(name));
  if(tag==='td'||tag==='th'){
   const align=(node.getAttribute('align')||'').toLowerCase();
   if(!out.style.textAlign&&['left','center','right','justify'].includes(align))out.style.textAlign=align;
  }
  if(tag==='col'&&/^[1-9][0-9]{0,2}$/.test(node.getAttribute('span')||''))out.setAttribute('span',node.getAttribute('span'));
  if(tag==='ol'&&/^[0-9]{1,9}$/.test(node.getAttribute('start')||''))out.setAttribute('start',node.getAttribute('start'));
  if(tag==='details'&&node.hasAttribute('open'))out.setAttribute('open','');
  if(tag==='input'){out.type='checkbox';out.disabled=true;if(node.hasAttribute('checked'))out.setAttribute('checked','');}
  // Tightly bounded presentation classes are generated by the
  // existing Markdown extensions, not formal object or editor-control metadata.
  const list=node.getAttribute('data-hrs-list-style');
  if(tag==='div'&&LIST_STYLES.has(list)){out.className='hrs-list-scope hrs-list-'+list;out.dataset.hrsListStyle=list;}
  if(tag==='code'&&/^language-[A-Za-z0-9_+-]{1,60}$/.test(node.className))out.className=node.className;
  if(['span','mark'].includes(tag)&&node.getAttribute('data-hrs-highlight')==='markdown')out.dataset.hrsHighlight='markdown';
  if(tag==='span'&&['warning-pill','reader-warning','reader-unresolved'].includes(node.className))out.className=node.className;
  for(const child of node.childNodes)out.append(copy(child,depth+1));
  if(tag==='li'){
   const first=out.firstElementChild,marker=first?.localName==='p'?first.firstElementChild:first;
   if(marker?.localName==='input'&&marker.type==='checkbox')out.classList.add('hrs-task-item');
  }
  if(/^h[1-6]$/.test(tag)&&options.headingID)out.id=options.headingID(out.textContent);
  return out;
 }
 const result=document.createDocumentFragment();
 for(const node of template.content.childNodes)result.append(copy(node,0));
 return result;
}
function hasHTML(token){
 if(!token||typeof token!=='object')return false;
 if(token.type==='html')return true;
 return [...(token.tokens||[]),...(token.items||[])].some(hasHTML);
}
const api={fragment,assetPath,safeLink,hasHTML};
root.ReportSafeHTML=api;
if(typeof module==='object'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
