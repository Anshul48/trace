"""M2 worker 2 (track B): relations/export G1/G3 qualification.

Source-path qualification (NOT predicate-only fixtures): every check
below runs through real product paths -- ingest_docs over source
texts, TLStore pins, NarrowIndex, NarrowQuery.run,
DossierQuery.run, relquery.traverse, export_store -- on scratch
stores. Corpus-scale source-grounded proofs with the pinned MiniLM
encoder live in tl-eval/evidence/m2-2026-10-06/trackB/; this file
pins the same behaviors at fixture scale and guards the exact
indexed relation/export contracts.

Covers:
  export relation disclosure (M2-B repair): healthy relation
    commits disclose honestly (counts + absent marker) instead of
    emitting spurious meta-missing errors and a false "no S-02
    relation records committed" claim; relation-free exports stay
    byte-identical to the legacy shape; validate_export IMPORTABLE.
  exclusion through real entry points: genuinely-absent endpoint /
    grounding ids (source-derived-but-never-committed, plus a real
    atom id committed in a DIFFERENT store) resolve ineligible with
    verbatim reasons, are never traversed / lateral-served /
    paired / emitted; Narrow OFF stays byte-identical pre/post
    commit; stale-index cross-pin serving is refused, never mixed.
  multi-hop at the frozen bound (M2B_FROZEN_HOPS=3):
    DossierQuery DOSSIER_SHAPE=relational + DOSSIER_REL_TRAVERSAL
    vetoes the hop-3 bridge at H=1/H=2 and serves it at H=3 with
    hop/via marks and traversal receipt keys; trav-H1 atom set
    equals the legacy lateral set.
  cross-topic + qualifier/opposing-pair assembly through the real
    Narrow/Dossier entry points (sections, lateral, identified +
    jointly-admitted pairs, unresolved mark riding).

Typed supplied relations throughout are analyst-labeled PROPOSED
records (no extraction claims). No tl-sys file outside
relations.py/relquery.py/dossier.py/export.py is touched by M2-B.

Run: HF_HOME=<repo>/local-data/hf-cache HF_HUB_OFFLINE=1
     PYTHONHASHSEED=0 tl-sys/.venv/bin/python
     tl-sys/tests/test_m2b_relexp.py
"""
import hashlib
import json
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys import relquery  # noqa: E402
from tlsys.relations import (PROPOSED, commit_relations,  # noqa: E402
                             get_index, invalidate_rel_index,
                             make_record)
from tlsys.export import export_store  # noqa: E402
from tlsys.identity import atom_id, ATOMIZER_CONFIG  # noqa: E402
from tlsys.validate_export import validate_export  # noqa: E402

FAILS = []

# M2-B frozen multi-hop bound (also frozen in
# tl-eval/evidence/m2-2026-10-06/trackB/CRITERIA.md before runs).
M2B_FROZEN_HOPS = 3


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
        return [0.9, 0.1, 0.0, 0.0]
    if "charlie" in t:
        return [0.0, 0.0, 1.0, 0.0]
    if "delta" in t:
        return [0.0, 0.0, 0.9, 0.1]
    return [0.25, 0.25, 0.25, 0.25]


def emb(texts):
    return [vec(t) for t in texts]


emb1 = lambda q: vec(q)  # noqa: E731

DOCS = [
    ("d0", "alpha norms govern the alpha baseline completely."),
    ("d1", "alpha bravo rules handle the bravo cases entirely."),
    ("d2", "charlie axioms cover the charlie domain fully."),
    ("d3", "charlie delta statutes span the delta regime wholly."),
    ("d4", "echo remarks touch sundry matters lightly."),
]

# Analyst-supplied typed relations: labeled, PROPOSED, no extractor.
CFG = {"extractor": "m2b-hand-commit-v1",
       "method": "analyst-asserted-over-retrieved-atoms",
       "note": "supplied input path only; no automatic extraction"}

root = tempfile.mkdtemp(prefix="tl-m2b-")
tl = TLStore(os.path.join(root, "store"), create=True,
             lease_owner="test-m2b-relexp")
# Second store: its real committed atom id is genuinely absent from
# the first store (cross-store exclusion is source-grounded: both
# ids trace to committed source bytes, neither store mixes).
tl2 = TLStore(os.path.join(root, "store2"), create=True,
              lease_owner="test-m2b-relexp-x")
