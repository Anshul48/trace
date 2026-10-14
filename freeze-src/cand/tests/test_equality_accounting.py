"""Equality/comparison work-accounting tests for the counted repair candidate.

Real NumPy, CPU-small only: every test uses <= 128 atoms, small dimension,
seeded RNG. Run: OMP_NUM_THREADS=1 python -m unittest discover -s tests
"""
import copy
import importlib.util
import os
import unittest

import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CANDIDATE = os.path.join(THIS_DIR, '..', 'fork', 'tl-sys', 'tlsys', 'local_repair.py')

spec = importlib.util.spec_from_file_location('counted_local_repair', CANDIDATE)
lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)

D = 8


def mean_of(vecs):
    return np.asarray(vecs, dtype=np.float64).mean(axis=0).tolist()


def leaf_entry(members, vectors):
    members = sorted(members)
    return {'members': members,
            'descriptor': mean_of([vectors[a] for a in members]) if members else [0.0] * D,
            'segments': []}


def parent_entry(children, leaves, vectors):
    children = sorted(children)
    members = sorted({a for lid in children for a in leaves[lid]['members']})
    return {'children': children, 'members': members,
            'descriptor': mean_of([vectors[a] for a in members]) if members else [0.0] * D}


def cfg(**kw):
    args = dict(enabled=True, dimension=D)
    args.update(kw)
    return lr.RepairConfig(**args)


class Tracer:
    """Logs per-key reservation then per-record actual in commit order."""

    def __init__(self, eng):
        self.reservations = []
        self.records = []
        orig = eng._estimate

        def spy(key):
            cost = orig(key)
            self.reservations.append((tuple(key), cost))
            return cost

        eng._estimate = spy

    def hook(self, record):
        self.records.append(record)


