"""C2 Lane O: D2 organization parity (flag-on vs flag-off reference).

Builds twin scratch stores (identical docs/encoder): one organized on
the exact C1 reference path (profile None), one behind the Lane O
profile flag. Asserts the committed organization is IDENTICAL:
xdoc memberships/descriptors after ingest, xdoc views after drain,
leaf/parent memberships/children/descriptors after organize
(bitwise descriptor equality: identical math in identical order),
overflow-sibling ids, same-parent attach, and op/report counts.
Also asserts the catalog work receipt (rows <= R_cat x catalogs
touched per decision) and fail-closed behavior.

Deterministic fake encoder; scratch stores under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_organization.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "coordination", "c2-work-20261006T1925Z", "lane-G")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.maint import (drain_placement_backlog,  # noqa: E402
                         organize_segments)
from tlsys.place import read_xholons, read_seg_hierarchy  # noqa: E402
from profile import default_profile  # noqa: E402  (Lane G, read-only)
from counters import Counters  # noqa: E402  (Lane G, read-only)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


DIM = 8


def pad(v):
    return [float(x) for x in v] + [0.0] * (DIM - len(v))


V_SPORT = pad([1.0, 0.1, 0.0])
V_SPORT2 = pad([0.95, 0.31, 0.0])
V_MED = pad([0.1, 1.0, 0.0])
V_BOTH = pad([0.72, 0.69, 0.0])
V_OUT = pad([0.0, 0.0, 1.0])


def emb(texts):
    out = []
    for t in texts:
        w = t.split()[0] if t.split() else ""
        if w.startswith("sport"):
            out.append(list(V_SPORT if "0" in w[:7] else V_SPORT2))
        elif w.startswith("medic"):
            out.append(list(V_MED))
        elif w.startswith("bothmark"):
            out.append(list(V_BOTH))
        else:
            out.append(list(V_OUT))
    return out


def run_of(word, n, start=0):
    return " ".join(f"{word}{start + i}" for i in range(n))


DOCS = [("doc-multi", " ".join([run_of("sport", 150, 0),
                                run_of("medic", 150, 0),
                                run_of("sport", 150, 1000),
                                run_of("medic", 150, 1000)])),
        ("doc-sport-b", run_of("sport", 150, 5000)),
        ("doc-med-b", run_of("medic", 150, 6000)),
        ("doc-both", run_of("bothmark", 150, 7000)),
        ("doc-out", run_of("outlier", 150, 8000))]


def prof_on(pid):
    p = default_profile(profile_id=pid,
                        calibration_manifest_id="seed-host-20261006")
    p["flags"]["organization_catalog_routing"] = True
    return p


def aid_sig(idx, aids):
    # Atom ids bind the store's random revision_id, so cross-store
    # membership compares by (doc_id, span) occurrence signature
    # (same convention as test_m2a_org seg-determinism); member
    # ORDER and descriptors compare exactly.
    return [(idx.atoms[a]["doc_id"], tuple(idx.atoms[a]["span"]))
            for a in aids]


def xh_sig(tl):
    idx = NarrowIndex(tl, tl.pin())
    xh = read_xholons(tl, tl.pin())
    return {h: (aid_sig(idx, v["members"]),
                [float(x) for x in v["descriptor"]])
            for h, v in xh.items()}


def hier_sig(tl):
    idx = NarrowIndex(tl, tl.pin())
    hier = read_seg_hierarchy(tl, tl.pin())
    leaves = {k: (aid_sig(idx, v["members"]),
                  [float(x) for x in v["descriptor"]])
              for k, v in hier["leaves"].items()}
    parents = {k: (list(v["children"]),
                   aid_sig(idx, v["members"]),
                   [float(x) for x in v["descriptor"]])
               for k, v in hier["parents"].items()}
    return leaves, parents


def strip_report(rep):
    # pinned/catchup carry store-unique birth ids; catalog is the
    # additive flag-on receipt. Everything else must match exactly.
    return {k: v for k, v in rep.items()
            if k not in ("catalog", "pinned", "catchup")}


def main():
    # -- twin ingest: flag-off reference vs flag-on -------------------
    tmp_r = tempfile.mkdtemp(prefix="tlsys-c2o-ref-")
    tmp_c = tempfile.mkdtemp(prefix="tlsys-c2o-cat-")
    tl_r = TLStore(os.path.join(tmp_r, "store"), create=True,
                   lease_owner="test-c2o-ref")
    tl_c = TLStore(os.path.join(tmp_c, "store"), create=True,
                   lease_owner="test-c2o-cat")
    p_on = prof_on("c2o-ingest")
    cc_ing = Counters(scope="trial:c2o-ingest")
    rep_r = ingest_docs(tl_r, DOCS, emb, store_id="c2o")
    rep_c = ingest_docs(tl_c, DOCS, emb, store_id="c2o",
                        profile=p_on, counters=cc_ing)
    check("d2-ingest-counts",
          strip_report(rep_c) == strip_report(rep_r),
          f"ref={strip_report(rep_r)} cat={strip_report(rep_c)}")
    check("d2-ingest-xdoc", xh_sig(tl_c) == xh_sig(tl_r),
          "committed xdoc views differ")
    check("d2-ingest-receipt",
          rep_c.get("catalog", {}).get("decisions") == len(DOCS)
          and rep_c["catalog"]["xholon"]["calls"] == len(DOCS),
          f"{rep_c.get('catalog')}")
    snap = cc_ing.snapshot()["counters"]
    check("d2-ingest-counters",
          snap.get("catalog_rows_scanned.xholon", 0) > 0
          and snap.get("scoring_evals.place_xdoc", 0)
          == snap.get("catalog_rows_scanned.xholon", -1),
          f"{sorted(snap)}")
    rcat = p_on["derived_limits"]["R_cat"]
    check("d2-ingest-budget",
          rep_c["catalog"]["max_rows_per_decision"] <= rcat
          and not rep_c["catalog"]["over_budget"],
          f"{rep_c['catalog']}")

    # -- twin organize -------------------------------------------------
    cc_org = Counters(scope="trial:c2o-organize")
    org_r = organize_segments(tl_r)
    org_c = organize_segments(tl_c, profile=p_on, counters=cc_org)
    for key in ("organized", "failed", "remaining", "n_leaf_ops",
                "n_parent_ops", "n_commits", "max_batch_ops"):
        check(f"d2-org-{key}", org_c[key] == org_r[key],
              f"ref={org_r[key]!r} cat={org_c[key]!r}")
    check("d2-org-churn", org_c["churn"] == org_r["churn"],
          f"ref={org_r['churn']} cat={org_c['churn']}")
    leaves_r, parents_r = hier_sig(tl_r)
    leaves_c, parents_c = hier_sig(tl_c)
    check("d2-org-leaves", leaves_c == leaves_r,
          f"ref={sorted(leaves_r)} cat={sorted(leaves_c)}")
    if leaves_c != leaves_r:
        for k in sorted(set(leaves_r) | set(leaves_c)):
            if leaves_r.get(k) != leaves_c.get(k):
                print(f"  leaf {k}: ref={leaves_r.get(k)} "
                      f"cat={leaves_c.get(k)}")
    check("d2-org-parents", parents_c == parents_r,
          f"ref={sorted(parents_r)} cat={sorted(parents_c)}")
    if parents_c != parents_r:
        for k in sorted(set(parents_r) | set(parents_c)):
            if parents_r.get(k) != parents_c.get(k):
                print(f"  parent {k}: ref={parents_r.get(k)} "
                      f"cat={parents_c.get(k)}")
    check("d2-org-receipt",
          org_c["catalog"]["decisions"] > 0
          and org_c["catalog"]["leaf"]["calls"] > 0
          and org_c["catalog"]["parent"]["calls"] > 0,
          f"{org_c.get('catalog')}")
    # Leaf decisions scan two masks of one catalog; the per-decision
    # rows stay within 2 x R_cat, each single scan within R_cat.
    check("d2-org-budget",
          org_c["catalog"]["max_rows_per_decision"] <= 2 * rcat
          and not org_c["catalog"]["over_budget"],
          f"{org_c['catalog']}")
    check("d2-org-ties", org_c["catalog"]["ties"] == []
          and rep_c["catalog"]["ties"] == [],
          f"org={org_c['catalog']['ties']} "
          f"ing={rep_c['catalog']['ties']}")
    snap_o = cc_org.snapshot()["counters"]
    check("d2-org-counters",
          snap_o.get("catalog_rows_scanned.leaf", 0) > 0
          and snap_o.get("catalog_rows_scanned.parent", 0) > 0
          and snap_o.get("scoring_evals.place_leaf", 0) > 0
          and snap_o.get("scoring_evals.place_parent", 0) > 0,
          f"{sorted(snap_o)}")
    tl_r.close()
    tl_c.close()

    # -- twin drain: deferred backlog, then flag-off/on drain ----------
    tmp_dr = tempfile.mkdtemp(prefix="tlsys-c2o-dr-")
    tmp_dc = tempfile.mkdtemp(prefix="tlsys-c2o-dc-")
    tl_dr = TLStore(os.path.join(tmp_dr, "store"), create=True,
                    lease_owner="test-c2o-dr")
    tl_dc = TLStore(os.path.join(tmp_dc, "store"), create=True,
                    lease_owner="test-c2o-dc")
    ingest_docs(tl_dr, DOCS, emb, store_id="c2o", place_budget=0)
    ingest_docs(tl_dc, DOCS, emb, store_id="c2o", place_budget=0,
                profile=p_on)
    cc_dr = Counters(scope="trial:c2o-drain")
    d_r = drain_placement_backlog(tl_dr, store_id="c2o")
    d_c = drain_placement_backlog(tl_dc, store_id="c2o",
                                  profile=p_on, counters=cc_dr)
    for key in ("drained", "already_placed", "failed", "remaining",
                "n_xholon_ops", "n_commits"):
        check(f"d2-drain-{key}", d_c[key] == d_r[key],
              f"ref={d_r[key]!r} cat={d_c[key]!r}")
    check("d2-drain-xdoc", xh_sig(tl_dc) == xh_sig(tl_dr),
          "drained xdoc views differ")
    check("d2-drain-receipt",
          d_c["catalog"]["decisions"] == len(DOCS)
          and d_c["catalog"]["max_rows_per_decision"] <= rcat
          and d_c["catalog"]["ties"] == [],
          f"{d_c.get('catalog')}")
    tl_dr.close()
    tl_dc.close()

    # -- twin overflow: sibling ids + same-parent attach ---------------
    odocs = [(f"doc-s{i}", run_of("sport", 150, 10000 + 200 * i))
             for i in range(5)]
    tmp_or_ = tempfile.mkdtemp(prefix="tlsys-c2o-or-")
    tmp_oc = tempfile.mkdtemp(prefix="tlsys-c2o-oc-")
    tl_or_ = TLStore(os.path.join(tmp_or_, "store"), create=True,
                     lease_owner="test-c2o-or")
    tl_oc = TLStore(os.path.join(tmp_oc, "store"), create=True,
                    lease_owner="test-c2o-oc")
    ingest_docs(tl_or_, odocs, emb, store_id="c2o")
    ingest_docs(tl_oc, odocs, emb, store_id="c2o", profile=p_on)
    oo_r = organize_segments(tl_or_, max_leaf_members=3)
    oo_c = organize_segments(tl_oc, max_leaf_members=3,
                             profile=p_on)
    lo_r, po_r = hier_sig(tl_or_)
    lo_c, po_c = hier_sig(tl_oc)
    sib_r = sorted(k for k in lo_r if "-ov" in k)
    sib_c = sorted(k for k in lo_c if "-ov" in k)
    check("d2-ovf-siblings",
          sib_r == sib_c and len(sib_r) == 1, f"{sib_r}/{sib_c}")
    check("d2-ovf-leaves", lo_c == lo_r, "overflow leaves differ")
    check("d2-ovf-parents", po_c == po_r,
          "overflow parents differ")
    check("d2-ovf-counts", oo_c["n_leaf_ops"] == oo_r["n_leaf_ops"]
          and oo_c["n_parent_ops"] == oo_r["n_parent_ops"],
          f"ref={(oo_r['n_leaf_ops'], oo_r['n_parent_ops'])} "
          f"cat={(oo_c['n_leaf_ops'], oo_c['n_parent_ops'])}")
    tl_or_.close()
    tl_oc.close()

    # -- twin NESTED overflow: ancestor re-mint after nesting -------
    # O-5 (O-4 REPORT §5/§7): phased fixture — 8 pure-V_SPORT docs,
    # 6 pure-V_SPORT2 docs, 6 pure-V_SPORT docs — with
    # max_leaf_members=3. Phase 1 mints S-ov1, S-ov2 (populating the
    # parent cache); phase 2 nests through S-ov2 (S-ov2-ov1,
    # S-ov2-ov1-ov1); phase 3 returns to pure-V_SPORT segs, which
    # rank the ancestor S first again. The re-mint must count the
    # nested keys (flag-off scan formula); arrived flag-on served
    # the stale cache (S-ov3/S-ov4 vs S-ov5/S-ov6). FAILS on arrived
    # code, PASSES after the O-5 propagation fix.
    ndocs = ([(f"doc-noa{i}", run_of("sport", 150, 10000 + 100 * i))
              for i in range(8)]
             + [(f"doc-nob{i}", run_of("sport", 150, 11111 + 111 * i))
                for i in range(6)]
             + [(f"doc-noc{i}", run_of("sport", 150, 10000 + 100 * i))
                for i in range(6)])
    tmp_nr = tempfile.mkdtemp(prefix="tlsys-c2o-nr-")
    tmp_nc = tempfile.mkdtemp(prefix="tlsys-c2o-nc-")
    tl_nr = TLStore(os.path.join(tmp_nr, "store"), create=True,
                    lease_owner="test-c2o-nr")
    tl_nc = TLStore(os.path.join(tmp_nc, "store"), create=True,
                    lease_owner="test-c2o-nc")
    ingest_docs(tl_nr, ndocs, emb, store_id="c2o")
    ingest_docs(tl_nc, ndocs, emb, store_id="c2o", profile=p_on)
    no_r = organize_segments(tl_nr, max_leaf_members=3)
    no_c = organize_segments(tl_nc, max_leaf_members=3,
                             profile=p_on)
    ln_r, pn_r = hier_sig(tl_nr)
    ln_c, pn_c = hier_sig(tl_nc)
    nsib_r = sorted(k for k in ln_r if "-ov" in k)
    nsib_c = sorted(k for k in ln_c if "-ov" in k)
    check("d2-novf-nested-present",
          any(k.count("-ov") >= 2 for k in nsib_r)
          and len(nsib_r) >= 5, f"{nsib_r}")
    check("d2-novf-siblings", nsib_c == nsib_r,
          f"ref={nsib_r} cat={nsib_c}")
    check("d2-novf-leaves", ln_c == ln_r,
          "nested-overflow leaves differ")
    check("d2-novf-parents", pn_c == pn_r,
          "nested-overflow parents differ")
    check("d2-novf-counts", no_c["n_leaf_ops"] == no_r["n_leaf_ops"]
          and no_c["n_parent_ops"] == no_r["n_parent_ops"],
          f"ref={(no_r['n_leaf_ops'], no_r['n_parent_ops'])} "
          f"cat={(no_c['n_leaf_ops'], no_c['n_parent_ops'])}")
    tl_nr.close()
    tl_nc.close()

    # -- flag-false profile == reference path, no catalog key ----------
    tmp_f = tempfile.mkdtemp(prefix="tlsys-c2o-ff-")
    tl_f = TLStore(os.path.join(tmp_f, "store"), create=True,
                   lease_owner="test-c2o-ff")
    p_off = default_profile(profile_id="c2o-off",
                            calibration_manifest_id="m")
    rep_f = ingest_docs(tl_f, DOCS[:2], emb, store_id="c2o",
                        profile=p_off)
    check("d2-flagfalse-ingest", "catalog" not in rep_f, f"{rep_f}")
    org_f = organize_segments(tl_f, profile=p_off)
    check("d2-flagfalse-org", "catalog" not in org_f, f"{org_f}")
    tl_f.close()

    # -- fail-closed ---------------------------------------------------
    tmp_e = tempfile.mkdtemp(prefix="tlsys-c2o-err-")
    tl_e = TLStore(os.path.join(tmp_e, "store"), create=True,
                   lease_owner="test-c2o-err")
    ingest_docs(tl_e, DOCS[:1], emb, store_id="c2o")
    for bad in ("x", {"flags": True},
                {"flags": {"organization_catalog_routing": "yes"}}):
        try:
            organize_segments(tl_e, profile=bad)
            ok = False
        except (ValueError, AttributeError, TypeError):
            ok = True
        check(f"d2-badprofile-{bad!r}", ok)
    # Missing flag key means flag-off (reference path, no receipt).
    org_e = organize_segments(
        tl_e, profile={"flags": {},
                       "derived_limits": {"R_cat": 65536}})
    check("d2-emptyflags-off", "catalog" not in org_e, f"{org_e}")
    pbad = prof_on("c2o-badrcat")
    pbad["derived_limits"]["R_cat"] = -5
    try:
        ingest_docs(tl_e, DOCS[:1], emb, store_id="c2o",
                    profile=pbad)
        ok = False
    except ValueError:
        ok = True
    check("d2-badrcat", ok)
    tl_e.close()

    # -- small R_cat: decisions still exact, exceedance latched --------
    # R_cat=1: any decision over >=2 rows latches over_budget while
    # the scan itself stays exact (budget violation is reported,
    # never approximated).
    p_small = prof_on("c2o-small")
    p_small["derived_limits"]["R_cat"] = 1
    tmp_s = tempfile.mkdtemp(prefix="tlsys-c2o-sm-")
    tl_s = TLStore(os.path.join(tmp_s, "store"), create=True,
                   lease_owner="test-c2o-sm")
    ingest_docs(tl_s, DOCS, emb, store_id="c2o", profile=p_small)
    org_s = organize_segments(tl_s, profile=p_small)
    leaves_s, parents_s = hier_sig(tl_s)
    check("d2-smallrcat-same", leaves_s == leaves_r
          and parents_s == parents_r, "small-R_cat diverged")
    check("d2-smallrcat-latch", org_s["catalog"]["over_budget"]
          is True, f"{org_s.get('catalog')}")
    tl_s.close()

    print(f"organization-suite done: {len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
