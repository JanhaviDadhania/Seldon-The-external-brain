# Implementation Plan

This will be built in phases so each phase leaves something real that can be tested manually before the next layer is added.

## Phase 0: Foundations

Goal: establish the project skeleton, storage choices, and core schemas.

This phase will implement:

- backend app structure
- config and environment loading
- database setup
- core tables or collections for `nodes`, `edges`, `embeddings`, `ingestion_jobs`, `link_jobs`
- ontology registry for node types and edge types
- simple health endpoints or internal status checks

Tests:

- schema creation works on a clean database
- invalid node type is rejected
- invalid edge type is rejected
- edge cannot reference missing nodes
- metadata JSON is stored and read back correctly

Manual tests:

- start the service
- inspect DB objects
- create one node manually through API or admin script
- create one edge manually
- verify persistence across restart

## Phase 1: Telegram Ingestion

Goal: send text from Telegram and get it stored as a node candidate.

This phase will implement:

- Telegram bot webhook or polling worker
- raw message capture
- source provenance fields
- initial heuristic classifier:
  - short -> `line`
  - medium -> `idea`
  - longer -> `thought_piece` or `article_candidate`
- ingestion job log
- idempotency for duplicate Telegram updates

Tests:

- duplicate Telegram update does not create duplicate node
- short text becomes the expected node type
- long text becomes the expected node type
- empty or whitespace-only message is ignored
- source metadata is attached correctly
- Telegram message ID is stored

Manual tests:

- send one short line from Telegram
- send one paragraph
- send one longer note
- verify all appear in storage with type, timestamp, and raw text
- resend the same message and confirm no duplicate node is created

## Phase 2: Node Normalization and Versioning

Goal: clean stored content and make edits safe.

This phase will implement:

- normalized text generation
- optional title or summary extraction
- version history for node edits
- tombstone or soft delete support
- tags and manual type correction hooks

Tests:

- node edit creates a new version
- current version resolves correctly
- soft-deleted node is excluded from normal queries
- normalization does not overwrite raw text
- manually corrected type persists

Manual tests:

- edit a stored note
- verify the old version remains available
- re-tag a note as `quote` or `topic`
- soft delete a note and confirm it disappears from main results

## Phase 3: Embeddings and Candidate Retrieval

Goal: prepare the graph for semantic linking.

This phase will implement:

- embedding generation pipeline
- embedding cache
- similarity search index
- candidate retriever combining semantic + lexical retrieval
- async re-embedding jobs when node text changes

Tests:

- embedding is created for a new node
- a changed node queues re-embedding
- similarity search returns related nodes
- a missing embedding does not crash retrieval
- retrieval respects tombstones and current version

Manual tests:

- add three related notes and one unrelated note
- trigger retrieval for one note
- verify the related notes rank higher

## Phase 4: AI Linker

Goal: create typed edges automatically after ingestion.

This phase will implement:

- async link job queue
- candidate narrowing before model call
- AI relation classification
- edge weight + confidence scoring
- duplicate edge prevention
- uncertain-edge review queue

Tests:

- linker creates edges only between valid nodes
- duplicate run does not create duplicate edges
- low-confidence proposals go to review instead of the final graph
- relation type is stored with confidence and evidence
- edge weights are numeric and bounded

Manual tests:

- ingest several related notes
- wait for the linker job
- inspect auto-created edges
- verify stronger relationships have higher weight
- inspect a weak or uncertain edge in the review queue

## Phase 5: Graph Query and Traversal

Goal: make the graph usable for exploration and article preparation.

This phase will implement:

- node neighborhood query
- subgraph fetch by topic or node
- traversal or path selection
- section grouping
- article outline planner

Tests:

- fetch neighbors by edge type
- weighted traversal prefers stronger edges
- traversal excludes deleted nodes
- topic-centered subgraph loads correctly
- outline planner produces stable section ordering

Manual tests:

- pick a node and inspect connected nodes
- filter by edge type like `supports` or `expands`
- ask for a topic subgraph
- generate an outline from selected nodes

## Phase 6: Article Composer

Goal: turn graph material into draft writing.

This phase will implement:

- article workspace
- outline-to-draft pipeline
- provenance mapping from draft sections back to source nodes
- draft versioning
- export to markdown

Tests:

- a draft is generated from the selected subgraph
- each section keeps provenance references
- editing the draft creates version history
- export output is valid markdown
- deleted source nodes are not used in new drafts

Manual tests:

- select a cluster of notes
- generate an outline
- generate a draft article
- inspect which nodes informed each section
- export the draft

## Phase 7: Visualization

Goal: make the graph explorable visually.

This phase will implement:

- main graph view
- weighted edge styling
- node color or shape by type
- relation filtering
- search + focus mode
- later: separate embedding-map mode

Tests:

- node type styling renders correctly
- edge weight affects thickness or opacity
- filtering hides unwanted edge types
- selecting a node fetches the correct neighborhood
- a large graph still renders within acceptable limits

Manual tests:

- open the graph UI
- search for a note or topic
- click a node and inspect its neighborhood
- toggle edge types on and off
- confirm stronger links appear visually stronger

## Phase 8: Review and Curation Tools

Goal: keep the graph clean over time.

This phase will implement:

- review queue for weak links
- merge duplicate nodes
- split overlong nodes
- manual edge creation or removal
- pin important nodes or topics

Tests:

- merge preserves provenance
- split creates the correct child nodes
- removing an edge updates graph queries
- pinned nodes stay surfaced
- review approval or rejection is persisted

Manual tests:

- manually merge two similar notes
- reject a bad edge
- pin a key topic
- split a long thought into smaller units

## Phase 9: Hardening

Goal: make it reliable enough for real use.

This phase will implement:

- observability and logs
- retry handling
- job backoff
- migration strategy
- backup or export
- performance thresholds for linking and traversal

Tests:

- a failed link job retries safely
- a duplicate retry does not create a duplicate edge
- restart resumes queued jobs
- backup/export roundtrip works
- migration preserves existing data

Manual tests:

- restart the service mid-job
- confirm the job resumes or fails cleanly
- export data and inspect it
- run with a few hundred nodes and check responsiveness

## Suggested Build Order

Implementation order:

1. foundations
2. Telegram ingestion
3. normalization + versioning
4. embeddings + retrieval
5. AI linker
6. graph queries + traversal
7. article composer
8. visualization
9. review/curation
10. hardening

## Incremental Manual Testing

After Phase 1:

- send Telegram text and see nodes created

After Phase 3:

- see semantic relatedness between notes

After Phase 4:

- see automatic edges being created

After Phase 5:

- explore neighborhoods and topic clusters

After Phase 6:

- generate article outlines and drafts from the graph

After Phase 7:

- visually inspect the graph like a real knowledge map

## Recommended Narrow v1

For the first implementation pass:

- Telegram text ingestion only
- a small fixed node type hierarchy
- semantic retrieval
- async AI linker
- basic graph UI
- outline generation, not full polished article generation yet

That gets the core graph intelligence working before spending time on polish.
