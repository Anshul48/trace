"""Durable outbox worker primitives.

The production NATS JetStream adaptor and the embedded test adaptor share this
small at-least-once delivery loop.  Projection consumers remain idempotent by
recording the Spine event ID they have applied.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .models import HierarchyBuildRequest, SchemaProposalRequest
from .repository import Repository
from .service import TraceService
from .jobs import JobManager


class EventPublisher(Protocol):
    def __call__(self, topic: str, message: dict[str, Any]) -> Awaitable[None]: ...


class OutboxWorker:
    def __init__(self, store: Repository, publisher: EventPublisher) -> None:
        self.store = store
        self.publisher = publisher

    async def drain_once(self, *, limit: int = 100) -> dict[str, int]:
        published = failed = 0
        for item in self.store.claim_outbox(limit=limit):
            envelope = item["payload"]
            # Both embedded and PostgreSQL adapters persist an event envelope.
            # Preserve the immutable event ID at the top level and expose the
            # canonical payload without duplicating a nested ``payload`` key.
            canonical = envelope.get("payload", envelope) if isinstance(envelope, dict) else {}
            message = {"event_id": item["event_id"], "event_offset": item["event_offset"], **canonical}
            try:
                publisher = getattr(self.publisher, "publish", self.publisher)
                await publisher(item["topic"], message)
            except Exception:
                self.store.release_outbox(item["event_offset"])
                failed += 1
            else:
                self.store.mark_outbox_published(item["event_offset"])
                published += 1
        return {"published": published, "failed": failed}


class IdempotentProjectionConsumer:
    """Guard a projection handler with event-ID and revision deduplication."""

    def __init__(self, store: Repository, *, projection_name: str, workspace_id: str) -> None:
        self.store = store
        self.projection_name = projection_name
        self.workspace_id = workspace_id

    def apply(self, message: dict[str, Any], handler: Any, *, projection_revision: int = 1) -> bool:
        event_id = str(message["event_id"])
        offset = int(message.get("event_offset", message.get("offset", 0)))
        checkpoint = self.store.projection_checkpoint(self.projection_name, self.workspace_id)
        if checkpoint and offset <= int(checkpoint["last_applied_event"]):
            return False
        handler(message)
        return self.store.record_projection_event(
            projection_name=self.projection_name,
            event_id=event_id,
            event_offset=offset,
            workspace_id=self.workspace_id,
            projection_revision=projection_revision,
        )


class JobWorker:
    """Small worker facade shared by a local process and durable queue worker."""

    def __init__(self, service: TraceService) -> None:
        self.service = service

    def run_once(self, *, limit: int = 10, kind: str | None = None) -> dict[str, int]:
        return self.service.jobs.run_once(limit=limit, kind=kind)


class CognitiveProjectionWorker:
    """Explicit periodic work for rebuildable cognitive projections.

    It may create summaries and pending schema proposals, but it never promotes
    a proposal or mutates relation trust autonomously. A scheduler invokes this
    worker per workspace after ingestion/indexing has settled.
    """

    def __init__(self, service: TraceService) -> None:
        self.service = service

    def run_once(
        self,
        *,
        workspace_id: str,
        propose_schemas: bool = True,
        actor: str = "cognitive-worker",
    ) -> dict[str, Any]:
        hierarchy = self.service.build_hierarchy(HierarchyBuildRequest(workspace_id=workspace_id, actor=actor))
        schemas = (
            self.service.propose_schemas(SchemaProposalRequest(workspace_id=workspace_id, actor=actor))
            if propose_schemas else {"workspace_id": workspace_id, "proposals": []}
        )
        return {
            "workspace_id": workspace_id,
            "hierarchy_generation_id": hierarchy["generation_id"],
            "schema_proposal_count": len(schemas["proposals"]),
            "auto_promoted": 0,
        }
