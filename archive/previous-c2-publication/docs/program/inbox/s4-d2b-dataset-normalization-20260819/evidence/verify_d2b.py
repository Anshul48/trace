"""Read-only owner-side verifier for the S4 D2b candidate.

The verifier does not repair or activate anything.  It writes one receipt to
the leased verifier scratch directory when explicitly given --receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


DATASETS = ("beir-scifact", "beir-nfcorpus", "beir-fiqa", "bright", "multihop-rag", "musique", "bigann")
B1_SRC = Path(r"C:\Users\anshu\AppData\Local\trace-worktrees\trace-bench-b11-20260819\src")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                yield line_number, json.loads(line)


def validate_b1(path: Path) -> None:
    sys.path.insert(0, str(B1_SRC))
    try:
        from trace_bench.datasets.loader import load_manifest

        load_manifest(path)
    finally:
        sys.path.remove(str(B1_SRC))


def verify_raw(raw_root: Path, portfolio_path: Path) -> dict[str, Any]:
    portfolio = load_json(portfolio_path)["datasets"]
    failures = []
    file_count = 0
    total_bytes = 0
    metadata_checks = ("source_record_sha256", "checksums_sha256", "layout_observation_sha256", "license_sha256", "acquisition_log_sha256")
    for dataset in DATASETS:
        d = raw_root / dataset
        checks = load_json(d / "checksums.json")
        for relative, expected in checks["files"].items():
            p = d / Path(relative.replace("/", "\\"))
            file_count += 1
            total_bytes += p.stat().st_size if p.exists() else 0
            if not p.exists():
                failures.append(f"raw missing: {dataset}/{relative}")
                continue
            actual = {"size_bytes": p.stat().st_size, "sha256": sha256_file(p)}
            if actual != {"size_bytes": expected.get("size_bytes"), "sha256": expected.get("sha256") }:
                failures.append(f"raw checksum: {dataset}/{relative}")
        metadata_files = {
            "source_record_sha256": d / "source-record.json",
            "checksums_sha256": d / "checksums.json",
            "layout_observation_sha256": d / "layout-observation.json",
            "license_sha256": d / "LICENSE-or-rights-notice.txt",
            "acquisition_log_sha256": d / "acquisition-log.md",
        }
        for key in metadata_checks:
            if sha256_file(metadata_files[key]) != portfolio[dataset][key]:
                failures.append(f"raw metadata manifest: {dataset}/{key}")
    return {"status": "pass" if not failures else "fail", "file_count": file_count, "total_bytes": total_bytes, "failures": failures}


def verify_dataset(dataset: str, root: Path) -> dict[str, Any]:
    d = root / dataset
    failures: list[str] = []
    manifest_path = d / "manifest.json"
    try:
        validate_b1(manifest_path)
    except Exception as exc:  # noqa: BLE001 - receipt must retain exact failure
        failures.append(f"B1 manifest validation: {exc}")
    corpus_ids: set[str] = set()
    corpus_by_id: dict[str, dict[str, Any]] = {}
    for line, record in jsonl(d / "corpus.jsonl"):
        internal = record.get("internal_id")
        if not internal or internal in corpus_ids:
            failures.append(f"duplicate/missing corpus internal_id at line {line}")
        corpus_ids.add(internal)
        corpus_by_id[internal] = record
    source_doc_ids: set[str] = set()
    source_documents_path = d / "source-documents.jsonl"
    if source_documents_path.exists():
        for line, record in jsonl(source_documents_path):
            internal = record.get("internal_id")
            if not internal or internal in source_doc_ids:
                failures.append(f"duplicate/missing source-document internal_id at line {line}")
            source_doc_ids.add(internal)
    else:
        # Operations-only lanes do not expose source-document identities.
        source_doc_ids = set(corpus_ids)
    segment_ids: set[str] = set(corpus_ids)
    for line, record in jsonl(d / "segments.jsonl"):
        internal = record.get("segment_internal_id")
        if internal in segment_ids:
            # Repeated segment rows are a failed dedupe invariant.
            failures.append(f"duplicate segment internal_id at line {line}: {internal}")
        segment_ids.add(internal)
    query_ids: set[str] = set()
    query_native: defaultdict[str, list[str]] = defaultdict(list)
    for line, record in jsonl(d / "queries.jsonl"):
        internal = record.get("internal_id")
        if not internal or internal in query_ids:
            failures.append(f"duplicate/missing query internal_id at line {line}")
        query_ids.add(internal)
        query_native[str(record.get("native_query_id"))].append(record.get("split", ""))
    split_by_native: defaultdict[str, set[str]] = defaultdict(set)
    for line, record in jsonl(d / "split-query-class.jsonl"):
        native = str(record.get("native_query_id"))
        split_by_native[native].add(str(record.get("split")))
    split_leakage = {native: sorted(splits) for native, splits in split_by_native.items() if len(splits) > 1}
    if split_leakage and dataset not in {"bright", "multihop-rag"}:
        failures.append(f"split leakage: {len(split_leakage)} native query IDs")
    map_keys: defaultdict[tuple[str, str], int] = defaultdict(int)
    native_map_rows = 0
    for line, record in jsonl(d / "native-id-maps.jsonl"):
        native_map_rows += 1
        key = (str(record.get("entity_type")), str(record.get("source_key")))
        map_keys[key] += 1
    duplicate_native_map_keys = {str(key): count for key, count in map_keys.items() if count > 1}
    if duplicate_native_map_keys:
        failures.append(f"duplicate native map keys: {len(duplicate_native_map_keys)}")
    judgment_count = 0
    judgment_query_ids: set[str] = set()
    for line, record in jsonl(d / "judgment-evidence-maps.jsonl"):
        judgment_count += 1
        query_internal = record.get("query_internal_id")
        judgment_query_ids.add(query_internal)
        if query_internal not in query_ids:
            failures.append(f"judgment line {line} references missing query {query_internal}")
        doc_internal = record.get("source_document_internal_id")
        if doc_internal is not None and doc_internal not in source_doc_ids:
            failures.append(f"judgment line {line} references missing source document {doc_internal}")
        segment_internal = record.get("segment_internal_id")
        if segment_internal is not None and segment_internal not in segment_ids:
            failures.append(f"judgment line {line} references missing segment {segment_internal}")
    cases = load_json(d / "manifest.json").get("cases", [])
    case_ids = {case.get("id") for case in cases}
    if not case_ids.issubset(query_ids):
        failures.append("manifest case references missing query")
    atom_cases = [case.get("id") for case in cases if case.get("gold_atom_ids")]
    if atom_cases:
        failures.append(f"atom IDs were emitted in {len(atom_cases)} cases")
    samples = load_json(d / "round-trip-samples.json").get("samples", [])
    sample_failures = []
    for sample in samples:
        internal = sample.get("source_document_internal_id") or sample.get("segment_internal_id")
        record = corpus_by_id.get(internal)
        if record is not None and record.get("content_hash") != sample.get("content_hash"):
            sample_failures.append(internal)
    if sample_failures:
        failures.append(f"round-trip content mismatch: {sample_failures[:3]}")
    report = {
        "dataset": dataset,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "counts": {
            "corpus_records": len(corpus_ids),
            "source_document_records": len(source_doc_ids),
            "query_records": len(query_ids),
            "judgment_records": judgment_count,
            "manifest_cases": len(cases),
            "native_map_rows": native_map_rows,
            "round_trip_samples": len(samples),
        },
        "split_leakage": split_leakage,
        "duplicate_native_map_keys": duplicate_native_map_keys,
        "atom_case_count": len(atom_cases),
    }
    return report


def verify_output(output_root: Path) -> dict[str, Any]:
    failures: list[str] = []
    checks = load_json(output_root / "checksums.json")
    checksum_count = 0
    for relative, expected in checks.get("files", {}).items():
        checksum_count += 1
        path = output_root / Path(relative.replace("/", "\\"))
        if not path.exists() or path.stat().st_size != expected.get("size_bytes") or sha256_file(path) != expected.get("sha256"):
            failures.append(f"output checksum mismatch: {relative}")
    datasets = [verify_dataset(dataset, output_root) for dataset in DATASETS]
    failures.extend(f"{item['dataset']}: {failure}" for item in datasets for failure in item["failures"])
    return {"status": "pass" if not failures else "fail", "failures": failures, "checksum_file_count": checksum_count, "datasets": datasets}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--portfolio", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    raw = verify_raw(args.raw_root, args.portfolio)
    output = verify_output(args.output_root)
    receipt = {
        "contract_version": "1.0",
        "verifier_id": "d2b-manifest-verifier-20260819",
        "packet_id": "s4-d2b-dataset-normalization-20260819",
        "authority_level": "C1",
        "status": "pass" if raw["status"] == "pass" and output["status"] == "pass" else "fail",
        "raw": raw,
        "output": output,
        "claim_boundary": "Owner-side fixed integrity and mapping review; not independent certification or retrieval-quality evidence.",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(args.receipt), "raw_failures": len(raw["failures"]), "output_failures": len(output["failures"])}, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
