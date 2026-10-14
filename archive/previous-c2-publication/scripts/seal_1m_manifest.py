#!/usr/bin/env python3
"""Atomic seal producer for H0 provisional 1M manifests (seal-pipeline repair).

Derives EVERY claim from one immutable selection record plus hash-verified
staged bytes, using the attempt-1 recompute mechanics
(benchmarks/verify_1m_checksums.py, imported here as the producer-side code
path). The independent checker (benchmarks/verify_1m_independent.py)
re-derives the same claims through genuinely separate code before anything
may be published.

Publication discipline:
- The output is a PROVISIONAL manifest in the gate directory, never an
  adoption: co-signature stays PENDING_HUMAN_BALLOT and no signature is
  minted here (signing binds the complete provisional file bytes and happens
  only via the separate human ballot recorded in 06_DECISION_LOG.md).
- The frozen capsule manifest is NEVER overwritten; output goes to the gate
  dir under a provisional name only.
- The manifest is written to a sibling tmp path, flushed + fsync'd, then
  atomically renamed. A crash (including kill -9) before the rename leaves
  only the tmp file, which is never treated as publishable output and is
  discarded on the next run.
- Any mismatch (unresolvable source, SHA drift, unparseable/inverted range,
  cross-partition collision, or --expect deviation) refuses publication:
  nonzero exit, no provisional file created, tmp removed best-effort.
- The producer embeds its own SHA-256 and the selection record SHA-256 so
  the checker can re-bind both.

Usage:
    python3 scripts/seal_1m_manifest.py \
        --selection docs/program/inbox/h0-1m-corpus-contract/selection_record.json \
        --gate-dir docs/program/inbox/h0-1m-corpus-contract \
        --expect /tmp/expected_claims.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

_PATH1 = ROOT_DIR / "benchmarks" / "verify_1m_checksums.py"
_spec = importlib.util.spec_from_file_location("h0_path1_recompute", _PATH1)
_path1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_path1)

PRODUCER_REL = "scripts/seal_1m_manifest.py"
TMP_SUFFIX = ".seal-tmp"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def load_selection(path: Path) -> tuple[dict, str]:
    with open(path, "r", encoding="utf-8") as handle:
        record = json.load(handle)
    if not isinstance(record, dict) or not isinstance(record.get("shards"), list):
        raise ValueError("selection record must carry a 'shards' list")
    required = ("dataset_name", "partition", "source_file", "source_file_sha256",
                "selection_range")
    for entry in record["shards"]:
        for key in required:
            if key not in entry:
                raise ValueError("selection shard %r missing %r"
                                 % (entry.get("dataset_name"), key))
        if entry.get("partition") not in ("base_100k", "delta_900k"):
            raise ValueError("selection shard %r has bad partition %r"
                             % (entry.get("dataset_name"), entry.get("partition")))
    return record, sha256_file(path)


def derive_claims(record: dict) -> tuple[dict, dict, list[str]]:
    """Hash-verify sources, recompute counts/bytes/roots. Returns (claims, aux, errors)."""
    errors: list[str] = []
    resolved: dict[str, Path] = {}
    for entry in record["shards"]:
        raw = entry["source_file"]
        candidate = Path(raw)
        if not candidate.is_absolute() or not candidate.exists():
            errors.append("SEAL-REFUSE source-unresolvable for %s: %s"
                          % (entry["dataset_name"], raw))
            continue
        try:
            actual = sha256_file(candidate)
        except OSError as exc:
            errors.append("SEAL-REFUSE source-unreadable for %s: %s"
                          % (entry["dataset_name"], exc))
            continue
        if actual != entry["source_file_sha256"]:
            errors.append("SEAL-REFUSE source-sha-drift for %s (%s)"
                          % (entry["dataset_name"], raw))
            continue
        try:
            _path1.parse_range(entry["selection_range"])
        except ValueError as exc:
            errors.append("SEAL-REFUSE bad-range for %s: %s"
                          % (entry["dataset_name"], exc))
            continue
        resolved.setdefault(raw, candidate.resolve())
    if errors:
        return {}, {}, errors

    pseudo = [{"dataset_name": e["dataset_name"], "partition": e["partition"],
               "source_file": e["source_file"], "selection_range": e["selection_range"]}
              for e in record["shards"]]
    try:
        rows, base_leaves, delta_leaves, base_bytes, delta_bytes = _path1.run_selection(
            pseudo, resolved, set(), set())
    except Exception as exc:
        return {}, {}, ["SEAL-REFUSE recompute-crashed: %s" % exc]

    base_docs = sum(r["recomputed_docs"] for r in rows if r["partition"] == "base_100k")
    delta_docs = sum(r["recomputed_docs"] for r in rows if r["partition"] == "delta_900k")
    total_docs = base_docs + delta_docs
    # Cross-partition uniqueness: leaves are content hashes; base+delta leaf
    # multiset must equal the union with no collision-driven drops.
    if len(set(base_leaves)) + len(set(delta_leaves)) != total_docs or \
            len(set(base_leaves + delta_leaves)) != total_docs:
        errors.append("SEAL-REFUSE cross-partition-collision: %d base + %d delta leaves "
                      "do not form a %d-unique union" % (len(base_leaves),
                                                         len(delta_leaves), total_docs))
        return {}, {}, errors

    base_root = _path1.compute_merkle_root(base_leaves)
    delta_root = _path1.compute_merkle_root(delta_leaves)
    union_root = _path1.compute_merkle_root(base_leaves + delta_leaves)
    shard_claims = [{"dataset_name": r["dataset_name"],
                     "partition": r["partition"],
                     "selection_range": r["selection_range_used"],
                     "selected_records_d": r["recomputed_docs"],
                     "selected_text_bytes": r["recomputed_bytes"]} for r in rows]
    claims = {
        "target_unique_documents_d": total_docs,
        "base_100k_documents_count": base_docs,
        "delta_900k_documents_count": delta_docs,
        "base_intersect_delta_count": 0,
        "total_raw_text_bytes": base_bytes + delta_bytes,
        "base_raw_text_bytes": base_bytes,
        "delta_raw_text_bytes": delta_bytes,
        "base_merkle_root_sha256": base_root,
        "delta_merkle_root_sha256": delta_root,
        "union_merkle_root_sha256": union_root,
        "shards": shard_claims,
    }
    aux = {"rows": rows, "path_map": {k: str(v) for k, v in resolved.items()}}
    return claims, aux, errors


def check_expect(claims: dict, expect_path: Path | None) -> list[str]:
    if expect_path is None:
        return []
    with open(expect_path, "r", encoding="utf-8") as handle:
        expected = json.load(handle)
    mismatches: list[str] = []
    flat = dict(claims)
    flat_shards = {s["dataset_name"]: s for s in claims.get("shards", [])}
    for key, wanted in expected.items():
        if "::" in key:
            shard_name, field = key.split("::", 1)
            seen = flat_shards.get(shard_name, {}).get(field, "<absent>")
        else:
            seen = flat.get(key, "<absent>")
        if seen != wanted:
            mismatches.append("SEAL-REFUSE expect-mismatch for %s: expected %s, derived %s"
                              % (key, wanted, seen))
    return mismatches


def build_provisional(record: dict, selection_sha: str, claims: dict, aux: dict) -> dict:
    return {
        "artifact": "h0-provisional-1m-manifest",
        "status": "PROVISIONAL-UNADOPTED",
        "contract_version": "2.0.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "producer": {
            "script": PRODUCER_REL,
            "script_sha256": sha256_file(ROOT_DIR / PRODUCER_REL),
            "recompute_path": "benchmarks/verify_1m_checksums.py",
            "recompute_sha256": sha256_file(_PATH1),
            "selection_sha256": selection_sha,
        },
        "selection": record["shards"],
        "selection_provenance": record.get("provenance", {}),
        "path_map": aux["path_map"],
        "claims": claims,
        "co_signature": {
            "status": "PENDING_HUMAN_BALLOT",
            "instruction": "Adoption is a separate human ballot recorded in "
                           "06_DECISION_LOG.md; this file confers no scale claim.",
        },
        "signature": None,
        "signing_rule": "A human co-signature binds sha256 of the complete provisional "
                        "file bytes at adoption time; no signature is minted by this script.",
    }


def atomic_publish(gate_dir: Path, output_name: str, document: dict,
                   stall_seconds: float) -> Path:
    gate_dir.mkdir(parents=True, exist_ok=True)
    final_path = gate_dir / output_name
    tmp_path = gate_dir / (output_name + TMP_SUFFIX)
    try:
        tmp_path.unlink()
    except OSError:
        pass
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    if stall_seconds > 0:
        time.sleep(stall_seconds)
    os.replace(tmp_path, final_path)
    return final_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive every 1M claim from one immutable selection record plus "
                    "hash-verified staged bytes and atomically publish a PROVISIONAL "
                    "(never adopted) manifest. Fail-closed: any mismatch refuses "
                    "publication with a nonzero exit and no output file."
    )
    parser.add_argument("--selection", type=Path, required=True,
                        help="Path to the immutable selection record JSON file")
    parser.add_argument("--gate-dir", type=Path,
                        default=ROOT_DIR / "docs" / "program" / "inbox"
                        / "h0-1m-corpus-contract",
                        help="Directory receiving the provisional manifest")
    parser.add_argument("--output-name", type=str, default="provisional_1m_manifest.json",
                        help="Provisional manifest file name inside --gate-dir")
    parser.add_argument("--expect", type=Path, default=None,
                        help="Optional JSON of expected claims (supports 'shard::field' "
                             "keys); any deviation refuses publication")
    parser.add_argument("--stall-before-publish", type=float, default=0.0,
                        help="Test-only delay in seconds between tmp fsync and atomic "
                             "rename, so a crash-safety probe can kill this process "
                             "mid-write. Never creates partial output.")
    args = parser.parse_args()

    selection_path = args.selection
    if not selection_path.exists():
        print("SEAL-REFUSE selection-missing: %s" % selection_path)
        return 1
    try:
        record, selection_sha = load_selection(selection_path)
    except (ValueError, OSError) as exc:
        print("SEAL-REFUSE bad-selection: %s" % exc)
        return 1

    claims, aux, errors = derive_claims(record)
    if args.expect is not None:
        try:
            errors.extend(check_expect(claims, args.expect))
        except (ValueError, OSError) as exc:
            errors.append("SEAL-REFUSE bad-expect-file: %s" % exc)
    if errors:
        print("[SEAL-REFUSE] publication refused with %d error(s):" % len(errors))
        for error in errors:
            print("  - %s" % error)
        return 1

    document = build_provisional(record, selection_sha, claims, aux)
    final_path = atomic_publish(args.gate_dir, args.output_name, document,
                                args.stall_before_publish)
    print("[SEAL-PUBLISH] provisional (UNADOPTED) manifest: %s" % final_path)
    print("  sha256: %s" % sha256_file(final_path))
    print("  docs: %d base + %d delta = %d; bytes: %d; union %s"
          % (claims["base_100k_documents_count"], claims["delta_900k_documents_count"],
             claims["target_unique_documents_d"], claims["total_raw_text_bytes"],
             claims["union_merkle_root_sha256"]))
    print("  co-signature: PENDING_HUMAN_BALLOT (separate ballot adopts; nothing conferred)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
