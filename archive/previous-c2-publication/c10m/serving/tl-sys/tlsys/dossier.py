"""Relational (Q4.1 shape (b)) + cross-topic dossier (Q4.1 shape (c))
retrieval over the Narrow path.

Q4.1(b): relational traversal -> descend to seed anchors, then
bounded lateral over explicit S-02 relation records (single
anchor = the query text; the `topics` argument is ignored).
Q4.1(c): cross-topic dossier -> multi-region descent with
batch-5-bounded lateral. Q5.1: spreading only for shapes (b)/(c);
the Narrow baseline runs first, so spreading is always additive
evidence. Q5.2: H/R/E/C/P/T recorded per run ([E]-provisional
under the bakeoff amendment); work budget + entry/edge/topic
caps enforced cooperatively (Q13.2), exhaustion disclosed as
bounded-incomplete with a partials inventory (Q13.2(d)/Q14.1).

Additive-first: this module is NEW. NarrowQuery is untouched and
remains the default: DOSSIER_SHAPE="narrow" (default) delegates
exactly to NarrowQuery.run, so Narrow defaults are byte-identical.
Cross-topic mode reuses query.py machinery (seeding, support
labels, disclosure precedence, bounded-incomplete receipt) and
fuse/relations helpers; it adds no new emission rule.

Preservation posture (batch 12; atoms carry no qualifier
signals -- named S-02-ingestion input):
  - cross-topic dedupe is exact-text-duplicate collapse only
    (fuse.static_prune semantics); content-plus-polarity collapse
    is impossible without signals, never silent weakening;
  - relation "unresolved" qualifier marks ride onto lateral
    entries (Q12.2: mark carried to batch 15 rendering);
  - identified qualifier-explicit pairs: none identifiable, so the
    admit() joint-preservation branch is settled-but-empty, same
    as Narrow -- not dead code;
  - conflicting evidence: both sides presented in per-topic
    sections; no voting (batch-12 refusal).

Lateral (bounded spreading): 1-hop over explicit S-02 relation
records only (Q4.1: hints authorize none; no hints consulted).
Each traversed edge charges "lateral-edge-inspection" and is
capped by DOSSIER_MAX_EDGES; H is fixed at 1 (recorded, no
bakeoff value adopted). Lateral entries are marked
(selection "lateral-additive", via_relation, verbatim
rel_status) with union seed-support labels, so TRACE can tell
seed-emitted from relation-reached evidence.

Round-9 track B adds the Q4.1(b) relational traversal behind
DOSSIER_REL_TRAVERSAL (default off): same seed anchors, but the
relational shape routes THROUGH the graph via
relquery.traverse (bounded multi-hop BFS over RelIndex
adjacency, DOSSIER_REL_HOPS, eligibility-gated, one
examination per edge globally). Flag-off runs execute the
pre-round-9 _lateral path untouched (byte-identical receipts).
DOSSIER_MAX_HOPS stays fixed at 1 for that path; no multi-hop
default value is adopted (explicit opt-in only).
"""

import os

from tlsys import query as _q
from tlsys import relquery as _relquery
from tlsys.fuse import admit  # noqa: F401 (re-exported: joint-preservation input point)
from tlsys.query import WorkBudget
from tlsys.relations import eligible, get_index, read_relations
from tlsys.relserve import StaleServeError as _StaleServeError

DOSSIER_SHAPE = "narrow"  # "narrow" (default) | "relational" | "cross-topic"
DOSSIER_MAX_TOPICS = 8  # [E] dossier topic fanout cap
DOSSIER_MAX_ENTRIES = 20  # [E] dossier-level C cap (final entries)
DOSSIER_MAX_EDGES = 50  # [E] lateral edge-inspection cap (E dim)
DOSSIER_MAX_HOPS = 1  # fixed: 1-hop lateral only (recorded H)
DOSSIER_LATERAL = True  # bounded lateral on in cross-topic mode
DOSSIER_WORK_BUDGET = _q.WORK_BUDGET  # shared across topics
DOSSIER_REL_TRAVERSAL = False  # Q4.1(b) graph traversal (R9B, off)
DOSSIER_REL_HOPS = 1  # traversal hop bound (explicit opt-in only)
# R-2 production wiring (Lane R-2; default ON): the lateral and
# traversal legs serve via the shared RelServe (incident/traverse
# over the facade predicate) instead of read_relations +
# set(idx.atoms) + RelIndex adjacency. Exact parity (entry
# differentials in test_c2_entry_guards_r2.py); the env/cfg
# precedence is query._relserve_wired's.
RELSERVE_WIRED = True

