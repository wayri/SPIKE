import type { ParsedBoard } from "./boardParser";
import { defaultTopologyPorts, emptyTopology, extractPowerPathFromBoard, layoutTopology, type TopologyDomain, type TopologyModel, type TopologyNode } from "./powerTree";
import { numericMaximum } from "./numericRange";

export type TopologyInputs = { source: string; net: string; sinks: string; voltage: string; current: string; sourcePad: string; sinkPad: string };

/** Generate only connectivity explicitly entered by the user or traced on the board. */
export function generateTopology(domain: TopologyDomain, input: TopologyInputs, board: ParsedBoard | null): TopologyModel {
  const number = (value: string, label: string, positive = false) => {
    const parsed = Number(value);
    if (!value.trim() || !Number.isFinite(parsed) || (positive ? parsed <= 0 : parsed < 0)) throw new Error(`Enter a ${positive ? "positive" : "non-negative"} ${label}.`);
    return parsed;
  };
  const voltageV = domain === "pi" ? number(input.voltage, "source voltage", true) : undefined;
  const loadCurrentA = domain === "pi" ? number(input.current, "current per load") : undefined;
  if (input.sourcePad || input.sinkPad) {
    if (!board || !input.sourcePad || !input.sinkPad) throw new Error("Select both board endpoints.");
    if (input.sourcePad === input.sinkPad) throw new Error("Choose two different endpoints.");
    if (domain === "pi") {
      const model = extractPowerPathFromBoard(board, input.sourcePad, input.sinkPad);
      if (model.extraction.warnings.some(warning => warning.startsWith("No unambiguous series component path"))) throw new Error("No series path connects these pads. Choose connected endpoints or build the missing stages manually.");
      return { ...model, nodes: model.nodes.map(node => node.kind === "source" ? { ...node, voltageV } : node.kind === "load" ? { ...node, loadCurrentA } : node) };
    }
    const source = board.pads.find(pad => pad.id === input.sourcePad);
    const sink = board.pads.find(pad => pad.id === input.sinkPad);
    if (!source || !sink || !source.net || source.net !== sink.net) throw new Error("Choose signal endpoints on the same net. Add connectors and series stages explicitly for a multi-net channel.");
    const model = generateTopology(domain, { ...input, sourcePad: "", sinkPad: "", source: `${source.ref}.${source.name}`, net: source.net, sinks: `${sink.ref}.${sink.name}` }, null);
    model.nodes = model.nodes.map(node => {
      const pad = node.kind === "driver" ? source : node.kind === "receiver" ? sink : undefined;
      return pad ? { ...node, ref: pad.ref, terminalPadId: pad.id, ports: node.ports?.map(port => port.kind === "signal" ? { ...port, padIds: [pad.id] } : port) } : node;
    });
    return model;
  }
  const sinks = input.sinks.split(/[,\n]/).map(value => value.trim()).filter(Boolean);
  if (!input.source.trim() || !input.net.trim() || !sinks.length) throw new Error("Enter a source, a net, and at least one destination.");
  if (new Set(sinks).size !== sinks.length) throw new Error("Give each destination a distinct name.");
  const model = emptyTopology(domain);
  const id = crypto.randomUUID();
  const node = (suffix: string, kind: TopologyNode["kind"], label: string): TopologyNode => ({
    id: `${id}-${suffix}`, kind, label, net: input.net.trim(), x: 0, y: 0, origin: "user",
    ports: defaultTopologyPorts(kind, domain).map(port => ({ ...port, net: ["power", "signal"].includes(port.kind) ? input.net.trim() : undefined, bindingState: ["power", "signal"].includes(port.kind) ? "bound" : "unassigned" })),
  });
  const source = { ...node("source", domain === "pi" ? "source" : "driver", input.source.trim()), voltageV, simulationModel: domain === "pi" ? "dc_source" : undefined };
  const rail = { ...node("net", domain === "pi" ? "rail" : "channel", input.net.trim()), voltageV };
  const loads = sinks.map((label, index) => ({ ...node(`sink-${index}`, domain === "pi" ? "load" : "receiver", label), loadCurrentA, simulationModel: domain === "pi" ? "constant_current" : undefined }));
  if (domain === "si") rail.ports = [...rail.ports!.filter(port => port.side !== "right"), ...loads.map((_, index) => ({ ...defaultTopologyPorts("channel", "si")[1], id: `out_${index + 1}`, label: `OUT${index + 1}`, net: input.net.trim(), bindingState: "bound" as const }))];
  model.nodes = [source, rail, ...loads];
  model.edges = [[source, rail], ...loads.map(load => [rail, load])].map(([from, to], index) => ({
    id: `${id}-wire-${index}`, from: from.id, to: to.id,
    fromPort: domain === "si" && index > 0 ? `out_${index}` : from.ports!.find(port => port.side === "right")!.id,
    toPort: to.ports!.find(port => port.side === "left")!.id,
    portBinding: "explicit", kind: domain === "pi" ? "power" : "signal", net: input.net.trim(), origin: "user",
  }));
  model.nodes = layoutTopology(model.nodes, model.edges);
  model.extraction.warnings = [domain === "pi" ? "Assign board terminals and review return paths and device models before analysis." : "Assign driver/receiver models and review channel and reference bindings before analysis."];
  return model;
}

export function appendTopology(current: TopologyModel, generated: TopologyModel): TopologyModel {
  // Imported board paths have stable IDs: isolate each insertion to avoid collisions.
  const prefix = `${crypto.randomUUID()}-`;
  const offset = current.nodes.length ? numericMaximum(current.nodes.map(node => node.y + 200)) : 0;
  return { ...current,
    nodes: [...current.nodes, ...generated.nodes.map(node => ({ ...node, id: prefix + node.id, pathGroupId: node.pathGroupId ? prefix + node.pathGroupId : undefined, y: node.y + offset }))],
    edges: [...current.edges, ...generated.edges.map(edge => ({ ...edge, id: prefix + edge.id, from: prefix + edge.from, to: prefix + edge.to }))],
    extraction: { ...current.extraction, warnings: [...new Set([...current.extraction.warnings.filter(w => !w.startsWith("No topology")), ...generated.extraction.warnings])] },
  };
}
