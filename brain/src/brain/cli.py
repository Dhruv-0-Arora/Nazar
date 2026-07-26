"""Console entry: brain serve | ingest <path> | pull <host...> | graph <run_id>."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .config import load_config
from .ingest.bundle import BundleError, validate_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brain", description="Offline diagnostic Brain")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("serve", help="run the API + UI + inbox watcher")

    p_ingest = sub.add_parser("ingest", help="deposit a bundle (USB mode) atomically into the inbox")
    p_ingest.add_argument("path", type=Path)

    p_pull = sub.add_parser("pull", help="SSH-pull the newest bundle from each client host")
    p_pull.add_argument("hosts", nargs="+")
    p_pull.add_argument("--remote-dir", default="~/bundles", help="collector output dir on the client")

    p_graph = sub.add_parser("graph", help="inspect a run's graph")
    p_graph.add_argument("run_id")
    p_graph.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    cfg = load_config()

    if args.cmd == "serve":
        import uvicorn

        from .api.server import create_app

        uvicorn.run(create_app(cfg), host="0.0.0.0", port=cfg.port, log_level="info")
        return 0

    if args.cmd == "ingest":
        return _ingest(cfg, args.path)

    if args.cmd == "pull":
        rc = 0
        for host in args.hosts:
            rc |= _pull(cfg, host, args.remote_dir)
        return rc

    if args.cmd == "graph":
        from .graph.cli import summarize

        path = cfg.runs / args.run_id / "graph.json"
        if not path.is_file():
            print(f"no graph.json for {args.run_id} under {cfg.runs}", file=sys.stderr)
            return 1
        print(summarize(path, as_json=args.json))
        return 0

    return 2


def _ingest(cfg, src: Path) -> int:
    src = src.expanduser().resolve()
    try:
        validate_bundle(src)
    except BundleError as e:
        print(f"refusing to ingest: {e}", file=sys.stderr)
        return 1
    cfg.ensure_dirs()
    staged = cfg.staging / src.name
    final = cfg.inbox / src.name
    if final.exists():
        print(f"bundle {src.name} already in inbox", file=sys.stderr)
        return 1
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(src, staged)
    staged.rename(final)  # atomic: same filesystem (CONTRACT.md section 5)
    print(f"ingested {src.name}")
    return 0


def _pull(cfg, host: str, remote_dir: str) -> int:
    """scp the newest bundle from the client's output dir (ADR-0003)."""
    find = subprocess.run(
        ["ssh", host, f"ls -1d {remote_dir}/bundle-* 2>/dev/null | sort | tail -1"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    remote_bundle = find.stdout.strip()
    if find.returncode != 0 or not remote_bundle:
        print(f"{host}: no bundles found in {remote_dir}", file=sys.stderr)
        return 1
    name = remote_bundle.rsplit("/", 1)[-1]
    cfg.ensure_dirs()
    staged = cfg.staging / name
    if staged.exists():
        shutil.rmtree(staged)
    # manifest first: it tells the Brain what it is looking at (SPEC section 5)
    manifest_peek = cfg.staging / f"{name}.manifest.json"
    subprocess.run(["scp", "-q", f"{host}:{remote_bundle}/manifest.json", str(manifest_peek)], check=False, timeout=30)
    if manifest_peek.is_file():
        print(f"{host}: manifest fetched ({manifest_peek.stat().st_size} bytes), pulling full bundle")
        manifest_peek.unlink()
    copy = subprocess.run(["scp", "-rq", f"{host}:{remote_bundle}", str(cfg.staging)], timeout=300)
    if copy.returncode != 0:
        print(f"{host}: scp failed", file=sys.stderr)
        return 1
    final = cfg.inbox / name
    if final.exists():
        print(f"{host}: bundle {name} already in inbox", file=sys.stderr)
        return 1
    staged.rename(final)
    print(f"pulled {name} from {host}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
