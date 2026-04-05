Bordi-Style UI Final Plan

Overall direction
- Use Bordi as the starting visual reference.
- Keep the UI quiet, paper-like, diary-like, and editorial.
- Do not over-design interactions yet.
- Build the first version with simple static visual rules. We can refine later.

1. Background system
- Use a soft paper-toned background close to Bordi.
- Keep it light and warm, not pure white.
- Add only a very subtle paper feel if needed.
- Do not add strong gradients, blur effects, or decorative noise in v1.

Implementation decision
- Main page background should feel like a desk/paper field.
- The graph area should visually merge into that field, not look like a separate app card.

2. Typography system
- Use Garamond-family serif fonts throughout the graph UI.
- The goal is “someone’s real diary” rather than software dashboard.
- Node text should feel handwritten-editorial, but still readable.
- Keep labels and UI controls simple and understated.

Implementation decision
- Use Garamond-style serif for node cards and detail text.
- Keep monospace only where raw machine-like output is unavoidable.

3. Note card system
- Notes should be rectangular cards, not circles.
- Cards should come from combinations of:
  - color: white, off-white, cream, cotton
  - background: plain, horizontal lines, boxes
- For v1, assign these styles from a small deterministic set so the graph has variation without chaos.
- Notes should look like physical paper notes pinned into a thinking board.

Implementation decision
- Create a small note-card style library with a few variants.
- Each node gets one variant consistently.
- No glassmorphism.
- No full transparency.
- Cards should feel like paper objects.

4. Node sizing rules
- Keep most note cards at a common default size.
- Longer notes should get larger cards.
- That is the only sizing rule needed for now.

Implementation decision
- Short and medium notes use one standard card size.
- Long notes expand vertically.
- Avoid too many size categories.

5. Thread system
- Use the most generic Bordi-style threads for now.
- Proposed links should not be shown in the main graph.
- Weaker links should be thinner.
- Stronger links should be thicker.
- Keep the thread look simple in v1.

Implementation decision
- Approved edges only in the main graph.
- Use soft curved threads.
- Use width to indicate strength.
- Avoid heavy stylization in v1.
- No loose fibrous thread effect for now.

6. State styling
- Keep interaction styling minimal for now.
- No extra hover language or pinning visuals yet.

Implementation decision
- Only selected node state needs to be clearly visible.
- Everything else stays subtle.

7. Layout behavior
- Keep the current simple layout approach for now.
- If adjusted, use only a very simple positioning improvement.
- The main goal is clarity, not advanced graph physics.

Implementation decision
- Continue with the existing simple layout as the base.
- Improve spacing between notes only if needed.
- Do not introduce complex motion or simulation yet.

8. Motion rules
- No motion for now.

Implementation decision
- No drifting, floating, springing, or animated settling.
- Keep transitions minimal or none.

9. Detail panel styling
- The detail panel is the right-side panel where you click a node and inspect its content.
- It should visually belong to the same paper/notes world as the graph.

Implementation decision
- Style the detail panel like a clean reading sheet, not like a dev tool sidebar.
- Keep it simple and quiet.
- Use the same serif language and paper palette.

10. Controls styling
- Keep the controls the way they are for now.
- Do not spend time redesigning them yet.

Implementation decision
- Bottom-left controls stay simple.
- Proposal drawer can remain functional and plain for now.

11. Empty/setup states
- Empty/setup states means screens like:
  - no graph data yet
  - loading/setup in progress
  - setup failed
- These should not break the visual language.

Implementation decision
- Show these states simply, using the same serif/paper styling.
- No special design work needed yet beyond visual consistency.

V1 build order
1. Replace transparent/minimal nodes with paper-like rectangular note cards.
2. Add a small set of card variants: white, off-white, cream, cotton; plain, lines, boxes.
3. Use Garamond-style serif typography across node cards and panel.
4. Keep only approved links visible.
5. Restyle edges into simple soft Bordi-like threads with thickness based on weight.
6. Keep current layout logic unless spacing becomes a real problem.
7. Restyle the detail panel into the same paper language.
8. Leave controls and proposal drawer mostly as-is.

Things explicitly not needed in v1
- glassmorphism
- heavy motion
- advanced hover states
- visible proposed links in the main graph
- complex physics simulation
- decorative thread texture experiments

Working principle
- Make it feel like a personal note board first.
- Keep implementation simple.
- Prefer consistency over cleverness.
- Add sophistication only after the base paper-note aesthetic feels right.
