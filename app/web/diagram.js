/* Local-only, intentionally limited Mermaid flowchart parser/editor.
 * Supported: graph/flowchart LR|RL|TD|TB|BT, rect/round/diamond nodes,
 * --> and -.-> edges, optional |edge labels|, standalone node declarations,
 * %% pos ID X Y positioning comments. Unsupported syntax fails visibly.
 */
(function(){
'use strict';
const ID_RE=/^[A-Za-z_][A-Za-z_0-9]*$/;
function parseNode(text, graph) {
  const s=text.trim();
  const m=s.match(/^([A-Za-z_][A-Za-z_0-9]*)(?:\[([^\]]*)\]|\{([^}]*)\}|\(([^)]*)\))?$/);
  if(!m)throw Error(`不支持的节点写法：${s}`);
  const id=m[1], shape=m[3]!=null?'decision':m[4]!=null?'round':'box';
  let label=(m[2]??m[3]??m[4]??id).replace(/^"(.*)"$/,'$1');
  label=label.replace(/<br\s*\/?\s*>/gi,'\n');
  if(/[<>]/.test(label)) throw Error('节点文字编辑只支持 <br/> 换行；其他语法请直接修改 Mermaid 源码');
  if(!graph.nodes.some(n=>n.id===id)) graph.nodes.push({id,label,shape});
  else if(m[2]!=null||m[3]!=null||m[4]!=null)Object.assign(graph.nodes.find(n=>n.id===id),{label,shape});
  return id;
}
function parse(code) {
  const lines=code.replace(/\r\n/g,'\n').split('\n').map(x=>x.trim()).filter(Boolean);
  const m=(lines.shift()||'').match(/^(?:flowchart|graph)\s+(LR|RL|TD|TB|BT)\s*$/i);
  if(!m)throw Error('本版图形编辑仅支持 flowchart LR/TD 等基本流程图；其他 Mermaid 保留源码');
  const g={direction:m[1].toUpperCase(),nodes:[],edges:[],positions:Object.create(null)};
  for (const line of lines){
    if(line.startsWith('%%')){
      const p=line.match(/^%%\s*pos\s+([A-Za-z_]\w*)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*$/);
      if(p)g.positions[p[1]]={x:Math.max(0,Math.min(100000,+p[2])),y:Math.max(0,Math.min(100000,+p[3]))};
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
  return g;
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
  if(options.positions!==false)for(const n of g.nodes){const p=g.positions[n.id];if(p)lines.push(`    %% pos ${n.id} ${Math.round(p.x)} ${Math.round(p.y)}`);}
  return lines.join('\n');
}
function positionLines(source,positions){
 const newline=source.match(/\r\n|\r|\n/)?.[0]||'\n';
 const base=source.replace(/^[ \t]*%%[ \t]+pos[ \t]+([A-Za-z_]\w*)[ \t]+-?\d+(?:\.\d+)?[ \t]+-?\d+(?:\.\d+)?[ \t]*(?:\r\n|\r|\n|$)/gm,'');
 const lines=Object.entries(positions).map(([id,p])=>{
  if(!ID_RE.test(id)||!Number.isFinite(p.x+p.y)||p.x<0||p.y<0||p.x>100000||p.y>100000)throw Error('流程图位置无效');
  return '    %% pos '+id+' '+Math.round(p.x)+' '+Math.round(p.y);
 });
 if(!lines.length)return base;
 // Insert metadata after the header. Removing it then restores the exact
 // original code and line endings, without adding a trailing blank line.
 const header=base.match(/^[ \t]*(?:flowchart|graph)[ \t]+(?:LR|RL|TD|TB|BT)[ \t]*(?:\r\n|\r|\n)/mi);
 if(!header)throw Error('无法定位流程图方向行');
 const offset=header.index+header[0].length;
 return base.slice(0,offset)+lines.join(newline)+newline+base.slice(offset);
}
function writePositions(source,positions){
 const graph=parse(source),ids=new Set(graph.nodes.map(n=>n.id));
 if(Object.keys(positions).some(id=>!ids.has(id)))throw Error('流程图位置对应的节点已变化');
 const next=positionLines(source,positions);if(next.length>50000)throw Error('排版后的流程图源码超过50000字符');
 return next;
}
function placement(source){
 try{const graph=parse(source);return {graph,source:positionLines(source,{}).replace(/[\r\n]+$/,'')};}
 catch{return {graph:null,source};}
}
window.Flow={parse,serialize,writePositions,placement,ID_RE};
})();
