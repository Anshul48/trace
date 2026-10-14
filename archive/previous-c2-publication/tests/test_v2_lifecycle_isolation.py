from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trace.v2.cortex import canonical_pair
from trace.v2.models import (
    CortexReleaseCreateRequest,
    CortexReleaseValidateRequest,
    CortexReleaseActivateRequest,
    CortexReleaseRollbackRequest,
    CortexValidationReceipt,
    IngestionRequest,
    QueryRequest,
)
from trace.v2.retrieval import HybridRetrievalEngine
from trace.v2.service import TraceService
from trace.v2.store import InvariantViolation, NotFoundError, SqliteEventStore


class MemoryObjectStore:
    def put_bytes(self, raw: bytes, media_type: str, **_: object) -> dict[str, object]:
        return {
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "object_key": "test/source",
            "media_type": media_type,
            "byte_length": len(raw),
            "metadata": {},
        }

    def put_text(self, text: str, media_type: str, **kwargs: object) -> dict[str, object]:
        return self.put_bytes(text.encode("utf-8"), media_type, **kwargs)


class CortexLifecycleIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SqliteEventStore(":memory:")
        self.service = TraceService(
            self.store,
            MemoryObjectStore(),
            retrieval_engine=HybridRetrievalEngine(),
        )

    def tearDown(self) -> None:
        self.store.close()

    def _ingest(self, workspace_id: str, text: str) -> tuple[dict, list[dict]]:
        ingestion = self.service.ingest(IngestionRequest(workspace_id=workspace_id, text=text))
        return ingestion, self.store.ingestion_atoms(ingestion["ingestion_id"])

    def test_candidate_release_isolation_from_active_readers(self) -> None:
        """Candidate release rows are invisible to active readers until activation."""
        _, atoms = self._ingest("alpha", "alpha node one\n\nalpha node two\n\nalpha node three")
        a1 = atoms[0]["atom_version_id"]
        a2 = atoms[1]["atom_version_id"]

        # Ensure initial active release exists
        active_0 = self.store.get_active_cortex_release("alpha")
        if active_0 is None:
            r0 = self.service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha", policy_revision="v0"))
            self.service.validate_cortex_release(r0["release_id"], CortexReleaseValidateRequest(validation_receipt=CortexValidationReceipt(passed=True)))
            active_0 = self.service.activate_cortex_release(r0["release_id"])
        rel0_id = active_0["release_id"]

        # Put an edge in active release
        self.store.put_affinity_edge(
            workspace_id="alpha",
            source_atom_version_id=a1,
            target_atom_version_id=a2,
            score=0.6,
            signal={"provider": "v0"},
            expires_at="2999-01-01T00:00:00+00:00",
            release_id=rel0_id,
        )

        # Create candidate release (building)
        cand = self.service.create_cortex_release(CortexReleaseCreateRequest(
            workspace_id="alpha",
            policy_revision="cognitive-v2",
        ))
        cand_id = cand["release_id"]
        self.assertEqual(cand["status"], "building")
        self.assertEqual(cand["parent_release_id"], rel0_id)

        # Write candidate-scoped edge and prior
        self.store.put_affinity_edge(
            workspace_id="alpha",
            source_atom_version_id=a1,
            target_atom_version_id=a2,
            score=0.95,
            signal={"provider": "candidate_test"},
            expires_at="2999-01-01T00:00:00+00:00",
            release_id=cand_id,
        )
        self.store.upsert_activation_prior(
            workspace_id="alpha",
            atom_version_id=a1,
            prior_kind="pin",
            score=0.8,
            release_id=cand_id,
        )

        # Active readers must NOT see candidate values
        active_edges = self.store.affinity_neighbors("alpha", [a1])
        self.assertEqual(len(active_edges), 1)
        self.assertEqual(active_edges[0]["score"], 0.6)
        self.assertEqual(active_edges[0]["signal"]["provider"], "v0")

        active_priors = self.store.activation_priors("alpha", [a1])
        self.assertEqual(active_priors, {})

        # Candidate-scoped readers see candidate values
        cand_edges = self.store.affinity_neighbors("alpha", [a1], release_id=cand_id)
        self.assertEqual(len(cand_edges), 1)
        self.assertEqual(cand_edges[0]["score"], 0.95)
        self.assertEqual(cand_edges[0]["signal"]["provider"], "candidate_test")

        cand_priors = self.store.activation_priors("alpha", [a1], release_id=cand_id)
        self.assertIn(a1, cand_priors)
        self.assertEqual(cand_priors[a1][0]["score"], 0.8)

    def test_validation_gate_and_atomic_activation(self) -> None:
        """Release cannot be activated without passing validation, and activation swaps atomically."""
        _, atoms = self._ingest("alpha", "source atom\n\ntarget atom")
        a1, a2 = atoms[0]["atom_version_id"], atoms[1]["atom_version_id"]

        r0 = self.service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha", policy_revision="v0"))
        self.service.validate_cortex_release(r0["release_id"], CortexReleaseValidateRequest(validation_receipt=CortexValidationReceipt(passed=True)))
        self.service.activate_cortex_release(r0["release_id"])

        cand = self.service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha"))
        cand_id = cand["release_id"]

        # Attempting activation while 'building' must fail
        with self.assertRaises(InvariantViolation):
            self.service.activate_cortex_release(cand_id)

        # Fail validation
        failed_receipt = CortexReleaseValidateRequest(
            validation_receipt=CortexValidationReceipt(
                passed=False,
                checks={"affinity_coherence": False},
                failure_detail="affinity cycle detected",
            )
        )
        val_failed = self.service.validate_cortex_release(cand_id, failed_receipt)
        self.assertEqual(val_failed["status"], "failed")

        # Attempting activation while 'failed' must fail
        with self.assertRaises(InvariantViolation):
            self.service.activate_cortex_release(cand_id)

        # Create a second candidate and pass validation
        cand2 = self.service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha"))
        cand2_id = cand2["release_id"]

        passed_receipt = CortexReleaseValidateRequest(
            validation_receipt=CortexValidationReceipt(
                passed=True,
                checks={"schema": True, "watermark": True},
                rationale="all invariants met",
            )
        )
        val_passed = self.service.validate_cortex_release(cand2_id, passed_receipt)
        self.assertEqual(val_passed["status"], "validated")

        # Activate candidate 2
        activated = self.service.activate_cortex_release(cand2_id)
        self.assertEqual(activated["status"], "active")
        self.assertIsNotNone(activated["activated_at"])

        # Check that active pointer moved
        active_now = self.store.get_active_cortex_release("alpha")
        self.assertEqual(active_now["release_id"], cand2_id)

        # Verify previous active release is now superseded
        prev = self.store.get_cortex_release(cand["parent_release_id"])
        self.assertEqual(prev["status"], "superseded")
        self.assertIsNotNone(prev["superseded_at"])

    def test_rollback_to_predecessor_release(self) -> None:
        """Rollback restores predecessor release and marks current active as superseded."""
        _, atoms = self._ingest("alpha", "rollback source\n\nrollback target")
        a1, a2 = atoms[0]["atom_version_id"], atoms[1]["atom_version_id"]

        active_0 = self.store.get_active_cortex_release("alpha")
        if active_0 is None:
            r0 = self.service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha", policy_revision="v0"))
            self.service.validate_cortex_release(r0["release_id"], CortexReleaseValidateRequest(validation_receipt=CortexValidationReceipt(passed=True)))
            active_0 = self.service.activate_cortex_release(r0["release_id"])
        rel0_id = active_0["release_id"]

        # Create, validate, activate release 1
        rel1 = self.service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha"))
        rel1_id = rel1["release_id"]
        self.service.validate_cortex_release(rel1_id, CortexReleaseValidateRequest(
            validation_receipt=CortexValidationReceipt(passed=True)
        ))
        self.service.activate_cortex_release(rel1_id)

        self.assertEqual(self.store.get_active_cortex_release("alpha")["release_id"], rel1_id)

        # Rollback without explicit target restores rel0
        rolled_back = self.service.rollback_cortex_release(CortexReleaseRollbackRequest(
            workspace_id="alpha",
            reason="canary regression detected",
        ))
        self.assertEqual(rolled_back["release_id"], rel0_id)
        self.assertEqual(rolled_back["status"], "active")

        active_after_rollback = self.store.get_active_cortex_release("alpha")
        self.assertEqual(active_after_rollback["release_id"], rel0_id)

        # rel1 is now superseded
        rel1_after = self.store.get_cortex_release(rel1_id)
        self.assertEqual(rel1_after["status"], "superseded")

    def test_workspace_isolation_and_cross_tenant_containment(self) -> None:
        """Releases and scoped rows from workspace alpha are strictly inaccessible in beta."""
        _, atoms_alpha = self._ingest("alpha", "alpha private knowledge")
        _, atoms_beta = self._ingest("beta", "beta private knowledge")

        rel_alpha = self.service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha"))
        rel_beta = self.service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="beta"))

        self.service.validate_cortex_release(rel_alpha["release_id"], CortexReleaseValidateRequest(
            validation_receipt=CortexValidationReceipt(passed=True)
        ))
        self.service.activate_cortex_release(rel_alpha["release_id"])

        # Listing in beta does not contain alpha release
        beta_releases = self.service.list_cortex_releases("beta")
        beta_rel_ids = {r["release_id"] for r in beta_releases}
        self.assertIn(rel_beta["release_id"], beta_rel_ids)
        self.assertNotIn(rel_alpha["release_id"], beta_rel_ids)

        # Cross workspace lookup raises InvariantViolation or empty
        with self.assertRaises(InvariantViolation):
            # Attempt to rollback beta to alpha's release
            self.service.rollback_cortex_release(CortexReleaseRollbackRequest(
                workspace_id="beta",
                target_release_id=rel_alpha["release_id"],
            ))

    def test_external_index_promotion_failure_compensation(self) -> None:
        """If external index alias promotion fails, release is failed and active pointer is not advanced."""
        self._ingest("alpha", "index failure test")
        active_before = self.store.get_active_cortex_release("alpha")
        if active_before is None:
            r0 = self.service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha", policy_revision="v0"))
            self.service.validate_cortex_release(r0["release_id"], CortexReleaseValidateRequest(validation_receipt=CortexValidationReceipt(passed=True)))
            active_before = self.service.activate_cortex_release(r0["release_id"])

        cand = self.service.create_cortex_release(CortexReleaseCreateRequest(workspace_id="alpha"))
        cand_id = cand["release_id"]
        self.service.validate_cortex_release(cand_id, CortexReleaseValidateRequest(
            validation_receipt=CortexValidationReceipt(passed=True)
        ))

        # Mock external index failure
        mock_lexical = MagicMock()
        mock_lexical.promote_alias.side_effect = RuntimeError("OpenSearch connection timeout during alias swap")
        self.service.retrieval_engine.lexical_index = mock_lexical

        with self.assertRaises(InvariantViolation) as ctx:
            self.service.activate_cortex_release(cand_id)
        self.assertIn("external index alias promotion failed", str(ctx.exception))

        # Candidate status is marked failed with error details
        failed_rel = self.store.get_cortex_release(cand_id)
        self.assertEqual(failed_rel["status"], "failed")
        self.assertIn("OpenSearch connection timeout", failed_rel["failure_detail"])

        # Active release is unchanged
        active_after = self.store.get_active_cortex_release("alpha")
        self.assertEqual(active_after["release_id"], active_before["release_id"])
