"""Inbox watcher: polling, validation/rejection, and case grouping (ADR-0006).

A case is every valid new bundle that lands inside one debounce window. The
watcher never sees transports, only atomically-renamed directories at the
inbox root (CONTRACT.md section 5).
"""

import asyncio
import shutil
import time

from ..config import Config
from ..runs import RunRegistry
from . import usb
from .bundle import BundleError, load_manifest, validate_bundle


def list_bundles(cfg: Config, used: set[str] | None = None) -> list[dict]:
    """State of every bundle the inbox knows, for GET /api/bundles."""
    used = used or set()
    out = []
    for d in sorted(cfg.inbox.glob("bundle-*")):
        if not d.is_dir():
            continue
        try:
            m = validate_bundle(d)
            out.append({
                "bundle_id": d.name,
                "machine_id": m.machine_id,
                "created_at": m.created_at,
                "services": list(m.services),
                "state": "ready",
                "in_run": d.name in used,
            })
        except BundleError as e:
            out.append({"bundle_id": d.name, "machine_id": None, "created_at": None, "services": None, "state": "rejected", "reason": str(e)})
    for d in sorted(cfg.rejected.glob("bundle-*")):
        if not d.is_dir():
            continue  # the .reject-reason.txt sidecars match the glob too
        reason_file = d.parent / f"{d.name}.reject-reason.txt"
        reason = reason_file.read_text(encoding="utf-8").strip() if reason_file.is_file() else "unknown"
        entry = {"bundle_id": d.name, "machine_id": None, "created_at": None, "services": None, "state": "rejected", "reason": reason}
        try:
            m = load_manifest(d)
            entry.update({"machine_id": m.machine_id, "created_at": m.created_at, "services": list(m.services)})
        except BundleError:
            pass
        out.append(entry)
    return out


async def watch_loop(cfg: Config, registry: RunRegistry) -> None:
    known: set[str] = set()
    pending: list[str] = []
    last_new = 0.0

    # bundles already consumed by a previous session must not auto-rerun,
    # but stay 'ready' for manual triggers (idempotent restart, SPEC 11)
    known |= registry.used_bundle_ids()

    while True:
        try:
            # usb auto-intake: a plugged-in client stick with unreceived bundles
            # gets received + normalized, then flows through the normal scan below
            if cfg.usb_watch:
                for src in usb.candidate_sources(cfg):
                    if usb.pending_bundles(src, cfg):
                        usb.receive(src, cfg)

            for d in sorted(cfg.inbox.glob("bundle-*")):
                if not d.is_dir() or d.name in known:
                    continue
                known.add(d.name)
                try:
                    validate_bundle(d)
                except BundleError as e:
                    _reject(cfg, d.name, str(e))
                    continue
                pending.append(d.name)
                last_new = time.monotonic()

            if cfg.autorun and pending and (time.monotonic() - last_new) >= cfg.debounce_s:
                batch, pending = pending, []
                ctx = registry.create_run(batch, question="Diagnose the collected machines: find the root cause of any failure and propose a fix.")
                registry.launch(ctx)
        except Exception:  # noqa: BLE001 - the watcher must survive anything
            pass
        await asyncio.sleep(cfg.poll_interval_s)


def _reject(cfg: Config, bundle_name: str, reason: str) -> None:
    src = cfg.inbox / bundle_name
    dst = cfg.rejected / bundle_name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.move(str(src), str(dst))
    (cfg.rejected / f"{bundle_name}.reject-reason.txt").write_text(reason + "\n", encoding="utf-8")
