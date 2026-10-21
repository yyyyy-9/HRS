"""Run existing HRS contract/browser/document gates with durable per-command logs.

Public fixtures are project-owned synthetic data. Evidence stays outside source/.
The browser executable is supplied explicitly; no browser or dependency download.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify_result(returncode, output):
    """HAR-02: process failure wins; unittest counts outrank incidental log words."""
    runs = list(re.finditer(r'^Ran (\d+) tests?\b', output, re.M))
    summaries = list(re.finditer(r'^(?:OK|FAILED)(?: \(([^\n]*)\))?[ \t]*$', output, re.M))
    ran, summary = (runs[-1] if runs else None), (summaries[-1] if summaries else None)
    counts = dict(re.findall(r'([a-z ]+)=(\d+)', summary[1] or '')) if summary else {}
    counts = {key.strip(): int(value) for key, value in counts.items()}
    total = int(ran[1]) if ran else None
    skipped = counts.get('skipped', 0) if ran and summary else None
    markers = re.findall(r'^SKIP\b[^\r\n]*', output, re.M)
    reasons = re.findall(r"^.*\.\.\. skipped ['\"](.*?)['\"]\s*$", output, re.M)
    omitted = re.findall(r'^NOT_SELECTED source-only history: (\S+)', output, re.M)
    expected = counts.get('expected failures', 0)
    passed = (total - skipped - expected - counts.get('failures', 0) - counts.get('errors', 0) - counts.get('unexpected successes', 0)
              if total is not None and skipped is not None else None)
    reason = None
    if returncode != 0:
        status, reason = 'FAIL', 'Child process exited with code ' + str(returncode)
    elif total == 0:
        status, reason = 'NOT_RUN', 'No unittest cases were discovered'
    elif skipped:
        status, reason = 'SKIP', f'{skipped} of {total} unittest cases skipped'
    elif expected:
        status, reason = 'SKIP', f'{expected} expected failures do not satisfy required acceptance'
    elif markers and total is None:
        status, reason = 'SKIP', '; '.join(markers)
        reasons = markers
    else:
        status = 'PASS'
    return {'status': status, 'exit_code': returncode, 'reason': reason,
            'tests_run': total, 'tests_passed': passed, 'tests_skipped': skipped,
            'failures': counts.get('failures', 0) if summary else None,
            'errors': counts.get('errors', 0) if summary else None,
            'expected_failures': expected if summary else None, 'skip_reasons': reasons,
            'non_required_omissions': [{'test': name, 'status': 'NOT_RUN',
                                       'reason': 'Source-only history is not distributed in Full',
                                       'required_for_this_distribution': False} for name in omitted]}


def run_command(command, source, environment, timeout=120, live_log=None):
    try:
        if live_log is None:
            result = subprocess.run(command,cwd=source,env=environment,capture_output=True,text=True,encoding='utf8',timeout=timeout)
            output=result.stdout+result.stderr
        else:
            # Stream actual child output to evidence while it runs. This avoids
            # blind timeout waits and keeps one ordered UTF-8 diagnostic log.
            with Path(live_log).open('w',encoding='utf8') as stream:
                result=subprocess.run(command,cwd=source,env=environment,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
            output=Path(live_log).read_text('utf8')
        return output, classify_result(result.returncode, output)
    except subprocess.TimeoutExpired as error:
        def decoded(value):
            return value.decode('utf8', errors='replace') if isinstance(value, bytes) else value or ''
        output, outcome = (Path(live_log).read_text('utf8') if live_log else decoded(error.stdout)+decoded(error.stderr)) + '\n' + str(error), classify_result(124, '')
        outcome['reason'] = 'TIMEOUT: ' + str(timeout) + ' seconds'
    except OSError as error:
        output, outcome = str(error), classify_result(None, '')
        outcome.update(status='NOT_RUN', reason='Child process could not start: ' + str(error))
    return output, outcome


def overall_status(results, changed):
    if changed or any(item['status'] == 'FAIL' for item in results):
        return 'FAIL'
    if not results or any(item['status'] == 'NOT_RUN' for item in results):
        return 'NOT_RUN'
    if any(item['status'] == 'SKIP' for item in results):
        return 'SKIP'
    return 'PASS' if all(item['status'] == 'PASS' for item in results) else 'FAIL'


def selected_plan(source, node, python, *, contracts=True, browsers=True, groups=None, batch=True):
    from test_catalog import command_plan
    selection = groups or (['full'] if contracts and browsers else
                           ['contracts'] if contracts else ['browsers'] if browsers else [])
    return command_plan(source, node, python, selection, generated=True, batch=batch) if selection else []


def selected_commands(source, node, python, *, contracts, browsers):
    """Compatibility for existing Source/Full callers; the catalog owns selection."""
    return [(item['name'], item['command']) for item in selected_plan(
        source, node, python, contracts=contracts, browsers=browsers)]


def execute_plan(source, evidence, environment, plan, *, selection, node, browser=None, label='checks', complete=False):
    """The adapters only choose paths/omissions; receipts and outcome logic live here."""
    def fingerprints():
        return {p.relative_to(source).as_posix(): sha(p) for p in sorted(source.rglob('*'))
                if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts
                and p.suffix not in ('.pyc', '.pyo')}
    before = fingerprints()
    results = []
    for entry in plan:
        name, command = entry['name'], list(entry['command'])
        prerequisites=['reader_bundle','readable_docs','settings_generation']
        passed={item['name'] for item in results if item['status']=='PASS'}
        if name=='documentation' and set(prerequisites)<=passed:
            app=source/'app'
            reuse={'schema':'hrs-generated-gate-reuse-v1','app':str(app.resolve()),'passed':prerequisites,
                   'fingerprints':{p.relative_to(app).as_posix():sha(p) for p in app.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}}
            reuse_path=evidence/'generated_gate_reuse.json'
            reuse_path.write_text(json.dumps(reuse,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            command+=['--generated-receipt',str(reuse_path)]
        started = time.monotonic()
        log = evidence / (name + '.log')
        output, outcome = run_command(command,source,environment,timeout=600 if name=="python_browsers" else 180,live_log=log)
        log.write_text(output, encoding='utf8')
        item = {'name': name, 'command': command, 'cwd': str(source), **outcome,
                'required': True, 'tests': entry['tests'], 'elapsed_seconds': round(time.monotonic() - started, 3),
                'log': log.name, 'log_sha256': sha(log)}
        results.append(item)
        print(json.dumps({k: item[k] for k in ('name', 'status', 'exit_code', 'elapsed_seconds')}, ensure_ascii=False), flush=True)
    after = fingerprints()
    changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    overall = overall_status(results, changed)
    report = {'label': label, 'completed_utc': datetime.now(timezone.utc).isoformat(),
              'selection': selection, 'full_regression_complete': complete and overall == 'PASS',
              'source': str(source), 'source_fingerprints': before,
              'environment': {'python': sys.version, 'platform': platform.platform(),
                  'node': subprocess.run([node, '--version'], capture_output=True, text=True).stdout.strip(),
                  'browser': str(browser) if browser else None},
              'commands': results, 'source_changed_by_checks': changed,
              'overall': overall,
              'explicit_integrations_not_selected': [name for name in __import__('test_catalog').EXPLICIT_FEATURES if name not in selection],
              'scope': 'Selected catalogued HRS automated scenarios; features and execution boundaries are attached per command. Not a coverage percentage or Office/system acceptance',
              'legacy_chrome112_edge92': 'NOT_RUN', 'office_clipboard_vbs': 'NOT_RUN',
              'token_usage': None, 'token_usage_status': 'UNAVAILABLE'}
    (evidence / 'RESULTS.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('OVERALL', report['overall'], flush=True)
    return report



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--browser', type=Path)
    parser.add_argument('--label', default='checks')
    groups = parser.add_mutually_exclusive_group()
    groups.add_argument('--contracts-only', action='store_true')
    groups.add_argument('--browsers-only', action='store_true')
    groups.add_argument('--groups', nargs='+', help='Feature groups or retained aliases; see --plan')
    parser.add_argument('--plan', action='store_true', help='Print the deduplicated selection without execution')
    parser.add_argument('--individual-browsers', action='store_true', help='Diagnostic comparison: do not batch browser suites')
    args = parser.parse_args()
    source = args.source.resolve()
    node = os.environ.get('HRS_BRIDGE_NODE') or shutil.which('node')
    if not node and args.plan:
        node = 'node'
    if not node:
        parser.error('Node is required; no dependency is installed by this runner')
    try:
        plan = selected_plan(source, node, sys.executable, contracts=not args.browsers_only,
                             browsers=not args.contracts_only, groups=args.groups, batch=not args.individual_browsers)
    except ValueError as error:
        parser.error(str(error))
    selection = args.groups or (['contracts'] if args.contracts_only else ['browsers'] if args.browsers_only else ['full'])
    if args.plan:
        from test_catalog import FEATURES, ALIASES
        print(json.dumps({'groups': selection, 'available_features': {key:value[0] for key,value in FEATURES.items()},
                          'aliases': ALIASES, 'plan': plan}, ensure_ascii=False, indent=2))
        return 0
    if not args.evidence:
        parser.error('--evidence is required for execution')
    evidence = args.evidence.resolve()
    if evidence.is_relative_to(source):
        parser.error('Evidence must be outside the source tree')
    environment = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    environment['PLAYWRIGHT_NODEJS_PATH'] = str(node)
    environment['TEST_ARTIFACT_DIR'] = str(evidence / 'screens')
    requires_browser = any(test['kind'] == 'browser' for entry in plan for test in entry['tests'])
    if any(test['id']=='test_desktop_runtime' for entry in plan for test in entry['tests']):
        needed={'HRS_DESKTOP_LAYOUT':Path.is_dir,'HRS_ELECTRON':Path.is_file,
                'HRS_DESKTOP_PORTABLE':Path.is_file,'HRS_WORD_PANDOC':Path.is_file}
        if any(not os.environ.get(name) or not check(Path(os.environ[name])) for name,check in needed.items()):
            parser.error('Desktop integration requires HRS_DESKTOP_LAYOUT, HRS_ELECTRON, HRS_DESKTOP_PORTABLE and HRS_WORD_PANDOC; see README_TESTS.txt')
    if requires_browser and (not args.browser or not args.browser.is_file()):
        parser.error('Browser checks require --browser pointing to an installed Chromium executable')
    from test_catalog import execution_requirements
    if execution_requirements(plan):
        component=environment.get('HRS_WORD_SUPPORT')
        python=environment.get('HRS_WORD_PYTHON')
        bundle=environment.get('HRS_WORD_BUNDLE')
        ready=(component and Path(component).is_dir() and python and Path(python).is_file()) or (bundle and Path(bundle).is_dir())
        if not ready or not Path(environment.get('HRS_WORD_TEST_ENV','__missing__')).is_dir():
            parser.error('Native Word checks require matching HRS_WORD_SUPPORT/PYTHON (or HRS_WORD_BUNDLE) and HRS_WORD_TEST_ENV; see README_TESTS.txt')
    if args.browser:
        environment['CHROMIUM_PATH'] = str(args.browser.resolve())
    evidence.mkdir(parents=True, exist_ok=False)
    report=execute_plan(source,evidence,environment,plan,selection=selection,node=node,
                        browser=args.browser,label=args.label,complete='full' in selection)
    return 0 if report['overall']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
