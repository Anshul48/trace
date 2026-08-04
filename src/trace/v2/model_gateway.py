"""Policy boundary for any local or cloud-assisted model call."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class ModelPolicy:
    """Redaction and budget policy applied before text leaves the service."""

    pii_classes: frozenset[str] = frozenset({"email", "phone", "api_key"})
    max_excerpt_chars: int = 4_000
    max_nodes: int = 32
    allow_cloud: bool = False
    token_budget: int = 4_000


@dataclass
class ModelCallAudit:
    provider: str
    purpose: str
    policy_outcome: str
    excerpt_hashes: list[str] = field(default_factory=list)
    node_count: int = 0
    estimated_tokens: int = 0
    cloud_tokens: int = 0
    cost_usd: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "purpose": self.purpose,
            "policy_outcome": self.policy_outcome,
            "excerpt_hashes": self.excerpt_hashes,
            "node_count": self.node_count,
            "estimated_tokens": self.estimated_tokens,
            "cloud_tokens": self.cloud_tokens,
            "cost_usd": self.cost_usd,
        }


class ModelGatewayPolicy:
    """Redact configured PII classes and return auditable safe excerpts."""

    _patterns = {
        "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        "phone": re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)"),
        "api_key": re.compile(r"\b(?:sk|pk|ghp|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b|\b[A-Za-z0-9_-]{24,}\b"),
        "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    }

    def __init__(self, policy: ModelPolicy | None = None) -> None:
        self.policy = policy or ModelPolicy()

    def redact(self, text: str) -> str:
        output = text
        for name in self.policy.pii_classes:
            pattern = self._patterns.get(name)
            if pattern:
                output = pattern.sub(f"[{name.upper()}_REDACTED]", output)
        return output

    def excerpt(self, text: str) -> tuple[str, str]:
        safe = self.redact(text)[: self.policy.max_excerpt_chars]
        return safe, hashlib.sha256(safe.encode("utf-8")).hexdigest()

    def prepare(
        self,
        *,
        provider: str,
        purpose: str,
        query: str,
        candidates: Sequence[dict[str, Any]],
        max_nodes: int,
        token_budget: int,
        cloud: bool,
    ) -> tuple[str, list[dict[str, Any]], ModelCallAudit]:
        if cloud and not self.policy.allow_cloud:
            raise PermissionError("cloud model calls are disabled by policy")
        audit = ModelCallAudit(provider=provider, purpose=purpose, policy_outcome="approved")
        safe_query, query_hash = self.excerpt(query)
        audit.excerpt_hashes.append(query_hash)
        selected: list[dict[str, Any]] = []
        used_tokens = 0
        for candidate in candidates[: min(max_nodes, self.policy.max_nodes)]:
            safe_text, text_hash = self.excerpt(str(candidate.get("content") or candidate.get("summary") or ""))
            estimate = max(1, len(safe_text.split()))
            if used_tokens + estimate > min(token_budget, self.policy.token_budget):
                break
            selected.append({
                "atom_version_id": candidate.get("atom_version_id") or candidate.get("id"),
                "content": safe_text,
                "source_atom_version_ids": list(candidate.get("source_atom_version_ids", []))[:32],
            })
            audit.excerpt_hashes.append(text_hash)
            used_tokens += estimate
        audit.node_count = len(selected)
        audit.estimated_tokens = used_tokens
        return safe_query, selected, audit
