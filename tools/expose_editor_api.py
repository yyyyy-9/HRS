"""Expose named extension primitives from the pinned first-party editor adapter.

The CodeMirror payload and existing adapter methods remain byte-identical.
This is a deterministic adapter export, not a rebuild of upstream packages.
"""
from pathlib import Path

BEFORE = 'window.SourceEditor={attach:Yu};'
AFTER = 'window.SourceEditor={attach:Yu,extensionAPI:{StateEffect:W,StateField:he,Decoration:F,EditorState:z,EditorView:D,EditorSelection:w,external:ei}};'


def expose(text):
    if AFTER in text:
        return text
    if text.count(BEFORE) != 1 or not text.endswith(BEFORE + '})();\n'):
        raise ValueError('Pinned editor adapter export changed; inspect before rebuilding')
    return text.replace(BEFORE, AFTER)


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'app/web/vendor/source-editor.js'
    original = path.read_bytes().decode('utf8')
    path.write_bytes(expose(original).encode('utf8'))
