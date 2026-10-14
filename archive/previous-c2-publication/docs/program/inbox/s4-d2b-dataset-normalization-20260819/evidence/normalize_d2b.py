"""S4 D2b deterministic normalizer.

This is a packet-local evidence utility.  It reads the immutable D2a raw root,
verifies every D2a checksum before creating an output root, and writes only the
leased external candidate directory.  It deliberately does not create atom
IDs: no ingest/chunking artifact is present in the pinned inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import pyarrow.parquet as pq


NORMALIZER_VERSION = "s4-d2b-normalizer-1.0.1-musique-roundtrip"
INPUT_MANIFEST_ID = "s4-d2b-inputs-20260820-030001z"
B1_COMMIT = "dcd32396f6430e6865176f053a3ce57112db6df3"
B1_SCHEMA_PATH = Path(
    r"C:\Users\anshu\AppData\Local\trace-worktrees\trace-bench-b11-20260819"
) / "src" / "trace_bench" / "datasets" / "schema.py"
DATASETS = (
    "beir-scifact",
    "beir-nfcorpus",
    "beir-fiqa",
    "bright",
    "multihop-rag",
    "musique",
    "bigann",
)
TEXT_DATASETS = DATASETS[:-1]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def required_text(value: Any) -> str:
    return normalized_text(value)


def stable_id(dataset: str, entity_type: str, source_key: str) -> str:
    key = f"{dataset}|{entity_type}|{source_key}"
    return f"d2b:{dataset}:{entity_type}:{sha256_text(key)}"


def safe_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return value.tolist()
    except AttributeError:
        return [value]


def rel_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


class JsonlWriter:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w", encoding="utf-8", newline="\n")
        self.digest = hashlib.sha256()
        self.count = 0

    def write(self, value: Any) -> None:
        line = canonical_json(value) + "\n"
        self.handle.write(line)
        self.digest.update(line.encode("utf-8"))
        self.count += 1

    def close(self) -> None:
        if not self.handle.closed:
            self.handle.close()

    def result(self) -> dict[str, Any]:
        self.close()
        return {
            "path": self.path.name,
            "records": self.count,
            "bytes": self.path.stat().st_size,
            "sha256": self.digest.hexdigest(),
        }


class CorpusWriter:
    def __init__(self, jsonl_path: Path, text_path: Path, offsets_path: Path):
        self.jsonl = JsonlWriter(jsonl_path)
        self.text_path = text_path
        self.text_handle = text_path.open("w", encoding="utf-8", newline="\n")
        self.offsets = JsonlWriter(offsets_path)
        self.char_position = 0
        self.block_index = 0

    def add(self, record: dict[str, Any], title: str, text: str) -> dict[str, Any]:
        self.jsonl.write(record)
        block = f"{title}\n\n{text}" if title else text
        if self.block_index:
            self.text_handle.write("\n\n")
            self.char_position += 2
        start = self.char_position
        self.text_handle.write(block)
        self.char_position += len(block)
        end = self.char_position
        self.offsets.write(
            {
                "corpus_index": self.block_index,
                "internal_id": record["internal_id"],
                "char_start": start,
                "char_end": end,
                "offset_unit": "unicode_code_points",
            }
        )
        self.block_index += 1
        return {"corpus_index": self.block_index - 1, "char_start": start, "char_end": end}

    def close(self) -> dict[str, Any]:
        if not self.text_handle.closed:
            self.text_handle.close()
        return {
            "corpus_jsonl": self.jsonl.result(),
            "corpus_txt": {
                "path": self.text_path.name,
                "records": self.block_index,
                "bytes": self.text_path.stat().st_size,
                "sha256": sha256_file(self.text_path),
            },
            "corpus_offsets": self.offsets.result(),
        }


class DatasetOutput:
    def __init__(self, dataset: str, output_root: Path, source: dict[str, Any], created_at: str):
        self.dataset = dataset
        self.root = output_root / dataset
        self.root.mkdir(parents=True, exist_ok=True)
        self.source = source
        self.created_at = created_at
        self.corpus = CorpusWriter(
            self.root / "corpus.jsonl",
            self.root / "corpus.txt",
            self.root / "corpus-offsets.jsonl",
        )
        self.native_maps = JsonlWriter(self.root / "native-id-maps.jsonl")
        self.judgment_maps = JsonlWriter(self.root / "judgment-evidence-maps.jsonl")
        self.queries = JsonlWriter(self.root / "queries.jsonl")
        self.split_records = JsonlWriter(self.root / "split-query-class.jsonl")
        self.exclusions = JsonlWriter(self.root / "exclusions.jsonl")
        self.segments = JsonlWriter(self.root / "segments.jsonl")
        self.source_documents = JsonlWriter(self.root / "source-documents.jsonl")
        self.segment_index: set[str] = set()
        self.source_document_index: set[str] = set()
        self.doc_index: dict[str, str] = {}
        self.doc_by_id: dict[str, dict[str, Any]] = {}
        self.query_index: dict[str, str] = {}
        self.query_rows: dict[str, dict[str, Any]] = {}
        self.cases: list[dict[str, Any]] = []
        self.round_trip: list[dict[str, Any]] = []
        self.duplicates: Counter[str] = Counter()
        self.duplicate_examples: list[dict[str, Any]] = []
        self.malformed: Counter[str] = Counter()
        self.malformed_examples: list[dict[str, Any]] = []
        self.ambiguous: Counter[str] = Counter()
        self.ambiguous_examples: list[dict[str, Any]] = []
        self.status_counts: Counter[str] = Counter()
        self.raw_file_hashes: dict[str, dict[str, Any]] = {}

    def malformed_record(self, reason: str, pointer: dict[str, Any], detail: str = "") -> None:
        self.malformed[reason] += 1
        if len(self.malformed_examples) < 100:
            self.malformed_examples.append({"reason": reason, "pointer": pointer, "detail": detail})

    def duplicate_record(self, reason: str, detail: dict[str, Any]) -> None:
        self.duplicates[reason] += 1
        if len(self.duplicate_examples) < 100:
            self.duplicate_examples.append({"reason": reason, **detail})

    def ambiguous_record(self, reason: str, detail: dict[str, Any]) -> None:
        self.ambiguous[reason] += 1
        if len(self.ambiguous_examples) < 100:
            self.ambiguous_examples.append({"reason": reason, **detail})

    def exclude(self, reason: str, record_type: str, pointer: dict[str, Any], detail: dict[str, Any] | None = None) -> None:
        self.exclusions.write(
            {
                "dataset": self.dataset,
                "record_type": record_type,
                "reason": reason,
                "pointer": pointer,
                "detail": detail or {},
            }
        )
        self.status_counts[reason] += 1

    def add_document(
        self,
        *,
        source_key: str,
        native_id: str | None,
        native_id_origin: str,
        title: str,
        text: str,
        pointer: dict[str, Any],
        field_path: str,
        document_internal_id: str | None = None,
        segment_internal_id: str | None = None,
        entity_type: str = "document",
        source_document_key: str | None = None,
        source_document_internal_id: str | None = None,
    ) -> str | None:
        if not text and not title:
            self.malformed_record("empty_document_content", pointer, field_path)
            return None
        if source_key in self.doc_index:
            previous = self.doc_by_id[self.doc_index[source_key]]
            if previous["content_hash"] == sha256_text(title + "\n" + text):
                self.duplicate_record("duplicate_source_document", {"source_key": source_key, "pointer": pointer})
                return previous["internal_id"]
            self.duplicate_record("conflicting_source_document_id", {"source_key": source_key, "pointer": pointer})
            return None
        internal_id = document_internal_id or stable_id(self.dataset, entity_type, source_key)
        content_hash = sha256_text(title + "\n" + text)
        record = {
            "dataset": self.dataset,
            "internal_id": internal_id,
            "entity_type": entity_type,
            "native_id": native_id,
            "native_id_origin": native_id_origin,
            "source_key": source_key,
            "source_document_key": source_document_key or source_key,
            "source_document_internal_id": source_document_internal_id or internal_id,
            "title": title,
            "text": text,
            "content_hash": content_hash,
            "raw_pointer": pointer,
            "raw_field_path": field_path,
            "segment_internal_id": segment_internal_id,
        }
        offsets = self.corpus.add(record, title, text)
        record["normalized_corpus_offsets"] = offsets
        self.doc_index[source_key] = internal_id
        self.doc_by_id[internal_id] = record
        self.add_source_document_identity(
            internal_id=source_document_internal_id or internal_id,
            source_key=source_document_key or source_key,
            title=title,
            native_id=native_id if entity_type == "document" else None,
            native_id_origin=native_id_origin,
            pointer=pointer,
            content_hash=content_hash if entity_type == "document" else sha256_text(title),
        )
        self.native_maps.write(
            {
                "dataset": self.dataset,
                "entity_type": entity_type,
                "native_id": native_id,
                "native_id_origin": native_id_origin,
                "source_key": source_key,
                "internal_id": internal_id,
                "content_hash": content_hash,
                "raw_pointer": pointer,
                "raw_field_path": field_path,
            }
        )
        return internal_id

    def add_segment_map(self, record: dict[str, Any]) -> None:
        segment_id = record["segment_internal_id"]
        if segment_id in self.segment_index:
            self.duplicate_record(
                "duplicate_segment_map_reused_by_multiple_judgments",
                {"segment_internal_id": segment_id, "source_key": record["source_key"]},
            )
            return
        self.segment_index.add(segment_id)
        self.segments.write(record)
        self.native_maps.write(
            {
                "dataset": self.dataset,
                "entity_type": "segment",
                "native_id": record.get("native_segment_id"),
                "native_id_origin": record.get("native_segment_id_origin", "derived"),
                "source_key": record["source_key"],
                "internal_id": record["segment_internal_id"],
                "content_hash": record["content_hash"],
                "raw_pointer": record.get("raw_pointer", {}),
                "raw_field_path": record.get("raw_field_path", ""),
            }
        )

    def add_source_document_identity(
        self,
        *,
        internal_id: str,
        source_key: str,
        title: str,
        native_id: str | None,
        native_id_origin: str,
        pointer: dict[str, Any],
        content_hash: str,
    ) -> None:
        if internal_id in self.source_document_index:
            return
        self.source_document_index.add(internal_id)
        self.source_documents.write(
            {
                "dataset": self.dataset,
                "internal_id": internal_id,
                "entity_type": "document",
                "native_id": native_id,
                "native_id_origin": native_id_origin,
                "source_key": source_key,
                "title": title,
                "text_status": "identity_only_when_source_exposes_paragraphs_without_full_document",
                "content_hash": content_hash,
                "raw_pointer": pointer,
            }
        )

    def add_query(
        self,
        *,
        source_key: str,
        native_id: str | None,
        native_id_origin: str,
        query: str,
        split: str,
        query_class: str,
        category: str,
        pointer: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        evaluation_status: str = "usable",
    ) -> str | None:
        if not query:
            self.malformed_record("empty_query_text", pointer, "query")
            return None
        if source_key in self.query_index:
            self.duplicate_record("duplicate_query_id", {"source_key": source_key, "pointer": pointer})
            return self.query_index[source_key]
        internal_id = stable_id(self.dataset, "query", source_key)
        row = {
            "dataset": self.dataset,
            "internal_id": internal_id,
            "native_query_id": native_id,
            "native_id_origin": native_id_origin,
            "source_key": source_key,
            "query": query,
            "split": split,
            "query_class": query_class,
            "category": category,
            "evaluation_status": evaluation_status,
            "raw_pointer": pointer,
            "metadata": metadata or {},
        }
        self.queries.write(row)
        self.split_records.write(
            {
                "dataset": self.dataset,
                "query_internal_id": internal_id,
                "native_query_id": native_id,
                "split": split,
                "query_class": query_class,
                "category": category,
                "evaluation_status": evaluation_status,
            }
        )
        self.native_maps.write(
            {
                "dataset": self.dataset,
                "entity_type": "query",
                "native_id": native_id,
                "native_id_origin": native_id_origin,
                "source_key": source_key,
                "internal_id": internal_id,
                "content_hash": sha256_text(query),
                "raw_pointer": pointer,
                "raw_field_path": "query/text",
            }
        )
        self.query_index[source_key] = internal_id
        self.query_rows[source_key] = row
        return internal_id

    def add_case(
        self,
        *,
        query_internal_id: str,
        native_query_id: str | None,
        category: str,
        query: str,
        native_gold_doc_ids: list[str],
        expected_abstention: bool,
        difficulty: str,
        metadata: dict[str, Any],
    ) -> None:
        self.cases.append(
            {
                "id": query_internal_id,
                "native_query_id": native_query_id,
                "category": category,
                "query": query,
                "gold_atom_ids": [],
                "native_gold_doc_ids": native_gold_doc_ids,
                "acceptable_alternative_ids": [],
                "expected_abstention": expected_abstention,
                "difficulty": difficulty,
                "metadata": metadata,
            }
        )

    def add_round_trip(self, chain: dict[str, Any]) -> None:
        if len(self.round_trip) < 5:
            self.round_trip.append(chain)

    def close_streams(self) -> dict[str, Any]:
        return {
            "corpus": self.corpus.close(),
            "native_id_maps": self.native_maps.result(),
            "judgment_evidence_maps": self.judgment_maps.result(),
            "queries": self.queries.result(),
            "split_query_class": self.split_records.result(),
            "exclusions": self.exclusions.result(),
            "segments": self.segments.result(),
            "source_documents": self.source_documents.result(),
        }

    def finalize(self, *, query_count: int, judgment_count: int, evaluation_status: str, extra_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        stream_results = self.close_streams()
        config = {
            "normalizer_version": NORMALIZER_VERSION,
            "created_at_utc": self.created_at,
            "input_manifest_id": INPUT_MANIFEST_ID,
            "b1_schema_contract": {
                "commit": B1_COMMIT,
                "schema_path": str(B1_SCHEMA_PATH),
                "schema_role": "BenchmarkManifest-compatible outer shape",
            },
            "text_normalization": {
                "unicode": "NFC",
                "line_endings": "CRLF/CR to LF",
                "whitespace": "otherwise preserved",
                "serialization": "UTF-8 JSON with sorted keys and compact separators",
            },
            "id_rules": {
                "namespace": "d2b:<dataset>:<entity_type>:sha256(dataset|entity_type|source_key)",
                "native_ids": "retained verbatim where supplied; derived source keys explicitly labelled",
                "atom_ids": "not created; deferred until named ingest/chunking artifact",
            },
            "evidence_rules": {
                "document_level": "retained when source provides only document judgment",
                "segment_level": "retained only for source paragraph/field evidence",
                "span_offsets": "recorded only when an evidence field is found verbatim in normalized source text",
                "unresolved": "excluded or blocked with explicit reason; never fabricated",
            },
        }
        write_json(self.root / "normalization-config.json", config)
        write_json(
            self.root / "duplicate-report.json",
            {"counts": dict(self.duplicates), "examples": self.duplicate_examples},
        )
        write_json(
            self.root / "malformed-record-report.json",
            {"counts": dict(self.malformed), "examples": self.malformed_examples},
        )
        write_json(
            self.root / "ambiguous-evidence-report.json",
            {"counts": dict(self.ambiguous), "examples": self.ambiguous_examples},
        )
        write_json(self.root / "round-trip-samples.json", {"samples": self.round_trip})
        manifest = {
            "contract_version": "1.0",
            "artifact_id": f"d2b:{self.dataset}:manifest:{INPUT_MANIFEST_ID}",
            "created_at": self.created_at,
            "producer": {
                "component": "S4 Data Steward",
                "task": "s4-d2b-dataset-normalization-20260819",
                "normalizer_version": NORMALIZER_VERSION,
            },
            "input_manifest_id": INPUT_MANIFEST_ID,
            "correlation_id": f"s4-d2b:{self.dataset}:{INPUT_MANIFEST_ID}",
            "status": evaluation_status,
            "name": self.dataset,
            "version": f"d2b-{self.created_at[:10].replace('-', '')}.1",
            "description": "Versioned real-data normalization with reversible source mappings; atom mapping is deferred.",
            "corpus_sha256": stream_results["corpus"]["corpus_txt"]["sha256"],
            "corpus_file": "corpus.txt",
            "release_authority": False,
            "mode": "certification",
            "admission": {
                "dataset_name": self.dataset,
                "version": str(self.source.get("version", "")),
                "license": str(self.source.get("license", "")),
                "source_url": str(self.source.get("official_url", "")),
                "sha256_checksum": str(self.source.get("source_record_sha256", "")),
                "is_admitted": True,
                "admission_decision": "DEC-P-001",
                "evidence_type": "real_data",
            },
            "source_mappings": [],
            "cases": sorted(self.cases, key=lambda item: item["id"]),
            "metadata": {
                "normalizer_version": NORMALIZER_VERSION,
                "input_raw_root": "C:\\Users\\anshu\\AppData\\Local\\trace-bench-data",
                "source_metadata_files": [
                    "source-record.json",
                    "checksums.json",
                    "layout-observation.json",
                    "LICENSE-or-rights-notice.txt",
                    "acquisition-log.md",
                ],
                "output_files": sorted([result["path"] for result in stream_results.values() if isinstance(result, dict) and "path" in result]),
                "source_mapping_file": "native-id-maps.jsonl",
                "judgment_evidence_mapping_file": "judgment-evidence-maps.jsonl",
                "query_count": query_count,
                "judgment_count": judgment_count,
                "case_count": len(self.cases),
                "evidence_mapping_status": "document_or_source_segment; atom_mapping_deferred",
                "atom_mapping_artifact": None,
                "evaluation_status": evaluation_status,
                **(extra_metadata or {}),
            },
        }
        write_json(self.root / "manifest.json", manifest)
        write_json(
            self.root / "retention-review.json",
            {
                "source_license": self.source.get("license", ""),
                "license_notice_sha256": self.source.get("license_sha256", ""),
                "admission_decision": "DEC-P-001",
                "local_derived_artifact_status": "retained for admitted local evaluation use; source terms remain attached",
                "redistribution_status": "not assessed or granted by S4",
                "retention_action": "purgeable as a rebuildable derived candidate; do not delete immutable raw source in this packet",
                "rights_interpretation_authority": "source record and human/coordinator review; no new legal interpretation made",
            },
        )
        write_json(
            self.root / "provenance.json",
            {
                "dataset": self.dataset,
                "source_record": self.source,
                "raw_source_root": "C:\\Users\\anshu\\AppData\\Local\\trace-bench-data\\" + self.dataset,
                "raw_directories_immutable": True,
                "normalized_output_version": f"d2b-{self.created_at[:10].replace('-', '')}.1",
                "raw_hashes_verified_before_output": True,
            },
        )
        write_text(
            self.root / "reproduction-log.md",
            "# D2b reproduction log\n\n"
            f"- Normalizer: `{NORMALIZER_VERSION}`\n"
            f"- Input manifest: `{INPUT_MANIFEST_ID}`\n"
            f"- Created-at pin: `{self.created_at}`\n"
            f"- Command template: `python <packet>/evidence/normalize_d2b.py --raw-root C:\\Users\\anshu\\AppData\\Local\\trace-bench-data --out <clean-output-root> --created-at-utc {self.created_at}`\n"
            "- Network: disabled; no providers called; no raw files written.\n"
            "- Expected replay check: compare every file hash in the first run's `checksums.json` except that file itself.\n"
            "- Atom mapping: intentionally not emitted until a named ingest/chunking artifact exists.\n",
        )
        return {
            "dataset": self.dataset,
            "evaluation_status": evaluation_status,
            "query_count": query_count,
            "judgment_count": judgment_count,
            "case_count": len(self.cases),
            "document_count": len(self.doc_by_id),
            "segment_count": self.segments.count,
            "exclusion_count": self.exclusions.count,
            "duplicate_counts": dict(self.duplicates),
            "malformed_counts": dict(self.malformed),
            "ambiguous_counts": dict(self.ambiguous),
            "corpus_sha256": stream_results["corpus"]["corpus_txt"]["sha256"],
        }


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def iter_jsonl(path: Path) -> Iterator[tuple[int, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                yield line_number, None
                continue
            try:
                yield line_number, json.loads(line)
            except json.JSONDecodeError as exc:
                yield line_number, exc


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_dataset_raw(dataset_root: Path, portfolio_entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    checks_path = dataset_root / "checksums.json"
    source_path = dataset_root / "source-record.json"
    layout_path = dataset_root / "layout-observation.json"
    license_path = dataset_root / "LICENSE-or-rights-notice.txt"
    acquisition_path = dataset_root / "acquisition-log.md"
    for required in (checks_path, source_path, layout_path, license_path, acquisition_path, dataset_root / "raw"):
        if not required.exists():
            raise RuntimeError(f"missing D2a artifact: {required}")
    checks = load_json(checks_path)
    files = checks.get("files", {})
    current: dict[str, dict[str, Any]] = {}
    for relative, expected in sorted(files.items()):
        path = dataset_root / Path(relative.replace("/", os.sep))
        if not path.exists():
            raise RuntimeError(f"raw manifest file missing: {dataset_root.name}/{relative}")
        actual_size = path.stat().st_size
        actual_sha = sha256_file(path)
        if actual_size != expected.get("size_bytes") or actual_sha != expected.get("sha256"):
            raise RuntimeError(
                f"raw checksum mismatch for {dataset_root.name}/{relative}: "
                f"expected {expected.get('size_bytes')}:{expected.get('sha256')}, "
                f"actual {actual_size}:{actual_sha}"
            )
        current[relative] = {"size_bytes": actual_size, "sha256": actual_sha}
    source = load_json(source_path)
    metadata_checks = {
        "source_record_sha256": sha256_file(source_path),
        "checksums_sha256": sha256_file(checks_path),
        "layout_observation_sha256": sha256_file(layout_path),
        "license_sha256": sha256_file(license_path),
        "acquisition_log_sha256": sha256_file(acquisition_path),
    }
    for key, expected_key in metadata_checks.items():
        if portfolio_entry.get(key) != expected_key:
            raise RuntimeError(
                f"D2a metadata mismatch for {dataset_root.name}: {key} expected {portfolio_entry.get(key)}, actual {expected_key}"
            )
    source = dict(source)
    source.update(metadata_checks)
    source["raw_file_count"] = len(current)
    source["raw_total_bytes"] = sum(item["size_bytes"] for item in current.values())
    return source, current


def add_judgment(output: DatasetOutput, record: dict[str, Any]) -> None:
    output.judgment_maps.write(record)


def build_beir(dataset: str, raw_root: Path, out_root: Path, source: dict[str, Any], created_at: str) -> dict[str, Any]:
    output = DatasetOutput(dataset, out_root, source, created_at)
    short = dataset.removeprefix("beir-")
    raw = raw_root / dataset / "raw" / short
    corpus_path = raw / "corpus.jsonl"
    query_path = raw / "queries.jsonl"
    docs: dict[str, str] = {}
    for line_number, item in iter_jsonl(corpus_path):
        pointer = {"file": f"raw/{short}/corpus.jsonl", "line": line_number}
        if item is None:
            output.malformed_record("blank_corpus_line", pointer)
            continue
        if isinstance(item, Exception) or not isinstance(item, dict):
            output.malformed_record("invalid_corpus_record", pointer, str(item))
            continue
        native = item.get("_id")
        if native is None or str(native) == "":
            output.malformed_record("missing_native_document_id", pointer)
            continue
        native = str(native)
        title = normalized_text(item.get("title", ""))
        text = normalized_text(item.get("text", ""))
        internal = output.add_document(
            source_key=native,
            native_id=native,
            native_id_origin="source_native_id",
            title=title,
            text=text,
            pointer=pointer,
            field_path="_id,title,text",
        )
        if internal:
            docs[native] = internal
    query_data: dict[str, dict[str, Any]] = {}
    for line_number, item in iter_jsonl(query_path):
        pointer = {"file": f"raw/{short}/queries.jsonl", "line": line_number}
        if item is None:
            output.malformed_record("blank_query_line", pointer)
            continue
        if isinstance(item, Exception) or not isinstance(item, dict):
            output.malformed_record("invalid_query_record", pointer, str(item))
            continue
        native = item.get("_id")
        query = normalized_text(item.get("text", ""))
        if native is None or str(native) == "":
            output.malformed_record("missing_native_query_id", pointer)
            continue
        query_data[str(native)] = {"query": query, "pointer": pointer, "metadata": item.get("metadata", {})}

    qrels: dict[tuple[str, str, str], dict[str, Any]] = {}
    split_queries: defaultdict[str, set[str]] = defaultdict(set)
    positive_by_query: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    nonpositive_by_query: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    conflicting: set[tuple[str, str]] = set()
    judgment_count = 0
    qrels_files = sorted(raw.glob("qrels/*.tsv"))
    for qrels_path in qrels_files:
        split = qrels_path.stem
        with qrels_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            header = next(reader, None)
            for line_number, row in enumerate(reader, 2):
                pointer = {"file": f"raw/{short}/qrels/{qrels_path.name}", "line": line_number}
                if len(row) < 3:
                    output.malformed_record("malformed_qrels_row", pointer, repr(row))
                    continue
                qid, did, score_text = str(row[0]), str(row[1]), str(row[2])
                try:
                    score = int(score_text)
                except ValueError:
                    output.malformed_record("non_integer_qrels_score", pointer, score_text)
                    continue
                key = (split, qid, did)
                existing = qrels.get(key)
                if existing is not None:
                    if existing["score"] == score:
                        output.duplicate_record("duplicate_judgment", {"key": key, "pointer": pointer})
                        continue
                    conflicting.add((split, qid))
                    output.ambiguous_record("conflicting_judgment_score", {"key": key, "pointer": pointer, "previous": existing["score"], "current": score})
                    continue
                qrels[key] = {"split": split, "query_id": qid, "doc_id": did, "score": score, "pointer": pointer}
                split_queries[qid].add(split)
                judgment_count += 1
                if score > 0:
                    positive_by_query[qid].append(qrels[key])
                else:
                    nonpositive_by_query[qid].append(qrels[key])

    for qid, data in sorted(query_data.items()):
        splits = sorted(split_queries.get(qid, set()))
        split = splits[0] if len(splits) == 1 else ("leakage:" + ",".join(splits) if splits else "unjudged")
        leakage = len(splits) > 1
        q_internal = output.add_query(
            source_key=qid,
            native_id=qid,
            native_id_origin="source_native_id",
            query=data["query"],
            split=split,
            query_class="direct_lookup",
            category="direct_lookup",
            pointer=data["pointer"],
            metadata={"source_metadata": data["metadata"], "split_membership": splits},
            evaluation_status="blocked_split_leakage" if leakage else ("usable" if splits else "unjudged"),
        )
        if q_internal is None:
            continue
        positive = []
        query_blocked = leakage or not splits
        for judgment in positive_by_query.get(qid, []):
            did = judgment["doc_id"]
            doc_internal = docs.get(did)
            map_record = {
                "dataset": dataset,
                "judgment_id": stable_id(dataset, "judgment", f"{judgment['split']}|{qid}|{did}"),
                "query_internal_id": q_internal,
                "query_native_id": qid,
                "judgment_native_id": f"{judgment['split']}:{qid}:{did}",
                "judgment_native_id_origin": "derived_from_source_qrels_key",
                "split": judgment["split"],
                "relevance": judgment["score"],
                "source_document_internal_id": doc_internal,
                "source_document_native_id": did,
                "source_document_id_origin": "source_native_id",
                "segment_internal_id": None,
                "evidence_level": "document" if doc_internal else "unresolved",
                "offset_status": "unavailable_source_qrels_document_judgment",
                "raw_pointer": judgment["pointer"],
                "round_trip_status": "pass" if doc_internal else "blocked_missing_source_document",
            }
            add_judgment(output, map_record)
            if doc_internal:
                positive.append(did)
            else:
                query_blocked = True
                output.exclude("judgment_references_missing_document", "judgment", judgment["pointer"], {"query_id": qid, "doc_id": did})
        if qid not in query_data:
            continue
        for judgment in nonpositive_by_query.get(qid, []):
            did = judgment["doc_id"]
            doc_internal = docs.get(did)
            add_judgment(
                output,
                {
                    "dataset": dataset,
                    "judgment_id": stable_id(dataset, "judgment", f"{judgment['split']}|{qid}|{did}"),
                    "query_internal_id": q_internal,
                    "query_native_id": qid,
                    "judgment_native_id": f"{judgment['split']}:{qid}:{did}",
                    "judgment_native_id_origin": "derived_from_source_qrels_key",
                    "split": judgment["split"],
                    "relevance": judgment["score"],
                    "source_document_internal_id": doc_internal,
                    "source_document_native_id": did,
                    "source_document_id_origin": "source_native_id",
                    "segment_internal_id": None,
                    "evidence_level": "nonrelevant_judgment",
                    "offset_status": "not_applicable",
                    "raw_pointer": judgment["pointer"],
                    "round_trip_status": "pass" if doc_internal else "blocked_missing_source_document",
                },
            )
        if not positive:
            output.exclude("query_has_no_positive_judgment", "query", data["pointer"], {"query_id": qid})
        elif query_blocked or (split, qid) in conflicting or (qid in split_queries and len(split_queries[qid]) > 1):
            output.exclude("query_blocked_by_mapping_or_split_validation", "query", data["pointer"], {"query_id": qid, "splits": splits})
        else:
            dedup_positive = sorted(set(positive))
            output.add_case(
                query_internal_id=q_internal,
                native_query_id=qid,
                category="direct_lookup",
                query=data["query"],
                native_gold_doc_ids=dedup_positive,
                expected_abstention=False,
                difficulty="graded" if dataset == "beir-nfcorpus" else "medium",
                metadata={"split": split, "mapping_status": "document_only", "native_gold_ids": True},
            )
            output.add_round_trip(
                {
                    "query_internal_id": q_internal,
                    "query_native_id": qid,
                    "judgment_native_id": f"{split}:{qid}:{dedup_positive[0]}",
                    "source_document_native_id": dedup_positive[0],
                    "source_document_internal_id": docs[dedup_positive[0]],
                    "evidence_level": "document",
                    "offset_status": "unavailable_source_qrels_document_judgment",
                    "round_trip": "query -> judgment -> native document -> internal document -> content hash",
                    "content_hash": output.doc_by_id[docs[dedup_positive[0]]]["content_hash"],
                }
            )
    return output.finalize(
        query_count=len(query_data),
        judgment_count=judgment_count,
        evaluation_status="evaluation_ready_document_level",
        extra_metadata={"query_class": "direct_lookup", "split_leakage_checked": True},
    )


def parquet_rows(path: Path, columns: list[str] | None = None, batch_size: int = 8192) -> Iterator[tuple[int, dict[str, Any]]]:
    parquet = pq.ParquetFile(path)
    row_number = 0
    for batch in parquet.iter_batches(batch_size=batch_size, columns=columns):
        for row in batch.to_pylist():
            row_number += 1
            yield row_number, row


def build_bright(dataset: str, raw_root: Path, out_root: Path, source: dict[str, Any], created_at: str) -> dict[str, Any]:
    output = DatasetOutput(dataset, out_root, source, created_at)
    raw = raw_root / dataset / "raw"
    subsets = sorted(p.stem.removesuffix("-00000-of-00001") for p in (raw / "documents").glob("*.parquet"))
    docs_by_subset: dict[str, dict[str, str]] = defaultdict(dict)
    doc_count = 0
    for subset in subsets:
        path = raw / "documents" / f"{subset}-00000-of-00001.parquet"
        for row_number, row in parquet_rows(path, ["id", "content"]):
            pointer = {"file": f"raw/documents/{path.name}", "row": row_number, "subset": subset}
            native_value = row.get("id")
            content_value = row.get("content")
            if native_value is None or str(native_value) == "":
                output.malformed_record("missing_native_document_id", pointer)
                continue
            native = str(native_value)
            text = normalized_text(content_value)
            scoped = f"{subset}:{native}"
            internal = output.add_document(
                source_key=scoped,
                native_id=native,
                native_id_origin="source_native_id_with_declared_subset_namespace",
                title="",
                text=text,
                pointer=pointer,
                field_path="id,content",
            )
            if internal:
                docs_by_subset[subset][native] = internal
                doc_count += 1
    query_count = 0
    judgment_count = 0
    seen_queries: set[str] = set()
    for subset in subsets:
        path = raw / "examples" / f"{subset}-00000-of-00001.parquet"
        for row_number, row in parquet_rows(path):
            pointer = {"file": f"raw/examples/{path.name}", "row": row_number, "subset": subset}
            native_value = row.get("id")
            query = normalized_text(row.get("query"))
            if native_value is None or str(native_value) == "":
                output.malformed_record("missing_native_query_id", pointer)
                continue
            native = str(native_value)
            scoped_query = f"{subset}:{native}"
            if scoped_query in seen_queries:
                output.duplicate_record("duplicate_query_id", {"source_key": scoped_query, "pointer": pointer})
                continue
            seen_queries.add(scoped_query)
            q_internal = output.add_query(
                source_key=scoped_query,
                native_id=native,
                native_id_origin="source_native_id_with_declared_subset_namespace",
                query=query,
                split="unspecified_in_source",
                query_class="cross_domain_reasoning",
                category="cross_domain",
                pointer=pointer,
                metadata={"subset": subset, "reasoning": row.get("reasoning"), "source_split_status": "not_provided"},
                evaluation_status="usable",
            )
            query_count += 1
            if q_internal is None:
                continue
            raw_gold = [str(value) for value in safe_list(row.get("gold_ids")) if value is not None and str(value) != ""]
            if len(raw_gold) != len(set(raw_gold)):
                output.duplicate_record("duplicate_gold_document_id", {"query": scoped_query, "pointer": pointer})
            gold = sorted(set(raw_gold))
            missing = [value for value in gold if value not in docs_by_subset[subset]]
            for value in gold:
                doc_internal = docs_by_subset[subset].get(value)
                judgment_count += 1
                add_judgment(
                    output,
                    {
                        "dataset": dataset,
                        "judgment_id": stable_id(dataset, "judgment", f"{subset}|{native}|{value}"),
                        "query_internal_id": q_internal,
                        "query_native_id": native,
                        "judgment_native_id": f"{subset}:{native}:{value}",
                        "judgment_native_id_origin": "derived_from_official_example_id_and_gold_id",
                        "split": "unspecified_in_source",
                        "relevance": 1,
                        "source_document_internal_id": doc_internal,
                        "source_document_native_id": value,
                        "source_document_id_origin": "source_native_id_with_declared_subset_namespace",
                        "segment_internal_id": None,
                        "evidence_level": "document" if doc_internal else "unresolved",
                        "offset_status": "unavailable_source_example_document_judgment",
                        "raw_pointer": pointer,
                        "round_trip_status": "pass" if doc_internal else "blocked_missing_source_document",
                    },
                )
            if missing or not gold:
                output.exclude("query_gold_mapping_unusable", "query", pointer, {"missing_gold_ids": missing, "gold_count": len(gold)})
                continue
            native_gold = [f"{subset}:{value}" for value in gold]
            output.add_case(
                query_internal_id=q_internal,
                native_query_id=native,
                category="cross_domain",
                query=query,
                native_gold_doc_ids=native_gold,
                expected_abstention=False,
                difficulty="hard",
                metadata={"subset": subset, "split": "unspecified_in_source", "mapping_status": "document_only", "source_split_status": "not_provided"},
            )
            first_doc = docs_by_subset[subset][gold[0]]
            output.add_round_trip(
                {
                    "query_internal_id": q_internal,
                    "query_native_id": native,
                    "judgment_native_id": f"{subset}:{native}:{gold[0]}",
                    "source_document_native_id": gold[0],
                    "source_document_internal_id": first_doc,
                    "evidence_level": "document",
                    "offset_status": "unavailable_source_example_document_judgment",
                    "round_trip": "query -> gold judgment -> subset-scoped document -> content hash",
                    "content_hash": output.doc_by_id[first_doc]["content_hash"],
                }
            )
    return output.finalize(
        query_count=query_count,
        judgment_count=judgment_count,
        evaluation_status="evaluation_ready_document_level_with_source_split_limitation",
        extra_metadata={
            "query_class": "cross_domain_reasoning",
            "declared_subsets": subsets,
            "source_split_status": "official staged examples do not expose an explicit train/dev/test field",
            "split_leakage_checked": True,
        },
    )


def build_multihop(dataset: str, raw_root: Path, out_root: Path, source: dict[str, Any], created_at: str) -> dict[str, Any]:
    output = DatasetOutput(dataset, out_root, source, created_at)
    raw = raw_root / dataset / "raw"
    corpus = load_json(raw / "corpus.json")
    if not isinstance(corpus, list):
        raise RuntimeError("MultiHop-RAG corpus is not a list")
    by_url: defaultdict[str, list[str]] = defaultdict(list)
    by_title_source_date: defaultdict[tuple[str, str, str], list[str]] = defaultdict(list)
    by_title: defaultdict[str, list[str]] = defaultdict(list)
    for index, item in enumerate(corpus):
        pointer = {"file": "raw/corpus.json", "record": index}
        if not isinstance(item, dict):
            output.malformed_record("invalid_corpus_record", pointer)
            continue
        source_key = f"row:{index}"
        title = normalized_text(item.get("title", ""))
        text = normalized_text(item.get("body", item.get("text", "")))
        internal = output.add_document(
            source_key=source_key,
            native_id=None,
            native_id_origin="derived_source_row_index_no_native_document_id",
            title=title,
            text=text,
            pointer=pointer,
            field_path="title,body",
        )
        if not internal:
            continue
        url = normalized_text(item.get("url", ""))
        source_name = normalized_text(item.get("source", ""))
        published = normalized_text(item.get("published_at", ""))
        if url:
            by_url[url].append(internal)
        by_title_source_date[(title, source_name, published)].append(internal)
        by_title[title].append(internal)
    queries = load_json(raw / "MultiHopRAG.json")
    if not isinstance(queries, list):
        raise RuntimeError("MultiHop-RAG query file is not a list")
    query_count = 0
    judgment_count = 0
    for index, item in enumerate(queries):
        pointer = {"file": "raw/MultiHopRAG.json", "record": index}
        if not isinstance(item, dict):
            output.malformed_record("invalid_query_record", pointer)
            continue
        native_query = f"row:{index}"
        query = normalized_text(item.get("query", ""))
        question_type = normalized_text(item.get("question_type", "")) or "unspecified"
        category = "historical" if question_type == "temporal_query" else ("out_of_scope" if question_type == "null_query" else "multi_hop")
        evidence_list = item.get("evidence_list", [])
        if not isinstance(evidence_list, list):
            output.malformed_record("invalid_evidence_list", pointer)
            continue
        q_internal = output.add_query(
            source_key=native_query,
            native_id=native_query,
            native_id_origin="derived_source_row_index_no_native_query_id",
            query=query,
            split="unspecified_in_source",
            query_class=question_type,
            category=category,
            pointer=pointer,
            metadata={"question_type": question_type, "answer": item.get("answer"), "source_split_status": "not_provided"},
            evaluation_status="usable",
        )
        query_count += 1
        if q_internal is None:
            continue
        if not evidence_list:
            if question_type == "null_query":
                output.add_case(
                    query_internal_id=q_internal,
                    native_query_id=native_query,
                    category="out_of_scope",
                    query=query,
                    native_gold_doc_ids=[],
                    expected_abstention=True,
                    difficulty="hard",
                    metadata={"question_type": question_type, "mapping_status": "explicit_source_null_query"},
                )
            else:
                output.exclude("non_null_query_has_no_evidence", "query", pointer, {"question_type": question_type})
            continue
        query_blocked = False
        positive_ids: list[str] = []
        seen_evidence_docs: set[str] = set()
        for evidence_index, evidence in enumerate(evidence_list):
            if not isinstance(evidence, dict):
                output.malformed_record("invalid_evidence_record", {**pointer, "evidence_index": evidence_index})
                query_blocked = True
                continue
            title = normalized_text(evidence.get("title", ""))
            url = normalized_text(evidence.get("url", ""))
            source_name = normalized_text(evidence.get("source", ""))
            published = normalized_text(evidence.get("published_at", ""))
            candidates = by_url.get(url, []) if url else []
            if not candidates:
                candidates = by_title_source_date.get((title, source_name, published), [])
            if not candidates:
                candidates = by_title.get(title, [])
            if len(candidates) != 1:
                output.ambiguous_record(
                    "evidence_document_match_ambiguous_or_missing",
                    {"query": native_query, "evidence_index": evidence_index, "title": title, "url": url, "candidate_count": len(candidates)},
                )
                output.exclude("evidence_document_match_unusable", "evidence", {**pointer, "evidence_index": evidence_index}, {"title": title, "url": url, "candidate_count": len(candidates)})
                query_blocked = True
                continue
            doc_internal = candidates[0]
            if doc_internal in seen_evidence_docs:
                output.duplicate_record("duplicate_evidence_document", {"query": native_query, "evidence_index": evidence_index, "source_document_internal_id": doc_internal})
                continue
            seen_evidence_docs.add(doc_internal)
            positive_ids.append(doc_internal)
            doc_record = output.doc_by_id[doc_internal]
            fact = normalized_text(evidence.get("fact", ""))
            start = doc_record["text"].find(fact) if fact else -1
            if start >= 0:
                end = start + len(fact)
                segment_key = f"{doc_internal}|body|{start}|{end}|{sha256_text(fact)}"
                segment_id = stable_id(dataset, "segment", segment_key)
                output.add_segment_map(
                    {
                        "dataset": dataset,
                        "segment_internal_id": segment_id,
                        "source_document_internal_id": doc_internal,
                        "source_key": segment_key,
                        "native_segment_id": None,
                        "native_segment_id_origin": "derived_evidence_fact_span",
                        "text": fact,
                        "content_hash": sha256_text(fact),
                        "char_offset_start": start,
                        "char_offset_end": end,
                        "offset_basis": "normalized body field",
                        "raw_pointer": {**pointer, "evidence_index": evidence_index},
                        "raw_field_path": "evidence_list[].fact",
                    }
                )
                evidence_level = "span"
                offset_status = "pass_fact_found_in_normalized_body"
            else:
                segment_id = None
                evidence_level = "document"
                offset_status = "fact_not_found_in_body_document_level_only"
            judgment_count += 1
            add_judgment(
                output,
                {
                    "dataset": dataset,
                    "judgment_id": stable_id(dataset, "judgment", f"{native_query}|{evidence_index}|{doc_internal}"),
                    "query_internal_id": q_internal,
                    "query_native_id": native_query,
                    "judgment_native_id": f"{native_query}:evidence:{evidence_index}",
                    "judgment_native_id_origin": "derived_source_evidence_list_index",
                    "split": "unspecified_in_source",
                    "relevance": 1,
                    "source_document_internal_id": doc_internal,
                    "source_document_native_id": None,
                    "source_document_id_origin": "derived_source_row_index_no_native_document_id",
                    "segment_internal_id": segment_id,
                    "evidence_level": evidence_level,
                    "offset_status": offset_status,
                    "raw_pointer": {**pointer, "evidence_index": evidence_index},
                    "raw_field_path": "evidence_list[]",
                    "round_trip_status": "pass",
                },
            )
        if query_blocked or not positive_ids:
            output.exclude("query_evidence_mapping_incomplete", "query", pointer, {"question_type": question_type})
            continue
        native_gold = [f"derived:source-row:{output.doc_by_id[doc][ 'raw_pointer' ].get('record')}" for doc in positive_ids]
        output.add_case(
            query_internal_id=q_internal,
            native_query_id=native_query,
            category=category,
            query=query,
            native_gold_doc_ids=native_gold,
            expected_abstention=False,
            difficulty="hard",
            metadata={"question_type": question_type, "mapping_status": "document_or_fact_span", "source_split_status": "not_provided"},
        )
        first_doc = positive_ids[0]
        output.add_round_trip(
            {
                "query_internal_id": q_internal,
                "query_native_id": native_query,
                "judgment_native_id": f"{native_query}:evidence:0",
                "source_document_internal_id": first_doc,
                "source_document_native_id": None,
                "source_document_origin": "derived_source_row_index_no_native_document_id",
                "evidence_level": "document_or_fact_span",
                "round_trip": "query -> evidence-list item -> source row -> derived document identity -> content hash",
                "content_hash": output.doc_by_id[first_doc]["content_hash"],
            }
        )
    return output.finalize(
        query_count=query_count,
        judgment_count=judgment_count,
        evaluation_status="evaluation_ready_document_or_span_level_with_derived_source_keys",
        extra_metadata={
            "query_class": "multi_hop",
            "source_split_status": "not_provided_in_source",
            "native_document_id_status": "source has no explicit document ID; row-index keys are labelled derived",
            "split_leakage_checked": False,
        },
    )


def build_musique(dataset: str, raw_root: Path, out_root: Path, source: dict[str, Any], created_at: str) -> dict[str, Any]:
    output = DatasetOutput(dataset, out_root, source, created_at)
    raw = raw_root / dataset / "raw"
    paragraph_docs: dict[str, str] = {}
    title_docs: dict[str, str] = {}
    query_seen: dict[str, str] = {}
    query_count = 0
    judgment_count = 0
    for split in ("dev", "train"):
        path = raw / f"musique_ans_v1.0_{split}.jsonl"
        for line_number, item in iter_jsonl(path):
            pointer = {"file": f"raw/{path.name}", "line": line_number, "split": split}
            if item is None:
                output.malformed_record("blank_query_line", pointer)
                continue
            if isinstance(item, Exception) or not isinstance(item, dict):
                output.malformed_record("invalid_query_record", pointer, str(item))
                continue
            native_query = item.get("id")
            query = normalized_text(item.get("question", ""))
            if native_query is None or str(native_query) == "":
                output.malformed_record("missing_native_query_id", pointer)
                continue
            native_query = str(native_query)
            if native_query in query_seen:
                output.duplicate_record("duplicate_query_id_across_splits", {"query_id": native_query, "pointer": pointer, "previous_split": query_seen[native_query]})
                output.exclude("query_split_leakage", "query", pointer, {"query_id": native_query, "previous_split": query_seen[native_query], "current_split": split})
                continue
            query_seen[native_query] = split
            paragraphs = item.get("paragraphs", [])
            if not isinstance(paragraphs, list):
                output.malformed_record("paragraphs_not_list", pointer)
                continue
            support_idxs: list[int] = []
            row_segment_ids: dict[int, str] = {}
            row_doc_ids: dict[int, str] = {}
            query_blocked = False
            for paragraph in paragraphs:
                if not isinstance(paragraph, dict):
                    output.malformed_record("invalid_paragraph_record", pointer)
                    query_blocked = True
                    continue
                idx = paragraph.get("idx")
                title = normalized_text(paragraph.get("title", ""))
                text = normalized_text(paragraph.get("paragraph_text", ""))
                if not isinstance(idx, int) or not title or not text:
                    output.malformed_record("malformed_paragraph", {**pointer, "paragraph_idx": idx})
                    query_blocked = True
                    continue
                if bool(paragraph.get("is_supporting", False)):
                    support_idxs.append(idx)
                title_key = title
                doc_internal = title_docs.get(title_key)
                if doc_internal is None:
                    doc_internal = stable_id(dataset, "document", title_key)
                    title_docs[title_key] = doc_internal
                    output.native_maps.write(
                        {
                            "dataset": dataset,
                            "entity_type": "document",
                            "native_id": None,
                            "native_id_origin": "derived_title_no_native_document_id",
                            "source_key": title_key,
                            "internal_id": doc_internal,
                            "content_hash": sha256_text(title),
                            "raw_pointer": pointer,
                            "raw_field_path": f"paragraphs[{idx}].title",
                        }
                    )
                    output.add_source_document_identity(
                        internal_id=doc_internal,
                        source_key=title_key,
                        title=title,
                        native_id=None,
                        native_id_origin="derived_title_no_native_document_id",
                        pointer=pointer,
                        content_hash=sha256_text(title),
                    )
                segment_key = f"title:{title}\nparagraph:{text}"
                segment_id = paragraph_docs.get(segment_key)
                if segment_id is None:
                    segment_id = stable_id(dataset, "segment", segment_key)
                    paragraph_docs[segment_key] = segment_id
                    output.add_document(
                        source_key=segment_key,
                        native_id=None,
                        native_id_origin="derived_content_hash_no_native_segment_id",
                        title=title,
                        text=text,
                        pointer={**pointer, "paragraph_idx": idx},
                        field_path=f"paragraphs[{idx}].title,paragraph_text",
                        document_internal_id=segment_id,
                        segment_internal_id=segment_id,
                        entity_type="segment",
                        source_document_key=title_key,
                        source_document_internal_id=doc_internal,
                    )
                else:
                    output.duplicate_record("duplicate_paragraph_content_across_source_records", {"source_key": segment_key, "pointer": {**pointer, "paragraph_idx": idx}})
                row_segment_ids[idx] = segment_id
                row_doc_ids[idx] = doc_internal
            decomposition = item.get("question_decomposition", [])
            decomposition_idxs = []
            if isinstance(decomposition, list):
                for component in decomposition:
                    if isinstance(component, dict) and isinstance(component.get("paragraph_support_idx"), int):
                        decomposition_idxs.append(component["paragraph_support_idx"])
            if decomposition_idxs and set(decomposition_idxs) != set(support_idxs):
                output.ambiguous_record(
                    "support_flag_decomposition_disagreement",
                    {"query_id": native_query, "split": split, "support_flags": sorted(set(support_idxs)), "decomposition": sorted(set(decomposition_idxs))},
                )
                query_blocked = True
            q_internal = output.add_query(
                source_key=native_query,
                native_id=native_query,
                native_id_origin="source_native_id",
                query=query,
                split=split,
                query_class="compositional_multi_hop",
                category="multi_hop",
                pointer=pointer,
                metadata={
                    "answer": item.get("answer"),
                    "answer_aliases": item.get("answer_aliases", []),
                    "answerable": item.get("answerable"),
                    "hop_count": len(decomposition) if isinstance(decomposition, list) else None,
                },
                evaluation_status="blocked_mapping_disagreement" if query_blocked else "usable",
            )
            query_count += 1
            if q_internal is None:
                continue
            evidence_ids: list[str] = []
            for idx in sorted(set(support_idxs)):
                segment_id = row_segment_ids.get(idx)
                doc_id = row_doc_ids.get(idx)
                if not segment_id or not doc_id:
                    query_blocked = True
                    output.exclude("supporting_paragraph_missing_after_normalization", "evidence", {**pointer, "paragraph_idx": idx}, {"query_id": native_query})
                    continue
                paragraph = next((p for p in paragraphs if isinstance(p, dict) and p.get("idx") == idx), None)
                if paragraph is None:
                    query_blocked = True
                    continue
                text = normalized_text(paragraph.get("paragraph_text", ""))
                judgment_count += 1
                evidence_ids.append(segment_id)
                add_judgment(
                    output,
                    {
                        "dataset": dataset,
                        "judgment_id": stable_id(dataset, "judgment", f"{split}|{native_query}|paragraph:{idx}"),
                        "query_internal_id": q_internal,
                        "query_native_id": native_query,
                        "judgment_native_id": f"{split}:{native_query}:paragraph:{idx}",
                        "judgment_native_id_origin": "derived_from_source_supporting_paragraph_index",
                        "split": split,
                        "relevance": 1,
                        "source_document_internal_id": doc_id,
                        "source_document_native_id": None,
                        "source_document_id_origin": "derived_title_no_native_document_id",
                        "segment_internal_id": segment_id,
                        "evidence_level": "segment",
                        "offset_status": "pass_full_paragraph_field",
                        "char_offset_start": 0,
                        "char_offset_end": len(text),
                        "offset_basis": "paragraph_text field value",
                        "raw_pointer": {**pointer, "paragraph_idx": idx},
                        "raw_field_path": f"paragraphs[{idx}].paragraph_text",
                        "round_trip_status": "pass",
                    },
                )
            if query_blocked:
                output.exclude("query_evidence_mapping_blocked", "query", pointer, {"query_id": native_query, "split": split})
                continue
            answerable = item.get("answerable")
            if not evidence_ids:
                if answerable is False:
                    output.add_case(
                        query_internal_id=q_internal,
                        native_query_id=native_query,
                        category="out_of_scope",
                        query=query,
                        native_gold_doc_ids=[],
                        expected_abstention=True,
                        difficulty="hard",
                        metadata={"split": split, "mapping_status": "explicit_unanswerable_source_record"},
                    )
                else:
                    output.exclude("answerable_query_has_no_supporting_paragraph", "query", pointer, {"query_id": native_query, "split": split})
                continue
            output.add_case(
                query_internal_id=q_internal,
                native_query_id=native_query,
                category="multi_hop",
                query=query,
                native_gold_doc_ids=[f"derived:segment:{segment_id}" for segment_id in sorted(set(evidence_ids))],
                expected_abstention=False,
                difficulty="hard",
                metadata={"split": split, "mapping_status": "source_paragraph_segment", "hop_count": len(decomposition) if isinstance(decomposition, list) else None},
            )
            first_support_idx = sorted(set(support_idxs))[0]
            first = row_segment_ids[first_support_idx]
            output.add_round_trip(
                {
                    "query_internal_id": q_internal,
                    "query_native_id": native_query,
                    "judgment_native_id": f"{split}:{native_query}:paragraph:{first_support_idx}",
                    "source_document_internal_id": row_doc_ids[first_support_idx],
                    "source_document_native_id": None,
                    "segment_internal_id": first,
                    "evidence_level": "segment",
                    "offset_status": "pass_full_paragraph_field",
                    "round_trip": "query -> supporting paragraph judgment -> derived title document -> source paragraph segment -> content hash",
                    "content_hash": output.doc_by_id[first]["content_hash"],
                }
            )
    return output.finalize(
        query_count=query_count,
        judgment_count=judgment_count,
        evaluation_status="evaluation_ready_source_segment_level_atom_mapping_deferred",
        extra_metadata={
            "query_class": "compositional_multi_hop",
            "source_segment_status": "official paragraph evidence preserved",
            "native_document_id_status": "source provides titles and paragraph indices but no stable native document IDs; derived identities are labelled",
            "split_leakage_checked": True,
        },
    )


def build_bigann(dataset: str, raw_root: Path, out_root: Path, source: dict[str, Any], created_at: str) -> dict[str, Any]:
    root = out_root / dataset
    root.mkdir(parents=True, exist_ok=True)
    raw = raw_root / dataset / "raw"
    native = JsonlWriter(root / "native-id-maps.jsonl")
    judgments = JsonlWriter(root / "judgment-evidence-maps.jsonl")
    queries = JsonlWriter(root / "queries.jsonl")
    splits = JsonlWriter(root / "split-query-class.jsonl")
    exclusions = JsonlWriter(root / "exclusions.jsonl")
    corpus = JsonlWriter(root / "corpus.jsonl")
    segments = JsonlWriter(root / "segments.jsonl")
    vector_records = []
    for filename, kind, expected_dim, expected_count in (
        ("sift_base.fvecs", "base", 128, 1_000_000),
        ("sift_query.fvecs", "query", 128, 10_000),
        ("sift_learn.fvecs", "learn", 128, 100_000),
        ("sift_groundtruth.ivecs", "groundtruth", 100, 10_000),
    ):
        path = raw / "sift" / filename
        raw_size = path.stat().st_size
        record_size = 4 * (expected_dim + 1)
        header = path.read_bytes()[:4]
        first_dim = int.from_bytes(header, byteorder="little", signed=True) if len(header) == 4 else None
        vector_count = raw_size // record_size if record_size and raw_size % record_size == 0 else None
        status = "pass" if first_dim == expected_dim and vector_count == expected_count else "blocked_header_or_count_mismatch"
        vector_record = {
            "dataset": dataset,
            "entity_type": "vector_file",
            "internal_id": stable_id(dataset, "vector_file", filename),
            "native_id": filename,
            "native_id_origin": "source_file_name",
            "source_key": filename,
            "kind": kind,
            "path": f"raw/sift/{filename}",
            "sha256": sha256_file(path),
            "size_bytes": raw_size,
            "record_dimension_or_k": first_dim,
            "expected_dimension_or_k": expected_dim,
            "record_count": vector_count,
            "expected_count": expected_count,
            "record_size_bytes": record_size,
            "status": status,
            "mapping_rule": "native vector row index remains operations-only; no text atom mapping",
        }
        vector_records.append(vector_record)
        native.write(vector_record)
    splits.write({"dataset": dataset, "split": "operations_only", "query_class": "vector_index_operations", "evaluation_status": "operations_only"})
    exclusions.write({"dataset": dataset, "record_type": "dataset", "reason": "operations_only_not_text_evidence", "pointer": {"root": "raw/sift"}, "detail": {"admission": "DEC-P-001"}})
    for writer in (native, judgments, queries, splits, exclusions, corpus, segments):
        writer.close()
    write_json(root / "vector-operations-manifest.json", {"dataset": dataset, "role": "operations_only", "files": vector_records})
    write_json(root / "normalization-config.json", {"normalizer_version": NORMALIZER_VERSION, "created_at_utc": created_at, "input_manifest_id": INPUT_MANIFEST_ID, "text_normalization": None, "atom_mapping_status": "not_applicable_operations_only"})
    write_json(root / "duplicate-report.json", {"counts": {}, "examples": []})
    write_json(root / "malformed-record-report.json", {"counts": {}, "examples": []})
    write_json(root / "ambiguous-evidence-report.json", {"counts": {}, "examples": []})
    write_json(root / "round-trip-samples.json", {"samples": [{"file": "raw/sift/sift_base.fvecs", "header_dimension": vector_records[0]["record_dimension_or_k"], "record_count": vector_records[0]["record_count"], "round_trip": "file -> binary header -> deterministic row-count check"}]})
    write_json(root / "retention-review.json", {"source_license": source.get("license", ""), "license_notice_sha256": source.get("license_sha256", ""), "admission_decision": "DEC-P-001", "local_derived_artifact_status": "operations metadata only", "redistribution_status": "not assessed or granted by S4"})
    write_json(root / "provenance.json", {"dataset": dataset, "source_record": source, "raw_source_root": "C:\\Users\\anshu\\AppData\\Local\\trace-bench-data\\bigann", "raw_directories_immutable": True, "normalized_output_version": f"d2b-{created_at[:10].replace('-', '')}.1"})
    write_text(root / "reproduction-log.md", f"# D2b reproduction log\n\n- Normalizer: `{NORMALIZER_VERSION}`\n- Input manifest: `{INPUT_MANIFEST_ID}`\n- Role: operations/vector-only; no text evaluation or atom mapping.\n")
    empty_hash = sha256_text("")
    manifest = {
        "contract_version": "1.0",
        "artifact_id": f"d2b:{dataset}:manifest:{INPUT_MANIFEST_ID}",
        "created_at": created_at,
        "producer": {"component": "S4 Data Steward", "task": "s4-d2b-dataset-normalization-20260819", "normalizer_version": NORMALIZER_VERSION},
        "input_manifest_id": INPUT_MANIFEST_ID,
        "correlation_id": f"s4-d2b:{dataset}:{INPUT_MANIFEST_ID}",
        "status": "operations_only",
        "name": dataset,
        "version": f"d2b-{created_at[:10].replace('-', '')}.1",
        "description": "Operations and vector-scale source inventory; not text-memory evidence.",
        "corpus_sha256": empty_hash,
        "corpus_text": "",
        "corpus_file": None,
        "release_authority": False,
        "mode": "regression",
        "admission": {"dataset_name": dataset, "version": str(source.get("version", "")), "license": str(source.get("license", "")), "source_url": str(source.get("official_url", "")), "sha256_checksum": str(source.get("source_record_sha256", "")), "is_admitted": True, "admission_decision": "DEC-P-001", "evidence_type": "real_data"},
        "source_mappings": [],
        "cases": [],
        "metadata": {"role": "operations_only", "vector_operations_manifest": "vector-operations-manifest.json", "evidence_mapping_status": "not_applicable", "atom_mapping_artifact": None},
    }
    write_json(root / "manifest.json", manifest)
    return {"dataset": dataset, "evaluation_status": "operations_only", "query_count": 0, "judgment_count": 0, "case_count": 0, "document_count": 0, "segment_count": 0, "exclusion_count": 1, "vector_file_count": len(vector_records)}


def inventory_hashes(root: Path, exclude: set[str] | None = None) -> dict[str, dict[str, Any]]:
    exclude = exclude or set()
    result = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in exclude:
            continue
        result[relative] = {"size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
    return result


def validate_b1_manifest(path: Path) -> None:
    # schema.py lives at <worktree>/src/trace_bench/datasets/schema.py; the
    # import root is therefore <worktree>/src, i.e. parents[2].
    import_root = B1_SCHEMA_PATH.parents[2]
    sys.path.insert(0, str(import_root))
    try:
        from trace_bench.datasets.loader import load_manifest

        load_manifest(path)
    finally:
        try:
            sys.path.remove(str(import_root))
        except ValueError:
            pass


def preflight(raw_root: Path, output_root: Path, portfolio_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if output_root.exists():
        raise RuntimeError(f"output root already exists; refusing to overwrite: {output_root}")
    portfolio = load_json(portfolio_path)
    entries = portfolio.get("datasets", {})
    if set(DATASETS) - set(entries):
        raise RuntimeError(f"portfolio missing admitted dataset entries: {sorted(set(DATASETS) - set(entries))}")
    actual_dirs = {path.name for path in raw_root.iterdir() if path.is_dir() and path.name not in {"normalized", "verification"}}
    extras = sorted(actual_dirs - set(DATASETS))
    if extras:
        raise RuntimeError(f"unadmitted raw roots present; refusing ambiguous input scope: {extras}")
    verified = {}
    for dataset in DATASETS:
        source, hashes = verify_dataset_raw(raw_root / dataset, entries[dataset])
        source["raw_file_hashes"] = hashes
        verified[dataset] = source
    return verified, portfolio


def build_all(raw_root: Path, output_root: Path, portfolio_path: Path, created_at: str) -> None:
    verified, portfolio = preflight(raw_root, output_root, portfolio_path)
    output_root.mkdir(parents=True, exist_ok=False)
    summaries: list[dict[str, Any]] = []
    try:
        for dataset in ("beir-scifact", "beir-nfcorpus", "beir-fiqa"):
            summaries.append(build_beir(dataset, raw_root, output_root, verified[dataset], created_at))
        summaries.append(build_bright("bright", raw_root, output_root, verified["bright"], created_at))
        summaries.append(build_multihop("multihop-rag", raw_root, output_root, verified["multihop-rag"], created_at))
        summaries.append(build_musique("musique", raw_root, output_root, verified["musique"], created_at))
        summaries.append(build_bigann("bigann", raw_root, output_root, verified["bigann"], created_at))
        write_json(
            output_root / "run-manifest.json",
            {
                "contract_version": "1.0",
                "artifact_id": f"d2b:run:{INPUT_MANIFEST_ID}",
                "created_at": created_at,
                "producer": {"component": "S4 Data Steward", "task": "s4-d2b-dataset-normalization-20260819", "normalizer_version": NORMALIZER_VERSION},
                "input_manifest_id": INPUT_MANIFEST_ID,
                "status": "completed_candidate",
                "datasets": summaries,
                "raw_input_scope": list(DATASETS),
                "raw_mutated": False,
                "network_used": False,
                "provider_used": False,
                "atom_ids_created": False,
                "claim_boundary": "No retrieval-quality, SOTA, release-threshold, or independent-certification claim.",
            },
        )
        write_text(
            output_root / "reproduction-log.md",
            "# S4 D2b run reproduction log\n\n"
            f"- Normalizer: `{NORMALIZER_VERSION}`\n"
            f"- Input manifest: `{INPUT_MANIFEST_ID}`\n"
            f"- B1.1 successor: `{B1_COMMIT}`\n"
            f"- Created-at pin: `{created_at}`\n"
            "- Command template: `python <packet>/evidence/normalize_d2b.py --raw-root C:\\Users\\anshu\\AppData\\Local\\trace-bench-data --out <clean-output-root> --portfolio <packet>/../b2-authorized-data-staging-20260819/evidence/portfolio-staging-manifest.json --created-at-utc "
            f"{created_at}`\n"
            "- Network/provider: disabled. Raw directories are immutable and are not copied or altered.\n"
            "- Replay acceptance: run into a new output root with the same created-at pin and compare all non-self hashes in `checksums.json`.\n"
            "- Atom IDs: not created because no named ingest/chunking artifact exists in the pinned inputs.\n",
        )
        checksums = inventory_hashes(output_root, {"checksums.json"})
        write_json(output_root / "checksums.json", {"algorithm": "SHA-256", "self_excluded": True, "files": checksums})
        write_json(output_root / "COMPLETED.json", {"status": "completed_candidate", "input_manifest_id": INPUT_MANIFEST_ID, "checksums_self_excluded": True, "normalizer_version": NORMALIZER_VERSION})
        # COMPLETED.json is part of the output and must be included in the final inventory.
        checksums = inventory_hashes(output_root, {"checksums.json"})
        write_json(output_root / "checksums.json", {"algorithm": "SHA-256", "self_excluded": True, "files": checksums})
        # Every generated manifest must parse through the pinned B1 model/loader.
        for dataset in DATASETS:
            validate_b1_manifest(output_root / dataset / "manifest.json")
    except Exception as exc:
        write_json(
            output_root / "error-receipt.json",
            {
                "error_code": "ERR_D2B_NORMALIZATION_FAILED",
                "stage": "normalization",
                "message": str(exc),
                "input_manifest_id": INPUT_MANIFEST_ID,
                "fallback_forbidden": True,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "normalizer_version": NORMALIZER_VERSION,
            },
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--portfolio", type=Path, required=True)
    parser.add_argument("--created-at-utc", required=True)
    args = parser.parse_args()
    if not args.raw_root.is_dir():
        raise SystemExit(f"raw root does not exist: {args.raw_root}")
    if not args.portfolio.is_file():
        raise SystemExit(f"portfolio manifest does not exist: {args.portfolio}")
    build_all(args.raw_root, args.out, args.portfolio, args.created_at_utc)
    print(json.dumps({"status": "completed_candidate", "output_root": str(args.out), "normalizer_version": NORMALIZER_VERSION}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
