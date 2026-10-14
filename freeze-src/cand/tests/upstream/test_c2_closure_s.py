"""Maintained Lane S closure tests (C2 Closure S): persisted generations,
production scorers, V1 pair-units, maintenance bounds.

Stage A: V1 pair-units (P-G3P-1) integration pins.
Stage B: production scorer kernels (vectorized BM25, stable head, dense).
Stage C: persisted query-ready generation v2 (format, attach, verify).
Stage D: maintenance bounds + end-to-end edit/publish/fresh-reader/answer.

Smallest maintained pins over scratch stores with deterministic fake
encoders (no weights). Bounds are on WORK (deterministic), never on
wall-clock time.

Run: HF_HOME=<repo>/local-data/hf-cache HF_HUB_OFFLINE=1 PYTHONHASHSEED=0
  tl-sys/.venv/bin/python tl-sys/tests/test_c2_closure_s.py
Goldens: C2S_REGEN_GOLDEN=1 ... (once, on arrived code, before Stage A impl)
"""
import contextlib
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "tlsys",
    "serving", "tests")))

ROOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(
    ROOT, "coordination", "c2-work-20261006T1925Z", "lane-G3P"))

import numpy as np  # noqa: E402

from fixture import emb_votes, make_docs, make_store  # noqa: E402
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys.index import ReferenceNarrowIndex, NarrowIndex  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.lifecycle import retire_docs  # noqa: E402
from tlsys.maint import organize_segments  # noqa: E402
from tlsys import query as _query_mod  # noqa: E402
from tlsys.query import NarrowQuery  # noqa: E402
from tlsys import relquery  # noqa: E402
from tlsys.relations import PROPOSED, commit_relations  # noqa: E402
from tlsys.relations import make_record  # noqa: E402
from tlsys.store_if import TLStore  # noqa: E402
from tlsys.fuse import admit as _fuse_admit  # noqa: E402
from tlsys.fuse import static_prune as _static_prune  # noqa: E402

GOLDEN_DIR = os.path.join(
    ROOT, "coordination", "c2-work-20261006T1925Z", "lane-S",
    "evidence", "c2s")
REGEN = os.environ.get("C2S_REGEN_GOLDEN") == "1"

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


def norm_run(obj):
    """Normalize runs for comparison (wall clocks only)."""
    def _walk(o):
        if isinstance(o, dict):
            return {k: (-1.0 if k in ("T_ms", "ms", "wall_ms")
                        else _walk(v))
                    for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_walk(v) for v in o]
        return o
    return _walk(obj)


def _golden_path(name):
    return os.path.join(GOLDEN_DIR, name)


def _aid_map(idx):
    """aid -> stable 'doc#k' role (k by (seq, span); aids are random)."""
    per_doc = {}
    for aid, a in idx.atoms.items():
        per_doc.setdefault(a["doc_id"], []).append(aid)
    out = {}
    for doc, aids in per_doc.items():
        aids.sort(key=lambda x: (idx.atoms[x].get("seq", 0),
                                 str(idx.atoms[x].get("span"))))
        for k, aid in enumerate(aids):
            out[aid] = f"{doc}#{k}"
    return out


