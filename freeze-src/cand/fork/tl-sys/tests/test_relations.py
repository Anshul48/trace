"""Maintained relations test: S-02 section 1b record foundation.

Covers: relation identity determinism + endpoint-order
invariance + qualifier sensitivity (negation/scope), canonical
JSON profile enforcement, extractor config binding, commit/read
roundtrip through a real scratch store, status immutability
(proposed never promoted), flat-AND-availability eligibility,
unresolved-mark preservation, endpoint degrees, and Narrow
isolation (index over relation commits yields identical
atoms/holons), plus first query-path consumption (Q10.1 hub
suppression, Q12.1(a)/(b) + Q12.2 qualifier plumbing over a real
scratch store with flag-OFF byte-identity), plus the R3-B
mechanism batch (Q12.3-mech pair identification + Q12.1(c)
partitioned MMR: pure-function checks, synthetic opposition
units, and wiring checks over a second real scratch store).

Deterministic fake encoder; scratch store under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_relations.py
"""
import json
import math
import os
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.fuse import mmr_order_matrix  # noqa: E402
from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.identity import (canonical_json_bytes,  # noqa: E402
                            extractor_config_id, relation_id)
from tlsys.relations import (PROPOSED, SOURCE_ATTRIBUTED,  # noqa: E402
                             commit_relations, eligible,
                             endpoint_degrees, make_record,
                             read_relations)
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys import relquery  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 4


def emb(texts):
    return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


CFG = {"extractor": "test-cooccur-v1", "window": 2,
       "model": "none", "rules": ["adjacent-chunks"]}
CFG_HEX = extractor_config_id(CFG)

A = "aa" * 32
B = "bb" * 32

# -- identity ----------------------------------------------------
r1 = relation_id("causes", [("agent", A), ("patient", B)],
                 {"negated": False}, CFG_HEX)
r1b = relation_id("causes", [("patient", B), ("agent", A)],
                  {"negated": False}, CFG_HEX)
check("identity/endpoint-order-invariant", r1 == r1b, f"{r1} vs {r1b}")

r_not = relation_id("causes", [("agent", A), ("patient", B)],
                    {"negated": True, "scope": "edge"}, CFG_HEX)
r_notin = relation_id("causes", [("agent", A), ("patient", B)],
                      {"negated": True, "scope": "patient"}, CFG_HEX)
check("identity/negation-scope-matters",
      len({r1, r_not, r_notin}) == 3, "A-causes-B / A-not-cause-B / "
      "A-causes-not-B must all differ")

ri1 = relation_id("cooccurs", [A, B], {}, CFG_HEX,
                  interchangeable=True)
ri2 = relation_id("cooccurs", [B, A], {}, CFG_HEX,
                  interchangeable=True)
check("identity/interchangeable-order-invariant", ri1 == ri2)

q1 = canonical_json_bytes({"b": 1, "a": [True, None]})
check("identity/canonical-bytes", q1 == b'{"a":[true,null],"b":1}',
      repr(q1))

for bad, nm in ((1.5, "float"), (2 ** 53, "big-int"),
                ({1: "x"}, "non-str-key")):
    try:
        canonical_json_bytes(bad)
        check(f"identity/rejects-{nm}", False, "no raise")
    except ValueError:
        check(f"identity/rejects-{nm}", True)

try:
    relation_id("causes", [("agent", "zz")], {}, CFG_HEX)
    check("identity/rejects-bad-endpoint", False, "no raise")
except ValueError:
    check("identity/rejects-bad-endpoint", True)

try:
    make_record("causes", [("agent", A)], {}, CFG_HEX,
                "certified-fact", [A])
    check("record/rejects-bad-status", False, "no raise")
except ValueError:
    check("record/rejects-bad-status", True)

