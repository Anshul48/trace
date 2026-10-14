"""Opt-in per-cycle/per-phase drain instrumentation (Fix-1 fork, harness-only).

Default OFF: with ``enabled=False`` the recorder is a no-op (no file is
created, no snapshots are taken) and :func:`run_drain_loop` executes the
exact drain_all statements from the base harness. With enabled=True each
drain cycle appends one JSON line to ``<out>/drain-cycles.jsonl`` and each
drained phase appends one phase line in the same file.

Overhead when ON is timer calls, two read-only snapshots (served-atom
pin acquire/release, read-only sqlite COUNT(*)) and one file append per
cycle. No product-core, acceptance, F1, fault, SIGKILL-retry, oracle,
reader-cadence or commit semantics change. Stdlib only.
"""
import json
import os
import time
from pathlib import Path

ENV_VAR = 'PILOT_DRAIN_INSTRUMENT'
CYCLES_FILENAME = 'drain-cycles.jsonl'

# Required keys for a per-cycle record. prepare_split sub-fields are None
# when not separately measurable at the harness layer (documented inline).
CYCLE_KEYS = ('type', 'phase', 'cycle', 'wall_s', 'lock_hold_s',
              'attempted_docs', 'committed_docs', 'failed_docs',
              'attempted_atoms', 'committed_atoms', 'atoms_before',
              'atoms_after', 'prepare_s', 'durable_publication_s',
              'handoff_s', 'prepare_split', 'commits_after', 'remaining')
PHASE_KEYS = ('type', 'phase', 'wall_s', 'cycles', 'attempted_docs',
              'committed_docs', 'commits_after')


def instrument_enabled(args=None):
    """True only with explicit opt-in: --drain-instrument or env == '1'."""
    if args is not None and getattr(args, 'drain_instrument', False):
        return True
    return os.environ.get(ENV_VAR, '0') == '1'


def served_atoms(service):
    """Served atom count at the current published frontier, or None.

    Best-effort read-only pin acquire/release; never raises.
    """
    try:
        pin = service.publisher.acquire()
    except Exception:
        return None
    try:
        return int(pin.facade.atom_count)
    except Exception:
        return None
    finally:
        try:
            pin.release()
        except Exception:
            pass


def commits_after(store):
    """Committed-source row count (read-only sqlite COUNT(*)), or None."""
    import sqlite3 as _sqlite3
    try:
        inner = getattr(store, 'store', store)  # TLStore wraps Store
        uri = 'file:%s?mode=ro' % inner.db_path
        con = _sqlite3.connect(uri, uri=True, timeout=5.0)
        try:
            return int(con.execute('SELECT COUNT(*) FROM commits').fetchone()[0])
        finally:
            con.close()
    except Exception:
        return None


class DrainRecorder:
    """Append-only JSONL recorder; no-op unless enabled."""

    def __init__(self, out_dir, enabled=False):
        self.enabled = bool(enabled)
        self.path = Path(out_dir) / CYCLES_FILENAME if out_dir is not None else None
        self.cycles = 0

    def append(self, record):
        if not self.enabled:
            return
        assert self.path is not None, 'recorder needs an out dir when enabled'
        with open(self.path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(record, default=str) + '\n')
        self.cycles += 1


def cycle_record(phase, cycle, wall_s, report, timings, atoms_before,
                 atoms_after, commits):
    """Build one per-cycle record dict (pure function, no I/O)."""
    completed = report.get('completed', []) or []
    failed = report.get('failed', {}) or {}
    timings = dict(timings or {})
    after_c = atoms_after if isinstance(atoms_after, int) else None
    before_c = atoms_before if isinstance(atoms_before, int) else None
    return {
        'type': 'cycle',
        'phase': phase,
        'cycle': int(cycle),
        'wall_s': float(wall_s),
        # lock_hold_s: drain() holds the single-writer lock for its whole
        # body; report wall_s is the harness-visible lock-hold measure.
        'lock_hold_s': (float(report['wall_s']) if isinstance(
            report.get('wall_s'), (int, float)) else None),
        'attempted_docs': int(report.get('attempted', 0)),
        'committed_docs': len(completed),
        'failed_docs': len(failed),
        # attempted atoms are not visible at the harness layer (per-doc
        # organize internals); committed atoms = served-atom delta across
        # this cycle's drain+publish.
        'attempted_atoms': None,
        'committed_atoms': (after_c - before_c
                            if after_c is not None and before_c is not None
                            else None),
        'atoms_before': before_c,
        'atoms_after': after_c,
        # prepare wall from publisher timings: prepare_s covers _prepare
        # (ViewPool build + source-hierarchy re-read) + verify_prepared.
        # The finer ViewPool-vs-verify-vs-scan split is not separately
        # measurable without core hooks, so sub-fields stay null.
        'prepare_s': timings.get('prepare_s'),
        'durable_publication_s': timings.get('durable_publication_s'),
        'handoff_s': timings.get('handoff_s'),
        'prepare_split': {
            'viewpool_build_s': None,
            'source_verify_s': None,
            'scan_s': None,
            'note': ('publisher prepare_s covers ViewPool build + '
                     'source-hierarchy re-read + verify_prepared; '
                     'finer split needs core hooks (not added here)'),
        },
        'commits_after': commits,
        'remaining': int(report.get('remaining', -1)),
    }


