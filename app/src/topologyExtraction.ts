import type { ParsedBoard } from "./boardParser";
import { normalizeTopologyPorts } from "./topologyPorts";
import {
  defaultTopologyScenarios,
  inferredVoltage,
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
} from "./powerTree";

type NetComponent = { ref: string; value: string; library?: string; nets: string[] };

function schematicProperties(source: string): Map<string, { value?: string; library?: string }> {
  const result = new Map<string, { value?: string; library?: string }>();
  const symbolPattern = /\(symbol\b[\s\S]*?\(property\s+"Reference"\s+"([^"]+)"[\s\S]*?\(property\s+"Value"\s+"([^"]*)"/g;
  for (const match of source.matchAll(symbolPattern)) result.set(match[1], { value: match[2] });
  return result;
}

const boardNetIndexCache = new WeakMap<ParsedBoard, Map<string, string[]>>();

export function boardComponents(board: ParsedBoard, schematicSource?: string): NetComponent[] {
  let netsByReference = boardNetIndexCache.get(board);
  if (!netsByReference) {
    netsByReference = new Map<string, string[]>();
    const seenByReference = new Map<string, Set<string>>();
    for (const pad of board.pads) {
      if (!pad.ref || !pad.net) continue;
      const seen = seenByReference.get(pad.ref) ?? new Set<string>();
      if (!netsByReference.has(pad.ref)) netsByReference.set(pad.ref, []);
      if (!seen.has(pad.net)) {
        seen.add(pad.net);
        netsByReference.get(pad.ref)!.push(pad.net);
      }
      seenByReference.set(pad.ref, seen);
    }
    boardNetIndexCache.set(board, netsByReference);
  }
  const schematic = schematicSource ? schematicProperties(schematicSource) : new Map<string, { value?: string; library?: string }>();
  return board.components.map(component => {
    const metadata = schematic.get(component.ref);
    return { ref: component.ref, value: metadata?.value || component.value, library: metadata?.library || component.library, nets: netsByReference.get(component.ref) ?? [] };
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
  if (/reg|ldo|buck|boost|converter|pmic|power|lm\d|lt\d|tps\d|mp\d/i.test(identity)) return "regulator";
  return /battery|supply|source|adapter|usb|barrel/i.test(identity) ? "source" : "load";
}

function topologyFromComponents(components: NetComponent[], domain: TopologyDomain, source: TopologyModel["extraction"]["source"]): TopologyModel {
  const allNets = [...new Set(components.flatMap(component => component.nets))];
  const interesting = allNets.filter(net => domain === "pi" ? isPowerNet(net) : signalName.test(net));
  const fallbackNets = allNets.filter(net => domain !== "pi" || !returnName.test(net));
  const selectedNets = [...new Set([...(interesting.length ? interesting : fallbackNets.slice(0, 24)), ...(domain === "pi" ? allNets.filter(net => returnName.test(net)).slice(0, 8) : [])])];
  const nodes: TopologyNode[] = selectedNets.map(net => ({ id: `${domain}-net-${slug(net)}`, kind: domain === "pi" ? returnName.test(net) ? "return" : "rail" : "channel", label: net, net, x: 0, y: 0, origin: "extracted" }));
  const edges: TopologyEdge[] = [];
  const sourceNetRank = (net: string) => /^(vin|vbat|bat|usb_vbus|12v|24v|48v)$/.test(net.split("/").filter(Boolean).pop()?.toLowerCase() ?? net.toLowerCase()) ? 0 : /^(vin|vbat|bat).*(?:_f|filter|protected)/.test(net) ? 1 : 2;
  for (const component of components) {
    const connected = component.nets.filter(net => selectedNets.includes(net));
    const powerConnected = domain === "pi" ? connected.filter(net => !returnName.test(net)) : connected;
    if (!connected.length || (domain === "pi" && /^(TP|MH|H)/i.test(component.ref))) continue;
    const kind = classifyComponent(component, domain), componentId = `${domain}-component-${slug(component.ref)}`;
    const isSeriesPassive = /^(R|L|FB|F|D|Q)/i.test(component.ref) && powerConnected.length >= 2;
    nodes.push({ id: componentId, kind, label: component.ref, ref: component.ref, value: component.value, orientation: domain === "pi" ? /^C/i.test(component.ref) ? "shunt" : isSeriesPassive || kind === "regulator" || kind === "transformer" ? "series" : "block" : "block", simulationModel: kind === "load" ? "constant_power" : kind === "source" ? "dc_source" : kind === "transformer" ? "isolated_transformer" : "", x: 0, y: 0, origin: "extracted" });
    connected.filter(net => returnName.test(net)).forEach((net, index) => edges.push({ id: `${componentId}-return-${index}`, from: componentId, to: `pi-net-${slug(net)}`, net, kind: "return", origin: "extracted" }));
    if (domain === "pi" && isSeriesPassive) {
      const ordered = [...powerConnected].sort((a, b) => sourceNetRank(a) - sourceNetRank(b));
      edges.push({ id: `${componentId}-input`, from: `pi-net-${slug(ordered[0])}`, to: componentId, net: ordered[0], kind: "power", origin: "extracted" }, { id: `${componentId}-output`, from: componentId, to: `pi-net-${slug(ordered[1])}`, net: ordered[1], kind: "power", origin: "extracted" });
    } else if (domain === "pi" && (kind === "regulator" || kind === "transformer") && powerConnected.length >= 2) {
      const input = powerConnected.find(net => /(?:^|[/_])(vin|vbat|input|primary)(?:$|[/_])/i.test(net)) ?? powerConnected[0];
      edges.push({ id: `${componentId}-input`, from: `pi-net-${slug(input)}`, to: componentId, net: input, kind: "power", origin: "extracted" });
      powerConnected.filter(net => net !== input).forEach((net, index) => edges.push({ id: `${componentId}-output-${index}`, from: componentId, to: `pi-net-${slug(net)}`, net, kind: "power", origin: "extracted" }));
    } else powerConnected.forEach((net, index) => {
      const netId = `${domain}-net-${slug(net)}`, outbound = kind === "source" || kind === "driver" || (kind === "regulator" && index > 0);
      edges.push({ id: `${componentId}-${slug(net)}-${index}`, from: outbound ? componentId : netId, to: outbound ? netId : componentId, net, kind: domain === "si" ? "signal" : returnName.test(net) ? "return" : "power", origin: "extracted" });
    });
  }
  if (domain === "pi" && !nodes.some(node => node.kind === "source")) {
    const incomingRails = new Set(edges.filter(edge => edge.kind === "power" && edge.to.startsWith("pi-net-")).map(edge => edge.to));
    const roots = selectedNets.filter(net => /(^|\/)(vin|vbat|bat|12v|24v|48v|usb_vbus)(?:$|[_/])/i.test(net)).filter(net => !incomingRails.has(`pi-net-${slug(net)}`)).sort((a, b) => sourceNetRank(a) - sourceNetRank(b));
    (roots.length ? roots.slice(0, 4) : selectedNets.slice(0, 1)).forEach(net => {
      const id = `pi-source-${slug(net)}`;
      nodes.push({ id, kind: "source", label: `${net} source`, net, voltageV: inferredVoltage({ id, kind: "source", label: net, net, x: 0, y: 0, origin: "extracted" }), simulationModel: "dc_source", x: 0, y: 0, origin: "extracted" });
      edges.push({ id: `${id}-feed`, from: id, to: `pi-net-${slug(net)}`, net, kind: "power", origin: "extracted" });
    });
  }
  if (domain === "pi") selectedNets.filter(net => /(?:^|[/_+-])(?:vout|[0-9]+(?:v[0-9]*|(?:\.[0-9]+)?v)out)(?:$|[/_+-])/i.test(net)).forEach(net => {
    const id = `pi-load-${slug(net)}`;
    if (!nodes.some(node => node.id === id)) {
      nodes.push({ id, kind: "load", label: `${net} external load`, net, simulationModel: "constant_power", orientation: "block", x: 0, y: 0, origin: "extracted" });
      edges.push({ id: `${id}-feed`, from: `pi-net-${slug(net)}`, to: id, net, kind: "power", origin: "extracted" });
    }
  });
  const warnings = !interesting.length ? [`No ${domain === "pi" ? "power" : "high-speed signal"} net names were recognized; showing a limited net inventory.`] : [];
  if (!nodes.some(node => domain === "pi" ? node.kind === "source" : node.kind === "driver")) warnings.push(`No explicit ${domain === "pi" ? "source" : "driver"} was identified. Assign one before simulation.`);
  return normalizeTopologyPorts({ contract: "spike/topology/v1", domain, name: domain === "pi" ? "Extracted power distribution tree" : "Extracted signal channel topology", nodes: layoutTopology([...new Map(nodes.map(node => [node.id, node])).values()], edges), edges, scenarios: domain === "pi" ? defaultTopologyScenarios() : undefined, extraction: { source, generatedAt: new Date().toISOString(), warnings } });
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
    if (ref) metadata.set(ref, { ref, value: component.querySelector("value")?.textContent || "", nets: [] });
  });
  documentNode.querySelectorAll("nets > net").forEach(netNode => {
    const net = netNode.getAttribute("name") || "";
    netNode.querySelectorAll("node").forEach(node => {
      const ref = node.getAttribute("ref") || "";
      const component = metadata.get(ref) ?? { ref, value: "", nets: [] };
      component.nets.push(net);
      metadata.set(ref, component);
    });
  });
  return topologyFromComponents([...metadata.values()], domain, "kicad_xml_netlist");
}
