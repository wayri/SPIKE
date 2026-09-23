import type { ParsedBoard } from "./boardParser";
import { normalizeTopologyPorts } from "./topologyPorts";
import { boardComponents, classifyComponent } from "./topologyExtraction";
export { extractTopologyFromBoard, extractTopologyFromXmlNetlist } from "./topologyExtraction";
export { defaultTopologyPorts, normalizeTopologyPorts, topologyPorts, topologyToText, validateTopologyPorts } from "./topologyPorts";
export type { TopologyValidationIssue } from "./topologyPorts";

export type TopologyDomain = "pi" | "si";
export type TopologyOperatingPoint = {
  enabled?: boolean;
  currentA?: number;
  powerW?: number;
};

export type TopologyScenario = {
  id: string;
  label: string;
  loadMultiplier: number;
};

export type TopologyNodeKind =
  | "source"
  | "regulator"
  | "transformer"
  | "rail"
  | "return"
  | "connector"
  | "harness"
  | "load"
  | "passive"
  | "driver"
  | "channel"
  | "receiver"
  | "termination";

export type TopologyPinRole = "input" | "output" | "return" | "control" | "passive" | "unused";
export type TopologyCircuitPin = { pad_id: string; circuit_node: string; role?: TopologyPinRole };
export type TopologyPortDirection = "input" | "output" | "bidirectional" | "reference" | "control" | "passive";
export type TopologyPortKind = "power" | "return" | "signal" | "reference" | "control" | "shield";
export type TopologyPortSide = "left" | "right";
export type TopologyPort = {
  id: string;
  label: string;
  direction: TopologyPortDirection;
  kind: TopologyPortKind;
  side: TopologyPortSide;
  net?: string;
  lane?: string;
  pair?: string;
  padIds?: string[];
  maximumConnections?: number;
  bindingState?: "unassigned" | "bound" | "inferred";
};
export type TopologyCircuitModel = {
  primitive?: "resistor" | "inductor" | "capacitor";
  type?: string;
  value?: string;
  orientation?: "series" | "shunt";
  pins?: TopologyCircuitPin[];
};

export type TopologyNode = {
  id: string;
  kind: TopologyNodeKind;
  label: string;
  ref?: string;
  net?: string;
  value?: string;
  orientation?: "series" | "shunt" | "block";
  simulationModel?: string;
  voltageV?: number;
  loadCurrentA?: number;
  loadPowerW?: number;
  efficiencyPercent?: number;
  maxCurrentA?: number;
  resistanceOhm?: number;
  enabled?: boolean;
  operatingPoints?: Record<string, TopologyOperatingPoint>;
  modelLink?: string;
  isolationDomain?: string;
  terminalPadId?: string;
  pinRoles?: Record<string, TopologyPinRole>;
  modelParameters?: Record<string, string | number | boolean>;
  solverPolicy?: "geometry" | "ngspice" | "staged_hybrid";
  circuitModel?: TopologyCircuitModel;
  ports?: TopologyPort[];
  pathGroupId?: string;
  pathGroupLabel?: string;
  x: number;
  y: number;
  origin: "extracted" | "user";
};

export type PowerNodeBudget = {
  nodeId: string;
  voltageV?: number;
  currentA: number;
  inputPowerW: number;
  outputPowerW: number;
  lossW: number;
  efficiencyPercent?: number;
};

export type PowerTreeBudget = {
  status: "complete" | "incomplete" | "invalid";
  scenarioId?: string;
  loadMultiplier: number;
  sourcePowerW: number;
  loadPowerW: number;
  lossW: number;
  efficiencyPercent?: number;
  nodes: Record<string, PowerNodeBudget>;
  rails: PowerRailBudget[];
  warnings: string[];
};

export type PowerRailBudget = {
  nodeId: string;
  net: string;
  voltageV?: number;
  currentA: number;
  powerW: number;
  downstreamLoadIds: string[];
  status: "ready" | "needs_setup" | "overloaded";
};

export type PowerTreeAnalysisJob = {
  id: string;
  railNodeId: string;
  net: string;
  sourceNodeIds: string[];
  loadNodeIds: string[];
  voltageV?: number;
  totalCurrentA: number;
  loadPowerW: number;
  status: "ready" | "needs_setup";
  warnings: string[];
};

