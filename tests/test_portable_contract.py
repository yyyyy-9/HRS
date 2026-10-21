"""TEST-SYSTEM-01: missing portable lifecycle/transport coverage, using virtual time."""
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from portable_sessions import WindowSessions
from portable_transport import accept_key, read_control, write_control


class PortableLifecycle(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.sessions = WindowSessions('current-instance', clock=lambda: self.now, grace=5, timeout=20)

    def test_reconnect_and_live_stream_survive_timers_but_closed_window_expires(self):
        session = self.sessions.join()
        old = self.sessions.connect(session)
        new = self.sessions.connect(session)
        self.sessions.disconnect(session, old)
        self.now = 1000
        self.assertFalse(self.sessions.should_stop())
        self.assertTrue(self.sessions.connected(session, new))
        self.assertFalse(self.sessions.connected(session, old))
        self.sessions.disconnect(session, new)
        self.now += 19
        self.assertFalse(self.sessions.should_stop())
        self.now += 1
        self.assertFalse(self.sessions.should_stop(), 'expired lease still gets a shutdown grace period')
        self.now += 5
        self.assertTrue(self.sessions.should_stop())
        self.assertFalse(self.sessions.begin_operation())
        with self.assertRaises(ValueError):
            self.sessions.join()

    def test_pending_launch_and_requests_drain_before_shutdown_and_new_work_resets_grace(self):
        ticket = self.sessions.reserve_launch()
        first = self.sessions.join(ticket)
        second_ticket = self.sessions.reserve_launch()
        self.assertTrue(self.sessions.begin_operation())
        self.sessions.leave(first)
        self.now = 10
        self.assertFalse(self.sessions.should_stop())
        self.sessions.cancel_launch(second_ticket)
        self.now = 50
        self.assertFalse(self.sessions.should_stop(), 'active document request prevents shutdown')
        self.sessions.end_operation()
        self.assertFalse(self.sessions.should_stop())
        self.now += 4
        second = self.sessions.join()
        self.sessions.leave(second)
        self.assertFalse(self.sessions.should_stop())
        self.now += 4
        self.assertFalse(self.sessions.should_stop())
        self.now += 1
        self.assertTrue(self.sessions.should_stop())

    def test_credentials_cannot_release_another_instance_and_keep_alive_is_explicit(self):
        session = self.sessions.join()
        for invalid in [None, {**session, 'secret': 'wrong'}, {**session, 'instance': 'other'}]:
            with self.subTest(credentials=invalid), self.assertRaises(ValueError):
                self.sessions.leave(invalid)
        self.assertEqual(self.sessions.summary()['windows'], 1)
        keep = WindowSessions('keep', enabled=False, grace=0, timeout=1, clock=lambda: self.now)
        credential = keep.join()
        keep.leave(credential)
        self.now = 10000
        self.assertFalse(keep.should_stop())


class PortableControlFrames(unittest.TestCase):
    def test_rfc_handshake_and_only_masked_complete_control_frames_are_accepted(self):
        self.assertEqual(accept_key('dGhlIHNhbXBsZSBub25jZQ=='), 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=')
        for invalid in [None, 'not-base64', 'YQ==']:
            with self.subTest(key=invalid), self.assertRaises(ValueError):
                accept_key(invalid)
        self.assertEqual(read_control(io.BytesIO(b'\x89\x82abcd' + bytes((ord('H') ^ 97, ord('i') ^ 98)))), (9, b'Hi'))
        for invalid in [b'\x81\x80abcd', b'\x09\x80abcd', b'\x89\x00', b'\x89\xfe', b'\x88\x81abcdx']:
            with self.subTest(frame=invalid), self.assertRaises(ValueError):
                read_control(io.BytesIO(invalid))
        with self.assertRaises(ConnectionError):
            read_control(io.BytesIO(b'\x89\x82abc'))
        output = io.BytesIO()
        write_control(output, 10, b'Hi')
        self.assertEqual(output.getvalue(), b'\x8a\x02Hi')
        with self.assertRaises(ValueError):
            write_control(output, 1, b'document data is forbidden')


if __name__ == '__main__':
    unittest.main(verbosity=2)
