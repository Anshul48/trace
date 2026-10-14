"""Dense engine: FP32 scan + certified FP64 rescore (E2 protocol).

Reference: tlsys.query._dense_rank (float64 mat@q/(qn*norms), zero->1.0,
stable descending argsort). Full ranking here is bitwise-equal to it given
identical inputs; bounded top-k adds the FP32-shortlist certificate
(k-th exact > best FP32 outside + eps, else widen x2 and repeat).
"""

import numpy as np


def _dense_rank_ref(qvec, ids, mat, norms, topk=None):
    # Same function object the product path calls (lazy import: query.py
    # never imports serving at module level, so no cycle).
    from tlsys.query import _dense_rank
    return _dense_rank(qvec, ids, mat, norms, topk=topk)


def build_fp32(rows):
    """rows: [array-like float64] in ordinal order.
    Returns (mat32 C-contiguous, inv32, norms64, overrides) where overrides
    maps row index -> exact float64 row for committed descriptors that are
    NOT exactly FP32-representable (bitwise check). norms64 uses C1's
    zero->1.0 rule; inv32 = (1/norms).astype(float32)."""
    mat64 = (np.stack([np.asarray(r, dtype=np.float64) for r in rows])
             if rows else np.empty((0, 0)))
    mat32 = np.ascontiguousarray(mat64.astype(np.float32))
    if rows:
        norms = np.linalg.norm(mat64, axis=1)
    else:
        norms = np.empty((0,))
    norms[norms == 0.0] = 1.0
    inv32 = (1.0 / norms).astype(np.float32)
    overrides = {}
    if rows:
        back = mat32.astype(np.float64)
        diff = np.any(back != mat64, axis=1)
        for i in np.nonzero(diff)[0].tolist():
            overrides[int(i)] = mat64[i].copy()
    return mat32, inv32, norms, overrides


def f64_row(i, mat32, overrides):
    ov = overrides.get(int(i))
    if ov is not None:
        return np.asarray(ov, dtype=np.float64)
    return mat32[int(i)].astype(np.float64)


def stable_head(scores, ids, k):
    """Exact head of the stable descending order, without a full sort.

    Returns [(id, score)] for the first k of np.argsort(-scores,
    kind="stable") — identical ids, scores, and tie order — using a
    selection + tie-expansion + head-only stable sort. Non-finite
    scores take the full-sort reference path (identical by
    construction). Pure; differential-pinned on ties/zeros/dups.
    """
    import numpy as _np
    s = _np.asarray(scores, dtype=_np.float64).ravel()
    ids = list(ids)
    n = int(s.shape[0])
    k = int(k)
    if k <= 0 or n == 0:
        return []
    if k >= n or not bool(_np.all(_np.isfinite(s))):
        order = _np.argsort(-s, kind="stable")[:k]
        return [(ids[int(i)], float(s[int(i)])) for i in order.tolist()]
    kth = float(-_np.partition(-s, k - 1)[k - 1])
    above = _np.nonzero(s > kth)[0]
    tied = _np.nonzero(s == kth)[0]
    cand = _np.union1d(above, tied)
    order = _np.lexsort((cand, -s[cand]))
    head = cand[order[:k]]
    return [(ids[int(i)], float(s[int(i)])) for i in head.tolist()]


def exact_full_rank(qvec, ids, mat32, norms64, overrides):
    """Bitwise-equal to _dense_rank(qvec, ids, mat64, norms64): identical
    inputs (FP32->FP64 exact + overrides + recomputed norms) through the
    identical function."""
    n = len(ids)
    if n == 0:
        return []
    mat64 = mat32.astype(np.float64)
    for i, row in overrides.items():
        mat64[int(i)] = row
    return _dense_rank_ref(qvec, list(ids), mat64,
                           np.asarray(norms64, dtype=np.float64))


