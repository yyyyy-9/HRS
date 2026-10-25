"""Project-relative asset spelling and bounded file access, without source edits.

The JSON rules also generate the browser catalog. Paths are not URLs to fetch:
only files under an already authorized assets directory may be read or written.
"""
from pathlib import Path
import json
import re
from project_workspace import is_link

RULES = json.loads(Path(__file__).with_suffix('.json').read_text('utf8'))
SEGMENT = re.compile(RULES['segment_pattern'])
RESERVED = set(RULES['reserved_names'])
IMAGE_EXTENSIONS = RULES['image_extensions']
# Kept for the existing independent source parser and clipboard validators.
_segment = RULES['segment_pattern'].removeprefix('^').removesuffix('$')
ASSET = re.compile(r'^assets/(?=.+\.(?:' + '|'.join(IMAGE_EXTENSIONS) + r')$)'
                   r'((?:' + _segment + r'/){0,' + str(RULES['max_directories']) + r'}' + _segment + r')$', re.I)


def normalize_asset(value, *, originals=False):
    if not isinstance(value, str): return None
    if value.startswith('./'): value = value[2:]
    if not value.startswith(RULES['prefix']): return None
    parts = value[len(RULES['prefix']):].split('/')
    if len(parts) > RULES['max_directories'] + 1: return None
    if any(not SEGMENT.fullmatch(p) or p.endswith('.') or p.split('.')[0].upper() in RESERVED for p in parts): return None
    extensions = IMAGE_EXTENSIONS + (RULES['original_extensions'] if originals else [])
    if parts[-1].rsplit('.', 1)[-1].lower() not in extensions or '.' not in parts[-1]: return None
    return value


def asset_file(root, name):
    """Keep lexical paths inside assets and reject links in every component."""
    if normalize_asset('assets/' + name, originals=True) != 'assets/' + name:
        raise ValueError('附件路径无效：' + str(name))
    root = Path(root)
    if is_link(root): raise ValueError('附件目录不能是链接')
    path = root
    for part in name.split('/'):
        path /= part
        if is_link(path): raise ValueError('附件路径不能包含链接：' + name)
    if not path.resolve().is_relative_to(root.resolve()): raise ValueError('附件超出工程目录')
    return path
