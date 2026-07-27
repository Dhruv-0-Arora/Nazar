"""Console adapter (ADR-0015): the fde-console ConsoleApi surface served
from Brain run state. Shapes must mirror ui/src/api/types.ts."""

import json
import shutil
import time

from fastapi.testclient import TestClient

from brain.api.server import create_app
from conftest import BUNDLE_A, BUNDLE_B, ENV_CHUNK, FakeLLM, scripted_diagnosis

SNAPSHOT_KEYS = {"run", "machines", "logs", "graph", "steps", "trace", "diagnosis", "globalContext"}


def seed(cfg):
    for bundle in (BUNDLE_A, BUNDLE_B):
        shutil.copytree(bundle, cfg.inbox / bundle.name)


def test_snapshot_empty_state(cfg):
    app = create_app(cfg, llm=FakeLLM([]))
    with TestClient(app) as client:
        snap = client.get("/api/snapshot").json()
        assert set(snap) == SNAPSHOT_KEYS
        assert snap["run"]["phase"] == "collecting" and snap["run"]["runId"] == "idle"
        assert any(m["role"] == "brain" for m in snap["machines"])
        assert snap["diagnosis"]["rootCause"] is None


def test_chat_runs_diagnosis_and_streams_trace(cfg):
    seed(cfg)
    app = create_app(cfg, llm=FakeLLM(scripted_diagnosis()))
    with TestClient(app) as client:
        lines = []
        with client.stream("POST", "/api/chat", json={"text": "why is the frontend down?"}) as resp:
            assert resp.headers["content-type"].startswith("application/x-ndjson")
            for line in resp.iter_lines():
                if line.strip():
                    lines.append(json.loads(line))
        kinds = [t["kind"] for t in lines]
        assert kinds[0] == "user"
        assert "query" in kinds and "retrieval" in kinds
        answer = lines[-1]
        assert answer["kind"] == "answer"
        assert "Root cause" in answer["text"]
        assert ENV_CHUNK in answer["citations"]


def test_snapshot_after_run_carries_console_shapes(cfg):
    seed(cfg)
    app = create_app(cfg, llm=FakeLLM(scripted_diagnosis()))
    with TestClient(app) as client:
        with client.stream("POST", "/api/chat", json={"text": "diagnose"}) as resp:
            for _ in resp.iter_lines():
                pass  # drain to completion
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            snap = client.get("/api/snapshot").json()
            if snap["run"]["phase"] in ("resolved", "failed"):
                break
            time.sleep(0.05)

        assert snap["run"]["phase"] == "resolved"
        machine_ids = {m["id"] for m in snap["machines"]}
        assert {"laptop-a", "laptop-b", "brain"} <= machine_ids

        assert snap["logs"], "log entries expected"
        entry = snap["logs"][0]
        assert {"id", "machineId", "timestamp", "severity", "source", "path", "service", "message", "summary"} <= set(entry)
        assert any(e["severity"] == "error" for e in snap["logs"])

        graph = snap["graph"]
        assert any(c["implicated"] for c in graph["chunks"])
        assert any(c["kind"] == "config" for c in graph["chunks"])
        kinds = {e["kind"] for e in graph["edges"]}
        assert "calls" in kinds  # talks_to mapped to chunk-level calls edge
        assert "emitted" in kinds  # service anchor -> its log/journal chunks
        assert "references" in kinds  # co-mention derivation (doc <-> config/log)
        assert len(graph["edges"]) >= 8, f"graph too sparse: {len(graph['edges'])} edges"
        chunk_ids = {c["id"] for c in graph["chunks"]}
        assert all(e["source"] in chunk_ids and e["target"] in chunk_ids for e in graph["edges"])
        assert all(e["source"] != e["target"] for e in graph["edges"])

        # organizer overlay merge: write an overlay, expect clusters + relates in the snapshot
        run_id = snap["run"]["runId"]
        two = sorted(chunk_ids)[:2]
        overlay = {"version": 1, "seq": 1,
                   "clusters": [{"id": "c1", "label": None, "members": two}],
                   "edges": [{"source": two[0], "target": two[1], "kind": "relates", "weight": 0.9}]}
        (cfg.runs / run_id / "organization.json").write_text(json.dumps(overlay))
        snap2 = client.get("/api/snapshot").json()
        assert {"id": "c1", "label": None} in snap2["graph"]["clusters"]
        assert any(c["cluster"] == "c1" for c in snap2["graph"]["chunks"])
        assert any(e["kind"] == "relates" for e in snap2["graph"]["edges"])
        org = client.get(f"/api/runs/{run_id}/organization").json()
        assert org["clusters"][0]["id"] == "c1"

        assert snap["steps"] and snap["steps"][-1]["status"] == "done"
        assert any(t["kind"] == "answer" for t in snap["trace"])
        assert snap["diagnosis"]["confidence"] == 0.9
        assert snap["diagnosis"]["actions"][0]["command"]


def test_context_roundtrip_and_injection_into_question(cfg):
    seed(cfg)
    llm = FakeLLM(scripted_diagnosis())
    app = create_app(cfg, llm=llm)
    with TestClient(app) as client:
        assert client.put("/api/context", json={"markdown": "site is on generator power"}).json() == {"ok": True}
        assert client.get("/api/snapshot").json()["globalContext"] == "site is on generator power"
        with client.stream("POST", "/api/chat", json={"text": "diagnose"}) as resp:
            for _ in resp.iter_lines():
                pass
    assert "generator power" in llm.calls[0][1]["content"]


def test_snapshot_is_byte_stable_across_builds(cfg):
    """SSE change-detection and React render keys require identical state to
    produce identical frames - no now() timestamps or unstable ids."""
    seed(cfg)
    app = create_app(cfg, llm=FakeLLM(scripted_diagnosis()))
    with TestClient(app) as client:
        with client.stream("POST", "/api/chat", json={"text": "diagnose"}) as resp:
            for _ in resp.iter_lines():
                pass
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if client.get("/api/snapshot").json()["run"]["phase"] in ("resolved", "failed"):
                break
            time.sleep(0.05)
        a = client.get("/api/snapshot").text
        time.sleep(1.1)  # cross a wall-clock second boundary
        b = client.get("/api/snapshot").text
    assert a == b


def test_chat_without_bundles_answers_gracefully(cfg):
    app = create_app(cfg, llm=FakeLLM([]))
    with TestClient(app) as client:
        with client.stream("POST", "/api/chat", json={"text": "diagnose"}) as resp:
            lines = [json.loads(l) for l in resp.iter_lines() if l.strip()]
    assert lines[-1]["kind"] == "answer" and "No bundles" in lines[-1]["text"]