def certified_topk(qvec, k, ids, mat32, norms64, overrides, m=64, eps=3e-5,
                   counters=None):
    """E2 protocol over ONE ordinal-ordered row set. ids/rows ascend by
    global ordinal. Returns ([(id, score)] top-k, cert dict). Order is
    (-score, ordinal); ties broken by ordinal exactly as C1's stable sort
    over the same order. Terminates: shortlist doubles to n-1 worst case."""
    n = len(ids)
    if n == 0 or k <= 0:
        return [], {"widened": 0, "margin": float("inf"), "exact": True,
                    "rows": 0}
    k = min(int(k), n)
    q = np.asarray(qvec, dtype=np.float64)
    qn = float(np.linalg.norm(q)) or 1.0
    q32 = (q / qn).astype(np.float32)
    inv32 = np.asarray(inv32_of(mat32, norms64), dtype=np.float32)
    s32_all = (mat32 @ q32) * inv32
    if counters is not None:
        counters.record(dense_fp32_rows=n)
    # Override rows (committed descriptors not exactly FP32) always join
    # the shortlist: the eps bound covers FP32 rounding of exactly held
    # rows only, so non-exact rows are never certified from the outside.
    must = np.array(sorted(set(int(i) for i in overrides if 0 <= i < n)),
                    dtype=np.int64)
    if n == 1:
        s = _rescore_rows(np.array([0]), mat32, overrides, q, qn)[0]
        if counters is not None:
            counters.record(dense_rescore_rows=1)
        return [(ids[0], float(s))], {"widened": 0,
                                      "margin": float("inf"),
                                      "exact": True, "rows": 1}
    mm = min(n - 1, k + m)
    widened = 0
    while True:
        if mm >= n - 1:
            sl = np.arange(n)
        else:
            sl = np.union1d(np.argpartition(-s32_all, mm)[:mm], must)
            if len(sl) >= n:
                sl = np.arange(n)
        s_resc = _rescore_rows(sl, mat32, overrides, q, qn)
        if counters is not None:
            counters.record(dense_rescore_rows=len(sl))
        # sl positions are unique; order (-score, position) == C1's
        # stable order over the same rows since positions ascend with
        # ordinals.
        order = np.lexsort((sl, -s_resc))
        top_pos = order[:k]
        top_ids = [ids[int(sl[p])] for p in top_pos]
        top_scores = [float(s_resc[p]) for p in top_pos]
        if len(sl) >= n:
            if counters is not None:
                counters.record(widenings=widened)
            return (list(zip(top_ids, top_scores)),
                    {"widened": widened, "margin": float("inf"),
                     "exact": True, "rows": int(len(sl)),
                     "shortlist": int(len(sl)), "full": True})
        in_sl = np.zeros(n, dtype=bool)
        in_sl[sl] = True
        out_best32 = float(s32_all[~in_sl].max())
        margin = float(top_scores[-1] - out_best32)
        if top_scores[-1] > out_best32 + eps:
            if counters is not None:
                counters.record(widenings=widened)
            return (list(zip(top_ids, top_scores)),
                    {"widened": widened, "margin": margin, "exact": True,
                     "rows": int(len(sl)), "shortlist": int(len(sl))})
        mm = min(n - 1, max(mm * 2, len(sl) * 2))
        widened += 1


def _rescore_rows(sl, mat32, overrides, q, qn):
    """Exact FP64 rescoring with C1's expression, vectorized (one BLAS
    matvec over the shortlist rows: per-row dots are bitwise identical to
    the full-matrix matvec in _dense_rank, verified by the E2-seed test)."""
    rows64 = np.asarray(mat32)[np.asarray(sl)].astype(np.float64)
    sl_list = np.asarray(sl).tolist()
    for j, i in enumerate(sl_list):
        ov = overrides.get(int(i))
        if ov is not None:
            rows64[j] = ov
    nrm = np.linalg.norm(rows64, axis=1)
    nrm[nrm == 0.0] = 1.0
    return (rows64 @ q) / (qn * nrm)


def inv32_of(mat32, norms64):
    # Inverse norms matching build_fp32 (recomputed form for callers that
    # hold only mat32+norms64).
    return (1.0 / np.asarray(norms64, dtype=np.float64)).astype(np.float32)