def canon_payload(obj, aid2role, birth):
    """Canonicalize random store identity (aids, birth) for goldens."""
    import re
    _hex = re.compile(r"^[0-9a-f]+$")

    def _str(s):
        if not isinstance(s, str):
            return s
        if s in aid2role:
            return f"AID<{aid2role[s]}>"
        if birth and (s == birth or s.startswith(birth + ":")):
            return "BIRTH" + s[len(birth):]
        if len(s) in (16, 32, 64) and _hex.match(s):
            hits = sorted({aid2role[a] for a in aid2role
                           if a.startswith(s) or s.startswith(a)})
            if hits:
                return f"P<{','.join(hits)}>"
            if len(s) == 16 and aid2role:
                return "P<unknown>"
        if s.startswith("candidate:") and len(s) == 26:
            p = s[len("candidate:"):]
            if _hex.match(p):
                hits = sorted({aid2role[a] for a in aid2role
                               if a.startswith(p)})
                if hits:
                    return f"candidate:P<{','.join(hits)}>"
        return s

    def _walk(o, path=()):
        if isinstance(o, dict):
            return {_str(k): _walk(v, path + (k,)) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            out = [_walk(v, path + (i,)) for i, v in enumerate(o)]
            # Pre-existing hier sidecar tie order is aid-hash-dependent
            # (score-0.0 ties; flaky across processes on arrived code,
            # unrelated to V1): sort golden-side only for stability.
            if path and path[-1] == "rows" and len(path) >= 2 \
                    and path[-2] == "hierarchy" \
                    and all(isinstance(r, dict) for r in out):
                out.sort(key=lambda r: (
                    -float(r.get("score", 0.0)),
                    str(r.get("doc_id", "")),
                    str(r.get("aid", ""))))
            return out
        if isinstance(o, (set, frozenset)):
            return sorted((_walk(v, path) for v in o), key=repr)
        return _str(o)
    return _walk(obj)


def _golden_roundtrip(name, payload, canon=None):
    """Regen mode: write golden, pass. Else: load + compare exact."""
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    path = _golden_path(name)
    if canon is not None:
        payload = canon(payload)
    normed = norm_run(payload)
    if REGEN:
        with open(path, "w") as f:
            json.dump(normed, f, sort_keys=True)
        check(f"v1-golden/{name}/regen", True, "wrote golden")
        return True
    if not os.path.isfile(path):
        check(f"v1-golden/{name}/present", False,
              "missing golden; run once with C2S_REGEN_GOLDEN=1")
        return False
    with open(path) as f:
        want = json.load(f)
    ok = normed == want
    if not ok:
        got_s = json.dumps(normed, sort_keys=True, default=str)
        want_s = json.dumps(want, sort_keys=True, default=str)
        detail = f"bytes {len(got_s)} vs {len(want_s)}"
        for i, (a, b) in enumerate(zip(got_s, want_s)):
            if a != b:
                detail += f"; firstdiv @{i}: {got_s[max(0,i-80):i+80]!r}"
                break
        else:
            detail += "; prefix-equal, length differs"
    else:
        detail = ""
    check(f"v1-golden/{name}/match", ok, detail)
    return ok


# -- deterministic keyword embedding (no weights) --------------------

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


RCFG = {"extractor": "test-c2s-v1", "window": 1,
        "model": "none", "rules": ["c2s"]}
REL_CFG = {"REL_HUB_SUPPRESS": True, "REL_QUALIFIERS": True}

DOCS = [
    ("d0", "alpha norms govern the alpha baseline completely."),
    ("d1", "bravo rules handle the bravo cases entirely."),
    ("d2", "charlie axioms cover the charlie domain fully."),
    ("d3", "delta statutes span the delta regime wholly."),
    ("d4", "echo remarks touch sundry matters lightly."),
    ("d5", "foxtrot clauses bind the foxtrot parties duly."),
    ("d6", "zebra quixotic jargon with no relation anywhere."),
]


def _plain_store(docs=None):
    root = tempfile.mkdtemp(prefix="tl-c2s-")
    tl = TLStore(os.path.join(root, "store"), create=True,
                 lease_owner="test-c2s")
    ingest_docs(tl, docs or DOCS, emb)
    organize_segments(tl)
    return tl, root, tl.pin()


def _rel_store():
    """Plain docs + one affirmed/negated evidence pair over a shared
    context (identify_pairs-eligible when both sides emit)."""
    tl, root, _p0 = _plain_store()
    idx = ReferenceNarrowIndex(tl, tl.pin())
    aids = {a["doc_id"]: aid for aid, a in idx.atoms.items()}
    a0, a3, a5 = aids["d0"], aids["d3"], aids["d5"]
    batch = [
        make_record("evidences", [("claim", a3), ("context", a0)],
                    {"negated": False, "scope": "as-stated"},
                    RCFG, PROPOSED, [a3, a0]),
        make_record("evidences", [("claim", a5), ("context", a0)],
                    {"negated": True, "scope": "as-stated"},
                    RCFG, PROPOSED, [a5, a0]),
    ]
    commit_relations(tl, batch)
    return tl, root, tl.pin(), (a0, a3, a5)


# -- Stage A: V1 pair-units ------------------------------------------

def _v1_battery():
    """Deterministic (scored, pairs) cases incl. overflow/dissolve."""
    t = ["alpha beta", "bravo charlie", "delta echo", "foxtrot sport",
         "medic alpha", "zebra quixotic"]
    A = [f"a{i:04d}" for i in range(8)]
    S = [(A[i], 1.0 - i * 0.1, t[i % len(t)]) for i in range(6)]
    dup = list(S) + [(A[6], 0.05, t[0])]  # exact-text dup of A[0]
    cases = [
        ("empty", [], [], 50, True),
        ("empty-pairs-unavail", [], [(A[0], A[1])], 50, True),
        ("singles", S, [], 50, True),
        ("one-pair", S, [(A[0], A[1])], 50, True),
        ("one-pair-cap1", S, [(A[0], A[1])], 1, True),
        ("one-pair-cap0", S, [(A[0], A[1])], 0, True),
        ("one-pair-cap2", S, [(A[0], A[1])], 2, True),
        ("two-units-cap3", S, [(A[0], A[1]), (A[2], A[3])], 3, True),
        ("shared-aid", S, [(A[0], A[1]), (A[1], A[2])], 50, True),
        ("self-pair", S, [(A[0], A[0])], 50, True),
        ("unavail-side", S, [(A[0], "zz99")], 50, True),
        ("both-unavail", S, [("zz97", "zz98")], 50, True),
        ("dup-collapse", dup, [(A[0], A[6])], 50, True),
        ("dup-nocollapse", dup, [(A[0], A[6])], 50, False),
        ("reversed-dup-pairs", S, [(A[1], A[0]), (A[0], A[1])], 50, True),
        ("lowpair-cap2", S, [(A[4], A[5])], 2, True),
    ]
    tie = [(A[i], 0.5, t[i]) for i in range(4)]
    cases.append(("ties", tie, [(A[0], A[3])], 3, True))
    return cases


def test_v1_seat_differential():
    from variants.v1_units import seat_units as ref_seat
    prod = getattr(_query_mod, "_seat_pair_units", None)
    check("v1-seat/present", prod is not None,
          "query._seat_pair_units missing (Stage A not implemented)")
    if prod is None:
        return
    for name, scored, pairs, cap, collapse in _v1_battery():
        want_s, want_d = ref_seat(scored, pairs, cap, collapse=collapse)
        got_s, got_d = prod(scored, pairs, cap, collapse=collapse)
        check(f"v1-seat/{name}",
              got_s == want_s and got_d == want_d,
              f"got {(got_s, got_d)} want {(want_s, want_d)}")
    try:
        prod([("a", 1.0, "t")], [], -1)
        check("v1-seat/negcap", False, "no ValueError")
    except ValueError:
        check("v1-seat/negcap", True)


def _split_battery():
    t = ["alpha beta", "bravo charlie", "delta echo", "foxtrot sport",
         "medic alpha", "zebra quixotic"]
    A = [f"b{i:04d}" for i in range(10)]
    S = [(A[i], 1.0 - i * 0.07, t[i % len(t)]) for i in range(10)]
    fw = {f"a:{A[i]}": (0.02 if i % 3 else 0.0) for i in range(10)}
    darrf = {f"a:{A[i]}": (0.0 if i % 3 == 1 else 0.03)
             for i in range(10)}
    # i%3==0: neither; ==1: lex-only; ==2: both; force two dense-only:
    fw["a:" + A[0]] = 0.0
    darrf["a:" + A[0]] = 0.05
    fw["a:" + A[3]] = 0.0
    darrf["a:" + A[3]] = 0.04
    scope = {A[0]: [("r1", {"negated": False, "scope": "as-stated"})],
             A[1]: [("r2", {"negated": True, "scope": "as-stated"})]}
    unresolved = {A[9]}
    prunes = [
        ("static", None),
        ("rel", lambda c, k: relquery.prune_rel(c, k, scope, unresolved)),
    ]
    return S, fw, darrf, prunes


def test_v1_split_fallback():
    S, fw, darrf, prunes = _split_battery()
    for pname, pfn in prunes:
        for cap in (1, 2, 3, 7, 50):
            base = _query_mod._split_prune(S, fw, darrf, cap,
                                           prune_fn=pfn)
            try:
                got_none = _query_mod._split_prune(
                    S, fw, darrf, cap, prune_fn=pfn, pairs=None)
                got_empty = _query_mod._split_prune(
                    S, fw, darrf, cap, prune_fn=pfn, pairs=[])
            except TypeError as e:
                check(f"v1-split/{pname}/cap{cap}/fallback", False,
                      f"pairs param missing: {e}")
                return
            check(f"v1-split/{pname}/cap{cap}/fallback-none",
                  got_none == base, f"{got_none} vs {base}")
            check(f"v1-split/{pname}/cap{cap}/fallback-empty",
                  got_empty == base, f"{got_empty} vs {base}")


def test_v1_split_engage():
    from variants.v1_units import seat_units as ref_seat
    S, fw, darrf, prunes = _split_battery()
    A = [c[0] for c in S]
    pair_sets = [
        ("one", [(A[0], A[1])]),
        ("two", [(A[0], A[1]), (A[4], A[5])]),
        ("dissolve", [(A[0], "missing-side")]),
        ("low", [(A[7], A[8])]),
    ]
    for pname, pfn in prunes:
        for psname, pairs in pair_sets:
            for cap in (1, 2, 3, 7, 50):
                if pfn is not None:
                    surv = pfn(S, len(S))
                    want, _d = ref_seat(surv, pairs, cap,
                                        collapse=False)
                else:
                    want, _d = ref_seat(S, pairs, cap, collapse=True)
                diag = {}
                try:
                    got = _query_mod._split_prune(
                        S, fw, darrf, cap, prune_fn=pfn,
                        pairs=pairs, pair_diag=diag)
                except TypeError as e:
                    check(f"v1-split/{pname}/{psname}/cap{cap}",
                          False, f"pairs param missing: {e}")
                    return
                check(f"v1-split/{pname}/{psname}/cap{cap}",
                      got == want, f"got {got} want {want}")
                check(f"v1-split/{pname}/{psname}/cap{cap}/diag",
                      2 * diag.get("units_seated", 0) +
                      diag.get("singles_seated", 0) == len(got)
                      and len(got) <= cap,
                      f"{diag} n={len(got)}")
    check("v1-split/PRUNE_CAP-frozen", _query_mod.PRUNE_CAP == 50,
          _query_mod.PRUNE_CAP)


def test_v1_admit_unchanged():
    check("v1-admit/same-object", _query_mod.admit is _fuse_admit,
          "query.admit must stay the frozen fuse.admit")
    adm, dfd = _fuse_admit([("a", 0.9), ("b", 0.001)], [("a", "b")],
                           0.005, 10)
    check("v1-admit/rides", adm == ["a", "b"] and not dfd, (adm, dfd))
    adm, dfd = _fuse_admit([("a", 0.9), ("b", 0.8)], [("a", "b")],
                           0.005, 1)
    check("v1-admit/overflow",
          adm == [] and sorted(dfd) == [("a", "pair-overflow-cap"),
                                        ("b", "pair-overflow-cap")],
          (adm, dfd))
    adm, dfd = _fuse_admit([("a", 0.9)], [("a", "b")], 0.005, 10)
    check("v1-admit/unidentified", dfd == [("a", "counterpart-unidentified")],
          (adm, dfd))


def test_v1_narrow_fallback_golden():
    tl, root, pin = _plain_store()
    try:
        payload = {}
        idx_c2 = NarrowIndex(tl, pin)
        aid2role = _aid_map(idx_c2)
        for tag, idx in (("c2", idx_c2),
                         ("ref", ReferenceNarrowIndex(tl, pin))):
            for q in ("alpha bravo", "sport athletics", "delta foxtrot"):
                nq = NarrowQuery(tl, idx, emb1)
                dos, rec = nq.run(q)
                payload[f"{tag}/{q}"] = {
                    "entries": dos["entries"], "receipt": rec}
        _golden_roundtrip(
            "c2s-v1-narrow.json", payload,
            canon=lambda p: canon_payload(p, aid2role, pin[0]))
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_v1_shapes_fallback_golden():
    tl, root, pin = _plain_store()
    try:
        idx = NarrowIndex(tl, pin)
        payload = {}
        cfgs = [
            ("relational", {"DOSSIER_SHAPE": "relational"}),
            ("relational-trav", {"DOSSIER_SHAPE": "relational",
                                 "DOSSIER_REL_TRAVERSAL": True,
                                 "DOSSIER_REL_HOPS": 1}),
            ("cross-topic", {"DOSSIER_SHAPE": "cross-topic"}),
            ("narrow-relcfg", {"DOSSIER_SHAPE": "narrow"}),
        ]
        for name, cfg in cfgs:
            dq = DossierQuery(tl, idx, emb1, cfg=dict(cfg))
            if name == "cross-topic":
                dos, rec = dq.run("alpha", topics=["alpha", "bravo"])
            elif name == "narrow-relcfg":
                nq = NarrowQuery(tl, idx, emb1, cfg=dict(REL_CFG))
                dos, rec = nq.run("alpha bravo")
            else:
                dos, rec = dq.run("alpha bravo")
            payload[name] = {"entries": dos["entries"], "receipt": rec}
        nq = NarrowQuery(tl, idx, emb1, cfg={"HIER_GUIDED": True})
        dos, rec = nq.run("sport athletics")
        payload["hier-guided"] = {"entries": dos["entries"],
                                  "receipt": rec}
        aid2role = _aid_map(idx)
        _golden_roundtrip(
            "c2s-v1-shapes.json", payload,
            canon=lambda p: canon_payload(p, aid2role, pin[0]))
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_v1_live_pair_leg():
    """Qualifier leg over a real pair: V1 engages iff pairs identified.

    Invariants (pass both pre/post V1 when pairs exist): pair seating
    is joint-or-explicit (overflow/dissolve recorded, cap respected),
    admission still applies the frozen rule to the new order. The
    arrived-vs-new diff is receipted as the consumer-policy diff.
    """
    tl, root, pin, _trio = _rel_store()
    try:
        idx = NarrowIndex(tl, pin)
        nq = NarrowQuery(tl, idx, emb1, cfg=dict(REL_CFG))
        dos, rec = nq.run("delta foxtrot scope as-stated")
        metrics = rec.get("metrics", {})
        rel_diag = None
        for _k in ("rel", "relations", "rel_diag"):
            if _k in rec:
                rel_diag = rec[_k]
        # rel_diag rides the receipt; locate pairs_identified anywhere
        blob = json.dumps(rec, sort_keys=True, default=str)
        n_pairs = None
        try:
            n_pairs = int(metrics.get("pairs_identified", -1))
        except (TypeError, ValueError):
            n_pairs = -1
        if n_pairs < 0:
            # fallback: scan receipt for the qualifier diag block
            def _find(o):
                if isinstance(o, dict):
                    if "pairs_identified" in o:
                        return o
                    for v in o.values():
                        r = _find(v)
                        if r is not None:
                            return r
                if isinstance(o, list):
                    for v in o:
                        r = _find(v)
                        if r is not None:
                            return r
                return None
            rel_diag = _find(rec)
            n_pairs = int((rel_diag or {}).get("pairs_identified", 0))
        else:
            rel_diag = {k: v for k, v in metrics.items()
                        if "pair" in k or "prune" in k or "unit" in k}
        check("v1-live/has-pairs", n_pairs > 0,
              f"fixture must identify >=1 pair, got {n_pairs}")
        if n_pairs <= 0:
            return
        units = (rel_diag or {}).get("prune_units")
        check("v1-live/engaged", isinstance(units, dict),
              "pairs>0 but no prune_units diag (Stage A missing?)")
        if not isinstance(units, dict):
            return
        seated = int(units.get("units_seated", 0))
        check("v1-live/seated-or-explicit",
              seated > 0 or int(units.get("overflow_n", 0)) > 0
              or int(units.get("dissolved_n", 0)) > 0, units)
        check("v1-live/cap",
              int(units.get("pruned_n", 0)) <= _query_mod.PRUNE_CAP,
              units)
        # Admission still the frozen rule on the new order: re-apply
        # admit() to the receipt order and require identical results.
        order = None
        try:
            order = rec["admission"]["order_scores"]
            pairs = [tuple(p) for p in
                     rec["admission"].get("pairs", [])]
            tau = rec["admission"]["tau"]
            cap = rec["admission"]["cap"]
            adm0 = rec["admission"]["admitted"]
            dfd0 = [tuple(d) for d in
                    rec["admission"].get("deferred", [])]
        except (KeyError, TypeError):
            order = None
        if order is not None:
            adm1, dfd1 = _fuse_admit(
                [(a, s) for a, s in order], pairs, tau, cap)
            check("v1-live/admit-frozen",
                  adm1 == adm0 and sorted(dfd1) == sorted(dfd0),
                  f"{(adm1, dfd1)} vs {(adm0, dfd0)}")
        else:
            check("v1-live/admit-frozen", "admitted" in blob,
                  "no admission block to re-verify")
        # Receipt the consumer-policy diff vs arrived (informational).
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        aid2role = _aid_map(idx)
        new_c = canon_payload({"entries": dos["entries"],
                               "receipt": rec}, aid2role, pin[0])
        apath = _golden_path("c2s-v1-livepair-new.json")
        with open(apath, "w") as f:
            json.dump(norm_run(new_c), f, sort_keys=True)
        arrived_p = _golden_path("c2s-v1-livepair-arrived.json")
        if REGEN or not os.path.isfile(arrived_p):
            if REGEN:
                with open(arrived_p, "w") as f:
                    json.dump(norm_run(new_c), f, sort_keys=True)
            check("v1-live/diff-recorded", True, "arrived saved")
        else:
            with open(arrived_p) as f:
                arrived = json.load(f)
            with open(apath) as f:
                new = json.load(f)
            same = arrived == new
            with open(os.path.join(
                    GOLDEN_DIR, "c2s-v1-livepair-diff.json"),
                    "w") as f:
                json.dump({"identical": same,
                           "arrived_entries": len(
                               arrived.get("entries", [])),
                           "new_entries": len(new.get("entries", []))},
                          f, sort_keys=True)
            check("v1-live/diff-recorded", True,
                  f"identical={same} (diff=authorized V1 policy)")
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_v1_overflow_dissolve_retire_scope():
    """Explicit unit-overflow partials + dissolve on unavailable /
    retired / wrong-scope sides, at the product _split_prune seam."""
    t = ["alpha beta", "bravo charlie", "delta echo", "foxtrot sport",
         "medic golf", "hotel india"]
    A = [f"c{i:04d}" for i in range(6)]
    S = [(A[i], 1.0 - i * 0.1, t[i]) for i in range(6)]
    fw = {f"a:{a}": 0.02 for a in A}
    darrf = {f"a:{a}": 0.03 for a in A}
    if getattr(_query_mod._split_prune, "__code__", None) is not None:
        import inspect
        if "pairs" not in inspect.signature(
                _query_mod._split_prune).parameters:
            check("v1-ods/pairs-param", False,
                  "pairs param missing (Stage A not implemented)")
            return
    check("v1-ods/pairs-param", True)
    # overflow: cap=3, two top units -> first seats, second overflows,
    # best single fills the last seat.
    diag = {}
    got = _query_mod._split_prune(
        S, fw, darrf, 3, pairs=[(A[0], A[1]), (A[2], A[3])],
        pair_diag=diag)
    got_aids = [a for a, _s, _t in got]
    check("v1-ods/overflow-seats",
          got_aids == [A[0], A[1], A[4]], (got_aids, diag))
    check("v1-ods/overflow-recorded",
          len(diag.get("overflow", [])) == 1
          and diag["overflow"][0]["reason"] == "unit-overflow",
          diag)
    # dissolve/unavailable: side missing from the universe.
    diag = {}
    got = _query_mod._split_prune(S, fw, darrf, 50,
                                  pairs=[(A[0], "gone-side")],
                                  pair_diag=diag)
    check("v1-ods/dissolve",
          A[0] in [a for a, _s, _t in got]
          and len(diag.get("dissolved", [])) == 1, (got, diag))
    # retire-model: retired aid absent from scored (liveness filter).
    live_only = [c for c in S if c[0] != A[1]]
    diag = {}
    got = _query_mod._split_prune(live_only, fw, darrf, 50,
                                  pairs=[(A[0], A[1])],
                                  pair_diag=diag)
    check("v1-ods/retire-dissolves",
          A[0] in [a for a, _s, _t in got]
          and len(diag.get("dissolved", [])) == 1, (got, diag))
    # wrong-scope-model: out-of-universe counterpart dissolves too.
    diag = {}
    got = _query_mod._split_prune(S, fw, darrf, 50,
                                  pairs=[(A[2], "other-scope-aid")],
                                  pair_diag=diag)
    check("v1-ods/scope-dissolves",
          A[2] in [a for a, _s, _t in got]
          and len(diag.get("dissolved", [])) == 1, (got, diag))


STAGE_A = (test_v1_seat_differential,
           test_v1_split_fallback,
           test_v1_split_engage,
           test_v1_admit_unchanged,
           test_v1_narrow_fallback_golden,
           test_v1_shapes_fallback_golden,
           test_v1_live_pair_leg,
           test_v1_overflow_dissolve_retire_scope)


# -- Stage B: production scorer kernels ------------------------------

BM25_QUERIES = ["sport medic", "alpha beta", "nonexistentterm xyz", "",
                "sport sport sport", "the domestic cat"]


def _bm25_shapes():
    from tlsys.serving.view import ViewPool
    shapes = {}
    # delta-only (no seal): everything in the overlay.
    tl, tmp, pin = make_store(make_docs(12, seed=11), emb_votes,
                              prefix="tlsys-c2sb-delta-")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=None,
                    config={"delta_flush_atoms": 1000})
    shapes["delta"] = (tl, tmp, pin, pool, pool.cold_build(pin))
    # multi-segment sealed.
    tl, tmp, pin = make_store(make_docs(12, seed=12), emb_votes,
                              prefix="tlsys-c2sb-multi-")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 3})
    v = pool.cold_build(pin)
    pool.checkpoint(v)
    shapes["multi"] = (tl, tmp, pin, pool, v)
    # sealed + retirements + tail.
    docs = make_docs(12, seed=13)
    tl, tmp, pin = make_store(docs, emb_votes,
                              prefix="tlsys-c2sb-ret-")
    from tlsys.serving.view import ViewPool as VP
    pool = VP(tl, pin[0], pin[1], serving_dir=None,
              config={"delta_flush_atoms": 1000})
    v = pool.cold_build(pin)
    retire_docs(tl, [docs[0][0], docs[3][0]], reason="c2sb-ret",
                approvals={d: {"type": "user",
                               "approval_id": f"fixture-c2sb-ret-{d}"}
                           for d, _t in (docs[0], docs[3])})
    v2 = pool.advance(v, tl.pin())
    shapes["retire"] = (tl, tmp, tl.pin(), pool, v2)
    return shapes


