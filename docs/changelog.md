# Changelog

All notable changes to the Trace project will be documented in this file.

## [1.0.0] - 2026-07-05

### Added
- **Terminal React UI**: Replaced the legacy Streamlit UI with a custom-engineered, dark-themed, monospaced React Dashboard that mimics a developer terminal.
- **Persistent Project Dashboard**: Enabled creation, management, and deletion of distinct project workspaces stored in SQLite (`trace.db`).
- **Dynamic Startup Script (`start.bat`)**: Re-architected startup sequence to use a single terminal process that dynamically auto-detects free ports, spins up both FastAPI and Vite servers, and opens the browser.
- **Trace Review Panel**: Fully wired SQLite traces to a trace editor, enabling real-time manual updates to concept anchors, types, and relations.
- **Interactive TOC Planner**: Integrated a Chat interface with the Planner Agent (`MacroSynthesizer`) inside the TOC editor to restructure and refine the Table of Contents via natural language.
- **Writer Agent Pipeline**: Connected the `WriterAgent` with automatic model fallbacks (using `gemini-3.1-flash-lite` on model errors) to compile raw, lossless traces into final markdown documentation.
- **DAG Export**: Automatically compiles and outputs a `Graph.mmd` Mermaid visual representation of the dependency graph in the project output directory.
- **Project Output Explorer**: Added a live file browser inside the React UI that polls, compiles, and lets users read the generated markdown documents right in their browser.

## [0.1.0] - 2026-07-04

### Added
- **Config Persistence**: Added a `.trace_config.json` system in the Streamlit UI to automatically save and load API keys, selected models, and UI preferences across sessions.
- **Model Selection**: The UI now allows independent selection of the Planner Model (for extraction/synthesizer) and the Writer Model (for Markdown generation).
- **Processing Mode Toggle**: Added a choice in the Streamlit UI between a "Cloud Hybrid Strategy" (uses fast layout parsing) and the "Existing Strategy" (heavy local parsing).
- **API Rate Limit Protections**: Integrated the `tenacity` library to implement an asynchronous exponential backoff and retry loop in `micro_extractor.py` for LLM API calls. This allows graceful handling of `429 Too Many Requests` when using cloud models like Gemma 4.

### Changed
- **Parser Optimization**: `ingest_documents` now accepts a `fast_mode` argument. When enabled, `unstructured.partition.auto` uses `strategy="fast"` to dramatically reduce memory/VRAM footprint and ingestion time by skipping heavy computer vision models.
- **Improved Logging**: Streamlit UI stdout redirection was improved to display the selected mode and model during the pipeline execution for better monitoring.
