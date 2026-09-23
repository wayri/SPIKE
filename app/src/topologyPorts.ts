import type {
  TopologyDomain, TopologyEdge, TopologyModel, TopologyNode, TopologyNodeKind,
  TopologyPort, TopologyPortDirection, TopologyPortKind, TopologyPortSide,
} from "./powerTree";

const topologyPort = (
  id: string, label: string, direction: TopologyPortDirection, kind: TopologyPortKind, side: TopologyPortSide,
  maximumConnections?: number,
): TopologyPort => ({ id, label, direction, kind, side, maximumConnections });

/** Electrically meaningful editable defaults; they do not assert a pin model. */
export function defaultTopologyPorts(
  kind: TopologyNodeKind, domain: TopologyDomain, orientation: TopologyNode["orientation"] = "block",
): TopologyPort[] {
  if (domain === "si") {
    switch (kind) {
      case "driver": return [topologyPort("out_1", "OUT1", "output", "signal", "right", 1), topologyPort("ref", "REF", "reference", "reference", "left")];
      case "receiver": return [topologyPort("in_1", "IN1", "input", "signal", "left", 1), topologyPort("ref", "REF", "reference", "reference", "left")];
      case "channel": return [topologyPort("in_1", "IN1", "input", "signal", "left", 1), topologyPort("out_1", "OUT1", "output", "signal", "right", 1), topologyPort("ref", "REF", "reference", "reference", "left")];
      case "connector":
      case "harness": return [
        topologyPort("a_1", "A1", "bidirectional", "signal", "left", 1), topologyPort("a_2", "A2", "bidirectional", "signal", "left", 1),
        topologyPort("b_1", "B1", "bidirectional", "signal", "right", 1), topologyPort("b_2", "B2", "bidirectional", "signal", "right", 1),
        topologyPort("shield", "SHLD", "reference", "shield", "left"),
      ];
      case "termination": return [topologyPort("signal", "SIG", "input", "signal", "left", 1), topologyPort("ref", "REF", "reference", "reference", "left")];
      default: return [topologyPort("in", "IN", "input", "signal", "left", 1), topologyPort("out", "OUT", "output", "signal", "right", 1)];
    }
  }
  switch (kind) {
    case "source": return [topologyPort("out", "OUT", "output", "power", "right"), topologyPort("return", "RET", "reference", "return", "left")];
    case "load": return [topologyPort("in", "IN", "input", "power", "left", 1), topologyPort("return", "RET", "reference", "return", "left")];
    case "regulator": return [
      topologyPort("vin", "VIN", "input", "power", "left", 1), topologyPort("vout", "VOUT", "output", "power", "right"),
      topologyPort("return", "GND", "reference", "return", "left"), topologyPort("enable", "EN", "control", "control", "left", 1),
    ];
    case "transformer": return [
      topologyPort("pri_p", "PRI+", "passive", "power", "left", 1), topologyPort("pri_n", "PRI-", "passive", "return", "left", 1),
      topologyPort("sec_p", "SEC+", "passive", "power", "right", 1), topologyPort("sec_n", "SEC-", "passive", "return", "right", 1),
    ];
    case "rail": return [topologyPort("in", "IN", "input", "power", "left"), topologyPort("out", "OUT", "output", "power", "right"), topologyPort("tap", "TAP", "output", "power", "right")];
    case "return": return [topologyPort("reference", "REF", "reference", "return", "left")];
    case "connector": return [
      topologyPort("in_1", "IN1", "input", "power", "left", 1), topologyPort("in_2", "IN2", "input", "power", "left", 1),
      topologyPort("out_1", "OUT1", "output", "power", "right"), topologyPort("out_2", "OUT2", "output", "power", "right"), topologyPort("return", "RET", "reference", "return", "left"),
    ];
    case "harness": return [
      topologyPort("a_power", "A+", "bidirectional", "power", "left", 1), topologyPort("a_return", "A-", "bidirectional", "return", "left", 1),
      topologyPort("b_power", "B+", "bidirectional", "power", "right", 1), topologyPort("b_return", "B-", "bidirectional", "return", "right", 1),
    ];
    case "passive": return orientation === "shunt" ? [
      topologyPort("line", "LINE", "passive", "power", "left", 1), topologyPort("return", "REF", "passive", "return", "right", 1),
    ] : [topologyPort("in", "IN", "passive", "power", "left", 1), topologyPort("out", "OUT", "passive", "power", "right", 1)];
    default: return [topologyPort("in", "IN", "input", "power", "left", 1), topologyPort("out", "OUT", "output", "power", "right")];
  }
}

