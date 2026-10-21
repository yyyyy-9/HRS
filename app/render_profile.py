"""Shared output policy over the existing IR; source saving remains independent."""
import json
import re
from pathlib import Path
from product_settings import PROFILES,OPTIONS


def normalize(value=None):
    if value is None:return PROFILES['default']
    if value not in tuple(item['id'] for item in PROFILES['choices']):raise ValueError('未知渲染模式 / render profile')
    return value


def read(folder, default=None):
    if folder is None:return normalize(default)
    path=Path(folder)/'meta.json'
    if path.is_symlink():raise ValueError('工程模式配置不能是链接文件')
    if not path.is_file():return normalize(default)
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    return normalize(data.get('render_profile',default))


def normalize_options(value=None):
    if value is None:value={}
    if not isinstance(value,dict):raise ValueError('渲染选项必须是对象')
    result={}
    for name,entry in OPTIONS.items():
        setting=value.get(name,entry['default'])
        if type(setting) is not bool:raise ValueError(entry['label']+'显示选项必须为布尔值')
        result[name]=setting
    return result


def new_options(profile=None):
    free=normalize(profile)=='free'
    return {name:entry['new_free'] if free else entry['default'] for name,entry in OPTIONS.items()}


def read_options(folder):
    if folder is None:return normalize_options()
    path=Path(folder)/'meta.json'
    if path.is_symlink():raise ValueError('工程显示配置不能是链接文件')
    if not path.is_file():return normalize_options()
    return normalize_options(json.loads(path.read_text(encoding='utf-8-sig')).get('render_options'))


def output_checks(ir,profile='engineering'):
    """Read heading records already parsed by report_contract, never reparse text."""
    if normalize(profile)!='engineering':return []
    result=[];previous=0;main_count=0
    for heading in ir.get('blocks',[]):
        if heading.get('type')!='heading':continue
        level=heading['level']
        def add(code,severity,message):
            result.append({'code':code,'severity':severity,'message':message,
                **{key:heading[key] for key in ('line','start','end') if key in heading}})
        if level==1:
            main_count+=1
            if main_count>1:add('MULTIPLE_H1','error','工程报告只能有一个主标题；请将本处改为正文章节标题')
        if previous and level>previous+1:add('HEADING_LEVEL_GAP','error','章节标题向下跳级；请补齐标题层级')
        if level>1 and re.match(r'^\d+(?:\.\d+)*[.)、]?[ \t]+',heading.get('text','')):
            add('HEADING_SOURCE_PREFIX','warning','标题可能含手工章号；输出会自动编号，请核对后确认继续')
        previous=level
    # The actionable prefix notice must be visible before long core diagnostic lists.
    return sorted(result,key=lambda d:(d['code']!='HEADING_SOURCE_PREFIX',d.get('line',0)))


def require_output(ir,profile='engineering',accept_numbered_headings=False):
    diagnostics=output_checks(ir,profile)
    errors=[d for d in diagnostics if d['severity']=='error']
    if errors:raise ValueError('工程输出检查失败：'+errors[0]['code']+'：'+errors[0]['message'])
    if any(d['code']=='HEADING_SOURCE_PREFIX' for d in diagnostics) and not accept_numbered_headings:
        raise ValueError('HEADING_SOURCE_PREFIX：请核对手工章号；程序调用须显式接受本次源快照的提醒')
    return diagnostics
