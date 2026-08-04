"""Storage boundaries used by the Trace V2 application layer.

The embedded adapter is deliberately still useful for local development and
replay drills.  This module prevents the rest of the application from making
SQLite-specific assumptions and documents the small set of capabilities a
production repository must provide.

The protocols use ``Any`` for row-shaped values because the public contracts
are dictionaries today and a PostgreSQL implementation may use dataclasses or
record mappings internally.  They are runtime-checkable only at the coarse
interface level; correctness remains enforced by the repository's transaction
and event invariants.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Iterable, Protocol, Sequence


class Repository(Protocol):
    """Canonical and projection operations required by :class:`TraceService`.

    Implementations must make every canonical mutation and its outbox record
    part of one transaction.  Returned rows must be tenant-scoped by the
    repository, never by an untrusted caller-provided filter alone.
    """

    def transaction(self) -> AbstractContextManager[Any]: ...

    def ingest(self, **kwargs: Any) -> dict[str, Any]: ...

    def edit_node(self, **kwargs: Any) -> dict[str, Any]: ...

    def split_node(self, **kwargs: Any) -> list[dict[str, Any]]: ...

    def create_alias(self, **kwargs: Any) -> dict[str, Any]: ...

    def queryable_atoms(self, workspace_id: str | None, as_of_event: int | None = None) -> list[dict[str, Any]]: ...

    def current_nodes(self, workspace_id: str, as_of_event: int | None = None) -> list[dict[str, Any]]: ...

    def current_edges(self, workspace_id: str, as_of_event: int | None = None) -> list[dict[str, Any]]: ...

    def atom_versions(self, atom_version_ids: Sequence[str]) -> list[dict[str, Any]]: ...

    def dense_vectors(self, provider_id: str, atom_version_ids: Sequence[str]) -> dict[str, list[float]]: ...

    def upsert_dense_vectors(self, **kwargs: Any) -> int: ...

    def save_bundle(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_bundle(self, bundle_id: str, **kwargs: Any) -> dict[str, Any]: ...

    def feedback_scores(self, workspace_id: str, atom_version_ids: Sequence[str]) -> dict[str, float]: ...

    def create_job(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_job(self, job_id: str) -> dict[str, Any]: ...

    def list_jobs(self, **kwargs: Any) -> list[dict[str, Any]]: ...

    def claim_jobs(self, **kwargs: Any) -> list[dict[str, Any]]: ...

    def complete_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]: ...

    def fail_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]: ...

    def cancel_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]: ...

    def retry_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]: ...


class AttachmentStore(Protocol):
    """Private object storage for original and normalized ingress artifacts."""

    def put_bytes(self, raw: bytes, media_type: str, **kwargs: Any) -> dict[str, Any]: ...

    def put_text(self, text: str, media_type: str, **kwargs: Any) -> dict[str, Any]: ...


class LexicalIndex(Protocol):
    """Workspace-filtered lexical candidate provider."""

    provider_id: str

    def search(
        self,
        *,
        workspace_id: str,
        query: str,
        limit: int,
        visibility: Sequence[str] | None = None,
        facets: Sequence[str] | None = None,
        as_of_event: int | None = None,
        index_revision: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def upsert(self, documents: Iterable[dict[str, Any]], *, revision: str) -> int: ...


class DenseIndex(Protocol):
    """Workspace-filtered dense candidate provider."""

    provider_id: str

    def search(
        self,
        *,
        workspace_id: str,
        vector: Sequence[float],
        limit: int,
        visibility: Sequence[str] | None = None,
        facets: Sequence[str] | None = None,
        as_of_event: int | None = None,
        index_revision: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def upsert(self, vectors: Iterable[dict[str, Any]], *, revision: str) -> int: ...


class EventPublisher(Protocol):
    """Durable outbox publisher (NATS JetStream in production)."""

    async def publish(self, topic: str, message: dict[str, Any]) -> None: ...


class CoordinationStore(Protocol):
    """TTL coordination/cache boundary (Redis in production)."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None: ...

    def delete(self, key: str) -> None: ...