def _items_equal(a, b):
    return list(a.items()) == list(b.items())


def test_scorer_bm25_vectorized():
    from tlsys.serving import lexical as lex_mod
    vec_fn = getattr(lex_mod, "bm25_accumulate_vectorized", None)
    check("scorer-bm25/vec-present", vec_fn is not None,
          "lexical.bm25_accumulate_vectorized missing (Stage B?)")
    shapes = _bm25_shapes()
    try:
        for name, (tl, tmp, pin, pool, v) in shapes.items():
            ref = ReferenceNarrowIndex(tl, pin)
            for q in BM25_QUERIES:
                got = v.bm25(q)
                want = ref.bm25(q)
                check(f"scorer-bm25/{name}/{q!r}/ref-bitwise",
                      _items_equal(got, want),
                      f"{list(got.items())[:3]} vs {list(want.items())[:3]}")
            if vec_fn is None:
                continue
            # Kernel equivalence: legacy generator path vs blocked
            # array path over the same view state, same query.
            from tlsys.serving.lexical import bm25_accumulate, idf_of
            cols = v._columnar_for_bm25()
            for q in BM25_QUERIES:
                terms = sorted(set(q.lower().split()))
                n = max(1, v.live_n)
                avgdl = v.total_tokens / n
                legacy = bm25_accumulate(
                    terms, v.df.get, n, avgdl, v._postings_of,
                    lambda o: v.aid_of_ord.get(o) in v.atoms,
                    v.aid_of_ord.__getitem__,
                    v.doclen_of.__getitem__,
                    v.ord_atom.__getitem__)
                blocked = vec_fn(
                    terms, v.df.get, n, avgdl,
                    v._bm25_runs_of, cols["live_ord"],
                    cols["doclen"], cols["aids"])
                check(f"scorer-bm25/{name}/{q!r}/kernel-bitwise",
                      _items_equal(blocked, legacy),
                      f"{list(blocked.items())[:3]}")
        # No Python loop per posting on the wired path: the legacy
        # per-posting generator must not fire during bm25.
        _tl, _tmp, _pin, _pool, v = shapes["multi"]
        fired = []
        orig = v._postings_of

        def _spy(term):
            fired.append(term)
            return orig(term)
        v._postings_of = _spy
        try:
            v.bm25("sport medic alpha")
        finally:
            v._postings_of = orig
        check("scorer-bm25/no-postings-loop", not fired,
              f"legacy generator fired for {fired}")
    finally:
        for tl, _tmp, _pin, _pool, _v in shapes.values():
            try:
                tl.close()
            except Exception:
                pass


