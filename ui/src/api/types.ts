/**
 * Mirror of CONTRACT.md. If the Brain changes a field name, change it here first,
 * then let the compiler show you every place that breaks.
 */

export type Severity = "critical" | "error" | "warn" | "info" | "debug";

/** Where a log line was captured from, not where it was written to. */
export type LogSource =
  | "journald"
  | "app_log"
  | "console"
  | "browser"
  | "collector";

export interface Machine {
  id: string;
  hostname: string;
  role: string; // "backend", "frontend", "brain"
  address: string;
  reachable: boolean;
  bundleReceivedAt: string | null; // ISO
  os: string;
}

export interface LogEntry {
  id: string;
  machineId: string;
  timestamp: string; // ISO
  severity: Severity;
  source: LogSource;
  /** File the line came from inside the bundle, e.g. "services/backend/journal.log". */
  path: string;
  service: string | null;
  message: string;
  /** Brain-generated one-liner. Null until the agent has read this chunk. */
  summary: string | null;
}

/** A retrievable unit — a slice of a log, a config, a doc, or a source file. */
export type ChunkKind = "log" | "config" | "code" | "doc" | "runbook" | "ticket";

export interface Chunk {
  id: string;
  machineId: string;
  kind: ChunkKind;
  path: string;
  lineStart: number;
  lineEnd: number;
  label: string;
  content: string;
  /** BM25 score from the retrieval that surfaced it. Null if never retrieved. */
  score: number | null;
  /** Agent flagged this as supporting the current hypothesis. */
  implicated: boolean;
}

export type EdgeKind =
  | "calls" // frontend -> backend
  | "reads" // service -> config
  | "emitted" // service -> log chunk
  | "references" // doc -> config key
  | "contradicts"; // near-miss doc vs. evidence

export interface GraphEdge {
  id: string;
  source: string; // Chunk id
  target: string; // Chunk id
  kind: EdgeKind;
  weight: number;
}

export interface GraphPayload {
  chunks: Chunk[];
  edges: GraphEdge[];
}

export type StepStatus = "queued" | "running" | "done" | "failed";

/** One unit of agent work, scoped to a machine. Drives the concurrency tracker. */
export interface AgentStep {
  id: string;
  machineId: string;
  label: string; // "Scanning logs", "Indexing files", "Triaging"
  status: StepStatus;
  startedAt: string | null;
  finishedAt: string | null;
  detail: string | null;
}

export type TraceKind = "thought" | "query" | "retrieval" | "answer" | "user";

export interface TraceEvent {
  id: string;
  kind: TraceKind;
  text: string;
  timestamp: string;
  /** Chunk ids cited, so the graph can highlight in sync with the transcript. */
  citations: string[];
}

export interface Diagnosis {
  rootCause: string | null;
  confidence: number; // 0..1
  evidence: string[]; // Chunk ids
  actions: { id: string; text: string; command: string | null }[];
}

export interface RunStatus {
  runId: string;
  startedAt: string;
  elapsedSeconds: number;
  /** Seconds remaining, Brain's estimate. Null while it has no basis to guess. */
  etaSeconds: number | null;
  phase: "collecting" | "indexing" | "diagnosing" | "resolved" | "failed";
}

/** Everything the console needs. One shape, whether it came from mock or live. */
export interface ConsoleSnapshot {
  run: RunStatus;
  machines: Machine[];
  logs: LogEntry[];
  graph: GraphPayload;
  steps: AgentStep[];
  trace: TraceEvent[];
  diagnosis: Diagnosis;
  globalContext: string; // markdown, editable by the FDE
}

export interface ConsoleApi {
  getSnapshot(): Promise<ConsoleSnapshot>;
  /** Streams the agent's reply token by token. Mock and live must both do this. */
  sendMessage(text: string): AsyncGenerator<TraceEvent, void, unknown>;
  saveGlobalContext(markdown: string): Promise<void>;
  subscribe(onSnapshot: (s: ConsoleSnapshot) => void): () => void;
}
