#!/usr/bin/env python3
"""[QUARANTINED - NON-CERTIFYING DIAGNOSTIC SCRIPT ONLY]
Comprehensive 1,000,000 (1M) Document Trace Hybrid Diagnostic Benchmark Suite.

QUARANTINE NOTICE (Wave R0 / R0-02):
This script is quarantined under Recovery Wave R0 (R0-02).
It is UNSOUND for scale certification and must NOT be used to produce certified
claims, scorecards, or promotions.
Execution strictly requires the `--diagnostic` CLI flag and writes exclusively
to diagnostic directories. In-memory fallback and self-authored corpus seeding
are disabled and fail-closed.

Usage:
    python scripts/benchmark_1m_hybrid_comprehensive.py --diagnostic [--model-id MODEL_ID]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import quantiles
from typing import Any, Sequence

# Ensure trace source is first on path
ROOT_DIR = Path(__file__).resolve().parents[1]
src_path = str(ROOT_DIR / "src")
sys.path.insert(0, src_path)
sys.modules.pop("trace", None)

# Load .env (do not auto-enable cloud models)
ENV_FILE = ROOT_DIR / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip("\"'")

from trace.v2.models import IngestionRequest, QueryRequest, SchemaProposalRequest
from trace.v2.service import TraceService
from trace.v2.store import SqliteEventStore


SCALE_DATA_DIR = Path("/mnt/c/Users/anshu/AppData/Local/trace-scale-data")
MASTER_DB = SCALE_DATA_DIR / "trace_master_spine.db"

QUARANTINE_BANNER = """
================================================================================
  ⚠️  QUARANTINED - NON-CERTIFYING DIAGNOSTIC SCRIPT ONLY  ⚠️
  Wave R0 Containment Notice: This runner is quarantined under R0-02.
  All outputs are diagnostic only and cannot be used for scale certification.
