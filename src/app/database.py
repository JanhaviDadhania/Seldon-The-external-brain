from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import Base, Workspace
from .workspace_ops import bootstrap_workspaces, get_or_create_workspace


def create_engine_for_settings(settings: Settings):
    connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
    return create_engine(settings.database_url, future=True, connect_args=connect_args)


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = create_engine_for_settings(settings)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _migrate_sqlite_schema(engine) -> None:
    inspector = inspect(engine)

    if "ingestion_jobs" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("ingestion_jobs")}
        statements: list[str] = []

        if "source_event_id" not in columns:
            statements.append(
                "ALTER TABLE ingestion_jobs ADD COLUMN source_event_id VARCHAR(255)"
            )
        if "node_id" not in columns:
            statements.append(
                "ALTER TABLE ingestion_jobs ADD COLUMN node_id INTEGER"
            )

        if statements:
            with engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
                if "source_event_id" not in columns:
                    connection.execute(
                        text(
                            "UPDATE ingestion_jobs "
                            "SET source_event_id = 'legacy:ingestion:' || id "
                            "WHERE source_event_id IS NULL"
                        )
                    )
                    connection.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS "
                            "ix_ingestion_jobs_source_event_id "
                            "ON ingestion_jobs (source_event_id)"
                        )
                    )
                if "node_id" not in columns:
                    connection.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_node_id "
                            "ON ingestion_jobs (node_id)"
                        )
                    )

    workspace_columns = {
        "nodes": "workspace_id INTEGER",
        "edges": "workspace_id INTEGER",
        "embeddings": "workspace_id INTEGER",
        "embedding_jobs": "workspace_id INTEGER",
        "ingestion_jobs": "workspace_id INTEGER",
        "link_jobs": "workspace_id INTEGER",
        "link_proposals": "workspace_id INTEGER",
        "internal_tags": "workspace_id INTEGER",
        "internal_tag_memberships": "workspace_id INTEGER",
        "experimental_hubs": "workspace_id INTEGER",
        "experimental_hub_memberships": "workspace_id INTEGER",
        "node_versions": "workspace_id INTEGER",
        "article_drafts": "workspace_id INTEGER",
        "article_draft_versions": "workspace_id INTEGER",
    }

    table_names = set(inspector.get_table_names())
    for table_name, column_sql in workspace_columns.items():
        if table_name not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "workspace_id" in columns:
            continue
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"))
            connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table_name}_workspace_id "
                    f"ON {table_name} (workspace_id)"
                )
            )

    if "workspaces" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("workspaces")}
        with engine.begin() as connection:
            if "type" not in columns:
                connection.execute(text("ALTER TABLE workspaces ADD COLUMN type VARCHAR(32)"))
                connection.execute(text("UPDATE workspaces SET type = 'general' WHERE type IS NULL"))
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_workspaces_type "
                        "ON workspaces (type)"
                    )
                )
            if "embed_token" not in columns:
                connection.execute(text("ALTER TABLE workspaces ADD COLUMN embed_token VARCHAR(128)"))
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_workspaces_embed_token "
                        "ON workspaces (embed_token)"
                    )
                )
            if "user_id" not in columns:
                connection.execute(text("ALTER TABLE workspaces ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_workspaces_user_id "
                        "ON workspaces (user_id)"
                    )
                )


def _backfill_workspace_ids(session_factory: sessionmaker[Session]) -> None:
    import secrets

    with session_factory() as db:
        default_workspace = get_or_create_workspace(db, "maker graph")
        db.flush()
        default_workspace_id = default_workspace.id

        workspaces = list(db.scalars(select(Workspace).order_by(Workspace.id)))
        for workspace in workspaces:
            if not getattr(workspace, "type", None):
                workspace.type = "general"
            if not getattr(workspace, "embed_token", None):
                workspace.embed_token = secrets.token_urlsafe(24)

        db.execute(text("UPDATE nodes SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE edges SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE embeddings SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE embedding_jobs SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE ingestion_jobs SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE link_jobs SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE link_proposals SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE internal_tags SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE internal_tag_memberships SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE experimental_hubs SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE experimental_hub_memberships SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE node_versions SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE article_drafts SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.execute(text("UPDATE article_draft_versions SET workspace_id = :workspace_id WHERE workspace_id IS NULL"), {"workspace_id": default_workspace_id})
        db.commit()
        bootstrap_workspaces(db)


def init_db(session_factory: sessionmaker[Session]) -> None:
    engine = session_factory.kw["bind"]
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        _migrate_sqlite_schema(engine)
    _backfill_workspace_ids(session_factory)


def get_db(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
