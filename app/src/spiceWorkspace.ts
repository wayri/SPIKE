import type { SolverResultBundle } from "./analysisResults";
import type { ParsedBoard, ParsedComponent, ParsedPad } from "./boardParser";

export const SPICE_WORKSPACE_CONTRACT = "spike/spice-workspace/v1";

export type SpiceModelKind = "primitive" | "subcircuit";
export type SpicePrimitive = "resistor" | "capacitor" | "inductor" | "voltage_source" | "current_source" | "diode";
export type SpiceModel = {
  id: string;
  name: string;
  kind: SpiceModelKind;
  primitive?: SpicePrimitive;
  subcircuit_name?: string;
  pins: string[];
  value?: string;
  device_model?: string;
  source?: string;
  parameters?: Record<string, unknown>;
  origin: "built_in" | "project" | "imported";
};
export type SpicePinBinding = {
  model_pin: string;
  pad_id: string;
  board_net: string;
  circuit_node: string;
};
export type SpiceAssignment = {
  id: string;
  component_ref: string;
  model_id: string;
  enabled: boolean;
  pin_bindings: SpicePinBinding[];
  ratings?: { voltage_v?: number; current_a?: number; power_w?: number };
  vectors?: { voltage?: string; current?: string; power?: string };
};
export type SpiceParasitic = {
  id: string;
  enabled: boolean;
  net: string;
  from_node: string;
  to_node: string;
  reference_node: string;
  resistance_ohm: number;
  inductance_h: number;
  capacitance_f: number;
  conductance_s: number;
  source_result_id: string;
  model_status: string;
  endpoint_reviewed: boolean;
  source_network_index?: number;
  source_mesh_nodes?: [number, number];
};
export type SpiceAnalysis =
  | { mode: "operating_point" }
  | { mode: "ac"; start_hz: number; stop_hz: number; points_per_decade: number }
  | { mode: "transient"; time_step_s: number; stop_time_s: number };
export type SpiceWorkspace = {
  contract: typeof SPICE_WORKSPACE_CONTRACT;
  name: string;
  domain: "pi" | "si";
  ground_node: string;
  models: SpiceModel[];
  assignments: SpiceAssignment[];
  parasitics: SpiceParasitic[];
  analysis: SpiceAnalysis;
};
export type SpiceValidationIssue = { code: string; severity: string; message: string; path?: string };
export type SpiceWorkspaceValidation = {
  contract: string;
  valid: boolean;
  can_run: boolean;
  issues: SpiceValidationIssue[];
  warnings: SpiceValidationIssue[];
  counts: { models: number; assignments: number; parasitics: number };
  model_status: string;
};
export type SpiceNetlistPreview = {
  contract: string;
  status: "ready" | "blocked";
  netlist: string;
  validation: SpiceWorkspaceValidation;
  node_aliases: Record<string, string>;
  provenance?: Record<string, unknown>;
};

const builtInModels = (): SpiceModel[] => [
  { id: "builtin_resistor", name: "Resistor", kind: "primitive", primitive: "resistor", pins: ["1", "2"], value: "1", parameters: { resistance_ohm: 1 }, origin: "built_in" },
  { id: "builtin_capacitor", name: "Capacitor", kind: "primitive", primitive: "capacitor", pins: ["1", "2"], value: "1u", parameters: { capacitance_f: 1e-6 }, origin: "built_in" },
  { id: "builtin_inductor", name: "Inductor", kind: "primitive", primitive: "inductor", pins: ["1", "2"], value: "1u", parameters: { inductance_h: 1e-6 }, origin: "built_in" },
  { id: "builtin_voltage_source", name: "Voltage source", kind: "primitive", primitive: "voltage_source", pins: ["p", "n"], value: "DC 12", parameters: { dc_value: 12 }, origin: "built_in" },
  { id: "builtin_current_source", name: "Current source", kind: "primitive", primitive: "current_source", pins: ["p", "n"], value: "DC 1", parameters: { dc_value: 1 }, origin: "built_in" },
  { id: "builtin_diode", name: "Generic diode", kind: "primitive", primitive: "diode", pins: ["a", "k"], device_model: "D_DEFAULT", origin: "built_in" },
];