# -- store roundtrip ----------------------------------------------
root = tempfile.mkdtemp(prefix="tl-rel-")
tl = TLStore(root, create=True, lease_owner="test-relations")
try:
    rep = ingest_docs(tl, [("d1", "alpha one two three four"),
                           ("d2", "beta five six seven eight")], emb)
    check("ingest/atoms", rep["n_atoms"] == 2, rep)
    pinned0 = tl.pin()
    idx0 = NarrowIndex(tl, pinned0)
    atoms0 = dict(idx0.atoms)
    holons0 = {k: sorted(v["members"]) for k, v in idx0.holons.items()}
    aids = sorted(idx0.atoms.keys())
    check("ingest/two-atoms", len(aids) == 2, aids)

    rec_attr = make_record(
        "supports", [("source", aids[0]), ("target", aids[1])],
        {"negated": False, "condition": None}, CFG,
        SOURCE_ATTRIBUTED, [aids[0], aids[1]],
        claim_text="d1 slice verbatim")
    rec_prop = make_record(
        "causes", [("agent", aids[0]), ("patient", aids[1])],
        {"negated": False, "unresolved": "conditional scope "
         "unrepresentable; see grounding"}, CFG, PROPOSED,
        [aids[0]])
    check("record/ids-differ",
          rec_attr["relation"] != rec_prop["relation"])
    check("record/cfg-bound",
          rec_attr["extractor_config_id"] == CFG_HEX)

    op_ids = commit_relations(tl, [rec_attr, rec_prop])
    check("commit/two-ops", len(op_ids) == 2, op_ids)

    pinned = tl.pin()
    rels = read_relations(tl, pinned)
    check("read/two-records", len(rels) == 2, sorted(rels))
    got_prop = rels[rec_prop["relation"]]["record"]
    check("read/status-preserved", got_prop["status"] == PROPOSED,
          got_prop["status"])
    check("read/unresolved-mark",
          eligible(got_prop, set(aids),
                   set(rels))["unresolved"] is not None)

    live = set(aids)
    vis = set(rels)
    e_attr = eligible(rels[rec_attr["relation"]]["record"], live,
                      vis)
    check("elig/live-eligible",
          e_attr == {"eligible": True,
                     "status": SOURCE_ATTRIBUTED, "reasons": [],
                     "unresolved": None}, e_attr)
    e_prop = eligible(got_prop, live, vis)
    check("elig/proposed-stays-proposed",
          e_prop["eligible"] and e_prop["status"] == PROPOSED,
          e_prop)
    e_dead = eligible(rels[rec_attr["relation"]]["record"],
                      {aids[0]}, vis)
    check("elig/retired-grounding-ineligible",
          not e_dead["eligible"] and any(
              r.startswith("grounding-not-live")
              for r in e_dead["reasons"]), e_dead)
    check("elig/status-verbatim-on-fail",
          e_dead["status"] == SOURCE_ATTRIBUTED, e_dead)

    deg = endpoint_degrees(rels.values())
    check("degrees/both-endpoints",
          deg == {aids[0]: 2, aids[1]: 2}, deg)

    # Narrow isolation: identical atoms/holons with relations in.
    idx1 = NarrowIndex(tl, pinned)
    same_atoms = set(idx1.atoms) == set(atoms0) and all(
        idx1.atoms[a]["doc_id"] == atoms0[a]["doc_id"]
        and idx1.atoms[a]["span"] == atoms0[a]["span"]
        for a in atoms0)
    same_holons = ({k: sorted(v["members"])
                    for k, v in idx1.holons.items()} == holons0)
    check("isolation/atoms-identical", same_atoms)
    check("isolation/holons-identical", same_holons)
finally:
    tl.close()

# -- query-path consumption (Q10.1/Q12.1/Q12.2 first use) -------------
QDOC_H = "hub alpha beta"
QDOC_AB = "shared duplicate text here"
QDOC_C = "lone wolf document"
QQUERY = "hub shared"
QVECS = {QDOC_H: [1.0, 0.0, 0.0, 0.0],
         QDOC_AB: [0.0, 1.0, 0.0, 0.0],
         QDOC_C: [0.0, 0.0, 1.0, 0.0],
         QQUERY: [0.7, 0.7, 0.0, 0.0]}


def qemb(texts):
    return [list(QVECS[t]) for t in texts]


def qemb1(q):
    return list(QVECS[q])


PHANTOM = "cc" * 32
UNRES_MARK = "scope unrepresentable; see grounding"

