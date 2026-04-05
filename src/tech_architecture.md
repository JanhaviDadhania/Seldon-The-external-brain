# Twitter Poster Technical Architecture

The right shape is a pipeline, not one big agent.

## Core Separation

1. `Ingestion` only finds and normalizes tweets.
2. `Selection` decides what is worth showing every 30 minutes.
3. `Content management` holds notes, thoughts, draft replies, and candidate original tweets.
4. `Posting` is a separate, locked-down executor that can only publish content explicitly approved by the user.

This separation matters because the hardest problem is not fetching tweets. It is content state, approval discipline, and keeping token usage under control.

## Services and Workers

- `source-connector`
  - Pulls tweets from the seed list of accounts.
  - Normalizes them into a common `SourceTweet` format.
- `similar-account-discovery`
  - Periodically expands the watchlist from related accounts.
  - Writes candidates to a reviewed watchlist instead of directly into posting logic.
- `ranking-and-digest`
  - Dedupes, scores, and builds the 30-minute digest.
  - Sends only compact, high-signal candidates.
- `content-workspace`
  - Stores user notes, opinions, instructions, and draft generations.
  - This is the core product boundary.
- `draft-generator`
  - Produces reply options and original tweet options from workspace context.
  - Never posts.
- `approval-gate`
  - Freezes exact text and version once the user finalizes content.
  - Any later edit revokes approval.
- `posting-worker`
  - Only consumes approved immutable `PostJob`s.
  - Has no draft generation access.

## Core Objects

- `SourceTweet`
  - Immutable snapshot of a found tweet.
- `ContentItem`
  - What gets surfaced in the digest.
- `UserSignal`
  - Notes, thoughts, instructions, and stance.
- `Draft`
  - Versioned candidate reply or original tweet.
- `ApprovalPacket`
  - Exact frozen text plus metadata and content hash.
- `PostJob`
  - The only object the posting worker can execute.

## State Machine

- `discovered`
- `normalized`
- `surfaced`
- `annotated`
- `drafted`
- `edited`
- `ready_for_approval`
- `approved`
- `queued_for_posting`
- `posted` or `failed`

Critical rule: if approved content changes, approval is invalidated automatically.

## Token Efficiency

Token efficiency comes from structure, not prompt tricks.

- Store raw tweets once.
- Summarize before generation.
- Reuse structured state instead of rereading full history.
- Keep each content thread local to one tweet or topic.
- Generate only on selected candidates, not on everything fetched.
- Separate ranking logic from generation logic.

## Separate Codex Workers

If implemented with multiple Codex sessions, the work should be split by ownership:

- Worker 1: ingestion and scheduler
- Worker 2: similar-account discovery and ranking
- Worker 3: content data model and workspace state machine
- Worker 4: approval gate and posting executor
- Worker 5: operator UX layer for digest review and draft finalization

The manager should only integrate interfaces and resolve contract mismatches. It should not implement worker-owned slices.

## Operating Mode

Before implementation, choose the operating mode:

- `API-first`
  - Cleaner and more reliable if access is available.
- `browser-automation-first`
  - Possible, but more fragile and higher-maintenance.
- `hybrid`
  - Structured ingestion where possible, browser automation only for final posting.

Recommended: `hybrid`.

## Phased Build Plan

### Phase 1

- Fixed seed list
- 30-minute digest
- Manual notes on surfaced tweets
- Draft generation
- Manual approval
- Manual post execution

### Phase 2

- Similar-account discovery
- Better ranking
- Thread or topic clustering
- Multiple draft styles

### Phase 3

- Scheduled posts
- Queueing approved drafts
- Audit trail
- Failure recovery and retries

### Phase 4

- Feedback learning from user edits
- Preference tuning per account or topic
- Better originality controls

## Recommended v1

Start with a narrow v1:

- fixed seed list
- no autonomous similar-account expansion yet
- 30-minute digest
- strong content workspace
- explicit approval gate
- browser-based posting only after final confirmation

That is the highest-leverage version and the least likely to become messy.
