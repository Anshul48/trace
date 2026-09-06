import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import benchmarks.run_model_bakeoff as rmb


class TestStagedBakeoff(unittest.TestCase):
    def setUp(self):
        self.manifest_data = {
            "manifest_sha256": "dummy_sha_12345",
            "total_clusters": 12,
            "clusters": [
                {
                    "cluster_id": f"c_{i:03d}",
                    "theme": f"Theme {i}",
                    "source_atoms": [
                        {
                            "atom_version_id": f"av_{i}_01",
                            "content": f"Evidence content for cluster {i} discussing quantum mechanics.",
                            "properties": {"title": f"Atom {i}"},
                        }
                    ],
                }
                for i in range(12)
            ],
        }

    def test_staged_execution_and_checkpoint_preservation(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            manifest_path = tdp / "test_manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(self.manifest_data, f)

            out_dir = tdp / "out"
            out_dir.mkdir()

            # Pre-seed tiers 0-3 as completed in checkpoint
            preseeded_checkpoint = {
                "manifest": "test_manifest.json",
                "total_clusters": 12,
                "completed_tiers": {
                    m: {
                        "tier_index": idx,
                        "name": f"Tier {idx}",
                        "model_id": m,
                        "architecture": "Test Arch",
                        "params": "Test Params",
                        "clusters_evaluated": 12,
                        "faithfulness": {
                            "point_estimate": 0.96,
                            "bootstrap_95_ci": [0.95, 0.97],
                            "ci_width": 0.02,
                            "clears_95_floor": True,
                            "valid_cluster_count": 12,
                        },
                        "performance": {
                            "cold_load_sec": 1.0,
                            "warm_tokens_per_sec": 25.0,
                            "p95_latency_ms": 1000.0,
                            "total_wall_clock_sec": 12.0,
                        },
                        "robustness": {"invalid_output_rate": 0.0, "invalid_cluster_count": 0},
                        "cost_and_resources": {
                            "api_spend_usd": 0.0,
                            "vram_allocated_gb": 4.0,
                            "cost_per_1k_holons_usd": 0.0,
                            "energy_kwh_per_1k_holons": 0.01,
                        },
                    }
                    for idx, m in enumerate(["extractive_control", "gemma4:e4b", "qwen3:8b", "gemma4:12b"])
                },
                "cluster_cache": {},
            }
            with open(out_dir / "bakeoff_checkpoint.json", "w", encoding="utf-8") as f:
                json.dump(preseeded_checkpoint, f)

            mock_bridge = MagicMock()
            call_count = {"27b": 0, "26b": 0}

            def mock_call_ollama(endpoint, payload, timeout=180.0):
                model = payload.get("model", "")
                if "27b" in model:
                    call_count["27b"] += 1
                elif "26b" in model:
                    call_count["26b"] += 1
                return {
                    "status": 200,
                    "wall_sec": 0.05,
                    "body": {
                        "eval_count": 50,
                        "eval_duration": 2000000000,
                        "response": json.dumps(
                            {
                                "section_summaries": [
                                    {
                                        "section_id": "sec_01",
                                        "title": "T",
                                        "content": "Evidence content for cluster discussing quantum mechanics.",
                                        "anchor_atom_ids": ["av_01"],
                                        "token_count": 7,
                                    }
                                ],
                                "topic_holons": [
                                    {
                                        "topic_id": "topic_001",
                                        "title": "T",
                                        "summary": "Evidence content for cluster discussing quantum mechanics.",
                                        "source_atom_ids": ["av_01"],
                                        "parent_topic_id": None,
                                        "confidence": 1.0,
                                    }
                                ],
                                "entity_candidates": [],
                                "relation_candidates": [],
                            }
                        ),
                    },
                }

            mock_bridge.call_ollama.side_effect = mock_call_ollama

            with patch.object(rmb, "WindowsOllamaBridge", return_value=mock_bridge):
                # Step 1: Model A (qwen3.8:27b), clusters 0-3 (evaluates 3 clusters)
                r1 = rmb.run_bakeoff(
                    manifest_path,
                    max_clusters=12,
                    out_dir=out_dir,
                    resume=True,
                    target_model="qwen3.8:27b",
                    cluster_start=0,
                    cluster_end=3,
                )
                self.assertEqual(r1.get("status"), "in_progress")
                self.assertEqual(call_count["27b"], 3)

                with open(out_dir / "bakeoff_checkpoint.json", "r") as f:
                    cp1 = json.load(f)
                self.assertEqual(len(cp1["cluster_cache"]["qwen3.8:27b"]), 3)
                self.assertNotIn("qwen3.8:27b", cp1["completed_tiers"])

                # Step 2: Model B (gemma4:26b), clusters 0-3 (evaluates 3 clusters)
                r2 = rmb.run_bakeoff(
                    manifest_path,
                    max_clusters=12,
                    out_dir=out_dir,
                    resume=True,
                    target_model="gemma4:26b",
                    cluster_start=0,
                    cluster_end=3,
                )
                self.assertEqual(r2.get("status"), "in_progress")
                self.assertEqual(call_count["26b"], 3)

                with open(out_dir / "bakeoff_checkpoint.json", "r") as f:
                    cp2 = json.load(f)
                self.assertEqual(len(cp2["cluster_cache"]["gemma4:26b"]), 3)
                self.assertNotIn("gemma4:26b", cp2["completed_tiers"])

                # Step 3: Model A (qwen3.8:27b), clusters 3-12 (evaluates remaining 9 clusters)
                # Ensure clusters 0-2 are NOT re-called!
                r3 = rmb.run_bakeoff(
                    manifest_path,
                    max_clusters=12,
                    out_dir=out_dir,
                    resume=True,
                    target_model="qwen3.8:27b",
                    cluster_start=3,
                    cluster_end=12,
                )
                # 3 from step 1 + 9 from step 3 = 12 total calls to 27b
                self.assertEqual(call_count["27b"], 12)

                with open(out_dir / "bakeoff_checkpoint.json", "r") as f:
                    cp3 = json.load(f)
                self.assertEqual(len(cp3["cluster_cache"]["qwen3.8:27b"]), 12)
                self.assertIn("qwen3.8:27b", cp3["completed_tiers"])

                # Step 4: Model B (gemma4:26b), clusters 3-12 (evaluates remaining 9 clusters)
                # Ensure clusters 0-2 are NOT re-called!
                r4 = rmb.run_bakeoff(
                    manifest_path,
                    max_clusters=12,
                    out_dir=out_dir,
                    resume=True,
                    target_model="gemma4:26b",
                    cluster_start=3,
                    cluster_end=12,
                )
                # 3 from step 2 + 9 from step 4 = 12 total calls to 26b
                self.assertEqual(call_count["26b"], 12)

                with open(out_dir / "bakeoff_checkpoint.json", "r") as f:
                    cp4 = json.load(f)
                self.assertEqual(len(cp4["cluster_cache"]["gemma4:26b"]), 12)
                self.assertIn("gemma4:26b", cp4["completed_tiers"])

                # Since all 6 tiers are complete, report should be returned
                self.assertIn("report_id", r4)

                # Check all artifacts were generated
                self.assertTrue((out_dir / "model_bakeoff_report.json").exists())
                self.assertTrue((out_dir / "bakeoff_raw_results.json").exists())
                self.assertTrue((out_dir / "verification_receipt.json").exists())
                self.assertTrue((out_dir / "handoff.md").exists())

                # Run verify_existing_receipt
                ok, errors = rmb.verify_existing_receipt(manifest_path, out_dir)
                self.assertTrue(ok, f"Verification failed with errors: {errors}")

    def test_timeout_configuration(self):
        """Verify 600s timeout for 27B and 26B, 240s for others."""
        mock_bridge = MagicMock()
        mock_bridge.call_ollama.return_value = {
            "status": 200,
            "wall_sec": 0.1,
            "body": {"response": "{}", "eval_count": 10, "eval_duration": 1000000},
        }

        cluster = {
            "cluster_id": "c_001",
            "source_atoms": [{"atom_version_id": "av_01", "content": "text", "properties": {}}],
        }

        # Test 27B
        rmb.run_llm_consolidation(mock_bridge, "qwen3.8:27b", cluster)
        call_kwargs = mock_bridge.call_ollama.call_args[1]
        self.assertEqual(call_kwargs.get("timeout"), 600.0)

        # Test 26B
        rmb.run_llm_consolidation(mock_bridge, "gemma4:26b", cluster)
        call_kwargs = mock_bridge.call_ollama.call_args[1]
        self.assertEqual(call_kwargs.get("timeout"), 600.0)

        # Test other models (e.g. 8b, 12b)
        rmb.run_llm_consolidation(mock_bridge, "qwen3:8b", cluster)
        call_kwargs = mock_bridge.call_ollama.call_args[1]
        self.assertEqual(call_kwargs.get("timeout"), 240.0)

        rmb.run_llm_consolidation(mock_bridge, "gemma4:12b", cluster)
        call_kwargs = mock_bridge.call_ollama.call_args[1]
        self.assertEqual(call_kwargs.get("timeout"), 240.0)

    def test_fail_closed_invalid_output_scores_zero(self):
        """Ensure invalid model output yields 0.0 support."""
        mock_bridge = MagicMock()
        # Non-JSON gibberish response
        mock_bridge.call_ollama.return_value = {
            "status": 200,
            "wall_sec": 0.1,
            "body": {"response": "Not valid JSON at all", "eval_count": 5, "eval_duration": 100000},
        }
        cluster = {
            "cluster_id": "c_001",
            "source_atoms": [{"atom_version_id": "av_01", "content": "valid atom content", "properties": {}}],
        }
        data, tps, wall_sec, is_invalid = rmb.run_llm_consolidation(mock_bridge, "qwen3.8:27b", cluster)
        self.assertTrue(is_invalid)

    def test_evaluate_faithfulness_empty_props_scores_zero(self):
        """Verify that empty summaries or unextractable text score 0.0, never 1.0."""
        atoms = [{"atom_version_id": "av_1", "content": "Some real factual content."}]
        empty_data = {
            "section_summaries": [],
            "topic_holons": [],
        }
        score = rmb.evaluate_faithfulness(empty_data, atoms)
        self.assertEqual(score, 0.0)

        # Empty content strings
        empty_content = {
            "section_summaries": [{"content": ""}],
            "topic_holons": [{"summary": ""}],
        }
        score = rmb.evaluate_faithfulness(empty_content, atoms)
        self.assertEqual(score, 0.0)

    def test_clean_and_parse_json_robustness(self):
        """Verify clean_and_parse_json handles think tags, fences, trailing commas, and schema."""
        # 1. Think tags and markdown fences
        raw = """<think>
Internal thought process...
</think>
```json
{
  "section_summaries": [
    {"section_id": "sec_1", "title": "T1", "content": "Sentence one.", "anchor_atom_ids": ["a1"], "token_count": 2},
  ],
  "topic_holons": [
    {"topic_id": "topic_001", "title": "T", "summary": "Topic sentence.", "source_atom_ids": ["a1"], "parent_topic_id": null, "confidence": 1.0},
  ],
}
```"""
        data, is_inv = rmb.clean_and_parse_json(raw)
        self.assertFalse(is_inv)
        self.assertIsNotNone(data)
        self.assertEqual(len(data["section_summaries"]), 1)

        # 2. Malformed / missing required schema
        malformed = '{"some_other_key": "val"}'
        data, is_inv = rmb.clean_and_parse_json(malformed)
        self.assertTrue(is_inv)
        self.assertIsNone(data)

    def test_extractive_control_not_chosen_as_slm_champion(self):
        """Under CAP-D006, Tier 0 Extractive Control must never be crowned champion over candidate SLMs."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            manifest_path = tdp / "test_manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(self.manifest_data, f)

            out_dir = tdp / "out"
            out_dir.mkdir()

            # Pre-seed tiers: Tier 0 has 1.0 faithfulness and 0.0 VRAM. Tier 1 has 0.96 faithfulness and 4.5 VRAM.
            preseeded_checkpoint = {
                "manifest": "test_manifest.json",
                "total_clusters": 12,
                "completed_tiers": {
                    "extractive_control": {
                        "tier_index": 0,
                        "name": "Extractive Control",
                        "model_id": "extractive_control",
                        "architecture": "Deterministic Heuristic",
                        "params": "0B (Zero-LLM)",
                        "clusters_evaluated": 12,
                        "faithfulness": {"point_estimate": 1.0, "bootstrap_95_ci": [1.0, 1.0], "ci_width": 0.0, "clears_95_floor": True, "valid_cluster_count": 12},
                        "performance": {"cold_load_sec": 0.0, "warm_tokens_per_sec": 2500.0, "p95_latency_ms": 0.5, "total_wall_clock_sec": 0.1},
                        "robustness": {"invalid_output_rate": 0.0, "invalid_cluster_count": 0},
                        "cost_and_resources": {"api_spend_usd": 0.0, "vram_allocated_gb": 0.0, "cost_per_1k_holons_usd": 0.0, "energy_kwh_per_1k_holons": 0.0001},
                    },
                    "gemma4:e4b": {
                        "tier_index": 1,
                        "name": "Gemma 4 E4B",
                        "model_id": "gemma4:e4b",
                        "architecture": "4B Dense",
                        "params": "4B",
                        "clusters_evaluated": 12,
                        "faithfulness": {"point_estimate": 0.96, "bootstrap_95_ci": [0.95, 0.97], "ci_width": 0.02, "clears_95_floor": True, "valid_cluster_count": 12},
                        "performance": {"cold_load_sec": 1.0, "warm_tokens_per_sec": 25.0, "p95_latency_ms": 1000.0, "total_wall_clock_sec": 12.0},
                        "robustness": {"invalid_output_rate": 0.0, "invalid_cluster_count": 0},
                        "cost_and_resources": {"api_spend_usd": 0.0, "vram_allocated_gb": 4.5, "cost_per_1k_holons_usd": 0.0, "energy_kwh_per_1k_holons": 0.01},
                    },
                    "qwen3:8b": {
                        "tier_index": 2,
                        "name": "Qwen3-8B",
                        "model_id": "qwen3:8b",
                        "architecture": "8B Dense",
                        "params": "8B",
                        "clusters_evaluated": 12,
                        "faithfulness": {"point_estimate": 0.96, "bootstrap_95_ci": [0.95, 0.97], "ci_width": 0.02, "clears_95_floor": True, "valid_cluster_count": 12},
                        "performance": {"cold_load_sec": 1.0, "warm_tokens_per_sec": 25.0, "p95_latency_ms": 1000.0, "total_wall_clock_sec": 12.0},
                        "robustness": {"invalid_output_rate": 0.0, "invalid_cluster_count": 0},
                        "cost_and_resources": {"api_spend_usd": 0.0, "vram_allocated_gb": 5.2, "cost_per_1k_holons_usd": 0.0, "energy_kwh_per_1k_holons": 0.01},
                    },
                    "gemma4:12b": {
                        "tier_index": 3,
                        "name": "Gemma 4 12B",
                        "model_id": "gemma4:12b",
                        "architecture": "12B Dense",
                        "params": "12B",
                        "clusters_evaluated": 12,
                        "faithfulness": {"point_estimate": 0.96, "bootstrap_95_ci": [0.95, 0.97], "ci_width": 0.02, "clears_95_floor": True, "valid_cluster_count": 12},
                        "performance": {"cold_load_sec": 1.0, "warm_tokens_per_sec": 25.0, "p95_latency_ms": 1000.0, "total_wall_clock_sec": 12.0},
                        "robustness": {"invalid_output_rate": 0.0, "invalid_cluster_count": 0},
                        "cost_and_resources": {"api_spend_usd": 0.0, "vram_allocated_gb": 7.6, "cost_per_1k_holons_usd": 0.0, "energy_kwh_per_1k_holons": 0.01},
                    },
                    "qwen3.8:27b": {
                        "tier_index": 4,
                        "name": "Qwen3.8-27B",
                        "model_id": "qwen3.8:27b",
                        "architecture": "27B Dense",
                        "params": "27B",
                        "clusters_evaluated": 12,
                        "faithfulness": {"point_estimate": 0.97, "bootstrap_95_ci": [0.96, 0.98], "ci_width": 0.02, "clears_95_floor": True, "valid_cluster_count": 12},
                        "performance": {"cold_load_sec": 1.0, "warm_tokens_per_sec": 22.0, "p95_latency_ms": 1500.0, "total_wall_clock_sec": 15.0},
                        "robustness": {"invalid_output_rate": 0.0, "invalid_cluster_count": 0},
                        "cost_and_resources": {"api_spend_usd": 0.0, "vram_allocated_gb": 8.0, "cost_per_1k_holons_usd": 0.0, "energy_kwh_per_1k_holons": 0.02},
                    },
                    "gemma4:26b": {
                        "tier_index": 5,
                        "name": "Gemma 4 26B MoE",
                        "model_id": "gemma4:26b",
                        "architecture": "26B MoE",
                        "params": "26B",
                        "clusters_evaluated": 12,
                        "faithfulness": {"point_estimate": 0.96, "bootstrap_95_ci": [0.95, 0.97], "ci_width": 0.02, "clears_95_floor": True, "valid_cluster_count": 12},
                        "performance": {"cold_load_sec": 1.0, "warm_tokens_per_sec": 20.0, "p95_latency_ms": 1600.0, "total_wall_clock_sec": 16.0},
                        "robustness": {"invalid_output_rate": 0.0, "invalid_cluster_count": 0},
                        "cost_and_resources": {"api_spend_usd": 0.0, "vram_allocated_gb": 8.0, "cost_per_1k_holons_usd": 0.0, "energy_kwh_per_1k_holons": 0.02},
                    },
                },
                "cluster_cache": {},
            }
            with open(out_dir / "bakeoff_checkpoint.json", "w", encoding="utf-8") as f:
                json.dump(preseeded_checkpoint, f)

            # Trigger report generation with all tiers complete
            res = rmb.run_bakeoff(manifest_path, max_clusters=12, out_dir=out_dir, resume=True)
            self.assertIn("pareto_recommendation", res)
            champ_id = res["pareto_recommendation"]["recommended_tier"]
            # Champion must be Tier 1 (gemma4:e4b), NOT Tier 0 (extractive_control)
            self.assertEqual(champ_id, "gemma4:e4b")
            self.assertNotEqual(champ_id, "extractive_control")

    def test_staged_flag_dynamic_bounds(self):
        """Verify that --staged CLI flag runs through 4 stages with dynamic bounds."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            manifest_path = tdp / "test_manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(self.manifest_data, f)

            out_dir = tdp / "out"
            out_dir.mkdir()

            mock_bridge = MagicMock()
            mock_bridge.call_ollama.return_value = {
                "status": 200,
                "wall_sec": 0.01,
                "body": {
                    "eval_count": 10,
                    "eval_duration": 1000000000,
                    "response": json.dumps({
                        "section_summaries": [{"content": "Quantum mechanics discussion."}],
                        "topic_holons": [{"summary": "Quantum mechanics theme."}],
                    }),
                },
            }
            with patch.object(rmb, "WindowsOllamaBridge", return_value=mock_bridge):
                res = rmb.run_bakeoff(manifest_path, max_clusters=4, out_dir=out_dir, resume=True, staged=True)
                with open(out_dir / "bakeoff_checkpoint.json", "r") as f:
                    cp = json.load(f)
                self.assertIn("qwen3.8:27b", cp["cluster_cache"])
                self.assertIn("gemma4:26b", cp["cluster_cache"])

    def test_fresh_start_finalists_incorporates_phase_a_baselines(self):
        """Verify that when running without any pre-existing checkpoint file, completing the finalists
        automatically incorporates the locked Phase A baseline tiers and generates a verified receipt."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            manifest_data_100 = {
                "manifest_sha256": "dummy_sha_100",
                "total_clusters": 100,
                "clusters": [
                    {
                        "cluster_id": f"c_{i:03d}",
                        "source_atoms": [{"atom_version_id": f"av_{i}", "content": "Quantum mechanics evidence content"}],
                    }
                    for i in range(100)
                ],
            }
            manifest_path = tdp / "bakeoff_clusters_v1.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_data_100, f)

            out_dir = tdp / "out"
            out_dir.mkdir()

            # Note: out_dir has NO bakeoff_checkpoint.json file! Fresh start!
            self.assertFalse((out_dir / "bakeoff_checkpoint.json").exists())

            mock_bridge = MagicMock()
            mock_bridge.call_ollama.return_value = {
                "status": 200,
                "wall_sec": 0.01,
                "body": {
                    "eval_count": 20,
                    "eval_duration": 1000000000,
                    "response": json.dumps({
                        "section_summaries": [{"section_id": "s1", "title": "T", "content": "Quantum mechanics evidence content", "anchor_atom_ids": ["a1"]}],
                        "topic_holons": [{"topic_id": "t1", "title": "T", "summary": "Quantum mechanics evidence content", "source_atom_ids": ["a1"]}],
                        "entity_candidates": [],
                        "relation_candidates": [],
                    }),
                },
            }

            with patch.object(rmb, "WindowsOllamaBridge", return_value=mock_bridge):
                # Step 1: Run gemma4:26b 0-100
                res1 = rmb.run_bakeoff(
                    manifest_path,
                    max_clusters=100,
                    out_dir=out_dir,
                    resume=True,
                    target_model="gemma4:26b",
                    cluster_start=0,
                    cluster_end=100,
                )
                self.assertEqual(res1.get("status"), "in_progress")
                self.assertTrue((out_dir / "bakeoff_checkpoint.json").exists())

                # Step 2: Run qwen3.8:27b 0-100
                res2 = rmb.run_bakeoff(
                    manifest_path,
                    max_clusters=100,
                    out_dir=out_dir,
                    resume=True,
                    target_model="qwen3.8:27b",
                    cluster_start=0,
                    cluster_end=100,
                )
                self.assertIn("report_id", res2)
                self.assertTrue((out_dir / "verification_receipt.json").exists())
                self.assertTrue((out_dir / "model_bakeoff_report.json").exists())

                # Verify receipt passes 100%
                ok, errors = rmb.verify_existing_receipt(manifest_path, out_dir)
                self.assertTrue(ok, f"Verification failed: {errors}")

    def test_output_token_limit_and_context_size(self):
        """Verify num_predict is set to 8192+ and num_ctx is set to 16384."""
        mock_bridge = MagicMock()
        mock_bridge.call_ollama.return_value = {
            "status": 200,
            "wall_sec": 0.05,
            "body": {
                "response": json.dumps({
                    "section_summaries": [{"content": "Quantum mechanics discussion."}],
                    "topic_holons": [{"summary": "Quantum mechanics discussion."}],
                }),
                "eval_count": 20,
                "eval_duration": 1000000000,
            },
        }
        cluster = {
            "cluster_id": "c_001",
            "source_atoms": [{"atom_version_id": "av_01", "content": "Quantum mechanics discussion.", "properties": {}}],
        }
        rmb.run_llm_consolidation(mock_bridge, "gemma4:26b", cluster)
        payload = mock_bridge.call_ollama.call_args[0][1]
        options = payload.get("options", {})
        self.assertGreaterEqual(options.get("num_predict", 0), 8192)
        self.assertGreaterEqual(options.get("num_ctx", 0), 16384)

    def test_retry_rescues_invalid_json_with_error_feedback(self):
        """Verify that score of 0 due to invalid JSON retries with error feedback and rescues."""
        mock_bridge = MagicMock()
        call_prompts = []

        def side_effect(endpoint, payload, timeout=180.0):
            call_prompts.append(payload.get("prompt", ""))
            if len(call_prompts) == 1:
                # Attempt 1: Invalid cut-off JSON
                return {
                    "status": 200,
                    "wall_sec": 0.05,
                    "body": {"response": '{"section_summaries": [{"content": "Cut off...', "eval_count": 10, "eval_duration": 500000000},
                }
            else:
                # Attempt 2: Rescued valid JSON
                return {
                    "status": 200,
                    "wall_sec": 0.05,
                    "body": {
                        "response": json.dumps({
                            "section_summaries": [{"section_id": "s1", "title": "T", "content": "Quantum mechanics evidence.", "anchor_atom_ids": ["a1"]}],
                            "topic_holons": [{"topic_id": "t1", "title": "T", "summary": "Quantum mechanics evidence.", "source_atom_ids": ["a1"]}],
                            "entity_candidates": [],
                            "relation_candidates": [],
                        }),
                        "eval_count": 20,
                        "eval_duration": 1000000000,
                    },
                }

        mock_bridge.call_ollama.side_effect = side_effect
        cluster = {
            "cluster_id": "c_001",
            "source_atoms": [{"atom_version_id": "av_01", "content": "Quantum mechanics evidence.", "properties": {}}],
        }
        data, tps, wall_sec, is_invalid = rmb.run_llm_consolidation(mock_bridge, "gemma4:26b", cluster)
        self.assertFalse(is_invalid)
        self.assertEqual(len(call_prompts), 2)
        # Verify second prompt contained error feedback
        self.assertIn("ERROR / FEEDBACK:", call_prompts[1])
        self.assertIn("PREVIOUS ATTEMPT OUTPUT:", call_prompts[1])
        # Verify _retry_meta
        self.assertEqual(data.get("_retry_meta", {}).get("retry_count"), 1)
        self.assertEqual(data.get("_retry_meta", {}).get("best_attempt"), 2)

    def test_retry_rescues_low_grounding_in_point_seven_range(self):
        """Verify that score in .7 range triggers retry and stops early when improved."""
        mock_bridge = MagicMock()
        call_prompts = []

        def side_effect(endpoint, payload, timeout=180.0):
            call_prompts.append(payload.get("prompt", ""))
            if len(call_prompts) == 1:
                # Attempt 1: Valid JSON, but paraphrased words yielding low support
                return {
                    "status": 200,
                    "wall_sec": 0.05,
                    "body": {
                        "response": json.dumps({
                            "section_summaries": [{"content": "General science study regarding various physical phenomena."}],
                            "topic_holons": [{"summary": "Quantum mechanics evidence."}],
                        }),
                        "eval_count": 15,
                        "eval_duration": 500000000,
                    },
                }
            else:
                # Attempt 2: Improved grounding using exact words
                return {
                    "status": 200,
                    "wall_sec": 0.05,
                    "body": {
                        "response": json.dumps({
                            "section_summaries": [{"content": "Quantum mechanics evidence."}],
                            "topic_holons": [{"summary": "Quantum mechanics evidence."}],
                        }),
                        "eval_count": 15,
                        "eval_duration": 500000000,
                    },
                }

        mock_bridge.call_ollama.side_effect = side_effect
        cluster = {
            "cluster_id": "c_001",
            "source_atoms": [{"atom_version_id": "av_01", "content": "Quantum mechanics evidence.", "properties": {}}],
        }
        data, tps, wall_sec, is_invalid = rmb.run_llm_consolidation(mock_bridge, "qwen3.8:27b", cluster)
        self.assertFalse(is_invalid)
        self.assertEqual(len(call_prompts), 2)
        self.assertIn("ERROR / FEEDBACK:", call_prompts[1])
        self.assertIn("Faithfulness score was", call_prompts[1])
        # Rescued to 1.0
        meta = data.get("_retry_meta", {})
        self.assertEqual(meta.get("retry_count"), 1)
        self.assertEqual(meta.get("best_attempt"), 2)
        self.assertGreaterEqual(meta.get("support", 0.0), 0.95)

    def test_retry_preserves_best_attempt_when_subsequent_attempts_fail(self):
        """Verify that when retry produces worse result, the best attempt is preserved."""
        mock_bridge = MagicMock()
        call_count = [0]

        def side_effect(endpoint, payload, timeout=180.0):
            call_count[0] += 1
            if call_count[0] == 1:
                # Attempt 1: score ~0.50 (below 0.80 threshold)
                return {
                    "status": 200,
                    "wall_sec": 0.05,
                    "body": {
                        "response": json.dumps({
                            "section_summaries": [{"content": "General physical phenomena study."}],
                            "topic_holons": [{"summary": "Quantum mechanics evidence."}],
                        }),
                        "eval_count": 10,
                        "eval_duration": 500000000,
                    },
                }
            else:
                # Attempt 2 & 3: Total garbage / invalid
                return {
                    "status": 200,
                    "wall_sec": 0.05,
                    "body": {"response": "Broken JSON", "eval_count": 5, "eval_duration": 200000000},
                }

        mock_bridge.call_ollama.side_effect = side_effect
        cluster = {
            "cluster_id": "c_001",
            "source_atoms": [{"atom_version_id": "av_01", "content": "Quantum mechanics evidence.", "properties": {}}],
        }
        data, tps, wall_sec, is_invalid = rmb.run_llm_consolidation(mock_bridge, "qwen3.8:27b", cluster, max_attempts=3)
        self.assertFalse(is_invalid)
        self.assertEqual(call_count[0], 3)
        # Attempt 1 was preserved as best
        meta = data.get("_retry_meta", {})
        self.assertEqual(meta.get("best_attempt"), 1)
        self.assertGreater(meta.get("support", 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
