# Eval harness

Repeated real-model diagnosis runs, auto-graded against `scenario/ground_truth.md`.
This is the reliability loop: run it, read the per-criterion rates, tune `brain/src/brain/agent/prompts.py`, run again.

## Usage

```
brain/.venv/bin/python eval/run_eval.py --trials 5
brain/.venv/bin/python eval/run_eval.py --trials 5 --thinking    # A/B for OPEN-QUESTIONS #4
```

- Trials run sequentially (one Ollama slot, predictable latency), each a fully independent run of the fixture case through the real agent loop and model, no server needed.
- Output lands in `eval/results/<timestamp>/`: per-trial run dirs (full `runs/`-style artifacts), `results.jsonl`, and `summary.md` with the hit rate and per-criterion table.
- `eval/results/` is gitignored; copy a `summary.md` into a commit or PR when it matters.

## Grading

`grading.py` encodes the ground-truth criteria as predicates over `report.json`.

- Required (pass = all true): names DB_HOST, names backend.env, identifies db.internal as the stale host, cites the config chunk, cites a log/journal error chunk, fix targets 127.0.0.1, fix restarts the backend, and does NOT blame the firewall (the planted near-miss trap).
- Bonus (tracked, not pass/fail): cross-machine evidence, citing the migration doc, explicitly ruling out the firewall, high confidence, fix script present.

A run that fails (no report) fails every criterion.

## Notes

- The trap criterion is inverted on purpose: ground truth says blaming the firewall rule is an outright fail, so `avoids_firewall_trap` is required.
- `--bundles` accepts any bundle directories, so future backup scenarios (port-in-use, firewall) get their own grading module and reuse the runner.
