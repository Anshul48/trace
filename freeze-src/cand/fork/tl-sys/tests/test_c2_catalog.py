"""C2 Lane O: catalog units + catalog-vs-reference decision differential.

Covers tlsys.catalog (Catalog, TouchMap, OverlayView, LeafParentIndex,
MemberIndex, OverflowCounters, AtomIndex, profile helpers) and the
place.decide_*_catalog mirrors of decide/decide_leaf/decide_parent:
identical ids, order, and stats over randomized populations (seeds),
ties, full populations, and threshold edges. Deterministic (no store).

Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_catalog.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "coordination", "c2-work-20261006T1925Z", "lane-G")))

import numpy as np

from tlsys import catalog as C
from tlsys.place import (T_LEAF, T_PARENT, T_PLACE, decide, decide_leaf,
                         decide_parent)
from tlsys.place import (decide_catalog, decide_leaf_catalog,
                         decide_parent_catalog)
from profile import default_profile  # noqa: E402  (Lane G, read-only)
from counters import Counters  # noqa: E402  (Lane G, read-only)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def rand_pop(rng, n, dim, max_members, kind="members"):
    pop = {}
    for i in range(n):
        v = rng.standard_normal(dim)
        v = v / np.linalg.norm(v)
        m = int(rng.integers(0, max_members + 3))
        entry = {"members": [f"a{i}-{j}" for j in range(m)],
                 "descriptor": [float(x) for x in v], "seq": i}
        if kind == "children":
            entry["children"] = [f"l{i}-{j}" for j in range(m)]
        pop[f"h{i:04d}"] = entry
    return pop


def cat_from(pop, population, dim, rcat=65536, count_key="members"):
    cat = C.Catalog(population, dim, rcat)
    cat.build((h, e["descriptor"], len(e[count_key]))
              for h, e in pop.items())
    return cat


def main():
    rng = np.random.default_rng(20261006)
    dim = 8

    # -- profile helpers ---------------------------------------------
    check("cat-flag-none-off", C.catalog_routing_enabled(None) is False)
    p0 = default_profile(profile_id="t0", calibration_manifest_id="m")
    check("cat-flag-default-off",
          C.catalog_routing_enabled(p0) is False)
    p1 = default_profile(profile_id="t1", calibration_manifest_id="m")
    p1["flags"]["organization_catalog_routing"] = True
    check("cat-flag-on", C.catalog_routing_enabled(p1) is True)
    check("cat-rcat", C.catalog_row_budget(p1) == 65536)
    for bad in ("x", 3.5, True):
        try:
            C.catalog_routing_enabled(bad)
            ok = False
        except ValueError:
            ok = True
        check(f"cat-flag-failclosed-{bad!r}", ok)
    pbad = default_profile(profile_id="t", calibration_manifest_id="m")
    pbad["flags"]["organization_catalog_routing"] = True
    pbad["derived_limits"]["R_cat"] = 0
    try:
        C.catalog_routing_enabled(pbad)
        ok = False
    except ValueError:
        ok = True
    check("cat-flag-bad-rcat-failclosed", ok)

    # -- build / ordinals / doubling -----------------------------------
    pop = rand_pop(rng, 600, dim, 25)
    cat = cat_from(pop, "leaf", dim)
    check("cat-build-n", cat.n == 600 and len(cat) == 600,
          f"n={cat.n}")
    check("cat-ordinals",
          all(cat.ordinal(h) == i for i, h in enumerate(pop))
          and cat.ids == tuple(pop),
          "ordinal/insertion order")
    check("cat-counts",
          all(cat.count_of(h) == len(e["members"])
              for h, e in pop.items()))
    check("cat-contains",
          "h0000" in cat and "zzz" not in cat)
    try:
        cat.build([("x", [0.0] * dim, 0)])
        ok = False
    except ValueError:
        ok = True
    check("cat-rebuild-refused", ok)
    try:
        C.Catalog("nope", dim, 100)
        ok = False
    except ValueError:
        ok = True
    check("cat-bad-population", ok)
    try:
        cat.upsert("h0000", [0.0] * (dim + 1), 1)
        ok = False
    except ValueError:
        ok = True
    check("cat-dim-failclosed", ok)
    empty = C.Catalog("parent", dim, 100)
    ids, info = empty.top_k([1.0] + [0.0] * (dim - 1), 3)
    check("cat-empty-topk",
          ids == [] and info["rows_scanned"] == 0
          and info["bytes_touched"] == 0)

    # -- top_k order: (score desc, ordinal asc); k/threshold edges ------
    q = rng.standard_normal(dim)
    ids, info = cat.top_k(q, 5)
    check("cat-topk-n", len(ids) == 5)
    sc = [s for _h, s in info["returned"]]
    check("cat-topk-sorted", all(sc[i] >= sc[i + 1] for i in range(4)),
          f"{sc}")
    check("cat-topk-counted",
          info["rows_scanned"] == 600
          and info["bytes_touched"] == 600 * (dim * 8 + 8),
          f"{info['rows_scanned']}/{info['bytes_touched']}")
    check("cat-topk-totals", cat.total_rows == 600
          and cat.total_calls == 1)
    ids0, info0 = cat.top_k(q, 0)
    check("cat-topk-k0", ids0 == [] and info0["rows_scanned"] == 600)
    ids_t, info_t = cat.top_k(q, 600, threshold=0.99)
    check("cat-topk-threshold",
          all(s >= 0.99 for _h, s in info_t["returned"])
          and info_t["rows_scanned"] == 600)
    # exact ties order by ordinal asc
    tie = C.Catalog("leaf", 2, 100)
    tie.build([(f"t{i}", [1.0, 0.0], 0) for i in range(4)])
    tids, _tinfo = tie.top_k([1.0, 0.0], 4)
    check("cat-tie-ordinal", tids == ["t0", "t1", "t2", "t3"],
          f"{tids}")
    # mask shape fail-closed
    try:
        cat.top_k(q, 3, mask=np.zeros(5, dtype=bool))
        ok = False
    except ValueError:
        ok = True
    check("cat-mask-failclosed", ok)
    lt = cat.mask_lt(25)
    ge = cat.mask_ge(25)
    check("cat-masks", lt.shape == (600,) and bool(np.all(lt ^ ge)))

    # -- Lane G counters interop (exact key spellings) -----------------
    cc = Counters(scope="trial:t")
    ids, info = cat.top_k(q, 3, mask=lt, counters=cc)
    snap = cc.snapshot()["counters"]
    check("cat-counters-keys",
          snap.get("catalog_rows_scanned.leaf") == info["rows_scanned"]
          and snap.get("catalog_bytes_touched.leaf")
          == info["bytes_touched"]
          and snap.get("scoring_evals.place_leaf")
          == info["rows_scanned"],
          f"{sorted(snap)}")
    xc = C.Catalog("xholon", dim, 100)
    xc.build([("x1", [1.0] + [0.0] * (dim - 1), 0)])
    cc2 = Counters(scope="trial:t2")
    xc.top_k(q, 1, counters=cc2)
    check("cat-counters-xholon",
          "catalog_rows_scanned.xholon" in cc2.snapshot()["counters"]
          and "scoring_evals.place_xdoc"
          in cc2.snapshot()["counters"])

    # -- row budget latch (correct scan, visible exceedance) -----------
    small = C.Catalog("leaf", dim, 4)
    small.build([(f"s{i}", list(rng.standard_normal(dim)), 0)
                 for i in range(6)])
    check("cat-budget-notyet", small.budget_exceeded is False)
    _ids, info = small.top_k(q, 2)
    check("cat-budget-latch",
          small.budget_exceeded is True
          and info["budget_exceeded"] is True
          and info["rows_scanned"] == 6)
    big = C.Catalog("leaf", dim, 65536)
    big.build([(f"s{i}", list(rng.standard_normal(dim)), 0)
               for i in range(6)])
    _ids, info = big.top_k(q, 2)
    check("cat-budget-ok", big.budget_exceeded is False
          and info["budget_exceeded"] is False)

    # -- per-doc rollback ----------------------------------------------
    rb = C.Catalog("leaf", 2, 100)
    rb.build([("a", [1.0, 0.0], 1), ("b", [0.0, 1.0], 2)])
    rb.begin_doc()
    rb.upsert("b", [1.0, 1.0], 5)
    rb.upsert("c", [0.5, 0.5], 0)
    check("cat-rb-mid", rb.n == 3 and rb.count_of("b") == 5)
    rb.rollback()
    check("cat-rb-restored",
          rb.n == 2 and rb.ids == ("a", "b")
          and rb.count_of("b") == 2 and "c" not in rb)
    v_b, _i = rb.top_k([0.0, 1.0], 1)
    check("cat-rb-vec", v_b == ["b"], f"{v_b}")
    try:
        rb.rollback()
        ok = False
    except ValueError:
        ok = True
    check("cat-rb-unarmed", ok)

    # -- TouchMap ------------------------------------------------------
    tm = C.TouchMap({"a": 1, "b": 2, "c": 3})
    tm.begin_doc()
    tm["b"] = 20
    tm["d"] = 4
    check("tm-mid", tm == {"a": 1, "b": 20, "c": 3, "d": 4})
    tm.rollback()
    check("tm-rollback",
          tm == {"a": 1, "b": 2, "c": 3}
          and list(tm) == ["a", "b", "c"],
          f"{tm}")
    try:
        tm.rollback()
        ok = False
    except ValueError:
        ok = True
    check("tm-unarmed", ok)

    # -- OverlayView: exact dict-copy order + values, no copy ----------
    base = {"a": 1, "b": 2, "c": 3}
    over = {"b": 20, "d": 4}
    view = C.OverlayView(base, over)
    ref = dict(base)
    ref.update(over)
    check("ov-order", list(view.items()) == list(ref.items()))
    check("ov-len", len(view) == len(ref) == 4)
    check("ov-get", view["b"] == 20 and view["a"] == 1
          and view.get("zzz") is None)
    check("ov-contains", "d" in view and "zzz" not in view)

    # -- LeafParentIndex ------------------------------------------------
    parents = {"p2": {"children": ["l1", "l2"]},
               "p1": {"children": ["l2"]},
               "p0": {"children": []}}
    edge = C.LeafParentIndex().build(parents)
    check("edge-parents", edge.parents_of("l2") == ["p1", "p2"]
          and edge.parents_of("l1") == ["p2"]
          and edge.parents_of("lx") == [])
    check("edge-has", edge.has_edge("p2", "l1")
          and not edge.has_edge("p1", "l1"))
    check("edge-children", edge.children_of("p2") == {"l1", "l2"})
    edge.begin_doc()
    edge.add_edge("p1", "l9")
    check("edge-mid", edge.parents_of("l9") == ["p1"])
    edge.rollback()
    check("edge-rb", edge.parents_of("l9") == []
          and edge.children_of("p1") == {"l2"})

    # -- MemberIndex ----------------------------------------------------
    leaves = {"l1": {"members": ["a", "b"]},
              "l2": {"members": ["b", "c"]}}
    parents_m = {"p2": {"members": ["a", "b", "c"],
                        "children": ["l1", "l2"]},
                 "p1": {"members": ["b", "c"], "children": ["l2"]},
                 "p0": {"members": [], "children": []}}
    mi = C.MemberIndex().build(parents_m, leaves)
    check("mi-union", mi.union_of("p2") == {"a", "b", "c"})
    check("mi-mult", mi.multiplicity_of("p2", "b") == 2
          and mi.multiplicity_of("p2", "a") == 1
          and mi.multiplicity_of("p2", "z") == 0)
    check("mi-contains", mi.contains("p2", "a")
          and not mi.contains("p2", "z"))
    mi.begin_doc()
    mi.ensure("p3")
    mi.add("p3", "q")
    check("mi-mid", mi.union_of("p3") == {"q"})
    mi.rollback()
    check("mi-rb-new", mi.union_of("p3") == set())
    mi.begin_doc()
    mi.add("p2", "n")
    check("mi-mid2", mi.contains("p2", "n"))
    mi.rollback()
    check("mi-rb-old", not mi.contains("p2", "n")
          and mi.union_of("p2") == {"a", "b", "c"})

    # -- OverflowCounters -----------------------------------------------
    live = {"leafA": 1, "leafA-ov1": 1, "leafA-ov2": 1, "leafB": 1}
    ov = C.OverflowCounters()
    ov.begin_doc()
    check("ovc-first", ov.next_n("leafA", live) == 3)
    check("ovc-incr", ov.next_n("leafA", live) == 4)
    check("ovc-fresh", ov.next_n("leafB", live) == 1)
    ov.rollback()
    ov.begin_doc()
    check("ovc-rb", ov.next_n("leafA", live) == 3)

    # -- OverflowCounters.seed: one-pass, exact incl. nesting --------
    live2 = {"leafA": 1, "leafA-ov1": 1, "leafA-ov2": 1,
             "leafA-ov1-ov1": 1, "leafB": 1,
             "xseg-d-ov1-s0": 1}
    ref_n = lambda b: 1 + sum(1 for k in live2  # noqa: E731
                              if k.startswith(b + "-ov"))
    # (direct: seeded counts equal the reference formula pre-mint)
    ov3 = C.OverflowCounters()
    ov3.seed(live2)
    got = {}
    for b in ("leafA", "leafA-ov1", "leafB", "zzz", "xseg-d"):
        # peek without consuming: next_n consumes, so snapshot the
        # count via a throwaway twin seeded identically
        t = C.OverflowCounters()
        t.seed(live2)
        got[b] = t.next_n(b, live2)
    check("ovc-seed-values",
          got == {b: ref_n(b) for b in got},
          f"{got} vs {[ref_n(b) for b in got]}")
    # seed-then-mint increments; mid-doc seed refused
    ov3.begin_doc()
    try:
        ov3.seed(live2)
        ok = False
    except ValueError:
        ok = True
    check("ovc-seed-middoc-refused", ok)
    ov3.rollback()

    # -- OverflowCounters: nested-mint ancestor propagation (O-5) ----
    # A mint through an overflow sib as base writes a key matching
    # every ancestor stem; cached ancestor counts must advance too
    # (arrived code left them stale: keyed 5 vs scan 6 below).
    live3 = {"B": 1, "B-ov1": 1, "B-ov2": 1, "B-ov3": 1}
    ov4 = C.OverflowCounters()
    ov4.seed(live3)
    ov4.begin_doc()
    check("ovc-nest-direct", ov4.next_n("B", live3) == 4)
    live3["B-ov4"] = 1
    check("ovc-nest-nested", ov4.next_n("B-ov1", live3) == 1)
    live3["B-ov1-ov1"] = 1
    check("ovc-nest-parent", ov4.next_n("B", live3) == 6)
    live3["B-ov6"] = 1
    check("ovc-nest-deep", ov4.next_n("B-ov1-ov1", live3) == 1)
    live3["B-ov1-ov1-ov1"] = 1
    check("ovc-nest-parent2", ov4.next_n("B", live3) == 8)
    check("ovc-nest-mid", ov4.next_n("B-ov1", live3) == 3)
    ov4.rollback()
    # uncached ancestors stay lazy-exact (later scans see landed keys)
    ov5 = C.OverflowCounters()
    ov5.begin_doc()
    check("ovc-nest-lazy", ov5.next_n("B-ov1", live3) == 3)
    check("ovc-nest-lazy-parent", ov5.next_n("B", live3) == 8)
    ov5.rollback()
    # rollback restores ancestor entries touched by propagation
    ov7 = C.OverflowCounters()
    ov7.seed({"B": 1, "B-ov1": 1})
    live_rb = {"B": 1, "B-ov1": 1}
    ov7.begin_doc()
    check("ovc-nest-rb-nest", ov7.next_n("B-ov1", live_rb) == 1)
    live_rb["B-ov1-ov1"] = 1
    check("ovc-nest-rb-stale", ov7.next_n("B", live_rb) == 3)
    ov7.rollback()
    del live_rb["B-ov1-ov1"]  # live rolls back alongside
    ov7.begin_doc()
    check("ovc-nest-rb-restored",
          ov7.next_n("B", live_rb) == 2)
    check("ovc-nest-rb-restored2",
          ov7.next_n("B-ov1", live_rb) == 1)
    ov7.rollback()

    # -- AtomIndex ------------------------------------------------------
    ai = C.AtomIndex().build({"o1": {"members": ["a", "b"]},
                              "o2": {"members": ["c"]}})
    check("ai-membership",
          "a" in ai and "c" in ai and "z" not in ai
          and ai.owner_of("b") == "o1")
    ai.add("o2", ["z"])
    check("ai-add", "z" in ai and ai.owner_of("z") == "o2")

    # -- decision differential: catalog vs reference (many seeds) ------
    n_diff = 0
    for seed in range(60):
        r = np.random.default_rng(1000 + seed)
        n = int(r.integers(0, 40))
        pop = rand_pop(r, n, dim, 25)
        xcat = cat_from(pop, "xholon", dim)
        qv = list(r.standard_normal(dim))
        t = float(r.choice([T_PLACE, 0.0, 0.99]))
        s1, s2 = {}, {}
        j1 = decide(qv, pop, t_place=t, stats=s1)
        j2 = decide_catalog(qv, xcat, t_place=t, stats=s2)
        same = (j1 == j2 and s1["scored"] == s2["scored"]
                and s1["full_skipped"] == s2["full_skipped"]
                and s2["unknown"] == [])
        if not same:
            n_diff += 1
            if n_diff <= 3:
                print(f"  xdoc seed {seed}: ref={j1} cat={j2} "
                      f"s1={s1} s2={s2}")
    check("diff-decide-60seeds", n_diff == 0, f"{n_diff} diffs")

    n_diff = n_tieflag = 0
    for seed in range(60):
        r = np.random.default_rng(2000 + seed)
        n = int(r.integers(0, 40))
        pop = rand_pop(r, n, dim, 25)
        lcat = cat_from(pop, "leaf", dim)
        qv = list(r.standard_normal(dim))
        s1, s2 = {}, {}
        j1 = decide_leaf(qv, pop, stats=s1)
        j2 = decide_leaf_catalog(qv, lcat, stats=s2)
        same = (j1 == j2 and s1["scored"] == s2["scored"]
                and s1["full_skipped"] == s2["full_skipped"]
                and s1["full_qualifying"] == s2["full_qualifying"])
        if not same:
            n_diff += 1
            if n_diff <= 3:
                print(f"  leaf seed {seed}: ref={j1} cat={j2}")
    check("diff-decide-leaf-60seeds", n_diff == 0, f"{n_diff} diffs")

    n_diff = 0
    for seed in range(60):
        r = np.random.default_rng(3000 + seed)
        n = int(r.integers(0, 40))
        pop = rand_pop(r, n, dim, 16, kind="children")
        pcat = cat_from(pop, "parent", dim, count_key="children")
        qv = list(r.standard_normal(dim))
        s1, s2 = {}, {}
        j1 = decide_parent(qv, pop, stats=s1)
        j2 = decide_parent_catalog(qv, pcat, stats=s2)
        same = (j1 == j2 and s1["scored"] == s2["scored"]
                and s1["full_skipped"] == s2["full_skipped"])
        if not same:
            n_diff += 1
            if n_diff <= 3:
                print(f"  parent seed {seed}: ref={j1} cat={j2}")
    check("diff-decide-parent-60seeds", n_diff == 0, f"{n_diff} diffs")

    # -- decision edges: all-full, empty, exact ties -------------------
    full = {f"f{i}": {"members": [f"m{j}" for j in range(25)],
                      "descriptor": list(rng.standard_normal(dim)),
                      "seq": i} for i in range(5)}
    fcat = cat_from(full, "leaf", dim)
    s1, s2 = {}, {}
    j1 = decide_leaf([1.0] + [0.0] * (dim - 1), full, t_leaf=-2.0,
                     stats=s1)
    j2 = decide_leaf_catalog([1.0] + [0.0] * (dim - 1), fcat,
                             t_leaf=-2.0, stats=s2)
    check("diff-leaf-allfull",
          j1 == j2 == []
          and s1["full_qualifying"] == s2["full_qualifying"]
          and s1["scored"] == s2["scored"] == 0,
          f"{j1}/{j2} {s1.get('full_qualifying')}")
    # exact ties: identical descriptors rank by insertion/ordinal
    dup = {f"d{i}": {"members": [], "descriptor": [1.0] * dim,
                     "seq": i} for i in range(4)}
    dcat = cat_from(dup, "xholon", dim)
    j1 = decide([1.0] * dim, dup, t_place=0.0)
    j2 = decide_catalog([1.0] * dim, dcat, t_place=0.0)
    check("diff-xdoc-ties", j1 == j2
          == ["d0", "d1", "d2"][:3], f"{j1}/{j2}")

    # -- doc population catalog (tested; product has no doc-holon
    # -- decision loop, so this population stays unwired -- see REPORT)
    dpop = rand_pop(rng, 10, dim, 5)
    dccat = cat_from(dpop, "doc", dim)
    cc3 = Counters(scope="trial:t3")
    dids, dinfo = dccat.top_k(list(rng.standard_normal(dim)), 2,
                              counters=cc3)
    check("cat-doc-pop",
          len(dids) == 2 and dinfo["rows_scanned"] == 10
          and "catalog_rows_scanned.doc"
          in cc3.snapshot()["counters"]
          and "scoring_evals.place_doc"
          not in cc3.snapshot()["counters"])

    # -- O-4: partition-selection proof (BLAS-free) ------------------
    # _rank_head on identical score vectors must equal the full stable
    # desc sort's head + first excluded row, bitwise, for every k --
    # including exact ties straddling the cutoff and +-0.0 mixes.
    def ref_head(vals, ords, k):
        order = np.argsort(-vals, kind="stable")
        ro, rs = ords[order], vals[order]
        return (ro[:k], rs[:k], ro[k], float(rs[k]))
    n_diff = n_calls = 0
    for seed in range(300):
        r = np.random.default_rng(7100 + seed)
        m = int(r.integers(1, 60))
        style = seed % 5
        if style == 0:  # tiny alphabet: massive exact ties
            alpha = [float(x) for x in r.standard_normal(
                int(r.integers(1, 4)))]
            vals = np.array([alpha[int(x)] for x in
                             r.integers(0, len(alpha), m)])
        elif style == 1:  # continuous: almost surely tie-free
            vals = r.standard_normal(m)
        elif style == 2:  # two values incl. +-0.0 mixes
            vals = np.array([r.choice([0.0, -0.0, 1.0, -1.0])
                             for _ in range(m)])
        elif style == 3:  # all equal
            vals = np.full(m, float(r.standard_normal()))
        else:  # quantized: cutoff inside a tie run
            vals = np.round(r.standard_normal(m), 1)
        ords = np.arange(m) * 2 + 1  # non-contiguous ordinals
        for k in (1, m // 2, m - 1):
            if not 0 < k < m:
                continue
            n_calls += 1
            p, s, no, ns = C._rank_head(vals, ords, k)
            ep, es, eno, ens = ref_head(vals, ords, k)
            if not (list(p) == list(ep) and list(s) == list(es)
                    and int(no) == int(eno) and ns == ens):
                n_diff += 1
                if n_diff <= 3:
                    print(f"  rank-head seed {seed} k={k}: "
                          f"got={list(p)} exp={list(ep)}")
    check("topk-rank-head-bitwise-300seeds", n_diff == 0,
          f"{n_diff}/{n_calls} diffs")
    # exhaustive k sweep on a forced-tie vector (every cutoff lands
    # inside a tie run at some k)
    fv = np.array([1.0] * 6 + [0.0, -0.0] + [-1.0] * 3)
    fo = np.arange(len(fv))
    n_diff = 0
    for k in range(1, len(fv)):
        p, s, no, ns = C._rank_head(fv, fo, k)
        ep, es, eno, ens = ref_head(fv, fo, k)
        if not (list(p) == list(ep) and list(s) == list(es)
                and int(no) == int(eno) and ns == ens):
            n_diff += 1
            print(f"  rank-head-sweep k={k}: got={list(p)} "
                  f"exp={list(ep)}")
    check("topk-rank-head-sweep-all-k", n_diff == 0,
          f"{n_diff} diffs")

    # -- O-4: full-call differential vs the Lane O formulation -------
    # Scoring moved from fancy-copy matvec to (dense) full matvec +
    # select: same admission class as Lane O's matvec-vs-ddot
    # (sub-TIE_EPS), so ids/order/tie diagnostics must match exactly
    # while scores must match within TIE_EPS. Sparse masks keep the
    # identical BLAS call (bitwise scores); dense masks may differ at
    # last ulp (Observed: OpenBLAS kernel selection varies with M).
    def ref_top_k(cat, q, k, mask=None, threshold=None):
        n = cat.n
        if mask is None:
            idx = np.arange(n)
        else:
            idx = np.nonzero(np.asarray(mask, dtype=bool))[0]
        qv = np.asarray(q, dtype=np.float64)
        qn = float(np.linalg.norm(qv)) or 1.0
        if len(idx):
            dots = cat._mat[:cat._n][idx] @ qv
            scores = dots / (cat._norms[idx] * qn)
            order = np.argsort(-scores, kind="stable")
            ranked, rscores = idx[order], scores[order]
        else:
            ranked = idx
            rscores = np.zeros((0,), dtype=np.float64)
        if threshold is not None:
            keep = np.nonzero(rscores >= threshold)[0]
            ranked, rscores = ranked[keep], rscores[keep]
        kk = len(ranked) if k is None else k
        picked, pscores = ranked[:kk], rscores[:kk]
        nxt = (float(rscores[len(picked)])
               if len(rscores) > len(picked) else None)
        hids = cat._ids  # list indexing like the shipped code
        ties = []
        if len(ranked) > len(picked) and len(picked) > 0:
            sa, sb = float(rscores[len(picked) - 1]), float(
                rscores[len(picked)])
            if abs(sa - sb) <= C.TIE_EPS:
                ties.append((hids[int(ranked[len(picked) - 1])],
                             hids[int(ranked[len(picked)])],
                             abs(sa - sb)))
        near = 0
        if threshold is not None and len(idx):
            near = int(np.sum(np.abs(rscores - threshold)
                              <= C.TIE_EPS))
        return ([hids[int(r)] for r in picked],
                [float(s) for s in pscores],
                float(pscores[-1]) if len(pscores) else None, nxt,
                ties, near, int(len(idx)))

    n_diff = n_calls = 0
    worst = 0.0
    for seed in range(120):
        r = np.random.default_rng(7000 + seed)
        n = int(r.integers(0, 60))
        dim_t = int(r.choice([2, 3, 8]))
        alpha = [float(x) for x in
                 r.standard_normal(int(r.integers(1, 5)))]
        pop = {}
        for i in range(n):
            v = np.array([alpha[int(x)] for x in
                          r.integers(0, len(alpha), dim_t)],
                         dtype=np.float64)
            if i and r.random() < 0.3:  # exact-duplicate some row
                v = np.array(pop[f"h{r.integers(0, i):04d}"]
                             ["descriptor"])
            pop[f"h{i:04d}"] = {"members": [], "descriptor": list(v),
                                "seq": i}
        cat = cat_from(pop, "leaf", dim_t)
        qv = list(r.standard_normal(dim_t))
        style = seed % 4
        if style == 0:
            mask = None
        elif style == 1:  # dense
            mask = list(r.random(n) < 0.8)
        elif style == 2:  # sparse
            mask = list(r.random(n) < 0.15)
        else:
            mask = ([True] * (n // 2) + [False] * (n - n // 2)
                    if n else None)
            if seed % 8 == 7:
                mask = [False] * n if n else None
        t = r.choice([None, 0.0, 0.5, 0.99, -2.0])
        t = None if t is None else float(t)
        kk = r.choice([0, 1, 2, 3, 5, n, n + 4, None])
        k = None if kk is None else int(kk)
        got_ids, got_info = cat.top_k(qv, k, mask=mask, threshold=t)
        (e_ids, e_sc, e_cut, e_nxt, e_ties, e_near,
         e_rows) = ref_top_k(cat, qv, k, mask=mask, threshold=t)
        g_sc = [s for _h, s in got_info["returned"]]
        sd = max([abs(a - b) for a, b in zip(g_sc, e_sc)]
                 + [0.0])
        cd = (0.0 if got_info["cutoff_score"] == e_cut else abs(
            (got_info["cutoff_score"] or 0.0) - (e_cut or 0.0)))
        nd = (0.0 if got_info["next_score"] == e_nxt else abs(
            (got_info["next_score"] or 0.0) - (e_nxt or 0.0)))
        worst = max(worst, sd, cd, nd)
        same = (got_ids == e_ids and sd <= C.TIE_EPS
                and cd <= C.TIE_EPS and nd <= C.TIE_EPS
                and (got_info["cutoff_score"] is None)
                == (e_cut is None)
                and (got_info["next_score"] is None)
                == (e_nxt is None)
                and got_info["ties_at_cutoff"] == e_ties
                and got_info["near_threshold"] == e_near
                and got_info["rows_scanned"] == e_rows)
        n_calls += 1
        if not same:
            n_diff += 1
            if n_diff <= 3:
                print(f"  topk-diff seed {seed}: n={n} k={k} t={t} "
                      f"got={got_ids} exp={e_ids} sd={sd:.3g}")
    check("topk-call-differential-120seeds", n_diff == 0,
          f"{n_diff}/{n_calls} diffs, worst score delta {worst:.3g}")
    # duplicate descriptors tie bitwise inside one call (one matvec,
    # one kernel: identical inputs score identically)
    dup = C.Catalog("leaf", 8, 100)
    base = list(np.random.default_rng(42).standard_normal(8))
    dup.build([(f"d{i}", base, 0) for i in range(4)]
              + [(f"o{i}",
                  list(np.random.default_rng(i).standard_normal(8)),
                  0) for i in range(4)])
    dids, dinfo = dup.top_k(list(
        np.random.default_rng(7).standard_normal(8)), 8)
    dsc = dict(dinfo["returned"])
    dpos = [dids.index(f"d{i}") for i in range(4)]
    check("topk-duplicates-tie-bitwise",
          dsc["d0"] == dsc["d1"] == dsc["d2"] == dsc["d3"]
          and dpos == sorted(dpos)
          and max(dpos) - min(dpos) == 3,
          f"{dids} {sorted(set(dsc.values()))[:2]}")

    print(f"catalog-suite done: {len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
