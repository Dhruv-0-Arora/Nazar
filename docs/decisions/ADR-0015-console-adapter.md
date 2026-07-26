# ADR-0015: Server-side ConsoleApi adapter bridges fde-console to the Brain

Status: accepted (Dhruv sign-off, resolving OPEN-QUESTIONS #8 option (a)).

## Context

ADR-0014 folded fde-console into `ui/` with a `ConsoleApi` client (`/api/snapshot`, `/api/chat` NDJSON, `PUT /api/context`, `/api/stream` full-snapshot SSE) modeling one continuous console session.
The Brain implements the runs/report model from API.md.
OPEN-QUESTIONS #8 recorded the mismatch with two options: a server-side console surface, or rewriting `ui/src/api/live.ts` against the runs API.

## Decision

Option (a): `brain/src/brain/api/console.py` implements the ConsoleApi surface as an adapter over existing run state, mounted alongside the runs API.

- `GET /api/snapshot` assembles a `ConsoleSnapshot` (mirroring `ui/src/api/types.ts` verbatim, camelCase and all) from the latest run: bundles -> machines (plus a `brain` machine), log-ish chunks -> per-line LogEntry with parsed severity, chunk store + evidence graph -> chunk-node GraphPayload (`talks_to`->`calls`, `has_config`->`reads`, reasoning edges->`references`, dangling edges weighted), events -> steps and trace, report -> diagnosis.
- `POST /api/chat` maps chat to diagnosis: reuse the active run if one is going, else start a run on every ready bundle with the message (+ saved operator context) as the question, then stream the run's event log folded into NDJSON TraceEvents, ending with an answer event carrying the cited report summary.
- `PUT /api/context` persists operator markdown (`$BRAIN_HOME/console-context.md`), appended to chat-triggered questions.
- `GET /api/stream` emits the full snapshot as SSE messages, only when it changed, on a 1 s cadence.

## Rationale

- Data locality: the snapshot needs every chunk, log line, and graph edge at once; that state lives in Brain memory and `runs/` artifacts, while the runs API has no bulk endpoints. Assembling server-side is one pass over local state; client-side would need new bulk endpoints anyway plus duplicated folding logic in TypeScript.
- The teammate's UI stays untouched and working, including its mock/live runtime toggle; `ui/dist` is now built with `VITE_USE_MOCK=false` so the Brain-served console defaults to live.
- The runs API remains the canonical contract (API.md sections 1-4); the console surface is documented as an adapter view, so brainctl, eval, and any future clients are unaffected.

## Consequences

- Two API surfaces over one state; `routes.py` stays canonical and `console.py` must never grow state of its own (it reads the registry and files only).
- The graph builder now records a service's own files (status, journal, config chunks) as that service node's evidence - needed for chunk-level console edges and generally correct (a service node's click-through should show its chunks).
- `run.py`'s discrete-run model shows through mildly in the console (a new chat while a run is active narrates the active run instead of starting another); acceptable for the demo, revisit if multi-case consoles are needed.
- OPEN-QUESTIONS #8 is closed and removed.
