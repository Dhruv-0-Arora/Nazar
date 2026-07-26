# ADR-0001: Repository layout and the "frontend" naming collision

Status: accepted.

## Context

PLAN.md says the repo has "a frontend + backend folder" for the broken scenario system.
The Brain also has a frontend (the React + sigma.js visualizer, PLAN M4.1).
Two unrelated things named `frontend/` in one repo guarantees confusion in conversation, in paths, and in build tooling.

## Decision

- The scenario's apps live under `scenario/backend/` and `scenario/frontend/`.
- The Brain's visualizer lives at top-level `ui/`.
- The Brain's Python service lives at top-level `brain/`.
- The collector lives at top-level `collector/`.
- Runtime state (inbox, runs) lives outside the repo under `$BRAIN_HOME` (default `~/brain/`), gitignored if ever local.

Full tree in SPEC.md section 3.

## Consequences

- "Frontend" in conversation always means the scenario app; the Brain's is always "the UI".
- The scenario package is self-contained and can be cloned onto client laptops without dragging Brain code along (clone the repo, use only `scenario/` and `collector/`).
