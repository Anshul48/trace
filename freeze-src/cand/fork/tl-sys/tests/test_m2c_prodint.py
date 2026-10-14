"""M2-C product integration: keyed projections, bounded nomination,
serving wire-up.

Covers the TL-M2 job-4 repairs (product-integration-20261006T0900Z v1):
keyed doc-atom + hierarchy projections with consumed frontiers
(tlsys.proj), bounded leaf/parent nomination before exact scoring,
HierQuery bounded parent nomination, and the flag-gated Narrow
hierarchy evidence leg. Deterministic fake encoder, scratch stores
under /tmp.

Checks:
  proj-cold-parity .. cold projection view == read_seg_hierarchy +
                      _doc_atom_rows rows + read_xholons
  proj-ingest-warm .. warm sync-placement ingest consumes only new
  proj-warm-local ... warm update after an append consumes only new
                      commits; per-append organize artifact reads stay
                      at a small fixed bound
  proj-persist ...... checkpoint survives close/reopen; warm catch-up
  proj-corrupt ...... corrupt checkpoint -> cold rebuild, same results
  nav-parity ........ navigator organize == exact organize structure
  nav-bounded ....... guided parent_budget caps parents_scored and
                      keeps ablation recall
  narrow-hier-optin . default receipts lack hierarchy; flag on adds
                      metrics[hierarchy] without changing rows
  debt-report ....... organize report carries catchup/debt/churn/
                      retained with sane values + budget backpressure

Run: tl-sys/.venv/bin/python tl-sys/tests/test_m2c_prodint.py
"""
import collections
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

import numpy as np

from tlsys.store_if import TLStore, CallTrace
from tlsys.ingest import ingest_docs
from tlsys.index import NarrowIndex
from tlsys.query import HierQuery, NarrowQuery
from tlsys.place import (
    MAX_LEAF_MEMBERS, MAX_SEG_MEMBERSHIPS, CandidateNavigator,
    read_seg_hierarchy, read_xholons,
)
from tlsys.maint import organize_segments, _doc_atom_rows
from tlsys.proj import Projections, PROJ_VERSION

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


V_SPORT = pad([1.0, 0.0, 0.0, 0.0])
V_MED = pad([0.0, 1.0, 0.0, 0.0])
V_TECH = pad([0.0, 0.0, 1.0, 0.0])


def emb(texts):
    out = []
    for t in texts:
        votes = [(t.count("sport"), V_SPORT), (t.count("medic"), V_MED),
                 (t.count("techn"), V_TECH)]
        votes.sort(key=lambda kv: -kv[0])
        out.append(list(votes[0][1]))
    return out


def emb1(q):
    return emb([q])[0]


def run_of(word, n, start=0):
    return " ".join(f"{word}{i}" for i in range(start, start + n))


