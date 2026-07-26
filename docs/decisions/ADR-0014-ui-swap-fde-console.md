# ADR-0014: ui/ replaced with fde-console (React + @xyflow/react)

Status: accepted.

## Context

SPEC.md and the original `ui/` specified React + sigma.js + graphology for the graph canvas, built around a multi-view model (RunsList, LiveRun, ReportView).
A more complete, independently-built UI ("fde-console") existed outside the repo: React + @xyflow/react + zustand + Tailwind, built around a single-console model (persistent machine rail, tabbed panels for Agent/Graph/Logs/Process) with a working mock/live/fixtures toggle already wired end to end.
It is materially more finished than the sigma.js `ui/` it replaces.

## Decision

`ui/` now contains fde-console verbatim (folded in from an external copy).

- Stack changes from sigma.js/graphology to @xyflow/react/zustand/Tailwind.
- View model changes from three routed views (RunsList/LiveRun/ReportView) to one screen with a machine rail and four tabbed panels (Agent/Graph/Logs/Process).
- Its `ConsoleApi` client (`src/api/types.ts`, `live.ts`) targets a different endpoint shape (`/api/snapshot`, `/api/chat`, `/api/context`, `/api/stream`) than the runs/report API the Brain backend (`brain/api/routes.py`) actually implements per API.md.
  This mismatch is deliberately left unresolved by this ADR - see [OPEN-QUESTIONS.md #8](../OPEN-QUESTIONS.md).

## Rationale

- The delivered UI is significantly further along (working panels, dagre-laid-out graph, chat-style trace, machine filtering) than the sigma.js scaffold it replaces, and covers the same conceptual surface (graph, trail, evidence, logs) the SPEC called for.
- Folding it in now and settling the API contract as a follow-up avoids blocking UI progress on a backend renegotiation, while keeping the mismatch visible instead of papered over.

## Consequences

- SPEC.md section 8 and the repo layout in section 3 now describe fde-console's actual panels and stack, not sigma.js.
- API.md is annotated to flag that `ui/` does not yet speak its contract; the contract itself is unchanged (`brain/api/routes.py` untouched by this ADR).
- Either `brain/api/routes.py` grows a `ConsoleApi`-shaped surface, or `ui/src/api/live.ts` + `types.ts` are rewritten against the existing runs/report API - a decision for OPEN-QUESTIONS.md #8, not this ADR.
- `ui/README.md` (from fde-console) documents the mock/live toggle and panel layout in more detail than SPEC.md section 8 needs to repeat.
