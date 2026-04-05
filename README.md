SELDON — CREATOR'S FEATURE LIST
Reference document for documentation, agent readiness, and onboarding.
================================


1. ENTERING THE APP
-------------------
Open the home page. Read it. Click anywhere to enter the graph.


2. WORKSPACES
-------------
Top left of the graph panel is a dropdown showing the current workspace name.
Click it to switch between workspaces.

Two types of workspaces:

  - General (default)
    A free-form thinking space. Notes are laid out using force-directed graph
    layout — nodes repel each other and edges pull connected nodes together.
    No time axis. Good for ideas, concepts, observations, anything.

  - Time-aware
    Notes are placed along a horizontal time axis. Each note carries a time
    label (year, month, or exact date). Good for tracking how your thinking
    evolved over time, journaling, research timelines.

A default workspace called "humans (default)" is pre-seeded on first launch
to show what the graph looks like with real content.


3. ADDING A NOTE (via app)
--------------------------
Click "+ Add Note" on the floating island at the bottom of the graph.
A form opens (floating, top right). Fill in:

  - Note text: your thought, observation, or idea. Plain text.
  - Tags: add #hashtags anywhere in the text — they are automatically
    extracted and stored as tags on the note.
  - (Time-aware workspaces only) Time field: enter a date, month, or year
    — e.g. "2017", "June 2017", "2017-06-12".

Click "Add Note" to save. The note appears on the graph immediately.


4. ADDING A NOTE (via Telegram) — primary method
-------------------------------------------------
Seldon is primarily designed to be used with Telegram as the input interface.
You can text Seldon from anywhere, anytime — on your phone, on your commute,
mid-conversation, in the middle of the night. Any thought, any length.

Just send a message to your Seldon Telegram bot. When you click "Poll Telegram"
in the app, it fetches all new messages and adds them as notes to your graph.

Notes are automatically classified by length:
  - Up to 140 characters  → line
  - 141–400 characters    → idea
  - 401–1500 characters   → thought_piece
  - 1500+ characters      → document


5. ADDING TAGS VIA TELEGRAM
----------------------------
Add #hashtags anywhere in your Telegram message.
Example: "consciousness might be substrate-independent #philosophy #mind"
Tags are extracted automatically and stored on the note.
They are stripped from the display text but visible in the tag list.


6. SWITCHING / CREATING A WORKSPACE VIA TELEGRAM
--------------------------------------------------
You can manage workspaces directly from Telegram without opening the app.

  Switch to an existing workspace:
    "switch to <workspace name>"
    Example: "switch to philosophy"

  Create a new general workspace and switch to it:
    "switch workspace to <workspace name>"
    Example: "switch workspace to consciousness research"

  Create a new time-aware workspace and switch to it:
    "switch workspace to timeaware <workspace name>"
    Example: "switch workspace to timeaware reading log 2025"

  After switching, all subsequent Telegram messages go into that workspace.


7. MESSAGE TYPES SUPPORTED FROM TELEGRAM
-----------------------------------------
Currently: text only.
(Images, voice notes, files — not supported yet.)

Special commands (see section 6):
  - switch to <name>
  - switch workspace to <name>
  - switch workspace to timeaware <name>

Topic nodes:
  Prefix your message with "topic: " to create a topic node instead of a note.
  Example: "topic: philosophy of mind"
  Topic nodes act as cluster anchors in the graph.


8. HOW EDGES ARE CREATED FOR NOTES YOU WRITE
---------------------------------------------
When you add a note (via app or Telegram), edges are not created automatically.
You create edges two ways:

  Manual:
    Click "+ Create Edge" on the floating island.
    Select two nodes on the graph (one as source, one as target).
    Choose an edge type and a weight (0 to 1 — how strong the connection is,
    default 0.5). Save.

  Automatic (via Generate Edges):
    Click the Generate Edges button (magic wand icon on the floating island).
    The app runs one or more edge creation methods (see section 12) across
    your notes and proposes edges. You review and accept or reject them.

Edge types available:
  similar_to, supports, contradicts, expands, led_to,
  belongs_to_topic, derived_from, mentions, inspired_by, part_of, reply_to


9. VIEWING A NOTE
-----------------
Click any node on the graph. A floating card appears at the top right showing:
  - The full note text
  - Tags attached to the note (If developer mode is On, tags shown are machine generated tags which were used in automatic edge creation.)
  - Narrative (if generated — see section 14)


10. PATH TRACING
----------------
Click the graph icon on the floating island. Path Tracing turns on.
Click any node on the graph to set it as the root.
The app traces all paths outward from that node through connected edges.
The root node is highlighted in red. All traced nodes and edges are highlighted
in orange. Everything else fades. Use this to see how one idea connects
through your entire graph.
Click the button again to turn Path Tracing off.


11. GENERATE EDGES (magic wand icon)
-------------------------------------
Runs automated edge detection across all notes in the current workspace.
It enqueues one link job per node and processes them as a batch, generating
candidate edge proposals across the whole graph.
After running, a proposal drawer opens showing suggested edges — each with
source node, target node, edge type, and confidence score.
You review each proposal and accept or reject it. Accepted edges are saved to the graph.
Note: this is a separate system from the five Advanced edge creation methods.


