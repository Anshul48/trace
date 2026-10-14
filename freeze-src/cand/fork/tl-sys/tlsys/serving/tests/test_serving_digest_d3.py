"""Lane S D3: incremental == cold canonical digest at the same pin +
I1 membership (every eligible atom indexed in lexical+dense legs).

Run: tl-sys/.venv/bin/python tl-sys/tlsys/serving/tests/test_serving_digest_d3.py
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from fixture import (  # noqa: E402
    UnitNormEmbed, emb_votes, fixture_approval, make_docs, make_store)
from tlsys.serving import compact as compact_mod  # noqa: E402
from tlsys.serving.digest import canonical_digest  # noqa: E402
from tlsys.serving.view import ViewPool  # noqa: E402
from tlsys.index import NarrowIndex, ReferenceNarrowIndex  # noqa: E402
from tlsys.query import _dense_rank  # noqa: E402
from tlsys.ingest import ingest_docs  # noqa: E402
from tlsys.lifecycle import retire_docs  # noqa: E402
from tlsys.maint import organize_segments  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


QUERIES = ["the domestic cat", "alpha beta", "zxqy", "sport medic"]


def ref_digest(ref):
    df = {}
    total = 0
    for text in ref.atom_text.values():
        ts = text.lower().split()
        total += len(ts)
        for t in set(ts):
            df[t] = df.get(t, 0) + 1
    return canonical_digest(ref.atoms, ref.holons, ref.atom_text,
                            ref.retired_docs, ref.retired_aids,
                            len(ref.atom_text), total, df)


def build_store_4pins():
    emb = UnitNormEmbed(dim=32, seed=91)
    docs1 = [(f"h1-{i}", t) for i, (_d, t) in
             enumerate(make_docs(16, seed=91))]
    tl, tmp, _p = make_store(docs1, emb, prefix="tlsys-lanes-d3-")
    pin1 = tl.pin()
    docs2 = [(f"h2-{i}", t) for i, (_d, t) in
             enumerate(make_docs(12, seed=92))]
    ingest_docs(tl, docs2, emb)
    pin2 = tl.pin()
    retire_docs(tl, ["h1-2", "h2-5"], reason="d3",
                approvals={d: fixture_approval(f"d3-{d}")
                           for d in ("h1-2", "h2-5")})
    pin3 = tl.pin()
    organize_segments(tl)
    pin4 = tl.pin()
    return tl, tmp, emb, (pin1, pin2, pin3, pin4)


def test_d3_incremental_equals_cold():
    tl, tmp, _emb, pins = build_store_4pins()
    _p1, _p2, _p3, pin4 = pins
    sdir = os.path.join(tmp, "serving")
    # Path A: incremental advances + seals + compact + checkpoint.
    pa = ViewPool(tl, pin4[0], pin4[1], serving_dir=sdir,
                  config={"delta_flush_atoms": 4,
                          "max_live_segments": 3, "merge_fan_in": 2})
    va = pa.acquire(pins[0])
    for pin in pins[1:]:
        va = pa.advance(va, pin)
    compact_mod.run_compaction(pa, mode="inprocess")
    pa.checkpoint(va)
    da = va.canonical_digest()
    # Path A2: fresh pool attaches the checkpoint (load path).
    pa2 = ViewPool(tl, pin4[0], pin4[1], serving_dir=sdir)
    va2 = pa2.acquire(pin4)
    da2 = va2.canonical_digest()
    # Path B: cold build, no seals (pure delta).
    pb = ViewPool(tl, pin4[0], pin4[1])
    vb = pb.cold_build(pin4)
    db = vb.canonical_digest()
    # Path C: reference oracle.
    ref = ReferenceNarrowIndex(tl, pin4)
    dc = ref_digest(ref)
    check("d3-incr-cold", da == db, f"{da[:16]} vs {db[:16]}")
    check("d3-attach-cold", da2 == db, f"{da2[:16]} vs {db[:16]}")
    check("d3-cold-ref", db == dc, f"{db[:16]} vs {dc[:16]}")
    # Legs agree across paths too (bitwise).
    for q in QUERIES:
        a, b, c = va.bm25(q), vb.bm25(q), ref.bm25(q)
        check(f"d3-bm25:{q[:10]}",
              set(a) == set(b) == set(c)
              and list(a) == list(b) == list(c)
              and all(a[k] == b[k] == c[k] for k in a))
    qv = np.arange(32, dtype=np.float64)
    ta = va.dense_atoms_topk(qv, 20)
    tb = vb.dense_atoms_topk(qv, 20)
    pop = ref.atoms
    ids = list(pop.keys())
    mat = np.stack([np.asarray(pop[i]["descriptor"], dtype=np.float64)
                    for i in ids])
    norms = np.linalg.norm(mat, axis=1)
    norms[norms == 0.0] = 1.0
    tr = _dense_rank(qv, ids, mat, norms, topk=20)
    check("d3-dense-topk",
          [a for a, _s in ta] == [a for a, _s in tb]
          == [a for a, _s in tr]
          and all(x == y == z for (_a, x), (_b, y), (_c, z)
                  in zip(ta, tb, tr)))
    # Same facade class over the attached view matches as well.
    fac = NarrowIndex(tl, pin4, serving_dir=sdir)
    check("d3-facade-attach",
          fac.serving_view.canonical_digest() == db)
    tl.close()


def test_i1_membership():
    tl, _tmp, _emb, pins = build_store_4pins()
    pin4 = pins[-1]
    ref = ReferenceNarrowIndex(tl, pin4)
    fac = NarrowIndex(tl, pin4)
    view = fac.serving_view
    check("i1-counts", view.live_n == len(ref.atoms) == len(fac.atoms),
          f"{view.live_n} vs {len(ref.atoms)}")
    # Every eligible atom with text is in the lexical postings;
    # every eligible atom is in the dense rows.
    dense_ids = {a for a, _o in
                 [(view.aid_of_ord[o], o)
                  for o in view._live_atom_ordinals()]}
    missing_lex = []
    for aid, text in ref.atom_text.items():
        if text.strip() and aid not in {
                a for t in set(text.lower().split())
                for a, _f in fac.postings[t]}:
            missing_lex.append(aid)
    check("i1-lexical", not missing_lex, f"{missing_lex[:5]}")
    check("i1-dense", dense_ids == set(ref.atoms))
    # Coverage before organization: atoms indexed without organize.
    docs = [(f"u-{i}", t) for i, (_d, t) in
            enumerate(make_docs(6, seed=93))]
    tl2, _t2, pin_u = make_store(docs, emb_votes,
                                 prefix="tlsys-lanes-d3u-")
    ref2 = ReferenceNarrowIndex(tl2, pin_u)
    fac2 = NarrowIndex(tl2, pin_u)
    check("i1-unorganized",
          set(fac2.atoms) == set(ref2.atoms)
          and fac2.serving_view.live_n == len(ref2.atoms))
    tl.close()
    tl2.close()


def main():
    import traceback
    for fn in (test_d3_incremental_equals_cold, test_i1_membership):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 (fault isolation)
            FAILS.append(fn.__name__)
            print(f"FAIL {fn.__name__} :: raised {type(e).__name__}: {e}")
            print(traceback.format_exc(limit=6))
    print("scratch: /tmp/tlsys-lanes-d3-*")
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
