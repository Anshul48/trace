#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pure standard-library read-only extractor for 20k local run topology and telemetry.

STRICT SAFETY CONSTRAINTS:
1. ONLY standard library modules (argparse, collections, datetime, hashlib, json, os, sys, pathlib).
2. ZERO third-party or project imports (NO numpy, torch, tlsys, etc.).
3. ZERO store/database constructor calls (NO TLStore, Store, Committer, Fence, keeper).
4. Pure disk read operations (mode 'r' and 'rb'). Never mutates run store or lock files.
5. Inverts parent-child and leaf-atom relationships preserving full overlapping DAG memberships.
6. Emits local_20k_data.json adhering strictly to the native schema.
"""

import argparse
import collections
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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

    raise FileNotFoundError("No verified 20k run directory found. Run ./install_and_run.sh first.")


def load_doc_texts(data_dir=None):
    """Load licensed SciFact abstract texts from repro-20k prefix data."""
    docs = {}
    if data_dir:
        docs_file = Path(data_dir) / "docs-100m.jsonl"
    else:
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


def replay_projections_pure(store_path: Path, expected_pin: list):
    """Pure disk read and replay matching frozen proj.py journal replacement semantics."""
    meta_path = store_path / "tl_projections.json"
    docs_path = store_path / "tl_projections_docs.json"
    hier_path = store_path / "tl_projections_hier.json"
    journal_path = store_path / "tl_projections.journal.jsonl"

    for p in (meta_path, docs_path, hier_path):
        if not p.is_file():
            raise RuntimeError(f"Required projection file missing: {p}")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    if not isinstance(meta, dict):
        raise ValueError(f"Projection meta at {meta_path} is not a dict")
    if meta.get("version") != 1:
        raise ValueError(f"Unsupported projection version: {meta.get('version')}")
    if meta.get("layout") != 2:
        raise ValueError(f"Expected layout 2, got: {meta.get('layout')}")

    target_frontier = int(expected_pin[2])
    target_triple = expected_pin[3]

    base_frontier = meta.get("frontier", 0)
    current_frontier = base_frontier
    current_triple = meta.get("triple")

    docs_new = {}
    hier_new = {"leaves": {}, "parents": {}}
    xdoc = dict(meta.get("xdoc", {}))
    retired = dict(meta.get("retired", {}))

    targets = (
        ("docs", docs_new),
        ("leaves", hier_new["leaves"]),
        ("parents", hier_new["parents"]),
        ("xdoc", xdoc),
        ("retired", retired),
    )

    if journal_path.is_file():
        with open(journal_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, json.JSONDecodeError) as e:
                    raise RuntimeError(f"Journal line {line_no} JSON parse failure: {e}") from e
                if not isinstance(rec, dict):
                    raise ValueError(f"Journal line {line_no} is not a dict")
                fline = rec.get("frontier")
                if not isinstance(fline, int) or fline <= current_frontier:
                    raise ValueError(f"Journal line {line_no}: out-of-order frontier {fline} <= {current_frontier}")
                if fline > target_frontier:
                    raise ValueError(f"Journal line {line_no}: frontier {fline} exceeds pin {target_frontier}")

                for key, target in targets:
                    part = rec.get(key, {})
                    if not isinstance(part, dict):
                        raise ValueError(f"Journal line {line_no} key '{key}' is not a dict")
                    target.update(part)

                current_frontier = fline
                current_triple = rec.get("triple")

    if current_frontier != target_frontier:
        raise RuntimeError(f"Journal replay halted at frontier {current_frontier}, expected pin {target_frontier}")
    if current_triple != target_triple:
        raise RuntimeError(f"Journal replay triple {current_triple} != expected {target_triple}")

    with open(hier_path, "r", encoding="utf-8") as f:
        base_hier = json.load(f)
    if not isinstance(base_hier, dict):
        raise ValueError(f"Base hierarchy at {hier_path} is not a dict")
    leaves = dict(base_hier.get("leaves", {}))
    parents = dict(base_hier.get("parents", {}))
    leaves.update(hier_new["leaves"])
    parents.update(hier_new["parents"])

    with open(docs_path, "r", encoding="utf-8") as f:
        base_docs = json.load(f)
    if not isinstance(base_docs, dict):
        raise ValueError(f"Base docs at {docs_path} is not a dict")
    docs = dict(base_docs)
    for doc, recs in docs_new.items():
        if doc in docs:
            docs[doc].update(recs)
        else:
            docs[doc] = dict(recs)

    return parents, leaves, docs


def extract_run_uuid(run_dir: Path) -> str:
    # Match UUID pattern in directory name e.g. run-YYYYMMDDTHHMMSSZ-<UUID>
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", run_dir.name, re.I)
    if m:
        return m.group(1).lower()
    return run_dir.name


def main():
    parser = argparse.ArgumentParser(description="Pure stdlib read-only 20k run exporter")
    parser.add_argument("--run-dir", default=None, help="Path to pilot run directory")
    parser.add_argument("--data-dir", default=None, help="Path to prefix data-20k directory")
    parser.add_argument("--out", default=None, help="Output JSON path")
    args = parser.parse_args()

    run_dir = resolve_run_dir(args.run_dir)
    print(f"Exporting from 20k run directory (pure stdlib reader): {run_dir}")

    result_path = run_dir / "result.json"
    result_raw = result_path.read_bytes()
    result_sha256 = hashlib.sha256(result_raw).hexdigest()
    result = json.loads(result_raw.decode("utf-8"))

    status = result.get("status")
    if status != "PASS":
        print(f"ERROR: Run status is {status}, expected PASS", file=sys.stderr)
        sys.exit(1)

    pin = result["final"]["source_head"]
    run_uuid = extract_run_uuid(run_dir)
    store_path = run_dir / "store"

    if args.out:
        out_p = Path(args.out)
    else:
        out_p = run_dir / "local_20k_data.json"

    # Destination safety and reuse check:
    # If out_p exists, it must strictly be a valid export matching run_uuid, result_sha256, and PASS.
    # If malformed, mismatch, directory, or non-file, fail closed non-zero without modifying output or store.
    if out_p.exists():
        if not out_p.is_file():
            print(f"ERROR: Destination {out_p} already exists and is not a regular file.", file=sys.stderr)
            sys.exit(1)
        try:
            existing = json.loads(out_p.read_text(encoding="utf-8"))
            ex_manifest = existing.get("manifest", {})
            if (ex_manifest.get("run_uuid") == run_uuid and
                ex_manifest.get("result_sha256") == result_sha256 and
                ex_manifest.get("status") == "PASS"):
                print(f"Verified existing valid export at {out_p} (run_uuid={run_uuid}). Reusing unchanged.")
                return
            else:
                print(f"ERROR: Destination {out_p} already exists but does not match run identity/result SHA. Refusing to overwrite.", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"ERROR: Destination {out_p} already exists but is corrupt or invalid JSON: {e}. Refusing to overwrite.", file=sys.stderr)
            sys.exit(1)

    parents_raw, leaves_raw, docs_raw = replay_projections_pure(store_path, pin)
    doc_texts = load_doc_texts(args.data_dir)

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

    # Format atoms (preserve doc_id, leaf_ids, title, snippet, chunk_ix, span, byte_span, seq)
    # Vectors explicitly omitted per presentation contract
    export_atoms = []
    for doc_id in sorted(docs_raw.keys()):
        doc_atoms = docs_raw[doc_id]
        for aid in sorted(doc_atoms.keys()):
            arec = doc_atoms[aid]
            atom_entry = {
                "id": aid,
                "doc_id": doc_id,
                "leaf_ids": sorted(atom_leaves[aid]),
                "chunk_ix": arec.get("chunk_ix", 0),
                "span": arec.get("span"),
                "byte_span": arec.get("byte_span", arec.get("span")),
                "seq": arec.get("seq"),
            }
            if doc_id in doc_texts:
                atom_entry["title"] = doc_texts[doc_id]["title"]
                atom_entry["snippet"] = doc_texts[doc_id]["snippet"]
            export_atoms.append(atom_entry)

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

    # Bidirectional resolution verification
    p_ids = {p["id"] for p in export_parents}
    l_ids = {l["id"] for l in export_leaves}
    a_ids = {a["id"] for a in export_atoms}
    d_ids = set(docs_raw.keys())

    for p in export_parents:
        for cid in p["children"]:
            if cid not in l_ids:
                raise ValueError(f"Parent child {cid} not in leaves")
    for l in export_leaves:
        for pid in l["parent_ids"]:
            if pid not in p_ids:
                raise ValueError(f"Leaf parent {pid} not in parents")
        for aid in l["atom_ids"]:
            if aid not in a_ids:
                raise ValueError(f"Leaf atom {aid} not in atoms")
        for did in l["doc_ids"]:
            if did not in d_ids:
                raise ValueError(f"Leaf doc {did} not in docs")
    for a in export_atoms:
        for lid in a["leaf_ids"]:
            if lid not in l_ids:
                raise ValueError(f"Atom leaf {lid} not in leaves")
        if a["doc_id"] not in d_ids:
            raise ValueError(f"Atom doc {a['doc_id']} not in docs")

    # Evaluation queries from fresh result.json - retain EXACT complete dictionaries verbatim
    eval_queries = []
    if "evaluation" in result and "queries" in result["evaluation"]:
        for q in result["evaluation"]["queries"]:
            # Copy exact complete dictionary from fresh result.json
            eval_queries.append(dict(q))

    # Phase Telemetry
    phase_file = run_dir / "phase-telemetry.json"
    phase_telemetry = json.loads(phase_file.read_text(encoding="utf-8")) if phase_file.exists() else {}

    output = {
        "manifest": {
            "scope": "Local 20k Prefix Reproduction Run (Pure Stdlib Reader)",
            "source_freeze_sha256": SOURCEFREEZE_SHA256,
            "run_uuid": run_uuid,
            "result_sha256": result_sha256,
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

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Exported pure 20k viewer data to {out_p} ({out_p.stat().st_size} bytes, "
          f"{len(export_parents)} parents, {len(export_leaves)} leaves, {len(export_atoms)} atoms, {len(eval_queries)} queries)")


if __name__ == "__main__":
    main()
