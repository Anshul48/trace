"""C2 Lane R: delta-aware RelServe over the ServingView facade.

Covers tlsys.relserve (RelServe.open/advance, incident/traverse, qualifier
access, tombstone-aware eligibility, Lane-G counters, pin discipline):

- Differential vs the C1 reference (relquery.load + relquery.traverse +
  identify_pairs + qual_signals over ReferenceNarrowIndex) at every pin:
  all six view fields + opposition material + bridge/qualifier outputs,
  exact, including degenerate shapes (0-edge traversal, empty pairs --
  the KNOWN C1 G3 grounding-failure shapes are REPRODUCED, never fixed).
- Advance == fresh open == reference after adds, late relation-endpoint
  resolution, supersedes (status + grounding change), corrections
  (new revision + retirement) and unrelated N-growth.
- Counters: exact unit accounting (open == 2R; advance == admits+evals;
  keyed reads +0); per-query cost has no N term (N-growth leaves advance
  and traverse units unchanged).
- Tombstones: retirement flips eligibility exactly; traverse/lateral
  exclude retired atoms at the next pin (FI-18 relation legs).
- Pin discipline: foreign-store/epoch advance rebuilds exact (FI-2),
  rewind rebuilds exact (FI-3), facade hop without paired advance fails
  closed (FI-7), two pins coexist without mixing.
- Facade purity: the index surface touched is exactly
  {triple, retired_aids, is_live_atom} (no NarrowIndex internals).
- Class outputs: dossier relational (+traversal) and cross-topic runs
  over the facade equal the reference; Narrow REL_QUALIFIERS runs equal.

Deterministic fake encoder; scratch stores under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_relserve.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import ReferenceNarrowIndex, NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys.relations import (PROPOSED, SOURCE_ATTRIBUTED,  # noqa: E402
                             commit_relations, get_index,
                             invalidate_rel_index, make_record)
from tlsys.lifecycle import retire_docs  # noqa: E402
from tlsys import relquery  # noqa: E402
from tlsys import relserve  # noqa: E402
from tlsys.relserve import RelServe, StaleServeError  # noqa: E402

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
    """Normalize dossier/narrow runs for comparison (wall clocks only)."""
    def _walk(o):
        if isinstance(o, dict):
            return {k: (-1.0 if k in ("T_ms", "ms", "wall_ms") else _walk(v))
                    for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_walk(v) for v in o]
        return o
    return _walk(obj)


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

CFG = {"extractor": "test-relserve-v1", "window": 1,
       "model": "none", "rules": ["relserve"]}
DEAD = "de" * 32

DOCS = [
    ("d0", "alpha norms govern the alpha baseline completely."),
    ("d1", "bravo rules handle the bravo cases entirely."),
    ("d2", "charlie axioms cover the charlie domain fully."),
    ("d3", "delta statutes span the delta regime wholly."),
    ("d4", "echo remarks touch sundry matters lightly."),
    ("d5", "foxtrot clauses bind the foxtrot parties duly."),
    ("d6", "zebra quixotic jargon with no relation anywhere."),
]


def fixture_approval(tag):
    return {"type": "user", "approval_id": "fixture-relserve-" + tag}


def ref_view(tl, pin):
    """Fresh C1 reference view (cache invalidated: exact per-call build)."""
    relquery.invalidate_rel_view()
    idx = ReferenceNarrowIndex(tl, pin)
    return relquery.load(tl, pin, set(idx.atoms)), idx


def norm_opp(opp):
    return canon({r: [o[0], sorted(o[1]), o[2], o[3]]
                  for r, o in opp.items()})


def norm_view_fields(view):
    return {
        "visible": canon(view.visible),
        "eligible": canon(view.eligible),
        "reasons": canon(view.reasons),
        "degrees": canon(view.degrees),
        "scope": canon(view.scope),
        "unresolved": canon(view.unresolved),
        # Opposition material is per-record content; the reference view
        # keeps eligible rows only while the serve retains all rows
        # (needed across eligibility flips without recompute), so the
        # parity comparison restricts to the eligible subset (the
        # all-rows mirror is drift-checked against RelIndex.opp
        # separately wherever the tag carries an index).
        "opp": norm_opp({r: view._opp[r] for r in view.eligible
                         if r in view._opp}),
    }


def check_view_parity(tag, serve, view):
    a = norm_view_fields(serve)
    b = norm_view_fields(view)
    for fld in a:
        check(f"{tag}/{fld}",
              a[fld] == b[fld],
              f"{tag} {fld} diverges")
    da = serve.digest()
    db = relserve.digest_rel_state(
        {r: {"seq": None, "op_id": None, "record": view.visible[r]}
         for r in view.visible},
        view.eligible, view.degrees, view.scope, view.unresolved,
        serve._triple)
    # Digest inputs differ by construction (serve carries seqs, the
    # reference view does not expose them); compare digest-of-content by
    # rebuilding both from bare records.
    da_content = relserve.digest_rel_state(
        {r: {"record": serve.visible[r]} for r in serve.visible},
        serve.eligible, serve.degrees, serve.scope, serve.unresolved,
        serve._triple)
    check(f"{tag}/digest-content", da_content == db,
          f"{da_content} != {db}")
    assert da  # served digest is well-formed (seq-carrying)


def check_traverse_parity(tag, serve, tl, pin, idx_ref, seeds, **kw):
    relquery.invalidate_rel_view()
    idx = get_index(tl, pin)
    live = set(idx_ref.atoms)
    ch_ref, ch_srv = [], []
    ref = relquery.traverse(
        idx, seeds, live, charge=lambda n, c: ch_ref.append((n, c)),
        **kw)
    srv = serve.traverse(
        seeds, charge=lambda n, c: ch_srv.append((n, c)), **kw)
    check(f"{tag}/traverse", canon(ref) == canon(srv),
          f"{canon(ref)} != {canon(srv)}")
    check(f"{tag}/traverse-charge", ch_ref == ch_srv,
          f"{ch_ref} != {ch_srv}")
    return ref


root = tempfile.mkdtemp(prefix="tl-relserve-")
tl = TLStore(os.path.join(root, "store"), create=True,
             lease_owner="test-c2-relserve")
try:
    rep = ingest_docs(tl, DOCS, emb)
    check("ingest/atoms", rep["n_atoms"] == 7, rep)
    pin0 = tl.pin()
    idx0 = NarrowIndex(tl, pin0)
    aids = {a["doc_id"]: aid for aid, a in idx0.atoms.items()}
    check("ingest/seven-atoms", len(aids) == 7, sorted(aids))
    a0, a1, a2 = aids["d0"], aids["d1"], aids["d2"]
    a3, a4, a5 = aids["d3"], aids["d4"], aids["d5"]
    a6 = aids["d6"]

    # Late record built now, committed at pin2: the early cites record
    # pointing at it flips ineligible -> eligible across the advance.
    r_late = make_record("links", [("src", a5), ("dst", a0)],
                         {"negated": False, "claim": "late1"}, CFG,
                         PROPOSED, [a5, a0])
    LATE1 = r_late["relation"]

    batch1 = [
        make_record("links", [("src", a0), ("dst", a1)],
                    {"negated": False, "claim": "c01"}, CFG,
                    PROPOSED, [a0, a1]),
        make_record("links", [("src", a1), ("dst", a2)],
                    {"negated": True, "claim": "c12",
                     "unresolved": "rs-ambig"}, CFG,
                    PROPOSED, [a1, a2]),
        make_record("links", [("src", a2), ("dst", a3)],
                    {"negated": False, "claim": "c23"}, CFG,
                    PROPOSED, [a2, a3]),
        make_record("links", [("src", a3), ("dst", a4)],
                    {"negated": False, "claim": "c34"}, CFG,
                    PROPOSED, [a3, a4]),
        # Opposition pair over context a0 (claims a3 affirmed, a5
        # negated): identify_pairs({a3, a5}) == [(a3, a5)].
        make_record("evidences", [("claim", a3), ("context", a0)],
                    {"negated": False, "scope": "as-stated"},
                    CFG, PROPOSED, [a3, a0]),
        make_record("evidences", [("claim", a5), ("context", a0)],
                    {"negated": True, "scope": "as-stated"},
                    CFG, PROPOSED, [a5, a0]),
        make_record("notes", [("about", a2), ("ctx", a4)],
                    {"note": "x", "unresolved": "rs-second"},
                    CFG, PROPOSED, [a2, a4]),
        make_record("cooccurs", [a4, a5, a4],
                    {"negated": True, "scope": "as-stated"},
                    CFG, PROPOSED, [a4], interchangeable=True),
        make_record("links", [("src", a0), ("dst", DEAD)],
                    {"negated": False}, CFG, PROPOSED, [a0]),
        make_record("cites", [("src", a5), ("dst", LATE1)],
                    {"negated": False}, CFG, PROPOSED, [a5]),
        make_record("also", [("x", a0), ("y", a1)],
                    {"note": "dup-incidence"}, CFG, PROPOSED,
                    [a0, a1]),
        make_record("grounded", [("src", a1), ("dst", a3)],
                    {"negated": False}, CFG, PROPOSED, [DEAD]),
    ]
    sigs = [relquery.make_qual_signal(
                a3, {"topic": "T", "negated": False}, CFG),
            relquery.make_qual_signal(a4, {"negated": True}, CFG)]
    commit_relations(tl, batch1[:10])
    commit_relations(tl, batch1[10:])
    relquery.commit_qual_signals(tl, sigs)
    pin1 = tl.pin()
    R1 = len(batch1) + len(sigs)
    check("p1/fourteen-records", R1 == 14, R1)

    fac1 = NarrowIndex(tl, pin1)
    v1, idx1 = ref_view(tl, pin1)
    s1 = RelServe.open(tl, fac1, pin1)
    check("p1/covers", s1.covers(pin1) and not s1.covers(pin0))
    # Exact unit accounting: R admits + R eligibility evals, nothing else
    # (measured before any digest/receipt call, which counts its scan).
    check("p1/units-open",
          s1.counters.get("relation_work_units") == 2 * R1
          and s1.stats()["records_admitted"] == R1
          and s1.stats()["eligibility_evals"] == R1,
          s1.stats())
    check_view_parity("p1/open", s1, v1)
    # All-rows opposition mirror drift-check vs the shared RelIndex.
    check("p1/opp-all-rows",
          norm_opp(s1._opp)
          == norm_opp({r: get_index(tl, pin1).opp[r]
                       for r in s1._opp}),
          "serve _opp_of drifted from RelIndex.opp")
    check("p1/counts",
          s1.counts()["visible"] == 14
          and s1.counts()["eligible"] == len(v1.eligible)
          and s1.counts()["ineligible"] == len(v1.reasons),
          s1.counts())

    # Bridge parity incl. charge order; multi-hop + edge cap shapes.
    t1 = check_traverse_parity("p1/bridge", s1, tl, pin1, idx1,
                               [a0], max_hops=2)
    check("p1/bridge-nonempty", t1["examined"] > 0
          and len(t1["reached"]) > 0, t1)
    check_traverse_parity("p1/bridge-cap", s1, tl, pin1, idx1,
                          [a0], max_hops=3, max_edges=2)
    # G3-analog degenerate shapes: reproduced, never fixed.
    t_iso = check_traverse_parity("p1/bridge-zero", s1, tl, pin1,
                                  idx1, [a6], max_hops=2)
    check("p1/bridge-zero-edges", t_iso["examined"] == 0
          and t_iso["reached"] == {} and t_iso["hops_used"] == 0,
          t_iso)
    # Qualifier parity: pair found over the pair universe, empty
    # elsewhere (the KNOWN C1 q1 empty-pairs shape, reproduced).
    uni_pair = [a3, a5]
    check("p1/pairs-found",
          s1.identify_pairs(uni_pair)
          == relquery.identify_pairs(v1, uni_pair)
          == [(a3, a5) if a3 < a5 else (a5, a3)],
          s1.identify_pairs(uni_pair))
    uni_empty = [a0, a1]
    check("p1/pairs-empty",
          s1.identify_pairs(uni_empty)
          == relquery.identify_pairs(v1, uni_empty) == [],
          s1.identify_pairs(uni_empty))
    check("p1/signals",
          canon(s1.qual_signals())
          == canon(relquery.qual_signals(v1)),
          canon(s1.qual_signals()))
    # Keyed reads cost zero units; incident/traverse cost touched only.
    u_before = s1.counters.get("relation_work_units")
    check("p1/keyed-scope", s1.scope_for(a0) == v1.scope.get(a0, []),
          s1.scope_for(a0))
    check("p1/keyed-degrees",
          s1.degrees_for([a0, a1, DEAD])
          == {a: v1.degrees[a] for a in (a0, a1) if a in v1.degrees},
          s1.degrees_for([a0, a1, DEAD]))
    _c = s1.counts()
    check("p1/keyed-zero",
          s1.counters.get("relation_work_units") == u_before,
          s1.counters.get("relation_work_units") - u_before)
    from tlsys.dossier import _incident_rids as _d_inc
    rels_raw = {r: {"record": v1.visible[r]} for r in v1.visible}
    check("p1/incident-dossier",
          s1.incident(a0) == _d_inc(rels_raw, get_index(tl, pin1)
                                    .endpoint_adj, a0),
          s1.incident(a0))
    # Error parity (same messages as the reference traverse).
    for bad in ({"max_hops": 0}, {"max_edges": -1}):
        try:
            relquery.traverse(get_index(tl, pin1), [a0], set(idx1.atoms),
                              **bad)
            ref_err = None
        except ValueError as e:
            ref_err = str(e)
        try:
            s1.traverse([a0], **bad)
            srv_err = None
        except ValueError as e:
            srv_err = str(e)
        check(f"p1/err-{sorted(bad)}", ref_err == srv_err
              and ref_err is not None, (ref_err, srv_err))

    # -- pin2: late resolution + supersedes + unrelated N-growth ----
    # Supersede 1: same identity, new status/version (winner moves, same
    # endpoints). Supersede 2: grounding change (live atom moves the
    # grounding edge; eligibility unchanged -- still eligible).
    sup_status = make_record(
        "links", [("src", a0), ("dst", a1)],
        {"negated": False, "claim": "c01"}, CFG,
        SOURCE_ATTRIBUTED, [a0, a1], version=2)
    check("p2/supersede-same-rid",
          sup_status["relation"]
          == [r for r in batch1
              if r.get("qualifiers", {}).get("claim") == "c01"][0][
              "relation"],
          sup_status["relation"])
    sup_ground = make_record(
        "links", [("src", a2), ("dst", a3)],
        {"negated": False, "claim": "c23"}, CFG,
        PROPOSED, [a2, a3, a5], version=2)
    commit_relations(tl, [r_late, sup_status, sup_ground])
    rep2 = ingest_docs(tl, [("d7", "alpha bravo extra unrelated text one."),
                            ("d8", "charlie delta extra unrelated two."),
                            ("d9", "echo foxtrot extra unrelated three.")],
                       emb)
    check("ingest/growth", rep2["n_atoms"] == 3, rep2)
    pin2 = tl.pin()
    fac2 = NarrowIndex(tl, pin2)
    v2, idx2 = ref_view(tl, pin2)
    u_pre = s1.counters.get("relation_work_units")
    inelig_pre = s1.counts()["ineligible"]
    s1.advance(fac2, pin2)
    u_adv = s1.counters.get("relation_work_units") - u_pre
    check("p2/covers", s1.covers(pin2) and not s1.covers(pin1))
    check_view_parity("p2/advance", s1, v2)
    # Fresh open agrees with the incremental advance (all fields).
    s2_fresh = RelServe.open(tl, fac2, pin2)
    check_view_parity("p2/fresh-eq-ref", s2_fresh, v2)
    check("p2/advance-eq-fresh",
          norm_view_fields(s1) == norm_view_fields(s2_fresh),
          "incremental advance diverges from fresh open")
    # The early cites record flipped ineligible -> eligible on late
    # resolution; the supersede winners moved.
    check("p2/late-flip",
          "cites" in {v2.visible[r]["rel_type"]
                      for r in v2.eligible}
          and s1.counts()["eligible"] == len(v2.eligible),
          s1.counts())
    check("p2/supersede-status",
          s1.visible[sup_status["relation"]]["status"]
          == SOURCE_ATTRIBUTED
          == v2.visible[sup_status["relation"]]["status"],
          s1.visible[sup_status["relation"]]["status"])
    # Advance units == admits(changed window) + evals(reeval set): the
    # unrelated N-growth contributes ZERO units (no N term).
    n_inelig_re = s1.stats()["ineligible_rechecks"]
    check("p2/units-advance-shape",
          u_adv == 3 + (3 + n_inelig_re),
          {"u_adv": u_adv, "inelig_rechecks": n_inelig_re,
           "inelig_pre": inelig_pre})
    t2 = check_traverse_parity("p2/bridge", s1, tl, pin2, idx2,
                               [a0], max_hops=2)
    check("p2/bridge-grew", len(t2["reached"]) >= len(t1["reached"]),
          (len(t1["reached"]), len(t2["reached"])))
    # Traverse units are touched-only: identical before/after N-growth
    # for the same seeds (N appears nowhere).
    u_t0 = s2_fresh.counters.get("relation_work_units")
    r_t = s2_fresh.traverse([a0], max_hops=2)
    u_trav = s2_fresh.counters.get("relation_work_units") - u_t0
    check("p2/traverse-units-touched",
          u_trav == r_t["examined"] + r_t["examined"],
          {"u_trav": u_trav, "examined": r_t["examined"]})

    # -- pin3: correction (new revision + retirement), FI-18 --------
    rep3 = ingest_docs(tl, [("d4-v2", "echo remarks revised and corrected "
                             "lightly.")], emb)
    check("ingest/correction", rep3["n_atoms"] == 1, rep3)
    rrep = retire_docs(tl, ["d4"], reason="rs-correction",
                       approvals={"d4": fixture_approval("retire-d4")})
    check("retire/report", rrep["retired"] == ["d4"]
          and rrep["n_commits"] == 1, rrep)
    pin3 = tl.pin()
    fac3 = NarrowIndex(tl, pin3)
    check("retire/facade-tombstone",
          "d4" in fac3.retired_docs and a4 in fac3.retired_aids
          and not fac3.is_live_atom(a4), fac3.retired_docs)
    v3, idx3 = ref_view(tl, pin3)
    check("retire/ref-agrees",
          "d4" in idx3.retired_docs and a4 in idx3.retired_aids,
          idx3.retired_docs)
    u_pre3 = s1.counters.get("relation_work_units")
    s1.advance(fac3, pin3)
    u_adv3 = s1.counters.get("relation_work_units") - u_pre3
    check_view_parity("p3/retire", s1, v3)
    # Tombstone flips are exact: every record touching a4 went
    # ineligible on both implementations, nothing else flipped.
    flipped = [r for r in v1.eligible if r not in v3.eligible]
    check("p3/flips-nonempty", len(flipped) > 0, len(flipped))
    def _touches_a4(rid):
        rec = v3.visible[rid]
        if rec.get("interchangeable"):
            eps = set(rec.get("endpoints", []))
        else:
            eps = {e[1] for e in rec.get("endpoints", [])}
        return a4 in eps or a4 in rec.get("grounding", [])
    check("p3/flips-touch-a4",
          all(_touches_a4(r) for r in flipped)
          and sorted(s1.eligible) == sorted(v3.eligible),
          flipped)
    # Exact retirement-advance units: 0 admits (no new records) +
    # evals over (records touching a4) union (p2 ineligible).
    touched_a4 = {r for r in v3.visible if _touches_a4(r)}
    expect_evals = len(touched_a4 | set(v2.reasons))
    check("p3/retire-units-exact", u_adv3 == expect_evals,
          {"u_adv3": u_adv3, "expect": expect_evals,
           "touched_a4": len(touched_a4),
           "inelig2": len(v2.reasons)})
    t3 = check_traverse_parity("p3/bridge", s1, tl, pin3, idx3,
                               [a0], max_hops=2)
    check("p3/bridge-excludes-retired",
          a4 not in t3["reached"], sorted(t3["reached"]))
    check("p3/pairs-after-retire",
          s1.identify_pairs([a3, a5])
          == relquery.identify_pairs(v3, [a3, a5]),
          s1.identify_pairs([a3, a5]))

    # -- FI-2 / FI-3 / FI-7 pin discipline ---------------------------
    root_f = tempfile.mkdtemp(prefix="tl-relserve-foreign-")
    tl_f = TLStore(os.path.join(root_f, "store"), create=True,
                   lease_owner="test-c2-relserve-foreign")
    ingest_docs(tl_f, [("f0", "alpha foreign store isolation text.")],
                emb)
    pin_f = tl_f.pin()
    fac_f = NarrowIndex(tl_f, pin_f)
    # FI-2: a foreign store's pin is refused (fail-closed), never
    # mixed and never silently served empty; same-store rewinds (FI-3
    # below) still rebuild.
    try:
        s1.advance(fac_f, pin_f)
        check("fi2/foreign-triple-refused", False, "no StaleServeError")
    except StaleServeError:
        check("fi2/foreign-triple-refused", True)
    try:
        RelServe.open(tl_f, fac_f, pin1)
        check("fi2/foreign-open-refused", False, "no StaleServeError")
    except StaleServeError:
        check("fi2/foreign-open-refused", True)
    # FI-3: rewind to pin1 rebuilds from scratch, exact.
    fac1b = NarrowIndex(tl, pin1)
    s1.advance(fac1b, pin1)
    check("fi3/rewind-covers", s1.covers(pin1))
    check("fi3/rewind-rebuilt", s1.stats()["rebuilds"] == 1,
          s1.stats())
    v1b, _i1b = ref_view(tl, pin1)
    check_view_parity("fi3/rewind", s1, v1b)
    # FI-7: facade hop without paired advance fails closed; two pins
    # coexist without mixing.
    sA = RelServe.open(tl, fac1b, pin1)
    fac1b.advance_to(pin3)
    try:
        sA.traverse([a0])
        check("fi7/stale-fails-closed", False, "no StaleServeError")
    except StaleServeError:
        check("fi7/stale-fails-closed", True)
    try:
        sA.counts()
        check("fi7/stale-counts-fails-closed", False, "no raise")
    except StaleServeError:
        check("fi7/stale-counts-fails-closed", True)
    sB = RelServe.open(tl, fac3, pin3)
    check("fi7/coexist",
          sB.covers(pin3) and sorted(sB.eligible)
          == sorted(v3.eligible)
          and sA._triple == pin1[3] and sB._triple == pin3[3],
          (sA._triple, sB._triple))
    # open() against a wrong-pin facade fails closed too.
    try:
        RelServe.open(tl, fac3, pin1)
        check("fi7/open-wrong-pin-refused", False, "no raise")
    except StaleServeError:
        check("fi7/open-wrong-pin-refused", True)

    # -- facade purity: no NarrowIndex internals --------------------
    touched = set()

    class _Spy:
        def __init__(self, inner):
            object.__setattr__(self, "_inner", inner)

        def __getattribute__(self, name):
            if name == "_inner":
                return object.__getattribute__(self, "_inner")
            touched.add(name)
            return getattr(object.__getattribute__(self, "_inner"),
                           name)

    spy = _Spy(NarrowIndex(tl, pin2))
    fac2b = NarrowIndex(tl, pin2)
    s_spy = RelServe.open(tl, spy, pin2)
    s_spy.traverse([a0])
    s_spy.identify_pairs([a3, a5])
    s_spy.qual_signals()
    s_spy.incident(a0)
    s_spy.scope_for(a0)
    s_spy.degrees_for([a0])
    s_spy.digest()
    s_spy.counts()
    spy2 = _Spy(fac2b)
    fac2b.advance_to(pin3)
    s_spy.advance(spy2, pin3)
    check("guard/allowlist",
          touched <= {"triple", "retired_aids", "is_live_atom"},
          sorted(touched))
    check("guard/uses-predicate", "is_live_atom" in touched,
          sorted(touched))

    # -- class outputs: dossier + narrow over facade vs reference ---
    # (Query paths resolve at the store's current pin, so the class
    # differentials run at pin3 -- with retirement active.)
    v3c, idx3c = ref_view(tl, pin3)
    fac3c = NarrowIndex(tl, pin3)
    for shape, cfg in (
            ("relational", {"DOSSIER_SHAPE": "relational"}),
            ("relational-trav",
             {"DOSSIER_SHAPE": "relational",
              "DOSSIER_REL_TRAVERSAL": True}),
            ("cross-topic", {"DOSSIER_SHAPE": "cross-topic"})):
        d_ref = DossierQuery(tl, idx3c, emb1, cfg=cfg)
        d_fac = DossierQuery(tl, fac3c, emb1, cfg=cfg)
        topics = ["alpha baseline norms", "delta regime statutes"]
        dos_r, rec_r = d_ref.run("alpha delta bridge", topics=topics)
        dos_f, rec_f = d_fac.run("alpha delta bridge", topics=topics)
        check(f"class/{shape}-entries",
              norm_run(dos_r) == norm_run(dos_f),
              f"{shape} dossier entries diverge")
        check(f"class/{shape}-receipt",
              norm_run(rec_r) == norm_run(rec_f),
              f"{shape} dossier receipts diverge")
    # G3-analog bridge-miss: isolated-topic query examines 0 edges and
    # adds nothing lateral -- reproduced on both backends.
    d_iso_r = DossierQuery(tl, idx3c, emb1,
                           cfg={"DOSSIER_SHAPE": "relational",
                                "DOSSIER_REL_TRAVERSAL": True})
    d_iso_f = DossierQuery(tl, fac3c, emb1,
                           cfg={"DOSSIER_SHAPE": "relational",
                                "DOSSIER_REL_TRAVERSAL": True})
    dos_ir, rec_ir = d_iso_r.run("zebra quixotic jargon")
    dos_if, rec_if = d_iso_f.run("zebra quixotic jargon")
    check("class/bridge-miss-equal",
          norm_run((dos_ir, rec_ir)) == norm_run((dos_if, rec_if)),
          "isolated bridge-miss diverges across backends")
    trav_iso = (dos_ir.get("traversal") or rec_ir.get("traversal")
                or {})
    check("class/bridge-miss-zero",
          trav_iso.get("edges_examined", 0) == 0
          and trav_iso.get("lateral_added", 0) == 0,
          trav_iso)
    # Qualifier class: Narrow REL_QUALIFIERS runs are backend-identical.
    n_ref = NarrowQuery(tl, idx3c, emb1,
                        cfg={"REL_QUALIFIERS": True,
                             "REL_HUB_SUPPRESS": True})
    n_fac = NarrowQuery(tl, fac3c, emb1,
                        cfg={"REL_QUALIFIERS": True,
                             "REL_HUB_SUPPRESS": True})
    dos_nr, rec_nr = n_ref.run("delta foxtrot scope as-stated")
    dos_nf, rec_nf = n_fac.run("delta foxtrot scope as-stated")
    check("class/qualifier-entries",
          norm_run(dos_nr) == norm_run(dos_nf),
          "narrow qualifier entries diverge")
    check("class/qualifier-receipt",
          norm_run(rec_nr) == norm_run(rec_nf),
          "narrow qualifier receipts diverge")
    # Lane-G export shape: disjoint-scope merge works with serving-style
    # counters (F-cell join contract).
    snap = s1.counters_snapshot()
    check("counters/snapshot-shape",
          snap["scope"] == "relserve"
          and "relation_work_units" in snap["counters"],
          snap)
finally:
    try:
        tl.close()
    except Exception:
        pass

print(f"FAILS: {len(FAILS)} :: {FAILS}" if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
