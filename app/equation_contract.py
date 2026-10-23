"""Small top-level block-equation syntax shared with web/report_equations.js."""
import re

MARKER=re.compile(r'^ {0,3}<!-- hrs:eq id=(eq-[A-Za-z0-9_-]{1,60}) -->[ \t]*\r?\n')
CLOSE=re.compile(r'(?<!\\)\$\$[ \t]*(?:\r?\n|$)')
BRACKET_CLOSE=re.compile(r'(?<!\\)\\\][ \t]*(?:\r?\n|$)')
# Position-anchored variants: pattern.match(text,pos) anchors at pos without
# copying the remaining document for every candidate equation line.
_MARKER_AT=re.compile(r' {0,3}<!-- hrs:eq id=(eq-[A-Za-z0-9_-]{1,60}) -->[ \t]*\r?\n')
_OPEN_AT=re.compile(r' {0,3}\$\$')
_BRACKET_OPEN_AT=re.compile(r' {0,3}\\\[')

def parse_equation(text, pos=0):
    if pos==0 and text.startswith('\ufeff'):
        result=parse_equation(text,1)
        if result:result['source']='\ufeff'+result['source']
        return result
    meta=_MARKER_AT.match(text,pos);offset=meta.end() if meta else pos
    # Delimiters carry content; an optional marker supplies stable identity.
    # Number visibility belongs exclusively to the document render options.
    opening=_OPEN_AT.match(text,offset)
    bracket=False
    if not opening:
        opening=_BRACKET_OPEN_AT.match(text,offset)
        bracket=bool(opening)
    if not opening:return None
    closing=(BRACKET_CLOSE if bracket else CLOSE).search(text,opening.end())
    if not closing:return None
    tex=text[opening.end():closing.start()]
    if not tex.strip():return None
    return {'source':text[pos:closing.end()],'latex':tex,
            'id':meta[1] if meta else None,
            'delimiter':'bracket' if bracket else 'dollar'}
