// Sigma.js rendering over a graphology instance, patched incrementally from
// graph delta events (API.md section 4). Deltas never trigger a full relayout:
// each new node gets a deterministic position (reasoning ring inside, evidence
// halo outside, findings beside their parent hypothesis) and sigma's
// autoRescale keeps everything in view.

import Graph from "graphology";
import Sigma from "sigma";
import { useEffect, useRef } from "react";
import type { GraphDelta, GraphNode, NodeStatus } from "../api/types";

const COLORS = {
  evidenceNode: "#46596b",
  evidenceEdge: "#2b3540",
  reasoningEdge: "#5c6773",
  contradictsEdge: "#a35d5d",
  danglingEdge: "#e5534b",
  open: "#e3b341",
  confirmed: "#3fb950",
  ruled_out: "#565e66",
};

function nodeColor(node: Pick<GraphNode, "layer" | "status">): string {
  if (node.layer === "evidence") return COLORS.evidenceNode;
  return COLORS[node.status ?? "open"];
}

function nodeSize(node: Pick<GraphNode, "layer" | "type">): number {
  if (node.layer === "reasoning") return node.type === "hypothesis" ? 11 : 7;
  return node.type === "machine" || node.type === "service" ? 7 : 5;
}

function countNodes(graph: Graph, pred: (attrs: Record<string, unknown>) => boolean): number {
  let n = 0;
  graph.forEachNode((_id, attrs) => {
    if (pred(attrs)) n += 1;
  });
  return n;
}

const GOLDEN_ANGLE = 2.399963;

function position(graph: Graph, node: GraphNode): { x: number; y: number } {
  const parent = node.parent;
  if (parent && graph.hasNode(parent)) {
    // Finding: orbit its hypothesis.
    const px = graph.getNodeAttribute(parent, "x") as number;
    const py = graph.getNodeAttribute(parent, "y") as number;
    const siblings = graph.degree(parent);
    const a = siblings * 1.1 + 0.6;
    return { x: px + 13 * Math.cos(a), y: py + 13 * Math.sin(a) };
  }
  if (node.layer === "reasoning") {
    // Hypotheses on an inner ring (max 8 per run, per the store caps).
    const i = countNodes(graph, (a) => a.layer === "reasoning" && a.nodeType === "hypothesis");
    const a = -Math.PI / 2 + i * ((2 * Math.PI) / 8);
    return { x: 32 * Math.cos(a), y: 32 * Math.sin(a) };
  }
  // Evidence halo on an outer ring, golden-angle spaced.
  const i = countNodes(graph, (a) => a.layer === "evidence");
  const r = 65 + (i % 3) * 12;
  return { x: r * Math.cos(i * GOLDEN_ANGLE), y: r * Math.sin(i * GOLDEN_ANGLE) };
}

function edgeStyle(rel: string, attrs?: Record<string, unknown>): { color: string; size: number } {
  if (attrs?.dangling === true) return { color: COLORS.danglingEdge, size: 2.5 };
  if (rel === "contradicts") return { color: COLORS.contradictsEdge, size: 1.5 };
  if (rel === "about" || rel === "supports" || rel === "retrieved_by")
    return { color: COLORS.reasoningEdge, size: 1.5 };
  return { color: COLORS.evidenceEdge, size: 1 };
}

function statusLabel(label: string, status: NodeStatus | undefined): string {
  return status === "ruled_out" ? `${label} (ruled out)` : label;
}

/** Apply one graph delta to the graphology instance. Idempotent per ID. */
export function applyGraphDelta(graph: Graph, delta: GraphDelta): void {
  switch (delta.op) {
    case "add_node": {
      const node = delta.node;
      if (graph.hasNode(node.id)) return;
      const { x, y } = position(graph, node);
      graph.addNode(node.id, {
        x,
        y,
        label: statusLabel(node.label, node.status),
        rawLabel: node.label,
        size: nodeSize(node),
        color: nodeColor(node),
        layer: node.layer,
        nodeType: node.type,
        status: node.status ?? null,
        evidence: node.evidence ?? [],
      });
      // A finding node carries parent + stance inside the node object; the
      // store creates the finding -stance-> hypothesis edge atomically, so
      // mirror that here.
      if (node.parent && node.stance && graph.hasNode(node.parent)) {
        const eid = `stance:${node.id}:${node.parent}`;
        if (!graph.hasEdge(eid)) {
          const style = edgeStyle(node.stance);
          graph.addEdgeWithKey(eid, node.id, node.parent, { rel: node.stance, ...style });
        }
      }
      return;
    }
    case "add_edge": {
      const edge = delta.edge;
      if (graph.hasEdge(edge.id)) return;
      if (!graph.hasNode(edge.from) || !graph.hasNode(edge.to)) return;
      const style = edgeStyle(edge.rel, edge.attrs);
      graph.addEdgeWithKey(edge.id, edge.from, edge.to, { rel: edge.rel, ...style });
      return;
    }
    case "set_status": {
      if (!graph.hasNode(delta.id)) return;
      graph.setNodeAttribute(delta.id, "status", delta.status);
      graph.setNodeAttribute(
        delta.id,
        "color",
        nodeColor({ layer: "reasoning", status: delta.status }),
      );
      const raw = (graph.getNodeAttribute(delta.id, "rawLabel") as string) ?? delta.id;
      graph.setNodeAttribute(delta.id, "label", statusLabel(raw, delta.status));
      return;
    }
  }
}

interface GraphCanvasProps {
  /** Owned by the parent; mutate it (via applyGraphDelta) and sigma follows. */
  graph: Graph;
  onNodeClick?: (nodeId: string, evidence: string[]) => void;
}

export default function GraphCanvas({ graph, onNodeClick }: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const clickRef = useRef(onNodeClick);
  clickRef.current = onNodeClick;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const sigma = new Sigma(graph, container, {
      allowInvalidContainer: true,
      labelColor: { color: "#aeb8c2" },
      labelSize: 12,
      labelRenderedSizeThreshold: 3,
      defaultEdgeColor: COLORS.evidenceEdge,
      zIndex: true,
    });
    sigma.on("clickNode", ({ node }) => {
      const evidence = (graph.getNodeAttribute(node, "evidence") as string[]) ?? [];
      clickRef.current?.(node, evidence);
    });
    return () => sigma.kill();
  }, [graph]);

  return <div ref={containerRef} className="graph-canvas" />;
}
