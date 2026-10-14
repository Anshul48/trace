"""Optional production adapters for the Trace V2 boundaries.

The core package intentionally does not import infrastructure SDKs at module
import time.  Each adapter accepts an injected client for tests and lazily
loads its vendor SDK only when a deployment selects that adapter.  This keeps
the embedded correctness path dependency-light while making the production
topology concrete rather than merely a documentation promise.
"""

from __future__ import annotations

import asyncio
import base64
from contextvars import ContextVar
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .models import AppendResult, CognitivePolicy, EventRecord
from .cortex import canonical_pair
from .store import (
    ALLOWED_RELATIONS,
    STRUCTURAL_RELATIONS,
    IdempotencyConflict,
    InvariantViolation,
    NotFoundError,
    evaluate_temporal_visibility,
    normalize_valid_time,
    _digest,
    _json,
    _now,
)
from .migrations import MigrationRunner, assert_runtime_role, default_migration_root


# Compatibility export for deployments that imported this symbol before SQL
# migrations became the only bootstrap path.  The executable source of truth
# is migrations/001_trace_production.sql, not a Python-embedded schema.
def _baseline_schema_sql() -> str:
    return (default_migration_root() / "001_trace_production.sql").read_text(encoding="utf-8")


POSTGRES_SCHEMA = _baseline_schema_sql()


_runtime_workspace: ContextVar[str | None] = ContextVar("trace_runtime_workspace", default=None)


class ProductionAdapterError(RuntimeError):
    """Raised when an optional production dependency or operation is missing."""


