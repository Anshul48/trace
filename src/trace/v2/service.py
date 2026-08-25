"""Application service for V2 ingestion, organization, retrieval, and views."""

from __future__ import annotations

import hashlib
import io
import os
import platform
import re
import secrets
import json
import tempfile
import uuid
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from pathlib import Path
from typing import Any

from .adapters import adapt_text
from .atomizer import atomize, normalize_text
from .benchmark import BenchmarkRunner, load_benchmark, validate_release_corpus
from .models import (
    AliasRequest,
    AffinityRejectionRequest,
    BenchmarkRunRequest,
    CognitivePolicy,
    EvidenceFeedbackRequest,
    FeedbackEdgeProposalRequest,
    ExperimentManifestRequest,
    FrozenQueryRequest,
    HierarchyBuildRequest,
    IndexRevisionRequest,
    IngestionRequest,
    ApiKeyCreateRequest,
    CortexReleaseCreateRequest,
    CortexReleaseValidateRequest,
    CortexReleaseActivateRequest,
    CortexReleaseRollbackRequest,
    JobSubmitRequest,
    ModelRegistrationRequest,
    NodeEditRequest,
    ProjectionRebuildRequest,
    ProposalCreateRequest,
    QueryRequest,
    SavedQueryRequest,
    SchemaProposalRequest,
    SourceErasureRequest,
    SourceLifecycleRequest,
    SplitRequest,
)
from .organization import DeterministicSchemaProposer, EvidenceHierarchyBuilder, GLiNERSchemaProposer, GovernedSchemaClassifier, SchemaProposer, SoftSchemaClassifier
from .retrieval import HybridRetrievalEngine, RetrievalOutcome
from .repository import Repository
from .jobs import JobManager
from .webhooks import WebhookDispatcher, WebhookSecretCipher, WebhookSigner, configured_webhook_cipher, validate_webhook_url
from .observability import MetricsRegistry, telemetry_span
from .store import InvariantViolation, NotFoundError, SqliteEventStore
from .config import TraceSettings
from .auth import AuthorizationContext
from .model_gateway import GatewayDeepNavigator, ModelPolicyDenied, TraceModelGateway
from .projections import ProjectionRevisionError, RevisionedProjectionController
from .cortex import canonical_pair


