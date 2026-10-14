"""Lane-2 closure + v3 repair: approval-gated retirement -> serving
exclusion -> export omission, plus projection checkpoint delta I/O.

Covers tl-sys/tlsys/lifecycle.py, the retirement consumption in
index/query/export/maint/proj, and the proj delta-journal checkpoint.
Deterministic fake encoder, scratch stores under /tmp. Failure-first:
this file was written before the implementation.

V3: every newly retiring op declares `retires` and carries a
per-operation stage-2 approval_ref (payload diff_hash + pin + policy +
scope) through the untouched core gate. Approvals below are
explicitly-labeled TEST FIXTURES exercising the ref contract shape;
they are not operator consent and never retroactively approve
pre-repair markers (old markers stay valid history, honored as-is).

Run: tl-sys/.venv/bin/python tl-sys/tests/test_m2c_retire.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore, prepare_artifact, uuidv7
from tlsys.identity import ATOM_SCHEME
from tlsys.ingest import ingest_docs
from tlsys.index import NarrowIndex
from tlsys.query import NarrowQuery
from tlsys.maint import organize_segments
from tlsys.export import export_store
from tlsys.proj import Projections
from tlsys.lifecycle import (retire_docs, read_retirements,
                             retirement_op, build_approval_ref)

FAILS = []


def fixture_approval(tag):
    """Explicitly-labeled test fixture leg (NOT operator consent)."""
    return {"type": "user", "approval_id": "fixture-v3-" + tag}


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 8


def pad(v):
    return [float(x) for x in v] + [0.0] * (DIM - len(v))


V_SPORT = pad([1.0, 0.0, 0.0, 0.0])
V_MED = pad([0.0, 1.0, 0.0, 0.0])


def emb(texts):
    out = []
    for t in texts:
        votes = [(t.count("sport"), V_SPORT), (t.count("medic"), V_MED)]
        votes.sort(key=lambda kv: -kv[0])
        out.append(list(votes[0][1]))
    return out


def emb1(q):
    return emb([q])[0]


def run_of(word, n, start=0):
    return " ".join(f"{word}{i}" for i in range(start, start + n))


def main():
    tmp = tempfile.mkdtemp(prefix="tlsys-lane2-")
    root = os.path.join(tmp, "store")
    tl = TLStore(root, create=True, lease_owner="test-lane2")
    docs = [(f"sport-{i}", run_of("sport", 150, 200 * i))
            for i in range(4)]
    docs += [(f"med-{i}", run_of("medic", 150, 5000 + 200 * i))
             for i in range(4)]
    ingest_docs(tl, docs, emb)
    organize_segments(tl)

    # -- retirement report + oracle ----------------------------------
    rep = retire_docs(tl, ["med-0"], reason="lane2-probe",
                      approvals={"med-0":
                                 fixture_approval("retire-med-0")})
    check("retire-report-keys",
          set(rep) == {"retired", "already_retired", "ops", "seqs",
                       "n_commits", "catchup"}
          and rep["retired"] == ["med-0"] and rep["n_commits"] == 1,
          f"{rep}")
    pin = tl.pin()
    oracle = read_retirements(tl, pin)
    check("retire-oracle",
          set(oracle) == {"med-0"}
          and set(oracle["med-0"]) == {"seq", "op_id", "reason"}
          and oracle["med-0"]["op_id"] == rep["ops"]["med-0"]
          and oracle["med-0"]["seq"] == rep["seqs"]["med-0"]
          and oracle["med-0"]["reason"] == "lane2-probe",
          f"{oracle}")
    _ack_outcome, _ack_triple = tl.cm.notify(rep["ops"]["med-0"])
    _ack = json.loads(_ack_outcome)
    check("retire-ack",
          _ack.get("committed") is True
          and _ack.get("seq") == rep["seqs"]["med-0"]
          and _ack.get("kind") == "ACCEPT_ATOMS",
          f"{_ack_outcome} {_ack_triple}")
    # No-effect retry needs no approval (nothing is committed).
    rep2 = retire_docs(tl, ["med-0"])
    check("retire-retry-idempotent",
          rep2["retired"] == [] and rep2["already_retired"] == ["med-0"]
          and rep2["n_commits"] == 0, f"{rep2}")
    try:
        retire_docs(tl, ["nope-missing"])
        check("retire-unknown-raises", False, "no ValueError")
    except ValueError:
        check("retire-unknown-raises", True)

    # -- serving exclusion -------------------------------------------
    idx = NarrowIndex(tl, pin)
    check("serve-index-excludes",
          idx.retired_docs == ["med-0"] and idx.retired_atoms >= 1
          and all(a["doc_id"] != "med-0" for a in idx.atoms.values())
          and "med-0" not in idx.holons
          and all("med-0" != d for d in idx.doc_atoms),
          f"{idx.retired_docs} {idx.retired_atoms}")
    nq = NarrowQuery(tl, idx, emb1)
    dos, rec = nq.run("medic")
    check("serve-entries-exclude",
          all(e["doc_id"] != "med-0" for e in dos["entries"])
          and len(dos["entries"]) >= 1, f"{dos}")
    check("serve-receipt-discloses",
          set(rec["metrics"].get("retired", {}))
          == {"docs", "atoms_excluded"}
          and rec["metrics"]["retired"]["docs"] == ["med-0"],
          f"{rec['metrics'].get('retired')}")

    # -- export omission ----------------------------------------------
    exp = export_store(tl)
    want = {"scope": "doc:med-0",
            "cause": "retired:" + rep["ops"]["med-0"],
            "seq": rep["seqs"]["med-0"],
            "atoms_withheld": idx.retired_atoms}
    check("export-omission-identity",
          want in exp["omissions"]
          and all(set(o) == {"scope", "cause", "seq", "atoms_withheld"}
                  for o in exp["omissions"]
                  if o.get("scope") == "doc:med-0")
          and exp["counts"]["retired_docs"] == 1
          and all(r["doc_id"] != "med-0" for r in exp["records"])
          and all(h["holon"] != "med-0" for h in exp["holons"]),
          f"{exp['omissions']} {exp['counts']}")

    # -- retry + reopen: identical exclusion + omission identities ----
    tl.close()
    tl_r = TLStore(root, create=False, lease_owner="test-lane2-reopen")
    pin_r = tl_r.pin()
    idx_r = NarrowIndex(tl_r, pin_r)
    dos_r, rec_r = NarrowQuery(tl_r, idx_r, emb1).run("medic")
    exp_r = export_store(tl_r)
    check("reopen-stable",
          idx_r.retired_docs == ["med-0"]
          and all(e["doc_id"] != "med-0" for e in dos_r["entries"])
          and want in exp_r["omissions"]
          and exp_r["counts"]["retired_docs"] == 1,
          f"{idx_r.retired_docs} {exp_r['omissions']}")
    # Mixed retry: already-retired med-0 needs no entry; med-1 does.
    rep3 = retire_docs(tl_r, ["med-0", "med-1"],
                       approvals={"med-1":
                                  fixture_approval("retire-med-1")})
    check("reopen-retry",
          rep3["already_retired"] == ["med-0"]
          and rep3["retired"] == ["med-1"], f"{rep3}")
    # organize skips retired docs (additive key, no behavior change else)
    org = organize_segments(tl_r, ["med-1"])
    check("organize-skips-retired",
          org.get("retired_skipped") == ["med-1"]
          and "med-1" not in org["organized"], f"{org}")
    tl_r.close()

    # -- v3 approval gating: refused paths fail closed ---------------
    tmp_g = tempfile.mkdtemp(prefix="tlsys-v3-gate-")
    tl_g = TLStore(os.path.join(tmp_g, "store"), create=True,
                   lease_owner="test-v3-gate")
    ingest_docs(tl_g, docs[:2], emb)
    _pin_g0 = tl_g.pin()
    _mx0 = _pin_g0[2]
    _exp_g0 = export_store(tl_g)
    try:
        retire_docs(tl_g, ["sport-0"], reason="v3-refused")
        check("gate-missing-fails-closed", False, "no ValueError")
    except ValueError:
        check("gate-missing-fails-closed", tl_g.pin()[2] == _mx0,
              "seq moved without approval")
    try:
        retire_docs(tl_g, ["sport-0", "sport-1"], reason="v3-refused",
                    approvals={"sport-1":
                               fixture_approval("partial")})
        check("gate-partial-fails-closed", False, "no ValueError")
    except ValueError:
        check("gate-partial-fails-closed", tl_g.pin()[2] == _mx0,
              "partial call committed")
    for _tag, _leg in (("no-id", {"type": "user"}),
                       ("bad-type", {"type": "llm"}),
                       ("not-dict", "fixture-v3-x")):
        try:
            retire_docs(tl_g, ["sport-0"], reason="v3-refused",
                        approvals={"sport-0": _leg})
            check(f"gate-malformed-{_tag}-fails-closed", False,
                  "no ValueError")
        except ValueError:
            check(f"gate-malformed-{_tag}-fails-closed",
                  tl_g.pin()[2] == _mx0, "malformed call committed")
    _pin_g1 = tl_g.pin()
    _idx_g1 = NarrowIndex(tl_g, _pin_g1)
    _dos_g1, _rec_g1 = NarrowQuery(tl_g, _idx_g1, emb1).run("sport")
    _exp_g1 = export_store(tl_g)
    check("gate-refused-eligibility-unchanged",
          _idx_g1.retired_docs == []
          and any(e["doc_id"] == "sport-0"
                  for e in _dos_g1["entries"])
          and "retired" not in _rec_g1["metrics"]
          and _exp_g1["counts"] == _exp_g0["counts"]
          and _exp_g1["omissions"] == _exp_g0["omissions"],
          f"{_idx_g1.retired_docs} {_exp_g1['counts']}")

    # Declared effect without a ref: the untouched core refuses.
    _prep_g = lambda bb, sid: prepare_artifact(  # noqa: E731
        tl_g.store, bb, sid)
    _bare = retirement_op("sport-0", "v3-bare", "tl-sys-docs", _prep_g)
    check("gate-op-declares-effect",
          _bare["payload"].get("retires") == "sport-0"
          and _bare["approval_ref"] is None, f"{_bare['payload']}")
    _res_bare, _ = tl_g.commit_batch([_bare])
    check("gate-bare-core-refuses",
          _res_bare[0].get("status") == "terminal"
          and _res_bare[0].get("code") == "APPROVAL_MISSING"
          and tl_g.pin()[2] == _mx0, f"{_res_bare}")

    # Tampered binding: diff_hash no longer covers the payload.
    _op_t = retirement_op("sport-0", "v3-tamper", "tl-sys-docs",
                          _prep_g)
    _ref_t = build_approval_ref(tl_g, _op_t["payload"],
                                fixture_approval("tamper"), "sport-0")
    _ref_t["assessment"]["diff_hash"] = "0" * 64
    _op_t["approval_ref"] = _ref_t
    _res_t, _ = tl_g.commit_batch([_op_t])
    check("gate-tampered-core-refuses",
          _res_t[0].get("status") == "terminal"
          and _res_t[0].get("code") == "REF_MALFORMED"
          and tl_g.pin()[2] == _mx0, f"{_res_t}")

    # Stale pin: a sibling ACCEPT_ATOMS commit lands between pin+gate.
    _op_s = retirement_op("sport-0", "v3-stale", "tl-sys-docs",
                          _prep_g)
    _ref_s = build_approval_ref(tl_g, _op_s["payload"],
                                fixture_approval("stale"), "sport-0",
                                pinned=tl_g.pin())
    ingest_docs(tl_g, [("sport-9", run_of("sport", 150, 99999))],
                emb)
    _op_s["approval_ref"] = _ref_s
    _res_s, _ = tl_g.commit_batch([_op_s])
    check("gate-stale-pin-core-refuses",
          _res_s[0].get("status") == "raised"
          and _res_s[0].get("code") == "STALE_ASSESSMENT",
          f"{_res_s}")

    # Approved path on the same store after refusals: commits+excludes.
    _mx_pre = tl_g.pin()[2]
    _rep_g = retire_docs(tl_g, ["sport-0"], reason="v3-approved",
                         approvals={"sport-0":
                                    fixture_approval("approve-sport-0")})
    _pin_g2 = tl_g.pin()
    check("gate-approved-commits",
          _rep_g["retired"] == ["sport-0"]
          and _rep_g["n_commits"] == 1
          and _pin_g2[2] == _mx_pre + 1
          and _rep_g["seqs"]["sport-0"] == _pin_g2[2],
          f"{_rep_g} mx={_mx_pre}->{_pin_g2[2]}")
    _idx_g2 = NarrowIndex(tl_g, _pin_g2)
    _dos_g2, _rec_g2 = NarrowQuery(tl_g, _idx_g2, emb1).run("sport")
    _exp_g2 = export_store(tl_g)
    check("gate-approved-excludes",
          _idx_g2.retired_docs == ["sport-0"]
          and all(e["doc_id"] != "sport-0"
                  for e in _dos_g2["entries"])
          and _rec_g2["metrics"]["retired"]["docs"] == ["sport-0"]
          and {"scope": "doc:sport-0",
               "cause": "retired:" + _rep_g["ops"]["sport-0"],
               "seq": _rep_g["seqs"]["sport-0"],
               "atoms_withheld": _idx_g2.retired_atoms}
          in _exp_g2["omissions"],
          f"{_idx_g2.retired_docs} {_exp_g2['omissions']}")
    _con = tl_g.store.open_db()
    try:
        _arow = _con.execute(
            "SELECT approval_ref FROM commits WHERE seq=?",
            (_rep_g["seqs"]["sport-0"],)).fetchone()
    finally:
        _con.close()
    _aref = json.loads(_arow[0])
    check("gate-approved-ref-bound",
          _aref.get("stage") == 2
          and _aref.get("scope") == "ACCEPT_ATOMS"
          and _aref.get("policy_version")
          == tl_g.current_policy_version()
          and _aref.get("pinned_generation")
          == [_pin_g0[0], _pin_g0[1], _mx_pre]
          and _aref.get("approval", {}).get("approval_id")
          == "fixture-v3-approve-sport-0",
          f"{_aref}")
    tl_g.close()

    # Pre-repair marker shape stays valid history (readers unchanged).
    tmp_l = tempfile.mkdtemp(prefix="tlsys-v3-legacy-")
    tl_l = TLStore(os.path.join(tmp_l, "store"), create=True,
                   lease_owner="test-v3-legacy")
    ingest_docs(tl_l, docs[:2], emb)
    _prep_l = lambda bb, sid: prepare_artifact(  # noqa: E731
        tl_l.store, bb, sid)
    _meta_l = {"retirement": {"doc": "sport-1",
                              "reason": "pre-repair"},
               "atom_scheme": ATOM_SCHEME}
    _mart_l = _prep_l(json.dumps(_meta_l, sort_keys=True).encode(),
                      "tl-sys-docs")
    _op_l = {"op_id": uuidv7(), "kind": "ACCEPT_ATOMS",
             "payload": {"retirement": "sport-1",
                         "meta_artifact": _mart_l["artifact_id"]},
             "disclosure": {"leg": "retire", "doc_id": "sport-1"},
             "approval_ref": None, "artifacts": (_mart_l,)}
    _res_l, _ = tl_l.commit_batch([_op_l])
    _pin_l = tl_l.pin()
    _idx_l = NarrowIndex(tl_l, _pin_l)
    _exp_l = export_store(tl_l)
    check("legacy-unapproved-marker-honored",
          _res_l[0].get("status") == "committed"
          and _idx_l.retired_docs == ["sport-1"]
          and _exp_l["counts"].get("retired_docs") == 1
          and any(o.get("scope") == "doc:sport-1"
                  for o in _exp_l["omissions"]),
          f"{_res_l} {_idx_l.retired_docs}")
    tl_l.close()

    # -- retirement-free stores stay byte-identical --------------------
    tmp_c = tempfile.mkdtemp(prefix="tlsys-lane2-clean-")
    tl_c = TLStore(os.path.join(tmp_c, "store"), create=True,
                   lease_owner="test-lane2-clean")
    ingest_docs(tl_c, docs[:2], emb)
    pin_c = tl_c.pin()
    idx_c = NarrowIndex(tl_c, pin_c)
    _d, rec_c = NarrowQuery(tl_c, idx_c, emb1).run("sport")
    exp_c = export_store(tl_c)
    check("clean-no-retired-keys",
          "retired" not in rec_c["metrics"]
          and "retired_docs" not in exp_c["counts"]
          and set(exp_c["counts"])
          == {"atoms", "holons", "entries", "omitted"}
          and idx_c.retired_docs == [], f"{exp_c['counts']}")
    tl_c.close()

    # -- checkpoint delta I/O ------------------------------------------
    tmp_p = tempfile.mkdtemp(prefix="tlsys-lane2-proj-")
    tl_p = TLStore(os.path.join(tmp_p, "store"), create=True,
                   lease_owner="test-lane2-proj")
    proj = Projections()
    ingest_docs(tl_p, docs, emb)
    organize_segments(tl_p, projections=proj)
    proj.update(tl_p)
    proj.save(tl_p)  # full snapshot once
    snap0 = os.path.getsize(Projections.checkpoint_path(tl_p))
    juni0 = os.path.getsize(Projections.journal_path(tl_p)) \
        if os.path.isfile(Projections.journal_path(tl_p)) else 0
    ingest_docs(tl_p, [("sport-new", run_of("sport", 150, 20000))],
                emb, place_xdoc=False)
    cup = proj.update(tl_p)
    proj.save(tl_p)  # delta append only
    juni1 = os.path.getsize(Projections.journal_path(tl_p))
    check("ckpt-delta-bounded",
          cup["cold"] is False and cup["commits"] <= 3
          and juni1 - juni0 < snap0 // 2,
          f"cup={cup} snap={snap0} djournal={juni1 - juni0}")
    live_l = set(proj.hierarchy_view()["leaves"])
    proj_ld = Projections.load(tl_p)
    cup_ld = proj_ld.update(tl_p)
    check("ckpt-load-replay-equal",
          cup_ld["commits"] == 0
          and set(proj_ld.hierarchy_view()["leaves"]) == live_l
          and proj_ld.retired_view() == proj.retired_view(),
          f"{cup_ld}")
    c1 = Projections.cached(tl_p)
    c2 = Projections.cached(tl_p)
    check("ckpt-cached-warm", c1 is c2, "no warm reuse")
    proj_ld.compact(tl_p)
    check("ckpt-compact",
          not os.path.isfile(Projections.journal_path(tl_p))
          and set(Projections.load(tl_p).hierarchy_view()["leaves"])
          == live_l
          and Projections.load(tl_p).retired_view()
          == proj.retired_view(),
          "compact broke replay")
    with open(Projections.journal_path(tl_p), "a") as f:
        f.write("{corrupt\n")
    proj_bad = Projections.load(tl_p)
    cup_bad = proj_bad.update(tl_p)
    check("ckpt-corrupt-cold-rebuild",
          cup_bad["cold"] is True
          and set(proj_bad.hierarchy_view()["leaves"]) == live_l,
          f"{cup_bad}")
    tl_p.close()

    print("store-root:", tmp)
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
