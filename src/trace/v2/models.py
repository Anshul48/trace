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
    deep_max_rounds: int = Field(default=3, ge=1, le=8)
    deep_branch_width: int = Field(default=4, ge=1, le=32)
    deep_token_budget: int = Field(default=4_000, ge=128, le=100_000)
    affinity_limit: int = Field(default=24, ge=0, le=128)
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
        "projection.backfill", "projection.legacy_import", "hierarchy.delta", "affinity.delta", "activation.recompute",
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
        if self.model_id and self.kind not in {"schema.proposals", "cognitive.delta", "hierarchy.delta"}:
            raise ValueError("model_id is allowed only for LLM-backed jobs")
        return self


class ActivationWeights(BaseModel):
    """Server-governed transition mass for the query-local energy layer.

    These values are policy state, not request tuning knobs.  Keeping every
    family individually bounded prevents a client from turning a feedback or
    affinity signal into a factual proof path.
    """

    structural: float = Field(default=0.35, ge=0, le=0.70)
    trusted_evidence: float = Field(default=0.35, ge=0, le=0.70)
    affinity: float = Field(default=0.20, ge=0, le=0.50)
    behavioral: float = Field(default=0.10, ge=0, le=0.35)
    damping: float = Field(default=0.55, ge=0, le=0.95)
    iterations: int = Field(default=12, ge=1, le=50)
    max_degree: int = Field(default=24, ge=1, le=128)

    @model_validator(mode="after")
    def bounded_total_mass(self) -> "ActivationWeights":
        if self.structural + self.trusted_evidence + self.affinity + self.behavioral > 1.0 + 1e-9:
            raise ValueError("activation family mass must not exceed 1")
        return self


class CognitivePolicy(BaseModel):
    """Revisioned workspace policy for replaceable Cortex projections."""

    policy_revision: str = Field(default="cognitive-policy-v1", min_length=1, max_length=128)
    auto_derived_projections: bool = True
    auto_promote_trusted_evidence: bool = False
    cloud_models_enabled: bool = True
    raw_evidence_required: bool = True
    allow_low_risk_projection_visibility: bool = True
    affinity_degree_cap: int = Field(default=16, ge=1, le=128)
    affinity_ttl_seconds: int = Field(default=2_592_000, ge=60, le=31_536_000)
    activation: ActivationWeights = Field(default_factory=ActivationWeights)

    @model_validator(mode="after")
    def factual_promotion_remains_reviewed(self) -> "CognitivePolicy":
        if self.auto_promote_trusted_evidence:
            raise ValueError("automatic promotion of trusted evidence is not permitted")
        if not self.raw_evidence_required:
            raise ValueError("raw evidence is required for factual synthesis")
        return self


class ProjectionRebuildRequest(BaseModel):
    """Bounded projection work request; it can never target canonical rows."""

    workspace_id: str = Field(min_length=1, max_length=255)
    projection_kind: Literal["hierarchy", "affinity", "activation"]
    from_event_offset: int | None = Field(default=None, ge=1)
    through_event_offset: int | None = Field(default=None, ge=1)
    atom_version_ids: list[str] = Field(default_factory=list, max_length=1_000)
    index_revision: str | None = Field(default=None, max_length=255)
    model_revision: str | None = Field(default=None, max_length=255)
    prompt_revision: str | None = Field(default=None, max_length=255)
    # Server-pinned at enqueue time. A worker refuses a stale policy rather
    # than silently rebuilding a projection under different controls.
    policy_revision: str | None = Field(default=None, max_length=255)
    actor: str = "system"

    @model_validator(mode="after")
    def bounded_event_range(self) -> "ProjectionRebuildRequest":
        if self.from_event_offset and self.through_event_offset and self.from_event_offset > self.through_event_offset:
            raise ValueError("from_event_offset must not exceed through_event_offset")
        return self


class AffinityRejectionRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=255)
    source_atom_version_id: str = Field(min_length=1)
    target_atom_version_id: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=2_000)
    actor: str = "anonymous"

    @model_validator(mode="after")
    def distinct_endpoints(self) -> "AffinityRejectionRequest":
        if self.source_atom_version_id == self.target_atom_version_id:
            raise ValueError("an affinity pair needs two distinct atom versions")
        return self


