// Side drawer resolving a chunk ID via GET /api/runs/{id}/chunks/{chunk_id}.
// This is the "each node opens the actual file from the bundle" requirement.

import { useEffect, useState } from "react";
import { getChunk } from "../api/client";
import type { Chunk } from "../api/types";

interface ChunkDrawerProps {
  runId: string;
  chunkId: string;
  onClose: () => void;
}

export default function ChunkDrawer({ runId, chunkId, onClose }: ChunkDrawerProps) {
  const [chunk, setChunk] = useState<Chunk | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setChunk(null);
    setError(null);
    getChunk(runId, chunkId)
      .then((c) => {
        if (!cancelled) setChunk(c);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [runId, chunkId]);

  return (
    <aside className="drawer" role="dialog" aria-label="Chunk detail">
      <div className="drawer-head">
        <code className="drawer-cid">{chunkId}</code>
        <button className="btn btn-ghost" onClick={onClose} aria-label="Close drawer">
          Close
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
      {!chunk && !error && <p className="muted">Loading chunk...</p>}
      {chunk && (
        <>
          <dl className="drawer-meta">
            <dt>File</dt>
            <dd>
              <code>{chunk.file_path}</code>
            </dd>
            <dt>Machine</dt>
            <dd>{chunk.machine_id}</dd>
            <dt>Span</dt>
            <dd>
              L{chunk.span[0]}-L{chunk.span[1]}
            </dd>
            <dt>Kind</dt>
            <dd>{chunk.kind}</dd>
            <dt>Bundle</dt>
            <dd>
              <code>{chunk.bundle_id}</code>
            </dd>
            <dt>Mentions</dt>
            <dd>
              {chunk.mentions.length === 0
                ? "-"
                : chunk.mentions.map((m) => (
                    <span key={m} className="tag">
                      {m}
                    </span>
                  ))}
            </dd>
          </dl>
          <pre className="drawer-text">{chunk.text}</pre>
        </>
      )}
    </aside>
  );
}
