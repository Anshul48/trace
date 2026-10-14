"""M1-C real navigation wiring tests.

- place.NavCounters / OrdinalCache (pure).
- place.PartitionCandidateIndex: deterministic flat-partition
  discovery behind the candidate-search boundary (E0-role
  primitive, NOT a directory/descent/rep/fusion variant).
- place.rescore_candidates: exact eligibility/capacity, direct
  fetch, published-ordinal ties.
- place.CandidateNavigator + attach_sync_nav: sync placement
  through ingest_docs (untouched) with per-placement work
  evidence; decide_with_search replenish.
- maint.drain_placement_backlog(navigator=...): deferred
  placement parity + per-doc work entries.
- Narrow legs: flag-off byte-identical with searches attached;
  flag-on parity + bounded per-query work; honest fallback.
- Dossier legs ride index.py wiring (no dossier.py edits):
  invocation evidence + parity.
- Serving legs: separate audit state per population, direct
  fetch (descriptor-touch counting: no disguised loops),
  explicit changed-ID sets.
- HNSW-backend checks mirror the partition checks and SKIP
  when hnswlib is absent.

Run: HF_HOME=<repo>/local-data/hf-cache HF_HUB_OFFLINE=1
  PYTHONHASHSEED=0 tl-sys/.venv/bin/python
  tl-sys/tests/test_m1c_nav.py
"""
import hashlib
import json
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

from tlsys.place import (  # noqa: E402
    CandidateNavigator, LiveAuditCache, NavCounters, OrdinalCache,
    PartitionCandidateIndex, attach_sync_nav, decide,
    decide_with_navigator, decide_with_search, detach_sync_nav,
    read_xholons, rescore_candidates, sync_nav_active)
from tlsys.hnsw_candidates import (  # noqa: E402
    StaleGenerationError, exact_cosine_topk)
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys import maint as _maint  # noqa: E402

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


def seed_of(text):
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


def make_emb(dim=16, n_clusters=5, seed=7):
    rng = np.random.RandomState(seed)
    centers = rng.randn(n_clusters, dim)

    def emb(texts):
        out = []
        for t in texts:
            head = t.split()[0] if t.split() else ""
            c = 0
            if head.startswith("topic"):
                try:
                    c = int(head[5:]) % n_clusters
                except ValueError:
                    c = 0
            r = np.random.RandomState(seed_of(t))
            v = centers[c] + 0.05 * r.randn(dim)
            out.append([float(x) for x in v])
        return out

    def emb1(q):
        return emb([q])[0]

    return emb, emb1, centers


def small_docs():
    docs = []
    for c in range(3):
        for i in range(4):
            docs.append((f"doc{c}-{i}",
                         f"topic{c} alpha beta gamma {c}-{i}"))
    docs.append(("docF", "far away tale zulu"))
    docs.append(("docO", "other matters vicar"))
    return docs


def make_store(tmp, name, docs, emb, **kw):
    root = os.path.join(tmp, name)
    tl = TLStore(root, create=True, lease_owner="m1c-test")
    kw.setdefault("store_id", "m1c-test")
    kw.setdefault("place_xdoc", True)
    ingest_docs(tl, docs, emb, **kw)
    return tl


def xh_summary(tl):
    # Cross-store comparable: atom IDs embed fresh revision UUIDs
    # per ingest, so membership SETS cannot match across stores;
    # member counts + exact descriptors capture the join decisions
    # and the published math.
    xh = read_xholons(tl, tl.pin())
    return {h: (len(v["members"]),
                [round(x, 9) for x in v["descriptor"]])
            for h, v in xh.items()}


def partition_search_for_holons(idx, pinned):
    return PartitionCandidateIndex().build(
        {h: {"descriptor": list(np.asarray(v["descriptor"],
                                          dtype=np.float64)),
             "seq": v["seq"]} for h, v in idx.holons.items()},
        pinned[3])


def partition_search_for_atoms(idx, pinned):
    return PartitionCandidateIndex().build(
        {a: {"descriptor": list(np.asarray(v["descriptor"],
                                          dtype=np.float64)),
             "seq": v["seq"]} for a, v in idx.atoms.items()},
        pinned[3])


class CountingInner(dict):
    """Inner live-dict wrapper counting descriptor touches.

    dict.get does NOT dispatch to __getitem__ overrides, so
    audit/seq reads (.get("seq")) stay invisible while every
    vector fetch (["descriptor"]) is counted.
    """

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.__dict__["touches"] = 0

    def __getitem__(self, key):
        if key == "descriptor":
            self.__dict__["touches"] += 1
        return super().__getitem__(key)


