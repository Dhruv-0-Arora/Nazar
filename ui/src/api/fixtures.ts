import type {
  AgentStep,
  Chunk,
  ConsoleSnapshot,
  GraphEdge,
  LogEntry,
  Machine,
  TraceEvent,
} from "./types";

const T0 = new Date("2026-07-26T14:02:00Z").getTime();
const at = (offsetSec: number) => new Date(T0 + offsetSec * 1000).toISOString();

export const machines: Machine[] = [
  {
    id: "m-brain",
    hostname: "brain",
    role: "brain",
    address: "192.168.50.1",
    reachable: true,
    bundleReceivedAt: null,
    os: "Ubuntu 24.04",
  },
  {
    id: "m-api",
    hostname: "client-a",
    role: "backend",
    address: "192.168.50.2",
    reachable: true,
    bundleReceivedAt: at(140),
    os: "Ubuntu 24.04",
  },
  {
    id: "m-web",
    hostname: "client-b",
    role: "frontend",
    address: "192.168.50.3",
    reachable: true,
    bundleReceivedAt: at(196),
    os: "Ubuntu 24.04",
  },
];

export const logs: LogEntry[] = [
  {
    id: "l1",
    machineId: "m-api",
    timestamp: at(12),
    severity: "critical",
    source: "app_log",
    path: "app_logs/backend.err",
    service: "backend",
    message:
      "FATAL getaddrinfo ENOTFOUND db-prod-01.internal — connection pool exhausted after 5 retries",
    summary: "Backend cannot resolve its database host. Process exits.",
  },
  {
    id: "l2",
    machineId: "m-api",
    timestamp: at(12),
    severity: "error",
    source: "journald",
    path: "services/backend/journal.log",
    service: "backend",
    message: "backend.service: Main process exited, code=exited, status=1/FAILURE",
    summary: null,
  },
  {
    id: "l3",
    machineId: "m-api",
    timestamp: at(13),
    severity: "info",
    source: "journald",
    path: "services/backend/journal.log",
    service: "backend",
    message: "backend.service: Scheduled restart job, restart counter is at 4.",
    summary: "Restart loop — systemctl still reports the unit as active.",
  },
  {
    id: "l4",
    machineId: "m-web",
    timestamp: at(31),
    severity: "error",
    source: "browser",
    path: "app_logs/frontend-console.log",
    service: "frontend",
    message: "GET http://client-a:8080/api/orders 502 (Bad Gateway)",
    summary: null,
  },
  {
    id: "l5",
    machineId: "m-web",
    timestamp: at(31),
    severity: "warn",
    source: "console",
    path: "app_logs/frontend.log",
    service: "frontend",
    message: "upstream unavailable, serving stale cache (age 41s)",
    summary: null,
  },
  {
    id: "l6",
    machineId: "m-api",
    timestamp: at(4),
    severity: "debug",
    source: "collector",
    path: "manifest.json",
    service: null,
    message: "bundle-client-a-20260726T140204Z collected, 14 files, 812 KB",
    summary: null,
  },
];

