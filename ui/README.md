# Brain UI

React + TypeScript + sigma.js front end for the Brain service.
Built against API.md v1.0; the production build is served statically by the FastAPI process on port 8000.

## Commands

All commands run from `ui/`.

- `npm install` - install dependencies.
- `npm run dev` - dev server with `/api` proxied to `http://localhost:8000`.
- `npm run mock` - dev server with `VITE_MOCK=1`; the whole UI runs against fixture data from `src/mock/` with no backend (includes a scripted live run that replays graph deltas and a token stream on a timer).
- `npm run build` - type-check (`tsc --noEmit`) then build to `ui/dist`.
- `npm run preview` - serve the production build locally.

## Layout

- `src/api/types.ts` - TypeScript mirrors of every schema in API.md (bundles, runs, report, SSE events, graph nodes/edges/deltas, chunks).
- `src/api/client.ts` - fetch wrappers for all endpoints; chunk IDs contain `:` and `/` and are `encodeURIComponent`-ed in path segments.
- `src/api/stream.ts` - the `useEventStream` SSE hook (see below).
- `src/views/RunsList.tsx` - bundle table with checkboxes, run table polled every 2 s, Diagnose button.
- `src/views/LiveRun.tsx` - three panes: reasoning trail, incrementally patched sigma graph, streaming report pane that swaps to the full report on `done`.
- `src/views/ReportView.tsx` - root cause, confidence badge, evidence and ruled-out lists, action plan table, fix script, metrics footer.
- `src/components/GraphCanvas.tsx` - sigma over a graphology instance; `applyGraphDelta` patches nodes/edges in place, never a full relayout.
- `src/components/ChunkDrawer.tsx` - side drawer resolving a chunk ID to its verbatim text and metadata.
- `src/mock/` - fixtures and the scripted mock event stream for `VITE_MOCK=1`.

## How the SSE hook handles resume and dedupe

`useEventStream(runId, fromSeq, callbacks)` in `src/api/stream.ts`:

- The first connection opens `GET /api/runs/{run_id}/stream?from_seq=<seq>`.
  `LiveRun` fetches the graph snapshot first and passes the snapshot's `seq` as `fromSeq`, so no delta between snapshot and subscribe is missed.
  Passing `fromSeq = 0` replays the whole event log, which is also how finished runs get post-hoc replay.
- Every SSE frame carries `id: <seq>`.
  On automatic reconnect, the browser's `EventSource` resends the last seen id in the `Last-Event-ID` header, which the server gives precedence over `from_seq`; the hook keeps the same URL and lets the browser handle it.
- As a second line of defense, the hook tracks the last processed `seq` and drops any frame with `seq <= lastSeq`, so server-side replay overlap or EventSource quirks never double-apply an event.
- `token` events are buffered and flushed in batches on `requestAnimationFrame`, never per token; the buffer is drained synchronously before the `done` or `error` callback fires.
- The hook closes the connection itself after `done` or `error` so `EventSource` does not try to reconnect to a finished stream.

## Graph rendering

The graphology instance is owned by `LiveRun` and mutated in place by `applyGraphDelta` for each `graph` event (`add_node`, `add_edge`, `set_status`); sigma re-renders reactively with `autoRescale`, so there is never a full relayout on a delta.
New nodes get deterministic positions: hypotheses on an inner ring, findings orbiting their parent hypothesis (the `parent`/`stance` fields inside a finding's node object also create its `finding -stance-> hypothesis` edge, mirroring the store), and evidence nodes on a golden-angle outer halo.
Colors: evidence nodes muted slate; reasoning nodes yellow (`open`), green (`confirmed`), gray with a "(ruled out)" label suffix (`ruled_out`); edges with `attrs.dangling: true` render red.
Clicking a node opens the chunk drawer on the node's first evidence chunk.
