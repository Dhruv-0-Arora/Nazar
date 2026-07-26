"""USB transport intake (ADR-0012).

Wraps the teammate's transport-layer receiver (receive_bundle.py) instead of
reimplementing it: the receiver verifies sha256/sizes and copies bundles off
the stick; this module discovers client outboxes, runs the receiver into
staging, normalizes each verified bundle to CONTRACT v1.0, and deposits it
atomically. USB-received bundles carry a receipt.json with transport "usb",
which is what flips a run into full-context mode (loop.py).
"""

import glob as globmod
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import Config
from .bundle import BUNDLE_NAME_RE, REQUIRED_FILES, BundleError, validate_bundle

REPO_RECEIVER = Path(__file__).resolve().parents[4] / "transport-layer" / "usb-transport" / "workstation" / "receive_bundle.py"
TS_RE = re.compile(r"(\d{8}T\d{6}Z)$")
USB_MOUNT_GLOBS = (
    "/media/*/*/usb-transport/client/outbox",
    "/media/*/usb-transport/client/outbox",
    "/run/media/*/*/usb-transport/client/outbox",
)


def sanitize_id(value: str) -> str:
    out = re.sub(r"[^a-z0-9-]", "-", value.lower()).strip("-")
    return out or "unknown"


def normalized_name(bundle_name: str) -> str:
    m = TS_RE.search(bundle_name)
    ts = m.group(1) if m else "00000000T000000Z"
    middle = bundle_name.removeprefix("bundle-")
    middle = TS_RE.sub("", middle).rstrip("-")
    return f"bundle-{sanitize_id(middle)}-{ts}"


def candidate_sources(cfg: Config) -> list[Path]:
    """Every plausible client outbox: configured paths, mounted sticks, repo copy."""
    found: list[Path] = []
    for raw in cfg.usb_sources:
        p = _resolve_outbox(Path(raw).expanduser())
        if p and p.is_dir():
            found.append(p)
    for pattern in USB_MOUNT_GLOBS:
        for hit in globmod.glob(pattern):
            found.append(Path(hit))
    repo_outbox = REPO_RECEIVER.parent.parent / "client" / "outbox"
    if repo_outbox.is_dir():
        found.append(repo_outbox)
    seen: set[Path] = set()
    return [p for p in found if not (p in seen or seen.add(p))]


def pending_bundles(outbox: Path, cfg: Config) -> list[Path]:
    """Bundles on the stick whose normalized name is not already known to the inbox."""
    known = {d.name for d in cfg.inbox.glob("bundle-*")} | {d.name for d in cfg.rejected.glob("bundle-*")}
    return [
        d for d in sorted(outbox.glob("bundle-*"))
        if d.is_dir() and (d / "manifest.json").is_file() and normalized_name(d.name) not in known
    ]


