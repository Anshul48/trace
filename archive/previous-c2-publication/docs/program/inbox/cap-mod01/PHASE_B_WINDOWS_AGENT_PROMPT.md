# Phase B Windows agent prompt (paste into agy CLI on Windows)

You are the Phase B runner for TRACE-CAP-001 (CAP-MOD01 redo).
Work in exactly this repo: `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace`.
Active plan: `docs\program\inbox\cap-mod01\PHASE_B_FINALISTS_PLAN.md` (read it first; it overrides Phase A).

## Absolute rules (violations fail the node)

1. Local-only. Teacher (`deepseek-v4-flash`) stays ABSENT: no provider calls, no spend. Never read, print, use, or rely on key-like values in `.env` (unknown provenance — flag ROTATE, never touch). Never write keys to disk/logs/receipts.
2. Finalists only: `gemma4:26b`, `qwen3.8:27b`. Do NOT run `gemma4:e4b`, `qwen3:8b`, `gemma4:12b`, or `extractive_control`. Do not "fix" them.
3. Minimal runner edit (one transport change, nothing else): in `benchmarks\run_model_bakeoff.py`, find the Ollama payload (currently `"format": "json"`). Replace it with a skeleton-only JSON-schema dict derived from the runner's OWN parser/required-keys (reference skeleton below — conform key names to the parser if they differ). No `pattern`/`regex` on inner text fields. Set `options` to `temperature 0.0, num_predict 1536`. Prompt text byte-identical. Fail-closed scoring (invalid = 0.0), verifier completeness checks, and detached outputs all untouched. If the payload site looks different from this description, STOP and paste the actual code back — do not improvise a second edit.
4. Detached artifacts only: all outputs to `docs\program\inbox\cap-mod01\`. Zero Spine/Cortex writes; `run_cognitive_delta` stays disabled. No Entity Pre-Pass code (B4 is deferred by plan).
5. STOP after Phase B. No teacher run, no MOD02, no commits. Report back and halt.

Reference skeleton (adjust key names to match the runner's parser):

```python
HOLON_SCHEMA = {
    "type": "object",
    "properties": {
        "section_summaries": {"type": "array", "items": {"type": "object",
            "properties": {"section_id": {"type": "string"}, "title": {"type": "string"},
                "content": {"type": "string"}, "anchor_atom_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["section_id", "title", "content", "anchor_atom_ids"]}},
        "topic_holons": {"type": "array", "items": {"type": "object",
            "properties": {"topic_id": {"type": "string"}, "title": {"type": "string"},
                "summary": {"type": "string"}, "source_atom_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["topic_id", "title", "summary", "source_atom_ids"]}},
        "entity_candidates": {"type": "array", "items": {"type": "object",
            "properties": {"entity_id": {"type": "string"}, "canonical_name": {"type": "string"},
                "entity_type": {"type": "string"}},
            "required": ["entity_id", "canonical_name", "entity_type"]}},
        "relation_candidates": {"type": "array", "items": {"type": "object",
            "properties": {"source_entity_id": {"type": "string"}, "target_entity_id": {"type": "string"},
                "relation_type": {"type": "string"}},
            "required": ["source_entity_id", "target_entity_id", "relation_type"]}},
    },
    "required": ["section_summaries", "topic_holons", "entity_candidates", "relation_candidates"],
}
# payload: "format": HOLON_SCHEMA
```

## Steps

1. Preflight: `ollama --version`; `curl http://127.0.0.1:11434/api/tags` must answer; `ollama list` must show `gemma4:26b` and `qwen3.8:27b`. If a weight is missing, STOP and report which — no substitutions. `git status --short` + `git log --oneline -3` for the record.
2. Apply the §3 edit. Show the diff. Sanity: `python -c "import ast; ast.parse(open('benchmarks/run_model_bakeoff.py').read())"`.
3. Run: double-click `docs\program\inbox\cap-mod01\run_phaseB_bakeoff.bat` (or the equivalent commands inside it). It backs up `bakeoff_checkpoint.json` once, resumes `gemma4:26b` 10→100 first (~1h), then `qwen3.8:27b` 10→100 (~6h, overnight OK), then `--verify-receipt` (must exit 0). Charger connected, machine awake. Live status is expected: per-cluster scores stream on console via `python -u`, plus `docs\program\inbox\cap-mod01\progress.json` updates live — keep that window visible; do NOT close it mid-run. If any step exits nonzero, STOP and paste the traceback back — do not patch around it or rerun with different flags.
4. Report back (paste verbatim, no paraphrase): the §3 diff; per-model coverage (expect 100/100), fail-closed point + 95% CI + width, conditional grounding (grounding-given-valid), invalid rate, warm tok/s, P95 latency, wall time, API spend ($0.00); champion + rationale per plan §4; full verify output.

Reference: failed 1-cluster pilot preserved under `docs\program\inbox\cap-mod01\attempt1_pilot_1cluster\` (evidence only). Phase A prompt/batch files are superseded, preserved as evidence.
