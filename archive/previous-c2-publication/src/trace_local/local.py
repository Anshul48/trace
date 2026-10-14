"""Local-first Trace Phase 1 storage and retrieval API.

This module intentionally depends only on the Python standard library. One
selected directory contains the SQLite ledger, immutable source atoms,
attachments, and a replaceable lexical projection. It never fetches a URI,
starts a service, or contacts a model provider.

The stable public import namespace is trace_local, avoiding the Python
standard-library module named trace.
"""

from __future__ import annotations

from collections import Counter, OrderedDict, deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import importlib
from itertools import islice
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import threading
import time
from typing import Any, Literal, Protocol, TypeAlias
from uuid import uuid4
import zipfile


EXPORT_FORMAT = "trace.phase1.export"
EXPORT_SCHEMA_VERSION = 1
LOCAL_SCHEMA_VERSION = 2
DEFAULT_COLLECTION = "default"
_TOKEN = re.compile(r"[\w][\w.'/-]*", re.UNICODE)


class TraceLocalError(RuntimeError):
    """Base exception for the dependency-light local API."""


class RecordValidationError(ValueError):
    """A caller-normalized record did not meet the Phase 1 input contract."""


class ImportBundleError(TraceLocalError):
    """An export archive is malformed, incomplete, or conflicts with local data."""


class ProjectionError(TraceLocalError):
    """A rebuildable projection cannot be constructed safely."""


class CapacityError(TraceLocalError):
    """A write or nonessential job would violate transactional disk headroom."""

    retryable = True

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: int = 60,
        status: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.status = dict(status or {})

    def public_dict(self) -> dict[str, Any]:
        return {
            "error": "capacity_pressure",
            "detail": str(self),
            "retryable": True,
            "retry_after_seconds": self.retry_after_seconds,
            "status": self.status,
        }


class LocalEmbeddingPlugin(Protocol):
    """Explicitly installed local embedding extension."""

    provider_id: str

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class LocalRerankerPlugin(Protocol):
    """Explicitly installed local reranking extension."""

    provider_id: str

    def score(self, query: str, documents: Sequence[str]) -> Sequence[float]: ...


PluginRef: TypeAlias = str | LocalEmbeddingPlugin | LocalRerankerPlugin
ResourceProbe: TypeAlias = Callable[[Path], Mapping[str, int] | tuple[int, int]]


@dataclass(frozen=True)
class ResourcePolicy:
    """Bounded local-resource policy, not a hardware admission requirement."""

    reserve_bytes: int | None = None
    minimum_reserve_bytes: int = 8 * 1024 * 1024
    maximum_reserve_bytes: int = 512 * 1024 * 1024
    reserve_fraction: float = 0.01
    cache_entries: int = 128
    constrained_cache_entries: int = 24
    query_history_size: int = 512
    background_concurrency: int = 1

    def __post_init__(self) -> None:
        if self.reserve_bytes is not None and self.reserve_bytes < 0:
            raise ValueError("reserve_bytes must be non-negative")
        if not 0 < self.reserve_fraction < 1:
            raise ValueError("reserve_fraction must be between zero and one")
        if self.cache_entries < 1 or self.constrained_cache_entries < 1:
            raise ValueError("cache limits must be positive")
        if self.background_concurrency < 0:
            raise ValueError("background_concurrency must be non-negative")


@dataclass(frozen=True)
class ResourceSnapshot:
    """Public resource measurements reported by LocalTrace.status."""

    free_disk_bytes: int
    total_disk_bytes: int
    reserved_disk_bytes: int
    database_bytes: int
    attachment_bytes: int
    index_growth_bytes: int
    cache_entries: int
    cache_capacity: int
    queue_depth: int
    ingestion_rate_per_second: float
    observed_query_p95_ms: float
    observed_query_count: int
    pressure: Literal["normal", "constrained", "critical"]
    background_concurrency: int


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise RecordValidationError(f"value must be JSON serializable: {error}") from error


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _parse_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


