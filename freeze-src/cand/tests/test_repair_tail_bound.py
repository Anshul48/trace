"""Focused synthetic tests for the repair-tail HARNESS control bound.

Tiny fake repair-hook simulation only: no datasets, no stores, no product
logic. Exercises tools/product_pilot.py::repair_tail_bound and
::run_repair_tail, the exact helpers the pilot's repair-to-zero block uses.
"""
import sys
import types
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / 'tools'
sys.path.insert(0, str(TOOLS_DIR))
if 'numpy' not in sys.modules:
    try:
        import numpy  # noqa: F401
    except ImportError:
        sys.modules['numpy'] = types.ModuleType('numpy')

from product_pilot import REPAIR_TAIL_DRAIN_CAP, repair_tail_bound, run_repair_tail


class FakeTail:
    """Synthetic repair hook: read() reports debt, drain() applies one step."""

    def __init__(self, debt, step):
        self.debt = debt
        self.step = step
        self.calls = 0

    def read(self):
        return self.debt

    def drain(self, iteration):
        self.calls += 1
        processed, self.debt = self.step(self.debt)
        return processed, self.debt


def steady_step(per_call):
    def step(debt):
        done = min(per_call, debt)
        return done, debt - done
    return step


class RepairTailBoundTest(unittest.TestCase):
    def test_observed_1m_tail_reaches_zero(self):
        bound = repair_tail_bound(1060, 'local')
        self.assertGreaterEqual(bound, 36)
        tail = FakeTail(1060, steady_step(30))
        result = run_repair_tail(tail.read, tail.drain, bound)
        self.assertEqual(result['iterations'], 36)
        self.assertEqual(result['final_debt'], 0)

    def test_no_progress_fails_fast(self):
        tail = FakeTail(100, lambda debt: (0, debt))
        with self.assertRaises(AssertionError):
            run_repair_tail(tail.read, tail.drain, repair_tail_bound(100, 'local'))
        self.assertLessEqual(tail.calls, 2)

    def test_growing_debt_cannot_run_forever(self):
        tail = FakeTail(50, lambda debt: (5, debt + 10))
        with self.assertRaises(AssertionError) as ctx:
            run_repair_tail(tail.read, tail.drain, 25)
        self.assertIn('bounded drains', str(ctx.exception))
        self.assertEqual(tail.calls, 25)

    def test_zero_start_clean(self):
        tail = FakeTail(0, steady_step(30))
        result = run_repair_tail(tail.read, tail.drain, repair_tail_bound(0, 'local'))
        self.assertEqual(result, {**result, 'iterations': 0, 'final_debt': 0})
        self.assertEqual(tail.calls, 0)

    def test_bound_and_final_debt_mandatory(self):
        for profile in ('local', 'vm'):
            bound = repair_tail_bound(1060, profile)
            self.assertIsInstance(bound, int)
            self.assertGreaterEqual(bound, REPAIR_TAIL_DRAIN_CAP)
        self.assertGreater(repair_tail_bound(100_000, 'vm'), repair_tail_bound(1060, 'vm'))
        tail = FakeTail(90, steady_step(30))
        result = run_repair_tail(tail.read, tail.drain, repair_tail_bound(90, 'local'))
        for key in ('initial_debt', 'max_drains', 'iterations', 'final_debt'):
            self.assertIn(key, result)
        self.assertEqual((result['initial_debt'], result['final_debt']), (90, 0))


if __name__ == '__main__':
    unittest.main()
