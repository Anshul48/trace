"""Lane S counters/profile: ServeCounters -> Lane-G export mapping,
profile consumption + validation, behavioral no-magic-numbers
(config values reach the mechanisms they govern).

Run: tl-sys/.venv/bin/python tl-sys/tlsys/serving/tests/test_serving_counters_profile.py
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from fixture import emb_votes, make_docs, make_store  # noqa: E402
from tlsys.serving import provisional  # noqa: E402
from tlsys.serving.counters import ServeCounters, to_lane_g  # noqa: E402
from tlsys.serving.view import ViewPool  # noqa: E402

LANE_G = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
    "..", "coordination", "c2-work-20261006T1925Z", "lane-G"))

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def test_export_mapping():
    docs = make_docs(10, seed=121)
    tl, _tmp, pin = make_store(docs, emb_votes,
                               prefix="tlsys-lanes-cnt-")
    pool = ViewPool(tl, pin[0], pin[1])
    v = pool.acquire(pin)
    present = next(iter(v.df))
    v.bm25(present)
    v.dense_atoms_topk(np.arange(v.dim, dtype=np.float64), 5)
    v.dense_holons_full(np.arange(v.dim, dtype=np.float64))
    totals = pool.counters.totals()
    lg, extra, note = to_lane_g(pool.counters, scope="trial-1")
    snap = lg.snapshot()
    c = snap["counters"]
    check("cnt-lex",
          c["scoring_evals.lex_postings"]
          == totals["lex_postings_scanned"] > 0)
    check("cnt-dense-atoms",
          c["scoring_evals.dense_atoms"]
          == totals["dense_fp32_rows"] + totals["dense_rescore_rows"]
          > 0)
    check("cnt-dense-holons",
          c["scoring_evals.dense_holons"]
          == totals["holon_rows_scored"] > 0)
    check("cnt-log",
          c["log_commits_read"] == totals["log_rows_read"] > 0
          and c["log_ops_read"] == totals["log_ops_read"] > 0)
    check("cnt-io",
          c["bytes_read"] == totals["bytes_read"] > 0
          and c["artifacts_read"] == totals["artifacts_read"] > 0
          and c["files_touched"] == totals["files_touched"])
    check("cnt-native-failed",
          c["native_work_units"] == totals["dense_fp32_rows"]
          and c["failed_retried_work_units"]
          == totals["failed_retried"])
    check("cnt-ancestor-zero",
          c["ancestor_versions_written"] == 0
          and c["ancestor_bytes_written"] == 0)
    check("cnt-extra",
          extra["views_retained"] == 1
          and extra["delta_rows"] == len(v.delta.atom_rows)
          and set(note["lane_g_unmapped"])
          == {"bytes_copied", "relation_work_units"})
    check("cnt-scope", snap["scope"] == "trial-1")
    # Lane-G merge: disjoint scopes combine (zeros don't block).
    sys.path.insert(0, LANE_G)
    import counters as lane_g_counters
    other = lane_g_counters.Counters("background")
    other.inc("relation_work_units", 3)
    merged = lg.add(other)
    check("cnt-merge",
          merged.snapshot()["counters"]["relation_work_units"] == 3
          and merged.snapshot()["counters"]["log_commits_read"]
          == c["log_commits_read"])
    # Unknown serving counter fails closed.
    try:
        pool.counters.record(bogus_counter=1)
        check("cnt-unknown-raises", False, "no raise")
    except ValueError:
        check("cnt-unknown-raises", True)
    pool.release(v)
    tl.close()


def test_profile_consumption():
    sys.path.insert(0, LANE_G)
    import profile as lane_g_profile
    prof = lane_g_profile.default_profile("cnt-test")
    cfg = provisional.serving_config(profile=prof)
    check("prof-source", cfg["source"] == "explicit-lane-G-arg",
          cfg.get("source"))
    check("prof-validated", cfg["lane_g_validated"] is True)
    check("prof-mapped",
          cfg["delta_flush_atoms"]
          == prof["derived_limits"]["delta_flush_atoms"] == 5000
          and cfg["shortlist_margin_m"] == 64
          and cfg["dense_eps"] == 3e-5
          and cfg["compactor_mode"] == "inprocess"
          and cfg["lane_g_profile_id"] == "cnt-test")
    bad = lane_g_profile.default_profile("cnt-bad")
    bad["derived_limits"]["R_cat"] = -1
    try:
        provisional.serving_config(profile=bad)
        check("prof-invalid-raises", False, "no raise")
    except ValueError:
        check("prof-invalid-raises", True)
    cfg2 = provisional.serving_config(profile={"delta_flush_atoms": 7})
    check("prof-serving-dict",
          cfg2["delta_flush_atoms"] == 7
          and cfg2["source"] == "explicit-arg")
    # Ambient consumption finds the live lane-G bindings.
    provisional._cache = None
    provisional._polls = 0
    bound, note = provisional.find_lane_g_bindings()
    check("prof-ambient", bound is not None
          and note.startswith("lane-G:"), note)


def test_config_reaches_mechanisms():
    docs = make_docs(8, seed=122)
    tl, _tmp, pin = make_store(docs, emb_votes,
                               prefix="tlsys-lanes-cfg-")
    # K=1 evicts the released ancestor.
    pool = ViewPool(tl, pin[0], pin[1],
                    config={"retained_generations_K": 1})
    v = pool.acquire(pin)
    pool.release(v)
    v2 = pool.acquire(pin)
    check("cfg-k1", pool.stats()["retained"] == [pin[2]],
          f"{pool.stats()['retained']}")
    pool.release(v2)
    # flush=1 seals on cold build.
    pool2 = ViewPool(tl, pin[0], pin[1],
                     config={"delta_flush_atoms": 1})
    mx = pin[2]
    v3 = pool2.cold_build(pin, ranges=[(0, mx // 2), (mx // 2, mx)])
    check("cfg-flush1", len(v3.segments) >= 1,
          f"{len(v3.segments)}")
    pool2.release(v3)
    # m/eps reach certified_topk (recorded via wrapper).
    import tlsys.serving.dense as dense_mod
    seen = {}
    orig = dense_mod.certified_topk

    def spy(qvec, k, ids, mat32, norms64, overrides, m=64,
            eps=3e-5, counters=None):
        seen["m"] = m
        seen["eps"] = eps
        return orig(qvec, k, ids, mat32, norms64, overrides, m=m,
                    eps=eps, counters=counters)
    dense_mod.certified_topk = spy
    try:
        pool3 = ViewPool(tl, pin[0], pin[1],
                         config={"shortlist_margin_m": 11,
                                 "dense_eps": 1e-4})
        v4 = pool3.acquire(pin)
        v4.dense_atoms_topk(np.arange(v4.dim, dtype=np.float64), 3)
        check("cfg-m-eps", seen == {"m": 11, "eps": 1e-4},
              f"{seen}")
        pool3.release(v4)
    finally:
        dense_mod.certified_topk = orig
    tl.close()


def main():
    import traceback
    for fn in (test_export_mapping, test_profile_consumption,
               test_config_reaches_mechanisms):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=6))
    print("scratch: /tmp/tlsys-lanes-cnt-*")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
