// SPDX-License-Identifier: Apache-2.0

import { resultModeAvailable, type PdnReview, type ResultViewMode, type ResultVisualization, type SolverResultBundle } from "./analysisResults";
import { DEFAULT_COPPER_FUSING_SETTINGS, buildResultEngineeringAnalytics } from "./resultAnalytics";
import { buildProbeRows, evaluateProbeFormulas, type ProbeFormulaRow, type ProbeInput, type ProbeReferenceValues } from "./probeCalculations";
import { encodeDetachedRowId, MAX_DETACHED_ROWS, type DetachedToolControl, type DetachedToolSnapshot } from "./detachedToolWindowModel";
import { buildDetachedTracePayload } from "./detachedTracePayload";

const shown = (value?: { value: number; unit: string }) => value ? `${value.value.toPrecision(6)} ${value.unit === "1" ? "" : value.unit}`.trim() : "-";
const finite = (value: number | null) => value === null || !Number.isFinite(value) ? "-" : value;

export function buildDetachedProbeSnapshot(
  probes: readonly ProbeInput[],
  result: SolverResultBundle | null,
  formulaRows: readonly ProbeFormulaRow[],
  referenceIds: Readonly<Record<string, string>> = {},
): DetachedToolSnapshot {
  const probeRows = buildProbeRows(probes, result, referenceIds);
  const references: ProbeReferenceValues = Object.fromEntries(probeRows.map(row => [row.id, row.values]));
  const calculations = evaluateProbeFormulas(formulaRows, references);
  const rows = [
    ...probeRows.map(row => ({
      id: encodeDetachedRowId(row.sourceId),
      cells: [row.id, row.name, row.status, `${row.net ?? "No net"} / ${row.layer ?? "through"}`, shown(row.values.voltage), shown(row.values.current), shown(row.values.power), shown(row.values.drop), shown(row.values.density), shown(row.values.impedance), "", ""],
      title: row.message,
      editActions: { 1: "rename-probe" },
      actions: [{ id: "delete-probe", label: "Delete", destructive: true }],
    })),
    ...calculations.map(row => ({
      id: encodeDetachedRowId(row.id),
      cells: [row.id, row.name, row.error ? "error" : "calculated", "-", "-", "-", "-", "-", "-", "-", row.formula, row.error ?? shown(row.result)],
      title: row.error,
      editActions: { 1: "rename-formula", 10: "edit-formula" },
      actions: [{ id: "delete-formula", label: "Delete", destructive: true }],
    })),
  ];
  const truncated = rows.length > MAX_DETACHED_ROWS;
  return {
    kind: "probes",
    title: "Probe results",
    revision: 0,
    status: truncated
      ? `${probeRows.length} probes; ${calculations.length} formulas. Showing ${MAX_DETACHED_ROWS} of ${rows.length} rows; export preserves the authoritative full table.`
      : `${probeRows.length} probes; ${calculations.length} formulas.`,
    columns: ["ID", "Name", "Status", "Net / layer", "Voltage", "Current", "Power", "Drop", "Density", "Ohm", "Formula", "Result / error"],
    rows: rows.slice(0, MAX_DETACHED_ROWS),
    controls: [
      { id: "add-formula", label: "Add formula", kind: "button" },
      { id: "export-csv", label: "Export CSV", kind: "button", disabled: rows.length === 0 },
    ],
    emptyMessage: "No probes placed. Place a probe on a conductor to begin.",
  };
}

const modes: Array<{ value: ResultViewMode; label: string; domains: Array<"pi" | "si"> }> = [
  { value: "geometry", label: "Geometry", domains: ["pi", "si"] },
  { value: "voltage", label: "Absolute voltage", domains: ["pi"] },
  { value: "voltage_drop", label: "Relative drop", domains: ["pi"] },
  { value: "current", label: "Current", domains: ["pi"] },
  { value: "current_density", label: "Current density", domains: ["pi"] },
  { value: "power_loss", label: "Copper loss", domains: ["pi"] },
  { value: "via_stress", label: "Via stress", domains: ["pi"] },
  { value: "impedance", label: "Impedance", domains: ["pi", "si"] },
  { value: "mesh", label: "Solver mesh", domains: ["pi", "si"] },
  { value: "electric_field", label: "Electric field", domains: ["si"] },
  { value: "magnetic_field", label: "Magnetic field", domains: ["si"] },
];

type DetachedVisualization = ResultVisualization & { viewMode?: "2D" | "3D"; dataCursor?: boolean };

const scalarMode = (mode: ResultViewMode) => ["voltage", "voltage_drop", "current", "current_density", "power_loss", "via_stress"].includes(mode);

function resultLayers(result: SolverResultBundle | null): string[] {
  if (!result) return [];
  return [...new Set([
    ...Object.values(result.scalar_fields).flatMap(samples => samples.map(sample => sample.layer)),
    ...Object.values(result.vector_fields).flatMap(samples => samples.map(sample => sample.layer)),
    ...result.mesh.map(cell => cell.layer),
  ].filter((layer): layer is string => Boolean(layer) && layer !== "through"))].sort();
}

