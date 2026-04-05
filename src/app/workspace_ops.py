from __future__ import annotations

import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppState, User, Workspace


DEFAULT_WORKSPACE_NAME = "maker graph"
ACTIVE_WORKSPACE_STATE_KEY = "current_workspace"
WORKSPACE_TYPES = {"general", "time_aware"}


def normalize_workspace_name(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name.strip())
    if not normalized:
        raise ValueError("Workspace name cannot be empty")
    return normalized


def get_workspace_by_id(db: Session, workspace_id: int) -> Workspace | None:
    return db.get(Workspace, workspace_id)


def get_workspace_by_name(db: Session, name: str) -> Workspace | None:
    normalized = normalize_workspace_name(name)
    return db.scalar(select(Workspace).where(Workspace.name == normalized))


def get_or_create_workspace(db: Session, name: str, workspace_type: str = "general") -> Workspace:
    normalized = normalize_workspace_name(name)
    if workspace_type not in WORKSPACE_TYPES:
        raise ValueError("Invalid workspace type")
    workspace = get_workspace_by_name(db, normalized)
    if workspace is not None:
        return workspace

    workspace = Workspace(
        name=normalized,
        type=workspace_type,
        embed_token=secrets.token_urlsafe(24),
        metadata_json={},
    )
    db.add(workspace)
    db.flush()
    return workspace


def list_workspaces(db: Session) -> list[Workspace]:
    return list(db.scalars(select(Workspace).order_by(Workspace.name, Workspace.id)))


def get_active_workspace(db: Session) -> Workspace:
    workspace = db.scalar(select(Workspace).order_by(Workspace.id).limit(1))
    if workspace is None:
        workspace = get_or_create_workspace(db, DEFAULT_WORKSPACE_NAME)
        db.flush()

    state = db.get(AppState, ACTIVE_WORKSPACE_STATE_KEY)
    if state is None:
        state = AppState(
            key=ACTIVE_WORKSPACE_STATE_KEY,
            value_json={"workspace_id": workspace.id},
        )
        db.add(state)
        db.flush()
        return workspace

    workspace_id = state.value_json.get("workspace_id")
    if isinstance(workspace_id, int):
        active = db.get(Workspace, workspace_id)
        if active is not None:
            return active

    state.value_json = {"workspace_id": workspace.id}
    db.flush()
    return workspace


def set_active_workspace(db: Session, workspace: Workspace) -> Workspace:
    state = db.get(AppState, ACTIVE_WORKSPACE_STATE_KEY)
    if state is None:
        state = AppState(key=ACTIVE_WORKSPACE_STATE_KEY, value_json={"workspace_id": workspace.id})
        db.add(state)
    else:
        state.value_json = {"workspace_id": workspace.id}
    db.flush()
    return workspace


def resolve_workspace(db: Session, workspace_id: int | None = None) -> Workspace:
    if workspace_id is not None:
        workspace = db.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")
        return workspace
    return get_active_workspace(db)


def switch_workspace_by_name(db: Session, name: str, workspace_type: str = "general") -> Workspace:
    workspace = get_or_create_workspace(db, name, workspace_type=workspace_type)
    set_active_workspace(db, workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


def bootstrap_workspaces(db: Session) -> Workspace:
    workspace = get_or_create_workspace(db, DEFAULT_WORKSPACE_NAME)
    get_active_workspace(db)
    db.commit()
    db.refresh(workspace)
    return workspace


def get_user_by_token(db: Session, token: str) -> User | None:
    return db.scalar(select(User).where(User.access_token == token))


def get_user_by_chat_id(db: Session, chat_id: str) -> User | None:
    return db.scalar(select(User).where(User.telegram_chat_id == chat_id))


def get_or_create_user(db: Session, telegram_chat_id: str) -> tuple[User, bool]:
    user = get_user_by_chat_id(db, telegram_chat_id)
    if user is not None:
        return user, False
    user = User(
        telegram_chat_id=telegram_chat_id,
        access_token=secrets.token_urlsafe(32),
    )
    db.add(user)
    db.flush()
    return user, True


def get_active_workspace_for_user(db: Session, user: User) -> Workspace:
    state_key = f"current_workspace:{user.id}"
    state = db.get(AppState, state_key)
    if state is not None:
        workspace_id = state.value_json.get("workspace_id")
        if isinstance(workspace_id, int):
            ws = db.get(Workspace, workspace_id)
            if ws is not None and ws.user_id == user.id:
                return ws

    workspace = db.scalar(
        select(Workspace).where(Workspace.user_id == user.id).order_by(Workspace.id).limit(1)
    )
    if workspace is None:
        workspace = get_or_create_workspace_for_user(db, DEFAULT_WORKSPACE_NAME, user)

    state = AppState(key=state_key, value_json={"workspace_id": workspace.id})
    db.merge(state)
    db.flush()
    return workspace


def set_active_workspace_for_user(db: Session, user: User, workspace: Workspace) -> Workspace:
    state_key = f"current_workspace:{user.id}"
    state = AppState(key=state_key, value_json={"workspace_id": workspace.id})
    db.merge(state)
    db.flush()
    return workspace


def get_or_create_workspace_for_user(
    db: Session, name: str, user: User, workspace_type: str = "general"
) -> Workspace:
    normalized = normalize_workspace_name(name)
    if workspace_type not in WORKSPACE_TYPES:
        raise ValueError("Invalid workspace type")
    workspace = db.scalar(
        select(Workspace).where(Workspace.user_id == user.id, Workspace.name == normalized)
    )
    if workspace is not None:
        return workspace
    # Make name globally unique by prefixing with user id to avoid DB unique constraint collision
    global_name = f"u{user.id}:{normalized}"
    workspace = db.scalar(select(Workspace).where(Workspace.name == global_name))
    if workspace is not None:
        return workspace
    workspace = Workspace(
        user_id=user.id,
        name=global_name,
        type=workspace_type,
        embed_token=secrets.token_urlsafe(24),
        metadata_json={"display_name": normalized},
    )
    db.add(workspace)
    db.flush()
    return workspace


def list_workspaces_for_user(db: Session, user: User) -> list[Workspace]:
    return list(
        db.scalars(select(Workspace).where(Workspace.user_id == user.id).order_by(Workspace.id))
    )


def switch_workspace_for_user(
    db: Session, name: str, user: User, workspace_type: str = "general"
) -> Workspace:
    workspace = get_or_create_workspace_for_user(db, name, user, workspace_type=workspace_type)
    set_active_workspace_for_user(db, user, workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


def get_workspace_display_name(workspace: Workspace) -> str:
    display = workspace.metadata_json.get("display_name")
    if display:
        return display
    return workspace.name
