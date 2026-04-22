from __future__ import annotations

import secrets

import bcrypt
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import Edge, Node, User, Workspace
from .workspace_ops import get_or_create_workspace, set_active_workspace

DEFAULT_USER_EMAIL = "rioname@gmail.com"
DEFAULT_USER_PASSWORD = "shubham"


SEED_WORKSPACE_NAME = "humans (default)"

SEED_NODES = [
    {
        "raw_text": "Are humans better than other animals?",
        "type": "idea",
        "tags": ["evolution", "biology", "humans", "thinking"],
    },
    {
        "raw_text": "We have better analytical capabilities — we think longer, harder, and weirder than any other animal.",
        "type": "idea",
        "tags": ["brain", "thinking", "cognition", "humans"],
    },
    {
        "raw_text": "In the evolution tree, where exactly did we move ahead of others? Did we always think harder and longer than other animals, or did something specific trigger it?",
        "type": "idea",
        "tags": ["evolution", "biology", "anthropology", "thinking"],
    },
    {
        "raw_text": "We have thumbs. Opposable thumbs let us grip, make tools, build things no other animal can.",
        "type": "idea",
        "tags": ["biology", "dexterity", "evolution", "tools"],
    },
    {
        "raw_text": "We have hands, legs, and are in general very dextrous — our body is built for making things. We are the only animal that builds tools to build more tools.",
        "type": "idea",
        "tags": ["biology", "dexterity", "evolution", "tools"],
    },
    {
        "raw_text": "The cheetah is faster. The elephant is stronger. The eagle sees further. We just think. Longer, harder, and weirder.",
        "type": "idea",
        "tags": ["brain", "thinking", "evolution", "humans"],
    },
    {
        "raw_text": "Wonder did not begin with us. The elephant returns to mourn its dead. The whale sings into three thousand metres of dark ocean. No survival manual explains that. Wonder began with consciousness — and consciousness is very, very old.",
        "type": "idea",
        "tags": ["consciousness", "wonder", "philosophy", "evolution"],
    },
    {
        "raw_text": "We followed through. Not the fastest, not the strongest, not the largest — we followed the question anyway. That is the only difference. That has always been the only difference.",
        "type": "idea",
        "tags": ["pursuit", "thinking", "humans", "philosophy"],
    },
    {
        "raw_text": "AI is brand new hardware for the same oldest pursuit. The same consciousness. Better equipped.",
        "type": "idea",
        "tags": ["ai", "brain", "hardware", "thinking", "future"],
    },
]

# (from_index, to_index, edge_type, weight)
SEED_EDGES = [
    (0, 1, "supports", 0.9),
    (0, 2, "expands", 0.8),
    (1, 5, "similar_to", 0.85),
    (2, 3, "expands", 0.75),
    (2, 4, "expands", 0.75),
    (3, 4, "similar_to", 0.7),
    (5, 6, "led_to", 0.8),
    (6, 7, "led_to", 0.9),
    (7, 8, "led_to", 0.95),
]


def seed_default_user(db: Session) -> None:
    existing = db.scalar(select(User).where(User.email == DEFAULT_USER_EMAIL))
    if existing is not None:
        return

    password_hash = bcrypt.hashpw(DEFAULT_USER_PASSWORD.encode(), bcrypt.gensalt()).decode()
    user = User(
        telegram_chat_id=f"email:{DEFAULT_USER_EMAIL}",
        access_token=secrets.token_urlsafe(32),
        email=DEFAULT_USER_EMAIL,
        password_hash=password_hash,
    )
    db.add(user)
    db.flush()

    db.execute(
        text("UPDATE workspaces SET user_id = :uid WHERE user_id IS NULL"),
        {"uid": user.id},
    )
    db.commit()


def seed_workspace(db: Session) -> None:
    workspace = get_or_create_workspace(db, SEED_WORKSPACE_NAME)
    set_active_workspace(db, workspace)
    db.flush()

    existing = db.scalar(
        select(Node).where(Node.workspace_id == workspace.id, Node.status != "deleted").limit(1)
    )
    if existing is not None:
        db.commit()
        return

    created_nodes = []
    for node_data in SEED_NODES:
        node = Node(
            workspace_id=workspace.id,
            type=node_data["type"],
            raw_text=node_data["raw_text"],
            normalized_text=node_data["raw_text"],
            source="seed",
            tags=node_data["tags"],
            metadata_json={},
        )
        db.add(node)
        db.flush()
        created_nodes.append(node)

    for from_idx, to_idx, edge_type, weight in SEED_EDGES:
        edge = Edge(
            workspace_id=workspace.id,
            from_node_id=created_nodes[from_idx].id,
            to_node_id=created_nodes[to_idx].id,
            type=edge_type,
            weight=weight,
            confidence=weight,
            created_by="seed",
        )
        db.add(edge)

    db.commit()
