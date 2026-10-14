"""C2 Lane R: delta-aware relation serving over the ServingView facade.

P-Rel delta path (architecture v1.1 section 3.2/3.9, handoff section 4
Lane R): adjacency/bridge/qualifier access through the facade, tombstone-
aware eligibility, no direct NarrowIndex internals.

Reads relation bytes from the commit log (the only source: ServingViews
carry no relation structures) and liveness/retirement/pin discipline from
the facade only. The facade surface touched here is exactly:

  - ``is_live_atom(aid)`` (O(1) membership predicate; ``set(idx.atoms)``
    is never materialized),
  - ``retired_aids`` (tombstone set, diffed per advance),
  - ``triple`` (pin binding; a facade hop without a paired advance fails
    closed with StaleServeError instead of mixing generations).

Reference: ``tlsys.relquery`` (M1 RelView semantics) + ``tlsys.relations``
(flat-AND eligibility, opposition material). This module reuses the pure
consumers verbatim (``identify_pairs``, ``qual_signals``, ``apply_hub``,
``prune_rel``, ``partitioned_mmr``, ``collapse_sig``, ``partition_key`` run
unmodified over the served maps) and maintains the state they consume
incrementally:

  - ``open`` builds the full prefix once (O(R) records; R ~ 75 at 10M).
  - ``advance`` consumes only the (frontier, max_seq] relation window and
    re-evaluates eligibility only for: records with a winner in the window,
    records touching newly retired atoms, and currently ineligible records
    (which newly live atoms can only repair, never break -- see below).
    Degrees, scope and unresolved marks are maintained for touched atoms
    only. Per-query serving (incident/traverse/scope/identify) touches no
    atom population and materializes no live set.

Exactness argument for the advance re-evaluation set: between advances the
live set only grows except for retirements, and the visible relation set
only grows (records are superseded, never deleted). An eligible record can
therefore only flip via retirement of a referenced atom or via its own
supersession (both covered); an ineligible record can only flip via newly
live atoms or its own supersession (all ineligible records are re-checked,
bounded by R). Proven, not asserted: every advance test also diffs against
a fresh full-prefix build and against ``relquery.load``.

Counters go through Lane G's API (read-only import, never copied): one
``relation_work_units`` unit per record eligibility evaluation, per edge
examination, or per record admitted from a log read. Log/artifact bytes
for the relation window are observed by the F-cell store wrapper (out of
this lane's write area); this module reports units + a stats dict only.
"""

import bisect
import os

from tlsys.identity import canonical_json_bytes
from tlsys.relations import eligible as _eligible
from tlsys.relations import read_relations

RELATION_WORK_UNIT = "relation_work_units"


def _lane_g_counters():
    """Lane G Counters class via read-only import (no copy/fork).

    Raises ImportError when Lane G's counters.py is unavailable (same
    rule as serving's to_lane_g export).
    """
    from tlsys.serving.provisional import _load_lane_g_module
    mod = _load_lane_g_module("counters")
    if mod is None:
        raise ImportError(
            "lane-G counters.py unavailable; RelServe counts through "
            "the Lane G API only (see profile-counters.md section 3)")
    return mod.Counters


class StaleServeError(Exception):
    """The bound facade moved to another pin without a paired advance.

    Fail-closed mixed-generation containment (FI-7): serve methods raise
    this instead of answering with a liveness predicate from the wrong pin.
    Also raised for cross-generation/cross-store pins (FI-2).
    """


def _require_store_generation(tlstore, pinned):
    """Refuse pins outside the store's current generation line (FI-2)."""
    mine = tlstore.pin()
    if pinned[0] != mine[0] or pinned[1] != mine[1]:
        raise StaleServeError(
            f"pin {pinned[3]!r} is outside this store's generation "
            f"line ({mine[0]}:{mine[1]}): open a fresh serve, never mix")


def _ep_ids(rec):
    """Endpoint ids in record order (mirrors relquery._build_view)."""
    eps = rec.get("endpoints", [])
    if rec.get("interchangeable"):
        return list(eps)
    return [e[1] for e in eps]


def _ep_roles(rec):
    """[(endpoint-id, role)] in record order (mirrors RelIndex views)."""
    eps = rec.get("endpoints", [])
    if rec.get("interchangeable"):
        return [(e, None) for e in eps]
    return [(e[1], e[0]) for e in eps]


