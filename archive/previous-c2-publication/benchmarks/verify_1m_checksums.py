#!/usr/bin/env python3
"""Verify the frozen Trace 1M corpus capsule against its manifest claims (WP-H0-2).

H0 preflight check for the 1M corpus contract
(docs/program/inbox/1m-02-corpus-capsule/evidence/1m_corpus_manifest.json,
``contract_version`` 2.0.0). This is a SIBLING of the frozen BEIR/MuSiQue
verifier (benchmarks/verify_dataset_checksums.py): it honors the same
fail-closed semantics but enforces a different contract, and it MUST NOT
change the frozen ``manifest_id == beir_musique_frozen_v1`` check.

What it verifies, from staged bytes (no trust in self-reported JSON):
1. Manifest header: contract_version, doc/byte totals, union Merkle claim.
2. Every Windows-absolute ``source_file`` resolves to an existing local path
   whose SHA-256 matches ``source_file_sha256`` (fail closed otherwise).
3. Per-shard doc counts and UTF-8 byte totals recomputed with the exact
   selection semantics of scripts/stage_1m_corpus.py (contiguous
   zero-indexed prefix slicing + strict (doc_id, content_hash) dedup).
4. Base / delta / union Merkle roots recomputed from per-doc content hashes
   with the identical Merkle construction (sorted leaves, duplicate-last).

Usage:
    python3 benchmarks/verify_1m_checksums.py \
        --manifest docs/program/inbox/1m-02-corpus-capsule/evidence/1m_corpus_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from trace.v2.atomizer import normalize_text  # noqa: E402  (content-hash primitive)

EXPECTED_CONTRACT_VERSION = "2.0.0"
EXPECTED_BASE_DOCS = 100_000
EXPECTED_DELTA_DOCS = 900_000
EXPECTED_TOTAL_DOCS = 1_000_000

RANGE_RE = re.compile(r"\[\s*(\d+)\s*,\s*(\d+)\s*\)")

# Exact doc_id fallback chains from scripts/stage_1m_corpus.py, keyed by
# capsule dataset_name. Unknown names use the generic base chain.
ID_FALLBACKS: dict[str, tuple[str, ...]] = {
    "musique": ("native_id", "internal_id", "segment_internal_id",
                "source_document_internal_id", "id", "_id", "source_key"),
    "beir-fiqa": ("native_id", "internal_id", "segment_internal_id",
                  "source_document_internal_id", "id", "_id", "source_key"),
    "beir-scifact": ("native_id", "internal_id", "segment_internal_id",
                     "source_document_internal_id", "id", "_id", "source_key"),
    "beir-nfcorpus": ("native_id", "internal_id", "segment_internal_id",
                      "source_document_internal_id", "id", "_id", "source_key"),
    "multihop-rag": ("native_id", "internal_id", "segment_internal_id",
                     "source_document_internal_id", "id", "_id", "source_key"),
    "musique_delta": ("native_id", "internal_id", "segment_internal_id",
                      "source_document_internal_id"),
    "beir-fiqa_delta": ("native_id", "internal_id", "segment_internal_id",
                        "id", "_id"),
    "bright_delta": ("native_id", "internal_id", "segment_internal_id",
                     "id", "_id"),
}
GENERIC_FALLBACKS = ("native_id", "internal_id", "segment_internal_id",
                     "source_document_internal_id", "id", "_id", "source_key")


def compute_sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_merkle_root(leaf_hashes: list[str]) -> str:
    """Identical construction to scripts/stage_1m_corpus.py."""
    if not leaf_hashes:
        return hashlib.sha256(b"").hexdigest()
    level = [bytes.fromhex(h) for h in sorted(leaf_hashes)]
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            next_level.append(hashlib.sha256(left + right).digest())
        level = next_level
    return level[0].hex()


def parse_range(selection_range: str) -> tuple[int, int]:
    m = RANGE_RE.fullmatch(selection_range.strip())
    if not m:
        raise ValueError(f"Unparseable selection_range: {selection_range!r}")
    return int(m.group(1)), int(m.group(2))


def resolve_doc_id(rec: dict, fallbacks: tuple[str, ...], dataset: str, idx: int) -> str:
    for key in fallbacks:
        val = rec.get(key)
        if val is not None and str(val) != "":
            return str(val)
    return f"{dataset}:{idx}"


def doc_content(dataset: str, rec: dict, idx: int) -> tuple[str, str]:
    """Return (doc_id, normalized full content) with staging-exact semantics."""
    if dataset == "enron_delta":
        doc_id = str(rec.get("email_id") or rec.get("doc_id") or f"enron:{idx}")
        subject = rec.get("subject") or rec.get("title") or ""
        text = rec.get("body") or rec.get("text") or rec.get("content") or ""
        head = subject
    elif dataset == "wikipedia_delta":
        doc_id = str(rec.get("doc_id"))
        head = rec.get("title") or ""
        text = rec.get("text") or ""
    else:
        fallbacks = ID_FALLBACKS.get(dataset, GENERIC_FALLBACKS)
        default_ns = dataset.split("_delta")[0] if dataset.endswith("_delta") else dataset
        doc_id = resolve_doc_id(rec, fallbacks, default_ns, idx)
        head = rec.get("title") or ""
        text = rec.get("text") or rec.get("content") or ""
    full = normalize_text(f"{head}\n\n{text}".strip() if head else text.strip())
    return doc_id, full


def iter_shard_records(
    dataset: str,
    src_path: Path,
    start: int,
    end: int,
    seen_ids: set[str],
    seen_hashes: set[str],
) -> tuple[int, int, list[str]]:
    """Yield-once selection scan with staging-exact semantics.

    Contiguous zero-indexed prefix slice [start, end) over file line index,
    then strict (doc_id, content_hash) dedup against the shared global sets.
    Returns (unique_docs, text_bytes, content_hash_leaves).
    """
    count = nbytes = 0
    leaves: list[str] = []
    with open(src_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx < start:
                continue
            if idx >= end:
                break
            rec = json.loads(line)
            doc_id, full = doc_content(dataset, rec, idx)
            chash = hashlib.sha256(full.encode("utf-8")).hexdigest()
            if doc_id in seen_ids or chash in seen_hashes:
                continue
            seen_ids.add(doc_id)
            seen_hashes.add(chash)
            leaves.append(chash)
            nbytes += len(full.encode("utf-8"))
            count += 1
    return count, nbytes, leaves


def run_selection(
    entries: list[dict],
    resolved: dict[str, Path],
    seen_ids: set[str],
    seen_hashes: set[str],
    range_overrides: dict[str, str] | None = None,
) -> tuple[list[dict], list[str], list[str], int, int]:
    """Scan shards in manifest order.

    Returns (shard_rows, base_leaves, delta_leaves, base_bytes, delta_bytes).

    ``range_overrides`` maps dataset_name -> selection_range and exists ONLY
    for labeled non-certifying forensic analysis (see --forensic-overrides).
    """
    range_overrides = range_overrides or {}
    shard_rows: list[dict] = []
    base_hashes: list[str] = []
    delta_hashes: list[str] = []
    base_bytes = delta_bytes = 0
    base_entries = [e for e in entries if e.get("partition") == "base_100k"]
    delta_entries = [e for e in entries if e.get("partition") == "delta_900k"]
    for partition, part_entries in (("base_100k", base_entries), ("delta_900k", delta_entries)):
        for entry in part_entries:
            name = entry["dataset_name"]
            sel_range = range_overrides.get(name, entry["selection_range"])
            start, end = parse_range(sel_range)
            count, nbytes, leaves = iter_shard_records(
                name, resolved[entry["source_file"]], start, end, seen_ids, seen_hashes
            )
            shard_rows.append({
                "dataset_name": name,
                "partition": partition,
                "selection_range_used": sel_range,
                "recomputed_docs": count,
                "recomputed_bytes": nbytes,
            })
            if partition == "base_100k":
                base_hashes.extend(leaves)
                base_bytes += nbytes
            else:
                delta_hashes.extend(leaves)
                delta_bytes += nbytes
    return shard_rows, base_hashes, delta_hashes, base_bytes, delta_bytes


def verify_manifest(manifest_path: Path) -> tuple[bool, list[str], dict]:
    errors: list[str] = []
    summary: dict = {"shards": [], "path_map": {}}

    if not manifest_path.exists():
        return False, [f"Manifest file does not exist: {manifest_path}"], summary
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        return False, [f"Failed to parse manifest JSON: {e}"], summary

    # 1. Header contract checks
    if manifest.get("contract_version") != EXPECTED_CONTRACT_VERSION:
        errors.append(
            f"contract_version mismatch: expected {EXPECTED_CONTRACT_VERSION}, "
            f"got {manifest.get('contract_version')}"
        )
    for key, expected in (
        ("target_unique_documents_d", EXPECTED_TOTAL_DOCS),
        ("base_100k_documents_count", EXPECTED_BASE_DOCS),
        ("delta_900k_documents_count", EXPECTED_DELTA_DOCS),
        ("base_intersect_delta_count", 0),
    ):
        if manifest.get(key) != expected:
            errors.append(f"Header {key} mismatch: expected {expected}, got {manifest.get(key)}")
    if manifest.get("synthetic_data_used") is not False:
        errors.append("synthetic_data_used must be false for the 1M contract")
    if manifest.get("in_memory_fallback_used") is not False:
        errors.append("in_memory_fallback_used must be false for the 1M contract")

    base_entries = manifest.get("datasets_base", [])
    delta_entries = manifest.get("datasets_delta", [])
    if not base_entries or not delta_entries:
        errors.append("Manifest must carry non-empty datasets_base and datasets_delta")
        return False, errors, summary

    # 2. Resolve + hash-verify every source_file (fail closed)
    resolved: dict[str, Path] = {}
    for entry in base_entries + delta_entries:
        src = entry.get("source_file", "")
        p = Path(src)
        if not p.is_absolute() or not p.exists():
            errors.append(f"Unresolvable source_file for {entry.get('dataset_name')}: {src}")
            continue
        actual_sha = compute_sha256_file(p)
        if actual_sha != entry.get("source_file_sha256"):
            errors.append(
                f"source_file SHA-256 mismatch for {entry.get('dataset_name')} "
                f"({src}): expected {entry.get('source_file_sha256')}, computed {actual_sha}"
            )
            continue
        resolved.setdefault(src, p.resolve())
        summary["path_map"][src] = str(p.resolve())

    if errors:
        return False, errors, summary

    # 3. Recompute counts / bytes / content hashes with staging-exact semantics
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    shard_rows, base_hashes, delta_hashes, base_bytes, delta_bytes = run_selection(
        base_entries + delta_entries, resolved, seen_ids, seen_hashes
    )
    base_docs = sum(r["recomputed_docs"] for r in shard_rows if r["partition"] == "base_100k")
    delta_docs = sum(r["recomputed_docs"] for r in shard_rows if r["partition"] == "delta_900k")
    summary["shards"] = shard_rows
    claims = {e["dataset_name"]: e for e in base_entries + delta_entries}
    for row in shard_rows:
        entry = claims[row["dataset_name"]]
        if row["recomputed_docs"] != entry.get("selected_records_d"):
            errors.append(
                f"{row['dataset_name']} doc count mismatch: manifest claims "
                f"{entry.get('selected_records_d')}, recomputed {row['recomputed_docs']}"
            )
        if row["recomputed_bytes"] != entry.get("selected_text_bytes"):
            errors.append(
                f"{row['dataset_name']} byte total mismatch: manifest claims "
                f"{entry.get('selected_text_bytes')}, recomputed {row['recomputed_bytes']}"
            )

    # 4. Totals + Merkle roots
    if base_docs != EXPECTED_BASE_DOCS:
        errors.append(
            f"Base doc total mismatch: expected {EXPECTED_BASE_DOCS}, "
            f"recomputed {base_docs}"
        )
    if delta_docs != EXPECTED_DELTA_DOCS:
        errors.append(
            f"Delta doc total mismatch: expected {EXPECTED_DELTA_DOCS}, "
            f"recomputed {delta_docs}"
        )
    if len(seen_ids) != EXPECTED_TOTAL_DOCS or len(seen_hashes) != EXPECTED_TOTAL_DOCS:
        errors.append(
            f"Union uniqueness mismatch: {len(seen_ids)} doc_ids / "
            f"{len(seen_hashes)} content_hashes, expected {EXPECTED_TOTAL_DOCS} each"
        )
    if manifest.get("base_raw_text_bytes") != base_bytes:
        errors.append(
            f"base_raw_text_bytes mismatch: manifest claims {manifest.get('base_raw_text_bytes')}, "
            f"recomputed {base_bytes}"
        )
    if manifest.get("delta_raw_text_bytes") != delta_bytes:
        errors.append(
            f"delta_raw_text_bytes mismatch: manifest "
            f"claims {manifest.get('delta_raw_text_bytes')}, "
            f"recomputed {delta_bytes}"
        )
    if manifest.get("total_raw_text_bytes") != base_bytes + delta_bytes:
        errors.append(
            f"total_raw_text_bytes mismatch: manifest "
            f"claims {manifest.get('total_raw_text_bytes')}, "
            f"recomputed {base_bytes + delta_bytes}"
        )

    base_root = compute_merkle_root(base_hashes)
    delta_root = compute_merkle_root(delta_hashes)
    union_root = compute_merkle_root(base_hashes + delta_hashes)
    summary.update({
        "recomputed_base_docs": base_docs,
        "recomputed_base_bytes": base_bytes,
        "recomputed_delta_docs": delta_docs,
        "recomputed_delta_bytes": delta_bytes,
        "recomputed_total_bytes": base_bytes + delta_bytes,
        "recomputed_base_merkle": base_root,
        "recomputed_delta_merkle": delta_root,
        "recomputed_union_merkle": union_root,
    })
    for key, recomputed in (
        ("base_merkle_root_sha256", base_root),
        ("delta_merkle_root_sha256", delta_root),
        ("union_merkle_root_sha256", union_root),
    ):
        if manifest.get(key) != recomputed:
            errors.append(
                f"{key} mismatch: manifest claims {manifest.get(key)}, "
                f"recomputed {recomputed}"
            )

    return len(errors) == 0, errors, summary


def forensic_selection_analysis(
    manifest_path: Path,
    resolved: dict[str, Path],
    manifest: dict,
    range_overrides: dict[str, str],
) -> dict:
    """Non-certifying analysis: recompute one caller-supplied alternate selection.

    NEVER affects the strict verdict. Exists so a documented historical
    selection hypothesis (e.g. pre-reseal shard ranges recovered from git
    history) can be re-executed against current staged bytes by any second
    party and compared with the manifest's pinned claims, field by field.
    """
    base_entries = manifest.get("datasets_base", [])
    delta_entries = manifest.get("datasets_delta", [])
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    shard_rows, base_hashes, delta_hashes, base_bytes, delta_bytes = run_selection(
        base_entries + delta_entries, resolved, seen_ids, seen_hashes,
        range_overrides=range_overrides,
    )
    base_docs = sum(r["recomputed_docs"] for r in shard_rows if r["partition"] == "base_100k")
    delta_docs = sum(r["recomputed_docs"] for r in shard_rows if r["partition"] == "delta_900k")
    base_root = compute_merkle_root(base_hashes)
    delta_root = compute_merkle_root(delta_hashes)
    union_root = compute_merkle_root(base_hashes + delta_hashes)
    claims = {
        "base_docs": manifest.get("base_100k_documents_count"),
        "delta_docs": manifest.get("delta_900k_documents_count"),
        "union_docs": manifest.get("target_unique_documents_d"),
        "base_bytes": manifest.get("base_raw_text_bytes"),
        "delta_bytes": manifest.get("delta_raw_text_bytes"),
        "total_bytes": manifest.get("total_raw_text_bytes"),
        "base_merkle": manifest.get("base_merkle_root_sha256"),
        "delta_merkle": manifest.get("delta_merkle_root_sha256"),
        "union_merkle": manifest.get("union_merkle_root_sha256"),
    }
    observed = {
        "base_docs": base_docs,
        "delta_docs": delta_docs,
        "union_docs": len(seen_ids),
        "base_bytes": base_bytes,
        "delta_bytes": delta_bytes,
        "total_bytes": base_bytes + delta_bytes,
        "base_merkle": base_root,
        "delta_merkle": delta_root,
        "union_merkle": union_root,
    }
    return {
        "certifying": False,
        "range_overrides": range_overrides,
        "shards": shard_rows,
        "observed": observed,
        "matches_claims": {k: observed[k] == claims[k] for k in claims},
    }


def load_resolved(manifest_path: Path) -> tuple[dict, dict[str, Path], list[str]]:
    """Load manifest JSON and hash-verify every source_file. Fail-closed."""
    errors: list[str] = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    resolved: dict[str, Path] = {}
    for entry in manifest.get("datasets_base", []) + manifest.get("datasets_delta", []):
        src = entry.get("source_file", "")
        p = Path(src)
        if not p.is_absolute() or not p.exists():
            errors.append(f"Unresolvable source_file for {entry.get('dataset_name')}: {src}")
            continue
        actual_sha = compute_sha256_file(p)
        if actual_sha != entry.get("source_file_sha256"):
            errors.append(
                f"source_file SHA-256 mismatch for {entry.get('dataset_name')} ({src})"
            )
            continue
        resolved.setdefault(src, p.resolve())
    return manifest, resolved, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the frozen Trace 1M corpus capsule (contract 2.0.0) "
                    "from staged bytes. Fail-closed: any unresolvable source, "
                    "hash drift, or count/byte/Merkle mismatch exits nonzero."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/program/inbox/1m-02-corpus-capsule/evidence/1m_corpus_manifest.json"),
        help="Path to 1M corpus manifest JSON file",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Root directory of repository worktree (resolves relative --manifest)",
    )
    parser.add_argument(
        "--emit-json",
        type=Path,
        default=None,
        help="Optional path to write the machine-readable recompute summary as JSON",
    )
    parser.add_argument(
        "--forensic-overrides",
        type=str,
        default=None,
        help="Optional JSON object mapping dataset_name to an alternate "
             "selection_range, e.g. '{\"bright_delta\": \"[0, 928750)\"}'. "
             "Runs ONE additional clearly-labeled NON-CERTIFYING analysis pass "
             "for diagnosis; the strict verdict is computed without it and is "
             "never affected by it.",
    )
    args = parser.parse_args()

    root_dir = args.root.resolve()
    manifest_arg: Path = args.manifest
    if manifest_arg.is_absolute():
        manifest_path = manifest_arg.resolve()
    elif manifest_arg.exists():
        manifest_path = manifest_arg.resolve()
    else:
        manifest_path = (root_dir / manifest_arg).resolve()

    print(f"Verifying 1M corpus manifest: {manifest_path}")

    passed, errors, summary = verify_manifest(manifest_path)
    forensic: dict | None = None
    if args.forensic_overrides is not None:
        try:
            overrides = json.loads(args.forensic_overrides)
        except Exception as e:
            print(f"[FAIL] Unparseable --forensic-overrides JSON: {e}")
            return 1
        if not isinstance(overrides, dict):
            print("[FAIL] --forensic-overrides must be a JSON object")
            return 1
        try:
            manifest_doc, resolved, load_errors = load_resolved(manifest_path)
        except Exception as e:
            print(f"[FAIL] Forensic pass cannot load manifest: {e}")
            return 1
        if load_errors:
            print("[FAIL] Forensic pass refused: source resolution failed:")
            for err in load_errors:
                print(f"  - {err}")
            return 1
        forensic = forensic_selection_analysis(manifest_path, resolved, manifest_doc, overrides)
        print("[FORENSIC-NON-CERTIFYING] alternate selection analysis (does not affect verdict):")
        for k, match in forensic["matches_claims"].items():
            print(f"  {k}: {'MATCH' if match else 'DIFFER'}")
    if args.emit_json is not None:
        with open(args.emit_json, "w", encoding="utf-8") as f:
            json.dump(
                {"passed": passed, "errors": errors, "summary": summary,
                 "forensic_non_certifying": forensic},
                f, indent=2,
            )
        print(f"Recompute summary: {args.emit_json}")
    if passed:
        print(
            f"[PASS] 1M corpus contract verified: "
            f"{summary['recomputed_base_docs']} base + {summary['recomputed_delta_docs']} delta = "
            f"{summary['recomputed_base_docs'] + summary['recomputed_delta_docs']} docs, "
            f"{summary['recomputed_total_bytes']} bytes."
        )
        print(f"  base_merkle : {summary['recomputed_base_merkle']}")
        print(f"  delta_merkle: {summary['recomputed_delta_merkle']}")
        print(f"  union_merkle: {summary['recomputed_union_merkle']}")
        return 0
    print(f"[FAIL] {len(errors)} verification errors detected:")
    for err in errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
