"""Section selectors over authoritative report_contract IR; offsets remain UTF-16."""
from __future__ import annotations
import re

def sections(ir):
    headings=[block for block in ir['blocks'] if block['type']=='heading'];stack=[];result=[]
    for i,block in enumerate(headings):
        while stack and stack[-1]['level']>=block['level']:stack.pop()
        item={**block,'path':[*(stack[-1]['path'] if stack else []),block['text']],
              'bodyStart':block['end'],
              'end':next((other['start'] for other in headings[i+1:] if other['level']<=block['level']),ir['source_snapshot']['utf16_length'])}
        stack.append(item);result.append(item)
    return result

def locate(ir,path):
    if not isinstance(path,list) or not path or any(not isinstance(title,str) or not title for title in path):
        raise ValueError('Section path must contain exact heading titles')
    found=[item for item in sections(ir) if len(path)<=len(item['path']) and item['path'][-len(path):]==path]
    if len(found)!=1:raise ValueError('AMBIGUOUS_SECTION: use full heading path' if found else 'MISSING_SECTION')
    return found[0]

def edit(text,item,replacement,operation):
    newline='\r\n' if '\r\n' in text else '\n'
    replacement=re.sub(r'\r\n?|\n',lambda _:newline,replacement)
    a,b=item['bodyStart'],item['end']
    if operation=='append':a=b
    elif operation=='prepend':b=a
    elif operation!='replace-body':raise ValueError('Section operation must be append, prepend or replace-body')
    raw=text.encode('utf-16-le');left=raw[:a*2].decode('utf-16-le');right=raw[b*2:].decode('utf-16-le')
    leading='' if not replacement or not left or left.endswith(newline*2) else newline if left.endswith(newline) else newline*2
    trailing='' if not right or not replacement or replacement.endswith(newline*2) else newline if replacement.endswith(newline) else newline*2
    return a,b,leading+replacement+trailing
