"""Fix-3 knob tests: resolve matrix, fail-closed, derivation, forwarding.

Synthetic only: stub service for budget forwarding, synthetic jsonl for
the file derivation. No corpus.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_common as C  # noqa: E402

import drain_instrument as di  # noqa: E402
import product_pilot as pilot  # noqa: E402


class StubService:
    """Minimal drain/pending surface recording per-cycle budgets."""

    def __init__(self, cycles):
        self.cycles = list(cycles)
        self.budgets = []
        self.maxdocs = []
        self.publisher = None

    def pending(self):
        return tuple('doc-%d' % i for i in range(len(self.cycles)))

    def drain(self, max_documents=None, budget_seconds=None):
        self.budgets.append(budget_seconds)
        self.maxdocs.append(max_documents)
        n = self.cycles.pop(0)
        return {'attempted': n, 'completed': ['doc-%d' % i for i in range(n)],
                'failed': {}, 'remaining': len(self.cycles),
                'wall_s': 0.001}


def main():
    for var in ('PILOT_DRAIN_BUDGET_S',):
        os.environ.pop(var, None)

    # Resolve matrix: flag beats env beats default.
    assert pilot.resolve_drain_budget(None) == 60
    assert pilot.resolve_drain_budget(965) == 965
    os.environ['PILOT_DRAIN_BUDGET_S'] = '965'
    assert pilot.resolve_drain_budget(None) == 965
    assert pilot.resolve_drain_budget(60) == 60
    del os.environ['PILOT_DRAIN_BUDGET_S']
    for bad in ('0', '-5', 'abc', '', '60.5'):
        os.environ['PILOT_DRAIN_BUDGET_S'] = bad
        try:
            pilot.resolve_drain_budget(None)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError('no fail-closed for %r' % bad)
        del os.environ['PILOT_DRAIN_BUDGET_S']
    try:
        pilot.resolve_drain_budget(0)
    except ValueError:
        pass
    else:
        raise AssertionError('no fail-closed for 0')

    # Derivation: ceil(2*max); R8 instance 482.006 -> 965.
    assert di.derive_budget_candidate([482.006, 470.8]) == 965
    assert di.derive_budget_candidate([60.0]) == 120
    assert di.derive_budget_candidate([0.4]) == 1
    for bad in ([], [0], [-3], ['x'], [None]):
        try:
            di.derive_budget_candidate(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('no fail-closed for %r' % (bad,))
    tmp = Path(tempfile.mkdtemp(prefix='fix3-deriv-'))
    rows = [{'type': 'cycle', 'phase': 'p', 'cycle': i, 'wall_s': w}
            for i, w in enumerate((68.11, 18.63, 81.15))]
    (tmp / 'drain-cycles.jsonl').write_text(
        '\n'.join(json.dumps(r) for r in rows) + '\n')
    got = di.derive_budget_from_cycles_file(tmp / 'drain-cycles.jsonl')
    assert got['candidate_budget_s'] == 163, got  # ceil(2*81.15)
    assert got['cycles'] == 3 and abs(got['max_cycle_wall_s'] - 81.15) < 1e-9

    # Forwarding: knob value reaches s.drain; default stays 60/4096.
    svc = StubService([2, 1])
    walls = {}
    n = di.run_drain_loop(svc, None, 'knob', walls, lambda: None,
                          recorder=None, budget_seconds=965)
    assert n == 2 and svc.budgets == [965, 965], svc.budgets
    assert svc.maxdocs == [4096, 4096], svc.maxdocs
    svc2 = StubService([1])
    di.run_drain_loop(svc2, None, 'dflt', {}, lambda: None, recorder=None)
    assert svc2.budgets == [60] and svc2.maxdocs == [4096]

    # service_config threading (default batched preserved).
    assert pilot.service_config().batched_drain is True
    assert pilot.service_config(batched_drain=False).batched_drain is False

    print('fix3: resolve 60/965/flag>env, fail-closed 6/6, derive 965/163, '
          'forward 965+default60, batched default')
    print('PASS test_fix3_knob')
    return 0


if __name__ == '__main__':
    sys.exit(main())
