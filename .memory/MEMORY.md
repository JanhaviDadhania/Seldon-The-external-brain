# Memory Index

- [Ask before removing dependencies](feedback_ask_before_removing_deps.md) — Always ask before dropping a dep or making fundamental changes; don't assume a fix justifies the side effects
- [Issue #1 — Dark Theme](project_issue1_dark_theme.md) — data-theme attribute approach, colorful mode planned, keep >2 theme extensibility
- [Issue #2 — Node Drag](project_issue2_node_drag.md) — nodePositions Map in JS, cleared on workspace switch; drag vs click via hasDragged flag
- [Issue #3 — Edge Always On](project_issue3_edge_always_on.md) — remove edgeMode toggle + button; first/second click = source/target; same node twice = cancel
- [Issue #4 — Node Editing](project_issue4_node_editing.md) — IMPLEMENTED: textarea + tag edit in right panel, PATCH /nodes/{node_id}
- [Login Feature — Email OTP via Resend](project_login_feature.md) — IMPLEMENTED. Resend SDK, 6-digit OTP, 10-min expiry.
- [Known Security Issues](project_security_known_issues.md) — No cross-user ownership check on node endpoints; image upload has no magic byte validation. Fix before public launch.
