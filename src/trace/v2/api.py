"""FastAPI surface for the headless ``/v2`` contract.

The router is intentionally thin. Request validation belongs to Pydantic
models, lifecycle and retrieval policy belong to :class:`TraceService`, and
durability/invariants belong to the store. This keeps HTTP clients independent
of SQLite and makes it possible to swap the embedded adapter for distributed
PostgreSQL/OpenSearch/Qdrant services without changing route semantics.

Every mutating route returns only after the relevant Spine event and local
projection transaction has committed. Long-running vector/model work is
represented as pending state and is expected to be consumed from the outbox.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, nullcontext
import os
import time
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .models import (
    AliasRequest,
    AffinityRejectionRequest,
    ApiKeyCreateRequest,
    ApiKeyDecisionRequest,
    BenchmarkRunRequest,
    CognitivePolicy,
    CortexReleaseCreateRequest,
    CortexReleaseValidateRequest,
    CortexReleaseActivateRequest,
    CortexReleaseRollbackRequest,
    EvidenceFeedbackRequest,
    FeedbackEdgeProposalRequest,
    ExperimentManifestRequest,
    FrozenQueryRequest,
    GraphRequest,
    HierarchyBuildRequest,
    IndexRevisionRequest,
    IngestionRequest,
    JobDecisionRequest,
    JobSubmitRequest,
    ModelRegistrationRequest,
    NodeEditRequest,
    ProposalCreateRequest,
    ProposalDecisionRequest,
    ProjectionRebuildRequest,
    QueryRequest,
    SavedQueryRequest,
    SchemaProposalRequest,
    SourceErasureRequest,
    SourceLifecycleRequest,
    SplitRequest,
    SynthesisRequest,
    WebhookCreateRequest,
    WebhookRotateRequest,
)
from .auth import AuthorizationContext, AuthenticationError, AuthorizationError, IdentityProvider, Principal, build_authorization_context, enforce_workspace
from .pagination import PaginationError, decode_page_token, encode_page_token
from .service import TraceService
from .store import IdempotencyConflict, InvariantViolation, NotFoundError, TraceStoreError
from .model_gateway import ModelGatewayError, ModelPolicyDenied, ModelUnavailableError


def _service(request: Request) -> TraceService:
    return request.app.state.trace_service


class PayloadTooLargeError(RuntimeError):
    """Raised after reading a chunked upload whose size was not in headers."""


def _principal(request: Request) -> Principal:
    return getattr(request.state, "principal", IdentityProvider(required=False).authenticate({}))


def _authorize(request: Request, workspace_id: str | None, *, scope: str = "retrieval:read") -> str:
    principal = _principal(request)
    principal.require_scope(scope)
    return enforce_workspace(principal, workspace_id)


def _actor(request: Request, actor: str | None = None) -> str:
    # Actor identity is never accepted from a caller-controlled body field.
    return _principal(request).subject


def _privacy(request: Request, value: dict[str, object] | None) -> dict[str, object]:
    return _principal(request).privacy_context(value)


def _authorization_context(
    request: Request,
    workspace_id: str | None,
    *,
    privacy: dict[str, object] | None = None,
    as_of_event: int | None = None,
) -> AuthorizationContext:
    """Derive one explicit-workspace context for downstream policy checks."""

    return build_authorization_context(
        _principal(request),
        workspace_id,
        request_id=getattr(request.state, "request_id", None),
        as_of_event=as_of_event,
        requested_privacy=privacy,
    )


def _respond_async(request: Request) -> bool:
    preference = request.headers.get("prefer", "")
    return "respond-async" in {item.strip().lower() for item in preference.split(",")} or os.environ.get("TRACE_ASYNC_WORKFLOWS", "false").lower() == "true"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request ID and authenticated principal before route execution."""

    def __init__(self, app: object, *, identity: IdentityProvider | None = None) -> None:
        super().__init__(app)
        self.identity = identity or IdentityProvider()
        self.max_body_bytes = max(1_024, int(os.environ.get("TRACE_MAX_BODY_BYTES", str(10 * 1024 * 1024))))
        self.rate_limit = max(0, int(os.environ.get("TRACE_RATE_LIMIT_PER_MINUTE", "600")))
        self._windows: dict[str, tuple[int, int]] = {}

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or request.headers.get("x-correlation-id") or os.urandom(12).hex()
        if len(request_id) > 128 or any(ord(char) < 32 for char in request_id):
            return JSONResponse(status_code=400, content={"type": "about:blank", "title": "Bad Request", "status": 400, "detail": "invalid request ID", "request_id": request_id[:128]})
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.max_body_bytes:
            return JSONResponse(status_code=413, content={"type": "about:blank", "title": "Payload Too Large", "status": 413, "detail": "request payload exceeds configured limit", "request_id": request_id})
        try:
            trace_service = getattr(request.app.state, "trace_service", None)
            if trace_service is not None and hasattr(trace_service.store, "resolve_api_key"):
                self.identity.key_resolver = trace_service.store.resolve_api_key
            principal = self.identity.authenticate(request.headers)
        except AuthenticationError as error:
            # Health/readiness are intentionally callable by load balancers;
            # all corpus/admin routes remain protected when auth is required.
            if request.url.path not in {"/v2/health", "/v2/ready", "/docs", "/openapi.json", "/redoc"}:
                return JSONResponse(status_code=error.status_code, content={"type": "about:blank", "title": "Unauthorized", "status": error.status_code, "detail": str(error), "code": error.code, "request_id": request_id}, headers={"WWW-Authenticate": "Bearer"})
            principal = IdentityProvider(required=False).authenticate({})
        key = principal.subject or (request.client.host if request.client else "anonymous")
        if self.rate_limit:
            now_window = int(time.time() // 60)
            window, count = self._windows.get(key, (now_window, 0))
            if window != now_window:
                window, count = now_window, 0
            count += 1
            self._windows[key] = (window, count)
            if count > self.rate_limit:
                return JSONResponse(status_code=429, content={"type": "about:blank", "title": "Too Many Requests", "status": 429, "detail": "rate limit exceeded", "request_id": request_id}, headers={"Retry-After": "60"})
        request.state.principal = principal
        request.state.request_id = request_id
        # API keys are deliberately single-workspace grants. Bind that server-
        # derived scope for the entire request so ID-addressed repository reads
        # remain RLS-protected without any request path ever setting '*'. Multi-
        # workspace OIDC principals still have to name a workspace at routes
        # that support multiple workspaces.
        scope_factory = getattr(trace_service.store, "authorization_scope", None) if trace_service is not None else None
        only_workspace = None
        if principal.workspace_ids is not None and len(principal.workspace_ids) == 1:
            only_workspace = next(iter(principal.workspace_ids))
        scope = scope_factory(only_workspace) if only_workspace and callable(scope_factory) else nullcontext()
        with scope:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _http_error(error: Exception) -> HTTPException:
    """Map domain failures to stable public status codes without leaking SQL."""
    if isinstance(error, NotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, IdempotencyConflict):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, (InvariantViolation, ValueError)):
        return HTTPException(status_code=422, detail=str(error))
    if isinstance(error, PayloadTooLargeError):
        return HTTPException(status_code=413, detail="request payload exceeds configured limit")
    if isinstance(error, PermissionError):
        return HTTPException(status_code=403, detail={"code": "policy_denied", "message": str(error)})
    if isinstance(error, ModelPolicyDenied):
        return HTTPException(status_code=403, detail={"code": "model_policy_denied", "message": str(error)})
    if isinstance(error, ModelUnavailableError):
        return HTTPException(status_code=503, detail={"code": "model_unavailable", "message": str(error)}, headers={"Retry-After": "5"})
    if isinstance(error, ModelGatewayError):
        return HTTPException(status_code=422, detail={"code": "model_response_invalid", "message": str(error)})
    if isinstance(error, (AuthenticationError, AuthorizationError)):
        return HTTPException(status_code=error.status_code, detail={"code": error.code, "message": str(error)})
    return HTTPException(status_code=500, detail="internal Trace V2 error")


