"""R8-B navigation integration tests.

- Reader migration (R7-A proposal C adoption): place.read_xholons,
  index._build, maint._doc_vecs / reconcile_manifest use only the
  paginated + batched readers (read_commits_all / artifact_rows);
  min_seq windowing preserved; reconcile idempotent.
- Incremental audit (LiveAuditCache): O(1) reuse on unchanged views,
  exact recompute on version bump / structural change / search
  growth; same refusal/detection semantics as the per-call audit.
- Dense-atom HNSW leg: flag-off identity, discovery parity at k>=N,
  attach/detach + generation checks, unpublished handling.

Pure-python checks always run; HNSW checks need hnswlib==0.8.0
(/tmp/tl-r6d-pkgs fallback, as R7-B) and SKIP when truly absent.

Run: PYTHONPATH=/tmp/tl-r6d-pkgs tl-sys/.venv/bin/python \
       tl-sys/tests/test_r8b_nav.py
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
    HolonCandidateIndex, StaleGenerationError)
from tlsys.place import (  # noqa: E402
    LiveAuditCache, decide_with_search, read_xholons)
from tlsys.index import NarrowIndex  # noqa: E402
from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
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


def tiny_store(tmp, place_xdoc=True):
    root = os.path.join(tmp, "store")
    tl = TLStore(root, create=True, lease_owner="r8b-test")
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
                emb, store_id="r8b-test", place_xdoc=place_xdoc)
    return tl, emb


class FakeSearch:
    """coverage()/n/generation-compatible stub (no hnswlib)."""

    def __init__(self, indexed, generation="gen:0:1"):
        self._indexed = dict(indexed)
        self.n = len(indexed)
        self.generation = generation
        self.calls = 0

    def coverage(self, live):
        self.calls += 1
        live_ids = set(live.keys())
        indexed_ids = set(self._indexed.keys())
        stale = sorted(h for h in indexed_ids
                       if h not in live
                       or live[h].get("seq") != self._indexed[h])
        return {"indexed": len(indexed_ids), "live": len(live_ids),
                "stale": stale,
                "unpublished": sorted(live_ids - indexed_ids)}


def test_migration_adoption():
    tmp = tempfile.mkdtemp(prefix="tl-r8b-test-")
    tl, _emb = tiny_store(tmp)
    pinned = tl.pin()

    def _boom(*a, **k):
        raise AssertionError("singular reader used")

    tl.read_commits = _boom
    tl.artifact_row = _boom
    try:
        xh = read_xholons(tl, pinned)
        check("mig/xholons-no-singular-reads",
              isinstance(xh, dict) and len(xh) >= 1, repr(len(xh)))
        idx = NarrowIndex(tl, pinned)
        check("mig/build-no-singular-reads",
              len(idx.atoms) == 4 and len(idx.holons) >= 4,
              repr((len(idx.atoms), len(idx.holons))))
        pairs = _maint._doc_vecs(tl, "docA")
        check("mig/doc-vecs-no-singular-reads",
              len(pairs) == 1 and pairs[0][0] is not None,
              repr(pairs))
        rep = _maint.reconcile_manifest(tl)
        check("mig/reconcile-no-singular-reads",
              sorted(rep.keys()) == ["pending_placement",
                                     "recovered_docs", "repaired_ops"],
              repr(rep))
    finally:
        tl.close()


def test_migration_semantics():
    tmp = tempfile.mkdtemp(prefix="tl-r8b-test-")
    tl, _emb = tiny_store(tmp)
    pinned = tl.pin()
    full = read_xholons(tl, pinned)
    check("mig/xholons-nonempty", len(full) >= 1, repr(len(full)))
    mx = max(v["seq"] for v in full.values())
    win = read_xholons(tl, pinned, min_seq=mx)
    check("mig/min-seq-window-excludes",
          all(v["seq"] > mx or k not in win for k, v in full.items())
          and len(win) <= len(full), repr((len(full), len(win))))
    # Incremental merge over seq frontiers equals the full read.
    mid = sorted(v["seq"] for v in full.values())[len(full) // 2]
    lo = read_xholons(tl, pinned, min_seq=0)
    lo = {k: v for k, v in lo.items() if v["seq"] <= mid}
    hi = read_xholons(tl, pinned, min_seq=mid)
    merged = dict(lo)
    merged.update(hi)
    check("mig/min-seq-merge-equals-full", merged == full,
          repr((len(merged), len(full))))
    try:
        _maint._doc_vecs(tl, "doc-missing")
        check("mig/doc-vecs-fail-closed", False, "no raise")
    except RuntimeError:
        check("mig/doc-vecs-fail-closed", True)
    _r1 = _maint.reconcile_manifest(tl)
    r2 = _maint.reconcile_manifest(tl)
    r3 = _maint.reconcile_manifest(tl)
    check("mig/reconcile-idempotent",
          r2 == r3 and r3["repaired_ops"] == 0, repr((r2, r3)))
    tl.close()


def test_audit_cache_pure():
    live = {f"h{i}": {"seq": i} for i in range(10)}
    s = FakeSearch({f"h{i}": i for i in range(10)})
    c = LiveAuditCache()
    a1, hit1 = c.audit(s, live, 1)
    a2, hit2 = c.audit(s, live, 1)
    check("audit/hit-on-unchanged",
          hit1 is False and hit2 is True and a2 is a1
          and s.calls == 1, repr((hit1, hit2, s.calls)))
    # Interior seq edit + version bump -> recompute + stale detected.
    live["h3"] = {"seq": 999}
    a3, hit3 = c.audit(s, live, 2)
    check("audit/bump-recomputes-stale",
          hit3 is False and a3["stale"] == ["h3"] and s.calls == 2,
          repr(a3))
    # Structural add WITHOUT a bump -> fingerprint still recomputes.
    live["h-new"] = {"seq": 1}
    a4, hit4 = c.audit(s, live, 2)
    check("audit/add-without-bump-recomputes",
          hit4 is False and a4["unpublished"] == ["h-new"]
          and s.calls == 3, repr(a4))
    # Structural remove WITHOUT a bump -> recomputes.
    del live["h-new"]
    del live["h9"]
    a5, hit5 = c.audit(s, live, 2)
    check("audit/remove-without-bump-recomputes",
          hit5 is False and "h9" in a5["stale"] and s.calls == 4,
          repr(a5))
    # Search growth (add) -> recomputes via population size.
    s._indexed["h9"] = 9
    s.n = 11
    _a6, hit6 = c.audit(s, live, 2)
    check("audit/search-growth-recomputes",
          hit6 is False and s.calls == 5, repr(hit6))
    # Same content, different live object -> recomputes (no aliasing).
    live2 = {h: dict(v) for h, v in live.items()}
    _a7, hit7 = c.audit(s, live2, 2)
    check("audit/new-live-object-recomputes",
          hit7 is False and s.calls == 6, repr(hit7))
    c.invalidate()
    _a8, hit8 = c.audit(s, live2, 2)
    check("audit/invalidate-recomputes",
          hit8 is False and s.calls == 7, repr(hit8))
    e = LiveAuditCache()
    ea, ehit = e.audit(s, {}, 0)
    check("audit/empty-live",
          ehit is False and ea["live"] == 0
          and ea["unpublished"] == [], repr(ea))


def _atom_search_for(idx, pinned, drop=()):
    return HolonCandidateIndex().build(
        {a: {"descriptor": list(np.asarray(v["descriptor"],
                                          dtype=np.float64)),
             "seq": v["seq"]}
         for a, v in idx.atoms.items() if a not in drop},
        pinned[3])


def _holon_search_for(idx, pinned):
    return HolonCandidateIndex().build(
        {h: {"descriptor": list(np.asarray(v["descriptor"],
                                          dtype=np.float64)),
             "seq": v["seq"]} for h, v in idx.holons.items()},
        pinned[3])


def test_atoms_search_leg():
    tmp = tempfile.mkdtemp(prefix="tl-r8b-test-")
    tl, _emb = tiny_store(tmp)
    pinned = tl.pin()
    idx = NarrowIndex(tl, pinned)
    qv = [1.0, 0.0, 0.0, 0.0]
    a = idx.dense_atoms(qv)
    b = idx.dense_atoms(qv, candidate_search=None)
    check("atoms/off-identical", a == b, repr((a, b)))
    check("atoms/off-no-report", idx.last_atom_candidate_report is None)
    if not HAVE_HNSW:
        skip("atoms/search", "hnswlib absent")
        tl.close()
        return
    s = _atom_search_for(idx, pinned)
    c = idx.dense_atoms(qv, candidate_search=s,
                        candidate_k=len(idx.atoms))
    check("atoms/search-k-ge-n-identical", c == a, repr((c, a)))
    rep = idx.last_atom_candidate_report
    check("atoms/report-populated",
          rep is not None and rep["rescored"] == len(a)
          and rep["stale_dropped"] == []
          and rep["unpublished"] == []
          and rep["audit_cached"] is False, repr(rep))
    # Repeat call reuses the audit (same search, same live, same
    # version): identical ranking, cached flag set.
    c2 = idx.dense_atoms(qv, candidate_search=s,
                         candidate_k=len(idx.atoms))
    rep2 = idx.last_atom_candidate_report
    check("atoms/audit-cached-on-repeat",
          c2 == a and rep2["audit_cached"] is True, repr(rep2))
    # Attached search flows; explicit None forces exact when attached.
    idx.attach_atom_search(s)
    d = idx.dense_atoms(qv, candidate_k=len(idx.atoms))
    check("atoms/attached-flows", d == a, repr(d))
    e = idx.dense_atoms(qv, candidate_search=None)
    check("atoms/explicit-none-forces-exact", e == a, repr(e))
    idx.detach_atom_search()
    check("atoms/detached-restores-exact",
          idx.dense_atoms(qv) == a
          and idx.last_atom_candidate_report is None)
    # Unpublished atom: unioned by default, skipped when off.
    drop_aid = a[0][0]
    s2 = _atom_search_for(idx, pinned, drop=(drop_aid,))
    got_on = idx.dense_atoms(qv, candidate_search=s2,
                             candidate_k=len(idx.atoms))
    rep_on = idx.last_atom_candidate_report
    got_off = idx.dense_atoms(qv, candidate_search=s2,
                              candidate_k=len(idx.atoms),
                              include_unpublished=False)
    rep_off = idx.last_atom_candidate_report
    check("atoms/unpublished-unioned-by-default",
          [x[0] for x in got_on] == [x[0] for x in a]
          and rep_on["unpublished"] == [drop_aid],
          repr((got_on, rep_on["unpublished"])))
    check("atoms/unpublished-skipped-when-off",
          drop_aid not in [x[0] for x in got_off]
          and rep_off["unpublished"] == [drop_aid],
          repr(got_off))
    # Generation mismatch refuses at attach and at call time.
    other = HolonCandidateIndex().build(
        {"h": {"descriptor": [1.0, 0.0, 0.0, 0.0], "seq": 1}},
        "other:0:0")
    try:
        idx.attach_atom_search(other)
        check("atoms/attach-generation-refused", False, "no raise")
    except StaleGenerationError:
        check("atoms/attach-generation-refused", True)
    try:
        idx.dense_atoms(qv, candidate_search=other)
        check("atoms/call-generation-refused", False, "no raise")
    except StaleGenerationError:
        check("atoms/call-generation-refused", True)
    tl.close()


def test_holons_audit_cached():
    if not HAVE_HNSW:
        skip("holons/audit", "hnswlib absent")
        return
    tmp = tempfile.mkdtemp(prefix="tl-r8b-test-")
    tl, _emb = tiny_store(tmp)
    pinned = tl.pin()
    idx = NarrowIndex(tl, pinned)
    s = _holon_search_for(idx, pinned)
    qv = [1.0, 0.0, 0.0, 0.0]
    exact = idx.dense_holons(qv)
    idx.attach_candidate_search(s)
    r1 = idx.dense_holons(qv, candidate_k=len(idx.holons))
    rep1 = idx.last_candidate_report
    r2 = idx.dense_holons(qv, candidate_k=len(idx.holons))
    rep2 = idx.last_candidate_report
    check("holons/audit-cache-agreement",
          r1 == exact and r2 == exact
          and rep1["audit_cached"] is False
          and rep2["audit_cached"] is True,
          repr((rep1["audit_cached"], rep2["audit_cached"])))
    # Structural add without a bump is still detected (fingerprint).
    idx.holons["docFRESH"] = {"seq": 9999, "op_id": "x",
                              "members": ["aX"],
                              "descriptor": np.array(
                                  [1.0, 0.0, 0.0, 0.0])}
    idx.dense_holons(qv, candidate_k=len(idx.holons))
    rep3 = idx.last_candidate_report
    check("holons/add-without-bump-detected",
          rep3["audit_cached"] is False
          and rep3["unpublished"] == ["docFRESH"], repr(rep3))
    del idx.holons["docFRESH"]
    idx.note_population_changed("holons")
    idx.dense_holons(qv, candidate_k=len(idx.holons))
    rep4 = idx.last_candidate_report
    check("holons/bump-restores-clean-audit",
          rep4["audit_cached"] is False
          and rep4["unpublished"] == [], repr(rep4))
    try:
        idx.note_population_changed("bogus")
        check("holons/note-bad-which-raises", False, "no raise")
    except ValueError:
        check("holons/note-bad-which-raises", True)
    tl.close()


def test_place_audit_cached():
    if not HAVE_HNSW:
        skip("place/audit", "hnswlib absent")
        return
    rng = np.random.RandomState(21)
    pop = {f"xdoc-h{i:03d}":
           {"descriptor": [float(x) for x in rng.randn(16)],
            "seq": 100 + i, "members": [f"m{i}"]}
           for i in range(120)}
    s = HolonCandidateIndex().build(pop, "gen:0:1")
    q = [float(x) for x in rng.randn(16)]
    cache = LiveAuditCache()
    g1, r1 = decide_with_search(q, pop, s, k=40,
                                generation="gen:0:1",
                                live_version=1, audit_cache=cache)
    g2, r2 = decide_with_search(q, pop, s, k=40,
                                generation="gen:0:1",
                                live_version=1, audit_cache=cache)
    g0, r0 = decide_with_search(q, pop, s, k=40,
                                generation="gen:0:1")
    check("place/audit-cache-agreement",
          g1 == g2 == g0 and r1["audit_cached"] is False
          and r2["audit_cached"] is True
          and r0["audit_cached"] is False,
          repr((r1["audit_cached"], r2["audit_cached"])))
    # Unpublished live holon detected through the cached path.
    live = dict(pop)
    live["xdoc-fresh"] = {"descriptor": list(q), "seq": 777,
                          "members": ["a1"]}
    g3, r3 = decide_with_search(q, live, s, k=40,
                                generation="gen:0:1",
                                live_version=1, audit_cache=cache)
    check("place/cached-path-detects-unpublished",
          "xdoc-fresh" in g3
          and r3["unpublished"] == ["xdoc-fresh"]
          and r3["audit_cached"] is False, repr(r3))
    try:
        decide_with_search(q, pop, s, k=40, generation="gen:0:9",
                           live_version=1, audit_cache=cache)
        check("place/cached-path-refuses-generation", False,
              "no raise")
    except StaleGenerationError:
        check("place/cached-path-refuses-generation", True)


def test_qpath_with_searches_attached():
    tmp = tempfile.mkdtemp(prefix="tl-r8b-qpath-")
    tl, _emb = tiny_store(tmp)
    pinned = tl.pin()

    def emb1(q):
        return [1.0, 0.0, 0.0, 0.0]

    idx_exact = NarrowIndex(tl, pinned)
    dos_e, rec_e = NarrowQuery(tl, idx_exact, emb1).run("alpha")
    if not HAVE_HNSW:
        skip("qpath/searches", "hnswlib absent")
        tl.close()
        return
    idx_h = NarrowIndex(tl, pinned,
                        candidate_search=_holon_search_for(
                            idx_exact, pinned),
                        atom_candidate_search=_atom_search_for(
                            idx_exact, pinned))
    dos_h, rec_h = NarrowQuery(tl, idx_h, emb1).run("alpha")
    check("qpath/both-searches-entries-identical", dos_h == dos_e,
          repr((dos_h, dos_e)))
    me = dict(rec_e["metrics"])
    mh = dict(rec_h["metrics"])
    me.pop("T_ms", None)
    mh.pop("T_ms", None)
    check("qpath/both-searches-receipt-identical", mh == me,
          repr((mh, me)))
    tl.close()


def main():
    test_migration_adoption()
    test_migration_semantics()
    test_audit_cache_pure()
    test_atoms_search_leg()
    test_holons_audit_cached()
    test_place_audit_cached()
    test_qpath_with_searches_attached()
    print(f"{len(FAILS)} failures, {len(SKIPS)} skips")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
