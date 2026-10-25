"""Independent HRS HTML commands, using the original browser export/archive code.

Ordinary GUI use has no extra dependency. This optional command adapter needs
Playwright and an installed Chrome/Chromium/Edge; it never downloads a browser.
Inputs are copied into a private local session and never saved by the editor.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from asset_paths import asset_file


class HTMLCommandError(ValueError):
    def __init__(self,message,code='HTML_COMMAND_FAILED'):
        super().__init__(message);self.code=code


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _new_output(path):
    path = Path(path).resolve()
    if path.exists():
        raise HTMLCommandError('Output already exists; choose a new path: ' + str(path))
    if not path.parent.is_dir():
        raise HTMLCommandError('Output parent directory does not exist: ' + str(path.parent))
    return path


def _snapshot(project):
    from project_workspace import is_link
    project = Path(project).resolve()
    if not project.is_dir() or not (project / 'report.md').is_file():
        raise HTMLCommandError('Choose an HRS project containing report.md: ' + str(project),'SOURCE_UNREADABLE')
    paths = [project / 'report.md']
    if (project/'meta.json').exists():paths.append(project/'meta.json')
    assets = project / 'assets'
    if assets.exists():
        if not assets.is_dir() or is_link(assets):
            raise HTMLCommandError('Project assets must be a real directory')
        paths += sorted(assets.rglob('*'))
    result = {}
    for path in paths:
        if is_link(path):
            raise HTMLCommandError('Project source may not contain filesystem links: ' + str(path))
        if path.is_file():
            result[path.relative_to(project).as_posix()] = _sha(path.read_bytes())
    return result


@contextmanager
def browser_session(project=None, browser=None, theme=None):
    """One temporary real server/browser; no personal profile or project writes."""
    from studio import StudioServer, pick_browser
    from portable_host import PortableHandler, WindowSessions
    try:
        from playwright.sync_api import sync_playwright, Error as BrowserError
    except ImportError as error:
        raise HTMLCommandError('Install the optional CLI dependencies from requirements-dev.txt, or use the matching self-contained Full bundle','ENGINE_UNAVAILABLE') from error
    executable = str(browser or os.environ.get('CHROMIUM_PATH') or pick_browser() or '')
    if not executable or not Path(executable).is_file():
        raise HTMLCommandError('Specify --browser or CHROMIUM_PATH with a Chrome/Chromium/Edge executable','ENGINE_UNAVAILABLE')
    with tempfile.TemporaryDirectory(prefix='hrs-html-') as directory:
        folder = Path(directory)
        target = folder / 'project'
        (target / 'assets').mkdir(parents=True)
        if project:
            project = Path(project)
            shutil.copyfile(project / 'report.md', target / 'report.md')
            if (project / 'assets').is_dir():
                shutil.copytree(project / 'assets', target / 'assets', dirs_exist_ok=True)
        class QuietHandler(PortableHandler):
            def log_message(self, *args):
                pass
        server = StudioServer(('127.0.0.1', 0), target, folder / 'workspace')
        server.RequestHandlerClass = QuietHandler
        server.portable_lifecycle = WindowSessions('html-cli', enabled=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                client = playwright.chromium.launch(executable_path=executable, headless=True)
                try:
                    page = client.new_page(viewport={'width': 1366, 'height': 900}, device_scale_factor=2)
                    page.set_default_timeout(120000)
                    from color_theme import normalize as normalize_color
                    suffix='' if theme is None else '&theme='+normalize_color(theme)
                    page.goto('http://127.0.0.1:' + str(server.server_port) + '/web/index.html?programmatic=1'+suffix, wait_until='load')
                    page.wait_for_function('window.ReportStudioProgrammatic && window.ReportExportArchive')
                    yield page
                finally:
                    client.close()
        except BrowserError as error:
            raise HTMLCommandError(str(error),'BROWSER_ENGINE_FAILED') from error
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def export_html(project, output, *, browser=None, quality='original', source_mode='recompilable', include_pdf_originals=False, render_profile=None, accept_numbered_headings=False,theme=None):
    """Call the same buildExport used by the UI, with both existing preflights."""
    from report_contract import analyze
    from studio import audit_export
    project = Path(project).resolve()
    before = _snapshot(project)
    output = _new_output(output)
    if output.is_relative_to(project / 'assets'):
        raise HTMLCommandError('HTML output cannot be written inside source assets/')
    raw = (project / 'report.md').read_bytes()
    ir = analyze(raw.decode('utf8'), assets=project / 'assets')
    if not ir['ok']:
        raise HTMLCommandError('Source contract failed: ' + json.dumps(ir['diagnostics'], ensure_ascii=False))
    from render_profile import read as read_profile, normalize as normalize_profile, read_options, require_output
    profile=read_profile(project) if render_profile is None else normalize_profile(render_profile)
    diagnostics=require_output(ir,profile,accept_numbered_headings)
    options=read_options(project)
    from color_theme import read as read_color, normalize as normalize_color
    color=read_color(project) if theme is None else normalize_color(theme)
    with browser_session(project, browser,theme=color) as page:
        result = page.evaluate('''async request=>{
            const preferences=request.preferences;
            const api=window.ReportStudioProgrammatic;
            let timer;
            try{return await Promise.race([(async()=>{
                await api.ready();await api.open('legacy');
                return {html:await api.exportHTML(preferences),engine:api.schema,diagnostics:ReportProfile.plan(request.markdown,preferences.renderProfile).diagnostics};
            })(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('HRS HTML export timed out')),120000);})]);}
            finally{clearTimeout(timer);}
        }''', {'preferences':{'quality': quality, 'sourceMode': source_mode, 'includePdfOriginals': include_pdf_originals,'renderProfile':profile,'renderOptions':options,'acceptNumberedHeadings':accept_numbered_headings},'markdown':(project/'report.md').read_bytes().decode('utf8')})
    audit_export(result['html'])
    if before != _snapshot(project):
        raise HTMLCommandError('Project source changed while exporting; output was not committed')
    data = result['html'].encode('utf8')
    with output.open('xb') as stream:
        stream.write(data)
    return {'ok': True, 'operation': 'export-html', 'output': str(output), 'bytes': len(data),
            'sha256': _sha(data), 'source_unchanged': True, 'engine': result['engine'],
            'render_profile':profile,'render_options':options,'color_theme':color,'diagnostics':diagnostics,'conversion_model_api_calls': 0}


def recover_html(source, output, *, browser=None):
    """Recover the original source with the existing archive/hash/media checks."""
    from report_contract import analyze
    from studio import check_image, clean_asset_name
    source = Path(source).resolve()
    if not source.is_file():
        raise HTMLCommandError('HTML input does not exist: ' + str(source))
    if source.stat().st_size > 36 * 1024 * 1024:
        raise HTMLCommandError('HTML input exceeds the existing 36 MiB archive limit')
    output = _new_output(output)
    raw = source.read_bytes()
    document = raw.decode('utf8')
    with browser_session(browser=browser) as page:
        restored = page.evaluate('''async html=>{
            // A template is fully inert, including images/frames. Imported HTML
            // is data: only the original archive/hash reader is invoked.
            const template=document.createElement('template');template.innerHTML=html;
            const doc=template.content;
            const source=doc.getElementById('report-source');
            if(!source)throw Error('Missing HRS archive');
            return ReportExportArchive.readArchive(JSON.parse(source.textContent),doc);
        }''', document)
    markdown = restored['markdown'].encode('utf8')
    hashes = {}
    with tempfile.TemporaryDirectory(prefix='hrs-html-recovery-', dir=output.parent) as directory:
        staged = Path(directory) / 'project'
        (staged / 'assets').mkdir(parents=True)
        (staged / 'report.md').write_bytes(markdown)
        if 'renderProfile' in restored:
            from render_profile import normalize_options
            from color_theme import normalize as normalize_color
            (staged/'meta.json').write_text(json.dumps({'render_profile':restored['renderProfile'],'render_options':normalize_options(restored.get('renderOptions')),'color_theme':normalize_color(restored.get('colorTheme'))})+'\n',encoding='utf8')
        for name, encoded in restored['assets'].items():
            clean_asset_name(name)
            data = base64.b64decode(encoded, validate=True)
            check_image(Path(name).suffix.lower(), data)
            target=asset_file(staged/'assets',name)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            hashes['assets/' + name] = _sha(data)
        ir = analyze(restored['markdown'], assets=staged / 'assets')
        if not ir['ok']:
            raise HTMLCommandError('Recovered source failed the existing contract: ' + str(ir['diagnostics']))
        if source.read_bytes() != raw:
            raise HTMLCommandError('HTML input changed while recovering')
        staged.rename(output)
    return {'ok': True, 'operation': 'recover-html', 'output': str(output),
            'markdown_sha256': _sha(markdown), 'assets': hashes,
            'unique_blobs': len(set(hashes.values())), 'diagnostics': ir['diagnostics'],
            'source_unchanged': True, 'conversion_model_api_calls': 0}


def check_project(source,*,browser=None,render_profile=None):
    """Full text/asset preflight through the GUI's existing Marked model."""
    from report_contract import analyze
    from render_profile import read as read_profile,normalize,read_options
    project=Path(source).resolve()
    if project.is_file():
        if project.name!='report.md':raise HTMLCommandError('Choose report.md or its HRS project folder')
        project=project.parent
    before=_snapshot(project)
    text=(project/'report.md').read_bytes().decode('utf8')
    ir=analyze(text,assets=project/'assets')
    profile=read_profile(project) if render_profile is None else normalize(render_profile)
    with browser_session(project,browser) as page:
        result=page.evaluate('''async request=>{
          const api=ReportStudioProgrammatic;await api.ready();await api.open('legacy');
          return api.check(request);
        }''',{'renderProfile':profile,'renderOptions':read_options(project),'expectSourceSha256':_sha(text.encode('utf8'))})
    seen={(d['code'],d.get('start'),d.get('end')) for d in result['diagnostics']}
    for diagnostic in ir['diagnostics']:
        key=(diagnostic['code'],diagnostic.get('start'),diagnostic.get('end'))
        if key not in seen:result['diagnostics'].append(diagnostic);seen.add(key)
    if before!=_snapshot(project):raise HTMLCommandError('STALE_SNAPSHOT: source/assets changed during check')
    valid=not any(d['severity']=='error' for d in result['diagnostics'])
    result.update(operation='check',ok=True,valid=valid,safeToCompile=valid and profile=='engineering',source_unchanged=True,
                  source_snapshot=ir['source_snapshot'],conversion_model_api_calls=0)
    result['preflight'].update(assets_checked=True,downstream_verified=False)
    return result


