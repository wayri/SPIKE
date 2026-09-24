// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/engineeringReport.ts", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node" });
const { buildEngineeringReport } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].contents).toString("base64")}`);
const componentResult = {
  contract: "spike/thermal-result/v1", status: "completed", model_status: "approximate", mode: "transient", ambient_temperature_c: 25,
  summary: { total_power_w: 2, max_temperature_c: 44 },
  nodes: [{ id: "U1", component_ref: "U1", power_w: 2, temperature_c: 44, steady_temperature_c: 45, heat_flow_top_w: 1, heat_flow_bottom_w: 1 }],
  surfaces: [{ id: "case-air", object_ref: "U1", surface: "case-outer", kind: "convection", heat_flow_w: 0.5 }],
  transient: [{ time_s: 0, temperatures_c: { U1: 25 } }, { time_s: 20, temperatures_c: { U1: 44 } }],
  issues: [{ severity: "warning", message: "Complete ambient paths required" }],
};
const input = {
  projectName: "Thermal fixture", boardFile: "fixture.kicad_pcb", analysisMode: "Thermal", domain: "thermal", board: null, result: null,
  setup: { net: "", sources: [], loads: [], returnPath: { mode: "explicit", net: "" }, meshDimension: "2d", meshTargetMm: "1",
    zoneCellMm: "1", viaModel: "explicit", viaPlatingMm: ".02", frequencyStart: "1e3", frequencyStop: "1e6", frequencyPoints: "5" },
  limits: { drop: "10", density: "1" }, probes: [], fusingSettings: { ambientTemperatureC: 25, faultDurationS: 1 },
  modelAssignmentCount: 0, pdnReview: null, projectPayload: {}, thermal: { scenario: { ambient_temperature_c: 25, component_result: componentResult } },
};
const completed = buildEngineeringReport(input);
assert.match(completed, /<b>completed<\/b><span> \| approximate<\/span>/);
assert.match(completed, /Component temperatures and heat paths/);
assert.match(completed, /<td>U1<\/td><td>2<\/td><td>44<\/td>/);
assert.match(completed, /approximate lumped RC model/);
assert.match(completed, /Object and surface heat flows/);
assert.match(completed, /<td>U1<\/td><td>case-outer<\/td><td>convection<\/td>/);
assert.doesNotMatch(completed, /RLCG and impedance extraction/);
assert.doesNotMatch(completed, /No numerical result is attached/);

const blocked = buildEngineeringReport({ ...input, thermal: { scenario: { component_result: { ...componentResult, status: "blocked", nodes: [] } } } });
assert.match(blocked, /<b>blocked<\/b>/);
assert.doesNotMatch(blocked, /Component temperatures and heat paths/);
console.log("component thermal report result and blocked-state checks passed");
