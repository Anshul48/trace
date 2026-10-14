"""Combined repair+publish integration: real TLRepair composed into the service.

Covers: real hook alters committed memberships; drain publishes the complete
repaired generation through patched Projections/NarrowIndex/segments readers;
old pins stay valid; hook failure blocks publication; restart resumes.
Plus regression tests for aux findings: tampered prepare output rejected;
identical-frontier resubmit is idempotent (no generation growth).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fork/tl-sys'))

import numpy as np

from tlsys.store_if import TLStore
from tlsys.ingest import ingest_docs
from tlsys.maint import organize_segments
from tlsys.local_repair import RepairConfig, canonical
from tlsys.index import NarrowIndex
from tlsys.query import HierQuery
from tlsys.org_publication import (
    GenerationPublisher, PreparedFacade, verify_prepared)
from tlsys.org_service import OrganizationService, ServiceConfig
from tlsys.repair_hook import TLStoreRepairHook


def emb(texts):
    vs = []
    for t in texts:
        v = np.zeros(384)
        v[0 if 'sport' in t else 1] = 1
        vs.append(v.tolist())
    return vs


def qvec(text):
    return emb([text])[0]


def build_store(root, **kw):
    tl = TLStore(os.path.join(root, 'store'), create=True, local_repair=True,
                 repair_config=RepairConfig(edge_threshold=.8))
    docs = [('sport-a', 'sport one two'), ('sport-b', 'sport three four'),
            ('med-a', 'medicine four five')]
    ingest_docs(tl, docs, emb, place_xdoc=False)
    organize_segments(tl, t_parent=-1)
    return tl


class CombinedTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='combined-')
        self.tl = build_store(self.root)
        self.services = []

    def tearDown(self):
        for s in self.services:
            s.close()
        if self.tl is not None:
            self.tl.close()

    def make_service(self, **kw):
        hook = TLStoreRepairHook(self.tl)
        s = OrganizationService(
            self.tl,
            config=ServiceConfig(enabled=True, max_documents_per_drain=8,
                                 drain_budget_seconds=30,
                                 repair_units_per_drain=10 ** 8,
                                 poll_seconds=0.05),
            directory=os.path.join(self.root, 'service'),
            repair=hook, **kw)
        self.services.append(s)
        return s

    def test_real_repair_alters_memberships_and_publishes(self):
        old_pin = self.tl.pin()
        old_index = NarrowIndex(self.tl, old_pin, use_reference=False)
        old_query = HierQuery(self.tl, old_index, lambda q: qvec(q))
        expected = canonical(old_query.guided('sport'))
        n_parents_before = len(old_index.seg_parents)
        s = self.make_service()
        report = s.drain(max_documents=0, repair_budget=10 ** 8)
        self.assertEqual(report['enabled'], True)
        self.assertEqual(report['repair']['hook'], 'tlstore-repair')
        self.assertGreater(
            self.tl.local_repair.engine.counts.get('parent_split', 0), 0)
        # Old pinned reader still serves identical rows after the split.
        self.assertEqual(canonical(old_query.guided('sport')), expected)
        gen = s.last_future.result()
        with s.publisher.acquire() as request:
            # Patched readers reach the publisher: repaired split visible.
            self.assertEqual(len(request.facade.parents), n_parents_before + 1)
            self.assertEqual(request.facade.membership_revisions,
                             gen.membership_revisions)
            rows, _ = request.facade.guided('sport', qvec('sport'))
            self.assertTrue(rows)
        if hasattr(old_index, 'release'):
            old_index.release()

    def test_hook_failure_blocks_publication(self):
        s = self.make_service()
        g0 = s.publish().result()
        def boom(budget):
            raise RuntimeError('injected repair failure')
        s.repair = type('B', (), {'repair_step': staticmethod(boom)})()
        with self.assertRaises(RuntimeError):
            s.drain(max_documents=0, repair_budget=10 ** 8)
        with s.publisher.acquire() as request:
            self.assertEqual(request.generation, g0)

    def test_restart_resumes_and_chains(self):
        s = self.make_service()
        s.ingest([('sport-c', 'sport late append')], emb)
        s.drain(repair_budget=10 ** 8)
        g1 = s.last_future.result()
        old = s.detach_readers()
        try:
            with old.acquire() as request:
                self.assertEqual(request.generation, g1)
                rows, _ = request.facade.guided('sport', qvec('sport'))
                self.assertTrue(rows)
                s2 = OrganizationService(
                    self.tl,
                    config=ServiceConfig(enabled=True, repair_units_per_drain=0),
                    directory=os.path.join(self.root, 'service'),
                    repair=TLStoreRepairHook(self.tl))
                self.services.append(s2)
                # Identical frontier republishes idempotently (aux dup fix).
                g2 = s2.publish().result()
                self.assertEqual(g2.generation_id, g1.generation_id)
                # New work after restart chains onto the resumed frontier.
                s2.ingest([('med-b', 'medicine late append')], emb)
                gi = s2.last_future.result()
                self.assertEqual(gi.parent_generation, g1.generation_id)
                s2.drain()
                g3 = s2.last_future.result()
                self.assertEqual(g3.parent_generation, gi.generation_id)
        finally:
            for pin in list(old._entries.values()):
                pass
            old.close()

    def test_tampered_prepare_rejected(self):
        s = self.make_service()
        real_prepare = s.publisher._prepare
        def tampered(tlstore, pin, pending):
            facade = real_prepare(tlstore, pin, pending)
            revs = list(facade.membership_revisions)
            ghost = type(revs[0])(holon_id='ghost-leaf', commit_seq=pin[2],
                                  membership_sha256='0' * 64)
            facade.membership_revisions = tuple(revs + [ghost])
            return facade
        s.publisher._prepare = tampered
        before = (s.publisher.directory / 'current.json').read_bytes() \
            if (s.publisher.directory / 'current.json').exists() else None
        with self.assertRaises(RuntimeError):
            s.publisher.submit(self.tl.pin(), ()).result()
        after = (s.publisher.directory / 'current.json').read_bytes() \
            if (s.publisher.directory / 'current.json').exists() else None
        self.assertEqual(before, after)

    def test_identical_resubmit_no_growth(self):
        s = self.make_service()
        g0 = s.publish().result()
        files_before = sorted(
            p.name for p in s.publisher.directory.glob('*.json'))
        g1 = s.publish().result()
        files_after = sorted(
            p.name for p in s.publisher.directory.glob('*.json'))
        self.assertEqual(g1.generation_id, g0.generation_id)
        self.assertEqual(files_before, files_after)

    def test_flag_off_identity(self):
        tl2 = TLStore(os.path.join(self.root, 'plain'), create=True)
        try:
            self.assertEqual(tl2.repair_step(10 ** 8),
                             {"enabled": False, "spent": 0, "checked": 0,
                              "debt": 0})
            hook = TLStoreRepairHook(tl2)
            out = hook.repair_step(10 ** 8)
            self.assertEqual(out['processed'], 0)
            self.assertEqual(out['hook'], 'tlstore-repair-disabled')
        finally:
            tl2.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
