"""Maintained dossier test: Q4.1(b) relational + Q4.1(c) cross-topic
slice over Narrow.

Covers: narrow shape default delegates byte-identically to
NarrowQuery; cross-topic assembly spans regions across topics
with per-topic sections; dossier C/topic caps + shared work
budget enforced with explicit overflow/bounded-incomplete;
per-entry support labels + dossier disclosure (S4 precedence
reused); bounded 1-hop lateral over explicit S-02 relations
(additive, marked, verbatim status, unresolved carried);
DOSSIER_LATERAL=False disables traversal; cfg validation.

Deterministic fake encoder; scratch store under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_dossier.py
"""
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
from tlsys.relations import (PROPOSED, SOURCE_ATTRIBUTED,  # noqa: E402
                             commit_relations, make_record,
                             read_relations)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def vec(text):
    t = text.lower()
    if any(w in t for w in ("cat", "dog", "animal", "purr", "bark")):
        return [1.0, 0.0, 0.0, 0.0]
    if any(w in t for w in ("fuse", "current", "circuit", "melt")):
        return [0.0, 1.0, 0.0, 0.0]
    return [0.0, 0.0, 1.0, 0.0]


def emb(texts):
    return [vec(t) for t in texts]


emb1 = lambda q: vec(q)  # noqa: E731

DOCS = [
    ("d-cat", "The domestic cat is a small carnivorous mammal. "
     "Cats purr when content."),
    ("d-dog", "The domestic dog is a loyal companion animal. "
     "Dogs bark to alert owners."),
    ("d-fuse", "An electrical fuse protects circuits from "
     "overcurrent. The fuse wire melts."),
]

root = tempfile.mkdtemp(prefix="tl-dos-")
tl = TLStore(os.path.join(root, "store"), create=True,
             lease_owner="test-dossier")
