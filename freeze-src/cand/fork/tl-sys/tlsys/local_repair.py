"""Flag-gated bounded local membership repair (numpy + stdlib only).

Budget units are 384-coordinate vector rows. Setup/replay and explicit snapshot
serialization are separate from maintenance work. One maintenance proposal is
one ACCEPT_ATOMS artifact: old evidence stays committed, delta and queue cursor
publish together. Callers own a single writer; readers keep their original pin.
"""
from collections import OrderedDict
from dataclasses import dataclass, asdict
import bisect
import hashlib
import json
import math
import os
import uuid
import numpy as np

VERSION = 'local-repair-v1'


@dataclass(frozen=True)
class RepairConfig:
    enabled: bool = False
    edge_threshold: float = .45
    leaf_threshold: float = .55
    parent_cohesion_threshold: float = .45
    max_children: int = 16
    max_leaf_members: int = 25
    candidate_limit: int = 16
    seed_limit: int = 16
    tie_tolerance: float = 1e-12
    dimension: int = 384

    def __post_init__(self):
        if not (1 <= self.max_children <= 16 and 1 <= self.max_leaf_members <= 25):
            raise ValueError('repair caps cannot exceed source caps 16/25')
        if not (1 <= self.seed_limit <= 16 and self.candidate_limit >= 0 and self.dimension > 0):
            raise ValueError('invalid repair work bounds')
        for v in (self.edge_threshold, self.leaf_threshold, self.parent_cohesion_threshold):
            if not math.isfinite(v) or not -1 <= v <= 1:
                raise ValueError('invalid coherence threshold')
        if not math.isfinite(self.tie_tolerance) or self.tie_tolerance < 0:
            raise ValueError('invalid tie tolerance')


def cos(u, v):
    u, v = np.asarray(u, dtype=np.float64), np.asarray(v, dtype=np.float64)
    den = float(np.linalg.norm(u)) * float(np.linalg.norm(v))
    return float(u @ v / den) if den else 0.0


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def partition(ids, vectors, cap, cfg, scorer=cos):
    """Farthest pair among <=16 deterministic seeds, cosine assignment.

    Parent populations <=16 use the exact farthest pair. Overcapacity and
    leaf populations use a bounded ID prefix for seeds. Degenerate vectors
    take balanced ID halves; forced seed ownership prevents empty partitions.
    Capacity ties use ID order. >2*cap is infeasible and stays queued.
    """
    ids = sorted(set(ids))
    if len(ids) < 2 or len(ids) > 2 * cap:
        return None
    seed_ids = ids[:cfg.seed_limit]
    best = None
    for i, a in enumerate(seed_ids):
        for b in seed_ids[i + 1:]:
            score = scorer(vectors[a], vectors[b])
            if best is None or score < best[0] - cfg.tie_tolerance:
                best = (score, a, b)
    if best is None or best[0] >= 1 - cfg.tie_tolerance:
        mid = len(ids) // 2
        return ids[:mid], ids[mid:]
    _, a, b = best
    left, right = [a], [b]
    for x in ids:
        if x in (a, b):
            continue
        s0, s1 = scorer(vectors[x], vectors[a]), scorer(vectors[x], vectors[b])
        take_left = s0 >= s1 - cfg.tie_tolerance
        if len(left) >= cap:
            take_left = False
        elif len(right) >= cap:
            take_left = True
        (left if take_left else right).append(x)
    return sorted(left), sorted(right)


