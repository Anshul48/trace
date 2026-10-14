"""Concurrency regression tests for publish-fix (own workspace only).

Covers: bg drain waits its OWN future (never alien last_future); start()
recovers after thread death preserving writer ownership + pending queue.
Tiny synthetic 4-d embeds, small TOK, bounded waits. Observed-only claims.
"""
import concurrent.futures as cf
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tlsys.store_if import TLStore
from tlsys.org_service import OrganizationService, ServiceConfig


def embed(texts):
    return [[1., 0., 0., 0.] if t.startswith('alpha') else [0., 1., 0., 0.] for t in texts]


def make_service(tl, **kw):
    cfg = ServiceConfig(enabled=True, drain_budget_seconds=30,
                        poll_seconds=kw.pop('poll_seconds', 0.02))
    return OrganizationService(tl, config=cfg, **kw)


class BgOwnFutureTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='pubfix-reg-'))
        self.tl = TLStore(str(self.root / 'store'), create=True)
        self.services = []

    def tearDown(self):
        for s in self.services:
            try:
                s.close()
            except Exception:
                pass
        try:
            self.tl.close()
        except Exception:
            pass

    def test_bg_ignores_alien_last_future(self):
        s = make_service(self.tl); self.services.append(s)
        s.ingest([('d1', 'alpha one')], embed); s.last_future.result()
        entered, gate = threading.Event(), threading.Event()
        orig = s.publisher._prepare

        def gated(tlstore, pin, pending=()):
            entered.set()
            self.assertTrue(gate.wait(10))
            return orig(tlstore, pin, pending)
        s.publisher._prepare = gated
        s.start()
        self.assertTrue(entered.wait(10))
        alien = cf.Future()
        alien.set_exception(RuntimeError('alien-build injected'))
        s.last_future = alien  # foreground overwrite while bg waits its own
        gate.set()
        deadline = time.monotonic() + 10
        while s.pending() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(s.pending(), ())
        self.assertTrue(s._thread.is_alive())
        self.assertIsNone(s.last_error)
        with self.assertRaisesRegex(RuntimeError, 'alien-build'):
            alien.result()
        # bg published its own generation after the alien overwrite
        self.assertIsNot(s.last_future, alien)
        s.last_future.result()
        rep = s.drain()
        json.dumps(rep)  # serializable drain report

    def test_start_recovers_after_thread_death(self):
        def failorg(where):
            if where == 'before_organize':
                raise RuntimeError('injected before_organize')
        s = make_service(self.tl, fault=failorg); self.services.append(s)
        pub_before = s.publisher
        s.ingest([('d1', 'alpha one')], embed); s.last_future.result()
        s.start()
        deadline = time.monotonic() + 10
        while (s._thread.is_alive() or s.last_error is None) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(s._thread.is_alive())
        self.assertIsNotNone(s.last_error)
        s.fault = None
        s.start()  # must not raise; resets last_error on valid restart
        self.assertIsNone(s.last_error)
        self.assertTrue(s._thread.is_alive())
        self.assertIs(s.publisher, pub_before)  # writer ownership preserved
        self.assertEqual(s.pending(), ('d1',))  # pending queue preserved
        deadline = time.monotonic() + 10
        while s.pending() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(s.pending(), ())
        self.assertIsNone(s.last_error)
        s.last_future.result()

    def test_repair_report_serializable_consistent_keys(self):
        s = make_service(self.tl); self.services.append(s)
        s.ingest([('d1', 'alpha one')], embed); s.last_future.result()
        rep = s.drain(max_documents=0)
        self.assertIn('processed', rep['repair'])
        self.assertIn('budget', rep['repair'])
        json.dumps(rep)


if __name__ == '__main__':
    unittest.main(verbosity=2)
