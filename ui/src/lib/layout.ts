import type { Edge, Node } from "@xyflow/react";

const NODE_W = 208;
const NODE_H = 68;
const ITERATIONS = 400;
const RESEED_ITERATIONS = 120;
const REPULSION = 42000;
const SPRING_LENGTH = 300;
const SPRING_STRENGTH = 0.02;
const DAMPING = 0.9;
const CENTER_PULL = 0.008;
const GROUP_PULL = CENTER_PULL * 4;
const GROUP_RADIUS = 700;
const ORPHAN_GAP_X = NODE_W + 48;
const ORPHAN_GAP_Y = NODE_H + 40;

interface Point {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export interface LayoutOptions {
  /** Seed positions (current on-screen spots) so re-layouts refine instead of snapping to a fresh spiral. */
  initial?: Map<string, { x: number; y: number }>;
  /** Group id per node (cluster or machine); groups become gravity wells on a ring. */
  groupOf?: (id: string) => string | null | undefined;
}

/**
 * Force-directed layout: every node repels every other node, edges act as
 * springs pulling connected chunks together. Produces an organic web/network
 * shape (as opposed to a layered left-to-right flow chart), which better fits
 * an undirected "evidence" graph where nothing actually flows.
 *
 * Two refinements over the naive sim:
 * - Degree-0 nodes are excluded from the physics and packed into a dim grid
 *   on the right periphery; unconnected tiles no longer smear into a disc.
 * - Groups (clusters, else machines) get anchors on a ring and a gentle pull,
 *   so related chunks settle into visible neighborhoods.
 */
export function layout(nodes: Node[], edges: Edge[], opts: LayoutOptions = {}): Node[] {
  if (nodes.length === 0) return nodes;

  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  const connected = nodes.filter((n) => (degree.get(n.id) ?? 0) > 0);
  const orphans = nodes.filter((n) => (degree.get(n.id) ?? 0) === 0);

  // group anchors on a ring, deterministic order
  const groups = new Map<string, { x: number; y: number }>();
  if (opts.groupOf) {
    const names = [...new Set(connected.map((n) => opts.groupOf!(n.id)).filter((g): g is string => !!g))].sort();
    names.forEach((name, i) => {
      const theta = (2 * Math.PI * i) / Math.max(1, names.length);
      groups.set(name, { x: GROUP_RADIUS * Math.cos(theta), y: GROUP_RADIUS * Math.sin(theta) });
    });
  }

  const points = new Map<string, Point>();
  const golden = Math.PI * (3 - Math.sqrt(5));
  let reseeded = false;
  connected.forEach((n, i) => {
    const seed = opts.initial?.get(n.id);
    if (seed) {
      reseeded = true;
      points.set(n.id, { x: seed.x + NODE_W / 2, y: seed.y + NODE_H / 2, vx: 0, vy: 0 });
      return;
    }
    const anchor = (opts.groupOf && groups.get(opts.groupOf(n.id) ?? "")) || { x: 0, y: 0 };
    const r = 160 * Math.sqrt(i + 1);
    const theta = i * golden;
    points.set(n.id, { x: anchor.x + r * Math.cos(theta) * 0.4, y: anchor.y + r * Math.sin(theta) * 0.4, vx: 0, vy: 0 });
  });

  const links = edges
    .map((e) => ({ source: points.get(e.source), target: points.get(e.target) }))
    .filter((l): l is { source: Point; target: Point } => !!l.source && !!l.target);

  const all = [...points.values()];
  const iterations = reseeded ? RESEED_ITERATIONS : ITERATIONS;

  for (let iter = 0; iter < iterations; iter++) {
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

    for (const n of connected) {
      const p = points.get(n.id)!;
      const anchor = (opts.groupOf && groups.get(opts.groupOf(n.id) ?? "")) || null;
      if (anchor) {
        p.vx -= (p.x - anchor.x) * GROUP_PULL;
        p.vy -= (p.y - anchor.y) * GROUP_PULL;
      } else {
        p.vx -= p.x * CENTER_PULL;
        p.vy -= p.y * CENTER_PULL;
      }
      p.vx *= DAMPING;
      p.vy *= DAMPING;
      p.x += p.vx;
      p.y += p.vy;
    }
  }

  // orphan grid on the right periphery of the connected web
  let maxX = 0;
  let minY = 0;
  for (const p of points.values()) {
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
  }
  if (points.size === 0) {
    maxX = -ORPHAN_GAP_X; // no connected nodes: grid becomes the whole view
    minY = 0;
  }
  const cols = Math.max(1, Math.ceil(Math.sqrt(orphans.length)));
  const orphanPos = new Map<string, { x: number; y: number }>();
  orphans.forEach((n, i) => {
    const kept = opts.initial?.get(n.id);
    if (kept) {
      orphanPos.set(n.id, { x: kept.x + NODE_W / 2, y: kept.y + NODE_H / 2 });
      return;
    }
    orphanPos.set(n.id, {
      x: maxX + ORPHAN_GAP_X * (1.5 + (i % cols)),
      y: minY + ORPHAN_GAP_Y * Math.floor(i / cols),
    });
  });

  return nodes.map((n) => {
    const p = points.get(n.id) ?? orphanPos.get(n.id)!;
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}