class EqualityTests(unittest.TestCase):
    def test_leaf_identity_guard_positive_charge(self):
        # Within-cap incoherent leaf: partition proposes a split, then the
        # identity guard evaluates (and counts) comparisons before rejecting
        # identical-only suppression. Sorted members a0==a1!=a2: the all()
        # executes 3 comparisons (self, a1, a2) then short-circuits.
        e0 = [1.0] + [0.0] * (D - 1)
        e1 = [0.0, 1.0] + [0.0] * (D - 2)
        vec = {'a0': list(e0), 'a1': list(e0), 'a2': list(e1), 'a3': list(e1)}
        leaves = {'L1': leaf_entry(sorted(vec), vec)}
        parents = {'P1': parent_entry(['L1'], leaves, vec)}
        eng = lr.RepairEngine(dict(vec), leaves, parents,
                              cfg(max_leaf_members=4, leaf_threshold=0.99))
        eng.touch(['L1'])
        rec = eng._proposal(('leaf', 'L1'))
        self.assertIsNotNone(rec)
        self.assertEqual(rec['work']['equality_rows'], 2 * 3)
        # _proposal carries raw work; repair_step charges sum(work)*dimension.
        self.assertGreater(sum(rec['work'].values()) * D, 0)

    def test_parent_identity_guard_positive_charge(self):
        # Two-cluster children force the parent split path (edge_threshold=-1
        # disables moves; cohesion 0.999 forces the split branch); the any()
        # guard then executes (and counts) comparisons before keeping parts.
        # Sorted kids L0..L2 ~= e0, L3..L5 ~= e1: any() runs 4 comparisons
        # (self, L1, L2, then L3 differs) before short-circuiting.
        e0 = [1.0] + [0.0] * (D - 1)
        e1 = [0.0, 1.0] + [0.0] * (D - 2)
        vec = {}
        for i in range(6):
            base = e0 if i < 3 else e1
            vec['a%d' % i] = list(base)
        leaves = {'L%d' % i: leaf_entry(['a%d' % i], vec) for i in range(6)}
        parents = {'P1': parent_entry(sorted(leaves), leaves, vec)}
        c = cfg(max_children=16, edge_threshold=-1.0, parent_cohesion_threshold=0.999)
        eng = lr.RepairEngine(dict(vec), leaves, parents, c)
        rec = eng._proposal(('parent', 'P1'))
        self.assertIsNotNone(rec)
        self.assertEqual(rec['work']['equality_rows'], 2 * 4)
        # _proposal carries raw work; repair_step charges sum(work)*dimension.
        self.assertGreater(sum(rec['work'].values()) * D, 0)

    def test_totals_staged_inequality_end_to_end(self):
        r = np.random.default_rng(13)
        vec = {}
        for i in range(24):
            vec['a%d' % i] = (np.eye(D)[i % D] + 0.01 * r.normal(size=D)).tolist()
        g = [sorted(vec)[i::3] for i in range(3)]
        leaves = {'L%d' % i: leaf_entry(m, vec) for i, m in enumerate(g)}
        parents = {'P1': parent_entry(sorted(leaves), leaves, vec)}
        eng = lr.RepairEngine(dict(vec), leaves, parents, cfg())
        eng.touch(sorted(leaves), ['P1'])
        budget = 10 ** 9
        tracer = Tracer(eng)
        eng.commit = tracer.hook
        out = eng.repair_step(budget)
        self.assertTrue(tracer.records)
        spent = 0
        seen = 0
        for (key, res), rec in zip(tracer.reservations, tracer.records):
            self.assertEqual(tuple(rec['consumed']), key)
            actual = rec['coordinates']
            self.assertEqual(actual, sum(rec['work'].values()) * D)
            self.assertLessEqual(actual, res)  # actual <= reservation
            self.assertLessEqual(res, budget - spent)  # reservation <= remaining
            spent += actual
            seen += 1
        self.assertEqual(seen, out['checked'])
        self.assertEqual(out['spent'], spent)
        self.assertEqual(eng.counts['coordinates'], spent)
        self.assertEqual(eng.counts['equality_rows'],
                         sum(r['work'].get('equality_rows', 0) for r in tracer.records))

    def test_old_record_and_snapshot_safe(self):
        vec = {'a%d' % i: [1.0] * D for i in range(4)}
        leaves = {'L1': leaf_entry(sorted(vec), vec)}
        parents = {'P1': parent_entry(['L1'], leaves, vec)}
        eng = lr.RepairEngine(dict(vec), leaves, parents, cfg())
        eng.touch(['L1'])
        rec = eng._proposal(('leaf', 'L1'))
        old = copy.deepcopy(rec)
        old['work'].pop('equality_rows', None)  # pre-equality replay record
        eng.apply(old)  # must not KeyError; adds zero equality
        self.assertEqual(eng.counts['equality_rows'], 0)
        snap = eng.snapshot()
        snap['counts'].pop('equality_rows', None)  # old snapshot without counter
        re = lr.RepairEngine.restore(snap, dict(vec))
        self.assertEqual(re.counts['equality_rows'], 0)
        re.touch(['L1'])
        out = re.repair_step(10 ** 9)  # restored engine keeps working
        self.assertEqual(out['debt'], 0)

    def test_zero_work_noop_terminates_uncharged(self):
        eng = lr.RepairEngine({}, {'L0': {'members': [], 'descriptor': [0.0] * D,
                                          'segments': []}},
                              {'P0': {'children': ['L0'], 'members': [],
                                      'descriptor': [0.0] * D}}, cfg())
        eng.touch(['L0'])
        seen = []
        eng.commit = seen.append
        out = eng.repair_step(10 ** 9)
        self.assertEqual(out['checked'], 2)
        self.assertEqual(out['debt'], 0)
        self.assertEqual(seen[0]['work']['equality_rows'], 0)
        self.assertEqual(seen[0]['coordinates'], 0)

    def test_refused_commit_no_state_no_charge(self):
        vec = {'a%d' % i: [1.0] * D for i in range(4)}
        leaves = {'L1': leaf_entry(sorted(vec), vec)}
        parents = {'P1': parent_entry(['L1'], leaves, vec)}
        eng = lr.RepairEngine(dict(vec), leaves, parents, cfg())
        eng.touch(['L1'])
        before = (list(eng.queue), eng.generation, dict(eng.counts))

        def boom(record):
            raise RuntimeError('simulated commit refusal')

        eng.commit = boom
        with self.assertRaises(RuntimeError):
            eng.repair_step(10 ** 9)
        self.assertEqual(list(eng.queue), before[0])
        self.assertEqual(eng.generation, before[1])
        self.assertEqual(dict(eng.counts), before[2])


if __name__ == '__main__':
    unittest.main()
