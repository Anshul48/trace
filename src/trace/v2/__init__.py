"""Trace V2: an evidence-first, replayable cognitive memory substrate.

The package deliberately has no dependency on the legacy Trace document pipeline.
"""

from .api import create_app
from .repository import AttachmentStore, DenseIndex, LexicalIndex, Repository
from .production import OpenSearchLexicalIndex, PostgresEventStore, QdrantDenseIndex, S3ObjectStore
from .service import TraceService
from .store import SqliteEventStore

__all__ = [
    "create_app", "SqliteEventStore", "PostgresEventStore", "S3ObjectStore",
    "OpenSearchLexicalIndex", "QdrantDenseIndex", "Repository", "AttachmentStore",
    "LexicalIndex", "DenseIndex", "TraceService",
]
