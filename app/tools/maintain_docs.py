#!/usr/bin/env python3
"""Read-only documentation hygiene / release consistency check.

This does NOT delete reports, user assets, or even historical documents.
The original frozen nine stay in source history/frozen_app/. Complete stage records
are source-only history/, optional for an independently extracted runtime.

Usage: python tools/maintain_docs.py --check
"""
from __future__ import annotations
import argparse,hashlib,re,sys,subprocess,shutil,json
from html import unescape
from urllib.parse import unquote,urlsplit
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs'
sys.path.insert(0,str(ROOT))
from release_info import load_release
RELEASE=load_release()
ACTIVE=['CURRENT_STATUS.md','SHORT_TERM_PLAN.md','LONG_TERM_ROADMAP.md','PROJECT_GOALS.md',
        'USER_GUIDE.md','CHANGELOG_READABLE.md','MODULE_OVERVIEW.md','WORD_COMPILER_HANDOFF.md',
        'USER_GUIDE_START_HERE.md','IMAGE_GROUP_AND_LIST_SPEC.md',
        'DOC_MAINTENANCE.md','HISTORY_INDEX.md']


def source_history_problems(source:Path)->list[str]:
 problems=[]
 history=(source/'history').resolve()
 manifest=history/'ARCHIVE_MANIFEST.json'
 if not manifest.is_file():
  policy=source/'PUBLIC_SOURCE_POLICY.json'
  if policy.is_file():
   try:
    data=json.loads(policy.read_text('utf8'))
    if data.get('schema')=='hrs-public-source-policy-v1' and data.get('private_history')=='preserved-locally-not-published' and not history.exists():return []
   except (ValueError,OSError):pass
  return ['Missing source-only document archive manifest'] if (source/'tests').is_dir() else []
 try:
  data=json.loads(manifest.read_text('utf8'))
  for entry in data['files']+data.get('maintenance_files',[]):
   saved=(source/entry['archived']).resolve()
   if not saved.is_relative_to(history) or not saved.is_file():
    problems.append('Unsafe/missing source archive: '+entry['archived']);continue
   if hashlib.sha256(saved.read_bytes()).hexdigest()!=entry['archived_sha256']:
    problems.append('Source archive changed: '+entry['archived'])
 except (KeyError,TypeError,ValueError,OSError) as exc:
  problems.append('Invalid source archive manifest: '+str(exc))
 return problems


def active_heading_version_problem(text:str)->bool:
 # Release metadata and generated page headers own the displayed identity.
 # An unversioned canonical heading is valid; if it names a release, it must
 # match. Historical evidence in the body remains bound to its old version.
 first=text.splitlines()[0] if text.splitlines() else ''
 match=re.search(r'\bv(\d+\.\d+\.\d+)(?:\s+(R\d+))?',first)
 return bool(match and ('v'+match[1]!=RELEASE['version_label'] or match[2] and match[2]!=RELEASE['package_revision']))


