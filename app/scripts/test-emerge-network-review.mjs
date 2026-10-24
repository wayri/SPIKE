// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";

async function load(path) {
  const bundled = await build({ entryPoints: [fileURLToPath(new URL(path, import.meta.url))], bundle: true, write: false, format: "esm", platform: "node" });
  return import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].contents).toString("base64")}`);
}
const { reviewEMergeNetwork, emergeNetworkReportHtml } = await load("../src/emergeNetworkReview.ts");
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const invokeFlow = appSource.slice(appSource.indexOf("  const invokeExtension ="), appSource.indexOf("  const openEmiEmerge ="));
assert.match(invokeFlow, /preview_radiation: contributionId === "emerge-radiation"/);
assert.match(invokeFlow, /crypto\.subtle\.digest\("SHA-256", new TextEncoder\(\)\.encode\(preview\.script\)\)/);
assert.match(invokeFlow, /scriptDigest !== preview\.script_sha256/);
assert.ok(invokeFlow.indexOf("expected_generated_script_sha256: scriptDigest") < invokeFlow.indexOf("contribution_id: contributionId, context"));
assert.match(invokeFlow, /!preparingEMerge\) setExtensionResult/);
assert.match(invokeFlow, /const previewGeneration = emergePreviewGenerationRef\.current/);
assert.ok((invokeFlow.match(/previewGeneration !== emergePreviewGenerationRef\.current/g) ?? []).length >= 3);
assert.ok(invokeFlow.indexOf("previewGeneration !== emergePreviewGenerationRef.current") < invokeFlow.indexOf("setEmergeScriptPreview(preview)"));
assert.match(appSource, /id === "emerge-preview"\) parameters\.preview_radiation = emergePreviewStudy === "radiation"/);
const network = { frequencies_hz: [1e8, 2e8, 3e8, 4e8], ports: ["P1", "P2"], reference_impedance_ohm: 50,
  values: [.5, .2, .1, .8].map(reflection => [[[reflection, 0], [.7, 0]], [[.8, 0], [.4, 0]]]) };
const payload = { analysis_id: "test", status: "completed", model_status: "unvalidated", summary: {},
  provenance: { board_case_sha256: "testdigest" }, networks: { s_parameters: network }, issues: [] };
const envelope = { data: { analysis_result: payload } };
const { exportEMergeNetwork } = await load("../src/emergeSampleExport.ts");
const touchstone = exportEMergeNetwork(envelope, "touchstone");
assert.equal(touchstone.name, "emerge-network.s2p");
assert.match(touchstone.text, /# Hz S RI R 50/);
assert.equal(touchstone.text.split("\n")[2], "100000000 0.5 0 0.8 0 0.7 0 0.4 0");
assert.match(exportEMergeNetwork(envelope, "csv").text, /100000000,"P2","P1",0.8,0/);
assert.throws(() => exportEMergeNetwork({ ...payload, status: "failed" }, "csv"), /No completed solved/);
assert.throws(() => exportEMergeNetwork({ ...payload, networks: { s_parameters: { ...network, reference_impedance_ohm: undefined } } }, "touchstone"), /reference impedance/);
const { admitEMergeFieldPlanes } = await load("../src/emergeNearFieldSamples.ts");
const fieldPlane = { frequency_hz: 1e9, grid_shape: [3, 3], coordinates_mm: Array.from({ length: 9 }, (_, i) => [i % 3, Math.floor(i / 3), 2]), valid: Array(9).fill(true), e_v_m: Array.from({ length: 9 }, () => [[1, 0], [0, 0], [0, 0]]), h_a_m: Array.from({ length: 9 }, () => [[0, 0], [1, 0], [0, 0]]) };
const planeData = { contract: "spike/emerge-nearfield-plane/v1", frequencies_hz: [1e9], planes: [fieldPlane] };
assert.equal(admitEMergeFieldPlanes(planeData).length, 1);
const withHole = { ...fieldPlane, valid: [false, ...fieldPlane.valid.slice(1)], e_v_m: [null, ...fieldPlane.e_v_m.slice(1)], h_a_m: [null, ...fieldPlane.h_a_m.slice(1)] };
assert.equal(admitEMergeFieldPlanes({ ...planeData, planes: [withHole] }).length, 1);
assert.equal(admitEMergeFieldPlanes({ ...planeData, planes: [{ ...withHole, e_v_m: fieldPlane.e_v_m }] }).length, 0);
assert.equal(admitEMergeFieldPlanes({ ...planeData, planes: [{ ...fieldPlane, grid_shape: [3, 4] }] }).length, 0);
assert.equal(admitEMergeFieldPlanes({ ...planeData, planes: [{ ...fieldPlane, e_v_m: [[[NaN, 0], [0, 0], [0, 0]], ...fieldPlane.e_v_m.slice(1)] }] }).length, 0);
const swapped = fieldPlane.coordinates_mm.map(point => [...point]);
[swapped[0], swapped[8]] = [swapped[8], swapped[0]];
assert.equal(admitEMergeFieldPlanes({ ...planeData, planes: [{ ...fieldPlane, coordinates_mm: swapped }] }).length, 0);
assert.equal(admitEMergeFieldPlanes({ ...planeData, frequencies_hz: [2e9] }).length, 0);
assert.equal(admitEMergeFieldPlanes({ ...planeData, planes: [{ ...fieldPlane, coordinates_mm: fieldPlane.coordinates_mm.map((point, i) => i ? point : [0, 0, 3]) }] }).length, 0);
assert.equal(admitEMergeFieldPlanes({ ...planeData, frequencies_hz: [1e9, 2e9], planes: [fieldPlane, { ...fieldPlane, frequency_hz: 2e9, grid_shape: [3, 4] }] }).length, 0);
const review = reviewEMergeNetwork(envelope);
assert.equal(review.issue, null);
assert.equal(review.ports[0].bestMatchHz, 3e8);
assert.ok(Math.abs(review.ports[0].returnLossDb - 20) < 1e-12);
assert.ok(Math.abs(review.ports[0].vswr - 11 / 9) < 1e-12);
assert.deepEqual(review.ports[0].matchedSampleSpansHz, [[2e8, 3e8]]);
assert.deepEqual(review.ports[1].matchedSampleSpansHz, []);
assert.equal(review.transmissions.length, 2);
assert.ok(Math.abs(review.transmissions[0].maximumDb - 20 * Math.log10(.7)) < 1e-12);
for (const change of [{ status: "failed" }, { model_status: "unsupported" }, { provenance: { solved: false } }]) {
  assert.equal(reviewEMergeNetwork({ ...payload, ...change }).ports.length, 0);
}
for (const change of [{ frequencies_hz: [1e8, NaN, 3e8, 4e8] }, { frequencies_hz: [2e8, 1e8, 3e8, 4e8] },
  { values: [[[[.1, 0]]]] }, { ports: ["P1", "P1"] }]) {
  assert.equal(reviewEMergeNetwork({ ...payload, networks: { s_parameters: { ...network, ...change } } }).ports.length, 0);
}
const zero = reviewEMergeNetwork({ ...payload, networks: { s_parameters: { frequencies_hz: [1e8, 2e8], ports: ["zero"], values: [[[[0, 0]]], [[[2, 0]]]] } } });
assert.equal(zero.ports[0].returnLossDb, null);
assert.equal(zero.ports[0].vswr, 1);
assert.deepEqual(zero.ports[0].matchedSampleSpansHz, [[1e8, 1e8]]);
const text = emergeNetworkReportHtml({ ...payload, issues: [{ message: '<script>alert("x")</script>' }] });
assert.match(text, /Model status: unvalidated/);
assert.match(text, /testdigest/);
assert.match(text, /&lt;script&gt;/);
assert.doesNotMatch(text, /<script>/);
assert.match(text, /not interpolated bandwidth/);
const fieldReport = emergeNetworkReportHtml({ ...payload, summary: { setup: { nearfield_enabled: true, field_excited_port: 2 } }, fields: { nearfield: { ...planeData, planes: [withHole] } } });
assert.match(fieldReport, /8 \/ 9/);
assert.match(fieldReport, /Input-power calibration/);
assert.match(fieldReport, /field excited port/);

const { suggestEMergePadPairs } = await load("../src/emergeSetupSuggestions.ts");
const pad = (id, net, layer, x = 1, extra = {}) => ({ id, net, at: [x, 2], drill: 0, layers: [layer], shape: "rect", ...extra });
const pads = [pad("signal", "RF", "In1.Cu"), pad("ground", "GND", "B.Cu"), pad("bad", "GND", "F.Cu"),
  pad("drilled", "GND", "B.Cu", 1, { drill: .4 }), pad("offset", "GND", "B.Cu", 1.01)];
assert.deepEqual(suggestEMergePadPairs(pads, "RF", "GND", ["F.Cu", "In1.Cu", "B.Cu"]), [{ signalId: "signal", returnId: "ground", signalLayer: "In1.Cu", returnLayer: "B.Cu" }]);
assert.deepEqual(suggestEMergePadPairs(pads, "GND", "GND"), []);
assert.deepEqual(suggestEMergePadPairs(pads, "RF", "GND", ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]), []);
assert.deepEqual(suggestEMergePadPairs([], "RF", "GND"), []);
const { buildEngineeringReport } = await load("../src/engineeringReport.ts");
const { normalizeSolverResult } = await load("../src/analysisResults.ts");
const reportPayload = { ...payload, contract: "spike/v1", mode: "si", fields: {}, summary: {
  engine: "EMerge", engine_version: "test-version", geometry_backend: "emcad", geometry_backend_version: "test-emcad",
  copper_layers: [{name: "In1.Cu", z_mm: -.2}], dielectric_layers: [{name: "Core fixture", thickness_mm: .4, epsilon_r: 4.2, loss_tangent: .01, z_top_mm: -.2, z_bottom_mm: -.6}],
  setup: {frequency_start_hz: 1e8, frequency_stop_hz: 4e8, frequency_points: 4, mesh_resolution_mm: .5,
    ports: [{signal_pad_id: "source-pad", signal_layer: "In1.Cu", return_pad_id: "ground-pad", return_layer: "In2.Cu", width_mm: .3, reference_impedance_ohm: 50}]}
} };
const reportInput = { projectName: "EMerge fixture", boardFile: "fixture.spike-design.json", analysisMode: "SI", domain: "si", board: null,
  result: normalizeSolverResult(reportPayload), emerge: { data: { analysis_result: reportPayload } },
  setup: { net: "RF", sources: [], loads: [], returnPath: { mode: "explicit", net: "GND" }, meshDimension: "3d", meshTargetMm: ".5", zoneCellMm: "1", viaModel: "ignore", viaPlatingMm: ".02", frequencyStart: "1e8", frequencyStop: "4e8", frequencyPoints: "4" },
  limits: { drop: "10", density: "1" }, probes: [], fusingSettings: { ambientTemperatureC: 25, faultDurationS: 1 }, modelAssignmentCount: 0, projectPayload: {} };
const report = buildEngineeringReport(reportInput);
assert.match(report, /id="emerge-network-review"/);
assert.match(report, /"emerge_network_review":/);
assert.match(report, /"values":/);
assert.match(report, /Dielectric materials/);
assert.match(report, /Core fixture/);
assert.match(report, /source-pad/);
assert.match(report, /test-emcad/);
const mismatched = buildEngineeringReport({ ...reportInput, emerge: { ...reportPayload, analysis_id: "another-run" } });
assert.doesNotMatch(mismatched, /id="emerge-network-review"/);
assert.match(mismatched, /"emerge_network_review":null/);
const rendered = await build({ stdin: { contents: `import React from "react"; import { renderToStaticMarkup } from "react-dom/server";
  import { EMergeSetupForm, defaultEMergeSetup, emergeParameters } from "./src/EMergeExtension.tsx";
  export const render = (pads, order, enabled = false) => renderToStaticMarkup(React.createElement(EMergeSetupForm, {
    value: {...defaultEMergeSetup("RF"), radome_enabled: enabled}, onChange: () => {}, boardPads: pads, copperLayerOrder: order,
    boardBounds: {minX: 0, minY: 0, maxX: 30, maxY: 20}
  })); export { defaultEMergeSetup, emergeParameters };`, resolveDir: fileURLToPath(new URL("..", import.meta.url)), loader: "tsx" },
  bundle: true, write: false, format: "esm", platform: "node", loader: { ".css": "empty" },
  banner: { js: `import {createRequire as testCreateRequire} from "node:module"; const require = testCreateRequire(process.cwd() + "/package.json");` } });
const form = await import(`data:text/javascript;base64,${Buffer.from(rendered.outputFiles[0].contents).toString("base64")}`);
const emptyForm = form.render([], []);
assert.match(emptyForm, /No exact-centre pair found/);
assert.match(emptyForm, /disabled=""/);
const suggestedForm = form.render(pads, ["F.Cu", "In1.Cu", "B.Cu"], true);
assert.match(suggestedForm, /signal \(In1.Cu\)/);
assert.match(suggestedForm, /Gap above top copper/);
assert.match(suggestedForm, /requires installed emcad/);
assert.throws(() => form.emergeParameters({ ...form.defaultEMergeSetup("RF"), geometry_backend: "invalid" }), /supported geometry/);
console.log("EMerge sampled network review and pad suggestions passed");
