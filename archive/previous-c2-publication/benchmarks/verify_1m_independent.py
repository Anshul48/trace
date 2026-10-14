#!/usr/bin/env python3
"""Independent checker for H0 provisional 1M manifests (seal-pipeline repair, path 2).

Recomputes selection counts, UTF-8 byte totals, and Merkle roots from staged
bytes with code written separately from the seal producer's path (which reuses
benchmarks/verify_1m_checksums.py). The only shared ground with that path is
byte-hashing primitives: hashlib.sha256 and trace.v2.atomizer.normalize_text
(imported directly here, never via the sibling module). This module imports
neither benchmarks.verify_1m_checksums nor scripts.seal_1m_manifest; a packet
test asserts that statically.

Input: a provisional manifest as emitted by scripts/seal_1m_manifest.py
(artifact h0-provisional-1m-manifest, status PROVISIONAL-UNADOPTED). The
checker re-derives every claim from the embedded selection record and the
hash-verified staged files, and additionally re-hashes the producer script
named in the manifest so a mutated producer cannot ride on an old seal.

Fail-closed: any unresolvable source, SHA drift, count/byte/root mismatch,
producer-identity mismatch, or non-pending co-signature exits nonzero and
prints INDEPENDENT-FAIL causes. A PASS never adopts anything: adoption stays
a separate human ballot (co-signature PENDING).

Usage:
    python3 benchmarks/verify_1m_independent.py \
        --manifest docs/program/inbox/h0-1m-corpus-contract/provisional_1m_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from trace.v2.atomizer import normalize_text  # noqa: E402  (hashing primitive only)

# Doc-id fallback chains, pinned to the staging semantics. Values necessarily
# match the producer path (same staged bytes); the lookup code below is
# written independently.
_FALLBACKS = {
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
_GENERIC_FALLBACKS = ("native_id", "internal_id", "segment_internal_id",
                      "source_document_internal_id", "id", "_id", "source_key")


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _split_range(spec: str) -> tuple[int, int]:
    """Parse '[start, end)' with plain string ops (no shared parser)."""
    text = spec.strip()
    if len(text) < 5 or text[0] != "[" or text[-1] != ")":
        raise ValueError(f"Unparseable selection_range: {spec!r}")
    pieces = text[1:-1].split(",")
    if len(pieces) != 2:
        raise ValueError(f"Unparseable selection_range: {spec!r}")
    try:
        start = int(pieces[0].strip())
        end = int(pieces[1].strip())
    except ValueError:
        raise ValueError(f"Unparseable selection_range: {spec!r}")
    if start < 0 or end < start:
        raise ValueError(f"Inverted selection_range: {spec!r}")
    return start, end


def _pick_id(record: dict, keys: tuple[str, ...], namespace: str, lineno: int) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return "%s:%d" % (namespace, lineno)


def _materialize(dataset: str, record: dict, lineno: int) -> tuple[str, str]:
    """Return (doc_id, normalized full content) with staging-exact semantics."""
    if dataset == "enron_delta":
        ident = record.get("email_id") or record.get("doc_id")
        doc_id = str(ident) if ident is not None else "enron:%d" % lineno
        heading = record.get("subject") or record.get("title") or ""
        body = record.get("body") or record.get("text") or record.get("content") or ""
    elif dataset == "wikipedia_delta":
        doc_id = str(record.get("doc_id"))
        heading = record.get("title") or ""
        body = record.get("text") or ""
    else:
        chain = _FALLBACKS.get(dataset, _GENERIC_FALLBACKS)
        if dataset.endswith("_delta"):
            namespace = dataset[: -len("_delta")]
        else:
            namespace = dataset
        doc_id = _pick_id(record, chain, namespace, lineno)
        heading = record.get("title") or ""
        body = record.get("text") or record.get("content") or ""
    if heading:
        joined = "%s\n\n%s" % (heading, body)
        content = normalize_text(joined.strip())
    else:
        content = normalize_text(body.strip())
    return doc_id, content


class _ShardScanner:
    """Own dedup-scan loop over one shard's line window."""

    def __init__(self) -> None:
        self.known_ids: set[str] = set()
        self.known_digests: set[str] = set()

    def scan(self, dataset: str, path: Path, start: int, end: int) -> tuple[int, int, list[str]]:
        found = 0
        num_bytes = 0
        leaves: list[str] = []
        with open(path, "r", encoding="utf-8") as handle:
            window = itertools.islice(handle, start, end)
            for offset, line in enumerate(window):
                lineno = start + offset
                record = json.loads(line)
                doc_id, content = _materialize(dataset, record, lineno)
                leaf = hashlib.sha256(content.encode("utf-8")).hexdigest()
                if doc_id in self.known_ids or leaf in self.known_digests:
                    continue
                self.known_ids.add(doc_id)
                self.known_digests.add(leaf)
                leaves.append(leaf)
                num_bytes += len(content.encode("utf-8"))
                found += 1
        return found, num_bytes, leaves


