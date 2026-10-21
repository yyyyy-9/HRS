"""Mask non-prose Markdown contexts without changing length or line endings.

This is a bounded context scanner for report references, not a Markdown renderer.
Link labels remain prose; destinations/titles, images, code, math, definitions and
HTML syntax do not. Original indices are retained for UTF-16 range conversion.
"""
import re

DEFINITION=re.compile(r'^ {0,3}\[([^\]\r\n]+)\]:[ \t]*([^\r\n]*)(?:\r?\n|$)',re.M)
BACKTICKS=re.compile(r'`+')
INLINE_TAG=re.compile(r'<(?:/?[A-Za-z][A-Za-z0-9:-]*(?:\s+(?:[^>\"\']|\"[^\"]*\"|\'[^\']*\')*)?\s*/?|(?:https?://|mailto:)[^>\r\n]+)>',re.I)
BARE_URL=re.compile(r'(?:https?://|www\.)[^\s<>]+')
BLOCK_TAGS=r'address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul'


def label_key(text):
    return re.sub(r'\s+',' ',text).strip().casefold()


def masked_context(text, *, mask_images=True, mask_html=True):
    result=list(text)
    def blank(start,end):
        for index in range(start,end):
            if text[index] not in '\r\n':result[index]=' '
    definitions={label_key(match[1]) for match in DEFINITION.finditer(text)}
    for match in DEFINITION.finditer(text):blank(match.start(),match.end())
    # Indented code at a block boundary. Do not mask continued list prose.
    previous_blank=True
    for match in re.finditer(r'[^\r\n]*(?:\r\n|\n|\r|$)',text):
        line=match[0].rstrip('\r\n')
        if not line:previous_blank=True;continue
        if previous_blank and re.match(r'^(?: {4}|\t)',line):blank(match.start(),match.end());continue
        previous_blank=not line.strip()
    # HTML blocks used by Marked consume through the next blank line, or the
    # matching close for raw-text elements/comments. Inline tag text stays prose.
    block_pattern=re.compile(r'^ {0,3}</?(?:'+BLOCK_TAGS+r')(?=[\s/>])[^\r\n]*(?:\r?\n(?![ \t]*\r?\n)[^\r\n]*)*',re.I|re.M)
    if mask_html:
        for match in block_pattern.finditer(text):blank(match.start(),match.end())
    for match in re.finditer(r'<(script|style|pre|textarea)\b[^>]*>[\s\S]*?</\1\s*>|<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<![A-Z][\s\S]*?>',text,re.I):blank(match.start(),match.end())

    bracket_cache={}
    def closing_bracket(start):
        # Nested '[' met during one scan share its escape alignment, so their
        # matches (or failures) are cached; many unclosed '[' stay linear.
        if start in bracket_cache:return bracket_cache[start]
        stack=[start];index=start+1
        while index<len(text):
            if text[index]=='\\':index+=2;continue
            if text[index]=='[':stack.append(index)
            elif text[index]==']':
                bracket_cache[stack.pop()]=index
                if not stack:return index
            index+=1
        for opened in stack:bracket_cache[opened]=None
        return None

    def closing_destination(start):
        depth=1;quote=None;angle=False;index=start+1
        while index<len(text):
            char=text[index]
            if char=='\\':index+=2;continue
            if quote:
                if char==quote:quote=None
            elif angle:
                if char=='>':angle=False
            elif char=='<':angle=True
            elif char in '\"\'' and index>start+1 and text[index-1].isspace():quote=char
            elif char=='(':depth+=1
            elif char==')':
                depth-=1
                if not depth:return index
            index+=1
        return None

    # Patterns are matched at a position instead of on text[index:] slices so a
    # long report with many backticks/tags is not copied once per occurrence.
    backtick_unclosed={}
    last_display=text.rfind('$$')
    index=0
    while index<len(text):
        if result[index]==' ' and text[index]!=' ':index+=1;continue
        char=text[index]
        if char=='\\':
            if not mask_html and text[index:index+2]=='\\<':
                escaped=INLINE_TAG.match(text,index+1)
                if escaped:blank(index,escaped.end());index=escaped.end();continue
            # TeX's escaped delimiters are structural math boundaries, not
            # ordinary Markdown escapes. Mask a complete pair only; unmatched
            # source remains prose, and backtick spans were consumed above.
            opener=text[index:index+2]
            if opener in ('\\(', '\\['):
                closer='\\)' if opener=='\\(' else '\\]'
                end=index+2
                while end<len(text):
                    if text[end]=='\\':
                        if text.startswith(closer,end):break
                        end+=2;continue
                    if opener=='\\(' and text[end] in '\r\n':break
                    end+=1
                if end<len(text) and text.startswith(closer,end):
                    blank(index,end+2);index=end+2;continue
            index+=2;continue
        if char=='`':
            run=BACKTICKS.match(text,index)[0]
            after_run=index+len(run)
            close=None
            if backtick_unclosed.get(len(run),len(text)+1)>after_run:
                close=re.compile(r'(?<!`)'+re.escape(run)+r'(?!`)').search(text,after_run)
                if not close:backtick_unclosed[len(run)]=after_run
            if close:
                end=close.end();blank(index,end);index=end;continue
        if char=='$':
            delimiter='$$' if text.startswith('$$',index) else '$'
            end=index+len(delimiter)
            if delimiter=='$$' and last_display<end:end=len(text)
            while end<len(text):
                if text[end]=='\\':end+=2;continue
                if delimiter=='$' and text[end] in '\r\n':break
                if text.startswith(delimiter,end):
                    blank(index,end+len(delimiter));index=end+len(delimiter);break
                end+=1
            else:end=len(text)
            if index==end+len(delimiter):continue
        if char=='<':
            tag=INLINE_TAG.match(text,index)
            if tag:
                if mask_html:blank(index,tag.end())
                index=tag.end();continue
        if char=='[' or char=='!' and index+1<len(text) and text[index+1]=='[':
            image=char=='!';start=index+1 if image else index;close=closing_bracket(start)
            if close is not None:
                after=close+1;end=None
                if after<len(text) and text[after]=='(':
                    tail=closing_destination(after)
                    if tail is not None:end=tail+1;blank(after,end)
                elif after<len(text) and text[after]=='[':
                    tail=closing_bracket(after)
                    if tail is not None:
                        key=text[after+1:tail] or text[start+1:close]
                        if label_key(key) in definitions:end=tail+1;blank(after,end)
                elif label_key(text[start+1:close]) in definitions:end=close+1
                if image and end is not None:
                    if mask_images:blank(index,end)
                    else:result[index:end]=text[index:end]
                    index=end;continue
                # Continue through link label so nested code/math/tags are masked.
        if text.startswith(('https://','http://','www.'),index) and (index==0 or not text[index-1].isalnum()):
            url=BARE_URL.match(text,index)
            if url:blank(index,url.end());index=url.end();continue
        index+=1
    return ''.join(result)
