import type { ThermalScenarioView } from "./thermalScene";
import type { EmiSetup } from "./EmiWorkbench";

export type WorkflowSymbol = { id: string; label: string; detail: string; column: number; target?: string };
export type WorkflowWire = { from: string; to: string; label: string; scope?: boolean };
export type WorkflowSchematic = { nodes: WorkflowSymbol[]; edges: WorkflowWire[]; notes: string[] };
const value = (v: number | undefined, unit: string) => v !== undefined && Number.isFinite(v) ? `${v} ${unit}` : `${unit} unassigned`;

type ThermalNetworkInputs = {
  ambient_temperature_c?: number;
  convection?: string;
  thermal_elements?: Array<Pick<NonNullable<ThermalScenarioView["thermal_elements"]>[number], "id" | "enabled" | "name" | "reference" | "kind" | "power_w">>;
  thermal_links?: ThermalScenarioView["thermal_links"];
  heat_sources?: Array<Pick<NonNullable<ThermalScenarioView["heat_sources"]>[number], "id" | "element_id" | "name" | "reference" | "power_w"> & { theta_ja_c_per_w?: number }>;
};
export function thermalSchematic(scenario: ThermalNetworkInputs): WorkflowSchematic {
  const nodes: WorkflowSymbol[] = [];
  const edges: WorkflowWire[] = [];
  const notes: string[] = [];
  const elements = (scenario.thermal_elements ?? []).filter(element => element.enabled !== false);
  elements.forEach(element => nodes.push({ id: element.id, label: element.reference || element.name || element.id, detail: `${element.kind || "Thermal element"} · ${value(element.power_w, "W")}`, column: element.power_w ? 0 : 1 }));
  (scenario.heat_sources ?? []).forEach((source, index) => {
    if (source.element_id && scenario.thermal_elements?.some(element => element.id === source.element_id && element.enabled === false)) return;
    if (source.element_id && elements.some(element => element.id === source.element_id)) return;
    const id = source.id || `heat-${index}`;
    if (!nodes.some(node => node.id === id)) nodes.push({ id, label: source.reference || source.name || (id === "board-total" ? "Board dissipation" : id), detail: value(source.power_w, "W"), column: 0 });
  });
  const ids = new Set(nodes.map(node => node.id));
  (scenario.thermal_links ?? []).filter(link => link.enabled !== false).forEach(link => {
    if (!ids.has(link.from_id) || !ids.has(link.to_id)) { notes.push(`Link ${link.id} has a missing or disabled endpoint.`); return; }
    edges.push({ from: link.from_id, to: link.to_id, label: `${link.kind || "Contact"} · ${value(link.resistance_c_per_w, "°C/W")}` });
  });
  nodes.push({ id: "__ambient__", label: "Ambient", detail: `${value(scenario.ambient_temperature_c, "°C")} · ${scenario.convection || "Boundary unassigned"}`, column: 2 });
  // Only the explicitly entered lumped source resistance establishes an ambient link.
  (scenario.heat_sources ?? []).forEach((source, index) => {
    const resistance = (source as typeof source & { theta_ja_c_per_w?: number }).theta_ja_c_per_w;
    const id = source.element_id && ids.has(source.element_id) ? source.element_id : source.id || `heat-${index}`;
    if (resistance !== undefined && Number.isFinite(resistance) && resistance > 0 && ids.has(id)) edges.push({ from: id, to: "__ambient__", label: `${resistance} °C/W` });
  });
  const disconnected = nodes.filter(node => node.id !== "__ambient__" && !edges.some(edge => edge.from === node.id || edge.to === node.id));
  if (disconnected.length) notes.push(`${disconnected.length} elements have no explicit thermal link in this network. Review contacts and boundary conditions.`);
  notes.push("Shows entered thermal links and lumped ambient resistances. CFD heat-flow direction and temperature require a solver result.");
  return { nodes, edges, notes };
}

export function emiSchematic(setup: EmiSetup): WorkflowSchematic {
  const nodes: WorkflowSymbol[] = [{ id: "excitation", label: "Excitation", detail: setup.excitation.mode.replace(/_/g, " "), column: 0, target: "excitation" }];
  const edges: WorkflowWire[] = [];
  if (setup.excitation.mode === "explicit_ports") setup.excitation.ports.forEach((port, index) => {
    nodes.push({ id: `port-${index}`, label: port.name || port.id, detail: `${port.impedance_ohm} Ω · ${port.excite ? "excited" : "passive"}`, column: 0, target: "excitation" });
  });
  setup.selected_nets.forEach((net, index) => {
    const id = `net-${index}`;
    nodes.push({ id, label: net, detail: "Candidate net", column: 1, target: "domain" });
    edges.push({ from: "excitation", to: id, label: "scope", scope: true });
  });
  setup.return_nets.forEach((net, index) => nodes.push({ id: `return-${index}`, label: net, detail: "Return / reference scope", column: 1, target: "domain" }));
  setup.requested_analyses.forEach((analysis, index) => {
    const id = `analysis-${index}`;
    nodes.push({ id, label: analysis.replace(/_/g, " "), detail: setup.environment.kind.replace(/_/g, " "), column: 2, target: "solver" });
    setup.selected_nets.forEach((_, netIndex) => edges.push({ from: `net-${netIndex}`, to: id, label: "evaluate", scope: true }));
  });
  const notes = ["Dashed lines describe test scope, not physical coupling or a compliance result. Click a symbol to edit its setup."];
  if (!setup.selected_nets.length) notes.push("Select candidate nets to define the test domain.");
  if (!setup.return_nets.length) notes.push("No return nets assigned. Review the reference scope.");
  return { nodes, edges, notes };
}
