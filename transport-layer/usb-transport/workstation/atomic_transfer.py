#!/usr/bin/env python3
"""atomic_transfer.py — USB -> Brain inbox -> index -> test query, one command.

The workstation end of USB mode (ADR-0003, ADR-0012, CONTRACT.md section 5).
Run it after plugging in the stick.

Deposits go THROUGH the Brain's own USB intake (brain.ingest.usb), which
verifies the bundle with the transport receiver, normalizes any bundle
dialect to CONTRACT v1.0 (lowercase machine_id, contract manifest, required
files), validates, and renames atomically into the inbox. In order:

1. POST /api/usb/receive on a running `brain serve` (preferred - the server
   normalizes, validates, deposits, and its watcher launches the diagnosis),
2. a direct call into brain.ingest.usb.receive() when no server is up,
3. NEVER a raw copy. If neither path is available this script fails loudly
   instead of depositing bundles the watcher would reject (that was the old
   failure mode: raw transport-dialect bundles landing in rejected/).

After the deposit it indexes the received bundles the way a Brain run does
(deterministic chunker -> BM25 -> evidence graph) and runs a test query so
you can eyeball retrieval quality immediately. The preview needs the brain
package plus rank_bm25/networkx - run with <repo>/brain/.venv/bin/python for
that part; the deposit itself works with any python3.

Usage:
    python atomic_transfer.py [source] [--inbox DIR] [--brain-url URL]
                              [--query TEXT] [-k N] [--hops N]
                              [--no-index] [--verify-only]

    [source]  bundle dir or dir of bundle-* dirs
              (default: ../client/outbox on this same stick)
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # receive_bundle.py ships next to this script

from receive_bundle import discover_bundles, verify_bundle  # noqa: E402

TS_RE = re.compile(r"(\d{8}T\d{6}Z)$")


def normalized_name(bundle_name: str) -> str:
    """Mirror of brain.ingest.usb.normalized_name, kept local so the API path
    works without the brain package importable."""
    m = TS_RE.search(bundle_name)
    ts = m.group(1) if m else "00000000T000000Z"
    middle = TS_RE.sub("", bundle_name.removeprefix("bundle-")).rstrip("-")
    middle = re.sub(r"[^a-z0-9-]", "-", middle.lower()).strip("-") or "unknown"
    return f"bundle-{middle}-{ts}"


# --------------------------------------------------------------- brain import

def _add_brain_paths() -> None:
    candidates = []
    if os.environ.get("BRAIN_SRC"):
        candidates.append(Path(os.environ["BRAIN_SRC"]).expanduser())
    # repo checkout: <repo>/transport-layer/usb-transport/workstation/
    if len(HERE.parents) > 2:  # on a stick, HERE may sit right under the drive root
        candidates.append(HERE.parents[2] / "brain" / "src")
    # common workstation checkout locations (stick runs outside the repo)
    for repo in ("Documents/whackathon", "whackathon", "Nazar/whackathon"):
        candidates.append(Path.home() / repo / "brain" / "src")
    for c in candidates:
        if (c / "brain" / "__init__.py").is_file() and str(c) not in sys.path:
            sys.path.insert(0, str(c))


def import_brain_core():
    """brain.config + brain.ingest.usb - stdlib-only, needed for direct deposit."""
    _add_brain_paths()
    try:
        from brain.config import load_config
        from brain.ingest import usb
    except ImportError:
        return None
    return {"load_config": load_config, "usb": usb}


def import_brain_indexing():
    """The retrieval stack - needs rank_bm25 + networkx."""
    _add_brain_paths()
    try:
        from brain.graph.build import build_graph
        from brain.graph.store import GraphStore
        from brain.index.bm25 import Bm25Index
        from brain.ingest.bundle import load_manifest
        from brain.ingest.chunker import chunk_bundle
        from brain.retrieval import Retriever
    except ImportError as e:
        print(f"NOTE: indexing preview unavailable ({e}).")
        print("      Run with <repo>/brain/.venv/bin/python (or pip install rank_bm25 networkx")
        print("      and set BRAIN_SRC=<repo>/brain/src) to get the BM25/graph preview.")
        return None
    return {
        "build_graph": build_graph, "GraphStore": GraphStore, "Bm25Index": Bm25Index,
        "load_manifest": load_manifest, "chunk_bundle": chunk_bundle, "Retriever": Retriever,
    }


# --------------------------------------------------------------- deposit paths

def deposit_via_api(outbox: Path, brain_url: str) -> dict | None:
    """POST /api/usb/receive. Returns the result dict, or None if no server."""
    req = urllib.request.Request(
        brain_url.rstrip("/") + "/api/usb/receive",
        data=json.dumps({"source": str(outbox)}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=330) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode()).get("detail", str(e))
        except Exception:  # noqa: BLE001
            detail = str(e)
        return {"received": [], "skipped": [], "errors": [f"brain API: {detail}"], "summary": ""}
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None  # no server - caller falls back to the direct path


def deposit_direct(outbox: Path, core, inbox_override: str | None) -> tuple[dict, Path]:
    """Call brain.ingest.usb.receive() in-process (no server needed).
    Returns (result, actual inbox path)."""
    if inbox_override:
        p = Path(inbox_override).expanduser().resolve()
        # brain derives inbox as $BRAIN_HOME/inbox; honor that layout
        home = p.parent if p.name == "inbox" else p
        os.environ["BRAIN_HOME"] = str(home)
        if p.name != "inbox":
            print(f"NOTE: brain uses <home>/inbox - depositing under {home / 'inbox'}")
    cfg = core["load_config"]()
    return core["usb"].receive(outbox, cfg), cfg.inbox


# ------------------------------------------------------------------- indexing

def index_and_query(idx, bundle_dirs: list[Path], query: str, k: int, hops: int) -> None:
    print()
    print("=" * 62)
    print(" INDEXING (deterministic chunker -> BM25 + evidence graph)")
    print("=" * 62)

    chunks, manifests = [], []
    for d in bundle_dirs:
        try:
            m = idx["load_manifest"](d)
        except Exception as e:  # noqa: BLE001
            print(f"  skipping {d.name}: {e}")
            continue
        manifests.append(m)
        bundle_chunks = idx["chunk_bundle"](d, m)
        chunks.extend(bundle_chunks)
        print(f"  {d.name}: {len(bundle_chunks)} chunks (machine {m.machine_id})")
    if not chunks:
        print("  no ingestible chunks - nothing to index")
        return

    index = idx["Bm25Index"](chunks)
    graph = idx["GraphStore"]()
    idx["build_graph"](chunks, manifests, graph)
    retriever = idx["Retriever"]({c.id: c for c in chunks}, index, graph)

    by_type: dict[str, int] = {}
    for n in graph.nodes.values():
        by_type[n.type] = by_type.get(n.type, 0) + 1
    print(f"  index : {len(chunks)} chunks from {len(manifests)} bundle(s)")
    print(f"  graph : {len(graph.nodes)} nodes ({', '.join(f'{t}={c}' for t, c in sorted(by_type.items()))}), "
          f"{len(graph.edges)} edges")

    print()
    print("=" * 62)
    print(f" TEST QUERY (BM25 top-{k}): {query!r}")
    print("=" * 62)
    hits = retriever.search(query, k=k)
    if not hits:
        print("  no hits with positive score - try --query with terms from the logs")
        return
    for chunk, score in hits:
        first_line = next((ln.strip() for ln in chunk.text.splitlines() if ln.strip()), "")
        print(f"  {score:7.2f}  {chunk.id}")
        print(f"           {first_line[:96]}")

    print()
    print("=" * 62)
    print(f" GRAPH EXPANSION (top hits, {hops} hop(s))")
    print("=" * 62)
    exp = retriever.expand([c.id for c, _ in hits[:3]], hops=hops)
    for line in exp.subgraph_text.splitlines():
        print(f"  {line}")
    if exp.chunks:
        print()
        print(f"  {len(exp.chunks)} additional chunk(s) reachable only via the graph:")
        for c in exp.chunks[:10]:
            print(f"    {c.id}")


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", nargs="?", default=None,
                    help="bundle dir or dir of bundle-* dirs "
                         "(default: ../client/outbox on this stick)")
    ap.add_argument("--inbox", default=None,
                    help="Brain inbox (default: $BRAIN_HOME/inbox or ~/brain/inbox; "
                         "only used for the direct path and the preview)")
    ap.add_argument("--brain-url", default=os.environ.get("BRAIN_URL", "http://127.0.0.1:8000"),
                    help="running brain serve to deposit through (default: %(default)s)")
    ap.add_argument("--query", default="error connection refused timeout failed",
                    help="test query to run against BM25 after the deposit")
    ap.add_argument("-k", type=int, default=5, help="top-k BM25 hits (default 5)")
    ap.add_argument("--hops", type=int, default=1, help="graph expansion hops (default 1)")
    ap.add_argument("--no-index", action="store_true", help="deposit only, skip the preview")
    ap.add_argument("--verify-only", action="store_true",
                    help="transport-verify the stick bundles, no deposit")
    args = ap.parse_args()

    source = Path(args.source).resolve() if args.source else (HERE.parent / "client" / "outbox")
    if args.source is None:
        print(f"No source given - using the outbox on this stick: {source}")
    if not source.is_dir():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        sys.exit(2)

    inbox = Path(args.inbox).expanduser() if args.inbox else (
        Path(os.environ.get("BRAIN_HOME", "~/brain")).expanduser() / "inbox")

    bundles = discover_bundles(source)
    if not bundles:
        print(f"ERROR: no bundle-*/manifest.json found under {source}", file=sys.stderr)
        sys.exit(2)
    print(f"Found {len(bundles)} bundle(s) at {source}")

    if args.verify_only:
        failed = 0
        for b in bundles:
            manifest, errors, _extras = verify_bundle(b)
            status = "OK" if manifest and not errors else "FAILED"
            print(f"  {b.name}: transport verify {status}")
            for e in errors or []:
                print(f"    - {e}")
            failed += bool(errors or manifest is None)
        sys.exit(1 if failed else 0)

    # ---- deposit through the Brain's USB intake (never a raw copy) ----------
    outbox = source if source.name == "outbox" or not (source / "manifest.json").is_file() else source.parent

    result = deposit_via_api(outbox, args.brain_url)
    via = f"brain serve at {args.brain_url}"
    if result is None:
        core = import_brain_core()
        if core is None:
            print()
            print("ERROR: no deposit path available.", file=sys.stderr)
            print(f"  - no brain serve reachable at {args.brain_url}", file=sys.stderr)
            print("  - brain package not importable for a direct deposit", file=sys.stderr)
            print("    (set BRAIN_SRC=<repo>/brain/src or run <repo>/brain/.venv/bin/python)", file=sys.stderr)
            print("Refusing to raw-copy: unnormalized bundles would be rejected by the watcher.", file=sys.stderr)
            sys.exit(2)
        via = "brain.ingest.usb (direct, no server)"
        result, inbox = deposit_direct(outbox, core, args.inbox)

    print()
    print("=" * 62)
    print(f" DEPOSIT via {via}")
    print("=" * 62)
    for name in result.get("received", []):
        print(f"  received : {name}")
    for name in result.get("skipped", []):
        print(f"  skipped  : {name} (already received earlier)")
    for err in result.get("errors", []):
        print(f"  ERROR    : {err}")
    if not result.get("received") and not result.get("skipped"):
        print("  nothing received.")

    # ---- preview: index what is now in the inbox ----------------------------
    wanted = {normalized_name(n) for n in
              list(result.get("received", [])) + list(result.get("skipped", []))}
    inbox_dirs = [inbox / n for n in sorted(wanted) if (inbox / n).is_dir()]

    if inbox_dirs and not args.no_index:
        idx = import_brain_indexing()
        if idx:
            index_and_query(idx, inbox_dirs, args.query, args.k, args.hops)
    elif not inbox_dirs and wanted:
        print(f"\nNOTE: deposited bundles not visible under {inbox} from here; preview skipped.")

    print()
    if result.get("received"):
        print(f"Done: {len(result['received'])} bundle(s) normalized into the inbox.")
        print("If `brain serve` is running with autorun, the watcher launches the")
        print("diagnosis within its debounce window (USB runs get full context).")
    sys.exit(1 if result.get("errors") else 0)


if __name__ == "__main__":
    main()
