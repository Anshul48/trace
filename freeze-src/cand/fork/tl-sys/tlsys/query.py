"""Narrow query path (Q2.1/Q2.2/Q2.3 -> Q3.1/Q3.2/Q3.3 -> Q4.1(a) ->
Q10.2 prune+MMR -> Q11.1 top-K -> Q14 receipt/disclosure + Q15 entries).

OPERATING DEFAULTS ([E]-valued items move only via docket +
frozen-workload re-measurement, Q16.1(d)):
  SEED_LEX=100, SEED_DENSE=100 .... Q2.3(b) [E]
  RRF_K=60 ........................ SETTLED (Q2.2, fixed)
  M_REGIONS=20 .................... Q3.2 M [E] (provisional range 5-20;
                                    10->20 adopted 2026-10-04: train
                                    funnel attribution showed 78% of
                                    dropped golds ranking 10-49; net
                                    +19 total-loss / +174 gain-depth
                                    on 2590q; see S3-REPAIR-DECISION)
  TAU=0, EPS=0 .................... Q3.3 [E], D-1 R1 adopted 2026-09-29:
                                    widening unhelpful on this workload;
                                    mechanism kept, trigger parked (0,0)
  WIDEN_FACTOR=2, WIDEN_CLAMP=40 ... Q3.3(b) [E]
  PRUNE_CAP=50 ..................... Q11.1 prune-output [E]
  MMR_LAMBDA=0.8 ................... Q10.2 lambda [E]
                                    (R1 repair 2026-10-04: 0.5 demoted
                                    top-scored gold in flat score band;
                                    dev P -0.039->-0.023, C1 intact)
  TAU_SEL=0.005, MAX_ENTRIES=10 .... Q12.3 [E], D-1 R2 adopted 2026-09-29
                                    (constrained optimum; identical to 0.0
                                    on tuning; abstention INEFFECTIVE on
                                    rank-only scale — see DOCKET.md)
  WORK_BUDGET=1000000 .............. Q13 work units (generous; eval-scale)

Promoted default (E1, adopted 2026-10-04; cfg can still opt out):
  EMIT_DENSE_ATOMS=True ........... atom emission adds a
                                    dense-atom RRF term (rank-only, k=60)
                                    to the fused lex/holon support, so
                                    lexically-distant atoms in selected
                                    regions can clear admission on dense
                                    support. Region ranking, prune, MMR,
                                    and admission rules are unchanged.
  SEED_DENSE_ATOMS=100 ............ dense-atom rank cutoff for the arm.
E1b follow-up (promoted 2026-10-04):
  DENSE_WEIGHT=0.5 ................ uniform scale on the dense-atom RRF
                                    term. Must stay UNIFORM (same w for all
                                    atoms): conditional application by lex
                                    rank creates a scale schism (guarded
                                    atoms capped at lex-scale while
                                    unguarded reach lex+dense scale),
                                    which inverted rankings in testing
                                    (curated S2 nDCG 0.666 -> 0.259).
                                    Dead-end guard flags removed; see
                                    TL-COMPLETION-RECORD E1b.
E3 prep funnel tracing (experiment; off unless cfg opts in):
  TRACE_FUNNEL=False .............. when True, receipt + rows carry a
                                    bounded funnel histogram (support mix,
                                    prune/admission pressures,
                                    deferral-reason counts, pre-prune
                                    top-10 snapshot). Counts only, no
                                    per-atom bulk, no judgments.
E2 confidence trigger (promoted 2026-10-04; honest-disclosure
  re-qualification 2026-10-04):
  DISCLOSE_TOP1_CUT=0.30 .......... (with EMIT_DENSE_ATOMS),
                                    ONE-SIDED low_retrieval_similarity
                                    flag fires when dense_cos_top1 <
                                    cut: settled Q3.3 disclose-don't-
                                    hide ("not sure (low retrieval
                                    similarity)" + present what we
                                    have). Silence presents as
                                    "unassessed", never "sure": the
                                    flag is not an answerability
                                    verdict (near-miss invisible to
                                    all TL signals; far-OOS operating
                                    point is corpus-dependent). No
                                    serving or admission change.
                                    Tuning evidence: cut=0.30 flags
                                    16/20 S4 at 0/949 answerable
                                    flags (offline sweep).
E3a region support (promoted 2026-10-04; weakest leg, strikable):
  REGION_DENSE_ATOMS=True ......... member dense-atom RRF also credits
  REGION_DENSE_WEIGHT=0.3 ......... the containing region (damped; the
                                    unscaled variant was flat with severe
                                    regressions and was rejected).
E3b prune split (promoted 2026-10-04):
  PRUNE_SPLIT=True ................ dense-only atoms get reserved prune
                                    seats instead of competing with
                                    lex-supported atoms (pruned-path
                                    no-op at current scale; unpruned
                                    +0.010/+0.023, 80 improvements).

Shape: always Q4.1(a) narrow lookup (direct descent, zero lateral).
Relational/dossier shapes need S-02 relation records + [E] shape
thresholds: future, named gap -- never silent rerouting.

Relations first consumption (tlsys.relquery; default OFF, see
REL_HUB_SUPPRESS / REL_HUB_ALPHA / REL_QUALIFIERS): Q10.1 hub
suppression deg^{-alpha} on emitted scores plus Q12.1(a)/(b)/(c)
+ Q12.2 + Q12.3-mechanism qualifier-scope/collapse/mark/pairs/
partitioned-MMR plumbing ((c) + pairs ruled round-3 R3-B; see
tl-eval/evidence/round3-2026-10-05/trackB/MECHANISM-RULING.md),
all gated on eligibility at the pinned generation. Flag-off runs
are byte-identical with or without committed relations.

M1-C candidate navigation (tlsys.place boundary; default OFF, see
USE_CANDIDATE_HOLONS / USE_CANDIDATE_ATOMS / CANDIDATE_K): the two
dense legs route through the index's attached candidate searches
(bounded discovery + exact rescore) with per-query work evidence
in receipt metrics candidate_nav. Flag-off runs are byte-identical
with or without attached searches.
"""

import hashlib
import os
import time
import weakref

RRF_K = 60
SEED_LEX = 100
SEED_DENSE = 100
M_REGIONS = 20
TAU = 0
EPS = 0
WIDEN_FACTOR = 2
WIDEN_CLAMP = 40
PRUNE_CAP = 50
MMR_LAMBDA = 0.8
TAU_SEL = 0.005
MAX_ENTRIES = 10
WORK_BUDGET = 1000000
EMIT_DENSE_ATOMS = True
SEED_DENSE_ATOMS = 100
DENSE_WEIGHT = 0.5
DISCLOSE_TOP1_CUT = 0.30
TRACE_FUNNEL = False
REGION_DENSE_ATOMS = True
REGION_DENSE_WEIGHT = 0.3
PRUNE_SPLIT = True
# R3 candidates (1b repair round; [E]-tagged, default OFF).
# CAP03 (worker 176): R3-1 SIM_CAP=0.3 promoted to default on
# validated evidence (PROBE 172/174: rescues exactly the 24
# MMR-convicted contradiction units; 16/16 lane-metric cells
# hold-or-improve). Explicit MMR_SIM_CAP=None restores exact MMR.
MMR_SIM_CAP = 0.3  # R3-1: cap the MMR similarity penalty: div'=min(div,cap)
MMR_DENSE_EXEMPT_D = 0  # R3-2: top-D dense-supported pruned cands exempt from sim term
# Relations first consumption (S-02 section 1b records; default OFF).
REL_HUB_SUPPRESS = False  # Q10.1 hub penalty deg^{-alpha} on emission
REL_HUB_ALPHA = 0.5  # [E], D-12 sqrt starting ballpark, unconstrained
REL_QUALIFIERS = False  # Q12.1(a)/(b)/(c)+Q12.2+Q12.3-mech
# scope/collapse/marks/pairs/partitioned-MMR plumbing (R3-B)
# M1-C candidate navigation (default OFF, flag-gated): route the two
# Narrow dense legs through the index's attached candidate searches
# (bounded discovery + exact rescore, tlsys.index) instead of the
# exact vectorized legs. Flag-off runs are byte-identical with or
# without attached searches (attach alone never reroutes).
USE_CANDIDATE_HOLONS = False
USE_CANDIDATE_ATOMS = False
CANDIDATE_K = 200
CANDIDATE_EF = None
CANDIDATE_INCLUDE_UNPUBLISHED = True
# M2-C hierarchy evidence leg (default OFF, flag-gated): NarrowQuery
# with cfg HIER_GUIDED=True additionally serves HierQuery guided
# parent->child->atom evidence as a receipt sidecar (emission
# untouched). HIER_PARENT_BUDGET bounds the leg's parent nomination
# (None = exact all-parent scoring); flag-off runs are byte-identical.
HIER_GUIDED = False
HIER_PARENT_BUDGET = 200
# R-2 production wiring (Lane R-2; default ON): the Narrow REL legs
# serve relation state via the delta-aware RelServe over the facade
# (no whole-population live set), and the HIER_GUIDED leg serves via
# a held HierServe (one HierQuery across runs, facade-only). Exact
# parity with the legacy path (entry differentials in
# test_c2_entry_guards_r2.py); TL_REL_ORACLE/AUDIT modes always take
# the legacy path (conformance/diagnostic exactness).
RELSERVE_WIRED = True
HIERSERVE_WIRED = True
RELSERVE_ENV = "TL_C2_RELSERVE"  # "0" forces the legacy rel path
HIERSERVE_ENV = "TL_C2_HIERSERVE"  # "0" forces direct HierQuery
# S-4 segmented dense wiring (Lane S-4; default ON): the Narrow vec
# legs assemble (ids, f64 mat, norms) from the serving view's
# segment-aware cached assembly instead of re-enumerating the facade
# mappings and stacking per query object. Bitwise-identical BLAS
# inputs (mapping order verified); executed rows are counted
# (R5 units); every legacy execution is tagged, never silent.
DENSESERVE_WIRED = True
DENSESERVE_ENV = "TL_C2_DENSESERVE"  # "0" forces the legacy pop


