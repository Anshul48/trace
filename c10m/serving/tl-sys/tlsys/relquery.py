"""First query-path consumption of S-02 section 1b relation records.

Covers the relations-gap dependency items behind the Narrow GAP rows
(TL-VERDICT-TABLE Q10.1/Q12.1/Q12.2/Q12.3-mechanism + S-02 section
1b). Round 2 landed Q10.1/Q12.1(a)/(b)/Q12.2; round 3 (R3-B) adds
Q12.1(c) + the Q12.3-mechanism pair trigger, both ruled in
tl-eval/evidence/round3-2026-10-05/trackB/MECHANISM-RULING.md:

  Q10.1 hub suppression: family deg^{-alpha} applied to
    emitted-candidate scores, selection-time post-emission, never
    in-loop. Alpha is [E] with the D-12 sqrt (0.5) starting
    ballpark; fit unconstrained (sublinearity is the hypothesis,
    not a constraint -- S-04 closure Q10.1). No ceilings or
    stoplists (conformant refusal stands).
  Q12.1(a) scope riding: qualifier scope rides per candidate
    through prune/MMR. Representation stays S-02's: qualifier
    dicts are carried verbatim, never re-encoded (Q7.1 precedent).
  Q12.1(b) amended collapse: near-dup collapse compares content
    plus full meaning-essential qualification; uncertain
    equivalence never collapses. Exact-text discipline kept
    (sub-quadratic hashing, Q10.2a cost guard).
  Q12.2 amended unresolved: unresolved-marked candidates are
    collapse-exempt, flow on score, and carry the mark to the
    dossier entries. No separate MMR stream (struck amendment).

Eligibility gating: ONLY relations eligible at the resolving
query's pinned generation (relations.eligible flat-AND over live
atoms + visible relations) contribute degrees or qualifier
signals. Status is reported verbatim and never upgrades.

Scope source: an eligible relation's qualifier scope rides to its
endpoint atoms only. Grounding atoms are supporting evidence, not
the qualified claim, so grounding membership confers no scope and
no unresolved mark.

Defaults: everything here is default-OFF (REL_HUB_SUPPRESS,
REL_QUALIFIERS False; REL_HUB_ALPHA 0.5 inert unless suppression
is on). The Narrow path calls into this module only when a flag
is on, and flag-OFF runs are byte-identical with or without
committed relations.

Round-3 (R3-B) mechanism batch, behind REL_QUALIFIERS:
  Q12.1(c) intra-polarity MMR: partition pruned candidates by
    S-02 qualifier value verbatim (partition_key =
    collapse_sig; untouched + unresolved-marked atoms join one
    unpartitioned pool), run exact MMR within each partition,
    merge heads by emitted score ([E]-default allocation: no
    per-partition floor/ceiling; single pool == plain MMR).
  Q12.3-mechanism pair identification: identify_pairs reports
    qualifier-explicit counterpart atoms over the emitted
    universe (same rel_type + same context endpoints +
    qualifiers equal except negated, opposite negated sides,
    neither atom unresolved-marked); query.py passes them to
    fuse.admit, whose settled branches seat them jointly,
    ride them below tau, or defer them explicitly.
  Both rules' underdetermined clauses are recorded as
  UNRESOLVED-implemented assumptions in the ruling note.
Explicitly still out: H/E/P receipt dimensions stay structural
zeros (degrees looked up, never traversed: no lateral hops, no
edge walk); prune-stage reserved seats for pairs (cap-cut pairs
surface via admit's counterpart-unidentified deferral).

Round-9 track B (additive, default-inert):
  Q4.1(b) relational traversal: traverse() routes THROUGH the
    relation graph -- bounded breadth-first expansion over
    RelIndex endpoint adjacency from seed anchors (multi-hop
    bridge reachability; Q7.1 per-call scratch, index read-only
    on the path). Consumed only by the dossier relational shape
    behind DOSSIER_REL_TRAVERSAL (default off).
  Qualifier-signal ingestion: qualifier judgments committed as
    durable S-02 records (rel_type QUAL_SIGNAL_TYPE, one atom
    endpoint, self-grounding) via make_qual_signal /
    commit_qual_signals, read back per atom by qual_signals().
    No new store machinery: the existing relation commit/read
    path carries them (relations.py untouched, imported only).
  Q12.1(c) W12 bakeoff arm: partitioned_mmr(merge="roundrobin")
    strict-interleave alternative to the score-merge default
    (default merge="score" reproduces the settled order exactly).

Reads are pinned-generation S-02 reads under Q8.2 discipline
(same pin the Narrow path resolves at).

M1 lane D (F4 repair, additive, default-identical): reusable
RelView keyed by pin. load() builds the view once per
(store, pinned generation, live-atom set) and serves the shared
view to every later query at the same pin -- zero record
copies, zero eligibility re-evaluation, zero store reads on a
hit. Pin discipline mirrors the R8-A RelIndex substrate it is
built on (retained, not reimplemented): a cache entry serves
only on an exact (birth, epoch, max_seq) match for the same
store plus an equal live set; any other pin, store, or live set
rebuilds from scratch (no cross-generation mixing, no
incremental view extend). Oracle mode (TL_REL_ORACLE=1) and
audit mode (TL_REL_AUDIT=1) bypass the cache entirely, and a
caller-held index covering the pin from a FOREIGN store bypasses
it too, so every conformance/diagnostic path keeps its exact
pre-M1 behavior. Served views are shared and read-only by
contract (every in-tree consumer only reads; the differential
suite pins this). Disclosure legs gain a typed enumeration
(DisclosureLeg); RelView carries its leg.
"""