def drain_one_cycle(service, store, phase, cycle, recorder=None,
                    await_publication=None, max_documents=4096,
                    budget_seconds=60):
    """Drain exactly one cycle; optionally record it. Returns report."""
    if recorder is not None and recorder.enabled:
        atoms_before = served_atoms(service)
        start = time.perf_counter()
        report = service.drain(max_documents=max_documents,
                               budget_seconds=budget_seconds)
        lock_wall = time.perf_counter() - start
        if await_publication is not None:
            await_publication()
        try:
            timings = dict(service.publisher.last_timings)
        except Exception:
            timings = {}
        atoms_after = served_atoms(service)
        n_commits = commits_after(store)
        wall_s = time.perf_counter() - start
        _ = lock_wall  # outer wall is the reported wall; kept for clarity
        recorder.append(cycle_record(phase, cycle, wall_s, report, timings,
                                     atoms_before, atoms_after, n_commits))
        return report
    report = service.drain(max_documents=max_documents,
                           budget_seconds=budget_seconds)
    if await_publication is not None:
        await_publication()
    return report


def run_drain_loop(service, store, label, walls, await_publication,
                   on_cycle=None, recorder=None, max_documents=4096,
                   budget_seconds=60):
    """Serial drain-until-empty loop (base drain_all semantics + records).

    With recorder None/disabled this executes the base harness statements:
    drain -> await publication -> raise on failed/no-progress -> count.
    With a recorder each cycle appends one JSONL line and the phase appends
    one phase line. max_documents/budget_seconds default to the base
    drain_all literals (Fix-3 threads the harness knob through here).
    Returns drained-cycle count.
    """
    wall = time.perf_counter()
    cycles, count = 0, 0
    while service.pending():
        report = drain_one_cycle(service, store, label, cycles, recorder,
                                 await_publication,
                                 max_documents=max_documents,
                                 budget_seconds=budget_seconds)
        if report['failed']:
            raise RuntimeError(str(report))
        if not report['attempted']:
            raise RuntimeError('drain made no progress')
        cycles += 1
        count += report['attempted']
        if on_cycle is not None:
            on_cycle(label, cycles, count, service)
    walls[label] = time.perf_counter() - wall
    if recorder is not None and recorder.enabled:
        try:
            timings = dict(service.publisher.last_timings)
        except Exception:
            timings = {}
        recorder.append({
            'type': 'phase', 'phase': label, 'wall_s': walls[label],
            'cycles': cycles, 'attempted_docs': count,
            'committed_docs': count,
            'prepare_s': timings.get('prepare_s'),
            'commits_after': commits_after(store),
        })
    return cycles


def derive_budget_candidate(cycle_walls):
    """Fix-3 probe-budget derivation: ceil(2 * max measured cycle wall).

    Pure function. cycle_walls: non-empty iterable of measured per-cycle
    wall seconds (e.g. from a drain-cycles.jsonl file). Returns an int.
    The 2.0x margin follows the R8/COMMIT-CEILING precedent; the basis
    must be measured walls, never a constant. Raises ValueError when no
    positive wall is supplied (fail closed: never derive from nothing).
    """
    import math as _math
    walls = [float(w) for w in cycle_walls
             if isinstance(w, (int, float)) and w > 0]
    if not walls:
        raise ValueError('need >=1 measured positive cycle wall to derive a budget')
    return int(_math.ceil(2.0 * max(walls)))


