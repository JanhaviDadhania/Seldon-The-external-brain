from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .edge_creation_ops import run_tag_matcher
from .internal_tag_ops import shared_internal_tags_for_node, sync_node_internal_tags
from .models import Edge, LinkJob, LinkProposal, Node
from .schemas import EdgeCreationNodeInput, EdgeCreationPair, EdgeCreationRequest


AUTO_APPLY_THRESHOLD = 0.0
SYMMETRIC_RELATIONS = {"similar_to", "contradicts"}

def enqueue_link_job(db: Session, node: Node, candidate_limit: int) -> LinkJob | None:
    if node.status == "deleted":
        return None

    existing_job = db.scalar(
        select(LinkJob).where(
            LinkJob.workspace_id == node.workspace_id,
            LinkJob.node_id == node.id,
            LinkJob.status.in_(["pending", "processing"]),
        )
    )
    if existing_job is not None:
        return existing_job

    job = LinkJob(
        workspace_id=node.workspace_id,
        node_id=node.id,
        status="pending",
        candidate_count=candidate_limit,
        payload_json={"candidate_limit": candidate_limit},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _edge_exists(
    db: Session,
    workspace_id: int,
    source_node_id: int,
    target_node_id: int,
    relation_type: str,
) -> bool:
    stmt = select(Edge).where(Edge.workspace_id == workspace_id, Edge.type == relation_type)
    if relation_type in SYMMETRIC_RELATIONS:
        stmt = stmt.where(
            (
                ((Edge.from_node_id == source_node_id) & (Edge.to_node_id == target_node_id))
                | ((Edge.from_node_id == target_node_id) & (Edge.to_node_id == source_node_id))
            )
        )
    else:
        stmt = stmt.where(Edge.from_node_id == source_node_id, Edge.to_node_id == target_node_id)

    existing_edge = db.scalar(stmt)
    return existing_edge is not None


def _proposal_exists(
    db: Session,
    workspace_id: int,
    source_node_id: int,
    target_node_id: int,
    relation_type: str,
) -> bool:
    stmt = select(LinkProposal).where(
        LinkProposal.workspace_id == workspace_id,
        LinkProposal.relation_type == relation_type,
        LinkProposal.status.in_(["review_needed", "approved", "applied"]),
    )
    if relation_type in SYMMETRIC_RELATIONS:
        stmt = stmt.where(
            (
                (
                    (LinkProposal.source_node_id == source_node_id)
                    & (LinkProposal.target_node_id == target_node_id)
                )
                | (
                    (LinkProposal.source_node_id == target_node_id)
                    & (LinkProposal.target_node_id == source_node_id)
                )
            )
        )
    else:
        stmt = stmt.where(
            LinkProposal.source_node_id == source_node_id,
            LinkProposal.target_node_id == target_node_id,
        )

    proposal = db.scalar(stmt)
    return proposal is not None

def process_pending_link_jobs(
    db: Session,
    settings: Settings,
    limit: int = 10,
    workspace_id: int | None = None,
) -> dict[str, int]:
    stmt = (
        select(LinkJob)
        .where(LinkJob.workspace_id.is_not(None), LinkJob.status == "pending")
        .order_by(LinkJob.id)
        .limit(limit)
    )
    if workspace_id is not None:
        stmt = stmt.where(LinkJob.workspace_id == workspace_id)

    jobs = list(db.scalars(stmt))

    processed = 0
    edges_created = 0
    proposals_created = 0
    duplicates_skipped = 0
    failed = 0

    for job in jobs:
        node = db.get(Node, job.node_id) if job.node_id is not None else None
        if node is None or node.status == "deleted" or node.workspace_id != job.workspace_id:
            job.status = "failed"
            job.error_message = "Node missing or deleted"
            db.commit()
            failed += 1
            continue

        job.status = "processing"
        db.commit()

        try:
            sync_node_internal_tags(db, node)
            shared_candidates = shared_internal_tags_for_node(db, node)
            job.candidate_count = len(shared_candidates)

            target_nodes: list[Node] = []
            for target_id in shared_candidates:
                target_node = db.get(Node, target_id)
                if target_node is None or target_node.status == "deleted":
                    continue
                if target_node.workspace_id != node.workspace_id:
                    continue
                target_nodes.append(target_node)

            if not target_nodes:
                job.status = "completed"
                job.error_message = None
                db.commit()
                processed += 1
                continue

            result = run_tag_matcher(
                db,
                EdgeCreationRequest(
                    function_name="tag_matcher",
                    nodes=[
                        EdgeCreationNodeInput(
                            id=node.id,
                            type=node.type,
                            raw_text=node.raw_text,
                            normalized_text=node.normalized_text,
                            user_tags=node.tags,
                            metadata=node.metadata_json,
                        ),
                        *[
                            EdgeCreationNodeInput(
                                id=target_node.id,
                                type=target_node.type,
                                raw_text=target_node.raw_text,
                                normalized_text=target_node.normalized_text,
                                user_tags=target_node.tags,
                                metadata=target_node.metadata_json,
                            )
                            for target_node in target_nodes
                        ],
                    ],
                    pairs=[
                        EdgeCreationPair(source_node_id=node.id, target_node_id=target_node.id)
                        for target_node in target_nodes
                    ],
                ),
                settings=settings,
            )

            for classified in result.edges:
                target_id = classified.target_node_id

                if _edge_exists(db, node.workspace_id, node.id, target_id, classified.edge_type):
                    duplicates_skipped += 1
                    continue
                if _proposal_exists(db, node.workspace_id, node.id, target_id, classified.edge_type):
                    duplicates_skipped += 1
                    continue

                edge = Edge(
                    workspace_id=node.workspace_id,
                    from_node_id=node.id,
                    to_node_id=target_id,
                    type=classified.edge_type,
                    weight=classified.score,
                    confidence=classified.confidence,
                    created_by="linker",
                    evidence=classified.evidence.get("reason") or "Shared internal keywords and concepts",
                    metadata_json={
                        "shared_keywords": classified.evidence.get("shared_keywords", []),
                        "shared_concepts": classified.evidence.get("shared_concepts", []),
                        "shared_total": len(classified.evidence.get("shared_keywords", []))
                        + len(classified.evidence.get("shared_concepts", [])),
                    },
                )
                db.add(edge)
                edges_created += 1

            job.status = "completed"
            job.error_message = None
            db.commit()
            processed += 1
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            db.commit()
            failed += 1

    remaining_pending_stmt = (
        select(func_count())
        .select_from(LinkJob)
        .where(LinkJob.status == "pending", LinkJob.workspace_id.is_not(None))
    )
    if workspace_id is not None:
        remaining_pending_stmt = remaining_pending_stmt.where(LinkJob.workspace_id == workspace_id)
    remaining_pending = db.scalar(remaining_pending_stmt) or 0

    return {
        "processed": processed,
        "edges_created": edges_created,
        "proposals_created": proposals_created,
        "duplicates_skipped": duplicates_skipped,
        "failed": failed,
        "remaining_pending": remaining_pending,
    }


def func_count():
    from sqlalchemy import func

    return func.count()


def apply_link_proposal(db: Session, proposal_id: int) -> LinkProposal | None:
    proposal = db.get(LinkProposal, proposal_id)
    if proposal is None:
        return None
    if not _edge_exists(db, proposal.workspace_id, proposal.source_node_id, proposal.target_node_id, proposal.relation_type):
        edge = Edge(
            workspace_id=proposal.workspace_id,
            from_node_id=proposal.source_node_id,
            to_node_id=proposal.target_node_id,
            type=proposal.relation_type,
            weight=proposal.weight,
            confidence=proposal.confidence,
            created_by="linker_review",
            evidence=proposal.evidence,
            metadata_json={
                "semantic_score": proposal.semantic_score,
                "lexical_score": proposal.lexical_score,
                "combined_score": proposal.combined_score,
                "proposal_id": proposal.id,
            },
        )
        db.add(edge)
    proposal.status = "applied"
    db.commit()
    db.refresh(proposal)
    return proposal


def reject_link_proposal(db: Session, proposal_id: int) -> LinkProposal | None:
    proposal = db.get(LinkProposal, proposal_id)
    if proposal is None:
        return None
    db.delete(proposal)
    db.commit()
    return proposal
