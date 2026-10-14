#!/usr/bin/env python3
"""Emit the H0 per-gate manifest for the Trace 1M corpus contract (WP-H0-2).

Runs benchmarks/verify_1m_checksums.py as a subprocess (fail closed) and
binds its recompute output together with source IDs, SHA-256 per shard,
licenses, tokenizer identity, the frozen workload vector, and revision
scope into one gate manifest JSON under docs/program/inbox/<gate>/.

Verdict discipline (H0 exit gate):
- Strict verifier PASS  -> manifest records ``signed: true`` with a
  human co-signature block left PENDING (only a human ballot in
  06_DECISION_LOG.md completes the gate; this script never prints
  CERTIFIED/APPROVED).
- Strict verifier FAIL  -> manifest records ``verdict: HOLD`` with the
  verifier errors embedded, ``signed: false``, and exits nonzero. No
  silent PASS: a HOLD manifest is evidence, not an approval.

A documented non-certifying forensic hypothesis may accompany a HOLD via
--forensic-overrides (dataset_name -> selection_range JSON). It is recorded
verbatim with its provenance and NEVER alters the strict verdict.

Default forensic hypothesis (H0-1M-CORPUS-CONTRACT): the pre-reseal shard
selection recovered from git history (commit d14f1a2, before the
scripts/finalize_1m_candidate.py reseal overwrote bright_delta counts and
wikipedia_delta bytes):
  bright_delta full-file dedup iteration (stage_1m_corpus.py step 2c has no
  index slice) + wikipedia_delta [0, 96639) prefix of the current staged
  file (the original 96639 records).

Usage:
    python3 scripts/sign_gate_manifest.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from trace.v2.atomizer import normalize_text, tokenize  # noqa: E402  (identity pin)

DEFAULT_VERIFIER = ROOT_DIR / "benchmarks" / "verify_1m_checksums.py"
DEFAULT_MANIFEST = (
    ROOT_DIR / "docs" / "program" / "inbox" / "1m-02-corpus-capsule"
    / "evidence" / "1m_corpus_manifest.json"
)
DEFAULT_QUERIES_MANIFEST = (
    ROOT_DIR / "docs" / "program" / "inbox" / "1m-02-corpus-capsule"
    / "evidence" / "1m_queries_manifest.json"
)
DEFAULT_GATE_DIR = ROOT_DIR / "docs" / "program" / "inbox" / "h0-1m-corpus-contract"
DEFAULT_GATE_ID = "H0-1M-CORPUS-CONTRACT"
BASE_COMMIT = "0150fbc19cc25bf2cb080bb797b535c3f4f5499d"

# Pre-reseal selection hypothesis; provenance: git show d14f1a2:<capsule
# manifest> vs HEAD (reseal at 34a0df1 via scripts/finalize_1m_candidate.py).
DEFAULT_FORENSIC_OVERRIDES = {
    "bright_delta": "[0, 928750)",
    "wikipedia_delta": "[0, 96639)",
}

ATOMIZER_REL = "src/trace/v2/atomizer.py"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def git_fact(args: list[str]) -> str:
    r = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False, cwd=str(ROOT_DIR)
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def build_gate_manifest(
    capsule: dict,
    recompute: dict,
    forensic: dict | None,
    verifier_argv: list[str],
    verifier_rc: int,
    verifier_stdout_tail: str,
    queries_manifest: dict,
    gate_id: str,
) -> dict:
    strict_passed: bool = bool(recompute.get("passed", False))
    summary: dict = recompute.get("summary", {})
    sources = []
    for entry in capsule.get("datasets_base", []) + capsule.get("datasets_delta", []):
        name = entry["dataset_name"]
        strict_row = next(
            (r for r in summary.get("shards", []) if r["dataset_name"] == name), {}
        )
        sources.append({
            "dataset_name": name,
            "partition": entry.get("partition"),
            "license": entry.get("license"),
            "license_url": entry.get("license_url"),
            "selection_range_manifest": entry.get("selection_range"),
            "selected_records_d_manifest": entry.get("selected_records_d"),
            "selected_text_bytes_manifest": entry.get("selected_text_bytes"),
            "source_file_manifest": entry.get("source_file"),
            "source_file_resolved": summary.get("path_map", {}).get(entry.get("source_file", "")),
            "source_file_sha256": entry.get("source_file_sha256"),
            "recomputed_docs_strict": strict_row.get("recomputed_docs"),
            "recomputed_bytes_strict": strict_row.get("recomputed_bytes"),
        })
    atomizer_path = ROOT_DIR / ATOMIZER_REL
    blind_rel = "docs/program/inbox/1m-02-corpus-capsule/evidence/1m_queries_blind_eval.jsonl"
    return {
        "gate_id": gate_id,
        "horizon": "H0",
        "objective": "Adopt the 1M corpus contract (preflight; grants no scale claim)",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": "SIGNED-AWAITING-BALLOT" if strict_passed else "HOLD",
        "signed": bool(strict_passed),
        "capsule": {
            "manifest_path": "docs/program/inbox/1m-02-corpus-capsule"
                             "/evidence/1m_corpus_manifest.json",
            "manifest_sha256": sha256_file(DEFAULT_MANIFEST),
            "contract_version": capsule.get("contract_version"),
            "status": capsule.get("status"),
        },
        "contract_claims": {
            "target_unique_documents_d": capsule.get("target_unique_documents_d"),
            "base_100k_documents_count": capsule.get("base_100k_documents_count"),
            "delta_900k_documents_count": capsule.get("delta_900k_documents_count"),
            "total_raw_text_bytes": capsule.get("total_raw_text_bytes"),
            "base_raw_text_bytes": capsule.get("base_raw_text_bytes"),
            "delta_raw_text_bytes": capsule.get("delta_raw_text_bytes"),
            "base_merkle_root_sha256": capsule.get("base_merkle_root_sha256"),
            "delta_merkle_root_sha256": capsule.get("delta_merkle_root_sha256"),
            "union_merkle_root_sha256": capsule.get("union_merkle_root_sha256"),
        },
        "verification": {
            "verifier": "benchmarks/verify_1m_checksums.py",
            "argv": verifier_argv,
            "exit_code": verifier_rc,
            "strict_passed": strict_passed,
            "strict_errors": recompute.get("errors", []),
            "strict_summary": summary,
            "stdout_tail": verifier_stdout_tail,
        },
        "forensic_non_certifying": forensic,
        "path_map": summary.get("path_map", {}),
        "sources": sources,
        "tokenizer_identity": {
            "module": "trace.v2.atomizer",
            "module_path": ATOMIZER_REL,
            "module_sha256": sha256_file(atomizer_path),
            "content_hash_primitive": "normalize_text: line-ending normalization only "
                                      "(CRLF/CR -> LF); leaf = sha256(normalized.encode('utf-8'))",
            "lexical_tokenizer": "tokenize: lowercased [A-Za-z0-9_]{2,} word tokens "
                                 "(model-free, deterministic)",
            "note": "1M contract pins raw UTF-8 bytes + content hashes; no model "
                    "tokenizer enters the corpus commitment.",
        },
        "frozen_workload_vector": {
            "manifest_path": "docs/program/inbox/1m-02-corpus-capsule"
                             "/evidence/1m_queries_manifest.json",
            "manifest_sha256": sha256_file(DEFAULT_QUERIES_MANIFEST),
            "contract_version": queries_manifest.get("contract_version"),
            "target_standard": queries_manifest.get("target_standard"),
            "selection_merkle_root_sha256": queries_manifest.get("selection_merkle_root_sha256"),
            "blind_file": queries_manifest.get("blind_queries_file"),
            "blind_file_sha256": sha256_file(ROOT_DIR / blind_rel),
            "summary_statistics": queries_manifest.get("summary_statistics"),
        },
        "revision_scope": {
            "packet_base_commit": BASE_COMMIT,
            "head_commit": git_fact(["rev-parse", "HEAD"]),
            "branch": git_fact(["branch", "--show-current"]),
            "scope": "H0 preflight only: path normalization + gate manifest. "
                     "No scale claim, no promotion, no capsule-manifest edits.",
        },
        "co_signature": {
            "status": "PENDING_HUMAN_BALLOT",
            "instruction": "A human records the H0 ballot in 06_DECISION_LOG.md; "
                           "until then this manifest confers no scale claim.",
            "ballot_text": (
                f"H0 {gate_id}: <PASS|HOLD|ABORT> — capsule "
                "1m_corpus_manifest.json (contract 2.0.0), union Merkle "
                f"{capsule.get('union_merkle_root_sha256')}, "
                "gate manifest <path>, verifier exit <rc>. Signed: <name+date>."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit the H0 per-gate manifest for the 1M corpus contract. "
                    "Fail-closed: verifier FAIL produces a HOLD manifest and a "
                    "nonzero exit; never a silent PASS."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help="Path to 1M corpus manifest JSON file")
    parser.add_argument("--queries-manifest", type=Path, default=DEFAULT_QUERIES_MANIFEST,
                        help="Path to 1M queries manifest JSON file")
    parser.add_argument("--verifier", type=Path, default=DEFAULT_VERIFIER,
                        help="Path to the 1M checksum verifier script")
    parser.add_argument("--gate-dir", type=Path, default=DEFAULT_GATE_DIR,
                        help="Directory receiving the gate manifest JSON")
    parser.add_argument("--gate-id", type=str, default=DEFAULT_GATE_ID,
                        help="Gate identifier recorded in the manifest")
    parser.add_argument("--forensic-overrides", type=str,
                        default=json.dumps(DEFAULT_FORENSIC_OVERRIDES),
                        help="JSON object for the verifier's non-certifying "
                             "forensic pass (default: pre-reseal hypothesis). "
                             "Use '{}' to skip the forensic pass.")
    args = parser.parse_args()

    gate_dir: Path = args.gate_dir
    gate_dir.mkdir(parents=True, exist_ok=True)
    tmp_out = gate_dir / ".verifier_recompute.tmp.json"

    verifier_argv = [sys.executable, str(args.verifier), "--manifest", str(args.manifest),
                     "--emit-json", str(tmp_out),
                     "--forensic-overrides", args.forensic_overrides]
    print(f"[H0-SIGN] Running: {' '.join(verifier_argv)}")
    proc = subprocess.run(verifier_argv, capture_output=True, text=True, check=False)
    print(proc.stdout[-3000:])
    if proc.stderr:
        print(proc.stderr[-1000:], file=sys.stderr)
    if not tmp_out.exists():
        print("[H0-SIGN-FAIL] Verifier produced no recompute JSON; refusing to sign.")
        return 1
    with open(tmp_out, "r", encoding="utf-8") as f:
        recompute = json.load(f)
    try:
        tmp_out.unlink()
    except OSError:
        pass

    with open(args.manifest, "r", encoding="utf-8") as f:
        capsule = json.load(f)
    with open(args.queries_manifest, "r", encoding="utf-8") as f:
        queries_manifest = json.load(f)

    manifest_doc = build_gate_manifest(
        capsule, recompute, recompute.get("forensic_non_certifying"),
        verifier_argv, proc.returncode, proc.stdout[-3000:],
        queries_manifest, args.gate_id,
    )
    out_path = gate_dir / "gate_manifest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest_doc, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"[H0-SIGN] Gate manifest: {out_path} (SHA-256: {sha256_file(out_path)})")
    if manifest_doc["signed"]:
        print("[H0-SIGN] Strict PASS recorded; awaiting human ballot (co-signature PENDING).")
        return 0
    print(f"[H0-SIGN-HOLD] Strict verifier failed with "
          f"{len(manifest_doc['verification']['strict_errors'])} errors; "
          f"verdict HOLD recorded, signed=false.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