export type PowerTreeAnalysisPlan = {
  contract: "spike/power-tree-analysis-plan/v1";
  status: "ready" | "needs_setup" | "invalid";
  scenarioId: string;
  budget: PowerTreeBudget;
  jobs: PowerTreeAnalysisJob[];
  warnings: string[];
};

export type TopologyEdge = {
  id: string;
  from: string;
  to: string;
  fromPort?: string;
  toPort?: string;
  portBinding?: "explicit" | "inferred";
  net?: string;
  kind: "power" | "return" | "signal" | "control";
  origin: "extracted" | "user";
};

export type TopologyModel = {
  contract: "spike/topology/v1";
  domain: TopologyDomain;
  name: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  scenarios?: TopologyScenario[];
  extraction: {
    source: "board_netlist" | "kicad_schematic+board_netlist" | "kicad_xml_netlist" | "manual";
    generatedAt: string;
    warnings: string[];
  };
};

export const slug = (value: string) => value.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase() || "item";
const unique = <T,>(values: T[]) => [...new Set(values)];
export const defaultTopologyScenarios = (): TopologyScenario[] => [
  { id: "typical", label: "Typical", loadMultiplier: 1 },
  { id: "maximum", label: "Maximum", loadMultiplier: 1.25 },
  { id: "standby", label: "Standby", loadMultiplier: 0.1 },
];
export const topologyScenarios = (model: TopologyModel): TopologyScenario[] =>
  model.scenarios?.length ? model.scenarios : defaultTopologyScenarios();
export const returnName = /(^|[/_.+-])(gnd|agnd|dgnd|pgnd|vss)(?:$|[/_.+-])/i;
export const isPowerNet = (net: string) => {
  if (returnName.test(net)) return false;
  const leaf = net.split("/").filter(Boolean).pop() ?? net;
  return /^(vcc|vdd|vin|vout|vbat|bat|pwr|power|usb_vbus|[+-]?\d+(?:v\d*|(?:\.\d+)?v(?:out|in)?)(?:_[a-z0-9]+)?)$/i.test(leaf)
    || /(?:^|[_+-])(vin|vout|vcc|vdd|vbat|pwr)(?:$|[_+-])/i.test(leaf);
};
export const signalName = /(clk|clock|data|uart|spi|i2c|sda|scl|usb|can|eth|pcie|ddr|rx|tx|mosi|miso|cs|diff|_p$|_n$)/i;

const seriesModelFor = (ref: string, kind: TopologyNodeKind) => {
  if (/^R/i.test(ref)) return "resistor";
  if (/^(L|FB)/i.test(ref)) return "inductor";
  if (/^C/i.test(ref)) return "capacitor";
  if (/^D/i.test(ref)) return "diode";
  if (/^Q/i.test(ref)) return "mosfet";
  if (kind === "transformer") return "isolated_transformer";
  if (kind === "regulator") return "spice_subcircuit";
  return "spice_subcircuit";
};

/**
 * Build a reviewable source-to-load power path from two explicit board pads.
 * Ground nets are excluded from series traversal and reintroduced as shunt
 * return nodes, so they cannot collapse the whole board into one false path.
 */
