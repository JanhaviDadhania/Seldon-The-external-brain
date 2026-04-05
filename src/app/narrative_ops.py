from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .models import Edge, Node
from .traversal_ops import TraversedNode


def build_narrative_prompt(
    root: Node,
    traversed_nodes: list[TraversedNode],
    edges: list[Edge],
    paragraphs: int = 2,
) -> str:
    node_lines = []
    for item in traversed_nodes:
        text = item.node.normalized_text or item.node.raw_text
        node_lines.append(
            f"- node_id={item.node.id} depth={item.depth} path_score={item.path_score:.2f} type={item.node.type}: {text}"
        )

    edge_lines = [
        f"- {edge.from_node_id} -> {edge.to_node_id} type={edge.type} weight={edge.weight:.2f}"
        for edge in edges
    ]

    return f"""You are helping turn a user's thought graph into a short narrative.

Write exactly {paragraphs} paragraphs.
Keep the output concise, vivid, and coherent.
Do not mention node ids, graph structure, metadata, or "the graph".
Write as if you are narrating the evolution of the user's thought.
Stay grounded in the provided notes and relations. Do not invent major facts not supported by the notes.

Root thought:
{root.normalized_text or root.raw_text}

Related notes:
{chr(10).join(node_lines) if node_lines else "- none"}

Edges:
{chr(10).join(edge_lines) if edge_lines else "- none"}

Return plain text only."""


def request_ollama_narrative(
    settings: Settings,
    prompt: str,
    model_name: str | None = None,
) -> str:
    response = httpx.post(
        f"{settings.ollama_base_url.rstrip('/')}/api/generate",
        json={
            "model": model_name or settings.ollama_narrative_model,
            "prompt": prompt,
            "stream": False,
        },
        timeout=settings.ollama_timeout_seconds,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    narrative = str(payload.get("response", "")).strip()
    if not narrative:
        raise ValueError("Ollama returned an empty narrative response")
    return narrative
