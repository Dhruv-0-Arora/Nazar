import json
import shutil

from brain.agent.loop import RunContext, execute_run
from brain.events import read_events
from conftest import BUNDLE_A, BUNDLE_B, ENV_CHUNK, FakeLLM, scripted_diagnosis


def make_ctx(cfg, tmp_path) -> RunContext:
    run_dir = tmp_path / "run-test"
    (run_dir / "bundles").mkdir(parents=True)
    for bundle in (BUNDLE_A, BUNDLE_B):
        shutil.copytree(bundle, run_dir / "bundles" / bundle.name)
    return RunContext(run_id="run-test", dir=run_dir, bundle_ids=[BUNDLE_A.name, BUNDLE_B.name], question="why is the frontend failing?")


def test_full_run_with_scripted_llm(cfg, tmp_path):
    ctx = make_ctx(cfg, tmp_path)
    llm = FakeLLM(scripted_diagnosis())
    execute_run(ctx, cfg, llm)

    assert ctx.status == "done", ctx.error
    assert ctx.turns_completed == 3

    report = json.loads((ctx.dir / "report.json").read_text())
    assert report["confidence"] == "high"
    cited = {e["chunk_id"] for e in report["evidence"]}
    assert ENV_CHUNK in cited
    assert not any("bogus" in c for c in cited)  # dangling citation stripped

    md = (ctx.dir / "report.md").read_text()
    assert "db.internal" in md and "Query trail" in md

    graph = json.loads((ctx.dir / "graph.json").read_text())
    reasoning = [n for n in graph["nodes"] if n["layer"] == "reasoning"]
    assert {n["id"] for n in reasoning} == {"hyp:1", "finding:1"}
    assert next(n for n in reasoning if n["id"] == "hyp:1")["status"] == "confirmed"

    events = read_events(ctx.dir / "events.jsonl")
    kinds = [e.event for e in events]
    assert kinds[-1] == "done"
    for expected in ("status", "query", "chunk", "graph", "token"):
        assert expected in kinds, f"missing {expected} events"
    seqs = [e.seq for e in events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)

    # chunks.jsonl written after graph build: mentions must be populated
    mentions = [json.loads(line)["mentions"] for line in (ctx.dir / "chunks.jsonl").read_text().splitlines()]
    assert any(m for m in mentions)

    metrics = json.loads((ctx.dir / "metrics.json").read_text())
    assert metrics["turns"] == 3 and metrics["tokens_generated"] > 0


def test_unparseable_turns_skip_then_conclude(cfg, tmp_path):
    ctx = make_ctx(cfg, tmp_path)
    garbage = ["not json at all"] * 3  # one turn's worth of parse retries
    llm = FakeLLM(garbage + scripted_diagnosis()[2:])  # then conclude + report
    execute_run(ctx, cfg, llm)
    assert ctx.status == "done", ctx.error


def test_llm_total_failure_marks_run_failed(cfg, tmp_path):
    class DeadLLM(FakeLLM):
        def chat(self, messages, **kwargs):
            from brain.llm import LLMError

            raise LLMError("ollama unreachable")

        chat_stream = chat

    ctx = make_ctx(cfg, tmp_path)
    execute_run(ctx, cfg, DeadLLM([]))
    assert ctx.status == "failed"
    events = read_events(ctx.dir / "events.jsonl")
    assert events[-1].event == "error"
    # failed runs still persist their graph so the console can render edges
    assert (ctx.dir / "graph.json").is_file()
