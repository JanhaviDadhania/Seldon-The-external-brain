from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread

import shutil

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import create_session_factory, get_db, init_db
from .edge_creation_ops import run_edge_creation_function
from .internal_tag_ops import ensure_node_internal_tag_metadata, ensure_nodes_internal_tag_metadata, sync_node_internal_tags
from .article_ops import create_article_draft, create_article_draft_version, build_outline_plan
from .embedding_ops import (
    enqueue_embedding_job,
    process_pending_embedding_jobs,
    retrieve_candidates,
    warm_embedding_model,
)
from .linker_ops import (
    apply_link_proposal,
    enqueue_link_job,
    process_pending_link_jobs,
    reject_link_proposal,
)
from .models import (
    ArticleDraft,
    ArticleDraftVersion,
    Edge,
    Embedding,
    EmbeddingJob,
    LinkJob,
    LinkProposal,
    Node,
    NodeVersion,
    User,
    Workspace,
)
from .narrative_ops import build_narrative_prompt, request_ollama_narrative
from .node_ops import create_node_version, merge_time_metadata, prepare_node_content
from .ontology import NODE_TYPES
from .schemas import (
    ArticleDraftCreate,
    LoginRequest,
    LoginResponse,
    ArticleDraftRead,
    ArticleDraftUpdate,
    ArticleDraftVersionRead,
    ArticleExportRead,
    EdgeCreationRequest,
    EdgeCreationResponse,
    EdgeCreate,
    EdgeRead,
    EmbeddingConfigResponse,
    EmbeddingJobRead,
    EmbeddingProcessResponse,
    EmbeddingRead,
    GenerateEdgesResponse,
    HealthResponse,
    NeighborRead,
    NodeCreate,
    NodeRead,
    NodeUpdate,
    NodeVersionRead,
    CandidateRead,
    TelegramConfigResponse,
    TelegramIngestRequest,
    TelegramIngestResponse,
    TelegramPollResponse,
    LinkJobRead,
    LinkProcessResponse,
    LinkProposalRead,
    NarrativeRead,
    NarrativeRequest,
    OutlinePlanRead,
    OutlinePlanRequest,
    OutlineSectionRead,
    SetupStatusResponse,
    SubgraphRead,
    TraversedNodeRead,
    WorkspaceRead,
    WorkspaceSwitchRequest,
)
from .telegram_ingest import (
    get_stored_telegram_offset,
    ingest_telegram_update_with_embeddings,
    poll_telegram_updates,
    send_telegram_message,
    store_telegram_offset,
)
from .traversal_ops import build_outline_sections, collect_subgraph, fetch_neighbors
from .workspace_ops import (
    get_active_workspace,
    get_active_workspace_for_user,
    get_or_create_user,
    get_user_by_token,
    get_workspace_display_name,
    list_workspaces,
    list_workspaces_for_user,
    resolve_workspace,
    set_active_workspace,
    set_active_workspace_for_user,
    switch_workspace_by_name,
    switch_workspace_for_user,
)
from .seed_ops import seed_default_user, seed_workspace, seed_workspace_for_user


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    session_factory = create_session_factory(app_settings)
    engine = session_factory.kw["bind"]
    import os
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    _default_uploads = Path(__file__).resolve().parent.parent / "uploads"
    uploads_dir = Path(os.environ.get("UPLOADS_DIR", str(_default_uploads)))
    uploads_dir.mkdir(parents=True, exist_ok=True)

    def start_model_setup(app: FastAPI) -> None:
        def worker() -> None:
            app.state.setup_status = {
                "status": "setting_up",
                "detail": f"Downloading and caching {app_settings.embedding_model_name}",
            }
            try:
                warm_embedding_model(app_settings)
                app.state.setup_status = {
                    "status": "ready",
                    "detail": f"{app_settings.embedding_model_name} is ready",
                }
            except Exception as exc:
                app.state.setup_status = {
                    "status": "error",
                    "detail": str(exc),
                }

        if not app_settings.preload_embedding_model_on_startup:
            app.state.setup_status = {
                "status": "ready",
                "detail": "Embedding preload disabled",
            }
            return

        Thread(target=worker, daemon=True).start()

    async def auto_poll_loop(app: FastAPI) -> None:
        while True:
            await asyncio.sleep(30)
            if not app_settings.telegram_bot_token:
                continue
            try:
                with session_factory() as db:
                    offset = get_stored_telegram_offset(db)
                updates = await poll_telegram_updates(app_settings, offset=offset)
                if not updates:
                    continue
                next_offset = None
                for update in updates:
                    message = update.get("message") or update.get("edited_message") or {}
                    chat = message.get("chat") or {}
                    chat_id = chat.get("id")
                    with session_factory() as db:
                        if chat_id is not None:
                            user, is_new = get_or_create_user(db, str(chat_id))
                            db.commit()
                            db.refresh(user)
                            if is_new:
                                seed_workspace_for_user(db, user)
                                first_name = (message.get("from") or {}).get("first_name", "")
                                graph_url = f"{app_settings.public_url}/graph?token={user.access_token}"
                                welcome = (
                                    f"Welcome{' ' + first_name if first_name else ''}! "
                                    f"Your personal knowledge graph is ready.\n\n"
                                    f"Open it here: {graph_url}\n\n"
                                    f"Send any message to add a note."
                                )
                                await send_telegram_message(app_settings, chat_id, welcome)
                            result = ingest_telegram_update_with_embeddings(db, app_settings, update, user=user)
                        else:
                            result = ingest_telegram_update_with_embeddings(db, app_settings, update)
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        next_offset = update_id + 1
                if next_offset is not None:
                    with session_factory() as db:
                        store_telegram_offset(db, next_offset)
            except Exception:
                pass

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(session_factory)
        app.state.settings = app_settings
        app.state.session_factory = session_factory
        app.state.engine = engine
        app.state.setup_status = {
            "status": "setting_up",
            "detail": f"Preparing {app_settings.embedding_model_name}",
        }
        seed_src = Path(__file__).resolve().parent.parent / "seed-uploads"
        if not seed_src.exists():
            seed_src = Path(__file__).resolve().parent.parent / "uploads"
        if seed_src.exists() and seed_src != uploads_dir:
            for f in seed_src.iterdir():
                dest = uploads_dir / f.name
                if not dest.exists():
                    shutil.copy2(f, dest)
        with session_factory() as db:
            seed_workspace(db)
        with session_factory() as db:
            seed_default_user(db)
        start_model_setup(app)
        poll_task = asyncio.create_task(auto_poll_loop(app))
        yield
        poll_task.cancel()
        engine.dispose()

    app = FastAPI(
        title="Seldon",
        description=(
            "Personal knowledge graph API. "
            "Save notes via Telegram or directly, connect them with typed edges, "
            "and explore how your ideas relate. "
            "Full agent reference: /llms.txt"
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

    def db_dependency(request: Request):
        yield from get_db(request.app.state.session_factory)

    def require_workspace(db: Session, workspace_id: int | None = None) -> Workspace:
        try:
            workspace = resolve_workspace(db, workspace_id=workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return workspace

    def require_node(db: Session, node_id: int, workspace_id: int) -> Node:
        node = db.get(Node, node_id)
        if node is None or node.workspace_id != workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
        return node

    def require_edge(db: Session, edge_id: int, workspace_id: int) -> Edge:
        edge = db.get(Edge, edge_id)
        if edge is None or edge.workspace_id != workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")
        return edge

    def require_draft(db: Session, draft_id: int, workspace_id: int) -> ArticleDraft:
        draft = db.get(ArticleDraft, draft_id)
        if draft is None or draft.workspace_id != workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
        return draft

    def require_embed_workspace(db: Session, workspace_id: int, token: str) -> Workspace:
        workspace = require_workspace(db, workspace_id)
        if workspace.embed_token != token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid embed token")
        return workspace

    def get_user_from_token(db: Session, token: str | None) -> User | None:
        if not token:
            return None
        user = get_user_by_token(db, token)
        if user is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
        return user

    def build_graph_payload(workspace: Workspace, db: Session) -> dict[str, object]:
        nodes = list(
            db.scalars(
                select(Node)
                .where(Node.workspace_id == workspace.id, Node.status != "deleted")
                .order_by(Node.id)
            )
        )
        active_node_ids = {node.id for node in nodes}
        edges = list(
            db.scalars(
                select(Edge)
                .where(
                    Edge.workspace_id == workspace.id,
                    Edge.from_node_id.in_(active_node_ids),
                    Edge.to_node_id.in_(active_node_ids),
                )
                .order_by(Edge.id)
            )
        )
        return {
            "workspace": {
                "id": workspace.id,
                "name": get_workspace_display_name(workspace),
                "type": workspace.type,
            },
            "nodes": [
                {
                    "id": node.id,
                    "workspace_id": node.workspace_id,
                    "type": node.type,
                    "label": (node.metadata_json.get("normalization", {}) or {}).get("title")
                    or (node.normalized_text or node.raw_text)[:48],
                    "raw_text": node.raw_text,
                    "normalized_text": node.normalized_text,
                    "time": (node.metadata_json.get("time", {}) or {}),
                    "tags": node.tags,
                    "linker_tags": (node.metadata_json.get("linker_tags", {}) or {}),
                    "ui_position": node.metadata_json.get("ui_position") or None,
                    "image": node.metadata_json.get("image") or None,
                    "source": node.source,
                    "status": node.status,
                }
                for node in nodes
            ],
            "edges": [
                {
                    "id": edge.id,
                    "workspace_id": edge.workspace_id,
                    "from_node_id": edge.from_node_id,
                    "to_node_id": edge.to_node_id,
                    "type": edge.type,
                    "weight": edge.weight,
                    "confidence": edge.confidence,
                }
                for edge in edges
            ],
        }

    @app.get("/robots.txt", include_in_schema=False)
    def robots_txt() -> FileResponse:
        return FileResponse(frontend_dir / "robots.txt", media_type="text/plain")

    @app.get("/llms.txt", include_in_schema=False)
    def llms_txt() -> FileResponse:
        return FileResponse(frontend_dir / "llms.txt", media_type="text/plain")

    @app.get("/", include_in_schema=False)
    def landing_home() -> FileResponse:
        return FileResponse(frontend_dir / "landing.html")

    @app.get("/graph", include_in_schema=False)
    def graph_home() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")

    @app.get("/advanced", include_in_schema=False)
    def advanced_home() -> FileResponse:
        return FileResponse(frontend_dir / "advanced.html")

    @app.get("/embed", include_in_schema=False)
    def embed_home() -> FileResponse:
        return FileResponse(frontend_dir / "embed.html")

    @app.get("/login", include_in_schema=False)
    def login_page() -> FileResponse:
        return FileResponse(frontend_dir / "login.html")

    @app.post("/auth/login", response_model=LoginResponse)
    def auth_login(
        payload: LoginRequest,
        db: Session = Depends(db_dependency),
    ) -> LoginResponse:
        import bcrypt as _bcrypt
        from sqlalchemy import select as sa_select
        user = db.scalar(sa_select(User).where(User.email == payload.email))
        if (
            user is None
            or not user.password_hash
            or not _bcrypt.checkpw(payload.password.encode(), user.password_hash.encode())
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        return LoginResponse(access_token=user.access_token)

    @app.post("/auth/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
    def auth_register(
        payload: LoginRequest,
        db: Session = Depends(db_dependency),
    ) -> LoginResponse:
        import secrets as _secrets
        import bcrypt as _bcrypt
        from sqlalchemy import select as sa_select
        existing = db.scalar(sa_select(User).where(User.email == payload.email))
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        email = payload.email.strip().lower()
        password_hash = _bcrypt.hashpw(payload.password.encode(), _bcrypt.gensalt()).decode()
        user = User(
            telegram_chat_id=f"email:{email}",
            access_token=_secrets.token_urlsafe(32),
            email=email,
            password_hash=password_hash,
        )
        db.add(user)
        db.flush()
        seed_workspace_for_user(db, user)
        db.commit()
        return LoginResponse(access_token=user.access_token)

    @app.post("/edge-creation/{function_name}", response_model=EdgeCreationResponse)
    def run_edge_creation_endpoint(
        function_name: str,
        payload: EdgeCreationRequest,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> EdgeCreationResponse:
        workspace = require_workspace(db, workspace_id or payload.workspace_id)
        request_payload = payload.model_copy(update={"function_name": function_name, "workspace_id": workspace.id})
        return run_edge_creation_function(db, request_payload, settings=app_settings)

    @app.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        settings = request.app.state.settings
        return HealthResponse(
            app_name=settings.app_name,
            environment=settings.environment,
            status="ok",
        )

    @app.get("/setup-status", response_model=SetupStatusResponse)
    def setup_status(request: Request) -> SetupStatusResponse:
        return SetupStatusResponse(**request.app.state.setup_status)

    @app.get("/workspaces", response_model=list[WorkspaceRead])
    def get_workspaces(
        token: str | None = None,
        db: Session = Depends(db_dependency),
    ) -> list[Workspace]:
        user = get_user_from_token(db, token)
        if user is not None:
            workspaces = list_workspaces_for_user(db, user)
            active = get_active_workspace_for_user(db, user)
            db.commit()
            return workspaces
        active = get_active_workspace(db)
        db.commit()
        db.refresh(active)
        return list_workspaces(db)

    @app.get("/workspaces/current", response_model=WorkspaceRead)
    def get_current_workspace(
        token: str | None = None,
        db: Session = Depends(db_dependency),
    ) -> Workspace:
        user = get_user_from_token(db, token)
        if user is not None:
            workspace = get_active_workspace_for_user(db, user)
            db.commit()
            db.refresh(workspace)
            return workspace
        workspace = get_active_workspace(db)
        db.commit()
        db.refresh(workspace)
        return workspace

    @app.post("/workspaces/switch", response_model=WorkspaceRead)
    def switch_workspace(
        payload: WorkspaceSwitchRequest,
        token: str | None = None,
        db: Session = Depends(db_dependency),
    ) -> Workspace:
        user = get_user_from_token(db, token)
        if user is not None:
            if payload.workspace_name:
                return switch_workspace_for_user(
                    db, payload.workspace_name, user, workspace_type=payload.workspace_type or "general"
                )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="workspace_name is required",
            )
        if payload.workspace_id is not None:
            workspace = require_workspace(db, payload.workspace_id)
            set_active_workspace(db, workspace)
            db.commit()
            db.refresh(workspace)
            return workspace
        if payload.workspace_name:
            return switch_workspace_by_name(db, payload.workspace_name, workspace_type=payload.workspace_type or "general")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="workspace_id or workspace_name is required",
        )

    @app.get("/ontology")
    def ontology() -> dict[str, list[str]]:
        return {
            "node_types": sorted(NODE_TYPES),
        }

    @app.get("/graph-data")
    def graph_data(
        workspace_id: int | None = None,
        token: str | None = None,
        db: Session = Depends(db_dependency),
    ) -> dict[str, object]:
        user = get_user_from_token(db, token)
        if user is not None:
            workspace = get_active_workspace_for_user(db, user)
            if workspace_id is not None:
                candidate = db.get(Workspace, workspace_id)
                if candidate and candidate.user_id == user.id:
                    workspace = candidate
        else:
            workspace = require_workspace(db, workspace_id)
        return build_graph_payload(workspace, db)

    @app.get("/graph-data/export")
    def graph_data_export(
        workspace_id: int | None = None,
        token: str | None = None,
        db: Session = Depends(db_dependency),
    ) -> Response:
        from fastapi.responses import JSONResponse
        user = get_user_from_token(db, token)
        if user is not None:
            workspace = get_active_workspace_for_user(db, user)
            if workspace_id is not None:
                candidate = db.get(Workspace, workspace_id)
                if candidate and candidate.user_id == user.id:
                    workspace = candidate
        else:
            workspace = require_workspace(db, workspace_id)
        nodes = list(
            db.scalars(
                select(Node)
                .where(Node.workspace_id == workspace.id, Node.status != "deleted")
                .order_by(Node.id)
            )
        )
        active_node_ids = {node.id for node in nodes}
        edges = list(
            db.scalars(
                select(Edge)
                .where(
                    Edge.workspace_id == workspace.id,
                    Edge.from_node_id.in_(active_node_ids),
                    Edge.to_node_id.in_(active_node_ids),
                )
                .order_by(Edge.id)
            )
        )
        payload = {
            "workspace": get_workspace_display_name(workspace),
            "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "nodes": [
                {"id": n.id, "type": n.type, "raw_text": n.raw_text, "tags": n.tags}
                for n in nodes
            ],
            "edges": [
                {
                    "id": e.id,
                    "source": e.from_node_id,
                    "target": e.to_node_id,
                    "type": e.type,
                    "weight": e.weight,
                    "confidence": e.confidence,
                    "evidence": e.evidence,
                }
                for e in edges
            ],
        }
        workspace_slug = get_workspace_display_name(workspace).lower().replace(" ", "-")
        return JSONResponse(
            content=payload,
            headers={"Content-Disposition": f'attachment; filename="seldon-{workspace_slug}.json"'},
        )

    @app.get("/embed/graph-data")
    def embed_graph_data(
        workspace_id: int,
        token: str,
        db: Session = Depends(db_dependency),
    ) -> dict[str, object]:
        workspace = require_embed_workspace(db, workspace_id, token)
        return build_graph_payload(workspace, db)

    @app.post("/graph/actions/generate-edges", response_model=GenerateEdgesResponse)
    def generate_edges_action(
        request: Request,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> GenerateEdgesResponse:
        settings = request.app.state.settings
        workspace = require_workspace(db, workspace_id)
        nodes = list(
            db.scalars(
                select(Node)
                .where(Node.workspace_id == workspace.id, Node.status != "deleted")
                .order_by(Node.id)
            )
        )

        metadata_backfilled = ensure_nodes_internal_tag_metadata(nodes, settings=settings)
        for node in nodes:
            sync_node_internal_tags(db, node)
        if metadata_backfilled:
            db.commit()

        queued_links = 0
        for node in nodes:
            job = enqueue_link_job(db, node, settings.candidate_retrieval_limit)
            if job is not None and job.status == "pending":
                queued_links += 1

        link_result = process_pending_link_jobs(
            db,
            settings,
            limit=max(len(nodes), 1) * 4,
            workspace_id=workspace.id,
        )
        return GenerateEdgesResponse(
            queued_embeddings=0,
            embedding_processing=EmbeddingProcessResponse(processed=0, reused=0, failed=0, remaining_pending=0),
            queued_links=queued_links,
            link_processing=LinkProcessResponse(**link_result),
        )

    @app.get("/telegram/config", response_model=TelegramConfigResponse)
    def telegram_config(request: Request) -> TelegramConfigResponse:
        settings = request.app.state.settings
        session_factory = request.app.state.session_factory
        with session_factory() as db:
            stored_offset = get_stored_telegram_offset(db)
            workspace = get_active_workspace(db)
        return TelegramConfigResponse(
            configured=bool(settings.telegram_bot_token),
            poll_limit=settings.telegram_poll_limit,
            stored_offset=stored_offset,
            current_workspace_id=workspace.id,
            current_workspace_name=workspace.name,
        )

    @app.get("/embeddings/config", response_model=EmbeddingConfigResponse)
    def embeddings_config(request: Request) -> EmbeddingConfigResponse:
        settings = request.app.state.settings
        return EmbeddingConfigResponse(
            configured=True,
            model_name=settings.embedding_model_name,
            batch_size=settings.embedding_batch_size,
        )

    @app.post(
        "/telegram/ingest",
        response_model=TelegramIngestResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def telegram_ingest(
        payload: TelegramIngestRequest,
        response: Response,
        request: Request,
        db: Session = Depends(db_dependency),
    ) -> TelegramIngestResponse:
        settings = request.app.state.settings
        result = ingest_telegram_update_with_embeddings(db, settings, payload.update)
        if result.outcome in {"duplicate", "ignored", "switched_workspace"}:
            response.status_code = status.HTTP_200_OK
        body = TelegramIngestResponse(
            outcome=result.outcome,
            detail=result.detail,
            update_id=result.update_id,
            node=result.node,
            ingestion_job_id=result.ingestion_job.id if result.ingestion_job else None,
        )
        return body

    @app.post("/telegram/poll", response_model=TelegramPollResponse)
    async def telegram_poll(
        request: Request,
        offset: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> TelegramPollResponse:
        settings = request.app.state.settings
        effective_offset = offset if offset is not None else get_stored_telegram_offset(db)
        updates = await poll_telegram_updates(settings, offset=effective_offset)
        created = 0
        duplicates = 0
        ignored = 0
        next_offset = None

        for update in updates:
            result = ingest_telegram_update_with_embeddings(db, settings, update)
            if result.outcome == "created":
                created += 1
            elif result.outcome == "duplicate":
                duplicates += 1
            elif result.outcome == "ignored":
                ignored += 1
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                next_offset = update_id + 1

        if next_offset is not None:
            store_telegram_offset(db, next_offset)

        workspace = get_active_workspace(db)

        return TelegramPollResponse(
            used_offset=effective_offset,
            fetched=len(updates),
            created=created,
            duplicates=duplicates,
            ignored=ignored,
            next_offset=next_offset,
            current_workspace_id=workspace.id,
            current_workspace_name=workspace.name,
        )

    @app.post("/nodes", response_model=NodeRead, status_code=status.HTTP_201_CREATED)
    def create_node(payload: NodeCreate, db: Session = Depends(db_dependency)) -> Node:
        settings = app_settings
        workspace = require_workspace(db, payload.workspace_id)
        metadata_input = dict(payload.metadata_json)
        if workspace.type == "time_aware":
            if not payload.time_label:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="time_label is required in time-aware workspaces",
                )
            metadata_input = merge_time_metadata(metadata_input, payload.time_label)
        elif payload.time_label:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="time_label is only allowed in time-aware workspaces",
            )
        normalized_text, metadata_json = prepare_node_content(
            payload.raw_text,
            metadata_input,
            payload.normalized_text,
            settings=settings,
        )
        node = Node(
            workspace_id=workspace.id,
            type=payload.type,
            raw_text=payload.raw_text,
            normalized_text=normalized_text,
            source=payload.source,
            author=payload.author,
            telegram_message_id=payload.telegram_message_id,
            status=payload.status,
            tags=payload.tags,
            metadata_json=metadata_json,
        )
        db.add(node)
        db.flush()
        sync_node_internal_tags(db, node)
        db.commit()
        db.refresh(node)
        enqueue_link_job(db, node, settings.candidate_retrieval_limit)
        enqueue_embedding_job(db, node, settings.embedding_model_name)
        return node

    @app.get("/nodes", response_model=list[NodeRead])
    def list_nodes(
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> list[Node]:
        workspace = require_workspace(db, workspace_id)
        stmt = select(Node).where(Node.workspace_id == workspace.id).order_by(Node.id)
        if not include_deleted:
            stmt = stmt.where(Node.status != "deleted")
        stmt = stmt.offset(offset).limit(limit)
        return list(db.scalars(stmt))

    @app.get("/nodes/{node_id}", response_model=NodeRead)
    def get_node(
        node_id: int,
        include_deleted: bool = False,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> Node:
        workspace = require_workspace(db, workspace_id)
        node = require_node(db, node_id, workspace.id)
        if node is None or (node.status == "deleted" and not include_deleted):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
        return node

    @app.get("/nodes/{node_id}/versions", response_model=list[NodeVersionRead])
    def list_node_versions(
        node_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> list[NodeVersion]:
        workspace = require_workspace(db, workspace_id)
        require_node(db, node_id, workspace.id)
        stmt = (
            select(NodeVersion)
            .where(NodeVersion.workspace_id == workspace.id, NodeVersion.node_id == node_id)
            .order_by(NodeVersion.version_number.desc())
        )
        return list(db.scalars(stmt))

    @app.patch("/nodes/{node_id}", response_model=NodeRead)
    def update_node(
        node_id: int,
        payload: NodeUpdate,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> Node:
        settings = app_settings
        workspace = require_workspace(db, workspace_id)
        node = require_node(db, node_id, workspace.id)

        updates = payload.model_dump(exclude_unset=True)
        reason = updates.pop("reason", "edit")
        if not updates:
            return node

        create_node_version(db, node, reason=reason)

        if "type" in updates:
            node.type = updates["type"]
        if "author" in updates:
            node.author = updates["author"]
        if "status" in updates:
            node.status = updates["status"]
        if "tags" in updates:
            node.tags = updates["tags"]
        if "raw_text" in updates or "normalized_text" in updates or "metadata_json" in updates:
            raw_text = updates.get("raw_text", node.raw_text)
            normalized_input = (
                updates["normalized_text"]
                if "normalized_text" in updates
                else None
            )
            metadata_input = updates.get("metadata_json", node.metadata_json)
            if "time_label" in updates:
                if node_workspace := require_workspace(db, node.workspace_id):
                    if node_workspace.type != "time_aware":
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="time_label is only allowed in time-aware workspaces",
                        )
                    metadata_input = merge_time_metadata(metadata_input, updates["time_label"])
            normalized_text, metadata_json = prepare_node_content(
                raw_text,
                metadata_input,
                normalized_input,
                settings=settings,
            )
            node.raw_text = raw_text
            node.normalized_text = normalized_text
            node.metadata_json = metadata_json
        elif "time_label" in updates:
            node_workspace = require_workspace(db, node.workspace_id)
            if node_workspace.type != "time_aware":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="time_label is only allowed in time-aware workspaces",
                )
            node.metadata_json = merge_time_metadata(node.metadata_json, updates["time_label"])
        elif "metadata_json" in updates:
            merged = dict(node.metadata_json)
            merged.update(updates["metadata_json"])
            node.metadata_json = merged

        db.commit()
        db.refresh(node)
        sync_node_internal_tags(db, node)
        db.commit()
        db.refresh(node)
        if node.status != "deleted":
            enqueue_link_job(db, node, settings.candidate_retrieval_limit)
            enqueue_embedding_job(db, node, settings.embedding_model_name)
        return node

    @app.post("/nodes/{node_id}/image", response_model=NodeRead)
    async def upload_node_image(
        node_id: int,
        file: UploadFile = File(...),
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> Node:
        workspace = require_workspace(db, workspace_id)
        node = require_node(db, node_id, workspace.id)
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File must be an image")
        suffix = Path(file.filename).suffix.lower() if file.filename else ".jpg"
        if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            suffix = ".jpg"
        old_image = (node.metadata_json or {}).get("image")
        if old_image:
            old_file = uploads_dir / Path(old_image).name
            if old_file.exists():
                old_file.unlink()
        filename = f"{node_id}{suffix}"
        with (uploads_dir / filename).open("wb") as dest:
            shutil.copyfileobj(file.file, dest)
        merged = dict(node.metadata_json or {})
        merged["image"] = f"/uploads/{filename}"
        node.metadata_json = merged
        db.commit()
        db.refresh(node)
        return node

    @app.delete("/nodes/{node_id}/image", response_model=NodeRead)
    def delete_node_image(
        node_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> Node:
        workspace = require_workspace(db, workspace_id)
        node = require_node(db, node_id, workspace.id)
        image_path = (node.metadata_json or {}).get("image")
        if image_path:
            file_path = uploads_dir / Path(image_path).name
            if file_path.exists():
                file_path.unlink()
        merged = dict(node.metadata_json or {})
        merged.pop("image", None)
        node.metadata_json = merged
        db.commit()
        db.refresh(node)
        return node

    @app.delete("/nodes/{node_id}", response_model=NodeRead)
    def soft_delete_node(
        node_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> Node:
        workspace = require_workspace(db, workspace_id)
        node = require_node(db, node_id, workspace.id)
        if node.status != "deleted":
            image_path = (node.metadata_json or {}).get("image")
            if image_path:
                orphan = uploads_dir / Path(image_path).name
                if orphan.exists():
                    orphan.unlink()
            create_node_version(db, node, reason="soft_delete")
            node.status = "deleted"
            sync_node_internal_tags(db, node)
            db.commit()
            db.refresh(node)
        return node

    @app.get("/nodes/{node_id}/embeddings", response_model=list[EmbeddingRead])
    def list_node_embeddings(
        node_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> list[Embedding]:
        workspace = require_workspace(db, workspace_id)
        require_node(db, node_id, workspace.id)
        stmt = (
            select(Embedding)
            .where(Embedding.workspace_id == workspace.id, Embedding.node_id == node_id)
            .order_by(Embedding.id.desc())
        )
        return list(db.scalars(stmt))

    @app.post("/nodes/{node_id}/embeddings/queue", response_model=EmbeddingJobRead | None)
    def queue_node_embedding(
        node_id: int,
        request: Request,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> EmbeddingJob | None:
        workspace = require_workspace(db, workspace_id)
        node = require_node(db, node_id, workspace.id)
        settings = request.app.state.settings
        return enqueue_embedding_job(db, node, settings.embedding_model_name)

    @app.post("/embeddings/jobs/process", response_model=EmbeddingProcessResponse)
    def process_embedding_jobs(
        request: Request,
        limit: int | None = None,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> EmbeddingProcessResponse:
        settings = request.app.state.settings
        workspace = require_workspace(db, workspace_id)
        result = process_pending_embedding_jobs(db, settings, limit=limit, workspace_id=workspace.id)
        return EmbeddingProcessResponse(**result)

    @app.post("/nodes/{node_id}/links/queue", response_model=LinkJobRead | None)
    def queue_node_links(
        node_id: int,
        request: Request,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> LinkJob | None:
        workspace = require_workspace(db, workspace_id)
        node = require_node(db, node_id, workspace.id)
        settings = request.app.state.settings
        return enqueue_link_job(db, node, settings.candidate_retrieval_limit)

    @app.post("/link-jobs/process", response_model=LinkProcessResponse)
    def process_link_jobs(
        request: Request,
        limit: int | None = None,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> LinkProcessResponse:
        settings = request.app.state.settings
        workspace = require_workspace(db, workspace_id)
        result = process_pending_link_jobs(db, settings, limit=limit or 10, workspace_id=workspace.id)
        return LinkProcessResponse(**result)

    @app.get("/link-proposals", response_model=list[LinkProposalRead])
    def list_link_proposals(
        status_filter: str | None = None,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> list[LinkProposal]:
        workspace = require_workspace(db, workspace_id)
        stmt = select(LinkProposal).where(LinkProposal.workspace_id == workspace.id).order_by(LinkProposal.id.desc())
        if status_filter is not None:
            stmt = stmt.where(LinkProposal.status == status_filter)
        return list(db.scalars(stmt))

    @app.post("/link-proposals/{proposal_id}/apply", response_model=LinkProposalRead)
    def apply_proposal(
        proposal_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> LinkProposal:
        workspace = require_workspace(db, workspace_id)
        proposal = db.get(LinkProposal, proposal_id)
        if proposal is None or proposal.workspace_id != workspace.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        proposal = apply_link_proposal(db, proposal_id)
        if proposal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        return proposal

    @app.post("/link-proposals/{proposal_id}/reject", response_model=LinkProposalRead)
    def reject_proposal(
        proposal_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> LinkProposal:
        workspace = require_workspace(db, workspace_id)
        proposal = db.get(LinkProposal, proposal_id)
        if proposal is None or proposal.workspace_id != workspace.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        proposal = reject_link_proposal(db, proposal_id)
        if proposal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        return proposal

    @app.get("/nodes/{node_id}/candidates", response_model=list[CandidateRead])
    def get_candidates(
        node_id: int,
        request: Request,
        limit: int | None = None,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> list[CandidateRead]:
        settings = request.app.state.settings
        workspace = require_workspace(db, workspace_id)
        require_node(db, node_id, workspace.id)
        results = retrieve_candidates(
            db,
            workspace_id=workspace.id,
            node_id=node_id,
            model_name=settings.embedding_model_name,
            limit=limit or settings.candidate_retrieval_limit,
        )
        return [
            CandidateRead(
                node=result.node,
                semantic_score=result.semantic_score,
                lexical_score=result.lexical_score,
                combined_score=result.combined_score,
            )
            for result in results
        ]

    @app.get("/nodes/{node_id}/neighbors", response_model=list[NeighborRead])
    def get_neighbors(
        node_id: int,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 20,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> list[NeighborRead]:
        workspace = require_workspace(db, workspace_id)
        require_node(db, node_id, workspace.id)
        if direction not in {"incoming", "outgoing", "both"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="direction must be one of incoming, outgoing, both",
            )
        neighbors = fetch_neighbors(
            db,
            workspace_id=workspace.id,
            node_id=node_id,
            direction=direction,
            edge_type=edge_type,
            limit=limit,
        )
        return [NeighborRead(direction=item.direction, edge=item.edge, node=item.node) for item in neighbors]

    @app.get("/nodes/{node_id}/subgraph", response_model=SubgraphRead)
    def get_subgraph(
        node_id: int,
        depth: int = 2,
        limit: int = 12,
        edge_type: str | None = None,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> SubgraphRead:
        workspace = require_workspace(db, workspace_id)
        try:
            root, nodes, edges = collect_subgraph(
                db,
                workspace_id=workspace.id,
                root_node_id=node_id,
                depth=depth,
                limit=limit,
                edge_type=edge_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return SubgraphRead(
            root_node=root,
            nodes=[
                TraversedNodeRead(
                    node=item.node,
                    depth=item.depth,
                    path_score=item.path_score,
                    via_edge_id=item.via_edge_id,
                )
                for item in nodes
            ],
            edges=edges,
        )

    @app.post("/outlines/plan", response_model=OutlinePlanRead)
    def plan_outline(payload: OutlinePlanRequest, db: Session = Depends(db_dependency)) -> OutlinePlanRead:
        workspace = require_workspace(db, payload.workspace_id)
        try:
            plan = build_outline_plan(
                db,
                workspace_id=workspace.id,
                root_node_id=payload.root_node_id,
                depth=payload.depth,
                max_nodes=payload.max_nodes,
                edge_type=payload.edge_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return OutlinePlanRead(
            root_node=plan["root_node"],
            sections=[OutlineSectionRead(**section) for section in plan["sections"]],
            nodes=[
                TraversedNodeRead(
                    node=item.node,
                    depth=item.depth,
                    path_score=item.path_score,
                    via_edge_id=item.via_edge_id,
                )
                for item in plan["nodes"]
            ],
            edges=plan["edges"],
        )

    @app.post("/narratives/generate", response_model=NarrativeRead)
    def generate_narrative(
        payload: NarrativeRequest,
        request: Request,
        db: Session = Depends(db_dependency),
    ) -> NarrativeRead:
        workspace = require_workspace(db, payload.workspace_id)
        try:
            root, nodes, edges = collect_subgraph(
                db,
                workspace_id=workspace.id,
                root_node_id=payload.root_node_id,
                depth=payload.depth,
                limit=payload.max_nodes,
                edge_type=payload.edge_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        prompt = build_narrative_prompt(root, nodes, edges, paragraphs=payload.paragraphs)
        try:
            narrative = request_ollama_narrative(request.app.state.settings, prompt)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Narrative generation failed: {exc}",
            ) from exc

        return NarrativeRead(
            root_node=root,
            narrative=narrative,
            nodes=[
                TraversedNodeRead(
                    node=item.node,
                    depth=item.depth,
                    path_score=item.path_score,
                    via_edge_id=item.via_edge_id,
                )
                for item in nodes
            ],
            edges=edges,
        )

    @app.post("/article-drafts", response_model=ArticleDraftRead, status_code=status.HTTP_201_CREATED)
    def create_draft(payload: ArticleDraftCreate, db: Session = Depends(db_dependency)) -> ArticleDraft:
        workspace = require_workspace(db, payload.workspace_id)
        try:
            draft = create_article_draft(
                db,
                workspace_id=workspace.id,
                root_node_id=payload.root_node_id,
                depth=payload.depth,
                max_nodes=payload.max_nodes,
                edge_type=payload.edge_type,
                title=payload.title,
                status=payload.status,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return draft

    @app.get("/article-drafts", response_model=list[ArticleDraftRead])
    def list_article_drafts(
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> list[ArticleDraft]:
        workspace = require_workspace(db, workspace_id)
        return list(
            db.scalars(
                select(ArticleDraft)
                .where(ArticleDraft.workspace_id == workspace.id)
                .order_by(ArticleDraft.id.desc())
            )
        )

    @app.get("/article-drafts/{draft_id}", response_model=ArticleDraftRead)
    def get_article_draft(
        draft_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> ArticleDraft:
        workspace = require_workspace(db, workspace_id)
        return require_draft(db, draft_id, workspace.id)

    @app.patch("/article-drafts/{draft_id}", response_model=ArticleDraftRead)
    def update_article_draft(
        draft_id: int,
        payload: ArticleDraftUpdate,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> ArticleDraft:
        workspace = require_workspace(db, workspace_id)
        draft = require_draft(db, draft_id, workspace.id)
        updates = payload.model_dump(exclude_unset=True)
        reason = updates.pop("reason", "edit")
        if not updates:
            return draft

        create_article_draft_version(db, draft, reason=reason)

        if "title" in updates:
            draft.title = updates["title"]
        if "status" in updates:
            draft.status = updates["status"]
        if "outline_json" in updates:
            draft.outline_json = updates["outline_json"]
        if "content_markdown" in updates:
            draft.content_markdown = updates["content_markdown"]
        if "provenance_json" in updates:
            draft.provenance_json = updates["provenance_json"]
        if "metadata_json" in updates:
            draft.metadata_json = updates["metadata_json"]

        db.commit()
        db.refresh(draft)
        return draft

    @app.get("/article-drafts/{draft_id}/versions", response_model=list[ArticleDraftVersionRead])
    def list_article_draft_versions(
        draft_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> list[ArticleDraftVersion]:
        workspace = require_workspace(db, workspace_id)
        require_draft(db, draft_id, workspace.id)
        return list(
            db.scalars(
                select(ArticleDraftVersion)
                .where(ArticleDraftVersion.workspace_id == workspace.id, ArticleDraftVersion.draft_id == draft_id)
                .order_by(ArticleDraftVersion.version_number.desc())
            )
        )

    @app.get("/article-drafts/{draft_id}/export", response_model=ArticleExportRead)
    def export_article_draft(
        draft_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> ArticleExportRead:
        workspace = require_workspace(db, workspace_id)
        draft = require_draft(db, draft_id, workspace.id)
        return ArticleExportRead(title=draft.title, markdown=draft.content_markdown)

    @app.post("/edges", response_model=EdgeRead, status_code=status.HTTP_201_CREATED)
    def create_edge(payload: EdgeCreate, db: Session = Depends(db_dependency)) -> Edge:
        workspace = require_workspace(db, payload.workspace_id)
        if payload.from_node_id == payload.to_node_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="from_node_id and to_node_id must be different",
            )

        from_node = require_node(db, payload.from_node_id, workspace.id)
        to_node = require_node(db, payload.to_node_id, workspace.id)
        if from_node.workspace_id != to_node.workspace_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Edges must connect nodes in the same workspace",
            )

        edge = Edge(
            workspace_id=workspace.id,
            from_node_id=payload.from_node_id,
            to_node_id=payload.to_node_id,
            type=payload.type,
            weight=payload.weight,
            confidence=payload.confidence,
            created_by=payload.created_by,
            evidence=payload.evidence,
            metadata_json=payload.metadata_json,
        )
        db.add(edge)
        db.commit()
        db.refresh(edge)
        return edge

    @app.get("/edges/{edge_id}", response_model=EdgeRead)
    def get_edge(
        edge_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> Edge:
        workspace = require_workspace(db, workspace_id)
        return require_edge(db, edge_id, workspace.id)

    @app.get("/edges", response_model=list[EdgeRead])
    def list_edges(
        limit: int = 50,
        offset: int = 0,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> list[Edge]:
        workspace = require_workspace(db, workspace_id)
        stmt = (
            select(Edge)
            .where(Edge.workspace_id == workspace.id)
            .order_by(Edge.id)
            .offset(offset)
            .limit(limit)
        )
        return list(db.scalars(stmt))

    @app.delete("/edges/{edge_id}", response_model=EdgeRead)
    def delete_edge(
        edge_id: int,
        workspace_id: int | None = None,
        db: Session = Depends(db_dependency),
    ) -> Edge:
        workspace = require_workspace(db, workspace_id)
        edge = require_edge(db, edge_id, workspace.id)
        db.delete(edge)
        db.commit()
        return edge

    return app


app = create_app()
