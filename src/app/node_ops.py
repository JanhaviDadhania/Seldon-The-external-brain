from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .internal_tag_ops import merge_internal_tag_metadata
from .models import Node, NodeVersion


def normalize_text(raw_text: str) -> str:
    collapsed = re.sub(r"\s+", " ", raw_text).strip()
    return collapsed


def derive_title_and_summary(normalized_text: str) -> tuple[str, str]:
    title = normalized_text[:80].strip()
    if len(normalized_text) > 80:
        title = title.rstrip() + "..."

    summary = normalized_text[:220].strip()
    if len(normalized_text) > 220:
        summary = summary.rstrip() + "..."

    return title, summary


def merge_normalization_metadata(
    metadata_json: dict[str, Any],
    normalized_text: str,
) -> dict[str, Any]:
    merged = dict(metadata_json)
    title, summary = derive_title_and_summary(normalized_text)
    merged["normalization"] = {
        "title": title,
        "summary": summary,
    }
    return merged


def derive_time_metadata(time_label: str) -> dict[str, Any]:
    stripped = time_label.strip()
    if not stripped:
        raise ValueError("time_label cannot be empty")

    year_match = re.search(r"\b(1[0-9]{3}|20[0-9]{2}|21[0-9]{2})\b", stripped)
    return {
        "label": stripped,
        "year": int(year_match.group(1)) if year_match else None,
    }


def merge_time_metadata(metadata_json: dict[str, Any], time_label: str | None) -> dict[str, Any]:
    merged = dict(metadata_json)
    if time_label is None:
        return merged
    merged["time"] = derive_time_metadata(time_label)
    return merged


def prepare_node_content(
    raw_text: str,
    metadata_json: dict[str, Any],
    normalized_text: str | None = None,
    settings: Settings | None = None,
) -> tuple[str, dict[str, Any]]:
    final_normalized = normalized_text.strip() if normalized_text else normalize_text(raw_text)
    final_metadata = merge_normalization_metadata(metadata_json, final_normalized)
    final_metadata = merge_internal_tag_metadata(final_metadata, raw_text, settings=settings)
    return final_normalized, final_metadata


def create_node_version(db: Session, node: Node, reason: str) -> NodeVersion:
    current_max = db.scalar(
        select(func.max(NodeVersion.version_number)).where(NodeVersion.node_id == node.id)
    )
    version_number = (current_max or 0) + 1

    version = NodeVersion(
        workspace_id=node.workspace_id,
        node_id=node.id,
        version_number=version_number,
        reason=reason,
        snapshot_json={
            "id": node.id,
            "workspace_id": node.workspace_id,
            "type": node.type,
            "raw_text": node.raw_text,
            "normalized_text": node.normalized_text,
            "source": node.source,
            "author": node.author,
            "telegram_message_id": node.telegram_message_id,
            "status": node.status,
            "tags": list(node.tags),
            "metadata_json": dict(node.metadata_json),
        },
    )
    db.add(version)
    db.flush()
    return version