def validate(*,generated_verified=False)->list[str]:
 problems=[]
 for name in ACTIVE:
  if not (DOC/name).is_file():problems.append('Missing canonical Markdown: docs/'+name)
 for name in ('CURRENT_STATUS.md','SHORT_TERM_PLAN.md','LONG_TERM_ROADMAP.md','PROJECT_GOALS.md'):
  file=DOC/name
  if file.is_file() and active_heading_version_problem(file.read_text('utf8')):problems.append('Old version text in '+name)
 changelog=DOC/'CHANGELOG_READABLE.md'
 if changelog.is_file() and RELEASE['version_label'] not in changelog.read_text('utf8'):
  problems.append('Current release is missing from CHANGELOG_READABLE.md')
 if not (ROOT/'README.md').is_file() or 'docs/CURRENT_STATUS.md' not in (ROOT/'README.md').read_text('utf8'):
  problems.append('README must link current state, rather than historical status only')
 for item in list(DOC.glob('*.md'))+list(ROOT.glob('*.md')):
  if item.name=='工程报告源格式_v1_规范.md':continue  # canonical technical source specification
  if re.search(r'(?:[_-](?:updated|draft|tmp|temp|final\d+|v\d+)|更新稿|中间稿|临时)',item.name,re.I):
   problems.append('Intermediate Markdown in active directory: '+item.relative_to(ROOT).as_posix())
 # All historical bytes are source-only and checked by the archive manifest.
 problems.extend(source_history_problems(ROOT.parent))
 if not (ROOT.parent/'AGENTS.md').is_file():problems.append('Missing source/portable root AGENTS.md')
 # Active documentation links are not silently allowed to go stale.
 # Bare file references in code fences are not links and are not included.
 for document in [ROOT/'README.md',ROOT/'工程报告源格式_v1_规范.md',*(DOC/name for name in ACTIVE)]:
  if not document.exists():continue
  value=document.read_text('utf8')
  value=re.sub(r'^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\1[ \t]*$', '',value,flags=re.M)
  value=re.sub(r'`[^`\n]*`','',value)  # ignore Markdown syntax samples in inline code
  for link in re.findall(r'(?<!!)\[[^]\n]+\]\(([^)\s]+)\)',value):
   if link.startswith(('#','http:','https:','mailto:','data:')):continue
   base=link.split('#',1)[0].split('?',1)[0]
   if not base:continue
   target=(document.parent/base).resolve()
   if not target.is_file():problems.append('Broken documentation link: '+document.relative_to(ROOT).as_posix()+' -> '+base)

 reader=ROOT/'web/report_reader.js'
 if reader.exists():
  script=reader.read_text('utf8')
  for file in ['web/help.html','web/CHANGELOG_READABLE.html','web/MODULE_OVERVIEW.html','web/WORD_COMPILER_HANDOFF.html',
               'docs/MODULE_OVERVIEW.html',
               'docs/USER_GUIDE.html','docs/CHANGELOG_READABLE.html','docs/WORD_COMPILER_HANDOFF.html',
               'docs/CURRENT_STATUS.html','docs/SHORT_TERM_PLAN.html','docs/LONG_TERM_ROADMAP.html']:
   doc=ROOT/file
   if not doc.is_file():problems.append('Offline readable document missing: '+file);continue
   html=doc.read_text('utf8')
   matches=re.findall(r'<script id="hrs-reader-runtime">([\s\S]*?)</script>',html)
   if len(matches)!=1 or matches[0]!=script:problems.append('Offline document has stale first-party reader: '+file)
   if '<html lang="zh-CN"' not in html or '<div class="docs-shell"' not in html:
    problems.append('Offline document layout incomplete: '+file)
   md_name={'web/help.html':'USER_GUIDE.md','web/CHANGELOG_READABLE.html':'CHANGELOG_READABLE.md',
            'web/MODULE_OVERVIEW.html':'MODULE_OVERVIEW.md','web/WORD_COMPILER_HANDOFF.html':'WORD_COMPILER_HANDOFF.md'}
   source=DOC/md_name.get(file,'USER_GUIDE.md' if file=='docs/USER_GUIDE.html' else Path(file).name.replace('.html','.md'))
   if source.is_file():
    hashmark=re.search(r'<meta name="hrs-markdown-sha256" content="([a-f0-9]{64})">',html)
    if not hashmark or hashmark[1]!=hashlib.sha256(source.read_bytes()).hexdigest():
     problems.append('Readable HTML no longer matches canonical Markdown: '+file)
   if re.search(r'<img\s+[^>]*src="(?:https?:|file:)',html,re.I):
    problems.append('Readable HTML contains external image: '+file)
   # Check every local target, including Markdown/JSON, in both output scopes.
   for href in re.findall(r'<a\b[^>]*href="([^"]+)"',html.split('<script id="hrs-reader-runtime">')[0],re.I):
    link=urlsplit(unescape(href))
    if link.scheme or link.netloc:continue
    target=(doc.parent/unquote(link.path)).resolve() if link.path else doc
    if not target.is_relative_to(ROOT.resolve()) or not target.is_file():
     problems.append('Broken generated HTML navigation: '+file+' -> '+href)
    elif link.fragment and target.suffix=='.html' and not re.search(r'\bid="'+re.escape(unquote(link.fragment))+'"',target.read_text('utf8')):
     problems.append('Broken generated HTML anchor: '+file+' -> '+href)
 # Full byte-for-byte deterministic regeneration check when Node is installed.
 # Portable end users need no Node; Markdown hashes and embedded reader still
 # get checked by the Python-only path above.
 if not generated_verified and shutil.which('node'):
  bundle=ROOT/'tools/build_reader_bundle.js'
  result=subprocess.run(['node',str(bundle),'--check'],capture_output=True,text=True,cwd=ROOT)
  if result.returncode!=0:problems.append('Standalone reader bundle differs from canonical modules: '+(result.stderr.strip() or result.stdout.strip())[:250])
 builder=ROOT/'tools/build_readable_docs.js'
 if not builder.is_file():problems.append('Missing readable docs builder')
 elif not generated_verified and shutil.which('node'):
  check=subprocess.run(['node',str(builder),'--check'],capture_output=True,text=True,cwd=ROOT)
  if check.returncode!=0:problems.append('Readable docs rebuild differs: '+(check.stderr.strip() or check.stdout.strip())[:300])
 module=DOC/'MODULE_CATALOG.json'
 if module.is_file() and RELEASE['release'].removeprefix('v') not in module.read_text('utf8'):
  problems.append('Module catalog release identity mismatch')
 settings_builder=ROOT/'tools/build_settings.js'
 if not generated_verified and shutil.which('node'):
  check=subprocess.run(['node',str(settings_builder),'--check'],capture_output=True,text=True,cwd=ROOT)
  if check.returncode:problems.append('Browser product settings are stale: '+check.stderr[:200])
 # Freeze the human-readable synthetic engineering report and its IR example
 # together. This avoids shipping an obsolete semantic example to a future Agent.
 source=DOC/'IR_EXAMPLE_SOURCE.md'; sample=DOC/'IR_EXAMPLE.json'
 if not source.is_file() or not sample.is_file():
  problems.append('Missing synthetic report source or canonical IR')
 else:
  sys.path.insert(0,str(ROOT))
  from report_contract import analyze
  expected=analyze(source.read_text('utf8'))
  if not expected['ok']:problems.append('Synthetic report source fails the current contract')
  try:
   if json.loads(sample.read_text('utf8'))!=expected:
    problems.append('IR_EXAMPLE.json differs from its Markdown source and live parser')
  except (ValueError,UnicodeError) as exc:
   problems.append('Synthetic IR example invalid: '+str(exc))
 return problems

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--check',action='store_true',required=True)
 parser.add_argument('--generated-receipt',type=Path,help='Runner-only: reuse successful gates bound to current App fingerprints')
 args=parser.parse_args()
 verified=False
 if args.generated_receipt:
  receipt=json.loads(args.generated_receipt.read_text('utf8'))
  actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
  verified=(receipt.get('schema')=='hrs-generated-gate-reuse-v1' and receipt.get('app')==str(ROOT.resolve()) and
            receipt.get('passed')==['reader_bundle','readable_docs','settings_generation'] and receipt.get('fingerprints')==actual)
  if not verified:parser.error('Generated gate receipt is stale or incomplete')
 failures=validate(generated_verified=verified)
 for problem in failures:print('ERROR:',problem,file=sys.stderr)
 if failures:raise SystemExit(1)
 print(RELEASE['release']+' documentation audit OK:',len(ACTIVE),'canonical files, source/frozen history, links, generated offline HTML and reader')
