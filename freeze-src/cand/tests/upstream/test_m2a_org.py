"""M2-A organization: segment leaves + parent holons + bounded hierarchy access.

Covers the G2 implementation dependency (O3 / COORDINATOR-DISPATCH item 1):
segment-level cross-source leaves replace whole-document-centroid grouping
as the organization substrate; meaningful parent->child holons replace
holon->atom-only expansion at serving time via bounded HierQuery access.

Checks (deterministic fake encoder, scratch store under /tmp):
  seg-units ......... segment_atoms / decide_leaf / decide_parent pure units
  seg-multitopic .... long multi-topic doc -> >=2 topic-coherent segments
  seg-cross-source .. same-topic segments from distinct docs share one leaf
  seg-overlap ....... one segment joins <= MAX_SEG_MEMBERSHIPS leaves
  seg-overflow ...... full leaf -> local sibling + same-parent attach
  seg-no-fit ........ far outlier -> singleton leaf, never forced
  seg-append ........ newly appended doc joins existing leaf (new version)
  seg-correction .... corrected revision republishes affected path only
  seg-persist ....... hierarchy survives close/reopen; provenance stable
  seg-ten-op ........ every organize commit_batch call carries <= 10 ops
  seg-idempotent .... re-organize is commit-free (pin unchanged)
  seg-determinism ... two identical builds -> identical leaf/parent structure
  hier-guided ....... guided parent->child->atom evidence with receipt paths
  hier-ablation ..... guided recall > matched-work flat recall (equal work)
  hier-flat-floor ... exhaustive flat needs strictly more work for same recall
  hier-cycle ........ cyclic parent refs terminate with bounded visits
  hier-no-store ..... empty hierarchy -> honest no-hierarchy status
  narrow-defaults ... default Narrow receipts carry no hierarchy keys

Run: tl-sys/.venv/bin/python tl-sys/tests/test_m2a_org.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

import numpy as np

from tlsys.store_if import TLStore
from tlsys.ingest import ingest_docs
from tlsys.index import NarrowIndex
from tlsys.query import HierQuery, NarrowQuery
from tlsys.place import (
    MAX_LEAF_MEMBERS, MAX_SEG_MEMBERSHIPS, PARENT_PREFIX, SEG_PREFIX,
    T_LEAF, decide_leaf, decide_parent, parent_op, read_seg_hierarchy,
    segment_atoms,
)
from tlsys.maint import organize_segments

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
V_SPORT2 = pad([0.97, 0.05, 0.0, 0.0])  # cos ~0.999 with V_SPORT: joins
V_MED = pad([0.0, 1.0, 0.0, 0.0])
V_TECH = pad([0.0, 0.0, 1.0, 0.0])
V_OUT = pad([0.0, 0.0, 0.0, 1.0])  # far from every topic: no-fit
V_MID = pad([0.70710678, 0.70710678, 0.0, 0.0])  # sport/med overlap


def emb(texts):
    out = []
    for t in texts:
        n_sport = t.count("sport")
        n_med = t.count("medic")
        n_tech = t.count("techn")
        n_out = t.count("outlier")
        if "bothmark" in t:
            out.append(list(V_MID))
        else:
            votes = [(n_sport, V_SPORT), (n_med, V_MED),
                     (n_tech, V_TECH), (n_out, V_OUT)]
            votes.sort(key=lambda kv: -kv[0])
            out.append(list(votes[0][1]))
    return out


def emb1(q):
    return emb([q])[0]


def run_of(word, n, start=0):
    return " ".join(f"{word}{i}" for i in range(start, start + n))


def cos(u, v):
    u = np.asarray(u, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    return float(u @ v / ((float(np.linalg.norm(u)) or 1.0)
                            * (float(np.linalg.norm(v)) or 1.0)))


def main():
    # -- pure units (no store) -----------------------------------------
    segs = segment_atoms(["a0", "a1", "a2", "a3"],
                         [V_SPORT, V_SPORT2, V_MED, V_MED])
    check("seg-units/split",
          [sorted(s) for s in segs] == [[0, 1], [2, 3]], repr(segs))
    check("seg-units/single",
          segment_atoms(["a0"], [V_SPORT]) == [[0]])
    check("seg-units/empty", segment_atoms([], []) == [])
    leaves = {"xseg-t0": {"members": ["m0"], "descriptor": V_SPORT,
                          "seq": 1}}
    check("seg-units/decide-join",
          decide_leaf(V_SPORT2, leaves) == ["xseg-t0"])
    check("seg-units/decide-miss", decide_leaf(V_OUT, leaves) == [])
    full = {"xseg-f": {"members": [f"m{i}" for i in range(25)],
                       "descriptor": V_SPORT, "seq": 1}}
    st = {}
    check("seg-units/decide-full",
          decide_leaf(V_SPORT2, full, stats=st) == []
          and st.get("full_skipped") == 1
          and st.get("full_qualifying") == ["xseg-f"], repr(st))
    many = {f"xseg-{i}": {"members": ["m"], "descriptor": V_SPORT,
                          "seq": i} for i in range(5)}
    check("seg-units/decide-cap",
          len(decide_leaf(V_SPORT2, many)) == MAX_SEG_MEMBERSHIPS)
    check("seg-units/parent-join",
          decide_parent(V_SPORT2, {"xpar-p": {"children": ["c"],
                                             "descriptor": V_SPORT,
                                             "seq": 1}}) == ["xpar-p"])
    check("seg-units/parent-miss",
          decide_parent(V_OUT, {"xpar-p": {"children": ["c"],
                                          "descriptor": V_SPORT,
                                          "seq": 1}}) == [])

    # -- main store: multitopic + cross-source + overlap + no-fit ------
    tmp = tempfile.mkdtemp(prefix="tlsys-m2a-")
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner="test-m2a-org")
    doc_multi = " ".join([run_of("sport", 150, 0), run_of("medic", 150, 0),
                          run_of("sport", 150, 1000),
                          run_of("medic", 150, 1000)])
    docs = [("doc-multi", doc_multi),
            ("doc-sport-b", run_of("sport", 150, 5000)),
            ("doc-med-b", run_of("medic", 150, 6000)),
            ("doc-both", run_of("bothmark", 150, 7000)),
            ("doc-out", run_of("outlier", 150, 8000))]
    rep = ingest_docs(tl, docs, emb)
    check("seg-ingest-counts",
          rep["n_atoms"] == 8 and rep["n_holons"] == 5, f"{rep}")
    pin0 = tl.pin()
    idx0 = NarrowIndex(tl, pin0)
    # provenance containers before organize (byte-stability baseline)
    prov0 = {d: (list(idx0.holons[d]["members"]),
                 [float(x) for x in idx0.holons[d]["descriptor"]],
                 idx0.holons[d]["seq"], idx0.holons[d]["op_id"])
             for d, _t in docs}
    # ten-op durability: wrap commit_batch during organize
    batch_sizes = []
    _orig_commit = tl.commit_batch

    def _rec(ops):
        batch_sizes.append(len(ops))
        return _orig_commit(ops)

    tl.commit_batch = _rec
    org = organize_segments(tl)
    tl.commit_batch = _orig_commit
    check("seg-organized",
          sorted(org["organized"]) == sorted(d for d, _t in docs)
          and not org["failed"], f"{org}")
    check("seg-ten-op",
          batch_sizes and max(batch_sizes) <= 10, repr(batch_sizes))
    check("seg-report-work",
          org["n_leaf_ops"] >= 3 and org["n_parent_ops"] >= 2
          and org["n_commits"] >= 1
          and org["max_batch_ops"] == max(batch_sizes), f"{org}")
    pin1 = tl.pin()
    idx1 = NarrowIndex(tl, pin1)
    check("seg-provenance-stable",
          all(d in idx1.holons and
              (list(idx1.holons[d]["members"]),
               [float(x) for x in idx1.holons[d]["descriptor"]],
               idx1.holons[d]["seq"], idx1.holons[d]["op_id"]) == prov0[d]
              for d, _t in docs),
          "per-doc holons must be byte-stable across organize")
    hier = read_seg_hierarchy(tl, pin1)
    leaves, parents = hier["leaves"], hier["parents"]
    check("seg-namespaces",
          all(k.startswith(SEG_PREFIX) for k in leaves)
          and all(k.startswith(PARENT_PREFIX) for k in parents)
          and len(leaves) >= 3 and len(parents) >= 2,
          f"leaves={sorted(leaves)} parents={sorted(parents)}")
    # multitopic: doc-multi atoms land in >= 2 topic-coherent segments
    multi_aids = set(idx1.holons["doc-multi"]["members"])
    multi_leaves = [lid for lid, lf in leaves.items()
                    if multi_aids & set(lf["members"])]
    check("seg-multitopic", len(multi_leaves) >= 2, repr(multi_leaves))
    # leaf coherence: every member atom scores >= 0.5 on its leaf
    avec = {a: np.asarray(idx1.atoms[a]["descriptor"], dtype=np.float64)
            for a in idx1.atoms}
    coh = all(cos(avec[a], lf["descriptor"]) >= 0.5
              for lf in leaves.values() for a in lf["members"])
    check("seg-coherent", coh, "leaf member below 0.5 coherence")
    # cross-source: one leaf holds sport atoms from >= 2 docs
    sport_docs = {"doc-multi", "doc-sport-b"}
    xsrc = [lid for lid, lf in leaves.items()
            if len({idx1.atoms[a]["doc_id"] for a in lf["members"]}
                   & sport_docs) >= 2]
    check("seg-cross-source", len(xsrc) >= 1, repr(xsrc))
    # overlap: the bothmark atom sits in exactly MAX_SEG_MEMBERSHIPS leaves
    both_aid = idx1.holons["doc-both"]["members"][0]
    both_in = [lid for lid, lf in leaves.items()
               if both_aid in lf["members"]]
    check("seg-overlap", len(both_in) == MAX_SEG_MEMBERSHIPS,
          repr(both_in))
    # no-fit: the outlier atom is a singleton leaf, never forced
    out_aid = idx1.holons["doc-out"]["members"][0]
    out_in = [lid for lid, lf in leaves.items()
              if out_aid in lf["members"]]
    check("seg-no-fit",
          len(out_in) == 1 and leaves[out_in[0]]["members"] == [out_aid],
          repr(out_in))
    # parents: meaningful child refs + member union + centroid descriptor
    par_ok = True
    for pid, par in parents.items():
        if not par["children"]:
            par_ok = False
        union = [a for c in par["children"] for a in
                 leaves.get(c, {}).get("members", [])]
        if sorted(par["members"]) != sorted(set(union)):
            par_ok = False
        if union and not np.allclose(
                par["descriptor"],
                np.stack([avec[a] for a in union]).mean(axis=0)):
            par_ok = False
    check("seg-parents", par_ok and len(parents) >= 2,
          f"{ {p: v['children'] for p, v in parents.items()} }")
    # idempotent re-organize: commit-free, pin unchanged
    org2 = organize_segments(tl)
    check("seg-idempotent",
          org2["organized"] == [] and org2["n_commits"] == 0
          and tl.pin()[3] == pin1[3], f"{org2}")
    # append: a new sport doc joins the existing sport leaf (new version)
    sport_leaf = xsrc[0]
    n_before = len(leaves[sport_leaf]["members"])
    rep3 = ingest_docs(tl, [("doc-sport-c", run_of("sport", 150, 9000))],
                       emb)
    check("seg-append-ingest", rep3["n_atoms"] == 1, f"{rep3}")
    org3 = organize_segments(tl)
    check("seg-append-organized", org3["organized"] == ["doc-sport-c"],
          f"{org3}")
    pin3 = tl.pin()
    hier3 = read_seg_hierarchy(tl, pin3)
    check("seg-append-join",
          len(hier3["leaves"][sport_leaf]["members"]) == n_before + 1,
          f"{sport_leaf}: {n_before} -> "
          f"{len(hier3['leaves'][sport_leaf]['members'])}")
    # correction: revised bytes under a new doc_id republish locally
    seqs_before = {k: v["seq"] for k, v in hier3["leaves"].items()}
    pseqs_before = {k: v["seq"] for k, v in hier3["parents"].items()}
    rep4 = ingest_docs(
        tl, [("doc-sport-b-v2", run_of("sport", 150, 9500) + " fixed")],
        emb)
    check("seg-correction-ingest", rep4["n_atoms"] == 1, f"{rep4}")
    org4 = organize_segments(tl)
    check("seg-correction-organized",
          org4["organized"] == ["doc-sport-b-v2"], f"{org4}")
    pin4 = tl.pin()
    hier4 = read_seg_hierarchy(tl, pin4)
    changed_leaves = sorted(
        k for k, v in hier4["leaves"].items()
        if seqs_before.get(k) != v["seq"])
    changed_parents = sorted(
        k for k, v in hier4["parents"].items()
        if pseqs_before.get(k) != v["seq"])
    check("seg-correction-local",
          changed_leaves == [sport_leaf] and len(changed_parents) == 1,
          f"leaves={changed_leaves} parents={changed_parents}")
    # persistence: close/reopen keeps hierarchy + provenance
    tl.close()
    tl_r = TLStore(os.path.join(tmp, "store"), create=False,
                   lease_owner="test-m2a-reopen")
    pin_r = tl_r.pin()
    check("seg-persist-pin", pin_r[3] == pin4[3], f"{pin_r[3]}")
    idx_r = NarrowIndex(tl_r, pin_r)
    hier_r = read_seg_hierarchy(tl_r, pin_r)
    check("seg-persist-hierarchy",
          set(hier_r["leaves"]) == set(hier4["leaves"])
          and set(hier_r["parents"]) == set(hier4["parents"])
          and all(hier_r["leaves"][k]["members"]
                  == hier4["leaves"][k]["members"]
                  for k in hier4["leaves"]), "hierarchy lost on reopen")
    check("seg-persist-provenance",
          all(d in idx_r.holons and
              (list(idx_r.holons[d]["members"]), idx_r.holons[d]["seq"],
               idx_r.holons[d]["op_id"]) ==
              (prov0[d][0], prov0[d][2], prov0[d][3])
              for d, _t in docs), "per-doc holons changed on reopen")

    # -- determinism: identical rebuild -> identical structure ---------
    tmp_b = tempfile.mkdtemp(prefix="tlsys-m2a-det-")
    tl_b = TLStore(os.path.join(tmp_b, "store"), create=True,
                   lease_owner="test-m2a-det")
    ingest_docs(tl_b, docs, emb)
    organize_segments(tl_b)
    pin_bb = tl_b.pin()
    hier_b = read_seg_hierarchy(tl_b, pin_bb)
    idx_b = NarrowIndex(tl_b, pin_bb)

    def _sig(idx, aids):
        return sorted((idx.atoms[a]["doc_id"],
                       tuple(idx.atoms[a]["span"])) for a in aids)

    check("seg-determinism",
          set(hier_b["leaves"]) == set(leaves)
          and set(hier_b["parents"]) == set(parents)
          and all(_sig(idx_b, hier_b["leaves"][k]["members"])
                  == _sig(idx1, leaves[k]["members"]) for k in leaves)
          and all(sorted(hier_b["parents"][k]["children"])
                  == sorted(parents[k]["children"]) for k in parents)
          and all(np.allclose(hier_b["leaves"][k]["descriptor"],
                              leaves[k]["descriptor"]) for k in leaves),
          "rebuild diverged")
    tl_b.close()

    # -- overflow store: capacity forces a local sibling ---------------
    tmp_o = tempfile.mkdtemp(prefix="tlsys-m2a-ovf-")
    tl_o = TLStore(os.path.join(tmp_o, "store"), create=True,
                   lease_owner="test-m2a-ovf")
    odocs = [(f"doc-s{i}", run_of("sport", 150, 10000 + 200 * i))
             for i in range(5)]
    ingest_docs(tl_o, odocs, emb)
    orgo = organize_segments(tl_o, max_leaf_members=3)
    check("seg-overflow-organized",
          sorted(orgo["organized"]) == sorted(d for d, _t in odocs),
          f"{orgo}")
    hier_o = read_seg_hierarchy(tl_o, tl_o.pin())
    lo = hier_o["leaves"]
    sib = [k for k in lo if "-ov" in k]
    check("seg-overflow-sibling",
          len(lo) == 2 and len(sib) == 1
          and all(len(v["members"]) <= 3 for v in lo.values())
          and sorted(sum([v["members"] for v in lo.values()], []))
          == sorted(a for d, _t in odocs for a in
                    NarrowIndex(tl_o, tl_o.pin()).holons[d]["members"]),
          f"{ {k: len(v['members']) for k, v in lo.items()} }")
    base = [k for k in lo if "-ov" not in k][0]
    opars = [p for p, v in hier_o["parents"].items()
             if base in v["children"]]
    check("seg-overflow-same-parent",
          len(opars) == 1 and sib[0] in hier_o["parents"][opars[0]][
              "children"],
          f"{ {p: v['children'] for p, v in hier_o['parents'].items()} }")
    tl_o.close()

    # -- ablation store: many sharded distractors + late answer -------
    tmp_a = tempfile.mkdtemp(prefix="tlsys-m2a-abl-")
    tl_a = TLStore(os.path.join(tmp_a, "store"), create=True,
                   lease_owner="test-m2a-abl")
    adocs = [(f"a-dist-{i:02d}", run_of("medic", 150, 20000 + 200 * i))
             for i in range(10)]
    adocs += [("m-answer-0", run_of("sport", 150, 30000)),
              ("m-answer-1", run_of("sport", 150, 30200))]
    ingest_docs(tl_a, adocs, emb)
    organize_segments(tl_a, max_leaf_members=2)
    pin_a = tl_a.pin()
    idx_a = NarrowIndex(tl_a, pin_a)
    hier_a = read_seg_hierarchy(tl_a, pin_a)
    la = hier_a["leaves"]
    ans_aids = set(idx_a.holons["m-answer-0"]["members"]
                   + idx_a.holons["m-answer-1"]["members"])
    ans_leaves = sorted(lid for lid, lf in la.items()
                        if ans_aids & set(lf["members"]))
    check("seg-ablation-setup",
          len(ans_leaves) == 1 and len(la) >= 6
          and all(aid not in lf["members"] for aid in ans_aids
                  for lid, lf in la.items() if lid != ans_leaves[0]),
          f"leaves={sorted(la)} ans={ans_leaves}")
    hq = HierQuery(tl_a, idx_a, emb1)
    grows, grec = hq.guided("sport", top_parents=1, top_children=2,
                            top_atoms=10)
    gwork = grec["work"]
    gtotal = (gwork["parents_scored"] + gwork["children_scored"]
              + gwork["atoms_scored"])
    got = {r["aid"] for r in grows}
    check("hier-guided-recall", ans_aids <= got,
          f"got={sorted(got)} want={sorted(ans_aids)}")
    # receipt paths resolve higher -> child -> atom -> source span
    paths_ok = True
    for r in grows:
        if len(r["path"]) != 3:
            paths_ok = False
        par, ch, aid = r["path"]
        if ch not in hier_a["parents"][par]["children"]:
            paths_ok = False
        if aid not in hier_a["leaves"][ch]["members"]:
            paths_ok = False
        if r["span"] != idx_a.atoms[aid]["span"]:
            paths_ok = False
        if r["integrity"] != "intact-verified":
            paths_ok = False
    check("hier-guided-paths", paths_ok and len(grows) > 0,
          f"{[r['path'] for r in grows]}")
    check("hier-guided-bounds",
          grec["max_depth_used"] <= 4
          and gwork["member_visits"] <= 10000
          and grec["cycle_skips"] == 0, f"{grec}")
    # matched-work flat control: same total scorings, deterministic order
    frows, frep = hq.flat("sport", total_budget=gtotal, top_atoms=10)
    fwork = frep["work"]
    ftotal = fwork["leaves_scored"] + fwork["atoms_scored"]
    fgot = {r["aid"] for r in frows}
    check("hier-ablation-work", ftotal == gtotal,
          f"flat={ftotal} guided={gtotal}")
    check("hier-ablation-contributes",
          len(ans_aids & got) > len(ans_aids & fgot),
          f"guided={len(ans_aids & got)} flat={len(ans_aids & fgot)}")
    # exhaustive flat reaches the same recall only with strictly more work
    xrows, xrep = hq.flat("sport", total_budget=10 ** 9, top_atoms=10)
    xgot = {r["aid"] for r in xrows}
    xwork = xrep["work"]
    xtotal = xwork["leaves_scored"] + xwork["atoms_scored"]
    check("hier-flat-floor",
          ans_aids <= xgot and xtotal > gtotal,
          f"exhaustive work={xtotal} guided work={gtotal}")
    # determinism of guided serving
    grows2, grec2 = hq.guided("sport", top_parents=1, top_children=2,
                              top_atoms=10)
    check("hier-deterministic",
          [r["aid"] for r in grows] == [r["aid"] for r in grows2]
          and grec["work"] == grec2["work"], "guided rerun diverged")

    # -- cycle store: cyclic parent refs terminate bounded ------------
    tmp_c = tempfile.mkdtemp(prefix="tlsys-m2a-cyc-")
    tl_c = TLStore(os.path.join(tmp_c, "store"), create=True,
                   lease_owner="test-m2a-cyc")
    ingest_docs(tl_c, [("c-doc", run_of("sport", 150, 40000))], emb)
    organize_segments(tl_c)
    from tlsys.store_if import prepare_artifact as _prep
    _store = tl_c.store
    _prep1 = lambda bb, sid: _prep(_store, bb, sid)  # noqa: E731
    _hc = read_seg_hierarchy(tl_c, tl_c.pin())
    _lf = next(iter(_hc["leaves"].keys()))
    _aids = list(_hc["leaves"][_lf]["members"])
    _cyc1 = parent_op("xpar-cyc-1", ["xpar-cyc-2"], list(_aids),
                      list(V_SPORT), "tl-sys-docs", _prep1)
    _cyc2 = parent_op("xpar-cyc-2", ["xpar-cyc-1"], list(_aids),
                      list(V_SPORT), "tl-sys-docs", _prep1)
    _res, _info = tl_c.commit_batch([_cyc1, _cyc2])
    assert all(r.get("status") == "committed" for r in _res), _res
    idx_c = NarrowIndex(tl_c, tl_c.pin())
    hq_c = HierQuery(tl_c, idx_c, emb1)
    crows, crep = hq_c.guided("sport", top_parents=10, top_children=10,
                              top_atoms=10)
    check("hier-cycle",
          crep["cycle_skips"] >= 1
          and crep["work"]["member_visits"] <= 10000
          and crep["max_depth_used"] <= 4, f"{crep}")
    tl_c.close()

    # -- no-hierarchy store + Narrow defaults --------------------------
    tmp_n = tempfile.mkdtemp(prefix="tlsys-m2a-nar-")
    tl_n = TLStore(os.path.join(tmp_n, "store"), create=True,
                   lease_owner="test-m2a-nar")
    ingest_docs(tl_n, [("n-doc", "plain narrow seulement")], emb)
    pin_n = tl_n.pin()
    idx_n = NarrowIndex(tl_n, pin_n)
    hq_n = HierQuery(tl_n, idx_n, emb1)
    nrows, nrep = hq_n.guided("plain")
    check("hier-no-store",
          nrows == [] and nrep["status"] == "no-hierarchy"
          and nrep["work"] == {"parents_scored": 0, "children_scored": 0,
                               "atoms_scored": 0, "member_visits": 0},
          f"{nrep}")
    nq = NarrowQuery(tl_n, idx_n, emb1)
    _dos, _rec = nq.run("plain")
    check("narrow-defaults",
          "hierarchy" not in _rec["metrics"]
          and "candidate_nav" not in _rec["metrics"], f"{_rec['metrics']}")
    tl_n.close()

    tl_r.close()
    tl_a.close()
    print("store-root:", tmp)
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
