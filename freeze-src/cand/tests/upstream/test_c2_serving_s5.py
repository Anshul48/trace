"""Maintained Lane S serving tests (S-5): attach surgery pins.

Fresh-attach surgery: read-once segment load + bulk replay + autonomous
debt enforcement + full work accounting (closure B). Smallest maintained
pins over scratch stores with a deterministic fake encoder (no weights).

Bounds are on WORK (deterministic: file opens, tokenizer calls, row
counts), never on wall-clock time (no flake-prone timing asserts; the
5 s ceiling evidence lives in lane-S5/REPORT.md + measure scripts).

Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_serving_s5.py
"""
import builtins
import io
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
from tlsys.serving import faults as faults_mod  # noqa: E402
from tlsys.serving import segments as seg_mod  # noqa: E402
from tlsys.serving.counters import ServeCounters  # noqa: E402
from tlsys.serving.view import ViewPool  # noqa: E402

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
    docs = [(f"s5-{tag}-{i}", t) for i, (_d, t) in enumerate(docs)]
    return make_store(docs, emb_votes, retire=retire,
                      prefix=f"tlsys-s5-{tag}-")


def _checkpointed(tag, n_docs=30, retire=None, flush=5, seed=505,
                  extra_config=None, n_ranges=3):
    tl, tmp, pin = _small_store(tag, n_docs=n_docs, retire=retire,
                               seed=seed)
    sdir = os.path.join(tmp, "serving")
    cfg = {"delta_flush_atoms": flush}
    cfg.update(extra_config or {})
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir, config=cfg)
    mx = pin[2]
    cuts = [0] + [mx * i // n_ranges for i in range(1, n_ranges)] + [mx]
    ranges = [(cuts[i], cuts[i + 1]) for i in range(n_ranges)
              if cuts[i + 1] > cuts[i]]
    v = pool.cold_build(pin, ranges=ranges)
    pool.checkpoint(v)
    return tl, tmp, pin, sdir, pool, v


# -- read-once load ------------------------------------------------

def test_load_read_once():
    tl, tmp, pin, sdir, pool, v = _checkpointed("ronce")
    segdirs = [os.path.join(sdir, s.segid) for s in v.segments]
    check("s5-load-multiseg", len(segdirs) >= 2, f"{len(segdirs)}")
    real_open = builtins.open
    opens = {}

    def counting_open(path, *a, **k):
        p = str(path)
        for sd in segdirs:
            if p.startswith(sd + os.sep):
                opens[p] = opens.get(p, 0) + 1
        return real_open(path, *a, **k)

    builtins.open = counting_open
    try:
        for sd in segdirs:
            seg_mod.Segment.load(sd)
    finally:
        builtins.open = real_open
    worst = {}
    for sd in segdirs:
        for name in sorted(os.listdir(sd)):
            p = os.path.join(sd, name)
            n = opens.get(p, 0)
            if n != 1:
                worst[p] = n
    check("s5-load-read-once", not worst,
          f"files opened != once: {dict(list(worst.items())[:4])}")
    pool.release(v)
    tl.close()


def test_load_holon_columnar():
    tl, tmp, pin, sdir, pool, v = _checkpointed("hcol")
    assert v.segments, "need sealed segments"
    seg0 = v.segments[0]
    segdir = os.path.join(sdir, seg0.segid)
    npy_p = os.path.join(segdir, "holon_vectors.npy")
    meta_p = os.path.join(segdir, "holon_meta.jsonl")
    check("s5-load-holon-npy-written", os.path.isfile(npy_p), segdir)
    check("s5-load-holon-meta-written", os.path.isfile(meta_p), segdir)
    if not (os.path.isfile(npy_p) and os.path.isfile(meta_p)):
        pool.release(v)
        tl.close()
        return
    with open(os.path.join(segdir, "header.json")) as f:
        header = json.load(f)
    check("s5-load-holon-header-pinned",
          "holon_vectors.npy" in header["files"]
          and "holon_meta.jsonl" in header["files"],
          f"{sorted(header['files'])}")
    reloaded = seg_mod.Segment.load(segdir)
    same = len(reloaded.holon_rows) == len(seg0.holon_rows) and all(
        r["hid"] == s["hid"] and r["ordinal"] == s["ordinal"]
        and r["seq"] == s["seq"] and r["op_id"] == s["op_id"]
        and list(r["members"]) == list(s["members"])
        and r.get("kind") == s.get("kind")
        and list(r.get("children") or [])
        == list(s.get("children") or [])
        and np.array_equal(np.asarray(r["descriptor"], dtype=np.float64),
                           np.asarray(s["descriptor"], dtype=np.float64))
        for r, s in zip(reloaded.holon_rows, seg0.holon_rows))
    check("s5-load-holon-exact", same)
    pool.release(v)
    tl.close()


def test_load_legacy_no_holon_files():
    # Old dirs (full holons.jsonl, no columnar files) still load exact.
    tl, tmp, pin, sdir, pool, v = _checkpointed("legacy")
    want_d = v.canonical_digest()
    for s in v.segments:
        segdir = os.path.join(sdir, s.segid)
        for name in ("holon_vectors.npy", "holon_meta.jsonl"):
            p = os.path.join(segdir, name)
            if os.path.exists(p):
                os.remove(p)
        hpath = os.path.join(segdir, "header.json")
        with open(hpath) as f:
            header = json.load(f)
        for name in ("holon_vectors.npy", "holon_meta.jsonl"):
            header["files"].pop(name, None)
        header.pop("holon_encoding", None)
        with open(hpath, "w") as f:
            json.dump(header, f, sort_keys=True)
    pool.release(v)
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    stages = {}
    va = pool2.attach(pin, stages=stages)
    check("s5-load-legacy-digest", va.canonical_digest() == want_d)
    check("s5-load-legacy-validated",
          stages.get("segments_rebuilt") == 0
          and stages.get("cold_fallback") is None, f"{stages}")
    pool2.release(va)
    tl.close()


def _craft_holon_columnar(segdir):
    """Hand-write holon columnar files for ANY code version (compat
    probe: arrived code ignores them; S-5 code verifies them)."""
    with open(os.path.join(segdir, "holons.jsonl")) as f:
        rows = [json.loads(line) for line in f]
    dim = max((len(r.get("descriptor") or []) for r in rows),
              default=0)
    mat = np.stack([np.asarray(r.get("descriptor") or [],
                              dtype=np.float64)
                    if dim else np.empty((0,)) for r in rows]) \
        if rows else np.empty((0, max(dim, 0)))
    if rows and dim == 0:
        mat = np.empty((len(rows), 0))
    np.save(os.path.join(segdir, "holon_vectors.npy"), mat)
    with open(os.path.join(segdir, "holon_meta.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps({
                "hid": r["hid"], "ordinal": r["ordinal"],
                "seq": r["seq"], "op_id": r["op_id"],
                "members": r["members"],
                "kind": r.get("kind"),
                "children": list(r.get("children") or [])}) + "\n")
    hpath = os.path.join(segdir, "header.json")
    with open(hpath) as f:
        header = json.load(f)
    for name in ("holon_vectors.npy", "holon_meta.jsonl"):
        header["files"][name] = seg_mod.sha256_file(
            os.path.join(segdir, name))
    header["holon_encoding"] = "meta-jsonl+vec-f64-npy-v1"
    with open(hpath, "w") as f:
        json.dump(header, f, sort_keys=True)


