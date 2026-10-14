"""Cross-doc placement baseline (Q1): centroid-similarity membership.

On ingest of each document (after its per-doc holon commits), compare the
doc centroid against existing cross-doc holon descriptors read from
COMMITTED data. Cosine >= T_PLACE -> join best holon (new versioned holon
meta: members + fresh centroid). Else -> new cross-doc holon. Budgets cap
memberships per doc; sparse/outlier docs keep singleton holons (never
forced into unrelated groups, S-03 section 1e).

Authority: placement commits ride the ingest path (ACCEPT_ATOMS,
non-consequential, same as existing per-doc holon commits) -- NOT
autonomous Stage-1 maintenance, so D-23 Entry 3 (struck) does not apply.
Versioned holon metas supersede by seq recency; no committed record is
ever mutated. Readers (NarrowIndex) already resolve latest-wins and are
holon-id-generic: no retrieval-path change needed.

Promoted defaults (adopted 2026-10-04; tuning-calibrated): T_PLACE=0.55,
MAX_XMEMBERSHIPS=3, MAX_XHOLON_MEMBERS=25.
"""

import json
import time

import numpy as np

from tlsys.hnsw_candidates import StaleGenerationError, normalize_f32
from tlsys.identity import ATOM_SCHEME
from tlsys.store_if import uuidv7

T_PLACE = 0.55
MAX_XMEMBERSHIPS = 3
MAX_XHOLON_MEMBERS = 25
# S-03 section 1b foreground budget: max placement decisions (docs)
# per ingest call. Overflow defers to the manifest backlog (drained
# by tlsys.maint.drain_placement_backlog). Generous default (same
# spirit as WORK_BUDGET); tests exercise small budgets.
PLACE_FOREGROUND_BUDGET = 100000


def _cos(u, v):
    u = np.asarray(u, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    un = float(np.linalg.norm(u)) or 1.0
    vn = float(np.linalg.norm(v)) or 1.0
    return float(u @ v / (un * vn))


def read_xholons(tlstore, pinned, min_seq=0):
    """{xholon_id: {members, descriptor, seq}} from COMMITTED metas.

    Only holon metas whose id starts with "xdoc-" (cross-doc namespace;
    per-doc holons use doc ids and never collide: doc ids with the
    "xdoc-" prefix are refused at placement). min_seq (exclusive) bounds
    the scan for incremental readers; latest-wins per id within the
    scanned window (callers merge with their cache for older seqs).

    R8-B (R7-A proposal C adoption): unbounded read via min_seq
    frontiers (read_commits_all) + single-connection batched artifact
    rows (same call shape as ingest._committed_doc_state). Results are
    identical to the pre-R8-B loop at every scale the old 1M window
    covered; past it the old call now raises TruncationError while
    this reader pages through.
    """
    birth, epoch, mx, _triple = pinned
    rows = tlstore.read_commits_all(birth, epoch, mx,
                                    kind="ACCEPT_ATOMS",
                                    min_seq=min_seq)
    seqs = [r[0] for r in rows]
    refs = tlstore.pub_refs(seqs)
    arows = tlstore.artifact_rows(
        [a for seq in seqs for a in refs.get(seq, [])])
    out = {}
    for seq in seqs:
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id,
                                         expect_digest=arow[4])
            try:
                meta = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            hid = meta.get("holon")
            if not isinstance(hid, str) or not hid.startswith("xdoc-"):
                continue
            if meta.get("atom_scheme") != ATOM_SCHEME:
                raise ValueError(
                    f"op seq {seq}: xholon meta scheme "
                    f"{meta.get('atom_scheme')!r} != {ATOM_SCHEME!r}")
            out[hid] = {"members": list(meta.get("members", [])),
                        "descriptor": list(meta.get("descriptor", [])),
                        "seq": seq}
    return out


def decide(centroid, xholons, t_place=T_PLACE, max_m=MAX_XMEMBERSHIPS,
           max_members=MAX_XHOLON_MEMBERS, candidate_ids=None,
           stats=None):
    """Return [xholon_id] to join (ranked, capped) or [] for new holon.

    Full holons (members >= max_members) are skipped: mean-centroid
    drift otherwise grows runaway mega-holons (399-member case at S1
    scale without the cap). The doc then joins other holons or, if all
    qualifying holons are full, creates a new one.

    R7-B candidate discovery (default OFF): candidate_ids restricts
    exact local scoring to a bounded candidate set (e.g. from
    tlsys.hnsw_candidates). candidate_ids=None scores the full
    population exactly as before (bit-identical flag-off behavior).
    Candidate ids absent from xholons (stale/unpublished refs) are
    ignored and, when stats is a dict, reported under "unknown" with
    "scored"/"full_skipped" counts. Threshold, cap, and full-holon
    policy are unchanged; membership acceptance stays separate from
    discovery.

    M1-C synchronous navigation: when candidate_ids is None and a
    navigator is attached (attach_sync_nav), discovery runs through
    the attached candidate-search boundary with exact local rescore
    (decide_with_navigator). Default (nothing attached) is the exact
    full-population path below, bit-identical to before. An explicit
    candidate_ids list always takes the explicit branch, ignoring
    any attached navigator.
    """
    if candidate_ids is None and _SYNC_NAV is not None:
        return decide_with_navigator(
            centroid, xholons, _SYNC_NAV, t_place=t_place,
            max_m=max_m, max_members=max_members, stats=stats,
            path="sync-place")
    if candidate_ids is None:
        scored = sorted(
            ((hid, _cos(centroid, h["descriptor"]))
             for hid, h in xholons.items()
             if len(h["members"]) < max_members),
            key=lambda kv: -kv[1])
        if stats is not None:
            stats.update({"scored": len(scored), "unknown": [],
                          "full_skipped": sum(
                              1 for h in xholons.values()
                              if len(h["members"]) >= max_members)})
        return [hid for hid, s in scored[:max_m] if s >= t_place]
    want = set(candidate_ids)
    unknown = [hid for hid in candidate_ids if hid not in xholons]
    # Iterate in xholons order (not candidate order) so stable-sort
    # ties match the full path among the selected.
    scored = sorted(
        ((hid, _cos(centroid, h["descriptor"]))
         for hid, h in xholons.items()
         if hid in want and len(h["members"]) < max_members),
        key=lambda kv: -kv[1])
    if stats is not None:
        stats.update({"scored": len(scored), "unknown": unknown,
                      "full_skipped": sum(
                          1 for hid in want
                          if hid in xholons
                          and len(xholons[hid]["members"])
                          >= max_members)})
    return [hid for hid, s in scored[:max_m] if s >= t_place]


class LiveAuditCache:
    """Incremental version tracking for candidate-index audits (R8-B).

    R7-B called search.coverage(live) on every discovery call: an O(N)
    set build + seq compare per query (the 3.6 ms audit term in the
    R7-B report section 3). This cache keeps the last audit for one
    (search, live view, caller version) triple: repeat calls against
    an unchanged view return the cached audit in O(1); anything else
    recomputes exactly via search.coverage, so refusal/detection
    semantics are identical to the per-call audit.

    Caller contract: live_version must change whenever the live view's
    membership or per-holon seqs change. Structural changes (add /
    remove / reorder) are ALSO caught without a version bump via a
    cheap O(1) fingerprint (len + first/last key), but interior seq
    edits rely on the version: view owners bump on every mutation
    (NarrowIndex bumps in _build; post-build mutation must go through
    note_population_changed). A stale version after an interior edit
    is a caller bug, same class as query._dense_pop's cache contract.
    The served search generation is immutable once published; a
    same-object rebuild needs re-attach (attach invalidates this
    cache), while growth via add() is caught via the population size.

    Caller-owned (no globals): NarrowIndex holds one per index;
    decide_with_search takes one explicitly. Strong refs to the
    audited (search, live) pair are held so id-reuse can never alias
    a dead view to a cached audit.
    """

    def __init__(self):
        self._entry = None

    @staticmethod
    def _fingerprint(live):
        n = len(live)
        if n == 0:
            return (0, None, None)
        first = next(iter(live))
        last = next(reversed(live))
        return (n, first, last)

    def audit(self, search, live, live_version):
        """(audit, cached) for search.coverage(live) at live_version.

        cached=True means the returned audit is the identical dict
        object from the last recompute (same search, same live view,
        same version and fingerprint, same search population and
        generation); cached=False means it was just recomputed via
        search.coverage(live).
        """
        fp = self._fingerprint(live)
        e = self._entry
        if (e is not None and e[0] is search and e[1] is live
                and e[2] == live_version and e[3] == fp
                and e[5] == search.n
                and e[6] == search.generation):
            return e[4], True
        audit = search.coverage(live)
        self._entry = (search, live, live_version, fp, audit,
                       search.n, search.generation)
        return audit, False

    def invalidate(self):
        """Drop the cached audit (attach/detach/rebuild boundary)."""
        self._entry = None


