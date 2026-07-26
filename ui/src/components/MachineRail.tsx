import { useStore } from "../store/useStore";
import { relative } from "../lib/format";

/**
 * Always visible, whatever tab you're on. At a glance: which box, is it reachable,
 * what is the agent doing on it right now. Clicking filters every other panel.
 */
export function MachineRail() {
  const snapshot = useStore((s) => s.snapshot);
  const selected = useStore((s) => s.selectedMachine);
  const selectMachine = useStore((s) => s.selectMachine);

  if (!snapshot) return <div className="hair w-56 shrink-0 border-r bg-panel" />;

  return (
    <aside className="hair flex w-56 shrink-0 flex-col border-r bg-panel">
      <div className="text-dim hair border-b px-3 py-2 text-[10px] uppercase tracking-wider">
        Machines
      </div>

      <div className="flex-1 overflow-y-auto">
        {snapshot.machines.map((m) => {
          const active = snapshot.steps.find(
            (s) => s.machineId === m.id && s.status === "running",
          );
          const isSelected = selected === m.id;
          const criticals = snapshot.logs.filter(
            (l) => l.machineId === m.id && l.severity === "critical",
          ).length;

          return (
            <button
              key={m.id}
              onClick={() => selectMachine(isSelected ? null : m.id)}
              className={`hair w-full border-b px-3 py-2.5 text-left transition-colors ${
                isSelected ? "bg-raised" : "hover:bg-raised/60"
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    !m.reachable
                      ? "bg-critical"
                      : active
                        ? "bg-live breathe"
                        : "bg-settled"
                  }`}
                />
                <span className="text-bright truncate">{m.hostname}</span>
                {criticals > 0 && (
                  <span className="text-critical ml-auto text-[10px] tabular-nums">
                    {criticals}!
                  </span>
                )}
              </div>

              <div className="text-dim mt-1 flex justify-between text-[10px]">
                <span>{m.role}</span>
                <span className="tabular-nums">{m.address}</span>
              </div>

              <div className="mt-1.5 truncate text-[11px]">
                {active ? (
                  <span className="text-live">{active.label}…</span>
                ) : (
                  <span className="text-dim">
                    bundle {relative(m.bundleReceivedAt)}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      <div className="hair text-dim border-t px-3 py-2 text-[10px] leading-relaxed">
        {snapshot.machines.filter((m) => m.reachable).length}/
        {snapshot.machines.length} reachable
      </div>
    </aside>
  );
}
