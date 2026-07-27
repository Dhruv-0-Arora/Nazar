#!/usr/bin/env python
"""Reliability eval harness: repeated real-model diagnosis runs, auto-graded.

Runs N independent trials of the same case through the real agent loop and
model (no server needed), grades each report against ground truth, and writes
results.jsonl + summary.md. Run with brain's venv python:

    brain/.venv/bin/python eval/run_eval.py --trials 5
    brain/.venv/bin/python eval/run_eval.py --trials 3 --thinking   # A/B: thinking on the conclude turn

Trials are sequential on purpose: one Ollama slot, predictable latency.
"""

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grading import SCENARIOS, Criterion, criteria_for, grade  # noqa: E402

from brain.agent.loop import RunContext, execute_run  # noqa: E402
from brain.config import load_config  # noqa: E402
from brain.llm import OllamaLLM  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLES = [
    REPO / "brain/tests/fixtures/bundle-laptop-a-20260726T120000Z",
    REPO / "brain/tests/fixtures/bundle-laptop-b-20260726T120100Z",
]
DEFAULT_QUESTION = "Why is the frontend on laptop-b showing BACKEND UNAVAILABLE?"


def run_trial(idx: int, out_dir: Path, bundles: list[Path], question: str, cfg, llm, criteria: list[Criterion]) -> dict:
    run_dir = out_dir / f"trial-{idx:02d}"
    (run_dir / "bundles").mkdir(parents=True)
    for b in bundles:
        shutil.copytree(b, run_dir / "bundles" / b.name)
    ctx = RunContext(run_id=f"eval-{idx:02d}", dir=run_dir, bundle_ids=[b.name for b in bundles], question=question)

    start = time.monotonic()
    execute_run(ctx, cfg, llm)
    elapsed = time.monotonic() - start

    report = None
    if (run_dir / "report.json").is_file():
        report = json.loads((run_dir / "report.json").read_text())
    graded = grade(report, criteria)
    metrics = {}
    if (run_dir / "metrics.json").is_file():
        metrics = json.loads((run_dir / "metrics.json").read_text())
    return {
        "trial": idx,
        "status": ctx.status,
        "error": ctx.error,
        "elapsed_s": round(elapsed, 1),
        "turns": ctx.turns_completed,
        "tokens_generated": metrics.get("tokens_generated"),
        **graded,
    }


def summarize(rows: list[dict], out_dir: Path, args, criteria: list[Criterion]) -> str:
    n = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    lines = [
        "# Eval summary",
        "",
        f"Config: trials={n}, scenario={args.scenario}, thinking={args.thinking}, max_turns={args.max_turns}, model={args.model}",
        f"Started: {args.started}",
        "",
        f"## Hit rate: {passed}/{n} passed",
        "",
        "| trial | status | passed | elapsed_s | turns | tokens | required failures |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['trial']} | {r['status']} | {'PASS' if r['passed'] else 'FAIL'} | {r['elapsed_s']} "
            f"| {r['turns']} | {r['tokens_generated']} | {', '.join(r['required_failed']) or '-'} |"
        )
    lines += ["", "## Per-criterion rates", "", "| criterion | required | rate |", "|---|---|---|"]
    for c in criteria:
        rate = sum(1 for r in rows if r["criteria"][c.name])
        lines.append(f"| {c.name} | {'yes' if c.required else 'no'} | {rate}/{n} |")
    elapsed_vals = [r["elapsed_s"] for r in rows if r["status"] == "done"]
    if elapsed_vals:
        lines += ["", f"Mean elapsed (done runs): {sum(elapsed_vals) / len(elapsed_vals):.1f} s"]
    text = "\n".join(lines) + "\n"
    (out_dir / "summary.md").write_text(text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--bundles", nargs="*", type=Path, default=DEFAULT_BUNDLES)
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="fixture",
        help="grading key: 'fixture' for the bundled test fixtures (the default bundles), "
        "'clinic' for Cedar Hollow bundles collected from a live scenario/ deployment",
    )
    ap.add_argument("--thinking", action="store_true", help="enable thinking on the conclude turn")
    ap.add_argument("--max-turns", type=int, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    from dataclasses import replace

    cfg = load_config()
    cfg = replace(
        cfg,
        think_final=args.thinking,
        max_turns=args.max_turns if args.max_turns is not None else cfg.max_turns,
        model=args.model if args.model else cfg.model,
    )
    args.model = cfg.model
    args.max_turns = cfg.max_turns
    args.started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out or (REPO / "eval" / "results" / f"{stamp}{'-thinking' if args.thinking else ''}")
    out_dir.mkdir(parents=True)
    llm = OllamaLLM(cfg.ollama_url, cfg.model, cfg.llm_timeout_s, cfg.num_ctx)

    ping = llm.ping()
    if ping != "ok":
        print(f"ollama not ready: {ping}", file=sys.stderr)
        return 1

    criteria = criteria_for(SCENARIOS[args.scenario])
    rows = []
    with open(out_dir / "results.jsonl", "a") as fh:
        for i in range(1, args.trials + 1):
            row = run_trial(i, out_dir, args.bundles, args.question, cfg, llm, criteria)
            rows.append(row)
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            print(
                f"trial {i}/{args.trials}: {row['status']} {'PASS' if row['passed'] else 'FAIL'} "
                f"({row['elapsed_s']} s, {row['turns']} turns)"
                + (f" failures: {', '.join(row['required_failed'])}" if row["required_failed"] else ""),
                flush=True,
            )

    print()
    print(summarize(rows, out_dir, args, criteria))
    print(f"artifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
