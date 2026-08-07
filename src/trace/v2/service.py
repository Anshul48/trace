"""Application service for V2 ingestion, organization, retrieval, and views."""

from __future__ import annotations

import hashlib
import io
import os
import re
import secrets
import json
import tempfile
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from pathlib import Path
from typing import Any

from .adapters import adapt_text
from .atomizer import atomize, normalize_text
from .benchmark import BenchmarkRunner, load_benchmark, validate_release_corpus
from .models import (
    AliasRequest,
    BenchmarkRunRequest,
    EvidenceFeedbackRequest,
    FeedbackEdgeProposalRequest,
    ExperimentManifestRequest,
    FrozenQueryRequest,
    HierarchyBuildRequest,
    IndexRevisionRequest,
    IngestionRequest,
    ApiKeyCreateRequest,
    JobSubmitRequest,
    ModelRegistrationRequest,
    NodeEditRequest,
    ProposalCreateRequest,
    QueryRequest,
    SavedQueryRequest,
    SchemaProposalRequest,
    SplitRequest,
)
from .organization import DeterministicSchemaProposer, EvidenceHierarchyBuilder, GLiNERSchemaProposer, GovernedSchemaClassifier, LiteLLMSchemaProposer, SchemaProposer, SoftSchemaClassifier
from .retrieval import HybridRetrievalEngine, RetrievalOutcome
from .repository import Repository
from .jobs import JobManager
from .webhooks import WebhookDispatcher, WebhookSecretCipher, WebhookSigner, configured_webhook_cipher, validate_webhook_url
from .observability import MetricsRegistry, telemetry_span
from .store import InvariantViolation, NotFoundError, SqliteEventStore
from .config import TraceSettings
from .auth import AuthorizationContext
from .model_gateway import GatewayDeepNavigator, TraceModelGateway
from .projections import ProjectionRevisionError, RevisionedProjectionController


