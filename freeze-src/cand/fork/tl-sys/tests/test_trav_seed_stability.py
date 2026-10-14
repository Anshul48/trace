"""TRAV: traversal-seed stability under admission widening.

r2-shape fixture (Q11.2 shipping blocker): the relational 2-hop
bridge chain seed -> bridge -> target, where bridge/target NEVER
traverse prune/admit (unseedable by descent) and are served ONLY via
dossier lateral traversal.

Lane-TRAV verdict (see lane-TRAV/REPORT.md): the section 5.8
seed-budget hypothesis is REFUTED for r2. Preserved 27-setting
traces show traversal output provably identical at every admission
width (edges/hops/added 2/2/2, 27/27; max_edges=50 never binds),
while the lateral pair is dropped at the 20-entry dossier outer cap
(inner-head-first seating). This battery pins:

  equiv/*  - traversal output identical under widening (refutation).
  seat/*   - repaired outer-cap seating (C2 seating repair): the
             traversal-built lateral block holds reserved seats
             against inner-width pressure; the displaced inner
             tail spills to explicit overflow partials.
  r2shape/xshape/saturate seating asserts - re-adopted verbatim
             from the preserved prior battery (6 checks).
  arm/*    - the section 5.8 experimental arm (common seed budget
             decoupled from admission, relevance-ranked with
             deterministic ties) in BOTH traversal impls, with the
             Lane R differential retained. Default (no budget) is
             bit-identical to the old path. The knob is NOT engaged
             by any caller: retained for the mandated 100M
             re-confirmation, not adopted as r2's repair.

Deterministic fake encoder; scratch store under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_trav_seed_stability.py
"""
import itertools
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys.relations import (SOURCE_ATTRIBUTED, commit_relations,  # noqa: E402
                             get_index, make_record,
                             read_relations)
from tlsys import relquery as _relquery  # noqa: E402
from tlsys.relserve import RelServe  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def raises(name, fn, exc):
    try:
        fn()
    except exc as e:
        print(f"pass {name}")
        return str(e)
    except Exception as e:  # noqa: BLE001 - must record, never raise
        FAILS.append(name)
        print(f"FAIL {name} :: wrong exc {type(e).__name__}: {e}")
        return ""
    FAILS.append(name)
    print(f"FAIL {name} :: no exception")
    return ""


def vec(text):
    return [1.0, 0.0, 0.0, 0.0]


def emb(texts):
    return [vec(t) for t in texts]


emb1 = lambda q: vec(q)  # noqa: E731

Q = "cats purr when content"
# Seed: short, all query terms (top BM25). Fillers: share one query
# term + a filler-only word ("lounge"), diluted by padding (lower
# BM25 than the seed, still tau-clearing). Bridge/target: zero
# query terms -- descent can never admit them (the r2 shape).
DOCS = [("d-seed", "cats purr content")]
for i in range(8):
    DOCS.append((f"d-f{i}", "cats lounge " + "padding " * (20 + i)))
DOCS.append(("d-bridge", "quantum photon spin entanglement lattice"))
DOCS.append(("d-target", "neutrino oscillation flavor mixing angle"))

PURE_LEX = {"EMIT_DENSE_ATOMS": False, "REGION_DENSE_ATOMS": False}

root = tempfile.mkdtemp(prefix="tl-trav-")
tl = TLStore(os.path.join(root, "store"), create=True,
             lease_owner="test-trav")
