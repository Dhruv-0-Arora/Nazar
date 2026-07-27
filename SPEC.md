# SPEC.md - Technical Specification (Architecture / Foundation)

Status: post-hackathon snapshot.
This document is the source of truth for the system architecture.
Decision rationale is tagged inline as ADR-00NN; the numbered ADR files were not carried into this repo, so the tags are rationale markers, not links.

## 1. What we are building

An offline "Brain" appliance that diagnoses broken machines it has never seen.
Client machines run a dependency-free collector script that packages system state, logs, configs, and a local doc corpus into a bundle.
Bundles reach the Brain over SSH (or USB when the network itself is the casualty).
The Brain chunks and indexes everything, builds an entity graph across machines, and runs an agent loop against a local LLM (qwen3.5:122b via Ollama) that searches, traverses the graph, rules hypotheses in and out, and emits a cited diagnosis with an action plan.
A live UI shows the reasoning trail and the graph mutating in real time.

The demo scenario: a two-machine fake company system (Node backend on laptop A, frontend on laptop B) sabotaged by a known bug (stale DB host env var), plus a planted doc corpus containing one genuinely useful runbook, one near-miss past ticket, and noise.

## 2. Components and ownership

| Component | Milestone | Directory | Owner |
|---|---|---|---|
| Scenario package (broken apps, corpus, inject/revert) | M0 | `scenario/` | teammate (scenario owner) |
| Client collector | M2 | `collector/` | us |
| Transport + contracts | C1/C2 | `CONTRACT.md` | us |
| Brain service (ingest, index, graph, agent, API) | M3/M4 | `brain/` | us |
| UI (React + @xyflow/react) | M4.1/M4.2 | `ui/` | us / teammate (UI owner) |
| OpenClaw operator layer | M4.3 | `integration/openclaw/` | us |

"Us" here is the architecture/foundation portion this spec covers in full detail.
The scenario package is specified only at its interfaces (what the collector must capture, what ground_truth.md must contain).

## 3. Repository layout

```
whackathon/
├── README.md                   project overview
├── SPEC.md                     this file - architecture source of truth
├── CONTRACT.md                 seam 1: collector <-> Brain bundle contract
├── API.md                      seam 2: Brain <-> UI HTTP/SSE contract
├── AIRGAP-SSH.md               talking to a machine over nothing but a cable
├── scenario/                   M0 - the broken system under test
│   ├── backend/                Node service that stays "running" while broken (the patient)
│   ├── mockdb/                 the records service the backend talks to
│   ├── frontend/               portal app on the other laptop (the symptom)
│   ├── corpus/                 authored markdown docs + placement.json
│   ├── scripts/                inject.sh / revert.sh / build.sh / run-local.sh / deploy.sh / nuke.sh
│   ├── deploy/                 systemd units + install.sh
│   ├── BREAKAGE.md             fault catalogue and difficulty ladder
│   └── ground_truth.md         grading key - NEVER deployed to client machines
├── collector/
│   └── collector.sh            single dependency-free bash script (M2)
├── brain/                      Python 3.12 package (M3/M4)
│   ├── pyproject.toml
│   ├── src/brain/
│   │   ├── config.py           env-var config, paths, model name
│   │   ├── cli.py              console entry: brain serve | pull <host..> | ingest <path> | graph ..
│   │   ├── llm.py              the ONLY module that talks to Ollama
│   │   ├── ingest/
│   │   │   ├── watcher.py      inbox polling + case grouping + usb auto-scan
│   │   │   ├── bundle.py       CONTRACT.md validation, manifest parsing
│   │   │   ├── usb.py          usb-stick intake: runs receive_bundle.py, normalizes (ADR-0012)
│   │   │   ├── ethernet.py     cable link watcher: fe80 peer discovery + auto-pull
│   │   │   └── chunker.py      deterministic structure-aware chunking
│   │   ├── index/
│   │   │   └── bm25.py         rank_bm25 wrapper, search(query, k)
│   │   ├── graph/
│   │   │   ├── model.py        Node/Edge dataclasses, ID schemes, caps
│   │   │   ├── build.py        structural + extracted tiers (deterministic)
│   │   │   ├── store.py        networkx wrapper, delta emission, snapshots
│   │   │   ├── organize.py     embedding pair-model: relates edges + clusters (ADR-0016)
│   │   │   └── cli.py          `brain graph` subcommands (inspect a run's graph)
│   │   ├── retrieval.py        search() + expand() facade used by the agent
│   │   ├── agent/
│   │   │   ├── protocol.py     JSON action schema, parsing, retries
│   │   │   ├── prompts.py      system + turn templates (static, cache-safe)
│   │   │   └── loop.py         the serial turn loop, budgets, fan-out
│   │   ├── events.py           append-only event log, seq numbers
│   │   ├── runs.py             run registry: run_id, meta.json, lifecycle, live-run state
│   │   ├── report.py           report.json validation + markdown rendering
│   │   └── api/
│   │       ├── server.py       FastAPI app, static UI mount, lifespan
│   │       ├── routes.py       endpoints from API.md, SSE tailer
│   │       └── console.py      ConsoleApi adapter over the runs model (ADR-0015)
│   └── tests/
│       ├── fixtures/
│       │   ├── bundle-laptop-a-20260726T120000Z/   hand-crafted bundle per CONTRACT.md
│       │   └── bundle-laptop-b-20260726T120100Z/   its cross-machine sibling
│       └── test_*.py
├── ui/                         React + @xyflow/react, built to static assets
│   └── src/
│       ├── api/                ConsoleApi client (mock/live/fixtures) - see ADR-0014
│       ├── store/               zustand store, single console snapshot
│       ├── panels/              Agent, Graph, Logs, Process
│       └── components/          Header, MachineRail
├── integration/
│   └── openclaw/               operator-layer skill: SKILL.md + brainctl (section 14)
├── transport-layer/
│   └── usb-transport/          FDE client stick (transport owner): setup + collectors
│       ├── client/             ships on the stick; outbox/ receives collected bundles
│       └── workstation/        receive_bundle.py - verifier the Brain's usb intake wraps
├── eval/                       reliability harness: run_eval.py + grading.py (section 10)
└── .gitignore                  ignores runs/, inbox contents, node_modules
```