qroot = tempfile.mkdtemp(prefix="tl-relq-")
qtl = TLStore(qroot, create=True, lease_owner="test-relations-qpath")
try:
    qrep = ingest_docs(qtl, [("docH", QDOC_H), ("docA", QDOC_AB),
                             ("docB", QDOC_AB), ("docC", QDOC_C)],
                       qemb)
    check("qpath/ingest-4-atoms", qrep["n_atoms"] == 4, qrep)
    qpin0 = qtl.pin()
    qidx0 = NarrowIndex(qtl, qpin0)
    by_doc = {}
    for _aid, _a in qidx0.atoms.items():
        by_doc.setdefault(_a["doc_id"], []).append(_aid)
    check("qpath/one-atom-per-doc",
          all(len(v) == 1 for v in by_doc.values()), by_doc)
    h_atom, a_atom = by_doc["docH"][0], by_doc["docA"][0]
    b_atom, c_atom = by_doc["docB"][0], by_doc["docC"][0]
    check("qpath/dup-text-distinct-ids",
          a_atom != b_atom
          and qidx0.atom_text[a_atom] == qidx0.atom_text[b_atom])

    dos0, rec0 = NarrowQuery(qtl, qidx0, qemb1).run(QQUERY)
    check("qpath/pre-run-complete",
          rec0["execution"]["status"] == "complete",
          rec0["execution"])

    qr1 = make_record("links",
                      [("source", h_atom), ("target", a_atom)],
                      {"negated": True, "scope": "edge"}, CFG,
                      SOURCE_ATTRIBUTED, [h_atom, a_atom])
    qr2 = make_record("links",
                      [("source", h_atom), ("target", b_atom)],
                      {"negated": False}, CFG, SOURCE_ATTRIBUTED,
                      [h_atom, b_atom])
    qr3 = make_record("links",
                      [("source", a_atom), ("target", PHANTOM)],
                      {"negated": False}, CFG, SOURCE_ATTRIBUTED,
                      [a_atom])
    qr4 = make_record("links",
                      [("source", h_atom), ("target", c_atom)],
                      {"negated": False, "unresolved": UNRES_MARK},
                      CFG, PROPOSED, [h_atom, c_atom])
    commit_relations(qtl, [qr1, qr2, qr3, qr4])
    check("qpath/pre-pin-sees-no-relations",
          read_relations(qtl, qpin0) == {})

    qpin1 = qtl.pin()
    qidx1 = NarrowIndex(qtl, qpin1)
    view = relquery.load(qtl, qpin1, set(qidx1.atoms))
    check("qpath/visible-4", len(view.visible) == 4,
          sorted(view.visible))
    check("qpath/eligible-3", len(view.eligible) == 3,
          sorted(view.eligible))
    check("qpath/r3-ineligible-reason",
          any(r.startswith("endpoint-unresolved")
              for r in view.reasons.get(qr3["relation"], [])),
          view.reasons)
    check("qpath/proposed-eligible-status-kept",
          view.eligible[qr4["relation"]]["status"] == PROPOSED)
    check("qpath/degrees-eligible-only",
          view.degrees == {h_atom: 3, a_atom: 1, b_atom: 1,
                           c_atom: 1},
          view.degrees)
    check("qpath/scope-differs-for-dups",
          relquery.collapse_sig(a_atom, view.scope)
          != relquery.collapse_sig(b_atom, view.scope))
    check("qpath/scope-empty-untouched",
          relquery.collapse_sig("00" * 32, view.scope) == ())
    check("qpath/unresolved-endpoints",
          view.unresolved == {h_atom: UNRES_MARK,
                             c_atom: UNRES_MARK},
          view.unresolved)
    check("qpath/hub-factor-edges",
          relquery.hub_factor("00" * 32, view.degrees, 0.5) == 1.0
          and relquery.hub_factor(h_atom, view.degrees, 0) == 1.0
          and math.isclose(relquery.hub_factor(h_atom, view.degrees,
                                               0.5),
                           3 ** -0.5, rel_tol=1e-12))

    # Flag-off identical: default cfg with relations committed.
    dos1, rec1 = NarrowQuery(qtl, qidx1, qemb1).run(QQUERY)

    def _norm_dos(dos):
        dos = json.loads(json.dumps(dos, sort_keys=True))
        for e in dos["entries"]:  # pin advanced on relation commits
            e.pop("resolving_generation", None)
        return dos

    check("qpath/off-entries-identical",
          _norm_dos(dos1) == _norm_dos(dos0),
          f"{dos1} vs {dos0}")

    def _norm(rec):
        rec = json.loads(json.dumps(rec, sort_keys=True))
        rec.pop("pinned_generation", None)
        rec.get("metrics", {}).pop("T_ms", None)
        return rec

    check("qpath/off-receipt-identical",
          _norm(rec1) == _norm(rec0))
    dosE, recE = NarrowQuery(
        qtl, qidx1, qemb1,
        cfg={"REL_HUB_SUPPRESS": False, "REL_HUB_ALPHA": "bogus",
             "REL_QUALIFIERS": False}).run(QQUERY)
    check("qpath/explicit-off-identical-junk-alpha",
          dosE == dos1 and _norm(recE) == _norm(rec1))
    check("qpath/off-no-rel-key", "rel_consumption" not in rec1)
    check("qpath/off-no-unresolved-marks",
          all("unresolved" not in e.get("marks", {})
              for e in dos1["entries"]))

    # Hub suppression: H damped by 3^-0.5, spokes untouched.
    dosH, recH = NarrowQuery(
        qtl, qidx1, qemb1, cfg={"REL_HUB_SUPPRESS": True}).run(
        QQUERY)
    off_scores = {e["atom_id"]: e["emitted_score"]
                  for e in dos1["entries"]}
    on_scores = {e["atom_id"]: e["emitted_score"]
                 for e in dosH["entries"]}
    check("qpath/hub-h-damped",
          math.isclose(on_scores[h_atom],
                       off_scores[h_atom] * (3 ** -0.5),
                       rel_tol=1e-12),
          (off_scores.get(h_atom), on_scores.get(h_atom)))
    check("qpath/hub-same-admitted",
          set(on_scores) == set(off_scores),
          (sorted(off_scores), sorted(on_scores)))
    check("qpath/hub-spokes-untouched",
          all(a not in on_scores or
              math.isclose(on_scores[a], off_scores[a],
                           rel_tol=1e-12)
              for a in off_scores if a != h_atom),
          (off_scores, on_scores))
    rdiag = recH.get("rel_consumption", {})
    check("qpath/hub-diag",
          rdiag.get("relations_visible") == 4
          and rdiag.get("relations_eligible") == 3
          and rdiag.get("relations_ineligible") == 1
          and rdiag.get("hub_alpha") == 0.5
          and rdiag.get("hub_touched") == 1
          and rdiag.get("unresolved_candidates") == 2, rdiag)
    try:
        NarrowQuery(qtl, qidx1, qemb1,
                    cfg={"REL_HUB_SUPPRESS": True,
                         "REL_HUB_ALPHA": "bogus"}).run(QQUERY)
        check("qpath/hub-bad-alpha-raises", False, "no raise")
    except ValueError:
        check("qpath/hub-bad-alpha-raises", True)

    # Qualifier plumbing: dups survive, mark rides, flags flip.
    dosQ, recQ = NarrowQuery(
        qtl, qidx1, qemb1, cfg={"REL_QUALIFIERS": True}).run(
        QQUERY)
    docs_off = sorted(e["doc_id"] for e in dos1["entries"])
    docs_on = sorted(e["doc_id"] for e in dosQ["entries"])
    check("qpath/off-collapses-dup",
          docs_off.count("docA") + docs_off.count("docB") == 1,
          docs_off)
    check("qpath/qual-dups-survive",
          "docA" in docs_on and "docB" in docs_on, docs_on)
    h_entry = next(e for e in dosQ["entries"]
                   if e["atom_id"] == h_atom)
    check("qpath/qual-unresolved-mark",
          h_entry["marks"].get("unresolved") == UNRES_MARK,
          h_entry["marks"])
    c_entry = next(e for e in dosQ["entries"]
                   if e["atom_id"] == c_atom)
    check("qpath/qual-unresolved-mark-dense-only",
          c_entry["marks"].get("unresolved") == UNRES_MARK,
          c_entry["marks"])
    check("qpath/qual-flags",
          recQ["flags"].get("qualifier_Q12.1") is True
          and recQ["flags"].get("unresolved_Q12.2") is True
          and "qualifier_Q12.1" not in recQ["flags_not_produced"]
          and "unresolved_Q12.2" not in recQ["flags_not_produced"],
          recQ["flags"])
    check("qpath/hub-alone-keeps-fnp",
          "qualifier_Q12.1" in recH["flags_not_produced"]
          and "unresolved_Q12.2" in recH["flags_not_produced"])
