"""ConsoleApi adapter surface for the fde-console UI (ADR-0015).

The console models one continuous session (snapshot + chat + context), while
the Brain models discrete runs. This adapter folds the latest run's state
into the console's shapes (ui/src/api/types.ts) server-side, where all the
data already lives. The runs API (routes.py) is untouched; this is a second
view over the same state, not a second source of truth.

Field names here are camelCase on purpose: they mirror types.ts verbatim.
"""

import asyncio
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import Config
from ..events import read_events
from ..ingest.watcher import list_bundles
from ..runs import RunRegistry

SNAPSHOT_INTERVAL_S = 1.0
MAX_LOG_ENTRIES = 500
MAX_GRAPH_CHUNKS = 200
SEVERITY_RE = re.compile(r"\b(CRITICAL|ERROR|WARN(?:ING)?|INFO|DEBUG)\b", re.IGNORECASE)
ISO_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)")
CONFIDENCE = {"high": 0.9, "medium": 0.6, "low": 0.3}


class ChatRequest(BaseModel):
    text: str


class ContextRequest(BaseModel):
    markdown: str


def create_console_router(cfg: Config, registry: RunRegistry) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/snapshot")
    async def snapshot() -> dict:
        return await asyncio.to_thread(build_snapshot, cfg, registry)

    @router.put("/context")
    async def put_context(body: ContextRequest) -> dict:
        _context_path(cfg).write_text(body.markdown, encoding="utf-8")
        return {"ok": True}

    @router.post("/chat")
    async def chat(body: ChatRequest) -> StreamingResponse:
        """Chat = start (or narrate) a diagnosis. Streams NDJSON TraceEvents."""

        async def gen():
            run_id, new_ctx, error = await asyncio.to_thread(_prepare_run_for_chat, cfg, registry, body.text)
            if error:
                yield _nd(_trace("answer", error))
                return
            if new_ctx is not None:
                registry.launch(new_ctx)  # create_task needs the event loop, not a worker thread
                run_id = new_ctx.run_id
                yield _nd(_trace("user", body.text))
            sent = 0
            while True:
                events = await asyncio.to_thread(read_events, registry.run_dir(run_id) / "events.jsonl", sent)
                for e in events:
                    sent = e.seq
                    trace = _event_to_trace(e.event, e.data, e.seq, e.ts)
                    if trace:
                        yield _nd(trace)
                    if e.event in ("done", "error"):
                        report, _md, _metrics = registry.get_report(run_id)
                        yield _nd(_trace("answer", _answer_text(report, e.event, e.data),
                                         citations=[x["chunk_id"] for x in (report or {}).get("evidence", [])],
                                         ts=e.ts, id_=f"tr-answer-{run_id}"))
                        return
                await asyncio.sleep(0.3)

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @router.get("/stream")
    async def stream() -> StreamingResponse:
        """SSE: a full ConsoleSnapshot per message (the console re-renders whole)."""

        async def gen():
            last = None
            while True:
                snap = await asyncio.to_thread(build_snapshot, cfg, registry)
                payload = json.dumps(snap, ensure_ascii=False)
                if payload != last:
                    last = payload
                    yield f"data: {payload}\n\n"
                await asyncio.sleep(SNAPSHOT_INTERVAL_S)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return router


# ---------- snapshot assembly ----------


def build_snapshot(cfg: Config, registry: RunRegistry) -> dict:
    runs = registry.list_runs()
    run = runs[0] if runs else None
    run_id = run["run_id"] if run else None

    chunks = _load_chunks(registry, run_id) if run_id else []
    events = read_events(registry.run_dir(run_id) / "events.jsonl") if run_id else []
    report = (registry.get_report(run_id)[0] or {}) if run_id and run and run.get("status") == "done" else {}
    cited = {e.get("chunk_id") for e in report.get("evidence", [])}
    scores = _retrieval_scores(events)
    organization = registry.get_organization(run_id) if run_id else None

    return {
        "run": _run_status(run),
        "machines": _machines(cfg, chunks),
        "logs": _logs(chunks),
        "graph": _graph(registry, run_id, chunks, cited, scores, organization),
        "steps": _steps(events, run),
        "trace": [t for t in (_event_to_trace(e.event, e.data, e.seq, e.ts) for e in events) if t]
        + ([_trace("answer", _answer_text(report, "done", {}), citations=sorted(c for c in cited if c),
                   ts=(run or {}).get("finished_at"), id_=f"tr-answer-{run_id}")] if report else []),
        "diagnosis": _diagnosis(report),
        "globalContext": _context_path(cfg).read_text(encoding="utf-8") if _context_path(cfg).is_file() else "",
    }


