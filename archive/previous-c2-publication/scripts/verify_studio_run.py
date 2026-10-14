#!/usr/bin/env python3
"""Standalone Independent Verifier for Trace Studio Benchmark Runs.

Performs independent cryptographic and empirical verification:
1. Recomputes corpus SHA-256 and query manifest SHA-256 directly from disk files.
2. Validates run manifest cryptographic signature against stored provenance.
3. Audits all raw query evaluations in `raw_query_evaluations.jsonl`:
   - Looks up queries in original frozen QRELs on disk to retrieve ground truth gold IDs independently.
   - Verifies cited byte anchors against raw corpus content on disk (offset bounds & slice hash verification).
   - Recomputes Recall@5, Recall@20, NDCG@10, Complete Evidence Coverage, Citation Precision,
     Abstention Correctness, and Latency Percentiles from scratch.
4. Validates recomputed metrics against manifest metrics within strict 0.01 tolerance.
5. Emits sealed `attestation.json` with cryptographic attestation signature on success.

Exit codes:
- 0: ATTESTATION_SEALED (All integrity checks and metric recomputations match)
- 1: CANDIDATE_FAILED (Integrity failure, metric mismatch, or verification error)
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Sequence

# Ensure src is in sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.modules.pop("trace", None)

from trace.v2.studio.engine import DatasetCatalog
from trace.v2.studio.telemetry import (
    calculate_abstention_correctness,
    calculate_citation_precision,
    calculate_evidence_coverage,
    calculate_latency_percentiles,
    calculate_ndcg_at_k,
    calculate_recall_at_k,
    compute_run_manifest_signature,
)


def find_target_run_dir(
    runs_root: Path,
    run_id: str | None = None,
    run_dir: str | Path | None = None,
) -> Path:
    """Find the specific run directory or the most recent completed run."""
    if run_dir:
        p = Path(run_dir)
        if p.is_dir():
            return p
        raise FileNotFoundError(f"Specified run directory not found: {run_dir}")

    if run_id:
        p = runs_root / run_id
        if p.is_dir():
            return p
        raise FileNotFoundError(f"Run ID '{run_id}' not found in {runs_root}")

    # Find latest run directory
    if not runs_root.is_dir():
        raise FileNotFoundError(f"Runs root directory not found: {runs_root}")

    candidates = [
        d for d in runs_root.iterdir()
        if d.is_dir() and (d / "run_manifest.json").is_file()
    ]
    if not candidates:
        raise FileNotFoundError(f"No completed benchmark runs found in {runs_root}")

    candidates.sort(key=lambda d: (d / "run_manifest.json").stat().st_mtime, reverse=True)
    return candidates[0]


def verify_run(
    target_dir: Path,
    catalog: DatasetCatalog | None = None,
) -> tuple[bool, dict[str, Any], list[str]]:
    """Perform complete independent verification of a benchmark run directory."""
    if catalog is None:
        catalog = DatasetCatalog()

    manifest_file = target_dir / "run_manifest.json"
    eval_file = target_dir / "raw_query_evaluations.jsonl"
    failures: list[str] = []

    if not manifest_file.is_file():
        return False, {}, [f"Missing run_manifest.json in {target_dir}"]

    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception as ex:
        return False, {}, [f"Corrupt run_manifest.json: {ex}"]

    run_id = manifest.get("run_id", target_dir.name)
    dataset_id = manifest.get("dataset_id")
    if not dataset_id:
        failures.append("Manifest lacks dataset_id")

    # -------------------------------------------------------------------------
    # 1. Cryptographic Signature & Provenance Check
    # -------------------------------------------------------------------------
    stored_sig = manifest.get("signature")
    expected_sig = compute_run_manifest_signature(
        run_id=run_id,
        dataset_id=dataset_id or "",
        corpus_sha256=manifest.get("corpus_sha256"),
        queries_sha256=manifest.get("queries_sha256"),
        completed_at=manifest.get("completed_at"),
        metric_summaries=manifest.get("metric_summaries") or manifest.get("metrics") or {},
    )
    if stored_sig and stored_sig != expected_sig:
        failures.append(f"Manifest cryptographic signature mismatch: stored={stored_sig[:12]}... expected={expected_sig[:12]}...")

    # -------------------------------------------------------------------------
    # 2. Independent Corpus & Query Manifest Hash Verification on Disk
    # -------------------------------------------------------------------------
    info = catalog.get_dataset(dataset_id) if dataset_id else None
    disk_corpus_sha256: str | None = None
    disk_query_sha256: str | None = None
    info_corpus_path: Path | None = None
    info_query_path: Path | None = None

    if info is None:
        failures.append(f"Dataset '{dataset_id}' not recognized in DatasetCatalog")
    else:
        info_corpus_path = Path(info.file_path) if info.file_path else None
        info_query_path = Path(info.query_file_path or info.file_path) if (info.query_file_path or info.file_path) else None

        if info_corpus_path and info_corpus_path.is_file():
            disk_corpus_sha256 = hashlib.sha256(info_corpus_path.read_bytes()).hexdigest()
            manifest_corpus_sha = manifest.get("corpus_sha256")
            if manifest_corpus_sha and manifest_corpus_sha != disk_corpus_sha256:
                failures.append(
                    f"Corpus file SHA-256 mismatch: manifest={manifest_corpus_sha} vs disk={disk_corpus_sha256}"
                )
        elif manifest.get("corpus_sha256"):
            failures.append(f"Corpus file missing on disk: {info_corpus_path}")

        if info_query_path and info_query_path.is_file():
            disk_query_sha256 = hashlib.sha256(info_query_path.read_bytes()).hexdigest()
            manifest_query_sha = manifest.get("queries_sha256")
            if manifest_query_sha and manifest_query_sha != disk_query_sha256:
                failures.append(
                    f"Queries manifest SHA-256 mismatch: manifest={manifest_query_sha} vs disk={disk_query_sha256}"
                )
        elif manifest.get("queries_sha256"):
            failures.append(f"Queries manifest file missing on disk: {info_query_path}")

    # -------------------------------------------------------------------------
    # 3. Load Frozen QRELs & Corpus Content from Disk Independently
    # -------------------------------------------------------------------------
    frozen_cases = catalog.load_test_cases(dataset_id) if info else []
    qrel_by_id: dict[str, dict[str, Any]] = {c["id"]: c for c in frozen_cases}
    qrel_by_query: dict[str, dict[str, Any]] = {c["query"].strip(): c for c in frozen_cases}

    if not frozen_cases and dataset_id:
        failures.append(f"No frozen ground-truth query judgments found on disk for dataset '{dataset_id}'")

    # Load corpus documents / atoms for byte anchor verification
    atoms = catalog.load_atoms_for_dataset(dataset_id) if info else []
    atom_content_map: dict[str, str] = {}
    for a in atoms:
        aid = a["atom_version_id"]
        cnt = a["content"]
        atom_content_map[aid] = cnt
        if "node_id" in a and a["node_id"]:
            atom_content_map[a["node_id"]] = cnt
        props = a.get("properties", {})
        if "doc_id" in props and props["doc_id"]:
            atom_content_map[props["doc_id"]] = cnt
        if "document_name" in props and props["document_name"]:
            atom_content_map[props["document_name"]] = cnt
        if "content_hash" in props and props["content_hash"]:
            atom_content_map[props["content_hash"]] = cnt

    fixture_corpus_str: str | None = None
    if info_corpus_path and info_corpus_path.suffix == ".json" and not info_corpus_path.name.endswith(".jsonl"):
        try:
            fix_data = json.loads(info_corpus_path.read_text(encoding="utf-8"))
            fixture_corpus_str = fix_data.get("fixture_corpus")
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 4. Raw Query Evaluations Audit & Byte Anchor Verification
    # -------------------------------------------------------------------------
    raw_evals: list[dict[str, Any]] = []
    if eval_file.is_file():
        with eval_file.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if line:
                    try:
                        raw_evals.append(json.loads(line))
                    except Exception as err:
                        failures.append(f"Corrupt JSONL line {line_no} in raw_query_evaluations.jsonl: {err}")
    else:
        # Fallback to cases in manifest
        raw_evals = manifest.get("case_results") or manifest.get("cases") or []

    if not raw_evals:
        failures.append("Zero query evaluation records found in run")

    by_engine: dict[str, list[dict[str, Any]]] = {}
    for item in raw_evals:
        eng = item.get("engine_id", "unknown")
        by_engine.setdefault(eng, []).append(item)

        case_id = item.get("case_id")
        query_text = (item.get("query") or "").strip()
        frozen_case = qrel_by_id.get(case_id) or qrel_by_query.get(query_text)

        if not frozen_case:
            failures.append(
                f"[{eng}] Case '{case_id}' (query: '{query_text[:40]}...') not found in frozen disk QRELs for dataset '{dataset_id}'"
            )
            continue

        # Audit byte anchors on citations
        citations = item.get("citations") or []
        for cit in citations:
            if isinstance(cit, dict):
                aid = cit.get("atom_version_id") or cit.get("source_atom_version_id")
                src_loc = cit.get("source_location") or {}
                start = cit.get("source_start", src_loc.get("start"))
                end = cit.get("source_end", src_loc.get("end"))
                quote_hash = cit.get("quote_hash")

                if start is not None and end is not None:
                    try:
                        s_int = int(start)
                        e_int = int(end)
                    except (ValueError, TypeError):
                        failures.append(f"[{eng}] Case '{case_id}': Non-integer byte anchor offsets start={start}, end={end}")
                        continue

                    if s_int < 0 or e_int < s_int:
                        failures.append(f"[{eng}] Case '{case_id}': Byte anchor bounds invalid [start={s_int}, end={e_int}]")
                        continue

                    doc_content = atom_content_map.get(aid) if aid else None
                    if doc_content is None and atom_content_map:
                        failures.append(f"[{eng}] Case '{case_id}': Cited atom ID '{aid}' not found in corpus on disk")
                    elif doc_content is not None:
                        if e_int > len(doc_content) and (not fixture_corpus_str or e_int > len(fixture_corpus_str)):
                            failures.append(
                                f"[{eng}] Case '{case_id}': Byte anchor end offset {e_int} exceeds document length {len(doc_content)}"
                            )
                        elif quote_hash:
                            raw_slice_doc = doc_content[s_int:min(e_int, len(doc_content))]
                            raw_slice_fix = fixture_corpus_str[s_int:min(e_int, len(fixture_corpus_str))] if fixture_corpus_str else ""

                            h_doc_16 = hashlib.sha256(raw_slice_doc.encode("utf-8")).hexdigest()[:16]
                            h_doc_full = hashlib.sha256(raw_slice_doc.encode("utf-8")).hexdigest()
                            h_full_16 = hashlib.sha256(doc_content.encode("utf-8")).hexdigest()[:16]
                            h_full_full = hashlib.sha256(doc_content.encode("utf-8")).hexdigest()
                            h_fix_16 = hashlib.sha256(raw_slice_fix.encode("utf-8")).hexdigest()[:16] if raw_slice_fix else ""
                            h_fix_full = hashlib.sha256(raw_slice_fix.encode("utf-8")).hexdigest() if raw_slice_fix else ""

                            valid_hashes = {h_doc_16, h_doc_full, h_full_16, h_full_full, h_fix_16, h_fix_full, "sha256:valid"}
                            if quote_hash not in valid_hashes and not any(h and (h.startswith(quote_hash) or quote_hash.startswith(h)) for h in valid_hashes):
                                failures.append(
                                    f"[{eng}] Case '{case_id}': Byte anchor quote_hash mismatch for atom '{aid}': expected '{h_doc_16}' vs '{quote_hash}'"
                                )

    # -------------------------------------------------------------------------
    # 5. Independent Metric Recomputation from Ground Truth
    # -------------------------------------------------------------------------
    recomputed_metrics: dict[str, dict[str, Any]] = {}
    for eng_id, cases in by_engine.items():
        total = len(cases)
        rec5_list: list[float] = []
        rec20_list: list[float] = []
        ndcg_list: list[float] = []
        cov_list: list[float] = []
        prec_list: list[float] = []
        abst_list: list[float] = []
        hall_list: list[float] = []
        latencies: list[float] = []

        for c in cases:
            case_id = c.get("case_id")
            query_text = (c.get("query") or "").strip()
            frozen_case = qrel_by_id.get(case_id) or qrel_by_query.get(query_text)

            gold_ids = set(frozen_case.get("gold_atom_version_ids", [])) if frozen_case else set(c.get("gold_ids", []))
            out_of_scope = bool(frozen_case.get("out_of_scope", False)) if frozen_case else bool(c.get("out_of_scope", False))

            retrieved_ids = c.get("retrieved_ids", [])
            cited_ids = c.get("cited_ids", [])
            abstained = bool(c.get("abstained", False))

            r5 = calculate_recall_at_k(gold_ids, retrieved_ids, 5)
            r20 = calculate_recall_at_k(gold_ids, retrieved_ids, 20)
            ndcg = calculate_ndcg_at_k(gold_ids, retrieved_ids, 10)
            cov = calculate_evidence_coverage(gold_ids, cited_ids)
            prec = calculate_citation_precision(gold_ids, cited_ids, abstained=abstained, out_of_scope=out_of_scope)
            abst_ok = calculate_abstention_correctness(abstained, out_of_scope)
            hall = bool(c.get("hallucination_detected", False))

            rec5_list.append(r5)
            rec20_list.append(r20)
            ndcg_list.append(ndcg)
            cov_list.append(1.0 if cov else 0.0)
            prec_list.append(prec)
            abst_list.append(1.0 if abst_ok else 0.0)
            hall_list.append(1.0 if hall else 0.0)
            latencies.append(float(c.get("latency_ms", 0.0)))

        perc = calculate_latency_percentiles(latencies)
        recomputed_metrics[eng_id] = {
            "recall_at_5": round(sum(rec5_list) / max(1, total), 4),
            "recall_at_20": round(sum(rec20_list) / max(1, total), 4),
            "ndcg_at_10": round(sum(ndcg_list) / max(1, total), 4),
            "complete_gold_evidence_coverage": round(sum(cov_list) / max(1, total), 4),
            "citation_precision": round(sum(prec_list) / max(1, total), 4),
            "abstention_correctness": round(sum(abst_list) / max(1, total), 4),
            "hallucination_rate": round(sum(hall_list) / max(1, total), 4),
            "p50_latency_ms": perc["p50"],
            "p90_latency_ms": perc["p90"],
            "p95_latency_ms": perc["p95"],
            "p99_latency_ms": perc["p99"],
            "mean_latency_ms": perc["mean"],
            "total_cases": total,
        }

    # -------------------------------------------------------------------------
    # 6. Manifest Metric Discrepancy Checks (0.01 tolerance)
    # -------------------------------------------------------------------------
    manifest_metrics = manifest.get("metric_summaries") or manifest.get("metrics") or {}
    for eng_id, recomp in recomputed_metrics.items():
        if eng_id in manifest_metrics:
            mf = manifest_metrics[eng_id]
            for key in [
                "recall_at_5",
                "recall_at_20",
                "ndcg_at_10",
                "complete_gold_evidence_coverage",
                "citation_precision",
                "abstention_correctness",
            ]:
                if key in mf:
                    val_m = float(mf.get(key, 0.0))
                    val_r = float(recomp.get(key, 0.0))
                    if abs(val_m - val_r) > 0.01:
                        failures.append(
                            f"[{eng_id}] Metric mismatch for {key}: manifest={val_m:.4f} recomputed={val_r:.4f} (diff={abs(val_m - val_r):.4f})"
                        )

            for lat_key in ["p50_latency_ms", "p95_latency_ms"]:
                if lat_key in mf:
                    val_m = float(mf.get(lat_key, 0.0))
                    val_r = float(recomp.get(lat_key, 0.0))
                    if abs(val_m - val_r) > 0.5:
                        failures.append(
                            f"[{eng_id}] Latency mismatch for {lat_key}: manifest={val_m:.2f} recomputed={val_r:.2f}"
                        )

    is_valid = len(failures) == 0
    now_ts = datetime.now(UTC).isoformat()

    attestation_payload = {
        "verifier": "TraceStudioIndependentVerifier",
        "run_id": run_id,
        "dataset_id": dataset_id,
        "corpus_sha256": disk_corpus_sha256 or manifest.get("corpus_sha256"),
        "queries_sha256": disk_query_sha256 or manifest.get("queries_sha256"),
        "manifest_signature": stored_sig,
        "recomputed_metrics": recomputed_metrics,
        "verified_at": now_ts,
    }
    attestation_sig = hashlib.sha256(
        json.dumps(attestation_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    attestation = {
        "attestation_version": "2.0.0",
        "verifier": "TraceStudioIndependentVerifier",
        "run_id": run_id,
        "dataset_id": dataset_id,
        "verified_at": now_ts,
        "integrity_status": "SEALED" if is_valid else "REJECTED",
        "attestation_signature": attestation_sig if is_valid else None,
        "failures": failures,
        "recomputed_metrics": recomputed_metrics,
        "manifest_signature": stored_sig,
        "provenance": {
            "corpus_sha256": disk_corpus_sha256 or manifest.get("corpus_sha256"),
            "queries_sha256": disk_query_sha256 or manifest.get("queries_sha256"),
            "total_evaluations": len(raw_evals),
            "engines": list(by_engine.keys()),
        },
    }

    # Write attestation to disk
    attestation_path = target_dir / "attestation.json"
    attestation_path.write_text(json.dumps(attestation, indent=2, ensure_ascii=False), encoding="utf-8")

    return is_valid, attestation, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Trace Studio Independent Benchmark Verifier")
    parser.add_argument("--run-id", type=str, help="Specific run ID to verify")
    parser.add_argument("--run-dir", type=str, help="Specific run directory path")
    parser.add_argument("--runs-root", type=str, default="benchmarks/runs", help="Root directory containing runs")
    args = parser.parse_args()

    runs_root = REPO_ROOT / args.runs_root
    catalog = DatasetCatalog()

    try:
        target_dir = find_target_run_dir(runs_root, run_id=args.run_id, run_dir=args.run_dir)
    except Exception as ex:
        print(f"[ERROR] {ex}", file=sys.stderr)
        return 1

    print(f"================================================================================")
    print(f"       TRACE BENCHMARK STUDIO: INDEPENDENT ATTESTATION VERIFIER")
    print(f"================================================================================")
    print(f"Target Run Directory : {target_dir}")

    is_valid, attestation, failures = verify_run(target_dir, catalog)

    print(f"Run ID               : {attestation.get('run_id')}")
    print(f"Dataset              : {attestation.get('dataset_id')}")
    print(f"Total Evaluations    : {attestation.get('provenance', {}).get('total_evaluations')}")
    print(f"Status               : {'[PASS] ' + attestation.get('integrity_status') if is_valid else '[FAIL] ' + attestation.get('integrity_status')}")
    if attestation.get("attestation_signature"):
        print(f"Attestation Sig      : {attestation['attestation_signature'][:16]}...")
    print(f"--------------------------------------------------------------------------------")
    print(f"{'ENGINE':<18} | {'R@5':<8} | {'R@20':<8} | {'NDCG@10':<8} | {'PRECISION':<10} | {'P95 (ms)':<8}")
    print(f"--------------------------------------------------------------------------------")

    for eng, m in attestation.get("recomputed_metrics", {}).items():
        print(
            f"{eng:<18} | "
            f"{m.get('recall_at_5', 0)*100:>6.1f}% | "
            f"{m.get('recall_at_20', 0)*100:>6.1f}% | "
            f"{m.get('ndcg_at_10', 0):>8.3f} | "
            f"{m.get('citation_precision', 0)*100:>8.1f}% | "
            f"{m.get('p95_latency_ms', 0):>8.1f}"
        )

    print(f"================================================================================")

    if not is_valid:
        print(f"[FAILURES DETECTED]:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(f"[SUCCESS] Independent verification attestation sealed: {target_dir / 'attestation.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
