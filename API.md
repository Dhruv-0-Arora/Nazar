# API.md - Brain Service API Contract (v1.0)

This is the interface between the Brain service (M3/M4, Python/FastAPI) and the UI (M4.1, React), as implemented by `brain/api/routes.py`.
The UI builds against mocked JSON matching these schemas and never talks to Ollama directly.
Any change requires a version bump and sign-off from both owners.

Note: the `ui/` in the repo (fde-console, [ADR-0014](docs/decisions/ADR-0014-ui-swap-fde-console.md)) speaks the ConsoleApi surface (`/api/snapshot`, `/api/chat`, `/api/context`, `/api/stream`), served by the Brain as an adapter over the runs model below - see [ADR-0015](docs/decisions/ADR-0015-console-adapter.md).
The runs API in this document remains the canonical contract; the console surface's shapes are defined by `ui/src/api/types.ts` and implemented in `brain/src/brain/api/console.py`.

Base URL: `http://<brain-host>:8000`.
The React build is served statically by the same FastAPI process at `/`, so there is one process and one port.
All API routes live under `/api/` to avoid colliding with UI routes.

## 1. Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/healthz` | liveness + Ollama reachability |
| GET | `/api/bundles` | list bundles known to the inbox |
| POST | `/api/runs` | start a diagnosis run on a set of bundles |
| POST | `/api/usb/receive` | receive + normalize bundles from a client USB stick |
| GET | `/api/runs` | list runs with status |
| GET | `/api/runs/{run_id}` | full run detail incl. report when done |
| GET | `/api/runs/{run_id}/stream` | SSE live event stream |
| GET | `/api/runs/{run_id}/graph` | current graph snapshot (nodes + edges) |
| GET | `/api/runs/{run_id}/organization` | organizer overlay: clusters + relates edges (ADR-0016) |
| GET | `/api/runs/{run_id}/chunks/{chunk_id}` | raw chunk text + metadata |

### GET /api/healthz

```json
{"status": "ok", "ollama": "ok", "model": "qwen3.5:122b", "version": "1.0.0"}
```

`ollama` is `"ok"` or an error string. Status 200 either way; the UI renders a warning banner when Ollama is down.

### GET /api/bundles

```json
[
  {
    "bundle_id": "bundle-laptop-a-20260726T183000Z",
    "machine_id": "laptop-a",
    "created_at": "2026-07-26T18:30:00Z",
    "services": ["backend"],
    "state": "ready"
  }
]
```

`state`: `ready` | `ingesting` | `rejected`.
For `rejected` bundles, `machine_id`, `created_at`, and `services` are `null` when the manifest was missing or unparseable, and an additional `reason` field carries the contents of `reject-reason.txt`.

### POST /api/runs

Request:

```json
{
  "bundle_ids": ["bundle-laptop-a-...", "bundle-laptop-b-..."],
  "question": "why is the frontend getting connection refused?"
}
```

- `bundle_ids` optional. Default: every `ready` bundle not yet part of a run.
  A run always operates on a case, i.e. a set of bundles indexed together (see [ADR-0006](docs/decisions/ADR-0006-case-based-runs.md)).
- `question` optional. Default prompt asks for general diagnosis of the collected machines.
- `full_context` optional tri-state (see [ADR-0012](docs/decisions/ADR-0012-usb-intake-full-context.md)): omitted/`null` = auto (on when any bundle arrived via USB, detected from its `receipt.json`); `true`/`false` force it. When on, the entire case content is injected into the agent's first message, chunk-ID delimited.

Response: `202` with `{"run_id": "run-20260726T184501Z-a1b2", "full_context": true}`.

### POST /api/usb/receive

Request: `{"source": "/media/fde/STICK"}`; `source` optional (default: auto-discover mounted client sticks).
The source may be the stick root, the `client/` folder, or the `outbox` itself.
Runs the transport layer's `receive_bundle.py`, normalizes verified bundles to this contract, and deposits them atomically.

Response `200`:

```json
{"received": ["bundle-bk608-20260726T212139Z"], "skipped": [], "errors": [], "summary": "<receiver stdout>"}
```

`404` when no source is found or nothing could be received (detail carries the errors).