try:
    rep = ingest_docs(tl, DOCS, emb)
    check("ingest/atoms", rep["n_atoms"] == 5, rep)
    rep2 = ingest_docs(tl2, [("x0", "xenon lamps glow softly.")],
                       emb)
    check("ingest/xstore", rep2["n_atoms"] == 1, rep2)
    pin_pre = tl.pin()
    idx_pre = NarrowIndex(tl, pin_pre)
    aids = {a["doc_id"]: aid for aid, a in idx_pre.atoms.items()}
    a0, a1, a2, a3, a4 = (aids["d0"], aids["d1"], aids["d2"],
                         aids["d3"], aids["d4"])
    idx2 = NarrowIndex(tl2, tl2.pin())
    (ax,) = list(idx2.atoms)
    check("ingest/fixture-ids", ax not in set(idx_pre.atoms))

    # Absent-source id: derived from real-form source bytes with a
    # revision UUID that was never committed, in a doc never
    # ingested. Well-formed occurrence identity, genuinely absent
    # from every store -- the retired/excluded-source analog.
    never = b"zebra migration corridors cross the northern range."
    XABS = atom_id(never, "doc-never", (0, len(never)),
                   str(uuid.uuid4()), ATOMIZER_CONFIG)
    check("excl/absent-wellformed",
          len(XABS) == 64 and XABS not in set(idx_pre.atoms)
          and XABS not in set(idx2.atoms))

    # Narrow OFF baseline BEFORE relations (temporal pre pin).
    nq0 = NarrowQuery(tl, idx_pre, emb1, cfg={})
    dos_pre, _rec_pre = nq0.run("alpha bravo")
    pre_ids = [e["atom_id"] for e in dos_pre["entries"]]
    exp_pre = export_store(tl)
    check("base/pre-export-clean",
          exp_pre["errors"] == [] and exp_pre["omissions"] == [],
          (exp_pre["errors"], exp_pre["omissions"]))

    recs = [
        # Chain a0-a1-a2-a3 (exact 3-hop ladder; a4 stays off
        # the chain so hop vetoes are exact).
        make_record("links", [("src", a0), ("dst", a1)],
                    {"negated": False, "claim": "c01"}, CFG,
                    PROPOSED, [a0, a1]),
        make_record("links", [("src", a1), ("dst", a2)],
                    {"negated": False, "claim": "c12"}, CFG,
                    PROPOSED, [a1, a2]),
        make_record("links", [("src", a2), ("dst", a3)],
                    {"negated": False, "claim": "c23"}, CFG,
                    PROPOSED, [a2, a3]),
        # Opposing pair over one shared context (Q12.3 geometry).
        # Context a4 (unseeded) keeps the pair off the a0-seeded
        # chain, so hop vetoes stay exact.
        make_record("evidences", [("claim", a0), ("context", a4)],
                    {"negated": False, "scope": "as-stated"}, CFG,
                    PROPOSED, [a0, a4]),
        make_record("evidences", [("claim", a1), ("context", a4)],
                    {"negated": True, "scope": "as-stated"}, CFG,
                    PROPOSED, [a1, a4]),
        # Unresolved qualifier mark (Q12.2 riding).
        make_record("evidences", [("claim", a3), ("context", a2)],
                    {"negated": False, "scope": "as-stated",
                     "unresolved": "m2b-conditional-scope"},
                    CFG, PROPOSED, [a3, a2]),
        # Genuinely-absent endpoint + grounding (exclusion).
        make_record("links", [("src", XABS), ("dst", a0)],
                    {"negated": False}, CFG, PROPOSED, [XABS]),
        # Cross-store endpoint + grounding (exclusion, no mixing).
        make_record("links", [("src", a0), ("dst", ax)],
                    {"negated": False}, CFG, PROPOSED,
                    [a0, ax]),
    ]
    commit_relations(tl, recs)
    check("commit/eight-records", len(recs) == 8)
    pin = tl.pin()
    idx = NarrowIndex(tl, pin)
    live = set(idx.atoms)
    check("commit/live-stable", live == set(idx_pre.atoms),
          (len(live), len(idx_pre.atoms)))
    invalidate_rel_index(tl)
    view = relquery.load(tl, pin, live)
    check("commit/visible-eight", len(view.visible) == 8,
          len(view.visible))
    check("commit/eligible-six", len(view.eligible) == 6,
          (len(view.eligible), sorted(view.reasons)))
    rids = {}
    for rid, item in get_index(tl, pin).records.items():
        rec = item["record"]
        q = rec.get("qualifiers", {})
        rids[q.get("claim", rec["rel_type"] + ":" +
                   q.get("scope", "?") + ":" +
                   str(q.get("negated")))] = rid
    rx = [r for r, rec in view.visible.items()
          if XABS in (rec.get("grounding") or [])][0]
    rxx = [r for r, rec in view.visible.items()
           if ax in (rec.get("grounding") or [])][0]

    # -- exclusion through real entry points ----------------------
    check("excl/absent-ineligible", rx in view.reasons
          and rx not in view.eligible, view.reasons.get(rx))
    check("excl/absent-reasons",
          any(r.startswith("endpoint-unresolved")
              for r in view.reasons.get(rx, []))
          and any(r.startswith("grounding-not-live")
                  for r in view.reasons.get(rx, [])),
          view.reasons.get(rx))
    check("excl/xstore-ineligible", rxx in view.reasons
          and rxx not in view.eligible, view.reasons.get(rxx))
    check("excl/status-verbatim",
          view.visible[rx]["status"] == PROPOSED
          and view.visible[rxx]["status"] == PROPOSED)
    trav = relquery.traverse(get_index(tl, pin), sorted(live),
                             live, max_hops=9, max_edges=500)
    check("excl/never-traversed",
          XABS not in trav["reached"] and ax not in trav["reached"],
          sorted(trav["reached"]))
    check("excl/never-degreed",
          XABS not in view.degrees and ax not in view.degrees)
    check("excl/never-scoped",
          XABS not in view.scope and ax not in view.scope)

    nq_off = NarrowQuery(tl, idx, emb1, cfg={})
    dos_off, _rc_off = nq_off.run("alpha bravo")
    off_ids = [e["atom_id"] for e in dos_off["entries"]]
    check("excl/off-identity", off_ids == pre_ids,
          (pre_ids, off_ids))
    nq_qual = NarrowQuery(tl, idx, emb1, cfg={"REL_QUALIFIERS": True})
    dos_q, rec_q = nq_qual.run("alpha bravo")
    q_ids = [e["atom_id"] for e in dos_q["entries"]]
    check("excl/never-emitted",
          XABS not in q_ids and ax not in q_ids, q_ids)
    rc = rec_q.get("rel_consumption", {})
    check("excl/diag-counts",
          rc.get("relations_visible") == 8
          and rc.get("relations_eligible") == 6
          and rc.get("relations_ineligible") == 2, rc)
    # Stale index across pins: refused, never silently mixed.
    try:
        DossierQuery(tl, idx_pre, emb1,
                     cfg={"DOSSIER_SHAPE": "relational"}).run("alpha")
        check("excl/stale-index-refused", False, "no raise")
    except ValueError:
        check("excl/stale-index-refused", True)

    # -- qualifier / opposing-pair assembly (Narrow entry) --------
    check("qual/pairs-identified",
          (rc.get("pairs_identified") or 0) >= 1, rc)
    check("qual/pairs-joint",
          (rc.get("pairs_jointly_admitted") or 0) >= 1, rc)
    check("qual/partitions",
          (rc.get("mmr_partitions") or 0) >= 1, rc)
    marks = [e.get("marks", {}).get("unresolved")
             for e in dos_q["entries"]]
    check("qual/unresolved-rides", "m2b-conditional-scope" in marks
          or a3 not in q_ids, (q_ids, marks))
    pairs = relquery.identify_pairs(view, q_ids)
    check("qual/pair-exact",
          pairs == [tuple(sorted((a0, a1)))], pairs)
    check("qual/pair-excludes-absent",
          all(XABS not in p and ax not in p for p in pairs), pairs)

    # -- multi-hop at the frozen bound (Dossier entry) ------------
    check("mhop/frozen-bound", M2B_FROZEN_HOPS == 3)
    Q = "alpha baseline norms"
    dq_off = DossierQuery(tl, idx, emb1,
                          cfg={"DOSSIER_SHAPE": "relational",
                               "NARROW": {"MAX_ENTRIES": 1}})
    dos_loff, rec_loff = dq_off.run(Q)
    loff_ids = [e["atom_id"] for e in dos_loff["entries"]]
    check("mhop/off-seeds-a0", loff_ids[:1] == [a0], loff_ids)
    got = {}
    for h in (1, 2, 3):
        dq = DossierQuery(
            tl, idx, emb1,
            cfg={"DOSSIER_SHAPE": "relational",
                 "DOSSIER_REL_TRAVERSAL": True,
                 "DOSSIER_REL_HOPS": h,
                 "NARROW": {"MAX_ENTRIES": 1}})
        dos_h, rec_h = dq.run(Q)
        got[h] = ([e["atom_id"] for e in dos_h["entries"]],
                  dos_h, rec_h)
    check("mhop/h1-veto",
          a2 not in got[1][0] and a3 not in got[1][0]
          and a1 in got[1][0], got[1][0])
    check("mhop/h1-set-parity",
          sorted(got[1][0]) == sorted(loff_ids),
          (sorted(got[1][0]), sorted(loff_ids)))
    check("mhop/h2-veto",
          a2 in got[2][0] and a3 not in got[2][0], got[2][0])
    check("mhop/h3-serves",
          M2B_FROZEN_HOPS == 3 and a3 in got[3][0], got[3][0])
    e3 = [e for e in got[3][1]["entries"]
          if e["atom_id"] == a3][0]
    check("mhop/h3-marks",
          e3["marks"].get("hop") == 3
          and e3["marks"].get("via_relation") is not None
          and e3["emitted_score"] == 0.0
          and e3["verdicts"]["selection"] == "lateral-additive"
          and e3["marks"].get("rel_status") == PROPOSED,
          e3["marks"])
    check("mhop/h3-receipt",
          got[3][2]["metrics"]["H_hops"] == 3
          and got[3][2]["metrics"]["dossier"].get("traversal")
          is True
          and got[3][2]["metrics"]["dossier"].get("rel_hops")
          == M2B_FROZEN_HOPS
          and got[3][2]["metrics"]["dossier"].get("hops_used")
          == 3
          and got[3][2]["flags"].get("dossier_rel_traversal")
          is True,
          got[3][2]["metrics"]["dossier"])
    check("mhop/absent-never-lateral",
          all(e["atom_id"] != XABS and e["atom_id"] != ax
              for _h, (ids, dos, _rc) in got.items()
              for e in dos["entries"]))
    check("mhop/edges-bounded",
          all(r["metrics"]["E_edges"] <= 50
              for _h, (_ids, _dos, r) in got.items()))

    # -- cross-topic assembly (Dossier entry) ----------------------
    dq_x = DossierQuery(tl, idx, emb1,
                        cfg={"DOSSIER_SHAPE": "cross-topic",
                             "NARROW": {"MAX_ENTRIES": 2}})
    dos_x, rec_x = dq_x.run("m2b-xtopic",
                            topics=["alpha bravo", "charlie delta"])
    check("xt/two-sections", len(dos_x["sections"]) == 2,
          dos_x["sections"])
    check("xt/both-served",
          {s["topic"] for s in dos_x["sections"]}
          == {"alpha bravo", "charlie delta"}
          and all(s["entry_ids"] for s in dos_x["sections"]),
          [(s["topic"], len(s["entry_ids"]))
           for s in dos_x["sections"]])
    check("xt/lateral",
          rec_x["metrics"]["dossier"]["lateral_added"] >= 1,
          rec_x["metrics"]["dossier"])
    check("xt/hops-one",
          rec_x["metrics"]["H_hops"] <= 1
          and "dossier_rel_traversal" not in rec_x["flags"])
    check("xt/absent-never-served",
          all(e["atom_id"] != XABS and e["atom_id"] != ax
              for e in dos_x["entries"]))

    # -- export: relation disclosure (M2-B repair) -----------------
    exp = export_store(tl)
    check("exp-rel/no-spurious-errors", exp["errors"] == [],
          exp["errors"])
    check("exp-rel/no-spurious-omissions",
          [o for o in exp["omissions"]
           if o.get("cause") == "meta-missing"] == [],
          exp["omissions"])
    check("exp-rel/truthful-absent",
          "no S-02 relation records committed"
          not in exp["absent"]["relations"]["reason"]
          and "[A6]" in exp["absent"]["relations"]["reason"]
          and "8" in exp["absent"]["relations"]["reason"],
          exp["absent"]["relations"])
    check("exp-rel/counts-relations",
          exp["counts"].get("relations") == 8, exp["counts"])
    check("exp-rel/counts-rest-stable",
          {k: exp["counts"][k]
           for k in ("atoms", "holons", "entries", "omitted")}
          == exp_pre["counts"], (exp["counts"], exp_pre["counts"]))
    check("exp-rel/records-stable",
          [r["atom_id"] for r in exp["records"]]
          == [r["atom_id"] for r in exp_pre["records"]]
          and len(exp["holons"]) == len(exp_pre["holons"]))
    check("exp-rel/id-deterministic",
          export_store(tl)["retry_identity"]["export_id"]
          == exp["retry_identity"]["export_id"])
    verdict = validate_export(exp)
    check("exp-rel/validator-importable",
          verdict["verdict"] == "IMPORTABLE"
          and verdict["problems"] == [], verdict)
    # Relation-free stores keep the exact legacy shape.
    exp2 = export_store(tl2)
    check("exp-rel/legacy-counts-keys",
          set(exp2["counts"])
          == {"atoms", "holons", "entries", "omitted"},
          exp2["counts"])
    check("exp-rel/legacy-absent-text",
          exp2["absent"]["relations"]["reason"]
          == ("no S-02 relation records committed; relational "
              "shapes are a named future gap [A6]"),
          exp2["absent"]["relations"])
    verdict2 = validate_export(exp2)
    check("exp-rel/legacy-importable",
          verdict2["verdict"] == "IMPORTABLE", verdict2)
finally:
    tl.close()
    tl2.close()

print(f"done: {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)

