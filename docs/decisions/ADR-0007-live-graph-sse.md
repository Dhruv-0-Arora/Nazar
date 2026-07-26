# ADR-0007: Live reasoning display, backed by an append-only event log

Status: accepted.

## Context

PLAN left one question explicitly open: is the graph visual a live reasoning display (nodes lighting up during diagnosis) or a post-hoc artifact in the report?
PLAN M4.2 then specifies a full SSE live-run pipeline, which implies the answer but never states it.

## Decision

Live, and post-hoc for free from the same mechanism.

- Every run appends events (`token`, `query`, `chunk`, `graph`, `status`, `done`, `error`) with monotonic sequence numbers to `runs/<run_id>/events.jsonl`.
- The SSE endpoint tails that file: on connect it replays from `Last-Event-ID` (or from zero), then streams live. Reconnects are therefore lossless and idempotent.
- Connecting to a finished run replays the entire log: the post-hoc artifact is a replay of the live one, plus the static `graph.json` snapshot and report.

## Rationale

- The query trail "shows reasoning rather than asserting it" and is the strongest demo asset; it must be live.
- Persisting events first and streaming second means a UI crash, browser refresh, or projector hiccup mid-demo loses nothing.
- One mechanism instead of two (websocket state + separate report artifact) is less to build and less to break.

## Consequences

- `events.py` is a tiny but load-bearing module: single writer per run, fsync per event is acceptable at our event rates.
- The UI dedupes by seq as a second line of defense against EventSource replay quirks.
