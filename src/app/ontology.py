from __future__ import annotations

NODE_TYPES = {
    "line",
    "quote",
    "paragraph",
    "idea",
    "thought_piece",
    "article_candidate",
    "article",
    "topic",
    "document",
}


def validate_node_type(value: str) -> str:
    if value not in NODE_TYPES:
        allowed = ", ".join(sorted(NODE_TYPES))
        raise ValueError(f"Invalid node type '{value}'. Allowed: {allowed}")
    return value


def validate_edge_type(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Edge type/note cannot be empty.")
    return value
