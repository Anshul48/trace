"""Read-only, whole-snapshot diagnostics; never run inside repair_step."""
import numpy as np
from tlsys.local_repair import cos


def occupancy(values):
    a = np.asarray(list(values), dtype=np.float64)
    return {'count': len(a), 'min': float(a.min()) if len(a) else 0,
            'max': float(a.max()) if len(a) else 0,
            'mean': float(a.mean()) if len(a) else 0,
            'p50': float(np.quantile(a, .5)) if len(a) else 0,
            'p95': float(np.quantile(a, .95)) if len(a) else 0}


def metrics(engine):
    leaves, parents = engine.leaves, engine.parents
    atom_cos = []
    weighted = total = atom_weighted = atom_total = 0.0
    edge_count = duplicates = dangling = 0
    owners = set()
    bad = 0
    for lid, leaf in leaves.items():
        for aid in leaf['members']:
            if aid not in engine.ineligible:
                atom_cos.append(cos(engine.vectors[aid], leaf['descriptor']))
    for pid, par in parents.items():
        for aid in set(par['members']) - engine.ineligible:
            atom_weighted += cos(engine.vectors[aid], par['descriptor'])
            atom_total += 1
        children = par['children']
        edge_count += len(children)
        duplicates += len(children) - len(set(children))
        for lid in children:
            if lid not in leaves:
                dangling += 1
                continue
            owners.add(lid)
            n = len(set(leaves[lid]['members']) - engine.ineligible)
            score = cos(leaves[lid]['descriptor'], par['descriptor'])
            weighted += n * score
            total += n
            bad += score < engine.config.edge_threshold - engine.config.tie_tolerance
    orphan = len(set(leaves) - owners)
    union_bad = sum(set(p['members']) != {a for lid in p['children'] for a in leaves.get(lid, {}).get('members', ()) if a not in engine.ineligible} for p in parents.values())
    return {'leaf_occupancy': occupancy(len(v['members']) for v in leaves.values()),
            'parent_occupancy': occupancy(len(v['children']) for v in parents.values()),
            'leaf_member_weighted_cohesion': float(np.mean(atom_cos)) if atom_cos else 0,
            'parent_member_weighted_cohesion': weighted / total if total else 0,
            'parent_atom_weighted_cohesion': atom_weighted / atom_total if atom_total else 0,
            'orphan_children': orphan, 'orphan_rate': orphan / max(1, len(leaves)),
            'duplicate_edges': duplicates, 'duplicate_edge_rate': duplicates / max(1, edge_count),
            'dangling_edges': dangling, 'dangling_edge_rate': dangling / max(1, edge_count),
            'incoherent_edges': bad, 'parent_union_mismatches': union_bad,
            'debt': len(engine.queue), 'repair_counts': dict(engine.counts),
            'churn': engine.counts['edge_churn'], 'generation': engine.generation}
