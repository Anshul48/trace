"""Maintained organization-conformance test: incremental ingest ->
per-doc holons -> committed persistence -> restart -> Narrow use.

Covers the bounded TL organization promise (S-03 S1b first baseline
as built: per-doc holons, trivially bottom-up; centroid descriptors,
E-S1a first-baseline candidate; D-18/D-19; Q2/Q3 guide-only):
  1. new material automatically receives organization (membership +
     centroid descriptor committed);
  2. related and distinct material stay distinguishable (incl.
     identical text at distinct occurrences, and preserved
     contradictions);
  3. accepted correction conditions: additive growth leaves existing
     organization byte-stable; unapproved mutation is terminally
     rejected (D-23) with the pin unchanged; re-ingest skips;
     stale index/generation mismatch fails closed (Q8.2);
  4. relationships + provenance survive close/reopen (restart);
  5. the intended consumer (NarrowQuery + index inspection) uses the
     committed structure;
  6. work performed and obvious resource costs are recorded.

Uses a deterministic fake encoder through the documented embed seam
(README: any encoder), so no model weights are needed. Needs the
venv for blake3 + numpy.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_organization_conformance.py
"""
import hashlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

import numpy as np

from tlsys.store_if import TLStore, prepare_artifact, uuidv7
from tlsys.ingest import chunk_text, ingest_docs
from tlsys.index import NarrowIndex
from tlsys.query import NarrowQuery
from tlsys.identity import atom_id

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 8


def fake_vec(text):
    h = hashlib.sha256(text.encode("utf-8")).digest()
    return [float(b) / 255.0 for b in h[:DIM]]


def emb(texts):
    return [fake_vec(t) for t in texts]


def emb1(q):
    return fake_vec(q)


def centroid(texts):
    vecs = [fake_vec(t) for t in texts]
    return [sum(v[d] for v in vecs) / len(vecs) for d in range(DIM)]


BOILER = "Identical boilerplate sentence repeated verbatim here."
NEAR1 = BOILER + " Primero."
NEAR2 = BOILER + " Secundo."
DOC_A = "The domestic cat is a small carnivorous mammal. Cats purr."
DOC_B = "The domestic dog is a loyal companion. Dogs bark loudly."
DOC_C = "An electrical fuse protects circuits from overcurrent faults."
PRO_X = "Drug X cures headaches quickly and reliably always."
CON_X = "Drug X causes headaches and must be avoided entirely."
LONG = " ".join(f"alpha{i}" for i in range(250))  # 2 chunks

tmp = tempfile.mkdtemp(prefix="tlsys-orgconf-")
sp = os.path.join(tmp, "store")
tl = TLStore(sp, create=True, lease_owner="test-orgconf")

# -- batch 1: creation ------------------------------------------------
rep1 = ingest_docs(tl, [("docA", DOC_A), ("docE", LONG)], emb)
pin1 = tl.pin()
check("b1-counts", rep1["n_atoms"] == 3 and rep1["n_holons"] == 2,
      f"{rep1}")
idx1 = NarrowIndex(tl, pin1)
check("b1-holons",
      {"docA", "docE"} <= set(idx1.holons)
      and all(h in ("docA", "docE") or h.startswith("xdoc-")
              for h in idx1.holons),
      f"{sorted(idx1.holons)}")
check("b1-membership",
      len(idx1.holons["docA"]["members"]) == 1
      and len(idx1.holons["docE"]["members"]) == 2,
      f"{ {k: len(v['members']) for k, v in idx1.holons.items()} }")
# descriptor == centroid of member chunk vectors (E-S1a first baseline)
echunks = [c[2] for c in chunk_text(LONG)]
check("b1-centroid",
      np.allclose(idx1.holons["docE"]["descriptor"], centroid(echunks)),
      "holon descriptor is not the member centroid")
check("b1-attribution",
      idx1.atoms[idx1.holons["docA"]["members"][0]]["doc_id"] == "docA"
      and all(idx1.atoms[a]["doc_id"] == "docE"
              for a in idx1.holons["docE"]["members"]),
      "atom->doc attribution wrong")
snapA = (list(idx1.holons["docA"]["members"]),
         [float(x) for x in idx1.holons["docA"]["descriptor"]],
         idx1.holons["docA"]["seq"], idx1.holons["docA"]["op_id"])

