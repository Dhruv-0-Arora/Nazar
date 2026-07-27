"""Run registry: run_id allocation, meta.json lifecycle, live-run state, and
the case-level concurrency semaphore (SPEC sections 5, 9, 10)."""

import asyncio
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .agent.loop import RunContext, execute_run
from .config import Config
from .ingest.usb import is_usb_bundle


class RunRegistry:
    def __init__(self, cfg: Config, llm, organizer=None):
        self.cfg = cfg
        self.llm = llm
        self.organizer = organizer
        self._live: dict[str, RunContext] = {}
        self._sem = asyncio.Semaphore(max(1, cfg.parallel))
        # bumped by reset(); the watcher re-seeds its memory when it changes,
        # so a re-plugged stick auto-ingests and auto-diagnoses again
        self.epoch = 0

    # ---------- lifecycle ----------

    def create_run(self, bundle_ids: list[str], question: str, full_context: bool | None = None) -> RunContext:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"run-{ts}-{uuid.uuid4().hex[:4]}"
        run_dir = self.cfg.runs / run_id
        (run_dir / "bundles").mkdir(parents=True)
        try:
            for bid in bundle_ids:
                src = self.cfg.inbox / bid
                if not src.is_dir():
                    raise FileNotFoundError(f"bundle {bid} not found in inbox")
                shutil.copytree(src, run_dir / "bundles" / bid)
        except Exception:
            # never leave a half-copied run dir behind: it has no meta.json,
            # is invisible to the API, and silently poisons later debugging
            shutil.rmtree(run_dir, ignore_errors=True)
            raise
        if full_context is None:
            # FDE-on-site default: usb-received bundles get whole-bundle injection (ADR-0012)
            full_context = any(is_usb_bundle(self.cfg.inbox / bid) for bid in bundle_ids)
        ctx = RunContext(run_id=run_id, dir=run_dir, bundle_ids=list(bundle_ids), question=question, full_context=full_context)
        ctx.save_meta()
        self._live[run_id] = ctx
        return ctx

    async def start(self, ctx: RunContext) -> None:
        async with self._sem:
            await asyncio.to_thread(execute_run, ctx, self.cfg, self.llm, self.organizer)

    def launch(self, ctx: RunContext) -> asyncio.Task:
        return asyncio.create_task(self.start(ctx), name=f"run:{ctx.run_id}")

    def reset(self, bundles: bool = True, runs: bool = True) -> dict:
        """Demo reset: clear inbox bundles, rejected leftovers, staging, and
        finished runs. Runs that are queued/running are protected, not killed."""
        removed_bundles: list[str] = []
        removed_runs: list[str] = []
        protected: list[str] = []

        if runs:
            for run_id, ctx in list(self._live.items()):
                if ctx.status in ("queued", "running"):
                    protected.append(run_id)
                else:
                    self._live.pop(run_id, None)
            for d in self.cfg.runs.glob("run-*"):
                if d.name in protected or not d.is_dir():
                    continue
                shutil.rmtree(d, ignore_errors=True)
                removed_runs.append(d.name)

        if bundles:
            active = {bid for rid in protected for bid in self._live[rid].bundle_ids}
            for d in self.cfg.inbox.glob("bundle-*"):
                if d.is_dir() and d.name not in active:
                    shutil.rmtree(d, ignore_errors=True)
                    removed_bundles.append(d.name)
            for p in self.cfg.rejected.glob("bundle-*"):
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
            for p in self.cfg.staging.iterdir() if self.cfg.staging.is_dir() else []:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)

        self.epoch += 1
        return {
            "removed_bundles": sorted(removed_bundles),
            "removed_runs": sorted(removed_runs),
            "protected_running": sorted(protected),
        }

    # ---------- queries ----------

    def live(self, run_id: str) -> RunContext | None:
        ctx = self._live.get(run_id)
        return ctx if ctx and ctx.status in ("queued", "running") else None

    def get_meta(self, run_id: str) -> dict | None:
        ctx = self._live.get(run_id)
        if ctx:
            return ctx.meta()
        meta_path = self.cfg.runs / run_id / "meta.json"
        if meta_path.is_file():
            return json.loads(meta_path.read_text(encoding="utf-8"))
        return None

    def list_runs(self) -> list[dict]:
        metas: dict[str, dict] = {}
        for meta_path in self.cfg.runs.glob("run-*/meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                metas[meta["run_id"]] = meta
            except (json.JSONDecodeError, KeyError):
                continue
        for run_id, ctx in self._live.items():
            metas[run_id] = ctx.meta()
        return sorted(metas.values(), key=lambda m: m.get("started_at") or m["run_id"], reverse=True)

    def used_bundle_ids(self) -> set[str]:
        used: set[str] = set()
        for meta in self.list_runs():
            used.update(meta.get("bundle_ids", []))
        return used

    def run_dir(self, run_id: str) -> Path:
        return self.cfg.runs / run_id

    def get_report(self, run_id: str) -> tuple[dict | None, str | None, dict | None]:
        d = self.run_dir(run_id)
        report = _read_json(d / "report.json")
        markdown = (d / "report.md").read_text(encoding="utf-8") if (d / "report.md").is_file() else None
        metrics = _read_json(d / "metrics.json")
        return report, markdown, metrics

    def get_organization(self, run_id: str) -> dict | None:
        ctx = self._live.get(run_id)
        if ctx and ctx.organization is not None:
            return ctx.organization
        return _read_json(self.run_dir(run_id) / "organization.json")

    def get_chunk(self, run_id: str, chunk_id: str) -> dict | None:
        ctx = self._live.get(run_id)
        if ctx and ctx.chunk_store is not None:
            chunk = ctx.chunk_store.get(chunk_id)
            return chunk.to_dict() if chunk else None
        chunks_path = self.run_dir(run_id) / "chunks.jsonl"
        if not chunks_path.is_file():
            return None
        with open(chunks_path, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                if rec.get("chunk_id") == chunk_id:
                    return rec
        return None

    def get_graph(self, run_id: str) -> dict | None:
        # live snapshot whenever a graph exists in memory (queued-after-ingest,
        # running, or a finished ctx whose graph.json write raced/failed)
        ctx = self._live.get(run_id)
        on_disk = _read_json(self.run_dir(run_id) / "graph.json")
        if on_disk is not None:
            return on_disk
        if ctx and ctx.graph is not None:
            snapshot = ctx.graph.snapshot()
            snapshot.update({"run_id": run_id, "seq": ctx.events.seq if ctx.events else 0})
            return snapshot
        return None


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