def _run_status(run: dict | None) -> dict:
    if run is None:
        return {"runId": "idle", "startedAt": "", "elapsedSeconds": 0, "etaSeconds": None, "phase": "collecting"}
    phase = {
        "queued": "collecting",
        "running": "indexing" if run.get("turns_completed", 0) == 0 else "diagnosing",
        "done": "resolved",
        "failed": "failed",
    }[run["status"]]
    return {
        "runId": run["run_id"],
        "startedAt": run.get("started_at") or "",
        "elapsedSeconds": run.get("elapsed_s") or 0,
        "etaSeconds": None,
        "phase": phase,
    }


def _machines(cfg: Config, chunks: list[dict]) -> list[dict]:
    machines = []
    chunk_machines = {c["machine_id"] for c in chunks}
    for b in list_bundles(cfg):
        if b["state"] != "ready" or not b["machine_id"]:
            continue
        role = "backend" if any("backend" in s for s in b["services"] or []) else (
            "frontend" if any(("frontend" in s) or ("portal" in s) for s in b["services"] or []) else "client"
        )
        machines.append({
            "id": b["machine_id"],
            "hostname": b["machine_id"],
            "role": role,
            "address": b["bundle_id"],
            "reachable": True,
            "bundleReceivedAt": b["created_at"],
            "os": "",
        })
    seen = {m["id"] for m in machines}
    for mid in sorted(chunk_machines - seen):  # machines whose bundle left the inbox
        machines.append({"id": mid, "hostname": mid, "role": "client", "address": "", "reachable": True, "bundleReceivedAt": None, "os": ""})
    machines.append({"id": "brain", "hostname": "brain", "role": "brain", "address": "localhost:8000", "reachable": True, "bundleReceivedAt": None, "os": "linux"})
    return machines


def _logs(chunks: list[dict]) -> list[dict]:
    entries = []
    for c in chunks:
        path = c["file_path"]
        is_journal = path.endswith("/journal.txt")
        if not (path.startswith("app_logs/") or is_journal):
            continue
        service = path.split("/")[1] if is_journal else None
        base = c["span"][0]
        for i, line in enumerate(c["text"].splitlines()):
            if not line.strip():
                continue
            sev_match = SEVERITY_RE.search(line)
            sev = (sev_match.group(1).lower() if sev_match else "info").replace("warning", "warn")
            ts_match = ISO_PREFIX_RE.search(line)
            entries.append({
                "id": f"{c['chunk_id']}#L{base + i}",
                "machineId": c["machine_id"],
                "timestamp": ts_match.group(1) if ts_match else "",
                "severity": sev if sev in ("critical", "error", "warn", "info", "debug") else "info",
                "source": "journald" if is_journal else "app_log",
                "path": path,
                "service": service,
                "message": line.strip(),
                "summary": None,
            })
    return entries[:MAX_LOG_ENTRIES]


def _kind(path: str) -> str:
    if path.startswith("docs/"):
        name = path.lower()
        return "ticket" if "ticket" in name else ("runbook" if "runbook" in name else "doc")
    if "/config/" in path or path.endswith(".env"):
        return "config"
    if path.endswith((".js", ".py", ".ts", ".sh")):
        return "code"
    return "log"


MAX_DERIVED_EDGES = 250
MAX_COMENTION_PER_CHUNK = 3
MAX_EMITTED_PER_SERVICE = 5
HUB_GUARD = 8  # entities mentioned by more chunks are too generic to link through
DOC_KINDS = ("doc", "runbook", "ticket")