def test_scorer_bm25_cache_coherent():
    """Columnar caches stay coherent across advance/retire/seal."""
    from tlsys.serving.view import ViewPool
    docs = make_docs(10, seed=21)
    tl, tmp, pin = make_store(docs, emb_votes,
                              prefix="tlsys-c2sb-coh-")
    try:
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=None,
                        config={"delta_flush_atoms": 4})
        v = pool.cold_build(pin)
        v.bm25("sport medic")  # populate caches
        pool.seal_locked(v)
        v.bm25("sport medic")
        retire_docs(tl, [docs[1][0]], reason="c2sb-coh",
                    approvals={docs[1][0]: {
                        "type": "user",
                        "approval_id": "fixture-c2sb-coh"}})
        v2 = pool.advance(v, tl.pin())
        for q in BM25_QUERIES:
            got = v2.bm25(q)
            ref = ReferenceNarrowIndex(tl, tl.pin())
            check(f"scorer-bm25coh/{q!r}",
                  _items_equal(got, ref.bm25(q)), q)
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_scorer_stable_head():
    from tlsys.serving import dense as dense_mod
    head_fn = getattr(dense_mod, "stable_head", None)
    check("scorer-head/present", head_fn is not None,
          "dense.stable_head missing (Stage B?)")
    if head_fn is None:
        return
    rng = np.random.RandomState(20261007)
    gens = {
        "uniform": lambda n: rng.uniform(-1, 1, n),
        "ties1": lambda n: np.round(rng.uniform(-1, 1, n), 1),
        "zeros": lambda n: np.zeros(n),
        "const": lambda n: np.full(n, 0.42),
        "dups": lambda n: rng.choice([0.1, 0.5, 0.9], n),
        "gauss": lambda n: rng.normal(0, 0.3, n),
    }
    for gname, gen in gens.items():
        for n in (0, 1, 2, 3, 5, 50, 500):
            s = np.asarray(gen(n), dtype=np.float64)
            ids = [f"id{i:05d}" for i in range(n)]
            for k in (0, 1, 2, n - 1, n, n + 5):
                kk = max(0, k)
                order = np.argsort(-s, kind="stable")[:kk]
                want = [(ids[i], float(s[i])) for i in order]
                got = head_fn(s, ids, kk)
                check(f"scorer-head/{gname}/n{n}/k{k}", got == want,
                      f"{got[:3]} vs {want[:3]}")
    # NaN falls back to the full-sort reference (never misorders).
    s = np.array([0.5, float("nan"), 0.2, float("nan"), 0.9])
    ids = [f"n{i}" for i in range(5)]
    order = np.argsort(-s, kind="stable")[:3]
    want = [(ids[i], float(s[i])) for i in order]
    got = head_fn(s, ids, 3)
    same = [g[0] for g in got] == [w[0] for w in want] and all(
        (g[1] == w[1]) or (g[1] != g[1] and w[1] != w[1])
        for g, w in zip(got, want))
    check("scorer-head/nan-fallback", same, f"{got} vs {want}")


def test_scorer_dense_rank_head():
    from tlsys.query import _dense_rank
    rng = np.random.RandomState(777)
    for trial in range(6):
        n, d = (1, 4) if trial == 0 else (7 + trial * 3, 8)
        mat = rng.normal(0, 1, (n, d))
        if trial >= 2:
            mat[0] = 0.0  # zero row
            mat[1] = mat[2]  # exact duplicate rows
        norms = np.linalg.norm(mat, axis=1)
        norms[norms == 0.0] = 1.0
        qvec = rng.normal(0, 1, d)
        if trial == 3:
            qvec = np.zeros(d)
        ids = [f"r{trial}-{i:03d}" for i in range(n)]
        full = _dense_rank(qvec, ids, mat, norms, topk=None)
        for k in (0, 1, 2, n - 1, n, n + 4):
            got = _dense_rank(qvec, ids, mat, norms, topk=k)
            check(f"scorer-denserank/t{trial}/k{k}",
                  got == full[:k if k is not None else None], k)
    check("scorer-denserank/empty", _dense_rank([1.0], [], [[]], []) == [])


def test_scorer_certified_widen():
    from tlsys.serving.dense import certified_topk, exact_full_rank
    from tlsys.serving.counters import ServeCounters
    # FP32/exact top-1 disagreement (near-tie below FP32 rounding):
    # the initial shortlist cannot certify, so it widens to the
    # full population (honest automatic fallback, counted).
    r0 = np.array([1.0, 0.0])
    r1 = np.array([1.0, 1e-4])  # exact < r0, FP32-tied with r0
    r2 = np.array([0.0, 1.0])
    mat32 = np.ascontiguousarray(
        np.stack([r0, r1, r2]).astype(np.float32))
    norms = np.linalg.norm(mat32.astype(np.float64), axis=1)
    norms[norms == 0.0] = 1.0
    ids = ["w000", "w001", "w002"]
    qvec = np.array([1.0, 0.0])
    n, k = 3, 1
    c = ServeCounters()
    out, cert = certified_topk(qvec, k, ids, mat32, norms, {},
                               m=0, eps=0.0, counters=c)
    ref = exact_full_rank(qvec, ids, mat32, norms, {})[:k]
    check("scorer-cert/widened", cert.get("widened", 0) > 0
          and cert.get("full") is True, cert)
    check("scorer-cert/order",
          [a for a, _s in out] == [a for a, _s in ref], cert)
    check("scorer-cert/scores",
          max(abs(a - b) for (_x, a), (_y, b) in zip(out, ref)) <= 1e-12,
          cert)
    tot = c.totals()
    check("scorer-cert/counts",
          tot["dense_fp32_rows"] == n
          and tot["dense_rescore_rows"] >= cert.get("rows", 0)
          and tot["widenings"] == cert.get("widened", -1), tot)


STAGE_B = (test_scorer_bm25_vectorized,
           test_scorer_bm25_cache_coherent,
           test_scorer_stable_head,
           test_scorer_dense_rank_head,
           test_scorer_certified_widen)


# -- Stage C: persisted generation v2 --------------------------------

def _gen_store(tag, n_docs=14, seed=41, flush=4):
    from tlsys.serving.view import ViewPool
    docs = make_docs(n_docs, seed=seed)
    tl, tmp, pin = make_store(docs, emb_votes,
                              prefix=f"tlsys-c2sg-{tag}-")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": flush})
    v = pool.cold_build(pin)
    return tl, tmp, pin, sdir, pool, v, docs


def _publish(pool, view):
    fn = getattr(pool, "publish_generation", None)
    assert fn is not None, "pool.publish_generation missing (Stage C?)"
    return fn(view)


