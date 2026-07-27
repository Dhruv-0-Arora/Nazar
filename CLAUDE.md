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

- `scenario/` - the deliberately broken system (Node backend, portal, mockdb, corpus docs, scripts/, ground_truth.md). Owned by the scenario teammate. ground_truth.md never ships to client machines. Cedar Hollow clinic domain since ADR-0012; backend 8080, portal 3000, mockdb 5432, deployed under `/opt/clinic` and `/etc/clinic`. Carries inert distractors (`backend/pool.js` dead code, `backend/maintenance.js` advisory warnings, unread config keys) documented in `scenario/BREAKAGE.md`; a diagnosis landing on any of them is a graded failure, see `scenario/ground_truth.md`.
- `collector/collector.sh` - dependency-free bash; produces bundles per CONTRACT.md.
- `brain/` - Python 3.12 package (FastAPI). Key modules under `src/brain/`:
  - `llm.py` - the ONLY module that talks to Ollama (swap seam).
  - `ingest/` - inbox watcher, bundle validation, deterministic chunker.
  - `index/bm25.py` + `retrieval.py` - `search()`/`expand()`, the retrieval seam (embeddings swap in here).
  - `graph/` - one store, two layers: deterministic evidence layer, capped agent reasoning layer (ADR-0005).
  - `agent/` - JSON turn protocol, prompts, serial loop.
  - `events.py` - append-only per-run event log; SSE replays from it (ADR-0007).
  - `api/` - routes from API.md; also serves the built UI.
- `ui/` - React + @xyflow/react + zustand + Tailwind (Vite), built static, served by the brain service on port 8000 (fde-console, see ADR-0014). Header toggle (or `VITE_USE_MOCK=false npm run dev`) switches between fixtures and the live Brain; its ConsoleApi surface is served by the Brain's adapter `brain/api/console.py` (ADR-0015).
- `integration/openclaw/` - operator layer (ADR-0011): `brainctl` CLI wrapping the Brain API + the OpenClaw `SKILL.md` + `install.sh`.
- `transport-layer/usb-transport/` - FDE client stick (transport owner): `client/main.sh` is the one-script entry (setup once per device via `collect-<machine_id>.conf`, then collect), collectors write to `client/outbox/`. Workstation side: `atomic_transfer.py` deposits through a running brain's `/api/usb/receive` or directly via `ingest/usb.py` (never a raw copy into the inbox), then prints a BM25 + graph preview; `receive_bundle.py` is the underlying verifier the Brain's `ingest/usb.py` wraps. `ingest/usb.py` normalizes any bundle dialect to CONTRACT v1.0; USB-received runs default to full-context injection (ADR-0012).
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

Brain: NVIDIA GB10, 120 GB unified memory, Ubuntu. Python 3.12.3, Node, Ollama with qwen3.5:122b (81 GB, primary) and qwen3-embedding:8b (4.7 GB, the graph organizer's pair model, ADR-0016). `OLLAMA_MAX_LOADED_MODELS=2`; `OLLAMA_NUM_PARALLEL=1` until measured (OPEN-QUESTIONS #3). Ports: brain 8000, Ollama 11434. Stage-3 curator (`BRAIN_CURATOR_MODEL`, default off) is agreed to default to nemotron-cascade-2:30b when built. OpenClaw is the operator-facing chat layer, integrated via the Brain API only (`integration/openclaw/`, ADR-0011); OpenShell is deferred to the future autofix phase.

## Commands

- Brain: `cd brain && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`; tests: `.venv/bin/python -m pytest`; run: `.venv/bin/brain serve` (also `brain ingest <bundle>`, `brain pull <host>`, `brain graph <run_id>`).
- UI: `cd ui && npm install && VITE_USE_MOCK=false npm run build` (output ui/dist, auto-served by brain, defaults to live); dev: `npm run dev` (defaults to fixtures; header toggle or `VITE_USE_MOCK=false` switches to the live Brain).
- Linked interactive test: see `docs/RUNBOOK-LINKED-TEST.md` (single-machine variant and MacBook-over-ethernet variant).
- Scenario: `scenario/scripts/run-local.sh` starts mockdb + backend + portal locally; `ENV_FILE=.local/backend.env scenario/scripts/inject.sh` plants the fault; `revert.sh` heals it. `scripts/build.sh` builds `dist/`; `deploy/install.sh laptop-a|laptop-b` installs under systemd; `scripts/nuke.sh --target /opt/clinic` strips hints before any evaluation run.
- Collector: `./collector/collector.sh -o ~/bundles --services "backend" [--push <brain-host>]`.
- Operator: `integration/openclaw/brainctl health|bundles|usb|diagnose|watch|report`.
- Eval: `brain/.venv/bin/python eval/run_eval.py --trials 5 [--thinking]` - real-model reliability runs auto-graded against ground truth; results in `eval/results/` (gitignored).

## Current phase

Phase 1 base implementation is DONE and tested end to end (29 pytest tests, UI builds clean, scenario E2E-verified, real-model run exercised). Standing goal: keep improving SPEC/contracts until PLAN-vs-SPEC inconsistencies are all either resolved in ADRs or listed in OPEN-QUESTIONS.md; keep code and SPEC in lockstep as features land.