class NavCounters:
    """Work-evidence accumulator for navigation legs (M1-C).

    Every discovery/rescore call records one dict: path label plus
    discovered/visited/rescored counts (and whatever else the leg
    reports). Summary statistics via totals(); JSON-safe via
    records. Caller-owned (no globals): serving indexes hold one;
    navigators hold one; evidence drivers read them.
    """

    def __init__(self):
        self.records = []

    def record(self, path, **kw):
        """Append one per-call work record (path + counters)."""
        rec = {"path": path}
        rec.update(kw)
        self.records.append(rec)
        return rec

    def totals(self):
        """{path: {counter: sum}} over numeric record fields."""
        out = {}
        for rec in self.records:
            slot = out.setdefault(rec["path"], {})
            for k, v in rec.items():
                if k == "path" or not isinstance(v, (int, float)):
                    continue
                slot[k] = slot.get(k, 0) + v
        return out


class OrdinalCache:
    """Cached live-insertion ordinals for stable nav ordering (M1-C).

    Same contract shape as LiveAuditCache: caller-owned, keyed on
    (live identity, caller version, cheap fingerprint), O(1) hits,
    exact rebuilds. ordinals() returns ({hid: position}, cached).
    Positions are the live dict's insertion order at (re)build --
    the published order for serving legs (build-once per
    generation). Structural changes without a version bump are
    caught via the fingerprint; interior reorders ride the caller
    version (same caller bug class as LiveAuditCache).
    """

    def __init__(self):
        self._entry = None

    @staticmethod
    def _fingerprint(live):
        n = len(live)
        if n == 0:
            return (0, None, None)
        first = next(iter(live))
        last = next(reversed(live))
        return (n, first, last)

    def ordinals(self, live, version):
        """({hid: insertion position}, cached) for this live view."""
        fp = self._fingerprint(live)
        e = self._entry
        if (e is not None and e[0] is live and e[1] == version
                and e[2] == fp):
            return e[3], True
        omap = {hid: i for i, hid in enumerate(live)}
        self._entry = (live, version, fp, omap)
        return omap, False

    def invalidate(self):
        """Drop the cached map (attach/detach/rebuild boundary)."""
        self._entry = None


