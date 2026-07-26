import type { ConsoleApi } from "./types";
import { mockApi } from "./mock";
import { liveApi } from "./live";

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
