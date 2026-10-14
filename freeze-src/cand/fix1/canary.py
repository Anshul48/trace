"""Self-validating canary for Fix-1 drain instrumentation (tiny fixture only).

Drives a 12-doc synthetic store through the fork harness with
instrumentation ON, re-measuring every drain cycle with its own timer,
then validates each JSONL record against the independent wall (15%
tolerance) and reconciles attempted/committed counts with the fixture
ledger.

Exit codes: 0 VALID / 1 NO-GO / 3 timeout (600 s fail-closed wall).
Run: nice -n 19 <venv-python> -B canary.py --out <dir>
"""
import argparse
import hashlib
import json
import os
import random
import resource
import signal
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORK = HERE / 'fork'
sys.path.insert(0, str(FORK / 'tools'))
sys.path.insert(0, str(FORK / 'fork' / 'tl-sys'))
sys.path.insert(0, str(FORK / 'fork' / 'tl-candidate-batch' / 'candidate'))

import drain_instrument as di  # noqa: E402

N_DOCS = 12
CYCLE_DOCS = 4
TIMEOUT_S = 600
TOL = 0.15


def _timeout(signum, frame):
    print('CANARY TIMEOUT', flush=True)
    sys.exit(3)


class FakeEmbed:
    """Deterministic memoized unit-norm float32 vectors (dim 384)."""

    def __init__(self, dim=384, seed=20261012):
        self.dim, self.memo = dim, {}
        self.seed = seed

    def __call__(self, texts):
        import numpy as np
        out = []
        for t in texts:
            if t not in self.memo:
                rng = random.Random(
                    int(hashlib.sha256(
                        ('%d:%s' % (self.seed, t)).encode()).hexdigest(), 16))
                vec = np.asarray([rng.gauss(0, 1) for _ in range(self.dim)],
                                 dtype=np.float64)
                vec = vec / float(np.linalg.norm(vec))
                self.memo[t] = vec.astype(np.float32).tolist()
            out.append(self.memo[t])
        return out


def build(root):
    from tlsys.store_if import TLStore
    from tlsys.local_repair import RepairConfig
    from tlsys.repair_hook import TLStoreRepairHook
    from tlsys.org_service import OrganizationService, ServiceConfig
    tl = TLStore(str(root / 'store'), create=True,
                 lease_owner='fix1-canary', local_repair=True,
                 repair_config=RepairConfig(edge_threshold=.45,
                                            leaf_threshold=.55))
    config = ServiceConfig(enabled=True, max_documents_per_drain=4096,
                           drain_budget_seconds=60,
                           repair_units_per_drain=250_000_000,
                           await_visibility_on_ack=True, batched_drain=True)
    service = OrganizationService(tl, config=config, keyed_state=True,
                                  repair=TLStoreRepairHook(tl))
    return tl, service


def fixture_docs(n=N_DOCS):
    words = ('alpha', 'beta', 'gamma', 'delta', 'sport', 'medic',
             'harbor', 'quartz', 'velvet', 'cobalt')
    docs = []
    for i in range(n):
        body = ' '.join(words[(i + k) % len(words)] for k in range(60))
        docs.append(('fix1-doc-%02d' % i,
                     'canary document %d %s' % (i, body)))
    return docs


def run_canary(out_dir):
    """Run the instrumented drain; return (rows, remeasured, ledger_docs)."""
    from tlsys.org_service import OrganizationService  # noqa: F401 (warm)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='fix1-canary-'))
    tl, service = build(tmp)
    embed = FakeEmbed()
    docs = fixture_docs()
    try:
        service.ingest_visible(docs, embed)
        service.last_future.result()
        recorder = di.DrainRecorder(out, enabled=True)

        def await_pub():
            service.last_future.result()

        remeasured, idx = {}, 0
        while service.pending():
            start = time.perf_counter()
            report = di.drain_one_cycle(service, tl, 'canary_drain', idx,
                                        recorder, await_pub,
                                        max_documents=CYCLE_DOCS)
            remeasured[idx] = time.perf_counter() - start
            if report['failed']:
                raise RuntimeError(str(report))
            if not report['attempted']:
                raise RuntimeError('drain made no progress')
            idx += 1
        rows = di.read_records(recorder.path)
        (out / 'remeasured.json').write_text(json.dumps(
            {str(k): v for k, v in remeasured.items()}, indent=2))
        (out / 'ledger.json').write_text(json.dumps(
            {'docs': [d for d, _ in docs], 'n_docs': len(docs)}, indent=2))
        return rows, remeasured, len(docs)
    finally:
        try:
            service.close()
        except Exception:
            pass
        try:
            tl.close()
        except Exception:
            pass


def check_existing(out_dir):
    """Re-validate a previous canary out dir (falsifier path). Exit 0/1."""
    out = Path(out_dir)
    rows = di.read_records(out / 'drain-cycles.jsonl')
    remeasured = {int(k): v for k, v in json.loads(
        (out / 'remeasured.json').read_text()).items()}
    ledger = json.loads((out / 'ledger.json').read_text())
    errors = di.validate_records(rows, ledger['n_docs'], remeasured, TOL)
    print(json.dumps({'status': 'VALID' if not errors else 'NO-GO',
                      'errors': errors[:5]}, indent=2), flush=True)
    return 0 if not errors else 1


def main():
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(TIMEOUT_S)
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--check', action='store_true',
                    help='re-validate an existing --out dir instead of running')
    args = ap.parse_args()
    if args.check:
        try:
            return check_existing(args.out)
        except Exception as exc:
            print('NO-GO exception: %r' % (exc,), flush=True)
            return 1
    started = time.perf_counter()
    try:
        rows, remeasured, ledger_docs = run_canary(args.out)
    except SystemExit as exc:
        raise
    except Exception as exc:
        print('NO-GO exception: %r' % (exc,), flush=True)
        return 1
    errors = di.validate_records(rows, ledger_docs, remeasured, TOL)
    wall = time.perf_counter() - started
    rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    summary = {'records': len(rows), 'ledger_docs': ledger_docs,
               'wall_s': wall, 'peak_rss_mib': rss_mib,
               'nice': os.getpriority(os.PRIO_PROCESS, 0),
               'errors': errors}
    (args.out / 'canary-summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({'status': 'VALID' if not errors else 'NO-GO',
                      'records': len(rows), 'wall_s': round(wall, 3),
                      'peak_rss_mib': round(rss_mib, 1),
                      'errors': errors[:5]}, indent=2), flush=True)
    signal.alarm(0)
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
