"""Use Pandoc's math converter only; HRS remains the Markdown parser."""
from copy import deepcopy
from io import BytesIO
import json
import re
import subprocess
from zipfile import ZipFile
from lxml import etree as E
from .runtime import BridgeError

M='http://schemas.openxmlformats.org/officeDocument/2006/math'
BATCH_ITEMS=64
BATCH_TEX_CHARS=64*1024
PANDOC_TIMEOUT_SECONDS=30


def normalize_tex_for_pandoc(tex):
    r"""Adapt scoped old roman declarations and escaped math whitespace.

    Only the converter input changes; source/provenance and cache keys retain
    the original TeX. The complete formula is also a bounded math scope.
    Mid-expression declarations remain subject to strict rejection. Escaped
    braces, comments and text arguments are preserved. An escaped line end or
    tab is a TeX control space, not the two-backslash multiline command.
    """
    text_commands={'text','textrm','textnormal','textsf','texttt','textbf',
                   'textit','textsc','mbox','operatorname'}

    def command_end(source, index):
        end=index+1
        if end<len(source) and source[end].isalpha():
            while end<len(source) and source[end].isalpha():end+=1
            return end
        return min(index+2,len(source))

    def group_end(source, index):
        depth=1;index+=1
        while index<len(source):
            char=source[index]
            if char=='\\':index=command_end(source,index);continue
            if char=='%':
                end=source.find('\n',index)
                index=len(source) if end<0 else end+1
                continue
            if char=='{':depth+=1
            elif char=='}':
                depth-=1
                if depth==0:return index
            index+=1
        return None

    def walk(source):
        parts=[];index=0
        while index<len(source):
            char=source[index]
            if char=='%':
                end=source.find('\n',index)
                end=len(source) if end<0 else end+1
                parts.append(source[index:end]);index=end;continue
            if char=='\\':
                end=command_end(source,index);command=source[index+1:end]
                if command in {'\n','\r','\t'}:
                    parts.append('\\ ');index=end;continue
                if command in text_commands:
                    start=end
                    if start<len(source) and source[start]=='*':start+=1
                    while start<len(source) and source[start].isspace():start+=1
                    closing=group_end(source,start) if start<len(source) and source[start]=='{' else None
                    if closing is not None:end=closing+1
                parts.append(source[index:end]);index=end;continue
            if char=='{':
                end=group_end(source,index)
                if end is None:parts.append(source[index:]);break
                inner=source[index+1:end]
                inner=scope(inner)
                parts.append('{'+inner+'}');index=end+1;continue
            parts.append(char);index+=1
        return ''.join(parts)

    def scope(source):
        declaration=re.match(r'(\s*)\\rm(?![A-Za-z])\s*',source)
        if declaration:return declaration.group(1)+r'\mathrm{'+walk(source[declaration.end():])+'}'
        return walk(source)

    return scope(tex)


class MathAdapter:
    def __init__(self,runtime):
        if not runtime.pandoc:raise BridgeError('PANDOC_PATH is required for native TeX/OMML conversion')
        self.exe=runtime.pandoc;self.cache={}
        r=subprocess.run([self.exe,'-f','markdown','-t','json'],input=b'',capture_output=True,check=True,timeout=PANDOC_TIMEOUT_SECONDS)
        self.version=json.loads(r.stdout)['pandoc-api-version']

    def _fill_omml(self,keys,*,speculative=False):
        blocks=[{'t':'Para','c':[{'t':'Math','c':[{'t':'DisplayMath' if display else 'InlineMath'},normalize_tex_for_pandoc(tex)]}]} for tex,display in keys]
        ast={'pandoc-api-version':self.version,'meta':{},'blocks':blocks}
        result=subprocess.run([self.exe,'--fail-if-warnings','-f','json','-t','docx','-o','-'],
                              input=json.dumps(ast).encode('utf8'),capture_output=True,timeout=PANDOC_TIMEOUT_SECONDS)
        if result.returncode:
            # The page model also contains unused definitions. Never make a
            # rejected speculative batch an export error or cache partial output;
            # an expression actually emitted still takes the strict path below.
            if speculative:return
            raise BridgeError('Native math conversion rejected: '+result.stderr.decode('utf8'))
        with ZipFile(BytesIO(result.stdout)) as z:doc=E.fromstring(z.read('word/document.xml'))
        namespaces={'m':M,'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        paragraphs=doc.xpath('/w:document/w:body/w:p',namespaces=namespaces)
        if len(paragraphs)!=len(keys):
            if speculative:return
            raise BridgeError('Native math conversion changed the number of formula paragraphs')
        converted={}
        for key,paragraph in zip(keys,paragraphs):
            nodes=paragraph.xpath('.//m:oMathPara' if key[1] else './/m:oMath',namespaces=namespaces)
            if len(nodes)!=1 or len(paragraph.xpath('.//m:oMath',namespaces=namespaces))!=1:
                if speculative:return
                raise BridgeError('Expected one native OMML expression per formula')
            converted[key]=deepcopy(nodes[0])
        self.cache.update(converted)

    def prefetch(self,expressions):
        """Warm original (TeX, display) keys in bounded, ordered batches.

        A large individual expression stays whole. Rejected batches are not
        retried here; the existing strict on-demand conversion remains decisive.
        """
        pending=[];chars=0;seen=set(self.cache)
        for key in expressions:
            if key in seen:continue
            if pending and (len(pending)>=BATCH_ITEMS or chars+len(key[0])>BATCH_TEX_CHARS):
                self._fill_omml(pending,speculative=True);pending=[];chars=0
            pending.append(key);seen.add(key);chars+=len(key[0])
        if pending:self._fill_omml(pending,speculative=True)

    def omml(self,tex,display=False):
        key=(tex,display)
        if key not in self.cache:self._fill_omml([key])
        return deepcopy(self.cache[key])

    def tex(self,omml):
        return self.tex_many([omml])[0]

    @staticmethod
    def math_values(result, count):
        if result.returncode:raise BridgeError('Math conversion rejected: '+result.stderr.decode('utf8'))
        found=[]
        def walk(n):
            if isinstance(n,dict):
                if n.get('t')=='Math':found.append(n['c'][1])
                for v in n.values():walk(v)
            elif isinstance(n,list):
                for v in n:walk(v)
        walk(json.loads(result.stdout))
        if len(found)!=count or any(not text.strip() for text in found):raise BridgeError('Math conversion changed the number of formulas')
        return found

    def tex_many(self,expressions):
        # One bounded conversion for the paste, with one paragraph per formula.
        from docx import Document
        doc=Document()
        for omml in expressions:doc.add_paragraph()._p.append(deepcopy(omml))
        data=BytesIO();doc.save(data)
        result=subprocess.run([self.exe,'--fail-if-warnings','-f','docx','-t','json'],input=data.getvalue(),capture_output=True,timeout=PANDOC_TIMEOUT_SECONDS)
        return self.math_values(result,len(expressions))

    def mathml_many(self,expressions):
        body='<!doctype html><html><body>'+''.join('<p>'+x+'</p>' for x in expressions)+'</body></html>'
        result=subprocess.run([self.exe,'--fail-if-warnings','-f','html','-t','json'],input=body.encode('utf8'),capture_output=True,timeout=PANDOC_TIMEOUT_SECONDS)
        return self.math_values(result,len(expressions))