### GET /api/runs

```json
[
  {
    "run_id": "run-20260726T184501Z-a1b2",
    "status": "running",
    "bundle_ids": ["bundle-laptop-a-...", "bundle-laptop-b-..."],
    "question": "...",
    "started_at": "2026-07-26T18:45:01Z",
    "elapsed_s": 12.4,
    "turns_completed": 3
  }
]
```

`status`: `queued` | `running` | `done` | `failed`.

### GET /api/runs/{run_id}

Everything from the list entry, plus when `status` is `done`:

```json
{
  "...": "...",
  "report": { "see": "section 3" },
  "report_markdown": "# Diagnosis...",
  "metrics": {
    "turns": 5,
    "queries_issued": 9,
    "chunks_retrieved": 31,
    "tokens_generated": 1450,
    "elapsed_s": 19.4
  }
}
```

When `failed`: an `error` string instead of `report`.

## 2. SSE stream: GET /api/runs/{run_id}/stream

- `Content-Type: text/event-stream`, one connection, multiplexed event types.
- Every event carries `id: <seq>` where `seq` is a monotonically increasing integer per run.
- Events are persisted to `runs/<run_id>/events.jsonl` as they are emitted.
  On connect (or reconnect with `Last-Event-ID`), the server replays persisted events after the given seq, then continues live.
  The client dedupes by seq as a second line of defense.
- A first connection may start mid-stream with `?from_seq=<seq>` (e.g. right after fetching a graph snapshot, whose `seq` says where to resume).
  On automatic reconnect the `Last-Event-ID` header takes precedence over `from_seq`.
- The stream ends after `done` or `error`.
  Connecting to a finished run replays the whole event log, which gives post-hoc replay for free.

Event types and payloads:

```
event: status   data: {"turn": 3, "state": "searching" | "expanding" | "thinking" | "reporting"}
event: query    data: {"turn": 2, "q": "backend.env DB host", "k": 5}
event: chunk    data: {"turn": 2, "cid": "laptop-a:services/backend/config/backend.env:L1-L12",
                       "file": "services/backend/config/backend.env", "score": 8.1,
                       "via": "bm25" | "graph"}
event: graph    data: {"op": "add_node" | "add_edge" | "set_status", ...}   // section 4 schemas
event: token    data: {"turn": 6, "text": "The root cause is", "kind": "report" | "thinking"}
event: done     data: {"run_id": "...", "elapsed_s": 19.4}
event: error    data: {"message": "ollama timeout on turn 3"}
event: organize data: {"phase": "ingest" | "turn" | "conclude" | "coalesced", "clusters": 4, "edges": 87}
                (or {"phase": ..., "error": "..."} when the embedder is unavailable; see ADR-0016)
```

UI guidance (binding, from PLAN M4.2):

- Lead with the query/chunk trail; only the final turn streams `token` events into a visible report pane.
- Flush token buffers on `requestAnimationFrame`, not per token.
- `kind: "thinking"` tokens render collapsed by default.

## 3. Report JSON schema

Produced by the agent's final turn, validated by the Brain before the run is marked `done`.

```json
{
  "root_cause": "backend.env DB_HOST points at db.internal which resolves to nothing on this network",
  "confidence": "high",
  "affected_machines": ["laptop-a"],
  "evidence": [
    {"chunk_id": "laptop-a:services/backend/config/backend.env:L1-L12", "why": "DB_HOST=db.internal set here"},
    {"chunk_id": "laptop-a:app_logs/backend.log:L120-L160", "why": "ECONNREFUSED to db.internal:5432 repeating"}
  ],
  "ruled_out": [
    {"hypothesis": "firewall blocking 5432", "why": "iptables section shows no reject rules", "chunk_id": "laptop-a:network.txt:L40-L55"}
  ],
  "action_plan": [
    {"step": 1, "action": "set DB_HOST to 192.168.50.10 in backend.env", "command": "sed -i ...", "risk": "low"},
    {"step": 2, "action": "restart backend service", "command": "systemctl restart backend", "risk": "low"}
  ],
  "proposed_fix_script": "#!/usr/bin/env bash\n..."
}
```

