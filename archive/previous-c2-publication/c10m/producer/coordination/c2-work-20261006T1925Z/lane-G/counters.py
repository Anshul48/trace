"""Lane G: F5 work counters API (sole-writer impl of profile-counters.md §3)."""
import copy

POPULATIONS = ("xholon", "leaf", "parent", "doc")
LEGS = ("place_xdoc", "place_leaf", "place_parent", "lex_postings",
        "dense_atoms", "dense_holons")

_COUNTER_KEYS = set()
for _pop in POPULATIONS:
    _COUNTER_KEYS.add(f"catalog_rows_scanned.{_pop}")
    _COUNTER_KEYS.add(f"catalog_bytes_touched.{_pop}")
for _leg in LEGS:
    _COUNTER_KEYS.add(f"scoring_evals.{_leg}")
_COUNTER_KEYS |= {
    "bytes_read", "bytes_written", "bytes_copied",
    "files_touched", "artifacts_read",
    "log_commits_read", "log_ops_read",
    "ancestor_versions_written", "ancestor_bytes_written",
    "relation_work_units", "native_work_units",
    "failed_retried_work_units",
}

_TIMER_KEYS = {
    "t_edit_arrival", "t_durable_ack", "t_first_fresh_answer",
    "f1_chunk_s", "f1_cache_s", "f1_encode_s", "f1_commit_s",
    "f1_place_s", "f1_tl_side_s", "f1_substrate_s",
    "f2_publish_s", "f2_query_s",
}


def counter_keys():
    return sorted(_COUNTER_KEYS)


def timer_keys():
    return sorted(_TIMER_KEYS)


class Counters:
    """Monotonic cumulative counters for one scope. Merging overlaps fails closed."""

    def __init__(self, scope):
        self.scope = scope
        self._c = {}
        self._t = {}

    def inc(self, key, n=1):
        if key not in _COUNTER_KEYS:
            raise KeyError(f"unknown counter: {key}")
        if n < 0:
            raise ValueError("counters are monotonic: negative increment refused")
        self._c[key] = self._c.get(key, 0) + n
        return self._c[key]

    def set_timer(self, key, seconds):
        if key not in _TIMER_KEYS:
            raise KeyError(f"unknown timer: {key}")
        self._t[key] = float(seconds)

    def get(self, key, default=0):
        return self._c.get(key, default)

    def add(self, other):
        """Merge two DISJOINT scopes. Any overlapping nonzero key is refused."""
        overlap = [k for k in self._c
                   if k in other._c and (self._c[k] or other._c[k])]
        if overlap:
            raise ValueError(f"overlapping scopes cannot merge: {overlap}")
        timer_overlap = [k for k in self._t if k in other._t]
        if timer_overlap:
            raise ValueError(f"overlapping timers cannot merge: {timer_overlap}")
        m = Counters(scope=f"{self.scope}+{other.scope}")
        m._c = dict(self._c)
        m._c.update(other._c)
        m._t = dict(self._t)
        m._t.update(other._t)
        return m

    def check_budget(self, key, ceiling):
        v = self._c.get(key, 0)
        return {"key": key, "value": v, "ceiling": ceiling,
                "exceeded": v > ceiling}

    def snapshot(self):
        return {"scope": self.scope,
                "counters": copy.deepcopy(self._c),
                "timers": copy.deepcopy(self._t)}
