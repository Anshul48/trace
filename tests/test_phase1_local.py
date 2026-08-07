from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trace_local import CapacityError, ImportBundleError, LocalTrace, RecordValidationError, ResourcePolicy
from trace_local.pilot import evaluate_pilot, run_public_fixture


_TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".phase1_tmp"


def local_tempdir():
    _TEST_TEMP_ROOT.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=_TEST_TEMP_ROOT)


def record(
    *,
    record_id: str = "architecture-1",
    content: str = "Trace retains raw source evidence and answers with citations.",
) -> dict[str, object]:
    return {
        "record_id": record_id,
        "document_name": "Architecture Decision.md",
        "source_url": "https://example.invalid/engineering/Architecture%20Decision.md?ref=pilot",
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "metadata": {
            "owner": "platform",
            "path": r"C:\Engineering\Decision Records\Architecture Decision.md",
            "labels": ["pilot", "evidence"],
        },
        "image_descriptions": [{"source_block": "figure-1", "description": "A local evidence flow diagram."}],
    }


class Phase1LocalTests(unittest.TestCase):
    def test_ingest_keeps_verbatim_provenance_and_retrieves_raw_evidence(self) -> None:
        with local_tempdir() as temporary:
            with LocalTrace(temporary) as trace:
                stored = trace.ingest(record())
                atom = trace.get_atom(stored["atom_id"])
                self.assertEqual(atom["source"]["document_name"], "Architecture Decision.md")
                self.assertEqual(atom["source"]["source_url"], record()["source_url"])
                self.assertEqual(atom["source"]["metadata"], record()["metadata"])
                self.assertEqual(atom["source"]["image_descriptions"], record()["image_descriptions"])
                self.assertEqual(trace.get_attachment(stored["attachment_id"]).decode("utf-8"), record()["content"])
                response = trace.query("raw source evidence")
                self.assertEqual(response["sufficiency_state"], "answerable")
                self.assertEqual(response["results"][0]["atom_id"], stored["atom_id"])
                self.assertEqual(response["results"][0]["source"]["attachment_id"], stored["attachment_id"])
                self.assertEqual(trace.query("local evidence flow diagram")["results"][0]["atom_id"], stored["atom_id"])
                self.assertTrue(trace.status()["offline_by_default"])
                self.assertFalse(trace.status()["runtime_network_access"])

    def test_external_id_is_idempotent_but_never_overwrites_source_atom(self) -> None:
        with local_tempdir() as temporary:
            with LocalTrace(temporary) as trace:
                first = trace.ingest(record())
                duplicate = trace.ingest(record())
                self.assertEqual(first["atom_id"], duplicate["atom_id"])
                self.assertTrue(duplicate["duplicate"])
                changed = record(content="Changed evidence must be a new immutable source atom.")
                with self.assertRaises(RecordValidationError):
                    trace.ingest(changed)
                self.assertEqual(trace.status()["canonical"]["source_atoms"], 1)

    def test_json_and_windows_bom_jsonl_are_accepted_and_query_latency_persists(self) -> None:
        with local_tempdir() as temporary:
            root = Path(temporary)
            jsonl = root / "records.jsonl"
            import json

            jsonl.write_bytes(b"\xef\xbb\xbf" + (json.dumps(record()) + "\n").encode("utf-8"))
            with LocalTrace(root / "store") as trace:
                self.assertEqual(len(trace.ingest_jsonl(jsonl)), 1)
                self.assertEqual(len(trace.ingest_json(record(record_id="json-2"))), 1)
                trace.query("source evidence")
            with LocalTrace(root / "store") as reopened:
                self.assertGreaterEqual(reopened.status()["queries"]["observed_count"], 1)

    def test_export_import_and_projection_rebuild_preserve_query_parity(self) -> None:
        with local_tempdir() as temporary:
            root = Path(temporary)
            with LocalTrace(root / "source") as source:
                first = source.ingest(record())
                second = source.ingest(
                    record(
                        record_id="dependency-2",
                        content="The deployment depends on the local SQLite event ledger.",
                    )
                )
                proposal = source.propose(
                    "relation",
                    {"relation": "depends_on", "from": first["atom_id"], "to": second["atom_id"]},
                    [first["atom_id"], second["atom_id"]],
                )
                self.assertEqual(proposal["status"], "pending")
                navigation = source.generate_navigation_summary([first["atom_id"], second["atom_id"]])
                self.assertEqual(len(navigation["sections"]), 2)
                before_ids = [item["atom_id"] for item in source.query("local event ledger")["results"]]
                exported = source.export(root / "trace-export.zip")
                self.assertEqual(exported["counts"]["atoms"], 2)
                rebuilt = source.rebuild_projections()
                self.assertTrue(rebuilt["parity"])
                self.assertTrue(source.verify_integrity()["valid"])
            with LocalTrace(root / "imported") as target:
                imported = target.import_bundle(root / "trace-export.zip")
                self.assertTrue(imported["integrity"]["valid"])
                self.assertEqual(
                    before_ids,
                    [item["atom_id"] for item in target.query("local event ledger")["results"]],
                )
                self.assertTrue(target.verify_integrity()["projection_parity"])

    def test_import_rejects_navigation_not_anchored_to_source_text(self) -> None:
        with local_tempdir() as temporary:
            root = Path(temporary)
            archive_path = root / "source.zip"
            tampered_path = root / "tampered.zip"
            with LocalTrace(root / "source") as source:
                stored = source.ingest(record())
                source.generate_navigation_summary([stored["atom_id"]])
                source.export(archive_path)
            with zipfile.ZipFile(archive_path, "r") as archive:
                members = {
                    member.filename: archive.read(member.filename)
                    for member in archive.infolist()
                    if not member.is_dir()
                }
            summaries = [
                json.loads(line)
                for line in members["navigation_summaries.jsonl"].decode("utf-8").splitlines()
                if line
            ]
            summaries[0]["sections"][0]["excerpt"] = "An unsupported conclusion not found in the source."
            members["navigation_summaries.jsonl"] = (
                "\n".join(json.dumps(summary, sort_keys=True, separators=(",", ":")) for summary in summaries) + "\n"
            ).encode("utf-8")
            with zipfile.ZipFile(tampered_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, raw in members.items():
                    archive.writestr(name, raw)
            with LocalTrace(root / "target") as target:
                with self.assertRaises(ImportBundleError):
                    target.import_bundle(tampered_path)

    def test_navigation_auto_publish_requires_exact_source_spans_and_other_derivations_review(self) -> None:
        with local_tempdir() as temporary:
            with LocalTrace(temporary) as trace:
                stored = trace.ingest(record())
                with self.assertRaises(RecordValidationError):
                    trace.publish_navigation_summary(
                        title="Unsupported conclusion",
                        sections=[{"atom_id": stored["atom_id"], "excerpt": "This fact was invented."}],
                        evidence_atom_ids=[stored["atom_id"]],
                    )
                proposal = trace.propose(
                    "claim",
                    {"claim": "Trace is globally correct"},
                    [stored["atom_id"]],
                )
                self.assertEqual(proposal["status"], "pending")
                approved = trace.review_proposal(
                    proposal["proposal_id"],
                    decision="approved",
                    reviewer="reviewer",
                    reason="reviewed manually",
                )
                self.assertEqual(approved["status"], "approved")

    def test_pressure_rejects_new_writes_and_defers_nonessential_rebuilds(self) -> None:
        free = [10_000_000]

        def probe(_: Path) -> tuple[int, int]:
            return free[0], 100_000

        policy = ResourcePolicy(reserve_bytes=100, minimum_reserve_bytes=1, maximum_reserve_bytes=100)
        with local_tempdir() as temporary:
            with LocalTrace(temporary, resource_policy=policy, resource_probe=probe) as trace:
                trace.ingest(record())
                free[0] = 150
                deferred = trace.rebuild_projections()
                self.assertEqual(deferred["status"], "deferred")
                self.assertEqual(trace.status()["capacity"]["pressure"], "constrained")
                free[0] = 50
                with self.assertRaises(CapacityError):
                    trace.ingest(record(record_id="capacity-2"))

    def test_explicit_local_plugins_are_bounded_to_lexical_candidates(self) -> None:
        class Embedder:
            provider_id = "test-local-embedder"

            def embed(self, texts):
                return [[float(text.lower().count("event")), float(text.lower().count("ledger"))] for text in texts]

        class Reranker:
            provider_id = "test-local-reranker"

            def score(self, query, documents):
                return [float(document.lower().count("ledger")) for document in documents]

        with local_tempdir() as temporary:
            with LocalTrace(temporary) as trace:
                trace.ingest(record(content="Event ledger evidence is local."))
                trace.ingest(record(record_id="other", content="A different source atom."))
                hybrid = trace.query("event ledger", mode="hybrid", embedding_plugin=Embedder())
                reranked = trace.query("event ledger", mode="rerank", reranker_plugin=Reranker())
                self.assertEqual(hybrid["plugins"]["embedding"], "test-local-embedder")
                self.assertEqual(reranked["plugins"]["reranker"], "test-local-reranker")

    def test_pilot_gate_requires_frozen_quality_and_measurement_evidence(self) -> None:
        classes = [
            "direct_lookup",
            "dependency",
            "contradiction",
            "chronology",
            "navigation",
            "out_of_scope",
        ]
        judgments = []
        for index in range(100):
            query_class = classes[index % len(classes)]
            gold = [] if query_class == "out_of_scope" else [f"atom-{index}"]
            judgments.append(
                {
                    "query_class": query_class,
                    "gold_evidence_atom_ids": gold,
                    "retrieved_atom_ids": gold,
                    "selected_citation_atom_ids": gold,
                }
            )
        report = {
            "hardware_profile": {"name": "test machine", "memory_bytes": 16 * 1024**3, "storage": "ssd"},
            "source_atoms": 100,
            "average_tokens_per_atom": 12.5,
            "immutable_version_growth": {"new_atoms": 0, "superseded_atoms": 0},
            "judged_queries": judgments,
            "navigation_summary_reviews": [{"decision": "approved"} for _ in range(7)] + [{"decision": "rejected"} for _ in range(3)],
            "latency_by_class": {query_class: {"p95_ms": 20} for query_class in classes},
            "critical_defects": [],
        }
        result = evaluate_pilot(report)
        self.assertTrue(result["passed"], result)

    def test_public_fixture_is_reproducible_and_keeps_source_evidence_local(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with local_tempdir() as temporary:
            with LocalTrace(temporary) as trace:
                report = run_public_fixture(
                    trace,
                    corpus_path=root / "fixtures" / "phase1" / "public-corpus.jsonl",
                    judgments_path=root / "fixtures" / "phase1" / "public-judged-queries.json",
                )
                self.assertEqual(len(report["judged_queries"]), 100)
                self.assertTrue(report["integrity"]["valid"])
                self.assertEqual(
                    {entry["query_class"] for entry in report["judged_queries"]},
                    {"direct_lookup", "dependency", "contradiction", "chronology", "navigation", "out_of_scope"},
                )

    def test_export_streams_full_event_lineage_beyond_public_event_page_limit(self) -> None:
        with local_tempdir() as temporary:
            root = Path(temporary)
            with LocalTrace(root / "store") as trace:
                with trace._transaction() as connection:
                    for index in range(10_005):
                        trace._append_event(
                            connection,
                            "fixture.event",
                            {"index": index},
                            actor="test",
                        )
                exported = trace.export(root / "events.zip")
                self.assertEqual(exported["counts"]["events"], 10_005)
            with zipfile.ZipFile(root / "events.zip") as archive:
                event_lines = [
                    line
                    for line in archive.read("events.jsonl").decode("utf-8").splitlines()
                    if line
                ]
                self.assertEqual(len(event_lines), 10_005)


if __name__ == "__main__":
    unittest.main()
