"""Generate the local v1 recipe or a checksum-pinned submission from one identity.

Distribution metadata comes from pyproject.toml; versions come from release.json.
This tool neither downloads sources nor submits or uploads packages.
"""
from pathlib import Path
import argparse
import json
import re
import sys
import tomllib
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from release_info import load_release


TEMPLATE = '''schema_version: 1

context:
  version: @VERSION@
  python_min: @PYTHON_MIN@

package:
  name: @NAME@
  version: ${{ version }}

source:
@SOURCE@

build:
  number: 0
  noarch: python
  script: python -m pip install . -vv --no-deps --no-build-isolation
  python:
    entry_points:
@ENTRY_POINTS@

requirements:
  host:
    - python ${{ python_min }}.*
    - pip
@BUILD_REQUIRES@
  run:
    - python >=${{ python_min }}

tests:
  - python:
      python_version:
        - ${{ python_min }}.*
        - "*"
      imports:
        - @IMPORT@
      pip_check: true
  - requirements:
      run:
        - python ${{ python_min }}.*
    script:
      - hrs --version
      - hrs info
      - python -m @IMPORT@ --version
      - @IDENTITY_TEST@
      - @RESOURCE_TEST@

about:
  homepage: @REPOSITORY@
  summary: @SUMMARY@
  description: |
    HRS is a local Markdown report editor for free notes and engineering reports.
    The package includes the local web application, offline frontend assets and
    the hrs command. It binds to 127.0.0.1 and keeps user state outside the
    installation. Word export requires separate optional native components.
  license: @LICENSE@
  license_file:
@LICENSE_FILES@
  repository: @REPOSITORY@
  documentation: @DOCUMENTATION@

extra:
  recipe-maintainers:
    - yyyyy-9
'''


def render(root=ROOT, *, source_url=None, source_sha256=None):
    data = tomllib.loads((root / 'pyproject.toml').read_text('utf8'))
    project = data['project']
    identity = load_release(root / 'app/release.json')
    minimum = re.fullmatch(r'>=(\d+\.\d+)', project['requires-python'])
    if minimum is None:
        raise ValueError('Conda Python range needs an explicit mapping')
    source = '  path: ../..'
    if source_url is not None or source_sha256 is not None:
        url = urlsplit(source_url or '')
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or not re.fullmatch(r'[a-f0-9]{64}', source_sha256 or '')):
            raise ValueError('Release source requires an HTTPS URL and SHA256')
        source = '  url: ' + json.dumps(source_url) + '\n  sha256: ' + source_sha256
    module = project['scripts']['hrs'].split(':')[0].split('.')[0]
    identity_test = ("from importlib.metadata import version; from " + module +
        ".release_info import load_release; assert version(" + repr(project['name']) +
        ") == load_release()['python_version'] == '${{ version }}'")
    resource_test = ("import " + module + "; from " + module + ".release_info import SOURCE_SPEC; from pathlib import Path; p=Path(" + module +
        ".__file__).parent; assert all((p/n).is_file() for n in "
        "['MANIFEST.json','web/app.js','web/help.html','LICENSE','COPYRIGHT',SOURCE_SPEC])")
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    fields = {
        'VERSION': quote(identity['python_version']), 'PYTHON_MIN': quote(minimum[1]),
        'NAME': project['name'], 'SOURCE': source, 'IMPORT': module,
        'ENTRY_POINTS': '\n'.join('      - ' + key + ' = ' + value for key, value in project['scripts'].items()),
        'BUILD_REQUIRES': '\n'.join('    - ' + re.sub(r'(?<=[\w.-])(?=[<>=!~])', ' ', value, count=1)
                                   for value in data['build-system']['requires']),
        'IDENTITY_TEST': quote('python -c "' + identity_test + '"'),
        'RESOURCE_TEST': quote('python -c "' + resource_test + '"'),
        'REPOSITORY': quote(project['urls']['Repository']),
        'DOCUMENTATION': quote(project['urls']['Repository'] + '#readme'),
        'SUMMARY': quote(project['description']), 'LICENSE': project['license'],
        'LICENSE_FILES': '\n'.join('    - ' + value for value in project['license-files']),
    }
    result = TEMPLATE
    for key, value in fields.items():
        result = result.replace('@' + key + '@', value)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--write', action='store_true', help='Update the generated local recipe')
    mode.add_argument('--check', action='store_true', help='Reject a stale local recipe')
    parser.add_argument('--source-url')
    parser.add_argument('--source-sha256')
    parser.add_argument('--output', type=Path, help='Create a new checksum-pinned submission recipe')
    args = parser.parse_args()
    if bool(args.output) != bool(args.source_url or args.source_sha256) or args.output and (args.write or args.check):
        parser.error('Submission requires --output, --source-url and --source-sha256; no --write/--check')
    try:
        text = render(source_url=args.source_url, source_sha256=args.source_sha256)
    except ValueError as error:
        parser.error(str(error))
    target = args.output or ROOT / 'packaging/conda/recipe.yaml'
    if args.check:
        if not target.is_file() or target.read_text('utf8') != text:
            parser.exit(1, 'Stale Conda recipe; run tools/build_conda_recipe.py --write\n')
        print('Conda recipe matches canonical metadata')
    elif args.write or args.output:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x' if args.output else 'w', encoding='utf8', newline='\n') as stream:
            stream.write(text)
        print('Wrote ' + str(target))
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
