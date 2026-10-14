"""Reference-validator test: tl-evidence-export/0.2 + /0.3 -> IMPORTABLE/REFUSED.

Covers tlsys/validate_export.py against the versioned contract
(EXPORT-SCHEMA.md + handoffs/TL-CONSUMER-ACCEPTANCE-CHECKLIST.md
gates B1/B12): live-producer 0.3 exports validate, rendering-only
changes keep identity, every tamper class refuses with a scoped
problem, and a hand-built 0.2 export with an independently
computed export_id validates under the 0.2 scheme pin.

Uses a deterministic fake encoder through the documented embed
seam (README: any encoder), so no model weights are needed. Needs
the venv for blake3. Scratch stores live under /tmp
(rebuild-no-migration).
Run: tl-sys/.venv/bin/python tl-sys/tests/test_validate_export.py
"""
import copy
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.export import export_store  # noqa: E402
from tlsys.validate_export import (  # noqa: E402
    IMPORTABLE,
    REFUSED,
    SCHEME_PINS,
    validate_export,
)
from tlsys import (  # noqa: E402
    CANDIDATE_APPROVAL,
    CANDIDATE_REV,
    SPEC_SESSION,
)

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


def expect_refused(name, exp, *scopes):
    got = validate_export(exp)
    ok = got["verdict"] == REFUSED and len(got["problems"]) > 0
    for scope in scopes:
        if not any(p.startswith(scope + ":") or p.startswith(scope + " ")
                   or p == scope or p.startswith(scope + "[")
                   for p in got["problems"]):
            ok = False
    check(name, ok, f"{got['verdict']} {got['problems'][:3]}")


DOC_A = "The domestic cat is a small carnivorous mammal. Cats purr."
DOC_B = "The domestic dog is a loyal companion. Dogs bark loudly."
BOILER = "Identical boilerplate sentence repeated verbatim here."

tmp = tempfile.mkdtemp(prefix="tlsys-validate-")
sp = os.path.join(tmp, "store")
tl = TLStore(sp, create=True, lease_owner="test-validate")
rep = ingest_docs(tl, [("docA", DOC_A), ("docB", DOC_B),
                       ("docD1", BOILER), ("docD2", BOILER)], emb)
pinned = tl.pin()
birth, epoch, mx, triple = pinned

# -- live 0.3 export validates ----------------------------------------
exp = export_store(tl)
got = validate_export(exp)
check("live-03-importable",
      got["verdict"] == IMPORTABLE and got["problems"] == [],
      f"{got['verdict']} {got['problems'][:3]}")
check("live-03-identity",
      got["identity"] == {
          "export_schema": "tl-evidence-export/0.3",
          "atom_scheme": SCHEME_PINS["tl-evidence-export/0.3"],
          "pinned_triple": triple,
          "export_id": exp["retry_identity"]["export_id"],
          "counts": dict(exp["counts"])},
      f"{got['identity']}")

# -- rendering-only changes keep identity (B1) -------------------------
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402

idx = NarrowIndex(tl, pinned)
nq = NarrowQuery(tl, idx, lambda q: fake_vec(q))
dos, rec = nq.run("which animal purrs when content")
exp_r = export_store(tl, include_text=False, dossier=dos, receipt=rec,
                     call_trace=tl.trace)
check("render-export-id-stable",
      exp_r["retry_identity"]["export_id"]
      == exp["retry_identity"]["export_id"],
      "rendering-only options moved export_id")
got_r = validate_export(exp_r)
check("render-importable",
      got_r["verdict"] == IMPORTABLE and got_r["problems"] == [],
      f"{got_r['verdict']} {got_r['problems'][:3]}")

# -- bounded-incomplete receipt still validates (partials math) --------
nq_tiny = NarrowQuery(tl, idx, lambda q: fake_vec(q),
                      cfg={"WORK_BUDGET": 0})
dos_b, rec_b = nq_tiny.run("which animal purrs when content")
check("bounded-fixture",
      rec_b["execution"]["status"] == "bounded-incomplete"
      and len(rec_b["partials"]) > 0,
      f"{rec_b['execution']} {rec_b.get('partials')}")
