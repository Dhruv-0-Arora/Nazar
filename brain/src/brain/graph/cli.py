"""`brain graph` subcommand: inspect a run's persisted graph (debug tool)."""

import json
from pathlib import Path


def summarize(graph_json_path: Path, as_json: bool = False) -> str:
    snapshot = json.loads(graph_json_path.read_text(encoding="utf-8"))
    if as_json:
        return json.dumps(snapshot, indent=2)

    nodes = snapshot.get("nodes", [])
    edges = snapshot.get("edges", [])
    by_layer: dict[str, int] = {}
    for n in nodes:
        by_layer[n["layer"]] = by_layer.get(n["layer"], 0) + 1
    lines = [
        f"run: {snapshot.get('run_id', '?')}  seq: {snapshot.get('seq', '?')}",
        f"nodes: {len(nodes)} ({', '.join(f'{k}={v}' for k, v in sorted(by_layer.items()))})  edges: {len(edges)}",
        "",
    ]
    for n in nodes:
        if n["layer"] == "reasoning":
            lines.append(f"  [{n.get('status', '-'):>9}] {n['id']}: {n['label']}")
    dangling = [e for e in edges if e.get("attrs", {}).get("dangling")]
    if dangling:
        lines.append("")
        lines.append("dangling edges (configs pointing at nothing that exists):")
        for e in dangling:
            lines.append(f"  {e['from']} -{e['rel']}-> {e['to']}")
    return "\n".join(lines)
