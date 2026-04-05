from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .ontology import validate_edge_type, validate_node_type


class HealthResponse(BaseModel):
    app_name: str
    environment: str
    status: str


class SetupStatusResponse(BaseModel):
    status: str
    detail: str | None = None


class TelegramConfigResponse(BaseModel):
    configured: bool
    poll_limit: int
    stored_offset: int | None = None
    current_workspace_id: int | None = None
    current_workspace_name: str | None = None


class WorkspaceRead(BaseModel):
    id: int
    name: str
    type: str
    embed_token: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    display_name: str | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def set_display_name(self) -> "WorkspaceRead":
        if self.display_name is None:
            meta = self.metadata_json or {}
            self.display_name = meta.get("display_name") or self.name
        return self


class WorkspaceSwitchRequest(BaseModel):
    workspace_id: int | None = None
    workspace_name: str | None = None
    workspace_type: str | None = None


class NodeCreate(BaseModel):
    workspace_id: int | None = None
    type: str
    raw_text: str = Field(min_length=1)
    time_label: str | None = None
    normalized_text: str | None = None
    source: str = "manual"
    author: str | None = None
    telegram_message_id: str | None = None
    status: str = "active"
    tags: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        return validate_node_type(value)

    @field_validator("raw_text")
    @classmethod
    def _validate_raw_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("raw_text cannot be empty or whitespace")
        return stripped


class NodeUpdate(BaseModel):
    type: str | None = None
    raw_text: str | None = None
    time_label: str | None = None
    normalized_text: str | None = None
    author: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    metadata_json: dict[str, Any] | None = None
    reason: str = "edit"

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_node_type(value)

    @field_validator("raw_text")
    @classmethod
    def _validate_raw_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("raw_text cannot be empty or whitespace")
        return stripped