exp_b = export_store(tl, receipt=rec_b)
got_b = validate_export(exp_b)
check("bounded-importable",
      got_b["verdict"] == IMPORTABLE and got_b["problems"] == []
      and exp_b["completeness"] == "bounded-incomplete",
      f"{got_b['verdict']} {got_b['problems'][:3]}")

# -- empty store validates ---------------------------------------------
sp_e = os.path.join(tmp, "store-empty")
tl_e = TLStore(sp_e, create=True, lease_owner="test-validate-empty")
exp_e = export_store(tl_e)
got_e = validate_export(exp_e)
check("empty-importable",
      got_e["verdict"] == IMPORTABLE and got_e["problems"] == [],
      f"{got_e['verdict']} {got_e['problems'][:3]}")

# -- tamper classes refuse ----------------------------------------------
t = copy.deepcopy(exp)
t["export_schema"] = "tl-evidence-export/9.9"
expect_refused("refuse-schema", t, "schema")

t = copy.deepcopy(exp)
t["producer"]["atom_scheme"] = "tlsys-v1-occurrence"
expect_refused("refuse-scheme-pin", t, "producer", "retry_identity")

t = copy.deepcopy(exp)
t["pinned_generation"]["triple"] = "forged:0:0"
expect_refused("refuse-triple", t, "pin", "frontier")

t = copy.deepcopy(exp)
t["coverage_frontier"]["pinned_triple"] = "forged:0:0"
expect_refused("refuse-frontier-triple", t, "frontier")

t = copy.deepcopy(exp)
t["coverage_frontier"]["kinds_covered"] = ["ACCEPT_ATOMS", "SNEAKED"]
expect_refused("refuse-frontier-kinds", t, "frontier")

t = copy.deepcopy(exp)
t["coverage_frontier"]["counts_ref"]["atoms"] += 1
expect_refused("refuse-counts-ref", t, "frontier")

t = copy.deepcopy(exp)
t["counts"]["atoms"] += 1
expect_refused("refuse-counts", t, "counts", "frontier",
               "retry_identity")

t = copy.deepcopy(exp)
t["records"] = t["records"][:-1]
expect_refused("refuse-dropped-record", t, "counts")

t = copy.deepcopy(exp)
t["retry_identity"]["export_id"] = (
    "blake3:" + "0" * 64)
expect_refused("refuse-export-id", t, "retry_identity")

t = copy.deepcopy(exp)
t["records"][0]["qualifications"]["qualifiers"] = {"hedge": 0.2}
expect_refused("refuse-present-qualifiers", t, "record")

t = copy.deepcopy(exp)
del t["records"][0]["occurrence"]["byte_span"]
expect_refused("refuse-missing-bytespan", t, "record")

t = copy.deepcopy(exp)
t["records"][0]["atom_scheme"] = "tlsys-v1-occurrence"
expect_refused("refuse-record-scheme", t, "record")

t = copy.deepcopy(exp)
t["counts"]["omitted"] += 1
expect_refused("refuse-omitted", t, "counts", "frontier",
               "retry_identity")

t = copy.deepcopy(exp)
t["completeness"] = "bounded-incomplete"
expect_refused("refuse-forged-completeness", t, "completeness")

t = copy.deepcopy(exp_b)
t["omissions"] = [o for o in t["omissions"]
                  if o not in rec_b["partials"]]
expect_refused("refuse-stripped-partials", t, "omissions")

t = copy.deepcopy(exp)
t["holons"][0]["relations"] = {"cites": ["docA"]}
expect_refused("refuse-present-relations", t, "holon")

t = copy.deepcopy(exp)
del t["absent"]["relations"]
expect_refused("refuse-absent-key", t, "absent")

t = copy.deepcopy(exp)
t["records"][0]["revision"]["resolving_generation"] = "forged:0:0"
expect_refused("refuse-resolving-gen", t, "record")

expect_refused("refuse-nonenvelope", ["not", "a", "dict"], "envelope")

# -- hand-built 0.2 export (independent preimage) ------------------------
import blake3  # noqa: E402

producer02 = {"system": "tlsys",
              "spec_session": SPEC_SESSION,
              "candidate_rev": CANDIDATE_REV,
              "candidate_approval": CANDIDATE_APPROVAL,
              "atom_scheme": "tlsys-v1-occurrence"}
