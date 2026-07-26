import { useMemo, useState } from "react";
import { useStore } from "../store/useStore";
import { timeOfDay } from "../lib/format";
import type { LogEntry, Severity } from "../api/types";

const SEVERITY_ORDER: Severity[] = ["critical", "error", "warn", "info", "debug"];

const SEVERITY_STYLE: Record<Severity, string> = {
  critical: "text-critical",
  error: "text-live",
  warn: "text-settled",
  info: "text-dim",
  debug: "text-dim/60",
};

export function LogsPanel() {
  // stable selector outputs only (zustand v5); default outside the selector
  const logs = useStore((s) => s.snapshot?.logs) ?? [];
  const machines = useStore((s) => s.snapshot?.machines) ?? [];
  const selectedMachine = useStore((s) => s.selectedMachine);
  const [minSeverity, setMinSeverity] = useState<Severity>("debug");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

  const hostname = (id: string) =>
    machines.find((m) => m.id === id)?.hostname ?? id;

  const visible = useMemo(() => {
    const cutoff = SEVERITY_ORDER.indexOf(minSeverity);
    return logs
      .filter((l) => SEVERITY_ORDER.indexOf(l.severity) <= cutoff)
      .filter((l) => !selectedMachine || l.machineId === selectedMachine)
      .filter((l) =>
        query
          ? (l.message + l.path + (l.service ?? ""))
              .toLowerCase()
              .includes(query.toLowerCase())
          : true,
      )
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  }, [logs, minSeverity, selectedMachine, query]);

  const open = visible.find((l) => l.id === openId) ?? null;

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="hair flex items-center gap-3 border-b px-3 py-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by message, path, or service"
            className="hair bg-raised text-body placeholder:text-dim/70 min-w-0 flex-1 rounded border px-2 py-1 outline-none"
          />
          <div className="flex gap-1">
            {SEVERITY_ORDER.map((s) => (
              <button
                key={s}
                onClick={() => setMinSeverity(s)}
                className={`hair rounded border px-1.5 py-0.5 text-[10px] uppercase transition-colors ${
                  minSeverity === s
                    ? "bg-raised text-bright"
                    : "text-dim hover:text-body"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <span className="text-dim shrink-0 text-[10px] tabular-nums">
            {visible.length} lines
          </span>
        </div>

        <div className="flex-1 overflow-y-auto">
          {visible.length === 0 ? (
            <div className="text-dim px-3 py-6">
              No lines match. Widen the severity filter or clear the search.
            </div>
          ) : (
            visible.map((l) => (
              <LogRow
                key={l.id}
                log={l}
                hostname={hostname(l.machineId)}
                selected={openId === l.id}
                onClick={() => setOpenId(openId === l.id ? null : l.id)}
              />
            ))
          )}
        </div>
      </div>

      {open && (
        <div className="hair bg-panel w-96 shrink-0 overflow-y-auto border-l px-3 py-3">
          <div className={`${SEVERITY_STYLE[open.severity]} text-[10px] uppercase tracking-wider`}>
            {open.severity}
          </div>
          <p className="text-bright mt-1 leading-relaxed break-words">{open.message}</p>

          {open.summary && (
            <p className="text-evidence mt-2.5 leading-relaxed">{open.summary}</p>
          )}

          <dl className="mt-4 space-y-1.5 text-[11px]">
            <Field label="Machine" value={hostname(open.machineId)} />
            <Field label="Captured from" value={open.source} />
            <Field label="Path in bundle" value={open.path} />
            <Field label="Service" value={open.service ?? "—"} />
            <Field label="Timestamp" value={open.timestamp} />
          </dl>
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="text-dim w-28 shrink-0">{label}</dt>
      <dd className="text-body min-w-0 break-words">{value}</dd>
    </div>
  );
}

function LogRow({
  log,
  hostname,
  selected,
  onClick,
}: {
  log: LogEntry;
  hostname: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`hair flex w-full gap-3 border-b px-3 py-1.5 text-left transition-colors ${
        selected ? "bg-raised" : "hover:bg-raised/50"
      }`}
    >
      <span className="text-dim w-16 shrink-0 text-[10px] tabular-nums">
        {timeOfDay(log.timestamp)}
      </span>
      <span
        className={`${SEVERITY_STYLE[log.severity]} w-14 shrink-0 text-[10px] uppercase`}
      >
        {log.severity}
      </span>
      <span className="text-dim w-20 shrink-0 truncate text-[10px]">{hostname}</span>
      <span className="text-dim w-16 shrink-0 truncate text-[10px]">{log.source}</span>
      <span
        className={`min-w-0 flex-1 truncate ${
          log.severity === "critical" ? "text-bright" : "text-body"
        }`}
      >
        {log.message}
      </span>
    </button>
  );
}
