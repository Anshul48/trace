"""Source-tree compatibility package for legacy Trace experiments.

The installable Phase 1 SDK uses trace_local because Python's standard library
already owns the trace module name. The re-exports below preserve local source
checkouts and legacy tests while trace.v2 remains isolated from the Phase 1
default package surface.
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
