"""Row-budgeted exact descriptor catalogs for C2 organization (Lane O).

A Catalog is the C2 replacement for the per-row python cosine loops in
placement/organization (arch v1.1 section 3.5.1): one contiguous float64
descriptor table per population (xholons, leaves, parents, doc holons)
with a published ordinal map, amortized-doubling append, in-place update
on joins, and an exact top_k with deterministic order (score desc,
published ordinal asc). Every scan is counted (rows, bytes) and bounded
by the profile row budget R_cat.

Ownership/lifecycle: Catalogs are caller-owned values (one per ingest /
organize / drain call). No module-global mutable catalog state exists or
may be added here: nothing is shared across runs or generations (frozen
v1 rule). Callers create, sync incrementally (O(new versions) per doc),
and discard them with the call.

Profile/counters consumption (Lane G sole writer; read-only here): the
profile arrives as a plain dict produced/validated by Lane G's
profile.py; counters arrive as an object with .inc(key, n) (Lane G's
Counters). This module imports neither (the shipped candidate must not
depend on coordination/ layout) and copies/forks neither. Key spellings
follow profile-counters.md section 3 exactly.

Numerics: scores are float64 cosines computed as dots/(norm*qn) with
norms identical to place._cos (float(linalg.norm) or 1.0). The matvec
may differ from the per-row ddot in float summation order (last-ulp),
so exact-threshold ties are detected and reported for D2 tie
classification; ranking is by (-score, ordinal), which equals the old
stable-sort-by-(-score) over insertion order whenever ordinals equal
insertion order (the only order catalogs are ever built in).

This module also holds the small Lane O working-state mechanisms wired
into maint.py / ingest.py behind the profile flag: TouchMap (copy-on-
write overlay of touched ids), OverlayView (read-only union with exact
dict-copy order, no copy), LeafParentIndex (keyed leaf->parents /
parent->children membership), MemberIndex (per-parent member sets with
multiplicity), OverflowCounters (per-base sibling numbering), and
AtomIndex (keyed atom->owner membership). All are caller-owned, support
per-doc begin/rollback where the call site rolls back, and reproduce the
reference behavior exactly (D2 parity).
"""

import numpy as np
from collections.abc import Mapping

POPULATIONS = ("xholon", "leaf", "parent", "doc")

SCORING_LEG = {"xholon": "place_xdoc", "leaf": "place_leaf",
               "parent": "place_parent", "doc": None}

# Near-tie qualification bound (frozen v1: exact/near ties <= 1e-12 are
# the only admitted tie qualification for parity classification).
TIE_EPS = 1e-12

# Dense-mask scoring crossover (Lane O-4; performance only, exactness-free).
# A masked matvec can either fancy-index the descriptor block first (copy
# cost ~2*rows*dim*8 bytes read+write plus rows*dim*8 matvec re-read) or
# run one full contiguous matvec and select the masked scores after
# (~n*dim*8 descriptor read, zero descriptor copy). Both compute each
# row's dot from identical float64 inputs, so scores are bitwise
# identical; the full scan wins when rows/n > ~1/3 at dim=384, hence the
# crossover 3*rows >= n below. Either branch preserves D2 parity exactly.
_DENSE_COPY_NUM = 3

_MISSING = object()


def _rank_head(qvals, qords, k):
    """Partition-based exact head of qualifying rows (Lane O-4).

    qvals: float64 qualifying scores in ascending-ordinal order;
    qords: their ordinals; k: 0 < k < len(qvals). Returns
    (picked_ordinals, picked_scores, next_ord, next_score) where the
    picked head equals the full stable desc sort's first k rows and
    (next_ord, next_score) is the full stable sort's row k (the first
    excluded row). Exact-tie rule: the head set is {scores > c} union
    {scores == c} with c the k-th largest value (exact float64
    comparison), stable-sorted; every non-head row is strictly below
    c, so the head's first k rows match the full sort's first k, and
    the first excluded row is either the head's row k or the
    ordinal-first argmax of the below-cutoff tail.
    """
    m_qual = int(qvals.shape[0])
    c = np.partition(qvals, m_qual - k)[m_qual - k]
    hp = np.nonzero(qvals >= c)[0]
    horder = np.argsort(-qvals[hp], kind="stable")
    head = hp[horder]
    picked = qords[head[:k]]
    pscores = qvals[head[:k]]
    if head.shape[0] > k:
        next_ord = qords[head[k]]
        next_score = float(qvals[head[k]])
    else:
        below = qvals < c
        j = int(np.argmax(np.where(below, qvals, -np.inf)))
        next_ord = qords[j]
        next_score = float(qvals[j])
    return picked, pscores, next_ord, next_score


