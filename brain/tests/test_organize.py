"""Organizer overlay (ADR-0016): deterministic with a stubbed embedder."""

import json
from dataclasses import replace

from brain.agent.loop import RunContext
from brain.graph.organize import Organizer
from brain.ingest.chunker import Chunk


class StubEmbedder:
    """Bucketed one-hot-ish vectors: same-topic chunks are near, others far."""

    BUCKETS = (("db", "database", "5432"), ("frontend", "proxy", "portal"), ("printer", "facilities"))

    def ping(self):
        return "ok"

    def embed(self, texts):
        vectors = []
        for t in texts:
            low = t.lower()
            v = [0.0, 0.0, 0.0, 0.05]
            for i, words in enumerate(self.BUCKETS):
                if any(w in low for w in words):
                    v[i] = 1.0
            vectors.append(v)
        return vectors


def make_chunk(cid, path, text, mentions=()):
    machine, rest = cid.split(":", 1)
    return Chunk(id=cid, text=text, machine_id=machine, file_path=path, span=(1, 2),
                 kind="evidence", bundle_id="b", mentions=list(mentions))


def make_ctx(tmp_path, chunks):
    ctx = RunContext(run_id="run-org", dir=tmp_path, bundle_ids=["b"], question="q")
    ctx.chunk_store = {c.id: c for c in chunks}
    return ctx


def build_chunks():
    return [
        make_chunk("a:app_logs/backend.log", "app_logs/backend.log", "ERROR database connect failed 5432", ["error:E1"]),
        make_chunk("a:services/backend/config/backend.env", "services/backend/config/backend.env", "DB_HOST=db.internal database", ["error:E1"]),
        make_chunk("b:docs/db-migration.md", "docs/db-migration.md", "database moved off db host 5432"),
        make_chunk("b:app_logs/frontend.log", "app_logs/frontend.log", "frontend proxy failed"),
        make_chunk("b:services/frontend/config/frontend.env", "services/frontend/config/frontend.env", "portal proxy target"),
        make_chunk("a:docs/printer.md", "docs/printer.md", "printer offline call facilities"),  # orphan candidate
    ]


def test_overlay_edges_clusters_and_orphans(cfg, tmp_path):
    org = Organizer(cfg, StubEmbedder())
    ctx = make_ctx(tmp_path, build_chunks())
    overlay = org.run_pass(ctx, "ingest")

    assert overlay is not None
    assert (tmp_path / "organization.json").is_file()
    assert ctx.organization == overlay

    pairs = {(e["source"], e["target"]) for e in overlay["edges"]}
    flat = {c for p in pairs for c in p}
    # semantic relates: db-topic chunks connect across machines and files
    assert "b:docs/db-migration.md" in flat
    assert any("backend" in a and "db-migration" in b or "db-migration" in a and "backend" in b for a, b in pairs)
    # clusters cover the connected topics
    assert overlay["clusters"], "expected at least one cluster"
    members = {m for c in overlay["clusters"] for m in c["members"]}
    # the printer chunk shares no topic and no mentions: it must be adopted
    assert "a:docs/printer.md" in members
    assert any("a:docs/printer.md" in p for p in pairs)


def test_overlay_is_deterministic(cfg, tmp_path):
    org = Organizer(cfg, StubEmbedder())
    ctx = make_ctx(tmp_path, build_chunks())
    first = org.run_pass(ctx, "ingest")
    second = org.run_pass(ctx, "turn")
    assert {k: v for k, v in first.items() if k != "seq"} == {k: v for k, v in second.items() if k != "seq"}


def test_embedder_failure_never_raises(cfg, tmp_path):
    class DeadEmbedder:
        def embed(self, texts):
            from brain.llm import LLMError

            raise LLMError("embedder down")

    org = Organizer(cfg, DeadEmbedder())
    ctx = make_ctx(tmp_path, build_chunks())
    assert org.run_pass(ctx, "ingest") is None
    assert ctx.organization is None


def test_edge_caps_respected(cfg, tmp_path):
    tight = replace(cfg, org_max_edges=2, org_max_edges_per_chunk=1)
    org = Organizer(tight, StubEmbedder())
    ctx = make_ctx(tmp_path, build_chunks())
    overlay = org.run_pass(ctx, "ingest")
    relates_non_orphan = [e for e in overlay["edges"]]
    per_chunk = {}
    for e in relates_non_orphan[:2]:
        for c in (e["source"], e["target"]):
            per_chunk[c] = per_chunk.get(c, 0) + 1
    assert all(v <= 1 for v in per_chunk.values())


def test_concurrent_event_emit_is_safe(cfg, tmp_path):
    import threading

    from brain.events import EventLog, read_events

    log = EventLog(tmp_path / "events.jsonl")
    threads = [threading.Thread(target=lambda: [log.emit("organize", {"i": i}) for i in range(50)]) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log.close()
    assert log.emit("organize", {"late": True}) == 0  # closed log: silent no-op
    events = read_events(tmp_path / "events.jsonl")
    seqs = [e.seq for e in events]
    assert len(seqs) == 200 and len(set(seqs)) == 200 and seqs == sorted(seqs)
