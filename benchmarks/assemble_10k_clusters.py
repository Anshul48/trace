#!/usr/bin/env python3
"""10K Shard Cluster Assembler for TRACE-CAP-001 (Cloud 10K Consolidation).

Normative Specs:
  - docs/program/inbox/cap-mod01/CLOUD_10K_SHADOW_SPEC.md
  - docs/program/inbox/cap-mod01/GC_BALLOT_RECEIPT.md
  - docs/program/inbox/cap-mod01/MODEL_PROMPT_REVISION_PIN.json

Assembler Identity:
  File: benchmarks/assemble_10k_clusters.py
  Function: assemble_10k_clusters
  Params:
    - shard_ranges:
        musique: 8,000 ([0, 8000))
        beir-fiqa: 1,058 ([0, 1058))
        beir-scifact: 518 ([0, 518))
        beir-nfcorpus: 363 ([0, 363))
        multihop-rag: 61 ([0, 61))
        Total: 10,000 docs exact
    - data_root: /mnt/c/Users/anshu/AppData/Local/trace-bench-data/normalized/d2b-20260819/repair-mq-roundtrip-20260820
    - atomize_defaults: src/trace/v2/atomizer.py::atomize (max_chars=1200)
    - cluster_size: 3 (contiguous triples in shard order)
    - consolidation_window: 2,000 clusters drawn by deterministic stride over shard order (seed 42)
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import random
import resource
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from trace.v2.atomizer import atomize

DEFAULT_BASE_DATA_ROOT = Path("/mnt/c/Users/anshu/AppData/Local/trace-bench-data/normalized/d2b-20260819/repair-mq-roundtrip-20260820")
DEFAULT_OUT_DIR = REPO_ROOT / "docs/program/inbox/cap-mod01-cloud-10k"
DEFAULT_SAMPLED_OUTPUT_FILE = DEFAULT_OUT_DIR / "clusters_10k_v1.json"
DEFAULT_FULL_OUTPUT_FILE = DEFAULT_OUT_DIR / "clusters_10k_full.json"
DEFAULT_DOSSIER_FILE = DEFAULT_OUT_DIR / "core_ingest_dossier.json"

SHARD_SLICES_10K = [
    ("musique", 8000),
    ("beir-fiqa", 1058),
    ("beir-scifact", 518),
    ("beir-nfcorpus", 363),
    ("multihop-rag", 61),
]

EXPECTED_TOTAL_DOCS = 10000
SAMPLE_WINDOW_SIZE = 2000
SEED = 42


def derive_10k_docs(
    base_data_root: Path = DEFAULT_BASE_DATA_ROOT,
    shard_slices: list[tuple[str, int]] = SHARD_SLICES_10K,
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


def sample_strided_clusters(
    all_clusters: list[dict[str, Any]],
    k: int = SAMPLE_WINDOW_SIZE,
    seed: int = SEED,
) -> tuple[list[dict[str, Any]], list[int], dict[str, Any]]:
    """Sample K clusters drawn by deterministic stride over shard order (seed 42)."""
    n = len(all_clusters)
    if k > n:
        raise ValueError(f"Requested {k} clusters but only {n} available")

    stride = n / k
    rng = random.Random(seed)
    offset = rng.uniform(0.0, stride)

    indices = [int(offset + i * stride) for i in range(k)]

    # Validate strict monotonic uniqueness
    if len(indices) != k or len(set(indices)) != k:
        # Fallback to pure linspace if any rounding collision occurs
        indices = [int(round(i * (n - 1) / (k - 1))) for i in range(k)]

    sampled = [all_clusters[idx] for idx in indices]

    stride_meta = {
        "total_available_clusters": n,
        "sample_window_size": k,
        "stride": stride,
        "seed": seed,
        "start_offset": offset,
        "min_index": indices[0],
        "max_index": indices[-1],
    }

    return sampled, indices, stride_meta


def assemble_10k_clusters(
    out_dir: Path = DEFAULT_OUT_DIR,
    base_data_root: Path = DEFAULT_BASE_DATA_ROOT,
    shard_slices: list[tuple[str, int]] = SHARD_SLICES_10K,
    sample_window: int = SAMPLE_WINDOW_SIZE,
    seed: int = SEED,
) -> tuple[dict[str, Any], dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()

    # Core Phase Ingestion & Atomization
    docs = derive_10k_docs(base_data_root=base_data_root, shard_slices=shard_slices)
    if len(docs) != EXPECTED_TOTAL_DOCS:
        raise ValueError(f"Expected {EXPECTED_TOTAL_DOCS} docs, got {len(docs)}")

    t_loaded = time.perf_counter()
    load_duration = t_loaded - t_start

    raw_atoms: list[dict[str, Any]] = []
    total_source_chars = 0
    total_token_est = 0

    for doc in docs:
        title = (doc.get("title") or "").strip()
        text = (doc.get("text") or "").strip()
        dataset_name = doc["_dataset"]
        doc_id = doc.get("internal_id") or doc.get("segment_internal_id") or f"{dataset_name}:{doc['_dataset_ordinal']}"

        if title:
            full_text = f"{title}\n\n{text}"
        else:
            full_text = text

        total_source_chars += len(full_text)
        total_token_est += len(full_text.split())

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

    t_atomized = time.perf_counter()
    atomize_duration = t_atomized - t_loaded
    total_ingest_duration = t_atomized - t_start

    total_atom_count = len(raw_atoms)
    num_triples = total_atom_count // 3
    docs_per_sec = len(docs) / total_ingest_duration
    atoms_per_sec = total_atom_count / total_ingest_duration
    tokens_per_sec = total_token_est / total_ingest_duration

    rusage = resource.getrusage(resource.RUSAGE_SELF)
    peak_rss_mb = rusage.ru_maxrss / 1024.0  # ru_maxrss is in KB on Linux

    print(f"[CORE PHASE] Ingested & atomized {len(docs)} docs in {total_ingest_duration:.2f}s")
    print(f"  Docs/sec: {docs_per_sec:.1f} (target >= 800 docs/s: {'PASS' if docs_per_sec >= 800 else 'FAIL'})")
    print(f"  Atoms/sec: {atoms_per_sec:.1f} (total atoms: {total_atom_count})")
    print(f"  Est. tokens/sec: {tokens_per_sec:.1f} (total words: {total_token_est})")
    print(f"  Peak RSS: {peak_rss_mb:.1f} MB")
    print(f"  Total triples/clusters: {num_triples}")

    # Build all contiguous clusters
    all_clusters = []
    for c_idx in range(num_triples):
        cluster_id = f"cluster_{c_idx + 1:04d}"
        triple_atoms = raw_atoms[c_idx * 3 : (c_idx + 1) * 3]

        theme = triple_atoms[0]["title"]
        if not theme:
            theme = triple_atoms[0]["content"][:60].strip()

        source_atoms = []
        for ord_idx, a in enumerate(triple_atoms):
            node_id = f"atom_{c_idx + 1:04d}_{ord_idx + 1:02d}"
            atom_version_id = f"av_{c_idx + 1:04d}_{ord_idx + 1:02d}"
            source_atoms.append({
                "node_id": node_id,
                "atom_version_id": atom_version_id,
                "workspace_id": "cap_mod01_cloud_10k",
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

        all_clusters.append({
            "cluster_id": cluster_id,
            "theme": theme,
            "atom_count": len(source_atoms),
            "source_atoms": source_atoms,
        })

    # Sample the 2,000 consolidation window via deterministic stride over shard order (seed 42)
    sampled_clusters, sampled_indices, stride_meta = sample_strided_clusters(
        all_clusters, k=sample_window, seed=seed
    )

    # Re-index sampled clusters with window ordinal while retaining original cluster_id
    window_clusters = []
    for w_idx, c in enumerate(sampled_clusters):
        c_copy = dict(c)
        c_copy["window_index"] = w_idx
        c_copy["shard_cluster_index"] = sampled_indices[w_idx]
        window_clusters.append(c_copy)

    # Manifest for the 2,000 consolidation window
    manifest_window: dict[str, Any] = {
        "manifest_name": "clusters_10k_v1",
        "version": "1.0.0",
        "target_node": "CAP-MOD01-CLOUD-10K",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "seed": seed,
        "sample_window_size": len(window_clusters),
        "total_clusters": len(window_clusters),
        "total_atoms": sum(len(c["source_atoms"]) for c in window_clusters),
        "total_shard_docs": len(docs),
        "total_shard_clusters": len(all_clusters),
        "raw_atom_count": total_atom_count,
        "stride_meta": stride_meta,
        "shard_slices": shard_slices,
        "clusters": window_clusters,
    }

    clusters_canonical = json.dumps(manifest_window["clusters"], sort_keys=True, indent=2)
    manifest_window["manifest_sha256"] = hashlib.sha256(clusters_canonical.encode("utf-8")).hexdigest()

    # Full shard manifest
    manifest_full: dict[str, Any] = {
        "manifest_name": "clusters_10k_full",
        "version": "1.0.0",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "seed": seed,
        "total_clusters": len(all_clusters),
        "total_atoms": sum(len(c["source_atoms"]) for c in all_clusters),
        "total_shard_docs": len(docs),
        "raw_atom_count": total_atom_count,
        "shard_slices": shard_slices,
        "clusters": all_clusters,
    }
    full_canonical = json.dumps(manifest_full["clusters"], sort_keys=True, indent=2)
    manifest_full["manifest_sha256"] = hashlib.sha256(full_canonical.encode("utf-8")).hexdigest()

    # Write manifests
    sampled_out = out_dir / "clusters_10k_v1.json"
    full_out = out_dir / "clusters_10k_full.json"

    with open(sampled_out, "w", encoding="utf-8") as f:
        json.dump(manifest_window, f, indent=2)

    with open(full_out, "w", encoding="utf-8") as f:
        json.dump(manifest_full, f, indent=2)

    # Core Phase Ingestion Dossier
    storage_source_bytes = total_source_chars
    storage_atom_bytes = sum(len(a["content"]) for a in raw_atoms)
    storage_spine_mb = (storage_source_bytes + storage_atom_bytes) / (1024.0 * 1024.0)

    dossier = {
        "program": "TRACE-CAP-001",
        "phase": "Core Ingestion & Atomization (Local)",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_docs": len(docs),
        "total_atoms": total_atom_count,
        "total_clusters_full": len(all_clusters),
        "sampled_window_clusters": len(window_clusters),
        "metrics": {
            "load_duration_sec": round(load_duration, 4),
            "atomize_duration_sec": round(atomize_duration, 4),
            "total_ingest_duration_sec": round(total_ingest_duration, 4),
            "docs_per_sec": round(docs_per_sec, 2),
            "target_docs_per_sec": 800.0,
            "clears_ingest_floor": bool(docs_per_sec >= 800.0),
            "atoms_per_sec": round(atoms_per_sec, 2),
            "tokens_per_sec": round(tokens_per_sec, 2),
            "peak_rss_mb": round(peak_rss_mb, 2),
            "storage_split": {
                "source_text_bytes": storage_source_bytes,
                "atom_text_bytes": storage_atom_bytes,
                "spine_wal_approx_mb": round(storage_spine_mb, 4),
                "clusters_10k_v1_json_bytes": sampled_out.stat().st_size,
                "clusters_10k_full_json_bytes": full_out.stat().st_size,
            },
        },
        "shard_slices": [
            {"dataset": ds, "count": cnt} for ds, cnt in shard_slices
        ],
        "manifest_10k_v1_sha256": manifest_window["manifest_sha256"],
        "manifest_10k_full_sha256": manifest_full["manifest_sha256"],
        "verdict": "PASS" if docs_per_sec >= 800.0 else "FAIL",
    }

    dossier_out = out_dir / "core_ingest_dossier.json"
    with open(dossier_out, "w", encoding="utf-8") as f:
        json.dump(dossier, f, indent=2)

    print(f"\n[SUCCESS] Manifests and dossier generated in {out_dir}:")
    print(f"  Sampled Window (2,000 clusters): {sampled_out} (SHA256: {manifest_window['manifest_sha256']})")
    print(f"  Full Shard ({len(all_clusters)} clusters): {full_out} (SHA256: {manifest_full['manifest_sha256']})")
    print(f"  Core Dossier: {dossier_out}")

    return manifest_window, dossier


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble 10K Shard Clusters and Consolidation Window")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory for manifests")
    parser.add_argument("--window", type=int, default=SAMPLE_WINDOW_SIZE, help="Consolidation window size (default 2000)")
    parser.add_argument("--seed", type=int, default=SEED, help="Deterministic sampling seed (default 42)")
    args = parser.parse_args()

    try:
        assemble_10k_clusters(out_dir=args.out_dir, sample_window=args.window, seed=args.seed)
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to assemble 10K clusters: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
