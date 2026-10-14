"""Tiered compaction: merge adjacent segments, publish by swap.

Merge = term-id remap + ordinal-order concat (no re-tokenization;
tlsys.serving.segments.merge_segments). Publish swaps the live view's
segment tuple under the pool lock, pre-touches persisted files BEFORE
the swap, updates the manifest atomically, and reclaims replaced
segment dirs. Old retained views keep serving their segments until
released (bounded by K). Separate-process mode: a worker merges pure
segment files (no store access); the parent validates vs the log and
publishes. A killed/failed merge never unserves the old segments.
"""
import os
import shutil
import subprocess
import sys

from tlsys.serving import faults as faults_mod
from tlsys.serving import manifest as manifest_mod
from tlsys.serving import segments as seg_mod


def _level(n_atoms, flush_atoms, fan_in):
    lvl = 0
    cap = max(1, int(flush_atoms))
    while n_atoms > cap:
        lvl += 1
        cap *= max(2, int(fan_in))
    return lvl


def plan_merge(segments, fan_in, max_live, flush_atoms):
    """[groups] of adjacent segments to merge (each >= 2, in order).

    Tiered: segments group by size level; a level run longer than
    fan_in merges leftmost-first in groups of <= fan_in. Cap
    enforcer: when the projected count still exceeds max_live, the
    whole chain repartitions into contiguous groups of width <=
    fan_in targeting <= max_live groups (one group may reach
    fan_in+1 to avoid singles). Empty plan == no work. The driver
    re-plans per round until the plan is empty (each round strictly
    reduces the count). Raises SegmentError on a non-contiguous
    chain (fail closed).
    """
    segs = sorted(segments, key=lambda s: s.lo)
    for a, b in zip(segs, segs[1:]):
        if a.hi != b.lo or a.birth != b.birth or a.epoch != b.epoch:
            raise seg_mod.SegmentError(
                "compaction needs one contiguous same-store chain")
    fan_in = max(2, int(fan_in))
    max_live = max(1, int(max_live))
    groups = []
    by_level = {}
    for i, s in enumerate(segs):
        by_level.setdefault(_level(len(s.atom_rows), flush_atoms,
                                   fan_in), []).append(i)
    for lvl in sorted(by_level):
        idxs = by_level[lvl]
        runs = []
        for i in idxs:
            if runs and i == runs[-1][-1] + 1:
                runs[-1].append(i)
            else:
                runs.append([i])
        for run in runs:
            while len(run) > fan_in:
                grp = run[:fan_in]
                groups.append([segs[i] for i in grp])
                run = run[fan_in:]
    projected = len(segs) - sum(len(g) - 1 for g in groups)
    if projected <= max_live:
        groups.sort(key=lambda g: g[0].lo)
        return groups
    # Cap enforcer: whole-chain partition.
    n = len(segs)
    width = min(fan_in, max(2, -(-n // max_live)))
    parts = [segs[i:i + width] for i in range(0, n, width)]
    if len(parts) > 1 and len(parts[-1]) == 1:
        parts[-2] = parts[-2] + parts[-1]
        parts.pop()
    return [p for p in parts if len(p) >= 2]


def merge_group(group, counters=None):
    """Merge one adjacent group (validates adjacency; FI-10 hooks)."""
    faults_mod.fire("compaction_kill", phase="pre-merge",
                    segs=[s.segid for s in group])
    merged = seg_mod.merge_segments(group)
    faults_mod.fire("compaction_kill", phase="post-merge",
                    segid=merged.segid)
    return merged


def publish(pool, merged, replaced):
    """Swap merged segments into the pool's current view (+manifest).

    merged/replaced: parallel lists ([new seg], [old segs]) per group.
    Pre-touches persisted files before the swap; updates the manifest
    atomically (serving_dir mode); reclaims replaced seg dirs. Runs
    under the pool lock; readers on old segments are unaffected.
    Returns the new segment tuple.
    """
    with pool.guarded():
        view = pool._current
        if view is None or not view._live:
            raise seg_mod.SegmentError("publish needs a live current")
        old_ids = {s.segid for g in replaced for s in g}
        new_tup = tuple(s for s in view.segments
                        if s.segid not in old_ids)
        for seg in merged:
            if pool.serving_dir is not None:
                segdir = os.path.join(pool.serving_dir, seg.segid)
                seg.save(segdir, counters=pool.counters)
                touched = seg_mod.pre_touch(segdir)
                pool.counters.record(bytes_read=touched)
            new_tup = new_tup + (seg,)
        new_tup = tuple(sorted(new_tup, key=lambda s: s.lo))
        view.segments = new_tup
        view._invalidate()
        pool.counters.set_gauge(segments_live=len(new_tup))
        if pool.serving_dir is not None:
            union = set()
            for s in new_tup:
                union |= s.retired_docs
            from tlsys.serving.view import tombstone_version_of
            payload = manifest_mod.build(
                list(new_tup), tombstone_version_of(union),
                new_tup[-1].hi if new_tup else 0, view.live_n,
                view.total_tokens)
            manifest_mod.atomic_write(
                os.path.join(pool.serving_dir, manifest_mod.FILENAME),
                payload, counters=pool.counters)
            for grp in replaced:
                for s in grp:
                    d = os.path.join(pool.serving_dir, s.segid)
                    if os.path.isdir(d):
                        shutil.rmtree(d)
        return new_tup


def _repo_tlsys_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", ".."))


def run_worker_merge(serving_dir, segids, out_segid, timeout_s=600):
    """Spawn the separate-process compactor for one group.

    Returns (returncode, stdout_tail). The worker only reads segment
    files and writes the merged segment (no store access); the parent
    validates + publishes. Worker failure never unserves old segs.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = _repo_tlsys_dir() + os.pathsep + \
        env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, "-m", "tlsys.serving.compact",
           "--dir", serving_dir,
           "--segs", ",".join(segids),
           "--out", out_segid]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout_s, env=env)
    except subprocess.TimeoutExpired as e:
        return 124, f"timeout: {e}"
    tail = (p.stdout or "")[-800:] + (p.stderr or "")[-800:]
    return p.returncode, tail


def run_compaction(pool, mode=None):
    """Plan + merge + validate + publish on the pool's current view.

    mode: "inprocess" | "process" (default: pool config
    compactor_mode). Returns [merged segids]. Merged segments are
    validated against the log before publish (I4); any failure
    leaves old segments serving and records failed_retried.
    """
    mode = mode or pool.config.get("compactor_mode", "inprocess")
    if mode not in ("inprocess", "process"):
        raise ValueError(f"unknown compactor mode: {mode!r}")
    with pool.guarded():
        view = pool._current
        if view is None:
            return []
        if mode == "process" and pool.serving_dir is None:
            raise ValueError("process compaction needs serving_dir")
        done = []
        for _round in range(16):
            groups = plan_merge(
                list(view.segments), pool.config["merge_fan_in"],
                pool.config["max_live_segments"],
                pool.config["delta_flush_atoms"])
            if not groups:
                break
            merged = []
            for group in groups:
                if mode == "inprocess":
                    seg = merge_group(group, counters=pool.counters)
                else:
                    out_id = seg_mod.segid_of(group[0].lo,
                                              group[-1].hi)
                    rc, tail = run_worker_merge(
                        pool.serving_dir, [s.segid for s in group],
                        out_id)
                    if rc != 0:
                        pool.counters.record(failed_retried=1)
                        raise seg_mod.SegmentError(
                            f"compactor worker failed rc={rc}: {tail}")
                    seg = seg_mod.Segment.load(
                        os.path.join(pool.serving_dir, out_id),
                        counters=pool.counters)
                try:
                    seg.validate_against_log(pool.tlstore, pool.birth,
                                             pool.epoch)
                except seg_mod.SegmentError:
                    pool.counters.record(failed_retried=1)
                    raise
                merged.append(seg)
            publish(pool, merged, groups)
            done.extend(s.segid for s in merged)
        return done


def compact_worker_main(argv):
    """CLI: merge segment files (pure; no store access)."""
    args = list(argv)
    try:
        d = args[args.index("--dir") + 1]
        segids = args[args.index("--segs") + 1].split(",")
        out = args[args.index("--out") + 1]
    except (ValueError, IndexError):
        print("usage: compact --dir D --segs A,B --out C", file=sys.stderr)
        return 2
    if "compaction_kill" in os.environ.get("TLSYS_COMPACT_FAULTS", ""):
        raise faults_mod.FaultTripped("compaction_kill",
                                      {"phase": "worker"})
    group = [seg_mod.Segment.load(os.path.join(d, s)) for s in segids]
    merged = seg_mod.merge_segments(group)
    merged.segid = out
    merged.save(os.path.join(d, out))
    print(f"merged {len(group)} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(compact_worker_main(sys.argv[1:]))
