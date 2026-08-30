"""Shared utilities for Trace scale dataset fetchers and stagers.

Provides standard Phase 1 record serialization, content hashing,
directory management, and streaming helpers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Generator, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default root directory for scale datasets staging
DEFAULT_SCALE_DATA_ROOT = Path(
    os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
) / "trace-scale-data"


def get_default_staging_dir(dataset_name: str) -> Path:
    """Return the default staging directory for a given dataset."""
    dest = DEFAULT_SCALE_DATA_ROOT / dataset_name
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def compute_sha256(content: str | bytes) -> str:
    """Compute sha256 hex digest for string or byte content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def estimate_tokens(text: str) -> int:
    """Estimate token count for a piece of text (roughly 4 chars per token)."""
    if not text:
        return 0
    # Quick heuristic if tiktoken is not directly needed in tight loops
    return max(1, len(text) // 4)


def create_trace_record(
    document_name: str,
    content: str,
    source_uri: str,
    metadata: dict[str, Any] | None = None,
    collection: str = "default",
    record_id: str | None = None,
    media_type: str = "text/plain; charset=utf-8",
) -> dict[str, Any]:
    """Create a normalized Trace Phase 1 record compliant with phase1-record.schema.json."""
    content_hash = compute_sha256(content)
    meta = metadata.copy() if metadata else {}

    # Enrich metadata with standard provenance fields if not present
    if "estimated_tokens" not in meta:
        meta["estimated_tokens"] = estimate_tokens(content)
    if "ingested_at" not in meta:
        meta["ingested_at"] = datetime.now(timezone.utc).isoformat()
    if "char_count" not in meta:
        meta["char_count"] = len(content)

    rec_id = record_id or f"{collection}:{content_hash[:16]}"

    record = {
        "record_id": rec_id,
        "document_name": document_name,
        "source_uri": source_uri,
        "content": content,
        "content_hash": content_hash,
        "metadata": meta,
        "collection": collection,
        "media_type": media_type,
    }
    return record


def write_jsonl_records(
    records: Iterable[dict[str, Any]],
    output_file: Path | str,
    limit: int | None = None,
    verbose: bool = True,
) -> int:
    """Stream records to a JSONL file with count tracking and directory creation."""
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    total_tokens = 0
    total_chars = 0

    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            if limit is not None and count >= limit:
                break
            line = json.dumps(rec, ensure_ascii=False)
            f.write(line + "\n")
            count += 1
            content_len = len(rec.get("content", ""))
            total_chars += content_len
            total_tokens += rec.get("metadata", {}).get("estimated_tokens", max(1, content_len // 4))

            if verbose and count % 1000 == 0:
                print(f"  [Progress] Written {count:,} records ({total_tokens:,} est. tokens)...")

    if verbose:
        print(
            f"  [Complete] Staged {count:,} records to {out_path.resolve()} "
            f"({total_chars:,} chars, ~{total_tokens:,} est. tokens)"
        )

    return count


def clean_text_whitespace(text: str) -> str:
    """Normalize excessive blank lines and clean up whitespace."""
    if not text:
        return ""
    # Normalize windows/mac line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Replace 3 or more consecutive newlines with 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
