"""HTML IMG attachment discovery only; rendering remains in the browser engine.

The existing context mask excludes code, escaped tags, comments and raw text.
HTMLParser supplies decoded attributes/positions. The caller applies the one
existing ASSET rule and attachment checks; HTML never creates numbered objects.
"""
from html.parser import HTMLParser
from reference_context import masked_context

DROP_CONTENT = {'script', 'style', 'iframe', 'object', 'applet', 'textarea',
                'select', 'button', 'svg', 'math', 'template', 'noscript', 'head'}


class ImageReferences(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images = []
        self.blocked = []

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT:
            self.blocked.append(tag)
        if tag == 'img' and not self.blocked:
            # The browser retains the first duplicate attribute, not dict's last.
            source = next((value or '' for name, value in attrs if name == 'src'), '')
            line, column = self.getpos()
            self.images.append((source, line, column, len(self.get_starttag_text())))

    def handle_endtag(self, tag):
        if tag in self.blocked:
            del self.blocked[len(self.blocked)-1-self.blocked[::-1].index(tag):]


def references(text):
    parser = ImageReferences()
    parser.feed(masked_context(text, mask_html=False))
    return parser.images