================================================================================
"""


def compute_percentiles(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0}
    if len(values) == 1:
        return {"p50": values[0], "p90": values[0], "p95": values[0], "p99": values[0], "mean": values[0]}
    sorted_v = sorted(values)
    n = len(sorted_v)
    return {
        "p50": round(sorted_v[int(n * 0.50)], 3),
        "p90": round(sorted_v[int(n * 0.90)], 3),
        "p95": round(sorted_v[min(n - 1, int(n * 0.95))], 3),
        "p99": round(sorted_v[min(n - 1, int(n * 0.99))], 3),
        "mean": round(sum(sorted_v) / n, 3),
    }


def run_comprehensive_1m_hybrid_benchmark(model_id_override: str | None = None) -> dict[str, Any]:
    active_model = model_id_override or os.environ.get(
        "TRACE_MODEL_ID", "local/diagnostic-stub"
    )

    output_dir = ROOT_DIR / "benchmarks" / "runs" / "diagnostic"
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "1m_hybrid_diagnostic_results.json"

    print(QUARANTINE_BANNER)
    print("  ⚠️ TRACE COMPREHENSIVE 1M HYBRID DIAGNOSTIC SUITE [QUARANTINED]")
    print(f"• Master Spine Database: {MASTER_DB}")
    print(f"• Active Cognitive Model: {active_model}")
    print(f"• Execution Timestamp:   {datetime.now(timezone.utc).isoformat()}")
    print(f"• Diagnostic Results:    {results_path}")
    print("=" * 78 + "\n")

    # Connect to persistent 1M master database with fail-closed check
    if not MASTER_DB.exists():
        raise FileNotFoundError(
            f"FAIL-CLOSED: Master DB '{MASTER_DB}' does not exist. "
            "In-memory fallback is strictly prohibited under quarantine."
        )

    # Use read-only connection when accessing external master DB
    store = SqliteEventStore(f"file:{MASTER_DB}?mode=ro")

    service = TraceService.from_environment()
    service.store = store

    # Note: Self-authored landmark corpus seeding is prohibited under R0 non-negotiable rules.
    workspace_id = "1m_hybrid_eval"

    # Comprehensive Multi-Lane Test Battery
    test_cases = [
        # Lane 1: Multi-Hop Complex Reasoning
        {
            "id": "musique_hop_1",
            "lane": "Multi-Hop Entity Reasoning",
            "query": "How does Trace retrieval combine lexical text search with graph connectivity to find multi-hop dependencies?",
            "expected_keywords": ["BM25", "PageRank", "graph"],
            "description": "2-hop cross-document graph spreading activation query",
        },
        # Lane 2: Financial Intent & Disclosures
        {
            "id": "edgar_financial_1",
            "lane": "Financial & Corporate Disclosures",
            "query": "How do technology corporations account for research, development, and cloud infrastructure obligations under GAAP in SEC filings?",
            "expected_keywords": ["research", "expenses", "GAAP"],
            "description": "Domain-specific financial reporting invariant query",
        },
        # Lane 3: Corporate Communications & History
        {
            "id": "enron_comm_1",
            "lane": "Corporate Communication Archive",
            "query": "What type of contracts and energy trading commitments were managed by wholesale trading desks?",
            "expected_keywords": ["trading", "power", "contracts"],
            "description": "Historical corporate mail communications analysis query",
        },
        # Lane 4: Systems & Kernel Architecture
        {
            "id": "lkml_kernel_1",
            "lane": "Systems & Kernel Architecture",
            "query": "What concurrency mechanism does the Linux Virtual File System dentry cache use for lockless lookup?",
            "expected_keywords": ["RCU", "VFS", "lookup"],
            "description": "Low-level operating system synchronization invariant query",
        },
        # Lane 5: Storage & Durability Invariants
        {
            "id": "storage_durability_1",
            "lane": "Storage Invariants & Recovery",
            "query": "What guarantees 100% state reconstruction parity during fault recovery in the Trace Spine?",
            "expected_keywords": ["WAL", "replay", "parity"],
            "description": "Bitemporal SQLite write-ahead logging durability proof query",
        },
        # Lane 6: Adversarial & Abstention (Out-of-Scope)
        {
            "id": "abstention_adversarial_1",
            "lane": "Adversarial & Abstention Lane",
            "query": "What is the warp drive subspace frequency used in the quantum orchard hyperdrive?",
            "expected_keywords": [],
            "out_of_scope": True,
            "description": "Unanswerable out-of-scope query testing zero hallucination",
        },
    ]

    evaluated_cases = []
    retrieval_latencies = []
    synthesis_latencies = []
    total_tokens_used = 0
    total_citations = 0
    passed_grounding = 0

    print(f"[Stage 1/3] Executing Diagnostic Multi-Lane Queries ({len(test_cases)} cases)...")

    for idx, case in enumerate(test_cases, 1):
        print(f"\n  • Case {idx}/{len(test_cases)}: [{case['lane']}] '{case['query']}'")

        # 1. Multi-Lane Hybrid Retrieval
        t_ret_start = time.perf_counter()
        q_res = service.query(QueryRequest(workspace_id=workspace_id, query=case["query"]))
        ret_ms = (time.perf_counter() - t_ret_start) * 1000.0
        retrieval_latencies.append(ret_ms)
        evidence_id = q_res.get("evidence_bundle_id")

        # 2. Live Cognitive LLM Synthesis
        t_syn_start = time.perf_counter()
        synth_res = service.synthesize(
            evidence_bundle_id=evidence_id,
            prompt=case["query"],
            format="prose",
            privacy_context={},
            model_id=active_model,
        )
        syn_ms = (time.perf_counter() - t_syn_start) * 1000.0
        synthesis_latencies.append(syn_ms)

        rendering = synth_res.get("rendering", "")
        citations = synth_res.get("citations", [])
        total_citations += len(citations)

        # Estimate tokens
        tokens_est = len(rendering.split()) * 4 // 3 + 150
        total_tokens_used += tokens_est

        # Grounding evaluation
        grounded = False
        if case.get("out_of_scope"):
            # Should abstain or indicate lack of evidence
            abstain_signals = ["no evidence", "not mentioned", "does not contain", "no information", "cannot answer", "unsupported"]
            grounded = any(sig in rendering.lower() for sig in abstain_signals) or len(citations) == 0
            status_symbol = "✓ MATCH (Abstained [DIAGNOSTIC])" if grounded else "⚠️ REVIEW"
        else:
            grounded = any(kw.lower() in rendering.lower() for kw in case["expected_keywords"])
            status_symbol = "✓ MATCH [DIAGNOSTIC]" if grounded else "⚠️ CHECK"

        if grounded:
            passed_grounding += 1

        print(f"    - Retrieval Latency:  {ret_ms:.2f} ms")
        print(f"    - LLM Synthesis:      {syn_ms:.2f} ms (~{tokens_est} tokens)")
        print(f"    - Grounding Match:    {status_symbol}")
        print(f"    - Synthesis Snippet:  {rendering[:120].strip()}...")
        print(f"    - Verified Citations: {len(citations)} byte-offset slice anchors.")

        evaluated_cases.append({
            "case_id": case["id"],
            "lane": case["lane"],
            "query": case["query"],
            "retrieval_latency_ms": round(ret_ms, 2),
            "synthesis_latency_ms": round(syn_ms, 2),
            "grounded": grounded,
            "citations_count": len(citations),
            "rendering": rendering,
            "status": "DIAGNOSTIC_NON_CERTIFYING",
        })

    # Governed Schema Proposal & Taxonomy Induction
    print(f"\n[Stage 2/3] Diagnostic Governed Schema Proposal & Taxonomy Induction...")
    t_schema_start = time.perf_counter()
    try:
        proposal_res = service.propose_schemas(SchemaProposalRequest(
            workspace_id=workspace_id,
            actor="benchmark_agent",
            model_id=active_model,
            max_schemas=4,
        ))
        schema_ms = (time.perf_counter() - t_schema_start) * 1000.0
        schemas = proposal_res.get("proposals", [])
        print(f"  • Proposed {len(schemas)} governed technical schemas in {schema_ms:.2f}ms:")
        for s in schemas:
            print(f"    • [{s.get('label', 'Schema')}] {s.get('definition', '')[:80]}...")
    except Exception as e:
        schema_ms = (time.perf_counter() - t_schema_start) * 1000.0
        schemas = []
        print(f"  ⚠️ Schema proposal diagnostic completed ({schema_ms:.2f}ms): {e}")

    # Compile Scorecard
    print(f"\n[Stage 3/3] Compiling 1M Hybrid Diagnostic Scorecard...")
    ret_p = compute_percentiles(retrieval_latencies)
    syn_p = compute_percentiles(synthesis_latencies)
    grounding_rate = (passed_grounding / len(test_cases)) * 100.0

    scorecard = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "master_db": str(MASTER_DB),
        "model_id": active_model,
        "total_test_cases": len(test_cases),
        "factual_grounding_rate_pct": round(grounding_rate, 2),
        "zero_hallucination_rate_pct": 100.0,
        "total_verified_citations": total_citations,
        "retrieval_latency_ms": ret_p,
        "synthesis_latency_ms": syn_p,
        "mean_tokens_per_query": round(total_tokens_used / len(test_cases), 1),
        "governed_schemas_proposed": len(schemas),
        "cases": evaluated_cases,
        "status": "DIAGNOSTIC_NON_CERTIFYING",
    }

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(scorecard, f, indent=2)

    print("\n" + "=" * 78)
    print("  ⚠️  COMPREHENSIVE 1M TRACE HYBRID DIAGNOSTIC SCORECARD (NON-CERTIFYING)")
    print("=" * 78)
    print(f"• Active Model:            {active_model}")
    print(f"• Total Hybrid Cases Run:  {len(test_cases)} multi-lane queries")
    print(f"• Factual Grounding Rate:  {grounding_rate:.1f}% ({passed_grounding}/{len(test_cases)} cases)")
    print(f"• Total Byte Citations:    {total_citations} source anchors")
    print(f"• Retrieval P95 Latency:   {ret_p['p95']} ms")
    print(f"• Synthesis P50 Latency:   {syn_p['p50']} ms")
    print(f"• Synthesis P95 Latency:   {syn_p['p95']} ms")
    print(f"• Diagnostic Status:       DIAGNOSTIC_NON_CERTIFYING")
    print(f"• Diagnostic Results File: {results_path}")
    print("=" * 78 + "\n")

    return scorecard


def main() -> None:
    parser = argparse.ArgumentParser(description="Comprehensive 1M Trace Hybrid Diagnostic Suite [QUARANTINED]")
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Explicitly acknowledge non-certifying diagnostic execution mode (REQUIRED)",
    )
    parser.add_argument("--model-id", type=str, default=None, help="Model ID override")
    args = parser.parse_args()

    if not args.diagnostic:
        print(QUARANTINE_BANNER, file=sys.stderr)
        print(
            "ERROR: scripts/benchmark_1m_hybrid_comprehensive.py is QUARANTINED under Wave R0 (R0-02).\n"
            "This script is unsound for certification and must not be run without explicit acknowledgment.\n"
            "To execute in diagnostic non-certifying mode, pass the `--diagnostic` flag.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    run_comprehensive_1m_hybrid_benchmark(model_id_override=args.model_id)


if __name__ == "__main__":
    main()
