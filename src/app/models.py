from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_chat_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    access_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False
    )


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="general", index=True)
    embed_token: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class Node(TimestampMixin, Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="manual")
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    telegram_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    outgoing_edges: Mapped[list["Edge"]] = relationship(
        back_populates="from_node", foreign_keys="Edge.from_node_id"
    )
    incoming_edges: Mapped[list["Edge"]] = relationship(
        back_populates="to_node", foreign_keys="Edge.to_node_id"
    )
    embeddings: Mapped[list["Embedding"]] = relationship(back_populates="node")
    versions: Mapped[list["NodeVersion"]] = relationship(back_populates="node")


class Edge(TimestampMixin, Base):
    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False, index=True)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="manual")
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    from_node: Mapped[Node] = relationship(back_populates="outgoing_edges", foreign_keys=[from_node_id])
    to_node: Mapped[Node] = relationship(back_populates="incoming_edges", foreign_keys=[to_node_id])


class Embedding(TimestampMixin, Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_json: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    node: Mapped[Node] = relationship(back_populates="embeddings")


class EmbeddingJob(TimestampMixin, Base):
    __tablename__ = "embedding_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestionJob(TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class LinkJob(TimestampMixin, Base):
    __tablename__ = "link_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class LinkProposal(TimestampMixin, Base):
    __tablename__ = "link_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    source_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False, index=True)
    target_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="review_needed", index=True)
    semantic_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    lexical_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    combined_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AppState(TimestampMixin, Base):
    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class InternalTag(TimestampMixin, Base):
    __tablename__ = "internal_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    tag_value: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tag_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)


class InternalTagMembership(TimestampMixin, Base):
    __tablename__ = "internal_tag_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("internal_tags.id"), nullable=False, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class ExperimentalHub(TimestampMixin, Base):
    __tablename__ = "experimental_hubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    signature: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    matcher_name: Mapped[str] = mapped_column(String(64), nullable=False, default="hub_matcher")
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    memberships: Mapped[list["ExperimentalHubMembership"]] = relationship(back_populates="hub")


class ExperimentalHubMembership(TimestampMixin, Base):
    __tablename__ = "experimental_hub_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    hub_id: Mapped[int] = mapped_column(ForeignKey("experimental_hubs.id"), nullable=False, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    hub: Mapped[ExperimentalHub] = relationship(back_populates="memberships")


class NodeVersion(TimestampMixin, Base):
    __tablename__ = "node_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False, default="edit")
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    node: Mapped[Node] = relationship(back_populates="versions")


class ArticleDraft(TimestampMixin, Base):
    __tablename__ = "article_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    root_node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft")
    outline_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provenance_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    versions: Mapped[list["ArticleDraftVersion"]] = relationship(back_populates="draft")


class ArticleDraftVersion(TimestampMixin, Base):
    __tablename__ = "article_draft_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("article_drafts.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False, default="edit")
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    draft: Mapped[ArticleDraft] = relationship(back_populates="versions")
