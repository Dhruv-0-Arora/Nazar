import json
from pathlib import Path

import pytest

from brain.config import Config
from brain.graph.build import build_graph
from brain.graph.store import GraphStore
from brain.index.bm25 import Bm25Index
from brain.ingest.bundle import load_manifest
from brain.ingest.chunker import chunk_bundle
from brain.llm import ChatResult
from brain.retrieval import Retriever

FIXTURES = Path(__file__).parent / "fixtures"
BUNDLE_A = FIXTURES / "bundle-laptop-a-20260726T120000Z"
BUNDLE_B = FIXTURES / "bundle-laptop-b-20260726T120100Z"

LOG_CHUNK = "laptop-a:app_logs/backend.log:L1-L4"
ENV_CHUNK = "laptop-a:services/backend/config/backend.env:L1-L4"


@pytest.fixture()
def cfg(tmp_path) -> Config:
    c = Config(
        home=tmp_path / "brain-home",
        ollama_url="http://127.0.0.1:1",  # never reached in tests
        model="fake",
        max_turns=5,
        debounce_s=0.1,
        poll_interval_s=0.05,
        port=8000,
        parallel=1,
        autorun=False,
        llm_timeout_s=5,
    )
    c.ensure_dirs()
    return c


@pytest.fixture(scope="session")
def case():
    """Both fixture bundles ingested together, like a real two-machine case."""
    manifests, chunks = [], []
    for bundle in (BUNDLE_A, BUNDLE_B):
        m = load_manifest(bundle)
        manifests.append(m)
        chunks.extend(chunk_bundle(bundle, m))
    chunk_store = {c.id: c for c in chunks}
    index = Bm25Index(chunks)
    graph = GraphStore()
    build_graph(chunks, manifests, graph)
    return Retriever(chunk_store, index, graph), manifests


class FakeLLM:
    """Scripted stand-in for OllamaLLM; same interface (the llm.py seam)."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def ping(self) -> str:
        return "ok"

    def _next(self) -> ChatResult:
        text = self.responses.pop(0) if self.responses else '{"conclude": true, "actions": []}'
        return ChatResult(text=text, eval_count=10, eval_duration_s=0.1, prompt_eval_count=100)

    def chat(self, messages, **kwargs) -> ChatResult:
        self.calls.append(list(messages))
        return self._next()

    def chat_stream(self, messages, *, thinking=False, on_token=lambda t, k: None) -> ChatResult:
        self.calls.append(list(messages))
        result = self._next()
        for i in range(0, len(result.text), 40):
            on_token(result.text[i : i + 40], "report")
        return result


def scripted_diagnosis() -> list[str]:
    """A three-turn scripted run against the fixture case, ending in a valid
    report that also carries one dangling citation (exercises stripping)."""
    turn1 = {
        "thought": "backend errors first",
        "actions": [
            {"op": "search", "query": "ENOTFOUND db connect failed", "k": 5},
            {"op": "graph", "delta": {"op": "add_node", "node": {"layer": "reasoning", "type": "hypothesis", "label": "stale DB host in backend.env"}}},
        ],
        "conclude": False,
    }
    turn2 = {
        "thought": "walk from the symptom chunk to its config",
        "actions": [
            {"op": "expand", "chunk_ids": [LOG_CHUNK], "hops": 1},
            {"op": "graph", "delta": {"op": "add_node", "node": {"layer": "reasoning", "type": "finding", "label": "backend.env points at db.internal", "parent": "hyp:1", "stance": "supports", "evidence": [ENV_CHUNK]}}},
        ],
        "conclude": False,
    }
    turn3 = {
        "thought": "confident",
        "actions": [{"op": "graph", "delta": {"op": "set_status", "id": "hyp:1", "status": "confirmed"}}],
        "conclude": True,
    }
    report = {
        "root_cause": "backend.env on laptop-a sets DB_HOST=db.internal, a host decommissioned in the 2025 migration; the DB runs locally on 127.0.0.1:5432",
        "confidence": "high",
        "affected_machines": ["laptop-a"],
        "evidence": [
            {"chunk_id": ENV_CHUNK, "why": "DB_HOST=db.internal set here"},
            {"chunk_id": LOG_CHUNK, "why": "repeating ENOTFOUND db.internal:5432"},
            {"chunk_id": "laptop-a:bogus.txt:L1-L2", "why": "this citation is dangling and must be stripped"},
        ],
        "ruled_out": [{"hypothesis": "firewall blocking 3001", "why": "iptables shows ACCEPT policy with no rules", "chunk_id": None}],
        "action_plan": [
            {"step": 1, "action": "set DB_HOST=127.0.0.1 in /etc/myapp/backend.env", "command": "sed -i 's/^DB_HOST=.*/DB_HOST=127.0.0.1/' /etc/myapp/backend.env", "risk": "low"},
            {"step": 2, "action": "restart the backend service", "command": "systemctl restart backend", "risk": "low"},
        ],
        "proposed_fix_script": "#!/usr/bin/env bash\nset -eu\nsed -i 's/^DB_HOST=.*/DB_HOST=127.0.0.1/' /etc/myapp/backend.env\nsystemctl restart backend\n",
    }
    return [json.dumps(turn1), json.dumps(turn2), json.dumps(turn3), json.dumps(report)]
