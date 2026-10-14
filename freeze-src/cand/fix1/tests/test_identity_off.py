"""Identity-OFF test: default path behaves exactly like the unmodified base.

Compares a manual replication of the base drain_all statements against
di.run_drain_loop with a DISABLED recorder on identical synthetic
fixtures, and asserts no cycles file is created when OFF.
"""
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix1_common import (OWN, PY, close, di, final_state, fresh_service,
                         ingest_all)


def base_loop(service):
    """Verbatim base drain_all statements (product_pilot.py pre-fix)."""
    cycles, count, reports = 0, 0, []

    def await_publication():
        service.last_future.result()

    while service.pending():
        report = service.drain(max_documents=4096, budget_seconds=60)
        await_publication()
        if report['failed']:
            raise RuntimeError(str(report))
        if not report['attempted']:
            raise RuntimeError('drain made no progress')
        cycles += 1
        count += report['attempted']
        reports.append({k: report[k] for k in
                        ('attempted', 'completed', 'failed', 'remaining')})
    return cycles, count, reports


def main():
    # flag default + env default both OFF
    import product_pilot as pilot
    assert pilot.argparse is not None
    import argparse as _ap
    assert instrument_default_off(pilot), 'flag default must be False'
    for var in ('PILOT_DRAIN_INSTRUMENT',):
        os.environ.pop(var, None)
    assert di.instrument_enabled(Namespace(drain_instrument=False)) is False
    rec = di.DrainRecorder(Path(tempfile.mkdtemp()), enabled=False)
    rec.append({'type': 'cycle'})
    assert not rec.path.exists(), 'disabled recorder must create no file'

    # behavioral equivalence on identical fixtures
    tmp_a = tempfile.mkdtemp(prefix='fix1-ident-a-')
    tmp_b = tempfile.mkdtemp(prefix='fix1-ident-b-')
    tl_a, s_a = fresh_service(tmp_a)
    tl_b, s_b = fresh_service(tmp_b)
    try:
        docs_a, docs_b = ingest_all(s_a), ingest_all(s_b)
        assert [d for d, _ in docs_a] == [d for d, _ in docs_b]
        out_b = Path(tempfile.mkdtemp(prefix='fix1-ident-out-'))
        walls = {}
        cycles_a, count_a, reps_a = base_loop(s_a)
        rec_b = di.DrainRecorder(out_b, enabled=False)
        cycles_b = di.run_drain_loop(
            s_b, tl_b, 'drain', walls,
            lambda: s_b.last_future.result(), recorder=rec_b)
        assert (cycles_a, count_a) == (cycles_b, len(docs_b)), \
            (cycles_a, count_a, cycles_b)
        assert not (out_b / di.CYCLES_FILENAME).exists(), \
            'no cycles file when OFF'
        fa, fb = final_state(s_a, tl_a), final_state(s_b, tl_b)
        # pins embed a random per-store incarnation UUID; compare the
        # deterministic tail (seq, commit count, derived label).
        assert fa['pin'][1:3] == fb['pin'][1:3], (fa, fb)
        assert fa['atoms'] == fb['atoms'] and fa['commits'] == fb['commits'], \
            (fa, fb)
        print('identity-OFF: cycles=%d docs=%d final=%r identical; no file OFF'
              % (cycles_a, count_a, fa))
    finally:
        close(s_a, tl_a)
        close(s_b, tl_b)
    print('PASS test_identity_off')
    return 0


def instrument_default_off(pilot):
    import io
    from contextlib import redirect_stderr
    parser = None
    # rebuild the parser the same way main does would run the world; instead
    # inspect source default for --drain-instrument
    src = Path(pilot.__file__).read_text()
    return "'--drain-instrument', action='store_true', default=False" in src


if __name__ == '__main__':
    sys.exit(main())
