"""Bundle validation and manifest parsing, enforcing CONTRACT.md v1.x."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

BUNDLE_NAME_RE = re.compile(r"^bundle-[a-z0-9-]+-\d{8}T\d{6}Z$")
MACHINE_ID_RE = re.compile(r"^[a-z0-9-]+$")
REQUIRED_FILES = ("system.txt", "network.txt", "processes.txt")
MAX_FILE_BYTES = 512 * 1024
MAX_BUNDLE_BYTES = 5 * 1024 * 1024
SUPPORTED_CONTRACT_MAJOR = 1


class BundleError(Exception):
    """Raised when a bundle violates the contract. str(e) is the reject reason."""


@dataclass(frozen=True)
class Manifest:
    contract_version: str
    bundle_id: str
    machine_id: str
    hostname: str
    created_at: str
    os: str = ""
    kernel: str = ""
    collector_version: str = ""
    services: tuple[str, ...] = ()
    files: tuple[dict, ...] = field(default_factory=tuple)
    notes: str = ""


def load_manifest(bundle_dir: Path) -> Manifest:
    path = bundle_dir / "manifest.json"
    if not path.is_file():
        raise BundleError("manifest.json missing")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise BundleError(f"manifest.json unparseable: {e}") from e
    try:
        return Manifest(
            contract_version=str(raw["contract_version"]),
            bundle_id=str(raw.get("bundle_id", bundle_dir.name)),
            machine_id=str(raw["machine_id"]),
            hostname=str(raw.get("hostname", raw["machine_id"])),
            created_at=str(raw["created_at"]),
            os=str(raw.get("os", "")),
            kernel=str(raw.get("kernel", "")),
            collector_version=str(raw.get("collector_version", "")),
            services=tuple(raw.get("services", [])),
            files=tuple(raw.get("files", [])),
            notes=str(raw.get("notes", "")),
        )
    except KeyError as e:
        raise BundleError(f"manifest.json missing required field {e}") from e


def validate_bundle(bundle_dir: Path) -> Manifest:
    """Full contract validation. Returns the manifest or raises BundleError."""
    if not bundle_dir.is_dir():
        raise BundleError("not a directory")
    if not BUNDLE_NAME_RE.match(bundle_dir.name):
        raise BundleError(f"bundle name {bundle_dir.name!r} violates naming contract")

    manifest = load_manifest(bundle_dir)

    major = manifest.contract_version.split(".", 1)[0]
    if not major.isdigit() or int(major) != SUPPORTED_CONTRACT_MAJOR:
        raise BundleError(f"unsupported contract_version {manifest.contract_version!r}")
    if not MACHINE_ID_RE.match(manifest.machine_id):
        raise BundleError(f"machine_id {manifest.machine_id!r} violates [a-z0-9-]+")

    for name in REQUIRED_FILES:
        if not (bundle_dir / name).is_file():
            raise BundleError(f"required file {name} missing")

    total = 0
    for path in bundle_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(bundle_dir).as_posix()
        if ":" in rel or "\n" in rel:
            raise BundleError(f"path {rel!r} contains forbidden characters")
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise BundleError(f"{rel} exceeds 512 KB ({size} bytes)")
        total += size
    if total > MAX_BUNDLE_BYTES:
        raise BundleError(f"bundle exceeds 5 MB ({total} bytes)")

    return manifest


def bundle_text_files(bundle_dir: Path) -> list[Path]:
    """Every ingestible text file (manifest.json included, per SPEC 6.1), deterministic order."""
    files = []
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file():
            continue
        if _looks_binary(path):
            continue
        files.append(path)
    return files


def _looks_binary(path: Path, sniff: int = 4096) -> bool:
    with open(path, "rb") as fh:
        head = fh.read(sniff)
    return b"\x00" in head
