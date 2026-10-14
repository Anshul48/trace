"""Synthetic budget-cost tests for the staged-admission repair candidate.

Real NumPy, CPU-small only: every test uses <= 128 atoms, small dimension,
seeded RNG. Run: OMP_NUM_THREADS=1 python -m unittest discover -s tests
"""
import importlib.util
import os
import unittest

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CANDIDATE = os.path.join(THIS_DIR, '..', 'fork', 'tl-sys', 'tlsys', 'local_repair.py')

spec = importlib.util.spec_from_file_location('candidate_local_repair', CANDIDATE)
lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)

D = 8
rng = np.random.default_rng(20261012)


def mean_of(vecs):
    return np.asarray(vecs, dtype=np.float64).mean(axis=0).tolist()


def leaf_entry(members, vectors):
    members = sorted(members)
    return {'members': members,
            'descriptor': mean_of([vectors[a] for a in members]) if members else [0.0] * D,
            'segments': []}


def parent_entry(children, leaves):
    children = sorted(children)
    members = sorted({a for lid in children for a in leaves[lid]['members']})
    return {'children': children, 'members': members,
            'descriptor': mean_of([VEC[a] for a in members]) if members else [0.0] * D}


VEC = {}


def cfg(**kw):
    args = dict(enabled=True, dimension=D)
    args.update(kw)
    return lr.RepairConfig(**args)


class Spy:
    """Pairs each charged actual with its key's outstanding reservation.

    Skipped (infeasible) keys reserve but never produce a record; their
    reservations stay outstanding and uncharged, which is exactly the
    no-charge-on-refusal property.
    """

    def __init__(self, eng):
        from collections import deque
        self.res = {}
        self.pairs = []
        self.act_log = []
        orig = eng._estimate

        def spy(key):
            cost = orig(key)
            self.res.setdefault(tuple(key), deque()).append(cost)
            return cost

        eng._estimate = spy

    def hook(self, record):
        actual = record['coordinates']
        expect = sum(record['work'].values()) * D
        assert actual == expect, (actual, expect)
        key = tuple(record['consumed'])
        res = self.res[key].popleft()  # KeyError if charged w/o reservation
        self.pairs.append((key, res, actual))
        self.act_log.append((key, actual))

    def assert_staged(self, test):
        test.assertTrue(self.pairs)
        for key, res, act in self.pairs:
            test.assertLessEqual(act, res)


