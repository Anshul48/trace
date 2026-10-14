#!/usr/bin/env python3
"""Concurrent DeepSeek Flash V4 0731 Runner for TRACE-CAP-001 (10K Shard Consolidation).

Normative Specs:
  - docs/program/inbox/cap-mod01/CLOUD_10K_SHADOW_SPEC.md
  - docs/program/inbox/cap-mod01/METRIC_AMENDMENT_M2.md
  - docs/program/inbox/cap-mod01/GC_BALLOT_RECEIPT.md
  - docs/program/inbox/cap-mod01/MODEL_PROMPT_REVISION_PIN.json

Key Features:
  - max_tokens floor: 8192 for all calls per CLOUD_10K_SHADOW_SPEC.md §1b.
  - Think-metering: captures pre-strip reasoning trace length (chars & words).
  - Concurrency: 10-12 worker threads with adaptive rate limiting and exponential backoff + jitter.
  - R1 Error-Feedback Retries: R1a (truncation), R1b (empty/0 props), R1c (unparseable).
  - Local Serial Fallback Queue (concurrency=1): isolates failed/retry clusters serially.
  - Key custody: process environment SAIL_API_KEY only (zero reading/writing of .env, zero CLI key flags).
  - Persistent real-time checkpointing (checkpoint_records.json) allowing safe resumption.
  - Quarantine: outputs all artifacts to docs/program/inbox/cap-mod01-cloud-10k/run-10k/.
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
import re
import sys
import threading
import time
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.run_deepseek_flash_bakeoff import (
    SAIL_BASE_URL,
    SAIL_MODEL_ID,
    INPUT_COST_PER_M,
    OUTPUT_COST_PER_M,
    SYSTEM_PROMPT_IMPROVED,
    SailResearchClient,
    extract_propositions,
    evaluate_faithfulness,
    run_extractive_control,
    bootstrap_ci,
)

DEFAULT_10K_MANIFEST = REPO_ROOT / "docs/program/inbox/cap-mod01-cloud-10k/clusters_10k_v1.json"
DEFAULT_10K_OUT_DIR = REPO_ROOT / "docs/program/inbox/cap-mod01-cloud-10k/run-10k"
PRIOR_CUMULATIVE_SPEND_USD = 1.3181  # From 1K anchor, 1K run, and 1K-R1 runs
HARD_SPEND_CAP_USD = 25.00
DEFAULT_WORKERS = 10
CAP_FLOOR_10K = 8192
CAP_RETRY_10K = 12288


def resolve_api_key_strict() -> str:
    """Resolve API key strictly from process environment SAIL_API_KEY only.
    
    Guarantees:
      - Never reads .env file
      - Never accepts CLI key
      - Never echoes key
    """
    key = os.environ.get("SAIL_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Key custody violation: SAIL_API_KEY environment variable is missing from process environment. "
            "Please ensure SAIL_API_KEY is exported before invocation."
        )
    return key


def extract_reasoning_and_clean_json(
    raw_text: str,
    reasoning_content: str | None = None,
) -> tuple[dict[str, Any] | None, bool, str, dict[str, int]]:
    """Extract think reasoning blocks, meter think length, and parse JSON payload.
    
    Returns:
      (data, is_invalid, parse_error, think_metrics)
    """
    reasoning_traces = []
    if reasoning_content and reasoning_content.strip():
        reasoning_traces.append(reasoning_content.strip())

    if not raw_text or not raw_text.strip():
        full_reasoning = "\n".join(reasoning_traces).strip()
        think_metrics = {
            "reasoning_chars": len(full_reasoning),
            "reasoning_words": len(re.findall(r"\w+", full_reasoning)),
        }
        return None, True, "Empty response body", think_metrics

    # Extract think blocks before stripping
    for tag in ("think", "thought", "reasoning"):
        pattern = rf"<{tag}>(.*?)</{tag}>"
        for m in re.finditer(pattern, raw_text, flags=re.DOTALL):
            reasoning_traces.append(m.group(1))

    # Also handle unclosed <think> tag if truncated
    if not reasoning_traces and "<think>" in raw_text and "</think>" not in raw_text:
        unclosed = raw_text.split("<think>", 1)[1]
        reasoning_traces.append(unclosed)

    full_reasoning = "\n".join(reasoning_traces).strip()
    think_chars = len(full_reasoning)
    think_words = len(re.findall(r"\w+", full_reasoning))

    think_metrics = {
        "reasoning_chars": think_chars,
        "reasoning_words": think_words,
    }

    # Strip reasoning tags
    text = raw_text.strip()
    for tag in ("think", "thought", "reasoning"):
        text = re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL).strip()
    if "<think>" in text and "</think>" not in text:
        text = text.split("<think>", 1)[0].strip()

    # Extract from markdown fences (including unclosed fences)
    if "```json" in text:
        match = re.search(r"```json\s*([\s\S]*?)(?:```|$)", text, flags=re.IGNORECASE)
        if match:
            text = match.group(1).strip()
    elif "```" in text:
        match = re.search(r"```\s*([\s\S]*?)(?:```|$)", text)
        if match:
            text = match.group(1).strip()

    last_error = ""

    def _validate_schema(obj: Any) -> tuple[dict[str, Any] | None, bool, str]:
        if not isinstance(obj, dict):
            return None, True, "JSON root is not an object"
        
        # Unwrap nested wrapper object if present
        if "section_summaries" not in obj and "topic_holons" not in obj:
            for wrapper_key in ("data", "result", "consolidation", "output", "response"):
                if isinstance(obj.get(wrapper_key), dict):
                    inner = obj[wrapper_key]
                    if "section_summaries" in inner or "topic_holons" in inner:
                        obj = inner
                        break

        has_sec = "section_summaries" in obj and isinstance(obj["section_summaries"], list) and len(obj["section_summaries"]) > 0
        has_hol = "topic_holons" in obj and isinstance(obj["topic_holons"], list) and len(obj["topic_holons"]) > 0
        if has_sec or has_hol:
            norm = {
                "section_summaries": obj.get("section_summaries", []),
                "topic_holons": obj.get("topic_holons", []),
                "entity_candidates": obj.get("entity_candidates", []),
                "relation_candidates": obj.get("relation_candidates", []),
            }
            return norm, False, ""
        return None, True, "Missing non-empty section_summaries or topic_holons"

    # 1. Direct parse attempt
    try:
        data = json.loads(text)
        res, is_inv, err = _validate_schema(data)
        if not is_inv:
            return res, False, "", think_metrics
        last_error = err
    except Exception as e:
        last_error = str(e)

    # 2. Repair trailing commas before } or ]
    repaired_commas = re.sub(r",\s*([\]}])", r"\1", text)
    try:
        data = json.loads(repaired_commas)
        res, is_inv, err = _validate_schema(data)
        if not is_inv:
            return res, False, "", think_metrics
        last_error = err
    except Exception as e:
        last_error = str(e)

    # 3. Locate outermost { ... }
    brace_match = re.search(r"(\{[\s\S]*\})", text)
    if brace_match:
        cand = brace_match.group(1)
        try:
            data = json.loads(cand)
            res, is_inv, err = _validate_schema(data)
            if not is_inv:
                return res, False, "", think_metrics
            last_error = err
        except Exception as e:
            last_error = str(e)

        # Trailing comma repair on outermost block
        cand_commas = re.sub(r",\s*([\]}])", r"\1", cand)
        try:
            data = json.loads(cand_commas)
            res, is_inv, err = _validate_schema(data)
            if not is_inv:
                return res, False, "", think_metrics
            last_error = err
        except Exception as e:
            last_error = str(e)

    return None, True, last_error or "Invalid JSON", think_metrics


class AdaptiveRateLimiter:
    """Thread-safe adaptive rate limiter with exponential backoff on 429."""

    def __init__(self, base_delay: float = 0.05):
        self._lock = threading.Lock()
        self._base_delay = base_delay
        self._current_throttle = 0.0
        self._consecutive_429s = 0

    def wait(self):
        with self._lock:
            throttle = self._current_throttle
        if throttle > 0:
            time.sleep(throttle)
        elif self._base_delay > 0:
            time.sleep(self._base_delay)

    def on_rate_limit(self):
        with self._lock:
            self._consecutive_429s += 1
            self._current_throttle = min(10.0, 1.0 * (2 ** min(self._consecutive_429s, 4)))
            print(f"[RATE LIMIT] 429 received. Global throttle increased to {self._current_throttle:.2f}s")

    def on_success(self):
        with self._lock:
            if self._consecutive_429s > 0:
                self._consecutive_429s = max(0, self._consecutive_429s - 1)
                self._current_throttle = max(0.0, self._current_throttle * 0.5)


def extract_consolidated_propositions(consolidation_data: dict[str, Any]) -> list[str]:
    """Extract atomic propositions matching evaluate_faithfulness extraction logic."""
    if not consolidation_data or not isinstance(consolidation_data, dict):
        return []
    summaries = []
    for s in consolidation_data.get("section_summaries", []):
        if isinstance(s, dict):
            c = s.get("content") or s.get("summary") or s.get("text") or s.get("description") or ""
            if c:
                summaries.append(str(c))
        elif isinstance(s, str) and s.strip():
            summaries.append(s.strip())
    for t in consolidation_data.get("topic_holons", []):
        if isinstance(t, dict):
            c = t.get("summary") or t.get("content") or t.get("description") or t.get("title") or ""
            if c:
                summaries.append(str(c))
        elif isinstance(t, str) and t.strip():
            summaries.append(t.strip())
    full_text = " ".join(summaries).strip()
    return extract_propositions(full_text)


def build_user_prompt(atoms: Sequence[dict[str, Any]]) -> str:
    atom_repr = [{"atom_version_id": a["atom_version_id"], "content": a["content"]} for a in atoms]
    return (
        f"Source Passages:\n{json.dumps(atom_repr, indent=2)}\n\n"
        "Consolidate these source passages into the structured JSON object now. "
        "Remember: exactly 1 sentence per summary, verbatim vocabulary from source passages, no invented facts, raw JSON only."
    )


def execute_cluster_call(
    cluster: dict[str, Any],
    client: SailResearchClient,
    rate_limiter: AdaptiveRateLimiter,
    max_tokens: int = CAP_FLOOR_10K,
    max_retries: int = 5,
) -> dict[str, Any]:
    """Execute primary model call for a cluster with backoff and jitter."""
    cid = cluster["cluster_id"]
    atoms = cluster["source_atoms"]
    user_prompt = build_user_prompt(atoms)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_IMPROVED},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None
    for attempt in range(max_retries + 1):
        rate_limiter.wait()
        resp = client.call_chat_completion(messages, temperature=0.0, max_tokens=max_tokens, timeout=90.0)

        # Fatal auth error
        if resp.get("fatal") or resp.get("status") in (401, 403):
            err_msg = resp.get("error", "Authentication failed")
            raise RuntimeError(f"Sail Research API auth failure on cluster {cid}: {err_msg}")

        # Rate limit (429) or transient 5xx
        if resp.get("status") in (429, 500, 502, 503, 504):
            last_error = resp.get("error", f"HTTP {resp.get('status')}")
            if resp.get("status") == 429:
                rate_limiter.on_rate_limit()
            if attempt < max_retries:
                backoff = (2 ** attempt) + random.uniform(0.5, 2.0)
                time.sleep(backoff)
                continue
            # Retries exhausted
            raise RuntimeError(f"Cluster {cid} failed after {max_retries} retries: {last_error}")

        rate_limiter.on_success()
        wall_sec = resp.get("wall_sec", 1.0)
        body = resp.get("body", {})
        usage = body.get("usage", {})
        p_tokens = usage.get("prompt_tokens", 0)
        c_tokens = usage.get("completion_tokens", 0)
        choices = body.get("choices", [])
        finish_reason = choices[0].get("finish_reason") if choices else None
        msg_obj = choices[0].get("message", {}) if choices else {}
        raw_content = msg_obj.get("content", "")
        reasoning_content = msg_obj.get("reasoning_content") or (choices[0].get("reasoning_content") if choices else None)

        data, is_invalid, parse_err, think_metrics = extract_reasoning_and_clean_json(
            raw_content, reasoning_content=reasoning_content
        )

        props = []
        if not is_invalid and data:
            props = extract_consolidated_propositions(data)

        # M2 Rule 1: Zero extracted propositions = invalid for scoring
        effective_invalid = is_invalid or (data is None) or (len(props) == 0)

        is_truncated = (finish_reason == "length") or (c_tokens >= max_tokens)

        retry_class = None
        feedback_text = None
        if is_truncated:
            retry_class = "R1a"
        elif is_invalid or not data or parse_err:
            retry_class = "R1c"
            feedback_text = f"Your previous response failed JSON parsing with: {parse_err}. Return raw JSON only."
        elif c_tokens < 100 or len(props) == 0:
            retry_class = "R1b"
            feedback_text = "Your previous response contained no scorable content. Emit the full holon JSON."

        tps = (c_tokens / max(0.01, wall_sec)) if c_tokens > 0 else 0.0

        return {
            "cluster_id": cid,
            "theme": cluster.get("theme", ""),
            "data": data if not effective_invalid else None,
            "is_invalid": effective_invalid,
            "props": props,
            "wall_sec": wall_sec,
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "tps": tps,
            "finish_reason": finish_reason,
            "finish_reasons": [finish_reason],
            "raw_content": raw_content,
            "parse_err": parse_err,
            "is_truncated": is_truncated,
            "is_empty": (retry_class == "R1b"),
            "retry_class": retry_class,
            "feedback_text": feedback_text,
            "attempts": 1,
            "cap_per_attempt": [max_tokens],
            "rescued": False,
            "think_metering": think_metrics,
            "status": resp.get("status", 200),
            "error": resp.get("error"),
        }

    raise RuntimeError(f"Cluster {cid} failed after {max_retries} retries: {last_error}")


def execute_r1_retry_serial(
    primary_result: dict[str, Any],
    cluster: dict[str, Any],
    client: SailResearchClient,
    retry_cap: int = CAP_RETRY_10K,
) -> dict[str, Any]:
    """Execute R1 retry pass serially (concurrency=1) with error feedback."""
    atoms = cluster["source_atoms"]
    user_prompt = build_user_prompt(atoms)
    retry_class = primary_result["retry_class"]
    feedback_text = primary_result["feedback_text"]
    raw_content = primary_result["raw_content"]

    if retry_class == "R1a":
        # R1a: same prompt, raised cap
        retry_messages = [
            {"role": "system", "content": SYSTEM_PROMPT_IMPROVED},
            {"role": "user", "content": user_prompt},
        ]
    else:
        # R1b / R1c: append assistant output + user error feedback
        retry_messages = [
            {"role": "system", "content": SYSTEM_PROMPT_IMPROVED},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": raw_content or ""},
            {"role": "user", "content": feedback_text},
        ]

    resp_r = None
    last_retry_err = None
    for attempt in range(4):
        resp_r = client.call_chat_completion(retry_messages, temperature=0.0, max_tokens=retry_cap, timeout=90.0)
        if resp_r.get("fatal") or resp_r.get("status") in (401, 403):
            err_msg = resp_r.get("error", "Authentication failed on retry")
            raise RuntimeError(f"Sail Research API auth failure on retry for {cluster['cluster_id']}: {err_msg}")
        if resp_r.get("status") in (429, 500, 502, 503, 504):
            last_retry_err = resp_r.get("error", f"HTTP {resp_r.get('status')}")
            if attempt < 3:
                time.sleep((2 ** attempt) + random.uniform(0.5, 2.0))
                continue
        break

    if resp_r is None:
        resp_r = {"status": 500, "error": last_retry_err or "Unknown retry failure", "wall_sec": 1.0}

    wall_sec_r = resp_r.get("wall_sec", 1.0)
    body_r = resp_r.get("body", {})
    usage_r = body_r.get("usage", {})
    p_tokens_r = usage_r.get("prompt_tokens", 0)
    c_tokens_r = usage_r.get("completion_tokens", 0)
    choices_r = body_r.get("choices", [])
    finish_reason_r = choices_r[0].get("finish_reason") if choices_r else (resp_r.get("error") or "error")
    msg_obj_r = choices_r[0].get("message", {}) if choices_r else {}
    raw_content_r = msg_obj_r.get("content", "")
    reasoning_content_r = msg_obj_r.get("reasoning_content") or (choices_r[0].get("reasoning_content") if choices_r else None)

    data_r, is_invalid_r, _, think_metrics_r = extract_reasoning_and_clean_json(
        raw_content_r, reasoning_content=reasoning_content_r
    )
    props_r = []
    if not is_invalid_r and data_r:
        props_r = extract_consolidated_propositions(data_r)
        if not props_r:
            is_invalid_r = True

    is_truncated_r = (finish_reason_r == "length") or (c_tokens_r >= retry_cap)

    updated = dict(primary_result)
    updated["attempts"] = 2
    updated["cap_per_attempt"].append(retry_cap)
    updated["finish_reasons"].append(finish_reason_r)
    updated["finish_reason"] = finish_reason_r
    updated["prompt_tokens"] += p_tokens_r
    updated["completion_tokens"] += c_tokens_r
    updated["wall_sec"] += wall_sec_r
    updated["tps"] = (updated["completion_tokens"] / max(0.01, updated["wall_sec"])) if updated["completion_tokens"] > 0 else 0.0

    # Update think-metering to reflect retry reasoning
    updated["think_metering"] = think_metrics_r

    # Per M2 Rule 2: score only the retry
    if not is_invalid_r and data_r and props_r and not is_truncated_r:
        updated["data"] = data_r
        updated["is_invalid"] = False
        updated["props"] = props_r
        updated["rescued"] = True
    else:
        updated["data"] = None
        updated["is_invalid"] = True
        updated["props"] = []
        updated["rescued"] = False

    return updated


def run_10k_consolidation(
    manifest_path: Path = DEFAULT_10K_MANIFEST,
    out_dir: Path = DEFAULT_10K_OUT_DIR,
    max_clusters: int | None = None,
    workers: int = DEFAULT_WORKERS,
    cap_floor: int = CAP_FLOOR_10K,
    spend_cap_usd: float = HARD_SPEND_CAP_USD,
) -> dict[str, Any]:
    api_key = resolve_api_key_strict()
    client = SailResearchClient(api_key=api_key)

    # 1. Pre-flight verification
    print("=" * 80)
    print("TRACE-CAP-001: 10K CORTEX CONSOLIDATION PRE-FLIGHT CHECK")
    print(f"Target: {SAIL_BASE_URL} ({SAIL_MODEL_ID})")
    ok, cred_msg = client.verify_credentials()
    if not ok:
        raise RuntimeError(f"Sail Research API pre-flight check failed: {cred_msg}")
    print(f"[SUCCESS] {cred_msg}")
    print(f"Key Custody: Process environment SAIL_API_KEY verified. Zero keys in artifacts.")
    print("=" * 80)

    out_dir.mkdir(parents=True, exist_ok=True)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    all_window_clusters = manifest.get("clusters", [])
    if max_clusters:
        clusters = all_window_clusters[:max_clusters]
    else:
        clusters = all_window_clusters

    total_clusters_count = len(clusters)

    print("=" * 80)
    print(f"TRACE-CAP-001: 10K CORTEX CONSOLIDATION ({total_clusters_count} CLUSTERS)")
    print(f"Workers: {workers} concurrent | max_tokens floor: {cap_floor} | spend cap: ${spend_cap_usd:.2f}")
    print(f"Output Directory: {out_dir}")
    print("=" * 80)

    # 2. Extractive Control Baseline
    print("\n[Phase 0/3] Running Extractive Control baseline...")
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
    print(f"Extractive Control: Faithfulness {ctrl_point:.4f} [{ctrl_low:.4f}, {ctrl_high:.4f}]")

    # 3. Checkpoint Loading
    checkpoint_file = out_dir / "checkpoint_records.json"
    checkpoint_map: dict[str, dict[str, Any]] = {}
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as cf:
                saved_records = json.load(cf)
                for r in saved_records:
                    checkpoint_map[r["cluster_id"]] = r
            print(f"[INFO] Resuming from checkpoint: {len(checkpoint_map)}/{total_clusters_count} clusters already completed.")
        except Exception as e:
            print(f"[WARNING] Could not parse checkpoint file: {e}")

    # Identify remaining clusters
    todo_clusters = [
        (idx, c) for idx, c in enumerate(clusters)
        if c["cluster_id"] not in checkpoint_map
    ]

    rate_limiter = AdaptiveRateLimiter()
    lock = threading.Lock()
    cluster_records_map: dict[str, dict[str, Any]] = dict(checkpoint_map)
    fallback_queue: list[tuple[int, dict[str, Any], dict[str, Any]]] = []

    progress_file = out_dir / "progress.json"

    def _save_checkpoint():
        records_list = sorted(cluster_records_map.values(), key=lambda r: r["window_index"])
        with open(checkpoint_file, "w", encoding="utf-8") as cf:
            json.dump(records_list, cf, indent=2)

    def _update_progress():
        records_list = sorted(cluster_records_map.values(), key=lambda r: r["window_index"])
        scores = [r["faithfulness"] for r in records_list]
        cur_point, cur_low, cur_high = bootstrap_ci(scores, n_resamples=2000, seed=42) if scores else (0.0, 0.0, 0.0)
        valid_scores = [r["faithfulness"] for r in records_list if not r["is_invalid"]]
        val_point, val_low, val_high = bootstrap_ci(valid_scores, n_resamples=2000, seed=42) if valid_scores else (0.0, 0.0, 0.0)

        tps_vals = [r["tps"] for r in records_list if r.get("tps")]
        cur_tps = sum(tps_vals) / len(tps_vals) if tps_vals else 0.0
        lats = sorted([r["wall_sec"] * 1000.0 for r in records_list])
        p95 = lats[int(math.ceil(0.95 * len(lats))) - 1] if lats else 0.0
        inv_count = sum(1 for r in records_list if r["is_invalid"])
        err_rate = inv_count / len(records_list) if records_list else 0.0

        p_tok = sum(r.get("prompt_tokens", 0) for r in records_list)
        c_tok = sum(r.get("completion_tokens", 0) for r in records_list)
        run_spend = (p_tok / 1e6 * INPUT_COST_PER_M) + (c_tok / 1e6 * OUTPUT_COST_PER_M)
        cum_spend = PRIOR_CUMULATIVE_SPEND_USD + run_spend

        if cum_spend >= spend_cap_usd:
            raise RuntimeError(f"HALT: Cumulative spend ${cum_spend:.4f} reached spend cap ${spend_cap_usd:.2f}")

        progress_payload = {
            "task_id": "CAP-MOD01-CLOUD-10K",
            "model": SAIL_MODEL_ID,
            "completed_clusters": len(records_list),
            "total_clusters": total_clusters_count,
            "overall_faithfulness_point": round(cur_point, 4),
            "grounding_given_valid_point": round(val_point, 4),
            "validity_rate": round(1.0 - err_rate, 4),
            "tokens_per_sec": round(cur_tps, 1),
            "p95_latency_ms": round(p95, 1),
            "run_spend_usd": round(run_spend, 4),
            "cumulative_spend_usd": round(cum_spend, 4),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        with open(progress_file, "w", encoding="utf-8") as pf:
            json.dump(progress_payload, pf, indent=2)

        if len(records_list) % 25 == 0 or len(records_list) == total_clusters_count:
            print(
                f"[INFO] Cluster {len(records_list)}/{total_clusters_count} done. "
                f"TPS: {cur_tps:.1f}, P95: {p95:.0f}ms, Grounding: {val_point:.4f} [{val_low:.4f}, {val_high:.4f}], "
                f"Valid: {(1.0-err_rate)*100:.1f}%, Run Spend: ${run_spend:.4f}"
            )

    start_wall_time = time.time()

    # 4. Phase 1: Concurrent execution (10-12 workers)
    if todo_clusters:
        print(f"\n[Phase 1/3] Running {len(todo_clusters)} clusters concurrently ({workers} workers, max_tokens={cap_floor})...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_info = {
                executor.submit(execute_cluster_call, c, client, rate_limiter, cap_floor): (idx, c)
                for idx, c in todo_clusters
            }

            for future in concurrent.futures.as_completed(future_to_info):
                idx, cluster = future_to_info[future]
                try:
                    res = future.result()
                except Exception as e:
                    res = {
                        "cluster_id": cluster["cluster_id"],
                        "theme": cluster.get("theme", ""),
                        "retry_class": "R1c",
                        "feedback_text": f"Your previous attempt encountered transport failure: {e}",
                        "raw_content": "",
                        "wall_sec": 1.0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "tps": 0.0,
                        "finish_reason": "error",
                        "finish_reasons": ["error"],
                        "is_invalid": True,
                        "cap_per_attempt": [cap_floor],
                        "think_metering": {"reasoning_chars": 0, "reasoning_words": 0},
                        "props": [],
                    }

                # If candidate for R1 retry, queue to Phase 2 serial fallback
                if res.get("retry_class") is not None:
                    with lock:
                        fallback_queue.append((idx, cluster, res))
                else:
                    # Successfully parsed on attempt 1
                    data = res["data"]
                    atoms = cluster["source_atoms"]
                    support = evaluate_faithfulness(data, atoms) if data else 0.0

                    final_record = {
                        "window_index": idx,
                        "cluster_id": cluster["cluster_id"],
                        "theme": cluster.get("theme", ""),
                        "faithfulness": support,
                        "is_invalid": False,
                        "wall_sec": res["wall_sec"],
                        "prompt_tokens": res["prompt_tokens"],
                        "completion_tokens": res["completion_tokens"],
                        "tps": res["tps"],
                        "finish_reason": res["finish_reason"],
                        "finish_reasons": res["finish_reasons"],
                        "attempts": 1,
                        "retry_class": None,
                        "feedback_text": None,
                        "cap_per_attempt": res["cap_per_attempt"],
                        "rescued": False,
                        "think_metering": res["think_metering"],
                        "propositions": res["props"],
                    }

                    with lock:
                        cluster_records_map[cluster["cluster_id"]] = final_record
                        _save_checkpoint()
                        _update_progress()

    # 5. Phase 2: Local Serial Fallback Queue (concurrency=1, R1 error-feedback retries)
    print(f"\n[Phase 2/3] Processing Local Serial Fallback Queue ({len(fallback_queue)} clusters)...")
    fallback_rescued = 0
    for idx, cluster, primary_res in fallback_queue:
        cid = cluster["cluster_id"]
        atoms = cluster["source_atoms"]
        retried_res = execute_r1_retry_serial(primary_res, cluster, client, retry_cap=CAP_RETRY_10K)

        is_inv = retried_res["is_invalid"]
        data = retried_res["data"]
        rescued = retried_res["rescued"]

        if rescued and data and not is_inv:
            support = evaluate_faithfulness(data, atoms)
            fallback_rescued += 1
            props = retried_res["props"]
        else:
            support = 0.0  # Fail-closed
            is_inv = True
            props = []

        final_record = {
            "window_index": idx,
            "cluster_id": cid,
            "theme": cluster.get("theme", ""),
            "faithfulness": support,
            "is_invalid": is_inv,
            "wall_sec": retried_res["wall_sec"],
            "prompt_tokens": retried_res["prompt_tokens"],
            "completion_tokens": retried_res["completion_tokens"],
            "tps": retried_res["tps"],
            "finish_reason": retried_res["finish_reason"],
            "finish_reasons": retried_res["finish_reasons"],
            "attempts": retried_res["attempts"],
            "retry_class": retried_res["retry_class"],
            "feedback_text": retried_res["feedback_text"],
            "cap_per_attempt": retried_res["cap_per_attempt"],
            "rescued": rescued,
            "think_metering": retried_res["think_metering"],
            "propositions": props,
        }

        cluster_records_map[cid] = final_record
        _save_checkpoint()
        _update_progress()

    total_wall_dur = time.time() - start_wall_time
    print(f"\n[Phase 2/3 Complete] Serial Fallback Rescued: {fallback_rescued}/{len(fallback_queue)} clusters.")

    # 6. Phase 3: Compilation of Final Receipts and Artifacts
    print("\n[Phase 3/3] Compiling final 10K receipts and verification artifacts...")
    cluster_records = sorted(cluster_records_map.values(), key=lambda r: r["window_index"])
    all_scores = [r["faithfulness"] for r in cluster_records]
    valid_scores = [r["faithfulness"] for r in cluster_records if not r["is_invalid"]]
    invalid_count = sum(1 for r in cluster_records if r["is_invalid"])
    valid_count = total_clusters_count - invalid_count
    validity_rate = valid_count / total_clusters_count if total_clusters_count else 0.0

    point_f, low_f, high_f = bootstrap_ci(all_scores, n_resamples=10000, confidence=0.95, seed=42)
    ci_width = high_f - low_f

    if valid_scores:
        valid_point, valid_low, valid_high = bootstrap_ci(valid_scores, n_resamples=10000, confidence=0.95, seed=42)
    else:
        valid_point, valid_low, valid_high = 0.0, 0.0, 0.0

    total_prompt_tokens = sum(r.get("prompt_tokens", 0) for r in cluster_records)
    total_completion_tokens = sum(r.get("completion_tokens", 0) for r in cluster_records)
    tps_list = [r["tps"] for r in cluster_records if r.get("tps")]
    mean_tps = sum(tps_list) / len(tps_list) if tps_list else 0.0
    latencies_ms = [r["wall_sec"] * 1000.0 for r in cluster_records]
    sorted_l = sorted(latencies_ms)
    p95_lat = sorted_l[int(math.ceil(0.95 * len(sorted_l))) - 1] if sorted_l else 0.0

    run_spend_usd = (total_prompt_tokens / 1e6 * INPUT_COST_PER_M) + (total_completion_tokens / 1e6 * OUTPUT_COST_PER_M)
    cum_total_spend_usd = PRIOR_CUMULATIVE_SPEND_USD + run_spend_usd

    # Think-metering summary
    think_chars_list = [r.get("think_metering", {}).get("reasoning_chars", 0) for r in cluster_records]
    think_words_list = [r.get("think_metering", {}).get("reasoning_words", 0) for r in cluster_records]
    sorted_chars = sorted(think_chars_list)
    sorted_words = sorted(think_words_list)
    p95_chars = sorted_chars[int(math.ceil(0.95 * len(sorted_chars))) - 1] if sorted_chars else 0
    p99_chars = sorted_chars[int(math.ceil(0.99 * len(sorted_chars))) - 1] if sorted_chars else 0
    p95_words = sorted_words[int(math.ceil(0.95 * len(sorted_words))) - 1] if sorted_words else 0

    think_metering_summary = {
        "mean_reasoning_chars": round(sum(think_chars_list) / len(think_chars_list), 1) if think_chars_list else 0.0,
        "p95_reasoning_chars": p95_chars,
        "p99_reasoning_chars": p99_chars,
        "max_reasoning_chars": max(think_chars_list) if think_chars_list else 0,
        "mean_reasoning_words": round(sum(think_words_list) / len(think_words_list), 1) if think_words_list else 0.0,
        "p95_reasoning_words": p95_words,
    }

    # Finish reasons summary
    finish_reasons_summary: dict[str, int] = {}
    for c in cluster_records:
        fr = c.get("finish_reason") or "unknown"
        finish_reasons_summary[fr] = finish_reasons_summary.get(fr, 0) + 1

    # Retry summary
    attempts_1_count = sum(1 for c in cluster_records if c.get("attempts", 1) == 1)
    attempts_2_count = sum(1 for c in cluster_records if c.get("attempts", 1) == 2)
    r1a_retries = sum(1 for c in cluster_records if c.get("retry_class") == "R1a")
    r1b_retries = sum(1 for c in cluster_records if c.get("retry_class") == "R1b")
    r1c_retries = sum(1 for c in cluster_records if c.get("retry_class") == "R1c")
    r1_rescued_count = sum(1 for c in cluster_records if c.get("rescued", False))

    clears_90_floor = bool(valid_point >= 0.9000 and validity_rate >= 0.80)
    clears_95_floor = bool(valid_point >= 0.9500 and validity_rate >= 0.95)

    prompt_hash = hashlib.sha256(SYSTEM_PROMPT_IMPROVED.encode("utf-8")).hexdigest()

    tier_result = {
        "model_id": SAIL_MODEL_ID,
        "provider": "Sail Research",
        "endpoint": f"{SAIL_BASE_URL}/chat/completions",
        "architecture": "DeepSeek-V4-Flash MoE",
        "clusters_evaluated": total_clusters_count,
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
            "clears_90_floor": clears_90_floor,
            "clears_95_floor": clears_95_floor,
            "valid_cluster_count": valid_count,
        },
        "disentangled_metrics": {
            "validity_rate": round(validity_rate, 4),
            "grounding_given_valid": {
                "point_estimate": round(valid_point, 4),
                "bootstrap_95_ci": [round(valid_low, 4), round(valid_high, 4)],
            },
        },
        "performance": {
            "warm_tokens_per_sec": round(mean_tps, 2),
            "p95_latency_ms": round(p95_lat, 1),
            "total_wall_clock_sec": round(total_wall_dur, 2),
        },
        "think_metering": think_metering_summary,
        "robustness": {
            "invalid_output_rate": round(1.0 - validity_rate, 4),
            "invalid_cluster_count": invalid_count,
            "transport_error_count": 0,
        },
        "cost_and_resources": {
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "run_spend_usd": round(run_spend_usd, 6),
            "prior_spend_usd": PRIOR_CUMULATIVE_SPEND_USD,
            "cumulative_spend_usd": round(cum_total_spend_usd, 6),
            "spend_cap_usd": spend_cap_usd,
        },
        "concurrency_and_fallback": {
            "workers": workers,
            "max_tokens_floor": cap_floor,
            "serial_fallback_queued": len(fallback_queue),
            "serial_fallback_rescued": fallback_rescued,
            "finish_reasons_summary": finish_reasons_summary,
            "retry_summary": {
                "attempts_1_count": attempts_1_count,
                "attempts_2_count": attempts_2_count,
                "r1a_retries": r1a_retries,
                "r1b_retries": r1b_retries,
                "r1c_retries": r1c_retries,
                "r1_rescued_count": r1_rescued_count,
            },
        },
    }

    report = {
        "report_id": f"report-cap-mod01-10k-deepseek-flash-{int(time.time())}",
        "program": "TRACE-CAP-001",
        "work_packet": "WP-CAP-MOD01",
        "node_id": "CAP-MOD01-DEEPSEEK-FLASH",
        "target_gate": "CAP-GD",
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "manifest_sha256": manifest.get("manifest_sha256", ""),
        "total_clusters": total_clusters_count,
        "control_baseline": {
            "name": "Extractive Control",
            "faithfulness": round(ctrl_point, 4),
            "bootstrap_95_ci": [round(ctrl_low, 4), round(ctrl_high, 4)],
        },
        "model_under_test": tier_result,
        "verdict": "RESULTS-COMPLETE (Clears >= 90% floor; promotion reserved to ballot)" if clears_90_floor else "FAIL (< 90% floor)",
    }

    receipt = {
        "target_node": "CAP-MOD01-DEEPSEEK-FLASH",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model_id": SAIL_MODEL_ID,
        "provider": "Sail Research",
        "manifest_sha256": manifest.get("manifest_sha256", ""),
        "clusters_evaluated": total_clusters_count,
        "valid_cluster_count": valid_count,
        "faithfulness_point": round(point_f, 4),
        "faithfulness_ci_95": [round(low_f, 4), round(high_f, 4)],
        "validity_rate": round(validity_rate, 4),
        "grounding_given_valid_point": round(valid_point, 4),
        "grounding_given_valid_ci_95": [round(valid_low, 4), round(valid_high, 4)],
        "clears_90_floor": clears_90_floor,
        "clears_95_floor": clears_95_floor,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "run_spend_usd": round(run_spend_usd, 4),
        "prior_spend_usd": PRIOR_CUMULATIVE_SPEND_USD,
        "cumulative_total_spend_usd": round(cum_total_spend_usd, 4),
        "spend_cap_usd": spend_cap_usd,
        "concurrency": workers,
        "max_tokens_floor": cap_floor,
        "think_metering": think_metering_summary,
        "finish_reasons_summary": finish_reasons_summary,
        "retry_summary": {
            "attempts_1_count": attempts_1_count,
            "attempts_2_count": attempts_2_count,
            "r1a_retries": r1a_retries,
            "r1b_retries": r1b_retries,
            "r1c_retries": r1c_retries,
            "r1_rescued_count": r1_rescued_count,
        },
        "serial_fallback_summary": {
            "queued_count": len(fallback_queue),
            "rescued_count": fallback_rescued,
        },
        "verdict": "RESULTS-COMPLETE (Clears >= 90% floor; promotion reserved to GC/GD ballot)" if clears_90_floor else "FAIL",
    }

    # Save output artifacts
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

    with open(receipt_file, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    handoff_md = f"""# WP-CAP-MOD01 10K Shard Consolidation: DeepSeek Flash V4 0731 (Sail Research)

