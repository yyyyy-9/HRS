"""Optional private desktop print transport; document/output rules stay in studio.

Only the owning desktop process supplies this capability via its child environment.
It is never returned to a page or accepted from a document/API request.
"""
import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
DESKTOP_PROTOCOL=json.loads(Path(__file__).with_name('host_capabilities.json').read_text('utf8'))['desktop_protocol']


def desktop_bridge():
    raw = os.environ.get('HRS_DESKTOP_BRIDGE')
    if not raw:
        return None
    value = json.loads(raw)
    target = urlsplit(value.get('url', ''))
    if (value.get('protocol') != DESKTOP_PROTOCOL or target.scheme != 'http' or
            target.hostname != '127.0.0.1' or not target.port or
            target.path or target.query or target.fragment or target.username or
            not isinstance(value.get('token'), str) or len(value['token']) < 32):
        raise RuntimeError('桌面打印通道无效，请重新启动程序')
    return value


def render_desktop_pdf(html_file, pdf_file):
    bridge = desktop_bridge()
    if bridge is None:
        return False
    request = Request(bridge['url'] + '/pdf', method='POST',
                      headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + bridge['token']},
                      data=json.dumps({'html': str(html_file.resolve()), 'pdf': str(pdf_file.resolve())}).encode('utf8'))
    with urlopen(request, timeout=60) as response:
        result = json.loads(response.read(4096))
    if result.get('ok') is not True or not pdf_file.is_file() or not pdf_file.read_bytes().startswith(b'%PDF-'):
        raise RuntimeError('桌面内核未生成 PDF，请重试')
    return True


def release_desktop_windows(server):
    """A dead host releases only its own leases, preserving separate browser pages."""
    life=server.portable_lifecycle
    with life.lock:
        server.desktop_parent_gone.set()
        for credentials in server.desktop_windows.values():
            try:life.leave(credentials)
            except ValueError:pass  # A normal pagehide may already have released it.
        server.desktop_windows.clear()
        life.cancel_launch(server.desktop_launch)
        # A surviving ordinary browser page uses its original PDF path once
        # the owning desktop renderer is gone. No fallback during normal use.
        os.environ.pop('HRS_DESKTOP_BRIDGE',None)


def watch_desktop_parent(server):
    """Bind to the actual parent process handle, not a reusable PID heuristic."""
    import ctypes
    from ctypes import wintypes
    parent=int(os.environ['HRS_DESKTOP_PARENT_PID'])
    if os.name!='nt' or parent<=0:raise RuntimeError('桌面父进程绑定无效')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x100000,False,parent)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    def watch():
        try:
            while not server.portable_lifecycle.stopping.is_set():
                result=kernel.WaitForSingleObject(handle,250)
                if result==0:
                    release_desktop_windows(server);return
                if result!=258:
                    release_desktop_windows(server);return
        finally:kernel.CloseHandle(handle)
    thread=threading.Thread(target=watch,name='desktop-parent-monitor',daemon=True);thread.start()
    return thread
