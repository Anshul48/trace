from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trace.v2.model_gateway import (
    DEFAULT_MODEL_REGISTRY,
    ModelGatewayError,
    ModelGatewayPolicy,
    ModelPolicy,
    ModelPolicyDenied,
    ModelUnavailableError,
    RegisteredModel,
    TraceModelGateway,
    _default_deepseek_flash_provider,
    _default_deepseek_pro_provider,
)
from trace.v2.models import (
    HierarchyBuildRequest,
    IngestionRequest,
    QueryRequest,
    RetrievalBudget,
    SchemaProposalRequest,
)
from trace.v2.service import TraceService
from trace.v2.store import SqliteEventStore


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


class TraceLLMGatewayTests(unittest.TestCase):
    def test_default_registry_includes_deepinfra_and_deepseek(self) -> None:
        registered_ids = {m.model_id for m in DEFAULT_MODEL_REGISTRY}
        self.assertIn("deepseek-v4-flash", registered_ids)
        self.assertIn("deepseek-v4-pro", registered_ids)
        self.assertIn("deepinfra/deepseek-ai/DeepSeek-V4-Flash", registered_ids)
        self.assertIn("deepinfra/deepseek-ai/DeepSeek-V4-Pro", registered_ids)

    def test_default_provider_checks_deepinfra_env(self) -> None:
        with patch.dict(os.environ, {"DEEPINFRA_API_KEY": "test-key-123"}, clear=False):
            flash = _default_deepseek_flash_provider()
            self.assertEqual(flash, "deepinfra/deepseek-ai/DeepSeek-V4-Flash")
            pro = _default_deepseek_pro_provider()
            self.assertEqual(pro, "deepinfra/deepseek-ai/DeepSeek-V4-Pro")

    def test_dynamic_provider_matching_when_cloud_allowed(self) -> None:
        gateway = TraceModelGateway(
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
            completion=lambda **kwargs: {"choices": [{"message": {"content": json.dumps({"rendering": "ok"})}}]},
        )
        model = gateway._registered("deepinfra/deepseek-ai/DeepSeek-V4-Flash-0731", purpose="synthesis")
        self.assertEqual(model.provider_model, "deepinfra/deepseek-ai/DeepSeek-V4-Flash-0731")
        self.assertEqual(model.tier, "flash")

    def test_dynamic_provider_denied_when_cloud_disabled(self) -> None:
        gateway = TraceModelGateway(
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=False)),
        )
        with self.assertRaises(ModelPolicyDenied):
            gateway._registered("deepinfra/custom-model", purpose="synthesis")

    def test_model_gateway_passes_api_key_and_options(self) -> None:
        captured_kwargs: dict = {}

        def mock_completion(**kwargs: object) -> object:
            nonlocal captured_kwargs
            captured_kwargs = dict(kwargs)
            return {
                "choices": [{"message": {"content": json.dumps({"rendering": "Answer based on Trace facts."})}}],
                "usage": {"prompt_tokens": 15, "completion_tokens": 8},
            }

        gateway = TraceModelGateway(
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
            completion=mock_completion,
        )
        context = SimpleNamespace(workspace_id="test_ws", model_permissions=frozenset({"*"}), subject="user1")
        response, audit = gateway.call_json(
            context=context,
            model_id="deepinfra/deepseek-ai/DeepSeek-V4-Flash",
            purpose="synthesis",
            query="Summarize performance metrics",
            candidates=[{"atom_version_id": "atom_1", "content": "Latency is 2ms."}],
            response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
            max_nodes=5,
            token_budget=1000,
            prompt_template_revision="v1",
        )
        self.assertEqual(response["rendering"], "Answer based on Trace facts.")
        self.assertEqual(audit["status"], "succeeded")
        self.assertEqual(captured_kwargs["model"], "deepinfra/deepseek-ai/DeepSeek-V4-Flash")

    def test_service_synthesize_with_model(self) -> None:
        store = SqliteEventStore(":memory:")
        service = TraceService(store, MemoryObjectStore())

        def mock_completion(**kwargs: object) -> object:
            return {
                "choices": [{"message": {"content": json.dumps({"rendering": "Revenue grew by 20% in Q3."})}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            }

        service.model_gateway = TraceModelGateway(
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
            completion=mock_completion,
        )

        try:
            service.ingest(IngestionRequest(workspace_id="finance", text="Q3 financial report: Revenue grew by 20% year over year."))
            query_res = service.query(QueryRequest(workspace_id="finance", query="Revenue growth"))
            bundle_id = query_res["evidence_bundle_id"]

            synth_res = service.synthesize(
                evidence_bundle_id=bundle_id,
                prompt="Summarize revenue growth",
                format="prose",
                privacy_context={},
                model_id="deepseek-v4-flash",
            )
            self.assertEqual(synth_res["rendering"], "Revenue grew by 20% in Q3.")
            self.assertIsNotNone(synth_res["model_audit"])
            self.assertEqual(synth_res["model_audit"]["status"], "succeeded")
            self.assertTrue(len(synth_res["citations"]) > 0)
        finally:
            store.close()

    def test_service_propose_schemas_with_model(self) -> None:
        store = SqliteEventStore(":memory:")
        service = TraceService(store, MemoryObjectStore())

        def mock_completion(**kwargs: object) -> object:
            return {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "schemas": [
                                {
                                    "label": "FinancialMetric",
                                    "definition": "A quantitative measurement of fiscal health.",
                                    "positive_examples": ["Operating margins improved"],
                                    "exclusions": ["User login"],
                                    "confidence": 0.95,
                                    "evidence_atom_version_ids": [atom_id],
                                }
                            ]
                        })
                    }
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 25},
            }

        service.model_gateway = TraceModelGateway(
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
            completion=mock_completion,
        )

        try:
            ingest_res = service.ingest(IngestionRequest(workspace_id="schemas_ws", text="Operating margins improved by 5 basis points."))
            atom_id = store.ingestion_atoms(ingest_res["ingestion_id"])[0]["atom_version_id"]
            proposals = service.propose_schemas(SchemaProposalRequest(
                workspace_id="schemas_ws",
                model_id="deepseek-v4-flash",
                max_schemas=3,
            ))
            self.assertTrue(len(proposals["proposals"]) > 0)
            self.assertEqual(proposals["proposals"][0]["candidate"]["label"], "FinancialMetric")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
