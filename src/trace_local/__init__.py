"""Public API for the local-first Trace Phase 1 alpha.

This package deliberately avoids the standard-library trace module name, so
the SDK remains importable after a normal PyPI installation.
"""

from .local import (
    CapacityError,
    ImportBundleError,
    LocalTrace,
    ProjectionError,
    RecordValidationError,
    ResourcePolicy,
    ResourceSnapshot,
    Trace,
    TraceLocalError,
    open_trace,
)

__version__ = "0.1.0"

__all__ = [
    "CapacityError",
    "ImportBundleError",
    "LocalTrace",
    "ProjectionError",
    "RecordValidationError",
    "ResourcePolicy",
    "ResourceSnapshot",
    "Trace",
    "TraceLocalError",
    "open_trace",
]