export function extractPowerPathFromBoard(board: ParsedBoard, sourcePadId: string, loadPadId: string): TopologyModel {
  const sourcePad = board.pads.find(pad => pad.id === sourcePadId);
  const loadPad = board.pads.find(pad => pad.id === loadPadId);
  if (!sourcePad?.net || !loadPad?.net) throw new Error("Select source and load pads with assigned nets.");
  const components = boardComponents(board);
  const componentByRef = new Map(components.map(component => [component.ref, component]));
  const traversable = components.filter(component => {
    const nonReturnNets = unique(component.nets.filter(net => !returnName.test(net)));
    const kind = classifyComponent(component, "pi");
    return nonReturnNets.length >= 2 && (/^(R|L|FB|F|D|Q|T|XFMR|U|IC)/i.test(component.ref) || kind === "regulator" || kind === "transformer");
  });
  const adjacency = new Map<string, { net: string; ref: string }[]>();
  traversable.forEach(component => {
    const nets = unique(component.nets.filter(net => !returnName.test(net)));
    nets.forEach(from => nets.filter(to => to !== from).forEach(to => adjacency.set(from, [...(adjacency.get(from) ?? []), { net: to, ref: component.ref }])));
  });
  const queue = [sourcePad.net];
  const previous = new Map<string, { net: string; ref: string }>();
  const visited = new Set(queue);
  while (queue.length && !visited.has(loadPad.net)) {
    const current = queue.shift()!;
    for (const step of adjacency.get(current) ?? []) {
      if (visited.has(step.net)) continue;
      visited.add(step.net);
      previous.set(step.net, { net: current, ref: step.ref });
      queue.push(step.net);
    }
  }
  const netPath = [loadPad.net];
  const refPath: string[] = [];
  while (netPath[0] !== sourcePad.net) {
    const step = previous.get(netPath[0]);
    if (!step) break;
    refPath.unshift(step.ref);
    netPath.unshift(step.net);
  }
  const complete = netPath[0] === sourcePad.net;
  if (!complete) {
    netPath.splice(0, netPath.length, sourcePad.net);
    if (loadPad.net !== sourcePad.net) netPath.push(loadPad.net);
  }
  const nodes: TopologyNode[] = [];
  const edges: TopologyEdge[] = [];
  const pathGroupId = `power-path-${slug(sourcePad.id)}-${slug(loadPad.id)}`;
  const pathGroupLabel = `${sourcePad.ref ?? "Input"}.${sourcePad.name} -> ${loadPad.ref ?? "Output"}.${loadPad.name}`;
  const sourceId = `pi-path-source-${slug(sourcePad.id)}`;
  const loadId = `pi-path-load-${slug(loadPad.id)}`;
  nodes.push({
    id: sourceId, kind: "source", label: `${sourcePad.ref ?? "Input"}.${sourcePad.name}`,
    ref: sourcePad.ref, net: sourcePad.net, terminalPadId: sourcePad.id, voltageV: inferredVoltage({ id: sourceId, kind: "source", label: sourcePad.net, net: sourcePad.net, x: 0, y: 0, origin: "user" }),
    simulationModel: "dc_source", solverPolicy: "staged_hybrid", orientation: "block", pathGroupId, pathGroupLabel, x: 0, y: 0, origin: "user",
  });
  netPath.forEach(net => nodes.push({ id: `pi-path-net-${slug(net)}`, kind: "rail", label: net, net, orientation: "series", pathGroupId, pathGroupLabel, x: 0, y: 0, origin: "extracted" }));
  nodes.push({
    id: loadId, kind: "load", label: `${loadPad.ref ?? "Output"}.${loadPad.name}`,
    ref: loadPad.ref, net: loadPad.net, terminalPadId: loadPad.id, simulationModel: "constant_current", solverPolicy: "staged_hybrid", orientation: "block", pathGroupId, pathGroupLabel, x: 0, y: 0, origin: "user",
  });
  edges.push({ id: `${sourceId}-feed`, from: sourceId, to: `pi-path-net-${slug(netPath[0])}`, net: netPath[0], kind: "power", origin: "user" });
  refPath.forEach((ref, index) => {
    const component = componentByRef.get(ref)!;
    const kind = classifyComponent(component, "pi");
    const nodeId = `pi-path-component-${slug(ref)}`;
    const inputNet = netPath[index];
    const outputNet = netPath[index + 1];
    const pinRoles: Record<string, TopologyPinRole> = {};
    board.pads.filter(pad => pad.ref === ref).forEach(pad => {
      pinRoles[pad.name] = pad.net === inputNet ? "input" : pad.net === outputNet ? "output" : pad.net && returnName.test(pad.net) ? "return" : "unused";
    });
    const componentPads = board.pads.filter(pad => pad.ref === ref);
    const inputPad = componentPads.find(pad => pad.net === inputNet);
    const outputPad = componentPads.find(pad => pad.net === outputNet);
    const circuitPins = [
      inputPad && { pad_id: inputPad.id, circuit_node: `N_${slug(inputNet).replace(/-/g, "_")}`, role: "input" as const },
      outputPad && { pad_id: outputPad.id, circuit_node: `N_${slug(outputNet).replace(/-/g, "_")}`, role: "output" as const },
    ].filter((pin): pin is NonNullable<typeof pin> => Boolean(pin));
    const primitive = /^(R)/i.test(ref) ? "resistor" as const : /^(L|FB)/i.test(ref) ? "inductor" as const : undefined;
    nodes.push({
      id: nodeId, kind, label: ref, ref, value: component.value, orientation: "series",
      simulationModel: seriesModelFor(ref, kind), solverPolicy: /^(R|L|FB|C)/i.test(ref) ? "staged_hybrid" : "ngspice",
      pinRoles, resistanceOhm: /^R/i.test(ref) ? inferredResistance(component.value) : undefined,
      circuitModel: primitive ? { primitive, type: primitive, value: component.value, orientation: "series", pins: circuitPins } : undefined,
      pathGroupId, pathGroupLabel,
      x: 0, y: 0, origin: "extracted",
    });
    edges.push({ id: `${nodeId}-input`, from: `pi-path-net-${slug(inputNet)}`, to: nodeId, net: inputNet, kind: "power", origin: "extracted" });
    edges.push({ id: `${nodeId}-output`, from: nodeId, to: `pi-path-net-${slug(outputNet)}`, net: outputNet, kind: "power", origin: "extracted" });
  });
  edges.push({ id: `${loadId}-feed`, from: `pi-path-net-${slug(netPath[netPath.length - 1])}`, to: loadId, net: netPath[netPath.length - 1], kind: "power", origin: "user" });
  const pathRefs = new Set(refPath);
  const shunts = components.filter(component => {
    if (pathRefs.has(component.ref)) return false;
    const rails = component.nets.filter(net => netPath.includes(net));
    const returns = component.nets.filter(net => returnName.test(net));
    return rails.length > 0 && returns.length > 0 && /^(C|R|L|FB)/i.test(component.ref);
  });
  const returnNets = unique([
    ...board.pads.filter(pad => pad.ref && pathRefs.has(pad.ref) && pad.net && returnName.test(pad.net)).map(pad => pad.net!),
    ...shunts.flatMap(component => component.nets.filter(net => returnName.test(net))),
  ]);
  returnNets.forEach(net => {
    const returnId = `pi-path-return-${slug(net)}`;
    nodes.push({ id: returnId, kind: "return", label: net, net, orientation: "shunt", voltageV: 0, isolationDomain: net, pathGroupId, pathGroupLabel, x: 0, y: 0, origin: "extracted" });
    refPath.forEach(ref => {
      if (board.pads.some(pad => pad.ref === ref && pad.net === net)) edges.push({ id: `${slug(ref)}-${slug(net)}-return`, from: `pi-path-component-${slug(ref)}`, to: returnId, net, kind: "return", origin: "extracted" });
    });
  });
  shunts.forEach(component => {
    const railNet = component.nets.find(net => netPath.includes(net));
    const returnNet = component.nets.find(net => returnName.test(net));
    if (!railNet || !returnNet) return;
    const nodeId = `pi-path-shunt-${slug(component.ref)}`;
    const railPad = board.pads.find(pad => pad.ref === component.ref && pad.net === railNet);
    const returnPad = board.pads.find(pad => pad.ref === component.ref && pad.net === returnNet);
    const primitive = /^C/i.test(component.ref) ? "capacitor" as const : /^R/i.test(component.ref) ? "resistor" as const : "inductor" as const;
    nodes.push({
      id: nodeId, kind: "passive", label: component.ref, ref: component.ref, net: railNet, value: component.value,
      orientation: "shunt", simulationModel: primitive, solverPolicy: "staged_hybrid",
      pinRoles: railPad && returnPad ? { [railPad.name]: "input", [returnPad.name]: "return" } : undefined,
      circuitModel: railPad && returnPad ? {
        primitive, type: primitive, value: component.value, orientation: "shunt",
        pins: [
          { pad_id: railPad.id, circuit_node: `N_${slug(railNet).replace(/-/g, "_")}`, role: "input" },
          { pad_id: returnPad.id, circuit_node: `N_${slug(returnNet).replace(/-/g, "_")}`, role: "return" },
        ],
      } : undefined,
      pathGroupId, pathGroupLabel, x: 0, y: 0, origin: "extracted",
    });
    edges.push({ id: `${nodeId}-rail`, from: `pi-path-net-${slug(railNet)}`, to: nodeId, net: railNet, kind: "power", origin: "extracted" });
    edges.push({ id: `${nodeId}-return`, from: nodeId, to: `pi-path-return-${slug(returnNet)}`, net: returnNet, kind: "return", origin: "extracted" });
  });
  const warnings = complete ? [] : ["No unambiguous series component path was found between the selected pads. The endpoints are retained for manual construction."];
  return normalizeTopologyPorts({
    contract: "spike/topology/v1", domain: "pi", name: `${sourcePad.ref ?? "Input"} to ${loadPad.ref ?? "Output"} power path`,
    nodes: layoutTopology(nodes, edges), edges, scenarios: defaultTopologyScenarios(),
    extraction: { source: "board_netlist", generatedAt: new Date().toISOString(), warnings },
  });
}

