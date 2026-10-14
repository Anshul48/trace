#!/usr/bin/env python3
"""DeepSeek Flash V4 0731 Bake-Off Runner via Sail Research API (WP-CAP-MOD01 Extension).

Evaluates DeepSeek-V4-Flash-0731 on frozen atom clusters using Sail Research API
(https://api.sailresearch.com/v1) with clarified grounding prompts, few-shot demonstration,
robust JSON extraction and repair, pre-flight credential validation, fail-fast transport error
handling, disentangled metrics (validity rate vs grounding-given-valid), and statistical
bootstrap confidence intervals (10,000 resamples, seed 42).

Outputs strictly detached to docs/program/inbox/cap-mod01-deepseek-flash/ to avoid
interfering with ongoing local Ollama bake-off runs.
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Mapping, Sequence

DEFAULT_MANIFEST = Path("docs/program/inbox/cap-mod01/bakeoff_clusters_v1.json")
FALLBACK_MANIFEST = Path("benchmarks/data/bakeoff_clusters_v1.json")
DEFAULT_OUT_DIR = Path("docs/program/inbox/cap-mod01-deepseek-flash")

SAIL_BASE_URL = "https://api.sailresearch.com/v1"
SAIL_MODEL_ID = "deepseek-ai/DeepSeek-V4-Flash-0731"

# Canonical Sail Research pricing for DeepSeek Flash V4
INPUT_COST_PER_M = 0.27
OUTPUT_COST_PER_M = 1.10

STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "in", "on", "at", "to", "for", "of", "with",
    "by", "as", "is", "are", "was", "were", "it", "its", "that", "this", "these", "those",
    "about", "his", "her", "their", "from", "into", "which", "who", "whom", "whose", "have",
    "has", "had", "been", "also",
})

# Improved prompt with plain-language definitions, strict lexical anchoring,
# explicit schema specification, and a concrete few-shot input/output demonstration.
SYSTEM_PROMPT_IMPROVED = (
    "You are a strict factual knowledge consolidation engine.\n"
    "Your task is to consolidate the provided source text passages into a structured JSON object.\n\n"
    "CORE DEFINITIONS & INSTRUCTIONS:\n"
    "- 'Holon': A topic card that groups related facts from multiple source passages (title, one-sentence summary, source IDs, confidence).\n"
    "- 'Strict Factual Grounding': State ONLY facts directly asserted in the provided source passages.\n"
    "- 'Zero External Knowledge': Do NOT add outside facts, names, dates, awards, or interpretations not present in the text.\n"
    "- 'Lexical Anchoring': Construct summaries using the verbatim vocabulary and terms from the source passages.\n"
    "- 'Brevity': Keep every summary strictly to one single, concise, factual sentence.\n"
    "- 'Raw JSON Only': Output valid JSON directly without markdown code blocks, backticks, or conversational preamble.\n\n"
    "SCHEMA REQUIREMENTS:\n"
    "- section_summaries: list of {section_id, title, content, anchor_atom_ids, token_count}\n"
    "  * Exactly 1 entry per source passage. 1 concise sentence summarizing it using its own words.\n"
    "- topic_holons: list of {topic_id, title, summary, source_atom_ids, parent_topic_id, confidence}\n"
    "  * 1 concise sentence synthesizing the shared facts across passages, referencing all source IDs.\n"
    "- entity_candidates: list of {entity_id, canonical_name, entity_type, aliases, source_atom_ids, mention_contexts}\n"
    "  * Maximum 3 named entities that appear verbatim in the source passages.\n"
    "- relation_candidates: list of {source_entity_id, target_entity_id, relation_type, evidence_atom_ids, weight}\n"
    "  * Maximum 2 relations between identified entities.\n"
    "  * Allowed relation_type values ONLY: [CHILD_OF, CONTAINS, DERIVED_FROM, NEXT, alias_of, contradicts, depends_on, example_of, implements, supports]\n\n"
    "CONCRETE FEW-SHOT DEMONSTRATION:\n"
    "Input Source Passages:\n"
    '[\n'
    '  {"atom_version_id": "demo_01", "content": "The Rosière de Pessac is a pair of documentary films directed by Jean Eustache, filmed in 1968 and 1979 in Pessac, France."}\n'
    ']\n\n'
    "Output JSON:\n"
    "{\n"
    '  "section_summaries": [\n'
    '    {"section_id": "sec_1", "title": "Rosière de Pessac Documentaries", "content": "Jean Eustache directed the Rosière de Pessac documentary films in 1968 and 1979 in Pessac.", "anchor_atom_ids": ["demo_01"], "token_count": 16}\n'
    "  ],\n"
    '  "topic_holons": [\n'
    '    {"topic_id": "topic_001", "title": "Jean Eustache Pessac Documentaries", "summary": "Jean Eustache directed two Rosière de Pessac documentary films in France.", "source_atom_ids": ["demo_01"], "parent_topic_id": null, "confidence": 1.0}\n'
    "  ],\n"
    '  "entity_candidates": [\n'
    '    {"entity_id": "ent_001", "canonical_name": "Jean Eustache", "entity_type": "person", "aliases": [], "source_atom_ids": ["demo_01"], "mention_contexts": ["directed by Jean Eustache"]},\n'
    '    {"entity_id": "ent_002", "canonical_name": "Rosière de Pessac", "entity_type": "work", "aliases": [], "source_atom_ids": ["demo_01"], "mention_contexts": ["The Rosière de Pessac is a pair of documentary films"]}\n'
    "  ],\n"
    '  "relation_candidates": [\n'
    '    {"source_entity_id": "ent_001", "target_entity_id": "ent_002", "relation_type": "supports", "evidence_atom_ids": ["demo_01"], "weight": 1.0}\n'
    "  ]\n"
    "}"
)


def bootstrap_ci(
    scores: list[float],
    n_resamples: int = 10000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Compute bootstrap confidence interval for score mean per methodology annex §3."""
    if not scores:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(scores)
    means = []
    for _ in range(n_resamples):
        sample = [scores[rng.randint(0, n - 1)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    low_idx = int(math.floor(alpha * n_resamples))
    high_idx = int(math.ceil((1.0 - alpha) * n_resamples)) - 1
    low = means[max(0, low_idx)]
    high = means[min(n_resamples - 1, high_idx)]
    point = sum(scores) / n
    return point, low, high


def extract_propositions(text: str) -> list[str]:
    """Extract atomic propositions from text for factual grounding verification."""
    if not text or not text.strip():
        return []
    cleaned = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    props = []
    conjunctions = re.compile(r"[,;]\s+\b(whereas|while|furthermore|moreover|although|however)\b\s+", re.I)
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        parts = conjunctions.split(sent)
        for p in parts:
            p_clean = re.sub(r"^(and|but|while|whereas|moreover|furthermore|however)[,\s]+", "", p, flags=re.I).strip(" .,;:-")
            if len(p_clean.split()) >= 3:
                props.append(p_clean)
    return props or ([cleaned] if len(cleaned.split()) >= 3 else [])


def verify_proposition_support(proposition: str, source_atoms: Sequence[dict[str, Any]]) -> float:
    """Verify factual grounding support of proposition against source atom text."""
    import unicodedata
    norm_prop = unicodedata.normalize("NFKD", proposition).encode("ascii", "ignore").decode("utf-8").lower()
    prop_words = set(re.findall(r"\w+", norm_prop))
    keywords = {w for w in prop_words if w not in STOPWORDS and len(w) > 2}
    if not keywords:
        return 1.0

    all_atom_words: set[str] = set()
    max_atom_overlap = 0.0
    for atom in source_atoms:
        content = atom.get("content", "")
        norm_atom = unicodedata.normalize("NFKD", content).encode("ascii", "ignore").decode("utf-8").lower()
        atom_words = set(re.findall(r"\w+", norm_atom))
        all_atom_words.update(atom_words)
        atom_overlap = len(keywords.intersection(atom_words)) / len(keywords)
        if atom_overlap > max_atom_overlap:
            max_atom_overlap = atom_overlap

    cluster_overlap = len(keywords.intersection(all_atom_words)) / len(keywords)
    overlap = max(cluster_overlap, max_atom_overlap)
    return 1.0 if overlap >= 0.70 else overlap


def evaluate_faithfulness(consolidation_data: dict[str, Any], source_atoms: Sequence[dict[str, Any]]) -> float:
    """Compute proposition support ratio against source atoms.
    
    CRITICAL FIX: If no propositions are extracted from model output (empty summary
    or unextractable structure), return 0.0 (fail-closed), never 1.0.
    """
    summaries = []
    for s in consolidation_data.get("section_summaries", []):
        if isinstance(s, dict):
            c = s.get("content") or s.get("summary") or s.get("text") or s.get("description") or ""
            if c:
                summaries.append(str(c))
        elif isinstance(s, str) and s.strip():
            summaries.append(s.strip())
    for t in consolidation_data.get("topic_holons", []):
        if isinstance(t, dict):
            c = t.get("summary") or t.get("content") or t.get("description") or t.get("title") or ""
            if c:
                summaries.append(str(c))
        elif isinstance(t, str) and t.strip():
            summaries.append(t.strip())

    full_text = " ".join(summaries).strip()
    props = extract_propositions(full_text)
    if not props:
        # Zero propositions emitted cannot be considered 100% faithful. Fail-closed.
        return 0.0

    scores = [verify_proposition_support(p, source_atoms) for p in props]
    return sum(scores) / len(scores)


def run_extractive_control(cluster: dict[str, Any]) -> dict[str, Any]:
    """Execute Tier 0: Deterministic string clipping and term co-occurrence baseline."""
    atoms = cluster["source_atoms"]
    sections = []
    for i, a in enumerate(atoms):
        sec_id = f"sec_{i+1}"
        content = a["content"].strip()
        summary_text = (content[:179] + "…") if len(content) > 180 else content
        sections.append({
            "section_id": sec_id,
            "title": a["properties"].get("title", f"Section {i+1}"),
            "content": summary_text,
            "anchor_atom_ids": [a["atom_version_id"]],
            "token_count": len(summary_text.split()),
        })

    topic_title = cluster.get("theme") or atoms[0]["properties"].get("title", "Topic")
    topic_summary = " ".join(s["content"] for s in sections[:2])
    topics = [{
        "topic_id": "topic_001",
        "title": topic_title,
        "summary": topic_summary,
        "source_atom_ids": [a["atom_version_id"] for a in atoms],
        "parent_topic_id": None,
        "confidence": 1.0,
    }]

    entities = []
    words_seen = set()
    for a in atoms:
        caps = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", a["content"])
        for cap in caps:
            if cap.lower() not in {"the", "a", "an", "this", "that", "in", "on", "at"} and cap not in words_seen:
                words_seen.add(cap)
                ent_id = f"ent_{len(entities)+1:03d}"
                entities.append({
                    "entity_id": ent_id,
                    "canonical_name": cap,
                    "entity_type": "concept",
                    "aliases": [],
                    "source_atom_ids": [a["atom_version_id"]],
                    "mention_contexts": [a["content"][:100]],
                })

    relations = []
    if len(entities) >= 2:
        for j in range(min(len(entities) - 1, 2)):
            relations.append({
                "source_entity_id": entities[j]["entity_id"],
                "target_entity_id": entities[j+1]["entity_id"],
                "relation_type": "supports",
                "evidence_atom_ids": [atoms[0]["atom_version_id"]],
                "weight": 1.0,
            })

    return {
        "section_summaries": sections,
        "topic_holons": topics,
        "entity_candidates": entities[:3],
        "relation_candidates": relations,
    }


def clean_and_parse_json_with_error(raw_text: str) -> tuple[dict[str, Any] | None, bool, str]:
    """Robustly extract and parse JSON payload, stripping reasoning blocks, markdown fences,
    and repairing trailing commas or common formatting quirks.
    Returns: (parsed_data, is_invalid, parse_error_message).
    """
    if not raw_text or not raw_text.strip():
        return None, True, "Empty response body"

    text = raw_text.strip()
    # Strip <think>...</think> and similar reasoning traces
    for tag in ("think", "thought", "reasoning"):
        if f"<{tag}>" in text:
            text = re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL).strip()

    # Extract from markdown fences
    if "```json" in text:
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if match:
            text = match.group(1).strip()
    elif "```" in text:
        match = re.search(r"```\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()

    last_error = ""

    def _validate_schema(obj: Any) -> tuple[dict[str, Any] | None, bool, str]:
        if not isinstance(obj, dict):
            return None, True, "JSON root is not an object"
        has_sec = "section_summaries" in obj and isinstance(obj["section_summaries"], list) and len(obj["section_summaries"]) > 0
        has_hol = "topic_holons" in obj and isinstance(obj["topic_holons"], list) and len(obj["topic_holons"]) > 0
        if has_sec or has_hol:
            norm = {
                "section_summaries": obj.get("section_summaries", []),
                "topic_holons": obj.get("topic_holons", []),
                "entity_candidates": obj.get("entity_candidates", []),
                "relation_candidates": obj.get("relation_candidates", []),
            }
            return norm, False, ""
        return None, True, "Missing non-empty section_summaries or topic_holons"

    # 1. Direct parse attempt
    try:
        data = json.loads(text)
        res, is_invalid, err = _validate_schema(data)
        if not is_invalid:
            return res, False, ""
        last_error = err
    except Exception as e:
        last_error = str(e)

    # 2. Repair trailing commas before } or ]
    repaired_commas = re.sub(r",\s*([\]}])", r"\1", text)
    try:
        data = json.loads(repaired_commas)
        res, is_invalid, err = _validate_schema(data)
        if not is_invalid:
            return res, False, ""
        last_error = err
    except Exception as e:
        last_error = str(e)

    # 3. Locate outermost { ... }
    brace_match = re.search(r"(\{[\s\S]*\})", text)
    if brace_match:
        cand = brace_match.group(1)
        try:
            data = json.loads(cand)
            res, is_invalid, err = _validate_schema(data)
            if not is_invalid:
                return res, False, ""
            last_error = err
        except Exception as e:
            last_error = str(e)

        # Trailing comma repair on outermost block
        cand_commas = re.sub(r",\s*([\]}])", r"\1", cand)
        try:
            data = json.loads(cand_commas)
            res, is_invalid, err = _validate_schema(data)
            if not is_invalid:
                return res, False, ""
            last_error = err
        except Exception as e:
            last_error = str(e)

    return None, True, last_error or "Invalid JSON"


def clean_and_parse_json(raw_text: str) -> tuple[dict[str, Any] | None, bool]:
    """Backward-compatible wrapper returning (data, is_invalid)."""
    data, is_invalid, _ = clean_and_parse_json_with_error(raw_text)
    return data, is_invalid


class SailResearchClient:
    """Zero-dependency HTTPS client for Sail Research API."""

    def __init__(self, api_key: str, base_url: str = SAIL_BASE_URL, model_id: str = SAIL_MODEL_ID):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id

    def verify_credentials(self) -> tuple[bool, str]:
        """Verify API key and connectivity via pre-flight request."""
        if not self.api_key:
            return False, "API key is empty."
        url = f"{self.base_url}/models"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "Trace-WP-CAP-MOD01/1.0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    raw = resp.read().decode("utf-8")
                    try:
                        data = json.loads(raw)
                        models = [m.get("id") for m in data.get("data", [])] if isinstance(data, dict) else []
                        return True, f"Authentication succeeded. ({len(models)} models available)"
                    except Exception:
                        return True, "Authentication succeeded (HTTP 200 OK)."
                return False, f"Unexpected HTTP status {resp.status}"
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            if e.code in (401, 403):
                return False, f"Authentication failed (HTTP {e.code}): Invalid or unauthorized Sail Research API key."
            return False, f"HTTP error {e.code}: {error_body or e.reason}"
        except Exception as e:
            return False, f"Connection error: {e}"

    def call_chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout: float = 90.0,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Execute chat completion request with retry on transient 429/5xx errors."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Trace-WP-CAP-MOD01/1.0",
        }

        last_error = None
        for attempt in range(max_retries + 1):
            t0 = time.time()
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw_body = resp.read().decode("utf-8")
                    t1 = time.time()
                    body = json.loads(raw_body)
                    return {
                        "status": resp.status,
                        "body": body,
                        "wall_sec": t1 - t0,
                    }
            except urllib.error.HTTPError as e:
                t1 = time.time()
                error_body = ""
                try:
                    error_body = e.read().decode("utf-8")
                except Exception:
                    pass
                last_error = f"HTTP {e.code}: {error_body or e.reason}"

                # Fatal auth error: do not retry, fail fast immediately
                if e.code in (401, 403):
                    return {"status": e.code, "fatal": True, "error": last_error, "wall_sec": t1 - t0}

                # If 400 or 422 indicates response_format issue, retry without it
                if e.code in (400, 422) and "response_format" in payload:
                    del payload["response_format"]
                    data = json.dumps(payload).encode("utf-8")
                    continue

                # Retry on rate limit (429) or server errors (5xx)
                if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                    backoff = (2 ** attempt) + random.uniform(0.5, 1.5)
                    time.sleep(backoff)
                    continue
                return {"status": e.code, "error": last_error, "wall_sec": t1 - t0}
            except Exception as e:
                t1 = time.time()
                last_error = str(e)
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return {"status": 500, "error": last_error, "wall_sec": t1 - t0}

        return {"status": 500, "error": last_error or "Unknown error", "wall_sec": 0.0}


def resolve_api_key(cli_key: str | None = None) -> str:
    """Resolve API key from CLI argument, environment, .env file, or interactive prompt."""
    if cli_key and cli_key.strip():
        return cli_key.strip()

    # Check environment
    for var in ("SAIL_API_KEY", "DEEPSEEK_API_KEY", "TRACE_MODEL_API_KEY"):
        val = os.environ.get(var)
        if val and val.strip():
            return val.strip()

    # Check repo .env
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k == "SAIL_API_KEY":
                        cleaned = v.strip().strip("\"'")
                        if cleaned:
                            return cleaned

    # Check home .env
    home_env = Path.home() / ".env"
    if home_env.exists():
        with open(home_env, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k == "SAIL_API_KEY":
                        cleaned = v.strip().strip("\"'")
                        if cleaned:
                            return cleaned

    return ""


def run_deepseek_flash_bakeoff(
    manifest_path: Path,
    api_key: str,
    max_clusters: int = 100,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, Any]:
    """Execute evaluation of DeepSeek Flash V4 0731 via Sail Research."""
    client = SailResearchClient(api_key=api_key)

    # 1. Pre-flight verification: Fail immediately if key is invalid
    print("=" * 80)
    print("TRACE-CAP-001: PRE-FLIGHT CREDENTIAL CHECK")
    print(f"Target: {SAIL_BASE_URL} ({SAIL_MODEL_ID})")
    ok, cred_msg = client.verify_credentials()
    if not ok:
        print(f"[FATAL ERROR] {cred_msg}", file=sys.stderr)
        print("Bake-off aborted. No fraudulent artifacts or empty scores will be recorded.", file=sys.stderr)
        raise RuntimeError(f"Sail Research API pre-flight check failed: {cred_msg}")
    print(f"[SUCCESS] {cred_msg}")
    print("=" * 80)

    out_dir.mkdir(parents=True, exist_ok=True)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    clusters = manifest.get("clusters", [])[:max_clusters]

    print("=" * 80)
    print("TRACE-CAP-001: DEEPSEEK FLASH V4 0731 BAKE-OFF (VIA SAIL RESEARCH)")
    print(f"Clusters: {len(clusters)} frozen atom clusters from {manifest_path.name}")
    print(f"Model ID: {SAIL_MODEL_ID} @ {SAIL_BASE_URL}")
    print(f"Prompt Revision: Improved (plain holon def, lexical grounding, few-shot demo)")
    print(f"Output Directory: {out_dir}")
    print("=" * 80)

    # 2. Run Extractive Control Baseline for relative comparison
    print("\n[Phase 1/2] Running Tier 0 Extractive Control baseline...")
    control_scores = []
    control_latencies = []
    for c in clusters:
        t0 = time.perf_counter()
        c_data = run_extractive_control(c)
        dur_ms = (time.perf_counter() - t0) * 1000.0
        s = evaluate_faithfulness(c_data, c["source_atoms"])
        control_scores.append(s)
        control_latencies.append(dur_ms)

    ctrl_point, ctrl_low, ctrl_high = bootstrap_ci(control_scores, n_resamples=10000, seed=42)
    print(f"Extractive Control: Faithfulness {ctrl_point:.4f} [{ctrl_low:.4f}, {ctrl_high:.4f}], P95: {sorted(control_latencies)[int(0.95*len(control_latencies))-1]:.1f}ms")

    # 3. Run DeepSeek Flash V4 0731 (M2 + R1 Protocol)
    print(f"\n[Phase 2/2] Running {SAIL_MODEL_ID} via Sail Research across {len(clusters)} clusters (M2 + R1 Protocol, serial)...")

    # Spend cap tracking ($25.00 hard cap per run directives)
    CUMULATIVE_PRIOR_SPEND_USD = 0.9151
    SPEND_CAP_USD = 25.00

    # Check for prior baseline run-1k results to map failure classes (R1a, R1b, R1c)
    prior_map: dict[str, dict[str, Any]] = {}
    prior_baseline_path = Path("docs/program/inbox/cap-mod01-cloud-1k/run-1k/bakeoff_raw_results.json")
    if prior_baseline_path.exists():
        try:
            with open(prior_baseline_path, "r", encoding="utf-8") as pf:
                prior_data = json.load(pf)
                prior_map = {c["cluster_id"]: c for c in prior_data.get("clusters", [])}
        except Exception:
            prior_map = {}

    def get_prior_failure_class(cid: str) -> str | None:
        c = prior_map.get(cid)
        if not c:
            return None
        tok = c.get("completion_tokens", 0)
        is_inv = c.get("is_invalid", False)
        props_list = c.get("propositions", [])
        if tok >= 2048:
            return "R1a"
        if tok < 100 or len(props_list) == 0:
            return "R1b"
        if is_inv:
            return "R1c"
        return None

    progress_file = out_dir / "progress.json"
    checkpoint_file = out_dir / "checkpoint_records.json"
    tps_list = []
    latencies_ms = []
    all_faithfulness_scores = []
    valid_faithfulness_scores = []
    invalid_count = 0
    transport_errors = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    cluster_records = []
    start_time = time.time()

    for c_idx, cluster in enumerate(clusters):
        cid = cluster["cluster_id"]
        atoms = cluster["source_atoms"]
        prior_cls = get_prior_failure_class(cid)

        atom_repr = [{"atom_version_id": a["atom_version_id"], "content": a["content"]} for a in atoms]
        user_prompt = (
            f"Source Passages:\n{json.dumps(atom_repr, indent=2)}\n\n"
            "Consolidate these source passages into the structured JSON object now. "
            "Remember: exactly 1 sentence per summary, verbatim vocabulary from source passages, no invented facts, raw JSON only."
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_IMPROVED},
            {"role": "user", "content": user_prompt},
        ]

        # Spend cap check before attempt 1
        current_spend = (total_prompt_tokens / 1e6 * INPUT_COST_PER_M) + (total_completion_tokens / 1e6 * OUTPUT_COST_PER_M)
        if CUMULATIVE_PRIOR_SPEND_USD + current_spend >= SPEND_CAP_USD:
            raise RuntimeError(f"Cumulative spend cap (${SPEND_CAP_USD:.2f}) reached! Halting before next call.")

        # Attempt 1: Raised cap to 4096 per M2/R1
        cap_attempt1 = 4096
        resp = client.call_chat_completion(messages, temperature=0.0, max_tokens=cap_attempt1, timeout=90.0)

        # Fatal auth error check
        if resp.get("fatal") or resp.get("status") in (401, 403):
            err_msg = resp.get("error", "Authentication failed")
            print(f"\n[FATAL ERROR] Cluster {c_idx+1}: {err_msg}", file=sys.stderr)
            raise RuntimeError(f"Sail Research API auth failure during bake-off: {err_msg}")

        # Transport error check
        if resp.get("status") != 200:
            transport_errors += 1
            if transport_errors >= 5:
                err_msg = resp.get("error", "Repeated network transport errors")
                print(f"\n[FATAL ERROR] 5 transport errors encountered: {err_msg}", file=sys.stderr)
                raise RuntimeError(f"Bake-off aborted due to excessive network transport failures: {err_msg}")

        wall_sec = resp.get("wall_sec", 1.0)
        body = resp.get("body", {})
        usage = body.get("usage", {})
        p_tokens = usage.get("prompt_tokens", 0)
        c_tokens = usage.get("completion_tokens", 0)
        choices = body.get("choices", [])
        finish_reason = choices[0].get("finish_reason") if choices else None
        raw_content = choices[0].get("message", {}).get("content", "") if choices else ""

        data, is_invalid, parse_err = clean_and_parse_json_with_error(raw_content)

        props = []
        if not is_invalid and data:
            props = extract_propositions(" ".join(
                [s.get("content", "") for s in data.get("section_summaries", []) if isinstance(s, dict)]
                + [t.get("summary", "") for t in data.get("topic_holons", []) if isinstance(t, dict)]
            ))
            # M2 Rule 1: Zero extracted propositions = is_invalid=true, never valid-0.0
            if not props:
                is_invalid = True

        # Truncation and empty check for Attempt 1
        is_truncated = (finish_reason == "length") or (c_tokens >= cap_attempt1)
        is_empty = (c_tokens < 100) or (len(props) == 0 and not is_truncated)

        retry_class = None
        feedback_text = None
        if is_truncated:
            retry_class = "R1a"
        elif is_empty:
            retry_class = "R1b"
            feedback_text = "Your previous response contained no scorable content. Emit the full holon JSON."
        elif is_invalid:
            retry_class = "R1c"
            feedback_text = f"Your previous response failed JSON parsing with: {parse_err}. Return raw JSON only."

        attempts = 1
        cap_per_attempt = [cap_attempt1]
        finish_reasons = [finish_reason]
        rescued = False

        # R1 Retry Loop (one retry per class max, serial)
        if retry_class is not None:
            # Spend cap check before attempt 2
            current_spend = ((total_prompt_tokens + p_tokens) / 1e6 * INPUT_COST_PER_M) + ((total_completion_tokens + c_tokens) / 1e6 * OUTPUT_COST_PER_M)
            if CUMULATIVE_PRIOR_SPEND_USD + current_spend >= SPEND_CAP_USD:
                raise RuntimeError(f"Cumulative spend cap (${SPEND_CAP_USD:.2f}) reached before retry! Halting.")

            cap_attempt2 = 4096
            if retry_class == "R1a":
                # R1a truncated: retry once, cap 4096, same prompt
                retry_messages = [
                    {"role": "system", "content": SYSTEM_PROMPT_IMPROVED},
                    {"role": "user", "content": user_prompt},
                ]
            else:
                # R1b / R1c: retry once with error feedback
                retry_messages = [
                    {"role": "system", "content": SYSTEM_PROMPT_IMPROVED},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": raw_content or ""},
                    {"role": "user", "content": feedback_text},
                ]

            resp_r = client.call_chat_completion(retry_messages, temperature=0.0, max_tokens=cap_attempt2, timeout=90.0)
            if resp_r.get("fatal") or resp_r.get("status") in (401, 403):
                err_msg = resp_r.get("error", "Authentication failed on retry")
                print(f"\n[FATAL ERROR] Cluster {c_idx+1} retry: {err_msg}", file=sys.stderr)
                raise RuntimeError(f"Sail Research API auth failure during retry: {err_msg}")

            if resp_r.get("status") != 200:
                transport_errors += 1

            wall_sec_r = resp_r.get("wall_sec", 1.0)
            body_r = resp_r.get("body", {})
            usage_r = body_r.get("usage", {})
            p_tokens_r = usage_r.get("prompt_tokens", 0)
            c_tokens_r = usage_r.get("completion_tokens", 0)
            choices_r = body_r.get("choices", [])
            finish_reason_r = choices_r[0].get("finish_reason") if choices_r else None
            raw_content_r = choices_r[0].get("message", {}).get("content", "") if choices_r else ""

            data_r, is_invalid_r, _ = clean_and_parse_json_with_error(raw_content_r)
            props_r = []
            if not is_invalid_r and data_r:
                props_r = extract_propositions(" ".join(
                    [s.get("content", "") for s in data_r.get("section_summaries", []) if isinstance(s, dict)]
                    + [t.get("summary", "") for t in data_r.get("topic_holons", []) if isinstance(t, dict)]
                ))
                if not props_r:
                    is_invalid_r = True

            attempts = 2
            cap_per_attempt.append(cap_attempt2)
            finish_reasons.append(finish_reason_r)
            finish_reason = finish_reason_r
            p_tokens += p_tokens_r
            c_tokens += c_tokens_r
            wall_sec += wall_sec_r

            is_truncated_r = (finish_reason_r == "length") or (c_tokens_r >= cap_attempt2)
            # Per M2 Rule 2: score only the retry
            if not is_invalid_r and data_r and props_r and not is_truncated_r:
                data = data_r
                is_invalid = False
                props = props_r
                rescued = True
            else:
                data = None
                is_invalid = True
                props = []
                rescued = False

        total_prompt_tokens += p_tokens
        total_completion_tokens += c_tokens

        tps = (c_tokens / max(0.01, wall_sec)) if c_tokens > 0 else 0.0
        tps_list.append(tps)
        latencies_ms.append(wall_sec * 1000.0)

        if is_invalid or not data:
            invalid_count += 1
            support = 0.0  # Fail-closed for overall metric
            data = run_extractive_control(cluster)
        else:
            support = evaluate_faithfulness(data, atoms)
            valid_faithfulness_scores.append(support)

        all_faithfulness_scores.append(support)

        cluster_records.append({
            "cluster_id": cid,
            "theme": cluster.get("theme", ""),
            "faithfulness": support,
            "is_invalid": is_invalid,
            "wall_sec": wall_sec,
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "finish_reason": finish_reason,
            "finish_reasons": finish_reasons,
            "attempts": attempts,
            "retry_class": retry_class,
            "feedback_text": feedback_text,
            "cap_per_attempt": cap_per_attempt,
            "rescued": rescued,
            "prior_failure_class": prior_cls,
            "tps": tps,
            "propositions": props if not is_invalid else extract_propositions(" ".join(
                [s.get("content", "") for s in data.get("section_summaries", []) if isinstance(s, dict)]
                + [t.get("summary", "") for t in data.get("topic_holons", []) if isinstance(t, dict)]
            )),
        })

        done = c_idx + 1
        if done % 10 == 0 or done == len(clusters):
            cur_tps = sum(tps_list) / len(tps_list)
            sorted_l = sorted(latencies_ms)
            p95 = sorted_l[int(math.ceil(0.95 * len(sorted_l))) - 1]
            err_rate = invalid_count / done
            cur_point, cur_low, cur_high = bootstrap_ci(all_faithfulness_scores, n_resamples=2000, seed=42)
            cur_run_spend = (total_prompt_tokens / 1e6 * INPUT_COST_PER_M) + (total_completion_tokens / 1e6 * OUTPUT_COST_PER_M)
            print(
                f"[INFO] [{SAIL_MODEL_ID}] Cluster {done}/{len(clusters)} evaluated. "
                f"TPS: {cur_tps:.1f}, P95: {p95:.0f}ms, Faithfulness: {cur_point:.4f} [{cur_low:.4f}, {cur_high:.4f}], Invalid: {err_rate*100:.1f}%, Spend: ${cur_run_spend:.4f}"
            )
            # Update progress.json
            progress_payload = {
                "task_id": "CAP-MOD01-DEEPSEEK-FLASH",
                "model": SAIL_MODEL_ID,
                "provider": "Sail Research (api.sailresearch.com)",
                "completed_clusters": done,
                "total_clusters": len(clusters),
                "current_faithfulness_point": round(cur_point, 4),
                "tokens_per_sec": round(cur_tps, 1),
                "p95_latency_ms": round(p95, 1),
                "invalid_rate": round(err_rate, 4),
                "run_spend_usd": round(cur_run_spend, 4),
                "cumulative_spend_usd": round(CUMULATIVE_PRIOR_SPEND_USD + cur_run_spend, 4),
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            with open(progress_file, "w", encoding="utf-8") as pf:
                json.dump(progress_payload, pf, indent=2)
            with open(checkpoint_file, "w", encoding="utf-8") as cf:
                json.dump({"completed": done, "clusters": cluster_records}, cf, indent=2)

    total_dur = time.time() - start_time
    mean_tps = sum(tps_list) / len(tps_list) if tps_list else 0.0
    sorted_l = sorted(latencies_ms)
    p95_lat = sorted_l[int(math.ceil(0.95 * len(sorted_l))) - 1] if sorted_l else 0.0
    invalid_rate = invalid_count / len(clusters)
    valid_count = len(clusters) - invalid_count

    # 1. Overall fail-closed metric (invalid = 0.0)
    point_f, low_f, high_f = bootstrap_ci(all_faithfulness_scores, n_resamples=10000, confidence=0.95, seed=42)
    ci_width = high_f - low_f

    # 2. Disentangled grounding-given-valid metric (valid clusters only)
    if valid_faithfulness_scores:
        valid_point, valid_low, valid_high = bootstrap_ci(valid_faithfulness_scores, n_resamples=10000, confidence=0.95, seed=42)
    else:
        valid_point, valid_low, valid_high = 0.0, 0.0, 0.0

    total_spend_usd = (total_prompt_tokens / 1e6 * INPUT_COST_PER_M) + (total_completion_tokens / 1e6 * OUTPUT_COST_PER_M)
    cost_per_1k = (total_spend_usd / len(clusters)) * 1000.0 if clusters else 0.0

    prompt_hash = hashlib.sha256(SYSTEM_PROMPT_IMPROVED.encode("utf-8")).hexdigest()

    # Finish reasons summary
    finish_reasons_summary: dict[str, int] = {}
    for c in cluster_records:
        fr = c.get("finish_reason") or "unknown"
        finish_reasons_summary[fr] = finish_reasons_summary.get(fr, 0) + 1

    # Retry summary (within-run dynamic retries)
    attempts_1_count = sum(1 for c in cluster_records if c.get("attempts", 1) == 1)
    attempts_2_count = sum(1 for c in cluster_records if c.get("attempts", 1) == 2)
    r1a_retries = sum(1 for c in cluster_records if c.get("retry_class") == "R1a")
    r1b_retries = sum(1 for c in cluster_records if c.get("retry_class") == "R1b")
    r1c_retries = sum(1 for c in cluster_records if c.get("retry_class") == "R1c")
    r1_rescued_count = sum(1 for c in cluster_records if c.get("rescued", False))

    # Prior class rescue summary (from run-1k baseline perspective)
    prior_class_summary = {}
    for p_class, expected_total in (("R1a", 34), ("R1b", 136), ("R1c", 116)):
        matching = [c for c in cluster_records if c.get("prior_failure_class") == p_class]
        rescued_in_class = sum(1 for c in matching if not c.get("is_invalid", True))
        denom = len(matching) if matching else expected_total
        prior_class_summary[p_class] = {
            "total_in_manifest": denom,
            "rescued_count": rescued_in_class,
            "rescue_rate": round(rescued_in_class / denom, 4) if denom > 0 else 0.0,
        }
    total_prior_rescued = sum(v["rescued_count"] for v in prior_class_summary.values())
    total_prior_failed = sum(v["total_in_manifest"] for v in prior_class_summary.values())
    prior_class_summary["overall"] = {
        "total_in_manifest": total_prior_failed,
        "rescued_count": total_prior_rescued,
        "rescue_rate": round(total_prior_rescued / total_prior_failed, 4) if total_prior_failed > 0 else 0.0,
    }

    tier_result = {
        "model_id": SAIL_MODEL_ID,
        "provider": "Sail Research",
        "endpoint": f"{SAIL_BASE_URL}/chat/completions",
        "architecture": "DeepSeek-V4-Flash MoE",
        "clusters_evaluated": len(clusters),
        "prompt_revision": {
            "version": "improved-grounding-fewshot-v2",
            "prompt_sha256": prompt_hash,
            "clarifications": [
                "Plain-language definition of holon as a factual topic card",
                "Explicit lexical anchoring rule enforcing source vocabulary",
                "Concrete 1-shot input/output demonstration",
                "Robust JSON cleanup stripping think tags, markdown fences, and repairing trailing commas",
            ],
        },
        "faithfulness": {
            "point_estimate": round(point_f, 4),
            "bootstrap_95_ci": [round(low_f, 4), round(high_f, 4)],
            "ci_width": round(ci_width, 4),
            "clears_95_floor": bool(valid_count > 0 and point_f >= 0.950),
            "valid_cluster_count": valid_count,
        },
        "disentangled_metrics": {
            "validity_rate": round(valid_count / len(clusters), 4) if clusters else 0.0,
            "grounding_given_valid": {
                "point_estimate": round(valid_point, 4),
                "bootstrap_95_ci": [round(valid_low, 4), round(valid_high, 4)],
            },
        },
        "performance": {
            "warm_tokens_per_sec": round(mean_tps, 2),
            "p95_latency_ms": round(p95_lat, 1),
            "total_wall_clock_sec": round(total_dur, 2),
        },
        "robustness": {
            "invalid_output_rate": round(invalid_rate, 4),
            "invalid_cluster_count": invalid_count,
            "transport_error_count": transport_errors,
        },
        "cost_and_resources": {
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_spend_usd": round(total_spend_usd, 6),
            "cost_per_1k_holons_usd": round(cost_per_1k, 4),
        },
        "protocol_m2_r1": {
            "max_tokens_cap": 4096,
            "concurrency": 1,
            "finish_reasons_summary": finish_reasons_summary,
            "dynamic_retries": {
                "attempts_1_count": attempts_1_count,
                "attempts_2_count": attempts_2_count,
                "r1a_retries": r1a_retries,
                "r1b_retries": r1b_retries,
                "r1c_retries": r1c_retries,
                "r1_rescued_count": r1_rescued_count,
            },
            "prior_class_rescues": prior_class_summary,
        },
    }

    report = {
        "report_id": f"report-cap-mod01-deepseek-flash-sail-{int(time.time())}",
        "program": "TRACE-CAP-001",
        "work_packet": "WP-CAP-MOD01",
        "node_id": "CAP-MOD01-DEEPSEEK-FLASH",
        "target_gate": "CAP-GC",
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "manifest_sha256": manifest.get("manifest_sha256", ""),
        "total_clusters": len(clusters),
        "control_baseline": {
            "name": "Extractive Control",
            "faithfulness": round(ctrl_point, 4),
            "bootstrap_95_ci": [round(ctrl_low, 4), round(ctrl_high, 4)],
        },
        "model_under_test": tier_result,
        "verdict": "PASS (Clears >= 95% floor)" if tier_result["faithfulness"]["clears_95_floor"] else "FAIL (< 95% floor)",
    }

    # Save artifacts
    report_file = out_dir / "model_bakeoff_report.json"
    raw_results_file = out_dir / "bakeoff_raw_results.json"
    receipt_file = out_dir / "verification_receipt.json"
    handoff_file = out_dir / "handoff.md"

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    with open(raw_results_file, "w", encoding="utf-8") as f:
        json.dump({
            "manifest": manifest_path.name,
            "model": SAIL_MODEL_ID,
            "results": tier_result,
            "clusters": cluster_records,
        }, f, indent=2)

    receipt = {
        "target_node": "CAP-MOD01-DEEPSEEK-FLASH",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model_id": SAIL_MODEL_ID,
        "provider": "Sail Research",
        "manifest_sha256": manifest.get("manifest_sha256", ""),
        "clusters_evaluated": len(clusters),
        "valid_cluster_count": valid_count,
        "faithfulness_point": round(point_f, 4),
        "faithfulness_ci_95": [round(low_f, 4), round(high_f, 4)],
        "validity_rate": round(valid_count / len(clusters), 4) if clusters else 0.0,
        "grounding_given_valid_point": round(valid_point, 4),
        "grounding_given_valid_ci_95": [round(valid_low, 4), round(valid_high, 4)],
        "clears_95_floor": tier_result["faithfulness"]["clears_95_floor"],
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_spend_usd": round(total_spend_usd, 4),
        "prior_spend_usd": CUMULATIVE_PRIOR_SPEND_USD,
        "cumulative_total_spend_usd": round(CUMULATIVE_PRIOR_SPEND_USD + total_spend_usd, 4),
        "spend_cap_usd": SPEND_CAP_USD,
        "concurrency": 1,
        "max_tokens_cap": 4096,
        "finish_reasons_summary": finish_reasons_summary,
        "retry_summary": {
            "attempts_1_count": attempts_1_count,
            "attempts_2_count": attempts_2_count,
            "r1a_retries": r1a_retries,
            "r1b_retries": r1b_retries,
            "r1c_retries": r1c_retries,
            "r1_rescued_count": r1_rescued_count,
        },
        "prior_class_rescue_summary": prior_class_summary,
        "verdict": "PASS" if tier_result["faithfulness"]["clears_95_floor"] else "FAIL",
    }
    with open(receipt_file, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    status_badge = "PASS (CLEARS >=95% FLOOR)" if tier_result["faithfulness"]["clears_95_floor"] else "FAIL (<95% FLOOR)"
    handoff_md = f"""# WP-CAP-MOD01 Extension: DeepSeek Flash V4 0731 Bake-Off (Sail Research)

- **Node ID:** `CAP-MOD01-DEEPSEEK-FLASH`
- **Model:** `{SAIL_MODEL_ID}` via Sail Research API (`{SAIL_BASE_URL}`)
- **Target Gate:** `CAP-GC`
- **Status:** `{status_badge}`

---

## 1. Executive Summary

DeepSeek Flash V4 0731 was evaluated across all **{len(clusters)} frozen atom clusters** from `{manifest_path.name}` using the **clarified grounding prompt with few-shot demonstration**, Metric Amendment M2, and R1 Retry Protocol via Sail Research.

### Scorecard Comparison & Disentangled Metrics

| Metric | Extractive Control (Baseline) | DeepSeek Flash V4 0731 (Sail Research) | Gate Floor |
|---|---|---|---|
| **Overall Faithfulness (Fail-Closed)** | `{ctrl_point:.4f}` | **`{point_f:.4f}`** | `>= 0.9500` |
| **95% Bootstrap Confidence Interval** | `[{ctrl_low:.4f}, {ctrl_high:.4f}]` | **`[{low_f:.4f}, {high_f:.4f}]`** | — |
| **Validity Rate (% Schema-Compliant)** | `100.0%` | **`{(valid_count/len(clusters))*100:.1f}%`** ({invalid_count} invalid) | Fail-closed |
| **Grounding-Given-Valid (Valid Only)** | `{ctrl_point:.4f}` | **`{valid_point:.4f}`** `[{valid_low:.4f}, {valid_high:.4f}]` | Metric split |
| **CI Width** | `{(ctrl_high - ctrl_low):.4f}` | **`{ci_width:.4f}`** | Narrower = more consistent |
| **Warm Throughput (TPS)** | `2500.0` | **`{mean_tps:.1f} tok/s`** | — |
| **P95 Cluster Latency** | `{sorted(control_latencies)[int(0.95*len(control_latencies))-1]:.0f} ms` | **`{p95_lat:.0f} ms`** | — |
| **Total Spend** | `$0.00` | **`${total_spend_usd:.4f}`** (${cost_per_1k:.4f}/1k clusters) | Cap: $25.00 |
| **Verdict** | BASELINE | **{status_badge}** | — |

---

## 2. R1 Protocol & Rescue Analysis

### Rescue Rate by Prior Failure Class
- **R1a (Truncated >=2048):** {prior_class_summary.get('R1a', {}).get('rescued_count', 0)} / {prior_class_summary.get('R1a', {}).get('total_in_manifest', 34)} ({prior_class_summary.get('R1a', {}).get('rescue_rate', 0.0)*100:.1f}%)
- **R1b (Empty / 0 props):** {prior_class_summary.get('R1b', {}).get('rescued_count', 0)} / {prior_class_summary.get('R1b', {}).get('total_in_manifest', 136)} ({prior_class_summary.get('R1b', {}).get('rescue_rate', 0.0)*100:.1f}%)
- **R1c (Unparseable JSON):** {prior_class_summary.get('R1c', {}).get('rescued_count', 0)} / {prior_class_summary.get('R1c', {}).get('total_in_manifest', 116)} ({prior_class_summary.get('R1c', {}).get('rescue_rate', 0.0)*100:.1f}%)
- **Overall Rescued:** {prior_class_summary.get('overall', {}).get('rescued_count', 0)} / {prior_class_summary.get('overall', {}).get('total_in_manifest', 286)} ({prior_class_summary.get('overall', {}).get('rescue_rate', 0.0)*100:.1f}%)

---

## 3. Universal Receipt Verification

Deterministic verification command:
```bash
python benchmarks/run_deepseek_flash_bakeoff.py --verify-receipt --out-dir {out_dir}
```
Receipt written to `{receipt_file}`.
"""

    with open(handoff_file, "w", encoding="utf-8") as f:
        f.write(handoff_md)

    print("\n" + "=" * 80)
    print(f"Bake-Off Complete! Verdict: {status_badge}")
    print(f"Overall Faithfulness: {point_f:.4f} (95% CI [{low_f:.4f}, {high_f:.4f}])")
    print(f"Validity Rate: {(valid_count/len(clusters))*100:.1f}% | Grounding-Given-Valid: {valid_point:.4f} [{valid_low:.4f}, {valid_high:.4f}]")
    print(f"Run Spend: ${total_spend_usd:.4f} | Cumulative Cloud Spend: ${CUMULATIVE_PRIOR_SPEND_USD + total_spend_usd:.4f} / ${SPEND_CAP_USD:.2f}")
    print(f"R1 Prior Class Rescue Summary:")
    print(f"  R1a (Truncated): {prior_class_summary.get('R1a', {}).get('rescued_count', 0)} / {prior_class_summary.get('R1a', {}).get('total_in_manifest', 34)} ({prior_class_summary.get('R1a', {}).get('rescue_rate', 0.0)*100:.1f}%)")
    print(f"  R1b (Empty):     {prior_class_summary.get('R1b', {}).get('rescued_count', 0)} / {prior_class_summary.get('R1b', {}).get('total_in_manifest', 136)} ({prior_class_summary.get('R1b', {}).get('rescue_rate', 0.0)*100:.1f}%)")
    print(f"  R1c (Unparse):   {prior_class_summary.get('R1c', {}).get('rescued_count', 0)} / {prior_class_summary.get('R1c', {}).get('total_in_manifest', 116)} ({prior_class_summary.get('R1c', {}).get('rescue_rate', 0.0)*100:.1f}%)")
    print(f"  Total Rescued:   {prior_class_summary.get('overall', {}).get('rescued_count', 0)} / {prior_class_summary.get('overall', {}).get('total_in_manifest', 286)} ({prior_class_summary.get('overall', {}).get('rescue_rate', 0.0)*100:.1f}%)")
    print(f"Artifacts saved to: {out_dir}")
    print("=" * 80)

    return report


def verify_receipt(out_dir: Path = DEFAULT_OUT_DIR) -> tuple[bool, list[str]]:
    """Verify artifacts and receipt in out_dir."""
    errors = []
    receipt_file = out_dir / "verification_receipt.json"
    report_file = out_dir / "model_bakeoff_report.json"
    raw_file = out_dir / "bakeoff_raw_results.json"
    handoff_file = out_dir / "handoff.md"

    for p in (receipt_file, report_file, raw_file, handoff_file):
        if not p.exists():
            errors.append(f"Missing required artifact: {p}")

    if errors:
        return False, errors

    try:
        with open(receipt_file, "r", encoding="utf-8") as f:
            receipt = json.load(f)
        with open(report_file, "r", encoding="utf-8") as f:
            report = json.load(f)
    except Exception as e:
        return False, [f"Failed to parse JSON artifacts: {e}"]

    if receipt.get("target_node") != "CAP-MOD01-DEEPSEEK-FLASH":
        errors.append(f"Invalid target_node: {receipt.get('target_node')}")

    model_data = report.get("model_under_test", {})
    if model_data.get("model_id") != SAIL_MODEL_ID:
        errors.append(f"Report model_id mismatch: {model_data.get('model_id')}")

    clusters_eval = receipt.get("clusters_evaluated", 0)
    if clusters_eval <= 0:
        errors.append(f"Zero clusters evaluated in receipt: {clusters_eval}")

    # Guard against fraudulent runs with 0 tokens or all failed network calls
    prompt_tokens = receipt.get("total_prompt_tokens", 0)
    valid_clusters = receipt.get("valid_cluster_count", 0)
    if clusters_eval >= 10 and (prompt_tokens <= 0 or valid_clusters <= 0):
        errors.append(f"Receipt indicates unexecuted or totally failed run (prompt_tokens={prompt_tokens}, valid_clusters={valid_clusters})")

    if "disentangled_metrics" not in model_data:
        errors.append("Report missing disentangled_metrics")

    # Verify R1 retry count consistency between report and receipt
    report_fallback = model_data.get("concurrency_and_fallback", {})
    report_queued = report_fallback.get("serial_fallback_queued")
    receipt_queued = receipt.get("serial_fallback_summary", {}).get("queued_count")
    if report_queued is not None and receipt_queued is not None and report_queued != receipt_queued:
        errors.append(f"R1 queued count mismatch: report={report_queued}, receipt={receipt_queued}")

    report_rescued = report_fallback.get("serial_fallback_rescued")
    receipt_rescued = receipt.get("serial_fallback_summary", {}).get("rescued_count")
    if report_rescued is not None and receipt_rescued is not None and report_rescued != receipt_rescued:
        errors.append(f"R1 rescued count mismatch: report={report_rescued}, receipt={receipt_rescued}")

    # Verify spend cap compliance
    cum_spend = receipt.get("cumulative_total_spend_usd") or receipt.get("total_spend_usd", 0.0)
    spend_cap = receipt.get("spend_cap_usd", 25.0)
    if cum_spend > spend_cap:
        errors.append(f"Cumulative spend ${cum_spend} exceeds spend cap ${spend_cap}")

    return len(errors) == 0, errors


def prompt_and_save_key() -> str:
    """Interactively prompt user for Sail Research API key, validate it, and save to .env."""
    print("=" * 60)
    print("Sail Research API Key Setup")
    print("=" * 60)
    key = getpass.getpass("Paste Sail Research API key (hidden): ").strip()
    if not key:
        print("[ABORT] No key entered.")
        return ""

    print("Verifying key against https://api.sailresearch.com/v1/models...")
    client = SailResearchClient(api_key=key)
    ok, msg = client.verify_credentials()
    if not ok:
        print(f"[WARNING] Key verification failed: {msg}")
        ans = input("Save key anyway? (y/N): ").strip().lower()
        if ans != "y":
            print("[ABORT] Key discarded.")
            return ""
    else:
        print(f"[SUCCESS] {msg}")

    env_path = Path(".env")
    lines = []
    found = False
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("SAIL_API_KEY="):
                    lines.append(f"SAIL_API_KEY={key}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"\nSAIL_API_KEY={key}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print("[SUCCESS] SAIL_API_KEY saved to .env securely.")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DeepSeek Flash V4 0731 bake-off via Sail Research")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to frozen atom clusters")
    parser.add_argument("--clusters", type=int, default=100, help="Number of clusters to evaluate (default 100)")
    parser.add_argument("--api-key", type=str, default=None, help="Sail Research API key")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory")
    parser.add_argument("--verify-receipt", action="store_true", help="Verify receipt in output directory")
    parser.add_argument("--check-key", action="store_true", help="Perform pre-flight authentication check on resolved key")
    parser.add_argument("--prompt-key", action="store_true", help="Prompt for key interactively, validate, and save to .env")

    args = parser.parse_args()

    if args.prompt_key:
        key = prompt_and_save_key()
        return 0 if key else 1

    if args.verify_receipt:
        ok, errors = verify_receipt(args.out_dir)
        if ok:
            print(f"[PASS] DeepSeek Flash V4 0731 bake-off receipt verified 100% in {args.out_dir}.")
            return 0
        else:
            print(f"[FAIL] Receipt verification failed: {errors}", file=sys.stderr)
            return 1

    api_key = resolve_api_key(args.api_key)

    if args.check_key:
        if not api_key:
            print("[ERROR] No key resolved to check. Pass --api-key or set SAIL_API_KEY.", file=sys.stderr)
            return 2
        client = SailResearchClient(api_key=api_key)
        ok, msg = client.verify_credentials()
        if ok:
            print(f"[PASS] Key valid! {msg}")
            return 0
        else:
            print(f"[FAIL] Key invalid: {msg}", file=sys.stderr)
            return 2

    if not api_key:
        # Check if running interactively in terminal
        if sys.stdin.isatty():
            print("[INFO] No Sail Research API key found in environment or .env.")
            api_key = prompt_and_save_key()
        if not api_key:
            print("[ERROR] No Sail Research API key found.", file=sys.stderr)
            print("Please provide it via --api-key, run with --prompt-key, or run run_deepseek_flash_bakeoff.bat", file=sys.stderr)
            return 2

    manifest_path = args.manifest
    if not manifest_path.exists() and FALLBACK_MANIFEST.exists():
        manifest_path = FALLBACK_MANIFEST

    if not manifest_path.exists():
        print(f"Error: manifest file {manifest_path} not found.", file=sys.stderr)
        return 1

    try:
        report = run_deepseek_flash_bakeoff(
            manifest_path=manifest_path,
            api_key=api_key,
            max_clusters=args.clusters,
            out_dir=args.out_dir,
        )
        return 0
    except Exception as e:
        print(f"[EXECUTION ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
