"""Maintained Lane S serving tests (S-3): segments/view/compaction/
tombstones/attach behavior pins.

Smallest maintained pins over scratch stores with a deterministic fake
encoder (no model weights). Covers the S-3 contract surface: packed
postings (int32/uint16, exact values, legacy int64 still loads),
segment validation + quarantine, view advance/attach digest equality,
compaction to the calibrated segment bound, tombstone union/version,
and attach stage-split instrumentation.

Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_serving_s3.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "tlsys",
    "serving", "tests")))

import numpy as np  # noqa: E402

from fixture import emb_votes, make_docs, make_store  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.serving import compact as compact_mod  # noqa: E402
from tlsys.serving import segments as seg_mod  # noqa: E402
from tlsys.serving.lexical import TermLexicon  # noqa: E402
from tlsys.serving.view import (EpochChangedError, RewindError,  # noqa: E402
                                ViewPool, tombstone_version_of)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


QUERIES = ["the domestic cat", "sport medic", "alpha beta"]


def _ref_df_total(ref):
    df = {}
    total = 0
    for text in ref.atom_text.values():
        ts = text.lower().split()
        total += len(ts)
        for t in set(ts):
            df[t] = df.get(t, 0) + 1
    return df, total


def _ref_digest_of(ref):
    from tlsys.serving.digest import canonical_digest
    df, total = _ref_df_total(ref)
    return canonical_digest(ref.atoms, ref.holons, ref.atom_text,
                            ref.retired_docs, ref.retired_aids,
                            len(ref.atom_text), total, df)


def _small_store(tag, n_docs=24, retire=None, seed=101):
    docs = make_docs(n_docs, seed=seed)
    docs = [(f"s3-{tag}-{i}", t) for i, (_d, t) in enumerate(docs)]
    return make_store(docs, emb_votes, retire=retire,
                      prefix=f"tlsys-s3-{tag}-")


# -- segments ------------------------------------------------------

def test_seg_packed_roundtrip():
    tl, tmp, pin = _small_store("seg")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 7})
    v = pool.acquire(pin)
    pool.checkpoint(v)
    check("s3-seg-sealed", len(v.segments) >= 1,
          f"{len(v.segments)} segments")
    seg0 = v.segments[0]
    segdir = os.path.join(sdir, seg0.segid)
    po = np.load(os.path.join(segdir, "lex_postings_ord.npy"))
    pt = np.load(os.path.join(segdir, "lex_postings_tf.npy"))
    check("s3-seg-packed-ord-i32", po.dtype == np.int32, f"{po.dtype}")
    check("s3-seg-packed-tf-u16", pt.dtype == np.uint16, f"{pt.dtype}")
    # Exact values preserved: postings match the live view + reference.
    ref = NarrowIndex(tl, pin, use_reference=True)
    live = v.postings_live()
    ok = all(live.get(t) == ref.postings.get(t)
             for t in set(live) | set(ref.postings))
    check("s3-seg-postings-exact-vs-ref", ok)
    got = {t: [(int(o), int(f)) for o, f in
               zip(*[a.tolist() for a in seg0.lex.postings_of(t)])]
           for t in seg0.lex.terms}
    reloaded = seg_mod.Segment.load(segdir)
    want = {t: [(int(o), int(f)) for o, f in
                zip(*[a.tolist() for a in reloaded.lex.postings_of(t)])]
            for t in reloaded.lex.terms}
    check("s3-seg-save-load-exact", got == want)
    # 6 bytes/posting on disk (int32 ord + uint16 tf), not 16.
    n_post = int(sum(len(reloaded.lex.postings_of(t)[0])
                     for t in reloaded.lex.terms))
    raw = (os.path.getsize(os.path.join(segdir, "lex_postings_ord.npy"))
           + os.path.getsize(os.path.join(segdir, "lex_postings_tf.npy")))
    check("s3-seg-packed-6B",
          raw < 16 * n_post + 512 and raw >= 6 * n_post,
          f"raw={raw} n_post={n_post}")
    pool.release(v)
    tl.close()


def test_seg_legacy_int64_loads():
    tl, tmp, pin = _small_store("legacy")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 1000})
    v = pool.acquire(pin)
    pool.checkpoint(v)
    segdir = os.path.join(sdir, v.segments[0].segid)
    before = {t: [a.tolist() for a in v.segments[0].lex.postings_of(t)]
              for t in v.segments[0].lex.terms}
    # Rewrite the two postings files as legacy int64; re-point digests.
    for name in ("lex_postings_ord.npy", "lex_postings_tf.npy"):
        p = os.path.join(segdir, name)
        np.save(p, np.load(p).astype(np.int64))
    hpath = os.path.join(segdir, "header.json")
    with open(hpath) as f:
        header = json.load(f)
    for name in ("lex_postings_ord.npy", "lex_postings_tf.npy"):
        header["files"][name] = seg_mod.sha256_file(
            os.path.join(segdir, name))
    with open(hpath, "w") as f:
        json.dump(header, f, sort_keys=True)
    seg = seg_mod.Segment.load(segdir)
    after = {t: [a.tolist() for a in seg.lex.postings_of(t)]
             for t in seg.lex.terms}
    check("s3-seg-legacy-i64-loads", before == after)
    pool.release(v)
    tl.close()


def test_seg_overflow_fails_closed():
    try:
        TermLexicon(["t"], [0, 1], [2 ** 31], [1], {0: 1}, [1], [0])
        check("s3-seg-ord-overflow", False, "int32 overflow accepted!")
    except (ValueError, OverflowError):
        check("s3-seg-ord-overflow", True)
    try:
        TermLexicon(["t"], [0, 1], [0], [70000], {0: 1}, [1], [0])
        check("s3-seg-tf-overflow", False, "uint16 overflow accepted!")
    except (ValueError, OverflowError):
        check("s3-seg-tf-overflow", True)


def test_seg_corrupt_quarantine():
    tl, tmp, pin = _small_store("quar")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 1000})
    v = pool.acquire(pin)
    pool.checkpoint(v)
    segdir = os.path.join(sdir, v.segments[0].segid)
    with open(os.path.join(segdir, "vectors.npy"), "r+b") as f:
        f.seek(100)
        b = f.read(1)
        f.seek(100)
        f.write(bytes([b[0] ^ 0xFF]))
    try:
        seg_mod.Segment.load(segdir)
        check("s3-seg-corrupt-detected", False, "flipped byte served!")
    except seg_mod.SegmentError:
        check("s3-seg-corrupt-detected", True)
    dest = seg_mod.quarantine(segdir, os.path.join(sdir, "quarantined"))
    check("s3-seg-quarantined",
          os.path.isdir(dest) and not os.path.exists(segdir), dest)
    pool.release(v)
    tl.close()


# -- view ----------------------------------------------------------

def test_view_advance_attach_digest():
    tl, tmp, pin = _small_store("view")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 7})
    v = pool.acquire(pin)
    ref = NarrowIndex(tl, pin, use_reference=True)
    check("s3-view-digest-eq-ref",
          v.canonical_digest() == _ref_digest_of(ref))
    same = all(v.bm25(q) == ref.bm25(q) for q in QUERIES)
    check("s3-view-bm25-bitwise", same)
    pool.checkpoint(v)
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    va = pool2.acquire(pin)
    check("s3-view-attach-digest",
          va.canonical_digest() == v.canonical_digest())
    check("s3-view-attach-count",
          len(va.segments) == len(v.segments),
          f"{len(va.segments)} vs {len(v.segments)}")
    pool.release(v)
    pool2.release(va)
    tl.close()


def test_view_pin_discipline():
    tl, tmp, pin = _small_store("pins")
    pool = ViewPool(tl, pin[0], pin[1])
    v = pool.acquire(pin)
    try:
        pool.acquire(("other-birth", pin[1], pin[2], "x"))
        check("s3-view-epoch-fail-closed", False, "foreign pin served!")
    except EpochChangedError:
        check("s3-view-epoch-fail-closed", True)
    try:
        pool.advance(v, (pin[0], pin[1], 0, "empty:0:0"))
        check("s3-view-rewind-refused", False, "rewind advanced!")
    except RewindError:
        check("s3-view-rewind-refused", True)
    pool.release(v)
    tl.close()


# -- compaction ----------------------------------------------------

def test_compact_to_bound():
    tl, tmp, pin = _small_store("compact", n_docs=30)
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 2,
                            "max_live_segments": 3,
                            "merge_fan_in": 2,
                            "compactor_mode": "inprocess"})
    mx = pin[2]
    cuts = [0] + [mx * i // 6 for i in range(1, 6)] + [mx]
    ranges = [(cuts[i], cuts[i + 1]) for i in range(6)
              if cuts[i + 1] > cuts[i]]
    v = pool.cold_build(pin, ranges=ranges)
    check("s3-compact-fragmented", len(v.segments) > 3,
          f"{len(v.segments)}")
    before_d = v.canonical_digest()
    merged = compact_mod.run_compaction(pool, mode="inprocess")
    check("s3-compact-ran", len(merged) >= 1, f"{merged}")
    check("s3-compact-within-bound", len(v.segments) <= 3,
          f"{len(v.segments)}")
    check("s3-compact-digest-stable",
          v.canonical_digest() == before_d)
    pool.checkpoint(v)
    import json as _json
    man = _json.load(open(os.path.join(sdir, "manifest.json")))
    check("s3-compact-manifest-bound", len(man["segments"]) <= 3,
          f"{len(man['segments'])}")
    pool.release(v)
    tl.close()


def test_checkpoint_preserves_chain():
    # Contract pin: checkpoint seals + persists the chain as-is (no
    # implicit merge); bound discipline is an explicit compact step.
    tl, tmp, pin = _small_store("ckpt", n_docs=30)
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 2,
                            "max_live_segments": 3,
                            "merge_fan_in": 2,
                            "compactor_mode": "inprocess"})
    mx = pin[2]
    cuts = [0] + [mx * i // 4 for i in range(1, 4)] + [mx]
    ranges = [(cuts[i], cuts[i + 1]) for i in range(4)
              if cuts[i + 1] > cuts[i]]
    v = pool.cold_build(pin, ranges=ranges)
    n0 = len(v.segments)
    payload = pool.checkpoint(v)
    check("s3-ckpt-chain-preserved",
          len(payload["segments"]) == n0, f"{len(payload['segments'])}")
    tl.close()


# -- tombstones ----------------------------------------------------

def test_tombstone_union_and_version():
    docs = make_docs(24, seed=202)
    docs = [(f"s3-tomb-{i}", t) for i, (_d, t) in enumerate(docs)]
    tl, tmp, pin = make_store(
        docs, emb_votes, retire=[docs[0][0], docs[5][0]],
        prefix="tlsys-s3-tomb-")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 7})
    v = pool.acquire(pin)
    ref = NarrowIndex(tl, pin, use_reference=True)
    check("s3-tomb-retired-eq",
          sorted(v.retired_docs) == sorted(ref.retired_docs),
          f"{sorted(v.retired_docs)}")
    check("s3-tomb-live-n-eq", v.live_n == len(ref.atom_text),
          f"live_n={v.live_n} ref={len(ref.atom_text)}")
    df_ref, total_ref = _ref_df_total(ref)
    check("s3-tomb-df-total-eq",
          (v.total_tokens, v.df) == (total_ref, df_ref),
          f"{v.total_tokens}/{len(v.df)}")
    ver0 = tombstone_version_of(set(v.retired_docs))
    payload = pool.checkpoint(v)
    check("s3-tomb-version-manifest",
          payload["tombstone_version"] == ver0)
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    va = pool2.acquire(pin)
    check("s3-tomb-version-attach-stable",
          tombstone_version_of(set(va.retired_docs)) == ver0)
    check("s3-tomb-digest-eq-ref",
          va.canonical_digest() == _ref_digest_of(ref))
    pool.release(v)
    pool2.release(va)
    tl.close()


# -- attach instrumentation ----------------------------------------

def test_attach_stage_splits():
    tl, tmp, pin = _small_store("stages", n_docs=30)
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 5})
    v = pool.acquire(pin)
    pool.checkpoint(v)
    n_seg = len(v.segments)
    pool.release(v)
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    stages = {}
    va = pool2.attach(pin, stages=stages)
    check("s3-stages-present",
          {"manifest_read_ms", "seg_load_ms", "seg_logval_ms",
           "replay_ms", "pretouch_ms", "tail_ms", "attach_total_ms",
           "segments_validated", "segments_rebuilt"}
          <= set(stages),
          f"{sorted(stages)}")
    check("s3-stages-all-validated",
          stages.get("segments_validated") == n_seg
          and stages.get("segments_rebuilt") == 0,
          f"{stages}")
    parts = sum(stages[k] for k in
                ("manifest_read_ms", "seg_load_ms", "seg_logval_ms",
                 "replay_ms", "pretouch_ms", "tail_ms"))
    check("s3-stages-sum-within-total",
          parts <= stages.get("attach_total_ms", -1) + 1e-6,
          f"parts={parts} total={stages.get('attach_total_ms')}")
    check("s3-stages-nonneg",
          all(stages[k] >= 0 for k in
              ("manifest_read_ms", "seg_load_ms", "seg_logval_ms",
               "replay_ms", "pretouch_ms", "tail_ms",
               "attach_total_ms")))
    check("s3-stages-digest",
          va.canonical_digest() == v.canonical_digest())
    pool2.release(va)
    tl.close()


def test_attach_log_mismatch_rebuild():
    # Batched log check (A15) must actually RUN: tamper a header's
    # op_ids (files still digest-valid) -> the range quarantines +
    # rebuilds from the log, digest still equal.
    tl, tmp, pin = _small_store("logval", n_docs=30)
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 5})
    v = pool.acquire(pin)
    pool.checkpoint(v)
    n_seg = len(v.segments)
    want_d = v.canonical_digest()
    segdir = os.path.join(sdir, v.segments[0].segid)
    hpath = os.path.join(segdir, "header.json")
    with open(hpath) as f:
        header = json.load(f)
    header["op_hash"] = "sha256:" + "00" * 32
    with open(hpath, "w") as f:
        json.dump(header, f, sort_keys=True)
    pool.release(v)
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    stages = {}
    va = pool2.acquire(pin, stages=stages)
    check("s3-logval-rebuilt-one",
          stages.get("segments_rebuilt") == 1
          and stages.get("segments_validated") == n_seg - 1,
          f"{stages}")
    check("s3-logval-digest-stable",
          va.canonical_digest() == want_d)
    pool2.release(va)
    tl.close()


def test_attach_empty_store():
    tl, tmp, pin = make_store([], emb_votes, prefix="tlsys-s3-empty-")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    v = pool.acquire(pin)
    payload = pool.checkpoint(v)
    check("s3-empty-checkpoint", payload["segments"] == []
          and payload["live_n"] == 0, f"{payload}")
    pool.release(v)
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    stages = {}
    va = pool2.acquire(pin, stages=stages)
    check("s3-empty-attach",
          va.live_n == 0 and len(va.segments) == 0
          and stages.get("segments_validated") == 0,
          f"live_n={va.live_n} stages={stages}")
    pool2.release(va)
    tl.close()


def main():
    import traceback
    for fn in (test_seg_packed_roundtrip,
               test_seg_legacy_int64_loads,
               test_seg_overflow_fails_closed,
               test_seg_corrupt_quarantine,
               test_view_advance_attach_digest,
               test_view_pin_discipline,
               test_compact_to_bound,
               test_checkpoint_preserves_chain,
               test_tombstone_union_and_version,
               test_attach_stage_splits,
               test_attach_log_mismatch_rebuild,
               test_attach_empty_store):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=4))
    print("scratch: /tmp/tlsys-s3-*")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
