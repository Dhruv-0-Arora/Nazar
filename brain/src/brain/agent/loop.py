"""The serial agent loop (SPEC section 7).

Turn N+1 depends on turn N: never parallelize the loop itself. Parallelism
lives across cases (runs.py semaphore) and within-turn search fan-out only.
The message array is append-only and the system prompt is static (prefix
cache discipline, SPEC 7.4).
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config
from ..events import EventLog
from ..graph.build import build_graph
from ..graph.store import GraphStore
from ..index.bm25 import Bm25Index
from ..ingest.bundle import Manifest, load_manifest
from ..ingest.chunker import Chunk, chunk_bundle
from ..llm import ChatResult, LLMError
from ..report import ReportError, parse_report, render_markdown
from ..retrieval import Retriever
from . import prompts
from .protocol import ExpandAction, GraphAction, ProtocolError, SearchAction, parse_turn

CHUNK_TEXT_CAP = 1200
PARSE_RETRIES = 2


@dataclass
class RunContext:
    run_id: str
    dir: Path
    bundle_ids: list[str]
    question: str
    full_context: bool = False  # usb transport: inject whole bundles into turn 1 (ADR-0012)
    status: str = "queued"
    error: str | None = None
    started_at: str = ""
    finished_at: str = ""
    elapsed_s: float = 0.0
    turns_completed: int = 0
    # live state, populated during execution, used by the API mid-run
    chunk_store: dict[str, Chunk] | None = None
    graph: GraphStore | None = None
    events: EventLog | None = None
    metrics: list[dict] = field(default_factory=list)

    def meta(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "bundle_ids": self.bundle_ids,
            "question": self.question,
            "full_context": self.full_context,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_s": round(self.elapsed_s, 2),
            "turns_completed": self.turns_completed,
            "error": self.error,
        }

    def save_meta(self) -> None:
        (self.dir / "meta.json").write_text(json.dumps(self.meta(), indent=2), encoding="utf-8")


def execute_run(ctx: RunContext, cfg: Config, llm) -> None:
    """Blocking; run via asyncio.to_thread. Owns all run artifacts and events."""
    ev = EventLog(ctx.dir / "events.jsonl")
    ctx.events = ev
    raw_dir = ctx.dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    start = time.monotonic()
    ctx.status = "running"
    ctx.started_at = datetime.now(timezone.utc).isoformat()
    ctx.save_meta()
    query_trail: list[str] = []

    try:
        retriever, manifests = _ingest(ctx, ev)
        full_block = None
        if ctx.full_context:
            full_block, included, omitted = _render_full_context(retriever.chunk_store, cfg.full_ctx_chars)
            ev.emit("status", {"turn": 0, "state": f"full-context: {included} chunks injected, {omitted} omitted"})
        messages = [
            {"role": "system", "content": prompts.SYSTEM},
            {
                "role": "user",
                "content": prompts.initial_user(
                    prompts.format_case_summary(manifests, _system_digests(retriever.chunk_store)),
                    ctx.question,
                    cfg.max_turns,
                    full_context_block=full_block,
                ),
            },
        ]

        concluded = False
        for turn_no in range(1, cfg.max_turns + 1):
            ev.emit("status", {"turn": turn_no, "state": "thinking"})
            turn, assistant_text = _model_turn(ctx, llm, messages, turn_no, ev, raw_dir)
            messages.append({"role": "assistant", "content": assistant_text})
            ctx.turns_completed = turn_no
            if turn is None:  # unparseable after retries; skip the turn
                messages.append({"role": "user", "content": json.dumps({"results": [], "note": "turn skipped: output was not parseable", "turns_remaining": cfg.max_turns - turn_no})})
                continue
            if turn.conclude:
                # models often bundle final graph ops (e.g. confirming a
                # hypothesis) with conclude; apply them before reporting
                for action in turn.actions:
                    if isinstance(action, GraphAction):
                        retriever.graph.apply_delta(action.delta)
                concluded = True
                break
            feedback = _execute_actions(turn, retriever, ev, turn_no, query_trail)
            feedback["turns_remaining"] = cfg.max_turns - turn_no
            messages.append({"role": "user", "content": json.dumps(feedback, ensure_ascii=False)})

        if not concluded:
            ev.emit("status", {"turn": ctx.turns_completed, "state": "refining"})

        report = _conclude(ctx, cfg, llm, messages, retriever, ev, raw_dir)
        ctx.elapsed_s = time.monotonic() - start

        (ctx.dir / "report.json").write_text(json.dumps(report.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
        (ctx.dir / "report.md").write_text(
            render_markdown(report, run_id=ctx.run_id, elapsed_s=ctx.elapsed_s, bundle_ids=ctx.bundle_ids, query_trail=query_trail),
            encoding="utf-8",
        )
        snapshot = ctx.graph.snapshot()
        snapshot.update({"run_id": ctx.run_id, "seq": ev.seq})
        (ctx.dir / "graph.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        (ctx.dir / "metrics.json").write_text(json.dumps(_metrics_summary(ctx), indent=2), encoding="utf-8")

        ctx.status = "done"
        ctx.finished_at = datetime.now(timezone.utc).isoformat()
        ctx.save_meta()
        ev.emit("done", {"run_id": ctx.run_id, "elapsed_s": round(ctx.elapsed_s, 1)})
    except Exception as e:  # noqa: BLE001 - a run failure must be recorded, never propagate
        ctx.status = "failed"
        ctx.error = str(e)
        ctx.elapsed_s = time.monotonic() - start
        ctx.finished_at = datetime.now(timezone.utc).isoformat()
        ctx.save_meta()
        ev.emit("error", {"message": str(e)})
    finally:
        ev.close()


# ---------- stages ----------


def _ingest(ctx: RunContext, ev: EventLog) -> tuple[Retriever, list[Manifest]]:
    ev.emit("status", {"turn": 0, "state": "ingesting"})
    manifests: list[Manifest] = []
    chunks: list[Chunk] = []
    for bundle_dir in sorted((ctx.dir / "bundles").iterdir()):
        if not bundle_dir.is_dir():
            continue
        manifest = load_manifest(bundle_dir)
        manifests.append(manifest)
        chunks.extend(chunk_bundle(bundle_dir, manifest))
    if not chunks:
        raise RuntimeError("case contains no ingestible chunks")

    chunk_store = {c.id: c for c in chunks}
    index = Bm25Index(chunks)
    graph = GraphStore(on_delta=lambda d: ev.emit("graph", d))
    build_graph(chunks, manifests, graph)
    # serialize AFTER graph build so chunk.mentions is populated (SPEC 6.1)
    with open(ctx.dir / "chunks.jsonl", "w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")

    ctx.chunk_store = chunk_store
    ctx.graph = graph
    return Retriever(chunk_store, index, graph), manifests


def _model_turn(ctx: RunContext, llm, messages: list[dict], turn_no: int, ev: EventLog, raw_dir: Path):
    """One JSON turn with parse retries. Returns (Turn | None, last_assistant_text)."""
    local = list(messages)
    assistant_text = ""
    for attempt in range(PARSE_RETRIES + 1):
        result: ChatResult = _chat_with_retry(llm, local, json_format=True)
        assistant_text = result.text
        (raw_dir / f"turn-{turn_no}-attempt-{attempt}.txt").write_text(result.text, encoding="utf-8")
        ctx.metrics.append(_metric(turn_no, result))
        try:
            return parse_turn(result.text), assistant_text
        except ProtocolError as e:
            local.append({"role": "assistant", "content": result.text})
            local.append({"role": "user", "content": f"Your output was invalid: {e}. Re-emit ONLY the corrected JSON object."})
    return None, assistant_text


def _execute_actions(turn, retriever: Retriever, ev: EventLog, turn_no: int, query_trail: list[str]) -> dict:
    searches = [a for a in turn.actions if isinstance(a, SearchAction)]
    expands = [a for a in turn.actions if isinstance(a, ExpandAction)]
    graph_ops = [a for a in turn.actions if isinstance(a, GraphAction)]

    results: list[dict] = []
    seen_this_turn: set[str] = set()

    # within-turn fan-out (SPEC section 9): all searches concurrently
    if searches:
        with ThreadPoolExecutor(max_workers=min(8, len(searches))) as pool:
            hits_per_query = list(pool.map(lambda a: retriever.search(a.query, a.k), searches))
        for action, hits in zip(searches, hits_per_query):
            ev.emit("query", {"turn": turn_no, "q": action.query, "k": action.k})
            entry_chunks = []
            for chunk, score in hits:
                ev.emit("chunk", {"turn": turn_no, "cid": chunk.id, "file": chunk.file_path, "score": round(score, 2), "via": "bm25"})
                entry_chunks.append(_chunk_payload(chunk, score))
                seen_this_turn.add(chunk.id)
            results.append({"query": action.query, "chunks": entry_chunks})
            query_trail.append(f'turn {turn_no}: searched "{action.query}" -> {len(entry_chunks)} chunks')

    for action in expands:
        expansion = retriever.expand(action.chunk_ids, hops=action.hops, exclude=seen_this_turn)
        for chunk in expansion.chunks:
            ev.emit("chunk", {"turn": turn_no, "cid": chunk.id, "file": chunk.file_path, "score": 0.0, "via": "graph"})
            seen_this_turn.add(chunk.id)
        results.append({
            "expanded": {
                "subgraph": expansion.subgraph_text,
                "chunks": [_chunk_payload(c, None) for c in expansion.chunks],
            }
        })
        query_trail.append(f"turn {turn_no}: expanded {len(action.chunk_ids)} chunks -> {len(expansion.chunks)} new via graph")

    graph_results = [retriever.graph.apply_delta(a.delta) for a in graph_ops]
    return {"results": results, "graph_results": graph_results}


def _conclude(ctx: RunContext, cfg: Config, llm, messages: list[dict], retriever: Retriever, ev: EventLog, raw_dir: Path):
    final_turn = ctx.turns_completed + 1
    messages.append({"role": "user", "content": prompts.FINAL_INSTRUCTION})
    ev.emit("status", {"turn": final_turn, "state": "reporting"})

    result = llm.chat_stream(
        messages,
        thinking=cfg.think_final,
        on_token=lambda text, kind: ev.emit("token", {"turn": final_turn, "text": text, "kind": kind}),
    )
    (raw_dir / "conclude-attempt-0.txt").write_text(result.text, encoding="utf-8")
    ctx.metrics.append(_metric(final_turn, result))
    known = set(retriever.chunk_store.keys())
    try:
        report, warnings = parse_report(result.text, known)
    except ReportError as e:
        messages.append({"role": "assistant", "content": result.text})
        messages.append({"role": "user", "content": f"Your report was invalid: {e}. Re-emit ONLY the corrected report JSON object."})
        retry = _chat_with_retry(llm, messages, json_format=True)
        (raw_dir / "conclude-attempt-1.txt").write_text(retry.text, encoding="utf-8")
        ctx.metrics.append(_metric(final_turn, retry))
        report, warnings = parse_report(retry.text, known)  # second failure raises ReportError -> run failed
    for w in warnings:
        ev.emit("status", {"turn": final_turn, "state": f"warning: {w}"})
    return report


def _render_full_context(chunk_store: dict[str, Chunk], max_chars: int) -> tuple[str, int, int]:
    """Whole-bundle injection for usb-mode runs: every chunk verbatim, delimited
    by its chunk id so the citation system keeps working. Evidence outranks
    knowledge when the budget forces omissions."""
    ordered = sorted(chunk_store.values(), key=lambda c: (c.kind != "evidence", c.id))
    parts: list[str] = []
    used = 0
    omitted = 0
    for chunk in ordered:
        block = f"----- {chunk.id} -----\n{chunk.text}\n"
        if used + len(block) > max_chars:
            omitted += 1
            continue
        used += len(block)
        parts.append(block)
    if omitted:
        parts.append(f"[{omitted} chunks omitted for length - retrieve them with search/expand]")
    return "".join(parts), len(ordered) - omitted, omitted


# ---------- helpers ----------


def _chat_with_retry(llm, messages: list[dict], **kwargs) -> ChatResult:
    try:
        return llm.chat(messages, **kwargs)
    except LLMError:
        return llm.chat(messages, **kwargs)  # one retry, then propagate


def _chunk_payload(chunk: Chunk, score: float | None) -> dict:
    payload = {"cid": chunk.id, "file": chunk.file_path, "machine": chunk.machine_id, "kind": chunk.kind, "text": chunk.text[:CHUNK_TEXT_CAP]}
    if score is not None:
        payload["score"] = round(score, 2)
    return payload


def _metric(turn: int, result: ChatResult) -> dict:
    return {
        "turn": turn,
        "eval_count": result.eval_count,
        "eval_duration_s": round(result.eval_duration_s, 3),
        "prompt_eval_count": result.prompt_eval_count,
    }


def _metrics_summary(ctx: RunContext) -> dict:
    return {
        "turns": ctx.turns_completed,
        "per_turn": ctx.metrics,
        "tokens_generated": sum(m["eval_count"] for m in ctx.metrics),
        "elapsed_s": round(ctx.elapsed_s, 2),
    }


def _system_digests(chunk_store: dict[str, Chunk]) -> dict[str, str]:
    """First data line of each of the first four command sections of system.txt."""
    digests: dict[str, list[str]] = {}
    for chunk in chunk_store.values():
        if chunk.file_path != "system.txt":
            continue
        lines = chunk.text.splitlines()
        if not lines or not lines[0].startswith("### CMD:"):
            continue
        body = next((ln.strip() for ln in lines[1:] if ln.strip()), "")
        digests.setdefault(chunk.machine_id, [])
        if len(digests[chunk.machine_id]) < 4 and body:
            digests[chunk.machine_id].append(f"{lines[0].removeprefix('### CMD: ').removesuffix(' ###')}: {body}")
    return {m: "; ".join(parts) for m, parts in digests.items()}