# -- batch 2: related + distinct + identical + contradictory ------------
rep2 = ingest_docs(tl, [("docB", DOC_B), ("docC", DOC_C),
                        ("docD1", BOILER), ("docD2", BOILER),
                        ("docN1", NEAR1), ("docN2", NEAR2),
                        ("docPro", PRO_X), ("docCon", CON_X)], emb)
pin2 = tl.pin()
check("b2-counts", rep2["n_atoms"] == 8 and rep2["n_holons"] == 8,
      f"{rep2}")
# stale index must fail closed (Q8.2), never silently mix generations
try:
    NarrowQuery(tl, idx1, emb1).run("cat purrs")
    check("stale-index-fail-closed", False, "no error on gen mismatch")
except ValueError:
    check("stale-index-fail-closed", True)
idx2 = NarrowIndex(tl, pin2)
# additive growth: existing organization byte-stable
hA = idx2.holons["docA"]
check("growth-stable",
      list(hA["members"]) == snapA[0]
      and [float(x) for x in hA["descriptor"]] == snapA[1]
      and hA["seq"] == snapA[2] and hA["op_id"] == snapA[3],
      "batch-1 organization mutated by batch-2 ingest")
# identical text, distinct occurrences -> distinct atoms (S-02 S1)
m1 = idx2.holons["docD1"]["members"]
m2 = idx2.holons["docD2"]["members"]
check("occurrence-distinct", len(m1) == 1 and len(m2) == 1
      and m1[0] != m2[0], f"{m1} vs {m2}")
check("occurrence-attribution",
      idx2.atoms[m1[0]]["doc_id"] == "docD1"
      and idx2.atoms[m2[0]]["doc_id"] == "docD2",
      "shared aid / wrong attribution")
check("index-complete", len(idx2.atoms) == 11, f"{len(idx2.atoms)}")
import json as _jsonm
_man = _jsonm.load(open(os.path.join(sp, "ingest_manifest.json")))
_rev1 = _man["docD1"]["revision_id"]
_bb = BOILER.encode("utf-8")
check("identity-deterministic",
      atom_id(_bb, "docD1", (0, len(_bb)), _rev1)
      == atom_id(_bb, "docD1", (0, len(_bb)), _rev1)
      == m1[0], "atom identity not deterministic")
# changed bytes under an existing doc_id fail closed (new revision
# needs a new doc_id); identical re-ingest still skips.
try:
    ingest_docs(tl, [("docD1", BOILER + " altered")], emb)
    check("changed-bytes-refused", False, "silent overwrite/skip")
except RuntimeError as e:
    check("changed-bytes-refused", "new revision" in str(e), f"{e}")
check("changed-refusal-pin-stable", tl.pin()[3] == pin2[3],
      f"{tl.pin()[3]} != {pin2[3]}")
# contradictions preserved: both sides committed, attributed, usable
check("contradiction-preserved",
      idx2.atoms[idx2.holons["docPro"]["members"][0]]["doc_id"]
      == "docPro"
      and idx2.atoms[idx2.holons["docCon"]["members"][0]]["doc_id"]
      == "docCon", "contradictory evidence merged or lost")

# -- correction boundary: unapproved mutation rejects, pin stable -----
for kind, code in (("DESCRIPTOR_REFRESH", "POLICY_NOT_ACTIVE"),
                   ("ORPHAN_COLLECT", "POLICY_NOT_ACTIVE"),
                   ("FOLD_PHYSICAL", "ENTRY1_MISSING_PA")):
    mart = prepare_artifact(tl.store, b'{"x":1}', "test-orgconf")
    results, _ = tl.commit_batch([{
        "op_id": uuidv7(), "kind": kind, "payload": {"holon": "docA"},
        "disclosure": {"leg": "test-orgconf"},
        "approval_ref": {"stage": 1, "policy_version": 0},
        "artifacts": (mart,)}])
    check(f"gate-{kind}",
          len(results) == 1 and results[0].get("status") == "terminal"
          and results[0].get("code") == code, f"{results}")
check("gate-pin-stable", tl.pin()[3] == pin2[3],
      f"{tl.pin()[3]} != {pin2[3]}")