export const topologyPorts = (node: TopologyNode, domain: TopologyDomain): TopologyPort[] =>
  node.ports?.length ? node.ports : defaultTopologyPorts(node.kind, domain, node.orientation);

const preferredPort = (node: TopologyNode, domain: TopologyDomain, side: TopologyPortSide, edgeKind?: TopologyEdge["kind"]) => {
  const ports = topologyPorts(node, domain);
  if (edgeKind === "return") {
    const referencePorts = ports.filter(port => ["return", "reference", "shield"].includes(port.kind));
    if (referencePorts.length) return referencePorts.find(port => port.side === side)?.id ?? referencePorts[0].id;
  }
  if (edgeKind === "control") {
    const controls = ports.filter(port => port.kind === "control");
    if (controls.length) return controls.find(port => port.side === side)?.id ?? controls[0].id;
  }
  const sameKind = ports.filter(port => port.side === side && (!edgeKind || port.kind === edgeKind || (edgeKind === "signal" && port.kind === "reference")));
  return (sameKind.length ? sameKind : ports.filter(port => port.side === side))[0]?.id ?? ports[0]?.id;
};

export function normalizeTopologyPorts(model: TopologyModel): TopologyModel {
  const nodes: TopologyNode[] = model.nodes.map(node => ({ ...node, ports: topologyPorts(node, model.domain).map(port => ({ ...port, bindingState: port.bindingState ?? "inferred" as const })) }));
  const byId = new Map(nodes.map(node => [node.id, node]));
  const edges = model.edges.map(edge => ({
    ...edge,
    fromPort: edge.fromPort ?? (byId.get(edge.from) ? preferredPort(byId.get(edge.from)!, model.domain, "right", edge.kind) : undefined),
    toPort: edge.toPort ?? (byId.get(edge.to) ? preferredPort(byId.get(edge.to)!, model.domain, "left", edge.kind) : undefined),
    portBinding: edge.fromPort && edge.toPort ? edge.portBinding ?? "explicit" : "inferred",
  }));
  return { ...model, nodes, edges };
}

export type TopologyValidationIssue = { severity: "error" | "warning"; code: string; message: string };

export function validateTopologyPorts(model: TopologyModel): TopologyValidationIssue[] {
  const issues: TopologyValidationIssue[] = [];
  const nodeIds = new Set<string>(); const edgeIds = new Set<string>();
  const portMaps = new Map<string, Map<string, TopologyPort>>();
  model.nodes.forEach(node => {
    if (nodeIds.has(node.id)) issues.push({ severity: "error", code: "duplicate_node", message: `Duplicate node ID ${node.id}.` });
    nodeIds.add(node.id);
    const map = new Map<string, TopologyPort>();
    topologyPorts(node, model.domain).forEach(port => {
      if (map.has(port.id)) issues.push({ severity: "error", code: "duplicate_port", message: `${node.label} contains duplicate port ID ${port.id}.` });
      map.set(port.id, port);
      if (port.maximumConnections !== undefined && (!Number.isInteger(port.maximumConnections) || port.maximumConnections < 1)) issues.push({ severity: "error", code: "invalid_connection_limit", message: `${node.label}.${port.label} has an invalid connection limit.` });
    });
    portMaps.set(node.id, map);
  });
  const connectionCounts = new Map<string, number>(); const endpointPairs = new Set<string>();
  model.edges.forEach(edge => {
    if (edgeIds.has(edge.id)) issues.push({ severity: "error", code: "duplicate_edge", message: `Duplicate edge ID ${edge.id}.` });
    edgeIds.add(edge.id);
    if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) issues.push({ severity: "error", code: "missing_node", message: `Connection ${edge.id} references a missing node.` });
    if (edge.from === edge.to) issues.push({ severity: "error", code: "self_loop", message: `Connection ${edge.id} loops back to the same block.` });
    if (Boolean(edge.fromPort) !== Boolean(edge.toPort)) issues.push({ severity: "error", code: "half_bound_edge", message: `Connection ${edge.id} must specify both endpoint ports or neither.` });
    if (!edge.fromPort || !edge.toPort) { issues.push({ severity: "warning", code: "legacy_edge", message: `Connection ${edge.id} has unresolved legacy port endpoints.` }); return; }
    const fromPort = portMaps.get(edge.from)?.get(edge.fromPort); const toPort = portMaps.get(edge.to)?.get(edge.toPort);
    if (!fromPort || !toPort) { issues.push({ severity: "error", code: "missing_port", message: `Connection ${edge.id} references a missing endpoint port.` }); return; }
    if (["input", "control"].includes(fromPort.direction) || toPort.direction === "output") issues.push({ severity: "error", code: "port_direction", message: `Connection ${edge.id} has incompatible port directions.` });
    const electricalClass = (port: TopologyPort) => ["return", "reference", "shield"].includes(port.kind) ? "reference" : port.kind;
    if (electricalClass(fromPort) !== electricalClass(toPort)) issues.push({ severity: "error", code: "port_kind", message: `Connection ${edge.id} has incompatible electrical port kinds.` });
    const pairKey = `${edge.from}\u0000${edge.fromPort}\u0000${edge.to}\u0000${edge.toPort}`;
    if (endpointPairs.has(pairKey)) issues.push({ severity: "error", code: "duplicate_endpoints", message: `Connection ${edge.id} duplicates an existing endpoint pair.` });
    endpointPairs.add(pairKey);
    const endpoints: [string, string, TopologyPort][] = [[edge.from, edge.fromPort, fromPort], [edge.to, edge.toPort, toPort]];
    endpoints.forEach(([nodeId, portId, port]) => {
      const key = `${nodeId}\u0000${portId}`; const count = (connectionCounts.get(key) ?? 0) + 1; connectionCounts.set(key, count);
      if (port.maximumConnections !== undefined && count > port.maximumConnections) issues.push({ severity: "error", code: "connection_limit", message: `Port ${nodeId}.${port.label} exceeds its connection limit.` });
    });
  });
  return issues;
}