def test_load_tampered_holon_npy():
    tl, tmp, pin, sdir, pool, v = _checkpointed("hnpytamper")
    segdir = os.path.join(sdir, v.segments[0].segid)
    if not os.path.isfile(os.path.join(segdir, "holon_vectors.npy")):
        _craft_holon_columnar(segdir)
    with open(os.path.join(segdir, "holon_vectors.npy"), "r+b") as f:
        f.seek(100)
        b = f.read(1)
        f.seek(100)
        f.write(bytes([b[0] ^ 0xFF]))
    try:
        seg_mod.Segment.load(segdir)
        check("s5-load-holon-tamper-detected", False,
              "flipped holon byte served!")
    except seg_mod.SegmentError:
        check("s5-load-holon-tamper-detected", True)
    pool.release(v)
    tl.close()


def test_load_parallel_matches_serial():
    # The size-gated parallel loader (10M path) must match serial
    # load exactly: digest, counts, legs, counters. Forced on here
    # (scout chains are below the gate); fails clean on arrived
    # code (no parallel path).
    import tlsys.serving.view as view_mod
    if not hasattr(view_mod, "PARALLEL_LOAD_BYTES"):
        check("s5-load-parallel-supported", False,
              "no size-gated parallel loader")
        return
    tl, tmp, pin, sdir, pool, v = _checkpointed("parload")
    want_d = v.canonical_digest()
    pool.release(v)
    real_gate = view_mod.PARALLEL_LOAD_BYTES
    view_mod.PARALLEL_LOAD_BYTES = 0
    try:
        counters = ServeCounters()
        pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                         counters=counters)
        stages = {}
        va = pool2.attach(pin, stages=stages)
    finally:
        view_mod.PARALLEL_LOAD_BYTES = real_gate
    check("s5-load-parallel-digest",
          va.canonical_digest() == want_d)
    check("s5-load-parallel-counts",
          stages.get("segments_validated") == len(v.segments)
          and stages.get("segments_rebuilt") == 0
          and stages.get("cold_fallback") is None, f"{stages}")
    ref = NarrowIndex(tl, pin, use_reference=True)
    check("s5-load-parallel-legs",
          all(va.bm25(q) == ref.bm25(q) for q in QUERIES))
    expect = 0
    for s in v.segments:
        segdir = os.path.join(sdir, s.segid)
        for name in sorted(os.listdir(segdir)):
            p = os.path.join(segdir, name)
            if os.path.isfile(p):
                expect += os.path.getsize(p)
    check("s5-load-parallel-bytes",
          counters.totals()["bytes_read"] == expect,
          f"{counters.totals()['bytes_read']} vs {expect}")
    pool2.release(va)
    tl.close()


