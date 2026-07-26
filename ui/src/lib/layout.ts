import type { Edge, Node } from "@xyflow/react";

const NODE_W = 208;
const NODE_H = 68;
const ITERATIONS = 400;
const REPULSION = 42000;
const SPRING_LENGTH = 300;
const SPRING_STRENGTH = 0.02;
const DAMPING = 0.9;
const CENTER_PULL = 0.008;

interface Point {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

/**
 * Force-directed layout: every node repels every other node, edges act as
 * springs pulling connected chunks together. Produces an organic web/network
 * shape (as opposed to dagre's layered left-to-right flow chart), which
 * better fits an undirected "evidence" graph where nothing actually flows.
 */
export function layout(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes;

  const points = new Map<string, Point>();
  const golden = Math.PI * (3 - Math.sqrt(5));
  nodes.forEach((n, i) => {
    const r = 200 * Math.sqrt(i + 1);
    const theta = i * golden;
    points.set(n.id, { x: r * Math.cos(theta), y: r * Math.sin(theta), vx: 0, vy: 0 });
  });

  const links = edges
    .map((e) => ({ source: points.get(e.source), target: points.get(e.target) }))
    .filter((l): l is { source: Point; target: Point } => !!l.source && !!l.target);

  const all = [...points.values()];

  for (let iter = 0; iter < ITERATIONS; iter++) {
    for (let i = 0; i < all.length; i++) {
      const a = all[i];
      for (let j = i + 1; j < all.length; j++) {
        const b = all[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const distSq = dx * dx + dy * dy || 0.01;
        const dist = Math.sqrt(distSq);
        const force = REPULSION / distSq;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }

    for (const { source, target } of links) {
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const force = (dist - SPRING_LENGTH) * SPRING_STRENGTH;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      source.vx += fx;
      source.vy += fy;
      target.vx -= fx;
      target.vy -= fy;
    }

    for (const p of all) {
      p.vx -= p.x * CENTER_PULL;
      p.vy -= p.y * CENTER_PULL;
      p.vx *= DAMPING;
      p.vy *= DAMPING;
      p.x += p.vx;
      p.y += p.vy;
    }
  }

  return nodes.map((n) => {
    const p = points.get(n.id)!;
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}
