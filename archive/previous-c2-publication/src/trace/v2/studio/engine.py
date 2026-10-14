"""Dataset catalog and benchmark suite coordinator for Trace Studio.

Auto-discovers and indexes scale datasets in local storage as well as repo fixtures:
- 1M scale manifest (`1m_scale_corpus_manifest.json`)
- 2WikiMultihop (`multihop/2wikimultihop_corpus.jsonl` & `multihop/2wikimultihop_queries.jsonl`)
- MuSiQue (`multihop/musique_corpus.jsonl` & `multihop/musique_queries.jsonl`)
- Enron Emails (`enron/enron_emails.jsonl`)
- SEC EDGAR Filings (`edgar/sec_edgar_filings.jsonl`)
- Wikipedia Stream (`wikipedia/wikipedia_stream.jsonl` & `wikipedia/wikipedia.db`)
- LKML Commits (`lkml/lkml_commits.jsonl`)
- Git Repositories (`code/cpython.git`, `code/rust.git`)
- Repo Benchmark Fixtures (`benchmarks/technical-docs-v1.json`, `benchmarks/bright-coding-v1.json`)

Runs benchmark test suites through Trace Hybrid and comparative baselines with live telemetry and full disk persistence.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Sequence
import uuid

from pydantic import BaseModel, Field


from .comparisons import (
    BaseComparativeEngine,
    TraceHybridEngine,
    get_engine,
)
from .telemetry import (
    BenchmarkEvent,
    CaseExecutionResult,
    calculate_abstention_correctness,
    calculate_citation_precision,
    calculate_evidence_coverage,
    calculate_ndcg_at_k,
    calculate_recall_at_k,
    telemetry_manager,
)


class DatasetInfo(BaseModel):
    """Catalog metadata for an available or scale dataset."""

    id: str
    name: str
    category: str  # multihop | enterprise_email | financial_sec | encyclopedic | linux_kernel | code | fixtures
    description: str
    file_path: str
    size_bytes: int = 0
    size_mb: float = 0.0
    record_count: int | str = 0
    sha256: str | None = None
    is_available: bool = True
    has_queries: bool = False
    query_file_path: str | None = None
    query_count: int = 0
    query_sha256: str | None = None
    is_evaluable: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkSuiteInfo(BaseModel):
    """Overview of a runnable benchmark test suite."""

    suite_id: str
    name: str
    dataset_id: str
    case_count: int
    description: str
    tags: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Dataset Catalog
# -----------------------------------------------------------------------------


class DatasetCatalog:
    """Auto-discovers, indexes, normalizes, and loads scale datasets and test fixtures."""

    def __init__(self, scale_data_dir: str | Path | None = None) -> None:
        self.scale_data_dir = self._resolve_scale_dir(scale_data_dir)
        self.repo_root = self._resolve_repo_root()
        self._cached_manifest: dict[str, Any] | None = None
        self._id_maps: dict[str, dict[str, str]] = {}
        self._file_hashes: dict[str, str] = {}

    @staticmethod
    def _resolve_scale_dir(custom_path: str | Path | None) -> Path:
        if custom_path:
            p = Path(custom_path)
            if p.exists():
                return p
        env_dir = os.environ.get("TRACE_SCALE_DATA_DIR")
        if env_dir and Path(env_dir).exists():
            return Path(env_dir)

        # Cross-platform WSL / Linux mount check
        wsl_path = Path("/mnt/c/Users/anshu/AppData/Local/trace-scale-data")
        if wsl_path.exists():
            return wsl_path

        # Standard Windows AppData location
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            win_path = Path(local_app) / "trace-scale-data"
            if win_path.exists():
                return win_path

        # Cross-platform user home fallback
        home_fallback = Path.home() / ".trace" / "scale-data"
        if home_fallback.exists():
            return home_fallback

        return Path(os.environ.get("LOCALAPPDATA", "C:\\Users\\anshu\\AppData\\Local")) / "trace-scale-data"

    @staticmethod
    def _resolve_repo_root() -> Path:
        # Resolve path to trace root from current file
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "benchmarks").is_dir() or (parent / "pyproject.toml").is_file():
                return parent
        return Path.cwd()

    def _compute_sha256(self, path: Path) -> str | None:
        """Compute and cache SHA-256 hash of a file."""
        key = str(path.resolve())
        if key in self._file_hashes:
            return self._file_hashes[key]
        if not path.is_file():
            return None
        try:
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            self._file_hashes[key] = h
            return h
        except Exception:
            return None

    def get_dataset_hashes(self, dataset_id: str) -> tuple[str | None, str | None]:
        """Return (corpus_sha256, queries_sha256) for a dataset."""
        info = self.get_dataset(dataset_id)
        if not info:
            return (None, None)

        corpus_sha = info.sha256
        if not corpus_sha and info.file_path:
            corpus_sha = self._compute_sha256(Path(info.file_path))

        query_sha = info.query_sha256
        if not query_sha and info.query_file_path:
            query_sha = self._compute_sha256(Path(info.query_file_path))

        return (corpus_sha, query_sha)

    def _load_manifest(self) -> dict[str, Any]:
        if self._cached_manifest is not None:
            return self._cached_manifest
        manifest_path = self.scale_data_dir / "1m_scale_corpus_manifest.json"
        if manifest_path.is_file():
            try:
                self._cached_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                self._cached_manifest = {}
        else:
            self._cached_manifest = {}
        return self._cached_manifest

    def list_datasets(self) -> list[DatasetInfo]:
        """Alias for discover_all."""
        return self.discover_all()

    def discover_all(self) -> list[DatasetInfo]:
        """Scan scale directories and repo fixtures, returning all discovered datasets."""
        datasets: list[DatasetInfo] = []

        manifest = self._load_manifest()

        # 1. Multi-hop datasets (2WikiMultihop & MuSiQue)
        wiki_corpus = self.scale_data_dir / "multihop" / "2wikimultihop_corpus.jsonl"
        wiki_queries = self.scale_data_dir / "multihop" / "2wikimultihop_queries.jsonl"
        if wiki_corpus.is_file():
            meta = manifest.get("multihop/2wikimultihop_corpus.jsonl", {})
            q_meta = manifest.get("multihop/2wikimultihop_queries.jsonl", {})
            has_q = wiki_queries.is_file()
            q_count = q_meta.get("record_count", 2)
            datasets.append(
                DatasetInfo(
                    id="multihop-2wiki",
                    name="2WikiMultihop QA",
                    category="multihop",
                    description="Complex multi-step Wikipedia reasoning benchmark with gold reasoning chains and triples.",
                    file_path=str(wiki_corpus),
                    size_bytes=meta.get("size_bytes", wiki_corpus.stat().st_size),
                    size_mb=meta.get("size_mb", round(wiki_corpus.stat().st_size / 1_048_576, 2)),
                    record_count=meta.get("record_count", 5),
                    sha256=meta.get("sha256") or self._compute_sha256(wiki_corpus),
                    is_available=True,
                    has_queries=has_q,
                    query_file_path=str(wiki_queries) if has_q else None,
                    query_count=q_count,
                    query_sha256=q_meta.get("sha256") or (self._compute_sha256(wiki_queries) if has_q else None),
                    is_evaluable=has_q and q_count > 0,
                    metadata={"benchmark_type": "compositional_reasoning"},
                )
            )

        musique_corpus = self.scale_data_dir / "multihop" / "musique_corpus.jsonl"
        musique_queries = self.scale_data_dir / "multihop" / "musique_queries.jsonl"
        if musique_corpus.is_file():
            meta = manifest.get("multihop/musique_corpus.jsonl", {})
            q_meta = manifest.get("multihop/musique_queries.jsonl", {})
            has_q = musique_queries.is_file()
            q_count = q_meta.get("record_count", 1000)
            datasets.append(
                DatasetInfo(
                    id="multihop-musique",
                    name="MuSiQue Multi-Hop Corpus",
                    category="multihop",
                    description="High-difficulty multi-hop reasoning corpus with 12,493 documents and 1,000 question chains.",
                    file_path=str(musique_corpus),
                    size_bytes=meta.get("size_bytes", musique_corpus.stat().st_size),
                    size_mb=meta.get("size_mb", round(musique_corpus.stat().st_size / 1_048_576, 2)),
                    record_count=meta.get("record_count", 12493),
                    sha256=meta.get("sha256") or self._compute_sha256(musique_corpus),
                    is_available=True,
                    has_queries=has_q,
                    query_file_path=str(musique_queries) if has_q else None,
                    query_count=q_count,
                    query_sha256=q_meta.get("sha256") or (self._compute_sha256(musique_queries) if has_q else None),
                    is_evaluable=has_q and q_count > 0,
                    metadata={"benchmark_type": "hop_chains"},
                )
            )

        # 2. Enron Emails (Exploratory / Scale dataset without frozen query judgments)
        enron_file = self.scale_data_dir / "enron" / "enron_emails.jsonl"
        if enron_file.is_file():
            meta = manifest.get("enron/enron_emails.jsonl", {})
            datasets.append(
                DatasetInfo(
                    id="enron-emails",
                    name="Enron Corporate Communications",
                    category="enterprise_email",
                    description="50,000 real enterprise email threads with sender/recipient metadata and temporal timestamps.",
                    file_path=str(enron_file),
                    size_bytes=meta.get("size_bytes", enron_file.stat().st_size),
                    size_mb=meta.get("size_mb", round(enron_file.stat().st_size / 1_048_576, 2)),
                    record_count=meta.get("record_count", 50000),
                    sha256=meta.get("sha256") or self._compute_sha256(enron_file),
                    is_available=True,
                    has_queries=False,
                    query_file_path=None,
                    query_count=0,
                    query_sha256=None,
                    is_evaluable=False,
                    metadata={"domain": "enterprise", "temporal": True, "dataset_class": "exploratory_scale"},
                )
            )

        # 3. SEC EDGAR Filings (Exploratory / Scale dataset without frozen query judgments)
        edgar_file = self.scale_data_dir / "edgar" / "sec_edgar_filings.jsonl"
        if edgar_file.is_file():
            meta = manifest.get("edgar/sec_edgar_filings.jsonl", {})
            datasets.append(
                DatasetInfo(
                    id="sec-edgar",
                    name="SEC EDGAR 10-K / 10-Q Financial Filings",
                    category="financial_sec",
                    description="Public financial statements, balance sheets, risk factors, and footnotes from Form 10-Q/10-K filings.",
                    file_path=str(edgar_file),
                    size_bytes=meta.get("size_bytes", edgar_file.stat().st_size),
                    size_mb=meta.get("size_mb", round(edgar_file.stat().st_size / 1_048_576, 2)),
                    record_count=meta.get("record_count", 50),
                    sha256=meta.get("sha256") or self._compute_sha256(edgar_file),
                    is_available=True,
                    has_queries=False,
                    query_file_path=None,
                    query_count=0,
                    query_sha256=None,
                    is_evaluable=False,
                    metadata={"domain": "finance", "dataset_class": "exploratory_scale"},
                )
            )

        # 4. Wikipedia Corpus (Exploratory / Scale dataset without frozen query judgments)
        wiki_stream = self.scale_data_dir / "wikipedia" / "wikipedia_stream.jsonl"
        if wiki_stream.is_file():
            meta = manifest.get("wikipedia/wikipedia_stream.jsonl", {})
            datasets.append(
                DatasetInfo(
                    id="wikipedia-stream",
                    name="Wikipedia Knowledge Stream",
                    category="encyclopedic",
                    description="500 high-density encyclopedic Wikipedia articles covering science, history, and technology.",
                    file_path=str(wiki_stream),
                    size_bytes=meta.get("size_bytes", wiki_stream.stat().st_size),
                    size_mb=meta.get("size_mb", round(wiki_stream.stat().st_size / 1_048_576, 2)),
                    record_count=meta.get("record_count", 500),
                    sha256=meta.get("sha256") or self._compute_sha256(wiki_stream),
                    is_available=True,
                    has_queries=False,
                    query_file_path=None,
                    query_count=0,
                    query_sha256=None,
                    is_evaluable=False,
                    metadata={"domain": "general_knowledge", "dataset_class": "exploratory_scale"},
                )
            )

        # 5. LKML Commits (Exploratory / Scale dataset without frozen query judgments)
        lkml_file = self.scale_data_dir / "lkml" / "lkml_commits.jsonl"
        if lkml_file.is_file():
            meta = manifest.get("lkml/lkml_commits.jsonl", {})
            datasets.append(
                DatasetInfo(
                    id="lkml-commits",
                    name="Linux Kernel Mailing List (LKML) & Commits",
                    category="linux_kernel",
                    description="Linux kernel patches, commit logs, trailers, and subsystem change histories.",
                    file_path=str(lkml_file),
                    size_bytes=meta.get("size_bytes", lkml_file.stat().st_size),
                    size_mb=meta.get("size_mb", round(lkml_file.stat().st_size / 1_048_576, 2)),
                    record_count=meta.get("record_count", 31),
                    sha256=meta.get("sha256") or self._compute_sha256(lkml_file),
                    is_available=True,
                    has_queries=False,
                    query_file_path=None,
                    query_count=0,
                    query_sha256=None,
                    is_evaluable=False,
                    metadata={"domain": "systems_software", "dataset_class": "exploratory_scale"},
                )
            )

        # 6. Local Benchmark Fixtures in repo
        benchmarks_dir = self.repo_root / "benchmarks"
        if benchmarks_dir.is_dir():
            for bench_path in sorted(benchmarks_dir.glob("*.json")):
                if bench_path.name.endswith(".schema.json") or bench_path.name.endswith(".template.json") or bench_path.name.endswith(".lock.json"):
                    continue
                try:
                    data = json.loads(bench_path.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "cases" in data:
                        cases = data.get("cases", [])
                        file_sha = self._compute_sha256(bench_path)
                        datasets.append(
                            DatasetInfo(
                                id=f"fixture-{bench_path.stem}",
                                name=data.get("name", bench_path.stem),
                                category="fixtures",
                                description=f"Curated frozen benchmark fixture ({len(cases)} cases) with gold byte-anchor references.",
                                file_path=str(bench_path),
                                size_bytes=bench_path.stat().st_size,
                                size_mb=round(bench_path.stat().st_size / 1_048_576, 3),
                                record_count=len(cases),
                                sha256=file_sha,
                                is_available=True,
                                has_queries=len(cases) > 0,
                                query_file_path=str(bench_path),
                                query_count=len(cases),
                                query_sha256=file_sha,
                                is_evaluable=len(cases) > 0,
                                metadata={
                                    "suite": data.get("suite", "in_domain"),
                                    "review_status": data.get("review_status", "development_fixture"),
                                    "is_fixture": True,
                                    "dataset_class": "frozen_benchmark",
                                },
                            )
                        )
                except Exception:
                    pass

        return datasets

    def get_dataset(self, dataset_id: str) -> DatasetInfo | None:
        """Find a dataset by ID."""
        for d in self.discover_all():
            if d.id == dataset_id or d.id.replace("fixture-", "") == dataset_id:
                return d
        return None

    def get_id_mapping(self, dataset_id: str) -> dict[str, str]:
        """Build and cache a deterministic mapping from document IDs, hashes, and URIs to loaded atom/record IDs."""
        if dataset_id in self._id_maps:
            return self._id_maps[dataset_id]

        id_map: dict[str, str] = {}
        info = self.get_dataset(dataset_id)
        if not info or not Path(info.file_path).is_file():
            self._id_maps[dataset_id] = id_map
            return id_map

        path = Path(info.file_path)

        if path.suffix == ".jsonl":
            try:
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        rec_id = record.get("record_id")
                        if not rec_id:
                            continue

                        title = record.get("metadata", {}).get("title", "")
                        content = record.get("content", "")
                        doc_name = record.get("document_name", "")
                        source_uri = record.get("source_uri", "")
                        content_hash = record.get("content_hash", "")

                        # Compute title:passage hash as used in stage_multihop
                        p_text = content.split("\n\n", 1)[1] if "\n\n" in content else content
                        h16 = hashlib.sha256(f"{title}:{p_text}".encode("utf-8")).hexdigest()[:16]
                        hfull = hashlib.sha256(f"{title}:{p_text}".encode("utf-8")).hexdigest()

                        # Register all standard identifier aliases
                        id_map[rec_id] = rec_id
                        id_map[f"musique/doc/{h16}"] = rec_id
                        id_map[f"musique/doc/{hfull}"] = rec_id
                        id_map[f"musique:{h16}"] = rec_id
                        id_map[f"2wikimultihop/doc/{h16}"] = rec_id
                        id_map[f"2wikimultihop/doc/{hfull}"] = rec_id
                        id_map[f"2wiki/doc/{h16}"] = rec_id
                        id_map[f"2wiki/doc/{hfull}"] = rec_id
                        id_map[f"2wikimultihop:{h16}"] = rec_id
                        id_map[f"2wiki:{h16}"] = rec_id
                        id_map[h16] = rec_id
                        id_map[hfull] = rec_id

                        if doc_name:
                            id_map[doc_name] = rec_id
                            id_map[f"doc/{doc_name}"] = rec_id
                        if source_uri:
                            id_map[source_uri] = rec_id
                        if content_hash:
                            id_map[content_hash] = rec_id
                            id_map[content_hash[:16]] = rec_id
            except Exception:
                pass

        elif path.suffix == ".json" and not path.name.endswith(".jsonl"):
            # Repo fixtures: hash the content
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                fixture_corpus = data.get("fixture_corpus")
                if fixture_corpus:
                    from ..atomizer import atomize

                    drafts = atomize(fixture_corpus)
                    for d in drafts:
                        aid = hashlib.sha256(d.content.encode("utf-8")).hexdigest()
                        id_map[aid] = aid
                        id_map[aid[:16]] = aid
                        id_map[aid[:8]] = aid
            except Exception:
                pass

        self._id_maps[dataset_id] = id_map
        return id_map

    def normalize_gold_ids(self, dataset_id: str, raw_gold_ids: Sequence[str]) -> list[str]:
        """Map raw gold doc IDs (e.g. musique/doc/<hash>) to deterministic loaded atom IDs."""
        id_map = self.get_id_mapping(dataset_id)
        normalized: list[str] = []
        for gid in raw_gold_ids:
            if not gid:
                continue
            if gid in id_map:
                normalized.append(id_map[gid])
                continue

            # Prefix normalization
            clean_gid = gid.strip()
            clean_lower = clean_gid.lower()
            if clean_gid in id_map:
                normalized.append(id_map[clean_gid])
            elif clean_lower in id_map:
                normalized.append(id_map[clean_lower])
            elif clean_gid.startswith("musique/doc/") and clean_gid.replace("musique/doc/", "") in id_map:
                normalized.append(id_map[clean_gid.replace("musique/doc/", "")])
            elif clean_gid.startswith("2wikimultihop/doc/") and clean_gid.replace("2wikimultihop/doc/", "") in id_map:
                normalized.append(id_map[clean_gid.replace("2wikimultihop/doc/", "")])
            elif clean_gid.startswith("2wiki/doc/") and clean_gid.replace("2wiki/doc/", "") in id_map:
                normalized.append(id_map[clean_gid.replace("2wiki/doc/", "")])
            elif clean_gid.startswith("musique:") and clean_gid.replace("musique:", "") in id_map:
                normalized.append(id_map[clean_gid.replace("musique:", "")])
            elif clean_gid.startswith("2wikimultihop:") and clean_gid.replace("2wikimultihop:", "") in id_map:
                normalized.append(id_map[clean_gid.replace("2wikimultihop:", "")])
            elif clean_gid.startswith("2wiki:") and clean_gid.replace("2wiki:", "") in id_map:
                normalized.append(id_map[clean_gid.replace("2wiki:", "")])
            else:
                normalized.append(clean_gid)

        return normalized

    def load_sample_records(self, dataset_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Load a preview slice of records from a dataset."""
        info = self.get_dataset(dataset_id)
        if not info or not Path(info.file_path).is_file():
            return []

        path = Path(info.file_path)
        records: list[dict[str, Any]] = []

        if path.suffix == ".jsonl":
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                            if len(records) >= limit:
                                break
                        except json.JSONDecodeError:
                            continue
        elif path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "cases" in data:
                    records = data["cases"][:limit]
                elif isinstance(data, list):
                    records = data[:limit]
            except Exception:
                pass

        return records

    def load_test_cases(self, dataset_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Load benchmark query cases for evaluation with deterministically resolved gold atom IDs.

        For datasets without frozen query judgments (e.g. raw Enron email dumps),
        returns an empty list to prevent ungrounded, synthetic evaluations.
        """
        info = self.get_dataset(dataset_id)
        if not info or not info.has_queries:
            return []

        cases: list[dict[str, Any]] = []

        # If it's a fixture JSON
        if info.file_path.endswith(".json") and not info.file_path.endswith(".jsonl"):
            path = Path(info.file_path)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for c in data.get("cases", []):
                    cases.append({
                        "id": c["id"],
                        "query": c["query"],
                        "kind": c.get("kind", "direct_lookup"),
                        "gold_atom_version_ids": c.get("gold_atom_version_ids", []),
                        "raw_gold_doc_ids": c.get("gold_atom_version_ids", []),
                        "out_of_scope": bool(c.get("out_of_scope", False)),
                        "fixture_corpus": data.get("fixture_corpus"),
                    })
            except Exception:
                pass

        # If it has a separate queries JSONL file (e.g. 2wikimultihop or musique)
        elif info.query_file_path and Path(info.query_file_path).is_file():
            q_path = Path(info.query_file_path)
            with q_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            item = json.loads(line)
                            raw_golds = item.get("gold_doc_ids", [])
                            mapped_golds = self.normalize_gold_ids(dataset_id, raw_golds)

                            cases.append({
                                "id": item.get("query_id", f"case_{len(cases)+1}"),
                                "query": item["query"],
                                "kind": item.get("query_type", "multihop"),
                                "gold_atom_version_ids": mapped_golds,
                                "raw_gold_doc_ids": raw_golds,
                                "gold_answer": item.get("gold_answer"),
                                "gold_sentences": item.get("gold_sentences", []),
                                "gold_triples": item.get("gold_triples", []),
                                "out_of_scope": False,
                            })
                        except json.JSONDecodeError:
                            continue

        if limit is not None and limit > 0:
            cases = cases[:limit]

        return cases

    def load_atoms_for_dataset(self, dataset_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Convert dataset records or fixture corpus into normalized atom dictionaries without hidden truncation."""
        info = self.get_dataset(dataset_id)
        if not info or not Path(info.file_path).is_file():
            return []

        path = Path(info.file_path)
        atoms: list[dict[str, Any]] = []

        # If fixture JSON has fixture_corpus
        if path.suffix == ".json" and not path.name.endswith(".jsonl"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                fixture_corpus = data.get("fixture_corpus")
                if fixture_corpus:
                    from ..atomizer import atomize

                    drafts = atomize(fixture_corpus)
                    for d in drafts:
                        aid = hashlib.sha256(d.content.encode("utf-8")).hexdigest()
                        atoms.append({
                            "atom_version_id": aid,
                            "node_id": f"node:{aid[:8]}",
                            "content": d.content,
                            "workspace_id": data.get("fixture_workspace_id", "benchmark-alpha"),
                            "properties": {
                                "source_start": d.start,
                                "source_end": d.end,
                                "parser_location": d.parser_location,
                                "source": {"uri": f"trace://fixtures/{info.id}"},
                            },
                        })
                        if limit is not None and limit > 0 and len(atoms) >= limit:
                            break
                    return atoms
            except Exception:
                pass

        # If JSONL file
        if path.suffix == ".jsonl":
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        aid = record.get("record_id", hashlib.sha256(line.encode("utf-8")).hexdigest())
                        content = record.get("content", "")
                        title = record.get("metadata", {}).get("title", "")
                        p_text = content.split("\n\n", 1)[1] if "\n\n" in content else content
                        h16 = hashlib.sha256(f"{title}:{p_text}".encode("utf-8")).hexdigest()[:16]

                        atoms.append({
                            "atom_version_id": aid,
                            "node_id": f"node:{aid[:8] if ':' not in aid else aid.split(':', 1)[1][:8]}",
                            "content": content,
                            "workspace_id": dataset_id,
                            "properties": {
                                "source_start": 0,
                                "source_end": len(content),
                                "parser_location": f"char:0-{len(content)}",
                                "source": {"uri": record.get("source_uri", f"trace://scale/{dataset_id}")},
                                "document_name": record.get("document_name"),
                                "doc_id": f"{dataset_id}/doc/{h16}",
                                "content_hash": record.get("content_hash"),
                                "metadata": record.get("metadata", {}),
                            },
                        })
                        if limit is not None and limit > 0 and len(atoms) >= limit:
                            break
                    except Exception:
                        continue

        return atoms


# -----------------------------------------------------------------------------
# Benchmark Suite Coordinator
# -----------------------------------------------------------------------------


class BenchmarkCoordinator:
    """Executes benchmark test suites across comparative engines and streams live telemetry with full disk persistence."""

    def __init__(
        self,
        catalog: DatasetCatalog | None = None,
        service: Any | None = None,
        runs_dir: Path | str | None = None,
    ) -> None:
        self.catalog = catalog or DatasetCatalog()
        self.service = service
        self.runs_dir = runs_dir

    async def run_benchmark(
        self,
        run_id: str | None = None,
        *,
        dataset_id: str,
        engine_ids: Sequence[str] = ("trace_hybrid", "pure_vector", "pure_lexical", "naive_rag"),
        max_cases: int | None = None,
        max_atoms: int | None = None,
        workspace_id: str = "default",
    ) -> dict[str, Any]:
        """Execute all test cases across selected engines, emitting live events and persisting manifest."""
        if run_id is None:
            run_id = f"bench-{uuid.uuid4().hex[:12]}"

        test_cases = self.catalog.load_test_cases(dataset_id, limit=max_cases)
        if not test_cases:
            info = self.catalog.get_dataset(dataset_id)
            ds_name = info.name if info else dataset_id
            raise ValueError(
                f"Dataset '{dataset_id}' ({ds_name}) does not have frozen benchmark query judgments. "
                "Ground-truth benchmark evaluation requires a frozen query manifest."
            )

        # Load atoms in memory for pure engines or standalone mode without arbitrary truncation
        atoms = self.catalog.load_atoms_for_dataset(dataset_id, limit=max_atoms)

        # Compute provenance hashes
        corpus_sha256, queries_sha256 = self.catalog.get_dataset_hashes(dataset_id)

        # Instantiate engines
        engines: dict[str, BaseComparativeEngine] = {}
        for eng_id in engine_ids:
            try:
                engines[eng_id] = get_engine(eng_id, service=self.service)
            except Exception:
                continue

        total_evaluations = len(test_cases) * len(engines)

        # Register run in telemetry manager
        telemetry_manager.create_run(
            run_id,
            suite_name=f"Benchmark: {dataset_id}",
            dataset_id=dataset_id,
            engines=list(engines.keys()),
            total_cases=total_evaluations,
            workspace_id=workspace_id,
            corpus_sha256=corpus_sha256,
            queries_sha256=queries_sha256,
            metadata={
                "dataset_id": dataset_id,
                "case_count": len(test_cases),
                "atom_count": len(atoms),
                "workspace_id": workspace_id,
            },
        )

        await telemetry_manager.emit(
            BenchmarkEvent(
                run_id=run_id,
                event_type="run_started",
                data={
                    "suite_name": f"Benchmark: {dataset_id}",
                    "dataset_id": dataset_id,
                    "workspace_id": workspace_id,
                    "engines": list(engines.keys()),
                    "total_cases": total_evaluations,
                    "case_count": len(test_cases),
                    "atom_count": len(atoms),
                    "corpus_sha256": corpus_sha256,
                    "queries_sha256": queries_sha256,
                },
            )
        )

        completed_count = 0

        for case_idx, case in enumerate(test_cases, start=1):
            case_id = case["id"]
            query_text = case["query"]
            gold_ids = set(case.get("gold_atom_version_ids", []))
            out_of_scope = bool(case.get("out_of_scope", False))

            await telemetry_manager.emit(
                BenchmarkEvent(
                    run_id=run_id,
                    event_type="case_started",
                    data={
                        "case_id": case_id,
                        "query": query_text,
                        "case_index": case_idx,
                        "total_cases": len(test_cases),
                    },
                )
            )

            for eng_id, engine in engines.items():
                try:
                    result = await engine.query(
                        query_text,
                        workspace_id=workspace_id,
                        atoms=atoms if getattr(engine, "service", None) is None else None,
                    )

                    retrieved_ids = [h.atom_version_id for h in result.results]
                    cited_ids = [c["atom_version_id"] for c in result.citations if "atom_version_id" in c]

                    # Metrics computed against normalized ground-truth gold IDs
                    recall_5 = calculate_recall_at_k(gold_ids, retrieved_ids, 5)
                    recall_20 = calculate_recall_at_k(gold_ids, retrieved_ids, 20)
                    ndcg_10 = calculate_ndcg_at_k(gold_ids, retrieved_ids, 10)
                    complete_cov = calculate_evidence_coverage(gold_ids, cited_ids)
                    precision = calculate_citation_precision(
                        gold_ids, cited_ids, abstained=result.abstained, out_of_scope=out_of_scope
                    )
                    abstention_correct = calculate_abstention_correctness(result.abstained, out_of_scope)

                    case_record = CaseExecutionResult(
                        case_id=case_id,
                        engine_id=eng_id,
                        query=query_text,
                        kind=case.get("kind", "unspecified"),
                        gold_ids=sorted(gold_ids),
                        retrieved_ids=retrieved_ids,
                        cited_ids=cited_ids,
                        citations=result.citations,
                        recall_at_5=recall_5,
                        recall_at_20=recall_20,
                        ndcg_at_10=ndcg_10,
                        complete_evidence=complete_cov,
                        citation_precision=precision,
                        abstained=result.abstained,
                        out_of_scope=out_of_scope,
                        abstention_correct=abstention_correct,
                        hallucination_detected=result.hallucination_detected,
                        latency_ms=result.latency_ms,
                        token_count=result.token_count,
                        token_cost_usd=result.token_cost_usd,
                        synthesis_preview=result.synthesis[:120] if result.synthesis else None,
                        diagnostics=result.stage_breakdown,
                    )

                    telemetry_manager.record_case(run_id, case_record)
                    completed_count += 1

                    await telemetry_manager.emit(
                        BenchmarkEvent(
                            run_id=run_id,
                            event_type="case_completed",
                            data={
                                "case_id": case_id,
                                "engine_id": eng_id,
                                "result": case_record.model_dump(),
                                "progress": round(completed_count / total_evaluations * 100, 1),
                            },
                        )
                    )

                    await telemetry_manager.emit(
                        BenchmarkEvent(
                            run_id=run_id,
                            event_type="run_progress",
                            data={
                                "progress": round(completed_count / total_evaluations * 100, 1),
                                "completed_cases": completed_count,
                                "total_cases": total_evaluations,
                            },
                        )
                    )

                    running_summary = telemetry_manager.get_run_summary(run_id)
                    await telemetry_manager.emit(
                        BenchmarkEvent(
                            run_id=run_id,
                            event_type="metrics_updated",
                            data={"metrics": running_summary.get("metrics", {}) if running_summary else {}},
                        )
                    )

                except Exception as ex:
                    completed_count += 1
                    # Record failure case
                    case_record = CaseExecutionResult(
                        case_id=case_id,
                        engine_id=eng_id,
                        query=query_text,
                        kind=case.get("kind", "unspecified"),
                        gold_ids=sorted(gold_ids),
                        retrieved_ids=[],
                        cited_ids=[],
                        abstained=True,
                        out_of_scope=out_of_scope,
                        abstention_correct=out_of_scope,
                        diagnostics={"error": str(ex)},
                    )
                    telemetry_manager.record_case(run_id, case_record)

        summary = telemetry_manager.finish_run(run_id, status="completed")

        await telemetry_manager.emit(
            BenchmarkEvent(
                run_id=run_id,
                event_type="run_completed",
                data={"summary": summary},
            )
        )

        return summary or {}

    # Backward-compatible alias
    run_suite = run_benchmark
