"""C2 Lane O: fault-injection rows 15, 16, 17, 19 (organization).

FI-15 valid prefix: fail each commit batch of an organize call in
turn (deterministic hook around commit_batch, raised before the
real commit so the batch is atomic-nothing), on flag-off and
flag-on twins; every killed prefix and every resumed completion
is structurally valid (no dangling/cyclic refs, member union
consistent, descriptors the exact member mean), and the resumed
twins agree with each other.
FI-16 overlap accounting: on an overlap-heavy fixture, every
parent's members are exactly the deduplicated child union and its
descriptor is the exact member mean (allclose: join_descriptor is
an incremental mean, identical math on both paths); flag-on and
flag-off agree.
FI-17 id/ordinal stability: overflow-sibling ids are deterministic
across rebuild twins; re-run organize is commit-free; a killed
doc consumes no sibling numbers (resumed numbering is gapless
and equal to the clean run).
FI-19 reverse-map drift: projection maps validate clean after
ingest+organize; a deliberately corrupted map is detected by
validate_reverse_maps and repaired by rebuild_reverse_maps.

Deterministic fake encoder; scratch stores under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_fi_15161719.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "coordination", "c2-work-20261006T1925Z", "lane-G")))

import numpy as np  # noqa: E402

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.maint import organize_segments  # noqa: E402
from tlsys.place import read_seg_hierarchy  # noqa: E402
from tlsys.proj import Projections  # noqa: E402
from profile import default_profile  # noqa: E402  (Lane G, read-only)

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


V_SPORT = pad([1.0, 0.1, 0.0])
V_SPORT2 = pad([0.95, 0.31, 0.0])
V_MED = pad([0.1, 1.0, 0.0])
V_BOTH = pad([0.72, 0.69, 0.0])
V_OUT = pad([0.0, 0.0, 1.0])


def emb(texts):
    out = []
    for t in texts:
        w = t.split()[0] if t.split() else ""
        if w.startswith("sport"):
            out.append(list(V_SPORT if "0" in w[:7] else V_SPORT2))
        elif w.startswith("medic"):
            out.append(list(V_MED))
        elif w.startswith("bothmark"):
            out.append(list(V_BOTH))
        else:
            out.append(list(V_OUT))
    return out


def run_of(word, n, start=0):
    return " ".join(f"{word}{start + i}" for i in range(n))


DOCS = [("doc-multi", " ".join([run_of("sport", 150, 0),
                                run_of("medic", 150, 0),
                                run_of("sport", 150, 1000),
                                run_of("medic", 150, 1000)])),
        ("doc-sport-b", run_of("sport", 150, 5000)),
        ("doc-med-b", run_of("medic", 150, 6000)),
        ("doc-both", run_of("bothmark", 150, 7000)),
        ("doc-out", run_of("outlier", 150, 8000))]


def prof_on(pid):
    p = default_profile(profile_id=pid,
                        calibration_manifest_id="seed-host-20261006")
    p["flags"]["organization_catalog_routing"] = True
    return p


def validate_hierarchy(tl):
    """(ok, detail): I7 valid-prefix structural checks on committed state.

    Every parent child resolves to a committed leaf; every member aid
    resolves to a committed atom; no self/cross cycles possible (leaf
    ids never appear as parent ids and vice versa); every parent's
    members are exactly the deduplicated child union; every
    descriptor is the exact member mean (allclose: incremental mean
    math, same on both paths).
    """
    pin = tl.pin()
    idx = NarrowIndex(tl, pin)
    hier = read_seg_hierarchy(tl, pin)
    leaves, parents = hier["leaves"], hier["parents"]
    if set(leaves) & set(parents):
        return False, "leaf/parent id sets overlap"
    avec = {a: np.asarray(idx.atoms[a]["descriptor"], dtype=np.float64)
            for a in idx.atoms}
    for lid, lf in leaves.items():
        for a in lf["members"]:
            if a not in avec:
                return False, f"leaf {lid} member {a} dangles"
        if lf["members"] and not np.allclose(
                lf["descriptor"],
                np.stack([avec[a] for a in lf["members"]]).mean(
                    axis=0)):
            return False, f"leaf {lid} descriptor not member mean"
    for pid, par in parents.items():
        if not par["children"]:
            return False, f"parent {pid} has no children"
        for c in par["children"]:
            if c not in leaves:
                return False, f"parent {pid} child {c} dangles"
            if c in parents:
                return False, f"child {c} is also a parent (cycle)"
        union = [a for c in par["children"]
                 for a in leaves[c]["members"]]
        if sorted(par["members"]) != sorted(set(union)):
            return False, (f"parent {pid} members != deduped "
                           "child union")
        if union and not np.allclose(
                par["descriptor"],
                np.stack([avec[a]
                          for a in set(union)]).mean(axis=0)):
            return False, f"parent {pid} descriptor not member mean"
    return True, f"{len(leaves)} leaves, {len(parents)} parents valid"


def hier_key(tl):
    # Cross-store comparable structure key: leaf ids + member
    # (doc, span) sets + children sets (member order/descriptors are
    # covered by the D2 suite; here resume-equality is structural).
    pin = tl.pin()
    idx = NarrowIndex(tl, pin)
    hier = read_seg_hierarchy(tl, pin)

    def sig(aids):
        return sorted((idx.atoms[a]["doc_id"],
                       tuple(idx.atoms[a]["span"])) for a in aids)

    leaves = {k: sig(v["members"]) for k, v in hier["leaves"].items()}
    parents = {k: (sorted(v["children"]), sig(v["members"]))
               for k, v in hier["parents"].items()}
    return leaves, parents


def fresh_store(tag, docs, profile):
    tmp = tempfile.mkdtemp(prefix=f"tlsys-c2fi-{tag}-")
    tl = TLStore(os.path.join(tmp, "store"), create=True,
                 lease_owner=f"test-c2fi-{tag}")
    ingest_docs(tl, docs, emb, store_id="c2fi", profile=profile)
    return tl


class KillHook:
    """Fail the k-th commit_batch call once (before the real commit)."""

    def __init__(self, tl, k):
        self.tl = tl
        self.k = k
        self.n = 0
        self.orig = tl.commit_batch
        self.fired = False

    def __call__(self, ops):
        self.n += 1
        if self.n == self.k and not self.fired:
            self.fired = True
            raise RuntimeError(f"FI-15 injected kill at batch {self.k}")
        return self.orig(ops)

    def arm(self):
        self.tl.commit_batch = self

    def disarm(self):
        self.tl.commit_batch = self.orig


def main():
    p_on = prof_on("c2fi")

    # -- how many commit batches does a clean organize take? -----------
    probe = fresh_store("probe", DOCS, None)
    batches = []
    orig = probe.commit_batch
    probe.commit_batch = lambda ops: (
        batches.append(len(ops)), orig(ops))[1]
    org0 = organize_segments(probe)
    probe.commit_batch = orig
    ok0, det0 = validate_hierarchy(probe)
    check("fi15-clean-valid", ok0 and not org0["failed"], det0)
    n_batches = len(batches)
    check("fi15-clean-batches", n_batches >= 2, f"{batches}")
    probe.close()

    # -- kill each batch in turn, on flag-off/on twins -----------------
    for k in range(1, n_batches + 1):
        tl_r = fresh_store(f"r{k}", DOCS, None)
        tl_c = fresh_store(f"c{k}", DOCS, p_on)
        kr, kc = KillHook(tl_r, k), KillHook(tl_c, k)
        kr.arm()
        kc.arm()
        org_r = organize_segments(tl_r)
        org_c = organize_segments(tl_c, profile=p_on)
        kr.disarm()
        kc.disarm()
        check(f"fi15-k{k}-fired",
              kr.fired and kc.fired
              and org_r["failed"] and org_c["failed"],
              f"ref={org_r['failed']} cat={org_c['failed']}")
        okr, detr = validate_hierarchy(tl_r)
        okc, detc = validate_hierarchy(tl_c)
        check(f"fi15-k{k}-prefix-valid", okr and okc,
              f"ref={detr} cat={detc}")
        # Resume clean on both; both must complete valid and agree.
        res_r = organize_segments(tl_r)
        res_c = organize_segments(tl_c, profile=p_on)
        check(f"fi15-k{k}-resumed",
              not res_r["failed"] and not res_c["failed"]
              and res_r["remaining"] == []
              and res_c["remaining"] == [],
              f"ref={res_r} cat={res_c}")
        okr2, detr2 = validate_hierarchy(tl_r)
        okc2, detc2 = validate_hierarchy(tl_c)
        check(f"fi15-k{k}-resumed-valid", okr2 and okc2,
              f"ref={detr2} cat={detc2}")
        check(f"fi15-k{k}-twins-agree",
              hier_key(tl_c) == hier_key(tl_r),
              "resumed twins diverged")
        tl_r.close()
        tl_c.close()

    # -- FI-16 overlap accounting (both paths, exact union) -------------
    tl_m = fresh_store("fi16", DOCS, p_on)
    organize_segments(tl_m, profile=p_on)
    pin = tl_m.pin()
    idx = NarrowIndex(tl_m, pin)
    hier = read_seg_hierarchy(tl_m, pin)
    both_aid = idx.holons["doc-both"]["members"][0]
    both_in = [lid for lid, lf in hier["leaves"].items()
               if both_aid in lf["members"]]
    check("fi16-overlap-present", len(both_in) == 2, repr(both_in))
    ok16 = True
    det16 = ""
    avec = {a: np.asarray(idx.atoms[a]["descriptor"],
                          dtype=np.float64) for a in idx.atoms}
    for pid, par in hier["parents"].items():
        union = [a for c in par["children"]
                 for a in hier["leaves"][c]["members"]]
        if sorted(par["members"]) != sorted(set(union)):
            ok16, det16 = False, f"{pid}: union mismatch"
        exact = np.stack([avec[a] for a in set(union)]).mean(axis=0)
        if not np.allclose(par["descriptor"], exact):
            ok16, det16 = False, f"{pid}: mean mismatch"
        # The shared atom is one member but two memberships: union
        # size is strictly smaller than the summed child sizes iff
        # overlap flows through this parent.
    check("fi16-exact-union-mean", ok16, det16)
    multi_kids = [pid for pid, par in hier["parents"].items()
                  if len(both_in) >= 2
                  and sum(c in par["children"] for c in both_in)
                  >= 1]
    check("fi16-overlap-flows", len(multi_kids) >= 1,
          repr(multi_kids))
    tl_m.close()

    # -- FI-17 sibling determinism + gapless resume ---------------------
    odocs = [(f"doc-s{i}", run_of("sport", 150, 10000 + 200 * i))
             for i in range(5)]
    tl_a = fresh_store("fi17a", odocs, None)
    tl_b = fresh_store("fi17b", odocs, p_on)
    organize_segments(tl_a, max_leaf_members=3)
    organize_segments(tl_b, max_leaf_members=3, profile=p_on)
    sib_a = sorted(k for k in
                   read_seg_hierarchy(tl_a, tl_a.pin())["leaves"]
                   if "-ov" in k)
    sib_b = sorted(k for k in
                   read_seg_hierarchy(tl_b, tl_b.pin())["leaves"]
                   if "-ov" in k)
    check("fi17-sibling-deterministic",
          sib_a == sib_b and len(sib_a) == 1, f"{sib_a}/{sib_b}")
    # Re-run is commit-free on both paths (no re-minted siblings).
    pin_a, pin_b = tl_a.pin(), tl_b.pin()
    re_a = organize_segments(tl_a)
    re_b = organize_segments(tl_b, profile=p_on)
    check("fi17-rerun-clean",
          re_a["n_commits"] == 0 and re_b["n_commits"] == 0
          and tl_a.pin()[3] == pin_a[3]
          and tl_b.pin()[3] == pin_b[3], f"{re_a}/{re_b}")
    tl_a.close()
    tl_b.close()
    # Killed single-doc batch -> resume equals the clean run
    # (gapless: the rolled-back sibling number is reused, not
    # skipped). A multi-doc kill legitimately replays the failed
    # doc last against different state (covered by fi15 twins),
    # so the gapless check isolates one doc.
    def _scenario(profile, kill):
        tl = fresh_store("fi17q", odocs, profile)
        first = [d for d, _t in odocs[:4]]
        organize_segments(tl, doc_ids=first, max_leaf_members=3,
                          profile=profile)
        if kill:
            hook = KillHook(tl, 1)
            hook.arm()
            organize_segments(tl, doc_ids=[odocs[4][0]],
                              max_leaf_members=3, profile=profile)
            hook.disarm()
            assert hook.fired
        res = organize_segments(tl, doc_ids=[odocs[4][0]],
                                max_leaf_members=3,
                                profile=profile)
        assert not res["failed"], res
        sibs = sorted(
            k for k in read_seg_hierarchy(tl, tl.pin())["leaves"]
            if "-ov" in k)
        key = hier_key(tl)
        tl.close()
        return sibs, key

    sib_co, key_co = _scenario(None, False)
    sib_cn, key_cn = _scenario(p_on, False)
    sib_ro, key_ro = _scenario(None, True)
    sib_rn, key_rn = _scenario(p_on, True)
    check("fi17-gapless-resume",
          sib_co == sib_cn == sib_ro == sib_rn
          and len(sib_co) == 1, f"{sib_co}/{sib_cn}/{sib_ro}/{sib_rn}")
    check("fi17-resume-equals-clean",
          key_co == key_cn == key_ro == key_rn,
          "clean/resume twins diverged")

    # -- FI-19 reverse-map drift detect + repair ------------------------
    tl_p = fresh_store("fi19", DOCS, None)
    organize_segments(tl_p)
    proj = Projections.cached(tl_p)
    proj.update(tl_p)
    rep = proj.validate_reverse_maps()
    check("fi19-clean", rep["ok"], f"{rep}")
    # Corrupt each map once; every corruption is detected.
    lp = proj.leaf_parents_view()
    victim = next(iter(lp))
    saved = set(lp[victim])
    lp[victim].add("xseg-GHOST")
    rep2 = proj.validate_reverse_maps()
    check("fi19-detect-leaf-parents",
          not rep2["ok"]
          and any(m["key"] == victim for m in rep2["mismatches"]),
          f"{rep2}")
    lp[victim] = saved
    al = proj.atom_leaves_view()
    avictim = next(iter(al))
    asaved = set(al[avictim])
    al[avictim].clear()
    rep3 = proj.validate_reverse_maps()
    check("fi19-detect-atom-leaves",
          not rep3["ok"]
          and any(m["key"] == avictim for m in rep3["mismatches"]),
          f"{rep3}")
    al[avictim] = asaved
    # Repair path: rebuild from edges, validate clean.
    counts = proj.rebuild_reverse_maps()
    rep4 = proj.validate_reverse_maps()
    check("fi19-repair", rep4["ok"]
          and counts["leaf_edges"] > 0
          and counts["atom_edges"] > 0, f"{rep4}/{counts}")
    tl_p.close()

    print(f"fi-suite done: {len(FAILS)} failures")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
