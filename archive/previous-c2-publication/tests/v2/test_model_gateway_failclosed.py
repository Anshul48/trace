"""Fail-closed hardening tests for TraceModelGateway (WP-CAP-GW01)."""

from __future__ import annotations

import json
import logging
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from trace.v2.model_gateway import (
    ModelCallAudit,
    ModelEmptyResponseError,
    ModelGatewayError,
    ModelGatewayPolicy,
    ModelMalformedJsonError,
    ModelPolicy,
    ModelPolicyDenied,
    ModelUnavailableError,
    ModelUncitedOutputError,
    RegisteredModel,
    TraceModelGateway,
)


class MockAuditStore:
    """In-memory audit store capturing persisted audit records."""

    def __init__(self) -> None:
        self.audits: list[dict[str, Any]] = []

    def record_model_audit(self, audit: dict[str, Any]) -> dict[str, Any]:
        self.audits.append(dict(audit))
        return audit


def _make_context(workspace_id: str = "ws-test", actor: str = "tester") -> SimpleNamespace:
    return SimpleNamespace(
        workspace_id=workspace_id,
        subject=actor,
        request_id="req-123",
        model_permissions=frozenset({"*", "model:pro"}),
    )


def _make_gateway(completion_fn: Any, store: Any = None) -> TraceModelGateway:
    return TraceModelGateway(
        store=store,
        policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
        completion=completion_fn,
        max_transient_retries=0,
    )


class TestModelGatewayFailClosedHierarchy(unittest.TestCase):
    """Validate exception taxonomy relationships."""

    def test_exception_inheritance(self) -> None:
        self.assertTrue(issubclass(ModelGatewayError, RuntimeError))
        self.assertTrue(issubclass(ModelUnavailableError, ModelGatewayError))
        self.assertTrue(issubclass(ModelPolicyDenied, ModelGatewayError))
        self.assertTrue(issubclass(ModelEmptyResponseError, ModelGatewayError))
        self.assertTrue(issubclass(ModelMalformedJsonError, ModelGatewayError))
        self.assertTrue(issubclass(ModelUncitedOutputError, ModelGatewayError))


