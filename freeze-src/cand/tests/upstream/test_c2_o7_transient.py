"""C2 Lane O-7: first-ingest-per-process transient repair pins.

Pins the proj.py lazy checkpoint (docs + hierarchy maps load on first
access; reverse maps rebuild on first access; xdoc/retired stay eager)
and the ingest manifest-append path (journal-mode per-flush appends +
one compact end-save). All pins are structural/deterministic (loaded
flags, file sizes, save counts, view equality) — no wall-clock
assertions. Exactness: lazy-vs-eager equivalence, overlay merge,
layout-1 backward compat, and corruption fallbacks.

Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_o7_transient.py
"""
import inspect
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "coordination", "c2-work-20261006T1925Z", "lane-G")))

from tlsys import proj as P
from tlsys.proj import Projections
from tlsys.store_if import TLStore
from tlsys import ingest as ING
from tlsys.ingest import ingest_docs
from tlsys.maint import organize_segments
from profile import default_profile  # noqa: E402  (Lane G, read-only)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


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


DOCS = [("t7-a", run_of("sport", 12, 0)),
        ("t7-b", run_of("sport", 12, 5000)),
        ("t7-c", run_of("medic", 12, 9000))]


def fresh_store(prefix="tlsys-o7-tr-"):
    tmp = tempfile.mkdtemp(prefix=prefix)
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="test-o7-transient")
    return tmp, tl


def warm_checkpoint(tl, docs=DOCS):
    """Build committed state + a persisted snapshot; return live views."""
    ingest_docs(tl, docs, emb8, store_id="o7t")
    org = organize_segments(tl)
    assert org["organized"], f"nothing organized: {org}"
    proj = Projections()
    cup = proj.update(tl)
    proj.save(tl)
    assert cup["cold"] is True
    views = {
        "docs": {d: sorted(r) for d, r in proj._docs.items()}
        if proj._docs is not None else None,
        "leaves": sorted(proj.hierarchy_view()["leaves"]),
        "parents": sorted(proj.hierarchy_view()["parents"]),
        "xdoc": sorted(proj.xholons_view()),
        "retired": dict(proj.retired_view()),
        "lp": {k: sorted(v)
               for k, v in proj.leaf_parents_view().items()},
        "pc": {k: sorted(v)
               for k, v in proj.parent_children_view().items()},
        "al": {k: sorted(v) for k, v in proj.atom_leaves_view().items()},
    }
    return proj, views


def snap_views(proj):
    proj._ensure_docs()
    proj._ensure_hier()
    proj._ensure_reverse_maps()
    return {
        "docs": {d: sorted(r) for d, r in proj._docs.items()},
        "leaves": sorted(proj.hierarchy_view()["leaves"]),
        "parents": sorted(proj.hierarchy_view()["parents"]),
        "xdoc": sorted(proj.xholons_view()),
        "retired": dict(proj.retired_view()),
        "lp": {k: sorted(v)
               for k, v in proj.leaf_parents_view().items()},
        "pc": {k: sorted(v)
               for k, v in proj.parent_children_view().items()},
        "al": {k: sorted(v) for k, v in proj.atom_leaves_view().items()},
    }


