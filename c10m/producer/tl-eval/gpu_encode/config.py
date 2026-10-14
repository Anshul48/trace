"""Pinned encoder specification for the TL GPU encode stage.

Authority: handoffs/TL-INGEST-NAVIGATION-ARCHITECTURE-2026-10-05.md
section 3 (Encoding and writes) + section 6 (GPU feasibility row);
freeze pins in handoffs/TL-TRACE-HANDOFF-2026-10-05.md section 1.

The cache key binds exact chunk bytes plus every output-affecting
encoder setting. It deliberately does NOT include atom IDs (their
revision UUIDs are minted later at ingest time).
"""

import hashlib
import json

FORMAT_TAG = "tl-gpu-embcache-v1"

# Pinned model/tokenizer (freeze pin; offline).
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

# Output-affecting encode settings. These MUST match the CPU path
# (tl-eval/run_quality.py emb(): ST defaults, convert_to_numpy,
# normalize_embeddings=False) except device/precision, which get
# distinct run identities (arch section 3).
POOLING = "mean"               # MiniLM-L6-v2 sentence-transformers head
TRUNCATION = True
MAX_SEQ_LENGTH = 256           # MiniLM-L6-v2 default max_seq_length
NORMALIZE_EMBEDDINGS = False   # matches CPU emb(); cosine is downstream
PRECISION_FIRST = "fp32"       # FP32 first; fp16/TF32 are separate variants

# Package pins the GPU run is validated against (recorded, not keyed).
PIN_ST = "2.7.0"
PIN_TORCH = "2.14.0"
PIN_TRANSFORMERS = "4.57.6"
PIN_TOKENIZERS = "0.22.2"
PIN_PYTHON = "3.12.3"


def key_config(precision=PRECISION_FIRST):
    """Canonical output-affecting config dict (the keyed portion)."""
    return {
        "format": FORMAT_TAG,
        "model": MODEL_ID,
        "revision": MODEL_REVISION,
        "pooling": POOLING,
        "truncation": TRUNCATION,
        "max_seq_length": MAX_SEQ_LENGTH,
        "normalize_embeddings": NORMALIZE_EMBEDDINGS,
        "precision": precision,
    }


def canonical_config_json(precision=PRECISION_FIRST):
    return json.dumps(key_config(precision),
                      sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def config_id(precision=PRECISION_FIRST):
    """Short identity for a numeric configuration (run labeling)."""
    h = hashlib.sha256(canonical_config_json(precision).encode("ascii"))
    return h.hexdigest()[:16]


def cache_key(chunk_bytes, precision=PRECISION_FIRST):
    """Embedding cache key: sha256 over keyed config + exact chunk bytes."""
    if not isinstance(chunk_bytes, (bytes, bytearray)):
        raise TypeError("chunk_bytes must be bytes")
    h = hashlib.sha256()
    h.update(FORMAT_TAG.encode("ascii"))
    h.update(b"\x00")
    h.update(canonical_config_json(precision).encode("ascii"))
    h.update(b"\x00")
    h.update(bytes(chunk_bytes))
    return h.hexdigest()
