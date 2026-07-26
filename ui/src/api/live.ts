import type { ConsoleApi, ConsoleSnapshot, TraceEvent } from "./types";

const BASE = import.meta.env.VITE_BRAIN_URL ?? "/api";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return (await res.json()) as T;
}

export const liveApi: ConsoleApi = {
  getSnapshot: () => json<ConsoleSnapshot>("/snapshot"),

  async *sendMessage(text: string) {
    const res = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.body) throw new Error("Brain returned no stream");

    // Expects newline-delimited JSON, one TraceEvent per line.
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.trim()) yield JSON.parse(line) as TraceEvent;
      }
    }
  },

  async saveGlobalContext(markdown: string) {
    await json("/context", { method: "PUT", body: JSON.stringify({ markdown }) });
  },

  subscribe(onSnapshot) {
    const es = new EventSource(`${BASE}/stream`);
    es.onmessage = (e) => onSnapshot(JSON.parse(e.data) as ConsoleSnapshot);
    return () => es.close();
  },
};
