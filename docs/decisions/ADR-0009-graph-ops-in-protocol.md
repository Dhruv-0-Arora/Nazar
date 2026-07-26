# ADR-0009: Agent mutates the graph via protocol ops, not a subprocess CLI

Status: accepted.

## Context

PLAN M4.1 has the model "call a CLI" (`graph add-node ...`) that appends operations against persistent state, each call returning only the new node ID.
But our agent loop is in-process Python driving Ollama; qwen3.5:122b has no shell.
A literal CLI would mean teaching the loop to parse shell-ish strings from the model and spawn subprocesses per op.

## Decision

- The model emits graph deltas as structured JSON inside its normal turn output (`{"op": "graph", "delta": {...}}`, SPEC.md section 7.1).
- The loop applies them through `graph/store.py`, the single mutation path that enforces caps, assigns IDs, and emits SSE deltas.
- The feedback message returns exactly what PLAN wanted returned: the assigned ID and nothing else, keeping tokens out of the loop.
- A real `brain graph` debug CLI still exists (`graph/cli.py`) for humans inspecting or patching a run's graph; it goes through the same store.

## Rationale

- Same behavior and same token economy as PLAN's CLI, minus subprocess parsing fragility, which is exactly where a 122b model under JSON constraints would waste retries.
- One mutation path means caps and delta emission cannot be bypassed.

## Consequences

- PLAN M4.1's CLI grammar becomes the delta schema in API.md section 4; nothing about caps, statuses, or returned IDs changes.
