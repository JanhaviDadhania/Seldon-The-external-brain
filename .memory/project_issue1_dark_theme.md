---
name: Issue #1 — Dark Theme
description: Plan for adding dark + colorful theme support to Seldon
type: project
---

Add dark theme (and later a colorful theme) to the graph app.

**Scope:**
- `app.css`: Add `[data-theme="dark"]` block overriding CSS vars (`--paper-bg`, `--desk`, `--text`, `--muted`, `--action`, shadow, panel backgrounds). Hardcoded `rgba()` values in `.graph-canvas`, `.floating-action-bar`, `.workspace-island`, `.detail-sheet`, `.proposal-drawer` etc. also need overrides.
- `app.js`: `NOTE_BACKGROUNDS` array (JS node fill colors) needs dark variants; toggle function sets `data-theme` on `<html>` and persists to `localStorage`.
- `index.html`: Add theme toggle button (meta-bar).

**Design decisions:**
- User wants dark colors chosen by implementer for now; will refine later.
- A colorful theme is also planned — keep theming system extensible (e.g. `data-theme="dark"` / `data-theme="colorful"` rather than a boolean class).
- Don't hardcode dark colors into the defaults; keep warm parchment as default.

**Why:** User requested; colorful mode also planned so system must support >2 themes.
**How to apply:** Implement as `data-theme` attribute on `<html>`, not a `.dark` class toggle.