def wrap_live(live):
    for h in list(live):
        live[h] = CountingInner(live[h])
    return live


def touches(live):
    return sum(v.touches for v in live.values()
               if isinstance(v, CountingInner))


def synth_pop(n=120, dim=16, seed=0, prefix="h"):
    rng = np.random.RandomState(seed)
    centers = rng.randn(6, dim)
    h = {}
    for i in range(n):
        c = centers[i % 6]
        v = c + 0.1 * rng.randn(dim)
        h[f"{prefix}{i:03d}"] = {
            "descriptor": [float(x) for x in v],
            "seq": 100 + i, "members": [f"m{i}"]}
    return h, rng


def test_counters_and_ordinals():
    c = NavCounters()
    c.record("p", discovered=10, visited=8, rescored=8)
    c.record("p", discovered=5, visited=5, rescored=5)
    c.record("q", discovered=3, note="x")
    t = c.totals()
    check("nav/counters-totals",
          t == {"p": {"discovered": 15, "visited": 13,
                      "rescored": 13},
                "q": {"discovered": 3}}, repr(t))
    check("nav/counters-json",
          json.loads(json.dumps(c.records))[1]["visited"] == 5)

    live = {f"h{i}": {"seq": i} for i in range(6)}
    oc = OrdinalCache()
    m1, hit1 = oc.ordinals(live, 1)
    m2, hit2 = oc.ordinals(live, 1)
    check("nav/ordinals-hit",
          hit1 is False and hit2 is True and m2 is m1
          and m1 == {f"h{i}": i for i in range(6)}, repr(m1))
    _m3, hit3 = oc.ordinals(live, 2)
    check("nav/ordinals-version-rebuilds", hit3 is False)
    live["h-new"] = {"seq": 9}
    m4, hit4 = oc.ordinals(live, 2)
    check("nav/ordinals-add-detected",
          hit4 is False and m4["h-new"] == 6, repr(m4))
    oc.invalidate()
    _m5, hit5 = oc.ordinals(live, 2)
    check("nav/ordinals-invalidate", hit5 is False)


def test_partition_backend():
    pop, rng = synth_pop()
    q = [float(x) for x in rng.randn(16)]
    s = PartitionCandidateIndex().build(pop, "gen:0:1")
    check("nav/part-build",
          s.n == 120 and s.generation == "gen:0:1"
          and len(s.ordinals) == 120
          and s.ordinals["h000"] == 0, repr(s.n))
    r = s.query(q, k=40, live=pop)
    check("nav/part-query-shape",
          len(r["hids"]) == 40 and r["k"] == 40
          and r["stale_dropped"] == []
          and r["n_scored_native_unknown"] is False
          and r["cells_visited"] >= 1
          and r["members_visited"] >= 40, repr(
              {k: r[k] for k in ("k", "cells_visited",
                                "members_visited")}))
    # Determinism: identical emission across rebuilds.
    s2 = PartitionCandidateIndex().build(pop, "gen:0:1")
    check("nav/part-deterministic",
          s2.query(q, k=40, live=pop)["hids"] == r["hids"])
    # Recall on clustered data (measured operating point; the
    # committed bar is deliberately below the observed value).
    exact = exact_cosine_topk(
        q, {h: v["descriptor"] for h, v in pop.items()}, 40)
    rec = len(set(r["hids"]) & set(h for h, _s in exact))
    print(f"info part-recall@40: {rec}/40")
    check("nav/part-recall-clustered", rec >= 38, f"{rec}/40")
    # k >= N is complete (provable parity regime).
    full = s.query(q, k=500, live=pop)
    check("nav/part-k-ge-n-complete",
          len(full["hids"]) == 120
          and set(full["hids"]) == set(pop), repr(len(
              full["hids"])))
    # Stale-drop + coverage + refusal mirror the HNSW boundary.
    live = dict(pop)
    live["h007"] = {"descriptor": list(q), "members": ["x"]}
    r3 = s.query(q, k=500, live=live)  # complete: h007 collected
    check("nav/part-stale-dropped",
          "h007" in r3["stale_dropped"]
          and "h007" not in r3["hids"], repr(
              r3["stale_dropped"][:3]))
    cov = s.coverage(live)
    check("nav/part-coverage",
          cov["indexed"] == 120 and cov["live"] == 120
          and cov["stale"] == ["h007"]
          and cov["unpublished"] == [], repr(cov))
    live["h-new"] = {"descriptor": list(q), "seq": 999,
                     "members": ["y"]}
    check("nav/part-coverage-unpublished",
          s.coverage(live)["unpublished"] == ["h-new"])
    try:
        s.query(q, k=5, generation="gen:0:9")
        check("nav/part-generation-refused", False, "no raise")
    except StaleGenerationError:
        check("nav/part-generation-refused", True)
    try:
        s.add({"z": {"descriptor": list(q), "seq": 1}},
              "gen:0:9")
        check("nav/part-add-refused", False, "no raise")
    except StaleGenerationError:
        check("nav/part-add-refused", True)
    n0 = s.n
    added = s.add({"h-new": {"descriptor": list(q), "seq": 999}},
                  "gen:0:1")
    check("nav/part-add",
          added == 1 and s.n == n0 + 1
          and s.ordinals["h-new"] == n0, repr((added, s.n)))
    check("nav/part-add-noop",
          s.add({"h-new": {"descriptor": list(q), "seq": 999}},
                "gen:0:1") == 0)
    e = PartitionCandidateIndex().build({}, "g:0")
    er = e.query([1.0] * 16, k=5)
    check("nav/part-empty",
          e.n == 0 and er["hids"] == []
          and e.cost()["index_bytes"] == 0)
    check("nav/part-add-empty-rebuilds",
          e.add({"z": {"descriptor": [1.0] * 16, "seq": 1}},
                "g:0") == 1 and e.n == 1)
    cost = s.cost()
    check("nav/part-cost",
          cost["n"] == 121 and cost["index_bytes"] > 0
          and cost["param_backend"].startswith("partition"),
          repr({k: cost[k] for k in ("n", "index_bytes")}))