export function layoutTopology(nodes: TopologyNode[], edges: TopologyEdge[]): TopologyNode[] {
  // Longest-path ranks have no depth cap. References do not push the signal flow
  // backwards; cyclic leftovers remain visible for validation and manual wiring.
  const ids = new Set(nodes.map(node => node.id));
  const forward = edges.filter(edge => edge.kind !== "return" && ids.has(edge.from) && ids.has(edge.to));
  const incoming = new Map(nodes.map(node => [node.id, 0]));
  const children = new Map(nodes.map(node => [node.id, [] as string[]]));
  const parents = new Map(nodes.map(node => [node.id, [] as string[]]));
  const rank = new Map(nodes.map(node => [node.id, 0]));
  forward.forEach(edge => { incoming.set(edge.to, incoming.get(edge.to)! + 1); children.get(edge.from)!.push(edge.to); parents.get(edge.to)!.push(edge.from); });
  const queue = nodes.filter(node => incoming.get(node.id) === 0).map(node => node.id);
  for (let i = 0; i < queue.length; i++) {
    const id = queue[i];
    children.get(id)!.forEach(child => {
      rank.set(child, Math.max(rank.get(child)!, rank.get(id)! + 1));
      incoming.set(child, incoming.get(child)! - 1);
      if (incoming.get(child) === 0) queue.push(child);
    });
  }
  let cycleColumn = Math.max(0, ...rank.values()) + 1;
  nodes.filter(node => incoming.get(node.id)! > 0).forEach(node => rank.set(node.id, cycleColumn++));
  edges.filter(edge => edge.kind === "return").forEach(edge => {
    if (ids.has(edge.to) && ids.has(edge.from)) rank.set(edge.to, rank.get(edge.from)!);
  });
  const rows = new Map<number, TopologyNode[]>();
  nodes.forEach(node => { const key = rank.get(node.id) ?? 0; if (!rows.has(key)) rows.set(key, []); rows.get(key)!.push(node); });
  const positions = new Map<string, number>();
  [...rows.entries()].sort(([a], [b]) => a - b).forEach(([, column]) => {
    const parentY = (node: TopologyNode) => {
      const upstream = parents.get(node.id)!;
      return upstream.length ? upstream.reduce((sum, id) => sum + (positions.get(id) ?? 60), 0) / upstream.length : 60;
    };
    column.sort((a, b) => Number(a.kind === "return") - Number(b.kind === "return") || parentY(a) - parentY(b));
    let bottom = 60;
    column.forEach(node => {
      const y = Math.max(bottom, parentY(node));
      positions.set(node.id, y);
      const ports = node.ports ?? [];
      bottom = y + Math.max(160, 80 + Math.max(ports.filter(p => p.side === "left").length, ports.filter(p => p.side === "right").length) * 24);
    });
  });
  return nodes.map(node => {
    const column = rank.get(node.id) ?? 0;
    return { ...node, x: 60 + column * 320, y: positions.get(node.id) ?? 60 };
  });
}

