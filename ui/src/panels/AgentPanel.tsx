import { useEffect, useRef, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CornerDownLeft, Pencil } from "lucide-react";
import { useStore } from "../store/useStore";
import { timeOfDay } from "../lib/format";
import type { TraceKind } from "../api/types";

const KIND_STYLE: Record<TraceKind, { label: string; className: string }> = {
  user: { label: "fde", className: "text-bright" },
  thought: { label: "think", className: "text-body" },
  query: { label: "query", className: "text-evidence" },
  retrieval: { label: "hits", className: "text-evidence/80" },
  answer: { label: "answer", className: "text-bright" },
};

function Transcript() {
  const trace = useStore((s) => s.snapshot?.trace ?? []);
  const focusChunk = useStore((s) => s.focusChunk);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [trace.length, trace[trace.length - 1]?.text]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3">
      {trace.map((e) => {
        const style = KIND_STYLE[e.kind];
        return (
          <div
            key={e.id}
            className="mb-3 flex gap-3"
            onMouseEnter={() => e.citations[0] && focusChunk(e.citations[0])}
            onMouseLeave={() => focusChunk(null)}
          >
            <div className="text-dim w-14 shrink-0 pt-0.5 text-right text-[10px] tabular-nums">
              {timeOfDay(e.timestamp)}
            </div>
            <div className="min-w-0 flex-1">
              <span className="text-dim mr-2 text-[10px] uppercase tracking-wider">
                {style.label}
              </span>
              <span
                className={`${style.className} ${
                  e.kind === "query" ? "font-medium" : ""
                }`}
              >
                {e.text}
              </span>
              {e.citations.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {e.citations.map((c) => (
                    <button
                      key={c}
                      onMouseEnter={() => focusChunk(c)}
                      className="text-evidence hair rounded border px-1.5 py-0.5 text-[10px]"
                    >
                      {c}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}

function Composer() {
  const [text, setText] = useState("");
  const send = useStore((s) => s.send);
  const sending = useStore((s) => s.sending);

  const submit = () => {
    const t = text.trim();
    if (!t || sending) return;
    setText("");
    void send(t);
  };

  return (
    <div className="hair border-t px-4 py-3">
      <div className="hair bg-raised flex items-end gap-2 rounded border px-2.5 py-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder="Steer the agent — challenge a hypothesis, point it at a file, narrow the search"
          className="text-body placeholder:text-dim/70 max-h-32 flex-1 resize-none bg-transparent outline-none"
        />
        <button
          onClick={submit}
          disabled={sending || !text.trim()}
          className="text-dim hover:text-live disabled:opacity-30"
          aria-label="Send"
        >
          <CornerDownLeft size={15} />
        </button>
      </div>
      {sending && (
        <div className="text-live mt-1.5 text-[10px] breathe">
          agent is responding…
        </div>
      )}
    </div>
  );
}

function GlobalContext() {
  const snapshot = useStore((s) => s.snapshot);
  const saveContext = useStore((s) => s.saveContext);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const markdown = snapshot?.globalContext ?? "";

  return (
    <div className="flex h-full flex-col">
      <div className="hair flex items-center gap-2 border-b px-3 py-2">
        <span className="text-dim text-[10px] uppercase tracking-wider">
          Global context
        </span>
        <span className="text-dim/60 text-[10px]">shared with the agent</span>
        <button
          onClick={() => {
            if (editing) {
              void saveContext(draft);
              setEditing(false);
            } else {
              setDraft(markdown);
              setEditing(true);
            }
          }}
          className="text-dim hover:text-bright ml-auto flex items-center gap-1 text-[11px]"
        >
          <Pencil size={11} />
          {editing ? "Save" : "Edit"}
        </button>
      </div>

      {editing ? (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="text-body flex-1 resize-none bg-transparent px-3 py-2.5 outline-none"
          spellCheck={false}
        />
      ) : (
        <div className="markdown flex-1 overflow-y-auto px-3 py-2.5 leading-relaxed">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: (p) => (
                <h1 className="text-bright mb-2 text-sm font-semibold" {...p} />
              ),
              h2: (p) => (
                <h2
                  className="text-dim mt-3 mb-1 text-[10px] uppercase tracking-wider"
                  {...p}
                />
              ),
              ul: (p) => <ul className="mb-2 list-disc pl-4" {...p} />,
              p: (p) => <p className="mb-2" {...p} />,
              strong: (p) => <strong className="text-bright font-medium" {...p} />,
              code: (p) => (
                <code className="text-evidence bg-raised rounded px-1" {...p} />
              ),
            }}
          >
            {markdown}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}

function DiagnosisCard() {
  const diagnosis = useStore((s) => s.snapshot?.diagnosis);
  const focusChunk = useStore((s) => s.focusChunk);
  if (!diagnosis?.rootCause) return null;

  return (
    <div className="hair border-t px-3 py-2.5">
      <div className="flex items-baseline gap-2">
        <span className="text-dim text-[10px] uppercase tracking-wider">
          Working diagnosis
        </span>
        <span className="text-live ml-auto text-[10px] tabular-nums">
          {Math.round(diagnosis.confidence * 100)}% confident
        </span>
      </div>
      <p className="text-bright mt-1.5 leading-relaxed">{diagnosis.rootCause}</p>

      <div className="mt-2.5 space-y-1.5">
        {diagnosis.actions.map((a, i) => (
          <div key={a.id} className="flex gap-2">
            <span className="text-dim shrink-0 tabular-nums">{i + 1}</span>
            <div className="min-w-0">
              <div className="text-body">{a.text}</div>
              {a.command && (
                <code className="text-evidence block truncate text-[11px]">
                  {a.command}
                </code>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap gap-1">
        {diagnosis.evidence.map((c) => (
          <button
            key={c}
            onMouseEnter={() => focusChunk(c)}
            onMouseLeave={() => focusChunk(null)}
            className="text-evidence hair rounded border px-1.5 py-0.5 text-[10px]"
          >
            {c}
          </button>
        ))}
      </div>
    </div>
  );
}

export function AgentPanel() {
  return (
    <PanelGroup direction="horizontal">
      <Panel defaultSize={62} minSize={35}>
        <div className="flex h-full flex-col">
          <Transcript />
          <Composer />
        </div>
      </Panel>

      <PanelResizeHandle className="hover:bg-live/40 w-px bg-[var(--color-hair)] transition-colors" />

      <Panel defaultSize={38} minSize={22}>
        <div className="flex h-full flex-col">
          <div className="min-h-0 flex-1">
            <GlobalContext />
          </div>
          <DiagnosisCard />
        </div>
      </Panel>
    </PanelGroup>
  );
}