COST_TABLE_VERSION = "v1-provisional-unit"
# Q13.1(a): per-class unit costs all [E]; v1 provisionally charges 1
# unit per op with per-class COUNTS recorded every run ([E]-
# provisional, unenforced per the Q5.2 bakeoff amendment). Only the
# aggregate cap + monotonic deadline enforce (also provisional).
T_DEADLINE_S = 120.0  # Q5.2 T [E]; generous provisional


class WorkBudget:
    """Cooperative cancellation (Q13.2b): charge() never raises; the
    path polls ok() at safe points and unwinds gracefully."""

    def __init__(self, cap=WORK_BUDGET, deadline_s=T_DEADLINE_S):
        self.cap = cap
        self.used = 0
        self.deadline = time.monotonic() + deadline_s
        self.counts = {}
        self.exhaustion = None

    def charge(self, units, op_class):
        self.counts[op_class] = self.counts.get(op_class, 0) + units
        self.used += units
        if self.exhaustion is None and self.used > self.cap:
            self.exhaustion = f"work-budget at {op_class}"

    def ok(self):
        if self.exhaustion is not None:
            return False
        if time.monotonic() > self.deadline:
            self.exhaustion = "monotonic-deadline T"
            return False
        return True


import numpy as np

from tlsys.fuse import admit, mmr_order_matrix, rrf_fuse, static_prune
from tlsys import relquery as _relquery
from tlsys.place import NavCounters
from tlsys.relserve import StaleServeError as _StaleServeError
from tlsys.index import DenseOrderDiverged as _DenseOrderDiverged


def _dense_rank(qvec, ids, mat, norms, topk=None):
    """Vectorized exact cosine rank (R7-A; R6-D mechanism (b)).

    Same cosine definition as NarrowIndex.dense_holons/dense_atoms
    (q @ d / (||q|| * ||d||), zero norms read as 1.0) over the same
    insertion-ordered ids, one float64 matvec + stable descending
    order. `norms` is the cached per-row ||d|| (zeros read as
    1.0). `topk` materializes exactly the full stable order's head
    via selection (no full sort; identical ids/scores/tie order);
    None materializes the full ranking. Score values may
    differ from the python loop in the last ulp (BLAS summation
    order); ordering matches on real queries, including
    tie-breaks (stable sort over identical input order).
    Near-ties within ~1e-15 relative (e.g. self-queries against
    near-duplicate descriptors) can flip rank vs the loop; the
    Narrow path consumes only ranks <= 100, where agreement holds
    (see trackA/dense.log).
    """
    if not ids:
        return []
    q = np.asarray(qvec, dtype=np.float64)
    qn = float(np.linalg.norm(q)) or 1.0
    s = (mat @ q) / (qn * norms)
    if topk is not None and 0 <= int(topk) < len(ids):
        # Head-only consumption without a full sort: stable_head
        # returns exactly the full stable order's head (same ids,
        # scores, tie order; differential-pinned). Output-identical
        # to the sliced full sort it replaces.
        from tlsys.serving.dense import stable_head
        return stable_head(s, ids, int(topk))
    order = np.argsort(-s, kind="stable")
    if topk is not None:
        order = order[:topk]
    return [(ids[i], float(s[i])) for i in order]


UNIT_OVERFLOW = "unit-overflow"
UNIT_DISSOLVED = "unit-dissolved"