finally:
    qtl.close()

# -- mechanism batch (Q12.3-mech pairs + Q12.1(c) MMR, R3-B) ----
MDOC_X = "context hub words"
MDOC_PQ = "claim text here"
MDOC_U = "unrelated matter"
MDOC_W = "murky conditional words"
MQUERY = "context claim"
MVECS = {MDOC_X: [1.0, 0.0, 0.0, 0.0],
         MDOC_PQ: [0.0, 1.0, 0.0, 0.0],
         MDOC_U: [0.0, 0.0, 1.0, 0.0],
         MDOC_W: [0.0, 0.0, 0.0, 1.0],
         MQUERY: [0.7, 0.7, 0.0, 0.0]}


def memb(texts):
    return [list(MVECS[t]) for t in texts]


def memb1(q):
    return list(MVECS[q])


MPHANTOM = "dd" * 32
MUNRES = "scope unrepresentable; see grounding"

mroot = tempfile.mkdtemp(prefix="tl-relm-")
mtl = TLStore(mroot, create=True, lease_owner="test-relations-mech")
try:
    mrep = ingest_docs(mtl, [("docX", MDOC_X), ("docP", MDOC_PQ),
                             ("docQ", MDOC_PQ), ("docU", MDOC_U),
                             ("docW", MDOC_W)], memb)
    check("mech/ingest-5-atoms", mrep["n_atoms"] == 5, mrep)
    mpin0 = mtl.pin()
    midx0 = NarrowIndex(mtl, mpin0)
    mby_doc = {}
    for _aid, _a in midx0.atoms.items():
        mby_doc.setdefault(_a["doc_id"], []).append(_aid)
    mX, mP = mby_doc["docX"][0], mby_doc["docP"][0]
    mQ, mU = mby_doc["docQ"][0], mby_doc["docU"][0]
    mW = mby_doc["docW"][0]

    mdos0, mrec0 = NarrowQuery(mtl, midx0, memb1).run(MQUERY)
    check("mech/pre-run-complete",
          mrec0["execution"]["status"] == "complete",
          mrec0["execution"])

    mr_aff = make_record(
        "links", [("source", mX), ("target", mP)],
        {"negated": False, "scope": "edge"}, CFG,
        SOURCE_ATTRIBUTED, [mX, mP])
    mr_neg = make_record(
        "links", [("source", mX), ("target", mQ)],
        {"negated": True, "scope": "edge"}, CFG,
        SOURCE_ATTRIBUTED, [mX, mQ])
    mr_other = make_record(
        "links", [("source", mX), ("target", mU)],
        {"negated": True, "scope": "target"}, CFG,
        SOURCE_ATTRIBUTED, [mX, mU])
    mr_unres = make_record(
        "links", [("source", mX), ("target", mW)],
        {"negated": False, "scope": "edge",
         "unresolved": MUNRES},
        CFG, PROPOSED, [mX, mW])
    mr_ph = make_record(
        "links", [("source", mX), ("target", MPHANTOM)],
        {"negated": True, "scope": "edge"}, CFG,
        SOURCE_ATTRIBUTED, [mX])
    commit_relations(mtl, [mr_aff, mr_neg, mr_other, mr_unres,
                           mr_ph])

    mpin1 = mtl.pin()
    midx1 = NarrowIndex(mtl, mpin1)
    mview = relquery.load(mtl, mpin1, set(midx1.atoms))
    check("mech/visible-5-eligible-4",
          len(mview.visible) == 5 and len(mview.eligible) == 4,
          (sorted(mview.visible), sorted(mview.eligible)))

    mpair = tuple(sorted([mP, mQ]))
    muniv = set(midx1.atoms)
    check("mech/pairs-one",
          relquery.identify_pairs(mview, muniv) == [mpair],
          relquery.identify_pairs(mview, muniv))
    check("mech/pairs-scope-mismatch-excluded",
          all(mU not in pr
              for pr in relquery.identify_pairs(mview, muniv)))
    check("mech/pairs-unresolved-excluded",
          all(mW not in pr and mX not in pr
              for pr in relquery.identify_pairs(mview, muniv)))
    # mr_ph is the ineligible twin of mr_neg's opposition: were it
    # consumed, (mP, MPHANTOM) would pair. It must not.
    check("mech/pairs-ineligible-excluded",
          relquery.identify_pairs(
              mview, muniv | {MPHANTOM}) == [mpair])
    check("mech/pairs-empty-universe",
          relquery.identify_pairs(mview, set()) == [])
    check("mech/pairs-sorted",
          relquery.identify_pairs(mview, muniv)
          == sorted(relquery.identify_pairs(mview, muniv)))

    check("mech/pkey-distinct-for-pair",
          relquery.partition_key(mP, mview.scope,
                                 mview.unresolved) is not None
          and relquery.partition_key(mP, mview.scope,
                                      mview.unresolved)
          != relquery.partition_key(mQ, mview.scope,
                                     mview.unresolved))
    check("mech/pkey-pool",
          relquery.partition_key(mW, mview.scope,
                                 mview.unresolved) is None
          and relquery.partition_key(mX, mview.scope,
                                      mview.unresolved) is None
          and relquery.partition_key("00" * 32, mview.scope,
                                      mview.unresolved) is None)

    # Flag-off identical with mechanism relations committed.
    mdos1, mrec1 = NarrowQuery(mtl, midx1, memb1).run(MQUERY)

    def _mnorm_dos(dos):
        dos = json.loads(json.dumps(dos, sort_keys=True))
        for e in dos["entries"]:
            e.pop("resolving_generation", None)
        return dos

    def _mnorm(rec):
        rec = json.loads(json.dumps(rec, sort_keys=True))
        rec.pop("pinned_generation", None)
        rec.get("metrics", {}).pop("T_ms", None)
        return rec

    check("mech/off-entries-identical",
          _mnorm_dos(mdos1) == _mnorm_dos(mdos0))
    check("mech/off-receipt-identical",
          _mnorm(mrec1) == _mnorm(mrec0))
    check("mech/off-no-rel-key", "rel_consumption" not in mrec1)

    mdosQ, mrecQ = NarrowQuery(
        mtl, midx1, memb1, cfg={"REL_QUALIFIERS": True}).run(
        MQUERY)
    mdiag = mrecQ.get("rel_consumption", {})
    check("mech/on-rel-diag",
          mdiag.get("pairs_identified") == 1
          and mdiag.get("pairs_jointly_admitted") == 1
          and mdiag.get("mmr_partitions") == 4
          and mdiag.get("relations_eligible") == 4, mdiag)
    check("mech/on-pair-seated",
          {mP, mQ} <= {e["atom_id"] for e in mdosQ["entries"]},
          [e["doc_id"] for e in mdosQ["entries"]])
    check("mech/joint-flag",
          mrecQ["flags"].get("joint_preservation_Q12.3") is True
          and "joint_preservation_Q12.3"
          not in mrecQ["flags_not_produced"],
          mrecQ["flags"])

    # Counterpart rides below tau (settled admit branch).
    _mon = {e["atom_id"]: e["emitted_score"]
            for e in mdosQ["entries"]}
    check("mech/pair-scores-differ", _mon[mP] != _mon[mQ],
          (_mon[mP], _mon[mQ]))
    _mlo = min(_mon[mP], _mon[mQ])
    _mhi = max(_mon[mP], _mon[mQ])
    _mtau = (_mlo + _mhi) / 2
    mdosT, mrecT = NarrowQuery(
        mtl, midx1, memb1,
        cfg={"REL_QUALIFIERS": True, "TAU_SEL": _mtau}).run(
        MQUERY)
    _tad = {e["atom_id"]: e["emitted_score"]
            for e in mdosT["entries"]}
    check("mech/counterpart-rides-below-tau",
          mP in _tad and mQ in _tad
          and min(_tad[mP], _tad[mQ]) < _mtau, _tad)
    _treasons = {p["cause"] for p in mrecT["partials"]}
    check("mech/tau-defers-only-below-tau",
          _treasons == {"selection-deferred:below-tau"}
          and any(p["scope"] == f"candidate:{mU[:16]}"
                  for p in mrecT["partials"]), mrecT["partials"])

    # Binding cap defers both, never one-sided.
    mdosC, mrecC = NarrowQuery(
        mtl, midx1, memb1,
        cfg={"REL_QUALIFIERS": True, "MAX_ENTRIES": 1}).run(
        MQUERY)
    _cad = {e["atom_id"] for e in mdosC["entries"]}
    _cdef = {p["scope"]: p["cause"] for p in mrecC["partials"]}
    check("mech/overflow-defers-both",
          _cad == {mX}
          and _cdef.get(f"candidate:{mP[:16]}")
          == "selection-deferred:pair-overflow-cap"
          and _cdef.get(f"candidate:{mQ[:16]}")
          == "selection-deferred:pair-overflow-cap",
          (_cad, _cdef))
    check("mech/overflow-never-onesided",
          not (_cad & {mP, mQ}) or ({mP, mQ} <= _cad), _cad)

    # Prune-cut pair: explicit deferral, never silent seating.
    mdosB, mrecB = NarrowQuery(
        mtl, midx1, memb1,
        cfg={"REL_QUALIFIERS": True, "PRUNE_SPLIT": False,
             "PRUNE_CAP": 2}).run(MQUERY)
    _bdef = {p["scope"]: p["cause"] for p in mrecB["partials"]}
    check("mech/prune-break-explicit",
          _bdef.get(f"candidate:{mP[:16]}")
          == "selection-deferred:counterpart-unidentified"
          and mQ not in {e["atom_id"]
                         for e in mdosB["entries"]},
          (_bdef, [e["doc_id"] for e in mdosB["entries"]]))

    # Hub flag stays orthogonal: no pairs, plain MMR.
    mdosH, mrecH = NarrowQuery(
        mtl, midx1, memb1, cfg={"REL_HUB_SUPPRESS": True}).run(
        MQUERY)
    _hdiag = mrecH.get("rel_consumption", {})
    check("mech/hub-keeps-empty-trigger",
          _hdiag.get("pairs_identified") == 0
          and _hdiag.get("mmr_partitions") is None
          and "joint_preservation_Q12.3"
          in mrecH["flags_not_produced"], _hdiag)

    # Combined flags compose: hub damping + pairs together.
    mdosB2, mrecB2 = NarrowQuery(
        mtl, midx1, memb1,
        cfg={"REL_HUB_SUPPRESS": True,
             "REL_QUALIFIERS": True}).run(MQUERY)
    _bon = {e["atom_id"]: e["emitted_score"]
            for e in mdosB2["entries"]}
    _bdiag = mrecB2.get("rel_consumption", {})
    check("mech/combined-hub-and-pairs",
          _bdiag.get("pairs_identified") == 1
          and _bdiag.get("hub_alpha") == 0.5
          and math.isclose(_bon[mX], _mon[mX] * (4 ** -0.5),
                           rel_tol=1e-12)
          and math.isclose(_bon[mP], _mon[mP], rel_tol=1e-12)
          and {mP, mQ} <= set(_bon), (_bon, _bdiag))
