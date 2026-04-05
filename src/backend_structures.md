# Backend Structures

The core pieces identified are:

- graph storage
- AI linker
- traverser / composer

But to make the system work well, the backend should be split into a few more subsystems.

## Core Structures

The system will need:

- `Node`
  - base entity with shared metadata
- `NodeType`
  - `line`, `quote`, `paragraph`, `idea`, `thought_piece`, `article`, `topic`, and later maybe `person`, `source`, `conversation`, `claim`
- `Edge`
  - typed relation between nodes
- `EdgeType`
  - `similar_to`, `expands`, `contradicts`, `supports`, `belongs_to_topic`, `derived_from`, `mentions`, `inspired_by`, `part_of`, `reply_to`
- `Graph`
  - logical workspace boundary, probably one personal knowledge graph for now

Each node should have at least:

- `id`
- `type`
- `raw_text`
- `normalized_text`
- `source`
- `created_at`
- `updated_at`
- `author`
- `telegram_message_id` if it came from Telegram
- `status`
- `tags`
- `embedding_ref`
- `metadata_json`

Each edge should have at least:

- `id`
- `from_node_id`
- `to_node_id`
- `type`
- `weight`
- `confidence`
- `created_by`
- `created_at`
- `evidence`
- `metadata_json`

`weight` and `confidence` should be stored numerically. Thickness or darkness is a frontend rendering choice, not the stored primitive.

## Additional Systems Needed

Besides storage, linker, and traverser, add:

- `ingestion pipeline`
  - receives Telegram messages
  - classifies them into likely node type
  - cleans and stores raw input
- `normalizer`
  - removes noise
  - extracts title or summary if needed
  - splits large content into smaller subnodes where appropriate
- `classifier`
  - decides whether a message is a line, idea, note, article, etc.
  - can be heuristic-first, AI-assisted later
- `embedding/indexing layer`
  - needed for linker candidate search
  - otherwise linking becomes too expensive
- `candidate retriever`
  - finds top related nodes before the linker reasons about edges
- `link validator`
  - checks whether a proposed edge is valid enough to store
  - avoids low-quality or duplicate edges
- `versioning / edit history`
  - because notes and thoughts will evolve
- `provenance system`
  - tracks where a node or edge came from
  - user-created, AI-created, imported, derived, merged
- `draft/composition workspace`
  - separate from the graph itself
  - lets traverser assemble an article plan before final output
- `job queue`
  - for asynchronous linking, re-linking, re-embedding, and traversal jobs
- `search layer`
  - lexical + semantic search
  - needed even if the graph is strong
- `review layer`
  - to inspect bad edges, merge duplicates, and fix node types
- `ontology/schema registry`
  - where node types and edge types are defined centrally
  - important because the hierarchy will evolve later

## Important Architectural Point

Do not store only big nodes.

There should likely be two layers:

- `content nodes`
  - actual user-authored units like line, paragraph, note, article
- `concept nodes`
  - abstract things like topic, person, theme, belief, project

That distinction matters or the graph will become messy quickly.

Example:

- a Telegram message becomes an `idea` node
- linker connects it to a `topic` node
- later several `idea` nodes compose into a `thought_piece`
- an article draft references both content nodes and topic nodes

## Linking Pipeline

The linker should likely work in stages:

1. retrieve candidate nodes using embeddings + keyword search
2. ask AI to classify relation type
3. assign edge weight and confidence
4. dedupe against existing edges
5. persist accepted edges
6. optionally queue uncertain edges for review

This should be asynchronous, not realtime.

## Traversal / Article Generation

Traverser alone is not enough. The system likely needs:

- `subgraph selector`
  - picks the relevant region of the graph
- `pathfinder`
  - finds meaningful narrative paths
- `structure builder`
  - turns selected nodes into outline sections
- `composer`
  - writes the article from the outline and source nodes
- `citation/provenance binder`
  - keeps track of which nodes informed which section

Otherwise `traverser creates article` is too underspecified.

## Other Things Likely Needed

- `deduplication`
  - two Telegram notes may express the same thought
- `merge/split operations`
  - merge duplicate nodes, split overlong nodes
- `confidence decay / relinking`
  - some edges should weaken over time or be replaced
- `temporal dimension`
  - thoughts change; the graph should preserve chronology
- `importance / salience score`
  - not all nodes should be equal
- `manual pinning`
  - the user should be able to force some nodes or edges as important
- `deletion / tombstoning`
  - avoid hard deletes where possible
- `export layer`
  - article export, markdown export, maybe graph snapshots
- `observability`
  - job logs, failed link jobs, traversal traces

## Recommended High-Level Backend Modules

- `telegram_ingest`
- `node_classifier`
- `content_store`
- `graph_store`
- `embedding_service`
- `candidate_retriever`
- `ai_linker`
- `edge_validator`
- `graph_traverser`
- `article_planner`
- `article_composer`
- `review_tools`
- `job_queue`
- `ontology_registry`

## Main Warning

Do not let the AI linker directly search the whole graph every time.

The system needs:

- embeddings
- candidate narrowing
- typed constraints
- async jobs

Otherwise it will become slow, expensive, and noisy.

## Visualization Layer

The graph is intended to look similar in spirit to TensorFlow's Embedding Projector, but TensorFlow Embedding Projector should not be the main product UI.

Reasons:

- it is primarily designed for embedding-space inspection, not rich typed knowledge graphs
- this system will need node types, edge types, edge weights, traversal, selection, editing, and subgraph-focused views
- Projector is good for showing where things sit in embedding space, but weaker for explaining why nodes are connected and for working with the graph as a product surface

Recommended options:

- `Cytoscape.js`
  - safest implementation choice for v1
  - strong graph model, layouts, styling, interaction, and weighted edges
  - better for typed nodes/edges and app-style graph operations
- `Sigma.js`
  - cleaner, more modern large-graph visual feel
  - WebGL-based and good for thousands of nodes and edges
  - stronger when performance and visual smoothness matter more than built-in editing
- `react-force-graph`
  - fastest path to something visually impressive
  - good for exploration and visual impact
  - less of a knowledge-graph workbench and more of an interactive graph scene
- `G6`
  - worth considering for strong visual customization
  - but likely behind Cytoscape and Sigma for this particular use case unless the design language fits especially well

Best product direction:

- use an `embedding map` as one mode
- use a `relation graph` as another mode

So the product should likely not have one visualizer only, but two coordinated views:

- `embedding map`
  - similar to TensorBoard Projector
  - shows semantic neighborhoods
- `relation graph`
  - shows typed edges like `supports`, `contradicts`, `expands`, and `belongs_to_topic`

If only one stack is chosen:

- choose `Cytoscape.js` for the main graph UI
- optionally add a separate embedding scatter plot later

If optimizing for:

- safest v1: `Cytoscape.js`
- best-looking with reasonable effort: `Sigma.js`
- fastest prototype: `react-force-graph`
