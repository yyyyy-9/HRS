"""Update named entry points in the pinned first-party editor adapter.

The CodeMirror payload remains byte-identical.
"""
import argparse
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


def share_source_blocks(content):
    """Pass the editor state field to the two existing decoration callbacks."""
    for callback in (b'sourceTokens', b'sourceLineDecorations'):
        call = b'api.' + callback + b'(text,range.from,range.to'
        before, after = call + b')', call + b',v.state.field(Dt))'
        if content.count(after) == 1 and before not in content:
            continue
        if content.count(before) != 1 or after in content:
            raise ValueError('Pinned source decoration adapter changed')
        content = content.replace(before, after, 1)
    return content


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--share-source-blocks', action='store_true')
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / 'app/web/vendor/source-editor.js'
    content = expose(path.read_bytes().decode('utf8')).encode('utf8')
    path.write_bytes(share_source_blocks(content) if args.share_source_blocks else content)
