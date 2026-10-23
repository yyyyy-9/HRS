"""Mathematics in the same native clipboard snapshot as HTML/text/images."""
from io import BytesIO
import posixpath
import re
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as E
from legacy_math import ole_to_tex

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M='http://schemas.openxmlformats.org/officeDocument/2006/math'
O='urn:schemas-microsoft-com:office:office'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
LABEL=re.compile(r'^\s*[（(]\s*\d+(?:[.\-]\d+)*\s*[)）]\s*$')


def xml(data):
    if len(data)>4*1024*1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('公式 XML 无效或超过限制')
    try:return E.fromstring(data)
    except E.ParseError as error:raise ValueError('公式 XML 不完整') from error


def native_formulas(blob,sources,expected_text,convert):
    """Bind native visual positions to exactly the HTML snapshot's images.

    Anonymous source formulas receive identity only in the original HRS paste
    transaction. Numbers beside a standalone formula are outside its math tree.
    """
    if not blob:return {}
    if len(blob)>30*1024*1024:raise ValueError('原生剪贴板文档超过限制')
    try:
        with ZipFile(BytesIO(blob)) as z:
            members=z.infolist()
            if len(members)>1000 or len({m.filename.casefold() for m in members})!=len(members) or sum(m.file_size for m in members)>64*1024*1024:
                raise ValueError('原生剪贴板文档成员无效或超过限制')
            root=xml(z.read('word/document.xml'))
            normalize=lambda text:re.sub(r'[\s\x07\ufffc]+','',text)
            text=''.join(n.text or '' for n in root.iter() if n.tag in ('{'+W+'}t','{'+M+'}t'))
            if normalize(text)!=normalize(expected_text):raise ValueError('原生公式片段与本次复制文字不一致；整段未插入')
            parents={child:parent for parent in root.iter() for child in parent}
            relations={}
            if 'word/_rels/document.xml.rels' in z.namelist():
                relations={r.get('Id'):r for r in xml(z.read('word/_rels/document.xml.rels'))}
            visuals=[]
            def walk(node):
                if node.tag in ('{'+M+'}oMath','{'+M+'}oMathPara'):
                    visuals.append(('omml',node));return
                if node.tag=='{'+W+'}object':
                    ole=node.find('.//{'+O+'}OLEObject')
                    if ole is not None and ole.get('ProgID','').lower().startswith(('equation.','mathtype.')):
                        visuals.append(('ole',node));return
                    raise ValueError('剪贴板包含尚不支持的嵌入对象，整段未插入')
                if node.tag in ('{'+W+'}drawing','{'+W+'}pict'):
                    visuals.append(('image',node));return
                for child in node:walk(child)
            walk(root)
            if not any(kind!='image' for kind,_ in visuals):return {}
            if len(visuals)!=len(sources):raise ValueError('公式、图片与本次 HTML 位置无法一一对应；整段未插入')
            result={};requests=[];pending=[]
            for (kind,node),url in zip(visuals,sources):
                if kind=='image':continue
                p=node
                while p in parents and p.tag!='{'+W+'}p':p=parents[p]
                prose=''.join(t.text or '' for t in p.iter('{'+W+'}t')).strip()
                display=not prose or bool(LABEL.fullmatch(prose)) or node.tag=='{'+M+'}oMathPara'
                item={'display':display,'source_number':prose if display and LABEL.fullmatch(prose) else ''}
                if kind=='ole':
                    ole=node.find('.//{'+O+'}OLEObject');rel=relations.get(ole.get('{'+R+'}id'))
                    if rel is None or rel.get('TargetMode')=='External':raise ValueError('旧公式没有内嵌数学数据')
                    target=posixpath.normpath(posixpath.join('word',rel.get('Target','')))
                    if not target.startswith('word/embeddings/') or '\\' in target:raise ValueError('旧公式资源关系无效')
                    item['tex']=ole_to_tex(z.read(target))
                else:
                    requests.append({'format':'omml','source':E.tostring(node,encoding='unicode')});pending.append(item)
                if url in result:raise ValueError('多个公式共用同一 HTML 图像地址，无法确定内容；整段未插入')
                result[url]=item
            if requests:
                if convert is None:raise ValueError('粘贴原生公式需要选择已有 Pandoc（导出 Word → 公式支持）')
                values=convert(requests)
                if len(values)!=len(pending):raise ValueError('公式转换数量不一致；整段未插入')
                for item,tex in zip(pending,values):item['tex']=tex
            return result
    except (BadZipFile,KeyError) as error:raise ValueError('原生剪贴板文档或公式资源不完整') from error
