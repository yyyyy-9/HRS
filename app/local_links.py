"""Explicit local document/folder navigation; never part of the asset graph."""
from pathlib import Path,PureWindowsPath
from urllib.parse import urlsplit,unquote
import os,re

DRIVE=re.compile(r'^[A-Za-z]:[\\/]')
CONTROL=re.compile(r'[\x00-\x1f\x7f-\x9f]')
# Opening a document is different from running programs, scripts or shortcuts.
PROGRAM_EXTENSIONS=set('.exe .com .bat .cmd .ps1 .psm1 .vbs .vbe .js .jse .wsf .wsh .hta .msi .msp .scr .pif .lnk .url .cpl .msc .reg .scf .application .appref-ms'.split())


def path_text(href):
    if not isinstance(href,str) or not 1<=len(href)<=8192 or CONTROL.search(href):raise ValueError('文件链接路径无效')
    if re.search(r'%(?![a-fA-F0-9]{2})',href):raise ValueError('文件链接编码无效')
    if href.lower().startswith('file:'):
        if not href.lower().startswith('file://'):raise ValueError('文件链接必须使用完整file://路径')
        uri=urlsplit(href)
        if uri.query or uri.fragment or uri.username or uri.password or uri.port:raise ValueError('文件链接不能包含登录信息、端口或查询片段')
        path=unquote(uri.path,errors='strict')
        if uri.netloc and uri.netloc.lower()!='localhost':
            if not re.fullmatch(r'[A-Za-z0-9_.-]+',uri.netloc):raise ValueError('文件链接主机无效')
            path='//'+uri.netloc+path
        elif re.match(r'^/[A-Za-z]:/',path):path=path[1:]
        if not (Path(path).is_absolute() or PureWindowsPath(path).is_absolute()):raise ValueError('file://必须指向绝对路径')
    else:
        if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:',href) and not DRIVE.match(href):raise ValueError('不是本地文件或文件夹链接')
        if href.startswith(('#','//')):raise ValueError('不是本地文件或文件夹链接')
        path=unquote(href,errors='strict')
    if not path or CONTROL.search(path):raise ValueError('文件链接路径无效')
    return path


def resolve_target(href,project=None):
    target=Path(path_text(href))
    if not target.is_absolute():
        if project is None:raise ValueError('相对文件链接需要已保存的工程目录；请先保存或改用绝对路径')
        target=Path(project)/target
    try:target=target.resolve(strict=True)
    except OSError as error:raise ValueError('文件或文件夹不存在：'+str(target)) from error
    if not (target.is_file() or target.is_dir()):raise ValueError('路径不是普通文件或文件夹')
    if target.is_file() and target.suffix.lower() in PROGRAM_EXTENSIONS:raise ValueError('程序、脚本和快捷方式请在资源管理器中确认后打开')
    return target


def open_target(target):
    if os.name!='nt':raise ValueError('本机文件/文件夹打开目前仅支持Windows')
    os.startfile(str(target))
