"""Service-scale-correction regressions: alternating per-doc callbacks.

Rejected behavior: all before_organize faults, then all docs, then all
after faults; admission-only wall budget; 3-failures-across-batch
tripwire. Correct behavior (keyed batched drain via maint
doc_checkpoint): strictly alternating before/after per doc in doc
order, per-doc budget/attempt/fault bracketing, fresh tripwire per
doc (no cross-doc wall), unstarted docs untouched. Synthetic 4-d.
Observed-only claims.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tlsys.store_if import TLStore
from tlsys.org_service import OrganizationService, ServiceConfig


def embed(texts):
    return [[1., 0., 0., 0.] if t.split()[0] == 'alpha' else [0., 1., 0., 0.]
            for t in texts]


def docs(n):
    return [(f'd{i:04d}',
             ('alpha ' if i % 2 == 0 else 'beta ') + f'doc number {i} filler text')
            for i in range(n)]


def make_service(tl, directory, batched=True, **kw):
    cfg = ServiceConfig(enabled=True, drain_budget_seconds=600,
                        max_documents_per_drain=kw.pop('max_docs', 64),
                        batched_drain=batched,
                        poll_seconds=kw.pop('poll_seconds', 0.02))
    return OrganizationService(tl, config=cfg, directory=directory,
                               keyed_state=True, **kw)


def geometry_hash(tl):
    from tlsys.proj import Projections
    proj = Projections.cached(tl)
    proj.update(tl)
    view = proj.hierarchy_view()
    leaves = {}
    for lid, v in view['leaves'].items():
        docset = sorted(s.get('doc') for s in v.get('segments', []))
        leaves[lid] = (docset,
                       [round(float(x), 9) for x in v['descriptor']])
    parents = {}
    for pid, v in view['parents'].items():
        pdocs = sorted({d for c in v.get('children', [])
                        for d in leaves.get(c, ([], []))[0]})
        parents[pid] = (pdocs, sorted(v.get('children', [])),
                        [round(float(x), 9) for x in v['descriptor']])
    canon = json.dumps({'leaves': leaves, 'parents': parents},
                       sort_keys=True, default=str)
    return hashlib.sha256(canon.encode()).hexdigest()


def organized_docset(tl):
    from tlsys.proj import Projections
    proj = Projections.cached(tl)
    proj.update(tl)
    view = proj.hierarchy_view()
    return {s.get('doc') for v in view['leaves'].values()
            for s in v.get('segments', [])}


class AlternatingCallbackTests(unittest.TestCase):
    def test_batched_legacy_fails_closed(self):
        root = Path(tempfile.mkdtemp(prefix='svc-cor-legacy-'))
        tl = TLStore(str(root / 'store'), create=True)
        cfg = ServiceConfig(enabled=True, batched_drain=True)
        svc = OrganizationService(tl, config=cfg, directory=str(root / 'svc'),
                                 keyed_state=False)
        try:
            svc.ingest(docs(2), embed)
            with self.assertRaises(RuntimeError):
                svc.drain()
        finally:
            svc.close()
            tl.close()

    def test_alternating_order_and_no_commits_between(self):
        root = Path(tempfile.mkdtemp(prefix='svc-cor-alt-'))
        tl = TLStore(str(root / 'store'), create=True)
        events, seqs, done_at_next_before = [], {}, {}

        def fault(stage):
            doc = current[0]
            events.append((stage, doc))
            seqs[(stage, doc)] = tl.pin()[2]
            if stage == 'before_organize':
                # Every earlier doc must already be durably done.
                states = {b['doc_id']: b['state'] for b in svc.backlog()}
                for d, _ in docs(4)[:int(doc[1:])]:
                    self.assertEqual(states[d], 'done')
                    done_at_next_before[d] = True

        current = [None]
        svc = make_service(tl, str(root / 'svc'))
        try:
            svc.ingest(docs(4), embed)
            # Map call index -> doc via deterministic pending order:
            # befores arrive in pending order; each after matches
            # the last before.
            pending = list(svc.pending())
            n_before = [0]

            def tracking(stage):
                if stage not in ('before_organize',
                                 'after_organize_before_ack'):
                    return
                if stage == 'before_organize':
                    current[0] = pending[n_before[0]]
                    n_before[0] += 1
                elif stage == 'after_organize_before_ack':
                    current[0] = pending[n_before[0] - 1]
                fault(stage)

            svc.fault = tracking
            rep = svc.drain()
            self.assertEqual(len(rep['completed']), 4)
            self.assertEqual(rep.get('budget_kind'),
                             'cooperative-between-documents')
            expect = []
            for d in pending:
                expect += [('before_organize', d),
                           ('after_organize_before_ack', d)]
            self.assertEqual(events, expect)
            # No commits happen between one doc's after and the next
            # doc's before: the source commit stream is per-doc.
            for i in range(len(pending) - 1):
                self.assertEqual(seqs[('after_organize_before_ack',
                                       pending[i])],
                                 seqs[('before_organize', pending[i + 1])])
            # First three docs were verified done before the next began.
            self.assertEqual(len(done_at_next_before), 3)
        finally:
            svc.close()
            tl.close()

    def test_fail_first_after_leaves_exactly_one_doc(self):
        root = Path(tempfile.mkdtemp(prefix='svc-cor-kill-'))
        tl = TLStore(str(root / 'store'), create=True)

        class KillAtFirstAck:
            def __init__(self):
                self.armed = True

            def __call__(self, stage):
                if stage == 'after_organize_before_ack' and self.armed:
                    self.armed = False
                    raise RuntimeError('kill at first ack')

        svc = make_service(tl, str(root / 'svc'), fault=KillAtFirstAck())
        try:
            svc.ingest(docs(4), embed)
            with self.assertRaises(RuntimeError):
                svc.drain()
            states = {b['doc_id']: b['state'] for b in svc.backlog()}
            attempts = {b['doc_id']: b['attempts'] for b in svc.backlog()}
            # Exactly the first doc organized; the second untouched
            # (no attempt, still pending, no failure recorded).
            self.assertEqual(organized_docset(tl), {'d0000'})
            self.assertEqual(states['d0000'], 'pending')
            self.assertEqual(attempts['d0000'], 1)
            for d in ('d0001', 'd0002', 'd0003'):
                self.assertEqual(states[d], 'pending')
                self.assertEqual(attempts[d], 0)
            errors = {b['doc_id']: b['last_error'] for b in svc.backlog()}
            self.assertTrue(all(v is None for v in errors.values()))
        finally:
            svc.close()
            tl.close()
        # Crash restart on the same dirs completes the same source.
        tl2 = TLStore(str(root / 'store'))
        svc2 = make_service(tl2, str(root / 'svc'))
        try:
            rep2 = svc2.drain()
            self.assertEqual(rep2['remaining'], 0, rep2)
            self.assertEqual(len(rep2['completed']), 4, rep2)
            geo_restart = geometry_hash(tl2)
        finally:
            svc2.close()
            tl2.close()
        root2 = Path(tempfile.mkdtemp(prefix='svc-cor-clean-'))
        tl3 = TLStore(str(root2 / 'store'), create=True)
        svc3 = make_service(tl3, str(root2 / 'svc'))
        try:
            svc3.ingest(docs(4), embed)
            svc3.drain()
            self.assertEqual(geometry_hash(tl3), geo_restart)
        finally:
            svc3.close()
            tl3.close()

    def test_partial_budget_starts_subset_only(self):
        root = Path(tempfile.mkdtemp(prefix='svc-cor-budget-'))
        tl = TLStore(str(root / 'store'), create=True)
        clock = [0.0]

        def advancing(stage):
            if stage == 'before_organize':
                clock[0] += 5.0

        cfg = ServiceConfig(enabled=True, drain_budget_seconds=10,
                            max_documents_per_drain=64, batched_drain=True)
        svc = OrganizationService(tl, config=cfg, directory=str(root / 'svc'),
                                 keyed_state=True, fault=advancing)
        try:
            svc.ingest(docs(5), embed)
            with mock.patch('time.monotonic',
                            side_effect=lambda: clock[0]):
                clock[0] = 0.0
                rep = svc.drain()
            # Budget admits docs 0,1 only; the rest stay pending with
            # no attempts and no failure counts.
            self.assertEqual(rep['attempted'], 2, rep)
            self.assertEqual(len(rep['completed']), 2, rep)
            self.assertEqual(rep['failed'], {})
            self.assertEqual(rep['remaining'], 3, rep)
            attempts = {b['doc_id']: b['attempts'] for b in svc.backlog()}
            states = {b['doc_id']: b['state'] for b in svc.backlog()}
            errors = {b['doc_id']: b['last_error'] for b in svc.backlog()}
            for d in ('d0000', 'd0001'):
                self.assertEqual(attempts[d], 1)
                self.assertEqual(states[d], 'done')
            for d in ('d0002', 'd0003', 'd0004'):
                self.assertEqual(attempts[d], 0)
                self.assertEqual(states[d], 'pending')
                self.assertIsNone(errors[d])
        finally:
            svc.close()
            tl.close()

    def test_zero_budget_batched_admits_nothing(self):
        root = Path(tempfile.mkdtemp(prefix='svc-cor-zero-'))
        tl = TLStore(str(root / 'store'), create=True)
        svc = make_service(tl, str(root / 'svc'))
        try:
            svc.ingest(docs(4), embed)
            rep = svc.drain(budget_seconds=0)
            self.assertEqual(rep['attempted'], 0)
            self.assertEqual(rep['remaining'], 4)
            attempts = {b['doc_id']: b['attempts'] for b in svc.backlog()}
            self.assertTrue(all(v == 0 for v in attempts.values()))
            self.assertEqual(rep['failed'], {})
        finally:
            svc.close()
            tl.close()

    def test_capacity_three_failures_match_perdoc(self):
        seen = {}
        for batched in (False, True):
            root = Path(tempfile.mkdtemp(prefix='svc-cor-cap-'))
            tl = TLStore(str(root / 'store'), create=True)
            svc = make_service(tl, str(root / 'svc'), batched=batched)
            try:
                svc.ingest(docs(3), embed)
                with mock.patch('tlsys.place.decide_leaf',
                                side_effect=RuntimeError(
                                    'REJECT_CAPACITY simulated wall')):
                    rep = svc.drain()
                # Stock tripwire intact but never a cross-doc wall:
                # each doc records its own cause and the drain
                # continues, exactly like per-doc mode.
                self.assertEqual(sorted(rep['failed']), ['d0000', 'd0001',
                                                         'd0002'], rep)
                self.assertTrue(all('REJECT_CAPACITY' in e
                                    for e in rep['failed'].values()))
                self.assertEqual(rep['completed'], [])
                states = {b['doc_id']: b['state'] for b in svc.backlog()}
                errors = {b['doc_id']: b['last_error']
                          for b in svc.backlog()}
                self.assertTrue(all(v == 'pending'
                                    for v in states.values()))
                self.assertTrue(all('REJECT_CAPACITY' in (e or '')
                                    for e in errors.values()))
                seen[batched] = dict(rep['failed'])
            finally:
                svc.close()
                tl.close()
        self.assertEqual(seen[False], seen[True])

    def test_doc_checkpoint_fail_closed(self):
        from tlsys.maint import organize_segments
        root = Path(tempfile.mkdtemp(prefix='svc-cor-closed-'))
        tl = TLStore(str(root / 'store'), create=True)
        from tlsys.ingest import ingest_docs
        try:
            ingest_docs(tl, docs(1), embed, keyed_state=True)
            with self.assertRaises(ValueError):
                organize_segments(tl, doc_ids=['d0000'],
                                  keyed_state=False,
                                  doc_checkpoint=lambda *a: True)
            with self.assertRaises(ValueError):
                organize_segments(tl, keyed_state=True,
                                  doc_checkpoint=lambda *a: True)
            from tlsys.maint import _organize_segments_keyed
            with self.assertRaises(ValueError):
                _organize_segments_keyed(tl, doc_checkpoint=lambda *a: True)
        finally:
            tl.close()


if __name__ == '__main__':
    unittest.main()