def test_rescore():
    pop, rng = synth_pop()
    q = [float(x) for x in rng.randn(16)]
    # Agreement with the exact full path (order + membership).
    exact = decide(q, pop, t_place=0.0)
    st = {}
    got = rescore_candidates(q, pop, list(pop), t_place=0.0,
                             stats=st)
    check("nav/rescore-agrees-full",
          got == exact and st["scored"] == 120
          and st["visited"] == 120 and st["unknown"] == []
          and st["full_skipped"] == 0, repr((got, exact)))
    exact_t = decide(q, pop, t_place=0.5)
    got_t = rescore_candidates(q, pop, list(pop), t_place=0.5)
    check("nav/rescore-threshold", got_t == exact_t,
          repr((got_t, exact_t)))
    # Unknown + full reporting.
    live = dict(pop)
    live["h003"] = {"descriptor": live["h003"]["descriptor"],
                    "seq": 103,
                    "members": [f"m{i}" for i in range(25)]}
    st2 = {}
    rescore_candidates(q, live, ["h003", "h-nope", "h010"],
                       t_place=0.0, stats=st2)
    check("nav/rescore-unknown-full",
          st2["unknown"] == ["h-nope"]
          and st2["full_skipped"] == 1 and st2["scored"] == 1
          and st2["visited"] == 2, repr(st2))
    # Direct fetch: vector touches == rescored, never N.
    live2 = wrap_live(dict(pop))
    st3 = {}
    rescore_candidates(q, live2, ["h010", "h011"], t_place=0.0,
                       stats=st3)
    check("nav/rescore-direct-fetch",
          touches(live2) == 2 and st3["scored"] == 2,
          repr(touches(live2)))
    # Published-ordinal ties: duplicate descriptors break by
    # index label order, stable across live-dict build orders.
    dup = {}
    for i in range(8):
        dup[f"xdoc-d{i}"] = {"descriptor": [1.0, 0.0, 0.0],
                             "seq": 50 + i, "members": [f"a{i}"]}
    s = PartitionCandidateIndex().build(dup, "g")
    nav = CandidateNavigator(search=s, k=8)
    nav.discover([1.0, 0.0, 0.0], dup)
    j1 = rescore_candidates([1.0, 0.0, 0.0], dup, list(dup),
                            t_place=0.0,
                            ordinal_key=nav.ordinal_key)
    rev = {h: dup[h] for h in reversed(list(dup))}
    j2 = rescore_candidates([1.0, 0.0, 0.0], rev,
                            list(reversed(list(dup))),
                            t_place=0.0,
                            ordinal_key=nav.ordinal_key)
    check("nav/rescore-ordinal-ties",
          j1 == j2 == ["xdoc-d0", "xdoc-d1", "xdoc-d2"],
          repr((j1, j2)))


