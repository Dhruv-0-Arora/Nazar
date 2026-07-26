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
        chunk_ids = {c["id"] for c in graph["chunks"]}
        assert all(e["source"] in chunk_ids and e["target"] in chunk_ids for e in graph["edges"])

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


def test_chat_without_bundles_answers_gracefully(cfg):
    app = create_app(cfg, llm=FakeLLM([]))
    with TestClient(app) as client:
        with client.stream("POST", "/api/chat", json={"text": "diagnose"}) as resp:
            lines = [json.loads(l) for l in resp.iter_lines() if l.strip()]
    assert lines[-1]["kind"] == "answer" and "No bundles" in lines[-1]["text"]
