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
from ..ingest.watcher import watch_loop
from ..llm import OllamaLLM
from ..runs import RunRegistry
from .routes import create_router


def default_ui_dist() -> Path:
    # brain/src/brain/api/server.py -> repo root is four levels up from src/
    override = os.environ.get("BRAIN_UI_DIST")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[4] / "ui" / "dist"


def create_app(cfg: Config | None = None, llm=None) -> FastAPI:
    cfg = cfg or load_config()
    llm = llm or OllamaLLM(cfg.ollama_url, cfg.model, cfg.llm_timeout_s)
    cfg.ensure_dirs()
    registry = RunRegistry(cfg, llm)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(watch_loop(cfg, registry), name="inbox-watcher")
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="brain", lifespan=lifespan)
    app.state.cfg = cfg
    app.state.registry = registry
    app.include_router(create_router(cfg, registry, llm))

    ui_dist = default_ui_dist()
    if ui_dist.is_dir():
        app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")
    else:

        @app.get("/")
        async def root() -> dict:
            return {"service": "brain", "note": "UI not built; see ui/README.md", "api": "/api"}

    return app