def _collapse_exact(scored):
    """[(aid, score, text)] -> deduped list, (score desc, aid asc)."""
    out = []
    seen = set()
    for aid, score, text in sorted(scored, key=lambda c: (-c[1], c[0])):
        h = hashlib.sha256(text.encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append((aid, score, text))
    return out


def _seat_pair_units(scored, pairs, cap, collapse=True):
    """V1 (P-G3P-1): qualifier pairs as complete selection units.

    Pure helper (no store); differential-pinned against the isolated
    G3P reference (variants/v1_units.seat_units). Rule: exact-collapse
    preserved (collapse=False when the caller pre-collapsed, e.g. the
    qualifier legs with prune_rel); pairs with both sides available
    form units keyed by max-side evidence; greedy seating within the
    unchanged total cap; units that cannot fit are skipped with an
    explicit unit-overflow while other material fills; pairs with an
    unavailable side dissolve to singles. Admission unchanged (the
    frozen admit() joint-preservation branch seats units jointly).
    Returns (seated [(aid, score, text)], diag dict).
    """
    if cap < 0:
        raise ValueError(f"cap must be >= 0, got {cap!r}")
    collapsed = _collapse_exact(scored) if collapse else list(scored)
    by_aid = {a: (a, s, t) for a, s, t in collapsed}
    diag = {"dissolved": [], "overflow": [], "units_seated": 0,
            "singles_seated": 0}
    used = set()
    units = []
    for a, b in sorted(set(tuple(sorted(p)) for p in (pairs or []))):
        if a == b:
            continue
        if a not in by_aid or b not in by_aid:
            diag["dissolved"].append(
                {"pair": [a[:16], b[:16]], "reason": UNIT_DISSOLVED})
            continue
        if a in used or b in used:
            diag["dissolved"].append(
                {"pair": [a[:16], b[:16]],
                 "reason": "aid-already-unitized"})
            continue
        used.add(a)
        used.add(b)
        ia, ib = by_aid[a], by_aid[b]
        units.append((ia, ib, max(ia[1], ib[1]), min(a, b)))
    singles = [item for aid, item in by_aid.items() if aid not in used]
    items = [("unit", u[2], u[3], u[0], u[1]) for u in units]
    items += [("single", s[1], s[0], s, None) for s in singles]
    items.sort(key=lambda it: (-it[1], it[2]))
    seated = []
    seats_left = cap
    for kind, _score, _tie, first, second in items:
        if kind == "single":
            if seats_left >= 1:
                seated.append(first)
                seats_left -= 1
                diag["singles_seated"] += 1
        else:
            if seats_left >= 2:
                seated.append(first)
                seated.append(second)
                seats_left -= 2
                diag["units_seated"] += 1
            else:
                diag["overflow"].append(
                    {"pair": sorted([first[0][:16], second[0][:16]]),
                     "reason": UNIT_OVERFLOW,
                     "seats_left": seats_left})
    seated.sort(key=lambda c: (-c[1], c[0]))
    return seated, diag


def _split_prune(scored, fw, darrf, cap, prune_fn=None, pairs=None,
                 pair_diag=None):
    """Prune with reserved seats for dense-only atoms (E3b).

    scored: [(aid, score, text)]. Pool A = lex-supported (lex-only +
    both), pool B = dense-only (no lex support); shares cap-share_b /
    share_b with share_b = cap // 2. Merged score-ordered, aid-deduped.
    Pure helper (no store); unit-tested directly.
    prune_fn: per-pool (cands, cap) collapse; None == static_prune
    (Narrow default; the relations path passes prune_rel).
    pairs: identified qualifier-explicit counterparts for this leg
    (V1 P-G3P-1). None/empty keeps the baseline pool split exactly;
    nonempty seats pairs as complete units by max-side evidence
    within the unchanged total cap (qualifier legs pre-collapse with
    prune_rel, collapse=False; overflow/dissolve explicit).
    pair_diag: optional dict receiving the seating diag (v1 mode,
    units/singles seated, dissolved, overflow).
    """
    if pairs:
        if prune_fn is not None:
            survivors = prune_fn(scored, len(scored))
            seated, diag = _seat_pair_units(survivors, pairs, cap,
                                            collapse=False)
        else:
            seated, diag = _seat_pair_units(scored, pairs, cap,
                                            collapse=True)
        if pair_diag is not None:
            pair_diag.update(diag)
            pair_diag["v1"] = "unit-seating"
            pair_diag["pairs_matched"] = len(pairs)
        return seated
    if pair_diag is not None:
        pair_diag["v1"] = "fallback-baseline"
    _pf = static_prune if prune_fn is None else prune_fn
    pool_a = [c for c in scored if fw.get("a:" + c[0], 0.0) > 0.0]
    pool_b = [c for c in scored
              if fw.get("a:" + c[0], 0.0) <= 0.0
              and darrf.get("a:" + c[0], 0.0) > 0.0]
    share_b = cap // 2
    share_a = cap - share_b
    pruned = _pf(pool_a, share_a) + _pf(pool_b, share_b)
    seen = set()
    merged = []
    for c in sorted(pruned, key=lambda c: -c[1]):
        if c[0] not in seen:
            seen.add(c[0])
            merged.append(c)
    return merged


# -- R-2 RelServe wiring (shared by NarrowQuery + DossierQuery) ----
# One serve per live index (WeakKeyDictionary: entries die with the
# index, so the cache never pins stale N-sized facades -- a strong
# cache would). Same pin+index reuses the serve (covers-hit, zero
# work, the M1-D cross-instance amortization); a new pin on the same
# index advances incrementally (forward) or rebuilds (rewind).
_RELSERVE_BY_INDEX = weakref.WeakKeyDictionary()


def _relserve_wired(cfg):
    """True iff the REL legs should serve via RelServe.

    Precedence: TL_C2_RELSERVE=0 forces legacy; TL_REL_ORACLE=1 and
    TL_REL_AUDIT=1 force legacy (conformance/diagnostic modes keep
    exact pre-R-2 behavior); else cfg["RELSERVE_WIRED"] when
    present; else the module default (ON).
    """
    if os.environ.get(RELSERVE_ENV) == "0":
        return False
    if os.environ.get(_relquery.ORACLE_ENV) == "1":
        return False
    if os.environ.get(_relquery.AUDIT_ENV) == "1":
        return False
    if cfg is not None and "RELSERVE_WIRED" in cfg:
        return bool(cfg["RELSERVE_WIRED"])
    return bool(RELSERVE_WIRED)


def _hierserve_wired(cfg):
    """True iff the HIER_GUIDED leg should serve via HierServe.

    Precedence: TL_C2_HIERSERVE=0 forces direct HierQuery; else
    cfg["HIERSERVE_WIRED"] when present; else the module default
    (ON).
    """
    if os.environ.get(HIERSERVE_ENV) == "0":
        return False
    if cfg is not None and "HIERSERVE_WIRED" in cfg:
        return bool(cfg["HIERSERVE_WIRED"])
    return bool(HIERSERVE_WIRED)


def _denseserve_wired(cfg):
    """True iff the vec legs should assemble from serving state.

    Precedence: TL_C2_DENSESERVE=0 forces the legacy pop; else
    cfg["DENSESERVE_WIRED"] when present; else the module default
    (ON). Reference-backend / stub indexes take the legacy pop
    regardless (no serving view; tagged, never silent).
    """
    if os.environ.get(DENSESERVE_ENV) == "0":
        return False
    if cfg is not None and "DENSESERVE_WIRED" in cfg:
        return bool(cfg["DENSESERVE_WIRED"])
    return bool(DENSESERVE_WIRED)


def _rel_serve_for(tlstore, index, pinned):
    """RelServe covering `pinned` over `index` (shared per index).

    Serves the cached entry on an exact pin match; advances it
    (forward) or rebuilds it (rewind) on a new pin; opens fresh on
    first use. Raises ImportError when Lane G counters are
    unavailable and StaleServeError when the facade does not serve
    the pin -- callers fall back to the legacy path (recorded,
    never silent). Other errors (e.g. corrupt relation bytes, also
    raised by the legacy path) propagate.
    """
    from tlsys.relserve import RelServe
    try:
        serve = _RELSERVE_BY_INDEX.get(index)
    except TypeError:
        serve = None  # unhashable/exotic holder: uncached serve
    if serve is not None:
        if serve.covers(pinned):
            if getattr(index, "triple", None) != pinned[3]:
                raise _StaleServeError(
                    f"facade at {getattr(index, 'triple', None)!r} "
                    f"does not serve pin {pinned[3]!r}")
            return serve
        serve = serve.advance(index, pinned)
        try:
            _RELSERVE_BY_INDEX[index] = serve
        except TypeError:
            pass
        return serve
    serve = RelServe.open(tlstore, index, pinned)
    try:
        _RELSERVE_BY_INDEX[index] = serve
    except TypeError:
        pass  # unweakrefable holder: correct, just uncached
    return serve


def invalidate_rel_serve(tlstore=None):
    """Explicit invalidation: drop cached RelServe entries (all, or
    just `tlstore`'s). Pin discipline already prevents stale serves;
    this is lifecycle control for tests and bounded operation."""
    if tlstore is None:
        _RELSERVE_BY_INDEX.clear()
        return
    prefix = os.path.abspath(tlstore.store.db_path)
    for key in list(_RELSERVE_BY_INDEX.keys()):
        try:
            db = os.path.abspath(key.tlstore.store.db_path)
        except AttributeError:
            continue
        if db == prefix:
            try:
                del _RELSERVE_BY_INDEX[key]
            except KeyError:
                pass


def rel_serve_cache_info():
    """Cache shape for evidence: {"size": n} (weak-by-index; entries
    die with their index, so no max is needed)."""
    return {"size": len(_RELSERVE_BY_INDEX)}


def _rel_view_for(tlstore, index, pinned, cfg):
    """(view, backend) for the REL legs.

    RelServe when wired (facade predicate liveness, no
    whole-population live set), else the legacy relquery.load view.
    Both expose the RelView shape (visible/eligible/reasons/degrees/
    scope/unresolved) consumed identically downstream. backend is
    "relserve" or "relquery" (recorded on the query object by the
    caller; fallbacks are honest, never silent).
    """
    if _relserve_wired(cfg) and hasattr(index, "is_live_atom"):
        try:
            return _rel_serve_for(tlstore, index, pinned), "relserve"
        except ImportError:
            pass  # Lane G counters unavailable: legacy path
        except _StaleServeError:
            pass  # facade/pin mismatch: legacy path
    return (_relquery.load(tlstore, pinned, index.live_atom_set()),
            "relquery")


class NarrowQuery:
    def __init__(self, tlstore, index, embed_query, cfg=None):
        self.tl = tlstore
        self.idx = index
        self.embed_query = embed_query
        # R7-A: stacked descriptor cache for the vectorized dense
        # legs (amortizes the stack across queries, as in R6-D (b)).
        self._dense_cache = {}
        # [E]-value overrides for tuning runs (Q16.1d docket).
        # Keys: subset of the FROZEN DEFAULTS; unknown keys rejected.
        c = dict(cfg or {})
        for k in c:
            if k not in ("SEED_LEX", "SEED_DENSE", "M_REGIONS", "TAU",
                         "EPS", "WIDEN_FACTOR", "WIDEN_CLAMP",
                         "PRUNE_CAP", "MMR_LAMBDA", "TAU_SEL",
                         "MAX_ENTRIES", "WORK_BUDGET",
                         "EMIT_DENSE_ATOMS", "SEED_DENSE_ATOMS",
                         "DENSE_WEIGHT", "DISCLOSE_TOP1_CUT",
                         "TRACE_FUNNEL", "REGION_DENSE_ATOMS",
                         "REGION_DENSE_WEIGHT", "PRUNE_SPLIT",
                         "MMR_SIM_CAP", "MMR_DENSE_EXEMPT_D",
                         "REL_HUB_SUPPRESS", "REL_HUB_ALPHA",
                         "REL_QUALIFIERS",
                         "USE_CANDIDATE_HOLONS",
                         "USE_CANDIDATE_ATOMS", "CANDIDATE_K",
                         "CANDIDATE_EF",
                         "CANDIDATE_INCLUDE_UNPUBLISHED",
                         "HIER_GUIDED", "HIER_PARENT_BUDGET",
                         "RELSERVE_WIRED", "HIERSERVE_WIRED",
                         "DENSESERVE_WIRED"):
                raise ValueError(f"unknown cfg key: {k}")
        self.cfg = c  # RRF_K=60 settled: not an accepted key
        # M1-C: per-run navigation summary (None unless a nav flag
        # was on for the last run; additive, never read by default
        # paths).
        self.last_nav = None
        # R-2: wired-backend evidence (additive attributes, never in
        # receipts): which relation/hierarchy backend served the
        # last run, the held HierServe, and its last traffic dict.
        self.last_rel_backend = None
        self.last_hier_backend = None
        self._hierserve = None
        self.last_hier_traffic = None
        # S-4: backend of the last-executed vec leg ("denseserve" /
        # "densepop"; additive, never in receipts).
        self.last_dense_backend = None

    def _C(self, name, default):
        return self.cfg.get(name, default)

    def _dense_pop(self, which):
        """Stacked (ids, float64 matrix) for "holons"|"atoms".

        Cached per index identity + pinned triple + population size
        with first/last-id validation; any mismatch rebuilds.
        NarrowIndex populations are build-once per generation, so a
        validated hit is exact. Returns ([ids], (n, d) matrix).

        S-4: when denseserve is wired and the index serves a C2 view,
        the assembly comes from serving state (segments FP32 + exact
        overrides + delta, one cached stack per view shared across
        query objects) in verified mapping order -- bitwise the
        legacy pop's BLAS inputs -- and the backend tags
        "denseserve". Otherwise the legacy mapping enumeration runs
        verbatim and tags "densepop" (env/cfg opt-out, reference
        backend, stub, or order divergence: every legacy execution
        is tagged, never silent).
        """
        if _denseserve_wired(self.cfg):
            meth = getattr(self.idx, "dense_served_pop", None)
            served = None
            if meth is not None:
                try:
                    served = meth(which)
                except _DenseOrderDiverged:
                    served = None
            if served is not None:
                s_ids, mat, norms = served
                hit = self._dense_cache.get(which)
                if (hit is not None
                        and hit["idx_id"] == id(self.idx)
                        and hit["triple"] == self.idx.triple
                        and hit["n"] == len(s_ids)
                        and (not s_ids or (hit["ids0"] == s_ids[0]
                                            and hit["ids1"]
                                            == s_ids[-1]))):
                    self.last_dense_backend = "denseserve"
                    return hit["ids"], hit["mat"], hit["norms"]
                self._dense_cache[which] = {
                    "idx_id": id(self.idx), "triple": self.idx.triple,
                    "n": len(s_ids), "ids": s_ids, "mat": mat,
                    "norms": norms,
                    "ids0": s_ids[0] if s_ids else None,
                    "ids1": s_ids[-1] if s_ids else None}
                self.last_dense_backend = "denseserve"
                return s_ids, mat, norms
        pop = self.idx.holons if which == "holons" else self.idx.atoms
        ids = list(pop.keys())
        hit = self._dense_cache.get(which)
        if (hit is not None and hit["idx_id"] == id(self.idx)
                and hit["triple"] == self.idx.triple
                and hit["n"] == len(ids)
                and (not ids or (hit["ids0"] == ids[0]
                                 and hit["ids1"] == ids[-1]))):
            self.last_dense_backend = "densepop"
            return hit["ids"], hit["mat"], hit["norms"]
        mat = (np.stack([np.asarray(pop[i]["descriptor"],
                                    dtype=np.float64)
                         for i in ids])
               if ids else np.empty((0, 0)))
        norms = (np.linalg.norm(mat, axis=1)
                 if ids else np.empty((0,)))
        norms[norms == 0.0] = 1.0
        self._dense_cache[which] = {
            "idx_id": id(self.idx), "triple": self.idx.triple,
            "n": len(ids), "ids": ids, "mat": mat, "norms": norms,
            "ids0": ids[0] if ids else None,
            "ids1": ids[-1] if ids else None}
        self.last_dense_backend = "densepop"
        return ids, mat, norms

    def _nav_leg(self, which, qvec, topk, nav_diag):
        """Route one dense leg through the attached search (M1-C).

        which: "holons" (SEED_DENSE leg) or "atoms" (E1 dense-atom
        leg). Returns the ranked head, or None when the exact vec
        leg must run instead: flag off (default -- byte-identical
        path), or flag on with no search attached (honest
        fallback: recorded in nav_diag, exact leg runs, results
        identical to flag-off). nav_diag may be None (no
        recording); returns None then too unless routed.
        """
        if which == "holons":
            on = bool(self._C("USE_CANDIDATE_HOLONS",
                              USE_CANDIDATE_HOLONS))
            search = self.idx.candidate_search
            leg = self.idx.dense_holons
        else:
            on = bool(self._C("USE_CANDIDATE_ATOMS",
                              USE_CANDIDATE_ATOMS))
            search = self.idx.atom_candidate_search
            leg = self.idx.dense_atoms
        if not on:
            return None
        if search is None:
            if nav_diag is not None:
                nav_diag[which] = {"fallback": "no-search-attached",
                                   "exact_vec_used": True}
            return None
        full = leg(qvec,
                   candidate_k=self._C("CANDIDATE_K", CANDIDATE_K),
                   ef=self._C("CANDIDATE_EF", CANDIDATE_EF),
                   include_unpublished=self._C(
                       "CANDIDATE_INCLUDE_UNPUBLISHED",
                       CANDIDATE_INCLUDE_UNPUBLISHED))
        head = full if topk is None else full[:topk]
        if nav_diag is not None:
            rep = (self.idx.last_candidate_report
                   if which == "holons"
                   else self.idx.last_atom_candidate_report)
            entry = dict(rep) if rep is not None else {}
            entry["head"] = len(head)
            nav_diag[which] = entry
        return head

    def _gen_dense_head(self, which, qvec, topk):
        """Block-aware served head for generation-backed views.

        Closure S: ranks base + overlay blocks separately and
        merges (no triple assembly, no full sort for heads).
        Returns the head list, or None without a gen-backed view
        (caller takes the pop path). Evidence mirrors the vec
        legs (full populations scored every call; the view counts
        executed rows itself, so no double-count here).
        """
        meth = getattr(self.idx, "dense_served_head", None)
        if meth is None:
            return None
        out = meth(which, qvec, topk)
        if out is None:
            return None
        pop = self.idx.holons if which == "holons" else self.idx.atoms
        n = len(pop)
        self.idx.nav_counters.record(
            f"narrow-{which}-vec", discovered=n, visited=n,
            rescored=n, head=len(out))
        self.last_dense_backend = "denseserve"
        return out

    def _dense_holons_vec(self, qvec, topk=None, nav_diag=None):
        """Vectorized NarrowIndex.dense_holons (identical ordering).

        M1-C: with cfg USE_CANDIDATE_HOLONS=True and a search
        attached to the index, routes through bounded discovery
        + exact rescore instead (flag off, or no search
        attached, runs the exact vec leg as before).
        """
        nav = self._nav_leg("holons", qvec, topk, nav_diag)
        if nav is not None:
            return nav
        if _denseserve_wired(self.cfg):
            head = self._gen_dense_head("holons", qvec, topk)
            if head is not None:
                return head
        ids, mat, norms = self._dense_pop("holons")
        out = _dense_rank(qvec, ids, mat, norms, topk=topk)
        # M1-C work evidence (additive record only): the vec leg
        # scores the whole population every call (full matvec;
        # topk only trims the materialized head).
        self.idx.nav_counters.record(
            "narrow-holons-vec", discovered=len(ids),
            visited=len(ids), rescored=len(ids),
            head=len(out))
        # S-4: served calls count executed native rows (R5 units).
        if self.last_dense_backend == "denseserve":
            self.idx.note_dense_scored("holons", len(ids))
        return out

    def _dense_atoms_vec(self, qvec, topk=None, nav_diag=None):
        """Vectorized NarrowIndex.dense_atoms (identical ordering).

        M1-C: with cfg USE_CANDIDATE_ATOMS=True and a search
        attached to the index, routes through bounded discovery
        + exact rescore instead (flag off, or no search
        attached, runs the exact vec leg as before).
        """
        nav = self._nav_leg("atoms", qvec, topk, nav_diag)
        if nav is not None:
            return nav
        if _denseserve_wired(self.cfg):
            head = self._gen_dense_head("atoms", qvec, topk)
            if head is not None:
                return head
        ids, mat, norms = self._dense_pop("atoms")
        out = _dense_rank(qvec, ids, mat, norms, topk=topk)
        # M1-C work evidence (additive record only): see holons.
        self.idx.nav_counters.record(
            "narrow-atoms-vec", discovered=len(ids),
            visited=len(ids), rescored=len(ids),
            head=len(out))
        # S-4: served calls count executed native rows (R5 units).
        if self.last_dense_backend == "denseserve":
            self.idx.note_dense_scored("atoms", len(ids))
        return out

    def run(self, query, unpruned_reference=False):
        """Full Narrow path. Returns (dossier, receipt)."""
        t0 = time.time()
        budget = WorkBudget(cap=self._C("WORK_BUDGET", WORK_BUDGET))
        events = []  # UQ1 wait/forage/LLM-help events (v1: none occur)
        pin = self.tl.pin()
        _birth, _epoch, _mx, triple = pin
        if triple != self.idx.triple:
            raise ValueError("index built at %s, store pinned at %s: "
                             "rebuild index (no cross-generation mixing)"
                             % (self.idx.triple, triple))
        # Cooperative: _run_inner polls budget.ok() and unwinds with
        # partials; no teardown-by-exception (Q13.2b).
        return self._run_inner(query, pin, budget, events, t0,
                               unpruned_reference)

    def _run_inner(self, query, pin, budget, events, t0, unpruned):
        _birth, _epoch, _mx, triple = pin
        # -- seed (Q2.3c: lexical->atoms, dense->holons) -------------
        qvec = self.embed_query(query)
        # M1-C nav diag sink (per-run; stays empty unless a nav
        # flag is on, in which case legs record discovery work).
        nav_diag = {}
        nav_on = bool(self._C("USE_CANDIDATE_HOLONS",
                              USE_CANDIDATE_HOLONS)) or bool(
            self._C("USE_CANDIDATE_ATOMS", USE_CANDIDATE_ATOMS))
        lex = self.idx.bm25(query)
        lex_rank = {a: r for r, (a, _s) in
                    enumerate(sorted(lex.items(), key=lambda kv: -kv[1])
                              [:self._C("SEED_LEX", SEED_LEX)])}
        budget.charge(len(lex_rank), "seed-lexical")
        # nav_diag is passed ONLY when a nav flag is on, so the
        # default call shape is exactly the pre-M1-C one (older
        # monkeypatches/tests overriding the legs keep working).
        if nav_on:
            dh = self._dense_holons_vec(
                qvec, topk=self._C("SEED_DENSE", SEED_DENSE),
                nav_diag=nav_diag)
        else:
            dh = self._dense_holons_vec(
                qvec, topk=self._C("SEED_DENSE", SEED_DENSE))
        den_rank = {d: r for r, (d, _s) in enumerate(dh)}
        budget.charge(len(den_rank), "seed-dense")
        # -- fuse (Q2.2 rank-only RRF) --------------------------------
        fw = rrf_fuse([{"a:" + a: r for a, r in lex_rank.items()},
                       {"h:" + d: r for d, r in den_rank.items()}])
        # -- E1 arm: dense-atom emission support (flag-gated) ---------
        # Region ranking below is untouched; this term flows ONLY into
        # atom emission at descent (and the outlier bypass), so any
        # measured change isolates the emission mechanism. Rank-only
        # RRF at the settled k=60, same scale as fw (not tunable).
        emit_dense = bool(self._C("EMIT_DENSE_ATOMS", EMIT_DENSE_ATOMS))
        darrf = {}
        dense_cos_top1 = 0.0
        dense_cos_margin = 0.0
        if emit_dense:
            if nav_on:
                da = self._dense_atoms_vec(
                    qvec, topk=self._C("SEED_DENSE_ATOMS",
                                       SEED_DENSE_ATOMS),
                    nav_diag=nav_diag)
            else:
                da = self._dense_atoms_vec(
                    qvec, topk=self._C("SEED_DENSE_ATOMS",
                                       SEED_DENSE_ATOMS))
            darrf = {"a:" + a: 1.0 / (RRF_K + r)
                     for r, (a, _s) in enumerate(da)}
            budget.charge(len(darrf), "seed-dense-atoms")
            if da:
                dense_cos_top1 = da[0][1]
                dense_cos_margin = da[0][1] - (
                    da[1][1] if len(da) > 1 else 0.0)
        elif nav_on and bool(self._C("USE_CANDIDATE_ATOMS",
                                     USE_CANDIDATE_ATOMS)):
            nav_diag["atoms"] = {"skipped": "emit-dense-atoms-off"}
        # Publish the per-run nav summary even if a later stage
        # unwinds bounded-incomplete (additive attribute).
        self.last_nav = dict(nav_diag) if nav_on else None

        dense_w = float(self._C("DENSE_WEIGHT", DENSE_WEIGHT))

        def emit_of(aid):
            # Flag-off: darrf is empty, + 0.0 is exact: identical to fw.
            return (fw.get("a:" + aid, 0.0)
                    + dense_w * darrf.get("a:" + aid, 0.0))
        # -- attribute + aggregate (Q3.1/Q3.2a) ------------------------
        region_score = {}
        region_sup = {}
        for target, w in fw.items():
            typ, key = target.split(":", 1)
            if typ == "h":
                region_score[key] = region_score.get(key, 0.0) + w
                region_sup.setdefault(key, []).append(("dense", w))
            else:
                a = self.idx.atoms.get(key)
                if a is None:
                    continue
                doc = a["doc_id"]  # atom->containing-holon (Q3.1)
                if doc is None:
                    continue  # empty attribution -> outlier stream
                region_score[doc] = region_score.get(doc, 0.0) + w
                region_sup.setdefault(doc, []).append(("lex:" + key, w))
        # -- E3a: dense-atom region support (promoted default) -------
        # Member dense-atom RRF also credits the containing region, so
        # regions ranked low by lex + holon-centroid can surface on
        # member-atom support. Damped by REGION_DENSE_WEIGHT (0.3);
        # DENSE_WEIGHT governs emission only. Requires the E1 dense-atom
        # scan (no darrf without it).
        region_dense = bool(self._C("REGION_DENSE_ATOMS",
                                    REGION_DENSE_ATOMS))
        region_dense_w = float(self._C("REGION_DENSE_WEIGHT",
                                       REGION_DENSE_WEIGHT))
        n_region_dense = 0
        if region_dense and darrf:
            for target, w in darrf.items():
                _typ, aid = target.split(":", 1)
                a = self.idx.atoms.get(aid)
                if a is None:
                    continue
                doc = a["doc_id"]
                if doc is None:
                    continue
                region_score[doc] = region_score.get(doc, 0.0) + \
                    region_dense_w * w
                region_sup.setdefault(doc, []).append(
                    ("dense-atom:" + aid[:16], w))
                n_region_dense += 1
        # outliers: empty attribution only (v1: none under per-doc
        # holons; branch implemented, never fires -- Q3.2b bypass kept)
        outliers = [a for a in lex_rank
                    if self.idx.atoms.get(a, {}).get("doc_id") is None]
        ranked_regions = sorted(region_score.items(),
                                key=lambda kv: -kv[1])
        # -- uncertainty gate (Q3.3a) ----------------------------------
        s1 = ranked_regions[0][1] if ranked_regions else 0.0
        s2 = ranked_regions[1][1] if len(ranked_regions) > 1 else 0.0
        uncertain = (s1 < self._C("TAU", TAU)) or (
            (s1 - s2) < self._C("EPS", EPS))
        # E2: dense-top1 disclosure trigger (settled Q3.3 semantics:
        # "not sure" + present what we have; never withholds). Needs
        # the dense-atom scan (emit_dense); without it there is no
        # signal and the trigger stays silent. Trigger source is
        # recorded in the receipt for attribution.
        top1_cut = self._C("DISCLOSE_TOP1_CUT", DISCLOSE_TOP1_CUT)
        top1_fired = bool(emit_dense and top1_cut is not None
                          and dense_cos_top1 < top1_cut)
        uncertain = uncertain or top1_fired
        m_eff = self._C("M_REGIONS", M_REGIONS)
        if uncertain and not unpruned:
            m_eff = min(len(ranked_regions),
                        min(m_eff * self._C("WIDEN_FACTOR", WIDEN_FACTOR),
                            self._C("WIDEN_CLAMP", WIDEN_CLAMP)))
        if unpruned:
            sel_regions = [d for d, _s in ranked_regions]
        else:
            sel_regions = [d for d, _s in ranked_regions[:m_eff]]
            budget.charge(len(sel_regions), "region-entry")
        # -- descend (Q4.1a: direct, zero lateral) ---------------------
        # Q3.2(c): "Region membership confers expansion-eligibility
        # only, never cross-path agreement." Members enter the
        # candidate stream with their OWN fused seed weight (0.0 if
        # unseeded); the region sum ranks REGIONS (descent scope),
        # never member scores. (Repair 2026-09-29: the previous
        # max(own, region_sum) let unseeded members of top regions
        # free-ride above seeded goldens elsewhere -- funnel probe
        # showed goldens served iff their region ranked #0.)
        # E1 arm: emit_of adds dense-atom RRF to own support when the
        # flag is on; flag-off it equals the fused lex/holon weight.
        cands = {}  # aid -> emission score (own support only)
        for doc in sel_regions:
            members = self.idx.holons.get(
                doc, {}).get("members", [])
            budget.charge(len(members), "member-enumeration")
            for aid in members:
                emit = emit_of(aid)
                if aid in cands:
                    cands[aid] = max(cands[aid], emit)
                else:
                    cands[aid] = emit
        for aid in outliers:  # bypass stream (Q3.2b routing only)
            cands.setdefault(aid, emit_of(aid))
        # -- relations first consumption (flag-gated; default off) ----
        # Q10.1(b): selection-time post-emission -- the hub factor
        # scales emission scores here; prune/MMR/admission consume
        # the penalized scores. Qualifier scope loads here and rides
        # per candidate through prune (collapse key) to the entries
        # (unresolved marks). Flag-off: rel_view stays None and every
        # line below is dead code (byte-identical Narrow path).
        rel_hub = bool(self._C("REL_HUB_SUPPRESS", REL_HUB_SUPPRESS))
        rel_qual = bool(self._C("REL_QUALIFIERS", REL_QUALIFIERS))
        rel_view = None
        rel_diag = None
        rel_pairs = []
        if rel_hub or rel_qual:
            # R-2: RelServe over the facade when wired (no
            # whole-population live set), else the legacy
            # relquery.load view. Same RelView shape downstream.
            rel_view, _rel_backend = _rel_view_for(
                self.tl, self.idx, pin, self.cfg)
            self.last_rel_backend = _rel_backend
            budget.charge(len(rel_view.visible), "rel-scope-read")
            alpha = self._C("REL_HUB_ALPHA", REL_HUB_ALPHA)
            if rel_hub:
                import math as _math
                if not isinstance(alpha, (int, float)) or \
                        not _math.isfinite(alpha):
                    raise ValueError(
                        f"REL_HUB_ALPHA must be finite, got {alpha!r}")
                cands = _relquery.apply_hub(cands, rel_view.degrees,
                                            alpha)
                budget.charge(len(cands), "rel-hub-penalty")
            rel_diag = {
                "hub_suppress": rel_hub,
                "hub_alpha": float(alpha) if rel_hub else None,
                "qualifiers": rel_qual,
                "relations_visible": len(rel_view.visible),
                "relations_eligible": len(rel_view.eligible),
                "relations_ineligible": len(rel_view.reasons),
                "hub_touched": sum(
                    1 for a in cands
                    if rel_view.degrees.get(a, 0) > 1) if rel_hub
                else 0,
                "unresolved_candidates": sum(
                    1 for a in cands if a in rel_view.unresolved),
            }
            # Q12.3-mech (R3-B): identified counterpart pairs over
            # the emitted universe (selection input). Hub-only
            # runs keep the empty trigger set.
            if rel_qual:
                rel_pairs = _relquery.identify_pairs(
                    rel_view, cands)
                budget.charge(len(rel_pairs), "rel-pair-identify")
            rel_diag["pairs_identified"] = len(rel_pairs)
            rel_diag["mmr_partitions"] = None  # set at MMR stage
            rel_diag["pairs_jointly_admitted"] = 0  # set at admit
        # -- E3 funnel trace (flag-gated; counts only) ------------------
        trace_funnel = bool(self._C("TRACE_FUNNEL", TRACE_FUNNEL))
        funnel = None
        if trace_funnel:
            funnel = {"regions_ranked": len(ranked_regions),
                      "regions_selected": len(sel_regions),
                      "candidates": len(cands),
                      "cand_lex_only": 0, "cand_dense_only": 0,
                      "cand_both": 0, "cand_neither": 0}
            for aid in cands:
                has_lex = fw.get("a:" + aid, 0.0) > 0.0
                has_dense = darrf.get("a:" + aid, 0.0) > 0.0
                if has_lex and has_dense:
                    funnel["cand_both"] += 1
                elif has_lex:
                    funnel["cand_lex_only"] += 1
                elif has_dense:
                    funnel["cand_dense_only"] += 1
                else:
                    funnel["cand_neither"] += 1
        # -- prune + MMR (Q10.2) ---------------------------------------
        partials = []
        if not budget.ok():
            return self._bounded_incomplete(
                query, pin, budget, events, t0, [], partials,
                {"regions_ranked": len(ranked_regions)})
        scored = [(a, s, self.idx.atom_text[a]) for a, s in cands.items()
                  if a in self.idx.atom_text]
        # -- E3b: support-split prune (flag-gated) ----------------------
        # Pool B reserves seats for dense-ONLY atoms (no lex support),
        # which "both"-supported atoms would otherwise outscore even
        # inside a dense-supported pool. No-op whenever a pool is under
        # its share (all pruned-path queries at current scale).
        prune_split = bool(self._C("PRUNE_SPLIT", PRUNE_SPLIT))
        # Relations qualifier collapse (flag-gated): prune_rel uses
        # the (text, qualifier-signature) collapse key with
        # unresolved exemption; flag-off prune_fn stays None.
        prune_fn = None
        if rel_view is not None and rel_qual:
            _scope, _unres = rel_view.scope, rel_view.unresolved
            prune_fn = lambda c, k: _relquery.prune_rel(  # noqa: E731
                c, k, _scope, _unres)
        prune_cap = self._C("PRUNE_CAP", PRUNE_CAP)
        pair_diag = {}
        if prune_split:
            pruned = _split_prune(
                scored, fw, darrf, prune_cap, prune_fn=prune_fn,
                pairs=rel_pairs, pair_diag=pair_diag)
        elif prune_fn is not None:
            pruned = prune_fn(scored, prune_cap)
        else:
            pruned = static_prune(scored, prune_cap)
        if pair_diag.get("v1") == "unit-seating":
            units_rec = {
                "units_seated": pair_diag.get("units_seated", 0),
                "singles_seated": pair_diag.get("singles_seated", 0),
                "dissolved_n": len(pair_diag.get("dissolved", [])),
                "overflow_n": len(pair_diag.get("overflow", [])),
                "pruned_n": len(pruned),
            }
            if rel_diag is not None:
                rel_diag["prune_units"] = units_rec
            for ov in pair_diag.get("overflow", []):
                partials.append({"scope": "prune:unit",
                                 "cause": "unit-overflow:"
                                 + ",".join(ov.get("pair", []))})
        budget.charge(len(scored), "prune-compare")
        if funnel is not None:
            funnel["prune_in"] = len(scored)
            funnel["prune_out"] = len(pruned)
            funnel["prune_units"] = {
                "units_seated": pair_diag.get("units_seated", 0),
                "singles_seated": pair_diag.get("singles_seated", 0),
                "dissolved_n": len(pair_diag.get("dissolved", [])),
                "overflow_n": len(pair_diag.get("overflow", [])),
            }
            funnel["pre_prune_top10"] = [
                {"aid16": a[:16], "score": round(s, 6),
                 "lex": fw.get("a:" + a, 0.0) > 0.0,
                 "dense": darrf.get("a:" + a, 0.0) > 0.0}
                for a, s, _t in sorted(scored, key=lambda c: -c[1])[:10]]
        # Cosine matrix once (numpy): MMR selection below is then
        # O(k^2) lookups instead of O(k^3*d) pure-python cosines.
        names = [a for a, _s, _t in pruned]
        if not names:
            order = []
        else:
            mat = np.array([np.asarray(
                self.idx.atoms[a]["descriptor"], dtype=np.float64)
                for a in names])
            norms = np.linalg.norm(mat, axis=1)
            norms[norms == 0.0] = 1.0
            sim_mat = (mat / norms[:, None]) @ (mat / norms[:, None]).T
            sim = {a: {b: float(sim_mat[i, j])
                       for j, b in enumerate(names)}
                   for i, a in enumerate(names)}
            # R3-2 ([E]): top-D dense-supported pruned cands ride MMR
            # exempt from the sim term (their own penalty is zeroed).
            exempt_d = self._C(
                "MMR_DENSE_EXEMPT_D", MMR_DENSE_EXEMPT_D) or 0
            exempt = set()
            if exempt_d > 0:
                dense_c = [(a, s) for a, s, _t in pruned
                           if darrf.get("a:" + a, 0.0) > 0.0]
                dense_c.sort(key=lambda c: -c[1])
                exempt = {a for a, _s in dense_c[:exempt_d]}
            if exempt:
                def sim_fn(a, b, _sim=sim, _ex=exempt):
                    return 0.0 if a in _ex else _sim[a][b]
            else:
                def sim_fn(a, b, _sim=sim):
                    return _sim[a][b]
            _mmr_cands = [(a, s) for a, s, _t in pruned]
            _mmr_lam = self._C("MMR_LAMBDA", MMR_LAMBDA)
            _mmr_cap = self._C("MMR_SIM_CAP", MMR_SIM_CAP)
            if rel_view is not None and rel_qual:
                # Q12.1(c) (R3-B): intra-polarity MMR per S-02
                # qualifier partition, score-ordered merge. Same
                # sim closure, lambda, and sim_cap as below.
                order = _relquery.partitioned_mmr(
                    _mmr_cands, sim_fn, _mmr_lam,
                    rel_view.scope, rel_view.unresolved,
                    sim_cap=_mmr_cap)
                rel_diag["mmr_partitions"] = len(
                    {_relquery.partition_key(
                        a, rel_view.scope, rel_view.unresolved)
                     for a, _s in _mmr_cands})
            else:
                order = mmr_order_matrix(
                    _mmr_cands, sim_fn, _mmr_lam, len(pruned),
                    sim_cap=_mmr_cap)
        budget.charge(len(order) * len(order), "mmr-pair-compare")
        # -- variable-K admission (Q12.3 final) --------------------------
        # Identified qualifier-explicit pairs (Q12.3-mech, R3-B):
        # relquery.identify_pairs over the emitted universe when
        # REL_QUALIFIERS is on; the settled admit branches seat
        # them jointly (counterparts ride below tau) or defer
        # them explicitly, never one-sided. Flag-off keeps the
        # empty trigger set (settled machinery, not dead code).
        identified_pairs = rel_pairs
        scores = {a: s for a, s, _t in pruned}
        admitted, deferred = admit(
            [(a, scores[a]) for a in order], identified_pairs,
            self._C("TAU_SEL", TAU_SEL),
            self._C("MAX_ENTRIES", MAX_ENTRIES))
        if rel_diag is not None and rel_qual:
            _adm = set(admitted)
            rel_diag["pairs_jointly_admitted"] = sum(
                1 for a, b in rel_pairs
                if a in _adm and b in _adm)
        for aid, reason in deferred:
            partials.append({"scope": f"candidate:{aid[:16]}",
                             "cause": f"selection-deferred:{reason}"})
        if funnel is not None:
            funnel["admitted"] = len(admitted)
            funnel["deferred_by_reason"] = {}
            for _aid, reason in deferred:
                funnel["deferred_by_reason"][reason] = \
                    funnel["deferred_by_reason"].get(reason, 0) + 1
        # -- dossier assembly (Q15.1 late materialization) -------------
        entries = []
        integrity_withheld = 0
        # S4 honest disclosure (2026-10-04): per-entry support labels
        # + dossier-level counts, always on. Context for TRACE, never
        # a trigger (support mix does not separate OOS; see S4-HONEST).
        support_counts = {"lex_only": 0, "dense_only": 0,
                          "both": 0, "neither": 0}
        for aid in admitted:
            if not budget.ok():
                return self._bounded_incomplete(
                    query, pin, budget, events, t0, entries, partials,
                    {"regions_ranked": len(ranked_regions),
                     "admitted": len(entries),
                     "assembly_stopped_at": aid[:16]})
            a = self.idx.atoms[aid]
            try:
                body = self.tl.read_artifact(
                    a["text_art"], expect_digest=a["text_digest"])
                integrity = "intact-verified"
            except (ValueError, OSError):
                partials.append({"scope": f"candidate:{aid[:16]}",
                                 "cause": "integrity-failed:withheld"})
                integrity_withheld += 1
                continue  # integrity-failed never served (Q15.2b)
            budget.charge(1, "assembly-read")
            text = body.decode("utf-8")
            has_lex = fw.get("a:" + aid, 0.0) > 0.0
            has_dense = darrf.get("a:" + aid, 0.0) > 0.0
            support = ("both" if has_lex and has_dense else
                       "lex-only" if has_lex else
                       "dense-only" if has_dense else "neither")
            support_counts[support.replace("-", "_")] += 1
            marks = {"routing_uncertain": uncertain,
                     "outlier": aid in outliers,
                     "resolution": "live"}
            if rel_view is not None and rel_qual:
                umark = rel_view.unresolved.get(aid)
                if umark is not None:  # Q12.2: mark rides to entries
                    marks["unresolved"] = umark
            entries.append({
                "atom_id": aid,
                "issuing_generation": f"{_birth}:{_epoch}:{a['seq']}",
                "resolving_generation": triple,
                "text": text, "span": a["span"],
                "doc_id": a["doc_id"],
                "emitted_score": scores[aid],
                "support": support,
                "verdicts": {"integrity": integrity,
                             "selection": "selected"},
                "marks": marks})
        ms = (time.time() - t0) * 1000.0
        if funnel is not None:
            funnel["integrity_withheld"] = integrity_withheld
            funnel["entries"] = len(entries)
        # -- M2-C hierarchy evidence leg (flag-gated; default off)
        # HIER_GUIDED=True serves HierQuery guided
        # parent->child->atom evidence as a receipt sidecar:
        # emission (entries, cands, regions) above is untouched, so
        # flag-on rows are identical to flag-off. Budget-charged;
        # text stripped from the sidecar rows (receipts stay
        # small; entries carry display text).
        hier_on = bool(self._C("HIER_GUIDED", HIER_GUIDED))
        if hier_on:
            # R-2: held HierServe when wired (one HierQuery across
            # runs, facade-only), else a fresh direct HierQuery.
            # Identical rows/reports either way (entry differential
            # in test_c2_entry_guards_r2.py).
            if _hierserve_wired(self.cfg):
                from tlsys.hierserve import HierServe
                if self._hierserve is None:
                    self._hierserve = HierServe(
                        self.tl, self.idx, self.embed_query)
                hrows, hrep, _htraffic = self._hierserve.guided(
                    query, parent_budget=self._C("HIER_PARENT_BUDGET",
                                                 HIER_PARENT_BUDGET))
                self.last_hier_traffic = dict(_htraffic)
                self.last_hier_backend = "hierserve"
            else:
                hq = HierQuery(self.tl, self.idx, self.embed_query)
                hrows, hrep = hq.guided(
                    query, parent_budget=self._C("HIER_PARENT_BUDGET",
                                                 HIER_PARENT_BUDGET))
                self.last_hier_backend = "hierquery"
            hwork = hrep["work"]
            budget.charge(hwork["parents_scored"]
                          + hwork["children_scored"]
                          + hwork["atoms_scored"], "hier-guided")
            hier_diag = {
                "status": hrep["status"], "work": hwork,
                "roots": hrep["roots"],
                "nomination": hrep["nomination"],
                "rows": [{k: r[k] for k in
                          ("aid", "score", "path", "doc_id", "span",
                           "integrity")} for r in hrows],
                "withheld": hrep.get("withheld", 0)}
        emit_diag = {"emit_dense_atoms": emit_dense,
                     "dense_atom_seeds": len(darrf),
                     "dense_cos_top1": round(dense_cos_top1, 6),
                     "dense_cos_margin": round(dense_cos_margin, 6),
                     "disclose_top1_cut": top1_cut,
                     "top1_trigger_fired": top1_fired,
                     "region_dense_atoms": region_dense,
                     "region_dense_terms": n_region_dense,
                     "support_counts": support_counts,
                     "funnel": funnel}
        if nav_on:
            # Flag-gated only: default runs never carry this key
            # (receipt byte-identical).
            emit_diag["candidate_nav"] = nav_diag
        if hier_on:
            # Flag-gated only (see above): default receipts never
            # carry this key.
            emit_diag["hierarchy"] = hier_diag
        receipt = self._receipt(query, pin, budget, events, ms, s1, s2,
                                uncertain, m_eff, ranked_regions,
                                sel_regions, cands, pruned, entries,
                                partials, unpruned, emit_diag,
                                rel_diag=rel_diag)
        return {"entries": entries}, receipt

    def _receipt(self, query, pin, budget, events, ms, s1, s2,
                 uncertain, m_eff, ranked_regions, sel_regions,
                 cands, pruned, entries, partials, unpruned,
                 emit_diag=None, rel_diag=None):
        _birth, _epoch, _mx, triple = pin
        if entries:
            support, sel_out = "supported-results", "selected"
        elif not ranked_regions:
            support, sel_out = "no-emission", "no-emission"
        elif not sel_regions:
            support, sel_out = "bounded-incomplete", "no-region-selected"
        else:
            support, sel_out = "examined-no-support", "none-cleared-tau"
        # S4 honest disclosure (2026-10-04): the top1 cut is a ONE-SIDED
        # low-similarity flag. Silence means "unassessed", never "sure":
        # near-miss OOS is invisible to every TL signal tested and the
        # far-OOS operating point does not transfer across corpora
        # (evidence: tl-eval/evidence/s4-honest-2026-10-04/). The legacy
        # TAU/EPS gate (dead at TAU=EPS=0 defaults) keeps its "not sure"
        # with honest source attribution when it fires.
        top1_fired = (emit_diag or {}).get("top1_trigger_fired", False)
        if top1_fired:
            presentation = "not sure (low retrieval similarity)"
        elif uncertain:
            presentation = "not sure (low region support)"
        else:
            presentation = ("unassessed (similarity above floor; "
                            "not an answerability claim)")
        # Relations receipt (flag-gated): when REL_QUALIFIERS is on,
        # relation-backed qualifier signals exist, so Q12.1/Q12.2/
        # Q12.3-joint move from flags_not_produced to produced
        # flags. Flag-off: the not-produced wording stands and no
        # rel key is added.
        _flags = {
            "routing_uncertain_Q3.3": uncertain,
            "low_retrieval_similarity_Q3.3": top1_fired,
            "narrow_Q9.2": True,
        }
        _fnp = {
            # Producer machinery absent in Narrow; absent is
            # honest, never default-false.
            "activation_drift_Q8.1": "no spreading/activation "
            "machinery in Narrow",
            "qualifier_Q12.1": "atoms carry no qualifier "
            "signals (named S-02-ingestion input)",
            "unresolved_Q12.2": "no qualifier signals to be "
            "unrepresentable against",
            "joint_preservation_Q12.3": "no identified pairs "
            "(trigger needs qualifier signals)",
        }
        if rel_diag is not None and rel_diag.get("qualifiers"):
            _flags["qualifier_Q12.1"] = True
            _flags["unresolved_Q12.2"] = any(
                "unresolved" in e.get("marks", {}) for e in entries)
            # Q12.3-mech (R3-B): True = pair trigger evaluated
            # (counts in rel_consumption; vacuous when zero).
            _flags["joint_preservation_Q12.3"] = True
            del _fnp["qualifier_Q12.1"]
            del _fnp["unresolved_Q12.2"]
            del _fnp["joint_preservation_Q12.3"]
        rec = {
            "query": query,
            "pinned_generation": triple,
            "execution": {"status": "complete",
                          "reason": None},
            "support_findings": support,
            "selection_outcomes": sel_out,
            "metrics": {
                # Q5.2 six dimensions, recorded per run ([E]-
                # provisional, unenforced). H/E/P are structural
                # zeros in Narrow (no lateral/edges/partitions).
                "H_hops": 0, "R_regions": len(sel_regions),
                "E_edges": 0, "C_candidates": len(cands),
                "P_partitions": 0, "T_ms": round(ms, 2),
                "work_used": budget.used,
                "work_budget": budget.cap,
                "op_class_counts": budget.counts,
                "cost_table": COST_TABLE_VERSION,
                "regions_ranked": len(ranked_regions),
                "prune_survivors": len(pruned),
                "entries": len(entries),
                "top_region_score": s1,
                "runnerup_margin": s1 - s2,
                "m_effective": m_eff,
                "tau_sel": self._C("TAU_SEL", TAU_SEL),
                "max_entries": self._C("MAX_ENTRIES", MAX_ENTRIES),
                "unpruned_reference": unpruned,
                "emit_dense_atoms": (emit_diag or {}).get(
                    "emit_dense_atoms", False),
                "dense_atom_seeds": (emit_diag or {}).get(
                    "dense_atom_seeds", 0),
                "dense_cos_top1": (emit_diag or {}).get(
                    "dense_cos_top1", 0.0),
                "dense_cos_margin": (emit_diag or {}).get(
                    "dense_cos_margin", 0.0),
                "disclose_top1_cut": (emit_diag or {}).get(
                    "disclose_top1_cut"),
                "top1_trigger_fired": (emit_diag or {}).get(
                    "top1_trigger_fired", False),
                "region_dense_atoms": (emit_diag or {}).get(
                    "region_dense_atoms", False),
                "region_dense_terms": (emit_diag or {}).get(
                    "region_dense_terms", 0),
                "support_counts": (emit_diag or {}).get(
                    "support_counts"),
                "funnel": (emit_diag or {}).get("funnel")},
            "flags": _flags,
            "flags_not_produced": _fnp,
            "uncertainty_presentation": presentation,
            "partials": partials,
            "disclosure_UQ1": {"events": events},
        }
        if (emit_diag or {}).get("candidate_nav") is not None:
            # Flag-gated only (see _run_inner): default receipts
            # never carry this key.
            rec["metrics"]["candidate_nav"] = \
                emit_diag["candidate_nav"]
        if (emit_diag or {}).get("hierarchy") is not None:
            # Flag-gated only (see _run_inner): default receipts
            # never carry this key.
            rec["metrics"]["hierarchy"] = emit_diag["hierarchy"]
        if rel_diag is not None:
            rec["rel_consumption"] = rel_diag
        if getattr(self.idx, "retired_docs", None):
            # Lane-2 retirement disclosure: present ONLY when the pin
            # carries retirements (retirement-free receipts unchanged).
            rec["metrics"]["retired"] = {
                "docs": list(self.idx.retired_docs),
                "atoms_excluded": int(
                    getattr(self.idx, "retired_atoms", 0))}
        return rec

    def _bounded_incomplete(self, query, pin, budget, events, t0,
                            entries, partials, extra):
        _birth, _epoch, _mx, triple = pin
        ms = (time.time() - t0) * 1000.0
        reason = budget.exhaustion or "unknown"
        partials = ([{"scope": "query", "cause": reason}] + partials)
        metrics = {"H_hops": 0,
                   "R_regions": extra.get("regions_ranked", 0),
                   "E_edges": 0,
                   "C_candidates": extra.get("admitted", 0),
                   "P_partitions": 0, "T_ms": round(ms, 2),
                   "work_used": budget.used,
                   "work_budget": budget.cap,
                   "op_class_counts": budget.counts,
                   "cost_table": COST_TABLE_VERSION,
                   "entries": len(entries),
                   # Schema symmetry with _receipt (audit 2026-10-04):
                   # this path never computes dense emission diagnostics.
                   "emit_dense_atoms": False,
                   "dense_atom_seeds": 0,
                   "dense_cos_top1": 0.0,
                   "dense_cos_margin": 0.0,
                   "support_counts": None,
                   "funnel": None}
        metrics.update({k: v for k, v in extra.items()
                        if k not in metrics})
        if getattr(self.idx, "retired_docs", None):
            metrics["retired"] = {
                "docs": list(self.idx.retired_docs),
                "atoms_excluded": int(
                    getattr(self.idx, "retired_atoms", 0))}
        return {"entries": entries}, {
            "query": query, "pinned_generation": triple,
            "execution": {"status": "bounded-incomplete",
                          "reason": reason},
            "support_findings": "bounded-incomplete",
            "selection_outcomes": "budget-hit",
            "metrics": metrics,
            "flags": {"routing_uncertain_Q3.3": None,
                      "low_retrieval_similarity_Q3.3": None,
                      "narrow_Q9.2": True},
            "flags_not_produced": {
                "activation_drift_Q8.1": "no spreading/activation "
                "machinery in Narrow",
                "qualifier_Q12.1": "atoms carry no qualifier signals",
                "unresolved_Q12.2": "no qualifier signals",
                "joint_preservation_Q12.3": "no identified pairs",
            },
            "uncertainty_presentation": "not sure (bounded-incomplete)",
            "partials": partials,
            "disclosure_UQ1": {"events": events}}


# ---- M2-A bounded hierarchy access ------------------------------------
HIER_TOP_PARENTS = 4
HIER_TOP_CHILDREN = 8
HIER_TOP_ATOMS = 50
HIER_MAX_DEPTH = 4
HIER_MAX_VISITS = 10000


def _hier_cos(qvec, desc):
    """Float64 cosine, same definition as the Narrow dense legs."""
    q = np.asarray(qvec, dtype=np.float64)
    d = np.asarray(desc, dtype=np.float64)
    qn = float(np.linalg.norm(q)) or 1.0
    dn = float(np.linalg.norm(d)) or 1.0
    return float(q @ d / (qn * dn))


class HierQuery:
    """Bounded higher->child->evidence access over the seg hierarchy.

    guided(): score parent descriptors (routing guidance only), take
    the top roots, descend child references with visited-set cycle
    protection + depth/visit bounds, score reached leaves, then score
    member atoms EXACTLY (emission support comes only from atom
    vectors, never from parent scores). Every returned row carries
    its [parent, child, atom] receipt path plus the verified source
    span. Work is counted per scoring class (parents/children/atoms)
    in the same NavCounters vocabulary as the place boundary.

    flat(): the matched-work control -- deterministic sorted-order
    leaf scoring with the same total scoring budget and exact atom
    rescoring, but no parent routing. The hierarchy ablation passes
    when guided() reaches known-group evidence flat() misses at
    equal measured work.

    Reads committed data through NarrowIndex only (build-stable
    populations); no HNSW/flat nomination backend is consulted.
    NarrowQuery is untouched: default Narrow behavior is identical
    with or without this class.

    Parent nomination (M2-C): parent_budget=None (default) scores
    every parent exactly, as before. A parent_budget int nominates
    a bounded candidate set first -- lexical BM25 support routed
    through atom->leaf->parent references, ranked, pid-order
    backfill to the budget -- and exactly scores only the
    nominees (same cosine math; candidate IDs drive keyed
    access). Nomination draws only from index-covered evidence at
    the pin, so acknowledged pending-placement and changed
    evidence stay nominatable; non-nominated parents are excluded
    from scoring (count disclosed). The nomination receipt names
    the mode, budget, support source and exclusion count.
    """

    def __init__(self, tlstore, index, embed_query):
        self.tl = tlstore
        self.idx = index
        self.embed_query = embed_query
        self.counters = NavCounters()
        # M2-C nomination reverse maps, built once per index
        # population (validated like NarrowQuery._dense_cache; index
        # populations are build-once per generation).
        self._nomap_key = None
        self._atom_leaves = {}
        self._leaf_parents = {}

    def _nomination_maps(self, leaves, parents):
        """(atom->leaves, leaf->parents) for bounded nomination.

        Built once per (index identity, triple, population shape);
        rebuilds on any mismatch. Pure index reads, no storage.
        Returns True on a fresh build, False on a cache hit.
        C2: delegates to the facade's incrementally maintained maps
        when present (read-only shared refs), else builds as before.
        """
        delegate = getattr(self.idx, "nomination_maps", None)
        if delegate is not None:
            try:
                amap, pmap, key = delegate()
            except AttributeError:
                pass  # reference backend / stub: build as before
            else:
                if key == self._nomap_key:
                    return False
                self._atom_leaves = amap
                self._leaf_parents = pmap
                self._nomap_key = key
                return True
        pids = sorted(parents)
        key = (id(self.idx), self.idx.triple, len(leaves),
               len(parents), pids[0] if pids else None,
               pids[-1] if pids else None)
        if key == self._nomap_key:
            return False
        atom_leaves = {}
        for lid, lf in leaves.items():
            for aid in lf["members"]:
                atom_leaves.setdefault(aid, []).append(lid)
        leaf_parents = {}
        for pid, par in parents.items():
            for child in par.get("children", []):
                leaf_parents.setdefault(child, []).append(pid)
        self._atom_leaves = atom_leaves
        self._leaf_parents = leaf_parents
        self._nomap_key = key
        return True

    def _nominate_parents(self, query, parents, budget):
        """(nominee_ids, receipt) bounded parent nomination.

        Lexical BM25 support (posting-bounded) routed to parents
        through the cached reverse maps, ranked by support
        (ties by pid), pid-order backfill to the budget when
        lexical support is thin or empty. Deterministic.
        """
        lex = self.idx.bm25(query)
        support = {}
        for aid, s in lex.items():
            for lid in self._atom_leaves.get(aid, ()):
                for pid in self._leaf_parents.get(lid, ()):
                    if pid in parents and s > support.get(pid, 0.0):
                        support[pid] = s
        ranked = sorted(support, key=lambda p: (-support[p], p))
        nominees = list(ranked[:max(0, int(budget))])
        backfilled = 0
        if len(nominees) < max(0, int(budget)):
            for pid in sorted(parents):
                if pid not in support and pid not in nominees:
                    nominees.append(pid)
                    backfilled += 1
                    if len(nominees) >= max(0, int(budget)):
                        break
        return nominees, {
            "lex_atoms": len(lex),
            "lex_supported_parents": len(ranked),
            "backfilled_pid_order": backfilled,
            "lexical_empty": not lex}

    def guided(self, query, top_parents=HIER_TOP_PARENTS,
               top_children=HIER_TOP_CHILDREN,
               top_atoms=HIER_TOP_ATOMS, parent_budget=None):
        """(rows, report) via parent-routed descent. Deterministic."""
        leaves = self.idx.seg_leaves
        parents = self.idx.seg_parents
        work = {"parents_scored": 0, "children_scored": 0,
                "atoms_scored": 0, "member_visits": 0}
        if not parents:
            return [], {"status": "no-hierarchy", "work": work,
                        "roots": [], "leaves_seen": 0,
                        "leaves_used": 0, "max_depth_used": 0,
                        "cycle_skips": 0,
                        "nomination": {"mode": "exact",
                                       "budget": parent_budget,
                                       "parents_total": 0,
                                       "scored_all": True}}
        qvec = self.embed_query(query)
        if parent_budget is None:
            pscore = {pid: _hier_cos(qvec, par["descriptor"])
                      for pid, par in parents.items()}
            work["parents_scored"] = len(pscore)
            nomination = {"mode": "exact", "budget": None,
                          "parents_total": len(parents),
                          "scored_all": True}
        else:
            maps_built = self._nomination_maps(leaves, parents)
            nominees, nrep = self._nominate_parents(
                query, parents, parent_budget)
            pscore = {pid: _hier_cos(qvec, parents[pid]["descriptor"])
                      for pid in nominees if pid in parents}
            work["parents_scored"] = len(pscore)
            nomination = {"mode": "bounded-lexical",
                          "budget": max(0, int(parent_budget)),
                          "parents_total": len(parents),
                          "scored_all": len(pscore) == len(parents),
                          "excluded_from_scoring":
                          len(parents) - len(pscore),
                          "maps_built": maps_built,
                          "map_entries": len(self._atom_leaves)}
            nomination.update(nrep)
        roots = sorted(pscore, key=lambda h: (-pscore[h], h))
        roots = roots[:max(0, int(top_parents))]
        leaf_hits = {}
        leaf_root = {}
        visited = set()
        cycle_skips = 0
        depth_skips = 0
        dangling = 0
        edge_visits = 0
        max_depth_used = 0
        capped = False
        for root in roots:
            if root in visited:
                cycle_skips += 1
                continue
            visited.add(root)
            stack = [(root, 0)]
            while stack and not capped:
                node, depth = stack.pop()
                kids = self.idx.holons.get(node, {}).get(
                    "children", [])
                for child in kids:
                    edge_visits += 1
                    if edge_visits > HIER_MAX_VISITS:
                        capped = True
                        break
                    if child in visited:
                        if child in parents:
                            cycle_skips += 1
                        continue
                    nd = depth + 1
                    if nd > HIER_MAX_DEPTH:
                        depth_skips += 1
                        continue
                    if child not in self.idx.holons:
                        dangling += 1
                        continue
                    visited.add(child)
                    max_depth_used = max(max_depth_used, nd)
                    if child in leaves:
                        leaf_hits[child] = _hier_cos(
                            qvec, leaves[child]["descriptor"])
                        work["children_scored"] += 1
                        leaf_root.setdefault(child, root)
                    elif child in parents:
                        stack.append((child, nd))
                    else:
                        dangling += 1
        ranked = sorted(leaf_hits,
                        key=lambda h: (-leaf_hits[h], h))
        ranked = ranked[:max(0, int(top_children))]
        atom_hits = []
        retired_aids = getattr(self.idx, "retired_aids", frozenset())
        retired_skipped = 0
        for lid in ranked:
            for aid in leaves[lid]["members"]:
                work["member_visits"] += 1
                if work["member_visits"] > HIER_MAX_VISITS:
                    capped = True
                    break
                a = self.idx.atoms.get(aid)
                if a is None:
                    if aid in retired_aids:
                        retired_skipped += 1
                    else:
                        dangling += 1
                    continue
                atom_hits.append((_hier_cos(qvec, a["descriptor"]),
                                  aid, lid))
                work["atoms_scored"] += 1
            if capped:
                break
        atom_hits.sort(key=lambda t: (-t[0], t[1]))
        rows = []
        withheld = 0
        for score, aid, lid in atom_hits[:max(0, int(top_atoms))]:
            a = self.idx.atoms[aid]
            try:
                body = self.tl.read_artifact(
                    a["text_art"], expect_digest=a["text_digest"])
                text = body.decode("utf-8")
            except (ValueError, OSError):
                withheld += 1
                continue  # integrity-failed never served (Q15.2b)
            rows.append({"aid": aid, "score": score,
                         "path": [leaf_root[lid], lid, aid],
                         "doc_id": a["doc_id"], "span": a["span"],
                         "text": text,
                         "integrity": "intact-verified"})
        report = {"status": "ok", "work": work, "roots": roots,
                  "leaves_seen": len(leaf_hits),
                  "leaves_used": len(ranked),
                  "max_depth_used": max_depth_used,
                  "cycle_skips": cycle_skips,
                  "depth_skips": depth_skips,
                  "dangling_children": dangling,
                  "retired_skipped": retired_skipped,
                  "withheld": withheld,
                  "visits_capped": capped,
                  "nomination": nomination}
        self.counters.record(
            "hier-guided", discovered=len(leaf_hits),
            visited=work["member_visits"],
            rescored=work["atoms_scored"], roots=len(roots))
        return rows, report

    def flat(self, query, total_budget, top_atoms=HIER_TOP_ATOMS):
        """(rows, report): matched-work flat control (no routing).

        Scores the first total_budget leaves in sorted-id order,
        ranks them, then spends the leftover budget scoring members
        of the top leaves exactly. Same scoring math and receipt
        shape as guided(); paths are [leaf, atom] (no parent leg).
        """
        leaves = self.idx.seg_leaves
        work = {"leaves_scored": 0, "atoms_scored": 0,
                "member_visits": 0}
        if not leaves:
            return [], {"status": "no-hierarchy", "work": work}
        qvec = self.embed_query(query)
        ordered = sorted(leaves)
        room = max(0, int(total_budget))
        take = ordered[:min(room, len(ordered))]
        lscore = {lid: _hier_cos(qvec, leaves[lid]["descriptor"])
                  for lid in take}
        work["leaves_scored"] = len(lscore)
        leftover = room - len(lscore)
        ranked = sorted(lscore, key=lambda h: (-lscore[h], h))
        atom_hits = []
        for lid in ranked:
            for aid in leaves[lid]["members"]:
                if len(atom_hits) >= leftover:
                    break
                work["member_visits"] += 1
                a = self.idx.atoms.get(aid)
                if a is None:
                    continue
                atom_hits.append((_hier_cos(qvec, a["descriptor"]),
                                  aid, lid))
                work["atoms_scored"] += 1
            if len(atom_hits) >= leftover:
                break
        atom_hits.sort(key=lambda t: (-t[0], t[1]))
        rows = []
        withheld = 0
        for score, aid, lid in atom_hits[:max(0, int(top_atoms))]:
            a = self.idx.atoms[aid]
            try:
                body = self.tl.read_artifact(
                    a["text_art"], expect_digest=a["text_digest"])
                text = body.decode("utf-8")
            except (ValueError, OSError):
                withheld += 1
                continue
            rows.append({"aid": aid, "score": score,
                         "path": [lid, aid],
                         "doc_id": a["doc_id"], "span": a["span"],
                         "text": text,
                         "integrity": "intact-verified"})
        report = {"status": "ok", "work": work,
                  "leaves_seen": len(lscore),
                  "withheld": withheld}
        self.counters.record(
            "hier-flat", discovered=len(lscore),
            visited=work["member_visits"],
            rescored=work["atoms_scored"])
        return rows, report
