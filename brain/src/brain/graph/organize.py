"""Graph organizer: the embedding pair-model (ADR-0016).

Runs beside the diagnosing model, event-driven (after ingest, after each turn,
after conclude), and produces a chunk-level ORGANIZATION OVERLAY: semantic
`relates` edges, community cluster assignments, and orphan adoption. The
overlay never touches the deterministic evidence graph, the reasoning layer,
or anything agent-visible - it exists purely so the console renders a cohesive
graph. A failed pass degrades to no overlay, never a failed run.
"""

import json
import threading
from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from ..config import Config
from ..llm import LLMError

EMBED_TEXT_CAP = 2000
HUB_GUARD = 8  # entities mentioned by more chunks than this are too generic to link through
COMENTION_TYPES = ("env_var:", "error:", "ticket:", "host:", "ip:", "port:")


@dataclass
class _RunState:
    thread: threading.Thread | None = None
    dirty: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


class Organizer:
    def __init__(self, cfg: Config, embedder):
        self.cfg = cfg
        self.embedder = embedder
        self._runs: dict[str, _RunState] = {}
        self._registry_lock = threading.Lock()

    # ---------- public API ----------

    def notify(self, ctx, phase: str) -> None:
        """Schedule a pass; coalesces if one is already running for this run."""
        if self.embedder is None or ctx.chunk_store is None:
            return
        with self._registry_lock:
            state = self._runs.setdefault(ctx.run_id, _RunState())
        with state.lock:
            if state.thread is not None and state.thread.is_alive():
                state.dirty = True
                return
            state.dirty = False
            state.thread = threading.Thread(target=self._worker, args=(ctx, state, phase), name=f"organize:{ctx.run_id}", daemon=True)
            state.thread.start()

    def run_pass(self, ctx, phase: str) -> dict | None:
        """One synchronous organizer pass (also the unit-test entry point)."""
        try:
            overlay = self._organize(ctx)
        except LLMError as e:
            self._emit(ctx, {"phase": phase, "error": str(e)})
            return None
        except Exception as e:  # noqa: BLE001 - the organizer must never fail a run
            self._emit(ctx, {"phase": phase, "error": f"organizer pass failed: {e}"})
            return None
        ctx.organization = overlay
        (ctx.dir / "organization.json").write_text(json.dumps(overlay, indent=2), encoding="utf-8")
        self._emit(ctx, {"phase": phase, "clusters": len(overlay["clusters"]), "edges": len(overlay["edges"])})
        return overlay

    # ---------- internals ----------

    def _worker(self, ctx, state: _RunState, phase: str) -> None:
        while True:
            self.run_pass(ctx, phase)
            with state.lock:
                if not state.dirty:
                    state.thread = None
                    return
                state.dirty = False
                phase = "coalesced"

    def _emit(self, ctx, data: dict) -> None:
        if ctx.events is not None:
            ctx.events.emit("organize", data)  # no-op if the log is closed

    def _organize(self, ctx) -> dict:
        chunks = list(ctx.chunk_store.values())
        ids = [c.id for c in chunks]
        vectors = self._embeddings(ctx, chunks)

        relates = self._relates_edges(ids, vectors, chunks)
        projection = self._projection_graph(ids, chunks, relates)
        clusters = self._clusters(projection)
        adopted = self._adopt_orphans(ids, vectors, projection, clusters)
        relates.extend(adopted)

        return {
            "version": 1,
            "seq": ctx.events.seq if ctx.events else 0,
            "clusters": clusters,
            "edges": relates,
        }

    def _embeddings(self, ctx, chunks) -> np.ndarray:
        """Embed once per run; cache to runs/<id>/embeddings.npz keyed by chunk id."""
        cache = ctx.dir / "embeddings.npz"
        if cache.is_file():
            data = np.load(cache, allow_pickle=False)
            cached_ids = list(data["ids"])
            if cached_ids == [c.id for c in chunks]:
                return data["vectors"]
        texts = [f"{c.file_path}\n{c.text[:EMBED_TEXT_CAP]}" for c in chunks]
        raw = np.asarray(self.embedder.embed(texts), dtype=np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        vectors = raw / np.maximum(norms, 1e-9)
        np.savez(cache, ids=np.asarray([c.id for c in chunks]), vectors=vectors)
        return vectors

    def _relates_edges(self, ids: list[str], vectors: np.ndarray, chunks) -> list[dict]:
        """Top-k cosine neighbors above threshold, skipping same-file pairs."""
        if len(ids) < 2:
            return []
        sim = vectors @ vectors.T
        file_of = {c.id: (c.machine_id, c.file_path) for c in chunks}
        per_chunk: dict[str, int] = {}
        edges: list[dict] = []
        seen: set[tuple[str, str]] = set()

        order = np.argsort(sim, axis=1)[:, ::-1]
        for i, cid in enumerate(ids):
            for j in order[i][1 : self.cfg.org_max_edges_per_chunk * 3 + 1]:
                score = float(sim[i, j])
                if score < self.cfg.org_sim_threshold:
                    break
                other = ids[int(j)]
                if file_of[cid] == file_of[other]:
                    continue  # same-file siblings connect via their file already
                pair = tuple(sorted((cid, other)))
                if pair in seen:
                    continue
                if per_chunk.get(cid, 0) >= self.cfg.org_max_edges_per_chunk:
                    break
                if per_chunk.get(other, 0) >= self.cfg.org_max_edges_per_chunk:
                    continue
                seen.add(pair)
                per_chunk[cid] = per_chunk.get(cid, 0) + 1
                per_chunk[other] = per_chunk.get(other, 0) + 1
                edges.append({"source": pair[0], "target": pair[1], "kind": "relates", "weight": round(score, 3)})
                if len(edges) >= self.cfg.org_max_edges:
                    return edges
        return edges

    def _projection_graph(self, ids: list[str], chunks, relates: list[dict]) -> nx.Graph:
        """Undirected chunk graph = co-mention edges (hub-guarded) + relates."""
        g = nx.Graph()
        g.add_nodes_from(ids)
        by_entity: dict[str, list[str]] = {}
        for c in chunks:
            for node_id in c.mentions:
                if node_id.startswith(COMENTION_TYPES):
                    by_entity.setdefault(node_id, []).append(c.id)
        for members in by_entity.values():
            if not 2 <= len(members) <= HUB_GUARD:
                continue
            anchor = members[0]
            for other in members[1:]:
                g.add_edge(anchor, other, weight=1.0 / max(1, len(members) - 1))
        for e in relates:
            g.add_edge(e["source"], e["target"], weight=e["weight"])
        return g

    def _clusters(self, projection: nx.Graph) -> list[dict]:
        communities = nx.algorithms.community.greedy_modularity_communities(projection, weight="weight")
        ordered = sorted((sorted(c) for c in communities), key=lambda m: (-len(m), m[0]))
        clusters = []
        for i, members in enumerate(ordered, start=1):
            if len(members) < 2:
                continue  # singletons are orphans, handled below
            clusters.append({"id": f"c{i}", "label": None, "members": members})
        return clusters

    def _adopt_orphans(self, ids, vectors, projection: nx.Graph, clusters) -> list[dict]:
        """Attach degree-0 chunks to the cluster with the nearest centroid."""
        if not clusters:
            return []
        index_of = {cid: i for i, cid in enumerate(ids)}
        centroids = {c["id"]: vectors[[index_of[m] for m in c["members"]]].mean(axis=0) for c in clusters}
        for cid in centroids:
            centroids[cid] = centroids[cid] / max(float(np.linalg.norm(centroids[cid])), 1e-9)

        adopted: list[dict] = []
        floor = self.cfg.org_sim_threshold - 0.1
        for chunk_id in ids:
            if projection.degree(chunk_id) > 0:
                continue
            vec = vectors[index_of[chunk_id]]
            best_cluster, best_score = max(
                ((cid, float(vec @ centroid)) for cid, centroid in centroids.items()), key=lambda p: p[1]
            )
            cluster = next(c for c in clusters if c["id"] == best_cluster)
            member_scores = [(m, float(vec @ vectors[index_of[m]])) for m in cluster["members"]]
            nearest, _ = max(member_scores, key=lambda p: p[1])
            cluster["members"].append(chunk_id)
            adopted.append({"source": chunk_id, "target": nearest, "kind": "relates", "weight": round(max(best_score, floor), 3)})
        return adopted
