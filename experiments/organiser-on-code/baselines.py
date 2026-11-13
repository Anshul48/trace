# SPDX-License-Identifier: Apache-2.0
"""Told-K baselines and cluster metrics (stdlib only).

k-means (told K, k-means++ starts, 10 restarts, cosine distance) in dense
and sparse flavours, average-link agglomeration cut at K groups, and an
equal-size random partition. Metrics: adjusted Rand index (Hubert-Arabie,
degenerate cases map to 0.0), purity, group count, median group size and
largest-group share. All deterministic given the caller's seed strings.
"""
import random


def c2(n):
    return n * (n - 1) // 2


def ari(true, pred):
    n = len(true)
    if n < 2:
        return 0.0
    cont = {}
    for t, p in zip(true, pred):
        cont[(t, p)] = cont.get((t, p), 0) + 1
    rows, cols = {}, {}
    for (t, p), v in cont.items():
        rows[t] = rows.get(t, 0) + v
        cols[p] = cols.get(p, 0) + v
    tot = c2(n)
    if tot == 0:
        return 0.0
    s = sum(c2(v) for v in cont.values())
    sr = sum(c2(v) for v in rows.values())
    sc = sum(c2(v) for v in cols.values())
    exp = sr * sc / tot
    den = 0.5 * (sr + sc) - exp
    if den == 0:
        return 0.0
    return (s - exp) / den


def cluster_index(labels):
    groups = {}
    for i, lab in enumerate(labels):
        groups.setdefault(lab, []).append(i)
    return groups


def purity_of(groups, truth):
    n = len(truth)
    tot = 0
    for members in groups.values():
        counts = {}
        for i in members:
            counts[truth[i]] = counts.get(truth[i], 0) + 1
        tot += max(counts.values())
    return tot / n


