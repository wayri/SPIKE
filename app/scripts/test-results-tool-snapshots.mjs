// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const bundle = await build({ entryPoints: [fileURLToPath(new URL("../src/resultsToolSnapshots.ts", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node" });
const snapshots = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].contents).toString("base64")}`);
const modelBundle = await build({ entryPoints: [fileURLToPath(new URL("../src/detachedToolWindowModel.ts", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node" });
const model = await import(`data:text/javascript;base64,${Buffer.from(modelBundle.outputFiles[0].contents).toString("base64")}`);

const result = {
  status: "completed", model_status: "validated", mode: "dc", summary: {}, analysis_id: "a", contract: "spike/v1",
  scalar_fields: { voltage_v: [{ value: 1, x_mm: 0, y_mm: 0, layer: "F.Cu" }], voltage_drop_v: [], current_a: [], operating_point_impedance_ohm: [], current_density_a_mm2: [], power_loss_w: [], via_current_density_a_mm2: [] },
  vector_fields: { current_density: [], electric_field: [], magnetic_field: [] }, mesh: [], component_bridges: [], parasitics: [], pdn_multiports: [], loop_parasitics: [], coupling_risks: [],
  time_series: { times_s: [], frames: [] }, component_stress: [], issues: [], provenance: {},
  probes: [{ id: "pad/1 dangerous", status: "mapped", voltage_v: 1, peak_adjacent_current_a: 2 }],
};
const probeSnapshot = snapshots.buildDetachedProbeSnapshot([{ id: "pad/1 dangerous", name: "Input", net: "VCC", layer: "F.Cu" }], result, [{ id: "C1", name: "Power", formula: "P_1.voltage" }], { "pad/1 dangerous": "P_1" });
assert.equal(probeSnapshot.rows.length, 2);
assert.equal(probeSnapshot.rows[0].cells[0], "P_1");
assert.equal(probeSnapshot.rows[0].editActions[1], "rename-probe");
assert.equal(probeSnapshot.rows[1].editActions[10], "edit-formula");
assert.match(probeSnapshot.rows[0].id, /^row_/);

const resultsSnapshot = snapshots.buildDetachedResultsSnapshot(result, {
  visible: true, mode: "voltage", analysisOnly: false, boardOpacity: 0.2, showVectors: false, vectorScale: 1,
  viaModel: "extracted", translucentScene: false, sceneMode: "opaque", showComponentModels: true,
  plotStyle: "flat", fieldStyle: "cells", waveHeightScale: 1, fusingAmbientC: 25, fusingDurationS: 1,
  animationPlaying: false, animationFrame: 0, animationFps: 12, impedanceFrequencyHz: null, visibleResultLayers: [],
}, "pi");
const control = id => resultsSnapshot.controls.find(item => item.id === id);
assert.deepEqual(control("field").options.map(item => item.value), ["geometry", "voltage"]);
assert.deepEqual(control("layer").options.map(item => item.value), ["", "F.Cu"]);
assert.equal(control("data-cursor").kind, "toggle");
assert.equal(resultsSnapshot.rows[0].cells[0], "Absolute voltage");

const manySamples = Array.from({ length: 100_005 }, (_, index) => ({ value: index, x_mm: index, y_mm: 0, layer: "F.Cu", source_id: `trace-${index}`, vertices_mm: [[index, 0, 0], [index, 1, 0], [index, 0, 1]] }));
const traceSnapshot = snapshots.buildDetachedTraceSnapshot({ ...result, scalar_fields: { ...result.scalar_fields, voltage_v: manySamples } }, "pi");
assert.equal(traceSnapshot.kind, "trace-plots");
assert.equal(traceSnapshot.trace.shownSamples, 100_000);
assert.equal(traceSnapshot.trace.result.scalar_fields.voltage_v.at(0).value, 0);
assert.equal(traceSnapshot.trace.result.scalar_fields.voltage_v.at(-1).value, 100_004);
assert.equal(traceSnapshot.trace.result.scalar_fields.voltage_v.at(0).source_id, "trace-0");
assert.equal(traceSnapshot.trace.result.scalar_fields.voltage_v.at(-1).source_id, "trace-100004");
assert.match(traceSnapshot.trace.notice, /100000 of 100005 field samples/);
const failedTrace = snapshots.buildDetachedTraceSnapshot({ ...result,
  summary: { solved: false, large_diagnostic: "x".repeat(100_000) },
  provenance: { solved: false, failure_stage: "physical_inductance_admission", numerical_quality: { inductance_passivity: { negative_mode_count: 5 } } },
}, "pi");
assert.equal(failedTrace.trace.result.status, "completed", "do not rewrite source status in display transport");
assert.deepEqual(failedTrace.trace.result.summary, { solved: false });
assert.deepEqual(failedTrace.trace.result.provenance, { solved: false, failure_stage: "physical_inductance_admission" });
const pdnTrace = snapshots.buildDetachedTraceSnapshot(result, "pi", { net: "VCC", target_ohm: .05 });
assert.equal(pdnTrace.trace.targetNet, "VCC");
assert.equal(pdnTrace.trace.targetOhm, .05);
assert.equal(snapshots.buildDetachedTraceSnapshot(result, "si", { net: "VCC", target_ohm: .05 }).trace.targetOhm, undefined);
const normalizedPdn = model.normalizeDetachedToolSnapshot(pdnTrace);
assert.equal(normalizedPdn.trace.targetNet, "VCC", "the target net survives detached-window transport");
assert.equal(normalizedPdn.trace.targetOhm, .05);
console.log("results tool snapshots: opaque IDs, formulas, capability controls and analytics passed");