export function defaultSpiceWorkspace(domain: "pi" | "si" = "pi", board?: ParsedBoard | null): SpiceWorkspace {
  const nets = board ? [...new Set(Object.values(board.nets).filter(Boolean))] : [];
  return {
    contract: SPICE_WORKSPACE_CONTRACT,
    name: domain === "pi" ? "PI circuit and parasitics" : "SI channel and termination",
    domain,
    ground_node: nets.find(net => /^(gnd|ground|0)$/i.test(net)) ?? "GND",
    models: builtInModels(),
    assignments: [],
    parasitics: [],
    analysis: domain === "pi"
      ? { mode: "transient", time_step_s: 1e-6, stop_time_s: 10e-3 }
      : { mode: "ac", start_hz: 1e3, stop_hz: 1e9, points_per_decade: 50 },
  };
}

export function normalizeSpiceWorkspace(value: unknown, board?: ParsedBoard | null): SpiceWorkspace {
  if (!value || typeof value !== "object" || (value as Partial<SpiceWorkspace>).contract !== SPICE_WORKSPACE_CONTRACT) {
    return defaultSpiceWorkspace("pi", board);
  }
  const candidate = value as Partial<SpiceWorkspace>;
  return {
    ...defaultSpiceWorkspace(candidate.domain === "si" ? "si" : "pi", board),
    ...candidate,
    contract: SPICE_WORKSPACE_CONTRACT,
    models: Array.isArray(candidate.models) ? candidate.models : builtInModels(),
    assignments: Array.isArray(candidate.assignments) ? candidate.assignments : [],
    parasitics: Array.isArray(candidate.parasitics) ? candidate.parasitics : [],
  } as SpiceWorkspace;
}

export function componentPads(board: ParsedBoard | null, component: ParsedComponent | string | null): ParsedPad[] {
  const reference = typeof component === "string" ? component : component?.ref ?? "";
  return board?.pads.filter(pad => pad.ref === reference).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })) ?? [];
}

export function createSpiceAssignment(board: ParsedBoard, component: ParsedComponent, model: SpiceModel): SpiceAssignment {
  const pads = componentPads(board, component);
  return {
    id: `assignment-${crypto.randomUUID()}`,
    component_ref: component.ref,
    model_id: model.id,
    enabled: true,
    pin_bindings: model.pins.map((pin, index) => {
      const pad = pads[index];
      return {
        model_pin: pin,
        pad_id: pad?.id ?? "",
        board_net: pad?.net ?? "",
        circuit_node: pad?.net ?? `${component.ref}.${pad?.name ?? pin}`,
      };
    }),
    ratings: {},
    vectors: {},
  };
}

export function parasiticsFromResult(result: SolverResultBundle | null, groundNode: string): SpiceParasitic[] {
  if (!result) return [];
  return result.parasitics.flatMap((item, index) => {
    const resistance = Number(item.resistance_ohm ?? 0);
    const inductance = Number(item.inductance_h ?? 0);
    const capacitance = Number(item.capacitance_f ?? 0);
    const conductance = Number(item.conductance_s ?? 0);
    if (![resistance, inductance, capacitance, conductance].some(value => Number.isFinite(value) && value > 0)) return [];
    const net = item.net || `net-${index + 1}`;
    return [{
      id: `parasitic-${result.analysis_id}-${index + 1}`,
      enabled: true,
      net,
      from_node: `${net}:source`,
      to_node: `${net}:load`,
      reference_node: groundNode,
      resistance_ohm: Number.isFinite(resistance) ? resistance : 0,
      inductance_h: Number.isFinite(inductance) ? inductance : 0,
      capacitance_f: Number.isFinite(capacitance) ? capacitance : 0,
      conductance_s: Number.isFinite(conductance) ? conductance : 0,
      source_result_id: result.analysis_id,
      model_status: item.model_status ?? result.model_status,
      endpoint_reviewed: false,
      source_network_index: index,
      source_mesh_nodes: Number.isInteger(item.source_node) && Number.isInteger(item.sink_node)
        ? [Number(item.source_node), Number(item.sink_node)]
        : undefined,
    }];
  });
}