def _problem(request: Request, *, status: int, title: str, detail: object, code: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        "type": "about:blank", "title": title, "status": status, "detail": detail,
        "instance": request.url.path, "request_id": getattr(request.state, "request_id", None),
    }
    if code:
        body["code"] = code
    return body


def create_app(service: TraceService | None = None) -> FastAPI:
    """Build an isolated V2 application.

    Passing a service is useful for tests and for embedding Trace into another
    ASGI process. Omitting it creates the configured embedded service during
    lifespan startup, so importing ``main_api.app`` does not open a database or
    create attachment directories prematurely.
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.trace_service = service or TraceService.from_environment()
        yield

    app = FastAPI(
        title="Trace V2",
        version="2.0.0",
        description="Headless, evidence-first cognitive memory substrate.",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    allowed_origins = [item.strip() for item in os.environ.get("TRACE_CORS_ORIGINS", "").split(",") if item.strip()]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-API-Key", "X-Request-ID"],
        )
    router = APIRouter(prefix="/v2")

    @router.get("/health")
    def health(request: Request) -> dict[str, object]:
        trace = _service(request)
        return {"status": "ok", "api_version": "v2", "last_event_offset": trace.store.last_event_offset()}

    @router.get("/ready")
    def ready(request: Request) -> dict[str, object]:
        trace = _service(request)
        checks: dict[str, object] = {"last_event_offset": trace.store.last_event_offset(), **trace.readiness()}
        if hasattr(trace.store, "projection_status"):
            try:
                trace.store.projection_status()
            except Exception as error:
                checks["postgresql"] = {"status": "error", "detail": str(error)[:200]}
        error_values = [value for key, value in checks.items() if key not in {"last_event_offset", "projection_lag", "outbox"} and isinstance(value, dict) and value.get("status") == "error"]
        ready_state = not error_values and checks.get("projection_lag", 0) != -1
        return {"status": "ready" if ready_state else "not_ready", "checks": checks}

    @router.get("/metrics", include_in_schema=False)
    def metrics(request: Request) -> PlainTextResponse:
        _principal(request).require_scope("metrics:read")
        return PlainTextResponse(_service(request).metrics.prometheus(), media_type="text/plain; version=0.0.4")

    @router.post("/jobs", status_code=202)
    def submit_job(payload: JobSubmitRequest, request: Request) -> dict[str, object]:
        try:
            workspace_id = _authorize(request, payload.workspace_id, scope="jobs:write")
            if payload.model_id:
                context = _authorization_context(request, workspace_id)
                if payload.model_id not in {item["id"] for item in _service(request).available_models(authorization_context=context)}:
                    raise AuthorizationError("requested model is outside the workspace model policy", code="model_scope_denied")
            body = payload.model_copy(update={
                "actor": _actor(request),
                "idempotency_key": payload.idempotency_key or request.headers.get("idempotency-key"),
            })
            return _service(request).submit_job(body, request_id=getattr(request.state, "request_id", None))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/jobs")
    def list_jobs(request: Request, workspace_id: str, status: str | None = None, kind: str | None = None, limit: int = Query(default=50, ge=1, le=200), page_token: str | None = None) -> dict[str, object]:
        try:
            _authorize(request, workspace_id, scope="jobs:read")
            scope = f"jobs:{workspace_id}:{status or ''}:{kind or ''}"
            position = decode_page_token(page_token, scope=scope, max_limit=200).position if page_token else 0
            items = _service(request).list_jobs(workspace_id=workspace_id, status=status, kind=kind, limit=limit + 1, offset=position)
            next_token = encode_page_token(scope=scope, position=position + limit, limit=limit) if len(items) > limit else None
            return {"items": items[:limit], "limit": limit, "next_page_token": next_token}
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str, request: Request) -> dict[str, object]:
        try:
            job = _service(request).get_job(job_id)
            _authorize(request, job["workspace_id"], scope="jobs:read")
            return job
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, payload: JobDecisionRequest, request: Request) -> dict[str, object]:
        try:
            current = _service(request).get_job(job_id)
            _authorize(request, current["workspace_id"], scope="jobs:write")
            return _service(request).cancel_job(job_id, actor=_actor(request), reason=payload.reason)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/jobs/{job_id}/retry")
    def retry_job(job_id: str, payload: JobDecisionRequest, request: Request) -> dict[str, object]:
        try:
            current = _service(request).get_job(job_id)
            _authorize(request, current["workspace_id"], scope="jobs:write")
            return _service(request).retry_job(job_id, actor=_actor(request), execute=payload.execute)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/webhooks", status_code=201)
    def create_webhook(payload: WebhookCreateRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="webhooks:write")
            return _service(request).create_webhook(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/webhooks/{webhook_id}")
    def get_webhook(webhook_id: str, request: Request) -> dict[str, object]:
        try:
            webhook = _service(request).get_webhook(webhook_id)
            _authorize(request, webhook["workspace_id"], scope="webhooks:read")
            return webhook
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/webhooks/{webhook_id}/rotate")
    def rotate_webhook(webhook_id: str, payload: WebhookRotateRequest, request: Request) -> dict[str, object]:
        try:
            webhook = _service(request).get_webhook(webhook_id)
            _authorize(request, webhook["workspace_id"], scope="webhooks:write")
            return _service(request).rotate_webhook(webhook_id, actor=_actor(request))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/api-keys", status_code=201)
    def create_api_key(payload: ApiKeyCreateRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="admin:write")
            _principal(request).validate_grant(
                scopes=payload.scopes,
                allowed_visibility=payload.allowed_visibility,
                model_permissions=payload.model_permissions,
            )
            return _service(request).create_api_key(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    # ---------------------------------------------------- cortex release endpoints
    @router.post("/cortex/releases", status_code=201)
    def create_cortex_release(payload: CortexReleaseCreateRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="cortex:write")
            return _service(request).create_cortex_release(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/cortex/releases")
    def list_cortex_releases(request: Request, workspace_id: str, status: str | None = None, limit: int = 50) -> list[dict[str, object]]:
        try:
            _authorize(request, workspace_id, scope="cortex:read")
            return _service(request).list_cortex_releases(workspace_id, status=status, limit=limit)
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/cortex/releases/active")
    def get_active_cortex_release(request: Request, workspace_id: str) -> dict[str, object]:
        try:
            _authorize(request, workspace_id, scope="cortex:read")
            active = _service(request).get_active_cortex_release(workspace_id)
            if active is None:
                raise HTTPException(status_code=404, detail=f"no active cortex release found for workspace {workspace_id}")
            return active
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/cortex/releases/{release_id}")
    def get_cortex_release(release_id: str, request: Request) -> dict[str, object]:
        try:
            release = _service(request).get_cortex_release(release_id)
            _authorize(request, release["workspace_id"], scope="cortex:read")
            return release
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/cortex/releases/{release_id}/validate")
    def validate_cortex_release(release_id: str, payload: CortexReleaseValidateRequest, request: Request) -> dict[str, object]:
        try:
            rel = _service(request).get_cortex_release(release_id)
            _authorize(request, rel["workspace_id"], scope="cortex:write")
            return _service(request).validate_cortex_release(release_id, payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/cortex/releases/{release_id}/activate")
    def activate_cortex_release(release_id: str, request: Request, payload: CortexReleaseActivateRequest | None = None) -> dict[str, object]:
        try:
            rel = _service(request).get_cortex_release(release_id)
            _authorize(request, rel["workspace_id"], scope="cortex:write")
            act_payload = payload.model_copy(update={"actor": _actor(request)}) if payload else CortexReleaseActivateRequest(actor=_actor(request))
            return _service(request).activate_cortex_release(release_id, act_payload)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/cortex/releases/rollback")
    def rollback_cortex_release(payload: CortexReleaseRollbackRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="cortex:write")
            return _service(request).rollback_cortex_release(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/api-keys/{api_key_id}")
    def get_api_key(api_key_id: str, request: Request) -> dict[str, object]:
        try:
            key = _service(request).get_api_key(api_key_id)
            _authorize(request, key["workspace_id"], scope="admin:read")
            return key
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/api-keys/{api_key_id}/revoke")
    def revoke_api_key(api_key_id: str, payload: ApiKeyDecisionRequest, request: Request) -> dict[str, object]:
        try:
            key = _service(request).get_api_key(api_key_id)
            _authorize(request, key["workspace_id"], scope="admin:write")
            return _service(request).revoke_api_key(api_key_id, actor=_actor(request), reason=payload.reason)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/ingestions", status_code=202)
    def ingest(payload: IngestionRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="ingestion:write")
            _privacy(request, {"visibility": payload.visibility})
            body = payload.model_copy(update={"actor": _actor(request), "idempotency_key": payload.idempotency_key or request.headers.get("idempotency-key")})
            return _service(request).ingest(body)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/ingestions/upload", status_code=202)
    async def ingest_upload(
        request: Request,
        workspace_id: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
        actor: Annotated[str, Form()] = "anonymous",
        visibility: Annotated[str, Form()] = "private",
        idempotency_key: Annotated[str | None, Form()] = None,
        source_uri: Annotated[str | None, Form()] = None,
    ) -> dict[str, object]:
        try:
            _authorize(request, workspace_id, scope="ingestion:write")
            _privacy(request, {"visibility": visibility})
            raw = await file.read()
            if len(raw) > max(1_024, int(os.environ.get("TRACE_MAX_BODY_BYTES", str(10 * 1024 * 1024)))):
                raise PayloadTooLargeError("upload exceeds configured request limit")
            filename = file.filename or "upload"
            media_type = file.content_type or "text/plain"
            adapter = "pdf" if media_type == "application/pdf" or filename.lower().endswith(".pdf") else (
                "html" if media_type == "text/html" or filename.lower().endswith((".html", ".htm")) else "upload"
            )
            return _service(request).ingest_bytes(
                workspace_id=workspace_id, raw=raw, actor=_actor(request), visibility=visibility,
                idempotency_key=idempotency_key or request.headers.get("idempotency-key"),
                source={"title": filename, "uri": source_uri, "media_type": media_type, "adapter": adapter},
            )
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/ingestions/{ingestion_id}")
    def ingestion_status(ingestion_id: str, request: Request) -> dict[str, object]:
        try:
            status = _service(request).ingestion_status(ingestion_id)
            _authorize(request, status["workspace_id"], scope="ingestion:read")
            return status
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/ingestions/{ingestion_id}/consolidate")
    def consolidate(ingestion_id: str, request: Request, actor: str = "system") -> dict[str, object]:
        try:
            status = _service(request).ingestion_status(ingestion_id)
            _authorize(request, status["workspace_id"], scope="organization:write")
            if _respond_async(request):
                submitted = _service(request).submit_job(JobSubmitRequest(
                    workspace_id=status["workspace_id"], kind="consolidation",
                    payload={"ingestion_id": ingestion_id, "actor": _actor(request)}, actor=_actor(request),
                    idempotency_key=request.headers.get("idempotency-key") or f"consolidation:{ingestion_id}",
                ), request_id=getattr(request.state, "request_id", None))
                return JSONResponse(status_code=202, content=submitted)
            return _service(request).consolidate_ingestion(ingestion_id, actor=_actor(request))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/nodes/{node_id}")
    def get_node(node_id: str, request: Request, as_of_event: int | None = None) -> dict[str, object]:
        try:
            node = _service(request).store.get_node(node_id, as_of_event)
            _authorize(request, node["workspace_id"], scope="retrieval:read")
            return node
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/nodes/{node_id}/history")
    def node_history(node_id: str, request: Request) -> list[dict[str, object]]:
        try:
            node = _service(request).store.get_node(node_id)
            _authorize(request, node["workspace_id"], scope="retrieval:read")
            return _service(request).store.node_history(node_id)
        except Exception as error:
            raise _http_error(error) from error

    @router.patch("/nodes/{node_id}")
    def edit_node(node_id: str, payload: NodeEditRequest, request: Request) -> dict[str, object]:
        try:
            node = _service(request).store.get_node(node_id)
            _authorize(request, node["workspace_id"], scope="ingestion:write")
            return _service(request).edit_node(node_id, payload.model_copy(update={"actor": _actor(request), "idempotency_key": payload.idempotency_key or request.headers.get("idempotency-key")}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/atom-versions/{atom_version_id}/lifecycle")
    def transition_source_lifecycle(atom_version_id: str, payload: SourceLifecycleRequest, request: Request) -> dict[str, object]:
        try:
            atoms = _service(request).store.atom_versions([atom_version_id])
            if not atoms:
                raise NotFoundError(f"atom version {atom_version_id} was not found")
            _authorize(request, atoms[0]["workspace_id"], scope="ingestion:write")
            body = payload.model_copy(update={"actor": _actor(request), "idempotency_key": payload.idempotency_key or request.headers.get("idempotency-key")})
            return _service(request).transition_source_lifecycle(atom_version_id, body)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/atom-versions/{atom_version_id}/erase")
    def erase_source(atom_version_id: str, payload: SourceErasureRequest, request: Request) -> dict[str, object]:
        try:
            atoms = _service(request).store.atom_versions([atom_version_id])
            if not atoms:
                raise NotFoundError(f"atom version {atom_version_id} was not found")
            _authorize(request, atoms[0]["workspace_id"], scope="admin:write")
            body = payload.model_copy(update={"actor": _actor(request), "idempotency_key": payload.idempotency_key or request.headers.get("idempotency-key")})
            return _service(request).erase_source(atom_version_id, body)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/nodes/{node_id}/split")
    def split_node(node_id: str, payload: SplitRequest, request: Request) -> list[dict[str, object]]:
        try:
            node = _service(request).store.get_node(node_id)
            _authorize(request, node["workspace_id"], scope="ingestion:write")
            return _service(request).split_node(node_id, payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/nodes/{node_id}/alias")
    def alias_node(node_id: str, payload: AliasRequest, request: Request) -> dict[str, object]:
        try:
            node = _service(request).store.get_node(node_id)
            _authorize(request, node["workspace_id"], scope="organization:write")
            return _service(request).alias_node(node_id, payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/queries")
    def query(payload: QueryRequest, request: Request) -> dict[str, object]:
        try:
            workspace_id = payload.workspace_id
            principal = _principal(request)
            if not workspace_id:
                if principal.workspace_ids is not None and len(principal.workspace_ids) == 1:
                    workspace_id = next(iter(principal.workspace_ids))
                else:
                    raise AuthorizationError("workspace_id is required unless the principal has exactly one workspace", code="workspace_required")
            _authorize(request, workspace_id, scope="retrieval:read")
            payload = payload.model_copy(update={"workspace_id": workspace_id})
            context = _authorization_context(request, workspace_id, privacy=payload.privacy_context, as_of_event=payload.as_of_event)
            body = payload.model_copy(update={"privacy_context": context.privacy_context()})
            return _service(request).query(body, authorization_context=context)
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/models")
    def models(request: Request, workspace_id: str | None = None) -> dict[str, object]:
        """List only server-registered models allowed for the caller/workspace."""

        try:
            principal = _principal(request)
            if not workspace_id:
                if principal.workspace_ids is not None and len(principal.workspace_ids) == 1:
                    workspace_id = next(iter(principal.workspace_ids))
                else:
                    raise AuthorizationError("workspace_id is required unless the principal has exactly one workspace", code="workspace_required")
            _authorize(request, workspace_id, scope="retrieval:read")
            context = _authorization_context(request, workspace_id)
            return {"workspace_id": workspace_id, "models": _service(request).available_models(authorization_context=context)}
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/retrieval-feedback")
    def retrieval_feedback(payload: EvidenceFeedbackRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="feedback:write")
            return _service(request).record_feedback(payload.model_copy(update={"actor": _actor(request), "idempotency_key": payload.idempotency_key or request.headers.get("idempotency-key")}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/graph/edge-strength-proposals")
    def feedback_edge_strengths(payload: FeedbackEdgeProposalRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="organization:write")
            return _service(request).propose_feedback_edge_strengths(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/syntheses")
    def synthesize(payload: SynthesisRequest, request: Request) -> dict[str, object]:
        try:
            trace = _service(request)
            if payload.workspace_id:
                _authorize(request, payload.workspace_id, scope="synthesis:read")
                context = _authorization_context(request, payload.workspace_id, privacy=payload.privacy_context)
                with trace.workspace_scope(payload.workspace_id):
                    bundle = trace.store.get_bundle(payload.evidence_bundle_id)
                    if bundle["workspace_id"] != payload.workspace_id:
                        raise NotFoundError("evidence bundle was not found in this workspace")
                    return trace.synthesize(
                        payload.evidence_bundle_id, prompt=payload.prompt, format=payload.format,
                        privacy_context=context.privacy_context(), model_id=payload.model_id, authorization_context=context,
                    )
            if trace.settings.production_mode:
                raise InvariantViolation("production synthesis requires workspace_id for tenant-scoped bundle lookup")
            bundle = trace.store.get_bundle(payload.evidence_bundle_id)
            _authorize(request, bundle["workspace_id"], scope="synthesis:read")
            context = _authorization_context(request, bundle["workspace_id"], privacy=payload.privacy_context)
            return trace.synthesize(
                payload.evidence_bundle_id, prompt=payload.prompt, format=payload.format,
                privacy_context=context.privacy_context(), model_id=payload.model_id, authorization_context=context,
            )
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/graph/subgraph")
    def subgraph(
        request: Request,
        workspace_id: str,
        seed_node_id: list[str] = Query(default=[]),
        depth: int = 1,
        as_of_event: int | None = None,
        allowed_visibility: list[str] = Query(default=[]),
    ) -> dict[str, object]:
        try:
            _authorize(request, workspace_id, scope="retrieval:read")
            return _service(request).subgraph(
                workspace_id=workspace_id, seed_node_ids=seed_node_id, depth=depth, as_of_event=as_of_event,
                privacy_context=_privacy(request, {"allowed_visibility": allowed_visibility} if allowed_visibility else {}),
            )
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/graph/subgraph")
    def subgraph_post(payload: GraphRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="retrieval:read")
            return _service(request).subgraph(
                workspace_id=payload.workspace_id, seed_node_ids=payload.seed_node_ids, depth=payload.depth,
                as_of_event=payload.as_of_event, privacy_context=_privacy(request, payload.privacy_context),
            )
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/proposals")
    def create_proposal(payload: ProposalCreateRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="organization:write")
            return _service(request).create_proposal(payload.model_copy(update={"actor": _actor(request), "idempotency_key": payload.idempotency_key or request.headers.get("idempotency-key")}))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/proposals")
    def list_proposals(request: Request, workspace_id: str, status: str | None = None, proposal_type: str | None = None, limit: int = Query(default=50, ge=1, le=200), page_token: str | None = None) -> dict[str, object]:
        try:
            _authorize(request, workspace_id, scope="organization:read")
            scope = f"proposals:{workspace_id}:{status or ''}:{proposal_type or ''}"
            position = decode_page_token(page_token, scope=scope, max_limit=200).position if page_token else 0
            items = _service(request).store.list_proposals(workspace_id, proposal_type=proposal_type, status=status, limit=limit + 1, offset=position)
            next_token = encode_page_token(scope=scope, position=position + limit, limit=limit) if len(items) > limit else None
            return {"items": items[:limit], "limit": limit, "next_page_token": next_token}
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/hierarchy/build")
    def build_hierarchy(payload: HierarchyBuildRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="organization:write")
            if _respond_async(request):
                return JSONResponse(status_code=202, content=_service(request).submit_job(JobSubmitRequest(
                    workspace_id=payload.workspace_id, kind="hierarchy.build", payload=payload.model_dump(mode="json"),
                    actor=_actor(request), idempotency_key=request.headers.get("idempotency-key"),
                ), request_id=getattr(request.state, "request_id", None)))
            return _service(request).build_hierarchy(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/affinity/rejections")
    def reject_affinity(payload: AffinityRejectionRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="organization:write")
            return _service(request).reject_affinity(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/schemas/proposals")
    def propose_schemas(payload: SchemaProposalRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="organization:write")
            context = _authorization_context(request, payload.workspace_id)
            if payload.model_id and payload.model_id not in {item["id"] for item in _service(request).available_models(authorization_context=context)}:
                raise AuthorizationError("requested model is outside the workspace model policy", code="model_scope_denied")
            if _respond_async(request):
                return JSONResponse(status_code=202, content=_service(request).submit_job(JobSubmitRequest(
                    workspace_id=payload.workspace_id, kind="schema.proposals", payload=payload.model_dump(mode="json"),
                    actor=_actor(request), idempotency_key=request.headers.get("idempotency-key"),
                ), request_id=getattr(request.state, "request_id", None)))
            return _service(request).propose_schemas(payload.model_copy(update={"actor": _actor(request)}), authorization_context=context)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/benchmarks/runs")
    def run_benchmark(payload: BenchmarkRunRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="benchmarks:write")
            if _respond_async(request):
                return JSONResponse(status_code=202, content=_service(request).submit_job(JobSubmitRequest(
                    workspace_id=payload.workspace_id, kind="benchmark.run", payload=payload.model_dump(mode="json"),
                    actor=_actor(request), idempotency_key=request.headers.get("idempotency-key"),
                ), request_id=getattr(request.state, "request_id", None)))
            return _service(request).run_benchmark(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/schemas/classifications")
    def schema_classifications(request: Request, workspace_id: str, atom_version_id: list[str] = Query(default=[])) -> list[dict[str, object]]:
        try:
            _authorize(request, workspace_id, scope="retrieval:read")
            return _service(request).classify_atoms(workspace_id, atom_version_ids=atom_version_id or None)
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/proposals/{proposal_id}")
    def get_proposal(proposal_id: str, request: Request) -> dict[str, object]:
        try:
            proposal = _service(request).store.get_proposal(proposal_id)
            _authorize(request, proposal["workspace_id"], scope="organization:read")
            return proposal
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/proposals/{proposal_id}/promote")
    def promote_proposal(proposal_id: str, payload: ProposalDecisionRequest, request: Request) -> dict[str, object]:
        try:
            proposal = _service(request).store.get_proposal(proposal_id)
            _authorize(request, proposal["workspace_id"], scope="organization:write")
            return _service(request).promote_proposal(
                proposal_id, actor=_actor(request), reason=payload.reason, idempotency_key=payload.idempotency_key or request.headers.get("idempotency-key"),
            )
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/proposals/{proposal_id}/reject")
    def reject_proposal(proposal_id: str, payload: ProposalDecisionRequest, request: Request) -> dict[str, object]:
        try:
            proposal = _service(request).store.get_proposal(proposal_id)
            _authorize(request, proposal["workspace_id"], scope="organization:write")
            return _service(request).reject_proposal(
                proposal_id, actor=_actor(request), reason=payload.reason, idempotency_key=payload.idempotency_key or request.headers.get("idempotency-key"),
            )
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/saved-queries")
    def save_query(payload: SavedQueryRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="retrieval:write")
            body = payload.model_copy(update={"actor": _actor(request), "query": payload.query.model_copy(update={"privacy_context": _privacy(request, payload.query.privacy_context)})})
            return _service(request).save_query(body)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/frozen-queries")
    def freeze_query(payload: FrozenQueryRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="retrieval:write")
            body = payload.model_copy(update={"actor": _actor(request), "query": payload.query.model_copy(update={"privacy_context": _privacy(request, payload.query.privacy_context)})})
            return _service(request).freeze_query(body)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/admin/projections/reconcile")
    def reconcile(request: Request, workspace_id: str | None = None, actor: str = "system") -> dict[str, object]:
        try:
            if workspace_id:
                _authorize(request, workspace_id, scope="admin:write")
            else:
                _principal(request).require_scope("admin:write")
            return _service(request).replay(workspace_id=workspace_id, actor=_actor(request))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/admin/replay")
    def validate_replay(request: Request, workspace_id: str) -> dict[str, object]:
        try:
            _authorize(request, workspace_id, scope="admin:read")
            return _service(request).validate_replay(workspace_id)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/admin/attachments/reconcile")
    def reconcile_attachment_staging(request: Request, workspace_id: str) -> dict[str, object]:
        try:
            _authorize(request, workspace_id, scope="admin:write")
            return _service(request).reconcile_attachment_staging(workspace_id, actor=_actor(request))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/admin/projections")
    def projection_status(request: Request, workspace_id: str | None = None) -> list[dict[str, object]]:
        trace = _service(request)
        if workspace_id:
            _authorize(request, workspace_id, scope="admin:read")
        else:
            _principal(request).require_scope("admin:read")
            if trace.settings.production_mode:
                raise InvariantViolation("production projection inspection requires workspace_id")
        with trace.workspace_scope(workspace_id):
            return trace.store.projection_status(workspace_id)

    @router.get("/admin/cognitive-policies/{workspace_id}")
    def get_cognitive_policy(workspace_id: str, request: Request) -> dict[str, object]:
        try:
            _authorize(request, workspace_id, scope="admin:read")
            return _service(request).get_cognitive_policy(workspace_id)
        except Exception as error:
            raise _http_error(error) from error

    @router.put("/admin/cognitive-policies/{workspace_id}")
    def put_cognitive_policy(workspace_id: str, payload: CognitivePolicy, request: Request) -> dict[str, object]:
        try:
            _authorize(request, workspace_id, scope="admin:write")
            return _service(request).put_cognitive_policy(workspace_id, payload, actor=_actor(request))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/admin/projection-runs")
    def projection_runs(
        request: Request,
        workspace_id: str,
        projection_kind: str | None = None,
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict[str, object]]:
        try:
            _authorize(request, workspace_id, scope="admin:read")
            trace = _service(request)
            source = getattr(trace.store, "list_projection_runs", None)
            if not callable(source):
                raise InvariantViolation("the configured repository does not support projection inspection")
            with trace.workspace_scope(workspace_id):
                return source(workspace_id, projection_kind=projection_kind, status=status, limit=limit)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/admin/projections/rebuild")
    def rebuild_projection(payload: ProjectionRebuildRequest, request: Request) -> dict[str, object]:
        try:
            _authorize(request, payload.workspace_id, scope="admin:write")
            body = payload.model_copy(update={"actor": _actor(request)})
            if _respond_async(request):
                kind = {
                    "hierarchy": "hierarchy.delta",
                    "affinity": "affinity.delta",
                    "activation": "activation.recompute",
                }[body.projection_kind]
                return JSONResponse(status_code=202, content=_service(request).submit_job(JobSubmitRequest(
                    workspace_id=body.workspace_id, kind=kind, payload=body.model_dump(mode="json"), actor=_actor(request),
                    idempotency_key=request.headers.get("idempotency-key"),
                ), request_id=getattr(request.state, "request_id", None)))
            return _service(request).rebuild_projection(body)
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/admin/snapshots")
    def snapshot(request: Request, actor: str = "system") -> dict[str, object]:
        try:
            _principal(request).require_scope("admin:write")
            return _service(request).snapshot(actor=_actor(request))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/admin/reindex")
    def reindex(payload: IndexRevisionRequest, request: Request) -> dict[str, object]:
        try:
            _principal(request).require_scope("admin:write")
            if payload.workspace_id:
                _authorize(request, payload.workspace_id, scope="admin:write")
            if _respond_async(request):
                workspace_id = payload.workspace_id or (next(iter(_principal(request).workspace_ids), "admin") if _principal(request).workspace_ids else "admin")
                return JSONResponse(status_code=202, content=_service(request).submit_job(JobSubmitRequest(
                    workspace_id=workspace_id, kind="index.rebuild", payload=payload.model_dump(mode="json"),
                    actor=_actor(request), idempotency_key=request.headers.get("idempotency-key"),
                ), request_id=getattr(request.state, "request_id", None)))
            return _service(request).reindex(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/admin/model-migrations")
    def model_migration(payload: IndexRevisionRequest, request: Request) -> dict[str, object]:
        try:
            _principal(request).require_scope("admin:write")
            return _service(request).reindex(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/admin/models")
    def register_model(payload: ModelRegistrationRequest, request: Request) -> dict[str, object]:
        try:
            _principal(request).require_scope("admin:write")
            return _service(request).register_model(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/admin/experiment-manifests")
    def register_manifest(payload: ExperimentManifestRequest, request: Request) -> dict[str, object]:
        try:
            _principal(request).require_scope("admin:write")
            return _service(request).register_manifest(payload.model_copy(update={"actor": _actor(request)}))
        except Exception as error:
            raise _http_error(error) from error

    @router.post("/admin/compaction")
    def compaction(request: Request, actor: str = "system") -> dict[str, object]:
        try:
            _principal(request).require_scope("admin:write")
            return _service(request).store.compact(actor=_actor(request))
        except Exception as error:
            raise _http_error(error) from error

    @router.get("/admin/events")
    def events(request: Request, after_offset: int = 0, through_offset: int | None = None, limit: int | None = Query(default=None, ge=1, le=200), page_token: str | None = None) -> object:
        _principal(request).require_scope("admin:read")
        if limit is None and page_token is None:
            return [event.model_dump(mode="json") for event in _service(request).store.events(after_offset=after_offset, through_offset=through_offset)]
        scope = "admin:events"
        position = decode_page_token(page_token, scope=scope, max_limit=200).position if page_token else after_offset
        selected = _service(request).store.events(after_offset=position, through_offset=through_offset)
        page_limit = limit or 50
        next_token = encode_page_token(scope=scope, position=position + page_limit, limit=page_limit) if len(selected) > page_limit else None
        return {"items": [event.model_dump(mode="json") for event in selected[:page_limit]], "limit": page_limit, "next_page_token": next_token}

    app.include_router(router)

    @app.exception_handler(TraceStoreError)
    async def store_exception_handler(_: Request, error: TraceStoreError) -> JSONResponse:
        request = _
        converted = _http_error(error)
        detail = converted.detail
        code = None
        if isinstance(detail, dict):
            code = detail.get("code")
            detail = detail.get("message", detail)
        return JSONResponse(status_code=converted.status_code, content=_problem(request, status=converted.status_code, title="Trace V2 error", detail=detail, code=code))

    @app.exception_handler(AuthenticationError)
    async def authentication_exception_handler(request: Request, error: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content=_problem(request, status=error.status_code, title="Unauthorized", detail=str(error), code=error.code), headers={"WWW-Authenticate": "Bearer"})

    @app.exception_handler(AuthorizationError)
    async def authorization_exception_handler(request: Request, error: AuthorizationError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content=_problem(request, status=error.status_code, title="Forbidden", detail=str(error), code=error.code))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, error: HTTPException) -> JSONResponse:
        detail = error.detail
        code = None
        if isinstance(detail, dict):
            code = detail.get("code")
            detail = detail.get("message", detail)
        return JSONResponse(status_code=error.status_code, content=_problem(request, status=error.status_code, title="HTTP error", detail=detail, code=code), headers=error.headers or {})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, error: RequestValidationError) -> JSONResponse:
        # Pydantic v2 may include a ``ValueError`` in an error context.  Encode
        # the structured detail before handing it to Starlette so malformed
        # requests always receive a valid RFC-style JSON problem response.
        return JSONResponse(status_code=422, content=_problem(request, status=422, title="Validation error", detail=jsonable_encoder(error.errors()), code="validation_error"))

    return app