def test_decide_with_search_replenish():
    # Crafted: round-0 discovery (k=2, one cell, label order)
    # hits only full holons; the qualifier sits beyond k.
    q = [1.0, 0.0, 0.0, 0.0]
    pop = {
        "xdoc-a-full1": {"descriptor": list(q), "seq": 1,
                         "members": [f"m{i}" for i in range(25)]},
        "xdoc-a-full2": {"descriptor": list(q), "seq": 2,
                         "members": [f"n{i}" for i in range(25)]},
        "xdoc-b-qual": {"descriptor": [0.999, 0.045, 0.0, 0.0],
                        "seq": 3, "members": ["a1"]},
        "xdoc-c-far": {"descriptor": [0.0, 0.0, 0.0, 1.0],
                       "seq": 4, "members": ["a2"]},
        "xdoc-c-far2": {"descriptor": [0.0, 0.0, 1.0, 0.0],
                        "seq": 5, "members": ["a3"]},
    }
    s = PartitionCandidateIndex().build(pop, "gen:0:1")
    off, rep_off = decide_with_search(
        q, pop, s, k=2, generation="gen:0:1", t_place=0.5)
    check("nav/replenish-off-empty",
          off == [] and rep_off["rounds"] == 1
          and rep_off["replenished"] == 0
          and rep_off["full_skipped"] == 2
          and rep_off["changed_ids"] == [], repr(rep_off))
    on, rep_on = decide_with_search(
        q, pop, s, k=2, generation="gen:0:1", t_place=0.5,
        replenish=True, max_rounds=3)
    check("nav/replenish-rescues",
          on == ["xdoc-b-qual"] and rep_on["rounds"] == 3
          and rep_on["replenished"] == 3
          and rep_on["discovered"] == 11
          and rep_on["changed_ids"] == [], repr(rep_on))
    # Quota reached in round 0: no extra rounds.
    exact = decide(q, pop, t_place=0.0)
    got, rep = decide_with_search(
        q, pop, s, k=5, generation="gen:0:1", t_place=0.0,
        replenish=True)
    check("nav/replenish-quota-stops",
          got == exact and rep["rounds"] == 1, repr(rep))


def test_sync_nav_ingest():
    tmp = tempfile.mkdtemp(prefix="tl-m1c-test-")
    emb, _emb1, _c = make_emb()
    docs = small_docs()
    tl_exact = make_store(tmp, "exact", docs, emb)
    sum_exact = xh_summary(tl_exact)
    tl_exact.close()
    nav = CandidateNavigator(k=200)
    attach_sync_nav(nav)
    try:
        check("nav/sync-attached", sync_nav_active() is True)
        tl_nav = make_store(tmp, "nav", docs, emb)
        sum_nav = xh_summary(tl_nav)
        tl_nav.close()
    finally:
        back = detach_sync_nav()
    check("nav/sync-detached",
          back is nav and sync_nav_active() is False)
    check("nav/sync-parity", sum_nav == sum_exact,
          repr({h: (sum_nav.get(h), sum_exact.get(h))
                for h in set(sum_nav) | set(sum_exact)
                if sum_nav.get(h) != sum_exact.get(h)}))
    tot = nav.counters.totals().get("sync-place", {})
    check("nav/sync-invoked",
          tot.get("rounds", 0) >= len(docs)
          and tot.get("joins", 0) >= 0, repr(tot))
    recs = [r for r in nav.counters.records
            if r["path"] == "sync-place"]
    check("nav/sync-per-placement-counters",
          len(recs) == len(docs)
          and all(set(("discovered", "visited", "rescored",
                       "rounds", "joins")) <= set(r)
                  for r in recs),
          repr(recs[0] if recs else None))
    # Explicit candidate_ids ignore the attached navigator.
    attach_sync_nav(CandidateNavigator(k=200))
    try:
        pop, rng = synth_pop(n=30)
        q = [float(x) for x in rng.randn(16)]
        st = {}
        decide(q, pop, candidate_ids=list(pop)[:5], stats=st)
        check("nav/sync-explicit-ignores-nav",
              "nav_rounds" not in st and st["scored"] == 5,
              repr(st))
    finally:
        detach_sync_nav()


