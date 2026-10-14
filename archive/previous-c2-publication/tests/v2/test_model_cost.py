"""Comprehensive unit test suite for model pricing, cost calculation, and telemetry receipts.

Governed by:
- WP-CAP-GW02 (Model Registry & Cost Telemetry)
- Program Invariants (docs/program/01_INVARIANTS.md)
- Clause CAP-D010 & CAP-D011 (Fail closed on missing models, zero/unknown costs reported as free)
"""

from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from typing import Any

from trace.v2.model_gateway import (
    DEFAULT_MODEL_REGISTRY,
    MODEL_PRICING_TABLE,
    ModelCallAudit,
    ModelGatewayError,
    ModelGatewayPolicy,
    ModelInvocationReceipt,
    ModelMissingUsageError,
    ModelPolicy,
    ModelPolicyDenied,
    ModelPricing,
    RegisteredModel,
    TraceModelGateway,
    UnregisteredModelPricingError,
    _deterministic_token_count,
    _extract_usage,
    _lookup_pricing,
    get_model_pricing,
)


class MockAuditStore:
    """In-memory audit store capturing persisted audit records."""

    def __init__(self) -> None:
        self.audits: list[dict[str, Any]] = []

    def record_model_audit(self, audit: dict[str, Any]) -> dict[str, Any]:
        self.audits.append(dict(audit))
        return audit


def _make_context(workspace_id: str = "ws-cost-test", actor: str = "cost-tester") -> SimpleNamespace:
    return SimpleNamespace(
        workspace_id=workspace_id,
        subject=actor,
        request_id="req-cost-001",
        model_permissions=frozenset({"*", "model:pro"}),
    )


def _make_gateway(
    completion_fn: Any,
    store: Any = None,
    enforce_tokenizer_fallback: bool = False,
) -> TraceModelGateway:
    return TraceModelGateway(
        store=store,
        policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
        completion=completion_fn,
        max_transient_retries=0,
        enforce_tokenizer_fallback=enforce_tokenizer_fallback,
    )