class RepairEngine:
    def __init__(self, vectors=None, leaves=None, parents=None, config=None, commit=None):
        self.config = config or RepairConfig()
        self.vectors = vectors if vectors is not None else {}
        self.leaves = dict(leaves or {})
        self.parents = dict(parents or {})
        self.commit = commit
        self.queue = OrderedDict()
        self.generation = 0
        self.last_revision_digest = None
        self.counts = {'checked': 0, 'reassigned': 0, 'parent_split': 0,
                       'leaf_split': 0, 'recomputed': 0, 'infeasible': 0,
                       'edge_churn': 0, 'coordinates': 0,
                       'member_rows': 0, 'cosine_rows': 0, 'equality_rows': 0}
        self._parent_ids = sorted(self.parents)
        self._lp, self._al = {}, {}
        for lid, entry in self.leaves.items():
            for aid in entry['members']:
                self._al.setdefault(aid, set()).add(lid)
        for pid, entry in self.parents.items():
            for lid in entry['children']:
                self._lp.setdefault(lid, set()).add(pid)

    def _put_leaf(self, lid, entry):
        old = self.leaves.get(lid, {})
        for aid in set(old.get('members', ())) - set(entry['members']):
            self._al.get(aid, set()).discard(lid)
        for aid in entry['members']:
            self._al.setdefault(aid, set()).add(lid)
        self.leaves[lid] = entry

    def _put_parent(self, pid, entry):
        old = self.parents.get(pid, {})
        for lid in set(old.get('children', ())) - set(entry['children']):
            self._lp.get(lid, set()).discard(pid)
        for lid in entry['children']:
            self._lp.setdefault(lid, set()).add(pid)
        if pid not in self.parents:
            bisect.insort(self._parent_ids, pid)
        self.parents[pid] = entry

    def touch(self, leaf_ids=(), parent_ids=()):
        if not self.config.enabled:
            return
        keys = {('leaf', lid) for lid in leaf_ids}
        keys.update(('parent', pid) for pid in parent_ids)
        for lid in leaf_ids:
            keys.update(('parent', pid) for pid in self._lp.get(lid, ()))
        for key in sorted(keys):
            self.queue.setdefault(key, None)

    def observe_leaf(self, lid, entry):
        self._put_leaf(lid, entry)
        self.touch([lid])

    def observe_parent(self, pid, entry):
        self._put_parent(pid, entry)
        self.touch(parent_ids=[pid])

    def retire_atoms(self, aids):
        touched = set()
        for aid in aids:
            touched.update(self._al.get(aid, ()))
        # Eligibility only: committed vectors and old memberships retained.
        self.ineligible.update(aids)
        self.touch(sorted(touched))

    @property
    def ineligible(self):
        if not hasattr(self, '_ineligible'):
            self._ineligible = set()
        return self._ineligible

    def _mean(self, members):
        if not members:
            return [0.0] * self.config.dimension
        if hasattr(self, '_work'):
            self._work['member_rows'] += len(members)
        mat = np.asarray([self.vectors[a] for a in members], dtype=np.float64)
        if mat.shape != (len(members), self.config.dimension) or not np.isfinite(mat).all():
            raise ValueError('missing, nonfinite or wrong-dimension vector')
        return mat.mean(axis=0).tolist()

    def _cos(self, u, v):
        self._work['cosine_rows'] += 1
        return cos(u, v)

    def _equal(self, u, v):
        # Counted identity comparison: one row per vector read, charged
        # BEFORE np.array_equal executes so no comparison runs uncounted.
        # Short-circuit callers (all/any) therefore charge exactly the
        # comparisons they execute. Same row-operation contract as
        # member_rows/cosine_rows: actual charge is rows * dimension.
        if hasattr(self, '_work'):
            self._work['equality_rows'] += 2
        return np.array_equal(u, v)

    def _leaf(self, old, members):
        members = sorted(set(members) - self.ineligible)
        segments = []
        member_set = set(members)
        for seg in old.get('segments', ()):
            original = seg.get('aids', ())
            indices = [i for i, a in enumerate(original) if a in member_set]
            aids = [original[i] for i in indices]
            if aids:
                entry = dict(seg, aids=aids)
                for key in ('spans', 'byte_spans'):
                    if key in seg:
                        if len(seg[key]) != len(original):
                            raise ValueError('unaligned segment provenance')
                        entry[key] = [seg[key][i] for i in indices]
                segments.append(entry)
        return {'members': members, 'descriptor': self._mean(members), 'segments': segments}

    def _parent(self, children, local_leaves):
        children = sorted(set(children))
        members = sorted({a for lid in children for a in
                          local_leaves.get(lid, self.leaves.get(lid, {})).get('members', ())}
                         - self.ineligible)
        return {'children': children, 'members': members, 'descriptor': self._mean(members)}

    def _candidates(self, exclude):
        # Bounded deterministic proposer. Best within this candidate set,
        # not a disguised whole-catalog regroup/nearest-parent guarantee.
        result = []
        for pid in self._parent_ids[:self.config.candidate_limit + 1]:
            if pid != exclude and len(self.parents[pid]['children']) < self.config.max_children:
                result.append(pid)
                if len(result) == self.config.candidate_limit:
                    break
        return result if self.config.candidate_limit else []

    def _estimate(self, key):
        kind, hid = key
        cfg = self.config
        leaves = set()
        pids = set()
        if kind == 'leaf' and hid in self.leaves:
            leaves.add(hid)
            pids.update(self._lp.get(hid, ()))
        elif kind == 'parent' and hid in self.parents:
            pids.add(hid)
            pids.update(self._candidates(hid))
        for pid in pids:
            leaves.update(self.parents[pid]['children'])
        # A changed leaf also republishes its other current parents. Account
        # for all their unions before any vector work is performed.
        pids.update(pid for lid in list(leaves) for pid in self._lp.get(lid, ()))
        for pid in pids:
            leaves.update(self.parents[pid]['children'])
        n = sum(len(self.leaves.get(lid, {}).get('members', ())) for lid in leaves)
        # Conservative: member recomputation + norms/cohesion/assignment,
        # edge comparisons, bounded pair comparisons and candidate scores.
        pair = min(cfg.seed_limit, len(self.leaves.get(hid, {}).get('members', ()))
                   if kind == 'leaf' else len(self.parents.get(hid, {}).get('children', ())))
        rows = (12 * n + 12 * len(leaves) + 6 * len(pids)
                + 3 * pair * pair + 6 * cfg.max_children * cfg.candidate_limit + 16)
        return rows * cfg.dimension

    def _overcap_leaves(self, kids):
        # Committed over-cap children, by eligible membership. Arithmetic
        # only: no vector work, so callers may use it before any proposal.
        cfg = self.config
        return [lid for lid in kids if lid in self.leaves
                and len(set(self.leaves[lid]['members']) - self.ineligible) > cfg.max_leaf_members]

    def _new_id(self, hid, label):
        return hid + '-repair-' + label + '-' + str(self.generation + 1)

    def _proposal(self, key):
        kind, hid = key
        cfg = self.config
        ls, ps, actions = {}, {}, []
        self._work = {'member_rows': 0, 'cosine_rows': 0, 'equality_rows': 0}
        # Infeasibility is a structural preflight, before vector work.
        # Oversized leaves needing >16 cap-sized groups stay explicit debt;
        # leaves needing 3..16 groups fall through to bounded multiway repair.
        if kind == 'leaf' and hid in self.leaves:
            _n = len(set(self.leaves[hid]['members']) - self.ineligible)
            if _n > 2 * cfg.max_leaf_members and (_n + cfg.max_leaf_members - 1) // cfg.max_leaf_members > 16:
                return None
        if kind == 'parent' and hid in self.parents and len(set(self.parents[hid]['children'])) > 2 * cfg.max_children:
            return None
        if kind == 'leaf' and hid in self.leaves:
            old = self.leaves[hid]
            fresh = self._leaf(old, old['members'])
            members = fresh['members']
            cohesion = (sum(self._cos(self.vectors[a], fresh['descriptor']) for a in members)
                        / len(members)) if members else 1.0
            needs = len(members) > cfg.max_leaf_members or cohesion < cfg.leaf_threshold - cfg.tie_tolerance
            if needs and len(members) > 1:
                parts = partition(members, self.vectors, cfg.max_leaf_members, cfg, self._cos)
                if parts is None:
                    # Bounded deterministic multiway capacity repair
                    # (qualification candidate only): previously infeasible
                    # oversized leaves split into <=16 cap-sized leaves via
                    # balanced ID chunks. No cosine/assignment work here; the
                    # original two-way path above is untouched for <=2*cap.
                    n = len(members)
                    groups = (n + cfg.max_leaf_members - 1) // cfg.max_leaf_members
                    if n <= 2 * cfg.max_leaf_members or groups > 16:
                        return None
                    ids = sorted(members)
                    base, rem = divmod(n, groups)
                    chunks, idx = [], 0
                    for g in range(groups):
                        size = base + (1 if g < rem else 0)
                        chunks.append(ids[idx:idx + size])
                        idx += size
                    fresh_ids = [self._new_id(hid, 'leaf-m%d' % i) for i in range(1, groups)]
                    ls[hid] = self._leaf(old, chunks[0])
                    for nid, chunk in zip(fresh_ids, chunks[1:]):
                        ls[nid] = self._leaf(old, chunk)
                    for pid in sorted(self._lp.get(hid, ())):
                        kids = sorted(set(self.parents[pid]['children']) | set(fresh_ids))
                        if len(kids) <= cfg.max_children:
                            ps[pid] = self._parent(kids, ls)
                        else:
                            # Full parent: retain all old edges, attach each
                            # sibling leaf to a singleton new parent.
                            ps[pid] = self._parent(self.parents[pid]['children'], ls)
                            for nid in fresh_ids:
                                npid = self._new_id('xpar-' + hashlib.sha256(nid.encode()).hexdigest()[:20], 'parent')
                                ps[npid] = self._parent([nid], ls)
                    if not self._lp.get(hid):
                        raise ValueError('orphan input leaf')
                    actions.append('leaf_split')
                # Splitting identical/zero members only for capacity avoids
                # endlessly subdividing an uninformative incoherent group.
                if len(members) <= cfg.max_leaf_members and all(
                        self._equal(self.vectors[members[0]], self.vectors[a]) for a in members):
                    parts = None
                if parts is not None:
                    new = self._new_id(hid, 'leaf')
                    ls[hid] = self._leaf(old, parts[0])
                    ls[new] = self._leaf(old, parts[1])
                    for pid in sorted(self._lp.get(hid, ())):
                        kids = sorted(set(self.parents[pid]['children'] + [new]))
                        if len(kids) <= cfg.max_children:
                            ps[pid] = self._parent(kids, ls)
                        else:
                            # Full parent: retain all old edges, attach sibling
                            # to a singleton new parent, never overflow.
                            ps[pid] = self._parent(self.parents[pid]['children'], ls)
                            npid = self._new_id('xpar-' + hashlib.sha256(new.encode()).hexdigest()[:20], 'parent')
                            ps[npid] = self._parent([new], ls)
                    if not self._lp.get(hid):
                        raise ValueError('orphan input leaf')
                    actions.append('leaf_split')
            if not ls:
                ls[hid] = fresh
                for pid in sorted(self._lp.get(hid, ())):
                    ps[pid] = self._parent(self.parents[pid]['children'], ls)
        elif kind == 'parent' and hid in self.parents:
            old = self.parents[hid]
            kids = sorted(set(old['children']))
            if any(lid not in self.leaves for lid in kids):
                raise ValueError('dangling input edge')
            # Committed over-cap children are organizer input, not repair
            # output: this parent scope cannot split leaves, so record debt
            # (None) before any vector work and let the leaf keys heal first.
            # Repair-created violations still raise loudly below.
            if self._overcap_leaves(kids):
                return None
            for lid in kids:
                ls[lid] = self._leaf(self.leaves[lid], self.leaves[lid]['members'])
            fresh = self._parent(kids, ls)
            # Candidate means are current member unions, not stale descriptors.
            candidates = {pid: self._parent(self.parents[pid]['children'], ls)
                          for pid in self._candidates(hid)}
            bad = [lid for lid in kids if self._cos(ls[lid]['descriptor'], fresh['descriptor'])
                   < cfg.edge_threshold - cfg.tie_tolerance]
            moved = False
            for lid in bad:
                scores = {pid: self._cos(ls[lid]['descriptor'], p['descriptor']) for pid, p in candidates.items()}
                # Stable ID winner at near-equal boundaries.
                ranked = []
                remaining = set(scores)
                while remaining:
                    best = max(scores[p] for p in remaining)
                    ties = sorted(p for p in remaining if scores[p] >= best - cfg.tie_tolerance)
                    ranked.extend(ties)
                    remaining.difference_update(ties)
                for pid in ranked:
                    score = scores[pid]
                    if (score >= cfg.edge_threshold - cfg.tie_tolerance
                            and lid not in candidates[pid]['children']):
                        ps[hid] = self._parent([x for x in kids if x != lid], ls)
                        ps[pid] = self._parent(candidates[pid]['children'] + [lid], ls)
                        actions.append('reassigned')
                        moved = True
                        break
                if moved:
                    break  # at most one move per revision
            if not moved:
                edge_coh = (sum(len(ls[lid]['members']) * self._cos(ls[lid]['descriptor'], fresh['descriptor']) for lid in kids)
                            / max(1, sum(len(ls[lid]['members']) for lid in kids)))
                if len(kids) > cfg.max_children or bad or edge_coh < cfg.parent_cohesion_threshold - cfg.tie_tolerance:
                    vecs = {lid: ls[lid]['descriptor'] for lid in kids}
                    parts = partition(kids, vecs, cfg.max_children, cfg, self._cos)
                    if parts is None and len(kids) > cfg.max_children:
                        return None
                    # No endless identical/zero-vector split at legal capacity.
                    if parts is not None and (len(kids) > cfg.max_children or any(
                            not self._equal(vecs[kids[0]], vecs[lid]) for lid in kids)):
                        ps[hid] = self._parent(parts[0], ls)
                        ps[self._new_id(hid, 'parent')] = self._parent(parts[1], ls)
                        actions.append('parent_split')
                if not ps:
                    ps[hid] = fresh
            # Every other parent of a recomputed child must see its new union.
            for lid in ls:
                for pid in sorted(self._lp.get(lid, ())):
                    if pid not in ps:
                        ps[pid] = self._parent(self.parents[pid]['children'], ls)
        # Omit byte-identical memberships/descriptors; seq is evidence metadata.
        def differs(a, b):
            return canonical({k: v for k, v in a.items() if k != 'seq'}) != canonical({k: v for k, v in b.items() if k != 'seq'})
        ls = {k: v for k, v in ls.items() if k not in self.leaves or differs(v, self.leaves[k])}
        ps = {k: v for k, v in ps.items() if k not in self.parents or differs(v, self.parents[k])}
        if not actions and (ls or ps):
            actions.append('recomputed')
        # Check changed edges and union; never validate by scanning entire store.
        for pid, par in ps.items():
            if len(par['children']) > cfg.max_children or len(par['children']) != len(set(par['children'])):
                raise ValueError('invalid repaired parent capacity/edges')
            expected = self._parent(par['children'], ls)
            if par['members'] != expected['members']:
                raise ValueError('invalid repaired parent union')
        for lid, leaf in ls.items():
            if len(leaf['members']) > cfg.max_leaf_members:
                raise ValueError('invalid repaired leaf capacity')
            owners = (self._lp.get(lid, set()) - set(ps)) | {pid for pid, p in ps.items() if lid in p['children']}
            if not owners:
                raise ValueError('repair creates orphan')
        edge_churn = sum(len(set(self.parents.get(pid, {}).get('children', ())) ^ set(par['children'])) for pid, par in ps.items())
        # Requeue only affected parents after membership movement/split; a
        # checked item without changes drains exactly once.
        touches = sorted({('parent', pid) for pid in ps}) if actions else []
        return {'version': VERSION, 'generation': self.generation + 1,
                'consumed': list(key), 'leaves': ls, 'parents': ps,
                'touches': [list(k) for k in touches], 'actions': actions,
                'edge_churn': edge_churn, 'work': dict(self._work)}

    def apply(self, record):
        digest = hashlib.sha256(canonical(record).encode()).hexdigest()
        if record['generation'] == self.generation and digest == self.last_revision_digest:
            return  # exact replay of the latest revision
        if record['version'] != VERSION or record['generation'] != self.generation + 1:
            raise ValueError('repair generation/version mismatch')
        for lid, entry in record['leaves'].items():
            self._put_leaf(lid, entry)
        for pid, entry in record['parents'].items():
            self._put_parent(pid, entry)
        self.queue.pop(tuple(record['consumed']), None)
        for key in record['touches']:
            self.queue.setdefault(tuple(key), None)
        self.generation = record['generation']
        self.last_revision_digest = digest
        self.counts['checked'] += 1
        for action in record['actions']:
            self.counts[action] += 1
        self.counts['edge_churn'] += record['edge_churn']
        self.counts['coordinates'] += record.get('coordinates', 0)
        for name in ('member_rows', 'cosine_rows', 'equality_rows'):
            # .get default 0 keeps older replay records (pre-equality_rows)
            # appliable without KeyError; their work simply adds no equality.
            self.counts[name] += record.get('work', {}).get(name, 0)

    def repair_step(self, budget):
        if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
            raise ValueError('budget is a nonnegative integer coordinate allowance')
        if not self.config.enabled:
            return {'enabled': False, 'spent': 0, 'checked': 0, 'debt': 0}
        spent = checked = 0
        blocked = None
        # Bounded durable-preserving scan: infeasible keys are skipped LOCALLY
        # for this call only (no counter/queue/order mutation, no budget
        # charge; refusals did zero vector work). Feasible keys keep the
        # original ordered-queue lifecycle, including a changed record's
        # requeue being consumed as a same-call no-op. An overcap parent
        # stages its missing overcap leaves as TEMPORARY local work items;
        # only a committed revision (apply) may change the durable queue.
        # A healed leaf clears its parents' local skip so they retry same
        # call. Metadata scan is O(remaining) per pick, no vector work.
        # Staged admission: each key pre-reserves its worst-case _estimate
        # (head-of-line block if unaffordable) but is charged only measured
        # work on commit, so healthy no-ops no longer consume worst case.
        skipped = set()
        temp = OrderedDict()
        while True:
            key = None
            from_temp = False
            for k in self.queue:
                if k not in skipped:
                    key = k
                    break
            if key is None:
                for k in temp:
                    if k not in skipped:
                        key = k
                        from_temp = True
                        break
            if key is None:
                break
            cost = self._estimate(key)
            if spent + cost > budget:
                blocked = blocked or 'budget'
                break
            record = self._proposal(key)
            if record is None:
                skipped.add(key)
                blocked = blocked or 'infeasible-local-two-way-split'
                if key[0] == 'parent' and key[1] in self.parents:
                    for lid in self._overcap_leaves(self.parents[key[1]]['children']):
                        tk = ('leaf', lid)
                        if tk not in self.queue and tk not in temp and tk not in skipped:
                            temp[tk] = None
                continue  # explicit debt, no cap-violating publication
            # Staged admission: `cost` (worst case) was reserved before the
            # proposal, so counted work above can never exceed the remaining
            # budget. Only measured `actual` is charged after success; the
            # unused reservation is refunded for later keys. Zero-work no-ops
            # still apply (drain exactly once) at zero charge.
            actual = sum(record['work'].values()) * self.config.dimension
            if actual > cost:
                raise RuntimeError('repair work accounting exceeded reserved budget')
            record['reserved_coordinates'] = cost
            record['coordinates'] = actual
            record['config'] = asdict(self.config)
            # Commit callback must atomically accept/reject this ONE record.
            # No queue, counts or membership mutation occurs before success;
            # a raise discards skipped/temp with the durable state untouched.
            if self.commit is not None:
                self.commit(record)
            self.apply(record)
            if from_temp:
                temp.pop(key, None)
                skipped.discard(key)
            spent += actual
            checked += 1
            for lid in record.get('leaves', ()):
                for pid in self._lp.get(lid, ()):
                    skipped.discard(('parent', pid))
        if not self.queue:
            blocked = None
        return {'enabled': True, 'spent': spent, 'checked': checked,
                'debt': len(self.queue), 'blocked': blocked, 'generation': self.generation}

    def snapshot(self):
        return {'config': asdict(self.config), 'leaves': self.leaves, 'parents': self.parents,
                'queue': [list(k) for k in self.queue], 'generation': self.generation,
                'last_revision_digest': self.last_revision_digest,
                'counts': dict(self.counts), 'ineligible': sorted(self.ineligible)}

    @classmethod
    def restore(cls, snapshot, vectors, commit=None):
        engine = cls(vectors, snapshot['leaves'], snapshot['parents'], RepairConfig(**snapshot['config']), commit)
        engine.queue = OrderedDict((tuple(k), None) for k in snapshot['queue'])
        engine.generation = snapshot['generation']
        engine.last_revision_digest = snapshot.get('last_revision_digest')
        engine.counts = dict(snapshot['counts'])
        # Old snapshots predate equality_rows: default to 0 so apply()
        # and later accounting never KeyError on the missing counter.
        engine.counts.setdefault('equality_rows', 0)
        engine.ineligible.update(snapshot['ineligible'])
        return engine