def test_load_parallel_quarantine_deterministic():
    # Corrupt-segment handling is identical under forced-parallel
    # load (manifest-order quarantine + rebuild, digest stable).
    import tlsys.serving.view as view_mod
    if not hasattr(view_mod, "PARALLEL_LOAD_BYTES"):
        check("s5-load-parallel-quarantine-path", False,
              "no size-gated parallel loader")
        return
    tl, tmp, pin, sdir, pool, v = _checkpointed("parquar")
    want_d = v.canonical_digest()
    bad = os.path.join(sdir, v.segments[0].segid, "vectors.npy")
    with open(bad, "r+b") as f:
        f.seek(100)
        b = f.read(1)
        f.seek(100)
        f.write(bytes([b[0] ^ 0xFF]))
    pool.release(v)
    real_gate = view_mod.PARALLEL_LOAD_BYTES
    view_mod.PARALLEL_LOAD_BYTES = 0
    try:
        pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
        stages = {}
        va = pool2.attach(pin, stages=stages)
    finally:
        view_mod.PARALLEL_LOAD_BYTES = real_gate
    check("s5-load-parallel-quarantine",
          stages.get("segments_rebuilt") == 1
          and stages.get("cold_fallback") is None, f"{stages}")
    check("s5-load-parallel-quarantine-digest",
          va.canonical_digest() == want_d)
    pool2.release(va)
    tl.close()


def test_load_bytes_exact():
    tl, tmp, pin, sdir, pool, v = _checkpointed("bytes")
    expect = 0
    for s in v.segments:
        segdir = os.path.join(sdir, s.segid)
        for name in sorted(os.listdir(segdir)):
            p = os.path.join(segdir, name)
            if os.path.isfile(p):
                expect += os.path.getsize(p)
    pool.release(v)
    counters = ServeCounters()
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                     counters=counters)
    va = pool2.attach(pin)
    got = counters.totals()["bytes_read"]
    check("s5-load-bytes-exact", got == expect,
          f"bytes_read={got} files={expect}")
    pool2.release(va)
    tl.close()


# -- bulk replay ---------------------------------------------------

def _counting_toks():
    import tlsys.serving.tombstones as tomb_mod
    import tlsys.serving.view as view_mod
    from tlsys.serving.lexical import toks as real
    calls = []

    def spy(text):
        calls.append(1)
        return real(text)

    return view_mod, tomb_mod, spy, calls