def test_deferred_drain():
    tmp = tempfile.mkdtemp(prefix="tl-m1c-test-")
    emb, _emb1, _c = make_emb()
    docs = small_docs()
    tl_e = make_store(tmp, "exact", docs, emb, place_budget=0)
    rep_e = _maint.drain_placement_backlog(tl_e, store_id="m1c-test")
    sum_e = xh_summary(tl_e)
    tl_e.close()
    check("nav/drain-default-keys",
          "nav" not in rep_e and "nav_totals" not in rep_e,
          repr(sorted(rep_e)))
    tl_n = make_store(tmp, "nav", docs, emb, place_budget=0)
    nav = CandidateNavigator(k=200)
    rep_n = _maint.drain_placement_backlog(
        tl_n, store_id="m1c-test", navigator=nav)
    sum_n = xh_summary(tl_n)
    tl_n.close()
    check("nav/drain-parity",
          sum_n == sum_e and rep_n["drained"] == rep_e["drained"],
          repr((rep_n["drained"], rep_e["drained"])))
    check("nav/drain-nav-entries",
          len(rep_n["nav"]) == len(rep_n["drained"])
          and all(set(("doc", "joins", "discovered", "visited",
                       "rescored", "rounds", "replenished",
                       "changed_ids")) <= set(e)
                  for e in rep_n["nav"])
          and rep_n["nav_totals"]["placements"]
          == len(rep_n["drained"]), repr(rep_n["nav_totals"]))
    tot = nav.counters.totals().get("deferred-place", {})
    check("nav/drain-invoked",
          tot.get("rounds", 0) >= len(rep_n["drained"])
          and tot.get("rescored", 0) > 0, repr(tot))


NAV_ON = {"USE_CANDIDATE_HOLONS": True, "USE_CANDIDATE_ATOMS": True,
          "CANDIDATE_K": 200}


def run_shapes(tl, idx, emb1, queries, cfg):
    dos, recs, navs = [], [], []
    nq = NarrowQuery(tl, idx, emb1, cfg=cfg)
    for qtext in queries:
        dos_q, rec_q = nq.run(qtext)
        dos.append(dos_q)
        recs.append(rec_q)
        navs.append(nq.last_nav)
    return dos, recs, navs


def strip_timing(rec):
    rec = json.loads(json.dumps(rec))
    rec["metrics"].pop("T_ms", None)
    return rec


def test_narrow_flags():
    tmp = tempfile.mkdtemp(prefix="tl-m1c-test-")
    emb, emb1, _c = make_emb()
    tl = make_store(tmp, "s", small_docs(), emb)
    pinned = tl.pin()
    queries = ["topic0 alpha", "topic1 beta", "topic2 gamma",
               "far away", "other matters"]
    idx_plain = NarrowIndex(tl, pinned)
    dos_e, rec_e, _n = run_shapes(tl, idx_plain, emb1, queries,
                                  None)
    # Attach alone never reroutes: byte-identical defaults.
    idx_att = NarrowIndex(
        tl, pinned,
        candidate_search=partition_search_for_holons(
            idx_plain, pinned),
        atom_candidate_search=partition_search_for_atoms(
            idx_plain, pinned))
    dos_a, rec_a, navs_a = run_shapes(tl, idx_att, emb1, queries,
                                      None)
    check("nav/flagoff-entries-identical", dos_a == dos_e)
    check("nav/flagoff-receipt-identical",
          [strip_timing(r) for r in rec_a]
          == [strip_timing(r) for r in rec_e])
    check("nav/flagoff-no-candidate-key",
          all("candidate_nav" not in r["metrics"] for r in rec_a))
    check("nav/flagoff-last-nav-none",
          all(v is None for v in navs_a))
    # Flag-on with k >= N: identical results + work evidence.
    idx_nav = NarrowIndex(
        tl, pinned,
        candidate_search=partition_search_for_holons(
            idx_plain, pinned),
        atom_candidate_search=partition_search_for_atoms(
            idx_plain, pinned))
    dos_n, rec_n, navs_n = run_shapes(tl, idx_nav, emb1, queries,
                                      dict(NAV_ON))
    check("nav/flagon-entries-identical", dos_n == dos_e)
    same_metrics = True
    for r_new, r_old in zip(rec_n, rec_e):
        m_new = strip_timing(r_new)["metrics"]
        m_new.pop("candidate_nav", None)
        if m_new != strip_timing(r_old)["metrics"]:
            same_metrics = False
    check("nav/flagon-metrics-identical-modulo-nav",
          same_metrics)
    check("nav/flagon-receipt-has-nav",
          all("candidate_nav" in r["metrics"] for r in rec_n)
          and all(v is not None and "holons" in v and "atoms" in v
                  for v in navs_n), repr(navs_n[0] if navs_n
                                         else None))
    hol = navs_n[0]["holons"]
    check("nav/flagon-work-keys",
          hol["discovered"] == len(idx_nav.holons)
          and hol["rescored"] == len(idx_nav.holons)
          and hol["changed_ids"] == []
          and "visited" in hol, repr(
              {k: hol[k] for k in ("discovered", "rescored")}))
    # Flags on, nothing attached: honest fallback, same results.
    dos_f, rec_f, navs_f = run_shapes(tl, idx_plain, emb1,
                                      queries, dict(NAV_ON))
    check("nav/fallback-identical",
          dos_f == dos_e
          and [strip_timing(r)["metrics"]
               for r in [dict(r, metrics={k: v for k, v in
                                          r["metrics"].items()
                                          if k != "candidate_nav"})
                         for r in rec_f]]
          == [strip_timing(r)["metrics"] for r in rec_e])
    check("nav/fallback-recorded",
          all(v["holons"]["fallback"] == "no-search-attached"
              and v["atoms"]["fallback"] == "no-search-attached"
              for v in navs_f), repr(navs_f[0]))
    tl.close()


