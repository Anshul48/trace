"""Lane S parity seeds: B2 lexical (224 queries, bitwise) + E2 dense
(160 queries, certified top-k vs _dense_rank) on one 3000-doc store
(384-d unit-norm vectors, exact-duplicate texts every 300th doc).

Run: tl-sys/.venv/bin/python tl-sys/tlsys/serving/tests/test_serving_parity_seeds.py
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from fixture import UnitNormEmbed, make_docs, make_store  # noqa: E402
from tlsys.index import NarrowIndex, ReferenceNarrowIndex  # noqa: E402
from tlsys.query import NarrowQuery, _dense_rank  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
        print(f"FAIL {name} :: {detail}")
    else:
        print(f"pass {name}")


N_DOCS = 3000
N_B2 = 224
N_E2 = 160
TOPK = 200


def emb1_factory(emb):
    def emb1(q):
        return emb([q])[0]
    return emb1


def build_seed_store():
    docs = make_docs(N_DOCS, seed=71, dup_every=300)
    docs = [(f"p-{i}", t) for i, (_d, t) in enumerate(docs)]
    emb = UnitNormEmbed(dim=384, seed=20261006)
    # place_xdoc=False: the lexical/dense legs don't need xdoc
    # placement, and the flat O(D^2) python path dominates build
    # time at 3000 docs (525s -> ~60s).
    tl, tmp, pin = make_store(docs, emb, prefix="tlsys-lanes-seeds-",
                              place_xdoc=False)
    return tl, tmp, pin, emb, docs


def b2_queries(docs, seed=810):
    rng = random.Random(seed)
    vocab = sorted({w for _d, t in docs for w in t.lower().split()})
    stops = [w for w in ("the", "a", "an", "of", "and", "in", "on",
                         "to", "is", "for", "with") if w in vocab]
    out = []
    for _ in range(N_B2):
        terms = [rng.choice(vocab) for _ in range(6)]
        terms += [rng.choice(stops) for _ in range(2)] if stops else []
        rng.shuffle(terms)
        out.append(" ".join(terms))
    return out


def test_b2_lexical(ref, fac, docs):
    view = fac.serving_view
    key_mis = order_mis = score_mis = 0
    fullscan_key_mis = 0
    t0 = time.time()
    for q in b2_queries(docs):
        r = ref.bm25(q)
        f = fac.bm25(q)
        v = view.bm25(q)
        if set(r) != set(f) or set(r) != set(v):
            key_mis += 1
            continue
        if list(r) != list(f) or list(r) != list(v):
            order_mis += 1
            continue
        bad = [a for a in r if r[a] != f[a] or r[a] != v[a]]
        if bad:
            score_mis += 1
        if set(ref.bm25_fullscan(q)) != set(r):
            fullscan_key_mis += 1
    dt = time.time() - t0
    print(f"b2: {N_B2} queries in {dt:.1f}s "
          f"({1000 * dt / N_B2:.1f} ms/query, 3 legs each)")
    check("b2-key-set-0", key_mis == 0, f"{key_mis}")
    check("b2-key-order-0", order_mis == 0, f"{order_mis}")
    check("b2-bitwise-0", score_mis == 0, f"{score_mis}")
    check("b2-fullscan-keys", fullscan_key_mis == 0, f"{fullscan_key_mis}")


def e2_queries(ref, emb, seed=811):
    rng = random.Random(seed)
    aids = list(ref.atoms)
    dup_aid = None
    seen_text = {}
    for aid in aids:
        t = ref.atom_text[aid]
        if t in seen_text:
            dup_aid = aid
            break
        seen_text[t] = aid
    assert dup_aid is not None, "no duplicate texts in seed store"
    dup_vec = np.asarray(ref.atoms[dup_aid]["descriptor"],
                         dtype=np.float64)
    mixed = []
    for _ in range(100):
        v = np.array([rng.gauss(0.0, 1.0) for _ in range(384)])
        mixed.append((v / (float(np.linalg.norm(v)) or 1.0)).tolist())
    selfs = [np.asarray(ref.atoms[rng.choice(aids)]["descriptor"],
                        dtype=np.float64).tolist() for _ in range(50)]
    dups = [dup_vec.tolist() for _ in range(10)]
    return mixed, selfs, dups


def tie_explained(ref_rank, got_ids, tol=1e-12):
    """True iff every order difference sits within <=tol score ties."""
    ref_ids = [a for a, _s in ref_rank]
    if ref_ids == got_ids:
        return True
    pos = {a: i for i, a in enumerate(ref_ids)}
    scores = dict(ref_rank)
    # Any inversion must span only exact/near ties.
    for i in range(len(got_ids)):
        for j in range(i + 1, len(got_ids)):
            a, b = got_ids[i], got_ids[j]
            if pos[a] > pos[b] and abs(scores[a] - scores[b]) > tol:
                return False
    return True


SCORE_TOL = 1e-12


def oracle_inputs(ref):
    # Same code as NarrowQuery._dense_pop.
    pop = ref.atoms
    ids = list(pop.keys())
    mat = (np.stack([np.asarray(pop[i]["descriptor"], dtype=np.float64)
                     for i in ids])
           if ids else np.empty((0, 0)))
    norms = np.linalg.norm(mat, axis=1) if ids else np.empty((0,))
    norms[norms == 0.0] = 1.0
    return ids, mat, norms


def test_e2_dense(ref, fac, emb):
    # Spec section 3.4 parity rule (measured form): identical ids and
    # order in the consumed head (any difference restricted to
    # exact/near ties <= 1e-12 and reported) + scores equal to C1's
    # expression. Score equality is max|diff| <= 1e-12, NOT bitwise:
    # OpenBLAS gemv summation order depends on shape/thread count
    # (verified: subset-gemv vs full-gemv differ last-ulp
    # multi-threaded, agree bitwise single-threaded), so bitwise is
    # not well-defined across configs; 1e-12 sits ~4 orders above
    # the observed BLAS noise (~1e-16) and ~4 below any formula bug
    # (see REPORT). Bitwise exactness of the mechanism itself is
    # proven single-threaded in test_e2_singlethread_bitwise.
    view = fac.serving_view
    ids, mat, norms = oracle_inputs(ref)
    mixed, selfs, dups = e2_queries(ref, emb)
    total_ord_mis = total_unexp = total_score_over = 0
    maxd = 0.0
    widenings = 0
    min_margin = float("inf")
    t0 = time.time()
    for group, qs in (("mixed", mixed), ("self", selfs),
                      ("dup", dups)):
        g_ord = g_unexp = g_score = 0
        for qv in qs:
            want = _dense_rank(qv, ids, mat, norms, topk=TOPK)
            got = view.dense_atoms_topk(qv, TOPK)
            cert = view._last_cert
            widenings = max(widenings, cert["widened"])
            if cert["margin"] < min_margin:
                min_margin = cert["margin"]
            want_ids = [a for a, _s in want]
            got_ids = [a for a, _s in got]
            d = max(abs(ws - gs)
                    for (_a, ws), (_b, gs) in zip(want, got))
            maxd = max(maxd, d)
            if d > SCORE_TOL:
                g_score += 1
            if want_ids != got_ids:
                g_ord += 1
                if not tie_explained(want, got_ids):
                    g_unexp += 1
        total_ord_mis += g_ord
        total_unexp += g_unexp
        total_score_over += g_score
        print(f"e2/{group}: queries={len(qs)} order_mis={g_ord} "
              f"unexplained={g_unexp} score_over_tol={g_score}")
        check(f"e2-{group}-order-0", g_ord == 0, f"{g_ord}")
    dt = time.time() - t0
    print(f"e2: {N_E2} queries in {dt:.1f}s; max widenings={widenings}; "
          f"min margin={min_margin:.2e}; max|score diff|={maxd:.2e}")
    check("e2-order-0", total_ord_mis == 0, f"{total_ord_mis}")
    check("e2-unexplained-0", total_unexp == 0, f"{total_unexp}")
    check("e2-scores-tol", total_score_over == 0,
          f"{total_score_over} over {SCORE_TOL}")
    # The shortlist path must actually engage (finite certificate
    # margin on at least one query); all-full would silently skip
    # the FP32 scan under test (regression guard).
    check("e2-shortlist-engaged", min_margin != float("inf"),
          f"min margin={min_margin}")
    # Same-shape full assembly is bitwise (deterministic in-process).
    qv = np.arange(384, dtype=np.float64)
    full = view.dense_atoms_full(qv)
    want = _dense_rank(qv, ids, mat, norms)
    check("e2-full-bitwise",
          [a for a, _s in full] == [a for a, _s in want]
          and all(ws == gs for (_a, ws), (_b, gs)
                  in zip(full, want)))


def test_e2_singlethread_bitwise(ref, fac, emb):
    # Mechanism exactness: under deterministic (single-threaded)
    # BLAS, certified shortlist top-k is bitwise-equal to the full
    # _dense_rank (E2-faithful; 5-query subset for speed).
    import threadpoolctl
    view = fac.serving_view
    ids, mat, norms = oracle_inputs(ref)
    mixed, selfs, dups = e2_queries(ref, emb)
    qs = mixed[:2] + selfs[:2] + dups[:1]
    with threadpoolctl.threadpool_limits(limits=1):
        bad = 0
        for qv in qs:
            want = _dense_rank(qv, ids, mat, norms, topk=TOPK)
            got = view.dense_atoms_topk(qv, TOPK)
            if [a for a, _s in want] != [a for a, _s in got] or any(
                    ws != gs for (_a, ws), (_b, gs)
                    in zip(want, got)):
                bad += 1
    check("e2-singlethread-bitwise", bad == 0, f"{bad}/5")


def test_e2_edges(ref, fac):
    view = fac.serving_view
    pop = ref.atoms
    ids = list(pop.keys())
    mat = np.stack([np.asarray(pop[i]["descriptor"], dtype=np.float64)
                    for i in ids])
    norms = np.linalg.norm(mat, axis=1)
    norms[norms == 0.0] = 1.0
    # Zero query vector.
    q0 = [0.0] * 384
    want = _dense_rank(q0, ids, mat, norms, topk=TOPK)
    got = view.dense_atoms_topk(q0, TOPK)
    check("e2-zero-query",
          [a for a, _s in want] == [a for a, _s in got]
          and max(abs(ws - gs) for (_a, ws), (_b, gs)
                  in zip(want, got)) <= SCORE_TOL)
    # Zero-norm atom present in both legs.
    fac.atoms["zeroATOM"] = {"seq": 10**9, "op_id": "z",
                             "doc_id": "zeroDOC", "span": [0, 1],
                             "text_art": "t", "text_digest": "g",
                             "descriptor": np.zeros(384)}
    fac.atom_text["zeroATOM"] = "lonelyzeroterm"
    pop2 = dict(pop)
    pop2["zeroATOM"] = fac.atoms["zeroATOM"]
    ids2 = list(pop2.keys())
    mat2 = np.stack([np.asarray(pop2[i]["descriptor"], dtype=np.float64)
                     for i in ids2])
    norms2 = np.linalg.norm(mat2, axis=1)
    norms2[norms2 == 0.0] = 1.0
    qv = mat2[0].tolist()
    want = _dense_rank(qv, ids2, mat2, norms2, topk=TOPK)
    got = view.dense_atoms_topk(qv, TOPK)
    want_ids = [a for a, _s in want]
    got_ids = [a for a, _s in got]
    maxd = max(abs(ws - gs) for (_a, ws), (_b, gs) in zip(want, got))
    detail = ""
    if want_ids != got_ids or maxd > SCORE_TOL:
        detail = (f"max|d|={maxd:.2e}; "
                  f"tie_explained={tie_explained(want, got_ids)}; "
                  f"cert={view._last_cert}")
    check("e2-zero-atom", not detail, detail)
    del fac.atoms["zeroATOM"]
    del fac.atom_text["zeroATOM"]


def main():
    import traceback
    t0 = time.time()
    tl, _tmp, pin, emb, docs = build_seed_store()
    ref = ReferenceNarrowIndex(tl, pin)
    fac = NarrowIndex(tl, pin)
    print(f"seed store: {len(ref.atoms)} atoms, "
          f"{len(ref.holons)} holons in {time.time() - t0:.0f}s")
    try:
        for fn in (lambda: test_b2_lexical(ref, fac, docs),
                   lambda: test_e2_dense(ref, fac, emb),
                   lambda: test_e2_singlethread_bitwise(ref, fac,
                                                        emb),
                   lambda: test_e2_edges(ref, fac)):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                FAILS.append(fn.__name__)
                print(f"FAIL {fn.__name__} :: {type(e).__name__}: {e}")
                print(traceback.format_exc(limit=6))
    finally:
        tl.close()
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)}: {FAILS})")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
