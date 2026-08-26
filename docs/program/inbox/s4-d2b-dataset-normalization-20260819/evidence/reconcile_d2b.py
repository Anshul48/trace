"""Independent, read-only reconciliation for the S4 D2b candidate.

This checker deliberately does not import or call the packet's owner verifier.
It rehashes the D2a checksum-listed raw inputs and both normalized output trees,
then checks the reversible mapping and explicit exclusion boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


DATASETS = (
    "beir-scifact",
    "beir-nfcorpus",
    "beir-fiqa",
    "bright",
    "multihop-rag",
    "musique",
    "bigann",
)
EXPECTED_STATUS = {
    "beir-scifact": "evaluation_ready_document_level",
    "beir-nfcorpus": "evaluation_ready_document_level",
    "beir-fiqa": "evaluation_ready_document_level",
    "bright": "evaluation_ready_document_level_with_source_split_limitation",
    "multihop-rag": "evaluation_ready_document_or_span_level_with_derived_source_keys",
    "musique": "evaluation_ready_source_segment_level_atom_mapping_deferred",
    "bigann": "operations_only",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except Exception as exc:  # noqa: BLE001 - retained in the receipt
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: record is not an object")
            result.append(value)
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(dataset: str, entity_type: str, source_key: str) -> str:
    normalized = source_key.replace("\r\n", "\n").replace("\r", "\n")
    key = f"{dataset}|{entity_type}|{normalized}".encode("utf-8")
    return f"d2b:{dataset}:{entity_type}:{hashlib.sha256(key).hexdigest()}"


class Reconciliation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.raw_files = 0
        self.raw_bytes = 0
        self.status_counts: Counter[str] = Counter()
        self.counts: dict[str, dict[str, int]] = {}
        self.split_leakage: dict[str, dict[str, list[str]]] = {}

    def check(self, condition: bool, message: str) -> None:
        if not condition:
            self.errors.append(message)

    def verify_raw(self, raw_root: Path, portfolio_path: Path) -> None:
        portfolio = load_json(portfolio_path)
        entries = portfolio.get("datasets", {})
        for dataset in DATASETS:
            raw_dataset = raw_root / dataset
            checksums = load_json(raw_dataset / "checksums.json")
            self.check(checksums.get("algorithm") == "SHA-256", f"{dataset}: raw algorithm")
            declared = entries.get(dataset, {})
            metadata_names = {
                "source_record_sha256": "source-record.json",
                "checksums_sha256": "checksums.json",
                "layout_observation_sha256": "layout-observation.json",
                "license_sha256": "LICENSE-or-rights-notice.txt",
                "acquisition_log_sha256": "acquisition-log.md",
            }
            for field, relative in metadata_names.items():
                expected = declared.get(field)
                if expected:
                    self.check(
                        sha256_file(raw_dataset / relative) == expected,
                        f"{dataset}: portfolio metadata hash {relative}",
                    )
            for relative, metadata in checksums.get("files", {}).items():
                path = raw_dataset / relative
                self.raw_files += 1
                if not path.is_file():
                    self.errors.append(f"{dataset}: raw missing {relative}")
                    continue
                self.raw_bytes += path.stat().st_size
                self.check(path.stat().st_size == metadata.get("size_bytes"), f"{dataset}: raw size {relative}")
                self.check(sha256_file(path) == metadata.get("sha256"), f"{dataset}: raw sha256 {relative}")

    def verify_tree(self, root: Path) -> dict[str, Any]:
        self.check(root.is_dir(), f"missing output tree {root}")
        checksums = load_json(root / "checksums.json")
        entries = checksums.get("files", {})
        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.name != "checksums.json"
        }
        self.check(set(entries) == actual, f"{root.name}: output inventory {len(entries)} vs {len(actual)}")
        failures = 0
        for relative, metadata in entries.items():
            path = root / relative
            if not path.is_file() or path.stat().st_size != metadata.get("size_bytes") or sha256_file(path) != metadata.get("sha256"):
                failures += 1
        self.check(failures == 0, f"{root.name}: output hash failures {failures}")
        return checksums

    def verify_roots(
        self,
        candidate: Path,
        replay: Path,
        candidate_checksums: dict[str, Any],
        replay_checksums: dict[str, Any],
    ) -> None:
        self.check(candidate_checksums == replay_checksums, "candidate/replay checksum maps differ")
        self.check(len(candidate_checksums.get("files", {})) == 134, "candidate checksum entry count is not 134")
        for root in (candidate, replay):
            run = load_json(root / "run-manifest.json")
            completed = load_json(root / "COMPLETED.json")
            self.check(run.get("status") == "completed_candidate", f"{root.name}: run status")
            self.check(run.get("input_manifest_id") == "s4-d2b-inputs-20260820-030001z", f"{root.name}: input manifest")
            for field in ("raw_mutated", "network_used", "provider_used", "atom_ids_created"):
                self.check(run.get(field) is False, f"{root.name}: {field}")
            self.check(completed.get("status") == "completed_candidate", f"{root.name}: completion marker")
            self.check(
                {path.name for path in root.iterdir() if path.is_dir()} == set(DATASETS),
                f"{root.name}: dataset roots",
            )

    def verify_dataset_structures(self, candidate: Path, raw_root: Path) -> None:
        raw_checksums = {dataset: load_json(raw_root / dataset / "checksums.json").get("files", {}) for dataset in DATASETS}
        for dataset in DATASETS:
            root = candidate / dataset
            manifest = load_json(root / "manifest.json")
            status = manifest.get("status")
            self.status_counts[status] += 1
            self.check(status == EXPECTED_STATUS[dataset], f"{dataset}: status {status}")
            self.check(manifest.get("input_manifest_id") == "s4-d2b-inputs-20260820-030001z", f"{dataset}: manifest input")
            admission = manifest.get("admission", {})
            self.check(admission.get("admission_decision") == "DEC-P-001", f"{dataset}: admission decision")
            self.check(admission.get("is_admitted") is True, f"{dataset}: admission flag")
            self.check(bool(admission.get("license")) and bool(admission.get("source_url")) and bool(admission.get("version")), f"{dataset}: rights provenance")
            config = load_json(root / "normalization-config.json")
            self.check(config.get("input_manifest_id") == "s4-d2b-inputs-20260820-030001z", f"{dataset}: config input")
            if dataset == "bigann":
                self.check(manifest.get("cases") == [], "bigann: text cases present")
                self.check((root / "judgment-evidence-maps.jsonl").stat().st_size == 0, "bigann: judgment maps present")
                vector_files = load_json(root / "vector-operations-manifest.json").get("files", [])
                self.check(len(vector_files) == 4, "bigann: vector file count")
                for record in vector_files:
                    relative = record.get("path", "")
                    raw_record = raw_checksums[dataset].get(relative)
                    self.check(record.get("status") == "pass", "bigann: vector status")
                    self.check(record.get("mapping_rule") == "native vector row index remains operations-only; no text atom mapping", "bigann: vector mapping rule")
                    self.check(raw_record is not None, f"bigann: vector raw reference {relative}")
                    if raw_record is not None:
                        self.check(record.get("sha256") == raw_record.get("sha256") and record.get("size_bytes") == raw_record.get("size_bytes"), f"bigann: vector hash {relative}")
                self.counts[dataset] = {
                    "queries": 0,
                    "judgments": 0,
                    "documents": 0,
                    "segments": 0,
                    "corpus_segment_records": 0,
                    "cases": 0,
                    "exclusions": len(load_jsonl(root / "exclusions.jsonl")),
                    "native_maps": len(load_jsonl(root / "native-id-maps.jsonl")),
                }
                continue

            queries = load_jsonl(root / "queries.jsonl")
            judgments = load_jsonl(root / "judgment-evidence-maps.jsonl")
            documents = load_jsonl(root / "source-documents.jsonl")
            native_maps = load_jsonl(root / "native-id-maps.jsonl")
            segments = load_jsonl(root / "segments.jsonl")
            corpus = load_jsonl(root / "corpus.jsonl")
            split_records = load_jsonl(root / "split-query-class.jsonl")
            exclusions = load_jsonl(root / "exclusions.jsonl")
            query_by_id = {record.get("internal_id"): record for record in queries}
            document_by_id = {record.get("internal_id"): record for record in documents}
            corpus_by_id = {record.get("internal_id"): record for record in corpus}
            segment_by_id = {record.get("segment_internal_id"): record for record in segments if record.get("segment_internal_id")}
            segment_by_id.update({record.get("internal_id"): record for record in corpus if record.get("entity_type") == "segment" or record.get("segment_internal_id") is not None})
            self.check(len(query_by_id) == len(queries), f"{dataset}: duplicate query internal IDs")
            self.check(len(document_by_id) == len(documents), f"{dataset}: duplicate source-document internal IDs")
            map_keys = [(record.get("entity_type"), record.get("source_key")) for record in native_maps]
            self.check(len(set(map_keys)) == len(map_keys), f"{dataset}: duplicate native-map keys")
            self.check(len({record.get("internal_id") for record in native_maps}) == len(native_maps), f"{dataset}: duplicate native-map internal IDs")
            for query in queries:
                self.check(query.get("dataset") == dataset and query.get("internal_id", "").startswith(f"d2b:{dataset}:query:"), f"{dataset}: query identity")
                self.check(query.get("internal_id") == stable_id(dataset, "query", query.get("source_key", "")), f"{dataset}: query stable ID")
                self.check(query.get("native_query_id") is not None, f"{dataset}: query native ID")
            for document in documents:
                self.check(document.get("dataset") == dataset and document.get("internal_id", "").startswith(f"d2b:{dataset}:document:"), f"{dataset}: document identity")
                self.check(bool(re.fullmatch(r"[0-9a-f]{64}", str(document.get("content_hash", "")))), f"{dataset}: document content hash")
            for mapping in native_maps:
                self.check(mapping.get("dataset") == dataset and mapping.get("internal_id") == stable_id(dataset, mapping.get("entity_type"), mapping.get("source_key")), f"{dataset}: native-map stable ID")
                if mapping.get("entity_type") == "document":
                    self.check(mapping.get("internal_id") in document_by_id, f"{dataset}: native-map document reference")
                if mapping.get("entity_type") == "query":
                    self.check(mapping.get("internal_id") in query_by_id, f"{dataset}: native-map query reference")
                if mapping.get("entity_type") == "segment":
                    self.check(mapping.get("internal_id") in segment_by_id, f"{dataset}: native-map segment reference")
            for segment in segments:
                self.check(segment.get("segment_internal_id") in segment_by_id and segment.get("source_document_internal_id") in document_by_id, f"{dataset}: segment reference")
                self.check(isinstance(segment.get("char_offset_start"), int) and isinstance(segment.get("char_offset_end"), int) and 0 <= segment["char_offset_start"] <= segment["char_offset_end"], f"{dataset}: segment offset")
                self.check(bool(re.fullmatch(r"[0-9a-f]{64}", str(segment.get("content_hash", "")))), f"{dataset}: segment content hash")
            exclusion_keys = {
                (record.get("detail", {}).get("query_id"), record.get("detail", {}).get("doc_id"))
                for record in exclusions
                if record.get("reason") == "judgment_references_missing_document"
            }
            for judgment in judgments:
                query_id = judgment.get("query_internal_id")
                document_id = judgment.get("source_document_internal_id")
                segment_id = judgment.get("segment_internal_id")
                self.check(query_id in query_by_id, f"{dataset}: judgment query reference")
                if query_id in query_by_id:
                    self.check(judgment.get("query_native_id") == query_by_id[query_id].get("native_query_id"), f"{dataset}: judgment query native ID")
                if document_id is None:
                    key = (judgment.get("query_native_id"), judgment.get("source_document_native_id"))
                    self.check(judgment.get("evidence_level") == "unresolved" and judgment.get("round_trip_status") == "blocked_missing_source_document" and key in exclusion_keys, f"{dataset}: unresolved judgment accounting")
                else:
                    self.check(document_id in document_by_id, f"{dataset}: judgment document reference")
                    if document_id in document_by_id and judgment.get("source_document_native_id") is not None:
                        self.check(judgment.get("source_document_native_id") == document_by_id[document_id].get("native_id"), f"{dataset}: judgment document native ID")
                    self.check(judgment.get("round_trip_status") == "pass", f"{dataset}: judgment round trip")
                if segment_id is not None:
                    self.check(segment_id in segment_by_id, f"{dataset}: judgment segment reference")
                    if segment_id in segment_by_id:
                        self.check(segment_by_id[segment_id].get("source_document_internal_id") == document_id, f"{dataset}: judgment segment/document link")
                if "char_offset_start" in judgment or "char_offset_end" in judgment:
                    self.check(isinstance(judgment.get("char_offset_start"), int) and isinstance(judgment.get("char_offset_end"), int) and judgment["char_offset_start"] <= judgment["char_offset_end"], f"{dataset}: judgment offset")
            native_splits: dict[str, set[str]] = {}
            for split in split_records:
                query_id = split.get("query_internal_id")
                self.check(query_id in query_by_id, f"{dataset}: split query reference")
                native_splits.setdefault(str(split.get("native_query_id")), set()).add(str(split.get("split")))
            leakage = {native: sorted(splits) for native, splits in native_splits.items() if len(splits) > 1}
            self.split_leakage[dataset] = leakage
            self.check(not leakage or dataset in {"bright", "multihop-rag"}, f"{dataset}: split leakage {len(leakage)}")
            for case in manifest.get("cases", []):
                self.check(case.get("id") in query_by_id and case.get("gold_atom_ids") == [], f"{dataset}: case chain or atom ID")
            for exclusion in exclusions:
                self.check(bool(exclusion.get("reason")) and bool(exclusion.get("record_type")), f"{dataset}: exclusion accounting")
            self.counts[dataset] = {
                "queries": len(queries),
                "judgments": len(judgments),
                "documents": len(documents),
                "segments": len(segments),
                "corpus_segment_records": sum(1 for record in corpus if record.get("entity_type") == "segment" or record.get("segment_internal_id") is not None),
                "cases": len(manifest.get("cases", [])),
                "exclusions": len(exclusions),
                "native_maps": len(native_maps),
            }

    def result(self, candidate_checksums: int, replay_checksums: int) -> dict[str, Any]:
        return {
            "status": "pass" if not self.errors else "fail",
            "error_count": len(self.errors),
            "errors": self.errors[:100],
            "raw_files_rehashed": self.raw_files,
            "raw_bytes_rehashed": self.raw_bytes,
            "candidate_checksum_entries": candidate_checksums,
            "replay_checksum_entries": replay_checksums,
            "status_counts": dict(self.status_counts),
            "split_leakage_exceptions": {key: value for key, value in self.split_leakage.items() if value},
            "counts": self.counts,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--portfolio", type=Path, required=True)
    args = parser.parse_args()
    reconciliation = Reconciliation()
    reconciliation.verify_raw(args.raw_root, args.portfolio)
    candidate_checksums = reconciliation.verify_tree(args.candidate)
    replay_checksums = reconciliation.verify_tree(args.replay)
    reconciliation.check(candidate_checksums == replay_checksums, "candidate/replay checksum maps differ")
    reconciliation.check(len(candidate_checksums.get("files", {})) == 134, "candidate checksum entry count is not 134")
    reconciliation.verify_roots(args.candidate, args.replay, candidate_checksums, replay_checksums)
    reconciliation.verify_dataset_structures(args.candidate, args.raw_root)
    result = reconciliation.result(len(candidate_checksums.get("files", {})), len(replay_checksums.get("files", {})))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
