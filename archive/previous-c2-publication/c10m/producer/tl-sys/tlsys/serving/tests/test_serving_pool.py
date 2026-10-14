"""Lane S ViewPool: advance O(Delta), atomic swap, K generations,
cold/attach/seal/checkpoint, rewind+epoch discipline.

Run: tl-sys/.venv/bin/python tl-sys/tlsys/serving/tests/test_serving_pool.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixture import (  # noqa: E402
    emb_votes, fixture_approval, make_docs, make_store)
from tlsys.serving.digest import canonical_digest  # noqa: E402
from tlsys.serving.view import (  # noqa: E402
    EpochChangedError, RewindError, StaleViewError, ViewPool)
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.lifecycle import retire_docs  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def ref_digest(ref):
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


def build_store():
    docs1 = make_docs(10, seed=21)
    docs1 = [(f"b1-{i}", t) for i, (_d, t) in enumerate(docs1)]
    tl, tmp, _p = make_store(docs1, emb_votes, prefix="tlsys-lanes-pool-")
    pin1 = tl.pin()
    docs2 = make_docs(10, seed=22)
    docs2 = [(f"b2-{i}", t) for i, (_d, t) in enumerate(docs2)]
    ingest_docs(tl, docs2, emb_votes)
    pin2 = tl.pin()
    retire_docs(tl, ["b1-1", "b2-3"], reason="pool",
                approvals={d: fixture_approval(f"pool-{d}")
                           for d in ("b1-1", "b2-3")})
    pin3 = tl.pin()
    return tl, tmp, pin1, pin2, pin3


def test_cold_matches_reference():
    tl, _tmp, pin1, _p2, _p3 = build_store()
    pool = ViewPool(tl, pin1[0], pin1[1])
    v = pool.acquire(pin1)
    ref = NarrowIndex(tl, pin1)
    check("pool-cold-atoms", set(v.atoms) == set(ref.atoms))
    check("pool-cold-holons", set(v.holons) == set(ref.holons))
    check("pool-cold-text", dict(v.atom_text) == dict(ref.atom_text))
    check("pool-cold-digest", v.canonical_digest() == ref_digest(ref))
    check("pool-cold-frontier", v.frontier == pin1[2])
    pool.release(v)


def test_advance_delta_and_swap():
    tl, _tmp, pin1, pin2, pin3 = build_store()
    pool = ViewPool(tl, pin1[0], pin1[1])
    v1 = pool.acquire(pin1)
    before = v1.canonical_digest()
    bm_before = v1.bm25("the domestic cat")
    c0 = pool.counters.totals()["log_rows_read"]
    exp_rows = len(tl.read_commits_all(pin1[0], pin1[1], pin2[2],
                                       kind="ACCEPT_ATOMS",
                                       min_seq=pin1[2]))
    v2 = pool.advance(v1, pin2)
    c1 = pool.counters.totals()["log_rows_read"]
    check("pool-advance-reads-delta", c1 - c0 == exp_rows,
          f"{c1 - c0} vs {exp_rows}")
    check("pool-old-frozen", v1._live is False)
    check("pool-old-pin", v1.pin == pin1)
    check("pool-old-serves", v1.canonical_digest() == before)
    check("pool-old-bm25", v1.bm25("the domestic cat") == bm_before)
    check("pool-new-pin", v2.pin == pin2 and v2._live is True)
    ref2 = NarrowIndex(tl, pin2)
    check("pool-advance-digest", v2.canonical_digest()
          == ref_digest(ref2))
    # Stale (materialized) old view still advances correctly.
    v3 = pool.advance(v1, pin3)
    ref3 = NarrowIndex(tl, pin3)
    check("pool-advance-from-stale", v3.canonical_digest()
          == ref_digest(ref3))
    for v in (v1, v2, v3):
        pool.release(v)


def test_k_generations():
    tl, _tmp, pin1, pin2, pin3 = build_store()
    pool = ViewPool(tl, pin1[0], pin1[1],
                    config={"retained_generations_K": 2})
    v1 = pool.acquire(pin1)
    v2 = pool.acquire(pin2)
    pool.release(v1)
    v3 = pool.acquire(pin3)
    st = pool.stats()
    check("pool-k-cap", st["retained"] == [pin2[2], pin3[2]],
          f"{st['retained']}")
    # Held views are never evicted (kept over cap).
    v1b = pool.acquire(pin1)
    st = pool.stats()
    check("pool-held-kept", pin1[2] in st["retained"]
          and len(st["retained"]) == 3, f"{st['retained']}")
    for v in (v1b, v2, v3):
        pool.release(v)


def test_rewind_and_epoch():
    tl, _tmp, pin1, pin2, _p3 = build_store()
    pool = ViewPool(tl, pin1[0], pin1[1])
    v2 = pool.acquire(pin2)
    try:
        pool.advance(v2, pin1)
        check("pool-rewind-raises", False, "no RewindError")
    except RewindError:
        check("pool-rewind-raises", True)
    # acquire() of an older-than-all pin cold-builds it.
    pool.release(v2)
    pool2 = ViewPool(tl, pin1[0], pin1[1])
    va = pool2.acquire(pin2)
    pool2.release(va)
    pool2.release(va)
    vb = pool2.acquire(pin1)
    ref1 = NarrowIndex(tl, pin1)
    check("pool-rewind-cold", vb.canonical_digest()
          == ref_digest(ref1))
    try:
        pool2.acquire(("other-birth", pin1[1], 0, "x"))
        check("pool-epoch-raises", False, "no EpochChangedError")
    except EpochChangedError:
        check("pool-epoch-raises", True)
    try:
        pool2.release(v2)
        check("pool-foreign-raises", False, "no StaleViewError")
    except StaleViewError:
        check("pool-foreign-raises", True)
    pool2.release(vb)


def test_seal_and_checkpoint_attach():
    tl, tmp, pin1, _p2, pin3 = build_store()
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin1[0], pin1[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 5})
    v = pool.acquire(pin3)
    check("pool-sealed", len(v.segments) >= 1,
          f"{len(v.segments)} segments")
    ref3 = NarrowIndex(tl, pin3)
    check("pool-sealed-digest", v.canonical_digest()
          == ref_digest(ref3))
    payload = pool.checkpoint(v)
    check("pool-manifest",
          os.path.isfile(os.path.join(sdir, "manifest.json")))
    check("pool-checkpoint-file",
          os.path.isfile(os.path.join(sdir, "checkpoint.json")))
    check("pool-checkpoint-frontier",
          payload["checkpoint_frontier"] == pin3[2])
    pool.release(v)
    # Fresh pool attaches (validates + pre-touches + serves).
    pool2 = ViewPool(tl, pin1[0], pin1[1], serving_dir=sdir)
    va = pool2.acquire(pin3)
    check("pool-attach-digest", va.canonical_digest()
          == ref_digest(ref3))
    check("pool-attach-sealed", len(va.segments) == len(v.segments),
          f"{len(va.segments)} vs {len(v.segments)}")
    pool2.release(va)
    # Tail: ingest more, attach the newer pin (replay beyond seal).
    docs4 = make_docs(4, seed=23)
    docs4 = [(f"b4-{i}", t) for i, (_d, t) in enumerate(docs4)]
    ingest_docs(tl, docs4, emb_votes)
    pin4 = tl.pin()
    vb = pool2.acquire(pin4)
    ref4 = NarrowIndex(tl, pin4)
    check("pool-attach-tail", vb.canonical_digest() == ref_digest(ref4))
    pool2.release(vb)


def test_parallel_cold():
    tl, _tmp, pin1, pin2, pin3 = build_store()
    pool = ViewPool(tl, pin1[0], pin1[1])
    vs = pool.acquire(pin3)
    ds = vs.canonical_digest()
    pool.release(vs)
    pool2 = ViewPool(tl, pin1[0], pin1[1])
    vp = pool2.cold_build(pin3,
                          ranges=[(0, pin1[2]), (pin1[2], pin2[2]),
                                  (pin2[2], pin3[2])],
                          parallel=True, max_workers=2)
    check("pool-parallel-digest", vp.canonical_digest() == ds)
    pool2.release(vp)
    try:
        pool2.cold_build(pin3, ranges=[(0, pin3[2] - 1)])
        check("pool-ranges-validated", False, "bad ranges accepted")
    except ValueError:
        check("pool-ranges-validated", True)
    pool2.release(pool2.acquire(pin3))


def main():
    import traceback
    for fn in (test_cold_matches_reference,
               test_advance_delta_and_swap,
               test_k_generations,
               test_rewind_and_epoch,
               test_seal_and_checkpoint_attach,
               test_parallel_cold):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=4))
    print("scratch: /tmp/tlsys-lanes-pool-*")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