counts02 = {"atoms": 1, "holons": 1, "entries": 1, "omitted": 0}
preimage = {"export_schema": "tl-evidence-export/0.2",
            "producer": {k: producer02[k]
                         for k in ("spec_session", "candidate_rev",
                                   "candidate_approval",
                                   "atom_scheme")},
            "pinned_triple": "b1:0:2",
            "counts": dict(counts02),
            "omissions": 0,
            "errors": 0}
pre_bytes = json.dumps(preimage, sort_keys=True,
                       separators=(",", ":"),
                       ensure_ascii=True).encode("ascii")
exp02 = {
    "export_schema": "tl-evidence-export/0.2",
    "producer": dict(producer02),
    "pinned_generation": {"birth": "b1", "epoch": 0, "seq": 2,
                          "triple": "b1:0:2"},
    "exported_at": "2026-10-05T00:00:00Z",
    "completeness": "complete",
    "counts": dict(counts02),
    "omissions": [],
    "errors": [],
    "absent": {k: {"status": "absent", "reason": f"test [{k}]"}
               for k in ("retirement", "qualifiers", "relations",
                         "valid_time", "archive",
                         "source_revision", "atomizer_config",
                         "byte_span")},
    "records": [{
        "atom_id": "ab" * 32,
        "atom_scheme": "tlsys-v1-occurrence",
        "doc_id": "docA",
        "occurrence": {
            "span": [0, 10], "span_unit": "char",
            "byte_span": {"status": "absent", "reason": "x [A3]"},
            "chunk_ix": 0, "n_chunks": 1,
            "source_revision": {"status": "absent",
                                "reason": "x [A1]"},
            "atomizer_config": {"status": "absent",
                                "reason": "x [A2]"},
        },
        "revision": {"issuing_generation": "b1:0:1",
                     "issuing_seq": 1,
                     "issuing_op_id": "op-1",
                     "resolving_generation": "b1:0:2",
                     "decided_at": 1759536000.0,
                     "retires": {"status": "absent",
                                 "reason": "x [A4]"}},
        "payload": {"text_artifact": "art-t",
                    "text_digest": "sha256:" + "c" * 64,
                    "text_len_bytes": 10,
                    "text_included": True,
                    "text": "0123456789",
                    "meta_artifact": "art-m",
                    "descriptor_included": False},
        "qualifications": {
            "qualifiers": {"status": "absent", "reason": "x [A5]"},
            "integrity": "intact-verified",
            "selection": "selected",
            "marks": {"routing_uncertain": False, "outlier": False,
                      "resolution": "live"}},
    }],
    "holons": [{
        "holon": "docA",
        "holon_ref": "holon:docA:b1:0:2",
        "atom_scheme": "tlsys-v1-occurrence",
        "members": ["ab" * 32],
        "issuing_seq": 2,
        "issuing_op_id": "op-2",
        "descriptor_included": False,
        "relations": {"status": "absent", "reason": "x [A6]"},
    }],
    "coverage_frontier": {"pinned_triple": "b1:0:2", "birth": "b1",
                          "epoch": 0, "max_seq": 2,
                          "kinds_covered": ["ACCEPT_ATOMS"],
                          "atom_scheme": "tlsys-v1-occurrence",
                          "counts_ref": dict(counts02)},
    "retry_identity": {"export_id": "blake3:" + blake3.blake3(
        pre_bytes).hexdigest(), "producer_attempt": 1},
}
got02 = validate_export(exp02)
check("handbuilt-02-importable",
      got02["verdict"] == IMPORTABLE and got02["problems"] == [],
      f"{got02['verdict']} {got02['problems'][:3]}")

t = copy.deepcopy(exp02)
t["producer"]["atom_scheme"] = "tlsys-v2-revision"
expect_refused("refuse-02-wrong-pin", t, "producer")

t = copy.deepcopy(exp02)
t["records"][0]["occurrence"]["byte_span"] = [0, 10]
expect_refused("refuse-02-present-bytespan", t, "record")

t = copy.deepcopy(exp02)
t["records"][0]["qualifications"]["qualifiers"] = {"q": True}
expect_refused("refuse-02-present-qualifiers", t, "record")

tl.close()
tl_e.close()

print(f"{len(FAILS)} failures")
if FAILS:
    print("FAILED:", FAILS)
    sys.exit(1)
print("ALL VALIDATE_EXPORT CHECKS PASSED")
