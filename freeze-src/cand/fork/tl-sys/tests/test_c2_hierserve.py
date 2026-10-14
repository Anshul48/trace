"""C2 Lane R: facade-native HierQuery port (guard + traffic accounting).

Covers tlsys.hierserve (FacadeGuard, MappingGuard, HierServe):

- Guard: HierQuery guided/flat/bounded touch only the section 3.4 /
  contract section 5 facade surface (anything else raises); the port is
  read-only (mutators excluded, writes refused).
- Differential vs direct HierQuery over the same index: rows + reports
  normalized-equal on the reference AND segmented backends, for guided
  exact, guided bounded, flat, retirement-active, no-hierarchy and
  degenerate (zero-budget) shapes.
- Delegation evidence: bounded nomination delegates to the facade maps
  (nomination_maps touched, maps_built False on repeat); the reference
  backend takes the build-as-before fallback (triple touched).
- Traffic: keyed vs full-scan mapping traffic is counted per call; the
  per-call full seg-dict materialization is NAMED as the residual N-term
  (facade copies; index.py is outside this lane's write area).

Deterministic fake encoder; scratch stores under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_hierserve.py
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
from tlsys.query import HierQuery  # noqa: E402
from tlsys.maint import organize_segments  # noqa: E402
from tlsys.lifecycle import retire_docs  # noqa: E402
from tlsys.hierserve import (FACADE_ATTRS, FacadeGuard,  # noqa: E402
                             HierServe)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def canon(obj):
    return json.dumps(obj, sort_keys=True, default=str)


def run_of(word, n, start=0):
    return " ".join(f"{word}-{i}" for i in range(start, start + n))


DIM = 8


def pad(v):
    return [float(x) for x in v] + [0.0] * (DIM - len(v))


V_SPORT = pad([1.0, 0.0, 0.0, 0.0])
V_MED = pad([0.0, 1.0, 0.0, 0.0])
V_OUT = pad([0.0, 0.0, 1.0, 0.0])


def emb(texts):
    out = []
    for t in texts:
        votes = [(t.count("sport"), V_SPORT), (t.count("medic"), V_MED)]
        votes.sort(key=lambda kv: -kv[0])
        out.append(list(votes[0][1]) if votes[0][0]
                   else list(V_OUT))
    return out


def emb1(q):
    return emb([q])[0]


def norm_hier(rows, report):
    # Rows carry verified text/spans (compared exactly); the report's
    # nomination block carries maps_built booleans (compared exactly).
    # Nothing wall-clock-bearing leaves HierQuery; full equality.
    return canon((rows, report))


def check_guided_parity(tag, tl, index, query, **kw):
    direct = HierQuery(tl, index, emb1)
    served = HierServe(tl, index, emb1)
    rows_d, rep_d = direct.guided(query, **kw)
    rows_s, rep_s, traffic = served.guided(query, **kw)
    check(f"{tag}/guided-equal",
          norm_hier(rows_d, rep_d) == norm_hier(rows_s, rep_s),
          f"{tag} guided diverges")
    return rows_s, rep_s, traffic, served


def check_flat_parity(tag, tl, index, query, budget, **kw):
    direct = HierQuery(tl, index, emb1)
    served = HierServe(tl, index, emb1)
    rows_d, rep_d = direct.flat(query, budget, **kw)
    rows_s, rep_s, traffic = served.flat(query, budget, **kw)
    check(f"{tag}/flat-equal",
          norm_hier(rows_d, rep_d) == norm_hier(rows_s, rep_s),
          f"{tag} flat diverges")
    return rows_s, rep_s, traffic, served


root = tempfile.mkdtemp(prefix="tl-hierserve-")
tl = TLStore(os.path.join(root, "store"), create=True,
             lease_owner="test-c2-hierserve")
try:
    doc_multi = " ".join([run_of("sport", 150, 0), run_of("medic", 150, 0),
                          run_of("sport", 150, 1000),
                          run_of("medic", 150, 1000)])
    docs = [("doc-multi", doc_multi),
            ("doc-sport-b", run_of("sport", 150, 5000)),
            ("doc-med-b", run_of("medic", 150, 6000)),
            ("doc-out", run_of("outlier", 150, 8000))]
    rep = ingest_docs(tl, docs, emb)
    check("ingest/counts", rep["n_atoms"] >= 4, rep)
    org = organize_segments(tl)
    check("ingest/organized", sorted(org["organized"])
          == sorted(d for d, _t in docs), org)
    pin1 = tl.pin()
    ref1 = ReferenceNarrowIndex(tl, pin1)
    fac1 = NarrowIndex(tl, pin1)
    check("ingest/hierarchy",
          len(ref1.seg_leaves) > 0 and len(ref1.seg_parents) > 0
          and len(fac1.seg_leaves) == len(ref1.seg_leaves)
          and len(fac1.seg_parents) == len(ref1.seg_parents),
          (len(ref1.seg_leaves), len(ref1.seg_parents)))

    Q = "sport medic athletics"
    # -- guided exact + flat, both backends -------------------------
    for tag, index in (("ref", ref1), ("fac", fac1)):
        rows, report, traffic, _s = check_guided_parity(
            f"{tag}/exact", tl, index, Q, top_parents=2,
            top_children=4, top_atoms=10)
        check(f"{tag}/exact-status",
              report["status"] == "ok" and len(rows) > 0, report)
        rows_f, rep_f, tr_f, _s = check_flat_parity(
            tag, tl, index, Q, 4, top_atoms=10)
        check(f"{tag}/flat-status",
              rep_f["status"] == "ok", rep_f)
    # -- bounded nomination, both backends --------------------------
    rows_rb, rep_rb, tr_rb, served_rb = check_guided_parity(
        "ref/bounded", tl, ref1, Q, top_parents=2, top_children=4,
        top_atoms=10, parent_budget=1)
    check("ref/bounded-mode",
          rep_rb["nomination"]["mode"] == "bounded-lexical"
          and rep_rb["nomination"]["maps_built"] is True, rep_rb)
    rows_fb, rep_fb, tr_fb, served_fb = check_guided_parity(
        "fac/bounded", tl, fac1, Q, top_parents=2, top_children=4,
        top_atoms=10, parent_budget=1)
    check("fac/bounded-mode",
          rep_fb["nomination"]["mode"] == "bounded-lexical"
          and rep_fb["nomination"]["maps_built"] is True, rep_fb)
    # Delegation evidence: facade path touches nomination_maps (the
    # view's incrementally maintained maps); the reference path takes
    # the build-as-before fallback (triple-keyed, no delegation).
    check("fac/delegates",
          "nomination_maps" in tr_fb, sorted(tr_fb))
    check("ref/fallback",
          "nomination_maps" in tr_rb
          and "triple" in served_rb.touched_surface(),
          (sorted(tr_rb), sorted(served_rb.touched_surface())))
    # Repeat bounded call on the held serve: no map rebuild on either
    # backend (facade: shared maintained maps; reference: key cache).
    _rows2, rep2, tr2 = served_fb.guided(
        Q, top_parents=2, top_children=4, top_atoms=10,
        parent_budget=1)
    check("fac/no-rebuild",
          rep2["nomination"]["maps_built"] is False, rep2)
    _rows3, rep3, tr3 = served_rb.guided(
        Q, top_parents=2, top_children=4, top_atoms=10,
        parent_budget=1)
    check("ref/no-rebuild",
          rep3["nomination"]["maps_built"] is False, rep3)
    # Guard surface: everything touched is facade surface, and the
    # touched subset is minimal and reported.
    touched_fac = served_fb.touched_surface()
    touched_ref = served_rb.touched_surface()
    check("guard/facade-only",
          touched_fac <= FACADE_ATTRS
          and touched_ref <= FACADE_ATTRS,
          (sorted(touched_fac), sorted(touched_ref)))
    print(f"info touched/fac={sorted(touched_fac)}")
    print(f"info touched/ref={sorted(touched_ref)}")
    # Traffic shape: exact guided materializes full seg dicts per call
    # (the NAMED residual N-term: facade seg_leaves/seg_parents return
    # full-dict copies; index.py is outside Lane R's write area).
    _r, _rep, tr_exact = HierServe(tl, fac1, emb1).guided(
        Q, top_parents=2, top_children=4, top_atoms=10)
    check("traffic/seg-copies-named",
          tr_exact.get("seg_leaves", 0) >= 1
          and tr_exact.get("seg_parents", 0) >= 1
          and tr_exact.get("seg_parents.full_scan", 0) >= 1,
          tr_exact)
    print(f"info traffic/exact-guided={tr_exact}")
    check("traffic/member-keyed",
          tr_exact.get("atoms.full_scan", 0) == 0
          and tr_exact.get("holons.full_scan", 0) == 0,
          tr_exact)
    # Guard refusals: internals/mutators/writes fail closed.
    g = FacadeGuard(fac1)
    for bad in ("_build", "_build_bm25", "advance_to",
                "note_population_changed", "_view", "_pool"):
        try:
            getattr(g, bad)
            check(f"guard/refuses-{bad}", False, "no AttributeError")
        except AttributeError:
            check(f"guard/refuses-{bad}", True)
    try:
        g.atoms = {}
        check("guard/read-only", False, "write allowed")
    except AttributeError:
        check("guard/read-only", True)

    # -- retirement-active hierarchy --------------------------------
    rep_c = ingest_docs(tl, [("doc-med-b-v2",
                              run_of("medic", 150, 9000))], emb)
    check("ingest/correction", rep_c["n_atoms"] >= 1, rep_c)
    rrep = retire_docs(
        tl, ["doc-med-b"], reason="hs-correction",
        approvals={"doc-med-b": {"type": "user",
                                 "approval_id": "fixture-hs-retire"}})
    check("retire/report", rrep["retired"] == ["doc-med-b"],
          rrep)
    pin2 = tl.pin()
    ref2 = ReferenceNarrowIndex(tl, pin2)
    fac2 = NarrowIndex(tl, pin2)
    check("retire/tombstones",
          "doc-med-b" in fac2.retired_docs
          and "doc-med-b" in ref2.retired_docs
          and fac2.retired_aids == ref2.retired_aids
          and len(fac2.retired_aids) > 0,
          (fac2.retired_docs, len(fac2.retired_aids)))
    for tag, index in (("ref2", ref2), ("fac2", fac2)):
        check_guided_parity(f"{tag}/retired", tl, index, Q,
                            top_parents=2, top_children=4,
                            top_atoms=10)
        check_guided_parity(f"{tag}/retired-bounded", tl, index, Q,
                            top_parents=2, top_children=4,
                            top_atoms=10, parent_budget=1)
        check_flat_parity(f"{tag}/retired", tl, index, Q, 4,
                          top_atoms=10)
    _rr, rep_rr, _tr, _s = check_guided_parity(
        "x/retired-skipped", tl, ref2, Q, top_parents=4,
        top_children=8, top_atoms=50)
    print(f"info retired_skipped={rep_rr.get('retired_skipped')} "
          f"withheld={rep_rr.get('withheld')}")

    # -- no-hierarchy + degenerate shapes ---------------------------
    root_b = tempfile.mkdtemp(prefix="tl-hierserve-bare-")
    tl_b = TLStore(os.path.join(root_b, "store"), create=True,
                   lease_owner="test-c2-hierserve-bare")
    ingest_docs(tl_b, [("solo", "sport lonely unorganized text")],
                emb)
    pin_b = tl_b.pin()
    for tag, index in (("bare-ref",
                        ReferenceNarrowIndex(tl_b, pin_b)),
                       ("bare-fac", NarrowIndex(tl_b, pin_b))):
        rows, report, _tr, _s = check_guided_parity(
            tag, tl_b, index, "sport")
        check(f"{tag}/no-hierarchy",
              rows == [] and report["status"] == "no-hierarchy",
              report)
        rows_f, rep_f, _tr, _s = check_flat_parity(
            tag, tl_b, index, "sport", 4)
        check(f"{tag}/flat-empty",
              rows_f == []
              and rep_f["status"] in ("ok", "no-hierarchy"), rep_f)
    # Zero budgets are exact on both backends.
    for tag, index in (("ref1", ref1), ("fac1", fac1)):
        check_guided_parity(f"{tag}/zero", tl, index, Q,
                            top_parents=0, top_children=0,
                            top_atoms=0)
        check_flat_parity(f"{tag}/zero", tl, index, Q, 0,
                          top_atoms=0)
    try:
        tl_b.close()
    except Exception:
        pass
finally:
    try:
        tl.close()
    except Exception:
        pass

print(f"FAILS: {len(FAILS)} :: {FAILS}" if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
