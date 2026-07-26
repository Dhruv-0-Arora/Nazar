// Fixture data for VITE_MOCK=1 mode. Shapes mirror API.md exactly.

import type {
  Bundle,
  Chunk,
  GraphSnapshot,
  Healthz,
  Report,
  RunDetail,
  StreamEnvelope,
  StreamEventMap,
  StreamEventName,
} from "../api/types";

export const MOCK_HEALTHZ: Healthz = {
  status: "ok",
  ollama: "ok",
  model: "qwen3.5:122b",
  version: "1.0.0",
};

export const MOCK_BUNDLES: Bundle[] = [
  {
    bundle_id: "bundle-laptop-a-20260726T183000Z",
    machine_id: "laptop-a",
    created_at: "2026-07-26T18:30:00Z",
    services: ["backend"],
    state: "ready",
  },
  {
    bundle_id: "bundle-laptop-b-20260726T183100Z",
    machine_id: "laptop-b",
    created_at: "2026-07-26T18:31:00Z",
    services: ["frontend"],
    state: "ready",
  },
  {
    bundle_id: "bundle-laptop-c-20260726T183200Z",
    machine_id: "laptop-c",
    created_at: "2026-07-26T18:32:00Z",
    services: ["db"],
    state: "ingesting",
  },
  {
    bundle_id: "bundle-unknown-20260726T090000Z",
    machine_id: null,
    created_at: null,
    services: null,
    state: "rejected",
    reason: "manifest.json missing; refusing bundle (collector version mismatch?)",
  },
];

export const DONE_RUN_ID = "run-20260726T174501Z-d0ne";
export const LIVE_RUN_ID = "run-20260726T184501Z-a1b2";

const DONE_REPORT: Report = {
  root_cause:
    "backend.env DB_HOST points at db.internal which resolves to nothing on this network",
  confidence: "high",
  affected_machines: ["laptop-a"],
  evidence: [
    {
      chunk_id: "laptop-a:services/backend/config/backend.env:L1-L12",
      why: "DB_HOST=db.internal set here",
    },
    {
      chunk_id: "laptop-a:app_logs/backend.log:L120-L160",
      why: "ECONNREFUSED to db.internal:5432 repeating every 5s",
    },
    {
      chunk_id: "laptop-a:network.txt:L1-L20",
      why: "no DNS entry for db.internal in resolv output",
    },
  ],
  ruled_out: [
    {
      hypothesis: "firewall blocking 5432",
      why: "iptables section shows no reject rules",
      chunk_id: "laptop-a:network.txt:L40-L55",
    },
    {
      hypothesis: "postgres service down on db host",
      why: "db host bundle shows postgres listening on 0.0.0.0:5432",
      chunk_id: "laptop-a:network.txt:L1-L20",
    },
  ],
  action_plan: [
    {
      step: 1,
      action: "set DB_HOST to 192.168.50.10 in backend.env",
      command:
        "sed -i 's/^DB_HOST=.*/DB_HOST=192.168.50.10/' services/backend/config/backend.env",
      risk: "low",
    },
    {
      step: 2,
      action: "restart backend service",
      command: "systemctl restart backend",
      risk: "low",
    },
    {
      step: 3,
      action: "verify frontend can reach backend",
      command: "curl -sf http://localhost:3000/healthz",
      risk: "low",
    },
  ],
  proposed_fix_script:
    "#!/usr/bin/env bash\nset -euo pipefail\n\n# Fix stale DB host in backend.env (advisory only; review before running)\nsed -i 's/^DB_HOST=.*/DB_HOST=192.168.50.10/' services/backend/config/backend.env\nsystemctl restart backend\ncurl -sf http://localhost:3000/healthz\n",
};

