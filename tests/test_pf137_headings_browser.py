"""READ-01: six-level navigation and readable deep headings, using the real exporter."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(ROOT))
from studio import audit_export


class ReaderHeadings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from contextlib import ExitStack
        from browser_support import LiveDocument, browser_session
        resources=ExitStack();cls.addClassCleanup(resources.close)
        cls.folder=Path(resources.enter_context(tempfile.TemporaryDirectory(prefix='hrs-heading-browser-')))
        cls.raw=('\n\n'.join('#'*i+' 标题'+str(i)+'\n\n正文示例。' for i in range(1,7))+'\n').encode('utf8')
        cls.browser=resources.enter_context(browser_session())
        document=resources.enter_context(LiveDocument(cls.browser,cls.folder,cls.raw.decode('utf8')))
        cls.editor=document.page;cls.project=document.project
        cls.html=document.export()
        cls.file=cls.folder/'report.html';cls.file.write_bytes(cls.html.encode('utf8'))
        cls.reader=cls.browser.new_page(viewport={'width':1366,'height':900})
        cls.reader.goto(cls.file.as_uri(),wait_until='load')

    def test_all_six_levels_have_real_targets_and_clickable_navigation(self):
        """H5/H6 must appear with their own depth and working anchors, excluding object internals."""
        links=self.reader.locator('.hrs-reader-links > .hrs-reader-nav-link')
        self.assertEqual(links.count(),6)
        for i in range(1,7):
            link=self.reader.locator('.hrs-reader-level-'+str(i));self.assertEqual(link.inner_text(),'标题'+str(i))
            href=link.get_attribute('href');self.assertTrue(href.startswith('#'))
            self.assertEqual(self.reader.locator(href).count(),1);link.click()
            self.assertTrue(self.reader.url.endswith(href))
        result=self.reader.evaluate('''()=>{const a=document.querySelector('main');const box=document.createElement('div');
            box.className='report-table-wrap';box.innerHTML='<h6>表内标题</h6>';a.append(box);
            const count=HRSReportReader.headingOutline(a).length;box.remove();return count;}''')
        self.assertEqual(result,6)

    def test_deep_headings_follow_body_size_in_preview_export_and_print_css(self):
        """H4..H6 never shrink below prose across the three existing themes and mobile/print CSS."""
        for theme in ('engineering','academic','brief'):
            self.editor.evaluate('(theme)=>document.body.dataset.reportTheme=theme',theme)
            sizes=self.editor.evaluate('''()=>{const b=document.querySelector('.paper');return [getComputedStyle(b).fontSize,
                ...[4,5,6].map(i=>getComputedStyle(b.querySelector('h'+i)).fontSize)];}''')
            self.assertTrue(all(float(v[:-2])>=float(sizes[0][:-2]) for v in sizes[1:]),('preview',theme,sizes))
            for media in ('screen','print'):
                self.reader.emulate_media(media=media)
                self.reader.evaluate('(theme)=>document.body.className="theme-"+theme+" hrs-reader-mode"',theme)
                sizes=self.reader.evaluate('''()=>[getComputedStyle(document.body).fontSize,
                    ...[4,5,6].map(i=>getComputedStyle(document.querySelector('main h'+i)).fontSize)]''')
                self.assertTrue(all(float(v[:-2])>=float(sizes[0][:-2]) for v in sizes[1:]),('export',theme,media,sizes))
        self.reader.emulate_media(media='screen');self.reader.set_viewport_size({'width':620,'height':900})
        sizes=self.reader.evaluate('''()=>[getComputedStyle(document.body).fontSize,
            ...[4,5,6].map(i=>getComputedStyle(document.querySelector('main h'+i)).fontSize)]''')
        self.assertTrue(all(float(v[:-2])>=float(sizes[0][:-2]) for v in sizes[1:]),('mobile',sizes))

    def test_source_and_heading_semantics_are_unchanged(self):
        """Presentation keeps H1..H6/source bytes; centering remains an unimplemented candidate."""
        payload=self.reader.locator('#report-source').text_content()
        import json
        self.assertEqual(json.loads(payload)['markdown'].encode('utf8'),self.raw)
        self.assertEqual(self.reader.locator('main h1,main h2,main h3,main h4,main h5,main h6').count(),6)
        self.assertNotEqual(self.reader.locator('main h1').evaluate('(n)=>getComputedStyle(n).textAlign'),'center')
        audit_export(self.html)
        self.assertEqual(hashlib.sha256((self.project/'report.md').read_bytes()).hexdigest(),hashlib.sha256(self.raw).hexdigest())


if __name__=='__main__':unittest.main(verbosity=2)
