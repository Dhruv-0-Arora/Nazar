# ADR-0004: Chunks and graph nodes are distinct objects; chunk IDs are the universal currency

Status: accepted (ratifies the resolution already reached in PLAN.md).

## Context

The instinct to unify "chunk" and "node" conflates two granularities.
A chunk is a span of verbatim evidence text (what BM25 scores, what enters model context).
A node is a typed thing the text talks about (`port:5432`), mentioned by many chunks across machines.
That many-to-many relationship is the entire value of the graph.

## Decision

- Chunking is deterministic and stable; it is the retrieval substrate and the citation system.
- Graph extraction reads the chunk store (never raw bundles) and records `node.evidence` chunk IDs at the moment of extraction. There is no reconciliation layer; the chunk<->node link is a byproduct of extraction.
- Chunk ID grammar `machine:path:Lstart-Lend` (CONTRACT.md section 6) threads BM25 results, graph evidence, report citations, and UI click-through with one scheme.

## Consequences

- The graph can be rebuilt ten times per run without invalidating the inverted index or any cited chunk ID.
- Every report claim is checkable: the Brain validates that cited chunk IDs resolve, and the UI opens them.
- Retrieval gets two complementary moves: `search()` (lexical entry) and `expand()` (graph traversal to chunks sharing no vocabulary with the query).
