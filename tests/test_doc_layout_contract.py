"""HAR-03: current runtime docs stand alone; full history stays source-only."""
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urldefrag, urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


BUILD = module('hrs_doc_build', ROOT / 'tools/build_release.py')
DOCS = module('hrs_doc_check', ROOT / 'app/tools/maintain_docs.py')


class DocumentLinks(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links, self.ids = [], set()
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])


class DocumentationHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / 'app'))
        from studio import StudioServer
        from portable_host import PortableHandler, WindowSessions
        cls.folder = tempfile.TemporaryDirectory(prefix='hrs-help-links-')
        folder = Path(cls.folder.name)
        cls.server = StudioServer(('127.0.0.1', 0), folder / 'project', folder / 'workspace')
        cls.server.RequestHandlerClass = PortableHandler
        cls.server.portable_lifecycle = WindowSessions('help-links-test', enabled=False)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.folder.cleanup()

    def request(self, url, *, data=None):
        request = Request(quote(url, safe=':/?#%=&'), data=data,
                          headers={'Content-Type': 'application/json'} if data else {})
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    def test_all_generated_document_links_work_on_real_server(self):
        """HELP-01: every local link and HTML anchor works through the actual server, including both reported targets."""
        app = ROOT / 'app'
        pages = list((app / 'docs').glob('*.html')) + [
            app / 'web' / name for name in ('help.html', 'CHANGELOG_READABLE.html', 'MODULE_OVERVIEW.html', 'WORD_COMPILER_HANDOFF.html')]
        self.assertEqual(len(pages), 11)
        broken, cache = [], {}
        for page in pages:
            origin = self.base + '/' + page.relative_to(app).as_posix()
            for href in DocumentLinks(page.read_text('utf8')).links:
                if urlsplit(href).scheme or urlsplit(href).netloc:
                    continue
                url, anchor = urldefrag(urljoin(origin, href))
                if url not in cache:
                    cache[url] = self.request(url)
                status, body = cache[url]
                expected = app / unquote(urlsplit(url).path).lstrip('/')
                if status != 200 or not expected.is_file() or body != expected.read_bytes():
                    broken.append((page.relative_to(app).as_posix(), href, status))
                elif anchor and expected.suffix == '.html' and unquote(anchor) not in DocumentLinks(body.decode('utf8')).ids:
                    broken.append((page.relative_to(app).as_posix(), href, 'missing anchor'))
        for path in ('/docs/SHORT_TERM_PLAN.html', '/docs/HISTORY_INDEX.md'):
            if self.request(self.base + path)[0] != 200:
                broken.append(('reported target', path, 404))
        self.assertEqual(broken, [], 'Broken documentation links: ' + repr(broken))
        self.assertEqual(self.request(self.base+'/docs/PF13_7_TEST_REPORT.md')[0],404)
        self.assertFalse((app/'docs/history').exists())

    def test_document_routes_do_not_expose_program_or_allow_writes(self):
        """HELP-01: documentation access cannot escape its directory, expose program files, or write documents."""
        for path, file in (('/', 'web/index.html'), ('/web/app.js', 'web/app.js'),
                           ('/web/design_tokens.css', 'web/design_tokens.css')):
            status, body = self.request(self.base + path)
            self.assertEqual(status, 200)
            self.assertEqual(body, (ROOT / 'app' / file).read_bytes())
        for path in ('/studio.py', '/MANIFEST.json', '/docs/%2e%2e/studio.py',
                     '/docs/..%5cstudio.py', '/docs/%2e%2e/%2e%2e/AGENTS.md'):
            self.assertEqual(self.request(self.base + path)[0], 404, path)
        self.assertEqual(self.request(self.base + '/docs/CURRENT_STATUS.md', data=b'{}')[0], 404)


