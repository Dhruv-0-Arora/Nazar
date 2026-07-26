"""Deterministic, structure-aware chunking (SPEC section 6.1).

Chunking is the retrieval substrate and the citation system: it must be
stable across graph rebuilds, so nothing here may depend on graph logic.
Chunk IDs follow CONTRACT.md section 6: <machine_id>:<path>:L<start>-L<end>.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .bundle import Manifest, bundle_text_files

CMD_MARKER_RE = re.compile(r"^### CMD: .+ ###$")
LOG_BOUNDARY_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]"          # ISO timestamps
    r"|\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}"  # syslog timestamps
    r"|-- )"                             # journalctl boundary lines
)
HEADING_RE = re.compile(r"^#{1,6}\s")
LOG_WINDOW = 40
CONFIG_WHOLE_FILE_MAX = 60


@dataclass
class Chunk:
    id: str
    text: str
    machine_id: str
    file_path: str  # bundle-relative
    span: tuple[int, int]  # 1-based inclusive
    kind: Literal["evidence", "knowledge"]
    bundle_id: str
    mentions: list[str] = field(default_factory=list)  # node IDs, filled by the graph builder

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.id,
            "text": self.text,
            "machine_id": self.machine_id,
            "file_path": self.file_path,
            "span": list(self.span),
            "kind": self.kind,
            "bundle_id": self.bundle_id,
            "mentions": self.mentions,
        }


def chunk_id(machine_id: str, file_path: str, start: int, end: int) -> str:
    return f"{machine_id}:{file_path}:L{start}-L{end}"


def chunk_bundle(bundle_dir: Path, manifest: Manifest) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in bundle_text_files(bundle_dir):
        rel = path.relative_to(bundle_dir).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            continue
        for start, end in _spans_for(rel, lines):
            text = "\n".join(lines[start - 1 : end])
            if not text.strip():
                continue
            kind: Literal["evidence", "knowledge"] = "knowledge" if rel.startswith("docs/") else "evidence"
            chunks.append(
                Chunk(
                    id=chunk_id(manifest.machine_id, rel, start, end),
                    text=text,
                    machine_id=manifest.machine_id,
                    file_path=rel,
                    span=(start, end),
                    kind=kind,
                    bundle_id=manifest.bundle_id,
                )
            )
    return chunks


def _spans_for(rel: str, lines: list[str]) -> list[tuple[int, int]]:
    if rel in ("system.txt", "network.txt"):
        return _split_cmd_sections(lines)
    if rel.startswith("app_logs/") or rel.endswith("/journal.txt"):
        return _split_log(lines)
    if rel.startswith("docs/") and rel.endswith(".md"):
        return _split_markdown(lines)
    if "/config/" in rel or rel.endswith("/status.txt"):
        return _split_config(lines)
    return [(1, len(lines))]  # processes.txt, packages.txt, anything else: whole file


def _split_cmd_sections(lines: list[str]) -> list[tuple[int, int]]:
    marks = [i + 1 for i, line in enumerate(lines) if CMD_MARKER_RE.match(line)]
    if not marks:
        return [(1, len(lines))]
    spans = []
    if marks[0] > 1:
        spans.append((1, marks[0] - 1))  # preamble before the first marker
    for j, start in enumerate(marks):
        end = (marks[j + 1] - 1) if j + 1 < len(marks) else len(lines)
        spans.append((start, end))
    return spans


def _split_log(lines: list[str]) -> list[tuple[int, int]]:
    """Blocks start at timestamp boundaries, merged up to LOG_WINDOW lines;
    oversized blocks fall back to fixed windows."""
    boundaries = [i + 1 for i, line in enumerate(lines) if LOG_BOUNDARY_RE.match(line)]
    if not boundaries or boundaries[0] != 1:
        boundaries.insert(0, 1)
    blocks = [(b, (boundaries[j + 1] - 1) if j + 1 < len(boundaries) else len(lines)) for j, b in enumerate(boundaries)]

    spans: list[tuple[int, int]] = []
    cur_start, cur_end = blocks[0]
    for start, end in blocks[1:]:
        if end - cur_start + 1 <= LOG_WINDOW:
            cur_end = end
        else:
            spans.append((cur_start, cur_end))
            cur_start, cur_end = start, end
    spans.append((cur_start, cur_end))

    windowed: list[tuple[int, int]] = []
    for start, end in spans:
        while end - start + 1 > LOG_WINDOW:
            windowed.append((start, start + LOG_WINDOW - 1))
            start += LOG_WINDOW
        windowed.append((start, end))
    return windowed


def _split_markdown(lines: list[str]) -> list[tuple[int, int]]:
    heads = [i + 1 for i, line in enumerate(lines) if HEADING_RE.match(line)]
    if not heads:
        return [(1, len(lines))]
    spans = []
    if heads[0] > 1:
        spans.append((1, heads[0] - 1))
    for j, start in enumerate(heads):
        end = (heads[j + 1] - 1) if j + 1 < len(heads) else len(lines)
        spans.append((start, end))
    return spans


def _split_config(lines: list[str]) -> list[tuple[int, int]]:
    if len(lines) <= CONFIG_WHOLE_FILE_MAX:
        return [(1, len(lines))]
    spans = []
    start = None
    for i, line in enumerate(lines, start=1):
        if line.strip() and start is None:
            start = i
        elif not line.strip() and start is not None:
            spans.append((start, i - 1))
            start = None
    if start is not None:
        spans.append((start, len(lines)))
    return spans or [(1, len(lines))]
