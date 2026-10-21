"""Read the release identity used by the server, build and maintenance tools."""
import json,re
from pathlib import Path

SOURCE_SPEC = 'source_format_v1.md'


def load_release(path=None):
    data=json.loads(Path(path or Path(__file__).with_name('release.json')).read_text('utf8'))
    version=data.get('version');revision=data.get('package_revision')
    if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('程序版本格式无效')
    if not isinstance(revision,str) or not re.fullmatch(r'R[1-9]\d*',revision):raise ValueError('包修订格式无效')
    python_version=version if revision=='R1' else version+'.post'+revision[1:]
    return {'version':version,'package_revision':revision,'python_version':python_version,'release':f'v{version} {revision}',
            'version_label':f'v{version}','stem':f'HTMLReportStudio_v{version}_{revision}'}