class DocumentLayout(unittest.TestCase):
    def test_current_documents_may_use_unversioned_headings_but_reject_stale_identity(self):
        """RELEASE-REVIEW-01: a gate must not require copies of the release constant."""
        self.assertFalse(DOCS.active_heading_version_problem('# 当前状态\n\n历史证据 v0.0.1。'))
        self.assertFalse(DOCS.active_heading_version_problem('# 当前状态 '+DOCS.RELEASE['release']))
        self.assertTrue(DOCS.active_heading_version_problem('# 当前状态 v0.0.0 R1'))
        self.assertTrue(DOCS.active_heading_version_problem('# 当前状态 '+DOCS.RELEASE['version_label']+' R99999'))

    def test_documented_ir_example_commands_succeed_without_source_changes(self):
        """DOC-02: run the documented structural example; full validation still rejects absent assets."""
        app = ROOT / 'app'
        spec = (app / '工程报告源格式_v1_规范.md').read_text('utf8')
        section = spec.split('## 6. 工程 IR 输出契约', 1)[1].split('## 7.', 1)[0]
        commands = [shlex.split(line) for line in section.splitlines()
                    if re.match(r'^python .*docs/IR_EXAMPLE_SOURCE\.md', line) and '--output' not in line]
        self.assertTrue(commands, 'The quick-start example must have an executable command')
        example = app / 'docs/IR_EXAMPLE_SOURCE.md'
        before = example.read_bytes()
        for command in commands:
            result = subprocess.run([sys.executable, '-X', 'utf8', '-B', *command[1:]],
                                    cwd=app, capture_output=True, text=True, encoding='utf8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(result.stdout)
            self.assertTrue(data['ok'])
            self.assertEqual(data['schema'], 'hrs-agent-read-v1')
        full = subprocess.run([sys.executable, '-X', 'utf8', '-B', 'report_contract.py',
                               'validate', 'docs/IR_EXAMPLE_SOURCE.md', '--json'],
                              cwd=app, capture_output=True, text=True, encoding='utf8')
        self.assertEqual(full.returncode, 1)
        self.assertEqual([d['code'] for d in json.loads(full.stdout)['diagnostics']],
                         ['MISSING_ASSET'] * 4)
        self.assertEqual(example.read_bytes(), before)

    def test_source_package_retains_history(self):
        """HAR-03: source packaging includes historical material outside app/."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'history').mkdir()
            (root / 'history/old.md').write_bytes(b'historical data')
            self.assertEqual(BUILD.source_files(root)['history/old.md'], b'historical data')

    def test_no_parallel_hotfix_or_bulk_redirects_in_current_app(self):
        """HAR-03: updates use existing logs; old duplicated paths are removed."""
        self.assertFalse((ROOT / 'app/HOTFIX_HF8_PF13_7.md').exists())
        redirects = [p for p in (ROOT / 'app').rglob('*.md')
                     if p.read_bytes().startswith(b'<!-- hrs-history-redirect -->')]
        self.assertEqual(redirects, [])

    def test_all_approved_archives_survive_outside_runtime(self):
        """HAR-03: all 41 moved records retain verifiable contents, with no app copy."""
        public = ROOT / 'PUBLIC_SOURCE_POLICY.json'
        if public.is_file():
            policy = json.loads(public.read_text('utf8'))
            self.assertEqual(policy['schema'], 'hrs-public-source-policy-v1')
            self.assertEqual(policy['private_history'], 'preserved-locally-not-published')
            self.assertFalse((ROOT / 'history').exists())
            self.assertEqual(DOCS.source_history_problems(ROOT), [])
            return
        manifest = json.loads((ROOT / 'history/ARCHIVE_MANIFEST.json').read_text('utf8'))
        self.assertEqual(len(manifest['files']), 41)
        for entry in manifest['files']:
            self.assertEqual(hashlib.sha256((ROOT / entry['archived']).read_bytes()).hexdigest(), entry['archived_sha256'])
        self.assertFalse((ROOT / 'app/docs/history/releases').exists())
        self.assertFalse((ROOT / 'app/docs/history/pf136_snapshot').exists())

    def test_portable_docs_do_not_require_source_history(self):
        """HAR-03: an independently extracted runtime need not carry source history."""
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(DOCS.source_history_problems(Path(folder)), [])

    def test_source_tree_must_not_silently_lose_history(self):
        """HAR-03: a source checkout missing its archive is a validation failure."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'tests').mkdir()
            self.assertTrue(DOCS.source_history_problems(root))

    def test_history_hash_and_path_escape_are_rejected(self):
        """HAR-03: source-only placement retains hash and path containment checks."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            history = root / 'history'
            history.mkdir()
            (history / 'old.md').write_bytes(b'original')
            entry = {'archived': 'history/old.md', 'archived_sha256': hashlib.sha256(b'original').hexdigest()}
            manifest = history / 'ARCHIVE_MANIFEST.json'
            manifest.write_text(json.dumps({'files': [entry]}), 'utf8')
            self.assertEqual(DOCS.source_history_problems(root), [])
            (history / 'old.md').write_bytes(b'tampered')
            self.assertTrue(DOCS.source_history_problems(root))
            entry['archived'] = '../outside.md'
            manifest.write_text(json.dumps({'files': [entry]}), 'utf8')
            self.assertTrue(DOCS.source_history_problems(root))


if __name__ == '__main__':
    unittest.main(verbosity=2)
