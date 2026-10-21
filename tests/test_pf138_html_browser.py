"""HTML-01: real-service preview, offline export/recovery, safe source editing and reading packs."""
import base64
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import zipfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(ROOT))
from studio import StudioServer, audit_export
from portable_host import PortableHandler, WindowSessions

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
SOURCE = '''# Safe HTML report

Water H<sub>2</sub>O and x<sup>2</sup>, <u>underline</u>, <mark>mark</mark>, <kbd>Ctrl</kbd>, <span style="color:red">red text</span><br>next line.

<div style="display:flex;flex-wrap:wrap;gap:16px;border:1px solid #b5aacd;padding:24px;border-radius:16px">
<div style="flex:1 1 240px;background-color:#554271;color:#ffffff;padding:24px">Card A</div>
<div style="flex:1 1 220px;background-color:#f3f0f8;padding:24px">Card B</div>
<details><summary>More</summary><p>Safe detail</p></details>
<table><tr><td>HTML display table</td></tr></table>
<img src="assets/pixel.png" alt="HTML local image" width="20" onerror="window.HRS_UNTRUSTED=1">
<script>window.HRS_UNTRUSTED=1</script>
<iframe src="https://untrusted.invalid/frame"></iframe>
<svg onload="window.HRS_UNTRUSTED=1"><a href="javascript:alert(1)">bad</a></svg>
<a href="javas&#99;ript:window.HRS_UNTRUSTED=1">Unsafe link</a>
<span style="position:fixed;z-index:99999;background-image:url(https://untrusted.invalid/pixel);color:blue" id="modal-layer" class="report-figure-wrap" data-figure-id="fig-fake" onclick="window.HRS_UNTRUSTED=1">Safe remaining text</span>
</div>

`<sub>literal code</sub>`

Tail paragraph.

| Formula | Value |
| --- | --- |
| H<sub>2</sub>O | x<sup>2</sup> |

- [x] Completed task
- [ ] Pending task
'''


