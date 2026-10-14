"""Comprehensive unit tests for 10K concurrent runner, assembler, R1 retry protocol, and think-metering."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from benchmarks.assemble_10k_clusters import sample_strided_clusters
from benchmarks.run_deepseek_flash_concurrent_10k import (
    AdaptiveRateLimiter,
    execute_cluster_call,
    execute_r1_retry_serial,
    extract_reasoning_and_clean_json,
    resolve_api_key_strict,
)


class TestConcurrent10kRunner(unittest.TestCase):
    def test_extract_reasoning_and_clean_json_valid_direct(self) -> None:
        raw = json.dumps({
            "section_summaries": [{"section_id": "sec_1", "content": "Fact one."}],
            "topic_holons": [{"topic_id": "topic_001", "summary": "Topic fact."}],
        })
        data, is_inv, _err, think_m = extract_reasoning_and_clean_json(raw)
        self.assertFalse(is_inv)
        self.assertIsNotNone(data)
        self.assertEqual(len(data["section_summaries"]), 1)
        self.assertEqual(think_m["reasoning_chars"], 0)
        self.assertEqual(think_m["reasoning_words"], 0)

    def test_extract_reasoning_with_think_tags(self) -> None:
        raw = """<think>
Evaluating source passages and checking for consistency.
Need to adhere to single sentence per summary.
</think>
```json
{
  "section_summaries": [{"section_id": "sec_1", "content": "Fact one."}],
  "topic_holons": [{"topic_id": "topic_001", "summary": "Topic fact."}]
}
```"""
        data, is_inv, _err, think_m = extract_reasoning_and_clean_json(raw)
        self.assertFalse(is_inv)
        self.assertIsNotNone(data)
        self.assertGreater(think_m["reasoning_chars"], 50)
        self.assertGreater(think_m["reasoning_words"], 10)

    def test_extract_reasoning_with_explicit_reasoning_content(self) -> None:
        raw_json = json.dumps({
            "section_summaries": [{"section_id": "sec_1", "content": "Fact one."}],
            "topic_holons": [{"topic_id": "topic_001", "summary": "Topic fact."}],
        })
        reasoning_str = "Step 1: Parse entities. Step 2: Validate grounding. Step 3: Emit JSON."
        data, is_inv, _err, think_m = extract_reasoning_and_clean_json(
            raw_json, reasoning_content=reasoning_str
        )
        self.assertFalse(is_inv)
        self.assertIsNotNone(data)
        self.assertEqual(think_m["reasoning_chars"], len(reasoning_str))
        self.assertEqual(think_m["reasoning_words"], 12)

    def test_extract_reasoning_unclosed_markdown_fence(self) -> None:
        raw = '```json\n{"section_summaries": [{"section_id": "sec_1", "content": "Fact one."}], "topic_holons": [{"topic_id": "top_1", "summary": "Sum."}]}'
        data, is_inv, _err, _think_m = extract_reasoning_and_clean_json(raw)
        self.assertFalse(is_inv)
        self.assertIsNotNone(data)
        self.assertEqual(len(data["section_summaries"]), 1)

    def test_extract_reasoning_nested_wrapper(self) -> None:
        raw = json.dumps({
            "consolidation": {
                "section_summaries": [{"section_id": "sec_1", "content": "Fact one."}],
                "topic_holons": [{"topic_id": "top_1", "summary": "Sum."}],
            }
        })
        data, is_inv, _err, _think_m = extract_reasoning_and_clean_json(raw)
        self.assertFalse(is_inv)
        self.assertIsNotNone(data)
        self.assertIn("section_summaries", data)

    def test_r1_retry_classification_r1a_truncation(self) -> None:
        client_mock = MagicMock()
        client_mock.call_chat_completion.return_value = {
            "status": 200,
            "wall_sec": 1.0,
            "body": {
                "choices": [{
                    "finish_reason": "length",
                    "message": {"content": '{"section_summaries": ['},
                }],
                "usage": {"prompt_tokens": 500, "completion_tokens": 8192},
            },
        }
        cluster = {
            "cluster_id": "c_01",
            "source_atoms": [{"atom_version_id": "av_1", "content": "Test text"}],
        }
        res = execute_cluster_call(cluster, client_mock, AdaptiveRateLimiter(), max_tokens=8192)
        self.assertEqual(res["retry_class"], "R1a")
        self.assertTrue(res["is_truncated"])

    def test_r1_retry_classification_r1c_unparseable(self) -> None:
        client_mock = MagicMock()
        client_mock.call_chat_completion.return_value = {
            "status": 200,
            "wall_sec": 1.0,
            "body": {
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"content": "Not JSON at all, completely malformed output."},
                }],
                "usage": {"prompt_tokens": 500, "completion_tokens": 250},
            },
        }
        cluster = {
            "cluster_id": "c_02",
            "source_atoms": [{"atom_version_id": "av_1", "content": "Test text"}],
        }
        res = execute_cluster_call(cluster, client_mock, AdaptiveRateLimiter(), max_tokens=8192)
        self.assertEqual(res["retry_class"], "R1c")
        self.assertTrue(res["is_invalid"])
        self.assertIn("Your previous response failed JSON parsing with:", res["feedback_text"])

    def test_r1_retry_classification_r1b_empty(self) -> None:
        client_mock = MagicMock()
        client_mock.call_chat_completion.return_value = {
            "status": 200,
            "wall_sec": 1.0,
            "body": {
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"content": json.dumps({"section_summaries": [{"content": ""}], "topic_holons": []})},
                }],
                "usage": {"prompt_tokens": 500, "completion_tokens": 50},
            },
        }
        cluster = {
            "cluster_id": "c_03",
            "source_atoms": [{"atom_version_id": "av_1", "content": "Test text"}],
        }
        res = execute_cluster_call(cluster, client_mock, AdaptiveRateLimiter(), max_tokens=8192)
        self.assertEqual(res["retry_class"], "R1b")
        self.assertIn("no scorable content", res["feedback_text"])

    def test_serial_retry_tps_recalculated(self) -> None:
        client_mock = MagicMock()
        client_mock.call_chat_completion.return_value = {
            "status": 200,
            "wall_sec": 2.0,
            "body": {
                "choices": [{
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps({
                            "section_summaries": [{"section_id": "sec_1", "content": "Test text fact."}],
                            "topic_holons": [{"topic_id": "t_1", "summary": "Test text fact."}],
                        })
                    },
                }],
                "usage": {"prompt_tokens": 500, "completion_tokens": 200},
            },
        }
        cluster = {
            "cluster_id": "c_04",
            "source_atoms": [{"atom_version_id": "av_1", "content": "Test text fact."}],
        }
        primary_res = {
            "cluster_id": "c_04",
            "theme": "test",
            "retry_class": "R1c",
            "feedback_text": "fix json",
            "raw_content": "{malformed",
            "wall_sec": 1.0,
            "prompt_tokens": 500,
            "completion_tokens": 0,
            "tps": 0.0,
            "finish_reason": "stop",
            "finish_reasons": ["stop"],
            "is_invalid": True,
            "cap_per_attempt": [8192],
            "think_metering": {"reasoning_chars": 0, "reasoning_words": 0},
            "props": [],
        }
        retried = execute_r1_retry_serial(primary_res, cluster, client_mock, retry_cap=12288)
        self.assertTrue(retried["rescued"])
        self.assertFalse(retried["is_invalid"])
        self.assertGreater(retried["tps"], 50.0)
        self.assertEqual(retried["completion_tokens"], 200)
        self.assertEqual(retried["wall_sec"], 3.0)

    def test_adaptive_rate_limiter(self) -> None:
        limiter = AdaptiveRateLimiter(base_delay=0.01)
        self.assertEqual(limiter._current_throttle, 0.0)
        limiter.on_rate_limit()
        self.assertGreater(limiter._current_throttle, 0.0)
        first_throttle = limiter._current_throttle
        limiter.on_rate_limit()
        self.assertGreaterEqual(limiter._current_throttle, first_throttle)
        limiter.on_success()
        self.assertLess(limiter._current_throttle, limiter._current_throttle * 2)

    def test_strided_clusters_sampling(self) -> None:
        dummy_clusters = [{"cluster_id": f"c_{i}"} for i in range(7778)]
        sampled, indices, _meta = sample_strided_clusters(dummy_clusters, k=2000, seed=42)
        self.assertEqual(len(sampled), 2000)
        self.assertEqual(len(indices), 2000)
        self.assertEqual(len(set(indices)), 2000)
        self.assertEqual(indices, sorted(indices))
        self.assertGreaterEqual(min(indices), 0)
        self.assertLess(max(indices), 7778)

    def test_key_custody_strict(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                resolve_api_key_strict()
            self.assertIn("Key custody violation", str(ctx.exception))

        with patch.dict(os.environ, {"SAIL_API_KEY": "test-key-12345"}):
            key = resolve_api_key_strict()
            self.assertEqual(key, "test-key-12345")


class TestShadowLifecycle(unittest.TestCase):
    def test_queue_depth_cap_drill(self) -> None:
        from benchmarks.run_10k_shadow_lifecycle import drill_queue_depth_cap
        res = drill_queue_depth_cap(max_allowed_depth=5000)
        self.assertEqual(res["status"], "PASS")
        self.assertTrue(res["nominal_pass"])
        self.assertTrue(res["cap_pass"])
        self.assertTrue(res["alert_halt_triggered"])

    def test_crash_restart_drill(self) -> None:
        from benchmarks.run_10k_shadow_lifecycle import drill_crash_restart
        with tempfile.TemporaryDirectory() as tmpdir:
            chk_file = Path(tmpdir) / "checkpoint.json"
            dummy_records = [{"cluster_id": f"c_{i}"} for i in range(1200)]
            with open(chk_file, "w", encoding="utf-8") as f:
                json.dump(dummy_records, f)
            res = drill_crash_restart(chk_file)
            self.assertEqual(res["status"], "PASS")
            self.assertEqual(res["lost_events_count"], 0)
            self.assertEqual(res["duplicate_work_count"], 0)
            self.assertEqual(res["total_recovered_count"], 1200)

    def test_pointer_swap_and_rollback_drill(self) -> None:
        from benchmarks.run_10k_shadow_lifecycle import drill_pointer_swap_and_rollback
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_file = Path(tmpdir) / "raw.json"
            raw_payload = {
                "results": {
                    "disentangled_metrics": {
                        "grounding_given_valid": {"point_estimate": 0.95}
                    }
                },
                "clusters": [{"cluster_id": "c_1", "is_invalid": False}],
            }
            with open(raw_file, "w", encoding="utf-8") as f:
                json.dump(raw_payload, f)
            res = drill_pointer_swap_and_rollback(raw_file)
            self.assertEqual(res["status"], "PASS")
            self.assertEqual(res["pointer_swap"]["status_after_swap"], "active")
            self.assertEqual(res["rollback_drill"]["rolled_back_release_status"], "superseded")
            self.assertEqual(res["rollback_drill"]["dangling_aliases_count"], 0)

    def test_verify_shadow_receipt(self) -> None:
        from benchmarks.run_10k_shadow_lifecycle import verify_shadow_receipt
        out_dir = Path("docs/program/inbox/cap-mod01-cloud-10k/run-10k")
        ok, errors = verify_shadow_receipt(out_dir)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_shadow_verdict_language_non_usurping(self) -> None:
        out_dir = Path("docs/program/inbox/cap-mod01-cloud-10k/run-10k")
        for filename in ("model_bakeoff_report.json", "verification_receipt.json", "shadow_lifecycle_receipt.json", "retrieval_uplift_report.json"):
            filepath = out_dir / filename
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            verdict = data.get("verdict", "")
            self.assertTrue(
                "RESULTS-COMPLETE" in verdict,
                f"Artifact {filename} has unauthorized verdict: {verdict}"
            )
            self.assertIn("ballot", verdict.lower(), f"Artifact {filename} missing ballot reservation: {verdict}")

    def test_verify_bakeoff_receipt(self) -> None:
        from benchmarks.run_deepseek_flash_bakeoff import verify_receipt
        out_dir = Path("docs/program/inbox/cap-mod01-cloud-10k/run-10k")
        ok, errors = verify_receipt(out_dir)
        self.assertTrue(ok)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
