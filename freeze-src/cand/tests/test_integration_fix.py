"""Integration-fix regressions for F1-F4 (candidate fork only).

F1: across-leaf atom sharing allowed (source MAX_SEG_MEMBERSHIPS=2);
    within-leaf / child-edge / union / seq checks retained.
F2: facade revisions bound to pinned source read_seg_hierarchy(tlstore,pin).
F3: identical-frontier no-op dedups BEFORE preparation (1 prepare total).
F4: opt-in ingest_visible waits for prepared generation; merged search().
"""
import hashlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fork/tl-sys'))

import numpy as np

from tlsys.store_if import TLStore
from tlsys.ingest import ingest_docs
from tlsys.local_repair import RepairConfig, canonical
from tlsys.org_publication import (
    GenerationPublisher, MembershipRevision, PreparedFacade, canonical as pub_canonical,
    verify_prepared)
from tlsys.org_service import OrganizationService, ServiceConfig
from tlsys.repair_hook import TLStoreRepairHook

from test_integration import build_store, emb, qvec


def make_service(root, tl, **cfg):
    s = OrganizationService(
        tl, config=ServiceConfig(enabled=True, drain_budget_seconds=30,
                                 repair_units_per_drain=0, **cfg),
        directory=os.path.join(root, 'service'),
        repair=TLStoreRepairHook(tl))
    return s


class FixTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='fix-')
        self.tl = build_store(self.root)
        self.services = []

    def tearDown(self):
        for s in self.services:
            s.close()
        if self.tl is not None:
            self.tl.close()

    # F1: legit overlap accepted; strict checks retained.
    def test_overlap_across_leaves_allowed(self):
        import hashlib as hl
        leaf_a = {"members": ("atom1", "atom2"), "seq": 1, "descriptor": (0.0,)}
        leaf_b = {"members": ("atom2", "atom3"), "seq": 1, "descriptor": (0.0,)}

        def rev(hid, h):
            return MembershipRevision(hid, 1, hl.sha256(pub_canonical({
                "members": list(h["members"]), "children": [],
                "descriptor": [0.0]})).hexdigest())

        facade = types.SimpleNamespace(
            leaves={"la": leaf_a, "lb": leaf_b}, parents={},
            membership_revisions=(rev("la", leaf_a), rev("lb", leaf_b)))
        self.assertTrue(verify_prepared(facade, (0, 0, 1, "t")))

    def test_within_leaf_duplicates_still_rejected(self):
        leaf_a = {"members": ("atom1", "atom1"), "seq": 1, "descriptor": (0.0,)}
        facade = types.SimpleNamespace(
            leaves={"la": leaf_a}, parents={}, membership_revisions=())
        with self.assertRaises(RuntimeError):
            verify_prepared(facade, (0, 0, 1, "t"))

    def test_child_edge_duplicates_still_rejected(self):
        leaf_a = {"members": ("atom1",), "seq": 1, "descriptor": (0.0,)}
        parent = {"members": ("atom1",), "children": ("la", "la"),
                  "seq": 1, "descriptor": (0.0,)}
        facade = types.SimpleNamespace(
            leaves={"la": leaf_a}, parents={"pa": parent},
            membership_revisions=())
        with self.assertRaises(RuntimeError):
            verify_prepared(facade, (0, 0, 1, "t"))

    # F2: source binding.
    def test_honest_facade_matches_pinned_source(self):
        pin = self.tl.pin()
        facade = PreparedFacade(self.tl, pin, ())
        try:
            self.assertTrue(verify_prepared(facade, pin, self.tl))
        finally:
            facade.close()

    def test_consistent_tamper_fails_source_binding(self):
        import hashlib as hl
        pin = self.tl.pin()
        facade = PreparedFacade(self.tl, pin, ())
        try:
            ghost = {"members": [], "children": [], "seq": pin[2],
                     "descriptor": [0.0]}
            digest = hl.sha256(pub_canonical(
                {"members": [], "children": [], "descriptor": [0.0]})).hexdigest()
            tampered = types.SimpleNamespace(
                leaves={**dict(facade.leaves), "ghost-leaf": ghost},
                parents=dict(facade.parents),
                membership_revisions=tuple(sorted(
                    facade.membership_revisions + (
                        MembershipRevision("ghost-leaf", pin[2], digest),),
                    key=lambda r: r.holon_id)))
            # Snapshot self-consistency is blind (documents the old hole).
            self.assertTrue(verify_prepared(tampered, pin))
            # Pinned-source binding rejects it.
            with self.assertRaises(RuntimeError):
                verify_prepared(tampered, pin, self.tl)
        finally:
            facade.close()

    # F3: no-op before prepare.
    def test_identical_frontier_single_prepare(self):
        s = make_service(self.root, self.tl)
        self.services.append(s)
        calls = []
        real = s.publisher._prepare

        def counting(tlstore, pin, pending):
            calls.append(pin)
            return real(tlstore, pin, pending)

        s.publisher._prepare = counting
        g0 = s.publish().result()
        files_before = sorted(p.name for p in s.publisher.directory.glob('*.json'))
        g1 = s.publish().result()
        files_after = sorted(p.name for p in s.publisher.directory.glob('*.json'))
        self.assertEqual(g1.generation_id, g0.generation_id)
        self.assertEqual(len(calls), 1)
        self.assertEqual(files_before, files_after)
        self.assertEqual(s.publisher.last_timings.get("dedup"), "identical-frontier")
        with s.publisher.acquire() as request:
            self.assertEqual(request.generation.generation_id, g0.generation_id)

    def test_rewind_and_foreign_still_refused(self):
        s = make_service(self.root, self.tl)
        self.services.append(s)
        g0 = s.publish().result()
        with self.assertRaises(RuntimeError):
            s.publisher.submit((g0.pin[0], g0.pin[1], g0.pin[2] - 1, g0.pin[3]), ()).result()
        with self.assertRaises(RuntimeError):
            s.publisher.submit(("foreign-birth", g0.pin[1], g0.pin[2], g0.pin[3]), ()).result()

    def test_prepare_fault_needs_fresh_frontier(self):
        s = make_service(self.root, self.tl)
        self.services.append(s)
        g0 = s.publish().result()

        def boom(stage):
            if stage == "before_prepare":
                raise RuntimeError("injected prepare failure")

        s.publisher._fault = boom
        # Identical frontier short-circuits before fault injection.
        g1 = s.publish().result()
        self.assertEqual(g1.generation_id, g0.generation_id)
        # Fresh frontier reaches the fault.
        s.ingest([('sport-c', 'sport late append')], emb)
        with self.assertRaises(RuntimeError):
            s.last_future.result()

    # F4: visible ingest + merged search.
    def test_ingest_visible_disabled_byte_identical(self):
        docs = [('sport-a', 'sport one two'), ('med-a', 'medicine four five')]
        ta = TLStore(os.path.join(self.root, 'a'), create=True)
        tb = TLStore(os.path.join(self.root, 'b'), create=True)
        try:
            sa = OrganizationService(ta, config=ServiceConfig(enabled=False))
            sb = OrganizationService(tb, config=ServiceConfig(enabled=False))
            ra = sa.ingest(list(docs), emb)
            rb = sb.ingest_visible(list(docs), emb)
            # Stores mint random revision/birth UUIDs; normalize those,
            # then the delegated results must be identical.
            import re
            norm = lambda v: re.sub(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                "REV", canonical(v))
            self.assertEqual(norm(rb), norm(ra))
        finally:
            sa.close()
            sb.close()
            ta.close()
            tb.close()

    def test_ingest_visible_acks_published_generation(self):
        s = make_service(self.root, self.tl, await_visibility_on_ack=True)
        self.services.append(s)
        out = s.ingest_visible([('sport-c', 'sport late append')], emb)
        self.assertIn("source_commit_to_ack_s", out)
        self.assertGreaterEqual(out["source_commit_to_ack_s"], 0)
        gen = out["generation"]
        with s.publisher.acquire() as request:
            self.assertEqual(request.generation.generation_id, gen.generation_id)
            rows, info = request.facade.search('sport', qvec('sport'), k=10)
            aids = [r["aid"] for r in rows]
            self.assertEqual(len(aids), len(set(aids)))
            self.assertIn("guided", info)
            self.assertIn("pending", info)

    def test_ingest_visible_fails_not_acks_on_prepare_failure(self):
        s = make_service(self.root, self.tl, await_visibility_on_ack=True)
        self.services.append(s)

        def boom(stage):
            if stage == "before_prepare":
                raise RuntimeError("injected prepare failure")

        s.publisher._fault = boom
        with self.assertRaises(RuntimeError):
            s.ingest_visible([('sport-c', 'sport late append')], emb)

    def test_ingest_visible_requires_opt_in_flag(self):
        s = make_service(self.root, self.tl)
        self.services.append(s)
        with self.assertRaises(RuntimeError):
            s.ingest_visible([('sport-c', 'sport late append')], emb)


if __name__ == '__main__':
    unittest.main(verbosity=2)
