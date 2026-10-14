"""Portable repair-correction tests: durable debt, no durable mutation on None.

Target: OWN fork ONLY (REPAIR_UNDER_TEST, default sibling fork path).
Frozen v5 read-only for one negative control (FROZEN_V5 env or default).
No package/builder imports: file-location load only. Real NumPy, <=128 atoms.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OWN_FORK = os.environ.get("REPAIR_UNDER_TEST",
                          os.path.join(HERE, "fork", "tl-sys", "tlsys", "local_repair.py"))
FROZEN_V5 = os.environ.get("FROZEN_V5",
                           "/home/anshul/trace-ops/handoff/sup/runs/20261011T160645Z"
                           "/vm-candidate-v5/fork/tl-sys/tlsys/local_repair.py")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mod = load("own_local_repair", OWN_FORK)

import numpy as np  # noqa: E402 real runtime, no shims

DIM = 8
CAP_LEAF = 25
CAP_KIDS = 16


def cfg(**kw):
    d = dict(enabled=True, dimension=DIM)
    d.update(kw)
    return mod.RepairConfig(**d)


def unit(k):
    v = np.zeros(DIM)
    v[k % DIM] = 1.0
    return v


def spread(n, seed):
    rng = np.random.default_rng(seed)
    m = rng.normal(size=(n, DIM))
    return [row / float(np.linalg.norm(row)) for row in m]


def leaf_entry(members, vectors, stale=True):
    ms = sorted(members)
    d = np.asarray([vectors[a] for a in ms], dtype=np.float64).mean(axis=0)
    if stale:
        d = d + 1e-9
    return {"members": ms, "descriptor": d.tolist(), "segments": []}


def parent_entry(children, leaves):
    um = sorted({a for lid in children for a in leaves[lid]["members"]})
    return {"children": sorted(children), "members": um, "descriptor": np.zeros(DIM).tolist()}


def assert_store_sound(eng, cap_leaf=CAP_LEAF, cap_kids=CAP_KIDS):
    seen = {}
    for lid, lf in eng.leaves.items():
        assert len(lf["members"]) == len(set(lf["members"])), lid
        assert len(lf["members"]) <= cap_leaf, (lid, len(lf["members"]))
        for a in lf["members"]:
            assert a not in seen, ("dup", a)
            seen[a] = lid
    for pid, p in eng.parents.items():
        assert len(p["children"]) == len(set(p["children"])), pid
        assert len(p["children"]) <= cap_kids, (pid, p["children"])
        for lid in p["children"]:
            assert lid in eng.leaves, ("dangling", pid, lid)
    for lid in eng.leaves:
        assert any(lid in p["children"] for p in eng.parents.values()), ("orphan", lid)
    for pid, p in eng.parents.items():
        um = sorted({a for lid in p["children"] for a in eng.leaves[lid]["members"]})
        assert p["members"] == um, ("union", pid)


def check(name, fn):
    fn()
    print("PASS %s" % name)


def c1_blocked_head_commit_raise_unchanged():
    """Blocked-parent head + later healthy work whose commit raises: snapshot bytes unchanged."""
    vectors, leaves = {}, {}
    kids = []
    for i in range(40):
        a = "j%03d" % i
        vectors[a] = unit(i)
        leaves["LJ%02d" % i] = leaf_entry([a], vectors)
        kids.append("LJ%02d" % i)
    okm = ["n%03d" % i for i in range(4)]
    for i, a in enumerate(okm):
        vectors[a] = unit(i)
    leaves["LO1"] = leaf_entry(okm[:2], vectors)
    leaves["LO2"] = leaf_entry(okm[2:], vectors)
    parents = {"P-big": parent_entry(sorted(kids), leaves),
               "P-ok": parent_entry(["LO1", "LO2"], leaves)}

    def fail(record):
        raise RuntimeError("simulated commit refusal")

    eng = mod.RepairEngine(vectors=dict(vectors), leaves=dict(leaves), parents=dict(parents),
                           config=cfg(), commit=fail)
    eng.touch(parent_ids=["P-big", "P-ok"])
    before = mod.canonical(eng.snapshot())
    try:
        eng.repair_step(10 ** 9)
    except RuntimeError as ex:
        assert "refusal" in str(ex), str(ex)
    else:
        raise AssertionError("commit failure did not propagate")
    assert mod.canonical(eng.snapshot()) == before, "complete rollback incl blocked head"


def c2_budget_unchanged():
    vectors = {}
    m1 = ["t%03d" % i for i in range(10)]
    m2 = ["u%03d" % i for i in range(8)]
    for a in m1:
        vectors[a] = unit(0)
    for a in m2:
        vectors[a] = unit(1)
    leaves = {"L1": leaf_entry(m1, vectors), "L2": leaf_entry(m2, vectors)}
    parents = {"P0": parent_entry(["L1", "L2"], leaves)}
    eng = mod.RepairEngine(vectors=dict(vectors), leaves=dict(leaves), parents=dict(parents), config=cfg())
    eng.touch(parent_ids=["P0"])
    q0 = list(eng.queue)
    before = mod.canonical(eng.snapshot())
    out = eng.repair_step(0)
    assert out["blocked"] == "budget" and out["spent"] == 0 and out["checked"] == 0, out
    assert mod.canonical(eng.snapshot()) == before and list(eng.queue) == q0
    eng2 = mod.RepairEngine(vectors=dict(vectors), leaves=dict(leaves), parents=dict(parents), config=cfg())
    eng2.touch(parent_ids=["P0"])
    before2 = mod.canonical(eng2.snapshot())
    out2 = eng2.repair_step(eng2._estimate(("parent", "P0")) - 1)
    assert out2["spent"] == 0 and out2["checked"] == 0, out2
    assert mod.canonical(eng2.snapshot()) == before2, "too-small budget unchanged"


def c3_impossible_only_unchanged():
    c = cfg(max_leaf_members=7)
    vectors = {}
    mem = ["h%03d" % i for i in range(120)]
    for a, v in zip(mem, spread(120, 13)):
        vectors[a] = v
    s = ["i%03d" % i for i in range(4)]
    for i, a in enumerate(s):
        vectors[a] = unit(i)
    leaves = {"L-huge": leaf_entry(mem, vectors), "L-s": leaf_entry(s, vectors)}
    parents = {"P0": parent_entry(["L-huge", "L-s"], leaves)}
    eng = mod.RepairEngine(vectors=dict(vectors), leaves=leaves, parents=parents, config=c)
    eng.touch(parent_ids=["P0"])
    eng.touch(leaf_ids=["L-huge"])
    before_q = list(eng.queue)
    before = mod.canonical(eng.snapshot())
    out = eng.repair_step(10 ** 9)
    assert out["checked"] == 0 and out["spent"] == 0, out
    assert out["blocked"] == "infeasible-local-two-way-split", out
    assert mod.canonical(eng.snapshot()) == before, "no counter/queue/order mutation on None"
    assert list(eng.queue) == before_q, "order preserved exactly"
    assert eng.counts["member_rows"] == 0 and eng.counts["cosine_rows"] == 0, dict(eng.counts)
    snap = eng.snapshot()
    eng2 = mod.RepairEngine.restore(snap, dict(vectors))
    assert list(eng2.queue) == before_q, "queue durable across restore"


def c4_feasible_noop_same_call_drain():
    vectors = {}
    mem = ["f%03d" % i for i in range(40)]
    for a, v in zip(mem, spread(40, 9)):
        vectors[a] = v
    s = ["g%03d" % i for i in range(6)]
    for i, a in enumerate(s):
        vectors[a] = unit(i)
    leaves = {"L-40": leaf_entry(mem, vectors), "L-s": leaf_entry(s, vectors)}
    parents = {"P0": parent_entry(["L-40", "L-s"], leaves)}
    eng = mod.RepairEngine(vectors=dict(vectors), leaves=leaves, parents=parents, config=cfg())
    eng.touch(leaf_ids=["L-40"])
    out = eng.repair_step(10 ** 9)
    assert out["debt"] == 0 and out["blocked"] is None, out
    assert out["checked"] >= 1, out  # changed record + same-call no-op consumption
    assert eng.counts.get("leaf_split", 0) == 1, dict(eng.counts)
    assert eng.counts.get("infeasible", 0) == 0, dict(eng.counts)
    assert_store_sound(eng)
    fam = [lid for lid, lf in eng.leaves.items() if set(lf["members"]) <= set(mem)]
    assert len(fam) == 2, fam  # original two-way path, not multiway
    before = mod.canonical(eng.snapshot())
    out2 = eng.repair_step(10 ** 9)
    assert out2["checked"] == 0 and mod.canonical(eng.snapshot()) == before


def c5_blocked_parent_healable_leaf_zero_debt():
    vectors = {}
    big = ["a%03d" % i for i in range(56)]
    s = ["b%03d" % i for i in range(10)]
    t = ["c%03d" % i for i in range(8)]
    for i, a in enumerate(big):
        vectors[a] = unit(i)
    for i, a in enumerate(s):
        vectors[a] = unit(i + 2)
    for i, a in enumerate(t):
        vectors[a] = unit(i + 5)
    leaves = {"L-big": leaf_entry(big, vectors), "L-s": leaf_entry(s, vectors),
              "L-t": leaf_entry(t, vectors)}
    parents = {"P0": parent_entry(["L-big", "L-s", "L-t"], leaves)}
    eng = mod.RepairEngine(vectors=dict(vectors), leaves=leaves, parents=parents, config=cfg())
    eng.touch(parent_ids=["P0"])  # parent only; missing leaf key must be TEMP, not durable pre-add
    q0len = len(eng.queue)
    assert list(eng.queue) == [("parent", "P0")], list(eng.queue)
    out = eng.repair_step(10 ** 9)
    assert out["debt"] == 0 and out["blocked"] is None, out
    assert out["checked"] >= 1, out
    assert eng.counts.get("infeasible", 0) == 0, dict(eng.counts)
    assert_store_sound(eng)
    union = sorted({a for lf in eng.leaves.values() for a in lf["members"]})
    assert union == sorted(big + s + t), "members retained"
    fam = [lid for lid, lf in eng.leaves.items() if set(lf["members"]) <= set(big)]
    assert len(fam) == 3, fam  # ceil(56/25) multiway
    assert q0len == 1


def c6_healthy_behind_truly_impossible():
    vectors, leaves = {}, {}
    kids = []
    for i in range(40):
        a = "j%03d" % i
        vectors[a] = unit(i)
        leaves["LJ%02d" % i] = leaf_entry([a], vectors)
        kids.append("LJ%02d" % i)
    okm = ["n%03d" % i for i in range(4)]
    for i, a in enumerate(okm):
        vectors[a] = unit(i)
    leaves["LO1"] = leaf_entry(okm[:2], vectors)
    leaves["LO2"] = leaf_entry(okm[2:], vectors)
    parents = {"P-big": parent_entry(sorted(kids), leaves),
               "P-ok": parent_entry(["LO1", "LO2"], leaves)}
    eng = mod.RepairEngine(vectors=dict(vectors), leaves=leaves, parents=parents, config=cfg())
    eng.touch(parent_ids=["P-big", "P-ok"])
    out = eng.repair_step(10 ** 9)
    assert out["blocked"] == "infeasible-local-two-way-split", out
    assert out["checked"] >= 1, out
    assert ("parent", "P-big") in eng.queue, "truly impossible debt retained"
    assert eng.parents["P-big"]["children"] == sorted(kids), "blocked input untouched"
    assert eng.counts.get("infeasible", 0) == 0, dict(eng.counts)


def c7_multiway_and_invariants():
    vectors = {}
    mem = ["d%03d" % i for i in range(65)]
    for a, v in zip(mem, spread(65, 7)):
        vectors[a] = v
    s = ["e%03d" % i for i in range(6)]
    for i, a in enumerate(s):
        vectors[a] = unit(i)
    leaves = {"L-65": leaf_entry(mem, vectors), "L-s": leaf_entry(s, vectors)}
    parents = {"P0": parent_entry(["L-65", "L-s"], leaves)}
    eng = mod.RepairEngine(vectors=dict(vectors), leaves=leaves, parents=parents, config=cfg())
    eng.touch(parent_ids=["P0"])
    eng.touch(leaf_ids=["L-65"])
    for _ in range(6):
        out = eng.repair_step(10 ** 9)
        if out["debt"] == 0:
            break
    assert out["debt"] == 0, out
    assert_store_sound(eng)
    fam = [lid for lid, lf in eng.leaves.items() if set(lf["members"]) <= set(mem)]
    assert len(fam) == 3, fam
    assert sorted(len(eng.leaves[lid]["members"]) for lid in fam) == [21, 22, 22], fam
    eng_o = mod.RepairEngine(vectors=dict(vectors),
                             leaves={"L-orph": leaf_entry(mem[:30], vectors)}, parents={}, config=cfg())
    try:
        eng_o._proposal(("leaf", "L-orph"))
    except ValueError as ex:
        assert str(ex) == "orphan input leaf", str(ex)
    else:
        raise AssertionError("orphan did not raise")
    v5 = load("frozen_local_repair", FROZEN_V5)
    eng5 = v5.RepairEngine(vectors=dict(vectors), leaves=dict(leaves), parents=dict(parents),
                           config=v5.RepairConfig(enabled=True, dimension=DIM))
    eng5.touch(parent_ids=["P0"])
    try:
        eng5.repair_step(10 ** 9)
    except ValueError as ex:
        assert str(ex) == "invalid repaired leaf capacity", str(ex)
    else:
        raise AssertionError("v5 did not crash on 56+ parent scope")


TESTS = {
    "c1": c1_blocked_head_commit_raise_unchanged,
    "c2": c2_budget_unchanged,
    "c3": c3_impossible_only_unchanged,
    "c4": c4_feasible_noop_same_call_drain,
    "c5": c5_blocked_parent_healable_leaf_zero_debt,
    "c6": c6_healthy_behind_truly_impossible,
    "c7": c7_multiway_and_invariants,
}


def main():
    names = sys.argv[1:] or ["c1", "c2", "c3", "c4", "c5", "c6", "c7"]
    for n in names:
        check("%s_%s" % (n, TESTS[n].__name__), TESTS[n])
    print("ALL-PASS %d/%d" % (len(names), len(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
