import type { ParsedBoard } from "./boardParser";
import { normalizeTopologyPorts } from "./topologyPorts";
import {
  defaultTopologyScenarios,
  isPowerNet,
  layoutTopology,
  returnName,
  signalName,
  slug,
  type TopologyDomain,
  type TopologyEdge,
  type TopologyModel,
  type TopologyNode,
  type TopologyNodeKind,
  type TopologyInference,
  type TopologyPinRole,
} from "./powerTree";

type NetPin = { id: string; name: string; net: string; function?: string; type?: string };
type NetComponent = { ref: string; value: string; library?: string; nets: string[]; pins?: NetPin[]; properties?: Record<string, unknown> };
const sorted = (values: Iterable<string>) => [...new Set(values)].sort((a, b) => a < b ? -1 : a > b ? 1 : 0);
const evidence = (confidence: TopologyInference["confidence"], ...items: string[]): TopologyInference => ({ confidence, evidence: items, reviewRequired: true });
const propertiesOf = (source: unknown): Record<string, unknown> => Array.isArray(source)
  ? Object.fromEntries(source.map(item => [String(item.name ?? ""), item.values?.[0]]))
  : source && typeof source === "object" ? source as Record<string, unknown> : {};

function schematicProperties(source: string): Map<string, { value?: string; library?: string }> {
  const result = new Map<string, { value?: string; library?: string }>();
  const symbolPattern = /\(symbol\b[\s\S]*?\(property\s+"Reference"\s+"([^"]+)"[\s\S]*?\(property\s+"Value"\s+"([^"]*)"/g;
  for (const match of source.matchAll(symbolPattern)) result.set(match[1], { value: match[2] });
  return result;
}

const boardNetIndexCache = new WeakMap<ParsedBoard, Map<string, NetPin[]>>();

export function boardComponents(board: ParsedBoard, schematicSource?: string): NetComponent[] {
  let pinsByReference = boardNetIndexCache.get(board);
  if (!pinsByReference) {
    pinsByReference = new Map<string, NetPin[]>();
    for (const pad of board.pads) {
      if (!pad.ref || !pad.net) continue;
      const semantics = pad as typeof pad & { pin_function?: string; pinfunction?: string; pin_type?: string; pintype?: string };
      if (!pinsByReference.has(pad.ref)) pinsByReference.set(pad.ref, []);
      pinsByReference.get(pad.ref)!.push({ id: pad.id, name: pad.name, net: pad.net,
        function: semantics.pin_function ?? semantics.pinfunction, type: semantics.pin_type ?? semantics.pintype });
    }
    boardNetIndexCache.set(board, pinsByReference);
  }
  const schematic = schematicSource ? schematicProperties(schematicSource) : new Map<string, { value?: string; library?: string }>();
  return board.components.map(component => {
    const metadata = schematic.get(component.ref);
    const pins = pinsByReference.get(component.ref) ?? [];
    return { ref: component.ref, value: metadata?.value || component.value, library: metadata?.library || component.library,
      nets: sorted(pins.map(pin => pin.net)), pins, properties: { ...component.vendor_properties, ...propertiesOf(component.properties) } };
  });
}

export function classifyComponent(component: NetComponent, domain: TopologyDomain): TopologyNodeKind {
  const identity = `${component.ref} ${component.value} ${component.library ?? ""}`;
  if (/^(J|P|CN)/i.test(component.ref)) return "connector";
  if (domain === "si") {
    if (/^(R|C|L|FB)/i.test(component.ref)) return /term|termination/i.test(identity) || component.ref.startsWith("R") ? "termination" : "passive";
    if (/driver|transmitter|buffer|serializer|mcu|fpga|cpu/i.test(identity)) return "driver";
    return "receiver";
  }
  if (/^(T|XFMR)/i.test(component.ref) || /transformer|flyback|isolation transformer/i.test(identity)) return "transformer";
  if (/^(R|C|L|FB|F|D|Q)/i.test(component.ref)) return "passive";
  if (/regulator|\bldo\b|\bbuck\b|\bboost\b|dc[ -]?dc|converter|\bpmic\b/i.test(identity)) return "regulator";
  return /\bbattery\b|\bpower supply\b|\bpsu\b|\bdc source\b/i.test(identity) ? "source" : "load";
}

function signalTopologyFromComponents(components: NetComponent[], source: TopologyModel["extraction"]["source"]): TopologyModel {
  const allNets = sorted(components.flatMap(component => component.nets));
  const interesting = allNets.filter(net => signalName.test(net));
  const selectedNets = new Set(interesting.length ? interesting : allNets.slice(0, 24));
  const nodes: TopologyNode[] = [...selectedNets].map(net => ({ id: `si-net-${slug(net)}`, kind: "channel", label: net, net, x: 0, y: 0, origin: "extracted" }));
  const edges: TopologyEdge[] = [];
  for (const component of components) {
    const connected = component.nets.filter(net => selectedNets.has(net));
    if (!connected.length) continue;
    const kind = classifyComponent(component, "si"), id = `si-component-${slug(component.ref)}`;
    nodes.push({ id, kind, label: component.ref, ref: component.ref, value: component.value, orientation: "block", x: 0, y: 0, origin: "extracted" });
    connected.forEach((net, index) => {
      const outbound = kind === "driver", netId = `si-net-${slug(net)}`;
      edges.push({ id: `${id}-${slug(net)}-${index}`, from: outbound ? id : netId, to: outbound ? netId : id, net, kind: "signal", origin: "extracted" });
    });
  }
  const warnings = interesting.length ? [] : ["No high-speed signal net names were recognized; showing a limited net inventory."];
  if (!nodes.some(node => node.kind === "driver")) warnings.push("No explicit driver was identified. Assign one before simulation.");
  return normalizeTopologyPorts({ contract: "spike/topology/v1", domain: "si", name: "Extracted signal channel topology", nodes: layoutTopology(nodes, edges), edges, extraction: { source, generatedAt: new Date().toISOString(), warnings } });
}

type PinEvidence = { role?: TopologyPinRole; inference: TopologyInference };
function pinEvidence(component: NetComponent, pin: NetPin): PinEvidence {
  let roles: unknown = component.properties?.["SPIKE.PinRoles"];
  if (typeof roles === "string") { try { roles = JSON.parse(roles); } catch { roles = {}; } }
  const declared = roles && typeof roles === "object" ? (roles as Record<string, unknown>)[pin.name] : undefined;
  if (typeof declared === "string" && ["input", "output", "return", "control", "passive", "unused"].includes(declared))
    return { role: declared as TopologyPinRole, inference: evidence("explicit", `SPIKE.PinRoles: ${component.ref}.${pin.name}=${declared}`) };
  const name = (pin.function || pin.name).trim().toUpperCase();
  if (/^(GND|AGND|DGND|PGND|VSS|VSSA|VSSD)(?:\d+)?$/.test(name))
    return { role: "return", inference: evidence("inferred", `${component.ref}.${pin.name} pin function ${name}`) };
  const type = (pin.type ?? "").toLowerCase();
  if (type === "power_in" || type === "power_out")
    return { role: type === "power_in" ? "input" : "output", inference: evidence("explicit", `${component.ref}.${pin.name} electrical type ${type}`) };
  if (type && type !== "passive" && type !== "unspecified")
    return { role: "control", inference: evidence("unresolved", `${component.ref}.${pin.name} has non-power electrical type ${type}`) };
  if (/^(VIN|PVIN|AVIN|VCC|VDD|AVDD|DVDD|VBAT)(?:[_\d].*)?$/.test(name))
    return { role: "input", inference: evidence("inferred", `${component.ref}.${pin.name} supply pin function ${name}`) };
  if (/^VOUT(?:[_\d].*)?$/.test(name) || (classifyComponent(component, "pi") === "regulator" && /^OUT\d*$/.test(name)))
    return { role: "output", inference: evidence("inferred", `${component.ref}.${pin.name} output pin function ${name}`) };
  if (pin.function || (type && type !== "passive"))
    return { role: "control", inference: evidence("unresolved", `${component.ref}.${pin.name} is not identified as a power pin (${name || type})`) };
  return { inference: evidence("unresolved", `${component.ref}.${pin.name} has no power-pin assignment`) };
}

/** Eligible selected-terminal transfers, mirrored by the worker path service. */
export function powerTransferPairs(component: NetComponent, knownReturnNets: ReadonlySet<string> = new Set()): [string, string][] {
  const pins = (component.pins ?? []).map(pin => ({ ...pin, ...pinEvidence(component, pin) }));
  const returns = new Set(pins.filter(pin => pin.role === "return").map(pin => pin.net));
  const nets = sorted(component.nets.filter(net => !returnName.test(net) && net !== "0" && !returns.has(net) && !knownReturnNets.has(net)));
  if (nets.length < 2) return [];
  const inputs = sorted(pins.filter(pin => pin.role === "input" && nets.includes(pin.net)).map(pin => pin.net));
  const outputs = sorted(pins.filter(pin => pin.role === "output" && nets.includes(pin.net)).map(pin => pin.net));
  const assigned = inputs.length === 1 && outputs.length && !outputs.includes(inputs[0]);
  if (/^(R|L|FB|F)\d/i.test(component.ref) && nets.length === 2 && new Set(pins.map(pin => pin.name)).size === 2)
    return assigned ? outputs.map(net => [inputs[0], net]) : [[nets[0], nets[1]], [nets[1], nets[0]]];
  if (/^(U|IC)\d/i.test(component.ref) && assigned) return outputs.map(net => [inputs[0], net]);
  return [];
}

export function powerReturnNets(components: NetComponent[]): Set<string> {
  const nets = new Set(components.flatMap(component => component.nets.filter(net => returnName.test(net) || net === "0")));
  for (const component of components) for (const pin of component.pins ?? []) if (pinEvidence(component, pin).role === "return") nets.add(pin.net);
  return nets;
}

/** A review draft from actual pin incidence. Numeric models are never inferred. */
function powerTopologyFromComponents(components: NetComponent[], source: TopologyModel["extraction"]["source"]): TopologyModel {
  const warnings: string[] = [];
  const ordered = [...components].sort((a, b) => a.ref < b.ref ? -1 : a.ref > b.ref ? 1 : 0);
  const pins = new Map(ordered.map(component => [component.ref, (component.pins ?? []).map(pin => ({ ...pin, ...pinEvidence(component, pin) }))]));
  const returns = powerReturnNets(ordered);
  const rails = new Set(ordered.flatMap(component => component.nets.filter(net => isPowerNet(net) && !returns.has(net))));
  const signalNets = new Set<string>(), supplyNets = new Set<string>();
  for (const values of pins.values()) for (const pin of values) {
    if (pin.role === "control") signalNets.add(pin.net);
    if (pin.role === "input" || pin.role === "output") supplyNets.add(pin.net);
  }
  for (const net of signalNets) if (!supplyNets.has(net)) rails.delete(net);
  for (const values of pins.values()) for (const pin of values) if ((pin.role === "input" || pin.role === "output") && !returns.has(pin.net)) rails.add(pin.net);
  // Stable, injective identities also distinguish /3V3, +3V3 and 3V3.
  const railId = (net: string) => `pi-net-${encodeURIComponent(net)}`;
  const nodes: TopologyNode[] = [];
  const edges: TopologyEdge[] = [];
  const roots = new Set<string>();
  const series: { component: NetComponent; node: TopologyNode; nets: string[] }[] = [];
  let omittedShunts = 0;
  const addEdge = (node: TopologyNode, net: string, outbound: boolean, inference: TopologyInference) => {
    const boundPins = (pins.get(node.ref ?? "") ?? []).filter(pin => pin.net === net);
    const portId = `${outbound ? "out" : "in"}-${encodeURIComponent(net)}`;
    node.ports!.push({ id: portId, label: boundPins.map(pin => pin.function || pin.name).join(" / ") || net,
      direction: outbound ? "output" : "input", kind: "power", side: outbound ? "right" : "left", net,
      padIds: boundPins.map(pin => pin.id), bindingState: inference.confidence === "explicit" ? "bound" : "inferred" });
    edges.push({ id: `${node.id}-${portId}`, from: outbound ? node.id : railId(net), to: outbound ? railId(net) : node.id,
      fromPort: outbound ? portId : "out", toPort: outbound ? "in" : portId, portBinding: "inferred",
      net, kind: "power", origin: "extracted", inference });
  };
  for (const component of ordered) {
    if (/^(TP|MH|H)\d/i.test(component.ref)) continue;
    const componentPins = pins.get(component.ref)!;
    const connected = sorted(component.nets.filter(net => rails.has(net)));
    if (!connected.length) continue;
    if (/^C\d/i.test(component.ref)) { omittedShunts++; continue; }
    const declaredRole = String(component.properties?.["SPIKE.PowerRole"] ?? "").toLowerCase();
    const hasInputs = componentPins.some(pin => pin.role === "input" && rails.has(pin.net));
    const hasOutputs = componentPins.some(pin => pin.role === "output" && rails.has(pin.net));
    let kind = classifyComponent(component, "pi");
    let classification = evidence("inferred", `Component identity: ${component.ref} ${component.value} ${component.library ?? ""}`);
    if (["source", "regulator", "load", "connector", "passive"].includes(declaredRole)) {
      kind = declaredRole as TopologyNodeKind;
      classification = evidence("explicit", `SPIKE.PowerRole=${declaredRole}`);
    } else if (kind === "connector" && /^(?:power[ _-]*)?(?:input|in|vin|vbat|supply|psu)$/i.test(component.value.trim())) {
      kind = "source";
      classification = evidence("inferred", `${component.ref} connector value explicitly labels a supply input (${component.value})`);
    } else if (hasInputs && hasOutputs && kind !== "connector" && kind !== "passive") {
      kind = "regulator";
      classification = evidence("inferred", `${component.ref} has distinct supply input and output pin evidence`);
    }
    if (kind === "passive" && component.nets.some(net => returns.has(net))) { omittedShunts++; continue; }
    const node: TopologyNode = { id: `pi-component-${encodeURIComponent(component.ref)}`, kind, label: component.ref, ref: component.ref,
      value: component.value, orientation: kind === "regulator" ? "series" : "block", x: 0, y: 0, origin: "extracted", ports: [], inference: classification,
      pinRoles: Object.fromEntries(componentPins.filter(pin => pin.role).map(pin => [pin.name, pin.role!])) };
    nodes.push(node);
    const edgeStart = edges.length;
    const inputNets = sorted(componentPins.filter(pin => pin.role === "input" && rails.has(pin.net)).map(pin => pin.net));
    const outputNets = sorted(componentPins.filter(pin => pin.role === "output" && rails.has(pin.net)).map(pin => pin.net));
    const netEvidence = (net: string, role: TopologyPinRole) => {
      const matched = componentPins.filter(pin => pin.net === net && pin.role === role);
      return evidence(matched.every(pin => pin.inference.confidence === "explicit") ? "explicit" : "inferred", ...matched.flatMap(pin => pin.inference.evidence));
    };
    if (kind === "source") {
      const sourceNets = outputNets.length ? outputNets : connected.length === 1 ? connected : [];
      sourceNets.forEach(net => { addEdge(node, net, true, outputNets.includes(net) ? netEvidence(net, "output") : classification); roots.add(net); });
      if (!sourceNets.length) warnings.push(`${component.ref}: source has multiple candidate rails; assign output pin roles.`);
    } else if (kind === "regulator") {
      const conflicting = inputNets.some(net => outputNets.includes(net));
      if (inputNets.length === 1 && outputNets.length && !conflicting) {
        inputNets.forEach(net => addEdge(node, net, false, netEvidence(net, "input")));
        outputNets.forEach(net => { addEdge(node, net, true, netEvidence(net, "output")); roots.add(net); });
      } else {
        node.inference = evidence("unresolved", ...classification.evidence, "Input/output power pin roles are missing, conflicting or span multiple input rails");
        warnings.push(`${component.ref}: regulator direction unresolved; assign input/output pins and review any multi-input channel mapping. Net names and pad order do not establish direction.`);
      }
    } else if (kind === "passive") {
      const nonReturn = sorted(component.nets.filter(net => !returns.has(net)));
      if (/^(R|L|FB|F)\d/i.test(component.ref) && nonReturn.length === 2 && connected.length === 2 && new Set(componentPins.map(pin => pin.name)).size === 2) {
        node.orientation = "series";
        if (inputNets.length === 1 && outputNets.length === 1 && inputNets[0] !== outputNets[0]) {
          addEdge(node, inputNets[0], false, netEvidence(inputNets[0], "input"));
          addEdge(node, outputNets[0], true, netEvidence(outputNets[0], "output"));
          roots.add(outputNets[0]);
        } else series.push({ component, node, nets: nonReturn });
      } else {
        node.inference = evidence("unresolved", "Series power transfer needs explicit pin/model assignment");
        warnings.push(`${component.ref}: no automatic internal power transfer; review its pins and model.`);
      }
    } else if (kind === "load" || kind === "connector") {
      const loadNets = inputNets.length ? inputNets : kind === "load" ? connected.filter(net => componentPins.some(pin => pin.net === net && !pin.role)) : [];
      loadNets.forEach(net => addEdge(node, net, false, inputNets.includes(net) ? netEvidence(net, "input") : evidence("inferred", `${component.ref} is connected to candidate supply rail ${net}; load pin role needs review`)));
      if (!loadNets.length) {
        node.inference = evidence("unresolved", "Connector or device supply direction is unassigned");
        warnings.push(`${component.ref}: supply direction unassigned; assign source/load pin roles.`);
      }
    } else warnings.push(`${component.ref}: ${kind} internal transfer requires explicit pin/model assignment.`);
    if (edges.length === edgeStart) {
      node.inference = evidence("unresolved", ...node.inference!.evidence);
      node.ports = connected.map(net => ({ id: `unassigned-${encodeURIComponent(net)}`, label: net, net,
        direction: "passive", kind: "power", side: "left", bindingState: "unassigned",
        padIds: componentPins.filter(pin => pin.net === net).map(pin => pin.id) }));
    }
  }
  // Orient a two-terminal series component only within a uniquely rooted region.
  const adjacency = new Map<string, string[]>();
  series.forEach(item => item.nets.forEach((net, index) => adjacency.set(net, [...(adjacency.get(net) ?? []), item.nets[1 - index]])));
  const visited = new Set<string>();
  const distances = new Map<string, number>();
  for (const net of sorted(adjacency.keys())) {
    if (visited.has(net)) continue;
    const region = [net]; visited.add(net);
    for (let index = 0; index < region.length; index++) for (const neighbor of adjacency.get(region[index]) ?? []) if (!visited.has(neighbor)) { visited.add(neighbor); region.push(neighbor); }
    const regionalRoots = region.filter(item => roots.has(item));
    if (regionalRoots.length !== 1) continue;
    const queue = [regionalRoots[0]]; distances.set(queue[0], 0);
    for (let index = 0; index < queue.length; index++) for (const neighbor of adjacency.get(queue[index]) ?? []) if (!distances.has(neighbor)) { distances.set(neighbor, distances.get(queue[index])! + 1); queue.push(neighbor); }
  }
  series.forEach(({ node, nets }) => {
    const left = distances.get(nets[0]), right = distances.get(nets[1]);
    if (left === undefined || right === undefined || left === right) {
      node.inference = evidence("unresolved", "Series region has no unique upstream source or equal-length paths");
      warnings.push(`${node.ref}: series direction unresolved (no unique source, competing supplies, or loop).`);
      return;
    }
    node.ports = [];
    node.inference = evidence("inferred", "Two-terminal connectivity in a region with one identified supply endpoint");
    addEdge(node, nets[left < right ? 0 : 1], false, node.inference);
    addEdge(node, nets[left < right ? 1 : 0], true, node.inference);
  });
  for (const net of sorted(rails)) nodes.push({ id: railId(net), kind: "rail", label: net, net, x: 0, y: 0, origin: "extracted",
    inference: evidence("inferred", `Imported net connectivity${isPowerNet(net) ? " and power-rail name" : " and supply pin semantics"}; operating voltage is unassigned`) });
  if (omittedShunts) warnings.push(`${omittedShunts} capacitor or return-connected passive component(s) omitted from the distribution overview; use a focused power path for shunts.`);
  if (!rails.size) warnings.push("No supply pins or power rails identified; signal nets were not promoted to power rails.");
  if (!nodes.some(node => node.kind === "source" && edges.some(edge => edge.from === node.id))) warnings.push("No source identified. Assign a supply connector or source and its output pins.");
  warnings.push("Extracted connectivity is a review draft. Confirm pin roles, voltages, load demand and converter models before analysis; no SPIKES simulation was run.");
  return normalizeTopologyPorts({ contract: "spike/topology/v1", domain: "pi", name: "Extracted power distribution tree", nodes: layoutTopology(nodes, edges), edges,
    scenarios: defaultTopologyScenarios(), extraction: { source, generatedAt: new Date().toISOString(), warnings } });
}

function topologyFromComponents(components: NetComponent[], domain: TopologyDomain, source: TopologyModel["extraction"]["source"]): TopologyModel {
  return domain === "pi" ? powerTopologyFromComponents(components, source) : signalTopologyFromComponents(components, source);
}

export function extractTopologyFromBoard(board: ParsedBoard, domain: TopologyDomain, schematicSource?: string): TopologyModel {
  return topologyFromComponents(boardComponents(board, schematicSource), domain, schematicSource ? "kicad_schematic+board_netlist" : "board_netlist");
}

export function extractTopologyFromXmlNetlist(source: string, domain: TopologyDomain): TopologyModel {
  const documentNode = new DOMParser().parseFromString(source, "application/xml");
  if (documentNode.querySelector("parsererror")) throw new Error("The selected XML netlist is invalid.");
  const metadata = new Map<string, NetComponent>();
  documentNode.querySelectorAll("components > comp").forEach(component => {
    const ref = component.getAttribute("ref") || "";
    const properties: Record<string, unknown> = {};
    component.querySelectorAll("property, field").forEach(item => { properties[item.getAttribute("name") || ""] = item.getAttribute("value") ?? item.textContent ?? ""; });
    if (ref) metadata.set(ref, { ref, value: component.querySelector("value")?.textContent || "", library: component.querySelector("libsource")?.getAttribute("part") || "", nets: [], pins: [], properties });
  });
  documentNode.querySelectorAll("nets > net").forEach(netNode => {
    const net = netNode.getAttribute("name") || "";
    netNode.querySelectorAll("node").forEach(node => {
      const ref = node.getAttribute("ref") || "";
      const component = metadata.get(ref) ?? { ref, value: "", nets: [], pins: [] };
      component.nets.push(net);
      const name = node.getAttribute("pin") || "";
      component.pins!.push({ id: `${ref}.${name}`, name, net, function: node.getAttribute("pinfunction") || "", type: node.getAttribute("pintype") || "" });
      metadata.set(ref, component);
    });
  });
  return topologyFromComponents([...metadata.values()], domain, "kicad_xml_netlist");
}
