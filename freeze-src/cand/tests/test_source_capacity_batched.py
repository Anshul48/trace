"""Source-capacity rejection in batched mode (capacity-harness-fix).

Proves the one-line harness correction: the source-capacity probe drain
passes repair_budget=0, so the repair hook is never invoked under poisoned
caps; the drain reports failed+pending with head unchanged; restoring caps
and retrying (default repair budget) succeeds. Default repair stays enabled.

Also proves repair-commit rejection is fail-closed at the engine seam: a
REJECT_CAPACITY-style commit failure raises with no state mutation and debt
retained for retry. Product exceptions are never downgraded.

Read-only inputs: vm-candidate + candidate forks (sys.path only, no writes).
Synthetic docs only (3); no corpus, no cache, no network.
"""
import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
VM_FORK = WORKSPACE / 'fork' / 'tl-sys'
sys.path.insert(0, str(VM_FORK))

import numpy as np

from tlsys.store_if import TLStore
from tlsys.local_repair import RepairConfig, RepairEngine, canonical
from tlsys.org_service import OrganizationService, ServiceConfig
from tlsys.repair_hook import TLStoreRepairHook

REPAIR_UNITS = 250_000_000


def emb(texts):
    vs = []
    for t in texts:
        v = np.zeros(384)
        v[0 if 'sport' in t else 1] = 1
        vs.append(v.tolist())
    return vs


class CountingHook:
    """RepairHook wrapper counting invocations; delegates to the real hook."""

    def __init__(self, tl):
        self.real = TLStoreRepairHook(tl)
        self.calls = 0

    def repair_step(self, budget):
        self.calls += 1
        return self.real.repair_step(budget)


class SourceCapacityBatchedTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='cap-harness-')
        self.tl = TLStore(os.path.join(self.root, 'store'), create=True,
                          local_repair=True,
                          repair_config=RepairConfig(edge_threshold=.45,
                                                     leaf_threshold=.55))
        self.hook = CountingHook(self.tl)
        self.s = OrganizationService(
            self.tl,
            config=ServiceConfig(enabled=True, max_documents_per_drain=128,
                                 drain_budget_seconds=60,
                                 repair_units_per_drain=REPAIR_UNITS,
                                 await_visibility_on_ack=True,
                                 batched_drain=True),
            directory=os.path.join(self.root, 'service'),
            keyed_state=True, repair=self.hook)
        docs = [('cap-a', 'sport one two'), ('cap-b', 'sport three four'),
                ('cap-c', 'medicine four five')]
        self.s.ingest(docs, emb)

    def tearDown(self):
        try:
            self.s.close()
        finally:
            self.tl.close()

    def test_capacity_rejection_skips_repair_and_keeps_head(self):
        previous_pin = self.tl.pin()
        caps = dict(self.tl.cm.caps)
        self.tl.cm.caps['max_delta_entries'] = 0
        self.tl.cm.caps['reserve_deadline_s'] = .01
        try:
            rejection = self.s.drain(max_documents=1, budget_seconds=60,
                                     repair_budget=0)
        finally:
            self.tl.cm.caps = caps
        self.assertEqual(self.hook.calls, 0)
        self.assertEqual(rejection['repair']['processed'], 0)
        self.assertEqual(rejection['repair']['budget'], 0)
        self.assertTrue(rejection['failed'])
        self.assertTrue(self.s.pending())
        self.assertEqual(self.tl.pin(), previous_pin)

    def test_restore_caps_retry_succeeds_with_default_repair(self):
        caps = dict(self.tl.cm.caps)
        self.tl.cm.caps['max_delta_entries'] = 0
        self.tl.cm.caps['reserve_deadline_s'] = .01
        try:
            self.s.drain(max_documents=1, budget_seconds=60, repair_budget=0)
        finally:
            self.tl.cm.caps = caps
        retry = self.s.drain(max_documents=8, budget_seconds=60)
        self.assertTrue(retry['completed'])
        self.assertGreaterEqual(self.hook.calls, 1)

    def test_repair_commit_rejection_fail_closed(self):
        vs = {f'a{i}': ([1.0] + [0.0] * 383) for i in range(4)}
        leaves = {f'xseg-l{i}': {'members': [f'a{i}'],
                                 'descriptor': vs[f'a{i}'], 'segments': []}
                  for i in range(4)}
        mean = np.mean(list(vs.values()), axis=0).tolist()
        parents = {'xpar-p': {'children': sorted(leaves),
                              'members': sorted(vs), 'descriptor': mean}}
        e = RepairEngine(copy.deepcopy(vs), copy.deepcopy(leaves),
                         copy.deepcopy(parents),
                         RepairConfig(enabled=True, edge_threshold=.8))
        e.touch(parent_ids=['xpar-p'])
        before = canonical(e.snapshot())
        debt_before = len(e.queue)

        def reject(record):
            raise RuntimeError(
                'repair: op deadbeef retryable:Retryable: '
                'REJECT_CAPACITY(deadline): explicit retryable capacity error')
        e.commit = reject
        with self.assertRaises(RuntimeError) as ctx:
            e.repair_step(10 ** 8)
        self.assertIn('REJECT_CAPACITY', str(ctx.exception))
        self.assertEqual(before, canonical(e.snapshot()))
        self.assertEqual(debt_before, len(e.queue))

    def test_harness_patch_is_exactly_the_one_line(self):
        src = (WORKSPACE / 'tools' / 'product_pilot.py').read_text()
        fixed = ('rejection = s.drain(max_documents=1, budget_seconds=60, '
                 'repair_budget=0)')
        self.assertEqual(src.count(fixed), 1)
        self.assertNotIn(
            'rejection = s.drain(max_documents=1, budget_seconds=60)\n', src)
        self.assertIn('repair_units_per_drain=250000000', src)
        self.assertIn('batched_drain=True', src)


if __name__ == '__main__':
    unittest.main()
