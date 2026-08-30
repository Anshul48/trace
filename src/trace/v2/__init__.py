"""Trace V2: an evidence-first, replayable cognitive memory substrate.

The package deliberately has no dependency on the legacy Trace document pipeline.
"""

try:
    from .api import create_app
except ImportError:
    create_app = None
try:
    from .repository import AttachmentStore, DenseIndex, LexicalIndex, Repository
except ImportError:
    AttachmentStore = DenseIndex = LexicalIndex = Repository = None
try:
    from .production import OpenSearchLexicalIndex, PostgresEventStore, QdrantDenseIndex, S3ObjectStore
except ImportError:
    OpenSearchLexicalIndex = PostgresEventStore = QdrantDenseIndex = S3ObjectStore = None
try:
    from .service import TraceService
except ImportError:
    TraceService = None
try:
    from .store import SqliteEventStore
except ImportError:
    SqliteEventStore = None

__all__ = [
    "create_app", "SqliteEventStore", "PostgresEventStore", "S3ObjectStore",
    "OpenSearchLexicalIndex", "QdrantDenseIndex", "Repository", "AttachmentStore",
    "LexicalIndex", "DenseIndex", "TraceService",
]
