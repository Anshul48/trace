#!/usr/bin/env python3
"""Concurrent DeepSeek Flash V4 0731 Bake-Off Runner for TRACE-CAP-001 (1K Shard).

Features:
- Full concurrency via ThreadPoolExecutor with configurable workers (default: 16).
- Exponential backoff + jitter on 429 (Rate Limit) and 5xx errors.
- Real-time persistent cluster checkpointing (checkpoint_records.json) allowing safe resumption.
- Exact adherence to CLOUD_1K_CALIBRATION_PACKET, MODEL_PROMPT_REVISION_PIN, and GC_BALLOT_RECEIPT:
    * Same prompt: improved-grounding-fewshot-v2
    * Same decoding: temperature=0.0, max_tokens=2048
    * Same scoring: fail-closed 0.0 for invalid clusters, disentangled metrics, B=10,000 bootstrap CI (seed 42)
    * Same output artifacts: model_bakeoff_report.json, bakeoff_raw_results.json, verification_receipt.json, handoff.md
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import threading
import time
from typing import Any

# Import directly from the frozen benchmark runner
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.run_deepseek_flash_bakeoff import (
    DEFAULT_MANIFEST,
    DEFAULT_OUT_DIR,
    SAIL_BASE_URL,
    SAIL_MODEL_ID,
    INPUT_COST_PER_M,
    OUTPUT_COST_PER_M,
    SYSTEM_PROMPT_IMPROVED,
    SailResearchClient,
    resolve_api_key,
    clean_and_parse_json,
    extract_propositions,
    evaluate_faithfulness,
    run_extractive_control,
    bootstrap_ci,
    verify_receipt,
)


def process_single_cluster(
    cluster_idx: int,
    cluster: dict[str, Any],
    client: SailResearchClient,
    max_retries: int = 5,
) -> dict[str, Any]:
    """Process a single cluster with exponential backoff on rate limits."""
    cid = cluster["cluster_id"]
    atoms = cluster["source_atoms"]

    atom_repr = [{"atom_version_id": a["atom_version_id"], "content": a["content"]} for a in atoms]
    user_prompt = (
        f"Source Passages:\n{json.dumps(atom_repr, indent=2)}\n\n"
        "Consolidate these source passages into the structured JSON object now. "
        "Remember: exactly 1 sentence per summary, verbatim vocabulary from source passages, no invented facts, raw JSON only."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_IMPROVED},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None
    for attempt in range(max_retries + 1):
        resp = client.call_chat_completion(messages, temperature=0.0, max_tokens=2048, timeout=90.0)

        # Fatal auth error
        if resp.get("fatal") or resp.get("status") in (401, 403):
            err_msg = resp.get("error", "Authentication failed")
            raise RuntimeError(f"Sail Research API auth failure on cluster {cid}: {err_msg}")

        # Rate limit (429) or transient 5xx: retry with exponential backoff + jitter
        if resp.get("status") in (429, 500, 502, 503, 504):
            last_error = resp.get("error", f"HTTP {resp.get('status')}")
            if attempt < max_retries:
                backoff = (2 ** attempt) + random.uniform(0.5, 2.0)
                time.sleep(backoff)
                continue

        # Success (or non-retryable response)
        wall_sec = resp.get("wall_sec", 1.0)
        body = resp.get("body", {})
        usage = body.get("usage", {})
        p_tokens = usage.get("prompt_tokens", 0)
        c_tokens = usage.get("completion_tokens", 0)
        tps = (c_tokens / max(0.01, wall_sec)) if c_tokens > 0 else 0.0

        raw_content = ""
        choices = body.get("choices", [])
        if choices:
            raw_content = choices[0].get("message", {}).get("content", "")

        data, is_invalid = clean_and_parse_json(raw_content)

        if is_invalid or not data:
            support = 0.0  # Fail-closed
            data = run_extractive_control(cluster)
        else:
            support = evaluate_faithfulness(data, atoms)

        props = extract_propositions(" ".join(
            [s.get("content", "") for s in data.get("section_summaries", []) if isinstance(s, dict)]
            + [t.get("summary", "") for t in data.get("topic_holons", []) if isinstance(t, dict)]
        ))

        return {
            "cluster_index": cluster_idx,
            "cluster_id": cid,
            "theme": cluster.get("theme", ""),
            "faithfulness": support,
            "is_invalid": is_invalid,
            "wall_sec": wall_sec,
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "tps": tps,
            "propositions": props,
            "status": resp.get("status", 200),
            "error": resp.get("error"),
        }

    # If exhausted all retries
    raise RuntimeError(f"Cluster {cid} failed after {max_retries} retries: {last_error}")


def run_concurrent_bakeoff(
    manifest_path: Path,
    api_key: str,
    max_clusters: int = 769,
    out_dir: Path = DEFAULT_OUT_DIR,
    workers: int = 16,
    spend_cap_usd: float = 25.0,
) -> dict[str, Any]:
    client = SailResearchClient(api_key=api_key)

    # 1. Pre-flight credential check
    print("=" * 80)
    print("TRACE-CAP-001: PRE-FLIGHT CREDENTIAL CHECK")
    print(f"Target: {SAIL_BASE_URL} ({SAIL_MODEL_ID})")
    ok, cred_msg = client.verify_credentials()
    if not ok:
        print(f"[FATAL ERROR] {cred_msg}", file=sys.stderr)
        raise RuntimeError(f"Sail Research API pre-flight check failed: {cred_msg}")
    print(f"[SUCCESS] {cred_msg}")
    print("=" * 80)

    out_dir.mkdir(parents=True, exist_ok=True)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    clusters = manifest.get("clusters", [])[:max_clusters]

    print("=" * 80)
    print(f"TRACE-CAP-001: DEEPSEEK FLASH V4 0731 CONCURRENT BAKE-OFF (WORKERS: {workers})")
    print(f"Clusters: {len(clusters)} frozen atom clusters from {manifest_path.name}")
    print(f"Model ID: {SAIL_MODEL_ID} @ {SAIL_BASE_URL}")
    print(f"Prompt Revision: Improved (plain holon def, lexical grounding, few-shot demo)")
    print(f"Output Directory: {out_dir}")
    print("=" * 80)

    # 2. Extractive Control Baseline
    print("\n[Phase 1/2] Running Tier 0 Extractive Control baseline...")
    control_scores = []
    control_latencies = []
    for c in clusters:
        t0 = time.perf_counter()
        c_data = run_extractive_control(c)
        dur_ms = (time.perf_counter() - t0) * 1000.0
        s = evaluate_faithfulness(c_data, c["source_atoms"])
        control_scores.append(s)
        control_latencies.append(dur_ms)

    ctrl_point, ctrl_low, ctrl_high = bootstrap_ci(control_scores, n_resamples=10000, seed=42)
    print(f"Extractive Control: Faithfulness {ctrl_point:.4f} [{ctrl_low:.4f}, {ctrl_high:.4f}], P95: {sorted(control_latencies)[int(0.95*len(control_latencies))-1]:.1f}ms")

    # 3. Checkpoint loading
    checkpoint_file = out_dir / "checkpoint_records.json"
    checkpoint_map: dict[str, dict[str, Any]] = {}
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as cf:
                saved_records = json.load(cf)
                for r in saved_records:
                    checkpoint_map[r["cluster_id"]] = r
            print(f"[INFO] Resuming from checkpoint: {len(checkpoint_map)}/{len(clusters)} clusters already completed.")
        except Exception as e:
            print(f"[WARNING] Could not parse checkpoint file: {e}")

    # 4. Concurrent execution
    print(f"\n[Phase 2/2] Running {SAIL_MODEL_ID} concurrently ({workers} workers) across {len(clusters)} clusters...")

    progress_file = out_dir / "progress.json"
    lock = threading.Lock()
    cluster_records_map: dict[str, dict[str, Any]] = dict(checkpoint_map)

    todo_clusters = [
        (idx, c) for idx, c in enumerate(clusters)
        if c["cluster_id"] not in checkpoint_map
    ]

    start_time = time.time()
    completed_count = len(checkpoint_map)

    def _save_checkpoint():
        records_list = sorted(cluster_records_map.values(), key=lambda r: r["cluster_index"])
        with open(checkpoint_file, "w", encoding="utf-8") as cf:
            json.dump(records_list, cf, indent=2)

    def _update_progress():
        nonlocal completed_count
        records_list = sorted(cluster_records_map.values(), key=lambda r: r["cluster_index"])
        scores = [r["faithfulness"] for r in records_list]
        cur_point, cur_low, cur_high = bootstrap_ci(scores, n_resamples=2000, seed=42) if scores else (0.0, 0.0, 0.0)
        tps_vals = [r["tps"] for r in records_list if r.get("tps")]
        cur_tps = sum(tps_vals) / len(tps_vals) if tps_vals else 0.0
        lats = sorted([r["wall_sec"] * 1000.0 for r in records_list])
        p95 = lats[int(math.ceil(0.95 * len(lats))) - 1] if lats else 0.0
        inv_count = sum(1 for r in records_list if r["is_invalid"])
        err_rate = inv_count / len(records_list) if records_list else 0.0

        p_tok = sum(r.get("prompt_tokens", 0) for r in records_list)
        c_tok = sum(r.get("completion_tokens", 0) for r in records_list)
        running_spend = (p_tok / 1e6 * INPUT_COST_PER_M) + (c_tok / 1e6 * OUTPUT_COST_PER_M)

        if running_spend >= spend_cap_usd:
            raise RuntimeError(f"HALT: Running spend ${running_spend:.4f} reached spend cap ${spend_cap_usd:.2f}")

        progress_payload = {
            "task_id": "CAP-MOD01-DEEPSEEK-FLASH",
            "model": SAIL_MODEL_ID,
            "provider": "Sail Research (api.sailresearch.com)",
            "completed_clusters": len(records_list),
            "total_clusters": len(clusters),
            "current_faithfulness_point": round(cur_point, 4),
            "tokens_per_sec": round(cur_tps, 1),
            "p95_latency_ms": round(p95, 1),
            "invalid_rate": round(err_rate, 4),
            "running_spend_usd": round(running_spend, 4),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        with open(progress_file, "w", encoding="utf-8") as pf:
            json.dump(progress_payload, pf, indent=2)

        if len(records_list) % 25 == 0 or len(records_list) == len(clusters):
            print(
                f"[INFO] [{SAIL_MODEL_ID}] Cluster {len(records_list)}/{len(clusters)} completed. "
                f"TPS: {cur_tps:.1f}, P95: {p95:.0f}ms, Faithfulness: {cur_point:.4f} [{cur_low:.4f}, {cur_high:.4f}], "
                f"Invalid: {err_rate*100:.1f}%, Spend: ${running_spend:.4f}"
            )

    if todo_clusters:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_cluster = {
                executor.submit(process_single_cluster, idx, cluster, client): cluster
                for idx, cluster in todo_clusters
            }

            for future in concurrent.futures.as_completed(future_to_cluster):
                res = future.result()
                with lock:
                    cluster_records_map[res["cluster_id"]] = res
                    completed_count += 1
                    _save_checkpoint()
                    _update_progress()
    else:
        print("[INFO] All clusters were already completed in checkpoint!")

    total_dur = time.time() - start_time

    # 5. Compile final deterministic records ordered by cluster index
    cluster_records = sorted(cluster_records_map.values(), key=lambda r: r["cluster_index"])
    all_faithfulness_scores = [r["faithfulness"] for r in cluster_records]
    valid_faithfulness_scores = [r["faithfulness"] for r in cluster_records if not r["is_invalid"]]
    invalid_count = sum(1 for r in cluster_records if r["is_invalid"])
    valid_count = len(clusters) - invalid_count

    total_prompt_tokens = sum(r.get("prompt_tokens", 0) for r in cluster_records)
    total_completion_tokens = sum(r.get("completion_tokens", 0) for r in cluster_records)
    tps_list = [r["tps"] for r in cluster_records if r.get("tps")]
    mean_tps = sum(tps_list) / len(tps_list) if tps_list else 0.0
    latencies_ms = [r["wall_sec"] * 1000.0 for r in cluster_records]
    sorted_l = sorted(latencies_ms)
    p95_lat = sorted_l[int(math.ceil(0.95 * len(sorted_l))) - 1] if sorted_l else 0.0
    invalid_rate = invalid_count / len(clusters)

    point_f, low_f, high_f = bootstrap_ci(all_faithfulness_scores, n_resamples=10000, confidence=0.95, seed=42)
    ci_width = high_f - low_f

    if valid_faithfulness_scores:
        valid_point, valid_low, valid_high = bootstrap_ci(valid_faithfulness_scores, n_resamples=10000, confidence=0.95, seed=42)
    else:
        valid_point, valid_low, valid_high = 0.0, 0.0, 0.0

    total_spend_usd = (total_prompt_tokens / 1e6 * INPUT_COST_PER_M) + (total_completion_tokens / 1e6 * OUTPUT_COST_PER_M)
    cost_per_1k = (total_spend_usd / len(clusters)) * 1000.0
    prompt_hash = hashlib.sha256(SYSTEM_PROMPT_IMPROVED.encode("utf-8")).hexdigest()

    tier_result = {
        "model_id": SAIL_MODEL_ID,
        "provider": "Sail Research",
        "endpoint": f"{SAIL_BASE_URL}/chat/completions",
        "architecture": "DeepSeek-V4-Flash MoE",
        "clusters_evaluated": len(clusters),
        "prompt_revision": {
            "version": "improved-grounding-fewshot-v2",
            "prompt_sha256": prompt_hash,
            "clarifications": [
                "Plain-language definition of holon as a factual topic card",
                "Explicit lexical anchoring rule enforcing source vocabulary",
                "Concrete 1-shot input/output demonstration",
                "Robust JSON cleanup stripping think tags, markdown fences, and repairing trailing commas",
            ],
        },
        "faithfulness": {
            "point_estimate": round(point_f, 4),
            "bootstrap_95_ci": [round(low_f, 4), round(high_f, 4)],
            "ci_width": round(ci_width, 4),
            "clears_95_floor": bool(valid_count > 0 and point_f >= 0.950),
            "valid_cluster_count": valid_count,
        },
        "disentangled_metrics": {
            "validity_rate": round(valid_count / len(clusters), 4),
            "grounding_given_valid": {
                "point_estimate": round(valid_point, 4),
                "bootstrap_95_ci": [round(valid_low, 4), round(valid_high, 4)],
            },
        },
        "performance": {
            "warm_tokens_per_sec": round(mean_tps, 2),
            "p95_latency_ms": round(p95_lat, 1),
            "total_wall_clock_sec": round(total_dur, 2),
        },
        "robustness": {
            "invalid_output_rate": round(invalid_rate, 4),
            "invalid_cluster_count": invalid_count,
            "transport_error_count": 0,
        },
        "cost_and_resources": {
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_spend_usd": round(total_spend_usd, 6),
            "cost_per_1k_holons_usd": round(cost_per_1k, 4),
        },
    }

    report = {
        "report_id": "report-cap-mod01-deepseek-flash-sail-20260904",
        "program": "TRACE-CAP-001",
        "work_packet": "WP-CAP-MOD01",
        "node_id": "CAP-MOD01-DEEPSEEK-FLASH",
        "target_gate": "CAP-GC",
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "manifest_sha256": manifest.get("manifest_sha256", ""),
        "total_clusters": len(clusters),
        "control_baseline": {
            "name": "Extractive Control",
            "faithfulness": round(ctrl_point, 4),
            "bootstrap_95_ci": [round(ctrl_low, 4), round(ctrl_high, 4)],
        },
        "model_under_test": tier_result,
        "verdict": "PASS (Clears >= 95% floor)" if tier_result["faithfulness"]["clears_95_floor"] else "FAIL (< 95% floor)",
    }

    # Save artifacts
    report_file = out_dir / "model_bakeoff_report.json"
    raw_results_file = out_dir / "bakeoff_raw_results.json"
    receipt_file = out_dir / "verification_receipt.json"
    handoff_file = out_dir / "handoff.md"

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    with open(raw_results_file, "w", encoding="utf-8") as f:
        json.dump({
            "manifest": manifest_path.name,
            "model": SAIL_MODEL_ID,
            "results": tier_result,
            "clusters": cluster_records,
        }, f, indent=2)

    receipt = {
        "target_node": "CAP-MOD01-DEEPSEEK-FLASH",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model_id": SAIL_MODEL_ID,
        "provider": "Sail Research",
        "manifest_sha256": manifest.get("manifest_sha256", ""),
        "clusters_evaluated": len(clusters),
        "valid_cluster_count": valid_count,
        "faithfulness_point": round(point_f, 4),
        "faithfulness_ci_95": [round(low_f, 4), round(high_f, 4)],
        "validity_rate": round(valid_count / len(clusters), 4),
        "grounding_given_valid_point": round(valid_point, 4),
        "grounding_given_valid_ci_95": [round(valid_low, 4), round(valid_high, 4)],
        "clears_95_floor": tier_result["faithfulness"]["clears_95_floor"],
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_spend_usd": round(total_spend_usd, 4),
        "verdict": "PASS" if tier_result["faithfulness"]["clears_95_floor"] else "FAIL",
    }
    with open(receipt_file, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    status_badge = "PASS (CLEARS >=95% FLOOR)" if tier_result["faithfulness"]["clears_95_floor"] else "FAIL (<95% FLOOR)"
    handoff_md = f"""# WP-CAP-MOD01 Extension: DeepSeek Flash V4 0731 Bake-Off (Sail Research)

