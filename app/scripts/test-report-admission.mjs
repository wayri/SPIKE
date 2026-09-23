// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/engineeringReport.ts", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node" });
const { buildEngineeringReport } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].contents).toString("base64")}`);
const fields = { voltage_v: [], voltage_drop_v: [{ x_mm: 1, y_mm: 2, net: "VDD", layer: "F.Cu", value: .02 }], current_a: [],
  operating_point_impedance_ohm: [], current_density_a_mm2: [], power_loss_w: [], via_current_density_a_mm2: [] };
const result = { contract: "spike/v1", analysis_id: "failed-pi", status: "failed", mode: "dc", model_status: "approximate",
  summary: { net: "VDD", source_voltage_v: 1, total_load_current_a: 2, max_voltage_drop_v: .02,
    total_copper_loss_w: .04, net_power_loss_w: { VDD: .04 } },
  scalar_fields: fields, vector_fields: { current_density: [], electric_field: [], magnetic_field: [] },
  mesh: [], component_bridges: [], parasitics: [{ net: "VDD", impedance: [{ frequency_hz: 1e3, magnitude_ohm: .1, phase_deg: 0 }] }],
  pdn_multiports: [], loop_parasitics: [], coupling_risks: [], component_stress: [], probes: [],
  time_series: { times_s: [0], frames: [{ time_s: 0, scalar_values: { voltage_drop_v: [.02] } }] },
  issues: [{ severity: "error", code: "PEEC_INDUCTANCE_NONPASSIVE", message: "Negative energy" }],
  provenance: { solved: false, failure_stage: "physical_inductance_admission", numerical_quality: { inductance_passivity: { negative_mode_count: 5 } } } };
const board = { width: 2, height: 3, nets: { 1: "VDD" }, bounds: { minX: 0, minY: 0, maxX: 2, maxY: 3 }, layers: ["F.Cu"], stackup: [], outlineLoops: [],
  tracks: [], vias: [], pads: [], zones: [], components: [] };
const input = { projectName: "Admission fixture", boardFile: "fixture.kicad_pcb", analysisMode: "DC", domain: "pi", board, result,
  setup: { net: "VDD", sources: [], loads: [], returnPath: { mode: "explicit", net: "GND" }, meshDimension: "2d", meshTargetMm: "1",
    zoneCellMm: "1", viaModel: "explicit", viaPlatingMm: ".02", frequencyStart: "1e3", frequencyStop: "1e6", frequencyPoints: "5" },
  limits: { drop: "10", density: "1" }, probes: [], fusingSettings: { ambientTemperatureC: 25, faultDurationS: 1 },
  modelAssignmentCount: 0, pdnReview: { contract: "spike/pdn-review/v1", net: "VDD", target_ohm: .05, status: "pass", candidate_screening: [], resonances: [], anti_resonances: [] },
  projectPayload: {} };
const scriptJson = (html, id) => JSON.parse(html.match(new RegExp(`<script id="${id}" type="application/json">([^<]*)</script>`))?.[1] ?? "null");
let failed;
try { failed = buildEngineeringReport(input); }
catch (error) { console.error(error.message, String(error.stack).split("\n").filter(line => !line.includes("data:text/javascript")).slice(0, 5).join("\n")); process.exit(1); }
const failedEvidence = scriptJson(failed, "evidence-data"), failedGeometry = scriptJson(failed, "report-data");
assert.equal(failedEvidence.analysis.status, "failed");
assert.equal(failedEvidence.solver_provenance.failure_stage, "physical_inductance_admission");
assert.equal(failedEvidence.analytics.rows[0].maxDropV, null);
assert.equal(failedEvidence.analytics.rows[0].conductorLossW, null);
assert.equal(failedEvidence.analysis.pdn_review, null);
assert.deepEqual(failedGeometry.fields, {});
assert.deepEqual(failedGeometry.datasets[0].fields, {});
assert.deepEqual(failedGeometry.impedance, []);
assert.deepEqual(failedGeometry.timeSeries, []);
assert.match(failed, /failed analysis: no solved values or plots are shown/);
for (const variant of [
  { status: "completed", provenance: { solved: false, failure_stage: "late_admission" } },
  { status: "blocked", provenance: { failure_stage: "capability_gate" } },
]) {
  const html = buildEngineeringReport({ ...input, result: { ...result, ...variant } });
  const evidence = scriptJson(html, "evidence-data"), geometry = scriptJson(html, "report-data");
  assert.equal(evidence.analytics.rows[0].maxDropV, null);
  assert.deepEqual(geometry.fields, {});
  assert.deepEqual(geometry.impedance, []);
}
const completed = buildEngineeringReport({ ...input, result: { ...result, status: "completed", provenance: { solver: "fixture" } } });
const completedEvidence = scriptJson(completed, "evidence-data"), completedGeometry = scriptJson(completed, "report-data");
assert.equal(completedEvidence.analytics.rows[0].maxDropV, .02);
assert.equal(completedGeometry.fields.voltage_drop_v.length, 1);
assert.equal(completedGeometry.impedance.length, 1);
console.log("PI report admission: failed partial metrics/plots are hidden, diagnostics retained, completed control preserved.");
