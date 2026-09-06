#!/usr/bin/env python3
"""1K Shard Cluster Assembler for TRACE-CAP-001 (Cloud Calibration).

Assembler Identity:
  File: docs/program/inbox/cap-mod01-cloud-1k/assemble_1k_clusters.py
  Function: assemble_1k_clusters
  Params:
    - manifest: docs/program/inbox/l1-02-corpus-capsule-20260828/evidence/corpus_manifest.json
    - shard_ranges: musique:[0,800), beir-fiqa:[0,106), beir-scifact:[0,52), beir-nfcorpus:[0,36), multihop-rag:[0,6)
    - atomize_defaults: src/trace/v2/atomizer.py::atomize (max_chars=1200)
    - cluster_size: 3 (contiguous triples in shard order)
    - seed: 42
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from trace.v2.atomizer import atomize

DEFAULT_BASE_DATA_ROOT = Path("/mnt/c/Users/anshu/AppData/Local/trace-bench-data/normalized/d2b-20260819/repair-mq-roundtrip-20260820")
DEFAULT_OUTPUT_FILE = REPO_ROOT / "docs/program/inbox/cap-mod01-cloud-1k/clusters_1k_v1.json"

SHARD_SLICES = [
    ("musique", 800),
    ("beir-fiqa", 106),
    ("beir-scifact", 52),
    ("beir-nfcorpus", 36),
    ("multihop-rag", 6),
]
EXPECTED_BASELINE_ATOMS = 2280
TOLERANCE_PCT = 0.15


def derive_1k_docs(
    base_data_root: Path = DEFAULT_BASE_DATA_ROOT,
    shard_slices: list[tuple[str, int]] = SHARD_SLICES,
) -> list[dict[str, Any]]:
    docs = []
    for dataset_name, count in shard_slices:
        corpus_path = base_data_root / dataset_name / "corpus.jsonl"
        if not corpus_path.exists():
            raise FileNotFoundError(f"Corpus file not found: {corpus_path}")

        loaded = 0
        with open(corpus_path, "r", encoding="utf-8") as f:
            for line in f:
                if loaded >= count:
                    break
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                record["_dataset"] = dataset_name
                record["_shard_index"] = len(docs)
                record["_dataset_ordinal"] = loaded
                docs.append(record)
                loaded += 1

        if loaded != count:
            raise ValueError(
                f"Dataset {dataset_name}: expected {count} docs, loaded {loaded}"
            )

    return docs


def assemble_1k_clusters(
    output_path: Path = DEFAULT_OUTPUT_FILE,
    base_data_root: Path = DEFAULT_BASE_DATA_ROOT,
    shard_slices: list[tuple[str, int]] = SHARD_SLICES,
    seed: int = 42,
) -> dict[str, Any]:
    docs = derive_1k_docs(base_data_root=base_data_root, shard_slices=shard_slices)
    if len(docs) != 1000:
        raise ValueError(f"Expected 1,000 docs, got {len(docs)}")

    raw_atoms: list[dict[str, Any]] = []

    for doc in docs:
        title = (doc.get("title") or "").strip()
        text = (doc.get("text") or "").strip()
        dataset_name = doc["_dataset"]
        doc_id = doc.get("internal_id") or doc.get("segment_internal_id") or f"{dataset_name}:{doc['_dataset_ordinal']}"

        if title:
            full_text = f"{title}\n\n{text}"
        else:
            full_text = text

        atom_drafts = atomize(full_text)
        for draft in atom_drafts:
            content = draft.content
            c_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            raw_atoms.append({
                "content": content,
                "content_hash": c_hash,
                "title": title or doc.get("source_document_key") or dataset_name,
                "dataset": dataset_name,
                "doc_id": doc_id,
            })

    total_atom_count = len(raw_atoms)
    deviation = abs(total_atom_count - EXPECTED_BASELINE_ATOMS) / EXPECTED_BASELINE_ATOMS
    print(f"Total atom count: {total_atom_count} (baseline {EXPECTED_BASELINE_ATOMS}, deviation {deviation:.2%})")
    if deviation > TOLERANCE_PCT:
        raise RuntimeError(
            f"HALT: atom count {total_atom_count} deviates from {EXPECTED_BASELINE_ATOMS} by {deviation:.2%} (> {TOLERANCE_PCT:.0%})"
        )

    clusters = []
    num_triples = total_atom_count // 3

    for c_idx in range(num_triples):
        cluster_id = f"cluster_{c_idx + 1:03d}"
        triple_atoms = raw_atoms[c_idx * 3 : (c_idx + 1) * 3]

        theme = triple_atoms[0]["title"]
        if not theme:
            theme = triple_atoms[0]["content"][:60].strip()

        source_atoms = []
        for ord_idx, a in enumerate(triple_atoms):
            node_id = f"atom_{c_idx + 1:03d}_{ord_idx + 1:02d}"
            atom_version_id = f"av_{c_idx + 1:03d}_{ord_idx + 1:02d}"
            source_atoms.append({
                "node_id": node_id,
                "atom_version_id": atom_version_id,
                "workspace_id": "cap_mod01_cloud_1k",
                "content": a["content"],
                "content_hash": a["content_hash"],
                "properties": {
                    "title": a["title"],
                    "source_dataset": a["dataset"],
                    "cluster_id": cluster_id,
                    "ordinal": ord_idx,
                    "doc_id": a["doc_id"],
                },
            })

        clusters.append({
            "cluster_id": cluster_id,
            "theme": theme,
            "atom_count": len(source_atoms),
            "source_atoms": source_atoms,
        })

    manifest_payload: dict[str, Any] = {
        "manifest_name": "clusters_1k_v1",
        "version": "1.0.0",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "seed": seed,
        "total_clusters": len(clusters),
        "total_atoms": sum(len(c["source_atoms"]) for c in clusters),
        "raw_atom_count": total_atom_count,
        "clusters": clusters,
    }

    clusters_canonical = json.dumps(manifest_payload["clusters"], sort_keys=True, indent=2)
    manifest_payload["manifest_sha256"] = hashlib.sha256(clusters_canonical.encode("utf-8")).hexdigest()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest_payload, f, indent=2)

    print(f"Successfully assembled {len(clusters)} clusters ({manifest_payload['total_atoms']} atoms) to {output_path}")
    print(f"Manifest SHA256: {manifest_payload['manifest_sha256']}")
    return manifest_payload


if __name__ == "__main__":
    assemble_1k_clusters()