def test_gen_build_publish_attach():
    from tlsys.serving.view import ViewPool
    from tlsys.serving.digest import canonical_digest
    tl, tmp, pin, sdir, pool, v, docs = _gen_store("bpa")
    try:
        check("gen-bpa/publish-api", hasattr(pool, "publish_generation"),
              "pool.publish_generation missing (Stage C?)")
        if not hasattr(pool, "publish_generation"):
            return
        receipt = _publish(pool, v)
        check("gen-bpa/published",
              receipt["publish"].get("frontier") == pin[2], receipt)
        d0 = v.canonical_digest()
        # Fresh pool attach at the same pin: no suffix, no replay.
        pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                         config={"delta_flush_atoms": 4})
        before = pool2.counters.totals()["log_rows_read"]
        stages = {}
        v2 = pool2.acquire(pin, stages=stages)
        after = pool2.counters.totals()["log_rows_read"]
        check("gen-bpa/kind", type(v2).__name__ == "GenerationView",
              type(v2).__name__)
        check("gen-bpa/digest", v2.canonical_digest() == d0,
              f"{v2.canonical_digest()} vs {d0}")
        check("gen-bpa/no-replay", after - before == 0,
              f"log_rows_read delta={after - before} (want 0)")
        check("gen-bpa/suffix-zero", stages.get("suffix_rows", -1) == 0,
              stages)
        pool2.release(v2)
        # Extend the store; fresh attach consumes ONLY the suffix.
        from tlsys.serving.view import ViewPool as VP
        (tl2, tmp2, pinx) = (tl, tmp, pin)
        ingest_docs(tl, [("d-new-0", "quasar pulsar quasar physics")],
                    emb_votes)
        from tlsys.maint import organize_segments
        organize_segments(tl)
        pin1 = tl.pin()
        pool3 = VP(tl, pin1[0], pin1[1], serving_dir=sdir,
                   config={"delta_flush_atoms": 4})
        b0 = pool3.counters.totals()["log_rows_read"]
        st3 = {}
        v3 = pool3.acquire(pin1, stages=st3)
        b1 = pool3.counters.totals()["log_rows_read"]
        mx0, mx1 = pin[2], pin1[2]
        rows_all = tl.read_commits_all(
            pin1[0], pin1[1], mx1, kind="ACCEPT_ATOMS", min_seq=0)
        rows_suf = tl.read_commits_all(
            pin1[0], pin1[1], mx1, kind="ACCEPT_ATOMS", min_seq=mx0)
        check("gen-bpa/suffix-only",
              st3.get("suffix_rows", -1) == len(rows_suf)
              and len(rows_suf) < len(rows_all)
              and (b1 - b0) == len(rows_suf),
              f"{st3} suf={len(rows_suf)} all={len(rows_all)} "
              f"read={b1 - b0}")
        ref = ReferenceNarrowIndex(tl, pin1)
        for q in ("quasar pulsar", "sport medic"):
            check(f"gen-bpa/suffix-bm25/{q}",
                  _items_equal(v3.bm25(q), ref.bm25(q)), q)
        pool3.release(v3)
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_gen_no_eager_dicts():
    from tlsys.serving.view import ViewPool
    from collections.abc import Mapping
    tl, tmp, pin, sdir, pool, v, docs = _gen_store("ned")
    try:
        if not hasattr(pool, "publish_generation"):
            check("gen-ned/publish-api", False, "Stage C missing?")
            return
        _publish(pool, v)
        pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                         config={"delta_flush_atoms": 4})
        g = pool2.acquire(pin)
        try:
            check("gen-ned/kind", type(g).__name__ == "GenerationView",
                  type(g).__name__)
            for attr in ("atoms", "holons", "atom_text", "doc_atoms",
                         "df", "doclen_of", "ord_atom", "aid_of_ord"):
                m = getattr(g, attr, None)
                check(f"gen-ned/{attr}-indexed",
                      isinstance(m, Mapping) and not isinstance(m, dict),
                      type(m).__name__)
            ov_total = sum(len(getattr(g, a, {}) or {})
                           for a in ("ov_atoms", "ov_holons",
                                     "ov_atom_text", "ov_doc_atoms",
                                     "ov_df", "ov_doclen"))
            check("gen-ned/overlay-small", ov_total == 0, ov_total)
            check("gen-ned/live-count", len(g.atoms) == g.live_n
                  == len(v.atoms), (len(g.atoms), g.live_n))
        finally:
            pool2.release(g)
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_gen_format_transition():
    from tlsys.serving.view import ViewPool
    from tlsys.serving import manifest as manifest_mod
    tl, tmp, pin, sdir, pool, v, docs = _gen_store("fmt")
    try:
        # Legacy v1 checkpoint first: new readers take the v1 path.
        pool.checkpoint(v)
        p1 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                      config={"delta_flush_atoms": 4})
        w = p1.acquire(pin)
        check("gen-fmt/legacy-v1", type(w).__name__ == "ServingView",
              type(w).__name__)
        p1.release(w)
        if not hasattr(pool, "publish_generation"):
            check("gen-fmt/publish-api", False, "Stage C missing?")
            return
        _publish(pool, v)
        with open(os.path.join(sdir, "manifest.json")) as f:
            man = json.load(f)
        check("gen-fmt/manifest-v2", man.get("format_version") == 2, man)
        check("gen-fmt/v1-retained",
              os.path.isfile(os.path.join(
                  sdir, "manifest.v1.json")) and os.path.isfile(
                  os.path.join(sdir, "checkpoint.v1.json")),
              os.listdir(sdir))
        # Old-reader refusal: the v1 validator rejects format 2.
        try:
            manifest_mod.read_validated(os.path.join(sdir, "manifest.json"))
            check("gen-fmt/old-refuses", False, "old reader accepted v2!")
        except ValueError:
            check("gen-fmt/old-refuses", True)
        # New reader takes v2.
        p2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                      config={"delta_flush_atoms": 4})
        g = p2.acquire(pin)
        check("gen-fmt/new-v2", type(g).__name__ == "GenerationView",
              type(g).__name__)
        d_gen = g.canonical_digest()
        p2.release(g)
        check("gen-fmt/digest", d_gen == v.canonical_digest(), d_gen)
        # Corrupt one block byte: fail closed (quarantine + v1/cold
        # fallback), digest-stable, never serving the bad bytes.
        vpath = os.path.join(sdir, "generation", "vectors.npy")
        with open(vpath, "r+b") as f:
            f.seek(100)
            b = f.read(1)
            f.seek(100)
            f.write(bytes([b[0] ^ 0xFF]))
        p3 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                      config={"delta_flush_atoms": 4})
        st = {}
        g3 = p3.acquire(pin, stages=st)
        tot = p3.counters.totals()
        check("gen-fmt/tamper-fallback",
              g3.canonical_digest() == v.canonical_digest()
              and tot["quarantines"] >= 1, (st, tot))
        p3.release(g3)
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_gen_verify_before_serve():
    from tlsys.serving import generation as gen_mod
    tl, tmp, pin, sdir, pool, v, docs = _gen_store("vbs")
    try:
        if not hasattr(pool, "publish_generation"):
            check("gen-vbs/publish-api", False, "Stage C missing?")
            return
        _publish(pool, v)
        gendir = os.path.join(sdir, "generation")
        root = gen_mod.read_root(gendir)
        # Tamper each block class at rest: open must fail closed.
        import shutil as _shutil
        for key in ("vectors.npy", "post_ord.npy", "terms.json",
                    "text.blob", "live.npy", "holon_vectors.npy"):
            backup = os.path.join(tmp, "bak-" + key)
            target = os.path.join(gendir, key)
            _shutil.copyfile(target, backup)
            with open(target, "r+b") as f:
                f.seek(10)
                b = f.read(1)
                f.seek(10)
                f.write(bytes([b[0] ^ 0x01]))
            try:
                gen_mod.GenerationReader(gendir, root)
                check(f"gen-vbs/tamper-{key}", False, "served bad bytes!")
            except gen_mod.GenerationError:
                check(f"gen-vbs/tamper-{key}", True)
            _shutil.copyfile(backup, target)
        # Tamper the root: self-digest fails closed.
        rpath = os.path.join(gendir, "generation.json")
        raw = open(rpath).read()
        open(rpath, "w").write(raw.replace(
            '"live_n": %d' % root["live_n"],
            '"live_n": %d' % (root["live_n"] + 1)))
        try:
            gen_mod.read_root(gendir)
            check("gen-vbs/tamper-root", False, "served bad root!")
        except gen_mod.GenerationError:
            check("gen-vbs/tamper-root", True)
        open(rpath, "w").write(raw)
        # In-RAM blob corruption is caught when the text is read.
        reader = gen_mod.GenerationReader(
            gendir, gen_mod.read_root(gendir))
        reader._blob = reader._blob[:5] + bytes(
            [reader._blob[5] ^ 0xFF]) + reader._blob[6:]
        try:
            reader.text_of_ord(0)
            check("gen-vbs/ram-text", False, "unverified text served!")
        except gen_mod.GenerationError:
            check("gen-vbs/ram-text", True)
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_gen_holon_latest_only():
    from tlsys.serving import generation as gen_mod
    from tlsys.serving.view import ViewPool
    tl, tmp, pin = make_store(make_docs(6, seed=51), emb_votes,
                              prefix="tlsys-c2sg-hist-")
    try:
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=None,
                        config={"delta_flush_atoms": 1000})
        v = pool.cold_build(pin)
        hid = next(iter(v.holons))
        old = dict(v.holons[hid])
        v._insert_holon(999001, "op-newer", {
            "holon": hid, "members": list(old["members"]),
            "descriptor": (old["descriptor"] + 1.0).tolist(),
            "kind": old.get("kind"),
            "children": list(old.get("children") or [])})
        out = os.path.join(tmp, "genhist")
        root, _rc = gen_mod.build_generation_blocks(v, out)
        import numpy as _np
        hids = _np.load(os.path.join(out, "holon_vectors.npy"))
        check("gen-hist/one-row-per-hid",
              len(hids) == len(v.ord_holon), (len(hids),
                                              len(v.ord_holon)))
        # Latest row persisted (descriptor + 1.0), history in the log.
        rroot = dict(root)
        rroot["digest"] = gen_mod.root_digest_of(rroot)
        import json as _json
        _json.dump(rroot, open(os.path.join(out, "generation.json"),
                               "w"), sort_keys=True)
        # NOTE: root lacks source_verification here (build-level
        # check only); the reader still verifies blocks+shapes.
        rd = gen_mod.GenerationReader(out, gen_mod.read_root(out))
        e = rd.holon_entry(hid)
        check("gen-hist/latest",
              bool((np.asarray(e["descriptor"]) ==
                    old["descriptor"] + 1.0).all()), hid)
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_gen_advance_no_copy():
    from tlsys.serving.view import ViewPool
    tl, tmp, pin, sdir, pool, v, docs = _gen_store("anc")
    try:
        if not hasattr(pool, "publish_generation"):
            check("gen-anc/publish-api", False, "Stage C missing?")
            return
        _publish(pool, v)
        pool2 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                         config={"delta_flush_atoms": 4})
        g = pool2.acquire(pin)
        ingest_docs(tl, [("d-new-1", "quasar pulsar discovery")],
                    emb_votes)
        from tlsys.maint import organize_segments
        organize_segments(tl)
        pin1 = tl.pin()
        ov_atoms_id = id(g.ov_atoms)
        reader = g._reader
        base_tomb = set(reader.retired_docs())
        g2 = pool2.advance(g, pin1)
        check("gen-anc/reader-shared", g2._reader is reader,
              "advance must share the immutable reader")
        check("gen-anc/overlay-moved", id(g2.ov_atoms) == ov_atoms_id,
              "overlay dicts move O(1), never rebuilt")
        check("gen-anc/base-tomb-shared",
              set(g2._reader.retired_docs()) == base_tomb
              and g2._reader is reader, "no tombstone copy")
        check("gen-anc/old-frozen", not g._live
              and g._snapshot is not None, g._live)
        snap_ov = sum(len(x) for x in
                      g._snapshot.get("overlay", {}).values()
                      if isinstance(x, (dict, set, list)))
        check("gen-anc/snapshot-bounded", snap_ov <= 64, snap_ov)
        # v1 advance moves (never copies) tombstones/maps/stats.
        p3 = ViewPool(tl, pin[0], pin[1], serving_dir=None,
                      config={"delta_flush_atoms": 1000})
        w = p3.cold_build(pin)
        live_set = w.tomb._live
        atoms_obj = w.atoms
        w2 = p3.advance(w, pin1)
        check("gen-anc/v1-tomb-moved", w2.tomb._live is live_set,
              "v1 advance must hand off the tomb set O(1)")
        check("gen-anc/v1-maps-moved", w2.atoms is atoms_obj,
              "v1 advance must hand off live maps O(1)")
        pool2.release(g2)
    finally:
        try:
            tl.close()
        except Exception:
            pass


