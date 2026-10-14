"""M1 lane D: reusable RelView keyed by pin + typed disclosure legs.

Proves the F4 repair (relquery.load per-query global rebuild -> build
once, share across queries at the same pin):

- Equivalence: cached views are byte/normalized-identical to fresh
  per-call builds AND to the TL_REL_ORACLE fullscan build, over a
  workload with relations, eligibility flips, unresolved marks,
  interchangeable endpoints, qualifier signals, and an
  identified pair (six RelView fields + opposition material +
  identify_pairs + qual_signals).
- Work: a fixed 12-query Narrow REL_QUALIFIERS workload touches
  N x R records with per-query rebuilds (pre-M1 shape) vs R
  records + 11 zero-touch serves cached (stats + external spies
  on records_copy / eligibility agree).
- Pin discipline: entries serve only on exact (store, birth,
  epoch, max_seq, live-set) match; cross-store isolation,
  live-mismatch rebuild, backward-pin exactness, foreign
  covering-index bypass without cache poisoning.
- Bypass purity: oracle + audit modes never populate/serve the
  cache (exact pre-M1 behavior on those paths).
- Typed legs: DisclosureLeg values, coerce battery, and
  leg_of_row agreement with the relations prefilter's fail-open
  contract over adversarial disclosures.
- Preserved behavior: traverse() reachability, flag-OFF zero
  relation-path calls, invalidate + FIFO bound.

Deterministic fake encoder; scratch stores under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_m1d_relview.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys.relations import (PROPOSED, commit_relations,  # noqa: E402
                             get_index, invalidate_rel_index,
                             make_record)
from tlsys import relations as relations_mod  # noqa: E402
from tlsys import relquery  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def canon(obj):
    return json.dumps(obj, sort_keys=True, default=str)


def norm_run(obj):
    """Canonical run output with wall-clock neutralized (T_ms only;
    same pin, so generation stamps must match exactly)."""
    obj = json.loads(json.dumps(obj, default=str))

    def _walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "T_ms":
                    o[k] = -1.0
                else:
                    _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)

    _walk(obj)
    return canon(obj)


def norm_view(view):
    """Fully canonical RelView snapshot: six fields + normalized
    opposition material + typed leg."""
    opp = getattr(view, "_opp", None)
    if opp is not None:
        opp = {rid: [rt, sorted(ids), rest, neg]
               for rid, (rt, ids, rest, neg) in opp.items()}
    return canon({"visible": view.visible,
                  "eligible": view.eligible,
                  "reasons": view.reasons,
                  "degrees": view.degrees,
                  "scope": view.scope,
                  "unresolved": view.unresolved,
                  "opp": opp,
                  "leg": view.leg})


def oracle_view(tl, pin, live):
    os.environ["TL_REL_ORACLE"] = "1"
    try:
        invalidate_rel_index(tl)
        return relquery.load(tl, pin, live)
    finally:
        del os.environ["TL_REL_ORACLE"]


def vec(text):
    t = text.lower()
    dims = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
    out = [0.0] * 6
    for i, w in enumerate(dims):
        if w in t:
            out[i] = 1.0
    if not any(out):
        return [0.2] * 6
    return out


def emb(texts):
    return [vec(t) for t in texts]


emb1 = lambda q: vec(q)  # noqa: E731

CFG = {"extractor": "test-m1d-v1", "window": 1,
       "model": "none", "rules": ["relview"]}
DEAD = "de" * 32

DOCS = [
    ("d0", "alpha norms govern the alpha baseline completely."),
    ("d1", "bravo rules handle the bravo cases entirely."),
    ("d2", "charlie axioms cover the charlie domain fully."),
    ("d3", "delta statutes span the delta regime wholly."),
    ("d4", "echo remarks touch sundry matters lightly."),
    ("d5", "foxtrot clauses bind the foxtrot parties duly."),
]

QUERIES = ["alpha baseline norms",
           "bravo cases rules",
           "charlie domain axioms",
           "delta regime statutes"]

root = tempfile.mkdtemp(prefix="tl-m1d-")
tl = TLStore(os.path.join(root, "store"), create=True,
             lease_owner="test-m1d-relview")
try:
    rep = ingest_docs(tl, DOCS, emb)
    check("ingest/atoms", rep["n_atoms"] == 6, rep)
    idx0 = NarrowIndex(tl, tl.pin())
    aids = {a["doc_id"]: aid for aid, a in idx0.atoms.items()}
    check("ingest/six-atoms", len(aids) == 6, sorted(aids))
    a0, a1, a2 = aids["d0"], aids["d1"], aids["d2"]
    a3, a4, a5 = aids["d3"], aids["d4"], aids["d5"]

    # Late records are pure-built now, committed in batch 2: the
    # early records pointing at them flip ineligible -> eligible.
    r_late = make_record("links", [("src", a5), ("dst", a0)],
                         {"negated": False, "claim": "late1"}, CFG,
                         PROPOSED, [a5, a0])
    r_late2 = make_record("links", [("src", a4), ("dst", a1)],
                          {"negated": False, "claim": "late2"},
                          CFG, PROPOSED, [a4, a1])
    LATE1, LATE2 = r_late["relation"], r_late2["relation"]

    batch1 = [
        make_record("links", [("src", a0), ("dst", a1)],
                    {"negated": False, "claim": "c01"}, CFG,
                    PROPOSED, [a0, a1]),
        make_record("links", [("src", a1), ("dst", a2)],
                    {"negated": True, "claim": "c12",
                     "unresolved": "m1d-ambig"}, CFG,
                    PROPOSED, [a1, a2]),
        make_record("links", [("src", a2), ("dst", a3)],
                    {"negated": False, "claim": "c23"}, CFG,
                    PROPOSED, [a2, a3]),
        make_record("links", [("src", a3), ("dst", a4)],
                    {"negated": False, "claim": "c34"}, CFG,
                    PROPOSED, [a3, a4]),
        make_record("evidences", [("claim", a3), ("context", a0)],
                    {"negated": False, "scope": "as-stated"},
                    CFG, PROPOSED, [a3, a0]),
        make_record("evidences", [("claim", a5), ("context", a0)],
                    {"negated": True, "scope": "as-stated"},
                    CFG, PROPOSED, [a5, a0]),
        make_record("notes", [("about", a2), ("ctx", a4)],
                    {"note": "x", "unresolved": "m1d-second"},
                    CFG, PROPOSED, [a2, a4]),
        make_record("cooccurs", [a4, a5, a4],
                    {"negated": True, "scope": "as-stated"},
                    CFG, PROPOSED, [a4], interchangeable=True),
        make_record("links", [("src", a0), ("dst", DEAD)],
                    {"negated": False}, CFG, PROPOSED, [a0]),
        make_record("cites", [("src", a5), ("dst", LATE1)],
                    {"negated": False}, CFG, PROPOSED, [a5]),
        make_record("cites", [("src", a4), ("dst", LATE2)],
                    {"negated": False}, CFG, PROPOSED, [a4]),
        make_record("also", [("x", a0), ("y", a1)],
                    {"note": "dup-incidence"}, CFG, PROPOSED,
                    [a0, a1]),
    ]
    sigs1 = [relquery.make_qual_signal(
                 a3, {"topic": "T", "negated": False}, CFG),
             relquery.make_qual_signal(
                 a4, {"negated": True}, CFG)]
    commit_relations(tl, batch1[:10])
    commit_relations(tl, batch1[10:])
    relquery.commit_qual_signals(tl, sigs1)
    pin1 = tl.pin()
    idx1 = NarrowIndex(tl, pin1)
    live = set(idx1.atoms)
    check("p1/six-live", live == set(aids.values()), len(live))
    R1 = len(batch1) + len(sigs1)
    check("p1/fourteen-records", R1 == 14, R1)
    r_early = [r for r in batch1
               if r["endpoints"][1][1] == LATE1][0]["relation"]
    r_early2 = [r for r in batch1
                if r["endpoints"][1][1] == LATE2][0]["relation"]
    r_bad = [r for r in batch1
             if r["endpoints"][1][1] == DEAD][0]["relation"]

    # -- B. equivalence at P1: cached == fresh == oracle ---------
    relquery.invalidate_rel_view()
    relquery.reset_rel_view_stats()
    v1 = relquery.load(tl, pin1, live)
    st = relquery.rel_view_stats()
    check("p1/first-load-builds",
          st == {"builds": 1, "hits": 0, "bypasses": 0,
                 "rows_built": 14}, st)
    check("p1/eligible-mix",
          len(v1.eligible) == 11 and len(v1.reasons) == 3,
          (len(v1.eligible), len(v1.reasons)))
    check("p1/early-ineligible",
          r_early in v1.reasons and r_early2 in v1.reasons
          and r_bad in v1.reasons, sorted(v1.reasons))
    check("p1/first-mark-wins",
          v1.unresolved.get(a2) == "m1d-ambig", v1.unresolved)
    check("p1/typed-leg",
          v1.leg is relquery.DisclosureLeg.RELATIONS
          and v1.leg.value == relations_mod.LEG, v1.leg)
    v1_hit = relquery.load(tl, pin1, live)
    check("p1/hit-shares-object", v1_hit is v1)
    check("p1/hit-stats",
          relquery.rel_view_stats()["hits"] == 1,
          relquery.rel_view_stats())
    relquery.invalidate_rel_view(tl)
    v1_fresh = relquery.load(tl, pin1, live)
    check("p1/fresh-distinct-object", v1_fresh is not v1)
    check("p1/cached-eq-fresh",
          norm_view(v1_hit) == norm_view(v1_fresh))
    uni1 = set(live)
    check("p1/pairs-eq",
          relquery.identify_pairs(v1_hit, uni1)
          == relquery.identify_pairs(v1_fresh, uni1),
          relquery.identify_pairs(v1_hit, uni1))
    check("p1/pair-found",
          relquery.identify_pairs(v1_hit, uni1)
          == [tuple(sorted((a3, a5)))],
          relquery.identify_pairs(v1_hit, uni1))
    check("p1/a4-mark-second",
          v1.unresolved.get(a4) == "m1d-second", v1.unresolved)
    check("p1/degrees-exact",
          v1.degrees == {a0: 4, a1: 3, a2: 3, a3: 4, a4: 4,
                         a5: 2}, v1.degrees)
    check("p1/signals-eq",
          canon(relquery.qual_signals(v1_hit))
          == canon(relquery.qual_signals(v1_fresh)))
    v1_orc = oracle_view(tl, pin1, live)
    check("p1/oracle-no-index-material",
          not hasattr(v1_orc, "_opp") and hasattr(v1_hit, "_opp"))
    for fld in ("visible", "eligible", "reasons", "degrees",
                "scope", "unresolved"):
        check(f"p1/oracle-{fld}-eq",
              canon(getattr(v1_orc, fld))
              == canon(getattr(v1_hit, fld)), fld)
    check("p1/oracle-pairs-eq",
          relquery.identify_pairs(v1_orc, uni1)
          == relquery.identify_pairs(v1_hit, uni1))
    # Explicit own covering index shares the same entry safely.
    idxr = get_index(tl, pin1)
    relquery.invalidate_rel_view(tl)
    v1_exp = relquery.load(tl, pin1, live, index=idxr)
    check("p1/explicit-index-eq",
          norm_view(v1_exp) == norm_view(v1_hit))
    check("p1/explicit-then-default-hits",
          relquery.load(tl, pin1, live) is v1_exp)
    stale = get_index(tl, pin1)
    stale.frontier -= 1
    check("p1/stale-falls-back-exact",
          norm_view(relquery.load(tl, pin1, live, index=stale))
          == norm_view(v1_hit))

    # -- C. fixed 12-query workload: rebuilds vs cached --------
    # Pre-warm the R8-A substrate so both arms measure pure F4
    # per-query work (record copies + eligibility), not I/O.
    get_index(tl, pin1)
    workload = [q for _ in range(3) for q in QUERIES]
    assert len(workload) == 12

    # R-2 wiring scope: this work block pins legacy relquery view
    # accounting (builds/hits/spies) through NarrowQuery, so it runs
    # the legacy rel path explicitly. The wired default is pinned by
    # test_c2_entry_guards_r2.py. No assertion below is changed.
    LEGACY_REL_CFG = {"REL_QUALIFIERS": True, "RELSERVE_WIRED": False}

    def _run_workload():
        outs = []
        for q in workload:
            nq = NarrowQuery(tl, idx1, emb1,
                             cfg=dict(LEGACY_REL_CFG))
            outs.append(norm_run(nq.run(q)))
        return outs

    copy_calls, copy_rows = [], []
    _orig_copy = relations_mod.RelIndex.records_copy

    def _spy_copy(self, min_seq=0):
        out = _orig_copy(self, min_seq=min_seq)
        copy_calls.append(1)
        copy_rows.append(len(out))
        return out

    elig_calls = []
    _orig_elig = relquery._eligible

    def _spy_elig(rec, live_atoms, visible=frozenset()):
        elig_calls.append(1)
        return _orig_elig(rec, live_atoms, visible)

    relations_mod.RelIndex.records_copy = _spy_copy
    relquery._eligible = _spy_elig
    try:
        # BEFORE shape: invalidate per query == pre-M1 per-call
        # build on every query (identical code path).
        relquery.reset_rel_view_stats()
        mark_before = len(tl.trace.calls)
        outs_before = []
        for q in workload:
            relquery.invalidate_rel_view(tl)
            nq = NarrowQuery(tl, idx1, emb1,
                             cfg=dict(LEGACY_REL_CFG))
            outs_before.append(norm_run(nq.run(q)))
        stats_before = relquery.rel_view_stats()
        copies_before = (len(copy_calls), sum(copy_rows))
        elig_before = len(elig_calls)
        store_before = [c["op"] for c in tl.trace.calls[
            mark_before:]]
        # AFTER: one build, eleven zero-touch serves.
        del copy_calls[:]
        del copy_rows[:]
        del elig_calls[:]
        relquery.invalidate_rel_view(tl)
        relquery.reset_rel_view_stats()
        mark_after = len(tl.trace.calls)
        outs_after = _run_workload()
        stats_after = relquery.rel_view_stats()
        copies_after = (len(copy_calls), sum(copy_rows))
        elig_after = len(elig_calls)
        store_after = [c["op"] for c in tl.trace.calls[
            mark_after:]]
    finally:
        relations_mod.RelIndex.records_copy = _orig_copy
        relquery._eligible = _orig_elig
    check("work/outputs-identical",
          outs_before == outs_after)
    check("work/before-rebuilds",
          stats_before == {"builds": 12, "hits": 0, "bypasses": 0,
                           "rows_built": 12 * 14}, stats_before)
    check("work/after-cached",
          stats_after == {"builds": 1, "hits": 11, "bypasses": 0,
                          "rows_built": 14}, stats_after)
    check("work/spy-copies",
          copies_before == (12, 12 * 14)
          and copies_after == (1, 14),
          (copies_before, copies_after))
    check("work/spy-eligibility",
          elig_before == 12 * 14 and elig_after == 14,
          (elig_before, elig_after))
    check("work/no-relation-store-reads",
          "read_commits" not in store_before
          and "pub_refs" not in store_before
          and "read_commits" not in store_after
          and "pub_refs" not in store_after,
          sorted(set(store_before) | set(store_after)))
    print(f"M1D-WORKLOAD before={stats_before} "
          f"copies={copies_before} elig={elig_before} "
          f"after={stats_after} copies={copies_after} "
          f"elig={elig_after}")

    # -- H. traverse() behavior preserved (R9-B) ----------------
    ridx = get_index(tl, pin1)
    t1 = relquery.traverse(ridx, [a0], live, max_hops=1,
                           max_edges=50)
    check("trav/hops1-set", set(t1["reached"]) == {a1, a3, a5},
          sorted(t1["reached"]))
    check("trav/hops1-counts",
          (t1["examined"], t1["ineligible"], t1["hops_used"])
          == (5, 1, 1),
          (t1["examined"], t1["ineligible"], t1["hops_used"]))
    t2 = relquery.traverse(ridx, [a0], live, max_hops=2,
                           max_edges=50)
    check("trav/hops2-set",
          set(t2["reached"]) == {a1, a2, a3, a4, a5},
          sorted(t2["reached"]))
    check("trav/hops2-counts",
          (t2["examined"], t2["ineligible"], t2["hops_used"])
          == (11, 2, 2),
          (t2["examined"], t2["ineligible"], t2["hops_used"]))
    _by_claim = {}
    for _rid, _rec in v1.eligible.items():
        _q = _rec.get("qualifiers", {})
        if "claim" in _q:
            _by_claim[_q["claim"]] = _rid
    _r_inter = [rid for rid, rec in v1.eligible.items()
                if rec["rel_type"] == "cooccurs"][0]
    check("trav/hops2-hopmarks",
          t2["reached"][a2]["hop"] == 2
          and t2["reached"][a4]["hop"] == 2
          and sorted(t2["reached"][a2]["via"])
          == sorted([_by_claim["c12"], _by_claim["c23"]])
          and sorted(t2["reached"][a4]["via"])
          == sorted([_by_claim["c34"], _r_inter]),
          t2["reached"][a2])

    # -- I. flag-OFF: zero relation-path calls ------------------
    load_calls = []
    _orig_load = relquery.load

    def _spy_load(*a, **k):
        load_calls.append(1)
        return _orig_load(*a, **k)

    relquery.load = _spy_load
    try:
        relquery.invalidate_rel_view(tl)
        off1 = NarrowQuery(tl, idx1, emb1, cfg={}).run(
            "alpha baseline")
        off2 = DossierQuery(tl, idx1, emb1, cfg={}).run(
            "alpha baseline")
    finally:
        relquery.load = _orig_load
    check("off/zero-load-calls", load_calls == [], load_calls)
    check("off/dossier-narrow-delegates",
          canon(off2[0]) == canon(off1[0]))

    # -- E. pin discipline --------------------------------------
    # Cross-store isolation: a second store never sees tl's view.
    root2 = tempfile.mkdtemp(prefix="tl-m1d-xstore-")
    tl2 = TLStore(os.path.join(root2, "store"), create=True,
                 lease_owner="test-m1d-xstore")
    try:
        ingest_docs(tl2, [("e1", "zebra quills vex jumpy foxes "
                           "brightly")], emb)
        pin_x = tl2.pin()
        live_x = set(NarrowIndex(tl2, pin_x).atoms)
        relquery.invalidate_rel_view()
        vx = relquery.load(tl2, pin_x, live_x)
        v1_again = relquery.load(tl, pin1, live)
        check("disc/two-entries",
              relquery.rel_view_cache_info()["size"] == 2,
              relquery.rel_view_cache_info())
        check("disc/xstore-empty",
              vx.visible == {} and v1_again is not vx)
        check("disc/home-exact",
              norm_view(v1_again) == norm_view(v1_hit))
        # Live-set mismatch rebuilds (never serves stale scope).
        r_neg = [rid for rid, rec in v1.eligible.items()
                 if rec["rel_type"] == "evidences"
                 and rec["qualifiers"].get("negated")][0]
        short = set(live)
        short.discard(a5)
        relquery.reset_rel_view_stats()
        v_short = relquery.load(tl, pin1, short)
        check("disc/live-mismatch-rebuilds",
              relquery.rel_view_stats()["builds"] == 1
              and v_short is not v1_again,
              relquery.rel_view_stats())
        check("disc/live-mismatch-exact",
              r_neg in v_short.reasons
              and r_neg not in v_short.eligible
              and v_short.degrees.get(a5, 0) == 0
              and any("endpoint-unresolved" in r
                      for r in v_short.reasons[r_neg]),
              (len(v_short.eligible), len(v_short.reasons)))
        v_full = relquery.load(tl, pin1, live)
        check("disc/live-restore-exact",
              norm_view(v_full) == norm_view(v1_hit)
              and relquery.rel_view_stats()["builds"] == 2)
        # Foreign covering index: bypassed, never cached.
        fake_rec = make_record("smuggled", [("s", a0)],
                               {"negated": False}, CFG,
                               PROPOSED, [a0])
        fake_rid = fake_rec["relation"]

        class _ForeignIndex:
            db_path = "/foreign/store.db"

            def covers(self, pinned):
                return True

            def records_copy(self, min_seq=0):
                return {fake_rid: {"seq": 1, "op_id": "f",
                                   "record": dict(fake_rec)}}

            opp = {}

        relquery.reset_rel_view_stats()
        v_for = relquery.load(tl, pin1, live,
                              index=_ForeignIndex())
        check("disc/foreign-bypass-content",
              set(v_for.visible) == {fake_rid}
              and relquery.rel_view_stats()["bypasses"] == 1,
              (sorted(v_for.visible),
               relquery.rel_view_stats()))
        check("disc/foreign-no-poison",
              relquery.load(tl, pin1, live) is v_full
              and relquery.rel_view_stats()["hits"] == 1)
    finally:
        tl2.close()

    # -- F. oracle/audit bypass purity --------------------------
    relquery.reset_rel_view_stats()
    size_before = relquery.rel_view_cache_info()["size"]
    os.environ["TL_REL_ORACLE"] = "1"
    try:
        oa = relquery.load(tl, pin1, live)
        ob = relquery.load(tl, pin1, live)
    finally:
        del os.environ["TL_REL_ORACLE"]
    check("bypass/oracle-twice",
          relquery.rel_view_stats() == {"builds": 0, "hits": 0,
                                        "bypasses": 2,
                                        "rows_built": 28},
          relquery.rel_view_stats())
    check("bypass/oracle-distinct-exact",
          oa is not ob and norm_view(oa) == norm_view(ob)
          and relquery.rel_view_cache_info()["size"]
          == size_before)
    os.environ["TL_REL_AUDIT"] = "1"
    try:
        relquery.reset_rel_view_stats()
        aa = relquery.load(tl, pin1, live)
        ab = relquery.load(tl, pin1, live)
    finally:
        del os.environ["TL_REL_AUDIT"]
    check("bypass/audit-twice",
          relquery.rel_view_stats()["bypasses"] == 2
          and relquery.rel_view_stats()["hits"] == 0,
          relquery.rel_view_stats())
    check("bypass/audit-exact",
          norm_view(aa) == norm_view(v1_hit)
          and norm_view(ab) == norm_view(v1_hit))
    check("bypass/cache-intact-after",
          relquery.load(tl, pin1, live) is v_full)

    # -- G. typed disclosure legs -------------------------------
    DL = relquery.DisclosureLeg
    check("legs/values",
          [m.value for m in DL]
          == ["relations", "ingest", "ingest-holon",
              "place-xdoc", "unknown"],
          [m.value for m in DL])
    check("legs/str-enum",
          all(isinstance(m, str) for m in DL)
          and DL.RELATIONS == "relations")
    check("legs/substrate-match",
          DL.RELATIONS.value == relations_mod.LEG)
    check("legs/coerce",
          DL.coerce("relations") is DL.RELATIONS
          and DL.coerce("ingest-holon") is DL.INGEST_HOLON
          and DL.coerce(DL.PLACE_XDOC) is DL.PLACE_XDOC
          and DL.coerce("nope") is DL.UNKNOWN
          and DL.coerce(None) is DL.UNKNOWN
          and DL.coerce(123) is DL.UNKNOWN
          and DL.coerce("") is DL.UNKNOWN
          and DL.coerce("Relations") is DL.UNKNOWN)

    def _row(disclosure):
        return (1, "op", "ACCEPT_ATOMS", "h", "committed",
                disclosure, "t")

    leg_cases = [
        (json.dumps({"leg": "relations"}), DL.RELATIONS),
        (json.dumps({"leg": "relations", "rel_type": "x"}),
         DL.RELATIONS),
        (json.dumps({"leg": "ingest"}), DL.INGEST),
        (json.dumps({"leg": "ingest-holon"}), DL.INGEST_HOLON),
        (json.dumps({"leg": "place-xdoc"}), DL.PLACE_XDOC),
        (json.dumps({}), DL.UNKNOWN),
        (json.dumps({"leg": None}), DL.UNKNOWN),
        (json.dumps({"leg": 123}), DL.UNKNOWN),
        (json.dumps({"leg": "relations-x"}), DL.UNKNOWN),
        ("[[[unparseable", None),
        ("[1,2]", None),
        ('"just-a-string"', None),
        ("null", None),
    ]
    leg_ok = True
    for dis, want in leg_cases:
        row = _row(dis)
        got = relquery.leg_of_row(row)
        keep = relations_mod._is_relation_row(row)
        if got is not want or keep != (got is DL.RELATIONS
                                       or got is None):
            leg_ok = False
    check("legs/classifier-agrees-with-prefilter", leg_ok)

    # -- D. eligibility flips at P2 + backward-pin exactness --
    commit_relations(tl, [r_late, r_late2])
    pin2 = tl.pin()
    check("p2/advanced", pin2[2] > pin1[2], (pin1[2], pin2[2]))
    idx2 = NarrowIndex(tl, pin2)
    live2 = set(idx2.atoms)
    check("p2/same-live", live2 == live)
    relquery.reset_rel_view_stats()
    v2 = relquery.load(tl, pin2, live2)
    check("p2/new-pin-builds",
          relquery.rel_view_stats()["builds"] == 1,
          relquery.rel_view_stats())
    check("p2/sixteen-records",
          len(v2.visible) == 16, len(v2.visible))
    check("p2/flips-eligible",
          r_early in v2.eligible and r_early2 in v2.eligible
          and r_early not in v2.reasons
          and r_early2 not in v2.reasons)
    check("p2/bad-stays-ineligible",
          r_bad in v2.reasons
          and any("endpoint-unresolved" in r
                  for r in v2.reasons[r_bad]))
    check("p2/eligible-count",
          len(v2.eligible) == 15 and len(v2.reasons) == 1,
          (len(v2.eligible), len(v2.reasons)))
    check("p2/marks-stable",
          v2.unresolved.get(a2) == "m1d-ambig"
          and v2.unresolved.get(a4) == "m1d-second",
          v2.unresolved)
    v2_hit = relquery.load(tl, pin2, live2)
    check("p2/hit-shares", v2_hit is v2)
    relquery.invalidate_rel_view(tl)
    v2_fresh = relquery.load(tl, pin2, live2)
    check("p2/cached-eq-fresh",
          norm_view(v2_hit) == norm_view(v2_fresh))
    v2_orc = oracle_view(tl, pin2, live2)
    for fld in ("visible", "eligible", "reasons", "degrees",
                "scope", "unresolved"):
        check(f"p2/oracle-{fld}-eq",
              canon(getattr(v2_orc, fld))
              == canon(getattr(v2_hit, fld)), fld)
    check("p2/oracle-pairs-eq",
          relquery.identify_pairs(v2_orc, set(live2))
          == relquery.identify_pairs(v2_hit, set(live2)))
    check("p2/pair-survives",
          relquery.identify_pairs(v2_hit, set(live2))
          == [tuple(sorted((a3, a5)))])
    check("p2/signals-eq",
          canon(relquery.qual_signals(v2_hit))
          == canon(relquery.qual_signals(v2_fresh)))
    # Backward pin: P1 serves its own exact content, never P2's.
    v1_back = relquery.load(tl, pin1, live)
    check("p2/backward-pin-exact",
          norm_view(v1_back) == norm_view(v1_hit)
          and r_early in v1_back.reasons)
    check("p2/pins-isolated",
          v1_back is not v2_hit and len(v2_hit.visible) == 16
          and len(v1_back.visible) == 14)

    # -- J. invalidation + FIFO bound ---------------------------
    info = relquery.rel_view_cache_info()
    check("inv/two-home-pins", info["size"] >= 2, info)
    relquery.invalidate_rel_view(tl)
    check("inv/invalidate-one-store",
          all(k[0] != relquery._view_cache_key(
              tl, pin1)[0] for k in relquery._VIEW_CACHE),
          relquery.rel_view_cache_info())
    check("inv/other-store-survives",
          relquery.rel_view_cache_info()["size"] == 1,
          relquery.rel_view_cache_info())
    relquery.invalidate_rel_view()
    check("inv/invalidate-all",
          relquery._VIEW_CACHE == {})
    # Grow past the bound: 9 single-record batches, 9 pins.
    pins_j = []
    for n in range(9):
        commit_relations(tl, [make_record(
            "jfill", [("s", a0), ("o", a1)],
            {"negated": False, "fill": n}, CFG, PROPOSED,
            [a0, a1])])
        pins_j.append(tl.pin())
    live_j = set(NarrowIndex(tl, pins_j[-1]).atoms)
    for p in pins_j:
        relquery.load(tl, p, live_j)
    check("inv/bounded",
          relquery.rel_view_cache_info() == {"size": 8,
                                             "max": 8},
          relquery.rel_view_cache_info())
    # Evicted pins rebuild exactly (differential vs oracle).
    for p in (pins_j[0], pins_j[4]):
        got = relquery.load(tl, p, live_j)
        want = oracle_view(tl, p, live_j)
        ok = all(canon(getattr(got, f))
                 == canon(getattr(want, f))
                 for f in ("visible", "eligible", "reasons",
                           "degrees", "scope", "unresolved"))
        check(f"inv/evicted-pin-exact-{pins_j.index(p)}", ok)
finally:
    tl.close()

print(f"done: {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
