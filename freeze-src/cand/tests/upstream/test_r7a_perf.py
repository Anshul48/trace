"""Track R7-A: persistence + read-path perf equivalence checks.

Authority: R6-A DIAGNOSIS (tl-eval/evidence/round6-2026-10-05/trackA) +
R6-B proposal C (trackB/REPRO-REPAIR.md section 4). Pinned env:
HF_HOME=<repo>/local-data/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0
(this file needs no encoder: fake embeddings only).

Every perf change here is output-identical by contract; each check
compares the new path against the old semantics (loop oracle, direct
SQL, or exact-limit reads). Narrow frozen defaults (release/
MANIFEST.json, 27 keys) must still match live values.

Run: tl-sys/.venv/bin/python tl-sys/tests/test_r7a_perf.py
"""
import inspect
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import (SQL_IN_CHUNK, TLStore,  # noqa: E402
                            TruncationError)
import tlsys.ingest as _ingmod  # noqa: E402
from tlsys.ingest import _journal_replay, ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 8


def _vec(seed):
    return [float((seed >> (4 * d)) & 1) for d in range(DIM)]


def emb(texts):
    out = []
    for t in texts:
        if t.startswith("ZERO-VEC "):
            out.append([0.0] * DIM)
        else:
            out.append(_vec(abs(hash(t)) % 256))
    return out


def emb1(q):
    return emb([q])[0]


