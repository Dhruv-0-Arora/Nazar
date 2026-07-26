// Root: tiny hash-based view switch (no router lib) plus health banner.
// Routes: #/ -> RunsList, #/runs/<run_id> -> LiveRun or ReportView by status.

import { useEffect, useState } from "react";
import { getHealthz, getRun } from "./api/client";
import type { RunDetail } from "./api/types";
import ChunkDrawer from "./components/ChunkDrawer";
import { isMock } from "./mock";
import LiveRun from "./views/LiveRun";
import ReportView from "./views/ReportView";
import RunsList from "./views/RunsList";

type Route = { view: "list" } | { view: "run"; runId: string };

function parseHash(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const parts = hash.split("/").filter(Boolean);
  if (parts[0] === "runs" && parts[1]) return { view: "run", runId: decodeURIComponent(parts[1]) };
  return { view: "list" };
}

function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(parseHash);
  useEffect(() => {
    const onChange = () => setRoute(parseHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

function RunPage({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drawerChunk, setDrawerChunk] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRun(null);
    setError(null);
    getRun(runId)
      .then((r) => {
        if (!cancelled) setRun(r);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (error) return <div className="page error-text">{error}</div>;
  if (!run) return <div className="page muted">Loading run...</div>;

  if (run.status === "done" || run.status === "failed") {
    return (
      <div className="page">
        <header className="live-head">
          <a href="#/" className="back-link">
            runs
          </a>
          <code className="run-id">{run.run_id}</code>
          <span className={`badge badge-${run.status}`}>{run.status}</span>
        </header>
        <ReportView run={run} onOpenChunk={setDrawerChunk} />
        {drawerChunk && (
          <ChunkDrawer runId={runId} chunkId={drawerChunk} onClose={() => setDrawerChunk(null)} />
        )}
      </div>
    );
  }

  return <LiveRun runId={runId} />;
}

export default function App() {
  const route = useHashRoute();
  const [ollama, setOllama] = useState<string>("ok");

  useEffect(() => {
    getHealthz()
      .then((h) => setOllama(h.ollama))
      .catch(() => setOllama("brain service unreachable"));
  }, []);

  return (
    <div className="app">
      <header className="app-head">
        <a href="#/" className="app-title">
          Brain
        </a>
        <span className="app-subtitle">offline diagnostics</span>
        {isMock && <span className="badge badge-mock">mock mode</span>}
      </header>
      {ollama !== "ok" && <div className="banner-warn">Ollama unavailable: {ollama}</div>}
      {route.view === "list" ? <RunsList /> : <RunPage key={route.runId} runId={route.runId} />}
    </div>
  );
}
