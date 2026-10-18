// SPDX-License-Identifier: Apache-2.0
// Display names never replace registry, worker-method or persisted capability IDs.
import { solverSuiteCatalog, type SolverSuiteCapability } from "./solverSuiteCatalog";

export type SolverOrigin = "internal" | "external" | "support" | "planned";
export const solverOriginLabels: Record<SolverOrigin, string> = {
  internal: "Internal solvers and models", external: "External engine adapters",
  support: "Execution and supporting tools", planned: "Planned / unavailable",
};
export type RuntimeSolver = {
  id: string; name: string; state: string; model_status: string;
  runnable?: boolean; reason?: string; analyses?: string[];
};
const names: Record<string, string> = {
  "pi-dc": "SPIKE DC PI", "pi-peec": "SPIKE 2.5D PI",
  "pi-solid-dc": "SPIKE 3D PI - DC conduction", "pi-transient": "SPIKE PI Transient",
  "pi-pdn": "SPIKE PDN and Filters", "pi-capacitance": "SPIKE 3D Capacitance",
  "pi-dielectric-ac": "SPIKE Dielectric AC", "pi-reduction": "SPIKE Port Reduction",
  "pi-engineering": "SPIKE PI Engineering Screens",
  "si-networks": "SPIKE SI Networks", "si-channels": "SPIKE SI Channels",
  "si-eye": "SPIKE SI Eye and Protocol Screens",
  "thermal-board": "SPIKE Board Thermal", "thermal-solids": "SPIKE 3D Solid Thermal",
  "thermal-electrothermal": "SPIKE Assembly Electrothermal", "thermal-pwm": "SPIKE PWM Electrothermal",
  "thermal-channel": "SPIKE Channel Airflow", "cfd-native": "SPIKE 2D CFD",
  "em-magnetic": "SPIKE 2D Magnetic FEM", "em-lumped": "SPIKE Lumped EM Machines",
  "mechanics-static": "SPIKE 3D Structural", "mechanics-thermoelastic": "SPIKE Thermoelastic",
  "circuit-native": "SPIKES Circuit MNA", "circuit-adaptive": "SPIKES Adaptive Transient",
  "circuit-equations": "SPIKES I/Q Device Models", "circuit-physics-parts": "SPIKES Lumped Physics Models",
  "circuit-smps": "SPIKES SMPS Stability", "circuit-battery": "SPIKES Battery Reference",
  "circuit-libraries": "SPIKES Passive and Digital Models", "circuit-tcad": "SPIKES 1D Equilibrium TCAD",
  "execution-cosim": "SPIKE Scalar Co-simulation",
  "planned-mom": "SPIKE Surface MoM (planned)", "planned-fullwave": "SPIKE 3D Full-wave (planned)",
};
export const capabilitySolverIds: Readonly<Record<string, readonly string[]>> = {
  "pi-dc": ["spike.routed_dc"], "pi-peec": ["spike.peec_2_5d"],
  "pi-transient": ["spike.peec_rl_transient"],
  "circuit-native": ["spike.native_mna_workspace", "spike.owned_spice_workspace", "spike.native_mna"],
  "planned-mom": ["spike.mom_surface"], "planned-fullwave": ["spike.fullwave_3d"],
};
const registryNames: Record<string, string> = {
  "spike.routed_dc": "SPIKE DC PI", "spike.peec_2_5d": "SPIKE 2.5D PI",
  "spike.peec_rl_transient": "SPIKE PI Transient", "spike.mom_surface": "SPIKE Surface MoM",
  "spike.fullwave_3d": "SPIKE 3D Full-wave", "spike.native_mna_workspace": "SPIKE Linear Circuit MNA",
  "spike.native_mna": "SPIKE Linear Circuit MNA", "spike.owned_spice_workspace": "SPIKES Circuit MNA",
  "spike.field_circuit_cosimulation": "SPIKE PEEC / Circuit Co-simulation",
};
export function solverDisplayName(item: SolverSuiteCapability): string {
  return names[item.id] ?? item.title;
}
export function solverOrigin(item: SolverSuiteCapability): SolverOrigin {
  if (item.status === "planned") return "planned";
  if (item.status === "external") return "external";
  if (["execution-workers", "execution-extensions"].includes(item.id)) return "support";
  return "internal";
}
export function runtimeSolverName(solver: RuntimeSolver): string {
  return registryNames[solver.id] ?? solver.name;
}
export function runtimeSolverOrigin(solver: RuntimeSolver): "internal" | "external" {
  // ngspice's historical spike.* alias is still an external engine.
  return solver.id.startsWith("external.") || solver.id === "spike.ngspice" ? "external" : "internal";
}
export function runtimeWorkflow(solver: RuntimeSolver): SolverSuiteCapability | undefined {
  return solverSuiteCatalog.find(item => item.action && capabilitySolverIds[item.id]?.includes(solver.id));
}
export function filterManagerCapabilities(entries: readonly SolverSuiteCapability[], query: string, origin: SolverOrigin | "all") {
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return entries.filter(item => (origin === "all" || solverOrigin(item) === origin) && words.every(word =>
    `${solverDisplayName(item)} ${item.id} ${item.title} ${item.group} ${item.summary} ${item.limits} ${item.reference} ${item.source} ${item.extensionId ?? ""} ${(capabilitySolverIds[item.id] ?? []).join(" ")}`.toLowerCase().includes(word)));
}