finally:
    mtl.close()

# -- synthetic opposition units (no store) ---------------------------
mA, mB, mC, mD = "aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32


def _mkview(specs, unres=frozenset(), inter=False):
    elig = {}
    for i, (rt, eps, quals) in enumerate(specs):
        elig[f"r{i}"] = {"rel_type": rt, "endpoints": eps,
                         "interchangeable": inter,
                         "qualifiers": quals}
    return relquery.RelView({}, elig, {}, {}, {},
                            {a: "m" for a in unres})


def _ord(*aids):
    return [["e%d" % i, a] for i, a in enumerate(aids)]


_aff = {"negated": False, "scope": "edge"}
_neg = {"negated": True, "scope": "edge"}
check("mech/unit-opposition-pairs",
      relquery.identify_pairs(
          _mkview([("links", _ord(mA, mB), _aff),
                   ("links", _ord(mA, mC), _neg)]),
          {mA, mB, mC}) == [(mB, mC)])
check("mech/unit-scope-mismatch",
      relquery.identify_pairs(
          _mkview([("links", _ord(mA, mB), _aff),
                   ("links", _ord(mA, mC),
                    {"negated": True, "scope": "target"})]),
          {mA, mB, mC}) == [])
check("mech/unit-type-mismatch",
      relquery.identify_pairs(
          _mkview([("links", _ord(mA, mB), _aff),
                   ("other", _ord(mA, mC), _neg)]),
          {mA, mB, mC}) == [])
