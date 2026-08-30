#!/usr/bin/env python3
"""Trace 100K Scale Gate Standalone Independent Candidate Verifier CLI.

Wave R2.4 Human Gate REPAIR / Level 1 Scale Certification Standard (DEC-P-005b-LEVEL1-R2.4):
- Authoritative Hash & Provenance Enforcement (Defect 4):
  * CANONICAL_POLICY_SHA256, CANONICAL_QUERIES_MANIFEST_SHA256, and CANONICAL_CORPUS_MANIFEST_SHA256 constants
  * Fail-closed policy loading against canonical digest and JSON schema validation
  * Verifies candidate runner_hash matches authoritative scripts/run_100k_scale_gate.py SHA-256
  * Verifies candidate verifier_hash matches authoritative scripts/verify_100k_candidate.py SHA-256
  * Verifies candidate schema_hash matches authoritative scale_policy.schema.json SHA-256
  * Verifies candidate policy_hash matches authoritative scale_policy.lock.json SHA-256
  * Enforces candidate_manifest.get("git_clean") is True in certifying candidate mode (dirty git worktree rejected)
- Strict 100,000 Unique Documents Verification (Defect 1):
  * Query scale_100k.db: COUNT(*) == required_D on events and ingestions (100,000)
  * COUNT(DISTINCT doc_id) == required_D on ingestions (100,000)
  * COUNT(DISTINCT content_hash) == required_D on ingestions (100,000)
  * COUNT(DISTINCT payload_hash) == required_D on events (100,000)
  * Colliding document IDs or duplicate content hashes fail closed
- Strict SQLite DB Membership for 100% of Candidates (Defect 2):
  * Load all persisted document IDs from SQLite (SELECT DISTINCT doc_id FROM ingestions)
  * Assert that every single candidate in ranked_candidates exists in persisted document IDs
  * Unpersisted candidate IDs or citations fail closed
- First-Principles Metric Recomputation & Sole Qrel Custody (Defect 3):
  * Verifier holds queries_manifest.json and computes all metrics from first principles
  * Candidate operates blindly: candidate records leaking gold_ids, is_null_query, expected_abstention, or precalculated metrics fail closed
  * Computes unfloored nDCG@10, Recall@20, Complete Coverage@20 (multi-hop binary coverage), Abstention accuracy, and Zero hallucination rate
- Retained Replay Database Mandatory & First-Principles Replay Audit (Defect 5):
  * scale_100k_replay.db is mandatory in evidence bundle (MANDATORY_EVIDENCE_FILES)
  * Direct inspection of scale_100k_replay.db: table row counts and table SHA-256 digests verified against scale_100k.db for all 6 tables
  * Fails closed if scale_100k_replay.db is missing or fails 6-table SHA-256 parity audit against scale_100k.db (never falls back to JSON)
  * Direct derivation of Graph P95 latency from graph_walk_telemetry.jsonl stream
- Total Hot-State Storage Accounting strictly against Frozen Policy Denominator (Defect 6):
  * Computes total hot database bytes: st_size(db) + st_size(db-wal) + st_size(db-shm) (for whichever exist)
  * Storage multiplier total_hot_bytes / frozen_raw_text_denominator_bytes strictly uses frozen policy denominator (62,870,136 bytes), never allowing dossier overrides
  * Peak RSS (Linux /proc/self/status VmHWM) and Current RSS (VmRSS) verified against policy ceiling
- Original-Source Real UTF-8 Byte Offset Anchor Proofs (Defect 7):
  * Slices raw UTF-8 bytes from raw dataset corpus files content.encode('utf-8')[span_start:span_end] to verify hashlib.sha256 matches content_hash
- Calibration Demotion:
  * When is_calibration is True (D < 100,000 or evaluated queries < 7,457):
    - Verdict MUST BE DIAGNOSTIC_NON_CERTIFYING (never PASS_INDEPENDENT_VERIFICATION)
    - Target standard MUST BE NONE_DIAGNOSTIC_ONLY (never DEC-P-005b-LEVEL1)
- Direct Read-Only SQLite database audit (PRAGMA query_only = ON)
- Schema-defined exit codes:
  * 0 = PASS / DIAGNOSTIC_NON_CERTIFYING (no invariant violations)
  * 1 = VERIFICATION_FAILED (violations found)
  * 2 = VERIFICATION_ERROR (operational crash, missing input files, etc.)

Usage:
    python scripts/verify_100k_candidate.py --candidate-dir benchmarks/runs/100k_scale_candidate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import quantiles
from typing import Any, Sequence

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

ROOT_DIR = Path(__file__).resolve().parents[1]

# Authoritative Canonical Hashes
CANONICAL_POLICY_SHA256 = "983279467455f006a5245bea0e8c550ce3a286fbda3fc5b01f9d797b05e3d880"
CANONICAL_QUERIES_MANIFEST_SHA256 = "8cb5c48cc722a5e92cd7d0451484ac1ea39804d3bed4a7d9db0e7f8fbabe18c9"
CANONICAL_CORPUS_MANIFEST_SHA256 = "0739a9cc9322ad647e7a1764114017ab17ba208ed2d0626f00bd1e3f1707ef6e"
CANONICAL_BLIND_QUERIES_SHA256 = "8731e89f4e1395c459da09859f89cc7bacad5dccf2c7c367874027e9021b449b"
CANONICAL_SCHEMA_SHA256 = "f9ce026422d4e0fc65b77f143d98559b26402629ebf56e9040d7181fa6fc2bb6"

# Schema-defined Exit Codes
EXIT_PASS = 0
EXIT_FAILED = 1
EXIT_ERROR = 2

# Verdict String Literals
VERDICT_PASS = "PASS_INDEPENDENT_VERIFICATION"
VERDICT_FAILED = "VERIFICATION_FAILED"
VERDICT_ERROR = "VERIFICATION_ERROR"
VERDICT_DIAGNOSTIC = "DIAGNOSTIC_NON_CERTIFYING"

# Standard Literals
STANDARD_LEVEL1 = "DEC-P-005b-LEVEL1"
STANDARD_DIAGNOSTIC = "NONE_DIAGNOSTIC_ONLY"

# Capability Lanes
CAPABILITY_LANES = [
    "direct_lookup",
    "domain_semantic",
    "semantic_qa",
    "multi_hop_reasoning",
    "abstention_suite",
]


# Ensure utf-8 encoding for stdout/stderr across Windows and Linux
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

import platform
import re


def resolve_platform_path(p: Path | str | None) -> Path | None:
    if p is None:
        return None
    s = str(p)
    if platform.system() == "Windows" and s.startswith("/mnt/c/"):
        s = "C:/" + s[7:]
    elif platform.system() != "Windows" and re.match(r"^[a-zA-Z]:[/\\]", s):
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/")
        s = f"/mnt/{drive}{rest}"
    return Path(s)


def safe_print(msg: str, file: Any = None) -> None:
    """Safely print message to stdout or stderr avoiding Unicode/charmap encoding crashes."""
    target_file = file or sys.stdout
    try:
        target_file.write(msg + "\n")
        target_file.flush()
    except UnicodeEncodeError:
        encoding = getattr(target_file, "encoding", "ascii") or "ascii"
        safe_msg = msg.encode(encoding, errors="backslashreplace").decode(encoding)
        target_file.write(safe_msg + "\n")
        target_file.flush()


def compute_sha256(path: Path | str) -> str:
    """Compute SHA-256 digest of a file in 64KB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_table_hash(conn: sqlite3.Connection, table_name: str) -> tuple[int, str]:
    """Compute deterministic row count and SHA-256 digest of an entire SQLite table."""
    cur = conn.cursor()
    target_table = table_name
    if table_name == "node_fts":
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='node_fts_content';")
        if cur.fetchone():
            target_table = "node_fts_content"

    cur.execute(f"PRAGMA table_info({target_table});")
    cols = [r[1] for r in cur.fetchall()]
    if not cols:
        return 0, hashlib.sha256(b"").hexdigest()

    col_str = ", ".join(f'"{c}"' for c in cols)
    order_clause = col_str if target_table != "node_fts" else "rowid"
    cur.execute(f"SELECT {col_str} FROM {target_table} ORDER BY {order_clause};")

    h = hashlib.sha256()
    count = 0
    while rows := cur.fetchmany(5000):
        for row in rows:
            count += 1
            row_repr = "|".join("" if v is None else str(v) for v in row)
            h.update(row_repr.encode("utf-8") + b"\n")
    return count, h.hexdigest()


def compute_merkle_root(leaf_hashes: list[str]) -> str:
    """Compute binary SHA-256 Merkle root from a list of leaf hex digests."""
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


def compute_percentiles(values: Sequence[float]) -> dict[str, float]:
    """Compute exact empirical latency percentiles (P50, P95, P99, Mean)."""
    if not values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0}
    sorted_v = sorted(values)
    n = len(sorted_v)
    mean_val = sum(sorted_v) / n
    if n == 1:
        return {"p50": sorted_v[0], "p95": sorted_v[0], "p99": sorted_v[0], "mean": mean_val}
    if n >= 100:
        qs = quantiles(sorted_v, n=100, method="inclusive")
        return {
            "p50": qs[49],
            "p95": qs[94],
            "p99": qs[98],
            "mean": mean_val,
        }
    p50_idx = int(round(0.50 * (n - 1)))
    p95_idx = int(round(0.95 * (n - 1)))
    p99_idx = int(round(0.99 * (n - 1)))
    return {
        "p50": sorted_v[p50_idx],
        "p95": sorted_v[p95_idx],
        "p99": sorted_v[p99_idx],
        "mean": mean_val,
    }


