import { Radio, Timer } from "lucide-react";
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

  return (
    <header className="hair flex items-center gap-6 border-b bg-panel px-4 py-2.5">
      <div className="flex items-baseline gap-2.5">
        <span className="text-bright text-sm font-semibold tracking-tight">
          FDE Console
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