# re-ingest skips (no duplicate organization), pin unchanged
rep3 = ingest_docs(tl, [("docA", DOC_A)], emb)
check("reingest-skip",
      rep3["n_atoms"] == 0 and rep3["n_holons"] == 0
      and rep3["skipped"] == ["docA"] and tl.pin()[3] == pin2[3],
      f"{rep3}")

# -- consumer use through the intended interface -----------------------
nq = NarrowQuery(tl, idx2, emb1)
dos, rec = nq.run("boilerplate sentence verbatim")
ids = sorted(e["doc_id"] for e in dos["entries"])
# Exact-duplicate TEXTS collapse at presentation prune (accepted Q10.2
# + amended Q12.1b exact-only); near-identical texts serve distinctly.
# Under promoted defaults dense emission widens serving at this tiny
# scale (dense top-100 covers all 11 atoms), so the default-path check
# pins collapse + distinctness, while the exact narrow scope is pinned
# under explicit lex-only cfg below.
check("query-distinct-served",
      "docN1" in ids and "docN2" in ids
      and sum(d in ids for d in ("docD1", "docD2")) == 1, f"{ids}")
check("entries-provenance",
      all(e["doc_id"] and e["span"] and e["text"]
          and e["issuing_generation"] and e["resolving_generation"]
          == pin2[3] for e in dos["entries"]),
      "entry missing provenance")
check("dense-sees-all-holons",
      sorted(d for d, _s in idx2.dense_holons(emb1("q")))
      == sorted(idx2.holons), "dense leg misses holons")
dosx, _recx = nq.run("Drug X headaches")
idx = sorted(e["doc_id"] for e in dosx["entries"])
check("query-contradiction-both",
      "docCon" in idx and "docPro" in idx, f"{idx}")
# lex-only cfg pins the exact narrow scope (pre-promotion behavior):
# collapse to one dup + both contradiction sides, nothing else.
_OFF = {"EMIT_DENSE_ATOMS": False, "REGION_DENSE_ATOMS": False,
        "PRUNE_SPLIT": False, "DISCLOSE_TOP1_CUT": None}
nq_off = NarrowQuery(tl, idx2, emb1, cfg=dict(_OFF))
dos_off, _ = nq_off.run("boilerplate sentence verbatim")
ids_off = sorted(e["doc_id"] for e in dos_off["entries"])
check("query-distinct-narrow-lex-only",
      "docN1" in ids_off and "docN2" in ids_off
      and sum(d in ids_off for d in ("docD1", "docD2")) == 1
      and len(ids_off) == 3, f"{ids_off}")
dosx_off, _ = nq_off.run("Drug X headaches")
idx_off = sorted(e["doc_id"] for e in dosx_off["entries"])
check("query-contradiction-narrow-lex-only",
      idx_off == ["docCon", "docPro"], f"{idx_off}")
# committed holon meta is directly inspectable, digest-verified
seqs = [r[0] for r in tl.read_commits(*pin2[:3], kind="ACCEPT_ATOMS")]
refs = tl.pub_refs(seqs)
found = 0
found_perdoc = 0
for seq in seqs:
    for art in refs.get(seq, []):
        arow = tl.artifact_row(art)
        if arow is None:
            continue
        body = tl.read_artifact(art, expect_digest=arow[4])
        try:
            import json as _json
            meta = _json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(meta, dict) and "holon" in meta:
            found += 1
            if not str(meta["holon"]).startswith("xdoc-"):
                found_perdoc += 1
check("holon-meta-inspectable",
      found_perdoc == 10 and found >= 10,
      f"{found_perdoc} per-doc + {found - found_perdoc} xdoc metas")
# integrity failure case: wrong digest refuses
try:
    tl.read_artifact(tl.read_commits(*pin2[:3], kind="ACCEPT_ATOMS")
                     and refs[seqs[0]][0], expect_digest="sha256:dead")
    check("integrity-refuses", False, "bad digest accepted")
except ValueError:
    check("integrity-refuses", True)

# -- identity-scheme guards: never silently mix --------------------------
import json as _json

man_path = os.path.join(tl.store.root, "ingest_manifest.json")
from tlsys.identity import ATOM_SCHEME as _SCHEME
_man_full = _json.load(open(man_path))
check("manifest-stamped",
      _man_full.get("_scheme") == _SCHEME == "tlsys-v2-revision"
      and _man_full["docA"]["revision_id"]
      and _man_full["docA"]["source_sha256"].startswith("sha256:")
      and _man_full["docA"]["revision_len"]
      == len(DOC_A.encode("utf-8")),
      "manifest lacks scheme stamp / revision binding")