class TestModelPricingRegistry(unittest.TestCase):
    """Verify registration, coefficients, and invariants across the model registry."""

    def test_default_registry_has_no_zero_cost_cloud_placeholders(self) -> None:
        """Every cloud model in DEFAULT_MODEL_REGISTRY must have strictly positive pricing."""
        for model in DEFAULT_MODEL_REGISTRY:
            if not model.is_local:
                self.assertGreater(
                    model.input_cost_per_million_usd,
                    0.0,
                    f"Cloud model {model.model_id} has zero/negative input cost",
                )
                self.assertGreater(
                    model.output_cost_per_million_usd,
                    0.0,
                    f"Cloud model {model.model_id} has zero/negative output cost",
                )

    def test_default_registry_local_models_strictly_zero_cost(self) -> None:
        """Every local model in DEFAULT_MODEL_REGISTRY must have is_local=True and exactly $0.00 cost."""
        local_models = [m for m in DEFAULT_MODEL_REGISTRY if m.is_local]
        self.assertGreaterEqual(len(local_models), 5, "At least 5 local models must be registered")
        for model in local_models:
            self.assertTrue(model.is_local)
            self.assertEqual(
                model.input_cost_per_million_usd,
                0.0,
                f"Local model {model.model_id} has non-zero input cost",
            )
            self.assertEqual(
                model.output_cost_per_million_usd,
                0.0,
                f"Local model {model.model_id} has non-zero output cost",
            )

    def test_pinned_deepseek_flash_coefficients(self) -> None:
        """Verify DeepSeek Flash pricing matches DAG pinned spec: $0.27/M in, $1.10/M out."""
        flash = get_model_pricing("deepseek-v4-flash")
        self.assertFalse(flash.is_local)
        self.assertAlmostEqual(flash.input_cost_per_million_usd, 0.27, places=4)
        self.assertAlmostEqual(flash.output_cost_per_million_usd, 1.10, places=4)
        self.assertAlmostEqual(flash.input_cost_per_m, 0.27, places=4)
        self.assertAlmostEqual(flash.output_cost_per_m, 1.10, places=4)

        # deepseek-chat alias
        chat = get_model_pricing("deepseek-chat")
        self.assertFalse(chat.is_local)
        self.assertAlmostEqual(chat.input_cost_per_m, 0.27, places=4)
        self.assertAlmostEqual(chat.output_cost_per_m, 1.10, places=4)

    def test_pinned_deepseek_pro_coefficients(self) -> None:
        """Verify DeepSeek Pro pricing matches spec: $0.55/M in, $2.19/M out."""
        pro = get_model_pricing("deepseek-v4-pro")
        self.assertFalse(pro.is_local)
        self.assertAlmostEqual(pro.input_cost_per_million_usd, 0.55, places=4)
        self.assertAlmostEqual(pro.output_cost_per_million_usd, 2.19, places=4)

    def test_pinned_openai_gpt4o_coefficients(self) -> None:
        """Verify GPT-4o pricing: $2.50/M in, $10.00/M out; GPT-4o-mini: $0.15/M in, $0.60/M out."""
        gpt4o = get_model_pricing("gpt-4o")
        self.assertFalse(gpt4o.is_local)
        self.assertAlmostEqual(gpt4o.input_cost_per_m, 2.50, places=4)
        self.assertAlmostEqual(gpt4o.output_cost_per_m, 10.00, places=4)

        mini = get_model_pricing("gpt-4o-mini")
        self.assertFalse(mini.is_local)
        self.assertAlmostEqual(mini.input_cost_per_m, 0.15, places=4)
        self.assertAlmostEqual(mini.output_cost_per_m, 0.60, places=4)

    def test_pinned_claude_coefficients(self) -> None:
        """Verify Claude 3.5 Sonnet ($3.00/$15.00) and Haiku ($0.80/$4.00)."""
        sonnet = get_model_pricing("claude-3-5-sonnet")
        self.assertFalse(sonnet.is_local)
        self.assertAlmostEqual(sonnet.input_cost_per_m, 3.00, places=4)
        self.assertAlmostEqual(sonnet.output_cost_per_m, 15.00, places=4)

        haiku = get_model_pricing("claude-3-5-haiku")
        self.assertFalse(haiku.is_local)
        self.assertAlmostEqual(haiku.input_cost_per_m, 0.80, places=4)
        self.assertAlmostEqual(haiku.output_cost_per_m, 4.00, places=4)

    def test_pinned_local_slm_and_embedding_models(self) -> None:
        """Verify local models record $0.00 / 1M tokens and is_local=True."""
        local_ids = (
            "all-MiniLM-L6-v2",
            "sentence-transformers/all-MiniLM-L6-v2",
            "qwen2.5-1.5b-local",
            "qwen2.5-3b-local",
            "qwen2.5-3b",
            "qwen2.5-7b-local",
            "qwen2.5-7b",
            "qwen2.5-14b-local",
            "llama-3.2-1b-local",
            "llama-3.2-3b-local",
        )
        for model_id in local_ids:
            pricing = get_model_pricing(model_id)
            self.assertTrue(pricing.is_local, f"Model {model_id} is not marked is_local=True")
            self.assertEqual(pricing.input_cost_per_m, 0.0, f"Model {model_id} has non-zero input cost")
            self.assertEqual(pricing.output_cost_per_m, 0.0, f"Model {model_id} has non-zero output cost")
            self.assertEqual(pricing.calculate_cost(500_000, 200_000), 0.0)

    def test_unregistered_model_raises_unregistered_model_pricing_error(self) -> None:
        """DAG Clause CAP-GW02 fallback requirement: Unregistered model ID raises UnregisteredModelPricingError."""
        with self.assertRaises(UnregisteredModelPricingError) as ctx:
            get_model_pricing("completely-unknown-model-xyz")
        self.assertIn("completely-unknown-model-xyz", str(ctx.exception))

    def test_registered_model_cloud_zero_pricing_rejected_at_instantiation(self) -> None:
        """RegisteredModel rejects cloud models initialized with zero costs."""
        with self.assertRaises(ValueError) as ctx:
            RegisteredModel(
                model_id="fraudulent-free-cloud-model",
                provider_model="openai/free-gpt",
                purposes=frozenset({"synthesis"}),
                is_local=False,
                input_cost_per_million_usd=0.0,
                output_cost_per_million_usd=0.0,
            )
        self.assertIn("cannot have zero pricing without is_local=True", str(ctx.exception))

    def test_registered_model_asymmetric_zero_pricing_rejected(self) -> None:
        """RegisteredModel rejects cloud models where only input or only output pricing is zero."""
        with self.assertRaises(ValueError):
            RegisteredModel(
                model_id="zero-input-cloud",
                provider_model="openai/test",
                purposes=frozenset({"synthesis"}),
                is_local=False,
                input_cost_per_million_usd=0.0,
                output_cost_per_million_usd=1.0,
            )
        with self.assertRaises(ValueError):
            RegisteredModel(
                model_id="zero-output-cloud",
                provider_model="openai/test",
                purposes=frozenset({"synthesis"}),
                is_local=False,
                input_cost_per_million_usd=1.0,
                output_cost_per_million_usd=0.0,
            )

    def test_registered_model_negative_pricing_rejected(self) -> None:
        """RegisteredModel rejects negative input or output pricing."""
        with self.assertRaises(ValueError):
            RegisteredModel(
                model_id="negative-input-cloud",
                provider_model="openai/test",
                purposes=frozenset({"synthesis"}),
                is_local=False,
                input_cost_per_million_usd=-0.27,
                output_cost_per_million_usd=1.10,
            )

    def test_registered_model_local_model_non_zero_pricing_rejected(self) -> None:
        """RegisteredModel rejects local models configured with non-zero pricing."""
        with self.assertRaises(ValueError) as ctx:
            RegisteredModel(
                model_id="costly-local-model",
                provider_model="local/test",
                purposes=frozenset({"synthesis"}),
                is_local=True,
                input_cost_per_million_usd=0.50,
                output_cost_per_million_usd=0.0,
            )
        self.assertIn("cannot have non-zero pricing", str(ctx.exception))

    def test_model_pricing_dataclass_validation_rules(self) -> None:
        """ModelPricing dataclass enforces identical positive cloud and zero local invariants."""
        with self.assertRaises(ValueError):
            ModelPricing("leak-cloud-1", 0.0, 1.0, is_local=False)
        with self.assertRaises(ValueError):
            ModelPricing("leak-cloud-2", 1.0, 0.0, is_local=False)
        with self.assertRaises(ValueError):
            ModelPricing("leak-cloud-3", -1.0, 2.0, is_local=False)
        with self.assertRaises(ValueError):
            ModelPricing("leak-local-1", 0.1, 0.0, is_local=True)
        with self.assertRaises(ValueError):
            ModelPricing("leak-local-2", 0.0, 0.1, is_local=True)

    def test_get_model_pricing_resolves_openrouter_and_provider_prefixes(self) -> None:
        """get_model_pricing resolves models specified with provider prefixes."""
        gpt4o = get_model_pricing("openrouter/openai/gpt-4o")
        self.assertFalse(gpt4o.is_local)
        self.assertAlmostEqual(gpt4o.input_cost_per_m, 2.50, places=4)
        self.assertAlmostEqual(gpt4o.output_cost_per_m, 10.00, places=4)

        sonnet = get_model_pricing("openrouter/anthropic/claude-3-5-sonnet")
        self.assertFalse(sonnet.is_local)
        self.assertAlmostEqual(sonnet.input_cost_per_m, 3.00, places=4)
        self.assertAlmostEqual(sonnet.output_cost_per_m, 15.00, places=4)

        deepseek = get_model_pricing("deepseek/deepseek-chat")
        self.assertFalse(deepseek.is_local)
        self.assertAlmostEqual(deepseek.input_cost_per_m, 0.27, places=4)

    def test_registered_model_public_dict_contains_cost_telemetry_fields(self) -> None:
        model = RegisteredModel(
            model_id="test-cloud-model",
            provider_model="test/model",
            purposes=frozenset({"synthesis"}),
            tier="flash",
            is_local=False,
            input_cost_per_million_usd=0.27,
            output_cost_per_million_usd=1.10,
        )
        pub = model.public_dict()
        self.assertEqual(pub["id"], "test-cloud-model")
        self.assertFalse(pub["is_local"])
        self.assertEqual(pub["input_cost_per_million_usd"], 0.27)
        self.assertEqual(pub["output_cost_per_million_usd"], 1.10)