def _combine(nodes: list[bytes]) -> bytes:
    if len(nodes) == 1:
        return nodes[0]
    paired: list[bytes] = []
    for pos in range(0, len(nodes), 2):
        left = nodes[pos]
        if pos + 1 < len(nodes):
            right = nodes[pos + 1]
        else:
            right = left
        paired.append(hashlib.sha256(left + right).digest())
    return _combine(paired)


def _root_for(leaves: list[str]) -> str:
    if not leaves:
        return hashlib.sha256(b"").hexdigest()
    ordered = [bytes.fromhex(item) for item in sorted(leaves)]
    return _combine(ordered).hex()


def check_provisional(manifest_path: Path) -> tuple[bool, list[str], dict]:
    failures: list[str] = []
    detail: dict = {"shards": []}

    if not manifest_path.exists():
        return False, ["INDEPENDENT-FAIL manifest-missing: %s" % manifest_path], detail
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            provisional = json.load(handle)
    except Exception as exc:
        return False, ["INDEPENDENT-FAIL manifest-unparseable: %s" % exc], detail

    if provisional.get("artifact") != "h0-provisional-1m-manifest":
        failures.append("INDEPENDENT-FAIL not-a-provisional: artifact=%r"
                        % (provisional.get("artifact"),))
        return False, failures, detail
    if provisional.get("status") != "PROVISIONAL-UNADOPTED":
        failures.append("INDEPENDENT-FAIL not-pending: status=%r"
                        % (provisional.get("status"),))
    co_signature = provisional.get("co_signature", {})
    if co_signature.get("status") != "PENDING_HUMAN_BALLOT":
        failures.append("INDEPENDENT-FAIL co-signature-not-pending: %r"
                        % (co_signature.get("status"),))

    producer = provisional.get("producer", {})
    script_rel = producer.get("script", "")
    script_path = (ROOT_DIR / script_rel).resolve() if script_rel else None
    if script_path is None or not script_path.exists():
        failures.append("INDEPENDENT-FAIL producer-script-missing: %r" % (script_rel,))
    elif producer.get("script_sha256") != _digest_file(script_path):
        failures.append("INDEPENDENT-FAIL producer-identity-mismatch: "
                        "recorded script sha does not match %s" % script_rel)

    selection = provisional.get("selection", [])
    claims = provisional.get("claims", {})
    if not selection or not claims:
        failures.append("INDEPENDENT-FAIL empty-selection-or-claims")
        return False, failures, detail

    local_paths: dict[str, Path] = {}
    for entry in selection:
        raw = entry.get("source_file", "")
        candidate = Path(raw)
        if not candidate.is_absolute() or not candidate.exists():
            failures.append("INDEPENDENT-FAIL source-unresolvable for %s: %s"
                            % (entry.get("dataset_name"), raw))
            continue
        if _digest_file(candidate) != entry.get("source_file_sha256"):
            failures.append("INDEPENDENT-FAIL source-sha-drift for %s (%s)"
                            % (entry.get("dataset_name"), raw))
            continue
        local_paths.setdefault(raw, candidate.resolve())

    if failures:
        return False, failures, detail

    scanner = _ShardScanner()
    base_leaves: list[str] = []
    delta_leaves: list[str] = []
    base_total_bytes = 0
    delta_total_bytes = 0
    ordered = ([e for e in selection if e.get("partition") == "base_100k"]
               + [e for e in selection if e.get("partition") == "delta_900k"])
    for entry in ordered:
        name = entry["dataset_name"]
        try:
            start, end = _split_range(entry["selection_range"])
        except ValueError as exc:
            failures.append("INDEPENDENT-FAIL bad-range for %s: %s" % (name, exc))
            continue
        found, num_bytes, leaves = scanner.scan(name, local_paths[entry["source_file"]],
                                                start, end)
        detail["shards"].append({"dataset_name": name,
                                 "recomputed_docs": found,
                                 "recomputed_bytes": num_bytes})
        if entry.get("partition") == "base_100k":
            base_leaves.extend(leaves)
            base_total_bytes += num_bytes
        else:
            delta_leaves.extend(leaves)
            delta_total_bytes += num_bytes

    if failures:
        return False, failures, detail

    base_docs = sum(r["recomputed_docs"] for r, e in
                    zip(detail["shards"], ordered) if e.get("partition") == "base_100k")
    delta_docs = sum(r["recomputed_docs"] for r, e in
                     zip(detail["shards"], ordered) if e.get("partition") == "delta_900k")

    claimed_shards = {s["dataset_name"]: s for s in claims.get("shards", [])}
    for row in detail["shards"]:
        wanted = claimed_shards.get(row["dataset_name"])
        if wanted is None:
            failures.append("INDEPENDENT-FAIL claim-missing-shard: %s" % row["dataset_name"])
            continue
        if row["recomputed_docs"] != wanted.get("selected_records_d"):
            failures.append("INDEPENDENT-FAIL shard-count-mismatch for %s: claims %s, "
                            "recomputed %d" % (row["dataset_name"],
                                               wanted.get("selected_records_d"),
                                               row["recomputed_docs"]))
        if row["recomputed_bytes"] != wanted.get("selected_text_bytes"):
            failures.append("INDEPENDENT-FAIL shard-bytes-mismatch for %s: claims %s, "
                            "recomputed %d" % (row["dataset_name"],
                                               wanted.get("selected_text_bytes"),
                                               row["recomputed_bytes"]))

    for key, seen in (("target_unique_documents_d", base_docs + delta_docs),
                      ("base_100k_documents_count", base_docs),
                      ("delta_900k_documents_count", delta_docs),
                      ("total_raw_text_bytes", base_total_bytes + delta_total_bytes),
                      ("base_raw_text_bytes", base_total_bytes),
                      ("delta_raw_text_bytes", delta_total_bytes)):
        if claims.get(key) != seen:
            failures.append("INDEPENDENT-FAIL total-mismatch for %s: claims %s, recomputed %s"
                            % (key, claims.get(key), seen))
    if len(scanner.known_ids) != base_docs + delta_docs or \
            len(scanner.known_digests) != base_docs + delta_docs:
        failures.append("INDEPENDENT-FAIL union-not-unique: %d ids / %d digests for %d docs"
                        % (len(scanner.known_ids), len(scanner.known_digests),
                           base_docs + delta_docs))

    base_root = _root_for(base_leaves)
    delta_root = _root_for(delta_leaves)
    union_root = _root_for(base_leaves + delta_leaves)
    detail.update({"recomputed_base_docs": base_docs,
                   "recomputed_delta_docs": delta_docs,
                   "recomputed_total_bytes": base_total_bytes + delta_total_bytes,
                   "recomputed_base_merkle": base_root,
                   "recomputed_delta_merkle": delta_root,
                   "recomputed_union_merkle": union_root})
    for key, seen in (("base_merkle_root_sha256", base_root),
                      ("delta_merkle_root_sha256", delta_root),
                      ("union_merkle_root_sha256", union_root)):
        if claims.get(key) != seen:
            failures.append("INDEPENDENT-FAIL root-mismatch for %s: claims %s, recomputed %s"
                            % (key, claims.get(key), seen))

    return len(failures) == 0, failures, detail


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Independently re-derive every claim of an H0 provisional 1M "
                    "manifest from staged bytes (second code path). Fail-closed: "
                    "any mismatch exits nonzero; a PASS never adopts the manifest."
    )
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Path to the provisional 1M manifest JSON file")
    parser.add_argument("--root", type=Path, default=Path("."),
                        help="Repository root used to resolve the recorded producer path")
    args = parser.parse_args()

    global ROOT_DIR
    ROOT_DIR = args.root.resolve() if args.root.exists() else ROOT_DIR

    manifest_arg: Path = args.manifest
    manifest_path = manifest_arg.resolve() if manifest_arg.exists() else (
        ROOT_DIR / manifest_arg).resolve()
    print("Independently checking provisional manifest: %s" % manifest_path)
    passed, failures, detail = check_provisional(manifest_path)
    if passed:
        print("[INDEPENDENT-PASS] %d base + %d delta = %d docs, %d bytes; "
              "union %s (still UNADOPTED: human ballot required)"
              % (detail["recomputed_base_docs"], detail["recomputed_delta_docs"],
                 detail["recomputed_base_docs"] + detail["recomputed_delta_docs"],
                 detail["recomputed_total_bytes"], detail["recomputed_union_merkle"]))
        return 0
    print("[INDEPENDENT-FAIL] %d error(s):" % len(failures))
    for failure in failures:
        print("  - %s" % failure)
    return 1


if __name__ == "__main__":
    sys.exit(main())
