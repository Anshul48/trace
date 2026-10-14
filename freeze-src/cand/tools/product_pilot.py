"""Portable product pilot (local<=1M TOK; VM 10M TOK): real-cache ingest_visible ->
organize/drain -> bounded repair -> publish faults + SIGKILL restore ->
repair-to-zero -> pinned actual-facade guided eval (all + leave-source-out).

Ported from frozen candidate tools/product_pilot_v2.py (hash 1217cf78...).
Product logic is preserved exactly: TOK_V1 complete-document corpus cache
identity, lifecycle faults, old-reader checks, 120-query all+LSO exact
float64 cosine oracle over cached FP32 vectors, matched-work accounting. Only path resolution is
parameterized (explicit args/env defaulting to file parents) plus
source/input pinning and memory observations. No product changes.

Explicit invocation (local, <=1M TOK hard cap; no local run >100k TOK while
the root pilot is active):
  PYTHONPATH=<tlsys>:<candidate>:tools nice -n 19 python -B tools/product_pilot.py
    --tokens 100000 --out <outdir> --profile local
    --source-root <candidate-root> --data-dir <pkg-data-dir>
VM 10M: same with --profile vm --tokens 10000000 (VM host only).
"""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
import resource
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

import numpy as np

TOOL_DIR = Path(__file__).resolve().parent
try:
    from preserve_deletes import install as _install_deletes
    _install_deletes()
except ImportError:
    pass

SEED = 20261011
REPAIR_UNITS = 250_000_000
EDGE, LEAF = .45, .55
F1_BUDGET_S = 5.0
TOK_CAP = {'local': 1_000_000, 'vm': 10_000_000}
REPAIR_TAIL_DRAIN_CAP = 4096

# Fix-3 harness knob: main drain_all per-cycle budget (contract
# FIX-CONTRACTS-36 §3.1; derivation ceil(2*max_measured_cycle_wall)).
# Default 60 = current behavior. Fault/child/retry drains
# (max_documents 0/1/16) stay at literal 60; product default unchanged.
DRAIN_ALL_BUDGET_S_DEFAULT = 60
DRAIN_ALL_BUDGET_S_ENV = 'PILOT_DRAIN_BUDGET_S'


def resolve_drain_budget(value):
    """Resolve the main drain_all budget knob; fail closed on bad input."""
    if value is None:
        value = os.environ.get(DRAIN_ALL_BUDGET_S_ENV,
                               DRAIN_ALL_BUDGET_S_DEFAULT)
    budget = int(value)
    if budget <= 0:
        raise ValueError(f'main drain budget must be positive seconds: {value!r}')
    return budget

# Capacity-repair qualification (harness-only): derived admission caps.
# ONLY max_delta_entries/max_dedup_rows may differ from core intake.CAPS;
# bytes/backlog/reservation/deadline/headroom preserved. Core defaults
# (intake.CAPS) are never changed (user-owned); derived values are floored
# at the core defaults, never below them.
#
# Measured rule (architect directive 2026-10-12, addendum wins):
#   cap = ceil(2.0 * max(37117/7035 * planned_atoms,
#                        37117/4424 * planned_docs))
# where 37117 commits / 7035 atoms / 4424 docs are the observed 1M-gate
# receipts and planned_* come from the run's own RealPrefix receipt in
# main(). The 2M literals below are the FALLBACK only, used (and labeled
# as fallback) when no measurement is available, e.g. unit tests calling
# qualification_caps() with no planned counts.
MEASURED_COMMITS = 37_117
MEASURED_ATOMS = 7_035
MEASURED_DOCS = 4_424
CAP_MARGIN = 2.0
# Fallback (labeled) when no measured planned counts are supplied.
QUAL_MAX_DELTA_ENTRIES = 2_000_000
QUAL_MAX_DEDUP_ROWS = 2_000_000


def cap_derivation(planned_atoms=None, planned_docs=None):
    """Derive the qualification cap from measured 1M rates (harness-only).

    Returns a dict with inputs, margin, per-basis estimates, the raw
    derived cap, per-knob floored outputs, and the source label
    ('derived' when planned counts are given, 'fallback' otherwise).
    Pure function: no imports, no global mutation.
    """
    import math as _math
    if planned_atoms is None or planned_docs is None:
        return {'source': 'fallback',
                'inputs': {'measured_commits': MEASURED_COMMITS,
                           'measured_atoms': MEASURED_ATOMS,
                           'measured_docs': MEASURED_DOCS,
                           'margin': CAP_MARGIN,
                           'planned_atoms': planned_atoms,
                           'planned_docs': planned_docs},
                'outputs': {'max_delta_entries': QUAL_MAX_DELTA_ENTRIES,
                            'max_dedup_rows': QUAL_MAX_DEDUP_ROWS}}
    atom_basis = MEASURED_COMMITS / MEASURED_ATOMS * int(planned_atoms)
    doc_basis = MEASURED_COMMITS / MEASURED_DOCS * int(planned_docs)
    raw = int(_math.ceil(CAP_MARGIN * max(atom_basis, doc_basis)))
    return {'source': 'derived',
            'inputs': {'measured_commits': MEASURED_COMMITS,
                       'measured_atoms': MEASURED_ATOMS,
                       'measured_docs': MEASURED_DOCS,
                       'margin': CAP_MARGIN,
                       'planned_atoms': int(planned_atoms),
                       'planned_docs': int(planned_docs),
                       'atom_basis_estimate': atom_basis,
                       'doc_basis_estimate': doc_basis},
            'outputs': {'derived_raw': raw}}


def qualification_caps(planned_atoms=None, planned_docs=None):
    """Harness-only admission caps for this qualification run.

    With planned counts (main passes the RealPrefix receipt values) the
    caps are derived from the measured rule, floored at the core defaults
    (never lowered). Without planned counts the 2M FALLBACK is returned
    (kept for test compatibility; not the primary path). Returns a fresh
    clone of the core intake.CAPS mapping with ONLY
    max_delta_entries/max_dedup_rows possibly raised. Never mutates
    intake.CAPS (callers may freely mutate the returned dict).
    """
    import intake as _intake
    caps = dict(_intake.CAPS)
    derivation = cap_derivation(planned_atoms, planned_docs)
    if derivation['source'] == 'fallback':
        caps['max_delta_entries'] = QUAL_MAX_DELTA_ENTRIES
        caps['max_dedup_rows'] = QUAL_MAX_DEDUP_ROWS
    else:
        raw = derivation['outputs']['derived_raw']
        caps['max_delta_entries'] = max(raw, _intake.CAPS['max_delta_entries'])
        caps['max_dedup_rows'] = max(raw, _intake.CAPS['max_dedup_rows'])
        derivation['outputs']['max_delta_entries'] = caps['max_delta_entries']
        derivation['outputs']['max_dedup_rows'] = caps['max_dedup_rows']
    # NOTE: derivation record kept out of the caps mapping (callers use
    # cap_derivation() for the record); mapping shape matches intake.CAPS.
    return caps


