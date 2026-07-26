"""HTTP + SSE endpoints, exactly the contract in API.md."""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..config import Config
from ..events import TERMINAL_EVENTS, read_events
from ..ingest.watcher import list_bundles
from ..runs import RunRegistry

SSE_POLL_S = 0.2


class RunRequest(BaseModel):
    bundle_ids: list[str] | None = None
    question: str = Field(default="Diagnose the collected machines: find the root cause of any failure and propose a fix.")


def create_router(cfg: Config, registry: RunRegistry, llm) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/healthz")
    async def healthz() -> dict:
        ollama = await asyncio.to_thread(llm.ping)
        return {"status": "ok", "ollama": ollama, "model": cfg.model, "version": __version__}

    @router.get("/bundles")
    async def bundles() -> list[dict]:
        return await asyncio.to_thread(list_bundles, cfg, registry.used_bundle_ids())

    @router.post("/runs", status_code=202)
    async def create_run(body: RunRequest) -> dict:
        bundle_ids = body.bundle_ids
        if not bundle_ids:
            used = registry.used_bundle_ids()
            bundle_ids = [b["bundle_id"] for b in list_bundles(cfg) if b["state"] == "ready" and b["bundle_id"] not in used]
        if not bundle_ids:
            raise HTTPException(status_code=400, detail="no ready bundles to run on")
        try:
            ctx = registry.create_run(bundle_ids, body.question)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        registry.launch(ctx)
        return {"run_id": ctx.run_id}

    @router.get("/runs")
    async def runs() -> list[dict]:
        return registry.list_runs()

    @router.get("/runs/{run_id}")
    async def run_detail(run_id: str) -> dict:
        meta = registry.get_meta(run_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="unknown run")
        if meta["status"] == "done":
            report, markdown, metrics = registry.get_report(run_id)
            meta.update({"report": report, "report_markdown": markdown, "metrics": metrics})
        return meta

    @router.get("/runs/{run_id}/stream")
    async def stream(run_id: str, request: Request, from_seq: int = 0) -> StreamingResponse:
        if registry.get_meta(run_id) is None:
            raise HTTPException(status_code=404, detail="unknown run")
        # Last-Event-ID (auto-reconnect) takes precedence over ?from_seq (API.md section 2)
        last_id = request.headers.get("last-event-id")
        after = int(last_id) if last_id and last_id.isdigit() else from_seq

        async def gen():
            sent = after
            while True:
                events = await asyncio.to_thread(read_events, registry.run_dir(run_id) / "events.jsonl", sent)
                terminal = False
                for e in events:
                    sent = e.seq
                    yield f"id: {e.seq}\nevent: {e.event}\ndata: {json.dumps(e.data, ensure_ascii=False)}\n\n"
                    terminal = terminal or e.event in TERMINAL_EVENTS
                if terminal:
                    return
                if not events:
                    meta = registry.get_meta(run_id)
                    if meta and meta["status"] in ("done", "failed"):
                        # drain any tail written between reads, then finish
                        for e in await asyncio.to_thread(read_events, registry.run_dir(run_id) / "events.jsonl", sent):
                            sent = e.seq
                            yield f"id: {e.seq}\nevent: {e.event}\ndata: {json.dumps(e.data, ensure_ascii=False)}\n\n"
                        return
                await asyncio.sleep(SSE_POLL_S)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @router.get("/runs/{run_id}/graph")
    async def graph(run_id: str) -> dict:
        snapshot = registry.get_graph(run_id)
        if snapshot is None:
            meta = registry.get_meta(run_id)
            if meta is None:
                raise HTTPException(status_code=404, detail="unknown run")
            return {"run_id": run_id, "seq": 0, "nodes": [], "edges": []}
        return snapshot

    @router.get("/runs/{run_id}/chunks/{chunk_id:path}")
    async def chunk(run_id: str, chunk_id: str) -> dict:
        rec = registry.get_chunk(run_id, chunk_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="unknown chunk")
        return rec

    return router