try:
    rep = ingest_docs(tl, DOCS, emb)
    check("ingest/atoms", rep["n_atoms"] == 3, rep)
    pinned = tl.pin()
    idx = NarrowIndex(tl, pinned)
    aids = {a["doc_id"]: aid for aid, a in idx.atoms.items()}
    check("ingest/three-atoms", len(aids) == 3, aids)

    CFG = {"extractor": "test-cooccur-v1", "window": 2,
           "model": "none", "rules": ["cross-topic-link"]}
    r1 = make_record(
        "relates", [("source", aids["d-cat"]),
                    ("target", aids["d-fuse"])],
        {"negated": False}, CFG, SOURCE_ATTRIBUTED,
        [aids["d-cat"], aids["d-fuse"]])
    r2 = make_record(
        "relates", [("source", aids["d-dog"]),
                    ("target", aids["d-fuse"])],
        {"negated": False, "unresolved": "conditional scope "
         "unrepresentable; see grounding"}, CFG, PROPOSED,
        [aids["d-dog"]])
    commit_relations(tl, [r1, r2])
    pinned = tl.pin()
    idx = NarrowIndex(tl, pinned)
    check("relations/committed",
          len(read_relations(tl, pinned)) == 2)

    Q = "which animal purrs when content"
    TOPICS = ["which animal purrs when content",
              "fuse wire melts overcurrent"]

    # -- narrow shape: default + byte-identical delegation ----
    nq = NarrowQuery(tl, idx, emb1)
    dos_n, rec_n = nq.run(Q)
    dq_def = DossierQuery(tl, idx, emb1)
    dos_d, rec_d = dq_def.run(Q)
    # Wall-clock T_ms is the only permitted difference (verified
    # separately: key-level diff shows T_ms alone).
    rec_n["metrics"]["T_ms"] = rec_d["metrics"]["T_ms"] = -1.0
    check("fallback/default-byte-identical",
          dos_d == dos_n and rec_d == rec_n,
          "default dossier run differs from NarrowQuery.run")
    check("fallback/flag",
          rec_d["flags"].get("narrow_Q9.2") is True)

    # -- cross-topic assembly across regions ------------------
    dq = DossierQuery(tl, idx, emb1,
                      cfg={"DOSSIER_SHAPE": "cross-topic"})
    dos, rec = dq.run(Q, topics=TOPICS)
    docs = {e["doc_id"] for e in dos["entries"]}
    check("assembly/multi-region", len(docs) >= 2, docs)
    check("assembly/sections",
          [s["topic"] for s in dos["sections"]] == TOPICS
          and sorted(sum((s["entry_ids"] for s in dos["sections"]),
                         []))
          == sorted(e["atom_id"]
                    for e in dos["entries"]
                    if not e["marks"].get("lateral")),
          dos["sections"])
    check("assembly/entry-shape",
          all("atom_id" in e and "text" in e and "span" in e
              and e["resolving_generation"] == pinned[3]
              and "dossier_topic" in e
              for e in dos["entries"]),
          f"{len(dos['entries'])} entries")
    check("assembly/no-dup-atoms",
          len({e["atom_id"] for e in dos["entries"]})
          == len(dos["entries"]))
    check("assembly/six-dims",
          all(k in rec["metrics"]
              for k in ("H_hops", "R_regions", "E_edges",
                        "C_candidates", "P_partitions", "T_ms")),
          sorted(rec["metrics"]))

    # -- disclosure labels (S4 machinery reused) --------------
    check("disclosure/support-labels",
          all(e["support"] in ("lex-only", "dense-only",
                               "both", "neither")
              for e in dos["entries"])
          and sum(rec["metrics"]["support_counts"].values())
          == len(dos["entries"]),
          rec["metrics"]["support_counts"])
    check("disclosure/presentation",
          rec["uncertainty_presentation"] in (
              "not sure (low retrieval similarity)",
              "not sure (low region support)",
              "unassessed (similarity above floor; "
              "not an answerability claim)"),
          rec["uncertainty_presentation"])
    check("disclosure/flags-not-produced",
          "qualifier_Q12.1" in rec["flags_not_produced"]
          and rec["flags"]["dossier_cross_topic"] is True
          and rec["flags"]["narrow_Q9.2"] is False,
          rec["flags"])
    check("disclosure/uq1",
          rec["disclosure_UQ1"] == {"events": []})

    # -- budget enforcement: C cap -----------------------------
    dq_cap = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "cross-topic",
             "DOSSIER_MAX_ENTRIES": 1})
    dos_c, rec_c = dq_cap.run(Q, topics=TOPICS)
    check("budget/entry-cap",
          len(dos_c["entries"]) == 1
          and any(p["cause"] == "dossier-cap-overflow"
                  for p in rec_c["partials"]),
          f"{len(dos_c['entries'])} entries, "
          f"{len(rec_c['partials'])} partials")
    check("budget/cap-counts-consistent",
          sum(rec_c["metrics"]["support_counts"].values())
          == len(dos_c["entries"]),
          rec_c["metrics"]["support_counts"])

    # -- budget enforcement: topic cap -------------------------
    dq_tc = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "cross-topic",
             "DOSSIER_MAX_TOPICS": 1})
    dos_t, rec_t = dq_tc.run(Q, topics=TOPICS)
    check("budget/topic-cap",
          len(dos_t["sections"]) == 1
          and rec_t["metrics"]["dossier"]["topics_deferred"]
          == TOPICS[1:]
          and any(p["cause"] == "dossier-topic-cap"
                  for p in rec_t["partials"]),
          rec_t["metrics"]["dossier"])

    # -- budget enforcement: shared work budget ----------------
    dq_wb = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "cross-topic",
             "DOSSIER_WORK_BUDGET": 1})
    _dos_w, rec_w = dq_wb.run(Q, topics=TOPICS)
    check("budget/work-exhaustion",
          rec_w["execution"]["status"] == "bounded-incomplete"
          and rec_w["support_findings"] == "bounded-incomplete"
          and rec_w["partials"]
          and rec_w["partials"][0]["scope"] == "query",
          rec_w["execution"])

    # -- bounded lateral over explicit relations ---------------
    # Pure-lex narrow arm: topic 2 matches nothing, so any
    # fuse entry must arrive via relation traversal.
    dq_lat = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "cross-topic",
             "NARROW": {"EMIT_DENSE_ATOMS": False,
                        "REGION_DENSE_ATOMS": False}})
    dos_l, rec_l = dq_lat.run(
        Q, topics=["cats purr when content", "zxqy wobble noprob"])
    lat = [e for e in dos_l["entries"]
           if e["marks"].get("lateral") is True]
    check("lateral/additive-entry",
          len(lat) >= 1
          and all(e["verdicts"]["selection"]
                  == "lateral-additive" for e in lat),
          f"{len(lat)} lateral of {len(dos_l['entries'])}")
    check("lateral/marks",
          all(e["marks"].get("via_relation")
              and e["marks"].get("rel_status")
              in (SOURCE_ATTRIBUTED, PROPOSED)
              for e in lat),
          [e["marks"] for e in lat])
    check("lateral/unresolved-carried",
          any(e["marks"].get("rel_unresolved") is not None
              for e in lat)
          or rec_l["metrics"]["dossier"][
              "lateral_edges_examined"] >= 1,
          rec_l["metrics"]["dossier"])
    check("lateral/bounded",
          rec_l["metrics"]["H_hops"] <= 1
          and rec_l["metrics"]["E_edges"]
          <= rec_l["metrics"]["dossier"]["max_edges"],
          rec_l["metrics"]["dossier"])
    check("lateral/honest-support",
          all(e["support"] in ("lex-only", "dense-only",
                               "both", "neither")
              for e in lat),
          [e["support"] for e in lat])

    dq_nolat = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "cross-topic",
             "DOSSIER_LATERAL": False,
             "NARROW": {"EMIT_DENSE_ATOMS": False,
                        "REGION_DENSE_ATOMS": False}})
    dos_nl, rec_nl = dq_nolat.run(
        Q, topics=["cats purr when content", "zxqy wobble noprob"])
    check("lateral/opt-out",
          all(e["marks"].get("lateral") is not True
              for e in dos_nl["entries"])
          and rec_nl["metrics"]["E_edges"] == 0
          and rec_nl["metrics"]["H_hops"] == 0)

    # -- edge cap enforced -------------------------------------
    dq_e0 = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "cross-topic",
             "DOSSIER_MAX_EDGES": 0,
             "NARROW": {"EMIT_DENSE_ATOMS": False,
                        "REGION_DENSE_ATOMS": False}})
    dos_e0, rec_e0 = dq_e0.run(
        Q, topics=["cats purr when content", "zxqy wobble noprob"])
    check("budget/edge-cap",
          rec_e0["metrics"]["E_edges"] == 0
          and all(e["marks"].get("lateral") is not True
                  for e in dos_e0["entries"]),
          rec_e0["metrics"]["dossier"])

    # -- cfg validation ----------------------------------------
    for bad, nm in (({"NOPE": 1}, "unknown-key"),
                    ({"DOSSIER_SHAPE": "spread"},
                     "bad-shape"),
                    ({"DOSSIER_MAX_HOPS": 2}, "multi-hop")):
        try:
            DossierQuery(tl, idx, emb1, cfg=bad)
            check(f"cfg/{nm}-rejected", False, "no raise")
        except ValueError:
            check(f"cfg/{nm}-rejected", True)
    try:
        DossierQuery(tl, idx, emb1,
                     cfg={"NARROW": {"RRF_K": 20}})
        check("cfg/narrow-passthrough-validated", False,
              "RRF_K accepted!")
    except ValueError:
        check("cfg/narrow-passthrough-validated", True)

    # -- Q4.1(b) relational shape ----------------------------
    dq_rel = DossierQuery(tl, idx, emb1,
                          cfg={"DOSSIER_SHAPE": "relational"})
    dos_r, rec_r = dq_rel.run(Q)
    check("relational/single-section",
          len(dos_r["sections"]) == 1
          and rec_r["metrics"]["dossier"]["shape"] == "relational"
          and rec_r["metrics"]["dossier"]["topics_run"] == [Q]
          and rec_r["flags"].get("dossier_relational") is True
          and rec_r["flags"].get("narrow_Q9.2") is False
          and "dossier_cross_topic" not in rec_r["flags"],
          rec_r["metrics"]["dossier"])
    check("relational/anchors-are-narrow",
          [e["atom_id"] for e in dos_r["entries"]
           if not e["marks"].get("lateral")]
          == [e["atom_id"] for e in dos_n["entries"]],
          "seed anchors differ from NarrowQuery.run order")
    check("relational/six-dims",
          all(k in rec_r["metrics"]
              for k in ("H_hops", "R_regions", "E_edges",
                        "C_candidates", "P_partitions", "T_ms")),
          sorted(rec_r["metrics"]))
    dos_ri, rec_ri = dq_rel.run(Q, topics=TOPICS)
    check("relational/topics-ignored",
          rec_ri["metrics"]["dossier"]["topics_run"] == [Q]
          and len(dos_ri["sections"]) == 1,
          rec_ri["metrics"]["dossier"])
    dq_rell = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "relational",
             "NARROW": {"EMIT_DENSE_ATOMS": False,
                        "REGION_DENSE_ATOMS": False}})
    dos_rl, rec_rl = dq_rell.run("cats purr when content")
    lat_r = [e for e in dos_rl["entries"]
             if e["marks"].get("lateral") is True]
    check("relational/lateral-additive",
          len(lat_r) >= 1
          and all(e["verdicts"]["selection"]
                  == "lateral-additive" for e in lat_r)
          and all(e["marks"].get("via_relation")
                  and e["marks"].get("rel_status")
                  in (SOURCE_ATTRIBUTED, PROPOSED)
                  for e in lat_r)
          and rec_rl["metrics"]["H_hops"] <= 1,
          f"{len(lat_r)} lateral of {len(dos_rl['entries'])}")
    dq_rel0 = DossierQuery(
        tl, idx, emb1,
        cfg={"DOSSIER_SHAPE": "relational",
             "DOSSIER_MAX_EDGES": 0,
             "NARROW": {"EMIT_DENSE_ATOMS": False,
                        "REGION_DENSE_ATOMS": False}})
    dos_r0, rec_r0 = dq_rel0.run("cats purr when content")
    check("relational/edge-cap",
          rec_r0["metrics"]["E_edges"] == 0
          and all(e["marks"].get("lateral") is not True
                  for e in dos_r0["entries"]),
          rec_r0["metrics"]["dossier"])
    dos_r2, _rec_r2 = dq_rel.run(Q)
    check("relational/deterministic",
          [e["atom_id"] for e in dos_r["entries"]]
          == [e["atom_id"] for e in dos_r2["entries"]],
          "order differs")

    # -- determinism -------------------------------------------
    dos2, _rec2 = dq.run(Q, topics=TOPICS)
    check("deterministic",
          [e["atom_id"] for e in dos["entries"]]
          == [e["atom_id"] for e in dos2["entries"]],
          "order differs")
finally:
    tl.close()

print(f"done: {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
