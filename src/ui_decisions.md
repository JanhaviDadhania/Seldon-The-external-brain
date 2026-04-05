# UI Final Decisions

---

## Tagline / One-liner
Shown as hidden hover text in the UI header.

**Candidates (all approved):**
- "A mind with more room"
- "Same you, same consciousness, more hardware"
- "More room for your brain"

**Placement:** Hidden element near a top button, revealed on hover. Quiet, not marketing.

---

## Empty State / Onboarding
No blank graph. On first load, seed the workspace with a pre-built demo graph on "What is something worth?" — nodes around Adam Smith, Ray Dalio, Buffett, subjective vs labor theory of value, marginal utility. Makes the first experience immediately rich.

**Loading screen copy:** "No one's mind is empty."

**Seed graph topic:** Worth / Value of Things
Nodes: personal entry point ("I paid $8 for this app..."), Adam Smith quote + topic node, Labor Theory, Subjective Theory, Ray Dalio formula, Buffett quote, Marginal Utility, attention/value observation, Value topic node.
Edges: supports, contradicts, expands, similar_to, inspired_by, led_to, belongs_to_topic.

**Implementation:** Hardcode as seed data (runs once when workspace has 0 nodes). Designed to be swappable with LLM-generated graphs later.

---

## Node Edit and Delete
Backend fully supports both — `PATCH /nodes/{node_id}` for edit, `DELETE /nodes/{node_id}` for soft delete.
Frontend work only. Add edit and delete actions to the node detail panel.
**Status: Pending — to be designed later.**

---

## Visual Theme (Final)

**Palette:**
- `#FBE8C3` — parchment (default background)
- `#26547C` — navy (text, dark page backgrounds)
- `#82D4BB` — teal (primary accent)
- `#EF798A` — pink (secondary accent)

**Background:** Parchment default. Navy for specific pages (reading/posts).

**Visual motif:** Harmonograph — coupled oscillator patterns. Dense, layered, intricate. Multiple colors overlaid. NOT decoration — it IS the thesis. Simple rules → intricate emergent pattern.

**The metaphor (load-bearing):** Harmonograph in the void = entire worldview. Cosmic void = linear, entropic universe. The pattern = rare island of complexity. Gaia. Lovelock's Gaia hypothesis. Bordi finds these same self-maintaining loops inside AI. The visual IS the argument.

**Mood:** Curiosity. Calm. Never urgent. Mathematician's sketchbook, not a TED talk. Intimate — "I was working on this and found something strange, come look."

**Typography:** Georgia serif. Uppercase small labels with wide letter-spacing. No aggressive fonts.

**Animation:** Harmonograph image rotates very slowly (90s full rotation). Meditative. If generated in code — draws itself on load, one element at a time.

**Layout:** Two-column hero — text left, image right. Clean. Generous whitespace.

**References:**
- B.R. Chopra Mahabharat title sequence (Sudarshana Chakra in cosmic void)
- Vintage naturalist scientific illustrations
- Cellarius Harmonia Macrocosmica (1660 astronomical atlas)
- Harmonograph / Lissajous figures / coupled pendulum art

**Image:** `harmonograph.webp` — the primary visual motif across the app.

---

## Action Bar / Toolbar
Excalidraw-style floating toolbar. Buttons replaced with icon symbols. No grouping for now.
On hover: show the button's actual name as a tooltip.
All existing buttons stay — including Poll Telegram and Developer Mode.

---
