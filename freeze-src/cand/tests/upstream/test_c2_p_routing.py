"""C2 Closure P (§5.2): R_cat pre-execution boundary + session routing.

Pins R_cat as a pre-execution resource boundary on the keyed producer
path (count native rows + both leaf masks + head copies/sorts + all
calls in one operation; reject BEFORE over-budget work; never truncate
exact populations), producer-session catalog/reverse-index reuse by
incarnation/frontier + committed deltas, and persisted restart-ready
routing snapshots with digest validation. All pins are
structural/deterministic — no wall-clock assertions.

Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_p_routing.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "coordination", "c2-work-20261006T1925Z", "lane-G")))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "tl-eval", "gate_runner")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.maint import (drain_placement_backlog,  # noqa: E402
                         organize_segments)
from tlsys.prodstate import (ProducerSession,  # noqa: E402
                             estimate_op_cost)
from profile import default_profile  # noqa: E402  (Lane G, read-only)
from gate_lib import snapshot_store  # noqa: E402  (fence-safe copy)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def prof_on(pid):
    p = default_profile(profile_id=pid,
                        calibration_manifest_id="seed-host-20261006")
    p["flags"]["organization_catalog_routing"] = True
    return p


def emb8(texts):
    out = []
    for t in texts:
        w = t.split()[0] if t.split() else ""
        v = [0.0] * 8
        if w.startswith("sport"):
            v[0], v[1] = 1.0, 0.1
        elif w.startswith("medic"):
            v[0], v[1] = 0.1, 1.0
        else:
            v[2] = 1.0
        out.append(v)
    return out


def run_of(word, n, start=0):
    return " ".join(f"{word}{start + i}" for i in range(n))


DOCS = [("r-a", run_of("sport", 12, 0)),
        ("r-b", run_of("sport", 12, 5000)),
        ("r-c", run_of("medic", 12, 9000)),
        ("r-d", run_of("other", 12, 30000))]


def fresh_store(prefix="tlsys-p-rt-"):
    tmp = tempfile.mkdtemp(prefix=prefix)
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="test-c2-p-rt")
    return tmp, tl


def hier_sig(tl):
    """Hierarchy signature from committed seg metas (D2 compare).

    Atom ids bind the store's random revision_id, so cross-store
    membership compares by (doc_id, span) occurrence signature (same
    convention as test_m2a_org seg-determinism); member ORDER and
    descriptors compare exactly.
    """
    import json as _j
    birth, epoch, mx, _t = tl.pin()
    rows = tl.read_commits(birth, epoch, mx, kind="ACCEPT_ATOMS",
                           limit=1000000)
    refs = tl.pub_refs([r[0] for r in rows])
    metas = []
    for seq in [r[0] for r in rows]:
        for art_id in refs.get(seq, []):
            arow = tl.artifact_row(art_id)
            if arow is None:
                continue
            try:
                meta = _j.loads(tl.read_artifact(
                    art_id, expect_digest=arow[4]).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(meta, dict):
                metas.append(meta)
    aidmap = {}
    for meta in metas:
        if "atom" in meta and "doc_id" in meta:
            aidmap[meta["atom"]] = (meta["doc_id"],
                                    tuple(meta.get("span", ())))
    sig = {}
    for meta in metas:
        if meta.get("kind") in ("seg-leaf", "seg-parent"):
            sig[meta["holon"]] = (
                tuple(aidmap.get(a, ("?", ())) for a in
                meta.get("members", ())),
                tuple(meta.get("children", ())),
                tuple(round(float(x), 12)
                      for x in meta.get("descriptor", [])))
    return sig


def main():
    # -- R. estimator: complete measured cost, no sharing ------------
    est1 = estimate_op_cost("xholon", n=100, rows_per_call=[40],
                            dim=8, k_per_call=[3])
    check("p-gate-est-one-call",
          est1["calls"] == 1 and est1["mask_rows"] == [40]
          and est1["bound_native_rows"] == 100
          and est1["budget_rows"] is None
          and est1["sort_temp_bound_B"] > 0
          and est1["mask_bytes"] > 0, f"{est1}")
    est2 = estimate_op_cost("leaf", n=100, rows_per_call=[40, 60],
                            dim=8, k_per_call=[2, 100])
    check("p-gate-est-two-calls",
          est2["calls"] == 2 and est2["mask_rows"] == [40, 60]
          and est2["bound_native_rows"] == 200, f"{est2}")
    estb = estimate_op_cost("leaf", n=10, rows_per_call=[4, 6],
                            dim=8, k_per_call=[2, 10], rcat=6)
    check("p-gate-est-over",
          estb["budget_rows"] == 12 and estb["over_budget"] is True,
          f"{estb}")
    estok = estimate_op_cost("leaf", n=10, rows_per_call=[4, 6],
                             dim=8, k_per_call=[2, 10], rcat=65536)
    check("p-gate-est-under", estok["over_budget"] is False, f"{estok}")

    # -- G. keyed gate: under-budget executes exactly -----------------
    _tmpr, tlr = fresh_store()
    prof = prof_on("p-rt")
    repr_ = ingest_docs(tlr, DOCS, emb8, store_id="p", profile=prof,
                        keyed_state=True)
    check("p-gate-ingest-executes",
          repr_["n_atoms"] == 4 and repr_["n_holons"] == 4
          and repr_["catalog"]["over_budget"] is False
          and repr_["catalog"]["rejected"] == [], f"{repr_}")
    check("p-gate-ingest-cost",
          repr_["keyed"]["rcat_estimates"] is not None
          and len(repr_["keyed"]["rcat_estimates"]) == 4
          and all(e["estimate"]["over_budget"] is False
                  for e in repr_["keyed"]["rcat_estimates"]),
          "pre-execution estimates receipted")
    orgr = organize_segments(tlr, profile=prof, keyed_state=True)
    check("p-gate-organize-executes",
          len(orgr["organized"]) == 4
          and orgr["catalog"]["over_budget"] is False
          and orgr["catalog"]["rejected"] == [], f"{orgr}")
    sig_key = hier_sig(tlr)
    # A second keyed call without a session restores routing from the
    # persisted snapshots (no full catalog rebuild) and serves
    # identical decisions.
    ingest_docs(tlr, [("r-z", run_of("medic", 12, 81000))], emb8,
                store_id="p", profile=prof, keyed_state=True)
    org_r2 = organize_segments(tlr, profile=prof, keyed_state=True)
    check("p-gate-no-rebuild-second-call",
          org_r2["organized"] == ["r-z"]
          and org_r2["keyed"]["routing"]["rebuilt_rows"] == 0
          and sorted(org_r2["keyed"]["routing"]["restored"])
          == ["leaf", "parent"], f"{org_r2}")
    tlr.close()
    # Same decisions as the legacy reference path (D2 parity).
    _tmpr2, tlr2 = fresh_store(prefix="tlsys-p-rt-leg-")
    ingest_docs(tlr2, DOCS, emb8, store_id="p")
    organize_segments(tlr2)
    check("p-gate-d2-parity", hier_sig(tlr2) == sig_key,
          "keyed+gated decisions differ from reference")
    tlr2.close()

    # -- J. keyed gate: over-budget rejects BEFORE work ---------------
    # Pre-build a 2-version xdoc population + 2 leaves under a normal
    # budget (sport/medic never join at T=0.55: deterministic mints).
    _tmpj, tlj = fresh_store(prefix="tlsys-p-rt-rej-")
    p_pre = prof_on("p-rt-pre")
    ingest_docs(tlj, DOCS[:3:2], emb8, store_id="p", profile=p_pre,
                keyed_state=True)
    org_pre = organize_segments(tlj, profile=p_pre, keyed_state=True)
    check("p-gate-prebuilt",
          sorted(org_pre["organized"]) == ["r-a", "r-c"]
          and org_pre["retained"]["leaves"] == 2, f"{org_pre}")
    p_small = prof_on("p-rt-small")
    p_small["derived_limits"]["R_cat"] = 1
    repj = ingest_docs(tlj, [("r-x", run_of("other", 12, 70000))],
                       emb8, store_id="p", profile=p_small,
                       keyed_state=True)
    # Atoms + per-doc holon still commit (acknowledged +
    # retrievable); placement defers with a named reason.
    check("p-gate-reject-defers",
          repj["n_atoms"] == 1 and repj["n_holons"] == 1
          and len(repj["catalog"]["rejected"]) == 1
          and "over-budget" in repj["catalog"]["rejected"][0]["reason"]
          and repj["pending_placement"] == ["r-x"], f"{repj}")
    # Zero placement scans executed on the rejected leg: the catalog
    # mirror exists (n=2) but no top_k ran through it.
    check("p-gate-reject-no-work",
          repj["catalog"]["decisions"] == 0
          and repj["catalog"]["xholon"]["n"] == 2
          and repj["catalog"]["xholon"]["calls"] == 0
          and repj["catalog"]["xholon"]["rows"] == 0,
          f"{repj['catalog']}")
    pin_j = tlj.pin()[3]
    orgj = organize_segments(tlj, profile=p_small, keyed_state=True)
    check("p-gate-organize-rejects",
          orgj["organized"] == []
          and list(orgj["failed"]) == ["r-x"]
          and "over-budget" in orgj["failed"]["r-x"], f"{orgj}")
    check("p-gate-reject-pin-stable",
          tlj.pin()[3] == pin_j and orgj["n_commits"] == 0,
          "rejected legs commit nothing")
    tlj.close()

    # -- S. producer-session routing reuse + restart ----------------
    _tmps, tls = fresh_store(prefix="tlsys-p-rt-sess-")
    prof_s = prof_on("p-rt-sess")
    ingest_docs(tls, DOCS, emb8, store_id="p", profile=prof_s,
                keyed_state=True)
    sess = ProducerSession(profile=prof_s)
    arec = sess.attach(tls)
    # The keyed ingest already persisted xdoc routing (ephemeral
    # legs persist when dirty); hier legs are cold.
    check("p-sess-attach-restores-xdoc",
          arec["attached"] is True
          and arec["restored_pops"] == ["xholon"]
          and arec["digest_mismatch"] is False, f"{arec}")
    org_s1 = organize_segments(tls, profile=prof_s, keyed_state=True,
                               session=sess, budget=1)
    srec1 = org_s1["keyed"]["session"]
    check("p-sess-first-build",
          srec1["built_from_views"] is True
          and org_s1["organized"] == ["r-a"], f"{srec1}")
    # External commit without the session, then reuse: the session
    # advances by committed delta (no full rebuild).
    organize_segments(tls, profile=prof_s, keyed_state=True, budget=1)
    org_s2 = organize_segments(tls, profile=prof_s, keyed_state=True,
                               session=sess)
    srec2 = org_s2["keyed"]["session"]
    check("p-sess-reuse-no-rebuild",
          srec2["built_from_views"] is False
          and srec2["rebuilt_rows"] == 0
          and srec2["advance_upserts"] > 0
          and sorted(org_s2["organized"]) == ["r-c", "r-d"],
          f"{srec2}")
    ingest_docs(tls, [("r-y", run_of("sport", 12, 80000))], emb8,
                store_id="p", profile=prof_s, keyed_state=True)
    org_s2b = organize_segments(tls, profile=prof_s, keyed_state=True,
                                session=sess)
    check("p-sess-absorb-new-doc",
          org_s2b["organized"] == ["r-y"]
          and org_s2b["keyed"]["session"]["rebuilt_rows"] == 0,
          f"{org_s2b['keyed']['session']}")
    sig_sess = hier_sig(tls)
    tls.close()
    # Identical committed hierarchy without the session (D2 parity).
    _tmps2, tls2 = fresh_store(prefix="tlsys-p-rt-nosess-")
    ingest_docs(tls2, DOCS, emb8, store_id="p", profile=prof_s,
                keyed_state=True)
    organize_segments(tls2, profile=prof_s, keyed_state=True)
    ingest_docs(tls2, [("r-y", run_of("sport", 12, 80000))], emb8,
                store_id="p", profile=prof_s, keyed_state=True)
    organize_segments(tls2, profile=prof_s, keyed_state=True)
    check("p-sess-d2-parity", hier_sig(tls2) == sig_sess,
          "session routing diverged")
    tls2.close()
    # Restart: a fresh session object restores persisted routing with
    # zero rebuild rows, then serves an identical call.
    sess2 = ProducerSession(profile=prof_s)
    _tmps3 = tempfile.mkdtemp(prefix="tlsys-p-rt-re3-")
    snap3 = snapshot_store(os.path.join(_tmps, "store"),
                           os.path.join(_tmps3, "store"))
    assert snap3["ok"], f"{snap3}"
    tls3 = TLStore(os.path.join(_tmps3, "store"), create=False,
                   lease_owner="test-c2-p-rt-re3")
    arec2 = sess2.attach(tls3)
    check("p-sess-restart-restores",
          arec2["routing_restored"] is True
          and arec2["rebuilt_rows"] == 0, f"{arec2}")
    org_s3 = organize_segments(tls3, profile=prof_s, keyed_state=True,
                               session=sess2)
    check("p-sess-restart-serves",
          org_s3["organized"] == []
          and org_s3["keyed"]["session"]["rebuilt_rows"] == 0,
          f"{org_s3['keyed']['session']}")
    check("p-sess-restart-parity", hier_sig(tls3) == sig_sess,
          "restored routing diverged")
    tls3.close()
    # Tampered routing bytes: the digest mismatch takes the named
    # rebuild path (receipted), and effects stay correct.
    import sqlite3 as _sq
    from tlsys import prodstate as _PS
    _tmpt = tempfile.mkdtemp(prefix="tlsys-p-rt-tamp-")
    snapt = snapshot_store(os.path.join(_tmps, "store"),
                           os.path.join(_tmpt, "store"))
    assert snapt["ok"], f"{snapt}"
    tlt = TLStore(os.path.join(_tmpt, "store"), create=False,
                  lease_owner="test-c2-p-rt-tamp")
    con = _sq.connect(os.path.join(tlt.store.root, _PS.SIDECAR_NAME))
    try:
        row = con.execute(
            "SELECT population, blob FROM routing_populations "
            "LIMIT 1").fetchone()
        assert row is not None, "no routing snapshot to tamper"
        bad = bytes([row[1][0] ^ 0xFF]) + row[1][1:]
        con.execute("UPDATE routing_populations SET blob=? "
                    "WHERE population=?", (bad, row[0]))
        con.commit()
    finally:
        con.close()
    sess_t = ProducerSession(profile=prof_s)
    arec_t = sess_t.attach(tlt)
    check("p-sess-tamper-rebuilds",
          arec_t["routing_restored"] is False
          and arec_t["digest_mismatch"] is True, f"{arec_t}")
    org_t = organize_segments(tlt, profile=prof_s, keyed_state=True,
                              session=sess_t)
    check("p-sess-tamper-serves",
          org_t["keyed"]["session"]["built_from_views"] is True
          and hier_sig(tlt) == sig_sess, "tamper path diverged")
    tlt.close()

    print(f"routing-suite done: {len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
