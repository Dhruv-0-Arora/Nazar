// Live run view, three panes (SPEC.md section 8):
// left - reasoning trail from status/query/chunk events, grouped by turn;
// center - sigma.js graph patched incrementally from graph deltas;
// right - report pane streaming token events on the final turn, swapped for
// the full report view once done.

import Graph from "graphology";
import { useCallback, useEffect, useState } from "react";
import { getGraph, getRun } from "../api/client";
import { useEventStream } from "../api/stream";
import type {
  AgentState,
  ChunkEvent,
  RunDetail,
} from "../api/types";
import ChunkDrawer from "../components/ChunkDrawer";
import GraphCanvas, { applyGraphDelta } from "../components/GraphCanvas";
import ReportView from "./ReportView";

type TrailItem =
  | { kind: "status"; turn: number; state: AgentState }
  | { kind: "query"; turn: number; state: AgentState | null; q: string; k: number; chunks: ChunkEvent[] };

interface LiveRunProps {
  runId: string;
}

export default function LiveRun({ runId }: LiveRunProps) {
  const [graph] = useState(() => new Graph());
  const [fromSeq, setFromSeq] = useState<number | null>(null);
  const [trail, setTrail] = useState<TrailItem[]>([]);
  const [agentState, setAgentState] = useState<{ turn: number; state: AgentState } | null>(null);
  const [reportText, setReportText] = useState("");
  const [thinkingText, setThinkingText] = useState("");
  const [doneRun, setDoneRun] = useState<RunDetail | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [drawerChunk, setDrawerChunk] = useState<string | null>(null);

  // Snapshot-then-subscribe: fetch the graph snapshot, hydrate the graphology
  // instance, then stream deltas from the snapshot's seq (API.md section 4).
  useEffect(() => {
    let cancelled = false;
    getGraph(runId)
      .then((snap) => {
        if (cancelled) return;
        for (const node of snap.nodes) applyGraphDelta(graph, { op: "add_node", node });
        for (const edge of snap.edges) applyGraphDelta(graph, { op: "add_edge", edge });
        setFromSeq(snap.seq);
      })
      .catch(() => {
        // No snapshot available: stream the full event log from zero.
        if (!cancelled) setFromSeq(0);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, graph]);

  const stream = useEventStream(runId, fromSeq, {
    onStatus: (e) => {
      setAgentState(e);
      setTrail((prev) => [...prev, { kind: "status", turn: e.turn, state: e.state }]);
    },
    onQuery: (e) => {
      setTrail((prev) => {
        const lastStatus = [...prev].reverse().find(
          (i): i is Extract<TrailItem, { kind: "status" }> =>
            i.kind === "status" && i.turn === e.turn,
        );
        return [
          ...prev,
          { kind: "query", turn: e.turn, state: lastStatus?.state ?? null, q: e.q, k: e.k, chunks: [] },
        ];
      });
    },
    onChunk: (e) => {
      setTrail((prev) => {
        const next = [...prev];
        for (let i = next.length - 1; i >= 0; i--) {
          const item = next[i];
          if (item.kind === "query" && item.turn === e.turn) {
            next[i] = { ...item, chunks: [...item.chunks, e] };
            return next;
          }
        }
        // Chunk without a preceding query (e.g. graph expansion): synthesize.
        next.push({ kind: "query", turn: e.turn, state: "expanding", q: "", k: 0, chunks: [e] });
        return next;
      });
    },
    onGraph: (delta) => {
      applyGraphDelta(graph, delta);
    },
    onTokens: (batch) => {
      let report = "";
      let thinking = "";
      for (const t of batch) {
        if (t.kind === "thinking") thinking += t.text;
        else report += t.text;
      }
      if (report) setReportText((prev) => prev + report);
      if (thinking) setThinkingText((prev) => prev + thinking);
    },
    onDone: () => {
      // Swap in the full report view.
      getRun(runId).then(setDoneRun).catch((e: unknown) => setRunError(String(e)));
    },
    onRunError: (e) => {
      setRunError(e.message);
    },
  });

  const onNodeClick = useCallback((_nodeId: string, evidence: string[]) => {
    if (evidence.length > 0) setDrawerChunk(evidence[0]);
  }, []);

  // Render the trail grouped by turn.
  const groups: { turn: number; items: TrailItem[] }[] = [];
  for (const item of trail) {
    const last = groups[groups.length - 1];
    if (last && last.turn === item.turn) last.items.push(item);
    else groups.push({ turn: item.turn, items: [item] });
  }

  return (
    <div className="live-run">
      <header className="live-head">
        <a href="#/" className="back-link">
          runs
        </a>
        <code className="run-id">{runId}</code>
        <span className="live-state">
          {doneRun
            ? "done"
            : runError
              ? "failed"
              : agentState
                ? `Turn ${agentState.turn} - ${agentState.state}`
                : "waiting for events"}
        </span>
        <span
          className={`conn-dot ${stream.finished ? "conn-finished" : stream.connected ? "conn-ok" : "conn-off"}`}
          title={
            stream.finished
              ? "stream finished"
              : stream.connected
                ? "stream connected"
                : "stream reconnecting"
          }
        />
      </header>

      <div className="panes">
        <section className="pane pane-trail">
          <h3>Reasoning trail</h3>
          {groups.length === 0 && <p className="muted">Waiting for the agent...</p>}
          {groups.map((g, gi) => (
            <div key={gi} className="turn-group">
              <div className="turn-title">Turn {g.turn}</div>
              {g.items.map((item, ii) =>
                item.kind === "status" ? (
                  <div key={ii} className="trail-line trail-status">
                    {item.state}
                  </div>
                ) : (
                  <div key={ii} className="trail-line">
                    {item.q !== "" && (
                      <div className="trail-query">
                        {item.state ?? "searching"}: <span className="q">"{item.q}"</span>{" "}
                        <span className="muted">(k={item.k})</span>
                      </div>
                    )}
                    {item.chunks.map((c) => (
                      <button
                        key={c.cid}
                        className="trail-chunk"
                        onClick={() => setDrawerChunk(c.cid)}
                        title={c.cid}
                      >
                        {"->"} retrieved {c.file} ({c.score.toFixed(1)}) [via {c.via}]
                      </button>
                    ))}
                  </div>
                ),
              )}
            </div>
          ))}
        </section>

        <section className="pane pane-graph">
          <GraphCanvas graph={graph} onNodeClick={onNodeClick} />
          <div className="graph-legend">
            <span className="legend-item legend-open">open</span>
            <span className="legend-item legend-confirmed">confirmed</span>
            <span className="legend-item legend-ruled-out">ruled out</span>
            <span className="legend-item legend-evidence">evidence</span>
          </div>
        </section>

        <section className="pane pane-report">
          {doneRun ? (
            <ReportView run={doneRun} onOpenChunk={setDrawerChunk} />
          ) : (
            <>
              <h3>Report</h3>
              {runError && <p className="error-text">{runError}</p>}
              {thinkingText && (
                <details className="thinking">
                  <summary>Thinking</summary>
                  <pre className="thinking-text">{thinkingText}</pre>
                </details>
              )}
              {reportText ? (
                <div className="stream-report">
                  {reportText}
                  {!stream.finished && <span className="cursor" />}
                </div>
              ) : (
                !runError && <p className="muted">The report streams here on the final turn.</p>
              )}
            </>
          )}
        </section>
      </div>

      {drawerChunk && (
        <ChunkDrawer runId={runId} chunkId={drawerChunk} onClose={() => setDrawerChunk(null)} />
      )}
    </div>
  );
}
