from __future__ import annotations

import hashlib
import hmac
import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trace.v2.auth import AuthorizationContext, Principal
from trace.v2.models import IngestionRequest, QueryRequest, ValidTimeMetadata
from trace.v2.service import TEMPORAL_EXCLUSION_DETAIL_LIMIT
from trace.v2.store import SqliteEventStore


class TemporalRevocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SqliteEventStore(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def _ingest(
        self,
        content: str,
        *,
        temporal: dict[str, object] | None = None,
        visibility: str = "private",
    ) -> dict[str, object]:
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
            visibility=visibility,
            idempotency_key=None,
        )
        return self.store.ingestion_atoms(result["ingestion_id"])[0]

    def _activate_release(self) -> int:
        planned = self.store.create_cortex_release(workspace_id="alpha", actor="release-controller")
        self.store.validate_cortex_release(
            planned["release_id"], {"passed": True, "receipt_id": "authorization-test"},
            actor="release-validator",
        )
        activated = self.store.activate_cortex_release(
            planned["release_id"], actor="release-controller"
        )
        return int(activated["activated_event_offset"])

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

    def test_valid_time_selects_predecessor_before_current_version_filter(self) -> None:
        january = datetime(2024, 1, 1, tzinfo=UTC)
        june = datetime(2024, 6, 1, tzinfo=UTC)
        december = datetime(2024, 12, 1, tzinfo=UTC)
        original = self._ingest(
            "historical price was ten",
            temporal={
                "valid_from": january.isoformat(),
                "valid_to": june.isoformat(),
                "precision": "day",
                "confidence": "explicit",
                "provenance": {"field": "effective_date"},
            },
        )
        successor = self.store.edit_node(
            node_id=original["node_id"],
            content="historical price became twelve",
            properties={
                "temporal": {
                    "valid_from": june.isoformat(),
                    "valid_to": december.isoformat(),
                    "precision": "day",
                    "confidence": "explicit",
                    "provenance": {"field": "effective_date"},
                }
            },
            actor="editor",
        )

        before_boundary = self.store.queryable_atoms(
            "alpha", valid_at=june - timedelta(seconds=1)
        )
        at_boundary = self.store.queryable_atoms("alpha", valid_at=june)

        from trace.v2.service import TraceService

        service = TraceService(self.store, object())
        before_response = service.query(
            QueryRequest(
                workspace_id="alpha",
                query="historical price",
                valid_at=june - timedelta(seconds=1),
            )
        )
        boundary_response = service.query(
            QueryRequest(workspace_id="alpha", query="historical price", valid_at=june)
        )

        self.assertIn(original["atom_version_id"], {item["atom_version_id"] for item in before_boundary})
        self.assertNotIn(successor["atom_version_id"], {item["atom_version_id"] for item in before_boundary})
        self.assertIn(successor["atom_version_id"], {item["atom_version_id"] for item in at_boundary})
        self.assertNotIn(original["atom_version_id"], {item["atom_version_id"] for item in at_boundary})
        self.assertIn(original["atom_version_id"], {item["atom_version_id"] for item in before_response["results"]})
        self.assertNotIn(successor["atom_version_id"], {item["atom_version_id"] for item in before_response["results"]})
        self.assertIn(successor["atom_version_id"], {item["atom_version_id"] for item in boundary_response["results"]})
        self.assertNotIn(original["atom_version_id"], {item["atom_version_id"] for item in boundary_response["results"]})

    def test_temporal_bundle_retains_source_revision_and_exclusion_metadata(self) -> None:
        from trace.v2.service import TraceService

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 2, 1, tzinfo=UTC)
        dated = self._ingest(
            "temporal marker dated",
            temporal={
                "valid_from": start.isoformat(),
                "valid_to": end.isoformat(),
                "precision": "month",
                "confidence": "explicit",
                "provenance": {"field": "source"},
            },
        )
        unknown = self._ingest("temporal marker unknown")
        response = TraceService(self.store, object()).query(
            QueryRequest(
                workspace_id="alpha",
                query="temporal marker",
                valid_at=start + timedelta(days=1),
            )
        )

        result = next(item for item in response["results"] if item["atom_version_id"] == dated["atom_version_id"])
        self.assertEqual(result["source_revision"], dated["atom_version_id"])
        self.assertEqual(result["temporal"]["requested_valid_at"], (start + timedelta(days=1)).isoformat())
        self.assertEqual(result["temporal"]["provenance"], {"field": "source"})
        exclusions = response["retrieval_diagnostics"]["temporal_exclusion_details"]
        exclusion = next(item for item in exclusions if item["source_revision"] == unknown["atom_version_id"])
        self.assertEqual(exclusion["exclusion_reason"], "valid_time_unknown_or_partial")
        self.assertEqual(exclusion["policy_result"], "excluded")
        self.assertIn("release_id", exclusion)

    def test_unauthorized_temporal_exclusion_is_aggregate_only_in_response_and_bundle(self) -> None:
        marker = "never-disclose-this-provenance"
        source = self._ingest(
            "unauthorized temporal secret",
            temporal={
                "valid_from": "2024-01-01T00:00:00+00:00",
                "valid_to": "2024-02-01T00:00:00+00:00",
                "precision": "day",
                "confidence": "explicit",
                "provenance": {"marker": marker},
            },
        )
        context = AuthorizationContext(
            principal=Principal(
                subject="public-only",
                auth_method="test",
                workspace_ids=frozenset({"alpha"}),
                allowed_visibility=frozenset({"public"}),
            ),
            workspace_id="alpha",
            allowed_visibility=frozenset({"public"}),
        )

        from trace.v2.service import TraceService

        response = TraceService(self.store, object()).query(
            QueryRequest(
                workspace_id="alpha",
                query="unauthorized temporal secret",
                valid_at=datetime(2025, 1, 1, tzinfo=UTC),
            ),
            authorization_context=context,
        )
        diagnostics = response["retrieval_diagnostics"]
        self.assertEqual(diagnostics["temporal_exclusions"], {"current_authorization_denied": 1})
        self.assertEqual(diagnostics["temporal_exclusion_details"], [])
        self.assertFalse(diagnostics["temporal_exclusion_details_truncated"])
        persisted = self.store.get_bundle(response["evidence_bundle_id"])
        serialized = json.dumps(persisted["query"]["retrieval_diagnostics"], sort_keys=True)
        self.assertNotIn(str(source["atom_version_id"]), serialized)
        self.assertNotIn(marker, serialized)

    def test_historical_public_current_private_uses_most_restrictive_authorization(self) -> None:
        source = self._ingest("authorization reclassification public private", visibility="public")
        activated_at = self._activate_release()
        context = AuthorizationContext(
            principal=Principal(
                subject="public-only",
                auth_method="test",
                workspace_ids=frozenset({"alpha"}),
                allowed_visibility=frozenset({"public"}),
            ),
            workspace_id="alpha",
            allowed_visibility=frozenset({"public"}),
            as_of_event=activated_at,
        )

        from trace.v2.service import TraceService

        service = TraceService(self.store, object())
        allowed = service.query(
            QueryRequest(
                workspace_id="alpha",
                query="authorization reclassification public private",
                as_of_event=activated_at,
            ),
            authorization_context=context,
        )
        evidence = next(
            item for item in allowed["results"]
            if item["atom_version_id"] == source["atom_version_id"]
        )
        self.assertEqual(evidence["temporal"]["authorization_policy_result"], "allowed")
        self.assertIsInstance(evidence["temporal"]["historical_authorization_revision_event"], int)
        self.assertIsInstance(evidence["temporal"]["current_authorization_revision_event"], int)

        self.store.transition_source_authorization(
            str(source["atom_version_id"]),
            visibility="private",
            actor="policy-admin",
            reason="classification raised",
        )
        denied = service.query(
            QueryRequest(
                workspace_id="alpha",
                query="authorization reclassification public private",
                as_of_event=activated_at,
            ),
            authorization_context=context,
        )
        self.assertNotIn(source["atom_version_id"], {item["atom_version_id"] for item in denied["results"]})
        self.assertEqual(denied["retrieval_diagnostics"]["temporal_exclusions"], {"current_authorization_denied": 1})
        self.assertEqual(denied["retrieval_diagnostics"]["temporal_exclusion_details"], [])
        persisted = self.store.get_bundle(denied["evidence_bundle_id"])
        serialized = json.dumps(persisted["query"]["retrieval_diagnostics"], sort_keys=True)
        self.assertNotIn(str(source["atom_version_id"]), serialized)
        self.assertNotIn("current_authorization_revision_event", serialized)
        self.assertNotIn("historical_authorization_revision_event", serialized)

    def test_historical_private_current_public_uses_most_restrictive_authorization(self) -> None:
        source = self._ingest("authorization reclassification private public", visibility="private")
        activated_at = self._activate_release()
        self.store.transition_source_authorization(
            str(source["atom_version_id"]),
            visibility="public",
            actor="policy-admin",
            reason="classification lowered",
        )
        context = AuthorizationContext(
            principal=Principal(
                subject="public-only",
                auth_method="test",
                workspace_ids=frozenset({"alpha"}),
                allowed_visibility=frozenset({"public"}),
            ),
            workspace_id="alpha",
            allowed_visibility=frozenset({"public"}),
            as_of_event=activated_at,
        )

        from trace.v2.service import TraceService

        denied = TraceService(self.store, object()).query(
            QueryRequest(
                workspace_id="alpha",
                query="authorization reclassification private public",
                as_of_event=activated_at,
            ),
            authorization_context=context,
        )
        self.assertNotIn(source["atom_version_id"], {item["atom_version_id"] for item in denied["results"]})
        self.assertEqual(
            denied["retrieval_diagnostics"]["temporal_exclusions"],
            {"historical_authorization_denied": 1},
        )
        self.assertEqual(denied["retrieval_diagnostics"]["temporal_exclusion_details"], [])

    def test_missing_historical_authorization_fails_closed_without_record_details(self) -> None:
        source = self._ingest("malformed authorization history sentinel", visibility="public")
        activated_at = self._activate_release()
        with self.store.transaction() as conn:
            row = conn.execute(
                """SELECT e.event_offset,e.payload_json FROM events e
                     JOIN nodes n ON n.created_event_offset=e.event_offset
                    WHERE n.node_id=?""",
                (source["node_id"],),
            ).fetchone()
            payload = json.loads(row["payload_json"])
            payload.pop("security", None)
            conn.execute(
                "UPDATE events SET payload_json=? WHERE event_offset=?",
                (json.dumps(payload, sort_keys=True), row["event_offset"]),
            )
        context = AuthorizationContext(
            principal=Principal(
                subject="public-only",
                auth_method="test",
                workspace_ids=frozenset({"alpha"}),
                allowed_visibility=frozenset({"public"}),
            ),
            workspace_id="alpha",
            allowed_visibility=frozenset({"public"}),
            as_of_event=activated_at,
        )

        from trace.v2.service import TraceService

        response = TraceService(self.store, object()).query(
            QueryRequest(
                workspace_id="alpha",
                query="malformed authorization history sentinel",
                as_of_event=activated_at,
            ),
            authorization_context=context,
        )
        self.assertEqual(response["status"], "historical_unavailable")
        self.assertEqual(response["results"], [])
        self.assertEqual(
            response["retrieval_diagnostics"]["temporal_exclusions"],
            {"historical_authorization_unavailable": 1},
        )
        self.assertEqual(response["retrieval_diagnostics"]["temporal_exclusion_details"], [])
        persisted = self.store.get_bundle(response["evidence_bundle_id"])
        serialized = json.dumps(persisted, sort_keys=True)
        self.assertNotIn(str(source["atom_version_id"]), serialized)

    def test_later_security_change_cannot_replace_missing_created_baseline(self) -> None:
        source = self._ingest("missing baseline after authorization change", visibility="private")
        activated_at = self._activate_release()
        self.store.transition_source_authorization(
            str(source["atom_version_id"]), visibility="public", actor="policy-admin",
        )
        with self.store.transaction() as conn:
            row = conn.execute(
                """SELECT e.event_offset,e.payload_json FROM events e
                     JOIN nodes n ON n.created_event_offset=e.event_offset
                    WHERE n.node_id=?""",
                (source["node_id"],),
            ).fetchone()
            payload = json.loads(row["payload_json"])
            payload.pop("security", None)
            conn.execute(
                "UPDATE events SET payload_json=? WHERE event_offset=?",
                (json.dumps(payload, sort_keys=True), row["event_offset"]),
            )
        resolved = self.store.resolve_source_authorization(
            str(source["atom_version_id"]), as_of_event=activated_at,
        )
        self.assertFalse(resolved["available"])
        self.assertEqual(resolved["exclusion_reason"], "historical_authorization_unavailable")

    def test_multiple_authorization_changes_resolve_latest_at_or_before_event(self) -> None:
        source = self._ingest("multiple authorization revisions sentinel", visibility="public")
        self._activate_release()
        private = self.store.transition_source_authorization(
            str(source["atom_version_id"]), visibility="private", actor="policy-admin",
        )
        internal = self.store.transition_source_authorization(
            str(source["atom_version_id"]), visibility="internal", actor="policy-admin",
        )
        resolved = self.store.resolve_source_authorization(
            str(source["atom_version_id"]),
            as_of_event=int(private["authorization_revision_event"]),
        )
        self.assertEqual(resolved["historical_security"]["visibility"], "private")
        self.assertEqual(resolved["current_security"]["visibility"], "internal")
        self.assertEqual(
            resolved["historical_authorization_revision_event"],
            private["authorization_revision_event"],
        )
        self.assertEqual(
            resolved["current_authorization_revision_event"],
            internal["authorization_revision_event"],
        )

    def test_same_authorization_is_zero_event_and_replay_updates_hot_security(self) -> None:
        source = self._ingest("authorization replay and hot inbox sentinel", visibility="public")
        changed = self.store.transition_source_authorization(
            str(source["atom_version_id"]), visibility="private", actor="policy-admin",
        )
        before_repeat = self.store.last_event_offset()
        repeated = self.store.transition_source_authorization(
            str(source["atom_version_id"]), visibility="private", actor="policy-admin",
        )
        self.assertFalse(repeated["changed"])
        self.assertEqual(repeated["authorization_revision_event"], changed["authorization_revision_event"])
        self.assertEqual(self.store.last_event_offset(), before_repeat)
        hot = self.store.hot_candidates(
            "alpha", "authorization replay hot inbox", visibility=["private"]
        )
        self.assertIn(source["atom_version_id"], {item["atom_version_id"] for item in hot})
        self.assertTrue(self.store.replay_report("alpha")["valid"])

    def test_authorized_temporal_exclusion_details_are_bounded_with_exact_aggregates(self) -> None:
        total = TEMPORAL_EXCLUSION_DETAIL_LIMIT + 5
        for index in range(total):
            self._ingest(f"bounded unknown temporal {index}")

        from trace.v2.service import TraceService

        response = TraceService(self.store, object()).query(
            QueryRequest(
                workspace_id="alpha",
                query="bounded unknown temporal",
                valid_at=datetime(2025, 1, 1, tzinfo=UTC),
            )
        )
        diagnostics = response["retrieval_diagnostics"]
        self.assertEqual(diagnostics["temporal_exclusions"]["valid_time_unknown_or_partial"], total)
        self.assertEqual(len(diagnostics["temporal_exclusion_details"]), TEMPORAL_EXCLUSION_DETAIL_LIMIT)
        self.assertTrue(diagnostics["temporal_exclusion_details_truncated"])
        self.assertEqual(diagnostics["temporal_exclusion_details_omitted_count"], 5)
        persisted = self.store.get_bundle(response["evidence_bundle_id"])
        stored = persisted["query"]["retrieval_diagnostics"]
        self.assertEqual(stored["temporal_exclusions"]["valid_time_unknown_or_partial"], total)
        self.assertEqual(stored["temporal_exclusion_details_omitted_count"], 5)

    def test_revision_rebuild_retains_immutable_predecessor_versions(self) -> None:
        from trace.v2.service import TraceService

        original = self._ingest("revision rebuild predecessor")
        successor = self.store.edit_node(
            node_id=original["node_id"],
            content="revision rebuild successor",
            properties={},
            actor="editor",
        )

        class RecordingIndex:
            def __init__(self) -> None:
                self.atom_ids: list[str] = []

            def upsert(self, documents: list[dict[str, object]], *, revision: str) -> int:
                del revision
                self.atom_ids.extend(str(item["atom_version_id"]) for item in documents)
                return len(documents)

        service = TraceService(self.store, object())
        recording = RecordingIndex()
        service.retrieval_engine.lexical_index = recording
        indexed = service.rebuild_lexical_index("alpha", revision="temporal-r1")

        dense_ids: list[str] = []

        def record_dense(
            workspace_id: str,
            atoms: list[dict[str, object]],
            *,
            actor: str,
            revision: str,
        ) -> int:
            self.assertEqual(workspace_id, "alpha")
            self.assertEqual(actor, "system")
            self.assertEqual(revision, "temporal-r1")
            dense_ids.extend(str(item["atom_version_id"]) for item in atoms)
            return len(atoms)

        service._index_atom_batch = record_dense  # type: ignore[method-assign]
        dense_indexed = service.rebuild_dense_index("alpha", revision="temporal-r1")

        self.assertGreaterEqual(indexed, 2)
        self.assertGreaterEqual(dense_indexed, 2)
        self.assertIn(original["atom_version_id"], recording.atom_ids)
        self.assertIn(successor["atom_version_id"], recording.atom_ids)
        self.assertIn(original["atom_version_id"], dense_ids)
        self.assertIn(successor["atom_version_id"], dense_ids)

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