12. REVIEW LINKS (brain icon)
------------------------------
Opens the proposal drawer to review any pending edge proposals that have
been generated but not yet accepted or rejected. Use this to come back to
proposals you deferred earlier.


13. ADVANCED TAB
----------------
Accessible via the "Advanced" link (bottom right of the screen).
Two sections: Traversal and Edge Creation.
Each method has a live form — fill in the fields and hit Send/Preview
to call the API directly and see the raw JSON response.


--- TRAVERSAL METHODS (5) ---

  A. Node Neighborhood
     Returns all nodes directly connected to a given node, along with the
     edges connecting them. Use when you want the immediate neighbors only.
     Parameters: node_id, direction (both/incoming/outgoing), edge_type, limit.

  B. Subgraph Fetch
     Traverses outward from a root node and returns the full connected
     subgraph up to a given depth and node limit.
     Parameters: node_id, depth, limit, edge_type.

  C. Weighted Traversal
     Same as Subgraph Fetch but returns a path_score for each node,
     favouring paths with stronger (higher weight) edges. Use this to
     find the most strongly connected cluster around a node.
     Parameters: node_id, depth, limit, edge_type.

  D. Topic Traversal
     Starts from a topic node and returns all notes connected to that topic.
     Use when the root is a topic node and you want its cluster.
     Parameters: topic node_id, depth, limit.

  E. Outline Planning
     Traverses a subgraph and groups the connected nodes by edge relation type,
     returning a structured sectioned outline. Useful for planning articles or
     essays from your notes.
     Parameters: root_node_id, depth, max_nodes, edge_type.
     Sections returned: Supporting Ideas, Expanded Threads, Counterpoints,
     Topic Connections, Parallel Thoughts, Derived Material, etc.


--- EDGE CREATION METHODS (5) ---

  A. Tag Matcher
     Compares LLM-generated internal keywords and concepts across note pairs.
     Edge strength comes from the number of shared generated tags.
     User-visible tags are kept separate — this uses an internal hidden tag layer.
     Requires: local Ollama model (e.g. qwen2.5:3b-instruct).
     Parameters: threshold, max_pairs, edge_types_allowed, nodes, pairs, model_name.

  B. Embedding Matcher
     Scores note pairs using cosine similarity over sentence embeddings.
     Notes that are semantically similar (high cosine score) get edges.
     Parameters: threshold (e.g. 0.72), max_pairs, model_name, strategy.

  C. LLM Matcher
     Asks an LLM to directly score each candidate note pair and decide
     whether they should be connected and what edge type fits.
     Parameters: threshold, max_pairs, model_name, prompt_style.

  D. LLM Debator
     Three-model debate: one model argues for the edge, one argues against,
     a judge model decides. The most rigorous method — use for uncertain pairs.
     Not yet wired directly to the live graph (preview mode only).
     Parameters: threshold, max_pairs, for_model, against_model, judge_model, rounds.

  E. Hub Matcher
     Creates higher-level meaning hubs and links notes upward to them.
     A note can belong to multiple hubs. Use to find emergent themes across
     a large set of notes.
     Parameters: threshold, max_pairs, hub_depth, hub_space.


14. DEVELOPER MODE
------------------
Click "Developer Mode" (bottom right corner).
  - Off: shows user-visible tags (the #hashtags you wrote).
  - On: shows internal linker tags — hidden LLM-generated keywords and
    concepts that the system uses internally for edge creation (Tag Matcher).
    Useful for debugging why two notes did or didn't get connected.


15. GENERATE NARRATIVE (hidden in deployed version)
----------------------------------------------------
Available when running with a local Ollama model.
Click the book icon on the floating island.
Select a note — the app traverses connected nodes up to depth 2,
collects the subgraph, and sends it to the local LLM with a prompt asking
it to write a short 2-paragraph narrative in the voice of someone narrating
the evolution of your thought. The narrative appears inside the note card.
It is grounded in your actual notes — the model does not invent facts.
Hidden in the deployed version because Ollama is not available in the cloud.


16. GRAPH NAVIGATION
--------------------
  - Two-finger drag on trackpad: pan the graph
  - Pinch (ctrl + scroll): zoom in and out, centered on cursor
  - Click a node: opens the note card (top right)
  - Graph starts centered on load


17. NODE LAYOUT
---------------
  - General workspaces: force-directed layout. Notes repel each other,
    edges pull connected notes together. The graph settles into clusters.
  - Time-aware workspaces: horizontal timeline layout. Notes are placed
    along a time axis by their date label.


THINGS NOT YET SUPPORTED
--------------------------
  - Images, voice notes, or files via Telegram
  - Shift+click to create edges (planned)
  - Real-time auto-polling from Telegram (currently manual poll)
  - Narrative generation in the deployed version (Ollama dependency)
