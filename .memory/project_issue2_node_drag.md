---
name: Issue #2 — Node Drag to Reposition
description: Plan for making graph nodes draggable with edges following
type: project
---

Allow nodes to be repositioned by click-drag; attached edges stretch/squeeze along.

**Where x,y are stored:**
Node positions are NOT persisted anywhere currently — `forceLayout()` recomputes them fresh on every `renderGraph()` call from scratch. They exist only as the local `layoutNodes` array inside `renderGraph()`. To support dragging:
- Add a module-level `const nodePositions = new Map()` in `app.js` to store `{ x, y }` per node id.
- `renderGraph()` seeds the map from force layout only for nodes NOT already in the map (i.e. first load, or newly added nodes). After that, the map is the source of truth for positions.
- On drag: update `nodePositions.get(nodeId)` live and redraw edges for that node.
- On workspace change / graph reload: clear `nodePositions` so layout reruns.

**Drag mechanics:**
- `mousedown` on a node `<g>` sets a dragging flag + records offset between pointer and node center.
- `mousemove` on the canvas updates `nodePositions` and re-renders only the dragged node's `<g>` transform and its connected edges' `d` attribute (avoids full re-render on every mouse move).
- `mouseup` / `mouseleave` ends drag.
- Use a `hasDragged` flag (true if pointer moved >4px) to distinguish drag from click — don't fire `handleNodeSelection` on drag-release.
- Add touch equivalents (`touchstart`/`touchmove`/`touchend`).

**Why:** User wants to freely rearrange the graph. Force layout positions are just a starting point.
**How to apply:** Positions live in JS memory only (not backend); cleared on workspace switch.