def repair_tail_bound(initial_debt, profile='local'):
    """Conservative finite bound on repair-tail drains (harness control only).

    Floor 4096 covers the observed 1M tail (debt 1060 at ~30/call needs 36
    drains) with two orders of magnitude headroom, plus 2x initial debt for
    larger (e.g. VM 10M) tails. The bound caps resource use only: exhaustion
    raises instead of relaxing the REQUIRED final debt of zero, and the
    fail-fast no-progress check in run_repair_tail still fires first.
    """
    _ = profile  # same conservative floor for local/vm; kept explicit
    initial = int(initial_debt)
    if initial < 0:
        initial = 0
    return max(REPAIR_TAIL_DRAIN_CAP, 2 * initial + 64)


def run_repair_tail(read_debt, drain_once, max_drains):
    """Bounded harness-only repair-tail driver.

    read_debt() returns current outstanding debt; drain_once(iteration)
    performs one bounded drain (max_documents=0, budget_seconds=60) and
    returns (processed, debt). Returns initial_debt/max_drains/iterations/
    final_debt. Raises AssertionError on no-progress drains or bound
    exhaustion; never relaxes the REQUIRED final debt of zero.
    """
    max_drains = int(max_drains)
    assert max_drains >= 0, f'repair tail bound must be non-negative: {max_drains!r}'
    initial_debt = int(read_debt())
    last_debt, iters = None, 0
    while int(read_debt()):
        iters += 1
        assert iters <= max_drains, (
            f'repair debt not zero after {max_drains} bounded drains '
            f'(initial={initial_debt}): debt={read_debt()}')
        processed, debt = drain_once(iters)
        processed, debt = int(processed), int(debt)
        assert processed > 0 or (last_debt is not None and debt < last_debt), \
            f'repair drain made no progress: processed={processed} debt={debt}'
        last_debt = debt
    final_debt = int(read_debt())
    return {'initial_debt': initial_debt, 'max_drains': max_drains,
            'iterations': iters, 'final_debt': final_debt}


# Measured post-failure 10M clone: service restore 113.14247418s,
# one-document drain 44.58894621s; marker at 157.73176039s.
# Evidence: W10 CHILD-PROBE-RESULT.md + remote out/timeline.json.
# Unit scaling below is PREDICTED; margin2 is explicit. No core defaults,
# acceptance assertions or organization/publication calls change.
KILL_MEASURED_SECONDS = 157.73176039001555
KILL_MEASURED_ATOMS = 63441
KILL_MEASURED_DOCS = 13081
KILL_WAIT_MARGIN = 2.0


def kill_wait_derivation(planned_atoms, planned_docs, remaining_seconds=None):
    import math
    units = (planned_atoms, planned_docs)
    if any(isinstance(n, bool) or not isinstance(n, int) or n <= 0 for n in units):
        raise ValueError('planned atoms/docs must be positive integer loader counts')
    raw = KILL_WAIT_MARGIN * KILL_MEASURED_SECONDS * max(
        planned_atoms / KILL_MEASURED_ATOMS, planned_docs / KILL_MEASURED_DOCS)
    wait = max(120, math.ceil(raw))  # unchanged old operational minimum
    if remaining_seconds is not None:
        if not math.isfinite(remaining_seconds) or remaining_seconds <= 0:
            raise ValueError('remaining run clock must be finite and positive')
        if wait + 10 > remaining_seconds:  # existing child reap grace
            raise RuntimeError('derived child wait plus reap grace cannot fit run clock')
    return {'source': 'derived', 'measured_child_marker_s': KILL_MEASURED_SECONDS,
            'measured_atoms': KILL_MEASURED_ATOMS, 'measured_docs': KILL_MEASURED_DOCS,
            'planned_atoms': planned_atoms, 'planned_docs': planned_docs,
            'margin': KILL_WAIT_MARGIN, 'unit_scaling_scope': 'predicted linear max(atom,doc)',
            'operational_minimum_s': 120, 'raw_s': raw, 'wait_s': wait,
            'remaining_run_clock_s': remaining_seconds,
            'evidence': 'W10 isolated post-failure clone; original child cause inferred'}


def remaining_run_clock():
    import datetime
    raw = os.environ.get('SUP_QUALIFICATION_DEADLINE_UTC')
    if raw is None:
        return None  # local fixtures; VM controller supplies an explicit UTC clock
    deadline = datetime.datetime.fromisoformat(raw.replace('Z', '+00:00'))
    if deadline.tzinfo is None or deadline.utcoffset() != datetime.timedelta(0):
        raise ValueError('qualification deadline must specify UTC')
    return deadline.timestamp() - time.time()


def await_kill_boundary(child, marker, wait_s):
    """Fresh marker required by caller; every exit cleans this child only."""
    import math
    if isinstance(wait_s, bool) or not math.isfinite(wait_s) or wait_s <= 0:
        raise ValueError('child wait must be finite and positive')
    start = time.monotonic()
    try:
        deadline = start + wait_s
        while child.is_alive() and not marker.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        if not marker.exists():
            raise AssertionError('writer missed derived kill boundary: %r' % child.exitcode)
        assert marker.read_text() == 'after_organize_before_ack', 'invalid kill marker'
        assert child.is_alive(), 'child exited before parent SIGKILL'
        child.kill(); child.join(10)
        assert child.exitcode == -9, 'child not reaped after parent SIGKILL'
        return time.monotonic() - start
    finally:
        if child.is_alive():
            child.kill(); child.join(10)
        elif child.pid is not None:
            child.join(0)


def resolve_paths(args):
    """Explicit args/env with file-parent defaults. Returns a namespace."""
    tools_dir = Path(args.tools_dir) if args.tools_dir else TOOL_DIR
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    source_root = Path(args.source_root) if args.source_root else Path(
        os.environ.get('PILOT_SOURCE_ROOT', tools_dir.parent))
    data_dir = Path(args.data_dir) if args.data_dir else Path(
        os.environ.get('PILOT_DATA_DIR', source_root / 'data'))
    tlsys_dir = Path(args.tlsys_dir) if args.tlsys_dir else Path(
        os.environ.get('PILOT_TLSYS_DIR', source_root / 'fork' / 'tl-sys'))
    cand_dir = Path(args.candidate_dir) if args.candidate_dir else Path(
        os.environ.get('PILOT_CANDIDATE_DIR',
                       source_root / 'fork' / 'tl-candidate-batch' / 'candidate'))
    return SimpleNamespace(source_root=source_root, data_dir=data_dir,
                           tlsys_dir=tlsys_dir, cand_dir=cand_dir,
                           tools_dir=tools_dir)


