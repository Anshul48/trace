"""Shared types and dataclasses for Trace v2 cognitive architecture."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping


class ModelGatewayError(RuntimeError):
    """A clean, caller-safe model-gateway failure."""


class ModelUnavailableError(ModelGatewayError):
    """A transient provider failure after the bounded retry policy is spent."""


class ModelPolicyDenied(ModelGatewayError):
    """The model is not registered, allowed, or within a workspace budget."""


class ModelEmptyResponseError(ModelGatewayError):
    """Raised when model returns empty or whitespace-only response."""


class ModelMalformedJsonError(ModelGatewayError):
    """Raised when JSON parsing fails or does not match payload boundaries."""


class ModelUncitedOutputError(ModelGatewayError):
    """Raised when an extractive/synthesizing output lacks required evidence anchors."""


class ModelMissingUsageError(ModelGatewayError):
    """Raised when token usage counters are missing from provider response."""


class UnregisteredModelPricingError(ModelGatewayError):
    """Raised when pricing is requested for an unregistered model."""


@dataclass(frozen=True)
class ModelPricing:
    """Pricing configuration ($/1M tokens) and locality metadata for a model."""

    model_id: str
    input_cost_per_million_usd: float
    output_cost_per_million_usd: float
    is_local: bool = False

    def __post_init__(self) -> None:
        if self.is_local:
            if self.input_cost_per_million_usd != 0.0 or self.output_cost_per_million_usd != 0.0:
                raise ValueError(
                    f"Local model {self.model_id!r} cannot have non-zero pricing without is_local=False (got in={self.input_cost_per_million_usd}, out={self.output_cost_per_million_usd})"
                )
        else:
            if self.input_cost_per_million_usd <= 0.0 or self.output_cost_per_million_usd <= 0.0:
                raise ValueError(
                    f"Cloud model {self.model_id!r} cannot have zero pricing without is_local=True (got in={self.input_cost_per_million_usd}, out={self.output_cost_per_million_usd})"
                )

    @property
    def input_cost_per_m(self) -> float:
        return self.input_cost_per_million_usd

    @property
    def output_cost_per_m(self) -> float:
        return self.output_cost_per_million_usd

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate deterministic USD cost from token counts."""
        if isinstance(input_tokens, bool) or isinstance(output_tokens, bool) or not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            raise TypeError(f"Token counts must be integers (got input_tokens={type(input_tokens).__name__}, output_tokens={type(output_tokens).__name__})")
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError(f"Token counts cannot be negative (got input_tokens={input_tokens}, output_tokens={output_tokens})")
        if self.is_local:
            return 0.0
        return (
            input_tokens * self.input_cost_per_million_usd
            + output_tokens * self.output_cost_per_million_usd
        ) / 1_000_000.0


