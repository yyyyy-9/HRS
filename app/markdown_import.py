"""Read one explicitly selected Markdown file through existing IR/resources.

This adapter supplies the source directory missing from browser File objects.
It never edits the source or creates a second Markdown parser/model.
"""
from pathlib import Path
import base64
from object_clipboard import _fragment, local_urls, local_path, copy_bundle, paste_bundle
from project_workspace import is_link
from render_profile import new_options


def prepare_markdown_import(source, check_image):
    source=Path(source)
    if is_link(source) or not source.is_file() or source.suffix.lower() not in ('.md','.markdown'):
        raise ValueError('请选择普通的 Markdown 文件')
    if source.stat().st_size>10*1024*1024:raise ValueError('Markdown 超过 10 MiB')
    raw=source.read_bytes()
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:raise ValueError('Markdown 不是 UTF-8 编码，请先另存为 UTF-8') from exc
    root=source.parent.resolve(strict=True)
    ir=_fragment(text)
    references=sorted(set(ir['assets'])|local_urls(ir))
    if len(references)>100:raise ValueError('Markdown 图片数量超过 100 项')
    missing=[];total=0
    for url in references:
        path=local_path(root,url)
        if path is None:missing.append(url)
        else:total+=path.stat().st_size
    if missing:
        raise ValueError('以下图片缺失或不在 Markdown 所在目录内（'+str(len(missing))+' 项）：\n'+'\n'.join(missing))
    if total>30*1024*1024:raise ValueError('Markdown 图片总量超过 30 MiB')
    bundle=copy_bundle(text,[root/'assets'],None,source_folder=root)
    bundle['operation']='import'
    result=paste_bundle(bundle,'',[],None,check_image,source_folder=root)
    return {'kind':'markdown','filename':source.name,'markdown':result['markdown'],
            'assets':{name:base64.b64encode(data).decode('ascii') for name,data in result['assets'].items()},
            'asset_map':result['asset_map'],'image_references':len(references),
            'render_profile':'free','render_options':new_options('free')}