STAGE_C = (test_gen_build_publish_attach,
           test_gen_no_eager_dicts,
           test_gen_format_transition,
           test_gen_verify_before_serve,
           test_gen_holon_latest_only,
           test_gen_advance_no_copy)


# -- Stage D: legs parity, debt, end-to-end --------------------------

def _entry_equal(a, b):
    if set(a) != set(b):
        return False
    for k in a:
        if k == "descriptor":
            if not (np.asarray(a[k]) == np.asarray(b[k])).all():
                return False
        elif a[k] != b[k]:
            return False
    return True


def _legs_shapes():
    """(gen view, v1 view, pin, pool, tl, tmp) across perturbations."""
    from tlsys.serving.view import ViewPool
    docs = make_docs(14, seed=61)
    tl, tmp, pin = make_store(docs, emb_votes,
                              prefix="tlsys-c2sd-legs-")
    sdir = os.path.join(tmp, "serving")
    pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                    config={"delta_flush_atoms": 4})
    v = pool.cold_build(pin)
    pool.publish_generation(v)
    out = {}
    # steady: no overlay.
    p0 = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                  config={"delta_flush_atoms": 4})
    out["steady"] = (p0.acquire(pin), v, pin, p0)
    # overlay: new suffix (atoms + holons + retire).
    ingest_docs(tl, [("d-new-2", "quasar pulsar discovery voyage"),
                     ("d-new-3", "pulsar timing array signals")],
                emb_votes)
    organize_segments(tl)
    retire_docs(tl, [docs[2][0]], reason="c2sd-legs",
                approvals={docs[2][0]: {"type": "user",
                                        "approval_id": "fx-c2sd"}})
    pin1 = tl.pin()
    p1 = ViewPool(tl, pin1[0], pin1[1], serving_dir=sdir,
                  config={"delta_flush_atoms": 4})
    g1 = p1.acquire(pin1)
    pv = ViewPool(tl, pin1[0], pin1[1], serving_dir=None,
                  config={"delta_flush_atoms": 1000})
    vv = pv.cold_build(pin1)
    out["overlay"] = (g1, vv, pin1, p1)
    out["_tl"] = (tl, tmp)
    return out


def test_legs_gen_parity():
    from tlsys.query import _dense_rank
    shapes = _legs_shapes()
    tl, tmp = shapes.pop("_tl")
    try:
        for name, (g, v, pin, _p) in shapes.items():
            ref = ReferenceNarrowIndex(tl, pin)
            for q in ("quasar pulsar", "sport medic", "alpha",
                      "nonexistent xyz"):
                check(f"legs-{name}/bm25/{q}",
                      _items_equal(g.bm25(q), ref.bm25(q)), q)
            # Mappings: keys + order + entries vs reference.
            for attr in ("atoms", "holons", "atom_text", "doc_atoms"):
                gm, rm = getattr(g, attr), getattr(ref, attr)
                check(f"legs-{name}/{attr}-keys",
                      list(gm.keys()) == list(rm.keys()), attr)
                ok = all(_entry_equal(gm[k], rm[k]) for k in rm) \
                    if attr in ("atoms", "holons") else \
                    all(gm[k] == rm[k] for k in rm)
                check(f"legs-{name}/{attr}-entries", ok, attr)
            for term in ("quasar", "sport", "alpha"):
                try:
                    want = _live_postings_ref(ref, term)
                except KeyError:
                    want = None
                try:
                    from tlsys.index import _live_postings_run
                    got = _live_postings_run(g, term)
                except KeyError:
                    got = None
                check(f"legs-{name}/postings/{term}", got == want,
                      (got, want))
            for term in ("quasar", "sport", "alpha", "missing"):
                check(f"legs-{name}/idf/{term}",
                      g.idf_live().get(term) == ref.idf.get(term),
                      term)
            check(f"legs-{name}/doclen",
                  g.doc_len_live() ==
                  {a: ref.doc_len[a] for a in ref.atoms}, name)
            check(f"legs-{name}/live-set",
                  g.live_atom_set() == frozenset(ref.atoms), name)
            check(f"legs-{name}/avgdl", g.avgdl == ref.avgdl,
                  (g.avgdl, ref.avgdl))
            check(f"legs-{name}/digest",
                  g.canonical_digest() == v.canonical_digest(), name)
            # Dense legs per-leg rule (S-4): full bitwise (steady),
            # order + 1e-12 under overlay perturbation (BLAS shape).
            qv = np.arange(8, dtype=np.float64)
            full = g.dense_atoms_full(qv)
            rids, rmat, rnorms = _ref_dense_atoms(ref)
            want_full = _dense_rank(qv, rids, rmat, rnorms)
            if name == "steady":
                check(f"legs-{name}/dense-full-bitwise",
                      full == want_full, len(full))
            else:
                check(f"legs-{name}/dense-full-order",
                      [a for a, _s in full] ==
                      [a for a, _s in want_full]
                      and max(abs(a - b) for (_x, a), (_y, b)
                              in zip(full, want_full)) <= 1e-12,
                      len(full))
            top = g.dense_atoms_topk(qv, 5)
            check(f"legs-{name}/dense-topk",
                  [a for a, _s in top] ==
                  [a for a, _s in want_full[:5]]
                  and (not top or max(
                      abs(a - b) for (_x, a), (_y, b)
                      in zip(top, want_full[:5])) <= 1e-12),
                  top)
            # Nomination maps + seg entries + eligibility.
            gal, glp = g.nomination_maps()
            check(f"legs-{name}/nom-al",
                  dict(gal) == dict(v.atom_leaves), name)
            check(f"legs-{name}/nom-lp",
                  dict(glp) == dict(v.leaf_parents), name)
            check(f"legs-{name}/seg-leaves",
                  _seg_entries_equal(g.seg_leaves, v.seg_leaves),
                  name)
            check(f"legs-{name}/seg-parents",
                  _seg_entries_equal(g.seg_parents, v.seg_parents),
                  name)
            check(f"legs-{name}/retired",
                  g.retired_docs == sorted(ref.retired_docs)
                  and g.retired_aids_set == set(ref.retired_aids),
                  name)
    finally:
        try:
            tl.close()
        except Exception:
            pass


def _live_postings_ref(ref, term):
    return ref.postings[term]


def _ref_dense_atoms(ref):
    ids = list(ref.atoms.keys())
    mat = np.stack([np.asarray(ref.atoms[i]["descriptor"],
                               dtype=np.float64) for i in ids]) \
        if ids else np.empty((0, 0))
    norms = np.linalg.norm(mat, axis=1) if ids else np.empty((0,))
    norms[norms == 0.0] = 1.0
    return ids, mat, norms


def _seg_entries_equal(a, b):
    if set(a) != set(b):
        return False
    return all(_entry_equal(a[k], b[k]) for k in a)


def test_gen_block_aware():
    """Heads without assembly/restack/sort; honest fallback counts."""
    from tlsys.serving.view import ViewPool
    shapes = _legs_shapes()
    tl, tmp = shapes.pop("_tl")
    try:
        g, _v, pin, _p = shapes["overlay"]
        qv = np.arange(8, dtype=np.float64)
        # No triple assembly on the head path (steady or perturbed).
        g._caches.pop("dense_atoms", None)
        head = g.dense_atoms_head(qv, 5)
        check("gen-block/no-assembly",
              "dense_atoms" not in g._caches, list(g._caches))
        full = g.dense_atoms_full(qv)
        check("gen-block/head-is-full-head",
              [a for a, _s in head] == [a for a, _s in full[:5]]
              and (not head or max(
                  abs(a - b) for (_x, a), (_y, b)
                  in zip(head, full[:5])) <= 1e-12),
              head)
        # Query legs take the head branch (no served-pop concat).
        served = _served_index_for(tl, pin, tmp)
        nq = NarrowQuery(tl, served, emb1)
        hv = nq._dense_holons_vec(qv, topk=4)
        check("gen-block/query-backend",
              nq.last_dense_backend == "denseserve",
              nq.last_dense_backend)
        hd = served._view.dense_holons_head(qv, 4)
        check("gen-block/query-head", hv == hd, (hv, hd))
        av = nq._dense_atoms_vec(qv, topk=4)
        ad = served._view.dense_atoms_head(qv, 4)
        check("gen-block/query-head-atoms", av == ad, (av, ad))
        # Certified topk counts honestly (fp32 scan + rescore +
        # widenings ride the view counters).
        from tlsys.serving.counters import ServeCounters
        c0 = g.counters.totals()
        g.dense_atoms_topk(qv, 5)
        c1 = g.counters.totals()
        check("gen-block/topk-counts",
              c1["dense_fp32_rows"] - c0["dense_fp32_rows"] ==
              len(g._reader.aids)
              and c1["dense_rescore_rows"] -
              c0["dense_rescore_rows"] > 0, (c0, c1))
    finally:
        try:
            tl.close()
        except Exception:
            pass