def _graph(registry: RunRegistry, run_id: str | None, chunks: list[dict], cited: set, scores: dict,
           organization: dict | None = None) -> dict:
    if not chunks:
        return {"chunks": [], "edges": [], "clusters": []}
    interesting = [c for c in chunks if c["chunk_id"] in cited or c["chunk_id"] in scores or _kind(c["file_path"]) != "log"]
    pool = chunks if len(chunks) <= MAX_GRAPH_CHUNKS else interesting[:MAX_GRAPH_CHUNKS]
    included = {c["chunk_id"] for c in pool}
    kind_of = {c["chunk_id"]: _kind(c["file_path"]) for c in pool}
    cluster_of = {}
    clusters_out = []
    if organization:
        for cluster in organization.get("clusters", []):
            members = [m for m in cluster.get("members", []) if m in included]
            if members:
                clusters_out.append({"id": cluster["id"], "label": cluster.get("label")})
                for m in members:
                    cluster_of[m] = cluster["id"]

    nodes = [{
        "id": c["chunk_id"],
        "machineId": c["machine_id"],
        "kind": kind_of[c["chunk_id"]],
        "path": c["file_path"],
        "lineStart": c["span"][0],
        "lineEnd": c["span"][1],
        "label": f"{c['file_path'].rsplit('/', 1)[-1]} L{c['span'][0]}-{c['span'][1]}",
        "content": c["text"],
        "score": scores.get(c["chunk_id"]),
        "implicated": c["chunk_id"] in cited,
        "cluster": cluster_of.get(c["chunk_id"]),
    } for c in pool]

    edges: list[dict] = []
    seen_pairs: set[tuple] = set()

    def add_edge(source: str | None, target: str | None, kind: str, weight: float) -> bool:
        if not source or not target or source == target:
            return False
        if source not in included or target not in included:
            return False
        pair = (source, target, kind)
        if pair in seen_pairs or (target, source, kind) in seen_pairs:
            return False
        seen_pairs.add(pair)
        edges.append({"id": f"ce{len(edges) + 1}", "source": source, "target": target, "kind": kind, "weight": round(weight, 3)})
        return True

    def pick(evidence: list[str], prefer: str | None = None, exclude: str | None = None) -> str | None:
        """Best renderable endpoint chunk: provenance > cited > highest score > first."""
        usable = [cid for cid in evidence if cid in included and cid != exclude]
        if prefer and prefer in included and prefer != exclude:
            return prefer
        if not usable:
            return None
        for cid in usable:
            if cid in cited:
                return cid
        scored = [c for c in usable if c in scores]
        if scored:
            return max(scored, key=lambda c: scores[c])
        return usable[0]

    snapshot = registry.get_graph(run_id) or {"nodes": [], "edges": []}
    node_by_id = {n["id"]: n for n in snapshot["nodes"]}
    rel_to_kind = {"talks_to": "calls", "has_config": "reads",
                   "about": "references", "supports": "references", "contradicts": "contradicts"}

    # structural + reasoning edges, with real endpoint selection
    for e in snapshot["edges"]:
        kind = rel_to_kind.get(e["rel"])
        if kind is None:
            continue
        attrs = e.get("attrs", {})
        src_node, dst_node = node_by_id.get(e["from"]), node_by_id.get(e["to"])
        if src_node is None or dst_node is None:
            continue
        src = pick(src_node.get("evidence", []), prefer=attrs.get("src_chunk"))
        dst = pick(dst_node.get("evidence", []), exclude=src)
        add_edge(src, dst, kind, 2.0 if attrs.get("dangling") else 1.0)

    # emitted: each service's anchor chunk (config, else status) -> its log/journal chunks
    for n in snapshot["nodes"]:
        if n.get("type") != "service":
            continue
        evidence = [cid for cid in n.get("evidence", []) if cid in included]
        anchor = next((cid for cid in evidence if "/config/" in cid), None) or next(
            (cid for cid in evidence if "/status.txt" in cid), None
        )
        if not anchor:
            continue
        emitted = 0
        for cid in evidence:
            if emitted >= MAX_EMITTED_PER_SERVICE:
                break
            if "/journal.txt" in cid or kind_of.get(cid) == "log":
                if add_edge(anchor, cid, "emitted", 1.0):
                    emitted += 1

    # references via co-mention: entities shared by a few chunks link them
    per_chunk_comention: dict[str, int] = {}
    derived = 0
    for n in snapshot["nodes"]:
        if derived >= MAX_DERIVED_EDGES:
            break
        if n.get("type") not in ("env_var", "error", "ticket", "host"):
            continue
        members = [cid for cid in n.get("evidence", []) if cid in included]
        if not 2 <= len(members) <= HUB_GUARD:
            continue
        weight = 1.0 / max(1.0, math.log2(1 + len(members)))
        docs = [c for c in members if kind_of.get(c) in DOC_KINDS]
        others = [c for c in members if kind_of.get(c) not in DOC_KINDS]
        pairs = [(d, o) for d in docs for o in others] or [(members[0], m) for m in members[1:]]
        for source, target in pairs:
            if derived >= MAX_DERIVED_EDGES:
                break
            if per_chunk_comention.get(source, 0) >= MAX_COMENTION_PER_CHUNK:
                continue
            if per_chunk_comention.get(target, 0) >= MAX_COMENTION_PER_CHUNK:
                continue
            if add_edge(source, target, "references", weight):
                per_chunk_comention[source] = per_chunk_comention.get(source, 0) + 1
                per_chunk_comention[target] = per_chunk_comention.get(target, 0) + 1
                derived += 1

    # organizer overlay: semantic relates edges (ADR-0016)
    if organization:
        for e in organization.get("edges", []):
            add_edge(e.get("source"), e.get("target"), "relates", float(e.get("weight", 0.5)))

    return {"chunks": nodes, "edges": edges, "clusters": clusters_out}