class NodeRead(BaseModel):
    id: int
    workspace_id: int
    type: str
    raw_text: str
    normalized_text: str | None
    source: str
    author: str | None
    telegram_message_id: str | None
    status: str
    tags: list[str]
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NodeVersionRead(BaseModel):
    id: int
    workspace_id: int
    node_id: int
    version_number: int
    reason: str
    snapshot_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EdgeCreate(BaseModel):
    workspace_id: int | None = None
    from_node_id: int
    to_node_id: int
    type: str
    weight: float = 0.5
    confidence: float = 0.5
    created_by: str = "manual"
    evidence: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        return validate_edge_type(value)

    @field_validator("weight", "confidence")
    @classmethod
    def _validate_score(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("weight and confidence must be between 0.0 and 1.0")
        return value


class EdgeRead(BaseModel):
    id: int
    workspace_id: int
    from_node_id: int
    to_node_id: int
    type: str
    weight: float
    confidence: float
    created_by: str
    evidence: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TelegramIngestRequest(BaseModel):
    update: dict[str, Any]


class TelegramIngestResponse(BaseModel):
    outcome: str
    detail: str
    update_id: int
    node: NodeRead | None = None
    ingestion_job_id: int | None = None


class TelegramPollResponse(BaseModel):
    used_offset: int | None = None
    fetched: int
    created: int
    duplicates: int
    ignored: int
    next_offset: int | None = None
    current_workspace_id: int | None = None
    current_workspace_name: str | None = None


class EmbeddingConfigResponse(BaseModel):
    configured: bool
    model_name: str
    batch_size: int


class EmbeddingRead(BaseModel):
    id: int
    workspace_id: int
    node_id: int
    model_name: str
    dimensions: int
    content_hash: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmbeddingJobRead(BaseModel):
    id: int
    workspace_id: int
    node_id: int
    model_name: str
    content_hash: str
    status: str
    payload_json: dict[str, Any]
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmbeddingProcessResponse(BaseModel):
    processed: int
    reused: int
    failed: int
    remaining_pending: int


class CandidateRead(BaseModel):
    node: NodeRead
    semantic_score: float
    lexical_score: float
    combined_score: float


class NeighborRead(BaseModel):
    direction: str
    edge: EdgeRead
    node: NodeRead


class TraversedNodeRead(BaseModel):
    node: NodeRead
    depth: int
    path_score: float
    via_edge_id: int | None


class SubgraphRead(BaseModel):
    root_node: NodeRead
    nodes: list[TraversedNodeRead]
    edges: list[EdgeRead]


class OutlineSectionRead(BaseModel):
    heading: str
    summary: str
    node_ids: list[int]
    edge_types: list[str]


class OutlinePlanRequest(BaseModel):
    workspace_id: int | None = None
    root_node_id: int
    depth: int = 2
    max_nodes: int = 12
    edge_type: str | None = None


class OutlinePlanRead(BaseModel):
    root_node: NodeRead
    sections: list[OutlineSectionRead]
    nodes: list[TraversedNodeRead]
    edges: list[EdgeRead]


class NarrativeRequest(BaseModel):
    workspace_id: int | None = None
    root_node_id: int
    depth: int = 2
    max_nodes: int = 9
    edge_type: str | None = None
    paragraphs: int = 2


class NarrativeRead(BaseModel):
    root_node: NodeRead
    narrative: str
    nodes: list[TraversedNodeRead]
    edges: list[EdgeRead]


class LinkJobRead(BaseModel):
    id: int
    workspace_id: int
    node_id: int | None
    status: str
    candidate_count: int
    payload_json: dict[str, Any]
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LinkProcessResponse(BaseModel):
    processed: int
    edges_created: int
    proposals_created: int
    duplicates_skipped: int
    failed: int
    remaining_pending: int


class LinkProposalRead(BaseModel):
    id: int
    workspace_id: int
    source_node_id: int
    target_node_id: int
    relation_type: str
    status: str
    semantic_score: float
    lexical_score: float
    combined_score: float
    confidence: float
    weight: float
    evidence: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArticleDraftCreate(BaseModel):
    workspace_id: int | None = None
    root_node_id: int
    depth: int = 2
    max_nodes: int = 12
    edge_type: str | None = None
    title: str | None = None
    status: str = "draft"


class ArticleDraftUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    outline_json: list[dict[str, Any]] | None = None
    content_markdown: str | None = None
    provenance_json: list[dict[str, Any]] | None = None
    metadata_json: dict[str, Any] | None = None
    reason: str = "edit"


class ArticleDraftRead(BaseModel):
    id: int
    workspace_id: int
    title: str
    root_node_id: int | None
    status: str
    outline_json: list[dict[str, Any]]
    content_markdown: str
    provenance_json: list[dict[str, Any]]
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArticleDraftVersionRead(BaseModel):
    id: int
    workspace_id: int
    draft_id: int
    version_number: int
    reason: str
    snapshot_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArticleExportRead(BaseModel):
    title: str
    markdown: str


class GenerateEdgesResponse(BaseModel):
    queued_embeddings: int
    embedding_processing: EmbeddingProcessResponse
    queued_links: int
    link_processing: LinkProcessResponse


class EdgeCreationPair(BaseModel):
    source_node_id: int
    target_node_id: int


class EdgeCreationNodeInput(BaseModel):
    id: int
    type: str
    raw_text: str
    normalized_text: str | None = None
    user_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        return validate_node_type(value)


class EdgeCreationConfig(BaseModel):
    threshold: float | None = None
    max_pairs: int | None = None
    edge_types_allowed: list[str] = Field(
        default_factory=lambda: [
            "similar_to",
            "supports",
            "contradicts",
            "expands",
            "led_to",
            "belongs_to_topic",
        ]
    )
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("edge_types_allowed")
    @classmethod
    def _validate_edge_types(cls, value: list[str]) -> list[str]:
        return [validate_edge_type(item) for item in value]


class EdgeCreationRequest(BaseModel):
    function_name: str
    run_id: str | None = None
    workspace_id: int | None = None
    config: EdgeCreationConfig = Field(default_factory=EdgeCreationConfig)
    node_ids: list[int] = Field(default_factory=list)
    nodes: list[EdgeCreationNodeInput] = Field(default_factory=list)
    pairs: list[EdgeCreationPair] = Field(default_factory=list)


class EdgeCreationSummary(BaseModel):
    nodes_seen: int
    pairs_considered: int
    edges_proposed: int
    hubs_proposed: int


class EdgeCreationError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class EdgeCreationEdgeResult(BaseModel):
    source_node_id: int
    target_node_id: int
    edge_type: str
    score: float
    confidence: float
    should_create: bool
    evidence: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeCreationHubResult(BaseModel):
    hub_temp_id: str
    label: str
    score: float
    source_node_ids: list[int]
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeCreationResponse(BaseModel):
    function_name: str
    run_id: str | None = None
    status: str
    summary: EdgeCreationSummary
    edges: list[EdgeCreationEdgeResult] = Field(default_factory=list)
    hubs: list[EdgeCreationHubResult] = Field(default_factory=list)
    errors: list[EdgeCreationError] = Field(default_factory=list)
