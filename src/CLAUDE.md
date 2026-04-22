# Seldon — CLAUDE.md

Project context for AI assistants. Read this before making any changes.

> **AI memory:** Persistent memory for this project lives in `/.memory/` (hidden directory at repo root). Read `/.memory/MEMORY.md` for the index. It contains feedback rules, feature plans, known issues, and design decisions that are not derivable from the code alone.

---

## What this is

Seldon is a personal knowledge graph app. The user saves notes (called nodes) — primarily via Telegram, or directly in the app — and the app builds a visual graph showing how ideas connect. AI automatically detects relationships between notes.

Public URL (once deployed): https://seldon.railway.app
Full feature reference: see `creators_feature_list.txt`
Agent readiness roadmap: see `agent_readiness.txt`

---

## Tech stack

- **Backend**: FastAPI + SQLite + SQLAlchemy (Python)
- **Frontend**: Vanilla JS + SVG, no framework, no bundler
- **AI**: local Ollama (optional — narrative generation + internal tag generation)
- **Graph layout**: custom force-directed algorithm (no D3)
- **Fonts**: EB Garamond (body), IBM Plex Mono (code/secondary)
- **Deployment target**: Railway + persistent Volume for SQLite

---

## Project structure

```
twitter_poster/
  app/                  # FastAPI backend
    main.py             # all routes, app factory
    config.py           # Settings (pydantic-settings, reads from env)
    database.py         # SQLAlchemy engine, session, migrations
    models.py           # ORM models (Node, Edge, Workspace, etc.)
    schemas.py          # Pydantic schemas
    telegram_ingest.py  # Telegram polling + message parsing
    edge_creation_ops.py # 5 edge creation methods
    traversal_ops.py    # graph traversal (neighbors, subgraph, outline)
    narrative_ops.py    # Ollama narrative generation
    seed_ops.py         # seeds default workspace on first launch
    linker_ops.py       # auto link proposal system
    node_ops.py         # node text processing
    internal_tag_ops.py # hidden LLM-generated tags for edge matching
    embedding_ops.py    # sentence embeddings
    workspace_ops.py    # workspace CRUD
  frontend/             # all served as static + FileResponse routes
    index.html          # main graph app
    landing.html        # manifesto landing page (click anywhere → /graph)
    advanced.html       # advanced tools (traversal + edge creation)
    app.js              # all frontend logic (~1300 lines)
    app.css             # all styles
    advanced.js / advanced.css
    llms.txt            # agent-readable description (served at /llms.txt)
    robots.txt          # served at /robots.txt
    harmonograph.webp   # background image on landing page
  creators_feature_list.txt  # complete feature reference
  agent_readiness.txt         # L1-L5 AI agent readiness roadmap
  README.md                   # same as creators_feature_list
```

---

## Key design decisions

**No right panel** — the layout is full-width graph. Everything floats over it:
- Note card (top right) — appears when a node is clicked; text and tags are editable inline, Save button PATCHes the node
- Floating action bar (bottom center) — all actions
- Workspace island (top left) — workspace switcher
- Meta bar (bottom right) — Advanced link + Export + Theme toggle + Developer Mode

**Figma-like pan/zoom** — two-finger drag = pan, pinch/ctrl+scroll = zoom.
Uses CSS `transform: translate + scale` on the SVG, NOT native browser scroll.
`panX`, `panY`, `graphZoom` are state variables. Graph centers on load.

**Force-directed layout** — custom implementation. Repulsion (28000), attraction (0.018), min distance (240px), ideal edge length (280px), 320 iterations. After layout, SVG viewBox is computed from actual node positions.

**Node drag** — nodes are draggable. Positions stored in module-level `nodePositions` Map (keyed by node id). On drag end, position is PATCHed to `node.metadata_json.ui_position` and restored from there on next load. `nodePositions` is cleared on workspace switch.

**Edge creation always on** — no mode toggle. First click on a node sets it as edge source; second click on a different node sets the target and shows the edge form. Clicking the source node again cancels the selection. The form has a free-form "Edge Note" text input (stored as `edge.type`, max 300 chars, default "related-somehow") and a 0–100 weight slider (divided by 100 before sending to the API).

**Node editing** — the note card (top right) has an image section at the top (WhatsApp-style), an auto-growing textarea for `raw_text`, and editable tags (× to remove, Enter to add). Save calls `PATCH /nodes/{id}` with updated `raw_text` and `tags`. Image upload calls `POST /nodes/{id}/image` (multipart); removal calls `DELETE /nodes/{id}/image`. Images stored in `src/uploads/`, served at `/uploads/`. The image thumbnail also renders on the graph node card in SVG. Hidden in developer mode (linker tags are read-only).