def test_dossier_legs():
    tmp = tempfile.mkdtemp(prefix="tl-m1c-test-")
    emb, emb1, _c = make_emb()
    tl = make_store(tmp, "s", small_docs(), emb)
    pinned = tl.pin()
    topics = ["topic0 alpha", "topic1 beta"]
    idx_e = NarrowIndex(tl, pinned)
    dq_e = DossierQuery(tl, idx_e, emb1,
                        cfg={"DOSSIER_SHAPE": "cross-topic"})
    dos_e, rec_e = dq_e.run("topic0 topic1", topics=topics)
    check("nav/dossier-exact-no-report",
          idx_e.last_atom_candidate_report is None)
    idx_n = NarrowIndex(
        tl, pinned,
        atom_candidate_search=partition_search_for_atoms(
            idx_e, pinned))
    dq_n = DossierQuery(tl, idx_n, emb1,
                        cfg={"DOSSIER_SHAPE": "cross-topic"})
    dos_n, rec_n = dq_n.run("topic0 topic1", topics=topics)
    rep = idx_n.last_atom_candidate_report
    check("nav/dossier-leg-invoked",
          rep is not None and rep["rescored"] > 0
          and rep["discovered"] > 0, repr(rep))
    check("nav/dossier-entries-identical", dos_n == dos_e)
    # Narrow-shape dossier with NARROW nav flags: routed + parity.
    idx_h = NarrowIndex(
        tl, pinned,
        candidate_search=partition_search_for_holons(
            idx_e, pinned),
        atom_candidate_search=partition_search_for_atoms(
            idx_e, pinned))
    dq_h = DossierQuery(tl, idx_h, emb1, cfg={"NARROW": dict(
        NAV_ON)})
    dos_h, rec_h = dq_h.run("topic0 alpha")
    dq_e2 = DossierQuery(tl, idx_e, emb1)
    dos_e2, rec_e2 = dq_e2.run("topic0 alpha")
    check("nav/dossier-narrow-nav-parity",
          dos_h == dos_e2
          and "candidate_nav" in rec_h["metrics"], repr(
              dos_h == dos_e2))
    tl.close()