def test_replay_no_live_retokenize():
    docs = make_docs(30, seed=606)
    docs = [(f"s5-notok-{i}", t) for i, (_d, t) in enumerate(docs)]
    tl, tmp, pin = make_store(
        docs, emb_votes, retire=[docs[0][0], docs[5][0]],
        prefix="tlsys-s5-notok-")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 5})
    v = pool.acquire(pin)
    pool.checkpoint(v)
    n_retired_aids = len(v.retired_aids)
    pool.release(v)
    view_mod, tomb_mod, spy, calls = _counting_toks()
    real_view, real_tomb = view_mod.toks, tomb_mod.toks
    view_mod.toks = spy
    tomb_mod.toks = spy
    try:
        pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
        va = pool2.attach(pin)
    finally:
        view_mod.toks = real_view
        tomb_mod.toks = real_tomb
    # Bulk replay tokenizes retired-aid texts once each (adjustments)
    # plus one toks per multi-occurrence aid (fixtures: none) — never
    # the live rows (arrived code tokenizes every live row here).
    check("s5-replay-no-live-retokenize", len(calls) == n_retired_aids,
          f"toks={len(calls)} retired_aids={n_retired_aids} "
          f"live_n={va.live_n}")
    check("s5-replay-notok-digest",
          va.canonical_digest() == v.canonical_digest())
    pool2.release(va)
    tl.close()


def _live_state_of(view):
    return {
        "atoms": {a: (e["seq"], e.get("op_id"), e["doc_id"],
                      tuple(e["span"]), e["text_art"], e["text_digest"],
                      tuple(np.asarray(e["descriptor"],
                                       dtype=np.float64).tolist()))
                  for a, e in view.atoms.items()},
        "holons": {h: (e["seq"], e.get("op_id"), tuple(e["members"]),
                       tuple(np.asarray(e["descriptor"],
                                        dtype=np.float64).tolist()),
                       e.get("kind"), tuple(e.get("children") or []))
                   for h, e in view.holons.items()},
        "doc_atoms": {d: list(a) for d, a in view.doc_atoms.items()},
        "atom_text": dict(view.atom_text),
        "retired_aids": set(view.retired_aids),
        "df": dict(view.df),
        "total": view.total_tokens,
        "live_n": view.live_n,
        "ord_atom": dict(view.ord_atom),
        "ord_holon": dict(view.ord_holon),
        "aid_of_ord": dict(view.aid_of_ord),
        "atom_order": list(view.atom_order),
        "doclen_of": dict(view.doclen_of),
        "atom_leaves": {a: list(v) for a, v in
                        view.atom_leaves.items()},
        "leaf_parents": {c: list(v) for c, v in
                         view.leaf_parents.items()},
        "overrides": {o: tuple(np.asarray(vec, dtype=np.float64).tolist())
                      for o, vec in view._atom_overrides.items()},
        "dim": view.dim,
        "tomb": set(view.tomb.materialize()),
    }