class TestCostCalculationFormulas(unittest.TestCase):
    """Validate deterministic USD cost calculations."""

    def test_deterministic_cloud_cost_calculation(self) -> None:
        """Formula: (input_tokens * cost_per_million_input + output_tokens * cost_per_million_output) / 1,000,000."""
        pricing = ModelPricing(
            model_id="deepseek-v4-flash",
            input_cost_per_million_usd=0.27,
            output_cost_per_million_usd=1.10,
            is_local=False,
        )
        # 1M input, 1M output -> 0.27 + 1.10 = 1.37
        cost_1m = pricing.calculate_cost(1_000_000, 1_000_000)
        self.assertAlmostEqual(cost_1m, 1.37, places=6)

        # 100 input, 50 output -> (100 * 0.27 + 50 * 1.10) / 1,000,000 = (27 + 55) / 1,000,000 = 82 / 1,000,000 = 0.000082
        cost_small = pricing.calculate_cost(100, 50)
        self.assertAlmostEqual(cost_small, 0.000082, places=8)

    def test_strict_zero_dollar_local_cost_calculation(self) -> None:
        """Local models must compute strictly $0.00 regardless of token scale."""
        pricing = ModelPricing(
            model_id="qwen2.5-7b-local",
            input_cost_per_million_usd=0.0,
            output_cost_per_million_usd=0.0,
            is_local=True,
        )
        self.assertEqual(pricing.calculate_cost(10_000_000, 5_000_000), 0.0)
        self.assertEqual(pricing.calculate_cost(1, 1), 0.0)

    def test_calculate_cost_negative_tokens_raises_value_error(self) -> None:
        """calculate_cost must reject negative token counts to prevent cost leaks."""
        pricing = ModelPricing(
            model_id="deepseek-v4-flash",
            input_cost_per_million_usd=0.27,
            output_cost_per_million_usd=1.10,
            is_local=False,
        )
        with self.assertRaises(ValueError):
            pricing.calculate_cost(-10, 50)
        with self.assertRaises(ValueError):
            pricing.calculate_cost(50, -10)

        # Also test on RegisteredModel
        model = RegisteredModel(
            model_id="test-reg-model",
            provider_model="test/provider",
            purposes=frozenset({"synthesis"}),
            input_cost_per_million_usd=0.27,
            output_cost_per_million_usd=1.10,
            is_local=False,
        )
        with self.assertRaises(ValueError):
            model.calculate_cost(-5, 20)
        with self.assertRaises(ValueError):
            model.calculate_cost(20, -5)

    def test_calculate_cost_rejects_boolean_and_non_int_types(self) -> None:
        """calculate_cost must reject boolean or float types instead of silently coercing."""
        pricing = ModelPricing(
            model_id="deepseek-v4-flash",
            input_cost_per_million_usd=0.27,
            output_cost_per_million_usd=1.10,
            is_local=False,
        )
        with self.assertRaises(TypeError):
            pricing.calculate_cost(True, 100)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            pricing.calculate_cost(100, False)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            pricing.calculate_cost(10.5, 50)  # type: ignore[arg-type]

    def test_deterministic_token_count_empty_and_whitespace(self) -> None:
        """Deterministic tokenizer returns 0 for empty and whitespace-only text."""
        self.assertEqual(_deterministic_token_count(""), 0)
        self.assertEqual(_deterministic_token_count("   \n\t  "), 0)
        self.assertEqual(_deterministic_token_count("word"), 1)
        self.assertGreater(_deterministic_token_count("hello world test prompt"), 3)