def cluster_stats(labels, truth):
    """K, median size, largest share, purity. Exact floats."""
    n = len(labels)
    assert n == len(truth) and n > 0
    groups = cluster_index(labels)
    sizes = sorted(len(m) for m in groups.values())
    k = len(sizes)
    if k % 2 == 1:
        median = float(sizes[k // 2])
    else:
        median = (sizes[k // 2 - 1] + sizes[k // 2]) / 2.0
    return {"K": k, "median": median, "share": sizes[-1] / n,
            "purity": purity_of(groups, truth), "n": n}


def dot_dense(a, b):
    s = 0.0
    for x, y in zip(a, b):
        s += x * y
    return s


def dot_sparse(a, b):
    if len(a) > len(b):
        a, b = b, a
    s = 0.0
    for k, v in a.items():
        w = b.get(k)
        if w is not None:
            s += v * w
    return s


def _kmeans_plus_plus(vecs, k, rng, dot, copy):
    n = len(vecs)
    rr = random.Random(rng)
    cents = [copy(vecs[rr.randrange(n)])]
    while len(cents) < k:
        d2 = []
        for v in vecs:
            dd = 1.0 - max(dot(v, c) for c in cents)
            d2.append(dd * dd if dd > 0 else 0.0)
        tot = sum(d2)
        if tot <= 0:
            cents.append(copy(vecs[rr.randrange(n)]))
            continue
        x = rr.random() * tot
        acc = 0.0
        pick = n - 1
        for i, dv in enumerate(d2):
            acc += dv
            if acc >= x:
                pick = i
                break
        cents.append(copy(vecs[pick]))
    return cents, rr


def kmeans_dense(vecs, k, rng, restarts=10, iters=100):
    """Lloyd on cosine distance over dense lists; rng is a seed string."""
    n = len(vecs)
    dim = len(vecs[0])
    best = None
    best_inertia = None
    for r in range(restarts):
        cents, _rr = _kmeans_plus_plus(
            vecs, k, rng + "#%d" % r, dot_dense, lambda v: list(v))
        assign = [0] * n
        for _ in range(iters):
            changed = False
            for i, v in enumerate(vecs):
                bi, bd = 0, None
                for c, cent in enumerate(cents):
                    dd = 1.0 - dot_dense(v, cent)
                    if bd is None or dd < bd:
                        bd, bi = dd, c
                if bi != assign[i]:
                    assign[i] = bi
                    changed = True
            sizes = [0] * k
            for a in assign:
                sizes[a] += 1
            for c in range(k):
                if sizes[c] == 0:
                    fi, fd = 0, -1.0
                    for i, v in enumerate(vecs):
                        dd = 1.0 - dot_dense(v, cents[assign[i]])
                        if dd > fd:
                            fd, fi = dd, i
                    assign[fi] = c
                    changed = True
            new = [[0.0] * dim for _ in range(k)]
            for i, v in enumerate(vecs):
                nc = new[assign[i]]
                for j in range(dim):
                    nc[j] += v[j]
            for c in range(k):
                norm = sum(v * v for v in new[c]) ** 0.5
                if norm > 0:
                    for j in range(dim):
                        new[c][j] /= norm
            cents = new
            if not changed:
                break
        inertia = sum(1.0 - dot_dense(vecs[i], cents[assign[i]])
                      for i in range(n))
        if best_inertia is None or inertia < best_inertia:
            best_inertia = inertia
            best = list(assign)
    return best


def kmeans_sparse(vecs, k, rng, restarts=10, iters=100):
    """Lloyd on cosine distance over sparse {index: weight} maps."""
    n = len(vecs)
    best = None
    best_inertia = None
    for r in range(restarts):
        cents, _rr = _kmeans_plus_plus(
            vecs, k, rng + "#%d" % r, dot_sparse, lambda v: dict(v))
        assign = [0] * n
        for _ in range(iters):
            changed = False
            for i, v in enumerate(vecs):
                bi, bd = 0, None
                for c, cent in enumerate(cents):
                    dd = 1.0 - dot_sparse(v, cent)
                    if bd is None or dd < bd:
                        bd, bi = dd, c
                if bi != assign[i]:
                    assign[i] = bi
                    changed = True
            sizes = [0] * k
            for a in assign:
                sizes[a] += 1
            for c in range(k):
                if sizes[c] == 0:
                    fi, fd = 0, -1.0
                    for i, v in enumerate(vecs):
                        dd = 1.0 - dot_sparse(v, cents[assign[i]])
                        if dd > fd:
                            fd, fi = dd, i
                    assign[fi] = c
                    changed = True
            new = [dict() for _ in range(k)]
            for i, v in enumerate(vecs):
                nc = new[assign[i]]
                for j, val in v.items():
                    nc[j] = nc.get(j, 0.0) + val
            for c in range(k):
                norm = sum(v * v for v in new[c].values()) ** 0.5
                if norm > 0:
                    for j in new[c]:
                        new[c][j] /= norm
            cents = new
            if not changed:
                break
        inertia = sum(1.0 - dot_sparse(vecs[i], cents[assign[i]])
                      for i in range(n))
        if best_inertia is None or inertia < best_inertia:
            best_inertia = inertia
            best = list(assign)
    return best


def avg_link(sim, k):
    """Average-link agglomeration on a similarity matrix, cut at k groups.

    Lowest-index scan, strict improvement, absorbed cluster merged into the
    surviving (lower-index) one with size-weighted similarities.
    """
    n = len(sim)
    active = list(range(n))
    size = [1] * n
    members = [[i] for i in range(n)]
    mat = [row[:] for row in sim]
    while len(active) > k:
        bi = bj = -1
        bval = None
        for x in range(len(active)):
            for y in range(x + 1, len(active)):
                i, j = active[x], active[y]
                v = mat[i][j]
                if bval is None or v > bval:
                    bval, bi, bj = v, i, j
                    bxj = y
        si, sj = size[bi], size[bj]
        for m in active:
            if m != bi and m != bj:
                mat[bi][m] = mat[m][bi] = \
                    (mat[bi][m] * si + mat[bj][m] * sj) / (si + sj)
        size[bi] = si + sj
        members[bi] = members[bi] + members[bj]
        active.pop(bxj)
    labels = [0] * n
    for lab, m in enumerate(active):
        for i in members[m]:
            labels[i] = lab
    return labels


def rand_partition(rng, n, k):
    """Equal-size random split of n items into k groups (first groups +1)."""
    order = list(range(n))
    rng.shuffle(order)
    labels = [0] * n
    base, rem = divmod(n, k)
    pos = 0
    for c in range(k):
        size = base + (1 if c < rem else 0)
        for t in range(pos, pos + size):
            labels[order[t]] = c
        pos += size
    return labels


def sim_matrix_dense(vecs):
    n = len(vecs)
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        sim[i][i] = 1.0
        for j in range(i + 1, n):
            v = dot_dense(vecs[i], vecs[j])
            sim[i][j] = sim[j][i] = v
    return sim


def sim_matrix_sparse(vecs):
    n = len(vecs)
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        sim[i][i] = 1.0
        for j in range(i + 1, n):
            v = dot_sparse(vecs[i], vecs[j])
            sim[i][j] = sim[j][i] = v
    return sim
