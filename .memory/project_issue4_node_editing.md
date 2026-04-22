---
name: Issue #4 — Node Editing via Right Panel
description: Plan for making node text and tags editable in the floating detail panel
type: project
---

Edit node text and add/remove tags directly from the right-side floating panel.

**Status: IMPLEMENTED**

**Backend:** Already exists — `PATCH /nodes/{node_id}` at `main.py:678` accepts `raw_text` and `tags`.

**Frontend changes:**
- `index.html`: `#detail-raw` changed from `<div>` to `<textarea>`. Tag-add input and Save button added inside `detail-sheet`.
- `app.js`: `renderDetail()` uses `.value` not `.textContent`. `renderTags()` adds × remove buttons per tag (non-developer mode only). `saveNodeEdits(nodeId)` PATCHes the node, reloads graph, re-renders detail. Tag input (Enter key) adds tags inline.
- `app.css`: Textarea styled to match read view; focused state adds subtle outline. Tag × buttons and add-tag input styled.

**Design decisions:**
- Save/edit UI hidden in developer mode (shows linker tags which are read-only).
- Tags collected from DOM `.tag[data-tag]` elements on save.
- After save: `loadGraph()` + explicit `renderDetail(getNodeById(nodeId))` to refresh panel with updated data.

**Why:** User wants to correct/refine notes and tags without using Telegram.
**How to apply:** Backend is the source of truth; always reload after save.
