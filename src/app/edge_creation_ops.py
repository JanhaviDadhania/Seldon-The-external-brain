from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import md5
import json
import math
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import ExperimentalHub, ExperimentalHubMembership, Node
from .schemas import (
    EdgeCreationConfig,
    EdgeCreationEdgeResult,
    EdgeCreationError,
    EdgeCreationHubResult,
    EdgeCreationNodeInput,
    EdgeCreationPair,
    EdgeCreationRequest,
    EdgeCreationResponse,
    EdgeCreationSummary,
)


EDGE_CREATION_FUNCTIONS = {
    "tag_matcher",
    "embedding_matcher",
    "llm_matcher",
    "llm_debator",
    "hub_matcher",
}

DEFAULT_EDGE_TYPES = [
    "similar_to",
    "supports",
    "contradicts",
    "expands",
    "led_to",
    "belongs_to_topic",
]

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "does",
    "etc",
    "for",
    "from",
    "have",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "like",
    "not",
    "now",
    "of",
    "on",
    "or",
    "same",
    "should",
    "so",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "they",
    "this",
    "to",
    "we",
    "what",
    "while",
    "will",
    "with",
    "would",
}

CONTRAST_WORDS = {"but", "however", "instead", "except", "unless", "yet"}


@dataclass
class InternalTags:
    keywords: list[str]
    concepts: list[str]


def _internal_tags_from_metadata(metadata: dict[str, Any] | None) -> InternalTags | None:
    linker_tags = ((metadata or {}).get("linker_tags") or {})
    keywords = [value for value in linker_tags.get("keywords", []) if value]
    concepts = [value for value in linker_tags.get("concepts", []) if value]
    if not keywords and not concepts:
        return None
    return InternalTags(keywords=keywords, concepts=concepts)


def _normalize_token(token: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "", token.lower())
    if len(token) > 4 and token.endswith("ing"):
        token = token[:-3]
    elif len(token) > 3 and token.endswith("ed"):
        token = token[:-2]
    elif len(token) > 3 and token.endswith("es"):
        token = token[:-2]
    elif len(token) > 2 and token.endswith("s"):
        token = token[:-1]
    return token


def _tokenize(text: str) -> list[str]:
    normalized = [_normalize_token(part) for part in re.split(r"\W+", text.lower())]
    return [token for token in normalized if token and token not in STOPWORDS]


def _heuristic_extract_internal_tags(text: str) -> InternalTags:
    tokens = _tokenize(text)
    keyword_counter = Counter(tokens)
    keywords = [token for token, _ in keyword_counter.most_common(8)]

    concepts: list[str] = []
    seen: set[str] = set()
    for size in (2, 3):
        for index in range(len(tokens) - size + 1):
            phrase = "_".join(tokens[index : index + size])
            if phrase in seen:
                continue
            seen.add(phrase)
            concepts.append(phrase)
            if len(concepts) >= 8:
                break
        if len(concepts) >= 8:
            break

    return InternalTags(keywords=keywords, concepts=concepts)


