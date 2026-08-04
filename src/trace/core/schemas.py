import uuid
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Any, Dict

# Basic Metadata
class SourceMeta(BaseModel):
    filename: str
    absolute_path: str
    chunk_index: int
    block_id: Optional[str] = None # UUID linking to SQLite block

# Traces and State
class ExtractedRelation(BaseModel):
    target_concept: str = Field(description="The name of the entity or concept this chunk links to.")
    relation_type: Literal["supersedes", "depends_on", "implements", "reverts", "contrasts_with", "paradox"] = Field(
        description="The precise structural relationship linking these two concepts."
    )

class HippocampalTrace(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    anchor_concept: str = Field(
        description="A canonical, highly descriptive name for the core technical concept/idea discussed."
    )
    artifact_type: Literal["core_concept", "version_milestone", "technical_idea", "architecture_decision", "informational"] = Field(
        description="The architectural category of this trace."
    )
    status: Literal["active", "rejected", "backlogged", "informational", "conflicted", "legacy"] = Field(
        description="Current state of the concept based *strictly* on the text. Use 'rejected' if an idea is abandoned."
    )
    chronological_marker: Optional[str] = Field(
        None, description="Any explicit version numbers, dates, or timeline indicators mentioned (e.g., 'v1.0-alpha', 'Q3 Review')."
    )
    summary_trace: str = Field(
        description="A dense, 1-2 sentence compression of the raw text block, stripping all fluff but retaining technical decisions."
    )
    relations: List[ExtractedRelation] = Field(
        default=[], description="Explicit links to other concepts extracted within this context block."
    )
    source_meta: Optional[SourceMeta] = None
    raw_source_text: str = "" # Holds the full text payload for the writer agent

class RollingStateBuffer(BaseModel):
    """The sliding state passed from chunk to chunk to maintain context."""
    active_version: str = Field(default="unknown", description="The prevailing project version in the current document context.")
    active_hypotheses: Dict[str, float] = Field(default_factory=dict, description="A running tracker of proposed technical ideas with their activation energies.")

class LLMRollingState(BaseModel):
    active_version: str = Field(default="unknown")
    active_hypotheses: List[str] = Field(default=[])

# Canonical Graph representation
class CanonicalEntity(BaseModel):
    id: str
    canonical_name: str
    traces: List[HippocampalTrace]
    status: str

class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    relation_type: str

class ConflictResolutionResult(BaseModel):
    resolved_entities: List[CanonicalEntity]
    new_edges: List[GraphEdge]

# Event Payloads
class Event(BaseModel):
    name: str
    payload: Any

class DocumentChunkedPayload(BaseModel):
    project_id: str
    chunk_text: str
    meta: SourceMeta
    is_chronological: bool = False
    thread_id: str = "default"

class TraceExtractedPayload(BaseModel):
    project_id: str
    trace: Optional[HippocampalTrace] = None
    updated_state: LLMRollingState

class GraphResolvedPayload(BaseModel):
    project_id: str
    entities: List[CanonicalEntity]
    edges: List[GraphEdge]
    is_chronological: bool = False

class TocGeneratedPayload(BaseModel):
    project_id: str
    global_toc: str
    entities: List[CanonicalEntity]
    edges: List[GraphEdge]
    part_guidance: Dict[str, str] = Field(default_factory=dict)
    entity_parts: Dict[str, str] = Field(default_factory=dict)

class LLMCallPayload(BaseModel):
    project_id: str
    agent_name: str
    model_name: str
    prompt: Any
    response: str