def _norm_of(desc):
    """place._cos-identical norm: float(linalg.norm) with zero -> 1.0."""
    return float(np.linalg.norm(np.asarray(desc, dtype=np.float64))) or 1.0


def catalog_routing_enabled(profile):
    """True iff profile routes organization decisions through catalogs.

    profile=None (or a missing/false flag) selects the exact C1
    reference path. A non-dict profile, or a true flag without a valid
    R_cat, fails closed (ValueError) rather than silently degrading.
    """
    if profile is None:
        return False
    if not isinstance(profile, dict):
        raise ValueError("profile must be a dict or None")
    flags = profile.get("flags")
    if not isinstance(flags, dict):
        raise ValueError("profile['flags'] must be a dict")
    on = flags.get("organization_catalog_routing", False)
    if on not in (True, False):
        raise ValueError(
            "profile flag 'organization_catalog_routing' must be a bool")
    if on:
        catalog_row_budget(profile)  # fail closed now, not mid-call
    return on


def catalog_row_budget(profile):
    """R_cat from a validated profile dict (positive int required)."""
    try:
        rcat = profile["derived_limits"]["R_cat"]
    except (KeyError, TypeError):
        raise ValueError("profile lacks derived_limits.R_cat")
    if not isinstance(rcat, int) or isinstance(rcat, bool) or rcat <= 0:
        raise ValueError("profile derived_limits.R_cat must be "
                         "a positive int")
    return rcat