function activeSampleCount(result: SolverResultBundle | null, mode: ResultViewMode): number {
  if (!result) return 0;
  const scalar: Partial<Record<ResultViewMode, number>> = {
    voltage: result.scalar_fields.voltage_v.length, voltage_drop: result.scalar_fields.voltage_drop_v.length,
    current: result.scalar_fields.current_a.length, current_density: result.scalar_fields.current_density_a_mm2.length,
    power_loss: result.scalar_fields.power_loss_w.length, via_stress: result.scalar_fields.via_current_density_a_mm2.length,
    impedance: result.scalar_fields.operating_point_impedance_ohm.length + result.parasitics.reduce((sum, item) => sum + (item.impedance?.length ?? 0), 0),
    mesh: result.mesh.length, electric_field: result.vector_fields.electric_field.length, magnetic_field: result.vector_fields.magnetic_field.length,
  };
  return scalar[mode] ?? 0;
}

export function buildDetachedResultsSnapshot(
  result: SolverResultBundle | null,
  visualization: DetachedVisualization,
  domain: "pi" | "si",
): DetachedToolSnapshot {
  const analytics = buildResultEngineeringAnalytics(result, null, DEFAULT_COPPER_FUSING_SETTINGS);
  const availableModes = modes.filter(mode => mode.domains.includes(domain) && resultModeAvailable(result, mode.value));
  const selectedMode = availableModes.some(mode => mode.value === visualization.mode) ? visualization.mode : availableModes[0]?.value ?? "geometry";
  const samples = activeSampleCount(result, selectedMode);
  const hasScalar = scalarMode(selectedMode) && samples > 0;
  const layers = resultLayers(result);
  const controls: DetachedToolControl[] = [
    { id: "field", label: "Field", kind: "select", value: selectedMode, options: availableModes.map(({ value, label }) => ({ value, label })) },
    { id: "scene", label: "Scene", kind: "select", value: visualization.sceneMode, options: [
      { value: "opaque", label: "Opaque board" }, { value: "translucent", label: "Translucent board" },
      { value: "analysis_only", label: "Analysis only" }, { value: "results_only", label: "Results only" },
    ] },
    { id: "plot", label: "Plot", kind: "select", value: hasScalar ? visualization.plotStyle : "flat", options: hasScalar
      ? [{ value: "flat", label: "Flat" }, { value: "height", label: "Height" }, { value: "contour", label: "Contour" }]
      : [{ value: "flat", label: "Flat" }] },
    { id: "view", label: "View", kind: "select", value: visualization.viewMode ?? "3D", options: [{ value: "2D", label: "2D" }, { value: "3D", label: "3D" }] },
  ];
  if (hasScalar && visualization.plotStyle !== "contour") controls.push({ id: "style", label: "Field style", kind: "select", value: visualization.fieldStyle, options: [{ value: "cells", label: "Solver cells" }, { value: "smooth", label: "Smooth display" }] });
  if (layers.length) controls.push({ id: "layer", label: "Layer", kind: "select", value: visualization.visibleResultLayers.length === 1 ? visualization.visibleResultLayers[0] : "", options: [{ value: "", label: "All stitched" }, ...layers.map(layer => ({ value: layer, label: layer }))] });
  if (samples > 0 && !["geometry", "mesh"].includes(selectedMode)) controls.push({ id: "data-cursor", label: "Data cursor", kind: "toggle", value: Boolean(visualization.dataCursor) });
  const rows = analytics.fields.map(field => ({ id: encodeDetachedRowId(`field:${field.key}`), cells: [field.label, field.count, finite(field.minimum), finite(field.mean), finite(field.percentile95), finite(field.maximum), field.unit || "-"] }));
  return {
    kind: "results", title: domain === "pi" ? "PI results" : "SI / HF results", revision: 0,
    status: result ? `${result.status} | ${result.model_status} | ${samples} active samples | ${analytics.probeSummary.mapped}/${analytics.probeSummary.total} probes mapped` : "No completed analysis result",
    columns: ["Field", "Samples", "Minimum", "Mean", "P95", "Maximum", "Unit"], rows, controls,
    emptyMessage: "No scalar result summaries are available for this analysis.",
  };
}

export function buildDetachedTraceSnapshot(result: SolverResultBundle | null, domain: "pi" | "si", pdnReview?: PdnReview | null): DetachedToolSnapshot {
  const trace = buildDetachedTracePayload(result, domain, pdnReview?.net, pdnReview?.target_ohm);
  return {
    kind: "trace-plots", title: domain === "pi" ? "PI trace graphs" : "SI / HF trace graphs", revision: 0,
    status: trace.notice, columns: [], rows: [], trace, emptyMessage: "No trace result is available.",
  };
}