**Themes** — three themes cycle via a toggle button in the meta bar. Preference saved in `localStorage`. Theme applied via `data-theme` attribute on `<html>`:
- (none) / light: warm parchment default
- `dark`: deep warm brown palette
- `colorful`: illustrated background image with blur, via `::before` pseudo-element
Node card fills are switched in JS (`NOTE_BACKGROUNDS`, `NOTE_BACKGROUNDS_DARK`, `NOTE_BACKGROUNDS_COLORFUL` arrays) since SVG inline `fill` attributes can't be overridden by CSS.

**Graph export** — "Export" button in the meta bar calls `GET /graph-data/export?workspace_id=&token=`. Returns JSON with keys `workspace`, `exported_at`, `nodes` (id, type, raw_text, tags), and `edges` (id, source, target, type, weight, confidence, evidence). File downloads as `seldon-{workspace-slug}.json`. Scoped to the active workspace only.

**SQLite on Railway** — use a Railway Volume mounted at `/data`. Set env var:
`DATABASE_URL=sqlite:////data/twitter_poster.db`

**No Ollama in production** — narrative generation button is hidden in deployed version. Ollama only used locally.

**`graphNeedsCenter = true`** — set this whenever workspace changes so the graph re-centers.

---

## Palette

**Light (default — warm parchment)**
```
--paper-bg: #f2ede4
--desk:     #ebe4d8
--text:     #2a2018
--muted:    #7d6d5b
--action:   #5f5144
```

**Dark**
```
--paper-bg: #161210
--desk:     #1c1814
--text:     #e2d5c3
--muted:    #7a6a58
--action:   #c8a87a
```

Dot grid (all themes): `radial-gradient(circle, rgba(83,65,47,0.18) 1px, transparent 1px)`, `background-size: 14px 14px`.

**Colorful** — background image (`shire.jpg`) + dot grid rendered in `::before` pseudo-element with `filter: blur(3px)`. Node cards use semi-transparent fills (`NOTE_BACKGROUNDS_COLORFUL`).

---

## Multi-user support

Each Telegram user gets their own isolated graph:
- `User` model: `telegram_chat_id` (unique), `access_token` (UUID)
- `Workspace.user_id` FK — per-user workspaces stored with internal name `u{user_id}:{display_name}`
- `metadata_json.display_name` holds the human-readable name shown in the UI
- On first message: User + default workspace created, welcome message sent with graph URL
- Auto-polling runs every 30s as a background asyncio task in lifespan
- Token passed as `?token=X` query param; stored in localStorage on the frontend
- Workspace endpoints (`/workspaces`, `/workspaces/current`, `/workspaces/switch`, `/graph-data`) all accept `?token=`
- Without a token: falls back to single-user legacy behaviour (original workspaces with `user_id=NULL`)

---

## Telegram message parsing

- Any text → note in active workspace (auto-classified by length)
- `topic: <text>` → topic node
- `#hashtag` in text → extracted as tags
- `switch to <name>` → switch to existing workspace
- `switch workspace to <name>` → create new general workspace
- `switch workspace to timeaware <name>` → create new time-aware workspace

---

## Environment variables (all optional except DATABASE_URL in prod)

```
DATABASE_URL                      sqlite:///./data/twitter_poster.db
TWITTER_POSTER_TELEGRAM_BOT_TOKEN your bot token
TWITTER_POSTER_PUBLIC_URL         https://seldon.railway.app
TWITTER_POSTER_OLLAMA_BASE_URL    http://127.0.0.1:11434
TWITTER_POSTER_OLLAMA_NARRATIVE_MODEL  qwen2.5:3b-instruct
TWITTER_POSTER_OLLAMA_TAG_MODEL   qwen2.5:3b-instruct
```

---

## What's next (todos)

1. Move this folder to its own independent git repo
2. Push to GitHub
3. Write Dockerfile + railway.toml
4. Deploy on Railway + set up Volume
5. Add OpenAPI endpoint descriptions (L3 agent readiness)
6. API key authentication (L4)
7. Webhooks (L4)
8. MCP server (L5)

---

## User preferences

- No unnecessary comments or docstrings added to code
- Don't add features beyond what's asked
- Concise responses — no trailing summaries
- Commit after each logical chunk of work when asked
- The user primarily uses Telegram to add notes, not the in-app form
- Design aesthetic: warm, parchment, calm — not dark, not clinical
