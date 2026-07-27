"""Node/Edge dataclasses, ID schemes, and caps (API.md section 4, ADR-0005)."""

from dataclasses import dataclass, field

REASONING_TYPES = {"hypothesis", "finding"}
REASONING_RELS = {"about", "supports", "contradicts", "retrieved_by"}
STATUSES = {"open", "confirmed", "ruled_out"}

MAX_HYPOTHESES = 8
MAX_FINDINGS_PER_HYPOTHESIS = 5
LABEL_MAX = 80


@dataclass
class Node:
    id: str
    layer: str  # evidence | reasoning
    type: str
    label: str
    status: str | None = None  # reasoning nodes only
    evidence: list[str] = field(default_factory=list)  # chunk IDs
    attrs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "layer": self.layer,
            "type": self.type,
            "label": self.label,
            "evidence": self.evidence,
            "attrs": self.attrs,
        }
        if self.status is not None:
            d["status"] = self.status
        return d


@dataclass
class Edge:
    id: str
    src: str
    dst: str
    rel: str
    attrs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "from": self.src, "to": self.dst, "rel": self.rel, "attrs": self.attrs}


def evidence_node_id(type_: str, value: str, machine_id: str | None = None) -> str:
    """Deterministic evidence-layer IDs; file nodes use '/' between machine and
    path so the chunk-ID grammar stays unambiguous (API.md section 4)."""
    if type_ == "file":
        assert machine_id is not None
        return f"file:{machine_id}/{value}"
    if type_ == "service" and machine_id is not None:
        return f"service:{machine_id}/{value}"
    return f"{type_}:{value}"
