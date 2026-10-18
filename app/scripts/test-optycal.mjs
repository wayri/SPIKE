// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const bundle = await build({ entryPoints: [fileURLToPath(new URL("../src/optycalStudy.ts", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node" });
const { admitOptycalSource, defaultOptycalSetup, optycalParameters } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].contents).toString("base64")}`);
const pattern = { frequency_hz: 1e9, theta_deg: [0, 90, 180], phi_deg: [0, 120, 240, 360], e_theta_v_m: Array.from({ length: 12 }, () => [1, 0]), e_phi_v_m: Array.from({ length: 12 }, () => [0, 0]) };
const radiation = { contract: "spike/emerge-radiation-cuts/v1", frequencies_hz: [1e9], patterns_3d: [pattern], excitation_port: "P1", excitation_ports: ["P1", "P2"], excitation_coefficients: [[1, 0], [0, 0]] };
const provenance = { solver: "EMerge/3.0.0a19", extension_id: "spike.emerge-suite", design_id: "test-board", design_digest_sha256: "a".repeat(64), board_case_sha256: "b".repeat(64), generated_script_sha256: "c".repeat(64) };
const source = { contract: "spike/v1", status: "completed", model_status: "unvalidated", analysis_id: "source", provenance, fields: { radiation } };
assert.equal(admitOptycalSource({ data: { analysis_result: source } }).port, "P1");
assert.equal(admitOptycalSource({ ...source, status: "failed" }), null);
assert.equal(admitOptycalSource({ ...source, provenance: { ...provenance, solver: "Optycal/0.0.6" } }), null);
assert.equal(admitOptycalSource({ ...source, provenance: { ...provenance, design_digest_sha256: "bad" } }), null);
for (const patch of [{ excitation_port: undefined }, { excitation_coefficients: [[1, 0], [1, 0]] }, { frequencies_hz: [2e9] }, { patterns_3d: [{ ...pattern, phi_deg: [0, 120, 120, 360] }] }, { patterns_3d: [{ ...pattern, e_theta_v_m: [[Infinity, 0], ...pattern.e_theta_v_m.slice(1)] }] }, { patterns_3d: [{ ...pattern, e_phi_v_m: [] }] }]) {
  assert.equal(admitOptycalSource({ ...source, fields: { radiation: { ...radiation, ...patch } } }), null);
}
const setup = { ...defaultOptycalSetup(), step_path: "C:/models/platform.step", source_phase_acknowledged: true };
assert.equal(optycalParameters(setup, source).frequency_hz, 1e9);
assert.deepEqual(optycalParameters(setup, source).structure_translation_mm, [0, 0, 1000]);
assert.equal(optycalParameters(setup, source).source_phase_assumption, "emerge_farfield_coefficient_e_plus_jwt");
assert.throws(() => optycalParameters({ ...setup, source_phase_acknowledged: false }, source), /Acknowledge/);
assert.throws(() => optycalParameters({ ...setup, frequency_hz: "2e9" }, source), /actually solved/);
assert.throws(() => optycalParameters({ ...setup, antenna_aperture_mm: "" }, source), /Largest antenna/);
assert.throws(() => optycalParameters({ ...setup, theta_step_deg: "7" }, source), /Angular steps/);
assert.throws(() => optycalParameters({ ...setup, structure_rotation_deg: ["0", "0", "Infinity"] }, source), /rotation Z/);
const uiBundle = await build({ entryPoints: [fileURLToPath(new URL("../src/OptycalExtension.tsx", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node", loader: { ".css": "empty" }, external: ["react", "react-dom", "react-dom/server", "lucide-react", "plotly.js-dist-min"] });
// A local file module keeps React resolution bound to this package.
const { writeFileSync, unlinkSync } = await import("node:fs");
const uiFile = new URL("../.optycal-test-ui.mjs", import.meta.url);
writeFileSync(uiFile, uiBundle.outputFiles[0].contents);
try {
  const { OptycalSetupForm, OptycalResultPlot, admitOptycalComparison } = await import(uiFile.href);
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const html = renderToStaticMarkup(createElement(OptycalSetupForm, { value: setup, sourceResult: source, onChange() {} }));
  assert.match(html, /Perfect electric conductor/);
  assert.match(html, /excited port P1/);
  assert.match(html, /does not update antenna input matching/);
  assert.match(html, /Largest antenna physical extent/);
  const comparison = { contract: "spike/optycal-pattern-comparison/v1", frequency_hz: 1e9, theta_deg: pattern.theta_deg, phi_deg: pattern.phi_deg, bare_relative_db: Array(12).fill(0), structure_relative_db: Array(12).fill(6), delta_db: Array(12).fill(6), interference_cross_term: Array(12).fill(2), direct_e_xyz: Array.from({ length: 12 }, () => [[1, 0], [0, 0], [0, 0]]), scattered_e_xyz: Array.from({ length: 12 }, () => [[1, 0], [0, 0], [0, 0]]), total_e_xyz: Array.from({ length: 12 }, () => [[2, 0], [0, 0], [0, 0]]) };
  assert.ok(admitOptycalComparison(comparison));
  assert.equal(admitOptycalComparison({ ...comparison, total_e_xyz: comparison.total_e_xyz.slice(1) }), null);
  assert.equal(admitOptycalComparison({ ...comparison, delta_db: [NaN, ...comparison.delta_db.slice(1)] }), null);
  const result = { data: { analysis_result: { status: "completed", model_status: "approximate", fields: { comparison } } } };
  const resultHtml = renderToStaticMarkup(createElement(OptycalResultPlot, { result }));
  assert.match(resultHtml, /same bare-field peak reference/);
  assert.match(resultHtml, /Coherent interference cross term/);
  assert.match(resultHtml, /Field component/);
  assert.match(resultHtml, /undefined at zero/);
  assert.match(resultHtml, /Download HTML report/);
  const reportBundle = await build({ entryPoints: [fileURLToPath(new URL("../src/optycalReport.ts", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node" });
  const { optycalReportHtml } = await import(`data:text/javascript;base64,${Buffer.from(reportBundle.outputFiles[0].contents).toString("base64")}`);
  const evidence = { ...result.data.analysis_result, analysis_id: "actual-comparison", summary: { mesh_size_mm: 25 }, provenance: { solver: "Optycal/0.0.6", source_result_sha256: "e".repeat(64), structure_path: "<script>bad()</script>" } };
  const reportHtml = optycalReportHtml(evidence);
  assert.match(reportHtml, /same bare-field peak reference/);
  assert.match(reportHtml, /Coherent interference angular map/);
  assert.match(reportHtml, /structure_relative_db/);
  assert.match(reportHtml, new RegExp("e".repeat(64)));
  assert.match(reportHtml, /&lt;script&gt;bad\(\)&lt;\/script&gt;/);
  assert.doesNotMatch(reportHtml, /<script>bad|<script src=|Infinity|NaN/);
  assert.throws(() => optycalReportHtml({ ...evidence, status: "failed" }), /No completed/);
  assert.throws(() => optycalReportHtml({ ...evidence, fields: { comparison: { ...comparison, total_e_xyz: [] } } }), /finite complex/);
  assert.equal(renderToStaticMarkup(createElement(OptycalResultPlot, { result: { data: { analysis_result: { ...result.data.analysis_result, status: "failed" } } } })), "");
} finally { unlinkSync(uiFile); }
console.log("Optycal source, setup, result admission and GUI checks passed.");
