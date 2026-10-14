"""Comprehensive unit tests for DeepSeek Flash V4 0731 bakeoff runner, prompt parser, and receipt verification."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.run_deepseek_flash_bakeoff import (
    DEFAULT_MANIFEST,
    SailResearchClient,
    bootstrap_ci,
    clean_and_parse_json,
    evaluate_faithfulness,
    extract_propositions,
    run_deepseek_flash_bakeoff,
    run_extractive_control,
    verify_proposition_support,
    verify_receipt,
)


class TestDeepSeekFlashBakeoff(unittest.TestCase):
    def test_clean_and_parse_json_direct(self) -> None:
        payload = {
            "section_summaries": [{"section_id": "sec_1", "content": "Sample summary."}],
            "topic_holons": [{"topic_id": "topic_001", "summary": "Sample topic."}],
        }
        data, is_invalid = clean_and_parse_json(json.dumps(payload))
        self.assertFalse(is_invalid)
        self.assertIsNotNone(data)
        self.assertEqual(len(data["section_summaries"]), 1)

    def test_clean_and_parse_json_with_think_and_fences(self) -> None:
        raw = """<think>
I need to produce a valid JSON object matching the user's constraints.
Let's make sure topic_holons is included.
</think>
```json
{
  "section_summaries": [
    {"section_id": "sec_1", "content": "Jean Eustache directed two films."}
  ],
  "topic_holons": [
    {"topic_id": "topic_001", "summary": "Films directed by Jean Eustache in Pessac."}
  ],
  "entity_candidates": [],
  "relation_candidates": []
}
```
"""
        data, is_invalid = clean_and_parse_json(raw)
        self.assertFalse(is_invalid)
        self.assertIsNotNone(data)
        self.assertIn("section_summaries", data)
        self.assertIn("topic_holons", data)

    def test_clean_and_parse_json_with_trailing_commas(self) -> None:
        raw = """{
  "section_summaries": [
    {"section_id": "sec_1", "content": "Fact one."},
  ],
  "topic_holons": [
    {"topic_id": "topic_001", "summary": "Topic fact."},
  ],
}"""
        data, is_invalid = clean_and_parse_json(raw)
        self.assertFalse(is_invalid)
        self.assertIsNotNone(data)
        self.assertEqual(len(data["section_summaries"]), 1)

    def test_clean_and_parse_json_with_conversational_wrapper(self) -> None:
        raw = """Here is the requested consolidation:
{
  "section_summaries": [{"section_id": "sec_1", "content": "Fact one."}],
  "topic_holons": [{"topic_id": "topic_001", "summary": "Topic fact."}]
}
Hope this helps!"""
        data, is_invalid = clean_and_parse_json(raw)
        self.assertFalse(is_invalid)
        self.assertIsNotNone(data)
        self.assertEqual(data["section_summaries"][0]["content"], "Fact one.")

    def test_clean_and_parse_json_invalid(self) -> None:
        raw = "This is not json at all."
        data, is_invalid = clean_and_parse_json(raw)
        self.assertTrue(is_invalid)
        self.assertIsNone(data)

    def test_bootstrap_ci(self) -> None:
        scores = [0.8, 0.9, 0.85, 0.95, 0.75, 1.0, 0.9]
        pt, low, high = bootstrap_ci(scores, n_resamples=1000, seed=42)
        self.assertAlmostEqual(pt, sum(scores) / len(scores), places=4)
        self.assertLessEqual(low, pt)
        self.assertGreaterEqual(high, pt)

    def test_evaluate_faithfulness_happy_path(self) -> None:
        atoms = [
            {"atom_version_id": "av_1", "content": "Jean Eustache directed two hour-long films in 1968 and 1979 in Pessac."}
        ]
        data = {
            "section_summaries": [
                {"content": "Jean Eustache directed two hour-long films in 1968 and 1979 in Pessac."}
            ],
            "topic_holons": [
                {"summary": "Jean Eustache directed films in Pessac."}
            ],
        }
        score = evaluate_faithfulness(data, atoms)
        self.assertEqual(score, 1.0)

    def test_evaluate_faithfulness_empty_props_fail_closed(self) -> None:
        """Verify that empty summaries or unextractable text fail closed to 0.0, NOT 1.0."""
        atoms = [{"atom_version_id": "av_1", "content": "Some real factual content."}]
        empty_data = {
            "section_summaries": [],
            "topic_holons": [],
        }
        score = evaluate_faithfulness(empty_data, atoms)
        self.assertEqual(score, 0.0)

    def test_evaluate_faithfulness_alternate_keys(self) -> None:
        """Verify that summary, text, description keys are recognized in summaries."""
        atoms = [{"atom_version_id": "av_1", "content": "Alice founded the company in 2020."}]
        data = {
            "section_summaries": [{"section_id": "sec_1", "summary": "Alice founded the company in 2020."}],
            "topic_holons": [{"topic_id": "top_1", "description": "Company was founded by Alice in 2020."}],
        }
        score = evaluate_faithfulness(data, atoms)
        self.assertGreaterEqual(score, 0.90)

    def test_evaluate_faithfulness_hallucination_penalty(self) -> None:
        """Verify unanchored claims are penalized."""
        atoms = [{"atom_version_id": "av_1", "content": "The river flows through the quiet mountain valley."}]
        data = {
            "section_summaries": [{"content": "The astronaut landed the spaceship on Mars yesterday."}],
            "topic_holons": [{"summary": "Extraterrestrial mission to the red planet was completed."}],
        }
        score = evaluate_faithfulness(data, atoms)
        self.assertLess(score, 0.20)

    def test_verify_credentials_success(self) -> None:
        client = SailResearchClient(api_key="test-key")
        mock_resp = unittest.mock.MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"data": [{"id": "deepseek-ai/DeepSeek-V4-Flash-0731"}]}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ok, msg = client.verify_credentials()
            self.assertTrue(ok)
            self.assertIn("Authentication succeeded", msg)

    def test_verify_credentials_auth_error(self) -> None:
        import urllib.error
        client = SailResearchClient(api_key="invalid-key")
        http_err = urllib.error.HTTPError(
            url="https://api.sailresearch.com/v1/models",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            ok, msg = client.verify_credentials()
            self.assertFalse(ok)
            self.assertIn("Authentication failed", msg)

    def test_preflight_failure_aborts_without_creating_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "sub"
            client = SailResearchClient(api_key="bad-key")
            with patch.object(SailResearchClient, "verify_credentials", return_value=(False, "Invalid key")):
                with self.assertRaises(RuntimeError) as ctx:
                    run_deepseek_flash_bakeoff(
                        manifest_path=DEFAULT_MANIFEST,
                        api_key="bad-key",
                        max_clusters=2,
                        out_dir=out_dir,
                    )
                self.assertIn("pre-flight check failed", str(ctx.exception))
                # Confirm no fraudulent report files were created
                self.assertFalse(out_dir.exists())

    def test_full_run_mock_and_verify_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            mock_resp = {
                "status": 200,
                "wall_sec": 0.5,
                "body": {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps({
                                    "section_summaries": [
                                        {"section_id": "sec_1", "content": "La Rosiere de Pessac directed by Jean Eustache in 1968 and 1979."}
                                    ],
                                    "topic_holons": [
                                        {"topic_id": "topic_001", "summary": "Films directed by Jean Eustache in Pessac."}
                                    ],
                                    "entity_candidates": [],
                                    "relation_candidates": [],
                                })
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 120, "completion_tokens": 45},
                },
            }

            with patch.object(SailResearchClient, "verify_credentials", return_value=(True, "OK")):
                with patch.object(SailResearchClient, "call_chat_completion", return_value=mock_resp):
                    report = run_deepseek_flash_bakeoff(
                        manifest_path=DEFAULT_MANIFEST,
                        api_key="mock-key-for-test",
                        max_clusters=2,
                        out_dir=out_dir,
                    )

            self.assertEqual(report["total_clusters"], 2)
            self.assertIn("model_under_test", report)
            self.assertIn("disentangled_metrics", report["model_under_test"])

            # Test verify_receipt
            ok, errors = verify_receipt(out_dir)
            self.assertTrue(ok, f"Verification failed with errors: {errors}")

    def test_verify_receipt_guards_against_zero_token_fraud(self) -> None:
        """Verify that verify_receipt catches fraudulent runs where no model calls succeeded."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            # Create a fraudulent receipt with 10 clusters evaluated but 0 prompt tokens and 0 valid clusters
            receipt = {
                "target_node": "CAP-MOD01-DEEPSEEK-FLASH",
                "model_id": "deepseek-ai/DeepSeek-V4-Flash-0731",
                "clusters_evaluated": 10,
                "valid_cluster_count": 0,
                "total_prompt_tokens": 0,
            }
            report = {
                "model_under_test": {
                    "model_id": "deepseek-ai/DeepSeek-V4-Flash-0731",
                    "disentangled_metrics": {},
                }
            }
            with open(out_dir / "verification_receipt.json", "w") as f:
                json.dump(receipt, f)
            with open(out_dir / "model_bakeoff_report.json", "w") as f:
                json.dump(report, f)
            (out_dir / "bakeoff_raw_results.json").write_text("{}")
            (out_dir / "handoff.md").write_text("# Handoff")

            ok, errors = verify_receipt(out_dir)
            self.assertFalse(ok)
            self.assertTrue(any("unexecuted or totally failed run" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