class DeepNavigationPlan(BaseModel):
    """Validated opaque-ID plan emitted by bounded deep navigation.

    The plan intentionally contains IDs and stop reasons only.  It cannot
    create relations, inject text, or act as a source of truth.
    """

    frontier_ids: list[str] = Field(default_factory=list, max_length=100)
    selected_ids: list[str] = Field(default_factory=list, max_length=100)
    bridge_seed_ids: list[str] = Field(default_factory=list, max_length=100)
    stop_reason: Literal["sufficient", "budget_exhausted", "no_frontier", "provider_unavailable", "max_rounds"] = "no_frontier"
    round: int = Field(default=1, ge=1, le=8)

    @model_validator(mode="after")
    def opaque_ids_are_unique(self) -> "DeepNavigationPlan":
        for values in (self.frontier_ids, self.selected_ids, self.bridge_seed_ids):
            if len(values) != len(set(values)):
                raise ValueError("deep-navigation IDs must be unique within each plan field")
        return self

    def validated_against(
        self,
        allowed_ids: set[str],
        *,
        branch_width: int,
        allowed_bridge_ids: set[str] | None = None,
    ) -> "DeepNavigationPlan":
        if branch_width < 1:
            raise ValueError("branch_width must be positive")
        invalid = (set(self.frontier_ids) | set(self.selected_ids)) - allowed_ids
        bridge_allowed = allowed_ids if allowed_bridge_ids is None else allowed_bridge_ids
        invalid |= set(self.bridge_seed_ids) - bridge_allowed
        if invalid:
            raise ValueError("deep-navigation plan contains an ID outside the allowed navigation set")
        if len(self.selected_ids) > branch_width:
            raise ValueError("deep-navigation plan exceeds branch_width")
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


class CortexValidationReceipt(BaseModel):
    """Durable validation receipt for a candidate Cortex release."""
    structural: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    parity: dict[str, Any] = Field(default_factory=dict)
    evaluator_manifest_id: str | None = None
    validated_at: datetime | None = None
    passed: bool = True


class CortexReleaseComponent(BaseModel):
    """One immutable component revision within a Cortex release root."""
    release_id: str
    workspace_id: str
    component_kind: Literal["hierarchy", "affinity", "activation_priors", "lexical_index", "dense_index"]
    component_revision: str
    input_checksum: str
    source_watermark: int
    carried_forward_from_release_id: str | None = None
    validation_status: Literal["pending", "validated", "failed"] = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class CortexRelease(BaseModel):
    """Unified Cortex Release Root representing one validated derived state."""
    release_id: str
    workspace_id: str
    parent_release_id: str | None = None
    spine_event_watermark: int
    status: Literal["planned", "building", "validating", "validated", "active", "superseded", "retired", "failed"]
    policy_revision: str
    policy_snapshot_hash: str
    code_revision: str
    validation_receipt: dict[str, Any] = Field(default_factory=dict)
    components: list[CortexReleaseComponent] | dict[str, Any] = Field(default_factory=list)
    created_at: datetime
    activated_at: datetime | None = None
    superseded_at: datetime | None = None
    retired_at: datetime | None = None
    failure_detail: str | None = None


class CortexReleaseCreateRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    parent_release_id: str | None = None
    spine_event_watermark: int | None = None
    policy_revision: str | None = None
    policy_snapshot_hash: str | None = None
    code_revision: str | None = None
    components: list[dict[str, Any]] = Field(default_factory=list)
    actor: str = "system"


class CortexReleaseValidateRequest(BaseModel):
    validation_receipt: CortexValidationReceipt | dict[str, Any] = Field(default_factory=dict)
    actor: str = "system"


class CortexReleaseActivateRequest(BaseModel):
    actor: str = "system"


class CortexReleaseRollbackRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    target_release_id: str | None = None
    reason: str | None = None
    actor: str = "system"

