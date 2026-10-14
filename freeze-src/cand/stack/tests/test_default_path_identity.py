"""Default-path identity: every knob absent/False reproduces base behavior.

Harness-level (no store): parser defaults, resolve matrix, config
defaults, loop-signature defaults, fix-6 OFF-branch equivalence with the
literal full sort. Store-level identity (fix-1 drain reports, fix-2 full
receipts, fix-5 noop) is covered by fix1/tests + test_fix2/test_fix5 and
re-asserted here by import where cheap.
"""
import inspect
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_common as C  # noqa: E402

import drain_instrument as di  # noqa: E402
import product_pilot as pilot  # noqa: E402


def main():
    for var in ('PILOT_DRAIN_INSTRUMENT', 'PILOT_DRAIN_BUDGET_S'):
        os.environ.pop(var, None)

    # Fix-1 OFF defaults (source + behavior, fix1-test convention).
    src = Path(pilot.__file__).read_text()
    assert "'--drain-instrument', action='store_true', default=False" in src
    from argparse import Namespace
    assert di.instrument_enabled(Namespace(drain_instrument=False)) is False

    # Fix-3 defaults: budget 60 (flag None + env absent), batched mode.
    assert pilot.DRAIN_ALL_BUDGET_S_DEFAULT == 60
    assert pilot.resolve_drain_budget(None) == 60
    assert "'--drain-budget-s', type=int, default=None" in src
    assert "'--drain-unbatched', action='store_true', default=False" in src
    cfg = pilot.service_config()
    assert cfg.batched_drain is True
    assert cfg.drain_budget_seconds == 60
    assert cfg.max_documents_per_drain == 4096
    sig = inspect.signature(di.run_drain_loop)
    assert sig.parameters['max_documents'].default == 4096
    assert sig.parameters['budget_seconds'].default == 60
    sig1 = inspect.signature(di.drain_one_cycle)
    assert sig1.parameters['max_documents'].default == 4096
    assert sig1.parameters['budget_seconds'].default == 60

    # Fix-6 OFF branch == literal full sort (branch byte-untouched).
    import numpy as np
    from tlsys.org_publication import pending_order
    rng = np.random.default_rng(99)
    for trial in range(60):
        n = int(rng.integers(1, 120))
        k = int(rng.integers(0, n + 1))
        scores = rng.normal(size=n) if trial % 2 else np.zeros(n)
        ids = tuple('x%04d' % i for i in rng.permutation(n))
        ref = sorted(range(n), key=lambda i: (-scores[i], ids[i]))[:k]
        assert list(pending_order(scores, ids, k, False)) == ref, trial
    # ... and the default is now ON.
    from tlsys.org_publication import PreparedFacade
    assert inspect.signature(
        PreparedFacade.__init__).parameters[
            'fast_pending_topk'].default is True

    print('defaults: instrument OFF, budget 60, batched, loop 4096/60, '
          'sort-OFF==literal (60/60), sort default ON')
    print('PASS test_default_path_identity')
    return 0


if __name__ == '__main__':
    sys.exit(main())