_TOKEN = re.compile(r"[\w][\w'-]*", re.UNICODE)
_STOPWORDS = frozenset({"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "that", "the", "to", "with"})


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
        schema_model = os.environ.get("TRACE_SCHEMA_MODEL")
        self.schema_proposer = schema_proposer or (
            LiteLLMSchemaProposer(schema_model)
            if schema_model
            else (GLiNERSchemaProposer() if os.environ.get("TRACE_GLINER_ENABLED", "false").lower() == "true" else DeterministicSchemaProposer())
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
        workspace_id = str(payload["workspace_id"])
        return {"workspace_id": workspace_id, "dense_indexed": self.rebuild_dense_index(workspace_id, actor="index-worker")}

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

    def submit_job(self, request: JobSubmitRequest, *, request_id: str | None = None) -> dict[str, Any]:
        """Validate an asynchronous workflow envelope before it enters the queue."""

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
        }
        validator = validators.get(request.kind)
        if validator is not None:
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
        attachment = attachment_override or self._put_text(raw_text, request.source.media_type, workspace_id=request.workspace_id)
        if text != raw_text:
            normalized_attachment = self._put_text(text, "text/plain; charset=utf-8", workspace_id=request.workspace_id)
            attachment["metadata"] = {
                **attachment["metadata"],
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
        result = self.store.ingest(
            workspace_id=request.workspace_id,
            source=source,
            attachment=attachment,
            atoms=[draft.__dict__ for draft in drafts],
            actor=request.actor,
            visibility=request.visibility,
            idempotency_key=request.idempotency_key,
        )
        result["status"] = "accepted"
        result["dense_index_status"] = "pending"
        index_job = self.jobs.submit(
            workspace_id=request.workspace_id,
            kind="ingestion.index",
            payload={"workspace_id": request.workspace_id, "ingestion_id": result["ingestion_id"]},
            actor=request.actor,
            idempotency_key=f"{request.idempotency_key}:index" if request.idempotency_key else None,
        )
        result["job_id"] = index_job["job_id"]
        result["job"] = index_job
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
        return self.store.edit_node(
            node_id=node_id, content=request.content, properties=request.properties,
            actor=request.actor, idempotency_key=request.idempotency_key,
        )

    def split_node(self, node_id: str, request: SplitRequest) -> list[dict[str, Any]]:
        return self.store.split_node(node_id=node_id, parts=request.parts, actor=request.actor, idempotency_key=request.idempotency_key)

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
        response = self.hierarchy_builder.build(**request.model_dump()).model_dump()
        if _create_job:
            job = self._completed_job(
                workspace_id=request.workspace_id, kind="hierarchy.build", payload=request.model_dump(mode="json"),
                result=response, actor=request.actor, idempotency_key=f"hierarchy:{request.workspace_id}:{response['generation_id']}",
            )
            response["job_id"] = job["job_id"]
            response["job"] = job
        return response

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

    def run_benchmark(self, request: BenchmarkRunRequest, *, _create_job: bool = True) -> dict[str, Any]:
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
    ) -> list[dict[str, Any]]:
        """Apply the mandatory post-index policy check to canonical rows.

        Search payload filters are defense in depth, not authorization.  An
        index can be stale, replaying a wrong revision, or compromised; every
        hit is reloaded from canonical storage and checked again here.
        """

        result: list[dict[str, Any]] = []
        wanted_facets = set(request.facets)
        for atom in atoms:
            if request.workspace_id and atom.get("workspace_id") != request.workspace_id:
                continue
            if request.as_of_event is not None and int(atom.get("created_event_offset", 0)) > request.as_of_event:
                continue
            if wanted_facets and not wanted_facets.issubset(set(atom.get("facets", []))):
                continue
            if authorization_context is not None:
                if not authorization_context.allows_record(atom):
                    continue
            elif not self._allowed(atom, request.privacy_context):
                continue
            result.append(atom)
        return result

    def query(self, request: QueryRequest, *, authorization_context: AuthorizationContext | None = None) -> dict[str, Any]:
        """Run retrieval inside the repository's explicit tenant scope."""

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

        index_hits: dict[str, list[dict[str, Any]]] = {}
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
                    "index_revision": os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
                }
                try:
                    index_hits["lexical"] = self.retrieval_engine.lexical_index.search(**lexical_kwargs)
                except TypeError:
                    lexical_kwargs.pop("index_revision", None)
                    index_hits["lexical"] = self.retrieval_engine.lexical_index.search(**lexical_kwargs)
                atom_ids.update(str(hit["atom_version_id"]) for hit in index_hits["lexical"] if hit.get("atom_version_id"))
            if self.retrieval_engine.dense_index is not None and request.retrieval_profile != "lexical":
                query_vector = self.retrieval_engine.dense_embedder.embed([request.query])[0]
                dense_kwargs = {
                    "workspace_id": request.workspace_id,
                    "vector": query_vector,
                    "limit": request.retrieval_budget.dense_limit,
                    "visibility": visibility,
                    "facets": request.facets,
                    "as_of_event": request.as_of_event,
                    "index_revision": os.environ.get("TRACE_INDEX_REVISION", "embedded-current"),
                }
                try:
                    index_hits["dense"] = self.retrieval_engine.dense_index.search(**dense_kwargs)
                except TypeError:
                    # Compatibility for an older injected adapter; production
                    # adapters implement revision-aware filtering.
                    dense_kwargs.pop("index_revision", None)
                    index_hits["dense"] = self.retrieval_engine.dense_index.search(**dense_kwargs)
                atom_ids.update(str(hit["atom_version_id"]) for hit in index_hits["dense"] if hit.get("atom_version_id"))
            atoms = self._revalidate_atoms(self.store.atom_versions(sorted(atom_ids)), request, authorization_context)
        else:
            if self.settings.requires_external_indexes:
                raise InvariantViolation("production retrieval requires both revisioned OpenSearch and Qdrant adapters")
            # The embedded adapter is deliberately a correctness path.  It is
            # never selected by a production-profile deployment.
            atoms = self.store.queryable_atoms(request.workspace_id, request.as_of_event)
            atoms = self._revalidate_atoms(atoms, request, authorization_context)
        with telemetry_span("trace.retrieval", {"workspace_id": request.workspace_id, "profile": request.retrieval_profile}):
            with self.metrics.timer("trace_retrieval_seconds", labels={"profile": request.retrieval_profile}):
                navigator = (
                    GatewayDeepNavigator(self.model_gateway, context=authorization_context, model_id=request.model_id)
                    if request.model_id and authorization_context is not None else None
                )
                outcome: RetrievalOutcome = self.retrieval_engine.retrieve(
                    store=self.store, request=request, atoms=atoms, index_hits=index_hits or None, deep_navigator=navigator,
                )
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
            if self._revalidate_atoms([candidate.atom], request, authorization_context)
        ]
        outcome.candidates.sort(key=lambda candidate: (-candidate.score, candidate.atom["atom_version_id"]))
        terms = set(_tokens(request.query))
        results: list[dict[str, Any]] = []
        for rank, candidate in enumerate(outcome.candidates[:request.retrieval_budget.candidate_limit], start=1):
            atom = candidate.atom
            is_source_atom = "atom" in atom.get("facets", [])
            source_ids = atom.get("source_atom_version_ids", [atom["atom_version_id"]] if is_source_atom else [])
            results.append({
                "rank": rank,
                "candidate_kind": "atom" if is_source_atom else "derived",
                "node_id": atom["node_id"],
                "atom_version_id": atom["atom_version_id"],
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
                "channel_scores": {
                    "lexical_bm25": candidate.lexical,
                    "dense": candidate.dense,
                    "rrf": candidate.rrf,
                    "rerank": candidate.rerank,
                    "graph_ppr": candidate.graph,
                    "feedback": candidate.feedback,
                    "hierarchy": candidate.hierarchy,
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
        return self.store.replay_report(workspace_id)

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
