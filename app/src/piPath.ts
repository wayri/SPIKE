import type { ParsedPad } from "./boardParser";
import type { TopologyModel, TopologyNode } from "./powerTree";

export type PiPathSegment = { id: string; net: string; rail_node_id: string };
export type PiPathTransition = {
  id: string;
  component_ref: string;
  component_node_id: string;
  from_segment_id: string;
  to_segment_id: string;
  input_pad_id: string;
  output_pad_id: string;
  model: Record<string, string | number | boolean | undefined>;
};
export type CompiledPiPath = {
  contract: "spike/pi-path/v1";
  id: string;
  label: string;
  source_terminal: { net: string; pad_id: string };
  load_terminal: { net: string; pad_id: string };
  segments: PiPathSegment[];
  transitions: PiPathTransition[];
  issues: string[];
};

export type PiPathTerminalAnchor = {
  net: string;
  position_mm: [number, number];
  layers: string[];
  geometry_anchor: { id: string; type: "pad" };
};

export type PiSeriesSolveHandoff = {
  net_names: string[];
  pi_path: CompiledPiPath;
  source_terminal: PiPathTerminalAnchor;
  load_terminal: PiPathTerminalAnchor;
};

/** Compile reviewed Power Tree path groups into an ordered solver handoff. */
export function compilePiPaths(model: TopologyModel): CompiledPiPath[] {
  const byId = new Map(model.nodes.map(node => [node.id, node]));
  const groups = [...new Set(model.nodes.map(node => node.pathGroupId).filter((id): id is string => Boolean(id)))];
  return groups.map(groupId => {
    const members = model.nodes.filter(node => node.pathGroupId === groupId);
    const memberIds = new Set(members.map(node => node.id));
    const source = members.find(node => node.kind === "source");
    const load = members.find(node => node.kind === "load");
    const outgoing = new Map<string, string[]>();
    model.edges.filter(edge => edge.kind === "power" && memberIds.has(edge.from) && memberIds.has(edge.to)).forEach(edge => {
      outgoing.set(edge.from, [...(outgoing.get(edge.from) ?? []), edge.to]);
    });
    const findPath = (current: string, target: string, visited = new Set<string>()): string[] | null => {
      if (current === target) return [current];
      if (visited.has(current)) return null;
      const nextVisited = new Set(visited).add(current);
      for (const next of outgoing.get(current) ?? []) {
        const tail = findPath(next, target, nextVisited);
        if (tail) return [current, ...tail];
      }
      return null;
    };
    const orderedIds = source && load ? findPath(source.id, load.id) ?? [] : [];
    const ordered = orderedIds.map(id => byId.get(id)).filter((node): node is TopologyNode => Boolean(node));
    const rails = ordered.filter(node => node.kind === "rail" && node.net);
    const segments: PiPathSegment[] = rails.map((rail, index) => ({ id: `${groupId}:segment:${index + 1}`, net: rail.net!, rail_node_id: rail.id }));
    const transitions: PiPathTransition[] = [];
    const issues: string[] = [];
    if (!source || !load) issues.push("Path requires one source and one load block.");
    if (!ordered.length) issues.push("No directed source-to-load power connection exists in this path group.");
    if (!source?.terminalPadId || !load?.terminalPadId) issues.push("Source and load must be anchored to explicit board pads.");
    for (let index = 0; index + 1 < rails.length; index += 1) {
      const beforeIndex = ordered.findIndex(node => node.id === rails[index].id);
      const afterIndex = ordered.findIndex(node => node.id === rails[index + 1].id);
      const component = ordered.slice(beforeIndex + 1, afterIndex).find(node => node.orientation === "series" && !["rail", "source", "load", "return"].includes(node.kind));
      if (!component) {
        issues.push(`No explicit series component joins ${rails[index].net} to ${rails[index + 1].net}.`);
        continue;
      }
      const pins = component.circuitModel?.pins ?? [];
      const input = pins.find(pin => pin.role === "input") ?? pins.find(pin => pin.role === "passive");
      const output = pins.find(pin => pin.role === "output") ?? pins.filter(pin => pin.role === "passive")[1];
      if (!input?.pad_id || !output?.pad_id) issues.push(`${component.ref ?? component.label} requires reviewed input and output pad mapping.`);
      const parameters = component.modelParameters ?? {};
      transitions.push({
        id: component.id,
        component_ref: component.ref ?? component.label,
        component_node_id: component.id,
        from_segment_id: segments[index].id,
        to_segment_id: segments[index + 1].id,
        input_pad_id: input?.pad_id ?? "",
        output_pad_id: output?.pad_id ?? "",
        model: {
          ...parameters,
          primitive: component.circuitModel?.primitive ?? component.simulationModel ?? "spice_subcircuit",
          type: component.circuitModel?.type ?? component.simulationModel ?? "spice_subcircuit",
          value: component.circuitModel?.value ?? component.value ?? "",
          dc_resistance_ohm: component.resistanceOhm ?? parameters.dc_resistance_ohm ?? parameters.series_resistance_ohm ?? parameters.resistance_ohm ?? parameters.rds_on_ohm,
          model_ref: component.modelLink ?? "",
          solver_policy: component.solverPolicy ?? "staged_hybrid",
        },
      });
    }
    if (transitions.length !== Math.max(0, segments.length - 1)) issues.push("Every adjacent net segment must have one reviewed series transition.");
    return {
      contract: "spike/pi-path/v1" as const,
      id: groupId,
      label: source?.pathGroupLabel ?? load?.pathGroupLabel ?? groupId,
      source_terminal: { net: source?.net ?? segments[0]?.net ?? "", pad_id: source?.terminalPadId ?? "" },
      load_terminal: { net: load?.net ?? segments[segments.length - 1]?.net ?? "", pad_id: load?.terminalPadId ?? "" },
      segments,
      transitions,
      issues: [...new Set(issues)],
    };
  });
}

/** Resolve a reviewed path into the exact mesh/solve contract consumed by the worker. */
export function compilePiSeriesSolveHandoff(path: CompiledPiPath, pads: readonly ParsedPad[]): PiSeriesSolveHandoff {
  if (path.issues.length) throw new Error(`Power path is incomplete: ${path.issues[0]}`);
  if (!path.segments.length || path.transitions.length !== path.segments.length - 1) {
    throw new Error("Power path requires every ordered net segment and series transition to be reviewed.");
  }
  const netNames = path.segments.map(segment => segment.net.trim());
  if (netNames.some(net => !net)) throw new Error("Power path contains an unnamed net segment.");

  const resolveTerminal = (terminal: CompiledPiPath["source_terminal"], role: "source" | "load"): PiPathTerminalAnchor => {
    const pad = pads.find(item => item.id === terminal.pad_id);
    if (!pad || pad.net !== terminal.net) {
      throw new Error(`Reviewed ${role} terminal must resolve to its declared board pad on ${terminal.net || "the path net"}.`);
    }
    return {
      net: terminal.net,
      position_mm: pad.at,
      layers: pad.layers,
      geometry_anchor: { id: pad.id, type: "pad" },
    };
  };

  return {
    net_names: netNames,
    pi_path: path,
    source_terminal: resolveTerminal(path.source_terminal, "source"),
    load_terminal: resolveTerminal(path.load_terminal, "load"),
  };
}
