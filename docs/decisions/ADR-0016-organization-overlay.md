# ADR-0016: Graph organizer as a chunk-level overlay, powered by an embedding pair-model

Status: accepted.

## Context

The console graph rendered many chunk nodes with almost no edges.
Most of that was deterministic loss (the console mapping discarded `mentions`/`located_on`/`listens_on`, machine nodes had no renderable evidence, endpoints collapsed to `evidence[0]`, and the UI never re-laid-out when edges arrived late), fixed directly in the pipeline.
Beyond those fixes, Dhruv wants a second model (~40 GB headroom beside the 81 GB qwen3.5:122b) organizing the graph as a pair to the diagnosing model.

## Decision

1. The organizer's output is a chunk-level ORGANIZATION OVERLAY, not a third `GraphStore` layer.
   ADR-0004 makes chunks and entity nodes deliberately distinct; semantic chunk-chunk similarity and chunk clusters are statements about chunks, so they live beside the chunk store: `ctx.organization` in memory, `runs/<run_id>/organization.json` on disk (`{version, seq, clusters: [{id, label, members}], edges: [{source, target, kind: "relates", weight}]}`), embeddings cached at `runs/<run_id>/embeddings.npz`.
2. The pair model is `qwen3-embedding:8b` (4.7 GB, already pulled), driven by `OllamaEmbedder` in `llm.py` (preserving the only-Ollama-module invariant) and `brain/src/brain/graph/organize.py`.
   A pass computes cosine `relates` edges (threshold/caps in config), community clusters via `networkx greedy_modularity_communities` over co-mention + relates projections, and orphan adoption to the nearest cluster centroid.
3. Cadence is event-driven, not a timer: the loop notifies the organizer after ingest, after each turn, and after conclude; a per-run worker thread coalesces overlapping notifications.
   The graph only changes at those discrete moments and turns take tens of seconds, so hooks give natural pacing with zero idle spin.
4. Isolation guarantees: the overlay is never agent-visible (retrieval, prompts, and the reasoning layer are untouched, so eval results cannot shift); a failed pass emits one `organize` event with an error and degrades to the deterministic graph; `EventLog` is now lock-guarded with emit-after-close as a no-op so a late organizer pass cannot crash.
5. Stage 3 follow-up (not built): an LLM curator for cluster labels, alias proposals, and narrative edges, defaulting to `nemotron-cascade-2:30b` (`BRAIN_CURATOR_MODEL`, empty = disabled), scheduled only when the diagnosing model is idle.

## Consequences

- ConsoleApi additions (additive, both owners): `"relates"` EdgeKind, `Chunk.cluster`, `GraphPayload.clusters`; API.md gains `GET /api/runs/{run_id}/organization`, the `organize` SSE event, and the `organization.json` artifact.
- `OLLAMA_MAX_LOADED_MODELS` moves from 1 to 2 (SPEC section 9): the embedder is 4.7 GB beside the 81 GB primary with ~40 GB measured headroom; the original 1 was set before headroom was measured.
- The UI's force layout now treats organizer clusters (else machines) as gravity wells, packs degree-0 chunks into a peripheral grid, and re-runs (seeded from current positions) when edges change, not only nodes.
