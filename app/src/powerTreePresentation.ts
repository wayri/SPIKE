// SPDX-License-Identifier: Apache-2.0
import type { TopologyEdge, TopologyModel, TopologyNode } from "./powerTree";

export const POWER_CARD_WIDTH = 218;
export const POWER_CARD_HEIGHT = 112;
export type PowerViewEdge = TopologyEdge & { viaRailIds?: string[]; viaRailLabels?: string[] };
export type PowerTreePresentation = {
  nodes: (TopologyNode & { viewX: number; viewY: number })[];
  edges: PowerViewEdge[];
  width: number; height: number;
  cyclicIds: Set<string>; hiddenCount: number; shuntCount: number;
  inlineRailCount?: number;
  error?: string;
};

/** Display-only graph projection. Never changes electrical identity or saved coordinates. */
export function presentPowerTree(model: TopologyModel, collapsed: ReadonlySet<string>, showShunts = false, inlineRails = false): PowerTreePresentation {
  const empty = { nodes: [], edges: [], width: 800, height: 400, cyclicIds: new Set<string>(), hiddenCount: 0, shuntCount: 0 };
  if (model.nodes.length > 512 || model.edges.length > 4096) return { ...empty, error: "Overview supports up to 512 elements and 4,096 connections. Use the wiring editor or split this investigation into power paths." };
  const ids = new Set(model.nodes.map(node => node.id));
  if (ids.size !== model.nodes.length) return { ...empty, error: "Duplicate element identities prevent a safe overview. Repair them in the wiring editor." };
  let eligible = model.nodes.filter(node => node.kind !== "return" && (showShunts || node.orientation !== "shunt"));
  const byId = new Map(eligible.map(node => [node.id, node]));
  let edges: PowerViewEdge[] = model.edges.filter(edge => edge.kind === "power" && byId.has(edge.from) && byId.has(edge.to));
  let inlineRailCount = 0;
  // Straight-through rail cards become labeled wire segments. Source identities
  // and both edge evidence records remain in the saved model and inspector.
  if (inlineRails) for (const node of [...eligible]) {
    const into = edges.filter(edge => edge.to === node.id), out = edges.filter(edge => edge.from === node.id);
    if (node.kind !== "rail" || into.length !== 1 || out.length !== 1 || into[0].from === out[0].to || collapsed.has(node.id)) continue;
    const a = into[0], b = out[0];
    const explicit = (edge: TopologyEdge) => edge.inference?.confidence === "explicit" || (!edge.inference && edge.origin === "user" && edge.portBinding === "explicit");
    edges = edges.filter(edge => edge !== a && edge !== b);
    edges.push({...a,id:`view:${a.id}:${b.id}`,to:b.to,toPort:b.toPort,net:node.net ?? a.net ?? b.net,
      viaRailIds:[...(a.viaRailIds ?? []),node.id,...(b.viaRailIds ?? [])],
      viaRailLabels:[...(a.viaRailLabels ?? []),node.net || node.label,...(b.viaRailLabels ?? [])],
      inference:{confidence:explicit(a)&&explicit(b)?"explicit":"inferred",reviewRequired:!explicit(a)||!explicit(b),
        evidence:[...(a.inference?.evidence ?? ["Input connection has no retained inference evidence."]),...(b.inference?.evidence ?? ["Output connection has no retained inference evidence."])]}});
    eligible = eligible.filter(item => item.id !== node.id); inlineRailCount++;
  }
  const incoming = new Map<string, Set<string>>(), outgoing = new Map<string, Set<string>>();
  for (const edge of edges) {
    if (!incoming.has(edge.to)) incoming.set(edge.to, new Set());
    if (!outgoing.has(edge.from)) outgoing.set(edge.from, new Set());
    incoming.get(edge.to)!.add(edge.from); outgoing.get(edge.from)!.add(edge.to);
  }
  // A shared downstream rail survives collapse if any other upstream path remains.
  const hidden = new Set<string>();
  for (let pass = 0; pass < eligible.length; pass++) {
    let changed = false;
    for (const node of eligible) {
      const parents = incoming.get(node.id);
      if (!collapsed.has(node.id) && !hidden.has(node.id) && parents?.size && [...parents].every(id => collapsed.has(id) || hidden.has(id))) {
        hidden.add(node.id); changed = true;
      }
    }
    if (!changed) break;
  }
  const visible = eligible.filter(node => !hidden.has(node.id));
  const visibleIds = new Set(visible.map(node => node.id));
  const shownEdges = edges.filter(edge => visibleIds.has(edge.from) && visibleIds.has(edge.to) && !collapsed.has(edge.from));
  const degrees = new Map(visible.map(node => [node.id, 0]));
  const children = new Map<string, Set<string>>();
  for (const edge of shownEdges) {
    if (!children.has(edge.from)) children.set(edge.from, new Set());
    if (!children.get(edge.from)!.has(edge.to)) degrees.set(edge.to, degrees.get(edge.to)! + 1);
    children.get(edge.from)!.add(edge.to);
  }
  const ranks = new Map<string, number>();
  const queue = visible.filter(node => degrees.get(node.id) === 0).map(node => node.id);
  for (const id of queue) ranks.set(id, 0);
  for (let i = 0; i < queue.length; i++) {
    const id = queue[i];
    for (const child of children.get(id) ?? []) {
      ranks.set(child, Math.max(ranks.get(child) ?? 0, ranks.get(id)! + 1));
      degrees.set(child, degrees.get(child)! - 1);
      if (degrees.get(child) === 0) queue.push(child);
    }
  }
  // Kahn leftovers include cycles and their dependents; never present them as a tree.
  const cyclicIds = new Set(visible.filter(node => degrees.get(node.id)! > 0).map(node => node.id));
  const lastRank = Math.max(0, ...ranks.values()) + 1;
  for (const id of cyclicIds) ranks.set(id, lastRank);
  const rows = new Map<number, number>();
  const connectedIds = new Set(shownEdges.flatMap(edge => [edge.from,edge.to]));
  // Place unconnected review candidates after connected branches so an unknown
  // connector cannot visually impersonate the source of an adjacent wire.
  const orderedVisible = [...visible.filter(node => connectedIds.has(node.id)),...visible.filter(node => !connectedIds.has(node.id))];
  const nodes = orderedVisible.map(node => {
    const rank = ranks.get(node.id) ?? 0, row = rows.get(rank) ?? 0;
    rows.set(rank, row + 1);
    return { ...node, viewX: 36 + rank * 280, viewY: 44 + row * 160 };
  });
  return { nodes, edges: shownEdges, width: Math.max(800, ...nodes.map(node => node.viewX + POWER_CARD_WIDTH + 40)),
    height: Math.max(360, ...nodes.map(node => node.viewY + POWER_CARD_HEIGHT + 40)), cyclicIds,
    hiddenCount: hidden.size, inlineRailCount, shuntCount: model.nodes.filter(node => node.orientation === "shunt").length };
}
