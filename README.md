# Project Trace: Reactive Knowledge Graph OS

Project Trace is a **Bi-Directional, Reactive Knowledge Graph OS** that converts unstructured project documentation into a structured, semantic DAG (Directed Acyclic Graph) of technical decisions, versions, and active/parked ideas. 

Unlike standard one-way ETL summarization pipelines, Project Trace treats the generated Markdown repository as a dynamic presentation layer (View) and the internal DAG as the ground-truth state (Model). It automatically parses human edits in the generated files and propagates those changes back into the graph in real-time.

---

## Key Features

- **Double Architecture Pattern**: Decouples the internal state database (SQLite + NetworkX) from the user-facing Markdown repository.
- **Bi-Directional Sync**: A background filesystem watcher intercepts edits made to the Markdown files (with a 5-second debounce) and decompiles them back into the DAG.
- **3-Tier Impact Routing**: Determines the impact of manual edits using a local embedding model (`all-MiniLM-L6-v2`) to compute cosine similarity.
  - **Tier 1 (Surface)**: Typos, grammar edits, or formatting updates update the database silently without calling LLMs.
  - **Tier 2 (Trace Mutation)**: Semantic changes (e.g. changing status of a concept from active to rejected) trigger a local re-run of the MicroExtractor.
  - **Tier 3 (Topology Change)**: Deleting sections or adding new text/wikilinks triggers a new ingestion and global graph reconstruction.
- **Persistent Projects**: Group document ingestions under distinct projects. Extracted traces are saved directly into the SQLite database (`trace.db`) under this project workspace, ensuring zero data loss if a network error occurs.
- **FastAPI Backend & React Frontend**: Decoupled, asynchronous service design. Live extraction logs are streamed to the frontend over WebSockets.
- **Trace & TOC Editing**: A modern dashboard allows you to review and manually edit extracted concepts before resolving the graph, and interactively refine the TOC with a dedicated Planner Agent.

---

## Quick Start

### Installation

Ensure you have [uv](https://github.com/astral-sh/uv) installed.

```bash
# Clone the repository and install dependencies
git clone <repo-url>
cd trace
uv sync
```

### Configuration

Create a `.env` file in the project root:

```env
DEEPSEEK_API_KEY="your-deepseek-api-key"
GEMINI_API_KEY="your-gemini-api-key"
```

### Running the Application

To build the frontend and launch both the backend and frontend servers in a single terminal process (with dynamic port detection):

```bash
# Double-click start.bat in Windows Explorer, or run in terminal:
./start.bat
```

This script automatically:
1. Locates available open ports for both the FastAPI backend and the Vite frontend.
2. Bundles/serves the frontend and starts the Uvicorn api.
3. Automatically opens your default web browser pointing to the correct address.

If you prefer to run them independently for active debugging:

#### Backend API
```bash
uv run uvicorn main_api:app --reload
```

#### React Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## Documentation

Full architectural specifications, data flows, and code walk-throughs are available in the [docs/](file:///c:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs) directory:
1. [Architecture Overview](file:///c:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/architecture.md)
2. [Data Contracts & Schemas](file:///c:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/schemas.md)
3. [The Reverse-Sync Sync Engine](file:///c:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/sync_engine.md)