check("mech/unit-context-mismatch",
      relquery.identify_pairs(
          _mkview([("links", _ord(mD, mB), _aff),
                   ("links", _ord(mA, mC), _neg)]),
          {mA, mB, mC, mD}) == [])
check("mech/unit-same-endpoint-nopair",
      relquery.identify_pairs(
          _mkview([("links", _ord(mA, mB), _aff),
                   ("links", _ord(mA, mB), _neg)]),
          {mA, mB}) == [])
check("mech/unit-unresolved-veto",
      relquery.identify_pairs(
          _mkview([("links", _ord(mA, mB), _aff),
                   ("links", _ord(mA, mC), _neg)],
                  unres={mB}),
          {mA, mB, mC}) == [])
check("mech/unit-absent-negated-affirms",
      relquery.identify_pairs(
          _mkview([("links", _ord(mA, mB), {"scope": "edge"}),
                   ("links", _ord(mA, mC), _neg)]),
          {mA, mB, mC}) == [(mB, mC)])
check("mech/unit-interchangeable",
      relquery.identify_pairs(
          _mkview([("cooccurs", [mA, mB], _aff),
                   ("cooccurs", [mA, mC], _neg)],
                  inter=True),
          {mA, mB, mC}) == [(mB, mC)])

# -- partitioned-MMR pure checks (no store) --------------------------
_rng = random.Random(11)
_vc = [f"v{i}" for i in range(12)]
_vv = {a: [_rng.uniform(-1, 1) for _ in range(8)] for a in _vc}
_cc = [(a, _rng.random()) for a in _vc]


