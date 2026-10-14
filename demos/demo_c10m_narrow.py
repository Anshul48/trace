#!/usr/bin/env python3
"""Primary demo: pinned C2-10M freeze-v2 serving stack on a tiny synthetic corpus.

Exercises the EXACT shipped serving bytes (c10m/serving/ over c10m/producer/):
TLStore -> ingest_docs -> NarrowIndex -> NarrowQuery at adopted budgets
M80-P100-A40. Fully offline, deterministic, exits nonzero on any failed check.

Encoder note: the shipped stack encodes with MiniLM-L6-v2 (weights + torch,
not vendored). This demo substitutes a deterministic SHA-256 token-hash
encoder (384-dim raw counts, same "raw vectors, cosine downstream"
convention). Retrieval BEHAVIOR here (scores, ranking) is a property of the
stand-in encoder on a 6-doc fixture and is NEVER a 10M measurement; what the
demo proves is that the pinned ingest/index/query code paths run end to end.

Requires: Linux/POSIX (pinned store uses fcntl locking), numpy, blake3::

    pip install -e .[c10m]
    python demos/demo_c10m_narrow.py
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
C10M = REPO / "c10m"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "c10m_synth_docs.jsonl"

DIM = 384  # MiniLM-L6-v2 width, mirroring the shipped convention
CFG = {"M_REGIONS": 80, "PRUNE_CAP": 100, "MAX_ENTRIES": 40}

# Demo-harness thresholds (fixture-specific, NOT product claims).
TOPICAL_FLOOR = 0.020   # topical top-1 must clear this
OFFTOPIC_CEILING = 0.015  # off-topic top-1 must stay under this

QUERIES = [
    ("Who designed the wug experiment?", "syn-006"),
    ("What protects logical qubits?", "syn-004"),
    ("completely unrelated zebra query about astrophysics", None),
]


def fail(msg):
    print(f"DEMO FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def check_manifest():
    """Verify every packaged c10m byte against PINS.sha256."""
    pins = C10M / "PINS.sha256"
    if not pins.is_file():
        fail("c10m/PINS.sha256 missing")
    bad, n = [], 0
    for line in pins.read_text().splitlines():
        if not line.strip():
            continue
        want, _, rel = line.partition("  ")
        data = (C10M / rel).read_bytes()
        n += 1
        if hashlib.sha256(data).hexdigest() != want:
            bad.append(rel)
    if bad:
        fail(f"{len(bad)} c10m bytes mismatch: {bad[:3]}")
    return n


def assemble_runtime():
    """Merge producer tree + serving overlay into a temp runtime dir."""
    rt = Path(tempfile.mkdtemp(prefix="c10m_runtime_"))
    shutil.copytree(C10M / "producer" / "tl-sys", rt / "tl-sys")
    shutil.copytree(C10M / "producer" / "tl-candidate-batch",
                    rt / "tl-candidate-batch")
    for src in (C10M / "serving").rglob("*.py"):
        dst = rt / src.relative_to(C10M / "serving")
        shutil.copy2(src, dst)
    return rt


def embed_texts(texts):
    vecs = []
    for text in texts:
        vec = [0.0] * DIM
        for tok in text.lower().split():
            vec[int(hashlib.sha256(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        vecs.append(vec)
    return vecs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", default=None, help="reuse a store dir")
    ap.add_argument("--keep", action="store_true", help="keep temp dirs")
    ap.add_argument("--quiet", action="store_true", help="verdict only")
    ap.add_argument("--out", default=None, help="write results JSON here")
    args = ap.parse_args(argv)
    log = (lambda *a: None) if args.quiet else print

    if os.name != "posix":
        fail("pinned TLStore requires POSIX locking; run on Linux/WSL")
    try:
        import numpy  # noqa: F401
        import blake3  # noqa: F401
    except ImportError as exc:
        fail(f"missing demo dependency ({exc}); pip install -e .[c10m]")

    n = check_manifest()
    log(f"pins: {n} c10m files verified against PINS.sha256")

    rt = assemble_runtime()
    sys.path.insert(0, str(rt / "tl-sys"))
    sys.path.insert(0, str(rt / "tl-candidate-batch" / "candidate"))
    from tlsys.store_if import TLStore
    from tlsys.ingest import ingest_docs
    from tlsys.index import NarrowIndex
    from tlsys.query import NarrowQuery
    import tlsys.query as qmod

    serving_sha = hashlib.sha256(
        Path(qmod.__file__).read_bytes()).hexdigest()
    if serving_sha != "d7756e72e2de65814103e216edfc7d53650cc0fada34cefe7cf41411f03414ce":
        fail(f"runtime query.py is not the pinned serving byte ({serving_sha[:16]}...)")

    docs = [(json.loads(line)["doc_id"], json.loads(line)["text"])
            for line in FIXTURE.read_text().splitlines() if line.strip()]
    log(f"corpus: {len(docs)} synthetic docs from fixtures/c10m_synth_docs.jsonl")

    data_dir = Path(args.data_dir) if args.data_dir else Path(
        tempfile.mkdtemp(prefix="c10m_demo_"))
    data_dir.mkdir(parents=True, exist_ok=True)
    store_path = data_dir / "store"
    fresh = not (store_path.exists() and any(store_path.iterdir()))
    store = TLStore(str(store_path), create=fresh, lease_owner="demo-c10m")
    if fresh:
        rep = ingest_docs(store, docs, embed_texts)
        log(f"ingest: atoms={rep['n_atoms']} holons={rep['n_holons']} "
            f"skipped={rep['skipped']} pin={rep['pinned']}")
        if rep["n_atoms"] != len(docs) or rep["n_holons"] != len(docs):
            fail(f"unexpected ingest counts: {rep}")
        if rep["skipped"]:
            fail(f"unexpected ingest skips: {rep['skipped']}")
    else:
        log(f"reusing store at {store_path}")
    pin = store.pin()
    log(f"store pin: {pin}")

    index = NarrowIndex(store, pin)
    log(f"index triple: {index.triple}")
    query = NarrowQuery(store, index, lambda t: embed_texts([t])[0], cfg=dict(CFG))

    results = []
    for text, want_top in QUERIES:
        dossier, receipt = query.run(text)
        status = receipt["execution"]["status"]
        support = receipt.get("support_findings")
        entries = [(e["doc_id"], round(e["emitted_score"], 4),
                    e["atom_id"], e["span"]) for e in dossier["entries"]]
        log(f"Q: {text}")
        log(f"  status={status} support={support} "
            f"top={entries[0] if entries else None}")
        if status != "complete":
            fail(f"query did not complete: {receipt['execution']}")
        if want_top is not None:
            if not entries or entries[0][0] != want_top:
                fail(f"expected top-1 {want_top}, got {entries[:1]}")
            if entries[0][1] < TOPICAL_FLOOR:
                fail(f"topical score {entries[0][1]} below floor {TOPICAL_FLOOR}")
        else:
            if entries and entries[0][1] >= OFFTOPIC_CEILING:
                fail(f"off-topic top score {entries[0][1]} above ceiling "
                     f"{OFFTOPIC_CEILING}")
            log(f"  off-topic top score below demo ceiling "
                f"({OFFTOPIC_CEILING}); harness-level signal only, not abstention")
        results.append({"query": text, "status": status, "support": support,
                        "entries": [{"doc_id": d, "score": s, "atom_id": a,
                                     "span": sp} for d, s, a, sp in entries]})
    store.close()
    if not args.keep and args.data_dir is None:
        shutil.rmtree(data_dir, ignore_errors=True)
    if not args.keep:
        shutil.rmtree(rt, ignore_errors=True)

    payload = {"pin": pin, "triple": str(index.triple), "cfg": CFG,
               "encoder": "sha256-token-hash-384 (demo stand-in, NOT MiniLM)",
               "results": results}
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2))
        log(f"results: {args.out}")
    print("DEMO PASS: pinned C2-10M serving stack ran offline "
          f"({len(docs)} synth docs, {len(results)} queries, budgets M80-P100-A40).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
