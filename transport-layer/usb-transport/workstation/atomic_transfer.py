#!/usr/bin/env python3
"""atomic_transfer.py — USB -> Brain inbox -> index -> test query, one command.

The workstation end of USB mode (ADR-0003, CONTRACT.md section 5). Run it
after plugging in the stick:

1. discovers bundle-* dirs at the source (default: the client outbox that
   ships on this same stick),
2. verifies each against its manifest (sha256/bytes, receive_bundle.py) and
   against the Brain's own contract validator (brain.ingest.bundle),
3. deposits atomically: copy into $BRAIN_INBOX/.staging/, then rename into
   the inbox root - the watcher can never see a half-copied bundle,
4. indexes the deposited bundles exactly the way a Brain run does
   (deterministic chunker -> BM25 inverted index -> evidence graph),
5. runs a test query against BM25 and expands the top hits through the
   graph, printing both so you can eyeball retrieval quality immediately.

If `brain serve` is running with autorun enabled, the inbox watcher will ALSO
pick the deposit up on its own and launch a full agent diagnosis; this script
does not interfere with that (same deposit protocol, no extra files written
into the bundle).

Usage:
    python atomic_transfer.py [source] [--inbox DIR] [--query TEXT] [-k N]
                              [--hops N] [--force] [--no-index] [--verify-only]

The indexing step needs the brain package's deps (rank_bm25, networkx). The
script finds the brain sources automatically when it runs from the repo
checkout, or via $BRAIN_SRC when the stick is standalone.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # receive_bundle.py ships next to this script

from receive_bundle import discover_bundles, verify_bundle  # noqa: E402


# --------------------------------------------------------------- brain import

def import_brain():
    """Make the brain package importable; return the modules we need or None."""
    candidates = []
    if os.environ.get("BRAIN_SRC"):
        candidates.append(Path(os.environ["BRAIN_SRC"]).expanduser())
    # repo checkout: <repo>/transport-layer/usb-transport/workstation/
    candidates.append(HERE.parents[2] / "brain" / "src")
    for c in candidates:
        if (c / "brain" / "__init__.py").is_file() and str(c) not in sys.path:
            sys.path.insert(0, str(c))
    try:
        from brain.graph.build import build_graph
        from brain.graph.store import GraphStore
        from brain.index.bm25 import Bm25Index
        from brain.ingest.bundle import BundleError, load_manifest, validate_bundle
        from brain.ingest.chunker import chunk_bundle
        from brain.retrieval import Retriever
    except ImportError as e:
        print(f"NOTE: brain package not importable ({e}).")
        print("      Deposit still works; indexing/test query will be skipped.")
        print("      Fix: pip install rank_bm25 networkx, and/or set BRAIN_SRC=<repo>/brain/src")
        return None
    return {
        "build_graph": build_graph, "GraphStore": GraphStore, "Bm25Index": Bm25Index,
        "BundleError": BundleError, "load_manifest": load_manifest,
        "validate_bundle": validate_bundle, "chunk_bundle": chunk_bundle,
        "Retriever": Retriever,
    }


# -------------------------------------------------------------------- deposit

def deposit_atomic(bundle_dir: Path, inbox: Path, force: bool) -> Path | None:
    """CONTRACT.md section 5: copy to .staging/, then atomic rename into inbox."""
    dest = inbox / bundle_dir.name
    if dest.exists():
        if not force:
            print(f"    already in inbox (use --force to re-copy): {dest}")
            return dest
        shutil.rmtree(dest)
    staging = inbox / ".staging" / bundle_dir.name
    if staging.exists():
        shutil.rmtree(staging)
    staging.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle_dir, staging)
    staging.rename(dest)  # atomic: same filesystem
    print(f"    deposited atomically -> {dest}")
    return dest


# ------------------------------------------------------------------- indexing

def index_and_query(brain, bundle_dirs: list[Path], query: str, k: int, hops: int) -> bool:
    print()
    print("=" * 62)
    print(" INDEXING (deterministic chunker -> BM25 + evidence graph)")
    print("=" * 62)

    chunks, manifests = [], []
    for d in bundle_dirs:
        m = brain["load_manifest"](d)
        manifests.append(m)
        bundle_chunks = brain["chunk_bundle"](d, m)
        chunks.extend(bundle_chunks)
        print(f"  {d.name}: {len(bundle_chunks)} chunks (machine {m.machine_id})")
    if not chunks:
        print("  no ingestible chunks - nothing to index")
        return False

    index = brain["Bm25Index"](chunks)
    graph = brain["GraphStore"]()
    brain["build_graph"](chunks, manifests, graph)
    chunk_store = {c.id: c for c in chunks}
    retriever = brain["Retriever"](chunk_store, index, graph)

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
        return True
    for chunk, score in hits:
        first_line = next((ln.strip() for ln in chunk.text.splitlines() if ln.strip()), "")
        print(f"  {score:7.2f}  {chunk.id}")
        print(f"           {first_line[:96]}")

    print()
    print("=" * 62)
    print(f" GRAPH EXPANSION (top hits, {hops} hop(s))")
    print("=" * 62)
    seed_ids = [c.id for c, _ in hits[:3]]
    exp = retriever.expand(seed_ids, hops=hops)
    for line in exp.subgraph_text.splitlines():
        print(f"  {line}")
    if exp.chunks:
        print()
        print(f"  {len(exp.chunks)} additional chunk(s) reachable only via the graph:")
        for c in exp.chunks[:10]:
            print(f"    {c.id}")
    return True


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", nargs="?", default=None,
                    help="bundle dir or dir of bundle-* dirs "
                         "(default: ../client/outbox on this stick)")
    ap.add_argument("--inbox", default=None,
                    help="Brain inbox (default: $BRAIN_HOME/inbox or ~/brain/inbox)")
    ap.add_argument("--query", default="error connection refused timeout failed",
                    help="test query to run against BM25 after indexing")
    ap.add_argument("-k", type=int, default=5, help="top-k BM25 hits (default 5)")
    ap.add_argument("--hops", type=int, default=1, help="graph expansion hops (default 1)")
    ap.add_argument("--force", action="store_true", help="re-copy bundles already in the inbox")
    ap.add_argument("--no-index", action="store_true", help="deposit only, skip indexing")
    ap.add_argument("--verify-only", action="store_true", help="verify + index from source, no deposit")
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

    brain = import_brain()
    ok_dirs: list[Path] = []
    failed = 0

    for b in bundles:
        print(f"\n==> {b.name}")
        manifest, errors, extras = verify_bundle(b)
        if manifest is None or errors:
            failed += 1
            for e in (errors or ["manifest unreadable"]):
                print(f"    TRANSPORT VERIFY FAILED: {e}")
            continue
        print("    transport verify OK (sizes + sha256 match manifest)")
        if extras:
            print(f"    note: {len(extras)} file(s) on disk not listed in manifest")

        if brain:
            try:
                brain["validate_bundle"](b)
                print("    contract validate OK (brain.ingest.bundle)")
            except brain["BundleError"] as e:
                failed += 1
                print(f"    CONTRACT VALIDATE FAILED (brain would reject): {e}")
                continue

        if args.verify_only:
            ok_dirs.append(b)
        else:
            dest = deposit_atomic(b, inbox, args.force)
            if dest:
                ok_dirs.append(dest)

    if ok_dirs and brain and not args.no_index:
        index_and_query(brain, ok_dirs, args.query, args.k, args.hops)

    print()
    if not args.verify_only and ok_dirs:
        print(f"Done: {len(ok_dirs)} bundle(s) in {inbox}.")
        print("If `brain serve` is running with autorun, the watcher will pick them")
        print("up within its debounce window and launch the full agent diagnosis.")
    if failed:
        print(f"{failed} bundle(s) FAILED verification and were NOT deposited.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
