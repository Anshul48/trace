"""C2 Lane O-7: executed-vs-eligible counting pins (R5, O scope).

Pins the catalog.py counting fix: per-call top_k info and Catalog
totals report EXECUTED native rows + logical read/copy/write bytes
(O-4 §3.2 ledger semantics, productionized) ALONGSIDE the eligible
rows/bytes, and the per-trial receipts (ingest/drain/organize
report["catalog"]) carry them. Eligible semantics, Lane-G counter
keys/values, and every decision are preserved (counting only).

Reproducer shape (parent handoff): 12-row catalog under a 4-row mask
takes the dense path (4*3 >= 12) and executes a 12-row matvec while
only 4 rows are eligible. At dim=4 the eligible receipt is 4 rows /
160B while 384 descriptor bytes execute.

Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_o7_counting.py
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
from tlsys.place import (decide_catalog, decide_leaf_catalog,
                         decide_parent_catalog)
from tlsys.store_if import TLStore
from tlsys.ingest import ingest_docs
from tlsys.maint import drain_placement_backlog, organize_segments
from profile import default_profile  # noqa: E402  (Lane G, read-only)
from counters import Counters  # noqa: E402  (Lane G, read-only)

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


# -- O-4 §3.2 ledger oracle (hardcoded arithmetic; the O-4 crossover ----
# constant is pinned, not imported, so a change to it fails loudly). --
DENSE_NUM = 3


def oracle_ledger(n, rows, m_qual, k, dim):
    """(executed_rows, desc_read, copy, scores_norms, sort_temp,
    logical_read, logical_written) per O-4 calib_topk.py ledger()."""
    d8 = dim * 8
    if rows == 0:
        return (0, 0, 0, 0, 0, 0, 0)
    dense = (rows == n or rows * DENSE_NUM >= n)
    if dense:
        desc_read = n * d8
        copy = 0
        score_write = n * 8 + rows * 8
        score_read = n * 8 + rows * 8
        norms_rw = n * 8 + rows * 8
        executed = n
    else:
        desc_read = rows * d8
        copy = 2 * rows * d8
        score_write = rows * 8
        score_read = rows * 8
        norms_rw = rows * 8 + rows * 8
        executed = rows
    kk = m_qual if k is None else k
    partition = (m_qual > kk and kk > 0)
    if partition:
        sort_traffic = m_qual * 8 * 3 + 64 * 8
    else:
        sort_traffic = m_qual * 8 * 4
    scores_norms = score_read + score_write + norms_rw
    logical_read = desc_read + score_read + norms_rw + sort_traffic // 2
    logical_written = score_write + sort_traffic // 2
    return (executed, desc_read, copy, scores_norms, sort_traffic,
            logical_read, logical_written)


def oracle_executed(n, rows):
    if rows == 0:
        return 0
    return n if (rows == n or rows * DENSE_NUM >= n) else rows


def main():
    check("o7-dense-num-pinned", C._DENSE_COPY_NUM == DENSE_NUM,
          f"{C._DENSE_COPY_NUM}")

    # -- 12-row / 4-mask reproducer (dim=4: eligible 4 rows / 160B) ----
    rng = np.random.RandomState(7)
    dim = 4
    cat = C.Catalog("leaf", dim, 65536)
    vecs = rng.standard_normal((12, dim))
    cat.build([(f"h{i:02d}", list(vecs[i]), 0) for i in range(12)])
    mask4 = np.zeros(12, dtype=bool)
    mask4[[1, 4, 7, 10]] = True
    q = list(rng.standard_normal(dim))
    ids, info = cat.top_k(q, 2, mask4)
    check("o7-12x4-eligible-preserved",
          info["rows_scanned"] == 4 and info["eligible"] == 4
          and info["bytes_touched"] == 4 * (dim * 8 + 8) == 160
          and info["catalog_n"] == 12,
          f"{info.get('rows_scanned')}/{info.get('bytes_touched')}")
    exp = oracle_ledger(12, 4, 0, 0, dim)  # path/shape only
    check("o7-12x4-executed",
          info["executed_rows"] == 12
          and info["descriptor_read_B"] == 384
          and info["copy_B"] == 0,
          f"{info.get('executed_rows')}/{info.get('descriptor_read_B')}"
          f"/{info.get('copy_B')}")
    check("o7-12x4-oracle-path", exp[0] == 12 and exp[1] == 384
          and exp[2] == 0, f"{exp}")

    # -- sparse control: 12-row / 2-mask (2*3 < 12) --------------------
    mask2 = np.zeros(12, dtype=bool)
    mask2[[3, 8]] = True
    _ids, info2 = cat.top_k(q, 2, mask2)
    check("o7-12x2-sparse",
          info2["rows_scanned"] == 2
          and info2["executed_rows"] == 2
          and info2["descriptor_read_B"] == 2 * dim * 8 == 64
          and info2["copy_B"] == 2 * 2 * dim * 8 == 128,
          f"{info2.get('executed_rows')}"
          f"/{info2.get('descriptor_read_B')}/{info2.get('copy_B')}")

    # -- crossover boundary pins ---------------------------------------
    catb = C.Catalog("leaf", dim, 65536)
    catb.build([(f"b{i:02d}", list(rng.standard_normal(dim)), 0)
                for i in range(13)])
    m4 = np.zeros(13, dtype=bool)
    m4[:4] = True  # 4*3=12 < 13 -> sparse
    _i, inf4 = catb.top_k(q, 2, m4)
    m5 = np.zeros(13, dtype=bool)
    m5[:5] = True  # 5*3=15 >= 13 -> dense
    _i, inf5 = catb.top_k(q, 2, m5)
    check("o7-crossover-boundary",
          inf4["executed_rows"] == 4 and inf4["copy_B"] > 0
          and inf5["executed_rows"] == 13 and inf5["copy_B"] == 0,
          f"{inf4.get('executed_rows')}/{inf5.get('executed_rows')}")

    # -- empty / unmasked / fully-masked edges -------------------------
    empty = C.Catalog("parent", dim, 100)
    _i, infe = empty.top_k([1.0] + [0.0] * (dim - 1), 3)
    check("o7-empty-zero",
          infe["rows_scanned"] == 0 and infe["executed_rows"] == 0
          and infe["descriptor_read_B"] == 0 and infe["copy_B"] == 0
          and infe["logical_read_B"] == 0
          and infe["logical_written_B"] == 0
          and infe["scores_norms_B"] == 0 and infe["sort_temp_B"] == 0,
          f"{infe}")
    mask_none = np.zeros(12, dtype=bool)
    _i, infz = cat.top_k(q, 2, mask_none)
    check("o7-zero-mask-zero",
          infz["rows_scanned"] == 0 and infz["executed_rows"] == 0
          and infz["logical_read_B"] == 0
          and infz["logical_written_B"] == 0, f"{infz}")
    _i, infu = cat.top_k(q, 2)  # mask=None: all rows eligible
    check("o7-unmasked-equal",
          infu["rows_scanned"] == 12 and infu["executed_rows"] == 12
          and infu["copy_B"] == 0, f"{infu}")

    # -- full ledger formulas across path x selection combinations ----
    led = C.Catalog("leaf", 8, 65536)
    dim8 = 8
    vrng = np.random.RandomState(11)
    vv = vrng.standard_normal((40, dim8))
    vv = vv / np.linalg.norm(vv, axis=1, keepdims=True)
    led.build([(f"l{i:02d}", list(vv[i]), 0) for i in range(40)])
    qq = list(vv[0] * 0.99 + vrng.standard_normal(dim8) * 0.01)
    combos = []
    mall = np.ones(40, dtype=bool)
    combos.append(("dense-part", mall, 3, None))
    combos.append(("dense-fullsort", mall, 40, None))
    combos.append(("dense-k0", mall, 0, None))
    combos.append(("dense-knone", mall, None, 0.5))
    msparse = np.zeros(40, dtype=bool)
    msparse[:5] = True  # 5*3=15 < 40 -> sparse
    combos.append(("sparse-part", msparse, 2, None))
    combos.append(("sparse-fullsort", msparse, 5, 0.9))
    combos.append(("sparse-k0", msparse, 0, None))
    ok_all = True
    detail = ""
    for tag, mk, kk, thr in combos:
        _i, nfo = led.top_k(qq, kk, mk, threshold=thr)
        rows = int(np.count_nonzero(mk))
        # m_qual oracle: independent recount from the same float64
        # inputs (matvec + threshold), not from the info under test.
        mat = led._mat[:led._n]
        norms = led._norms[:led._n]
        idx = np.nonzero(mk)[0]
        qv = np.asarray(qq, dtype=np.float64)
        qn = float(np.linalg.norm(qv)) or 1.0
        sc = (mat @ qv)[idx] / (norms[idx] * qn)
        if thr is not None:
            sc = sc[sc >= thr]
        m_qual = int(sc.shape[0])
        exp = oracle_ledger(40, rows, m_qual, kk, dim8)
        got = (nfo["executed_rows"], nfo["descriptor_read_B"],
               nfo["copy_B"], nfo["scores_norms_B"], nfo["sort_temp_B"],
               nfo["logical_read_B"], nfo["logical_written_B"])
        if got != exp:
            ok_all = False
            detail = f"{tag}: got={got} exp={exp}"
            break
    check("o7-ledger-formulas", ok_all, detail)

    # -- totals accumulate; eligible totals unchanged ------------------
    tcat = C.Catalog("xholon", dim, 65536)
    tcat.build([(f"x{i:02d}", list(rng.standard_normal(dim)), 0)
                for i in range(12)])
    tcat.top_k(q, 2, mask4)   # dense: exec 12
    tcat.top_k(q, 2, mask2)   # sparse: exec 2
    check("o7-totals",
          tcat.total_rows == 6 and tcat.total_calls == 2
          and tcat.total_bytes == 6 * (dim * 8 + 8)
          and tcat.total_executed_rows == 14
          and tcat.total_descriptor_read_B == 384 + 64
          and tcat.total_copy_B == 128
          and tcat.total_logical_read_B > 0
          and tcat.total_logical_written_B > 0,
          f"rows={tcat.total_rows} exec={tcat.total_executed_rows} "
          f"desc={tcat.total_descriptor_read_B} copy={tcat.total_copy_B}")
    # totals reconcile against summed per-call info
    rcat = C.Catalog("xholon", dim, 65536)
    rcat.build([(f"x{i:02d}", list(rng.standard_normal(dim)), 0)
                for i in range(12)])
    acc = [0, 0, 0, 0, 0]
    for mk, kk in ((mask4, 2), (mask2, 1), (None, 3)):
        _i, nfo = rcat.top_k(q, kk, mk)
        acc[0] += nfo["executed_rows"]
        acc[1] += nfo["descriptor_read_B"]
        acc[2] += nfo["copy_B"]
        acc[3] += nfo["logical_read_B"]
        acc[4] += nfo["logical_written_B"]
    check("o7-totals-reconcile",
          (rcat.total_executed_rows, rcat.total_descriptor_read_B,
           rcat.total_copy_B, rcat.total_logical_read_B,
           rcat.total_logical_written_B) == tuple(acc),
          f"{acc}")

    # -- Lane-G counters: eligible semantics preserved, no new keys ----
    cc = Counters(scope="trial:o7")
    _i, nfo = cat.top_k(q, 2, mask4, counters=cc)
    snap = cc.snapshot()["counters"]
    check("o7-counters-eligible",
          snap.get("catalog_rows_scanned.leaf") == 4
          and snap.get("catalog_bytes_touched.leaf") == 160
          and snap.get("scoring_evals.place_leaf") == 4
          and set(snap) == {"catalog_rows_scanned.leaf",
                            "catalog_bytes_touched.leaf",
                            "scoring_evals.place_leaf"},
          f"{sorted(snap)}")

    # -- old info keys intact ------------------------------------------
    need = {"rows_scanned", "bytes_touched", "eligible", "catalog_n",
            "returned", "cutoff_score", "next_score", "ties_at_cutoff",
            "near_threshold", "budget_exceeded"}
    check("o7-info-keys-superset", need.issubset(set(nfo)),
          f"{sorted(nfo)}")
    check("o7-info-eligible-echo",
          nfo["eligible"] == nfo["rows_scanned"] == 4, f"{nfo}")

    # -- place.py mirrors: stats unchanged (eligible units) ------------
    from tlsys.place import (T_LEAF, T_PARENT, T_PLACE)
    pop = {}
    prng = np.random.RandomState(3)
    for i in range(12):
        v = prng.standard_normal(dim)
        v = v / np.linalg.norm(v)
        m = int(prng.randint(0, 4))
        pop[f"h{i:02d}"] = {"members": [f"a{i}-{j}" for j in range(m)],
                            "descriptor": [float(x) for x in v]}
    xcat = C.Catalog("xholon", dim, 65536)
    xcat.build((h, e["descriptor"], len(e["members"]))
               for h, e in pop.items())
    st = {}
    decide_catalog(list(prng.standard_normal(dim)), xcat,
                   t_place=T_PLACE, stats=st)
    check("o7-stats-xdoc-eligible",
          st["catalog_rows"] == st["scored"]
          and "catalog_executed_rows" not in st, f"{st}")
    lcat = C.Catalog("leaf", dim, 65536)
    lcat.build((h, e["descriptor"], len(e["members"]))
               for h, e in pop.items())
    stl = {}
    decide_leaf_catalog(list(prng.standard_normal(dim)), lcat,
                        t_leaf=T_LEAF, stats=stl)
    # eligible + full masks partition the population, so the summed
    # eligible rows always equal n (place.py's business, unchanged).
    check("o7-stats-leaf-eligible",
          stl["catalog_rows"] == 12 and stl["scored"] <= 12,
          f"{stl}")
    pcat = C.Catalog("parent", dim, 65536)
    pcat.build((h, e["descriptor"], len(e["members"]))
               for h, e in pop.items())
    stp = {}
    decide_parent_catalog(list(prng.standard_normal(dim)), pcat,
                          t_parent=T_PARENT, stats=stp)
    check("o7-stats-parent-eligible",
          stp["catalog_rows"] == stp["scored"]
          and "catalog_executed_rows" not in stp, f"{stp}")
    # executed rows live in the receipt/totals, never in stats
    # (place.py untouched by this lane).
    check("o7-stats-no-executed-key",
          "catalog_executed_rows" not in stl, f"{sorted(stl)}")

    # -- per-trial receipts carry executed + logical work --------------
    prof = default_profile(profile_id="c2-o7-count",
                           calibration_manifest_id="seed-host-20261006")
    prof["flags"]["organization_catalog_routing"] = True

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

    docs = [("o7-a", run_of("sport", 30, 0)),
            ("o7-b", run_of("sport", 30, 5000)),
            ("o7-c", run_of("medic", 30, 9000))]
    tmp = tempfile.mkdtemp(prefix="tlsys-o7-count-")
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="test-o7-count")
    rep = ingest_docs(tl, docs, emb8, store_id="o7",
                      profile=prof, counters=Counters(scope="trial:o7i"))
    cc_sec = rep.get("catalog", {})
    xh = cc_sec.get("xholon") or {}
    check("o7-receipt-ingest",
          cc_sec.get("decisions", 0) > 0
          and "max_executed_rows_per_decision" in cc_sec
          and cc_sec["max_executed_rows_per_decision"]
          >= cc_sec.get("max_rows_per_decision", 0)
          and {"executed_rows", "descriptor_read_B", "copy_B",
               "logical_read_B", "logical_written_B"}.issubset(xh)
          and xh["executed_rows"] >= xh.get("rows", 0)
          and xh["logical_read_B"] >= xh.get("bytes", 0),
          f"{cc_sec}")
    check("o7-receipt-ingest-eligible-intact",
          {"decisions", "max_rows_per_decision", "over_budget",
           "ties"}.issubset(cc_sec)
          and {"rows", "bytes", "calls", "n"}.issubset(xh),
          f"{cc_sec}")

    org = organize_segments(tl, profile=prof,
                            counters=Counters(scope="trial:o7o"))
    oc_sec = org.get("catalog", {})
    leaf = oc_sec.get("leaf")
    parent = oc_sec.get("parent")
    exec_keys = {"executed_rows", "descriptor_read_B", "copy_B",
                 "logical_read_B", "logical_written_B"}
    check("o7-receipt-organize",
          "max_executed_rows_per_decision" in oc_sec
          and leaf is not None and exec_keys.issubset(leaf)
          and (parent is None or exec_keys.issubset(parent)),
          f"{oc_sec}")
    tl.close()

    # drain receipt: deferred docs drain through the xdoc catalog
    tmpd = tempfile.mkdtemp(prefix="tlsys-o7-count-drain-")
    tld = TLStore(os.path.join(tmpd, "store"), create=True,
                  lease_owner="test-o7-count-drain")
    ingest_docs(tld, docs, emb8, store_id="o7", place_budget=0,
                profile=prof)
    dr = drain_placement_backlog(tld, store_id="o7", profile=prof,
                                 counters=Counters(scope="trial:o7d"))
    dc_sec = dr.get("catalog", {})
    dxh = dc_sec.get("xholon") or {}
    check("o7-receipt-drain",
          dc_sec.get("decisions", 0) > 0
          and "max_executed_rows_per_decision" in dc_sec
          and {"executed_rows", "descriptor_read_B", "copy_B",
               "logical_read_B", "logical_written_B"}.issubset(dxh),
          f"{dc_sec}")
    tld.close()

    print(f"counting-suite done: {len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