Runtime state lives outside the repo under `$BRAIN_HOME` (default `~/brain/`):

```
~/brain/
├── inbox/                      bundle deposits (CONTRACT.md section 5)
│   ├── .staging/
│   └── rejected/
└── runs/                       one directory per run (section 10)
```

Note: the scenario's frontend and backend live under `scenario/` because the Brain's UI also needs a home and two things named "frontend" guarantees confusion.
See ADR-0001.

## 4. Runtime topology

```
laptop A (patient)          laptop B (symptom)              Brain (GB10, 120 GB)
┌──────────────────┐        ┌──────────────────┐        ┌──────────────────────────┐
│ scenario backend │◄──X────│ scenario frontend│        │ Ollama :11434            │
│ (Node, broken)   │        │                  │        │   qwen3.5:122b           │
│ collector.sh     │        │ collector.sh     │        │ brain service :8000      │
│ /opt/company-docs│        │ /opt/company-docs│        │   FastAPI + static UI    │
└────────┬─────────┘        └────────┬─────────┘        │ ~/brain/inbox, ~/brain/  │
         │  bundle (scp/SSH/USB)     │                  │   runs                   │
         └──────────────┬────────────┘                  └──────────▲───────────────┘
                        └──────────────────────────────────────────┘
                                             demo operator's browser -> http://brain:8000/
```

- Two processes on the Brain: Ollama and the brain service. Nothing else.
- The UI is static files served by the brain service; the browser talks only to `:8000`.
- Transport modes (shared LAN SSH pull primary, scp push fallback, USB tertiary) are a connectivity choice, not an architecture choice; all deposit identical bundles per CONTRACT.md section 5.

## 5. End-to-end data flow

```
inject.sh ──► broken backend ──► symptoms (logs, dead requests)
collector.sh ──► bundle-<machine>-<ts>/ ──transport──► ~/brain/inbox/
inbox watcher ──► validate (bundle.py) ──► case = {bundle_ids}
case ──► [1 CHUNKER] ──► chunk store ──┬──► [2 BM25] inverted index
                                       └──► [3 GRAPH BUILD] evidence layer
agent loop (serial turns) ──► search()/expand()/graph ops ──► events.jsonl
final turn ──► report.json + report.md ──► runs/<run_id>/
FastAPI ──► SSE replay+live ──► React UI (query trail + live graph + report)
```

Numbered walk-through:

