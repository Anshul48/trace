"""Maintained faithful-export test: TLStore generation -> tl-evidence-export/0.3.

Covers EXPORT-SCHEMA.md (tl-evidence-export/0.3): present A1/A2/A3 +
absent facts A4/A5/A6/A9/A10:
envelope/producer/pin identity, coverage frontier + retry identity,
ordinary occurrence resolution, per-record + envelope absent markers,
empty-store export, scheme-mismatch abort, integrity-failure
withholding, duplicate-occurrence distinctness, dossier+receipt
attachment.

Uses a deterministic fake encoder through the documented embed seam
(README: any encoder), so no model weights are needed. Needs the venv
for blake3. Scratch stores live under /tmp (rebuild-no-migration).
Run: tl-sys/.venv/bin/python tl-sys/tests/test_export.py
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
from tlsys.ingest import chunk_text, ingest_docs  # noqa: E402
from tlsys.export import (  # noqa: E402
    EXPORT_SCHEMA,
    SchemeMismatchError,
    envelope_absent_block,
    export_store,
)
from tlsys.identity import ATOM_SCHEME  # noqa: E402
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


def is_absent(node):
    return (isinstance(node, dict) and node.get("status") == "absent"
            and isinstance(node.get("reason"), str)
            and len(node["reason"]) > 0)


DOC_A = "The domestic cat is a small carnivorous mammal. Cats purr."
DOC_B = "The domestic dog is a loyal companion. Dogs bark loudly."
BOILER = "Identical boilerplate sentence repeated verbatim here."

# -- main store: ordinary docs + duplicate occurrences ------------------
tmp = tempfile.mkdtemp(prefix="tlsys-export-")
sp = os.path.join(tmp, "store")
tl = TLStore(sp, create=True, lease_owner="test-export")
rep = ingest_docs(tl, [("docA", DOC_A), ("docB", DOC_B),
                       ("docD1", BOILER), ("docD2", BOILER)], emb)
check("ingest-counts", rep["n_atoms"] == 4 and rep["n_holons"] == 4,
      f"{rep}")
pinned = tl.pin()
birth, epoch, mx, triple = pinned

exp = export_store(tl)

# -- envelope ------------------------------------------------------------
check("envelope-schema", exp.get("export_schema") == EXPORT_SCHEMA
      == "tl-evidence-export/0.3", f"{exp.get('export_schema')}")
check("envelope-producer",
      exp.get("producer") == {"system": "tlsys",
                              "spec_session": SPEC_SESSION,
                              "candidate_rev": CANDIDATE_REV,
                              "candidate_approval": CANDIDATE_APPROVAL,
                              "atom_scheme": ATOM_SCHEME},
      f"{exp.get('producer')}")
check("envelope-pin",
      exp.get("pinned_generation") == {"birth": birth, "epoch": epoch,
                                       "seq": mx, "triple": triple},
      f"{exp.get('pinned_generation')} vs {pinned}")
check("envelope-exported-at",
      isinstance(exp.get("exported_at"), str)
      and exp["exported_at"].endswith("Z")
      and "T" in exp["exported_at"], f"{exp.get('exported_at')}")
check("envelope-completeness", exp.get("completeness") == "complete",
      f"{exp.get('completeness')}")
check("envelope-counts",
      exp.get("counts") == {"atoms": 4, "holons": 8, "entries": 4,
                            "omitted": 0}, f"{exp.get('counts')}")
check("envelope-omissions-errors",
      exp.get("omissions") == [] and exp.get("errors") == [],
      f"{exp.get('omissions')} {exp.get('errors')}")
check("envelope-no-attachments",
      "receipt" not in exp and "dossier" not in exp
      and "call_trace_summary" not in exp,
      f"{sorted(exp)}")

# -- 0.2 coverage frontier + retry identity -------------------------------
fr = exp.get("coverage_frontier", {})
check("frontier-shape",
      fr.get("pinned_triple") == triple
      and fr.get("birth") == birth
      and fr.get("epoch") == epoch
      and fr.get("max_seq") == mx
      and fr.get("kinds_covered") == ["ACCEPT_ATOMS"]
      and fr.get("atom_scheme") == ATOM_SCHEME
      and fr.get("counts_ref") == exp["counts"],
      f"{fr}")
check("frontier-keys",
      set(fr) == {"pinned_triple", "birth", "epoch", "max_seq",
                  "kinds_covered", "atom_scheme", "counts_ref"},
      f"{sorted(fr)}")
check("frontier-counts-copy",
      fr.get("counts_ref") is not exp.get("counts"),
      "counts_ref aliases live counts")
ri = exp.get("retry_identity", {})
check("identity-shape",
      set(ri) == {"export_id", "producer_attempt"}
      and ri.get("producer_attempt") == 1
      and isinstance(ri.get("export_id"), str)
      and ri["export_id"].startswith("blake3:")
      and len(ri["export_id"]) == 7 + 64,
      f"{ri}")

# -- export_id determinism --------------------------------------------------
exp_again = export_store(tl)
check("identity-deterministic",
      exp_again["retry_identity"]["export_id"]
      == exp["retry_identity"]["export_id"],
      "same store state must yield same id (wall clock excluded)")
# independent recomputation from the EXPORT-SCHEMA.md section 3.3 recipe
from blake3 import blake3 as _b3test  # noqa: E402
_pre = {"export_schema": EXPORT_SCHEMA,
        "producer": {"spec_session": SPEC_SESSION,
                     "candidate_rev": CANDIDATE_REV,
                     "candidate_approval": CANDIDATE_APPROVAL,
                     "atom_scheme": ATOM_SCHEME},
        "pinned_triple": triple,
        "counts": dict(exp["counts"]),
        "omissions": len(exp["omissions"]),
        "errors": len(exp["errors"])}
_canon = json.dumps(_pre, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True).encode("ascii")
check("identity-preimage",
      "blake3:" + _b3test(_canon).hexdigest()
      == exp["retry_identity"]["export_id"],
      "code/spec preimage recipe drift")
# id moves when store state moves (own scratch store; main store untouched)
sp_v = os.path.join(tmp, "store-version")
tl_v = TLStore(sp_v, create=True, lease_owner="test-export-version")
ingest_docs(tl_v, [("docA", DOC_A)], emb)
_id1 = export_store(tl_v)["retry_identity"]["export_id"]
_id1b = export_store(tl_v)["retry_identity"]["export_id"]
ingest_docs(tl_v, [("docB", DOC_B)], emb)
_id2 = export_store(tl_v)["retry_identity"]["export_id"]
check("identity-stable-same-state", _id1 == _id1b, f"{_id1} vs {_id1b}")
check("identity-moves-on-ingest", _id1 != _id2, f"{_id1} vs {_id2}")
tl_v.close()

# -- envelope absent block: A4-A6, A9, A10 (A1/A2/A3 present in 0.3) --
ABS_KEYS = {"retirement": "A4",
            "qualifiers": "A5", "relations": "A6",
            "valid_time": "A9", "archive": "A10"}
absent = exp.get("absent", {})
check("absent-envelope-keys", set(absent) == set(ABS_KEYS),
      f"{sorted(absent)}")
check("absent-envelope-markers",
      all(is_absent(absent.get(k)) for k in ABS_KEYS),
      f"{absent}")
check("absent-envelope-helper", envelope_absent_block() == absent,
      "helper/block drift")
check("absent-no-synthesis",
      all(absent[k].get("status") == "absent" for k in ABS_KEYS)
      and "valid_from" not in json.dumps(exp)
      and "valid_until" not in json.dumps(exp)
      and "tx_time" not in json.dumps(exp)
      and "RETRACT" not in json.dumps(exp),
      "synthetic temporal/retirement content?")

# -- ordinary occurrence resolution (A8: meta join, not read_commits) ----
recs = exp.get("records", [])
check("records-count", len(recs) == 4, f"{len(recs)}")
hols = exp.get("holons", [])
check("holons-count", len(hols) == 8, f"{len(hols)}")
rows = {r[0]: r for r in
        tl.read_commits(birth, epoch, mx, kind="ACCEPT_ATOMS")}
refs = tl.pub_refs(list(rows))
atis = {}
for seq, r in rows.items():
    for art in refs.get(seq, []):
        arow = tl.artifact_row(art)
        body = tl.read_artifact(art, expect_digest=arow[4])
        try:
            meta = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(meta, dict) and "atom" in meta:
            atis[meta["atom"]] = (seq, r, art, meta)
check("meta-join-fixture", len(atis) == 4, f"{len(atis)}")
by_doc = {}
for rec in recs:
    by_doc.setdefault(rec["doc_id"], []).append(rec)
    aid = rec["atom_id"]
    check(f"rec-{aid[:8]}-scheme",
          rec.get("atom_scheme") == ATOM_SCHEME, f"{rec}")
    seq, row, mart, meta = atis[aid]
    _seq, op_id, _k, _ph, _oc, _dis, decided_at = row
    occ = rec["occurrence"]
    rev = rec["revision"]
    pay = rec["payload"]
    qua = rec["qualifications"]
    _src = {"docA": DOC_A, "docB": DOC_B,
            "docD1": BOILER, "docD2": BOILER}[rec["doc_id"]]
    chunks = chunk_text(_src)
    c0, c1, ctext, b0, b1 = chunks[meta["chunk_ix"]]
    want_digest = "sha256:" + hashlib.sha256(
        ctext.encode("utf-8")).hexdigest()
    check(f"rec-{aid[:8]}-occurrence",
          occ.get("span") == [c0, c1]
          and occ.get("span_unit") == "char"
          and occ.get("byte_span") == [b0, b1] == meta["byte_span"]
          and _src.encode("utf-8")[b0:b1].decode("utf-8") == ctext
          and occ.get("chunk_ix") == meta["chunk_ix"] == 0
          and occ.get("n_chunks") == meta["n_chunks"] == 1
          and occ.get("source_revision")
          == {"revision_id": meta["revision_id"]}
          and occ.get("atomizer_config")
          == {"atomizer_config": meta["atomizer_config"]},
          f"{occ}")
    check(f"rec-{aid[:8]}-revision",
          rev.get("issuing_generation") == f"{birth}:{epoch}:{seq}"
          and rev.get("issuing_seq") == seq
          and rev.get("issuing_op_id") == op_id
          and rev.get("resolving_generation") == triple
          and rev.get("decided_at") == decided_at,
          f"{rev} vs row {row}")
    check(f"rec-{aid[:8]}-payload",
          pay.get("text_artifact") == meta["text_artifact"]
          and pay.get("text_digest") == meta["text_digest"]
          == want_digest
          and pay.get("text_len_bytes") == meta["text_len"]
          == len(ctext.encode("utf-8"))
          and pay.get("text_included") is True
          and pay.get("text") == ctext
          and pay.get("meta_artifact") == mart
          and pay.get("descriptor_included") is False
          and "descriptor" not in pay,
          f"{pay}")
    check(f"rec-{aid[:8]}-qualifications",
          qua.get("integrity") == "intact-verified"
          and qua.get("selection") == "selected"
          and qua.get("marks") == {"routing_uncertain": False,
                                   "outlier": False,
                                   "resolution": "live"},
          f"{qua}")
    # per-record absent markers: A4, A5 (A1/A2/A3 present in 0.3)
    check(f"rec-{aid[:8]}-absent",
          is_absent(rev.get("retires"))
          and "A4" in rev["retires"]["reason"]
          and is_absent(qua.get("qualifiers"))
          and "A5" in qua["qualifiers"]["reason"],
          f"{occ} {rev} {qua}")
    check(f"rec-{aid[:8]}-keys",
          set(rec) == {"atom_id", "atom_scheme", "doc_id",
                       "occurrence", "revision", "payload",
                       "qualifications"}
          and set(occ) == {"span", "span_unit", "byte_span",
                           "chunk_ix", "n_chunks", "source_revision",
                           "atomizer_config"},
          f"{sorted(rec)} {sorted(occ)}")

# -- holons ---------------------------------------------------------------
hm = {}
for seq, r in rows.items():
    for art in refs.get(seq, []):
        arow = tl.artifact_row(art)
        body = tl.read_artifact(art, expect_digest=arow[4])
        try:
            meta = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(meta, dict) and "holon" in meta:
            # versioned xdoc metas share one holon id: key by (holon, seq)
            hm[(meta["holon"], seq)] = (seq, r, meta)
for hol in hols:
    doc = hol["holon"]
    seq, row, meta = hm[(doc, hol["issuing_seq"])]
    check(f"hol-{doc}-shape",
          hol.get("holon_ref") == f"holon:{doc}:{triple}"
          and hol.get("atom_scheme") == ATOM_SCHEME
          and hol.get("members") == meta["members"]
          and hol.get("issuing_seq") == seq
          and hol.get("issuing_op_id") == row[1]
          and hol.get("descriptor_included") is False
          and "descriptor" not in hol
          and is_absent(hol.get("relations"))
          and "A6" in hol["relations"]["reason"],
          f"{hol}")
    check(f"hol-{doc}-keys",
          set(hol) == {"holon", "holon_ref", "atom_scheme",
                       "members", "issuing_seq", "issuing_op_id",
                       "descriptor_included", "relations"},
          f"{sorted(hol)}")

# -- A7: duplicate occurrences stay distinct ------------------------------
d1 = by_doc["docD1"][0]
d2 = by_doc["docD2"][0]
check("a7-distinct-atoms", d1["atom_id"] != d2["atom_id"],
      f"{d1['atom_id']} vs {d2['atom_id']}")
check("a7-same-bytes",
      d1["payload"]["text"] == d2["payload"]["text"] == BOILER
      and d1["payload"]["text_digest"]
      == d2["payload"]["text_digest"],
      "same bytes, shared digest expected")
check("a7-no-shared-identity",
      d1["revision"]["issuing_op_id"]
      != d2["revision"]["issuing_op_id"]
      and d1["payload"]["meta_artifact"]
      != d2["payload"]["meta_artifact"],
      "copies must not preserve identity")

# -- exporter options ------------------------------------------------------
exp_nt = export_store(tl, include_text=False)
r0 = exp_nt["records"][0]["payload"]
check("opt-no-text",
      r0.get("text_included") is False and "text" not in r0
      and r0.get("text_digest", "").startswith("sha256:")
      and r0.get("text_len_bytes", 0) > 0,
      f"{r0}")
exp_d = export_store(tl, include_descriptors=True)
rd = exp_d["records"][0]["payload"]
hd = exp_d["holons"][0]
check("opt-descriptors",
      rd.get("descriptor_included") is True
      and isinstance(rd.get("descriptor"), list)
      and len(rd["descriptor"]) == DIM
      and hd.get("descriptor_included") is True
      and isinstance(hd.get("descriptor"), list)
      and len(hd["descriptor"]) == DIM,
      "descriptor inclusion")

# -- receipt / dossier attachment ------------------------------------------
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402

idx = NarrowIndex(tl, pinned)
nq = NarrowQuery(tl, idx, lambda q: fake_vec(q))
dos, rec = nq.run("which animal purrs when content")
exp_a = export_store(tl, dossier=dos, receipt=rec,
                     call_trace=tl.trace)
check("attach-receipt-verbatim", exp_a.get("receipt") == rec,
      "receipt mutated in attach")
check("attach-dossier-verbatim", exp_a.get("dossier") == dos,
      "dossier mutated in attach")
cts = exp_a.get("call_trace_summary", {})
check("attach-call-trace",
      cts.get("candidate_rev") == CANDIDATE_REV
      and isinstance(cts.get("summary"), dict)
      and any(k.startswith("pin/") for k in cts["summary"]),
      f"{cts}")
check("attach-completeness-mirror",
      exp_a.get("completeness")
      == rec["execution"]["status"] == "complete",
      f"{exp_a.get('completeness')}")
check("attach-omissions-carry-partials",
      all(p in exp_a["omissions"] for p in rec.get("partials", [])),
      f"{exp_a['omissions']} vs {rec.get('partials')}")
# attachment must not rewrite export identity/counts
check("attach-counts-stable",
      exp_a["counts"] == exp["counts"]
      and exp_a["pinned_generation"] == exp["pinned_generation"]
      and [r["atom_id"] for r in exp_a["records"]]
      == [r["atom_id"] for r in exp["records"]],
      "attachment changed export body")
check("identity-attachment-stable",
      exp_a["retry_identity"]["export_id"]
      == exp["retry_identity"]["export_id"]
      and exp_a["coverage_frontier"] == exp["coverage_frontier"],
      "caller attachments must not move the store-claim seal")
# bounded-incomplete receipt mirrors into completeness + omissions
nq_tiny = NarrowQuery(tl, idx, lambda q: fake_vec(q),
                      cfg={"WORK_BUDGET": 0})
dos_b, rec_b = nq_tiny.run("which animal purrs when content")
check("bounded-fixture",
      rec_b["execution"]["status"] == "bounded-incomplete",
      f"{rec_b['execution']}")
exp_b = export_store(tl, receipt=rec_b)
check("bounded-mirror",
      exp_b.get("completeness") == "bounded-incomplete"
      and all(p in exp_b["omissions"] for p in rec_b["partials"])
      and len(exp_b["records"]) == 4,
      f"{exp_b.get('completeness')} {exp_b.get('omissions')}")

# -- empty store is a valid export ------------------------------------------
sp_e = os.path.join(tmp, "store-empty")
tl_e = TLStore(sp_e, create=True, lease_owner="test-export-empty")
pin_e = tl_e.pin()
check("empty-pin", pin_e[3] == "empty:0:0", f"{pin_e}")
exp_e = export_store(tl_e)
check("empty-export",
      exp_e.get("completeness") == "complete"
      and exp_e.get("records") == []
      and exp_e.get("holons") == []
      and exp_e.get("counts") == {"atoms": 0, "holons": 0,
                                  "entries": 0, "omitted": 0}
      and exp_e.get("omissions") == []
      and exp_e.get("errors") == []
      and exp_e.get("pinned_generation") == {"birth": "empty",
                                             "epoch": 0, "seq": 0,
                                             "triple": "empty:0:0"}
      and set(exp_e.get("absent", {})) == set(ABS_KEYS),
      f"{exp_e}")
fr_e = exp_e.get("coverage_frontier", {})
check("empty-frontier",
      fr_e == {"pinned_triple": "empty:0:0", "birth": "empty",
               "epoch": 0, "max_seq": 0,
               "kinds_covered": ["ACCEPT_ATOMS"],
               "atom_scheme": ATOM_SCHEME,
               "counts_ref": {"atoms": 0, "holons": 0,
                              "entries": 0, "omitted": 0}},
      f"{fr_e}")
check("empty-identity",
      exp_e.get("retry_identity", {}).get("producer_attempt") == 1
      and exp_e["retry_identity"]["export_id"].startswith("blake3:")
      and export_store(tl_e)["retry_identity"]["export_id"]
      == exp_e["retry_identity"]["export_id"],
      f"{exp_e.get('retry_identity')}")
tl_e.close()

# -- scheme mismatch aborts --------------------------------------------------
from tlsys.store_if import prepare_artifact, uuidv7  # noqa: E402

sp_leg = os.path.join(tmp, "store-legacy")
tl_leg = TLStore(sp_leg, create=True, lease_owner="test-export-leg")
_tart = prepare_artifact(tl_leg.store, b"legacy bytes", "s-leg")
_mart = prepare_artifact(
    tl_leg.store,
    json.dumps({"atom": "a" * 64, "doc_id": "docLeg",
                "chunk_ix": 0, "n_chunks": 1, "span": [0, 12],
                "text_len": 12,
                "text_artifact": _tart["artifact_id"],
                "text_digest": _tart["digest"],
                "descriptor": [0.0] * DIM}).encode(), "s-leg")
tl_leg.commit_batch([{
    "op_id": uuidv7(), "kind": "ACCEPT_ATOMS",
    "payload": {"atom": "a" * 64, "doc_id": "docLeg",
                "meta_artifact": _mart["artifact_id"]},
    "disclosure": {"leg": "test-export-legacy"},
    "approval_ref": None, "artifacts": (_tart, _mart)}])
try:
    export_store(tl_leg)
    check("scheme-abort", False, "mixed schemes silently")
except SchemeMismatchError as e:
    errs = (e.export or {}).get("errors", []) if hasattr(e, "export") \
        else []
    check("scheme-abort",
          any(x.get("scope") == "store"
              and "scheme-mismatch" in x.get("cause", "")
              for x in errs),
          f"{errs}")
    check("scheme-abort-unsealed",
          "coverage_frontier" not in (e.export or {})
          and "retry_identity" not in (e.export or {}),
          "aborted claim must not carry sealed blocks")
except ValueError as e:
    check("scheme-abort", "scheme-mismatch" in str(e), f"{e}")
tl_leg.close()

# -- integrity failure withholds with omission entry ------------------------
sp_c = os.path.join(tmp, "store-corrupt")
tl_c = TLStore(sp_c, create=True, lease_owner="test-export-corrupt")
ingest_docs(tl_c, [("docA", DOC_A), ("docB", DOC_B)], emb)
pin_c = tl_c.pin()
rows_c = tl_c.read_commits(*pin_c[:3], kind="ACCEPT_ATOMS")
refs_c = tl_c.pub_refs([r[0] for r in rows_c])
victim_aid = None
victim_art = None
for r in rows_c:
    for art in refs_c.get(r[0], []):
        arow = tl_c.artifact_row(art)
        body = tl_c.read_artifact(art, expect_digest=arow[4])
        try:
            meta = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(meta, dict) and meta.get("doc_id") == "docA" \
                and "atom" in meta:
            victim_aid = meta["atom"]
            victim_art = meta["text_artifact"]
check("corrupt-fixture", bool(victim_aid and victim_art),
      f"{victim_aid} {victim_art}")
with open(os.path.join(tl_c.store.artdir, victim_art), "r+b") as f:
    b = bytearray(f.read())
    b[0] ^= 0xFF
    f.seek(0)
    f.write(b)
exp_c = export_store(tl_c)
aids_c = [r["atom_id"] for r in exp_c["records"]]
check("corrupt-withheld", victim_aid not in aids_c, f"{aids_c}")
check("corrupt-survivor", len(aids_c) == 1
      and exp_c["records"][0]["doc_id"] == "docB", f"{aids_c}")
check("corrupt-omission",
      {"scope": f"candidate:{victim_aid[:16]}",
       "cause": "integrity-failed:withheld"} in exp_c["omissions"],
      f"{exp_c['omissions']}")
check("corrupt-counts",
      exp_c["counts"] == {"atoms": 1, "holons": 4, "entries": 1,
                          "omitted": 1}
      and exp_c["completeness"] == "complete",
      f"{exp_c['counts']}")
check("corrupt-frontier",
      exp_c.get("coverage_frontier", {}).get("counts_ref")
      == exp_c["counts"]
      and exp_c["coverage_frontier"]["pinned_triple"]
      == exp_c["pinned_generation"]["triple"],
      f"{exp_c.get('coverage_frontier')}")
tl_c.close()

# -- export is read-only w.r.t. the store ------------------------------------
check("export-readonly", tl.pin()[3] == triple,
      f"{tl.pin()[3]} != {triple}")
# export output is self-contained: mutating the caller's receipt copy
# after attach must not alias the exported body
rec_copy = copy.deepcopy(rec)
exp_alias = export_store(tl, receipt=rec_copy)
rec_copy["execution"]["status"] = "MUTATED"
check("export-no-alias",
      exp_alias["receipt"]["execution"]["status"] == "complete",
      f"{exp_alias['receipt']['execution']}")

tl.close()
print("store-root:", tmp)
print("RESULT:", "FAIL " + str(FAILS) if FAILS else "PASS")
sys.exit(1 if FAILS else 0)