@dataclass(frozen=True)
class ModelInvocationReceipt:
    """Immutable provenance and cost receipt for a model execution."""

    invocation_id: str
    model_id: str
    is_local: bool
    input_tokens: int
    output_tokens: int
    wall_clock_seconds: float
    duration_ms: float
    usd_cost: float
    request_hash: str = ""
    response_hash: str = ""
    status: str = "succeeded"
    prompt_tokens: int = field(init=False)
    completion_tokens: int = field(init=False)
    wall_time_ms: float = field(init=False)
    cost_usd: float = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.input_tokens, bool) or isinstance(self.output_tokens, bool) or not isinstance(self.input_tokens, int) or not isinstance(self.output_tokens, int):
            raise TypeError(f"Receipt token counts must be integers (got input_tokens={type(self.input_tokens).__name__}, output_tokens={type(self.output_tokens).__name__})")
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError(f"Receipt token counts cannot be negative (in={self.input_tokens}, out={self.output_tokens})")
        if self.wall_clock_seconds < 0.0 or self.duration_ms < 0.0:
            raise ValueError(f"Receipt duration cannot be negative (wall_clock_seconds={self.wall_clock_seconds}, duration_ms={self.duration_ms})")
        if self.usd_cost < 0.0:
            raise ValueError(f"Receipt cost cannot be negative (usd_cost={self.usd_cost})")
        if self.is_local and self.usd_cost != 0.0:
            raise ValueError(f"Local model receipt for {self.model_id!r} cannot have non-zero cost ({self.usd_cost})")
        if not self.is_local and self.status == "succeeded":
            if self.usd_cost <= 0.0 or (self.input_tokens <= 0 and self.output_tokens <= 0):
                raise ValueError(
                    f"Cloud model receipt for {self.model_id!r} cannot have zero or negative cost or zero tokens on success "
                    f"(got in={self.input_tokens}, out={self.output_tokens}, cost={self.usd_cost})"
                )
        if self.status == "failed" and self.usd_cost != 0.0:
            raise ValueError(f"Failed invocation receipt for {self.model_id!r} cannot record non-zero cost ({self.usd_cost})")

        object.__setattr__(self, "prompt_tokens", self.input_tokens)
        object.__setattr__(self, "completion_tokens", self.output_tokens)
        object.__setattr__(self, "wall_time_ms", self.duration_ms)
        object.__setattr__(self, "cost_usd", self.usd_cost)

    def as_dict(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "model_id": self.model_id,
            "is_local": self.is_local,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "wall_clock_seconds": self.wall_clock_seconds,
            "duration_seconds": self.wall_clock_seconds,
            "wall_clock_duration": self.wall_clock_seconds,
            "duration_ms": self.duration_ms,
            "wall_time_ms": self.wall_time_ms,
            "usd_cost": self.usd_cost,
            "cost_usd": self.cost_usd,
            "request_hash": self.request_hash,
            "response_hash": self.response_hash,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelInvocationReceipt:
        raw_seconds = data.get("wall_clock_seconds", data.get("duration_seconds", data.get("wall_clock_duration")))
        raw_ms = data.get("duration_ms", data.get("wall_time_ms"))
        if raw_seconds is not None:
            wall_clock_seconds = float(raw_seconds)
            duration_ms = float(raw_ms) if raw_ms is not None else (wall_clock_seconds * 1000.0)
        elif raw_ms is not None:
            duration_ms = float(raw_ms)
            wall_clock_seconds = duration_ms / 1000.0
        else:
            wall_clock_seconds = 0.0
            duration_ms = 0.0
        return cls(
            invocation_id=str(data.get("invocation_id") or uuid.uuid4()),
            model_id=str(data["model_id"]),
            is_local=bool(data["is_local"]),
            input_tokens=int(data.get("input_tokens", data.get("prompt_tokens", 0))),
            output_tokens=int(data.get("output_tokens", data.get("completion_tokens", 0))),
            wall_clock_seconds=wall_clock_seconds,
            duration_ms=duration_ms,
            usd_cost=float(data.get("usd_cost", data.get("cost_usd", 0.0))),
            request_hash=str(data.get("request_hash", "")),
            response_hash=str(data.get("response_hash", "")),
            status=str(data.get("status", "succeeded")),
        )

    @classmethod
    def create(
        cls,
        *,
        model_id: str,
        is_local: bool,
        input_tokens: int,
        output_tokens: int,
        wall_clock_seconds: float,
        usd_cost: float,
        duration_ms: float | None = None,
        request_hash: str = "",
        response_hash: str = "",
        status: str = "succeeded",
        invocation_id: str | None = None,
    ) -> ModelInvocationReceipt:
        return cls(
            invocation_id=invocation_id or str(uuid.uuid4()),
            model_id=model_id,
            is_local=is_local,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            wall_clock_seconds=wall_clock_seconds,
            duration_ms=duration_ms if duration_ms is not None else (wall_clock_seconds * 1000.0),
            usd_cost=usd_cost,
            request_hash=request_hash,
            response_hash=response_hash,
            status=status,
        )