1. `inject.sh` plants the bug on laptop A and restarts the service. `systemctl` still reports running; requests fail; errors accumulate in the app log. The subtlety is the point.
2. An operator runs `collector.sh` on each laptop. It writes a bundle to `~/bundles/` per CONTRACT.md and (in push mode) scp's it to the Brain. In pull mode the operator runs `brain pull <host...>` on the Brain, which fetches each client's `manifest.json` first, then the full bundle. At single-digit MB we always pull whole; the manifest still matters because it tells the Brain what it is looking at.
3. The watcher polls the inbox every 2 s. When a new valid bundle appears it starts a debounce window (default 10 s). Every bundle that lands inside the window joins the same case. This is what makes cross-machine synthesis possible: laptop A's and laptop B's bundles are indexed together. See ADR-0006.
4. Ingest runs the three-stage pipeline (section 6). Chunking is deterministic; BM25 and the evidence graph are built once per run and never rebuilt mid-run.
5. The agent loop (section 7) runs at most `BRAIN_MAX_TURNS` (default 5) retrieval turns plus one conclude turn, emitting events throughout.
6. `report.py` validates the model's final JSON against the schema in API.md section 3, strips citations that do not resolve in the chunk store, renders markdown, and writes everything to `runs/<run_id>/`.
7. The UI, connected via SSE from the moment the run was created, has been rendering the trail and graph deltas all along; on `done` it fetches the full report.

## 6. Ingest pipeline (Brain-side, per case)

All indexing happens on the Brain, never on clients (the sick machine may be resource-starved; the Brain has the model).

### 6.1 Chunker (deterministic, structure-aware)

`chunker.chunk_bundle(bundle_dir, manifest) -> list[Chunk]`

```python
@dataclass
class Chunk:
    id: str            # CONTRACT.md section 6 grammar
    text: str          # verbatim source material
    machine_id: str
    file_path: str     # bundle-relative
    span: tuple[int, int]
    kind: Literal["evidence", "knowledge"]   # docs/ -> knowledge, else evidence
    bundle_id: str
    mentions: list[str] = field(default_factory=list)   # node IDs, filled by the graph builder
```

Every field except `mentions` is set once by the chunker and never changed; `mentions` is populated during graph build (section 6.3).

Per-file-type strategy:

| Input | Strategy |
|---|---|
| `app_logs/*`, `services/*/journal.txt` | split on error-block boundaries (timestamp/severity lines); fallback fixed 40-line windows |
| `services/*/config/*`, `services/*/status.txt` | whole file if <= 60 lines, else per stanza |
| `docs/**/*.md` | split per markdown heading |
| `system.txt`, `network.txt` | one chunk per `### CMD:` section (CONTRACT.md section 4) |
| `processes.txt`, `packages.txt`, `manifest.json` | whole file |

Chunking is deterministic and stable because it is the retrieval substrate and the citation system.
Graph extraction is fuzzy and iterative; it must be able to rebuild ten times without invalidating chunk IDs.
This is why chunks and nodes are distinct objects (see ADR-0004).

The chunk store is an in-memory dict `chunk_id -> Chunk`, serialized once to `runs/<run_id>/chunks.jsonl` after the graph build so `mentions` is populated.

### 6.2 BM25 index

`bm25.Index.build(chunks)`, `index.search(query: str, k: int) -> list[ScoredChunk]` where `ScoredChunk = (chunk_id, score)`.

- Tokenization: lowercase, split on non-alphanumerics, keep dotted/colon tokens intact once (so `db.internal` and `ECONNREFUSED` both survive as searchable tokens alongside their fragments).
- Implementation: `rank_bm25.BM25Okapi`, roughly 20 lines of wrapper.
- `retrieval.search()` is the single retrieval seam. Embeddings (qwen3-embedding:8b is already pulled on the Brain) swap in behind this signature later; nothing upstream changes.

### 6.3 Graph builder (evidence layer)

Input is the chunk store, never the raw bundles.
Nodes are created by reading chunks, and every node records the chunk IDs it was born from at the moment of extraction.
There is no reconciliation step; the chunk<->node link is a byproduct of extraction itself:

```python
for chunk in chunk_store:
    for match in extract_entities(chunk.text):        # regexes: IP, port, hostname, env key, error class, ticket id
        node = graph.get_or_create(match.type, match.value)
        node.evidence.append(chunk.id)
        chunk.mentions.append(node.id)
```

Two deterministic tiers:

- Structural tier (zero inference): `machine`, `service`, `file` nodes straight from the manifest and directory layout; edges `file -located_on-> machine`, `service -has_config-> file`, and chunks linked to files via metadata.
- Extracted tier (regex): `ip`, `port`, `host`, `env_var`, `error`, `ticket` nodes with `mentions` edges back to chunks. The `ss -tlnp` section of `network.txt` additionally yields `service -listens_on-> port` edges.
- Cross-reference pass (the money edge): when a config chunk on machine B mentions an IP/port/hostname that resolves to machine A, emit `service -talks_to-> service`. When an extracted `host` matches no machine and no interface in any bundle, mark the `talks_to` edge `dangling: true`. For the demo scenario, that dangling edge IS the bug rendered as topology.

The optional LLM concept tier is not cut but subsumed: it IS the reasoning layer (section 7), living in the same store (see ADR-0005).

Store: `networkx.MultiDiGraph` in memory wrapped by `graph/store.py`, which is the only mutation path and therefore the single place that enforces caps, assigns edge IDs, and emits `event: graph` deltas.
Serialized to `runs/<run_id>/graph.json` (schema in API.md section 4).

## 7. Agent loop

Serial by design: turn N+1 depends on turn N. Never parallelize the loop itself; parallelize within a turn.

### 7.1 Turn protocol

`llm.py` is the only module that calls Ollama (swap seam for vLLM/llama.cpp).
Intermediate turns request strict JSON (Ollama `format: json`), thinking disabled.
The model emits:

```json
{
  "thought": "stale DB host suspected; env file should confirm",
  "actions": [
    {"op": "search", "query": "backend env DB host", "k": 5},
    {"op": "search", "query": "ECONNREFUSED 5432", "k": 5},
    {"op": "expand", "chunk_ids": ["laptop-a:app_logs/backend.log:L120-L160"], "hops": 1},
    {"op": "graph", "delta": {"op": "add_node", "node": {"layer": "reasoning", "type": "hypothesis", "label": "stale DB host in backend.env"}}},
    {"op": "graph", "delta": {"op": "set_status", "id": "hyp:1", "status": "ruled_out"}}
  ],
  "conclude": false
}
```

Node IDs are assigned by the store and returned in the next feedback message, so a `set_status` (or an edge endpoint) may only reference IDs from earlier turns; in this example `hyp:1` was created in a previous turn.
Ops referencing unknown IDs are rejected with an error in the feedback.

The loop executes all `search` actions concurrently (BM25 is CPU-cheap; within-turn fan-out), applies graph deltas through the store (which returns assigned IDs or cap errors), executes `expand`, and feeds results back as the next user turn:

```json
{
  "results": [
    {"query": "backend env DB host", "chunks": [{"cid": "...", "file": "...", "score": 8.1, "text": "..."}]},
    {"expanded": {"subgraph": "backend -talks_to-> host:db.internal [DANGLING]", "chunks": [...]}}
  ],
  "graph_results": [{"assigned_id": "hyp:1"}, {"ok": true}],
  "turns_remaining": 3
}
```

Retrieved chunk text is truncated to 1200 chars per chunk in the feedback, deduped across the turn, each labeled with its chunk ID and the path that surfaced it (`via bm25` vs `via graph`).

### 7.2 retrieval.expand()

`expand(chunk_ids, hops=1) -> Expansion(subgraph, extra_chunks)`

1. Collect the `mentions` of each input chunk -> seed nodes.
2. Traverse `hops` (1-2) along evidence-layer edges -> subgraph.
3. Collect `evidence` chunk IDs from every subgraph node, minus chunks already seen this turn -> extra chunks.
4. Render the subgraph compactly as text (`backend -talks_to-> db.internal [DANGLING: no machine matches]`).

This is the move BM25 cannot make: lexical search finds the symptom chunk, the graph walks `has_config` to the cause chunk that shares no vocabulary with the query.

### 7.3 Turn budget and termination