def test_replay_differential_synthetic():
    # Replay == manual per-row inserts on adversarial rows (recommit
    # with vector change, retirement, holon supersession). Guards the
    # bulk rewrite: must hold before AND after (exact-equivalence).
    from tlsys.serving.lexical import TermLexicon
    tl, _tmp, pin = _small_store("synth", n_docs=4, seed=707)
    pool = ViewPool(tl, pin[0], pin[1])
    dim = 4
    d0 = [0.5, 0.0, 0.5, 0.0]
    d1 = [0.0, 0.5, 0.0, 0.5]
    d1b = [0.0, 0.25, 0.0, 0.75]
    rows = [
        {"aid": "a0", "ordinal": 0, "seq": 1, "op_id": "op1",
         "doc_id": "d0", "span": [0, 1], "text_art": "t0",
         "text_digest": "x0", "descriptor": d0},
        {"aid": "a1", "ordinal": 1, "seq": 2, "op_id": "op2",
         "doc_id": "d1", "span": [0, 2], "text_art": "t1",
         "text_digest": "x1", "descriptor": d1},
        # Same-aid recommit (later seq, changed vector, same text).
        {"aid": "a1", "ordinal": 1, "seq": 3, "op_id": "op3",
         "doc_id": "d1", "span": [0, 2], "text_art": "t1",
         "text_digest": "x1", "descriptor": d1b},
        {"aid": "a2", "ordinal": 2, "seq": 4, "op_id": "op4",
         "doc_id": "d2", "span": [0, 1], "text_art": "t2",
         "text_digest": "x2", "descriptor": d0},
    ]
    texts = ["alpha beta", "gamma delta", "gamma delta",
             "alpha epsilon"]
    hrows = [
        {"hid": "h0", "ordinal": 0, "seq": 1, "op_id": "op1",
         "members": ["a0"], "descriptor": d0, "kind": "seg-leaf",
         "children": []},
        # Supersession: same hid, new version.
        {"hid": "h0", "ordinal": 0, "seq": 5, "op_id": "op5",
         "members": ["a0", "a2"], "descriptor": d1,
         "kind": "seg-leaf", "children": []},
        {"hid": "d2", "ordinal": 1, "seq": 4, "op_id": "op4",
         "members": ["a2"], "descriptor": d0, "kind": None,
         "children": []},
    ]
    mat32 = np.asarray([d0, d1, d1b, d0], dtype=np.float32)
    seg = seg_mod.Segment("s0000000000-0000000005", 0, 5, pin[0],
                          pin[1], [dict(r) for r in rows],
                          list(texts), [dict(r) for r in hrows],
                          {"d2"}, ["op1", "op2", "op3", "op4", "op5"],
                          5, lex=TermLexicon.build(
                              [(r["ordinal"], t)
                               for r, t in zip(rows, texts)]),
                          mat32=mat32)
    entry = {"segid": seg.segid, "lo": 0, "hi": 5}
    got = pool._new_live()
    got._no_delta = True
    try:
        pool._replay_merged_locked(got, [(entry, seg)], [])
    finally:
        got._no_delta = False
    want = pool._new_live()
    want._no_delta = True
    try:
        for r, t in zip(rows, texts):
            want._insert_atom(
                r["seq"], r["op_id"],
                {"atom": r["aid"], "doc_id": r["doc_id"],
                 "span": r["span"], "text_artifact": r["text_art"],
                 "text_digest": r["text_digest"],
                 "descriptor": np.asarray(r["descriptor"],
                                          dtype=np.float64)}, t)
        for r in hrows:
            want._insert_holon(
                r["seq"], r["op_id"],
                {"holon": r["hid"], "members": r["members"],
                 "descriptor": np.asarray(r["descriptor"],
                                          dtype=np.float64),
                 "kind": r.get("kind"),
                 "children": r.get("children")})
        want._retire_docs(["d2"])
    finally:
        want._no_delta = False
    a, b = _live_state_of(got), _live_state_of(want)
    bad = [k for k in a if a[k] != b[k]]
    check("s5-replay-differential-synthetic", not bad, f"{bad}")
    check("s5-replay-synth-overrides",
          set(got._atom_overrides) == {1}
          and set(want._atom_overrides) == {1})
    tl.close()


def test_replay_ordinal_tamper():
    # Persisted ordinals are verified: swapping two rows' ordinals
    # (file digests repaired, log checks pass) must fail closed to
    # quarantine + rebuild, never serve silently.
    tl, tmp, pin, sdir, pool, v = _checkpointed("ordtamper")
    segdir = os.path.join(sdir, v.segments[0].segid)
    apath = os.path.join(segdir, "atoms.jsonl")
    with open(apath) as f:
        lines = [json.loads(line) for line in f]
    assert len(lines) >= 2
    lines[0]["ordinal"], lines[1]["ordinal"] = (lines[1]["ordinal"],
                                                lines[0]["ordinal"])
    with open(apath, "w") as f:
        for r in lines:
            f.write(json.dumps(r) + "\n")
    hpath = os.path.join(segdir, "header.json")
    with open(hpath) as f:
        header = json.load(f)
    header["files"]["atoms.jsonl"] = seg_mod.sha256_file(apath)
    with open(hpath, "w") as f:
        json.dump(header, f, sort_keys=True)
    pool.release(v)
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    stages = {}
    va = pool2.attach(pin, stages=stages)
    check("s5-replay-ordinal-tamper-caught",
          stages.get("segments_rebuilt") == 1
          or stages.get("cold_fallback") is not None,
          f"{stages}")
    check("s5-replay-ordinal-digest-stable",
          va.canonical_digest() == v.canonical_digest())
    pool2.release(va)
    tl.close()


