#!/usr/bin/env python3
"""Prepare the file-backed embedding cache a 10M store build consumes.

`c10m/producer/lane-RELAUNCH/b100m_build_c2.py --mode 10m` needs
`--cache-dir` pointing at a `tl-gpu-embcache-v1` cache holding a vector
for EVERY chunk of the exact `docs-10m.jsonl`, keyed by
(chunk bytes, pinned encoder config), served STRICT (any miss aborts
the build). The historical cache (`/srv/tl/stores/encode-5050/...`) is
machine-local and NOT portable; this wrapper regenerates an equivalent
cache from the exact input with the pinned model:

- chunking: the PRODUCT `tlsys.ingest._supplied_chunks` imported from
  a disposable copy of the frozen producer tree (never reimplemented,
  so chunk bytes are identical to what the builder's ingest looks up);
- encoding: pinned `sentence-transformers/all-MiniLM-L6-v2`
  rev `1110a243...`, `normalize_embeddings=False` (the pinned CPU
  convention `gpu_encode/config.py` records);
- writing: the PRODUCT `gpu_encode.cache.CacheWriter` (stdlib-only
  `meta.json` + `index.jsonl` + `shard_*.f32` layout), with a
  `produced_by` stack record;
- verification: every chunk key is re-located after the write; any
  miss fails closed.

Usage (from the repo root; weights must be cached — see
`fetch_weights.py` — and the exact input extracted — see
`c10m/data/DATA-README.md` §2):

    python benchmarks/evidence/live/prepare_emb_cache.py \\
        --docs /tmp/c10m-inputs/docs-10m.jsonl \\
        --cache-dir /tmp/c2-emb-cache

`--max-docs N` prepares a PARTIAL cache for wrapper validation only
(it cannot serve a build; the script says so). A full 10M-chunk cache
is a long CPU encode; the wrapper resumes (CacheWriter replays
`index.jsonl`) and refuses to mix stacks in one cache dir.
"""

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
C10M = REPO / "c10m"

PIN_DOCS_10M = "04bbbb3ea3425a49491559173b20280fb286edeeef49c8293aebc0b92bcce3fd"
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
DIM = 384


def fail(msg):
    print(f"EMB-CACHE FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stream_docs(path, max_docs=None):
    n = 0
    with open(path, "rb") as f:
        for raw in f:
            raw = raw.rstrip(b"\n")
            if not raw.strip():
                continue
            row = json.loads(raw.decode("utf-8"))
            yield row["doc_id"], row["text"]
            n += 1
            if max_docs is not None and n >= max_docs:
                return


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--docs", required=True,
                    help="exact docs-10m.jsonl (hash-gated to the 10M pin "
                         "unless --no-pin-check)")
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--max-docs", type=int, default=None,
                    help="PARTIAL validation mode: encode only the first N "
                         "docs (cannot serve a build)")
    ap.add_argument("--no-pin-check", action="store_true",
                    help="allow a non-10M docs file (tiny-fixture wrapper "
                         "validation only)")
    args = ap.parse_args(argv)

    docs = Path(args.docs)
    if not docs.is_file():
        fail(f"--docs not found: {docs}")
    if args.no_pin_check:
        print("note: --no-pin-check: docs are NOT the pinned 10M input; "
              "this cache can only validate wrapper mechanics, never a build")
    else:
        got = sha256_file(docs)
        if got != PIN_DOCS_10M:
            fail(f"docs hash {got} != 10M pin {PIN_DOCS_10M} (extract the "
                 f"exact input per c10m/data/DATA-README.md §2)")

    # Disposable chunker/codec root: frozen producer bytes, read-only use.
    for need in ("producer/tl-sys", "producer/tl-eval",
                 "producer/tl-candidate-batch"):
        if not (C10M / need).is_dir():
            fail(f"c10m/{need} missing (run from the repo root)")
    root = Path(tempfile.mkdtemp(prefix="c10m_emb_prep_"))
    try:
        shutil.copytree(C10M / "producer" / "tl-sys", root / "tl-sys")
        shutil.copytree(C10M / "producer" / "tl-eval", root / "tl-eval")
        shutil.copytree(C10M / "producer" / "tl-candidate-batch",
                        root / "tl-candidate-batch")
        sys.path.insert(0, str(root / "tl-sys"))
        sys.path.insert(0, str(root / "tl-eval"))
        sys.path.insert(0, str(root / "tl-candidate-batch" / "candidate"))
        from tlsys.ingest import _supplied_chunks  # product chunker
        from gpu_encode import cache as emb_cache
        from gpu_encode import config as emb_cfg

        try:
            from sentence_transformers import SentenceTransformer
            import torch
            import sentence_transformers as st_pkg
        except ImportError as exc:
            fail(f"missing encoder dependency ({exc}); install the bench "
                 f"stack per ../pins/PINS.md")

        model = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION)
        dim = model.get_sentence_embedding_dimension()
        if dim != DIM:
            fail(f"encoder dim {dim} != cache dim {DIM}")
        produced_by = {"model": MODEL_ID, "revision": MODEL_REVISION,
                       "torch": torch.__version__,
                       "sentence_transformers": st_pkg.__version__,
                       "device": "cpu",
                       "normalize_embeddings": False}
        writer = emb_cache.CacheWriter(args.cache_dir, DIM,
                                       produced_by=produced_by)
        print(f"cache: {args.cache_dir} "
              f"config_id={emb_cfg.config_id()} rows_resumed={writer.row_count}")

        # Collect chunk texts (dedup: CacheWriter keeps first row per key).
        pending, n_docs, n_chunks = [], 0, 0
        for _doc_id, text in stream_docs(docs, args.max_docs):
            n_docs += 1
            for _c0, _c1, ctext, _b0, _b1 in _supplied_chunks(text):
                pending.append(ctext)
                n_chunks += 1
                if len(pending) >= args.batch_size:
                    vecs = model.encode(
                        pending, normalize_embeddings=False,
                        show_progress_bar=False, batch_size=args.batch_size)
                    for t, v in zip(pending, vecs):
                        writer.put(t.encode("utf-8"), [float(x) for x in v])
                    pending = []
        if pending:
            vecs = model.encode(pending, normalize_embeddings=False,
                                show_progress_bar=False,
                                batch_size=args.batch_size)
            for t, v in zip(pending, vecs):
                writer.put(t.encode("utf-8"), [float(x) for x in v])
        print(f"encoded: docs={n_docs} chunks={n_chunks} "
              f"rows={writer.row_count}")

        # Coverage verification: every chunk key must locate.
        missing = 0
        checked = 0
        for _doc_id, text in stream_docs(docs, args.max_docs):
            for _c0, _c1, ctext, _b0, _b1 in _supplied_chunks(text):
                key = emb_cfg.cache_key(ctext.encode("utf-8"))
                checked += 1
                if key not in writer:
                    missing += 1
        if missing:
            fail(f"coverage: {missing}/{checked} chunk keys missing from "
                 f"{args.cache_dir} (refusing: strict builds abort on miss)")
        print(f"coverage: {checked}/{checked} chunk keys locate "
              f"(config_id={emb_cfg.config_id()})")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if args.max_docs is not None or args.no_pin_check:
        print(f"EMB-CACHE PARTIAL (validation only): {args.cache_dir} — "
              f"NOT build-serving")
        return 0
    print(f"EMB-CACHE READY: {args.cache_dir} rows={writer.row_count} "
          f"config_id={emb_cfg.config_id()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
