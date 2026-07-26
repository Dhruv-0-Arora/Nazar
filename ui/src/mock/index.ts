// Mock backend for VITE_MOCK=1: serves fixtures for client.ts and replays the
// scripted live stream for stream.ts. No network involved.

import type {
  Bundle,
  Chunk,
  CreateRunRequest,
  CreateRunResponse,
  GraphSnapshot,
  Healthz,
  RunDetail,
  StreamEnvelope,
} from "../api/types";
import {
  DONE_RUN_ID,
  LIVE_RUN_ID,
  MOCK_BUNDLES,
  MOCK_CHUNKS,
  MOCK_DONE_RUN,
  MOCK_EMPTY_GRAPH,
  MOCK_HEALTHZ,
  MOCK_LIVE_EVENTS,
  MOCK_LIVE_RUN_BASE,
  MOCK_LIVE_RUN_DONE,
} from "./fixtures";

export const isMock = import.meta.env.VITE_MOCK === "1";

// The live mock run flips to "done" after its scripted stream finishes, so the
// UI's on-done refetch shows the real report flow.
let liveRunFinished = false;
let liveRunStartedAt = 0;

export function markLiveRunFinished(): void {
  liveRunFinished = true;
}

function delay<T>(value: T, ms = 120): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

export function mockHealthz(): Promise<Healthz> {
  return delay(MOCK_HEALTHZ);
}

export function mockBundles(): Promise<Bundle[]> {
  return delay(MOCK_BUNDLES);
}

function liveRun(): RunDetail {
  if (liveRunFinished) return MOCK_LIVE_RUN_DONE;
  const elapsed =
    liveRunStartedAt > 0 ? (Date.now() - liveRunStartedAt) / 1000 : MOCK_LIVE_RUN_BASE.elapsed_s;
  return { ...MOCK_LIVE_RUN_BASE, elapsed_s: Math.round(elapsed * 10) / 10 };
}

export function mockRuns(): Promise<RunDetail[]> {
  return delay([liveRun(), MOCK_DONE_RUN]);
}

export function mockRun(runId: string): Promise<RunDetail> {
  if (runId === DONE_RUN_ID) return delay(MOCK_DONE_RUN);
  if (runId === LIVE_RUN_ID) return delay(liveRun());
  return Promise.reject(new Error(`mock: unknown run ${runId}`));
}

export function mockCreateRun(_req: CreateRunRequest): Promise<CreateRunResponse> {
  // Starting a run in mock mode always points at the scripted live run.
  liveRunFinished = false;
  liveRunStartedAt = Date.now();
  return delay({ run_id: LIVE_RUN_ID }, 200);
}

export function mockGraph(runId: string): Promise<GraphSnapshot> {
  return delay({ ...MOCK_EMPTY_GRAPH, run_id: runId });
}

export function mockChunk(_runId: string, chunkId: string): Promise<Chunk> {
  const chunk = MOCK_CHUNKS[chunkId];
  if (!chunk) return Promise.reject(new Error(`mock: unknown chunk ${chunkId}`));
  return delay(chunk);
}

/**
 * Replays the scripted live-run events on a timer, honoring from_seq.
 * Returns a cancel function. Mirrors the real SSE contract closely enough
 * that stream.ts treats both paths identically past the transport.
 */
export function mockStream(
  runId: string,
  fromSeq: number,
  onEvent: (envelope: StreamEnvelope) => void,
): () => void {
  if (runId !== LIVE_RUN_ID) {
    // Finished (or unknown) runs replay their whole log instantly, matching
    // "connecting to a finished run replays the whole event log".
    return () => {};
  }
  const pending = MOCK_LIVE_EVENTS.filter((e) => e.seq > fromSeq);
  let i = 0;
  let timer = 0;

  const step = () => {
    if (i >= pending.length) return;
    const envelope = pending[i++];
    onEvent(envelope);
    if (envelope.event === "done" || envelope.event === "error") {
      markLiveRunFinished();
      return;
    }
    // Tokens stream fast; structural events pace the narrative.
    const ms = pending[i]?.event === "token" ? 35 : 550;
    timer = window.setTimeout(step, ms);
  };
  timer = window.setTimeout(step, 400);
  return () => window.clearTimeout(timer);
}
