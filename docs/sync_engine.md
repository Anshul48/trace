# Project Trace: The Bi-Directional Sync Engine

The sync engine handles the reactive loop that turns Project Trace from a static ETL summarizer into a living document compiler.

## The compilation/Decompilation Loop

```
    [Immutable DB State] --(WriterAgent Compile)--> [Markdown Files with hidden trace_ids]
            ^                                                   |
            |                                             (User Edits File)
            |                                                   v
    [DB Block Updated] <---(Triage Evaluation)--- [Watcher Diff & Regex Decompile]
```

### 1. Compile Phase (WriterAgent)
When generating files, the Writer Agent parses the DAG nodes and wraps the output blocks with invisible trace tags containing the exact database UUIDs:
```html
<!-- trace_id: a5f392... -->
Raw text compiled cohesively for the human view.
<!-- end_trace_id -->
```

### 2. File Monitoring (Watcher)
The `watchdog` framework actively monitors the `repo_out/` directory. When an `.md` file is saved:
1. The watcher intercepts the file update.
2. A **5-second debounce** is triggered. If the user makes another edit, the timer resets.
3. Once the timer completes, the file path is sent to the `Decompiler`.

### 3. Decompile Phase
The `Decompiler` reads the file and compiles the regular expression:
```regex
<!--\s*trace_id:\s*(.*?)\s*-->(.*?)<!--\s*end_trace_id\s*-->
```
It extracts the `trace_id` and the `modified_text`.

### 4. 3-Tier Triage Router
To save LLM costs and preserve performance, the engine triages the manual edits using local embedding models:
1. **Hash Check**: Computes a normalized SHA-256 hash of the modified text and compares it to the hash stored in SQLite. If identical, execution stops (no edits were made to that block).
2. **Cosine Similarity**: If hashes differ, it encodes the old block content and the new block content using `all-MiniLM-L6-v2` and computes their cosine similarity.

#### Heuristics:
- **Cosine Similarity > 0.95 (Tier 1: Surface Mutation)**:
  The edits are minor typos, styling changes, or syntactical rewrites. The database block is updated silently. No LLMs are called.
- **Cosine Similarity <= 0.95 (Tier 2: Trace Mutation)**:
  The edits indicate semantic shifts (e.g. changing an architectural preference). The SQLite block is updated and a local MicroExtractor call is scheduled to update the trace metadata status or relations.
- **Missing / Deleted Anchors (Tier 3: Topology Mutation)**:
  If a block has been added without anchors, it is treated as a fresh raw document chunk, routed to vector embedding, clustered, and woven into the master DAG.
