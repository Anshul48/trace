#!/usr/bin/env python3
"""Standalone verification script for frozen benchmark datasets and manifests (WP-CAP-EVAL02).

Usage:
    python benchmarks/verify_dataset_checksums.py [--manifest PATH]

Validates:
1. Manifest integrity and schema compliance.
2. File existence, byte length, and line count for every staged file.
3. Cryptographic SHA-256 checksum verification against frozen manifest digests.
4. Exact split query counts (SciFact 300, NFCorpus 323, FiQA 648, MuSiQue 500).
5. Canonical BEIR archive MD5 references and MuSiQue stratification metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def compute_sha256_and_bytes(file_path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def count_lines(file_path: Path) -> int:
    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count


def verify_manifest(manifest_path: Path, root_dir: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []

    if not manifest_path.exists():
        return False, [f"Manifest file does not exist: {manifest_path}"]

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        return False, [f"Failed to parse manifest JSON: {e}"]

    # 1. Header checks
    if manifest.get("manifest_id") != "beir_musique_frozen_v1":
        errors.append(f"Invalid manifest_id: {manifest.get('manifest_id')}")

    auth = manifest.get("authority", {})
    if auth.get("charter") != "TRACE-CAP-001":
        errors.append(f"Invalid charter authority: {auth.get('charter')}")
    if auth.get("directives") != "CAP_001_WAVEB_DIRECTIVES.md":
        errors.append(f"Invalid directives authority: {auth.get('directives')}")

    datasets = manifest.get("datasets", {})
    files = manifest.get("files", {})

    expected_datasets = {"scifact", "nfcorpus", "fiqa", "musique"}
    if set(datasets.keys()) != expected_datasets:
        errors.append(f"Expected datasets {expected_datasets}, got {set(datasets.keys())}")

    # 2. Per-dataset query count assertions (Directive D1 / Annex §1.1)
    expected_counts = {
        "scifact": 300,
        "nfcorpus": 323,
        "fiqa": 648,
        "musique": 500,
    }
    for name, expected_count in expected_counts.items():
        ds_info = datasets.get(name, {})
        actual_count = ds_info.get("queries_count")
        if actual_count != expected_count:
            errors.append(f"Dataset {name} query count mismatch: expected {expected_count}, got {actual_count}")

    # 3. Canonical archive MD5 assertions
    expected_md5s = {
        "scifact": "5f7d1de60b170fc8027bb7898e2efca1",
        "nfcorpus": "a89dba18a62ef92f7d323ec890a0d38d",
        "fiqa": "17918ed23cd04fb15047f73e6c3bd9d9",
    }
    for name, expected_md5 in expected_md5s.items():
        ds_info = datasets.get(name, {})
        actual_md5 = ds_info.get("canonical_archive_md5")
        if actual_md5 != expected_md5:
            errors.append(f"Dataset {name} canonical MD5 mismatch: expected {expected_md5}, got {actual_md5}")

    # 4. MuSiQue stratification check
    musique_info = datasets.get("musique", {})
    sampling = musique_info.get("sampling_strategy", {})
    if sampling.get("random_seed") != 42:
        errors.append(f"MuSiQue random seed mismatch: expected 42, got {sampling.get('random_seed')}")
    hop_dist = sampling.get("hop_distribution", {})
    if hop_dist.get("2_hop") != 259 or hop_dist.get("3_hop") != 157 or hop_dist.get("4_hop") != 84:
        errors.append(f"MuSiQue hop distribution mismatch: got {hop_dist}")

    # 5. File integrity checks
    if len(files) < 8:
        errors.append(f"Expected at least 8 pinned files, found {len(files)}")

    for rel_path, meta in files.items():
        abs_path = root_dir / rel_path
        if not abs_path.exists():
            errors.append(f"Missing pinned file: {rel_path} ({abs_path})")
            continue

        calc_sha, calc_size = compute_sha256_and_bytes(abs_path)
        calc_lines = count_lines(abs_path)

        expected_sha = meta.get("sha256")
        expected_size = meta.get("byte_length")
        expected_lines = meta.get("row_count")

        if calc_sha != expected_sha:
            errors.append(f"SHA-256 checksum mismatch on {rel_path}: expected {expected_sha}, computed {calc_sha}")
        if calc_size != expected_size:
            errors.append(f"Byte size mismatch on {rel_path}: expected {expected_size}, observed {calc_size}")
        if calc_lines != expected_lines:
            errors.append(f"Row count mismatch on {rel_path}: expected {expected_lines}, observed {calc_lines}")

    return len(errors) == 0, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify frozen dataset manifests and checksums.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmarks/manifests/beir_musique_frozen_v1.json"),
        help="Path to manifest JSON file",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Root directory of repository worktree",
    )
    args = parser.parse_args()

    root_dir = args.root.resolve()
    manifest_arg = args.manifest
    if manifest_arg.is_absolute():
        manifest_path = manifest_arg.resolve()
    else:
        if manifest_arg.exists():
            manifest_path = manifest_arg.resolve()
        elif (root_dir / manifest_arg).exists():
            manifest_path = (root_dir / manifest_arg).resolve()
        else:
            manifest_path = (root_dir / manifest_arg).resolve()

    print(f"Verifying dataset manifest: {manifest_path}")
    print(f"Repository root: {root_dir}")

    passed, errors = verify_manifest(manifest_path, root_dir)
    if passed:
        print("[PASS] All 4 frozen dataset splits and 8 staged files matched cryptographic checksums 100%.")
        return 0
    else:
        print(f"[FAIL] {len(errors)} verification errors detected:")
        for err in errors:
            print(f"  - {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