def main():
    tmp = tempfile.mkdtemp(prefix="tlsys-m2c-")
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="test-m2c")
    docs = [(f"sport-{i}", run_of("sport", 150, 200 * i))
            for i in range(4)]
    docs += [(f"med-{i}", run_of("medic", 150, 5000 + 200 * i))
             for i in range(4)]
    docs.append(("tech-0", run_of("techn", 150, 9000)))
    ingest_docs(tl, docs, emb)
    org0 = organize_segments(tl)
    check("proj-setup-organized",
          sorted(org0["organized"]) == sorted(d for d, _t in docs),
          f"{org0}")

    # -- cold parity: projection view == committed reads --------------
    pin0 = tl.pin()
    proj = Projections()
    cup0 = proj.update(tl)
    hier0 = read_seg_hierarchy(tl, pin0)
    view0 = proj.hierarchy_view()
    check("proj-cold-parity",
          cup0["cold"] is True
          and set(view0["leaves"]) == set(hier0["leaves"])
          and set(view0["parents"]) == set(hier0["parents"])
          and all(view0["leaves"][k]["members"]
                  == hier0["leaves"][k]["members"]
                  and np.allclose(view0["leaves"][k]["descriptor"],
                                  hier0["leaves"][k]["descriptor"])
                  and view0["leaves"][k]["seq"]
                  == hier0["leaves"][k]["seq"] for k in hier0["leaves"])
          and all(view0["parents"][k]["members"]
                  == hier0["parents"][k]["members"]
                  and view0["parents"][k]["children"]
                  == hier0["parents"][k]["children"]
                  and np.allclose(view0["parents"][k]["descriptor"],
                                  hier0["parents"][k]["descriptor"])
                  and view0["parents"][k]["seq"]
                  == hier0["parents"][k]["seq"] for k in hier0["parents"]),
          f"{cup0}")
    rows_ok = True
    for d, _t in docs:
        if proj.doc_rows(d) != [tuple(r) for r in
                               _doc_atom_rows(tl, d)]:
            rows_ok = False
    check("proj-doc-rows-parity", rows_ok, "doc rows diverged")
    check("proj-xdoc-parity",
          proj.xholons_view() == read_xholons(tl, pin0),
          "xdoc view diverged")
    check("proj-version", PROJ_VERSION == 1, f"{PROJ_VERSION}")
    # Warm sync-placement ingest consumes only new commits.
    proj.save(tl)  # checkpoint at the full pin; nothing new yet
    rep_w = ingest_docs(tl, [("sport-warm", run_of("sport", 150, 21000))],
                        emb)
    check("proj-ingest-warm",
          rep_w["catchup"] is not None
          and rep_w["catchup"]["cold"] is False
          and rep_w["catchup"]["commits"] == 0
          and rep_w["catchup"].get("checkpoint_saved") is True,
          f"{rep_w.get('catchup')}")
    org_w = organize_segments(tl)
    check("proj-ingest-warm-organized",
          org_w["organized"] == ["sport-warm"], f"{org_w}")

    # -- warm local: equal append consumes only new commits -----------
    ckpt = proj.checkpoint_path(tl)
    proj.save(tl)
    ckpt_bytes = os.path.getsize(ckpt)
    rep = ingest_docs(tl, [("sport-new",
                            run_of("sport", 150, 20000))], emb)
    check("proj-append-ingest", rep["n_atoms"] == 1, f"{rep}")
    proj2 = Projections.load(tl)
    tl.trace = CallTrace(recent_max=100000)
    cup1 = proj2.update(tl)
    # new commits since the checkpoint: exactly the append's own
    # (1 atom + 1 text... only ACCEPT_ATOMS commits with metas/texts)
    check("proj-warm-incremental",
          cup1["cold"] is False and cup1["commits"] <= 3
          and cup1["artifacts"] <= 6, f"{cup1}")
    tl.trace = CallTrace(recent_max=100000)
    org1 = organize_segments(tl, ["sport-new"], budget=1,
                             projections=proj2)
    evs = tl.trace.calls
    assert len(evs) == tl.trace.n_total
    scans = [e["detail"]["n"] for e in evs
             if e["op"] == "read_commits_all"]
    n_art = sum(1 for e in evs if e["op"] == "read_artifact")
    check("proj-warm-local",
          org1["organized"] == ["sport-new"]
          and all(n <= 3 for n in scans)
          and n_art <= 6, f"scans={scans} artifacts={n_art}")
    check("proj-checkpoint-bytes", ckpt_bytes > 0, f"{ckpt_bytes}")

    # -- persist: close/reopen keeps warm frontier --------------------
    # organize committed hierarchy versions after proj2's update;
    # consume them first so the checkpoint covers the full pin.
    cup1b = proj2.update(tl)
    check("proj-warm-hierarchy-versions",
          cup1b["cold"] is False
          and cup1b["commits"] == org1["n_leaf_ops"]
          + org1["n_parent_ops"] == 2,
          f"{cup1b}")
    proj2.save(tl)
    tl.close()
    tl_r = TLStore(os.path.join(tmp, "store"), create=False,
                   lease_owner="test-m2c-reopen")
    proj_r = Projections.load(tl_r)
    cup_r = proj_r.update(tl_r)
    check("proj-persist",
          cup_r["cold"] is False and cup_r["commits"] == 0
          and set(proj_r.hierarchy_view()["leaves"])
          == set(view0["leaves"]) | set(
              proj2.hierarchy_view()["leaves"]),
          f"{cup_r}")

    # -- corrupt checkpoint -> cold rebuild, same results --------------
    with open(proj.checkpoint_path(tl_r), "w") as f:
        f.write("{corrupt")
    proj_c = Projections.load(tl_r)
    cup_c = proj_c.update(tl_r)
    check("proj-corrupt",
          cup_c["cold"] is True
          and set(proj_c.hierarchy_view()["leaves"])
          == set(proj_r.hierarchy_view()["leaves"]),
          f"{cup_c}")
    tl_r.close()

    # -- navigator parity: same structure as exact --------------------
    def build(use_nav):
        t = tempfile.mkdtemp(prefix="tlsys-m2c-nav-")
        s = TLStore(os.path.join(t, "store"), create=True,
                    lease_owner="test-m2c-nav")
        ingest_docs(s, docs, emb)
        if use_nav:
            o = organize_segments(
                s,
                navigator=CandidateNavigator(kind="partition", k=50),
                parent_navigator=CandidateNavigator(kind="partition",
                                                    k=50))
        else:
            o = organize_segments(s)
        pin = s.pin()
        h = read_seg_hierarchy(s, pin)
        idx = NarrowIndex(s, pin)
        s.close()
        return o, h, idx

    def _sig(idx, aids):
        return sorted((idx.atoms[a]["doc_id"],
                       tuple(idx.atoms[a]["span"])) for a in aids)

    _o_exact, h_exact, idx_exact = build(False)
    o_nav, h_nav, idx_nav = build(True)
    check("nav-parity",
          o_nav["organized"] == _o_exact["organized"]
          and set(h_nav["leaves"]) == set(h_exact["leaves"])
          and set(h_nav["parents"]) == set(h_exact["parents"])
          and all(_sig(idx_nav, h_nav["leaves"][k]["members"])
                  == _sig(idx_exact,
                           h_exact["leaves"][k]["members"])
                  and np.allclose(h_nav["leaves"][k]["descriptor"],
                                  h_exact["leaves"][k]["descriptor"])
                  for k in h_exact["leaves"])
          and all(_sig(idx_nav, h_nav["parents"][k]["members"])
                  == _sig(idx_exact,
                           h_exact["parents"][k]["members"])
                  and sorted(h_nav["parents"][k]["children"])
                  == sorted(h_exact["parents"][k]["children"])
                  for k in h_exact["parents"]),
          f"{o_nav}")
    check("nav-report",
          isinstance(o_nav.get("nav"), list) and len(o_nav["nav"]) >= 1
          and o_nav["nav_totals"]["rounds"] >= 1
          and all(e["leg"] in ("leaf", "parent")
                  for e in o_nav["nav"])
          and all(v >= 0 for v in o_nav["nav_totals"].values()),
          f"{o_nav.get('nav_totals')}")

    # -- bounded guided: capped scoring, kept recall ------------------
    tmp_a = tempfile.mkdtemp(prefix="tlsys-m2c-abl-")
    tl_a = TLStore(os.path.join(tmp_a, "store"), create=True,
                   lease_owner="test-m2c-abl")
    adocs = [(f"a-dist-{i:02d}", run_of("medic", 150, 20000 + 200 * i))
             for i in range(10)]
    adocs += [("m-answer-0", run_of("sport", 150, 30000)),
              ("m-answer-1", run_of("sport", 150, 30200))]
    ingest_docs(tl_a, adocs, emb)
    organize_segments(tl_a, max_leaf_members=2)
    pin_a = tl_a.pin()
    idx_a = NarrowIndex(tl_a, pin_a)
    hq = HierQuery(tl_a, idx_a, emb1)
    ans_aids = set(idx_a.holons["m-answer-0"]["members"]
                   + idx_a.holons["m-answer-1"]["members"])
    grows, grec = hq.guided("sport", top_parents=1, top_children=2,
                            top_atoms=10, parent_budget=4)
    check("nav-bounded",
          grec["work"]["parents_scored"] <= 4
          and grec["nomination"]["mode"] == "bounded-lexical"
          and ans_aids <= {r["aid"] for r in grows},
          f"{grec['work']} {grec.get('nomination')}")
    grows_x, grec_x = hq.guided("sport", top_parents=1, top_children=2,
                                top_atoms=10)
    check("nav-exact-default",
          grec_x.get("nomination", {}).get("mode") == "exact"
          and grec_x["work"]["parents_scored"]
          == len(idx_a.seg_parents),
          f"{grec_x['work']}")
    # determinism of bounded serving
    grows2, grec2 = hq.guided("sport", top_parents=1, top_children=2,
                              top_atoms=10, parent_budget=4)
    check("nav-bounded-deterministic",
          [r["aid"] for r in grows] == [r["aid"] for r in grows2]
          and grec["work"] == grec2["work"], "bounded rerun diverged")

    # -- Narrow opt-in hierarchy leg ----------------------------------
    nq0 = NarrowQuery(tl_a, idx_a, emb1)
    dos0, rec0 = nq0.run("sport")
    check("narrow-hier-default-off",
          "hierarchy" not in rec0["metrics"], f"{rec0['metrics']}")
    nq1 = NarrowQuery(tl_a, idx_a, emb1,
                      cfg={"HIER_GUIDED": True, "HIER_PARENT_BUDGET": 4})
    dos1, rec1 = nq1.run("sport")
    hmet = rec1["metrics"].get("hierarchy", {})
    check("narrow-hier-optin",
          hmet.get("status") == "ok"
          and hmet.get("work", {}).get("parents_scored", 99) <= 4
          and len(hmet.get("rows", [])) >= 1
          and all(len(r["path"]) == 3 for r in hmet["rows"]),
          f"{hmet}")
    check("narrow-hier-rows-stable",
          [(e["atom_id"], e["emitted_score"])
           for e in dos0["entries"]]
          == [(e["atom_id"], e["emitted_score"])
              for e in dos1["entries"]],
          "flag changed Narrow emission")
    tl_a.close()

    # -- debt/catch-up/churn/retained accounting ----------------------
    tmp_d = tempfile.mkdtemp(prefix="tlsys-m2c-debt-")
    tl_d = TLStore(os.path.join(tmp_d, "store"), create=True,
                   lease_owner="test-m2c-debt")
    ingest_docs(tl_d, docs, emb)
    orgd = organize_segments(tl_d, budget=3)
    check("debt-report",
          orgd["debt"]["unorganized_before"] == len(docs)
          and orgd["debt"]["organized"] == 3
          and orgd["debt"]["backpressured"] == len(docs) - 3
          and orgd["catchup"]["cold"] is False
          and orgd["commit_catchup"]["commits"]
          == orgd["n_leaf_ops"] + orgd["n_parent_ops"]
          and orgd["retained"]["docs"] == len(docs)
          and orgd["retained"]["checkpoint_bytes"] > 0
          and orgd["churn"]["minted"] >= 1, f"{orgd}")
    orgd2 = organize_segments(tl_d)
    check("debt-drained",
          orgd2["debt"]["unorganized_before"] == len(docs) - 3
          and orgd2["debt"]["backpressured"] == 0
          and orgd2["remaining"] == [], f"{orgd2}")
    check("debt-commit-catchup",
          orgd2["commit_catchup"] is not None
          and orgd2["commit_catchup"]["cold"] is False,
          f"{orgd2.get('commit_catchup')}")
    # Own-lifecycle checkpoint covers the end pin: the next loader
    # consumes nothing.
    fresh = Projections.load(tl_d)
    cup_next = fresh.update(tl_d)
    check("debt-end-pin",
          cup_next["cold"] is False and cup_next["commits"] == 0,
          f"{cup_next}")
    tl_d.close()

    print("store-root:", tmp)
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
