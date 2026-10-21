"""Optional, isolated EMF -> vector SVG route, with explicit fallback.

Does not ship or auto-install a converter. On Windows the user may optionally
install Inkscape or point HRS_INKSCAPE to an approved local executable. Inkscape
is never invoked for SVG files, only an explicit EMF clipboard/file import.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from clipboard_graphics import validate_emf

LIMIT_VECTOR=12*1024*1024


def find_inkscape() -> str | None:
    configured=os.environ.get('HRS_INKSCAPE','').strip()
    if configured:
        path=Path(configured)
        return str(path) if path.is_file() else None
    binary=shutil.which('inkscape') or shutil.which('inkscape.exe')
    if binary:return binary
    if os.name=='nt':
        for env in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
            root=os.environ.get(env,'')
            if root:
                path=Path(root)/'Inkscape'/'bin'/'inkscape.exe'
                if path.is_file():return str(path)
    return None


def try_emf_svg(emf:bytes, *,normalizer, warnings:list[str] | None=None) -> bytes | None:
    """Return a safe SVG, or None if an optional converter is absent/fails.

    Never claim vector preservation when only raster fallback succeeded.
    """
    validate_emf(emf)
    binary=find_inkscape()
    if not binary:
        if warnings is not None:warnings.append('未找到可选 EMF→SVG 转换器，使用 PNG 预览，原始 EMF 保留')
        return None
    with tempfile.TemporaryDirectory(prefix='hrs_emf_svg_') as dirname:
        folder=Path(dirname);src=folder/'input.emf';out=folder/'output.svg'
        src.write_bytes(emf)
        try:
            result=subprocess.run([binary,str(src),'--export-filename='+str(out)],
                  stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                  cwd=folder,timeout=25,check=False)
            if result.returncode or not out.is_file() or out.is_symlink():
                raise ValueError('转换器未生成有效 SVG')
            if out.stat().st_size>LIMIT_VECTOR:raise ValueError('SVG 输出超过大小限制')
            svg=normalizer(out.read_bytes())
            if len(svg)>LIMIT_VECTOR:raise ValueError('SVG 规范化后超出限制')
            if warnings is not None:warnings.append('EMF 已通过本机可选转换器转为 SVG，原件和备用 PNG 均保留')
            return svg
        except (OSError,subprocess.TimeoutExpired,ValueError) as exc:
            if warnings is not None:warnings.append('EMF→SVG 转换失败，改用 PNG 预览：'+str(exc)[:90])
            return None
