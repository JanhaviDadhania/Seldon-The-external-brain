# Clarifications

## Structured Content Memory

The key idea is: do not treat the whole system as one long chat with the AI.

In `silicon-stemcell`, the prompt is rebuilt from files each time. The model gets a clean, structured context assembled from durable sources, instead of relying on a huge conversational backlog.

For this Twitter system, that translates to:

- `stable memory`
  - writing style
  - opinions and positioning
  - accounts to watch
  - accounts to avoid engaging with
  - recurring topics of interest
  - posting constraints
- `thread memory`
  - which tweet was surfaced
  - why it was surfaced
  - user comments on it
  - past draft attempts for that tweet
  - final approved version
- `runtime state`
  - waiting for approval
  - queued for posting
  - posted
  - failed

Instead of giving the model the last thousands of messages and asking it to infer everything, provide:

- a compact workspace profile
- the specific content thread
- the latest user note
- the current task

This saves tokens and reduces confusion.

Example:

If the user comments on a tweet:

`good idea but too abstract, make the reply sharper and founder-oriented`

that should be stored as structured state on that content item, not left buried in chat history.

Later, a revision step should only need:

- the source tweet
- the user note
- the user style or profile
- the previous draft

not the entire history of all tweets and all replies.

That is what is meant by `structured content memory`.

## Browser Queue

Playwright can drive a browser session, but it does not solve the orchestration problem at the application level.

Playwright does not decide:

- which job should run first
- whether two jobs should share one logged-in session
- whether posting jobs must be serialized
- whether one worker is already using the account
- whether a retry might duplicate a post
- whether a `post now` task should wait for approval state

Playwright executes commands in order within one script or session, but that is not sufficient.

The queue needed here is an application-level queue, not an internal Playwright command queue.

Example:

- Job A: open X and inspect notifications
- Job B: post approved tweet 17
- Job C: post approved tweet 18

If all of these hit the same logged-in account or browser profile at once, likely failure modes include:

- page navigation collisions
- wrong tab state
- stale DOM references
- one post flow interfering with another
- accidental duplicate posting

The correct rule is:

- research and analysis workers can run in parallel
- draft generation can run in parallel
- browser posting against the real account should be serialized through one posting queue

That is what is meant by borrowing the `browser queue` idea.

## Short Version

- `DNA.py` idea: rebuild context from structured memory, not chat history
- `browser queue` idea: serialize real account actions at the system level; do not rely on Playwright to manage business-level task ordering
