// TypeScript mirrors of every schema in API.md (v1.0).
// Field names match API.md exactly; do not rename without a contract version bump.

// ---------------------------------------------------------------------------
// GET /api/healthz

export interface Healthz {
  status: string;
  /** "ok" or an error string. */
  ollama: string;
  model: string;
  version: string;
}

// ---------------------------------------------------------------------------
// GET /api/bundles

export type BundleState = "ready" | "ingesting" | "rejected";

export interface Bundle {
  bundle_id: string;
  /** null when the bundle was rejected with a missing/unparseable manifest. */
  machine_id: string | null;
  created_at: string | null;
  services: string[] | null;
  state: BundleState;
  /** Present only for rejected bundles; contents of reject-reason.txt. */
  reason?: string;
}

// ---------------------------------------------------------------------------
// POST /api/runs

export interface CreateRunRequest {
  /** Optional; default is every ready bundle not yet part of a run. */
  bundle_ids?: string[];
  /** Optional; default prompt asks for general diagnosis. */
  question?: string;
}

export interface CreateRunResponse {
  run_id: string;
}

// ---------------------------------------------------------------------------
// GET /api/runs and GET /api/runs/{run_id}

export type RunStatus = "queued" | "running" | "done" | "failed";

export interface RunSummary {
  run_id: string;
  status: RunStatus;
  bundle_ids: string[];
  question: string;
  started_at: string;
  elapsed_s: number;
  turns_completed: number;
}

export interface RunMetrics {
  turns: number;
  queries_issued: number;
  chunks_retrieved: number;
  tokens_generated: number;
  elapsed_s: number;
}

export interface RunDetail extends RunSummary {
  /** Present when status is "done". */
  report?: Report;
  report_markdown?: string;
  metrics?: RunMetrics;
  /** Present when status is "failed". */
  error?: string;
}

// ---------------------------------------------------------------------------
// Report JSON schema (API.md section 3)

export type Confidence = "high" | "medium" | "low";

export interface ReportEvidence {
  chunk_id: string;
  why: string;
}

export interface ReportRuledOut {
  hypothesis: string;
  why: string;
  chunk_id: string;
}

export interface ReportActionStep {
  step: number;
  action: string;
  command: string;
  risk: string;
}

export interface Report {
  root_cause: string;
  confidence: Confidence;
  affected_machines: string[];
  evidence: ReportEvidence[];
  ruled_out: ReportRuledOut[];
  action_plan: ReportActionStep[];
  /** Advisory only; the Brain never executes it (ADR-0010). */
  proposed_fix_script: string;
}

// ---------------------------------------------------------------------------
// SSE stream events (API.md section 2)

export type AgentState = "searching" | "expanding" | "thinking" | "reporting";

export interface StatusEvent {
  turn: number;
  state: AgentState;
}

export interface QueryEvent {
  turn: number;
  q: string;
  k: number;
}

export interface ChunkEvent {
  turn: number;
  cid: string;
  file: string;
  score: number;
  via: "bm25" | "graph";
}

export type TokenKind = "report" | "thinking";

export interface TokenEvent {
  turn: number;
  text: string;
  kind: TokenKind;
}

export interface DoneEvent {
  run_id: string;
  elapsed_s: number;
}

export interface ErrorEvent {
  message: string;
}

/** Discriminated map of SSE event name -> payload. */
export interface StreamEventMap {
  status: StatusEvent;
  query: QueryEvent;
  chunk: ChunkEvent;
  graph: GraphDelta;
  token: TokenEvent;
  done: DoneEvent;
  error: ErrorEvent;
}

export type StreamEventName = keyof StreamEventMap;

/** One event as replayed by mocks or read off the wire, tagged with its seq. */
export interface StreamEnvelope<E extends StreamEventName = StreamEventName> {
  seq: number;
  event: E;
  data: StreamEventMap[E];
}

// ---------------------------------------------------------------------------
// Graph schemas (API.md section 4)

export type GraphLayer = "evidence" | "reasoning";

export type NodeType =
  | "machine"
  | "service"
  | "file"
  | "host"
  | "ip"
  | "port"
  | "env_var"
  | "error"
  | "ticket"
  | "hypothesis"
  | "finding";

export type NodeStatus = "open" | "confirmed" | "ruled_out";

export interface GraphNode {
  id: string;
  layer: GraphLayer;
  type: NodeType;
  /** Capped at 80 chars by the store. */
  label: string;
  /** Only meaningful on reasoning-layer nodes. */
  status?: NodeStatus;
  /** Chunk IDs; resolved via GET .../chunks/{chunk_id} on click. */
  evidence?: string[];
  /** Finding nodes only: the owning hypothesis, e.g. "hyp:2". */
  parent?: string;
  /** Finding nodes only; the store creates the finding -stance-> hypothesis edge atomically. */
  stance?: "supports" | "contradicts";
  attrs?: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  rel: string;
  attrs?: Record<string, unknown>;
}

export interface AddNodeDelta {
  op: "add_node";
  /** For findings, node.parent and node.stance ride inside the node object. */
  node: GraphNode;
}

export interface AddEdgeDelta {
  op: "add_edge";
  edge: GraphEdge;
}

export interface SetStatusDelta {
  op: "set_status";
  id: string;
  status: NodeStatus;
}

export type GraphDelta = AddNodeDelta | AddEdgeDelta | SetStatusDelta;

// GET /api/runs/{run_id}/graph

export interface GraphSnapshot {
  run_id: string;
  /** Event seq this snapshot is consistent with; subscribe from here. */
  seq: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---------------------------------------------------------------------------
// GET /api/runs/{run_id}/chunks/{chunk_id}

export interface Chunk {
  chunk_id: string;
  text: string;
  bundle_id: string;
  machine_id: string;
  file_path: string;
  span: [number, number];
  kind: string;
  mentions: string[];
}
