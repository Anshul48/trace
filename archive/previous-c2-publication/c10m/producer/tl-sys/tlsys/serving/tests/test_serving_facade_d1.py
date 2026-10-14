"""Lane S D1: facade vs ReferenceNarrowIndex at identical pins.

Surface (atoms/holons/atom_text/doc_atoms/seg_*/retired_*/postings/idf/
avgdl/doc_len), legs (bm25/bitwise, fullscan, dense loop-identical,
_dense_rank path), class outputs (Narrow/Hier/Dossier/Rel-flag line),
advance_to hops, post-build mutation, backend selection.

Run: tl-sys/.venv/bin/python tl-sys/tlsys/serving/tests/test_serving_facade_d1.py
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from fixture import (  # noqa: E402
    emb_votes, fixture_approval, make_docs, make_store)
from tlsys.index import (  # noqa: E402
    NarrowIndex, ReferenceNarrowIndex)
from tlsys.query import HierQuery, NarrowQuery, _dense_rank  # noqa: E402
from tlsys.dossier import DossierQuery  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


QUERIES = [
    "the domestic cat",
    "sport medic fuse",
    "alpha beta gamma delta",
    "the the the",  # repeats + stopwords
    "zxqy unknownword",  # unknown terms
    "",  # empty
    "SPORT Sport sport",  # case folding
    "w1x5 w2x9",
]


def emb1(q):
    return emb_votes([q])[0]


def build_fixture():
    docs = make_docs(24, seed=61, dup_every=7)
    docs = [(f"f-{i}", t) for i, (_d, t) in enumerate(docs)]
    tl, tmp, pin = make_store(docs, emb_votes, retire=["f-1", "f-9"],
                              organize=True, prefix="tlsys-lanes-d1-")
    return tl, tmp, pin


_VOLATILE = ("ms", "T_ms", "wall_s", "elapsed", "t_query_s")


def norm(obj):
    if isinstance(obj, dict):
        return {k: norm(v) for k, v in obj.items()
                if k not in _VOLATILE}
    if isinstance(obj, (list, tuple)):
        return [norm(v) for v in obj]
    return obj


def first_diff(a, b, path="$"):
    if type(a) is not type(b):
        return f"{path}: type {type(a)} vs {type(b)}"
    if isinstance(a, dict):
        if set(a) != set(b):
            return f"{path}: keys {set(a) ^ set(b)}"
        for k in a:
            d = first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return f"{path}: len {len(a)} vs {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    if isinstance(a, float) and isinstance(b, float):
        if a != b:
            return f"{path}: {a!r} vs {b!r}"
        return None
    if a != b:
        return f"{path}: {a!r} vs {b!r}"
    return None


def test_surface_and_legs():
    tl, _tmp, pin = build_fixture()
    ref = ReferenceNarrowIndex(tl, pin)
    fac = NarrowIndex(tl, pin)
    check("d1-atoms-keys", set(fac.atoms) == set(ref.atoms))
    check("d1-atoms-order", list(fac.atoms) == list(ref.atoms))
    ok = True
    for aid in ref.atoms:
        a, b = ref.atoms[aid], fac.atoms[aid]
        if (a["seq"], a["doc_id"], tuple(a["span"]), a["text_art"],
                a["text_digest"]) != (
                b["seq"], b["doc_id"], tuple(b["span"]), b["text_art"],
                b["text_digest"]) or not bool(np.all(
                    np.asarray(a["descriptor"]) ==
                    np.asarray(b["descriptor"]))):
            ok = False
            break
    check("d1-atoms-entries", ok)
    check("d1-holons", list(fac.holons) == list(ref.holons))
    ok = True
    for hid in ref.holons:
        a, b = ref.holons[hid], fac.holons[hid]
        if (a["seq"], a["members"], a.get("kind"),
                list(a.get("children") or [])) != (
                b["seq"], b["members"], b.get("kind"),
                list(b.get("children") or [])) or not bool(np.all(
                    np.asarray(a["descriptor"]) ==
                    np.asarray(b["descriptor"]))):
            ok = False
            break
    check("d1-holons-entries", ok)
    check("d1-atom-text", dict(fac.atom_text) == dict(ref.atom_text))
    check("d1-atom-text-order",
          list(fac.atom_text) == list(ref.atom_text))
    check("d1-doc-atoms", dict(fac.doc_atoms) == dict(ref.doc_atoms))
    check("d1-seg-leaves", set(fac.seg_leaves) == set(ref.seg_leaves),
          f"{len(ref.seg_leaves)} leaves")
    check("d1-seg-parents",
          set(fac.seg_parents) == set(ref.seg_parents),
          f"{len(ref.seg_parents)} parents")
    check("d1-retired-docs", fac.retired_docs == ref.retired_docs)
    check("d1-retired-atoms", fac.retired_atoms == ref.retired_atoms)
    check("d1-retired-aids", fac.retired_aids == ref.retired_aids)
    check("d1-avgdl", fac.avgdl == ref.avgdl, repr(ref.avgdl))
    check("d1-idf", dict(fac.idf) == ref.idf)
    check("d1-doc-len", dict(fac.doc_len) == ref.doc_len)
    check("d1-postings-content",
          {t: fac.postings[t] for t in ref.postings} == ref.postings)
    check("d1-postings-keys", set(fac.postings) == set(ref.postings))
    check("d1-idf-bitwise",
          all(fac.idf[t] == ref.idf[t] for t in ref.idf))
    for q in QUERIES:
        b1, b2 = ref.bm25(q), fac.bm25(q)
        ok = (set(b1) == set(b2) and list(b1) == list(b2)
              and all(b1[a] == b2[a] for a in b1))
        check(f"d1-bm25:{q[:18]!r}", ok)
        f1, f2 = ref.bm25_fullscan(q), fac.bm25_fullscan(q)
        ok = (set(f1) == set(f2) and list(f1) == list(f2)
              and all(f1[a] == f2[a] for a in f1))
        check(f"d1-fullscan:{q[:18]!r}", ok)
    qv = np.arange(8, dtype=np.float64)
    check("d1-dense-atoms", ref.dense_atoms(qv) == fac.dense_atoms(qv))
    check("d1-dense-holons",
          ref.dense_holons(qv) == fac.dense_holons(qv))
    # The _dense_rank product path (query._dense_pop + _dense_rank).
    nqr, nqf = NarrowQuery(tl, ref, emb1), NarrowQuery(tl, fac, emb1)
    for which in ("holons", "atoms"):
        ir, mr, nr = nqr._dense_pop(which)
        iq, mq, nq = nqf._dense_pop(which)
        check(f"d1-densepop-{which}",
              ir == iq and bool(np.all(mr == mq))
              and bool(np.all(nr == nq)))
    r1 = _dense_rank(qv, *nqr._dense_pop("atoms"))
    r2 = _dense_rank(qv, *nqf._dense_pop("atoms"))
    check("d1-denserank-atoms", r1 == r2)
    # Mapping protocol: reversed/len/contains/get (audit caches).
    for name in ("atoms", "holons", "atom_text", "doc_atoms"):
        m, d = getattr(fac, name), getattr(ref, name)
        check(f"d1-map-{name}",
              list(reversed(m)) == list(reversed(list(d)))
              and len(m) == len(d)
              and all((k in m) for k in d))
    check("d1-live-set",
          fac.live_atom_set() == frozenset(ref.atoms)
          and ref.live_atom_set() == frozenset(ref.atoms))
    tl.close()


def test_class_outputs():
    tl, _tmp, pin = build_fixture()
    ref = ReferenceNarrowIndex(tl, pin)
    fac = NarrowIndex(tl, pin)
    for q in QUERIES[:5]:
        dr, rr = NarrowQuery(tl, ref, emb1).run(q)
        dq, rq = NarrowQuery(tl, fac, emb1).run(q)
        d = first_diff(norm(dr), norm(dq))
        check(f"d1-narrow-dos:{q[:14]!r}", d is None, d or "")
        d = first_diff(norm(rr), norm(rq))
        check(f"d1-narrow-rec:{q[:14]!r}", d is None, d or "")
    # REL-flag line (query.py:602 live_atom_set path).
    dr, rr = NarrowQuery(tl, ref, emb1,
                         cfg={"REL_QUALIFIERS": True}).run(QUERIES[0])
    dq, rq = NarrowQuery(tl, fac, emb1,
                         cfg={"REL_QUALIFIERS": True}).run(QUERIES[0])
    d = first_diff(norm(dr), norm(dq))
    check("d1-narrow-rel-dos", d is None, d or "")
    d = first_diff(norm(rr), norm(rq))
    check("d1-narrow-rel-rec", d is None, d or "")
    # Hier guided (exact + bounded nomination) and flat.
    hr, hq = HierQuery(tl, ref, emb1), HierQuery(tl, fac, emb1)
    for kw in ({}, {"parent_budget": 2}):
        r1, p1 = hr.guided(QUERIES[1], top_parents=3, top_children=3,
                           top_atoms=5, **kw)
        r2, p2 = hq.guided(QUERIES[1], top_parents=3, top_children=3,
                           top_atoms=5, **kw)
        d = first_diff(r1, r2)
        check(f"d1-hier-guided{kw}", d is None, d or "")
        d = first_diff(p1, p2)
        check(f"d1-hier-guided-rep{kw}", d is None, d or "")
    r1, p1 = hr.flat(QUERIES[1], total_budget=6, top_atoms=5)
    r2, p2 = hq.flat(QUERIES[1], total_budget=6, top_atoms=5)
    d = first_diff((r1, p1), (r2, p2))
    check("d1-hier-flat", d is None, d or "")
    # Delegation cache semantics: second call is a hit on both.
    hq2 = HierQuery(tl, fac, emb1)
    b1 = hq2._nomination_maps(fac.seg_leaves, fac.seg_parents)
    b2 = hq2._nomination_maps(fac.seg_leaves, fac.seg_parents)
    check("d1-nomap-cache", (b1, b2) == (True, False), f"{b1},{b2}")
    # Dossier.
    dr, rr = DossierQuery(tl, ref, emb1).run(QUERIES[0])
    dq, rq = DossierQuery(tl, fac, emb1).run(QUERIES[0])
    d = first_diff(norm(dr), norm(dq))
    check("d1-dossier-dos", d is None, d or "")
    d = first_diff(norm(rr), norm(rq))
    check("d1-dossier-rec", d is None, d or "")
    tl.close()


def test_advance_hops():
    tl, _tmp, pin1 = build_fixture()
    fac = NarrowIndex(tl, pin1)
    nq = NarrowQuery(tl, fac, emb1)
    am, hm = fac.atoms, fac.holons
    docs2 = make_docs(4, seed=62)
    docs2 = [(f"g-{i}", t) for i, (_d, t) in enumerate(docs2)]
    ingest_docs(tl, docs2, emb_votes)
    pin2 = tl.pin()
    fac.advance_to(pin2)
    ref2 = ReferenceNarrowIndex(tl, pin2)
    check("d1-hop-mappings-stable", fac.atoms is am and fac.holons is hm)
    check("d1-hop-atoms", set(fac.atoms) == set(ref2.atoms)
          and list(fac.atoms) == list(ref2.atoms))
    check("d1-hop-avgdl", fac.avgdl == ref2.avgdl)
    for q in QUERIES[:4]:
        b1, b2 = ref2.bm25(q), fac.bm25(q)
        check(f"d1-hop-bm25:{q[:14]!r}",
              set(b1) == set(b2) and list(b1) == list(b2)
              and all(b1[a] == b2[a] for a in b1))
    # Same query objects work across the hop (caches rebuild).
    dr, rr = NarrowQuery(tl, ref2, emb1).run(QUERIES[0])
    dq, rq = nq.run(QUERIES[0])
    d = first_diff((norm(dr), norm(rr)), (norm(dq), norm(rq)))
    check("d1-hop-narrow", d is None, d or "")
    # Rewind hop routes to ancestor/cold and matches.
    fac.advance_to(pin1)
    ref1 = ReferenceNarrowIndex(tl, pin1)
    check("d1-hop-rewind", set(fac.atoms) == set(ref1.atoms)
          and fac.avgdl == ref1.avgdl
          and fac.bm25(QUERIES[0]) == ref1.bm25(QUERIES[0]))
    # Reference-backend hop rebuilds in place.
    facr = NarrowIndex(tl, pin1, use_reference=True)
    facr.advance_to(pin2)
    check("d1-hop-ref", set(facr.atoms) == set(ref2.atoms)
          and facr.bm25(QUERIES[0]) == ref2.bm25(QUERIES[0]))
    tl.close()


def test_mutation_and_backends():
    tl, _tmp, pin = build_fixture()
    fac = NarrowIndex(tl, pin)
    d0 = fac.serving_view.canonical_digest()
    # r8b pattern: holon add/del + note + exact leg.
    fac.holons["docFRESH"] = {"seq": 9999, "op_id": "x",
                              "members": ["aX"],
                              "descriptor": np.array(
                                  [1.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0])}
    check("d1-mut-add-visible", "docFRESH" in fac.holons)
    names = [h for h, _s in fac.dense_holons([1.0] + [0.0] * 7)]
    check("d1-mut-add-scored", "docFRESH" in names)
    del fac.holons["docFRESH"]
    fac.note_population_changed("holons")
    check("d1-mut-del-restores",
          fac.serving_view.canonical_digest() == d0)
    # Atom add (with consistent text) then del.
    aids_before = set(fac.atoms)
    fac.atoms["aidFRESH"] = {"seq": 9999, "op_id": "y",
                             "doc_id": "docFRESH",
                             "span": [0, 1], "text_art": "t",
                             "text_digest": "g",
                             "descriptor": np.array([0.0] * 8)}
    fac.atom_text["aidFRESH"] = "zxqy freshword"
    fac.doc_atoms["docFRESH"] = ["aidFRESH"]
    got = fac.bm25("zxqy freshword")
    check("d1-mut-atom-scored", "aidFRESH" in got and got["aidFRESH"] > 0)
    del fac.atoms["aidFRESH"]
    del fac.atom_text["aidFRESH"]
    del fac.doc_atoms["docFRESH"]
    check("d1-mut-atom-restores",
          set(fac.atoms) == aids_before
          and fac.serving_view.canonical_digest() == d0)
    # Backend selection matrix.
    check("d1-backend-default",
          isinstance(NarrowIndex(tl, pin).atoms, dict) is False)
    check("d1-backend-arg",
          isinstance(NarrowIndex(tl, pin, use_reference=True).atoms,
                     dict))
    os.environ["TL_C2_REFERENCE_INDEX"] = "1"
    try:
        check("d1-backend-env",
              isinstance(NarrowIndex(tl, pin).atoms, dict))
        check("d1-backend-arg-beats-env",
              isinstance(NarrowIndex(tl, pin, use_reference=False).atoms,
                         dict) is False)
    finally:
        del os.environ["TL_C2_REFERENCE_INDEX"]
    sys.path.insert(0, os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
        "..", "coordination", "c2-work-20261006T1925Z", "lane-G")))
    import profile as lane_g_profile
    prof = lane_g_profile.default_profile("d1-test")
    check("d1-backend-profile-false",
          isinstance(NarrowIndex(tl, pin, profile=prof).atoms, dict))
    prof["flags"]["serving_segmented"] = True
    check("d1-backend-profile-true",
          isinstance(NarrowIndex(tl, pin, profile=prof).atoms, dict)
          is False)
    tl.close()


class FakeSearch:
    """Deterministic stand-in for HolonCandidateIndex (no hnswlib).

    Implements the protocol the via-search legs consume: n,
    generation, coverage(live), query(...). Returns the first k
    indexed ids (insertion order); audits seqs exactly.
    """

    def __init__(self, hids, generation, seqs):
        self._hids = list(hids)
        self.generation = generation
        self._seq = dict(seqs)
        self.n = len(hids)

    def coverage(self, live):
        live_ids = set(live.keys())
        indexed = set(self._hids)
        stale = sorted(h for h in indexed
                       if h not in live
                       or live[h].get("seq") != self._seq.get(h))
        return {"indexed": len(indexed), "live": len(live_ids),
                "stale": stale,
                "unpublished": sorted(live_ids - indexed)}

    def query(self, qvec=None, k=200, ef=None, generation=None,
              live=None):
        if generation != self.generation:
            raise ValueError("stale generation (fake)")
        return {"k": k, "ef": ef, "ms": 0.0,
                "hids": list(self._hids)[:max(0, int(k))],
                "stale_dropped": 0, "n_scored_native_unknown": 0}


def test_via_search_with_fake():
    tl, _tmp, pin = build_fixture()
    ref = ReferenceNarrowIndex(tl, pin)
    fac = NarrowIndex(tl, pin)
    qv = [1.0] + [0.0] * 7
    for which, leg in (("holons", "dense_holons"),
                       ("atoms", "dense_atoms")):
        pop = getattr(ref, which)
        seqs = {h: pop[h]["seq"] for h in pop}
        sr = FakeSearch(list(pop.keys()), ref.triple, seqs)
        sf = FakeSearch(list(pop.keys()), fac.triple, seqs)
        if which == "holons":
            ref.attach_candidate_search(sr)
            fac.attach_candidate_search(sf)
        else:
            ref.attach_atom_search(sr)
            fac.attach_atom_search(sf)
        exact_r = getattr(ref, leg)(qv, candidate_search=None)
        exact_f = getattr(fac, leg)(qv, candidate_search=None)
        check(f"d1-via-exact-{which}", exact_r == exact_f)
        via_r = getattr(ref, leg)(qv, candidate_k=len(pop))
        via_f = getattr(fac, leg)(qv, candidate_k=len(pop))
        check(f"d1-via-parity-{which}", via_r == via_f)
        check(f"d1-via-equals-exact-{which}", via_f == exact_f)
        # r8b pattern on the facade: add detected without a bump.
        key = "docFRESH" if which == "holons" else "aidFRESH"
        entry = {"seq": 9999, "op_id": "x", "members": ["aX"],
                 "descriptor": np.array([1.0] + [0.0] * 7)}
        if which == "atoms":
            entry.update({"doc_id": "docFRESH", "span": [0, 1],
                          "text_art": "t", "text_digest": "g"})
            fac.atom_text[key] = "freshword zxqy"
        getattr(fac, which)[key] = entry
        getattr(fac, leg)(qv, candidate_k=len(pop) + 1)
        rep = (fac.last_candidate_report if which == "holons"
               else fac.last_atom_candidate_report)
        check(f"d1-via-add-detected-{which}",
              rep["audit_cached"] is False
              and rep["unpublished"] == [key], repr(rep))
        del getattr(fac, which)[key]
        if which == "atoms":
            del fac.atom_text[key]
        fac.note_population_changed(which)
        getattr(fac, leg)(qv, candidate_k=len(pop))
        rep = (fac.last_candidate_report if which == "holons"
               else fac.last_atom_candidate_report)
        check(f"d1-via-bump-clean-{which}",
              rep["audit_cached"] is False
              and rep["unpublished"] == [], repr(rep))
        if which == "holons":
            ref.detach_candidate_search()
            fac.detach_candidate_search()
        else:
            ref.detach_atom_search()
            fac.detach_atom_search()
    tl.close()


def main():
    import traceback
    for fn in (test_surface_and_legs, test_class_outputs,
               test_advance_hops, test_mutation_and_backends,
               test_via_search_with_fake):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=6))
    print("scratch: /tmp/tlsys-lanes-d1-*")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