def main():
    # -- layout-2 snapshot shape --------------------------------------
    _tmp0, tl0 = fresh_store()
    _proj0, views0 = warm_checkpoint(tl0)
    meta_p = Projections.checkpoint_path(tl0)
    docs_p = Projections.docs_path(tl0)
    hier_p = Projections.hier_path(tl0)
    journ_p = Projections.journal_path(tl0)
    check("o7-split-files",
          os.path.isfile(meta_p) and os.path.isfile(docs_p)
          and os.path.isfile(hier_p)
          and not os.path.isfile(journ_p),
          f"{os.path.basename(meta_p)}")
    with open(meta_p) as f:
        meta = json.load(f)
    check("o7-meta-layout2",
          meta.get("layout") == 2 and "docs" not in meta
          and "leaves" not in meta and "parents" not in meta
          and isinstance(meta.get("xdoc"), dict)
          and isinstance(meta.get("retired"), dict),
          f"{sorted(meta)}")

    # -- lazy load: docs/hier/maps untouched ---------------------------
    P._WARM.clear()
    lazy = Projections.load(tl0)
    check("o7-lazy-unloaded",
          lazy._docs_loaded is False and lazy._hier_loaded is False
          and lazy._maps_built is False
          and sorted(lazy.xholons_view()) == views0["xdoc"]
          and dict(lazy.retired_view()) == views0["retired"],
          "eager maps wrong or lazy maps built")
    cup = lazy.update(tl0)
    check("o7-lazy-warm",
          cup["cold"] is False and cup["commits"] == 0
          and lazy._docs_loaded is False
          and lazy._hier_loaded is False, f"{cup}")
    rows = lazy.doc_rows("t7-a")
    check("o7-docs-on-access",
          lazy._docs_loaded is True and len(rows) > 0
          and lazy._hier_loaded is False, f"{len(rows)}")
    _hv = lazy.hierarchy_view()
    check("o7-hier-on-access",
          lazy._hier_loaded is True and lazy._maps_built is False,
          "hier access built maps")
    _lp = lazy.leaf_parents_view()
    check("o7-maps-on-access", lazy._maps_built is True,
          "reverse access skipped rebuild")
    check("o7-lazy-equal", snap_views(lazy) == views0,
          "lazy views != eager views")
    tl0.close()

    # -- consume-while-unloaded overlay + journal round-trip -----------
    tmp1, tl1 = fresh_store(prefix="tlsys-o7-tr-ov-")
    _proj1, views1 = warm_checkpoint(tl1)
    P._WARM.clear()
    # Single-writer discipline: the ingest below reuses this same
    # warm object via cached(), so its end update+save run on ov.
    ov = Projections.cached(tl1)
    ov.update(tl1)
    meta_pre = os.path.getsize(Projections.checkpoint_path(tl1))
    docs_pre = os.path.getsize(Projections.docs_path(tl1))
    hier_pre = os.path.getsize(Projections.hier_path(tl1))
    ingest_docs(tl1, [("t7-d", run_of("sport", 12, 20000))], emb8,
                store_id="o7t")
    check("o7-overlay-consume",
          ov._docs_loaded is False and "t7-d" in ov._docs_new
          and ov.frontier == tl1.pin()[2],
          "ingest end-update forced docs load or missed the overlay")
    ov.save(tl1)  # no-op (ingest end-save already journaled)
    check("o7-overlay-save-append",
          os.path.isfile(Projections.journal_path(tl1))
          and ov._docs_loaded is False
          and os.path.getsize(Projections.checkpoint_path(tl1))
          == meta_pre
          and os.path.getsize(Projections.docs_path(tl1)) == docs_pre
          and os.path.getsize(Projections.hier_path(tl1)) == hier_pre,
          "snapshot files rewritten")
    P._WARM.clear()
    ov2 = Projections.load(tl1)
    ov2.update(tl1)
    check("o7-overlay-roundtrip",
          ov2.doc_rows("t7-d") == ov.doc_rows("t7-d")
          and sorted(ov2.xholons_view()) == sorted(ov.xholons_view())
          and snap_views(ov2) == snap_views(ov),
          "overlay state lost across save/load")
    tl1.close()

    # -- layout-1 backward compat --------------------------------------
    tmp2, tl2 = fresh_store(prefix="tlsys-o7-tr-l1-")
    proj2, views2 = warm_checkpoint(tl2)
    # layout-1 shape, crafted literally (independent of production).
    payload = {"version": 1, "birth": proj2.birth, "epoch": proj2.epoch,
               "frontier": proj2.frontier, "triple": proj2.triple,
               "docs": proj2._docs, "leaves": proj2._leaves,
               "parents": proj2._parents, "xdoc": proj2._xdoc,
               "retired": proj2._retired}
    for p in (Projections.docs_path(tl2), Projections.hier_path(tl2)):
        if os.path.isfile(p):
            os.remove(p)
    if os.path.isfile(Projections.journal_path(tl2)):
        os.remove(Projections.journal_path(tl2))
    with open(Projections.checkpoint_path(tl2), "w") as f:
        json.dump(payload, f)
    P._WARM.clear()
    l1 = Projections.load(tl2)
    l1.update(tl2)
    check("o7-layout1-warm",
          l1._docs_loaded is True and l1._hier_loaded is True
          and l1._maps_built is False, "layout-1 must stay exact+lazy")
    check("o7-layout1-equal", snap_views(l1) == views2,
          "layout-1 views differ")
    tl2.close()

    # -- corruption fallbacks ------------------------------------------
    tmp3, tl3 = fresh_store(prefix="tlsys-o7-tr-bad-")
    _proj3, views3 = warm_checkpoint(tl3)
    with open(Projections.docs_path(tl3), "w") as f:
        f.write("{corrupt")
    P._WARM.clear()
    bad = Projections.load(tl3)  # lazy: no read yet, no failure
    check("o7-corrupt-docs-lazy-ok",
          bad._docs_loaded is False
          and sorted(bad.xholons_view()) == views3["xdoc"],
          "load touched docs")
    rows3 = bad.doc_rows("t7-a")  # access heals via cold rebuild
    check("o7-corrupt-docs-heal",
          len(rows3) > 0 and snap_views(bad) == views3,
          "healed views differ")
    with open(Projections.hier_path(tl3), "w") as f:
        f.write("[broken")
    P._WARM.clear()
    badh = Projections.load(tl3)
    _hv3 = badh.hierarchy_view()
    check("o7-corrupt-hier-heal", snap_views(badh) == views3,
          "hier heal differs")
    os.remove(Projections.docs_path(tl3))
    P._WARM.clear()
    missing = Projections.load(tl3)
    cup_m = missing.update(tl3)
    check("o7-missing-docs-cold",
          cup_m["cold"] is True
          and snap_views(missing) == views3, f"{cup_m}")
    tl3.close()

    # -- validate/rebuild entry points ---------------------------------
    tmp4, tl4 = fresh_store(prefix="tlsys-o7-tr-val-")
    _proj4, _views4 = warm_checkpoint(tl4)
    P._WARM.clear()
    val = Projections.load(tl4)
    rep = val.validate_reverse_maps()
    check("o7-validate-lazy-ok",
          rep["ok"] is True and val._maps_built is True, f"{rep}")
    rc = val.rebuild_reverse_maps()
    check("o7-rebuild-counts",
          rc["leaf_edges"] >= 0 and rc["atom_edges"] >= 0, f"{rc}")
    tl4.close()

    # -- manifest: compact + (opt-in) append --------------------------
    # The journal default stays False: test_r7a_perf
    # journal-off-by-default pins it, and test_recovery J4 pins the
    # legacy per-flush cadence. O-7 ships compact dumps on every
    # path plus equivalence proof for the opt-in append path.
    check("o7-journal-default-off",
          inspect.signature(ingest_docs).parameters[
              "progress_journal"].default is False,
          "must match the r7a pin (no fork)")

    def build_manifest_twins(journal_flag, prefix):
        t = tempfile.mkdtemp(prefix=prefix)
        s = TLStore(os.path.join(t, "store"), create=True,
                    lease_owner="test-o7-manifest")
        saves = []
        real = ING._save_manifest

        def counting(path, manifest):
            saves.append(path)
            return real(path, manifest)

        ING._save_manifest = counting
        try:
            r = ingest_docs(s, DOCS, emb8, store_id="o7m",
                            progress_journal=journal_flag)
        finally:
            ING._save_manifest = real
        with open(os.path.join(s.store.root,
                               ING.MANIFEST_NAME), "rb") as f:
            raw = f.read()
        man = json.loads(raw.decode("utf-8"))
        has_journal = os.path.isfile(os.path.join(
            s.store.root, ING.JOURNAL_NAME))
        s.close()
        return r, man, raw, len(saves), has_journal

    r_j, man_j, raw_j, saves_j, journ_j = build_manifest_twins(
        True, "tlsys-o7-tr-mj-")
    r_l, man_l, raw_l, saves_l, journ_l = build_manifest_twins(
        False, "tlsys-o7-tr-ml-")
    r_d, man_d, _raw_d, saves_d, journ_d = build_manifest_twins(
        inspect.signature(ingest_docs).parameters[
            "progress_journal"].default, "tlsys-o7-tr-md-")

    def man_shape(m):
        # op_ids are random per store; compare structure + counts.
        shape = {}
        for k, v in m.items():
            if k.startswith("_"):
                if k in ("_pending_placement", "_scheme"):
                    shape[k] = v
                continue
            shape[k] = {"atoms": len(v.get("atoms", [])),
                        "xdoc": len(v.get("xdoc", [])),
                        "holon": v.get("holon") is not None,
                        "status": v.get("status")}
        return shape

    check("o7-manifest-twins-equal",
          man_shape(man_j) == man_shape(man_l) == man_shape(man_d)
          and (r_j["n_atoms"], r_j["n_holons"], r_j["n_xholon_ops"])
          == (r_l["n_atoms"], r_l["n_holons"], r_l["n_xholon_ops"])
          == (r_d["n_atoms"], r_d["n_holons"], r_d["n_xholon_ops"])
          and not journ_j and not journ_l and not journ_d,
          f"saves j={saves_j} l={saves_l} d={saves_d}")
    check("o7-manifest-append-collapse",
          saves_j == 1 and saves_j < saves_l and saves_d == saves_l,
          f"journal={saves_j} legacy={saves_l} default={saves_d}")
    check("o7-manifest-compact",
          b"\n" not in raw_j and b"\n" not in raw_l
          and json.loads(raw_l.decode("utf-8")) == man_l
          and len(raw_l) < len(json.dumps(man_l, indent=1).encode()),
          f"{len(raw_j)}B journal-mode, {len(raw_l)}B legacy-mode")

    # -- first-ingest IO bound (fresh process, checkpoint present) -----
    tmp5, tl5 = fresh_store(prefix="tlsys-o7-tr-first-")
    _proj5, _views5 = warm_checkpoint(tl5)
    meta_pre = os.path.getsize(Projections.checkpoint_path(tl5))
    docs_pre = os.path.getsize(Projections.docs_path(tl5))
    hier_pre = os.path.getsize(Projections.hier_path(tl5))
    P._WARM.clear()  # simulate a fresh process
    saves5 = []
    real5 = ING._save_manifest

    def counting5(path, manifest):
        saves5.append(path)
        return real5(path, manifest)

    ING._save_manifest = counting5
    try:
        prof = default_profile(
            profile_id="c2-o7-first",
            calibration_manifest_id="seed-host-20261006")
        prof["flags"]["organization_catalog_routing"] = True
        rep5 = ingest_docs(tl5, [("t7-new", run_of("sport", 12, 40000))],
                           emb8, store_id="o7t", profile=prof)
    finally:
        ING._save_manifest = real5
    warm_obj = P._WARM[tl5.store.root]["obj"]
    check("o7-first-ingest-lazy",
          warm_obj._docs_loaded is False
          and warm_obj._hier_loaded is False
          and warm_obj._maps_built is False
          and rep5["n_atoms"] > 0
          and rep5.get("catalog", {}).get("decisions", 0) > 0,
          f"{rep5}")
    check("o7-first-ingest-io-bound",
          len(saves5) <= 4
          and os.path.getsize(Projections.checkpoint_path(tl5))
          == meta_pre
          and os.path.getsize(Projections.docs_path(tl5)) == docs_pre
          and os.path.getsize(Projections.hier_path(tl5)) == hier_pre,
          f"saves={len(saves5)}")

    # -- steady state: warm reuse, no rescan, snapshot untouched -------
    c1 = Projections.cached(tl5)
    c2 = Projections.cached(tl5)
    cup_s = c2.update(tl5)
    sig_before = Projections._disk_sig(tl5)
    c2.save(tl5)
    check("o7-steady-warm",
          c1 is c2 is warm_obj and cup_s["commits"] == 0
          and Projections._disk_sig(tl5) == sig_before,
          f"{cup_s}")
    tl5.close()

    print(f"transient-suite done: {len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
