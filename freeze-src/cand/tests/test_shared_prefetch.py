"""Opt-in shared-pool nonblocking prefetch (tiny native fixtures).

Covers the suffix-prefetch seam only: retained old-pin queries complete
while a prefetched source scan is blocked; rows/revisions match an
independent cold build; same-pin warm hits scan nothing; rewind/stale
ranges fall back safely; source work is counted exactly once.
"""
import threading
import time
import tempfile
import unittest
from pathlib import Path

from tlsys.org_publication import PreparedFacade
from tlsys.org_service import OrganizationService, ServiceConfig
from tlsys.index import NarrowIndex
from tlsys.serving.view import ViewPool
from tlsys.store_if import TLStore
from test_publication import embed


def view_digest(index):
    with index._locked_view() as view:
        return view.canonical_digest()


def cold_parity(case, reader, pending=()):
    g = reader.generation
    cold = PreparedFacade(reader.facade._tl, g.pin, pending or g.pending_documents)
    try:
        case.assertEqual(reader.facade.membership_revisions, cold.membership_revisions)
        case.assertEqual(reader.facade.leaves, cold.leaves)
        case.assertEqual(reader.facade.parents, cold.parents)
        for v in ([1., 0., 0., 0.], [0., 1., 0., 0.]):
            for method in ('guided', 'search'):
                a = getattr(reader.facade, method)('alpha', v)[0]
                b = getattr(cold, method)('alpha', v)[0]
                case.assertEqual(a, b)
    finally:
        cold.close()


class SharedPrefetchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='shared-prefetch-'))
        self.tl = TLStore(str(self.root / 'store'), create=True)
        self.services = []
        self.publishers = []

    def tearDown(self):
        for s in self.services:
            s.close()
        for p in self.publishers:
            p.close()
        self.tl.close()

    def service(self):
        s = OrganizationService(self.tl, config=ServiceConfig(
            enabled=True, drain_budget_seconds=30, reuse_view_pool=True))
        self.services.append(s)
        return s

    def test_prefetch_advance_matches_cold_and_counts_once(self):
        s = self.service()
        s.ingest([('d1', 'alpha one'), ('d2', 'beta two')], embed)
        g1 = s.last_future.result()
        s.ingest([('d3', 'alpha three')], embed)
        g2 = s.last_future.result()
        pool = ViewPool(self.tl, g1.pin[0], g1.pin[1])
        v1 = pool.acquire(tuple(g1.pin))
        c0 = pool.counters.totals()
        v2 = pool.acquire_shared(tuple(g2.pin))
        c1 = pool.counters.totals()
        try:
            ref = NarrowIndex(self.tl, tuple(g2.pin))
            try:
                self.assertEqual(v2.canonical_digest(), view_digest(ref))
            finally:
                ref._pool.release(ref._view)
            exp = len(self.tl.read_commits_all(
                g1.pin[0], g1.pin[1], g2.pin[2], kind="ACCEPT_ATOMS", min_seq=g1.pin[2]))
            self.assertEqual(c1['log_rows_read'] - c0['log_rows_read'], exp)
            # A second pool over the default path must count identical work.
            pool2 = ViewPool(self.tl, g1.pin[0], g1.pin[1])
            w1 = pool2.acquire(tuple(g1.pin))
            d0 = pool2.counters.totals()
            w2 = pool2.acquire(tuple(g2.pin))
            d1 = pool2.counters.totals()
            try:
                self.assertEqual(w2.canonical_digest(), v2.canonical_digest())
                self.assertEqual(d1['log_rows_read'] - d0['log_rows_read'],
                                 c1['log_rows_read'] - c0['log_rows_read'])
            finally:
                pool2.release(w1)
                pool2.release(w2)
        finally:
            pool.release(v1)
            pool.release(v2)

    def test_retained_query_completes_during_blocked_prefetch(self):
        s = self.service()
        s.ingest([('d1', 'alpha one'), ('d2', 'beta two')], embed)
        s.last_future.result()
        old = s.publisher.acquire()
        try:
            before = old.facade.guided('alpha', [1., 0., 0., 0.])[0]
            pool = s.publisher._view_pool
            orig_scan = pool._scan
            started = threading.Event()
            release = threading.Event()
            calls = []
            owned_during_scan = []

            def slow(lo, hi):
                calls.append((lo, hi))
                owned_during_scan.append(pool._lock._is_owned())
                started.set()
                self.assertTrue(release.wait(timeout=60), "bounded fixture wait")
                return orig_scan(lo, hi)

            pool._scan = slow  # instance-only: no other pool observes this
            try:
                worker = threading.Thread(
                    target=lambda: s.ingest([('d3', 'alpha three')], embed))
                worker.start()
                try:
                    self.assertTrue(started.wait(timeout=60))
                    t0 = time.monotonic()
                    during = old.facade.guided('alpha', [1., 0., 0., 0.])[0]
                    elapsed = time.monotonic() - t0
                    # Guided query finished BEFORE the scan was released.
                    self.assertFalse(release.is_set())
                    self.assertEqual(during, before)
                    self.assertLess(elapsed, 30)
                finally:
                    release.set()
                worker.join(timeout=60)
                self.assertFalse(worker.is_alive())
                g = s.last_future.result(timeout=60)
            finally:
                pool._scan = orig_scan
            # Prefetch ran outside the pool lock; exactly one suffix scan.
            self.assertEqual(owned_during_scan, [False])
            self.assertEqual(len(calls), 1)
            self.assertEqual(pool.counters.totals()['log_ops_read'] >= 1, True)
            cold_parity(self, old)
            with s.publisher.acquire() as cur:
                self.assertEqual(cur.generation, g)
                cold_parity(self, cur)
        finally:
            old.release()

    def test_same_pin_warm_hit_scans_nothing(self):
        s = self.service()
        s.ingest([('d1', 'alpha one')], embed)
        g = s.last_future.result()
        pool = s.publisher._view_pool
        c0 = pool.counters.totals()
        v = pool.acquire_shared(tuple(g.pin))
        try:
            c1 = pool.counters.totals()
            self.assertEqual(c1['log_rows_read'], c0['log_rows_read'])
            self.assertEqual(c1['log_ops_read'], c0['log_ops_read'])
        finally:
            pool.release(v)

    def test_rewind_and_stale_range_fall_back_safely(self):
        s = self.service()
        s.ingest([('d1', 'alpha one'), ('d2', 'beta two')], embed)
        g1 = s.last_future.result()
        s.ingest([('d3', 'alpha three')], embed)
        g2 = s.last_future.result()
        s.ingest([('d4', 'beta four')], embed)
        g3 = s.last_future.result()
        pool = ViewPool(self.tl, g1.pin[0], g1.pin[1])
        v2 = pool.acquire(tuple(g2.pin))
        try:
            # Rewind below the retained frontier falls back (cold build).
            old = pool.acquire_shared(tuple(g1.pin))
            try:
                ref = NarrowIndex(self.tl, tuple(g1.pin))
                self.assertEqual(old.canonical_digest(), view_digest(ref))
            finally:
                pool.release(old)
            # Stale prefetched range rescans under the lock, still exact.
            base = pool._retained[g2.pin[2]]
            c0 = pool.counters.totals()
            v3 = pool._advance_prefetched_locked(
                base, tuple(g3.pin), lo=-1, prefetched=([], [], {}))
            try:
                ref3 = NarrowIndex(self.tl, tuple(g3.pin))
                try:
                    self.assertEqual(v3.pin, tuple(g3.pin))
                    self.assertEqual(v3.canonical_digest(),
                                     view_digest(ref3))
                finally:
                    ref3._pool.release(ref3._view)
                c1 = pool.counters.totals()
                self.assertGreater(c1['log_rows_read'], c0['log_rows_read'])
            finally:
                pool.release(v3)
        finally:
            pool.release(v2)

    def test_failed_publication_keeps_anchor_and_retries(self):
        s = self.service()
        s.ingest([('d1', 'alpha one')], embed)
        s.last_future.result()
        pointer = (s.publisher.directory / 'current.json').read_bytes()
        old = s.publisher.acquire()
        try:
            def fail(stage):
                if stage == 'after_prepare':
                    raise RuntimeError('prepare fault')
            s.publisher._fault = fail
            s.ingest([('d2', 'beta two')], embed)
            with self.assertRaisesRegex(RuntimeError, 'prepare fault'):
                s.last_future.result()
            self.assertEqual((s.publisher.directory / 'current.json').read_bytes(), pointer)
            cold_parity(self, old)
            s.publisher._fault = None
            s.drain(max_documents=2, budget_seconds=30)
            s.last_future.result()
            with s.publisher.acquire() as cur:
                cold_parity(self, cur)
            cold_parity(self, old)
        finally:
            old.release()


if __name__ == '__main__':
    unittest.main(verbosity=2)
