#!/usr/bin/env python3
"""Reconstruct the exact C2-10M freeze-v2 build inputs from pinned upstreams.

Reproduces the two large frozen corpus files byte-exactly, then verifies
every hash:

1. ``docs-100m.jsonl`` (622471790 B, ``c098fdac…``) from the three pinned
   upstream sources, in order, per ``preflight-100m.json``
   ``selection_formula``:
   - scifact: 5183 rows, ``{"doc_id": _id, "text": (title + "\\n" + text).strip()}``
   - curated: 100 rows from ``corpus_text`` ``\\n\\n`` paragraphs
     (non-blank, byte-preserving), ``para-0`` … ``para-99``
   - wikipedia_delta: frozen prefix, first 25644 rows in file order,
     ``{"doc_id": doc_id, "text": (title + "\\n" + text).strip()}``
   Lines are ``json.dumps(..., separators=(",", ":"), ensure_ascii=False)``.
2. ``docs-10m.jsonl`` (64291035 B, ``04bbbb3e…``): 3099 rows selected from
   the parent by 0-based line ordinal from ``derivation.json``
   ``case_grounding.per_doc_geometry`` (in file order), re-serialized with
   default ``json.dumps`` separators and ``ensure_ascii=False``.
3. The three small frozen inputs ship verbatim in ``inputs/`` and are
   re-verified by hash: ``corpus-manifest-10m.json``, ``prefix-doc-ranges.json``,
   ``relations-10m.json``.

Every input is hash-gated BEFORE use; any mismatch (or missing file) fails
closed naming the expected pin. Upstream provenance, licenses, and
attribution: ``DATA-README.md`` (this directory). The exact
``docs-10m.jsonl`` also ships as a deterministic gzip bundle
(``bundle/docs-10m.jsonl.gz``) so reproduction never depends on the
machine-local 1.4 GB delta: ``--from-bundle`` extracts and verifies it.

Usage::

    python c10m/data/reconstruct_inputs.py --out-dir /tmp/c10m-inputs --from-bundle
    python c10m/data/reconstruct_inputs.py --out-dir /tmp/c10m-inputs \\
        --scifact /path/to/corpus.jsonl --delta /path/to/wikipedia_delta.jsonl
    # curated defaults to the vendored copy: c10m/data/upstream/
    python c10m/data/reconstruct_inputs.py --check-only --docs-100m A --docs-10m B
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

PINS = {
    "bundle": "31002b8cdb871989fc40c1970e7485e4dcbd80d0cbd813956dedffa28dda760a",
    "scifact": "cf30fea2468ff6237a0ce515c5e7ea28442319e03fd53721b61b7b6a7f4e896a",
    "curated": "210a20a4d1e7591413ecddc39eeed20b5e487009ddde1f18dfc05bf2e325af84",
    "delta": "ffe485442095c1f8a6bb141dc14deb4ca8ff9b78edecf15a2bda830825eb978d",
    "docs-100m": "c098fdace3a73efc83f3c71a9e024b3cd77114fd0d7f2348c7c813995e6b0e09",
    "docs-10m": "04bbbb3ea3425a49491559173b20280fb286edeeef49c8293aebc0b92bcce3fd",
    "corpus-manifest-10m.json": "e56ac0a940f5e7cc9d8f22a49c9e31c9c4d842835104dc882f2e178155367c1d",
    "prefix-doc-ranges.json": "c255a52ff85a7adaa629b51d9f0b5469fcf4edc756b59358093037fe677db0c6",
    "relations-10m.json": "fef3ec6a200f12fce9cbdc6d90d041281921a25a86418a17fa40c098045ecdb5",
}

N_SCIFACT = 5183
N_CURATED = 100
N_DELTA_PREFIX = 25644
N_100M = 30927
N_10M = 3099
BYTES_100M = 622471790
BYTES_10M = 64291035


def fail(msg: str) -> None:
    print(f"RECONSTRUCT FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gate(path: Path, key: str, what: str) -> None:
    if not path.is_file():
        fail(f"missing {what}: {path} (expected sha256 {PINS[key]}; "
             f"see DATA-README.md for the acquisition recipe)")
    got = sha_file(path)
    if got != PINS[key]:
        fail(f"{what} hash mismatch: got {got[:16]}…, want {PINS[key][:16]}…")


def dump_parent(doc_id: str, text: str) -> str:
    return json.dumps({"doc_id": doc_id, "text": text},
                      separators=(",", ":"), ensure_ascii=False) + "\n"


def dump_slice(doc_id: str, text: str) -> str:
    return json.dumps({"doc_id": doc_id, "text": text}, ensure_ascii=False) + "\n"


def assemble_parent(scifact: Path, curated: Path, delta: Path, out: Path,
                    keep: set[int]) -> dict[int, tuple[str, str]]:
    """Stream-assemble docs-100m; retain rows whose 0-based index is in keep."""
    held: dict[int, tuple[str, str]] = {}
    h = hashlib.sha256()
    n = 0
    with open(out, "w", encoding="utf-8", newline="") as fh:
        def emit(doc_id: str, text: str) -> None:
            nonlocal n
            line = dump_parent(doc_id, text)
            fh.write(line)
            h.update(line.encode("utf-8"))
            if n in keep:
                held[n] = (doc_id, text)
            n += 1

        n_sci = 0
        with open(scifact, encoding="utf-8") as f:
            for raw in f:
                if not raw.strip():
                    continue
                s = json.loads(raw)
                emit(s["_id"], (s["title"] + "\n" + s["text"]).strip())
                n_sci += 1
        if n_sci != N_SCIFACT:
            fail(f"scifact rows {n_sci} != {N_SCIFACT}")

        cur = json.loads(curated.read_text(encoding="utf-8"))
        paras = [p for p in cur["corpus_text"].split("\n\n") if p.strip() != ""]
        if len(paras) != N_CURATED:
            fail(f"curated paragraphs {len(paras)} != {N_CURATED}")
        for i, para in enumerate(paras):
            emit(f"para-{i}", para)

        n_delta = 0
        with open(delta, encoding="utf-8") as f:
            for raw in f:
                if n_delta >= N_DELTA_PREFIX:
                    break
                if not raw.strip():
                    continue
                w = json.loads(raw)
                emit(w["doc_id"], (w["title"] + "\n" + w["text"]).strip())
                n_delta += 1
        if n_delta != N_DELTA_PREFIX:
            fail(f"delta prefix rows {n_delta} != {N_DELTA_PREFIX}")
    if n != N_100M:
        fail(f"assembled rows {n} != {N_100M}")
    if h.hexdigest() != PINS["docs-100m"]:
        fail(f"docs-100m mismatch: got {h.hexdigest()[:16]}…, "
             f"want {PINS['docs-100m'][:16]}…")
    if out.stat().st_size != BYTES_100M:
        fail(f"docs-100m bytes {out.stat().st_size} != {BYTES_100M}")
    return held


def slice_10m(held: dict[int, tuple[str, str]], derivation: Path, out: Path) -> None:
    geo = json.loads(derivation.read_text(encoding="utf-8"))[
        "case_grounding"]["per_doc_geometry"]
    if len(geo) != N_10M:
        fail(f"derivation rows {len(geo)} != {N_10M}")
    h = hashlib.sha256()
    with open(out, "w", encoding="utf-8", newline="") as fh:
        for g in geo:
            ordinal = g["parent_ordinal"]
            if ordinal not in held:
                fail(f"ordinal {ordinal} missing from assembled parent")
            doc_id, text = held[ordinal]
            if doc_id != g["doc_id"]:
                fail(f"ordinal {ordinal}: parent {doc_id} != map {g['doc_id']}")
            line = dump_slice(doc_id, text)
            fh.write(line)
            h.update(line.encode("utf-8"))
    if h.hexdigest() != PINS["docs-10m"]:
        fail(f"docs-10m mismatch: got {h.hexdigest()[:16]}…, "
             f"want {PINS['docs-10m'][:16]}…")
    if out.stat().st_size != BYTES_10M:
        fail(f"docs-10m bytes {out.stat().st_size} != {BYTES_10M}")


def extract_bundle(bundle: Path, out: Path) -> None:
    """Extract the shipped docs-10m bundle via the corrected verifier.

    Delegates to ``bundle/verify_docs_10m.py`` (A50/A52: asset/out alias
    guards + sibling-temp atomic extraction; existing output and asset
    preserved on every failure). The old inline ``gzip`` copy wrote
    ``--out`` before verifying and is removed. The read-only bundle
    hash gate stays first so pin failures name the pin.
    """
    import importlib.util
    gate(bundle, "bundle", "shipped bundle docs-10m.jsonl.gz")
    verifier = bundle.parent / "verify_docs_10m.py"
    if not verifier.is_file():
        verifier = HERE / "bundle" / "verify_docs_10m.py"
    if not verifier.is_file():
        fail(f"missing bundle verifier: {verifier}")
    spec = importlib.util.spec_from_file_location(
        "bundle_verify_docs_10m", verifier)
    if spec is None or spec.loader is None:
        fail(f"cannot load bundle verifier: {verifier}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if mod.verify(str(bundle), str(out)) != 0:
        fail("bundle verify failed (see FAIL line above)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--scifact", default=None)
    ap.add_argument("--curated", default=str(HERE / "upstream"
                                            / "trace_engineering_curated.json"))
    ap.add_argument("--delta", default=None)
    ap.add_argument("--from-bundle", action="store_true",
                    help="extract docs-10m from the shipped deterministic "
                         "bundle instead of the upstream recipe")
    ap.add_argument("--bundle", default=str(HERE / "bundle"
                                            / "docs-10m.jsonl.gz"))
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--docs-100m", default=None)
    ap.add_argument("--docs-10m", default=None)
    args = ap.parse_args(argv)

    inputs = HERE / "inputs"
    for name in ("corpus-manifest-10m.json", "prefix-doc-ranges.json",
                 "relations-10m.json"):
        gate(inputs / name, name, f"shipped input {name}")
    print(f"small inputs: 3/3 hash-verified ({inputs})")

    if args.check_only:
        if not args.docs_100m or not args.docs_10m:
            fail("--check-only needs --docs-100m and --docs-10m")
        gate(Path(args.docs_100m), "docs-100m", "docs-100m.jsonl")
        gate(Path(args.docs_10m), "docs-10m", "docs-10m.jsonl")
        print("RECONSTRUCT PASS (--check-only): both corpus hashes exact.")
        return 0

    if not args.out_dir:
        fail("needs --out-dir")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.from_bundle:
        slice_out = out_dir / "docs-10m.jsonl"
        extract_bundle(Path(args.bundle), slice_out)
        print(f"docs-10m: {N_10M} rows, {BYTES_10M} bytes, "
              f"sha {PINS['docs-10m'][:16]}… exact (from bundle)")
        print("RECONSTRUCT PASS (--from-bundle): exact freeze-v2 "
              f"docs-10m reproduced in {out_dir}.")
        return 0

    if not args.scifact or not args.delta:
        fail("needs --scifact and --delta (curated defaults to "
             "the vendored copy) — or use --from-bundle")

    gate(Path(args.scifact), "scifact", "scifact corpus.jsonl")
    gate(Path(args.curated), "curated", "curated fixture")
    gate(Path(args.delta), "delta", "wikipedia_delta.jsonl")
    print("upstreams: 3/3 hash-verified")

    geo = json.loads((inputs / "derivation.json").read_text(
        encoding="utf-8"))["case_grounding"]["per_doc_geometry"]
    keep = {g["parent_ordinal"] for g in geo}
    parent_out = out_dir / "docs-100m.jsonl"
    held = assemble_parent(Path(args.scifact), Path(args.curated),
                           Path(args.delta), parent_out, keep)
    print(f"docs-100m: {N_100M} rows, {BYTES_100M} bytes, "
          f"sha {PINS['docs-100m'][:16]}… exact")
    slice_out = out_dir / "docs-10m.jsonl"
    slice_10m(held, inputs / "derivation.json", slice_out)
    print(f"docs-10m: {N_10M} rows, {BYTES_10M} bytes, "
          f"sha {PINS['docs-10m'][:16]}… exact")
    print("RECONSTRUCT PASS: exact freeze-v2 build inputs reproduced "
          f"in {out_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
