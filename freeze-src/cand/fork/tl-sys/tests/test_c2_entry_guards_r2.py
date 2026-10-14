"""C2 Lane R-2: production entry-point wiring guards + entry differentials.

Proves RelServe/HierServe execute on the REAL query/dossier paths
(NarrowQuery/DossierQuery.run -- the gate's entry points), not just in
helper tests, with exact parity to the legacy path:

- Guards (failing-first: FAIL on arrived code where the legacy global
  path runs, PASS after R-2 wiring): spy-blocked legacy calls
  (_relquery.load, idx.live_atom_set, dossier.read_relations/get_index/
  eligible, whole-atoms iteration) must not fire on the wired path;
  backend tags must read "relserve"/"hierserve"; the held HierServe
  must be reused across runs.
- Entry differentials (PASS before and after: on arrived code both
  arms are legacy; after wiring they compare wired vs legacy through
  the same entry points): narrow+REL flags, relational,
  relational+traversal, cross-topic, HIER_GUIDED sidecar, plus a
  retirement pin and a cross-backend (facade vs reference) arm.

Deterministic fake encoder; scratch stores under /tmp.
Run: tl-sys/.venv/bin/python tl-sys/tests/test_c2_entry_guards_r2.py
"""
import contextlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))

from tlsys.store_if import TLStore  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.index import ReferenceNarrowIndex, NarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys.relations import PROPOSED, commit_relations  # noqa: E402
from tlsys.relations import make_record  # noqa: E402
from tlsys.maint import organize_segments  # noqa: E402
from tlsys.lifecycle import retire_docs  # noqa: E402
from tlsys import relquery  # noqa: E402
from tlsys import query as _query_mod  # noqa: E402
from tlsys import dossier as _dossier_mod  # noqa: E402

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
    """Normalize runs for comparison (wall clocks only)."""
    def _walk(o):
        if isinstance(o, dict):
            return {k: (-1.0 if k in ("T_ms", "ms", "wall_ms") else _walk(v))
                    for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_walk(v) for v in o]
        return o
    return _walk(obj)


DIMS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
        "sport", "medic"]


def vec(text):
    t = text.lower()
    out = [1.0 if w in t else 0.0 for w in DIMS]
    if not any(out):
        return [0.2] * len(DIMS)
    return out


def emb(texts):
    return [vec(t) for t in texts]


def emb1(q):
    return vec(q)


CFG = {"extractor": "test-r2-v1", "window": 1,
       "model": "none", "rules": ["r2"]}
DEAD = "de" * 32

DOCS = [
    ("d0", "alpha norms govern the alpha baseline completely."),
    ("d1", "bravo rules handle the bravo cases entirely."),
    ("d2", "charlie axioms cover the charlie domain fully."),
    ("d3", "delta statutes span the delta regime wholly."),
    ("d4", "echo remarks touch sundry matters lightly."),
    ("d5", "foxtrot clauses bind the foxtrot parties duly."),
    ("d6", "zebra quixotic jargon with no relation anywhere."),
]


def run_of(word, n, start=0):
    return " ".join(f"{word}-{i}" for i in range(start, start + n))


HIER_DOCS = [
    ("h0", " ".join([run_of("sport", 100, 0), run_of("medic", 100, 0)])),
    ("h1", run_of("sport", 100, 5000)),
]


@contextlib.contextmanager
def _env(**kw):
    """Temporarily set (value None = unset) env vars; always restore."""
    saved = {k: os.environ.get(k) for k in kw}
    try:
        for k, v in kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def _patched(obj, name, new):
    old = getattr(obj, name)
    setattr(obj, name, new)
    try:
        yield
    finally:
        setattr(obj, name, old)


def _raising(name):
    def _boom(*a, **k):
        raise AssertionError(f"legacy call fired on wired path: {name}")
    return _boom


class _NoIterAtoms:
    """Atoms mapping refusing whole-population traversal (keyed OK)."""

    def __init__(self, inner):
        self._inner = inner

    def get(self, *a, **k):
        return self._inner.get(*a, **k)

    def __getitem__(self, key):
        return self._inner[key]

    def __contains__(self, key):
        return key in self._inner

    def __len__(self):
        return len(self._inner)

    def __iter__(self):
        raise AssertionError("legacy set(idx.atoms) iteration fired")

    def keys(self):
        raise AssertionError("legacy atoms.keys() fired")

    def items(self):
        raise AssertionError("legacy atoms.items() fired")

    def values(self):
        raise AssertionError("legacy atoms.values() fired")


