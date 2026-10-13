// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";

const appRoot = resolve(import.meta.dirname, "..");
const source = readFileSync(resolve(appRoot, "src", "MagneticMachineWorkbench.tsx"), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const nodeRequire = createRequire(import.meta.url);
const numericRange = await importTestTypescript("numericRange");
const loaded = { exports: {} };
new Function("require", "module", "exports", compiled)(name => {
  if (name === "react") return React;
  if (name === "react/jsx-runtime") return nodeRequire("react/jsx-runtime");
  if (name === "./PlotlyChart") return { default: () => React.createElement("div") };
  if (name === "./numericRange") return numericRange;
  if (name === "./workerBridge") return { isDesktopShell: () => false, runLocalWorker: async () => ({ ok: false }) };
  if (name.endsWith(".css")) return {};
  return nodeRequire(name);
}, loaded, loaded.exports);

const { defaultMagneticMachineRequest, validMagneticMachineResult, magneticMachineFieldTraces } = loaded.exports;
assert.equal(defaultMagneticMachineRequest("pm_rotor").remanence_t, 1);
assert.equal(defaultMagneticMachineRequest("solenoid").remanence_t, 0);
assert.equal(defaultMagneticMachineRequest("solenoid").motion, undefined);
assert.equal(defaultMagneticMachineRequest("solenoid").transient, undefined);
const field = {
  nodes_m: [[0, 0], [1, 0], [0, 1]], triangles: [[0, 1, 2]],
  element_b_t: [[0.2, 0.1]], element_h_a_per_m: [[20, 10]], potential_a_wb_per_m: [0, 0.1, 0.2],
};
const thermalFrame = {
  time_s: 0, potential_a_wb_per_m: [0, 0.1, 0.2], temperature_k: [300, 301, 302],
  element_b_t: [[0.2, 0.1]], element_joule_loss_w: [0.5], joule_loss_w: 0.5, max_temperature_k: 302,
};
const result = {
  contract: "spike/magnetic-machine-study-result/v1", model: "pm_rotor", model_status: "experimental",
  summary: { max_b_t: 0.224, magnetic_energy_j: -0.01, force_x_n: 1, force_y_n: 2, torque_n_m: 3 },
  summary_state: "final_stationary_transient", field_time_s: 0,
  steady_reference_summary: { max_b_t: 0.2, magnetic_energy_j: -0.02, force_x_n: 0.5, force_y_n: 1, torque_n_m: 1.5 },
  final_stress: { force_x_n: 4, force_y_n: 5, torque_n_m: -6 },
  stress_contour_m: [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2], [0.1, 0.1]], field,
  coupled: { contract: "spike/planar-magnetic-thermal-result/v1", model_status: "experimental", history: [thermalFrame],
    final_thermal_result: { temperature_k: [300, 301, 302], element_mean_temperature_k: [301] } },
};

assert.equal(validMagneticMachineResult(result, "pm_rotor"), true);
assert.equal(validMagneticMachineResult({ ...result, final_stress: { ...result.final_stress, force_x_n: Infinity } }, "pm_rotor"), false, "final stress must be finite");
assert.equal(validMagneticMachineResult({ ...result, field: { ...field, element_b_t: [[0.2, NaN]] } }, "pm_rotor"), false, "field vectors must be finite");
assert.equal(validMagneticMachineResult({ ...result, coupled: { ...result.coupled, history: [{ ...thermalFrame, temperature_k: [300, 301] }] } }, "pm_rotor"), false, "thermal nodes must match the field mesh");
assert.equal(validMagneticMachineResult({ ...result, coupled: { ...result.coupled, history: [{ ...thermalFrame, joule_loss_w: NaN }] } }, "pm_rotor"), false, "coupled scalar histories must be finite");
assert.equal(validMagneticMachineResult({ ...result, field_time_s: NaN }, "pm_rotor"), false, "final transient field time must be finite");
assert.equal(validMagneticMachineResult({ ...result, summary_state: "initial_guess" }, "pm_rotor"), false, "unknown summary-state claims must be rejected");
assert.equal(validMagneticMachineResult({ ...result, steady_reference_summary: { ...result.steady_reference_summary, magnetic_energy_j: Infinity } }, "pm_rotor"), false, "steady reference summaries must remain finite");

const traces = magneticMachineFieldTraces(result, "b");
const force = traces.find(trace => String(trace.name).includes("force direction"));
const torque = traces.find(trace => String(trace.name).includes("torque direction"));
assert.match(force.name, /^Final force direction \(normalized display arrow\)$/);
assert.deepEqual(force.customdata[0], [4, 5, Math.hypot(4, 5)], "force tooltip data must use final stress values");
assert.match(force.hovertemplate, /Fx=.*N.*Fy=.*N.*\|F\|=.*N/s);
assert.match(torque.name, /^Final torque direction \(normalized display circle\)$/);
assert.ok(torque.customdata.every(value => value === -6), "torque tooltip data must use final torque");
assert.match(torque.hovertemplate, /N·m.*Normalized direction display about origin/s);
assert.ok(traces.some(trace => trace.name === "Returned stress contour"), "the solver-provided stress contour must be plotted");

const elementCount = 4001;
const largeField = { ...field, triangles: Array.from({ length: elementCount }, () => [0, 1, 2]),
  element_b_t: Array.from({ length: elementCount }, () => [0.2, 0.1]), element_h_a_per_m: Array.from({ length: elementCount }, () => [20, 10]) };
const largeTraces = magneticMachineFieldTraces({ ...result, field: largeField, coupled: undefined, summary_state: undefined,
  steady_reference_summary: undefined, field_time_s: undefined }, "b");
assert.equal(largeTraces.find(trace => trace.name === "|B| (T)").x.length, elementCount, "all returned scalar element samples must remain plotted");
const largeVectors = largeTraces.find(trace => String(trace.name).startsWith("B direction"));
assert.match(largeVectors.name, /of 4001 elements; uniform stride/);
assert.ok(largeVectors.x.length / 3 <= 2000, "vector glyph lines must be capped at 2,000 uniformly strided elements");

const fallback = magneticMachineFieldTraces({ ...result, final_stress: undefined, coupled: undefined }, "b");
assert.match(fallback.find(trace => String(trace.name).includes("force direction")).name, /^Initial force direction/);
assert.deepEqual(fallback.find(trace => String(trace.name).includes("force direction")).customdata[0], [1, 2, Math.hypot(1, 2)]);
assert.match(source, /Magnetic constitutive potential/);
assert.match(source, /not a total stored-energy claim/);
assert.match(source, /Advanced request JSON/);
assert.match(source, /Mesh edge \(m\)/);
assert.match(source, /Current density \(A\/m²\)/);
assert.match(source, /uniformly strided subset capped at 2,000 elements/);

console.log("magnetic machine result admission and physical overlay tests passed");
