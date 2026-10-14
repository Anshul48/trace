"""Round-9 track B: Q4.1(b) relational traversal + qualifier-signal
ingestion + W12 merge-arm unit checks.

Covers (fixture scratch store, deterministic fake encoder):
  traverse(): hop-bounded BFS reachability (bridge veto: hop-2 node
    unreached at hops=1, reached at hops=2), eligibility gating,
    one-examination-per-edge, max_edges cap, charge callback,
    Q7.1 index read-only, arg validation, determinism.
  dossier relational: flag-off byte-path preserved (no traversal
    keys); traversal-on hops=1 reaches the same atom set as the
    legacy _lateral (+hop mark, disclosed); hops=2 serves the
    bridge with hop/via marks + receipt traversal keys;
    traversal ignored for narrow/cross-topic shapes and when
    DOSSIER_LATERAL=False; cfg validation.
  qualifier signals: make/commit/read roundtrip, empty-qualifiers
    + bad-aid refusal, ineligible-signal exclusion, ingested vs
    overlay scope-equivalence (collapse_sig + partition_key +
    unresolved per atom), identify_pairs signal-geometry pin.
  partitioned_mmr: merge="score" default reproduces the settled
    order; merge="roundrobin" deterministic interleave (pinned
    differing order); single pool == plain MMR on both arms;
    bad merge refused.

Run: tl-sys/.venv/bin/python tl-sys/tests/test_r9b_relpath.py
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
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys.fuse import mmr_order_matrix  # noqa: E402
from tlsys import relquery  # noqa: E402
from tlsys.relations import (PROPOSED, commit_relations,  # noqa: E402
                             get_index, invalidate_rel_index,
                             make_record)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def vec(text):
    t = text.lower()
    if "alpha" in t:
        return [1.0, 0.0, 0.0, 0.0]
    if "bravo" in t:
        return [0.0, 1.0, 0.0, 0.0]
    if "charlie" in t:
        return [0.0, 0.0, 1.0, 0.0]
    if "delta" in t:
        return [0.0, 0.0, 0.0, 1.0]
    return [0.25, 0.25, 0.25, 0.25]


def emb(texts):
    return [vec(t) for t in texts]


emb1 = lambda q: vec(q)  # noqa: E731

DOCS = [
    ("d0", "alpha norms govern the alpha baseline completely."),
    ("d1", "bravo rules handle the bravo cases entirely."),
    ("d2", "charlie axioms cover the charlie domain fully."),
    ("d3", "delta statutes span the delta regime wholly."),
    ("d4", "echo remarks touch sundry matters lightly."),
]

CFG = {"extractor": "test-r9b-v1", "window": 1,
       "model": "none", "rules": ["chain-link"]}

root = tempfile.mkdtemp(prefix="tl-r9b-")
tl = TLStore(os.path.join(root, "store"), create=True,
             lease_owner="test-r9b-relpath")
try:
    rep = ingest_docs(tl, DOCS, emb)
    check("ingest/atoms", rep["n_atoms"] == 5, rep)
    pinned0 = tl.pin()
    idx0 = NarrowIndex(tl, pinned0)
    aids = {a["doc_id"]: aid for aid, a in idx0.atoms.items()}
    check("ingest/five-atoms", len(aids) == 5, sorted(aids))
    a0, a1, a2, a3, a4 = (aids["d0"], aids["d1"], aids["d2"],
                         aids["d3"], aids["d4"])

    DEAD = "de" * 32
    # Chain a0-a1-a2-a3-a4 + one ineligible record incident to a0
    # (dead endpoint) + one duplicate-incidence record (a0,a1).
    recs = [
        make_record("links", [("src", a0), ("dst", a1)],
                    {"negated": False, "claim": "c01"}, CFG,
                    PROPOSED, [a0, a1]),
        make_record("links", [("src", a1), ("dst", a2)],
                    {"negated": True, "claim": "c12",
                     "unresolved": "r9b-ambig"}, CFG,
                    PROPOSED, [a1, a2]),
        make_record("links", [("src", a2), ("dst", a3)],
                    {"negated": False, "claim": "c23"}, CFG,
                    PROPOSED, [a2, a3]),
        make_record("links", [("src", a3), ("dst", a4)],
                    {"negated": False, "claim": "c34"}, CFG,
                    PROPOSED, [a3, a4]),
        make_record("links", [("src", a0), ("dst", DEAD)],
                    {"negated": False}, CFG, PROPOSED, [a0]),
        make_record("also", [("x", a0), ("y", a1)],
                    {"note": "dup-incidence"}, CFG, PROPOSED,
                    [a0, a1]),
    ]
    commit_relations(tl, recs)
    pin = tl.pin()
    idx = NarrowIndex(tl, pin)
    live = set(idx.atoms)
    ridx = get_index(tl, pin)
    check("index/six-records", len(ridx.records) == 6,
          len(ridx.records))
    rids = {}
    for rid, item in ridx.records.items():
        rec = item["record"]
        key = (rec["rel_type"],
               tuple(sorted(
                   e[1][:8] for e in rec["endpoints"])))
        rids.setdefault(key, rid)
    r01 = [r for r, it in ridx.records.items()
           if it["record"]["qualifiers"].get("claim") == "c01"][0]
    r12 = [r for r, it in ridx.records.items()
           if it["record"]["qualifiers"].get("claim") == "c12"][0]
    rdup = [r for r, it in ridx.records.items()
            if it["record"]["rel_type"] == "also"][0]

    # -- traverse(): hop-bounded reachability --------------------
    before = json.dumps(ridx.records, sort_keys=True)
    t1 = relquery.traverse(ridx, [a0], live, max_hops=1,
                           max_edges=50)
    check("trav/hops1-reaches-a1",
          set(t1["reached"]) == {a1}, sorted(t1["reached"]))
    check("trav/hops1-hopmarks",
          t1["reached"][a1]["hop"] == 1
          and sorted(t1["reached"][a1]["via"])
          == sorted([r01, rdup])
          and t1["reached"][a1]["rel_status"] == PROPOSED,
          t1["reached"][a1])
    check("trav/hops1-bridge-veto", a2 not in t1["reached"])
    check("trav/hops1-hops-used", t1["hops_used"] == 1,
          t1["hops_used"])
    # Incident to a0: r01, r_bad, r_dup = 3 examined, 1 ineligible.
    check("trav/hops1-examined", t1["examined"] == 3,
          t1["examined"])
    check("trav/hops1-inelig", t1["ineligible"] == 1,
          t1["ineligible"])

    t2 = relquery.traverse(ridx, [a0], live, max_hops=2,
                           max_edges=50)
    check("trav/hops2-reaches-a2",
          set(t2["reached"]) == {a1, a2}, sorted(t2["reached"]))
    check("trav/hops2-marks",
          t2["reached"][a2]["hop"] == 2
          and t2["reached"][a2]["via"] == [r12]
          and t2["reached"][a2]["rel_unresolved"] == "r9b-ambig",
          t2["reached"][a2])
    check("trav/hops2-hops-used", t2["hops_used"] == 2)
    # Hop 2 newly examines r12 only (r01/r_dup already examined).
    check("trav/hops2-examined", t2["examined"] == 4,
          t2["examined"])

    t9 = relquery.traverse(ridx, [a0], live, max_hops=9,
                           max_edges=50)
    check("trav/full-chain",
          set(t9["reached"]) == {a1, a2, a3, a4}
          and t9["hops_used"] == 4, t9["hops_used"])
    check("trav/dead-never-reached", DEAD not in t9["reached"])

    # One examination per edge: seeds {a0,a1} share r01 + r_dup.
    t12 = relquery.traverse(ridx, [a0, a1], live, max_hops=1,
                            max_edges=50)
    check("trav/edge-once", t12["examined"] == 4, t12["examined"])
    check("trav/edge-once-set", set(t12["reached"]) == {a2},
          sorted(t12["reached"]))

    # Caps, charges, validation, read-only, determinism.
    tcap = relquery.traverse(ridx, [a0], live, max_hops=9,
                             max_edges=1)
    check("trav/edge-cap",
          tcap["examined"] == 1 and tcap["hops_used"] <= 1,
          (tcap["examined"], tcap["hops_used"]))
    charges = []
    relquery.traverse(ridx, [a0], live, max_hops=2,
                      max_edges=50,
                      charge=lambda n, c: charges.append((n, c)))
    check("trav/charges",
          charges == [(1, "lateral-edge-inspection")] * 4,
          charges)
    for bad, kw in (("hops0", {"max_hops": 0}),
                    ("edges-neg", {"max_edges": -1})):
        try:
            relquery.traverse(ridx, [a0], live, **kw)
            check(f"trav/{bad}-raises", False, "no raise")
        except ValueError:
            check(f"trav/{bad}-raises", True)
    after = json.dumps(ridx.records, sort_keys=True)
    check("trav/index-readonly", before == after)
    t2b = relquery.traverse(ridx, [a0], live, max_hops=2,
                            max_edges=50)
    check("trav/deterministic",
          json.dumps(t2, sort_keys=True)
          == json.dumps(t2b, sort_keys=True))
    check("trav/empty-seeds",
          relquery.traverse(ridx, [], live)["reached"] == {})

    # -- dossier relational: flag-off preserved ------------------
    Q = "alpha baseline norms"
    dq_off = DossierQuery(tl, idx, emb1,
                          cfg={"DOSSIER_SHAPE": "relational",
                               "NARROW": {"MAX_ENTRIES": 1}})
    dos_off, rec_off = dq_off.run(Q)
    off_ids = [e["atom_id"] for e in dos_off["entries"]]
    check("dos/off-seeds-a0", off_ids[:1] == [a0], off_ids)
    check("dos/off-adds-a1", a1 in off_ids and a2 not in off_ids,
          [i[:8] for i in off_ids])
    check("dos/off-no-trav-keys",
          "traversal" not in rec_off["metrics"]["dossier"]
          and "rel_hops" not in rec_off["metrics"]["dossier"]
          and "dossier_rel_traversal" not in rec_off["flags"],
          sorted(rec_off["flags"]))
    check("dos/off-h1", rec_off["metrics"]["H_hops"] == 1,
          rec_off["metrics"]["H_hops"])

    # -- traversal-on hops=1: same atom set as legacy lateral ---
    dq_t1 = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "relational",
             "DOSSIER_REL_TRAVERSAL": True,
             "NARROW": {"MAX_ENTRIES": 1}})
    dos_t1, rec_t1 = dq_t1.run(Q)
    t1_ids = [e["atom_id"] for e in dos_t1["entries"]]
    # Single lateral addition here, so set == order; with ≥2
    # additions the order differs deterministically (incidence vs
    # (hop, aid): SciFact-pinned delta D3, same set).
    check("dos/t1-same-set", t1_ids == off_ids,
          ([i[:8] for i in t1_ids], [i[:8] for i in off_ids]))
    lat = [e for e in dos_t1["entries"]
           if e["verdicts"]["selection"] == "lateral-additive"]
    check("dos/t1-hop-marks",
          len(lat) == 1 and lat[0]["marks"]["hop"] == 1
          and lat[0]["marks"]["via_relation"]
          == min(r01, rdup)
          and lat[0]["emitted_score"] == 0.0
          and lat[0]["marks"]["rel_status"] == PROPOSED,
          lat[0]["marks"] if lat else None)
    check("dos/t1-examined-parity",
          rec_t1["metrics"]["E_edges"]
          == rec_off["metrics"]["E_edges"],
          (rec_t1["metrics"]["E_edges"],
           rec_off["metrics"]["E_edges"]))
    check("dos/t1-receipt-keys",
          rec_t1["metrics"]["dossier"].get("traversal") is True
          and rec_t1["metrics"]["dossier"].get("rel_hops") == 1
          and rec_t1["flags"].get("dossier_rel_traversal")
          is True)
    # Legacy entries equal modulo the added hop mark.
    ok = True
    for e_off, e_t1 in zip(dos_off["entries"], dos_t1["entries"]):
        m = dict(e_t1["marks"])
        m.pop("hop", None)
        if dict(e_t1, marks=m) != e_off:
            ok = False
    check("dos/t1-entries-modulo-hop", ok)

    # -- traversal-on hops=2: bridge served ----------------------
    dq_t2 = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "relational",
             "DOSSIER_REL_TRAVERSAL": True,
             "DOSSIER_REL_HOPS": 2,
             "NARROW": {"MAX_ENTRIES": 1}})
    dos_t2, rec_t2 = dq_t2.run(Q)
    t2_ids = [e["atom_id"] for e in dos_t2["entries"]]
    check("dos/t2-bridge-served",
          t2_ids[:1] == [a0] and a1 in t2_ids and a2 in t2_ids,
          [i[:8] for i in t2_ids])
    e2 = [e for e in dos_t2["entries"] if e["atom_id"] == a2][0]
    check("dos/t2-bridge-marks",
          e2["marks"]["hop"] == 2
          and e2["marks"]["via_relation"] == r12
          and e2["marks"]["rel_unresolved"] == "r9b-ambig"
          and e2["emitted_score"] == 0.0,
          e2["marks"])
    check("dos/t2-hops-used",
          rec_t2["metrics"]["H_hops"] == 2
          and rec_t2["metrics"]["dossier"]["hops_used"] == 2,
          rec_t2["metrics"]["H_hops"])

    # -- traversal ignored off-shape / lateral-off; cfg gates ----
    dq_n = DossierQuery(tl, idx, emb1,
                        cfg={"DOSSIER_REL_TRAVERSAL": True,
                             "DOSSIER_REL_HOPS": 2})
    _dn, rec_n = dq_n.run(Q)
    check("dos/narrow-ignores-trav",
          "dossier_rel_traversal" not in rec_n["flags"]
          and rec_n["flags"].get("narrow_Q9.2") is True)
    dq_x = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "cross-topic",
             "DOSSIER_REL_TRAVERSAL": True,
             "NARROW": {"MAX_ENTRIES": 1}})
    _dx, rec_x = dq_x.run(Q, topics=["alpha", "bravo"])
    check("dos/xtopic-ignores-trav",
          "dossier_rel_traversal" not in rec_x["flags"]
          and rec_x["metrics"]["H_hops"] <= 1)
    dq_nl = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "relational",
             "DOSSIER_REL_TRAVERSAL": True,
             "DOSSIER_REL_HOPS": 2, "DOSSIER_LATERAL": False,
             "NARROW": {"MAX_ENTRIES": 1}})
    _dnl, rec_nl = dq_nl.run(Q)
    check("dos/lateral-off-wins",
          rec_nl["metrics"]["dossier"]["lateral_added"] == 0
          and rec_nl["metrics"]["E_edges"] == 0)
    for name, cfg in (("hops0", {"DOSSIER_REL_TRAVERSAL": True,
                                 "DOSSIER_REL_HOPS": 0}),
                      ("hops-without-trav",
                       {"DOSSIER_REL_HOPS": 2})):
        try:
            DossierQuery(tl, idx, emb1, cfg=cfg)
            check(f"dos/{name}-raises", False, "no raise")
        except ValueError:
            check(f"dos/{name}-raises", True)

    # -- qualifier signals: build/commit/read --------------------
    try:
        relquery.make_qual_signal(a0, {}, CFG)
        check("qsig/empty-refused", False, "no raise")
    except ValueError:
        check("qsig/empty-refused", True)
    try:
        relquery.make_qual_signal("zz", {"negated": True}, CFG)
        check("qsig/bad-aid-refused", False, "no raise")
    except ValueError:
        check("qsig/bad-aid-refused", True)
    g1 = make_record("evidences", [("s", a0), ("o", a4)],
                     {"negated": False, "topic": "T"}, CFG,
                     PROPOSED, [a0, a4])
    g2 = make_record("evidences", [("s", a3), ("o", a4)],
                     {"negated": True, "topic": "T"}, CFG,
                     PROPOSED, [a3, a4])
    commit_relations(tl, [g1, g2])
    pin1 = tl.pin()
    idx1 = NarrowIndex(tl, pin1)
    live1 = set(idx1.atoms)
    view0 = relquery.load(tl, pin1, live1)
    check("qsig/general-eligible",
          len(view0.eligible) == 7, len(view0.eligible))
    # Mirror every ELIGIBLE overlay touch as an ingested signal
    # (ineligible touches mirror nothing: r_bad stays overlay-absent
    # and signal-absent alike).
    sigs = []
    for rid, rec in sorted(view0.eligible.items()):
        if rec.get("rel_type") == relquery.QUAL_SIGNAL_TYPE:
            continue
        eps = rec.get("endpoints", [])
        ids = (list(eps) if rec.get("interchangeable")
               else [e[1] for e in eps])
        for aid in sorted(set(ids)):
            sigs.append(relquery.make_qual_signal(
                aid, rec["qualifiers"], CFG, PROPOSED))
    ops = relquery.commit_qual_signals(tl, sigs)
    check("qsig/committed", len(ops) == len(sigs) == 14,
          (len(ops), len(sigs)))
    check("qsig/scheme",
          all(s["rel_scheme"] == "tlsys-rel-v1" for s in sigs)
          and all(s["rel_type"] == relquery.QUAL_SIGNAL_TYPE
                  for s in sigs))
    pin2 = tl.pin()
    idx2 = NarrowIndex(tl, pin2)
    live2 = set(idx2.atoms)
    invalidate_rel_index(tl)
    view = relquery.load(tl, pin2, live2)
    got = relquery.qual_signals(view)
    from tlsys.identity import canonical_json_bytes  # noqa: E402
    overlay = {}
    for aid, touches in view0.scope.items():
        overlay[aid] = sorted((canonical_json_bytes(q)
                               for _r, q in touches))
    ingested = {}
    for aid, touches in got.items():
        ingested[aid] = sorted((canonical_json_bytes(q)
                                for _r, q in touches))
    check("qsig/scope-multisets",
          json.dumps(overlay, sort_keys=True, default=str)
          == json.dumps(ingested, sort_keys=True, default=str),
          (sorted(overlay), sorted(ingested)))
    sig_scope = {a: got.get(a, []) for a in live2}
    for aid in sorted(live2):
        ig = sig_scope.get(aid, [])
        if relquery.collapse_sig(aid, view0.scope) != \
                relquery.collapse_sig(aid, sig_scope):
            check("qsig/collapse-sig", False, aid[:8])
            break
        un0 = {a: view0.unresolved.get(a) for a in (aid,)}
        # Ingested unresolved: first-mark-wins over ascending rids.
        mark = None
        for _r, q in sorted(ig):
            if q.get("unresolved") is not None:
                mark = q["unresolved"]
                break
        if un0[aid] != mark:
            check("qsig/unresolved", False, (aid[:8], un0, mark))
            break
    else:
        check("qsig/collapse-sig", True)
        check("qsig/unresolved", True)
    pk0 = {a: relquery.partition_key(a, view0.scope,
                                     view0.unresolved)
           for a in live2}
    pk1 = {a: relquery.partition_key(a, sig_scope,
                                     view0.unresolved)
           for a in live2}
    check("qsig/partition-key",
          json.dumps(pk0, sort_keys=True, default=str)
          == json.dumps(pk1, sort_keys=True, default=str))
    # Ineligible signals stay out of the reader.
    dsig = relquery.make_qual_signal(DEAD, {"negated": True}, CFG)
    relquery.commit_qual_signals(tl, [dsig])
    invalidate_rel_index(tl)
    view3 = relquery.load(tl, tl.pin(), live2)
    check("qsig/dead-excluded",
          DEAD not in relquery.qual_signals(view3))

    # -- identify_pairs: signal geometry pins the delta ---------
    uni = [a0, a3, a4]
    gpairs = relquery.identify_pairs(view0, uni)
    check("qsig/general-pairs", gpairs == [(a0, a3)]
          if a0 < a3 else gpairs == [(a3, a0)], gpairs)
    sig_elig = {r: rec for r, rec in view.eligible.items()
                if rec.get("rel_type")
                == relquery.QUAL_SIGNAL_TYPE}
    sig_view = relquery.RelView(sig_elig, sig_elig, {}, {}, {},
                                {})
    # Signal-only view over the mirrored touches.
    spairs = relquery.identify_pairs(sig_view, uni)
    expect = sorted([(a0, a3), (a0, a4), (a3, a4)]
                    if a0 < a3 else [(a3, a0), (a0, a4),
                                     (a3, a4)])
    expect = sorted(tuple(sorted(p)) for p in expect)
    check("qsig/signal-pairs-superset", spairs == expect, spairs)

    # -- partitioned_mmr merge arms (pure) -----------------------
    x1, x2 = "x" * 63 + "1", "x" * 63 + "2"
    y1 = "y" * 64
    scope = {y1: [("r", {"negated": True})]}
    cands = [(x1, 0.9), (x2, 0.85), (y1, 0.8)]
    sim0 = lambda a, b: 1.0 if a == b else 0.0  # noqa: E731
    m_def = relquery.partitioned_mmr(cands, sim0, 0.8, scope, {})
    m_exp = relquery.partitioned_mmr(cands, sim0, 0.8, scope, {},
                                     merge="score")
    check("mmr/default-is-score", m_def == m_exp == [x1, x2, y1],
          m_def)
    m_rr = relquery.partitioned_mmr(cands, sim0, 0.8, scope, {},
                                    merge="roundrobin")
    check("mmr/roundrobin", m_rr == [x1, y1, x2], m_rr)
    m_rr2 = relquery.partitioned_mmr(cands, sim0, 0.8, scope, {},
                                     merge="roundrobin")
    check("mmr/roundrobin-deterministic", m_rr2 == m_rr)
    one = [(x1, 0.9), (x2, 0.85)]
    plain = mmr_order_matrix(one, sim0, 0.8, len(one))
    check("mmr/single-pool-score",
          relquery.partitioned_mmr(one, sim0, 0.8, {}, {})
          == plain, plain)
    check("mmr/single-pool-rr",
          relquery.partitioned_mmr(one, sim0, 0.8, {}, {},
                                   merge="roundrobin")
          == plain, plain)
    try:
        relquery.partitioned_mmr(one, sim0, 0.8, {}, {},
                                 merge="lottery")
        check("mmr/bad-merge-raises", False, "no raise")
    except ValueError:
        check("mmr/bad-merge-raises", True)
finally:
    tl.close()

print(f"done: {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
