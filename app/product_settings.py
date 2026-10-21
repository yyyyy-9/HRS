"""Product defaults and choice catalogs. Values have one JSON owner.

Protocol/schema identifiers and trust hashes belong to their own contracts.
Browser data is generated from this same file, never maintained by hand.
"""
import json
from pathlib import Path
from types import MappingProxyType


def load_settings(path=None):
    data=json.loads(Path(path or Path(__file__).with_suffix('.json')).read_text('utf8'))
    if data.get('schema')!='hrs-product-settings-v1':raise ValueError('产品设置格式无效')
    for key in ('render_profiles','color_themes'):
        group=data[key];ids=[item['id'] for item in group['choices']]
        if not ids or len(set(ids))!=len(ids) or group['default'] not in ids:raise ValueError('产品设置目录无效：'+key)
    for entry in data['render_options'].values():
        if type(entry['default']) is not bool or type(entry['new_free']) is not bool:raise ValueError('产品显示默认值必须是布尔值')
    highlights=data['highlights'];choices=highlights['choices'];ids=[choice['id'] for choice in choices]
    import re
    if len(set(ids))!=len(ids) or highlights['default'] not in ids or any(not re.fullmatch(r'#[a-fA-F0-9]{6}',choice['color']) for choice in choices):
        raise ValueError('高亮颜色目录无效')
    return data


def _freeze(value):
    if isinstance(value,dict):return MappingProxyType({key:_freeze(item) for key,item in value.items()})
    if isinstance(value,list):return tuple(_freeze(item) for item in value)
    return value


SETTINGS=_freeze(load_settings())
PROFILES=SETTINGS['render_profiles']
OPTIONS=SETTINGS['render_options']
THEMES=SETTINGS['color_themes']
