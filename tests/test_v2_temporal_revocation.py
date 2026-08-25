from __future__ import annotations

import hashlib
import hmac
import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trace.v2.models import IngestionRequest, QueryRequest, ValidTimeMetadata
from trace.v2.store import SqliteEventStore


class TemporalRevocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SqliteEventStore(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def _ingest(self, content: str, *, temporal: dict[str, object] | None = None) -> dict[str, object]:
        raw = content.encode("utf-8")
        content_hash = hashlib.sha256(raw).hexdigest()
        result = self.store.ingest(
            workspace_id="alpha",
            source={"uri": "fixture://tr2", "media_type": "text/plain", "adapter": "test"},
            attachment={
                "content_hash": content_hash,
                "object_key": f"fixture/{content_hash}",
                "media_type": "text/plain",
                "byte_length": len(raw),
                "metadata": {},
            },
            atoms=[{
                "content": content,
                "start": 0,
                "end": len(content),
                "ordinal": 0,
                "parser_location": "fixture:1",
                "temporal": temporal or {},
            }],
            actor="test",
            visibility="private",
            idempotency_key=None,
        )
        return self.store.ingestion_atoms(result["ingestion_id"])[0]

    def test_valid_time_is_explicit_half_open_and_unknown_is_not_inferred(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 2, 1, tzinfo=UTC)
        dated = self._ingest(
            "dated source",
            temporal={
                "valid_from": start.isoformat(), "valid_to": end.isoformat(),
                "precision": "month", "confidence": "explicit", "provenance": {"field": "source"},
            },
        )
        unknown = self._ingest("unknown source")

        inside = self.store.queryable_atoms("alpha", valid_at=end - timedelta(seconds=1))
        boundary = self.store.queryable_atoms("alpha", valid_at=end)
        self.assertIn(dated["atom_version_id"], {item["atom_version_id"] for item in inside})
        self.assertNotIn(dated["atom_version_id"], {item["atom_version_id"] for item in boundary})
        self.assertNotIn(unknown["atom_version_id"], {item["atom_version_id"] for item in inside})

        with self.assertRaises(ValueError):
            ValidTimeMetadata(valid_from=start, valid_to=end, precision="unknown", confidence="explicit")
        with self.assertRaises(ValueError):
            IngestionRequest(
                workspace_id="alpha", text="naive boundary", valid_from=datetime(2024, 1, 1),
                valid_to=end, valid_time_precision="month", valid_time_confidence="explicit",
            )

    def test_edit_preserves_immutable_lineage_and_historical_version(self) -> None:
        original = self._ingest("original assertion")
        before_edit = self.store.last_event_offset()
        successor = self.store.edit_node(
            node_id=original["node_id"], content="corrected assertion", properties={}, actor="editor"
        )

        self.assertEqual(
            self.store.get_source_lifecycle(original["atom_version_id"])["state"], "superseded"
        )
        self.assertEqual(
            self.store.get_source_lifecycle(original["atom_version_id"])["superseded_by_atom_version_id"],
            successor["atom_version_id"],
        )
        self.assertEqual(
            self.store.get_source_lifecycle(original["atom_version_id"], as_of_event=before_edit)["state"],
            "active",
        )
        historical_ids = {item["atom_version_id"] for item in self.store.queryable_atoms("alpha", before_edit)}
        current_ids = {item["atom_version_id"] for item in self.store.queryable_atoms("alpha")}
        self.assertIn(original["atom_version_id"], historical_ids)
        self.assertIn(successor["atom_version_id"], current_ids)
        self.assertNotIn(original["atom_version_id"], current_ids)

    def test_contradiction_is_explicit_and_does_not_make_assertions_unreadable(self) -> None:
        left = self._ingest("left assertion")
        right = self._ingest("right assertion")
        edge = self.store.create_edge(
            workspace_id="alpha", source_node_id=left["node_id"], target_node_id=right["node_id"],
            relation_type="contradicts", evidence_atom_version_ids=[left["atom_version_id"], right["atom_version_id"]],
            actor="reviewer", model_version="manual", confidence=1.0, weight=1.0,
            status="trusted", properties={"reason": "reviewed"},
        )

        self.assertEqual(self.store.get_source_lifecycle(left["atom_version_id"])["state"], "conflicted")
        self.assertEqual(self.store.get_source_lifecycle(right["atom_version_id"])["state"], "conflicted")
        self.assertLessEqual(edge["event_offset"], self.store.last_event_offset())
        current_ids = {item["atom_version_id"] for item in self.store.queryable_atoms("alpha")}
        self.assertTrue({left["atom_version_id"], right["atom_version_id"]} <= current_ids)

    def test_revocation_and_tombstone_are_currently_denied_even_at_old_watermark(self) -> None:
        revoked = self._ingest("revoked source")
        old_watermark = self.store.last_event_offset()
        self.store.revoke_source(revoked["atom_version_id"], actor="compliance", reason="withdrawn")

        historical = self.store.temporal_visibility(revoked, as_of_event=old_watermark)
        self.assertFalse(historical["visible"])
        self.assertEqual(historical["exclusion_reason"], "current_lifecycle_revoked")
        self.assertEqual(
            self.store.get_source_lifecycle(revoked["atom_version_id"], as_of_event=old_watermark)["state"],
            "active",
        )

        tombstoned = self._ingest("tombstoned source")
        self.store.tombstone_source(tombstoned["atom_version_id"], actor="compliance", reason="invalidated")
        current_ids = {item["atom_version_id"] for item in self.store.queryable_atoms("alpha")}
        self.assertNotIn(revoked["atom_version_id"], current_ids)
        self.assertNotIn(tombstoned["atom_version_id"], current_ids)

    def test_erasure_removes_readable_payload_and_projection_coverage_with_signed_receipt(self) -> None:
        source = self._ingest("legally erased source")
        run = self.store.create_projection_run(
            workspace_id="alpha", projection_kind="hierarchy", revision="tr2-test",
            input_checksum="fixture", actor="test",
        )
        self.store.transition_projection_run(run["projection_run_id"], status="running", actor="test")
        self.store.write_projection_objects(
            projection_run_id=run["projection_run_id"],
            objects=[{
                "projection_object_id": "projection-source",
                "object_kind": "summary",
                "logical_key": "source",
                "content": "derived projection content",
                "source_atom_version_ids": [source["atom_version_id"]],
            }],
            actor="test",
        )

        lifecycle = self.store.erase_source(
            source["atom_version_id"], signing_key="test-signing-key", actor="compliance", reason="erasure request"
        )
        receipt = lifecycle["erasure_receipt"]
        self.assertEqual(lifecycle["state"], "redacted_purged")
        self.assertEqual(receipt["action"], "redacted_purged")
        payload = {key: value for key, value in receipt.items() if key != "signature"}
        expected = hmac.new(
            b"test-signing-key", json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"), hashlib.sha256
        ).hexdigest()
        self.assertEqual(receipt["signature"], expected)
        self.assertEqual(self.store.atom_versions([source["atom_version_id"]])[0]["content"], "")
        self.assertNotIn(source["atom_version_id"], {item["atom_version_id"] for item in self.store.queryable_atoms("alpha")})
        with self.store._connect() as conn:
            remaining = conn.execute(
                "SELECT COUNT(*) FROM projection_objects WHERE projection_object_id='projection-source'"
            ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_repeat_erasure_is_idempotent_and_returns_original_receipt(self) -> None:
        source = self._ingest("source to be erased multiple times")
        first = self.store.erase_source(
            source["atom_version_id"], signing_key="test-signing-key", actor="compliance", reason="gdpr"
        )
        second = self.store.erase_source(
            source["atom_version_id"], signing_key="test-signing-key", actor="compliance", reason="gdpr"
        )
        self.assertEqual(first["erasure_receipt"]["receipt_id"], second["erasure_receipt"]["receipt_id"])
        self.assertEqual(first["erasure_receipt"]["signature"], second["erasure_receipt"]["signature"])
        self.assertEqual(first["event_offset"], second["event_offset"])
        self.assertEqual(second["state"], "redacted_purged")

    def test_service_erasure_deletes_raw_object_from_object_store(self) -> None:
        import os
        import tempfile
        from trace.v2.models import SourceErasureRequest
        from trace.v2.service import LocalPrivateObjectStore, TraceService

        with tempfile.TemporaryDirectory() as tmpdir:
            object_store = LocalPrivateObjectStore(tmpdir)
            put_res = object_store.put_text("confidential attachment content", "text/plain", workspace_id="alpha")
            object_key = put_res["object_key"]
            self.assertTrue((Path(tmpdir) / object_key).exists())

            source = self._ingest("atom with attachment")
            # Link attachment object_key to node properties
            self.store.edit_node(
                node_id=source["node_id"],
                content="atom with attachment",
                properties={"object_key": object_key},
                actor="test",
            )
            atom_ver_id = self.store.get_node(source["node_id"])["atom_version_id"]

            os.environ["TRACE_ERASURE_SIGNING_KEY"] = "test-signing-key"
            try:
                service = TraceService(self.store, object_store)
                res = service.erase_source(atom_ver_id, SourceErasureRequest(actor="compliance", reason="erasure"))
                self.assertEqual(res["state"], "redacted_purged")
                self.assertFalse((Path(tmpdir) / object_key).exists())
            finally:
                os.environ.pop("TRACE_ERASURE_SIGNING_KEY", None)

    def test_historical_release_identity_and_missing_history_fail_closed(self) -> None:
        self._ingest("release identity evidence")
        planned = self.store.create_cortex_release(workspace_id="alpha", actor="release-controller")
        self.store.validate_cortex_release(
            planned["release_id"], {"passed": True, "receipt_id": "tr2-test"}, actor="release-validator"
        )
        activated = self.store.activate_cortex_release(planned["release_id"], actor="release-controller")
        activated_at = int(activated["activated_event_offset"])
        resolved = self.store.get_cortex_release_as_of_event("alpha", activated_at)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["release_id"], planned["release_id"])
        self.assertEqual(len(resolved["components"]), 5)
        self.assertIsNone(self.store.get_cortex_release_as_of_event("alpha", activated_at - 1))

        from trace.v2.service import TraceService

        service = TraceService(self.store, object())
        unavailable = service.query(
            QueryRequest(workspace_id="alpha", query="release evidence", as_of_event=activated_at - 1)
        )
        self.assertEqual(unavailable["status"], "historical_unavailable")
        self.assertEqual(unavailable["results"], [])


if __name__ == "__main__":
    unittest.main()
