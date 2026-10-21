"""Run an explicit set once, without importing unrelated browser suites."""
from pathlib import Path
import argparse
import os
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', nargs='+', required=True)
    parser.add_argument('--reuse-browser', action='store_true')
    parser.add_argument('--omit-source-history', action='store_true',
                        help='Full only: history is absent; report the excluded source case')
    args = parser.parse_args()
    os.environ.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    sys.path.insert(0, str(ROOT / 'tests'))
    os.chdir(ROOT)
    cases, seen = [], set()
    omitted = 'test_doc_layout_contract.DocumentLayout.test_all_approved_archives_survive_outside_runtime'
    for filename in args.files:
        filename, _, selector = filename.partition('::')
        path = (ROOT / filename).resolve(strict=True)
        if path.parent != ROOT / 'tests' or not path.name.startswith('test_'):
            parser.error('Select test modules directly inside tests/')
        suite = unittest.defaultTestLoader.loadTestsFromName(path.stem + ('.' + selector if selector else ''))
        loaded = list(flatten(suite))
        if not loaded:
            parser.error('No unittest cases in selected module: ' + filename)
        for case in loaded:
            if args.omit_source_history and case.id() == omitted:
                print('NOT_SELECTED source-only history:', omitted, flush=True)
                continue
            if case.id() not in seen:
                cases.append(case)
                seen.add(case.id())
    if not cases:
        parser.error('No cases selected; empty selection is not success')
    if args.reuse_browser:
        os.environ['HRS_TEST_REUSE_BROWSER'] = '1'
    try:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(cases))
    finally:
        if args.reuse_browser:
            from browser_support import close_shared_browser
            close_shared_browser()
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
