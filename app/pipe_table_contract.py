"""Read-only GFM pipe table recognizer for engineering-report-ir-v1.

Shares the same conservative source semantics as web/pipe_tables.js:
no migration of Markdown, no invented stable id, no HTML execution. A full
Markdown parser is still required for the eventual Word inline-style AST.
"""
import re

DELIMITER=re.compile(r'^:?-{3,}:?$')
CAPTION=re.compile(r'^ {0,3}:[ \t]+([^\r\n]*?)(?:[ \t]+\{#(tbl-[A-Za-z0-9_-]{1,60})\})?[ \t]*$')
MAX_ROWS,MAX_COLS=100,30


def split_cells(value):
    """Split a GFM row. Escape parity is identical to web/pipe_tables.js.

    Odd runs before | escape the pipe; even runs leave it a separator.
    Backslash pairs immediately before a pipe decode to literal slashes.
    Backticks protect pipes from being treated as cell boundaries.
    """
    text=value.rstrip('\r\n').strip()
    if text.startswith('|'):text=text[1:]
    if text.endswith('|'):
        backslashes=len(text[:-1])-len(text[:-1].rstrip('\\'))
        if backslashes%2==0:text=text[:-1]
    cells=[];buffer=[];fence=0;i=0
    while i<len(text):
        ch=text[i]
        if ch=='\\':
            j=i+1
            while j<len(text) and text[j]=='\\':j+=1
            n=j-i
            if j<len(text) and text[j]=='|' and not fence:
                buffer.append('\\'*(n//2))
                if n%2:buffer.append('|');i=j+1;continue
                i=j;continue
            buffer.append('\\'*n);i=j;continue
        if ch=='`':
            n=1
            while i+n<len(text) and text[i+n]=='`':n+=1
            if fence==0:fence=n
            elif fence==n:fence=0
            buffer.append(text[i:i+n]);i+=n;continue
        if ch=='|' and not fence:cells.append(''.join(buffer).strip());buffer=[]
        else:buffer.append(ch)
        i+=1
    cells.append(''.join(buffer).strip())
    return cells


def parse_at(lines,index):
    """Return the table block at index or None. Adjacent caption is preferred.

    A standalone pipe table is treated as ordinary body structure even without
    a Quarto caption. An ID is only registered if explicitly authored.
    """
    if index+1>=len(lines):return None
    first=lines[index].rstrip('\r\n');second=lines[index+1].rstrip('\r\n')
    if index==0:first=first.lstrip('\ufeff')
    if not ('|' in first or '|' in second):return None
    header=split_cells(first);delimiter=split_cells(second)
    if not (1<=len(header)<=MAX_COLS and len(header)==len(delimiter) and
            all(DELIMITER.fullmatch(cell) for cell in delimiter)):
        return None
    align=['center' if v.startswith(':') and v.endswith(':') else 'right' if v.endswith(':') else 'left' if v.startswith(':') else None for v in delimiter]
    rows=[header];end=index+2
    while end<len(lines):
        line=lines[end].rstrip('\r\n')
        if not line.strip():break
        if CAPTION.fullmatch(line):break
        if '|' not in line:break  # adjacent prose is not another table row
        cells=split_cells(line)
        # GFM pads short data rows and ignores excess data cells for display.
        if len(cells)<len(header):cells.extend(['']*(len(header)-len(cells)))
        cells=cells[:len(header)]
        if len(rows)>=MAX_ROWS:raise ValueError('Markdown 管道表格不能超过 100 行（含表头）')
        if any(len(c)>30000 for c in cells):raise ValueError('Markdown 管道表格单格内容过长')
        rows.append(cells);end+=1
    caption='';stable_id=None
    # Adjacent caption is the canonical authoring form. One empty line is
    # accepted strictly for older documents; two blanks are not associated.
    cap_idx=end
    if cap_idx<len(lines) and not lines[cap_idx].strip():cap_idx+=1
    if cap_idx<len(lines):
        hit=CAPTION.fullmatch(lines[cap_idx].rstrip('\r\n'))
        if hit:
            caption=hit[1].strip()
            if not caption or len(caption)>300:raise ValueError('GFM 表题应为 1–300 个字')
            stable_id=hit[2]
            end=cap_idx+1
    source=''.join(lines[index:end])
    return {'source':source,'lines':end-index,'sourceKind':'gfm-pipe','id':stable_id,
            'data':{'schema':'gfm-pipe-table-v1','sourceKind':'gfm-pipe','id':stable_id,'caption':caption,
                    'header':header,'align':align,'rows':rows,'source':source}}