# old (unstamped, non-empty) manifest -> explicit ingest refusal
sp_old = os.path.join(tmp, "store-old")
tl_old = TLStore(sp_old, create=True, lease_owner="test-orgconf-old")
with open(os.path.join(tl_old.store.root,
                       "ingest_manifest.json"), "w") as f:
    _json.dump({"docZ": {"atoms": ["op-1"], "holon": "op-2"}}, f)
try:
    ingest_docs(tl_old, [("docNew", "fresh text")], emb)
    check("old-manifest-refused", False, "mixed schemes silently")
except RuntimeError:
    check("old-manifest-refused", True)
tl_old.close()
# old-scheme committed meta -> explicit index refusal (true old-data
# simulation: hand-built pre-repair atom meta, no atom_scheme field)
sp_leg = os.path.join(tmp, "store-legacy")
tl_leg = TLStore(sp_leg, create=True, lease_owner="test-orgconf-leg")
_tart = prepare_artifact(tl_leg.store, b"legacy bytes", "s-leg")
_mart = prepare_artifact(
    tl_leg.store,
    _json.dumps({"atom": "a" * 64, "doc_id": "docLeg", "chunk_ix": 0,
                 "n_chunks": 1, "span": [0, 12], "text_len": 12,
                 "text_artifact": _tart["artifact_id"],
                 "text_digest": _tart["digest"],
                 "descriptor": [0.0] * DIM}).encode(), "s-leg")
tl_leg.commit_batch([{
    "op_id": uuidv7(), "kind": "ACCEPT_ATOMS",
    "payload": {"atom": "a" * 64, "doc_id": "docLeg",
                "meta_artifact": _mart["artifact_id"]},
    "disclosure": {"leg": "test-orgconf-legacy"},
    "approval_ref": None, "artifacts": (_tart, _mart)}])
try:
    NarrowIndex(tl_leg, tl_leg.pin())
    check("old-commits-refused", False, "indexed old-scheme data")
except ValueError:
    check("old-commits-refused", True)
tl_leg.close()

# -- work performed and resource costs recorded ------------------------
check("receipt-work",
      rec["metrics"]["work_used"] > 0
      and rec["metrics"]["op_class_counts"]
      and rec["metrics"]["T_ms"] >= 0
      and rec["metrics"]["cost_table"] == "v1-provisional-unit",
      f"{rec['metrics']}")
summ = tl.trace.summary()
check("trace-work",
      any(k.startswith("commit_batch/") for k in summ)
      and any(k.startswith("read_commits/") for k in summ)
      and any(k.startswith("read_artifact/") for k in summ),
      f"{sorted(summ)}")

# -- restart: relationships + provenance survive -----------------------
snap = {d: (list(h["members"]), [float(x) for x in h["descriptor"]],
             h["seq"], h["op_id"]) for d, h in idx2.holons.items()}
tl.close()
tl2 = TLStore(sp, create=False, lease_owner="test-orgconf-2")
rep4 = ingest_docs(tl2, [("docA", DOC_A)], emb)
pinR = tl2.pin()
check("restart-manifest",
      rep4["skipped"] == ["docA"] and pinR[3] == pin2[3], f"{rep4}")
idxR = NarrowIndex(tl2, pinR)
same = (sorted(idxR.holons) == sorted(snap)
        and all(list(idxR.holons[d]["members"]) == snap[d][0]
                and [float(x) for x in idxR.holons[d]["descriptor"]]
                == snap[d][1]
                and idxR.holons[d]["seq"] == snap[d][2]
                and idxR.holons[d]["op_id"] == snap[d][3]
                for d in snap))
check("restart-identical", same, "organization changed across restart")
dosR, _ = NarrowQuery(tl2, idxR, emb1).run("boilerplate sentence verbatim")
check("restart-requery-identical",
      [e["atom_id"] for e in dosR["entries"]]
      == [e["atom_id"] for e in dos["entries"]], "rankings differ")
tl2.close()

print("store-root:", tmp)
print("RESULT:", "FAIL " + str(FAILS) if FAILS else "PASS")
sys.exit(1 if FAILS else 0)