def membership_metas(meta):
    """Expand one atomically committed revision for ordinary hierarchy readers."""
    from tlsys.identity import ATOM_SCHEME
    record = meta.get('local_repair')
    if not isinstance(record, dict) or record.get('version') != VERSION:
        raise ValueError('unsupported repair generation')
    if meta.get('atom_scheme') != ATOM_SCHEME:
        raise ValueError('repair atom scheme mismatch')
    for kind, namespace in [('seg-leaf', 'leaves'), ('seg-parent', 'parents')]:
        for hid, entry in record[namespace].items():
            yield dict(entry, holon=hid, kind=kind, atom_scheme=ATOM_SCHEME)


class TLRepair:
    """Single-writer core-store adapter; queue reconstructs from committed truth.

    Attach via TLStore(..., local_repair=True, repair_config=...). Commit hooks
    consume only the new suffix, automatically enqueueing joins/revisions and
    retiring leaves. Cold replay is explicit setup cost, not maintenance work.
    """
    def __init__(self, tlstore, config):
        self.tl = tlstore
        self.engine = RepairEngine(config=config, commit=self._commit)
        self.frontier = 0
        self.base_timestamp = 0
        self.incarnation = None
        self.doc_atoms = {}
        self._committing = False
        self.sync_receipts = []

    def sync(self):
        if not self.engine.config.enabled or self._committing:
            return
        birth, epoch, mx, _ = self.tl.pin()
        if self.incarnation is not None and self.incarnation != (birth, epoch):
            raise RuntimeError('repair controller belongs to a different incarnation')
        self.incarnation = (birth, epoch)
        rows = self.tl.read_commits_all(birth, epoch, mx, kind='ACCEPT_ATOMS', min_seq=self.frontier)
        seqs = [r[0] for r in rows]
        op_by_seq = {r[0]: r[1] for r in rows}
        refs = self.tl.pub_refs(seqs)
        arows = self.tl.artifact_rows([a for seq in seqs for a in refs.get(seq, ())])
        for seq in seqs:
            for aid in refs.get(seq, ()):
                arow = arows.get(aid)
                if arow is None:
                    continue
                body = self.tl.read_artifact(aid, expect_digest=arow[4])
                try:
                    meta = json.loads(body)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(meta, dict):
                    continue
                if 'atom' in meta and 'descriptor' in meta and 'doc_id' in meta:
                    atom = meta['atom']
                    self.engine.vectors[atom] = meta['descriptor']
                    self.doc_atoms.setdefault(meta['doc_id'], set()).add(atom)
                    # Revisions of existing atoms also invalidate their owners.
                    self.engine.touch(sorted(self.engine._al.get(atom, ())))
                if 'local_repair' in meta:
                    # A committed crash-window record wins even when no local
                    # apply/checkpoint ran before the writer stopped.
                    list(membership_metas(meta))  # validate schema/scheme
                    if meta['local_repair']['generation'] > self.engine.generation:
                        self.engine.apply(meta['local_repair'])
                elif meta.get('kind') == 'seg-leaf':
                    self.engine.observe_leaf(meta['holon'], {k: meta.get(k, []) for k in ('members', 'descriptor', 'segments')})
                elif meta.get('kind') == 'seg-parent':
                    self.engine.observe_parent(meta['holon'], {k: meta.get(k, []) for k in ('members', 'descriptor', 'children')})
                ret = meta.get('retirement')
                if isinstance(ret, dict) and 'doc' in ret:
                    self.engine.retire_atoms(self.doc_atoms.get(ret['doc'], ()))
            self.frontier = seq
            self.base_timestamp = uuid.UUID(op_by_seq[seq]).int >> 80
        # Bounded telemetry; full receipts belong in the caller's evidence log.
        self.sync_receipts = [{'commits': len(rows), 'frontier': self.frontier}]

    def _commit(self, record):
        from tlsys.identity import ATOM_SCHEME
        from tlsys.store_if import format_commit_failure
        meta = {'atom_scheme': ATOM_SCHEME, 'local_repair': record}
        body = canonical(meta).encode()
        # Content-addressed preparation gives retries the same payload hash.
        # Ordinary core preparation mints a random artifact ID on every call,
        # which would conflict with a deterministic operation ID after refusal.
        content_hash = hashlib.sha256(body).hexdigest()
        artifact_id = 'a-repair-' + content_hash
        path = os.path.join(self.tl.store.artdir, artifact_id)
        if os.path.exists(path):
            with open(path, 'rb') as f:
                existing = f.read()
            if existing != body:
                # Preserve interrupted bytes; never delete failed preparation.
                os.rename(path, path + '.interrupted-' + uuid.uuid4().hex)
        if not os.path.exists(path):
            with open(path, 'xb') as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            fd = os.open(self.tl.store.artdir, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        else:
            # A previous attempt can have written complete bytes but failed
            # fsync. Seal reused bytes and their directory entry before retry.
            with open(path, 'rb') as f:
                os.fsync(f.fileno())
            fd = os.open(self.tl.store.artdir, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        artifact = {'artifact_id': artifact_id, 'store_id': 'tl-sys-local-repair',
                    'extent': 'whole-immutable-file', 'length': len(body),
                    'digest': 'sha256:' + content_hash}
        # Content-addressed operation ID gives retry identity, including queue
        # cursor/config and base pin. The core returns an existing commit on
        # retry rather than publishing a second revision.
        digest = hashlib.sha256((str(self.incarnation) + ':' + str(self.frontier)).encode() + body).hexdigest()
        raw_id = int(digest[:32], 16)
        raw_id = (self.base_timestamp << 80) | (raw_id & ((1 << 80) - 1))
        raw_id = (raw_id & ~(15 << 76)) | (7 << 76)
        raw_id = (raw_id & ~(3 << 62)) | (2 << 62)
        op_id = str(uuid.UUID(int=raw_id))
        op = {'op_id': op_id, 'kind': 'ACCEPT_ATOMS',
              'payload': {'meta_artifact': artifact['artifact_id'], 'local_repair_version': VERSION},
              'disclosure': {'leg': 'local-repair', 'generation': record['generation']},
              'approval_ref': None, 'artifacts': (artifact,)}
        self._committing = True
        try:
            results, _ = self.tl.commit_batch([op])
            if len(results) != 1 or results[0].get('status') != 'committed':
                raise RuntimeError('repair: ' + format_commit_failure(results[0]))
        finally:
            self._committing = False

    def repair_step(self, budget):
        self.sync()
        try:
            return self.engine.repair_step(budget)
        finally:
            # Replay the commit-before-local-apply crash window. Already applied
            # records are skipped; an accepted but unapplied record is applied.
            self.sync()

    def snapshot(self):
        self.sync()
        return {'version': VERSION, 'incarnation': list(self.incarnation or ()),
                'frontier': self.frontier, 'engine': self.engine.snapshot(),
                'doc_atoms': {d: sorted(a) for d, a in self.doc_atoms.items()}}