def test_audit_separation_and_direct_fetch():
    tmp = tempfile.mkdtemp(prefix="tl-m1c-test-")
    emb, emb1, _c = make_emb()
    tl = make_store(tmp, "s", small_docs(), emb)
    pinned = tl.pin()
    idx = NarrowIndex(tl, pinned)
    idx.attach_candidate_search(
        partition_search_for_holons(idx, pinned))
    idx.attach_atom_search(partition_search_for_atoms(idx, pinned))
    qv = emb1("topic0 alpha")
    # Alternating legs keep their own audit state: with the old
    # shared single-entry cache the second round would re-audit.
    idx.dense_holons(qv, candidate_k=200)
    idx.dense_atoms(qv, candidate_k=200)
    idx.dense_holons(qv, candidate_k=200)
    idx.dense_atoms(qv, candidate_k=200)
    check("nav/audit-separated",
          idx.last_candidate_report["audit_cached"] is True
          and idx.last_atom_candidate_report["audit_cached"]
          is True, repr((idx.last_candidate_report[
              "audit_cached"],
              idx.last_atom_candidate_report["audit_cached"])))
    check("nav/changed-ids-explicit",
          idx.last_candidate_report["changed_ids"] == []
          and idx.last_atom_candidate_report["changed_ids"]
          == [])
    # Direct fetch: descriptor touches == rescored on both legs.
    wrap_live(idx.holons)
    wrap_live(idx.atoms)
    idx.note_population_changed("holons")
    idx.note_population_changed("atoms")
    idx.dense_holons(qv, candidate_k=5)
    rh = idx.last_candidate_report
    check("nav/holons-direct-fetch",
          touches(idx.holons) == rh["rescored"] == 5
          and rh["visited"] == 5, repr((touches(idx.holons),
                                        rh["rescored"])))
    idx.dense_atoms(qv, candidate_k=7)
    ra = idx.last_atom_candidate_report
    check("nav/atoms-direct-fetch",
          touches(idx.atoms) == ra["rescored"] == 7
          and ra["visited"] == 7, repr((touches(idx.atoms),
                                        ra["rescored"])))
    # Exact legs touch the whole population (the contrast).
    idx.dense_holons(qv, candidate_search=None)
    check("nav/exact-touches-all",
          touches(idx.holons) == 5 + len(idx.holons),
          repr(touches(idx.holons)))
    tl.close()


def scale_docs(n=250, n_clusters=5):
    docs = []
    for i in range(n):
        c = i % n_clusters
        docs.append((f"sdoc{i:04d}",
                     f"topic{c} filler words number {i}"))
    return docs


def test_scale_narrow_bounded():
    tmp = tempfile.mkdtemp(prefix="tl-m1c-test-")
    emb, emb1, _c = make_emb(n_clusters=5)
    tl = make_store(tmp, "scale", scale_docs(), emb)
    pinned = tl.pin()
    idx_e = NarrowIndex(tl, pinned)
    n_h, n_a = len(idx_e.holons), len(idx_e.atoms)
    idx_n = NarrowIndex(
        tl, pinned,
        candidate_search=partition_search_for_holons(
            idx_e, pinned),
        atom_candidate_search=partition_search_for_atoms(
            idx_e, pinned))
    queries = [f"topic{c} filler" for c in range(5)] + ["zzz qq"]
    cfg = {"USE_CANDIDATE_HOLONS": True,
           "USE_CANDIDATE_ATOMS": True, "CANDIDATE_K": 120}
    nq_e, nq_n = NarrowQuery(tl, idx_e, emb1), NarrowQuery(
        tl, idx_n, emb1, cfg=cfg)
    agree_h = agree_a = agree_entries = 0
    for qtext in queries:
        qv = emb1(qtext)
        h_e = [h for h, _s in idx_e.dense_holons(qv)[:100]]
        h_n = [h for h, _s in nq_n._dense_holons_vec(
            qv, topk=100, nav_diag={})]
        a_e = [a for a, _s in idx_e.dense_atoms(qv)[:100]]
        a_n = [a for a, _s in nq_n._dense_atoms_vec(
            qv, topk=100, nav_diag={})]
        agree_h += h_e == h_n
        agree_a += a_e == a_n
        dos_e, _r = NarrowQuery(tl, idx_e, emb1).run(qtext)
        dos_n, _r = nq_n.run(qtext)
        agree_entries += dos_e == dos_n
    print(f"info scale@k120: holons-heads {agree_h}/{len(queries)} "
          f"atoms-heads {agree_a}/{len(queries)} "
          f"entries {agree_entries}/{len(queries)} "
          f"(N holons={n_h} atoms={n_a})")
    tot = idx_n.nav_counters.totals()
    nav_h = tot.get("dense-holons-nav", {})
    nav_a = tot.get("dense-atoms-nav", {})
    # Bounded per-query vector work: every nav call rescored a
    # strict subset (k=120 < N on both legs here).
    recs_h = [r for r in idx_n.nav_counters.records
              if r["path"] == "dense-holons-nav"]
    recs_a = [r for r in idx_n.nav_counters.records
              if r["path"] == "dense-atoms-nav"]
    check("nav/scale-bounded",
          len(recs_h) == 2 * len(queries)
          and len(recs_a) == 2 * len(queries)
          and all(r["rescored"] <= 120 for r in recs_h)
          and all(r["rescored"] <= 120 for r in recs_a)
          and nav_h.get("rescored", 0)
          < 2 * len(queries) * n_h
          and nav_a.get("rescored", 0)
          < 2 * len(queries) * n_a,
          repr((nav_h, nav_a)))
    # Determinism: identical nav heads across repeated runs.
    qv = emb1(queries[0])
    r1 = nq_n._dense_holons_vec(qv, topk=100, nav_diag={})
    r2 = nq_n._dense_holons_vec(qv, topk=100, nav_diag={})
    check("nav/scale-deterministic", r1 == r2)
    tl.close()


