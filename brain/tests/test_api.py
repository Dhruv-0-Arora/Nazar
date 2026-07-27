import shutil
import time
import urllib.parse

from fastapi.testclient import TestClient

from brain.api.server import create_app
from brain.ingest.watcher import list_bundles
from conftest import BUNDLE_A, BUNDLE_B, ENV_CHUNK, FakeLLM, scripted_diagnosis


def seed_inbox(cfg):
    for bundle in (BUNDLE_A, BUNDLE_B):
        shutil.copytree(bundle, cfg.inbox / bundle.name)


def wait_done(client, run_id, timeout=15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["status"] in ("done", "failed"):
            return detail
        time.sleep(0.05)
    raise AssertionError("run did not finish in time")


def test_full_api_flow(cfg):
    seed_inbox(cfg)
    app = create_app(cfg, llm=FakeLLM(scripted_diagnosis()))
    with TestClient(app) as client:
        health = client.get("/api/healthz").json()
        assert health["ollama"] == "ok"

        bundles = client.get("/api/bundles").json()
        assert {b["bundle_id"] for b in bundles} == {BUNDLE_A.name, BUNDLE_B.name}
        assert all(b["state"] == "ready" for b in bundles)

        resp = client.post("/api/runs", json={"bundle_ids": [BUNDLE_A.name, BUNDLE_B.name], "question": "diagnose"})
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]

        detail = wait_done(client, run_id)
        assert detail["status"] == "done"
        assert detail["report"]["confidence"] == "high"
        assert "report_markdown" in detail and detail["metrics"]["turns"] == 3

        listed = client.get("/api/runs").json()
        assert any(r["run_id"] == run_id for r in listed)

        graph = client.get(f"/api/runs/{run_id}/graph").json()
        assert graph["seq"] > 0
        assert any(n["id"] == "hyp:1" for n in graph["nodes"])
        assert any(e.get("attrs", {}).get("dangling") for e in graph["edges"])

        chunk = client.get(f"/api/runs/{run_id}/chunks/{urllib.parse.quote(ENV_CHUNK, safe='')}").json()
        assert chunk["chunk_id"] == ENV_CHUNK
        assert "db.internal" in chunk["text"]

        with client.stream("GET", f"/api/runs/{run_id}/stream") as stream:
            body = ""
            for line in stream.iter_lines():
                body += line + "\n"
                if "event: done" in body:
                    break
        assert "event: query" in body and "id: 1" in body

        # replay from an offset skips earlier events
        with client.stream("GET", f"/api/runs/{run_id}/stream?from_seq=9999") as stream:
            tail = "".join(stream.iter_lines())
        assert "event: query" not in tail

        assert client.get("/api/runs/nope").status_code == 404


def test_run_default_bundle_selection_and_errors(cfg):
    app = create_app(cfg, llm=FakeLLM(scripted_diagnosis()))
    with TestClient(app) as client:
        assert client.post("/api/runs", json={}).status_code == 400  # empty inbox
        seed_inbox(cfg)
        resp = client.post("/api/runs", json={})
        assert resp.status_code == 202
        detail = wait_done(client, resp.json()["run_id"])
        assert sorted(detail["bundle_ids"]) == sorted([BUNDLE_A.name, BUNDLE_B.name])


def test_reset_clears_state_and_bumps_epoch(cfg):
    seed_inbox(cfg)
    app = create_app(cfg, llm=FakeLLM(scripted_diagnosis()))
    with TestClient(app) as client:
        run_id = client.post("/api/runs", json={"bundle_ids": [BUNDLE_A.name]}).json()["run_id"]
        wait_done(client, run_id)

        registry = app.state.registry
        epoch_before = registry.epoch
        result = client.post("/api/reset", json={}).json()

        assert BUNDLE_A.name in result["removed_bundles"]
        assert run_id in result["removed_runs"]
        assert result["protected_running"] == []
        assert registry.epoch == epoch_before + 1
        assert client.get("/api/bundles").json() == []
        assert client.get("/api/runs").json() == []
        assert registry.used_bundle_ids() == set()  # watcher re-seed sees a clean slate

        # re-depositing the same bundle id after reset works (the demo loop)
        seed_inbox(cfg)
        assert client.post("/api/runs", json={"bundle_ids": [BUNDLE_A.name]}).status_code == 202


def test_rejected_bundle_listing(cfg):
    bad = cfg.inbox / BUNDLE_A.name
    shutil.copytree(BUNDLE_A, bad)
    (bad / "manifest.json").unlink()
    entries = list_bundles(cfg)
    assert entries[0]["state"] == "rejected"
    assert entries[0]["machine_id"] is None
    assert "manifest" in entries[0]["reason"]
