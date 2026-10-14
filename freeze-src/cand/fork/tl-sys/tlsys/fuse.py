"""Pure fusion/selection/admission (no numpy, no store): RRF-60 (Q2.2),
exact-only static prune (Q10.2a + amended Q12.1b), exact MMR (Q10.2a),
variable-K admission with conflict-specific joint preservation
(Q12.3 final). Pure so the maintained tests run anywhere."""

import hashlib
import math

RRF_K = 60


def rrf_fuse(rank_lists, k=RRF_K):
    """Rank-only RRF (Q2.2). rank_lists: [{target: rank}]. Targets of
    mixed type fuse mechanically -- ranks only, never compared."""
    w = {}
    for rl in rank_lists:
        for target, rank in rl.items():
            w[target] = w.get(target, 0.0) + 1.0 / (k + rank)
    return w


def static_prune(cands, cap):
    """Score-ordered greedy, EXACT-duplicate collapse only (amended
    Q12.1(b)). cands: [(aid, score, text)]. Score order out."""
    cands = sorted(cands, key=lambda c: -c[1])
    seen = set()
    out = []
    for aid, score, text in cands:
        h = hashlib.sha256(text.encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append((aid, score, text))
        if len(out) >= cap:
            break
    return out


def _cos(va, vb):
    n = 0.0
    na = nb = 0.0
    for x, y in zip(va, vb):
        n += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return n / math.sqrt(na * nb)


def mmr_order(cands, vecs, lam, k):
    """Exact vector MMR on the bounded set (Q10.2a), once per query.
    cands: [(aid, score)]; vecs: {aid: seq(float)}. Ordered aids.
    Reference implementation (pure python). Product path uses
    mmr_order_matrix with a precomputed similarity closure."""
    return mmr_order_matrix(
        cands, lambda a, b: _cos(vecs[a], vecs[b])
        if (a in vecs and b in vecs) else 0.0, lam, k)


def mmr_order_matrix(cands, sim, lam, k, sim_cap=None):
    """Exact MMR with caller-supplied sim(aid, aid) closure (e.g. over
    a numpy cosine matrix). Selection logic identical to mmr_order.
    sim_cap ([E] R3-1): when not None, the diversity term is capped:
    div' = min(div, sim_cap), so topically-similar candidates (e.g.
    contradictory para pairs) are not mutually excluded. Default
    None preserves exact-MMR behavior."""
    if not cands:
        return []
    rel = {c[0]: c[1] for c in cands}
    mx = max(rel.values()) or 1.0
    # Deterministic scan order (cands order: score desc, then
    # insertion): NEVER iterate a set here -- hash randomization
    # made tie-breaks differ per process (found 2026-09-29: 13% of
    # campaign rows differed across runs). `rest` stays a set for
    # O(1) membership only.
    scan = [c[0] for c in cands]
    sel, rest = [], set(rel)
    while rest and len(sel) < k:
        best, best_v = None, -1e18
        for aid in scan:
            if aid not in rest:
                continue
            div = 0.0
            if aid in rel and sel:
                for s in sel:
                    div = max(div, sim(aid, s))
            if sim_cap is not None:
                div = min(div, sim_cap)
            v = lam * (rel[aid] / mx) - (1 - lam) * div
            if v > best_v:
                best, best_v = aid, v
        sel.append(best)
        rest.discard(best)
    return sel


def admit(order_scores, pairs, tau, cap):
    """Variable-K admission (Q12.3 final). order_scores: [(aid, score)]
    in MMR order. pairs: [(a, b)] identified qualifier-explicit
    counterparts (matching scope). Returns (admitted [aid],
    deferred [(aid, reason)]). Rules: ordinary candidates clear
    score tau; zero-valid, no backfill; required counterparts ride
    below tau with status unmodified; any binding cap that would
    break an identified pair defers BOTH (never one-sided) with
    explicit overflow; unaffected material may still fill."""
    partner = {}
    for a, b in pairs:
        partner[a] = b
        partner[b] = a
    admitted, deferred = [], []
    seats = {}

    def seat(aid, score, why):
        admitted.append(aid)
        seats[aid] = (score, why)

    for aid, score in order_scores:
        if aid in seats or any(aid == d[0] for d in deferred):
            continue
        bud = partner.get(aid)
        if bud is None:
            if score >= tau and len(admitted) < cap:
                seat(aid, score, "cleared-tau")
            elif score < tau:
                deferred.append((aid, "below-tau"))
            else:
                deferred.append((aid, "cap-reached"))
            continue
        # joint preservation: seat both or defer both
        bscore = next((s for i, s in order_scores if i == bud), None)
        if bscore is None:
            deferred.append((aid, "counterpart-unidentified"))
            continue
        if len(admitted) + 2 <= cap:
            if score >= bscore:
                first, fscore, other, oscore = aid, score, bud, bscore
            else:
                first, fscore, other, oscore = bud, bscore, aid, score
            admitted.extend([first, other])
            seats[first] = (fscore, "pair-primary")
            seats[other] = (oscore, "counterpart-rides")
        else:
            deferred.append((aid, "pair-overflow-cap"))
            if not any(bud == d[0] for d in deferred):
                deferred.append((bud, "pair-overflow-cap"))
    return admitted, deferred
