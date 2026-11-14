"""Refresh the HRS MathLive selection changes against the pinned upstream UMD."""
import argparse
from hashlib import sha256
from pathlib import Path

UPSTREAM_SHA256 = '51e9ab5c4739209a2951a550042dcecb99ad3047269c1d791d09d7d613226eae'


def patch(raw: bytes) -> bytes:
    if sha256(raw).hexdigest() != UPSTREAM_SHA256:
        raise ValueError('Expected the original MathLive 0.111.1 UMD')
    text = raw.decode('utf8')

    def replace(before, after):
        nonlocal text
        if text.count(before) != 1:
            raise ValueError('Pinned MathLive implementation changed at ' + before[:80])
        text = text.replace(before, after, 1)

    # Preserve native hit testing and painting. Only schedule a paint if the
    # final range or caret changes, including after word-selection expansion.
    replace(
        'xe>=0&&Pe>=0&&(r.model.extendSelectionTo(xe,Pe),Y(t)),o&&Ks(r.model)',
        'if(xe>=0&&Pe>=0){let anchor=r.model.anchor,position=r.model.position,before=r.model.selection;'
        'r.model.extendSelectionTo(xe,Pe),o&&Ks(r.model);'
        'if(anchor!==r.model.anchor||position!==r.model.position||j0(before,r.model.selection)==="different")Y(t)'
        '}else o&&Ks(r.model)',
    )
    # Geometry unions own their accumulator. The original union could grow
    # the first atom's cached hit box into the neighboring script.
    replace(
        'n.right=Math.max(n.right,a.right)):n=a)}return n!=null?n:{top:0,bottom:0,left:0,right:0}',
        'n.right=Math.max(n.right,a.right)):n={...a})}return n!=null?n:{top:0,bottom:0,left:0,right:0}',
    )
    # The selector index belongs to one native markup generation.
    replace(
        'i.innerHTML=globalThis.MathfieldElement.createHTML(a),uo(t,e.interactive)',
        't.atomNodeIndex=void 0,i.innerHTML=globalThis.MathfieldElement.createHTML(a),uo(t,e.interactive)',
    )
    replace(
        'function ar(t,e){',
        'function hrAtomNodes(field,id){'
        'let index=field.atomNodeIndex;'
        'if(!index){index=new Map;'
        'for(let node of field.field.querySelectorAll("[data-atom-id]")){'
        'let key=node.getAttribute("data-atom-id");'
        'if(!index.has(key))index.set(key,[]);index.get(key).push(node)'
        '}field.atomNodeIndex=index}return index.get(id)||[]'
        '}function ar(t,e){',
    )
    replace(
        'let i=t.field.querySelectorAll(\x60[data-atom-id="${e.id}"]\x60),n=Array.from(i);',
        'let n=hrAtomNodes(t,String(e.id));',
    )
    # Measure the common coordinate origin once per selection range.
    replace(
        'function hc(t,e,r){if(!e)return null;let i=t.field.getBoundingClientRect(),n=e.right-e.left,'
        'o=e.bottom-e.top,a=Math.ceil(e.left-i.left+t.field.scrollLeft*r),s=Math.ceil(e.top-i.top);',
        'function hc(t,e,r,i,scrollLeft){if(!e)return null;'
        'i??=t.field.getBoundingClientRect(),scrollLeft??=t.field.scrollLeft;'
        'let n=e.right-e.left,o=e.bottom-e.top,'
        'a=Math.ceil(e.left-i.left+scrollLeft*r),s=Math.ceil(e.top-i.top);',
    )
    replace(
        'let i=new Map,n=t.field,o=n.offsetWidth,s=Math.floor(n.getBoundingClientRect().width)/o;s=isNaN(s)?1:s;',
        'let i=new Map,n=t.field,o=n.offsetWidth,bounds=n.getBoundingClientRect(),scrollLeft=n.scrollLeft,'
        's=Math.floor(bounds.width)/o;s=isNaN(s)?1:s;',
    )
    replace('let c=hc(t,ar(t,l),s);', 'let c=hc(t,ar(t,l),s,bounds,scrollLeft);')

    # Native hit boxes use viewport coordinates. Invalidate them when the
    # formula moves, including autoscroll while the selection is unchanged.
    replace(
        'let n=t.field.querySelector(".ML__latex").getBoundingClientRect();if(!n)return 0;',
        'let n=t.field.querySelector(".ML__latex")?.getBoundingClientRect();if(!n)return 0;'
        'let previous=t.atomBoundsViewport;'
        'if(previous&&(previous.left!==n.left||previous.top!==n.top||previous.right!==n.right||previous.bottom!==n.bottom))'
        't.atomBoundsCache?.clear();t.atomBoundsViewport=n;',
    )
    return text.encode('utf8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_bytes(patch(args.upstream.read_bytes()))


if __name__ == '__main__':
    main()