def _served_index_for(tl, pin, tmp):
    """C2 NarrowIndex over the serving dir in tmp (gen route)."""
    return NarrowIndex(tl, pin,
                       serving_dir=os.path.join(tmp, "serving"))


def test_gen_debt_bounds():
    from tlsys.serving.view import ViewPool
    from tlsys.serving import generation as gen_mod
    docs = make_docs(10, seed=71)
    tl, tmp, pin = make_store(docs, emb_votes,
                              prefix="tlsys-c2sd-debt-")
    try:
        sdir = os.path.join(tmp, "serving")
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                        config={"delta_flush_atoms": 4,
                                "gen_overlay_max_atoms": 2,
                                "gen_overlay_max_holons": 100,
                                "gen_overlay_max_edges": 100000})
        v = pool.cold_build(pin)
        pool.publish_generation(v)
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                        config={"delta_flush_atoms": 4,
                                "gen_overlay_max_atoms": 2,
                                "gen_overlay_max_holons": 100,
                                "gen_overlay_max_edges": 100000})
        g = pool.acquire(pin)
        assert type(g).__name__ == "GenerationView", type(g).__name__
        # Debt metrics cover atoms AND holons AND edges AND bytes.
        dm = gen_mod.debt_metrics_for_view(v)
        check("gen-debt/metrics",
              dm["atom_rows"] > 0 and dm["holon_rows"] > 0
              and "edges" in dm and "mat_bytes" in dm, dm)
        # Push the overlay past the atom bound -> auto-rebase.
        ingest_docs(tl, [(f"d-ov-{i}", f"quasar pulsar ledger {i}")
                         for i in range(4)], emb_votes)
        organize_segments(tl)
        pin1 = tl.pin()
        d0 = g.canonical_digest()
        g2 = pool.advance(g, pin1)
        rb = getattr(g2, "_last_rebase", None) or {}
        check("gen-debt/rebase-published",
              rb.get("status") == "published"
              and rb.get("bounds_hit") == ["atom_rows"]
              and "maint_counters" in rb, rb)
        check("gen-debt/overlay-reset",
              len(g2.delta.atom_rows) == 0
              and len(g2.ov_atoms) == 0
              and g2._reader.root["frontier"] == pin1[2],
              (len(g2.delta.atom_rows), len(g2.ov_atoms)))
        check("gen-debt/serving-current",
              "quasar" in g2.df and g2.live_n > 0, g2.live_n)
        st = pool.stats()
        check("gen-debt/stats",
              st["current_kind"] == "generation"
              and "overlay_debt" in (st["generation"] or {}), st)
        # Tiny time budget -> abort receipted, serving stays
        # correct on the overlay, debt explicit.
        pool2 = ViewPool(tl, pin1[0], pin1[1], serving_dir=sdir,
                         config={"delta_flush_atoms": 4,
                                 "gen_overlay_max_atoms": 1,
                                 "maint_time_budget_s": 1e-9})
        h = pool2.acquire(pin1)
        ingest_docs(tl, [("d-ov-9", "pulsar quasar horizon"),
                         ("d-ov-10", "quasar horizon survey")],
                    emb_votes)
        organize_segments(tl)
        pin2 = tl.pin()
        h2 = pool2.advance(h, pin2)
        rb2 = getattr(h2, "_last_rebase", None) or {}
        check("gen-debt/abort",
              rb2.get("status") == "aborted"
              and len(h2.delta.atom_rows) > 0, rb2)
        ref = ReferenceNarrowIndex(tl, pin2)
        check("gen-debt/abort-serving",
              _items_equal(h2.bm25("pulsar quasar"),
                           ref.bm25("pulsar quasar")), "overlay serves")
        pool.release(g2)
        pool2.release(h2)
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_gen_rebase_safety():
    from tlsys.serving.view import ViewPool
    from tlsys.serving import generation as gen_mod
    docs = make_docs(10, seed=73)
    tl, tmp, pin = make_store(docs, emb_votes,
                              prefix="tlsys-c2sd-rsaf-")
    try:
        sdir = os.path.join(tmp, "serving")
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                        config={"delta_flush_atoms": 4,
                                "gen_overlay_max_atoms": 2})
        v = pool.cold_build(pin)
        pool.publish_generation(v)
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                        config={"delta_flush_atoms": 4,
                                "gen_overlay_max_atoms": 2})
        g = pool.acquire(pin)
        assert type(g).__name__ == "GenerationView", type(g).__name__
        d_old = g.canonical_digest()
        ingest_docs(tl, [(f"d-rb-{i}", f"quasar ledger {i}")
                         for i in range(3)], emb_votes)
        organize_segments(tl)
        pin1 = tl.pin()
        g2 = pool.advance(g, pin1)  # triggers rebase (bound 2)
        rb = getattr(g2, "_last_rebase", None) or {}
        check("gen-rsaf/rebase", rb.get("status") == "published", rb)
        # Old-pin reader: frozen base still serves its pin exactly.
        check("gen-rsaf/old-frozen", not g._live, g._live)
        check("gen-rsaf/old-digest", g.canonical_digest() == d_old,
              "straggler must serve its pin")
        # Retained previous generation on disk (reader safety).
        retained = os.path.join(sdir, "generations")
        check("gen-rsaf/retained",
              os.path.isdir(retained) and
              any(n.startswith("gen-") for n in os.listdir(retained)),
              os.listdir(retained) if os.path.isdir(retained) else [])
        # Fresh attach at the new pin == rebased view (digest).
        pool3 = ViewPool(tl, pin1[0], pin1[1], serving_dir=sdir,
                         config={"delta_flush_atoms": 4})
        g3 = pool3.acquire(pin1)
        check("gen-rsaf/fresh",
              g3.canonical_digest() == g2.canonical_digest()
              and type(g3).__name__ == "GenerationView",
              type(g3).__name__)
        pool.release(g2)
        pool3.release(g3)
    finally:
        try:
            tl.close()
        except Exception:
            pass


def test_e2e_gen_answer():
    """edit/publish/fresh-process-reader/answer: source, pin,
    coverage, parity, corruption; warm vs cold measured separately."""
    import subprocess
    docs = make_docs(12, seed=83)
    tl, tmp, pin = make_store(docs, emb_votes,
                              prefix="tlsys-c2sd-e2e-")
    try:
        from tlsys.serving.view import ViewPool
        sdir = os.path.join(tmp, "serving")
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                        config={"delta_flush_atoms": 4})
        v = pool.cold_build(pin)
        pool.publish_generation(v)
        # Edit after publish: new evidence + retirement.
        ingest_docs(tl, [("d-e2e-0", "quasar pulsar e2e voyage")],
                    emb_votes)
        organize_segments(tl)
        retire_docs(tl, [docs[0][0]], reason="c2sd-e2e",
                    approvals={docs[0][0]: {"type": "user",
                                            "approval_id": "fx-e2e"}})
        pin1 = tl.pin()
        script = os.path.join(tmp, "fresh_reader.py")
        with open(script, "w") as f:
            f.write(_FRESH_READER_SRC)
        out = os.path.join(tmp, "fresh.json")
        # The store fence is single-holder: release before the
        # fresh process opens it, reopen after (same bytes).
        tl.close()
        t0 = time.time()
        r = subprocess.run(
            [sys.executable, script, ROOT, tmp, pin1[0], str(pin1[1]),
             str(pin1[2]), docs[0][0], out], capture_output=True,
            text=True, timeout=300,
            env=dict(os.environ, HF_HUB_OFFLINE="1",
                     PYTHONHASHSEED="0", OPENBLAS_NUM_THREADS="1",
                     OMP_NUM_THREADS="1", MKL_NUM_THREADS="1"))
        tl = TLStore(os.path.join(tmp, "store"), create=False,
                     lease_owner="test-c2sd-e2e-reopen")
        cold_ms = (time.time() - t0) * 1000.0
        check("gen-e2e/fresh-process", r.returncode == 0,
              (r.returncode, r.stderr[-2000:]))
        if r.returncode != 0:
            return
        with open(out) as f:
            fresh = json.load(f)
        with open(os.path.join(
                GOLDEN_DIR, "c2s-e2e-fresh.json"), "w") as f:
            json.dump({"cold_ms": cold_ms, "fresh": fresh}, f,
                      sort_keys=True)
        # Pin + source correspondence.
        check("gen-e2e/pin",
              fresh["triple"] == [pin1[0], pin1[1], pin1[2]],
              fresh.get("triple"))
        check("gen-e2e/source-texts",
              fresh["texts_verified"] == fresh["texts_live"]
              and fresh["texts_live"] > 0, fresh)
        # Coverage: suffix evidence searchable, retired excluded.
        check("gen-e2e/coverage",
              fresh["suffix_hit"] and fresh["retired_excluded"],
              fresh)
        # Parity vs in-process reference answer (overlay window:
        # same admitted multiset + 1e-9 scores; exact order is
        # recorded, bitwise only in steady state — BLAS shape).
        ref = ReferenceNarrowIndex(tl, pin1)
        nq = NarrowQuery(tl, ref, emb1)
        dos, _rec = nq.run("quasar pulsar")
        got_aids = [e["atom_id"] for e in dos["entries"]]
        got_scores = [e["emitted_score"] for e in dos["entries"]]
        exact = got_aids == fresh["entry_aids"] and \
            got_scores == fresh["entry_scores"]
        print(f"e2e overlay-window exact-order: {exact}")
        check("gen-e2e/parity",
              sorted(got_aids) == sorted(fresh["entry_aids"])
              and len(got_scores) == len(fresh["entry_scores"])
              and (not got_scores or max(
                  abs(a - b) for a, b in zip(
                      sorted(got_scores), sorted(
                          fresh["entry_scores"]))) <= 1e-9),
              fresh)
        # Warm attach in-process (repeat open; page-cache warm).
        pool2 = ViewPool(tl, pin1[0], pin1[1], serving_dir=sdir,
                         config={"delta_flush_atoms": 4})
        w0 = time.time()
        gw = pool2.acquire(pin1)
        warm_ms = (time.time() - w0) * 1000.0
        check("gen-e2e/warm", gw.canonical_digest() ==
              fresh["digest"], warm_ms)
        pool2.release(gw)
        with open(os.path.join(
                GOLDEN_DIR, "c2s-e2e-warmcold.json"), "w") as f:
            json.dump({"fresh_process_ms": cold_ms,
                       "warm_attach_ms": warm_ms,
                       "note": "fresh-process ~ cold-ish (page cache "
                       "may persist); true storage-cold needs "
                       "drop_caches (root) — see REPORT method note"},
                      f, sort_keys=True)
        print(f"e2e warm/cold: fresh-process={cold_ms:.1f}ms "
              f"warm-attach={warm_ms:.1f}ms")
    finally:
        try:
            tl.close()
        except Exception:
            pass


