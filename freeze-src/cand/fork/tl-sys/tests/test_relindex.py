"""Indexed relation reads: RelIndex + disclosure-prefilter conformance.

Covers RELREAD-PROFILE section 6 rules 1/2/4/6 at fixture scale
(query-level rule 3 + perf rule 5 run against the SciFact-scale
store in round8 trackA evidence, not here):

- read_relations == read_relations_fullscan (canonical JSON) on:
  empty store, atoms-only store, mixed store, repeat-rid
  latest-wins, foreign rel_scheme (both raise ValueError),
  id-mismatch (both raise ValueError), adversarial relation meta
  smuggled under a non-"relations" disclosure leg (fast path misses
  per the LEG read contract; TL_REL_AUDIT=1 raises; oracle finds).
- min_seq filtering identical between fast path and oracle.
- RelIndex structure: by_type / endpoint_adj sorted, qualifier
  sidecar, opposition material; PYTHONHASHSEED-independent order.
- Frontier discipline: same-pin serves from memory (zero
  read_commits/read_artifact calls); pin advance extends via a
  min_seq window only (asserted via captured min_seq args);
  backward pin rebuilds; invalidate_rel_index drops entries.
- RelView-equivalence: load() over indexed reads vs oracle reads
  (visible/eligible/reasons/degrees/scope/unresolved + pairs).
- identify_pairs over index opposition material == computed path.
- dossier lateral over adjacency == full-scan lateral (entries +
  receipts modulo T_ms), including a duplicate-endpoint record.
- Flag-OFF invariance: OFF runs issue zero relation-path calls and
  stay byte-identical pre/post relation commit.

Deterministic fake encoder; scratch stores under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_relindex.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.store_if import prepare_artifact as _prep_art  # noqa: E402
from tlsys.store_if import uuidv7  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys.identity import (canonical_json_bytes,  # noqa: E402
                            extractor_config_id)
from tlsys.relations import (PROPOSED, REL_SCHEME,  # noqa: E402
                             commit_relations, eligible,
                             endpoint_degrees, get_index,
                             invalidate_rel_index, make_record,
                             read_relations,
                             read_relations_fullscan)
from tlsys import relations as relations_mod  # noqa: E402
from tlsys import relquery  # noqa: E402
from tlsys import dossier as dossier_mod  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def canon(obj):
    return json.dumps(obj, sort_keys=True, default=str)


def norm_run(obj):
    """Canonical run output with wall-clock / pin stamps neutralized
    (T_ms wall time; pinned/resolving generations, which legitimately
    differ across pins). Everything else must match exactly."""
    obj = json.loads(json.dumps(obj, default=str))

    def _walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "T_ms":
                    o[k] = -1.0
                elif k in ("pinned_generation",
                           "resolving_generation"):
                    o[k] = "*"
                else:
                    _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)

    _walk(obj)
    return canon(obj)


def emb(texts):
    return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


CFG = {"extractor": "test-relindex-v1", "window": 2}
CFG_HEX = extractor_config_id(CFG)
A = "aa" * 32
B = "bb" * 32
C = "cc" * 32


def fresh_store(prefix="tl-relidx-"):
    root = tempfile.mkdtemp(prefix=prefix)
    tl = TLStore(root, create=True, lease_owner="test-relindex")
    return root, tl


def craft_op(tl, meta, leg, store_id="tl-sys-docs"):
    """Commit-ready ACCEPT_ATOMS op with hand-made meta + leg."""
    mart = _prep_art(tl.store, json.dumps(
        meta, sort_keys=True).encode(), store_id)
    return {"op_id": uuidv7(),
            "kind": "ACCEPT_ATOMS",
            "payload": {"relation": meta.get("relation", "00" * 32),
                        "meta_artifact": mart["artifact_id"]},
            "disclosure": {"leg": leg},
            "approval_ref": None,
            "artifacts": (mart,)}


def commit_ops(tl, ops):
    results, _info = tl.commit_batch(ops)
    for r in results:
        assert r.get("status") == "committed", r
    return [r["op_id"] for r in results]


# -- A. empty store -----------------------------------------------
root_a, tla = fresh_store()
try:
    pin_a = tla.pin()
    check("empty/fast-eq-oracle",
          canon(read_relations(tla, pin_a))
          == canon(read_relations_fullscan(tla, pin_a))
          == canon({}))
finally:
    tla.close()

# -- B. atoms-only store -------------------------------------------
root_b, tlb = fresh_store()
try:
    ingest_docs(tlb, [("d1", "alpha one two three four"),
                      ("d2", "beta five six seven eight")], emb)
    pin_b = tlb.pin()
    check("atoms-only/fast-eq-oracle",
          canon(read_relations(tlb, pin_b))
          == canon(read_relations_fullscan(tlb, pin_b))
          == canon({}))
finally:
    tlb.close()

# -- C. mixed store + repeat-rid + min_seq --------------------------
root_c, tlc = fresh_store()
try:
    rep = ingest_docs(tlc, [("d1", "alpha one two three four"),
                            ("d2", "beta five six seven eight")],
                      emb)
    assert rep["n_atoms"] == 2, rep
    pin_c0 = tlc.pin()
    idx_c0 = NarrowIndex(tlc, pin_c0)
    aids = sorted(idx_c0.atoms.keys())
    assert len(aids) == 2, aids
    r1 = make_record("supports",
                     [("source", aids[0]), ("target", aids[1])],
                     {"negated": False}, CFG, PROPOSED,
                     [aids[0], aids[1]])
    r2 = make_record("cooccurs", [aids[0], aids[1]],
                     {"negated": True, "scope": "as-stated"},
                     CFG, PROPOSED, [aids[0]],
                     interchangeable=True)
    # repeat-rid new version: same identity inputs, new version tag
    r1v2 = make_record("supports",
                       [("source", aids[0]), ("target", aids[1])],
                       {"negated": False}, CFG, PROPOSED,
                       [aids[0], aids[1]], version=2)
    assert r1v2["relation"] == r1["relation"]
    commit_relations(tlc, [r1, r2])
    pin_c1 = tlc.pin()
    commit_relations(tlc, [r1v2])
    pin_c2 = tlc.pin()
    fast = read_relations(tlc, pin_c2)
    oracle = read_relations_fullscan(tlc, pin_c2)
    check("mixed/fast-eq-oracle",
          canon(fast) == canon(oracle) and len(fast) == 2,
          f"{len(fast)}")
    check("mixed/latest-wins",
          fast[r1["relation"]]["record"]["version"] == 2
          and fast[r1["relation"]]["seq"] > fast[
              r2["relation"]]["seq"],
          fast[r1["relation"]])
    # min_seq filtering identical to the oracle at every cut
    cuts = sorted({0, pin_c0[2], pin_c1[2], pin_c2[2]})
    ms_ok = all(
        canon(read_relations(tlc, pin_c2, min_seq=c))
        == canon(read_relations_fullscan(tlc, pin_c2, min_seq=c))
        for c in cuts)
    check("mixed/min-seq-eq-oracle", ms_ok, cuts)
    check("mixed/min-seq-tail-only",
          set(read_relations(tlc, pin_c2,
                             min_seq=pin_c1[2])) == {
              r1["relation"]},
          sorted(read_relations(tlc, pin_c2, min_seq=pin_c1[2])))
    check("mixed/min-seq-empty",
          read_relations(tlc, pin_c2,
                         min_seq=pin_c2[2]) == {},
          read_relations(tlc, pin_c2, min_seq=pin_c2[2]))
    # index structure over the mixed store
    invalidate_rel_index(tlc)
    idxc = get_index(tlc, pin_c2)
    check("index/by-type",
          idxc.by_type == {"cooccurs": [r2["relation"]],
                           "supports": [r1["relation"]]},
          idxc.by_type)
    check("index/adjacency-sorted",
          all(v == sorted(v) for v in idxc.endpoint_adj.values())
          and set(idxc.endpoint_adj) == set(aids),
          idxc.endpoint_adj)
    check("index/adj-roles",
          idxc.endpoint_adj[aids[0]] == sorted(
              [(r1["relation"], "source"),
               (r2["relation"], None)]),
          idxc.endpoint_adj[aids[0]])
    check("index/qual-sidecar",
          idxc.qualifiers[r2["relation"]] == {
              "negated": True, "scope": "as-stated"},
          idxc.qualifiers)
    rt, eids, rest, neg = idxc.opp[r2["relation"]]
    check("index/opp-material",
          rt == "cooccurs" and eids == frozenset(aids)
          and rest == canonical_json_bytes({"scope": "as-stated"})
          and neg is True, idxc.opp[r2["relation"]])
    check("index/frontier", idxc.frontier == pin_c2[2],
          idxc.frontier)
finally:
    tlc.close()


def _raises_ve(fn):
    try:
        fn()
    except ValueError:
        return True
    except AssertionError:
        return "assert"
    return False


# -- D. foreign rel_scheme: both raise -------------------------------
root_d, tld = fresh_store()
try:
    ingest_docs(tld, [("d1", "alpha one two three four")], emb)
    pin_d0 = NarrowIndex(tld, tld.pin())
    daids = sorted(pin_d0.atoms.keys())
    bad = make_record("supports",
                      [("source", daids[0]), ("target", daids[0])],
                      {"negated": False}, CFG, PROPOSED, [daids[0]])
    bad["rel_scheme"] = "tlsys-rel-v999"
    commit_ops(tld, [craft_op(tld, bad, "relations")])
    pin_d = tld.pin()
    invalidate_rel_index(tld)
    check("foreign/fast-raises",
          _raises_ve(lambda: read_relations(tld, pin_d)) is True)
    invalidate_rel_index(tld)
    check("foreign/oracle-raises",
          _raises_ve(lambda: read_relations_fullscan(
              tld, pin_d)) is True)
finally:
    tld.close()

# -- E. id mismatch: both raise --------------------------------------
root_e, tle = fresh_store()
try:
    ingest_docs(tle, [("d1", "alpha one two three four")], emb)
    eaids = sorted(NarrowIndex(tle, tle.pin()).atoms.keys())
    bad = make_record("supports",
                      [("source", eaids[0]), ("target", eaids[0])],
                      {"negated": False}, CFG, PROPOSED, [eaids[0]])
    bad["relation"] = "ff" * 32
    commit_ops(tle, [craft_op(tle, bad, "relations")])
    pin_e = tle.pin()
    invalidate_rel_index(tle)
    check("idmismatch/fast-raises",
          _raises_ve(lambda: read_relations(tle, pin_e)) is True)
    invalidate_rel_index(tle)
    check("idmismatch/oracle-raises",
          _raises_ve(lambda: read_relations_fullscan(
              tle, pin_e)) is True)
finally:
    tle.close()

# -- F. adversarial smuggle under a non-relations leg -----------------
root_f, tlf = fresh_store()
try:
    ingest_docs(tlf, [("d1", "alpha one two three four"),
                      ("d2", "beta five six seven eight")], emb)
    faids = sorted(NarrowIndex(tlf, tlf.pin()).atoms.keys())
    legit = make_record("supports",
                        [("source", faids[0]),
                         ("target", faids[1])],
                        {"negated": False}, CFG, PROPOSED,
                        [faids[0], faids[1]])
    commit_relations(tlf, [legit])
    smug = make_record("supports",
                       [("source", faids[1]),
                        ("target", faids[0])],
                       {"negated": True}, CFG, PROPOSED, [faids[1]])
    assert smug["relation"] != legit["relation"]
    commit_ops(tlf, [craft_op(tlf, smug, "ingest")])
    pin_f = tlf.pin()
    invalidate_rel_index(tlf)
    oracle_f = read_relations_fullscan(tlf, pin_f)
    check("smuggle/oracle-finds",
          set(oracle_f) == {legit["relation"],
                            smug["relation"]},
          sorted(oracle_f))
    invalidate_rel_index(tlf)
    fast_f = read_relations(tlf, pin_f)
    check("smuggle/fast-misses-per-contract",
          set(fast_f) == {legit["relation"]}, sorted(fast_f))
    os.environ["TL_REL_AUDIT"] = "1"
    try:
        invalidate_rel_index(tlf)
        got = _raises_ve(lambda: read_relations(tlf, pin_f))
    finally:
        del os.environ["TL_REL_AUDIT"]
    check("smuggle/audit-raises", got == "assert", got)
    # audit passes on a clean store (no false positive)
    os.environ["TL_REL_AUDIT"] = "1"
    try:
        invalidate_rel_index(tlf)
        # remove the smuggled record from view: pin before it
        clean = read_relations(tlf, pin_f, min_seq=pin_f[2])
    finally:
        del os.environ["TL_REL_AUDIT"]
    check("smuggle/audit-clean-prefix-ok", clean == {}, clean)
finally:
    tlf.close()

# -- G. frontier: memory serve + min_seq extend -----------------------
root_g, tlg = fresh_store()
try:
    ingest_docs(tlg, [("d1", "alpha one two three four"),
                      ("d2", "beta five six seven eight")], emb)
    gaids = sorted(NarrowIndex(tlg, tlg.pin()).atoms.keys())
    pin_g0 = tlg.pin()
    invalidate_rel_index(tlg)
    check("frontier/empty-prefix",
          read_relations(tlg, pin_g0) == {})
    mark = len(tlg.trace.calls)
    check("frontier/memory-serve",
          read_relations(tlg, pin_g0) == {})
    served = tlg.trace.calls[mark:]
    check("frontier/memory-serve-zero-store-reads",
          [c["op"] for c in served] == [],
          [c["op"] for c in served])
    # capture the extend window
    seen_min = []
    _orig_rc = tlg.read_commits

    def _spy_rc(birth, epoch, max_seq, kind=None, limit=100000,
                min_seq=0):
        seen_min.append(min_seq)
        return _orig_rc(birth, epoch, max_seq, kind=kind,
                        limit=limit, min_seq=min_seq)

    tlg.read_commits = _spy_rc
    try:
        gr = make_record("supports",
                         [("source", gaids[0]),
                          ("target", gaids[1])],
                         {"negated": False}, CFG, PROPOSED,
                         [gaids[0], gaids[1]])
        commit_relations(tlg, [gr])
        pin_g1 = tlg.pin()
        got = read_relations(tlg, pin_g1)
    finally:
        tlg.read_commits = _orig_rc
    check("frontier/extend-finds",
          set(got) == {gr["relation"]}, sorted(got))
    check("frontier/extend-min-seq-window",
          seen_min == [pin_g0[2]], seen_min)
    check("frontier/extend-eq-oracle",
          canon(got) == canon(
              read_relations_fullscan(tlg, pin_g1)))
    # backward pin rebuilds (older prefix, correct content)
    back = read_relations(tlg, pin_g0)
    check("frontier/backward-pin-rebuilds",
          back == {} and canon(back) == canon(
              read_relations_fullscan(tlg, pin_g0)), back)
    # ... and the newer pin still serves after that
    check("frontier/forward-again",
          set(read_relations(tlg, pin_g1)) == {gr["relation"]})
finally:
    tlg.close()

# -- H. RelView-equivalence + identify_pairs --------------------------
root_h, tlh = fresh_store()
try:
    ingest_docs(tlh, [("d1", "alpha one two three four"),
                      ("d2", "beta five six seven eight"),
                      ("d3", "gamma nine ten eleven twelve")], emb)
    idx_h = NarrowIndex(tlh, tlh.pin())
    haids = sorted(idx_h.atoms.keys())
    ha, hb, hc = haids[0], haids[1], haids[2]
    haff = make_record("evidences",
                       [("claim", ha), ("context", hc)],
                       {"negated": False, "scope": "as-stated"},
                       CFG, PROPOSED, [ha, hc])
    hneg = make_record("evidences",
                       [("claim", hb), ("context", hc)],
                       {"negated": True, "scope": "as-stated"},
                       CFG, PROPOSED, [hb, hc])
    commit_relations(tlh, [haff, hneg])
    pin_h = tlh.pin()
    live_h = set(haids)
    invalidate_rel_index(tlh)
    v_fast = relquery.load(tlh, pin_h, live_h)
    os.environ["TL_REL_ORACLE"] = "1"
    try:
        invalidate_rel_index(tlh)
        v_orc = relquery.load(tlh, pin_h, live_h)
    finally:
        del os.environ["TL_REL_ORACLE"]
    check("relview/oracle-carries-no-index",
          not hasattr(v_orc, "_opp")
          and hasattr(v_fast, "_opp"))
    for fld in ("visible", "eligible", "reasons", "degrees",
                "scope", "unresolved"):
        check(f"relview/{fld}-eq",
              canon(getattr(v_fast, fld))
              == canon(getattr(v_orc, fld)),
              fld)
    uni = {ha, hb, hc}
    check("relview/pairs-eq",
          relquery.identify_pairs(v_fast, uni)
          == relquery.identify_pairs(v_orc, uni)
          == [(ha, hb) if ha < hb else (hb, ha)],
          relquery.identify_pairs(v_fast, uni))
    # explicit-index load == default load
    idxh = get_index(tlh, pin_h)
    v_exp = relquery.load(tlh, pin_h, live_h, index=idxh)
    check("relview/explicit-index-eq",
          canon(v_exp.eligible) == canon(v_fast.eligible))
    # stale index for an older pin falls back to the cache
    stale = get_index(tlh, pin_h)
    stale.frontier -= 1  # simulate a behind-frontier holder
    v_stale = relquery.load(tlh, pin_h, live_h, index=stale)
    check("relview/stale-index-falls-back",
          canon(v_stale.eligible) == canon(v_fast.eligible))
    invalidate_rel_index(tlh)
finally:
    tlh.close()

# -- I. dossier lateral: adjacency == full-scan lateral ---------------
root_i, tli = fresh_store()
try:
    DOCS = [
        ("d-cat", "The domestic cat is a small carnivorous mammal. "
         "Cats purr when content."),
        ("d-dog", "The domestic dog is a loyal companion animal. "
         "Dogs bark to alert owners."),
        ("d-fuse", "An electrical fuse protects circuits from "
         "overcurrent. The fuse wire melts."),
    ]

    def _vec(text):
        t = text.lower()
        if any(w in t for w in ("cat", "dog", "animal", "purr",
                                "bark")):
            return [1.0, 0.0, 0.0, 0.0]
        if any(w in t for w in ("fuse", "current", "circuit",
                                "melt")):
            return [0.0, 1.0, 0.0, 0.0]
        return [0.0, 0.0, 1.0, 0.0]

    _emb = lambda ts: [_vec(t) for t in ts]  # noqa: E731
    _emb1 = lambda q: _vec(q)  # noqa: E731
    ingest_docs(tli, DOCS, _emb)
    idx_i0 = NarrowIndex(tli, tli.pin())
    iaids = {a["doc_id"]: aid
             for aid, a in idx_i0.atoms.items()}
    icat, idog, ifuse = (iaids["d-cat"], iaids["d-dog"],
                         iaids["d-fuse"])
    ir1 = make_record("relates",
                      [("source", icat), ("target", ifuse)],
                      {"negated": False}, CFG, PROPOSED,
                      [icat, ifuse])
    # duplicate-endpoint record: same atom under two roles must
    # still visit once per source (examined-count identity)
    ir2 = make_record("relates",
                      [("source", idog), ("target", ifuse),
                       ("witness", ifuse)],
                      {"negated": False}, CFG, PROPOSED, [idog])
    commit_relations(tli, [ir1, ir2])
    pin_i = tli.pin()
    idx_i = NarrowIndex(tli, pin_i)
    Q = "which animal purrs when content"
    TOPICS = ["which animal purrs when content",
              "fuse wire melts overcurrent"]

    def _run_all():
        nq = NarrowQuery(tli, idx_i, _emb1,
                         cfg={"REL_QUALIFIERS": True})
        dq_r = DossierQuery(tli, idx_i, _emb1,
                            cfg={"DOSSIER_SHAPE": "relational",
                                 "NARROW": {"REL_QUALIFIERS": True}})
        dq_x = DossierQuery(tli, idx_i, _emb1,
                            cfg={"DOSSIER_SHAPE": "cross-topic",
                                 "NARROW": {"REL_QUALIFIERS": True}})
        return [nq.run(Q), dq_r.run(Q), dq_x.run("x", topics=TOPICS)]

    invalidate_rel_index(tli)
    got_fast = _run_all()
    os.environ["TL_REL_ORACLE"] = "1"
    try:
        invalidate_rel_index(tli)
        got_orc = _run_all()
    finally:
        del os.environ["TL_REL_ORACLE"]
    for nm, f_, o_ in zip(("narrow-qual", "relational",
                           "cross-topic"), got_fast, got_orc):
        check(f"dossier/{nm}-eq-oracle",
              norm_run(f_) == norm_run(o_),
              nm)
    lat = got_fast[1][1]["metrics"]["dossier"]
    # All 3 fixture atoms are seeds, so lateral adds 0; traversal
    # over both committed relations must still have run (added>0
    # cases are covered at SciFact scale in round8 trackA).
    check("dossier/lateral-nonvacuous",
          lat["lateral_edges_examined"] >= 2, lat)
finally:
    tli.close()

# -- J. flag-OFF: zero relation calls + byte-identity -----------------
root_j, tlj = fresh_store()
try:
    ingest_docs(tlj, [("d1", "alpha one two three four"),
                      ("d2", "beta five six seven eight")], emb)
    pin_j0 = tlj.pin()
    idx_j0 = NarrowIndex(tlj, pin_j0)
    emb1j = lambda q: [1.0, 0.0, 0.0, 0.0]  # noqa: E731
    off_pre = NarrowQuery(tlj, idx_j0, emb1j, cfg={}).run("alpha")
    jaids = sorted(idx_j0.atoms.keys())
    commit_relations(tlj, [make_record(
        "supports", [("source", jaids[0]),
                     ("target", jaids[1])],
        {"negated": False}, CFG, PROPOSED, [jaids[0], jaids[1]])])
    pin_j1 = tlj.pin()
    idx_j1 = NarrowIndex(tlj, pin_j1)
    calls = []
    _saves = [(relquery, "load"),
              (dossier_mod, "read_relations"),
              (dossier_mod, "get_index"),
              (relations_mod, "read_relations"),
              (relations_mod, "get_index")]
    _origs = [(m, n, getattr(m, n)) for m, n in _saves]

    def _spy(name, fn):
        def _inner(*a, **k):
            calls.append(name)
            return fn(*a, **k)
        return _inner

    for m, n, fn in _origs:
        setattr(m, n, _spy(f"{m.__name__}.{n}", fn))
    try:
        invalidate_rel_index(tlj)
        off_post = NarrowQuery(tlj, idx_j1, emb1j, cfg={}).run(
            "alpha")
        dos_off = DossierQuery(tlj, idx_j1, emb1j,
                               cfg={}).run("alpha")
    finally:
        for m, n, fn in _origs:
            setattr(m, n, fn)
    check("off/zero-relation-calls", calls == [], calls)
    check("off/byte-identical-post-commit",
          norm_run(off_pre) == norm_run(off_post))
    check("off/dossier-narrow-delegates",
          canon(dos_off[0]) == canon(off_post[0]))
finally:
    tlj.close()

# -- K. invalidation + cross-store isolation --------------------------
root_k1, tlk1 = fresh_store(prefix="tl-relidx-k1-")
root_k2, tlk2 = fresh_store(prefix="tl-relidx-k2-")
try:
    ingest_docs(tlk1, [("d1", "alpha one")], emb)
    ingest_docs(tlk2, [("d1", "alpha one")], emb)
    pin_k1, pin_k2 = tlk1.pin(), tlk2.pin()
    invalidate_rel_index()
    read_relations(tlk1, pin_k1)
    read_relations(tlk2, pin_k2)
    check("cache/two-stores",
          len(relations_mod._INDEX_CACHE) == 2,
          len(relations_mod._INDEX_CACHE))
    invalidate_rel_index(tlk1)
    check("cache/invalidate-one-store",
          len(relations_mod._INDEX_CACHE) == 1,
          len(relations_mod._INDEX_CACHE))
    m1 = len(tlk2.trace.calls)
    read_relations(tlk2, pin_k2)
    check("cache/other-store-still-cached",
          tlk2.trace.calls[m1:] == [], tlk2.trace.calls[m1:])
    m2 = len(tlk1.trace.calls)
    read_relations(tlk1, pin_k1)
    ops = [c["op"] for c in tlk1.trace.calls[m2:]]
    check("cache/invalidated-store-rescans",
          "read_commits" in ops, ops)
    invalidate_rel_index()
    check("cache/invalidate-all",
          relations_mod._INDEX_CACHE == {})
finally:
    tlk1.close()
    tlk2.close()

print(f"done: {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
