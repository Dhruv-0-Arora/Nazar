"""FastAPI app factory: API routes, watcher lifespan task, static UI mount.

One process, one port (SPEC section 4): the built UI is served from ui/dist
by this same app; the browser only ever talks to :8000.
"""

import asyncio
import contextlib
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..config import Config, load_config
from ..graph.organize import Organizer
from ..ingest.ethernet import ethernet_loop
from ..ingest.watcher import watch_loop
from ..llm import OllamaEmbedder, OllamaLLM
from ..runs import RunRegistry
from .console import create_console_router
from .routes import create_router


def default_ui_dist() -> Path:
    # brain/src/brain/api/server.py -> repo root is four levels up from src/
    override = os.environ.get("BRAIN_UI_DIST")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[4] / "ui" / "dist"


def create_app(cfg: Config | None = None, llm=None, embedder=None) -> FastAPI:
    cfg = cfg or load_config()
    llm = llm or OllamaLLM(cfg.ollama_url, cfg.model, cfg.llm_timeout_s, cfg.num_ctx)
    cfg.ensure_dirs()
    organizer = None
    if cfg.organize:
        embedder = embedder or OllamaEmbedder(cfg.ollama_url, cfg.embed_model, cfg.embed_timeout_s)
        organizer = Organizer(cfg, embedder)
    registry = RunRegistry(cfg, llm, organizer)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks = [asyncio.create_task(watch_loop(cfg, registry), name="inbox-watcher")]
        if cfg.eth_iface and cfg.eth_user:
            tasks.append(asyncio.create_task(ethernet_loop(cfg, registry), name="ethernet-watcher"))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="brain", lifespan=lifespan)
    app.state.cfg = cfg
    app.state.registry = registry
    app.include_router(create_router(cfg, registry, llm))
    app.include_router(create_console_router(cfg, registry))

    ui_dist = default_ui_dist()
    if ui_dist.is_dir():
        app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")
    else:

        @app.get("/")
        async def root() -> dict:
            return {"service": "brain", "note": "UI not built; see ui/README.md", "api": "/api"}

    return app
