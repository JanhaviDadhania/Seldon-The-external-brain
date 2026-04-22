---
name: Ask before removing dependencies
description: Always ask before dropping a dependency or making other fundamental changes to the codebase
type: feedback
---

Do not remove dependencies, refactor core features, or make other fundamental changes without asking first.

**Why:** Removing sentence-transformers without asking broke the auto-link pipeline — a non-obvious side effect the user hadn't approved.

**How to apply:** If a fix requires removing a package, changing a core module, or disabling a feature, stop and ask the user before making the change.