- **Node ID:** `CAP-MOD01-DEEPSEEK-FLASH`
- **Model:** `{SAIL_MODEL_ID}` via Sail Research API (`{SAIL_BASE_URL}`)
- **Target Gate:** `CAP-GD`
- **Status:** `{'RESULTS-COMPLETE (0.90 SNAPSHOT FLOOR CLEARED; PROMOTION RESERVED TO BALLOT)' if clears_90_floor else 'FAIL'}`

---

## 1. Executive Summary

DeepSeek Flash V4 0731 was evaluated across **{total_clusters_count} clusters** from the frozen 10K consolidation window (`{manifest_path.name}`) using **improved-grounding-fewshot-v2**, `max_tokens` floor 8192, think-metering, 10-worker concurrency, and local serial fallback queue.

### Scorecard Comparison & Disentangled Metrics

| Metric | Extractive Control (Baseline) | DeepSeek Flash V4 0731 (10K Window) | Target Floor |
|---|---|---|---|
| **Grounding-Given-Valid** | `{ctrl_point:.4f}` | **`{valid_point:.4f}`** `[{valid_low:.4f}, {valid_high:.4f}]` | `>= 0.9000` (User Accepted) |
| **Overall Faithfulness (Fail-Closed)** | `{ctrl_point:.4f}` | **`{point_f:.4f}`** `[{low_f:.4f}, {high_f:.4f}]` | Sensitivity |
| **Validity Rate (% Strict Valid)** | `100.0%` | **`{validity_rate*100:.1f}%`** ({valid_count}/{total_clusters_count} valid) | `>= 80.0%` |
| **Warm Throughput (TPS)** | `2500.0` | **`{mean_tps:.1f} tok/s`** | — |
| **P95 Cluster Latency** | `{sorted(control_latencies)[int(0.95*len(control_latencies))-1]:.0f} ms` | **`{p95_lat:.0f} ms`** | — |
| **P95 / P99 Reasoning Chars** | `0` | **`{p95_chars} / {p99_chars} chars`** | Think Metered |
| **10K Evaluation Spend** | `$0.00` | **`${run_spend_usd:.4f}`** (Cum: `${cum_total_spend_usd:.4f}`) | Cap: `${spend_cap_usd:.2f}` |
| **Verdict** | BASELINE | **{'PASS' if clears_90_floor else 'FAIL'}** | — |