_CFG_KEYS = ("DOSSIER_SHAPE", "DOSSIER_MAX_TOPICS",
             "DOSSIER_MAX_ENTRIES", "DOSSIER_MAX_EDGES",
             "DOSSIER_MAX_HOPS", "DOSSIER_LATERAL",
             "DOSSIER_WORK_BUDGET", "DOSSIER_REL_TRAVERSAL",
             "DOSSIER_REL_HOPS", "NARROW", "RELSERVE_WIRED")


def _incident_rids(rels, adj, src):
    """Incident relation ids for `src` in ascending order.

    Indexed adjacency (round 8 track A) at O(touches); adj=None takes
    the pre-index sorted(rels) + membership scan (TL_REL_ORACLE mode,
    exact old behavior for differential conformance). Both visit each
    incident rid exactly once per source in the same order (dedupe: one
    record may list src twice under two roles), so examined /
    ineligible counts and charge order are identical.
    """
    if adj is None:
        out = []
        for rid in sorted(rels):
            rec = rels[rid]["record"]
            eps = rec.get("endpoints", [])
            ep_ids = (list(eps) if rec.get("interchangeable")
                      else [e[1] for e in eps])
            if src in ep_ids:
                out.append(rid)
        return out
    return sorted({r for r, _ in adj.get(src, ())})