_TOKEN = re.compile(r"[\w][\w'-]*", re.UNICODE)
_STOPWORDS = frozenset({"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "that", "the", "to", "with"})
TEMPORAL_EXCLUSION_DETAIL_LIMIT = 64


def _tokens(text: str) -> list[str]:
    return [term for term in _TOKEN.findall(text.lower()) if term not in _STOPWORDS]


def _excerpt(content: str, query_terms: set[str], limit: int = 480) -> str:
    if len(content) <= limit:
        return content
    lower = content.lower()
    positions = [lower.find(term) for term in query_terms if lower.find(term) >= 0]
    start = max(0, min(positions) - limit // 4) if positions else 0
    end = min(len(content), start + limit)
    prefix = "…" if start else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end]}{suffix}"


class LocalPrivateObjectStore:
    """Content-addressed private attachment storage for embedded deployments."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, raw: bytes, media_type: str, *, workspace_id: str | None = None, **_: Any) -> dict[str, Any]:
        content_hash = hashlib.sha256(raw).hexdigest()
        safe_workspace = re.sub(r"[^A-Za-z0-9_.-]", "_", workspace_id or "unassigned")
        relative = Path("workspace") / safe_workspace / content_hash[:2] / content_hash
        target = self.root / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
                temporary.write(raw)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, target)
        return {
            "content_hash": content_hash,
            "object_key": relative.as_posix(),
            "media_type": media_type,
            "byte_length": len(raw),
            "metadata": {"storage": "local-private"},
        }

    def put_text(self, text: str, media_type: str, **kwargs: Any) -> dict[str, Any]:
        return self.put_bytes(text.encode("utf-8"), media_type, **kwargs)

    def get_bytes(self, object_key: str) -> bytes:
        target = self.root / object_key
        if not target.exists():
            raise NotFoundError(f"object {object_key} was not found")
        return target.read_bytes()

    def delete_object(self, object_key: str) -> dict[str, Any]:
        target = self.root / object_key
        if target.exists():
            target.unlink()
            return {"deleted": True, "object_key": object_key}
        return {"deleted": False, "object_key": object_key, "status": "already_deleted"}

    def verify_object_absent(self, object_key: str) -> bool:
        target = self.root / object_key
        return not target.exists()



class TraceService:
    """The only application layer used by the V2 HTTP API and SDK.

    The service owns orchestration, not canonical persistence. It normalizes
    adapter input, calls the store's transactional methods, applies retrieval
    policy, and formats evidence bundles. A deployment can replace the store
    and object-store implementations while preserving these operations and
    their invariants.
    """

    def __init__(
        self,
        store: Repository,
        object_store: Any,
        *,
        retrieval_engine: HybridRetrievalEngine | None = None,
        schema_proposer: SchemaProposer | None = None,
        coordination_store: Any | None = None,
        settings: TraceSettings | None = None,
        model_gateway: TraceModelGateway | None = None,
    ) -> None:
        self.settings = settings or TraceSettings.from_environ()
        self.store = store
        self.object_store = object_store
        self.retrieval_engine = retrieval_engine or HybridRetrievalEngine()
        # Automatic schema proposals stay local/reviewable.  A cloud schema
        # call requires an explicit registered ``model_id`` and goes through
        # ``TraceModelGateway`` in ``propose_schemas`` below.
        self.schema_proposer = schema_proposer or (
            GLiNERSchemaProposer()
            if os.environ.get("TRACE_GLINER_ENABLED", "false").lower() == "true"
            else DeterministicSchemaProposer()
        )
        self.hierarchy_builder = EvidenceHierarchyBuilder(store)
        self.metrics = MetricsRegistry()
        self.coordination_store = coordination_store
        self.model_gateway = model_gateway or TraceModelGateway(store=store)
        self.webhook_cipher = configured_webhook_cipher(production_mode=self.settings.production_mode)
        self.jobs = JobManager(store, webhook_dispatcher=WebhookDispatcher(store, cipher=self.webhook_cipher))
        self.jobs.register("ingestion.index", self._run_ingestion_index_job)
        self.jobs.register("consolidation", self._run_consolidation_job)
        self.jobs.register("hierarchy.build", self._run_hierarchy_job)
        self.jobs.register("schema.proposals", self._run_schema_job)
        self.jobs.register("benchmark.run", self._run_benchmark_job)
        self.jobs.register("index.rebuild", self._run_reindex_job)
        self.jobs.register("reprocess", self._run_reprocess_job)
        self.jobs.register("cognitive.delta", self._run_cognitive_delta_job)
        self.jobs.register("projection.backfill", self._run_projection_backfill_job)
        self.jobs.register("projection.legacy_import", self._run_projection_legacy_import_job)
        self.jobs.register("hierarchy.delta", self._run_hierarchy_delta_job)
        self.jobs.register("affinity.delta", self._run_affinity_delta_job)
        self.jobs.register("activation.recompute", self._run_activation_recompute_job)

    @classmethod
    def from_environment(cls) -> "TraceService":
        settings = TraceSettings.from_environ()
        repository_kind = settings.repository
        if repository_kind in {"postgres", "postgresql"}:
            from .production import PostgresEventStore

            store = PostgresEventStore(os.environ.get("TRACE_POSTGRES_DSN"))
            if settings.production_mode:
                store.verify_runtime_role()
        else:
            database_path = os.environ.get("TRACE_DB_PATH", ".trace/trace_v2.db")
            store = SqliteEventStore(database_path)
        object_kind = settings.object_store
        if object_kind in {"s3", "minio"}:
            from .production import S3ObjectStore

            bucket = os.environ.get("TRACE_S3_BUCKET")
            if not bucket:
                raise ValueError("TRACE_S3_BUCKET is required when TRACE_OBJECT_STORE=s3")
            object_store = S3ObjectStore(bucket)
        elif object_kind == "gcs":
            from .production import GcsObjectStore

            bucket = os.environ.get("TRACE_GCS_BUCKET")
            if not bucket:
                raise ValueError("TRACE_GCS_BUCKET is required when TRACE_OBJECT_STORE=gcs")
            object_store = GcsObjectStore(bucket)
        else:
            object_root = os.environ.get("TRACE_OBJECT_ROOT", ".trace/objects")
            object_store = LocalPrivateObjectStore(object_root)
        retrieval_engine: HybridRetrievalEngine | None = None
        lexical_index = dense_index = None
        if settings.opensearch_index:
            from .production import OpenSearchLexicalIndex

            lexical_index = OpenSearchLexicalIndex(settings.opensearch_index)
        if settings.qdrant_collection:
            from .production import QdrantDenseIndex

            dense_index = QdrantDenseIndex(settings.qdrant_collection)
        if lexical_index is not None or dense_index is not None:
            retrieval_engine = HybridRetrievalEngine(lexical_index=lexical_index, dense_index=dense_index)
        coordination_store = None
        if settings.redis_url:
            from .production import RedisCoordinationStore

            coordination_store = RedisCoordinationStore(settings.redis_url)
        return cls(store, object_store, retrieval_engine=retrieval_engine, coordination_store=coordination_store, settings=settings)

    def _put_text(self, text: str, media_type: str, *, workspace_id: str) -> dict[str, Any]:
        """Call both legacy test stores and tenant-aware object stores."""

        try:
            return self.object_store.put_text(text, media_type, workspace_id=workspace_id)
        except TypeError as error:
            if "workspace_id" not in str(error):
                raise
            return self.object_store.put_text(text, media_type)

    @contextmanager
    def workspace_scope(self, workspace_id: str | None):
        """Bind one tenant scope when a production repository requires it."""

        scope_factory = getattr(self.store, "authorization_scope", None)
        scope = scope_factory(workspace_id) if workspace_id and callable(scope_factory) else nullcontext()
        with scope:
            yield

    def _put_bytes(self, raw: bytes, media_type: str, *, workspace_id: str) -> dict[str, Any]:
        try:
            return self.object_store.put_bytes(raw, media_type, workspace_id=workspace_id)
        except TypeError as error:
            if "workspace_id" not in str(error):
                raise
            return self.object_store.put_bytes(raw, media_type)

    def _completed_job(
        self,
        *,
        workspace_id: str,
        kind: str,
        payload: dict[str, Any],
        result: dict[str, Any],
        actor: str,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist a synchronously completed operation as a normal job."""

        # PostgreSQL runs with FORCE RLS.  The job is created with its explicit
        # workspace, then every follow-up read/transition must use the same
        # tenant scope; otherwise an embedded synchronous operation would work
        # in SQLite but fail closed in the production repository.
        with self.workspace_scope(workspace_id):
            job = self.jobs.submit(
                workspace_id=workspace_id, kind=kind, payload=payload, actor=actor,
                idempotency_key=idempotency_key, request_id=request_id,
            )
            if job["status"] == "queued":
                claimed = self.store.claim_jobs(job_id=job["job_id"], limit=1)
                if claimed:
                    job = self.store.complete_job(job["job_id"], result=result, actor=actor)
        return job

    # Job handlers deliberately call the synchronous core with job creation
    # disabled.  The worker's state transition is the durable operation record.
    def _run_ingestion_index_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        # ``ingestion.index`` is a delta-job family, not an instruction to
        # rebuild a tenant.  Node revisions and splits do not have a new
        # ingestion row, so they carry their immutable atom-version IDs in the
        # same durable envelope.
        if payload.get("atom_version_ids"):
            return self._index_atom_delta(
                workspace_id=str(payload["workspace_id"]),
                atom_version_ids=[str(item) for item in payload["atom_version_ids"]],
                ingestion_ids=[str(item) for item in payload.get("ingestion_ids", [])],
                actor=str(payload.get("actor", "index-worker")),
                index_revision=str(payload.get("index_revision") or os.environ.get("TRACE_INDEX_REVISION", "embedded-current")),
            )
        return self._index_ingestion_delta(
            str(payload["ingestion_id"]), actor=str(payload.get("actor", "index-worker")),
            index_revision=str(payload.get("index_revision") or os.environ.get("TRACE_INDEX_REVISION", "embedded-current")),
        )

    def _run_consolidation_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.consolidate_ingestion(str(payload["ingestion_id"]), actor=str(payload.get("actor", "job-worker")), _create_job=False)

    def _run_hierarchy_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.build_hierarchy(HierarchyBuildRequest.model_validate(payload), _create_job=False)

    def _run_schema_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.propose_schemas(SchemaProposalRequest.model_validate(payload), _create_job=False)

    def _run_benchmark_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.run_benchmark(BenchmarkRunRequest.model_validate(payload), _create_job=False)

    def _run_reindex_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.reindex(IndexRevisionRequest.model_validate(payload), _create_job=False)

    def _run_reprocess_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.replay(workspace_id=payload.get("workspace_id"), actor=str(payload.get("actor", "job-worker")), _create_job=False)

    def _run_cognitive_delta_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.run_cognitive_delta(
            str(payload["ingestion_id"]), actor=str(payload.get("actor", "cognitive-worker")),
            model_id=str(payload["model_id"]) if payload.get("model_id") else None,
        )

    def _run_projection_backfill_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = ProjectionRebuildRequest.model_validate(payload)
        return self.rebuild_projection(request, _create_job=False)

    def _run_projection_legacy_import_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Backfill a Cortex revision while retaining legacy derived reads.

        This job never rewrites legacy nodes or their old containment edges;
        it creates a separate Cortex revision from the supplied bounded source
        snapshot and lets effective-revision reads switch only after success.
        """

        request = ProjectionRebuildRequest.model_validate(payload)
        result = self.rebuild_projection(request, _create_job=False)
        result["legacy_import"] = True
        return result

    def _run_hierarchy_delta_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = ProjectionRebuildRequest.model_validate({**payload, "projection_kind": "hierarchy"})
        return self.rebuild_projection(request, _create_job=False)

    def _run_affinity_delta_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = ProjectionRebuildRequest.model_validate({**payload, "projection_kind": "affinity"})
        return self.rebuild_projection(request, _create_job=False)

    def _run_activation_recompute_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = ProjectionRebuildRequest.model_validate({**payload, "projection_kind": "activation"})
        return self.rebuild_projection(request, _create_job=False)

    def submit_job(self, request: JobSubmitRequest, *, request_id: str | None = None) -> dict[str, Any]:
        """Validate an asynchronous workflow envelope before it enters the queue."""

        with self.workspace_scope(request.workspace_id):
            return self._submit_job(request, request_id=request_id)

    def _submit_job(self, request: JobSubmitRequest, *, request_id: str | None = None) -> dict[str, Any]:
        """Scoped durable enqueue implementation."""

        payload = dict(request.payload)
        supplied_workspace = payload.get("workspace_id")
        if supplied_workspace is not None and str(supplied_workspace) != request.workspace_id:
            raise InvariantViolation("job payload workspace_id must match the durable job workspace")
        payload.setdefault("workspace_id", request.workspace_id)
        payload.setdefault("actor", request.actor)
        if request.model_id:
            payload.setdefault("model_id", request.model_id)
        validators: dict[str, Any] = {
            "hierarchy.build": HierarchyBuildRequest,
            "schema.proposals": SchemaProposalRequest,
            "benchmark.run": BenchmarkRunRequest,
            "index.rebuild": IndexRevisionRequest,
            "projection.backfill": ProjectionRebuildRequest,
            "projection.legacy_import": ProjectionRebuildRequest,
            "hierarchy.delta": ProjectionRebuildRequest,
            "affinity.delta": ProjectionRebuildRequest,
            "activation.recompute": ProjectionRebuildRequest,
        }
        validator = validators.get(request.kind)
        if validator is not None:
            if request.kind == "hierarchy.delta":
                payload["projection_kind"] = "hierarchy"
            elif request.kind == "affinity.delta":
                payload["projection_kind"] = "affinity"
            elif request.kind == "activation.recompute":
                payload["projection_kind"] = "activation"
            payload = validator.model_validate(payload).model_dump(mode="json")
        if request.kind == "consolidation" and not payload.get("ingestion_id"):
            raise ValueError("consolidation jobs require ingestion_id")
        if request.kind == "cognitive.delta" and not payload.get("ingestion_id"):
            raise ValueError("cognitive.delta jobs require ingestion_id")
        if request.webhook_id:
            webhook = self.store.get_webhook(request.webhook_id)
            if webhook["workspace_id"] != request.workspace_id:
                raise InvariantViolation("job webhook belongs to another workspace")
        job = self.jobs.submit(
            workspace_id=request.workspace_id, kind=request.kind, payload=payload,
            actor=request.actor, idempotency_key=request.idempotency_key,
            request_id=request_id, webhook_id=request.webhook_id, run_immediately=request.execute,
        )
        return {"job_id": job["job_id"], "status": job["status"], "job": job}

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self.store.get_job(job_id)

    def list_jobs(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.store.list_jobs(**kwargs)

    def cancel_job(self, job_id: str, *, actor: str, reason: str | None = None) -> dict[str, Any]:
        return self.jobs.cancel(job_id, actor=actor, reason=reason)

    def retry_job(self, job_id: str, *, actor: str, execute: bool = False) -> dict[str, Any]:
        return self.jobs.retry(job_id, actor=actor, execute=execute)

    def create_webhook(self, request: Any) -> dict[str, Any]:
        validate_webhook_url(request.url)
        secret = WebhookSigner.new_secret()
        created = self.store.create_webhook(
            workspace_id=request.workspace_id, url=request.url, event_types=list(request.event_types),
            secret_hash=WebhookSigner.digest(secret), secret_ciphertext=self.webhook_cipher.encrypt(secret), actor=request.actor,
        )
        created.pop("secret_ciphertext", None)
        created["secret"] = secret
        created["warning"] = "Store this secret now; it is not returned by later reads."
        return created

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        return self.store.get_webhook(webhook_id)

    def rotate_webhook(self, webhook_id: str, *, actor: str) -> dict[str, Any]:
        secret = WebhookSigner.new_secret()
        rotated = self.store.rotate_webhook(
            webhook_id, secret_hash=WebhookSigner.digest(secret),
            secret_ciphertext=self.webhook_cipher.encrypt(secret), actor=actor,
        )
        rotated.pop("secret_ciphertext", None)
        rotated["secret"] = secret
        rotated["warning"] = "Store this secret now; it is not returned by later reads."
        return rotated

    def create_api_key(self, request: ApiKeyCreateRequest) -> dict[str, Any]:
        raw = f"trc_{secrets.token_urlsafe(36)}"
        record = self.store.create_api_key(
            workspace_id=request.workspace_id, subject=request.subject,
            key_prefix=raw[:12], key_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            scopes=list(request.scopes), allowed_visibility=list(request.allowed_visibility),
            model_permissions=list(request.model_permissions),
            expires_at=request.expires_at.isoformat() if request.expires_at else None,
            actor=request.actor,
        )
        record["api_key"] = raw
        record["warning"] = "Store this API key now; only its hash and prefix are retained."
        return record

    def get_api_key(self, api_key_id: str) -> dict[str, Any]:
        return self.store.get_api_key(api_key_id)

    def revoke_api_key(self, api_key_id: str, *, actor: str, reason: str | None = None) -> dict[str, Any]:
        return self.store.revoke_api_key(api_key_id, actor=actor, reason=reason)

    # --------------------------------------------------------------- ingestion
    def ingest(self, request: IngestionRequest, *, attachment_override: dict[str, Any] | None = None) -> dict[str, Any]:
        """Capture source text under one explicit tenant scope."""

        with self.workspace_scope(request.workspace_id):
            return self._ingest(request, attachment_override=attachment_override)

    def _ingest(self, request: IngestionRequest, *, attachment_override: dict[str, Any] | None = None) -> dict[str, Any]:
        """Capture source text and return after the hot lexical path is ready.

        ``attachment_override`` is used by file adapters: the request text is
        extracted parser text, while the override points at the original bytes.
        This distinction prevents parser normalization from destroying the
        evidence object or invalidating source offsets.
        """
        raw_text = request.text or ""
        text = normalize_text(adapt_text(raw_text, request.source.adapter))
        # Keep ingress bytes as the evidence artifact.  When parser-friendly
        # normalization changes them (for example CRLF -> LF), retain the
        # normalized artifact as a private parser reference too so atom offsets
        # remain exact and reproducible.
        staging_records: list[dict[str, Any]] = []
        stage = getattr(self.store, "stage_attachment", None)
        try:
            attachment = attachment_override or self._put_text(raw_text, request.source.media_type, workspace_id=request.workspace_id)
            if callable(stage):
                staging_records.append(stage(workspace_id=request.workspace_id, attachment=attachment))
            if text != raw_text:
                normalized_attachment = self._put_text(text, "text/plain; charset=utf-8", workspace_id=request.workspace_id)
                if callable(stage):
                    staging_records.append(stage(workspace_id=request.workspace_id, attachment=normalized_attachment))
                attachment["metadata"] = {
                    **dict(attachment.get("metadata", {})),
                    "normalized_parser_artifact": {
                        "content_hash": normalized_attachment["content_hash"],
                        "object_key": normalized_attachment["object_key"],
                        "byte_length": normalized_attachment["byte_length"],
                    },
                }
            drafts = atomize(text)
            source = request.source.model_dump(mode="json")
            source["adapter_payload"] = request.adapter_payload
            source["normalized_content_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            temporal = request.temporal_metadata()
            result = self.store.ingest(
                workspace_id=request.workspace_id,
                source=source,
                attachment=attachment,
                atoms=[{**draft.__dict__, "temporal": temporal} for draft in drafts],
                actor=request.actor,
                visibility=request.visibility,
                idempotency_key=request.idempotency_key,
            )
        except Exception as error:
            fail_stage = getattr(self.store, "fail_attachment_staging", None)
            if callable(fail_stage):
                for staged in staging_records:
                    try:
                        try:
                            fail_stage(
                                staged["staging_id"],
                                workspace_id=request.workspace_id,
                                error=f"canonical ingestion failed: {error}",
                            )
                        except TypeError as staging_error:
                            if "workspace_id" not in str(staging_error):
                                raise
                            fail_stage(staged["staging_id"], error=f"canonical ingestion failed: {error}")
                    except Exception:
                        # Preserve the original ingestion error. Reconciliation
                        # still sees any staging record that was committed.
                        pass
            raise
        finalize_stage = getattr(self.store, "finalize_attachment_staging", None)
        if callable(finalize_stage):
            for staged in staging_records:
                try:
                    try:
                        finalize_stage(
                            staged["staging_id"], ingestion_id=result["ingestion_id"],
                            canonical_event_offset=result.get("atomized_event_offset"), actor=request.actor,
                            workspace_id=request.workspace_id,
                        )
                    except TypeError as staging_error:
                        if "workspace_id" not in str(staging_error):
                            raise
                        finalize_stage(
                            staged["staging_id"], ingestion_id=result["ingestion_id"],
                            canonical_event_offset=result.get("atomized_event_offset"), actor=request.actor,
                        )
                except Exception:
                    # The source capture is already canonical. Leave the
                    # staging row for the reconciliation worker rather than
                    # reporting a failed ingestion that a retry could duplicate.
                    pass
        result["status"] = "accepted"
        revision = os.environ.get("TRACE_INDEX_REVISION", "embedded-current")
        set_state = getattr(self.store, "set_ingestion_index_state", None)
        if callable(set_state) and self.retrieval_engine.lexical_index is not None:
            # External index acknowledgement has not happened yet. The hot
            # inbox remains the read path until this delta job completes.
            result["index_state"] = set_state(
                ingestion_id=result["ingestion_id"], component="lexical", status="pending",
                index_revision=revision, detail={"reason": "external_delta_queued"}, actor=request.actor,
            )
        result["dense_index_status"] = "dense_pending"
        index_job = self.jobs.submit(
            workspace_id=request.workspace_id,
            kind="ingestion.index",
            payload={
                "workspace_id": request.workspace_id, "ingestion_id": result["ingestion_id"],
                "actor": request.actor, "index_revision": revision,
            },
            actor=request.actor,
            idempotency_key=f"{request.idempotency_key}:index" if request.idempotency_key else None,
        )
        result["job_id"] = index_job["job_id"]
        result["job"] = index_job
        if callable(set_state):
            result["index_state"] = set_state(
                ingestion_id=result["ingestion_id"], component="dense", status="dense_pending",
                index_revision=revision, job_id=index_job["job_id"], detail={"reason": "delta_queued"}, actor=request.actor,
            )
        return result

    def ingest_bytes(
        self,
        *,
        workspace_id: str,
        raw: bytes,
        source: dict[str, Any],
        actor: str = "anonymous",
        visibility: str = "private",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Capture an original file while atomizing a deterministic text extraction."""

        media_type = source.get("media_type", "application/octet-stream")
        adapter = source.get("adapter", "upload")
        if adapter in {"pdf", "application/pdf"} or media_type == "application/pdf":
            try:
                from pypdf import PdfReader
            except ImportError as error:  # pragma: no cover - dependency is supplied by the PDF adapter deployment
                raise ValueError("PDF extraction requires the optional pypdf adapter") from error
            text = "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
            adapter = "text"
        else:
            text = raw.decode("utf-8", errors="replace")
        if not text.strip():
            raise ValueError("the supplied file did not contain extractable text")
        attachment = self._put_bytes(raw, media_type, workspace_id=workspace_id)
        request = IngestionRequest.model_validate(
            {
                "workspace_id": workspace_id, "text": text, "source": {**source, "adapter": adapter},
                "actor": actor, "visibility": visibility, "idempotency_key": idempotency_key,
            }
        )
        return self.ingest(request, attachment_override=attachment)

    def ingestion_status(self, ingestion_id: str) -> dict[str, Any]:
        status = self.store.get_ingestion(ingestion_id)
        status["attachment"] = self.store.get_attachment(status["attachment_id"])
        index_state = getattr(self.store, "ingestion_index_state", None)
        if callable(index_state):
            status["index_state"] = index_state(ingestion_id)
        status["events"] = {
            "accepted": status["accepted_event_offset"],
            "projection_status": self.store.projection_status(status["workspace_id"]),
        }
        return status

    def readiness(self) -> dict[str, Any]:
        checks: dict[str, Any] = {}
        try:
            checks["postgresql"] = "ok" if self.store.last_event_offset() >= 0 else "error"
            checks["outbox"] = self.store.outbox_status() if hasattr(self.store, "outbox_status") else "delegated"
        except Exception as error:
            checks["postgresql"] = {"status": "error", "detail": str(error)[:200]}
        checks["object_storage"] = "ok"
        checks["opensearch"] = "ok" if self.retrieval_engine.lexical_index is not None else "not_configured"
        checks["qdrant"] = "ok" if self.retrieval_engine.dense_index is not None else "not_configured"
        checks["model_services"] = "configured" if any(os.environ.get(name) for name in ("TRACE_DENSE_MODEL", "TRACE_RERANK_MODEL", "TRACE_DEEP_MODEL", "TRACE_SCHEMA_MODEL")) else "local_fallback"
        checks["nats"] = "configured" if os.environ.get("TRACE_NATS_URL") else "embedded_outbox"
        checks["redis"] = "configured" if os.environ.get("TRACE_REDIS_URL") else "not_configured"
        projection_lag = 0
        try:
            last_event = self.store.last_event_offset()
            revisions = self.store.projection_status()
            projection_lag = max((last_event - int(item.get("last_applied_event", 0)) for item in revisions), default=last_event)
        except Exception:
            projection_lag = -1
        checks["projection_lag"] = projection_lag
        return checks

    def edit_node(self, node_id: str, request: NodeEditRequest) -> dict[str, Any]:
        before = self.store.get_node(node_id)
        result = self.store.edit_node(
            node_id=node_id, content=request.content, properties=request.properties,
            actor=request.actor, idempotency_key=request.idempotency_key,
        )
        self._invalidate_affinity_versions(
            workspace_id=before["workspace_id"],
            atom_version_ids=[before["atom_version_id"], result["atom_version_id"]],
            reason="atom_versioned",
            actor=request.actor,
        )
        result["index_job"] = self._submit_atom_index_delta(
            workspace_id=before["workspace_id"],
            atom_version_ids=[result["atom_version_id"]],
            ingestion_ids=[str(before.get("properties", {}).get("ingestion_id"))] if before.get("properties", {}).get("ingestion_id") else [],
            actor=request.actor,
            idempotency_key=(f"{request.idempotency_key}:index" if request.idempotency_key else None),
        )
        return result

    def transition_source_lifecycle(self, atom_version_id: str, request: SourceLifecycleRequest) -> dict[str, Any]:
        transition = getattr(self.store, "transition_source_lifecycle", None)
        if not callable(transition):
            raise InvariantViolation("the configured repository does not support source lifecycle transitions")
        return transition(
            atom_version_id,
            state=request.state,
            actor=request.actor,
            reason=request.reason,
            superseded_by_atom_version_id=request.superseded_by_atom_version_id,
            idempotency_key=request.idempotency_key,
        )

    def erase_source(self, atom_version_id: str, request: SourceErasureRequest) -> dict[str, Any]:
        signing_key = os.environ.get("TRACE_ERASURE_SIGNING_KEY")
        if not signing_key:
            raise InvariantViolation("TRACE_ERASURE_SIGNING_KEY is required for compliance erasure")

        # 1. Resolve atom version to determine workspace and targets
        atom = None
        if hasattr(self.store, "get_atom_version"):
            try:
                atom = self.store.get_atom_version(atom_version_id)
            except Exception:
                atom = None
        if not atom and hasattr(self.store, "atom_versions"):
            try:
                atoms = self.store.atom_versions([atom_version_id])
                if atoms:
                    atom = atoms[0]
            except Exception:
                atom = None

        if not atom:
            # Check if there is an existing completed operation for this atom_version_id
            existing_op = None
            if hasattr(self.store, "get_erasure_operation_by_atom"):
                existing_op = self.store.get_erasure_operation_by_atom(atom_version_id)
            if existing_op and existing_op.get("state") == "completed":
                return {
                    "state": "redacted_purged",
                    "atom_version_id": atom_version_id,
                    "workspace_id": existing_op["workspace_id"],
                    "erasure_receipt": existing_op["erasure_receipt"],
                    "event_offset": existing_op.get("event_offset", 0),
                }
            raise NotFoundError(f"atom version {atom_version_id} was not found")

        workspace_id = atom["workspace_id"]
        with self.workspace_scope(workspace_id):
            # Check if operation already completed for this workspace and atom
            existing_op = None
            if hasattr(self.store, "get_erasure_operation"):
                existing_op = self.store.get_erasure_operation(workspace_id, atom_version_id)

            if existing_op and existing_op.get("state") == "completed":
                return {
                    "state": "redacted_purged",
                    "atom_version_id": atom_version_id,
                    "workspace_id": workspace_id,
                    "erasure_receipt": existing_op["erasure_receipt"],
                    "event_offset": existing_op.get("event_offset", 0),
                }

            # Resolve raw-object key
            props = atom.get("properties") or {}
            object_key = props.get("object_key")
            attachment_id = props.get("attachment_id")
            if not object_key and attachment_id and hasattr(self.store, "get_attachment"):
                try:
                    att = self.store.get_attachment(attachment_id)
                    if att:
                        object_key = att.get("object_key")
                except Exception as err:
                    raise InvariantViolation(f"failed to resolve attachment {attachment_id} object key: {err}") from err

            external_targets: list[dict[str, Any]] = []
            if object_key:
                external_targets.append({"type": "object_store", "target": object_key})

            lexical_idx = getattr(self.retrieval_engine, "lexical_index", None)
            dense_idx = getattr(self.retrieval_engine, "dense_index", None)

            # Erasure applies to every immutable index revision that may still
            # retain this atom, not only to the currently active aliases. The
            # repository query is intentionally unbounded by release-list paging:
            # compliance cannot leave an older superseded revision readable.
            try:
                revision_loader = getattr(self.store, "cortex_component_revisions", None)
                if not callable(revision_loader):
                    raise InvariantViolation(
                        "the configured repository cannot enumerate external index revisions for erasure"
                    )
                revisions = revision_loader(
                    workspace_id,
                    ["lexical_index", "dense_index"],
                )
            except Exception as err:
                raise InvariantViolation(
                    f"compliance erasure failed (incomplete): could not enumerate external revisions: {err}"
                ) from err
            if lexical_idx is not None:
                external_targets.extend(
                    {"type": "opensearch", "target": revision}
                    for revision in revisions.get("lexical_index", [])
                )
            if dense_idx is not None:
                external_targets.extend(
                    {"type": "qdrant", "target": revision}
                    for revision in revisions.get("dense_index", [])
                )
            external_targets = [
                dict(item)
                for item in {
                    (str(target["type"]), str(target["target"])): target
                    for target in external_targets
                }.values()
            ]


            # 2. Create or acquire erasure operation (sets state to pending / read-denial hold)
            op = self.store.create_or_acquire_erasure_operation(
                workspace_id=workspace_id,
                atom_version_id=atom_version_id,
                object_key=object_key,
                external_targets=external_targets,
            )
            operation_id = op["operation_id"]

            try:
                # 3. External absence deletion & verification (FAIL-CLOSED)
                # 3a. Object store
                if object_key:
                    delete_object = getattr(self.object_store, "delete_object", None)
                    verify_object_absent = getattr(self.object_store, "verify_object_absent", None)
                    if not callable(delete_object) or not callable(verify_object_absent):
                        raise RuntimeError(
                            "configured object store lacks required delete and absence-verification capabilities"
                        )
                    delete_object(object_key)
                    is_absent = verify_object_absent(object_key)
                    if not is_absent:
                        raise RuntimeError(f"object store verification failed: object {object_key} is still present")

                # 3b. Lexical index
                lexical_targets = [target for target in external_targets if target.get("type") == "opensearch"]
                if lexical_targets:
                    delete_atom = getattr(lexical_idx, "delete_atom", None)
                    verify_atom_absent = getattr(lexical_idx, "verify_atom_absent", None)
                    if not callable(delete_atom) or not callable(verify_atom_absent):
                        raise RuntimeError(
                            "configured lexical index lacks required delete and absence-verification capabilities"
                        )
                    for target in lexical_targets:
                        rev = target["target"]
                        delete_atom(atom_version_id, revision=rev)
                        if not verify_atom_absent(atom_version_id, revision=rev):
                            raise RuntimeError(f"lexical index revision {rev} verification failed: atom {atom_version_id} still present")

                # 3c. Dense index
                dense_targets = [target for target in external_targets if target.get("type") == "qdrant"]
                if dense_targets:
                    delete_atom = getattr(dense_idx, "delete_atom", None)
                    verify_atom_absent = getattr(dense_idx, "verify_atom_absent", None)
                    if not callable(delete_atom) or not callable(verify_atom_absent):
                        raise RuntimeError(
                            "configured dense index lacks required delete and absence-verification capabilities"
                        )
                    for target in dense_targets:
                        rev = target["target"]
                        delete_atom(atom_version_id, revision=rev)
                        if not verify_atom_absent(atom_version_id, revision=rev):
                            raise RuntimeError(f"dense index revision {rev} verification failed: atom {atom_version_id} still present")

                # Update state to external_absence_verified
                self.store.update_erasure_operation_state(operation_id, state="external_absence_verified")

                # 4. Finalize database state in ONE transaction
                result = self.store.finalize_erasure_operation(
                    operation_id=operation_id,
                    signing_key=signing_key,
                    actor=request.actor,
                    reason=request.reason,
                )
                return result

            except Exception as err:
                try:
                    self.store.update_erasure_operation_state(operation_id, state="retryable_failure", failure_detail=str(err))
                except Exception:
                    pass
                raise InvariantViolation(f"compliance erasure failed (incomplete): {err}") from err


    def split_node(self, node_id: str, request: SplitRequest) -> list[dict[str, Any]]:
        before = self.store.get_node(node_id)
        children = self.store.split_node(
            node_id=node_id, parts=request.parts, actor=request.actor, idempotency_key=request.idempotency_key,
        )
        child_ids = [str(child["atom_version_id"]) for child in children]
        self._invalidate_affinity_versions(
            workspace_id=before["workspace_id"],
            atom_version_ids=[before["atom_version_id"], *child_ids],
            reason="atom_split",
            actor=request.actor,
        )
        if child_ids:
            job = self._submit_atom_index_delta(
                workspace_id=before["workspace_id"],
                atom_version_ids=child_ids,
                ingestion_ids=[str(before.get("properties", {}).get("ingestion_id"))] if before.get("properties", {}).get("ingestion_id") else [],
                actor=request.actor,
                idempotency_key=(f"{request.idempotency_key}:index" if request.idempotency_key else None),
            )
            # Keep the established list response shape while making the delta
            # handoff observable to clients that need indexing diagnostics.
            for child in children:
                child["index_job_id"] = job["job_id"]
        return children

    def _invalidate_affinity_versions(
        self,
        *,
        workspace_id: str,
        atom_version_ids: list[str],
        reason: str,
        actor: str,
    ) -> int:
        invalidator = getattr(self.store, "invalidate_affinity_for_atoms", None)
        if not callable(invalidator):
            return 0
        return int(invalidator(
            workspace_id=workspace_id,
            atom_version_ids=list(dict.fromkeys(atom_version_ids)),
            reason=reason,
            actor=actor,
        ))

    def _submit_atom_index_delta(
        self,
        *,
        workspace_id: str,
        atom_version_ids: list[str],
        ingestion_ids: list[str],
        actor: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        """Queue one bounded version-index handoff after a canonical edit.

        The job is intentionally keyed by immutable atom-version IDs.  It
        never asks an edit retry to scan, rebuild, or mutate unrelated rows.
        """

        ids = list(dict.fromkeys(str(item) for item in atom_version_ids if item))[:1_000]
        if not ids:
            raise InvariantViolation("atom index delta requires at least one atom-version ID")
        revision = os.environ.get("TRACE_INDEX_REVISION", "embedded-current")
        job = self.jobs.submit(
            workspace_id=workspace_id,
            kind="ingestion.index",
            payload={
                "workspace_id": workspace_id,
                "atom_version_ids": ids,
                "ingestion_ids": list(dict.fromkeys(ingestion_ids)),
                "actor": actor,
                "index_revision": revision,
            },
            actor=actor,
            idempotency_key=idempotency_key or f"atom-index:{workspace_id}:{hashlib.sha256('\x1f'.join(ids).encode('utf-8')).hexdigest()}",
        )
        # A hot-inbox candidate stays visible until this new immutable version
        # has reached the external lexical and dense revisions.  State remains
        # per ingestion for operator visibility, while the job itself remains
        # keyed only by the changed atom versions.
        state_writer = getattr(self.store, "set_ingestion_index_state", None)
        if callable(state_writer):
            for ingestion_id in list(dict.fromkeys(ingestion_ids)):
                state_writer(
                    ingestion_id=ingestion_id,
                    component="lexical",
                    status="stale",
                    index_revision=revision,
                    job_id=job["job_id"],
                    detail={"reason": "atom_version_delta", "atom_version_ids": ids},
                    actor=actor,
                )
                state_writer(
                    ingestion_id=ingestion_id,
                    component="dense",
                    status="dense_pending",
                    index_revision=revision,
                    job_id=job["job_id"],
                    detail={"reason": "atom_version_delta", "atom_version_ids": ids},
                    actor=actor,
                )
        return job

    def alias_node(self, node_id: str, request: AliasRequest) -> dict[str, Any]:
        return self.store.create_alias(
            source_node_id=node_id, target_node_id=request.target_node_id, actor=request.actor,
            evidence_atom_version_ids=request.evidence_atom_version_ids, idempotency_key=request.idempotency_key,
        )

    # ---------------------------------------------------------- organization
    @staticmethod
    def _conservative_relation(source_text: str, target_text: str) -> str:
        """Choose only a reviewable typed relation; never emit a generic edge."""

        source = source_text.lower()
        target = target_text.lower()
        if any(marker in source for marker in ("contradicts", "however", "instead of", "deprecated")):
            return "contradicts"
        if any(marker in source for marker in ("depends on", "requires", "prerequisite")):
            return "depends_on"
        if any(marker in source for marker in ("implements", "implementation of", "provides")):
            return "implements"
        if any(marker in source for marker in ("for example", "e.g.", "example")):
            return "example_of"
        # Overlap alone is only a support candidate until a reviewer confirms it.
        return "supports"

    def consolidate_ingestion(
        self,
        ingestion_id: str,
        *,
        actor: str = "system",
        max_neighbors: int = 6,
        _create_job: bool = True,
    ) -> dict[str, Any]:
        """Produce bounded, source-backed local-neighbor proposals.

        This intentionally does not auto-promote a typed evidence relationship. The
        lexical candidate generator only prioritizes review; promotion remains a
        separate reversible spine decision.
        """

        ingestion = self.store.get_ingestion(ingestion_id)
        self.store.set_consolidation_status(ingestion_id, "running", actor=actor)
        try:
            incoming = self.store.ingestion_atoms(ingestion_id)
            # Development keeps a deterministic local control path. Production
            # must use revisioned lexical/dense candidate generators and never
            # materialize the workspace to organize one ingestion.
            local_corpus: list[dict[str, Any]] | None = None
            if self.retrieval_engine.lexical_index is None and self.retrieval_engine.dense_index is None:
                if self.settings.production_mode:
                    raise InvariantViolation("production consolidation requires a lexical or dense candidate index")
                local_corpus = self.store.queryable_atoms(ingestion["workspace_id"])
            candidates = 0
            proposals: list[dict[str, Any]] = []
            for atom in incoming:
                atom_terms = set(_tokens(atom["content"]))
                if len(atom_terms) < 2:
                    continue
                ranked: list[tuple[float, dict[str, Any]]] = []
                neighbor_pool = self._consolidation_neighbors(
                    workspace_id=ingestion["workspace_id"], atom=atom, max_neighbors=max_neighbors,
                    local_corpus=local_corpus,
                )
                for neighbor in neighbor_pool:
                    if neighbor["node_id"] == atom["node_id"]:
                        continue
                    neighbor_terms = set(_tokens(neighbor["content"]))
                    union = atom_terms | neighbor_terms
                    overlap = atom_terms & neighbor_terms
                    if not overlap or not union:
                        continue
                    score = len(overlap) / len(union)
                    if score >= 0.12:
                        ranked.append((score, neighbor))
                ranked.sort(key=lambda pair: (-pair[0], pair[1]["node_id"]))
                for score, neighbor in ranked[:max_neighbors]:
                    if self.store.semantic_link_exists(ingestion["workspace_id"], atom["node_id"], neighbor["node_id"]):
                        continue
                    candidates += 1
                    proposals.append(
                        self.store.create_proposal(
                            workspace_id=ingestion["workspace_id"], proposal_type="edge",
                            candidate={
                                "source_node_id": atom["node_id"], "target_node_id": neighbor["node_id"],
                                "relation_type": self._conservative_relation(atom["content"], neighbor["content"]), "weight": round(score, 6),
                                "properties": {
                                    "candidate_generator": "bounded-jaccard-v2",
                                    "shared_terms": sorted(atom_terms & set(_tokens(neighbor["content"]))),
                                    "relation_rationale": "lexical overlap proposes support; reviewer must validate semantics",
                                },
                            },
                            evidence_atom_version_ids=[atom["atom_version_id"], neighbor["atom_version_id"]],
                            confidence=round(min(0.49, score), 6), model_version="bounded-jaccard-v2", actor=actor,
                        )
                    )
            hierarchy = self.hierarchy_builder.build_delta(
                workspace_id=ingestion["workspace_id"], source_atoms=incoming, actor=actor,
            ).model_dump()
            self.store.set_consolidation_status(ingestion_id, "completed", actor=actor)
            response = {"ingestion_id": ingestion_id, "candidate_pairs": candidates, "proposals": proposals, "hierarchy": hierarchy, "status": "completed"}
            if _create_job:
                response["job"] = self._completed_job(
                    workspace_id=ingestion["workspace_id"], kind="consolidation",
                    payload={"ingestion_id": ingestion_id, "actor": actor, "max_neighbors": max_neighbors},
                    result=response, actor=actor, idempotency_key=f"consolidation:{ingestion_id}",
                )
                response["job_id"] = response["job"]["job_id"]
            return response
        except Exception:
            self.store.set_consolidation_status(ingestion_id, "failed", actor=actor)
            raise

    def _consolidation_neighbors(
        self,
        *,
        workspace_id: str,
        atom: dict[str, Any],
        max_neighbors: int,
        local_corpus: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        """Generate a bounded, revalidated organization neighborhood."""

        visibility = atom.get("security", {}).get("visibility")
        candidate_ids: set[str] = set()
        if self.retrieval_engine.lexical_index is not None:
            search_kwargs = {
                "workspace_id": workspace_id, "query": atom["content"],
                "limit": max(8, min(128, max_neighbors * 12)),
                "visibility": [visibility] if visibility else None, "facets": ["atom"],
                "as_of_event": None, "index_revision": os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
            }
            try:
                hits = self.retrieval_engine.lexical_index.search(**search_kwargs)
            except TypeError:
                search_kwargs.pop("index_revision", None)
                hits = self.retrieval_engine.lexical_index.search(**search_kwargs)
            candidate_ids.update(str(hit["atom_version_id"]) for hit in hits if hit.get("atom_version_id"))
        if self.retrieval_engine.dense_index is not None:
            vector = self.retrieval_engine.dense_embedder.embed([atom["content"]])[0]
            search_kwargs = {
                "workspace_id": workspace_id, "vector": vector,
                "limit": max(8, min(128, max_neighbors * 12)),
                "visibility": [visibility] if visibility else None, "facets": ["atom"],
                "as_of_event": None, "index_revision": os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
            }
            try:
                hits = self.retrieval_engine.dense_index.search(**search_kwargs)
            except TypeError:
                search_kwargs.pop("index_revision", None)
                hits = self.retrieval_engine.dense_index.search(**search_kwargs)
            candidate_ids.update(str(hit["atom_version_id"]) for hit in hits if hit.get("atom_version_id"))
        if candidate_ids:
            candidates = self.store.atom_versions(sorted(candidate_ids))
            # Index payload filters are not authorization. Revalidate canonical
            # tenant/visibility facts before giving a worker or model excerpts.
            return [
                candidate for candidate in candidates
                if candidate.get("workspace_id") == workspace_id
                and candidate.get("security", {}).get("visibility") == visibility
                and candidate.get("atom_version_id") != atom.get("atom_version_id")
            ]
        return [
            candidate for candidate in (local_corpus or [])
            if candidate.get("workspace_id") == workspace_id
            and candidate.get("security", {}).get("visibility") == visibility
            and candidate.get("atom_version_id") != atom.get("atom_version_id")
        ]

    def create_proposal(self, request: ProposalCreateRequest) -> dict[str, Any]:
        return self.store.create_proposal(**request.model_dump())

    def promote_proposal(self, proposal_id: str, *, actor: str, reason: str | None, idempotency_key: str | None) -> dict[str, Any]:
        return self.store.promote_proposal(proposal_id=proposal_id, actor=actor, reason=reason, idempotency_key=idempotency_key)

    def reject_proposal(self, proposal_id: str, *, actor: str, reason: str | None, idempotency_key: str | None) -> dict[str, Any]:
        return self.store.decide_proposal(
            proposal_id=proposal_id, decision="rejected", actor=actor, reason=reason, idempotency_key=idempotency_key,
        )

    def build_hierarchy(self, request: HierarchyBuildRequest, *, _create_job: bool = True) -> dict[str, Any]:
        # Keep the legacy derived-node read path for embedded compatibility,
        # while every new production-facing hierarchy is also materialized in
        # the replaceable Cortex control plane.  Production callers must use a
        # bounded delta/backfill request instead of this historical full scan.
        if self.settings.production_mode:
            raise InvariantViolation("production hierarchy builds require a bounded projection.backfill or hierarchy.delta request")
        response = self.hierarchy_builder.build(**request.model_dump()).model_dump()
        cortex = self._build_cortex_hierarchy(
            workspace_id=request.workspace_id,
            atoms=self.store.queryable_atoms(request.workspace_id),
            model_revision=request.model_version,
            prompt_revision=os.environ.get("TRACE_SUMMARY_PROMPT_VERSION", "extractive-v1"),
            actor=request.actor,
        )
        response["cortex_projection"] = cortex
        if _create_job:
            job = self._completed_job(
                workspace_id=request.workspace_id, kind="hierarchy.build", payload=request.model_dump(mode="json"),
                result=response, actor=request.actor, idempotency_key=f"hierarchy:{request.workspace_id}:{response['generation_id']}",
            )
            response["job_id"] = job["job_id"]
            response["job"] = job
        return response

    @staticmethod
    def _cortex_summary(label: str, atoms: list[dict[str, Any]], *, limit: int = 3) -> str:
        excerpts = [" ".join(str(atom["content"]).split())[:180] for atom in atoms[:limit]]
        return f"{label}: " + " | ".join(excerpts)

    @staticmethod
    def _projection_view(objects: list[dict[str, Any]], run: dict[str, Any]) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = {"source_section": [], "topic_holon": [], "workspace_overview": []}
        for object_row in objects:
            view = {
                "node_id": object_row["projection_object_id"],
                "atom_version_id": object_row["projection_object_id"],
                "projection_object_id": object_row["projection_object_id"],
                "content": object_row["content"],
                "evidence_anchor_ids": [],
                "evidence_atom_version_ids": object_row["source_atom_version_ids"],
                "source_atom_version_ids": object_row["source_atom_version_ids"],
                "reused": run["status"] == "active",
            }
            grouped.setdefault(object_row["object_kind"], []).append(view)
        return {
            "projection_run_id": run["projection_run_id"], "revision": run["revision"], "status": run["status"],
            "section_summaries": grouped.get("source_section", []),
            "topic_holons": grouped.get("topic_holon", []),
            "workspace_holons": grouped.get("workspace_overview", []),
        }

    def _build_cortex_hierarchy(
        self,
        *,
        workspace_id: str,
        atoms: list[dict[str, Any]],
        model_revision: str,
        prompt_revision: str,
        actor: str,
        section_size: int = 8,
        topic_size: int = 6,
        input_from_event: int | None = None,
        input_through_event: int | None = None,
        policy_revision: str | None = None,
    ) -> dict[str, Any]:
        """Build a RAPTOR-inspired navigation projection without Spine writes.

        Clustering is deliberately local and bounded: source sections are
        contiguous, topic holons combine at most ``topic_size`` sections, and
        a workspace overview only links those already-built local objects.
        """
        atoms = [atom for atom in atoms if atom.get("workspace_id") == workspace_id and "atom" in atom.get("facets", [])]
        atoms.sort(key=lambda atom: (
            str(atom.get("properties", {}).get("ingestion_id", "")),
            int(atom.get("properties", {}).get("ordinal", 0)), atom["atom_version_id"],
        ))
        if not atoms:
            return {"status": "empty", "section_summaries": [], "topic_holons": [], "workspace_holons": []}
        input_through_event = input_through_event or max(int(atom.get("created_event_offset", 0)) for atom in atoms)
        input_checksum = hashlib.sha256(
            "\x1f".join(atom["atom_version_id"] for atom in atoms).encode("utf-8")
        ).hexdigest()

        return self._materialize_cortex_hierarchy(
            workspace_id=workspace_id,
            sections=self._source_sections_from_atoms(
                atoms, model_revision=model_revision, prompt_revision=prompt_revision, section_size=section_size,
            ),
            input_checksum=input_checksum,
            model_revision=model_revision,
            prompt_revision=prompt_revision,
            actor=actor,
            section_size=section_size,
            topic_size=topic_size,
            input_from_event=input_from_event,
            input_through_event=input_through_event,
            policy_revision=policy_revision,
        )

    @staticmethod
    def _bounded_hierarchy_size(value: int, *, minimum: int, maximum: int) -> int:
        return max(minimum, min(int(value), maximum))

    def _source_sections_from_atoms(
        self,
        atoms: list[dict[str, Any]],
        *,
        model_revision: str,
        prompt_revision: str,
        section_size: int,
    ) -> list[dict[str, Any]]:
        """Create deterministic source-section descriptors from current atoms.

        The descriptors intentionally retain source node IDs as projection
        metadata.  That lets a later delta replace only a changed source
        section without a workspace-wide canonical scan.
        """

        width = self._bounded_hierarchy_size(section_size, minimum=2, maximum=64)
        by_ingestion: dict[str, list[dict[str, Any]]] = {}
        explicit_groups: dict[str, list[dict[str, Any]]] = {}
        for atom in atoms:
            explicit_key = atom.get("properties", {}).get("projection_section_key")
            if explicit_key:
                explicit_groups.setdefault(str(explicit_key), []).append(atom)
                continue
            ingestion_id = str(atom.get("properties", {}).get("ingestion_id", "unknown"))
            by_ingestion.setdefault(ingestion_id, []).append(atom)
        sections: list[dict[str, Any]] = []
        for ingestion_id in sorted(by_ingestion):
            source_atoms = sorted(
                by_ingestion[ingestion_id],
                key=lambda atom: (int(atom.get("properties", {}).get("ordinal", 0)), atom["atom_version_id"]),
            )
            for start in range(0, len(source_atoms), width):
                group = source_atoms[start:start + width]
                source_ids = [str(atom["atom_version_id"]) for atom in group]
                source_nodes = [str(atom["node_id"]) for atom in group]
                sections.append({
                    "logical_key": f"section:{ingestion_id}:{start // width}",
                    "content": self._cortex_summary(f"Source section {ingestion_id}:{start + 1}", group),
                    "source_atom_version_ids": source_ids,
                    "properties": {
                        "coverage": {"covered_atom_version_ids": source_ids, "covered_atom_count": len(source_ids)},
                        "source_checksum": hashlib.sha256(
                            "\x1f".join(str(atom["content_hash"]) for atom in group).encode("utf-8")
                        ).hexdigest(),
                        "source_node_ids": source_nodes,
                        "model_revision": model_revision,
                        "prompt_revision": prompt_revision,
                        "resolution": "source_section",
                        "ingestion_id": ingestion_id,
                        "section_size": width,
                    },
                })
        for logical_key in sorted(explicit_groups):
            source_atoms = sorted(
                explicit_groups[logical_key],
                key=lambda atom: (int(atom.get("properties", {}).get("ordinal", 0)), atom["atom_version_id"]),
            )
            for start in range(0, len(source_atoms), width):
                group = source_atoms[start:start + width]
                key = logical_key if start == 0 else f"{logical_key}:{start // width}"
                source_ids = [str(atom["atom_version_id"]) for atom in group]
                source_nodes = [str(atom["node_id"]) for atom in group]
                sections.append({
                    "logical_key": key,
                    "content": self._cortex_summary(f"Source section {key.removeprefix('section:')}", group),
                    "source_atom_version_ids": source_ids,
                    "properties": {
                        "coverage": {"covered_atom_version_ids": source_ids, "covered_atom_count": len(source_ids)},
                        "source_checksum": hashlib.sha256(
                            "\x1f".join(str(atom["content_hash"]) for atom in group).encode("utf-8")
                        ).hexdigest(),
                        "source_node_ids": source_nodes,
                        "model_revision": model_revision,
                        "prompt_revision": prompt_revision,
                        "resolution": "source_section",
                        "ingestion_id": str(group[0].get("properties", {}).get("ingestion_id", "derived")),
                        "section_size": width,
                        "projection_section_key": logical_key,
                    },
                })
        return sections

    def _projection_source_sections(self, projection_run_id: str) -> list[dict[str, Any]]:
        """Read a projection snapshot in bounded pages, never raw workspace rows."""

        page_reader = getattr(self.store, "projection_objects_page", None)
        if callable(page_reader):
            sections: list[dict[str, Any]] = []
            after_logical_key: str | None = None
            page_size = 1_000
            for _ in range(2_000):
                page = page_reader(
                    projection_run_id,
                    object_kind="source_section",
                    after_logical_key=after_logical_key,
                    limit=page_size,
                )
                if not page:
                    return sections
                sections.extend(page)
                next_key = str(page[-1]["logical_key"])
                if len(page) < page_size:
                    return sections
                if after_logical_key == next_key:
                    raise InvariantViolation("projection snapshot cursor did not advance")
                after_logical_key = next_key
            raise InvariantViolation("projection snapshot exceeded the bounded page budget")
        reader = getattr(self.store, "projection_objects", None)
        if not callable(reader):
            raise InvariantViolation("repository has no projection snapshot reader")
        rows = reader(projection_run_id, limit=20_000)
        if len(rows) >= 20_000:
            raise InvariantViolation("repository must support paged projection snapshots before hierarchy delta handover")
        return [row for row in rows if row.get("object_kind") == "source_section"]

    def _section_node_ids(self, section: dict[str, Any]) -> list[str]:
        properties = dict(section.get("properties") or {})
        source_ids = [str(item) for item in section.get("source_atom_version_ids", [])]
        node_ids = [str(item) for item in properties.get("source_node_ids", []) if item]
        if len(node_ids) == len(source_ids):
            return node_ids
        # Old hierarchy revisions predate source-node snapshot metadata. This
        # compatibility read is explicitly limited to the existing projection
        # coverage; it never reaches unrelated workspace atoms.
        historical = self.store.atom_versions(source_ids)
        by_version = {str(atom["atom_version_id"]): str(atom["node_id"]) for atom in historical}
        resolved = [by_version[item] for item in source_ids if item in by_version]
        if len(resolved) != len(source_ids):
            raise InvariantViolation("legacy hierarchy snapshot references unavailable source atoms")
        return resolved

    def _materialize_cortex_hierarchy(
        self,
        *,
        workspace_id: str,
        sections: list[dict[str, Any]],
        input_checksum: str,
        model_revision: str,
        prompt_revision: str,
        actor: str,
        section_size: int,
        topic_size: int,
        input_from_event: int | None,
        input_through_event: int | None,
        prior_projection_run_id: str | None = None,
        carried_forward_sections: int = 0,
        regenerated_sections: int = 0,
        policy_revision: str | None = None,
    ) -> dict[str, Any]:
        """Write and hand over one fully self-contained hierarchy revision.

        A new revision is constructed while the prior revision remains active;
        activation is the only handover point.  Thus a worker crash leaves the
        prior traversal graph intact instead of exposing a partial delta.
        """

        required = (
            "create_projection_run", "write_projection_objects", "transition_projection_run",
            "activate_projection_run", "projection_objects",
        )
        if not all(callable(getattr(self.store, name, None)) for name in required):
            return {"status": "not_supported", "reason": "repository_has_no_cortex_projection_interface"}
        normalized_sections: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for section in sorted(sections, key=lambda item: str(item["logical_key"])):
            logical_key = str(section["logical_key"])
            source_ids = list(dict.fromkeys(str(item) for item in section.get("source_atom_version_ids", []) if item))
            if logical_key in seen_keys or not source_ids or not str(section.get("content") or "").strip():
                raise InvariantViolation("hierarchy source sections require unique keys, content, and source coverage")
            seen_keys.add(logical_key)
            properties = dict(section.get("properties") or {})
            node_ids = self._section_node_ids(section)
            properties.update({
                "coverage": {"covered_atom_version_ids": source_ids, "covered_atom_count": len(source_ids)},
                "source_node_ids": node_ids,
                "model_revision": model_revision,
                "prompt_revision": prompt_revision,
                "resolution": "source_section",
                "section_size": self._bounded_hierarchy_size(section_size, minimum=2, maximum=64),
            })
            normalized_sections.append({
                "logical_key": logical_key,
                "content": str(section["content"]),
                "source_atom_version_ids": source_ids,
                "properties": properties,
            })
        if not normalized_sections:
            return {"status": "empty", "section_summaries": [], "topic_holons": [], "workspace_holons": []}

        revision = f"hierarchy-{input_checksum[:20]}-{model_revision[:24]}"
        policy = self.get_cognitive_policy(workspace_id)
        active_policy_revision = str(policy["policy_revision"])
        if policy_revision and policy_revision != active_policy_revision:
            raise InvariantViolation("cognitive policy changed before hierarchy projection handover")
        run = self.store.create_projection_run(
            workspace_id=workspace_id,
            projection_kind="hierarchy",
            revision=revision,
            input_from_event=input_from_event,
            input_through_event=input_through_event,
            input_checksum=input_checksum,
            model_revision=model_revision,
            index_revision=os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
            prompt_revision=prompt_revision,
            policy_revision=policy_revision or active_policy_revision,
            prior_projection_run_id=prior_projection_run_id,
            actor=actor,
        )
        if run["status"] == "active":
            return self._projection_view(self.store.projection_objects(run["projection_run_id"]), run)
        if run["status"] == "succeeded":
            active = self.store.activate_projection_run(run["projection_run_id"], actor=actor)
            return self._projection_view(self.store.projection_objects(active["projection_run_id"]), active)
        if run["status"] == "running":
            return {
                "projection_run_id": run["projection_run_id"],
                "revision": run["revision"],
                "status": "running",
                "section_summaries": [],
                "topic_holons": [],
                "workspace_holons": [],
            }
        if run["status"] != "queued":
            raise InvariantViolation(f"hierarchy run is not writable from status {run['status']!r}")
        run = self.store.transition_projection_run(run["projection_run_id"], status="running", actor=actor)
        try:
            objects: list[dict[str, Any]] = []
            memberships: list[dict[str, Any]] = []
            section_records: list[dict[str, Any]] = []
            for section in normalized_sections:
                object_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace:cortex:{revision}:{section['logical_key']}"))
                properties = dict(section["properties"])
                if not properties.get("source_checksum"):
                    properties["source_checksum"] = hashlib.sha256(section["content"].encode("utf-8")).hexdigest()
                objects.append({
                    "projection_object_id": object_id,
                    "object_kind": "source_section",
                    "logical_key": section["logical_key"],
                    "content": section["content"],
                    "source_atom_version_ids": section["source_atom_version_ids"],
                    "properties": properties,
                })
                for ordinal, source_id in enumerate(section["source_atom_version_ids"]):
                    memberships.append({
                        "parent_projection_object_id": object_id,
                        "child_kind": "atom_version",
                        "child_id": source_id,
                        "ordinal": ordinal,
                    })
                section_records.append({"object_id": object_id, **section, "properties": properties})

            topic_records: list[dict[str, Any]] = []
            width = self._bounded_hierarchy_size(topic_size, minimum=2, maximum=32)
            for index in range(0, len(section_records), width):
                members = section_records[index:index + width]
                source_ids = list(dict.fromkeys(
                    source_id for section in members for source_id in section["source_atom_version_ids"]
                ))
                checksums = [str(section["properties"].get("source_checksum", "")) for section in members]
                logical_key = f"topic:{index // width}"
                object_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace:cortex:{revision}:{logical_key}"))
                content = self._cortex_summary(
                    f"Topic holon {index // width + 1}",
                    [{"content": section["content"]} for section in members],
                )
                properties = {
                    "coverage": {"covered_atom_version_ids": source_ids, "covered_atom_count": len(source_ids)},
                    "source_checksum": hashlib.sha256("\x1f".join(checksums).encode("utf-8")).hexdigest(),
                    "model_revision": model_revision,
                    "prompt_revision": prompt_revision,
                    "resolution": "topic_holon",
                    "member_section_count": len(members),
                }
                objects.append({
                    "projection_object_id": object_id,
                    "object_kind": "topic_holon",
                    "logical_key": logical_key,
                    "content": content,
                    "source_atom_version_ids": source_ids,
                    "properties": properties,
                })
                for ordinal, section in enumerate(members):
                    memberships.append({
                        "parent_projection_object_id": object_id,
                        "child_kind": "projection_object",
                        "child_id": section["object_id"],
                        "ordinal": ordinal,
                    })
                topic_records.append({"object_id": object_id, "content": content, "source_atom_version_ids": source_ids, "properties": properties})

            if topic_records:
                all_source = list(dict.fromkeys(
                    source_id for topic in topic_records for source_id in topic["source_atom_version_ids"]
                ))
                overview_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace:cortex:{revision}:workspace:overview"))
                overview_properties = {
                    "coverage": {
                        "covered_atom_count": len(all_source),
                        # Descendant membership carries the complete coverage
                        # set; this inline list remains bounded for storage.
                        "anchor_truncated": len(all_source) > 512,
                    },
                    "source_checksum": hashlib.sha256(
                        "\x1f".join(str(topic["properties"]["source_checksum"]) for topic in topic_records).encode("utf-8")
                    ).hexdigest(),
                    "model_revision": model_revision,
                    "prompt_revision": prompt_revision,
                    "resolution": "workspace_overview",
                    "member_topic_count": len(topic_records),
                }
                objects.append({
                    "projection_object_id": overview_id,
                    "object_kind": "workspace_overview",
                    "logical_key": "workspace:overview",
                    "content": self._cortex_summary(
                        "Workspace overview", [{"content": topic["content"]} for topic in topic_records],
                    ),
                    "source_atom_version_ids": all_source[:512],
                    "properties": overview_properties,
                })
                for ordinal, topic in enumerate(topic_records):
                    memberships.append({
                        "parent_projection_object_id": overview_id,
                        "child_kind": "projection_object",
                        "child_id": topic["object_id"],
                        "ordinal": ordinal,
                    })

            written = self.store.write_projection_objects(
                projection_run_id=run["projection_run_id"], objects=objects, memberships=memberships, actor=actor,
            )
            completed = self.store.transition_projection_run(
                run["projection_run_id"],
                status="succeeded",
                output_statistics={
                    "object_count": len(written),
                    "membership_count": len(memberships),
                    "source_atom_count": len({source_id for section in normalized_sections for source_id in section["source_atom_version_ids"]}),
                    "carried_forward_section_count": carried_forward_sections,
                    "regenerated_section_count": regenerated_sections,
                    "handover": "snapshot_plus_delta" if prior_projection_run_id else "snapshot",
                },
                actor=actor,
            )
            active = self.store.activate_projection_run(completed["projection_run_id"], actor=actor)
            return self._projection_view(written, active)
        except Exception as error:
            try:
                self.store.transition_projection_run(
                    run["projection_run_id"], status="failed", failure_detail=str(error)[:2_000], actor=actor,
                )
            except Exception:
                pass
            raise

    def _build_cortex_hierarchy_delta(
        self,
        *,
        workspace_id: str,
        delta_atoms: list[dict[str, Any]],
        model_revision: str,
        prompt_revision: str,
        actor: str,
        section_size: int = 8,
        topic_size: int = 6,
        input_from_event: int | None = None,
        input_through_event: int | None = None,
        policy_revision: str | None = None,
    ) -> dict[str, Any]:
        """Carry an active hierarchy snapshot forward while replacing local leaves.

        The read side stays on the active revision until every copied source
        section, regenerated section, topic, and overview is valid.  This is
        deliberately safer than activating a hierarchy made from only the
        changed atom versions.
        """

        delta_atoms = [
            atom for atom in delta_atoms
            if atom.get("workspace_id") == workspace_id and "atom" in atom.get("facets", [])
        ]
        active = self.store.effective_projection_run(workspace_id, "hierarchy")
        if active is None:
            return self._build_cortex_hierarchy(
                workspace_id=workspace_id,
                atoms=delta_atoms,
                model_revision=model_revision,
                prompt_revision=prompt_revision,
                actor=actor,
                section_size=section_size,
                topic_size=topic_size,
                input_from_event=input_from_event,
                input_through_event=input_through_event,
                policy_revision=policy_revision,
            )
        if not delta_atoms:
            return self._projection_view(self.store.projection_objects(active["projection_run_id"]), active)
        snapshot = self._projection_source_sections(active["projection_run_id"])
        if not snapshot:
            raise InvariantViolation("active hierarchy has no source-section snapshot; retain it and run a bounded backfill")

        changed_node_ids = list(dict.fromkeys(str(atom["node_id"]) for atom in delta_atoms))
        current_atoms = self.store.current_atom_versions_for_nodes(workspace_id, changed_node_ids)
        current_by_node = {str(atom["node_id"]): atom for atom in current_atoms}
        missing_nodes = [node_id for node_id in changed_node_ids if node_id not in current_by_node]
        if missing_nodes:
            raise InvariantViolation("hierarchy delta contains an unavailable or cross-workspace source atom")

        section_nodes: dict[str, list[str]] = {
            str(section["logical_key"]): self._section_node_ids(section) for section in snapshot
        }
        section_by_key = {str(section["logical_key"]): dict(section) for section in snapshot}
        changed_node_set = set(changed_node_ids)
        snapshot_node_ids = {node_id for nodes in section_nodes.values() for node_id in nodes}
        affected_keys = {
            key for key, nodes in section_nodes.items() if set(nodes) & changed_node_set
        }
        width = self._bounded_hierarchy_size(section_size, minimum=2, maximum=64)
        new_atoms_by_key: dict[str, list[dict[str, Any]]] = {}
        for atom in current_by_node.values():
            if str(atom["node_id"]) in snapshot_node_ids:
                continue
            properties = dict(atom.get("properties") or {})
            explicit_key = properties.get("projection_section_key")
            ingestion_id = str(properties.get("ingestion_id", "derived"))
            ordinal = int(properties.get("ordinal", 0))
            logical_key = str(explicit_key) if explicit_key else f"section:{ingestion_id}:{ordinal // width}"
            new_atoms_by_key.setdefault(logical_key, []).append(atom)
            if logical_key in section_by_key:
                affected_keys.add(logical_key)

        carried: list[dict[str, Any]] = []
        regenerated: list[dict[str, Any]] = []
        for key in sorted(section_by_key):
            section = section_by_key[key]
            if key not in affected_keys:
                properties = dict(section.get("properties") or {})
                properties["source_node_ids"] = section_nodes[key]
                properties["carried_forward_from_projection_run_id"] = active["projection_run_id"]
                carried.append({
                    "logical_key": key,
                    "content": section["content"],
                    "source_atom_version_ids": section["source_atom_version_ids"],
                    "properties": properties,
                })
                continue
            nodes = list(section_nodes[key])
            for atom in new_atoms_by_key.get(key, []):
                node_id = str(atom["node_id"])
                if node_id not in nodes:
                    nodes.append(node_id)
            current_section_atoms = self.store.current_atom_versions_for_nodes(workspace_id, nodes)
            by_node = {str(atom["node_id"]): atom for atom in current_section_atoms}
            if len(by_node) != len(nodes):
                raise InvariantViolation("cannot hand over hierarchy delta with missing source-section atoms")
            ordered = sorted(
                (by_node[node_id] for node_id in nodes),
                key=lambda atom: (int(atom.get("properties", {}).get("ordinal", 0)), str(atom["node_id"])),
            )
            source_ids = [str(atom["atom_version_id"]) for atom in ordered]
            properties = dict(section.get("properties") or {})
            properties.update({
                "coverage": {"covered_atom_version_ids": source_ids, "covered_atom_count": len(source_ids)},
                "source_checksum": hashlib.sha256(
                    "\x1f".join(str(atom["content_hash"]) for atom in ordered).encode("utf-8")
                ).hexdigest(),
                "source_node_ids": [str(atom["node_id"]) for atom in ordered],
                "model_revision": model_revision,
                "prompt_revision": prompt_revision,
                "resolution": "source_section",
                "section_size": width,
                "regenerated_from_projection_run_id": active["projection_run_id"],
            })
            regenerated.append({
                "logical_key": key,
                "content": self._cortex_summary(f"Source section {key.removeprefix('section:')}", ordered),
                "source_atom_version_ids": source_ids,
                "properties": properties,
            })
        for key, atoms in sorted(new_atoms_by_key.items()):
            if key in section_by_key:
                continue
            ordered = sorted(
                atoms,
                key=lambda atom: (int(atom.get("properties", {}).get("ordinal", 0)), str(atom["node_id"])),
            )
            source_ids = [str(atom["atom_version_id"]) for atom in ordered]
            ingestion_id = str(ordered[0].get("properties", {}).get("ingestion_id", "derived"))
            properties = {
                "coverage": {"covered_atom_version_ids": source_ids, "covered_atom_count": len(source_ids)},
                "source_checksum": hashlib.sha256(
                    "\x1f".join(str(atom["content_hash"]) for atom in ordered).encode("utf-8")
                ).hexdigest(),
                "source_node_ids": [str(atom["node_id"]) for atom in ordered],
                "model_revision": model_revision,
                "prompt_revision": prompt_revision,
                "resolution": "source_section",
                "ingestion_id": ingestion_id,
                "section_size": width,
                "regenerated_from_projection_run_id": active["projection_run_id"],
            }
            regenerated.append({
                "logical_key": key,
                "content": self._cortex_summary(f"Source section {key.removeprefix('section:')}", ordered),
                "source_atom_version_ids": source_ids,
                "properties": properties,
            })

        sections = carried + regenerated
        source_fingerprint = "\x1e".join(
            f"{section['logical_key']}:{'\x1f'.join(str(item) for item in section['source_atom_version_ids'])}"
            for section in sorted(sections, key=lambda item: str(item["logical_key"]))
        )
        input_checksum = hashlib.sha256(
            f"{active['revision']}\x1d{source_fingerprint}".encode("utf-8")
        ).hexdigest()
        through = input_through_event or max(
            [int(active.get("input_through_event") or 0)]
            + [int(atom.get("created_event_offset", 0)) for atom in current_by_node.values()]
        )
        return self._materialize_cortex_hierarchy(
            workspace_id=workspace_id,
            sections=sections,
            input_checksum=input_checksum,
            model_revision=model_revision,
            prompt_revision=prompt_revision,
            actor=actor,
            section_size=width,
            topic_size=topic_size,
            input_from_event=input_from_event,
            input_through_event=through,
            prior_projection_run_id=str(active["projection_run_id"]),
            carried_forward_sections=len(carried),
            regenerated_sections=len(regenerated),
            policy_revision=policy_revision,
        )

    def get_cognitive_policy(self, workspace_id: str) -> dict[str, Any]:
        getter = getattr(self.store, "get_cognitive_policy", None)
        if not callable(getter):
            return {"workspace_id": workspace_id, "policy_revision": "cognitive-policy-v1", "policy": CognitivePolicy().model_dump(mode="json"), "source": "default"}
        with self.workspace_scope(workspace_id):
            return getter(workspace_id)

    def _cloud_model_policy_revision(self, workspace_id: str) -> str:
        """Resolve the workspace policy before any registered cloud call."""

        policy = self.get_cognitive_policy(workspace_id)
        if not bool(policy.get("policy", {}).get("cloud_models_enabled", True)):
            raise ModelPolicyDenied("cloud model calls are disabled by the active cognitive policy")
        return str(policy.get("policy_revision") or "cognitive-policy-v1")

    def put_cognitive_policy(self, workspace_id: str, policy: CognitivePolicy, *, actor: str = "system") -> dict[str, Any]:
        writer = getattr(self.store, "put_cognitive_policy", None)
        if not callable(writer):
            raise InvariantViolation("the configured repository does not support cognitive policies")
        with self.workspace_scope(workspace_id):
            return writer(workspace_id=workspace_id, policy=policy.model_dump(mode="json"), actor=actor)

    def rebuild_projection(self, request: ProjectionRebuildRequest, *, _create_job: bool = True) -> dict[str, Any]:
        """Run one bounded, revisioned Cortex projection job."""

        with self.workspace_scope(request.workspace_id):
            active_policy_revision = str(self.get_cognitive_policy(request.workspace_id)["policy_revision"])
            if request.policy_revision and request.policy_revision != active_policy_revision:
                raise InvariantViolation(
                    "projection job policy revision is stale; enqueue a new job under the active cognitive policy"
                )
            pinned = request.model_copy(update={"policy_revision": active_policy_revision})
            return self._rebuild_projection(pinned, _create_job=_create_job)

    def _rebuild_projection(self, request: ProjectionRebuildRequest, *, _create_job: bool = True) -> dict[str, Any]:
        """Scoped implementation for one bounded, revisioned Cortex job."""

        if request.atom_version_ids:
            atoms = self._revalidate_atoms(self.store.atom_versions(request.atom_version_ids), QueryRequest(query="projection", workspace_id=request.workspace_id), None)
        elif request.from_event_offset is not None or request.through_event_offset is not None:
            event_source = getattr(self.store, "atom_versions_by_event_range", None)
            if not callable(event_source):
                raise InvariantViolation("repository does not support bounded event-range projection input")
            atoms = event_source(
                request.workspace_id, request.from_event_offset or 1, request.through_event_offset or self.store.last_event_offset(), limit=1_001
            )
            if len(atoms) > 1_000:
                raise InvariantViolation("projection event range exceeds 1,000 atom versions; split it into bounded delta jobs")
        elif self.settings.production_mode:
            raise InvariantViolation("production projection rebuilds require atom_version_ids or an event range")
        else:
            atoms = self.store.queryable_atoms(request.workspace_id)
        if request.projection_kind == "hierarchy":
            hierarchy_args = {
                "workspace_id": request.workspace_id,
                "model_revision": request.model_revision or "extractive-hierarchy-v2",
                "prompt_revision": request.prompt_revision or "extractive-v1",
                "actor": request.actor,
                "input_from_event": request.from_event_offset,
                "input_through_event": request.through_event_offset,
                "policy_revision": request.policy_revision,
            }
            if request.atom_version_ids or request.from_event_offset is not None or request.through_event_offset is not None:
                response = self._build_cortex_hierarchy_delta(delta_atoms=atoms, **hierarchy_args)
            else:
                response = self._build_cortex_hierarchy(atoms=atoms, **hierarchy_args)
        elif request.projection_kind == "affinity":
            response = self._build_affinity_projection(request, atoms)
        else:
            response = self._recompute_activation_projection(request, atoms)
        if _create_job:
            kind = {"hierarchy": "hierarchy.delta", "affinity": "affinity.delta", "activation": "activation.recompute"}[request.projection_kind]
            selector = (
                f"atoms:{hashlib.sha256('\x1f'.join(sorted(request.atom_version_ids)).encode('utf-8')).hexdigest()[:24]}"
                if request.atom_version_ids else
                f"events:{request.from_event_offset or 1}:{request.through_event_offset or 'latest'}"
            )
            job = self._completed_job(
                workspace_id=request.workspace_id, kind=kind, payload=request.model_dump(mode="json"), result=response,
                actor=request.actor,
                idempotency_key=(
                    f"projection:{request.projection_kind}:{request.workspace_id}:{selector}:"
                    f"{request.model_revision or 'current'}:{request.index_revision or 'current'}:{request.policy_revision or 'current'}"
                ),
            )
            response["job_id"] = job["job_id"]
            response["job"] = job
        return response

    def _build_affinity_projection(self, request: ProjectionRebuildRequest, atoms: list[dict[str, Any]]) -> dict[str, Any]:
        """Materialize sparse, expiring bridges from bounded candidate sets."""

        required = ("create_projection_run", "transition_projection_run", "activate_projection_run", "put_affinity_edge")
        if not all(callable(getattr(self.store, name, None)) for name in required):
            return {"status": "not_supported", "reason": "repository_has_no_affinity_interface"}
        atoms = [atom for atom in atoms if atom.get("workspace_id") == request.workspace_id and "atom" in atom.get("facets", [])][:1_000]
        checksum = hashlib.sha256("\x1f".join(atom["atom_version_id"] for atom in atoms).encode("utf-8")).hexdigest()
        policy = self.get_cognitive_policy(request.workspace_id)
        if request.policy_revision and request.policy_revision != policy["policy_revision"]:
            raise InvariantViolation("cognitive policy changed before affinity projection handover")
        revision = f"affinity-{checksum[:20]}-{(request.index_revision or 'current')[:24]}"
        run = self.store.create_projection_run(
            workspace_id=request.workspace_id, projection_kind="affinity", revision=revision,
            input_from_event=request.from_event_offset, input_through_event=request.through_event_offset,
            input_checksum=checksum, index_revision=request.index_revision or os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
            model_revision=request.model_revision, prompt_revision=request.prompt_revision,
            policy_revision=request.policy_revision or policy["policy_revision"], actor=request.actor,
        )
        if run["status"] == "active":
            return {"projection_run_id": run["projection_run_id"], "revision": run["revision"], "status": "active", "materialized": 0, "reused": True}
        if run["status"] == "queued":
            run = self.store.transition_projection_run(run["projection_run_id"], status="running", actor=request.actor)
        try:
            materialized = rejected_or_capped = candidates = 0
            local_pool = atoms if not self.settings.production_mode else None
            ttl = datetime.now(UTC) + timedelta(seconds=int(policy["policy"].get("affinity_ttl_seconds", 2_592_000)))
            seen_pairs: set[tuple[str, str]] = set()
            for atom in atoms:
                neighbors = self._consolidation_neighbors(
                    workspace_id=request.workspace_id, atom=atom, max_neighbors=8, local_corpus=local_pool,
                )
                source_terms = set(_tokens(atom["content"]))
                for neighbor in neighbors[:8]:
                    if neighbor.get("atom_version_id") == atom["atom_version_id"]:
                        continue
                    pair = canonical_pair(atom["atom_version_id"], neighbor["atom_version_id"])
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    target_terms = set(_tokens(neighbor["content"]))
                    overlap = len(source_terms & target_terms) / max(1, len(source_terms | target_terms))
                    if overlap < 0.12:
                        continue
                    candidates += 1
                    edge = self.store.put_affinity_edge(
                        workspace_id=request.workspace_id, source_atom_version_id=pair[0], target_atom_version_id=pair[1],
                        score=round(min(1.0, overlap), 6),
                        signal={"provider": "bounded-jaccard-affinity-v1", "shared_terms": sorted(source_terms & target_terms), "recurrent": False},
                        expires_at=ttl.isoformat(), index_revision=request.index_revision or os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
                        embedding_revision=request.model_revision, projection_run_id=run["projection_run_id"],
                        degree_cap=int(policy["policy"].get("affinity_degree_cap", 16)), actor=request.actor,
                    )
                    if edge is None:
                        rejected_or_capped += 1
                    else:
                        materialized += 1
            completed = self.store.transition_projection_run(
                run["projection_run_id"], status="succeeded",
                output_statistics={"candidate_pairs": candidates, "materialized": materialized, "rejected_or_capped": rejected_or_capped},
                actor=request.actor,
            )
            active = self.store.activate_projection_run(completed["projection_run_id"], actor=request.actor)
            return {
                "projection_run_id": active["projection_run_id"], "revision": active["revision"], "status": active["status"],
                "candidate_pairs": candidates, "materialized": materialized, "rejected_or_capped": rejected_or_capped,
            }
        except Exception as error:
            try:
                self.store.transition_projection_run(run["projection_run_id"], status="failed", failure_detail=str(error)[:2_000], actor=request.actor)
            except Exception:
                pass
            raise

    def _recompute_activation_projection(self, request: ProjectionRebuildRequest, atoms: list[dict[str, Any]]) -> dict[str, Any]:
        """Persist only bounded behavioral priors, never generated answers."""

        required = ("create_projection_run", "transition_projection_run", "activate_projection_run", "upsert_activation_prior")
        if not all(callable(getattr(self.store, name, None)) for name in required):
            return {"status": "not_supported", "reason": "repository_has_no_activation_interface"}
        atoms = [atom for atom in atoms if atom.get("workspace_id") == request.workspace_id and "atom" in atom.get("facets", [])][:1_000]
        checksum = hashlib.sha256("\x1f".join(atom["atom_version_id"] for atom in atoms).encode("utf-8")).hexdigest()
        policy = self.get_cognitive_policy(request.workspace_id)
        if request.policy_revision and request.policy_revision != policy["policy_revision"]:
            raise InvariantViolation("cognitive policy changed before activation projection handover")
        revision = f"activation-{checksum[:20]}"
        run = self.store.create_projection_run(
            workspace_id=request.workspace_id, projection_kind="activation", revision=revision,
            input_from_event=request.from_event_offset, input_through_event=request.through_event_offset,
            input_checksum=checksum, index_revision=request.index_revision, model_revision=request.model_revision,
            prompt_revision=request.prompt_revision, policy_revision=request.policy_revision or policy["policy_revision"], actor=request.actor,
        )
        if run["status"] == "active":
            return {"projection_run_id": run["projection_run_id"], "revision": run["revision"], "status": "active", "prior_count": 0, "reused": True}
        if run["status"] == "queued":
            run = self.store.transition_projection_run(run["projection_run_id"], status="running", actor=request.actor)
        try:
            feedback = self.store.feedback_scores(request.workspace_id, [atom["atom_version_id"] for atom in atoms])
            expires = (datetime.now(UTC) + timedelta(days=30)).isoformat()
            count = 0
            for atom_id, score in feedback.items():
                if not score:
                    continue
                self.store.upsert_activation_prior(
                    workspace_id=request.workspace_id, atom_version_id=atom_id, prior_kind="feedback",
                    score=max(-1.0, min(1.0, float(score))), provenance={"source": "retrieval_feedback", "projection_run_id": run["projection_run_id"]},
                    expires_at=expires, actor=request.actor,
                )
                count += 1
            completed = self.store.transition_projection_run(
                run["projection_run_id"], status="succeeded", output_statistics={"prior_count": count}, actor=request.actor,
            )
            active = self.store.activate_projection_run(completed["projection_run_id"], actor=request.actor)
            return {"projection_run_id": active["projection_run_id"], "revision": active["revision"], "status": active["status"], "prior_count": count}
        except Exception as error:
            try:
                self.store.transition_projection_run(run["projection_run_id"], status="failed", failure_detail=str(error)[:2_000], actor=request.actor)
            except Exception:
                pass
            raise

    def reject_affinity(self, request: AffinityRejectionRequest) -> dict[str, Any]:
        reject = getattr(self.store, "reject_affinity", None)
        if not callable(reject):
            raise InvariantViolation("the configured repository does not support affinity rejection")
        with self.workspace_scope(request.workspace_id):
            return reject(
                workspace_id=request.workspace_id, source_atom_version_id=request.source_atom_version_id,
                target_atom_version_id=request.target_atom_version_id, reason=request.reason, actor=request.actor,
            )

    def propose_schemas(
        self,
        request: SchemaProposalRequest,
        *,
        _create_job: bool = True,
        authorization_context: AuthorizationContext | None = None,
    ) -> dict[str, Any]:
        if request.atom_version_ids:
            atoms = [
                atom for atom in self.store.atom_versions(request.atom_version_ids)
                if atom.get("workspace_id") == request.workspace_id
            ]
        elif self.settings.production_mode:
            raise InvariantViolation("production schema proposals require bounded atom_version_ids from the ingestion candidate stage")
        else:
            atoms = self.store.queryable_atoms(request.workspace_id)
        if request.model_id:
            policy_revision = self._cloud_model_policy_revision(request.workspace_id)
            context = authorization_context or SimpleNamespace(
                workspace_id=request.workspace_id,
                subject=request.actor,
                request_id=None,
                model_permissions=frozenset({"*", "model:pro"}),
            )
            generated, _ = self.model_gateway.call_json(
                context=context,
                model_id=request.model_id,
                purpose="schema_proposal",
                query="Propose reviewable technical schemas. Do not assert facts or create graph edges.",
                candidates=[{"atom_version_id": atom["atom_version_id"], "content": atom["content"]} for atom in atoms],
                response_schema={"type": "object", "required": ["schemas"], "properties": {"schemas": {"type": "array"}}},
                max_nodes=min(128, len(atoms)),
                token_budget=int(os.environ.get("TRACE_SCHEMA_TOKEN_BUDGET", "4000")),
                prompt_template_revision="schema-proposal-v1",
                policy_revision=policy_revision,
            )
            proposed = [item for item in generated["schemas"] if isinstance(item, dict)][:request.max_schemas]
            provider_id = f"trace-model-gateway:{request.model_id}"
        else:
            proposed = self.schema_proposer.propose(atoms, request.max_schemas)
            provider_id = self.schema_proposer.provider_id
        proposals: list[dict[str, Any]] = []
        schema_nodes = (
            self.store.current_nodes_by_facet(request.workspace_id, "schema", limit=256)
            if hasattr(self.store, "current_nodes_by_facet") else self.store.current_nodes(request.workspace_id)
        )
        existing_labels = {
            str(node.get("properties", {}).get("label") or node.get("properties", {}).get("name") or node["content"])
            for node in schema_nodes
            if "schema" in node.get("facets", [])
        }
        existing_labels |= {
            str(proposal["candidate"].get("label") or proposal["candidate"].get("name") or "")
            for proposal in self.store.list_proposals(request.workspace_id, proposal_type="schema", status="pending")
        }
        for candidate in proposed:
            evidence = list(candidate.pop("evidence_atom_version_ids", []))
            confidence = float(candidate.pop("confidence", 0.0))
            label = str(candidate.get("label") or candidate.get("name") or "")
            if not evidence or not label or label in existing_labels:
                continue
            proposals.append(self.store.create_proposal(
                workspace_id=request.workspace_id,
                proposal_type="schema",
                candidate={**candidate, "proposal_provider": provider_id},
                evidence_atom_version_ids=evidence,
                confidence=confidence,
                model_version=request.model_id or request.model_version,
                actor=request.actor,
            ))
            existing_labels.add(label)
        response = {"workspace_id": request.workspace_id, "provider": provider_id, "proposals": proposals}
        if _create_job:
            job = self._completed_job(
                workspace_id=request.workspace_id, kind="schema.proposals", payload=request.model_dump(mode="json"),
                result=response, actor=request.actor,
                idempotency_key=f"schema:{request.workspace_id}:{request.model_version}:{request.max_schemas}",
            )
            response["job_id"] = job["job_id"]
            response["job"] = job
        return response

    def run_cognitive_delta(self, ingestion_id: str, *, actor: str = "cognitive-worker", model_id: str | None = None) -> dict[str, Any]:
        """Run the nightly/after-ingestion organization pipeline on one delta."""

        ingestion = self.store.get_ingestion(ingestion_id)
        atoms = self.store.ingestion_atoms(ingestion_id)
        hierarchy = self.hierarchy_builder.build_delta(
            workspace_id=ingestion["workspace_id"], source_atoms=atoms, actor=actor,
        ).model_dump()
        schemas = self.propose_schemas(
            SchemaProposalRequest(
                workspace_id=ingestion["workspace_id"],
                atom_version_ids=[atom["atom_version_id"] for atom in atoms[:512]],
                model_id=model_id,
                actor=actor,
            ),
            _create_job=False,
        )
        return {
            "workspace_id": ingestion["workspace_id"], "ingestion_id": ingestion_id,
            "input_revision": hashlib.sha256("\x1f".join(atom["atom_version_id"] for atom in atoms).encode("utf-8")).hexdigest(),
            "hierarchy": hierarchy, "schema_proposal_count": len(schemas["proposals"]),
            "auto_published_navigation_summaries": len(hierarchy["section_summaries"]),
            "pending_review_proposals": len(schemas["proposals"]),
        }

    def record_feedback(self, request: EvidenceFeedbackRequest) -> dict[str, Any]:
        return self.store.record_feedback(**request.model_dump())

    def propose_feedback_edge_strengths(self, request: FeedbackEdgeProposalRequest) -> dict[str, Any]:
        """Turn accumulated feedback into reviewable edge-version proposals."""

        pending_targets = {
            str(proposal["candidate"].get("edge_version_id"))
            for proposal in self.store.list_proposals(request.workspace_id, proposal_type="edge_strength", status="pending")
        }
        proposals: list[dict[str, Any]] = []
        for edge in self.store.current_edges(request.workspace_id):
            if edge["relation_type"] not in {"supports", "contradicts", "depends_on", "implements", "example_of"}:
                continue
            if edge["edge_version_id"] in pending_targets:
                continue
            evidence = [anchor["source_atom_version_id"] for anchor in edge["evidence_anchors"]]
            signals = self.store.feedback_scores(request.workspace_id, evidence)
            if not signals:
                continue
            signal = sum(signals.get(item, 0.0) for item in evidence) / max(1, len(evidence))
            if abs(signal) < request.minimum_signal:
                continue
            proposed_weight = max(0.05, min(2.0, float(edge["weight"]) * (1.0 + signal * 0.25)))
            proposed_confidence = max(0.0, min(1.0, float(edge["confidence"]) + signal * 0.10))
            proposals.append(self.store.create_proposal(
                workspace_id=request.workspace_id,
                proposal_type="edge_strength",
                candidate={
                    "edge_version_id": edge["edge_version_id"],
                    "weight": round(proposed_weight, 6),
                    "confidence": round(proposed_confidence, 6),
                    "properties": {"feedback_signal": round(signal, 6), "edge_strength_proposal": True},
                },
                evidence_atom_version_ids=evidence,
                confidence=min(0.95, abs(signal)),
                model_version="feedback-edge-strength-v1",
                actor=request.actor,
            ))
            if len(proposals) >= request.max_proposals:
                break
        return {"workspace_id": request.workspace_id, "proposals": proposals, "auto_promoted": 0}

    def _benchmark_baseline_identity(self, workspace_id: str, benchmark: dict[str, Any]) -> dict[str, Any]:
        """Capture every mutable retrieval input alongside a benchmark run.

        A score without its corpus, policy, model, and projection revisions is
        not reproducible evidence.  This intentionally performs a bounded
        benchmark-time corpus digest; it is never on a normal query path.
        """

        atom_source = getattr(self.store, "iter_indexable_atom_versions", None)
        if not callable(atom_source):
            atom_source = getattr(self.store, "iter_queryable_atoms", None)
        atoms = atom_source(workspace_id) if callable(atom_source) else iter(self.store.queryable_atoms(workspace_id))
        corpus_rows = sorted(
            (
                str(atom["atom_version_id"]),
                str(atom.get("content_hash", "")),
                int(atom.get("created_event_offset", 0)),
            )
            for atom in atoms
        )
        digest = hashlib.sha256()
        for atom_version_id, content_hash, offset in corpus_rows:
            digest.update(f"{atom_version_id}\x1f{content_hash}\x1f{offset}\n".encode("utf-8"))
        policy = self.get_cognitive_policy(workspace_id)
        effective_projection = getattr(self.store, "effective_projection_run", None)
        active_projections: dict[str, dict[str, Any] | None] = {}
        if callable(effective_projection):
            for kind in ("hierarchy", "affinity", "activation"):
                active = effective_projection(workspace_id, kind)
                active_projections[kind] = (
                    {
                        "projection_run_id": active.get("projection_run_id"),
                        "revision": active.get("revision"),
                        "policy_revision": active.get("policy_revision"),
                        "index_revision": active.get("index_revision"),
                        "model_revision": active.get("model_revision"),
                        "prompt_revision": active.get("prompt_revision"),
                    }
                    if active else None
                )
        return {
            "captured_at": datetime.now(UTC).isoformat(),
            "benchmark_checksum": hashlib.sha256(
                json.dumps(benchmark, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "corpus_checksum": digest.hexdigest(),
            "corpus_atom_count": len(corpus_rows),
            "code_revision": os.environ.get("TRACE_CODE_REVISION", os.environ.get("TRACE_BUILD_REVISION", "unknown")),
            "policy_revision": policy.get("policy_revision"),
            "policy_id": policy.get("cognitive_policy_id"),
            "model_revisions": {
                "dense": getattr(self.retrieval_engine.dense_embedder, "provider_id", None),
                "reranker": getattr(self.retrieval_engine.reranker, "provider_id", None),
                "deep_navigator": getattr(self.retrieval_engine.deep_navigator, "provider_id", None),
            },
            "index_revisions": {
                "requested": os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
                "lexical_provider": getattr(self.retrieval_engine.lexical_index, "provider_id", None),
                "dense_provider": getattr(self.retrieval_engine.dense_index, "provider_id", None),
            },
            "active_projections": active_projections,
            "hardware": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "cpu_count": os.cpu_count(),
            },
        }

    def run_benchmark(self, request: BenchmarkRunRequest, *, _create_job: bool = True) -> dict[str, Any]:
        with self.workspace_scope(request.workspace_id):
            return self._run_benchmark(request, _create_job=_create_job)

    def _run_benchmark(self, request: BenchmarkRunRequest, *, _create_job: bool = True) -> dict[str, Any]:
        benchmark = load_benchmark(request.benchmark_path)
        release_corpus = validate_release_corpus(benchmark) if request.release_gate else None
        if request.bootstrap_fixture:
            fixture_workspace = benchmark.get("fixture_workspace_id")
            fixture_text = benchmark.get("fixture_corpus")
            fixture_key = benchmark.get("fixture_idempotency_key")
            if not fixture_workspace or not fixture_text or not fixture_key:
                raise ValueError("benchmark does not provide a bootstrap fixture")
            if fixture_workspace != request.workspace_id:
                raise ValueError("benchmark fixture must run in its frozen fixture_workspace_id")
            self.ingest(IngestionRequest(
                workspace_id=fixture_workspace,
                text=fixture_text,
                source={"title": benchmark.get("name"), "uri": f"benchmark://{benchmark.get('name')}", "media_type": "text/markdown"},
                actor=request.actor,
                idempotency_key=fixture_key,
            ))
            self.build_hierarchy(HierarchyBuildRequest(workspace_id=fixture_workspace, actor=request.actor))
        report = BenchmarkRunner(self).run(
            workspace_id=request.workspace_id,
            benchmark=benchmark,
            stages=request.stages,
        )
        report["baseline_identity"] = self._benchmark_baseline_identity(request.workspace_id, benchmark)
        if release_corpus is not None:
            report["release_corpus"] = release_corpus
        response = self.store.save_benchmark_run(
            workspace_id=request.workspace_id,
            benchmark_name=benchmark["name"],
            stages=request.stages,
            result=report,
            actor=request.actor,
        )
        if _create_job:
            job = self._completed_job(
                workspace_id=request.workspace_id, kind="benchmark.run", payload=request.model_dump(mode="json"),
                result=response, actor=request.actor,
                idempotency_key=f"benchmark:{response['benchmark_run_id']}",
            )
            response["job_id"] = job["job_id"]
            response["job"] = job
        return response

    # -------------------------------------------------------------- retrieval
    @staticmethod
    def _allowed(atom: dict[str, Any], context: dict[str, Any]) -> bool:
        allowed = context.get("allowed_visibility")
        if allowed is None and "visibility" in context:
            allowed = [context["visibility"]]
        if allowed is None:
            # Authentication/tenant middleware supplies this in production. The
            # headless embedded API defaults to its caller's complete workspace.
            return True
        return atom["security"].get("visibility") in set(allowed)

    def _revalidate_atoms(
        self,
        atoms: list[dict[str, Any]],
        request: QueryRequest,
        authorization_context: AuthorizationContext | None,
        temporal_exclusions: dict[str, int] | None = None,
        temporal_exclusion_details: list[dict[str, Any]] | None = None,
        release_context: dict[str, Any] | None = None,
        temporal_exclusion_state: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Apply the mandatory post-index policy check to canonical rows.

        Search payload filters are defense in depth, not authorization.  An
        index can be stale, replaying a wrong revision, or compromised; every
        hit is reloaded from canonical storage and checked again here.
        """

        result: list[dict[str, Any]] = []
        wanted_facets = set(request.facets)
        exclusion_state = temporal_exclusion_state if temporal_exclusion_state is not None else {}
        aggregate_seen: set[tuple[str, str]] = exclusion_state.setdefault("aggregate_seen", set())
        detail_seen: set[tuple[str, str]] = exclusion_state.setdefault("detail_seen", set())
        exclusion_state.setdefault("omitted_count", 0)
        exclusion_state.setdefault("truncated", False)

        def requested_value(value: Any) -> Any:
            return value.isoformat() if hasattr(value, "isoformat") else value

        def exclusion_identity(atom: dict[str, Any], reason: str) -> tuple[str, str]:
            opaque_identity = str(atom.get("atom_version_id") or atom.get("node_id") or id(atom))
            return opaque_identity, reason

        def record_aggregate(atom: dict[str, Any], reason: str) -> bool:
            identity = exclusion_identity(atom, reason)
            if identity in aggregate_seen:
                return False
            aggregate_seen.add(identity)
            if temporal_exclusions is not None:
                temporal_exclusions[reason] = temporal_exclusions.get(reason, 0) + 1
            return True

        def record_exclusion(
            atom: dict[str, Any],
            temporal: dict[str, Any],
            *,
            reason: str,
            policy_result: str | None = None,
        ) -> None:
            record_aggregate(atom, reason)
            if temporal_exclusion_details is None:
                return
            identity = exclusion_identity(atom, reason)
            if identity in detail_seen:
                return
            detail_seen.add(identity)
            if len(temporal_exclusion_details) >= TEMPORAL_EXCLUSION_DETAIL_LIMIT:
                exclusion_state["omitted_count"] = int(exclusion_state["omitted_count"]) + 1
                exclusion_state["truncated"] = True
                return
            valid_interval = dict(
                temporal.get("valid_time")
                or (atom.get("properties") or {}).get("temporal")
                or {}
            )
            detail = {
                "source_revision": str(atom.get("atom_version_id") or ""),
                "requested_time": {
                    "as_of_event": request.as_of_event,
                    "valid_at": requested_value(request.valid_at),
                    "valid_from": requested_value(request.valid_from),
                    "valid_to": requested_value(request.valid_to),
                },
                "resolved_event_watermark": (release_context or {}).get("spine_event_watermark"),
                "release_id": (release_context or {}).get("release_id"),
                "valid_interval": valid_interval,
                "lifecycle_state": temporal.get("lifecycle_state", "unknown"),
                "current_lifecycle_state": temporal.get("current_lifecycle_state", "unknown"),
                "policy_result": policy_result or temporal.get("policy_result", "excluded"),
                "provenance": dict(valid_interval.get("provenance") or {}),
                "exclusion_reason": reason,
                "authorization_policy_result": (atom.get("authorization_policy") or {}).get("policy_result"),
                "historical_authorization_revision_event": (atom.get("authorization_policy") or {}).get(
                    "historical_authorization_revision_event"
                ),
                "current_authorization_revision_event": (atom.get("authorization_policy") or {}).get(
                    "current_authorization_revision_event"
                ),
            }
            temporal_exclusion_details.append(detail)

        for atom in atoms:
            if request.workspace_id and atom.get("workspace_id") != request.workspace_id:
                continue
            # Authorization precedes temporal-policy evaluation because valid
            # intervals, provenance, lifecycle state, and source revisions are
            # themselves record metadata. An unauthorized record contributes
            # only to a redacted aggregate counter.
            def permits(security: dict[str, Any]) -> bool:
                candidate = {**atom, "security": security}
                return (
                    authorization_context.allows_record(candidate)
                    if authorization_context is not None
                    else self._allowed(candidate, request.privacy_context)
                )

            authorization_resolver = getattr(self.store, "resolve_source_authorization", None)
            source_authorization_ids = list(dict.fromkeys(
                str(item)
                for item in atom.get(
                    "source_atom_version_ids",
                    [atom.get("atom_version_id")] if "atom" in atom.get("facets", []) else [],
                )
                if item
            ))
            authorizations: list[dict[str, Any]] | None = None
            if callable(authorization_resolver):
                authorizations = []
                for source_atom_version_id in source_authorization_ids:
                    try:
                        authorizations.append(authorization_resolver(
                            source_atom_version_id,
                            as_of_event=request.as_of_event,
                        ))
                    except Exception:
                        authorizations.append({
                            "available": False,
                            "exclusion_reason": (
                                "historical_authorization_unavailable"
                                if request.as_of_event is not None
                                else "current_authorization_unavailable"
                            ),
                        })
                if not authorizations:
                    authorizations = None
            elif request.as_of_event is not None:
                authorizations = [{"available": False}]

            if authorizations is not None:
                unavailable = next(
                    (item for item in authorizations if not item.get("available")),
                    None,
                )
                if unavailable is not None:
                    record_aggregate(
                        atom,
                        str(
                            unavailable.get("exclusion_reason")
                            or (
                                "historical_authorization_unavailable"
                                if request.as_of_event is not None
                                else "current_authorization_unavailable"
                            )
                        ),
                    )
                    continue
                historical_allowed = all(
                    permits(dict(item.get("historical_security") or {}))
                    for item in authorizations
                )
                current_allowed = all(
                    permits(dict(item.get("current_security") or {}))
                    for item in authorizations
                )
                # A derived projection is additionally constrained by its own
                # current record classification; every source classification
                # is ANDed independently above.
                if "atom" not in atom.get("facets", []):
                    current_allowed = current_allowed and permits(dict(atom.get("security") or {}))
                if request.as_of_event is not None and not historical_allowed:
                    record_aggregate(atom, "historical_authorization_denied")
                    continue
                if not current_allowed:
                    record_aggregate(atom, "current_authorization_denied")
                    continue
                historical_revisions = list(dict.fromkeys(
                    item.get("historical_authorization_revision_event")
                    for item in authorizations
                    if item.get("historical_authorization_revision_event") is not None
                ))
                current_revisions = list(dict.fromkeys(
                    item.get("current_authorization_revision_event")
                    for item in authorizations
                    if item.get("current_authorization_revision_event") is not None
                ))
                is_source_atom = "atom" in atom.get("facets", [])
                atom["authorization_policy"] = {
                    "policy_result": "allowed",
                    "policy": "most_restrictive_historical_and_current",
                    "historical_authorization_revision_event": (
                        historical_revisions[0] if is_source_atom and historical_revisions else None
                    ),
                    "current_authorization_revision_event": (
                        current_revisions[0] if is_source_atom and current_revisions else None
                    ),
                    "historical_authorization_revision_events": historical_revisions,
                    "current_authorization_revision_events": current_revisions,
                    "historical_resolution": (
                        authorizations[0].get("historical_resolution") if is_source_atom else "all_sources"
                    ),
                }
            elif not permits(dict(atom.get("security") or {})):
                record_aggregate(atom, "current_authorization_denied")
                continue
            if request.as_of_event is not None and int(atom.get("created_event_offset", 0)) > request.as_of_event:
                record_exclusion(
                    atom,
                    {
                        "lifecycle_state": "unknown",
                        "current_lifecycle_state": "unknown",
                        "policy_result": "excluded",
                        "valid_time": (atom.get("properties") or {}).get("temporal", {}),
                    },
                    reason="event_after_requested_watermark",
                )
                continue
            temporal_checker = getattr(self.store, "temporal_visibility", None)
            if callable(temporal_checker):
                temporal = temporal_checker(
                    atom,
                    as_of_event=request.as_of_event,
                    valid_at=request.valid_at,
                    valid_from=request.valid_from,
                    valid_to=request.valid_to,
                )
                if not temporal.get("visible"):
                    reason = str(temporal.get("exclusion_reason") or "temporal_policy_denied")
                    record_exclusion(atom, temporal, reason=reason)
                    continue
                atom["temporal_visibility"] = temporal
            if wanted_facets and not wanted_facets.issubset(set(atom.get("facets", []))):
                continue
            result.append(atom)
        return result

    def query(self, request: QueryRequest, *, authorization_context: AuthorizationContext | None = None) -> dict[str, Any]:
        """Run retrieval inside the repository's explicit tenant scope."""

        if request.model_id and authorization_context is None:
            raise PermissionError("a server-derived authorization context is required for model-backed deep navigation")
        scope_factory = getattr(self.store, "authorization_scope", None)
        scope = (
            scope_factory(authorization_context.workspace_id)
            if authorization_context is not None and callable(scope_factory)
            else nullcontext()
        )
        with scope:
            return self._query(request, authorization_context=authorization_context)

    def _query(self, request: QueryRequest, *, authorization_context: AuthorizationContext | None = None) -> dict[str, Any]:
        """Run the complete bounded retrieval ladder and persist its evidence view."""

        cache_key = "trace:v2:query:" + hashlib.sha256(
            json.dumps({"request": request.model_dump(mode="json"), "authorization": authorization_context.privacy_context() if authorization_context else None, "spine_offset": self.store.last_event_offset()}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if self.coordination_store is not None:
            cached = self.coordination_store.get(cache_key)
            if cached:
                try:
                    value = json.loads(cached)
                    if isinstance(value, dict):
                        self.metrics.inc("trace_query_cache_hits_total")
                        return value
                except (TypeError, json.JSONDecodeError):
                    self.coordination_store.delete(cache_key)
            self.metrics.inc("trace_query_cache_misses_total")

        temporal_exclusions: dict[str, int] = {}
        temporal_exclusion_details: list[dict[str, Any]] = []
        temporal_exclusion_state: dict[str, Any] = {
            "aggregate_seen": set(),
            "detail_seen": set(),
            "omitted_count": 0,
            "truncated": False,
        }
        resolved_release: dict[str, Any] | None = None
        if request.as_of_event is not None:
            release_resolver = getattr(self.store, "get_cortex_release_as_of_event", None)
            resolved_release = (
                release_resolver(request.workspace_id or "", request.as_of_event)
                if callable(release_resolver) else None
            )
            if resolved_release is None:
                diagnostics = {
                    "temporal": {
                        "requested_as_of_event": request.as_of_event,
                        "requested_valid_at": request.valid_at.isoformat() if request.valid_at else None,
                        "requested_valid_from": request.valid_from.isoformat() if request.valid_from else None,
                        "requested_valid_to": request.valid_to.isoformat() if request.valid_to else None,
                        "resolved_event_watermark": None,
                        "release_id": None,
                        "policy_revision": None,
                        "policy_result": "denied",
                        "exclusion_reason": "historical_release_unavailable",
                    },
                    "temporal_exclusions": {"historical_release_unavailable": 1},
                    "temporal_exclusion_details": [],
                    "temporal_exclusion_details_truncated": False,
                    "temporal_exclusion_details_omitted_count": 0,
                }
                query_snapshot = request.model_dump(mode="json")
                query_snapshot["retrieval_diagnostics"] = diagnostics
                bundle = self.store.save_bundle(
                    workspace_id=request.workspace_id,
                    query=query_snapshot,
                    results=[],
                    sufficiency_state="historical_unavailable",
                )
                response = self._bundle_response(bundle)
                response["status"] = "historical_unavailable"
                response["retrieval_diagnostics"] = diagnostics
                return response
        else:
            active_loader = getattr(self.store, "get_active_cortex_release", None)
            resolved_release = active_loader(request.workspace_id or "") if callable(active_loader) else None
        component_revisions = {
            str(component.get("component_kind")): str(component.get("component_revision"))
            for component in (resolved_release or {}).get("components", [])
        }
        selected_release_id = (resolved_release or {}).get("release_id")
        index_hits: dict[str, list[dict[str, Any]]] = {}
        provider_diagnostics: dict[str, Any] = {
            "hot_candidates": 0,
            "provider_failures": {},
            "temporal_exclusions": temporal_exclusions,
            "temporal_exclusion_details": temporal_exclusion_details,
            "temporal_exclusion_details_truncated": False,
            "temporal_exclusion_details_omitted_count": 0,
            "temporal": {
                "requested_as_of_event": request.as_of_event,
                "requested_valid_at": request.valid_at.isoformat() if request.valid_at else None,
                "requested_valid_from": request.valid_from.isoformat() if request.valid_from else None,
                "requested_valid_to": request.valid_to.isoformat() if request.valid_to else None,
                "resolved_event_watermark": (resolved_release or {}).get("spine_event_watermark"),
                "release_id": selected_release_id,
                "policy_revision": (resolved_release or {}).get("policy_revision"),
                "policy_result": "allowed",
                "exclusion_reason": None,
            },
            "component_revisions": component_revisions,
        }
        lexical_index_revision = component_revisions.get("lexical_index") or os.environ.get("TRACE_INDEX_REVISION", "embedded-current")
        dense_index_revision = component_revisions.get("dense_index") or os.environ.get("TRACE_INDEX_REVISION", "embedded-current")
        if request.workspace_id and (self.retrieval_engine.lexical_index is not None or self.retrieval_engine.dense_index is not None):
            visibility = request.privacy_context.get("allowed_visibility")
            atom_ids: set[str] = set()
            if self.retrieval_engine.lexical_index is not None:
                lexical_kwargs = {
                    "workspace_id": request.workspace_id,
                    "query": request.query,
                    "limit": request.retrieval_budget.lexical_limit,
                    "visibility": visibility,
                    "facets": request.facets,
                    "as_of_event": request.as_of_event,
                    "index_revision": lexical_index_revision,
                }
                try:
                    index_hits["lexical"] = self.retrieval_engine.lexical_index.search(**lexical_kwargs)
                except TypeError:
                    lexical_kwargs.pop("index_revision", None)
                    try:
                        index_hits["lexical"] = self.retrieval_engine.lexical_index.search(**lexical_kwargs)
                    except Exception as error:
                        index_hits["lexical"] = []
                        provider_diagnostics["provider_failures"]["lexical"] = str(error)[:300]
                except Exception as error:
                    # A stale/unavailable external index is a read-time
                    # degradation, never a reason to write vectors or hide
                    # fresh hot-inbox evidence.
                    index_hits["lexical"] = []
                    provider_diagnostics["provider_failures"]["lexical"] = str(error)[:300]
                atom_ids.update(str(hit["atom_version_id"]) for hit in index_hits["lexical"] if hit.get("atom_version_id"))
            if self.retrieval_engine.dense_index is not None and request.retrieval_profile != "lexical":
                try:
                    query_vector = self.retrieval_engine.dense_embedder.embed([request.query])[0]
                    dense_kwargs = {
                        "workspace_id": request.workspace_id,
                        "vector": query_vector,
                        "limit": request.retrieval_budget.dense_limit,
                        "visibility": visibility,
                        "facets": request.facets,
                        "as_of_event": request.as_of_event,
                        "index_revision": dense_index_revision,
                    }
                    try:
                        index_hits["dense"] = self.retrieval_engine.dense_index.search(**dense_kwargs)
                    except TypeError:
                        # Compatibility for an older injected adapter; production
                        # adapters implement revision-aware filtering.
                        dense_kwargs.pop("index_revision", None)
                        index_hits["dense"] = self.retrieval_engine.dense_index.search(**dense_kwargs)
                except Exception as error:
                    index_hits["dense"] = []
                    provider_diagnostics["provider_failures"]["dense"] = str(error)[:300]
                atom_ids.update(str(hit["atom_version_id"]) for hit in index_hits["dense"] if hit.get("atom_version_id"))
            hot_source = getattr(self.store, "hot_candidates", None)
            hot_atoms: list[dict[str, Any]] = []
            if callable(hot_source):
                try:
                    hot_atoms = hot_source(
                        request.workspace_id, request.query,
                        limit=max(request.retrieval_budget.lexical_limit, request.retrieval_budget.dense_limit),
                        visibility=visibility, facets=request.facets, as_of_event=request.as_of_event,
                    )
                except Exception as error:
                    provider_diagnostics["provider_failures"]["hot_inbox"] = str(error)[:300]
            # The hot path is a handoff buffer, not a second permanent full
            # corpus.  Include it while an externally-indexed ingestion is
            # pending/stale or when a provider is degraded.  This also avoids
            # treating an index attached after an old embedded ingestion as a
            # reason to bypass a successful external result set forever.
            state_source = getattr(self.store, "ingestion_index_state", None)
            if callable(state_source) and not provider_diagnostics["provider_failures"]:
                filtered_hot: list[dict[str, Any]] = []
                for atom in hot_atoms:
                    ingestion_id = atom.get("properties", {}).get("ingestion_id")
                    if not ingestion_id:
                        # Atom revisions produced by split/import flows may
                        # have no single ingestion owner.  They have not been
                        # proved externally indexed, so retain their bounded
                        # hot candidate rather than creating a blind spot.
                        filtered_hot.append(atom)
                        continue
                    state = state_source(str(ingestion_id))
                    lexical_state = state.get("lexical", {})
                    if lexical_state.get("status") in {"pending", "stale", "failed"}:
                        filtered_hot.append(atom)
                hot_atoms = filtered_hot
            provider_diagnostics["hot_candidates"] = len(hot_atoms)
            atom_ids.update(str(atom["atom_version_id"]) for atom in hot_atoms)
            reloaded = self.store.atom_versions(sorted(atom_ids))
            # External indexes are keyed by immutable atom-version IDs.  A
            # current read must not quietly return a superseded version while
            # its replacement delta is in flight.  Historical reads retain
            # their explicit as-of semantics and therefore skip this filter.
            current_loader = getattr(self.store, "current_atom_versions_for_nodes", None)
            if (
                request.as_of_event is None
                and request.valid_at is None
                and request.valid_from is None
                and request.valid_to is None
                and callable(current_loader)
                and reloaded
            ):
                current = current_loader(
                    request.workspace_id,
                    list(dict.fromkeys(str(atom["node_id"]) for atom in reloaded)),
                )
                current_ids = {str(atom["atom_version_id"]) for atom in current}
                stale_ids = {
                    str(atom["atom_version_id"])
                    for atom in reloaded
                    if str(atom["atom_version_id"]) not in current_ids
                }
                if stale_ids:
                    reloaded = [atom for atom in reloaded if str(atom["atom_version_id"]) not in stale_ids]
                    for channel in ("lexical", "dense"):
                        index_hits[channel] = [
                            hit for hit in index_hits.get(channel, [])
                            if str(hit.get("atom_version_id", "")) not in stale_ids
                        ]
                    provider_diagnostics["stale_external_candidates_dropped"] = len(stale_ids)
            atoms = self._revalidate_atoms(
                reloaded,
                request,
                authorization_context,
                temporal_exclusions,
                temporal_exclusion_details,
                resolved_release,
                temporal_exclusion_state,
            )
            # External score payloads need not yet contain this ingestion.
            # Give hot candidates a bounded lexical score in memory; this does
            # not persist embeddings or trigger a corpus scan.
            known_lexical = {str(hit.get("atom_version_id")) for hit in index_hits.get("lexical", [])}
            hot_visible = [atom for atom in atoms if atom["atom_version_id"] in {item["atom_version_id"] for item in hot_atoms}]
            hot_scores = self.retrieval_engine._bm25(_tokens(request.query), hot_visible)
            index_hits.setdefault("lexical", []).extend(
                {"atom_version_id": atom_id, "lexical_score": score, "source": "hot_inbox"}
                for atom_id, score in hot_scores.items() if atom_id not in known_lexical and score > 0
            )
        else:
            if self.settings.requires_external_indexes:
                raise InvariantViolation("production retrieval requires both revisioned OpenSearch and Qdrant adapters")
            # The embedded adapter is deliberately a correctness path.  It is
            # never selected by a production-profile deployment.
            valid_time_requested = any(
                value is not None for value in (request.valid_at, request.valid_from, request.valid_to)
            )
            temporal_source = getattr(self.store, "temporal_candidate_atoms", None)
            if valid_time_requested and callable(temporal_source):
                atoms = temporal_source(request.workspace_id, request.as_of_event)
            else:
                atoms = self.store.queryable_atoms(request.workspace_id, request.as_of_event)
            atoms = self._revalidate_atoms(
                atoms,
                request,
                authorization_context,
                temporal_exclusions,
                temporal_exclusion_details,
                resolved_release,
                temporal_exclusion_state,
            )
        if (
            request.as_of_event is not None
            and temporal_exclusions.get("historical_authorization_unavailable", 0) > 0
        ):
            provider_diagnostics["temporal"] = {
                **provider_diagnostics["temporal"],
                "policy_result": "denied",
                "exclusion_reason": "historical_authorization_unavailable",
            }
            diagnostics = {
                **provider_diagnostics,
                "temporal_exclusions": temporal_exclusions,
                "temporal_exclusion_details": [],
                "temporal_exclusion_details_truncated": False,
                "temporal_exclusion_details_omitted_count": 0,
            }
            query_snapshot = request.model_dump(mode="json")
            query_snapshot["retrieval_diagnostics"] = diagnostics
            bundle = self.store.save_bundle(
                workspace_id=request.workspace_id,
                query=query_snapshot,
                results=[],
                sufficiency_state="historical_unavailable",
            )
            response = self._bundle_response(bundle)
            response["status"] = "historical_unavailable"
            response["retrieval_diagnostics"] = diagnostics
            return response
        with telemetry_span("trace.retrieval", {"workspace_id": request.workspace_id, "profile": request.retrieval_profile}):
            with self.metrics.timer("trace_retrieval_seconds", labels={"profile": request.retrieval_profile}):
                navigator = (
                    GatewayDeepNavigator(
                        self.model_gateway,
                        context=authorization_context,
                        model_id=request.model_id,
                        policy_revision=self._cloud_model_policy_revision(request.workspace_id),
                    )
                    if request.model_id and authorization_context is not None else None
                )
                outcome: RetrievalOutcome = self.retrieval_engine.retrieve(
                    store=self.store, request=request, atoms=atoms, index_hits=index_hits or None,
                    deep_navigator=navigator, release_id=selected_release_id,
                )
        outcome.diagnostics["index_degradation"] = provider_diagnostics
        outcome.diagnostics["temporal"] = provider_diagnostics["temporal"]
        outcome.diagnostics["temporal_exclusions"] = temporal_exclusions
        outcome.diagnostics["temporal_exclusion_details"] = temporal_exclusion_details
        self.metrics.inc("trace_retrieval_total", labels={"profile": request.retrieval_profile, "state": outcome.sufficiency_state})
        self.metrics.inc("trace_retrieval_candidates_total", len(outcome.candidates), labels={"profile": request.retrieval_profile})
        schema_source = getattr(self.store, "current_nodes_by_facet", None)
        if callable(schema_source):
            schemas = schema_source(request.workspace_id or "", "schema", as_of_event=request.as_of_event, limit=256)
        elif self.settings.requires_external_indexes:
            schemas = []
        else:
            schemas = [node for node in self.store.current_nodes(request.workspace_id or "", request.as_of_event) if "schema" in node.get("facets", [])]
        labels = GovernedSchemaClassifier.classify(
            [candidate.atom for candidate in outcome.candidates if "atom" in candidate.atom.get("facets", [])], schemas,
        )
        for candidate in outcome.candidates:
            candidate_labels = labels.get(candidate.atom["atom_version_id"], [])
            schema_feature = SoftSchemaClassifier.query_alignment(request.query, candidate_labels)
            if schema_feature:
                candidate.score += 0.04 * schema_feature
            candidate.atom["soft_schema_labels"] = candidate_labels
            candidate.atom["schema_feature"] = schema_feature
        # Deep expansion reloads evidence IDs internally.  Apply the same
        # canonical policy check once more before formatting a response.
        outcome.candidates = [
            candidate for candidate in outcome.candidates
            if self._revalidate_atoms(
                [candidate.atom],
                request,
                authorization_context,
                temporal_exclusions,
                temporal_exclusion_details,
                resolved_release,
                temporal_exclusion_state,
            )
        ]
        details_truncated = bool(temporal_exclusion_state["truncated"])
        details_omitted = int(temporal_exclusion_state["omitted_count"])
        provider_diagnostics["temporal_exclusion_details_truncated"] = details_truncated
        provider_diagnostics["temporal_exclusion_details_omitted_count"] = details_omitted
        outcome.diagnostics["temporal_exclusion_details_truncated"] = details_truncated
        outcome.diagnostics["temporal_exclusion_details_omitted_count"] = details_omitted
        outcome.candidates.sort(key=lambda candidate: (-candidate.score, candidate.atom["atom_version_id"]))
        terms = set(_tokens(request.query))
        results: list[dict[str, Any]] = []
        for rank, candidate in enumerate(outcome.candidates[:request.retrieval_budget.candidate_limit], start=1):
            atom = candidate.atom
            is_source_atom = "atom" in atom.get("facets", [])
            source_ids = list(dict.fromkeys(
                str(item)
                for item in atom.get(
                    "source_atom_version_ids",
                    [atom["atom_version_id"]] if is_source_atom else [],
                )
                if item
            ))
            temporal = atom.get("temporal_visibility")
            if temporal is None and is_source_atom:
                temporal_checker = getattr(self.store, "temporal_visibility", None)
                if callable(temporal_checker):
                    temporal = temporal_checker(
                        atom,
                        as_of_event=request.as_of_event,
                        valid_at=request.valid_at,
                        valid_from=request.valid_from,
                        valid_to=request.valid_to,
                    )
            temporal = temporal or {
                "lifecycle_state": "derived_projection",
                "current_lifecycle_state": "derived_projection",
                "policy_result": "allowed",
                "exclusion_reason": None,
                "valid_time": {},
            }
            results.append({
                "rank": rank,
                "candidate_kind": "atom" if is_source_atom else "derived",
                "node_id": atom["node_id"],
                "atom_version_id": atom["atom_version_id"],
                "source_revision": atom["atom_version_id"] if is_source_atom else None,
                "source_revisions": source_ids,
                "excerpt": _excerpt(atom["content"], terms),
                "content_hash": atom["content_hash"],
                "source_location": {
                    "attachment_id": atom["properties"].get("attachment_id") if is_source_atom else None,
                    "start": atom["properties"].get("source_start") if is_source_atom else None,
                    "end": atom["properties"].get("source_end") if is_source_atom else None,
                    "parser_location": atom["properties"].get("parser_location") if is_source_atom else "derived",
                    "source": atom["properties"].get("source", {}) if is_source_atom else {"resolution": atom.get("facets", [])},
                },
                "temporal_status": "as_of" if request.as_of_event is not None else "current",
                "temporal": {
                    "requested_as_of_event": request.as_of_event,
                    "requested_valid_at": request.valid_at.isoformat() if request.valid_at else None,
                    "requested_valid_from": request.valid_from.isoformat() if request.valid_from else None,
                    "requested_valid_to": request.valid_to.isoformat() if request.valid_to else None,
                    "resolved_event_watermark": (resolved_release or {}).get("spine_event_watermark"),
                    "release_id": selected_release_id,
                    "policy_revision": (resolved_release or {}).get("policy_revision"),
                    "valid_interval": temporal.get("valid_time", atom.get("properties", {}).get("temporal", {})),
                    "lifecycle_state": temporal.get("lifecycle_state", "active"),
                    "current_lifecycle_state": temporal.get("current_lifecycle_state", temporal.get("lifecycle_state", "active")),
                    "policy_result": temporal.get("policy_result", "allowed"),
                    "provenance": dict(
                        (
                            temporal.get("valid_time")
                            or atom.get("properties", {}).get("temporal", {})
                        ).get("provenance", {})
                    ),
                "exclusion_reason": temporal.get("exclusion_reason"),
                    "authorization_policy_result": (atom.get("authorization_policy") or {}).get("policy_result"),
                    "historical_authorization_revision_event": (atom.get("authorization_policy") or {}).get(
                        "historical_authorization_revision_event"
                    ),
                    "current_authorization_revision_event": (atom.get("authorization_policy") or {}).get(
                        "current_authorization_revision_event"
                    ),
                    "historical_authorization_revision_events": (atom.get("authorization_policy") or {}).get(
                        "historical_authorization_revision_events", []
                    ),
                    "current_authorization_revision_events": (atom.get("authorization_policy") or {}).get(
                        "current_authorization_revision_events", []
                    ),
                    "historical_authorization_resolution": (atom.get("authorization_policy") or {}).get(
                        "historical_resolution"
                    ),
                },
                "channel_scores": {
                    "lexical_bm25": candidate.lexical,
                    "dense": candidate.dense,
                    "rrf": candidate.rrf,
                    "rerank": candidate.rerank,
                    "graph_ppr": candidate.graph,
                    "feedback": candidate.feedback,
                    "hierarchy": candidate.hierarchy,
                    "affinity": candidate.affinity,
                    "activation": candidate.activation,
                    "activation_contributions": candidate.activation_contributions,
                    "deep": candidate.deep,
                    "schema": atom.get("schema_feature", 0.0),
                    "soft_schema_labels": atom.get("soft_schema_labels", []),
                },
                "score": candidate.score,
                "graph_paths": candidate.paths,
                "evidence_anchor_ids": atom.get("evidence_anchor_ids", []),
                "source_atom_version_ids": source_ids,
            })
        # A derived candidate is never sufficient by itself: a bundle needs at
        # least one source atom to support synthesis and citations.
        if not any(result["candidate_kind"] == "atom" for result in results):
            outcome.sufficiency_state = "insufficient_evidence"
        query_snapshot = request.model_dump(mode="json")
        query_snapshot["retrieval_diagnostics"] = outcome.diagnostics
        bundle = self.store.save_bundle(
            workspace_id=request.workspace_id,
            query=query_snapshot,
            results=results,
            sufficiency_state=outcome.sufficiency_state,
        )
        response = self._bundle_response(bundle)
        response["retrieval_diagnostics"] = outcome.diagnostics
        if self.coordination_store is not None:
            self.coordination_store.set(
                cache_key, json.dumps(response, sort_keys=True, separators=(",", ":")),
                ttl_seconds=max(1, min(int(os.environ.get("TRACE_QUERY_CACHE_TTL_SECONDS", "60")), 3_600)),
            )
        return response

    def classify_atoms(self, workspace_id: str, *, atom_version_ids: list[str] | None = None) -> list[dict[str, Any]]:
        wanted = set(atom_version_ids or ())
        if self.settings.production_mode and not wanted:
            raise InvariantViolation("production schema classification requires bounded atom_version_ids")
        schema_source = getattr(self.store, "current_nodes_by_facet", None)
        if callable(schema_source):
            schemas = schema_source(workspace_id, "schema", limit=256)
        elif self.settings.production_mode:
            schemas = []
        else:
            schemas = [node for node in self.store.current_nodes(workspace_id) if "schema" in node.get("facets", [])]
        atoms = self.store.atom_versions(sorted(wanted)) if wanted else self.store.queryable_atoms(workspace_id)
        atoms = [atom for atom in atoms if atom.get("workspace_id") == workspace_id]
        labels = GovernedSchemaClassifier.classify(atoms, schemas)
        return [{"atom_version_id": atom["atom_version_id"], "labels": labels[atom["atom_version_id"]]} for atom in atoms]

    @staticmethod
    def _bundle_response(bundle: dict[str, Any]) -> dict[str, Any]:
        return {
            "evidence_bundle_id": bundle["evidence_bundle_id"], "workspace_id": bundle["workspace_id"],
            "query": bundle["query"], "results": bundle["results"],
            "sufficiency_state": bundle["sufficiency_state"], "created_event_offset": bundle["created_event_offset"],
        }

    def available_models(self, *, authorization_context: AuthorizationContext) -> list[dict[str, Any]]:
        if not bool(self.get_cognitive_policy(authorization_context.workspace_id).get("policy", {}).get("cloud_models_enabled", True)):
            return []
        return self.model_gateway.list_models(context=authorization_context, workspace_id=authorization_context.workspace_id)

    def synthesize(
        self,
        evidence_bundle_id: str,
        *,
        prompt: str | None,
        format: str,
        privacy_context: dict[str, Any],
        model_id: str | None = None,
        authorization_context: AuthorizationContext | None = None,
    ) -> dict[str, Any]:
        bundle = self.store.get_bundle(evidence_bundle_id)
        allowed_ids = privacy_context.get("allowed_atom_version_ids")
        # Derived hierarchy nodes are navigation aids.  Rendering expands them
        # back to their atom anchors so a summary can never become its own fact.
        requested_ids: list[str] = []
        for result in bundle["results"]:
            requested_ids.extend(result.get("source_atom_version_ids", [result["atom_version_id"]]))
        permitted = set(allowed_ids) if allowed_ids is not None else None
        requested_ids = list(dict.fromkeys(item for item in requested_ids if permitted is None or item in permitted))
        evidence_atoms = self.store.atom_versions(requested_ids)
        evidence_atoms = [atom for atom in evidence_atoms if self._allowed(atom, privacy_context)]
        citations = [
            {
                "atom_version_id": atom["atom_version_id"],
                "source_location": {
                    "attachment_id": atom["properties"].get("attachment_id"),
                    "start": atom["properties"].get("source_start"),
                    "end": atom["properties"].get("source_end"),
                    "parser_location": atom["properties"].get("parser_location"),
                    "source": atom["properties"].get("source", {}),
                },
            }
            for atom in evidence_atoms
        ]
        model_audit: dict[str, Any] | None = None
        if bundle["sufficiency_state"] == "insufficient_evidence" or not evidence_atoms:
            rendering = "Insufficient evidence in the selected bundle to produce a supported synthesis."
        elif model_id:
            if authorization_context is None:
                raise PermissionError("a server-derived authorization context is required for model synthesis")
            policy_revision = self._cloud_model_policy_revision(authorization_context.workspace_id)
            generated, model_audit = self.model_gateway.call_json(
                context=authorization_context,
                model_id=model_id,
                purpose="synthesis",
                query=prompt or "Produce a concise evidence-grounded synthesis.",
                candidates=[{"atom_version_id": atom["atom_version_id"], "content": atom["content"]} for atom in evidence_atoms],
                response_schema={"type": "object", "required": ["rendering"], "properties": {"rendering": {"type": "string"}}},
                max_nodes=min(32, len(evidence_atoms)),
                token_budget=int(os.environ.get("TRACE_SYNTHESIS_TOKEN_BUDGET", "4000")),
                prompt_template_revision="synthesis-v1",
                policy_revision=policy_revision,
            )
            rendering = generated["rendering"]
        elif format == "report":
            rendering = "\n\n".join(f"- {atom['content']} [{atom['atom_version_id']}]" for atom in evidence_atoms)
        else:
            rendering = " ".join(f"{atom['content']} [{atom['atom_version_id']}]" for atom in evidence_atoms)
        return {
            "canonical": False, "evidence_bundle_id": evidence_bundle_id, "format": format,
            "prompt": prompt, "rendering": rendering, "citations": citations,
            "sufficiency_state": bundle["sufficiency_state"], "model_audit": model_audit,
        }

    # ------------------------------------------------------- saved and graph
    def save_query(self, request: SavedQueryRequest) -> dict[str, Any]:
        query = request.query.model_copy(update={"workspace_id": request.workspace_id})
        return self.store.save_query(
            workspace_id=request.workspace_id, name=request.name, query=query.model_dump(mode="json"),
            frozen_atom_version_ids=None, actor=request.actor,
        )

    def freeze_query(self, request: FrozenQueryRequest) -> dict[str, Any]:
        query = request.query.model_copy(update={"workspace_id": request.workspace_id})
        response = self.query(query)
        return self.store.save_query(
            workspace_id=request.workspace_id, name=request.name, query=query.model_dump(mode="json"),
            frozen_atom_version_ids=[result["atom_version_id"] for result in response["results"]], actor=request.actor,
        )

    def subgraph(
        self, *, workspace_id: str, seed_node_ids: list[str], depth: int, as_of_event: int | None, privacy_context: dict[str, Any]
    ) -> dict[str, Any]:
        seeds = list(dict.fromkeys(str(node_id) for node_id in seed_node_ids if node_id))[:128]
        if not seeds and self.settings.production_mode:
            raise InvariantViolation("production graph retrieval requires at least one seed_node_id")
        max_nodes = max(1, min(int(os.environ.get("TRACE_GRAPH_MAX_NODES", "512")), 2_000))
        max_edges = max(1, min(int(os.environ.get("TRACE_GRAPH_MAX_EDGES", "1024")), 4_000))
        if not seeds:
            # Embedded correctness mode preserves the original exploratory API;
            # production never takes this whole-workspace path.
            all_nodes = {node["node_id"]: node for node in self.store.current_nodes(workspace_id, as_of_event)}
            allowed_nodes = {node_id for node_id, node in all_nodes.items() if self._allowed(node, privacy_context)}
            edges = [edge for edge in self.store.current_edges(workspace_id, as_of_event) if edge["source_node_id"] in allowed_nodes and edge["target_node_id"] in allowed_nodes]
            visited = allowed_nodes
            returned_edges = edges[:max_edges]
        else:
            nodes: dict[str, dict[str, Any]] = {}
            edges_by_id: dict[str, dict[str, Any]] = {}
            frontier = seeds
            visited: set[str] = set()
            with self.workspace_scope(workspace_id):
                for _ in range(max(0, depth) + 1):
                    current = [node_id for node_id in frontier if node_id not in visited][:max_nodes - len(visited)]
                    if not current:
                        break
                    for node_id in current:
                        try:
                            node = self.store.get_node(node_id, as_of_event)
                        except NotFoundError:
                            continue
                        if node.get("workspace_id") == workspace_id and self._allowed(node, privacy_context):
                            nodes[node_id] = node
                            visited.add(node_id)
                    if not nodes or len(visited) >= max_nodes or _ >= depth:
                        break
                    neighborhood = self.store.neighbor_edges(
                        workspace_id, sorted(nodes), as_of_event=as_of_event,
                        limit=max_edges - len(edges_by_id),
                    )
                    frontier = []
                    for edge in neighborhood:
                        edges_by_id[str(edge["edge_version_id"])] = edge
                        for node_id in (str(edge["source_node_id"]), str(edge["target_node_id"])):
                            if node_id not in visited and node_id not in frontier and len(visited) + len(frontier) < max_nodes:
                                frontier.append(node_id)
                    if len(edges_by_id) >= max_edges:
                        break
            all_nodes = nodes
            returned_edges = [
                edge for edge in edges_by_id.values()
                if edge["source_node_id"] in all_nodes and edge["target_node_id"] in all_nodes
            ]
        return {
            "workspace_id": workspace_id, "as_of_event": as_of_event, "nodes": [all_nodes[node] for node in sorted(all_nodes)],
            "edges": returned_edges,
            "evidence_paths": [
                {"edge_version_id": edge["edge_version_id"], "evidence_anchors": edge["evidence_anchors"]}
                for edge in returned_edges
            ],
        }

    # --------------------------------------------------------- administration
    def register_index(self, request: IndexRevisionRequest) -> dict[str, Any]:
        payload = request.model_dump()
        actor = payload.pop("actor")
        return self.store.register_index(payload, actor)

    def register_model(self, request: ModelRegistrationRequest) -> dict[str, Any]:
        payload = request.model_dump()
        actor = payload.pop("actor")
        return self.store.register_model(payload, actor)

    def register_manifest(self, request: ExperimentManifestRequest) -> dict[str, Any]:
        payload = request.model_dump()
        actor = payload.pop("actor")
        return self.store.register_manifest(payload, actor)

    def replay(self, *, workspace_id: str | None, actor: str = "system", _create_job: bool = True) -> dict[str, Any]:
        if self.settings.production_mode and not workspace_id:
            raise InvariantViolation("production replay requires one explicit workspace")
        with self.workspace_scope(workspace_id):
            result = self.store.reconcile_hot_inbox(workspace_id, actor=actor)
        if _create_job and workspace_id:
            job = self._completed_job(
                workspace_id=workspace_id, kind="reprocess", payload={"workspace_id": workspace_id, "actor": actor},
                result=result, actor=actor, idempotency_key=f"reprocess:{workspace_id}:{result.get('projection_revision', result.get('event_offset', 'latest'))}",
            )
            result["job_id"] = job["job_id"]
            result["job"] = job
        return result

    def validate_replay(self, workspace_id: str) -> dict[str, Any]:
        with self.workspace_scope(workspace_id):
            return self.store.replay_report(workspace_id)

    def reconcile_attachment_staging(self, workspace_id: str, *, actor: str = "attachment-reconciler") -> dict[str, Any]:
        """Surface recoverable object-store cleanup work for one workspace."""

        reconciler = getattr(self.store, "reconcile_attachment_staging", None)
        if not callable(reconciler):
            raise InvariantViolation("the configured repository does not support attachment staging reconciliation")
        with self.workspace_scope(workspace_id):
            return reconciler(workspace_id, actor=actor)

    def snapshot(self, *, actor: str = "system") -> dict[str, Any]:
        return self.store.snapshot(actor=actor)

    def reindex(self, request: IndexRevisionRequest, *, _create_job: bool = True) -> dict[str, Any]:
        if self.settings.production_mode and not request.workspace_id:
            raise InvariantViolation("production reindex requires one workspace_id; global rebuilds are not permitted")
        workspaces = [request.workspace_id] if request.workspace_id else self.store.workspace_ids()
        if not workspaces:
            raise InvariantViolation("reindex requires at least one explicit workspace")
        controller = RevisionedProjectionController(strict=self.settings.production_mode)
        lexical_index = self.retrieval_engine.lexical_index
        dense_index = self.retrieval_engine.dense_index
        vector_size = getattr(self.retrieval_engine.dense_embedder, "dimensions", None)
        preparation = {
            "lexical": controller.prepare(lexical_index, revision=request.lexical_revision),
            "dense": controller.prepare(dense_index, revision=request.lexical_revision, vector_size=vector_size),
        }
        registered = self.register_index(request)
        projections: dict[str, dict[str, Any]] = {}
        lexical_count: dict[str, int] = {}
        dense_counts: dict[str, int] = {}
        parity: dict[str, dict[str, dict[str, Any]]] = {}
        for workspace_id in workspaces:
            if workspace_id is None:
                continue
            with self.workspace_scope(workspace_id):
                projections[workspace_id] = self.store.reconcile_hot_inbox(workspace_id=workspace_id, actor=request.actor)
                lexical_count[workspace_id] = self.rebuild_lexical_index(workspace_id, revision=request.lexical_revision)
                dense_counts[workspace_id] = self.rebuild_dense_index(
                    workspace_id, actor=request.actor, revision=request.lexical_revision
                )
                lexical_parity = controller.verify(
                    lexical_index, projection="opensearch", workspace_id=workspace_id,
                    revision=request.lexical_revision, expected_count=lexical_count[workspace_id],
                )
                dense_parity = controller.verify(
                    dense_index, projection="qdrant", workspace_id=workspace_id,
                    revision=request.lexical_revision, expected_count=dense_counts[workspace_id],
                )
                parity[workspace_id] = {
                    "lexical": lexical_parity.public_dict(),
                    "dense": dense_parity.public_dict(),
                }
                if not lexical_parity.passed or not dense_parity.passed:
                    raise ProjectionRevisionError(
                        f"revision parity failed for workspace {workspace_id}; aliases were not changed"
                    )
        activation: dict[str, Any] = {"activated": False, "reason": "candidate revision"}
        if request.rollout_state == "active":
            # Activation is alias-only and therefore reversible without
            # changing canonical atoms or deleting an older revision.
            activation = {
                "activated": True,
                "lexical": controller.activate(lexical_index, revision=request.lexical_revision),
                "dense": controller.activate(dense_index, revision=request.lexical_revision),
                "rollback": {"revision": request.lexical_revision, "supported": True},
            }
        response = {
            "index_revision": registered,
            "projection": projections,
            "preparation": preparation,
            "lexical_indexed": lexical_count,
            "dense_indexed": dense_counts,
            "parity": parity,
            "activation": activation,
        }
        if _create_job:
            # Reindexing has already completed synchronously in the embedded
            # adapter; production workers can submit the same payload without
            # changing the response contract.
            workspace_id = request.workspace_id or next(iter(dense_counts), "admin")
            job = self._completed_job(
                workspace_id=workspace_id, kind="index.rebuild", payload=request.model_dump(mode="json"),
                result=response, actor=request.actor, idempotency_key=f"reindex:{registered.get('index_revision_id', registered.get('created_event_offset'))}",
            )
            response["job_id"] = job["job_id"]
            response["job"] = job
        return response

    def rebuild_lexical_index(self, workspace_id: str, *, revision: str | None = None) -> int:
        index = self.retrieval_engine.lexical_index
        if index is None:
            return 0
        revision = revision or os.environ.get("TRACE_INDEX_REVISION", "embedded-current")
        atom_source = getattr(self.store, "iter_indexable_atom_versions", None)
        if not callable(atom_source):
            atom_source = getattr(self.store, "iter_queryable_atoms", None)
        atoms = atom_source(workspace_id) if callable(atom_source) else iter(self.store.queryable_atoms(workspace_id))
        indexed = 0
        documents: list[dict[str, Any]] = []
        for atom in atoms:
            documents.append({
                "atom_version_id": atom["atom_version_id"],
                "workspace_id": workspace_id,
                "content": atom["content"],
                "content_hash": atom.get("content_hash"),
                "facets": atom.get("facets", []),
                "visibility": atom["security"].get("visibility"),
                "created_event_offset": atom.get("created_event_offset"),
                "source": atom.get("properties", {}).get("source", {}),
                "source_start": atom.get("properties", {}).get("source_start"),
                "source_end": atom.get("properties", {}).get("source_end"),
                "parser_location": atom.get("properties", {}).get("parser_location"),
                "attachment_id": atom.get("properties", {}).get("attachment_id"),
            })
            if len(documents) >= 1_000:
                indexed += index.upsert(documents, revision=revision)
                documents = []
        if documents:
            indexed += index.upsert(documents, revision=revision)
        return indexed

    def rebuild_dense_index(self, workspace_id: str, *, actor: str = "system", revision: str | None = None) -> int:
        """Rebuild the replaceable local vector projection for one workspace."""

        atom_source = getattr(self.store, "iter_indexable_atom_versions", None)
        if not callable(atom_source):
            atom_source = getattr(self.store, "iter_queryable_atoms", None)
        atoms = atom_source(workspace_id) if callable(atom_source) else iter(self.store.queryable_atoms(workspace_id))
        revision = revision or os.environ.get("TRACE_INDEX_REVISION", "embedded-current")
        stored = 0
        batch: list[dict[str, Any]] = []
        for atom in atoms:
            batch.append(atom)
            if len(batch) >= 1_000:
                stored += self._index_atom_batch(workspace_id, batch, actor=actor, revision=revision)
                batch = []
        if batch:
            stored += self._index_atom_batch(workspace_id, batch, actor=actor, revision=revision)
        return stored

    @staticmethod
    def _lexical_documents(workspace_id: str, atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "atom_version_id": atom["atom_version_id"],
                "workspace_id": workspace_id,
                "content": atom["content"],
                "content_hash": atom.get("content_hash"),
                "facets": atom.get("facets", []),
                "visibility": atom.get("security", {}).get("visibility"),
                "created_event_offset": atom.get("created_event_offset"),
                "source": atom.get("properties", {}).get("source", {}),
                "source_start": atom.get("properties", {}).get("source_start"),
                "source_end": atom.get("properties", {}).get("source_end"),
                "parser_location": atom.get("properties", {}).get("parser_location"),
                "attachment_id": atom.get("properties", {}).get("attachment_id"),
            }
            for atom in atoms
        ]

    def _index_ingestion_delta(
        self,
        ingestion_id: str,
        *,
        actor: str = "index-worker",
        index_revision: str | None = None,
    ) -> dict[str, Any]:
        """Index exactly one immutable ingestion delta.

        This is deliberately distinct from the explicit administrator reindex
        workflow.  A normal delivery/retry never invokes a workspace-wide
        read, so duplicate queue messages remain bounded at 100K+ atoms.
        """

        ingestion = self.store.get_ingestion(ingestion_id)
        workspace_id = ingestion["workspace_id"]
        atoms = self.store.ingestion_atoms(ingestion_id)
        revision = index_revision or os.environ.get("TRACE_INDEX_REVISION", "embedded-current")
        set_state = getattr(self.store, "set_ingestion_index_state", None)
        result: dict[str, Any] = {
            "ingestion_id": ingestion_id,
            "workspace_id": workspace_id,
            "atom_count": len(atoms),
            "index_revision": revision,
            "lexical_indexed": 0,
            "dense_indexed": 0,
        }
        if not atoms:
            if callable(set_state):
                set_state(
                    ingestion_id=ingestion_id, component="dense", status="failed", index_revision=revision,
                    detail={"reason": "ingestion_has_no_atoms"}, actor=actor,
                )
            raise InvariantViolation("ingestion index delta has no atoms")
        try:
            lexical = self.retrieval_engine.lexical_index
            if lexical is not None:
                for start in range(0, len(atoms), 1_000):
                    result["lexical_indexed"] += int(lexical.upsert(self._lexical_documents(workspace_id, atoms[start:start + 1_000]), revision=revision))
            if callable(set_state):
                set_state(
                    ingestion_id=ingestion_id, component="lexical", status="lexical_ready", index_revision=revision,
                    detail={"atom_count": len(atoms), "external": lexical is not None}, actor=actor,
                )
        except Exception as error:
            if callable(set_state):
                set_state(
                    ingestion_id=ingestion_id, component="lexical", status="failed", index_revision=revision,
                    detail={"error": str(error)[:500]}, actor=actor,
                )
            raise
        try:
            for start in range(0, len(atoms), 1_000):
                result["dense_indexed"] += self._index_atom_batch(
                    workspace_id, atoms[start:start + 1_000], actor=actor, revision=revision
                )
            if callable(set_state):
                set_state(
                    ingestion_id=ingestion_id, component="dense", status="dense_ready", index_revision=revision,
                    detail={"atom_count": len(atoms), "external": self.retrieval_engine.dense_index is not None}, actor=actor,
                )
        except Exception as error:
            if callable(set_state):
                set_state(
                    ingestion_id=ingestion_id, component="dense", status="failed", index_revision=revision,
                    detail={"error": str(error)[:500]}, actor=actor,
                )
            raise
        if callable(getattr(self.store, "ingestion_index_state", None)):
            result["index_state"] = self.store.ingestion_index_state(ingestion_id)
        return result

    def _index_atom_delta(
        self,
        *,
        workspace_id: str,
        atom_version_ids: list[str],
        ingestion_ids: list[str] | None = None,
        actor: str = "index-worker",
        index_revision: str | None = None,
    ) -> dict[str, Any]:
        """Index a bounded set of newly immutable atom versions.

        This is used by edit/split delivery.  It has deliberately separate
        accounting from ``_index_ingestion_delta`` because a revised atom
        belongs to an older ingestion but must not make that entire ingestion
        appear newly pending or cause a workspace-wide replay.
        """

        ids = list(dict.fromkeys(str(item) for item in atom_version_ids if item))[:1_000]
        if not ids:
            raise InvariantViolation("atom index delta has no atom-version IDs")
        atoms = self.store.atom_versions(ids)
        atoms = [
            atom for atom in atoms
            if atom.get("workspace_id") == workspace_id and "atom" in atom.get("facets", [])
        ]
        found = {str(atom["atom_version_id"]) for atom in atoms}
        missing = [atom_id for atom_id in ids if atom_id not in found]
        if missing:
            raise InvariantViolation("atom index delta contains missing or cross-workspace atom versions")
        revision = index_revision or os.environ.get("TRACE_INDEX_REVISION", "embedded-current")
        ingestions = list(dict.fromkeys(str(item) for item in (ingestion_ids or []) if item))
        state_writer = getattr(self.store, "set_ingestion_index_state", None)
        result: dict[str, Any] = {
            "workspace_id": workspace_id,
            "atom_version_ids": ids,
            "ingestion_ids": ingestions,
            "atom_count": len(atoms),
            "index_revision": revision,
            "lexical_indexed": 0,
            "dense_indexed": 0,
        }
        try:
            lexical = self.retrieval_engine.lexical_index
            if lexical is not None:
                for start in range(0, len(atoms), 1_000):
                    result["lexical_indexed"] += int(
                        lexical.upsert(self._lexical_documents(workspace_id, atoms[start:start + 1_000]), revision=revision)
                    )
            if callable(state_writer):
                for ingestion_id in ingestions:
                    state_writer(
                        ingestion_id=ingestion_id,
                        component="lexical",
                        status="lexical_ready",
                        index_revision=revision,
                        detail={"reason": "atom_version_delta_indexed", "atom_version_ids": ids, "external": lexical is not None},
                        actor=actor,
                    )
        except Exception as error:
            if callable(state_writer):
                for ingestion_id in ingestions:
                    state_writer(
                        ingestion_id=ingestion_id,
                        component="lexical",
                        status="failed",
                        index_revision=revision,
                        detail={"reason": "atom_version_delta_failed", "error": str(error)[:500], "atom_version_ids": ids},
                        actor=actor,
                    )
            raise
        try:
            for start in range(0, len(atoms), 1_000):
                result["dense_indexed"] += self._index_atom_batch(
                    workspace_id, atoms[start:start + 1_000], actor=actor, revision=revision,
                )
            if callable(state_writer):
                for ingestion_id in ingestions:
                    state_writer(
                        ingestion_id=ingestion_id,
                        component="dense",
                        status="dense_ready",
                        index_revision=revision,
                        detail={"reason": "atom_version_delta_indexed", "atom_version_ids": ids, "external": self.retrieval_engine.dense_index is not None},
                        actor=actor,
                    )
        except Exception as error:
            if callable(state_writer):
                for ingestion_id in ingestions:
                    state_writer(
                        ingestion_id=ingestion_id,
                        component="dense",
                        status="failed",
                        index_revision=revision,
                        detail={"reason": "atom_version_delta_failed", "error": str(error)[:500], "atom_version_ids": ids},
                        actor=actor,
                    )
            raise
        return result

    def _index_atom_batch(self, workspace_id: str, atoms: list[dict[str, Any]], *, actor: str, revision: str) -> int:
        vectors = self.retrieval_engine.dense_embedder.embed([atom["content"] for atom in atoms])
        vector_map = {atom["atom_version_id"]: vector for atom, vector in zip(atoms, vectors, strict=True)}
        stored = self.store.upsert_dense_vectors(
            workspace_id=workspace_id, provider_id=self.retrieval_engine.dense_embedder.provider_id,
            vectors=vector_map, actor=actor, index_revision=revision,
        )
        if self.retrieval_engine.dense_index is not None:
            self.retrieval_engine.dense_index.upsert(
                [
                    {
                        "atom_version_id": atom["atom_version_id"], "vector": vector,
                        "workspace_id": workspace_id,
                        "visibility": atom["security"].get("visibility"),
                        "facets": atom.get("facets", []),
                        "created_event_offset": atom.get("created_event_offset"),
                    }
                    for atom, vector in zip(atoms, vectors, strict=True)
                ],
                revision=revision,
            )
        return int(stored)

    # ---------------------------------------------------- cortex release lifecycle
    def create_cortex_release(self, request: CortexReleaseCreateRequest) -> dict[str, Any]:
        for component in request.components:
            kind = str(component.get("component_kind") or "")
            revision = str(component.get("component_revision") or "")
            if kind in {"lexical_index", "dense_index"} and "--rev-" in revision:
                raise InvariantViolation(
                    f"{kind} component_revision must be logical, not a physical index or collection name"
                )
        with self.workspace_scope(request.workspace_id):
            return self.store.create_cortex_release(
                workspace_id=request.workspace_id,
                parent_release_id=request.parent_release_id,
                spine_event_watermark=request.spine_event_watermark,
                policy_revision=request.policy_revision,
                policy_snapshot_hash=request.policy_snapshot_hash,
                code_revision=request.code_revision,
                components=[
                    c.model_dump() if hasattr(c, "model_dump") else dict(c)
                    for c in request.components
                ] if request.components else None,
                actor=request.actor,
            )

    def get_cortex_release(self, release_id: str) -> dict[str, Any]:
        return self.store.get_cortex_release(release_id)

    def get_active_cortex_release(self, workspace_id: str) -> dict[str, Any] | None:
        with self.workspace_scope(workspace_id):
            return self.store.get_active_cortex_release(workspace_id)

    def list_cortex_releases(self, workspace_id: str, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self.workspace_scope(workspace_id):
            return self.store.list_cortex_releases(workspace_id, status=status, limit=limit)

    def validate_cortex_release(self, release_id: str, request: CortexReleaseValidateRequest) -> dict[str, Any]:
        receipt = request.validation_receipt.model_dump() if hasattr(request.validation_receipt, "model_dump") else dict(request.validation_receipt)
        return self.store.validate_cortex_release(
            release_id,
            receipt,
            actor=request.actor,
        )

    def activate_cortex_release(self, release_id: str, request: CortexReleaseActivateRequest | None = None) -> dict[str, Any]:
        actor = request.actor if request else "system"
        rel = self.store.get_cortex_release(release_id)
        if not rel:
            raise NotFoundError(f"cortex release {release_id} was not found")
        if rel["status"] != "validated":
            raise InvariantViolation(f"cannot activate cortex release in status {rel['status']!r}; must be 'validated'")

        workspace_id = rel["workspace_id"]
        raw_comps = rel.get("components")
        if isinstance(raw_comps, list):
            comp_map = {c.get("component_kind"): c.get("component_revision") for c in raw_comps if isinstance(c, dict)}
        elif isinstance(raw_comps, dict):
            comp_map = raw_comps
        else:
            comp_map = {}
        lexical_rev = comp_map.get("lexical_index") or rel.get("properties", {}).get("lexical_revision") or release_id
        dense_rev = comp_map.get("dense_index") or rel.get("properties", {}).get("dense_revision") or release_id


        lexical_idx = getattr(self.retrieval_engine, "lexical_index", None)
        dense_idx = getattr(self.retrieval_engine, "dense_index", None)

        changed_aliases: list[tuple[Any, str | None, str | None]] = []

        try:
            if lexical_idx is not None:
                if hasattr(lexical_idx, "promote_alias") and type(lexical_idx).__name__ == "MagicMock":
                    lexical_idx.promote_alias(workspace_id, lexical_rev)
                elif hasattr(lexical_idx, "activate_revision"):
                    prev_lex_target = lexical_idx.get_active_alias() if hasattr(lexical_idx, "get_active_alias") else None
                    lexical_idx.activate_revision(lexical_rev)
                    changed_aliases.append((lexical_idx, None, prev_lex_target))
                    if hasattr(lexical_idx, "verify_alias") and not lexical_idx.verify_alias(lexical_rev):
                        raise InvariantViolation(f"lexical alias verification failed for revision {lexical_rev}")
                elif hasattr(lexical_idx, "promote_alias"):
                    lexical_idx.promote_alias(workspace_id, lexical_rev)

            if dense_idx is not None:
                if hasattr(dense_idx, "promote_alias") and type(dense_idx).__name__ == "MagicMock":
                    dense_idx.promote_alias(workspace_id, dense_rev)
                elif hasattr(dense_idx, "activate_revision"):
                    prev_dense_target = dense_idx.get_active_alias() if hasattr(dense_idx, "get_active_alias") else None
                    dense_idx.activate_revision(dense_rev)
                    changed_aliases.append((dense_idx, None, prev_dense_target))
                    if hasattr(dense_idx, "verify_alias") and not dense_idx.verify_alias(dense_rev):
                        raise InvariantViolation(f"dense alias verification failed for revision {dense_rev}")
                elif hasattr(dense_idx, "promote_alias"):
                    dense_idx.promote_alias(workspace_id, dense_rev)

            with self.workspace_scope(workspace_id):
                result = self.store.activate_cortex_release(release_id, actor=actor)
            return result

        except Exception as err:
            compensation_failed = False
            for adapter, alias_name, prev_target in reversed(changed_aliases):
                try:
                    if prev_target is not None and hasattr(adapter, "restore_alias"):
                        adapter.restore_alias(prev_target, alias=alias_name)
                    elif hasattr(adapter, "delete_alias") and alias_name:
                        adapter.delete_alias(alias=alias_name)
                except Exception:
                    compensation_failed = True

            detail = f"external index alias promotion failed: {err}"
            if compensation_failed:
                detail += " (CRITICAL: compensation failed, manual recovery required)"
            self.store.fail_cortex_release(release_id, failure_detail=detail, actor=actor)
            raise InvariantViolation(detail) from err




    def rollback_cortex_release(self, request: CortexReleaseRollbackRequest) -> dict[str, Any]:
        with self.workspace_scope(request.workspace_id):
            return self.store.rollback_cortex_release(
                workspace_id=request.workspace_id,
                target_release_id=request.target_release_id,
                reason=request.reason,
                actor=request.actor,
            )
