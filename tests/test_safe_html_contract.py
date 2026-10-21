"""HTML-01: HTML display images share the existing project asset contract."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from report_contract import analyze
from studio import audit_export


class SafeHTMLAssets(unittest.TestCase):
    def test_html_image_is_a_resource_not_a_numbered_object(self):
        """A local HTML IMG is audited as an asset without inventing a figure ID."""
        result = analyze('# Report\n\n<div><img src="assets/sample.png" alt="sample"></div>\n')
        self.assertTrue(result['ok'])
        self.assertEqual(result['assets'], ['assets/sample.png'])
        self.assertFalse(any(b['type'] == 'figure' for b in result['blocks']))

    def test_html_image_missing_asset_uses_existing_diagnostic(self):
        """A missing HTML image must fail the same attachment check as Markdown."""
        with tempfile.TemporaryDirectory() as directory:
            result = analyze('<img src="assets/missing.png">\n', assets=Path(directory))
        self.assertFalse(result['ok'])
        self.assertTrue(any(d['code'] == 'MISSING_ASSET' for d in result['diagnostics']))

    def test_html_image_external_and_traversal_are_rejected(self):
        """HTML does not bypass the offline image path boundary."""
        for src in ('https://invalid.example/a.png', '../a.png', 'data:image/png;base64,AAAA'):
            with self.subTest(src=src):
                result = analyze('<div><img src="' + src + '"></div>\n')
                self.assertFalse(result['ok'])
                self.assertTrue(any(d['code'] == 'EXTERNAL_IMAGE' for d in result['diagnostics']))

    def test_html_in_code_comments_and_raw_text_is_not_an_asset(self):
        """Examples, escaped tags and blocked raw-text elements never require files."""
        text = ('`<img src="assets/a.png">`\n\n'
                '```html\n<img src="assets/b.png">\n```\n\n'
                '\\<img src="assets/c.png">\n\n'
                '<!-- <img src="assets/d.png"> -->\n\n'
                '<script><img src="assets/e.png"></script>\n')
        self.assertEqual(analyze(text)['assets'], [])

    def test_entity_and_duplicate_attribute_follow_html_parsing(self):
        """HTML entities decode, and the browser's first duplicate attribute wins."""
        result = analyze('<img src="assets&#47;first.png" src="assets/second.png">\n')
        self.assertEqual(result['assets'], ['assets/first.png'])


class ExportHTMLAudit(unittest.TestCase):
    def test_source_json_and_code_are_not_executable_css(self):
        """Unsafe source stays exact in the archive; only rendered CSS can fetch."""
        document = ('<!doctype html><html><body><pre><code>url(https://invalid.example/example)</code></pre>'
                    '<script type="application/json" id="report-source">'
                    '{"markdown":"background-image:url(https://invalid.example/source)"}'
                    '</script></body></html>')
        audit_export(document)

    def test_rendered_external_css_is_still_rejected(self):
        """Scoping the audit must not admit a real style attribute or stylesheet fetch."""
        for style in ('<style>@import "https://invalid.example/style";</style>',
                      '<p style="background-image:&#117;rl(https://invalid.example/image)">x</p>'):
            with self.subTest(style=style):
                with self.assertRaisesRegex(ValueError, 'CSS'):
                    audit_export('<!doctype html><html><body>' + style +
                                 '<script type="application/json" id="report-source">{}</script></body></html>')


if __name__ == '__main__':
    unittest.main()
