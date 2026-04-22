---
name: Known Security Issues — Image Upload + Auth
description: Two known security gaps to address if Seldon ever goes fully public
type: project
---

Two known issues flagged during image feature audit. Acceptable for a personal/small app, worth fixing before public launch.

**1. No cross-user ownership check on workspace/node endpoints**
Any authenticated user who knows another user's workspace_id + node_id can PATCH, DELETE, or upload images to their nodes. `require_workspace()` only checks the workspace exists, not that the requesting user owns it.
**Why:** Token-based auth was added later; ownership checks were never backfilled.
**How to apply:** When fixing, add a `user_id` check in `require_workspace()` or a new `require_owned_workspace()` helper.

**2. Image upload validates Content-Type header only, no magic byte check**
An attacker could upload an HTML file with `Content-Type: image/png`. The suffix whitelist (jpg/png/gif/webp) is checked, but file contents are not verified. Could be an XSS vector if the app is public.
**Why:** No image parsing library is in the stack (no Pillow etc.).
**How to apply:** Add `python-magic` or `Pillow` to verify actual file bytes match the declared image type before saving.