export const inferredVoltage = (node: TopologyNode): number | undefined => {
  const text = `${node.net ?? ""} ${node.label}`;
  const decimal = text.match(/(?:^|[^0-9])([0-9]{1,3})[vV]([0-9]{1,3})(?:[^0-9]|$)/);
  if (decimal) return Number(`${decimal[1]}.${decimal[2]}`);
  const volts = text.match(/(?:^|[^0-9])([0-9]+(?:\.[0-9]+)?)\s*[vV](?:[^a-zA-Z]|$)/);
  return volts ? Number(volts[1]) : undefined;
};

const inferredResistance = (value?: string): number | undefined => {
  if (!value) return undefined;
  const normalized = value.trim().replace(/ohms?|\u03a9/gi, "");
  const match = normalized.match(/^([0-9]*\.?[0-9]+)\s*([munkM]?)(?:[rR]([0-9]+))?/);
  if (!match) {
    const embedded = normalized.match(/^([0-9]+)[rR]([0-9]+)$/);
    return embedded ? Number(`${embedded[1]}.${embedded[2]}`) : undefined;
  }
  const scale: Record<string, number> = { m: 1e-3, u: 1e-6, n: 1e-9, k: 1e3, M: 1e6, "": 1 };
  const base = match[3] ? Number(`${match[1]}.${match[3]}`) : Number(match[1]);
  return base * (scale[match[2]] ?? 1);
};

