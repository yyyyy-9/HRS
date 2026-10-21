"""Small, thread-safe window leases for the portable host (standard library only).

A connected event stream stays alive without relying on JavaScript timers in a
hidden window. Disconnected leases have time to reconnect; explicit page exits
release their lease. Shutdown is committed only after the last lease/launch and
all ongoing document requests have drained, followed by a grace period.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import secrets
import threading
import time
import uuid


@dataclass
class WindowLease:
    secret: str
    seen: float
    generation: int = 0
    connected: bool = False


class WindowSessions:
    def __init__(self, instance: str, *, enabled: bool = True, grace: float = 10,
                 timeout: float = 90, clock=time.monotonic):
        self.instance = instance
        self.enabled = enabled
        self.grace = grace
        self.timeout = timeout
        self.clock = clock
        self.lock = threading.RLock()
        self.windows: dict[str, WindowLease] = {}
        self.launches: dict[str, float] = {}
        self.armed = False
        self.idle_since = None
        self.operations = 0
        self.stopping = threading.Event()

    def reserve_launch(self) -> str:
        with self.lock:
            if self.stopping.is_set():
                raise ValueError('服务正在退出，请稍后重新启动')
            ticket = uuid.uuid4().hex
            self.launches[ticket] = self.clock() + self.timeout
            self.armed = True
            self.idle_since = None
            return ticket

    def cancel_launch(self, ticket: str) -> None:
        with self.lock:
            self.launches.pop(ticket, None)

    def join(self, launch: str = '') -> dict:
        with self.lock:
            if self.stopping.is_set():
                raise ValueError('服务正在退出，请稍后重新启动')
            if len(self.windows) >= 32:
                raise ValueError('编辑窗口数量已达到上限')
            # Only the new window may consume its own pending launch ticket.
            self.launches.pop(launch, None)
            ident = uuid.uuid4().hex
            secret = secrets.token_urlsafe(32)
            self.windows[ident] = WindowLease(secret, self.clock())
            self.armed = True
            self.idle_since = None
            return {'instance': self.instance, 'window': ident, 'secret': secret}

    def _lease(self, credentials: dict) -> WindowLease:
        if not isinstance(credentials, dict) or credentials.get('instance') != self.instance:
            raise ValueError('窗口与当前服务不匹配')
        ident, secret = credentials.get('window'), credentials.get('secret')
        if not isinstance(ident, str) or not isinstance(secret, str):
            raise ValueError('窗口口令无效')
        lease = self.windows.get(ident)
        if not lease or not hmac.compare_digest(secret, lease.secret):
            raise ValueError('窗口已结束或口令不匹配')
        return lease

    def authenticate(self, credentials: dict) -> None:
        with self.lock:
            self._lease(credentials)

    def pulse(self, credentials: dict) -> None:
        with self.lock:
            lease = self._lease(credentials)
            lease.seen = self.clock()
            self.idle_since = None

    def connect(self, credentials: dict) -> int:
        with self.lock:
            lease = self._lease(credentials)
            lease.generation += 1
            lease.connected = True
            lease.seen = self.clock()
            self.idle_since = None
            return lease.generation

    def connected(self, credentials: dict, generation: int) -> bool:
        with self.lock:
            try:
                lease = self._lease(credentials)
                return lease.connected and lease.generation == generation and not self.stopping.is_set()
            except ValueError:
                return False

    def disconnect(self, credentials: dict, generation: int) -> None:
        with self.lock:
            try:
                lease = self._lease(credentials)
            except ValueError:
                return
            # An old connection's finally block must not release a newer one.
            if lease.generation == generation:
                lease.connected = False
                lease.seen = self.clock()

    def leave(self, credentials: dict) -> None:
        with self.lock:
            self._lease(credentials)
            del self.windows[credentials['window']]

    def begin_operation(self) -> bool:
        with self.lock:
            if self.stopping.is_set():
                return False
            self.operations += 1
            self.idle_since = None
            return True

    def end_operation(self) -> None:
        with self.lock:
            self.operations -= 1

    def should_stop(self) -> bool:
        with self.lock:
            if self.stopping.is_set():
                return True
            if not self.enabled or not self.armed:
                return False
            now = self.clock()
            for ident, lease in list(self.windows.items()):
                if not lease.connected and now - lease.seen >= self.timeout:
                    del self.windows[ident]
            self.launches = {key: expiry for key, expiry in self.launches.items() if expiry > now}
            if self.windows or self.launches or self.operations:
                self.idle_since = None
                return False
            if self.idle_since is None:
                self.idle_since = now
            if now - self.idle_since < self.grace:
                return False
            # Same lock as join/launch/operations: no new work can race shutdown.
            self.stopping.set()
            return True

    def summary(self) -> dict:
        with self.lock:
            return {'auto_exit': self.enabled, 'windows': len(self.windows),
                    'connected': sum(lease.connected for lease in self.windows.values()),
                    'pending_launches': len(self.launches), 'operations': self.operations,
                    'closing': self.stopping.is_set(), 'grace_seconds': self.grace}