def _opp_of(rec):
    """Opposition material for one record (mirrors RelIndex._admit_views).

    Drift-checked by the differential battery (RelServe._opp equals the
    shared RelIndex opp on the same pin), not asserted here.
    """
    quals = rec.get("qualifiers", {}) or {}
    rest = canonical_json_bytes(
        {k: v for k, v in quals.items() if k != "negated"})
    return (rec.get("rel_type"),
            frozenset(e for e, _r in _ep_roles(rec)),
            rest, bool(quals.get("negated", False)))


def digest_rel_state(visible, eligible_map, degrees, scope, unresolved,
                     triple):
    """Order-independent hex digest of served relation state.

    Shared by RelServe.digest and the cross-implementation differential
    (same function over relquery RelView fields), so digest equality is a
    real parity claim, not a same-code tautology.
    """
    import hashlib
    import json
    scope_c = {a: sorted((r, json.dumps(q, sort_keys=True))
                         for r, q in lst)
               for a, lst in scope.items()}
    blob = json.dumps({
        "visible": sorted((r, v.get("seq"), v.get("op_id"))
                          if isinstance(v, dict) and "record" in v
                          else (r, None, None)
                          for r, v in visible.items()),
        "eligible": sorted(eligible_map),
        "degrees": sorted(degrees.items()),
        "scope": sorted(scope_c.items()),
        "unresolved": sorted(unresolved.items()),
        "triple": triple,
    }, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


class _LivePredicate:
    """``in``-only live view over the facade (never a materialized set).

    ``relations.eligible`` only uses ``in`` on its live argument, so this
    proxy yields identical booleans to ``set(idx.atoms)`` at O(1) per probe
    with zero population copies. Iteration/len are refused (fail-closed:
    no caller may accidentally pay O(N) through this object).
    """

    def __init__(self, index):
        self._index = index

    def __contains__(self, aid):
        pred = getattr(self._index, "is_live_atom", None)
        if pred is not None:
            return bool(pred(aid))
        return aid in self._index.atoms

    def __iter__(self):
        raise TypeError("_LivePredicate is probe-only (no O(N) scan)")

    def __len__(self):
        raise TypeError("_LivePredicate is probe-only (no O(N) scan)")


class RelServe:
    """Delta-aware relation view bound to one facade pin.

    Served maps (same shapes as relquery.RelView, shared read-only by
    contract): ``visible`` {rid: record}, ``eligible`` {rid: record},
    ``reasons`` {rid: [reason]} (ineligible only), ``degrees``
    {endpoint: degree} (eligible-only), ``scope`` {aid: [(rid,
    qualifiers)]} (raw order), ``unresolved`` {aid: mark} (first-mark-
    wins in raw order), ``_opp`` opposition material for identify_pairs.

    ``advance``/``open`` are the only mutators; concurrent mutation during
    a serve is caller error (single-threaded contract, same as the facade
    mappings' external-mutation rule).
    """

    def __init__(self, tlstore, index, pinned, _records):
        self._tl = tlstore
        self._index = index
        self._db = os.path.abspath(tlstore.store.db_path)
        self._birth, self._epoch = pinned[0], pinned[1]
        self._frontier = pinned[2]
        self._triple = pinned[3]
        Counters = _lane_g_counters()
        self.counters = Counters("relserve")
        from tlsys import relquery as _rq
        self.leg = _rq.DisclosureLeg.RELATIONS
        self._stats = {"records_admitted": 0, "eligibility_evals": 0,
                       "edge_exams": 0, "advances": 0, "rebuilds": 0,
                       "ineligible_rechecks": 0, "retired_flips": 0}
        # State (see _full_build).
        self.visible = {}
        self.eligible = {}
        self.reasons = {}
        self.degrees = {}
        self.scope = {}
        self.unresolved = {}
        self._opp = {}
        self._records = {}   # rid -> {seq, op_id, record}
        self._order = []     # rids in first-seen (ascending-seq) order
        self._pos = {}       # rid -> index in _order
        self._adj = {}       # eid -> sorted [(rid, role)] (all records)
        self._atom_rids = {}  # atom -> {rid} over endpoints+grounding
        self._atom_elig = {}  # aid -> sorted [(pos, rid)] eligible, endpoint
        self._atom_marks = {}  # aid -> sorted [(pos, rid, mark)] eligible
        self._visible_ids = frozenset()
        self._retired_seen = frozenset()
        self._live = _LivePredicate(index)
        self._full_build(_records)

    # -- construction --------------------------------------------
    @classmethod
    def open(cls, tlstore, index, pinned):
        """Build the full-prefix view at ``pinned`` (TLStore.pin() tuple).

        Requires the bound facade to already serve that pin
        (``index.triple == pinned[3]``) and the pin to belong to the
        bound store's current generation line; anything else fails
        closed (FI-2: a serve fuses log relations with facade liveness,
        so cross-generation or cross-store pins are refused, never
        mixed -- open a fresh serve instead).
        """
        if getattr(index, "triple", None) != pinned[3]:
            raise StaleServeError(
                f"facade at {getattr(index, 'triple', None)!r} does not "
                f"serve pin {pinned[3]!r}: advance the facade first")
        _require_store_generation(tlstore, pinned)
        raw = read_relations(tlstore, pinned)
        serve = cls(tlstore, index, pinned, raw)
        serve._retired_seen = frozenset(
            getattr(index, "retired_aids", ()) or ())
        return serve

    def _full_build(self, raw):
        for rid, item in raw.items():
            self._admit_new(rid, item)
        self._visible_ids = frozenset(self._records)
        self._eval_all(raw)

    def _admit_new(self, rid, item):
        """Admit a first-seen record (order + edges + opp + visible)."""
        rec = item["record"]
        self._records[rid] = {"seq": item["seq"],
                              "op_id": item["op_id"],
                              "record": rec}
        self._pos[rid] = len(self._order)
        self._order.append(rid)
        self.visible[rid] = rec
        self._opp[rid] = _opp_of(rec)
        for eid, role in _ep_roles(rec):
            lst = self._adj.setdefault(eid, [])
            if (rid, role) not in lst:
                lst.append((rid, role))
                lst.sort()
        for aid in set(_ep_ids(rec)) | set(rec.get("grounding", [])):
            self._atom_rids.setdefault(aid, set()).add(rid)
        self._stats["records_admitted"] += 1
        self.counters.inc(RELATION_WORK_UNIT, 1)

    def _eval_all(self, raw):
        for rid in self._order:
            rec = self._records[rid]["record"]
            self._eval_one(rid, rec, fresh=True)
        # Degrees/scope/unresolved from scratch (open path only).
        self.degrees = {}
        self._atom_elig = {}
        self._atom_marks = {}
        for rid in self._order:
            if rid not in self.eligible:
                continue
            self._insert_eligibility(rid, self.eligible[rid])
        for aid in self._atom_elig:
            self._rematerialize_atom(aid)

    def _eval_one(self, rid, rec, fresh=False):
        """Evaluate one record; update eligible/reasons; count the unit."""
        res = _eligible(rec, self._live, self._visible_ids)
        self._stats["eligibility_evals"] += 1
        self.counters.inc(RELATION_WORK_UNIT, 1)
        was = rid in self.eligible
        if res["eligible"]:
            self.eligible[rid] = rec
            self.reasons.pop(rid, None)
        else:
            self.eligible.pop(rid, None)
            self.reasons[rid] = res["reasons"]
        return was, (rid in self.eligible)

    # -- incremental maintenance -----------------------------------
    def _insert_eligibility(self, rid, rec):
        """Add an eligible record's endpoint contributions."""
        pos = self._pos[rid]
        for aid in set(_ep_ids(rec)):
            lst = self._atom_elig.setdefault(aid, [])
            if (pos, rid) not in lst:
                bisect.insort(lst, (pos, rid))
            self.degrees[aid] = self.degrees.get(aid, 0) + 1
        mark = rec.get("qualifiers", {}).get("unresolved")
        if mark is not None:
            for aid in set(_ep_ids(rec)):
                lst = self._atom_marks.setdefault(aid, [])
                if (pos, rid, mark) not in lst:
                    bisect.insort(lst, (pos, rid, mark))

    def _remove_eligibility(self, rid, rec):
        """Drop an eligible record's endpoint contributions."""
        pos = self._pos[rid]
        for aid in set(_ep_ids(rec)):
            lst = self._atom_elig.get(aid, [])
            if (pos, rid) in lst:
                lst.remove((pos, rid))
            if aid in self.degrees:
                if self.degrees[aid] <= 1:
                    del self.degrees[aid]
                else:
                    self.degrees[aid] -= 1
            mlst = self._atom_marks.get(aid, [])
            for entry in [e for e in mlst if e[1] == rid]:
                mlst.remove(entry)

    def _rematerialize_atom(self, aid):
        """Rebuild scope/unresolved entries for one atom (raw order)."""
        lst = self._atom_elig.get(aid, [])
        if lst:
            self.scope[aid] = [(rid, self.eligible[rid]["qualifiers"])
                               for _p, rid in lst]
        else:
            self.scope.pop(aid, None)
        mlst = self._atom_marks.get(aid, [])
        if mlst:
            self.unresolved[aid] = mlst[0][2]
        else:
            self.unresolved.pop(aid, None)

    def _reedge_changed(self, rid, old_rec, new_rec):
        """Move adj/atom_rids/eligibility membership across a supersede.

        Note: endpoints are relation-identity inputs, so a same-rid
        supersede cannot change them (endpoint moves below are
        defensive-only); grounding is NOT an identity input, so
        grounding-edge moves are the live path (tested).
        """
        old_eps = set(_ep_ids(old_rec))
        new_eps = set(_ep_ids(new_rec))
        old_roles = _ep_roles(old_rec)
        new_roles = _ep_roles(new_rec)
        for eid, role in old_roles:
            if (eid, role) not in new_roles:
                lst = self._adj.get(eid, [])
                if (rid, role) in lst:
                    lst.remove((rid, role))
        for eid, role in new_roles:
            if (eid, role) not in old_roles:
                lst = self._adj.setdefault(eid, [])
                if (rid, role) not in lst:
                    lst.append((rid, role))
                    lst.sort()
        old_atoms = old_eps | set(old_rec.get("grounding", []))
        new_atoms = new_eps | set(new_rec.get("grounding", []))
        for aid in old_atoms - new_atoms:
            s = self._atom_rids.get(aid)
            if s is not None:
                s.discard(rid)
        for aid in new_atoms - old_atoms:
            self._atom_rids.setdefault(aid, set()).add(rid)
        # Eligibility contributions follow the endpoint set (the record
        # is currently eligible or not; the re-eval below decides anew).
        if rid in self.eligible:
            for aid in old_eps - new_eps:
                self._remove_endpoint(rid, aid)
            for aid in new_eps - old_eps:
                self._add_endpoint(rid, aid)

    def _remove_endpoint(self, rid, aid):
        pos = self._pos[rid]
        lst = self._atom_elig.get(aid, [])
        if (pos, rid) in lst:
            lst.remove((pos, rid))
        if aid in self.degrees:
            if self.degrees[aid] <= 1:
                del self.degrees[aid]
            else:
                self.degrees[aid] -= 1
        mlst = self._atom_marks.get(aid, [])
        for entry in [e for e in mlst if e[1] == rid]:
            mlst.remove(entry)

    def _add_endpoint(self, rid, aid):
        pos = self._pos[rid]
        lst = self._atom_elig.setdefault(aid, [])
        if (pos, rid) not in lst:
            bisect.insort(lst, (pos, rid))
        self.degrees[aid] = self.degrees.get(aid, 0) + 1
        mark = self.eligible[rid].get("qualifiers", {}).get("unresolved")
        if mark is not None:
            mlst = self._atom_marks.setdefault(aid, [])
            if (pos, rid, mark) not in mlst:
                bisect.insort(mlst, (pos, rid, mark))

    # -- advance ---------------------------------------------------
    def covers(self, pinned):
        """True iff this serve answers exactly ``pinned``."""
        return (pinned[0] == self._birth and pinned[1] == self._epoch
                and pinned[2] == self._frontier
                and pinned[3] == self._triple)

    def _require_fresh(self):
        if getattr(self._index, "triple", None) != self._triple:
            raise StaleServeError(
                f"bound facade moved to "
                f"{getattr(self._index, 'triple', None)!r}; serve is "
                f"pinned at {self._triple!r}: pair advance calls")

    def advance(self, index, pinned):
        """Serve ``pinned`` (TLStore.pin() tuple), incrementally or fresh.

        The (possibly hopped) facade must already serve that pin. A
        forward same-generation pin consumes only the (frontier, max_seq]
        relation window; a backward same-generation pin rebuilds from
        scratch (rewind-safe); a pin from another generation line or
        another store is refused (FI-2: never mixed, never silently
        emptied -- open a fresh serve instead). Returns self.
        """
        if getattr(index, "triple", None) != pinned[3]:
            raise StaleServeError(
                f"facade at {getattr(index, 'triple', None)!r} does not "
                f"serve pin {pinned[3]!r}: advance the facade first")
        _require_store_generation(self._tl, pinned)
        db = os.path.abspath(self._tl.store.db_path)
        forward = (db == self._db and pinned[0] == self._birth
                   and pinned[1] == self._epoch
                   and pinned[2] >= self._frontier)
        self._index = index
        self._live = _LivePredicate(index)
        if not forward:
            raw = read_relations(self._tl, pinned)
            self._birth, self._epoch = pinned[0], pinned[1]
            self._frontier = pinned[2]
            self._triple = pinned[3]
            self._db = db
            self.visible = {}
            self.eligible = {}
            self.reasons = {}
            self.degrees = {}
            self.scope = {}
            self.unresolved = {}
            self._opp = {}
            self._records = {}
            self._order = []
            self._pos = {}
            self._adj = {}
            self._atom_rids = {}
            self._atom_elig = {}
            self._atom_marks = {}
            self._full_build(raw)
            self._retired_seen = frozenset(
                getattr(index, "retired_aids", ()) or ())
            self._stats["rebuilds"] += 1
            self._stats["advances"] += 1
            return self
        won = read_relations(self._tl, pinned, min_seq=self._frontier)
        changed = []
        for rid, item in won.items():
            if rid in self._records:
                old_rec = self._records[rid]["record"]
                new_rec = item["record"]
                self._records[rid] = {"seq": item["seq"],
                                      "op_id": item["op_id"],
                                      "record": new_rec}
                self.visible[rid] = new_rec
                self._opp[rid] = _opp_of(new_rec)
                if rid in self.eligible:
                    # Content follows the winner now (eligibility itself
                    # is re-decided below); endpoint moves below read
                    # the new qualifiers for mark maintenance.
                    self.eligible[rid] = new_rec
                self._reedge_changed(rid, old_rec, new_rec)
                changed.append(rid)
                self._stats["records_admitted"] += 1
                self.counters.inc(RELATION_WORK_UNIT, 1)
            else:
                self._admit_new(rid, item)
                changed.append(rid)
        self._frontier = pinned[2]
        self._triple = pinned[3]
        self._visible_ids = frozenset(self._records)
        retired_now = frozenset(
            getattr(index, "retired_aids", ()) or ())
        retired_new = retired_now - self._retired_seen
        self._retired_seen = retired_now
        reeval = set(changed)
        for aid in retired_new:
            reeval.update(self._atom_rids.get(aid, ()))
        inelig = [r for r in self._order if r not in self.eligible
                  and r not in reeval]
        self._stats["ineligible_rechecks"] += len(inelig)
        reeval.update(inelig)
        touched = set()
        for rid in changed:
            rec = self._records[rid]["record"]
            touched.update(set(_ep_ids(rec)))
        for rid in sorted(reeval):
            rec = self._records[rid]["record"]
            touched.update(set(_ep_ids(rec)))
            was, is_now = self._eval_one(rid, rec)
            if was and not is_now:
                self._remove_eligibility(rid, rec)
                self._stats["retired_flips"] += 1
            elif is_now and not was:
                self._insert_eligibility(rid, rec)
        for aid in touched:
            self._rematerialize_atom(aid)
        self._stats["advances"] += 1
        return self

    # -- adjacency / bridge / qualifier access (through the facade) --
    def incident(self, src):
        """Sorted incident relation ids for one atom (bridge primitive).

        Same order as dossier._incident_rids over indexed adjacency: one
        entry per incident record (a record listing src twice contributes
        once). Counts one unit per incident record scanned.
        """
        self._require_fresh()
        out = sorted({r for r, _ in self._adj.get(src, ())})
        self._stats["edge_exams"] += len(out)
        self.counters.inc(RELATION_WORK_UNIT, len(out))
        return out

    def traverse(self, seeds, max_hops=1, max_edges=50, charge=None,
                 visible=None, seed_scores=None, seed_budget=None):
        """Bounded Q4.1(b) relational traversal (relquery.traverse parity).

        Identical semantics, pruning, counting, charge order and output
        shape to relquery.traverse over the shared RelIndex; the live set
        is the facade predicate (no set materialization). Counts one unit
        per edge examination plus one per eligibility evaluation.
        seed_scores/seed_budget: TRAV experimental arm, delegated to
        relquery.select_seeds (zero duplication, same fail-closed
        rules); both None (default) preserves the exact legacy
        behavior. Selection itself is uncounted pre-processing.
        """
        if int(max_hops) < 1:
            raise ValueError(f"max_hops must be >= 1, got {max_hops!r}")
        if int(max_edges) < 0:
            raise ValueError(f"max_edges must be >= 0, got "
                             f"{max_edges!r}")
        self._require_fresh()
        from tlsys import relquery as _rq
        seeds = _rq.select_seeds(seeds, seed_scores, seed_budget)
        live = self._live
        vis = (set(self._records) if visible is None
               else set(visible))
        adj = self._adj
        frontier = sorted(s for s in set(seeds) if s in live)
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
                    self._stats["edge_exams"] += 1
                    self.counters.inc(RELATION_WORK_UNIT, 1)
                    if charge is not None:
                        charge(1, "lateral-edge-inspection")
                    item = self._records.get(rid)
                    if item is None:
                        continue
                    rec = item["record"]
                    el = _eligible(rec, live, vis)
                    self._stats["eligibility_evals"] += 1
                    self.counters.inc(RELATION_WORK_UNIT, 1)
                    if not el["eligible"]:
                        inelig += 1
                        continue
                    ep_ids = _ep_ids(rec)
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

    def scope_for(self, aid):
        """[(rid, qualifiers)] touching one atom (raw order; keyed)."""
        self._require_fresh()
        return list(self.scope.get(aid, ()))

    def degrees_for(self, aids):
        """{aid: degree} over eligible records (keyed; absent means 0)."""
        self._require_fresh()
        return {a: self.degrees[a] for a in aids if a in self.degrees}

    def qual_signals(self):
        """Ingested per-atom qualifier signals (relquery parity).

        Delegates to relquery.qual_signals over the served maps (zero
        duplication); counts one unit per eligible record scanned (an
        R-bounded named term, not an N term).
        """
        from tlsys import relquery as _rq
        self._require_fresh()
        out = _rq.qual_signals(self)
        self.counters.inc(RELATION_WORK_UNIT, len(self.eligible))
        return out

    def identify_pairs(self, universe):
        """Q12.3-mechanism counterpart pairs (relquery parity).

        Delegates to relquery.identify_pairs over the served maps (zero
        duplication); counts one unit per eligible record scanned (an
        R-bounded named term, not an N term).
        """
        from tlsys import relquery as _rq
        self._require_fresh()
        out = _rq.identify_pairs(self, universe)
        self.counters.inc(RELATION_WORK_UNIT, len(self.eligible))
        return out

    # -- receipts --------------------------------------------------
    def digest(self):
        """Order-independent hex digest of the served state (I-counts).

        O(R) receipt work; counted (+R units), like any other scan.
        """
        self._require_fresh()
        self.counters.inc(RELATION_WORK_UNIT, len(self._records))
        return digest_rel_state(
            {r: self._records[r] for r in self._records},
            self.eligible, self.degrees, self.scope, self.unresolved,
            self._triple)

    def counts(self):
        """I-counts: visible/eligible/ineligible + pin binding."""
        self._require_fresh()
        return {"visible": len(self.visible),
                "eligible": len(self.eligible),
                "ineligible": len(self.reasons),
                "pin": self._triple,
                "frontier": self._frontier}

    def stats(self):
        """Work stats (units decompose; counters stay Lane-G-only)."""
        return dict(self._stats)

    def counters_snapshot(self):
        """Lane-G Counters snapshot for F-cell merge (disjoint scope)."""
        return self.counters.snapshot()