def test_replay_override_range_tamper():
    # Out-of-range sealed override keys (digests repaired) fail
    # closed to quarantine + rebuild, never silent-ignore (old) or
    # wrong-row overwrite (unchecked bulk apply).
    tl, tmp, pin, sdir, pool, v = _checkpointed("ovrtamper")
    segdir = os.path.join(sdir, v.segments[0].segid)
    opath = os.path.join(segdir, "overrides.json")
    with open(opath) as f:
        ovr = json.load(f)
    dim = v.segments[0].mat32.shape[1]
    ovr["999999999"] = [0.0] * dim
    with open(opath, "w") as f:
        json.dump(ovr, f)
    hpath = os.path.join(segdir, "header.json")
    with open(hpath) as f:
        header = json.load(f)
    header["files"]["overrides.json"] = seg_mod.sha256_file(opath)
    with open(hpath, "w") as f:
        json.dump(header, f, sort_keys=True)
    pool.release(v)
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    stages = {}
    va = pool2.attach(pin, stages=stages)
    check("s5-replay-override-range-caught",
          stages.get("segments_rebuilt") == 1
          or stages.get("cold_fallback") is not None,
          f"{stages}")
    check("s5-replay-override-digest-stable",
          va.canonical_digest() == v.canonical_digest())
    pool2.release(va)
    tl.close()


def test_replay_parity_e2e():
    docs = make_docs(30, seed=808)
    docs = [(f"s5-par-{i}", t) for i, (_d, t) in enumerate(docs)]
    tl, tmp, pin = make_store(
        docs, emb_votes, retire=[docs[0][0], docs[7][0]],
        prefix="tlsys-s5-par-")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 5})
    v = pool.acquire(pin)
    ref = NarrowIndex(tl, pin, use_reference=True)
    check("s5-par-digest-eq-ref",
          v.canonical_digest() == _ref_digest_of(ref))
    pool.checkpoint(v)
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir)
    stages = {}
    va = pool2.attach(pin, stages=stages)
    check("s5-par-attach-digest",
          va.canonical_digest() == v.canonical_digest())
    check("s5-par-counts",
          stages.get("segments_validated") == len(v.segments)
          and stages.get("segments_rebuilt") == 0
          and stages.get("cold_fallback") is None, f"{stages}")
    check("s5-par-bm25-bitwise",
          all(va.bm25(q) == ref.bm25(q) for q in QUERIES))
    qv = np.asarray(ref.atoms[next(iter(ref.atoms))]["descriptor"],
                    dtype=np.float64)
    ids_a, _s_a = zip(*va.dense_atoms_full(qv)) if va.live_n else ((), ())
    r_ids = list(ref.atoms.keys())
    r_mat = np.stack([np.asarray(ref.atoms[i]["descriptor"],
                                 dtype=np.float64) for i in r_ids])
    r_norms = np.linalg.norm(r_mat, axis=1)
    r_norms[r_norms == 0.0] = 1.0
    from tlsys.query import _dense_rank
    ref_rank = _dense_rank(qv, r_ids, r_mat, r_norms)
    check("s5-par-dense-full-ids",
          list(ids_a) == [a for a, _s in ref_rank])
    pool.release(v)
    pool2.release(va)
    tl.close()


# -- debt enforcement ------------------------------------------------

def _advance_loop(n_deltas=8, bound=3, tag="debt", serving=True,
                  seed=909):
    from tlsys.ingest import ingest_docs
    from fixture import UnitNormEmbed
    import tempfile
    tmp = tempfile.mkdtemp(prefix=f"tlsys-s5-{tag}-")
    from tlsys.store_if import TLStore
    store_root = os.path.join(tmp, "store")
    tl = TLStore(store_root, create=True, lease_owner=f"s5-{tag}")
    emb = UnitNormEmbed(dim=16, seed=seed)
    docs = [(f"base-{i}", t) for i, (_d, t) in
            enumerate(make_docs(12, seed=seed))]
    ingest_docs(tl, docs, emb, place_xdoc=False)
    sdir = os.path.join(tmp, "serving") if serving else None
    pool = ViewPool(tl, tl.pin()[0], tl.pin()[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 4,
                            "max_live_segments": bound,
                            "merge_fan_in": 2})
    v = pool.acquire(tl.pin())
    if sdir is not None:
        pool.checkpoint(v)
    for it in range(n_deltas):
        term = f"zzs5{tag}{it}"
        ddocs = [(f"{tag}-{it}-{j}",
                  f"{term} " + " ".join(f"w{j}x{k}" for k in range(8)))
                 for j in range(3)]
        ingest_docs(tl, ddocs, emb, place_xdoc=False)
        v = pool.advance(v, tl.pin())
        if sdir is not None:
            pool.checkpoint(v)
    return tl, tmp, pool, v


