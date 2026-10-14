"""Serving-side work counters (I6/F5). Provisional holder.

Names are chosen to merge 1:1 into Lane G's counters API when published
(see serving-contract.md section 6). Native/vectorized work is counted
like python work.
"""

import copy
import threading


class ServeCounters:
    FIELDS = (
        "lex_postings_scanned",
        "dense_fp32_rows",
        "dense_rescore_rows",
        "holon_rows_scored",
        "bytes_read",
        "bytes_written",
        "files_touched",
        "artifacts_read",
        "log_rows_read",
        "log_ops_read",
        "failed_retried",
        "ancestor_versions",  # always 0 on serving path; placement-owned
        "segments_live",
        "delta_rows",
        "views_retained",
        "widenings",
        "quarantines",
        "rebuild_ranges",
        "full_copies",  # O(N) copies taken (shared-reader COW); must be ~0
        "straggler_rebuilds",
    )

    def __init__(self):
        self._c = {k: 0 for k in self.FIELDS}
        self._lock = threading.Lock()

    def record(self, **kw):
        with self._lock:
            for k, v in kw.items():
                if k not in self._c:
                    raise ValueError(f"unknown counter: {k}")
                self._c[k] += v

    def set_gauge(self, **kw):
        with self._lock:
            for k, v in kw.items():
                if k not in self._c:
                    raise ValueError(f"unknown counter: {k}")
                self._c[k] = v

    def totals(self):
        with self._lock:
            return dict(self._c)

    def to_dict(self):
        return {"scope": "serving", "counters": dict(self._c)}

    def merge(self, other):
        for k, v in other.totals().items():
            if k in self._c:
                self._c[k] += v

    def copy(self):
        out = ServeCounters()
        out._c = copy.deepcopy(self._c)
        return out


# ServeCounters -> Lane-G Counters key map (contract section 6). Sums
# are tuples of serving keys. Gauges and serving-only counts are NOT
# Lane-G keys; they ride the `extra` dict (documented, never dropped).
LANE_G_MAP = (
    (("lex_postings_scanned",), "scoring_evals.lex_postings"),
    (("dense_fp32_rows", "dense_rescore_rows"), "scoring_evals.dense_atoms"),
    (("holon_rows_scored",), "scoring_evals.dense_holons"),
    (("bytes_read",), "bytes_read"),
    (("bytes_written",), "bytes_written"),
    (("files_touched",), "files_touched"),
    (("artifacts_read",), "artifacts_read"),
    (("log_rows_read",), "log_commits_read"),
    (("log_ops_read",), "log_ops_read"),
    (("dense_fp32_rows",), "native_work_units"),
    (("failed_retried",), "failed_retried_work_units"),
)

SERVING_EXTRA_KEYS = (
    "segments_live",
    "delta_rows",
    "views_retained",
    "widenings",
    "quarantines",
    "rebuild_ranges",
    "full_copies",
    "straggler_rebuilds",
    "ancestor_versions",
)

# Lane-G keys with no serving source (documented gaps, not zeros):
# bytes_copied (pointer-copy bytes untracked), relation_work_units
# (Lane R), catalog_rows_scanned.*/catalog_bytes_touched.* and
# scoring_evals.place_* (Lane O), timers (F-cell harness).
LANE_G_UNMAPPED = (
    "bytes_copied",
    "relation_work_units",
)


def to_lane_g(serve_counters, scope="serving"):
    """Export serving counters to Lane G's Counters (read-only import).

    Returns (lane_g_counters, extra, note). Raises ImportError when
    Lane G's counters.py is unavailable (product code never copies or
    forks it). ancestor_* are explicitly zero (serving never writes
    ancestors); unmapped keys are listed in the note, never zeroed.
    """
    from tlsys.serving.provisional import _load_lane_g_module
    mod = _load_lane_g_module("counters")
    if mod is None:
        raise ImportError(
            "lane-G counters.py unavailable; export needs it "
            "(see serving-contract.md section 6)")
    totals = serve_counters.totals()
    out = mod.Counters(scope)
    for srcs, dst in LANE_G_MAP:
        out.inc(dst, sum(totals.get(s, 0) for s in srcs))
    out.inc("ancestor_versions_written", 0)
    out.inc("ancestor_bytes_written", 0)
    extra = {k: totals.get(k, 0) for k in SERVING_EXTRA_KEYS}
    note = {"scope": scope,
            "serving_extra_keys": list(SERVING_EXTRA_KEYS),
            "lane_g_unmapped": list(LANE_G_UNMAPPED)}
    return out, extra, note