- `confidence`: `high` | `medium` | `low`.
- Every claim must cite a `chunk_id` that exists in the chunk store; the Brain validates and strips dangling citations.
- `proposed_fix_script` is advisory output only. The Brain never executes it (see [ADR-0010](docs/decisions/ADR-0010-fix-scripts.md)).
- `action_plan` is the future autofix API surface; keep it strictly structured.

## 4. Graph schemas

Shared by `GET /api/runs/{run_id}/graph` (snapshot), `event: graph` (deltas), and `runs/<run_id>/graph.json` (persisted artifact).
One store, two layers (see [ADR-0005](docs/decisions/ADR-0005-two-layer-graph.md)).

Node:

```json
{
  "id": "port:5432",
  "layer": "evidence" | "reasoning",
  "type": "machine|service|file|host|ip|port|env_var|error|ticket|hypothesis|finding",
  "label": "port 5432",
  "status": "open" | "confirmed" | "ruled_out",
  "evidence": ["laptop-a:services/backend/config/backend.env:L1-L12"],
  "attrs": {}
}
```

- Evidence-layer node IDs are deterministic: `<type>:<value>` (e.g. `host:db.internal`, `machine:laptop-a`).
  Exception: file node IDs use `file:<machine_id>/<path>` with `/` separating machine from path (e.g. `file:laptop-a/services/backend/config/backend.env`) to keep the chunk-ID grammar unambiguous.
- Reasoning-layer node IDs are assigned by the store: `hyp:1`, `hyp:2`, `finding:1`.
- `status` only applies to reasoning nodes. `label` is capped at 80 chars, enforced by the store.
- `evidence` lists chunk IDs; the UI resolves them via `GET .../chunks/{chunk_id}` on click.

Edge:

```json
{"id": "e42", "from": "service:backend", "to": "host:db.internal", "rel": "talks_to", "attrs": {"dangling": true}}
```

`rel` vocabulary:

- Evidence layer: `located_on`, `has_config`, `mentions`, `listens_on`, `talks_to`.
- Reasoning layer: `about` (reasoning node -> evidence node), `supports`, `contradicts`, `retrieved_by`.

Graph delta ops (the `event: graph` payloads):

```json
{"op": "add_node", "node": { ...node schema... }}
{"op": "add_edge", "edge": { ...edge schema... }}
{"op": "set_status", "id": "hyp:2", "status": "ruled_out"}
```

Caps, enforced by the graph store, not the prompt (PLAN M4.1):

- Reasoning layer: max 8 hypothesis nodes per run, max 5 finding nodes per hypothesis (so at most 48 reasoning nodes).
- A finding's `add_node` delta must carry `"parent": "hyp:N"` and `"stance": "supports" | "contradicts"` as fields INSIDE the `node` object; the store creates the finding and the edge `finding -<stance>-> hypothesis` atomically, which is what makes the per-hypothesis cap enforceable.
- On overflow (or an op referencing an unknown ID): reject the op and return an error to the agent loop, which tells the model in the next turn.
- PLAN's 150-node figure survives as the UI's rendered-view budget (reasoning layer + 1-hop evidence halo); when exceeded, the UI trims halo nodes on `ruled_out` branches first (see ADR-0005).
- The evidence layer itself is uncapped; the UI renders it as on-demand subgraphs, never the whole layer (see SPEC.md section 8).

### GET /api/runs/{run_id}/graph

```json
{"run_id": "...", "seq": 118, "nodes": [...], "edges": [...]}
```

`seq` is the event sequence number this snapshot is consistent with, so a client can snapshot then subscribe from `seq` without missing deltas.

### GET /api/runs/{run_id}/chunks/{chunk_id}

```json
{
  "chunk_id": "laptop-a:app_logs/backend.log:L120-L160",
  "text": "...verbatim chunk text...",
  "bundle_id": "bundle-laptop-a-20260726T183000Z",
  "machine_id": "laptop-a",
  "file_path": "app_logs/backend.log",
  "span": [120, 160],
  "kind": "evidence",
  "mentions": ["error:ECONNREFUSED", "host:db.internal", "port:5432"]
}
```

The chunk ID contains `/` and `:`; the UI must URL-encode it in the path segment.
