import { Radio, Timer, Trash2 } from "lucide-react";
import { useState } from "react";
import { resetBrain } from "../api/client";
import { useStore } from "../store/useStore";
import { clock } from "../lib/format";

const PHASE_COPY: Record<string, string> = {
  collecting: "Collecting bundles",
  indexing: "Indexing",
  diagnosing: "Diagnosing",
  resolved: "Resolved",
  failed: "Stalled",
};

export function Header() {
  const run = useStore((s) => s.snapshot?.run);
  const source = useStore((s) => s.source);
  const switchSource = useStore((s) => s.switchSource);
  const selectMachine = useStore((s) => s.selectMachine);
  const [resetting, setResetting] = useState(false);

  async function onReset() {
    if (!window.confirm("Clear all bundles and finished runs on the Brain?")) return;
    setResetting(true);
    try {
      await resetBrain();
      selectMachine(null); // the machine we had selected may be gone now
    } catch (err) {
      window.alert(`Reset failed: ${err instanceof Error ? err.message : err}`);
    } finally {
      setResetting(false);
    }
  }

  return (
    <header className="hair flex items-center gap-6 border-b bg-panel px-4 py-2.5">
      <div className="flex items-baseline gap-2.5">
        <span className="text-bright text-sm font-semibold tracking-tight">
          Nazar
        </span>
        <span className="text-dim text-[11px]">{run?.runId ?? "no run"}</span>
      </div>

      <div className="flex items-center gap-2">
        <Radio size={13} className="text-live breathe" />
        <span className="text-body text-[11px] uppercase tracking-wider">
          {run ? PHASE_COPY[run.phase] : "Waiting"}
        </span>
      </div>

      {/* ETA is the number the room actually cares about, so it gets real size. */}
      <div className="ml-auto flex items-baseline gap-6">
        <div className="text-right">
          <div className="text-dim text-[10px] uppercase tracking-wider">Elapsed</div>
          <div className="text-body tabular-nums">
            {run ? clock(run.elapsedSeconds) : "—"}
          </div>
        </div>
        <div className="text-right">
          <div className="text-dim flex items-center justify-end gap-1 text-[10px] uppercase tracking-wider">
            <Timer size={10} /> Est. remaining
          </div>
          <div className="text-live text-xl leading-6 tabular-nums">
            {run?.etaSeconds != null ? clock(run.etaSeconds) : "—:—"}
          </div>
        </div>

        <button
          onClick={onReset}
          disabled={resetting || source === "mock"}
          className="hair text-dim hover:text-critical flex items-center gap-1.5 rounded border px-2 py-1 text-[11px] transition-colors disabled:opacity-40"
          title="Demo reset: clear all bundles and finished runs on the Brain (running runs survive)"
        >
          <Trash2 size={11} />
          {resetting ? "clearing…" : "reset"}
        </button>

        <button
          onClick={() => switchSource(source === "mock" ? "live" : "mock")}
          className="hair text-dim hover:text-bright rounded border px-2 py-1 text-[11px] transition-colors"
          title="Switch between fixtures and the Brain"
        >
          {source === "mock" ? "fixtures" : "brain"}
        </button>
      </div>
    </header>
  );
}
