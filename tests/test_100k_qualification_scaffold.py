"""Unit tests for 100K Paired Qualification Scaffold & Preflight (Node CAP-INT02)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import sqlite3
import struct

from benchmarks.run_100k_qualification import (
    DEFAULT_CAPSULE_MANIFEST,
    EXPECTED_MERKLE_ROOT,
    FORBIDDEN_LEGACY_CORPUS,
    PreflightFailure,
    check_stop_rules,
    measure_live_storage,
    run_paired_ablation,
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

    def test_live_ablation_uses_measured_scores(self) -> None:
        with self.assertRaises(PreflightFailure):
            run_paired_ablation(db_path=Path("nonexistent/test.db"), n_queries=5)

        with tempfile.TemporaryDirectory() as tmpdir:
            # db1 has matching document for query 0 ("31715818")
            db1_path = Path(tmpdir) / "db1.db"
            conn1 = sqlite3.connect(str(db1_path))
            conn1.execute("CREATE TABLE node_versions (atom_version_id TEXT, content TEXT)")
            conn1.execute(
                "INSERT INTO node_versions VALUES (?, ?)",
                ("31715818", "0-dimensional biomaterials lack inductive properties in experiments"),
            )
            conn1.commit()
            conn1.close()

            # db2 has non-matching document
            db2_path = Path(tmpdir) / "db2.db"
            conn2 = sqlite3.connect(str(db2_path))
            conn2.execute("CREATE TABLE node_versions (atom_version_id TEXT, content TEXT)")
            conn2.execute(
                "INSERT INTO node_versions VALUES (?, ?)",
                ("99999999", "completely unrelated text about aerospace engineering"),
            )
            conn2.commit()
            conn2.close()

            res1 = run_paired_ablation(db_path=db1_path, n_queries=1, n_resamples=100)
            res2 = run_paired_ablation(db_path=db2_path, n_queries=1, n_resamples=100)

            ndcg1 = res1["top20_metrics"]["bm25_only"]["ndcg_at_10"]
            ndcg2 = res2["top20_metrics"]["bm25_only"]["ndcg_at_10"]
            self.assertEqual(ndcg1, 1.0)
            self.assertNotEqual(ndcg1, ndcg2)

    def test_storage_dbstat_failure_fails_closed(self) -> None:
        with self.assertRaises(PreflightFailure):
            measure_live_storage(db_path=Path("nonexistent/path/db.sqlite"))

        with tempfile.TemporaryDirectory() as tmpdir:
            corrupted = Path(tmpdir) / "corrupted.db"
            corrupted.write_bytes(b"NOT_A_VALID_SQLITE_DATABASE_PAGE_HEADER")

            with self.assertRaises(PreflightFailure):
                measure_live_storage(db_path=corrupted)

            with self.assertRaises(PreflightFailure):
                scaffold_100k_qualification(out_dir=Path(tmpdir) / "out", db_path=corrupted)

    def test_all_arms_measured_not_derived(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ablation.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE node_versions (atom_version_id TEXT, content TEXT)")
            conn.execute("CREATE TABLE edge_versions (source_node_id TEXT, target_node_id TEXT, weight REAL)")
            conn.execute("CREATE TABLE toc (id TEXT, c0 BLOB, members TEXT, status TEXT)")

            from trace.v2.retrieval import HashingDenseEmbedder
            embedder = HashingDenseEmbedder(dimensions=384)

            doc_gold = "0-dimensional biomaterials lack inductive properties in experiments"
            doc_connected = "experiments on inductive properties of cellular matrices and biomaterials"
            doc_unrelated = "completely unrelated astronomy planetary motion galaxies and stellar dynamics"

            conn.execute("INSERT INTO node_versions VALUES (?, ?)", ("31715818", doc_gold))
            conn.execute("INSERT INTO node_versions VALUES (?, ?)", ("doc_connected", doc_connected))
            conn.execute("INSERT INTO node_versions VALUES (?, ?)", ("doc_unrelated", doc_unrelated))

            conn.execute("INSERT INTO edge_versions VALUES (?, ?, ?)", ("31715818", "doc_connected", 1.0))
            conn.execute("INSERT INTO edge_versions VALUES (?, ?, ?)", ("doc_connected", "31715818", 1.0))

            vec_gold = embedder.embed([doc_gold])[0]
            blob_gold = struct.pack(f"{len(vec_gold)}f", *vec_gold)
            vec_unrelated = embedder.embed([doc_unrelated])[0]
            blob_unrelated = struct.pack(f"{len(vec_unrelated)}f", *vec_unrelated)

            conn.execute(
                "INSERT INTO toc VALUES (?, ?, ?, ?)",
                ("toc_1", blob_gold, json.dumps(["31715818", "doc_connected"]), "ACTIVE"),
            )
            conn.execute(
                "INSERT INTO toc VALUES (?, ?, ?, ?)",
                ("toc_2", blob_unrelated, json.dumps(["doc_unrelated"]), "ACTIVE"),
            )
            conn.commit()

            # Run ablation A before mutation
            res_a = run_paired_ablation(db_path=db_path, n_queries=1, n_resamples=50, require_graph=True)
            metrics_a = res_a["top20_metrics"]
            uplift_a = res_a["tier2_uplift_promotion_gate"]["point_estimate_uplift"]

            # Assert all 5 arms exist and delta is not a hardcoded constant
            for arm in ["bm25_only", "dense_only", "hybrid_rrf", "graph_csr", "toc_beam"]:
                self.assertIn(arm, metrics_a)
                self.assertIn("ndcg_at_10", metrics_a[arm])
            self.assertNotIn(uplift_a, {0.0179, 0.0090, 0.0127, 0.0144})

            # Mutate gold document text so it no longer matches query 0
            conn.execute(
                "UPDATE node_versions SET content = ? WHERE atom_version_id = ?",
                ("completely unrelated astronomy deep space astrophysics", "31715818"),
            )
            conn.commit()
            conn.close()

            # Run ablation B after mutation
            res_b = run_paired_ablation(db_path=db_path, n_queries=1, n_resamples=50, require_graph=True)
            metrics_b = res_b["top20_metrics"]
            uplift_b = res_b["tier2_uplift_promotion_gate"]["point_estimate_uplift"]

            # Assert mutating gold document changes all 5 ablation arms
            for arm in ["bm25_only", "dense_only", "hybrid_rrf", "graph_csr", "toc_beam"]:
                score_a = metrics_a[arm]["ndcg_at_10"]
                score_b = metrics_b[arm]["ndcg_at_10"]
                self.assertNotEqual(
                    score_a,
                    score_b,
                    f"Ablation arm {arm} failed to change upon mutating gold doc: {score_a} == {score_b}",
                )

            # Assert delta is measured and changed (not a fixed constant)
            self.assertNotEqual(uplift_a, uplift_b)

    def test_missing_qrels_or_graph_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Missing qrels (manifest query with empty gold_ids) fails closed
            bad_manifest = Path(tmpdir) / "empty_qrels_manifest.json"
            bad_manifest.write_text(
                json.dumps({
                    "closed_evaluation_cohorts": {
                        "direct_lookup": [
                            {"query_id": "q_empty_gold", "query_text": "sample text", "gold_ids": []}
                        ],
                        "domain_semantic": [],
                        "semantic_qa": [],
                    }
                }),
                encoding="utf-8",
            )
            db_path = Path(tmpdir) / "valid.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE node_versions (atom_version_id TEXT, content TEXT)")
            conn.execute("INSERT INTO node_versions VALUES ('atom1', 'some text')")
            conn.commit()
            conn.close()

            with self.assertRaises(PreflightFailure):
                run_paired_ablation(
                    db_path=db_path,
                    queries_manifest_path=bad_manifest,
                    n_queries=1,
                )

            # 2. Missing graph / TOC index fails closed when require_graph=True
            db_no_graph = Path(tmpdir) / "no_graph.db"
            conn = sqlite3.connect(str(db_no_graph))
            conn.execute("CREATE TABLE node_versions (atom_version_id TEXT, content TEXT)")
            conn.execute("INSERT INTO node_versions VALUES ('31715818', 'inductive properties')")
            conn.commit()
            conn.close()

            with self.assertRaises(PreflightFailure):
                run_paired_ablation(
                    db_path=db_no_graph,
                    n_queries=1,
                    require_graph=True,
                )

            # 3. Explicit --db-path pointing to a DB with zero gold overlap must abort fail-closed
            db_zero_overlap = Path(tmpdir) / "zero_overlap.db"
            conn = sqlite3.connect(str(db_zero_overlap))
            conn.execute("CREATE TABLE node_versions (atom_version_id TEXT, content TEXT)")
            conn.execute("INSERT INTO node_versions VALUES ('unrelated_99999', 'completely unrelated content')")
            conn.commit()
            conn.close()

            with self.assertRaises(PreflightFailure):
                scaffold_100k_qualification(
                    out_dir=Path(tmpdir) / "out",
                    db_path=db_zero_overlap,
                    n_ablation_queries=1,
                )

            # 4. Missing or corrupt baseline runs fails closed
            corrupt_runs_dir = Path(tmpdir) / "corrupt_runs"
            corrupt_runs_dir.mkdir()
            (corrupt_runs_dir / "beir-scifact_runs.json").write_text("{invalid json", encoding="utf-8")

            import benchmarks.run_100k_qualification as q_mod
            orig_dir = q_mod.DEFAULT_BASE_RUNS_DIR
            try:
                q_mod.DEFAULT_BASE_RUNS_DIR = corrupt_runs_dir
                with self.assertRaises(PreflightFailure):
                    run_paired_ablation(n_queries=1)
            finally:
                q_mod.DEFAULT_BASE_RUNS_DIR = orig_dir

    def test_empty_database_atoms_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_db = Path(tmpdir) / "empty.db"
            conn = sqlite3.connect(str(empty_db))
            conn.execute("CREATE TABLE node_versions (atom_version_id TEXT, content TEXT)")
            conn.commit()
            conn.close()

            with self.assertRaises(PreflightFailure):
                run_paired_ablation(db_path=empty_db, n_queries=1)


if __name__ == "__main__":
    unittest.main()