_FRESH_READER_SRC = '''
import json, os, sys
root, tmp, birth, epoch, mx, retired_doc, out = sys.argv[1:8]
mx = int(mx)
epoch = int(epoch)
sys.path.insert(0, os.path.join(root, "tl-sys"))
from tlsys.store_if import TLStore
from tlsys.serving.view import ViewPool
from tlsys.query import NarrowQuery
tl = TLStore(os.path.join(tmp, "store"), create=False,
             lease_owner="test-c2sd-fresh")
pin = tl.pin()
assert (pin[0], pin[1], pin[2]) == (birth, epoch, mx), (pin, birth)
pool = ViewPool(tl, birth, epoch,
                serving_dir=os.path.join(tmp, "serving"),
                config={"delta_flush_atoms": 4})
stages = {}
g = pool.acquire(pin, stages=stages)
assert type(g).__name__ == "GenerationView", type(g).__name__
# Source correspondence: every live text verifies against its pin.
n_live = n_ok = 0
for aid in g.atoms:
    n_live += 1
    e = g.atoms[aid]
    body = tl.read_artifact(e["text_art"],
                            expect_digest=e["text_digest"])
    assert body.decode("utf-8") == g.atom_text[aid]
    n_ok += 1
suffix_hit = "quasar" in g.df and len(g.bm25("quasar pulsar")) > 0
retired_excluded = all(
    e.get("doc_id") != retired_doc for e in g.atoms.values()) \\
    and retired_doc not in list(g.doc_atoms.keys()) \\
    and retired_doc in g.retired_docs
from tlsys.index import NarrowIndex
idx = NarrowIndex(tl, pin, serving_dir=os.path.join(tmp, "serving"))
DIMS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
        "sport", "medic"]
def vec(t):
    t = t.lower()
    out = [1.0 if w in t else 0.0 for w in DIMS]
    return out if any(out) else [0.2] * len(DIMS)
nq2 = NarrowQuery(tl, idx, vec)
dos, rec = nq2.run("quasar pulsar")
with open(out, "w") as f:
    json.dump({"kind": type(g).__name__, "digest": g.canonical_digest(),
               "triple": [pin[0], pin[1], pin[2]],
               "texts_live": n_live, "texts_verified": n_ok,
               "suffix_hit": bool(suffix_hit),
               "retired_excluded": bool(retired_excluded),
               "entry_aids": [e["atom_id"] for e in dos["entries"]],
               "entry_scores": [e["emitted_score"] for e in dos["entries"]],
               "stages": stages}, f, sort_keys=True)
print("fresh ok")
'''


def test_shapes_gen_regression():
    """All query shapes: gen backend == v1 backend, same pin."""
    tl, root, pin = _plain_store()
    try:
        from tlsys.serving.view import ViewPool
        sdir = os.path.join(root, "serving")
        pool = ViewPool(tl, pin[0], pin[1], serving_dir=sdir,
                        config={"delta_flush_atoms": 4})
        v = pool.cold_build(pin)
        pool.publish_generation(v)
        idx_v1 = NarrowIndex(tl, pin)
        idx_gen = NarrowIndex(tl, pin, serving_dir=sdir)
        assert type(idx_gen._view).__name__ == "GenerationView"
        aid2role = _aid_map(idx_v1)
        payload = {}
        for tag, idx in (("v1", idx_v1), ("gen", idx_gen)):
            sub = {}
            for q in ("alpha bravo", "sport athletics"):
                nq = NarrowQuery(tl, idx, emb1)
                dos, rec = nq.run(q)
                sub[f"narrow/{q}"] = {"entries": dos["entries"],
                                     "receipt": rec}
            nq = NarrowQuery(tl, idx, emb1, cfg=dict(REL_CFG))
            dos, rec = nq.run("alpha bravo")
            sub["narrow-relcfg"] = {"entries": dos["entries"],
                                    "receipt": rec}
            nq = NarrowQuery(tl, idx, emb1, cfg={"HIER_GUIDED": True})
            dos, rec = nq.run("sport athletics")
            sub["hier-guided"] = {"entries": dos["entries"],
                                  "receipt": rec}
            for name, cfg in (
                    ("relational", {"DOSSIER_SHAPE": "relational"}),
                    ("relational-trav",
                     {"DOSSIER_SHAPE": "relational",
                      "DOSSIER_REL_TRAVERSAL": True,
                      "DOSSIER_REL_HOPS": 1}),
                    ("cross-topic",
                     {"DOSSIER_SHAPE": "cross-topic"})):
                dq = DossierQuery(tl, idx, emb1, cfg=dict(cfg))
                if name == "cross-topic":
                    dos, rec = dq.run("alpha",
                                      topics=["alpha", "bravo"])
                else:
                    dos, rec = dq.run("alpha bravo")
                sub[name] = {"entries": dos["entries"],
                             "receipt": rec}
            payload[tag] = canon_payload(sub, aid2role, pin[0])
        a = norm_run(payload["v1"])
        b = norm_run(payload["gen"])
        check("gen-shapes/backend-identical", a == b,
              _first_div(a, b))
        # Relational pair legs engage identically on both backends.
        tl2, _r2, pin2, _trio = _rel_store()
        try:
            sdir2 = os.path.join(_r2, "serving")
            pool2 = ViewPool(tl2, pin2[0], pin2[1],
                             serving_dir=sdir2,
                             config={"delta_flush_atoms": 4})
            pool2.publish_generation(pool2.cold_build(pin2))
            i1 = NarrowIndex(tl2, pin2)
            i2 = NarrowIndex(tl2, pin2, serving_dir=sdir2)
            assert type(i2._view).__name__ == "GenerationView"
            outs = []
            for idx in (i1, i2):
                nq = NarrowQuery(tl2, idx, emb1,
                                 cfg=dict(REL_CFG))
                dos, rec = nq.run("delta foxtrot scope as-stated")
                outs.append(canon_payload(
                    {"entries": dos["entries"], "receipt": rec},
                    _aid_map(i1), pin2[0]))
            check("gen-shapes/pair-legs-identical",
                  norm_run(outs[0]) == norm_run(outs[1]),
                  _first_div(norm_run(outs[0]), norm_run(outs[1])))
            blob = json.dumps(outs[1], sort_keys=True, default=str)
            check("gen-shapes/v1-engaged", "prune_units" in blob,
                  "pair legs must engage V1 on gen too")
        finally:
            try:
                tl2.close()
            except Exception:
                pass
    finally:
        try:
            tl.close()
        except Exception:
            pass


def _first_div(a, b, limit=300):
    sa = json.dumps(a, sort_keys=True, default=str)
    sb = json.dumps(b, sort_keys=True, default=str)
    if sa == sb:
        return ""
    for i, (x, y) in enumerate(zip(sa, sb)):
        if x != y:
            return (f"bytes {len(sa)} vs {len(sb)}; firstdiv @{i}: "
                    f"{sa[max(0, i-80):i+80]!r}")
    return f"prefix-equal; lengths {len(sa)} vs {len(sb)}"


STAGE_D = (test_legs_gen_parity,
           test_gen_block_aware,
           test_gen_debt_bounds,
           test_gen_rebase_safety,
           test_e2e_gen_answer,
           test_shapes_gen_regression)


def main():
    import traceback
    for fn in STAGE_A + STAGE_B + STAGE_C + STAGE_D:
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=6))
    print("scratch: /tmp/tl-c2s-*")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
