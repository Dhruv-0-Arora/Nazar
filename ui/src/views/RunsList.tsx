// Landing view: bundle table with checkboxes, run table polled every 2 s,
// and a Diagnose button that POSTs /api/runs and navigates to the live view.

import { useCallback, useEffect, useMemo, useState } from "react";
import { createRun, getBundles, getRuns } from "../api/client";
import type { Bundle, RunSummary } from "../api/types";

function formatElapsed(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s - m * 60)}s`;
}

function StateBadge({ state }: { state: string }) {
  return <span className={`badge badge-${state}`}>{state}</span>;
}

export default function RunsList() {
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [question, setQuestion] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    getRuns().then(setRuns).catch((e: unknown) => setError(String(e)));
    getBundles().then(setBundles).catch((e: unknown) => setError(String(e)));
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, [refresh]);

  const readyIds = useMemo(
    () => new Set(bundles.filter((b) => b.state === "ready").map((b) => b.bundle_id)),
    [bundles],
  );

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const diagnose = async () => {
    setStarting(true);
    setError(null);
    try {
      const bundle_ids = [...selected].filter((id) => readyIds.has(id));
      const res = await createRun({
        ...(bundle_ids.length > 0 ? { bundle_ids } : {}),
        ...(question.trim() ? { question: question.trim() } : {}),
      });
      window.location.hash = `#/runs/${res.run_id}`;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setStarting(false);
    }
  };

  return (
    <div className="page">
      {error && <p className="error-text">{error}</p>}

      <section>
        <h2>Bundles</h2>
        <table className="table">
          <thead>
            <tr>
              <th className="col-check" />
              <th>Bundle</th>
              <th>Machine</th>
              <th>Services</th>
              <th>Created</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {bundles.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  No bundles in the inbox yet.
                </td>
              </tr>
            )}
            {bundles.map((b) => (
              <tr key={b.bundle_id} className={b.state === "rejected" ? "row-rejected" : ""}>
                <td className="col-check">
                  <input
                    type="checkbox"
                    disabled={b.state !== "ready"}
                    checked={selected.has(b.bundle_id)}
                    onChange={() => toggle(b.bundle_id)}
                    aria-label={`Select ${b.bundle_id}`}
                  />
                </td>
                <td>
                  <code>{b.bundle_id}</code>
                </td>
                <td>{b.machine_id ?? "-"}</td>
                <td>{b.services?.join(", ") ?? "-"}</td>
                <td>{b.created_at ?? "-"}</td>
                <td>
                  <StateBadge state={b.state} />
                  {b.state === "rejected" && b.reason && (
                    <div className="reject-reason">{b.reason}</div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="diagnose-bar">
          <input
            className="question-input"
            type="text"
            placeholder="Question (optional) - default asks for general diagnosis"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button className="btn btn-primary" onClick={diagnose} disabled={starting}>
            {starting
              ? "Starting..."
              : selected.size > 0
                ? `Diagnose ${selected.size} bundle${selected.size > 1 ? "s" : ""}`
                : "Diagnose all ready bundles"}
          </button>
        </div>
      </section>

      <section>
        <h2>Runs</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Run</th>
              <th>Status</th>
              <th>Bundles</th>
              <th>Turns</th>
              <th>Elapsed</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  No runs yet.
                </td>
              </tr>
            )}
            {runs.map((r) => (
              <tr key={r.run_id}>
                <td>
                  <a href={`#/runs/${r.run_id}`}>
                    <code>{r.run_id}</code>
                  </a>
                </td>
                <td>
                  <StateBadge state={r.status} />
                </td>
                <td>{r.bundle_ids.length}</td>
                <td>{r.turns_completed}</td>
                <td>{formatElapsed(r.elapsed_s)}</td>
                <td>{r.started_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