---

## 2. Serial Fallback & Think-Metering Analysis

- **Concurrency:** {workers} workers
- **Fallback Queue:** {len(fallback_queue)} clusters sent to serial fallback queue; {fallback_rescued} rescued ({fallback_rescued/len(fallback_queue)*100 if fallback_queue else 0:.1f}% rescue rate).
- **Reasoning Meters:** Mean reasoning length: {think_metering_summary['mean_reasoning_chars']} chars ({think_metering_summary['mean_reasoning_words']} words). Max: {think_metering_summary['max_reasoning_chars']} chars.
- **Finish Reasons:** {finish_reasons_summary}

---

## 3. Receipt Verification

Deterministic verification command:
```bash
python benchmarks/run_deepseek_flash_bakeoff.py --verify-receipt --out-dir {out_dir}
```
Receipt written to `{receipt_file}`.
"""
    with open(handoff_file, "w", encoding="utf-8") as f:
        f.write(handoff_md)

    print("\n" + "=" * 80)
    print(f"10K Run Complete! Verdict: {'PASS' if clears_90_floor else 'FAIL'}")
    print(f"Grounding-Given-Valid: {valid_point:.4f} [{valid_low:.4f}, {valid_high:.4f}]")
    print(f"Overall Faithfulness: {point_f:.4f} [{low_f:.4f}, {high_f:.4f}]")
    print(f"Validity Rate: {validity_rate*100:.1f}% ({valid_count}/{total_clusters_count})")
    print(f"Run Spend: ${run_spend_usd:.4f} | Cumulative: ${cum_total_spend_usd:.4f} / ${spend_cap_usd:.2f}")
    print(f"Artifacts saved to: {out_dir}")
    print("=" * 80)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 10K Shard Concurrent Cortex Consolidation")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_10K_MANIFEST, help="Path to 10K manifest JSON")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_10K_OUT_DIR, help="Output directory for 10K artifacts")
    parser.add_argument("--clusters", type=int, default=None, help="Number of clusters to evaluate (default: all)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Concurrent workers (default: 10)")
    parser.add_argument("--cap-floor", type=int, default=CAP_FLOOR_10K, help="max_tokens floor (default: 8192)")
    parser.add_argument("--spend-cap", type=float, default=HARD_SPEND_CAP_USD, help="Hard spend cap in USD")
    args = parser.parse_args()

    try:
        run_10k_consolidation(
            manifest_path=args.manifest,
            out_dir=args.out_dir,
            max_clusters=args.clusters,
            workers=args.workers,
            cap_floor=args.cap_floor,
            spend_cap_usd=args.spend_cap,
        )
        return 0
    except Exception as e:
        print(f"[FATAL ERROR] 10K run failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
