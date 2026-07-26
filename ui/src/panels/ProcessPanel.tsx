import { useStore } from "../store/useStore";
import { relative } from "../lib/format";
import type { AgentStep, StepStatus } from "../api/types";

const STATUS_STYLE: Record<StepStatus, string> = {
  running: "border-l-[var(--color-live)] bg-raised",
  done: "border-l-[var(--color-settled)]",
  queued: "border-l-[var(--color-hair)] opacity-60",
  failed: "border-l-[var(--color-critical)]",
};

/**
 * One column per machine, so "what is happening on which laptop" is answered by
 * looking, not reading. Columns, not a merged feed — the point is concurrency.
 */
export function ProcessPanel() {
  const snapshot = useStore((s) => s.snapshot);
  if (!snapshot) return null;

  return (
    <div className="flex h-full gap-px overflow-x-auto bg-[var(--color-hair)]">
      {snapshot.machines.map((m) => {
        const steps = snapshot.steps.filter((s) => s.machineId === m.id);
        const running = steps.filter((s) => s.status === "running").length;

        return (
          <div key={m.id} className="bg-ground flex min-w-72 flex-1 flex-col">
            <div className="hair flex items-baseline gap-2 border-b px-3 py-2">
              <span className="text-bright">{m.hostname}</span>
              <span className="text-dim text-[10px]">{m.role}</span>
              <span className="text-dim ml-auto text-[10px] tabular-nums">
                {running > 0 ? (
                  <span className="text-live">{running} active</span>
                ) : (
                  "idle"
                )}
              </span>
            </div>

            <div className="flex-1 space-y-1.5 overflow-y-auto p-2.5">
              {steps.length === 0 ? (
                <div className="text-dim px-1 py-4 text-[11px]">
                  Nothing scheduled on this machine yet.
                </div>
              ) : (
                steps.map((s) => <StepTile key={s.id} step={s} />)
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StepTile({ step }: { step: AgentStep }) {
  return (
    <div
      className={`hair rounded border border-l-2 px-2.5 py-2 ${STATUS_STYLE[step.status]}`}
    >
      <div className="flex items-center gap-2">
        {step.status === "running" && (
          <span className="bg-live breathe h-1.5 w-1.5 rounded-full" />
        )}
        <span className={step.status === "running" ? "text-bright" : "text-body"}>
          {step.label}
        </span>
        <span className="text-dim ml-auto text-[10px]">
          {step.status === "running"
            ? relative(step.startedAt)
            : step.status === "done"
              ? "done"
              : step.status}
        </span>
      </div>
      {step.detail && (
        <div className="text-dim mt-1 truncate text-[10px]">{step.detail}</div>
      )}
    </div>
  );
}
