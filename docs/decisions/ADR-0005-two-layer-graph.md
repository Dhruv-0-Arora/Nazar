# ADR-0005: One graph store, two layers (evidence + reasoning)

Status: accepted.

## Context

PLAN describes two graphs without reconciling them:

- M3 stage 3: a deterministic evidence graph (structural + regex-extracted tiers) built at ingest.
- M4.1: an agent-mutated graph of `{hypothesis|evidence|cause}` nodes with per-run caps (~8 hypotheses, ~150 nodes) built through incremental operations during reasoning.

Are these one graph, two graphs, which one does the visualizer show, and what do the caps apply to?
Unresolved, this is the largest inconsistency in the plan.

## Decision

One store (`graph/store.py`), every node tagged `layer: evidence | reasoning`.

- Evidence layer: built once per run at ingest, deterministic, uncapped. Node IDs are content-derived (`port:5432`) so mentions from every machine merge.
- Reasoning layer: mutated by the agent during the loop via graph ops (`add_node`, `add_edge`, `set_status`). Store-assigned IDs (`hyp:1`). All PLAN M4.1 caps apply to this layer only, enforced in the store, not the prompt.
- Reasoning nodes attach to the evidence layer via `about` edges and to chunks via the same `evidence: [chunk_ids]` field.
- The UI renders the reasoning layer plus a 1-hop evidence halo by default; the rest of the evidence layer is reachable by expansion clicks. The whole evidence layer is never dumped to sigma at once.

## Rationale

- A single store gives one delta stream, one snapshot schema, one persistence file.
- Capping only the reasoning layer preserves both PLAN goals: an exhaustive machine-readable topology and a human-readable live display.
- The `dangling: true` attr on a `talks_to` edge lives in the evidence layer, so "the bug rendered as topology" appears even before the agent reasons about it. The demo moment is the agent's hypothesis node attaching to it.

## Consequences

- PLAN M4.1's "model calls a CLI" becomes "model emits graph ops in its JSON turn"; see ADR-0009.
- The concept tier from PLAN M3 is subsumed: it IS the reasoning layer, so nothing was actually cut.
- Node-type vocabulary changes from PLAN, recorded here deliberately: PLAN M4.1's reasoning types `{hypothesis|evidence|cause}` become `{hypothesis|finding}`. "Evidence" as a reasoning type collided with the evidence layer's name, and a "cause" is just a hypothesis with `status: confirmed`, not a separate type. PLAN M3's structural-tier `Bundle` node is also dropped: bundle identity already lives in chunk metadata and `/api/bundles`, and a bundle node would only add an uninformative hub to every subgraph.
- Cap-overflow behavior also changes from PLAN, which said "evict lowest-BM25-score evidence on ruled-out branches". That splits into two mechanisms: the store rejects ops beyond the cap (agent-facing, keeps the model honest), and the UI trims 1-hop halo nodes on `ruled_out` branches when the rendered view exceeds the ~150-node budget (display-facing, keeps PLAN's eviction intent).