def test_debt_advance_bounds():
    tl, tmp, pool, v = _advance_loop()
    check("s5-debt-advance-bounded", len(v.segments) <= 4,
          f"{len(v.segments)} segments (bound=3, no manual compact)")
    man = json.load(open(os.path.join(tmp, "serving",
                                      "manifest.json")))
    check("s5-debt-manifest-bounded", len(man["segments"]) <= 4,
          f"{len(man['segments'])}")
    pool2 = ViewPool(tl, v.pin[0], v.pin[1],
                     serving_dir=os.path.join(tmp, "serving"))
    va = pool2.attach(v.pin)
    check("s5-debt-digest-stable",
          va.canonical_digest() == v.canonical_digest())
    check("s5-debt-gauge",
          pool.counters.totals()["segments_live"] <= 4,
          f"{pool.counters.totals()['segments_live']}")
    tl.close()


def test_debt_inmemory():
    tl, tmp, pool, v = _advance_loop(tag="debtmem", serving=False)
    check("s5-debt-inmemory-bounded", len(v.segments) <= 4,
          f"{len(v.segments)} segments (bound=3, in-memory)")
    tl.close()


def test_debt_failure_open():
    tl, tmp, pool, v0 = _advance_loop(tag="debtfi", n_deltas=2)
    from tlsys.ingest import ingest_docs
    from fixture import UnitNormEmbed
    emb = UnitNormEmbed(dim=16, seed=911)
    for it in range(6):
        term = f"zzs5debtfi2{it}"
        ddocs = [(f"fi2-{it}-{j}",
                  f"{term} " + " ".join(f"w{j}x{k}" for k in range(8)))
                 for j in range(3)]
        ingest_docs(tl, ddocs, emb, place_xdoc=False)
    faults_mod.arm("compaction_kill")
    try:
        v1 = pool.advance(v0, tl.pin())
    finally:
        faults_mod.disarm()
    ref = NarrowIndex(tl, tl.pin(), use_reference=True)
    check("s5-debt-failure-advance-ok",
          v1.canonical_digest() == _ref_digest_of(ref))
    check("s5-debt-failure-counted",
          pool.counters.totals()["failed_retried"] >= 1,
          f"{pool.counters.totals()['failed_retried']}")
    tl.close()


def test_debt_bulk_pinned_intact():
    # Pinned bulk semantics preserved: cold_build fragments and
    # checkpoint preserves (explicit compact still bounds it).
    tl, tmp, pin = _small_store("bulkpin", n_docs=30)
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
    check("s5-debt-bulk-fragments", len(v.segments) > 3,
          f"{len(v.segments)}")
    payload = pool.checkpoint(v)
    check("s5-debt-bulk-checkpoint-preserves",
          len(payload["segments"]) == len(v.segments))
    tl.close()


# -- accounting --------------------------------------------------------

def test_acct_logval_rows():
    tl, tmp, pin, sdir, pool, v = _checkpointed("acct")
    expect_rows = tl.read_commits_all(
        pin[0], pin[1], pin[2], kind=seg_mod.KIND, min_seq=0)
    pool.release(v)
    counters = ServeCounters()
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                     counters=counters)
    va = pool2.attach(pin)
    got = counters.totals()["log_rows_read"]
    check("s5-acct-logval-rows", got == len(expect_rows),
          f"log_rows_read={got} expect={len(expect_rows)}")
    check("s5-acct-logval-no-ops",
          counters.totals()["log_ops_read"] == 0,
          f"{counters.totals()['log_ops_read']}")
    pool2.release(va)
    tl.close()


def test_acct_cumulative():
    tl, tmp, pin, sdir, pool, v = _checkpointed("cum")
    pool.release(v)
    counters = ServeCounters()
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                     counters=counters)
    va = pool2.attach(pin)
    first = counters.totals()["log_rows_read"]
    pool2.release(va)
    vb = pool2.attach(pin)
    second = counters.totals()["log_rows_read"]
    check("s5-acct-cumulative", first > 0 and second == 2 * first,
          f"first={first} second={second}")
    pool2.release(vb)
    tl.close()


