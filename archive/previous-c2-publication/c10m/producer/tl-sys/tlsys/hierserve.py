"""C2 Lane R: facade-native HierQuery port (guard + work accounting).

HierQuery runs over the Lane S compat facade unchanged (its nomination
maps already delegate to the view's incrementally maintained maps). This
module is the Lane R port layer around that product path:

  - ``FacadeGuard`` proves "no direct NarrowIndex internals": every index
    attribute HierQuery touches must be on the section 3.4 / contract
    section 5 facade surface allowlist, else AttributeError (fail-closed).
    Mutators (advance_to, note_population_changed) are excluded: the port
    is read-only.
  - ``MappingGuard`` wraps the served mappings and counts keyed access
    (get/getitem/contains) separately from full-population traffic
    (items/values/iteration), so per-query N-terms are named, not hidden.
  - ``HierServe`` binds (tlstore, facade, embed) and serves guided/flat
    through one held HierQuery (the product caching shape), returning
    (rows, report, traffic) per call. Traffic has no Lane G key (the
    scoring_evals legs cover narrow/placement only); it is reported in
    receipts via stats(), never mislabeled into another key.

Differential rule: HierServe output equals direct HierQuery output over
the same index (rows + reports normalized-equal), on both the reference
and the segmented backends, including retirement (retired_skipped) and
bounded nomination (maps_built/exclusion counts).
"""

# Facade surface (spec section 3.4 + serving-contract.md section 5) minus
# mutators. HierQuery touches a small subset; the guard allowlists the
# whole read surface and the tests pin the touched subset as evidence.
FACADE_ATTRS = frozenset({
    "atoms", "holons", "atom_text", "doc_atoms",
    "seg_leaves", "seg_parents",
    "retired_docs", "retired_atoms", "retired_aids",
    "triple", "birth", "epoch", "max_seq",
    "bm25", "bm25_fullscan", "dense_atoms", "dense_holons",
    "is_live_atom", "live_atom_set", "nomination_maps",
    "serving_view", "serve_counters",
})

_FULL_SCAN_METHODS = frozenset({"items", "values", "keys", "copy"})


class MappingGuard:
    """Read-only mapping wrapper counting keyed vs full-scan traffic."""

    def __init__(self, mapping, traffic, name):
        object.__setattr__(self, "_mg_map", mapping)
        object.__setattr__(self, "_mg_traffic", traffic)
        object.__setattr__(self, "_mg_name", name)

    def _bump(self, kind):
        key = f"{self._mg_name}.{kind}"
        self._mg_traffic[key] = self._mg_traffic.get(key, 0) + 1

    def get(self, *a, **k):
        self._bump("keyed")
        return self._mg_map.get(*a, **k)

    def __getitem__(self, key):
        self._bump("keyed")
        return self._mg_map[key]

    def __contains__(self, key):
        self._bump("keyed")
        return key in self._mg_map

    def __len__(self):
        return len(self._mg_map)

    def __iter__(self):
        self._bump("full_scan")
        return iter(self._mg_map)

    def __getattr__(self, name):
        if name in _FULL_SCAN_METHODS:
            self._bump("full_scan")
        target = getattr(object.__getattribute__(self, "_mg_map"), name)
        if callable(target):
            def _wrapped(*a, **k):
                return target(*a, **k)
            return _wrapped
        return target


def _is_mapping(value):
    return hasattr(value, "get") and hasattr(value, "__getitem__")


class FacadeGuard:
    """Read-only facade proxy: allowlist + per-call traffic."""

    def __init__(self, index):
        object.__setattr__(self, "_fg_index", index)
        object.__setattr__(self, "traffic", {})
        object.__setattr__(self, "touched", set())

    def reset_traffic(self):
        object.__setattr__(self, "traffic", {})

    def _bump(self, name):
        tr = object.__getattribute__(self, "traffic")
        tr[name] = tr.get(name, 0) + 1
        object.__getattribute__(self, "touched").add(name)

    def __getattribute__(self, name):
        if name in ("_fg_index", "traffic", "touched",
                    "reset_traffic", "_bump"):
            return object.__getattribute__(self, name)
        if name not in FACADE_ATTRS:
            raise AttributeError(
                f"FacadeGuard: {name!r} is not facade surface "
                f"(no NarrowIndex internals on the port path)")
        object.__getattribute__(self, "_bump")(name)
        value = getattr(object.__getattribute__(self, "_fg_index"), name)
        if _is_mapping(value) and not isinstance(value, MappingGuard):
            return MappingGuard(
                value, object.__getattribute__(self, "traffic"), name)
        return value

    def __setattr__(self, name, value):
        raise AttributeError("FacadeGuard is read-only")


class HierServe:
    """HierQuery over the facade, guarded and traffic-counted.

    Holds one HierQuery (the product caching shape: nomination maps cache
    across calls at a pin). ``guided``/``flat`` return (rows, report,
    traffic) with per-call traffic. Raises StaleServeError-equivalent
    behavior is owned by the facade (typed refusal on pin mismatch); this
    layer adds no pin of its own.
    """

    def __init__(self, tlstore, index, embed_query):
        from tlsys.query import HierQuery
        self.tl = tlstore
        self.index = index
        self.guard = FacadeGuard(index)
        self._hq = HierQuery(tlstore, self.guard, embed_query)
        self._calls = 0

    def guided(self, query, top_parents=None, top_children=None,
               top_atoms=None, parent_budget=None):
        """(rows, report, traffic) via parent-routed descent."""
        from tlsys import query as _q
        kw = {}
        if top_parents is not None:
            kw["top_parents"] = top_parents
        if top_children is not None:
            kw["top_children"] = top_children
        if top_atoms is not None:
            kw["top_atoms"] = top_atoms
        kw["parent_budget"] = parent_budget
        self.guard.reset_traffic()
        rows, report = self._hq.guided(query, **kw)
        self._calls += 1
        traffic = dict(self.guard.traffic)
        traffic["calls"] = self._calls
        return rows, report, traffic

    def flat(self, query, total_budget, top_atoms=None):
        """(rows, report, traffic): matched-work flat control."""
        kw = {}
        if top_atoms is not None:
            kw["top_atoms"] = top_atoms
        self.guard.reset_traffic()
        rows, report = self._hq.flat(query, total_budget, **kw)
        self._calls += 1
        traffic = dict(self.guard.traffic)
        traffic["calls"] = self._calls
        return rows, report, traffic

    def touched_surface(self):
        """Facade attributes touched so far (evidence of minimal use)."""
        return set(self.guard.touched)

    def reset_cache(self):
        """Drop the held HierQuery caches (fresh-nomination measurement)."""
        from tlsys.query import HierQuery
        emb = self._hq.embed_query
        self._hq = HierQuery(self.tl, self.guard, emb)
