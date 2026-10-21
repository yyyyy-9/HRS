#!/usr/bin/env python3
"""HTML Report Studio Windows portable host.

Uses the *bundled* pythonw.exe on Windows.  No third-party packages, admin rights,
registry changes or network access are required.  This is deliberately separate
from studio.py so the editor's data/API semantics stay unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
import uuid
import webbrowser

# The embedded Python _pth includes ../app; normal CPython also resolves this.
from studio import Handler, StudioServer, atomic_write, pick_browser, digest
from portable_sessions import WindowSessions
from portable_transport import accept_key, read_control, write_control

STATE_NAME = '.portable-instance.json'
LOCK_NAME = '.portable-instance.lock'


def notify(title: str, detail: str, *, warning: bool = False) -> None:
    """Show a dialog only for desktop launch failures and requested exit errors."""
    if os.environ.get('STUDIO_PORTABLE_NO_DIALOG') == '1':
        print(f'{title}: {detail}', file=sys.stderr)
        return
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(detail), str(title), 0x30 if warning else 0x40)
    else:
        print(f'{title}: {detail}', file=sys.stderr)


def ensure_data(root: Path) -> Path:
    data = root / 'data'
    data.mkdir(parents=True, exist_ok=True)
    return data


def read_state(data: Path) -> dict | None:
    path = data / STATE_NAME
    if not path.is_file() or path.is_symlink():
        return None
    try:
        state = json.loads(path.read_text('utf-8'))
        if (not isinstance(state, dict) or
            type(state.get('port')) is not int or not 1 <= state['port'] <= 65535 or
            not isinstance(state.get('instance'), str) or
            not isinstance(state.get('token'), str)):
            return None
        return state
    except (ValueError, UnicodeError, OSError, TypeError):
        return None


def query_instance(state: dict, timeout: float = 0.5) -> str | None:
    try:
        request = Request(f"http://127.0.0.1:{state['port']}/api/portable/status")
        with urlopen(request, timeout=timeout) as res:
            if res.status != 200:
                return None
            obj = json.loads(res.read(2048))
            if obj.get('ok') and not obj.get('closing') and obj.get('instance') == state.get('instance'):
                return f"http://127.0.0.1:{state['port']}"
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        pass
    return None


class InstanceLock:
    """Lifetime OS lock.  Prevents duplicate servers without killing stale PIDs."""
    def __init__(self, path: Path):
        self.file = open(path, 'a+b')
        # A one-byte lock file behaves consistently with Windows msvcrt.locking.
        self.file.seek(0, os.SEEK_END)
        if self.file.tell() == 0:
            self.file.write(b'\0')
            self.file.flush()
        self.acquired = False

    def acquire(self) -> bool:
        try:
            if os.name == 'nt':
                import msvcrt
                # Lock exactly the first byte from offset zero. No stale PID heuristics.
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.acquired = True
            return True
        except OSError:
            return False

    def close(self) -> None:
        if self.acquired:
            try:
                if os.name == 'nt':
                    import msvcrt
                    self.file.seek(0)
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            self.acquired = False
        self.file.close()


def redirect_logs(data: Path):
    logs = data / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    dest = logs / 'portable.log'
    try:
        if dest.is_file() and dest.stat().st_size > 3 * 1024 * 1024:
            dest.replace(logs / 'portable.previous.log')
    except OSError:
        pass
    stream = open(dest, 'a', encoding='utf-8', buffering=1)
    sys.stdout = stream
    sys.stderr = stream
    return stream


class PortableServer(StudioServer):
    # Finish ongoing document requests before interpreter exit.
    daemon_threads = False


class PortableHandler(Handler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def bytes(self, *args, **kwargs):
        try:
            return super().bytes(*args, **kwargs)
        except (BrokenPipeError, ConnectionError):
            # A closing page may stop reading the reply after its draft has
            # already been durably written. Finish lease release and draining.
            self.close_connection = True

    def _portable_origin_ok(self):
        if not self._origin_ok():
            return False
        origin = self.headers.get('Origin')
        if origin:
            try:
                parsed = urlsplit(origin)
                return parsed.hostname in ('127.0.0.1', 'localhost') and parsed.port == self.server.server_port
            except ValueError:
                return False
        return self.headers.get('Sec-Fetch-Site') not in ('cross-site', 'same-site')

    def _portable_body(self, limit=4096):
        if not self._portable_origin_ok():
            raise PermissionError('仅允许当前编辑器访问')
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            raise ValueError('仅接受 JSON')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise ValueError('长度无效') from None
        if not 1 <= size <= limit:
            raise ValueError('请求长度无效')
        obj = json.loads(self.rfile.read(size))
        if not isinstance(obj, dict):
            raise ValueError('JSON 必须是对象')
        return obj

    def _events(self):
        if not self._portable_origin_ok():
            return self.fail('仅允许当前编辑器访问', 403)
        parameters = parse_qs(urlsplit(self.path).query)
        credentials = {key: parameters.get(key, [''])[0] for key in ('instance', 'window', 'secret')}
        life = self.server.portable_lifecycle
        try:
            if self.headers.get('Upgrade', '').lower() != 'websocket' or self.headers.get('Sec-WebSocket-Version') != '13':
                raise ValueError('需要窗口连接协议')
            accept = accept_key(self.headers.get('Sec-WebSocket-Key'))
            generation = life.connect(credentials)
        except ValueError as exc:
            return self.fail(exc, 403)
        try:
            # HTTP/1.1 is required for the upgrade response; ordinary requests
            # retain the existing request/response semantics.
            self.protocol_version = 'HTTP/1.1'
            self.send_response(101)
            self.send_header('Upgrade', 'websocket')
            self.send_header('Connection', 'Upgrade')
            self.send_header('Sec-WebSocket-Accept', accept)
            self.end_headers()
            while life.connected(credentials, generation):
                challenge = secrets.token_bytes(8)
                write_control(self.wfile, 9, challenge)
                deadline = time.monotonic() + 15
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ConnectionError('Window heartbeat timed out')
                    self.connection.settimeout(remaining)
                    opcode, payload = read_control(self.rfile)
                    if opcode == 8:
                        write_control(self.wfile, 8, payload)
                        return
                    if opcode == 9:
                        write_control(self.wfile, 10, payload)
                    elif opcode == 10 and payload == challenge:
                        break
                if life.stopping.wait(3):
                    break
            write_control(self.wfile, 8, b'\x03\xe9')
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        except ValueError:
            try:
                write_control(self.wfile, 8, b'\x03\xea')
            except OSError:
                pass
        finally:
            life.disconnect(credentials, generation)
            self.close_connection = True

    def log_message(self, fmt, *args):
        if urlsplit(self.path).path == '/api/portable/events':
            # The per-window capability is never written into the request log.
            print('[local] portable window stream')
        else:
            super().log_message(fmt, *args)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/portable/events':
            return self._events()
        if path == '/api/portable/status':
            if not self._portable_origin_ok():
                return self.fail('仅允许本机访问', 403)
            return self.resp({'ok': True, 'instance': self.server.portable_instance,
                             **self.server.portable_lifecycle.summary()})
        return super().do_GET()

    def do_POST(self):
        life = self.server.portable_lifecycle
        if not life.begin_operation():
            return self.fail('服务正在退出，请重新启动', 503)
        try:
            path = urlsplit(self.path).path
            if not path.startswith('/api/portable/'):
                return super().do_POST()
            obj = self._portable_body(10 * 1024 * 1024 + 8192 if path.endswith('/leave') else 4096)
            if path in ('/api/portable/stop', '/api/portable/launch'):
                if not isinstance(obj.get('token'), str) or not hmac.compare_digest(obj['token'], self.server.portable_token):
                    return self.fail('服务口令不匹配', 403)
                if path.endswith('/launch'):
                    return self.resp({'ok': True, 'launch': life.reserve_launch()})
                self.resp({'ok': True, 'message': '正在关闭服务'})
                life.stopping.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if path == '/api/portable/join':
                launch = obj.get('launch', '')
                if not isinstance(launch, str):
                    raise ValueError('启动标识无效')
                with life.lock:
                    desktop=obj.get('desktop',False)
                    if type(desktop) is not bool:raise ValueError('宿主标记无效')
                    if desktop and (not hasattr(self.server,'desktop_parent_gone') or self.server.desktop_parent_gone.is_set() or launch!=self.server.desktop_launch):
                        raise ValueError('桌面宿主已结束或启动标识不匹配')
                    joined=life.join(launch)
                    if desktop:self.server.desktop_windows[joined['window']]=joined
                return self.resp({'ok': True, **joined})
            if path == '/api/portable/pulse':
                life.pulse(obj)
                return self.resp({'ok': True})
            if path == '/api/portable/leave':
                life.authenticate(obj)
                # Persist the final recoverable snapshot before releasing the
                # window; this never writes the official report.
                if obj.get('draft') is not None and obj.get('draft_delta') is not None:
                    raise ValueError('关闭草稿只能提供一种快照')
                if obj.get('draft_delta') is not None:
                    with self.server.lock:
                        self._write_close_delta(obj['draft_delta'])
                elif obj.get('draft') is not None:
                    if not isinstance(obj['draft'], dict):
                        raise ValueError('草稿必须是对象')
                    with self.server.lock:
                        self._write_draft(obj['draft'])
                else:
                    self.resp({'ok': True})
                life.leave(obj)
                return
            return self.fail('接口不存在', 404)
        except PermissionError as exc:
            return self.fail(exc, 403)
        except (ValueError, UnicodeError, OSError) as exc:
            return self.fail(exc, 400)
        finally:
            life.end_operation()

    def _write_close_delta(self, delta):
        if not isinstance(delta, dict):
            raise ValueError('关闭补丁必须是对象')
        did = self._draft_id(delta)
        previous = self.server.read_draft(did)
        for key in ('document_id', 'template', 'base_revision'):
            if delta.get(key) != previous[key]:
                raise ValueError('关闭补丁与原草稿绑定不匹配')
        start, end, insertion, seq = (delta.get(key) for key in ('from', 'to', 'insert', 'seq'))
        if type(start) is not int or type(end) is not int or type(seq) is not int or not isinstance(insertion, str):
            raise ValueError('关闭补丁范围无效')
        encoded = previous['markdown'].encode('utf-16-le')
        if not 0 <= start <= end <= len(encoded)//2 or not 1 <= seq <= 2147483647:
            raise ValueError('关闭补丁范围或版本无效')
        if delta.get('base_sha256') != digest(previous['markdown'].encode('utf-8')) or seq <= previous['seq']:
            # An in-flight full write or another restored window may already
            # have changed this draft. Preserve that snapshot without guessing.
            return self.resp({'ok':True,'accepted':False,'reason':'STALE_DRAFT_SNAPSHOT','seq':previous['seq']})
        prefix = encoded[:start*2].decode('utf-16-le')
        suffix = encoded[end*2:].decode('utf-16-le')
        return self._write_draft({**delta, 'markdown':prefix+insertion+suffix})


def open_browser(url: str, root: Path) -> None:
    """Use a private Chromium profile, keeping the user's existing browser alone.

    Process IDs do not determine window lifetime. Page leases and live streams
    handle reused browser processes and multiple editor windows.
    """
    try:
        browser = pick_browser()
        if browser and Path(browser).name.lower() in ('msedge.exe', 'chrome.exe', 'msedge', 'chrome', 'chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable'):
            profile = ensure_data(root) / 'browser-profile'
            profile.mkdir(exist_ok=True)
            args = [browser, '--app=' + url, '--user-data-dir=' + str(profile),
                    '--no-first-run', '--no-default-browser-check', '--disable-background-mode',
                    '--disable-background-networking', '--disable-sync', '--disable-extensions']
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            print('Opened independent application window')
            return
    except (OSError, ValueError) as exc:
        print('Application window unavailable:', exc)
    if not webbrowser.open(url, new=1):
        notify('HTML Report Studio', f'请在浏览器中打开：\n{url}', warning=True)


def start(root: Path, *, no_browser: bool = False, keep_alive: bool = False) -> int:
    data = ensure_data(root)
    lock = InstanceLock(data / LOCK_NAME)
    if not lock.acquire():
        # Another launch may still be starting; briefly wait for its state file.
        for _ in range(32):
            state = read_state(data)
            url = query_instance(state) if state else None
            if url:
                if not no_browser:
                    request = Request(url + '/api/portable/launch', method='POST',
                                      headers={'Content-Type': 'application/json'},
                                      data=json.dumps({'token': state['token']}).encode())
                    try:
                        with urlopen(request, timeout=4) as res:
                            ticket = json.loads(res.read(4096))['launch']
                        open_browser(url + '?' + urlencode({'portable_launch': ticket}), root)
                    except (URLError, OSError, ValueError, KeyError):
                        time.sleep(0.15)
                        continue
                lock.close()
                return 0
            time.sleep(0.15)
        notify('HTML Report Studio', '软件正在启动，或已有进程占用。请稍后重试，必要时查看 data\\logs。', warning=True)
        lock.close()
        return 2

    original_out, original_err = sys.stdout, sys.stderr
    log = None
    state_path = data / STATE_NAME
    instance = uuid.uuid4().hex
    server = None
    monitor = None
    try:
        log = redirect_logs(data)
        print(f'[{datetime.now(timezone.utc).isoformat()}] Starting portable host in {root}')
        # Data lives beside the portable package, never in app/ or runtime/.
        projects = data / 'projects'
        server = PortableServer(('127.0.0.1', 0), projects / 'legacy', projects, require_project_location=True)
        server.RequestHandlerClass = PortableHandler
        server.portable_instance = instance
        server.portable_token = secrets.token_urlsafe(32)
        desktop=bool(os.environ.get('HRS_DESKTOP_BRIDGE'))
        life = WindowSessions(instance, enabled=not keep_alive, **({'timeout':15,'grace':2} if desktop else {}))
        server.portable_lifecycle = life
        if desktop:
            server.desktop_launch=life.reserve_launch()
            server.desktop_windows={};server.desktop_parent_gone=threading.Event()
            from host_services import watch_desktop_parent
            watch_desktop_parent(server)
        state = {
            'version': 1,
            'instance': instance,
            'pid': os.getpid(),
            'port': server.server_port,
            'token': server.portable_token,
            'started': datetime.now(timezone.utc).isoformat(),
            **({'desktop_launch':server.desktop_launch} if desktop else {}),
        }
        atomic_write(state_path, (json.dumps(state, ensure_ascii=False) + '\n').encode('utf-8'))
        url = f"http://127.0.0.1:{server.server_port}"
        print('Local editor:', url)
        print('Data directory:', projects)
        if not no_browser:
            ticket = life.reserve_launch()
            open_browser(url + '?' + urlencode({'portable_launch': ticket}), root)
        def watch_windows():
            while not life.stopping.wait(.25):
                if life.should_stop():
                    print('Last editor window ended; stopping after grace period')
                    server.shutdown()
                    return
        monitor = threading.Thread(target=watch_windows, name='portable-window-monitor', daemon=True)
        monitor.start()
        server.serve_forever(poll_interval=0.15)
        print('Server stopped normally')
        return 0
    except Exception as exc:
        import traceback
        traceback.print_exc()
        notify('HTML Report Studio 启动失败', f'{type(exc).__name__}: {exc}\n请查看 data\\logs\\portable.log。', warning=True)
        return 1
    finally:
        if server is not None:
            server.portable_lifecycle.stopping.set()
            server.server_close()
        if monitor is not None:
            monitor.join(2)
        # Only remove this process' run file (never erase another instance).
        current = read_state(data)
        if current and current.get('instance') == instance:
            try:
                state_path.unlink()
            except OSError:
                pass
        lock.close()
        if log is not None:
            log.flush()
            sys.stdout, sys.stderr = original_out, original_err
            log.close()


def stop(root: Path, *, quiet: bool = False) -> int:
    state = read_state(root / 'data')
    if not state:
        if not quiet:
            notify('HTML Report Studio', '软件未运行（找不到运行记录）。')
        return 0
    url = query_instance(state)
    if not url:
        if not quiet:
            notify('HTML Report Studio', '未找到当前软件服务。若之前异常关闭，重新双击启动即可。', warning=True)
        return 2
    body = json.dumps({'token': state['token']}).encode('utf-8')
    req = Request(url + '/api/portable/stop', data=body, method='POST',
                  headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=4) as res:
            data = json.loads(res.read(4096))
            if not data.get('ok'):
                raise RuntimeError('服务未确认退出')
    except (URLError, HTTPError, OSError, ValueError, RuntimeError) as exc:
        if not quiet:
            notify('HTML Report Studio', f'关闭失败：{exc}', warning=True)
        return 3
    # The server removes the state file when shutdown finishes.
    for _ in range(25):
        if not query_instance(state, timeout=0.15):
            break
        time.sleep(0.1)
    if not quiet:
        notify('HTML Report Studio', '本地服务已请求关闭。\n请关闭浏览器中已打开的编辑器标签页。')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='HTML Report Studio portable desktop host')
    parser.add_argument('action', choices=('start', 'stop', 'status'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--keep-alive', action='store_true', help='调试用：不随最后编辑窗口退出，需手动停止')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.action == 'start':
        return start(root, no_browser=args.no_browser, keep_alive=args.keep_alive)
    if args.action == 'stop':
        return stop(root, quiet=args.quiet)
    state = read_state(root / 'data')
    url = query_instance(state) if state else None
    print(json.dumps({'running': bool(url), 'url': url, 'pid': state.get('pid') if url else None}))
    return 0 if url else 1


if __name__ == '__main__':
    raise SystemExit(main())
