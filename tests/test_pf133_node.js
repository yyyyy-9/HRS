/* PF13.3: bracketed display math and existing $$/numbered equation parity. */
'use strict';
const assert=require('node:assert/strict');
const path=require('node:path');
const ROOT=path.resolve(__dirname,'../app/web');
const equations=require(path.join(ROOT,'report_equations.js'));
const marked=require(path.join(ROOT,'vendor/marked.js'));
const parse=equations.parse;
for(const newline of ['\n','\r\n']){
 const raw=[String.raw`\[`,String.raw`K=\left|\frac{d\beta}{d\lambda}\right|`,String.raw`\]`,''].join(newline);
 const eq=parse(raw);
 assert(eq);assert.equal(eq.raw,raw);assert.equal(eq.delimiter,'bracket');
 assert.equal(eq.numbered,false);assert.equal(eq.id,null);
 assert(eq.tex.includes(String.raw`\frac`));
}
assert.equal(parse('$$\nE=mc^2\n$$\n').delimiter,'dollar');
assert.equal(parse('<!-- hrs:eq id=eq-check -->\n$$\nE=mc^2\n$$\n').id,'eq-check');
assert.equal(parse('<!-- hrs:eq id=eq-check -->\n\\[\nE=mc^2\n\\]'),null);
assert.equal(parse('\\[\nE=mc^2'),null);
assert.equal(parse('\\\\[\\nnot math\\n\\]'),null);
equations.installMarked(marked);
const md=String.raw`# 标题

\[
K=\left|\frac{d\beta}{d\lambda}\right|
\]

$$
E=mc^2
$$

\(T_{11}\)

`+'```text\n\\[\nnot math\n\\]\n```\n';
const tokens=marked.lexer(md);
assert.equal(tokens.filter(t=>t.type==='reportEquation').length,2);
assert.equal(tokens.filter(t=>t.type==='code').length,1);
assert(tokens.filter(t=>t.type==='reportEquation').every(t=>t.raw.includes('\n')));
const raw=md.replaceAll('\n','\r\n');
assert.equal(marked.lexer(raw).filter(t=>t.type==='reportEquation').length,2);
console.log('PF13.3 Node: bracket TeX, CRLF, older math syntax and fence exclusions OK');