try:
    rep = ingest_docs(tl, DOCS, emb)
    check("fixture/atoms", rep["n_atoms"] == 11, rep)
    pinned = tl.pin()
    idx = NarrowIndex(tl, pinned)
    aids = {a["doc_id"]: aid for aid, a in idx.atoms.items()}
    check("fixture/docs", len(aids) == 11, sorted(aids))
    SEED, BRIDGE, TARGET = (aids["d-seed"], aids["d-bridge"],
                            aids["d-target"])
    FILL = [aids[f"d-f{i}"] for i in range(8)]

    CFG = {"extractor": "test-cooccur-v1", "window": 2,
           "model": "none", "rules": ["bridge-link"]}
    ra = make_record(
        "relates", [("source", SEED), ("target", BRIDGE)],
        {"negated": False}, CFG, SOURCE_ATTRIBUTED, [SEED, BRIDGE])
    rb = make_record(
        "relates", [("source", BRIDGE), ("target", TARGET)],
        {"negated": False}, CFG, SOURCE_ATTRIBUTED,
        [BRIDGE, TARGET])
    commit_relations(tl, [ra, rb])
    pinned = tl.pin()
    idx = NarrowIndex(tl, pinned)
    check("fixture/relations",
          len(read_relations(tl, pinned)) == 2)

    REL = {"DOSSIER_SHAPE": "relational",
           "DOSSIER_REL_TRAVERSAL": True,
           "DOSSIER_REL_HOPS": 2,
           "DOSSIER_MAX_ENTRIES": 4}

    def narrow_a(a):
        nq = NarrowQuery(tl, idx, emb1,
                         cfg=dict(PURE_LEX, MAX_ENTRIES=a))
        return nq.run(Q)

    def rel_a(a):
        dq = DossierQuery(tl, idx, emb1,
                          cfg=dict(REL, NARROW=dict(
                              PURE_LEX, MAX_ENTRIES=a)))
        return dq.run(Q)

    # -- anchor shape: narrow admits seed + fillers only --------
    dos_n2, _ = narrow_a(2)
    dos_n8, _ = narrow_a(8)
    n2 = [e["atom_id"] for e in dos_n2["entries"]]
    n8 = [e["atom_id"] for e in dos_n8["entries"]]
    check("shape/narrow-admits-2",
          len(n2) == 2 and SEED in n2, n2)
    check("shape/narrow-admits-8-prefix-stable",
          len(n8) == 8 and n8[:2] == n2
          and BRIDGE not in n8 and TARGET not in n8, n8)
    check("shape/owning-never-admitted",
          BRIDGE not in n8 and TARGET not in n8)

    # -- equiv: traversal output identical under widening --------
    # (the refutation core: 2/50 edges at every width on the live
    # path, exactly as in the preserved 27-setting traces).
    dos_r2, rec_r2 = rel_a(2)
    dos_r8, rec_r8 = rel_a(8)
    d2, d8 = (rec_r2["metrics"]["dossier"],
              rec_r8["metrics"]["dossier"])
    check("equiv/edges-identical",
          d2["lateral_edges_examined"]
          == d8["lateral_edges_examined"] == 2, (d2, d8))
    check("equiv/added-identical",
          d2["lateral_added"] == d8["lateral_added"] == 2,
          (d2, d8))
    check("equiv/hops-identical",
          rec_r2["metrics"]["H_hops"]
          == rec_r8["metrics"]["H_hops"] == 2)
    lat2 = [e["atom_id"] for e in dos_r2["entries"]
            if e["marks"].get("lateral")]
    check("equiv/narrow-serves-chain",
          lat2 == [BRIDGE, TARGET]
          and len(dos_r2["entries"]) == 4, lat2)
    got8 = [e["atom_id"] for e in dos_r8["entries"]]

    # -- seat: repaired outer-cap seating (was defect/*) -------
    # The traversal builds the pair pre-cap at width 8
    # (lateral_added == 2, same as width 2); the seating repair
    # reserves the lateral block seats and displaces the inner
    # tail to explicit overflow partials.
    check("seat/lateral-built-precap-wide",
          d8["lateral_added"] == 2, d8)
    check("seat/wide-seats-pair",
          got8 == n8[:2] + [BRIDGE, TARGET], got8)
    check("seat/cap-respected", len(got8) == 4, got8)
    over8 = [p for p in rec_r8["partials"]
             if p["cause"] == "dossier-cap-overflow"]
    check("seat/overflow-names-displaced-inner",
          {p["scope"] for p in over8}
          == {f"candidate:{a[:16]}" for a in n8[2:]},
          [p["scope"] for p in over8])
    check("seat/counts-consistent",
          sum(rec_r8["metrics"]["support_counts"].values())
          == len(got8))

    # -- re-adopted seating checks (verbatim from the preserved
    # prior battery; SEAT failing-first: RED pre-repair) --------
    check("r2shape/wide-serves-target",
          TARGET in got8 and BRIDGE in got8, got8)
    check("r2shape/wide-inner-head-preserved",
          got8[:2] == n8[:2]
          and got8[2:] == [BRIDGE, TARGET], got8)
    check("r2shape/overflow-disclosed",
          len(over8) == 6
          and {p["scope"] for p in over8}
          == {f"candidate:{a[:16]}" for a in n8[2:]},
          [p["scope"] for p in over8])

    # -- no-lateral runs: head-kept rule byte-preserved ---------
    dq_off = DossierQuery(tl, idx, emb1,
                          cfg=dict(REL, DOSSIER_LATERAL=False,
                                   NARROW=dict(PURE_LEX,
                                               MAX_ENTRIES=8)))
    dos_off, rec_off = dq_off.run(Q)
    got_off = [e["atom_id"] for e in dos_off["entries"]]
    check("noop/opt-out-head-kept",
          got_off == n8[:4], got_off)
    dq_edge = DossierQuery(tl, idx, emb1,
                           cfg=dict(REL, NARROW=dict(
                               PURE_LEX, MAX_ENTRIES=8)))
    dos_e, _rec_e = dq_edge.run("lounge")
    got_e = [e["atom_id"] for e in dos_e["entries"]]
    dos_nl, _ = NarrowQuery(
        tl, idx, emb1,
        cfg=dict(PURE_LEX, MAX_ENTRIES=8)).run("lounge")
    want_e = [e["atom_id"] for e in dos_nl["entries"][:4]]
    check("noop/edgeless-seeds-head-kept",
          SEED not in got_e and BRIDGE not in got_e
          and TARGET not in got_e
          and got_e == want_e, got_e)

    # -- cross-topic 1-hop leg: same seat protection ---------
    XT = {"DOSSIER_SHAPE": "cross-topic",
          "DOSSIER_MAX_ENTRIES": 3,
          "NARROW": dict(PURE_LEX, MAX_ENTRIES=8)}
    dq_x = DossierQuery(tl, idx, emb1, cfg=dict(XT))
    dos_x, rec_x = dq_x.run(Q, topics=[Q])
    got_x = [e["atom_id"] for e in dos_x["entries"]]
    dx = rec_x["metrics"]["dossier"]
    check("seat/xshape-lateral-built-precap",
          dx["lateral_added"] == 1, dx)
    check("seat/xshape-seats-lateral",
          got_x == n8[:2] + [BRIDGE], got_x)
    check("xshape/wide-serves-lateral",
          BRIDGE in got_x and len(got_x) == 3, got_x)
    check("xshape/inner-head-preserved",
          got_x[:2] == n8[:2] and got_x[2] == BRIDGE, got_x)

    # -- saturation cap: lateral block binds at cap 1 ---------
    dq_s1 = DossierQuery(tl, idx, emb1,
                         cfg=dict(REL, DOSSIER_MAX_ENTRIES=1,
                                  NARROW=dict(PURE_LEX,
                                              MAX_ENTRIES=2)))
    dos_s1, rec_s1 = dq_s1.run(Q)
    got_s1 = [e["atom_id"] for e in dos_s1["entries"]]
    check("seat/saturate-lateral-binds",
          got_s1 == [BRIDGE], got_s1)
    over_s1 = [p for p in rec_s1["partials"]
               if p["cause"] == "dossier-cap-overflow"]
    check("seat/saturate-overflow-count",
          len(over_s1) == 3, [p["scope"] for p in over_s1])
    check("saturate/cap-binds",
          got_s1 == [BRIDGE], got_s1)

    # -- arm: select_seeds pure-unit semantics -------------------
    sel = _relquery.select_seeds
    check("arm/select-rank",
          sel(["a", "b", "c"], {"a": 1.0, "b": 3.0, "c": 2.0},
              2) == ["b", "c"])
    tie = sel(["c", "a", "b"],
              {"a": 5, "b": 5, "c": 5}, 3)
    check("arm/select-ties-aid-asc", tie == ["a", "b", "c"], tie)
    perms = {tuple(sel(list(p), {"a": 5, "b": 5, "c": 1}, 2))
             for p in itertools.permutations(["a", "b", "c"])}
    check("arm/select-permutation-invariant",
          perms == {("a", "b")}, perms)
    raises("arm/select-unscored-fails-closed",
           lambda: sel(["a", "b"], {"a": 1.0}, 2), ValueError)
    raises("arm/select-bad-budget",
           lambda: sel(["a"], {"a": 1.0}, -1), ValueError)
    raises("arm/select-nan-fails-closed",
           lambda: sel(["a"], {"a": float("nan")}, 1),
           ValueError)
    raises("arm/select-inf-fails-closed",
           lambda: sel(["a"], {"a": float("inf")}, 1),
           ValueError)
    check("arm/select-zero", sel(["a"], {"a": 1.0}, 0) == [])
    check("arm/select-none-identity",
          sel(["b", "a", "b"]) == ["b", "a", "b"])
    check("arm/select-no-scores-keeps-order",
          sel(["b", "a", "b", "c"], None, 2) == ["b", "a"])

    # -- arm: traverse kwargs on BOTH impls (Lane R parity) ------
    serve = RelServe.open(tl, idx, pinned)
    ridx = get_index(tl, pinned)
    live = set(idx.atoms)
    vis = set(ridx.records)
    SEEDS = [SEED] + FILL
    SCORES = {SEED: 100.0}
    for i, f in enumerate(FILL):
        SCORES[f] = 8.0 - i

    def run_both(seeds, scores, budget, hops=2, edges=50):
        ch_r, ch_s = [], []
        tr = _relquery.traverse(
            ridx, seeds, live, max_hops=hops, max_edges=edges,
            charge=lambda n, o: ch_r.append((n, o)),
            visible=vis, seed_scores=scores,
            seed_budget=budget)
        ts = serve.traverse(
            seeds, max_hops=hops, max_edges=edges,
            charge=lambda n, o: ch_s.append((n, o)),
            visible=set(serve.visible), seed_scores=scores,
            seed_budget=budget)
        return tr, ts, ch_r, ch_s

    tr, ts, ch_r, ch_s = run_both(SEEDS, SCORES, 1)
    check("arm/parity-budgeted-reached",
          tr["reached"] == ts["reached"]
          and sorted(tr["reached"]) == sorted([BRIDGE, TARGET]),
          (tr["reached"], ts["reached"]))
    check("arm/parity-budgeted-counts",
          (tr["examined"], tr["ineligible"], tr["hops_used"])
          == (ts["examined"], ts["ineligible"], ts["hops_used"])
          == (2, 0, 2), (tr, ts))
    check("arm/parity-budgeted-charges",
          ch_r == ch_s
          == [(1, "lateral-edge-inspection")] * 2, (ch_r, ch_s))
    check("arm/parity-budgeted-hop-provenance",
          all(tr["reached"][a]["hop"]
              == ts["reached"][a]["hop"] == h
              and tr["reached"][a]["via"]
              == ts["reached"][a]["via"]
              and tr["reached"][a]["rel_status"]
              == ts["reached"][a]["rel_status"]
              for a, h in ((BRIDGE, 1), (TARGET, 2))),
          (tr["reached"], ts["reached"]))
    # kwargs path == preselected core path (no core change).
    pre = _relquery.traverse(
        ridx, [SEED], live, max_hops=2, max_edges=50,
        visible=vis)
    check("arm/kwargs-equiv-preslice",
          {k: tr[k] for k in ("reached", "examined",
                              "ineligible", "hops_used")}
          == {k: pre[k] for k in ("reached", "examined",
                                  "ineligible", "hops_used")},
          (tr, pre))
    # Default path bit-identical to the old behavior.
    t_plain = _relquery.traverse(ridx, SEEDS, live, max_hops=2,
                                 max_edges=50, visible=vis)
    t_none = _relquery.traverse(
        ridx, SEEDS, live, max_hops=2, max_edges=50,
        visible=vis, seed_scores=None, seed_budget=None)
    check("arm/default-unchanged-relquery", t_plain == t_none,
          (t_plain, t_none))
    s_plain = serve.traverse(SEEDS, max_hops=2, max_edges=50,
                             visible=set(serve.visible))
    s_none = serve.traverse(
        SEEDS, max_hops=2, max_edges=50,
        visible=set(serve.visible), seed_scores=None,
        seed_budget=None)
    check("arm/default-unchanged-relserve", s_plain == s_none)
    check("arm/default-parity", t_plain == s_plain,
          (t_plain, s_plain))
    # Seed ORDER is a proven no-op (both impls sort seeds): only
    # the budgeted SET has teeth.
    outs = set()
    for p in (SEEDS, SEEDS[::-1], FILL[:4] + [SEED] + FILL[4:]):
        o = _relquery.traverse(ridx, p, live, max_hops=2,
                               max_edges=50, visible=vis)
        outs.add((str(sorted((k, v["hop"],
                              tuple(v["via"]))
                             for k, v in o["reached"].items())),
                  o["examined"], o["ineligible"], o["hops_used"]))
    check("arm/order-noop-relquery", len(outs) == 1, outs)
    outs_s = set()
    for p in (SEEDS, SEEDS[::-1], FILL[:4] + [SEED] + FILL[4:]):
        o = serve.traverse(p, max_hops=2, max_edges=50,
                           visible=set(serve.visible))
        outs_s.add((str(sorted((k, v["hop"],
                                tuple(v["via"]))
                               for k, v in o["reached"].items())),
                    o["examined"], o["ineligible"],
                    o["hops_used"]))
    check("arm/order-noop-relserve", len(outs_s) == 1, outs_s)
    # r2-shape + budget: extras contribute nothing (mirrors the
    # 2/50 preserved-trace finding); budget keeps the useful seed.
    tb1, _, _, _ = run_both(SEEDS, SCORES, 1)
    check("arm/r2shape-budget-keeps-chain",
          sorted(tb1["reached"]) == sorted([BRIDGE, TARGET])
          and tb1["examined"] == 2, tb1)
    tb0, _, _, _ = run_both(SEEDS, SCORES, 0)
    check("arm/r2shape-budget-zero-empty",
          tb0["reached"] == {} and tb0["examined"] == 0
          and tb0["hops_used"] == 0, tb0)

    # -- arm: saturation protection (mechanism in principle) -----
    # Junk edges on every filler + a tight edge cap: unbudgeted
    # traversal starves the useful seed; a top-1 relevance budget
    # protects it. Deterministic for ANY aid/rid assignment: the
    # useful seed is the last-sorted filler, so the cap binds
    # before its edges under atom-id order only.
    junk_docs = [(f"d-j{i}",
                  f"zxqy-{i} wugnab quuxor plimble")
                 for i in range(8)]
    ingest_docs(tl, junk_docs, emb)
    pinned2 = tl.pin()
    idx2 = NarrowIndex(tl, pinned2)
    aids2 = {a["doc_id"]: aid
             for aid, a in idx2.atoms.items()}
    JUNK = [aids2[f"d-j{i}"] for i in range(8)]
    USEFUL = sorted(FILL)[-1]
    jrecs = [make_record(
        "relates", [("source", FILL[i]), ("target", JUNK[i])],
        {"negated": False}, CFG, SOURCE_ATTRIBUTED,
        [FILL[i], JUNK[i]]) for i in range(8)]
    jrecs.append(make_record(
        "relates", [("source", USEFUL), ("target", TARGET)],
        {"negated": False}, CFG, SOURCE_ATTRIBUTED,
        [USEFUL, TARGET]))
    commit_relations(tl, jrecs)
    pinned2 = tl.pin()
    idx2 = NarrowIndex(tl, pinned2)
    serve2 = RelServe.open(tl, idx2, pinned2)
    ridx2 = get_index(tl, pinned2)
    live2 = set(idx2.atoms)
    vis2 = set(ridx2.records)
    SAT_SCORES = {f: (100.0 if f == USEFUL else 8.0 - i)
                  for i, f in enumerate(FILL)}
    cap = len(FILL) - 1  # all junk edges but USEFUL's, then stop
    u_r = _relquery.traverse(ridx2, FILL, live2, max_hops=1,
                             max_edges=cap, visible=vis2)
    u_s = serve2.traverse(FILL, max_hops=1, max_edges=cap,
                          visible=set(serve2.visible))
    check("arm/saturate-unbudgeted-starved",
          TARGET not in u_r["reached"]
          and TARGET not in u_s["reached"]
          and u_r["examined"] == u_s["examined"] == cap
          and u_r["reached"] == u_s["reached"], (u_r, u_s))
    b_r = _relquery.traverse(
        ridx2, FILL, live2, max_hops=1, max_edges=cap,
        visible=vis2, seed_scores=SAT_SCORES, seed_budget=1)
    b_s = serve2.traverse(
        FILL, max_hops=1, max_edges=cap,
        visible=set(serve2.visible), seed_scores=SAT_SCORES,
        seed_budget=1)
    check("arm/saturate-budget-protects",
          TARGET in b_r["reached"] and TARGET in b_s["reached"]
          and b_r["reached"] == b_s["reached"]
          and b_r["examined"] == b_s["examined"] == 2,
          (b_r, b_s))
finally:
    tl.close()

print(f"done: {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