- Turn 1 input: manifest summaries + `system.txt` digests for every bundle in the case + the question. For USB-sourced cases (full-context mode, ADR-0012), turn 1 additionally carries every chunk verbatim, chunk-ID delimited, evidence before knowledge, capped by `BRAIN_FULL_CTX_CHARS`; `llm.py` pins `options.num_ctx` (`BRAIN_NUM_CTX`) so the injection cannot silently overflow Ollama's window.
- Max `BRAIN_MAX_TURNS` (default 5) action turns; the `turns_remaining` counter is in every feedback message; at 0 the loop forces `conclude`.
- Conclude turn: thinking optionally enabled, streaming on, model emits the report JSON (API.md section 3). `report.py` validates; on schema failure the loop retries once with the validation errors appended; on second failure the run is marked `failed` with the raw output preserved in `runs/`.
- Malformed intermediate JSON: re-prompt with the parse error, max 2 retries per turn, then skip the turn (counts against budget).
- Ollama timeouts: 120 s per call; one retry; then run `failed` with an `error` event.

### 7.4 Prefix-cache discipline

- The message array is append-only; earlier turns are never mutated.
- Nothing variable (timestamps, run IDs) in the system prompt.
- Log `eval_count` / `eval_duration` from every Ollama response into `runs/<run_id>/metrics.json` so token throughput is measured, not assumed.

## 8. UI (M4.1 / M4.2)

Stack: React + @xyflow/react (SVG/HTML graph canvas) + zustand + Tailwind, Vite build, output copied into the FastAPI static mount.
Contract: API.md. The current `ui/` (fde-console, folded in per ADR-0014) speaks the `ConsoleApi` shape (`/api/snapshot`, `/api/chat`, `/api/context`, `/api/stream`), which the Brain serves as an adapter over the runs model in `brain/api/console.py` (ADR-0015).
The UI is buildable against its own fixtures (`src/api/fixtures.ts`) regardless of backend state.

Panels (single console screen, not a multi-view runs list, per the fde-console layout actually delivered):

- Header: run phase, elapsed/ETA, fixtures/live source toggle.
- MachineRail: persistent left rail of known machines; click to filter every panel to one machine.
- AgentPanel: chat-style trace of `TraceEvent`s (thought/query/retrieval/answer/user) plus a message box that streams the agent's reply token by token.
- GraphPanel: @xyflow/react canvas of `Chunk` nodes and `GraphEdge`s, laid out by the hand-rolled force simulation in `src/lib/layout.ts`; node click opens the evidence chunk - this is the "each node opens the actual file from the bundle" requirement.
- LogsPanel: `LogEntry` list, filterable by machine/severity/source.
- ProcessPanel: `AgentStep` list, one row per unit of agent work, scoped to a machine.

Graph rendering policy (still binding, mechanism-agnostic): the reasoning layer plus every evidence node reachable from it within 1 hop is always shown; the rest of the evidence layer appears only through expansion clicks, keeping the visible graph within the caps meaningful (see ADR-0005).

Client-side rules (binding): rAF-batched token flush; seq-number dedupe on SSE reconnect; thinking tokens collapsed by default.

## 9. Concurrency model (M3.5)

- Across cases: the watcher dispatches each case to a worker task; runs are fully independent (own chunk store, index, graph, event log). Bounded by a semaphore equal to `OLLAMA_NUM_PARALLEL`.
- Within a turn: all N search queries fan out concurrently.
- The loop itself is serial.
- Ollama config: `OLLAMA_MAX_LOADED_MODELS=2` - the graph organizer's embedding pair-model (`qwen3-embedding:8b`, 4.7 GB) stays resident beside the 81 GB primary; headroom measured at ~40 GB (ADR-0016). `OLLAMA_NUM_PARALLEL` starts at 1: a second KV cache for the 122b is still unverified headroom; raise to 2 only if measured. Predictable serial latency beats swapping mid-demo.
- Graph organizer concurrency: a per-run worker thread, event-driven (post-ingest, post-turn, post-conclude) with dirty-flag coalescing; it never blocks or delays the diagnosing model's turns and its output is never agent-visible (ADR-0016).

## 10. runs/ directory (eval harness for free)

```
~/brain/runs/<run_id>/
├── meta.json          run_id, case bundle_ids, question, status, timestamps
├── bundles/           verbatim copies of the case's bundles
├── chunks.jsonl       serialized chunk store
├── graph.json         final graph snapshot (both layers)
├── events.jsonl       append-only event log (SSE source of truth)
├── metrics.json       per-turn eval_count/eval_duration, totals
├── report.json        validated report
├── report.md          rendered report (elapsed time in the header)
└── raw/               unvalidated model outputs per turn (debugging)
```

