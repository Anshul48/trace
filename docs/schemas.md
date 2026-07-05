# Project Trace: Data Contracts & Schemas

This document defines the key Pydantic data schemas that drive the Project Trace DAG engine.

## Structural Data Models

### 1. SourceMeta
Metadata linking a semantic trace back to its origin file and partition block.
```python
class SourceMeta(BaseModel):
    filename: str
    absolute_path: str
    chunk_index: int
    block_id: Optional[str] = None # UUID pointing to the SQLite blocks table
```

### 2. ExtractedRelation
Represents a structural relationship between the anchor concept and another concept in the graph.
```python
class ExtractedRelation(BaseModel):
    target_concept: str # The name of the target entity
    relation_type: Literal["supersedes", "depends_on", "implements", "reverts", "contrasts_with"]
```

### 3. HippocampalTrace
The atomic semantic node extracted by the MicroExtractor.
```python
class HippocampalTrace(BaseModel):
    trace_id: str # Cryptographic UUID generated on extraction
    anchor_concept: str # Canonical concept name
    artifact_type: Literal["core_concept", "version_milestone", "technical_idea", "architecture_decision"]
    status: Literal["active", "rejected", "backlogged", "informational"]
    chronological_marker: Optional[str] # Version tag or date review markers
    summary_trace: str # Dense 1-2 sentence compression of technical choices
    relations: List[ExtractedRelation]
    source_meta: Optional[SourceMeta]
    raw_source_text: str # Preserved full-text block for lossless compilation
```

---

## Event Bus Payloads

All event payloads include a `project_id` to route messages correctly inside the workspace and isolate parallel projects.

### 1. DocumentChunkedPayload
Triggered when a document has been partitioned and stored as an immutable block.
```python
class DocumentChunkedPayload(BaseModel):
    project_id: str
    chunk_text: str
    meta: SourceMeta
```

### 2. TraceExtractedPayload
Emitted when the MicroExtractor finishes running on a block.
```python
class TraceExtractedPayload(BaseModel):
    project_id: str
    trace: HippocampalTrace
    updated_state: RollingStateBuffer # Carries rolling hypotheses and versions
```

### 3. GraphResolvedPayload
Emitted once the deterministic clustering process finishes semantic deduplication of entities and edges.
```python
class GraphResolvedPayload(BaseModel):
    project_id: str
    entities: List[CanonicalEntity]
    edges: List[GraphEdge]
```

### 4. TocGeneratedPayload
Emitted by the MacroSynthesizer after building the Table of Contents, pausing the compiler to wait for human intervention.
```python
class TocGeneratedPayload(BaseModel):
    project_id: str
    global_toc: str
    entities: List[CanonicalEntity]
    edges: List[GraphEdge]
```

### 5. LLMCallPayload
Emitted on every LLM agent execution, providing detailed system context, prompt inputs, and outputs to the live logs dashboard.
```python
class LLMCallPayload(BaseModel):
    project_id: str
    agent_name: str
    model_name: str
    prompt: Any
    response: str
```