def main():
    with tempfile.TemporaryDirectory(prefix='hrs-safe-html-') as directory:
        folder = Path(directory)
        project = folder / 'project'
        (project / 'assets').mkdir(parents=True)
        # CRLF and non-ASCII source are intentional: display must not normalize storage.
        raw = (SOURCE + '\n中文原稿。\n').replace('\n', '\r\n').encode('utf8')
        (project / 'report.md').write_bytes(raw)
        (project / 'assets/pixel.png').write_bytes(PNG)
        server = StudioServer(('127.0.0.1', 0), project, folder / 'workspace')
        server.RequestHandlerClass = PortableHandler
        server.portable_lifecycle = WindowSessions('safe-html-test', enabled=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ['CHROMIUM_PATH'], headless=True)
                page = browser.new_page(viewport={'width': 1400, 'height': 900})
                external_requests = []
                page.on('request', lambda req: external_requests.append(req.url) if 'untrusted.invalid' in req.url else None)
                page.goto('http://127.0.0.1:' + str(server.server_port) + '/web/index.html?programmatic=1')
                page.evaluate("async()=>{await ReportStudioProgrammatic.ready();await ReportStudioProgrammatic.open('legacy');}")
                preview = page.locator('#preview-content')
                # Safe HTML preserves both inline semantics and the supplied card layout.
                assert preview.locator('sub').count() == 2, 'HTML subscript must render in prose and GFM cells'
                assert preview.locator('sup,u,mark,kbd').count() == 5
                assert preview.locator('details > summary').filter(has_text='More').inner_text() == 'More'
                assert preview.locator('[style*="display: flex"]').count() == 1
                assert preview.locator('[style*="display: flex"]').evaluate("e=>getComputedStyle(e).borderTopWidth") == '1px'
                assert preview.locator('img[alt="HTML local image"]').evaluate('(e)=>e.complete&&e.naturalWidth>0')
                assert preview.locator('table').count() == 2
                assert preview.locator('.report-table-wrap[data-pipe-table]').count() == 1
                assert preview.locator('.report-figure-wrap,[data-table-id]').count() == 0, 'HTML is display content, not numbered HRS objects'
                assert preview.locator('code').filter(has_text='<sub>literal code</sub>').count() == 1
                # RC3-04 explicitly enables source-mapped GFM tasks in the
                # editor. Free exported controls have local reading state; read-pack controls stay disabled.
                assert preview.locator('input.hrs-task-checkbox[checked]:enabled').count() == 1
                assert page.evaluate('window.HRS_UNTRUSTED || 0') == 0
                assert preview.locator('script,iframe,svg,[onclick],[onerror],[data-figure-id]').count() == 0
                assert preview.locator('[style*="position"],[style*="url("],a[href^="javascript:"]').count() == 0
                assert not external_requests, external_requests
                # Malformed foreign markup, encoded URLs and control impersonation
                # cannot escape the same fresh-node boundary.
                attacks = [
                    '<math><mtext><table><mglyph><style><!--</style><img title="--><img src=x onerror=alert(1)>">',
                    '<svg><foreignObject><div><img src=x onerror=alert(1)></div></foreignObject></svg>',
                    '<a href="jav&#x09;ascript:alert(1)">link</a>',
                    '<form><input name="ReportStudioProgrammatic"></form>',
                    '<span id="modal-layer" class="report-figure-wrap" data-figure-id="fig-fake" contenteditable="true">text</span>',
                    '<span style="background-image:u\\72l(https://untrusted.invalid/image);color:red">text</span>',
                ]
                for attack in attacks:
                    unsafe = page.evaluate('''html=>{
                        const box=document.createElement('div');
                        box.append(ReportSafeHTML.fragment(html,{images:false}));
                        return box.querySelectorAll('script,style,iframe,svg,math,form,input,[id],[onclick],[onerror],[contenteditable],[data-figure-id],a[href^="javascript:"],[style*="url("]').length;
                    }''', attack)
                    assert unsafe == 0, attack
                # HTML-containing paragraphs use the existing source modal, never a lossy DOM serializer.
                html_paragraph = preview.locator('.doc-block').filter(has=page.locator('sub')).first
                assert html_paragraph.get_attribute('data-editable') == '0'
                html_paragraph.locator('sub').dblclick()
                page.locator('#modal-layer:not([hidden])').wait_for()
                assert '<sub>2</sub>' in page.locator('#modal-body textarea').input_value()
                page.locator('#modal-cancel').click()
                exported = page.evaluate("()=>ReportStudioProgrammatic.exportHTML({quality:'original',sourceMode:'recompilable'})")
                audit_export(exported)
                restored = page.evaluate('''async html=>{
                    const doc=new DOMParser().parseFromString(html,'text/html');
                    return ReportExportArchive.readArchive(JSON.parse(doc.getElementById('report-source').textContent),doc);
                }''', exported)
                assert restored['markdown'].encode('utf8') == raw
                assert base64.b64decode(restored['assets']['pixel.png']) == PNG
                offline = folder / 'report.html'
                offline.write_bytes(exported.encode('utf8'))
                reader = browser.new_page(viewport={'width': 1400, 'height': 900})
                reader.goto(offline.as_uri())
                assert reader.locator('main sub').first.inner_text() == '2'
                assert reader.locator('main details summary').filter(has_text='More').inner_text() == 'More'
                assert reader.locator('main img').evaluate('(e)=>e.complete&&e.naturalWidth>0')
                assert reader.evaluate('window.HRS_UNTRUSTED || 0') == 0
                assert reader.locator('main input[type="checkbox"][checked]:enabled').count() == 1
                # A single sanitizer also protects the existing read-only ZIP viewer.
                memory = io.BytesIO()
                with zipfile.ZipFile(memory, 'w') as archive:
                    archive.writestr('guide.md', '# Read pack\n\n[Jump](#destination)\n\n<div style="display:flex"><span style="color:red">Read pack</span></div>\n\n## Destination\n\nH<sub>2</sub>O\n\n![external](https://untrusted.invalid/image.png)\n\n| Center |\n| :---: |\n| value |\n')
                page.locator('#menu-open > summary').click()
                page.locator('#btn-readpack').click()
                page.locator('#file-reader-zip').set_input_files({'name':'guide.zip','mimeType':'application/zip','buffer':memory.getvalue()})
                page.locator('#reader-article sub').wait_for()
                assert page.locator('#reader-article sub').inner_text() == '2'
                assert page.locator('#reader-article [style*="display: flex"]').count() == 1
                assert page.locator('#reader-article a').get_attribute('href') == '#hrs-pack-heading-destination'
                assert page.locator('#reader-article #hrs-pack-heading-destination').count() == 1
                assert page.locator('#reader-article .reader-warning').count() == 1
                assert page.locator('#reader-article th').evaluate('e=>getComputedStyle(e).textAlign') == 'center'
                page.locator('#reader-close').click()
                assert (project / 'report.md').read_bytes() == raw
                assert (project / 'assets/pixel.png').read_bytes() == PNG
                browser.close()
                # API-02 exercises the public standalone CLI, with no bridge import.
                for arguments in (
                    ['export', str(project), '--output', str(folder / 'cli.html')],
                    ['recover', str(folder / 'cli.html'), '--output', str(folder / 'cli-project')],
                ):
                    command = [sys.executable, '-X', 'utf8', '-B', str(ROOT / 'html_cli.py'), *arguments,
                               '--browser', os.environ['CHROMIUM_PATH']]
                    result = subprocess.run(command, capture_output=True, text=True, encoding='utf8', timeout=150)
                    assert result.returncode == 0, result.stdout + result.stderr
                    assert json.loads(result.stdout)['ok']
                assert (folder / 'cli-project/report.md').read_bytes() == raw
                assert (folder / 'cli-project/assets/pixel.png').read_bytes() == PNG
                # Recovery reads archive data in an inert template. Even an
                # added HTML script that would corrupt the archive never runs.
                untrusted = exported.replace('</body>', '<script>document.getElementById("report-source").textContent="corrupt"</script><img src="https://untrusted.invalid/recover"></body>')
                (folder / 'untrusted.html').write_bytes(untrusted.encode('utf8'))
                result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(ROOT / 'html_cli.py'),
                    'recover', str(folder / 'untrusted.html'), '--output', str(folder / 'untrusted-project'),
                    '--browser', os.environ['CHROMIUM_PATH']], capture_output=True, text=True, encoding='utf8', timeout=150)
                assert result.returncode == 0, result.stdout + result.stderr
                assert (folder / 'untrusted-project/report.md').read_bytes() == raw
                print('BROWSER PF13.8 HTML: inline/block/style, local image audit, no scripts/network/object spoofing, source modal, exact CRLF/source/assets, offline export/recover and readpack PASS')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