Grading: `eval/run_eval.py` runs N independent real-model trials of a case and auto-grades each `report.json` against a scenario-specific criteria set (`eval/grading.py --scenario fixture|clinic`; the clinic key encodes `scenario/ground_truth.md`); iterate `prompts.py` until the hit rate holds.
`BRAIN_THINK_FINAL` (config) toggles thinking on the conclude turn; the harness's `--thinking` flag drives that A/B.
Every run is a future eval case and fine-tuning example.

## 11. Error handling summary

| Failure | Behavior |
|---|---|
| invalid bundle | moved to `inbox/rejected/` + reason file, `state: rejected` in `/api/bundles` |
| Ollama down at run start | run `failed` fast, `error` event, healthz shows it |
| model emits bad JSON | 2 re-prompts per turn, then skip turn |
| report fails schema | 1 retry with errors, then run `failed`, raw preserved |
| graph cap overflow | op rejected, error returned to model in next turn |
| SSE client disconnect | reconnect + `Last-Event-ID` replay from events.jsonl |
| brain service crash | one systemd unit runs the whole service (the watcher is an asyncio task inside the FastAPI lifespan, so "two processes on the Brain" stays true); on restart the inbox rescan is idempotent (processed bundle ids recorded in runs/) and in-flight runs are marked `failed` |

## 12. Environment and versions

| Thing | Version / value | Note |
|---|---|---|
| Python | 3.12.x (3.12.3 already on the Brain) | pinned in pyproject; no new install needed |
| Python deps | fastapi, uvicorn, rank_bm25, networkx, httpx, pydantic, numpy | all pure-python or wheel-safe on 3.12; SSE is hand-rolled over events.jsonl |
| Node | already installed | UI build only; not needed at runtime on clients |
| Ollama models | qwen3.5:122b (primary), qwen3-embedding:8b (graph organizer pair-model, ADR-0016) | already pulled |
| collector.sh | bash + coreutils only | zero dependencies, fits on a USB stick |
| Ports | brain 8000, Ollama 11434 | one UI-facing port |

## 13. Build order and parallel tracks

1. Minute 0-10: this spec's two seams already exist (CONTRACT.md, API.md); both owners sign off.
2. Track A (Brain): hand-craft the `brain/tests/fixtures/` bundles per the contract -> chunker -> BM25 -> agent loop end-to-end with search only -> graph as pure upgrade (the loop degrades gracefully without `expand`).
3. Track B (UI): mock JSON per API.md -> RunsList -> LiveRun trail -> graph deltas.
4. Track C (scenario owner): backend/frontend apps -> inject/revert -> corpus + placement -> ground_truth.
5. Track D (collector): collector.sh against a healthy machine -> against the bugged one -> eyeball that the env var error is captured in the bundle.
6. Integration: real bundle replaces the fixture; pre-demo checklist (SSH keys both ways, inbox permissions, one dry-run scp, static IPs pinned for cable mode).

## 14. Operator layer: OpenClaw (M4.3)

Required scope per ADR-0011: OpenClaw is the chat-facing operator layer; OpenShell is deferred to the autofix phase; NemoClaw is out of scope.

- `integration/openclaw/brainctl`: a small bash CLI wrapping the Brain API (curl only, no other deps): `brainctl health`, `brainctl bundles`, `brainctl diagnose [bundle_id...] [-q question]`, `brainctl runs`, `brainctl watch <run_id>` (follows the SSE stream, prints the trail), `brainctl report <run_id>` (prints report markdown), `brainctl usb`, `brainctl reset`. Reads `BRAIN_URL` (default `http://127.0.0.1:8000`).
- `integration/openclaw/SKILL.md`: the OpenClaw skill definition teaching the agent when and how to use `brainctl`, with the workflow (list bundles -> diagnose -> watch -> summarize report with citations) and guardrails (never apply fixes; present `proposed_fix_script` for human review per ADR-0010).
- `integration/openclaw/install.sh`: copies/symlinks the skill into the local OpenClaw skills directory and `brainctl` onto PATH.
- Boundary rules: OpenClaw consumes the Brain API exactly as the UI does, gains no private endpoints, and never talks to Ollama about diagnosis; the Brain remains the only diagnostic reasoner.

## 15. Risks

- 81 GB model on 120 GB unified memory: concurrency and thinking-mode budgets are guesses until `metrics.json` says otherwise. Measure on day one.
- Regex entity extraction quality gates the money edge; the fixture bundle must exercise every extractor.
- The demo depends on both laptops' bundles landing in one case; the debounce window must be generous and the UI must show which bundles a run includes.
