import { useEffect } from "react";
import { Header } from "./components/Header";
import { MachineRail } from "./components/MachineRail";
import { AgentPanel } from "./panels/AgentPanel";
import { GraphPanel } from "./panels/GraphPanel";
import { LogsPanel } from "./panels/LogsPanel";
import { ProcessPanel } from "./panels/ProcessPanel";
import { useStore, type TabId } from "./store/useStore";

const TABS: { id: TabId; label: string }[] = [
  { id: "agent", label: "Agent" },
  { id: "graph", label: "Evidence graph" },
  { id: "logs", label: "Logs" },
  { id: "processes", label: "Work in flight" },
];

export function App() {
  const tab = useStore((s) => s.tab);
  const setTab = useStore((s) => s.setTab);
  const connect = useStore((s) => s.connect);
  const snapshot = useStore((s) => s.snapshot);
  const selectedMachine = useStore((s) => s.selectedMachine);
  const machines = useStore((s) => s.snapshot?.machines ?? []);
  const selectMachine = useStore((s) => s.selectMachine);

  useEffect(() => connect(), [connect]);

  const filterName = machines.find((m) => m.id === selectedMachine)?.hostname;

  return (
    <div className="flex h-full flex-col">
      <Header />

      <div className="flex min-h-0 flex-1">
        <MachineRail />

        <main className="flex min-w-0 flex-1 flex-col">
          <nav className="hair flex items-center gap-1 border-b px-2">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`border-b-2 px-3 py-2 text-[12px] transition-colors ${
                  tab === t.id
                    ? "border-live text-bright"
                    : "text-dim hover:text-body border-transparent"
                }`}
              >
                {t.label}
              </button>
            ))}

            {filterName && (
              <button
                onClick={() => selectMachine(null)}
                className="text-live hair ml-auto rounded border px-2 py-0.5 text-[10px]"
              >
                filtered to {filterName} — clear
              </button>
            )}
          </nav>

          <div className="min-h-0 flex-1">
            {!snapshot ? (
              <div className="text-dim px-4 py-6">
                Waiting for the first bundle to land in the inbox.
              </div>
            ) : tab === "agent" ? (
              <AgentPanel />
            ) : tab === "graph" ? (
              <GraphPanel />
            ) : tab === "logs" ? (
              <LogsPanel />
            ) : (
              <ProcessPanel />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