def test_scale_place_policy():
    pop, rng = synth_pop(n=2000, prefix="xdoc-s")
    nav = CandidateNavigator(k=200)
    agree = 0
    trials = 12
    ok_policy = True
    for t in range(trials):
        if t % 2 == 0:
            # Member self-query: top join must be findable.
            hid = f"xdoc-s{(t * 173) % 2000:03d}"
            q = list(pop[hid]["descriptor"])
        else:
            q = [float(x) for x in rng.randn(16)]
        st = {}
        joins = decide_with_navigator(q, pop, nav, t_place=0.0,
                                      stats=st)
        exact = decide(q, pop, t_place=0.0)
        agree += joins == exact
        # Policy exactness on every trial: threshold + cap +
        # non-full, regardless of discovery recall.
        if not (len(joins) <= 3 and len(set(joins)) == len(joins)
                and all(len(pop[h]["members"]) < 25
                        for h in joins)):
            ok_policy = False
    print(f"info scale-place@k200: joins-agreement "
          f"{agree}/{trials} (N=2000)")
    tot = nav.counters.totals().get("place-nav", {})
    check("nav/scale-place-policy", ok_policy)
    check("nav/scale-place-bounded",
          tot.get("rescored", 0) < trials * 2000
          and tot.get("rounds", 0) >= trials, repr(tot))
    # Determinism across navigator instances.
    nav2 = CandidateNavigator(k=200)
    q = [float(x) for x in rng.randn(16)]
    check("nav/scale-place-deterministic",
          decide_with_navigator(q, pop, nav, t_place=0.5)
          == decide_with_navigator(q, pop, nav2, t_place=0.5))


def test_hnsw_backend():
    if not HAVE_HNSW:
        skip("nav-hnsw/all", "hnswlib absent")
        return
    from tlsys.hnsw_candidates import HolonCandidateIndex
    pop, rng = synth_pop()
    q = [float(x) for x in rng.randn(16)]
    s = HolonCandidateIndex().build(pop, "gen:0:1")
    nav = CandidateNavigator(search=s, k=40)
    new_ids, drep = nav.discover(q, pop)
    check("nav-hnsw/discover",
          len(new_ids) == 40 and drep["changed_ids"] == []
          and drep["n_scored_native_unknown"] is True,
          repr({k: drep[k] for k in ("discovered", "new")}))
    joins = decide_with_navigator(q, pop, nav, t_place=0.0)
    check("nav-hnsw/joins-agree",
          joins == decide(q, pop, t_place=0.0), repr(joins))
    # Pending (seq-less) entries union + rescore live, never index.
    live = dict(pop)
    live["xdoc-pend"] = {"descriptor": list(q),
                         "members": ["a1"]}
    got = decide_with_navigator(q, live, nav, t_place=0.0)
    check("nav-hnsw/pending-rescored",
          "xdoc-pend" in got and "xdoc-pend" not in s.hids,
          repr(got))
    # Strict generation refuses.
    nav_s = CandidateNavigator(search=s, k=40,
                               strict_generation=True,
                               generation="gen:0:9")
    try:
        nav_s.discover(q, pop)
        check("nav-hnsw/strict-refuses", False, "no raise")
    except StaleGenerationError:
        check("nav-hnsw/strict-refuses", True)
    # Ordinals append-only across add.
    before = nav.ordinal_key("h010")
    s.add({"h-new": {"descriptor": list(q), "seq": 999}},
          "gen:0:1")
    nav.discover(q, pop)
    check("nav-hnsw/ordinals-stable",
          nav.ordinal_key("h010") == before, repr(before))


def main():
    test_counters_and_ordinals()
    test_partition_backend()
    test_rescore()
    test_decide_with_search_replenish()
    test_sync_nav_ingest()
    test_deferred_drain()
    test_narrow_flags()
    test_dossier_legs()
    test_audit_separation_and_direct_fetch()
    test_scale_narrow_bounded()
    test_scale_place_policy()
    test_hnsw_backend()
    print(f"{len(FAILS)} failures, {len(SKIPS)} skips")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