export function calculatePowerTree(model: TopologyModel, operatingCase: number | string = "typical"): PowerTreeBudget {
  const selectedScenario = typeof operatingCase === "string"
    ? topologyScenarios(model).find(item => item.id === operatingCase) ?? topologyScenarios(model)[0]
    : undefined;
  const multiplierValue = typeof operatingCase === "number" ? operatingCase : selectedScenario?.loadMultiplier ?? 1;
  const multiplier = Number.isFinite(multiplierValue) && multiplierValue >= 0 ? multiplierValue : 1;
  const scenarioId = selectedScenario?.id;
  const operatingPoint = (node: TopologyNode) => scenarioId ? node.operatingPoints?.[scenarioId] : undefined;
  const activeNodes = model.nodes.filter(node => node.enabled !== false && operatingPoint(node)?.enabled !== false);
  const nodeById = new Map(activeNodes.map(node => [node.id, node]));
  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  model.edges.filter(edge => edge.kind === "power" && nodeById.has(edge.from) && nodeById.has(edge.to)).forEach(edge => {
    outgoing.set(edge.from, [...(outgoing.get(edge.from) ?? []), edge.to]);
    incoming.set(edge.to, [...(incoming.get(edge.to) ?? []), edge.from]);
  });
  const warnings = [...model.extraction.warnings];
  activeNodes.filter(node => (incoming.get(node.id)?.length ?? 0) > 1).forEach(node => warnings.push(`${node.label} has multiple upstream paths; parallel-source sharing requires a circuit solver.`));

  const voltages = new Map<string, number>();
  activeNodes.forEach(node => {
    const voltage = node.voltageV ?? inferredVoltage(node);
    if (voltage !== undefined && voltage > 0) voltages.set(node.id, voltage);
  });
  for (let pass = 0; pass < Math.max(2, activeNodes.length); pass += 1) {
    activeNodes.forEach(node => {
      if (voltages.has(node.id)) return;
      const upstream = (incoming.get(node.id) ?? []).map(id => voltages.get(id)).find(value => value !== undefined);
      if (upstream !== undefined) voltages.set(node.id, upstream);
    });
  }

  const metrics: Record<string, PowerNodeBudget> = {};
  const visiting = new Set<string>();
  const memo = new Map<string, number>();
  let cycleFound = false;
  const demandAtInput = (id: string): number => {
    if (memo.has(id)) return memo.get(id)!;
    if (visiting.has(id)) { cycleFound = true; return 0; }
    visiting.add(id);
    const node = nodeById.get(id)!;
    const voltage = voltages.get(id);
    const downstreamPower = (outgoing.get(id) ?? []).reduce((sum, child) => sum + demandAtInput(child), 0);
    let outputPower = downstreamPower;
    if (node.kind === "load") {
      const point = operatingPoint(node);
      const explicitScenarioDemand = point?.powerW !== undefined || point?.currentA !== undefined;
      if (point?.powerW !== undefined) outputPower = Math.max(0, point.powerW);
      else if (point?.currentA !== undefined) outputPower = Math.max(0, point.currentA * (voltage ?? 0));
      else if (node.loadPowerW !== undefined) outputPower = Math.max(0, node.loadPowerW);
      else outputPower = Math.max(0, (node.loadCurrentA ?? 0) * (voltage ?? 0));
      if (!explicitScenarioDemand) outputPower *= multiplier;
      if (outputPower === 0) warnings.push(`${node.label} has no load current or power assignment.`);
    }
    const efficiency = node.kind === "regulator" || node.kind === "transformer" ? Math.min(100, Math.max(0.1, node.efficiencyPercent ?? 90)) : undefined;
    const resistance = Math.max(0, node.resistanceOhm ?? ((node.kind === "passive" || node.kind === "connector" || node.kind === "harness") ? inferredResistance(node.value) ?? 0 : 0));
    const point = operatingPoint(node);
    const current = voltage && voltage > 0 ? outputPower / voltage : point?.currentA ?? (node.loadCurrentA ? node.loadCurrentA * multiplier : 0);
    const conductionLoss = current * current * resistance;
    const inputPower = efficiency !== undefined ? outputPower / (efficiency / 100) : outputPower + conductionLoss;
    const loss = Math.max(0, inputPower - outputPower);
    metrics[id] = { nodeId: id, voltageV: voltage, currentA: current, inputPowerW: inputPower, outputPowerW: outputPower, lossW: loss, efficiencyPercent: efficiency };
    if (node.maxCurrentA !== undefined && current > node.maxCurrentA) warnings.push(`${node.label} exceeds its ${node.maxCurrentA.toFixed(3)} A current limit (${current.toFixed(3)} A).`);
    visiting.delete(id);
    memo.set(id, inputPower);
    return inputPower;
  };

  const sources = activeNodes.filter(node => node.kind === "source");
  const loads = activeNodes.filter(node => node.kind === "load");
  const sourcePowerW = sources.reduce((sum, node) => sum + demandAtInput(node.id), 0);
  activeNodes.forEach(node => { if (!metrics[node.id]) demandAtInput(node.id); });
  const loadPowerW = loads.reduce((sum, node) => sum + (metrics[node.id]?.outputPowerW ?? 0), 0);
  const reachable = new Set<string>();
  const pending = sources.map(node => node.id);
  while (pending.length) {
    const id = pending.pop()!;
    if (reachable.has(id)) continue;
    reachable.add(id);
    (outgoing.get(id) ?? []).forEach(child => pending.push(child));
  }
  if (!sources.length) warnings.push("No source is assigned.");
  if (!loads.length) warnings.push("No loads are assigned.");
  loads.filter(node => !(incoming.get(node.id)?.length)).forEach(node => warnings.push(`${node.label} is disconnected from the power path.`));
  loads.filter(node => sources.length && !reachable.has(node.id)).forEach(node => warnings.push(`${node.label} is not reachable from a source; complete the converter/rail connections or import the schematic netlist.`));
  sources.filter(node => !voltages.has(node.id)).forEach(node => warnings.push(`${node.label} has no source voltage assignment.`));
  if (cycleFound) warnings.push("The power tree contains a cycle; use the circuit solver for meshed or parallel networks.");
  const invalid = cycleFound || !sources.length || !loads.length;
  const incomplete = !invalid && (sourcePowerW <= 0 || warnings.some(warning => /no (load|source voltage)|not reachable|disconnected/i.test(warning)));
  const downstreamLoads = (rootId: string) => {
    const found = new Set<string>();
    const pendingIds = [...(outgoing.get(rootId) ?? [])];
    const visited = new Set<string>();
    while (pendingIds.length) {
      const id = pendingIds.pop()!;
      if (visited.has(id)) continue;
      visited.add(id);
      const node = nodeById.get(id);
      if (!node) continue;
      if (node.kind === "load") found.add(id);
      else (outgoing.get(id) ?? []).forEach(child => pendingIds.push(child));
    }
    return [...found];
  };
  const rails: PowerRailBudget[] = activeNodes.filter(node => node.kind === "rail" && node.net).map(node => {
    const nodeMetrics = metrics[node.id];
    const loadIds = downstreamLoads(node.id);
    const overloaded = node.maxCurrentA !== undefined && (nodeMetrics?.currentA ?? 0) > node.maxCurrentA;
    return {
      nodeId: node.id,
      net: node.net!,
      voltageV: nodeMetrics?.voltageV,
      currentA: nodeMetrics?.currentA ?? 0,
      powerW: nodeMetrics?.outputPowerW ?? 0,
      downstreamLoadIds: loadIds,
      status: overloaded ? "overloaded" : loadIds.length && (nodeMetrics?.voltageV ?? 0) > 0 && (nodeMetrics?.currentA ?? 0) > 0 ? "ready" : "needs_setup",
    };
  });
  return {
    status: invalid ? "invalid" : incomplete ? "incomplete" : "complete",
    scenarioId,
    loadMultiplier: multiplier,
    sourcePowerW,
    loadPowerW,
    lossW: Math.max(0, sourcePowerW - loadPowerW),
    efficiencyPercent: sourcePowerW > 0 ? 100 * loadPowerW / sourcePowerW : undefined,
    nodes: metrics,
    rails,
    warnings: unique(warnings),
  };
}

