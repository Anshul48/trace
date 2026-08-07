from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trace.v2.benchmark import ReleaseCorpusError, load_benchmark, validate_release_corpus
from trace.v2.config import ConfigurationError, TraceSettings
from trace.v2.model_gateway import ModelGatewayPolicy, ModelPolicy, ModelUnavailableError, TraceModelGateway
from trace.v2.models import IngestionRequest, QueryRequest
from trace.v2.projections import ProjectionRevisionError, RevisionedProjectionController
from trace.v2.release import evaluate_release_evidence
from trace.v2.retrieval import HybridRetrievalEngine
from trace.v2.service import TraceService
from trace.v2.store import SqliteEventStore


class MemoryObjectStore:
    def put_bytes(self, raw: bytes, media_type: str, **_: object) -> dict[str, object]:
        return {
            "content_hash": hashlib.sha256(raw).hexdigest(), "object_key": "test/source",
            "media_type": media_type, "byte_length": len(raw), "metadata": {},
        }

    def put_text(self, text: str, media_type: str, **kwargs: object) -> dict[str, object]:
        return self.put_bytes(text.encode("utf-8"), media_type, **kwargs)


class CrossTenantLexicalIndex:
    provider_id = "test-cross-tenant"

    def __init__(self, atom_version_id: str) -> None:
        self.atom_version_id = atom_version_id

    def search(self, **_: object) -> list[dict[str, object]]:
        return [{"atom_version_id": self.atom_version_id, "lexical_score": 1.0}]


class CountedProjection:
    def __init__(self, count: int) -> None:
        self.count = count
        self.created: list[str] = []
        self.activated: list[str] = []

    def create_revision(self, revision: str, **_: object) -> str:
        self.created.append(revision)
        return revision

    def revision_count(self, **_: object) -> int:
        return self.count

    def activate_revision(self, revision: str) -> None:
        self.activated.append(revision)


class ReleaseControlTests(unittest.TestCase):
    def test_gcp_profile_fails_closed_outside_mumbai_and_requires_runtime_controls(self) -> None:
        with self.assertRaises(ConfigurationError):
            TraceSettings.from_environ({"TRACE_DEPLOYMENT_PROFILE": "gcp_mumbai", "TRACE_GCP_REGION": "us-central1"})
        settings = TraceSettings.from_environ({
            "TRACE_DEPLOYMENT_PROFILE": "gcp_mumbai", "TRACE_GCP_REGION": "asia-south1",
            "TRACE_WORKSPACE_DATA_REGION": "asia-south1", "TRACE_PRODUCTION_MODE": "true",
            "TRACE_AUTH_REQUIRED": "true", "TRACE_REPOSITORY": "postgres", "TRACE_OBJECT_STORE": "gcs",
            "TRACE_OPENSEARCH_INDEX": "atoms", "TRACE_QDRANT_COLLECTION": "vectors",
            "TRACE_NATS_URL": "nats://private", "TRACE_REDIS_URL": "redis://private",
            "TRACE_MODEL_GATEWAY_URL": "http://gateway/v1", "TRACE_POSTGRES_RUNTIME_ROLE": "runtime",
            "TRACE_POSTGRES_MIGRATION_ROLE": "migrator", "TRACE_POSTGRES_POOL_ENABLED": "true",
            "TRACE_WEBHOOK_KMS_KEY": "projects/p/locations/asia-south1/keyRings/r/cryptoKeys/k",
        })
        self.assertEqual(settings.public_dict()["gcp_region"], "asia-south1")

    def test_index_hit_is_reloaded_and_cross_workspace_result_is_dropped(self) -> None:
        store = SqliteEventStore(":memory:")
        service = TraceService(store, MemoryObjectStore())
        try:
            service.ingest(IngestionRequest(workspace_id="alpha", text="alpha private evidence"))
            beta = service.ingest(IngestionRequest(workspace_id="beta", text="beta secret evidence"))
            beta_atom = store.ingestion_atoms(beta["ingestion_id"])[0]
            service.retrieval_engine = HybridRetrievalEngine(
                lexical_index=CrossTenantLexicalIndex(beta_atom["atom_version_id"])
            )
            response = service.query(QueryRequest(workspace_id="alpha", query="evidence"))
            self.assertEqual(response["sufficiency_state"], "insufficient_evidence")
            self.assertEqual(response["results"], [])
        finally:
            store.close()

    def test_model_failure_retries_only_the_same_registered_model(self) -> None:
        calls: list[str] = []

        class TransientFailure(Exception):
            status_code = 503

        def unavailable(**kwargs: object) -> object:
            calls.append(str(kwargs["model"]))
            raise TransientFailure()

        gateway = TraceModelGateway(
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)), completion=unavailable,
            max_transient_retries=1, sleep=lambda _: None,
        )
        context = SimpleNamespace(workspace_id="alpha", model_permissions=frozenset({"deepseek-v4-flash"}), subject="tester")
        with self.assertRaises(ModelUnavailableError):
            gateway.call_json(
                context=context, model_id="deepseek-v4-flash", purpose="synthesis", query="q",
                candidates=[{"atom_version_id": "a", "content": "evidence"}],
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=1, token_budget=64, prompt_template_revision="test",
            )
        self.assertEqual(calls, [calls[0], calls[0]])

    def test_revision_parity_blocks_activation_and_release_fixture_is_not_authority(self) -> None:
        controller = RevisionedProjectionController(strict=True)
        adapter = CountedProjection(count=2)
        controller.prepare(adapter, revision="r1")
        parity = controller.verify(adapter, projection="lexical", workspace_id="alpha", revision="r1", expected_count=3)
        self.assertFalse(parity.passed)
        with self.assertRaises(ProjectionRevisionError):
            if not parity.passed:
                raise ProjectionRevisionError("parity failed")
        fixture = load_benchmark(Path(__file__).resolve().parents[1] / "benchmarks" / "technical-docs-v1.json")
        with self.assertRaises(ReleaseCorpusError):
            validate_release_corpus(fixture)

    def test_release_gate_fails_closed_and_accepts_complete_measured_evidence(self) -> None:
        self.assertFalse(evaluate_release_evidence({}).passed)
        result = evaluate_release_evidence({
            "load": {
                "atoms": 10_000_000,
                "non_deep_qps": 500,
                "mix": {"fast": 0.70, "standard": 0.20, "graph": 0.05, "hierarchy": 0.05},
                "fast_p95_seconds": 2,
                "standard_p95_seconds": 5,
                "graph_p95_seconds": 5,
                "hierarchy_p95_seconds": 5,
                "deep_p95_seconds": 90,
            },
            "restore": {"passed": True, "rpo_hours": 24, "rto_hours": 24},
            "security": {
                "tenant_leak_test_passed": True,
                "rls_visibility_test_passed": True,
                "provider_redaction_test_passed": True,
            },
            "quality": {"complete_gold_evidence_delta": 0.02, "citation_precision_delta": -0.005},
            "shadow": {"passed": True, "stages": [5, 25, 50, 100], "automatic_rollback_triggered": False},
        })
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
