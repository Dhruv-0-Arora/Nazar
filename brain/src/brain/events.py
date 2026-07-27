"""Append-only per-run event log (ADR-0007).

The event log is the SSE source of truth: the API tails this file, so a
crash, reconnect, or post-hoc replay all read the same record. Single
writer per run; seq numbers are monotonic from 1.
"""

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

TERMINAL_EVENTS = {"done", "error"}


@dataclass(frozen=True)
class Event:
    seq: int
    event: str
    data: dict
    ts: float = 0.0  # epoch seconds at emit time


class EventLog:
    """Append-only, seq-ordered. Multiple writer threads are allowed (the agent
    loop and the graph organizer); the lock serializes them, and emits after
    close() are silent no-ops so a late organizer pass never hits a closed fh."""

    def __init__(self, path: Path):
        self.path = path
        self._seq = 0
        self._lock = threading.Lock()
        self._closed = False
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8")

    @property
    def seq(self) -> int:
        return self._seq

    def emit(self, event: str, data: dict) -> int:
        with self._lock:
            if self._closed:
                return 0
            self._seq += 1
            record = {"seq": self._seq, "event": event, "ts": time.time(), "data": data}
            self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())
            return self._seq

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._fh.close()


def read_events(path: Path, after_seq: int = 0) -> list[Event]:
    if not path.exists():
        return []
    events = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # torn write at EOF; the next read picks it up complete
            if rec.get("seq", 0) > after_seq:
                events.append(Event(seq=rec["seq"], event=rec["event"], data=rec.get("data", {}), ts=rec.get("ts", 0.0)))
    return events