def _vcos(va, vb):
    n = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    return n / (na * nb) if na > 0 and nb > 0 else 0.0


_vsim = {a: {b: _vcos(_vv[a], _vv[b]) for b in _vc}
         for a in _vc}
check("mech/mmr-single-pool-identity",
      relquery.partitioned_mmr(_cc, lambda a, b: _vsim[a][b],
                               0.8, {}, {})
      == mmr_order_matrix(_cc, lambda a, b: _vsim[a][b], 0.8,
                          len(_cc))
      and relquery.partitioned_mmr(
          _cc, lambda a, b: _vsim[a][b], 0.8, {}, {},
          sim_cap=0.3)
      == mmr_order_matrix(_cc, lambda a, b: _vsim[a][b], 0.8,
                          len(_cc), sim_cap=0.3))

m_a1, m_a2, m_b1, m_c1 = "a1" * 32, "a2" * 32, "b1" * 32, "c1" * 32
_mscope = {m_a1: [("ra", _aff)], m_a2: [("ra", _aff)],
           m_b1: [("rn", _neg)]}
_mcands = [(m_a1, 1.0), (m_a2, 0.9), (m_b1, 0.95),
           (m_c1, 0.5)]
check("mech/mmr-score-merge",
      relquery.partitioned_mmr(_mcands, lambda a, b: 0.0, 0.8,
                               _mscope, {})
      == [m_a1, m_b1, m_a2, m_c1])

