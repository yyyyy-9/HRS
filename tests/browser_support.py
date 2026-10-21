"""Shared real-service fixture; no document or rendering API is mocked.

Only the native destination picker is substituted. Each case owns its registry,
drafts, page and server; class resources and failed setup always get cleanup.
"""
from contextlib import ExitStack, contextmanager
from pathlib import Path
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import studio
from portable_host import PortableHandler, WindowSessions
from studio import StudioServer

_shared = None
SERVER_POLL_SECONDS = 0.05


def artifact_directory(filename, legacy_env=None, prefix='hrs-evidence-'):
    """One directory per standalone suite; do not create unused temporary roots."""
    if os.environ.get('TEST_ARTIFACT_DIR'):
        result=Path(os.environ['TEST_ARTIFACT_DIR'])/Path(filename).stem
    elif legacy_env and os.environ.get(legacy_env):
        result=Path(os.environ[legacy_env])
    else:
        result=Path(tempfile.mkdtemp(prefix=prefix))
    result.mkdir(parents=True,exist_ok=True)
    return result


def wait_rich_clipboard(page, expected):
    """Await actual clipboard data; this pinned driver's wait_for_function can accept a Promise itself."""
    return page.evaluate('''async expected=>{
      const normalize=text=>text.replace(/\\r\\n?/g,'\\n'),deadline=Date.now()+10000;
      do{
        const text=await navigator.clipboard.readText(),items=await navigator.clipboard.read();
        if(normalize(text)===normalize(expected)&&items[0]?.types.includes('text/html')&&
           (await(await items[0].getType('text/html')).text()).includes('data-hrs-clipboard'))return true;
        await new Promise(resolve=>setTimeout(resolve,30));
      }while(Date.now()<deadline);
      throw Error('Current object copy did not finish before selection/document change');
    }''',expected)


def close_shared_browser():
    global _shared
    if _shared is not None:
        playwright, browser = _shared
        _shared = None
        try:
            browser.close()
        finally:
            playwright.stop()


def source(page, text):
    page.evaluate("md=>{const e=document.querySelector('#markdown').sourceEditor;e.view.dispatch({changes:{from:0,to:e.value.length,insert:md}});}", text)
    page.wait_for_function("md=>document.querySelector('#markdown').sourceEditor.value===md", arg=text)


def select(page, start, end):
    page.evaluate("([a,b])=>{const e=document.querySelector('#markdown').sourceEditor;e.setSelectionRange(a,b);e.focus();}", [start, end])


def value(page):
    return page.locator('#markdown').evaluate('e=>e.sourceEditor.value')


def css_color(page, token):
    """Resolve the canonical theme token, independently of a table/code consumer."""
    return page.evaluate("token=>{const probe=document.createElement('span');probe.style.backgroundColor=`var(--hrs-${token})`;document.body.append(probe);const value=getComputedStyle(probe).backgroundColor;probe.remove();return value;}", token)


@contextmanager
def browser_session():
    global _shared
    from playwright.sync_api import sync_playwright
    executable = Path(os.environ.get('CHROMIUM_PATH', ''))
    if not executable.is_file():
        raise RuntimeError('Browser tests require CHROMIUM_PATH pointing to an installed Chromium executable')
    if os.environ.get('HRS_TEST_REUSE_BROWSER') == '1':
        if _shared is None:
            playwright = sync_playwright().start()
            try:
                browser = playwright.chromium.launch(executable_path=str(executable), headless=True)
            except BaseException:
                playwright.stop()
                raise
            _shared = playwright, browser
        browser = _shared[1]
        existing = set(browser.contexts)
        try:
            yield browser
        finally:
            for context in browser.contexts:
                if context not in existing:
                    context.close()
    else:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(executable), headless=True)
            try:
                yield browser
            finally:
                browser.close()


class QuietHandler(PortableHandler):
    def log_message(self, *args):
        pass