const textValue = (value: unknown) => value === undefined ? "-" : JSON.stringify(value);
const codeUnitCompare = (left: string, right: string) => left < right ? -1 : left > right ? 1 : 0;
const stableValue = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value as Record<string, unknown>)
    .filter(([, item]) => item !== undefined).sort(([left], [right]) => codeUnitCompare(left, right)).map(([key, item]) => [key, stableValue(item)]));
  if (typeof value === "number" && !Number.isFinite(value)) throw new Error("Topology text cannot represent non-finite numbers.");
  return Object.is(value, -0) ? 0 : value;
};
const stableJson = (value: unknown) => JSON.stringify(stableValue(value));

/** Deterministic, read-only semantic text; canvas coordinates are excluded. */
export function topologyToText(source: TopologyModel): string {
  const model = normalizeTopologyPorts(source);
  const lines = ["SPIKE TOPOLOGY TEXT v1", `DOMAIN ${model.domain.toUpperCase()}`, `NAME ${textValue(model.name)}`, `SOURCE ${model.extraction.source}`, `SCENARIOS ${stableJson([...(model.scenarios ?? [])].sort((a, b) => codeUnitCompare(a.id, b.id)))}`];
  [...model.nodes].sort((a, b) => codeUnitCompare(a.id, b.id)).forEach(node => {
    const { id: _id, kind: _kind, label: _label, ref: _ref, net: _net, origin: _origin, x: _x, y: _y, ports: _ports, ...properties } = node;
    lines.push(`NODE ${textValue(node.id)} kind=${node.kind} label=${textValue(node.label)} ref=${textValue(node.ref)} net=${textValue(node.net)} origin=${node.origin}`);
    if (Object.keys(stableValue(properties) as object).length) lines.push(`  PROPERTIES ${stableJson(properties)}`);
    topologyPorts(node, model.domain).sort((a, b) => codeUnitCompare(a.id, b.id)).forEach(port => lines.push(`  PORT ${textValue(port.id)} label=${textValue(port.label)} direction=${port.direction} kind=${port.kind} side=${port.side} net=${textValue(port.net)} lane=${textValue(port.lane)} pair=${textValue(port.pair)} binding=${port.bindingState ?? "unassigned"} pads=${stableJson(port.padIds ?? [])} maximum_connections=${textValue(port.maximumConnections)}`));
  });
  [...model.edges].sort((a, b) => codeUnitCompare(`${a.from}\u0000${a.to}\u0000${a.kind}\u0000${a.net ?? ""}\u0000${a.id}`, `${b.from}\u0000${b.to}\u0000${b.kind}\u0000${b.net ?? ""}\u0000${b.id}`)).forEach(edge => lines.push(`CONNECT ${textValue(edge.id)} ${textValue(edge.from)}.${textValue(edge.fromPort)} -> ${textValue(edge.to)}.${textValue(edge.toPort)} kind=${edge.kind} net=${textValue(edge.net)} origin=${edge.origin} port_binding=${edge.portBinding ?? "inferred"}`));
  [...model.extraction.warnings].sort(codeUnitCompare).forEach(warning => lines.push(`NOTICE ${textValue(warning)}`));
  return `${lines.join("\n")}\n`;
}