export const chunks: Chunk[] = [
  {
    id: "c-cfg",
    machineId: "m-api",
    kind: "config",
    path: "services/backend/backend.env",
    lineStart: 3,
    lineEnd: 3,
    label: "backend.env — DB_HOST",
    content: "DB_HOST=db-prod-01.internal\nDB_PORT=5432\nDB_POOL_MAX=20",
    score: 18.4,
    implicated: true,
  },
  {
    id: "c-err",
    machineId: "m-api",
    kind: "log",
    path: "app_logs/backend.err",
    lineStart: 118,
    lineEnd: 126,
    label: "backend.err — ENOTFOUND",
    content:
      "FATAL getaddrinfo ENOTFOUND db-prod-01.internal\n  at GetAddrInfoReqWrap.onlookupall\n  connection pool exhausted after 5 retries",
    score: 22.1,
    implicated: true,
  },
  {
    id: "c-unit",
    machineId: "m-api",
    kind: "log",
    path: "services/backend/journal.log",
    lineStart: 40,
    lineEnd: 52,
    label: "journal — restart loop",
    content:
      "backend.service: Main process exited, code=exited, status=1/FAILURE\nbackend.service: Scheduled restart job, restart counter is at 4.",
    score: 11.7,
    implicated: true,
  },
  {
    id: "c-502",
    machineId: "m-web",
    kind: "log",
    path: "app_logs/frontend-console.log",
    lineStart: 8,
    lineEnd: 12,
    label: "frontend console — 502s",
    content: "GET http://client-a:8080/api/orders 502 (Bad Gateway)",
    score: 14.9,
    implicated: true,
  },
  {
    id: "c-runbook",
    machineId: "m-web",
    kind: "runbook",
    path: "docs/runbook-backend-config.md",
    lineStart: 1,
    lineEnd: 22,
    label: "runbook — backend config",
    content:
      "Database connection settings live in /etc/myapp/backend.env. After editing, `systemctl restart backend`. Note: the unit reports active even when the app is crash-looping.",
    score: 16.2,
    implicated: true,
  },
  {
    id: "c-nearmiss",
    machineId: "m-web",
    kind: "ticket",
    path: "docs/2025-03-frontend-502.md",
    lineStart: 1,
    lineEnd: 18,
    label: "ticket 2025-03 — 502s (near miss)",
    content:
      "Frontend returned 502s across the fleet. Root cause was an iptables rule dropping traffic on 8080. Fixed by flushing the rule.",
    score: 15.8,
    implicated: false,
  },
  {
    id: "c-fw",
    machineId: "m-api",
    kind: "config",
    path: "network.txt",
    lineStart: 60,
    lineEnd: 74,
    label: "network.txt — nft ruleset",
    content: "table inet filter { chain input { policy accept; } }",
    score: 6.3,
    implicated: false,
  },
  {
    id: "c-code",
    machineId: "m-api",
    kind: "code",
    path: "backend/src/db.js",
    lineStart: 9,
    lineEnd: 24,
    label: "db.js — pool init",
    content:
      "const pool = new Pool({ host: process.env.DB_HOST, port: +process.env.DB_PORT });",
    score: 9.5,
    implicated: true,
  },
];

export const edges: GraphEdge[] = [
  { id: "e1", source: "c-502", target: "c-err", kind: "calls", weight: 0.9 },
  { id: "e2", source: "c-code", target: "c-cfg", kind: "reads", weight: 1 },
  { id: "e3", source: "c-code", target: "c-err", kind: "emitted", weight: 0.8 },
  { id: "e4", source: "c-err", target: "c-unit", kind: "emitted", weight: 0.7 },
  { id: "e5", source: "c-runbook", target: "c-cfg", kind: "references", weight: 0.6 },
  { id: "e6", source: "c-nearmiss", target: "c-fw", kind: "contradicts", weight: 0.4 },
  { id: "e7", source: "c-nearmiss", target: "c-502", kind: "references", weight: 0.3 },
  { id: "e8", source: "c-runbook", target: "c-err", kind: "relates", weight: 0.81 },
];

export const clusters = [
  { id: "c1", label: null as string | null },
  { id: "c2", label: null as string | null },
];