def _sanitize_generated_tag(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_ -]+", "", str(value).strip().lower())
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _dedupe_preserve_order(values: Iterable[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _build_ollama_tag_prompt(text: str) -> str:
    return f"""I am designing external brain application. It is designed on graph structure. My notes, ideas, documents are stored in nodes of the graph. To generate emergent structure, we need to automatically generate edges of the graph. We are designing this system for 7 astronauts going to mars this year. They will use it to generate and store everything they are learning there. You are responsible for part of edge creation were we generate tags for every node.

Create exactly 15 tags for the node below:
- 8 keywords
- 7 concepts

Requirements:
- tags must describe the actual idea, concept, subject, or mechanism in the node
- lowercase only
- no explanations
- no duplicate tags
- concepts should use underscores for multi-word phrases
- concepts must be canonical normalized labels, not surface phrasing
- prefer noun forms over adjective forms when possible
- prefer underlying domains or stable abstractions over descriptive variants
- for example, use `biology` instead of `biological`, `cybernetics` instead of `cybernetic`, `organism` instead of `organisms` when plurality is not essential
- avoid weak tags copied directly from sentence scaffolding
- return strict JSON only
- JSON schema:
{{
  "keywords": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8"],
  "concepts": ["concept1", "concept2", "concept3", "concept4", "concept5", "concept6", "concept7"]
}}

For example, if the text is "software systems should be designed like biological systems", good tags include:
- keywords: ["software_systems", "system_design", "adaptation", "architecture"]
- concepts: ["biology", "cybernetics", "complex_systems", "software_architecture"]

Avoid tags like:
- "biological"
- "designed"
- "should"

Node text:
[NODE_TEXT]
{text.strip()}
[/NODE_TEXT]"""


def _build_ollama_batch_tag_prompt(texts: list[str]) -> str:
    items = "\n".join(
        f"- input_index: {index}\n  text: \"\"\"{item.strip()}\"\"\""
        for index, item in enumerate(texts)
    )
    return f"""I am designing external brain application. It is designed on graph structure. My notes, ideas, documents are stored in nodes of the graph. To generate emergent structure, we need to automatically generate edges of the graph. We are designing this system for 7 astronauts going to mars this year. They will use it to generate and store everything they are learning there. You are responsible for part of edge creation were we generate tags for every node.

For each node below, create exactly 15 tags:
- 8 keywords
- 7 concepts

Requirements:
- tags must describe the actual idea, concept, subject, or mechanism in the node
- lowercase only
- no explanations
- no duplicate tags per node
- concepts should use underscores for multi-word phrases
- concepts must be canonical normalized labels, not surface phrasing
- prefer noun forms over adjective forms when possible
- prefer underlying domains or stable abstractions over descriptive variants
- for example, use `biology` instead of `biological`, `cybernetics` instead of `cybernetic`, `organism` instead of `organisms` when plurality is not essential
- avoid weak tags copied directly from sentence scaffolding
- return strict JSON only
- output schema:
{{
  "items": [
    {{
      "input_index": 0,
      "keywords": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8"],
      "concepts": ["concept1", "concept2", "concept3", "concept4", "concept5", "concept6", "concept7"]
    }}
  ]
}}

Batch nodes:
{items}"""

def _parse_ollama_tag_payload(payload: dict[str, Any]) -> InternalTags:
    keywords = _dedupe_preserve_order(
        (_sanitize_generated_tag(value) for value in payload.get("keywords", [])),
        8,
    )
    concepts = _dedupe_preserve_order(
        (_sanitize_generated_tag(value) for value in payload.get("concepts", [])),
        7,
    )
    return InternalTags(keywords=keywords, concepts=concepts)


def _request_ollama_tags(text: str, settings: Settings, model_name: str | None = None) -> InternalTags:
    response = httpx.post(
        f"{settings.ollama_base_url.rstrip('/')}/api/generate",
        json={
            "model": model_name or settings.ollama_tag_model,
            "prompt": _build_ollama_tag_prompt(text),
            "stream": False,
            "format": "json",
        },
        timeout=settings.ollama_timeout_seconds,
    )
    response.raise_for_status()
    body = response.json()
    raw = body.get("response", "").strip()
    if not raw:
        raise ValueError("Ollama returned an empty tag response")
    parsed = json.loads(raw)
    tags = _parse_ollama_tag_payload(parsed)
    if not tags.keywords or not tags.concepts:
        raise ValueError("Ollama did not return both keywords and concepts")
    return tags


def _request_ollama_tags_batch(
    texts: list[str],
    settings: Settings,
    model_name: str | None = None,
) -> list[InternalTags]:
    response = httpx.post(
        f"{settings.ollama_base_url.rstrip('/')}/api/generate",
        json={
            "model": model_name or settings.ollama_tag_model,
            "prompt": _build_ollama_batch_tag_prompt(texts),
            "stream": False,
            "format": "json",
        },
        timeout=settings.ollama_timeout_seconds,
    )
    response.raise_for_status()
    body = response.json()
    raw = body.get("response", "").strip()
    if not raw:
        raise ValueError("Ollama returned an empty batch tag response")
    parsed = json.loads(raw)
    items = parsed.get("items")
    if not isinstance(items, list):
        raise ValueError("Ollama batch response did not include items")

    result: list[InternalTags | None] = [None] * len(texts)
    for item in items:
        if not isinstance(item, dict):
            continue
        input_index = item.get("input_index")
        if not isinstance(input_index, int) or not 0 <= input_index < len(texts):
            continue
        result[input_index] = _parse_ollama_tag_payload(item)

    if any(tags is None or not tags.keywords or not tags.concepts for tags in result):
        raise ValueError("Ollama batch response was incomplete")
    return [tags for tags in result if tags is not None]


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _extract_internal_tags_batch(
    texts: list[str],
    settings: Settings | None = None,
    model_name: str | None = None,
) -> list[InternalTags]:
    if not texts:
        return []

    effective_settings = settings or get_settings()
    if effective_settings.use_ollama_for_internal_tags:
        batch_size = max(1, effective_settings.ollama_tag_batch_size)
        try:
            tags: list[InternalTags] = []
            for batch in _chunked(texts, batch_size):
                tags.extend(_request_ollama_tags_batch(batch, effective_settings, model_name=model_name))
            return tags
        except Exception:
            pass

    return [_heuristic_extract_internal_tags(text) for text in texts]


def _extract_internal_tags(text: str, settings: Settings | None = None, model_name: str | None = None) -> InternalTags:
    return _extract_internal_tags_batch([text], settings=settings, model_name=model_name)[0]


def _hash_embedding(text: str, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokenize(text):
        digest = md5(token.encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % dimensions
        sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
        vector[index] += sign
    return vector


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(left * right for left, right in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(value * value for value in a))
    norm_b = math.sqrt(sum(value * value for value in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _lexical_overlap(left: str, right: str) -> float:
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _resolve_nodes(db: Session, request: EdgeCreationRequest) -> list[EdgeCreationNodeInput]:
    if request.nodes:
        return request.nodes
    if not request.node_ids:
        return []

    stmt = select(Node).where(Node.id.in_(request.node_ids)).order_by(Node.id)
    if request.workspace_id is not None:
        stmt = stmt.where(Node.workspace_id == request.workspace_id)
    found = {node.id: node for node in db.scalars(stmt)}
    nodes: list[EdgeCreationNodeInput] = []
    for node_id in request.node_ids:
        node = found.get(node_id)
        if node is None:
            continue
        nodes.append(
            EdgeCreationNodeInput(
                id=node.id,
                type=node.type,
                raw_text=node.raw_text,
                normalized_text=node.normalized_text,
                user_tags=node.tags,
                metadata=node.metadata_json,
            )
        )
    return nodes


def _enumerate_pairs(
    nodes: list[EdgeCreationNodeInput],
    pairs: list[EdgeCreationPair],
    max_pairs: int | None,
) -> list[tuple[EdgeCreationNodeInput, EdgeCreationNodeInput]]:
    node_map = {node.id: node for node in nodes}
    resolved: list[tuple[EdgeCreationNodeInput, EdgeCreationNodeInput]] = []

    if pairs:
        for pair in pairs:
            source = node_map.get(pair.source_node_id)
            target = node_map.get(pair.target_node_id)
            if source is None or target is None or source.id == target.id:
                continue
            resolved.append((source, target))
    else:
        for index, source in enumerate(nodes):
            for target in nodes[index + 1 :]:
                resolved.append((source, target))

    if max_pairs is not None:
        return resolved[:max_pairs]
    return resolved


def _edge_type_for_pair(
    source: EdgeCreationNodeInput,
    target: EdgeCreationNodeInput,
    similarity: float,
    overlap: float,
    allowed: set[str],
    mode: str,
) -> tuple[str, str]:
    source_text = source.raw_text.lower()
    target_text = target.raw_text.lower()

    if "belongs_to_topic" in allowed and (source.type == "topic" or target.type == "topic"):
        return "belongs_to_topic", "One node is a topic"

    contrastive = any(word in source_text.split() or word in target_text.split() for word in CONTRAST_WORDS)
    if mode in {"llm_matcher", "llm_debator"} and contrastive and "contradicts" in allowed:
        return "contradicts", "Contrastive wording suggests tension"

    if similarity >= 0.7 and "similar_to" in allowed:
        return "similar_to", "High semantic similarity"

    if overlap >= 0.24 and "expands" in allowed and abs(len(source.raw_text) - len(target.raw_text)) > 50:
        return "expands", "Shared language with differing detail depth"

    if "supports" in allowed:
        return "supports", "Moderate semantic overlap"

    first = next(iter(allowed), "similar_to")
    return first, "Fallback allowed edge type"


def _build_edge_result(
    function_name: str,
    source: EdgeCreationNodeInput,
    target: EdgeCreationNodeInput,
    edge_type: str,
    score: float,
    confidence: float,
    evidence: dict[str, Any],
) -> EdgeCreationEdgeResult:
    return EdgeCreationEdgeResult(
        source_node_id=source.id,
        target_node_id=target.id,
        edge_type=edge_type,
        score=max(0.0, min(score, 1.0)),
        confidence=max(0.0, min(confidence, 1.0)),
        should_create=True,
        evidence=evidence,
        metadata={"function_name": function_name},
    )


def _empty_response(function_name: str, run_id: str | None, errors: list[EdgeCreationError] | None = None) -> EdgeCreationResponse:
    return EdgeCreationResponse(
        function_name=function_name,
        run_id=run_id,
        status="ok" if not errors else "partial",
        summary=EdgeCreationSummary(nodes_seen=0, pairs_considered=0, edges_proposed=0, hubs_proposed=0),
        edges=[],
        hubs=[],
        errors=errors or [],
    )


def run_tag_matcher(
    db: Session,
    request: EdgeCreationRequest,
    settings: Settings | None = None,
) -> EdgeCreationResponse:
    nodes = _resolve_nodes(db, request)
    if not nodes:
        return _empty_response(request.function_name, request.run_id)

    effective_settings = settings or get_settings()
    model_name = request.config.extra.get("model_name") if request.config.extra else None
    allowed = set(request.config.edge_types_allowed or DEFAULT_EDGE_TYPES)
    pairs = _enumerate_pairs(nodes, request.pairs, request.config.max_pairs)
    tag_map: dict[int, InternalTags] = {}
    missing_nodes: list[EdgeCreationNodeInput] = []
    for node in nodes:
        stored_tags = _internal_tags_from_metadata(node.metadata)
        if stored_tags is not None:
            tag_map[node.id] = stored_tags
            continue
        missing_nodes.append(node)

    if missing_nodes:
        extracted_tags = _extract_internal_tags_batch(
            [node.raw_text for node in missing_nodes],
            settings=effective_settings,
            model_name=model_name,
        )
        for node, tags in zip(missing_nodes, extracted_tags, strict=False):
            tag_map[node.id] = tags

    edges: list[EdgeCreationEdgeResult] = []
    for source, target in pairs:
        source_tags = tag_map[source.id]
        target_tags = tag_map[target.id]
        shared_keywords = sorted(set(source_tags.keywords) & set(target_tags.keywords))
        shared_concepts = sorted(set(source_tags.concepts) & set(target_tags.concepts))
        shared_total = len(shared_keywords) + len(shared_concepts)
        if shared_total == 0:
            continue
        base = max(1, min(len(source_tags.keywords) + len(source_tags.concepts), len(target_tags.keywords) + len(target_tags.concepts)))
        score = min(1.0, shared_total / base)
        edge_type, reason = _edge_type_for_pair(source, target, score, score, allowed, "tag_matcher")
        edges.append(
            _build_edge_result(
                "tag_matcher",
                source,
                target,
                edge_type,
                score,
                score,
                {
                    "shared_keywords": shared_keywords,
                    "shared_concepts": shared_concepts,
                    "cosine_similarity": None,
                    "llm_reasoning": None,
                    "debate_summary": None,
                    "hub_ids": [],
                    "reason": reason,
                },
            )
        )

    return EdgeCreationResponse(
        function_name="tag_matcher",
        run_id=request.run_id,
        status="ok",
        summary=EdgeCreationSummary(
            nodes_seen=len(nodes),
            pairs_considered=len(pairs),
            edges_proposed=len(edges),
            hubs_proposed=0,
        ),
        edges=edges,
        hubs=[],
        errors=[],
    )


def run_embedding_matcher(db: Session, request: EdgeCreationRequest) -> EdgeCreationResponse:
    nodes = _resolve_nodes(db, request)
    if not nodes:
        return _empty_response(request.function_name, request.run_id)

    threshold = request.config.threshold if request.config.threshold is not None else 0.58
    allowed = set(request.config.edge_types_allowed or DEFAULT_EDGE_TYPES)
    pairs = _enumerate_pairs(nodes, request.pairs, request.config.max_pairs)
    vector_map = {node.id: _hash_embedding(node.raw_text) for node in nodes}

    edges: list[EdgeCreationEdgeResult] = []
    for source, target in pairs:
        similarity = _cosine_similarity(vector_map[source.id], vector_map[target.id])
        if similarity < threshold:
            continue
        overlap = _lexical_overlap(source.raw_text, target.raw_text)
        edge_type, reason = _edge_type_for_pair(source, target, similarity, overlap, allowed, "embedding_matcher")
        edges.append(
            _build_edge_result(
                "embedding_matcher",
                source,
                target,
                edge_type,
                similarity,
                similarity,
                {
                    "shared_keywords": [],
                    "shared_concepts": [],
                    "cosine_similarity": similarity,
                    "llm_reasoning": None,
                    "debate_summary": None,
                    "hub_ids": [],
                    "reason": reason,
                },
            )
        )

    return EdgeCreationResponse(
        function_name="embedding_matcher",
        run_id=request.run_id,
        status="ok",
        summary=EdgeCreationSummary(
            nodes_seen=len(nodes),
            pairs_considered=len(pairs),
            edges_proposed=len(edges),
            hubs_proposed=0,
        ),
        edges=edges,
        hubs=[],
        errors=[],
    )


def run_llm_matcher(db: Session, request: EdgeCreationRequest) -> EdgeCreationResponse:
    nodes = _resolve_nodes(db, request)
    if not nodes:
        return _empty_response(request.function_name, request.run_id)

    threshold = request.config.threshold if request.config.threshold is not None else 0.45
    allowed = set(request.config.edge_types_allowed or DEFAULT_EDGE_TYPES)
    pairs = _enumerate_pairs(nodes, request.pairs, request.config.max_pairs)

    edges: list[EdgeCreationEdgeResult] = []
    for source, target in pairs:
        similarity = _cosine_similarity(_hash_embedding(source.raw_text), _hash_embedding(target.raw_text))
        overlap = _lexical_overlap(source.raw_text, target.raw_text)
        score = (similarity * 0.72) + (overlap * 0.28)
        if score < threshold:
            continue
        edge_type, reason = _edge_type_for_pair(source, target, similarity, overlap, allowed, "llm_matcher")
        edges.append(
            _build_edge_result(
                "llm_matcher",
                source,
                target,
                edge_type,
                score,
                min(1.0, score + 0.08),
                {
                    "shared_keywords": [],
                    "shared_concepts": [],
                    "cosine_similarity": similarity,
                    "llm_reasoning": f"Heuristic LLM placeholder selected {edge_type}. {reason}.",
                    "debate_summary": None,
                    "hub_ids": [],
                    "reason": reason,
                },
            )
        )

    return EdgeCreationResponse(
        function_name="llm_matcher",
        run_id=request.run_id,
        status="ok",
        summary=EdgeCreationSummary(
            nodes_seen=len(nodes),
            pairs_considered=len(pairs),
            edges_proposed=len(edges),
            hubs_proposed=0,
        ),
        edges=edges,
        hubs=[],
        errors=[],
    )


def run_llm_debator(db: Session, request: EdgeCreationRequest) -> EdgeCreationResponse:
    nodes = _resolve_nodes(db, request)
    if not nodes:
        return _empty_response(request.function_name, request.run_id)

    threshold = request.config.threshold if request.config.threshold is not None else 0.42
    allowed = set(request.config.edge_types_allowed or DEFAULT_EDGE_TYPES)
    pairs = _enumerate_pairs(nodes, request.pairs, request.config.max_pairs)

    edges: list[EdgeCreationEdgeResult] = []
    for source, target in pairs:
        similarity = _cosine_similarity(_hash_embedding(source.raw_text), _hash_embedding(target.raw_text))
        overlap = _lexical_overlap(source.raw_text, target.raw_text)
        score = (similarity * 0.7) + (overlap * 0.3)
        if score < threshold:
            continue
        edge_type, reason = _edge_type_for_pair(source, target, similarity, overlap, allowed, "llm_debator")
        pro_argument = f"A argues the pair shares meaningful conceptual overlap ({score:.2f})."
        con_argument = f"B argues the pair may only share surface language ({overlap:.2f})."
        judge = f"C selects {edge_type} because {reason.lower()}."
        edges.append(
            _build_edge_result(
                "llm_debator",
                source,
                target,
                edge_type,
                score,
                min(1.0, score + 0.1),
                {
                    "shared_keywords": [],
                    "shared_concepts": [],
                    "cosine_similarity": similarity,
                    "llm_reasoning": None,
                    "debate_summary": {
                        "pro": pro_argument,
                        "con": con_argument,
                        "judge": judge,
                    },
                    "hub_ids": [],
                    "reason": reason,
                },
            )
        )

    return EdgeCreationResponse(
        function_name="llm_debator",
        run_id=request.run_id,
        status="ok",
        summary=EdgeCreationSummary(
            nodes_seen=len(nodes),
            pairs_considered=len(pairs),
            edges_proposed=len(edges),
            hubs_proposed=0,
        ),
        edges=edges,
        hubs=[],
        errors=[],
    )


def _persist_hubs(
    db: Session,
    workspace_id: int | None,
    hubs: Iterable[EdgeCreationHubResult],
    matcher_name: str,
) -> None:
    if workspace_id is None:
        return
    for hub in hubs:
        signature = f"{matcher_name}:{hub.label.lower()}"
        record = db.scalar(
            select(ExperimentalHub).where(
                ExperimentalHub.workspace_id == workspace_id,
                ExperimentalHub.signature == signature,
            )
        )
        if record is None:
            record = ExperimentalHub(
                workspace_id=workspace_id,
                label=hub.label,
                signature=signature,
                matcher_name=matcher_name,
                score=hub.score,
                metadata_json=hub.metadata,
            )
            db.add(record)
            db.flush()
        else:
            record.label = hub.label
            record.score = hub.score
            record.metadata_json = hub.metadata

        existing = {
            membership.node_id: membership
            for membership in db.scalars(
                select(ExperimentalHubMembership).where(
                    ExperimentalHubMembership.workspace_id == workspace_id,
                    ExperimentalHubMembership.hub_id == record.id,
                )
            )
        }
        for node_id in hub.source_node_ids:
            membership = existing.get(node_id)
            if membership is None:
                db.add(
                    ExperimentalHubMembership(
                        workspace_id=workspace_id,
                        hub_id=record.id,
                        node_id=node_id,
                        score=hub.score,
                        metadata_json={"matcher_name": matcher_name},
                    )
                )
            else:
                membership.score = hub.score
                membership.metadata_json = {"matcher_name": matcher_name}
    db.commit()


def run_hub_matcher(db: Session, request: EdgeCreationRequest) -> EdgeCreationResponse:
    nodes = _resolve_nodes(db, request)
    if not nodes:
        return _empty_response(request.function_name, request.run_id)

    concept_to_nodes: dict[str, list[int]] = defaultdict(list)
    concept_scores: Counter[str] = Counter()
    for node in nodes:
        tags = _extract_internal_tags(node.raw_text)
        for concept in tags.concepts[:4]:
            concept_to_nodes[concept].append(node.id)
            concept_scores[concept] += 1

    hubs: list[EdgeCreationHubResult] = []
    for concept, node_ids in concept_to_nodes.items():
        unique_ids = sorted(set(node_ids))
        if len(unique_ids) < 2:
            continue
        score = min(1.0, len(unique_ids) / max(2, len(nodes)))
        hubs.append(
            EdgeCreationHubResult(
                hub_temp_id=f"hub:{concept}",
                label=concept.replace("_", " "),
                score=score,
                source_node_ids=unique_ids,
                metadata={"matcher_name": "hub_matcher", "concept_frequency": concept_scores[concept]},
            )
        )

    _persist_hubs(db, request.workspace_id, hubs, "hub_matcher")

    return EdgeCreationResponse(
        function_name="hub_matcher",
        run_id=request.run_id,
        status="ok",
        summary=EdgeCreationSummary(
            nodes_seen=len(nodes),
            pairs_considered=0,
            edges_proposed=0,
            hubs_proposed=len(hubs),
        ),
        edges=[],
        hubs=hubs,
        errors=[],
    )


def run_edge_creation_function(
    db: Session,
    request: EdgeCreationRequest,
    settings: Settings | None = None,
) -> EdgeCreationResponse:
    if request.function_name not in EDGE_CREATION_FUNCTIONS:
        return _empty_response(
            request.function_name,
            request.run_id,
            errors=[
                EdgeCreationError(
                    code="unknown_function",
                    message=f"Unknown edge creation function: {request.function_name}",
                )
            ],
        )

    request.config = request.config or EdgeCreationConfig()

    if request.function_name == "tag_matcher":
        return run_tag_matcher(db, request, settings=settings)
    if request.function_name == "embedding_matcher":
        return run_embedding_matcher(db, request)
    if request.function_name == "llm_matcher":
        return run_llm_matcher(db, request)
    if request.function_name == "llm_debator":
        return run_llm_debator(db, request)
    return run_hub_matcher(db, request)
