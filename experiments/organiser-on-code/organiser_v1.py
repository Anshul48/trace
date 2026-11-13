# SPDX-License-Identifier: Apache-2.0
"""Streaming organiser v1: average-link over unit directions, data-chosen threshold.

Public copy of the organiser kernel: three streaming levels, a
percentile-of-pairwise-distances threshold, closest-pair merges,
and second-parent links. Interface: insert/predict/level_up/
reorganize/to_pred/cluster_counts/to_state/from_state.
"""
import math
RES_MAX, EVERY, QPCT = 300, 50, 20.0
class Dist:  # fallback counter; callers may pass the frozen Dist instead
    def __init__(self): self.n = 0
    def bump(self, k): self.n += k
def _unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]
def _dot(a, b): return sum(x * y for x, y in zip(a, b))
def _pct(sv):  # nearest-rank 20th percentile of sorted values
    r = min(max(int(math.ceil(QPCT / 100.0 * len(sv))), 1), len(sv))
    return sv[r - 1]
class Level:  # one streaming avg-link level; res = first RES_MAX unit inputs
    def __init__(self, dist):
        self.dist = dist
        self.sums = []; self.counts = []; self.members = []
        self.res = []; self.t = float("inf"); self.arrivals = 0; self.fx = False
    def _di(self, x, i):  # item-to-cluster = mean sq-dist to members
        self.dist.bump(1)
        return 2.0 - 2.0 * _dot(x, self.sums[i]) / self.counts[i]
    def _dp(self, i, j):  # cluster-to-cluster avg-link distance
        self.dist.bump(1)
        return 2.0 - 2.0 * _dot(self.sums[i], self.sums[j]) / (
            self.counts[i] * self.counts[j])
    def _ret(self):  # t from reservoir pairwise distances
        m = len(self.res)
        if m < 2: return
        ds = []
        for i in range(m):
            for j in range(i + 1, m):
                self.dist.bump(1); ds.append(2.0 - 2.0 * _dot(self.res[i], self.res[j]))
        ds.sort()
        self.t = _pct(ds)
    def nearest(self, x):
        return sorted((self._di(x, i), i) for i in range(len(self.sums)))
    def assign(self, x, update=True):
        ds = self.nearest(x)
        if not ds or ds[0][0] > self.t:
            self.sums.append(list(x)); self.counts.append(1); self.members.append(set())
            return [len(self.sums) - 1]
        if update:
            s = self.sums[ds[0][1]]
            for k in range(len(x)): s[k] += x[k]
            self.counts[ds[0][1]] += 1
        return [ds[0][1]]
    def observe(self, x):  # START: seed until t exists, then join
        if len(self.res) < RES_MAX and not self.fx: self.res.append(list(x))
        self.arrivals += 1
        if self.arrivals <= EVERY and not math.isfinite(self.t):
            self.sums.append(list(x)); self.counts.append(1); self.members.append(set())
            idx = len(self.sums) - 1
            if self.arrivals < EVERY: return idx, None
            self._ret()
        else:
            if self.arrivals % EVERY == 0: self._ret()
            idx = self.assign(x)[0]
        if self.arrivals % EVERY == 0:
            mg, rm = self.merge_close()
            return (rm[idx], rm) if mg else (idx, None)
        return idx, None
    def merge_close(self, dist=None, factor=None):  # closest-pair merges <= t
        k = len(self.sums)
        if k < 2: return 0, {i: i for i in range(k)}
        sm = [[0.0] * k for _ in range(k)]
        for i in range(k):
            for j in range(i + 1, k): sm[i][j] = sm[j][i] = self._dp(i, j)
        alive = list(range(k)); par = list(range(k))
        while len(alive) > 1:
            bi = bj = -1; bv = None
            for a in range(len(alive)):
                for b in range(a + 1, len(alive)):
                    v = sm[alive[a]][alive[b]]
                    if bv is None or v < bv: bv, bi, bj = v, alive[a], alive[b]
            if bv is None or bv > self.t: break
            if bi > bj: bi, bj = bj, bi
            par[bj] = bi
            na, nb = self.counts[bi], self.counts[bj]
            sa, sb = self.sums[bi], self.sums[bj]
            for q in range(len(sa)): sa[q] += sb[q]
            for m in alive:
                if m != bi and m != bj:
                    sm[bi][m] = sm[m][bi] = (sm[bi][m] * na + sm[bj][m] * nb) / (na + nb)
            self.counts[bi] = na + nb
            self.members[bi] |= self.members[bj]
            alive.remove(bj)
        def find(x):
            while par[x] != x: par[x] = par[par[x]]; x = par[x]
            return x
        alive.sort()
        new_of = {o: n for n, o in enumerate(alive)}
        remap = {i: new_of[find(i)] for i in range(k)}
        self.sums = [self.sums[i] for i in alive]
        self.counts = [self.counts[i] for i in alive]
        self.members = [self.members[i] for i in alive]
        return k - len(alive), remap