REL_CFG = {"REL_HUB_SUPPRESS": True, "REL_QUALIFIERS": True}
Q_REL = "delta foxtrot scope as-stated"
Q_HIER = "sport athletics"


def _invalidate_caches():
    relquery.invalidate_rel_view()
    inv = getattr(_query_mod, "invalidate_rel_serve", None)
    if inv is not None:
        inv()


root = tempfile.mkdtemp(prefix="tl-r2-")
tl = TLStore(os.path.join(root, "store"), create=True,
             lease_owner="test-c2-r2")
# Pinned clean control env for every arm below (inner _env blocks
# flip single vars; the outer session env is restored in finally).
_SAVED_ENV = {k: os.environ.get(k) for k in (
    "TL_REL_ORACLE", "TL_REL_AUDIT", "TL_C2_RELSERVE",
    "TL_C2_HIERSERVE")}
for _k in _SAVED_ENV:
    os.environ.pop(_k, None)
try:
    rep = ingest_docs(tl, DOCS + HIER_DOCS, emb)
    check("ingest/atoms", rep["n_atoms"] == 9, rep)
    org = organize_segments(tl)
    check("ingest/organized", "h0" in org["organized"], org)
    pin0 = tl.pin()
    idx0 = NarrowIndex(tl, pin0)
    aids = {a["doc_id"]: aid for aid, a in idx0.atoms.items()}
    check("ingest/nine-atoms", len(aids) == 9, sorted(aids))
    a0, a1, a2 = aids["d0"], aids["d1"], aids["d2"]
    a3, a4, a5 = aids["d3"], aids["d4"], aids["d5"]
    a6 = aids["d6"]

    batch = [
        make_record("links", [("src", a0), ("dst", a1)],
                    {"negated": False, "claim": "c01"}, CFG,
                    PROPOSED, [a0, a1]),
        make_record("links", [("src", a1), ("dst", a2)],
                    {"negated": True, "claim": "c12",
                     "unresolved": "r2-ambig"}, CFG,
                    PROPOSED, [a1, a2]),
        make_record("links", [("src", a2), ("dst", a3)],
                    {"negated": False, "claim": "c23"}, CFG,
                    PROPOSED, [a2, a3]),
        make_record("evidences", [("claim", a3), ("context", a0)],
                    {"negated": False, "scope": "as-stated"},
                    CFG, PROPOSED, [a3, a0]),
        make_record("evidences", [("claim", a5), ("context", a0)],
                    {"negated": True, "scope": "as-stated"},
                    CFG, PROPOSED, [a5, a0]),
        make_record("links", [("src", a0), ("dst", DEAD)],
                    {"negated": False}, CFG, PROPOSED, [a0]),
    ]
    sigs = [relquery.make_qual_signal(
                a3, {"topic": "T", "negated": False}, CFG),
            relquery.make_qual_signal(a4, {"negated": True}, CFG)]
    commit_relations(tl, batch)
    relquery.commit_qual_signals(tl, sigs)
    pin1 = tl.pin()
    ref1 = ReferenceNarrowIndex(tl, pin1)
    fac1 = NarrowIndex(tl, pin1)
    check("harness/facade-is-c2",
          fac1.serve_counters().get("backend") == "c2",
          fac1.serve_counters())
    check("harness/hierarchy",
          len(ref1.seg_leaves) > 0 and len(ref1.seg_parents) > 0,
          (len(ref1.seg_leaves), len(ref1.seg_parents)))

    # -- guards: Narrow REL path serves via RelServe ---------------
    # Spy-block the legacy global calls: the wired entry must not
    # fire them (arrived code fires them -> these FAIL pre-wiring).
    for tag, index in (("ref", ref1), ("fac", fac1)):
        _invalidate_caches()
        nq = NarrowQuery(tl, index, emb1, cfg=dict(REL_CFG))
        try:
            with _patched(relquery, "load", _raising("relquery.load")):
                dos_w, rec_w = nq.run(Q_REL)
            blocked_ok = True
        except AssertionError as e:
            blocked_ok, dos_w, rec_w = False, None, None
            detail = str(e)
        check(f"guard/{tag}/narrow-no-relquery-load", blocked_ok,
              detail if not blocked_ok else "")
        check(f"guard/{tag}/narrow-backend-relserve",
              getattr(nq, "last_rel_backend", None) == "relserve",
              getattr(nq, "last_rel_backend", None))

    for tag, index in (("ref", ref1), ("fac", fac1)):
        _invalidate_caches()
        nq = NarrowQuery(tl, index, emb1, cfg=dict(REL_CFG))
        with _env(TL_C2_RELSERVE=None):
            had = "live_atom_set" in index.__dict__
            old = index.__dict__.get("live_atom_set")
            index.live_atom_set = _raising("live_atom_set")
            try:
                dos_w, rec_w = nq.run(Q_REL)
                noset_ok = True
            except AssertionError as e:
                noset_ok, detail = False, str(e)
            finally:
                if had:
                    index.live_atom_set = old
                else:
                    del index.live_atom_set
        check(f"guard/{tag}/narrow-no-live-set", noset_ok,
              detail if not noset_ok else "")

    # Serve-cache reuse across entry instances at the same pin (the
    # wired path keeps the M1-D cross-instance amortization).
    _invalidate_caches()
    cache_fn = getattr(_query_mod, "_rel_serve_for", None)
    if cache_fn is None:
        check("guard/serve-cache-reuse", False,
              "query._rel_serve_for missing (unwired)")
        check("guard/serve-cache-invalidate", False,
              "query.invalidate_rel_serve missing (unwired)")
    else:
        s_a = cache_fn(tl, fac1, pin1)
        s_b = cache_fn(tl, fac1, pin1)
        check("guard/serve-cache-reuse", s_a is s_b, (s_a, s_b))
        _query_mod.invalidate_rel_serve()
        s_c = cache_fn(tl, fac1, pin1)
        check("guard/serve-cache-invalidate", s_c is not s_a,
              "invalidate did not drop the cached serve")
        check("guard/serve-cache-info",
              _query_mod.rel_serve_cache_info().get("size") == 1,
              _query_mod.rel_serve_cache_info())

    # -- guards: dossier lateral/traversal serve via RelServe -----
    for tag, index in (("ref", ref1), ("fac", fac1)):
        _invalidate_caches()
        dq = DossierQuery(tl, index, emb1,
                          cfg={"DOSSIER_SHAPE": "cross-topic"})
        try:
            with _patched(_dossier_mod, "read_relations",
                          _raising("dossier.read_relations")), \
                 _patched(_dossier_mod, "get_index",
                          _raising("dossier.get_index")), \
                 _patched(_dossier_mod, "eligible",
                          _raising("dossier.eligible")):
                dos_w, rec_w = dq.run(
                    "alpha bravo", topics=["alpha", "bravo foxtrot"])
            lat_ok = True
        except AssertionError as e:
            lat_ok, detail = False, str(e)
        check(f"guard/{tag}/dossier-lateral-wired", lat_ok,
              detail if not lat_ok else "")
        check(f"guard/{tag}/dossier-backend-relserve",
              getattr(dq, "last_rel_backend", None) == "relserve",
              getattr(dq, "last_rel_backend", None))

    # Direct _lateral leg with whole-atoms iteration refused: the
    # wired leg probes liveness (legacy set(idx.atoms) raises).
    for tag, index in (("ref", ref1), ("fac", fac1)):
        _invalidate_caches()
        from tlsys.query import WorkBudget  # noqa: E402
        guarded = (ReferenceNarrowIndex if tag == "ref"
                   else NarrowIndex)(tl, pin1)
        guarded.atoms = _NoIterAtoms(guarded.atoms)
        dq = DossierQuery(tl, guarded, emb1,
                          cfg={"DOSSIER_SHAPE": "cross-topic"})
        budget = WorkBudget()
        entries = [{"atom_id": a0}]
        try:
            out = dq._lateral(pin1, pin1[3], budget, entries, {a0},
                              [], [({a0}, {a0}, 0.5, True)], False)
            noiter_ok = True
        except AssertionError as e:
            noiter_ok, detail = False, str(e)
        check(f"guard/{tag}/dossier-lateral-no-atom-iter", noiter_ok,
              detail if not noiter_ok else "")

    for tag, index in (("ref", ref1), ("fac", fac1)):
        _invalidate_caches()
        dq = DossierQuery(tl, index, emb1,
                          cfg={"DOSSIER_SHAPE": "relational",
                               "DOSSIER_REL_TRAVERSAL": True,
                               "DOSSIER_REL_HOPS": 1})
        try:
            with _patched(_dossier_mod, "get_index",
                          _raising("dossier.get_index")), \
                 _patched(_dossier_mod, "read_relations",
                          _raising("dossier.read_relations")):
                dos_w, rec_w = dq.run("alpha bravo")
            trav_ok = True
        except AssertionError as e:
            trav_ok, detail = False, str(e)
        check(f"guard/{tag}/dossier-traverse-wired", trav_ok,
              detail if not trav_ok else "")

    # -- guards: HIER_GUIDED leg serves via held HierServe --------
    for tag, index in (("ref", ref1), ("fac", fac1)):
        _invalidate_caches()
        nq = NarrowQuery(tl, index, emb1, cfg={"HIER_GUIDED": True})
        with _env(TL_C2_HIERSERVE=None):
            dos_h, rec_h = nq.run(Q_HIER)
            held = getattr(nq, "_hierserve", None)
            check(f"guard/{tag}/hier-held-serve", held is not None,
                  "no held HierServe (unwired)")
            if held is not None:
                dos_h2, rec_h2 = nq.run(Q_HIER)
                check(f"guard/{tag}/hier-serve-reused",
                      nq._hierserve is held and held._calls == 2,
                      getattr(held, "_calls", None))
                from tlsys.hierserve import FACADE_ATTRS  # noqa: E402
                check(f"guard/{tag}/hier-facade-only",
                      held.touched_surface() <= FACADE_ATTRS,
                      held.touched_surface() - FACADE_ATTRS)
                check(f"guard/{tag}/hier-backend-tag",
                      getattr(nq, "last_hier_backend", None)
                      == "hierserve",
                      getattr(nq, "last_hier_backend", None))

    # -- guards: explicit opt-out flags route to legacy ---------
    for tag, index in (("ref", ref1), ("fac", fac1)):
        try:
            nq = NarrowQuery(
                tl, index, emb1,
                cfg={"REL_HUB_SUPPRESS": True,
                     "RELSERVE_WIRED": False})
            with _env(TL_C2_RELSERVE=None):
                nq.run(Q_REL)
            cfg_ok = (getattr(nq, "last_rel_backend", None)
                      == "relquery")
            detail = getattr(nq, "last_rel_backend", None)
        except ValueError as e:
            cfg_ok, detail = False, str(e)
        check(f"guard/{tag}/cfg-relserve-off", cfg_ok, detail)
        try:
            dq = DossierQuery(
                tl, index, emb1,
                cfg={"DOSSIER_SHAPE": "cross-topic",
                     "RELSERVE_WIRED": False})
            with _env(TL_C2_RELSERVE=None):
                dq.run("alpha bravo", topics=["alpha"])
            dcfg_ok = (getattr(dq, "last_rel_backend", None)
                       == "relquery")
            detail = getattr(dq, "last_rel_backend", None)
        except ValueError as e:
            dcfg_ok, detail = False, str(e)
        check(f"guard/{tag}/cfg-dossier-relserve-off", dcfg_ok,
              detail)
        try:
            nq = NarrowQuery(tl, index, emb1,
                             cfg={"HIER_GUIDED": True,
                                  "HIERSERVE_WIRED": False})
            with _env(TL_C2_HIERSERVE=None):
                nq.run(Q_HIER)
            hcfg_ok = (getattr(nq, "last_hier_backend", None)
                       == "hierquery")
            detail = getattr(nq, "last_hier_backend", None)
        except ValueError as e:
            hcfg_ok, detail = False, str(e)
        check(f"guard/{tag}/cfg-hierserve-off", hcfg_ok, detail)

    # Oracle/audit conformance modes force the legacy path (and
    # stay output-identical: fullscan == indexed by contract).
    for tag, index in (("ref", ref1), ("fac", fac1)):
        _invalidate_caches()
        with _env(TL_C2_RELSERVE=None, TL_REL_ORACLE="1",
                  TL_REL_AUDIT=None):
            nq = NarrowQuery(tl, index, emb1, cfg=dict(REL_CFG))
            dos_o, rec_o = nq.run(Q_REL)
        check(f"guard/{tag}/oracle-forces-legacy",
              getattr(nq, "last_rel_backend", None) == "relquery",
              getattr(nq, "last_rel_backend", None))
        _invalidate_caches()
        with _env(TL_C2_RELSERVE=None, TL_REL_ORACLE=None,
                  TL_REL_AUDIT=None):
            nq2 = NarrowQuery(tl, index, emb1, cfg=dict(REL_CFG))
            dos_d, rec_d = nq2.run(Q_REL)
        check(f"parity/{tag}/oracle-output-equal",
              norm_run((dos_o, rec_o)) == norm_run((dos_d, rec_d)),
              "oracle run diverges from default run")

    # -- entry differentials: wired vs legacy, same entry -------
    # Env flip: TL_C2_RELSERVE=0 forces legacy. On arrived code the
    # env is ignored (both arms legacy -> equal); after wiring this
    # is the wired-vs-legacy entry differential.
    def _narrow_pair(index, cfg, q):
        _invalidate_caches()
        with _env(TL_C2_RELSERVE=None, TL_REL_ORACLE=None,
                  TL_REL_AUDIT=None):
            d1, r1 = NarrowQuery(
                tl, index, emb1, cfg=dict(cfg)).run(q)
        _invalidate_caches()
        with _env(TL_C2_RELSERVE="0", TL_REL_ORACLE=None,
                  TL_REL_AUDIT=None):
            d0, r0 = NarrowQuery(
                tl, index, emb1, cfg=dict(cfg)).run(q)
        return d1, r1, d0, r0

    def _dossier_pair(index, cfg, q, topics=None):
        _invalidate_caches()
        with _env(TL_C2_RELSERVE=None, TL_REL_ORACLE=None,
                  TL_REL_AUDIT=None):
            d1, r1 = DossierQuery(
                tl, index, emb1, cfg=dict(cfg)).run(q, topics=topics)
        _invalidate_caches()
        with _env(TL_C2_RELSERVE="0", TL_REL_ORACLE=None,
                  TL_REL_AUDIT=None):
            d0, r0 = DossierQuery(
                tl, index, emb1, cfg=dict(cfg)).run(q, topics=topics)
        return d1, r1, d0, r0

    for tag, index in (("ref", ref1), ("fac", fac1)):
        d1, r1, d0, r0 = _narrow_pair(index, REL_CFG, Q_REL)
        check(f"parity/{tag}/narrow-rel-hubqual",
              norm_run((d1, r1)) == norm_run((d0, r0)),
              "wired narrow REL run diverges from legacy")
        d1, r1, d0, r0 = _narrow_pair(
            index, {"REL_HUB_SUPPRESS": True}, "alpha bravo-links")
        check(f"parity/{tag}/narrow-rel-hubonly",
              norm_run((d1, r1)) == norm_run((d0, r0)),
              "wired hub-only run diverges from legacy")
        d1, r1, d0, r0 = _dossier_pair(
            index, {"DOSSIER_SHAPE": "relational"}, "alpha bravo")
        check(f"parity/{tag}/dossier-relational",
              norm_run((d1, r1)) == norm_run((d0, r0)),
              "wired relational dossier diverges from legacy")
        d1, r1, d0, r0 = _dossier_pair(
            index, {"DOSSIER_SHAPE": "relational",
                    "DOSSIER_REL_TRAVERSAL": True,
                    "DOSSIER_REL_HOPS": 1}, "alpha bravo")
        check(f"parity/{tag}/dossier-relational-traversal",
              norm_run((d1, r1)) == norm_run((d0, r0)),
              "wired traversal dossier diverges from legacy")
        d1, r1, d0, r0 = _dossier_pair(
            index, {"DOSSIER_SHAPE": "cross-topic"}, "alpha bravo",
            topics=["alpha", "bravo foxtrot"])
        check(f"parity/{tag}/dossier-cross-topic",
              norm_run((d1, r1)) == norm_run((d0, r0)),
              "wired cross-topic dossier diverges from legacy")

    # Direct _lateral leg differential (entries + return tuple).
    for tag, index in (("ref", ref1), ("fac", fac1)):
        from tlsys.query import WorkBudget  # noqa: E402
        outs = []
        for env in (None, "0"):
            _invalidate_caches()
            with _env(TL_C2_RELSERVE=env, TL_REL_ORACLE=None,
                      TL_REL_AUDIT=None):
                dq = DossierQuery(
                    tl, index, emb1,
                    cfg={"DOSSIER_SHAPE": "cross-topic"})
                budget = WorkBudget()
                entries = [{"atom_id": a0}]
                ret = dq._lateral(
                    pin1, pin1[3], budget, entries, {a0}, [],
                    [({a0}, {a0}, 0.5, True)], False)
                outs.append((ret, entries, budget.used,
                             dict(budget.counts)))
        check(f"parity/{tag}/dossier-lateral-direct",
              norm_run(outs[0]) == norm_run(outs[1]),
              f"{outs[0]} != {outs[1]}")

    # HIER_GUIDED sidecar differential (exact + bounded arms).
    for hier_cfg, arm in (({"HIER_GUIDED": True}, "exact"),
                         ({"HIER_GUIDED": True,
                            "HIER_PARENT_BUDGET": 2}, "bounded")):
        for tag, index in (("ref", ref1), ("fac", fac1)):
            _invalidate_caches()
            with _env(TL_C2_HIERSERVE=None, TL_REL_ORACLE=None,
                      TL_REL_AUDIT=None):
                d1, r1 = NarrowQuery(
                    tl, index, emb1, cfg=dict(hier_cfg)).run(Q_HIER)
            _invalidate_caches()
            with _env(TL_C2_HIERSERVE="0", TL_REL_ORACLE=None,
                      TL_REL_AUDIT=None):
                d0, r0 = NarrowQuery(
                    tl, index, emb1, cfg=dict(hier_cfg)).run(Q_HIER)
            check(f"parity/{tag}/hier-sidecar-{arm}",
                  norm_run((d1, r1)) == norm_run((d0, r0)),
                  "wired hier sidecar diverges from legacy")

    # Cross-backend entry parity (facade vs reference, wired arm).
    with _env(TL_C2_RELSERVE=None, TL_C2_HIERSERVE=None,
              TL_REL_ORACLE=None, TL_REL_AUDIT=None):
        _invalidate_caches()
        df, rf = NarrowQuery(
            tl, fac1, emb1, cfg=dict(REL_CFG)).run(Q_REL)
        _invalidate_caches()
        dr, rr = NarrowQuery(
            tl, ref1, emb1, cfg=dict(REL_CFG)).run(Q_REL)
        check("parity/xbackend/narrow-rel",
              norm_run((df, rf)) == norm_run((dr, rr)),
              "narrow REL facade vs reference diverge")
        _invalidate_caches()
        df, rf = DossierQuery(
            tl, fac1, emb1,
            cfg={"DOSSIER_SHAPE": "relational"}).run("alpha bravo")
        _invalidate_caches()
        dr, rr = DossierQuery(
            tl, ref1, emb1,
            cfg={"DOSSIER_SHAPE": "relational"}).run("alpha bravo")
        check("parity/xbackend/dossier-relational",
              norm_run((df, rf)) == norm_run((dr, rr)),
              "relational dossier facade vs reference diverge")
        _invalidate_caches()
        df, rf = DossierQuery(
            tl, fac1, emb1,
            cfg={"DOSSIER_SHAPE": "cross-topic"}).run(
                "alpha bravo", topics=["alpha", "bravo foxtrot"])
        _invalidate_caches()
        dr, rr = DossierQuery(
            tl, ref1, emb1,
            cfg={"DOSSIER_SHAPE": "cross-topic"}).run(
                "alpha bravo", topics=["alpha", "bravo foxtrot"])
        check("parity/xbackend/dossier-cross-topic",
              norm_run((df, rf)) == norm_run((dr, rr)),
              "cross-topic dossier facade vs reference diverge")

    # -- retirement pin: tombstone path through wired entries ----
    rrep = retire_docs(tl, ["d4"], reason="r2-fi18",
                       approvals={"d4": {"type": "user",
                                         "approval_id": "fx-r2"}})
    check("retire/report", rrep["retired"] == ["d4"], rrep)
    pin2 = tl.pin()
    ref2 = ReferenceNarrowIndex(tl, pin2)
    fac2 = NarrowIndex(tl, pin2)
    check("retire/facade-tombstone",
          "d4" in fac2.retired_docs
          and not fac2.is_live_atom(a4), fac2.retired_docs)
    for tag, index in (("ref", ref2), ("fac", fac2)):
        d1, r1, d0, r0 = _narrow_pair(index, REL_CFG, Q_REL)
        check(f"parity/{tag}/retire-narrow-rel",
              norm_run((d1, r1)) == norm_run((d0, r0)),
              "retired-pin narrow REL diverges")
        d1, r1, d0, r0 = _dossier_pair(
            index, {"DOSSIER_SHAPE": "relational",
                    "DOSSIER_REL_TRAVERSAL": True,
                    "DOSSIER_REL_HOPS": 1}, "alpha bravo")
        check(f"parity/{tag}/retire-traversal",
              norm_run((d1, r1)) == norm_run((d0, r0)),
              "retired-pin traversal diverges")
finally:
    for _k, _v in _SAVED_ENV.items():
        if _v is None:
            os.environ.pop(_k, None)
        else:
            os.environ[_k] = _v
    try:
        tl.close()
    except Exception:
        pass

print(f"FAILS: {len(FAILS)} :: {FAILS}" if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
