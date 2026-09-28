import type { ResultViewMode, SolverResultBundle } from "./analysisResults";

export type ViewportContextInput = {
  tab: string;
  analysisMode: string;
  hasBoard: boolean;
  hasSelection: boolean;
  hasSelectedNet: boolean;
  hasStoredResults: boolean;
  hasActiveResult: boolean;
};

export const availableViewportResultModes = (result: SolverResultBundle | null): ResultViewMode[] => {
  if (!result) return [];
  const modes: ResultViewMode[] = [];
  if (result.scalar_fields.voltage_v.length) modes.push("voltage");
  if (result.scalar_fields.voltage_drop_v.length) modes.push("voltage_drop");
  if (result.scalar_fields.current_a.length) modes.push("current");
  if (result.scalar_fields.current_density_a_mm2.length) modes.push("current_density");
  if (result.scalar_fields.power_loss_w.length) modes.push("power_loss");
  if (result.scalar_fields.via_current_density_a_mm2.length) modes.push("via_stress");
  // A frequency sweep belongs in the RLC/Z(f) workbench. The viewport impedance
  // field is offered only when the solver returned spatial operating-point data.
  if (result.scalar_fields.operating_point_impedance_ohm.length) modes.push("impedance");
  if (result.mesh.length) modes.push("mesh");
  if (result.vector_fields.electric_field.length) modes.push("electric_field");
  if (result.vector_fields.magnetic_field.length) modes.push("magnetic_field");
  return modes;
};

export const viewportContextLabel = (input: ViewportContextInput) => {
  if (!input.hasBoard) return "NO DESIGN";
  if (input.hasActiveResult) {
    if (input.analysisMode === "AC Impedance Sweep") return "AC RESULT";
    if (input.analysisMode === "Transient PI") return "TRANSIENT";
    if (input.analysisMode === "Bulk Net Analysis") return "BATCH RESULT";
    return "DC RESULT";
  }
  if (input.hasStoredResults) return "RESULTS HIDDEN";
  if (input.tab === "Thermal") return "THERMAL SETUP";
  if (input.tab === "EM" || input.tab === "EMI") return "EM SETUP";
  if (input.tab === "HF / SI") return input.hasSelectedNet ? "NET EXTRACTION" : "SI SETUP";
  if (input.tab === "Probes") return input.hasSelection ? "SELECTION" : "PROBE SETUP";
  if (input.tab === "PI") {
    if (input.analysisMode === "AC Impedance Sweep") return "AC SETUP";
    if (input.analysisMode === "Transient PI") return "TRANSIENT SETUP";
    if (input.analysisMode === "Bulk Net Analysis") return "BATCH SETUP";
    return "DC SETUP";
  }
  return input.hasSelection ? "SELECTION" : "BOARD";
};

export const resultHasExtractedNetworks = (result: SolverResultBundle | null) => Boolean(
  result?.parasitics.length || result?.loop_parasitics.length || result?.pdn_multiports.length,
);
