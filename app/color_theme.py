"""Palette metadata only; never changes source or engineering output semantics."""
import json
from pathlib import Path
from product_settings import THEMES
NAMES=tuple(item['id'] for item in THEMES['choices'])
DEFAULT=THEMES['default']
def normalize(value=None):
    if value is None or value=='default':return DEFAULT
    if value not in NAMES:raise ValueError('未知配色主题')
    return value
def read(folder):
    if folder is None:return DEFAULT
    path=Path(folder)/'meta.json'
    if path.is_symlink():raise ValueError('配色配置不能是链接文件')
    if not path.is_file():return DEFAULT
    return normalize(json.loads(path.read_text('utf-8-sig')).get('color_theme'))