class LiveDocument:
    """One isolated project using the genuine StudioServer and shipped page."""
    def __init__(self, browser, folder, text='# Initial\n', *, assets=None,
                 profile='free', registered=False, init_script=None):
        self.browser, self.folder = browser, Path(folder)
        self.project = self.folder / 'source'
        (self.project / 'assets').mkdir(parents=True)
        (self.project / 'report.md').write_bytes(text.encode('utf8'))
        for name, raw in (assets or {}).items():
            target = self.project / 'assets' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        self.resources = ExitStack()
        try:
            self.server = StudioServer(('127.0.0.1', 0), self.project, self.folder / 'workspace')
            # PUBLIC-01: wait for this test server's in-flight writes before
            # TemporaryDirectory cleanup; production daemon policy is unchanged.
            self.server.daemon_threads = False
            self.resources.callback(self.server.server_close)
            self.server.RequestHandlerClass = QuietHandler
            self.server.portable_lifecycle = WindowSessions('test-service', enabled=False)
            document_id = 'e' * 32 if registered else 'legacy'
            if registered:
                self.server.registry.register(document_id, self.project)
            # The stdlib default adds up to half a second to each case's
            # shutdown. This only tunes the short-lived test server, not product
            # request/lease timing; incoming sockets still wake select at once.
            thread = threading.Thread(target=self.server.serve_forever,
                                      kwargs={'poll_interval': SERVER_POLL_SECONDS}, daemon=True)
            thread.start()
            self.resources.callback(thread.join, 3)
            self.resources.callback(self.server.shutdown)
            self.context = browser.new_context(viewport={'width': 1600, 'height': 1000})
            self.resources.callback(self.context.close)
            if init_script:
                self.context.add_init_script(init_script)
            self.page = self.context.new_page()
            self.page.set_default_timeout(12000)
            self.errors = []
            self.page.on('pageerror', lambda error: self.errors.append(str(getattr(error, 'stack', None) or error)))
            self.url = f'http://127.0.0.1:{self.server.server_port}'
            self.page.goto(self.url + '/web/index.html?programmatic=1')
            self.page.evaluate('async id=>{await ReportStudioProgrammatic.ready();await ReportStudioProgrammatic.open(id)}', document_id)
            self.page.locator('#render-profile').select_option(profile)
            self.page.wait_for_function("profile=>!document.querySelector('#render-profile').disabled&&document.body.dataset.renderProfile===profile",arg=profile)
        except BaseException:
            if getattr(self, 'errors', None):
                print('Browser setup errors:', self.errors, flush=True)
            self.resources.close()
            raise

    def close(self):
        self.resources.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def export(self, *, via_ui=False):
        if via_ui:
            self.page.locator('#menu-export > summary').click()
            self.page.locator('#btn-export').click()
            self.page.locator('input[name="export-quality"][value="original"]').check()
            self.page.locator('input[name="export-source"][value="recompilable"]').check()
            with self.page.expect_response(lambda response: '/api/export/store' in response.url) as pending:
                self.page.locator('#modal-ok').click()
            response = pending.value
            receipt = response.json()
            if not response.ok or not receipt.get('ok'):
                raise AssertionError('Native UI export failed: ' + str(receipt))
            return response.request.post_data_json['html']
        return self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({quality:'original',sourceMode:'recompilable'})")


class ManualService(unittest.TestCase):
    initial_markdown = '# Initial\n'
    registered_project = False

    @classmethod
    def setUpClass(cls):
        resources = ExitStack()
        cls.addClassCleanup(resources.close)
        cls.folder = Path(resources.enter_context(tempfile.TemporaryDirectory(prefix='hrs-ui-')))
        cls.destination = Path(resources.enter_context(tempfile.TemporaryDirectory(prefix='hrs-saved-')))
        resources.enter_context(patch.object(studio, 'pick_project_parent', lambda: cls.destination))
        cls.browser = resources.enter_context(browser_session())

    def project_setup(self):
        return self.initial_markdown, self.registered_project

    def setUp(self):
        text, registered = self.project_setup()
        self.document = LiveDocument(self.browser, self.folder / self._testMethodName,
                                     text, registered=registered)
        self.addCleanup(self.document.close)
        for name in ('page', 'server', 'project', 'errors'):
            setattr(self, name, getattr(self.document, name))
        evidence_root = os.environ.get('TEST_ARTIFACT_DIR') or os.environ.get('HRS_RC3_EVIDENCE')
        self.evidence = Path(evidence_root) / type(self).__name__ / self._testMethodName if evidence_root else None
        if self.evidence:
            self.evidence.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        print('UI state:', self.page.locator('#save-indicator').inner_text(), self.page.locator('#toast').inner_text(), self.page.locator('#modal-note').inner_text(), flush=True)
        self.assertFalse(self.errors, self.errors)

    def import_manual(self):
        fixture = ROOT / 'tests/fixtures/lingmo_manual'
        self.page.locator('#file-import').set_input_files(str(fixture / '灵墨用户手册.md'))
        self.page.wait_for_selector('#modal-body input[type=file]')
        image = next((fixture / '资源').glob('*.png'))
        self.page.locator('#modal-body input[type=file]').set_input_files(str(image))
        self.page.locator('#modal-ok').click()
        self.page.wait_for_function("document.querySelector('#preview-content img')?.naturalWidth>0")
        return value(self.page)