export const steps: AgentStep[] = [
  {
    id: "s1",
    machineId: "m-api",
    label: "Collecting bundle",
    status: "done",
    startedAt: at(2),
    finishedAt: at(140),
    detail: "14 files, 812 KB over scp",
  },
  {
    id: "s2",
    machineId: "m-web",
    label: "Collecting bundle",
    status: "done",
    startedAt: at(6),
    finishedAt: at(196),
    detail: "11 files, 402 KB over scp",
  },
  {
    id: "s3",
    machineId: "m-api",
    label: "Indexing files",
    status: "done",
    startedAt: at(142),
    finishedAt: at(180),
    detail: "1,284 chunks → BM25",
  },
  {
    id: "s4",
    machineId: "m-web",
    label: "Indexing files",
    status: "running",
    startedAt: at(198),
    finishedAt: null,
    detail: "612 / 890 chunks",
  },
  {
    id: "s5",
    machineId: "m-api",
    label: "Scanning logs",
    status: "running",
    startedAt: at(184),
    finishedAt: null,
    detail: "journal.log, backend.err",
  },
  {
    id: "s6",
    machineId: "m-api",
    label: "Triaging",
    status: "queued",
    startedAt: null,
    finishedAt: null,
    detail: null,
  },
  {
    id: "s7",
    machineId: "m-web",
    label: "Searching code files",
    status: "queued",
    startedAt: null,
    finishedAt: null,
    detail: null,
  },
];

export const trace: TraceEvent[] = [
  {
    id: "t1",
    kind: "thought",
    text: "Two hosts report failure within 19s. client-b's 502s are downstream of client-a — start at the backend, not the edge.",
    timestamp: at(200),
    citations: ["c-502"],
  },
  {
    id: "t2",
    kind: "query",
    text: 'search("backend connection refused database host", k=6)',
    timestamp: at(204),
    citations: [],
  },
  {
    id: "t3",
    kind: "retrieval",
    text: "6 chunks — top: backend.err ENOTFOUND (22.1), backend.env DB_HOST (18.4), runbook-backend-config (16.2)",
    timestamp: at(206),
    citations: ["c-err", "c-cfg", "c-runbook"],
  },
  {
    id: "t4",
    kind: "thought",
    text: "The 2025-03 ticket matches the symptom but not the cause — its 502s came from a dropped iptables rule, and network.txt shows an accept policy here. Setting it aside.",
    timestamp: at(212),
    citations: ["c-nearmiss", "c-fw"],
  },
  {
    id: "t5",
    kind: "answer",
    text: "DB_HOST in backend.env points at db-prod-01.internal, which does not resolve on this network. The unit reports active because systemd restarts it faster than the check interval.",
    timestamp: at(218),
    citations: ["c-cfg", "c-err", "c-unit"],
  },
];

export const globalContext = `# Incident context

**Site:** Ravenna warehouse, cutover weekend
**Reported:** order page returns 502 for all users
**Network:** site uplink down — Brain on direct cable, no DNS, no internet

## Known-good

- \`client-a\` and \`client-b\` both reachable at 192.168.50.2/.3
- Postgres reachable at 192.168.50.10 as \`db-local-01\`

## Constraints

- No package installs on client machines
- Any fix must survive a reboot
`;

export const snapshot: ConsoleSnapshot = {
  run: {
    runId: "run-20260726-1402",
    startedAt: at(0),
    elapsedSeconds: 224,
    etaSeconds: 95,
    phase: "diagnosing",
  },
  machines,
  logs,
  graph: { chunks, edges, clusters },
  steps,
  trace,
  diagnosis: {
    rootCause:
      "backend.env sets DB_HOST to db-prod-01.internal, which does not resolve on the isolated site network. The backend crash-loops on startup; the frontend's 502s are a downstream symptom.",
    confidence: 0.86,
    evidence: ["c-cfg", "c-err", "c-unit", "c-runbook"],
    actions: [
      {
        id: "a1",
        text: "Point DB_HOST at the reachable local database",
        command: "sed -i 's/^DB_HOST=.*/DB_HOST=db-local-01/' /etc/myapp/backend.env",
      },
      {
        id: "a2",
        text: "Restart the backend and confirm it stops crash-looping",
        command: "systemctl restart backend && journalctl -u backend -n 20",
      },
      {
        id: "a3",
        text: "Re-check the order page from client-b",
        command: "curl -sS -o /dev/null -w '%{http_code}' http://client-a:8080/api/orders",
      },
    ],
  },
  globalContext,
};