class BudgetTests(unittest.TestCase):
    def test_healthy_noop_charges_actual(self):
        global VEC
        VEC = {'a%d' % i: [1.0] * D for i in range(6)}
        leaves = {'L1': leaf_entry(['a0', 'a1', 'a2'], VEC),
                  'L2': leaf_entry(['a3', 'a4', 'a5'], VEC)}
        parents = {'P1': {'children': ['L1', 'L2'],
                          'members': sorted(['a%d' % i for i in range(6)]),
                          'descriptor': [1.0] * D}}
        eng = lr.RepairEngine(dict(VEC), leaves, parents, cfg())
        eng.touch(['L1', 'L2'], ['P1'])
        est = sum(eng._estimate(k) for k in eng.queue)
        spy = Spy(eng)
        eng.commit = spy.hook
        out = eng.repair_step(10 ** 9)
        self.assertEqual(out['debt'], 0)
        self.assertEqual(out['checked'], 3)
        self.assertIsNone(out['blocked'])
        spy.assert_staged(self)
        self.assertEqual(out['spent'], sum(a for _, a in spy.act_log))
        self.assertEqual(eng.counts['coordinates'], out['spent'])
        self.assertLess(out['spent'], est)  # worst case NOT charged

    def test_head_of_line_block_preserved(self):
        global VEC
        VEC = {'a%d' % i: [1.0] * D for i in range(4)}
        leaves = {'L1': leaf_entry(['a0', 'a1'], VEC),
                  'L2': leaf_entry(['a2', 'a3'], VEC)}
        parents = {'P1': {'children': ['L1', 'L2'],
                          'members': sorted(VEC), 'descriptor': [1.0] * D}}
        eng = lr.RepairEngine(dict(VEC), leaves, parents, cfg())
        eng.touch(['L1'])  # also enqueues parent P1 via touch cascade
        cost = eng._estimate(('leaf', 'L1'))
        out = eng.repair_step(cost - 1)
        self.assertEqual(out['checked'], 0)
        self.assertEqual(out['spent'], 0)
        self.assertEqual(out['blocked'], 'budget')
        self.assertEqual(list(eng.queue), [('leaf', 'L1'), ('parent', 'P1')])

    def test_refund_admits_later_keys(self):
        global VEC
        VEC = {'a%d' % i: [1.0] * D for i in range(8)}
        leaves = {'L1': leaf_entry(['a0', 'a1', 'a2', 'a3'], VEC),
                  'L2': leaf_entry(['a4', 'a5', 'a6', 'a7'], VEC)}
        parents = {'P1': {'children': ['L1', 'L2'],
                          'members': sorted(VEC), 'descriptor': [1.0] * D}}
        eng = lr.RepairEngine(dict(VEC), leaves, parents, cfg())
        eng.touch(['L1', 'L2'])
        eng.queue.pop(('parent', 'P1'))  # isolate the two leaf keys
        e1 = eng._estimate(('leaf', 'L1'))
        e2 = eng._estimate(('leaf', 'L2'))
        # Measure actuals with an unbounded run on a twin engine.
        twin = lr.RepairEngine(dict(VEC),
                               {k: dict(v) for k, v in leaves.items()},
                               {k: dict(v) for k, v in parents.items()}, cfg())
        twin.touch(['L1', 'L2'])
        twin.queue.pop(('parent', 'P1'))
        twin.repair_step(10 ** 9)
        a_total = twin.counts['coordinates']
        budget = e1 + e2 - 1  # unaffordable under old charge-all-reservation
        self.assertGreater(e1 + e2, a_total)
        spy = Spy(eng)
        eng.commit = spy.hook
        out = eng.repair_step(budget)
        self.assertEqual(out['checked'], 2)
        self.assertEqual(out['debt'], 0)
        self.assertLessEqual(out['spent'], budget)
        spy.assert_staged(self)

    def test_zero_work_noop_terminates(self):
        eng = lr.RepairEngine({}, {'L0': {'members': [], 'descriptor': [0.0] * D,
                                          'segments': []}},
                              {'P0': {'children': ['L0'], 'members': [],
                                      'descriptor': [0.0] * D}}, cfg())
        eng.touch(['L0'])  # queues L0 plus parent P0 via touch cascade
        cost = eng._estimate(('leaf', 'L0')) + eng._estimate(('parent', 'P0'))
        spy = Spy(eng)
        eng.commit = spy.hook
        out = eng.repair_step(cost)
        self.assertEqual(out['checked'], 2)
        self.assertEqual(out['debt'], 0)
        self.assertIsNone(out['blocked'])
        spy.assert_staged(self)
        self.assertEqual(spy.act_log[0][0], ('leaf', 'L0'))
        self.assertEqual(spy.act_log[0][1], 0)  # zero work, zero charge


