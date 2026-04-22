---
name: Issue #3 — Edge Creation Always On
description: Plan for removing the edge-mode toggle; clicking two nodes always creates an edge
type: project
---

Remove the "Create Edge" toggle button from the FAB. Edge creation is always available — first click sets source, second click sets target; clicking the same node twice cancels the selection.

**Changes:**
- `index.html`: Remove the `#toggle-edge-form-button` ("+ Create Edge") from the FAB entirely. The `#cancel-edge-selection-button` ("Cancel") already exists and stays.
- `app.js`:
  - Remove `edgeMode` boolean and all `toggleEdgeMode()` / `edgeModeButton` logic.
  - `handleNodeSelection()`: always try to set `edgeSourceNodeId` / `edgeTargetNodeId`. First click → source. Second click on same node → cancel (set both to null). Second click on different node → target → show form.
  - `updateEdgeSelectionUi()`: remove the `edgeMode` guard; show the edge form sheet whenever a source is selected.
  - `resetEdgeSelection()`: remove `keepMode` option since there's no mode.
  - `cancelEdgeSelectionButton`: clears source + target, hides form.
  - The `edgeModeButton` in HTML (currently hidden) can be removed.

**Key UX:** Clicking a node still shows its detail card. If no source yet, that click sets it as source AND shows detail. If source is set and user clicks a different node, that becomes the target and the edge form appears. Clicking the source node again = cancel.

**Why:** User finds the toggle unnecessary friction; edge creation should be a natural part of clicking nodes.
**How to apply:** Remove the button and `edgeMode` state entirely — don't keep it as dead code.