class PostgresEventStore:
    """PostgreSQL event/outbox/job adapter.

    The canonical event spine and core projections are implemented here.
    ``delegate`` remains an explicit migration seam for deployments that need
    to move a projection independently; the adapter never silently falls back
    to SQLite.
    """

    def __init__(self, dsn: str | None = None, *, connection_factory: Any | None = None, delegate: Any | None = None, pool: Any | None = None) -> None:
        self.dsn = dsn or os.environ.get("TRACE_POSTGRES_DSN")
        self.connection_factory = connection_factory
        self.delegate = delegate
        self.pool = pool
        if not self.dsn and self.connection_factory is None:
            raise ValueError("TRACE_POSTGRES_DSN or connection_factory is required")
        if os.environ.get("TRACE_PRODUCTION_MODE", "false").lower() == "true":
            runtime_role = os.environ.get("TRACE_POSTGRES_RUNTIME_ROLE")
            migrator_role = os.environ.get("TRACE_POSTGRES_MIGRATION_ROLE")
            if runtime_role and migrator_role and runtime_role == migrator_role:
                raise ValueError("runtime and migration PostgreSQL roles must be distinct in production")
        if self.pool is None and connection_factory is None and os.environ.get("TRACE_POSTGRES_POOL_ENABLED", "false").lower() == "true":
            try:
                from psycopg_pool import ConnectionPool
            except ImportError as error:  # pragma: no cover - optional deployment dependency
                raise ProductionAdapterError("psycopg_pool is required when TRACE_POSTGRES_POOL_ENABLED=true") from error
            self.pool = ConnectionPool(
                conninfo=self.dsn,
                min_size=max(1, int(os.environ.get("TRACE_POSTGRES_POOL_MIN", "2"))),
                max_size=max(2, int(os.environ.get("TRACE_POSTGRES_POOL_MAX", "20"))),
                kwargs={"autocommit": False},
            )

    def _connect(self) -> Any:
        if self.pool is not None:
            return self.pool.getconn()
        if self.connection_factory is not None:
            return self.connection_factory()
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover - optional production dependency
            raise ProductionAdapterError("psycopg is required for PostgresEventStore") from error
        return psycopg.connect(self.dsn)

    @contextmanager
    def authorization_scope(self, workspace_id: str) -> Iterator[None]:
        """Bind one explicit workspace to all PostgreSQL reads in this scope.

        This is the repository counterpart of ``AuthorizationContext``. It is
        intentionally unable to represent a wildcard tenant; missing scope
        fails closed before a query can reach a row-policy-protected table.
        """

        if not workspace_id or workspace_id == "*":
            raise InvariantViolation("PostgreSQL operations require one explicit workspace scope")
        token = _runtime_workspace.set(workspace_id)
        try:
            yield
        finally:
            _runtime_workspace.reset(token)

    @staticmethod
    def _set_workspace(cursor: Any, workspace_id: str | None = None) -> str:
        selected = workspace_id or _runtime_workspace.get()
        if not selected or selected == "*":
            raise InvariantViolation("PostgreSQL operation has no explicit workspace scope")
        cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (selected,))
        return selected

    @staticmethod
    def _set_api_key_lookup(cursor: Any, key_hash: str) -> None:
        """Bind the narrowly-scoped pre-workspace API-key lookup policy.

        Authentication happens before an :class:`AuthorizationContext` exists.
        The matching RLS policy in migration 003 permits only an equality
        lookup of this opaque 64-character digest; it cannot enumerate a
        tenant or become a wildcard read path.
        """

        if not re.fullmatch(r"[0-9a-f]{64}", key_hash):
            raise InvariantViolation("API key hash must be a SHA-256 digest")
        cursor.execute("SELECT set_config('trace.auth_lookup', 'api_key', true)")
        cursor.execute("SELECT set_config('trace.api_key_hash', %s, true)", (key_hash,))

    @contextmanager
    def connection(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if self.pool is not None:
                self.pool.putconn(connection)
            else:
                connection.close()

    def initialize(self) -> None:
        with self.connection() as conn:
            MigrationRunner().apply(conn)

    def verify_runtime_role(self) -> None:
        """Ensure API/worker connections cannot bypass forced tenant RLS."""

        with self.connection() as conn:
            assert_runtime_role(conn, expected_role=os.environ.get("TRACE_POSTGRES_RUNTIME_ROLE"))

    def _call_delegate(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if self.delegate is None or not hasattr(self.delegate, name):
            raise ProductionAdapterError(
                f"PostgresEventStore operation {name!r} requires the PostgreSQL projection adapter"
            )
        return getattr(self.delegate, name)(*args, **kwargs)

    # Rich canonical/projection methods remain swappable during migration.
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if self.delegate is not None and hasattr(self.delegate, name):
            return getattr(self.delegate, name)
        raise AttributeError(name)

    @staticmethod
    def _json_value(value: Any, default: Any = None) -> Any:
        if value is None:
            return {} if default is None else default
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)

    @staticmethod
    def _cursor_mapping(cursor: Any, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        columns: list[str] = []
        for description in cursor.description:
            name = getattr(description, "name", None)
            columns.append(str(name if name is not None else description[0]))
        return dict(
            zip(
                columns,
                (str(val) if isinstance(val, uuid.UUID) else val for val in row),
                strict=True,
            )
        )

    def _append_event_in_connection(
        self,
        conn: Any,
        *,
        stream_id: str,
        event_type: str,
        payload: dict[str, Any],
        actor: str = "system",
        causation_id: str | None = None,
        correlation_id: str | None = None,
        schema_version: int = 1,
        idempotency_key: str | None = None,
    ) -> AppendResult:
        """Append an event and its outbox message on an existing transaction."""

        workspace_id = str(payload.get("workspace_id") or stream_id.split(":", 1)[-1])
        payload_hash = _digest(payload)
        with conn.cursor() as cursor:
            cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
            if idempotency_key:
                cursor.execute(
                    "SELECT event_id,event_offset,stream_sequence,payload_hash,event_type FROM trace_events WHERE workspace_id=%s AND idempotency_key=%s",
                    (workspace_id, idempotency_key),
                )
                existing = cursor.fetchone()
                if existing:
                    event_id, offset, sequence, existing_hash, existing_type = existing
                    if existing_hash != payload_hash or existing_type != event_type:
                        raise IdempotencyConflict("idempotency key was reused with a different event")
                    return AppendResult(event_id=str(event_id), offset=int(offset), stream_sequence=int(sequence), duplicate=True)
            event_id = str(uuid.uuid4())
            occurred_at = datetime.now(UTC)
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (stream_id,))
            cursor.execute(
                "SELECT COALESCE(MAX(stream_sequence),0)+1 FROM trace_events WHERE stream_id=%s",
                (stream_id,),
            )
            sequence = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO trace_events(
                    event_id,workspace_id,stream_id,stream_sequence,event_type,occurred_at,
                    actor,causation_id,correlation_id,schema_version,payload,payload_hash,idempotency_key
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                RETURNING event_offset""",
                (
                    event_id, workspace_id, stream_id, sequence, event_type, occurred_at,
                    actor, causation_id, correlation_id, schema_version,
                    json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str), payload_hash, idempotency_key,
                ),
            )
            offset = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO trace_outbox(event_offset,event_id,workspace_id,topic,payload,available_at)
                   VALUES (%s,%s,%s,%s,%s::jsonb,%s)""",
                (offset, event_id, workspace_id, event_type, json.dumps({"event_id": event_id, "offset": offset, "payload": payload}, default=str), occurred_at),
            )
            cursor.execute(
                "INSERT INTO trace_event_keys(event_id,workspace_id,idempotency_key,event_offset,occurred_at) VALUES (%s,%s,%s,%s,%s)",
                (event_id, workspace_id, idempotency_key, offset, occurred_at),
            )
            return AppendResult(event_id=event_id, offset=offset, stream_sequence=sequence)

    def append_event(
        self,
        *,
        stream_id: str,
        event_type: str,
        payload: dict[str, Any],
        actor: str = "system",
        causation_id: str | None = None,
        correlation_id: str | None = None,
        schema_version: int = 1,
        idempotency_key: str | None = None,
    ) -> AppendResult:
        with self.connection() as conn:
            return self._append_event_in_connection(
                conn, stream_id=stream_id, event_type=event_type, payload=payload,
                actor=actor, causation_id=causation_id, correlation_id=correlation_id,
                schema_version=schema_version, idempotency_key=idempotency_key,
            )

    def events(self, *, after_offset: int = 0, through_offset: int | None = None) -> list[EventRecord]:
        sql = "SELECT event_id,event_offset,stream_id,stream_sequence,event_type,occurred_at,actor,causation_id,correlation_id,schema_version,payload,payload_hash,idempotency_key FROM trace_events WHERE event_offset>%s"
        values: list[Any] = [after_offset]
        if through_offset is not None:
            sql += " AND event_offset<=%s"
            values.append(through_offset)
        sql += " ORDER BY event_offset"
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute(sql, values)
                rows = cursor.fetchall()
        records: list[EventRecord] = []
        for row in rows:
            payload = row[10] if isinstance(row[10], dict) else json.loads(row[10])
            records.append(EventRecord(
                event_id=str(row[0]), offset=int(row[1]), stream_id=row[2], stream_sequence=int(row[3]),
                event_type=row[4], occurred_at=row[5], actor=row[6], causation_id=str(row[7]) if row[7] else None,
                correlation_id=str(row[8]) if row[8] else None, schema_version=int(row[9]), payload=payload,
                payload_hash=row[11], idempotency_key=row[12],
            ))
        return records

    def last_event_offset(self) -> int:
        if _runtime_workspace.get() is None:
            # Health endpoints intentionally reveal no tenant event volume.
            return 0
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT COALESCE(MAX(event_offset),0) FROM trace_events")
                return int(cursor.fetchone()[0])

    def outbox_status(self) -> dict[str, int]:
        if _runtime_workspace.get() is None:
            return {}
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT status,COUNT(*) FROM trace_outbox GROUP BY status")
                return {str(status): int(count) for status, count in cursor.fetchall()}

    def projection_status(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        if workspace_id is None and _runtime_workspace.get() is None:
            return []
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                if workspace_id:
                    cursor.execute("SELECT projection_name,workspace_id,last_applied_event,revision,updated_at FROM trace_projection_revisions WHERE workspace_id=%s ORDER BY projection_name", (workspace_id,))
                else:
                    cursor.execute("SELECT projection_name,workspace_id,last_applied_event,revision,updated_at FROM trace_projection_revisions ORDER BY workspace_id,projection_name")
                return [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]

    def workspace_ids(self) -> list[str]:
        if _runtime_workspace.get() is None:
            return []
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT DISTINCT workspace_id FROM trace_nodes ORDER BY workspace_id")
                return [str(row[0]) for row in cursor.fetchall()]

    @classmethod
    def _pg_atom_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        if "atom_version_id" in result and result["atom_version_id"] is not None:
            result["atom_version_id"] = str(result["atom_version_id"])
        if "node_id" in result and result["node_id"] is not None:
            result["node_id"] = str(result["node_id"])
        result["properties"] = cls._json_value(result.pop("properties"), {})
        result["facets"] = cls._json_value(result.pop("facets"), [])
        result["security"] = cls._json_value(result.pop("security"), {})
        return result


    @classmethod
    def _pg_anchor_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def _pg_atoms_query(
        self,
        cursor: Any,
        *,
        workspace_id: str | None,
        as_of_event: int | None,
        atom_ids: Sequence[str] | None = None,
        all_versions: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["n.facets @> '[\"atom\"]'::jsonb"]
        values: list[Any] = []
        if workspace_id is not None:
            clauses.append("n.workspace_id=%s")
            values.append(workspace_id)
        if as_of_event is not None:
            clauses.append("nv.created_event_offset<=%s")
            values.append(as_of_event)
        if atom_ids is not None:
            if not atom_ids:
                return []
            placeholders = ",".join("%s" for _ in atom_ids)
            clauses.append(f"nv.atom_version_id IN ({placeholders})")
            values.extend(atom_ids)
            cursor.execute(
                f"""SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                           n.workspace_id,n.facets,n.security
                    FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                    WHERE {' AND '.join(clauses)} ORDER BY nv.created_event_offset DESC""",
                values,
            )
            return [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]
        if all_versions:
            cursor.execute(
                f"""SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                           n.workspace_id,n.facets,n.security
                    FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                    WHERE {' AND '.join(clauses)}
                    ORDER BY nv.node_id,nv.version DESC,nv.created_event_offset DESC""",
                values,
            )
            return [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]
        cursor.execute(
            f"""WITH ranked AS (
                SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                       n.workspace_id,n.facets,n.security,
                       ROW_NUMBER() OVER (PARTITION BY nv.node_id ORDER BY nv.version DESC) AS rank
                FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                WHERE {' AND '.join(clauses)}
            ) SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset,workspace_id,facets,security
              FROM ranked WHERE rank=1 ORDER BY created_event_offset DESC""",
            values,
        )
        return [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]

    @classmethod
    def _pg_lifecycle_row(cls, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        result = dict(row)
        for key in (
            "atom_version_id",
            "predecessor_atom_version_id",
            "superseded_by_atom_version_id",
        ):
            value = result.get(key)
            if value is not None:
                result[key] = str(value)
        for key in ("valid_from", "valid_to", "created_at"):
            value = result.get(key)
            if hasattr(value, "isoformat"):
                result[key] = value.isoformat()
        result["valid_provenance"] = cls._json_value(result.pop("valid_provenance", {}), {})
        erasure_receipt = result.pop("erasure_receipt", None)
        result["erasure_receipt"] = None if erasure_receipt is None else cls._json_value(erasure_receipt, {})
        result["valid_time"] = {
            "valid_from": result.get("valid_from"),
            "valid_to": result.get("valid_to"),
            "precision": result.get("valid_precision", "unknown"),
            "confidence": result.get("valid_confidence", "unknown"),
            "provenance": result.get("valid_provenance", {}),
        }
        return result

    def _pg_historical_source_state(self, cursor: Any, atom_version_id: str, as_of_event: int) -> str | None:
        cursor.execute(
            """SELECT event_type,payload FROM trace_events
               WHERE event_offset<=%s
                 AND event_type IN ('source.lifecycle_changed','source.lifecycle_initialized')
                 AND payload->>'atom_version_id'=%s
               ORDER BY event_offset""",
            (int(as_of_event), atom_version_id),
        )
        state: str | None = None
        for event_type, payload in cursor.fetchall():
            del event_type
            value = payload if isinstance(payload, dict) else json.loads(payload)
            state = str(value.get("state") or state or "active")
        if state is None:
            cursor.execute(
                "SELECT state,changed_event_offset FROM trace_source_lifecycle WHERE atom_version_id=%s",
                (atom_version_id,),
            )
            current = cursor.fetchone()
            if current:
                state = str(current[0]) if int(current[1] or 0) <= int(as_of_event) else "active"
        return state

    def get_source_lifecycle(self, atom_version_id: str, *, as_of_event: int | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_source_lifecycle"):
            return self.delegate.get_source_lifecycle(atom_version_id, as_of_event=as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT * FROM trace_source_lifecycle WHERE atom_version_id=%s", (atom_version_id,))
                current = self._pg_lifecycle_row(self._cursor_mapping(cursor, cursor.fetchone()))
                if current is None:
                    raise NotFoundError(f"source lifecycle for {atom_version_id} was not found")
                state = self._pg_historical_source_state(cursor, atom_version_id, int(as_of_event)) if as_of_event is not None else current["state"]
                result = dict(current)
                result["state"] = state
                result["requested_as_of_event"] = as_of_event
                return result

    @staticmethod
    def _pg_authorization_events(
        cursor: Any,
        node_id: str,
        node_created_event: int,
        as_of_event: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        def fetch_event(query: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
            cursor.execute(query, parameters)
            row = cursor.fetchone()
            if not row:
                return None
            payload = row[1] if isinstance(row[1], dict) else json.loads(row[1])
            if str(payload.get("node_id") or "") != node_id:
                return None
            return {"event_offset": int(row[0]), "payload": payload}

        initial = fetch_event(
            """SELECT event_offset,payload FROM trace_events
                 WHERE event_offset=%s AND event_type='node.created' LIMIT 1""",
            (int(node_created_event),),
        )
        current = fetch_event(
            """SELECT event_offset,payload FROM trace_events
                 WHERE stream_id=%s AND event_type='node.security_changed'
                 ORDER BY event_offset DESC LIMIT 1""",
            (f"node:{node_id}",),
        )
        if as_of_event is None:
            historical = current
        else:
            historical = fetch_event(
                """SELECT event_offset,payload FROM trace_events
                     WHERE stream_id=%s AND event_type='node.security_changed' AND event_offset<=%s
                     ORDER BY event_offset DESC LIMIT 1""",
                (f"node:{node_id}", int(as_of_event)),
            )
        return initial, current, historical

    def transition_source_authorization(
        self,
        atom_version_id: str,
        *,
        visibility: str,
        actor: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "transition_source_authorization"):
            return self.delegate.transition_source_authorization(
                atom_version_id, visibility=visibility, actor=actor, reason=reason,
            )
        visibility = str(visibility).strip()
        if not visibility:
            raise InvariantViolation("source authorization visibility must be non-empty")
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute(
                    """SELECT nv.node_id,n.workspace_id,n.security,n.created_event_offset
                         FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                        WHERE nv.atom_version_id=%s FOR UPDATE OF n""",
                    (atom_version_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise NotFoundError(f"atom version {atom_version_id} was not found")
                node_id, workspace_id = str(row[0]), str(row[1])
                previous = self._json_value(row[2], {})
                security = {**previous, "visibility": visibility, "actor": actor}
                if previous.get("visibility") == visibility:
                    initial, current, _ = self._pg_authorization_events(cursor, node_id, int(row[3]))
                    revision = current["event_offset"] if current else (initial or {}).get("event_offset")
                    return {
                        "atom_version_id": atom_version_id,
                        "node_id": node_id,
                        "workspace_id": workspace_id,
                        "security": previous,
                        "authorization_revision_event": revision,
                        "changed": False,
                    }
            event = self._append_event_in_connection(
                conn,
                stream_id=f"node:{node_id}",
                event_type="node.security_changed",
                payload={
                    "node_id": node_id,
                    "workspace_id": workspace_id,
                    "atom_version_id": atom_version_id,
                    "previous_security": previous,
                    "security": security,
                    "reason": reason,
                },
                actor=actor,
            )
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    "UPDATE trace_nodes SET security=%s::jsonb WHERE node_id=%s",
                    (json.dumps(security), node_id),
                )
                cursor.execute(
                    "UPDATE trace_hot_inbox SET security=%s::jsonb WHERE node_id=%s",
                    (json.dumps(security), node_id),
                )
            return {
                "atom_version_id": atom_version_id,
                "node_id": node_id,
                "workspace_id": workspace_id,
                "security": security,
                "authorization_revision_event": event.offset,
                "changed": True,
            }

    def resolve_source_authorization(
        self,
        atom_version_id: str,
        *,
        as_of_event: int | None = None,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "resolve_source_authorization"):
            return self.delegate.resolve_source_authorization(atom_version_id, as_of_event=as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute(
                    """SELECT nv.node_id,n.security,n.created_event_offset
                         FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                        WHERE nv.atom_version_id=%s""",
                    (atom_version_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise NotFoundError(f"atom version {atom_version_id} was not found")
                node_id = str(row[0])
                current_security = self._json_value(row[1], {})
                node_created_event = int(row[2])
                initial, current, historical = self._pg_authorization_events(
                    cursor, node_id, node_created_event, as_of_event
                )
        current_revision = (
            current["event_offset"] if current
            else (initial or {}).get("event_offset", node_created_event)
        )
        if as_of_event is None:
            if not current_security.get("visibility"):
                return {
                    "available": False,
                    "requested_as_of_event": None,
                    "current_authorization_revision_event": current_revision,
                    "exclusion_reason": "current_authorization_unavailable",
                }
            return {
                "available": True,
                "requested_as_of_event": None,
                "historical_security": current_security,
                "current_security": current_security,
                "historical_authorization_revision_event": current_revision,
                "current_authorization_revision_event": current_revision,
                "historical_resolution": "current",
            }
        requested = int(as_of_event)
        if requested < node_created_event:
            return {
                "available": False,
                "requested_as_of_event": requested,
                "current_security": current_security,
                "current_authorization_revision_event": current_revision,
                "exclusion_reason": "historical_authorization_unavailable",
            }
        initial_security = dict((initial or {}).get("payload", {}).get("security") or {})
        current_event_security = dict((current or {}).get("payload", {}).get("security") or {})
        if (
            not initial_security.get("visibility")
            or (current is not None and not current_event_security.get("visibility"))
        ):
            return {
                "available": False,
                "requested_as_of_event": requested,
                "current_authorization_revision_event": current_revision,
                "exclusion_reason": "historical_authorization_unavailable",
            }
        if historical:
            historical_security = dict(historical["payload"].get("security") or {})
            historical_revision = historical["event_offset"]
            resolution = "latest_change_at_or_before_requested_event"
        elif initial and initial["event_offset"] <= requested:
            historical_security = initial_security
            historical_revision = initial["event_offset"]
            resolution = "node_created_event"
        else:
            return {
                "available": False,
                "requested_as_of_event": requested,
                "current_authorization_revision_event": current_revision,
                "exclusion_reason": "historical_authorization_unavailable",
            }
        if not historical_security.get("visibility") or not current_security.get("visibility"):
            return {
                "available": False,
                "requested_as_of_event": requested,
                "current_authorization_revision_event": current_revision,
                "exclusion_reason": "historical_authorization_unavailable",
            }
        return {
            "available": True,
            "requested_as_of_event": requested,
            "historical_security": historical_security,
            "current_security": current_security,
            "historical_authorization_revision_event": historical_revision,
            "current_authorization_revision_event": current_revision,
            "historical_resolution": resolution,
        }

    def temporal_visibility(
        self,
        atom: dict[str, Any],
        *,
        as_of_event: int | None = None,
        valid_at: Any | None = None,
        valid_from: Any | None = None,
        valid_to: Any | None = None,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "temporal_visibility"):
            return self.delegate.temporal_visibility(
                atom, as_of_event=as_of_event, valid_at=valid_at, valid_from=valid_from, valid_to=valid_to,
            )
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, str(atom.get("workspace_id") or _runtime_workspace.get() or ""))
                cursor.execute("SELECT * FROM trace_source_lifecycle WHERE atom_version_id=%s", (atom.get("atom_version_id"),))
                current = self._pg_lifecycle_row(self._cursor_mapping(cursor, cursor.fetchone())) or {"state": "active"}
                historical = self._pg_historical_source_state(cursor, str(atom.get("atom_version_id")), int(as_of_event)) if as_of_event is not None else None
        return evaluate_temporal_visibility(
            atom,
            current_lifecycle=current,
            historical_state=historical,
            as_of_event=as_of_event,
            valid_at=valid_at,
            valid_from=valid_from,
            valid_to=valid_to,
        )

    def _change_source_lifecycle_in_connection(
        self,
        conn: Any,
        *,
        atom_version_id: str,
        state: str,
        actor: str,
        reason: str | None = None,
        superseded_by_atom_version_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        allowed = {"active", "superseded", "revoked", "tombstoned", "conflicted", "redacted_purged"}
        if state not in allowed:
            raise InvariantViolation(f"unsupported source lifecycle state {state!r}")
        with conn.cursor() as cursor:
            self._set_workspace(cursor)
            cursor.execute("SELECT * FROM trace_source_lifecycle WHERE atom_version_id=%s FOR UPDATE", (atom_version_id,))
            current = self._pg_lifecycle_row(self._cursor_mapping(cursor, cursor.fetchone()))
            if current is None:
                raise NotFoundError(f"source lifecycle for {atom_version_id} was not found")
            cursor.execute("SELECT workspace_id FROM trace_nodes n JOIN trace_node_versions nv ON nv.node_id=n.node_id WHERE nv.atom_version_id=%s", (atom_version_id,))
            node = self._cursor_mapping(cursor, cursor.fetchone())
        previous = str(current["state"])
        if previous == "redacted_purged":
            raise InvariantViolation("redacted/purged source content cannot transition")
        if state == "active":
            raise InvariantViolation("source lifecycle cannot be resurrected through a normal transition")
        if state == "superseded" and not superseded_by_atom_version_id:
            raise InvariantViolation("superseded source requires an explicit successor atom version")
        if previous == state and not reason:
            return current | {"event_offset": current.get("changed_event_offset")}
        event = self._append_event_in_connection(
            conn,
            stream_id=f"node:{atom_version_id}",
            event_type="source.lifecycle_changed",
            payload={
                "atom_version_id": atom_version_id, "workspace_id": node["workspace_id"],
                "previous_state": previous, "state": state, "reason": reason,
                "superseded_by_atom_version_id": superseded_by_atom_version_id,
            },
            actor=actor,
            idempotency_key=idempotency_key,
        )
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE trace_source_lifecycle SET state=%s,superseded_by_atom_version_id=COALESCE(%s,superseded_by_atom_version_id),changed_event_offset=%s WHERE atom_version_id=%s",
                (state, superseded_by_atom_version_id, event.offset, atom_version_id),
            )
            if state in {"revoked", "tombstoned", "redacted_purged"}:
                cursor.execute("DELETE FROM trace_hot_inbox WHERE atom_version_id=%s", (atom_version_id,))
            cursor.execute("SELECT * FROM trace_source_lifecycle WHERE atom_version_id=%s", (atom_version_id,))
            result = self._pg_lifecycle_row(self._cursor_mapping(cursor, cursor.fetchone()))
        return (result or current) | {"event_offset": event.offset}

    def transition_source_lifecycle(self, atom_version_id: str, *, state: str, actor: str = "system", reason: str | None = None, superseded_by_atom_version_id: str | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "transition_source_lifecycle"):
            return self.delegate.transition_source_lifecycle(
                atom_version_id,
                state=state,
                actor=actor,
                reason=reason,
                superseded_by_atom_version_id=superseded_by_atom_version_id,
                idempotency_key=idempotency_key,
            )
        with self.connection() as conn:
            return self._change_source_lifecycle_in_connection(
                conn,
                atom_version_id=atom_version_id,
                state=state,
                actor=actor,
                reason=reason,
                superseded_by_atom_version_id=superseded_by_atom_version_id,
                idempotency_key=idempotency_key,
            )

    def get_erasure_operation(self, workspace_id: str, atom_version_id: str) -> dict[str, Any] | None:
        if self.delegate is not None and hasattr(self.delegate, "get_erasure_operation"):
            return self.delegate.get_erasure_operation(workspace_id, atom_version_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(
                    "SELECT * FROM trace_erasure_operations WHERE workspace_id=%s AND atom_version_id=%s",
                    (workspace_id, str(atom_version_id)),
                )
                row = self._cursor_mapping(cursor, cursor.fetchone())
                if not row:
                    return None
                return {
                    "operation_id": str(row["operation_id"]),
                    "workspace_id": str(row["workspace_id"]),
                    "atom_version_id": str(row["atom_version_id"]),
                    "state": str(row["state"]),
                    "object_key": row.get("object_key"),
                    "external_targets": self._json_value(row.get("external_targets"), []),
                    "erasure_receipt": self._json_value(row.get("erasure_receipt")),
                    "event_offset": row.get("event_offset"),
                    "failure_detail": row.get("failure_detail"),
                    "created_at": str(row.get("created_at")),
                    "updated_at": str(row.get("updated_at")),
                }

    def get_erasure_operation_by_atom(self, atom_version_id: str) -> dict[str, Any] | None:
        if self.delegate is not None and hasattr(self.delegate, "get_erasure_operation_by_atom"):
            return self.delegate.get_erasure_operation_by_atom(atom_version_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute(
                    "SELECT * FROM trace_erasure_operations WHERE atom_version_id=%s",
                    (str(atom_version_id),),
                )
                row = self._cursor_mapping(cursor, cursor.fetchone())
                if not row:
                    return None
                return {
                    "operation_id": str(row["operation_id"]),
                    "workspace_id": str(row["workspace_id"]),
                    "atom_version_id": str(row["atom_version_id"]),
                    "state": str(row["state"]),
                    "object_key": row.get("object_key"),
                    "external_targets": self._json_value(row.get("external_targets"), []),
                    "erasure_receipt": self._json_value(row.get("erasure_receipt")),
                    "event_offset": row.get("event_offset"),
                    "failure_detail": row.get("failure_detail"),
                    "created_at": str(row.get("created_at")),
                    "updated_at": str(row.get("updated_at")),
                }

    def create_or_acquire_erasure_operation(
        self,
        workspace_id: str,
        atom_version_id: str,
        object_key: str | None = None,
        external_targets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_or_acquire_erasure_operation"):
            return self.delegate.create_or_acquire_erasure_operation(workspace_id, atom_version_id, object_key, external_targets)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(
                    "SELECT * FROM trace_erasure_operations WHERE workspace_id=%s AND atom_version_id=%s FOR UPDATE",
                    (workspace_id, str(atom_version_id)),
                )
                existing = self._cursor_mapping(cursor, cursor.fetchone())
                if existing:
                    return {
                        "operation_id": str(existing["operation_id"]),
                        "workspace_id": str(existing["workspace_id"]),
                        "atom_version_id": str(existing["atom_version_id"]),
                        "state": str(existing["state"]),
                        "object_key": existing.get("object_key"),
                        "external_targets": self._json_value(existing.get("external_targets"), []),
                        "erasure_receipt": self._json_value(existing.get("erasure_receipt")),
                        "event_offset": existing.get("event_offset"),
                        "failure_detail": existing.get("failure_detail"),
                    }
                op_id = str(uuid.uuid4())
                cursor.execute(
                    """INSERT INTO trace_erasure_operations(
                        operation_id, workspace_id, atom_version_id, state, object_key,
                        external_targets, failure_detail, created_at, updated_at
                    ) VALUES (%s, %s, %s, 'pending', %s, %s::jsonb, NULL, NOW(), NOW())
                    ON CONFLICT (workspace_id, atom_version_id) DO UPDATE SET updated_at=NOW()
                    RETURNING *""",
                    (op_id, workspace_id, str(atom_version_id), object_key, json.dumps(external_targets or [])),
                )
                row = self._cursor_mapping(cursor, cursor.fetchone())
                return {
                    "operation_id": str(row["operation_id"]),
                    "workspace_id": str(row["workspace_id"]),
                    "atom_version_id": str(row["atom_version_id"]),
                    "state": str(row["state"]),
                    "object_key": row.get("object_key"),
                    "external_targets": self._json_value(row.get("external_targets"), []),
                    "erasure_receipt": self._json_value(row.get("erasure_receipt")),
                    "event_offset": row.get("event_offset"),
                    "failure_detail": row.get("failure_detail"),
                }

    def update_erasure_operation_state(self, operation_id: str, state: str, failure_detail: str | None = None) -> None:
        if self.delegate is not None and hasattr(self.delegate, "update_erasure_operation_state"):
            return self.delegate.update_erasure_operation_state(operation_id, state, failure_detail)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute(
                    "UPDATE trace_erasure_operations SET state=%s, failure_detail=%s, updated_at=NOW() WHERE operation_id=%s",
                    (state, failure_detail, str(operation_id)),
                )

    def finalize_erasure_operation(
        self,
        operation_id: str,
        *,
        signing_key: str,
        actor: str = "system",
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "finalize_erasure_operation"):
            return self.delegate.finalize_erasure_operation(operation_id, signing_key=signing_key, actor=actor, reason=reason)
        if not signing_key:
            raise InvariantViolation("compliance erasure requires a configured signing key")
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT * FROM trace_erasure_operations WHERE operation_id=%s FOR UPDATE", (str(operation_id),))
                op = self._cursor_mapping(cursor, cursor.fetchone())
                if not op:
                    raise NotFoundError(f"erasure operation {operation_id} was not found")
                workspace_id = str(op["workspace_id"])
                atom_version_id = str(op["atom_version_id"])
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                if op["state"] == "completed":
                    return {
                        "state": "redacted_purged",
                        "atom_version_id": atom_version_id,
                        "workspace_id": workspace_id,
                        "erasure_receipt": self._json_value(op.get("erasure_receipt")),
                        "event_offset": op.get("event_offset"),
                    }
                cursor.execute(
                    """SELECT nv.content_hash,n.workspace_id,nv.node_id,nv.properties
                       FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                       WHERE nv.atom_version_id=%s FOR UPDATE""",
                    (atom_version_id,),
                )
                source = self._cursor_mapping(cursor, cursor.fetchone())
                if not source:
                    raise NotFoundError(f"atom version {atom_version_id} was not found")
                cursor.execute("SELECT * FROM trace_source_lifecycle WHERE atom_version_id=%s FOR UPDATE", (atom_version_id,))
                current = self._pg_lifecycle_row(self._cursor_mapping(cursor, cursor.fetchone()))
                if current is None:
                    raise NotFoundError(f"source lifecycle for {atom_version_id} was not found")

            # Strict non-content allow-list receipt
            receipt_payload = {
                "receipt_id": str(uuid.uuid4()),
                "atom_version_id": str(atom_version_id),
                "workspace_id": str(workspace_id),
                "action": "redacted_purged",
                "issued_at": _now(),
            }
            signature = hmac.new(
                signing_key.encode("utf-8"),
                _json(receipt_payload).encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
            receipt = {**receipt_payload, "signature": signature}

            event = self._append_event_in_connection(
                conn,
                stream_id=f"node:{atom_version_id}",
                event_type="source.erasure_applied",
                payload={"atom_version_id": atom_version_id, "workspace_id": workspace_id, "receipt": receipt},
                actor=actor,
            )
            properties = self._json_value(source.get("properties"), {})
            redacted = {
                "temporal": properties.get("temporal", normalize_valid_time(None)),
                "erasure_receipt_id": receipt["receipt_id"],
                "erasure_event_offset": event.offset,
            }
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute("UPDATE trace_node_versions SET content='',properties=%s::jsonb WHERE atom_version_id=%s", (json.dumps(redacted), atom_version_id))
                cursor.execute(
                    "UPDATE trace_source_lifecycle SET state='redacted_purged',erasure_receipt=%s::jsonb,changed_event_offset=%s WHERE atom_version_id=%s",
                    (json.dumps(receipt), event.offset, atom_version_id),
                )
                cursor.execute("DELETE FROM trace_hot_inbox WHERE atom_version_id=%s", (atom_version_id,))
                cursor.execute("DELETE FROM trace_dense_vectors WHERE atom_version_id=%s", (atom_version_id,))
                cursor.execute("DELETE FROM trace_activation_priors WHERE atom_version_id=%s", (atom_version_id,))
                cursor.execute("DELETE FROM trace_affinity_edges WHERE left_atom_version_id=%s OR right_atom_version_id=%s", (atom_version_id, atom_version_id))
                cursor.execute("DELETE FROM trace_evidence_anchors WHERE source_atom_version_id=%s", (atom_version_id,))
                cursor.execute(
                    "UPDATE trace_edge_versions SET status='tombstoned',properties=jsonb_build_object('erasure_receipt_id',%s::text) WHERE source_node_id=%s OR target_node_id=%s",
                    (receipt["receipt_id"], source["node_id"], source["node_id"]),
                )

                cursor.execute(
                    """WITH doomed AS (
                           SELECT projection_object_id FROM trace_projection_objects
                           WHERE workspace_id=%s AND source_atom_version_ids @> %s::jsonb
                       ) DELETE FROM trace_projection_memberships WHERE parent_projection_object_id IN (SELECT projection_object_id FROM doomed) OR child_id IN (SELECT projection_object_id FROM doomed)""",
                    (workspace_id, json.dumps([atom_version_id])),
                )
                cursor.execute(
                    "DELETE FROM trace_projection_objects WHERE workspace_id=%s AND source_atom_version_ids @> %s::jsonb",
                    (workspace_id, json.dumps([atom_version_id])),
                )
                attachment_id = properties.get("attachment_id")
                if attachment_id:
                    cursor.execute(
                        """DELETE FROM trace_attachments WHERE attachment_id=%s
                           AND NOT EXISTS (SELECT 1 FROM trace_node_versions WHERE properties->>'attachment_id'=%s AND content<>'' )""",
                        (attachment_id, str(attachment_id)),
                    )
                # Mark operation completed and scrub object_key and external_targets
                cursor.execute(
                    """UPDATE trace_erasure_operations
                       SET state='completed', erasure_receipt=%s::jsonb, event_offset=%s, object_key=NULL, external_targets='[]'::jsonb, failure_detail=NULL, updated_at=NOW()
                       WHERE operation_id=%s""",
                    (json.dumps(receipt), event.offset, str(operation_id)),
                )
            return {
                "state": "redacted_purged",
                "atom_version_id": atom_version_id,
                "workspace_id": workspace_id,
                "erasure_receipt": receipt,
                "event_offset": event.offset,
            }

    def erase_source(self, atom_version_id: str, *, signing_key: str, actor: str = "system", reason: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "erase_source"):
            return self.delegate.erase_source(atom_version_id, signing_key=signing_key, actor=actor, reason=reason)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT nv.atom_version_id, n.workspace_id, nv.properties FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s",
                    (str(atom_version_id),),
                )
                row = self._cursor_mapping(cursor, cursor.fetchone())
                if not row:
                    existing_op = self.get_erasure_operation_by_atom(atom_version_id)
                    if existing_op and existing_op.get("state") == "completed":
                        return {
                            "state": "redacted_purged",
                            "atom_version_id": atom_version_id,
                            "workspace_id": existing_op["workspace_id"],
                            "erasure_receipt": existing_op["erasure_receipt"],
                            "event_offset": existing_op.get("event_offset", 0),
                        }
                    raise NotFoundError(f"atom version {atom_version_id} was not found")
                workspace_id = str(row["workspace_id"])
                props = self._json_value(row.get("properties"), {})
                object_key = props.get("object_key")

        op = self.create_or_acquire_erasure_operation(workspace_id, atom_version_id, object_key=object_key)
        if op.get("state") == "completed":
            return {
                "state": "redacted_purged",
                "atom_version_id": atom_version_id,
                "workspace_id": workspace_id,
                "erasure_receipt": op["erasure_receipt"],
                "event_offset": op.get("event_offset", 0),
            }
        return self.finalize_erasure_operation(op["operation_id"], signing_key=signing_key, actor=actor, reason=reason)


    def queryable_atoms(
        self,
        workspace_id: str | None,
        as_of_event: int | None = None,
        *,
        valid_at: Any | None = None,
        valid_from: Any | None = None,
        valid_to: Any | None = None,
    ) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "queryable_atoms"):
            try:
                return self.delegate.queryable_atoms(
                    workspace_id, as_of_event, valid_at=valid_at, valid_from=valid_from, valid_to=valid_to,
                )
            except TypeError:
                return self.delegate.queryable_atoms(workspace_id, as_of_event)
        valid_time_requested = any(value is not None for value in (valid_at, valid_from, valid_to))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                atoms = self._pg_atoms_query(
                    cursor,
                    workspace_id=workspace_id,
                    as_of_event=as_of_event,
                    all_versions=valid_time_requested,
                )
        visible = [
            atom
            for atom in atoms
            if self.temporal_visibility(
                atom,
                as_of_event=as_of_event,
                valid_at=valid_at,
                valid_from=valid_from,
                valid_to=valid_to,
            )["visible"]
        ]
        if not valid_time_requested:
            return visible
        # Valid-time is orthogonal to system/event time. Select the newest
        # immutable version that is valid at the requested real-world time,
        # rather than selecting today's version and filtering it afterwards.
        selected: dict[str, dict[str, Any]] = {}
        for atom in visible:
            selected.setdefault(str(atom["node_id"]), atom)
        return sorted(selected.values(), key=lambda item: int(item.get("created_event_offset", 0)), reverse=True)

    def temporal_candidate_atoms(
        self,
        workspace_id: str | None,
        as_of_event: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return all immutable source versions eligible for valid-time policy checks."""

        if self.delegate is not None and hasattr(self.delegate, "temporal_candidate_atoms"):
            return self.delegate.temporal_candidate_atoms(workspace_id, as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                return self._pg_atoms_query(
                    cursor,
                    workspace_id=workspace_id,
                    as_of_event=as_of_event,
                    all_versions=True,
                )

    def iter_indexable_atom_versions(
        self,
        workspace_id: str | None,
        as_of_event: int | None = None,
        *,
        batch_size: int = 1_000,
    ) -> Iterator[dict[str, Any]]:
        """Stream immutable source versions retained by a revisioned index."""

        if self.delegate is not None and hasattr(self.delegate, "iter_indexable_atom_versions"):
            yield from self.delegate.iter_indexable_atom_versions(
                workspace_id, as_of_event, batch_size=batch_size
            )
            return
        clauses = ["n.facets @> '[\"atom\"]'::jsonb", "nv.content<>''"]
        values: list[Any] = []
        if workspace_id is not None:
            clauses.append("n.workspace_id=%s")
            values.append(workspace_id)
        if as_of_event is not None:
            clauses.append("nv.created_event_offset<=%s")
            values.append(as_of_event)
        with self.connection() as conn:
            # A named/server-side cursor defers executing SELECT expressions
            # until rows are fetched.  Binding set_config through that cursor
            # therefore leaves forced RLS unset when the streaming query is
            # declared.  Establish the transaction-local workspace eagerly on
            # a normal cursor before opening the bounded stream.
            with conn.cursor() as workspace_cursor:
                self._set_workspace(workspace_cursor, workspace_id)
            with conn.cursor(name="trace_indexable_atom_versions") as cursor:
                cursor.execute(
                    f"""SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                               n.workspace_id,n.facets,n.security
                        FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                        WHERE {' AND '.join(clauses)}
                        ORDER BY nv.created_event_offset,nv.atom_version_id""",
                    values,
                )
                while True:
                    rows = cursor.fetchmany(max(1, min(int(batch_size), 10_000)))
                    if not rows:
                        break
                    for row in rows:
                        yield self._pg_atom_row(self._cursor_mapping(cursor, row) or {})

    def iter_queryable_atoms(self, workspace_id: str | None, as_of_event: int | None = None, *, batch_size: int = 1_000) -> Iterator[dict[str, Any]]:
        """Stream current source atoms so rebuild workers do not materialize a tenant."""

        if self.delegate is not None and hasattr(self.delegate, "iter_queryable_atoms"):
            yield from self.delegate.iter_queryable_atoms(workspace_id, as_of_event, batch_size=batch_size)
            return
        clauses = ["n.facets @> '[\"atom\"]'::jsonb"]
        values: list[Any] = []
        if workspace_id is not None:
            clauses.append("n.workspace_id=%s")
            values.append(workspace_id)
        if as_of_event is not None:
            clauses.append("nv.created_event_offset<=%s")
            values.append(as_of_event)
        with self.connection() as conn:
            with conn.cursor() as workspace_cursor:
                self._set_workspace(workspace_cursor, workspace_id)
            with conn.cursor(name="trace_current_atoms") as cursor:
                cursor.execute(
                    f"""WITH ranked AS (
                        SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                               n.workspace_id,n.facets,n.security,
                               ROW_NUMBER() OVER (PARTITION BY nv.node_id ORDER BY nv.version DESC) AS rank
                        FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                        WHERE {' AND '.join(clauses)}
                    ) SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset,workspace_id,facets,security FROM ranked WHERE rank=1 ORDER BY created_event_offset DESC""",
                    values,
                )
                while True:
                    rows = cursor.fetchmany(max(1, min(int(batch_size), 10_000)))
                    if not rows:
                        break
                    for row in rows:
                        yield self._pg_atom_row(self._cursor_mapping(cursor, row) or {})

    def atom_versions(self, atom_version_ids: Sequence[str]) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "atom_versions"):
            return self.delegate.atom_versions(atom_version_ids)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                rows = self._pg_atoms_query(cursor, workspace_id=None, as_of_event=None, atom_ids=atom_version_ids)
        by_id = {str(row["atom_version_id"]): row for row in rows}
        return [by_id[str(item)] for item in atom_version_ids if str(item) in by_id]


    def _pg_node(self, cursor: Any, node_id: str) -> dict[str, Any]:
        cursor.execute("SELECT node_id,workspace_id,facets,security,created_event_offset FROM trace_nodes WHERE node_id=%s", (node_id,))
        node = self._cursor_mapping(cursor, cursor.fetchone())
        if not node:
            raise NotFoundError(f"node {node_id} was not found")
        node["node_id"] = str(node["node_id"])
        return node

    def _pg_node_version(self, cursor: Any, node_id: str, as_of_event: int | None = None) -> dict[str, Any]:
        condition = " AND created_event_offset<=%s" if as_of_event is not None else ""
        values: list[Any] = [node_id]
        if as_of_event is not None:
            values.append(as_of_event)
        cursor.execute(f"SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset FROM trace_node_versions WHERE node_id=%s{condition} ORDER BY version DESC LIMIT 1", values)
        version = self._cursor_mapping(cursor, cursor.fetchone())
        if not version:
            raise NotFoundError(f"node {node_id} has no version at requested time")
        version["atom_version_id"] = str(version["atom_version_id"])
        version["node_id"] = str(version["node_id"])
        return version

    def get_node(self, node_id: str, as_of_event: int | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_node"):
            return self.delegate.get_node(node_id, as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                node = self._pg_node(cursor, node_id)
                version = self._pg_node_version(cursor, node_id, as_of_event)
                result = self._pg_atom_row({**version, "workspace_id": node["workspace_id"], "facets": node["facets"], "security": node["security"]})
                cursor.execute("SELECT anchor_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset FROM trace_evidence_anchors WHERE target_kind='node_version' AND target_id=%s ORDER BY anchor_id", (version["atom_version_id"],))
                result["evidence_anchors"] = self._pg_anchor_rows([self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()])
                return result

    def node_history(self, node_id: str) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "node_history"):
            return self.delegate.node_history(node_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                node = self._pg_node(cursor, node_id)
                cursor.execute("SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset FROM trace_node_versions WHERE node_id=%s ORDER BY version", (node_id,))
                return [self._pg_atom_row({**(self._cursor_mapping(cursor, row) or {}), "workspace_id": node["workspace_id"], "facets": node["facets"], "security": node["security"]}) for row in cursor.fetchall()]

    def edit_node(self, *, node_id: str, content: str, properties: dict[str, Any], actor: str, idempotency_key: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "edit_node"):
            return self.delegate.edit_node(node_id=node_id, content=content, properties=properties, actor=actor, idempotency_key=idempotency_key)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                node = self._pg_node(cursor, node_id)
                current = self._pg_node_version(cursor, node_id)
            current_properties = self._json_value(current.get("properties"), {})
            merged = {**current_properties, **properties, "predecessor_atom_version_id": current["atom_version_id"]}
            merged["temporal"] = normalize_valid_time(merged.get("temporal"))
            version = int(current["version"]) + 1
            version_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"node-version:{node_id}:{idempotency_key}")) if idempotency_key else str(uuid.uuid4())
            event = self._append_event_in_connection(conn, stream_id=f"node:{node_id}", event_type="node.versioned", payload={"node_id": node_id, "workspace_id": node["workspace_id"], "atom_version_id": version_id, "version": version, "content": content, "properties": merged, "patch": properties, "predecessor": current["atom_version_id"]}, actor=actor, idempotency_key=idempotency_key)
            with conn.cursor() as cursor:
                if event.duplicate:
                    cursor.execute("SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset FROM trace_node_versions WHERE created_event_offset=%s", (event.offset,))
                    duplicate = self._cursor_mapping(cursor, cursor.fetchone())
                    if not duplicate:
                        raise InvariantViolation("duplicate edit event has no node projection")
                    return self._pg_atom_row({**duplicate, "workspace_id": node["workspace_id"], "facets": node["facets"], "security": node["security"]})
                cursor.execute("INSERT INTO trace_node_versions(atom_version_id,node_id,version,content,properties,content_hash,created_event_offset) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)", (version_id, node_id, version, content, json.dumps(merged), _digest(content), event.offset))
                cursor.execute(
                    "SELECT state,valid_from,valid_to,valid_precision,valid_confidence,valid_provenance,predecessor_atom_version_id,superseded_by_atom_version_id,erasure_receipt FROM trace_source_lifecycle WHERE atom_version_id=%s",
                    (current["atom_version_id"],),
                )
                predecessor_lifecycle = self._pg_lifecycle_row(self._cursor_mapping(cursor, cursor.fetchone()))
            if predecessor_lifecycle and predecessor_lifecycle["state"] in {"revoked", "tombstoned", "redacted_purged"}:
                raise InvariantViolation(
                    f"cannot edit source in non-readable lifecycle state {predecessor_lifecycle['state']!r}"
                )
            if predecessor_lifecycle is not None:
                lifecycle_event = self._append_event_in_connection(
                    conn,
                    stream_id=f"node:{current['atom_version_id']}",
                    event_type="source.lifecycle_changed",
                    payload={
                        "atom_version_id": current["atom_version_id"], "workspace_id": node["workspace_id"],
                        "previous_state": predecessor_lifecycle["state"], "state": "superseded",
                        "reason": "superseded_by_node_edit", "superseded_by_atom_version_id": version_id,
                    },
                    actor=actor,
                )
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE trace_source_lifecycle SET state='superseded',superseded_by_atom_version_id=%s,changed_event_offset=%s WHERE atom_version_id=%s",
                        (version_id, lifecycle_event.offset, current["atom_version_id"]),
                    )
            temporal = merged["temporal"]
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_source_lifecycle(
                       atom_version_id,workspace_id,state,valid_from,valid_to,valid_precision,valid_confidence,
                       valid_provenance,predecessor_atom_version_id,changed_event_offset,created_at
                    ) VALUES (%s,%s,'active',%s,%s,%s,%s,%s::jsonb,%s,%s,NOW())
                    ON CONFLICT (atom_version_id) DO NOTHING""",
                    (
                        version_id, node["workspace_id"], temporal.get("valid_from"), temporal.get("valid_to"),
                        temporal.get("precision", "unknown"), temporal.get("confidence", "unknown"),
                        json.dumps(temporal.get("provenance", {})), current["atom_version_id"], event.offset,
                    ),
                )
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM trace_hot_inbox WHERE node_id=%s", (node_id,))
                cursor.execute("INSERT INTO trace_hot_inbox(atom_version_id,node_id,workspace_id,content,visible_from_event,facets,security) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)", (version_id, node_id, node["workspace_id"], content, event.offset, json.dumps(self._json_value(node["facets"], [])), json.dumps(self._json_value(node["security"], {}))))
                cursor.execute("INSERT INTO trace_projection_revisions(projection_name,workspace_id,last_applied_event,revision,updated_at) VALUES ('hot_inbox',%s,%s,1,NOW()) ON CONFLICT(projection_name,workspace_id) DO UPDATE SET last_applied_event=EXCLUDED.last_applied_event,revision=trace_projection_revisions.revision+1,updated_at=NOW()", (node["workspace_id"], event.offset))
            return self._pg_atom_row({"atom_version_id": version_id, "node_id": node_id, "version": version, "content": content, "properties": merged, "content_hash": _digest(content), "created_event_offset": event.offset, "workspace_id": node["workspace_id"], "facets": node["facets"], "security": node["security"]})

    def split_node(self, *, node_id: str, parts: list[str], actor: str, idempotency_key: str | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "split_node"):
            return self.delegate.split_node(node_id=node_id, parts=parts, actor=actor, idempotency_key=idempotency_key)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                parent = self._pg_node(cursor, node_id)
                parent_version = self._pg_node_version(cursor, node_id)
            marker = self._append_event_in_connection(conn, stream_id=f"node:{node_id}", event_type="node.split_requested", payload={"node_id": node_id, "workspace_id": parent["workspace_id"], "parts_hash": _digest(parts)}, actor=actor, idempotency_key=idempotency_key)
            if marker.duplicate:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,n.workspace_id,n.facets,n.security FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE n.workspace_id=%s AND nv.properties->>'split_marker_event'=%s ORDER BY nv.version", (parent["workspace_id"], str(marker.offset)))
                    return [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]
            children: list[dict[str, Any]] = []
            parent_properties = self._json_value(parent_version.get("properties"), {})
            for ordinal, part in enumerate(parts):
                child_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
                security = self._json_value(parent.get("security"), {})
                node_event = self._append_event_in_connection(conn, stream_id=f"workspace:{parent['workspace_id']}", event_type="node.created", payload={"node_id": child_id, "workspace_id": parent["workspace_id"], "facets": ["atom"], "security": security}, actor=actor, causation_id=marker.event_id)
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO trace_nodes(node_id,workspace_id,facets,security,created_event_offset) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s)", (child_id, parent["workspace_id"], json.dumps(["atom"]), json.dumps(security), node_event.offset))
                properties = {
                    "split_from_node_id": node_id,
                    "split_from_atom_version_id": parent_version["atom_version_id"],
                    "split_marker_event": marker.offset,
                    "ordinal": ordinal,
                    "ingestion_id": parent_properties.get("ingestion_id"),
                    "source_ordinal": parent_properties.get("ordinal"),
                    "projection_section_key": f"section:split:{node_id}:{marker.offset}",
                    "temporal": normalize_valid_time(parent_properties.get("temporal")),
                }
                version_event = self._append_event_in_connection(conn, stream_id=f"node:{child_id}", event_type="node.versioned", payload={"node_id": child_id, "workspace_id": parent["workspace_id"], "atom_version_id": version_id, "version": 1, "content": part, "properties": properties, "split_from": parent_version["atom_version_id"]}, actor=actor, causation_id=node_event.event_id)
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO trace_node_versions(atom_version_id,node_id,version,content,properties,content_hash,created_event_offset) VALUES (%s,%s,1,%s,%s::jsonb,%s,%s)", (version_id, child_id, part, json.dumps(properties), _digest(part), version_event.offset))
                    temporal = properties["temporal"]
                    cursor.execute(
                        """INSERT INTO trace_source_lifecycle(
                           atom_version_id,workspace_id,state,valid_from,valid_to,valid_precision,valid_confidence,
                           valid_provenance,predecessor_atom_version_id,changed_event_offset,created_at
                        ) VALUES (%s,%s,'active',%s,%s,%s,%s,%s::jsonb,%s,%s,NOW())""",
                        (
                            version_id, parent["workspace_id"], temporal.get("valid_from"), temporal.get("valid_to"),
                            temporal.get("precision", "unknown"), temporal.get("confidence", "unknown"),
                            json.dumps(temporal.get("provenance", {})), parent_version["atom_version_id"], version_event.offset,
                        ),
                    )
                    cursor.execute("INSERT INTO trace_hot_inbox(atom_version_id,node_id,workspace_id,content,visible_from_event,facets,security) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)", (version_id, child_id, parent["workspace_id"], part, version_event.offset, json.dumps(["atom"]), json.dumps(security)))
                self._pg_insert_edge(conn, workspace_id=parent["workspace_id"], source_node_id=child_id, target_node_id=node_id, relation_type="CHILD_OF", evidence_atom_version_ids=[parent_version["atom_version_id"]], actor=actor, model_version="lineage-v1", confidence=1.0, weight=1.0, status="trusted", properties={"operation": "split", "marker_event": marker.offset}, causation_id=marker.event_id)
                children.append(self._pg_atom_row({"atom_version_id": version_id, "node_id": child_id, "version": 1, "content": part, "properties": properties, "content_hash": _digest(part), "created_event_offset": version_event.offset, "workspace_id": parent["workspace_id"], "facets": ["atom"], "security": security}))
            return children

    def create_alias(self, *, source_node_id: str, target_node_id: str, actor: str, evidence_atom_version_ids: list[str], idempotency_key: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_alias"):
            return self.delegate.create_alias(source_node_id=source_node_id, target_node_id=target_node_id, actor=actor, evidence_atom_version_ids=evidence_atom_version_ids, idempotency_key=idempotency_key)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                source = self._pg_node(cursor, source_node_id)
                target = self._pg_node(cursor, target_node_id)
                if source["workspace_id"] != target["workspace_id"]:
                    raise InvariantViolation("nodes and relations must stay within one workspace")
                if not evidence_atom_version_ids:
                    current = self._pg_node_version(cursor, source_node_id)
                    evidence_atom_version_ids = [current["atom_version_id"]]
            operation = self._append_event_in_connection(conn, stream_id=f"node:{source_node_id}", event_type="node.aliased", payload={"source_node_id": source_node_id, "target_node_id": target_node_id, "workspace_id": source["workspace_id"]}, actor=actor, idempotency_key=idempotency_key)
            if operation.duplicate:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT edge_version_id,edge_id,version,workspace_id,source_node_id,target_node_id,relation_type,weight,confidence,status,valid_from_event,valid_to_event,model_version,properties,created_event_offset FROM trace_edge_versions WHERE source_node_id=%s AND target_node_id=%s AND relation_type='alias_of' ORDER BY created_event_offset DESC LIMIT 1", (source_node_id, target_node_id))
                    edge = self._cursor_mapping(cursor, cursor.fetchone())
                if not edge:
                    raise InvariantViolation("duplicate alias event has no edge projection")
                edge["properties"] = self._json_value(edge.get("properties"), {})
                return edge
            return self._pg_insert_edge(conn, workspace_id=source["workspace_id"], source_node_id=source_node_id, target_node_id=target_node_id, relation_type="alias_of", evidence_atom_version_ids=evidence_atom_version_ids, actor=actor, model_version="manual", confidence=1.0, weight=1.0, status="trusted", properties={"operation_event": operation.offset}, causation_id=operation.event_id)

    def current_nodes(self, workspace_id: str, as_of_event: int | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "current_nodes"):
            return self.delegate.current_nodes(workspace_id, as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                clauses = ["n.workspace_id=%s"]
                values: list[Any] = [workspace_id]
                if as_of_event is not None:
                    clauses.append("nv.created_event_offset<=%s")
                    values.append(as_of_event)
                cursor.execute(
                    f"""WITH ranked AS (
                        SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                               n.workspace_id,n.facets,n.security,
                               ROW_NUMBER() OVER (PARTITION BY nv.node_id ORDER BY nv.version DESC) AS rank
                        FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                        WHERE {' AND '.join(clauses)}
                    ) SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset,workspace_id,facets,security FROM ranked WHERE rank=1 ORDER BY created_event_offset DESC""",
                    values,
                )
                nodes = [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]
                for node in nodes:
                    cursor.execute("SELECT anchor_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset FROM trace_evidence_anchors WHERE target_kind='node_version' AND target_id=%s ORDER BY anchor_id", (node["atom_version_id"],))
                    node["evidence_anchors"] = self._pg_anchor_rows([self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()])
                return nodes

    def current_nodes_by_facet(
        self,
        workspace_id: str,
        facet: str,
        *,
        as_of_event: int | None = None,
        limit: int = 256,
    ) -> list[dict[str, Any]]:
        """Bounded facet lookup used by online retrieval paths."""

        if self.delegate is not None and hasattr(self.delegate, "current_nodes_by_facet"):
            return self.delegate.current_nodes_by_facet(workspace_id, facet, as_of_event=as_of_event, limit=limit)
        limit = max(1, min(int(limit), 2_000))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                clauses = ["n.workspace_id=%s", "n.facets @> %s::jsonb"]
                values: list[Any] = [workspace_id, json.dumps([facet])]
                if as_of_event is not None:
                    clauses.append("nv.created_event_offset<=%s")
                    values.append(as_of_event)
                values.append(limit)
                cursor.execute(
                    f"""WITH ranked AS (
                        SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                               n.workspace_id,n.facets,n.security,
                               ROW_NUMBER() OVER (PARTITION BY nv.node_id ORDER BY nv.version DESC) AS rank
                        FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                        WHERE {' AND '.join(clauses)}
                    ) SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset,workspace_id,facets,security
                      FROM ranked WHERE rank=1 ORDER BY created_event_offset DESC LIMIT %s""",
                    values,
                )
                nodes = [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]
                for node in nodes:
                    cursor.execute("SELECT anchor_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset FROM trace_evidence_anchors WHERE target_kind='node_version' AND target_id=%s ORDER BY anchor_id", (node["atom_version_id"],))
                    node["evidence_anchors"] = self._pg_anchor_rows([self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()])
                return nodes

    def current_nodes_by_hierarchy_keys(
        self,
        workspace_id: str,
        hierarchy_keys: Sequence[str],
        *,
        limit: int = 512,
    ) -> list[dict[str, Any]]:
        """Lookup exact materialization keys using PostgreSQL JSONB indexes."""

        if self.delegate is not None and hasattr(self.delegate, "current_nodes_by_hierarchy_keys"):
            return self.delegate.current_nodes_by_hierarchy_keys(workspace_id, hierarchy_keys, limit=limit)
        keys = [str(key) for key in dict.fromkeys(hierarchy_keys) if key]
        if not keys:
            return []
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    """WITH ranked AS (
                        SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                               n.workspace_id,n.facets,n.security,
                               ROW_NUMBER() OVER (PARTITION BY nv.node_id ORDER BY nv.version DESC) AS rank
                        FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                        WHERE n.workspace_id=%s AND nv.properties->>'hierarchy_key' = ANY(%s)
                    ) SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset,workspace_id,facets,security
                      FROM ranked WHERE rank=1 ORDER BY created_event_offset DESC LIMIT %s""",
                    (workspace_id, keys, max(1, min(int(limit), 2_000))),
                )
                nodes = [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]
                for node in nodes:
                    cursor.execute("SELECT anchor_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset FROM trace_evidence_anchors WHERE target_kind='node_version' AND target_id=%s ORDER BY anchor_id", (node["atom_version_id"],))
                    node["evidence_anchors"] = self._pg_anchor_rows([self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()])
                return nodes

    def get_ingestion(self, ingestion_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_ingestion"):
            return self.delegate.get_ingestion(ingestion_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT ingestion_id,workspace_id,source,attachment_id,accepted_event_offset,atom_count,parsing_status,indexing_status,consolidation_status,created_at FROM trace_ingestions WHERE ingestion_id=%s", (ingestion_id,))
                result = self._cursor_mapping(cursor, cursor.fetchone())
        if not result:
            raise NotFoundError(f"ingestion {ingestion_id} was not found")
        result["source"] = self._json_value(result.get("source"), {})
        return result

    def get_attachment(self, attachment_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_attachment"):
            return self.delegate.get_attachment(attachment_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT attachment_id,workspace_id,content_hash,object_key,media_type,byte_length,created_event_offset,metadata FROM trace_attachments WHERE attachment_id=%s", (attachment_id,))
                result = self._cursor_mapping(cursor, cursor.fetchone())
        if not result:
            raise NotFoundError(f"attachment {attachment_id} was not found")
        result["metadata"] = self._json_value(result.get("metadata"), {})
        return result

    def ingestion_atoms(self, ingestion_id: str) -> list[dict[str, Any]]:
        ingestion = self.get_ingestion(ingestion_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (ingestion["workspace_id"],))
                cursor.execute(
                    """SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                              n.workspace_id,n.facets,n.security
                       FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                       WHERE n.workspace_id=%s AND nv.properties->>'ingestion_id'=%s ORDER BY (nv.properties->>'ordinal')::INTEGER""",
                    (ingestion["workspace_id"], ingestion_id),
                )
                return [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]

    def ingest(
        self,
        *,
        workspace_id: str,
        source: dict[str, Any],
        attachment: dict[str, Any],
        atoms: Sequence[dict[str, Any]],
        actor: str,
        visibility: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        """Capture raw source metadata and versioned atoms in one transaction."""

        if self.delegate is not None and hasattr(self.delegate, "ingest"):
            return self.delegate.ingest(workspace_id=workspace_id, source=source, attachment=attachment, atoms=atoms, actor=actor, visibility=visibility, idempotency_key=idempotency_key)
        stable_seed = f"{workspace_id}:{idempotency_key}" if idempotency_key else None
        ingestion_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ingestion:{stable_seed}")) if stable_seed else str(uuid.uuid4())
        attachment_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"attachment:{stable_seed}")) if stable_seed else str(uuid.uuid4())
        with self.connection() as conn:
            accepted = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="ingestion.accepted",
                payload={"ingestion_id": ingestion_id, "workspace_id": workspace_id, "source": source, "content_hash": attachment["content_hash"]},
                actor=actor, correlation_id=ingestion_id, idempotency_key=idempotency_key,
            )
            if accepted.duplicate:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT ingestion_id,workspace_id,source,attachment_id,accepted_event_offset,atom_count,parsing_status,indexing_status,consolidation_status,created_at FROM trace_ingestions WHERE accepted_event_offset=%s", (accepted.offset,))
                    existing = self._cursor_mapping(cursor, cursor.fetchone())
                if not existing:
                    raise InvariantViolation("duplicate ingestion event has no ingestion projection")
                existing["source"] = self._json_value(existing.get("source"), {})
                return existing
            now = datetime.now(UTC)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_ingestions(ingestion_id,workspace_id,source,attachment_id,accepted_event_offset,atom_count,parsing_status,indexing_status,consolidation_status,created_at) VALUES (%s,%s,%s::jsonb,%s,%s,%s,'running','pending','pending',%s)", (ingestion_id, workspace_id, json.dumps(source), attachment_id, accepted.offset, len(atoms), now))
            attachment_event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="attachment.recorded",
                payload={"attachment_id": attachment_id, "ingestion_id": ingestion_id, "workspace_id": workspace_id, "content_hash": attachment["content_hash"], "object_key": attachment["object_key"], "media_type": attachment["media_type"], "byte_length": attachment["byte_length"], "metadata": attachment.get("metadata", {})},
                actor=actor, causation_id=accepted.event_id, correlation_id=ingestion_id,
            )
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_attachments(attachment_id,workspace_id,content_hash,object_key,media_type,byte_length,metadata,created_event_offset) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)", (attachment_id, workspace_id, attachment["content_hash"], attachment["object_key"], attachment["media_type"], attachment["byte_length"], json.dumps(attachment.get("metadata", {})), attachment_event.offset))
            created: list[dict[str, Any]] = []
            for atom in atoms:
                ordinal = atom["ordinal"]
                node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"node:{stable_seed}:{ordinal}")) if stable_seed else str(uuid.uuid4())
                security = {"visibility": visibility, "origin": source.get("uri"), "actor": actor}
                node_event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="node.created", payload={"node_id": node_id, "workspace_id": workspace_id, "facets": ["atom"], "security": security}, actor=actor, causation_id=accepted.event_id, correlation_id=ingestion_id)
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO trace_nodes(node_id,workspace_id,facets,security,created_event_offset) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s)", (node_id, workspace_id, json.dumps(["atom"]), json.dumps(security), node_event.offset))
                version_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"atom-version:{stable_seed}:{ordinal}:1")) if stable_seed else str(uuid.uuid4())
                properties = {
                    "ingestion_id": ingestion_id, "attachment_id": attachment_id,
                    "source_start": atom["start"], "source_end": atom["end"],
                    "ordinal": atom["ordinal"], "parser_location": atom["parser_location"],
                    "source": source, "temporal": normalize_valid_time(atom.get("temporal")),
                }
                version_event = self._append_event_in_connection(conn, stream_id=f"node:{node_id}", event_type="node.versioned", payload={"node_id": node_id, "workspace_id": workspace_id, "atom_version_id": version_id, "version": 1, "content": atom["content"], "properties": properties}, actor=actor, causation_id=node_event.event_id, correlation_id=ingestion_id)
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO trace_node_versions(atom_version_id,node_id,version,content,properties,content_hash,created_event_offset) VALUES (%s,%s,1,%s,%s::jsonb,%s,%s)", (version_id, node_id, atom["content"], json.dumps(properties), _digest(atom["content"]), version_event.offset))
                    temporal = properties["temporal"]
                    cursor.execute(
                        """INSERT INTO trace_source_lifecycle(
                           atom_version_id,workspace_id,state,valid_from,valid_to,valid_precision,valid_confidence,
                           valid_provenance,changed_event_offset,created_at
                        ) VALUES (%s,%s,'active',%s,%s,%s,%s,%s::jsonb,%s,NOW())""",
                        (
                            version_id, workspace_id, temporal.get("valid_from"), temporal.get("valid_to"),
                            temporal.get("precision", "unknown"), temporal.get("confidence", "unknown"),
                            json.dumps(temporal.get("provenance", {})), version_event.offset,
                        ),
                    )
                    cursor.execute("INSERT INTO trace_hot_inbox(atom_version_id,node_id,workspace_id,content,visible_from_event,facets,security) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)", (version_id, node_id, workspace_id, atom["content"], version_event.offset, json.dumps(["atom"]), json.dumps(security)))
                created.append({"node_id": node_id, "atom_version_id": version_id, "event_offset": version_event.offset, **properties})
            for previous, following in zip(created, created[1:]):
                self._pg_insert_edge(conn, workspace_id=workspace_id, source_node_id=previous["node_id"], target_node_id=following["node_id"], relation_type="NEXT", evidence_atom_version_ids=[previous["atom_version_id"], following["atom_version_id"]], actor=actor, model_version="structural-v1", confidence=1.0, weight=1.0, status="trusted", properties={"ingestion_id": ingestion_id, "structural": True}, causation_id=accepted.event_id, correlation_id=ingestion_id)
            finished = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="ingestion.atomized", payload={"ingestion_id": ingestion_id, "atom_count": len(created)}, actor="system", causation_id=accepted.event_id, correlation_id=ingestion_id)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_ingestions SET parsing_status='completed',indexing_status='lexical_ready',consolidation_status='pending' WHERE ingestion_id=%s", (ingestion_id,))
            return {"ingestion_id": ingestion_id, "workspace_id": workspace_id, "atom_count": len(created), "accepted_event_offset": accepted.offset, "atomized_event_offset": finished.offset, "parsing_status": "completed", "indexing_status": "lexical_ready", "consolidation_status": "pending"}

    def _pg_insert_edge(
        self,
        conn: Any,
        *,
        workspace_id: str,
        source_node_id: str,
        target_node_id: str,
        relation_type: str,
        evidence_atom_version_ids: list[str],
        actor: str,
        model_version: str,
        confidence: float,
        weight: float,
        status: str,
        properties: dict[str, Any],
        causation_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        if relation_type not in ALLOWED_RELATIONS:
            raise InvariantViolation(f"unsupported relation_type {relation_type!r}")
        if relation_type not in STRUCTURAL_RELATIONS and not evidence_atom_version_ids:
            raise InvariantViolation("evidence relations require source anchors")
        edge_id, edge_version_id = str(uuid.uuid4()), str(uuid.uuid4())
        event = self._append_event_in_connection(
            conn, stream_id=f"workspace:{workspace_id}", event_type="edge.created",
            payload={"edge_id": edge_id, "edge_version_id": edge_version_id, "workspace_id": workspace_id, "source_node_id": source_node_id, "target_node_id": target_node_id, "relation_type": relation_type, "weight": weight, "confidence": confidence, "status": status, "model_version": model_version, "evidence_atom_version_ids": evidence_atom_version_ids, "properties": properties},
            actor=actor, causation_id=causation_id, correlation_id=correlation_id,
        )
        conflicting_atom_version_ids: list[str] = []
        with conn.cursor() as cursor:
            cursor.execute("SELECT workspace_id FROM trace_nodes WHERE node_id IN (%s,%s) ORDER BY node_id", (source_node_id, target_node_id))
            node_workspaces = [str(row[0]) for row in cursor.fetchall()]
            if len(node_workspaces) != 2 or any(item != workspace_id for item in node_workspaces):
                raise InvariantViolation("nodes and relations must stay within one workspace")
            if relation_type == "contradicts":
                cursor.execute(
                    """SELECT DISTINCT ON (nv.node_id) nv.atom_version_id
                       FROM trace_node_versions nv
                       JOIN trace_nodes n ON n.node_id=nv.node_id
                       WHERE n.workspace_id=%s AND n.node_id IN (%s,%s)
                       ORDER BY nv.node_id,nv.version DESC""",
                    (workspace_id, source_node_id, target_node_id),
                )
                conflicting_atom_version_ids = [str(row[0]) for row in cursor.fetchall()]
            cursor.execute("INSERT INTO trace_edge_versions(edge_version_id,edge_id,version,workspace_id,source_node_id,target_node_id,relation_type,weight,confidence,status,valid_from_event,model_version,properties,created_event_offset) VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)", (edge_version_id, edge_id, workspace_id, source_node_id, target_node_id, relation_type, weight, confidence, status, event.offset, model_version, json.dumps(properties), event.offset))
            for source_atom_version_id in evidence_atom_version_ids:
                cursor.execute("SELECT nv.properties,nv.content FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s AND n.workspace_id=%s", (source_atom_version_id, workspace_id))
                source = self._cursor_mapping(cursor, cursor.fetchone())
                if not source:
                    raise InvariantViolation(f"evidence atom version {source_atom_version_id} is absent or out of scope")
                source_properties = self._json_value(source.get("properties"), {})
                cursor.execute("INSERT INTO trace_evidence_anchors(anchor_id,workspace_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset) VALUES (%s,%s,'edge_version',%s,%s,%s,%s,%s,%s,%s)", (str(uuid.uuid4()), workspace_id, edge_version_id, source_atom_version_id, source_properties.get("source_start"), source_properties.get("source_end"), source_properties.get("parser_location"), _digest(source.get("content", "")), event.offset))
        if relation_type == "contradicts":
            for atom_version_id in conflicting_atom_version_ids:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT state FROM trace_source_lifecycle WHERE atom_version_id=%s FOR UPDATE", (atom_version_id,))
                    lifecycle_row = cursor.fetchone()
                lifecycle_state = str(lifecycle_row[0]) if lifecycle_row else None
                if lifecycle_state and lifecycle_state not in {"revoked", "tombstoned", "redacted_purged", "conflicted"}:
                    self._change_source_lifecycle_in_connection(
                        conn,
                        atom_version_id=atom_version_id,
                        state="conflicted",
                        actor=actor,
                        reason="contradiction_edge_created",
                    )
        return {"edge_id": edge_id, "edge_version_id": edge_version_id, "version": 1, "workspace_id": workspace_id, "source_node_id": source_node_id, "target_node_id": target_node_id, "relation_type": relation_type, "weight": weight, "confidence": confidence, "status": status, "model_version": model_version, "properties": properties, "evidence_atom_version_ids": list(evidence_atom_version_ids), "created_event_offset": event.offset}

    def create_edge(self, **kwargs: Any) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_edge"):
            return self.delegate.create_edge(**kwargs)
        with self.connection() as conn:
            return self._pg_insert_edge(conn, **kwargs)

    def current_edges(self, workspace_id: str, as_of_event: int | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "current_edges"):
            return self.delegate.current_edges(workspace_id, as_of_event)
        clause = " AND ev.created_event_offset<=%s" if as_of_event is not None else ""
        values: list[Any] = [workspace_id]
        if as_of_event is not None:
            values.append(as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(f"""WITH ranked AS (
                    SELECT ev.*,ROW_NUMBER() OVER (PARTITION BY ev.edge_id ORDER BY ev.version DESC) AS rank
                    FROM trace_edge_versions ev WHERE ev.workspace_id=%s{clause}
                ) SELECT edge_version_id,edge_id,version,workspace_id,source_node_id,target_node_id,relation_type,weight,confidence,status,valid_from_event,valid_to_event,model_version,properties,created_event_offset FROM ranked WHERE rank=1 AND status='trusted'""", values)
                edges = [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]
                for edge in edges:
                    edge["properties"] = self._json_value(edge.get("properties"), {})
                    cursor.execute("SELECT anchor_id,workspace_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset FROM trace_evidence_anchors WHERE target_kind='edge_version' AND target_id=%s ORDER BY anchor_id", (edge["edge_version_id"],))
                    edge["evidence_anchors"] = [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]
                return edges

    def neighbor_edges(
        self,
        workspace_id: str,
        node_ids: Sequence[str],
        *,
        as_of_event: int | None = None,
        limit: int = 512,
    ) -> list[dict[str, Any]]:
        """Fetch only one bounded current graph frontier under tenant RLS."""

        if self.delegate is not None and hasattr(self.delegate, "neighbor_edges"):
            return self.delegate.neighbor_edges(
                workspace_id, node_ids, as_of_event=as_of_event, limit=limit
            )
        selected = list(dict.fromkeys(str(node_id) for node_id in node_ids if node_id))[:512]
        if not selected:
            return []
        values: list[Any] = [workspace_id, selected, selected]
        event_clause = ""
        if as_of_event is not None:
            event_clause = " AND ev.created_event_offset<=%s"
            values.append(as_of_event)
        values.append(max(1, min(int(limit), 2_000)))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    f"""WITH ranked AS (
                        SELECT ev.*,ROW_NUMBER() OVER (PARTITION BY ev.edge_id ORDER BY ev.version DESC) AS rank
                        FROM trace_edge_versions ev
                        WHERE ev.workspace_id=%s
                          AND (ev.source_node_id = ANY(%s) OR ev.target_node_id = ANY(%s)){event_clause}
                    ) SELECT edge_version_id,edge_id,version,workspace_id,source_node_id,target_node_id,
                             relation_type,weight,confidence,status,valid_from_event,valid_to_event,
                             model_version,properties,created_event_offset
                      FROM ranked WHERE rank=1 AND status='trusted'
                      ORDER BY created_event_offset DESC,edge_version_id LIMIT %s""",
                    values,
                )
                edges = [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]
                for edge in edges:
                    edge["properties"] = self._json_value(edge.get("properties"), {})
                    cursor.execute(
                        "SELECT anchor_id,workspace_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset FROM trace_evidence_anchors WHERE target_kind='edge_version' AND target_id=%s ORDER BY anchor_id",
                        (edge["edge_version_id"],),
                    )
                    edge["evidence_anchors"] = [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]
                return edges

    def semantic_link_exists(self, workspace_id: str, source_node_id: str, target_node_id: str) -> bool:
        if self.delegate is not None and hasattr(self.delegate, "semantic_link_exists"):
            return self.delegate.semantic_link_exists(workspace_id, source_node_id, target_node_id)
        marks = ",".join("%s" for _ in ("supports", "contradicts", "depends_on", "implements", "example_of"))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(f"SELECT 1 FROM trace_edge_versions WHERE workspace_id=%s AND source_node_id=%s AND target_node_id=%s AND relation_type IN ({marks}) AND status IN ('trusted','proposed') LIMIT 1", [workspace_id, source_node_id, target_node_id, "supports", "contradicts", "depends_on", "implements", "example_of"])
                return cursor.fetchone() is not None

    def set_consolidation_status(self, ingestion_id: str, status: str, *, actor: str = "system") -> None:
        if status not in {"pending", "running", "completed", "failed"}:
            raise ValueError("invalid consolidation status")
        if self.delegate is not None and hasattr(self.delegate, "set_consolidation_status"):
            return self.delegate.set_consolidation_status(ingestion_id, status, actor=actor)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT workspace_id FROM trace_ingestions WHERE ingestion_id=%s FOR UPDATE", (ingestion_id,))
                row = cursor.fetchone()
            if not row:
                raise NotFoundError(f"ingestion {ingestion_id} was not found")
            workspace_id = str(row[0])
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type=f"consolidation.{status}", payload={"ingestion_id": ingestion_id, "status": status, "workspace_id": workspace_id}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_ingestions SET consolidation_status=%s WHERE ingestion_id=%s", (status, ingestion_id))
                cursor.execute("INSERT INTO trace_projection_revisions(projection_name,workspace_id,last_applied_event,revision,updated_at) VALUES ('consolidation',%s,%s,1,NOW()) ON CONFLICT(projection_name,workspace_id) DO UPDATE SET last_applied_event=EXCLUDED.last_applied_event,revision=trace_projection_revisions.revision+1,updated_at=NOW()", (workspace_id, event.offset))

    def reconcile_hot_inbox(self, workspace_id: str | None = None, *, actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "reconcile_hot_inbox"):
            return self.delegate.reconcile_hot_inbox(workspace_id, actor=actor)
        workspace_id = workspace_id or _runtime_workspace.get()
        if not workspace_id:
            raise InvariantViolation("PostgreSQL projection rebuilds require one explicit workspace")
        with self.connection() as conn:
            started = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="projection.reconcile_started", payload={"projection": "hot_inbox", "workspace_id": workspace_id}, actor=actor)
            workspaces = [workspace_id]
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("DELETE FROM trace_hot_inbox WHERE workspace_id=%s", (workspace_id,))
            inserted = 0
            for workspace in workspaces:
                with conn.cursor() as cursor:
                    atoms = self._pg_atoms_query(cursor, workspace_id=workspace, as_of_event=None)
                    for atom in atoms:
                        cursor.execute("INSERT INTO trace_hot_inbox(atom_version_id,node_id,workspace_id,content,visible_from_event,facets,security) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)", (atom["atom_version_id"], atom["node_id"], workspace, atom["content"], atom["created_event_offset"], json.dumps(atom["facets"]), json.dumps(atom["security"])))
                        inserted += 1
            completed = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="projection.reconciled", payload={"projection": "hot_inbox", "workspace_id": workspace_id, "inserted": inserted}, actor=actor, causation_id=started.event_id)
            with conn.cursor() as cursor:
                for workspace in workspaces:
                    cursor.execute("INSERT INTO trace_projection_revisions(projection_name,workspace_id,last_applied_event,revision,updated_at) VALUES ('hot_inbox',%s,%s,1,NOW()) ON CONFLICT(projection_name,workspace_id) DO UPDATE SET last_applied_event=EXCLUDED.last_applied_event,revision=trace_projection_revisions.revision+1,updated_at=NOW()", (workspace, completed.offset))
            return {"projection": "hot_inbox", "workspace_id": workspace_id, "inserted": inserted, "event_offset": completed.offset}

    def replay_report(self, workspace_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "replay_report"):
            return self.delegate.replay_report(workspace_id)
        # Projections are intentionally excluded: this verifies that the
        # append-only Spine still reconstructs canonical records, not that a
        # replaceable index happens to be current.
        with self.authorization_scope(workspace_id):
            events = self.events()
            folded_nodes: dict[str, dict[str, Any]] = {}
            folded_versions: dict[str, dict[str, Any]] = {}
            folded_edges: dict[str, dict[str, Any]] = {}
            folded_attachments: dict[str, dict[str, Any]] = {}
            errors: list[str] = []
            expected_sequence: dict[str, int] = {}
            for event in events:
                if event.payload_hash != _digest(event.payload):
                    errors.append(f"event {event.offset} payload hash differs from its payload")
                sequence = expected_sequence.get(event.stream_id, 0) + 1
                if event.stream_sequence != sequence:
                    errors.append(f"event {event.offset} breaks stream sequence for {event.stream_id}")
                expected_sequence[event.stream_id] = event.stream_sequence
                payload = event.payload
                if event.event_type == "node.created":
                    folded_nodes[str(payload["node_id"])] = {
                        "facets": payload.get("facets", []),
                        "security": payload.get("security", {}),
                    }
                elif event.event_type == "node.security_changed" and str(payload.get("node_id")) in folded_nodes:
                    security = payload.get("security")
                    if not isinstance(security, dict) or not security.get("visibility"):
                        errors.append(f"event {event.offset} cannot replay node security")
                        continue
                    folded_nodes[str(payload["node_id"])]["security"] = dict(security)
                elif event.event_type == "node.versioned" and str(payload.get("node_id")) in folded_nodes:
                    required = {"atom_version_id", "version", "content", "properties"}
                    if not required <= payload.keys():
                        errors.append(f"event {event.offset} cannot replay node version")
                        continue
                    folded_versions[str(payload["atom_version_id"])] = {
                        "node_id": str(payload["node_id"]),
                        "version": int(payload["version"]),
                        "content": payload["content"],
                        "properties": payload["properties"],
                    }
                elif event.event_type in {"edge.created", "edge.versioned"}:
                    required = {
                        "edge_version_id", "edge_id", "source_node_id", "target_node_id",
                        "relation_type", "evidence_atom_version_ids",
                    }
                    if not required <= payload.keys():
                        errors.append(f"event {event.offset} cannot replay edge version")
                        continue
                    folded_edges[str(payload["edge_version_id"])] = payload
                elif event.event_type == "attachment.recorded":
                    folded_attachments[str(payload["attachment_id"])] = payload

            with self.connection() as conn:
                with conn.cursor() as cursor:
                    self._set_workspace(cursor, workspace_id)
                    cursor.execute("SELECT node_id,facets,security FROM trace_nodes WHERE workspace_id=%s", (workspace_id,))
                    actual_nodes = {
                        str(node_id): {"facets": self._json_value(facets, []), "security": self._json_value(security, {})}
                        for node_id, facets, security in cursor.fetchall()
                    }
                    cursor.execute(
                        """SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties
                           FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                           WHERE n.workspace_id=%s""",
                        (workspace_id,),
                    )
                    actual_versions = {
                        str(atom_version_id): {
                            "node_id": str(node_id), "version": int(version), "content": content,
                            "properties": self._json_value(properties, {}),
                        }
                        for atom_version_id, node_id, version, content, properties in cursor.fetchall()
                    }
                    cursor.execute(
                        """SELECT edge_version_id,edge_id,version,source_node_id,target_node_id,relation_type,
                                  weight,confidence,status,model_version,properties
                           FROM trace_edge_versions WHERE workspace_id=%s""",
                        (workspace_id,),
                    )
                    actual_edges = {
                        str(edge_version_id): {
                            "edge_id": str(edge_id), "version": int(version),
                            "source_node_id": str(source_node_id), "target_node_id": str(target_node_id),
                            "relation_type": relation_type, "weight": float(weight), "confidence": float(confidence),
                            "status": status, "model_version": model_version,
                            "properties": self._json_value(properties, {}),
                        }
                        for edge_version_id, edge_id, version, source_node_id, target_node_id, relation_type,
                            weight, confidence, status, model_version, properties in cursor.fetchall()
                    }
                    cursor.execute(
                        """SELECT attachment_id,content_hash,object_key,media_type,byte_length,metadata
                           FROM trace_attachments WHERE workspace_id=%s""",
                        (workspace_id,),
                    )
                    actual_attachments = {
                        str(attachment_id): {
                            "content_hash": content_hash, "object_key": object_key, "media_type": media_type,
                            "byte_length": int(byte_length), "metadata": self._json_value(metadata, {}),
                        }
                        for attachment_id, content_hash, object_key, media_type, byte_length, metadata in cursor.fetchall()
                    }
                    cursor.execute(
                        """SELECT e.event_id FROM trace_events e
                           LEFT JOIN trace_outbox o ON o.event_offset=e.event_offset AND o.event_id=e.event_id
                           WHERE e.workspace_id=%s AND o.event_id IS NULL""",
                        (workspace_id,),
                    )
                    missing_outbox = [str(row[0]) for row in cursor.fetchall()]

                    for edge_version_id, payload in folded_edges.items():
                        actual = actual_edges.get(edge_version_id)
                        if not actual:
                            errors.append(f"edge {edge_version_id} exists in the event fold but not in canonical records")
                            continue
                        cursor.execute(
                            """SELECT source_atom_version_id FROM trace_evidence_anchors
                               WHERE workspace_id=%s AND target_kind='edge_version' AND target_id=%s
                               ORDER BY source_atom_version_id""",
                            (workspace_id, edge_version_id),
                        )
                        anchors = [str(row[0]) for row in cursor.fetchall()]
                        if sorted(str(item) for item in payload["evidence_atom_version_ids"]) != anchors:
                            errors.append(f"edge {edge_version_id} evidence anchors differ from its event")
                        for field in (
                            "edge_id", "version", "source_node_id", "target_node_id", "relation_type",
                            "status", "weight", "confidence", "model_version", "properties",
                        ):
                            expected = payload.get(field)
                            if field == "version" and expected is None:
                                # ``edge.created`` is the first immutable
                                # edge version and therefore implies version 1.
                                expected = 1
                            if field in {"edge_id", "source_node_id", "target_node_id"} and expected is not None:
                                expected = str(expected)
                            if field in {"weight", "confidence"} and expected is not None:
                                expected = float(expected)
                            if expected != actual.get(field):
                                errors.append(f"edge {edge_version_id} field {field} differs from its event")
                    for attachment_id, payload in folded_attachments.items():
                        actual = actual_attachments.get(attachment_id)
                        if not actual:
                            errors.append(f"attachment {attachment_id} exists in the event fold but not in canonical records")
                            continue
                        for field in ("content_hash", "object_key", "media_type", "byte_length", "metadata"):
                            expected = int(payload[field]) if field == "byte_length" else payload.get(field)
                            if expected != actual.get(field):
                                errors.append(f"attachment {attachment_id} field {field} differs from its event")
            if folded_nodes != actual_nodes:
                errors.append("folded node identities/facets/security differ from canonical records")
            if folded_versions != actual_versions:
                errors.append("folded node versions differ from canonical records")
            if set(folded_edges) != set(actual_edges):
                errors.append("folded edge versions differ from canonical records")
            if set(folded_attachments) != set(actual_attachments):
                errors.append("folded attachments differ from canonical records")
            if missing_outbox:
                errors.append(f"{len(missing_outbox)} Spine events have no durable outbox record")
            return {
                "workspace_id": workspace_id,
                "valid": not errors,
                "errors": errors,
                "event_count": len(events),
                "nodes": len(folded_nodes),
                "node_versions": len(folded_versions),
                "edge_versions": len(folded_edges),
                "attachments": len(folded_attachments),
                "through_event_offset": max((event.offset for event in events), default=0),
            }

    def save_bundle(self, *, workspace_id: str | None, query: dict[str, Any], results: list[dict[str, Any]], sufficiency_state: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "save_bundle"):
            return self.delegate.save_bundle(workspace_id=workspace_id, query=query, results=results, sufficiency_state=sufficiency_state)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id or 'all'}", event_type="evidence_bundle.created", payload={"evidence_bundle_id": identifier, "workspace_id": workspace_id, "result_count": len(results), "sufficiency_state": sufficiency_state}, actor="system")
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_evidence_bundles(evidence_bundle_id,workspace_id,query,results,sufficiency_state,created_event_offset,created_at) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s,%s,NOW())", (identifier, workspace_id, json.dumps(query), json.dumps(results), sufficiency_state, event.offset))
                return self._pg_bundle_from_cursor(cursor, identifier)

    def _pg_bundle_from_cursor(self, cursor: Any, bundle_id: str) -> dict[str, Any]:
        cursor.execute("SELECT evidence_bundle_id,workspace_id,query,results,sufficiency_state,created_event_offset,created_at FROM trace_evidence_bundles WHERE evidence_bundle_id=%s", (bundle_id,))
        result = self._cursor_mapping(cursor, cursor.fetchone())
        if not result:
            raise NotFoundError(f"evidence bundle {bundle_id} was not found")
        result["query"] = self._json_value(result.get("query"), {})
        result["results"] = self._json_value(result.get("results"), [])
        return result

    def get_bundle(self, evidence_bundle_id: str, **_: Any) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_bundle"):
            return self.delegate.get_bundle(evidence_bundle_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                return self._pg_bundle_from_cursor(cursor, evidence_bundle_id)

    def record_feedback(
        self,
        *,
        workspace_id: str,
        atom_version_id: str,
        event_type: str,
        weight: float,
        actor: str,
        evidence_bundle_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "record_feedback"):
            return self.delegate.record_feedback(workspace_id=workspace_id, atom_version_id=atom_version_id, event_type=event_type, weight=weight, actor=actor, evidence_bundle_id=evidence_bundle_id, metadata=metadata, idempotency_key=idempotency_key)
        if event_type not in {"selected", "opened", "cited", "accepted", "rejected"}:
            raise InvariantViolation(f"unsupported feedback event_type {event_type!r}")
        metadata = metadata or {}
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute("SELECT 1 FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s AND n.workspace_id=%s", (atom_version_id, workspace_id))
                if cursor.fetchone() is None:
                    raise InvariantViolation(f"evidence atom version {atom_version_id} is absent or out of scope")
                if evidence_bundle_id:
                    bundle = self._pg_bundle_from_cursor(cursor, evidence_bundle_id)
                    if bundle["workspace_id"] != workspace_id or atom_version_id not in {item.get("atom_version_id") for item in bundle["results"]}:
                        raise InvariantViolation("feedback atom is absent from the named evidence bundle")
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="retrieval.feedback_recorded", payload={"feedback_id": identifier, "workspace_id": workspace_id, "evidence_bundle_id": evidence_bundle_id, "atom_version_id": atom_version_id, "event_type": event_type, "weight": weight, "metadata": metadata}, actor=actor, idempotency_key=idempotency_key)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_feedback(feedback_id,workspace_id,evidence_bundle_id,atom_version_id,event_type,weight,actor,metadata,created_event_offset,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,NOW())", (identifier, workspace_id, evidence_bundle_id, atom_version_id, event_type, weight, actor, json.dumps(metadata), event.offset))
                return {"feedback_id": identifier, "workspace_id": workspace_id, "evidence_bundle_id": evidence_bundle_id, "atom_version_id": atom_version_id, "event_type": event_type, "weight": weight, "actor": actor, "metadata": metadata, "created_event_offset": event.offset}

    def feedback_scores(self, workspace_id: str, atom_version_ids: Sequence[str]) -> dict[str, float]:
        if self.delegate is not None and hasattr(self.delegate, "feedback_scores"):
            return self.delegate.feedback_scores(workspace_id, atom_version_ids)
        if not atom_version_ids:
            return {}
        marks = ",".join("%s" for _ in atom_version_ids)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(f"SELECT atom_version_id,event_type,SUM(weight) AS total FROM trace_feedback WHERE workspace_id=%s AND atom_version_id IN ({marks}) GROUP BY atom_version_id,event_type", [workspace_id, *atom_version_ids])
                rows = cursor.fetchall()
        weights = {"selected": 0.05, "opened": 0.10, "cited": 0.20, "accepted": 0.15, "rejected": -0.20}
        result: dict[str, float] = {}
        for atom_id, kind, total in rows:
            result[str(atom_id)] = max(-1.0, min(1.0, result.get(str(atom_id), 0.0) + weights[str(kind)] * float(total)))
        return result

    def dense_vectors(self, provider_id: str, atom_version_ids: Sequence[str], *, index_revision: str = "embedded-current") -> dict[str, list[float]]:
        if self.delegate is not None and hasattr(self.delegate, "dense_vectors"):
            return self.delegate.dense_vectors(provider_id, atom_version_ids, index_revision=index_revision)
        if not atom_version_ids:
            return {}
        marks = ",".join("%s" for _ in atom_version_ids)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute(f"SELECT atom_version_id,vector FROM trace_dense_vectors WHERE provider_id=%s AND index_revision=%s AND atom_version_id IN ({marks})", [provider_id, index_revision, *atom_version_ids])
                rows = cursor.fetchall()
        return {str(atom_id): [float(item) for item in self._json_value(vector, [])] for atom_id, vector in rows}

    def upsert_dense_vectors(self, *, workspace_id: str, provider_id: str, vectors: dict[str, list[float]], actor: str = "system", index_revision: str = "embedded-current") -> int:
        if self.delegate is not None and hasattr(self.delegate, "upsert_dense_vectors"):
            return self.delegate.upsert_dense_vectors(workspace_id=workspace_id, provider_id=provider_id, vectors=vectors, actor=actor, index_revision=index_revision)
        if not vectors:
            return 0
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="dense_index.updated", payload={"workspace_id": workspace_id, "provider_id": provider_id, "index_revision": index_revision, "atom_version_ids": sorted(vectors), "count": len(vectors)}, actor=actor)
            with conn.cursor() as cursor:
                for atom_id, vector in vectors.items():
                    cursor.execute("SELECT 1 FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s AND n.workspace_id=%s", (atom_id, workspace_id))
                    if cursor.fetchone() is None:
                        raise InvariantViolation(f"evidence atom version {atom_id} is absent or out of scope")
                    cursor.execute("INSERT INTO trace_dense_vectors(atom_version_id,provider_id,index_revision,vector,created_event_offset) VALUES (%s,%s,%s,%s::jsonb,%s) ON CONFLICT(atom_version_id,provider_id,index_revision) DO UPDATE SET vector=EXCLUDED.vector,created_event_offset=EXCLUDED.created_event_offset", (atom_id, provider_id, index_revision, json.dumps(vector), event.offset))
            return len(vectors)

    @classmethod
    def _pg_proposal_row(cls, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("proposal was not found")
        result = dict(row)
        result["candidate"] = cls._json_value(result.pop("candidate"), {})
        result["evidence_atom_version_ids"] = cls._json_value(result.pop("evidence_atom_version_ids"), [])
        return result

    def create_proposal(
        self,
        *,
        workspace_id: str,
        proposal_type: str,
        candidate: dict[str, Any],
        evidence_atom_version_ids: list[str],
        confidence: float,
        model_version: str,
        actor: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_proposal"):
            return self.delegate.create_proposal(workspace_id=workspace_id, proposal_type=proposal_type, candidate=candidate, evidence_atom_version_ids=evidence_atom_version_ids, confidence=confidence, model_version=model_version, actor=actor, idempotency_key=idempotency_key)
        if proposal_type == "edge" and candidate.get("relation_type") not in ALLOWED_RELATIONS:
            raise InvariantViolation("edge proposals require an allowed relation_type")
        identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, f"proposal:{workspace_id}:{idempotency_key}")) if idempotency_key else str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                for atom_id in evidence_atom_version_ids:
                    cursor.execute("SELECT 1 FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s AND n.workspace_id=%s", (atom_id, workspace_id))
                    if cursor.fetchone() is None:
                        raise InvariantViolation(f"evidence atom version {atom_id} is absent or out of scope")
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="proposal.created", payload={"proposal_id": identifier, "workspace_id": workspace_id, "proposal_type": proposal_type, "candidate": candidate, "evidence_atom_version_ids": evidence_atom_version_ids, "confidence": confidence, "model_version": model_version}, actor=actor, idempotency_key=idempotency_key)
            with conn.cursor() as cursor:
                if event.duplicate:
                    cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE created_event_offset=%s", (event.offset,))
                    return self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))
                cursor.execute("INSERT INTO trace_proposals(proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,'pending',%s)", (identifier, workspace_id, proposal_type, json.dumps(candidate), json.dumps(evidence_atom_version_ids), confidence, model_version, event.offset))
                cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE proposal_id=%s", (identifier,))
                return self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def list_proposals(self, workspace_id: str, *, proposal_type: str | None = None, status: str | None = None, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "list_proposals"):
            return self.delegate.list_proposals(workspace_id, proposal_type=proposal_type, status=status, limit=limit, offset=offset)
        clauses = ["workspace_id=%s"]
        values: list[Any] = [workspace_id]
        if proposal_type:
            clauses.append("proposal_type=%s")
            values.append(proposal_type)
        if status:
            clauses.append("status=%s")
            values.append(status)
        suffix = ""
        if limit is not None:
            suffix = " LIMIT %s OFFSET %s"
            values.extend([max(1, min(int(limit), 200)), max(0, int(offset))])
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(f"SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE {' AND '.join(clauses)} ORDER BY created_event_offset DESC{suffix}", values)
                return [self._pg_proposal_row(self._cursor_mapping(cursor, row)) for row in cursor.fetchall()]

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_proposal"):
            return self.delegate.get_proposal(proposal_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE proposal_id=%s", (proposal_id,))
                return self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def decide_proposal(self, *, proposal_id: str, decision: str, actor: str, reason: str | None, idempotency_key: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "decide_proposal"):
            return self.delegate.decide_proposal(proposal_id=proposal_id, decision=decision, actor=actor, reason=reason, idempotency_key=idempotency_key)
        if decision not in {"promoted", "rejected"}:
            raise ValueError("decision must be promoted or rejected")
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE proposal_id=%s FOR UPDATE", (proposal_id,))
                row = self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))
            if row["status"] != "pending":
                if row["status"] == decision:
                    return row
                raise InvariantViolation(f"proposal is already {row['status']}")
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{row['workspace_id']}", event_type=f"proposal.{decision}", payload={"proposal_id": proposal_id, "workspace_id": row["workspace_id"], "reason": reason}, actor=actor, idempotency_key=idempotency_key)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_proposals SET status=%s,decided_event_offset=%s,decision_reason=%s WHERE proposal_id=%s", (decision, event.offset, reason, proposal_id))
                cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE proposal_id=%s", (proposal_id,))
                return self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def _pg_insert_derived_node(self, conn: Any, *, workspace_id: str, facets: list[str], content: str, properties: dict[str, Any], evidence_atom_version_ids: list[str], actor: str) -> dict[str, Any]:
        if not evidence_atom_version_ids:
            raise InvariantViolation("derived nodes require evidence anchors")
        node_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
        anchor_ids = [str(uuid.uuid4()) for _ in evidence_atom_version_ids]
        visibility = str(properties.get("visibility", "private"))
        stored = {**properties, "evidence_anchor_ids": anchor_ids, "evidence_atom_version_ids": list(evidence_atom_version_ids)}
        node_event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="node.created", payload={"node_id": node_id, "workspace_id": workspace_id, "facets": facets, "security": {"visibility": visibility, "actor": actor, "derived": True}}, actor=actor)
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO trace_nodes(node_id,workspace_id,facets,security,created_event_offset) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s)", (node_id, workspace_id, json.dumps(facets), json.dumps({"visibility": visibility, "actor": actor, "derived": True}), node_event.offset))
        version_event = self._append_event_in_connection(conn, stream_id=f"node:{node_id}", event_type="node.versioned", payload={"node_id": node_id, "workspace_id": workspace_id, "atom_version_id": version_id, "version": 1, "derived": True, "content": content, "properties": stored, "evidence_atom_version_ids": evidence_atom_version_ids}, actor=actor, causation_id=node_event.event_id)
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO trace_node_versions(atom_version_id,node_id,version,content,properties,content_hash,created_event_offset) VALUES (%s,%s,1,%s,%s::jsonb,%s,%s)", (version_id, node_id, content, json.dumps(stored), _digest(content), version_event.offset))
            temporal = normalize_valid_time(stored.get("temporal"))
            cursor.execute(
                """INSERT INTO trace_source_lifecycle(
                   atom_version_id,workspace_id,state,valid_from,valid_to,valid_precision,valid_confidence,
                   valid_provenance,changed_event_offset,created_at
                ) VALUES (%s,%s,'active',%s,%s,%s,%s,%s::jsonb,%s,NOW())""",
                (
                    version_id, workspace_id, temporal.get("valid_from"), temporal.get("valid_to"),
                    temporal.get("precision", "unknown"), temporal.get("confidence", "unknown"),
                    json.dumps(temporal.get("provenance", {})), version_event.offset,
                ),
            )
            for anchor_id, source_id in zip(anchor_ids, evidence_atom_version_ids, strict=True):
                cursor.execute("SELECT nv.properties,nv.content FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s AND n.workspace_id=%s", (source_id, workspace_id))
                source = self._cursor_mapping(cursor, cursor.fetchone())
                if not source:
                    raise InvariantViolation(f"evidence atom version {source_id} is absent or out of scope")
                source_properties = self._json_value(source.get("properties"), {})
                cursor.execute("INSERT INTO trace_evidence_anchors(anchor_id,workspace_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset) VALUES (%s,%s,'node_version',%s,%s,%s,%s,%s,%s,%s)", (anchor_id, workspace_id, version_id, source_id, source_properties.get("source_start"), source_properties.get("source_end"), source_properties.get("parser_location"), _digest(source.get("content", "")), version_event.offset))
        return {"node_id": node_id, "atom_version_id": version_id, "event_offset": version_event.offset, "facets": facets, "evidence_anchor_ids": anchor_ids, "evidence_atom_version_ids": list(evidence_atom_version_ids)}

    def create_derived_node(self, *, workspace_id: str, facets: list[str], content: str, properties: dict[str, Any], evidence_atom_version_ids: list[str], actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_derived_node"):
            return self.delegate.create_derived_node(workspace_id=workspace_id, facets=facets, content=content, properties=properties, evidence_atom_version_ids=evidence_atom_version_ids, actor=actor)
        with self.connection() as conn:
            return self._pg_insert_derived_node(conn, workspace_id=workspace_id, facets=facets, content=content, properties=properties, evidence_atom_version_ids=evidence_atom_version_ids, actor=actor)

    def promote_proposal(self, *, proposal_id: str, actor: str, reason: str | None, idempotency_key: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "promote_proposal"):
            return self.delegate.promote_proposal(proposal_id=proposal_id, actor=actor, reason=reason, idempotency_key=idempotency_key)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE proposal_id=%s FOR UPDATE", (proposal_id,))
                proposal = self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))
            if proposal["status"] != "pending":
                if proposal["status"] == "promoted":
                    return proposal
                raise InvariantViolation(f"proposal is already {proposal['status']}")
            candidate = proposal["candidate"]
            if proposal["proposal_type"] == "edge":
                materialized = self._pg_insert_edge(conn, workspace_id=proposal["workspace_id"], source_node_id=str(candidate["source_node_id"]), target_node_id=str(candidate["target_node_id"]), relation_type=str(candidate["relation_type"]), evidence_atom_version_ids=proposal["evidence_atom_version_ids"], actor=actor, model_version=proposal["model_version"], confidence=float(proposal["confidence"]), weight=float(candidate.get("weight", 1.0)), status="trusted", properties={**candidate.get("properties", {}), "proposal_id": proposal_id})
            else:
                content = str(candidate.get("content") or candidate.get("summary") or candidate.get("name") or _json(candidate))
                materialized = self._pg_insert_derived_node(conn, workspace_id=proposal["workspace_id"], facets=["claim" if proposal["proposal_type"] == "contradiction_resolution" else proposal["proposal_type"]], content=content, properties={**candidate, "proposal_id": proposal_id, "model_version": proposal["model_version"]}, evidence_atom_version_ids=proposal["evidence_atom_version_ids"], actor=actor)
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{proposal['workspace_id']}", event_type="proposal.promoted", payload={"proposal_id": proposal_id, "workspace_id": proposal["workspace_id"], "reason": reason, "materialized": materialized}, actor=actor, idempotency_key=idempotency_key)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_proposals SET status='promoted',decided_event_offset=%s,decision_reason=%s WHERE proposal_id=%s", (event.offset, reason, proposal_id))
            proposal["status"] = "promoted"
            proposal["decided_event_offset"] = event.offset
            proposal["decision_reason"] = reason
            proposal["materialized"] = materialized
            return proposal

    def save_benchmark_run(self, *, workspace_id: str, benchmark_name: str, stages: list[str], result: dict[str, Any], actor: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "save_benchmark_run"):
            return self.delegate.save_benchmark_run(workspace_id=workspace_id, benchmark_name=benchmark_name, stages=stages, result=result, actor=actor)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="benchmark.run_completed", payload={"benchmark_run_id": identifier, "workspace_id": workspace_id, "benchmark_name": benchmark_name, "stages": stages, "result": result}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_benchmark_runs(benchmark_run_id,workspace_id,benchmark_name,stages,result,created_event_offset,created_at) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,NOW())", (identifier, workspace_id, benchmark_name, json.dumps(stages), json.dumps(result), event.offset))
        return {"benchmark_run_id": identifier, "workspace_id": workspace_id, "benchmark_name": benchmark_name, "stages": stages, "result": result, "created_event_offset": event.offset}

    def save_query(self, *, workspace_id: str, name: str, query: dict[str, Any], frozen_atom_version_ids: list[str] | None, actor: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "save_query"):
            return self.delegate.save_query(workspace_id=workspace_id, name=name, query=query, frozen_atom_version_ids=frozen_atom_version_ids, actor=actor)
        table = "trace_frozen_queries" if frozen_atom_version_ids is not None else "trace_saved_queries"
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="saved_query.created", payload={"id": identifier, "workspace_id": workspace_id, "name": name, "frozen": frozen_atom_version_ids is not None}, actor=actor)
            with conn.cursor() as cursor:
                try:
                    if frozen_atom_version_ids is None:
                        cursor.execute("INSERT INTO trace_saved_queries(saved_query_id,workspace_id,name,query,created_event_offset) VALUES (%s,%s,%s,%s::jsonb,%s)", (identifier, workspace_id, name, json.dumps(query), event.offset))
                    else:
                        cursor.execute("INSERT INTO trace_frozen_queries(frozen_query_id,workspace_id,name,query,atom_version_ids,created_event_offset) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s)", (identifier, workspace_id, name, json.dumps(query), json.dumps(frozen_atom_version_ids), event.offset))
                except Exception as error:
                    if "duplicate" in str(error).lower() or "unique" in str(error).lower():
                        raise InvariantViolation(f"a saved query named {name!r} already exists in this workspace") from error
                    raise
        return {"frozen_query_id" if frozen_atom_version_ids is not None else "saved_query_id": identifier, "workspace_id": workspace_id, "name": name, "query": query, "created_event_offset": event.offset, "atom_version_ids": frozen_atom_version_ids}

    def register_index(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "register_index"):
            return self.delegate.register_index(payload, actor)
        identifier = str(uuid.uuid4())
        workspace_id = str(payload.get("workspace_id") or _runtime_workspace.get() or "")
        if not workspace_id:
            raise InvariantViolation("PostgreSQL index revisions require one explicit workspace")
        with self.connection() as conn:
            scoped_payload = {"index_revision_id": identifier, **payload, "workspace_id": workspace_id}
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="index_revision.created", payload=scoped_payload, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_index_revisions(index_revision_id,workspace_id,embedding_model,vector_namespace,lexical_revision,normalization,rollout_state,created_event_offset) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)", (identifier, workspace_id, payload["embedding_model"], payload["vector_namespace"], payload["lexical_revision"], json.dumps(payload.get("normalization", {})), payload["rollout_state"], event.offset))
        return {"index_revision_id": identifier, "created_event_offset": event.offset, **payload, "workspace_id": workspace_id}

    def register_model(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "register_model"):
            return self.delegate.register_model(payload, actor)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id="admin:models", event_type="model.registered", payload={"model_registry_id": identifier, **payload}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_model_registry(model_registry_id,name,provider,purpose,version,configuration,created_event_offset) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)", (identifier, payload["name"], payload["provider"], payload["purpose"], payload["version"], json.dumps(payload.get("configuration", {})), event.offset))
        return {"model_registry_id": identifier, "created_event_offset": event.offset, **payload}

    def register_manifest(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "register_manifest"):
            return self.delegate.register_manifest(payload, actor)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id="admin:experiments", event_type="experiment_manifest.created", payload={"manifest_id": identifier, **payload}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_experiment_manifests(manifest_id,name,corpus_snapshot,code_revision,model_versions,index_revisions,parameters,created_event_offset) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)", (identifier, payload["name"], payload["corpus_snapshot"], payload["code_revision"], json.dumps(payload.get("model_versions", {})), json.dumps(payload.get("index_revisions", [])), json.dumps(payload.get("parameters", {})), event.offset))
        return {"manifest_id": identifier, "created_event_offset": event.offset, **payload}

    def snapshot(self, *, actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "snapshot"):
            return self.delegate.snapshot(actor=actor)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT COALESCE(MAX(event_offset),0) FROM trace_events")
                through = int(cursor.fetchone()[0])
                cursor.execute("SELECT event_offset,payload_hash FROM trace_events WHERE event_offset<=%s ORDER BY event_offset", (through,))
                state_hash = _digest([{"event_offset": row[0], "payload_hash": row[1]} for row in cursor.fetchall()])
            event = self._append_event_in_connection(conn, stream_id="admin:snapshots", event_type="snapshot.created", payload={"snapshot_id": identifier, "through_event_offset": through, "state_hash": state_hash}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_snapshots(snapshot_id,through_event_offset,state_hash,created_event_offset,created_at) VALUES (%s,%s,%s,%s,NOW())", (identifier, through, state_hash, event.offset))
        return {"snapshot_id": identifier, "through_event_offset": through, "state_hash": state_hash, "created_event_offset": event.offset}

    def compact(self, *, actor: str = "system") -> dict[str, Any]:
        event = self.append_event(stream_id="admin:compaction", event_type="compaction.completed", payload={"deleted_spine_events": 0, "deleted_node_versions": 0, "note": "canonical history is retained; only rebuildable projections may be compacted"}, actor=actor)
        return {"deleted_spine_events": 0, "deleted_node_versions": 0, "event_offset": event.offset}

    def claim_outbox(
        self,
        *,
        limit: int = 100,
        lease_seconds: int = 30,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        workspace_id = workspace_id or _runtime_workspace.get()
        if not workspace_id:
            raise InvariantViolation("outbox publisher requires one explicit workspace scope")
        now = datetime.now(UTC)
        lease = datetime.fromtimestamp(now.timestamp() + max(1, lease_seconds), UTC)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    """UPDATE trace_outbox SET status='pending',lease_until=NULL
                       WHERE workspace_id=%s AND status='inflight' AND lease_until<%s""", (workspace_id, now)
                )
                cursor.execute(
                    """SELECT o.event_offset,o.event_id,o.topic,o.payload,o.attempts
                       FROM trace_outbox o WHERE o.workspace_id=%s AND o.status='pending' AND o.available_at<=%s
                       ORDER BY o.event_offset FOR UPDATE SKIP LOCKED LIMIT %s""", (workspace_id, now, limit),
                )
                rows = cursor.fetchall()
                result: list[dict[str, Any]] = []
                for offset, event_id, topic, payload, attempts in rows:
                    cursor.execute(
                        "UPDATE trace_outbox SET status='inflight',attempts=attempts+1,lease_until=%s WHERE event_offset=%s AND event_id=%s",
                        (lease, offset, event_id),
                    )
                    if not isinstance(payload, dict):
                        payload = json.loads(payload)
                    result.append({"event_offset": int(offset), "event_id": str(event_id), "workspace_id": workspace_id, "topic": topic, "payload": payload, "attempts": int(attempts) + 1})
                return result

    def mark_outbox_published(self, event_offset: int) -> None:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute(
                    "UPDATE trace_outbox SET status='published',published_at=NOW(),lease_until=NULL WHERE event_offset=%s AND status='inflight'",
                    (event_offset,),
                )
                if cursor.rowcount != 1:
                    raise InvariantViolation(f"outbox event {event_offset} is not leased")

    def release_outbox(self, event_offset: int) -> None:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute(
                    "UPDATE trace_outbox SET status='pending',lease_until=NULL WHERE event_offset=%s AND status='inflight'",
                    (event_offset,),
                )
                if cursor.rowcount != 1:
                    raise InvariantViolation(f"outbox event {event_offset} is not leased")

    def record_projection_event(
        self,
        *,
        projection_name: str,
        event_id: str,
        event_offset: int,
        workspace_id: str,
        projection_revision: int,
    ) -> bool:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    """INSERT INTO trace_projection_events(projection_name,event_id,event_offset,workspace_id,projection_revision,applied_at)
                       VALUES (%s,%s,%s,%s,%s,NOW()) ON CONFLICT(projection_name,event_id) DO NOTHING""",
                    (projection_name, event_id, event_offset, workspace_id, projection_revision),
                )
                inserted = cursor.rowcount == 1
                if inserted:
                    cursor.execute(
                        """INSERT INTO trace_projection_revisions(projection_name,workspace_id,last_applied_event,revision,updated_at)
                           VALUES (%s,%s,%s,%s,NOW())
                           ON CONFLICT(projection_name,workspace_id) DO UPDATE SET last_applied_event=GREATEST(trace_projection_revisions.last_applied_event,EXCLUDED.last_applied_event),revision=EXCLUDED.revision,updated_at=NOW()""",
                        (projection_name, workspace_id, event_offset, projection_revision),
                    )
                return inserted

    def projection_checkpoint(self, projection_name: str, workspace_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT * FROM trace_projection_revisions WHERE projection_name=%s AND workspace_id=%s", (projection_name, workspace_id))
                row = cursor.fetchone()
                if not row:
                    return None
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row, strict=True))

    _JOB_COLUMNS = "job_id,workspace_id,kind,status,payload,result,error,idempotency_key,attempts,max_attempts,available_at,lease_until,request_id,webhook_id,created_event_offset,created_at,updated_at,started_at,finished_at,cancel_requested"

    @classmethod
    def _pg_job_row(cls, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("job was not found")
        result = dict(row)
        result["payload"] = cls._json_value(result.get("payload"), {})
        result["error"] = cls._json_value(result.get("error")) if result.get("error") is not None else None
        result["result"] = cls._json_value(result.get("result")) if result.get("result") is not None else None
        result["cancel_requested"] = bool(result.get("cancel_requested"))
        result["retryable"] = result.get("status") not in {"succeeded", "cancelled"} and int(result.get("attempts", 0)) < int(result.get("max_attempts", 3))
        available_at = result.get("available_at")
        result["retry_after"] = available_at.isoformat() if hasattr(available_at, "isoformat") and result.get("status") == "queued" and result.get("attempts", 0) else (available_at if result.get("status") == "queued" and result.get("attempts", 0) else None)
        return result

    def _pg_fetch_job(self, cursor: Any, job_id: str, *, for_update: bool = False) -> dict[str, Any] | None:
        cursor.execute(f"SELECT {self._JOB_COLUMNS} FROM trace_jobs WHERE job_id=%s" + (" FOR UPDATE" if for_update else ""), (job_id,))
        return self._cursor_mapping(cursor, cursor.fetchone())

    def _pg_transition_job(
        self,
        conn: Any,
        *,
        row: dict[str, Any],
        status: str,
        actor: str,
        reason: str | None = None,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        available_at: datetime | None = None,
        lease_until: datetime | None = None,
        cancel_requested: bool | None = None,
    ) -> dict[str, Any]:
        allowed = {"queued", "running", "succeeded", "failed", "cancelled"}
        if status not in allowed:
            raise InvariantViolation(f"unsupported job status {status!r}")
        now = datetime.now(UTC)
        event = self._append_event_in_connection(
            conn,
            stream_id=f"workspace:{row['workspace_id']}",
            event_type="job.status_changed",
            payload={
                "job_id": row["job_id"], "workspace_id": row["workspace_id"],
                "from_status": row["status"], "status": status, "reason": reason,
                "result": result, "error": error,
            },
            actor=actor,
        )
        effective_available = available_at or (now if status != "queued" else now)
        effective_cancel = bool(row.get("cancel_requested")) if cancel_requested is None else bool(cancel_requested)
        with conn.cursor() as cursor:
            cursor.execute(
                """UPDATE trace_jobs SET status=%s,updated_at=%s,available_at=%s,lease_until=%s,
                   error=%s::jsonb,result=%s::jsonb,started_at=%s,finished_at=%s,cancel_requested=%s
                   WHERE job_id=%s""",
                (
                    status, now, effective_available, lease_until,
                    json.dumps(error, sort_keys=True) if error is not None else None,
                    json.dumps(result, sort_keys=True) if result is not None else None,
                    now if status == "running" else (row.get("started_at") if row.get("started_at") else None),
                    now if status in {"succeeded", "failed", "cancelled"} else None,
                    effective_cancel, row["job_id"],
                ),
            )
            updated = self._pg_fetch_job(cursor, str(row["job_id"]))
        if updated is None:
            raise InvariantViolation("job transition removed its projection")
        projected = self._pg_job_row(updated)
        projected["status_event_offset"] = event.offset
        return projected

    def create_job(
        self,
        *,
        workspace_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        actor: str = "system",
        idempotency_key: str | None = None,
        request_id: str | None = None,
        webhook_id: str | None = None,
        max_attempts: int = 3,
        status: str = "queued",
    ) -> dict[str, Any]:
        """Create a PostgreSQL job and its creation event atomically."""

        if self.delegate is not None and hasattr(self.delegate, "create_job"):
            return self.delegate.create_job(
                workspace_id=workspace_id, kind=kind, payload=payload, actor=actor,
                idempotency_key=idempotency_key, request_id=request_id,
                webhook_id=webhook_id, max_attempts=max_attempts, status=status,
            )
        if status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise InvariantViolation(f"unsupported job status {status!r}")
        if not kind.strip() or max_attempts < 1:
            raise InvariantViolation("job kind is required and max_attempts must be positive")
        payload = payload or {}
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                if idempotency_key:
                    cursor.execute(
                        f"SELECT {self._JOB_COLUMNS} FROM trace_jobs WHERE workspace_id=%s AND idempotency_key=%s",
                        (workspace_id, idempotency_key),
                    )
                    existing = self._cursor_mapping(cursor, cursor.fetchone())
                    if existing:
                        existing_payload = self._json_value(existing.get("payload"), {})
                        if existing["kind"] != kind or _digest(existing_payload) != _digest(payload):
                            raise IdempotencyConflict("job idempotency key was reused with a different operation")
                        duplicate = self._pg_job_row(existing)
                        duplicate["duplicate"] = True
                        return duplicate
            job_id = str(uuid.uuid4())
            now = datetime.now(UTC)
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="job.created",
                payload={"job_id": job_id, "workspace_id": workspace_id, "kind": kind, "status": status, "payload": payload, "request_id": request_id},
                actor=actor, correlation_id=request_id,
                idempotency_key=f"job:{idempotency_key}" if idempotency_key else None,
            )
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_jobs(
                       job_id,workspace_id,kind,status,payload,attempts,max_attempts,available_at,
                       request_id,webhook_id,created_event_offset,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s::jsonb,0,%s,%s,%s,%s,%s,%s,%s)""",
                    (job_id, workspace_id, kind, status, json.dumps(payload, sort_keys=True), max_attempts, now, request_id, webhook_id, event.offset, now, now),
                )
                created = self._pg_fetch_job(cursor, job_id)
            return self._pg_job_row(created)

    def get_job(self, job_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_job"):
            return self.delegate.get_job(job_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                row = self._pg_fetch_job(cursor, job_id)
        return self._pg_job_row(row)

    def list_jobs(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "list_jobs"):
            return self.delegate.list_jobs(workspace_id=workspace_id, status=status, kind=kind, limit=limit, offset=offset)
        clauses: list[str] = []
        values: list[Any] = []
        if workspace_id is not None:
            clauses.append("workspace_id=%s")
            values.append(workspace_id)
        if status is not None:
            clauses.append("status=%s")
            values.append(status)
        if kind is not None:
            clauses.append("kind=%s")
            values.append(kind)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(f"SELECT {self._JOB_COLUMNS} FROM trace_jobs{where} ORDER BY created_at DESC,job_id DESC LIMIT %s OFFSET %s", [*values, max(1, min(int(limit), 200)), max(0, int(offset))])
                rows = [self._cursor_mapping(cursor, row) for row in cursor.fetchall()]
        return [self._pg_job_row(row) for row in rows]

    def claim_jobs(
        self,
        *,
        limit: int = 10,
        lease_seconds: int = 300,
        kind: str | None = None,
        job_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "claim_jobs"):
            return self.delegate.claim_jobs(limit=limit, lease_seconds=lease_seconds, kind=kind, job_id=job_id, workspace_id=workspace_id)
        workspace_id = workspace_id or _runtime_workspace.get()
        if not workspace_id:
            raise InvariantViolation("job worker requires one explicit workspace scope")
        now = datetime.now(UTC)
        lease_until = datetime.fromtimestamp(now.timestamp() + max(1, lease_seconds), UTC)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("UPDATE trace_jobs SET status='queued',lease_until=NULL,available_at=%s WHERE workspace_id=%s AND status='running' AND lease_until IS NOT NULL AND lease_until<%s AND cancel_requested=FALSE", (now, workspace_id, now))
                clauses = ["workspace_id=%s", "status='queued'", "available_at<=%s", "cancel_requested=FALSE"]
                values: list[Any] = [workspace_id, now]
                if kind:
                    clauses.append("kind=%s")
                    values.append(kind)
                if job_id:
                    clauses.append("job_id=%s")
                    values.append(job_id)
                cursor.execute(f"SELECT {self._JOB_COLUMNS} FROM trace_jobs WHERE {' AND '.join(clauses)} ORDER BY created_at,job_id LIMIT %s FOR UPDATE SKIP LOCKED", [*values, max(1, min(int(limit), 100))])
                rows = [self._cursor_mapping(cursor, row) for row in cursor.fetchall()]
            claimed: list[dict[str, Any]] = []
            for row in rows:
                if row is None:
                    continue
                transitioned = self._pg_transition_job(conn, row=row, status="running", actor="job-worker", available_at=now, lease_until=lease_until)
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE trace_jobs SET attempts=attempts+1 WHERE job_id=%s", (row["job_id"],))
                    updated = self._pg_fetch_job(cursor, str(row["job_id"]))
                claimed.append(self._pg_job_row(updated))
            return claimed

    def complete_job(self, job_id: str, *, result: dict[str, Any] | None = None, actor: str = "job-worker") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "complete_job"):
            return self.delegate.complete_job(job_id, result=result, actor=actor)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                row = self._pg_fetch_job(cursor, job_id, for_update=True)
            if row is None:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] in {"succeeded", "cancelled"}:
                return self._pg_job_row(row)
            return self._pg_transition_job(conn, row=row, status="succeeded", actor=actor, result=result, lease_until=None)

    def fail_job(self, job_id: str, *, error: dict[str, Any], actor: str = "job-worker", retry: bool = True) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "fail_job"):
            return self.delegate.fail_job(job_id, error=error, actor=actor, retry=retry)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                row = self._pg_fetch_job(cursor, job_id, for_update=True)
            if row is None:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] in {"succeeded", "cancelled"}:
                return self._pg_job_row(row)
            should_retry = retry and int(row["attempts"]) < int(row["max_attempts"]) and not row["cancel_requested"]
            if should_retry:
                delay = min(300, 2 ** max(0, int(row["attempts"]) - 1))
                return self._pg_transition_job(conn, row=row, status="queued", actor=actor, reason="retry_scheduled", error=error, available_at=datetime.fromtimestamp(datetime.now(UTC).timestamp() + delay, UTC), lease_until=None)
            return self._pg_transition_job(conn, row=row, status="failed", actor=actor, error=error, lease_until=None)

    def cancel_job(self, job_id: str, *, actor: str = "system", reason: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "cancel_job"):
            return self.delegate.cancel_job(job_id, actor=actor, reason=reason)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                row = self._pg_fetch_job(cursor, job_id, for_update=True)
            if row is None:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] in {"succeeded", "failed", "cancelled"}:
                return self._pg_job_row(row)
            return self._pg_transition_job(conn, row=row, status="cancelled", actor=actor, reason=reason or "cancelled_by_request", lease_until=None, cancel_requested=True)

    def retry_job(self, job_id: str, *, actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "retry_job"):
            return self.delegate.retry_job(job_id, actor=actor)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                row = self._pg_fetch_job(cursor, job_id, for_update=True)
            if row is None:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] == "running":
                raise InvariantViolation("running jobs must expire or be cancelled before retry")
            if row["status"] == "succeeded":
                return self._pg_job_row(row)
            return self._pg_transition_job(conn, row=row, status="queued", actor=actor, reason="manual_retry", available_at=datetime.now(UTC), lease_until=None, cancel_requested=False)

    @classmethod
    def _pg_webhook_row(cls, row: dict[str, Any] | None, *, include_ciphertext: bool = False) -> dict[str, Any]:
        if not row:
            raise NotFoundError("webhook was not found")
        result = dict(row)
        result["event_types"] = cls._json_value(result.pop("event_types"), [])
        ciphertext = result.pop("secret_ciphertext", None)
        if include_ciphertext:
            result["secret_ciphertext"] = ciphertext
        return result

    def create_webhook(
        self,
        *,
        workspace_id: str,
        url: str,
        event_types: list[str],
        secret_hash: str,
        secret_ciphertext: str,
        actor: str,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_webhook"):
            return self.delegate.create_webhook(workspace_id=workspace_id, url=url, event_types=event_types, secret_hash=secret_hash, secret_ciphertext=secret_ciphertext, actor=actor)
        identifier = str(uuid.uuid4())
        now = datetime.now(UTC)
        with self.connection() as conn:
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="webhook.created",
                payload={"webhook_id": identifier, "workspace_id": workspace_id, "url": url, "event_types": event_types, "secret_hash": secret_hash}, actor=actor,
            )
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_webhooks(webhook_id,workspace_id,url,secret_hash,secret_ciphertext,event_types,status,created_event_offset,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s::jsonb,'active',%s,%s)""",
                    (identifier, workspace_id, url, secret_hash, secret_ciphertext, json.dumps(event_types), event.offset, now),
                )
                cursor.execute("SELECT webhook_id,workspace_id,url,secret_hash,secret_ciphertext,event_types,status,created_event_offset,created_at,rotated_at FROM trace_webhooks WHERE webhook_id=%s", (identifier,))
                result = self._pg_webhook_row(self._cursor_mapping(cursor, cursor.fetchone()), include_ciphertext=True)
            return result

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_webhook"):
            return self.delegate.get_webhook(webhook_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT webhook_id,workspace_id,url,secret_hash,secret_ciphertext,event_types,status,created_event_offset,created_at,rotated_at FROM trace_webhooks WHERE webhook_id=%s", (webhook_id,))
                return self._pg_webhook_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def webhook_secret(self, webhook_id: str, *, cipher: Any) -> str:
        if self.delegate is not None and hasattr(self.delegate, "webhook_secret"):
            return self.delegate.webhook_secret(webhook_id, cipher=cipher)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT secret_ciphertext FROM trace_webhooks WHERE webhook_id=%s", (webhook_id,))
                row = cursor.fetchone()
        if not row:
            raise NotFoundError(f"webhook {webhook_id} was not found")
        return cipher.decrypt(row[0])

    def rotate_webhook(
        self,
        webhook_id: str,
        *,
        secret_hash: str,
        secret_ciphertext: str,
        actor: str,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "rotate_webhook"):
            return self.delegate.rotate_webhook(webhook_id, secret_hash=secret_hash, secret_ciphertext=secret_ciphertext, actor=actor)
        now = datetime.now(UTC)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT workspace_id FROM trace_webhooks WHERE webhook_id=%s FOR UPDATE", (webhook_id,))
                row = cursor.fetchone()
            if not row:
                raise NotFoundError(f"webhook {webhook_id} was not found")
            workspace_id = str(row[0])
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="webhook.rotated",
                payload={"webhook_id": webhook_id, "workspace_id": workspace_id, "secret_hash": secret_hash}, actor=actor,
            )
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_webhooks SET secret_hash=%s,secret_ciphertext=%s,rotated_at=%s WHERE webhook_id=%s", (secret_hash, secret_ciphertext, now, webhook_id))
                cursor.execute("SELECT webhook_id,workspace_id,url,secret_hash,secret_ciphertext,event_types,status,created_event_offset,created_at,rotated_at FROM trace_webhooks WHERE webhook_id=%s", (webhook_id,))
                result = self._pg_webhook_row(self._cursor_mapping(cursor, cursor.fetchone()), include_ciphertext=True)
            result["rotation_event_offset"] = event.offset
            return result

    # ----------------------------------------------------- webhook delivery
    @classmethod
    def _pg_delivery_row(cls, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("webhook delivery was not found")
        result = dict(row)
        result["payload"] = cls._json_value(result.pop("payload"), {})
        return result

    def enqueue_webhook_delivery(self, job: dict[str, Any], *, max_attempts: int = 8) -> dict[str, Any] | None:
        if self.delegate is not None and hasattr(self.delegate, "enqueue_webhook_delivery"):
            return self.delegate.enqueue_webhook_delivery(job, max_attempts=max_attempts)
        webhook_id = job.get("webhook_id")
        if not webhook_id:
            return None
        workspace_id = str(job["workspace_id"])
        event_type = "job." + str(job["status"])
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT webhook_id,workspace_id,event_types,status FROM trace_webhooks WHERE webhook_id=%s AND workspace_id=%s", (webhook_id, workspace_id))
                webhook = self._cursor_mapping(cursor, cursor.fetchone())
                if not webhook:
                    raise NotFoundError("job webhook was not found in its workspace")
                event_types = self._json_value(webhook.get("event_types"), [])
                if webhook["status"] != "active" or (event_types and event_type not in event_types):
                    return None
                cursor.execute("SELECT delivery_id,webhook_id,workspace_id,job_id,event_type,payload,status,attempts,max_attempts,available_at,lease_until,last_error,delivered_at,created_event_offset,created_at,updated_at FROM trace_webhook_deliveries WHERE webhook_id=%s AND job_id=%s AND event_type=%s", (webhook_id, job["job_id"], event_type))
                existing = self._cursor_mapping(cursor, cursor.fetchone())
                if existing:
                    return self._pg_delivery_row(existing)
            payload = {
                "delivery_id": identifier, "event": event_type, "job_id": job["job_id"],
                "workspace_id": workspace_id, "kind": job["kind"], "status": job["status"],
                "result": job.get("result"), "error": job.get("error"), "request_id": job.get("request_id"),
            }
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="webhook.delivery_queued",
                payload={"delivery_id": identifier, "webhook_id": str(webhook_id), "workspace_id": workspace_id, "job_id": str(job["job_id"]), "event_type": event_type},
                actor="webhook-dispatcher", correlation_id=str(job["request_id"]) if job.get("request_id") else None,
            )
            now = datetime.now(UTC)
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_webhook_deliveries(
                       delivery_id,webhook_id,workspace_id,job_id,event_type,payload,status,attempts,max_attempts,
                       available_at,created_event_offset,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,'pending',0,%s,%s,%s,%s,%s)""",
                    (identifier, webhook_id, workspace_id, job["job_id"], event_type, json.dumps(payload), max(1, min(int(max_attempts), 32)), now, event.offset, now, now),
                )
                cursor.execute("SELECT delivery_id,webhook_id,workspace_id,job_id,event_type,payload,status,attempts,max_attempts,available_at,lease_until,last_error,delivered_at,created_event_offset,created_at,updated_at FROM trace_webhook_deliveries WHERE delivery_id=%s", (identifier,))
                return self._pg_delivery_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def claim_webhook_deliveries(
        self,
        *,
        limit: int = 25,
        lease_seconds: int = 30,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "claim_webhook_deliveries"):
            return self.delegate.claim_webhook_deliveries(limit=limit, lease_seconds=lease_seconds, workspace_id=workspace_id)
        workspace_id = workspace_id or _runtime_workspace.get()
        if not workspace_id:
            raise InvariantViolation("webhook worker requires TRACE_WORKER_WORKSPACE_ID or an authorization scope")
        now = datetime.now(UTC)
        lease_until = datetime.fromtimestamp(now.timestamp() + max(1, int(lease_seconds)), UTC)
        columns = "delivery_id,webhook_id,workspace_id,job_id,event_type,payload,status,attempts,max_attempts,available_at,lease_until,last_error,delivered_at,created_event_offset,created_at,updated_at"
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("UPDATE trace_webhook_deliveries SET status='pending',lease_until=NULL,updated_at=%s WHERE workspace_id=%s AND status='inflight' AND lease_until<%s", (now, workspace_id, now))
                cursor.execute(f"SELECT {columns} FROM trace_webhook_deliveries WHERE workspace_id=%s AND status='pending' AND available_at<=%s ORDER BY created_at,delivery_id LIMIT %s FOR UPDATE SKIP LOCKED", (workspace_id, now, max(1, min(int(limit), 100))))
                rows = [self._cursor_mapping(cursor, row) for row in cursor.fetchall()]
                claimed: list[dict[str, Any]] = []
                for row in rows:
                    if row is None:
                        continue
                    cursor.execute("UPDATE trace_webhook_deliveries SET status='inflight',attempts=attempts+1,lease_until=%s,updated_at=%s WHERE delivery_id=%s AND status='pending'", (lease_until, now, row["delivery_id"]))
                    if cursor.rowcount:
                        cursor.execute(f"SELECT {columns} FROM trace_webhook_deliveries WHERE delivery_id=%s", (row["delivery_id"],))
                        claimed.append(self._pg_delivery_row(self._cursor_mapping(cursor, cursor.fetchone())))
                return claimed

    def mark_webhook_delivery_succeeded(self, delivery_id: str) -> dict[str, Any]:
        columns = "delivery_id,webhook_id,workspace_id,job_id,event_type,payload,status,attempts,max_attempts,available_at,lease_until,last_error,delivered_at,created_event_offset,created_at,updated_at"
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute(f"SELECT {columns} FROM trace_webhook_deliveries WHERE delivery_id=%s FOR UPDATE", (delivery_id,))
                delivery = self._pg_delivery_row(self._cursor_mapping(cursor, cursor.fetchone()))
            if delivery["status"] == "succeeded":
                return delivery
            if delivery["status"] != "inflight":
                raise InvariantViolation("webhook delivery is not leased")
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{delivery['workspace_id']}", event_type="webhook.delivery_succeeded", payload={"delivery_id": delivery_id, "workspace_id": delivery["workspace_id"], "job_id": str(delivery["job_id"]), "attempts": delivery["attempts"]}, actor="webhook-delivery-worker")
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_webhook_deliveries SET status='succeeded',lease_until=NULL,delivered_at=NOW(),updated_at=NOW(),last_error=NULL WHERE delivery_id=%s", (delivery_id,))
                cursor.execute(f"SELECT {columns} FROM trace_webhook_deliveries WHERE delivery_id=%s", (delivery_id,))
                result = self._pg_delivery_row(self._cursor_mapping(cursor, cursor.fetchone()))
            result["status_event_offset"] = event.offset
            return result

    def fail_webhook_delivery(self, delivery_id: str, *, error: str, retry_delay_seconds: int | None = None) -> dict[str, Any]:
        columns = "delivery_id,webhook_id,workspace_id,job_id,event_type,payload,status,attempts,max_attempts,available_at,lease_until,last_error,delivered_at,created_event_offset,created_at,updated_at"
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute(f"SELECT {columns} FROM trace_webhook_deliveries WHERE delivery_id=%s FOR UPDATE", (delivery_id,))
                delivery = self._pg_delivery_row(self._cursor_mapping(cursor, cursor.fetchone()))
            if delivery["status"] != "inflight":
                raise InvariantViolation("webhook delivery is not leased")
            dead_letter = int(delivery["attempts"]) >= int(delivery["max_attempts"])
            delay = int(retry_delay_seconds if retry_delay_seconds is not None else min(3_600, 2 ** min(int(delivery["attempts"]), 10)))
            available_at = datetime.fromtimestamp(datetime.now(UTC).timestamp() + max(1, delay), UTC)
            status = "dead_letter" if dead_letter else "pending"
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{delivery['workspace_id']}", event_type="webhook.delivery_dead_lettered" if dead_letter else "webhook.delivery_retry_scheduled", payload={"delivery_id": delivery_id, "workspace_id": delivery["workspace_id"], "job_id": str(delivery["job_id"]), "attempts": delivery["attempts"], "error": error[:500]}, actor="webhook-delivery-worker")
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_webhook_deliveries SET status=%s,lease_until=NULL,available_at=%s,last_error=%s,updated_at=NOW() WHERE delivery_id=%s", (status, available_at, error[:2_000], delivery_id))
                cursor.execute(f"SELECT {columns} FROM trace_webhook_deliveries WHERE delivery_id=%s", (delivery_id,))
                result = self._pg_delivery_row(self._cursor_mapping(cursor, cursor.fetchone()))
            result["status_event_offset"] = event.offset
            return result

    @classmethod
    def _pg_api_key_row(cls, row: dict[str, Any] | None, *, include_hash: bool = False) -> dict[str, Any]:
        if not row:
            raise NotFoundError("API key was not found")
        result = dict(row)
        result["scopes"] = cls._json_value(result.pop("scopes"), [])
        result["allowed_visibility"] = cls._json_value(result.pop("allowed_visibility"), [])
        result["model_permissions"] = cls._json_value(result.pop("model_permissions"), [])
        if not include_hash:
            result.pop("key_hash", None)
        return result

    def create_api_key(
        self,
        *,
        workspace_id: str,
        subject: str,
        key_prefix: str,
        key_hash: str,
        scopes: list[str],
        allowed_visibility: list[str],
        model_permissions: list[str],
        expires_at: str | None,
        actor: str,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_api_key"):
            return self.delegate.create_api_key(workspace_id=workspace_id, subject=subject, key_prefix=key_prefix, key_hash=key_hash, scopes=scopes, allowed_visibility=allowed_visibility, model_permissions=model_permissions, expires_at=expires_at, actor=actor)
        identifier = str(uuid.uuid4())
        now = datetime.now(UTC)
        with self.connection() as conn:
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="api_key.created",
                payload={"api_key_id": identifier, "workspace_id": workspace_id, "subject": subject, "key_prefix": key_prefix, "scopes": scopes, "allowed_visibility": allowed_visibility, "model_permissions": model_permissions, "expires_at": expires_at}, actor=actor,
            )
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_api_keys(api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,'active',%s,%s,%s)""",
                    (identifier, workspace_id, subject, key_prefix, key_hash, json.dumps(scopes), json.dumps(allowed_visibility), json.dumps(model_permissions), expires_at, event.offset, now),
                )
                cursor.execute("SELECT api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at,revoked_at FROM trace_api_keys WHERE api_key_id=%s", (identifier,))
                return self._pg_api_key_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def get_api_key(self, api_key_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_api_key"):
            return self.delegate.get_api_key(api_key_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at,revoked_at FROM trace_api_keys WHERE api_key_id=%s", (api_key_id,))
                return self._pg_api_key_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def resolve_api_key(self, raw_key: str) -> dict[str, Any] | None:
        if self.delegate is not None and hasattr(self.delegate, "resolve_api_key"):
            return self.delegate.resolve_api_key(raw_key)
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_api_key_lookup(cursor, digest)
                cursor.execute("SELECT api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at,revoked_at FROM trace_api_keys WHERE key_hash=%s AND status='active' AND (expires_at IS NULL OR expires_at>NOW())", (digest,))
                row = self._cursor_mapping(cursor, cursor.fetchone())
        return self._pg_api_key_row(row, include_hash=True) if row else None

    def revoke_api_key(self, api_key_id: str, *, actor: str, reason: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "revoke_api_key"):
            return self.delegate.revoke_api_key(api_key_id, actor=actor, reason=reason)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT workspace_id,status FROM trace_api_keys WHERE api_key_id=%s FOR UPDATE", (api_key_id,))
                row = cursor.fetchone()
            if not row:
                raise NotFoundError(f"API key {api_key_id} was not found")
            workspace_id, status = str(row[0]), row[1]
            if status == "revoked":
                with conn.cursor() as cursor:
                    cursor.execute("SELECT api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at,revoked_at FROM trace_api_keys WHERE api_key_id=%s", (api_key_id,))
                    return self._pg_api_key_row(self._cursor_mapping(cursor, cursor.fetchone()))
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="api_key.revoked",
                payload={"api_key_id": api_key_id, "workspace_id": workspace_id, "reason": reason}, actor=actor,
            )
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_api_keys SET status='revoked',revoked_at=NOW() WHERE api_key_id=%s", (api_key_id,))
                cursor.execute("SELECT api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at,revoked_at FROM trace_api_keys WHERE api_key_id=%s", (api_key_id,))
                result = self._pg_api_key_row(self._cursor_mapping(cursor, cursor.fetchone()))
            result["revocation_event_offset"] = event.offset
            return result

    # ---------------------------------------------------------- model audits
    def record_model_audit(self, audit: dict[str, Any]) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "record_model_audit"):
            return self.delegate.record_model_audit(audit)
        workspace_id = str(audit.get("workspace_id") or "")
        if not workspace_id:
            raise InvariantViolation("model audit requires a workspace_id")
        identifier = str(uuid.uuid4())
        payload = {
            "model_call_audit_id": identifier,
            "workspace_id": workspace_id,
            "model_id": str(audit.get("model_id") or "unknown"),
            "purpose": str(audit.get("purpose") or "unknown"),
            "prompt_template_revision": str(audit.get("prompt_template_revision") or "unknown"),
            "response_schema_hash": str(audit.get("response_schema_hash") or ""),
            "excerpt_hashes": list(audit.get("excerpt_hashes") or []),
            "node_count": int(audit.get("node_count") or 0),
            "estimated_tokens": int(audit.get("estimated_tokens") or 0),
            "cloud_tokens": int(audit.get("cloud_tokens") or 0),
            "cost_usd": float(audit.get("cost_usd") or 0.0),
            "status": str(audit.get("status") or "succeeded"),
        }
        with self.connection() as conn:
            event = self._append_event_in_connection(
                conn,
                stream_id=f"workspace:{workspace_id}",
                event_type="model.call_audited",
                payload=payload,
                actor=str(audit.get("actor") or "system"),
                correlation_id=str(audit["request_id"]) if audit.get("request_id") else None,
            )
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_model_call_audits(
                       model_call_audit_id,workspace_id,model_id,purpose,actor,request_id,
                       prompt_template_revision,response_schema_hash,excerpt_hashes,node_count,
                       estimated_tokens,cloud_tokens,cost_usd,status,created_event_offset,created_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,NOW())""",
                    (
                        identifier, workspace_id, payload["model_id"], payload["purpose"], str(audit.get("actor") or "system"),
                        audit.get("request_id"), payload["prompt_template_revision"], payload["response_schema_hash"],
                        json.dumps(payload["excerpt_hashes"]), payload["node_count"], payload["estimated_tokens"],
                        payload["cloud_tokens"], payload["cost_usd"], payload["status"], event.offset,
                    ),
                )
        return {"model_call_audit_id": identifier, "created_event_offset": event.offset, **payload}

    def model_cost_total(self, workspace_id: str) -> float:
        if self.delegate is not None and hasattr(self.delegate, "model_cost_total"):
            return float(self.delegate.model_cost_total(workspace_id))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT COALESCE(SUM(cost_usd),0) FROM trace_model_call_audits WHERE workspace_id=%s AND status='succeeded'", (workspace_id,))
                return float(cursor.fetchone()[0] or 0.0)

    # ------------------------------------------------ Cortex / data-plane additions
    # These methods intentionally mirror the embedded adapter's bounded
    # interface. They use the additive 004 migration and never write trusted
    # ``trace_edge_versions`` for hierarchy, affinity, or behavioral state.
    def hot_candidates(self, workspace_id: str, query: str, *, limit: int = 100, visibility: Sequence[str] | None = None, facets: Sequence[str] | None = None, as_of_event: int | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "hot_candidates"):
            return self.delegate.hot_candidates(workspace_id, query, limit=limit, visibility=visibility, facets=facets, as_of_event=as_of_event)
        terms = [item.lower() for item in re.findall(r"[\w'-]+", query) if len(item) > 1][:8]
        clauses = ["workspace_id=%s"]
        values: list[Any] = [workspace_id]
        if as_of_event is not None:
            clauses.append("visible_from_event<=%s")
            values.append(as_of_event)
        if terms:
            clauses.append("(" + " OR ".join("LOWER(content) LIKE %s" for _ in terms) + ")")
            values.extend(f"%{term}%" for term in terms)
        values.append(max(1, min(int(limit) * 4, 800)))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    f"SELECT atom_version_id,security,facets FROM trace_hot_inbox WHERE {' AND '.join(clauses)} ORDER BY visible_from_event DESC LIMIT %s",
                    values,
                )
                rows = cursor.fetchall()
        allowed = set(visibility or ())
        required = set(facets or ())
        ids: list[str] = []
        for atom_id, security, row_facets in rows:
            security_value = self._json_value(security, {})
            facet_value = set(self._json_value(row_facets, []))
            if (not allowed or security_value.get("visibility") in allowed) and (not required or required <= facet_value):
                ids.append(str(atom_id))
            if len(ids) >= max(1, min(int(limit), 200)):
                break
        return self.atom_versions(ids)

    def current_atom_versions_for_nodes(self, workspace_id: str, node_ids: Sequence[str], *, as_of_event: int | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "current_atom_versions_for_nodes"):
            return self.delegate.current_atom_versions_for_nodes(workspace_id, node_ids, as_of_event=as_of_event)
        if not node_ids:
            return []
        marks = ",".join("%s" for _ in node_ids)
        condition = " AND nv.created_event_offset<=%s" if as_of_event is not None else ""
        values: list[Any] = [workspace_id, *node_ids]
        if as_of_event is not None:
            values.append(as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    f"""WITH ranked AS (
                        SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                               n.workspace_id,n.facets,n.security,ROW_NUMBER() OVER (PARTITION BY nv.node_id ORDER BY nv.version DESC) AS rank
                        FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                        WHERE n.workspace_id=%s AND n.node_id IN ({marks}) AND n.facets @> '[\"atom\"]'::jsonb{condition}
                    ) SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset,workspace_id,facets,security
                    FROM ranked WHERE rank=1""",
                    values,
                )
                rows = [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]
        by_node = {row["node_id"]: row for row in rows}
        return [by_node[str(node_id)] for node_id in node_ids if str(node_id) in by_node]

    def atom_versions_by_event_range(self, workspace_id: str, from_event_offset: int, through_event_offset: int, *, limit: int = 1_000) -> list[dict[str, Any]]:
        if from_event_offset < 1 or through_event_offset < from_event_offset:
            raise InvariantViolation("invalid atom event range")
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    """SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                              n.workspace_id,n.facets,n.security
                       FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                       WHERE n.workspace_id=%s AND n.facets @> '[\"atom\"]'::jsonb
                         AND nv.created_event_offset BETWEEN %s AND %s
                       ORDER BY nv.created_event_offset,nv.atom_version_id LIMIT %s""",
                    (workspace_id, from_event_offset, through_event_offset, max(1, min(int(limit), 10_000))),
                )
                return [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]

    def stage_attachment(self, *, workspace_id: str, attachment: dict[str, Any], ingestion_id: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "stage_attachment"):
            return self.delegate.stage_attachment(workspace_id=workspace_id, attachment=attachment, ingestion_id=ingestion_id)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="attachment.staged", payload={"staging_id": identifier, "workspace_id": workspace_id, "content_hash": attachment["content_hash"], "object_key": attachment["object_key"], "ingestion_id": ingestion_id}, actor="ingestion-stager")
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_attachment_staging(staging_id,workspace_id,content_hash,object_key,attachment,status,ingestion_id,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s::jsonb,'staged',%s,NOW(),NOW())""",
                    (identifier, workspace_id, attachment["content_hash"], attachment["object_key"], json.dumps(attachment), ingestion_id),
                )
        return {"staging_id": identifier, "workspace_id": workspace_id, "attachment": attachment, "status": "staged", "staged_event_offset": event.offset}

    def finalize_attachment_staging(
        self,
        staging_id: str,
        *,
        ingestion_id: str,
        canonical_event_offset: int | None = None,
        actor: str = "ingestion-stager",
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "finalize_attachment_staging"):
            return self.delegate.finalize_attachment_staging(staging_id, ingestion_id=ingestion_id, canonical_event_offset=canonical_event_offset, actor=actor, workspace_id=workspace_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT workspace_id,status FROM trace_attachment_staging WHERE staging_id=%s FOR UPDATE", (staging_id,))
                row = cursor.fetchone()
            if not row:
                raise NotFoundError("attachment staging record was not found")
            workspace_id, status = str(row[0]), str(row[1])
            if status == "committed":
                return {"staging_id": staging_id, "workspace_id": workspace_id, "status": status}
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="attachment.staging_committed", payload={"staging_id": staging_id, "workspace_id": workspace_id, "ingestion_id": ingestion_id}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_attachment_staging SET status='committed',ingestion_id=%s,canonical_event_offset=%s,last_error=NULL,updated_at=NOW() WHERE staging_id=%s", (ingestion_id, canonical_event_offset or event.offset, staging_id))
        return {"staging_id": staging_id, "workspace_id": workspace_id, "ingestion_id": ingestion_id, "status": "committed", "committed_event_offset": event.offset}

    def fail_attachment_staging(
        self,
        staging_id: str,
        *,
        error: str,
        actor: str = "ingestion-stager",
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "fail_attachment_staging"):
            return self.delegate.fail_attachment_staging(staging_id, error=error, actor=actor, workspace_id=workspace_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT workspace_id FROM trace_attachment_staging WHERE staging_id=%s FOR UPDATE", (staging_id,))
                row = cursor.fetchone()
            if not row:
                raise NotFoundError("attachment staging record was not found")
            workspace_id = str(row[0])
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="attachment.staging_cleanup_required", payload={"staging_id": staging_id, "workspace_id": workspace_id, "error": error[:500]}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_attachment_staging SET status='cleanup_required',last_error=%s,updated_at=NOW() WHERE staging_id=%s", (error[:2_000], staging_id))
        return {"staging_id": staging_id, "workspace_id": workspace_id, "status": "cleanup_required", "cleanup_event_offset": event.offset}

    def reconcile_attachment_staging(self, workspace_id: str, *, actor: str = "attachment-reconciler") -> dict[str, Any]:
        """Reconcile durable object staging without deleting object bytes.

        A storage lifecycle worker decides whether a cleanup-required object
        may be removed.  The database worker merely exposes recoverable
        targets and commits records that did reach canonical attachment state.
        """

        if self.delegate is not None and hasattr(self.delegate, "reconcile_attachment_staging"):
            return self.delegate.reconcile_attachment_staging(workspace_id, actor=actor)
        if not workspace_id:
            raise InvariantViolation("PostgreSQL attachment reconciliation requires one workspace")
        with self.authorization_scope(workspace_id):
            with self.connection() as conn:
                with conn.cursor() as cursor:
                    self._set_workspace(cursor, workspace_id)
                    cursor.execute(
                        """SELECT staging_id,content_hash,object_key,status FROM trace_attachment_staging
                           WHERE workspace_id=%s AND status IN ('staged','cleanup_required')
                           ORDER BY created_at LIMIT 500 FOR UPDATE""",
                        (workspace_id,),
                    )
                    rows = cursor.fetchall()
                    committed = 0
                    cleanup: list[dict[str, Any]] = []
                    for staging_id, content_hash, object_key, status in rows:
                        cursor.execute(
                            """SELECT created_event_offset FROM trace_attachments
                               WHERE workspace_id=%s AND content_hash=%s AND object_key=%s LIMIT 1""",
                            (workspace_id, content_hash, object_key),
                        )
                        attachment = cursor.fetchone()
                        if attachment:
                            cursor.execute(
                                """UPDATE trace_attachment_staging SET status='committed',canonical_event_offset=%s,
                                   last_error=NULL,updated_at=NOW() WHERE staging_id=%s""",
                                (attachment[0], staging_id),
                            )
                            committed += 1
                        else:
                            if status != "cleanup_required":
                                cursor.execute(
                                    "UPDATE trace_attachment_staging SET status='cleanup_required',updated_at=NOW() WHERE staging_id=%s",
                                    (staging_id,),
                                )
                            cleanup.append({
                                "staging_id": str(staging_id), "workspace_id": workspace_id,
                                "object_key": object_key, "content_hash": content_hash,
                            })
                if rows:
                    event = self._append_event_in_connection(
                        conn,
                        stream_id=f"workspace:{workspace_id}",
                        event_type="attachment.staging_reconciled",
                        payload={"workspace_id": workspace_id, "committed": committed, "cleanup_required": len(cleanup)},
                        actor=actor,
                    )
                else:
                    event = None
        return {
            "workspace_id": workspace_id,
            "committed": committed,
            "cleanup_required": cleanup,
            "event_offset": event.offset if event else None,
        }

    def ingestion_index_state(self, ingestion_id: str) -> dict[str, dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "ingestion_index_state"):
            return self.delegate.ingestion_index_state(ingestion_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT component,status,index_revision,job_id,run_id,detail,updated_event_offset,updated_at,workspace_id,ingestion_id FROM trace_ingestion_index_state WHERE ingestion_id=%s", (ingestion_id,))
                rows = [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]
        return {str(row.pop("component")): {**row, "detail": self._json_value(row.get("detail"), {})} for row in rows}

    def set_ingestion_index_state(self, *, ingestion_id: str, component: str, status: str, index_revision: str | None = None, job_id: str | None = None, run_id: str | None = None, detail: dict[str, Any] | None = None, actor: str = "index-worker") -> dict[str, dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "set_ingestion_index_state"):
            return self.delegate.set_ingestion_index_state(ingestion_id=ingestion_id, component=component, status=status, index_revision=index_revision, job_id=job_id, run_id=run_id, detail=detail, actor=actor)
        if component not in {"hot", "lexical", "dense"} or status not in {"hot_ready", "lexical_ready", "dense_pending", "dense_ready", "failed", "stale", "pending"}:
            raise InvariantViolation("invalid ingestion index component or state")
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT workspace_id FROM trace_ingestions WHERE ingestion_id=%s", (ingestion_id,))
                row = cursor.fetchone()
            if not row:
                raise NotFoundError(f"ingestion {ingestion_id} was not found")
            workspace_id = str(row[0])
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="ingestion.index_state_updated", payload={"workspace_id": workspace_id, "ingestion_id": ingestion_id, "component": component, "status": status, "index_revision": index_revision, "job_id": job_id, "run_id": run_id}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_ingestion_index_state(ingestion_id,workspace_id,component,status,index_revision,job_id,run_id,detail,updated_event_offset,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,NOW())
                       ON CONFLICT(ingestion_id,component) DO UPDATE SET status=EXCLUDED.status,index_revision=EXCLUDED.index_revision,job_id=EXCLUDED.job_id,run_id=EXCLUDED.run_id,detail=EXCLUDED.detail,updated_event_offset=EXCLUDED.updated_event_offset,updated_at=NOW()""",
                    (ingestion_id, workspace_id, component, status, index_revision, job_id, run_id, json.dumps(detail or {}), event.offset),
                )
        return self.ingestion_index_state(ingestion_id)

    @staticmethod
    def _pg_cognitive_policy_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        value = dict(row)
        value["policy"] = PostgresEventStore._json_value(value.pop("policy"), {})
        return value

    def get_cognitive_policy(self, workspace_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_cognitive_policy"):
            return self.delegate.get_cognitive_policy(workspace_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT * FROM trace_cognitive_policy_versions WHERE workspace_id=%s AND active=true ORDER BY created_at DESC LIMIT 1", (workspace_id,))
                row = self._pg_cognitive_policy_row(self._cursor_mapping(cursor, cursor.fetchone()))
        return row or {"cognitive_policy_id": None, "workspace_id": workspace_id, "policy_revision": "cognitive-policy-v1", "policy": CognitivePolicy().model_dump(mode="json"), "active": True, "source": "default"}

    def put_cognitive_policy(self, *, workspace_id: str, policy: dict[str, Any], actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "put_cognitive_policy"):
            return self.delegate.put_cognitive_policy(workspace_id=workspace_id, policy=policy, actor=actor)
        validated = CognitivePolicy.model_validate(policy)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT policy_revision FROM trace_cognitive_policy_versions WHERE workspace_id=%s", (workspace_id,))
                used = {str(row[0]) for row in cursor.fetchall()}
            revision = validated.policy_revision
            suffix = 1
            while revision in used:
                suffix += 1
                revision = f"{validated.policy_revision}-{suffix}"
            payload = validated.model_dump(mode="json") | {"policy_revision": revision}
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="cognitive_policy.activated", payload={"workspace_id": workspace_id, "policy_revision": revision, "policy": payload}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_cognitive_policy_versions SET active=false WHERE workspace_id=%s AND active=true", (workspace_id,))
                cursor.execute("INSERT INTO trace_cognitive_policy_versions(cognitive_policy_id,workspace_id,policy_revision,policy,active,created_event_offset,created_at,actor) VALUES (%s,%s,%s,%s::jsonb,true,%s,NOW(),%s)", (identifier, workspace_id, revision, json.dumps(payload), event.offset, actor))
                cursor.execute("SELECT * FROM trace_cognitive_policy_versions WHERE cognitive_policy_id=%s", (identifier,))
                return self._pg_cognitive_policy_row(self._cursor_mapping(cursor, cursor.fetchone())) or {}

    @staticmethod
    def _pg_projection_run_row(row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("projection run was not found")
        value = dict(row)
        if value.get("projection_run_id") is not None:
            value["projection_run_id"] = str(value["projection_run_id"])
        if value.get("prior_projection_run_id") is not None:
            value["prior_projection_run_id"] = str(value["prior_projection_run_id"])
        if value.get("workspace_id") is not None:
            value["workspace_id"] = str(value["workspace_id"])
        value["output_statistics"] = PostgresEventStore._json_value(value.pop("output_statistics"), {})
        return value

    def create_projection_run(self, *, workspace_id: str, projection_kind: str, revision: str, input_from_event: int | None = None, input_through_event: int | None = None, input_checksum: str = "", model_revision: str | None = None, index_revision: str | None = None, prompt_revision: str | None = None, policy_revision: str | None = None, prior_projection_run_id: str | None = None, actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_projection_run"):
            return self.delegate.create_projection_run(workspace_id=workspace_id, projection_kind=projection_kind, revision=revision, input_from_event=input_from_event, input_through_event=input_through_event, input_checksum=input_checksum, model_revision=model_revision, index_revision=index_revision, prompt_revision=prompt_revision, policy_revision=policy_revision, prior_projection_run_id=prior_projection_run_id, actor=actor)
        if projection_kind not in {"hierarchy", "affinity", "activation"}:
            raise InvariantViolation("invalid projection kind")
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT * FROM trace_projection_runs WHERE workspace_id=%s AND projection_kind=%s AND revision=%s", (workspace_id, projection_kind, revision))
                existing = cursor.fetchone()
                if existing:
                    return self._pg_projection_run_row(self._cursor_mapping(cursor, existing))
                effective_prior = prior_projection_run_id
                if effective_prior is None:
                    cursor.execute(
                        """SELECT projection_run_id FROM trace_projection_runs
                           WHERE workspace_id=%s AND projection_kind=%s AND status='active'
                           ORDER BY activated_event_offset DESC,created_at DESC LIMIT 1""",
                        (workspace_id, projection_kind),
                    )
                    active = cursor.fetchone()
                    effective_prior = str(active[0]) if active else None
                if effective_prior:
                    cursor.execute(
                        "SELECT workspace_id,projection_kind FROM trace_projection_runs WHERE projection_run_id=%s",
                        (effective_prior,),
                    )
                    prior = cursor.fetchone()
                    if not prior or str(prior[0]) != workspace_id or str(prior[1]) != projection_kind:
                        raise InvariantViolation("projection prior run must belong to the same workspace and projection family")
            policy_revision = policy_revision or self.get_cognitive_policy(workspace_id)["policy_revision"]
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="projection.run_queued", payload={"projection_run_id": identifier, "workspace_id": workspace_id, "projection_kind": projection_kind, "revision": revision, "input_checksum": input_checksum, "policy_revision": policy_revision}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_projection_runs(projection_run_id,workspace_id,projection_kind,revision,status,input_from_event,input_through_event,input_checksum,output_statistics,model_revision,index_revision,prompt_revision,policy_revision,prior_projection_run_id,cost_usd,created_event_offset,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,'queued',%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,0,%s,NOW(),NOW())""",
                    (identifier, workspace_id, projection_kind, revision, input_from_event, input_through_event, input_checksum, json.dumps({}), model_revision, index_revision, prompt_revision, policy_revision, effective_prior, event.offset),
                )
                cursor.execute("SELECT * FROM trace_projection_runs WHERE projection_run_id=%s", (identifier,))
                return self._pg_projection_run_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def transition_projection_run(self, projection_run_id: str, *, status: str, output_statistics: dict[str, Any] | None = None, failure_detail: str | None = None, cost_usd: float | None = None, actor: str = "projection-worker") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "transition_projection_run"):
            return self.delegate.transition_projection_run(projection_run_id, status=status, output_statistics=output_statistics, failure_detail=failure_detail, cost_usd=cost_usd, actor=actor)
        if status not in {"queued", "running", "succeeded", "failed", "superseded", "active"}:
            raise InvariantViolation("unknown projection run status")
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT * FROM trace_projection_runs WHERE projection_run_id=%s FOR UPDATE", (projection_run_id,))
                run = self._pg_projection_run_row(self._cursor_mapping(cursor, cursor.fetchone()))
            if run["status"] == status:
                return run
            allowed = {
                "queued": {"running", "failed", "superseded"},
                "running": {"succeeded", "failed", "superseded"},
                "succeeded": {"active", "superseded"},
                "active": {"superseded"},
                "failed": set(),
                "superseded": set(),
            }
            if status not in allowed.get(str(run["status"]), set()):
                raise InvariantViolation(f"projection run cannot transition from {run['status']} to {status}")
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{run['workspace_id']}", event_type=f"projection.run_{status}", payload={"projection_run_id": str(projection_run_id), "workspace_id": str(run["workspace_id"]), "projection_kind": str(run["projection_kind"]), "revision": str(run["revision"]), "failure_detail": failure_detail}, actor=actor)
            with conn.cursor() as cursor:
                if status == "active":
                    cursor.execute("UPDATE trace_projection_runs SET status='superseded',updated_at=NOW() WHERE workspace_id=%s AND projection_kind=%s AND status='active' AND projection_run_id<>%s", (run["workspace_id"], run["projection_kind"], projection_run_id))
                cursor.execute("UPDATE trace_projection_runs SET status=%s,output_statistics=%s::jsonb,failure_detail=%s,cost_usd=%s,activated_event_offset=CASE WHEN %s='active' THEN %s ELSE activated_event_offset END,updated_at=NOW() WHERE projection_run_id=%s", (status, json.dumps(output_statistics if output_statistics is not None else run["output_statistics"]), failure_detail, float(cost_usd if cost_usd is not None else run["cost_usd"]), status, event.offset, projection_run_id))
                cursor.execute("SELECT * FROM trace_projection_runs WHERE projection_run_id=%s", (projection_run_id,))
                return self._pg_projection_run_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def activate_projection_run(self, projection_run_id: str, *, actor: str = "projection-worker") -> dict[str, Any]:
        return self.transition_projection_run(projection_run_id, status="active", actor=actor)

    def effective_projection_run(
        self,
        workspace_id: str,
        projection_kind: str,
        *,
        release_id: str | None = None,
        as_of_event: int | None = None,
    ) -> dict[str, Any] | None:
        if self.delegate is not None and hasattr(self.delegate, "effective_projection_run"):
            try:
                return self.delegate.effective_projection_run(
                    workspace_id, projection_kind, release_id=release_id, as_of_event=as_of_event,
                )
            except TypeError:
                return self.delegate.effective_projection_run(workspace_id, projection_kind)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                if release_id is None:
                    cursor.execute("SELECT * FROM trace_projection_runs WHERE workspace_id=%s AND projection_kind=%s AND status='active' ORDER BY activated_event_offset DESC,created_at DESC LIMIT 1", (workspace_id, projection_kind))
                else:
                    cursor.execute("SELECT component_revision,source_watermark,metadata FROM trace_cortex_release_components WHERE release_id=%s AND workspace_id=%s AND component_kind=%s", (release_id, workspace_id, projection_kind))
                    component = self._cursor_mapping(cursor, cursor.fetchone())
                    if not component:
                        return None
                    metadata = self._json_value(component.get("metadata"), {})
                    run_id = metadata.get("projection_run_id")
                    if run_id:
                        cursor.execute("SELECT * FROM trace_projection_runs WHERE projection_run_id=%s AND workspace_id=%s AND projection_kind=%s", (run_id, workspace_id, projection_kind))
                    else:
                        watermark = min(int(component["source_watermark"]), int(as_of_event) if as_of_event is not None else int(component["source_watermark"]))
                        through = int(as_of_event) if as_of_event is not None else watermark
                        cursor.execute(
                            """SELECT * FROM trace_projection_runs
                               WHERE workspace_id=%s AND projection_kind=%s
                                 AND status IN ('active','superseded','succeeded')
                                 AND COALESCE(input_through_event,created_event_offset)<=%s
                                 AND COALESCE(activated_event_offset,created_event_offset)<=%s
                               ORDER BY COALESCE(input_through_event,created_event_offset) DESC,created_at DESC LIMIT 1""",
                            (workspace_id, projection_kind, watermark, through),
                        )
                row = cursor.fetchone()
                return self._pg_projection_run_row(self._cursor_mapping(cursor, row)) if row else None

    @classmethod
    def _pg_projection_object_row(cls, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("projection object was not found")
        value = dict(row)
        if value.get("projection_object_id") is not None:
            value["projection_object_id"] = str(value["projection_object_id"])
        if value.get("projection_run_id") is not None:
            value["projection_run_id"] = str(value["projection_run_id"])
        if value.get("workspace_id") is not None:
            value["workspace_id"] = str(value["workspace_id"])
        raw_sources = cls._json_value(value.pop("source_atom_version_ids"), [])
        value["source_atom_version_ids"] = [str(x) for x in raw_sources] if isinstance(raw_sources, (list, tuple)) else []
        value["properties"] = cls._json_value(value.pop("properties"), {})
        return value

    def projection_objects(self, projection_run_id: str, *, limit: int = 2_000) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "projection_objects"):
            return self.delegate.projection_objects(projection_run_id, limit=limit)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT * FROM trace_projection_objects WHERE projection_run_id=%s ORDER BY object_kind,logical_key LIMIT %s", (projection_run_id, max(1, min(int(limit), 10_000))))
                return [self._pg_projection_object_row(self._cursor_mapping(cursor, row)) for row in cursor.fetchall()]

    def projection_objects_page(
        self,
        projection_run_id: str,
        *,
        object_kind: str,
        after_logical_key: str | None = None,
        limit: int = 1_000,
    ) -> list[dict[str, Any]]:
        """Read an indexed, bounded page from one derived projection run."""

        if self.delegate is not None and hasattr(self.delegate, "projection_objects_page"):
            return self.delegate.projection_objects_page(
                projection_run_id,
                object_kind=object_kind,
                after_logical_key=after_logical_key,
                limit=limit,
            )
        bounded_limit = max(1, min(int(limit), 2_000))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                if after_logical_key is None:
                    cursor.execute(
                        """SELECT * FROM trace_projection_objects
                           WHERE projection_run_id=%s AND object_kind=%s
                           ORDER BY logical_key LIMIT %s""",
                        (projection_run_id, object_kind, bounded_limit),
                    )
                else:
                    cursor.execute(
                        """SELECT * FROM trace_projection_objects
                           WHERE projection_run_id=%s AND object_kind=%s AND logical_key>%s
                           ORDER BY logical_key LIMIT %s""",
                        (projection_run_id, object_kind, after_logical_key, bounded_limit),
                    )
                return [
                    self._pg_projection_object_row(self._cursor_mapping(cursor, row))
                    for row in cursor.fetchall()
                ]

    def hierarchy_objects(
        self,
        workspace_id: str,
        projection_object_ids: Sequence[str],
        *,
        limit: int = 256,
        release_id: str | None = None,
        as_of_event: int | None = None,
    ) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "hierarchy_objects"):
            try:
                return self.delegate.hierarchy_objects(workspace_id, projection_object_ids, limit=limit, release_id=release_id, as_of_event=as_of_event)
            except TypeError:
                return self.delegate.hierarchy_objects(workspace_id, projection_object_ids, limit=limit)
        ids = list(dict.fromkeys(str(item) for item in projection_object_ids if item))[:max(1, min(int(limit), 512))]
        if not ids:
            return []
        run = self.effective_projection_run(workspace_id, "hierarchy", release_id=release_id, as_of_event=as_of_event)
        if not run:
            return []
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    """SELECT * FROM trace_projection_objects
                       WHERE workspace_id=%s AND projection_run_id=%s
                         AND projection_object_id = ANY(%s::uuid[])
                       ORDER BY object_kind,logical_key LIMIT %s""",
                    (workspace_id, run["projection_run_id"], ids, len(ids)),
                )
                rows = [
                    self._pg_projection_object_row(self._cursor_mapping(cursor, row))
                    | {"projection_revision": run["revision"]}
                    for row in cursor.fetchall()
                ]
        by_id = {str(row["projection_object_id"]): row for row in rows}
        return [by_id[item] for item in ids if item in by_id]

    def list_projection_runs(self, workspace_id: str, *, projection_kind: str | None = None, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "list_projection_runs"):
            return self.delegate.list_projection_runs(workspace_id, projection_kind=projection_kind, status=status, limit=limit)
        clauses = ["workspace_id=%s"]
        values: list[Any] = [workspace_id]
        if projection_kind:
            clauses.append("projection_kind=%s")
            values.append(projection_kind)
        if status:
            clauses.append("status=%s")
            values.append(status)
        values.append(max(1, min(int(limit), 500)))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(f"SELECT * FROM trace_projection_runs WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT %s", values)
                return [self._pg_projection_run_row(self._cursor_mapping(cursor, row)) for row in cursor.fetchall()]

    def write_projection_objects(self, *, projection_run_id: str, objects: Sequence[dict[str, Any]], memberships: Sequence[dict[str, Any]] = (), actor: str = "projection-worker") -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "write_projection_objects"):
            return self.delegate.write_projection_objects(projection_run_id=projection_run_id, objects=objects, memberships=memberships, actor=actor)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT * FROM trace_projection_runs WHERE projection_run_id=%s FOR UPDATE", (projection_run_id,))
                run = self._pg_projection_run_row(self._cursor_mapping(cursor, cursor.fetchone()))
            if run["status"] not in {"queued", "running"}:
                raise InvariantViolation("projection objects can only be written to a queued or running run")
            materialized: list[dict[str, Any]] = []
            ids: set[str] = set()
            for item in objects:
                identifier = str(item.get("projection_object_id") or uuid.uuid4())
                source_ids = list(dict.fromkeys(str(value) for value in item.get("source_atom_version_ids", []) if value))
                if not source_ids or not str(item.get("content") or "").strip() or identifier in ids:
                    raise InvariantViolation("projection objects require unique IDs, content, and source coverage")
                ids.add(identifier)
                materialized.append({"projection_object_id": identifier, "object_kind": str(item.get("object_kind") or "summary"), "logical_key": str(item.get("logical_key") or identifier), "content": str(item["content"]), "source_atom_version_ids": source_ids, "properties": dict(item.get("properties") or {})})
            graph: dict[str, list[str]] = {identifier: [] for identifier in ids}
            for membership in memberships:
                parent = str(membership.get("parent_projection_object_id") or "")
                child = str(membership.get("child_id") or "")
                kind = membership.get("child_kind")
                if parent not in ids or kind not in {"projection_object", "atom_version"}:
                    raise InvariantViolation("invalid projection membership")
                if kind == "projection_object":
                    if child not in ids:
                        raise InvariantViolation("projection membership references an unknown object")
                    graph[parent].append(child)
            visiting: set[str] = set()
            visited: set[str] = set()
            def visit(node: str) -> None:
                if node in visiting:
                    raise InvariantViolation("hierarchy projection containment must be acyclic")
                if node in visited:
                    return
                visiting.add(node)
                for child in graph.get(node, []):
                    visit(child)
                visiting.remove(node)
                visited.add(node)
            for object_id in sorted(ids):
                visit(object_id)
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{run['workspace_id']}", event_type="projection.objects_written", payload={"projection_run_id": str(projection_run_id), "workspace_id": str(run["workspace_id"]), "object_count": len(materialized), "membership_count": len(memberships)}, actor=actor)
            with conn.cursor() as cursor:
                for item in materialized:
                    cursor.execute("SELECT COUNT(*) FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE n.workspace_id=%s AND nv.atom_version_id = ANY(%s::uuid[])", (run["workspace_id"], item["source_atom_version_ids"]))
                    if int(cursor.fetchone()[0]) != len(item["source_atom_version_ids"]):
                        raise InvariantViolation("projection source atoms are absent or out of scope")
                    cursor.execute("INSERT INTO trace_projection_objects(projection_object_id,workspace_id,projection_run_id,object_kind,logical_key,content,source_atom_version_ids,properties,content_hash,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,NOW())", (item["projection_object_id"], run["workspace_id"], projection_run_id, item["object_kind"], item["logical_key"], item["content"], json.dumps(item["source_atom_version_ids"]), json.dumps(item["properties"]), _digest(item["content"])))
                for membership in memberships:
                    cursor.execute("INSERT INTO trace_projection_memberships(projection_membership_id,workspace_id,projection_run_id,parent_projection_object_id,child_kind,child_id,ordinal,properties) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)", (str(membership.get("projection_membership_id") or uuid.uuid4()), run["workspace_id"], projection_run_id, membership["parent_projection_object_id"], membership["child_kind"], membership["child_id"], int(membership.get("ordinal", 0)), json.dumps(dict(membership.get("properties") or {}))))
                cursor.execute("SELECT * FROM trace_projection_objects WHERE projection_run_id=%s ORDER BY object_kind,logical_key", (projection_run_id,))
                result = [self._pg_projection_object_row(self._cursor_mapping(cursor, row)) | {"created_event_offset": event.offset} for row in cursor.fetchall()]
        return result

    def hierarchy_frontier(self, workspace_id: str, query: str, *, limit: int = 32, as_of_event: int | None = None, release_id: str | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "hierarchy_frontier"):
            try:
                return self.delegate.hierarchy_frontier(workspace_id, query, limit=limit, as_of_event=as_of_event, release_id=release_id)
            except TypeError:
                return self.delegate.hierarchy_frontier(workspace_id, query, limit=limit, as_of_event=as_of_event)
        run = self.effective_projection_run(workspace_id, "hierarchy", release_id=release_id, as_of_event=as_of_event)
        if not run:
            return []
        terms = [item.lower() for item in re.findall(r"[\w'-]+", query) if len(item) > 1][:8]
        clauses = ["workspace_id=%s", "projection_run_id=%s"]
        values: list[Any] = [workspace_id, run["projection_run_id"]]
        if terms:
            clauses.append("(" + " OR ".join("LOWER(content) LIKE %s" for _ in terms) + ")")
            values.extend(f"%{term}%" for term in terms)
        values.append(max(1, min(int(limit), 200)))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(f"SELECT * FROM trace_projection_objects WHERE {' AND '.join(clauses)} ORDER BY object_kind,logical_key LIMIT %s", values)
                return [self._pg_projection_object_row(self._cursor_mapping(cursor, row)) | {"projection_revision": run["revision"]} for row in cursor.fetchall()]

    def hierarchy_children(self, workspace_id: str, parent_projection_object_ids: Sequence[str], *, limit: int = 256, release_id: str | None = None, as_of_event: int | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "hierarchy_children"):
            try:
                return self.delegate.hierarchy_children(workspace_id, parent_projection_object_ids, limit=limit, release_id=release_id, as_of_event=as_of_event)
            except TypeError:
                return self.delegate.hierarchy_children(workspace_id, parent_projection_object_ids, limit=limit)
        run = self.effective_projection_run(workspace_id, "hierarchy", release_id=release_id, as_of_event=as_of_event)
        if not run or not parent_projection_object_ids:
            return []
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT * FROM trace_projection_memberships WHERE workspace_id=%s AND projection_run_id=%s AND parent_projection_object_id = ANY(%s::uuid[]) ORDER BY ordinal,projection_membership_id LIMIT %s", (workspace_id, run["projection_run_id"], list(parent_projection_object_ids), max(1, min(int(limit), 1_000))))
                rows = [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]
        for row in rows:
            row["properties"] = self._json_value(row.pop("properties"), {})
        return rows

    def hierarchy_source_atom_ids(self, workspace_id: str, projection_object_ids: Sequence[str], *, limit: int = 512, release_id: str | None = None, as_of_event: int | None = None) -> list[str]:
        if self.delegate is not None and hasattr(self.delegate, "hierarchy_source_atom_ids"):
            try:
                return self.delegate.hierarchy_source_atom_ids(workspace_id, projection_object_ids, limit=limit, release_id=release_id, as_of_event=as_of_event)
            except TypeError:
                return self.delegate.hierarchy_source_atom_ids(workspace_id, projection_object_ids, limit=limit)
        run = self.effective_projection_run(workspace_id, "hierarchy", release_id=release_id, as_of_event=as_of_event)
        if not run or not projection_object_ids:
            return []
        bounded_limit = max(1, min(int(limit), 4_096))
        frontier = list(dict.fromkeys(str(item) for item in projection_object_ids if item))[:bounded_limit]
        seen_objects: set[str] = set()
        source_ids: list[str] = []
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                while frontier and len(source_ids) < bounded_limit:
                    batch = [item for item in frontier if item not in seen_objects][:128]
                    frontier = []
                    if not batch:
                        break
                    seen_objects.update(batch)
                    cursor.execute(
                        """SELECT projection_object_id,source_atom_version_ids
                           FROM trace_projection_objects
                           WHERE workspace_id=%s AND projection_run_id=%s
                             AND projection_object_id = ANY(%s::uuid[])""",
                        (workspace_id, run["projection_run_id"], batch),
                    )
                    for object_id, sources in cursor.fetchall():
                        del object_id
                        for source in self._json_value(sources, []):
                            source_id = str(source)
                            if source_id not in source_ids and len(source_ids) < bounded_limit:
                                source_ids.append(source_id)
                    cursor.execute(
                        """SELECT child_kind,child_id FROM trace_projection_memberships
                           WHERE workspace_id=%s AND projection_run_id=%s
                             AND parent_projection_object_id = ANY(%s::uuid[])
                           ORDER BY ordinal,projection_membership_id""",
                        (workspace_id, run["projection_run_id"], batch),
                    )
                    for child_kind, child_id in cursor.fetchall():
                        identifier = str(child_id)
                        if child_kind == "atom_version":
                            if identifier not in source_ids and len(source_ids) < bounded_limit:
                                source_ids.append(identifier)
                        elif child_kind == "projection_object" and identifier not in seen_objects:
                            frontier.append(identifier)
        return source_ids[:bounded_limit]

    # ---------------------------------------------------- cortex release lifecycle
    @classmethod
    def _pg_cortex_release_row(cls, row: dict[str, Any] | None, components: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("cortex release was not found")
        result = dict(row)
        for key in ("release_id", "parent_release_id"):
            value = result.get(key)
            if value is not None:
                result[key] = str(value)
        for key in ("created_at", "activated_at", "superseded_at", "retired_at"):
            value = result.get(key)
            if hasattr(value, "isoformat"):
                result[key] = value.isoformat()
        result["validation_receipt"] = cls._json_value(result.pop("validation_receipt", {}), {})
        if components is not None:
            result["components"] = components
        return result

    @classmethod
    def _pg_cortex_component_row(cls, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("cortex release component was not found")
        result = dict(row)
        for key in ("release_id", "carried_forward_from_release_id"):
            value = result.get(key)
            if value is not None:
                result[key] = str(value)
        value = result.get("created_at")
        if hasattr(value, "isoformat"):
            result["created_at"] = value.isoformat()
        result["metadata"] = cls._json_value(result.pop("metadata", {}), {})
        return result

    def _create_bootstrap_release_in_pg(self, cursor: Any, workspace_id: str, actor: str = "system") -> str:
        cursor.execute("SELECT release_id FROM trace_cortex_releases WHERE workspace_id=%s AND status='active'", (workspace_id,))
        active_row = cursor.fetchone()
        if active_row:
            return str(active_row[0])
        cursor.execute("SELECT COALESCE(MAX(event_offset), 0) FROM trace_events WHERE stream_id=%s", (f"workspace:{workspace_id}",))
        ev_row = cursor.fetchone()
        watermark = int(ev_row[0]) if ev_row and ev_row[0] else 0
        rel_id = str(uuid.uuid4())
        cursor.execute(
            """INSERT INTO trace_cortex_releases(release_id,workspace_id,parent_release_id,spine_event_watermark,status,policy_revision,policy_snapshot_hash,code_revision,validation_receipt,created_at,activated_at)
               VALUES (%s,%s,NULL,%s,'active','bootstrap-v0','0000000000000000000000000000000000000000000000000000000000000000','bootstrap-v0','{"bootstrap": true}'::jsonb,NOW(),NOW())""",
            (rel_id, workspace_id, watermark),
        )
        for kind in ('hierarchy', 'affinity', 'activation_priors', 'lexical_index', 'dense_index'):
            cursor.execute(
                """INSERT INTO trace_cortex_release_components(release_id,workspace_id,component_kind,component_revision,input_checksum,source_watermark,carried_forward_from_release_id,validation_status,metadata,created_at)
                   VALUES (%s,%s,%s,'bootstrap-v0','0000000000000000000000000000000000000000000000000000000000000000',%s,NULL,'validated','{"bootstrap": true}'::jsonb,NOW())
                   ON CONFLICT DO NOTHING""",
                (rel_id, workspace_id, kind, watermark),
            )
        return rel_id

    def create_cortex_release(
        self,
        *,
        workspace_id: str,
        parent_release_id: str | None = None,
        spine_event_watermark: int | None = None,
        policy_revision: str | None = None,
        policy_snapshot_hash: str | None = None,
        code_revision: str | None = None,
        components: Sequence[dict[str, Any]] | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_cortex_release"):
            return self.delegate.create_cortex_release(workspace_id=workspace_id, parent_release_id=parent_release_id, spine_event_watermark=spine_event_watermark, policy_revision=policy_revision, policy_snapshot_hash=policy_snapshot_hash, code_revision=code_revision, components=components, actor=actor)
        if not workspace_id:
            raise InvariantViolation("cortex release requires a workspace_id")
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                if spine_event_watermark is None:
                    cursor.execute("SELECT COALESCE(MAX(event_offset), 0) FROM trace_events WHERE stream_id=%s", (f"workspace:{workspace_id}",))
                    ev_row = cursor.fetchone()
                    watermark = int(ev_row[0]) if ev_row and ev_row[0] else 0
                else:
                    watermark = int(spine_event_watermark)
                cursor.execute("SELECT * FROM trace_cognitive_policy_versions WHERE workspace_id=%s AND active=true", (workspace_id,))
                pol_row = self._cursor_mapping(cursor, cursor.fetchone())
                eff_policy_rev = policy_revision or (pol_row or {}).get("policy_revision") or "cognitive-policy-v1"
                eff_policy_hash = policy_snapshot_hash or _digest(self._json_value((pol_row or {}).get("policy", {}), {}))
                eff_code_rev = code_revision or os.environ.get("TRACE_CODE_REVISION", "trace-v2-cortex")
                if parent_release_id is None:
                    cursor.execute("SELECT release_id FROM trace_cortex_releases WHERE workspace_id=%s AND status='active'", (workspace_id,))
                    active_row = cursor.fetchone()
                    parent_release_id = str(active_row[0]) if active_row else None
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="cortex.release_planned",
                payload={"release_id": identifier, "workspace_id": workspace_id, "parent_release_id": parent_release_id, "spine_event_watermark": watermark, "policy_revision": eff_policy_rev, "code_revision": eff_code_rev},
                actor=actor,
            )
            comps: list[dict[str, Any]] = []
            default_kinds = ('hierarchy', 'affinity', 'activation_priors', 'lexical_index', 'dense_index')
            comp_map = {item["component_kind"]: item for item in (components or []) if "component_kind" in item}
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    """INSERT INTO trace_cortex_releases(release_id,workspace_id,parent_release_id,spine_event_watermark,status,policy_revision,policy_snapshot_hash,code_revision,validation_receipt,created_at)
                       VALUES (%s,%s,%s,%s,'building',%s,%s,%s,'{}'::jsonb,NOW())""",
                    (identifier, workspace_id, parent_release_id, watermark, eff_policy_rev, eff_policy_hash, eff_code_rev),
                )
                for kind in default_kinds:
                    c = comp_map.get(kind, {})
                    c_rev = c.get("component_revision") or f"{kind}-{watermark}"
                    c_checksum = c.get("input_checksum") or _digest(f"{kind}:{watermark}")
                    c_watermark = int(c.get("source_watermark", watermark))
                    c_carried = c.get("carried_forward_from_release_id")
                    c_status = c.get("validation_status", "pending")
                    c_meta = c.get("metadata", {})
                    cursor.execute(
                        """INSERT INTO trace_cortex_release_components(release_id,workspace_id,component_kind,component_revision,input_checksum,source_watermark,carried_forward_from_release_id,validation_status,metadata,created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,NOW())""",
                        (identifier, workspace_id, kind, c_rev, c_checksum, c_watermark, c_carried, c_status, json.dumps(c_meta)),
                    )
                    comps.append({
                        "release_id": identifier, "workspace_id": workspace_id, "component_kind": kind,
                        "component_revision": c_rev, "input_checksum": c_checksum, "source_watermark": c_watermark,
                        "carried_forward_from_release_id": c_carried, "validation_status": c_status, "metadata": c_meta,
                    })
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s", (identifier,))
                row = self._cursor_mapping(cursor, cursor.fetchone())
                return self._pg_cortex_release_row(row, components=comps)

    def get_cortex_release(self, release_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_cortex_release"):
            return self.delegate.get_cortex_release(release_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s", (release_id,))
                row = self._cursor_mapping(cursor, cursor.fetchone())
                if not row:
                    raise NotFoundError(f"cortex release {release_id} was not found")
                cursor.execute("SELECT * FROM trace_cortex_release_components WHERE release_id=%s ORDER BY component_kind", (release_id,))
                comps = [self._pg_cortex_component_row(self._cursor_mapping(cursor, r)) for r in cursor.fetchall()]
                return self._pg_cortex_release_row(row, components=comps)

    def get_active_cortex_release(self, workspace_id: str) -> dict[str, Any] | None:
        if self.delegate is not None and hasattr(self.delegate, "get_active_cortex_release"):
            return self.delegate.get_active_cortex_release(workspace_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE workspace_id=%s AND status='active' ORDER BY activated_at DESC LIMIT 1", (workspace_id,))
                row = self._cursor_mapping(cursor, cursor.fetchone())
                if not row:
                    return None
                cursor.execute("SELECT * FROM trace_cortex_release_components WHERE release_id=%s ORDER BY component_kind", (row["release_id"],))
                comps = [self._pg_cortex_component_row(self._cursor_mapping(cursor, r)) for r in cursor.fetchall()]
                return self._pg_cortex_release_row(row, components=comps)

    def get_cortex_release_as_of_event(self, workspace_id: str, as_of_event: int) -> dict[str, Any] | None:
        if self.delegate is not None and hasattr(self.delegate, "get_cortex_release_as_of_event"):
            return self.delegate.get_cortex_release_as_of_event(workspace_id, as_of_event)
        if int(as_of_event) < 1:
            raise InvariantViolation("historical release resolution requires a positive event watermark")
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    """SELECT event_type,payload FROM trace_events
                       WHERE workspace_id=%s AND stream_id=%s AND event_offset<=%s
                         AND event_type IN ('cortex.release_activated','cortex.release_rolled_back')
                       ORDER BY event_offset""",
                    (workspace_id, f"workspace:{workspace_id}", int(as_of_event)),
                )
                selected_id: str | None = None
                for event_type, payload in cursor.fetchall():
                    value = payload if isinstance(payload, dict) else json.loads(payload)
                    if event_type == "cortex.release_activated":
                        selected_id = str(value.get("release_id") or "") or selected_id
                    else:
                        selected_id = str(value.get("to_release_id") or "") or selected_id
                if selected_id is None:
                    cursor.execute(
                        """SELECT * FROM trace_cortex_releases
                           WHERE workspace_id=%s AND policy_revision='bootstrap-v0' AND spine_event_watermark<=%s
                           ORDER BY created_at,release_id LIMIT 1""",
                        (workspace_id, int(as_of_event)),
                    )
                else:
                    cursor.execute("SELECT * FROM trace_cortex_releases WHERE workspace_id=%s AND release_id=%s", (workspace_id, selected_id))
                row = self._cursor_mapping(cursor, cursor.fetchone())
                if not row or int(row["spine_event_watermark"]) > int(as_of_event):
                    return None
                cursor.execute("SELECT * FROM trace_cortex_release_components WHERE release_id=%s ORDER BY component_kind", (row["release_id"],))
                component_rows = [self._cursor_mapping(cursor, item) or {} for item in cursor.fetchall()]
                if len(component_rows) != 5 or any(int(item["source_watermark"]) > int(as_of_event) for item in component_rows):
                    return None
                return self._pg_cortex_release_row(row, components=[self._pg_cortex_component_row(item) for item in component_rows])

    def list_cortex_releases(self, workspace_id: str, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "list_cortex_releases"):
            return self.delegate.list_cortex_releases(workspace_id, status=status, limit=limit)
        clauses = ["workspace_id=%s"]
        values: list[Any] = [workspace_id]
        if status:
            clauses.append("status=%s")
            values.append(status)
        values.append(max(1, min(int(limit), 200)))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(f"SELECT * FROM trace_cortex_releases WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT %s", values)
                rows = [self._cursor_mapping(cursor, r) for r in cursor.fetchall()]
                results: list[dict[str, Any]] = []
                for row in rows:
                    cursor.execute("SELECT * FROM trace_cortex_release_components WHERE release_id=%s ORDER BY component_kind", (row["release_id"],))
                    comps = [self._pg_cortex_component_row(self._cursor_mapping(cursor, cr)) for cr in cursor.fetchall()]
                    results.append(self._pg_cortex_release_row(row, components=comps))
                return results

    def cortex_component_revisions(
        self,
        workspace_id: str,
        component_kinds: Sequence[str],
    ) -> dict[str, list[str]]:
        """List every immutable external component revision known to a workspace."""

        if self.delegate is not None and hasattr(self.delegate, "cortex_component_revisions"):
            return self.delegate.cortex_component_revisions(workspace_id, component_kinds)
        kinds = list(dict.fromkeys(str(kind) for kind in component_kinds if kind))
        result = {kind: [] for kind in kinds}
        if not kinds:
            return result
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    """SELECT component_kind,component_revision
                         FROM trace_cortex_release_components
                        WHERE workspace_id=%s AND component_kind=ANY(%s)
                        GROUP BY component_kind,component_revision
                        ORDER BY component_kind,component_revision""",
                    (workspace_id, kinds),
                )
                for kind, revision in cursor.fetchall():
                    result[str(kind)].append(str(revision))
        return result

    def record_cortex_component(self, release_id: str, *, component_kind: str, component_revision: str, input_checksum: str, source_watermark: int, carried_forward_from_release_id: str | None = None, validation_status: str = "pending", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "record_cortex_component"):
            return self.delegate.record_cortex_component(release_id, component_kind=component_kind, component_revision=component_revision, input_checksum=input_checksum, source_watermark=source_watermark, carried_forward_from_release_id=carried_forward_from_release_id, validation_status=validation_status, metadata=metadata)
        if component_kind not in {'hierarchy', 'affinity', 'activation_priors', 'lexical_index', 'dense_index'}:
            raise InvariantViolation(f"invalid cortex component kind: {component_kind}")
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT workspace_id, status FROM trace_cortex_releases WHERE release_id=%s FOR UPDATE", (release_id,))
                rel = self._cursor_mapping(cursor, cursor.fetchone())
                if not rel:
                    raise NotFoundError(f"cortex release {release_id} was not found")
                if rel["status"] not in {"planned", "building", "validating"}:
                    raise InvariantViolation(f"cannot update component on release in status {rel['status']}")
                cursor.execute(
                    """INSERT INTO trace_cortex_release_components(release_id,workspace_id,component_kind,component_revision,input_checksum,source_watermark,carried_forward_from_release_id,validation_status,metadata,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,NOW())
                       ON CONFLICT(release_id,component_kind) DO UPDATE SET
                         component_revision=EXCLUDED.component_revision,
                         input_checksum=EXCLUDED.input_checksum,
                         source_watermark=EXCLUDED.source_watermark,
                         carried_forward_from_release_id=EXCLUDED.carried_forward_from_release_id,
                         validation_status=EXCLUDED.validation_status,
                         metadata=EXCLUDED.metadata""",
                    (release_id, rel["workspace_id"], component_kind, component_revision, input_checksum, int(source_watermark), carried_forward_from_release_id, validation_status, json.dumps(metadata or {})),
                )
                cursor.execute("SELECT * FROM trace_cortex_release_components WHERE release_id=%s AND component_kind=%s", (release_id, component_kind))
                return self._pg_cortex_component_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def validate_cortex_release(self, release_id: str, validation_receipt: dict[str, Any], *, actor: str = "validation-worker") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "validate_cortex_release"):
            return self.delegate.validate_cortex_release(release_id, validation_receipt, actor=actor)
        passed = bool(validation_receipt.get("passed", True))
        new_status = "validated" if passed else "failed"
        failure_detail = validation_receipt.get("failure_detail") if not passed else None
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s FOR UPDATE", (release_id,))
                rel = self._cursor_mapping(cursor, cursor.fetchone())
                if not rel:
                    raise NotFoundError(f"cortex release {release_id} was not found")
                if rel["status"] not in {"planned", "building", "validating"}:
                    raise InvariantViolation(f"cortex release in status {rel['status']} cannot be validated")
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{rel['workspace_id']}", event_type=f"cortex.release_{new_status}",
                payload={"release_id": str(release_id), "workspace_id": rel["workspace_id"], "validation_receipt": validation_receipt, "status": new_status},
                actor=actor,
            )
            with conn.cursor() as cursor:
                self._set_workspace(cursor, rel["workspace_id"])
                cursor.execute("UPDATE trace_cortex_releases SET status=%s,validation_receipt=%s::jsonb,failure_detail=%s WHERE release_id=%s", (new_status, json.dumps(validation_receipt), failure_detail, release_id))
                if passed:
                    cursor.execute("UPDATE trace_cortex_release_components SET validation_status='validated' WHERE release_id=%s", (release_id,))
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s", (release_id,))
                row = self._cursor_mapping(cursor, cursor.fetchone())
                cursor.execute("SELECT * FROM trace_cortex_release_components WHERE release_id=%s ORDER BY component_kind", (release_id,))
                comps = [self._pg_cortex_component_row(self._cursor_mapping(cursor, r)) for r in cursor.fetchall()]
                return self._pg_cortex_release_row(row, components=comps)

    def activate_cortex_release(self, release_id: str, *, actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "activate_cortex_release"):
            return self.delegate.activate_cortex_release(release_id, actor=actor)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s FOR UPDATE", (release_id,))
                rel = self._cursor_mapping(cursor, cursor.fetchone())
                if not rel:
                    raise NotFoundError(f"cortex release {release_id} was not found")
                if rel["status"] != "validated":
                    raise InvariantViolation(f"cannot activate cortex release in status {rel['status']!r}; must be 'validated'")
                ws = rel["workspace_id"]
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{ws}", event_type="cortex.release_activated",
                payload={"release_id": str(release_id), "workspace_id": ws, "spine_event_watermark": rel["spine_event_watermark"], "policy_revision": rel["policy_revision"], "code_revision": rel["code_revision"]},
                actor=actor,
            )
            with conn.cursor() as cursor:
                self._set_workspace(cursor, ws)
                cursor.execute("UPDATE trace_cortex_releases SET status='superseded',superseded_at=NOW(),superseded_event_offset=%s WHERE workspace_id=%s AND status='active' AND release_id<>%s", (event.offset, ws, release_id))
                cursor.execute("UPDATE trace_cortex_releases SET status='active',activated_at=NOW(),activated_event_offset=%s,superseded_at=NULL WHERE release_id=%s", (event.offset, release_id))
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s", (release_id,))
                row = self._cursor_mapping(cursor, cursor.fetchone())
                cursor.execute("SELECT * FROM trace_cortex_release_components WHERE release_id=%s ORDER BY component_kind", (release_id,))
                comps = [self._pg_cortex_component_row(self._cursor_mapping(cursor, r)) for r in cursor.fetchall()]
                return self._pg_cortex_release_row(row, components=comps)

    def rollback_cortex_release(self, workspace_id: str, *, target_release_id: str | None = None, reason: str | None = None, actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "rollback_cortex_release"):
            return self.delegate.rollback_cortex_release(workspace_id, target_release_id=target_release_id, reason=reason, actor=actor)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE workspace_id=%s AND status='active' FOR UPDATE", (workspace_id,))
                current_active = self._cursor_mapping(cursor, cursor.fetchone())
                if not current_active:
                    raise InvariantViolation("cannot rollback: workspace has no active cortex release")
                target_row = None
                if target_release_id is not None:
                    cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s AND workspace_id=%s FOR UPDATE", (target_release_id, workspace_id))
                    target_row = self._cursor_mapping(cursor, cursor.fetchone())
                    if not target_row:
                        raise NotFoundError(f"target rollback release {target_release_id} was not found")
                    if target_row["status"] not in {"superseded", "validated"}:
                        raise InvariantViolation(f"cannot rollback to release with status {target_row['status']!r}")
                else:
                    if current_active.get("parent_release_id"):
                        cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s FOR UPDATE", (current_active["parent_release_id"],))
                        target_row = self._cursor_mapping(cursor, cursor.fetchone())
                    if not target_row:
                        cursor.execute("SELECT * FROM trace_cortex_releases WHERE workspace_id=%s AND status='superseded' ORDER BY activated_at DESC, created_at DESC LIMIT 1 FOR UPDATE", (workspace_id,))
                        target_row = self._cursor_mapping(cursor, cursor.fetchone())
                    if not target_row:
                        raise InvariantViolation("cannot rollback: no validated predecessor release available")
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="cortex.release_rolled_back",
                payload={"workspace_id": workspace_id, "from_release_id": str(current_active["release_id"]), "to_release_id": str(target_row["release_id"]), "reason": reason},
                actor=actor,
            )

            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("UPDATE trace_cortex_releases SET status='superseded',superseded_at=NOW(),superseded_event_offset=%s WHERE release_id=%s", (event.offset, current_active["release_id"]))
                cursor.execute("UPDATE trace_cortex_releases SET status='active',activated_at=NOW(),activated_event_offset=%s,superseded_at=NULL WHERE release_id=%s", (event.offset, target_row["release_id"]))
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s", (target_row["release_id"],))
                row = self._cursor_mapping(cursor, cursor.fetchone())
                cursor.execute("SELECT * FROM trace_cortex_release_components WHERE release_id=%s ORDER BY component_kind", (target_row["release_id"],))
                comps = [self._pg_cortex_component_row(self._cursor_mapping(cursor, r)) for r in cursor.fetchall()]
                return self._pg_cortex_release_row(row, components=comps)

    def fail_cortex_release(self, release_id: str, failure_detail: str, *, actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "fail_cortex_release"):
            return self.delegate.fail_cortex_release(release_id, failure_detail, actor=actor)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor)
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s FOR UPDATE", (release_id,))
                rel = self._cursor_mapping(cursor, cursor.fetchone())
                if not rel:
                    raise NotFoundError(f"cortex release {release_id} was not found")
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{rel['workspace_id']}", event_type="cortex.release_failed",
                payload={"release_id": str(release_id), "workspace_id": rel["workspace_id"], "failure_detail": failure_detail},
                actor=actor,
            )

            with conn.cursor() as cursor:
                self._set_workspace(cursor, rel["workspace_id"])
                cursor.execute("UPDATE trace_cortex_releases SET status='failed',failure_detail=%s WHERE release_id=%s", (failure_detail, release_id))
                cursor.execute("SELECT * FROM trace_cortex_releases WHERE release_id=%s", (release_id,))
                row = self._cursor_mapping(cursor, cursor.fetchone())
                cursor.execute("SELECT * FROM trace_cortex_release_components WHERE release_id=%s ORDER BY component_kind", (release_id,))
                comps = [self._pg_cortex_component_row(self._cursor_mapping(cursor, r)) for r in cursor.fetchall()]
                return self._pg_cortex_release_row(row, components=comps)

    def affinity_neighbors(self, workspace_id: str, atom_version_ids: Sequence[str], *, release_id: str | None = None, limit: int = 64, index_revision: str | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "affinity_neighbors"):
            return self.delegate.affinity_neighbors(workspace_id, atom_version_ids, release_id=release_id, limit=limit, index_revision=index_revision)
        if not atom_version_ids:
            return []
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                eff_release_id = release_id
                if eff_release_id is None:
                    cursor.execute("SELECT release_id FROM trace_cortex_releases WHERE workspace_id=%s AND status='active'", (workspace_id,))
                    active = cursor.fetchone()
                    if not active:
                        return []
                    eff_release_id = str(active[0])
                clauses = ["workspace_id=%s", "release_id=%s", "status='active'", "expires_at>NOW()", "(left_atom_version_id = ANY(%s::uuid[]) OR right_atom_version_id = ANY(%s::uuid[]))"]
                values: list[Any] = [workspace_id, eff_release_id, list(atom_version_ids), list(atom_version_ids)]
                if index_revision:
                    clauses.append("(index_revision IS NULL OR index_revision=%s)")
                    values.append(index_revision)
                values.append(max(1, min(int(limit), 256)))
                cursor.execute(f"SELECT * FROM trace_affinity_edges WHERE {' AND '.join(clauses)} ORDER BY score DESC,pair_key LIMIT %s", values)
                rows = [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]
        for row in rows:
            row["signal"] = self._json_value(row.pop("signal"), {})
        return rows

    def put_affinity_edge(self, *, workspace_id: str, source_atom_version_id: str, target_atom_version_id: str, score: float, signal: dict[str, Any], expires_at: str, release_id: str | None = None, index_revision: str | None = None, embedding_revision: str | None = None, projection_run_id: str | None = None, degree_cap: int = 16, actor: str = "affinity-worker") -> dict[str, Any] | None:
        if self.delegate is not None and hasattr(self.delegate, "put_affinity_edge"):
            return self.delegate.put_affinity_edge(workspace_id=workspace_id, source_atom_version_id=source_atom_version_id, target_atom_version_id=target_atom_version_id, score=score, signal=signal, expires_at=expires_at, release_id=release_id, index_revision=index_revision, embedding_revision=embedding_revision, projection_run_id=projection_run_id, degree_cap=degree_cap, actor=actor)
        left, right = canonical_pair(source_atom_version_id, target_atom_version_id)
        if not 0 <= float(score) <= 1:
            raise InvariantViolation("affinity score must be between zero and one")
        pair_key = f"{left}:{right}"
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute(
                    """SELECT COUNT(*) FROM trace_node_versions nv
                       JOIN trace_nodes n ON n.node_id=nv.node_id
                       WHERE n.workspace_id=%s AND nv.atom_version_id = ANY(%s::uuid[])""",
                    (workspace_id, [left, right]),
                )
                if int(cursor.fetchone()[0]) != 2:
                    raise InvariantViolation("affinity endpoints are absent or out of scope")
                eff_release_id = release_id or self._create_bootstrap_release_in_pg(cursor, workspace_id, actor=actor)
                cursor.execute("SELECT 1 FROM trace_affinity_rejections WHERE workspace_id=%s AND pair_key=%s AND (expires_at IS NULL OR expires_at>NOW())", (workspace_id, pair_key))
                if cursor.fetchone():
                    return None
                cursor.execute("SELECT affinity_edge_id FROM trace_affinity_edges WHERE workspace_id=%s AND release_id=%s AND pair_key=%s", (workspace_id, eff_release_id, pair_key))
                existing = cursor.fetchone()
                if existing is None:
                    cap = max(1, int(degree_cap))
                    cursor.execute(
                        """SELECT COUNT(*) FROM trace_affinity_edges
                           WHERE workspace_id=%s AND release_id=%s AND status='active' AND expires_at>NOW()
                             AND (left_atom_version_id=%s OR right_atom_version_id=%s)""",
                        (workspace_id, eff_release_id, left, left),
                    )
                    left_degree = int(cursor.fetchone()[0])
                    cursor.execute(
                        """SELECT COUNT(*) FROM trace_affinity_edges
                           WHERE workspace_id=%s AND release_id=%s AND status='active' AND expires_at>NOW()
                             AND (left_atom_version_id=%s OR right_atom_version_id=%s)""",
                        (workspace_id, eff_release_id, right, right),
                    )
                    right_degree = int(cursor.fetchone()[0])
                    if left_degree >= cap or right_degree >= cap:
                        return None
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="affinity.edge_upserted", payload={"workspace_id": str(workspace_id), "release_id": str(eff_release_id), "left_atom_version_id": str(left), "right_atom_version_id": str(right), "score": float(score), "projection_run_id": str(projection_run_id) if projection_run_id is not None else None}, actor=actor)
            identifier = str(existing[0]) if existing else str(uuid.uuid4())
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("""INSERT INTO trace_affinity_edges(affinity_edge_id,workspace_id,release_id,left_atom_version_id,right_atom_version_id,pair_key,score,signal,index_revision,embedding_revision,projection_run_id,status,expires_at,created_event_offset,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,'active',%s,%s,NOW())
                    ON CONFLICT(workspace_id,release_id,pair_key) DO UPDATE SET score=EXCLUDED.score,signal=EXCLUDED.signal,index_revision=EXCLUDED.index_revision,embedding_revision=EXCLUDED.embedding_revision,projection_run_id=EXCLUDED.projection_run_id,status='active',expires_at=EXCLUDED.expires_at,created_event_offset=EXCLUDED.created_event_offset,updated_at=NOW()""", (identifier, workspace_id, eff_release_id, left, right, pair_key, float(score), json.dumps(signal), index_revision, embedding_revision, projection_run_id, expires_at, event.offset))
                cursor.execute("SELECT * FROM trace_affinity_edges WHERE workspace_id=%s AND release_id=%s AND pair_key=%s", (workspace_id, eff_release_id, pair_key))
                row = self._cursor_mapping(cursor, cursor.fetchone()) or {}
        row["signal"] = self._json_value(row.pop("signal"), {})
        return row

    def reject_affinity(self, *, workspace_id: str, source_atom_version_id: str, target_atom_version_id: str, reason: str | None = None, expires_at: str | None = None, actor: str = "anonymous") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "reject_affinity"):
            return self.delegate.reject_affinity(workspace_id=workspace_id, source_atom_version_id=source_atom_version_id, target_atom_version_id=target_atom_version_id, reason=reason, expires_at=expires_at, actor=actor)
        left, right = canonical_pair(source_atom_version_id, target_atom_version_id)
        pair_key = f"{left}:{right}"
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="affinity.rejected", payload={"workspace_id": workspace_id, "left_atom_version_id": left, "right_atom_version_id": right, "reason": reason}, actor=actor)
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("""INSERT INTO trace_affinity_rejections(affinity_rejection_id,workspace_id,pair_key,left_atom_version_id,right_atom_version_id,reason,actor,expires_at,created_event_offset,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                    ON CONFLICT(workspace_id,pair_key) DO UPDATE SET reason=EXCLUDED.reason,actor=EXCLUDED.actor,expires_at=EXCLUDED.expires_at,created_event_offset=EXCLUDED.created_event_offset,created_at=NOW()""", (identifier, workspace_id, pair_key, left, right, reason, actor, expires_at, event.offset))
                cursor.execute("UPDATE trace_affinity_edges SET status='rejected',updated_at=NOW() WHERE workspace_id=%s AND pair_key=%s", (workspace_id, pair_key))
                cursor.execute("SELECT * FROM trace_affinity_rejections WHERE workspace_id=%s AND pair_key=%s", (workspace_id, pair_key))
                result = self._cursor_mapping(cursor, cursor.fetchone()) or {}
        result["rejection_event_offset"] = event.offset
        return result

    def invalidate_affinity_for_atoms(self, *, workspace_id: str, atom_version_ids: Sequence[str], reason: str, actor: str = "projection-worker") -> int:
        if self.delegate is not None and hasattr(self.delegate, "invalidate_affinity_for_atoms"):
            return self.delegate.invalidate_affinity_for_atoms(workspace_id=workspace_id, atom_version_ids=atom_version_ids, reason=reason, actor=actor)
        if not atom_version_ids:
            return 0
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="affinity.invalidated", payload={"workspace_id": workspace_id, "atom_version_ids": list(atom_version_ids), "reason": reason}, actor=actor)
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("UPDATE trace_affinity_edges SET status='stale',updated_at=NOW() WHERE workspace_id=%s AND status='active' AND (left_atom_version_id = ANY(%s::uuid[]) OR right_atom_version_id = ANY(%s::uuid[]))", (workspace_id, list(atom_version_ids), list(atom_version_ids)))
                return int(cursor.rowcount)

    def upsert_activation_prior(self, *, workspace_id: str, atom_version_id: str, prior_kind: str, score: float, release_id: str | None = None, provenance: dict[str, Any] | None = None, expires_at: str | None = None, actor: str = "activation-worker") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "upsert_activation_prior"):
            return self.delegate.upsert_activation_prior(workspace_id=workspace_id, atom_version_id=atom_version_id, prior_kind=prior_kind, score=score, release_id=release_id, provenance=provenance, expires_at=expires_at, actor=actor)
        if prior_kind not in {"pin", "recency", "feedback", "suppression", "co_retrieval"} or not -1 <= float(score) <= 1:
            raise InvariantViolation("invalid activation prior")
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                eff_release_id = release_id or self._create_bootstrap_release_in_pg(cursor, workspace_id, actor=actor)
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="activation.prior_upserted", payload={"workspace_id": workspace_id, "release_id": eff_release_id, "atom_version_id": atom_version_id, "prior_kind": prior_kind, "score": float(score)}, actor=actor)
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                cursor.execute("""INSERT INTO trace_activation_priors(activation_prior_id,workspace_id,release_id,atom_version_id,prior_kind,score,provenance,expires_at,created_event_offset,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,NOW())
                    ON CONFLICT(workspace_id,release_id,atom_version_id,prior_kind) DO UPDATE SET score=EXCLUDED.score,provenance=EXCLUDED.provenance,expires_at=EXCLUDED.expires_at,created_event_offset=EXCLUDED.created_event_offset,updated_at=NOW()""", (identifier, workspace_id, eff_release_id, atom_version_id, prior_kind, float(score), json.dumps(provenance or {}), expires_at, event.offset))
                cursor.execute("SELECT * FROM trace_activation_priors WHERE workspace_id=%s AND release_id=%s AND atom_version_id=%s AND prior_kind=%s", (workspace_id, eff_release_id, atom_version_id, prior_kind))
                result = self._cursor_mapping(cursor, cursor.fetchone()) or {}
        result["provenance"] = self._json_value(result.pop("provenance", {}), {})
        return result

    def activation_priors(self, workspace_id: str, atom_version_ids: Sequence[str], *, release_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
        if self.delegate is not None and hasattr(self.delegate, "activation_priors"):
            return self.delegate.activation_priors(workspace_id, atom_version_ids, release_id=release_id)
        if not atom_version_ids:
            return {}
        with self.connection() as conn:
            with conn.cursor() as cursor:
                self._set_workspace(cursor, workspace_id)
                eff_release_id = release_id
                if eff_release_id is None:
                    cursor.execute("SELECT release_id FROM trace_cortex_releases WHERE workspace_id=%s AND status='active'", (workspace_id,))
                    active = cursor.fetchone()
                    if not active:
                        return {}
                    eff_release_id = str(active[0])
                cursor.execute("SELECT * FROM trace_activation_priors WHERE workspace_id=%s AND release_id=%s AND atom_version_id = ANY(%s::uuid[]) AND (expires_at IS NULL OR expires_at>NOW()) ORDER BY prior_kind", (workspace_id, eff_release_id, list(atom_version_ids)))
                rows = [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            row["provenance"] = self._json_value(row.pop("provenance", {}), {})
            result.setdefault(str(row["atom_version_id"]), []).append(row)
        return result

    def clear_cortex_projections(self, workspace_id: str, *, actor: str = "projection-recovery") -> dict[str, int]:
        """Delete only rebuildable Cortex rows for one tenant revision reset."""

        if self.delegate is not None and hasattr(self.delegate, "clear_cortex_projections"):
            return self.delegate.clear_cortex_projections(workspace_id, actor=actor)
        if not workspace_id:
            raise InvariantViolation("PostgreSQL Cortex recovery requires one workspace")
        with self.authorization_scope(workspace_id):
            with self.connection() as conn:
                with conn.cursor() as cursor:
                    self._set_workspace(cursor, workspace_id)
                    cursor.execute("SELECT projection_run_id FROM trace_projection_runs WHERE workspace_id=%s", (workspace_id,))
                    run_ids = [str(row[0]) for row in cursor.fetchall()]
                    if run_ids:
                        cursor.execute("DELETE FROM trace_projection_memberships WHERE workspace_id=%s AND projection_run_id = ANY(%s::uuid[])", (workspace_id, run_ids))
                        memberships = int(cursor.rowcount)
                        cursor.execute("DELETE FROM trace_projection_objects WHERE workspace_id=%s AND projection_run_id = ANY(%s::uuid[])", (workspace_id, run_ids))
                        objects = int(cursor.rowcount)
                    else:
                        memberships = objects = 0
                    cursor.execute("DELETE FROM trace_affinity_edges WHERE workspace_id=%s", (workspace_id,))
                    affinities = int(cursor.rowcount)
                    cursor.execute("DELETE FROM trace_activation_priors WHERE workspace_id=%s", (workspace_id,))
                    priors = int(cursor.rowcount)
                    cursor.execute("DELETE FROM trace_projection_runs WHERE workspace_id=%s", (workspace_id,))
                    runs = int(cursor.rowcount)
                self._append_event_in_connection(
                    conn,
                    stream_id=f"workspace:{workspace_id}",
                    event_type="projection.cortex_cleared",
                    payload={
                        "workspace_id": workspace_id, "runs": runs, "objects": objects,
                        "memberships": memberships, "affinities": affinities, "priors": priors,
                    },
                    actor=actor,
                )
        return {"runs": runs, "objects": objects, "memberships": memberships, "affinities": affinities, "priors": priors}


class S3ObjectStore:
    """Private, content-addressed S3-compatible attachment storage.

    Canonical records retain only the returned object metadata and digest.  The
    object body never enters the event payload.  Server-side encryption is
    requested on every write; deployments may additionally encrypt client-side
    before calling this adapter.
    """

    def __init__(
        self,
        bucket: str,
        *,
        client: Any | None = None,
        prefix: str = "trace/attachments",
        kms_key_id: str | None = None,
        endpoint_url: str | None = None,
        server_side_encryption: str | None = "AES256",
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.kms_key_id = kms_key_id or os.environ.get("TRACE_OBJECT_KMS_KEY_ID")
        self.server_side_encryption = server_side_encryption
        if client is None:
            try:
                import boto3
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("boto3 is required for S3ObjectStore") from error
            client = boto3.client("s3", endpoint_url=endpoint_url or os.environ.get("TRACE_S3_ENDPOINT"))
        self.client = client

    def _put(self, raw: bytes, media_type: str, *, workspace_id: str | None = None) -> dict[str, Any]:
        digest = hashlib.sha256(raw).hexdigest()
        safe_workspace = re.sub(r"[^A-Za-z0-9_.-]", "_", workspace_id or "unassigned")
        tenant_prefix = f"workspace/{safe_workspace}/"
        key = f"{self.prefix}/{tenant_prefix}{digest}"
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": raw,
            "ContentType": media_type,
            "Metadata": {"sha256": digest, "tenant": workspace_id or "unassigned"},
        }
        if self.server_side_encryption:
            kwargs["ServerSideEncryption"] = "aws:kms" if self.kms_key_id else self.server_side_encryption
            if self.kms_key_id:
                kwargs["SSEKMSKeyId"] = self.kms_key_id
        self.client.put_object(**kwargs)
        return {
            "content_hash": digest,
            "object_key": key,
            "media_type": media_type,
            "byte_length": len(raw),
            "metadata": {"storage": "s3", "bucket": self.bucket, "encrypted": bool(self.server_side_encryption)},
        }


    def put_bytes(self, raw: bytes, media_type: str, *, workspace_id: str | None = None, **_: Any) -> dict[str, Any]:
        return self._put(raw, media_type, workspace_id=workspace_id)

    def put_text(self, text: str, media_type: str, *, workspace_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return self.put_bytes(text.encode("utf-8"), media_type, workspace_id=workspace_id, **kwargs)

    def presign_get(self, object_key: str, *, expires_seconds: int = 300) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": object_key}, ExpiresIn=max(1, min(expires_seconds, 86_400))
        )

    def get_bytes(self, object_key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
            return response["Body"].read()
        except Exception as error:
            raise NotFoundError(f"object {object_key} was not found in bucket {self.bucket}") from error

    def delete_object(self, object_key: str) -> dict[str, Any]:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
            return {"deleted": True, "object_key": object_key, "bucket": self.bucket}
        except Exception as error:
            raise ProductionAdapterError(f"failed to delete object {object_key} from bucket {self.bucket}") from error

    def verify_object_absent(self, object_key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=object_key)
            return False
        except Exception as error:
            status_code = 0
            err_code = ""
            if hasattr(error, "response"):
                resp = getattr(error, "response", {})
                status_code = resp.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
                err_code = resp.get("Error", {}).get("Code", "")
            err_str = str(error).lower()
            if status_code == 404 or err_code in ("404", "NoSuchKey", "NotFound") or "not found" in err_str or "404" in err_str:
                return True
            raise ProductionAdapterError(f"failed to verify absence of object {object_key}: {error}") from error


class GcsObjectStore:
    """Private GCS attachment store for the Mumbai profile.

    The Terraform profile configures bucket-level CMEK and versioning.  This
    adapter intentionally uses application-default credentials only; callers
    cannot choose a bucket, project, service account, or public URL.
    """

    def __init__(self, bucket: str, *, client: Any | None = None, prefix: str = "trace") -> None:
        if not bucket:
            raise ValueError("TRACE_GCS_BUCKET is required for GCS object storage")
        self.bucket_name = bucket
        self.prefix = prefix.strip("/")
        if client is None:
            try:
                from google.cloud import storage
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("google-cloud-storage is required for GcsObjectStore") from error
            client = storage.Client()
        self.client = client

    def _put(self, raw: bytes, media_type: str, *, workspace_id: str | None) -> dict[str, Any]:
        digest = hashlib.sha256(raw).hexdigest()
        safe_workspace = re.sub(r"[^A-Za-z0-9_.-]", "_", workspace_id or "unassigned")
        object_key = f"{self.prefix}/workspace/{safe_workspace}/{digest[:2]}/{digest}"
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(object_key)
        blob.metadata = {"sha256": digest, "tenant": workspace_id or "unassigned"}
        blob.upload_from_string(raw, content_type=media_type)
        return {
            "content_hash": digest,
            "object_key": object_key,
            "media_type": media_type,
            "byte_length": len(raw),
            "metadata": {"storage": "gcs", "bucket": self.bucket_name, "encrypted": True},
        }

    def put_bytes(self, raw: bytes, media_type: str, *, workspace_id: str | None = None, **_: Any) -> dict[str, Any]:
        return self._put(raw, media_type, workspace_id=workspace_id)

    def put_text(self, text: str, media_type: str, *, workspace_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return self.put_bytes(text.encode("utf-8"), media_type, workspace_id=workspace_id, **kwargs)

    def signed_get_url(self, object_key: str, *, expires_seconds: int = 300) -> str:
        bucket = self.client.bucket(self.bucket_name)
        return bucket.blob(object_key).generate_signed_url(expiration=max(1, min(expires_seconds, 86_400)), method="GET")

    def get_bytes(self, object_key: str) -> bytes:
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(object_key)
        if not blob.exists():
            raise NotFoundError(f"object {object_key} was not found in bucket {self.bucket_name}")
        return blob.download_as_bytes()

    def delete_object(self, object_key: str) -> dict[str, Any]:
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(object_key)
        if blob.exists():
            blob.delete()
            return {"deleted": True, "object_key": object_key, "bucket": self.bucket_name}
        return {"deleted": False, "object_key": object_key, "status": "already_deleted"}

    def verify_object_absent(self, object_key: str) -> bool:
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(object_key)
            return not blob.exists()
        except Exception as error:
            raise ProductionAdapterError(f"failed to verify absence of object {object_key}: {error}") from error



class OpenSearchLexicalIndex:
    """BM25/OpenSearch adapter with mandatory tenant and visibility filters."""

    provider_id = "opensearch-bm25-v1"

    def __init__(self, index: str, *, client: Any | None = None, hosts: Sequence[str] | None = None) -> None:
        self.index = index
        if client is None:
            try:
                from opensearchpy import OpenSearch
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("opensearch-py is required for OpenSearchLexicalIndex") from error
            client = OpenSearch(list(hosts or [os.environ.get("TRACE_OPENSEARCH_URL", "http://localhost:9200")]))
        self.client = client

    @staticmethod
    def _revision_token(revision: str) -> str:
        token = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(revision)).strip("-_").lower()
        if not token:
            raise ValueError("index revision must contain a letter or digit")
        return token[:96]

    @classmethod
    def _logical_revision(cls, revision: str) -> str:
        value = str(revision)
        if "--rev-" in value:
            raise ValueError("OpenSearch revision must be a logical component revision, not a physical index name")
        cls._revision_token(value)
        return value

    def revision_index(self, revision: str) -> str:
        """Return the immutable physical index behind a logical revision."""

        logical = self._logical_revision(revision)
        return f"{self.index}--rev-{self._revision_token(logical)}"

    def create_revision(self, revision: str, *, vector_size: int | None = None) -> str:
        """Create a physical, immutable OpenSearch revision if absent."""

        target = self.revision_index(revision)
        indexes = getattr(self.client, "indices", None)
        if indexes is None:
            return target
        try:
            exists = bool(indexes.exists(index=target))
        except Exception:
            exists = False
        if not exists:
            body = {
                "settings": {"index": {
                    "number_of_shards": int(os.environ.get("TRACE_OPENSEARCH_SHARDS", "3")),
                    "number_of_replicas": int(os.environ.get("TRACE_OPENSEARCH_REPLICAS", "1")),
                }},
                "mappings": {"dynamic": "strict", "properties": {
                    "atom_version_id": {"type": "keyword"},
                    "workspace_id": {"type": "keyword"},
                    "content": {"type": "text"},
                    "title": {"type": "text"},
                    "visibility": {"type": "keyword"},
                    "facets": {"type": "keyword"},
                    "created_event_offset": {"type": "long"},
                    "index_revision": {"type": "keyword"},
                    "content_hash": {"type": "keyword"},
                    # SourceInput permits adapter provenance extensions. Keep
                    # the enclosing index strict while explicitly accepting
                    # the stable source fields and retaining opaque metadata
                    # without dynamically mapping arbitrary user keys.
                    "source": {
                        "type": "object",
                        "dynamic": False,
                        "properties": {
                            "title": {"type": "text"},
                            "uri": {"type": "keyword", "ignore_above": 2048},
                            "media_type": {"type": "keyword"},
                            "adapter": {"type": "keyword"},
                            "metadata": {"type": "object", "enabled": False},
                        },
                    },
                    "source_start": {"type": "integer"},
                    "source_end": {"type": "integer"},
                    "parser_location": {"type": "keyword", "ignore_above": 2048},
                    "attachment_id": {"type": "keyword"},
                }},
            }
            try:
                indexes.create(index=target, body=body)
            except Exception as error:
                # Concurrent maintenance workers may race index creation. Only
                # accept the failure if the exact physical target now exists.
                if not indexes.exists(index=target):
                    raise error
        return target

    @staticmethod
    def _filters(workspace_id: str, visibility: Sequence[str] | None, facets: Sequence[str] | None, as_of_event: int | None, index_revision: str | None = None) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = [{"term": {"workspace_id": workspace_id}}]
        if visibility:
            filters.append({"terms": {"visibility": list(visibility)}})
        if facets:
            filters.extend({"term": {"facets": facet}} for facet in facets)
        if as_of_event is not None:
            filters.append({"range": {"created_event_offset": {"lte": as_of_event}}})
        if index_revision is not None:
            filters.append({"term": {"index_revision": index_revision}})
        return filters

    def search(self, *, workspace_id: str, query: str, limit: int, visibility: Sequence[str] | None = None, facets: Sequence[str] | None = None, as_of_event: int | None = None, index_revision: str | None = None) -> list[dict[str, Any]]:
        body = {
            "size": max(1, min(limit, 1_000)),
            "query": {"bool": {"must": [{"multi_match": {"query": query, "fields": ["content^2", "title", "source.uri"]}}], "filter": self._filters(workspace_id, visibility, facets, as_of_event, index_revision)}},
            "_source": True,
        }
        target = self.revision_index(index_revision) if index_revision else self.index
        response = self.client.search(index=target, body=body)
        hits = response.get("hits", {}).get("hits", [])
        return [{**hit.get("_source", {}), "atom_version_id": hit.get("_id"), "lexical_score": float(hit.get("_score") or 0.0)} for hit in hits]

    def upsert(self, documents: Iterable[dict[str, Any]], *, revision: str) -> int:
        """Idempotently bulk-index one bounded delta into its revision target."""

        target = self.create_revision(revision)
        batch_size = max(1, min(int(os.environ.get("TRACE_OPENSEARCH_BULK_SIZE", "500")), 2_000))
        batch: list[tuple[str, dict[str, Any]]] = []
        indexed = 0

        def flush(rows: list[tuple[str, dict[str, Any]]]) -> int:
            if not rows:
                return 0
            bulk = getattr(self.client, "bulk", None)
            if not callable(bulk):
                for atom_id, payload in rows:
                    self.client.index(index=target, id=atom_id, body=payload, refresh=False)
                return len(rows)
            operations: list[dict[str, Any]] = []
            for atom_id, payload in rows:
                operations.append({"index": {"_index": target, "_id": atom_id}})
                operations.append(payload)
            response = bulk(body=operations, refresh=False)
            if isinstance(response, dict) and response.get("errors"):
                failures = [
                    item for item in response.get("items", [])
                    if isinstance(item, dict)
                    and any(int(value.get("status", 500)) >= 300 for value in item.values() if isinstance(value, dict))
                ]
                detail = json.dumps(failures[:3], sort_keys=True)[:1_000]
                raise ProductionAdapterError(f"OpenSearch bulk delta rejected one or more documents: {detail}")
            return len(rows)

        for document in documents:
            atom_id = document.get("atom_version_id")
            if not atom_id:
                continue
            batch.append((str(atom_id), {**document, "index_revision": revision}))
            if len(batch) >= batch_size:
                indexed += flush(batch)
                batch = []
        return indexed + flush(batch)

    def revision_count(self, *, workspace_id: str, revision: str) -> int:
        target = self.revision_index(revision)
        body = {"query": {"bool": {"filter": self._filters(workspace_id, None, None, None, revision)}}}
        try:
            response = self.client.count(index=target, body=body)
        except TypeError:
            response = self.client.count(index=target, query=body["query"])
        return int(response.get("count", 0) if isinstance(response, dict) else getattr(response, "count", 0))

    def get_active_alias(self, alias: str | None = None) -> str | None:
        alias_name = alias or self.index
        try:
            aliases = self.client.indices.get_alias(name=alias_name)
            if isinstance(aliases, dict) and aliases:
                return list(aliases.keys())[0]
        except Exception:
            return None
        return None

    def verify_alias(self, revision: str, *, alias: str | None = None) -> bool:
        alias_name = alias or self.index
        expected_target = revision if "--rev-" in revision else self.revision_index(revision)
        current = self.get_active_alias(alias_name)
        return current == expected_target

    def restore_alias(self, target: str, *, alias: str | None = None) -> None:
        self.activate_revision(target, alias=alias)

    def delete_alias(self, alias: str) -> None:
        try:
            existing = self.client.indices.get_alias(name=alias)
            if isinstance(existing, dict):
                actions = [{"remove": {"alias": alias, "index": index}} for index in existing]
                if actions:
                    self.client.indices.update_aliases(body={"actions": actions})
        except Exception:
            pass

    def delete_atom(self, atom_version_id: str, *, revision: str) -> None:
        target = self.revision_index(revision)
        try:
            self.client.delete(index=target, id=str(atom_version_id), refresh=True)
        except Exception as error:
            status = getattr(error, "status_code", 0)
            if status != 404 and "not_found" not in str(error).lower() and "404" not in str(error):
                raise ProductionAdapterError(f"failed to delete atom {atom_version_id} from OpenSearch {target}: {error}") from error

    def verify_atom_absent(self, atom_version_id: str, *, revision: str) -> bool:
        target = self.revision_index(revision)
        try:
            return not bool(self.client.exists(index=target, id=str(atom_version_id)))
        except Exception as error:
            raise ProductionAdapterError(f"failed to verify absence of atom {atom_version_id} in OpenSearch {target}: {error}") from error

    def activate_revision(self, revision: str, *, alias: str | None = None) -> None:
        """Atomically move a read alias to a fully rebuilt revision index."""

        alias = alias or self.index
        target = revision if "--rev-" in revision else self.revision_index(revision)
        actions: list[dict[str, Any]] = []
        try:
            existing = self.client.indices.get_alias(name=alias)
        except Exception:
            existing = {}
        if isinstance(existing, dict):
            actions.extend({"remove": {"alias": alias, "index": index}} for index in existing if index != target)
        actions.append({"add": {"alias": alias, "index": target}})
        self.client.indices.update_aliases(body={"actions": actions})

    def rollback_revision(self, revision: str, *, alias: str | None = None) -> None:
        self.activate_revision(revision, alias=alias)


class QdrantDenseIndex:
    """Qdrant adapter keyed by atom version and dense index revision."""

    provider_id = "qdrant-bge-m3-v1"

    def __init__(self, collection: str, *, client: Any | None = None, url: str | None = None, api_key: str | None = None) -> None:
        self.collection = collection
        if client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("qdrant-client is required for QdrantDenseIndex") from error
            client = QdrantClient(url=url or os.environ.get("TRACE_QDRANT_URL"), api_key=api_key or os.environ.get("TRACE_QDRANT_API_KEY"))
        self.client = client

    @staticmethod
    def _revision_token(revision: str) -> str:
        token = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(revision)).strip("-_").lower()
        if not token:
            raise ValueError("vector revision must contain a letter or digit")
        return token[:96]

    @classmethod
    def _logical_revision(cls, revision: str) -> str:
        value = str(revision)
        if "--rev-" in value:
            raise ValueError("Qdrant revision must be a logical component revision, not a physical collection name")
        cls._revision_token(value)
        return value

    def revision_collection(self, revision: str) -> str:
        logical = self._logical_revision(revision)
        return f"{self.collection}--rev-{self._revision_token(logical)}"

    def create_revision(self, revision: str, *, vector_size: int | None = None) -> str:
        """Create a revision collection plus mandatory tenant payload indexes."""

        target = self.revision_collection(revision)
        if not vector_size:
            # Qdrant requires the dimension at collection creation. The first
            # embedding batch supplies it before any point is accepted.
            return target
        exists = False
        try:
            exists = bool(self.client.collection_exists(target))
        except Exception:
            try:
                self.client.get_collection(target)
                exists = True
            except Exception:
                exists = False
        if not exists:
            try:
                from qdrant_client.models import Distance, VectorParams

                vectors_config: Any = VectorParams(size=int(vector_size), distance=Distance.COSINE)
            except ImportError:
                vectors_config = {"size": int(vector_size), "distance": "Cosine"}
            self.client.create_collection(collection_name=target, vectors_config=vectors_config)
        try:
            from qdrant_client.models import PayloadSchemaType

            schemas: dict[str, Any] = {
                "workspace_id": PayloadSchemaType.KEYWORD,
                "visibility": PayloadSchemaType.KEYWORD,
                "facets": PayloadSchemaType.KEYWORD,
                "created_event_offset": PayloadSchemaType.INTEGER,
                "index_revision": PayloadSchemaType.KEYWORD,
                "atom_version_id": PayloadSchemaType.KEYWORD,
            }
        except ImportError:
            schemas = {
                "workspace_id": "keyword", "visibility": "keyword", "facets": "keyword",
                "created_event_offset": "integer", "index_revision": "keyword", "atom_version_id": "keyword",
            }
        for field_name, field_schema in schemas.items():
            try:
                self.client.create_payload_index(
                    collection_name=target, field_name=field_name, field_schema=field_schema, wait=True
                )
            except Exception:
                # Existing payload indexes are harmless; a parity check still
                # blocks activation if a usable revision was not produced.
                continue
        return target

    @staticmethod
    def _filter(workspace_id: str, visibility: Sequence[str] | None, facets: Sequence[str] | None, as_of_event: int | None, index_revision: str | None = None) -> Any:
        conditions: list[dict[str, Any]] = [{"key": "workspace_id", "match": {"value": workspace_id}}]
        if visibility:
            conditions.append({"should": [{"key": "visibility", "match": {"value": item}} for item in visibility]})
        if facets:
            conditions.extend({"key": "facets", "match": {"value": facet}} for facet in facets)
        if as_of_event is not None:
            conditions.append({"key": "created_event_offset", "range": {"lte": as_of_event}})
        if index_revision is not None:
            conditions.append({"key": "index_revision", "match": {"value": index_revision}})
        return {"must": conditions}

    def search(self, *, workspace_id: str, vector: Sequence[float], limit: int, visibility: Sequence[str] | None = None, facets: Sequence[str] | None = None, as_of_event: int | None = None, index_revision: str | None = None) -> list[dict[str, Any]]:
        query_filter = self._filter(workspace_id, visibility, facets, as_of_event, index_revision)
        target = self.revision_collection(index_revision) if index_revision else self.collection
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(collection_name=target, query=list(vector), query_filter=query_filter, limit=max(1, min(limit, 1_000)), with_payload=True)
            points = response.get("points", []) if isinstance(response, dict) else getattr(response, "points", response)
        else:  # qdrant-client versions before query_points
            points = self.client.search(collection_name=target, query_vector=list(vector), query_filter=query_filter, limit=max(1, min(limit, 1_000)), with_payload=True)
        output: list[dict[str, Any]] = []
        for point in points:
            if isinstance(point, dict):
                payload = dict(point.get("payload") or {})
                point_id = point.get("id")
                score = point.get("score", 0.0)
            else:
                payload = dict(getattr(point, "payload", None) or {})
                point_id = getattr(point, "id", None)
                score = getattr(point, "score", 0.0)
            output.append({**payload, "atom_version_id": str(payload.get("atom_version_id") or point_id), "dense_score": float(score or 0.0)})
        return output

    def upsert(self, vectors: Iterable[dict[str, Any]], *, revision: str) -> int:
        items = list(vectors)
        if not items:
            return 0
        target = self.create_revision(revision, vector_size=len(items[0]["vector"]))
        injected_client = self.client is not None
        try:
            from qdrant_client.models import PointStruct
        except ImportError:
            if not injected_client:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("qdrant-client models are required for QdrantDenseIndex")
            PointStruct = None
        points = []
        for item in items:
            atom_version_id = str(item["atom_version_id"])
            payload = {key: value for key, value in item.items() if key != "vector"}
            payload["atom_version_id"] = atom_version_id
            payload["index_revision"] = revision
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace:qdrant:{atom_version_id}:{revision}"))
            points.append(
                PointStruct(id=point_id, vector=list(item["vector"]), payload=payload)
                if PointStruct is not None
                else {"id": point_id, "vector": list(item["vector"]), "payload": payload}
            )
        batch_size = max(1, min(int(os.environ.get("TRACE_QDRANT_BATCH_SIZE", "256")), 2_000))
        for start in range(0, len(points), batch_size):
            self.client.upsert(collection_name=target, points=points[start:start + batch_size], wait=True)
        return len(points)

    def revision_count(self, *, workspace_id: str, revision: str) -> int:
        target = self.revision_collection(revision)
        query_filter = self._filter(workspace_id, None, None, None, revision)
        try:
            response = self.client.count(collection_name=target, count_filter=query_filter, exact=True)
        except TypeError:
            response = self.client.count(collection_name=target, filter=query_filter, exact=True)
        if isinstance(response, dict):
            return int(response.get("count", 0))
        return int(getattr(response, "count", 0))

    def get_active_alias(self, alias: str | None = None) -> str | None:
        alias_name = alias or self.collection
        try:
            aliases_info = self.client.get_aliases()
            aliases = getattr(aliases_info, "aliases", aliases_info)
            for a in aliases:
                a_name = getattr(a, "alias_name", None) or (a.get("alias_name") if isinstance(a, dict) else None)
                c_name = getattr(a, "collection_name", None) or (a.get("collection_name") if isinstance(a, dict) else None)
                if a_name == alias_name:
                    return c_name
        except Exception:
            return None
        return None

    def verify_alias(self, revision: str, *, alias: str | None = None) -> bool:
        alias_name = alias or self.collection
        expected_target = revision if "--rev-" in revision else self.revision_collection(revision)
        current = self.get_active_alias(alias_name)
        return current == expected_target

    def restore_alias(self, target: str, *, alias: str | None = None) -> None:
        self.activate_revision(target, alias=alias)

    def delete_alias(self, alias: str) -> None:
        try:
            self.client.update_collection_aliases(change_aliases_operations=[{"delete_alias": {"alias_name": alias}}])
        except Exception:
            pass

    def delete_atom(self, atom_version_id: str, *, revision: str) -> None:
        logical_revision = self._logical_revision(revision)
        target = self.revision_collection(logical_revision)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace:qdrant:{atom_version_id}:{logical_revision}"))
        try:
            try:
                from qdrant_client.models import PointIdsList
                self.client.delete(collection_name=target, points_selector=PointIdsList(points=[point_id]), wait=True)
            except Exception:
                self.client.delete(collection_name=target, points_selector=[point_id], wait=True)
        except Exception as error:
            raise ProductionAdapterError(f"failed to delete atom {atom_version_id} from Qdrant {target}: {error}") from error

    def verify_atom_absent(self, atom_version_id: str, *, revision: str) -> bool:
        logical_revision = self._logical_revision(revision)
        target = self.revision_collection(logical_revision)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace:qdrant:{atom_version_id}:{logical_revision}"))
        try:
            res = self.client.retrieve(collection_name=target, ids=[point_id])
            return len(res) == 0
        except Exception as error:
            raise ProductionAdapterError(f"failed to verify absence of atom {atom_version_id} in Qdrant {target}: {error}") from error

    def activate_revision(self, revision: str, *, alias: str | None = None) -> None:
        """Atomically move the query alias after successful parity checks."""

        alias = alias or self.collection
        target = revision if "--rev-" in revision else self.revision_collection(revision)
        operations = [
            {"delete_alias": {"alias_name": alias}},
            {"create_alias": {"collection_name": target, "alias_name": alias}},
        ]
        try:
            self.client.update_collection_aliases(change_aliases_operations=operations)
        except TypeError:
            self.client.update_collection_aliases(actions=operations)
        except Exception:
            # Initial activation has no old alias. Do not mask a failed create
            # operation; only retry the safe, create-only form.
            create_only = [operations[-1]]
            try:
                self.client.update_collection_aliases(change_aliases_operations=create_only)
            except TypeError:
                self.client.update_collection_aliases(actions=create_only)

    def rollback_revision(self, revision: str, *, alias: str | None = None) -> None:
        self.activate_revision(revision, alias=alias)



class NatsJetStreamPublisher:
    """NATS JetStream publisher with one persistent, drainable connection."""

    def __init__(self, *, servers: Sequence[str] | None = None, stream: str = "TRACE_EVENTS", client: Any | None = None) -> None:
        self.servers = list(servers or [os.environ.get("TRACE_NATS_URL", "nats://localhost:4222")])
        self.stream = stream
        self.client = client
        self._connection_lock = asyncio.Lock()

    async def _connected_client(self) -> Any:
        current = self.client
        if current is not None and not bool(getattr(current, "is_closed", False)):
            return current
        async with self._connection_lock:
            current = self.client
            if current is not None and not bool(getattr(current, "is_closed", False)):
                return current
            try:
                import nats
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("nats-py is required for NatsJetStreamPublisher") from error
            self.client = await nats.connect(servers=self.servers)
            return self.client

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        client = await self._connected_client()
        subject = f"{self.stream.lower()}.{topic.replace('.', '_')}"
        body = json.dumps(message, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if hasattr(client, "jetstream"):
            await client.jetstream().publish(subject, body)
        else:
            await client.publish(subject, body)

    async def drain(self) -> None:
        """Flush acknowledged work on shutdown without dropping the outbox."""

        async with self._connection_lock:
            client, self.client = self.client, None
        if client is None:
            return
        drain = getattr(client, "drain", None)
        if callable(drain):
            await drain()
            return
        close = getattr(client, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result


class RedisCoordinationStore:
    """Redis TTL cache/coordination adapter; values are never canonical truth."""

    def __init__(self, url: str | None = None, *, client: Any | None = None) -> None:
        if client is None:
            try:
                import redis
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("redis is required for RedisCoordinationStore") from error
            client = redis.Redis.from_url(url or os.environ.get("TRACE_REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
        self.client = client

    def get(self, key: str) -> str | None:
        return self.client.get(key)

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        self.client.set(key, value, ex=max(1, min(int(ttl_seconds), 86_400 * 30)))

    def delete(self, key: str) -> None:
        self.client.delete(key)


class InMemoryCoordinationStore:
    """Small deterministic coordination substitute for unit tests."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        item = self._values.get(key)
        if not item:
            return None
        value, expires = item
        if expires <= time.time():
            self._values.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        self._values[key] = (value, time.time() + max(1, ttl_seconds))

    def delete(self, key: str) -> None:
        self._values.pop(key, None)