def derive_budget_from_cycles_file(path):
    """Derive a Fix-3 probe budget from a recorded drain-cycles.jsonl file.

    Returns {'basis': ..., 'cycles': n, 'max_cycle_wall_s': m,
    'candidate_budget_s': ceil(2*m)}. Raises ValueError when the file
    carries no usable cycle walls.
    """
    rows = read_records(path)
    walls = [r['wall_s'] for _, r in rows if r.get('type') == 'cycle']
    candidate = derive_budget_candidate(walls)
    return {'basis': 'drain-cycles.jsonl cycle wall_s (measured)',
            'cycles': len(walls),
            'max_cycle_wall_s': max(float(w) for w in walls),
            'candidate_budget_s': candidate}


def read_records(path):
    """Read and JSON-parse every line of a cycles file."""
    rows = []
    with open(path, encoding='utf-8') as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                rows.append((lineno, json.loads(line)))
    return rows


def validate_records(rows, ledger_docs, remeasured=None, tol=0.15):
    """Check cycle/phase records against ledger + independent walls.

    ledger_docs: number of docs the fixture ingested for draining.
    remeasured: {cycle_index: independently measured wall_s}.
    Returns a list of error strings (empty == VALID).
    """
    errors = []
    cycles = [r for _, r in rows if r.get('type') == 'cycle']
    if not cycles:
        return ['no cycle records']
    for _, rec in rows:
        if rec.get('type') == 'cycle':
            missing = [k for k in CYCLE_KEYS if k not in rec]
            if missing:
                errors.append('cycle %r missing keys %r' % (rec.get('cycle'), missing))
            if not isinstance(rec.get('wall_s'), (int, float)) or rec['wall_s'] <= 0:
                errors.append('cycle %r bad wall_s %r' % (rec.get('cycle'), rec.get('wall_s')))
        elif rec.get('type') == 'phase':
            missing = [k for k in PHASE_KEYS if k not in rec]
            if missing:
                errors.append('phase %r missing keys %r' % (rec.get('phase'), missing))
        else:
            errors.append('unknown record type %r' % (rec.get('type'),))
    attempted = sum(r['attempted_docs'] for _, r in rows if r.get('type') == 'cycle'
                    and isinstance(r.get('attempted_docs'), int))
    committed = sum(r['committed_docs'] for _, r in rows if r.get('type') == 'cycle'
                    and isinstance(r.get('committed_docs'), int))
    failed = sum(r['failed_docs'] for _, r in rows if r.get('type') == 'cycle'
                 and isinstance(r.get('failed_docs'), int))
    if attempted != ledger_docs:
        errors.append('attempted %d != ledger docs %d' % (attempted, ledger_docs))
    if committed + failed != attempted:
        errors.append('committed %d + failed %d != attempted %d' % (committed, failed, attempted))
    if failed:
        errors.append('fixture drain had %d failures' % failed)
    atom_deltas = [r['committed_atoms'] for _, r in rows
                   if r.get('type') == 'cycle' and isinstance(r.get('committed_atoms'), int)]
    known = [r for _, r in rows if r.get('type') == 'cycle']
    first_before = known[0].get('atoms_before')
    last_after = known[-1].get('atoms_after')
    if (first_before is not None and last_after is not None
            and sum(atom_deltas) != last_after - first_before):
        errors.append('atom deltas do not telescope to served-atom growth')
    commits = [r['commits_after'] for _, r in rows if r.get('type') == 'cycle'
               and isinstance(r.get('commits_after'), int)]
    if commits and any(b < a for a, b in zip(commits, commits[1:])):
        errors.append('commits_after decreased across cycles')
    if remeasured:
        for _, rec in rows:
            if rec.get('type') != 'cycle':
                continue
            idx = rec.get('cycle')
            if idx not in remeasured:
                errors.append('cycle %r lacks independent re-measurement' % (idx,))
                continue
            ref = remeasured[idx]
            got = rec.get('wall_s')
            if not isinstance(ref, (int, float)) or ref <= 0:
                errors.append('cycle %r bad reference wall %r' % (idx, ref))
            elif not isinstance(got, (int, float)) or abs(got - ref) / ref > tol:
                errors.append('cycle %r wall %r vs independent %r exceeds %.0f%%'
                              % (idx, got, ref, tol * 100))
    if known and known[-1].get('remaining') != 0:
        errors.append('final remaining != 0: %r' % (known[-1].get('remaining'),))
    return errors
