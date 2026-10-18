#!/usr/bin/env python3
"""Build the slim hero membership payload from the recorded 20K run.

Reads docs/explorer/local_20k_data.json (256 KB full export) and writes
docs/assets/hero20k.json (<25 KB): 51 parents (file-order idx + primary
atom count, disjoint, sums to 144) plus 144 atoms (short id + primary
parent idx, with secondary parent idx for atoms sitting in one of the
8 multi-parent leaves).

Only structural ids and counts are exported: no titles, no snippets, no
spans, no telemetry, no paths, no author info.

Usage:  python3 tools/build_hero20k.py
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "explorer", "local_20k_data.json")
DST = os.path.join(ROOT, "docs", "assets", "hero20k.json")


def main():
    with open(SRC, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    parents = data["parents"]
    leaves = data["leaves"]
    atoms = data["atoms"]
    manifest = data["manifest"]

    assert len(parents) == 51, len(parents)
    assert len(leaves) == 81, len(leaves)
    assert len(atoms) == 144, len(atoms)
    assert manifest["multi_parent_leaves"] == 8, manifest["multi_parent_leaves"]

    parent_idx = {p["id"]: i for i, p in enumerate(parents)}
    leaf_map = {leaf["id"]: leaf for leaf in leaves}

    # Cross-check stored atom counts against leaf->parent wiring (stored
    # counts every leaf link, so atoms in multi-parent leaves count twice).
    per_link = [0] * len(parents)
    for leaf in leaves:
        for pid in leaf["parent_ids"]:
            per_link[parent_idx[pid]] += len(leaf["atom_ids"])
    for i, p in enumerate(parents):
        assert p["atom_count"] == per_link[i], (p["id"], p["atom_count"])

    # Exported n = PRIMARY membership (leaf_ids[0] -> parent_ids[0], the same
    # convention as the explorer's layout20kFull): disjoint, sums to 144.
    primary = [0] * len(parents)

    atom_rows = []
    multi = 0
    for atom in atoms:
        lids = atom["leaf_ids"]
        assert len(lids) == 1, atom["id"]  # manifest: multi_leaf_atoms == 0
        pids = leaf_map[lids[0]]["parent_ids"]
        assert 1 <= len(pids) <= 2, (atom["id"], pids)
        primary[parent_idx[pids[0]]] += 1
        row = atom["id"][:8] + ":" + str(parent_idx[pids[0]])
        if len(pids) == 2:
            row += ":" + str(parent_idx[pids[1]])
            multi += 1
        atom_rows.append(row)
    assert sum(primary) == 144, sum(primary)

    payload = {
        "meta": {
            "source": "docs/explorer/local_20k_data.json",
            "scope": "recorded 20K run",
            "parents": 51,
            "leaves": 81,
            "atoms": 144,
            "multi_parent_leaves": 8,
            "atoms_in_multi_parent_leaves": multi,
            "layout": "illustrative (deterministic ellipse + id-hash jitter)",
            "membership": "real (atom -> leaf -> primary parent from source file)",
            "n_def": "primary-membership atom count per parent (disjoint, sums to 144); 14 atoms in 8 multi-parent leaves carry a second parent idx in their atom row",
        },
        "parents": [
            {"id": p["id"], "n": n} for p, n in zip(parents, primary)
        ],
        "atoms": atom_rows,
    }

    with open(DST, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))

    size = os.path.getsize(DST)
    print("wrote %s (%d bytes, %d atoms, %d multi-parent)" % (DST, size, len(atom_rows), multi))
    assert size < 25 * 1024, size


if __name__ == "__main__":
    main()
