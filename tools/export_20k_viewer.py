#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pure standard-library read-only extractor for 20k local run topology and telemetry.

STRICT SAFETY CONSTRAINTS:
1. ONLY standard library modules (argparse, collections, datetime, hashlib, json, os, sys, pathlib).
2. ZERO third-party or project imports (NO numpy, torch, tlsys, etc.).
3. ZERO store/database constructor calls (NO TLStore, Store, Committer, Fence, keeper).
4. Pure disk read operations (mode 'r' and 'rb'). Never mutates run store or lock files.
5. Inverts parent-child and leaf-atom relationships preserving full overlapping DAG memberships.
6. Emits docs/explorer/local_20k_data.json adhering strictly to the native schema.
"""

import argparse
import collections
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "docs" / "explorer" / "local_20k_data.json"
SOURCEFREEZE_SHA256 = "38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54"


def resolve_run_dir(given_path=None):
    if given_path:
        p = Path(given_path).resolve()
        if (p / "result.json").exists():
            return p
        raise FileNotFoundError(f"result.json not found in specified --run-dir: {given_path}")

    current_pointer = ROOT / "local-runs" / "current_run.json"
    if current_pointer.exists():
        try:
            data = json.loads(current_pointer.read_text(encoding="utf-8"))
            active = data.get("active_run")
            if active and (Path(active) / "result.json").exists():
                return Path(active).resolve()
        except Exception:
            pass

    fallback = ROOT / "local-run-20k"
    if (fallback / "result.json").exists():
        return fallback.resolve()

    raise FileNotFoundError("No verified 20k run directory found. Run ./install_and_run.sh first.")


def load_doc_texts():
    """Load licensed SciFact abstract texts from repro-20k prefix data."""
    docs = {}
    docs_file = ROOT / "repro-20k" / "data-20k" / "docs-100m.jsonl"
    if docs_file.exists():
        with open(docs_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                lines = [l.strip() for l in row.get("text", "").split("\n") if l.strip()]
                title = lines[0][:120] if lines else f"Document {row['doc_id']}"
                snippet = lines[1][:200] if len(lines) > 1 else ""
                docs[str(row["doc_id"])] = {"title": title, "snippet": snippet}
    return docs


def replay_projections_pure(store_path: Path, target_frontier: int):
    """Pure disk read and replay of layout-2 projections without any constructor."""
    meta_path = store_path / "tl_projections.json"
    docs_path = store_path / "tl_projections_docs.json"
    hier_path = store_path / "tl_projections_hier.json"
    journal_path = store_path / "tl_projections.journal.jsonl"

    for p in (meta_path, docs_path, hier_path):
        if not p.is_file():
            raise RuntimeError(f"Required projection file missing: {p}")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    if meta.get("version") != 1 or meta.get("layout") != 2:
        raise ValueError(f"Unsupported projection version/layout in {meta_path}")

    with open(hier_path, "r", encoding="utf-8") as f:
        base_hier = json.load(f)
    leaves = dict(base_hier.get("leaves", {}))
    parents = dict(base_hier.get("parents", {}))

    with open(docs_path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    current_frontier = meta.get("frontier", 0)

    if journal_path.is_file():
        with open(journal_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                rec = json.loads(line)
                fline = rec.get("frontier")
                if not isinstance(fline, int) or fline <= current_frontier:
                    continue
                if fline > target_frontier:
                    break

                leaves.update(rec.get("leaves", {}))
                parents.update(rec.get("parents", {}))
                docs_part = rec.get("docs", {})
                for doc, recs in docs_part.items():
                    if doc in docs:
                        docs[doc].update(recs)
                    else:
                        docs[doc] = dict(recs)
                current_frontier = fline

    return parents, leaves, docs


def main():
    parser = argparse.ArgumentParser(description="Pure stdlib read-only 20k run exporter")
    parser.add_argument("--run-dir", default=None, help="Path to pilot run directory")
    parser.add_argument("--out", default=str(OUT_FILE), help="Output JSON path")
    args = parser.parse_args()

    run_dir = resolve_run_dir(args.run_dir)
    print(f"Exporting from 20k run directory (pure stdlib reader): {run_dir}")

    result_path = run_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    status = result.get("status")
    if status != "PASS":
        print(f"ERROR: Run status is {status}, expected PASS", file=sys.stderr)
        sys.exit(1)

    pin = result["final"]["source_head"]
    target_frontier = int(pin[2])
    store_path = run_dir / "store"

    parents_raw, leaves_raw, docs_raw = replay_projections_pure(store_path, target_frontier)
    doc_texts = load_doc_texts()

    # Invert child -> parents
    child_parents = collections.defaultdict(list)
    for pid in sorted(parents_raw.keys()):
        pentry = parents_raw[pid]
        for cid in pentry.get("children", []):
            child_parents[cid].append(pid)

    # Invert atom -> leaves
    atom_leaves = collections.defaultdict(list)
    for lid in sorted(leaves_raw.keys()):
        lentry = leaves_raw[lid]
        for aid in lentry.get("members", []):
            atom_leaves[aid].append(lid)

    # Format parents (preserve authentic IDs and children)
    export_parents = []
    for pid in sorted(parents_raw.keys()):
        pentry = parents_raw[pid]
        export_parents.append({
            "id": pid,
            "children": sorted(pentry.get("children", [])),
            "atom_count": len(pentry.get("members", [])),
        })

    # Format leaves (preserve authentic parent_ids, atom_ids, doc_ids)
    export_leaves = []
    for lid in sorted(leaves_raw.keys()):
        lentry = leaves_raw[lid]
        doc_ids = sorted(list(set(seg["doc"] for seg in lentry.get("segments", []) if "doc" in seg)))
        export_leaves.append({
            "id": lid,
            "parent_ids": sorted(child_parents[lid]),
            "atom_ids": sorted(lentry.get("members", [])),
            "doc_ids": doc_ids,
        })

    # Format atoms (preserve doc_id, leaf_ids, title, snippet)
    export_atoms = []
    total_atoms_count = 0
    for doc_id in sorted(docs_raw.keys()):
        doc_atoms = docs_raw[doc_id]
        for aid in sorted(doc_atoms.keys()):
            arec = doc_atoms[aid]
            doc_meta = doc_texts.get(doc_id, {"title": f"Doc {doc_id}", "snippet": ""})
            export_atoms.append({
                "id": aid,
                "doc_id": doc_id,
                "leaf_ids": sorted(atom_leaves[aid]),
                "title": doc_meta["title"],
                "snippet": doc_meta["snippet"],
                "chunk_ix": arec.get("chunk_ix", 0),
                "span": arec.get("span"),
                "seq": arec.get("seq"),
            })
            total_atoms_count += 1

    # Graph connectivity assertions
    parent_child_edges = sum(len(p["children"]) for p in export_parents)
    leaf_atom_edges = sum(len(l["atom_ids"]) for l in export_leaves)
    multi_parent_leaves = sum(1 for l in export_leaves if len(l["parent_ids"]) > 1)
    multi_leaf_atoms = sum(1 for a in export_atoms if len(a["leaf_ids"]) > 1)
    orphan_leaves = sum(1 for l in export_leaves if len(l["parent_ids"]) == 0)
    orphan_atoms = sum(1 for a in export_atoms if len(a["leaf_ids"]) == 0)

    if len(export_parents) != result["final"]["parents"]:
        raise ValueError(f"Parent count mismatch: {len(export_parents)} != {result['final']['parents']}")
    if len(export_leaves) != result["final"]["leaves"]:
        raise ValueError(f"Leaf count mismatch: {len(export_leaves)} != {result['final']['leaves']}")
    if len(export_atoms) != result["final"]["atoms"]:
        raise ValueError(f"Atom count mismatch: {len(export_atoms)} != {result['final']['atoms']}")

    # Load 240 Evaluation Rows
    eval_queries = []
    if "evaluation" in result and "queries" in result["evaluation"]:
        for q in result["evaluation"]["queries"]:
            eval_queries.append({
                "probe": q["probe"],
                "family": q.get("family", ""),
                "leave_source_out": q.get("leave_source_out", False),
                "guided_recall10": q.get("guided_recall10", 0.0),
                "flat_recall10": q.get("flat_recall10", 0.0),
                "work": q.get("work", {}),
                "guided_scoring_rows": q.get("guided_scoring_rows", 0),
                "flat_scoring_rows": q.get("flat_scoring_rows", 0),
                "guided_wall_s": q.get("guided_wall_s", 0.0)
            })

    # Phase Telemetry
    phase_file = run_dir / "phase-telemetry.json"
    phase_telemetry = json.loads(phase_file.read_text(encoding="utf-8")) if phase_file.exists() else {}

    output = {
        "manifest": {
            "scope": "Local 20k Prefix Reproduction Run (Pure Stdlib Reader)",
            "source_freeze_sha256": SOURCEFREEZE_SHA256,
            "run_dir": str(run_dir),
            "store_head_pin": pin,
            "actual_tokens": result["input"]["actual_tokens"],
            "complete_documents": result["input"]["complete_documents"],
            "atoms_count": len(export_atoms),
            "leaves_count": len(export_leaves),
            "parents_count": len(export_parents),
            "parent_child_edges": parent_child_edges,
            "leaf_atom_edges": leaf_atom_edges,
            "multi_parent_leaves": multi_parent_leaves,
            "multi_leaf_atoms": multi_leaf_atoms,
            "orphan_leaves": orphan_leaves,
            "orphan_atoms": orphan_atoms,
            "status": status,
            "wall_s": result.get("wall_s", 0.0),
            "layout_mode": "deterministic_structural_hierarchy"
        },
        "parents": export_parents,
        "leaves": export_leaves,
        "atoms": export_atoms,
        "evaluation_queries": eval_queries,
        "phase_telemetry": phase_telemetry,
        "f1_append_visible": result.get("f1_append_visible", {}),
        "repair_to_zero": result.get("repair_to_zero", {}),
        "configured_caps": result.get("configured_caps", {})
    }

    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Exported pure 20k viewer data to {out_p} ({out_p.stat().st_size} bytes, "
          f"{len(export_parents)} parents, {len(export_leaves)} leaves, {len(export_atoms)} atoms)")


if __name__ == "__main__":
    main()