def compute_bootstrap_ci(
    values: Sequence[float],
    iterations: int = 10000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Compute bootstrap mean and [ci_lower, ci_upper] confidence interval (B=10000, seed=42)."""
    if not values:
        return 0.0, 0.0, 0.0
    n = len(values)
    mean_val = sum(values) / n
    if n == 1:
        return mean_val, mean_val, mean_val

    rng = random.Random(seed)
    choices = rng.choices
    sample_means = [sum(choices(values, k=n)) / n for _ in range(iterations)]
    sample_means.sort()

    alpha = (1.0 - confidence_level) / 2.0
    lower_idx = max(0, min(int(math.floor(alpha * iterations)), iterations - 1))
    upper_idx = max(0, min(int(math.ceil((1.0 - alpha) * iterations)) - 1, iterations - 1))

    return mean_val, sample_means[lower_idx], sample_means[upper_idx]


def extract_candidate_ids(cands_raw: Sequence[Any]) -> list[str]:
    """Extract string document IDs from a list of strings or candidate objects."""
    result: list[str] = []
    for c in cands_raw:
        if isinstance(c, dict):
            cid = str(c.get("doc_id") or c.get("id") or c.get("native_id") or "")
        else:
            cid = str(c)
        if cid:
            result.append(cid)
    return result


def extract_gold_ids(gold_raw: Any) -> set[str]:
    """Extract normalized set of gold document IDs."""
    if isinstance(gold_raw, (list, tuple, set)):
        result = set()
        for g in gold_raw:
            if isinstance(g, dict):
                gid = str(g.get("doc_id") or g.get("id") or g.get("native_id") or "")
            else:
                gid = str(g)
            if gid:
                result.add(gid)
        return result
    elif isinstance(gold_raw, str) and gold_raw:
        return {gold_raw}
    return set()


def compute_query_ndcg10_recall20_coverage20(
    candidates_raw: Sequence[Any],
    gold_ids: set[str],
) -> tuple[float, float, float]:
    """Independently calculate unfloored nDCG@10, Recall@20, and Complete Coverage@20 from top-20 ranking candidate IDs."""
    if not gold_ids:
        return 0.0, 0.0, 0.0

    candidates = extract_candidate_ids(candidates_raw)

    # Deduplicate candidate hits
    seen = set()
    dedup_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            dedup_candidates.append(c)

    # Recall@20 & Complete Coverage@20
    hits_20 = sum(1 for c in dedup_candidates[:20] if c in gold_ids)
    rec = hits_20 / float(len(gold_ids))
    cov = 1.0 if (hits_20 == len(gold_ids)) else 0.0

    # nDCG@10
    dcg = 0.0
    for rank_idx, cand in enumerate(dedup_candidates[:10]):
        if cand in gold_ids:
            dcg += 1.0 / math.log2(rank_idx + 2)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(10, len(gold_ids))))
    ndcg = (dcg / idcg) if idcg > 0 else 0.0

    return ndcg, rec, cov


# Backward compatibility alias
compute_query_ndcg10_recall20 = compute_query_ndcg10_recall20_coverage20


class CandidateVerifier:
    """Independent verification agent inspecting sealed candidate bundles under Wave R2.4."""

    def __init__(
        self,
        candidate_dir: Path,
        receipt_out: Path | None = None,
        queries_manifest_path: Path | None = None,
        policy_path: Path | None = None,
        corpus_manifest_path: Path | None = None,
        data_root: Path | None = None,
    ) -> None:
        self.candidate_dir = Path(candidate_dir).resolve()
        self.receipt_out = (receipt_out or (self.candidate_dir / "verifier_attestation_receipt.json")).resolve()

        # Dynamic Policy Path Resolution
        self.policy_path = self._resolve_policy_path(policy_path)
        # Dynamic Queries Manifest Path Resolution
        self.queries_manifest_path = self._resolve_queries_manifest_path(queries_manifest_path)
        # Dynamic Corpus Manifest Path Resolution
        self.corpus_manifest_path = self._resolve_corpus_manifest_path(corpus_manifest_path)
        self.data_root = Path(data_root).resolve() if data_root else None

        self.policy: dict[str, Any] = {}
        self.policy_sha256: str = ""
        self.queries_manifest: dict[str, Any] = {}
        self.queries_manifest_sha256: str = ""
        self.corpus_manifest: dict[str, Any] = {}
        self.corpus_manifest_sha256: str = ""
        self.persisted_doc_ids: set[str] = set()

        self.audit_log: list[str] = []
        self.violations: list[str] = []

    def _resolve_policy_path(self, explicit_path: Path | None) -> Path:
        if explicit_path:
            p = Path(explicit_path).resolve()
            if p.exists():
                return p
            raise FileNotFoundError(f"Specified policy lockfile not found: {p}")

        default_1 = ROOT_DIR / "benchmarks" / "policies" / "scale_policy.lock.json"
        if default_1.exists():
            return default_1.resolve()

        default_2 = ROOT_DIR / "docs" / "program" / "inbox" / "c2-pol-01-policy-reconciliation-20260829" / "evidence" / "scale_policy.lock.json"
        if default_2.exists():
            return default_2.resolve()

        raise FileNotFoundError(
            f"Unable to locate scale_policy.lock.json at default paths: {default_1} or {default_2}"
        )

    def _resolve_queries_manifest_path(self, explicit_path: Path | None) -> Path:
        if explicit_path:
            p = Path(explicit_path).resolve()
            if p.exists():
                return p
            raise FileNotFoundError(f"Specified queries manifest not found: {p}")

        default_path = (
            ROOT_DIR / "docs" / "program" / "inbox" / "l1-02-corpus-capsule-20260828" / "evidence" / "queries_manifest.json"
        )
        if default_path.exists():
            return default_path.resolve()

        raise FileNotFoundError(f"Unable to locate queries_manifest.json at default path: {default_path}")

    def _resolve_corpus_manifest_path(self, explicit_path: Path | None) -> Path:
        if explicit_path:
            p = Path(explicit_path).resolve()
            if p.exists():
                return p
            raise FileNotFoundError(f"Specified corpus manifest not found: {p}")

        default_path = (
            ROOT_DIR / "docs" / "program" / "inbox" / "l1-02-corpus-capsule-20260828" / "evidence" / "corpus_manifest.json"
        )
        if default_path.exists():
            return default_path.resolve()

        return default_path

    def log(self, msg: str) -> None:
        """Safe log output."""
        formatted = f"[VERIFIER] {msg}"
        safe_print(formatted)
        self.audit_log.append(msg)

    def load_policy(self) -> None:
        """Public alias for _load_policy."""
        self._load_policy()

    def _load_policy(self) -> None:
        """Load, compute SHA-256, fail closed on mismatch vs CANONICAL_POLICY_SHA256, and validate schema."""
        if not self.policy_path.exists():
            raise FileNotFoundError(f"Policy file does not exist: {self.policy_path}")

        self.policy_sha256 = compute_sha256(self.policy_path)
        with open(self.policy_path, "r", encoding="utf-8") as f:
            self.policy = json.load(f)

        # Enforce canonical SHA-256 digest
        if self.policy_sha256.lower() != CANONICAL_POLICY_SHA256.lower():
            err_msg = (
                f"Loaded policy lockfile SHA-256 '{self.policy_sha256}' does not match "
                f"expected canonical digest '{CANONICAL_POLICY_SHA256}'."
            )
            self.violations.append(err_msg)
            raise ValueError(err_msg)

        # Validate against JSON schema
        schema_path = ROOT_DIR / "benchmarks" / "policies" / "scale_policy.schema.json"
        if not schema_path.exists():
            schema_path = self.policy_path.parent / "scale_policy.schema.json"

        if schema_path.exists():
            with open(schema_path, "r", encoding="utf-8") as sf:
                schema_data = json.load(sf)
            if HAS_JSONSCHEMA:
                try:
                    jsonschema.validate(instance=self.policy, schema=schema_data)
                except jsonschema.ValidationError as s_err:
                    err_msg = f"Policy lockfile failed JSON Schema validation: {s_err.message}"
                    self.violations.append(err_msg)
                    raise ValueError(err_msg)
            else:
                for req_key in schema_data.get("required", []):
                    if req_key not in self.policy:
                        err_msg = f"Policy lockfile missing required schema key '{req_key}'"
                        self.violations.append(err_msg)
                        raise ValueError(err_msg)

        self.log(f"Loaded and schema-validated scale policy: {self.policy_path}")
        self.log(f"Policy ID: {self.policy.get('policy_id', 'UNKNOWN')} | Policy SHA-256: {self.policy_sha256}")

    def load_queries_manifest(self) -> None:
        """Public alias for _load_queries_manifest."""
        self._load_queries_manifest()

    def _load_queries_manifest(self) -> None:
        """Load and validate queries manifest against CANONICAL_QUERIES_MANIFEST_SHA256."""
        if not self.queries_manifest_path.exists():
            raise FileNotFoundError(f"Queries manifest does not exist: {self.queries_manifest_path}")

        self.queries_manifest_sha256 = compute_sha256(self.queries_manifest_path)
        with open(self.queries_manifest_path, "r", encoding="utf-8") as f:
            self.queries_manifest = json.load(f)

        if self.queries_manifest_sha256.lower() != CANONICAL_QUERIES_MANIFEST_SHA256.lower():
            err_msg = (
                f"Loaded queries manifest SHA-256 '{self.queries_manifest_sha256}' does not match "
                f"expected canonical digest '{CANONICAL_QUERIES_MANIFEST_SHA256}'."
            )
            self.violations.append(err_msg)
            self.log(f"[VIOLATION] {err_msg}")

        total_closed = self.queries_manifest.get("summary_statistics", {}).get("total_closed_evaluation_queries", 0)
        self.log(f"Loaded frozen queries manifest: {self.queries_manifest_path}")
        self.log(f"Queries Manifest SHA-256: {self.queries_manifest_sha256} | Declared Closed Queries: {total_closed}")

    def load_corpus_manifest(self) -> None:
        """Public alias for _load_corpus_manifest."""
        self._load_corpus_manifest()

    def _load_corpus_manifest(self) -> None:
        """Load and validate corpus manifest against CANONICAL_CORPUS_MANIFEST_SHA256."""
        if not self.corpus_manifest_path.exists():
            self.log(f"Corpus manifest not found at {self.corpus_manifest_path} (skipping optional corpus file direct reading)")
            return

        self.corpus_manifest_sha256 = compute_sha256(self.corpus_manifest_path)
        with open(self.corpus_manifest_path, "r", encoding="utf-8") as f:
            self.corpus_manifest = json.load(f)

        if self.corpus_manifest_sha256.lower() != CANONICAL_CORPUS_MANIFEST_SHA256.lower():
            err_msg = (
                f"Loaded corpus manifest SHA-256 '{self.corpus_manifest_sha256}' does not match "
                f"expected canonical digest '{CANONICAL_CORPUS_MANIFEST_SHA256}'."
            )
            self.violations.append(err_msg)
            self.log(f"[VIOLATION] {err_msg}")

        self.log(f"Loaded corpus manifest: {self.corpus_manifest_path} (SHA-256: {self.corpus_manifest_sha256})")

    def verify_all(self) -> dict[str, Any]:
        """Execute full independent verification protocol under Wave R2.4."""
        self.log(f"Starting Wave R2.4 Independent Verification on: {self.candidate_dir}")

        if not self.candidate_dir.exists():
            raise FileNotFoundError(f"Candidate directory does not exist: {self.candidate_dir}")

        # 1. Load Policy, Queries Manifest, and Corpus Manifest
        self.load_policy()
        self.load_queries_manifest()
        self.load_corpus_manifest()

        # 2. Checksums.json verification & Merkle leaf computation
        checksums_path = self.candidate_dir / "checksums.json"
        if not checksums_path.exists():
            raise FileNotFoundError(f"Missing checksums.json at {checksums_path}")

        with open(checksums_path, "r", encoding="utf-8") as f:
            checksums = json.load(f)

        MANDATORY_EVIDENCE_FILES = [
            "scale_100k.db", "scale_100k_replay.db", "checksums.json", "candidate_manifest.json",
            "runs/raw_query_evaluations.jsonl", "runs/abstention_evaluations.jsonl",
            "runs/replay_recovery_trace.json", "runs/durability_audit_trace.json",
            "runs/telemetry_timeseries.json", "runs/graph_walk_telemetry.jsonl",
            "runs/restart_recovery_receipt.json", "runs/incremental_resume_receipt.json"
        ]

        # Check dossier explicit existence
        dossier_path = self.candidate_dir / "100k_scale_dossier.json"
        if not dossier_path.exists():
            dossier_path = self.candidate_dir / "100k_scale_diagnostic_dossier.json"
        if not dossier_path.exists():
            raise FileNotFoundError(f"Missing dossier file in {self.candidate_dir}")

        for m_file in MANDATORY_EVIDENCE_FILES:
            if m_file == "scale_100k_replay.db":
                f_path = self.candidate_dir / m_file
                if not f_path.exists():
                    f_path = self.candidate_dir / "runs" / m_file
                if not f_path.exists():
                    self.violations.append(f"Missing mandatory evidence file: {m_file}")
                if (m_file not in checksums and f"runs/{m_file}" not in checksums) and m_file != "checksums.json":
                    self.violations.append(f"Missing mandatory evidence file in checksums.json: {m_file}")
            else:
                f_path = self.candidate_dir / m_file
                if not f_path.exists():
                    self.violations.append(f"Missing mandatory evidence file: {m_file}")
                if m_file not in checksums and m_file != "checksums.json":
                    self.violations.append(f"Missing mandatory evidence file in checksums.json: {m_file}")

        verified_checksums = 0
        leaf_hashes: list[str] = []
        evidence_files_audited: dict[str, str] = {}

        for rel_path, expected_sha in sorted(checksums.items()):
            file_path = self.candidate_dir / rel_path
            if not file_path.exists():
                self.violations.append(f"Missing file declared in checksums.json: {rel_path}")
                continue
            actual_sha = compute_sha256(file_path)
            leaf_hashes.append(actual_sha)
            evidence_files_audited[rel_path] = actual_sha

            if actual_sha != expected_sha:
                self.violations.append(
                    f"Checksum mismatch for {rel_path}: expected {expected_sha[:12]}, got {actual_sha[:12]}"
                )
            else:
                verified_checksums += 1

        # Add checksums.json itself into the candidate evidence Merkle leaves
        checksums_self_sha = compute_sha256(checksums_path)
        leaf_hashes.append(checksums_self_sha)
        evidence_files_audited["checksums.json"] = checksums_self_sha

        merkle_root = compute_merkle_root(leaf_hashes)
        self.log(f"Checksums Verified: {verified_checksums}/{len(checksums)} files passed 100% SHA-256 match.")
        self.log(f"Candidate Evidence SHA-256 Merkle Root: {merkle_root}")

        # 3. Dossier & Manifest inspection and Cryptographic Bindings (Defect 4)
        with open(dossier_path, "r", encoding="utf-8") as f:
            dossier = json.load(f)

        candidate_manifest_path = self.candidate_dir / "candidate_manifest.json"
        candidate_manifest: dict[str, Any] = {}
        if candidate_manifest_path.exists():
            with open(candidate_manifest_path, "r", encoding="utf-8") as f:
                candidate_manifest = json.load(f)

        doc_count_D = dossier.get("scale_workload_vector", {}).get("document_count_D", 0)
        required_D = self.policy.get("scale", {}).get("required_document_count_D", 100000)
        expected_total_queries = self.queries_manifest.get("summary_statistics", {}).get("total_closed_evaluation_queries", 7457)

        # Policy SHA-256 Enforcement
        candidate_declared_policy_sha = (
            candidate_manifest.get("policy_sha256")
            or candidate_manifest.get("scale_policy_sha256")
            or candidate_manifest.get("policy_hash")
            or dossier.get("policy_sha256")
            or dossier.get("scale_policy_sha256")
            or dossier.get("governance", {}).get("policy_sha256")
        )
        cand_local_policy_file = self.candidate_dir / "scale_policy.lock.json"
        if cand_local_policy_file.exists():
            cand_local_sha = compute_sha256(cand_local_policy_file)
            if cand_local_sha.lower() != CANONICAL_POLICY_SHA256.lower():
                self.violations.append(
                    f"Candidate directory scale_policy.lock.json SHA-256 '{cand_local_sha}' != canonical policy SHA-256 '{CANONICAL_POLICY_SHA256}'"
                )
            if not candidate_declared_policy_sha:
                candidate_declared_policy_sha = cand_local_sha

        if candidate_declared_policy_sha:
            if candidate_declared_policy_sha.lower() != CANONICAL_POLICY_SHA256.lower():
                self.violations.append(
                    f"Candidate declared policy SHA-256 mismatch: candidate declared '{candidate_declared_policy_sha}', canonical is '{CANONICAL_POLICY_SHA256}'"
                )
            else:
                self.log(f"Policy Lockfile SHA-256 Binding Verified: {CANONICAL_POLICY_SHA256}")

        # Query Manifest SHA-256 Enforcement
        candidate_declared_manifest_sha = (
            candidate_manifest.get("queries_manifest_sha256")
            or candidate_manifest.get("query_manifest_sha256")
            or dossier.get("queries_manifest_sha256")
            or dossier.get("query_manifest_sha256")
            or dossier.get("governance", {}).get("queries_manifest_sha256")
        )
        cand_local_manifest_file = self.candidate_dir / "queries_manifest.json"
        if cand_local_manifest_file.exists():
            cand_local_m_sha = compute_sha256(cand_local_manifest_file)
            if cand_local_m_sha.lower() != CANONICAL_QUERIES_MANIFEST_SHA256.lower():
                self.violations.append(
                    f"Candidate directory queries_manifest.json SHA-256 '{cand_local_m_sha}' != canonical manifest SHA-256 '{CANONICAL_QUERIES_MANIFEST_SHA256}'"
                )
            if not candidate_declared_manifest_sha:
                candidate_declared_manifest_sha = cand_local_m_sha

        if candidate_declared_manifest_sha:
            if candidate_declared_manifest_sha.lower() != CANONICAL_QUERIES_MANIFEST_SHA256.lower():
                self.violations.append(
                    f"Candidate declared queries manifest SHA-256 mismatch: candidate declared '{candidate_declared_manifest_sha}', canonical is '{CANONICAL_QUERIES_MANIFEST_SHA256}'"
                )
            else:
                self.log(f"Queries Manifest SHA-256 Binding Verified: {CANONICAL_QUERIES_MANIFEST_SHA256}")

        if self.queries_manifest_sha256.lower() != CANONICAL_QUERIES_MANIFEST_SHA256.lower():
            self.violations.append(
                f"Verifier loaded queries manifest SHA-256 '{self.queries_manifest_sha256}' != canonical '{CANONICAL_QUERIES_MANIFEST_SHA256}'"
            )

        # Blind Queries SHA-256 Enforcement (Defect 3 & 4)
        cand_blind_queries_sha = (
            candidate_manifest.get("blind_queries_sha256")
            or candidate_manifest.get("queries_blind_eval_sha256")
            or candidate_manifest.get("blind_queries_hash")
            or dossier.get("blind_queries_sha256")
        )
        if not cand_blind_queries_sha:
            self.violations.append(
                f"Candidate manifest missing required 'blind_queries_sha256' binding (expected '{CANONICAL_BLIND_QUERIES_SHA256}')"
            )
        elif cand_blind_queries_sha.lower() != CANONICAL_BLIND_QUERIES_SHA256.lower():
            self.violations.append(
                f"Candidate declared blind queries SHA-256 mismatch: candidate declared '{cand_blind_queries_sha}', canonical is '{CANONICAL_BLIND_QUERIES_SHA256}'"
            )
        else:
            self.log(f"Blind Queries SHA-256 Binding Verified: {CANONICAL_BLIND_QUERIES_SHA256}")

        # Calibration Determination
        is_calibration = (doc_count_D < required_D)

        # Defect 4: Authoritative Script, Policy, Schema Hash & Git Provenance Verification
        runner_file_path = ROOT_DIR / "scripts" / "run_100k_scale_gate.py"
        auth_runner_sha = compute_sha256(runner_file_path) if runner_file_path.exists() else None
        cand_runner_hash = candidate_manifest.get("runner_hash") or candidate_manifest.get("runner_sha256")
        if cand_runner_hash and auth_runner_sha:
            if cand_runner_hash.lower() != auth_runner_sha.lower():
                self.violations.append(
                    f"Candidate declared runner hash mismatch: candidate declared '{cand_runner_hash}', "
                    f"authoritative scripts/run_100k_scale_gate.py SHA-256 is '{auth_runner_sha}'"
                )
            else:
                self.log(f"Runner Script SHA-256 Binding Verified: {auth_runner_sha}")
        elif not is_calibration and not cand_runner_hash:
            self.violations.append("Candidate manifest missing required 'runner_hash' / 'runner_sha256'")

        verifier_file_path = Path(__file__).resolve()
        auth_verifier_sha = compute_sha256(verifier_file_path) if verifier_file_path.exists() else None
        cand_verifier_hash = candidate_manifest.get("verifier_hash") or candidate_manifest.get("verifier_sha256")
        if cand_verifier_hash and auth_verifier_sha:
            if cand_verifier_hash.lower() != auth_verifier_sha.lower():
                self.violations.append(
                    f"Candidate declared verifier hash mismatch: candidate declared '{cand_verifier_hash}', "
                    f"authoritative scripts/verify_100k_candidate.py SHA-256 is '{auth_verifier_sha}'"
                )
            else:
                self.log(f"Verifier Script SHA-256 Binding Verified: {auth_verifier_sha}")
        elif not is_calibration and not cand_verifier_hash:
            self.violations.append("Candidate manifest missing required 'verifier_hash' / 'verifier_sha256'")

        schema_file_path = ROOT_DIR / "benchmarks" / "policies" / "scale_policy.schema.json"
        if not schema_file_path.exists():
            schema_file_path = self.policy_path.parent / "scale_policy.schema.json"
        auth_schema_sha = compute_sha256(schema_file_path) if schema_file_path.exists() else None

        cand_schema_hash = candidate_manifest.get("schema_hash") or candidate_manifest.get("schema_sha256")
        if cand_schema_hash:
            if cand_schema_hash.lower() != CANONICAL_SCHEMA_SHA256.lower():
                self.violations.append(
                    f"Candidate declared schema hash mismatch: candidate declared '{cand_schema_hash}', "
                    f"canonical schema SHA-256 is '{CANONICAL_SCHEMA_SHA256}'"
                )
            else:
                self.log(f"Policy Schema SHA-256 Binding Verified: {CANONICAL_SCHEMA_SHA256}")
        elif not is_calibration:
            self.violations.append("Candidate manifest missing required 'schema_hash' / 'schema_sha256'")

        # Git Clean Verification for Certifying Candidate Mode
        is_candidate_mode = (candidate_manifest.get("execution_mode") == "candidate") or (not is_calibration)
        if is_candidate_mode and candidate_manifest:
            if candidate_manifest.get("git_clean") is not True:
                self.violations.append(
                    f"Candidate manifest git_clean is {candidate_manifest.get('git_clean')}, expected True for certifying candidate run (dirty git worktree rejected)"
                )
            else:
                self.log(f"Candidate Git Provenance Verified: Clean worktree commit {candidate_manifest.get('git_commit')}")

        # Cryptographic Identity Bindings Check in Candidate Manifest
        REQUIRED_MANIFEST_BINDINGS = [
            ("git_commit", ["git_commit", "commit_hash", "commit"]),
            ("runner_hash", ["runner_hash", "runner_sha256"]),
            ("verifier_hash", ["verifier_hash", "verifier_sha256"]),
            ("schema_hash", ["schema_hash", "schema_sha256"]),
            ("policy_hash", ["policy_hash", "policy_sha256", "scale_policy_sha256"]),
            ("blind_queries_sha256", ["blind_queries_sha256", "queries_blind_eval_sha256", "blind_queries_hash"]),
            ("command_line", ["command_line", "cli_args", "command"]),
        ]
        if not is_calibration and candidate_manifest:
            for binding_name, aliases in REQUIRED_MANIFEST_BINDINGS:
                if not any(candidate_manifest.get(alias) for alias in aliases):
                    self.violations.append(
                        f"Candidate manifest missing required cryptographic identity binding: '{binding_name}'"
                    )

        # 4. Host Environment Memory & Peak RSS (VmHWM) Derivation (Defect #6, #10)
        timeseries_path = self.candidate_dir / "runs" / "telemetry_timeseries.json"
        if not timeseries_path.exists():
            timeseries_path = self.candidate_dir / "telemetry_timeseries.json"

        max_peak_ram_gb = self.policy.get("memory", {}).get("max_peak_ram_gb", 8.0)
        if not timeseries_path.exists():
            self.violations.append("Missing mandatory evidence file: runs/telemetry_timeseries.json")
            effective_peak_rss_gb = 999.0
            effective_current_rss_gb = 999.0
        else:
            with open(timeseries_path, "r", encoding="utf-8") as f:
                ts_raw = json.load(f)
            samples = ts_raw if isinstance(ts_raw, list) else ts_raw.get("timeseries", [])
            if not samples:
                self.violations.append("telemetry_timeseries.json is empty or invalid.")
                max_peak_rss_mb = 0.0
                max_current_rss_mb = 0.0
            else:
                max_peak_rss_mb = max((float(s.get("peak_rss_mb") or s.get("rss_mb") or 0.0) for s in samples if isinstance(s, dict)), default=0.0)
                max_current_rss_mb = max((float(s.get("rss_mb", 0.0)) for s in samples if isinstance(s, dict)), default=0.0)
            if max_peak_rss_mb <= 0.0:
                self.violations.append("telemetry_timeseries.json contains invalid rss_mb / peak_rss_mb data.")

            effective_peak_rss_gb = max_peak_rss_mb / 1024.0
            effective_current_rss_gb = max_current_rss_mb / 1024.0
            self.log(
                f"Host Environment Memory: Peak RSS (VmHWM) = {effective_peak_rss_gb:.3f} GiB, "
                f"Current RSS (VmRSS) = {effective_current_rss_gb:.3f} GiB (Limit: <= {max_peak_ram_gb:.1f} GiB)"
            )
            if effective_peak_rss_gb > max_peak_ram_gb:
                self.violations.append(f"Peak RSS {effective_peak_rss_gb:.3f} GiB > {max_peak_ram_gb:.1f} GiB")

        # 5. Read-Only SQLite Database Audit (Defects #1, #2, #6, #7)
        db_path = self.candidate_dir / "scale_100k.db"
        if not db_path.exists():
            db_candidates = list(self.candidate_dir.glob("*.db"))
            if db_candidates:
                db_path = db_candidates[0]
            else:
                raise FileNotFoundError(f"Missing scale_100k.db database in candidate custody: {self.candidate_dir}")

        db_sha256 = compute_sha256(db_path) if db_path.exists() else ""
        db_size_bytes = db_path.stat().st_size if db_path.exists() else 0
        persisted_max_degree = 0
        anchor_matches = 0
        total_atoms = 0
        total_events = 0
        table_counts: dict[str, int] = {}
        anchor_recovery_rate = 0.0
        sampled_proof_count = 0

        max_storage_bytes = self.policy.get("storage", {}).get("max_storage_bytes", 188610408)
        max_storage_mult = self.policy.get("storage", {}).get("max_storage_multiplier", 3.00)
        max_stored_deg = self.policy.get("graph", {}).get("max_stored_degree", 10)
        min_anchor_rec = self.policy.get("durability", {}).get("min_anchor_recovery", 1.000)
        anchor_proof_samples = self.policy.get("durability", {}).get("anchor_proof_samples", 1000)
        verification_tables = list(self.policy.get("resilience", {}).get(
            "verification_tables",
            ["events", "ingestions", "nodes", "node_versions", "edge_versions", "source_lifecycle"]
        ))
        if "node_fts" not in verification_tables:
            verification_tables.append("node_fts")

        events_distinct_payload_hash = 0
        ingestions_distinct_doc_id = 0
        ingestions_distinct_content_hash = 0

        if db_path.exists():
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                conn.execute("PRAGMA query_only = ON;")
                cur = conn.cursor()

                cur.execute("PRAGMA quick_check;")
                quick_res = cur.fetchone()[0]
                if quick_res != "ok":
                    self.violations.append(f"SQLite PRAGMA quick_check failed: {quick_res}")
                else:
                    self.log("SQLite PRAGMA quick_check: OK")

                cur.execute("PRAGMA integrity_check;")
                integ_res = cur.fetchone()[0]
                if integ_res != "ok":
                    self.violations.append(f"SQLite PRAGMA integrity_check failed: {integ_res}")
                else:
                    self.log("SQLite PRAGMA integrity_check: OK")

                for table in verification_tables:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {table}")
                        cnt = cur.fetchone()[0]
                        table_counts[table] = cnt
                    except sqlite3.OperationalError as table_err:
                        self.violations.append(f"Verification table '{table}' query error: {table_err}")

                total_atoms = table_counts.get("node_versions", 0)
                total_events = table_counts.get("events", 0)

                # Defect 1: Strict Unique Document Verification
                cur.execute("SELECT COUNT(*), COUNT(DISTINCT payload_hash) FROM events")
                events_cnt, events_distinct_payload_hash = cur.fetchone()

                cur.execute("SELECT COUNT(*), COUNT(DISTINCT doc_id), COUNT(DISTINCT content_hash) FROM ingestions")
                ing_cnt, ingestions_distinct_doc_id, ingestions_distinct_content_hash = cur.fetchone()

                self.log(
                    f"SQLite Unique Document Integrity: events COUNT={events_cnt}, Distinct payload_hash={events_distinct_payload_hash} | "
                    f"ingestions COUNT={ing_cnt}, Distinct doc_id={ingestions_distinct_doc_id}, Distinct content_hash={ingestions_distinct_content_hash}"
                )

                if not is_calibration:
                    if events_cnt != required_D:
                        self.violations.append(f"Persisted SQLite events row count {events_cnt} != {required_D}")
                    if events_distinct_payload_hash != required_D:
                        self.violations.append(
                            f"Persisted SQLite events distinct payload_hash count {events_distinct_payload_hash} != {required_D} "
                            f"({events_cnt - events_distinct_payload_hash} duplicate payload hashes found)"
                        )
                    if ing_cnt != required_D:
                        self.violations.append(f"Persisted SQLite ingestions row count {ing_cnt} != {required_D}")
                    if ingestions_distinct_doc_id != required_D:
                        self.violations.append(
                            f"Persisted SQLite ingestions distinct doc_id count {ingestions_distinct_doc_id} != {required_D} "
                            f"({ing_cnt - ingestions_distinct_doc_id} duplicate doc_ids found)"
                        )
                    if ingestions_distinct_content_hash != required_D:
                        self.violations.append(
                            f"Persisted SQLite ingestions distinct content_hash count {ingestions_distinct_content_hash} != {required_D} "
                            f"({ing_cnt - ingestions_distinct_content_hash} duplicate content hashes found)"
                        )
                else:
                    if events_distinct_payload_hash < events_cnt:
                        self.violations.append(
                            f"SQLite events contains {events_cnt - events_distinct_payload_hash} duplicate payload hashes "
                            f"({events_distinct_payload_hash} distinct out of {events_cnt})"
                        )
                    if ingestions_distinct_doc_id < ing_cnt:
                        self.violations.append(
                            f"SQLite ingestions contains {ing_cnt - ingestions_distinct_doc_id} duplicate doc_ids "
                            f"({ingestions_distinct_doc_id} distinct out of {ing_cnt})"
                        )
                    if ingestions_distinct_content_hash < ing_cnt:
                        self.violations.append(
                            f"SQLite ingestions contains {ing_cnt - ingestions_distinct_content_hash} duplicate content hashes "
                            f"({ingestions_distinct_content_hash} distinct out of {ing_cnt})"
                        )

                # Defect 2: Load all persisted document IDs from SQLite
                cur.execute("SELECT DISTINCT doc_id FROM ingestions")
                self.persisted_doc_ids = {str(row[0]) for row in cur.fetchall()}
                self.log(f"Loaded {len(self.persisted_doc_ids)} distinct canonical persisted document IDs from SQLite.")

                cur.execute("SELECT COALESCE(MAX(deg), 0) FROM (SELECT COUNT(*) as deg FROM edge_versions GROUP BY source_id)")
                persisted_max_degree = cur.fetchone()[0]
                self.log(f"Persisted SQLite Max Degree (SQL): {persisted_max_degree} (Limit: <= {max_stored_deg})")
                if persisted_max_degree > max_stored_deg:
                    self.violations.append(f"Persisted max graph degree {persisted_max_degree} > {max_stored_deg}")

                # Defect 7: Strict Source-Only Original UTF-8 Byte-Offset Anchor Proofs Verification
                sample_size = min(anchor_proof_samples, total_atoms)
                if sample_size > 0:
                    cur.execute(
                        f"WITH sampled_nv AS ("
                        f"    SELECT atom_version_id, stream_sequence, span_start, span_end, content_hash "
                        f"    FROM node_versions ORDER BY substr(content_hash, 1, 8), atom_version_id LIMIT {sample_size}"
                        f") "
                        f"SELECT snv.atom_version_id, snv.span_start, snv.span_end, snv.content_hash, "
                        f"       ing.doc_id, ing.dataset "
                        f"FROM sampled_nv snv "
                        f"JOIN ingestions ing ON ing.stream_sequence = snv.stream_sequence"
                    )
                    sampled_rows = cur.fetchall()
                    sampled_proof_count = len(sampled_rows)

                    # Determine data root for original dataset corpus files
                    candidate_data_root = None
                    if self.data_root:
                        p = resolve_platform_path(self.data_root)
                        if p and p.exists():
                            candidate_data_root = p
                    elif candidate_manifest and candidate_manifest.get("data_root"):
                        p = resolve_platform_path(candidate_manifest["data_root"])
                        if p and p.exists():
                            candidate_data_root = p
                    elif (self.candidate_dir / "data").exists():
                        candidate_data_root = self.candidate_dir / "data"
                    elif (self.candidate_dir / "mock_data").exists():
                        candidate_data_root = self.candidate_dir / "mock_data"
                    elif self.corpus_manifest and self.corpus_manifest.get("base_data_root"):
                        manifest_root = resolve_platform_path(self.corpus_manifest["base_data_root"])
                        if manifest_root and manifest_root.exists():
                            candidate_data_root = manifest_root

                    if not candidate_data_root or not candidate_data_root.exists():
                        self.violations.append(
                            f"Original source dataset root not found for anchor proofs verification (data_root={self.data_root}). "
                            f"Defect 7: original-source proof strictly requires upstream source dataset files."
                        )

                    # If dataset corpus files exist, build index of needed raw documents
                    raw_corpus_docs: dict[tuple[str, str], str] = {}
                    if candidate_data_root and candidate_data_root.exists():
                        needed_docs_by_dataset: dict[str, set[str]] = {}
                        for _, _, _, _, doc_id, dataset_name in sampled_rows:
                            needed_docs_by_dataset.setdefault(dataset_name, set()).add(str(doc_id))

                        manifest_rel_paths: dict[str, str] = {}
                        if self.corpus_manifest and self.corpus_manifest.get("datasets"):
                            for ds_item in self.corpus_manifest["datasets"]:
                                d_name = ds_item.get("dataset_name") or ds_item.get("dataset")
                                cf_rel = (
                                    ds_item.get("corpus_file", {}).get("relative_path")
                                    if isinstance(ds_item.get("corpus_file"), dict)
                                    else None
                                )
                                if d_name and cf_rel:
                                    manifest_rel_paths[d_name] = cf_rel

                        for ds_name, doc_id_set in needed_docs_by_dataset.items():
                            corpus_file_candidates = []
                            if ds_name in manifest_rel_paths:
                                corpus_file_candidates.append(candidate_data_root / manifest_rel_paths[ds_name])
                            corpus_file_candidates.extend([
                                candidate_data_root / ds_name / "corpus.jsonl",
                                candidate_data_root / f"{ds_name}.jsonl",
                                candidate_data_root / f"{ds_name}.txt",
                                candidate_data_root / "corpus.jsonl",
                            ])
                            corpus_file = next((p for p in corpus_file_candidates if p.exists()), None)
                            if corpus_file:
                                with open(corpus_file, "r", encoding="utf-8") as cf:
                                    for line_idx, line in enumerate(cf):
                                        if not doc_id_set:
                                            break
                                        line_str = line.strip()
                                        if not line_str:
                                            continue
                                        try:
                                            rec = json.loads(line_str)
                                            cid = str(
                                                rec.get("native_id")
                                                if rec.get("native_id") is not None
                                                else (
                                                    rec.get("internal_id")
                                                    or rec.get("segment_internal_id")
                                                    or rec.get("source_document_internal_id")
                                                    or rec.get("id")
                                                    or rec.get("_id")
                                                    or rec.get("source_key")
                                                    or f"{ds_name}:{line_idx}"
                                                )
                                            )
                                            text = rec.get("text") or rec.get("content") or ""
                                            title = rec.get("title") or ""
                                        except Exception:
                                            cid = f"{corpus_file.stem}_{line_idx}"
                                            text = line_str
                                            title = ""

                                        if cid in doc_id_set:
                                            full_content = (f"{title}\n\n{text}".strip() if title else text.strip()).replace("\r\n", "\n").replace("\r", "\n")
                                            raw_corpus_docs[(ds_name, cid)] = full_content
                                            raw_corpus_docs[("", cid)] = full_content
                                            doc_id_set.remove(cid)

                            # Check for direct doc files if any remaining
                            for remaining_id in list(doc_id_set):
                                base_stem = remaining_id.rsplit("_", 1)[0] if "_" in remaining_id else remaining_id
                                direct_cand_files = [
                                    candidate_data_root / f"{remaining_id}.txt",
                                    candidate_data_root / f"{remaining_id}.json",
                                    candidate_data_root / f"{base_stem}.txt",
                                    candidate_data_root / f"{base_stem}.json",
                                    candidate_data_root / ds_name / f"{remaining_id}.txt",
                                    candidate_data_root / ds_name / f"{base_stem}.txt",
                                ]
                                for df in direct_cand_files:
                                    if df.exists():
                                        try:
                                            if df.suffix == ".json":
                                                dj = json.loads(df.read_text(encoding="utf-8"))
                                                t = dj.get("text") or dj.get("content") or ""
                                                tit = dj.get("title") or ""
                                                fc = (f"{tit}\n\n{t}".strip() if tit else t.strip()).replace("\r\n", "\n").replace("\r", "\n")
                                            else:
                                                fc = df.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
                                            raw_corpus_docs[(ds_name, remaining_id)] = fc
                                            raw_corpus_docs[("", remaining_id)] = fc
                                            doc_id_set.remove(remaining_id)
                                            break
                                        except Exception:
                                            pass

                    source_corpus_matches = 0
                    for av_id, s_start, s_end, stored_hash, doc_id, dataset_name in sampled_rows:
                        raw_content = raw_corpus_docs.get((dataset_name, str(doc_id))) or raw_corpus_docs.get(("", str(doc_id)))
                        if raw_content is None:
                            self.violations.append(
                                f"Sampled anchor proof '{av_id}' for doc '{doc_id}' in dataset '{dataset_name}' "
                                f"could not be resolved from upstream source dataset files in {candidate_data_root}"
                            )
                            continue

                        content_bytes = raw_content.encode("utf-8")
                        byte_slice = content_bytes[s_start:s_end]
                        calc_hash = hashlib.sha256(byte_slice).hexdigest()
                        if calc_hash == stored_hash:
                            anchor_matches += 1
                            source_corpus_matches += 1
                        else:
                            self.violations.append(
                                f"Anchor proof hash mismatch for atom '{av_id}' (doc '{doc_id}'): "
                                f"expected {stored_hash[:12]}, got {calc_hash[:12]} from upstream source byte slice [{s_start}:{s_end}]"
                            )

                    anchor_recovery_rate = anchor_matches / max(1, sampled_proof_count)
                    self.log(
                        f"Original-Source UTF-8 Byte-Offset Anchor Proofs: {anchor_matches}/{sampled_proof_count} verified "
                        f"({anchor_recovery_rate*100:.1f}%) [Strict Upstream Source Dataset Matches: {source_corpus_matches}]"
                    )
                    effective_min_anchor_rec = max(min_anchor_rec, 1.000)
                    if anchor_recovery_rate < effective_min_anchor_rec:
                        self.violations.append(
                            f"Anchor recovery rate {anchor_recovery_rate:.4f} < {effective_min_anchor_rec:.3f} "
                            f"(Defect 7: strict source-only anchor verification requires 100% recovery against upstream source dataset)"
                        )

            finally:
                conn.close()

        # Defect 6: Total Hot-State Storage Accounting strictly against frozen policy denominator
        wal_path = db_path.parent / (db_path.name + "-wal")
        shm_path = db_path.parent / (db_path.name + "-shm")
        wal_size_bytes = wal_path.stat().st_size if wal_path.exists() else 0
        shm_size_bytes = shm_path.stat().st_size if shm_path.exists() else 0
        total_hot_db_bytes = db_size_bytes + wal_size_bytes + shm_size_bytes

        raw_text_denom = self.policy.get("storage", {}).get("raw_text_denominator_bytes", 62870136)
        storage_multiplier = round(total_hot_db_bytes / max(1, raw_text_denom), 2)
        self.log(
            f"Total Hot Storage Footprint: {total_hot_db_bytes / (1024*1024):.2f} MB "
            f"(db: {db_size_bytes / (1024*1024):.2f} MB, wal: {wal_size_bytes / (1024*1024):.2f} MB, "
            f"shm: {shm_size_bytes / (1024*1024):.2f} MB, Multiplier: {storage_multiplier:.2f}x against "
            f"frozen policy denominator {raw_text_denom} bytes, Limit: <= {max_storage_mult:.2f}x)"
        )
        if not is_calibration and storage_multiplier > max_storage_mult:
            self.violations.append(
                f"Storage multiplier {storage_multiplier:.2f}x > {max_storage_mult:.2f}x "
                f"(Total hot DB size {total_hot_db_bytes} bytes / frozen denominator {raw_text_denom} bytes)"
            )
        if not is_calibration and total_hot_db_bytes > max_storage_bytes:
            self.violations.append(
                f"Database total hot footprint {total_hot_db_bytes / (1024*1024):.2f} MB > {max_storage_bytes / (1024*1024):.1f} MB ({max_storage_bytes} bytes)"
            )

        # 6. First-Principles Replay Database Audit (Defect 5)
        min_reb_par = self.policy.get("resilience", {}).get("min_rebuild_parity", 1.000)
        replay_db_path = self.candidate_dir / "scale_100k_replay.db"
        if not replay_db_path.exists():
            replay_db_path = self.candidate_dir / "runs" / "scale_100k_replay.db"

        derived_rebuild_parity = 0.0
        replay_db_verified = False
        replay_table_audits: dict[str, Any] = {}
        replay_db_sha256: str | None = None

        if not replay_db_path.exists():
            self.violations.append(
                "Mandatory retained replay database 'scale_100k_replay.db' is missing from candidate bundle. "
                "Candidate verification requires direct SQLite 6-table SHA-256 parity audit and never falls back to JSON."
            )
        else:
            replay_db_sha256 = compute_sha256(replay_db_path)
            self.log(f"Found retained replay database: {replay_db_path} (SHA-256: {replay_db_sha256})")

            src_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            rep_conn = sqlite3.connect(f"file:{replay_db_path}?mode=ro", uri=True)
            try:
                src_conn.execute("PRAGMA query_only = ON;")
                rep_conn.execute("PRAGMA query_only = ON;")

                rep_cur = rep_conn.cursor()
                rep_cur.execute("PRAGMA quick_check;")
                rep_q = rep_cur.fetchone()[0]
                if rep_q != "ok":
                    self.violations.append(f"Replay SQLite PRAGMA quick_check failed: {rep_q}")

                rep_cur.execute("PRAGMA integrity_check;")
                rep_i = rep_cur.fetchone()[0]
                if rep_i != "ok":
                    self.violations.append(f"Replay SQLite PRAGMA integrity_check failed: {rep_i}")

                matching_tables = 0
                for table in verification_tables:
                    s_cnt, s_hash = compute_table_hash(src_conn, table)
                    r_cnt, r_hash = compute_table_hash(rep_conn, table)
                    match = (s_cnt == r_cnt) and (s_hash == r_hash)
                    replay_table_audits[table] = {
                        "source_count": s_cnt,
                        "replay_count": r_cnt,
                        "source_hash": s_hash,
                        "replay_hash": r_hash,
                        "parity_match": match,
                    }
                    if match:
                        matching_tables += 1
                    else:
                        self.violations.append(
                            f"Replay DB table parity mismatch for '{table}': primary (count={s_cnt}, hash={s_hash[:12]}), "
                            f"replay (count={r_cnt}, hash={r_hash[:12]})"
                        )

                derived_rebuild_parity = matching_tables / max(1, len(verification_tables))
                replay_db_verified = (derived_rebuild_parity >= min_reb_par)
                self.log(f"DEBUG: len(verification_tables) is {len(verification_tables)}, tables are {verification_tables}")
                self.log(f"Direct SQLite Replay Parity Audit: {matching_tables}/{len(verification_tables)} tables matched ({derived_rebuild_parity*100:.1f}%)")
            finally:
                src_conn.close()
                rep_conn.close()

        if derived_rebuild_parity < min_reb_par:
            self.violations.append(f"Rebuild parity {derived_rebuild_parity:.4f} < {min_reb_par:.4f}")

        # 7. First-Principles Graph Traversal Telemetry (Defect #5)
        graph_telemetry_path = self.candidate_dir / "runs" / "graph_walk_telemetry.jsonl"
        if not graph_telemetry_path.exists():
            graph_telemetry_path = self.candidate_dir / "graph_walk_telemetry.jsonl"

        max_graph_p95 = self.policy.get("graph", {}).get("max_traversal_p95_ms", 35.0)
        graph_latencies: list[float] = []

        if graph_telemetry_path.exists():
            with open(graph_telemetry_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        g_obj = json.loads(line_str)
                        lat = float(g_obj.get("latency_ms", g_obj.get("traversal_latency_ms", 0.0)))
                        graph_latencies.append(lat)
                    except (json.JSONDecodeError, ValueError):
                        pass

        if graph_latencies:
            graph_percentiles = compute_percentiles(graph_latencies)
            graph_p95_lat = float(graph_percentiles["p95"])
            graph_p50_lat = float(graph_percentiles["p50"])
            graph_p99_lat = float(graph_percentiles["p99"])
            graph_mean_lat = float(graph_percentiles["mean"])
            self.log(
                f"Graph Traversal Latency (from graph_walk_telemetry.jsonl): P95 = {graph_p95_lat:.3f} ms, "
                f"P50 = {graph_p50_lat:.3f} ms, Mean = {graph_mean_lat:.3f} ms ({len(graph_latencies)} walk samples, Limit: <= {max_graph_p95:.1f} ms)"
            )
            if graph_p95_lat > max_graph_p95:
                self.violations.append(
                    f"Graph traversal P95 latency {graph_p95_lat:.3f} ms > {max_graph_p95:.1f} ms (derived directly from graph_walk_telemetry.jsonl)"
                )
        else:
            graph_p95_lat = 0.0
            graph_p50_lat = 0.0
            graph_p99_lat = 0.0
            graph_mean_lat = 0.0
            if not is_calibration:
                self.violations.append("Missing mandatory evidence file or empty telemetry: runs/graph_walk_telemetry.jsonl")

        dossier_graph_p95 = float(dossier.get("metrics", {}).get("promise_4_bounded_economics", {}).get("graph_traversal_p95_latency_ms", 0.0))
        if dossier_graph_p95 > 0:
            self.log(f"Dossier declared graph traversal P95: {dossier_graph_p95:.3f} ms (Verifier independently computed: {graph_p95_lat:.3f} ms)")

        # 8. Ingest Query Manifest Ground Truth Cohorts (Defect #3, #8)
        manifest_cohorts = self.queries_manifest.get("closed_evaluation_cohorts", {})
        manifest_qids_by_lane: dict[str, set[str]] = {lane: set() for lane in CAPABILITY_LANES}
        manifest_queries_by_lane_and_id: dict[tuple[str, str], dict[str, Any]] = {}
        manifest_null_qids: set[str] = set()

        for lane_k, q_list in manifest_cohorts.items():
            canonical_lane = "abstention_suite" if lane_k in ("abstention_suite", "abstention_lane") else lane_k
            if canonical_lane not in manifest_qids_by_lane:
                manifest_qids_by_lane[canonical_lane] = set()
            for q_obj in q_list:
                qid = str(q_obj.get("query_id") or q_obj.get("internal_id") or "")
                if qid:
                    manifest_qids_by_lane[canonical_lane].add(qid)
                    manifest_queries_by_lane_and_id[(canonical_lane, qid)] = q_obj
                    if canonical_lane == "abstention_suite" or q_obj.get("is_null_query") or q_obj.get("expected_abstention"):
                        manifest_null_qids.add(qid)

        # 9. Ingest Raw Telemetry, Blindness Verification & DB Membership (Defects #2, #3, #8, #9)
        raw_queries_path = self.candidate_dir / "runs" / "raw_query_evaluations.jsonl"
        if not raw_queries_path.exists():
            raw_queries_path = self.candidate_dir / "raw_query_evaluations.jsonl"

        abstention_queries_path = self.candidate_dir / "runs" / "abstention_evaluations.jsonl"
        if not abstention_queries_path.exists():
            abstention_queries_path = self.candidate_dir / "abstention_evaluations.jsonl"

        raw_records_by_lane: dict[str, list[dict[str, Any]]] = {lane: [] for lane in CAPABILITY_LANES}
        all_seen_query_records: dict[str, dict[str, Any]] = {}

        def process_telemetry_line(raw_line: str, source_file: str) -> None:
            line_str = raw_line.strip()
            if not line_str:
                return
            r = json.loads(line_str)
            qid = str(r.get("query_id") or r.get("native_query_id") or r.get("internal_id") or "")
            if not qid:
                self.violations.append(f"Query evaluation record missing query_id in {source_file}")
                return

            raw_lane = r.get("lane")
            if (
                raw_lane in ("abstention_suite", "abstention_lane")
                or r.get("query_class") == "null_query"
                or (raw_lane is None and qid in manifest_null_qids)
                or (source_file.endswith("abstention_evaluations.jsonl") and not raw_lane)
            ):
                target_lane = "abstention_suite"
            elif raw_lane in raw_records_by_lane:
                target_lane = raw_lane
            else:
                target_lane = None
                for l_k, q_set in manifest_qids_by_lane.items():
                    if qid in q_set:
                        target_lane = l_k
                        break
                if not target_lane:
                    target_lane = raw_lane or "unknown"

            # Defect 3: Assert candidate operated blindly without leaking qrels or precalculated metrics
            if (
                r.get("gold_ids")
                or r.get("native_gold_doc_ids")
                or r.get("gold_document_ids")
                or "is_null_query" in r
                or "expected_abstention" in r
            ):
                self.violations.append(
                    f"Query evaluation record '{qid}' in lane '{target_lane}' contains leaked ground-truth fields "
                    f"(gold_ids/is_null_query/expected_abstention). Candidate runner must operate blindly without access to qrels."
                )
            if (
                "ndcg_at_10" in r
                or "recall_at_20" in r
                or "complete_coverage_at_20" in r
                or "zero_hallucination_rate" in r
                or "abstention_accuracy" in r
            ):
                self.violations.append(
                    f"Query evaluation record '{qid}' in lane '{target_lane}' contains precalculated metric fields. Verifier holds sole custody of evaluation metrics."
                )

            # Defect 2: Assert that 100% of candidate document IDs exist in SQLite database
            cands_raw = r.get("ranked_candidates") or r.get("retrieved_top20") or []
            cand_ids = extract_candidate_ids(cands_raw)
            missing_from_db = [cid for cid in cand_ids if cid not in self.persisted_doc_ids]
            if missing_from_db:
                self.violations.append(
                    f"Query '{qid}' in lane '{target_lane}' retrieved {len(missing_from_db)} candidate document IDs not present in SQLite database: {missing_from_db[:5]}"
                )

            citations_emitted = r.get("citations_emitted") or []
            for cit in citations_emitted:
                cit_id = str(cit.get("doc_id") or cit.get("id") or cit.get("native_id") or "") if isinstance(cit, dict) else str(cit)
                if cit_id and cit_id not in self.persisted_doc_ids:
                    self.violations.append(
                        f"Query '{qid}' emitted citation '{cit_id}' not present in SQLite database"
                    )

            query_key = (target_lane, qid)
            if query_key in all_seen_query_records:
                prev_r = all_seen_query_records[query_key]
                prev_cands = extract_candidate_ids(prev_r.get("ranked_candidates") or prev_r.get("retrieved_top20") or [])
                curr_cands = extract_candidate_ids(r.get("ranked_candidates") or r.get("retrieved_top20") or [])
                prev_abs = prev_r.get("system_abstained")
                curr_abs = r.get("system_abstained")
                prev_cit = prev_r.get("citations_emitted") or []
                curr_cit = r.get("citations_emitted") or []
                if prev_cands != curr_cands or prev_abs != curr_abs or prev_cit != curr_cit:
                    self.violations.append(
                        f"Contradictory duplicate evaluation records found for query ID '{qid}' in lane '{target_lane}'"
                    )
                else:
                    self.violations.append(
                        f"Duplicate evaluation record found for query ID '{qid}' in lane '{target_lane}'"
                    )
                return

            all_seen_query_records[query_key] = r
            if target_lane not in raw_records_by_lane:
                self.violations.append(f"Query record '{qid}' has unrecognized capability lane '{target_lane}'")
                return

            raw_records_by_lane[target_lane].append(r)

        if raw_queries_path.exists():
            with open(raw_queries_path, "r", encoding="utf-8") as f:
                for line in f:
                    process_telemetry_line(line, str(raw_queries_path))

        if abstention_queries_path.exists():
            with open(abstention_queries_path, "r", encoding="utf-8") as f:
                for line in f:
                    process_telemetry_line(line, str(abstention_queries_path))

        # Check total evaluation cohort count
        total_eval_queries = sum(len(recs) for recs in raw_records_by_lane.values())
        null_eval_count = len(raw_records_by_lane["abstention_suite"])
        answerable_eval_count = total_eval_queries - null_eval_count

        self.log(
            f"Candidate Evaluated Queries: {total_eval_queries} total ({null_eval_count} null, {answerable_eval_count} answerable)"
        )

        # Calibration Determination
        is_calibration = (doc_count_D < required_D)

        # Scale Gate: Full candidate requires exact document count D
        if not is_calibration and doc_count_D != required_D:
            self.violations.append(f"Full candidate document count D={doc_count_D} != {required_D}")

        if not is_calibration and total_eval_queries < expected_total_queries:
            self.violations.append(
                f"Full 100K candidate evaluated only {total_eval_queries} queries, expected all {expected_total_queries} closed queries without truncation"
            )

        # 10. Strict Top-20 Ranking Verification & Exact Query ID Set Equality (Defect #8)
        for lane_name in CAPABILITY_LANES:
            records = raw_records_by_lane[lane_name]
            expected_lane_qids = manifest_qids_by_lane[lane_name]
            telemetry_lane_qids = {
                str(r.get("query_id") or r.get("native_query_id") or r.get("internal_id"))
                for r in records
            }

            # Check unauthorized query IDs
            unauthorized = telemetry_lane_qids - expected_lane_qids
            if unauthorized:
                self.violations.append(
                    f"Lane '{lane_name}' contains {len(unauthorized)} unauthorized query IDs not present in queries_manifest: {sorted(list(unauthorized))[:5]}"
                )

            # Full Candidate Exact Set Equality Mandate
            if not is_calibration:
                missing = expected_lane_qids - telemetry_lane_qids
                if missing:
                    self.violations.append(
                        f"Lane '{lane_name}' missing {len(missing)} query IDs required by queries_manifest: {sorted(list(missing))[:5]}"
                    )
                if telemetry_lane_qids != expected_lane_qids:
                    self.violations.append(
                        f"Query count/set mismatch for lane '{lane_name}': candidate evaluated {len(telemetry_lane_qids)}, manifest requires {len(expected_lane_qids)}"
                    )

            # Strict 20-entry ranking verification for answerable lanes (no retrieved_top3 fallback)
            if lane_name != "abstention_suite":
                for r in records:
                    qid = str(r.get("query_id") or r.get("native_query_id") or r.get("internal_id"))
                    ranked_cands = r.get("ranked_candidates") or r.get("retrieved_top20")
                    if ranked_cands is None or not isinstance(ranked_cands, list) or len(ranked_cands) != 20:
                        self.violations.append(
                            f"Query '{qid}' in lane '{lane_name}' does not contain exactly 20 entries in 'ranked_candidates' or 'retrieved_top20' (found {len(ranked_cands) if isinstance(ranked_cands, list) else 0})"
                        )
                    elif any(isinstance(c, dict) and "rank" in c for c in ranked_cands):
                        ranks = [c.get("rank") for c in ranked_cands if isinstance(c, dict) and "rank" in c]
                        if ranks and ranks != list(range(1, 21)):
                            self.violations.append(
                                f"Query '{qid}' in lane '{lane_name}' has invalid candidate rank sequence: {ranks[:5]}..."
                            )

        # 11. Metric Recomputation & First-Principles Quality Enforcement (Defects #3, #8, #9, #10)
        recomputed_metrics: dict[str, dict[str, Any]] = {}
        dossier_ret = dossier.get("metrics", {}).get("promise_3_retrieval_quality", {})
        policy_ret = self.policy.get("retrieval", {})

        for lane_name in ["direct_lookup", "domain_semantic", "semantic_qa", "multi_hop_reasoning"]:
            records = raw_records_by_lane[lane_name]
            if not records:
                self.violations.append(f"Missing raw query evaluation records for lane: {lane_name}")
                continue

            ndcg_list: list[float] = []
            recall_list: list[float] = []
            coverage_list: list[float] = []
            latency_list: list[float] = []

            for r in records:
                qid = str(r.get("query_id") or r.get("native_query_id") or r.get("internal_id") or "")
                manifest_q = manifest_queries_by_lane_and_id.get((lane_name, qid), {})
                gold_ids = extract_gold_ids(manifest_q.get("gold_ids") or [])

                q_lat = float(r.get("latency_ms", 0.0))
                latency_list.append(q_lat)

                candidates_raw = r.get("ranked_candidates") or r.get("retrieved_top20") or []
                candidates = extract_candidate_ids(candidates_raw)

                # Strict Ranking & Unique Candidate Verification
                if len(candidates[:20]) != 20:
                    self.violations.append(f"Query '{qid}' does not contain exactly 20 candidates in top-20 ranking.")
                elif len(set(candidates[:20])) != 20:
                    self.violations.append(f"Query '{qid}' contains duplicate candidate IDs in top-20 ranking: {candidates[:20]}")

                # Answerable Query Citation Validation (Defect #9)
                citations_emitted = r.get("citations_emitted") or []
                top20_set = set(candidates[:20])
                for cit in citations_emitted:
                    if isinstance(cit, dict):
                        cit_id = str(cit.get("doc_id") or cit.get("id") or cit.get("native_id") or "")
                    else:
                        cit_id = str(cit)
                    if cit_id and cit_id not in top20_set:
                        self.violations.append(
                            f"Query '{qid}' emitted citation '{cit_id}' not found in top-20 retrieved candidates"
                        )

                if gold_ids:
                    ndcg_val, rec_val, cov_val = compute_query_ndcg10_recall20_coverage20(candidates_raw, gold_ids)
                    ndcg_list.append(ndcg_val)
                    recall_list.append(rec_val)
                    coverage_list.append(cov_val if lane_name == "multi_hop_reasoning" else rec_val)
                else:
                    ndcg_list.append(0.0)
                    recall_list.append(0.0)
                    coverage_list.append(0.0)

            p_lat = compute_percentiles(latency_list)
            mean_ndcg = round(sum(ndcg_list) / max(1, len(ndcg_list)), 4) if ndcg_list else 0.0
            mean_rec = round(sum(recall_list) / max(1, len(recall_list)), 4) if recall_list else 0.0
            mean_cov = round(sum(coverage_list) / max(1, len(coverage_list)), 4) if coverage_list else 0.0

            stat_cfg = self.policy.get("statistical_methods", {})
            b_iter = int(stat_cfg.get("bootstrap_resamples", 10000))
            b_conf = float(stat_cfg.get("bootstrap_ci_level", 0.95))
            b_seed = int(stat_cfg.get("bootstrap_seed", 42))

            # Bootstrap Confidence Intervals (Defect #10)
            _, ndcg_ci_low, ndcg_ci_high = compute_bootstrap_ci(ndcg_list, iterations=b_iter, confidence_level=b_conf, seed=b_seed)
            _, rec_ci_low, rec_ci_high = compute_bootstrap_ci(recall_list, iterations=b_iter, confidence_level=b_conf, seed=b_seed)

            recomputed_metrics[lane_name] = {
                "ndcg_at_10": mean_ndcg,
                "recall_at_20": mean_rec,
                "complete_coverage_at_20": mean_rec if lane_name != "multi_hop_reasoning" else mean_cov,
                "p95_ms": round(p_lat["p95"], 3),
                "queries_evaluated": len(records),
                "bootstrap_ci_95": {
                    "ndcg_at_10": {
                        "mean": mean_ndcg,
                        "ci_lower": round(ndcg_ci_low, 4),
                        "ci_upper": round(ndcg_ci_high, 4),
                    },
                    "recall_at_20": {
                        "mean": mean_rec,
                        "ci_lower": round(rec_ci_low, 4),
                        "ci_upper": round(rec_ci_high, 4),
                    },
                    "iterations": b_iter,
                    "seed": b_seed,
                },
            }

            self.log(
                f"Recomputed {lane_name:20s}: nDCG@10={mean_ndcg:.4f} [95% CI: {ndcg_ci_low:.4f}-{ndcg_ci_high:.4f}] | "
                f"Recall@20={mean_rec:.4f} [95% CI: {rec_ci_low:.4f}-{rec_ci_high:.4f}] | P95={p_lat['p95']:.3f} ms ({len(records)} queries)"
            )

            # Compare against dossier (Fail closed if mismatch > 0.0001)
            dossier_lane = dossier_ret.get(lane_name, {})
            if "ndcg_at_10" in dossier_lane:
                d_ndcg = float(dossier_lane["ndcg_at_10"])
                if abs(mean_ndcg - d_ndcg) > 0.0001:
                    self.violations.append(
                        f"Dossier metric mismatch for {lane_name}.ndcg_at_10: dossier={d_ndcg:.4f}, recomputed={mean_ndcg:.4f} (diff: {abs(mean_ndcg - d_ndcg):.5f} > 0.0001)"
                    )
            if "recall_at_20" in dossier_lane:
                d_rec = float(dossier_lane["recall_at_20"])
                if abs(mean_rec - d_rec) > 0.0001:
                    self.violations.append(
                        f"Dossier metric mismatch for {lane_name}.recall_at_20: dossier={d_rec:.4f}, recomputed={mean_rec:.4f} (diff: {abs(mean_rec - d_rec):.5f} > 0.0001)"
                    )
            if "complete_coverage_at_20" in dossier_lane and lane_name == "multi_hop_reasoning":
                d_cov = float(dossier_lane["complete_coverage_at_20"])
                if abs(mean_cov - d_cov) > 0.0001:
                    self.violations.append(
                        f"Dossier metric mismatch for {lane_name}.complete_coverage_at_20: dossier={d_cov:.4f}, recomputed={mean_cov:.4f}"
                    )

            # Enforce Policy Retrieval Thresholds (Certifying candidate runs only)
            lane_policy = policy_ret.get(lane_name, {})
            if lane_policy and not is_calibration:
                min_ndcg = lane_policy.get("min_ndcg10")
                if min_ndcg is not None and mean_ndcg < min_ndcg:
                    self.violations.append(f"{lane_name} nDCG@10 {mean_ndcg:.4f} < {min_ndcg:.4f}")

                min_rec = lane_policy.get("min_recall20")
                if min_rec is not None and mean_rec < min_rec:
                    self.violations.append(f"{lane_name} Recall@20 {mean_rec:.4f} < {min_rec:.4f}")

                min_cov = lane_policy.get("min_coverage20") or lane_policy.get("min_coverage_at_20")
                effective_cov = mean_cov if lane_name == "multi_hop_reasoning" else mean_rec
                if min_cov is not None and effective_cov < min_cov:
                    self.violations.append(f"{lane_name} Coverage@20 {effective_cov:.4f} < {min_cov:.4f}")

                max_lat = lane_policy.get("max_p95_ms")
                if max_lat is not None and p_lat["p95"] > max_lat:
                    self.violations.append(f"{lane_name} P95 latency {p_lat['p95']:.3f} ms > {max_lat:.1f} ms")

        # 12. First-Principles Abstention & Zero Hallucination Derivation (Defect #9)
        null_records = raw_records_by_lane["abstention_suite"]
        total_null_eval = len(null_records)
        hallucinations = 0
        correct_abstentions = 0

        for r in null_records:
            citations_emitted = r.get("citations_emitted") or []
            system_abstained = (r.get("system_abstained") is True)

            # Derivation from first principles: DO NOT TRUST candidate-authored flags
            is_hallucination = False
            if len(citations_emitted) > 0:
                is_hallucination = True
            if not system_abstained:
                is_hallucination = True

            if is_hallucination:
                hallucinations += 1

            if system_abstained and len(citations_emitted) == 0:
                correct_abstentions += 1

        zero_hallucination_rate = 1.0 if (hallucinations == 0 and total_null_eval > 0) else (0.0 if total_null_eval > 0 else 1.0)
        abstention_accuracy = round(correct_abstentions / max(1, total_null_eval), 4) if total_null_eval > 0 else 1.0

        recomputed_metrics["abstention_lane"] = {
            "unanswerable_queries_evaluated": total_null_eval,
            "zero_hallucination_rate": zero_hallucination_rate,
            "abstention_accuracy": abstention_accuracy,
        }

        self.log(
            f"Recomputed abstention_lane     : Accuracy={abstention_accuracy:.4f} | Zero Hallucination={zero_hallucination_rate:.4f} ({total_null_eval} null queries)"
        )

        dossier_abs = dossier_ret.get("abstention_lane", {})
        if "zero_hallucination_rate" in dossier_abs:
            d_zhr = float(dossier_abs["zero_hallucination_rate"])
            if abs(zero_hallucination_rate - d_zhr) > 0.0001:
                self.violations.append(
                    f"Dossier metric mismatch for abstention_lane.zero_hallucination_rate: dossier={d_zhr:.4f}, recomputed={zero_hallucination_rate:.4f}"
                )
        if "abstention_accuracy" in dossier_abs:
            d_acc = float(dossier_abs["abstention_accuracy"])
            if abs(abstention_accuracy - d_acc) > 0.0001:
                self.violations.append(
                    f"Dossier metric mismatch for abstention_lane.abstention_accuracy: dossier={d_acc:.4f}, recomputed={abstention_accuracy:.4f}"
                )
        if "unanswerable_queries_evaluated" in dossier_abs:
            d_cnt = int(dossier_abs["unanswerable_queries_evaluated"])
            if total_null_eval != d_cnt and not is_calibration:
                self.violations.append(
                    f"Dossier count mismatch for abstention_lane.unanswerable_queries_evaluated: dossier={d_cnt}, recomputed={total_null_eval}"
                )

        # Enforce Policy Abstention Thresholds
        abstention_policy = self.policy.get("abstention", {})
        min_zhr = abstention_policy.get("min_zero_hallucination_rate", 1.000)
        min_abs_acc = abstention_policy.get("min_abstention_accuracy", 0.900)
        req_null_q = abstention_policy.get("required_null_queries", 301)

        if zero_hallucination_rate < min_zhr:
            self.violations.append(f"Zero hallucination rate {zero_hallucination_rate:.4f} < {min_zhr:.4f}")
        if not is_calibration and total_null_eval < req_null_q:
            self.violations.append(f"Unanswerable null queries evaluated {total_null_eval} < {req_null_q}")
        if abstention_accuracy < min_abs_acc:
            self.violations.append(f"Abstention accuracy {abstention_accuracy:.4f} < {min_abs_acc:.4f}")

        # 13. Durability Audit Trace & Invariant Derivation (Defect #10)
        dur_policy = self.policy.get("durability", {})
        min_atom_ret = dur_policy.get("min_atom_retention", 1.000)
        max_h_drift = dur_policy.get("max_hash_drift", 0.000)
        max_rep_eras = dur_policy.get("max_repeat_erasure_delta", 0)

        atom_retention = 0.0
        hash_drift = 1.0
        repeat_erasure_delta = 999

        dur_trace_path = self.candidate_dir / "runs" / "durability_audit_trace.json"
        if not dur_trace_path.exists():
            dur_trace_path = self.candidate_dir / "durability_audit_trace.json"

        if not dur_trace_path.exists():
            self.violations.append("Missing mandatory evidence file: runs/durability_audit_trace.json")
        else:
            with open(dur_trace_path, "r", encoding="utf-8") as f:
                dur_data = json.load(f)

            atom_retention = float(dur_data.get("source_atom_retention", 1.0))
            hash_drift = float(dur_data.get("hash_drift_rate", dur_data.get("content_hash_drift", 0.0)))
            repeat_erasure_delta = int(dur_data.get("repeat_erasure_delta_writes", 0))

            if "total_atoms_in_db" in dur_data and total_atoms > 0 and dur_data["total_atoms_in_db"] != total_atoms:
                self.violations.append(
                    f"Durability trace total atoms ({dur_data['total_atoms_in_db']}) != SQLite node_versions ({total_atoms})"
                )
            if "total_documents_in_db" in dur_data and total_events > 0 and dur_data["total_documents_in_db"] != total_events:
                self.violations.append(
                    f"Durability trace total documents ({dur_data['total_documents_in_db']}) != SQLite events ({total_events})"
                )

            if atom_retention < min_atom_ret:
                self.violations.append(f"Atom retention {atom_retention:.4f} < {min_atom_ret:.4f}")
            if hash_drift > max_h_drift:
                self.violations.append(f"Hash drift {hash_drift:.4f} > {max_h_drift:.4f}")
            if repeat_erasure_delta > max_rep_eras:
                self.violations.append(f"Repeat erasure delta {repeat_erasure_delta} != {max_rep_eras}")

        # RECOVERY & INCREMENTAL RESUME ARTIFACT AUDIT (Audit Finding 3)
        restart_rec_path = self.candidate_dir / "runs" / "restart_recovery_receipt.json"
        if not restart_rec_path.exists():
            restart_rec_path = self.candidate_dir / "restart_recovery_receipt.json"

        if not restart_rec_path.exists():
            self.violations.append("Missing mandatory evidence file: runs/restart_recovery_receipt.json")
        else:
            with open(restart_rec_path, "r", encoding="utf-8") as f:
                rec_data = json.load(f)
                status = rec_data.get("status")
                integrity = rec_data.get("integrity_check")
                if status not in ("PASS", "RECOVERY_VERIFIED"):
                    self.violations.append(f"Restart recovery receipt status '{status}' is invalid (expected PASS or RECOVERY_VERIFIED)")
                if integrity != "ok":
                    self.violations.append(f"Restart recovery receipt integrity_check '{integrity}' is invalid (expected 'ok')")
                if "recovery_timestamp" not in rec_data and "timestamp" not in rec_data and "recovery_time" not in rec_data:
                    self.violations.append("Restart recovery receipt missing valid recovery timestamps")

        inc_res_path = self.candidate_dir / "runs" / "incremental_resume_receipt.json"
        if not inc_res_path.exists():
            inc_res_path = self.candidate_dir / "incremental_resume_receipt.json"

        if not inc_res_path.exists():
            self.violations.append("Missing mandatory evidence file: runs/incremental_resume_receipt.json")
        else:
            with open(inc_res_path, "r", encoding="utf-8") as f:
                res_data = json.load(f)
                status = res_data.get("status")
                dupes = res_data.get("duplicate_events", res_data.get("duplicate_events_accepted", 0))
                watermarks_continuous = res_data.get("watermarks_continuous", True if (res_data.get("final_watermark", 0) > res_data.get("initial_watermark", 0)) else False)
                if status not in ("PASS", "RESUME_VERIFIED"):
                    self.violations.append(f"Incremental resume receipt status '{status}' is invalid (expected PASS or RESUME_VERIFIED)")
                if dupes != 0:
                    self.violations.append(f"Incremental resume receipt indicates {dupes} duplicate events (expected 0)")
                if not watermarks_continuous:
                    self.violations.append("Incremental resume receipt indicates watermarks are not continuous")

        # 14. Calibration Verdict & Standard Demotion (Defect #7)
        is_verified = (len(self.violations) == 0)
        if is_verified:
            if is_calibration:
                verdict = VERDICT_DIAGNOSTIC
                target_standard = STANDARD_DIAGNOSTIC
            else:
                verdict = VERDICT_PASS
                target_standard = STANDARD_LEVEL1
        else:
            verdict = VERDICT_FAILED
            target_standard = STANDARD_DIAGNOSTIC if is_calibration else STANDARD_LEVEL1

        # 15. Content-Addressed Merkle Digest Token Binding (Defect #4, #10)
        attestation_id = f"attest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        digest_token_payload = f"{attestation_id}:{self.candidate_dir}:{merkle_root}:{self.policy_sha256}:{db_sha256}:{verdict}"
        merkle_digest_token = hashlib.sha256(digest_token_payload.encode("utf-8")).hexdigest()

        receipt: dict[str, Any] = {
            "attestation_id": attestation_id,
            "verification_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "verifier_role": "Independent Verifier (Wave R2.4 / Level 1 Standard)",
            "target_standard": target_standard,
            "is_calibration": is_calibration,
            "calibration_notice": (
                "Calibration / diagnostic run (D < 100,000 or evaluated queries < 7,457) is non-certifying "
                "and cannot pass Gate C2 Level 1 standard (DEC-P-005b-LEVEL1). Assigned target standard is NONE_DIAGNOSTIC_ONLY."
                if is_calibration else None
            ),
            "policy_file_path": str(self.policy_path),
            "policy_sha256": self.policy_sha256,
            "queries_manifest_path": str(self.queries_manifest_path),
            "queries_manifest_sha256": self.queries_manifest_sha256,
            "blind_queries_sha256": CANONICAL_BLIND_QUERIES_SHA256,
            "corpus_manifest_path": str(self.corpus_manifest_path) if self.corpus_manifest_path.exists() else None,
            "corpus_manifest_sha256": self.corpus_manifest_sha256 if self.corpus_manifest_path.exists() else None,
            "candidate_directory": str(self.candidate_dir),
            "candidate_database_file": str(db_path),
            "candidate_database_sha256": db_sha256,
            "candidate_replay_database_file": str(replay_db_path) if replay_db_path.exists() else None,
            "candidate_replay_database_sha256": replay_db_sha256,
            "candidate_evidence_merkle_root": merkle_root,
            "dossier_sha256": compute_sha256(dossier_path),
            "candidate_manifest_sha256": compute_sha256(candidate_manifest_path) if candidate_manifest_path.exists() else None,
            "cryptographic_identity_bindings": {
                "git_commit": candidate_manifest.get("git_commit"),
                "git_tree_hash": candidate_manifest.get("git_tree_hash"),
                "git_clean": candidate_manifest.get("git_clean"),
                "runner_hash": cand_runner_hash or auth_runner_sha,
                "verifier_hash": cand_verifier_hash or auth_verifier_sha,
                "schema_hash": cand_schema_hash or auth_schema_sha,
                "policy_hash": self.policy_sha256,
                "blind_queries_sha256": candidate_manifest.get("blind_queries_sha256") or CANONICAL_BLIND_QUERIES_SHA256,
                "command_line": candidate_manifest.get("command_line"),
            },
            "evidence_files_audited": evidence_files_audited,
            "checksums_audit": {
                "total_files_declared": len(checksums),
                "total_files_verified": verified_checksums,
                "all_checksums_match": (verified_checksums == len(checksums)),
            },
            "sqlite_database_audit": {
                "integrity_check": "ok",
                "table_row_counts": table_counts,
                "events_count": events_cnt if db_path.exists() else 0,
                "events_distinct_payload_hash": events_distinct_payload_hash,
                "ingestions_count": ing_cnt if db_path.exists() else 0,
                "ingestions_distinct_doc_id": ingestions_distinct_doc_id,
                "ingestions_distinct_content_hash": ingestions_distinct_content_hash,
                "persisted_distinct_document_count": len(self.persisted_doc_ids),
                "document_uniqueness_verified": (
                    events_distinct_payload_hash == (required_D if not is_calibration else events_cnt)
                    and ingestions_distinct_doc_id == (required_D if not is_calibration else ing_cnt)
                    and ingestions_distinct_content_hash == (required_D if not is_calibration else ing_cnt)
                ),
                "persisted_max_degree_sql": persisted_max_degree,
                "max_degree_bound_verified": (persisted_max_degree <= max_stored_deg),
                "sampled_slice_anchor_proofs": sampled_proof_count,
                "anchor_recovery_rate": anchor_recovery_rate,
                "storage_footprint_bytes": total_hot_db_bytes,
                "main_db_bytes": db_size_bytes,
                "wal_bytes": wal_size_bytes,
                "shm_bytes": shm_size_bytes,
                "frozen_denominator_bytes": raw_text_denom,
                "storage_multiplier": storage_multiplier,
                "storage_multiplier_verified": (storage_multiplier <= max_storage_mult or is_calibration),
            },
            "host_environment_audit": {
                "peak_rss_gb": effective_peak_rss_gb,
                "current_rss_gb": effective_current_rss_gb,
                "peak_rss_verified": (effective_peak_rss_gb <= max_peak_ram_gb),
            },
            "graph_telemetry_audit": {
                "walk_samples_evaluated": len(graph_latencies),
                "traversal_p50_latency_ms": graph_p50_lat,
                "traversal_p95_latency_ms": graph_p95_lat,
                "traversal_p99_latency_ms": graph_p99_lat,
                "traversal_mean_latency_ms": graph_mean_lat,
                "graph_p95_verified": (graph_p95_lat <= max_graph_p95),
            },
            "recomputed_metrics_audit": {
                "recomputed_metrics": recomputed_metrics,
                "all_metrics_match_dossier": not any("Dossier metric mismatch" in v for v in self.violations),
            },
            "retrieval_and_abstention_audit": {
                "unanswerable_null_queries_evaluated": total_null_eval,
                "zero_hallucination_rate": zero_hallucination_rate,
                "abstention_accuracy": abstention_accuracy,
                "abstention_verified": (
                    zero_hallucination_rate >= min_zhr
                    and abstention_accuracy >= min_abs_acc
                    and (total_null_eval >= req_null_q or is_calibration)
                ),
                "is_calibration": is_calibration,
            },
            "resilience_audit": {
                "rebuild_parity": derived_rebuild_parity,
                "parity_verified": (derived_rebuild_parity >= min_reb_par),
                "replay_database_verified": replay_db_verified,
                "table_parity_audit": replay_table_audits,
            },
            "durability_audit": {
                "atom_retention": atom_retention,
                "hash_drift": hash_drift,
                "repeat_erasure_delta": repeat_erasure_delta,
                "durability_verified": (
                    atom_retention >= min_atom_ret
                    and hash_drift <= max_h_drift
                    and repeat_erasure_delta <= max_rep_eras
                ),
            },
            "verification_verdict": verdict,
            "violations_found": self.violations,
            "attestation_token_type": "Content-Addressed Merkle Digest Token",
            "merkle_digest_token": merkle_digest_token,
        }

        self.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        with open(self.receipt_out, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2)

        self.log(f"Attestation Receipt written to: {self.receipt_out}")
        self.log(f"Verification Verdict: {verdict} (Standard: {target_standard})")

        if not is_verified:
            self.log(f"Violations Found ({len(self.violations)}):")
            for v in self.violations:
                self.log(f"  [FAIL] {v}")

        return receipt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trace 100K Scale Gate Standalone Independent Candidate Verifier (Wave R2.4)"
    )
    parser.add_argument(
        "--candidate-dir",
        type=Path,
        required=True,
        help="Path to sealed candidate output directory",
    )
    parser.add_argument(
        "--receipt-out",
        type=Path,
        default=None,
        help="Path to write signed attestation receipt JSON",
    )
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=None,
        help="Path to dynamic scale_policy.lock.json lockfile",
    )
    parser.add_argument(
        "--queries-manifest",
        type=Path,
        default=None,
        help="Path to frozen queries manifest JSON",
    )
    parser.add_argument(
        "--corpus-manifest",
        type=Path,
        default=None,
        help="Path to frozen corpus manifest JSON",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Path to root directory containing raw dataset corpus files",
    )
    args = parser.parse_args()

    try:
        verifier = CandidateVerifier(
            candidate_dir=args.candidate_dir,
            receipt_out=args.receipt_out,
            queries_manifest_path=args.queries_manifest,
            policy_path=args.policy_file,
            corpus_manifest_path=args.corpus_manifest,
            data_root=args.data_root,
        )
        receipt = verifier.verify_all()
        if len(verifier.violations) > 0:
            sys.exit(EXIT_FAILED)
        sys.exit(EXIT_PASS)
    except (FileNotFoundError, ValueError, sqlite3.Error) as err:
        safe_print(f"[VERIFIER] [ERROR] Operational error: {err}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    except Exception as err:
        safe_print(f"[VERIFIER] [ERROR] Unexpected verifier exception: {err}", file=sys.stderr)
        sys.exit(EXIT_ERROR)


if __name__ == "__main__":
    main()
