from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .embedding_ops import enqueue_embedding_job
from .internal_tag_ops import sync_node_internal_tags
from .linker_ops import enqueue_link_job
from .models import AppState, IngestionJob, Node, User
from .node_ops import prepare_node_content
from .workspace_ops import (
    get_active_workspace,
    get_active_workspace_for_user,
    get_or_create_user,
    get_workspace_by_name,
    switch_workspace_by_name,
    switch_workspace_for_user,
)


TELEGRAM_OFFSET_STATE_KEY = "telegram_poll_offset"
HASHTAG_PATTERN = re.compile(r"(?<!\w)#([A-Za-z][A-Za-z0-9_-]*)")
TOPIC_PREFIX_PATTERN = re.compile(r"^\s*topic\s*:\s*", re.IGNORECASE)
SWITCH_WORKSPACE_PATTERN = re.compile(r"^\s*switch\s+workspace\s+to\s+(.+?)\s*$", re.IGNORECASE)
SWITCH_WORKSPACE_TIMEAWARE_PATTERN = re.compile(
    r"^\s*switch\s+workspace\s+to\s+timeaware\s+(.+?)\s*$",
    re.IGNORECASE,
)
SWITCH_TO_WORKSPACE_PATTERN = re.compile(r"^\s*switch\s+to\s+(.+?)\s*$", re.IGNORECASE)


@dataclass
class TelegramIngestResult:
    outcome: str
    detail: str
    update_id: int
    node: Node | None = None
    ingestion_job: IngestionJob | None = None


def classify_telegram_text(text: str) -> str:
    stripped = text.strip()
    length = len(stripped)
    if length <= 140:
        return "line"
    if length <= 400:
        return "idea"
    if length <= 1500:
        return "thought_piece"
    return "document"