def _steps(events, run: dict | None) -> list[dict]:
    if run is None:
        return []
    steps: list[dict] = []
    running = run.get("status") == "running"
    for e in events:
        if e.event != "status":
            continue
        state = e.data.get("state", "")
        label = {
            "ingesting": "Indexing bundles",
            "thinking": f"Turn {e.data.get('turn')}: reasoning",
            "reporting": "Writing report",
            "refining": "Refining",
        }.get(state.split(":")[0], state)
        if steps and steps[-1]["status"] == "running":
            steps[-1]["status"] = "done"
            steps[-1]["finishedAt"] = None
        steps.append({"id": f"step-{e.seq}", "machineId": "brain", "label": label, "status": "running",
                      "startedAt": None, "finishedAt": None, "detail": state if ":" in state else None})
    if steps and not running:
        steps[-1]["status"] = "failed" if run.get("status") == "failed" else "done"
    return steps


def _event_to_trace(event: str, data: dict, seq: int = 0, ts: float = 0.0) -> dict | None:
    id_ = f"tr-{seq}" if seq else None
    if event == "query":
        return _trace("query", f'search "{data.get("q")}" (k={data.get("k")})', ts=ts, id_=id_)
    if event == "chunk":
        return _trace("retrieval", f'{data.get("file")} [{data.get("via")}]', citations=[data.get("cid")], ts=ts, id_=id_)
    if event == "status" and data.get("state") == "thinking":
        return _trace("thought", f"Turn {data.get('turn')}: forming and testing hypotheses", ts=ts, id_=id_)
    if event == "graph" and data.get("op") == "add_node" and data.get("node", {}).get("layer") == "reasoning":
        node = data["node"]
        return _trace("thought", f'{node.get("type")}: {node.get("label")}', citations=node.get("evidence", []), ts=ts, id_=id_)
    return None


def _answer_text(report: dict | None, terminal: str, data: dict) -> str:
    if terminal == "error" or not report:
        return f"Run failed: {data.get('message', 'no report produced')}"
    plan = "\n".join(f"{s['step']}. {s['action']}" for s in report.get("action_plan", []))
    return f"**Root cause** ({report.get('confidence')} confidence): {report.get('root_cause')}\n\n**Action plan**\n{plan}"


def _diagnosis(report: dict) -> dict:
    return {
        "rootCause": report.get("root_cause"),
        "confidence": CONFIDENCE.get(report.get("confidence"), 0.0),
        "evidence": [e["chunk_id"] for e in report.get("evidence", [])],
        "actions": [{"id": str(s["step"]), "text": s["action"], "command": s.get("command")} for s in report.get("action_plan", [])],
    }


# ---------- helpers ----------


def _prepare_run_for_chat(cfg: Config, registry: RunRegistry, text: str):
    """Reuse the active run if one is going; otherwise create (NOT launch - the
    caller launches on the event loop) a run on every ready bundle with the
    chat text (+ saved global context) as the question."""
    for run in registry.list_runs():
        if run["status"] in ("queued", "running"):
            return run["run_id"], None, None
    ready = [b["bundle_id"] for b in list_bundles(cfg) if b["state"] == "ready"]
    if not ready:
        return None, None, "No bundles in the inbox yet. Collect from a client (collector.sh, brain pull, or brainctl usb) first."
    question = text
    ctx_file = _context_path(cfg)
    if ctx_file.is_file() and ctx_file.read_text(encoding="utf-8").strip():
        question += "\n\nOperator context:\n" + ctx_file.read_text(encoding="utf-8")
    return None, registry.create_run(ready, question), None


def _load_chunks(registry: RunRegistry, run_id: str) -> list[dict]:
    live = registry.live(run_id)
    if live and live.chunk_store is not None:
        return [c.to_dict() for c in live.chunk_store.values()]
    path = registry.run_dir(run_id) / "chunks.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _retrieval_scores(events) -> dict:
    scores: dict = {}
    for e in events:
        if e.event == "chunk":
            cid = e.data.get("cid")
            score = e.data.get("score") or 0.0
            if cid and score >= scores.get(cid, -1):
                scores[cid] = score
    return scores


def _trace(kind: str, text: str, citations: list | None = None, ts: float | str | None = None, id_: str | None = None) -> dict:
    """Timestamps and ids must be STABLE across snapshot builds: the SSE
    change-detection (and the UI's render keys) depend on identical state
    producing identical frames. Only genuinely-live traces may default to now."""
    if isinstance(ts, (int, float)) and ts:
        stamp = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")
    elif isinstance(ts, str) and ts:
        stamp = ts
    else:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "id": id_ or f"tr-{abs(hash((kind, text))) % 10**10}",
        "kind": kind,
        "text": text,
        "timestamp": stamp,
        "citations": [c for c in (citations or []) if c],
    }


def _nd(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _context_path(cfg: Config) -> Path:
    return cfg.home / "console-context.md"
