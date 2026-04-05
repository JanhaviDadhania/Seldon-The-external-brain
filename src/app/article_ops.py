from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ArticleDraft, ArticleDraftVersion, Node
from .traversal_ops import build_outline_sections, collect_subgraph


def derive_article_title(root: Node, explicit_title: str | None = None) -> str:
    if explicit_title:
        return explicit_title.strip()

    normalization = (root.metadata_json or {}).get("normalization", {})
    title = normalization.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()

    text = root.normalized_text or root.raw_text
    title = text.strip().split(".")[0][:80].strip()
    return title or f"Article from Node {root.id}"


def build_outline_plan(
    db: Session,
    workspace_id: int,
    root_node_id: int,
    depth: int = 2,
    max_nodes: int = 12,
    edge_type: str | None = None,
) -> dict[str, object]:
    root, traversed_nodes, edges = collect_subgraph(
        db,
        workspace_id=workspace_id,
        root_node_id=root_node_id,
        depth=depth,
        limit=max_nodes,
        edge_type=edge_type,
    )
    sections = build_outline_sections(root, traversed_nodes, edges)
    return {
        "root_node": root,
        "nodes": traversed_nodes,
        "edges": edges,
        "sections": sections,
    }


def compose_markdown_from_plan(
    root: Node,
    sections: list[dict[str, object]],
    node_lookup: dict[int, Node],
    title: str,
) -> tuple[str, list[dict[str, object]]]:
    lines = [f"# {title}", "", root.normalized_text or root.raw_text, ""]
    provenance: list[dict[str, object]] = [
        {
            "heading": "Introduction",
            "node_ids": [root.id],
        }
    ]

    for section in sections:
        heading = str(section["heading"])
        node_ids = [int(node_id) for node_id in section["node_ids"]]
        lines.append(f"## {heading}")
        provenance.append({"heading": heading, "node_ids": node_ids})

        section_lines: list[str] = []
        for node_id in node_ids:
            node = node_lookup.get(node_id)
            if node is None or node.status == "deleted":
                continue
            section_lines.append(f"- {node.normalized_text or node.raw_text}")

        if not section_lines:
            section_lines.append("- No active source nodes available for this section.")

        lines.extend(section_lines)
        lines.append("")

    return "\n".join(lines).strip() + "\n", provenance


def create_article_draft(
    db: Session,
    workspace_id: int,
    root_node_id: int,
    depth: int = 2,
    max_nodes: int = 12,
    edge_type: str | None = None,
    title: str | None = None,
    status: str = "draft",
) -> ArticleDraft:
    plan = build_outline_plan(
        db,
        workspace_id=workspace_id,
        root_node_id=root_node_id,
        depth=depth,
        max_nodes=max_nodes,
        edge_type=edge_type,
    )
    root = plan["root_node"]
    sections = plan["sections"]
    node_lookup = {item.node.id: item.node for item in plan["nodes"]}

    draft_title = derive_article_title(root, explicit_title=title)
    markdown, provenance = compose_markdown_from_plan(root, sections, node_lookup, draft_title)
    draft = ArticleDraft(
        workspace_id=workspace_id,
        title=draft_title,
        root_node_id=root.id,
        status=status,
        outline_json=sections,
        content_markdown=markdown,
        provenance_json=provenance,
        metadata_json={
            "depth": depth,
            "max_nodes": max_nodes,
            "edge_type": edge_type,
            "source_node_ids": sorted(node_lookup.keys()),
        },
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def create_article_draft_version(db: Session, draft: ArticleDraft, reason: str) -> ArticleDraftVersion:
    next_version = (
        db.scalar(
            select(ArticleDraftVersion.version_number)
            .where(ArticleDraftVersion.draft_id == draft.id)
            .order_by(ArticleDraftVersion.version_number.desc())
            .limit(1)
        )
        or 0
    ) + 1
    version = ArticleDraftVersion(
        workspace_id=draft.workspace_id,
        draft_id=draft.id,
        version_number=next_version,
        reason=reason,
        snapshot_json={
            "title": draft.title,
            "root_node_id": draft.root_node_id,
            "status": draft.status,
            "outline_json": draft.outline_json,
            "content_markdown": draft.content_markdown,
            "provenance_json": draft.provenance_json,
            "metadata_json": draft.metadata_json,
        },
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version
