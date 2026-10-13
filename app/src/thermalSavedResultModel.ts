// SPDX-License-Identifier: Apache-2.0
import type { SimulationStudy } from "./simulationStudies";
import { boardThermalViewportGrid } from "./boardThermalViewport";

export type ThermalRecord = Record<string, unknown>;
export type SavedThermalEntry = {
  id: string; name: string; result: ThermalRecord; request: ThermalRecord | null;
  capturedAt?: string; source: string; inputsChanged: boolean;
};
export const thermalRecord = (value: unknown): ThermalRecord | null =>
  value && typeof value === "object" && !Array.isArray(value) ? value as ThermalRecord : null;
const text = (value: unknown) => typeof value === "string" ? value : "";
function identity(value: unknown): string {
  return JSON.stringify(value, (_, item) => item && typeof item === "object" && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
}

/** Index retained results by reference; browsing never updates inputs or starts a solver. */
export function savedThermalEntries(scenario: ThermalRecord | null, studies: SimulationStudy[]): SavedThermalEntry[] {
  const entries: SavedThermalEntry[] = [];
  function add(id: string, name: string, snapshot: unknown, inputs: unknown, source: string, capturedAt?: string) {
    const container = thermalRecord(snapshot);
    if (!container) return;
    const isResult = (value: ThermalRecord) => typeof value.contract === "string" && /thermal[^/]*-result\//.test(value.contract);
    const candidates = isResult(container) ? [["", container]] as const
      : ["board_thermal_result", "component_result", "result", "field_result"].map(key => [key, thermalRecord(container[key])] as const);
    for (const [key, result] of candidates) {
      if (!result || !isResult(result)) continue;
      const inputContainer = thermalRecord(inputs);
      const configured = thermalRecord(container.board_thermal_request) ?? thermalRecord(inputContainer?.board_thermal_request);
      const recorded = thermalRecord(thermalRecord(result.provenance)?.request);
      const request = recorded ?? configured ?? inputContainer;
      entries.push({ id: `${id}:${key || "thermal"}`, name: key === "board_thermal_result" ? `${name} - board thermal` : name,
        result, request, capturedAt, source,
        inputsChanged: Boolean(recorded && configured && identity(recorded) !== identity(configured)) });
    }
  }
  add("workspace", text(scenario?.name) || "Saved thermal study", scenario, scenario, "Saved project thermal scenario");
  for (const study of studies) for (const item of study.cases) {
    if (item.type !== "thermal") continue;
    const name = `${study.name} / ${item.name}`;
    add(`${study.id}:${item.id}`, name, item.resultSnapshot, item.scenario, "Captured case result");
    for (const run of item.runs) add(`${study.id}:${item.id}:${run.id}`, `${name} / ${run.capturedAt}`,
      run.resultSnapshot, run.scenario, "Retained run history", run.capturedAt);
  }
  return entries;
}

/** Report evidence exactly: a small linear residual is not mesh convergence. */
export function thermalResultEvidence(entry: SavedThermalEntry) {
  const result = entry.result;
  const provenance = thermalRecord(result.provenance);
  const board = thermalRecord(entry.request?.board);
  const warnings: string[] = [];
  for (const key of ["zones", "tracks", "pads", "vias", "copper"])
    if (board?.[`include_${key}`] === false) warnings.push(`${key} excluded from the saved thermal model`);
  const scope = text(entry.request?.study_scope);
  if (scope) warnings.push(scope);
  const convergence = thermalRecord(result.convergence);
  const meshConverged = convergence?.mesh_converged === true;
  if (!meshConverged) warnings.push("Mesh/grid convergence is not established by this saved result.");
  if (text(provenance?.board_model).includes("layered"))
    warnings.push("Single-board structured model: assembly cooling contacts, casings, airflow coupling and radiation are not established by this result.");
  const issues = Array.isArray(result.issues) ? result.issues.map(thermalRecord).filter(Boolean) : [];
  for (const issue of issues) if (text(issue?.message)) warnings.push(`${text(issue?.severity) || "issue"}: ${text(issue?.message)}`);
  return { status: text(result.status) || "Not recorded", modelStatus: text(result.model_status) || "Not recorded",
    solverId: text(provenance?.solver_id) || text(result.solver_id) || "Not recorded",
    designId: text(provenance?.design_id) || text(result.design_id) || "Not recorded",
    meshConverged, warnings: Array.from(new Set(warnings)), grid: boardThermalViewportGrid(result) };
}