def check_token_cap(tokens, profile):
    cap = TOK_CAP[profile]
    if tokens <= 0 or tokens > cap:
        raise SystemExit(f'--tokens {tokens} outside {profile} cap 1..{cap}')
    return cap


def read_mem_kb():
    try:
        with open('/proc/meminfo') as source:
            for line in source:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1])
    except OSError:
        return -1
    return -1


def service_config(repair_units=REPAIR_UNITS, batched_drain=True):
    from tlsys.org_service import ServiceConfig
    return ServiceConfig(enabled=True, max_documents_per_drain=4096,
                         drain_budget_seconds=60, repair_units_per_drain=repair_units,
                         await_visibility_on_ack=True, batched_drain=batched_drain,
                         reuse_view_pool=os.environ.get("SUP_REUSE_VIEW_POOL", "0") == "1")


def child_writer(root, marker, caps=None):
    import faulthandler
    started = time.monotonic()
    stages = {'spawn_entry_s': 0.0}
    def note(name, **fields):
        stages[name] = time.monotonic() - started
        try:
            _atomic_write_json(Path(str(marker) + '.stages.json'),
                               {'stages': stages, **fields})
        except Exception:
            pass  # observational telemetry cannot change acceptance
    wait = float(os.environ.get('SUP_KILL_WAIT_S', '120'))
    faulthandler.dump_traceback_later(wait, repeat=False)
    note('before_store_open')
    from tlsys.store_if import TLStore
    from tlsys.local_repair import RepairConfig
    from tlsys.repair_hook import TLStoreRepairHook
    from tlsys.org_service import OrganizationService
    if caps is None:
        caps = qualification_caps()
    tl = TLStore(root, local_repair=True,
                 repair_config=RepairConfig(edge_threshold=EDGE, leaf_threshold=LEAF),
                 caps=caps)
    note('after_store_open', effective_caps=dict(tl.cm.caps))

    def fault(stage):
        if stage == 'after_organize_before_ack':
            note('fault_reached', effective_caps=dict(tl.cm.caps), source_head=list(tl.pin()))
            Path(marker).write_text(stage)
            while True:
                time.sleep(.02)
    note('before_service_open')
    s = OrganizationService(tl, config=service_config(repair_units=0), keyed_state=True,
                            repair=TLStoreRepairHook(tl), fault=fault)
    note('after_service_open')
    s.drain(max_documents=1, budget_seconds=60, repair_budget=0)
    note('unexpected_drain_return')
    faulthandler.cancel_dump_traceback_later()


def percentiles(values):
    a = np.asarray(values, dtype=np.float64) * 1000
    return {'n': len(a), 'p50_ms': float(np.percentile(a, 50)),
            'p95_ms': float(np.percentile(a, 95)), 'max_ms': float(a.max())} if len(a) else {'n': 0}


def _atomic_write_json(path, obj):
    """Write JSON atomically (tmp file + os.replace). Harness-only."""
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, default=str))
    os.replace(tmp, path)


def phase_counts_snapshot(tl):
    """Bounded read-only sqlite SELECT COUNT(*) over commits/dedup/intake.

    Opens commit.db in read-only URI mode with a short timeout; never
    writes. Returns {'commits': n, 'dedup': n, 'intake': n} or
    {'error': ...} so telemetry can never fail the run.
    """
    import sqlite3 as _sqlite3
    try:
        uri = 'file:%s?mode=ro' % tl.store.db_path
        con = _sqlite3.connect(uri, uri=True, timeout=5.0)
        try:
            out = {}
            for table in ('commits', 'dedup', 'intake'):
                out[table] = con.execute(
                    'SELECT COUNT(*) FROM %s' % table).fetchone()[0]
            return out
        finally:
            con.close()
    except Exception as exc:  # telemetry is best-effort by design
        return {'error': repr(exc)}


class Readers:
    def __init__(self, publisher, qvec):
        self.publisher, self.qvec = publisher, qvec
        self.stop = threading.Event()
        self.samples = [[], []]
        self.counts = [{}, {}]
        self.errors = []
        self.phase = 'baseline'
        self.threads = [threading.Thread(target=self.run, args=(i,), name=f'reader-{i}')
                        for i in range(2)]
        for thread in self.threads:
            thread.start()

    def run(self, i):
        try:
            while not self.stop.is_set():
                publisher = self.publisher
                started = time.perf_counter()
                reader = publisher.acquire()
                acquired = time.perf_counter()
                try:
                    generation = reader.generation
                    guided, report = reader.facade.guided('cached structural probe', self.qvec,
                                                          top_atoms=10, top_children=4)
                    pending, work = reader.facade.pending_search(self.qvec, k=10)
                    assert reader.facade.triple == generation.pin[3]
                    assert not report.get('dangling_children', 0)
                    assert all(row['generation'] == generation.pin[3] for row in pending)
                    completed = time.perf_counter()
                    phase = self.phase
                    self.counts[i][phase] = self.counts[i].get(phase, 0) + 1
                    if self.counts[i][phase] <= 4096:
                        self.samples[i].append((phase, acquired - started, completed - started,
                                                generation.generation_id, len(guided), len(pending)))
                finally:
                    reader.release()
                self.stop.wait(.01)
        except BaseException:
            self.errors.append(traceback.format_exc())
            self.stop.set()

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join()

    def report(self):
        rows = [r for group in self.samples for r in group]
        by_phase = {}
        for phase in sorted({r[0] for r in rows}):
            data = [r for r in rows if r[0] == phase]
            by_phase[phase] = {'reader_acquire_stall': percentiles([r[1] for r in data]),
                               'request_latency': percentiles([r[2] for r in data]),
                               'visible_generations': len({r[3] for r in data})}
        return {'threads': 2, 'requests_by_thread': [len(g) for g in self.samples],
                'total_requests_by_phase_and_thread': self.counts,
                'reader_acquire_stall': percentiles([r[1] for r in rows]),
                'request_latency': percentiles([r[2] for r in rows]),
                'phases': by_phase, 'errors': self.errors,
                'sample_cap_per_phase_per_thread': 4096, 'request_pause_seconds': .01,
                'sampling': 'first 4096 requests per phase/thread; distributions/max refer to retained samples',
                'stall_definition': 'wall around publisher.acquire (lock + pointer/refcount); query time separately'}


