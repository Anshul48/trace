"""10M retrieval rung driver (phase 1: ingest + index + 1-query smoke).

Standalone driver in the owned evidence dir; imports (never edits)
run_quality machinery + frozen tlsys. Run_quality.py is UNTOUCHED.

Corpus (exact TOK-10M validated vector, token-identical):
  [scifact file order, 5183 docs][curated paras, 100][wikipedia_delta
  file order lines 0..7797] = 13,081 docs / 10,003,381 TOK-v1.
  Two deliberate doc_id label choices vs the OP manifest (both
  token-identical, verified by corpus_check.py):
  - curated paras use run_quality's `para-N` ids (NOT manifest `cur-NNN`)
    so the S2/S3 gold mapping stays valid against this index.
  - 3 scifact docs ingest .strip()ped per _load_beir (manifest counted
    them un-stripped; whitespace-only, 0 token diff).

Ingest path: identical to run_quality.main() scifact branch --
  same encoder (all-MiniLM-L6-v2), same emb() (batch_size=64),
  TLStore(lease_owner="quality-campaign"),
  ingest_docs(..., store_id="quality-scale10m", place_xdoc=True,
  place_t=None), tl_cfg={}.

Usage (from repo root):
  # phase 1 (ingest + index + smoke):
  HF_HOME=/tmp/tl-bench-env-20260927/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0 \\
    tl-sys/.venv/bin/python tl-eval/evidence/scale10m-2026-10-04/driver_10m.py --phase ingest
  # phase 2 (GATED -- coordinator go only):
  <same env> ... driver_10m.py --phase queries

Bulk output (--out) defaults to /tmp scratch; only small summaries are
written to the owned dir (C:\\ is 97% full).
"""
import argparse
import hashlib
import json
import os
import resource
import sys
import threading
import time

EVDIR = os.path.dirname(os.path.abspath(__file__))
# run_quality is a top-level module in tl-eval/ (= EVDIR/../..)
sys.path.insert(0, os.path.normpath(os.path.join(EVDIR, "..", "..")))
sys.path.insert(0, os.path.normpath(os.path.join(
    EVDIR, "..", "..", "..", "tl-sys")))

import numpy as np  # noqa: E402

from run_quality import (  # noqa: E402
    load_curated, load_scifact, metrics_for,
)
from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys.fuse import rrf_fuse  # noqa: E402

DELTA = ("/mnt/c/Users/anshu/AppData/Local/trace-scale-data/staged_1m"
         "/wikipedia_delta.jsonl")
N_DELTA = 7798  # validated prefix length (corpus_check.py)
CORPUS = "scale10m"

