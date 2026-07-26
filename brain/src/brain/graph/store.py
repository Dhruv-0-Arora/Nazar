"""The single graph mutation path (SPEC 6.3, ADR-0005, ADR-0009).

Everything that changes the graph goes through GraphStore, which is therefore
the one place that enforces caps, assigns IDs, and emits deltas. The on_delta
callback fires only for reasoning-layer mutations: evidence construction at
ingest would flood the SSE stream, and the UI gets that layer via snapshot.
"""

from typing import Callable

import networkx as nx

from .model import (
    EVIDENCE_RELS,
    LABEL_MAX,
    MAX_FINDINGS_PER_HYPOTHESIS,
    MAX_HYPOTHESES,
    REASONING_RELS,
    REASONING_TYPES,
    STATUSES,
    Edge,
    Node,
    evidence_node_id,
)


class GraphStore:
    def __init__(self, on_delta: Callable[[dict], None] | None = None):
        self._g = nx.MultiDiGraph()
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}
        self._edge_keys: set[tuple[str, str, str]] = set()
        self._edge_seq = 0
        self._hyp_seq = 0
        self._finding_seq = 0
        self._findings_per_hyp: dict[str, int] = {}
        self._on_delta = on_delta or (lambda d: None)

    # ---------- evidence layer (ingest-time, deterministic) ----------

    def get_or_create(self, type_: str, value: str, machine_id: str | None = None, label: str | None = None) -> Node:
        node_id = evidence_node_id(type_, value, machine_id)
        if node_id not in self.nodes:
            node = Node(id=node_id, layer="evidence", type=type_, label=(label or f"{type_} {value}")[:LABEL_MAX])
            self.nodes[node_id] = node
            self._g.add_node(node_id)
        return self.nodes[node_id]

    def add_evidence(self, node_id: str, chunk_id: str) -> None:
        ev = self.nodes[node_id].evidence
        if chunk_id not in ev:
            ev.append(chunk_id)

    def add_edge(self, src: str, dst: str, rel: str, attrs: dict | None = None) -> Edge | None:
        """Deduped on (src, dst, rel); returns None when it already exists."""
        key = (src, dst, rel)
        if key in self._edge_keys:
            if attrs:
                for e in self.edges.values():
                    if (e.src, e.dst, e.rel) == key:
                        e.attrs.update(attrs)
            return None
        self._edge_keys.add(key)
        self._edge_seq += 1
        edge = Edge(id=f"e{self._edge_seq}", src=src, dst=dst, rel=rel, attrs=attrs or {})
        self.edges[edge.id] = edge
        self._g.add_edge(src, dst, key=edge.id, rel=rel)
        return edge

    # ---------- reasoning layer (agent-driven deltas, API.md section 4) ----------

    def apply_delta(self, delta: dict) -> dict:
        """Validate and apply one agent delta. Returns {'assigned_id': ...} /
        {'ok': True} on success, {'error': ...} on rejection (never raises)."""
        try:
            op = delta.get("op")
            if op == "add_node":
                return self._apply_add_node(delta.get("node") or {})
            if op == "add_edge":
                return self._apply_add_edge(delta.get("edge") or {})
            if op == "set_status":
                return self._apply_set_status(delta)
            return {"error": f"unknown op {op!r}"}
        except Exception as e:  # noqa: BLE001 - agent input must never crash the loop
            return {"error": f"malformed delta: {e}"}

    def _apply_add_node(self, spec: dict) -> dict:
        if spec.get("layer") != "reasoning":
            return {"error": "agent may only add reasoning-layer nodes"}
        type_ = spec.get("type")
        if type_ not in REASONING_TYPES:
            return {"error": f"type must be one of {sorted(REASONING_TYPES)}"}
        label = str(spec.get("label", ""))[:LABEL_MAX]
        if not label:
            return {"error": "label required"}

        if type_ == "hypothesis":
            if self._hyp_seq >= MAX_HYPOTHESES:
                return {"error": f"hypothesis cap ({MAX_HYPOTHESES}) reached; rule out or reuse existing ones"}
            self._hyp_seq += 1
            node_id = f"hyp:{self._hyp_seq}"
            parent_edge = None
        else:  # finding
            parent = spec.get("parent")
            stance = spec.get("stance")
            if parent not in self.nodes or self.nodes[parent].type != "hypothesis":
                return {"error": "finding requires 'parent' set to an existing hypothesis id"}
            if stance not in ("supports", "contradicts"):
                return {"error": "finding requires 'stance': supports | contradicts"}
            if self._findings_per_hyp.get(parent, 0) >= MAX_FINDINGS_PER_HYPOTHESIS:
                return {"error": f"finding cap ({MAX_FINDINGS_PER_HYPOTHESIS}) reached for {parent}"}
            self._finding_seq += 1
            node_id = f"finding:{self._finding_seq}"
            self._findings_per_hyp[parent] = self._findings_per_hyp.get(parent, 0) + 1
            parent_edge = (node_id, parent, stance)

        evidence = [c for c in spec.get("evidence", []) if isinstance(c, str)]
        node = Node(id=node_id, layer="reasoning", type=type_, label=label, status="open", evidence=evidence)
        self.nodes[node_id] = node
        self._g.add_node(node_id)
        self._on_delta({"op": "add_node", "node": node.to_dict()})
        if parent_edge:
            edge = self.add_edge(*parent_edge)
            if edge:
                self._on_delta({"op": "add_edge", "edge": edge.to_dict()})
        return {"assigned_id": node_id}

    def _apply_add_edge(self, spec: dict) -> dict:
        src, dst, rel = spec.get("from"), spec.get("to"), spec.get("rel")
        if src not in self.nodes:
            return {"error": f"unknown node {src!r}"}
        if dst not in self.nodes:
            return {"error": f"unknown node {dst!r}"}
        if rel not in REASONING_RELS:
            return {"error": f"rel must be one of {sorted(REASONING_RELS)}"}
        edge = self.add_edge(src, dst, rel, spec.get("attrs") or {})
        if edge is None:
            return {"ok": True}  # idempotent duplicate
        self._on_delta({"op": "add_edge", "edge": edge.to_dict()})
        return {"assigned_id": edge.id}

    def _apply_set_status(self, delta: dict) -> dict:
        node_id, status = delta.get("id"), delta.get("status")
        node = self.nodes.get(node_id)
        if node is None:
            return {"error": f"unknown node {node_id!r} (ids are assigned in earlier turns)"}
        if node.layer != "reasoning":
            return {"error": "status applies to reasoning nodes only"}
        if status not in STATUSES:
            return {"error": f"status must be one of {sorted(STATUSES)}"}
        node.status = status
        self._on_delta({"op": "set_status", "id": node_id, "status": status})
        return {"ok": True}

    # ---------- queries ----------

    def neighbors(self, seed_ids: set[str], hops: int = 1) -> set[str]:
        """Undirected expansion over the evidence layer."""
        seen = {s for s in seed_ids if s in self.nodes}
        frontier = set(seen)
        for _ in range(max(0, hops)):
            nxt = set()
            for nid in frontier:
                nxt.update(self._g.successors(nid))
                nxt.update(self._g.predecessors(nid))
            nxt = {n for n in nxt if self.nodes[n].layer == "evidence"}
            nxt -= seen
            if not nxt:
                break
            seen |= nxt
            frontier = nxt
        return seen

    def edges_within(self, node_ids: set[str]) -> list[Edge]:
        return [e for e in self.edges.values() if e.src in node_ids and e.dst in node_ids]

    def snapshot(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges.values()],
        }

    _EVIDENCE_RELS = EVIDENCE_RELS  # exposed for build-time sanity checks
