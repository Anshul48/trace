"""Source-tree compatibility re-export for the legacy trace package.

The installable Phase 1 SDK lives at trace_local because Python already ships
with a standard-library module named trace.
"""

from trace_local.local import *
