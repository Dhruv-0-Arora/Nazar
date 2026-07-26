# ADR-0006: Runs operate on cases (bundle sets), not single bundles

Status: accepted.

## Context

PLAN M3.5 says "Inbox watcher dispatches each bundle to a worker; runs are fully independent (own index, own loop)".
But the headline demo is cross-machine synthesis: `placement.json` deliberately puts a useful corpus doc on the other laptop, and the money edge (`service -talks_to-> service`, and the dangling DB host) can only exist when laptop A's and laptop B's chunks are in the same index and graph.
Per-bundle runs make the flagship demo impossible.
This is a genuine contradiction in PLAN.md.

## Decision

Introduce the case: a set of bundles indexed, graphed, and reasoned over together.

- A run takes a case, not a bundle. `POST /api/runs {bundle_ids: [...]}`.
- Watcher auto-trigger: on the first new valid bundle, open a debounce window (default 10 s); every bundle landing inside it joins the same case; then start the run.
- Manual trigger via the API/UI overrides everything, and is the recommended demo path (press the button when both bundles are visibly in).
- Concurrency semantics are unchanged: cases (not bundles) are the unit of parallelism, bounded by the Ollama semaphore.

## Consequences

- Chunk IDs already carry `machine_id`, so a multi-bundle index needs no ID changes.
- The UI must display which bundles a run includes, so a missing bundle is caught before the run, not after a wrong diagnosis.
- Single-bundle cases remain valid (a lone sick machine is just a case of one).
