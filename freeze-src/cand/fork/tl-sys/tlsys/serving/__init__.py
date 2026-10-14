"""C2 serving: immutable segments + delta + tombstones -> pinned ServingView.

Spec: handoffs/TL-C2-LOCALITY-ARCHITECTURE-2026-10-06.md v1.1 section 3.3/3.4.
Contract: the Lane-S serving-contract.md (v1; v1.2 rules preserved by S-3).

No module in this package imports tlsys.index at module level (the facade
imports us); shared constants live in tlsys.serving.lexical and are
re-exported by tlsys.index.
"""

FORMAT_VERSION = 1
CONFIG_ID = "c2-serving-v1"
ANALYZER_ID = "lower-split-v1"

__all__ = [
    "FORMAT_VERSION", "CONFIG_ID", "ANALYZER_ID",
    "provisional", "counters", "faults", "lexical", "dense",
    "tombstones", "delta", "segments", "manifest", "checkpoints",
    "digest", "view", "compact", "generation",
]
