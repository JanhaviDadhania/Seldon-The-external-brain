---
name: Login Feature — Email OTP via Resend
description: Email OTP login using Resend — IMPLEMENTED. Key design decisions.
type: project
---

Email-based login is IMPLEMENTED (April 2026).

**What was built:**
- `POST /auth/request-otp` — generates 6-digit OTP, sends via Resend, stores hashed in User row
- `POST /auth/verify-otp` — verifies code, returns access_token
- `GET /login` — serves login.html
- `src/frontend/login.html` — two-step email → OTP form, warm parchment aesthetic
- `src/app/auth_ops.py` — OTP logic (generate, store, verify, send via resend SDK)
- app.js guard: redirects to /login if no authToken in localStorage

**Key design decisions:**
- Email sender: `resend` SDK (resend.com), from address configurable via `TWITTER_POSTER_RESEND_FROM_EMAIL` (default `onboarding@resend.dev`)
- OTP: 6-digit numeric, 10-minute expiry, max 5 failed attempts
- User model: `telegram_chat_id` made nullable (SQLite migration recreates users table); email users have no telegram_chat_id
- Config keys added: `resend_api_key`, `resend_from_email`, `otp_expiry_minutes`
- Access token stored in localStorage same as Telegram flow — no breaking change

**Still needed:**
- User adds `TWITTER_POSTER_RESEND_API_KEY=re_...` to src/.env
- For production: set `TWITTER_POSTER_RESEND_FROM_EMAIL` to a verified domain address