class PartitionCandidateIndex:
    """Deterministic flat-partition candidate discovery (M1-C).

    PROVISIONAL E0-role primitive: bounded candidate discovery with
    exact caller-side rescore, behind the same boundary as
    HolonCandidateIndex (query/coverage/add/cost, generation tag,
    per-holon seqs, n/dim/hids). It is NOT a directory, descent,
    representative-set, fusion, or multi-vector variant: no
    hierarchy is traversed, no beam descends groups, no rep sets
    are routed, no scores are fused. Candidates come from a flat
    IVF-style partition (seeded-free deterministic k-means over
    L2-normalized float32 descriptors); callers rescore every
    candidate exactly from live descriptors and apply their own
    eligibility/capacity policy, exactly as with HNSW.

    Use: environments without the pinned hnswlib (pure numpy), and
    as the measured fallback wherever HNSW is unavailable. Where
    hnswlib==0.8.0 is present, HolonCandidateIndex remains the
    primary primitive; both backends share the CandidateNavigator
    driver and report the same work vocabulary.

    Determinism: labels follow sorted hid order; k-means inits on
    evenly spaced rows and runs a fixed Lloyd iteration cap with
    argmax-first ties; every emission is ordinal-ordered. No RNG,
    no set-iteration order, no PYTHONHASHSEED dependence.

    Native-work accounting: every unit of native work is counted
    (cells scored/visited, members collected) --
    n_scored_native_unknown is False. (BLAS-internal flops are not
    itemized; member-visit granularity is the disclosed unit.)
    """

    BACKEND = "partition-ivf/f32-cosine"

    def __init__(self):
        self._cent = None  # (C, d) float32 normalized centroids
        self._cells = []  # cell -> [labels] (label order)
        self.hids = []  # label -> hid (sorted at build)
        self._label = {}
        self._seq = {}
        self._cell_of = []  # label -> cell
        self.ordinals = {}  # hid -> label (stable published ordinals)
        self.generation = None
        self.dim = None
        self.n = 0
        self.params = {"backend": self.BACKEND, "n_cells": 0,
                       "iters": 12}
        self._cost = {"build_s": 0.0, "update_s": 0.0,
                      "update_count": 0, "index_bytes": 0,
                      "vector_input_bytes": 0,
                      "retained_matrix_bytes": 0, "map_entries": 0}

    # -- build / update --------------------------------------------
    def build(self, holons, generation, n_cells=None, iters=12):
        """Build over {hid: {descriptor, seq}} at generation tag.

        Same entry contract as HolonCandidateIndex.build (missing
        seq recorded as None, never claimed fresh). Fixed-point
        Lloyd k-means (iters cap, deterministic init); empty cells
        are kept (no members). Returns self.
        """
        import numpy as np
        t0 = time.perf_counter()
        hids = sorted(holons.keys())
        self.generation = generation
        self.hids = hids
        self._label = {h: i for i, h in enumerate(hids)}
        self._seq = {h: holons[h].get("seq") for h in hids}
        self.ordinals = dict(self._label)
        if hids:
            mat = np.stack([normalize_f32(holons[h]["descriptor"])
                            for h in hids])
            self.dim = int(mat.shape[1])
            want = max(1, min(256, len(hids) // 16))
            n_cells = want if n_cells is None else max(1, int(n_cells))
            n_cells = min(n_cells, len(hids))
            self._fit(mat, n_cells, iters)
            self._cost["vector_input_bytes"] = int(mat.nbytes)
        else:
            self.dim = None
            self._cent = None
            self._cells = []
            self._cell_of = []
            n_cells = 0
            self._cost["vector_input_bytes"] = 0
        self.n = len(hids)
        self.params = {"backend": self.BACKEND, "n_cells": n_cells,
                       "iters": int(iters)}
        self._cost["build_s"] = time.perf_counter() - t0
        self._cost["index_bytes"] = self._measure_bytes()
        self._cost["map_entries"] = len(hids)
        self._cost["retained_matrix_bytes"] = 0
        return self

    def _fit(self, mat, n_cells, iters):
        import numpy as np
        n = mat.shape[0]
        picks = [(i * n) // n_cells for i in range(n_cells)]
        cent = mat[picks].copy()
        assign = np.zeros(n, dtype=np.int64)
        for _ in range(max(1, int(iters))):
            sims = mat @ cent.T
            new = sims.argmax(axis=1)
            if bool((new == assign).all()):
                assign = new
                break
            assign = new
            for c in range(n_cells):
                rows = mat[assign == c]
                if len(rows) == 0:
                    continue
                m = rows.mean(axis=0)
                nn = float(np.linalg.norm(m)) or 1.0
                cent[c] = (m / nn).astype(np.float32)
        self._cent = cent
        self._cells = [[] for _ in range(n_cells)]
        self._cell_of = [0] * n
        for lab in range(n):
            c = int(assign[lab])
            self._cells[c].append(lab)
            self._cell_of[lab] = c

    def add(self, holons, generation):
        """Incrementally add {hid: {descriptor, seq}} (same tag).

        Same contract as HolonCandidateIndex.add: generation
        mismatch raises StaleGenerationError; re-add of an indexed
        hid is a no-op; changed descriptors need a rebuild (fresh
        labels only). New members join their nearest CURRENT
        centroid (centroids are not refit on add; rebuild for
        changed geometry). Returns count added.
        """
        import numpy as np
        if generation != self.generation:
            raise StaleGenerationError(
                f"candidate index at {self.generation}, "
                f"add at {generation}: rebuild, no mixing")
        fresh = [h for h in sorted(holons.keys())
                 if h not in self._label]
        if not fresh:
            return 0
        if self._cent is None:
            params = dict(self.params)
            self.build({h: {"descriptor": holons[h]["descriptor"],
                            "seq": holons[h].get("seq")}
                        for h in fresh},
                       self.generation,
                       n_cells=params.get("n_cells") or None,
                       iters=params.get("iters", 12))
            return len(fresh)
        t0 = time.perf_counter()
        mat = np.stack([normalize_f32(holons[h]["descriptor"],
                                      dim=self.dim) for h in fresh])
        sims = mat @ self._cent.T
        base = self.n
        for i, h in enumerate(fresh):
            lab = base + i
            c = int(sims[i].argmax())
            self._label[h] = lab
            self.hids.append(h)
            self.ordinals[h] = lab
            self._seq[h] = holons[h].get("seq")
            self._cells[c].append(lab)
            self._cell_of.append(c)
        self.n = len(self.hids)
        dt = time.perf_counter() - t0
        self._cost["update_s"] += dt
        self._cost["update_count"] += 1
        self._cost["update_last_s"] = dt
        self._cost["update_last_added"] = len(fresh)
        self._cost["vector_input_bytes"] += int(mat.nbytes)
        self._cost["index_bytes"] = self._measure_bytes()
        self._cost["map_entries"] = self.n
        return len(fresh)

    def _measure_bytes(self):
        # Measured structure bytes: centroid matrix + per-member
        # label/cell slots (8 bytes each, disclosed unit).
        cent = int(self._cent.nbytes) if self._cent is not None else 0
        return cent + 8 * self.n

    # -- query ------------------------------------------------------
    def query(self, qvec, k=200, ef=None, generation=None, live=None):
        """Top-k candidate hids for qvec (bounded discovery).

        Same boundary as HolonCandidateIndex.query: k clamped to
        the indexed population; generation, when given, must equal
        the build tag (else StaleGenerationError); live, when
        given, drops candidates whose live seq differs (reported
        as stale_dropped, never silently rescored). Cells open in
        centroid-similarity rank order until k members are
        collected (cell-granular: the last cell is finished);
        emission is ordinal-ordered (stable). ef is accepted and
        reported for boundary parity; it carries no truncation
        semantics in this backend (unlike HNSW's search width).

        Scores are per-member CELL-centroid similarities
        (scores_are="cell-centroid-approx"): callers never decide
        on them (exact rescore decides). All native work is
        counted (cells_scored/visited, members_visited):
        n_scored_native_unknown is False.
        """
        import numpy as np
        if generation is not None and generation != self.generation:
            raise StaleGenerationError(
                f"candidate index at {self.generation}, "
                f"queried at {generation}: rebuild, no mixing")
        kk = max(0, min(int(k), self.n))
        if ef is None:
            ef = max(kk, 50)
        rep = {"hids": [], "scores": [], "k": kk, "ef": int(ef),
               "ms": 0.0, "stale_dropped": [],
               "n_scored_native_unknown": False,
               "scores_are": "cell-centroid-approx",
               "cells_scored": 0, "cells_visited": 0,
               "members_visited": 0, "overshoot": 0}
        if kk == 0 or self._cent is None:
            return rep
        q = normalize_f32(qvec, dim=self.dim).reshape(-1)
        t0 = time.perf_counter()
        sims = self._cent @ q
        order = np.argsort(-sims, kind="stable")
        rep["cells_scored"] = int(len(order))
        collected = []  # (label, cell_sim) in collection order
        for c in order:
            c = int(c)
            rep["cells_visited"] += 1
            for lab in self._cells[c]:
                hid = self.hids[lab]
                if live is not None:
                    lv = live.get(hid)
                    if lv is None or \
                            lv.get("seq") != self._seq.get(hid):
                        rep["stale_dropped"].append(hid)
                        continue
                collected.append((lab, float(sims[c])))
            if len(collected) >= kk:
                break
        rep["ms"] = (time.perf_counter() - t0) * 1000.0
        rep["members_visited"] = len(collected)
        rep["overshoot"] = max(0, len(collected) - kk)
        collected = collected[:kk]
        collected.sort(key=lambda t: t[0])  # stable ordinal emission
        rep["hids"] = [self.hids[lab] for lab, _s in collected]
        rep["scores"] = [s for _lab, s in collected]
        return rep

    def coverage(self, live):
        """Version audit of a live {hid: {seq}} view (same shape as
        HolonCandidateIndex.coverage)."""
        live_ids = set(live.keys())
        indexed_ids = set(self._label.keys())
        stale = sorted(h for h in indexed_ids
                       if h not in live
                       or live[h].get("seq") != self._seq.get(h))
        unpublished = sorted(live_ids - indexed_ids)
        return {"indexed": len(indexed_ids), "live": len(live_ids),
                "stale": stale, "unpublished": unpublished}

    def cost(self):
        """Measured build/update/memory accounting (JSON-safe)."""
        out = dict(self._cost)
        out.update({"n": self.n, "dim": self.dim,
                    "generation": self.generation})
        out.update({f"param_{k}": v
                    for k, v in self.params.items()})
        return out


def decide_with_search(centroid, xholons, search, k=200, ef=None,
                       generation=None, t_place=T_PLACE,
                       max_m=MAX_XMEMBERSHIPS,
                       max_members=MAX_XHOLON_MEMBERS,
                       include_unpublished=True, live_version=None,
                       audit_cache=None, replenish=False,
                       max_rounds=3):
    """decide() with HNSW candidate discovery (R7-B; explicit opt-in).

    search: tlsys.hnsw_candidates.HolonCandidateIndex (or the M1-C
    PartitionCandidateIndex, same boundary). Candidates are exactly
    rescored by decide(); threshold/cap/full-holon policy are
    unchanged. Stale indexed versions (live seq differs, e.g.
    same-batch pending overwrites) are dropped as candidates and
    reported, then rescored from their LIVE descriptors (never the
    indexed vector) when include_unpublished=True. Live holons absent
    from the index (committed after build, or same-batch pending)
    are, with include_unpublished=True (default), unioned in and
    exactly scored so recall can only gain over candidates alone;
    with False both classes are reported and skipped. Generation
    mismatch raises StaleGenerationError. Returns (joins, report).

    R8-B incremental audit: pass a caller-owned LiveAuditCache plus a
    live_version token (bumped on every xholons mutation) to audit
    once and reuse across calls; audit_cache=None (default) keeps
    the exact R7-B per-call coverage audit. The report carries
    "audit_cached" either way.

    M1-C replenish (default OFF): replenish=True re-queries with a
    growing k (k, 2k, ...) up to max_rounds rounds while joins are
    below max_m and fresh candidates arrive, so full-holon
    rejections and threshold misses within discovery range are
    replenished within budget instead of silently ending the
    placement. Default False keeps exact R7-B/R8-B single-round
    behavior (report values identical; the M1-C keys below are the
    only output delta and are additive).
    """
    if audit_cache is None:
        audit = search.coverage(xholons)
        audit_cached = False
    else:
        audit, audit_cached = audit_cache.audit(search, xholons,
                                                live_version)
    # Stale indexed versions (e.g. same-batch pending overwrites in
    # the ingest xh cache) are rescored from their LIVE descriptors,
    # never from the indexed vector; unpublished live holons are
    # exactly scored. Both keep recall from silently dropping below
    # the exact path; both are reported by class.
    stale_live = [h for h in audit["stale"] if h in xholons]
    changed_ids = sorted(set(stale_live) | set(audit["unpublished"]))
    rounds = 0
    cands = []
    seen = set()
    discovered_total = 0
    visited_total = 0
    replenished_total = 0
    q = None
    joins = []
    stats = {}
    max_r = max(1, int(max_rounds)) if replenish else 1
    for rnd in range(max_r):
        q = search.query(qvec=centroid, k=k * (rnd + 1), ef=ef,
                         generation=generation, live=xholons)
        rounds += 1
        discovered_total += len(q["hids"])
        fresh = [h for h in q["hids"] if h not in seen]
        if rnd > 0:
            replenished_total += len(fresh)
        for h in fresh:
            seen.add(h)
            cands.append(h)
        if include_unpublished:
            for h in stale_live + audit["unpublished"]:
                if h not in seen:
                    seen.add(h)
                    cands.append(h)
        stats = {}
        joins = decide(centroid, xholons, t_place=t_place,
                       max_m=max_m, max_members=max_members,
                       candidate_ids=list(cands), stats=stats)
        visited_total += stats["scored"]
        if not replenish or len(joins) >= max_m or not fresh:
            break
        if len(seen) >= len(xholons):
            break  # whole live population rescored; nothing fresh
    report = {"joins": list(joins), "k": q["k"], "ef": q["ef"],
              "search_ms": q["ms"],
              "audit_cached": audit_cached,
              "n_candidates": len(q["hids"]),
              "stale_dropped": q["stale_dropped"],
              "stale_rescored_live": stale_live
              if include_unpublished else [],
              "unpublished": audit["unpublished"],
              "include_unpublished": include_unpublished,
              "scored": stats["scored"],
              "unknown": stats["unknown"],
              "full_skipped": stats["full_skipped"],
              "n_scored_native_unknown":
                  q["n_scored_native_unknown"],
              "rounds": rounds,
              "replenished": replenished_total,
              "discovered": discovered_total,
              "visited": visited_total,
              "changed_ids": changed_ids}
    return joins, report


def _score_fresh(centroid, live, fresh_ids, max_members):
    """Direct-fetch exact scores: ([(hid, cos)], unknown, full).

    One live.get per id (keyed iteration only); exactly one
    cosine per fetched non-full candidate. Shared by
    rescore_candidates and decide_with_navigator so no leg
    scores the same id twice.
    """
    scored = []
    unknown = []
    full = 0
    for hid in fresh_ids:
        h = live.get(hid)
        if h is None:
            unknown.append(hid)
            continue
        if len(h["members"]) >= max_members:
            full += 1
            continue
        scored.append((hid, _cos(centroid, h["descriptor"])))
    return scored, unknown, full


def rescore_candidates(centroid, live, candidate_ids,
                       t_place=T_PLACE, max_m=MAX_XMEMBERSHIPS,
                       max_members=MAX_XHOLON_MEMBERS,
                       ordinal_key=None, stats=None):
    """Exact local rescore of discovered candidates (M1-C).

    Same eligibility/capacity policy as decide(): threshold
    t_place, at most max_m joins, full holons (members >=
    max_members) skipped. Differences from decide()'s explicit
    candidate branch: (1) selected IDs are fetched DIRECTLY
    (live.get per candidate -- keyed iteration, no
    population loop); only fetched descriptors are scored, so
    vector work is O(len(candidate_ids)); (2) ranking ties
    break by ordinal_key(hid) (default: hid string order,
    deterministic) instead of live-dict order -- callers pass
    the candidate index's stable published ordinals so ties
    are stable across calls and dict build orders.

    stats (when a dict) gains scored/unknown/full_skipped
    (same names as decide) plus visited (fetched existing
    candidates = scored + full_skipped). Returns [hid] joins.
    """
    if ordinal_key is None:
        def ordinal_key(hid):
            return (1, hid)
    scored, unknown, full_skipped = _score_fresh(
        centroid, live, list(candidate_ids), max_members)
    scored.sort(key=lambda kv: (-kv[1], ordinal_key(kv[0])))
    if stats is not None:
        stats.update({"scored": len(scored), "unknown": unknown,
                      "full_skipped": full_skipped,
                      "visited": len(scored) + full_skipped})
    return [hid for hid, s in scored[:max_m] if s >= t_place]


class CandidateNavigator:
    """Common candidate-search boundary driver, placement legs (M1-C).

    Wraps one HolonCandidateIndex (HNSW) or
    PartitionCandidateIndex behind a single discover() protocol
    used by synchronous placement (decide via attach_sync_nav)
    and deferred placement (maint.drain_placement_backlog):

    - bounded discovery: search.query(k_hint) per round;
    - exact per-holon seq audit per call (stale indexed versions
      are dropped, rescored from LIVE descriptors, never trusted);
    - pending (seq-less) live entries are NEVER indexed -- they
      are unioned and rescored live every call;
    - committed-but-unpublished live entries are auto-added to
      the search (same-tag add) so the index catches up within
      the call instead of union-rescoring a growing tail;
    - explicit changed-ID sets (stale + unpublished) per call;
    - stable published ordinals for rescore tie-breaks
      (incrementally cached from the search's label order);
    - per-call work records in a caller-visible NavCounters.

    Generation discipline: strict_generation=False (default)
    floats -- the navigator binds the search's own tag and
    passes no expected generation to query(), because sync and
    deferred populations advance mid-call (new commits land
    while placing). Cross-view safety still holds: every
    candidate is seq-audited against the live view and
    rescored from live descriptors. strict_generation=True
    binds an expected tag and refuses mismatches (same error
    as the raw backends). One navigator per (store, run):
    never share across stores.

    search=None (default) lazily builds the backend of kind
    ("partition" default; "hnsw" needs hnswlib==0.8.0) over the
    first-seen committed population. kind is ignored when a
    built search is passed.

    Audit cost note: live views here are caller-rebuilt dicts
    (ingest/maint refetch per doc), so the seq audit runs per
    call -- O(N) SCALAR work (id/seq compares, no vector
    fetches, no artifact reads), honestly reported (audit_live
    counts). The O(1) cached audit (LiveAuditCache) applies to
    the serving legs (index.py), whose live objects are
    build-stable. Vector work on every leg is bounded by the
    discovery budget.
    """

    def __init__(self, search=None, kind="partition", k=200,
                 ef=None, include_unpublished=True, max_rounds=3,
                 strict_generation=False, generation=None,
                 counters=None):
        self._search = search
        self.kind = kind
        self.k = int(k)
        self.ef = ef
        self.include_unpublished = include_unpublished
        self.max_rounds = max(1, int(max_rounds))
        self.strict_generation = bool(strict_generation)
        self._expected = generation
        self.counters = counters if counters is not None \
            else NavCounters()
        self._ord = {}  # hid -> published label (incremental)
        self._ord_n = 0
        self._ord_gen = None

    @property
    def search(self):
        """The wrapped backend index (None until first discover
        when lazily built)."""
        return self._search

    def _ensure_search(self, committed):
        if self._search is not None:
            return self._search
        if self.kind == "partition":
            backend = PartitionCandidateIndex()
        elif self.kind == "hnsw":
            from tlsys.hnsw_candidates import HolonCandidateIndex
            backend = HolonCandidateIndex()
        else:
            raise ValueError(f"unknown navigator kind: {self.kind!r}")
        tag = self._expected or "m1c-nav:floating"
        backend.build({h: {"descriptor": v["descriptor"],
                           "seq": v.get("seq")}
                       for h, v in committed.items()}, tag)
        self._search = backend
        if self._expected is None:
            self._expected = tag
        return backend

    def _ordinals_sync(self, search):
        # Incremental: labels only append (add never reorders),
        # so consume the new tail; a generation/tag change resets.
        if search.generation != self._ord_gen:
            self._ord = {}
            self._ord_n = 0
            self._ord_gen = search.generation
        hids = search.hids
        for lab in range(self._ord_n, len(hids)):
            self._ord[hids[lab]] = lab
        self._ord_n = len(hids)
        return self._ord

    def ordinal_key(self, hid):
        """Stable sort key: (0, published label) when indexed,
        (1, hid) for unindexed (pending/unpublished) tail."""
        lab = self._ord.get(hid)
        if lab is None:
            return (1, hid)
        return (0, lab)

    def discover(self, qvec, live, exclude=(), k_hint=None):
        """One bounded discovery round -> (new_ids, report).

        exclude: ids already rescored (replenish rounds skip
        them). k_hint: this round's discovery k (default self.k).
        new_ids are unseen live ids (native discovery plus the
        stale/pending union when include_unpublished is True).
        The report carries discovered/unioned/new counts, the
        explicit changed_ids set, stale/pending classes, audit
        sizes, and native search accounting.
        """
        kh = self.k if k_hint is None else max(0, int(k_hint))
        excluded = set(exclude)
        committed = {h: v for h, v in live.items()
                     if v.get("seq") is not None}
        pending = sorted(h for h in live
                         if live[h].get("seq") is None)
        search = self._ensure_search(committed)
        audit = search.coverage(committed)
        stale_live = [h for h in audit["stale"] if h in live]
        changed_ids = sorted(set(stale_live)
                             | set(audit["unpublished"]))
        # Committed-but-unpublished entries join the index (same
        # tag) so later rounds/calls discover them natively;
        # pending (seq-less) entries NEVER join -- they are
        # unioned and rescored live every call.
        if audit["unpublished"]:
            search.add({h: {"descriptor": live[h]["descriptor"],
                            "seq": live[h].get("seq")}
                        for h in audit["unpublished"]},
                       search.generation)
        self._ordinals_sync(search)
        q = search.query(qvec=qvec, k=kh, ef=self.ef,
                         generation=(self._expected
                                     if self.strict_generation
                                     else None),
                         live=committed)
        new_ids = [h for h in q["hids"] if h not in excluded]
        unioned = []
        if self.include_unpublished:
            seen = set(q["hids"]) | excluded
            for h in stale_live + pending:
                if h not in seen:
                    seen.add(h)
                    new_ids.append(h)
                    unioned.append(h)
        rep = {"discovered": len(q["hids"]),
               "excluded_dropped": len(q["hids"]) - len(
                   [h for h in q["hids"] if h not in excluded]),
               "unioned": len(unioned),
               "unioned_ids": unioned,
               "new": len(new_ids),
               "k_hint": q["k"], "ef": q["ef"],
               "search_ms": q["ms"],
               "stale_dropped": list(q["stale_dropped"]),
               "stale_rescored_live": stale_live
               if self.include_unpublished else [],
               "pending_live": pending,
               "changed_ids": changed_ids,
               "audit_indexed": audit["indexed"],
               "audit_live": audit["live"],
               "include_unpublished": self.include_unpublished,
               "n_scored_native_unknown":
                   q["n_scored_native_unknown"]}
        for wk in ("cells_scored", "cells_visited",
                   "members_visited", "overshoot"):
            if wk in q:
                rep[wk] = q[wk]
        self.counters.record(
            "place-discover", discovered=rep["discovered"],
            unioned=rep["unioned"], new=rep["new"],
            changed=len(changed_ids),
            audit_live=audit["live"])
        return new_ids, rep


def decide_with_navigator(centroid, xholons, navigator,
                          t_place=T_PLACE, max_m=MAX_XMEMBERSHIPS,
                          max_members=MAX_XHOLON_MEMBERS,
                          stats=None, path="place-nav"):
    """decide() through a CandidateNavigator (M1-C; explicit opt-in).

    Shared driver for synchronous placement (via attach_sync_nav)
    and deferred placement (maint drain): bounded discovery
    rounds (k, 2k, ... up to navigator.max_rounds) with exact
    local rescore (same threshold/cap/full-holon policy as
    decide/rescore_candidates) after every round. Rounds stop
    early when joins reach max_m or no fresh candidates arrive;
    every round's fresh ids are rescored exactly once (no
    rescore repeats across rounds). stats gains the decide
    counters (scored/unknown/full_skipped/visited) plus nav_
    work keys; the navigator counters gain one record per
    placement. Returns [hid] joins.
    """
    seen = set()
    ranked = []  # (score, hid) merged over rounds
    unknown_all = []
    full_total = 0
    rounds = 0
    discovered_total = 0
    unioned_total = 0
    replenished_total = 0
    changed_all = set()
    exhausted = False
    joins = []
    max_r = max(1, int(navigator.max_rounds))
    for rnd in range(max_r):
        new_ids, drep = navigator.discover(
            centroid, xholons, exclude=seen,
            k_hint=navigator.k * (rnd + 1))
        rounds += 1
        discovered_total += drep["discovered"]
        unioned_total += drep["unioned"]
        changed_all.update(drep["changed_ids"])
        fresh = [h for h in new_ids if h not in seen]
        for h in fresh:
            seen.add(h)
        if rnd > 0:
            replenished_total += len(fresh)
        if not fresh:
            exhausted = True
            break
        scored, unknown, full = _score_fresh(
            centroid, xholons, fresh, max_members)
        unknown_all.extend(unknown)
        full_total += full
        ranked.extend((s, hid) for hid, s in scored)
        ranked.sort(key=lambda t: (-t[0],
                                   navigator.ordinal_key(t[1])))
        joins = [hid for _s, hid in ranked[:max_m]
                 if _s >= t_place]
        if len(joins) >= max_m:
            break
        if len(seen) >= len(xholons):
            # Whole live population already rescored (discovery
            # only emits live ids): no fresh candidates can
            # exist; stop without another query round.
            exhausted = True
            break
    # Exact-score ties between fresh ids of different rounds
    # merge by (score, published ordinal) -- the same order a
    # single rescore over the union would emit.
    if stats is not None:
        stats.update({"scored": len(ranked),
                      "unknown": unknown_all,
                      "full_skipped": full_total,
                      "visited": len(ranked) + full_total,
                      "nav_rounds": rounds,
                      "nav_discovered": discovered_total,
                      "nav_unioned": unioned_total,
                      "nav_replenished": replenished_total,
                      "nav_exhausted": exhausted,
                      "nav_changed_ids": sorted(changed_all),
                      "nav_ordinals": "published"})
    navigator.counters.record(
        path, discovered=discovered_total,
        unioned=unioned_total, visited=len(ranked) + full_total,
        rescored=len(ranked), rounds=rounds,
        replenished=replenished_total, joins=len(joins),
        changed=len(changed_all))
    return joins


_SYNC_NAV = None


def attach_sync_nav(navigator):
    """Attach a CandidateNavigator to the sync decide path (M1-C).

    While attached, decide() with candidate_ids=None (the ingest
    sync-placement call shape) discovers through the navigator
    with exact local rescore; detach_sync_nav() restores the
    exact path. One navigator per (store, run); callers detach
    (finally) so no global leaks across runs. Returns navigator.
    """
    global _SYNC_NAV
    _SYNC_NAV = navigator
    return navigator


def detach_sync_nav():
    """Detach the sync navigator; returns it (None if none was)."""
    global _SYNC_NAV
    nav, _SYNC_NAV = _SYNC_NAV, None
    return nav


def sync_nav_active():
    """True while a sync navigator is attached."""
    return _SYNC_NAV is not None


def member_centroid(member_vecs):
    """Fresh centroid over member atom vectors (placement-time)."""
    mat = np.asarray(member_vecs, dtype=np.float64)
    return [float(x) for x in mat.mean(axis=0)]


def join_descriptor(old_descriptor, n_old, new_vecs):
    """Incremental mean descriptor for a join (sync + drain paths).

    old_descriptor: current version descriptor (length n_old members);
    new_vecs: [vec] of joining atoms. Both placement paths MUST use
    this helper so sync and deferred joins publish identical math.
    Matches the exact member mean up to float rounding (O(eps) per
    join); compatibility checks use allclose, never exact equality.
    """
    old_c = np.asarray(old_descriptor, dtype=np.float64)
    new_c = np.asarray(new_vecs, dtype=np.float64).sum(axis=0)
    n_new = len(new_vecs)
    return ((old_c * n_old + new_c) / (n_old + n_new)).tolist()


def xholon_op(holon_id, member_aids, descriptor, store_id,
              prepare_artifact):
    """Versioned cross-doc holon meta op (additive supersession)."""
    from tlsys.ingest import KIND
    meta = {"holon": holon_id, "atom_scheme": ATOM_SCHEME,
            "members": list(member_aids),
            "descriptor": list(descriptor),
            "xdoc_version": 1}
    import json as _json
    mart = prepare_artifact(
        _json.dumps(meta, sort_keys=True).encode(), store_id)
    return {"op_id": uuidv7(),
            "kind": KIND,
            "payload": {"holon": holon_id,
                        "meta_artifact": mart["artifact_id"]},
            "disclosure": {"leg": "place-xdoc", "holon": holon_id},
            "approval_ref": None,
            "artifacts": (mart,)}


# ---- M2-A segment organization --------------------------------------
# Segment-level cross-source leaves ("xseg-") + parent holons ("xpar-")
# with typed child references. Additive alongside the whole-document
# xdoc path above (which keeps its exact behavior): separate id
# namespaces, separate committed meta kind tags, separate readers.
# Versions supersede by seq recency; no committed record is mutated.
# Descriptors are member-mean centroids (join_descriptor math shared
# with xdoc); parent scores are routing guidance only, never served
# as evidence-support scores (see tlsys.query.HierQuery).
SEG_PREFIX = "xseg-"
PARENT_PREFIX = "xpar-"
T_SEG_JOIN = 0.50
T_LEAF = 0.55
MAX_SEG_MEMBERSHIPS = 2
MAX_LEAF_MEMBERS = 25
T_PARENT = 0.45
MAX_PARENT_CHILDREN = 16
MAX_LEAF_PARENTS = 2
SEG_VERSION = 1


def segment_atoms(aids, vecs, t_join=T_SEG_JOIN):
    """Greedy sequential segmentation of one doc's atoms.

    aids/vecs are parallel lists in chunk order. The running exact-mean
    centroid of the current segment admits the next atom while cosine
    >= t_join; otherwise a new segment starts. Deterministic (no RNG,
    no hash order). Returns [segment] as index lists; [] for no atoms.
    Single-topic docs yield one segment; long multi-topic docs yield
    one segment per topic run (plus boundary-mixed atoms joining the
    nearer run).
    """
    if len(aids) != len(vecs):
        raise ValueError(
            f"segment_atoms: {len(aids)} aids vs {len(vecs)} vecs")
    if not aids:
        return []
    mat = np.asarray(vecs, dtype=np.float64)
    segs = [[0]]
    run = mat[0].copy()
    for ix in range(1, len(aids)):
        cent = run / len(segs[-1])
        if _cos(mat[ix], cent) >= t_join:
            segs[-1].append(ix)
            run = run + mat[ix]
        else:
            segs.append([ix])
            run = mat[ix].copy()
    return segs


def read_seg_hierarchy(tlstore, pinned, min_seq=0):
    """{"leaves", "parents"} latest-wins committed hierarchy.

    Same read shape as read_xholons (unbounded min_seq frontiers +
    batched artifact rows). Classification requires the kind tag
    ("seg-leaf"/"seg-parent"), never the bare prefix, so a per-doc
    holon can never be misread as hierarchy. Scheme mismatches on
    our namespaces raise, like read_xholons.
    """
    birth, epoch, mx, _triple = pinned
    rows = tlstore.read_commits_all(birth, epoch, mx,
                                    kind="ACCEPT_ATOMS",
                                    min_seq=min_seq)
    seqs = [r[0] for r in rows]
    refs = tlstore.pub_refs(seqs)
    arows = tlstore.artifact_rows(
        [a for seq in seqs for a in refs.get(seq, [])])
    leaves, parents = {}, {}
    for seq in seqs:
        for art_id in refs.get(seq, []):
            arow = arows.get(art_id)
            if arow is None:
                continue
            body = tlstore.read_artifact(art_id,
                                         expect_digest=arow[4])
            try:
                meta = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            hid = meta.get("holon")
            kind = meta.get("kind")
            if "local_repair" in meta:
                from tlsys.local_repair import membership_metas
                for entry in membership_metas(meta):
                    key = "leaves" if entry["kind"] == "seg-leaf" else "parents"
                    target = leaves if key == "leaves" else parents
                    target[entry["holon"]] = {
                        k: v for k, v in entry.items()
                        if k not in ("holon", "kind", "atom_scheme")}
                    target[entry["holon"]]["seq"] = seq
                continue
            if not isinstance(hid, str):
                continue
            if kind == "seg-leaf" and hid.startswith(SEG_PREFIX):
                if meta.get("atom_scheme") != ATOM_SCHEME:
                    raise ValueError(
                        f"op seq {seq}: seg-leaf meta scheme "
                        f"{meta.get('atom_scheme')!r} != {ATOM_SCHEME!r}")
                leaves[hid] = {
                    "members": list(meta.get("members", [])),
                    "descriptor": list(meta.get("descriptor", [])),
                    "segments": list(meta.get("segments", [])),
                    "seq": seq}
            elif kind == "seg-parent" and hid.startswith(PARENT_PREFIX):
                if meta.get("atom_scheme") != ATOM_SCHEME:
                    raise ValueError(
                        f"op seq {seq}: seg-parent meta scheme "
                        f"{meta.get('atom_scheme')!r} != {ATOM_SCHEME!r}")
                parents[hid] = {
                    "members": list(meta.get("members", [])),
                    "children": list(meta.get("children", [])),
                    "descriptor": list(meta.get("descriptor", [])),
                    "seq": seq}
    return {"leaves": leaves, "parents": parents}


def decide_leaf(centroid, leaves, t_leaf=T_LEAF,
                max_m=MAX_SEG_MEMBERSHIPS,
                max_members=MAX_LEAF_MEMBERS, stats=None):
    """Return [leaf_id] a segment joins (ranked, capped) or [] for new.

    Same policy shape as decide(): cosine threshold, membership cap,
    full leaves skipped (capacity overflow is handled by the caller
    via stats["full_qualifying"], the ranked qualifying-but-full
    leaves). Stable deterministic order (score desc, live order ties).
    """
    scored = sorted(
        ((lid, _cos(centroid, lf["descriptor"]))
         for lid, lf in leaves.items()
         if len(lf["members"]) < max_members),
        key=lambda kv: -kv[1])
    full_q = sorted(
        ((lid, _cos(centroid, lf["descriptor"]))
         for lid, lf in leaves.items()
         if len(lf["members"]) >= max_members),
        key=lambda kv: -kv[1])
    full_qualifying = [lid for lid, s in full_q if s >= t_leaf]
    if stats is not None:
        stats.update({"scored": len(scored), "unknown": [],
                      "full_skipped": sum(
                          1 for lf in leaves.values()
                          if len(lf["members"]) >= max_members),
                      "full_qualifying": full_qualifying})
    return [lid for lid, s in scored[:max_m] if s >= t_leaf]


def _score_fresh_children(leaf_desc, live, fresh_ids,
                          max_children):
    """Direct-fetch exact parent scores ([(pid, cos)], unknown, full).

    Same keyed-fetch shape as _score_fresh, but capacity is the
    parent children cap (len(children) >= max_children skips),
    matching decide_parent's eligibility rule.
    """
    scored = []
    unknown = []
    full = 0
    for pid in fresh_ids:
        par = live.get(pid)
        if par is None:
            unknown.append(pid)
            continue
        if len(par["children"]) >= max_children:
            full += 1
            continue
        scored.append((pid, _cos(leaf_desc, par["descriptor"])))
    return scored, unknown, full


def decide_leaf_with_navigator(centroid, leaves, navigator,
                               t_leaf=T_LEAF,
                               max_m=MAX_SEG_MEMBERSHIPS,
                               max_members=MAX_LEAF_MEMBERS,
                               stats=None, path="place-seg-leaf-nav"):
    """decide_leaf() through a CandidateNavigator (M2-C; opt-in).

    Same driver shape as decide_with_navigator: bounded discovery
    rounds (k, 2k, ...) with exact local rescore (same threshold/
    membership-cap policy as decide_leaf) after every round; every
    round's fresh ids are rescored exactly once. Full-but-
    qualifying leaves are scored exactly when nominated (they feed
    stats["full_qualifying"] for the caller's overflow path);
    un-nominated full leaves are undiscovered, honestly reported
    via nav_exhausted=False + the nav work keys. stats gains the
    decide counters plus nav_ work keys; the navigator counters
    gain one record per placement. Returns [leaf_id] joins.
    """
    seen = set()
    ranked = []
    unknown_all = []
    full_q = {}
    rounds = 0
    discovered_total = 0
    unioned_total = 0
    replenished_total = 0
    changed_all = set()
    exhausted = False
    joins = []
    max_r = max(1, int(navigator.max_rounds))
    for rnd in range(max_r):
        new_ids, drep = navigator.discover(
            centroid, leaves, exclude=seen,
            k_hint=navigator.k * (rnd + 1))
        rounds += 1
        discovered_total += drep["discovered"]
        unioned_total += drep["unioned"]
        changed_all.update(drep["changed_ids"])
        fresh = [h for h in new_ids if h not in seen]
        for h in fresh:
            seen.add(h)
        if rnd > 0:
            replenished_total += len(fresh)
        if not fresh:
            exhausted = True
            break
        scored, unknown, _full = _score_fresh(
            centroid, leaves, fresh, max_members)
        unknown_all.extend(unknown)
        # Exact-score nominated full leaves for the overflow rule
        # (same >= t_leaf qualification as decide_leaf).
        for hid in fresh:
            lf = leaves.get(hid)
            if lf is None or hid in full_q:
                continue
            if len(lf["members"]) >= max_members:
                s = _cos(centroid, lf["descriptor"])
                if s >= t_leaf:
                    full_q[hid] = s
        ranked.extend((s, hid) for hid, s in scored)
        ranked.sort(key=lambda t: (-t[0],
                                   navigator.ordinal_key(t[1])))
        joins = [hid for _s, hid in ranked[:max_m]
                 if _s >= t_leaf]
        if len(joins) >= max_m:
            break
        if len(seen) >= len(leaves):
            exhausted = True
            break
    full_qualifying = sorted(full_q, key=lambda h: (-full_q[h], h))
    if stats is not None:
        stats.update({"scored": len(ranked),
                      "unknown": unknown_all,
                      "full_skipped": sum(
                          1 for lf in leaves.values()
                          if len(lf["members"]) >= max_members),
                      "full_qualifying": full_qualifying,
                      "nav_rounds": rounds,
                      "nav_discovered": discovered_total,
                      "nav_unioned": unioned_total,
                      "nav_replenished": replenished_total,
                      "nav_exhausted": exhausted,
                      "nav_changed_ids": sorted(changed_all),
                      "nav_ordinals": "published"})
    navigator.counters.record(
        path, discovered=discovered_total,
        unioned=unioned_total, visited=len(ranked),
        rescored=len(ranked), rounds=rounds,
        replenished=replenished_total, joins=len(joins),
        changed=len(changed_all))
    return joins


def decide_parent_with_navigator(leaf_desc, parents, navigator,
                                 t_parent=T_PARENT,
                                 max_m=MAX_LEAF_PARENTS,
                                 max_children=MAX_PARENT_CHILDREN,
                                 stats=None,
                                 path="place-seg-parent-nav"):
    """decide_parent() through a CandidateNavigator (M2-C; opt-in).

    Same driver shape as decide_leaf_with_navigator over parent
    descriptors with the children-cap eligibility rule. stats and
    navigator counters gain the same nav work keys. Returns
    [parent_id] joins.
    """
    seen = set()
    ranked = []
    unknown_all = []
    full_total = 0
    rounds = 0
    discovered_total = 0
    unioned_total = 0
    replenished_total = 0
    changed_all = set()
    exhausted = False
    joins = []
    max_r = max(1, int(navigator.max_rounds))
    for rnd in range(max_r):
        new_ids, drep = navigator.discover(
            leaf_desc, parents, exclude=seen,
            k_hint=navigator.k * (rnd + 1))
        rounds += 1
        discovered_total += drep["discovered"]
        unioned_total += drep["unioned"]
        changed_all.update(drep["changed_ids"])
        fresh = [h for h in new_ids if h not in seen]
        for h in fresh:
            seen.add(h)
        if rnd > 0:
            replenished_total += len(fresh)
        if not fresh:
            exhausted = True
            break
        scored, unknown, full = _score_fresh_children(
            leaf_desc, parents, fresh, max_children)
        unknown_all.extend(unknown)
        full_total += full
        ranked.extend((s, hid) for hid, s in scored)
        ranked.sort(key=lambda t: (-t[0],
                                   navigator.ordinal_key(t[1])))
        joins = [hid for _s, hid in ranked[:max_m]
                 if _s >= t_parent]
        if len(joins) >= max_m:
            break
        if len(seen) >= len(parents):
            exhausted = True
            break
    if stats is not None:
        stats.update({"scored": len(ranked),
                      "unknown": unknown_all,
                      "full_skipped": full_total,
                      "nav_rounds": rounds,
                      "nav_discovered": discovered_total,
                      "nav_unioned": unioned_total,
                      "nav_replenished": replenished_total,
                      "nav_exhausted": exhausted,
                      "nav_changed_ids": sorted(changed_all),
                      "nav_ordinals": "published"})
    navigator.counters.record(
        path, discovered=discovered_total,
        unioned=unioned_total, visited=len(ranked) + full_total,
        rescored=len(ranked), rounds=rounds,
        replenished=replenished_total, joins=len(joins),
        changed=len(changed_all))
    return joins


def decide_parent(leaf_desc, parents, t_parent=T_PARENT,
                  max_m=MAX_LEAF_PARENTS,
                  max_children=MAX_PARENT_CHILDREN, stats=None):
    """Return [parent_id] a leaf joins (ranked, capped) or [] for new.

    Same policy shape as decide_leaf over parent descriptors; parents
    at the children cap are skipped (callers mint a new parent).
    """
    scored = sorted(
        ((pid, _cos(leaf_desc, par["descriptor"]))
         for pid, par in parents.items()
         if len(par["children"]) < max_children),
        key=lambda kv: -kv[1])
    if stats is not None:
        stats.update({"scored": len(scored), "unknown": [],
                      "full_skipped": sum(
                          1 for par in parents.values()
                          if len(par["children"]) >= max_children)})
    return [pid for pid, s in scored[:max_m] if s >= t_parent]


def seg_leaf_id(doc_id, seg_ix):
    """Deterministic leaf id for a doc's segment index."""
    return f"{SEG_PREFIX}{doc_id}-s{seg_ix}"


def seg_parent_id(first_child_leaf_id):
    """Deterministic parent id derived from its first child leaf."""
    stem = first_child_leaf_id
    if stem.startswith(SEG_PREFIX):
        stem = stem[len(SEG_PREFIX):]
    return f"{PARENT_PREFIX}{stem}"


def overflow_leaf_id(base_leaf_id, n):
    """Deterministic nth overflow-sibling id for a full leaf (n >= 1)."""
    return f"{base_leaf_id}-ov{n}"


def leaf_op(leaf_id, member_aids, descriptor, store_id,
            prepare_artifact, segments=None):
    """Versioned segment-leaf meta op (additive supersession).

    segments: [{doc, aids, spans}] provenance records, one per placed
    segment (bounded by membership). Same ACCEPT_ATOMS authority as
    xholon_op; disclosure leg "place-seg-leaf".
    """
    from tlsys.ingest import KIND
    meta = {"holon": leaf_id, "atom_scheme": ATOM_SCHEME,
            "kind": "seg-leaf",
            "members": list(member_aids),
            "descriptor": list(descriptor),
            "seg_version": SEG_VERSION,
            "segments": list(segments or [])}
    import json as _json
    mart = prepare_artifact(
        _json.dumps(meta, sort_keys=True).encode(), store_id)
    return {"op_id": uuidv7(),
            "kind": KIND,
            "payload": {"holon": leaf_id,
                        "meta_artifact": mart["artifact_id"]},
            "disclosure": {"leg": "place-seg-leaf", "holon": leaf_id},
            "approval_ref": None,
            "artifacts": (mart,)}


def parent_op(parent_id, child_ids, member_aids, descriptor, store_id,
              prepare_artifact):
    """Versioned parent-holon meta op (additive supersession).

    members MUST equal the union of children's members; descriptor is
    the exact member mean (callers use join_descriptor). children are
    typed child-holon references (leaves, or parents in deeper
    builds). Disclosure leg "place-seg-parent".
    """
    from tlsys.ingest import KIND
    meta = {"holon": parent_id, "atom_scheme": ATOM_SCHEME,
            "kind": "seg-parent",
            "members": list(member_aids),
            "children": list(child_ids),
            "descriptor": list(descriptor),
            "seg_version": SEG_VERSION}
    import json as _json
    mart = prepare_artifact(
        _json.dumps(meta, sort_keys=True).encode(), store_id)
    return {"op_id": uuidv7(),
            "kind": KIND,
            "payload": {"holon": parent_id,
                        "meta_artifact": mart["artifact_id"]},
            "disclosure": {"leg": "place-seg-parent",
                           "holon": parent_id},
            "approval_ref": None,
            "artifacts": (mart,)}


# ---- C2 Lane O catalog routing (additive; reference paths untouched) --
# decide_catalog / decide_leaf_catalog / decide_parent_catalog mirror
# decide / decide_leaf / decide_parent exactly (same thresholds, caps,
# full-population policy, stats keys, tie order) but score through a
# tlsys.catalog.Catalog (exact float64 scan, counted rows/bytes) instead
# of the per-row python loop. The catalog is duck-typed (no import: the
# shipped candidate must not depend on coordination/ layout); callers
# pass a Catalog synced with the live overlay (same ids, descriptors,
# counts, and insertion order). These run ONLY behind the profile flag
# `organization_catalog_routing`; flag-off call sites keep calling the
# reference functions above, bit-identical to before. Catalog routing
# does not compose with navigators (explicit candidate_ids or an
# attached sync navigator): those combinations fail closed.
def _catalog_guard(candidate_ids):
    if candidate_ids is not None:
        raise ValueError(
            "catalog routing does not take explicit candidate_ids")
    if _SYNC_NAV is not None:
        raise ValueError(
            "catalog routing does not compose with an attached "
            "sync navigator")


def decide_catalog(centroid, cat, t_place=T_PLACE,
                   max_m=MAX_XMEMBERSHIPS,
                   max_members=MAX_XHOLON_MEMBERS, stats=None,
                   counters=None, candidate_ids=None):
    """decide() through a catalog (Lane O; flag-gated mirror).

    cat: Catalog over the xholon population synced with the decision
    population (counts mirror len(members)). Returns [xholon_id] and
    fills stats with the identical keys as decide().
    """
    _catalog_guard(candidate_ids)
    mask = cat.mask_lt(max_members)
    joins, info = cat.top_k(centroid, max_m, mask,
                            threshold=t_place, counters=counters)
    if stats is not None:
        stats.update({"scored": info["rows_scanned"], "unknown": [],
                      "full_skipped": cat.n - info["rows_scanned"],
                      "catalog_rows": info["rows_scanned"]})
        if info["ties_at_cutoff"] or info["near_threshold"]:
            stats["catalog_ties"] = {
                "at_cutoff": info["ties_at_cutoff"],
                "near_threshold": info["near_threshold"]}
        if info["budget_exceeded"]:
            stats["catalog_budget_exceeded"] = True
    return joins


def decide_leaf_catalog(centroid, cat, t_leaf=T_LEAF,
                        max_m=MAX_SEG_MEMBERSHIPS,
                        max_members=MAX_LEAF_MEMBERS, stats=None,
                        counters=None):
    """decide_leaf() through a catalog (Lane O; flag-gated mirror).

    cat: Catalog over the leaf population (counts mirror
    len(members)). stats gains the identical keys as decide_leaf(),
    including the ranked full_qualifying list (second exact scan over
    the full rows, same (score desc, ordinal asc) order).
    """
    mask = cat.mask_lt(max_members)
    joins, info = cat.top_k(centroid, max_m, mask,
                            threshold=t_leaf, counters=counters)
    full_ids, full_info = cat.top_k(centroid, cat.n,
                                    cat.mask_ge(max_members),
                                    threshold=t_leaf,
                                    counters=counters)
    if stats is not None:
        stats.update({"scored": info["rows_scanned"], "unknown": [],
                      "full_skipped": cat.n - info["rows_scanned"],
                      "full_qualifying": full_ids,
                      "catalog_rows": info["rows_scanned"]
                      + full_info["rows_scanned"]})
        ties = bool(info["ties_at_cutoff"]
                    or info["near_threshold"]
                    or full_info["ties_at_cutoff"]
                    or full_info["near_threshold"])
        if ties:
            stats["catalog_ties"] = {
                "at_cutoff": info["ties_at_cutoff"],
                "near_threshold": info["near_threshold"],
                "full_at_cutoff": full_info["ties_at_cutoff"],
                "full_near_threshold":
                    full_info["near_threshold"]}
        if info["budget_exceeded"] or full_info["budget_exceeded"]:
            stats["catalog_budget_exceeded"] = True
    return joins


def decide_parent_catalog(leaf_desc, cat, t_parent=T_PARENT,
                          max_m=MAX_LEAF_PARENTS,
                          max_children=MAX_PARENT_CHILDREN, stats=None,
                          counters=None):
    """decide_parent() through a catalog (Lane O; flag-gated mirror).

    cat: Catalog over the parent population (counts mirror
    len(children)). stats gains the identical keys as decide_parent().
    """
    mask = cat.mask_lt(max_children)
    joins, info = cat.top_k(leaf_desc, max_m, mask,
                            threshold=t_parent, counters=counters)
    if stats is not None:
        stats.update({"scored": info["rows_scanned"], "unknown": [],
                      "full_skipped": cat.n - info["rows_scanned"],
                      "catalog_rows": info["rows_scanned"]})
        if info["ties_at_cutoff"] or info["near_threshold"]:
            stats["catalog_ties"] = {
                "at_cutoff": info["ties_at_cutoff"],
                "near_threshold": info["near_threshold"]}
        if info["budget_exceeded"]:
            stats["catalog_budget_exceeded"] = True
    return joins
