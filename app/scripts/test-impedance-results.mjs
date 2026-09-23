import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/analysisResults.ts", import.meta.url), "utf8")
  .replace(
    'import { numericMaximum } from "./numericRange";',
    "const numericMaximum = (values, fallback = 0) => values.length ? Math.max(...values) : fallback;",
  );
const transpiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const results = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);

const sweep = [{
  frequency_hz: 1e6,
  resistance_ohm: 0.02,
  reactance_ohm: 0.1,
  magnitude_ohm: Math.hypot(0.02, 0.1),
  phase_deg: 78.6900675,
}];
const emptyScalars = {
  voltage_v: [], voltage_drop_v: [], current_a: [], current_density_a_mm2: [],
  operating_point_impedance_ohm: [], power_loss_w: [], via_current_density_a_mm2: [],
};
const emptyVectors = { current_density: [], electric_field: [], magnetic_field: [] };

const direct = results.normalizeSolverResult({
  contract: "spike/v1",
  analysis_id: "direct-ac",
  mode: "ac",
  status: "completed",
  model_status: "approximate",
  summary: {},
  scalar_fields: emptyScalars,
  vector_fields: emptyVectors,
  mesh: [],
  networks: { parasitics: [{ net: "VDD", impedance: sweep }] },
  time_series: { times_s: [], frames: [] },
  probes: [], issues: [], provenance: {},
});
assert.equal(direct.parasitics.length, 1, "direct plugin results must retain networks.parasitics");
assert.equal(results.resultModeAvailable(direct, "impedance"), true);

const generic = results.normalizeSolverResult({
  contract: "spike/v1",
  analysis_id: "generic-ac",
  mode: "broadband_hf",
  status: "completed",
  model_status: "approximate",
  summary: {},
  fields: { visualization: { scalar_fields: {}, vector_fields: {}, mesh: [] } },
  networks: { parasitics: [{ net: "VDD", impedance: sweep }] },
  probes: [], issues: [], provenance: {},
});
assert.equal(generic.parasitics[0].impedance[0].frequency_hz, 1e6);
assert.equal(results.resultModeAvailable(generic, "impedance"), true);
assert.equal(results.resultModeAvailable(generic, "voltage"), false);
assert.equal(generic.scalar_fields.operating_point_impedance_ohm.length, 0,
  "network-only Z(f) must not be treated as a fabricated spatial impedance field");

const dc = results.normalizeSolverResult({
  contract: "spike/v1", analysis_id: "direct-dc", mode: "dc", status: "completed", model_status: "approximate",
  summary: { operating_point_impedance_ohm: 12 },
  scalar_fields: { ...emptyScalars, operating_point_impedance_ohm: [{ x_mm: 1, y_mm: 2, layer: "F.Cu", net: "VDD", value: 12 }] },
  vector_fields: emptyVectors, mesh: [], time_series: { times_s: [], frames: [] }, probes: [], issues: [], provenance: {},
});
assert.equal(dc.scalar_fields.operating_point_impedance_ohm[0].value, 12);
assert.equal(results.resultModeAvailable(dc, "impedance"), true, "DC V/I samples must enable PI impedance view");

console.log("impedance result normalization and availability assertions passed");
