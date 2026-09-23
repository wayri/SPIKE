import type { TopologyDomain, TopologyEdge, TopologyNode } from "./powerTree";
import { topologyPorts } from "./topologyPorts";
import { numericMaximum } from "./numericRange";

export const schematicWidth = 210;
export function schematicHeight(node: TopologyNode, domain: TopologyDomain) {
  const ports = topologyPorts(node, domain);
  return Math.max(112, 48 + numericMaximum(["left", "right"].map(side => ports.filter(p => p.side === side).length)) * 24);
}
export function schematicPort(node: TopologyNode, domain: TopologyDomain, portId: string | undefined, fallback: "left" | "right") {
  const ports = topologyPorts(node, domain);
  const port = ports.find(p => p.id === portId) ?? ports.find(p => p.side === fallback) ?? ports[0];
  const side = port?.side ?? fallback;
  const siblings = ports.filter(p => p.side === side);
  return { x: node.x + (side === "right" ? schematicWidth : 0), y: node.y + (Math.max(0, siblings.findIndex(p => p.id === port?.id)) + 1) * schematicHeight(node, domain) / (siblings.length + 1), side };
}
export function schematicWire(edge: TopologyEdge, nodes: TopologyNode[], domain: TopologyDomain) {
  const from = nodes.find(n => n.id === edge.from), to = nodes.find(n => n.id === edge.to);
  if (!from || !to) return null;
  const a = schematicPort(from, domain, edge.fromPort, "right"), b = schematicPort(to, domain, edge.toPort, "left");
  const start = a.x + (a.side === "right" ? 24 : -24), end = b.x + (b.side === "left" ? -24 : 24);
  if (a.side === "right" && b.side === "left" && end >= start) {
    const bend = (start + end) / 2;
    return { d: `M ${a.x} ${a.y} H ${bend} V ${b.y} H ${b.x}`, a, b, labelX: (a.x + bend) / 2, labelY: a.y - 8 };
  }
  // Feedback and same-side ports leave their symbol before using a lower corridor.
  const bottom = numericMaximum([
    ...nodes.filter(n => n.x + schematicWidth >= Math.min(start, end) && n.x <= Math.max(start, end)).map(n => n.y + schematicHeight(n, domain)),
    a.y,
    b.y,
  ]) + 36;
  return { d: `M ${a.x} ${a.y} H ${start} V ${bottom} H ${end} V ${b.y} H ${b.x}`, a, b, labelX: (start + end) / 2, labelY: bottom - 8 };
}
