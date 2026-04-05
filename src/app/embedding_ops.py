from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import Embedding, EmbeddingJob, Node


_MODEL_CACHE: dict[str, Any] = {}


def embedding_input_for_node(node: Node) -> str:
    return node.normalized_text or node.raw_text


def compute_content_hash(text: str, model_name: str) -> str:
    payload = f"{model_name}\n{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def enqueue_embedding_job(db: Session, node: Node, model_name: str) -> EmbeddingJob | None:
    if node.status == "deleted":
        return None

    text = embedding_input_for_node(node)
    content_hash = compute_content_hash(text, model_name)

    existing_embedding = db.scalar(
        select(Embedding).where(
            Embedding.workspace_id == node.workspace_id,
            Embedding.node_id == node.id,
            Embedding.model_name == model_name,
            Embedding.content_hash == content_hash,
        )
    )
    if existing_embedding is not None:
        return None

    existing_job = db.scalar(
        select(EmbeddingJob).where(
            EmbeddingJob.workspace_id == node.workspace_id,
            EmbeddingJob.node_id == node.id,
            EmbeddingJob.model_name == model_name,
            EmbeddingJob.content_hash == content_hash,
            EmbeddingJob.status.in_(["pending", "processing", "completed"]),
        )
    )
    if existing_job is not None:
        return existing_job

    job = EmbeddingJob(
        workspace_id=node.workspace_id,
        node_id=node.id,
        model_name=model_name,
        content_hash=content_hash,
        status="pending",
        payload_json={"text_preview": text[:120]},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _load_sentence_transformer(model_name: str):
    from sentence_transformers import SentenceTransformer

    model = _MODEL_CACHE.get(model_name)
    if model is None:
        model = SentenceTransformer(model_name)
        _MODEL_CACHE[model_name] = model
    return model


def _embed_text(settings: Settings, model_name: str, text: str) -> list[float]:
    model = _load_sentence_transformer(model_name)
    vector = model.encode(text, normalize_embeddings=True)
    return [float(value) for value in vector.tolist()]


def warm_embedding_model(settings: Settings) -> None:
    _load_sentence_transformer(settings.embedding_model_name)


def process_pending_embedding_jobs(
    db: Session,
    settings: Settings,
    limit: int | None = None,
    workspace_id: int | None = None,
) -> dict[str, int]:
    from .linker_ops import enqueue_link_job

    max_jobs = limit or settings.embedding_batch_size
    stmt = (
        select(EmbeddingJob)
        .where(EmbeddingJob.workspace_id.is_not(None), EmbeddingJob.status == "pending")
        .order_by(EmbeddingJob.id)
        .limit(max_jobs)
    )
    if workspace_id is not None:
        stmt = stmt.where(EmbeddingJob.workspace_id == workspace_id)
    jobs = list(db.scalars(stmt))

    processed = 0
    reused = 0
    failed = 0

    for job in jobs:
        node = db.get(Node, job.node_id)
        if node is None or node.status == "deleted" or node.workspace_id != job.workspace_id:
            job.status = "failed"
            job.error_message = "Node missing or deleted"
            db.commit()
            failed += 1
            continue

        text = embedding_input_for_node(node)
        content_hash = compute_content_hash(text, job.model_name)
        if content_hash != job.content_hash:
            job.status = "failed"
            job.error_message = "Node content changed; requeue required"
            db.commit()
            failed += 1
            continue

        existing_for_node = db.scalar(
            select(Embedding).where(
                Embedding.workspace_id == node.workspace_id,
                Embedding.node_id == node.id,
                Embedding.model_name == job.model_name,
                Embedding.content_hash == job.content_hash,
            )
        )
        if existing_for_node is not None:
            job.status = "completed"
            db.commit()
            enqueue_link_job(db, node, settings.candidate_retrieval_limit)
            processed += 1
            continue

        cached_embedding = db.scalar(
            select(Embedding).where(
                Embedding.workspace_id == node.workspace_id,
                Embedding.model_name == job.model_name,
                Embedding.content_hash == job.content_hash,
            )
        )
        if cached_embedding is not None:
            clone = Embedding(
                workspace_id=node.workspace_id,
                node_id=node.id,
                model_name=job.model_name,
                dimensions=cached_embedding.dimensions,
                vector_json=list(cached_embedding.vector_json),
                content_hash=job.content_hash,
            )
            db.add(clone)
            job.status = "completed"
            db.commit()
            enqueue_link_job(db, node, settings.candidate_retrieval_limit)
            reused += 1
            processed += 1
            continue

        try:
            job.status = "processing"
            db.commit()
            vector = _embed_text(settings, job.model_name, text)
            embedding = Embedding(
                workspace_id=node.workspace_id,
                node_id=node.id,
                model_name=job.model_name,
                dimensions=len(vector),
                vector_json=vector,
                content_hash=job.content_hash,
            )
            db.add(embedding)
            job.status = "completed"
            job.error_message = None
            db.commit()
            enqueue_link_job(db, node, settings.candidate_retrieval_limit)
            processed += 1
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            db.commit()
            failed += 1

    remaining_pending_stmt = (
        select(func_count())
        .select_from(EmbeddingJob)
        .where(EmbeddingJob.status == "pending", EmbeddingJob.workspace_id.is_not(None))
    )
    if workspace_id is not None:
        remaining_pending_stmt = remaining_pending_stmt.where(EmbeddingJob.workspace_id == workspace_id)

    return {
        "processed": processed,
        "reused": reused,
        "failed": failed,
        "remaining_pending": db.scalar(remaining_pending_stmt) or 0,
    }


def func_count():
    from sqlalchemy import func

    return func.count()


def lexical_overlap_score(query_text: str, candidate_text: str) -> float:
    query_tokens = set(re.findall(r"\w+", query_text.lower()))
    candidate_tokens = set(re.findall(r"\w+", candidate_text.lower()))
    if not query_tokens or not candidate_tokens:
        return 0.0
    intersection = len(query_tokens & candidate_tokens)
    union = len(query_tokens | candidate_tokens)
    return intersection / union if union else 0.0


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class CandidateResult:
    node: Node
    semantic_score: float
    lexical_score: float
    combined_score: float


def retrieve_candidates(
    db: Session,
    workspace_id: int,
    node_id: int,
    model_name: str,
    limit: int,
) -> list[CandidateResult]:
    source_node = db.get(Node, node_id)
    if source_node is None or source_node.status == "deleted" or source_node.workspace_id != workspace_id:
        return []

    source_embedding = db.scalar(
        select(Embedding).where(
            Embedding.workspace_id == workspace_id,
            Embedding.node_id == node_id,
            Embedding.model_name == model_name,
        )
    )
    if source_embedding is None:
        return []

    source_text = embedding_input_for_node(source_node)
    candidate_rows = list(
        db.scalars(
            select(Node)
            .where(Node.workspace_id == workspace_id, Node.id != node_id, Node.status != "deleted")
            .order_by(Node.id)
        )
    )

    embedding_map = {
        embedding.node_id: embedding
        for embedding in db.scalars(
            select(Embedding).where(Embedding.workspace_id == workspace_id, Embedding.model_name == model_name)
        )
    }

    results: list[CandidateResult] = []
    for candidate in candidate_rows:
        candidate_embedding = embedding_map.get(candidate.id)
        if candidate_embedding is None:
            continue
        semantic_score = cosine_similarity(
            source_embedding.vector_json,
            candidate_embedding.vector_json,
        )
        lexical_score = lexical_overlap_score(
            source_text,
            embedding_input_for_node(candidate),
        )
        combined = (semantic_score * 0.8) + (lexical_score * 0.2)
        results.append(
            CandidateResult(
                node=candidate,
                semantic_score=semantic_score,
                lexical_score=lexical_score,
                combined_score=combined,
            )
        )

    results.sort(key=lambda item: item.combined_score, reverse=True)
    return results[:limit]