def check_main(argv=None):
    parser=argparse.ArgumentParser(description='Complete HRS text/asset checks; no output document or source writes')
    parser.add_argument('source',type=Path)
    parser.add_argument('--browser',type=Path)
    parser.add_argument('--render-profile',choices=('free','engineering'))
    args=parser.parse_args(argv)
    try:
        result=check_project(args.source,browser=args.browser,render_profile=args.render_profile)
    except Exception as error:
        code=getattr(error,'code','SOURCE_UNREADABLE' if isinstance(error,OSError) else 'CHECK_FAILED')
        result={'ok':False,'operation':'check','valid':False,'safeToCompile':False,
                'preflight':{'complete':False},'code':code,'error':str(error)}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result.get('ok') and result.get('valid') else 1


def main(argv=None):
    # Machine receipts are always UTF-8, including Windows redirected stdout.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export', help='Export one report.md/assets project through the original HRS engine')
    recover = sub.add_parser('recover', help='Recover a recompilable HRS HTML into a new project')
    for command in (export, recover):
        command.add_argument('source', type=Path)
        command.add_argument('--output', type=Path, required=True)
        command.add_argument('--browser', type=Path)
    export.add_argument('--quality', choices=('compact', 'standard', 'print', 'original'), default='original')
    export.add_argument('--source-mode', choices=('recompilable', 'reading'), default='recompilable')
    export.add_argument('--include-pdf-originals', action='store_true')
    export.add_argument('--render-profile',choices=('free','engineering'),help='Override only this output; keep project/source unchanged')
    export.add_argument('--accept-numbered-headings',action='store_true',help='Accept the manual heading number notice for this input snapshot')
    from color_theme import NAMES
    export.add_argument('--theme',choices=('default',*NAMES),help='Override this output palette only; default means original blue')
    args = parser.parse_args(argv)
    try:
        if args.command == 'export':
            result = export_html(args.source, args.output, browser=args.browser,
                                 quality=args.quality, source_mode=args.source_mode,
                                 include_pdf_originals=args.include_pdf_originals,render_profile=args.render_profile,accept_numbered_headings=args.accept_numbered_headings,theme=args.theme)
        else:
            result = recover_html(args.source, args.output, browser=args.browser)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({'ok': False, 'operation': args.command, 'code':getattr(error,'code','HTML_COMMAND_FAILED'), 'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