export const MOCK_DONE_RUN: RunDetail = {
  run_id: DONE_RUN_ID,
  status: "done",
  bundle_ids: ["bundle-laptop-a-20260726T183000Z"],
  question: "why is the frontend getting connection refused?",
  started_at: "2026-07-26T17:45:01Z",
  elapsed_s: 19.4,
  turns_completed: 5,
  report: DONE_REPORT,
  report_markdown:
    "# Diagnosis\n\n## Root cause\n\nbackend.env DB_HOST points at db.internal which resolves to nothing on this network.\n\n## Evidence\n\n- backend.env sets DB_HOST=db.internal\n- backend.log shows ECONNREFUSED to db.internal:5432 repeating\n- no DNS entry for db.internal\n\n## Fix\n\nSet DB_HOST to 192.168.50.10 and restart the backend service.\n",
  metrics: {
    turns: 5,
    queries_issued: 9,
    chunks_retrieved: 31,
    tokens_generated: 1450,
    elapsed_s: 19.4,
  },
};

export const MOCK_LIVE_RUN_BASE: RunDetail = {
  run_id: LIVE_RUN_ID,
  status: "running",
  bundle_ids: [
    "bundle-laptop-a-20260726T183000Z",
    "bundle-laptop-b-20260726T183100Z",
  ],
  question: "why is the frontend getting connection refused?",
  started_at: "2026-07-26T18:45:01Z",
  elapsed_s: 4.2,
  turns_completed: 1,
};

/** What the live mock run becomes once its scripted stream finishes. */
export const MOCK_LIVE_RUN_DONE: RunDetail = {
  ...MOCK_LIVE_RUN_BASE,
  status: "done",
  elapsed_s: 21.7,
  turns_completed: 6,
  report: DONE_REPORT,
  report_markdown: MOCK_DONE_RUN.report_markdown,
  metrics: {
    turns: 6,
    queries_issued: 7,
    chunks_retrieved: 24,
    tokens_generated: 1180,
    elapsed_s: 21.7,
  },
};

export const MOCK_CHUNKS: Record<string, Chunk> = {
  "laptop-a:services/backend/config/backend.env:L1-L12": {
    chunk_id: "laptop-a:services/backend/config/backend.env:L1-L12",
    text:
      "# backend service configuration\nNODE_ENV=production\nPORT=3000\nDB_HOST=db.internal\nDB_PORT=5432\nDB_NAME=appdb\nDB_USER=backend\nDB_PASSWORD=<redacted>\nCACHE_TTL=300\nLOG_LEVEL=info\nWORKERS=4\nTIMEOUT_MS=5000\n",
    bundle_id: "bundle-laptop-a-20260726T183000Z",
    machine_id: "laptop-a",
    file_path: "services/backend/config/backend.env",
    span: [1, 12],
    kind: "config",
    mentions: ["host:db.internal", "port:5432", "env_var:DB_HOST"],
  },
  "laptop-a:app_logs/backend.log:L120-L160": {
    chunk_id: "laptop-a:app_logs/backend.log:L120-L160",
    text:
      "2026-07-26T18:12:04Z error: connect ECONNREFUSED db.internal:5432\n    at TCPConnectWrap.afterConnect [as oncomplete] (node:net:1300:16)\n2026-07-26T18:12:09Z warn: retrying db connection (attempt 14)\n2026-07-26T18:12:09Z error: connect ECONNREFUSED db.internal:5432\n2026-07-26T18:12:14Z warn: retrying db connection (attempt 15)\n2026-07-26T18:12:14Z error: connect ECONNREFUSED db.internal:5432\n2026-07-26T18:12:19Z error: giving up after 15 attempts, entering degraded mode\n",
    bundle_id: "bundle-laptop-a-20260726T183000Z",
    machine_id: "laptop-a",
    file_path: "app_logs/backend.log",
    span: [120, 160],
    kind: "log",
    mentions: ["error:ECONNREFUSED", "host:db.internal", "port:5432"],
  },
  "laptop-a:network.txt:L40-L55": {
    chunk_id: "laptop-a:network.txt:L40-L55",
    text:
      "# iptables -L -n\nChain INPUT (policy ACCEPT)\ntarget     prot opt source               destination\nACCEPT     all  --  0.0.0.0/0            0.0.0.0/0\nChain FORWARD (policy ACCEPT)\nChain OUTPUT (policy ACCEPT)\n# no REJECT or DROP rules present\n",
    bundle_id: "bundle-laptop-a-20260726T183000Z",
    machine_id: "laptop-a",
    file_path: "network.txt",
    span: [40, 55],
    kind: "diagnostic",
    mentions: ["port:5432"],
  },
  "laptop-a:network.txt:L1-L20": {
    chunk_id: "laptop-a:network.txt:L1-L20",
    text:
      "# getent hosts db.internal\n(no output)\n\n# ss -ltnp\nState  Recv-Q Send-Q Local Address:Port  Peer Address:Port\nLISTEN 0      511    0.0.0.0:3000        0.0.0.0:*      users:((\"node\",pid=812))\nLISTEN 0      128    127.0.0.53:53       0.0.0.0:*\n",
    bundle_id: "bundle-laptop-a-20260726T183000Z",
    machine_id: "laptop-a",
    file_path: "network.txt",
    span: [1, 20],
    kind: "diagnostic",
    mentions: ["host:db.internal", "port:3000"],
  },
  "laptop-b:app_logs/frontend.log:L10-L42": {
    chunk_id: "laptop-b:app_logs/frontend.log:L10-L42",
    text:
      "2026-07-26T18:13:01Z error: GET /api/items -> 502 Bad Gateway\n2026-07-26T18:13:01Z error: upstream backend http://laptop-a:3000 returned 503 degraded\n2026-07-26T18:13:06Z error: GET /api/items -> 502 Bad Gateway\n",
    bundle_id: "bundle-laptop-b-20260726T183100Z",
    machine_id: "laptop-b",
    file_path: "app_logs/frontend.log",
    span: [10, 42],
    kind: "log",
    mentions: ["service:frontend", "service:backend", "port:3000"],
  },
};

