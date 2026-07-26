# CLAUDE.md

Offline diagnostic "Brain": client machines are packaged into bundles by a bash collector, shipped to a GB10 box, indexed (BM25 + entity graph), and diagnosed by an agent loop on qwen3.5:122b via Ollama, with a live React UI showing the reasoning trail and graph.

## Read this first

- `SPEC.md` - architecture source of truth. Component specs, interfaces, data flow, build order.
- `CONTRACT.md` - bundle format (collector <-> Brain seam). Chunk ID grammar lives here.
- `API.md` - HTTP + SSE + graph schemas (Brain <-> UI seam). Report JSON schema lives here.
- `docs/decisions/` - ADRs; why things are the way they are. Do not re-litigate silently; add a new ADR.
- `docs/OPEN-QUESTIONS.md` - unsettled items. Do not build against these without a decision; settled items become ADRs and are removed from the list.
- `PLAN.md` - raw brainstorm, historical. Never build against it; where it disagrees with SPEC.md, SPEC.md wins.

## Layout

- `scenario/` - the deliberately broken system (Node backend, frontend, corpus docs, inject.sh/revert.sh, ground_truth.md). Owned by the scenario teammate. ground_truth.md never ships to client machines.
- `collector/collector.sh` - dependency-free bash; produces bundles per CONTRACT.md.
- `brain/` - Python 3.12 package (FastAPI). Key modules under `src/brain/`:
  - `llm.py` - the ONLY module that talks to Ollama (swap seam).
  - `ingest/` - inbox watcher, bundle validation, deterministic chunker.
  - `index/bm25.py` + `retrieval.py` - `search()`/`expand()`, the retrieval seam (embeddings swap in here).
  - `graph/` - one store, two layers: deterministic evidence layer, capped agent reasoning layer (ADR-0005).
  - `agent/` - JSON turn protocol, prompts, serial loop.
  - `events.py` - append-only per-run event log; SSE replays from it (ADR-0007).
  - `api/` - routes from API.md; also serves the built UI.
- `ui/` - React + sigma.js + TypeScript (Vite), built static, served by the brain service on port 8000. `npm run mock` demos the full UI with no backend.
- `integration/openclaw/` - operator layer (ADR-0011): `brainctl` CLI wrapping the Brain API + the OpenClaw `SKILL.md` + `install.sh`.
- `transport-layer/usb-transport/` - FDE client stick (transport owner): interactive setup + collectors (bash/PowerShell) writing to `client/outbox/`, and `workstation/receive_bundle.py`. The Brain's `ingest/usb.py` wraps the receiver and normalizes its bundle dialect to CONTRACT v1.0; USB-received runs default to full-context injection (ADR-0012).
- Runtime state is NOT in the repo: `~/brain/inbox/` and `~/brain/runs/` (`$BRAIN_HOME`).

## Conventions and invariants

- Contract-first: the two seams (CONTRACT.md, API.md) change only with a version bump and both owners' sign-off.
- Chunk IDs (`machine:path:Lstart-Lend`) are the universal currency: BM25 results, graph evidence, report citations, UI click-through. Never invent a second ID scheme.
- Chunking is deterministic; the graph may be rebuilt freely, chunk IDs may not change (ADR-0004).
- The agent loop is serial; parallelism is across cases and within-turn search fan-out only.
- Prompt discipline: append-only message arrays, nothing variable in the system prompt (prefix cache).
- The Brain never executes generated fix scripts (ADR-0010).
- All caps (graph nodes, label length, turn budget) are enforced in code, never just in prompts.
- Markdown in this repo: one sentence per line, plain `-` dashes.

## Environment

Brain: NVIDIA GB10, 120 GB unified memory, Ubuntu. Python 3.12.3, Node, Ollama with qwen3.5:122b (81 GB, primary) and qwen3-embedding:8b (future retrieval upgrade). Ports: brain 8000, Ollama 11434. `OLLAMA_NUM_PARALLEL=1` until measured (OPEN-QUESTIONS #3). OpenClaw is the operator-facing chat layer, integrated via the Brain API only (`integration/openclaw/`, ADR-0011); OpenShell is deferred to the future autofix phase.

## Commands

- Brain: `cd brain && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`; tests: `.venv/bin/python -m pytest`; run: `.venv/bin/brain serve` (also `brain ingest <bundle>`, `brain pull <host>`, `brain graph <run_id>`).
- UI: `cd ui && npm install && npm run build` (output ui/dist, auto-served by brain); dev: `npm run dev`; no-backend demo: `npm run mock`.
- Scenario: `scenario/run-local.sh` starts mock-db + backend + frontend locally; `scenario/inject.sh` plants the bug; `scenario/revert.sh` heals it.
- Collector: `./collector/collector.sh -o ~/bundles --services "backend" [--push <brain-host>]`.
- Operator: `integration/openclaw/brainctl health|bundles|usb|diagnose|watch|report`.
- Eval: `brain/.venv/bin/python eval/run_eval.py --trials 5 [--thinking]` - real-model reliability runs auto-graded against ground truth; results in `eval/results/` (gitignored).

## Current phase

Phase 1 base implementation is DONE and tested end to end (29 pytest tests, UI builds clean, scenario E2E-verified, real-model run exercised). Standing goal: keep improving SPEC/contracts until PLAN-vs-SPEC inconsistencies are all either resolved in ADRs or listed in OPEN-QUESTIONS.md; keep code and SPEC in lockstep as features land.