class TestModelGatewayCostTelemetry(unittest.TestCase):
    """Verify live gateway execution populates telemetry and persists audit records."""

    def setUp(self) -> None:
        self.store = MockAuditStore()
        self.context = _make_context()
        self.candidates = [
            {"atom_version_id": "atom-cost-1", "content": "Evidence node for cost calculation testing."}
        ]

    def test_cloud_invocation_records_non_zero_cost_and_tokens(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Non-zero cost summary verified.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
            },
            store=self.store,
        )

        val, audit = gateway.call_json(
            context=self.context,
            model_id="deepseek-v4-flash",
            purpose="synthesis",
            query="Cost verification query",
            candidates=self.candidates,
            response_schema={
                "type": "object",
                "required": ["rendering", "citations"],
                "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}},
            },
            max_nodes=5,
            token_budget=2000,
            prompt_template_revision="v1",
        )

        self.assertEqual(val["rendering"], "Non-zero cost summary verified.")
        self.assertEqual(audit["status"], "succeeded")
        self.assertFalse(audit["is_local"])
        self.assertEqual(audit["input_tokens"], 1000)
        self.assertEqual(audit["output_tokens"], 500)
        self.assertEqual(audit["cloud_tokens"], 1500)
        self.assertGreater(audit["wall_clock_seconds"], 0.0)
        self.assertGreater(audit["duration_ms"], 0.0)

        # Expected cost: (1000 * 0.27 + 500 * 1.10) / 1_000_000 = (270 + 550) / 1_000_000 = 820 / 1_000_000 = 0.00082
        expected_cost = (1000 * 0.27 + 500 * 1.10) / 1_000_000.0
        self.assertAlmostEqual(audit["usd_cost"], expected_cost, places=8)
        self.assertAlmostEqual(audit["cost_usd"], expected_cost, places=8)

        # Verify persisted store record
        self.assertEqual(len(self.store.audits), 1)
        persisted = self.store.audits[0]
        self.assertEqual(persisted["status"], "succeeded")
        self.assertAlmostEqual(persisted["usd_cost"], expected_cost, places=8)
        self.assertEqual(persisted["input_tokens"], 1000)
        self.assertEqual(persisted["output_tokens"], 500)
        self.assertFalse(persisted["is_local"])
        self.assertIn("receipt", persisted)

    def test_local_model_invocation_records_strictly_zero_cost(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Local model synthesis answer.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 2500, "completion_tokens": 1200},
            },
            store=self.store,
        )

        val, audit = gateway.call_json(
            context=self.context,
            model_id="qwen2.5-3b-local",
            purpose="synthesis",
            query="Local execution query",
            candidates=self.candidates,
            response_schema={
                "type": "object",
                "required": ["rendering", "citations"],
                "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}},
            },
            max_nodes=5,
            token_budget=4000,
            prompt_template_revision="v1",
        )

        self.assertEqual(audit["status"], "succeeded")
        self.assertTrue(audit["is_local"])
        self.assertEqual(audit["input_tokens"], 2500)
        self.assertEqual(audit["output_tokens"], 1200)
        self.assertEqual(audit["cloud_tokens"], 0, "Local model must record 0 cloud tokens")
        self.assertEqual(audit["usd_cost"], 0.0)
        self.assertEqual(audit["cost_usd"], 0.0)

        # Verify persisted store record
        persisted = self.store.audits[0]
        self.assertTrue(persisted["is_local"])
        self.assertEqual(persisted["usd_cost"], 0.0)
        self.assertEqual(persisted["cost_usd"], 0.0)

    def test_call_with_audit_returns_typed_model_invocation_receipt(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Receipt testing answer.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 200, "completion_tokens": 100},
            },
            store=self.store,
        )

        val, receipt = gateway.call_with_audit(
            context=self.context,
            model_id="gpt-4o",
            purpose="synthesis",
            query="Receipt query",
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

        self.assertIsInstance(receipt, ModelInvocationReceipt)
        self.assertEqual(receipt.model_id, "gpt-4o")
        self.assertFalse(receipt.is_local)
        self.assertEqual(receipt.input_tokens, 200)
        self.assertEqual(receipt.output_tokens, 100)
        self.assertEqual(receipt.prompt_tokens, 200)
        self.assertEqual(receipt.completion_tokens, 100)
        self.assertGreater(receipt.wall_clock_seconds, 0.0)
        self.assertGreater(receipt.duration_ms, 0.0)
        self.assertEqual(receipt.wall_time_ms, receipt.duration_ms)

        # Cost for GPT-4o ($2.50 in, $10.00 out): (200 * 2.50 + 100 * 10.00) / 1,000,000 = (500 + 1000) / 1M = 0.0015
        expected_cost = (200 * 2.50 + 100 * 10.00) / 1_000_000.0
        self.assertAlmostEqual(receipt.usd_cost, expected_cost, places=8)
        self.assertAlmostEqual(receipt.cost_usd, expected_cost, places=8)
        self.assertTrue(len(receipt.request_hash) == 64)
        self.assertTrue(len(receipt.response_hash) == 64)

        receipt_dict = receipt.as_dict()
        self.assertEqual(receipt_dict["model_id"], "gpt-4o")
        self.assertEqual(receipt_dict["input_tokens"], 200)
        self.assertAlmostEqual(receipt_dict["usd_cost"], expected_cost, places=8)

    def test_navigation_selection_contains_cost_telemetry(self) -> None:
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({"selected_ids": ["atom-cost-1"]})
                    }
                }],
                "usage": {"prompt_tokens": 150, "completion_tokens": 30},
            },
            store=self.store,
        )

        selected, meta = gateway.select_navigation(
            context=self.context,
            model_id="deepseek-v4-flash",
            query="Navigate query",
            candidates=self.candidates,
            max_nodes=1,
            token_budget=500,
        )
        self.assertEqual(selected, ["atom-cost-1"])
        self.assertIn("usd_cost", meta)
        self.assertIn("cloud_token_cost_usd", meta)
        self.assertIn("input_tokens", meta)
        self.assertIn("output_tokens", meta)
        self.assertEqual(meta["input_tokens"], 150)
        self.assertEqual(meta["output_tokens"], 30)
        self.assertFalse(meta["is_local"])
        expected_cost = (150 * 0.27 + 30 * 1.10) / 1_000_000.0
        self.assertAlmostEqual(meta["usd_cost"], expected_cost, places=8)


