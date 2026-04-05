from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Edge, Node


RELATION_SECTION_TITLES = {
    "supports": "Supporting Ideas",
    "expands": "Expanded Threads",
    "contradicts": "Counterpoints",
    "belongs_to_topic": "Topic Connections",
    "similar_to": "Parallel Thoughts",
    "derived_from": "Derived Material",
    "mentions": "Mentions",
    "inspired_by": "Inspirations",
    "part_of": "Composed Parts",
    "reply_to": "Replies",
}


@dataclass
class NeighborResult:
    edge: Edge
    node: Node
    direction: str


@dataclass
class TraversedNode:
    node: Node
    depth: int
    path_score: float
    via_edge_id: int | None


def _edge_matches(edge: Edge, edge_type: str | None) -> bool:
    return edge_type is None or edge.type == edge_type


def fetch_neighbors(
    db: Session,
    workspace_id: int,
    node_id: int,
    direction: str = "both",
    edge_type: str | None = None,
    limit: int = 20,
) -> list[NeighborResult]:
    results: list[NeighborResult] = []

    if direction in {"outgoing", "both"}:
        outgoing = list(
            db.scalars(
                select(Edge)
                .where(Edge.workspace_id == workspace_id, Edge.from_node_id == node_id)
                .order_by(Edge.weight.desc(), Edge.id)
                .limit(limit)
            )
        )
        for edge in outgoing:
            if not _edge_matches(edge, edge_type):
                continue
            node = db.get(Node, edge.to_node_id)
            if node is None or node.status == "deleted":
                continue
            if node.workspace_id != workspace_id:
                continue
            results.append(NeighborResult(edge=edge, node=node, direction="outgoing"))

    if direction in {"incoming", "both"}:
        incoming = list(
            db.scalars(
                select(Edge)
                .where(Edge.workspace_id == workspace_id, Edge.to_node_id == node_id)
                .order_by(Edge.weight.desc(), Edge.id)
                .limit(limit)
            )
        )
        for edge in incoming:
            if not _edge_matches(edge, edge_type):
                continue
            node = db.get(Node, edge.from_node_id)
            if node is None or node.status == "deleted":
                continue
            if node.workspace_id != workspace_id:
                continue
            results.append(NeighborResult(edge=edge, node=node, direction="incoming"))

    results.sort(key=lambda item: (-item.edge.weight, item.edge.id, item.node.id))
    return results[:limit]


def collect_subgraph(
    db: Session,
    workspace_id: int,
    root_node_id: int,
    depth: int = 2,
    limit: int = 12,
    edge_type: str | None = None,
) -> tuple[Node, list[TraversedNode], list[Edge]]:
    root = db.get(Node, root_node_id)
    if root is None or root.status == "deleted" or root.workspace_id != workspace_id:
        raise ValueError("Root node not found")

    visited: dict[int, TraversedNode] = {
        root.id: TraversedNode(node=root, depth=0, path_score=1.0, via_edge_id=None)
    }
    queue: deque[tuple[int, int, float]] = deque([(root.id, 0, 1.0)])

    while queue and len(visited) < limit:
        current_id, current_depth, current_score = queue.popleft()
        if current_depth >= depth:
            continue

        neighbors = fetch_neighbors(
            db,
            workspace_id=workspace_id,
            node_id=current_id,
            direction="both",
            edge_type=edge_type,
            limit=limit * 2,
        )
        for neighbor in neighbors:
            candidate = neighbor.node
            if candidate.id == root.id:
                continue

            path_score = current_score * max(neighbor.edge.weight, 0.01)
            existing = visited.get(candidate.id)
            should_store = existing is None or path_score > existing.path_score
            if should_store:
                visited[candidate.id] = TraversedNode(
                    node=candidate,
                    depth=current_depth + 1,
                    path_score=path_score,
                    via_edge_id=neighbor.edge.id,
                )
                queue.append((candidate.id, current_depth + 1, path_score))

            if len(visited) >= limit:
                break

    ordered_nodes = sorted(
        visited.values(),
        key=lambda item: (item.depth, -item.path_score, item.node.id),
    )
    node_ids = {item.node.id for item in ordered_nodes}
    edges = list(
        db.scalars(
            select(Edge)
            .where(
                Edge.workspace_id == workspace_id,
                Edge.from_node_id.in_(node_ids),
                Edge.to_node_id.in_(node_ids),
            )
            .order_by(Edge.weight.desc(), Edge.id)
        )
    )
    if edge_type is not None:
        edges = [edge for edge in edges if edge.type == edge_type]
    return root, ordered_nodes, edges


def build_outline_sections(
    root: Node,
    traversed_nodes: list[TraversedNode],
    edges: list[Edge],
) -> list[dict[str, object]]:
    children = [item for item in traversed_nodes if item.node.id != root.id]
    if not children:
        return [
            {
                "heading": "Core Idea",
                "summary": root.normalized_text or root.raw_text,
                "node_ids": [root.id],
                "edge_types": [],
            }
        ]

    relation_by_node: dict[int, str] = {}
    for edge in edges:
        if edge.from_node_id == root.id and edge.to_node_id != root.id:
            relation_by_node.setdefault(edge.to_node_id, edge.type)
        elif edge.to_node_id == root.id and edge.from_node_id != root.id:
            relation_by_node.setdefault(edge.from_node_id, edge.type)

    groups: dict[str, list[TraversedNode]] = {}
    for item in children:
        relation = relation_by_node.get(item.node.id, "similar_to")
        groups.setdefault(relation, []).append(item)

    ordered_groups = sorted(
        groups.items(),
        key=lambda pair: (
            -max(item.path_score for item in pair[1]),
            RELATION_SECTION_TITLES.get(pair[0], pair[0].replace("_", " ").title()),
        ),
    )

    sections: list[dict[str, object]] = []
    for relation, items in ordered_groups:
        ordered_items = sorted(items, key=lambda item: (-item.path_score, item.node.id))
        sections.append(
            {
                "heading": RELATION_SECTION_TITLES.get(relation, relation.replace("_", " ").title()),
                "summary": ordered_items[0].node.normalized_text or ordered_items[0].node.raw_text,
                "node_ids": [item.node.id for item in ordered_items],
                "edge_types": [relation],
            }
        )
    return sections