class LifecycleTests(unittest.TestCase):
    def _healthy(self, n=4):
        global VEC
        VEC = {'a%d' % i: [1.0] * D for i in range(n)}
        leaves = {'L1': leaf_entry(sorted(VEC), VEC)}
        parents = {'P1': {'children': ['L1'], 'members': sorted(VEC),
                          'descriptor': [1.0] * D}}
        return lr.RepairEngine(dict(VEC), leaves, parents, cfg())

    def test_commit_failure_rolls_back(self):
        eng = self._healthy()
        eng.touch(['L1'])
        before = (list(eng.queue), eng.generation, dict(eng.counts))

        def boom(record):
            raise RuntimeError('simulated commit refusal')

        eng.commit = boom
        with self.assertRaises(RuntimeError):
            eng.repair_step(10 ** 9)
        self.assertEqual(list(eng.queue), before[0])  # queue untouched
        self.assertEqual(eng.generation, before[1])
        self.assertEqual(dict(eng.counts), before[2])  # no charge, no counts
        eng.commit = lambda record: None  # retry succeeds
        out = eng.repair_step(10 ** 9)
        self.assertEqual(out['checked'], 2)  # L1 plus cascaded P1
        self.assertEqual(out['debt'], 0)

    def test_replay_is_idempotent(self):
        eng = self._healthy()
        eng.touch(['L1'])
        seen = []
        eng.commit = seen.append
        eng.repair_step(10 ** 9)
        self.assertEqual(len(seen), 2)  # L1 plus cascaded P1
        gen, counts = eng.generation, dict(eng.counts)
        eng.apply(seen[-1])  # exact replay of latest revision: no-op
        self.assertEqual(eng.generation, gen)
        self.assertEqual(dict(eng.counts), counts)

    def test_overcap_parent_requeues_leaf_same_call(self):
        global VEC
        # One tight cluster: the 6-member leaf splits into cap-sized pieces,
        # all cohesive, so the same-call parent retry settles as one no-op.
        r = np.random.default_rng(7)
        VEC = {}
        for i in range(6):
            VEC['a%d' % i] = (np.eye(D)[0] + 0.01 * r.normal(size=D)).tolist()
        c = cfg(max_leaf_members=4, max_children=4)
        leaves = {'L1': leaf_entry(sorted(VEC), VEC)}
        parents = {'P1': {'children': ['L1'], 'members': sorted(VEC),
                          'descriptor': mean_of(list(VEC.values()))}}
        eng = lr.RepairEngine(dict(VEC), leaves, parents, c)
        spy = Spy(eng)
        eng.commit = spy.hook
        eng.touch(parent_ids=['P1'])  # only the parent is queued
        out = eng.repair_step(10 ** 9)
        # Parent infeasible locally -> temp leaf staged, healed, parent retried.
        self.assertEqual(out['checked'], 2)
        self.assertEqual(out['debt'], 0)
        for lid, leaf in eng.leaves.items():
            self.assertLessEqual(len(leaf['members']), 4)
        self.assertGreater(eng.counts.get('leaf_split', 0), 0)
        spy.assert_staged(self)
        self.assertLessEqual(out['spent'], 10 ** 9)

    def test_infeasible_debt_preserved(self):
        global VEC
        VEC = {'a%d' % i: [1.0] * D for i in range(60)}  # 60 <= 128 atoms
        c = cfg(max_leaf_members=3)  # 60 members -> 20 groups > 16: infeasible
        leaves = {'LBIG': leaf_entry(sorted(VEC), VEC)}
        parents = {'P1': {'children': ['LBIG'], 'members': sorted(VEC),
                          'descriptor': [1.0] * D}}
        eng = lr.RepairEngine(dict(VEC), leaves, parents, c)
        eng.touch(['LBIG'])  # also enqueues parent P1 via touch cascade
        out = eng.repair_step(10 ** 12)
        self.assertEqual(out['checked'], 0)
        self.assertEqual(out['spent'], 0)  # refusals did zero vector work
        self.assertEqual(out['debt'], 2)  # explicit debt, queue/order kept
        self.assertEqual(list(eng.queue), [('leaf', 'LBIG'), ('parent', 'P1')])
        self.assertEqual(eng.generation, 0)
        self.assertEqual(out['blocked'], 'infeasible-local-two-way-split')

    def test_mixed_queue_keeps_infeasible_loses_nothing(self):
        global VEC
        VEC = {'a%d' % i: [1.0] * D for i in range(63)}
        c = cfg(max_leaf_members=3)
        big = ['a%d' % i for i in range(60)]
        small = ['a%d' % i for i in range(60, 63)]  # healthy: no touches
        leaves = {'LBIG': leaf_entry(big, VEC), 'LOK': leaf_entry(small, VEC)}
        parents = {'P1': {'children': ['LBIG', 'LOK'], 'members': sorted(VEC),
                          'descriptor': [1.0] * D}}
        eng = lr.RepairEngine(dict(VEC), leaves, parents, c)
        eng.touch(['LBIG', 'LOK'])  # touch cascade also enqueues P1
        out = eng.repair_step(10 ** 12)
        self.assertEqual(out['checked'], 1)  # feasible key applied
        # Infeasible leaf + overcap parent retained, no loss, order kept.
        self.assertEqual(out['debt'], 2)
        self.assertEqual(list(eng.queue), [('leaf', 'LBIG'), ('parent', 'P1')])
        self.assertEqual(eng.counts['checked'], 1)


if __name__ == '__main__':
    unittest.main()
