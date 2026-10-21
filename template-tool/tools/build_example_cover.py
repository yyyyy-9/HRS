"""Create the project-owned generic cover example from the report style template.

No external cover text, images, institutional identity or personal metadata is used.
"""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'


def node(tag, **attrs):
    item = etree.Element('{%s}%s' % (W, tag))
    for key, value in attrs.items():
        item.set('{%s}%s' % (W, key), str(value))
    return item


def paragraph(text='', size=None, centered=False):
    item = node('p')
    properties = node('pPr')
    properties.append(node('pStyle', val='Normal'))
    if centered:
        properties.append(node('jc', val='center'))
    item.append(properties)
    run = node('r')
    if size:
        props = node('rPr'); props.append(node('sz', val=size)); run.append(props)
    value = node('t'); value.text = text; run.append(value); item.append(run)
    return item


def xml(item):
    return etree.tostring(item, xml_declaration=True, encoding='UTF-8', standalone=True)


def build():
    with ZipFile(ROOT / 'templates/target_template.docx') as source:
        files = {name: source.read(name) for name in source.namelist() if not name.endswith('/')}
    document = etree.fromstring(files['word/document.xml'])
    body = document.find('{%s}body' % W)
    sections = body.findall('{%s}sectPr' % W)
    section = sections[-1] if sections else node('sectPr')
    for child in list(body):
        body.remove(child)
    body.extend([paragraph('HRS 通用工程报告', 44, True), paragraph('封面示例', 28, True),
                 paragraph('项目：________________', centered=True),
                 paragraph('编制：________________', centered=True),
                 paragraph('日期：________________', centered=True)])
    page = paragraph(); run = node('r'); run.append(node('br', type='page')); page.append(run); body.append(page)
    body.append(paragraph('目录', 32, True))
    toc = paragraph(); field = node('fldSimple', instr=' TOC \\o "1-6" \\h \\z \\u ')
    run = node('r'); text = node('t'); text.text = '装配报告后在 Word/WPS 中更新目录。'; run.append(text); field.append(run); toc.append(field); body.append(toc)
    page = paragraph(); run = node('r'); run.append(node('br', type='page')); page.append(run); body.append(page)
    slot = paragraph(); slot.append(node('bookmarkStart', id=51000, name='WPS_ReportBody')); slot.append(node('bookmarkEnd', id=51000)); body.append(slot)
    for ref in section.findall('{%s}headerReference' % W):
        section.remove(ref)
    ref = node('headerReference', type='default'); ref.set('{%s}id' % R, 'rIdHrsPublicHeader'); section.insert(0, ref); body.append(section)
    header = node('hdr'); header.append(paragraph('HRS · 通用工程报告示例', 18))
    files['word/header_hrs_public.xml'] = xml(header)
    relations = etree.fromstring(files['word/_rels/document.xml.rels'])
    etree.SubElement(relations, '{%s}Relationship' % P, Id='rIdHrsPublicHeader', Type=R+'/header', Target='header_hrs_public.xml')
    files['word/_rels/document.xml.rels'] = xml(relations)
    content = etree.fromstring(files['[Content_Types].xml'])
    etree.SubElement(content, '{%s}Override' % CT, PartName='/word/header_hrs_public.xml', ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml')
    files['[Content_Types].xml'] = xml(content)
    files['word/document.xml'] = xml(document)
    files['docProps/core.xml'] = b'''<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>HRS generic cover example</dc:title><dc:creator>yyyyy-9</dc:creator><cp:lastModifiedBy>yyyyy-9</cp:lastModifiedBy></cp:coreProperties>'''
    target = ROOT / 'templates/cover_template_v0311.docx'
    with ZipFile(target, 'w', compression=ZIP_DEFLATED, compresslevel=9) as out:
        for name, raw in sorted(files.items()):
            entry = ZipInfo(name, (2026, 10, 21, 0, 0, 0)); entry.compress_type = ZIP_DEFLATED
            out.writestr(entry, raw)
    print(target.name + ': generated project-owned cover / TOC / header / body bookmark')


if __name__ == '__main__':
    build()
