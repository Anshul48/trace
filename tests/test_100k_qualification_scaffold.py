"""Unit tests for 100K Paired Qualification Scaffold & Preflight (Node CAP-INT02)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from benchmarks.run_100k_qualification import (
    DEFAULT_CAPSULE_MANIFEST,
    EXPECTED_MERKLE_ROOT,
    FORBIDDEN_LEGACY_CORPUS,
    check_stop_rules,
    run_preflight_checks,
    scaffold_100k_qualification,
    verify_qualification_receipt,
)


class Test100KQualificationScaffold(unittest.TestCase):
    def test_preflight_success_with_real_capsule_manifest(self) -> None:
        ok, errors = run_preflight_checks(manifest_path=DEFAULT_CAPSULE_MANIFEST)
        self.assertTrue(ok, f"Preflight failed: {errors}")
        self.assertEqual(errors, [])

    def test_preflight_fails_closed_on_forbidden_legacy_path(self) -> None:
        ok, errors = run_preflight_checks(corpus_input=FORBIDDEN_LEGACY_CORPUS)
        self.assertFalse(ok)
        self.assertTrue(any("Prohibited legacy path referenced" in e for e in errors))

        ok2, errors2 = run_preflight_checks(corpus_input="benchmarks/data/corpus_100k_frozen.jsonl")
        self.assertFalse(ok2)
        self.assertTrue(any("Prohibited legacy path referenced" in e for e in errors2))

    def test_preflight_fails_on_missing_manifest(self) -> None:
        ok, errors = run_preflight_checks(manifest_path=Path("nonexistent/manifest.json"))
        self.assertFalse(ok)
        self.assertTrue(any("Capsule manifest not found" in e for e in errors))

    def test_preflight_fails_on_merkle_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_manifest_path = Path(tmpdir) / "corpus_manifest.json"
            with open(bad_manifest_path, "w", encoding="utf-8") as f:
                json.dump({
                    "selection_merkle_root_sha256": "bad_hash_0000000000000000000000000000000000000000000000000000000000",
                    "target_unique_documents_d": 100000,
                    "synthetic_data_used": False,
                    "in_memory_fallback_used": False,
                }, f)
            ok, errors = run_preflight_checks(manifest_path=bad_manifest_path)
            self.assertFalse(ok)
            self.assertTrue(any("Merkle root mismatch" in e for e in errors))

    def test_stop_rule_profile2_regression(self) -> None:
        # Normal passing scores
        passing_scores = {"scifact": 0.6720, "nfcorpus": 0.3580, "fiqa": 0.4110}
        ok, violations = check_stop_rules(passing_scores, storage_multiplier=2.72)
        self.assertTrue(ok)
        self.assertEqual(violations, [])

        # Regressed SciFact (< 0.65)
        regressed_scifact = {"scifact": 0.6450, "nfcorpus": 0.3580, "fiqa": 0.4110}
        ok, violations = check_stop_rules(regressed_scifact, storage_multiplier=2.72)
        self.assertFalse(ok)
        self.assertTrue(any("Stop Rule 1 Triggered: Profile 2 scifact" in v for v in violations))

        # Regressed NFCorpus (< 0.32)
        regressed_nfcorpus = {"scifact": 0.6720, "nfcorpus": 0.3150, "fiqa": 0.4110}
        ok, violations = check_stop_rules(regressed_nfcorpus, storage_multiplier=2.72)
        self.assertFalse(ok)
        self.assertTrue(any("Stop Rule 1 Triggered: Profile 2 nfcorpus" in v for v in violations))

    def test_stop_rule_storage_multiplier_exceeded(self) -> None:
        passing_scores = {"scifact": 0.6720, "nfcorpus": 0.3580, "fiqa": 0.4110}
        ok, violations = check_stop_rules(passing_scores, storage_multiplier=3.51)
        self.assertFalse(ok)
        self.assertTrue(any("Stop Rule 2 Triggered: Storage multiplier" in v for v in violations))

    def test_three_profile_separation_in_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "cap-int02"
            dossier = scaffold_100k_qualification(out_dir=out_dir)
            profiles = dossier.get("profiles", {})
            self.assertEqual(len(profiles), 3)
            self.assertIn("profile_1_lexical", profiles)
            self.assertIn("profile_2_hybrid", profiles)
            self.assertIn("profile_3_cortex", profiles)

            # Check isolation of component definitions
            self.assertEqual(profiles["profile_1_lexical"]["components"], ["Spine WAL", "SQLite FTS5 BM25"])
            self.assertIn("MiniLM-L6-v2 Dense", profiles["profile_2_hybrid"]["components"])
            self.assertIn("Asynchronous Local SLM Semantic Projections", profiles["profile_3_cortex"]["components"])

            ok, errors = verify_qualification_receipt(out_dir)
            self.assertTrue(ok, f"Verification failed: {errors}")

    def test_preflight_fails_on_corrupted_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corrupted_manifest = Path(tmpdir) / "corrupted_manifest.json"
            with open(corrupted_manifest, "w", encoding="utf-8") as f:
                f.write("{invalid json content")
            ok, errors = run_preflight_checks(manifest_path=corrupted_manifest)
            self.assertFalse(ok)
            self.assertTrue(any("Failed to parse capsule manifest JSON" in e for e in errors))

    def test_preflight_fails_on_missing_base_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_manifest = Path(tmpdir) / "manifest.json"
            with open(bad_manifest, "w", encoding="utf-8") as f:
                json.dump({
                    "selection_merkle_root_sha256": EXPECTED_MERKLE_ROOT,
                    "target_unique_documents_d": 100000,
                    "synthetic_data_used": False,
                    "in_memory_fallback_used": False,
                    "base_data_root": str(Path(tmpdir) / "nonexistent_dir"),
                    "datasets": [{"dataset_name": "test", "corpus_file": {"relative_path": "a.jsonl", "size_bytes": 10}}],
                }, f)
            ok, errors = run_preflight_checks(manifest_path=bad_manifest)
            self.assertFalse(ok)
            self.assertTrue(any("base_data_root does not exist" in e for e in errors))

    def test_preflight_fails_on_missing_shard_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "data"
            base_dir.mkdir()
            bad_manifest = Path(tmpdir) / "manifest.json"
            with open(bad_manifest, "w", encoding="utf-8") as f:
                json.dump({
                    "selection_merkle_root_sha256": EXPECTED_MERKLE_ROOT,
                    "target_unique_documents_d": 100000,
                    "synthetic_data_used": False,
                    "in_memory_fallback_used": False,
                    "base_data_root": str(base_dir),
                    "datasets": [{"dataset_name": "missing_ds", "corpus_file": {"relative_path": "missing.jsonl", "size_bytes": 10}}],
                }, f)
            ok, errors = run_preflight_checks(manifest_path=bad_manifest)
            self.assertFalse(ok)
            self.assertTrue(any("corpus shard file missing" in e for e in errors))

    def test_preflight_fails_on_shard_size_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "data"
            base_dir.mkdir()
            shard = base_dir / "shard.jsonl"
            shard.write_text("12345", encoding="utf-8")  # 5 bytes
            bad_manifest = Path(tmpdir) / "manifest.json"
            with open(bad_manifest, "w", encoding="utf-8") as f:
                json.dump({
                    "selection_merkle_root_sha256": EXPECTED_MERKLE_ROOT,
                    "target_unique_documents_d": 100000,
                    "synthetic_data_used": False,
                    "in_memory_fallback_used": False,
                    "base_data_root": str(base_dir),
                    "datasets": [{"dataset_name": "bad_size_ds", "corpus_file": {"relative_path": "shard.jsonl", "size_bytes": 100}}],
                }, f)
            ok, errors = run_preflight_checks(manifest_path=bad_manifest)
            self.assertFalse(ok)
            self.assertTrue(any("corpus shard size mismatch" in e for e in errors))

    def test_verify_qualification_receipt_fails_on_tampered_merkle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "cap-int02"
            scaffold_100k_qualification(out_dir=out_dir)
            dossier_path = out_dir / "100k_qualification_dossier.json"
            with open(dossier_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            d["source_capsule"]["merkle_root_sha256"] = "tampered_root"
            with open(dossier_path, "w", encoding="utf-8") as f:
                json.dump(d, f)
            ok, errors = verify_qualification_receipt(out_dir)
            self.assertFalse(ok)
            self.assertTrue(any("Merkle root mismatch" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
