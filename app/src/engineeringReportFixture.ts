// SPDX-License-Identifier: MIT

import type { SolverResultBundle } from "./analysisResults";
import type { ParsedBoard } from "./boardParser";
import { buildEngineeringReport, type ReportInput } from "./engineeringReport";
import type { ReportDomain } from "./engineeringReportDomain";

const board: ParsedBoard = {
  width: 42, height: 24, bounds: { minX: 0, minY: 0, maxX: 42, maxY: 24 },
  outlineLoops: [[[0, 0], [42, 0], [42, 24], [0, 24]]], tracks: [], vias: [], pads: [],
  components: [], zones: [], drawings: [], layers: ["F.Cu"], layerDefinitions: [], stackup: [],
  nets: { "1": "VDD_CORE", "2": "VDD_IO" },
};

const fixtureDomain = (["pi", "si", "thermal", "emi"].includes(new URLSearchParams(location.search).get("domain") ?? "")
  ? new URLSearchParams(location.search).get("domain") : "pi") as ReportDomain;
const modeByDomain: Record<ReportDomain, string> = { pi: "dc_ir_drop", si: "signal_integrity", thermal: "thermal", emi: "openems" };

const result = (analysisId: string, net: string, voltage: number): SolverResultBundle => {
  const face = (x: number, value: number) => ({ x_mm: x + 3, y_mm: 8, layer: "F.Cu", net, value,
    source_id: `${net}-${x}`, vertices_mm: [[x, 4, 0], [x + 6, 4, 0], [x + 6, 12, 0], [x, 12, 0]] as [number, number, number][] });
  const voltageSamples = [face(2, voltage), face(20, voltage - 0.04)];
  return {
    contract: "spike/analysis-result/v1", analysis_id: analysisId, status: "completed",
    mode: modeByDomain[fixtureDomain], model_status: "synthetic_ui_fixture_not_validated",
    summary: { net, max_voltage_drop_v: 0.04, max_current_density_a_mm2: 5.2, total_copper_loss_w: 0.12, solver_time_s: 0.01 },
    scalar_fields: { voltage_v: voltageSamples, voltage_drop_v: [], current_a: [], operating_point_impedance_ohm: [], current_density_a_mm2: [], power_loss_w: [], via_current_density_a_mm2: [] },
    vector_fields: { current_density: [], electric_field: [], magnetic_field: [] }, mesh: [], component_bridges: [], parasitics: [], pdn_multiports: [], loop_parasitics: [], coupling_risks: [],
    time_series: { times_s: [], frames: [] }, component_stress: [], probes: [], issues: [{ severity: "warning", code: "UI_FIXTURE", message: "Synthetic browser fixture; not solver evidence.", status: "not_validated" }],
    provenance: { solver: "fixture-generator", purpose: "browser UI verification only", numerical_evidence: false },
  };
};

const first = result("UI-FIXTURE-CORE", "VDD_CORE", 1.0);
const second = result("UI-FIXTURE-IO", "VDD_IO", 3.3);
const input: ReportInput = {
  projectName: "Generated report browser fixture - not solver evidence", boardFile: "synthetic-ui-fixture",
  analysisMode: modeByDomain[fixtureDomain], domain: fixtureDomain, board, result: first,
  results: [{ label: "VDD_CORE", bundle: first }, { label: "VDD_IO", bundle: second }],
  setup: { net: "VDD_CORE", sources: [], loads: [], returnPath: { mode: "explicit", net: "GND" }, meshDimension: "2D", meshTargetMm: "1", zoneCellMm: "1", viaModel: "none", viaPlatingMm: "0", frequencyStart: "-", frequencyStop: "-", frequencyPoints: "-" },
  limits: { drop: "100", density: "10" }, probes: [], fusingSettings: { ambientTemperatureC: 25, faultDurationS: 1 }, modelAssignmentCount: 0,
  projectPayload: { contract: "spike/ui-fixture/v1", fixture_only: true },
};
if (fixtureDomain === "si") input.si = { channelResult: { model_status: "synthetic_ui_fixture_not_validated", compliance_status: "not_evaluated", extraction: { characteristic_impedance_ohm: 50 }, eye: {} }, suite: null };
if (fixtureDomain === "thermal") input.thermal = { scenario: { field_result: { model_status: "synthetic_ui_fixture_not_validated", summary: { max_temperature_c: 62, min_temperature_c: 25, max_temperature_rise_c: 37, total_dissipation_w: 1.2, ambient_temperature_c: 25 }, fields: { temperature_c: [] } } } };
if (fixtureDomain === "emi") input.emi = { setup: { contract: "spike/emi-setup/v1", chamber: {}, selected_nets: ["VDD_CORE"], return_nets: ["GND"], requested_analyses: ["far_field"], frequency: { start_hz: 1e6, stop_hz: 1e9, points: 101 }, environment: { kind: "free_space" }, mesh: { resolution_mm: 1, padding_cells: 8 }, max_solver_time_s: 60, excitation: { mode: "explicit_ports", ports: [] }, net_metrics: [], viewport: { translucent_board: true, analysis_nets_only: true } } as never, preflight: null, screening: null, fieldResult: null };

document.open();
document.write(buildEngineeringReport(input));
document.close();