def _safe_json_object(value: Any, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RecordValidationError(f"{field} must be a JSON object")
    result = dict(value)
    _canonical_json(result)
    return result


def _safe_json_list(value: Any, *, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RecordValidationError(f"{field} must be a JSON array")
    result = list(value)
    _canonical_json(result)
    return result


def _text_terms(text: str) -> list[str]:
    return [term.casefold() for term in _TOKEN.findall(text)]


def _tree_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for candidate in path.rglob("*"):
        if candidate.is_file():
            try:
                total += candidate.stat().st_size
            except OSError:
                continue
    return total


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return float(ordered[index])


def _coerce_plugin(plugin: PluginRef, capability: Literal["embedding", "reranker"]) -> Any:
    """Load a plugin only after an explicit caller opt-in."""

    loaded: Any = plugin
    if isinstance(plugin, str):
        module_name, separator, attribute = plugin.partition(":")
        if not separator or not module_name or not attribute:
            raise ValueError("plugin references must use 'package.module:object'")
        try:
            loaded = getattr(importlib.import_module(module_name), attribute)
        except (ImportError, AttributeError) as error:
            raise ValueError(f"cannot load local {capability} plugin {plugin!r}: {error}") from error
        if isinstance(loaded, type) or (
            callable(loaded) and not hasattr(loaded, "embed") and not hasattr(loaded, "score")
        ):
            loaded = loaded()
    method = "embed" if capability == "embedding" else "score"
    if not callable(getattr(loaded, method, None)):
        raise ValueError(f"{capability} plugin must provide {method}(...)")
    return loaded


@dataclass(frozen=True)
class _NormalizedRecord:
    document_name: str
    source_url: str | None
    file_uri: str | None
    content: str
    content_hash: str
    metadata: dict[str, Any]
    image_descriptions: list[Any]
    external_id: str | None
    collection: str
    media_type: str
    raw_record: dict[str, Any]

    @property
    def record_hash(self) -> str:
        return _sha256_text(
            _canonical_json(
                {
                    "document_name": self.document_name,
                    "source_url": self.source_url,
                    "file_uri": self.file_uri,
                    "content": self.content,
                    "content_hash": self.content_hash,
                    "metadata": self.metadata,
                    "image_descriptions": self.image_descriptions,
                    "external_id": self.external_id,
                    "collection": self.collection,
                    "media_type": self.media_type,
                    "raw_record": self.raw_record,
                }
            )
        )


def _normalize_record(record: Mapping[str, Any]) -> _NormalizedRecord:
    """Validate a caller-normalized record without altering source strings."""

    raw_record = dict(record)
    document_name = record.get("document_name", record.get("document", record.get("name")))
    content = record.get("content", record.get("text"))
    source_url = record.get("source_url", record.get("url"))
    file_uri = record.get("file_uri")
    source_uri = record.get("source_uri")
    if source_uri is not None and source_url is None and file_uri is None:
        if isinstance(source_uri, str) and "://" in source_uri and not source_uri.lower().startswith("file:"):
            source_url = source_uri
        else:
            file_uri = source_uri
    if not isinstance(document_name, str) or not document_name:
        raise RecordValidationError("document_name must be a non-empty string")
    if not isinstance(content, str) or not content:
        raise RecordValidationError("content (or text) must be a non-empty string")
    if source_url is not None and not isinstance(source_url, str):
        raise RecordValidationError("source_url must be a string when provided")
    if file_uri is not None and not isinstance(file_uri, str):
        raise RecordValidationError("file_uri must be a string when provided")
    if source_url is None and file_uri is None:
        raise RecordValidationError("one of source_url, file_uri, or source_uri is required")
    declared_hash = record.get("content_hash")
    if declared_hash is None:
        declared_hash = _sha256_text(content)
    if not isinstance(declared_hash, str) or not declared_hash:
        raise RecordValidationError("content_hash must be a non-empty string")
    metadata = _safe_json_object(record.get("metadata"), field="metadata")
    image_descriptions = _safe_json_list(
        record.get("image_descriptions", record.get("image_description_blocks")),
        field="image_descriptions",
    )
    external_id = record.get("record_id", record.get("external_id", record.get("id")))
    if external_id is not None and (not isinstance(external_id, str) or not external_id):
        raise RecordValidationError("record_id must be a non-empty string when provided")
    collection = record.get("collection", DEFAULT_COLLECTION)
    if not isinstance(collection, str) or not collection:
        raise RecordValidationError("collection must be a non-empty string")
    media_type = record.get("media_type", "text/plain; charset=utf-8")
    if not isinstance(media_type, str) or not media_type:
        raise RecordValidationError("media_type must be a non-empty string")
    _canonical_json(raw_record)
    return _NormalizedRecord(
        document_name=document_name,
        source_url=source_url,
        file_uri=file_uri,
        content=content,
        content_hash=declared_hash,
        metadata=metadata,
        image_descriptions=image_descriptions,
        external_id=external_id,
        collection=collection,
        media_type=media_type,
        raw_record=raw_record,
    )


class LocalTrace:
    """One offline Trace store rooted at a directory chosen by its operator."""

    def __init__(
        self,
        data_dir: str | os.PathLike[str],
        *,
        resource_policy: ResourcePolicy | None = None,
        resource_probe: ResourceProbe | None = None,
    ) -> None:
        if not isinstance(data_dir, (str, os.PathLike)):
            raise TypeError("data_dir must be a filesystem path selected by the caller")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir = self.data_dir / "attachments"
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "trace.sqlite3"
        self.resource_policy = resource_policy or ResourcePolicy()
        self._resource_probe = resource_probe
        self._lock = threading.RLock()
        self._query_latencies_ms: deque[float] = deque(maxlen=self.resource_policy.query_history_size)
        self._result_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._initialize()

    @classmethod
    def open(
        cls,
        data_dir: str | os.PathLike[str],
        *,
        resource_policy: ResourcePolicy | None = None,
        resource_probe: ResourceProbe | None = None,
    ) -> "LocalTrace":
        return cls(data_dir, resource_policy=resource_policy, resource_probe=resource_probe)

    def __enter__(self) -> "LocalTrace":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _initialize(self) -> None:
        with self._lock:
            connection = self._connection
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trace_meta (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE, event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL, actor TEXT NOT NULL,
                    parent_event_id TEXT, payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, origin_event_id TEXT,
                    origin_sequence INTEGER
                );
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY, document_name TEXT NOT NULL,
                    source_url TEXT, file_uri TEXT, collection_name TEXT NOT NULL,
                    declared_content_hash TEXT NOT NULL, stored_content_hash TEXT NOT NULL,
                    media_type TEXT NOT NULL, metadata_json TEXT NOT NULL,
                    image_descriptions_json TEXT NOT NULL, raw_record_json TEXT NOT NULL,
                    record_hash TEXT NOT NULL, external_id TEXT UNIQUE,
                    created_event_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    attachment_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL UNIQUE REFERENCES documents(document_id),
                    object_key TEXT NOT NULL, content_hash TEXT NOT NULL,
                    media_type TEXT NOT NULL, byte_length INTEGER NOT NULL,
                    created_event_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS atoms (
                    atom_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    attachment_id TEXT NOT NULL REFERENCES attachments(attachment_id),
                    ordinal INTEGER NOT NULL, content TEXT NOT NULL,
                    content_hash TEXT NOT NULL, created_event_id TEXT NOT NULL,
                    UNIQUE(document_id, ordinal)
                );
                CREATE INDEX IF NOT EXISTS atoms_document_id ON atoms(document_id);
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY, proposal_type TEXT NOT NULL,
                    candidate_json TEXT NOT NULL, evidence_atom_ids_json TEXT NOT NULL,
                    status TEXT NOT NULL, actor TEXT NOT NULL, reviewer TEXT,
                    decision_reason TEXT, created_event_id TEXT NOT NULL,
                    decided_event_id TEXT
                );
                CREATE INDEX IF NOT EXISTS proposals_status ON proposals(status, proposal_type);
                CREATE TABLE IF NOT EXISTS navigation_summaries (
                    summary_id TEXT PRIMARY KEY,
                    proposal_id TEXT UNIQUE REFERENCES proposals(proposal_id),
                    title TEXT NOT NULL, sections_json TEXT NOT NULL,
                    evidence_atom_ids_json TEXT NOT NULL,
                    published_event_id TEXT NOT NULL, published_by TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS work_queue (
                    work_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, completed_at TEXT, detail TEXT
                );
                CREATE INDEX IF NOT EXISTS work_queue_status ON work_queue(status, created_at);
                CREATE TABLE IF NOT EXISTS projection_state (
                    projection_name TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    atom_count INTEGER NOT NULL, canonical_hash TEXT NOT NULL,
                    indexed_at TEXT NOT NULL, index_growth_bytes INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS query_observations (
                    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    elapsed_ms REAL NOT NULL,
                    mode TEXT NOT NULL,
                    cache_hit INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS query_observations_at
                    ON query_observations(observation_id DESC);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO trace_meta(key,value) VALUES('schema_version',?)",
                (str(LOCAL_SCHEMA_VERSION),),
            )
            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS lexical_fts USING fts5(
                        atom_id UNINDEXED, content, document_name,
                        source_url, file_uri, metadata
                    )
                    """
                )
                self._fts_available = True
            except sqlite3.OperationalError:
                self._fts_available = False
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS lexical_terms (
                        atom_id TEXT NOT NULL REFERENCES atoms(atom_id),
                        term TEXT NOT NULL, frequency INTEGER NOT NULL,
                        PRIMARY KEY(atom_id, term)
                    );
                    CREATE INDEX IF NOT EXISTS lexical_terms_term ON lexical_terms(term);
                    """
                )
            self._migrate_legacy_attachment_schema()
            connection.execute(
                "INSERT INTO trace_meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(LOCAL_SCHEMA_VERSION),),
            )
            if self._projection_count() == 0 and self._atom_count() > 0:
                self._rebuild_projection(force=True, actor="system", record_event=False)

    def _migrate_legacy_attachment_schema(self) -> None:
        """Allow several immutable documents to share one content-addressed file.

        Early alpha directories made attachment object keys unique. That is
        wrong when two independently sourced records have byte-identical text:
        they should retain separate provenance rows while safely sharing the
        same content-addressed attachment bytes.
        """

        row = self._connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='attachments'"
        ).fetchone()
        definition = re.sub(r"\s+", " ", str(row["sql"] or "")).upper() if row else ""
        if "OBJECT_KEY TEXT NOT NULL UNIQUE" not in definition:
            return
        self._connection.execute("PRAGMA foreign_keys=OFF")
        try:
            self._connection.executescript(
                """
                BEGIN IMMEDIATE;
                ALTER TABLE atoms RENAME TO atoms_legacy_attachment_key;
                ALTER TABLE attachments RENAME TO attachments_legacy_attachment_key;
                CREATE TABLE attachments (
                    attachment_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL UNIQUE REFERENCES documents(document_id),
                    object_key TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    byte_length INTEGER NOT NULL,
                    created_event_id TEXT NOT NULL
                );
                INSERT INTO attachments(
                    attachment_id,document_id,object_key,content_hash,media_type,byte_length,created_event_id
                )
                SELECT attachment_id,document_id,object_key,content_hash,media_type,byte_length,created_event_id
                FROM attachments_legacy_attachment_key;
                CREATE TABLE atoms (
                    atom_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    attachment_id TEXT NOT NULL REFERENCES attachments(attachment_id),
                    ordinal INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_event_id TEXT NOT NULL,
                    UNIQUE(document_id, ordinal)
                );
                INSERT INTO atoms(
                    atom_id,document_id,attachment_id,ordinal,content,content_hash,created_event_id
                )
                SELECT atom_id,document_id,attachment_id,ordinal,content,content_hash,created_event_id
                FROM atoms_legacy_attachment_key;
                DROP TABLE atoms_legacy_attachment_key;
                DROP TABLE attachments_legacy_attachment_key;
                CREATE INDEX IF NOT EXISTS atoms_document_id ON atoms(document_id);
                COMMIT;
                """
            )
        finally:
            self._connection.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def _transaction(self) -> Iterable[sqlite3.Connection]:
        with self._lock:
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            else:
                connection.execute("COMMIT")

    def _append_event(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        actor: str,
        parent_event_id: str | None = None,
        event_id: str | None = None,
        occurred_at: str | None = None,
        origin_event_id: str | None = None,
        origin_sequence: int | None = None,
    ) -> dict[str, Any]:
        encoded_payload = _canonical_json(dict(payload))
        event_id = event_id or str(uuid4())
        event = {
            "event_id": event_id, "event_type": event_type,
            "occurred_at": occurred_at or _utc_now(), "actor": actor,
            "parent_event_id": parent_event_id, "payload": json.loads(encoded_payload),
            "payload_hash": _sha256_text(encoded_payload),
            "origin_event_id": origin_event_id, "origin_sequence": origin_sequence,
        }
        cursor = connection.execute(
            """
            INSERT INTO events(
                event_id,event_type,occurred_at,actor,parent_event_id,payload_json,
                payload_hash,origin_event_id,origin_sequence
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                event["event_id"], event["event_type"], event["occurred_at"],
                event["actor"], event["parent_event_id"], encoded_payload,
                event["payload_hash"], event["origin_event_id"], event["origin_sequence"],
            ),
        )
        event["sequence"] = int(cursor.lastrowid)
        return event

    # --------------------------------------------------------------- capacity
    def _volume_usage(self) -> tuple[int, int]:
        if self._resource_probe is not None:
            observed = self._resource_probe(self.data_dir)
            if isinstance(observed, Mapping):
                free = int(observed["free_disk_bytes"])
                total = int(observed["total_disk_bytes"])
            else:
                free, total = int(observed[0]), int(observed[1])
            return max(0, free), max(1, total)
        usage = shutil.disk_usage(self.data_dir)
        return int(usage.free), int(usage.total)

    def _reserved_disk_bytes(self, total_bytes: int) -> int:
        if self.resource_policy.reserve_bytes is not None:
            return self.resource_policy.reserve_bytes
        calculated = int(total_bytes * self.resource_policy.reserve_fraction)
        return max(
            min(self.resource_policy.maximum_reserve_bytes, calculated),
            min(self.resource_policy.minimum_reserve_bytes, total_bytes),
        )

    def _database_bytes(self) -> int:
        return sum(
            _tree_size(candidate)
            for candidate in (
                self.db_path,
                self.db_path.with_name(self.db_path.name + "-wal"),
                self.db_path.with_name(self.db_path.name + "-shm"),
            )
        )

    def _queue_depth(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS count FROM work_queue WHERE status='queued'").fetchone()
        return int(row["count"])

    def _atom_count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS count FROM atoms").fetchone()
        return int(row["count"])

    def _projection_count(self) -> int:
        if self._fts_available:
            row = self._connection.execute("SELECT COUNT(*) AS count FROM lexical_fts").fetchone()
        else:
            row = self._connection.execute("SELECT COUNT(DISTINCT atom_id) AS count FROM lexical_terms").fetchone()
        return int(row["count"])

    def _ingestion_rate(self) -> float:
        cutoff = datetime.fromtimestamp(time.time() - 60, UTC).isoformat()
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM events WHERE event_type='ingestion.accepted' AND occurred_at>=?",
            (cutoff,),
        ).fetchone()
        return round(int(row["count"]) / 60.0, 4)

    def _observed_query_metrics(self) -> tuple[float, int]:
        rows = self._connection.execute(
            "SELECT elapsed_ms FROM query_observations ORDER BY observation_id DESC LIMIT ?",
            (self.resource_policy.query_history_size,),
        ).fetchall()
        values = [float(row["elapsed_ms"]) for row in rows]
        return round(_percentile(values, 0.95), 3), len(values)

    def _record_query_observation(self, *, elapsed_ms: float, mode: str, cache_hit: bool) -> None:
        """Persist bounded local diagnostics without making query success depend on it."""

        try:
            with self._transaction() as connection:
                connection.execute(
                    "INSERT INTO query_observations(occurred_at,elapsed_ms,mode,cache_hit) VALUES(?,?,?,?)",
                    (_utc_now(), elapsed_ms, mode, int(cache_hit)),
                )
                connection.execute(
                    """
                    DELETE FROM query_observations
                    WHERE observation_id NOT IN (
                        SELECT observation_id FROM query_observations
                        ORDER BY observation_id DESC LIMIT ?
                    )
                    """,
                    (self.resource_policy.query_history_size,),
                )
        except sqlite3.Error:
            # Metrics are a rebuildable diagnostic projection. A full disk or
            # transient lock must not hide a raw evidence result.
            return

    @staticmethod
    def _pressure(free_bytes: int, reserved_bytes: int) -> Literal["normal", "constrained", "critical"]:
        if free_bytes <= reserved_bytes:
            return "critical"
        if free_bytes <= reserved_bytes * 2:
            return "constrained"
        return "normal"

    def _cache_capacity(self, pressure: str) -> int:
        return self.resource_policy.cache_entries if pressure == "normal" else self.resource_policy.constrained_cache_entries

    def _trim_cache(self, pressure: str) -> None:
        while len(self._result_cache) > self._cache_capacity(pressure):
            self._result_cache.popitem(last=False)

    def resource_snapshot(self) -> ResourceSnapshot:
        free_bytes, total_bytes = self._volume_usage()
        reserved_bytes = self._reserved_disk_bytes(total_bytes)
        pressure = self._pressure(free_bytes, reserved_bytes)
        self._trim_cache(pressure)
        projection = self._connection.execute(
            "SELECT index_growth_bytes FROM projection_state WHERE projection_name='lexical'"
        ).fetchone()
        background_concurrency = self.resource_policy.background_concurrency if pressure == "normal" else 0
        observed_p95, observed_count = self._observed_query_metrics()
        return ResourceSnapshot(
            free_disk_bytes=free_bytes,
            total_disk_bytes=total_bytes,
            reserved_disk_bytes=reserved_bytes,
            database_bytes=self._database_bytes(),
            attachment_bytes=_tree_size(self.attachments_dir),
            index_growth_bytes=int(projection["index_growth_bytes"]) if projection else 0,
            cache_entries=len(self._result_cache),
            cache_capacity=self._cache_capacity(pressure),
            queue_depth=self._queue_depth(),
            ingestion_rate_per_second=self._ingestion_rate(),
            observed_query_p95_ms=observed_p95,
            observed_query_count=observed_count,
            pressure=pressure,
            background_concurrency=background_concurrency,
        )

    def status(self) -> dict[str, Any]:
        """Report local pressure and performance without telemetry export."""

        snapshot = self.resource_snapshot()
        lexical_state = self._connection.execute(
            "SELECT revision,atom_count,canonical_hash,indexed_at FROM projection_state WHERE projection_name='lexical'"
        ).fetchone()
        return {
            "data_dir": str(self.data_dir),
            "offline_by_default": True,
            "runtime_network_access": False,
            "canonical": {
                "source_atoms": self._atom_count(),
                "events": int(self._connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()["count"]),
                "attachments": int(self._connection.execute("SELECT COUNT(*) AS count FROM attachments").fetchone()["count"]),
            },
            "capacity": {
                "pressure": snapshot.pressure,
                "free_disk_bytes": snapshot.free_disk_bytes,
                "total_disk_bytes": snapshot.total_disk_bytes,
                "reserved_disk_bytes": snapshot.reserved_disk_bytes,
                "writes_safe": snapshot.pressure != "critical",
            },
            "storage": {
                "database_bytes": snapshot.database_bytes,
                "attachment_bytes": snapshot.attachment_bytes,
                "index_growth_bytes": snapshot.index_growth_bytes,
            },
            "cache": {
                "entries": snapshot.cache_entries,
                "capacity": snapshot.cache_capacity,
                "pressure": round(snapshot.cache_entries / max(1, snapshot.cache_capacity), 3),
            },
            "queue": {
                "depth": snapshot.queue_depth,
                "background_concurrency": snapshot.background_concurrency,
                "deferred_when_constrained": True,
            },
            "ingestion": {"rate_per_second": snapshot.ingestion_rate_per_second},
            "queries": {
                "observed_count": snapshot.observed_query_count,
                "p95_latency_ms": snapshot.observed_query_p95_ms,
            },
            "projection": {
                "backend": "sqlite-fts5" if self._fts_available else "sqlite-term-fallback",
                "revision": int(lexical_state["revision"]) if lexical_state else 0,
                "indexed_atoms": int(lexical_state["atom_count"]) if lexical_state else self._projection_count(),
                "last_rebuild_at": lexical_state["indexed_at"] if lexical_state else None,
            },
        }

    def _ensure_write_capacity(self, estimated_bytes: int, *, purpose: str) -> None:
        snapshot = self.resource_snapshot()
        remaining = snapshot.free_disk_bytes - max(0, estimated_bytes)
        if remaining < snapshot.reserved_disk_bytes:
            raise CapacityError(
                f"{purpose} is deferred because it would consume transactional disk headroom",
                status=self.status(),
            )

    def _ensure_background_capacity(self, *, purpose: str, estimated_bytes: int) -> None:
        snapshot = self.resource_snapshot()
        if snapshot.pressure != "normal":
            # Queue state is helpful when there is room for a tiny SQLite
            # transaction. At critical pressure even that diagnostic write is
            # skipped, preserving the same headroom rule as source ingestion.
            if snapshot.free_disk_bytes - 4 * 1024 >= snapshot.reserved_disk_bytes:
                self._enqueue_work(
                    kind=purpose,
                    payload={"reason": "resource_pressure"},
                    detail="deferred due to resource pressure",
                )
            raise CapacityError(
                f"{purpose} is deferred while local resource pressure is {snapshot.pressure}",
                status=self.status(),
            )
        self._ensure_write_capacity(estimated_bytes, purpose=purpose)

    # ----------------------------------------------------------- source atoms
    def _attachment_path(self, object_key: str) -> Path:
        candidate = self.attachments_dir / object_key
        resolved = candidate.resolve()
        root = self.attachments_dir.resolve()
        if root not in (resolved, *resolved.parents):
            raise ImportBundleError("attachment object key escapes the selected data directory")
        return candidate

    def _store_attachment(self, raw: bytes, content_hash: str) -> str:
        object_key = (Path(content_hash[:2]) / content_hash).as_posix()
        destination = self._attachment_path(object_key)
        if destination.exists():
            return object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".trace-", delete=False) as temporary:
                temporary.write(raw)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
        return object_key

    def _index_atom(self, connection: sqlite3.Connection, row: Mapping[str, Any]) -> None:
        searchable_provenance = _canonical_json(
            {
                "metadata": row["metadata"],
                "image_descriptions": row.get("image_descriptions", []),
            }
        )
        if self._fts_available:
            connection.execute(
                """
                INSERT INTO lexical_fts(atom_id,content,document_name,source_url,file_uri,metadata)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    row["atom_id"],
                    row["content"],
                    row["document_name"],
                    row.get("source_url") or "",
                    row.get("file_uri") or "",
                    searchable_provenance,
                ),
            )
            return
        searchable = " ".join(
            (
                str(row["content"]),
                str(row["document_name"]),
                str(row.get("source_url") or ""),
                str(row.get("file_uri") or ""),
                searchable_provenance,
            )
        )
        frequencies = Counter(_text_terms(searchable))
        connection.executemany(
            "INSERT INTO lexical_terms(atom_id,term,frequency) VALUES(?,?,?)",
            [(row["atom_id"], term, frequency) for term, frequency in frequencies.items()],
        )

    def _clear_query_cache(self) -> None:
        self._result_cache.clear()

    def ingest(self, record: Mapping[str, Any], *, actor: str = "local-user") -> dict[str, Any]:
        """Append one immutable, caller-normalized source atom.

        Trace stores document names, URLs, file URIs, hashes, metadata, and
        image-description blocks as supplied. It never opens a source path or
        fetches a source URL.
        """

        normalized = _normalize_record(record)
        if normalized.external_id:
            existing = self._connection.execute(
                "SELECT document_id,record_hash FROM documents WHERE external_id=?",
                (normalized.external_id,),
            ).fetchone()
            if existing is not None:
                if existing["record_hash"] != normalized.record_hash:
                    raise RecordValidationError("record_id was already used for different immutable source content")
                result = self._document_result(existing["document_id"])
                result["duplicate"] = True
                return result
        raw = normalized.content.encode("utf-8")
        self._ensure_write_capacity(max(64 * 1024, len(raw) * 3), purpose="ingestion")
        stored_content_hash = _sha256_bytes(raw)
        object_key = self._store_attachment(raw, stored_content_hash)
        document_id, attachment_id, atom_id = str(uuid4()), str(uuid4()), str(uuid4())
        event_payload = {
            "document_id": document_id,
            "attachment_id": attachment_id,
            "atom_id": atom_id,
            "collection": normalized.collection,
            "document_name": normalized.document_name,
            "source_url": normalized.source_url,
            "file_uri": normalized.file_uri,
            "content_hash": normalized.content_hash,
            "stored_content_hash": stored_content_hash,
            "external_id": normalized.external_id,
        }
        with self._transaction() as connection:
            if normalized.external_id:
                existing = connection.execute(
                    "SELECT document_id,record_hash FROM documents WHERE external_id=?",
                    (normalized.external_id,),
                ).fetchone()
                if existing is not None:
                    if existing["record_hash"] != normalized.record_hash:
                        raise RecordValidationError("record_id was already used for different immutable source content")
                    result = self._document_result(existing["document_id"])
                    result["duplicate"] = True
                    return result
            event = self._append_event(connection, "ingestion.accepted", event_payload, actor=actor)
            connection.execute(
                """
                INSERT INTO documents(
                    document_id,document_name,source_url,file_uri,collection_name,
                    declared_content_hash,stored_content_hash,media_type,metadata_json,
                    image_descriptions_json,raw_record_json,record_hash,external_id,created_event_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    document_id, normalized.document_name, normalized.source_url, normalized.file_uri,
                    normalized.collection, normalized.content_hash, stored_content_hash,
                    normalized.media_type, _canonical_json(normalized.metadata),
                    _canonical_json(normalized.image_descriptions), _canonical_json(normalized.raw_record),
                    normalized.record_hash, normalized.external_id, event["event_id"],
                ),
            )
            connection.execute(
                """
                INSERT INTO attachments(
                    attachment_id,document_id,object_key,content_hash,media_type,byte_length,created_event_id
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    attachment_id, document_id, object_key, stored_content_hash,
                    normalized.media_type, len(raw), event["event_id"],
                ),
            )
            connection.execute(
                "INSERT INTO atoms(atom_id,document_id,attachment_id,ordinal,content,content_hash,created_event_id) VALUES(?,?,?,?,?,?,?)",
                (atom_id, document_id, attachment_id, 0, normalized.content, stored_content_hash, event["event_id"]),
            )
            self._index_atom(
                connection,
                {
                    "atom_id": atom_id, "content": normalized.content,
                    "document_name": normalized.document_name, "source_url": normalized.source_url,
                    "file_uri": normalized.file_uri, "metadata": normalized.metadata,
                    "image_descriptions": normalized.image_descriptions,
                },
            )
        self._clear_query_cache()
        return self._document_result(document_id, event=event)

    def ingest_many(self, records: Iterable[Mapping[str, Any]], *, actor: str = "local-user") -> list[dict[str, Any]]:
        return [self.ingest(record, actor=actor) for record in records]

    def ingest_jsonl(
        self,
        source: str | os.PathLike[str] | Iterable[str],
        *,
        actor: str = "local-user",
    ) -> list[dict[str, Any]]:
        """Ingest JSONL records without inspecting any referenced source URI."""

        if isinstance(source, os.PathLike):
            lines: Iterable[str] = Path(source).read_text(encoding="utf-8-sig").splitlines()
        elif isinstance(source, str):
            source_path = Path(source)
            lines = source_path.read_text(encoding="utf-8-sig").splitlines() if source_path.exists() else source.splitlines()
        else:
            lines = source
        results: list[dict[str, Any]] = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as error:
                raise RecordValidationError(f"invalid JSONL record on line {line_number}: {error.msg}") from error
            if not isinstance(parsed, Mapping):
                raise RecordValidationError(f"JSONL record on line {line_number} must be an object")
            results.append(self.ingest(parsed, actor=actor))
        return results

    def ingest_json(
        self,
        source: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | os.PathLike[str],
        *,
        actor: str = "local-user",
    ) -> list[dict[str, Any]]:
        """Ingest one JSON object or a JSON array of normalized source records."""

        parsed: Any
        if isinstance(source, Mapping):
            parsed = source
        elif isinstance(source, os.PathLike):
            try:
                parsed = json.loads(Path(source).read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as error:
                raise RecordValidationError(f"invalid JSON input: {error.msg}") from error
        elif isinstance(source, str):
            source_path = Path(source)
            try:
                parsed = json.loads(source_path.read_text(encoding="utf-8-sig") if source_path.exists() else source)
            except json.JSONDecodeError as error:
                raise RecordValidationError(f"invalid JSON input: {error.msg}") from error
        else:
            parsed = source
        if isinstance(parsed, Mapping):
            return [self.ingest(parsed, actor=actor)]
        if not isinstance(parsed, Sequence) or isinstance(parsed, (str, bytes, bytearray)):
            raise RecordValidationError("JSON input must be an object or an array of objects")
        records: list[Mapping[str, Any]] = []
        for index, item in enumerate(parsed):
            if not isinstance(item, Mapping):
                raise RecordValidationError(f"JSON record at index {index} must be an object")
            records.append(item)
        return self.ingest_many(records, actor=actor)

    def _document_result(self, document_id: str, *, event: Mapping[str, Any] | None = None) -> dict[str, Any]:
        row = self._connection.execute(
            """
            SELECT d.*,a.attachment_id,a.object_key,a.byte_length,a.content_hash AS attachment_content_hash,
                   atom.atom_id,atom.content AS atom_content,atom.created_event_id AS atom_created_event_id
            FROM documents d
            JOIN attachments a ON a.document_id=d.document_id
            JOIN atoms atom ON atom.document_id=d.document_id
            WHERE d.document_id=? ORDER BY atom.ordinal LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown document {document_id}")
        return {
            "document_id": row["document_id"], "atom_id": row["atom_id"],
            "attachment_id": row["attachment_id"],
            "event_id": event["event_id"] if event else row["created_event_id"],
            "event_sequence": event["sequence"] if event else self._event_sequence(row["created_event_id"]),
            "collection": row["collection_name"], "document_name": row["document_name"],
            "source_url": row["source_url"], "file_uri": row["file_uri"],
            "content_hash": row["declared_content_hash"],
            "stored_content_hash": row["stored_content_hash"], "media_type": row["media_type"],
            "metadata": _parse_json(row["metadata_json"], {}),
            "image_descriptions": _parse_json(row["image_descriptions_json"], []),
            "atom_count": 1, "duplicate": False,
        }

    def _event_sequence(self, event_id: str) -> int | None:
        row = self._connection.execute("SELECT sequence FROM events WHERE event_id=?", (event_id,)).fetchone()
        return int(row["sequence"]) if row else None

    # --------------------------------------------------------------- evidence
    def _joined_atom_row(self, atom_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT atom.*,d.document_name,d.source_url,d.file_uri,d.collection_name,
                   d.declared_content_hash,d.stored_content_hash,d.media_type,d.metadata_json,
                   d.image_descriptions_json,d.raw_record_json,d.created_event_id AS document_created_event_id,
                   att.object_key,att.byte_length
            FROM atoms atom
            JOIN documents d ON d.document_id=atom.document_id
            JOIN attachments att ON att.attachment_id=atom.attachment_id
            WHERE atom.atom_id=?
            """,
            (atom_id,),
        ).fetchone()

    def get_atom(self, atom_id: str) -> dict[str, Any]:
        """Return raw atom text plus all searchable provenance."""

        row = self._joined_atom_row(atom_id)
        if row is None:
            raise KeyError(f"unknown atom {atom_id}")
        return self._atom_public_dict(row)

    def get_attachment(self, attachment_id: str) -> bytes:
        """Read retained attachment bytes; no path or URL is ever fetched."""

        row = self._connection.execute(
            "SELECT object_key,content_hash FROM attachments WHERE attachment_id=?",
            (attachment_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown attachment {attachment_id}")
        source = self._attachment_path(row["object_key"])
        try:
            raw = source.read_bytes()
        except OSError as error:
            raise TraceLocalError(f"retained attachment is unavailable: {attachment_id}") from error
        if _sha256_bytes(raw) != row["content_hash"]:
            raise TraceLocalError(f"retained attachment hash mismatch: {attachment_id}")
        return raw

    @staticmethod
    def _event_public_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "sequence": int(row["sequence"]),
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "occurred_at": row["occurred_at"],
            "actor": row["actor"],
            "parent_event_id": row["parent_event_id"],
            "payload": _parse_json(row["payload_json"], {}),
            "payload_hash": row["payload_hash"],
            "origin_event_id": row["origin_event_id"],
            "origin_sequence": row["origin_sequence"],
        }

    def _iter_events(self, *, after_sequence: int = 0, batch_size: int = 1_000) -> Iterable[dict[str, Any]]:
        """Stream immutable events without dropping old lineage at scale."""

        if after_sequence < 0 or batch_size < 1:
            raise ValueError("after_sequence must be non-negative and batch_size must be positive")
        sequence = after_sequence
        while True:
            rows = self._connection.execute(
                "SELECT * FROM events WHERE sequence>? ORDER BY sequence LIMIT ?",
                (sequence, batch_size),
            ).fetchall()
            if not rows:
                return
            for row in rows:
                event = self._event_public_dict(row)
                sequence = event["sequence"]
                yield event

    def events(self, *, after_sequence: int = 0, limit: int = 1_000) -> list[dict[str, Any]]:
        if after_sequence < 0 or limit < 1:
            raise ValueError("after_sequence must be non-negative and limit must be positive")
        return list(islice(self._iter_events(after_sequence=after_sequence), min(limit, 10_000)))

    # --------------------------------------------------------------- retrieval
    def _fts_expression(self, query: str) -> str:
        terms = _text_terms(query)
        escaped = [term.replace('"', '""') for term in terms]
        return " OR ".join(f'"{term}"' for term in escaped)

    def _lexical_candidates(self, query: str, *, collection: str | None, limit: int) -> list[tuple[str, float]]:
        expression = self._fts_expression(query)
        if not expression:
            return []
        if self._fts_available:
            try:
                rows = self._connection.execute(
                    """
                    SELECT f.atom_id, -bm25(lexical_fts,1.0,0.4,0.35,0.35,0.2) AS score
                    FROM lexical_fts f
                    JOIN atoms atom ON atom.atom_id=f.atom_id
                    JOIN documents d ON d.document_id=atom.document_id
                    WHERE lexical_fts MATCH ? AND (? IS NULL OR d.collection_name=?)
                    ORDER BY bm25(lexical_fts) ASC, f.atom_id ASC
                    LIMIT ?
                    """,
                    (expression, collection, collection, limit),
                ).fetchall()
                return [(str(row["atom_id"]), float(row["score"])) for row in rows]
            except sqlite3.OperationalError:
                return self._direct_lexical_candidates(query, collection=collection, limit=limit)
        terms = sorted(set(_text_terms(query)))
        if not terms:
            return []
        marks = ",".join("?" for _ in terms)
        rows = self._connection.execute(
            f"""
            SELECT l.atom_id,SUM(l.frequency) AS score
            FROM lexical_terms l
            JOIN atoms atom ON atom.atom_id=l.atom_id
            JOIN documents d ON d.document_id=atom.document_id
            WHERE l.term IN ({marks}) AND (? IS NULL OR d.collection_name=?)
            GROUP BY l.atom_id
            ORDER BY score DESC,l.atom_id ASC
            LIMIT ?
            """,
            (*terms, collection, collection, limit),
        ).fetchall()
        return [(str(row["atom_id"]), float(row["score"])) for row in rows]

    def _direct_lexical_candidates(self, query: str, *, collection: str | None, limit: int) -> list[tuple[str, float]]:
        """Portable fallback for a platform with a partially working FTS build."""

        terms = sorted(set(_text_terms(query)))
        if not terms:
            return []
        patterns = [f"%{term}%" for term in terms]
        clauses = " OR ".join(
            "(atom.content LIKE ? COLLATE NOCASE OR d.document_name LIKE ? COLLATE NOCASE "
            "OR COALESCE(d.source_url,'') LIKE ? COLLATE NOCASE "
            "OR COALESCE(d.file_uri,'') LIKE ? COLLATE NOCASE "
            "OR d.metadata_json LIKE ? COLLATE NOCASE "
            "OR d.image_descriptions_json LIKE ? COLLATE NOCASE)"
            for _ in patterns
        )
        values: list[Any] = []
        for pattern in patterns:
            values.extend([pattern] * 6)
        rows = self._connection.execute(
            f"""
            SELECT atom.atom_id,atom.content,d.document_name,d.source_url,d.file_uri,
                   d.metadata_json,d.image_descriptions_json
            FROM atoms atom JOIN documents d ON d.document_id=atom.document_id
            WHERE (? IS NULL OR d.collection_name=?) AND ({clauses})
            LIMIT ?
            """,
            (collection, collection, *values, limit * 4),
        ).fetchall()
        scored: list[tuple[str, float]] = []
        for row in rows:
            haystack = " ".join(
                (
                    row["content"],
                    row["document_name"],
                    row["source_url"] or "",
                    row["file_uri"] or "",
                    row["metadata_json"],
                    row["image_descriptions_json"],
                )
            ).casefold()
            score = float(sum(haystack.count(term) for term in terms))
            if score:
                scored.append((str(row["atom_id"]), score))
        return sorted(scored, key=lambda item: (-item[1], item[0]))[:limit]

    @staticmethod
    def _vector_cosine(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right, strict=True))
        denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
        return numerator / denominator if denominator else 0.0

    def _embedding_scores(self, plugin: PluginRef, query: str, rows: Sequence[sqlite3.Row]) -> tuple[dict[str, float], str]:
        loaded = _coerce_plugin(plugin, "embedding")
        texts = [query, *[str(row["content"]) for row in rows]]
        vectors = list(loaded.embed(texts))
        if len(vectors) != len(texts):
            raise ValueError("embedding plugin returned a vector count that does not match its inputs")
        try:
            converted = [[float(value) for value in vector] for vector in vectors]
        except (TypeError, ValueError) as error:
            raise ValueError("embedding plugin returned a non-numeric vector") from error
        if any(any(not math.isfinite(value) for value in vector) for vector in converted):
            raise ValueError("embedding plugin returned non-finite values")
        query_vector = converted[0]
        scores = {
            str(row["atom_id"]): self._vector_cosine(query_vector, vector)
            for row, vector in zip(rows, converted[1:], strict=True)
        }
        return scores, str(getattr(loaded, "provider_id", loaded.__class__.__name__))

    def _rerank_scores(self, plugin: PluginRef, query: str, rows: Sequence[sqlite3.Row]) -> tuple[dict[str, float], str]:
        loaded = _coerce_plugin(plugin, "reranker")
        scores = list(loaded.score(query, [str(row["content"]) for row in rows]))
        if len(scores) != len(rows):
            raise ValueError("reranker plugin returned a score count that does not match its inputs")
        try:
            converted = [float(score) for score in scores]
        except (TypeError, ValueError) as error:
            raise ValueError("reranker plugin returned a non-numeric score") from error
        if any(not math.isfinite(score) for score in converted):
            raise ValueError("reranker plugin returned non-finite values")
        return (
            {str(row["atom_id"]): score for row, score in zip(rows, converted, strict=True)},
            str(getattr(loaded, "provider_id", loaded.__class__.__name__)),
        )

    def _atom_public_dict(
        self,
        row: Mapping[str, Any],
        *,
        score: float | None = None,
        lexical_score: float | None = None,
        embedding_score: float | None = None,
        rerank_score: float | None = None,
    ) -> dict[str, Any]:
        source = {
            "document_id": row["document_id"],
            "document_name": row["document_name"],
            "source_url": row["source_url"],
            "file_uri": row["file_uri"],
            "content_hash": row["declared_content_hash"],
            "stored_content_hash": row["stored_content_hash"],
            "media_type": row["media_type"],
            "metadata": _parse_json(row["metadata_json"], {}),
            "image_descriptions": _parse_json(row["image_descriptions_json"], []),
            "attachment_id": row["attachment_id"],
            "attachment_object_key": row["object_key"],
            "attachment_byte_length": int(row["byte_length"]),
            "created_event_id": row["created_event_id"],
        }
        result = {
            "atom_id": row["atom_id"],
            "collection": row["collection_name"],
            "content": row["content"],
            "content_hash": row["content_hash"],
            "ordinal": int(row["ordinal"]),
            "created_event_id": row["created_event_id"],
            "source": source,
        }
        if score is not None:
            result["score"] = score
            result["channel_scores"] = {
                "lexical": lexical_score or 0.0,
                "embedding": embedding_score or 0.0,
                "rerank": rerank_score or 0.0,
            }
        return result

    def query(
        self,
        query: str,
        *,
        limit: int = 10,
        collection: str | None = None,
        mode: Literal["lexical", "hybrid", "rerank"] = "lexical",
        embedding_plugin: PluginRef | None = None,
        reranker_plugin: PluginRef | None = None,
    ) -> dict[str, Any]:
        """Return raw evidence and citations, never a synthesized answer."""

        if not isinstance(query, str) or not query:
            raise ValueError("query must be a non-empty string")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if collection is not None and (not isinstance(collection, str) or not collection):
            raise ValueError("collection must be a non-empty string when provided")
        if mode not in {"lexical", "hybrid", "rerank"}:
            raise ValueError("mode must be lexical, hybrid, or rerank")
        if mode == "hybrid" and embedding_plugin is None:
            raise ValueError("hybrid retrieval requires an explicitly installed embedding_plugin")
        if mode == "rerank" and reranker_plugin is None:
            raise ValueError("rerank retrieval requires an explicitly installed reranker_plugin")
        cache_key = _canonical_json({"query": query, "limit": limit, "collection": collection, "mode": mode})
        cacheable = mode == "lexical"
        started = time.perf_counter()
        if cacheable and cache_key in self._result_cache:
            cached = json.loads(_canonical_json(self._result_cache[cache_key]))
            cached["cache_hit"] = True
            elapsed_ms = (time.perf_counter() - started) * 1_000
            cached["elapsed_ms"] = round(elapsed_ms, 3)
            self._query_latencies_ms.append(elapsed_ms)
            self._record_query_observation(elapsed_ms=elapsed_ms, mode=mode, cache_hit=True)
            self._result_cache.move_to_end(cache_key)
            return cached

        candidate_limit = min(500, max(limit * 8, 32))
        candidates = self._lexical_candidates(query, collection=collection, limit=candidate_limit)
        rows: list[sqlite3.Row] = []
        lexical_scores: dict[str, float] = {}
        for atom_id, score in candidates:
            row = self._joined_atom_row(atom_id)
            if row is not None:
                rows.append(row)
                lexical_scores[atom_id] = score
        embedding_scores: dict[str, float] = {}
        rerank_scores: dict[str, float] = {}
        plugins: dict[str, str] = {}
        if mode == "hybrid":
            assert embedding_plugin is not None
            embedding_scores, plugins["embedding"] = self._embedding_scores(embedding_plugin, query, rows)
        if mode == "rerank":
            assert reranker_plugin is not None
            rerank_scores, plugins["reranker"] = self._rerank_scores(reranker_plugin, query, rows)

        def combined_score(row: sqlite3.Row) -> float:
            atom_id = str(row["atom_id"])
            lexical = lexical_scores.get(atom_id, 0.0)
            if mode == "hybrid":
                return lexical + max(0.0, embedding_scores.get(atom_id, 0.0))
            if mode == "rerank":
                return rerank_scores.get(atom_id, 0.0)
            return lexical

        ordered = sorted(rows, key=lambda row: (-combined_score(row), str(row["atom_id"])))[:limit]
        results = [
            self._atom_public_dict(
                row,
                score=combined_score(row),
                lexical_score=lexical_scores.get(str(row["atom_id"]), 0.0),
                embedding_score=embedding_scores.get(str(row["atom_id"]), 0.0),
                rerank_score=rerank_scores.get(str(row["atom_id"]), 0.0),
            )
            for row in ordered
        ]
        elapsed_ms = (time.perf_counter() - started) * 1_000
        self._query_latencies_ms.append(elapsed_ms)
        self._record_query_observation(elapsed_ms=elapsed_ms, mode=mode, cache_hit=False)
        response = {
            "query": query, "collection": collection, "mode": mode, "plugins": plugins,
            "candidate_limit": candidate_limit, "result_count": len(results),
            "sufficiency_state": "answerable" if results else "insufficient_evidence",
            "results": results, "elapsed_ms": round(elapsed_ms, 3), "cache_hit": False,
        }
        if cacheable:
            self._result_cache[cache_key] = json.loads(_canonical_json(response))
            self._trim_cache(self.resource_snapshot().pressure)
        return response

    # --------------------------------------------------------- review control
    def _validate_evidence_atom_ids(self, atom_ids: Sequence[str]) -> list[str]:
        if not atom_ids:
            raise RecordValidationError("at least one immutable source atom is required as evidence")
        validated: list[str] = []
        seen: set[str] = set()
        for atom_id in atom_ids:
            if not isinstance(atom_id, str) or not atom_id:
                raise RecordValidationError("evidence atom IDs must be non-empty strings")
            if atom_id in seen:
                continue
            if self._joined_atom_row(atom_id) is None:
                raise RecordValidationError(f"evidence atom does not exist: {atom_id}")
            seen.add(atom_id)
            validated.append(atom_id)
        return validated

    def propose(
        self,
        proposal_type: str,
        candidate: Mapping[str, Any],
        evidence_atom_ids: Sequence[str],
        *,
        actor: str = "local-user",
    ) -> dict[str, Any]:
        """Create a review-required derived proposal.

        Relations, schemas, factual claims, and feedback-derived topology are
        always pending. Retrieval feedback therefore cannot mutate topology.
        """

        if not isinstance(proposal_type, str) or not proposal_type:
            raise RecordValidationError("proposal_type must be a non-empty string")
        candidate_value = _safe_json_object(candidate, field="candidate")
        evidence = self._validate_evidence_atom_ids(evidence_atom_ids)
        self._ensure_write_capacity(32 * 1024, purpose="proposal creation")
        proposal_id = str(uuid4())
        with self._transaction() as connection:
            event = self._append_event(
                connection,
                "proposal.created",
                {
                    "proposal_id": proposal_id,
                    "proposal_type": proposal_type,
                    "evidence_atom_ids": evidence,
                },
                actor=actor,
            )
            connection.execute(
                """
                INSERT INTO proposals(
                    proposal_id,proposal_type,candidate_json,evidence_atom_ids_json,status,
                    actor,reviewer,decision_reason,created_event_id,decided_event_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    proposal_id, proposal_type, _canonical_json(candidate_value), _canonical_json(evidence),
                    "pending", actor, None, None, event["event_id"], None,
                ),
            )
        return self.get_proposal(proposal_id)

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        row = self._connection.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown proposal {proposal_id}")
        return {
            "proposal_id": row["proposal_id"],
            "proposal_type": row["proposal_type"],
            "candidate": _parse_json(row["candidate_json"], {}),
            "evidence_atom_ids": _parse_json(row["evidence_atom_ids_json"], []),
            "status": row["status"],
            "actor": row["actor"],
            "reviewer": row["reviewer"],
            "decision_reason": row["decision_reason"],
            "created_event_id": row["created_event_id"],
            "decided_event_id": row["decided_event_id"],
        }

    def list_proposals(self, *, status: str | None = None, proposal_type: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if status is not None:
            clauses.append("status=?")
            values.append(status)
        if proposal_type is not None:
            clauses.append("proposal_type=?")
            values.append(proposal_type)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._connection.execute(f"SELECT proposal_id FROM proposals{where} ORDER BY rowid", values).fetchall()
        return [self.get_proposal(str(row["proposal_id"])) for row in rows]

    def _validated_navigation_sections(self, candidate: Mapping[str, Any], evidence: Sequence[str]) -> tuple[str, list[dict[str, str]]]:
        title = candidate.get("title", "Source navigation")
        if not isinstance(title, str) or not title:
            raise RecordValidationError("navigation summary title must be a non-empty string")
        sections = candidate.get("sections")
        if not isinstance(sections, list) or not sections:
            raise RecordValidationError("navigation summaries require non-empty extractive sections")
        allowed = set(evidence)
        validated: list[dict[str, str]] = []
        used: set[str] = set()
        for section in sections:
            if not isinstance(section, Mapping):
                raise RecordValidationError("navigation summary sections must be objects")
            atom_id, excerpt = section.get("atom_id"), section.get("excerpt")
            if atom_id not in allowed:
                raise RecordValidationError("navigation summary section must cite one of its evidence atoms")
            if not isinstance(excerpt, str) or not excerpt:
                raise RecordValidationError("navigation summary excerpts must be non-empty strings")
            atom = self.get_atom(str(atom_id))
            if excerpt not in atom["content"]:
                raise RecordValidationError("navigation summary excerpts must be exact source spans")
            validated.append({"atom_id": str(atom_id), "excerpt": excerpt})
            used.add(str(atom_id))
        if not used:
            raise RecordValidationError("navigation summary needs at least one source anchor")
        return title, validated

    def _publish_navigation_summary(
        self,
        connection: sqlite3.Connection,
        *,
        title: str,
        sections: Sequence[Mapping[str, str]],
        evidence: Sequence[str],
        actor: str,
        proposal_id: str | None,
        parent_event_id: str | None = None,
    ) -> dict[str, Any]:
        summary_id = str(uuid4())
        event = self._append_event(
            connection,
            "navigation_summary.published",
            {
                "summary_id": summary_id,
                "proposal_id": proposal_id,
                "title": title,
                "evidence_atom_ids": list(evidence),
                "section_count": len(sections),
            },
            actor=actor,
            parent_event_id=parent_event_id,
        )
        connection.execute(
            """
            INSERT INTO navigation_summaries(
                summary_id,proposal_id,title,sections_json,evidence_atom_ids_json,
                published_event_id,published_by
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                summary_id, proposal_id, title, _canonical_json(list(sections)),
                _canonical_json(list(evidence)), event["event_id"], actor,
            ),
        )
        return {
            "summary_id": summary_id,
            "proposal_id": proposal_id,
            "title": title,
            "sections": list(sections),
            "evidence_atom_ids": list(evidence),
            "published_event_id": event["event_id"],
            "published_by": actor,
        }

    def publish_navigation_summary(
        self,
        *,
        title: str,
        sections: Sequence[Mapping[str, str]],
        evidence_atom_ids: Sequence[str],
        actor: str = "system",
    ) -> dict[str, Any]:
        """Auto-publish only an exact-source, navigation-only summary."""

        evidence = self._validate_evidence_atom_ids(evidence_atom_ids)
        safe_title, safe_sections = self._validated_navigation_sections(
            {"title": title, "sections": list(sections)}, evidence
        )
        self._ensure_write_capacity(32 * 1024, purpose="navigation summary")
        with self._transaction() as connection:
            return self._publish_navigation_summary(
                connection,
                title=safe_title,
                sections=safe_sections,
                evidence=evidence,
                actor=actor,
                proposal_id=None,
            )

    def generate_navigation_summary(
        self,
        atom_ids: Sequence[str],
        *,
        title: str | None = None,
        max_excerpt_characters: int = 280,
        actor: str = "system",
    ) -> dict[str, Any]:
        """Build a deterministic extractive navigation view from raw evidence."""

        if not 1 <= max_excerpt_characters <= 4_000:
            raise ValueError("max_excerpt_characters must be between 1 and 4000")
        evidence = self._validate_evidence_atom_ids(atom_ids)
        sections = [
            {"atom_id": atom_id, "excerpt": self.get_atom(atom_id)["content"][:max_excerpt_characters]}
            for atom_id in evidence
        ]
        return self.publish_navigation_summary(
            title=title or f"Navigation across {len(evidence)} source atoms",
            sections=sections,
            evidence_atom_ids=evidence,
            actor=actor,
        )

    def review_proposal(
        self,
        proposal_id: str,
        *,
        decision: Literal["approved", "rejected"],
        reviewer: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Record a human review; no proposal is promoted by retrieval feedback."""

        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        if not reviewer:
            raise RecordValidationError("reviewer must be a non-empty string")
        self._ensure_write_capacity(32 * 1024, purpose="proposal review")
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown proposal {proposal_id}")
            if row["status"] != "pending":
                raise TraceLocalError(f"proposal is already {row['status']}")
            evidence = self._validate_evidence_atom_ids(_parse_json(row["evidence_atom_ids_json"], []))
            candidate = _parse_json(row["candidate_json"], {})
            event = self._append_event(
                connection,
                f"proposal.{decision}",
                {
                    "proposal_id": proposal_id,
                    "proposal_type": row["proposal_type"],
                    "evidence_atom_ids": evidence,
                    "reason": reason,
                },
                actor=reviewer,
                parent_event_id=row["created_event_id"],
            )
            connection.execute(
                """
                UPDATE proposals SET status=?,reviewer=?,decision_reason=?,decided_event_id=?
                WHERE proposal_id=?
                """,
                (decision, reviewer, reason, event["event_id"], proposal_id),
            )
            summary: dict[str, Any] | None = None
            if decision == "approved" and row["proposal_type"] == "navigation_summary":
                title, sections = self._validated_navigation_sections(candidate, evidence)
                summary = self._publish_navigation_summary(
                    connection,
                    title=title,
                    sections=sections,
                    evidence=evidence,
                    actor=reviewer,
                    proposal_id=proposal_id,
                    parent_event_id=event["event_id"],
                )
        result = self.get_proposal(proposal_id)
        if summary is not None:
            result["navigation_summary"] = summary
        return result

    def list_navigation_summaries(self) -> list[dict[str, Any]]:
        rows = self._connection.execute("SELECT * FROM navigation_summaries ORDER BY rowid").fetchall()
        return [
            {
                "summary_id": row["summary_id"],
                "proposal_id": row["proposal_id"],
                "title": row["title"],
                "sections": _parse_json(row["sections_json"], []),
                "evidence_atom_ids": _parse_json(row["evidence_atom_ids_json"], []),
                "published_event_id": row["published_event_id"],
                "published_by": row["published_by"],
            }
            for row in rows
        ]

    # -------------------------------------------------------- work/projection
    def _enqueue_work(self, *, kind: str, payload: Mapping[str, Any], detail: str | None = None) -> dict[str, Any]:
        work_id = str(uuid4())
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO work_queue(work_id,kind,payload_json,status,created_at,completed_at,detail) VALUES(?,?,?,?,?,?,?)",
                (work_id, kind, _canonical_json(dict(payload)), "queued", _utc_now(), None, detail),
            )
        return {"work_id": work_id, "kind": kind, "status": "queued", "detail": detail}

    def schedule_organization(self, *, atom_ids: Sequence[str], kind: str = "organization.scan") -> dict[str, Any]:
        """Queue a bounded review-only organization task."""

        evidence = self._validate_evidence_atom_ids(atom_ids)
        self._ensure_write_capacity(16 * 1024, purpose="organization queue")
        return self._enqueue_work(kind=kind, payload={"atom_ids": evidence})

    def _canonical_atom_hash(self) -> str:
        rows = self._connection.execute("SELECT atom_id,content_hash FROM atoms ORDER BY atom_id").fetchall()
        joined = "\n".join(f"{row['atom_id']}:{row['content_hash']}" for row in rows)
        return _sha256_text(joined)

    def _rebuild_projection(self, *, force: bool, actor: str, record_event: bool) -> dict[str, Any]:
        atom_count = self._atom_count()
        character_row = self._connection.execute("SELECT COALESCE(SUM(length(content)),0) AS chars FROM atoms").fetchone()
        estimated_bytes = max(64 * 1024, int(character_row["chars"]) * 2)
        if not force:
            self._ensure_background_capacity(purpose="projection.rebuild", estimated_bytes=estimated_bytes)
        else:
            self._ensure_write_capacity(estimated_bytes, purpose="projection.rebuild")
        before_size = self._database_bytes()
        with self._transaction() as connection:
            if self._fts_available:
                connection.execute("DELETE FROM lexical_fts")
            else:
                connection.execute("DELETE FROM lexical_terms")
            rows = connection.execute(
                """
                SELECT atom.atom_id,atom.content,d.document_name,d.source_url,d.file_uri,
                       d.metadata_json,d.image_descriptions_json
                FROM atoms atom JOIN documents d ON d.document_id=atom.document_id
                ORDER BY atom.atom_id
                """
            ).fetchall()
            for row in rows:
                self._index_atom(
                    connection,
                    {
                        "atom_id": row["atom_id"],
                        "content": row["content"],
                        "document_name": row["document_name"],
                        "source_url": row["source_url"],
                        "file_uri": row["file_uri"],
                        "metadata": _parse_json(row["metadata_json"], {}),
                        "image_descriptions": _parse_json(row["image_descriptions_json"], []),
                    },
                )
            indexed_count = self._projection_count()
            parity = indexed_count == atom_count
            if not parity:
                raise ProjectionError(
                    f"lexical projection parity failed: indexed {indexed_count}, canonical {atom_count}"
                )
            prior = connection.execute(
                "SELECT revision FROM projection_state WHERE projection_name='lexical'"
            ).fetchone()
            revision = (int(prior["revision"]) if prior else 0) + 1
            state = {
                "revision": revision,
                "atom_count": atom_count,
                "canonical_hash": self._canonical_atom_hash(),
                "indexed_at": _utc_now(),
                "index_growth_bytes": max(0, self._database_bytes() - before_size),
            }
            connection.execute(
                """
                INSERT INTO projection_state(
                    projection_name,revision,atom_count,canonical_hash,indexed_at,index_growth_bytes
                ) VALUES('lexical',?,?,?,?,?)
                ON CONFLICT(projection_name) DO UPDATE SET
                    revision=excluded.revision,atom_count=excluded.atom_count,
                    canonical_hash=excluded.canonical_hash,indexed_at=excluded.indexed_at,
                    index_growth_bytes=excluded.index_growth_bytes
                """,
                (
                    state["revision"], state["atom_count"], state["canonical_hash"],
                    state["indexed_at"], state["index_growth_bytes"],
                ),
            )
            event: dict[str, Any] | None = None
            if record_event:
                event = self._append_event(
                    connection,
                    "projection.rebuilt",
                    {"projection": "lexical", **state, "parity": parity},
                    actor=actor,
                )
            connection.execute(
                "UPDATE work_queue SET status='completed',completed_at=?,detail='completed by projection rebuild' WHERE status='queued' AND kind='projection.rebuild'",
                (_utc_now(),),
            )
        self._clear_query_cache()
        return {
            "status": "completed",
            "projection": "lexical",
            "canonical_atom_count": atom_count,
            "indexed_atom_count": indexed_count,
            "parity": parity,
            **state,
            "event_id": event["event_id"] if event else None,
        }

    def rebuild_projections(self, *, actor: str = "local-user") -> dict[str, Any]:
        """Rebuild replaceable lexical state from immutable canonical atoms."""

        try:
            return self._rebuild_projection(force=False, actor=actor, record_event=True)
        except CapacityError as error:
            return {
                "status": "deferred",
                "retryable": True,
                "retry_after_seconds": error.retry_after_seconds,
                "capacity": error.status,
            }

    def run_queued_work(self, *, limit: int = 1, actor: str = "local-user") -> dict[str, Any]:
        """Run only resource-safe queued local work."""

        if limit < 1:
            raise ValueError("limit must be positive")
        snapshot = self.resource_snapshot()
        if snapshot.pressure != "normal":
            return {
                "status": "deferred",
                "processed": 0,
                "queue_depth": snapshot.queue_depth,
                "reason": f"resource pressure is {snapshot.pressure}",
            }
        rows = self._connection.execute(
            "SELECT * FROM work_queue WHERE status='queued' ORDER BY created_at LIMIT ?",
            (limit,),
        ).fetchall()
        completed: list[dict[str, Any]] = []
        for row in rows:
            if row["kind"] == "projection.rebuild":
                completed.append(self._rebuild_projection(force=False, actor=actor, record_event=True))
                continue
            with self._transaction() as connection:
                connection.execute(
                    "UPDATE work_queue SET status='waiting_review',detail=? WHERE work_id=? AND status='queued'",
                    ("requires explicit reviewer or local organization extension", row["work_id"]),
                )
            completed.append({"work_id": row["work_id"], "status": "waiting_review", "kind": row["kind"]})
        return {
            "status": "completed",
            "processed": len(completed),
            "items": completed,
            "queue_depth": self._queue_depth(),
        }

    # -------------------------------------------------------------- portability
    @staticmethod
    def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
        return "".join(_canonical_json(dict(row)) + "\n" for row in rows).encode("utf-8")

    @staticmethod
    def _write_jsonl(archive: zipfile.ZipFile, member: str, rows: Iterable[Mapping[str, Any]]) -> None:
        """Write JSONL incrementally so event history is never truncated by RAM."""

        with archive.open(member, "w") as destination:
            for row in rows:
                destination.write((_canonical_json(dict(row)) + "\n").encode("utf-8"))

    @staticmethod
    def _read_jsonl(raw: bytes, *, member: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as error:
                raise ImportBundleError(f"invalid JSON in {member} line {line_number}") from error
            if not isinstance(parsed, dict):
                raise ImportBundleError(f"{member} line {line_number} must be an object")
            records.append(parsed)
        return records

    def _export_documents(self) -> list[dict[str, Any]]:
        rows = self._connection.execute("SELECT * FROM documents ORDER BY document_id").fetchall()
        return [
            {
                "document_id": row["document_id"],
                "document_name": row["document_name"],
                "source_url": row["source_url"],
                "file_uri": row["file_uri"],
                "collection_name": row["collection_name"],
                "declared_content_hash": row["declared_content_hash"],
                "stored_content_hash": row["stored_content_hash"],
                "media_type": row["media_type"],
                "metadata": _parse_json(row["metadata_json"], {}),
                "image_descriptions": _parse_json(row["image_descriptions_json"], []),
                "raw_record": _parse_json(row["raw_record_json"], {}),
                "record_hash": row["record_hash"],
                "external_id": row["external_id"],
                "created_event_id": row["created_event_id"],
            }
            for row in rows
        ]

    def _export_attachments(self) -> list[dict[str, Any]]:
        rows = self._connection.execute("SELECT * FROM attachments ORDER BY attachment_id").fetchall()
        return [
            {
                "attachment_id": row["attachment_id"],
                "document_id": row["document_id"],
                "object_key": row["object_key"],
                "content_hash": row["content_hash"],
                "media_type": row["media_type"],
                "byte_length": int(row["byte_length"]),
                "created_event_id": row["created_event_id"],
                "archive_member": f"attachments/{row['content_hash']}",
            }
            for row in rows
        ]

    def _export_atoms(self) -> list[dict[str, Any]]:
        rows = self._connection.execute("SELECT * FROM atoms ORDER BY atom_id").fetchall()
        return [
            {
                "atom_id": row["atom_id"],
                "document_id": row["document_id"],
                "attachment_id": row["attachment_id"],
                "ordinal": int(row["ordinal"]),
                "content": row["content"],
                "content_hash": row["content_hash"],
                "created_event_id": row["created_event_id"],
            }
            for row in rows
        ]

    def _export_proposals(self) -> list[dict[str, Any]]:
        return [self.get_proposal(str(row["proposal_id"])) for row in self._connection.execute(
            "SELECT proposal_id FROM proposals ORDER BY proposal_id"
        ).fetchall()]

    def export(
        self,
        destination: str | os.PathLike[str],
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Write a portable event and source bundle without deleting local data."""

        target = Path(destination)
        if target.exists() and not overwrite:
            raise FileExistsError(f"export destination already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        documents = self._export_documents()
        attachments = self._export_attachments()
        atoms = self._export_atoms()
        proposals = self._export_proposals()
        summaries = self.list_navigation_summaries()
        event_count = int(self._connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()["count"])
        manifest = {
            "format": EXPORT_FORMAT,
            "schema_version": EXPORT_SCHEMA_VERSION,
            "created_at": _utc_now(),
            "offline_only": True,
            "canonical_contract": "trace.local.v1",
            "counts": {
                "events": event_count,
                "documents": len(documents),
                "attachments": len(attachments),
                "atoms": len(atoms),
                "proposals": len(proposals),
                "navigation_summaries": len(summaries),
            },
            "attachments": [
                {
                    "attachment_id": item["attachment_id"],
                    "archive_member": item["archive_member"],
                    "content_hash": item["content_hash"],
                    "byte_length": item["byte_length"],
                }
                for item in attachments
            ],
        }
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".trace-export-", suffix=".zip", delete=False) as temporary:
                temporary_path = Path(temporary.name)
            with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                archive.writestr("manifest.json", _canonical_json(manifest))
                self._write_jsonl(archive, "events.jsonl", self._iter_events())
                archive.writestr("documents.jsonl", self._jsonl_bytes(documents))
                archive.writestr("attachments.jsonl", self._jsonl_bytes(attachments))
                archive.writestr("atoms.jsonl", self._jsonl_bytes(atoms))
                archive.writestr("proposals.jsonl", self._jsonl_bytes(proposals))
                archive.writestr("navigation_summaries.jsonl", self._jsonl_bytes(summaries))
                for attachment in attachments:
                    raw = self.get_attachment(attachment["attachment_id"])
                    archive.writestr(attachment["archive_member"], raw)
            if target.exists() and not overwrite:
                raise FileExistsError(f"export destination already exists: {target}")
            os.replace(temporary_path, target)
            temporary_path = None
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
        return {
            "path": str(target),
            "format": EXPORT_FORMAT,
            "schema_version": EXPORT_SCHEMA_VERSION,
            "counts": manifest["counts"],
        }

    @staticmethod
    def _safe_archive_members(archive: zipfile.ZipFile) -> set[str]:
        members: set[str] = set()
        for info in archive.infolist():
            path = Path(info.filename)
            if info.filename.startswith(("/", "\\")) or ".." in path.parts:
                raise ImportBundleError("archive contains an unsafe member path")
            if info.is_dir():
                continue
            if info.filename in members:
                raise ImportBundleError(f"archive contains duplicate member {info.filename}")
            members.add(info.filename)
        return members

    def _read_bundle(self, source: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, bytes]]:
        required = {
            "manifest.json",
            "events.jsonl",
            "documents.jsonl",
            "attachments.jsonl",
            "atoms.jsonl",
            "proposals.jsonl",
            "navigation_summaries.jsonl",
        }
        try:
            with zipfile.ZipFile(source, "r") as archive:
                members = self._safe_archive_members(archive)
                missing = required - members
                if missing:
                    raise ImportBundleError("archive is missing " + ", ".join(sorted(missing)))
                try:
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ImportBundleError("manifest.json is invalid") from error
                if not isinstance(manifest, dict) or manifest.get("format") != EXPORT_FORMAT:
                    raise ImportBundleError("archive is not a Trace Phase 1 export")
                if manifest.get("schema_version") != EXPORT_SCHEMA_VERSION:
                    raise ImportBundleError("unsupported Trace export schema version")
                rows = {
                    member.removesuffix(".jsonl"): self._read_jsonl(archive.read(member), member=member)
                    for member in required
                    if member.endswith(".jsonl")
                }
                attachment_bytes: dict[str, bytes] = {}
                for attachment in rows["attachments"]:
                    member = attachment.get("archive_member")
                    if not isinstance(member, str) or member not in members:
                        raise ImportBundleError("archive is missing an attachment payload")
                    raw = archive.read(member)
                    if _sha256_bytes(raw) != attachment.get("content_hash"):
                        raise ImportBundleError(f"attachment hash mismatch for {attachment.get('attachment_id')}")
                    if len(raw) != int(attachment.get("byte_length", -1)):
                        raise ImportBundleError(f"attachment byte length mismatch for {attachment.get('attachment_id')}")
                    attachment_bytes[str(attachment["attachment_id"])] = raw
        except (OSError, zipfile.BadZipFile) as error:
            raise ImportBundleError(f"cannot read export archive: {error}") from error
        return manifest, rows, attachment_bytes

    @staticmethod
    def _required(row: Mapping[str, Any], *names: str) -> None:
        missing = [name for name in names if name not in row]
        if missing:
            raise ImportBundleError("archive row missing " + ", ".join(missing))

    def _validate_import_rows(
        self,
        manifest: Mapping[str, Any],
        rows: Mapping[str, list[dict[str, Any]]],
        attachment_bytes: Mapping[str, bytes],
    ) -> None:
        """Reject a bundle whose ledger rows do not describe the retained source.

        A hash-valid zip alone is not sufficient: a malformed archive must not
        pair one atom with a different attachment or publish a navigation span
        that the canonical source does not contain.
        """

        count_keys = {
            "events": "events",
            "documents": "documents",
            "attachments": "attachments",
            "atoms": "atoms",
            "proposals": "proposals",
            "navigation_summaries": "navigation_summaries",
        }
        counts = manifest.get("counts")
        if not isinstance(counts, Mapping):
            raise ImportBundleError("archive manifest has no valid counts")
        for manifest_key, row_key in count_keys.items():
            if not isinstance(counts.get(manifest_key), int) or counts[manifest_key] != len(rows[row_key]):
                raise ImportBundleError(f"archive manifest count does not match {manifest_key}")

        documents_by_id: dict[str, dict[str, Any]] = {}
        normalized_by_document: dict[str, _NormalizedRecord] = {}
        for document in rows["documents"]:
            self._required(
                document,
                "document_id", "document_name", "collection_name", "declared_content_hash",
                "stored_content_hash", "media_type", "metadata", "image_descriptions",
                "raw_record", "record_hash", "created_event_id",
            )
            document_id = document["document_id"]
            if not isinstance(document_id, str) or not document_id or document_id in documents_by_id:
                raise ImportBundleError("archive has invalid or duplicate document IDs")
            if (
                not isinstance(document["document_name"], str)
                or not document["document_name"]
                or not isinstance(document["collection_name"], str)
                or not document["collection_name"]
                or not isinstance(document["declared_content_hash"], str)
                or not document["declared_content_hash"]
                or not isinstance(document["stored_content_hash"], str)
                or not document["stored_content_hash"]
                or not isinstance(document["media_type"], str)
                or not document["media_type"]
                or not isinstance(document["record_hash"], str)
                or not document["record_hash"]
                or not isinstance(document["created_event_id"], str)
                or not document["created_event_id"]
            ):
                raise ImportBundleError("archive has an invalid document field")
            source_url, file_uri = document.get("source_url"), document.get("file_uri")
            if source_url is not None and not isinstance(source_url, str):
                raise ImportBundleError("archive document source_url must be text")
            if file_uri is not None and not isinstance(file_uri, str):
                raise ImportBundleError("archive document file_uri must be text")
            if source_url is None and file_uri is None:
                raise ImportBundleError("archive document needs a source URL or file URI")
            _safe_json_object(document["metadata"], field="metadata")
            _safe_json_list(document["image_descriptions"], field="image_descriptions")
            raw_record = _safe_json_object(document["raw_record"], field="raw_record")
            try:
                normalized = _normalize_record(raw_record)
            except (RecordValidationError, TypeError, ValueError) as error:
                raise ImportBundleError("archive document raw record is not a valid Phase 1 source") from error
            if (
                normalized.document_name != document["document_name"]
                or normalized.source_url != source_url
                or normalized.file_uri != file_uri
                or normalized.collection != document["collection_name"]
                or normalized.content_hash != document["declared_content_hash"]
                or normalized.media_type != document["media_type"]
                or normalized.metadata != document["metadata"]
                or normalized.image_descriptions != document["image_descriptions"]
                or normalized.external_id != document.get("external_id")
                or normalized.record_hash != document["record_hash"]
            ):
                raise ImportBundleError("archive document does not match its raw source record")
            documents_by_id[document_id] = document
            normalized_by_document[document_id] = normalized

        attachments_by_id: dict[str, dict[str, Any]] = {}
        attachment_by_document: dict[str, str] = {}
        for attachment in rows["attachments"]:
            self._required(
                attachment,
                "attachment_id", "document_id", "content_hash", "media_type",
                "byte_length", "created_event_id",
            )
            attachment_id, document_id = attachment["attachment_id"], attachment["document_id"]
            if (
                not isinstance(attachment_id, str)
                or not attachment_id
                or attachment_id in attachments_by_id
                or not isinstance(document_id, str)
                or document_id not in documents_by_id
                or document_id in attachment_by_document
                or not isinstance(attachment["content_hash"], str)
                or not attachment["content_hash"]
                or not isinstance(attachment["media_type"], str)
                or not attachment["media_type"]
                or not isinstance(attachment["byte_length"], int)
                or attachment["byte_length"] < 0
                or not isinstance(attachment["created_event_id"], str)
                or not attachment["created_event_id"]
            ):
                raise ImportBundleError("archive has invalid attachment references")
            raw = attachment_bytes.get(attachment_id)
            if raw is None:
                raise ImportBundleError(f"archive attachment payload is unavailable: {attachment_id}")
            if _sha256_bytes(raw) != attachment["content_hash"] or len(raw) != attachment["byte_length"]:
                raise ImportBundleError(f"archive attachment does not match its declared bytes: {attachment_id}")
            document = documents_by_id[document_id]
            if (
                attachment["content_hash"] != document["stored_content_hash"]
                or attachment["media_type"] != document["media_type"]
            ):
                raise ImportBundleError("archive attachment does not match its document provenance")
            attachments_by_id[attachment_id] = attachment
            attachment_by_document[document_id] = attachment_id

        atoms_by_id: dict[str, dict[str, Any]] = {}
        atom_by_document: dict[str, str] = {}
        for atom in rows["atoms"]:
            self._required(atom, "atom_id", "document_id", "attachment_id", "ordinal", "content", "content_hash", "created_event_id")
            atom_id, document_id, attachment_id = atom["atom_id"], atom["document_id"], atom["attachment_id"]
            if (
                not isinstance(atom_id, str)
                or not atom_id
                or atom_id in atoms_by_id
                or not isinstance(document_id, str)
                or document_id not in documents_by_id
                or document_id in atom_by_document
                or not isinstance(attachment_id, str)
                or attachment_id not in attachments_by_id
                or attachment_by_document.get(document_id) != attachment_id
                or not isinstance(atom["ordinal"], int)
                or atom["ordinal"] != 0
                or not isinstance(atom["content"], str)
                or not atom["content"]
                or not isinstance(atom["content_hash"], str)
                or not atom["content_hash"]
                or not isinstance(atom["created_event_id"], str)
                or not atom["created_event_id"]
            ):
                raise ImportBundleError("archive has invalid atom references")
            raw = attachment_bytes[attachment_id]
            normalized = normalized_by_document[document_id]
            if (
                raw != atom["content"].encode("utf-8")
                or _sha256_bytes(raw) != atom["content_hash"]
                or atom["content_hash"] != attachments_by_id[attachment_id]["content_hash"]
                or atom["content_hash"] != documents_by_id[document_id]["stored_content_hash"]
                or atom["content"] != normalized.content
            ):
                raise ImportBundleError("archive atom does not match its retained source attachment")
            atoms_by_id[atom_id] = atom
            atom_by_document[document_id] = atom_id
        if set(documents_by_id) != set(atom_by_document):
            raise ImportBundleError("archive has a document without exactly one immutable source atom")
        if set(documents_by_id) != set(attachment_by_document):
            raise ImportBundleError("archive has a document without exactly one retained attachment")

        seen_events: set[str] = set()
        for event in rows["events"]:
            self._required(event, "event_id", "event_type", "occurred_at", "actor", "payload", "payload_hash")
            event_id = event["event_id"]
            if (
                not isinstance(event_id, str)
                or not event_id
                or event_id in seen_events
                or not isinstance(event["event_type"], str)
                or not event["event_type"]
                or not isinstance(event["occurred_at"], str)
                or not event["occurred_at"]
                or not isinstance(event["actor"], str)
                or not event["actor"]
                or not isinstance(event["payload"], Mapping)
                or not isinstance(event["payload_hash"], str)
                or not event["payload_hash"]
            ):
                raise ImportBundleError("archive has an invalid event")
            seen_events.add(event_id)
            if _sha256_text(_canonical_json(event["payload"])) != event["payload_hash"]:
                raise ImportBundleError(f"event payload hash mismatch for {event_id}")
        for event in rows["events"]:
            for field in ("parent_event_id", "origin_event_id"):
                value = event.get(field)
                if value is not None and (not isinstance(value, str) or value not in seen_events):
                    raise ImportBundleError(f"archive event has an invalid {field}")

        proposal_ids: set[str] = set()
        for proposal in rows["proposals"]:
            self._required(proposal, "proposal_id", "proposal_type", "candidate", "evidence_atom_ids", "status", "actor", "created_event_id")
            proposal_id = proposal["proposal_id"]
            if (
                not isinstance(proposal_id, str)
                or not proposal_id
                or proposal_id in proposal_ids
                or not isinstance(proposal["proposal_type"], str)
                or not proposal["proposal_type"]
                or proposal["status"] not in {"pending", "approved", "rejected"}
                or not isinstance(proposal["actor"], str)
                or not proposal["actor"]
                or not isinstance(proposal["created_event_id"], str)
                or proposal["created_event_id"] not in seen_events
            ):
                raise ImportBundleError("archive has an invalid proposal")
            _safe_json_object(proposal["candidate"], field="candidate")
            evidence = proposal["evidence_atom_ids"]
            if (
                not isinstance(evidence, list)
                or not evidence
                or any(not isinstance(atom_id, str) for atom_id in evidence)
                or not set(evidence).issubset(atoms_by_id)
            ):
                raise ImportBundleError("archive proposal has invalid evidence references")
            decided_event_id = proposal.get("decided_event_id")
            if proposal["status"] == "pending":
                if decided_event_id is not None:
                    raise ImportBundleError("pending archive proposal cannot have a review event")
            elif not isinstance(decided_event_id, str) or decided_event_id not in seen_events:
                raise ImportBundleError("reviewed archive proposal needs a valid review event")
            proposal_ids.add(proposal_id)

        for summary in rows["navigation_summaries"]:
            self._required(summary, "summary_id", "title", "sections", "evidence_atom_ids", "published_event_id", "published_by")
            if (
                not isinstance(summary["summary_id"], str)
                or not summary["summary_id"]
                or not isinstance(summary["title"], str)
                or not summary["title"]
                or not isinstance(summary["published_event_id"], str)
                or summary["published_event_id"] not in seen_events
                or not isinstance(summary["published_by"], str)
                or not summary["published_by"]
                or summary.get("proposal_id") is not None
                and summary["proposal_id"] not in proposal_ids
            ):
                raise ImportBundleError("archive navigation summary has invalid provenance")
            evidence = summary["evidence_atom_ids"]
            if (
                not isinstance(evidence, list)
                or not evidence
                or any(not isinstance(atom_id, str) for atom_id in evidence)
                or not set(evidence).issubset(atoms_by_id)
            ):
                raise ImportBundleError("archive navigation summary has invalid evidence references")
            sections = summary["sections"]
            if not isinstance(sections, list) or not sections:
                raise ImportBundleError("archive navigation summary needs extractive sections")
            allowed = set(evidence)
            for section in sections:
                if not isinstance(section, Mapping):
                    raise ImportBundleError("archive navigation summary section must be an object")
                atom_id, excerpt = section.get("atom_id"), section.get("excerpt")
                if (
                    not isinstance(atom_id, str)
                    or atom_id not in allowed
                    or not isinstance(excerpt, str)
                    or not excerpt
                    or excerpt not in atoms_by_id[atom_id]["content"]
                ):
                    raise ImportBundleError("archive navigation summary is not anchored to an exact source span")

        for document in documents_by_id.values():
            if document["created_event_id"] not in seen_events:
                raise ImportBundleError("archive document has no creation event")
        for attachment in attachments_by_id.values():
            if attachment["created_event_id"] not in seen_events:
                raise ImportBundleError("archive attachment has no creation event")
        for atom in atoms_by_id.values():
            if atom["created_event_id"] not in seen_events:
                raise ImportBundleError("archive atom has no creation event")

        declared_attachments = manifest.get("attachments")
        if not isinstance(declared_attachments, list):
            raise ImportBundleError("archive manifest has no valid attachment inventory")
        manifest_attachments: dict[str, Mapping[str, Any]] = {}
        for item in declared_attachments:
            if not isinstance(item, Mapping):
                raise ImportBundleError("archive manifest attachment inventory is invalid")
            self._required(item, "attachment_id", "archive_member", "content_hash", "byte_length")
            attachment_id = item["attachment_id"]
            if not isinstance(attachment_id, str) or attachment_id in manifest_attachments:
                raise ImportBundleError("archive manifest has duplicate attachment IDs")
            manifest_attachments[attachment_id] = item
        if set(manifest_attachments) != set(attachments_by_id):
            raise ImportBundleError("archive manifest attachment inventory does not match ledger rows")
        for attachment_id, attachment in attachments_by_id.items():
            item = manifest_attachments[attachment_id]
            if (
                item["content_hash"] != attachment["content_hash"]
                or item["byte_length"] != attachment["byte_length"]
                or item["archive_member"] != attachment.get("archive_member")
            ):
                raise ImportBundleError("archive manifest attachment inventory has inconsistent provenance")

    def _check_import_conflicts(self, connection: sqlite3.Connection, rows: Mapping[str, list[dict[str, Any]]]) -> None:
        for document in rows["documents"]:
            existing = connection.execute(
                "SELECT record_hash FROM documents WHERE document_id=?", (document["document_id"],)
            ).fetchone()
            if existing is not None and existing["record_hash"] != document["record_hash"]:
                raise ImportBundleError(f"document ID conflict: {document['document_id']}")
            external_id = document.get("external_id")
            if external_id:
                by_external = connection.execute(
                    "SELECT document_id,record_hash FROM documents WHERE external_id=?", (external_id,)
                ).fetchone()
                if by_external is not None and (
                    by_external["document_id"] != document["document_id"] or by_external["record_hash"] != document["record_hash"]
                ):
                    raise ImportBundleError(f"external record ID conflict: {external_id}")
        for atom in rows["atoms"]:
            existing = connection.execute(
                "SELECT content_hash FROM atoms WHERE atom_id=?", (atom["atom_id"],)
            ).fetchone()
            if existing is not None and existing["content_hash"] != atom["content_hash"]:
                raise ImportBundleError(f"atom ID conflict: {atom['atom_id']}")
        for event in rows["events"]:
            existing = connection.execute(
                "SELECT payload_hash FROM events WHERE event_id=?", (event["event_id"],)
            ).fetchone()
            if existing is not None and existing["payload_hash"] != event["payload_hash"]:
                raise ImportBundleError(f"event ID conflict: {event['event_id']}")

    def import_bundle(self, source: str | os.PathLike[str], *, actor: str = "local-user") -> dict[str, Any]:
        """Import a portable bundle and rebuild replaceable lexical state."""

        archive_path = Path(source)
        manifest, rows, attachment_bytes = self._read_bundle(archive_path)
        self._validate_import_rows(manifest, rows, attachment_bytes)
        estimated = max(64 * 1024, sum(len(raw) for raw in attachment_bytes.values()) * 3)
        self._ensure_write_capacity(estimated, purpose="import")
        object_keys: dict[str, str] = {}
        for attachment_id, raw in attachment_bytes.items():
            object_keys[attachment_id] = self._store_attachment(raw, _sha256_bytes(raw))
        inserted = {"events": 0, "documents": 0, "attachments": 0, "atoms": 0, "proposals": 0, "navigation_summaries": 0}
        with self._transaction() as connection:
            self._check_import_conflicts(connection, rows)
            for document in rows["documents"]:
                if connection.execute("SELECT 1 FROM documents WHERE document_id=?", (document["document_id"],)).fetchone():
                    continue
                connection.execute(
                    """
                    INSERT INTO documents(
                        document_id,document_name,source_url,file_uri,collection_name,
                        declared_content_hash,stored_content_hash,media_type,metadata_json,
                        image_descriptions_json,raw_record_json,record_hash,external_id,created_event_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        document["document_id"], document["document_name"], document.get("source_url"),
                        document.get("file_uri"), document["collection_name"], document["declared_content_hash"],
                        document["stored_content_hash"], document["media_type"], _canonical_json(document["metadata"]),
                        _canonical_json(document["image_descriptions"]), _canonical_json(document["raw_record"]),
                        document["record_hash"], document.get("external_id"), document["created_event_id"],
                    ),
                )
                inserted["documents"] += 1
            for attachment in rows["attachments"]:
                if connection.execute("SELECT 1 FROM attachments WHERE attachment_id=?", (attachment["attachment_id"],)).fetchone():
                    continue
                connection.execute(
                    """
                    INSERT INTO attachments(
                        attachment_id,document_id,object_key,content_hash,media_type,byte_length,created_event_id
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        attachment["attachment_id"], attachment["document_id"], object_keys[attachment["attachment_id"]],
                        attachment["content_hash"], attachment["media_type"], int(attachment["byte_length"]),
                        attachment["created_event_id"],
                    ),
                )
                inserted["attachments"] += 1
            for atom in rows["atoms"]:
                if connection.execute("SELECT 1 FROM atoms WHERE atom_id=?", (atom["atom_id"],)).fetchone():
                    continue
                connection.execute(
                    "INSERT INTO atoms(atom_id,document_id,attachment_id,ordinal,content,content_hash,created_event_id) VALUES(?,?,?,?,?,?,?)",
                    (
                        atom["atom_id"], atom["document_id"], atom["attachment_id"], int(atom["ordinal"]),
                        atom["content"], atom["content_hash"], atom["created_event_id"],
                    ),
                )
                inserted["atoms"] += 1
            for event in rows["events"]:
                if connection.execute("SELECT 1 FROM events WHERE event_id=?", (event["event_id"],)).fetchone():
                    continue
                connection.execute(
                    """
                    INSERT INTO events(
                        event_id,event_type,occurred_at,actor,parent_event_id,payload_json,
                        payload_hash,origin_event_id,origin_sequence
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        event["event_id"], event["event_type"], event["occurred_at"], event["actor"],
                        event.get("parent_event_id"), _canonical_json(event["payload"]), event["payload_hash"],
                        event.get("origin_event_id"), event.get("sequence", event.get("origin_sequence")),
                    ),
                )
                inserted["events"] += 1
            for proposal in rows["proposals"]:
                if connection.execute("SELECT 1 FROM proposals WHERE proposal_id=?", (proposal["proposal_id"],)).fetchone():
                    continue
                connection.execute(
                    """
                    INSERT INTO proposals(
                        proposal_id,proposal_type,candidate_json,evidence_atom_ids_json,status,
                        actor,reviewer,decision_reason,created_event_id,decided_event_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        proposal["proposal_id"], proposal["proposal_type"], _canonical_json(proposal["candidate"]),
                        _canonical_json(proposal["evidence_atom_ids"]), proposal["status"], proposal["actor"],
                        proposal.get("reviewer"), proposal.get("decision_reason"), proposal["created_event_id"],
                        proposal.get("decided_event_id"),
                    ),
                )
                inserted["proposals"] += 1
            for summary in rows["navigation_summaries"]:
                if connection.execute("SELECT 1 FROM navigation_summaries WHERE summary_id=?", (summary["summary_id"],)).fetchone():
                    continue
                connection.execute(
                    """
                    INSERT INTO navigation_summaries(
                        summary_id,proposal_id,title,sections_json,evidence_atom_ids_json,
                        published_event_id,published_by
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        summary["summary_id"], summary.get("proposal_id"), summary["title"],
                        _canonical_json(summary["sections"]), _canonical_json(summary["evidence_atom_ids"]),
                        summary["published_event_id"], summary["published_by"],
                    ),
                )
                inserted["navigation_summaries"] += 1
            self._append_event(
                connection,
                "bundle.imported",
                {
                    "source_format": manifest["format"],
                    "source_schema_version": manifest["schema_version"],
                    "source_counts": manifest.get("counts", {}),
                    "inserted": inserted,
                },
                actor=actor,
            )
            inserted["events"] += 1
        rebuild = self._rebuild_projection(force=True, actor=actor, record_event=True)
        self._clear_query_cache()
        return {
            "status": "completed",
            "source": str(archive_path),
            "inserted": inserted,
            "projection": rebuild,
            "integrity": self.verify_integrity(),
        }

    # -------------------------------------------------------------- validation
    def verify_integrity(self) -> dict[str, Any]:
        """Check provenance, event hashes, source anchors, and projection parity."""

        errors: list[dict[str, Any]] = []
        event_count = 0
        for event in self._iter_events():
            event_count += 1
            actual_hash = _sha256_text(_canonical_json(event["payload"]))
            if actual_hash != event["payload_hash"]:
                errors.append({"kind": "event_hash", "event_id": event["event_id"]})
        attachments = self._connection.execute("SELECT * FROM attachments ORDER BY attachment_id").fetchall()
        for attachment in attachments:
            try:
                raw = self.get_attachment(attachment["attachment_id"])
            except TraceLocalError as error:
                errors.append({"kind": "attachment", "attachment_id": attachment["attachment_id"], "detail": str(error)})
                continue
            if len(raw) != int(attachment["byte_length"]):
                errors.append({"kind": "attachment_length", "attachment_id": attachment["attachment_id"]})
        atom_ids = {
            row["atom_id"] for row in self._connection.execute("SELECT atom_id FROM atoms").fetchall()
        }
        for proposal in self.list_proposals():
            missing = [atom_id for atom_id in proposal["evidence_atom_ids"] if atom_id not in atom_ids]
            if missing:
                errors.append({"kind": "proposal_anchor", "proposal_id": proposal["proposal_id"], "missing": missing})
        for summary in self.list_navigation_summaries():
            try:
                self._validated_navigation_sections(
                    {"title": summary["title"], "sections": summary["sections"]},
                    summary["evidence_atom_ids"],
                )
            except (RecordValidationError, KeyError) as error:
                errors.append({"kind": "navigation_summary", "summary_id": summary["summary_id"], "detail": str(error)})
        canonical_count = self._atom_count()
        indexed_count = self._projection_count()
        state = self._connection.execute(
            "SELECT atom_count,canonical_hash FROM projection_state WHERE projection_name='lexical'"
        ).fetchone()
        projection_parity = canonical_count == indexed_count
        if state is not None:
            projection_parity = (
                projection_parity
                and int(state["atom_count"]) == canonical_count
                and state["canonical_hash"] == self._canonical_atom_hash()
            )
        if not projection_parity:
            errors.append(
                {
                    "kind": "projection_parity",
                    "canonical_atom_count": canonical_count,
                    "indexed_atom_count": indexed_count,
                }
            )
        return {
            "valid": not errors,
            "errors": errors,
            "canonical_atom_count": canonical_count,
            "indexed_atom_count": indexed_count,
            "projection_parity": projection_parity,
            "attachment_count": len(attachments),
            "event_count": event_count,
        }


# The shortest public SDK spelling is intentionally exported at module scope.
Trace = LocalTrace


def open_trace(
    data_dir: str | os.PathLike[str],
    *,
    resource_policy: ResourcePolicy | None = None,
    resource_probe: ResourceProbe | None = None,
) -> LocalTrace:
    """Open one explicitly selected local Trace directory."""

    return LocalTrace.open(data_dir, resource_policy=resource_policy, resource_probe=resource_probe)


__all__ = [
    "CapacityError",
    "DEFAULT_COLLECTION",
    "EXPORT_FORMAT",
    "EXPORT_SCHEMA_VERSION",
    "ImportBundleError",
    "LocalEmbeddingPlugin",
    "LocalRerankerPlugin",
    "LocalTrace",
    "ProjectionError",
    "RecordValidationError",
    "ResourcePolicy",
    "ResourceSnapshot",
    "Trace",
    "TraceLocalError",
    "open_trace",
]
