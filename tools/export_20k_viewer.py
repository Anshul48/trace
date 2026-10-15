#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Extract authentic structural topology and query records from a 20k local run.

Reads store, result.json, probes.json, and repro-20k documents
to emit docs/explorer/local_20k_data.json adhering to DATA-CONTRACT.md.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAND = ROOT / "freeze-src" / "cand"
OUT_FILE = ROOT / "docs" / "explorer" / "local_20k_data.json"

sys.path.insert(0, str(CAND / "fork" / "tl-candidate-batch"))
sys.path.insert(0, str(CAND / "fork" / "tl-sys"))
sys.path.insert(0, str(CAND / "tools"))

from tlsys.store_if import TLStore
from tlsys.org_publication import PreparedFacade


def resolve_run_dir(given_path=None):
    if given_path:
        p = Path(given_path).resolve()
        if (p / "result.json").exists():
            return p
        raise FileNotFoundError(f"result.json not found in specified --run-dir: {given_path}")

    current_pointer = ROOT / "local-runs" / "current_run.json"
    if current_pointer.exists():
        try:
            data = json.loads(current_pointer.read_text())
            active = data.get("active_run")
            if active and (Path(active) / "result.json").exists():
                return Path(active).resolve()
        except Exception:
            pass

    fallback = ROOT / "local-run-20k"
    if (fallback / "result.json").exists():
        return fallback.resolve()

    raise FileNotFoundError("No verified 20k run directory found. Run ./install_and_run.sh first.")


def main():
    parser = argparse.ArgumentParser(description="Export 20k run data for explorer")
    parser.add_argument("--run-dir", default=None, help="Path to pilot run directory")
    parser.add_argument("--out", default=str(OUT_FILE), help="Output JSON path")
    args = parser.parse_args()

    run_dir = resolve_run_dir(args.run_dir)
    print(f"Exporting from 20k run directory: {run_dir}")

    result_path = run_dir / "result.json"
    result = json.loads(result_path.read_text())
    status = result.get("status")
    if status != "PASS":
        print(f"ERROR: Run status is {status}, expected PASS", file=sys.stderr)
        sys.exit(1)

    pin = tuple(result["final"]["source_head"])
    store_path = run_dir / "store"

    parents_out = []
    leaves_out = []
    atoms_out = []

    # Read licensed text snippets for the 88 complete documents in this prefix
    docs = {}
    docs_file = ROOT / "repro-20k" / "data-20k" / "docs-100m.jsonl"
    if docs_file.exists():
        with open(docs_file, "r", encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                lines = [l.strip() for l in row.get("text", "").split("\n") if l.strip()]
                title = lines[0][:120] if lines else f"Document {row['doc_id']}"
                snippet = lines[1][:200] if len(lines) > 1 else ""
                docs[row["doc_id"]] = {"title": title, "snippet": snippet}

    if store_path.exists():
        tl = TLStore(str(store_path), create=False)
        facade = PreparedFacade(tl, pin, [])

        parent_map = {}
        for pid in sorted(facade.parents.keys()):
            p = facade.parents[pid]
            children = list(p.get("children", []))
            members = list(p.get("members", []))
            node = {
                "id": pid,
                "leaf_count": len(children),
                "atom_count": len(members),
                "leaf_ids": children,
            }
            parents_out.append(node)
            parent_map[pid] = node

        for lid in sorted(facade.leaves.keys()):
            leaf = facade.leaves[lid]
            members = list(leaf.get("members", []))
            parent_id = None
            for pid, pnode in parent_map.items():
                if lid in pnode["leaf_ids"]:
                    parent_id = pid
                    break
            node = {
                "id": lid,
                "parent_id": parent_id,
                "atom_count": len(members),
                "atom_ids": members,
            }
            leaves_out.append(node)

        for aid in sorted(facade._index.atoms.keys()):
            atom = facade._index.atoms[aid]
            doc_id = str(atom.get("doc_id", ""))
            doc_meta = docs.get(doc_id, {"title": f"Doc {doc_id}", "snippet": ""})
            atoms_out.append({
                "id": aid,
                "doc_id": doc_id,
                "title": doc_meta["title"],
                "snippet": doc_meta["snippet"]
            })
        total_atoms = facade.atom_count
        total_leaves = len(facade.leaves)
        total_parents = len(facade.parents)
    else:
        # Fallback if store was omitted
        total_atoms = result["final"]["atoms"]
        total_leaves = result["final"]["leaves"]
        total_parents = result["final"]["parents"]

    # Load 120 Probes & 240 Evaluation Rows
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
    phase_telemetry = json.loads(phase_file.read_text()) if phase_file.exists() else {}

    output = {
        "manifest": {
            "scope": "Local 20k Prefix Reproduction Run (Actual Frozen Engine Execution)",
            "source_freeze_sha256": "38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54",
            "run_dir": str(run_dir),
            "store_head_pin": list(pin),
            "actual_tokens": result["input"]["actual_tokens"],
            "complete_documents": result["input"]["complete_documents"],
            "atoms_count": total_atoms,
            "leaves_count": total_leaves,
            "parents_count": total_parents,
            "status": status,
            "wall_s": result.get("wall_s", 0.0),
            "layout_mode": "deterministic_structural_hierarchy"
        },
        "parents": parents_out,
        "leaves": leaves_out,
        "atoms": atoms_out,
        "evaluation_queries": eval_queries,
        "phase_telemetry": phase_telemetry,
        "f1_append_visible": result.get("f1_append_visible", {}),
        "repair_to_zero": result.get("repair_to_zero", {})
    }

    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(output, indent=2))
    print(f"Exported 20k viewer data to {out_p} ({out_p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