export function buildPowerTreeAnalysisPlan(model: TopologyModel, scenarioId = "typical"): PowerTreeAnalysisPlan {
  const budget = calculatePowerTree(model, scenarioId);
  const activeIds = new Set(model.nodes.filter(node => node.enabled !== false && node.operatingPoints?.[scenarioId]?.enabled !== false).map(node => node.id));
  const nodeById = new Map(model.nodes.map(node => [node.id, node]));
  const edges = model.edges.filter(edge => edge.kind === "power" && activeIds.has(edge.from) && activeIds.has(edge.to));
  const incoming = new Map<string, TopologyEdge[]>();
  const outgoing = new Map<string, TopologyEdge[]>();
  edges.forEach(edge => {
    incoming.set(edge.to, [...(incoming.get(edge.to) ?? []), edge]);
    outgoing.set(edge.from, [...(outgoing.get(edge.from) ?? []), edge]);
  });
  const nearestFeedNodes = (railId: string, net: string) => {
    const result = new Set<string>();
    const pending = (incoming.get(railId) ?? []).filter(edge => !edge.net || edge.net === net).map(edge => edge.from);
    const visited = new Set<string>();
    while (pending.length) {
      const id = pending.shift()!;
      if (visited.has(id)) continue;
      visited.add(id);
      const node = nodeById.get(id);
      if (!node) continue;
      if (node.kind !== "rail" && node.kind !== "return") result.add(id);
      else (incoming.get(id) ?? []).filter(edge => !edge.net || edge.net === net).forEach(edge => pending.push(edge.from));
    }
    return [...result];
  };
  const sameRailLoads = (railId: string, net: string) => {
    const result = new Set<string>();
    const pending = (outgoing.get(railId) ?? []).filter(edge => !edge.net || edge.net === net).map(edge => edge.to);
    const visited = new Set<string>();
    while (pending.length) {
      const id = pending.shift()!;
      if (visited.has(id)) continue;
      visited.add(id);
      const node = nodeById.get(id);
      if (!node) continue;
      if (node.kind === "load") result.add(id);
      else if (node.kind !== "rail" && node.kind !== "regulator" && node.kind !== "transformer") {
        (outgoing.get(id) ?? []).filter(edge => !edge.net || edge.net === net).forEach(edge => pending.push(edge.to));
      }
    }
    return [...result];
  };
  const jobs = budget.rails.map(rail => {
    const sourceNodeIds = nearestFeedNodes(rail.nodeId, rail.net);
    const loadNodeIds = sameRailLoads(rail.nodeId, rail.net);
    const warnings: string[] = [];
    if (!sourceNodeIds.length) warnings.push("No source or conversion-stage terminal is mapped to this rail.");
    if (!loadNodeIds.length) warnings.push("No load terminal is mapped to this rail.");
    if (!(rail.voltageV && rail.voltageV > 0)) warnings.push("Rail voltage is not assigned.");
    if (!(rail.currentA > 0)) warnings.push("Rail current is zero; assign scenario consumption before solving.");
    return {
      id: `power-tree-${slug(scenarioId)}-${slug(rail.net)}`,
      railNodeId: rail.nodeId,
      net: rail.net,
      sourceNodeIds,
      loadNodeIds,
      voltageV: rail.voltageV,
      totalCurrentA: rail.currentA,
      loadPowerW: rail.powerW,
      status: warnings.length ? "needs_setup" as const : "ready" as const,
      warnings,
    };
  });
  const warnings = unique([...budget.warnings, ...jobs.flatMap(job => job.warnings.map(warning => `${job.net}: ${warning}`))]);
  const status = budget.status === "invalid" || !jobs.length ? "invalid" : jobs.every(job => job.status === "ready") ? "ready" : "needs_setup";
  return { contract: "spike/power-tree-analysis-plan/v1", status, scenarioId, budget, jobs, warnings };
}

export function emptyTopology(domain: TopologyDomain): TopologyModel {
  return normalizeTopologyPorts({
    contract: "spike/topology/v1",
    domain,
    name: domain === "pi" ? "Power distribution tree" : "Signal channel topology",
    nodes: [],
    edges: [],
    scenarios: domain === "pi" ? defaultTopologyScenarios() : undefined,
    extraction: { source: "manual", generatedAt: new Date().toISOString(), warnings: ["No topology has been extracted."] },
  });
}
