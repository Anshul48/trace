"""Public contracts and small internal value objects for Trace V2.

These models are the compatibility boundary for SDKs and HTTP clients. Storage
details such as SQLite row IDs, projection revisions, and object-store paths
are intentionally absent from request models; responses may expose provenance
IDs and event offsets for auditability.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceInput(BaseModel):
    """Ingress provenance and adapter metadata, never an atom owner.

    ``metadata`` is retained as provenance. It must not be interpreted as a
    canonical semantic label unless a later evidence-backed proposal promotes
    that interpretation.
    """

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    uri: str | None = None
    media_type: str = "text/plain"
    adapter: str = "text"
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionRequest(BaseModel):
    """Normalized text capture request.

    Binary uploads use the multipart route, which retains the original bytes
    and passes extracted parser text through this same contract.
    """
    workspace_id: str = Field(min_length=1, max_length=255)
    text: str | None = None
    source: SourceInput = Field(default_factory=SourceInput)
    actor: str = "anonymous"
    visibility: str = "private"
    idempotency_key: str | None = Field(default=None, max_length=255)
    adapter_payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def requires_text(self) -> "IngestionRequest":
        if not self.text or not self.text.strip():
            raise ValueError("text is required; adapters must provide normalized text")
        return self


class NodeEditRequest(BaseModel):
    content: str = Field(min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)
    actor: str = "anonymous"
    idempotency_key: str | None = None


class SplitRequest(BaseModel):
    parts: list[str] = Field(min_length=2)
    actor: str = "anonymous"
    idempotency_key: str | None = None

    @model_validator(mode="after")
    def nonempty_parts(self) -> "SplitRequest":
        if any(not part.strip() for part in self.parts):
            raise ValueError("split parts must not be empty")
        return self


class AliasRequest(BaseModel):
    target_node_id: str = Field(min_length=1)
    actor: str = "anonymous"
    evidence_atom_version_ids: list[str] = Field(default_factory=list)
    idempotency_key: str | None = None


class RetrievalBudget(BaseModel):
    """Hard limits for a retrieval run.

    Limits are part of the query contract rather than implementation defaults:
    this makes deep searches reproducible and prevents an unbounded model or
    graph traversal from becoming an accidental corpus read.
    """

    candidate_limit: int = Field(default=20, ge=1, le=200)
    lexical_limit: int = Field(default=100, ge=1, le=1_000)
    dense_limit: int = Field(default=100, ge=1, le=1_000)
    rerank_limit: int = Field(default=50, ge=1, le=500)
    graph_seed_limit: int = Field(default=5, ge=1, le=25)
    graph_iterations: int = Field(default=20, ge=1, le=100)
    graph_weight: float = Field(default=0.18, ge=0, le=1)
    feedback_weight: float = Field(default=0.08, ge=0, le=1)
    hierarchy_limit: int = Field(default=32, ge=1, le=200)
    deep_max_nodes: int = Field(default=12, ge=1, le=100)
    deep_token_budget: int = Field(default=4_000, ge=128, le=100_000)
    allow_deep_escalation: bool = True
    mode: Literal["fast", "standard", "graph", "hierarchy", "deep"] = "fast"

    @model_validator(mode="after")
    def bounded_stages(self) -> "RetrievalBudget":
        if self.rerank_limit > max(self.lexical_limit, self.dense_limit) * 2:
            raise ValueError("rerank_limit must remain bounded by candidate generators")
        return self


class QueryRequest(BaseModel):
    """Evidence retrieval request with explicit historical and policy scope."""
    query: str = Field(min_length=1)
    workspace_id: str | None = None
    as_of_event: int | None = Field(default=None, ge=1)
    facets: list[str] = Field(default_factory=list)
    privacy_context: dict[str, Any] = Field(default_factory=dict)
    retrieval_budget: RetrievalBudget = Field(default_factory=RetrievalBudget)
    retrieval_profile: Literal["auto", "lexical", "hybrid", "rerank", "hierarchy", "graph", "deep"] = "auto"
    # A model is meaningful only for bounded deep navigation.  Ordinary
    # evidence retrieval stays model-independent and cannot be turned into an
    # arbitrary provider call by adding a model name to a request.
    model_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def model_only_for_deep_navigation(self) -> "QueryRequest":
        if self.model_id and self.retrieval_profile != "deep" and self.retrieval_budget.mode != "deep":
            raise ValueError("model_id is allowed only for deep navigation")
        return self


class SynthesisRequest(BaseModel):
    """Request for a disposable rendering of one persisted evidence bundle."""
    evidence_bundle_id: str = Field(min_length=1)
    workspace_id: str | None = Field(default=None, min_length=1)
    prompt: str | None = None
    format: Literal["brief", "report", "weave"] = "brief"
    privacy_context: dict[str, Any] = Field(default_factory=dict)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)


class ProposalCreateRequest(BaseModel):
    """Source-backed candidate organization awaiting a reversible decision."""
    workspace_id: str = Field(min_length=1)
    proposal_type: Literal[
        "edge", "edge_strength", "holon", "schema", "merge", "summary", "contradiction_resolution", "claim"
    ]
    candidate: dict[str, Any]
    evidence_atom_version_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    model_version: str = "manual"
    actor: str = "anonymous"
    idempotency_key: str | None = None


class HierarchyBuildRequest(BaseModel):
    """Request a deterministic, evidence-anchored hierarchy projection."""

    workspace_id: str = Field(min_length=1)
    section_size: int = Field(default=8, ge=2, le=64)
    local_topic_size: int = Field(default=6, ge=2, le=32)
    actor: str = "system"
    model_version: str = "extractive-hierarchy-v1"


class SchemaProposalRequest(BaseModel):
    """Ask the configured teacher/proposer for reviewable schema candidates."""

    workspace_id: str = Field(min_length=1)
    max_schemas: int = Field(default=12, ge=1, le=100)
    # Nightly workers supply just-ingested / candidate IDs. Omitting this is
    # permitted only by the embedded control adapter, never production scale.
    atom_version_ids: list[str] = Field(default_factory=list, max_length=512)
    model_version: str = "local-schema-proposer-v1"
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    actor: str = "system"


class EvidenceFeedbackRequest(BaseModel):
    """Explicit retrieval feedback; it is never a graph-mutation command."""

    workspace_id: str = Field(min_length=1)
    evidence_bundle_id: str | None = None
    atom_version_id: str = Field(min_length=1)
    event_type: Literal["selected", "opened", "cited", "accepted", "rejected"]
    weight: float = Field(default=1.0, ge=0, le=10)
    metadata: dict[str, Any] = Field(default_factory=dict)
    actor: str = "anonymous"
    idempotency_key: str | None = Field(default=None, max_length=255)


class FeedbackEdgeProposalRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    minimum_signal: float = Field(default=0.15, ge=0.01, le=1)
    max_proposals: int = Field(default=50, ge=1, le=500)
    actor: str = "system"


class BenchmarkRunRequest(BaseModel):
    """Run a frozen evidence-retrieval benchmark against named stages."""

    workspace_id: str = Field(min_length=1)
    benchmark_path: str = Field(min_length=1)
    stages: list[Literal["lexical", "hybrid", "rerank", "hierarchy", "graph", "deep"]] = Field(
        default_factory=lambda: ["lexical", "hybrid", "rerank", "hierarchy", "graph", "deep"]
    )
    bootstrap_fixture: bool = False
    release_gate: bool = False
    actor: str = "system"


class ProposalDecisionRequest(BaseModel):
    actor: str = "anonymous"
    reason: str | None = None
    idempotency_key: str | None = None


class JobSubmitRequest(BaseModel):
    """Submit a bounded asynchronous workflow to the durable job ledger."""

    workspace_id: str = Field(min_length=1, max_length=255)
    kind: Literal[
        "consolidation", "hierarchy.build", "schema.proposals", "benchmark.run",
        "index.rebuild", "reprocess", "ingestion.index", "cognitive.delta",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    actor: str = "anonymous"
    idempotency_key: str | None = Field(default=None, max_length=255)
    webhook_id: str | None = None
    execute: bool = False
    # Only the server maps this ID to a provider/model configuration.  The
    # payload deliberately has no provider URL, API key, or raw prompt field.
    model_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def model_only_for_llm_job(self) -> "JobSubmitRequest":
        if self.model_id and self.kind not in {"schema.proposals", "cognitive.delta"}:
            raise ValueError("model_id is allowed only for LLM-backed jobs")
        return self


class JobDecisionRequest(BaseModel):
    actor: str = "anonymous"
    reason: str | None = None
    execute: bool = False


class WebhookCreateRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=2_048)
    event_types: list[str] = Field(default_factory=lambda: ["job.succeeded", "job.failed"])
    actor: str = "anonymous"


class WebhookRotateRequest(BaseModel):
    actor: str = "anonymous"


class ApiKeyCreateRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: ["retrieval:read"])
    allowed_visibility: list[str] = Field(default_factory=lambda: ["private"])
    model_permissions: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    actor: str = "anonymous"


class ApiKeyDecisionRequest(BaseModel):
    actor: str = "anonymous"
    reason: str | None = None


class SavedQueryRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)
    query: QueryRequest
    actor: str = "anonymous"


class FrozenQueryRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)
    query: QueryRequest
    actor: str = "anonymous"


class GraphRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    seed_node_ids: list[str] = Field(default_factory=list, max_length=128)
    depth: int = Field(default=1, ge=0, le=4)
    as_of_event: int | None = Field(default=None, ge=1)
    privacy_context: dict[str, Any] = Field(default_factory=dict)


class IndexRevisionRequest(BaseModel):
    workspace_id: str | None = None
    embedding_model: str
    vector_namespace: str
    lexical_revision: str
    normalization: dict[str, Any] = Field(default_factory=dict)
    rollout_state: Literal["candidate", "active", "retired"] = "candidate"
    actor: str = "anonymous"


class ModelRegistrationRequest(BaseModel):
    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    purpose: Literal["embedding", "reranking", "classification", "synthesis", "navigation"]
    version: str = Field(min_length=1)
    configuration: dict[str, Any] = Field(default_factory=dict)
    actor: str = "anonymous"


class ExperimentManifestRequest(BaseModel):
    name: str = Field(min_length=1)
    corpus_snapshot: str = Field(min_length=1)
    code_revision: str = "unknown"
    model_versions: dict[str, str] = Field(default_factory=dict)
    index_revisions: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    actor: str = "anonymous"


class AppendResult(BaseModel):
    event_id: str
    offset: int
    stream_sequence: int
    duplicate: bool = False


class EventRecord(BaseModel):
    event_id: str
    offset: int
    stream_id: str
    stream_sequence: int
    event_type: str
    occurred_at: datetime
    actor: str
    causation_id: str | None = None
    correlation_id: str | None = None
    schema_version: int
    payload: dict[str, Any]
    payload_hash: str
    idempotency_key: str | None = None
