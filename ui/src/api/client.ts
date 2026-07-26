// Fetch wrappers for every endpoint in API.md section 1.
// In mock mode (VITE_MOCK=1) these serve fixture data from src/mock/.

import type {
  Bundle,
  Chunk,
  CreateRunRequest,
  CreateRunResponse,
  GraphSnapshot,
  Healthz,
  RunDetail,
  RunSummary,
} from "./types";
import {
  isMock,
  mockBundles,
  mockChunk,
  mockCreateRun,
  mockGraph,
  mockHealthz,
  mockRun,
  mockRuns,
} from "../mock";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = await res.text();
    } catch {
      // ignore body read failures
    }
    throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}${detail ? `: ${detail.slice(0, 300)}` : ""}`);
  }
  return (await res.json()) as T;
}

export function getHealthz(): Promise<Healthz> {
  if (isMock) return mockHealthz();
  return request<Healthz>("/api/healthz");
}

export function getBundles(): Promise<Bundle[]> {
  if (isMock) return mockBundles();
  return request<Bundle[]>("/api/bundles");
}

export function getRuns(): Promise<RunSummary[]> {
  if (isMock) return mockRuns();
  return request<RunSummary[]>("/api/runs");
}

export function getRun(runId: string): Promise<RunDetail> {
  if (isMock) return mockRun(runId);
  return request<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`);
}

export function createRun(req: CreateRunRequest): Promise<CreateRunResponse> {
  if (isMock) return mockCreateRun(req);
  return request<CreateRunResponse>("/api/runs", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function getGraph(runId: string): Promise<GraphSnapshot> {
  if (isMock) return mockGraph(runId);
  return request<GraphSnapshot>(`/api/runs/${encodeURIComponent(runId)}/graph`);
}

export function getChunk(runId: string, chunkId: string): Promise<Chunk> {
  if (isMock) return mockChunk(runId, chunkId);
  // Chunk IDs contain ':' and '/'; API.md requires URL-encoding the segment.
  return request<Chunk>(
    `/api/runs/${encodeURIComponent(runId)}/chunks/${encodeURIComponent(chunkId)}`,
  );
}