def extract_message_text(update: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return None, None

    text = message.get("text") or message.get("caption")
    if not isinstance(text, str):
        return None, message
    return text, message


def build_source_event_id(update_id: int) -> str:
    return f"telegram:update:{update_id}"


def build_telegram_message_id(message: dict[str, Any]) -> str | None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    if chat_id is None or message_id is None:
        return None
    return f"{chat_id}:{message_id}"


def extract_tags_from_text(text: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for match in HASHTAG_PATTERN.finditer(text):
        tag = match.group(1).lower()
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def strip_tags_from_text(text: str) -> str:
    stripped = HASHTAG_PATTERN.sub("", text)
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip()


def extract_explicit_node_type(text: str) -> tuple[str | None, str]:
    if TOPIC_PREFIX_PATTERN.match(text):
        stripped = TOPIC_PREFIX_PATTERN.sub("", text, count=1).strip()
        return "topic", stripped
    return None, text.strip()


def extract_workspace_switch_command(text: str) -> tuple[str, str] | None:
    timeaware_match = SWITCH_WORKSPACE_TIMEAWARE_PATTERN.match(text)
    if timeaware_match:
        return ("time_aware", timeaware_match.group(1).strip())

    switch_to_match = SWITCH_TO_WORKSPACE_PATTERN.match(text)
    if switch_to_match:
        return ("existing", switch_to_match.group(1).strip())

    match = SWITCH_WORKSPACE_PATTERN.match(text)
    if match:
        return ("general", match.group(1).strip())

    return None


async def send_telegram_message(settings: Settings, chat_id: str | int, text: str) -> None:
    if not settings.telegram_bot_token:
        return
    url = f"{settings.telegram_api_base_url}/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


def ingest_telegram_update(
    db: Session,
    update: dict[str, Any],
    settings: Settings | None = None,
    user: User | None = None,
) -> TelegramIngestResult:
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        raise ValueError("Telegram update is missing a valid update_id")

    source_event_id = build_source_event_id(update_id)
    existing_job = db.scalar(
        select(IngestionJob).where(IngestionJob.source_event_id == source_event_id)
    )
    if existing_job is not None:
        node = None
        if existing_job.node_id is not None:
            node = db.get(Node, existing_job.node_id)
        return TelegramIngestResult(
            outcome="duplicate",
            detail="Update already processed",
            update_id=update_id,
            node=node,
            ingestion_job=existing_job,
        )

    text, message = extract_message_text(update)
    telegram_message_id = build_telegram_message_id(message or {})
    base_payload = {
        "update_id": update_id,
        "message": message or {},
    }

    if text is None or not text.strip():
        job = IngestionJob(
            source="telegram",
            source_event_id=source_event_id,
            status="ignored",
            payload_json=base_payload,
            error_message="No text content found in Telegram update",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return TelegramIngestResult(
            outcome="ignored",
            detail="Update did not contain usable text",
            update_id=update_id,
            ingestion_job=job,
        )

    explicit_node_type, input_text = extract_explicit_node_type(text)
    workspace_switch_command = extract_workspace_switch_command(input_text)
    if workspace_switch_command:
        mode, workspace_name = workspace_switch_command
        if user is not None:
            workspace_type = "time_aware" if mode == "time_aware" else "general"
            if mode == "existing":
                from .workspace_ops import list_workspaces_for_user, get_workspace_display_name
                user_workspaces = list_workspaces_for_user(db, user)
                matched = next(
                    (w for w in user_workspaces if get_workspace_display_name(w) == workspace_name),
                    None,
                )
                if matched is None:
                    job = IngestionJob(
                        source="telegram",
                        source_event_id=source_event_id,
                        status="failed_command",
                        payload_json={**base_payload, "command": "switch_workspace", "workspace_name": workspace_name},
                        error_message="Workspace not found",
                    )
                    db.add(job)
                    db.commit()
                    db.refresh(job)
                    return TelegramIngestResult(
                        outcome="ignored",
                        detail=f"Workspace '{workspace_name}' not found",
                        update_id=update_id,
                        ingestion_job=job,
                    )
                workspace = switch_workspace_for_user(db, get_workspace_display_name(matched), user, workspace_type=matched.type)
            else:
                workspace = switch_workspace_for_user(db, workspace_name, user, workspace_type=workspace_type)
        else:
            if mode == "existing":
                workspace = get_workspace_by_name(db, workspace_name)
                if workspace is None:
                    job = IngestionJob(
                        source="telegram",
                        source_event_id=source_event_id,
                        status="failed_command",
                        payload_json={**base_payload, "command": "switch_workspace", "workspace_name": workspace_name},
                        error_message="Workspace not found",
                    )
                    db.add(job)
                    db.commit()
                    db.refresh(job)
                    return TelegramIngestResult(
                        outcome="ignored",
                        detail=f"Workspace '{workspace_name}' not found",
                        update_id=update_id,
                        ingestion_job=job,
                    )
                workspace = switch_workspace_by_name(db, workspace.name, workspace_type=workspace.type)
            else:
                workspace_type = "time_aware" if mode == "time_aware" else "general"
                workspace = switch_workspace_by_name(db, workspace_name, workspace_type=workspace_type)
        job = IngestionJob(
            workspace_id=workspace.id,
            source="telegram",
            source_event_id=source_event_id,
            status="processed_command",
            payload_json={
                **base_payload,
                "command": "switch_workspace",
                "workspace_name": workspace.name,
                "workspace_type": workspace.type,
            },
            error_message=None,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return TelegramIngestResult(
            outcome="switched_workspace",
            detail=f"Switched active workspace to {workspace.name}",
            update_id=update_id,
            ingestion_job=job,
        )

    workspace = get_active_workspace_for_user(db, user) if user is not None else get_active_workspace(db)
    tags = extract_tags_from_text(input_text)
    raw_text = strip_tags_from_text(input_text)
    node_type = explicit_node_type or classify_telegram_text(raw_text)
    normalized_text, metadata = prepare_node_content(
        raw_text,
        {
            "origin": "telegram",
            "update_id": update_id,
            "chat": (message or {}).get("chat", {}),
            "from": (message or {}).get("from", {}),
        },
        settings=settings,
    )

    node = Node(
        workspace_id=workspace.id,
        type=node_type,
        raw_text=raw_text,
        normalized_text=normalized_text,
        source="telegram",
        author=((message or {}).get("from", {}) or {}).get("username"),
        telegram_message_id=telegram_message_id,
        status="active",
        tags=tags,
        metadata_json=metadata,
    )
    db.add(node)
    db.flush()

    job = IngestionJob(
        workspace_id=workspace.id,
        source="telegram",
        source_event_id=source_event_id,
        status="processed",
        payload_json=base_payload,
        node_id=node.id,
    )
    db.add(job)
    sync_node_internal_tags(db, node)
    db.commit()
    db.refresh(node)
    db.refresh(job)
    return TelegramIngestResult(
        outcome="created",
        detail="Telegram update ingested into a node",
        update_id=update_id,
        node=node,
        ingestion_job=job,
    )


def ingest_telegram_update_with_embeddings(
    db: Session,
    settings: Settings,
    update: dict[str, Any],
    user: User | None = None,
) -> TelegramIngestResult:
    result = ingest_telegram_update(db, update, settings=settings, user=user)
    if result.outcome == "created" and result.node is not None:
        enqueue_link_job(db, result.node, settings.candidate_retrieval_limit)
        enqueue_embedding_job(db, result.node, settings.embedding_model_name)
    return result


async def poll_telegram_updates(settings: Settings, offset: int | None = None) -> list[dict[str, Any]]:
    if not settings.telegram_bot_token:
        raise ValueError("Telegram bot token is not configured")

    params: dict[str, Any] = {"timeout": 1, "limit": settings.telegram_poll_limit}
    if offset is not None:
        params["offset"] = offset

    url = f"{settings.telegram_api_base_url}/bot{settings.telegram_bot_token}/getUpdates"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise ValueError(f"Telegram API returned non-ok payload: {payload}")
    result = payload.get("result", [])
    if not isinstance(result, list):
        raise ValueError("Telegram API payload did not include a result list")
    return result


def get_stored_telegram_offset(db: Session) -> int | None:
    state = db.get(AppState, TELEGRAM_OFFSET_STATE_KEY)
    if state is None:
        return None
    value = state.value_json.get("offset")
    return value if isinstance(value, int) else None


def store_telegram_offset(db: Session, offset: int) -> None:
    state = db.get(AppState, TELEGRAM_OFFSET_STATE_KEY)
    if state is None:
        state = AppState(
            key=TELEGRAM_OFFSET_STATE_KEY,
            value_json={"offset": offset},
        )
        db.add(state)
    else:
        state.value_json = {"offset": offset}
    db.commit()
    db.refresh(state)