def load_scale10m():
    """[(doc_id, text)] in frozen order. Asserts the validated shape."""
    scifact_docs, queries, qrels = load_scifact()
    curated_docs, _cases = load_curated()
    assert len(scifact_docs) == 5183, len(scifact_docs)
    assert len(curated_docs) == 100, len(curated_docs)
    delta_docs = []
    with open(DELTA, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= N_DELTA:
                break
            r = json.loads(line)
            delta_docs.append((r["doc_id"], (r.get("title", "") + "\n" +
                                             r.get("text", "")).strip()))
    assert len(delta_docs) == N_DELTA, len(delta_docs)
    docs = scifact_docs + curated_docs + delta_docs
    assert len(docs) == 13081, len(docs)
    ids = [d[0] for d in docs]
    assert len(set(ids)) == len(ids), "doc_id collision"
    return docs, queries, qrels


def du_bytes(path):
    tot = 0
    for dp, _dn, fn in os.walk(path):
        for f in fn:
            try:
                tot += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return tot


def vmhwm_kb():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1])
    except OSError:
        return -1
    return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="ingest",
                    choices=["ingest", "queries"])
    ap.add_argument("--store-base",
                    default="/tmp/tl-scale10m-2026-10-04/stores")
    ap.add_argument("--out",
                    default="/tmp/tl-scale10m-2026-10-04/phase-out")
    ap.add_argument("--evdir", default=EVDIR)
    ap.add_argument("--smoke-n", type=int, default=1)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.store_base, exist_ok=True)

    from sentence_transformers import SentenceTransformer
    enc = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    def emb(texts):
        return [list(map(float, v)) for v in
                enc.encode(texts, convert_to_numpy=True,
                           batch_size=64, show_progress_bar=False)]

    def emb1(q):
        return list(map(float, enc.encode(
            q, convert_to_numpy=True, show_progress_bar=False)))

    def make_cached_emb1(texts):
        vecs = emb(texts)
        cache = dict(zip(texts, vecs))

        def cached(q):
            if q not in cache:
                cache[q] = emb([q])[0]
            return cache[q]
        return cached

    docs, queries, qrels = load_scale10m()
    print(f"[scale10m] corpus: {len(docs)} docs "
          f"(scifact 5183 + curated 100 + delta {N_DELTA})", flush=True)

    sroot = os.path.join(args.store_base, CORPUS)
    tl = TLStore(sroot, create=not os.path.isdir(sroot),
                 lease_owner="quality-campaign")

    if args.phase == "ingest":
        # heartbeat monitor (read-only): manifest growth + RSS
        man_path = os.path.join(sroot, "ingest_manifest.json")
        stop = threading.Event()
        prog_f = open(os.path.join(args.out, "progress.jsonl"), "a")

        def beat():
            while not stop.wait(60):
                try:
                    m = json.load(open(man_path)) if os.path.isfile(
                        man_path) else {}
                    n = sum(1 for k in m if not k.startswith("_"))
                except (OSError, ValueError):
                    n = -1
                rec = {"t": round(time.time(), 0),
                       "manifest_docs": n,
                       "vmhwm_kb": vmhwm_kb(),
                       "store_bytes": du_bytes(sroot)}
                prog_f.write(json.dumps(rec) + "\n")
                prog_f.flush()
                print(f"[scale10m] ingest heartbeat: {rec}", flush=True)

        mon = threading.Thread(target=beat, daemon=True)
        mon.start()
        t0 = time.time()
        rep = ingest_docs(tl, docs, emb, store_id=f"quality-{CORPUS}",
                          place_xdoc=True, place_t=None)
        t_ing = time.time() - t0
        stop.set()
        mon.join()
        prog_f.close()
        print(f"[scale10m] ingest done: {rep} ingest_s={t_ing:.1f}",
              flush=True)

        pinned = tl.pin()
        t1 = time.time()
        idx = NarrowIndex(tl, pinned)
        t_idx = time.time() - t1
        store_b = du_bytes(sroot)
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(f"[scale10m] index: atoms={len(idx.atoms)} "
              f"holons={len(idx.holons)} build_s={t_idx:.1f} "
              f"store_MB={store_b / 1e6:.1f} peakRSS_MB={peak_kb / 1e3:.0f}",
              flush=True)

        # tasks: EXACT run_quality scifact branch (lines 370-380)
        tasks = []
        for qid, qtext in queries.items():
            rel = {d: (1 if g >= 1 else 0)
                   for d, (g, _s) in qrels.get(qid, {}).items()
                   if g >= 1}
            splits = {s for _d, (_g, s) in qrels.get(qid, {}).items()}
            sp = "tuning" if "tuning" in splits else (
                "heldout" if splits else "noqrel")
            tasks.append((qid, qtext, rel, "S1", sp))
        tuning = [t for t in tasks if t[4] == "tuning" and t[2]]
        print(f"[scale10m] tuning tasks with rels: {len(tuning)}",
              flush=True)

        # 1-query smoke (phase-1 allowance): all 5 systems, one query
        smoke = tuning[:args.smoke_n]
        cemb1 = make_cached_emb1([t[1] for t in smoke])
        nq = NarrowQuery(tl, idx, cemb1, cfg={})
        nqu = NarrowQuery(tl, idx, cemb1, cfg={})
        smoke_rows = []
        for qid, qtext, rel, sl, sp in smoke:
            for sysname, nqq, unp in (("tl", nq, False),
                                      ("tl-unpruned", nqu, True)):
                t0 = time.time()
                try:
                    if unp:
                        dos, rec = nqq.run(qtext, unpruned_reference=True)
                    else:
                        dos, rec = nqq.run(qtext)
                    err = None
                except Exception as e:  # noqa: BLE001
                    dos, rec, err = {"entries": []}, None, repr(e)
                ms = (time.time() - t0) * 1000.0
                ranked = [e["doc_id"] for e in dos["entries"]]
                m = metrics_for(ranked, rel)
                m.update({"qid": qid, "system": sysname,
                          "ms": round(ms, 2), "err": err,
                          "n_served": len(ranked)})
                smoke_rows.append(m)

            def lex_top100():
                lex = idx.bm25(qtext)
                return [a for a, _s in sorted(
                    lex.items(), key=lambda kv: -kv[1])[:100]]

            def dense_top100():
                qv = cemb1(qtext)
                qn = np.array(qv)
                qn_n = float(np.linalg.norm(qn)) or 1.0
                scored = []
                for aid, a in idx.atoms.items():
                    dv = a["descriptor"]
                    dn = float(np.linalg.norm(dv)) or 1.0
                    scored.append((aid, float(qn @ dv / (qn_n * dn))))
                scored.sort(key=lambda x: -x[1])
                return [a for a, _s in scored[:100]]

            for sysname in ("bm25", "dense", "hybrid"):
                t0 = time.time()
                if sysname == "bm25":
                    arank = lex_top100()[:10]
                elif sysname == "dense":
                    arank = dense_top100()[:10]
                else:
                    h_lex = lex_top100()
                    h_den = dense_top100()
                    hyb = rrf_fuse([{a: r for r, a in enumerate(h_lex)},
                                    {a: r for r, a in enumerate(h_den)}])
                    arank = [a for a, _s in sorted(
                        hyb.items(), key=lambda kv: -kv[1])[:10]]
                ms = (time.time() - t0) * 1000.0
                ranked = [idx.atoms[a]["doc_id"] for a in arank
                          if a in idx.atoms]
                m = metrics_for(ranked, rel)
                m.update({"qid": qid, "system": sysname,
                          "ms": round(ms, 2), "err": None,
                          "n_served": len(ranked)})
                smoke_rows.append(m)
        for r in smoke_rows:
            print(f"[scale10m] smoke: {r}", flush=True)

        phase1 = {
            "corpus": CORPUS, "docs": len(docs),
            "n_scifact": 5183, "n_curated": 100, "n_delta": N_DELTA,
            "tok_v1": 10003381, "ingest": rep,
            "ingest_s": round(t_ing, 1),
            "pinned": pinned[3],
            "index_build_s": round(t_idx, 1),
            "n_atoms": len(idx.atoms), "n_holons": len(idx.holons),
            "store_bytes": store_b,
            "store_MB": round(store_b / 1e6, 1),
            "peak_rss_kb": peak_kb,
            "n_tuning_tasks": len(tuning),
            "smoke_rows": smoke_rows,
            "store_path": sroot,
            "encoder": "sentence-transformers/all-MiniLM-L6-v2",
            "tl_cfg": {}, "place_xdoc": True, "place_t": None,
        }
        json.dump(phase1, open(os.path.join(args.out, "phase1.json"),
                               "w"), indent=1)
        json.dump(phase1, open(os.path.join(args.evdir, "phase1.json"),
                               "w"), indent=1)
        tl.trace.dump(os.path.join(args.out, "trace-scale10m.json"))
        tl.close()
        print(f"[scale10m] PHASE 1 DONE -> {args.out}/phase1.json",
              flush=True)
        return

    # -- phase 2 (GATED): full S1/tuning campaign on the 10M index ------
    rep = ingest_docs(tl, docs, emb, store_id=f"quality-{CORPUS}",
                      place_xdoc=True, place_t=None)
    assert not rep["n_atoms"], rep  # committed store; all skipped
    pinned = tl.pin()
    t1 = time.time()
    idx = NarrowIndex(tl, pinned)
    t_idx = time.time() - t1
    print(f"[scale10m] phase2 index: atoms={len(idx.atoms)} "
          f"build_s={t_idx:.1f} pinned={pinned[3]}", flush=True)

    tasks = []
    for qid, qtext in queries.items():
        rel = {d: (1 if g >= 1 else 0)
               for d, (g, _s) in qrels.get(qid, {}).items()
               if g >= 1}
        splits = {s for _d, (_g, s) in qrels.get(qid, {}).items()}
        sp = "tuning" if "tuning" in splits else (
            "heldout" if splits else "noqrel")
        tasks.append((qid, qtext, rel, "S1", sp))
    tasks = [t for t in tasks if t[4] == "tuning" and t[2]]
    print(f"[scale10m] phase2 tasks: {len(tasks)}", flush=True)
    cemb1 = make_cached_emb1([t[1] for t in tasks])
    nq = NarrowQuery(tl, idx, cemb1, cfg={})
    nqu = NarrowQuery(tl, idx, cemb1, cfg={})
    rows = []
    rows_f = open(os.path.join(args.out, "rows.jsonl"), "a")
    flushed = 0
    t_q0 = time.time()
    for n, (qid, qtext, rel, sl, sp) in enumerate(tasks, 1):
        if n == 1 or n % 25 == 0 or n == len(tasks):
            print(f"[scale10m] query {n}/{len(tasks)} "
                  f"elapsed={time.time() - t_q0:.0f}s", flush=True)
            for r in rows[flushed:]:
                rows_f.write(json.dumps(r) + "\n")
            rows_f.flush()
            flushed = len(rows)
        for sysname, nqq, unp in (("tl", nq, False),
                                  ("tl-unpruned", nqu, True)):
            t0 = time.time()
            try:
                if unp:
                    dos, rec = nqq.run(qtext, unpruned_reference=True)
                else:
                    dos, rec = nqq.run(qtext)
                err = None
            except Exception as e:  # noqa: BLE001
                dos, rec, err = {"entries": []}, None, repr(e)
            ms = (time.time() - t0) * 1000.0
            ranked = [e["doc_id"] for e in dos["entries"]]
            m = metrics_for(ranked, rel)
            rm = rec["metrics"] if rec else {}
            m.update({"corpus": CORPUS, "qid": qid, "slice": sl,
                      "split": sp, "system": sysname,
                      "ms": round(ms, 2), "err": err,
                      "n_served": len(ranked), "ranked": ranked,
                      "top_score": (dos["entries"][0]["emitted_score"]
                                    if dos["entries"] else 0.0)})
            rows.append(m)

        def lex_top100():
            lex = idx.bm25(qtext)
            return [a for a, _s in sorted(
                lex.items(), key=lambda kv: -kv[1])[:100]]

        def dense_top100():
            qv = cemb1(qtext)
            qn = np.array(qv)
            qn_n = float(np.linalg.norm(qn)) or 1.0
            scored = []
            for aid, a in idx.atoms.items():
                dv = a["descriptor"]
                dn = float(np.linalg.norm(dv)) or 1.0
                scored.append((aid, float(qn @ dv / (qn_n * dn))))
            scored.sort(key=lambda x: -x[1])
            return [a for a, _s in scored[:100]]

        for sysname in ("bm25", "dense", "hybrid"):
            t0 = time.time()
            if sysname == "bm25":
                arank = lex_top100()[:10]
            elif sysname == "dense":
                arank = dense_top100()[:10]
            else:
                h_lex = lex_top100()
                h_den = dense_top100()
                hyb = rrf_fuse([{a: r for r, a in enumerate(h_lex)},
                                {a: r for r, a in enumerate(h_den)}])
                arank = [a for a, _s in sorted(
                    hyb.items(), key=lambda kv: -kv[1])[:10]]
            ms = (time.time() - t0) * 1000.0
            ranked = [idx.atoms[a]["doc_id"] for a in arank
                      if a in idx.atoms]
            m = metrics_for(ranked, rel)
            m.update({"corpus": CORPUS, "qid": qid, "slice": sl,
                      "split": sp, "system": sysname,
                      "ms": round(ms, 2), "err": None,
                      "n_served": len(ranked), "ranked": ranked})
            rows.append(m)
    for r in rows[flushed:]:
        rows_f.write(json.dumps(r) + "\n")
    rows_f.close()
    with open(os.path.join(args.out, "rows.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from collections import defaultdict
    agg = defaultdict(list)
    for r in rows:
        agg[(r["slice"], r["split"], r["system"])].append(r)
    tables = {}
    for (sl, sp, sy), rs in sorted(agg.items()):
        n = len(rs)
        tables[f"{sl}/{sp}/{sy}"] = {
            "n": n,
            "ndcg10": round(sum(r["ndcg10"] for r in rs) / n, 4),
            "rec5": round(sum(r["rec5"] for r in rs) / n, 4),
            "rec20": round(sum(r["rec20"] for r in rs) / n, 4),
            "mrr": round(sum(r["mrr"] for r in rs) / n, 4),
            "errs": sum(1 for r in rs if r["err"]),
            "p50_ms": round(sorted(r["ms"] for r in rs)[n // 2], 1),
            "p99_ms": round(sorted(r["ms"] for r in rs)
                            [min(n - 1, int(n * 0.99))], 1)}
    json.dump(tables, open(os.path.join(args.out, "metrics.json"), "w"),
              indent=1)
    json.dump(tables, open(os.path.join(args.evdir, "metrics.json"), "w"),
              indent=1)
    tl.trace.dump(os.path.join(args.out, "trace-scale10m-queries.json"))
    tl.close()
    for k, v in tables.items():
        print(k, v, flush=True)
    print(f"[scale10m] PHASE 2 DONE rows={len(rows)} -> {args.out}",
          flush=True)


if __name__ == "__main__":
    main()
