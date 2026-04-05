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

EDGE_TYPES = {
    "similar_to",
    "expands",
    "contradicts",
    "supports",
    "led_to",
    "belongs_to_topic",
    "derived_from",
    "mentions",
    "inspired_by",
    "part_of",
    "reply_to",
}


def validate_node_type(value: str) -> str:
    if value not in NODE_TYPES:
        allowed = ", ".join(sorted(NODE_TYPES))
        raise ValueError(f"Invalid node type '{value}'. Allowed: {allowed}")
    return value


def validate_edge_type(value: str) -> str:
    if value not in EDGE_TYPES:
        allowed = ", ".join(sorted(EDGE_TYPES))
        raise ValueError(f"Invalid edge type '{value}'. Allowed: {allowed}")
    return value
