"""The retrieval facade the agent loop uses: search() + expand() (SPEC 6.2, 7.2).

search() is the embeddings swap seam. expand() is the move BM25 cannot make:
chunks -> their nodes -> 1-2 hops -> neighboring chunks that share no
vocabulary with the query.
"""

from dataclasses import dataclass, field

from .graph.store import GraphStore
from .index.bm25 import Bm25Index
from .ingest.chunker import Chunk


@dataclass
class Expansion:
    subgraph_text: str
    chunks: list[Chunk] = field(default_factory=list)


class Retriever:
    def __init__(self, chunk_store: dict[str, Chunk], index: Bm25Index, graph: GraphStore):
        self.chunk_store = chunk_store
        self.index = index
        self.graph = graph

    def search(self, query: str, k: int = 5) -> list[tuple[Chunk, float]]:
        return [(self.chunk_store[cid], score) for cid, score in self.index.search(query, k)]

    def expand(self, chunk_ids: list[str], hops: int = 1, exclude: set[str] | None = None) -> Expansion:
        exclude = exclude or set()
        seeds: set[str] = set()
        for cid in chunk_ids:
            chunk = self.chunk_store.get(cid)
            if chunk:
                seeds.update(chunk.mentions)
        if not seeds:
            return Expansion(subgraph_text="(no graph nodes reachable from those chunks)")

        subgraph = self.graph.neighbors(seeds, hops=min(max(hops, 1), 2))
        extra: list[Chunk] = []
        seen_chunks = set(chunk_ids) | exclude
        for nid in sorted(subgraph):
            for cid in self.graph.nodes[nid].evidence:
                if cid not in seen_chunks and cid in self.chunk_store:
                    seen_chunks.add(cid)
                    extra.append(self.chunk_store[cid])

        return Expansion(
            subgraph_text=self.render_subgraph(subgraph),
            chunks=extra,
        )

    def render_subgraph(self, node_ids: set[str]) -> str:
        """Compact text rendering, e.g.
        service:laptop-a/backend -talks_to-> host:db.internal [DANGLING: no machine matches]"""
        lines = []
        edges = self.graph.edges_within(node_ids)
        for edge in edges:
            suffix = " [DANGLING: no machine matches]" if edge.attrs.get("dangling") else ""
            lines.append(f"{edge.src} -{edge.rel}-> {edge.dst}{suffix}")
        isolated = node_ids - {e.src for e in edges} - {e.dst for e in edges}
        for nid in sorted(isolated):
            lines.append(nid)
        return "\n".join(lines) if lines else "(empty subgraph)"
