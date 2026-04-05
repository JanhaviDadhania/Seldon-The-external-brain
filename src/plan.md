# Product Hunt Readiness Plan

Items to address one by one. Cross off each as done.

---

## 1. One-liner / tagline
A short philosophical tagline shown as hidden hover text in the UI header.
Reflects the belief: humans differ by brain hardware, not consciousness. LLMs are the next hardware upgrade, not a threat. This app is one such upgrade.

**Status:** IN PROGRESS

---

## 2. Empty state / onboarding
First-time users see a blank graph and "Click a note to inspect it."
Need: a prompt to create their first node, a brief explanation of what the app does.

---

## 3. Reorganize the action bar
Bottom-left strip has 11+ buttons with no grouping or hierarchy.
Need: group controls by function (zoom, modes, graph actions), reduce visual noise.

---

## 4. Fix confusing toggle button names
- "Generate Narrative Off" reads like an action, not a state.
- Same for "Path Tracing Off", "Developer Mode Off".
Need: clearer on/off labeling or icon-based toggles.

---

## 5. Hide "Poll Telegram" and "Developer Mode" from default view
"Poll Telegram" requires external setup — new users will hit errors.
"Developer Mode" is internal tooling, not end-user facing.
Need: move to advanced/settings, or hide behind a toggle.

---

## 6. Add node edit and delete
Nodes can be created but not edited or deleted in the UI.
Need: edit and delete actions in the node detail panel.

---

## 7. Clarify edge creation flow
Activating edge mode gives no visual overlay or instruction on the graph itself.
Need: an in-graph tooltip or overlay explaining "click source, then target."

---

## 8. ~~Fix XSS in proposalCard~~ — SKIPPED

## 9. ~~Fix stale activeNodeId after node deletion~~ — SKIPPED (acceptable)

## 10. ~~Fix narrativeMode toggle not refreshing detail panel~~ — SKIPPED

## 11. Add timeout/max retry to waitForSetup — DONE
Show "Something went wrong, please refresh." after 10 failed retries.

## 12. ~~Fix path tracing silently cancelling edge mode~~ — SKIPPED (nothing breaks)
