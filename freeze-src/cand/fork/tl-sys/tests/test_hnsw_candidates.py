"""HNSW candidate-search interface tests (R7-B).

- hnsw_candidates: version pin, exact-topk oracle, build/query recall vs
  exact, determinism (rebuild + repeat query), stale-generation refusal,
  stale-seq drop + report, unpublished coverage, cost accounting (build/
  update wall, index bytes, no retained matrix by default), incremental
  add(), empty population.
- place.decide: flag-off identity (None == default), candidate
  restriction + unknown reporting, decide_with_search agreement and
  unpublished/stale handling.
- index.NarrowIndex: flag-off identity, attach/detach + generation
  check, dense_holons via search vs exact, NarrowQuery.run end-to-end
  parity on a tiny store through the real product path.

hnswlib==0.8.0 is required for the HNSW checks (R6-D scratch path
/tmp/tl-r6d-pkgs is appended as a fallback); pure-python checks always
run. HNSW checks SKIP (not fail) when hnswlib is truly absent.

Run: PYTHONPATH=/tmp/tl-r6d-pkgs tl-sys/.venv/bin/python \
       tl-sys/tests/test_hnsw_candidates.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))
try:
    import hnswlib  # noqa: F401
    HAVE_HNSW = True
except ImportError:
    if os.path.isdir("/tmp/tl-r6d-pkgs"):
        sys.path.insert(0, "/tmp/tl-r6d-pkgs")
        try:
            import hnswlib  # noqa: F401
            HAVE_HNSW = True
        except ImportError:
            HAVE_HNSW = False
    else:
        HAVE_HNSW = False

import numpy as np  # noqa: E402

from tlsys.hnsw_candidates import (  # noqa: E402
    HNSW_PIN, HolonCandidateIndex, StaleGenerationError,
    check_hnsw_version, exact_cosine_topk,
)
from tlsys.place import decide, decide_with_search  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402

FAILS = []
SKIPS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def skip(name, reason):
    SKIPS.append(name)
    print(f"skip {name} :: {reason}")


def synth_population(n=120, dim=16, seed=0):
    rng = np.random.RandomState(seed)
    centers = rng.randn(6, dim)
    h = {}
    for i in range(n):
        c = centers[i % 6]
        v = c + 0.1 * rng.randn(dim)
        h[f"h{i:03d}"] = {"descriptor": [float(x) for x in v],
                          "seq": 100 + i, "members": [f"m{i}"]}
    return h


def test_version_pin():
    check_hnsw_version("0.8.0")
    check("pin/accept-0.8.0", HNSW_PIN == "0.8.0", HNSW_PIN)
    try:
        check_hnsw_version("0.7.0")
        check("pin/reject-other", False, "no raise")
    except ValueError:
        check("pin/reject-other", True)
    check("pin/exception-type",
          issubclass(StaleGenerationError, ValueError))


def test_exact_topk_oracle():
    items = {"a": [1.0, 0.0], "b": [0.0, 1.0], "c": [1.0, 1.0]}
    got = exact_cosine_topk([1.0, 0.0], items, 2)
    check("oracle/order",
          [h for h, _s in got] == ["a", "c"], repr(got))
    check("oracle/scores",
          abs(got[0][1] - 1.0) < 1e-12
          and abs(got[1][1] - 2 ** -0.5) < 1e-12,
          repr(got))
    check("oracle/zero-vec",
          exact_cosine_topk([0.0, 0.0], {"z": [0.0, 0.0]},
                            1)[0][1] == 0.0)
    check("oracle/k-clamp",
          exact_cosine_topk([1.0, 0.0], items, 99) is not None
          and len(exact_cosine_topk([1.0, 0.0], items, 99)) == 3)


def test_decide_flagoff_identity():
    pop = synth_population()
    q = [float(x) for x in np.random.RandomState(7).randn(16)]
    a = decide(q, pop)
    b = decide(q, pop, candidate_ids=None)
    check("decide/off-identical", a == b, repr((a, b)))
    st = {}
    c = decide(q, pop, stats=st)
    check("decide/off-stats-harmless",
          c == a and st["unknown"] == []
          and st["scored"] == len(pop), repr(st))
    # candidate_ids == full population reproduces the exact decision.
    d = decide(q, pop, candidate_ids=list(pop.keys()))
    check("decide/full-candidates-identical", d == a,
          repr((d, a)))


def test_decide_candidates_pure():
    pop = synth_population(n=30)
    q = [float(x) for x in np.random.RandomState(7).randn(16)]
    cands = list(pop.keys())[:10] + ["xdoc-ghost"]
    st = {}
    got = decide(q, pop, candidate_ids=cands, stats=st)
    check("decide/unknown-reported", st["unknown"] == ["xdoc-ghost"],
          repr(st))
    check("decide/scored-bounded", st["scored"] == 10, repr(st))
    full = decide(q, pop)
    # Candidate restriction can only narrow: every join also joins
    # under the exact path (same scores, threshold, caps).
    check("decide/candidates-subset-of-exact",
          all(h in full for h in got), repr((got, full)))


def test_hnsw_build_query():
    if not HAVE_HNSW:
        skip("hnsw/build-query", "hnswlib absent")
        return
    pop = synth_population()
    s = HolonCandidateIndex().build(pop, "gen:0:1")
    check("hnsw/n-dim", s.n == 120 and s.dim == 16,
          repr((s.n, s.dim)))
    rng = np.random.RandomState(11)
    descs = {h: v["descriptor"] for h, v in pop.items()}
    recs = []
    first = True
    for _ in range(10):
        q = [float(x) for x in rng.randn(16)]
        got = s.query(q, k=20)
        want = [h for h, _s in exact_cosine_topk(q, descs, 20)]
        recs.append(len(set(got["hids"]) & set(want)) / 20.0)
        if first:
            first = False
            check("hnsw/report-keys",
                  got["ef"] >= 20 and got["ms"] >= 0.0
                  and got["n_scored_native_unknown"] is True
                  and got["stale_dropped"] == [], repr(got))
    check("hnsw/recall-vs-exact", min(recs) >= 0.95, repr(recs))
    check("hnsw/scores-desc",
          all(a >= b for a, b in
              zip(s.query(q, k=20)["scores"],
                  s.query(q, k=20)["scores"][1:])))


def test_hnsw_determinism():
    if not HAVE_HNSW:
        skip("hnsw/determinism", "hnswlib absent")
        return
    pop = synth_population()
    q = [float(x) for x in np.random.RandomState(7).randn(16)]
    a = HolonCandidateIndex().build(pop, "gen:0:1")
    b = HolonCandidateIndex().build(pop, "gen:0:1")
    ra = a.query(q, k=30)
    rb = b.query(q, k=30)
    check("hnsw/rebuild-identical-hids",
          ra["hids"] == rb["hids"], repr((ra["hids"], rb["hids"])))
    check("hnsw/rebuild-identical-scores",
          ra["scores"] == rb["scores"], repr(ra["scores"][:3]))
    r2 = a.query(q, k=30)
    check("hnsw/repeat-query-identical",
          r2["hids"] == ra["hids"] and r2["scores"] == ra["scores"])


def test_hnsw_stale_and_coverage():
    if not HAVE_HNSW:
        skip("hnsw/stale", "hnswlib absent")
        return
    pop = synth_population(n=40)
    s = HolonCandidateIndex().build(pop, "gen:0:1")
    q = [float(x) for x in np.random.RandomState(7).randn(16)]
    try:
        s.query(q, k=5, generation="gen:0:2")
        check("hnsw/stale-generation-refused", False, "no raise")
    except StaleGenerationError:
        check("hnsw/stale-generation-refused", True)
    live = {h: dict(v) for h, v in pop.items()}
    victim = s.query(q, k=5)["hids"][0]
    live[victim] = dict(live[victim])
    live[victim]["seq"] += 1000  # committed a newer version
    got = s.query(q, k=5, live=live)
    check("hnsw/stale-seq-dropped",
          victim in got["stale_dropped"]
          and victim not in got["hids"], repr(got))
    live["h-new"] = {"descriptor": [0.0] * 16, "seq": 9999}
    cov = s.coverage(live)
    check("hnsw/coverage-classes",
          cov["unpublished"] == ["h-new"]
          and victim in cov["stale"]
          and cov["indexed"] == 40 and cov["live"] == 41,
          repr(cov))


def test_hnsw_cost_and_update():
    if not HAVE_HNSW:
        skip("hnsw/cost", "hnswlib absent")
        return
    pop = synth_population(n=60)
    s = HolonCandidateIndex().build(pop, "gen:0:1")
    c = s.cost()
    check("hnsw/cost-keys",
          c["build_s"] > 0.0 and c["index_bytes"] > 0
          and c["vector_input_bytes"] == 60 * 16 * 4
          and c["retained_matrix_bytes"] == 0
          and c["map_entries"] == 60
          and c["hnswlib_pin"] == "0.8.0", repr(c))
    more = {f"u{i}": {"descriptor": [1.0 if j == i else 0.0
                                          for j in range(16)],
                          "seq": 500 + i}
            for i in range(10)}
    added = s.add(more, "gen:0:1")
    c2 = s.cost()
    check("hnsw/add-count", added == 10 and s.n == 70,
          repr((added, s.n)))
    check("hnsw/update-accounted",
          c2["update_count"] == 1 and c2["update_s"] > 0.0
          and c2["index_bytes"] >= c["index_bytes"]
          and c2["map_entries"] == 70, repr(c2))
    check("hnsw/add-noop", s.add(more, "gen:0:1") == 0)
    try:
        s.add(more, "gen:0:9")
        check("hnsw/add-generation-refused", False, "no raise")
    except StaleGenerationError:
        check("hnsw/add-generation-refused", True)
    q = [1.0 if j == 9 else 0.0 for j in range(16)]
    got = s.query(q, k=3)
    check("hnsw/added-retrievable", got["hids"][0] == "u9",
          repr(got["hids"]))
    e = HolonCandidateIndex().build({}, "gen:0:1")
    check("hnsw/empty", e.n == 0
          and e.query([1.0] * 4, k=5)["hids"] == []
          and e.cost()["index_bytes"] == 0)
    check("hnsw/empty-add-rebuilds",
          e.add({"z": {"descriptor": [1.0] * 16, "seq": 1}},
                "gen:0:1") == 1 and e.n == 1)


def test_place_with_search():
    if not HAVE_HNSW:
        skip("place/search", "hnswlib absent")
        return
    pop = synth_population(n=120)
    s = HolonCandidateIndex().build(pop, "gen:0:1")
    rng = np.random.RandomState(21)
    agree = 0
    nonempty = 0
    trials = 12
    for _ in range(trials):
        q = [float(x) for x in rng.randn(16)]
        # t_place=0.0 forces top-max_m joins: non-trivial agreement.
        exact = decide(q, pop, t_place=0.0)
        got, rep = decide_with_search(q, pop, s, k=40,
                                      generation="gen:0:1",
                                      t_place=0.0)
        nonempty += bool(exact)
        if got == exact:
            agree += 1
        check("place/search-report-keys",
              rep["scored"] <= 40 + len(rep["unpublished"])
              and rep["ef"] >= 40
              and rep["n_scored_native_unknown"] is True
              and rep["include_unpublished"] is True,
              repr(rep))
        break
    for _ in range(trials - 1):
        q = [float(x) for x in rng.randn(16)]
        ex = decide(q, pop, t_place=0.0)
        nonempty += bool(ex)
        if decide_with_search(q, pop, s, k=40,
                              generation="gen:0:1",
                              t_place=0.0)[0] == ex:
            agree += 1
    check("place/search-decide-agreement", agree == trials,
          f"{agree}/{trials}")
    check("place/search-agreement-nontrivial", nonempty == trials,
          f"{nonempty}/{trials}")
    # Unpublished live holon: unioned by default, skipped when off.
    q = [float(x) for x in rng.randn(16)]
    live = dict(pop)
    live["xdoc-fresh"] = {"descriptor": list(q), "seq": 777,
                          "members": ["a1"]}
    got_on, rep_on = decide_with_search(q, live, s, k=40,
                                        generation="gen:0:1")
    got_off, rep_off = decide_with_search(
        q, live, s, k=40, generation="gen:0:1",
        include_unpublished=False)
    check("place/unpublished-unioned-by-default",
          "xdoc-fresh" in got_on
          and rep_on["unpublished"] == ["xdoc-fresh"],
          repr((got_on, rep_on["unpublished"])))
    check("place/unpublished-skipped-when-off",
          "xdoc-fresh" not in got_off
          and rep_off["unpublished"] == ["xdoc-fresh"],
          repr(got_off))
    # Stale pending overwrite (no seq, like ingest pending_x):
    # rescored from live, reported by class.
    live2 = dict(pop)
    pend = s.query(q, k=40)["hids"][0]
    live2[pend] = {"descriptor": list(q),
                   "members": pop[pend]["members"]}
    got_p, rep_p = decide_with_search(q, live2, s, k=40,
                                      generation="gen:0:1")
    check("place/stale-pending-rescored-live",
          pend in rep_p["stale_rescored_live"]
          and pend in got_p, repr(rep_p))


def tiny_store(tmp):
    root = os.path.join(tmp, "store")
    tl = TLStore(root, create=True, lease_owner="hnsw-test")
    vecs = {
        "alpha one": [1.0, 0.0, 0.0, 0.0],
        "alpha two": [0.99, 0.01, 0.0, 0.0],
        "far away tale": [0.0, 0.0, 1.0, 0.0],
        "other matters": [0.0, 1.0, 0.0, 0.0],
    }

    def emb(texts):
        return [list(vecs[t]) for t in texts]

    ingest_docs(tl, [("docA", "alpha one"), ("docA2", "alpha two"),
                     ("docF", "far away tale"),
                     ("docO", "other matters")],
                emb, store_id="hnsw-test", place_xdoc=True)
    return tl, emb


def test_index_flagoff_and_search():
    tmp = tempfile.mkdtemp(prefix="tl-hnsw-test-")
    tl, emb = tiny_store(tmp)
    pinned = tl.pin()
    idx = NarrowIndex(tl, pinned)
    qv = [1.0, 0.0, 0.0, 0.0]
    a = idx.dense_holons(qv)
    b = idx.dense_holons(qv, candidate_search=None)
    check("index/off-identical", a == b, repr((a, b)))
    check("index/off-no-report", idx.last_candidate_report is None)
    if not HAVE_HNSW:
        skip("index/search", "hnswlib absent")
        tl.close()
        return
    s = HolonCandidateIndex().build(
        {h: {"descriptor": list(np.asarray(v["descriptor"],
                                           dtype=np.float64)),
             "seq": v["seq"]} for h, v in idx.holons.items()},
        pinned[3])
    # Explicit (unattached) search, k >= N: identical full ranking.
    c = idx.dense_holons(qv, candidate_search=s,
                         candidate_k=len(idx.holons))
    check("index/search-k-ge-n-identical", c == a,
          repr((c, a)))
    check("index/report-populated",
          idx.last_candidate_report is not None
          and idx.last_candidate_report["rescored"] == len(a)
          and idx.last_candidate_report["stale_dropped"] == []
          and idx.last_candidate_report["unpublished"] == [],
          repr(idx.last_candidate_report))
    # Attached search flows through the real query path (query.py
    # calls idx.dense_holons(qvec) with no extra args).
    idx.attach_candidate_search(s)
    d = idx.dense_holons(qv, candidate_k=len(idx.holons))
    check("index/attached-flows", d == a, repr(d))
    # Explicit None forces exact even when attached.
    e = idx.dense_holons(qv, candidate_search=None)
    check("index/explicit-none-forces-exact", e == a, repr(e))
    idx.detach_candidate_search()
    check("index/detached-restores-exact",
          idx.dense_holons(qv) == a)
    # Generation mismatch refuses at attach and at call time.
    other = HolonCandidateIndex().build(
        {"h": {"descriptor": [1.0, 0.0, 0.0, 0.0], "seq": 1}},
        "other:0:0")
    try:
        idx.attach_candidate_search(other)
        check("index/attach-generation-refused", False, "no raise")
    except StaleGenerationError:
        check("index/attach-generation-refused", True)
    try:
        idx.dense_holons(qv, candidate_search=other)
        check("index/call-generation-refused", False, "no raise")
    except StaleGenerationError:
        check("index/call-generation-refused", True)
    tl.close()


def test_query_end_to_end_parity():
    tmp = tempfile.mkdtemp(prefix="tl-hnsw-qpath-")
    tl, emb = tiny_store(tmp)
    pinned = tl.pin()

    def emb1(q):
        return [1.0, 0.0, 0.0, 0.0]

    idx_exact = NarrowIndex(tl, pinned)
    dos_e, rec_e = NarrowQuery(tl, idx_exact, emb1).run("alpha")
    if not HAVE_HNSW:
        skip("qpath/parity", "hnswlib absent")
        tl.close()
        return
    s = HolonCandidateIndex().build(
        {h: {"descriptor": list(np.asarray(v["descriptor"],
                                           dtype=np.float64)),
             "seq": v["seq"]}
         for h, v in idx_exact.holons.items()}, pinned[3])
    idx_h = NarrowIndex(tl, pinned, candidate_search=s)
    dos_h, rec_h = NarrowQuery(tl, idx_h, emb1).run("alpha")
    check("qpath/entries-identical", dos_h == dos_e,
          repr((dos_h, dos_e)))
    me = dict(rec_e["metrics"])
    mh = dict(rec_h["metrics"])
    me.pop("T_ms", None)
    mh.pop("T_ms", None)
    check("qpath/receipt-identical", mh == me, repr((mh, me)))
    tl.close()


def main():
    test_version_pin()
    test_exact_topk_oracle()
    test_decide_flagoff_identity()
    test_decide_candidates_pure()
    test_hnsw_build_query()
    test_hnsw_determinism()
    test_hnsw_stale_and_coverage()
    test_hnsw_cost_and_update()
    test_place_with_search()
    test_index_flagoff_and_search()
    test_query_end_to_end_parity()
    print(f"{len(FAILS)} failures, {len(SKIPS)} skips")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
