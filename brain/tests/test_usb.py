"""USB intake layer (ADR-0012): drives the teammate's real receive_bundle.py,
then verifies normalization, deposit, auto full-context, and injection."""

import hashlib
import json
import shutil

from brain.ingest import usb
from brain.ingest.bundle import validate_bundle
from brain.runs import RunRegistry
from conftest import BUNDLE_A, FakeLLM, scripted_diagnosis

USB_TS = "20260726T212139Z"
USB_DIRNAME = f"bundle-BK608-{USB_TS}"  # uppercase host, like the real usb collector emits


def make_usb_client(root):
    """A stick-shaped tree: usb-transport/{client/outbox/bundle-*, workstation/}."""
    outbox = root / "usb-transport" / "client" / "outbox"
    bundle = outbox / USB_DIRNAME
    files = {
        "system.txt": "### CMD: uptime ###\n 12:00:00 up 1 day\n",
        "network.txt": "### CMD: ip addr ###\n    inet 10.0.0.5/24\n",
        "app_logs/01-LOG.txt": "2026-07-26T21:20:00Z ERROR stale text docs pipeline crashed\n",
        "problem/TEXTERROR/LOG.txt": "ERROR: cannot parse TEXTERROR corpus\n",
        "problem/TEXTERROR/readme.md": "# TEXTERROR\nBroken text pipeline folder.\n",
        "NOTES.txt": "",
    }
    entries = []
    for rel, text in files.items():
        p = bundle / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        entries.append({
            "path": rel,
            "kind": "log" if "LOG" in rel else "text",
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        })
    manifest = {
        "contract_version": "1",  # the usb collector's dialect, not ours
        "bundle": USB_DIRNAME,
        "hostname": "BK608",
        "created_at_utc": "2026-07-26T21:21:39Z",
        "os": "Windows 11 (git-bash)",
        "collector_version": "0.1.0",
        "file_count": len(entries),
        "total_bytes": sum(e["bytes"] for e in entries),
        "counts_by_kind": {},
        "targets": {"problem_dirs": ["problem/TEXTERROR"], "log_files": ["problem/TEXTERROR/LOG.txt"], "services": ["testerrorfiles"]},
        "log_tail_lines": 500,
        "files": entries,
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # ship the real receiver on the stick, like the actual layout
    workstation = root / "usb-transport" / "workstation"
    workstation.mkdir(parents=True)
    shutil.copyfile(usb.REPO_RECEIVER, workstation / "receive_bundle.py")
    return outbox


NORMALIZED = f"bundle-bk608-{USB_TS}"


def test_receive_normalizes_and_deposits(cfg, tmp_path):
    outbox = make_usb_client(tmp_path / "stick")
    result = usb.receive(tmp_path / "stick", cfg)  # stick root, not the outbox: path resolution
    assert result["errors"] == []
    assert result["received"] == [NORMALIZED]
    assert "VERIFICATION: OK" in result["summary"]

    deposited = cfg.inbox / NORMALIZED
    manifest = validate_bundle(deposited)  # normalized bundle passes CONTRACT v1.0
    assert manifest.machine_id == "bk608"
    assert manifest.services == ("testerrorfiles",)
    assert "problem dirs: problem/TEXTERROR" in manifest.notes
    assert (deposited / "manifest.usb.json").is_file()  # original preserved
    assert (deposited / "processes.txt").is_file()  # synthesized required file
    assert usb.is_usb_bundle(deposited)  # receipt.json marks the transport

    # idempotent: a second receive skips the already-deposited bundle
    again = usb.receive(outbox, cfg)
    assert again["received"] == [] and USB_DIRNAME in again["skipped"]


def test_usb_run_gets_full_context_injected(cfg, tmp_path):
    make_usb_client(tmp_path / "stick")
    usb.receive(tmp_path / "stick", cfg)
    shutil.copytree(BUNDLE_A, cfg.inbox / BUNDLE_A.name)  # mixed case: ssh + usb bundles

    registry = RunRegistry(cfg, FakeLLM(scripted_diagnosis()))
    ctx = registry.create_run([NORMALIZED, BUNDLE_A.name], "diagnose")
    assert ctx.full_context is True  # auto-detected from the usb receipt

    from brain.agent.loop import execute_run

    llm = FakeLLM(scripted_diagnosis())
    execute_run(ctx, cfg, llm)
    assert ctx.status == "done", ctx.error

    first_user = llm.calls[0][1]["content"]
    assert "FULL CLIENT CONTEXT" in first_user
    assert f"----- bk608:problem/TEXTERROR/LOG.txt:L1-L1 -----" in first_user
    assert "cannot parse TEXTERROR corpus" in first_user  # verbatim client-folder content
    assert ctx.meta()["full_context"] is True


def test_full_context_budget_omits_and_notes(cfg, tmp_path):
    make_usb_client(tmp_path / "stick")
    usb.receive(tmp_path / "stick", cfg)
    from dataclasses import replace

    small = replace(cfg, full_ctx_chars=200)  # force omissions
    registry = RunRegistry(small, None)
    ctx = registry.create_run([NORMALIZED], "diagnose")
    llm = FakeLLM(scripted_diagnosis())
    execute_run_ok(ctx, small, llm)
    first_user = llm.calls[0][1]["content"]
    assert "omitted for length" in first_user


def execute_run_ok(ctx, cfg, llm):
    from brain.agent.loop import execute_run

    execute_run(ctx, cfg, llm)
    assert ctx.status == "done", ctx.error


def test_usb_api_endpoint(cfg, tmp_path):
    from fastapi.testclient import TestClient

    from brain.api.server import create_app

    make_usb_client(tmp_path / "stick")
    app = create_app(cfg, llm=FakeLLM(scripted_diagnosis()))
    with TestClient(app) as client:
        resp = client.post("/api/usb/receive", json={"source": str(tmp_path / "stick")})
        assert resp.status_code == 200
        assert resp.json()["received"] == [NORMALIZED]

        listed = client.get("/api/bundles").json()
        assert any(b["bundle_id"] == NORMALIZED and b["state"] == "ready" for b in listed)

        run = client.post("/api/runs", json={"bundle_ids": [NORMALIZED]}).json()
        assert run["full_context"] is True

        missing = client.post("/api/usb/receive", json={"source": str(tmp_path / "nowhere")})
        assert missing.status_code == 404


def test_non_usb_run_stays_retrieval_only(cfg):
    shutil.copytree(BUNDLE_A, cfg.inbox / BUNDLE_A.name)
    registry = RunRegistry(cfg, None)
    ctx = registry.create_run([BUNDLE_A.name], "diagnose")
    assert ctx.full_context is False
    forced = registry.create_run([BUNDLE_A.name + ""], "diagnose", full_context=True)
    assert forced.full_context is True
