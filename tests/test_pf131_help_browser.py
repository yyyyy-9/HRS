"""HELP-01: real HTTP/offline navigation using the shared isolated fixture."""
from pathlib import Path
import hashlib,os,re,tempfile,unittest
from browser_support import ROOT as SOURCE_ROOT,LiveDocument,browser_session
ROOT=SOURCE_ROOT/'app'

class HelpNavigation(unittest.TestCase):
    def test_generated_help_and_current_document_navigation(self):
        markdown = (ROOT / 'docs/USER_GUIDE.md').read_bytes()
        html = (ROOT / 'web/help.html').read_text('utf8')
        assert '<meta name="hrs-markdown-sha256" content="' + hashlib.sha256(markdown).hexdigest() + '">' in html
        assert html.count('<script id="hrs-reader-runtime">') == 1
        assert (ROOT / 'web/report_reader.js').read_text('utf8') in html
        assert not re.search(r'<img\s+[^>]*src=["\'](?:https?://|file:)', html, re.I)

        with browser_session() as browser,tempfile.TemporaryDirectory(prefix='hrs-help-') as folder:
            with LiveDocument(browser,Path(folder)) as document:
                page=document.page;errors=document.errors;base=document.url
                response = page.goto(base + '/web/help.html', wait_until='load')
                assert response.status == 200
                assert 'HTML Report Studio' in page.title()
                assert page.locator('.docs-paper h1,.docs-paper h2').count() >= 4
                assert page.locator('.docs-paper table').count() >= 1
                headings = page.locator('.docs-paper h2,.docs-paper h3').all_inner_texts()
                assert not any(re.search(r'HF8\s+PF\d', text) for text in headings), headings
                first_section = page.locator('.docs-nav a[href^="#"]').first
                assert '五分钟' in first_section.inner_text()
                first_section.click()
                assert '#section-' in page.url
                images = page.locator('.docs-paper img')
                assert images.count() >= 5
                assert images.evaluate_all('(list)=>list.every(i=>i.src.startsWith("data:image/") && i.complete && i.naturalWidth>0)')
                assert page.locator('script[src^="http"]').count() == 0
                assert page.locator('.docs-paper pre code').count() >= 1
                assert page.locator('[data-code-copy],button[data-copy-code],.hrs-code-copy').count() > 0
                artifact = os.environ.get('TEST_ARTIFACT_DIR')
                if artifact:
                    directory = Path(artifact)
                    directory.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(directory / 'pf131_help_dogfood.png'), full_page=False)

                # Follow real navigation, including the two routes reported by the user.
                def follow(selector, expected):
                    with page.expect_navigation(wait_until='load') as nav:
                        page.locator(selector).first.click()
                    assert nav.value.status == 200, (expected, page.url)
                    assert page.url.split('#')[0].endswith(expected), page.url

                # DOC-03: the Module action must describe the current application,
                # with the downstream Word handoff available as a separate document.
                assert page.locator('.docs-actions a').filter(has_text='模块说明').get_attribute('href') == 'MODULE_OVERVIEW.html'
                follow('.docs-actions a[href="MODULE_OVERVIEW.html"]', '/web/MODULE_OVERVIEW.html')
                assert page.locator('h1').inner_text() == 'HTML Report Studio 模块说明'
                for subject in ('解析', '保存', '资源', '导出', '服务'):
                    assert subject in page.locator('.docs-paper').inner_text(), subject
                if artifact:
                    page.screenshot(path=str(directory / 'module_overview.png'), full_page=False)
                follow('a[href$="WORD_COMPILER_HANDOFF.html"]', '/web/WORD_COMPILER_HANDOFF.html')
                assert 'Word/WPS 下游数据接口' in page.locator('h1').inner_text()
                assert not any(re.search(r'^(?:HF\d|PF\d|v\d|20\d\d-)', text)
                               for text in page.locator('.docs-paper h2,.docs-paper h3').all_inner_texts())
                if artifact:
                    page.screenshot(path=str(directory / 'word_handoff.png'), full_page=False)
                follow('a[href$="LONG_TERM_ROADMAP.html"]', '/docs/LONG_TERM_ROADMAP.html')
                follow('a[href$="SHORT_TERM_PLAN.html"]', '/docs/SHORT_TERM_PLAN.html')
                follow('a[href$="CURRENT_STATUS.html"]', '/docs/CURRENT_STATUS.html')
                follow('a[href$="HISTORY_INDEX.md"]', '/docs/HISTORY_INDEX.md')
                if (SOURCE_ROOT / 'PUBLIC_SOURCE_POLICY.json').is_file():
                    assert '发行记录' in page.locator('body').inner_text()
                    assert 'https://github.com/yyyyy-9/HRS/releases' in page.locator('body').inner_text()
                else:
                    assert '完整阶段原文' in page.locator('body').inner_text()

                # Same HTML-to-HTML navigation must work without any server.
                page.goto((ROOT / 'web/help.html').as_uri(), wait_until='load')
                with page.expect_navigation(wait_until='load'):
                    page.locator('.docs-actions a[href="CHANGELOG_READABLE.html"]').click()
                assert page.url.startswith('file:') and page.url.endswith('/web/CHANGELOG_READABLE.html')
                with page.expect_navigation(wait_until='load'):
                    page.locator('a[href$="CURRENT_STATUS.html"]').first.click()
                assert page.url.startswith('file:') and page.url.endswith('/docs/CURRENT_STATUS.html')
                assert '当前状态' in page.locator('h1').inner_text()
                assert not errors, errors
                print('BROWSER help: real portable HTTP routes and clicks, task-oriented TOC, embedded images/reader, offline file navigation, zero errors OK')


if __name__=='__main__':unittest.main(verbosity=2)
