// useEventStream: SSE client for GET /api/runs/{run_id}/stream (API.md section 2).
//
// - First connection passes ?from_seq=<seq> (e.g. the graph snapshot's seq).
// - On automatic reconnect the browser sends Last-Event-ID, which the server
//   gives precedence over from_seq; we just keep the same URL.
// - Every event carries id: <seq>; we dedupe by tracking the last seen seq and
//   dropping replays (second line of defense per ADR-0007).
// - token events are buffered and flushed on requestAnimationFrame, never per
//   token (binding UI guidance in API.md section 2).

import { useEffect, useRef, useState } from "react";
import type {
  ChunkEvent,
  DoneEvent,
  ErrorEvent as RunErrorEvent,
  GraphDelta,
  QueryEvent,
  StatusEvent,
  StreamEnvelope,
  StreamEventName,
  TokenEvent,
} from "./types";
import { isMock, mockStream } from "../mock";

export interface StreamCallbacks {
  onStatus?: (e: StatusEvent) => void;
  onQuery?: (e: QueryEvent) => void;
  onChunk?: (e: ChunkEvent) => void;
  onGraph?: (delta: GraphDelta) => void;
  /** Called with an rAF-flushed batch of token events, in order. */
  onTokens?: (batch: TokenEvent[]) => void;
  onDone?: (e: DoneEvent) => void;
  /** The run failed (event: error from the agent loop). */
  onRunError?: (e: RunErrorEvent) => void;
}

export interface StreamState {
  /** Transport is open (real mode) or replay is active (mock mode). */
  connected: boolean;
  /** Last event seq processed; useful for debugging and resume. */
  lastSeq: number;
  /** Stream ended with done or error. */
  finished: boolean;
}

const EVENT_NAMES: StreamEventName[] = [
  "status",
  "query",
  "chunk",
  "graph",
  "token",
  "done",
  "error",
];

/**
 * Subscribe to a run's SSE stream.
 *
 * @param runId   run to stream, or null to stay disconnected
 * @param fromSeq resume point (0 for the full log, or a graph snapshot's seq);
 *                null delays connecting until known
 */
export function useEventStream(
  runId: string | null,
  fromSeq: number | null,
  callbacks: StreamCallbacks,
): StreamState {
  const [state, setState] = useState<StreamState>({
    connected: false,
    lastSeq: 0,
    finished: false,
  });

  // Latest callbacks without retriggering the connection effect.
  const cbRef = useRef(callbacks);
  cbRef.current = callbacks;

  useEffect(() => {
    if (runId === null || fromSeq === null) return;

    let closed = false;
    const lastSeqRef = { seq: fromSeq };
    const tokenBuf: TokenEvent[] = [];
    let rafId: number | null = null;

    const flushTokens = () => {
      rafId = null;
      if (tokenBuf.length === 0) return;
      const batch = tokenBuf.splice(0, tokenBuf.length);
      cbRef.current.onTokens?.(batch);
    };

    const scheduleFlush = () => {
      if (rafId === null) rafId = requestAnimationFrame(flushTokens);
    };

    const finish = () => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      flushTokens(); // drain anything buffered before done/error reaches the UI
      setState((s) => ({ ...s, connected: false, finished: true }));
    };

    const handle = (envelope: StreamEnvelope) => {
      if (closed) return;
      if (envelope.seq <= lastSeqRef.seq) return; // dedupe replays by seq
      lastSeqRef.seq = envelope.seq;
      setState((s) => ({ ...s, lastSeq: envelope.seq }));

      const cb = cbRef.current;
      switch (envelope.event) {
        case "status":
          cb.onStatus?.(envelope.data as StatusEvent);
          break;
        case "query":
          cb.onQuery?.(envelope.data as QueryEvent);
          break;
        case "chunk":
          cb.onChunk?.(envelope.data as ChunkEvent);
          break;
        case "graph":
          cb.onGraph?.(envelope.data as GraphDelta);
          break;
        case "token":
          tokenBuf.push(envelope.data as TokenEvent);
          scheduleFlush();
          break;
        case "done":
          finish();
          teardown();
          cb.onDone?.(envelope.data as DoneEvent);
          break;
        case "error":
          finish();
          teardown();
          cb.onRunError?.(envelope.data as RunErrorEvent);
          break;
      }
    };

    let teardown: () => void = () => {};

    if (isMock) {
      const cancel = mockStream(runId, fromSeq, handle);
      teardown = cancel;
      setState({ connected: true, lastSeq: fromSeq, finished: false });
    } else {
      const url = `/api/runs/${encodeURIComponent(runId)}/stream?from_seq=${fromSeq}`;
      const es = new EventSource(url);
      teardown = () => es.close();

      es.onopen = () => {
        if (!closed) setState((s) => ({ ...s, connected: true }));
      };
      es.onerror = () => {
        // EventSource reconnects automatically, resending Last-Event-ID.
        if (!closed) setState((s) => ({ ...s, connected: false }));
      };

      for (const name of EVENT_NAMES) {
        es.addEventListener(name, (raw: MessageEvent<string>) => {
          const seq = Number(raw.lastEventId);
          let data: unknown;
          try {
            data = JSON.parse(raw.data);
          } catch {
            return; // malformed frame; skip rather than crash the stream
          }
          handle({ seq, event: name, data } as StreamEnvelope);
        });
      }
      setState({ connected: false, lastSeq: fromSeq, finished: false });
    }

    return () => {
      closed = true;
      if (rafId !== null) cancelAnimationFrame(rafId);
      teardown();
    };
  }, [runId, fromSeq]);

  return state;
}
