import type { ConsoleApi } from "./types";
import { mockApi } from "./mock";
import { liveApi } from "./live";

const BASE = import.meta.env.VITE_BRAIN_URL ?? "/api";

/** Demo reset: clears bundles + finished runs on the Brain; running runs survive.
 * Operator action, deliberately outside ConsoleApi (mock mode has nothing to clear). */
export async function resetBrain(): Promise<{ removed_bundles: string[]; removed_runs: string[] }> {
  const res = await fetch(`${BASE}/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on /reset`);
  return res.json();
}

/**
 * Flip with `VITE_USE_MOCK=false npm run dev`, or from the header toggle at runtime.
 * Nothing outside this file knows which one it's talking to.
 */
const envPrefersMock = import.meta.env.VITE_USE_MOCK !== "false";

let current: ConsoleApi = envPrefersMock ? mockApi : liveApi;

export const api: ConsoleApi = {
  getSnapshot: (...a) => current.getSnapshot(...a),
  sendMessage: (...a) => current.sendMessage(...a),
  saveGlobalContext: (...a) => current.saveGlobalContext(...a),
  subscribe: (...a) => current.subscribe(...a),
};

export function setSource(source: "mock" | "live") {
  current = source === "mock" ? mockApi : liveApi;
}

export function currentSource(): "mock" | "live" {
  return current === mockApi ? "mock" : "live";
}