def test_acct_physical_vs_logical():
    tl, tmp, pin, sdir, pool, v = _checkpointed("phys")
    pool.release(v)
    counters = ServeCounters()
    pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                            counters=counters)
    va = pool2.attach(pin)
    before = counters.totals()["bytes_read"]
    va.bm25("alpha beta")
    qv = np.asarray(va.atoms[next(iter(va.atoms))]["descriptor"],
                    dtype=np.float64)
    va.dense_atoms_full(qv)
    after = counters.totals()["bytes_read"]
    check("s5-acct-legs-add-no-file-bytes", after == before,
          f"{before} -> {after}")
    n = va.live_n
    dim = va.dim
    logical = n * (dim * 8 + 8)
    check("s5-acct-logical-derived", logical > 0, f"{logical}")
    pool2.release(va)
    tl.close()


def test_acct_manifest_rows():
    tl, tmp, pin, sdir, pool, v = _checkpointed("manrows", retire=None)
    man = json.load(open(os.path.join(sdir, "manifest.json")))
    n_atoms = sum(s["atoms"] for s in man["segments"])
    n_holons = sum(s["holons"] for s in man["segments"])
    check("s5-acct-manifest-atoms",
          n_atoms == v.live_n + v.retired_atoms,
          f"manifest={n_atoms} live+retired="
          f"{v.live_n + v.retired_atoms}")
    pool.release(v)
    tl.close()


# -- reference-build drift pin -----------------------------------------

def test_drift_read_shape():
    # C1 reference-build read shape (structural, no timing): metas
    # once, live texts twice (C1 skip-then-use), everything else once.
    # Pins C2 == C1 exactly; any future redundant re-read fails here.
    tl, tmp, pin = _small_store("drift", n_docs=16)
    from tlsys.store_if import TLStore
    real_read = TLStore.read_artifact
    real_commits = TLStore.read_commits_all
    real_pubrefs = TLStore.pub_refs
    real_arows = TLStore.artifact_rows
    calls = []
    counts = {"commits": 0, "pubrefs": 0, "arows": 0}

    def spy_read(self, artifact_id, expect_digest=None):
        calls.append(artifact_id)
        return real_read(self, artifact_id, expect_digest)

    def spy_commits(self, *a, **k):
        counts["commits"] += 1
        return real_commits(self, *a, **k)

    def spy_pubrefs(self, *a, **k):
        counts["pubrefs"] += 1
        return real_pubrefs(self, *a, **k)

    def spy_arows(self, *a, **k):
        counts["arows"] += 1
        return real_arows(self, *a, **k)

    TLStore.read_artifact = spy_read
    TLStore.read_commits_all = spy_commits
    TLStore.pub_refs = spy_pubrefs
    TLStore.artifact_rows = spy_arows
    try:
        ref = NarrowIndex(tl, pin, use_reference=True)
    finally:
        TLStore.read_artifact = real_read
        TLStore.read_commits_all = real_commits
        TLStore.pub_refs = real_pubrefs
        TLStore.artifact_rows = real_arows
    from collections import Counter
    mult = Counter(calls)
    live_texts = {e["text_art"] for e in ref.atoms.values()}
    twice = {i for i, c in mult.items() if c == 2}
    once = {i for i, c in mult.items() if c == 1}
    bad = {i for i, c in mult.items() if c not in (1, 2)}
    check("s5-drift-no-triple-reads", not bad, f"{sorted(bad)[:3]}")
    check("s5-drift-texts-twice", twice == live_texts,
          f"twice={len(twice)} live_texts={len(live_texts)}")
    check("s5-drift-batched-scans",
          counts["commits"] == 1 and counts["pubrefs"] == 1
          and counts["arows"] == 1, f"{counts}")
    tl.close()


def main():
    import traceback
    for fn in (test_load_read_once,
               test_load_parallel_matches_serial,
               test_load_parallel_quarantine_deterministic,
               test_load_holon_columnar,
               test_load_legacy_no_holon_files,
               test_load_tampered_holon_npy,
               test_load_bytes_exact,
               test_replay_no_live_retokenize,
               test_replay_differential_synthetic,
               test_replay_ordinal_tamper,
               test_replay_override_range_tamper,
               test_replay_parity_e2e,
               test_debt_advance_bounds,
               test_debt_inmemory,
               test_debt_failure_open,
               test_debt_bulk_pinned_intact,
               test_acct_logval_rows,
               test_acct_cumulative,
               test_acct_physical_vs_logical,
               test_acct_manifest_rows,
               test_drift_read_shape):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=4))
    print("scratch: /tmp/tlsys-s5-*")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
