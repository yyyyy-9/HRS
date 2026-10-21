const __hrsVarMap={'#eef3ff':'--hrs-diagram-bg','#e6f5ed':'--hrs-diagram-alt','#75ad98':'--hrs-diagram-accent','#334664':'--hrs-diagram-ink','#91a8dd':'--hrs-diagram-line','#91a0b9':'--hrs-diagram-muted','#8494b3':'--hrs-diagram-note','#64718c':'--hrs-diagram-strong','#a897d9':'--hrs-diagram-special','#f4efff':'--hrs-diagram-soft'};
function __hrsThemeSvg(svg){try{const cs=getComputedStyle(document.documentElement);for(const [hex,name] of Object.entries(__hrsVarMap)){const v=cs.getPropertyValue(name).trim();if(v)svg=svg.split(hex).join(v);}}catch(e){}return svg;}
/* Local-only, intentionally limited Mermaid flowchart parser/editor.
 * Supported: graph/flowchart LR|RL|TD|TB|BT, rect/round/diamond nodes,
 * --> and -.-> edges, optional |edge labels|, standalone node declarations,
 * %% pos ID X Y positioning comments. Unsupported syntax fails visibly.
 */
(function(){
'use strict';
const escape = s => String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ID_RE=/^[A-Za-z_][A-Za-z_0-9]*$/;
function parseNode(text, graph) {
  const s=text.trim();
  const m=s.match(/^([A-Za-z_][A-Za-z_0-9]*)(?:\[([^\]]*)\]|\{([^}]*)\}|\(([^)]*)\))?$/);
  if(!m)throw Error(`不支持的节点写法：${s}`);
  const id=m[1], shape=m[3]!=null?'decision':m[4]!=null?'round':'box';
  let label=(m[2]??m[3]??m[4]??id).replace(/^"(.*)"$/,'$1');
  label=label.replace(/<br\s*\/?\s*>/gi,'\n');
  if(/[<>]/.test(label)) throw Error('节点文字编辑只支持 <br/> 换行；其他语法请直接修改 Mermaid 源码');
  if(!graph.nodes.some(n=>n.id===id)) graph.nodes.push({id,label,shape,x:null,y:null});
  else if(m[2]!=null||m[3]!=null||m[4]!=null)Object.assign(graph.nodes.find(n=>n.id===id),{label,shape});
  return id;
}
function parse(code) {
  const lines=code.replace(/\r\n/g,'\n').split('\n').map(x=>x.trim()).filter(Boolean);
  const m=(lines.shift()||'').match(/^(?:flowchart|graph)\s+(LR|RL|TD|TB|BT)\s*$/i);
  if(!m)throw Error('本版图形编辑仅支持 flowchart LR/TD 等基本流程图；其他 Mermaid 保留源码');
  const g={direction:m[1].toUpperCase(),nodes:[],edges:[],positions:{}};
  for (const line of lines){
    if(line.startsWith('%%')){
      const p=line.match(/^%%\s*pos\s+([A-Za-z_]\w*)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*$/);
      if(p)g.positions[p[1]]={x:Math.max(10,Math.min(4000,+p[2])),y:Math.max(10,Math.min(4000,+p[3]))};
      else throw Error('暂不支持该 Mermaid 注释；请在源码模式编辑，以免丢失注释');
      continue;
    }
    const edge=line.match(/^(.*?)\s*(-->|-\.->)\s*(?:\|([^|]*)\|\s*)?(.*?)$/);
    if(edge){
      const from=parseNode(edge[1],g),to=parseNode(edge[4],g);
      if(g.edges.length>99)throw Error('当前最多支持 100 条连线');
      g.edges.push({from,to,label:edge[3]||'',dashed:edge[2]==='-.->'});
    }else if(/^[A-Za-z_]\w*(?:\[.*\]|\{.*\}|\(.*\))?$/.test(line))parseNode(line,g);
    else throw Error('暂未支持的 Mermaid 语法：'+line.slice(0,50));
    if(g.nodes.length>90) throw Error('当前最多支持 90 个节点');
  }
  layout(g);
  return g;
}
function layout(g){
  const directions=['TD','TB','BT'];const vertical=directions.includes(g.direction);
  const r={};for(const n of g.nodes)r[n.id]=0;
  // Ignore back edges for layout ranking; Mermaid feedback loops must not grow
  // to an enormous coordinate range by repeatedly incrementing cycle ranks.
  const order=Object.fromEntries(g.nodes.map((n,i)=>[n.id,i]));
  for(let iter=0;iter<Math.min(g.nodes.length,12);iter++){
    let changed=false;
    for(const e of g.edges){
      if(e.from===e.to || order[e.to]<=order[e.from])continue;
      const v=Math.min(g.nodes.length,r[e.from]+1);
      if(r[e.to]<v){r[e.to]=v;changed=true;}
    }
    if(!changed)break;
  }
  const levels={};
  for (const n of g.nodes){
    if(!levels[r[n.id]])levels[r[n.id]]=[];
    levels[r[n.id]].push(n);
  }
  for (const [rank,list] of Object.entries(levels)){
    list.forEach((n,i)=>{
      const col=Number(rank),rev=g.direction==='RL'||g.direction==='BT';
      const primary=rev?(Math.max(0,10-col))*180:col*185;
      const secondary=i*104;
      const original=g.positions[n.id];
      n.x=original?original.x:45+(vertical?secondary:primary);
      n.y=original?original.y:45+(vertical?primary:secondary);
    });
  }
  return g;
}
function nodeLines(text){
  const words=Array.from(String(text));const lines=[];let segment='',width=0;
  for(const ch of words){const w=/[\u2e80-\uffff]/.test(ch)?1.8:1;
    if(width+w>19&&segment){lines.push(segment);segment='';width=0;}
    segment+=ch;width+=w;
  }
  if(segment)lines.push(segment);
  return lines.slice(0,3).length?lines.slice(0,3):[''];
}
function svg(g,opts={}){
  layout(g);
  const W=160,H=68,pad=42, id='flow_'+Math.random().toString(36).slice(2,9);
  const maxX=Math.max(420,...g.nodes.map(n=>n.x+W+pad)),maxY=Math.max(190,...g.nodes.map(n=>n.y+H+pad));
  let result=`<svg xmlns="http://www.w3.org/2000/svg" width="${maxX}" height="${maxY}" viewBox="0 0 ${maxX} ${maxY}" role="img" aria-label="流程图"><defs><marker id="${id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#8494b3"/></marker></defs>`;
  const nodeMap=Object.fromEntries(g.nodes.map(n=>[n.id,n]));
  for(const edge of g.edges){
    const a=nodeMap[edge.from],b=nodeMap[edge.to];if(!a||!b)continue;
    const horizontal=!['TD','TB','BT'].includes(g.direction);
    const right=b.x>a.x,down=b.y>a.y;
    let ax,ay,bx,by,path;
    if(horizontal&&Math.abs(b.x-a.x)>110){ax=a.x+(right?W:0);ay=a.y+H/2;bx=b.x+(right?0:W);by=b.y+H/2;const delta=Math.max(28,Math.abs(bx-ax)/2);path=`M ${ax} ${ay} C ${ax+(right?delta:-delta)} ${ay} ${bx-(right?delta:-delta)} ${by} ${bx} ${by}`;}
    else{ax=a.x+W/2;ay=a.y+(down?H:0);bx=b.x+W/2;by=b.y+(down?0:H);const delta=Math.max(23,Math.abs(by-ay)/2);path=`M ${ax} ${ay} C ${ax} ${ay+(down?delta:-delta)} ${bx} ${by-(down?delta:-delta)} ${bx} ${by}`;}
    const dash=edge.dashed?' stroke-dasharray="6 5"':'';
    result+=`<path d="${path}" fill="none" stroke="#91a0b9" stroke-width="1.8"${dash} marker-end="url(#${id})"/>`;
    if(edge.label){const lx=(ax+bx)/2,ly=(ay+by)/2-9;result+=`<rect x="${lx-34}" y="${ly-13}" width="68" height="20" rx="5" fill="#fff"/><text x="${lx}" y="${ly+1}" text-anchor="middle" fill="#64718c" font-size="11">${escape(edge.label)}</text>`;}
  }
  for(const n of g.nodes){
    const selected=n.id===opts.selectedId?' selected':'';
    const lines=nodeLines(n.label),lineH=17;
    result+=`<g class="flow-node${selected}" data-node="${escape(n.id)}" transform="translate(${n.x} ${n.y})">`;
    if(n.shape==='decision')result+=`<polygon points="80,0 160,34 80,68 0,34" fill="#f4efff" stroke="#a897d9" stroke-width="1.7"/>`;
    else result+=`<rect width="160" height="68" rx="${n.shape==='round'?34:10}" fill="${n.shape==='round'?'#e6f5ed':'#eef3ff'}" stroke="${n.shape==='round'?'#75ad98':'#91a8dd'}" stroke-width="1.7"/>`;
    const height=lines.length*lineH,start=34-height/2+13;
    lines.forEach((line,i)=>result+=`<text x="80" y="${start+i*lineH}" font-size="13" fill="#334664" text-anchor="middle" font-family="Segoe UI,Microsoft Yahei,sans-serif">${escape(line)}</text>`);
    result+='</g>';
  }
  return __hrsThemeSvg(result+'</svg>');
}
function formatNode(n){
  const safe=String(n.label),closing=n.shape==='decision'?'}':n.shape==='round'?')':']';
  if(/[<>]/.test(safe)||safe.includes(closing))throw Error('该节点形状暂不支持此文字中的 HTML 或闭合括号；源码仍可直接编辑');
  const text=safe.replace(/\r\n?|\n/g,'<br/>');
  if(n.shape==='decision')return `${n.id}{${text}}`;
  if(n.shape==='round')return `${n.id}(${text})`;
  return `${n.id}[${text}]`;
}
function serialize(g,options={}){
  const lines=['flowchart '+g.direction];
  for(const n of g.nodes)lines.push('    '+formatNode(n));
  for(const e of g.edges){if(/[|\r\n]/.test(e.label))throw Error('连线文字暂不支持竖线或换行');lines.push('    '+e.from+' '+(e.dashed?'-.->':'-->')+(e.label?'|'+e.label+'|':'')+' '+e.to);}
  if(options.positions!==false)for(const n of g.nodes) lines.push(`    %% pos ${n.id} ${Math.round(n.x)} ${Math.round(n.y)}`);
  return lines.join('\n');
}
window.Flow={parse,svg,serialize,layout,ID_RE};
})();