class TestFailClosedOnMissingUsageTelemetry(unittest.TestCase):
    """Verify gateway fails closed when provider response omits required usage counters."""

    def setUp(self) -> None:
        self.store = MockAuditStore()
        self.context = _make_context()
        self.candidates = [
            {"atom_version_id": "atom-cost-1", "content": "Evidence node for usage tests."}
        ]

    def test_missing_usage_envelope_raises_model_missing_usage_error(self) -> None:
        """Provider returns valid JSON payload, but entirely omits usage counters."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Synthesized text without token telemetry.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                # usage field completely omitted
            },
            store=self.store,
            enforce_tokenizer_fallback=False,
        )

        with self.assertRaises(ModelMissingUsageError) as ctx:
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Usage test query",
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
        self.assertIn("missing required token usage counters", str(ctx.exception))

        # Verify audit record persisted as failed
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["policy_outcome"], "missing_usage")
        self.assertGreaterEqual(audit["wall_clock_seconds"], 0.0)

    def test_partial_usage_missing_completion_tokens_raises_model_missing_usage_error(self) -> None:
        """Provider returns prompt_tokens but completion_tokens is None."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Partial usage text.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": None},
            },
            store=self.store,
            enforce_tokenizer_fallback=False,
        )

        with self.assertRaises(ModelMissingUsageError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Partial usage test",
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
        self.assertEqual(self.store.audits[0]["status"], "failed")
        self.assertEqual(self.store.audits[0]["policy_outcome"], "missing_usage")

    def test_deterministic_tokenizer_fallback_when_enabled(self) -> None:
        """When enforce_tokenizer_fallback=True, missing provider usage triggers deterministic token counting."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Synthesized text with deterministic tokenizer fallback.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                # usage omitted
            },
            store=self.store,
            enforce_tokenizer_fallback=True,
        )

        val, audit = gateway.call_json(
            context=self.context,
            model_id="deepseek-v4-flash",
            purpose="synthesis",
            query="Fallback tokenizer test",
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

        self.assertEqual(audit["status"], "succeeded")
        self.assertGreater(audit["input_tokens"], 0)
        self.assertGreater(audit["output_tokens"], 0)
        self.assertGreater(audit["usd_cost"], 0.0)

    def test_custom_tokenizer_fallback_callable_in_call_json(self) -> None:
        """Custom tokenizer callable passed directly to call_json is honored when usage is missing."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Custom tokenizer answer.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
            },
            store=self.store,
            enforce_tokenizer_fallback=False,
        )

        custom_counter = lambda text: len(text.split())

        val, audit = gateway.call_json(
            context=self.context,
            model_id="deepseek-v4-flash",
            purpose="synthesis",
            query="Custom tokenizer query",
            candidates=self.candidates,
            response_schema={
                "type": "object",
                "required": ["rendering", "citations"],
                "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}},
            },
            max_nodes=5,
            token_budget=1000,
            prompt_template_revision="v1",
            tokenizer_fallback=custom_counter,
        )

        self.assertEqual(audit["status"], "succeeded")
        self.assertGreater(audit["input_tokens"], 0)
        self.assertGreater(audit["output_tokens"], 0)
        self.assertGreater(audit["usd_cost"], 0.0)

    def test_negative_prompt_tokens_raises_model_missing_usage_error(self) -> None:
        """Provider returns negative prompt_tokens, which must be rejected as missing/invalid usage."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Negative tokens test.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": -10, "completion_tokens": 5},
            },
            store=self.store,
            enforce_tokenizer_fallback=False,
        )
        with self.assertRaises(ModelMissingUsageError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Negative tokens test",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering", "citations"], "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        self.assertEqual(self.store.audits[0]["status"], "failed")
        self.assertEqual(self.store.audits[0]["policy_outcome"], "missing_usage")
        self.assertEqual(self.store.audits[0]["usd_cost"], 0.0)
        self.assertEqual(self.store.audits[0]["cost_usd"], 0.0)

    def test_negative_completion_tokens_raises_model_missing_usage_error(self) -> None:
        """Provider returns negative completion_tokens, which must be rejected."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Negative completion tokens test.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": -5},
            },
            store=self.store,
            enforce_tokenizer_fallback=False,
        )
        with self.assertRaises(ModelMissingUsageError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Negative completion tokens",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering", "citations"], "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )

    def test_string_formatted_non_numeric_tokens_raises_model_missing_usage_error(self) -> None:
        """Provider returns string-formatted non-numeric token counters like 'N/A'."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Non-numeric tokens test.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": "N/A", "completion_tokens": 10},
            },
            store=self.store,
            enforce_tokenizer_fallback=False,
        )
        with self.assertRaises(ModelMissingUsageError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Non numeric tokens",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering", "citations"], "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )

    def test_failed_call_records_zero_cost_in_audit_record(self) -> None:
        """When a call fails at the provider layer, actual spend recorded in audit is strictly $0.00."""
        def failing_completion(**_: Any) -> Any:
            raise RuntimeError("upstream provider network timeout")

        gateway = _make_gateway(failing_completion, store=self.store)
        with self.assertRaises(Exception):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Failure spend check",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        audit = self.store.audits[0]
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["usd_cost"], 0.0)
        self.assertEqual(audit["cost_usd"], 0.0)
        self.assertEqual(audit["input_tokens"], 0)
        self.assertEqual(audit["output_tokens"], 0)
        self.assertIn("receipt", audit)
        receipt_dict = audit["receipt"]
        self.assertEqual(receipt_dict["status"], "failed")
        self.assertEqual(receipt_dict["usd_cost"], 0.0)
        self.assertEqual(receipt_dict["input_tokens"], 0)
        self.assertEqual(receipt_dict["output_tokens"], 0)

    def test_zero_prompt_and_completion_tokens_raises_model_missing_usage_error(self) -> None:
        """Provider returns 0 for both prompt and completion tokens, which must fail closed as invalid usage."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Zero tokens text.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            },
            store=self.store,
            enforce_tokenizer_fallback=False,
        )
        with self.assertRaises(ModelMissingUsageError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Zero tokens test",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering", "citations"], "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertEqual(len(self.store.audits), 1)
        self.assertEqual(self.store.audits[0]["status"], "failed")
        self.assertEqual(self.store.audits[0]["policy_outcome"], "missing_usage")

    def test_zero_prompt_tokens_positive_completion_fails_closed(self) -> None:
        """Provider returns 0 prompt tokens and positive completion tokens, which must fail closed."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Zero prompt text.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 50},
            },
            store=self.store,
            enforce_tokenizer_fallback=False,
        )
        with self.assertRaises(ModelMissingUsageError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Zero prompt tokens test",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering", "citations"], "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )

    def test_positive_prompt_zero_completion_fails_closed(self) -> None:
        """Provider returns positive prompt tokens and 0 completion tokens on non-empty completion."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Zero completion text.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 0},
            },
            store=self.store,
            enforce_tokenizer_fallback=False,
        )
        with self.assertRaises(ModelMissingUsageError):
            gateway.call_json(
                context=self.context,
                model_id="deepseek-v4-flash",
                purpose="synthesis",
                query="Zero completion tokens test",
                candidates=self.candidates,
                response_schema={"type": "object", "required": ["rendering", "citations"], "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )

    def test_zero_tokens_triggers_deterministic_fallback_when_enabled(self) -> None:
        """Provider returns 0 tokens, but enforce_tokenizer_fallback=True recovers deterministic positive token counts."""
        gateway = _make_gateway(
            lambda **_: {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "rendering": "Fallback recovered text.",
                            "citations": ["atom-cost-1"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            },
            store=self.store,
            enforce_tokenizer_fallback=True,
        )
        val, audit = gateway.call_json(
            context=self.context,
            model_id="deepseek-v4-flash",
            purpose="synthesis",
            query="Zero tokens fallback test",
            candidates=self.candidates,
            response_schema={"type": "object", "required": ["rendering", "citations"], "properties": {"rendering": {"type": "string"}, "citations": {"type": "array"}}},
            max_nodes=5,
            token_budget=1000,
            prompt_template_revision="v1",
        )
        self.assertEqual(audit["status"], "succeeded")
        self.assertGreater(audit["input_tokens"], 0)
        self.assertGreater(audit["output_tokens"], 0)
        self.assertGreater(audit["usd_cost"], 0.0)


class TestModelInvocationReceiptInvariants(unittest.TestCase):
    """Verify ModelInvocationReceipt validation, locality invariants, and serialization."""

    def test_receipt_rejects_negative_tokens(self) -> None:
        with self.assertRaises(ValueError):
            ModelInvocationReceipt.create(
                model_id="gpt-4o",
                is_local=False,
                input_tokens=-1,
                output_tokens=10,
                wall_clock_seconds=0.1,
                usd_cost=0.01,
            )
        with self.assertRaises(ValueError):
            ModelInvocationReceipt.create(
                model_id="gpt-4o",
                is_local=False,
                input_tokens=10,
                output_tokens=-1,
                wall_clock_seconds=0.1,
                usd_cost=0.01,
            )

    def test_receipt_rejects_negative_duration(self) -> None:
        with self.assertRaises(ValueError):
            ModelInvocationReceipt.create(
                model_id="gpt-4o",
                is_local=False,
                input_tokens=10,
                output_tokens=10,
                wall_clock_seconds=-0.5,
                usd_cost=0.01,
            )

    def test_receipt_rejects_negative_cost(self) -> None:
        with self.assertRaises(ValueError):
            ModelInvocationReceipt.create(
                model_id="gpt-4o",
                is_local=False,
                input_tokens=10,
                output_tokens=10,
                wall_clock_seconds=0.5,
                usd_cost=-0.01,
            )

    def test_receipt_rejects_local_model_non_zero_cost(self) -> None:
        with self.assertRaises(ValueError):
            ModelInvocationReceipt.create(
                model_id="qwen2.5-7b-local",
                is_local=True,
                input_tokens=100,
                output_tokens=50,
                wall_clock_seconds=0.5,
                usd_cost=0.05,
            )

    def test_receipt_rejects_cloud_model_zero_cost_with_positive_tokens(self) -> None:
        with self.assertRaises(ValueError):
            ModelInvocationReceipt.create(
                model_id="gpt-4o",
                is_local=False,
                input_tokens=100,
                output_tokens=50,
                wall_clock_seconds=0.5,
                usd_cost=0.0,
            )

    def test_receipt_roundtrip_as_dict_and_from_dict(self) -> None:
        receipt = ModelInvocationReceipt.create(
            model_id="gpt-4o",
            is_local=False,
            input_tokens=250,
            output_tokens=120,
            wall_clock_seconds=0.45,
            usd_cost=0.001825,
            request_hash="req-sha256",
            response_hash="resp-sha256",
            status="succeeded",
        )
        d = receipt.as_dict()
        restored = ModelInvocationReceipt.from_dict(d)
        self.assertEqual(restored.invocation_id, receipt.invocation_id)
        self.assertEqual(restored.model_id, receipt.model_id)
        self.assertEqual(restored.is_local, receipt.is_local)
        self.assertEqual(restored.input_tokens, receipt.input_tokens)
        self.assertEqual(restored.output_tokens, receipt.output_tokens)
        self.assertEqual(restored.prompt_tokens, receipt.prompt_tokens)
        self.assertEqual(restored.completion_tokens, receipt.completion_tokens)
        self.assertEqual(restored.wall_clock_seconds, receipt.wall_clock_seconds)
        self.assertEqual(restored.duration_ms, receipt.duration_ms)
        self.assertEqual(restored.wall_time_ms, receipt.wall_time_ms)
        self.assertEqual(restored.usd_cost, receipt.usd_cost)
        self.assertEqual(restored.cost_usd, receipt.cost_usd)
        self.assertEqual(restored.request_hash, receipt.request_hash)
        self.assertEqual(restored.response_hash, receipt.response_hash)
        self.assertEqual(restored.status, receipt.status)


    def test_receipt_rejects_cloud_model_zero_tokens_on_success(self) -> None:
        """Cloud model receipt with status='succeeded' cannot have 0 tokens or $0.00 cost."""
        with self.assertRaises(ValueError):
            ModelInvocationReceipt.create(
                model_id="gpt-4o",
                is_local=False,
                input_tokens=0,
                output_tokens=0,
                wall_clock_seconds=0.1,
                usd_cost=0.0,
                status="succeeded",
            )

    def test_receipt_rejects_failed_invocation_with_non_zero_cost(self) -> None:
        """Failed invocation receipt cannot record non-zero billed cost."""
        with self.assertRaises(ValueError):
            ModelInvocationReceipt.create(
                model_id="gpt-4o",
                is_local=False,
                input_tokens=0,
                output_tokens=0,
                wall_clock_seconds=0.1,
                usd_cost=0.05,
                status="failed",
            )

    def test_receipt_from_dict_derives_duration_ms_when_missing(self) -> None:
        """from_dict auto-derives duration_ms from wall_clock_seconds if duration_ms is absent."""
        data = {
            "model_id": "gpt-4o",
            "is_local": False,
            "input_tokens": 100,
            "output_tokens": 50,
            "wall_clock_seconds": 1.25,
            "usd_cost": 0.00075,
            "status": "succeeded",
        }
        receipt = ModelInvocationReceipt.from_dict(data)
        self.assertAlmostEqual(receipt.wall_clock_seconds, 1.25)
        self.assertAlmostEqual(receipt.duration_ms, 1250.0)

    def test_receipt_from_dict_derives_wall_clock_seconds_when_missing(self) -> None:
        """from_dict auto-derives wall_clock_seconds from duration_ms if seconds is absent."""
        data = {
            "model_id": "gpt-4o",
            "is_local": False,
            "input_tokens": 100,
            "output_tokens": 50,
            "duration_ms": 2500.0,
            "usd_cost": 0.00075,
            "status": "succeeded",
        }
        receipt = ModelInvocationReceipt.from_dict(data)
        self.assertAlmostEqual(receipt.duration_ms, 2500.0)
        self.assertAlmostEqual(receipt.wall_clock_seconds, 2.5)

    def test_receipt_rejects_boolean_token_counts(self) -> None:
        """ModelInvocationReceipt rejects booleans passed as token counts."""
        with self.assertRaises(TypeError):
            ModelInvocationReceipt.create(
                model_id="gpt-4o",
                is_local=False,
                input_tokens=True,  # type: ignore[arg-type]
                output_tokens=10,
                wall_clock_seconds=0.1,
                usd_cost=0.01,
            )


class TestDynamicProviderPricingResolution(unittest.TestCase):
    """Verify dynamically resolved cloud providers get verified non-zero pricing."""

    def test_dynamic_openrouter_deepseek_resolves_pricing(self) -> None:
        gateway = TraceModelGateway(
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
        )
        model = gateway._registered("openrouter/deepseek/deepseek-chat", purpose="synthesis")
        self.assertFalse(model.is_local)
        self.assertAlmostEqual(model.input_cost_per_million_usd, 0.27, places=4)
        self.assertAlmostEqual(model.output_cost_per_million_usd, 1.10, places=4)

    def test_dynamic_openrouter_gpt4o_resolves_pricing(self) -> None:
        gateway = TraceModelGateway(
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
        )
        model = gateway._registered("openrouter/openai/gpt-4o", purpose="synthesis")
        self.assertFalse(model.is_local)
        self.assertAlmostEqual(model.input_cost_per_million_usd, 2.50, places=4)
        self.assertAlmostEqual(model.output_cost_per_million_usd, 10.00, places=4)

    def test_dynamic_unlisted_cloud_provider_gets_tier_pricing_never_zero(self) -> None:
        gateway = TraceModelGateway(
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
        )
        model_flash = gateway._registered("together_ai/custom-mini-model", purpose="synthesis")
        self.assertFalse(model_flash.is_local)
        self.assertGreater(model_flash.input_cost_per_million_usd, 0.0)
        self.assertGreater(model_flash.output_cost_per_million_usd, 0.0)

        model_pro = gateway._registered("together_ai/custom-huge-model", purpose="synthesis")
        self.assertFalse(model_pro.is_local)
        self.assertGreater(model_pro.input_cost_per_million_usd, 0.0)
        self.assertGreater(model_pro.output_cost_per_million_usd, 0.0)

    def test_case_insensitive_and_whitespace_pricing_lookup(self) -> None:
        """Pricing lookup resolves case-insensitively and ignores leading/trailing whitespace."""
        p1 = get_model_pricing("  ALL-MiniLM-L6-v2  ")
        self.assertTrue(p1.is_local)
        self.assertEqual(p1.input_cost_per_m, 0.0)

        p2 = get_model_pricing("DEEPSEEK-V4-FLASH")
        self.assertFalse(p2.is_local)
        self.assertAlmostEqual(p2.input_cost_per_m, 0.27)

    def test_ollama_local_model_resolution_and_zero_cost(self) -> None:
        """Dynamic ollama/ or local/ models resolve with is_local=True and strictly $0.00 pricing."""
        gateway = TraceModelGateway(
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
        )
        ollama_model = gateway._registered("ollama/mistral", purpose="synthesis")
        self.assertTrue(ollama_model.is_local)
        self.assertEqual(ollama_model.input_cost_per_million_usd, 0.0)
        self.assertEqual(ollama_model.output_cost_per_million_usd, 0.0)


class TestWorkspaceModelBudgetEnforcement(unittest.TestCase):
    """Verify workspace budget checks enforce cost limits on cloud models but allow free local models."""

    def test_workspace_budget_exceeded_raises_model_policy_denied(self) -> None:
        class BudgetAuditStore:
            def model_cost_total(self, workspace_id: str) -> float:
                return 10.00

        gateway = TraceModelGateway(
            store=BudgetAuditStore(),
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
            completion=lambda **_: {
                "choices": [{"message": {"content": json.dumps({"rendering": "Budget test."})}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )
        gateway.workspace_budget_usd = 10.00
        context = SimpleNamespace(
            workspace_id="ws-budget",
            subject="tester",
            request_id="req-b1",
            model_permissions=frozenset({"*"}),
        )
        # DeepSeek Pro costs $0.55/M in. Estimated tokens for query + candidate will exceed $0.001
        with self.assertRaises(ModelPolicyDenied) as ctx:
            gateway.call_json(
                context=context,
                model_id="deepseek-v4-pro",
                purpose="synthesis",
                query="Budget query that puts spend over $10.00",
                candidates=[{"atom_version_id": "a1", "content": "Evidence text for budget test."}],
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=5,
                token_budget=1000,
                prompt_template_revision="v1",
            )
        self.assertIn("workspace model budget is exhausted", str(ctx.exception))

    def test_workspace_budget_allows_local_models_even_when_budget_exhausted(self) -> None:
        class BudgetAuditStore:
            def model_cost_total(self, workspace_id: str) -> float:
                return 100.00

        gateway = TraceModelGateway(
            store=BudgetAuditStore(),
            policy=ModelGatewayPolicy(ModelPolicy(allow_cloud=True)),
            completion=lambda **_: {
                "choices": [{"message": {"content": json.dumps({"rendering": "Free local call allowed."})}}],
                "usage": {"prompt_tokens": 200, "completion_tokens": 100},
            },
        )
        gateway.workspace_budget_usd = 10.00  # Already spent $100 > $10
        context = SimpleNamespace(
            workspace_id="ws-budget",
            subject="tester",
            request_id="req-b2",
            model_permissions=frozenset({"*"}),
        )
        # Local model has $0.00 estimate, so 100.0 + 0.0 = 100.0 <= budget check (estimate_usd == 0)
        # Wait: spent + estimate_usd > workspace_budget_usd -> 100 + 0 = 100 > 10.
        # But for local models, budget is checked only if estimated_cost > 0!
        val, audit = gateway.call_json(
            context=context,
            model_id="qwen2.5-3b-local",
            purpose="synthesis",
            query="Local query should proceed",
            candidates=[{"atom_version_id": "a1", "content": "Evidence text for local test."}],
            response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
            max_nodes=5,
            token_budget=1000,
            prompt_template_revision="v1",
        )
        self.assertEqual(val["rendering"], "Free local call allowed.")
        self.assertEqual(audit["status"], "succeeded")
        self.assertEqual(audit["usd_cost"], 0.0)


if __name__ == "__main__":
    unittest.main()