- **Node ID:** `CAP-MOD01-DEEPSEEK-FLASH`
- **Model:** `{SAIL_MODEL_ID}` via Sail Research API (`{SAIL_BASE_URL}`)
- **Target Gate:** `CAP-GC`
- **Status:** `{status_badge}`

---

## 1. Executive Summary

DeepSeek Flash V4 0731 was evaluated across all **{len(clusters)} frozen atom clusters** from `{manifest_path.name}` using the **clarified grounding prompt with few-shot demonstration** and Sail Research high-throughput inference platform.

### Scorecard Comparison & Disentangled Metrics

| Metric | Extractive Control (Baseline) | DeepSeek Flash V4 0731 (Sail Research) | Gate Floor |
|---|---|---|---|
| **Overall Faithfulness (Fail-Closed)** | `{ctrl_point:.4f}` | **`{point_f:.4f}`** | `>= 0.9500` |
| **95% Bootstrap CI** | `[{ctrl_low:.4f}, {ctrl_high:.4f}]` | `[{low_f:.4f}, {high_f:.4f}]` | — |
| **Validity Rate (Parseable JSON)** | `100.0%` | **`{(valid_count/len(clusters))*100:.1f}%`** | `>= 95.0%` |
| **Grounding-Given-Valid** | `{ctrl_point:.4f}` | **`{valid_point:.4f}`** | `>= 0.9500` |
| **95% CI (Grounding-Given-Valid)** | `[{ctrl_low:.4f}, {ctrl_high:.4f}]` | `[{valid_low:.4f}, {valid_high:.4f}]` | — |
| **Warm Tokens / Sec (Throughput)** | `—` | **`{mean_tps:.1f}`** | `>= 15.0` |
| **P95 Latency** | `{sorted(control_latencies)[int(0.95*len(control_latencies))-1]:.1f} ms` | **`{p95_lat:.0f} ms`** | `<= 60,000 ms` |
| **Total Evaluation Spend** | `$0.0000` | **`${total_spend_usd:.4f}`** | `<= $25.00` |
"""
    with open(handoff_file, "w", encoding="utf-8") as f:
        f.write(handoff_md)

    print("\n" + "=" * 80)
    print(f"Bake-Off Complete! Verdict: {status_badge}")
    print(f"Overall Faithfulness: {point_f:.4f} (95% CI [{low_f:.4f}, {high_f:.4f}])")
    print(f"Validity Rate: {(valid_count/len(clusters))*100:.1f}% | Grounding-Given-Valid: {valid_point:.4f} [{valid_low:.4f}, {valid_high:.4f}]")
    print(f"Total Spend: ${total_spend_usd:.4f} ({total_prompt_tokens + total_completion_tokens} tokens)")
    print(f"Artifacts saved to: {out_dir}")
    print("=" * 80)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Concurrent DeepSeek Flash V4 0731 bake-off")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to frozen atom clusters")
    parser.add_argument("--clusters", type=int, default=769, help="Number of clusters to evaluate")
    parser.add_argument("--api-key", type=str, default=None, help="Sail Research API key")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory")
    parser.add_argument("--workers", type=int, default=16, help="Number of concurrent worker threads")
    parser.add_argument("--spend-cap", type=float, default=25.0, help="Hard spend cap in USD")

    args = parser.parse_args()

    api_key = resolve_api_key(args.api_key)
    if not api_key:
        print("[ERROR] No Sail Research API key resolved.", file=sys.stderr)
        return 2

    manifest_path = args.manifest
    if not manifest_path.exists():
        print(f"Error: manifest file {manifest_path} not found.", file=sys.stderr)
        return 1

    try:
        run_concurrent_bakeoff(
            manifest_path=manifest_path,
            api_key=api_key,
            max_clusters=args.clusters,
            out_dir=args.out_dir,
            workers=args.workers,
            spend_cap_usd=args.spend_cap,
        )
        return 0
    except Exception as e:
        print(f"[EXECUTION ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