class Organiser:  # insert/predict/level_up/reorganize/to_pred/counts/state
    def __init__(self, dist=None, tau_link=None, tau_seed=None, r=2,
                 maintain=False, plastic=True, scale=1.0):
        self.dist = dist or Dist()
        self.r = r; self.plastic = plastic
        self.lv = {l: Level(self.dist) for l in (1, 2, 3)}
        self.atom_vec = {}; self.atom_o1 = {}; self.atom_o2 = {}; self.atom_o3 = {}
        self.o1_o2 = {}; self.o2_o3 = {}; self.index_remaps = []; self.live_o1 = set()
    def _apply_remap(self, remap):
        self.index_remaps.append(dict(remap))
        self.atom_o1 = {a: sorted({remap[i] for i in v}) for a, v in self.atom_o1.items()}
    def insert(self, atom_id, vec):
        x = _unit(vec); self.atom_vec[atom_id] = x
        idx, remap = self.lv[1].observe(x)
        if remap is not None: self._apply_remap(remap)
        self.atom_o1[atom_id] = [idx]; self.lv[1].members[idx].add(atom_id)
        return {"o1": [idx]}
    def attach(self, atom_id, vec, idx):
        x = _unit(vec); self.atom_vec[atom_id] = x
        s = self.lv[1].sums[idx]
        for k in range(len(x)): s[k] += x[k]
        self.lv[1].counts[idx] += 1; self.lv[1].members[idx].add(atom_id); self.atom_o1[atom_id] = [idx]
        return {"o1": [idx]}
    def predict(self, vec):
        ds = self.lv[1].nearest(_unit(vec))
        return [i for d, i in ds[:max(self.r, 1)] if d <= self.lv[1].t]
    def second_parents(self):  # links only; sums updated for 1st parent only
        lv = self.lv[1]
        for a, v in self.atom_vec.items():
            first = self.atom_o1[a][0]; best, bd = -1, None
            for i in range(len(lv.sums)):
                if i == first: continue
                d = lv._di(v, i)
                if bd is None or d < bd: bd, best = d, i
            self.atom_o1[a] = [first, best] if best >= 0 and bd <= lv.t else [first]
    def refine(self):
        self.reorganize()
        if self.plastic and self.r >= 2: self.second_parents()
    def reorganize(self, region=None):
        merged, remap = self.lv[1].merge_close()
        if merged: self._apply_remap(remap)
        return {"merged_o1": merged, "remap": remap}
    def _stream_level(self, level, items, tagfmt):  # own t upfront, then join
        lv = self.lv[level]; links = []
        lv.res = [list(x) for x in items]; lv._ret(); lv.fx = True
        for i, x in enumerate(items):
            j, rm = lv.observe(x)
            if rm is not None: links = [rm[v] for v in links]
            links.append(j)
            lv.members[j].add(tagfmt % i)
        merged, rm = lv.merge_close()
        if merged: links = [rm[v] for v in links]
        return links
    def level_up(self):
        self.refine()
        self.lv[2] = Level(self.dist); self.lv[3] = Level(self.dist)
        d1 = [_unit(s) for s in self.lv[1].sums]
        self.o1_o2 = {i: [j] for i, j in enumerate(self._stream_level(2, d1, "o1:%d"))}
        d2 = [_unit(s) for s in self.lv[2].sums]
        self.o2_o3 = {j: [k] for j, k in enumerate(self._stream_level(3, d2, "o2:%d"))}
        for a, o1s in self.atom_o1.items():
            o2 = {self.o1_o2[i][0] for i in o1s}
            self.atom_o2[a] = o2
            self.atom_o3[a] = {self.o2_o3[j][0] for j in o2}
        self.level_up_end()
    def level_up_end(self): self.live_o1 = set(range(len(self.lv[1].sums)))
    def translate(self, i):
        for rm in self.index_remaps: i = rm.get(i, i)
        return i
    def periodic_dissolve(self): return {"dissolved": 0, "remap": {}}
    def to_pred(self):
        out = {}
        for key, mp, tag in (("3", self.atom_o1, "o1"), ("2", self.atom_o2, "o2"), ("1", self.atom_o3, "o3")):
            cm = {}
            for a, ix in mp.items():
                for i in ix: cm.setdefault(i, []).append(a)
            out[key] = [{"id": "%s_%d" % (tag, i), "members": sorted(m)} for i, m in sorted(cm.items())]
        return {"levels": out}
    def cluster_counts(self): return {l: len(self.lv[l].sums) for l in (1, 2, 3)}
    def to_state(self):
        return {"sums": {str(l): [list(s) for s in self.lv[l].sums] for l in (1, 2, 3)},
            "counts": {str(l): list(self.lv[l].counts) for l in (1, 2, 3)},
            "members": {str(l): [sorted(m) for m in self.lv[l].members] for l in (1, 2, 3)},
            "res": {str(l): [list(v) for v in self.lv[l].res] for l in (1, 2, 3)},
            "t": {str(l): self.lv[l].t for l in (1, 2, 3)}, "arrivals": {str(l): self.lv[l].arrivals for l in (1, 2, 3)},
            "atom_vec": {a: list(v) for a, v in self.atom_vec.items()},
            "atom_o1": {a: list(v) for a, v in self.atom_o1.items()},
            "atom_o2": {a: sorted(v) for a, v in self.atom_o2.items()},
            "atom_o3": {a: sorted(v) for a, v in self.atom_o3.items()},
            "o1_o2": {str(k): list(v) for k, v in self.o1_o2.items()}, "o2_o3": {str(k): list(v) for k, v in self.o2_o3.items()},
            "live_o1": sorted(self.live_o1)}
    def from_state(self, state):
        for l in (1, 2, 3):
            lv = self.lv[l]; k = str(l)
            lv.sums = [list(s) for s in state["sums"][k]]; lv.counts = list(state["counts"][k])
            lv.members = [set(m) for m in state["members"][k]]; lv.res = [list(v) for v in state["res"][k]]
            lv.t = state["t"][k]; lv.arrivals = state["arrivals"][k]; lv.fx = (l != 1)
        self.atom_vec = {a: list(v) for a, v in state["atom_vec"].items()}; self.live_o1 = set(state.get("live_o1", []))
        self.atom_o1 = {a: list(v) for a, v in state["atom_o1"].items()}; self.atom_o2 = {a: set(v) for a, v in state["atom_o2"].items()}
        self.atom_o3 = {a: set(v) for a, v in state["atom_o3"].items()}
        self.o1_o2 = {int(k): list(v) for k, v in state["o1_o2"].items()}; self.o2_o3 = {int(k): list(v) for k, v in state["o2_o3"].items()}
