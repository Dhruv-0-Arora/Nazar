#!/usr/bin/env python3
"""receive_bundle.py — workstation (Brain) end of the transport layer.

Run this after plugging in the USB stick (or after pull.sh/push.sh staged a
bundle). It discovers bundle-* directories at the given source, verifies each
one against its manifest.json (existence, byte size, sha256), copies verified
bundles into the Brain inbox, writes a receipt.json, and prints a summary of
what was received — exactly what the Brain's indexer consumes.

This script deliberately contains NO indexing/chunking logic. Transport ends
when a verified bundle sits in the inbox.

Usage:
    python receive_bundle.py [source] [--inbox DIR] [--verify-only]
                             [--transport usb|ssh|push] [--force]

    [source]   a bundle directory, or a directory containing bundle-* dirs.
               OPTIONAL: when omitted, defaults to the client outbox that
               ships on the same USB stick as this script
               (../../usb-transport/client/outbox relative to here) — so on
               the workstation, plugging in the stick and running
               `python receive_bundle.py` with no arguments does the whole
               ingest. Setup is the only interactive step in this layer.
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

CONTRACT_VERSION = "1"
RECEIVER_VERSION = "0.1.0"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def discover_bundles(source: Path):
    """Return a list of bundle directories found at source."""
    if (source / "manifest.json").is_file():
        return [source]
    found = sorted(
        d for d in source.glob("bundle-*")
        if d.is_dir() and (d / "manifest.json").is_file()
    )
    return found


def verify_bundle(bundle_dir: Path):
    """Check every manifest entry against disk. Returns (manifest, errors, extras)."""
    errors = []
    try:
        manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return None, [f"manifest.json unreadable or invalid JSON: {e}"], []

    major = str(manifest.get("contract_version", "")).split(".", 1)[0]
    if major != CONTRACT_VERSION:
        errors.append(
            f"contract version mismatch: bundle says "
            f"{manifest.get('contract_version')!r}, receiver speaks major {CONTRACT_VERSION!r}"
        )

    listed = set()
    for entry in manifest.get("files", []):
        rel = entry.get("path", "")
        listed.add(rel)
        f = bundle_dir / rel
        if not f.is_file():
            errors.append(f"missing file: {rel}")
            continue
        actual_bytes = f.stat().st_size
        if actual_bytes != entry.get("bytes"):
            errors.append(
                f"size mismatch: {rel} manifest={entry.get('bytes')} actual={actual_bytes}"
            )
            continue
        expected_hash = entry.get("sha256", "")
        if expected_hash:
            actual_hash = sha256_of(f)
            if actual_hash != expected_hash:
                errors.append(f"sha256 mismatch: {rel}")

    # Files present on disk but not in the manifest (receipt.json is ours).
    extras = []
    for f in bundle_dir.rglob("*"):
        if f.is_file():
            rel = f.relative_to(bundle_dir).as_posix()
            if rel not in listed and rel not in ("manifest.json", "receipt.json", "SUMMARY.md"):
                extras.append(rel)

    return manifest, errors, extras


def human_bytes(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


def summarize(manifest, bundle_dir, errors, extras, dest, transport):
    t = manifest.get("targets", {}) if manifest else {}
    print("=" * 62)
    print(f" RECEIVED BUNDLE ({transport}): {manifest.get('bundle', bundle_dir.name)}")
    print("=" * 62)
    print(f"  from host      : {manifest.get('hostname', '?')}")
    print(f"  collected at   : {manifest.get('created_at_utc', '?')} (UTC)")
    print(f"  client OS      : {manifest.get('os', '?')}")
    print(f"  collector      : v{manifest.get('collector_version', '?')}"
          f"  (contract v{manifest.get('contract_version', '?')})")
    print(f"  files          : {manifest.get('file_count', '?')}"
          f"  ({human_bytes(manifest.get('total_bytes'))})")

    counts = manifest.get("counts_by_kind", {})
    if counts:
        pretty = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  by kind        : {pretty}")

    if t.get("problem_dirs"):
        print(f"  problem dirs   : {', '.join(t['problem_dirs'])}")
    if t.get("log_files"):
        print(f"  tracked logs   : {', '.join(t['log_files'])}"
              f"  (last {manifest.get('log_tail_lines', '?')} lines each)")
    if t.get("docs_dir"):
        print(f"  docs corpus    : {t['docs_dir']}")
    if t.get("services"):
        print(f"  services       : {', '.join(t['services'])}")

    print()
    print("  contents:")
    for entry in (manifest.get("files") or []):
        print(f"    [{entry.get('kind', '?'):9}] {entry.get('path')}"
              f"  ({human_bytes(entry.get('bytes'))})")

    if extras:
        print()
        print("  ! files on disk not listed in manifest:")
        for rel in extras:
            print(f"    {rel}")

    print()
    if errors:
        print("  VERIFICATION: FAILED")
        for e in errors:
            print(f"    - {e}")
    else:
        print("  VERIFICATION: OK - every manifest entry present, sizes and hashes match")

    if dest:
        print(f"  inbox location : {dest}")
        print("  status         : ready for indexing (indexer not part of transport layer)")
    print()


def write_markdown_summary(manifest, errors, extras, dest: Path, transport: str):
    """Render manifest.json as SUMMARY.md inside the inbox bundle — the
    no-LLM stand-in for the future diagnosis report (M3)."""
    t = manifest.get("targets", {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# Bundle summary — {manifest.get('bundle', dest.name)}",
        "",
        f"Received via **{transport}** at {now} (UTC). "
        f"Generated by receive_bundle.py v{RECEIVER_VERSION} from `manifest.json` — no model involved.",
        "",
        "## Origin",
        "",
        "| | |",
        "|---|---|",
        f"| Hostname | `{manifest.get('hostname', '?')}` |",
        f"| Collected at | {manifest.get('created_at_utc', '?')} (UTC) |",
        f"| Client OS | {manifest.get('os', '?')} |",
        f"| Collector | v{manifest.get('collector_version', '?')} "
        f"(contract v{manifest.get('contract_version', '?')}) |",
        f"| Files | {manifest.get('file_count', '?')} "
        f"({human_bytes(manifest.get('total_bytes'))}) |",
        "",
        "## Registered targets",
        "",
    ]
    for label, key in (("Problem folders", "problem_dirs"),
                       ("Tracked logs", "log_files"),
                       ("Services", "services")):
        vals = t.get(key) or []
        for v in vals:
            lines.append(f"- **{label[:-1] if len(vals) == 1 else label}**: `{v}`")
    if t.get("docs_dir"):
        lines.append(f"- **Docs corpus**: `{t['docs_dir']}`")
    lines += [
        "",
        "## Contents by kind",
        "",
        "| Kind | Count |",
        "|---|---|",
    ]
    for kind, count in sorted((manifest.get("counts_by_kind") or {}).items()):
        lines.append(f"| {kind} | {count} |")
    lines += [
        "",
        "## Files",
        "",
        "| Path | Kind | Size | sha256 |",
        "|---|---|---|---|",
    ]
    for entry in manifest.get("files", []):
        sha = entry.get("sha256", "")
        lines.append(f"| `{entry.get('path')}` | {entry.get('kind', '?')} "
                     f"| {human_bytes(entry.get('bytes'))} | `{sha[:12]}…` |" if sha
                     else f"| `{entry.get('path')}` | {entry.get('kind', '?')} "
                          f"| {human_bytes(entry.get('bytes'))} | (none) |")
    lines += ["", "## Verification", ""]
    if errors:
        lines.append("**FAILED**")
        lines += [f"- {e}" for e in errors]
    else:
        lines.append("**OK** — every manifest entry present, sizes and hashes match.")
    if extras:
        lines += ["", "Files on disk not listed in the manifest:"]
        lines += [f"- `{r}`" for r in extras]
    lines += ["", "---", "*Next stage (not part of transport): indexer chunks these "
              "files, builds BM25 + graph, and the agent loop produces the real report.*", ""]
    (dest / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def receive(bundle_dir: Path, inbox: Path, transport: str,
            verify_only: bool, force: bool) -> bool:
    manifest, errors, extras = verify_bundle(bundle_dir)
    if manifest is None:
        print(f"ERROR: {bundle_dir}: {errors[0]}", file=sys.stderr)
        return False

    dest = None
    if not verify_only:
        dest = inbox / bundle_dir.name
        if dest.exists():
            if force:
                shutil.rmtree(dest)
            else:
                print(f"NOTE: {dest} already in inbox - verifying in place "
                      f"(use --force to re-copy).")
                dest_existing = dest
                manifest, errors, extras = verify_bundle(dest_existing)
                if manifest is not None:
                    write_markdown_summary(manifest, errors, extras, dest_existing, transport)
                summarize(manifest, dest_existing, errors, extras, dest_existing, transport)
                return not errors
        inbox.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundle_dir, dest)

        receipt = {
            "receiver_version": RECEIVER_VERSION,
            "received_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "transport": transport,
            "source": str(bundle_dir),
            "verified": not errors,
            "errors": errors,
            "unlisted_files": extras,
        }
        (dest / "receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        write_markdown_summary(manifest, errors, extras, dest, transport)

    summarize(manifest, bundle_dir, errors, extras, dest, transport)
    return not errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", nargs="?", default=None,
                    help="bundle dir, or dir containing bundle-* dirs. "
                         "Default: the client outbox on this same USB stick "
                         "(../client/outbox relative to this script)")
    ap.add_argument("--inbox", default=str(Path.home() / "brain" / "inbox"),
                    help="Brain inbox directory (default: ~/brain/inbox)")
    ap.add_argument("--transport", default="usb", choices=["usb", "ssh", "push"],
                    help="how this bundle arrived (recorded in receipt.json)")
    ap.add_argument("--verify-only", action="store_true",
                    help="verify + summarize without copying to the inbox")
    ap.add_argument("--force", action="store_true",
                    help="re-copy even if the bundle already sits in the inbox")
    args = ap.parse_args()

    if args.source is None:
        # Zero-argument mode: this script ships on the USB stick alongside the
        # client folder, so the outbox is always at a fixed relative location.
        source = (Path(__file__).resolve().parent.parent / "client" / "outbox")
        print(f"No source given - using the outbox on this stick: {source}")
    else:
        source = Path(args.source).resolve()
    if not source.is_dir():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        if args.source is None:
            print("Nothing collected yet? Run setup.sh / collector.sh on the "
                  "client first — the outbox is created on first collection.",
                  file=sys.stderr)
        sys.exit(2)

    bundles = discover_bundles(source)
    if not bundles:
        print(f"ERROR: no bundle-*/manifest.json found under {source}", file=sys.stderr)
        sys.exit(2)

    print(f"Found {len(bundles)} bundle(s) at {source}\n")
    all_ok = True
    for b in bundles:
        ok = receive(b, Path(args.inbox), args.transport,
                     args.verify_only, args.force)
        all_ok = all_ok and ok

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