import hashlib
import json
import math
import os

from enum import Enum

from tlsys.fuse import mmr_order_matrix
from tlsys.identity import canonical_json_bytes
from tlsys.relations import AUDIT_ENV
from tlsys.relations import commit_relations as _commit_relations
from tlsys.relations import eligible as _eligible
from tlsys.relations import endpoint_degrees, get_index, read_relations
from tlsys.relations import LEG as _RELATIONS_LEG
from tlsys.relations import make_record as _make_record
from tlsys.relations import ORACLE_ENV

REL_HUB_SUPPRESS = False
REL_HUB_ALPHA = 0.5
REL_QUALIFIERS = False

# Qualifier-signal ingestion (round 9 track B): distinguished
# rel_type for ingested per-atom qualifier judgments. The durable
# form is an ordinary S-02 relation record (single atom endpoint,
# self-grounding); the existing commit/read/index path carries it.
QUAL_SIGNAL_TYPE = "tlsys/qualifier-signal/v1"


class DisclosureLeg(str, Enum):
    """Typed disclosure-leg vocabulary (M1 lane D).

    The commit disclosure leg routes indexed readers to the ops
    carrying their records (RELREAD-PROFILE section 4.3 rule 5).
    Values mirror the legs stamped across tl-sys; RELATIONS is
    contract-checked against relations.LEG at import (fail-loud
    on substrate drift). UNKNOWN is the classifier bucket for a
    parsed disclosure whose leg is missing or unrecognized (not
    a stamped value): like any known non-relations leg, it is
    NOT the relations leg. None is reserved for undecidable
    disclosures (unparseable/non-dict: fail-open, content guards
    decide, exactly as the relations prefilter).
    """

    RELATIONS = "relations"
    INGEST = "ingest"
    INGEST_HOLON = "ingest-holon"
    PLACE_XDOC = "place-xdoc"
    UNKNOWN = "unknown"

    @classmethod
    def coerce(cls, value):
        """The member for `value`: itself when already a member,
        the matching member for a known leg string, else UNKNOWN."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            for member in cls:
                if value == member.value:
                    return member
        return cls.UNKNOWN


if DisclosureLeg.RELATIONS.value != _RELATIONS_LEG:
    raise AssertionError(
        "DisclosureLeg.RELATIONS drifted from relations.LEG: "
        f"{DisclosureLeg.RELATIONS.value!r} != {_RELATIONS_LEG!r}")


def leg_of_row(row):
    """Typed disclosure leg of a read_commits row, or None.

    None covers only undecidable disclosures (unparseable or
    non-dict: fail-open, the caller keeps the row and lets
    content guards decide). A parsed dict yields a member:
    RELATIONS/INGEST/... for known legs, UNKNOWN for a missing
    or unrecognized leg (dropped like any non-relations leg).
    Bridge to the substrate prefilter:
    relations._is_relation_row(row) is True exactly when this
    returns RELATIONS or None (proven by the M1-D differential
    battery, not asserted here). This classifier types the
    vocabulary only; relations.py remains the sole relation
    reader.
    """
    try:
        dis = json.loads(row[5])
    except (ValueError, TypeError):
        return None
    if not isinstance(dis, dict):
        return None
    return DisclosureLeg.coerce(dis.get("leg"))


class RelView:
    """Eligibility-gated relation state at one pinned generation."""

    def __init__(self, visible, eligible_recs, reasons, degrees,
                 scope, unresolved):
        self.visible = visible    # {rid: record} all records at pin
        self.eligible = eligible_recs  # {rid: record} eligible at pin
        self.reasons = reasons    # {rid: [reason]} ineligible only
        self.degrees = degrees    # {endpoint: degree} eligible-only
        self.scope = scope        # {aid: [(rid, qualifiers)]} endpoints
        self.unresolved = unresolved  # {aid: mark} endpoints, eligible
        self.leg = DisclosureLeg.RELATIONS  # typed materialized leg


# Module RelView cache: (db_path, birth, epoch, max_seq) ->
# (live frozenset, RelView). Bounded (FIFO eviction); every serve
# re-validates the pin AND the live set, so a stale entry can
# only cause a rebuild, never a stale read. Pin-exact: unlike the
# RelIndex (which extends across same-generation pins), a view is
# built once per pin and shared across queries at that pin only.
_VIEW_CACHE_MAX = 8
_VIEW_CACHE = {}

# Process-local relation-path work counters (evidence, not
# behavior): full per-call builds, cache serves, bypass builds
# (oracle/audit/foreign-index paths), and relation records
# scanned by builds. A cache hit touches zero records.
_VIEW_STATS = {"builds": 0, "hits": 0, "bypasses": 0,
               "rows_built": 0}


def _view_cache_key(tlstore, pinned):
    return (os.path.abspath(tlstore.store.db_path),
            pinned[0], pinned[1], pinned[2])


def invalidate_rel_view(tlstore=None):
    """Explicit invalidation: drop cached RelView entries (all, or
    just `tlstore`'s). Pin discipline already prevents stale serves;
    this is lifecycle control for tests and cache-bounded operation."""
    if tlstore is None:
        _VIEW_CACHE.clear()
        return
    prefix = os.path.abspath(tlstore.store.db_path)
    for key in [k for k in _VIEW_CACHE if k[0] == prefix]:
        del _VIEW_CACHE[key]


def rel_view_stats():
    """Copy of the relation-path work counters (see _VIEW_STATS)."""
    return dict(_VIEW_STATS)


def reset_rel_view_stats():
    """Zero the relation-path work counters."""
    for key in _VIEW_STATS:
        _VIEW_STATS[key] = 0


def rel_view_cache_info():
    """Cache shape for evidence: {"size": n, "max": _VIEW_CACHE_MAX}."""
    return {"size": len(_VIEW_CACHE), "max": _VIEW_CACHE_MAX}


def _build_view(raw, live, idx):
    """Assemble a RelView from pinned raw records.

    The exact pre-M1 per-call build, extracted verbatim: flat-AND
    eligibility over all raw records, eligible-only degrees,
    endpoint scope/unresolved maps, then index opposition material
    when built over an index. Pure over its inputs.
    """
    visible_ids = frozenset(raw)
    elig, reasons = {}, {}
    for rid, item in raw.items():
        rec = item["record"]
        res = _eligible(rec, live, visible_ids)
        if res["eligible"]:
            elig[rid] = rec
        else:
            reasons[rid] = res["reasons"]
    degrees = endpoint_degrees(list(elig.values()))
    scope, unresolved = {}, {}
    for rid, rec in elig.items():
        eps = rec.get("endpoints", [])
        ids = list(eps) if rec.get("interchangeable") \
            else [e[1] for e in eps]
        for aid in set(ids):
            scope.setdefault(aid, []).append((rid, rec["qualifiers"]))
        mark = rec.get("qualifiers", {}).get("unresolved")
        if mark is not None:
            for aid in set(ids):
                unresolved.setdefault(aid, mark)
    view = RelView({r: raw[r]["record"] for r in raw}, elig, reasons,
                   degrees, scope, unresolved)
    if idx is not None:
        view._opp = {rid: idx.opp[rid] for rid in elig
                     if rid in idx.opp}
    return view


def _foreign_covering_index(tlstore, index, pinned):
    """True iff `index` covers `pinned` from a FOREIGN store (or an
    untyped holder without store provenance). Such an index keeps
    the exact pre-M1 per-call behavior (its own records are read)
    and bypasses the view cache, so foreign records can never
    poison this store's cached views."""
    if index is None or not index.covers(pinned):
        return False
    return (getattr(index, "db_path", None)
            != os.path.abspath(tlstore.store.db_path))


def load(tlstore, pinned, live_atoms, index=None):
    """Build or serve the RelView at `pinned` (TLStore.pin() tuple).

    live_atoms: set of atom ids live at the pin (Narrow has no
      retirement, so index atoms == live).
    index: optional caller-held RelIndex; used only when it covers
      `pinned` exactly, else the module cache serves (pin discipline:
      a newer or foreign index is never served for this pin).
      TL_REL_ORACLE=1 ignores `index` and serves the fullscan oracle
      with no index material (exact pre-index behavior).

    M1 lane D: the first call at a pin builds the view (the exact
    pre-M1 per-call build) and caches it; later calls at the same
    pin with the same live set are served the shared view (zero
    record copies, zero eligibility work, zero store reads). The
    served view is shared and read-only by contract: callers must
    not mutate it. Oracle mode, audit mode (TL_REL_AUDIT=1), and a
    foreign covering index bypass the cache with the exact pre-M1
    per-call behavior. Use invalidate_rel_view for lifecycle
    control and rel_view_stats for work evidence.
    """
    live = set(live_atoms)
    if os.environ.get(ORACLE_ENV) == "1":
        idx = None
        raw = read_relations(tlstore, pinned)
        _VIEW_STATS["bypasses"] += 1
        _VIEW_STATS["rows_built"] += len(raw)
        return _build_view(raw, live, idx)
    bypass = (os.environ.get(AUDIT_ENV) == "1"
              or _foreign_covering_index(tlstore, index, pinned))
    key = None
    if not bypass:
        key = _view_cache_key(tlstore, pinned)
        ent = _VIEW_CACHE.get(key)
        if ent is not None and ent[0] == frozenset(live):
            _VIEW_STATS["hits"] += 1
            return ent[1]
    if index is not None and index.covers(pinned):
        idx = index
        raw = idx.records_copy()
    else:
        idx = get_index(tlstore, pinned)
        raw = read_relations(tlstore, pinned)
    view = _build_view(raw, live, idx)
    _VIEW_STATS["rows_built"] += len(raw)
    if bypass:
        _VIEW_STATS["bypasses"] += 1
    else:
        _VIEW_STATS["builds"] += 1
        if len(_VIEW_CACHE) >= _VIEW_CACHE_MAX:
            _VIEW_CACHE.pop(next(iter(_VIEW_CACHE)))
        _VIEW_CACHE[key] = (frozenset(live), view)
    return view


def hub_factor(aid, degrees, alpha):
    """Q10.1 penalty factor for one candidate: deg^{-alpha}.

    Atoms with no eligible-relation presence (deg 0 / absent) get
    exactly 1.0: suppression damps hubs, never invents signal for
    unconnected atoms. Alpha is used unconstrained per Q10.1
    (must still be a finite number; validated by the caller).
    """
    deg = degrees.get(aid, 0)
    if deg <= 0:
        return 1.0
    return math.pow(deg, -alpha)


def apply_hub(cands, degrees, alpha):
    """{aid: score} with the Q10.1 factor applied. Pure."""
    return {aid: score * hub_factor(aid, degrees, alpha)
            for aid, score in cands.items()}


def collapse_sig(aid, scope):
    """Canonical qualifier signature for one candidate: sorted tuple
    of canonical qualifier bytes over eligible relations touching
    it. Empty tuple when untouched (collapse then behaves exactly
    as the Narrow exact-only rule)."""
    quals = scope.get(aid, [])
    return tuple(sorted(canonical_json_bytes(q) for _rid, q in quals))


def prune_rel(cands, cap, scope, unresolved):
    """Score-ordered greedy with qualifier-aware collapse (amended
    Q12.1(b)) + unresolved exemption (amended Q12.2).

    cands: [(aid, score, text)]. Collapse key is (text-sha256,
    collapse_sig): exact-text duplicates collapse iff their full
    meaning-essential qualification matches; differing (or
    one-sided) qualification never collapses. Unresolved-marked
    candidates always survive on score. Score order out. Pure.
    """
    cands = sorted(cands, key=lambda c: -c[1])
    seen = set()
    out = []
    for aid, score, text in cands:
        if aid in unresolved:
            out.append((aid, score, text))
        else:
            key = (hashlib.sha256(text.encode()).hexdigest(),
                   collapse_sig(aid, scope))
            if key in seen:
                continue
            seen.add(key)
            out.append((aid, score, text))
        if len(out) >= cap:
            break
    return out


def partition_key(aid, scope, unresolved):
    """Q12.1(c) MMR partition key for one candidate.

    The key is the candidate's S-02 qualifier value verbatim
    (collapse_sig over touching eligible relations). Atoms with
    no scope and unresolved-marked atoms (polarity-unassigned
    per Q12.3, no separate stream per amended Q12.2) return None:
    they share one unpartitioned pool. Pure.
    """
    if aid in unresolved:
        return None
    if not scope.get(aid):
        return None
    return collapse_sig(aid, scope)


def identify_pairs(view, universe):
    """Q12.3-mechanism identified counterpart atoms (R3-B ruling).

    view: RelView at the resolving pin (eligible-only).
    universe: emitted candidate atom ids (selection input; pairs
      with an un-emitted side are never identified).
    Returns sorted [(a, b)] with a < b per pair. A pair needs one
    affirmed touch (qualifiers.negated False-or-absent) and one
    negated touch in one opposition group keyed by (rel_type,
    context-endpoints = endpoint set minus the touched atom,
    canonical qualifiers-minus-negated); neither atom may carry
    an unresolved mark. Deterministic under any hash seed. Pure.
    """
    uni = set(universe)
    groups = {}  # key -> [affirmed {aid}, negated {aid}]
    pre = getattr(view, "_opp", None)  # index opposition material
    for rid in sorted(view.eligible):
        rec = view.eligible[rid]
        if pre is not None and rid in pre:
            rtype, ids, rest, neg = pre[rid]
        else:
            eps = rec.get("endpoints", [])
            ids = set(eps) if rec.get("interchangeable") \
                else {e[1] for e in eps}
            quals = rec.get("qualifiers", {}) or {}
            neg = bool(quals.get("negated", False))
            rest = canonical_json_bytes(
                {k: v for k, v in quals.items() if k != "negated"})
            rtype = rec.get("rel_type")
        mine = [a for a in ids if a in uni]
        if not mine:
            continue
        for aid in mine:
            key = (rtype, frozenset(ids - {aid}), rest)
            grp = groups.setdefault(key, [set(), set()])
            grp[1 if neg else 0].add(aid)
    out = set()
    for aff, ng in groups.values():
        for a in aff:
            if a in view.unresolved:
                continue
            for b in ng:
                if b in view.unresolved or a == b:
                    continue
                out.add((a, b) if a < b else (b, a))
    return sorted(out)


def _pool_rank(key):
    # Deterministic partition order: unpartitioned pool (None)
    # first, then qualifier-sig bytes ascending.
    return (key is not None, key if key is not None else ())


def partitioned_mmr(cands, sim, lam, scope, unresolved,
                    sim_cap=None, merge="score"):
    """Q12.1(c) intra-polarity MMR with score-ordered merge.

    cands: [(aid, score)] in pruned order. MMR runs independently
    within each partition_key group (same sim closure, lambda,
    and sim_cap the plain call would use); the per-partition
    orders merge by emitted-score heads (ties: partition key,
    then aid). One pool reproduces mmr_order_matrix exactly.
    Deterministic under any hash seed. Pure.

    merge="roundrobin" (round 9 track B, W12 bakeoff arm only) is
    the strict-interleave alternative: per-partition heads seat
    cyclically in partition order (unpartitioned pool first, then
    qualifier-sig bytes ascending). The default merge="score" is
    the settled rule, byte-identical to the pre-round-9 order.
    """
    if merge not in ("score", "roundrobin"):
        raise ValueError(f"merge must be score|roundrobin, got "
                         f"{merge!r}")
    groups = {}
    for aid, score in cands:
        groups.setdefault(
            partition_key(aid, scope, unresolved),
            []).append((aid, score))
    pkeys = sorted(groups, key=_pool_rank)
    orders = {k: mmr_order_matrix(groups[k], sim, lam,
                                  len(groups[k]),
                                  sim_cap=sim_cap)
              for k in pkeys}
    if merge == "roundrobin":
        merged = []
        pos = {k: 0 for k in pkeys}
        progressed = True
        while progressed:
            progressed = False
            for k in pkeys:
                i = pos[k]
                if i < len(orders[k]):
                    merged.append(orders[k][i])
                    pos[k] = i + 1
                    progressed = True
        return merged
    score_of = {a: s for a, s in cands}
    pos = {k: 0 for k in pkeys}
    merged = []
    total = sum(len(v) for v in orders.values())
    while len(merged) < total:
        best = None
        for k in pkeys:
            order = orders[k]
            idx = pos[k]
            if idx >= len(order):
                continue
            aid = order[idx]
            cand = (-score_of[aid], _pool_rank(k), aid)
            if best is None or cand < best[0]:
                best = (cand, k)
        merged.append(orders[best[1]][pos[best[1]]])
        pos[best[1]] += 1
    return merged


def make_qual_signal(aid, qualifiers, extractor_config,
                     status="proposed", claim_text=None):
    """Build (but do not commit) one ingested qualifier-signal record.

    The durable form is an ordinary S-02 relation record with
    rel_type QUAL_SIGNAL_TYPE, a single ("atom", aid) endpoint,
    and self-grounding [aid]; commit with commit_qual_signals and
    read back with qual_signals. The qualifiers dict is the
    judgment (negated/scope/condition/unresolved per S-02); it
    must be nonempty -- a signal with nothing to say is refused.
    aid/extractor/config validation is relations.make_record's
    (imported, not reimplemented).
    """
    if not isinstance(qualifiers, dict) or not qualifiers:
        raise ValueError("qual signal needs a nonempty "
                         "qualifiers dict")
    return _make_record(QUAL_SIGNAL_TYPE, [("atom", aid)],
                        dict(qualifiers), extractor_config,
                        status, [aid], claim_text=claim_text)


def commit_qual_signals(tlstore, signals, store_id="tl-sys-docs"):
    """Commit qualifier-signal records; returns [op_id]. Thin wrapper
    over relations.commit_relations (same op/ledger path, same
    disclosure leg, same raised errors), chunked to the owning
    committer's ten-operation cap."""
    out = []
    pending = list(signals)
    while pending:
        out.extend(_commit_relations(tlstore, pending[:10],
                                     store_id=store_id))
        pending = pending[10:]
    return out


def qual_signals(view):
    """Ingested per-atom qualifier signals at the view's pin.

    view: RelView (eligibility-gated at the resolving pin).
    Returns {aid: [(rid, qualifiers)]} over eligible records with
    rel_type QUAL_SIGNAL_TYPE, rids ascending per atom -- the same
    shape as RelView.scope values, so collapse_sig /
    partition_key consume ingested signals identically to
    query-time overlay scope. Pure (reads the view only).
    """
    out = {}
    for rid in sorted(view.eligible):
        rec = view.eligible[rid]
        if rec.get("rel_type") != QUAL_SIGNAL_TYPE:
            continue
        eps = rec.get("endpoints", [])
        ids = (list(eps) if rec.get("interchangeable")
               else [e[1] for e in eps])
        for aid in sorted(set(ids)):
            out.setdefault(aid, []).append(
                (rid, rec.get("qualifiers", {}) or {}))
    return out


def select_seeds(seeds, seed_scores=None, seed_budget=None):
    """Relevance-ranked seed-budget selection (TRAV experimental arm).

    Pure pre-pass for traverse(): narrows the seed SET to the top
    seed_budget anchors by relevance, deterministically. Ranking
    key is (-score, aid): score ties break by ascending atom id,
    so the output is identical under any input permutation or
    hash seed. Without scores the input order is kept (deduped,
    first-wins) and the head is taken.

    seed_budget None (default) returns list(seeds) unchanged: the
    traversal behaves exactly as before. A budget >= the seed
    count returns every seed (ranked when scored). Budget 0
    yields no seeds (traversal reaches nothing).

    Fail-closed: a negative/unparseable budget, an unscored seed,
    or a non-real/non-finite score raises ValueError (a silently
    misranked seed could evict evidence). Selection itself is
    uncounted pre-processing, like caller-side seed assembly.

    Status: section 5.8 item 3 arm, retained for the mandated 100M
    re-confirmation. It is NOT r2's repair: lane-TRAV evidence
    shows r2's traversal output is identical at every admission
    width (2/50 edges) and the pair is dropped at the dossier
    outer cap instead. No caller engages the budget yet.
    """
    if seed_budget is None:
        return list(seeds)
    n = int(seed_budget)
    if n < 0:
        raise ValueError(f"seed_budget must be >= 0, got "
                         f"{seed_budget!r}")
    uniq = list(dict.fromkeys(seeds))
    if seed_scores is None:
        return uniq[:n]
    missing = [a for a in uniq if a not in seed_scores]
    if missing:
        sample = ", ".join(str(a)[:16] for a in missing[:3])
        raise ValueError(
            f"{len(missing)} seed(s) lack scores "
            f"(e.g. {sample}): score every seed or drop it "
            f"explicitly")
    vals = {}
    for a in uniq:
        s = seed_scores[a]
        if isinstance(s, bool) or isinstance(s, (str, bytes)):
            raise ValueError(
                f"seed_scores[{str(a)[:16]}...] must be real, got "
                f"{s!r}")
        try:
            f = float(s)
        except (TypeError, ValueError):
            raise ValueError(
                f"seed_scores[{str(a)[:16]}...] must be real, got "
                f"{s!r}")
        if not math.isfinite(f):
            raise ValueError(
                f"seed_scores[{str(a)[:16]}...] must be finite, got "
                f"{s!r}")
        vals[a] = f
    return sorted(uniq, key=lambda a: (-vals[a], a))[:n]


def traverse(index, seeds, live, max_hops=1, max_edges=50,
             charge=None, visible=None, seed_scores=None,
             seed_budget=None):
    """Bounded Q4.1(b) relational traversal over the relation graph.

    Breadth-first expansion from seed anchors over RelIndex
    endpoint adjacency: hop-1 neighbours of the seeds, then
    neighbours of newly reached atoms, to max_hops. Every edge is
    eligibility-gated (relations.eligible flat-AND at the pin);
    ineligible edges are counted, never crossed. Each edge is
    examined at most once globally (unlike the dossier 1-hop
    lateral, which charges per source incidence); examination
    stops at max_edges. Q7.1: visited set, frontier, and counters
    live in per-call scratch; the index is read-only on this path
    (records are looked up, never mutated).

    index: RelIndex covering the resolving pin (its endpoint_adj
      and records are read; caller owns pin discipline).
    seeds: anchor atom ids (descent entries). live: atom ids live
      at the pin. charge: optional charge(n, opclass) callback
      (one "lateral-edge-inspection" per examined edge).
      visible: relation ids visible at the pin for eligibility
      (defaults to every record in the index).
    seed_scores/seed_budget: TRAV experimental arm (select_seeds):
      an optional relevance-ranked cap on the seed set,
      decoupled from admission. Both None (default) preserves
      the exact legacy behavior. Note the BFS sorts its
      frontier, so seed ORDER alone never matters; only the
      budgeted SET can change the outcome.
    Returns {"reached": {aid: {"hop": h, "via": [rid...],
      "rel_status": s, "rel_unresolved": m}}, "examined": n,
      "ineligible": k, "hops_used": h}. Seeds never appear in
      reached; "via" is ascending; all iteration is sorted
      (deterministic under any hash seed).
    """
    if int(max_hops) < 1:
        raise ValueError(f"max_hops must be >= 1, got {max_hops!r}")
    if int(max_edges) < 0:
        raise ValueError(f"max_edges must be >= 0, got "
                         f"{max_edges!r}")
    seeds = select_seeds(seeds, seed_scores, seed_budget)
    live = set(live)
    vis = (set(index.records) if visible is None
           else set(visible))
    adj = index.endpoint_adj
    rec_of = index.records
    frontier = sorted(set(seeds) & live)
    visited = set(frontier)
    reached = {}
    examined_rids = set()
    examined = inelig = hops_used = 0
    hop = 0
    done = False
    while frontier and hop < int(max_hops) and not done:
        hop += 1
        nxt = []
        for src in frontier:
            if done:
                break
            for rid in sorted({r for r, _ in adj.get(src, ())}):
                if rid in examined_rids:
                    continue
                if examined >= int(max_edges):
                    done = True
                    break
                examined_rids.add(rid)
                examined += 1
                if charge is not None:
                    charge(1, "lateral-edge-inspection")
                item = rec_of.get(rid)
                if item is None:
                    continue
                rec = item["record"]
                el = _eligible(rec, live, vis)
                if not el["eligible"]:
                    inelig += 1
                    continue
                eps = rec.get("endpoints", [])
                ep_ids = (list(eps) if rec.get("interchangeable")
                          else [e[1] for e in eps])
                for eid in sorted(set(ep_ids)):
                    if eid not in live:
                        continue
                    if eid in reached:
                        if reached[eid]["hop"] == hop \
                                and rid not in \
                                reached[eid]["via"]:
                            reached[eid]["via"].append(rid)
                        continue
                    if eid in visited:
                        continue  # seed anchors never re-enter
                    reached[eid] = {
                        "hop": hop, "via": [rid],
                        "rel_status": rec.get("status"),
                        "rel_unresolved": el.get("unresolved")}
                    visited.add(eid)
                    nxt.append(eid)
        if nxt:
            hops_used = hop
        frontier = sorted(set(nxt))
    for info in reached.values():
        info["via"] = sorted(set(info["via"]))
    return {"reached": reached, "examined": examined,
            "ineligible": inelig, "hops_used": hops_used}
