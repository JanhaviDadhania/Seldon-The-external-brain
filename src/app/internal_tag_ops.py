from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .edge_creation_ops import _extract_internal_tags, _extract_internal_tags_batch
from .models import InternalTag, InternalTagMembership, Node


def merge_internal_tag_metadata(metadata_json: dict, raw_text: str, settings: Settings | None = None) -> dict:
    merged = dict(metadata_json)
    tags = _extract_internal_tags(raw_text, settings=settings)
    merged["linker_tags"] = {
        "keywords": tags.keywords,
        "concepts": tags.concepts,
    }
    return merged


def ensure_node_internal_tag_metadata(node: Node, settings: Settings | None = None) -> bool:
    linker_tags = ((node.metadata_json or {}).get("linker_tags") or {})
    if linker_tags.get("keywords") and linker_tags.get("concepts"):
        return False
    node.metadata_json = merge_internal_tag_metadata(node.metadata_json or {}, node.raw_text, settings=settings)
    return True


def ensure_nodes_internal_tag_metadata(nodes: list[Node], settings: Settings | None = None) -> bool:
    missing_nodes: list[Node] = []
    for node in nodes:
        linker_tags = ((node.metadata_json or {}).get("linker_tags") or {})
        if linker_tags.get("keywords") and linker_tags.get("concepts"):
            continue
        missing_nodes.append(node)

    if not missing_nodes:
        return False

    extracted = _extract_internal_tags_batch(
        [node.raw_text for node in missing_nodes],
        settings=settings,
    )
    for node, tags in zip(missing_nodes, extracted, strict=False):
        merged = dict(node.metadata_json or {})
        merged["linker_tags"] = {
            "keywords": tags.keywords,
            "concepts": tags.concepts,
        }
        node.metadata_json = merged
    return True


def sync_node_internal_tags(db: Session, node: Node) -> None:
    db.query(InternalTagMembership).filter(
        InternalTagMembership.node_id == node.id,
        InternalTagMembership.workspace_id == node.workspace_id,
    ).delete(synchronize_session=False)
    if node.status == "deleted":
        db.flush()
        return

    linker_tags = ((node.metadata_json or {}).get("linker_tags") or {})
    grouped_tags = {
        "keyword": linker_tags.get("keywords", []),
        "concept": linker_tags.get("concepts", []),
    }

    existing_tags = {
        (tag.tag_type, tag.tag_value): tag
        for tag in db.scalars(select(InternalTag).where(InternalTag.workspace_id == node.workspace_id))
    }

    for tag_type, values in grouped_tags.items():
        for value in values:
            key = (tag_type, value)
            tag = existing_tags.get(key)
            if tag is None:
                tag = InternalTag(workspace_id=node.workspace_id, tag_value=value, tag_type=tag_type)
                db.add(tag)
                db.flush()
                existing_tags[key] = tag
            db.add(
                InternalTagMembership(
                    workspace_id=node.workspace_id,
                    tag_id=tag.id,
                    node_id=node.id,
                    score=1.0,
                    metadata_json={"tag_type": tag_type},
                )
            )
    db.flush()


def shared_internal_tags_for_node(db: Session, node: Node) -> dict[int, dict[str, list[str]]]:
    memberships = list(
        db.scalars(
            select(InternalTagMembership).where(
                InternalTagMembership.node_id == node.id,
                InternalTagMembership.workspace_id == node.workspace_id,
            )
        )
    )
    if not memberships:
        return {}

    tag_ids = [membership.tag_id for membership in memberships]
    tag_map = {
        tag.id: tag
        for tag in db.scalars(
            select(InternalTag).where(
                InternalTag.workspace_id == node.workspace_id,
                InternalTag.id.in_(tag_ids),
            )
        )
    }

    reverse_rows = list(
        db.scalars(
            select(InternalTagMembership).where(
                InternalTagMembership.workspace_id == node.workspace_id,
                InternalTagMembership.tag_id.in_(tag_ids),
                InternalTagMembership.node_id != node.id,
            )
        )
    )

    shared: dict[int, dict[str, list[str]]] = defaultdict(lambda: {"keywords": [], "concepts": []})
    for membership in reverse_rows:
        tag = tag_map.get(membership.tag_id)
        if tag is None:
            continue
        key = "keywords" if tag.tag_type == "keyword" else "concepts"
        shared[membership.node_id][key].append(tag.tag_value)
    return dict(shared)
