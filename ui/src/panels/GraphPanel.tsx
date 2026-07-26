import { useEffect, useRef } from "react";
import {
  BaseEdge,
  Background,
  Controls,
  EdgeLabelRenderer,
  Handle,
  Position,
  ReactFlow,
  getBezierPath,
  useEdgesState,
  useInternalNode,
  useNodesState,
  type Edge,
  type EdgeProps,
  type InternalNode,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { useStore } from "../store/useStore";
import { layout } from "../lib/layout";
import type { Chunk, ChunkKind, EdgeKind } from "../api/types";

const KIND_ACCENT: Record<ChunkKind, string> = {
  log: "var(--color-live)",
  config: "var(--color-evidence)",
  code: "var(--color-body)",
  doc: "var(--color-dim)",
  runbook: "var(--color-settled)",
  ticket: "var(--color-dim)",
};

const EDGE_COLOR: Record<EdgeKind, string> = {
  calls: "var(--color-body)",
  reads: "var(--color-evidence)",
  emitted: "var(--color-live)",
  references: "var(--color-dim)",
  contradicts: "var(--color-critical)",
};

/** Nodes are React components, which is the whole reason we're on React Flow. */
function ChunkNode({ data, dragging }: NodeProps) {
  const chunk = data.chunk as Chunk;
  const focused = data.focused as boolean;
  const accent = KIND_ACCENT[chunk.kind];

  return (
    <div
      className={`group hair bg-panel relative w-52 rounded border px-2.5 py-2 transition-all ${
        dragging ? "cursor-grabbing shadow-lg" : "cursor-grab"
      } ${focused ? "ring-live scale-105 ring-2" : ""} ${chunk.implicated ? "" : "opacity-55"}`}
      style={{ borderLeft: `3px solid ${accent}` }}
    >
      {/* Hidden — edges are drawn "floating" straight to whichever side faces the other node, so a fixed handle position isn't needed. */}
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <Handle type="source" position={Position.Top} className="!opacity-0" />

      <div className="flex items-center gap-1.5">
        <span className="text-[9px] uppercase tracking-wider" style={{ color: accent }}>
          {chunk.kind}
        </span>
        {chunk.score != null && (
          <span className="text-dim ml-auto text-[9px] tabular-nums">
            {chunk.score.toFixed(1)}
          </span>
        )}
      </div>

      <div className="text-bright mt-0.5 truncate text-[11px]">{chunk.label}</div>
      <div className="text-dim truncate text-[9px]">
        {chunk.path}:{chunk.lineStart}–{chunk.lineEnd}
      </div>

      {/* Hover reveals the chunk body — the point of a chunk-level graph. */}
      <div className="pointer-events-none absolute top-full left-0 z-50 mt-1.5 hidden w-80 group-hover:block">
        <pre className="hair bg-raised text-body overflow-hidden rounded border px-2.5 py-2 text-[10px] leading-relaxed whitespace-pre-wrap">
          {chunk.content}
        </pre>
      </div>
    </div>
  );
}

/** Where a straight line between two node centers crosses `intersectionNode`'s border. */
function getNodeIntersection(intersectionNode: InternalNode<Node>, targetNode: InternalNode<Node>) {
  const w = (intersectionNode.measured.width ?? 0) / 2;
  const h = (intersectionNode.measured.height ?? 0) / 2;
  const pos = intersectionNode.internals.positionAbsolute;
  const targetPos = targetNode.internals.positionAbsolute;

  const x2 = pos.x + w;
  const y2 = pos.y + h;
  const x1 = targetPos.x + (targetNode.measured.width ?? 0) / 2;
  const y1 = targetPos.y + (targetNode.measured.height ?? 0) / 2;

  const xx1 = (x1 - x2) / (2 * w) - (y1 - y2) / (2 * h);
  const yy1 = (x1 - x2) / (2 * w) + (y1 - y2) / (2 * h);
  const a = 1 / (Math.abs(xx1) + Math.abs(yy1) || 1);

  return { x: w * (a * xx1 + a * yy1) + x2, y: h * (-a * xx1 + a * yy1) + y2 };
}

/**
 * "Floating" edge: rather than leaving each end pinned to a fixed left/right
 * handle (which is what makes a graph read as a directional flow chart), the
 * line is recomputed every render to run straight between wherever the two
 * node borders face each other — the look of an undirected web of evidence.
 */
function FloatingEdge({ id, source, target, style, label }: EdgeProps) {
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);
  if (!sourceNode || !targetNode) return null;

  const sourceIntersection = getNodeIntersection(sourceNode, targetNode);
  const targetIntersection = getNodeIntersection(targetNode, sourceNode);
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX: sourceIntersection.x,
    sourceY: sourceIntersection.y,
    targetX: targetIntersection.x,
    targetY: targetIntersection.y,
  });
  const color = style?.stroke as string | undefined;

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} />
      {label != null && (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan absolute rounded text-[9px] font-medium tracking-wide uppercase"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              color,
              background: "var(--color-ground)",
              border: `1px solid ${color}`,
              padding: "1px 4px",
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const nodeTypes = { chunk: ChunkNode };
const edgeTypes = { floating: FloatingEdge };

export function GraphPanel() {
  const graph = useStore((s) => s.snapshot?.graph);
  const focusedChunk = useStore((s) => s.focusedChunk);
  const selectedMachine = useStore((s) => s.selectedMachine);
  const focusChunk = useStore((s) => s.focusChunk);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges] = useEdgesState<Edge>([]);
  const layoutKey = useRef("");

  // Re-lay-out only when the visible chunk/edge set actually changes shape —
  // never on hover — so dragged tiles stay put instead of snapping back.
  useEffect(() => {
    if (!graph) {
      setNodes([]);
      setEdges([]);
      layoutKey.current = "";
      return;
    }

    const visible = selectedMachine
      ? graph.chunks.filter((c) => c.machineId === selectedMachine)
      : graph.chunks;
    const ids = new Set(visible.map((c) => c.id));

    const rawEdges: Edge[] = graph.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: "floating",
        animated: e.kind === "emitted",
        label: e.kind,
        style: {
          stroke: EDGE_COLOR[e.kind],
          strokeDasharray: e.kind === "contradicts" ? "4 3" : undefined,
          opacity: 0.35 + e.weight * 0.6,
        },
      }));

    const key = visible
      .map((c) => c.id)
      .sort()
      .join(",");

    if (key !== layoutKey.current) {
      const rawNodes: Node[] = visible.map((chunk) => ({
        id: chunk.id,
        type: "chunk",
        position: { x: 0, y: 0 },
        zIndex: focusedChunk === chunk.id ? 1000 : 0,
        data: { chunk, focused: focusedChunk === chunk.id },
      }));
      setNodes(layout(rawNodes, rawEdges));
      layoutKey.current = key;
    } else {
      setNodes((nds) =>
        nds.map((n) => {
          const chunk = visible.find((c) => c.id === n.id);
          return chunk
            ? { ...n, zIndex: focusedChunk === n.id ? 1000 : 0, data: { chunk, focused: focusedChunk === n.id } }
            : n;
        }),
      );
    }

    setEdges(rawEdges);
    // focusedChunk deliberately excluded — handled by the effect below without touching layout
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, selectedMachine, setNodes, setEdges]);

  // Hover repaints the focus ring and — since the hover preview card can
  // overhang neighboring tiles — raises the hovered tile's stacking order so
  // its preview always draws in front instead of getting clipped underneath.
  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        zIndex: focusedChunk === n.id ? 1000 : 0,
        data: { ...n.data, focused: focusedChunk === n.id },
      })),
    );
  }, [focusedChunk, setNodes]);

  return (
    <div className="relative h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeMouseEnter={(_, n) => focusChunk(n.id)}
        onNodeMouseLeave={() => focusChunk(null)}
        nodesDraggable
        fitView
        minZoom={0.3}
        proOptions={{ hideAttribution: false }}
      >
        <Background color="var(--color-hair)" gap={22} size={1} />
        <Controls className="!shadow-none" />
      </ReactFlow>

      <div className="hair bg-panel/95 absolute top-3 left-3 rounded border px-2.5 py-2">
        <div className="text-dim mb-1.5 text-[10px] uppercase tracking-wider">
          Edges
        </div>
        {(Object.keys(EDGE_COLOR) as EdgeKind[]).map((k) => (
          <div key={k} className="flex items-center gap-2 text-[10px]">
            <span
              className="h-px w-5"
              style={{
                background: EDGE_COLOR[k],
                ...(k === "contradicts" ? { height: 0, borderTop: `1px dashed ${EDGE_COLOR[k]}` } : {}),
              }}
            />
            <span className="text-dim">{k}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
