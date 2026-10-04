// SPDX-License-Identifier: Apache-2.0
const apiLabels: Record<string, string> = { pcb_layer_polygons: "Layer-aware PCB polygons", pcb_geometry: "PCB geometry and materials", microwave_sweep: "Microwave frequency sweeps", microwave_boundaries: "Ports and absorbing boundaries", mesh_generation: "Engine mesh generation", mesh_sizing: "Engine mesh sizing", mesh_export: "Mesh topology export" };

export function emergeRuntimePresentation(value: Record<string, unknown>) {
  const available = value.available === true, version = typeof value.version === "string" ? value.version : "", exercised = value.adapter_evidence === "executed_fixture";
  const checks = value.api_checks && typeof value.api_checks === "object" && !Array.isArray(value.api_checks) ? Object.entries(value.api_checks).filter(([, present]) => typeof present === "boolean").map(([id, present]) => ({ id, label: apiLabels[id] ?? id, present: present === true })) : [];
  const capabilities = Array.isArray(value.capabilities) ? value.capabilities.filter((item): item is string => typeof item === "string") : [];
  return { available, checks, capabilities, title: available ? `EMerge ${version} APIs available` : "EMerge runtime unavailable", message: !available ? String(value.reason ?? "Select an EMerge 3+ interpreter and check its runtime.") : exercised ? "Adapter execution evidence is recorded for this release. Results remain unvalidated." : "Required APIs are detected. Execution qualification is pending for this release." };
}