class Catalog:
    """Contiguous float64 descriptor table with ordinals + counted scans.

    Counts (len(members) / len(children)) mirror the caller's live
    overlay exactly: every build/upsert carries the count the reference
    path would read from the entry, so eligibility masks reproduce the
    reference eligibility row for row. The catalog never reads the live
    overlay itself (no aliasing, no generation sharing).
    """

    def __init__(self, population, dim, row_budget):
        if population not in POPULATIONS:
            raise ValueError(f"unknown catalog population {population!r}")
        if not isinstance(dim, int) or dim <= 0:
            raise ValueError("dim must be a positive int")
        if not isinstance(row_budget, int) or row_budget <= 0:
            raise ValueError("row_budget must be a positive int")
        self.population = population
        self.dim = dim
        self.row_budget = row_budget
        self._cap = 256
        self._n = 0
        self._mat = np.zeros((self._cap, dim), dtype=np.float64)
        self._norms = np.ones((self._cap,), dtype=np.float64)
        self._counts = np.zeros((self._cap,), dtype=np.int64)
        self._ids = []
        self._ordinal = {}
        self._snap = None
        self.budget_exceeded = False
        self.total_rows = 0
        self.total_bytes = 0
        self.total_calls = 0
        # O-7 executed-vs-eligible accounting (counting only): eligible
        # totals above keep their reference-eval semantics (rows ==
        # reference evals; Lane-G keys unchanged); the executed totals
        # below record what the matvec natively ran (dense path: all
        # n rows) plus the logical read/copy/write bytes (O-4 §3.2
        # ledger semantics, productionized per call).
        self.total_executed_rows = 0
        self.total_descriptor_read_B = 0
        self.total_copy_B = 0
        self.total_logical_read_B = 0
        self.total_logical_written_B = 0

    @property
    def n(self):
        return self._n

    @property
    def ids(self):
        return tuple(self._ids)

    def __contains__(self, hid):
        return hid in self._ordinal

    def __len__(self):
        return self._n

    def ordinal(self, hid):
        return self._ordinal[hid]

    def count_of(self, hid):
        return int(self._counts[self._ordinal[hid]])

    def _grow(self):
        cap2 = self._cap * 2
        mat = np.zeros((cap2, self.dim), dtype=np.float64)
        mat[:self._cap] = self._mat
        norms = np.ones((cap2,), dtype=np.float64)
        norms[:self._cap] = self._norms
        counts = np.zeros((cap2,), dtype=np.int64)
        counts[:self._cap] = self._counts
        self._mat, self._norms, self._counts = mat, norms, counts
        self._cap = cap2

    def _check_desc(self, descriptor):
        vec = np.asarray(descriptor, dtype=np.float64)
        if vec.shape != (self.dim,):
            raise ValueError(
                f"catalog {self.population}: descriptor dim "
                f"{vec.shape} != {self.dim}")
        return vec

    def build(self, entries):
        """Populate an empty catalog from (hid, descriptor, count) rows.

        entries order is the published ordinal order: callers MUST pass
        live-overlay insertion order so ordinals reproduce the reference
        stable-sort tie order. Empty input is a valid empty build.
        """
        if self._n:
            raise ValueError("build() on a non-empty catalog")
        for hid, desc, count in entries:
            self.upsert(hid, desc, count)
        return self

    def upsert(self, hid, descriptor, count):
        """Append a new id or update an existing row in place.

        Updates keep the row (ordinal stability); appends extend the
        published order. Per-doc rollback snapshots pre-doc rows via
        begin_doc()/rollback().
        """
        if not isinstance(count, int) or count < 0:
            raise ValueError("count must be a non-negative int")
        vec = self._check_desc(descriptor)
        row = self._ordinal.get(hid)
        if row is None:
            if self._n == self._cap:
                self._grow()
            row = self._n
            self._ordinal[hid] = row
            self._ids.append(hid)
            self._n += 1
        elif self._snap is not None and row not in self._snap[1]:
            self._snap[1][row] = (self._mat[row].copy(),
                                  float(self._norms[row]),
                                  int(self._counts[row]))
        self._mat[row] = vec
        self._norms[row] = _norm_of(vec)
        self._counts[row] = count
        return row

    def mask_lt(self, cap):
        """Boolean mask of rows with count < cap (eligible rows)."""
        return self._counts[:self._n] < cap

    def mask_ge(self, cap):
        """Boolean mask of rows with count >= cap (full rows)."""
        return self._counts[:self._n] >= cap

    def top_k(self, q, k, mask=None, threshold=None, counters=None,
              tie_eps=TIE_EPS):
        """Exact top-k scan: ([hid], info) in (score desc, ordinal asc).

        q: query vector; k: max ids returned (k<=0 scans but returns
        none, mirroring the reference [:max_m] shape); mask: bool array
        over ordinals (None = all rows); threshold: keep s >= t only.
        Every masked row is scored and counted whether or not it is
        returned. counters: optional Lane G Counters (.inc); per-call
        stats are always in info and on total_rows/total_bytes.

        Exactness (Lane O-4): ids, returned scores, cutoff/next scores,
        ties_at_cutoff, near_threshold and all counts are bitwise
        identical to the Lane O full-scan + full-stable-argsort
        formulation. Two exact levers: (1) dense masks score one full
        contiguous matvec and select after (no descriptor fancy-index
        copy; sparse masks keep the copy, which is cheaper there --
        both compute each row dot from identical inputs, so scores are
        bitwise identical); (2) when fewer than all qualifying rows are
        returned, partition finds the cutoff value and only the
        strictly-greater plus exactly-equal head is stable-sorted, which
        equals the full stable sort's head (proof in the Lane O-4
        report; differential tie tests in test_c2_catalog.py).
        """
        if mask is None:
            idx = np.arange(self._n)
        else:
            m = np.asarray(mask, dtype=bool)
            if m.shape != (self._n,):
                raise ValueError(
                    f"mask shape {m.shape} != catalog n {self._n}")
            idx = np.nonzero(m)[0]
        qv = np.asarray(q, dtype=np.float64)
        if qv.shape != (self.dim,):
            raise ValueError(
                f"query dim {qv.shape} != catalog dim {self.dim}")
        qn = float(np.linalg.norm(qv)) or 1.0
        rows = int(idx.shape[0])
        if rows:
            mat = self._mat[:self._n]
            norms = self._norms[:self._n]
            if rows == self._n or rows * _DENSE_COPY_NUM >= self._n:
                # Dense: one full contiguous matvec, select masked
                # scores after. No descriptor copy.
                scores = (mat @ qv)[idx] / (norms[idx] * qn)
            else:
                # Sparse: fancy-index only the masked block (smaller
                # than a full scan here). Bitwise-identical scores.
                dots = mat[idx] @ qv
                scores = dots / (self._norms[idx] * qn)
            if threshold is not None:
                qp = np.nonzero(scores >= threshold)[0]
                qvals = scores[qp]
                qords = idx[qp]
            else:
                qvals = scores
                qords = idx
        else:
            qvals = np.zeros((0,), dtype=np.float64)
            qords = idx
        m_qual = int(qvals.shape[0])
        if k is None:
            k = m_qual
        if k < 0:
            raise ValueError("k must be >= 0")
        if m_qual > k and k > 0:
            # Partition path: exact head + first excluded row (see
            # _rank_head for the tie rule).
            picked, pscores, next_ord, next_score = _rank_head(
                qvals, qords, k)
            has_next = True
        else:
            # Full-sort path (k == 0, k >= m_qual, or empty): stable
            # sort of the qualifying rows only; identical order to
            # sorting all masked rows and filtering after.
            order = np.argsort(-qvals, kind="stable")
            ranked = qords[order]
            rscores = qvals[order]
            picked = ranked[:k]
            pscores = rscores[:k]
            has_next = rscores.shape[0] > picked.shape[0]
            if has_next:
                next_ord = ranked[picked.shape[0]]
                next_score = float(rscores[picked.shape[0]])
        ids = [self._ids[int(r)] for r in picked]
        row_bytes = self.dim * 8 + 8  # matrix row + norm
        byte_n = rows * row_bytes
        # -- O-7 executed-vs-eligible counting (counting only; the --
        # -- scoring/selection above is untouched) --------------------
        # Executed native rows re-evaluate the O-4 dense predicate
        # (read-only): the dense path runs one full n-row matvec and
        # selects after, so all n rows execute; the sparse path
        # fancy-indexes only the eligible block. rows == 0 executes
        # nothing (the matvec above is guarded by `if rows:`).
        # Byte semantics are O-4 §3.2 productionized: descriptor_read
        # (matvec operand read), copy (fancy-index read+write, sparse
        # path only), scores/norms vector traffic, analytic sort-temp
        # traffic, folded into logical read/written. A dedicated
        # Lane-G logical-bytes key needs Lane G (sole writer) and is
        # NOT smuggled in here: Lane-G keys below keep eligible units.
        d8 = self.dim * 8
        if rows == 0:
            exec_rows = 0
            desc_read_b = 0
            copy_b = 0
            scores_norms_b = 0
            sort_temp_b = 0
            logical_read_b = 0
            logical_written_b = 0
        else:
            dense_exec = (rows == self._n
                          or rows * _DENSE_COPY_NUM >= self._n)
            if dense_exec:
                exec_rows = self._n
                desc_read_b = self._n * d8
                copy_b = 0
                score_write = self._n * 8 + rows * 8
                score_read = self._n * 8 + rows * 8
                norms_rw = self._n * 8 + rows * 8
            else:
                exec_rows = rows
                desc_read_b = rows * d8
                copy_b = 2 * rows * d8
                score_write = rows * 8
                score_read = rows * 8
                norms_rw = rows * 8 + rows * 8
            scores_norms_b = score_read + score_write + norms_rw
            # Partition predicate mirrors the selection branch above
            # (k already normalized to m_qual when None there).
            if m_qual > k and k > 0:
                sort_temp_b = m_qual * 8 * 3 + 64 * 8
            else:
                sort_temp_b = m_qual * 8 * 4
            logical_read_b = (desc_read_b + score_read + norms_rw
                              + sort_temp_b // 2)
            logical_written_b = score_write + sort_temp_b // 2
        self.total_rows += rows
        self.total_bytes += byte_n
        self.total_calls += 1
        self.total_executed_rows += exec_rows
        self.total_descriptor_read_B += desc_read_b
        self.total_copy_B += copy_b
        self.total_logical_read_B += logical_read_b
        self.total_logical_written_B += logical_written_b
        if counters is not None:
            counters.inc(f"catalog_rows_scanned.{self.population}", rows)
            counters.inc(f"catalog_bytes_touched.{self.population}",
                         byte_n)
            leg = SCORING_LEG[self.population]
            if leg is not None:
                counters.inc(f"scoring_evals.{leg}", rows)
        over = self._n > self.row_budget
        if over:
            self.budget_exceeded = True
        # Tie diagnostics for D2 classification: pairs straddling the
        # return cutoff within tie_eps, and rows near the threshold.
        ties_cutoff = []
        if has_next and len(picked) > 0:
            sa = float(pscores[-1])
            sb = next_score
            if abs(sa - sb) <= tie_eps:
                ties_cutoff.append(
                    (self._ids[int(picked[-1])],
                     self._ids[int(next_ord)], abs(sa - sb)))
        near_threshold = 0
        if threshold is not None and rows:
            near_threshold = int(
                np.sum(np.abs(qvals - threshold) <= tie_eps))
        info = {"rows_scanned": rows, "bytes_touched": byte_n,
                "eligible": rows, "catalog_n": self._n,
                "executed_rows": exec_rows,
                "descriptor_read_B": desc_read_b,
                "copy_B": copy_b,
                "scores_norms_B": scores_norms_b,
                "sort_temp_B": sort_temp_b,
                "logical_read_B": logical_read_b,
                "logical_written_B": logical_written_b,
                "returned": [(h, float(s)) for h, s in zip(ids, pscores)],
                "cutoff_score": float(pscores[-1]) if len(pscores) else None,
                "next_score": next_score if has_next else None,
                "ties_at_cutoff": ties_cutoff,
                "near_threshold": near_threshold,
                "budget_exceeded": over}
        return ids, info

    # -- per-doc snapshot/rollback (organize overlay) --------------------
    def begin_doc(self):
        """Arm per-doc rollback: record n + pre-doc touched rows."""
        self._snap = (self._n, {})

    def rollback(self):
        """Undo this doc's appends + in-place updates (order-preserving).

        Appended rows are truncated (ordinals of surviving rows never
        shift); updated rows restore their pre-doc vector/norm/count.
        Requires begin_doc(); unarmed rollback is a fail-closed error.
        """
        if self._snap is None:
            raise ValueError("catalog rollback without begin_doc")
        n0, touched = self._snap
        self._snap = None
        for hid in self._ids[n0:]:
            del self._ordinal[hid]
        del self._ids[n0:]
        self._n = n0
        for row, (vec, nm, ct) in touched.items():
            self._mat[row] = vec
            self._norms[row] = nm
            self._counts[row] = ct


class TouchMap(dict):
    """A dict recording first-touch per doc for O(touched) rollback.

    Replaces the per-doc dict(live) whole-population snapshots in
    organize_segments. While armed (between begin_doc and rollback),
    the first write to each key records its pre-doc value (or MISSING);
    rollback restores exactly those keys, preserving pre-doc order:
    existing keys keep their positions (dict assignment never moves a
    key), doc-added keys are deleted. Unarmed writes are plain writes.
    """

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._touched = None

    def begin_doc(self):
        self._touched = {}

    def rollback(self):
        if self._touched is None:
            raise ValueError("TouchMap rollback without begin_doc")
        touched, self._touched = self._touched, None
        for k, v in touched.items():
            if v is _MISSING:
                dict.__delitem__(self, k)
            else:
                dict.__setitem__(self, k, v)

    def __setitem__(self, k, v):
        t = self._touched
        if t is not None and k not in t:
            t[k] = self[k] if k in self else _MISSING
        super().__setitem__(k, v)


class OverlayView(Mapping):
    """Read-only base+overlay union with exact dict-copy order, no copy.

    Iterates base keys first, then overlay-only keys -- the exact key
    order of `d = dict(base); d.update(overlay)` -- with overlay
    values winning. Replaces the per-doc dict(xh_cache) copy in
    ingest place_doc. Both maps are read live (no snapshot): the view
    is valid only while neither map is structurally mutated.
    """

    def __init__(self, base, overlay):
        self._base = base
        self._overlay = overlay

    def __getitem__(self, k):
        if k in self._overlay:
            return self._overlay[k]
        return self._base[k]

    def __iter__(self):
        for k in self._base:
            yield k
        for k in self._overlay:
            if k not in self._base:
                yield k

    def __len__(self):
        n = len(self._base)
        for k in self._overlay:
            if k not in self._base:
                n += 1
        return n

    def __contains__(self, k):
        return k in self._overlay or k in self._base


class LeafParentIndex:
    """Keyed leaf->parents / parent->children membership (organize overlay).

    Replaces the `sorted(live_p)` + `child in children` scans in
    _republish_parents and the preferred-parents scan. parents_of(lid)
    returns pids in sorted order -- the exact order of the replaced
    `sorted(live_p)`-filtered loop. Children ORDER still lives in the
    live entries (committed meta order); this index mirrors membership
    only. Per-doc edge additions roll back; v1 never removes edges.
    """

    def __init__(self):
        self._lp = {}  # lid -> set of pids
        self._pc = {}  # pid -> set of lids
        self._added = None

    def build(self, parents_view):
        """Seed from {pid: entry with 'children'} (committed or live)."""
        if self._lp or self._pc:
            raise ValueError("LeafParentIndex.build on a non-empty index")
        for pid, par in parents_view.items():
            kids = set(par.get("children", ()))
            self._pc[pid] = set(kids)
            for lid in kids:
                self._lp.setdefault(lid, set()).add(pid)
        return self

    def parents_of(self, lid):
        return sorted(self._lp.get(lid, ()))

    def has_edge(self, pid, lid):
        return lid in self._pc.get(pid, ())

    def children_of(self, pid):
        return set(self._pc.get(pid, ()))

    def add_edge(self, pid, lid):
        if self._added is not None:
            self._added.append((pid, lid))
        self._pc.setdefault(pid, set()).add(lid)
        self._lp.setdefault(lid, set()).add(pid)

    def begin_doc(self):
        self._added = []

    def rollback(self):
        if self._added is None:
            raise ValueError("LeafParentIndex rollback without begin_doc")
        added, self._added = self._added, None
        for pid, lid in reversed(added):
            kids = self._pc.get(pid)
            if kids is not None:
                kids.discard(lid)
            pars = self._lp.get(lid)
            if pars is not None:
                pars.discard(pid)


class MemberIndex:
    """Per-parent member sets with multiplicity (organize overlay).

    union_of(pid) reproduces set(par['members']) exactly (v1 unions are
    append-only, so the set only grows); multiplicity_of(pid, aid) is
    the number of children whose current members contain aid (overlap
    accounting for FI-16; the union and the exact deduplicated member
    mean are unchanged -- adds still dedupe against the union before
    join_descriptor runs). Per-doc begin/rollback snapshots touched
    pids only (sets/mult dicts are small: parent members <= ~692).
    """

    def __init__(self):
        self._sets = {}   # pid -> set of aids (union)
        self._mult = {}   # pid -> {aid: child count}
        self._snap = None

    def build(self, parents_view, leaves_view):
        """Seed unions from parent members; mults from child members."""
        if self._sets or self._mult:
            raise ValueError("MemberIndex.build on a non-empty index")
        for pid, par in parents_view.items():
            self._sets[pid] = set(par.get("members", ()))
            mult = {}
            for lid in par.get("children", ()):
                leaf = leaves_view.get(lid)
                if leaf is None:
                    continue
                for aid in leaf.get("members", ()):
                    mult[aid] = mult.get(aid, 0) + 1
            self._mult[pid] = mult
        return self

    def _touch(self, pid):
        if self._snap is not None and pid not in self._snap:
            if pid in self._sets:
                self._snap[pid] = (set(self._sets[pid]),
                                   dict(self._mult[pid]))
            else:
                self._snap[pid] = None

    def ensure(self, pid, members=()):
        """Register a (possibly new) parent; union starts at members."""
        self._touch(pid)
        if pid not in self._sets:
            self._sets[pid] = set(members)
            self._mult[pid] = {}
        return pid

    def contains(self, pid, aid):
        return aid in self._sets.get(pid, ())

    def union_of(self, pid):
        return set(self._sets.get(pid, ()))

    def multiplicity_of(self, pid, aid):
        return self._mult.get(pid, {}).get(aid, 0)

    def add(self, pid, aid):
        """Record aid arriving via one more child (union + mult)."""
        self._touch(pid)
        self._sets.setdefault(pid, set()).add(aid)
        mult = self._mult.setdefault(pid, {})
        mult[aid] = mult.get(aid, 0) + 1

    def begin_doc(self):
        self._snap = {}

    def rollback(self):
        if self._snap is None:
            raise ValueError("MemberIndex rollback without begin_doc")
        snap, self._snap = self._snap, None
        for pid, saved in snap.items():
            if saved is None:
                self._sets.pop(pid, None)
                self._mult.pop(pid, None)
            else:
                self._sets[pid], self._mult[pid] = saved


class OverflowCounters:
    """Per-base overflow-sibling numbering without startswith scans.

    next_n(base, live) returns the exact n the reference path computes
    as 1 + #{k in live : k startswith base + '-ov'}: the count is taken
    once per base (lazily, on first overflow of that base) and then
    incremented per mint, which is equivalent because overflow mints
    are the only writers of `base-ov*` ids. A mint through base B
    also advances every CACHED ancestor entry (prefixes of B before
    a `-ov` occurrence -- the minted `B-ov{n}` id matches those
    stems too, same enumeration as seed()); uncached ancestors stay
    lazy (their later scans see the landed key). Per-doc rollback
    restores touched bases. seed(live) takes every base's baseline
    in ONE pass over the committed view (call once per call, before
    any doc), so steady-state numbering is O(1) per mint with no
    per-base scan.
    """

    def __init__(self):
        self._counts = {}
        self._snap = None

    def seed(self, live):
        """Baseline all bases in one pass (exact startswith semantics).

        Every `-ov` occurrence in a key yields one base (the key
        prefix before it), which is exactly the set of bases whose
        reference startswith count includes that key -- including
        nested overflow ids (`B-ov1-ov2` counts for both `B` and
        `B-ov1`). Idempotent-correct at doc boundaries: re-seeding
        overwrites baselines with current-live counts, which equal
        baseline+mints whenever no doc is mid-flight. Must not be
        called mid-doc (between begin_doc and rollback): it would
        clobber the snapshot the rollback needs.
        """
        if self._snap is not None:
            raise ValueError(
                "OverflowCounters.seed mid-doc (snapshot armed)")
        counts = {}
        for k in live:
            i = k.find("-ov")
            while i != -1:
                base = k[:i]
                counts[base] = counts.get(base, 1) + 1
                i = k.find("-ov", i + 1)
        self._counts.update(counts)
        return len(counts)

    def next_n(self, base, live):
        stem = base + "-ov"
        if base not in self._counts:
            self._counts[base] = 1 + sum(
                1 for k in live if k.startswith(stem))
        if self._snap is not None and base not in self._snap:
            self._snap[base] = self._counts[base]
        n = self._counts[base]
        self._counts[base] = n + 1
        # Nested-mint propagation (O-5): the minted `base-ov{n}` id
        # also matches every ancestor stem (prefixes of base before
        # a `-ov` occurrence -- same enumeration as seed()). Cached
        # ancestor counts must advance too, else the next mint
        # through an ancestor serves a stale n (O-4 §5: keyed 4 vs
        # scan 5). Uncached ancestors stay lazy: their later scans
        # see the landed key, so seeding them here would only cost
        # a scan per nested mint for no gain.
        i = base.find("-ov")
        while i != -1:
            anc = base[:i]
            if anc in self._counts:
                if self._snap is not None and anc not in self._snap:
                    self._snap[anc] = self._counts[anc]
                self._counts[anc] += 1
            i = base.find("-ov", i + 1)
        return n

    def begin_doc(self):
        self._snap = {}

    def rollback(self):
        if self._snap is None:
            raise ValueError("OverflowCounters rollback without begin_doc")
        snap, self._snap = self._snap, None
        for base, n in snap.items():
            self._counts[base] = n


class AtomIndex:
    """Keyed atom->owner membership (drain placed check, no union scans).

    Replaces the per-doc full-population placed_aids union in
    drain_placement_backlog: `aid in idx` answers whether any owner
    holds the atom. Owners only gain members in v1 (no removal, no
    rollback needed at the drain call sites, which mutate only after
    a successful commit).
    """

    def __init__(self):
        self._owner = {}

    def build(self, owners_view):
        """Seed from {oid: entry with 'members'} (first owner wins)."""
        if self._owner:
            raise ValueError("AtomIndex.build on a non-empty index")
        for oid, entry in owners_view.items():
            for aid in entry.get("members", ()):
                self._owner.setdefault(aid, oid)
        return self

    def add(self, oid, aids):
        for aid in aids:
            self._owner.setdefault(aid, oid)

    def __contains__(self, aid):
        return aid in self._owner

    def owner_of(self, aid, default=None):
        return self._owner.get(aid, default)