class TestModelGatewayEmptyResponseFailClosed(unittest.TestCase):
    """Validate fail-closed behavior when model returns empty or whitespace response."""

    def setUp(self) -> None:
        self.store = MockAuditStore()
        self.context = _make_context()
        self.candidates = [{"atom_version_id": "atom-1", "content": "Evidence text."}]

    def test_empty_string_raises_model_empty_response_error(self) -> None:
        gateway = _make_gateway(
            lambda **_: {"choices": [{"message": {"content": ""}}]},
            store=self.store,
        )
        with self.assertRaises(ModelEmptyResponseError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize this",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "empty_response")
        self.assertGreaterEqual(audit["wall_clock_duration"], 0.0)
        self.assertGreaterEqual(audit["duration_ms"], 0.0)

    def test_whitespace_only_raises_model_empty_response_error(self) -> None:
        gateway = _make_gateway(
            lambda **_: {"choices": [{"message": {"content": "   \n\t   \r\n  "}}]},
            store=self.store,
        )
        with self.assertRaises(ModelEmptyResponseError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize this",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "empty_response")

    def test_none_content_raises_model_empty_response_error(self) -> None:
        gateway = _make_gateway(
            lambda **_: {"choices": [{"message": {"content": None}}]},
            store=self.store,
        )
        with self.assertRaises(ModelEmptyResponseError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize this",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "empty_response")


class TestModelGatewayMalformedJsonFailClosed(unittest.TestCase):
    """Validate fail-closed behavior when model returns malformed JSON or invalid schema."""

    def setUp(self) -> None:
        self.store = MockAuditStore()
        self.context = _make_context()
        self.candidates = [{"atom_version_id": "atom-1", "content": "Evidence text."}]

    def test_plain_text_non_json_raises_model_malformed_json_error(self) -> None:
        gateway = _make_gateway(
            lambda **_: {"choices": [{"message": {"content": "This is raw unstructured prose, not JSON."}}]},
            store=self.store,
        )
        with self.assertRaises(ModelMalformedJsonError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize this",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "malformed_json")
        self.assertGreaterEqual(audit["wall_clock_duration"], 0.0)

    def test_truncated_json_raises_model_malformed_json_error(self) -> None:
        gateway = _make_gateway(
            lambda **_: {"choices": [{"message": {"content": '{"rendering": "unterminated string...'}}]},
            store=self.store,
        )
        with self.assertRaises(ModelMalformedJsonError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize this",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "malformed_json")

    def test_missing_required_schema_key_raises_model_malformed_json_error(self) -> None:
        gateway = _make_gateway(
            lambda **_: {"choices": [{"message": {"content": json.dumps({"unexpected_key": "some value"})}}]},
            store=self.store,
        )
        with self.assertRaises(ModelMalformedJsonError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize this",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "malformed_json")

    def test_schema_type_mismatch_raises_model_malformed_json_error(self) -> None:
        gateway = _make_gateway(
            lambda **_: {"choices": [{"message": {"content": json.dumps({"rendering": 12345})}}]},
            store=self.store,
        )
        with self.assertRaises(ModelMalformedJsonError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize this",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "malformed_json")

    def test_malformed_response_envelope_raises_model_malformed_json_error(self) -> None:
        gateway = _make_gateway(
            lambda **_: {"choices": []},
            store=self.store,
        )
        with self.assertRaises(ModelMalformedJsonError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize this",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "malformed_json")


class TestModelGatewayUncitedOutputFailClosed(unittest.TestCase):
    """Validate fail-closed behavior when extractive or synthesizing output lacks evidence anchors."""

    def setUp(self) -> None:
        self.store = MockAuditStore()
        self.context = _make_context()
        self.candidates = [
            {"atom_version_id": "atom-auth-1", "content": "Authentication token format."},
            {"atom_version_id": "atom-auth-2", "content": "Refresh token mechanism."},
        ]

    def test_schema_proposal_missing_evidence_anchors_raises_uncited_output(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "schemas": [
                                {
                                    "label": "TokenAuth",
                                    "definition": "Authentication via bearer tokens.",
                                    # Missing evidence_atom_version_ids
                                }
                            ]
                        })
                    }
                }]
            },
            store=self.store,
        )
        with self.assertRaises(ModelUncitedOutputError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="schema_proposal",
                query="Propose schemas",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["schemas"], "properties": {"schemas": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "uncited_output")
        self.assertGreaterEqual(audit["wall_clock_duration"], 0.0)

    def test_schema_proposal_empty_evidence_anchors_raises_uncited_output(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "schemas": [
                                {
                                    "label": "TokenAuth",
                                    "definition": "Authentication via bearer tokens.",
                                    "evidence_atom_version_ids": [],
                                }
                            ]
                        })
                    }
                }]
            },
            store=self.store,
        )
        with self.assertRaises(ModelUncitedOutputError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="schema_proposal",
                query="Propose schemas",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["schemas"], "properties": {"schemas": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "uncited_output")

    def test_schema_proposal_ungrounded_evidence_anchor_raises_uncited_output(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "schemas": [
                                {
                                    "label": "TokenAuth",
                                    "definition": "Authentication via bearer tokens.",
                                    "evidence_atom_version_ids": ["hallucinated-atom-id"],
                                }
                            ]
                        })
                    }
                }]
            },
            store=self.store,
        )
        with self.assertRaises(ModelUncitedOutputError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="schema_proposal",
                query="Propose schemas",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["schemas"], "properties": {"schemas": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "uncited_output")

    def test_synthesis_empty_citations_when_required_raises_uncited_output(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Bearer tokens expire in 1 hour.",
                            "citations": [],
                        })
                    }
                }]
            },
            store=self.store,
        )
        with self.assertRaises(ModelUncitedOutputError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize token expiration",
                candidates=self.candidates,
                response_schema={
                    "type": "object",
                    "required": ["rendering", "citations"],
                    "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}},
                },
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "uncited_output")

    def test_synthesis_ungrounded_citations_raises_uncited_output(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Bearer tokens expire in 1 hour.",
                            "citations": ["atom-unrelated-999"],
                        })
                    }
                }]
            },
            store=self.store,
        )
        with self.assertRaises(ModelUncitedOutputError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize token expiration",
                candidates=self.candidates,
                response_schema={
                    "type": "object",
                    "required": ["rendering", "citations"],
                    "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}},
                },
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "uncited_output")

    def test_require_citations_flag_enforces_anchors(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Bearer tokens expire in 1 hour.",
                        })
                    }
                }]
            },
            store=self.store,
        )
        with self.assertRaises(ModelUncitedOutputError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize token expiration",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
                require_citations=True,
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "uncited_output")

    def test_grounded_citations_succeeds(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Bearer tokens expire in 1 hour.",
                            "citations": ["atom-auth-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
            store=self.store,
        )
        val, audit = gateway.call_json(
            context=self.context,
            model_id="deepseek-v4-flash",
            purpose="synthesis",
            query="Synthesize token expiration",
            candidates=self.candidates,
            response_schema={
                "type": "object",
                "required": ["rendering", "citations"],
                "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}},
            },
            max_nodes=5,
            token_budget=1000,
            prompt_template_revision="v1",
        )
        self.assertEqual(val["rendering"], "Bearer tokens expire in 1 hour.")
        self.assertEqual(val["citations"], ["atom-auth-1"])
        self.assertEqual(audit["status"], "succeeded")
        self.assertEqual(audit["policy_outcome"], "approved")


class TestModelGatewayZeroFallbacks(unittest.TestCase):
    """Verify that NO synthetic fallbacks are ever manufactured on failure."""

    def setUp(self) -> None:
        self.context = _make_context()
        self.candidates = [{"atom_version_id": "atom-cand-1", "content": "Real candidate evidence."}]

    def test_no_synthetic_technical_architecture_schema_on_empty(self) -> None:
        gateway = _make_gateway(lambda **_: {"choices": [{"message": {"content": ""}}]})
        with self.assertRaises(ModelEmptyResponseError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="schema_proposal",
                query="Propose schemas",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["schemas"], "properties": {"schemas": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )

    def test_no_synthetic_technical_architecture_schema_on_malformed(self) -> None:
        gateway = _make_gateway(lambda **_: {"choices": [{"message": {"content": "Not JSON"}}]})
        with self.assertRaises(ModelMalformedJsonError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="schema_proposal",
                query="Propose schemas",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["schemas"], "properties": {"schemas": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )

    def test_no_synthetic_rendering_on_empty(self) -> None:
        gateway = _make_gateway(lambda **_: {"choices": [{"message": {"content": ""}}]})
        with self.assertRaises(ModelEmptyResponseError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )

    def test_no_synthetic_rendering_on_malformed(self) -> None:
        gateway = _make_gateway(lambda **_: {"choices": [{"message": {"content": "Malformed {json"}}]})
        with self.assertRaises(ModelMalformedJsonError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )

    def test_no_synthetic_selected_ids_on_empty(self) -> None:
        gateway = _make_gateway(lambda **_: {"choices": [{"message": {"content": ""}}]})
        with self.assertRaises(ModelEmptyResponseError):
            gateway.select_navigation(
                context=self.context,
                model_id="deepseek-v4-flash",
                query="Navigate",
                candidates=self.candidates,
                max_nodes=5,
                token_budget=1000,
            )

    def test_no_synthetic_selected_ids_on_malformed(self) -> None:
        gateway = _make_gateway(lambda **_: {"choices": [{"message": {"content": "Random text"}}]})
        with self.assertRaises(ModelMalformedJsonError):
            gateway.select_navigation(
                context=self.context,
                model_id="deepseek-v4-flash",
                query="Navigate",
                candidates=self.candidates,
                max_nodes=5,
                token_budget=1000,
            )


class TestModelGatewayLoggingAndAuditing(unittest.TestCase):
    """Validate failure logging and audit persistence."""

    def setUp(self) -> None:
        self.store = MockAuditStore()
        self.context = _make_context()
        self.candidates = [{"atom_version_id": "atom-1", "content": "Text"}]

    def test_failure_logging_emitted_on_error(self) -> None:
        gateway = _make_gateway(
            lambda **_: {"choices": [{"message": {"content": ""}}]},
            store=self.store,
        )
        with self.assertLogs("trace.v2.model_gateway", level="WARNING") as log_context:
            with self.assertRaises(ModelEmptyResponseError):
                gateway.call_json(
                    context=self.context,
                    model_id="deepseek-v4-flash",
                    purpose="synthesis",
                    query="Synthesize",
                    candidates=self.candidates,
                    response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                    max_nodes=5,
                    token_budget=1000,
                    prompt_template_revision="v1",
                )
            self.assertTrue(any("empty_response" in record.getMessage() for record in log_context.records))
            self.assertTrue(any("failed" in record.getMessage() for record in log_context.records))

    def test_provider_failure_audit_records_exact_metadata(self) -> None:
        def failing_completion(**_: Any) -> Any:
            raise RuntimeError("upstream provider 500 internal server error")

        gateway = _make_gateway(failing_completion, store=self.store)
        with self.assertRaises(ModelUnavailableError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Synthesize",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "provider_failed")
        self.assertGreaterEqual(audit["wall_clock_duration"], 0.0)


if __name__ == "__main__":
    unittest.main()
