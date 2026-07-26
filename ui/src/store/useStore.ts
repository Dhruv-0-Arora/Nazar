import { create } from "zustand";
import type { ConsoleSnapshot } from "../api/types";
import { api, currentSource, setSource } from "../api/client";

export type TabId = "agent" | "graph" | "logs" | "processes";

interface State {
  snapshot: ConsoleSnapshot | null;
  tab: TabId;
  /** Chunk id under the cursor — shared so the graph and transcript highlight together. */
  focusedChunk: string | null;
  selectedMachine: string | null;
  sending: boolean;
  source: "mock" | "live";

  setTab: (t: TabId) => void;
  focusChunk: (id: string | null) => void;
  selectMachine: (id: string | null) => void;
  connect: () => () => void;
  send: (text: string) => Promise<void>;
  saveContext: (markdown: string) => Promise<void>;
  switchSource: (s: "mock" | "live") => void;
}

export const useStore = create<State>((set, get) => ({
  snapshot: null,
  tab: "agent",
  focusedChunk: null,
  selectedMachine: null,
  sending: false,
  source: currentSource(),

  setTab: (tab) => set({ tab }),
  focusChunk: (focusedChunk) => set({ focusedChunk }),
  selectMachine: (selectedMachine) => set({ selectedMachine }),

  connect: () => api.subscribe((snapshot) => set({ snapshot })),

  send: async (text) => {
    set({ sending: true });
    try {
      // The stream mutates shared state; subscribe() pushes each frame back to us.
      for await (const _ of api.sendMessage(text)) void _;
    } finally {
      set({ sending: false });
    }
  },

  saveContext: async (markdown) => {
    await api.saveGlobalContext(markdown);
  },

  switchSource: (source) => {
    setSource(source);
    set({ source, snapshot: null });
    get().connect();
  },
}));