class DossierQuery:
    def __init__(self, tlstore, index, embed_query, cfg=None):
        self.tl = tlstore
        self.idx = index
        self.embed_query = embed_query
        c = dict(cfg or {})
        for k in c:
            if k not in _CFG_KEYS:
                raise ValueError(f"unknown dossier cfg key: {k}")
        if c.get("DOSSIER_SHAPE", DOSSIER_SHAPE) not in (
                "narrow", "relational", "cross-topic"):
            raise ValueError(
                "DOSSIER_SHAPE must be narrow|relational|cross-topic")
        if int(c.get("DOSSIER_MAX_HOPS", DOSSIER_MAX_HOPS)) != 1:
            raise ValueError("DOSSIER_MAX_HOPS is fixed at 1 "
                             "(no multi-hop value adopted)")
        trav = bool(c.get("DOSSIER_REL_TRAVERSAL",
                          DOSSIER_REL_TRAVERSAL))
        hops = int(c.get("DOSSIER_REL_HOPS", DOSSIER_REL_HOPS))
        if hops < 1:
            raise ValueError("DOSSIER_REL_HOPS must be >= 1, got "
                             f"{hops!r}")
        if not trav and hops != 1:
            raise ValueError("DOSSIER_REL_HOPS != 1 requires "
                             "DOSSIER_REL_TRAVERSAL=True "
                             "(no silent hop change)")
        self.cfg = c
        self.nq = _q.NarrowQuery(tlstore, index, embed_query,
                                 cfg=dict(c.get("NARROW") or {}))
        # R-2: wired-backend evidence (additive attribute, never in
        # receipts): which relation backend served the last
        # dossier-level lateral/traversal leg ("relserve",
        # "relquery", or None when no such leg ran; the narrow
        # shape mirrors the delegated NarrowQuery's tag).
        self.last_rel_backend = None

    def _C(self, name, default):
        return self.cfg.get(name, default)

    def run(self, query, topics=None, unpruned_reference=False):
        """Narrow shape: exact NarrowQuery.run delegation (identical
        objects). Relational: single-anchor Narrow descent (the
        query text; `topics` ignored) + bounded 1-hop lateral.
        Cross-topic: multi-topic descent + bounded lateral
        assembly. Returns (dossier, receipt)."""
        import time
        shape = self._C("DOSSIER_SHAPE", DOSSIER_SHAPE)
        if shape == "narrow":
            out = self.nq.run(
                query, unpruned_reference=unpruned_reference)
            self.last_rel_backend = self.nq.last_rel_backend
            return out
        t0 = time.time()
        tl, idx = self.tl, self.idx
        pin = tl.pin()
        _birth, _epoch, _mx, triple = pin
        if triple != idx.triple:
            raise ValueError(
                "index built at %s, store pinned at %s: rebuild "
                "index (no cross-generation mixing)"
                % (idx.triple, triple))
        budget = WorkBudget(
            cap=self._C("DOSSIER_WORK_BUDGET", DOSSIER_WORK_BUDGET))
        events = []
        if shape == "relational":
            ask = [query]  # Q4.1(b): single anchor, topics ignored
        else:
            ask = [query] if not topics else list(topics)
        max_topics = int(self._C("DOSSIER_MAX_TOPICS",
                                 DOSSIER_MAX_TOPICS))
        ran, deferred_topics = ask[:max_topics], ask[max_topics:]
        partials = [{"scope": f"topic:{t[:32]}",
                     "cause": "dossier-topic-cap"}
                    for t in deferred_topics]
        entries, seen = [], set()
        sections = []
        r_total = c_cand = prune_total = 0
        top1_any = uncertain_any = False
        incomplete = None
        per_topic_support = []  # (lex_set, dense_set, dense_w) per topic
        for topic in ran:
            if not budget.ok():
                incomplete = budget.exhaustion or "unknown"
                partials.insert(0, {"scope": "query",
                                    "cause": incomplete})
                break
            budget.charge(1, "dossier-topic-fanout")
            dos_t, rec_t = self.nq._run_inner(
                topic, pin, budget, events, t0, unpruned_reference)
            if rec_t["execution"]["status"] == "bounded-incomplete":
                incomplete = rec_t["execution"]["reason"]
            m = rec_t["metrics"]
            r_total += m.get("R_regions", 0)
            c_cand += m.get("C_candidates", 0)
            prune_total += m.get("prune_survivors", 0)
            top1_any = top1_any or bool(
                m.get("top1_trigger_fired", False))
            uncertain_any = uncertain_any or bool(rec_t["flags"].get(
                "routing_uncertain_Q3.3", False))
            # Support counts recount from SERVED entries after
            # merge/lateral/cap (per-topic counts double-count
            # deduped atoms); see the recount below.
            partials.extend(rec_t.get("partials", []))
            sec_ids = []
            for e in dos_t["entries"]:
                if e["atom_id"] in seen:
                    continue  # exact atom-id dedupe, first-wins
                seen.add(e["atom_id"])
                e = dict(e, dossier_topic=topic[:64])
                entries.append(e)
                sec_ids.append(e["atom_id"])
            sections.append({"topic": topic[:64], "entry_ids": sec_ids,
                             "support_findings": rec_t[
                                 "support_findings"]})
            per_topic_support.append(self._topic_seeds(topic))
            if incomplete is not None:
                break
        # -- bounded lateral (Q4.1(c) + Q5.1; additive only) --------
        # Q4.1(b) with DOSSIER_REL_TRAVERSAL routes THROUGH the
        # graph instead (relquery.traverse, hops-bounded BFS).
        trav_on = (shape == "relational" and bool(
            self._C("DOSSIER_REL_TRAVERSAL", DOSSIER_REL_TRAVERSAL)))
        lat_added = edges_examined = hops_used = 0
        lat_inelig = 0
        if (bool(self._C("DOSSIER_LATERAL", DOSSIER_LATERAL))
                and incomplete is None and budget.ok()):
            _lat = (self._traverse_lateral if trav_on
                    else self._lateral)
            lat_added, edges_examined, hops_used, lat_inelig = \
                _lat(pin, triple, budget, entries, seen,
                     partials, per_topic_support,
                     uncertain_any)
        # -- dossier-level C cap (Q12.3-overflow precedent: -------
        # cap-splits explicit, never silent) -----------------------
        # Lateral seat protection (C2 seating repair): lateral
        # entries are additive evidence unreachable by descent, so
        # over-cap assembly reserves them seats up to the
        # traversal receipt count against inner-width pressure.
        # Generic across shapes/legs/cases (no per-case rules, cap
        # value unchanged): the served set is the inner head plus
        # the lateral block in pre-cap order; the displaced inner
        # tail and any unseated lateral spill to explicit
        # dossier-cap-overflow partials. Total<=cap or zero-lateral
        # runs seat exactly as before (inner-head-first).
        max_entries = int(self._C("DOSSIER_MAX_ENTRIES",
                                  DOSSIER_MAX_ENTRIES))
        if len(entries) > max_entries:
            lateral = [e for e in entries
                       if e["marks"].get("lateral")]
            if lateral and max_entries > 0:
                n_lat = min(len(lateral), max_entries)
                inner = [e for e in entries
                         if not e["marks"].get("lateral")]
                inner_head = inner[:max_entries - n_lat]
                seated = lateral[:n_lat]
                seated_ids = {e["atom_id"]
                              for e in inner_head + seated}
                overflow = [e for e in entries
                            if e["atom_id"] not in seated_ids]
                entries = inner_head + seated
            else:
                overflow = entries[max_entries:]
                entries = entries[:max_entries]
        else:
            overflow = []
        for e in overflow:
            partials.append({"scope": f"candidate:{e['atom_id'][:16]}",
                             "cause": "dossier-cap-overflow"})
        # Honest counts: recount over served entries only, so the
        # receipt's support_counts always sums to len(entries).
        counts = {"lex_only": 0, "dense_only": 0,
                  "both": 0, "neither": 0}
        for e in entries:
            counts[e["support"].replace("-", "_")] += 1
        ms = (time.time() - t0) * 1000.0
        receipt = self._receipt(query, ran, deferred_topics, pin,
                                budget, events, ms, entries,
                                sections, partials, counts,
                                r_total, c_cand, prune_total,
                                top1_any, uncertain_any, incomplete,
                                lat_added, edges_examined, hops_used,
                                lat_inelig, unpruned_reference, shape,
                                trav_on)
        return {"entries": entries, "sections": sections}, receipt

    def _topic_seeds(self, topic):
        """Per-topic seed sets for union support labels (same cuts
        the Narrow path uses; charged to the dossier budget by the
        caller context -- see run()). Returns (lex_set, dense_set,
        dense_w, emit_on)."""
        nq, idx = self.nq, self.idx
        qvec = self.embed_query(topic)
        lex = idx.bm25(topic)
        lex_set = {a for a, _s in sorted(
            lex.items(), key=lambda kv: -kv[1])[
            :nq._C("SEED_LEX", _q.SEED_LEX)]}
        emit_on = bool(nq._C("EMIT_DENSE_ATOMS",
                             _q.EMIT_DENSE_ATOMS))
        dense_set = set()
        if emit_on:
            dense_set = {a for a, _s in idx.dense_atoms(qvec)[
                :nq._C("SEED_DENSE_ATOMS", _q.SEED_DENSE_ATOMS)]}
        return (lex_set, dense_set,
                float(nq._C("DENSE_WEIGHT", _q.DENSE_WEIGHT)),
                emit_on)

    def _union_support(self, aid, per_topic_support):
        """Union seed-support label across dossier topics: has_lex /
        has_dense iff seeded by ANY topic (same 4-label scheme as
        Narrow; lateral entries keep this plus lateral marks)."""
        has_lex = any(aid in lex for lex, _d, _w, _e
                      in per_topic_support)
        has_dense = any(aid in dense for _l, dense, _w, e
                        in per_topic_support if e)
        return ("both" if has_lex and has_dense else
                "lex-only" if has_lex else
                "dense-only" if has_dense else "neither")

    def _rel_serve_or_none(self, pin):
        """RelServe covering `pin` shared with the Narrow legs, or
        None when the legacy path owns this call (wiring disabled,
        oracle/audit mode, or a holder without the facade predicate;
        ImportError/StaleServeError also fall back, recorded)."""
        cfg = dict(self.cfg)
        cfg.setdefault("RELSERVE_WIRED", RELSERVE_WIRED)
        if not _q._relserve_wired(cfg):
            return None
        if not hasattr(self.idx, "is_live_atom"):
            return None
        try:
            return _q._rel_serve_for(self.tl, self.idx, pin)
        except ImportError:
            return None  # Lane G counters unavailable: legacy path
        except _StaleServeError:
            return None  # facade/pin mismatch: legacy path

    def _lateral(self, pin, triple, budget, entries, seen,
                 partials, per_topic_support, uncertain):
        serve = self._rel_serve_or_none(pin)
        if serve is not None:
            return self._lateral_served(
                serve, pin, triple, budget, entries, seen,
                partials, per_topic_support, uncertain)
        _birth, _epoch, _mx = pin[0], pin[1], pin[2]
        max_edges = int(self._C("DOSSIER_MAX_EDGES",
                                DOSSIER_MAX_EDGES))
        rels = read_relations(self.tl, pin)
        live = set(self.idx.atoms)
        vis = set(rels)
        oracle = os.environ.get("TL_REL_ORACLE") == "1"
        adj = None if oracle else get_index(self.tl, pin).endpoint_adj
        examined = added = hops = inelig = 0
        sources = [e["atom_id"] for e in entries]
        done = False
        for src in sources:
            if done or not budget.ok():
                break
            for rid in _incident_rids(rels, adj, src):
                if examined >= max_edges:
                    done = True
                    break
                if not budget.ok():
                    break
                rec = rels[rid]["record"]
                eps = rec.get("endpoints", [])
                ep_ids = (list(eps) if rec.get("interchangeable")
                          else [e[1] for e in eps])
                examined += 1
                budget.charge(1, "lateral-edge-inspection")
                el = eligible(rec, live, vis)
                if not el["eligible"]:
                    inelig += 1
                    continue
                for eid in sorted(set(ep_ids) - {src}):
                    if eid in seen or eid not in live:
                        continue  # atoms only; 1-hop; dedupe
                    a = self.idx.atoms[eid]
                    try:
                        body = self.tl.read_artifact(
                            a["text_art"],
                            expect_digest=a["text_digest"])
                        integrity = "intact-verified"
                    except (ValueError, OSError):
                        partials.append({
                            "scope": f"candidate:{eid[:16]}",
                            "cause": "integrity-failed:withheld"})
                        continue  # Q15.2b: never served
                    budget.charge(1, "assembly-read")
                    support = self._union_support(
                        eid, per_topic_support)
                    seen.add(eid)
                    entries.append({
                        "atom_id": eid,
                        "issuing_generation":
                            f"{_birth}:{_epoch}:{a['seq']}",
                        "resolving_generation": triple,
                        "text": body.decode("utf-8"),
                        "span": a["span"], "doc_id": a["doc_id"],
                        "emitted_score": 0.0,
                        "support": support,
                        "verdicts": {
                            "integrity": integrity,
                            "selection": "lateral-additive"},
                        "marks": {"routing_uncertain": uncertain,
                                  "outlier": False,
                                  "resolution": "live",
                                  "lateral": True,
                                  "via_relation": rid,
                                  "rel_status": rec.get("status"),
                                  "rel_unresolved": el.get(
                                      "unresolved")},
                        "dossier_topic": None})
                    added += 1
                    hops = 1
        self.last_rel_backend = "relquery"
        return added, examined, hops, inelig

    def _lateral_served(self, serve, pin, triple, budget, entries,
                        seen, partials, per_topic_support,
                        uncertain):
        """Wired 1-hop lateral over RelServe (R-2).

        Identical entries, counts, budget charges and marks to
        _lateral: incident rids via serve.incident (same ascending
        order as _incident_rids over indexed adjacency),
        eligibility via the serve's gated map, liveness via the O(1)
        facade probe (no set(idx.atoms), no read_relations /
        get_index / eligible call on this module).
        """
        _birth, _epoch, _mx = pin[0], pin[1], pin[2]
        max_edges = int(self._C("DOSSIER_MAX_EDGES",
                                DOSSIER_MAX_EDGES))
        is_live = self.idx.is_live_atom
        examined = added = hops = inelig = 0
        sources = [e["atom_id"] for e in entries]
        done = False
        for src in sources:
            if done or not budget.ok():
                break
            for rid in serve.incident(src):
                if examined >= max_edges:
                    done = True
                    break
                if not budget.ok():
                    break
                rec = serve.visible[rid]
                eps = rec.get("endpoints", [])
                ep_ids = (list(eps) if rec.get("interchangeable")
                          else [e[1] for e in eps])
                examined += 1
                budget.charge(1, "lateral-edge-inspection")
                if rid not in serve.eligible:
                    inelig += 1
                    continue
                for eid in sorted(set(ep_ids) - {src}):
                    if eid in seen or not is_live(eid):
                        continue  # atoms only; 1-hop; dedupe
                    a = self.idx.atoms[eid]
                    try:
                        body = self.tl.read_artifact(
                            a["text_art"],
                            expect_digest=a["text_digest"])
                        integrity = "intact-verified"
                    except (ValueError, OSError):
                        partials.append({
                            "scope": f"candidate:{eid[:16]}",
                            "cause": "integrity-failed:withheld"})
                        continue  # Q15.2b: never served
                    budget.charge(1, "assembly-read")
                    support = self._union_support(
                        eid, per_topic_support)
                    seen.add(eid)
                    entries.append({
                        "atom_id": eid,
                        "issuing_generation":
                            f"{_birth}:{_epoch}:{a['seq']}",
                        "resolving_generation": triple,
                        "text": body.decode("utf-8"),
                        "span": a["span"], "doc_id": a["doc_id"],
                        "emitted_score": 0.0,
                        "support": support,
                        "verdicts": {
                            "integrity": integrity,
                            "selection": "lateral-additive"},
                        "marks": {"routing_uncertain": uncertain,
                                  "outlier": False,
                                  "resolution": "live",
                                  "lateral": True,
                                  "via_relation": rid,
                                  "rel_status": rec.get("status"),
                                  "rel_unresolved": rec.get(
                                      "qualifiers", {}).get(
                                      "unresolved")},
                        "dossier_topic": None})
                    added += 1
                    hops = 1
        self.last_rel_backend = "relserve"
        return added, examined, hops, inelig

    def _traverse_lateral(self, pin, triple, budget, entries, seen,
                          partials, per_topic_support, uncertain):
        """Q4.1(b) relational traversal (round 9 track B): route
        THROUGH the graph from the seed entries via
        relquery.traverse (hops-bounded BFS over RelIndex
        adjacency, DOSSIER_REL_HOPS). Reached atoms emit as
        lateral-additive entries with hop/via marks
        (emitted_score 0.0: routing is never support). Each edge
        is examined once globally; examination stops at
        DOSSIER_MAX_EDGES. Index-native: no TL_REL_ORACLE legacy
        loop exists for this path (nothing pre-index to conform
        to). Same (added, examined, hops, ineligible) shape as
        _lateral."""
        serve = self._rel_serve_or_none(pin)
        if serve is not None:
            return self._traverse_served(
                serve, pin, triple, budget, entries, seen,
                partials, per_topic_support, uncertain)
        _birth, _epoch, _mx = pin[0], pin[1], pin[2]
        max_edges = int(self._C("DOSSIER_MAX_EDGES",
                                DOSSIER_MAX_EDGES))
        hops = int(self._C("DOSSIER_REL_HOPS", DOSSIER_REL_HOPS))
        idx_rel = get_index(self.tl, pin)
        live = set(self.idx.atoms)
        trav = _relquery.traverse(
            idx_rel, [e["atom_id"] for e in entries], live,
            max_hops=hops, max_edges=max_edges,
            charge=budget.charge, visible=set(idx_rel.records))
        reached = trav["reached"]
        added = 0
        for eid in sorted(reached,
                          key=lambda a: (reached[a]["hop"], a)):
            info = reached[eid]
            if eid in seen or eid not in live:
                continue  # atoms only; dedupe
            a = self.idx.atoms[eid]
            try:
                body = self.tl.read_artifact(
                    a["text_art"],
                    expect_digest=a["text_digest"])
                integrity = "intact-verified"
            except (ValueError, OSError):
                partials.append({
                    "scope": f"candidate:{eid[:16]}",
                    "cause": "integrity-failed:withheld"})
                continue  # Q15.2b: never served
            budget.charge(1, "assembly-read")
            support = self._union_support(
                eid, per_topic_support)
            seen.add(eid)
            entries.append({
                "atom_id": eid,
                "issuing_generation":
                    f"{_birth}:{_epoch}:{a['seq']}",
                "resolving_generation": triple,
                "text": body.decode("utf-8"),
                "span": a["span"], "doc_id": a["doc_id"],
                "emitted_score": 0.0,
                "support": support,
                "verdicts": {
                    "integrity": integrity,
                    "selection": "lateral-additive"},
                "marks": {"routing_uncertain": uncertain,
                          "outlier": False,
                          "resolution": "live",
                          "lateral": True,
                          "via_relation": info["via"][0],
                          "rel_status": info["rel_status"],
                          "rel_unresolved": info[
                              "rel_unresolved"],
                          "hop": info["hop"]},
                "dossier_topic": None})
            added += 1
        self.last_rel_backend = "relquery"
        return (added, trav["examined"], trav["hops_used"],
                trav["ineligible"])

    def _traverse_served(self, serve, pin, triple, budget, entries,
                         seen, partials, per_topic_support,
                         uncertain):
        """Wired Q4.1(b) traversal over RelServe (R-2).

        Identical entries, counts, budget charges and marks to
        _traverse_lateral: serve.traverse has the same semantics,
        pruning, charge order and output shape as relquery.traverse
        (Lane R differential), with facade-predicate liveness (no
        set(idx.atoms), no get_index call on this module).
        """
        _birth, _epoch, _mx = pin[0], pin[1], pin[2]
        max_edges = int(self._C("DOSSIER_MAX_EDGES",
                                DOSSIER_MAX_EDGES))
        hops = int(self._C("DOSSIER_REL_HOPS", DOSSIER_REL_HOPS))
        is_live = self.idx.is_live_atom
        trav = serve.traverse(
            [e["atom_id"] for e in entries],
            max_hops=hops, max_edges=max_edges,
            charge=budget.charge, visible=set(serve.visible))
        reached = trav["reached"]
        added = 0
        for eid in sorted(reached,
                          key=lambda a: (reached[a]["hop"], a)):
            info = reached[eid]
            if eid in seen or not is_live(eid):
                continue  # atoms only; dedupe
            a = self.idx.atoms[eid]
            try:
                body = self.tl.read_artifact(
                    a["text_art"],
                    expect_digest=a["text_digest"])
                integrity = "intact-verified"
            except (ValueError, OSError):
                partials.append({
                    "scope": f"candidate:{eid[:16]}",
                    "cause": "integrity-failed:withheld"})
                continue  # Q15.2b: never served
            budget.charge(1, "assembly-read")
            support = self._union_support(
                eid, per_topic_support)
            seen.add(eid)
            entries.append({
                "atom_id": eid,
                "issuing_generation":
                    f"{_birth}:{_epoch}:{a['seq']}",
                "resolving_generation": triple,
                "text": body.decode("utf-8"),
                "span": a["span"], "doc_id": a["doc_id"],
                "emitted_score": 0.0,
                "support": support,
                "verdicts": {
                    "integrity": integrity,
                    "selection": "lateral-additive"},
                "marks": {"routing_uncertain": uncertain,
                          "outlier": False,
                          "resolution": "live",
                          "lateral": True,
                          "via_relation": info["via"][0],
                          "rel_status": info["rel_status"],
                          "rel_unresolved": info[
                              "rel_unresolved"],
                          "hop": info["hop"]},
                "dossier_topic": None})
            added += 1
        self.last_rel_backend = "relserve"
        return (added, trav["examined"], trav["hops_used"],
                trav["ineligible"])

    def _receipt(self, query, ran, deferred_topics, pin, budget,
                 events, ms, entries, sections, partials, counts,
                 r_total, c_cand, prune_total, top1_any,
                 uncertain_any, incomplete, lat_added,
                 edges_examined, hops_used, lat_inelig, unpruned,
                 shape, trav_on=False):
        triple = pin[3]
        if incomplete is not None:
            status, reason = "bounded-incomplete", incomplete
            support, sel_out = "bounded-incomplete", "budget-hit"
            presentation = "not sure (bounded-incomplete)"
        elif entries:
            status, reason = "complete", None
            support, sel_out = "supported-results", "selected"
            presentation = None  # settled below (S4 precedence)
        elif not ran:
            status, reason = "complete", None
            support, sel_out = "no-emission", "no-emission"
            presentation = None
        else:
            status, reason = "complete", None
            support, sel_out = ("examined-no-support",
                                "none-cleared-tau")
            presentation = None
        if presentation is None:
            # S4 honest-disclosure precedence, reused from Narrow:
            # one-sided low-similarity flag; silence is
            # "unassessed", never "sure".
            if top1_any:
                presentation = ("not sure (low retrieval "
                                "similarity)")
            elif uncertain_any:
                presentation = ("not sure (low region support)")
            else:
                presentation = ("unassessed (similarity above "
                                "floor; not an answerability "
                                "claim)")
        # Flag-off receipts are byte-identical to pre-round-9: the
        # traversal keys below are added only when trav_on.
        out = {
            "query": query,
            "pinned_generation": triple,
            "execution": {"status": status, "reason": reason},
            "support_findings": support,
            "selection_outcomes": sel_out,
            "metrics": {
                "H_hops": hops_used, "R_regions": r_total,
                "E_edges": edges_examined,
                "C_candidates": c_cand, "P_partitions": 0,
                "T_ms": round(ms, 2),
                "work_used": budget.used,
                "work_budget": budget.cap,
                "op_class_counts": budget.counts,
                "cost_table": _q.COST_TABLE_VERSION,
                "regions_ranked": r_total,
                "prune_survivors": prune_total,
                "entries": len(entries),
                "unpruned_reference": unpruned,
                "support_counts": dict(counts),
                "dossier": {
                    "shape": shape,
                    "topics_run": list(ran),
                    "topics_deferred": list(deferred_topics),
                    "sections": len(sections),
                    "lateral": bool(self._C(
                        "DOSSIER_LATERAL", DOSSIER_LATERAL)),
                    "lateral_added": lat_added,
                    "lateral_edges_examined": edges_examined,
                    "lateral_ineligible": lat_inelig,
                    "max_entries": self._C(
                        "DOSSIER_MAX_ENTRIES",
                        DOSSIER_MAX_ENTRIES),
                    "max_edges": self._C("DOSSIER_MAX_EDGES",
                                         DOSSIER_MAX_EDGES),
                    "max_topics": self._C("DOSSIER_MAX_TOPICS",
                                          DOSSIER_MAX_TOPICS)}},
            "flags": {
                "routing_uncertain_Q3.3": uncertain_any,
                "low_retrieval_similarity_Q3.3": top1_any,
                "narrow_Q9.2": False,
                # Cross-topic receipts keep their exact key set;
                # relational mirrors it with its own shape flag.
                **({"dossier_relational": True}
                   if shape == "relational" else
                   {"dossier_cross_topic": True}),
            },
            "flags_not_produced": {
                "activation_drift_Q8.1": "no spreading/activation "
                "machinery in dossier 1-hop (relation traversal "
                "only)",
                "qualifier_Q12.1": "atoms carry no qualifier "
                "signals (named S-02-ingestion input)",
                "unresolved_Q12.2": "atom-level unresolved marks "
                "need qualifier signals; relation-level "
                "unresolved carried on lateral entries",
                "joint_preservation_Q12.3": "no identified pairs "
                "(trigger needs qualifier signals)",
            },
            "uncertainty_presentation": presentation,
            "partials": partials,
            "disclosure_UQ1": {"events": events},
        }
        if trav_on:
            out["metrics"]["dossier"]["traversal"] = True
            out["metrics"]["dossier"]["rel_hops"] = int(
                self._C("DOSSIER_REL_HOPS", DOSSIER_REL_HOPS))
            out["metrics"]["dossier"]["hops_used"] = hops_used
            out["flags"]["dossier_rel_traversal"] = True
        return out
