// Final report rendering for done runs (API.md sections 1 and 3):
// root cause, confidence badge, evidence with chunk links, ruled-out list,
// action plan table, fix script, metrics footer.

import type { RunDetail } from "../api/types";

interface ReportViewProps {
  run: RunDetail;
  onOpenChunk: (chunkId: string) => void;
}

function ChunkLink({ chunkId, onOpen }: { chunkId: string; onOpen: (cid: string) => void }) {
  return (
    <button className="chunk-link" onClick={() => onOpen(chunkId)} title="Open chunk">
      {chunkId}
    </button>
  );
}

export default function ReportView({ run, onOpenChunk }: ReportViewProps) {
  const report = run.report;
  if (!report) {
    return (
      <div className="report">
        <p className="muted">
          {run.status === "failed"
            ? `Run failed: ${run.error ?? "unknown error"}`
            : "No report available for this run."}
        </p>
      </div>
    );
  }

  return (
    <div className="report">
      <section className="report-head">
        <span className={`badge badge-confidence-${report.confidence}`}>
          {report.confidence} confidence
        </span>
        <h2 className="root-cause">{report.root_cause}</h2>
        <p className="muted">
          Affected machines: {report.affected_machines.join(", ") || "-"}
        </p>
      </section>

      <section>
        <h3>Evidence</h3>
        <ul className="evidence-list">
          {report.evidence.map((e) => (
            <li key={e.chunk_id}>
              <ChunkLink chunkId={e.chunk_id} onOpen={onOpenChunk} />
              <span className="why">{e.why}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>Ruled out</h3>
        {report.ruled_out.length === 0 && <p className="muted">Nothing ruled out.</p>}
        <ul className="ruled-out-list">
          {report.ruled_out.map((r) => (
            <li key={r.hypothesis}>
              <span className="ruled-out-hypothesis">{r.hypothesis}</span>
              <span className="why">{r.why}</span>
              <ChunkLink chunkId={r.chunk_id} onOpen={onOpenChunk} />
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>Action plan</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Step</th>
              <th>Action</th>
              <th>Command</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {report.action_plan.map((a) => (
              <tr key={a.step}>
                <td>{a.step}</td>
                <td>{a.action}</td>
                <td>
                  <code>{a.command}</code>
                </td>
                <td>
                  <span className={`badge badge-risk-${a.risk}`}>{a.risk}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3>Proposed fix script</h3>
        <p className="muted small">Advisory only - the Brain never executes fix scripts (ADR-0010).</p>
        <pre className="code-block">{report.proposed_fix_script}</pre>
      </section>

      {run.report_markdown && (
        <details className="report-markdown">
          <summary>Report markdown</summary>
          <pre className="code-block">{run.report_markdown}</pre>
        </details>
      )}

      {run.metrics && (
        <footer className="metrics">
          <span>{run.metrics.turns} turns</span>
          <span>{run.metrics.queries_issued} queries</span>
          <span>{run.metrics.chunks_retrieved} chunks</span>
          <span>{run.metrics.tokens_generated} tokens</span>
          <span>{run.metrics.elapsed_s.toFixed(1)}s</span>
        </footer>
      )}
    </div>
  );
}
