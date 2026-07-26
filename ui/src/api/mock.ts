import type { ConsoleApi, ConsoleSnapshot, TraceEvent } from "./types";
import { snapshot as seed } from "./fixtures";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const clone = <T,>(v: T): T => structuredClone(v);

let state: ConsoleSnapshot = clone(seed);
const listeners = new Set<(s: ConsoleSnapshot) => void>();

function emit() {
  const frozen = clone(state);
  listeners.forEach((fn) => fn(frozen));
}

/** Nudges the clock and advances one running step so the UI has a pulse. */
function tick() {
  state.run.elapsedSeconds += 1;
  if (state.run.etaSeconds !== null) {
    state.run.etaSeconds = Math.max(0, state.run.etaSeconds - 1);
  }
  emit();
}

let timer: ReturnType<typeof setInterval> | null = null;

export const mockApi: ConsoleApi = {
  async getSnapshot() {
    await sleep(180);
    return clone(state);
  },

  async *sendMessage(text: string) {
    const now = () => new Date().toISOString();
    const user: TraceEvent = {
      id: `u-${Date.now()}`,
      kind: "user",
      text,
      timestamp: now(),
      citations: [],
    };
    state.trace.push(user);
    emit();
    yield user;

    await sleep(400);

    // Streamed word by word, because the live path will stream too.
    const reply =
      "Checking that against the bundle. The restart counter in journal.log rules out a one-off — " +
      "this is the fourth crash in ninety seconds, and every one aborts at the same resolver call. " +
      "I would not touch the firewall until DB_HOST resolves.";
    const id = `a-${Date.now()}`;
    const event: TraceEvent = {
      id,
      kind: "answer",
      text: "",
      timestamp: now(),
      citations: ["c-unit", "c-err"],
    };
    state.trace.push(event);

    for (const word of reply.split(" ")) {
      await sleep(45);
      event.text = event.text ? `${event.text} ${word}` : word;
      emit();
      yield { ...event };
    }
  },

  async saveGlobalContext(markdown: string) {
    await sleep(120);
    state.globalContext = markdown;
    emit();
  },

  subscribe(onSnapshot) {
    listeners.add(onSnapshot);
    if (!timer) timer = setInterval(tick, 1000);
    onSnapshot(clone(state));
    return () => {
      listeners.delete(onSnapshot);
      if (listeners.size === 0 && timer) {
        clearInterval(timer);
        timer = null;
      }
    };
  },
};