export const MOCK_EMPTY_GRAPH: GraphSnapshot = {
  run_id: LIVE_RUN_ID,
  seq: 0,
  nodes: [],
  edges: [],
};

// ---------------------------------------------------------------------------
// Scripted live stream. Replayed on a timer by the mock EventSource.
// seq is assigned from array position (1-based) so dedupe logic is exercised.

type Scripted<E extends StreamEventName> = { event: E; data: StreamEventMap[E] };

function ev<E extends StreamEventName>(event: E, data: StreamEventMap[E]): Scripted<E> {
  return { event, data };
}

const REPORT_TOKENS =
  "The root cause is a stale database host in the backend configuration. backend.env on laptop-a sets DB_HOST=db.internal, but that name no longer resolves on this network, so every backend connection attempt fails with ECONNREFUSED and the frontend on laptop-b sees 502s from its upstream. Fix: point DB_HOST at 192.168.50.10 and restart the backend service.".split(
    /(?<= )/,
  );

const THINKING_TOKENS =
  "Both hypotheses trace back to db.internal. The firewall shows no reject rules, so hyp:2 is out. The dangling talks_to edge plus the empty getent output confirms hyp:1.".split(
    /(?<= )/,
  );

const SCRIPT: Scripted<StreamEventName>[] = [
  ev("status", { turn: 1, state: "searching" }),
  ev("query", { turn: 1, q: "connection refused frontend", k: 5 }),
  ev("chunk", {
    turn: 1,
    cid: "laptop-b:app_logs/frontend.log:L10-L42",
    file: "app_logs/frontend.log",
    score: 7.4,
    via: "bm25",
  }),
  ev("chunk", {
    turn: 1,
    cid: "laptop-a:app_logs/backend.log:L120-L160",
    file: "app_logs/backend.log",
    score: 9.2,
    via: "bm25",
  }),
  ev("graph", {
    op: "add_node",
    node: {
      id: "machine:laptop-a",
      layer: "evidence",
      type: "machine",
      label: "laptop-a",
      evidence: [],
      attrs: {},
    },
  }),
  ev("graph", {
    op: "add_node",
    node: {
      id: "service:backend",
      layer: "evidence",
      type: "service",
      label: "backend",
      evidence: ["laptop-a:app_logs/backend.log:L120-L160"],
      attrs: {},
    },
  }),
  ev("graph", {
    op: "add_edge",
    edge: { id: "e1", from: "service:backend", to: "machine:laptop-a", rel: "located_on", attrs: {} },
  }),
  ev("status", { turn: 2, state: "searching" }),
  ev("query", { turn: 2, q: "backend.env DB host", k: 5 }),
  ev("chunk", {
    turn: 2,
    cid: "laptop-a:services/backend/config/backend.env:L1-L12",
    file: "services/backend/config/backend.env",
    score: 8.1,
    via: "graph",
  }),
  ev("graph", {
    op: "add_node",
    node: {
      id: "host:db.internal",
      layer: "evidence",
      type: "host",
      label: "db.internal",
      evidence: ["laptop-a:services/backend/config/backend.env:L1-L12"],
      attrs: {},
    },
  }),
  ev("graph", {
    op: "add_edge",
    edge: {
      id: "e2",
      from: "service:backend",
      to: "host:db.internal",
      rel: "talks_to",
      attrs: { dangling: true },
    },
  }),
  ev("status", { turn: 3, state: "thinking" }),
  ev("graph", {
    op: "add_node",
    node: {
      id: "hyp:1",
      layer: "reasoning",
      type: "hypothesis",
      label: "stale DB host: db.internal no longer resolves",
      status: "open",
      evidence: ["laptop-a:services/backend/config/backend.env:L1-L12"],
      attrs: {},
    },
  }),
  ev("graph", {
    op: "add_edge",
    edge: { id: "e3", from: "hyp:1", to: "host:db.internal", rel: "about", attrs: {} },
  }),
  ev("graph", {
    op: "add_node",
    node: {
      id: "hyp:2",
      layer: "reasoning",
      type: "hypothesis",
      label: "firewall blocking 5432",
      status: "open",
      evidence: [],
      attrs: {},
    },
  }),
  ev("status", { turn: 4, state: "expanding" }),
  ev("query", { turn: 4, q: "iptables reject drop 5432", k: 5 }),
  ev("chunk", {
    turn: 4,
    cid: "laptop-a:network.txt:L40-L55",
    file: "network.txt",
    score: 6.3,
    via: "bm25",
  }),
  ev("graph", {
    op: "add_node",
    node: {
      id: "finding:1",
      layer: "reasoning",
      type: "finding",
      label: "iptables has no reject rules",
      status: "open",
      evidence: ["laptop-a:network.txt:L40-L55"],
      parent: "hyp:2",
      stance: "contradicts",
      attrs: {},
    },
  }),
  ev("graph", { op: "set_status", id: "hyp:2", status: "ruled_out" }),
  ev("status", { turn: 5, state: "expanding" }),
  ev("query", { turn: 5, q: "getent hosts db.internal resolv", k: 3 }),
  ev("chunk", {
    turn: 5,
    cid: "laptop-a:network.txt:L1-L20",
    file: "network.txt",
    score: 7.8,
    via: "graph",
  }),
  ev("graph", {
    op: "add_node",
    node: {
      id: "finding:2",
      layer: "reasoning",
      type: "finding",
      label: "db.internal has no DNS entry",
      status: "open",
      evidence: ["laptop-a:network.txt:L1-L20"],
      parent: "hyp:1",
      stance: "supports",
      attrs: {},
    },
  }),
  ev("graph", { op: "set_status", id: "hyp:1", status: "confirmed" }),
  ev("status", { turn: 6, state: "reporting" }),
  ...THINKING_TOKENS.map((text) => ev("token", { turn: 6, text, kind: "thinking" as const })),
  ...REPORT_TOKENS.map((text) => ev("token", { turn: 6, text, kind: "report" as const })),
  ev("done", { run_id: LIVE_RUN_ID, elapsed_s: 21.7 }),
];

export const MOCK_LIVE_EVENTS: StreamEnvelope[] = SCRIPT.map((s, i) => ({
  seq: i + 1,
  event: s.event,
  data: s.data,
}));