def receive(source: Path | str | None, cfg: Config) -> dict:
    """Run the transport receiver against a client folder/outbox and deposit
    normalized bundles into the inbox. Returns {received, skipped, errors, summary}."""
    result: dict = {"received": [], "skipped": [], "errors": [], "summary": ""}

    outbox = _resolve_outbox(Path(source).expanduser().resolve()) if source else _first_pending_source(cfg)
    if outbox is None or not outbox.is_dir():
        result["errors"].append(f"no client outbox found{f' at {source}' if source else ''}")
        return result

    pend = pending_bundles(outbox, cfg)
    already = [d.name for d in sorted(outbox.glob("bundle-*")) if d.is_dir() and d not in pend]
    result["skipped"] = already
    if not pend:
        result["summary"] = f"nothing new at {outbox} ({len(already)} bundle(s) already received)"
        return result

    receiver = _receiver_for(outbox)
    if receiver is None:
        result["errors"].append("receive_bundle.py not found (stick, BRAIN_RECEIVER, or repo copy)")
        return result

    cfg.ensure_dirs()
    stage_root = cfg.staging / "usb"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True)

    proc = subprocess.run(
        [sys.executable, str(receiver), str(outbox), "--inbox", str(stage_root), "--transport", "usb"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    result["summary"] = proc.stdout
    if proc.returncode not in (0, 1) and proc.stderr.strip():
        result["errors"].append(proc.stderr.strip())

    for staged in sorted(stage_root.glob("bundle-*")):
        receipt = _read_json(staged / "receipt.json") or {}
        if receipt and not receipt.get("verified", True):
            _reject(cfg, staged, "usb receiver verification failed: " + "; ".join(receipt.get("errors", [])))
            result["errors"].append(f"{staged.name}: verification failed")
            continue
        try:
            final_name = _normalize_and_deposit(staged, cfg)
            result["received"].append(final_name)
        except BundleError as e:
            _reject(cfg, staged, str(e))
            result["errors"].append(f"{staged.name}: {e}")
    return result


def is_usb_bundle(bundle_dir: Path) -> bool:
    receipt = _read_json(bundle_dir / "receipt.json")
    return bool(receipt) and receipt.get("transport") == "usb"


# ---------- internals ----------


def _first_pending_source(cfg: Config) -> Path | None:
    for src in candidate_sources(cfg):
        if pending_bundles(src, cfg):
            return src
    sources = candidate_sources(cfg)
    return sources[0] if sources else None


def _resolve_outbox(source: Path) -> Path | None:
    """Accept the outbox itself, the client folder, the usb-transport root, or
    the stick root, and find the outbox inside."""
    for candidate in (
        source,
        source / "outbox",
        source / "client" / "outbox",
        source / "usb-transport" / "client" / "outbox",
        source / "transport-layer" / "usb-transport" / "client" / "outbox",
    ):
        if candidate.is_dir() and (candidate.name == "outbox" or any(candidate.glob("bundle-*"))):
            return candidate
    return source if source.is_dir() else None


def _receiver_for(outbox: Path) -> Path | None:
    stick_receiver = outbox.parent.parent / "workstation" / "receive_bundle.py"
    if stick_receiver.is_file():
        return stick_receiver  # prefer the stick's own copy: it matches its bundles
    import os

    override = os.environ.get("BRAIN_RECEIVER")
    if override and Path(override).is_file():
        return Path(override)
    if REPO_RECEIVER.is_file():
        return REPO_RECEIVER
    return None


def _normalize_and_deposit(staged: Path, cfg: Config) -> str:
    """Bring a receiver-verified bundle up to CONTRACT v1.0, then atomically
    rename into the inbox. Raises BundleError if it cannot conform."""
    raw = _read_json(staged / "manifest.json")
    if raw is None:
        raise BundleError("manifest.json unreadable")

    final_name = normalized_name(staged.name)
    if "machine_id" not in raw or not BUNDLE_NAME_RE.match(staged.name):
        hostname = str(raw.get("hostname") or final_name.split("-")[1])
        machine_id = sanitize_id(hostname)
        targets = raw.get("targets", {}) or {}
        notes_bits = [str(raw.get("notes") or "").strip(), "received via usb transport"]
        if targets.get("problem_dirs"):
            notes_bits.append("problem dirs: " + ", ".join(targets["problem_dirs"]))
        shutil.copyfile(staged / "manifest.json", staged / "manifest.usb.json")
        contract_manifest = {
            "contract_version": "1.0",
            "bundle_id": final_name,
            "machine_id": machine_id,
            "hostname": hostname,
            "created_at": raw.get("created_at") or raw.get("created_at_utc") or "",
            "os": raw.get("os", ""),
            "kernel": raw.get("kernel", ""),
            "collector_version": str(raw.get("collector_version", "")),
            "services": list(targets.get("services") or raw.get("services") or []),
            "files": [
                {"path": e.get("path"), "bytes": e.get("bytes"), "truncated": bool(e.get("truncated", False))}
                for e in raw.get("files", [])
                if e.get("path")
            ],
            "notes": "; ".join(b for b in notes_bits if b),
        }
        (staged / "manifest.json").write_text(json.dumps(contract_manifest, indent=2) + "\n", encoding="utf-8")
        for req in REQUIRED_FILES:
            if not (staged / req).is_file():
                (staged / req).write_text("unavailable: not captured by usb collector\n", encoding="utf-8")

    if staged.name != final_name:
        staged = staged.rename(staged.parent / final_name)
    validate_bundle(staged)  # raises BundleError with the reject reason

    final = cfg.inbox / final_name
    if final.exists():
        raise BundleError(f"bundle {final_name} already in inbox")
    staged.rename(final)  # atomic: staging lives inside the inbox filesystem
    return final_name


def _reject(cfg: Config, staged: Path, reason: str) -> None:
    dst = cfg.rejected / staged.name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.move(str(staged), str(dst))
    (cfg.rejected / f"{staged.name}.reject-reason.txt").write_text(reason + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
