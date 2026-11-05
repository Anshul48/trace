#!/usr/bin/env python3
"""bench-deep-v0 Step 2: routing vs exact + abstention on the repo 20k set.
Stdlib only. Deterministic. See PREREG.md. Writes results JSON to stdout."""
import json, math, os, random, resource, struct, sys, time

# Repo root resolved from this script's own location (docs/benchmarks-deep/results/).
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA20K = os.path.join(ROOT, "docs", "reproduction", "repro-20k", "data-20k")
CACHE = os.path.join(DATA20K, "emb_cache")
TREE = os.path.join(ROOT, "docs", "explorer", "local_20k_data.json")

def load_vectors():
    t0 = time.perf_counter()
    idx = {}
    with open(os.path.join(CACHE, "index.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            idx[r["chunk_sha256"]] = r["row"]
    with open(os.path.join(CACHE, "shard_000000.f32"), "rb") as f:
        raw = f.read()
    dim = 384
    n = len(raw) // (dim * 4)
    assert n == 144, n
    vecs = []
    for i in range(n):
        v = struct.unpack("<%df" % dim, raw[i*dim*4:(i+1)*dim*4])
        norm = math.sqrt(sum(x*x for x in v))
        vecs.append([x/norm for x in v])
    return idx, vecs, time.perf_counter() - t0

def load_tree(idx):
    import hashlib
    t0 = time.perf_counter()
    with open(TREE) as f:
        d = json.load(f)
    docs = {}
    with open(os.path.join(DATA20K, "docs-100m.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            docs[r["doc_id"]] = r["text"].encode("utf-8")
    atoms = d["atoms"]
    assert len(atoms) == 144
    aid_row = {}
    for a in atoms:
        s, e = a["byte_span"]
        h = hashlib.sha256(docs[a["doc_id"]][s:e]).hexdigest()
        assert h in idx, (a["id"][:12], a["doc_id"], a["byte_span"])
        aid_row[a["id"]] = idx[h]
    assert len(set(aid_row.values())) == 144, "join must cover all 144 rows"
    leaves = {L["id"]: [aid_row[x] for x in L["atom_ids"]] for L in d["leaves"]}
    leaf_of = {}
    for L in d["leaves"]:
        for x in L["atom_ids"]:
            leaf_of.setdefault(aid_row[x], []).append(L["id"])
    pmap = {}
    for L in d["leaves"]:
        for p in L["parent_ids"]:
            pmap.setdefault(p, []).append(L["id"])
    parents = {p: sorted({r for L in ls for r in leaves[L]}) for p, ls in pmap.items()}
    return atoms, aid_row, leaves, parents, time.perf_counter() - t0

def centroid(vecs, rows):
    dim = len(vecs[0])
    c = [0.0]*dim
    for r in rows:
        v = vecs[r]
        for j in range(dim):
            c[j] += v[j]
    n = math.sqrt(sum(x*x for x in c)) or 1.0
    return [x/n for x in c]

def dot(a, b):
    return sum(x*y for x, y in zip(a, b))

def topk(scores, k):
    # scores: list of (score, key); prereg tie rule: atom id ascending
    scores.sort(key=lambda t: (-t[0], t[1]))
    return scores[:k]

def dcg(gains):
    return sum(g / math.log2(i+2) for i, g in enumerate(gains))

def main():
    timings = {}
    idx, vecs, timings["load_vectors_s"] = load_vectors()
    N = len(vecs)
    atoms, aid_row, leaves, parents, timings["load_tree_s"] = load_tree(idx)
    t0 = time.perf_counter()
    leaf_ids = sorted(leaves)
    par_ids = sorted(parents)
    leaf_c = {L: centroid(vecs, leaves[L]) for L in leaf_ids}
    par_c = {p: centroid(vecs, parents[p]) for p in par_ids}
    timings["build_centroids_s"] = time.perf_counter() - t0
    rownum_of = [None]*N
    for a in atoms:
        rownum_of[aid_row[a["id"]]] = a["id"]
    assert all(x is not None for x in rownum_of)

    # (a) EXACT top-100 for all 144 atom-queries
    exact = {}
    tq = []
    for q in range(N):
        s = time.perf_counter()
        sc = [(dot(vecs[q], vecs[r]), rownum_of[r], r) for r in range(N)]
        sc.sort(key=lambda t: (-t[0], t[1]))
        exact[q] = sc[:100]
        tq.append(time.perf_counter() - s)
    timings["exact_per_query_s"] = {"mean": sum(tq)/N, "max": max(tq)}

    def route(q, cents, members, order, budget):
        rs = topk([(dot(vecs[q], cents[g]), g) for g in order], budget)
        opened = [g for _, g in rs]
        seen = []
        dup = set()
        for g in opened:  # parents overlap: dedupe rows, count each once
            for r in members[g]:
                if r not in dup:
                    dup.add(r)
                    seen.append(r)
        asc = [(dot(vecs[q], vecs[r]), rownum_of[r], r) for r in seen]
        asc.sort(key=lambda t: (-t[0], t[1]))
        return asc[:100], len(order) + len(seen), len(seen), opened

    out_route = {}
    for name, cents, members, order, budgets in (
            ("leaf", leaf_c, leaves, leaf_ids, [1,2,4,8,16,81]),
            ("parent", par_c, parents, par_ids, [1,2,4,8,51])):
        for B in budgets:
            rec10 = rec100 = sndcg = fndcg = 0.0
            scored = routed = 0
            tqq = []
            perq = []
            for q in range(N):
                s = time.perf_counter()
                got, nrout, nsc, opened = route(q, cents, members, order, B)
                tqq.append(time.perf_counter() - s)
                gt = exact[q]
                gt10 = {r for _, _, r in gt[:10]}
                got10 = [r for _, _, r in got[:10]]
                rec10 += len(set(got10) & gt10)/10
                got100 = {r for _, _, r in got}
                rec100 += len(got100 & {r for _, _, r in gt})/100
                selfrow = q
                gains = [1.0 if r == selfrow else 0.0 for r in got10]
                sndcg += dcg(gains)  # IDCG = 1.0
                gmap = {r: 11.0-i for i, (_, _, r) in enumerate(gt[:10])}
                fg = [gmap.get(r, 0.0) for r in got10]
                ideal = sorted(gmap.values(), reverse=True)
                fndcg += dcg(fg)/dcg(ideal)
                scored += nsc; routed += nrout
                perq.append({"q": q, "scored": nsc, "routed": nrout,
                             "rec10": len(set(got10) & gt10)/10,
                             "opened": opened if B <= 8 else None})
            out_route["%s_L%d" % (name, B)] = {
                "recall10": rec10/N, "recall100": rec100/N,
                "self_ndcg10": sndcg/N, "fidelity_ndcg10": fndcg/N,
                "mean_scored": scored/N, "mean_scored_frac": scored/N/N,
                "mean_routed": routed/N,
                "per_query_wall_mean_s": sum(tqq)/N, "per_query": perq}

    # (b) ABSTENTION
    rng = random.Random(7)
    noise = []
    for _ in range(48):
        v = [rng.gauss(0, 1) for _ in range(len(vecs[0]))]
        n = math.sqrt(sum(x*x for x in v))
        noise.append([x/n for x in v])
    # answerable: self present; unanswerable-heldout: self removed; noise
    sig = []  # (kind, qid, top1, margin, correct_top1)
    for q in range(N):
        sc = exact[q]
        top1, _, r1 = sc[0]
        top2 = sc[1][0]
        sig.append(("answerable", q, top1, top1-top2, r1 == q))
    for q in range(N):
        sc = [(dot(vecs[q], vecs[r]), rownum_of[r], r) for r in range(N) if r != q]
        sc.sort(key=lambda t: (-t[0], t[1]))
        sig.append(("heldout", q, sc[0][0], sc[0][0]-sc[1][0], False))
    for i, v in enumerate(noise):
        sc = [(dot(v, vecs[r]), rownum_of[r], r) for r in range(N)]
        sc.sort(key=lambda t: (-t[0], t[1]))
        sig.append(("noise", i, sc[0][0], sc[0][0]-sc[1][0], False))

    def stats(pred):
        tot = len(pred)
        ans = [p for p in pred if p[0]]
        cov = len(ans)/tot
        prec = (sum(1 for _, c in ans if c)/len(ans)) if ans else None
        far = sum(1 for a, c in pred if a and not c)/tot
        return {"coverage": cov, "precision_on_answered": prec,
                "false_answer_rate": far, "n_answered": len(ans), "n": tot}

    prereg = {}
    for sigidx, name, thr in ((2, "top1", 0.85), (2, "top1", 0.95),
                              (2, "top1", 0.99), (3, "margin", 0.02),
                              (3, "margin", 0.10), (3, "margin", 0.25)):
        prereg["%s_%s" % (name, thr)] = stats(
            [(s[sigidx] >= thr, s[4]) for s in sig])
    # full risk-coverage curves (pooled + split)
    curves = {}
    for signame, si in (("top1", 2), ("margin", 3)):
        vals = sorted({s[si] for s in sig}, reverse=True)
        rows = []
        for t in vals:
            pooled = stats([(s[si] >= t, s[4]) for s in sig])
            held = stats([(s[si] >= t, s[4]) for s in sig if s[0] != "noise"])
            rows.append({"thr": t, "pooled": pooled, "heldout_split": held})
        # decimate curve rows to <= 120 for size (keep endpoints + extremes)
        if len(rows) > 120:
            keep = [0] + [round(i*(len(rows)-1)/119) for i in range(1, 119)] + [len(rows)-1]
            rows = [rows[i] for i in sorted(set(keep))]
        curves[signame] = rows

    res = {
        "scope": "20k prefix, 144 atoms, 88 docs, passages-as-queries",
        "n_atoms": N, "n_leaves": len(leaf_ids), "n_parents": len(par_ids),
        "leaf_sizes": sorted(len(v) for v in leaves.values()),
        "timings_s": timings,
        "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        "routing": out_route,
        "abstention_prereg": prereg,
        "abstention_curves": curves,
        "abstention_signals": [
            {"kind": k, "qid": q, "top1": a, "margin": m, "correct": c}
            for k, q, a, m, c in sig],
    }
    json.dump(res, sys.stdout, indent=1)

if __name__ == "__main__":
    main()
