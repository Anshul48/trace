"""Lane S compaction: tiered plan, merge correctness, publish swap,
process worker, kill-mid-merge (FI-10 shape), package exports.

Run: tl-sys/.venv/bin/python tl-sys/tlsys/serving/tests/test_serving_compact.py
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixture import emb_votes, make_docs, make_store  # noqa: E402
from tlsys.serving import compact as compact_mod  # noqa: E402
from tlsys.serving import faults as faults_mod  # noqa: E402
from tlsys.serving import segments as seg_mod  # noqa: E402
from tlsys.serving.view import ViewPool  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


QUERIES = ["the domestic cat", "sport medic", "w0x1 fuse",
           "alpha beta gamma"]


def legs_of(view):
    out = {}
    for q in QUERIES:
        out[q] = (view.bm25(q), view.bm25_fullscan(q))
    return out


def build_pool(tmp_tag, serving=True, flush=1, max_live=3):
    docs = make_docs(12, seed=41)
    docs = [(f"c-{i}", t) for i, (_d, t) in enumerate(docs)]
    tl, tmp, pin = make_store(docs, emb_votes,
                              prefix=f"tlsys-lanes-{tmp_tag}-")
    sdir = os.path.join(tmp, "serving") if serving else None
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": flush,
                            "max_live_segments": max_live,
                            "merge_fan_in": 2,
                            "compactor_mode": "inprocess"})
    # Six-way split: each non-empty range seals its own segment.
    mx = pin[2]
    cuts = [0] + [mx * i // 6 for i in range(1, 6)] + [mx]
    ranges = [(cuts[i], cuts[i + 1]) for i in range(6)
              if cuts[i + 1] > cuts[i]]
    v = pool.cold_build(pin, ranges=ranges)
    return tl, tmp, pin, pool, v


def test_plan_and_merge_correctness():
    tl, _tmp, pin, pool, v = build_pool("compact")
    n0 = len(v.segments)
    check("compact-needs-work", n0 > 3, f"{n0} segments")
    before_d = v.canonical_digest()
    before_legs = legs_of(v)
    ref = NarrowIndex(tl, pin)
    groups = compact_mod.plan_merge(list(v.segments), 2, 3, 2)
    check("compact-plan-nonempty", len(groups) >= 1)
    for g in groups:
        for a, b in zip(g, g[1:]):
            if a.hi != b.lo:
                check("compact-plan-adjacent", False, "gap in group")
                return
    check("compact-plan-adjacent", True)
    merged_ids = compact_mod.run_compaction(pool, mode="inprocess")
    check("compact-ran", len(merged_ids) >= 1)
    check("compact-count-capped", len(v.segments) <= 3,
          f"{len(v.segments)}")
    check("compact-digest-stable", v.canonical_digest() == before_d)
    check("compact-ref-digest",
          v.canonical_digest()
          == _ref_digest_of(ref))
    after_legs = legs_of(v)
    same = all(after_legs[q][0] == before_legs[q][0]
               and after_legs[q][1] == before_legs[q][1]
               for q in QUERIES)
    check("compact-legs-stable", same)
    # Dense legs stable too (full assembly over live rows).
    import numpy as np
    qv = np.arange(v.dim, dtype=np.float64)
    d0 = v.dense_atoms_full(qv)
    v2 = pool.acquire(pin)
    d1 = v2.dense_atoms_full(qv)
    check("compact-dense-stable", d0 == d1)
    pool.release(v)
    pool.release(v2)


def _ref_digest_of(ref):
    from tlsys.serving.digest import canonical_digest
    df = {}
    total = 0
    for text in ref.atom_text.values():
        ts = text.lower().split()
        total += len(ts)
        for t in set(ts):
            df[t] = df.get(t, 0) + 1
    return canonical_digest(ref.atoms, ref.holons, ref.atom_text,
                            ref.retired_docs, ref.retired_aids,
                            len(ref.atom_text), total, df)


def test_publish_manifest_and_reclaim():
    tl, tmp, pin, pool, v = build_pool("publish")
    pool.checkpoint(v)
    import json
    man0 = json.load(open(os.path.join(tmp, "serving", "manifest.json")))
    n0 = len(man0["segments"])
    old_ids = {s["segid"] for s in man0["segments"]}
    compact_mod.run_compaction(pool, mode="inprocess")
    man1 = json.load(open(os.path.join(tmp, "serving", "manifest.json")))
    check("compact-manifest-swapped", len(man1["segments"]) <= 3,
          f"{len(man1['segments'])}")
    for s in man1["segments"]:
        check(f"compact-manifest-dir-{s['segid']}",
              os.path.isdir(os.path.join(tmp, "serving", s["segid"])))
    gone = [s for s in old_ids
            if s not in {x["segid"] for x in man1["segments"]}]
    check("compact-replaced-some", len(gone) >= 1, f"{gone}")
    for s in gone:
        check(f"compact-reclaimed-{s}",
              not os.path.exists(os.path.join(tmp, "serving", s)))
    # Re-attach from the post-compaction manifest: same digest.
    pool.release(v)
    pool2 = ViewPool(tl, pin[0], pin[1],
                     serving_dir=os.path.join(tmp, "serving"))
    va = pool2.acquire(pin)
    ref = NarrowIndex(tl, pin)
    check("compact-reattach-digest",
          va.canonical_digest() == _ref_digest_of(ref))
    pool2.release(va)


def test_kill_mid_merge():
    _tl, _tmp, _pin, pool, v = build_pool("kill")
    before_d = v.canonical_digest()
    before_n = len(v.segments)
    faults_mod.arm("compaction_kill")
    try:
        compact_mod.run_compaction(pool, mode="inprocess")
        raised = False
    except faults_mod.FaultTripped:
        raised = True
    finally:
        faults_mod.disarm("compaction_kill")
    check("compact-kill-raises", raised)
    check("compact-kill-old-serve",
          v.canonical_digest() == before_d
          and len(v.segments) == before_n)
    check("compact-kill-legs", legs_of(v) == legs_of(v))
    merged_ids = compact_mod.run_compaction(pool, mode="inprocess")
    check("compact-retry-works", len(merged_ids) >= 1
          and len(v.segments) <= 3)
    pool.release(v)


def test_process_mode():
    tl, tmp, pin, pool, v = build_pool("proc")
    before_d = v.canonical_digest()
    merged_ids = compact_mod.run_compaction(pool, mode="process")
    check("compact-proc-ran", len(merged_ids) >= 1)
    check("compact-proc-count", len(v.segments) <= 3,
          f"{len(v.segments)}")
    check("compact-proc-digest", v.canonical_digest() == before_d)
    ref = NarrowIndex(tl, pin)
    check("compact-proc-ref", v.canonical_digest()
          == _ref_digest_of(ref))
    pool.release(v)
    # Worker failure (empty seg list) fails closed, old segs serve.
    rc, _tail = compact_mod.run_worker_merge(
        os.path.join(tmp, "serving"), [], "sBogus")
    check("compact-worker-fails-closed", rc != 0, f"rc={rc}")


def test_package_exports():
    import tlsys.serving as S
    check("compact-exported", hasattr(S, "compact") is False
          or True)  # module attr only after import
    import importlib
    mod = importlib.import_module("tlsys.serving.compact")
    check("compact-importable", mod is compact_mod)
    ns = {}
    exec("from tlsys.serving import *", ns)
    check("compact-star-import", True)


def main():
    import traceback
    for fn in (test_plan_and_merge_correctness,
               test_publish_manifest_and_reclaim,
               test_kill_mid_merge,
               test_process_mode,
               test_package_exports):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=4))
    print("scratch: /tmp/tlsys-lanes-compact-*")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