def tie_recall(scores, aids, returned, k=10, tol=1e-10):
    k = min(k, len(aids))
    if not k:
        return 0.0
    boundary = np.sort(scores)[-k]
    strict = {a for a, s in zip(aids, scores) if s > boundary + tol}
    ties = {a for a, s in zip(aids, scores) if abs(s - boundary) <= tol}
    hits = set(returned)
    return (len(hits & strict) + min(k - len(strict), len(hits & ties))) / k


def build_probes(docs, real):
    from tlsys.ingest import chunk_text
    rng = np.random.default_rng(SEED)
    chunks = [(d, c[2]) for d, t in docs for c in chunk_text(t)]
    assert chunks, 'no chunks for probes'
    picks = rng.choice(len(chunks), size=120, replace=len(chunks) < 120)
    vecs = real.embed([chunks[int(i)][1] for i in picks])
    result = []
    for i, (ix, vec) in enumerate(zip(picks, vecs)):
        q = np.asarray(vec, dtype=np.float64)
        family = 'chunk' if i < 40 else 'noisy' if i < 80 else 'cross'
        sources = {chunks[int(ix)][0]}
        if family == 'noisy':
            noise = rng.normal(size=384)
            noise /= np.linalg.norm(noise)
            q = q / np.linalg.norm(q) + .3 * noise
        elif family == 'cross':
            j = (int(ix) + len(chunks) // 2) % len(chunks)
            vec2 = np.asarray(real.embed([chunks[j][1]])[0], dtype=np.float64)
            q = q / np.linalg.norm(q) + vec2 / np.linalg.norm(vec2)
            sources.add(chunks[j][0])
        q = q / np.linalg.norm(q)
        result.append({'id': i, 'family': family, 'vector': q, 'sources': sources})
    return result


def evaluate_facade(tl, facade, probe_set, top_parents=4, top_children=8):
    from tlsys.query import HierQuery
    t0 = time.perf_counter()
    idx = facade._index
    atoms = {a: dict(idx.atoms[a]) for a in list(idx.atoms)}
    assert atoms, 'no live atoms at pinned generation'
    aids = sorted(atoms, key=lambda a: (atoms[a].get('doc_id'), atoms[a].get('span', ''), a))
    mat = np.asarray([np.asarray(atoms[a]['descriptor'], dtype=np.float64) for a in aids])
    mat = mat / np.linalg.norm(mat, axis=1)[:, None]
    doc_of = np.asarray([atoms[a].get('doc_id') for a in aids])
    lso_diag = {'routing': 'shallow filtered index (atoms/holons/seg_leaves/seg_parents/retired_aids); '
                           'setup cost outside query work; no source filter in API'}
    records, lso_errors = [], []
    for probe in probe_set:
        scores = mat @ probe['vector']
        for lso in (False, True):
            eligible = np.ones(len(aids), dtype=bool) if not lso else ~np.isin(doc_of, list(probe['sources']))
            eaids = [a for a, ok in zip(aids, eligible) if ok]
            escores = scores[eligible]
            if not len(eaids):
                continue
            if lso:
                filtered = SimpleNamespace(atoms={a: atoms[a] for a in eaids},
                                           holons=dict(idx.holons),
                                           seg_leaves=dict(idx.seg_leaves),
                                           seg_parents=dict(idx.seg_parents),
                                           retired_aids=set(aids) - set(eaids))
                q = HierQuery(tl, filtered, lambda x: x)
            else:
                q = None
            start = time.perf_counter()
            try:
                if lso:
                    rows, report = q.guided(probe['vector'], top_parents=top_parents,
                                            top_children=top_children, top_atoms=10)
                else:
                    rows, report = facade.guided(probe['vector'], probe['vector'],
                                                 top_parents=top_parents,
                                                 top_children=top_children, top_atoms=10)
            except BaseException as exc:
                lso_errors.append({'probe': probe['id'], 'lso': lso, 'error': repr(exc)})
                continue
            wall = time.perf_counter() - start
            got = list(dict.fromkeys(r['aid'] for r in rows))[:10]
            work = report['work']
            scored = work['parents_scored'] + work['children_scored'] + work['atoms_scored']
            sample_n = min(scored, len(eaids))
            rng = np.random.default_rng(SEED + probe['id'] * 2 + int(lso))
            selected = rng.choice(len(eaids), sample_n, replace=False) if sample_n else np.array([], dtype=int)
            top = sorted(selected, key=lambda i: (-escores[i], eaids[i]))[:10]
            flat = [eaids[i] for i in top]
            records.append({'probe': probe['id'], 'family': probe['family'], 'leave_source_out': lso,
                            'guided_recall10': tie_recall(escores, eaids, got),
                            'flat_recall10': tie_recall(escores, eaids, flat),
                            'work': work, 'guided_scoring_rows': scored, 'flat_scoring_rows': sample_n,
                            'matched_work': sample_n == scored, 'guided_wall_s': wall,
                            'eligible_atoms': len(eaids), 'oracle_scored_atoms': len(aids),
                            'guided_distinct_returned': len(got)})
    summaries = {}
    for lso in (False, True):
        r = [x for x in records if x['leave_source_out'] == lso]
        summaries['leave_source_out' if lso else 'all_sources'] = {
            'probes': len(r),
            'guided_recall10': float(np.mean([x['guided_recall10'] for x in r])) if r else 0.0,
            'flat_recall10': float(np.mean([x['flat_recall10'] for x in r])) if r else 0.0,
            'mean_guided_scoring_rows': float(np.mean([x['guided_scoring_rows'] for x in r])) if r else 0.0,
            'mean_flat_scoring_rows': float(np.mean([x['flat_scoring_rows'] for x in r])) if r else 0.0,
            'matched_work_queries': sum(x['matched_work'] for x in r),
            'guided_wall_p50_s': float(np.median([x['guided_wall_s'] for x in r])) if r else 0.0,
            'families': {fam: {'guided_recall10': float(np.mean([x['guided_recall10'] for x in r if x['family'] == fam])),
                               'flat_recall10': float(np.mean([x['flat_recall10'] for x in r if x['family'] == fam]))}
                         for fam in ('chunk', 'noisy', 'cross')}}
    return {'summary': summaries, 'queries': records, 'lso_errors': lso_errors,
            'lso_diagnostic': lso_diag, 'evaluation_wall_s': time.perf_counter() - t0,
            'live_atoms': len(aids)}


def hash_manifest(source_root, tlsys_dir, tools_dir):
    freeze = Path(source_root) / 'SOURCEFREEZE.json'
    names = json.loads(freeze.read_text())['files']
    files = [Path(source_root) / name for name in sorted(names)] + \
        [tools_dir / 'real_prefix.py', tools_dir / 'preserve_deletes.py',
         Path(__file__).resolve(), Path(source_root) / 'runtime.sh', freeze]
    seen, out = set(), {}
    for f in files:
        f = Path(f).resolve()
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        out[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tokens', type=int, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--profile', choices=('local', 'vm'), default='local')
    ap.add_argument('--source-root', type=Path, default=None)
    ap.add_argument('--data-dir', type=Path, default=None)
    ap.add_argument('--tlsys-dir', type=Path, default=None)
    ap.add_argument('--candidate-dir', type=Path, default=None)
    ap.add_argument('--tools-dir', type=Path, default=None)
    ap.add_argument('--drain-instrument', action='store_true', default=False,
                    help='opt-in per-cycle/per-phase drain timing JSONL '
                         '(<out>/drain-cycles.jsonl); default OFF leaves '
                         'outputs byte-identical')
    ap.add_argument('--drain-budget-s', type=int, default=None,
                    help='Fix-3: main drain_all per-cycle budget_seconds; '
                         f'default 60 (env {DRAIN_ALL_BUDGET_S_ENV}) = '
                         'current behavior')
    ap.add_argument('--drain-unbatched', action='store_true', default=False,
                    help='Fix-3: run the drain path unbatched '
                         '(contract §3.3 arm A control); default batched '
                         '(current behavior)')
    args = ap.parse_args()
    check_token_cap(args.tokens, args.profile)
    if args.profile == "vm" and socket.gethostname().split(".")[0] != "trace-build500":
        raise SystemExit("VM profile requires existing trace-build500; local runs capped at 1M TOK")
    paths = resolve_paths(args)
    for extra in (paths.cand_dir, paths.tlsys_dir):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    from real_prefix import RealPrefix
    from tlsys.ingest import chunk_text
    from tlsys.store_if import TLStore
    from tlsys.local_repair import RepairConfig
    from tlsys.repair_hook import TLStoreRepairHook
    from tlsys.org_service import OrganizationService
    from tlsys.repair_metrics import metrics
    from drain_instrument import DrainRecorder, commits_after as _commits_after
    from drain_instrument import instrument_enabled, run_drain_loop
    args.out.mkdir(parents=True, exist_ok=False)
    # Fix-1 opt-in instrumentation (default OFF): recorder is a no-op unless
    # --drain-instrument or PILOT_DRAIN_INSTRUMENT=1; no file is created OFF.
    recorder = DrainRecorder(args.out, enabled=instrument_enabled(args))
    # Fix-3 harness knob (default 60/batched = current behavior; resolved
    # fail-closed before any work starts).
    drain_budget_s = resolve_drain_budget(args.drain_budget_s)
    drain_batched = not args.drain_unbatched
    failures = []
    manifest_before = hash_manifest(paths.source_root, paths.tlsys_dir, paths.tools_dir)
    freeze_file = paths.source_root / 'SOURCEFREEZE.json'
    if not freeze_file.is_file():
        raise SystemExit(f'source pin missing: {freeze_file} (pass --source-root <candidate-root>)')
    frozen = json.loads(freeze_file.read_text())['files']
    assert all(hashlib.sha256((paths.source_root/name).read_bytes()).hexdigest()==digest for name,digest in frozen.items()), 'frozen source drift'
    (args.out / 'manifest-before.json').write_text(json.dumps(manifest_before, indent=2))
    mem_kb = read_mem_kb()
    assert mem_kb >= 3_000_000, f'MemAvailable floor 3GB violated: {mem_kb} kB'
    source_pin = {'source_root': str(paths.source_root), 'frozen_files': len(frozen),
                  'frozen_ok': True,
                  'harness_sha256': manifest_before.get(str(Path(__file__).resolve()))}
    started = time.perf_counter()
    real = RealPrefix(args.tokens, data_dir=paths.data_dir)
    (args.out / 'input.json').write_text(json.dumps(real.receipt, indent=2))
    (args.out / 'source-pin.json').write_text(json.dumps(
        {**source_pin, 'data_dir': str(paths.data_dir),
         'input_receipt': real.receipt}, indent=2))
    print(json.dumps(real.receipt), flush=True)
    derivation = cap_derivation(planned_atoms=real.receipt['atoms'],
                                planned_docs=real.receipt['complete_documents'])
    qual_caps = qualification_caps(planned_atoms=real.receipt['atoms'],
                                   planned_docs=real.receipt['complete_documents'])
    derivation['outputs'].setdefault('max_delta_entries',
                                     qual_caps['max_delta_entries'])
    derivation['outputs'].setdefault('max_dedup_rows',
                                     qual_caps['max_dedup_rows'])
    _atomic_write_json(args.out / 'cap-derivation.json', derivation)
    print(json.dumps({'cap_derivation': derivation}), flush=True)
    tl = TLStore(str(args.out / 'store'), create=True, lease_owner='product-pilot',
                 local_repair=True, repair_config=RepairConfig(edge_threshold=EDGE, leaf_threshold=LEAF),
                 caps=qual_caps)
    s = OrganizationService(tl, config=service_config(batched_drain=drain_batched), keyed_state=True, repair=TLStoreRepairHook(tl))
    walls, handoffs = {}, []
    readers = None
    anchors = []
    result = {'claim': 'measured', 'input': real.receipt, 'walls_s': walls,
              'drain_all_budget_s': drain_budget_s,
              'drain_mode': 'batched' if drain_batched else 'unbatched',
              'composition': {'tlstore': 'TLStore(local_repair=True, RepairConfig(edge_threshold=.45, leaf_threshold=.55))',
                              'service': 'OrganizationService(enabled=True, keyed_state=True, TLStoreRepairHook, '
                                         'repair_units_per_drain=250000000, await_visibility_on_ack=True, batched_drain=%s)' % drain_batched,
                              'mem_available_floor_gb': 3, 'mem_available_kb': mem_kb},
              'manifest_before_match': None}
    result['runtime'] = {'python': sys.executable, 'numpy': np.__version__,
                         'OMP_NUM_THREADS': os.environ.get('OMP_NUM_THREADS'),
                         'OPENBLAS_NUM_THREADS': os.environ.get('OPENBLAS_NUM_THREADS'),
                         'MKL_NUM_THREADS': os.environ.get('MKL_NUM_THREADS'),
                         'nice': os.getpriority(os.PRIO_PROCESS, 0)}
    result['configured_caps'] = {'main': dict(qual_caps), 'child': dict(qual_caps),
                                 'restart': dict(qual_caps)}
    result['cap_derivation'] = derivation
    telemetry = []

    def record_phase(label):
        """Append one phase-telemetry entry and atomically replace the file.

        Entry: phase label, run-elapsed wall, copy of phase walls so far,
        read-only sqlite counts, and the actual effective tl.cm.caps.
        Best-effort: count failures are recorded, never raised.
        """
        entry = {'phase': label, 'wall_s': time.perf_counter() - started,
                 'phase_walls_s': dict(walls),
                 'counts': phase_counts_snapshot(tl),
                 'effective_caps': dict(tl.cm.caps)}
        telemetry.append(entry)
        _atomic_write_json(args.out / 'phase-telemetry.json',
                           {'claim': 'measured', 'phases': telemetry})
        return entry
    result['profile'] = {'profile': args.profile, 'token_cap': TOK_CAP[args.profile]}
    result['paths'] = {k: str(v) for k, v in vars(paths).items()}
    result['source_pin'] = source_pin
    result['memory_observations_kb'] = {'mem_available_start': mem_kb}

    def measured_ingest(docs):
        stamp = {'commits': 0}
        original = tl.cm.commit_batch
        def committed(*a, **kw):
            value = original(*a, **kw)
            stamp['last_cm_return'] = time.perf_counter()
            stamp['commits'] += 1
            return value
        tl.cm.commit_batch = committed
        try:
            ack = s.ingest_visible(docs, real.embed)
            returned = time.perf_counter()
        finally:
            tl.cm.commit_batch = original
        assert stamp['commits'], 'fresh input must commit source'
        ack['last_cm_return_to_ack_s'] = returned - stamp['last_cm_return']
        ack['source_commit_clock'] = 'last successful Committer.commit_batch return in this serialized ingest; API field source_commit_to_ack_s starts at ingest_docs return'
        ack['source_commits'] = stamp['commits']
        return ack

    def await_publication():
        r = s.last_future.result()
        handoffs.append(dict(s.publisher.last_timings))
        return r

    def note_phase(label):
        # Fix-1: opt-in phase wall in the cycles-file format; no-op when OFF.
        if recorder.enabled:
            recorder.append({'type': 'phase', 'phase': label,
                             'wall_s': walls.get(label), 'cycles': None,
                             'attempted_docs': None, 'committed_docs': None,
                             'prepare_s': None,
                             'commits_after': _commits_after(tl)})

    def drain_all(label):
        # Fix-1: recorder None/OFF runs the base statements unchanged.
        # Fix-3: per-cycle budget from the harness knob (default 60).
        def _progress(label, cycles, count, service):
            print(f'{label} cycles={cycles} attempted={count} remaining={len(service.pending())}', flush=True)
        return run_drain_loop(s, tl, label, walls, await_publication,
                              on_cycle=_progress, recorder=recorder,
                              budget_seconds=drain_budget_s)

    try:
        split = max(1, 3 * len(real.docs) // 4)
        wall = time.perf_counter()
        ack0 = measured_ingest(real.docs[:split])
        first = await_publication()
        walls['initial_ingest_visible_and_prepare'] = time.perf_counter() - wall
        record_phase('initial_ingest_visible_and_prepare')
        note_phase('initial_ingest_visible_and_prepare')
        result['initial_ack'] = {k: ack0[k] for k in ('source_commit_to_ack_s', 'total_ingest_to_ack_s', 'last_cm_return_to_ack_s', 'source_commit_clock', 'source_commits')}
        with s.publisher.acquire() as pending_pin:
            rows, work = pending_pin.facade.pending_search(real.probe(), k=10)
            assert rows and work['pending_atoms_scored'] == pending_pin.facade.atom_count
        drain_all('initial_drain_and_prepare')
        record_phase('initial_drain_and_prepare')
        baseline = await_publication()
        anchors = [s.publisher.acquire(), s.publisher.acquire()]
        anchor_count = anchors[0].facade.atom_count
        readers = Readers(s.publisher, real.probe())
        time.sleep(.3)
        readers.phase = 'append'
        assert len(s.pending()) == 0
        rest = real.docs[split:]
        assert len(rest) >= 4, f'too few append docs for fault/kill coverage: {len(rest)}'
        append_doc, append_text = rest[0]
        append_chunks = chunk_text(append_text) or [(0, 0, append_text, 0, 0)]
        append_chunk_text = append_chunks[0][2]
        try:
            append_vec = np.asarray(real.embed([append_chunk_text])[0], dtype=np.float64)
        except KeyError as exc:
            raise RuntimeError(f'append chunk cache miss: {exc}')
        wall = time.perf_counter()
        ack1 = measured_ingest(rest)
        ack_point = time.perf_counter()
        with s.publisher.acquire() as pin:
            merged, mrep = pin.facade.search('append visibility probe', append_vec, k=50)
            q_done = time.perf_counter()
            assert any(r['doc_id'] == append_doc for r in merged), \
                f'append doc {append_doc} not visible in merged search top-50'
        # Same acknowledged generation, 32 complete source documents.
        # This measures visibility probes rather than inferring p95 from one.
        timings = [q_done - ack_point]
        rng = np.random.default_rng(SEED + 17)
        selected = rng.choice(len(rest), min(32, len(rest)), replace=False)
        for ix in selected:
            doc, text = rest[int(ix)]
            chunk = chunk_text(text)[0][2]
            vec = np.asarray(real.embed([chunk])[0], dtype=np.float64)
            begin = time.perf_counter()
            with s.publisher.acquire() as view:
                rows, detail = view.facade.search('append sampled visibility', vec, k=50)
                elapsed = time.perf_counter() - begin
                assert any(r['doc_id'] == doc for r in rows), f'acknowledged doc missing from top50: {doc}'
                assert tuple(view.generation.pin)==tuple(ack1['generation'].pin)
            timings.append(elapsed)
        result['f1_visibility_samples'] = {'query_completion':percentiles(timings),
            'n_documents':len(selected)+1,'top_k':50,
            'measurement':'first query starts at ACK return; 32 later queries at same frontier; latency from each request start',
            'all_within_5s':max(timings)<=F1_BUDGET_S}
        assert result['f1_visibility_samples']['all_within_5s']
        walls['append_ingest_visible_with_readers'] = ack_point - wall
        record_phase('append_ingest_visible_with_readers')
        note_phase('append_ingest_visible_with_readers')
        result['f1_append_visible'] = {
            'ack_return_to_query_s': q_done - ack_point,
            'post_ingest_return_to_ack_s': ack1['source_commit_to_ack_s'],
            'last_cm_return_to_ack_s': ack1['last_cm_return_to_ack_s'],
            'source_commit_clock': ack1['source_commit_clock'],
            'total_ingest_to_ack_s': ack1['total_ingest_to_ack_s'],
            'append_doc': append_doc, 'merged_rows': mrep['merged_rows'],
            'within_5s': (q_done - ack_point) <= F1_BUDGET_S}
        assert result['f1_append_visible']['within_5s'], 'F1 ACK->searchable exceeded 5s'
        print(f"append ACK->searchable {q_done - ack_point:.3f}s "
              f"(last CM return->ack {ack1['last_cm_return_to_ack_s']:.3f}s, "
              f"ingest->ack {ack1['total_ingest_to_ack_s']:.3f}s)", flush=True)
        assert anchors[0].generation == baseline == anchors[1].generation
        assert anchors[0].facade.atom_count == anchor_count

        readers.phase = 'source_capacity_rejection'
        wall = time.perf_counter()
        previous_pin = tl.pin()
        # Snapshot the qualified (derived/fallback) caps; the injected
        # 0-delta/.01-deadline rejection below restores this snapshot, so
        # the qualified caps stay enforced.
        caps = dict(tl.cm.caps)
        tl.cm.caps['max_delta_entries'] = 0
        tl.cm.caps['reserve_deadline_s'] = .01
        try:
            rejection = s.drain(max_documents=1, budget_seconds=60, repair_budget=0)
        finally:
            tl.cm.caps = caps
        assert rejection['failed'] and s.pending()
        assert tl.pin() == previous_pin
        await_publication()
        result['rejection'] = rejection
        walls['source_capacity_rejection'] = time.perf_counter() - wall
        record_phase('source_capacity_rejection')
        print('source capacity rejection preserved pending source', flush=True)

        readers.phase = 'prepare_rejection_fresh_frontier'
        wall = time.perf_counter()
        old_record = s.publisher.load_record()
        old_pin = tl.pin()

        def fail(stage):
            if stage == 'after_prepare':
                raise RuntimeError('injected prepare failure')
        s.publisher._fault = fail
        try:
            fresh_rep = s.drain(max_documents=1, budget_seconds=60)
            assert fresh_rep['completed'], 'fault drain must still advance source head for fresh frontier'
            try:
                s.last_future.result()
                raise AssertionError('injection did not fail')
            except RuntimeError as e:
                assert 'injected' in str(e)
                result['prepare_fault'] = {'error': str(e), 'advanced_docs': fresh_rep['completed']}
        finally:
            s.publisher._fault = None
        assert s.publisher.load_record() == old_record
        assert tl.pin() != old_pin, 'head must advance so the fault hits a fresh frontier'
        fresh = s.publish().result()
        handoffs.append(dict(s.publisher.last_timings))
        assert s.publisher.load_record() == fresh and fresh != old_record
        result['prepare_fault']['fresh_generation'] = fresh.generation_id
        walls['prepare_rejection_fresh_frontier'] = time.perf_counter() - wall
        record_phase('prepare_rejection_fresh_frontier')
        print('prepare fault on fresh frontier left pointer unchanged; fresh head published', flush=True)

        readers.phase = 'writer_kill_and_restart'
        wall = time.perf_counter()
        old_publisher = s.detach_readers()
        s.close()
        tl.close()
        marker = args.out / 'kill-marker'
        assert not marker.exists(), 'refuse stale kill marker; preserve prior evidence'
        wait_basis = kill_wait_derivation(real.receipt['atoms'],
                                         real.receipt['complete_documents'], remaining_run_clock())
        _atomic_write_json(args.out / 'kill-wait-derivation.json', wait_basis)
        result['kill_wait_derivation'] = wait_basis
        print(json.dumps({'kill_wait_derivation': wait_basis}), flush=True)
        old_wait_env = os.environ.get('SUP_KILL_WAIT_S')
        os.environ['SUP_KILL_WAIT_S'] = str(wait_basis['wait_s'])
        try:
            child = mp.get_context('spawn').Process(target=child_writer, args=(str(args.out / 'store'), str(marker), dict(qual_caps)))
            child.start()
        finally:
            if old_wait_env is None:
                os.environ.pop('SUP_KILL_WAIT_S', None)
            else:
                os.environ['SUP_KILL_WAIT_S'] = old_wait_env
        marker_elapsed = await_kill_boundary(child, marker, wait_basis['wait_s'])
        result['kill_child_marker_elapsed_s'] = marker_elapsed
        stages_path = Path(str(marker) + '.stages.json')
        if stages_path.exists():
            result['kill_child_stages'] = json.loads(stages_path.read_text())
        tl = TLStore(str(args.out / 'store'), lease_owner='product-pilot-resumed',
                     local_repair=True, repair_config=RepairConfig(edge_threshold=EDGE, leaf_threshold=LEAF),
                     caps=qual_caps)
        restart_head = tl.pin()
        s = OrganizationService(tl, config=service_config(batched_drain=drain_batched), keyed_state=True, repair=TLStoreRepairHook(tl))
        restored = s.publisher.load_record()
        assert restored == fresh, 'restart must restore the latest durable publication'
        resumed = s.drain(max_documents=1, budget_seconds=60, repair_budget=0)
        await_publication()
        assert resumed['completed'] and tl.pin() == restart_head, \
            f'source recommit after kill: {resumed} head {restart_head} vs {tl.pin()}'
        result['kill_resume'] = {'exitcode': child.exitcode, 'source_recommit_count': 0,
                                 'resumed': resumed, 'restart_head': list(restart_head),
                                 'old_generation_retained': True, 'repair_budget_at_boundary': 0}
        readers.publisher = s.publisher
        walls['writer_kill_and_restart'] = time.perf_counter() - wall
        record_phase('writer_kill_and_restart')
        note_phase('writer_kill_and_restart')
        print('SIGKILL/restart passed without duplicate source commits', flush=True)
        readers.phase = 'drain'
        drain_all('remaining_drain_and_prepare_with_readers')
        record_phase('remaining_drain_and_prepare_with_readers')
        final = await_publication()
        wall = time.perf_counter()
        max_drains = repair_tail_bound(len(tl.local_repair.engine.queue), args.profile)

        def tail_drain_once(iteration):
            rep = s.drain(max_documents=0, budget_seconds=60)
            await_publication()
            inner = rep['repair'].get('repair', {})
            debt = int(inner.get('debt', len(tl.local_repair.engine.queue)))
            processed = int(rep['repair'].get('processed', 0))
            print(f'repair drain iter={iteration} debt={debt} processed={processed}', flush=True)
            return processed, debt

        tail = run_repair_tail(lambda: len(tl.local_repair.engine.queue),
                               tail_drain_once, max_drains)
        assert tail['final_debt'] == 0, f'repair tail final debt must be zero: {tail}'
        walls['repair_to_zero'] = time.perf_counter() - wall
        record_phase('repair_to_zero')
        result['repair_to_zero'] = {'iters': tail['iterations'], 'initial_debt': tail['initial_debt'],
                                    'max_drains': tail['max_drains'], 'iterations': tail['iterations'],
                                    'final_debt': tail['final_debt']}
        head = tl.pin()
        again = s.drain(max_documents=16, budget_seconds=60)
        await_publication()
        assert again['attempted'] == 0 and tl.pin() == head
        assert anchors[0].generation == anchors[1].generation == baseline
        assert anchors[0].facade.atom_count == anchor_count
        result['idempotent_empty_drain'] = True

        published = s.publish().result()
        handoffs.append(dict(s.publisher.last_timings))
        assert tuple(published.pin) == tuple(tl.pin()), f'{published.pin} vs {tl.pin()}'
        repub = s.publish().result()
        handoffs.append(dict(s.publisher.last_timings))
        assert repub.generation_id == published.generation_id
        assert s.publisher.last_timings.get('dedup'), 'no-op republish must dedup without prepare'
        result['final'] = {'generation_id': published.generation_id, 'source_head': list(tl.pin()),
                           'no_op_republish_dedup': s.publisher.last_timings.get('dedup')}
        time.sleep(.3)
        readers.close()
        assert not readers.errors, readers.errors
        result['readers'] = readers.report()
        readers = None
        with s.publisher.acquire() as pin:
            assert pin.facade.atom_count == real.chunk_count
            assert not pin.generation.pending_documents
            guided, report = pin.facade.guided('cached structural probe', real.probe(), top_atoms=10)
            assert guided and not report['dangling_children']
            result['final'].update({'atoms': pin.facade.atom_count, 'leaves': len(pin.facade.leaves),
                                    'parents': len(pin.facade.parents),
                                    'membership_revisions': len(pin.generation.membership_revisions),
                                    'pending_documents': 0, 'guided_query_work': report['work']})
            probe_set = build_probes(real.docs, real)
            result['evaluation'] = evaluate_facade(tl, pin.facade, probe_set)
            assert not result['evaluation']['lso_errors'], result['evaluation']['lso_errors']
            assert all(result['evaluation']['summary'][group]['probes']==120 for group in ('all_sources','leave_source_out')), 'incomplete evaluation'
            result['evaluation']['pin'] = list(pin.generation.pin)
            body = json.dumps([{**q,'vector':q['vector'].tolist(),'sources':sorted(q['sources'])} for q in probe_set],sort_keys=True).encode()
            (args.out/'probes.json').write_bytes(body)
            result['evaluation']['probes_sha256'] = hashlib.sha256(body).hexdigest()
        m = metrics(tl.local_repair.engine)
        for key in ('orphan_children', 'duplicate_edges', 'dangling_edges', 'parent_union_mismatches', 'incoherent_edges'):
            assert not m[key], f'{key}={m[key]}'
        assert m['leaf_occupancy']['max'] <= 25 and m['parent_occupancy']['max'] <= 16
        result['repair_metrics'] = m
        result['handoff'] = percentiles([h['handoff_s'] for h in handoffs if h])
        result['preparation'] = percentiles([h['prepare_s'] for h in handoffs if h])
        result['durable_publication'] = percentiles([h['durable_publication_s'] for h in handoffs if h])
        result['publication_count'] = len(handoffs)
        result['old_pin_atom_count'] = anchor_count
        result['wall_s'] = time.perf_counter() - started
        result['memory_observations_kb']['mem_available_end'] = read_mem_kb()
        (args.out / 'memory.json').write_text(json.dumps(result['memory_observations_kb'], indent=2))
        result['peak_parent_rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        result['peak_child_rss_mib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
        result['retained_disk_bytes'] = sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file())
        peak_commits = max((e['counts'].get('commits', 0) for e in telemetry
                            if isinstance(e.get('counts'), dict)), default=0)
        result['cap_peak_headroom'] = {
            'peak_commits': peak_commits,
            'effective_max_delta_entries': qual_caps['max_delta_entries'],
            'effective_max_dedup_rows': qual_caps['max_dedup_rows'],
            'headroom_delta_entries':
                qual_caps['max_delta_entries'] - peak_commits}
        record_phase('final')
        result['status'] = 'PASS'
        print(json.dumps({k: result[k] for k in ('status', 'f1_append_visible', 'final',
                                                'repair_to_zero', 'wall_s')}, indent=2), flush=True)
    except BaseException as exc:
        failures.append(traceback.format_exc())
        result['status'] = 'FAIL'
        result['failures'] = failures[-3:]
        print(f'FAIL: {exc!r}', flush=True)
    finally:
        if 'child' in locals() and child.is_alive():
            child.kill(); child.join(10)
        try:
            if readers:
                readers.close()
        except BaseException:
            pass
        for pin in anchors:
            try:
                pin.release()
            except BaseException:
                pass
        try:
            if 'old_publisher' in locals():
                old_publisher.close()
        except BaseException:
            pass
        try:
            s.close()
        except BaseException:
            pass
        try:
            tl.close()
        except BaseException:
            pass
        manifest_after = hash_manifest(paths.source_root, paths.tlsys_dir, paths.tools_dir)
        (args.out / 'manifest-after.json').write_text(json.dumps(manifest_after, indent=2))
        result['manifest_match'] = (manifest_after == manifest_before)
        if not result['manifest_match']:
            result['status']='FAIL'
            result.setdefault('failures',[]).append('source/harness manifest changed during run')
        result['manifest_harness_sha256'] = manifest_after.get(str(Path(__file__).resolve()))
        (args.out / 'result.json').write_text(json.dumps(result, indent=2, default=str))
        if result.get('status') != 'PASS':
            raise SystemExit(1)


if __name__ == '__main__':
    main()