def committed_metas_loop(tl):
    """Full committed meta scan, OLD shape: single-IN pub_refs +
    per-artifact artifact_row loop (the R6-A 57% term). Oracle for
    the batched scan."""
    birth, epoch, mx, _t = tl.pin()
    rows = tl.read_commits(birth, epoch, mx, kind="ACCEPT_ATOMS")
    refs = tl.pub_refs([r[0] for r in rows])
    metas = []
    for seq in [r[0] for r in rows]:
        for art_id in refs.get(seq, []):
            arow = tl.artifact_row(art_id)
            if arow is None:
                continue
            try:
                meta = json.loads(tl.read_artifact(
                    art_id, expect_digest=arow[4]).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(meta, dict):
                metas.append((seq, art_id, json.dumps(meta,
                                                     sort_keys=True)))
    return metas


def committed_metas_batch(tl):
    """Same scan, NEW shape: paginated commits + batched rows."""
    birth, epoch, mx, _t = tl.pin()
    rows = tl.read_commits_all(birth, epoch, mx, kind="ACCEPT_ATOMS")
    seqs = [r[0] for r in rows]
    refs = tl.pub_refs(seqs)
    arows = tl.artifact_rows(
        [a for seq in seqs for a in refs.get(seq, [])])
    metas = []
    for seq in seqs:
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            try:
                meta = json.loads(tl.read_artifact(
                    art_id, expect_digest=arow[4]).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(meta, dict):
                metas.append((seq, art_id, json.dumps(meta,
                                                     sort_keys=True)))
    return metas


def direct_pub_refs(store, seqs):
    """Ground truth: one single-IN query on a raw connection (small
    scale only, under the var limit)."""
    con = sqlite3.connect(store.db_path)
    try:
        q = ("SELECT seq,artifact_id FROM pub_refs WHERE seq IN (%s)"
             "ORDER BY seq,artifact_id" % ",".join("?" * len(seqs)))
        rows = con.execute(q, list(seqs)).fetchall()
    finally:
        con.close()
    out = {}
    for s, a in rows:
        out.setdefault(s, []).append(a)
    return out


def main():
    tmp = tempfile.mkdtemp(prefix="tlsys-r7a-")

    # -- store A: >500 artifacts (chunking regime), ties + zero vec --
    sp = os.path.join(tmp, "store-a")
    tl = TLStore(sp, create=True, lease_owner="test-r7a-a")
    docs = [(f"a{i}", f"alpha doc number {i} beta gamma") for i in range(200)]
    docs.append(("tie1", "identical tie text here"))
    docs.append(("tie2", "identical tie text here"))
    docs.append(("zero1", "ZERO-VEC marker text"))
    ingest_docs(tl, docs, emb, store_id="r7a", place_xdoc=False)
    birth, epoch, mx, _t = tl.pin()
    n_commits = len(tl.read_commits_all(birth, epoch, mx))
    check("shape-n-commits", n_commits == 203 * 2, f"{n_commits}")
    seqs = [r[0] for r in tl.read_commits_all(birth, epoch, mx)]

    # -- (1a) artifact_rows == artifact_row loop ----------------------
    refs = tl.pub_refs(seqs)
    art_ids = [a for seq in seqs for a in refs.get(seq, [])]
    check("shape-n-artifacts", len(art_ids) > SQL_IN_CHUNK,
          f"{len(art_ids)}")
    loop_rows = [tl.artifact_row(a) for a in art_ids]
    t_batch = tl.artifact_rows(art_ids)
    check("batch-rows-identical",
          [tuple(t_batch[a]) for a in art_ids]
          == [tuple(r) for r in loop_rows],
          "every batched row must equal its single-row read")
    check("batch-rows-empty", tl.artifact_rows([]) == {})
    check("batch-rows-missing",
          tl.artifact_rows(["no-such-artifact"]) == {}
          and tl.artifact_row("no-such-artifact") is None)
    dup = tl.artifact_rows([art_ids[0], art_ids[0], art_ids[1]])
    check("batch-rows-dedup",
          len(dup) == 2 and tuple(dup[art_ids[0]])
          == tuple(tl.artifact_row(art_ids[0])), f"{len(dup)}")
    # Single-connection proof: batch N ids with N > chunk size while
    # counting open_db (expect 1 for the batch vs N singles).
    n_open = [0]
    real_open = tl.store.open_db

    def counting_open(_n=n_open, _real=real_open):
        _n[0] += 1
        return _real()

    tl.store.open_db = counting_open
    try:
        tl.artifact_rows(art_ids[:SQL_IN_CHUNK + 10])
        batch_opens = n_open[0]
        n_open[0] = 0
        for a in art_ids[:20]:
            tl.artifact_row(a)
        loop_opens = n_open[0]
    finally:
        tl.store.open_db = real_open
    check("batch-single-connection",
          batch_opens == 1 and loop_opens == 20,
          f"batch={batch_opens} loop20={loop_opens}")

    # -- (1b) full-scan loop vs batch identical -----------------------
    check("fullscan-loop-eq-batch",
          committed_metas_loop(tl) == committed_metas_batch(tl))

    # -- (2a) pub_refs chunked == single-IN ground truth --------------
    check("pubrefs-eq-direct",
          tl.pub_refs(seqs) == direct_pub_refs(tl.store, seqs))
    check("pubrefs-empty", tl.pub_refs([]) == {})
    rev = tl.pub_refs(list(reversed(seqs)))
    check("pubrefs-order-independent", rev == direct_pub_refs(
        tl.store, seqs), "union must equal ORDER BY regardless of "
        "input order")
    long_seqs = list(range(1, mx + 1)) + list(
        range(1000000, 1000000 + 600))
    check("pubrefs-multichunk-eq",
          tl.pub_refs(long_seqs) == direct_pub_refs(
              tl.store, list(range(1, mx + 1))),
          "1200-seq input (3 chunks incl. misses)")

    # -- (2b) fail-loud + pagination ----------------------------------
    try:
        tl.read_commits(birth, epoch, mx, limit=5)
        check("readcommits-fail-loud", False, "silent truncation")
    except TruncationError:
        check("readcommits-fail-loud", True)
    full = tl.read_commits_all(birth, epoch, mx)
    check("readcommits-exact-limit-ok",
          [tuple(r) for r in tl.read_commits(
              birth, epoch, mx, limit=len(full))]
          == [tuple(r) for r in full],
          "limit == n must read clean (LIMIT+1 probe)")
    for pg in (1, 2, 7, 50000):
        got = tl.read_commits_all(birth, epoch, mx, page=pg)
        if [tuple(r) for r in got] != [tuple(r) for r in full]:
            check(f"readcommits-paged-{pg}", False, "mismatch")
            break
    else:
        check("readcommits-paged-all", True)
    kf = tl.read_commits_all(birth, epoch, mx, kind="ACCEPT_ATOMS")
    check("readcommits-kind-filter",
          len(kf) == len(full) and all(r[2] == "ACCEPT_ATOMS" for r in kf))
    win = tl.read_commits_all(birth, epoch, mx, min_seq=seqs[9])
    check("readcommits-minseq-window",
          [r[0] for r in win] == seqs[10:],
          "exclusive lower bound preserved")
    try:
        tl.read_commits(birth, epoch, mx, kind="ACCEPT_ATOMS",
                        limit=len(full) - 1)
        check("readcommits-kind-truncation", False, "silent")
    except TruncationError:
        check("readcommits-kind-truncation", True)

    # -- resume path exercises the paginated scan ---------------------
    idx = NarrowIndex(tl, tl.pin())

    # -- (3) vectorized dense legs == loop oracles --------------------
    nq = NarrowQuery(tl, idx, emb1)
    qvecs = [emb1("alpha beta"), emb1("zzzqqq no match here"),
             emb1("identical tie text here"), [0.0] * DIM,
             [1.0] * DIM, emb1("doc number 199 gamma")]
    for qi, qv in enumerate(qvecs):
        oh = idx.dense_holons(qv)
        vh = nq._dense_holons_vec(qv)
        oa = idx.dense_atoms(qv)
        va = nq._dense_atoms_vec(qv)
        same_h = [d for d, _s in oh] == [d for d, _s in vh]
        same_a = [a for a, _s in oa] == [a for a, _s in va]
        close_h = all(abs(s1 - s2) < 1e-9 for (_d1, s1), (_d2, s2)
                      in zip(oh, vh))
        close_a = all(abs(s1 - s2) < 1e-9 for (_d1, s1), (_d2, s2)
                      in zip(oa, va))
        if not (same_h and same_a and close_h and close_a):
            check(f"dense-vec-order-{qi}", False,
                  f"h:{same_h}/{close_h} a:{same_a}/{close_a}")
            break
    else:
        check("dense-vec-order-all", True)
    # Tie discipline: identical descriptors keep insertion order in
    # both implementations.
    tie_ids = [a for a, _s in idx.dense_atoms(
        emb1("identical tie text here"))[:5]]
    check("dense-vec-ties",
          tie_ids == [a for a, _s in nq._dense_atoms_vec(
              emb1("identical tie text here"))[:5]], f"{tie_ids}")
    th = nq._dense_holons_vec(qvecs[0], topk=10)
    ta = nq._dense_atoms_vec(qvecs[0], topk=10)
    check("dense-vec-topk",
          [d for d, _s in th]
          == [d for d, _s in idx.dense_holons(qvecs[0])[:10]]
          and [a for a, _s in ta]
          == [a for a, _s in idx.dense_atoms(qvecs[0])[:10]]
          and nq._dense_holons_vec(qvecs[0], topk=100000)
          == nq._dense_holons_vec(qvecs[0]),
          "topk head == full head; oversize topk == full")
    # Empty population.
    from tlsys.query import _dense_rank  # noqa: E402
    import numpy as _np  # noqa: E402
    check("dense-vec-empty",
          _dense_rank([1.0] * DIM, [], _np.empty((0, 0)),
                      _np.empty((0,))) == [])
    # Cache validation: second index at a new pin rebuilds.
    nq2 = NarrowQuery(tl, idx, emb1)
    _ = nq2._dense_holons_vec(qvecs[0])
    c0 = dict(nq2._dense_cache["holons"])
    ingest_docs(tl, [("a-new", "brand new doc here")], emb,
                store_id="r7a", place_xdoc=False)
    idx_new = NarrowIndex(tl, tl.pin())
    nq2.idx = idx_new
    _ = nq2._dense_holons_vec(qvecs[0])
    c1 = nq2._dense_cache["holons"]
    check("dense-cache-rebuilds",
          c1["triple"] == idx_new.triple and c1["n"] == c0["n"] + 1,
          f"{c0['n']} -> {c1['n']}")

    # -- (3b) Narrow end-to-end: vec path == loop path ----------------
    idx = NarrowIndex(tl, tl.pin())
    nq_vec = NarrowQuery(tl, idx, emb1)
    nq_loop = NarrowQuery(tl, idx, emb1)
    nq_loop._dense_holons_vec = lambda qv, topk=None: (
        idx.dense_holons(qv)[:topk])
    nq_loop._dense_atoms_vec = lambda qv, topk=None: (
        idx.dense_atoms(qv)[:topk])
    queries = ["alpha doc", "zzzqqq no match here",
               "identical tie text", "doc number 5",
               "ZERO-VEC marker text", "beta gamma alpha"]
    for q in queries:
        d_v, r_v = nq_vec.run(q)
        d_l, r_l = nq_loop.run(q)
        r_v = json.loads(json.dumps(r_v))
        r_l = json.loads(json.dumps(r_l))
        r_v["metrics"].pop("T_ms", None)
        r_l["metrics"].pop("T_ms", None)
        if json.dumps((d_v, r_v), sort_keys=True) != json.dumps(
                (d_l, r_l), sort_keys=True):
            check(f"narrow-vec-eq-loop:{q}", False, "dossier/receipt "
                  "differs (T_ms excluded)")
            break
    else:
        check("narrow-vec-eq-loop-all", True)
    tl.close()

    # -- mini resume via the paginated _committed_doc_state -----------
    sp = os.path.join(tmp, "store-resume")
    tlr = TLStore(sp, create=True, lease_owner="test-r7a-resume")
    t12 = " ".join(f"w{i}" for i in range(1800))
    real_cb = tlr.commit_batch
    calls = [0]

    def crash_once(ops, _real=real_cb, _calls=calls):
        _calls[0] += 1
        if _calls[0] == 2:
            raise RuntimeError("SIMCRASH-r7a")
        return _real(ops)

    tlr.commit_batch = crash_once
    try:
        ingest_docs(tlr, [("rA", t12)], emb, store_id="r7a",
                    place_xdoc=False)
    except RuntimeError:
        pass
    tlr.commit_batch = real_cb
    rep = ingest_docs(tlr, [("rA", t12)], emb, store_id="r7a",
                      place_xdoc=False)
    check("resume-paginated", rep["skipped"] == []
          and rep["n_atoms"] == 2 and rep["n_holons"] == 1, f"{rep}")
    tlr.close()

    # -- (4a) journal replay strictness --------------------------------
    man = {}
    jp = os.path.join(tmp, "j-strict.jsonl")
    with open(jp, "w") as f:
        f.write('{"seq": 1, "event": "flushed", "ops": [], '
                '"statuses": {}}\n')
        f.write('[1, 2]\n')
    try:
        _journal_replay(dict(man), jp)
        check("journal-nondict-refused", False, "no refusal")
    except RuntimeError:
        check("journal-nondict-refused", True)
    jp = os.path.join(tmp, "j-badseq.jsonl")
    with open(jp, "w") as f:
        f.write('{"seq": "x", "event": "flushed", "ops": [], '
                '"statuses": {}}\n')
    try:
        _journal_replay(dict(man), jp)
        check("journal-badseq-refused", False, "no refusal")
    except RuntimeError:
        check("journal-badseq-refused", True)
    jp = os.path.join(tmp, "j-reorder.jsonl")
    with open(jp, "w") as f:
        f.write('{"seq": 2, "event": "flushed", "ops": [], '
                '"statuses": {}}\n')
        f.write('{"seq": 1, "event": "flushed", "ops": [], '
                '"statuses": {}}\n')
    try:
        _journal_replay(dict(man), jp)
        check("journal-reorder-refused", False, "no refusal")
    except RuntimeError:
        check("journal-reorder-refused", True)
    jp = os.path.join(tmp, "j-torn.jsonl")
    with open(jp, "w") as f:
        f.write('{"seq": 1, "event": "flushed", "ops": [], '
                '"statuses": {}}\n')
        f.write('{"seq": 2, "event": "flus')
    m2 = {}
    try:
        mx = _journal_replay(m2, jp)
        check("journal-torn-tail-tolerated", mx == 1, f"{mx}")
    except RuntimeError as e:
        check("journal-torn-tail-tolerated", False, f"{e}")

    # -- (4b) dir-fsync on journal create only; adoption OFF -----------
    sig = inspect.signature(ingest_docs)
    check("journal-off-by-default",
          sig.parameters["progress_journal"].default is False)
    fsync_dirs = []
    real_fdir = _ingmod._fsync_dir

    def counting_fdir(p, _real=real_fdir, _out=fsync_dirs):
        _out.append(p)
        return _real(p)

    _ingmod._fsync_dir = counting_fdir
    try:
        sp = os.path.join(tmp, "store-jc")
        tlj = TLStore(sp, create=True, lease_owner="test-r7a-jc")
        ingest_docs(tlj, [("jc1", "hello world")], emb, store_id="r7a",
                    place_xdoc=False, progress_journal=True)
        tlj.close()
        jc_calls = list(fsync_dirs)
        del fsync_dirs[:]
        sp = os.path.join(tmp, "store-jc-leg")
        tll = TLStore(sp, create=True, lease_owner="test-r7a-jc-leg")
        ingest_docs(tll, [("jc1", "hello world")], emb, store_id="r7a",
                    place_xdoc=False)
        tll.close()
        leg_calls = list(fsync_dirs)
    finally:
        _ingmod._fsync_dir = real_fdir
    check("journal-dir-fsync-on-create", len(jc_calls) == 1
          and jc_calls[0] == os.path.join(tmp, "store-jc"),
          f"{jc_calls}")
    check("legacy-no-dir-fsync", leg_calls == [], f"{leg_calls}")

    # -- narrow frozen defaults: 27/27 vs release/MANIFEST.json --------
    repo = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    with open(os.path.join(repo, "release", "MANIFEST.json")) as f:
        frozen = json.load(f)["defaults"]
    import tlsys.query as _q  # noqa: E402
    import tlsys.place as _p  # noqa: E402
    import tlsys.identity as _idn  # noqa: E402
    import tlsys.export as _exp  # noqa: E402
    import tlsys.fuse as _fuse  # noqa: E402
    live = {}
    for k in frozen:
        if k == "RRF_K":
            live[k] = _q.RRF_K
        elif k == "place_xdoc":
            live[k] = sig.parameters["place_xdoc"].default
        elif k == "PLACE_T":
            live[k] = _p.T_PLACE
        elif k == "PLACE_MEMBER_CAP":
            live[k] = _p.MAX_XHOLON_MEMBERS
        elif k == "ATOM_SCHEME":
            live[k] = _idn.ATOM_SCHEME
        elif k == "EXPORT_SCHEMA":
            live[k] = _exp.EXPORT_SCHEMA
        else:
            live[k] = getattr(_q, k)
    bad = {k: (frozen[k], live[k]) for k in frozen
           if frozen[k] != live[k]}
    check("narrow-defaults-27", not bad and len(frozen) == 27,
          f"{bad}")
    check("fuse-rrf-k", _fuse.RRF_K == 60, f"{_fuse.RRF_K}")

    print("store-root:", tmp)
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