p_a, p_b, p_c = "pa" * 32, "pb" * 32, "pc" * 32
_pscope = {p_a: [("ra", _aff)], p_b: [("rn", _neg)]}


def _psim(a, b):
    return 0.99 if {a, b} == {p_a, p_b} else 0.0


_pcands = [(p_a, 1.0), (p_b, 0.99), (p_c, 0.8)]
_plain = mmr_order_matrix(_pcands, _psim, 0.8, 3)
_part = relquery.partitioned_mmr(_pcands, _psim, 0.8,
                                 _pscope, {})
check("mech/mmr-protects-pair",
      _plain == [p_a, p_c, p_b] and _part == [p_a, p_b, p_c],
      (_plain, _part))

t_p, t_a = "tp" * 32, "ta" * 32
_tscope = {t_a: [("ra", _aff)]}
_tord = relquery.partitioned_mmr([(t_a, 0.5), (t_p, 0.5)],
                                 lambda a, b: 0.0, 0.8,
                                 _tscope, {})
check("mech/mmr-tie-pool-first-repeatable",
      _tord == [t_p, t_a]
      and relquery.partitioned_mmr([(t_a, 0.5), (t_p, 0.5)],
                                   lambda a, b: 0.0, 0.8,
                                   _tscope, {}) == _tord,
      _tord)

_mprobe = ("import sys; sys.path.insert(0, %r); "
           "from tlsys import relquery as R; "
           "A='aa'*32; B='bb'*32; C='cc'*32; "
           "e1={'rel_type':'links','endpoints':[['s',A],['t',B]],"
           "'interchangeable':False,'qualifiers':"
           "{'negated':False,'scope':'edge'}}; "
           "e2={'rel_type':'links','endpoints':[['s',A],['t',C]],"
           "'interchangeable':False,'qualifiers':"
           "{'negated':True,'scope':'edge'}}; "
           "v=R.RelView({},{'r1':e1,'r2':e2},{},{},{},{}); "
           "print(R.identify_pairs(v,{A,B,C})); "
           "s={B:[('r1',e1['qualifiers'])],"
           "C:[('r2',e2['qualifiers'])]}; "
           "print(R.partitioned_mmr([(B,0.5),(C,0.5),(A,0.4)],"
           "lambda a,b:0.0,0.8,s,{}))")
_mhere = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."))
_mouts = set()
for _seed in ("0", "1", "42"):
    _env = dict(os.environ, PYTHONHASHSEED=_seed)
    _p = subprocess.run([sys.executable, "-c", _mprobe % _mhere],
                        capture_output=True, text=True, env=_env)
    _mouts.add((_p.returncode, _p.stdout.strip()))
check("mech/xproc-deterministic",
      len(_mouts) == 1 and next(iter(_mouts))[0] == 0,
      f"{_mouts}")

print(f"done: {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
