"""Expose named extension primitives from the pinned first-party editor adapter.

The CodeMirror payload and existing adapter methods remain byte-identical.
This is a deterministic adapter export, not a rebuild of upstream packages.
"""
from pathlib import Path

BEFORE = 'window.SourceEditor={attach:Yu};'
PREVIOUS = 'window.SourceEditor={attach:Yu,extensionAPI:{StateEffect:W,StateField:he,Decoration:F,EditorState:z,EditorView:D,EditorSelection:w,external:ei}};'
AFTER = 'window.SourceEditor={attach:Yu,extensionAPI:{StateEffect:W,StateField:he,Decoration:F,EditorState:z,EditorView:D,EditorSelection:w,external:ei,foldedRanges:Rn,foldEffect:Ii,unfoldEffect:Qt,sourceBlocks:Dt}};'


def expose(text):
    if text.endswith(AFTER + '})();\n'):
        return text
    for tail in (PREVIOUS, BEFORE):
        if text.count(tail) == 1 and text.endswith(tail + '})();\n'):
            return text[:-len(tail + '})();\n')] + AFTER + '})();\n'
    raise ValueError('Pinned editor adapter export changed; inspect before rebuilding')


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'app/web/vendor/source-editor.js'
    original = path.read_bytes().decode('utf8')
    path.write_bytes(expose(original).encode('utf8'))
