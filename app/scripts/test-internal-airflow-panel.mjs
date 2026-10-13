// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";

const appRoot = resolve(import.meta.dirname, "..");
const source = readFileSync(resolve(appRoot, "src", "InternalAirflowPanel.tsx"), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const nodeRequire = createRequire(import.meta.url);
const numericRange = await importTestTypescript("numericRange");

function loadModule(reactDependency, worker) {
  const loaded = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => {
    if (name === "react") return reactDependency;
    if (name === "react/jsx-runtime") return nodeRequire("react/jsx-runtime");
    if (name === "./numericRange") return numericRange;
    if (name === "./workerBridge") return { runLocalWorker: worker };
    if (name === "./InternalAirflowPanel.css") return {};
    return nodeRequire(name);
  }, loaded, loaded.exports);
  return loaded.exports;
}

const staticModule = loadModule(React, async () => { throw new Error("not used by static render"); });
const InternalAirflowPanel = staticModule.default;
const draft = {
  length_m: "0.12", gap_m: "0.008", width_m: "0.04", mean_velocity_m_s: "0.35",
  inlet_temperature_k: "298.15", density_kg_m3: "1.184", viscosity_pa_s: "1.85e-5",
  conductivity_w_mk: "0.0262", specific_heat_j_kgk: "1007",
  lower_wall_heat_flux_w_m2: "500", upper_wall_heat_flux_w_m2: "0", axial_cells: "2", transverse_cells: "3",
};
const request = staticModule.buildInternalAirflowRequest(draft);
const resultFor = (solvedRequest, pressureDrop = 0.46) => {
  const nx = solvedRequest.mesh.axial_cells;
  const ny = solvedRequest.mesh.transverse_cells;
  const x = Array.from({ length: nx }, (_, index) => solvedRequest.geometry.length_m * (index + 1) / nx);
  const y = Array.from({ length: ny }, (_, index) => solvedRequest.geometry.gap_m * (index + 0.5) / ny);
  return {
  contract: "spike/internal-channel-airflow-result/v1",
  status: "experimental", model_status: "experimental", production_qualified: false,
  flow_regime: "laminar_prescribed", turbulence_model: "none",
  request_digest: "a".repeat(64), result_digest: "b".repeat(64), request_snapshot: structuredClone(solvedRequest), units: "SI",
  field_location: "downstream_axial_station_by_transverse_cell", inlet_temperature_k: solvedRequest.operating.inlet_temperature_k,
  x_m: x, y_m: y,
  velocity_u_m_s: y.map((_, index) => 0.2 + 0.3 * Math.sin(Math.PI * (index + 0.5) / ny)),
  temperature_k: x.map((_, xi) => y.map((__, yi) => 298.4 + xi / nx + yi / ny)),
  bulk_temperature_k: x.map((_, index) => 298.5 + index / nx),
  wall_temperature_k: { lower: x.map((_, index) => 302 + index / nx), upper: x.map((_, index) => 298.3 + index / nx) },
  reynolds_hydraulic: 298.7, peclet_length: 191_800,
  mass_flow_kg_s: 0.000132608, pressure_drop_pa: pressureDrop,
  heat_balance: { wall_input_w: 2.4, coolant_enthalpy_gain_w: 2.3999998, imbalance_w: 2e-7, relative_imbalance: 8.33e-8, acceptance_tolerance_w: 2.4e-6 },
  diagnostics: { maximum_equation_residual_w: 3e-10, maximum_mass_imbalance_kg_s: 0, omitted_viscous_heating_rise_k: 4e-7,
    mesh_convergence_verified: false, axial_scheme: "first_order_upwind", transverse_scheme: "centered_finite_volume" },
  resources: { axial_cells: nx, transverse_cells: ny, field_values: nx * ny, maximum_field_values: 100_000 },
  limitations: ["Steady, incompressible, constant-property screening model.", "No turbulence model is solved."],
  };
};
const result = resultFor(request);

assert.deepEqual(request.geometry, { length_m: 0.12, gap_m: 0.008, span_m: 0.04 });
assert.deepEqual(request.operating, { mean_velocity_m_s: 0.35, inlet_temperature_k: 298.15, lower_wall_heat_flux_w_m2: 500, upper_wall_heat_flux_w_m2: 0 });
assert.deepEqual(request.mesh, { axial_cells: 2, transverse_cells: 3 });
assert.throws(() => staticModule.buildInternalAirflowRequest({ ...draft, axial_cells: "2.5" }), /Mesh budget/);
assert.equal(staticModule.validInternalAirflowResult(result, request), true);
assert.equal(staticModule.validInternalAirflowResult(result, { ...request, fluid: { ...request.fluid, density_kg_m3: 2 } }), false, "saved fields must bind all fluid inputs");
assert.equal(staticModule.validInternalAirflowResult(result, { ...request, operating: { ...request.operating, lower_wall_heat_flux_w_m2: 100 } }), false, "saved fields must bind wall loading");
assert.equal(staticModule.validInternalAirflowResult({ ...result, temperature_k: [[299], [300]] }, request), false, "field shape must match returned coordinates");
assert.equal(staticModule.validInternalAirflowResult({ ...result, turbulence_model: "k-epsilon" }, request), false, "the UI must reject an unsupported turbulence claim");
assert.equal(staticModule.validInternalAirflowResult({ ...result, production_qualified: true }, request), false, "the UI must not promote experimental output");

const completeMarkup = renderToStaticMarkup(React.createElement(InternalAirflowPanel, { workerAvailable: true, initialRequest: request, initialResult: result }));
assert.match(completeMarkup, /Internal channel airflow/);
assert.match(completeMarkup, /Laminar prescribed flow · turbulence model: none/);
assert.match(completeMarkup, /does not solve a solid domain, turbulence, flow separation, fans, or enclosure-scale CFD/);
assert.match(completeMarkup, /Temperature \(K\)/);
assert.match(completeMarkup, /Mass flow/);
assert.match(completeMarkup, /Heat imbalance/);
assert.match(completeMarkup, /Max equation residual/);
assert.match(completeMarkup, /within/);
assert.match(completeMarkup, /Steady, incompressible, constant-property screening model/);
assert.match(completeMarkup, /aria-label="Channel width \(m\)"/);
assert.match(completeMarkup, /Both wall heat fluxes are signed/);
assert.match(completeMarkup, /Mesh convergence/);
assert.doesNotMatch(renderToStaticMarkup(React.createElement(InternalAirflowPanel, { workerAvailable: true })), /internal-airflow-velocity-arrow/, "the browser must not synthesize a field before a solver result");
const unavailableMarkup = renderToStaticMarkup(React.createElement(InternalAirflowPanel, { workerAvailable: false }));
assert.match(unavailableMarkup, /Local solver worker unavailable/);
assert.match(unavailableMarkup, /<button[^>]*disabled=""[^>]*>Run channel screen<\/button>/);

const states = [];
const refs = [];
let stateCursor = 0;
let refCursor = 0;
const pending = [];
const statuses = [];
const hookReact = {
  useEffect() {},
  useRef(initial) {
    const index = refCursor++;
    if (!(index in refs)) refs[index] = { current: initial };
    return refs[index];
  },
  useState(initial) {
    const index = stateCursor++;
    if (!(index in states)) states[index] = typeof initial === "function" ? initial() : initial;
    return [states[index], value => { states[index] = typeof value === "function" ? value(states[index]) : value; }];
  },
};
const worker = value => new Promise(resolvePromise => pending.push({ request: value, resolve: resolvePromise }));
const interactive = loadModule(hookReact, worker).default;
const mount = (workerAvailable = true) => {
  stateCursor = 0; refCursor = 0;
  return interactive({ workerAvailable, onStatus: message => statuses.push(message) });
};
function findNode(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) {
    const found = findNode(child, predicate);
    if (found) return found;
  }
  return null;
}
const flush = async () => { await new Promise(resolvePromise => setImmediate(resolvePromise)); await new Promise(resolvePromise => setImmediate(resolvePromise)); };

const firstRun = findNode(mount(), node => node.type === "button" && node.props.children === "Run channel screen");
firstRun.props.onClick();
assert.equal(pending.length, 1);
assert.equal(pending[0].request.method, "run_internal_airflow");
assert.equal(pending[0].request.params.request.contract, "spike/internal-channel-airflow-request/v1");
assert.equal(pending[0].request.params.request.geometry.span_m, 0.04);
assert.equal(pending[0].request.params.request.operating.upper_wall_heat_flux_w_m2, 0);
assert.deepEqual(pending[0].request.params.request.mesh, { axial_cells: 64, transverse_cells: 17 });
assert.equal(findNode(mount(), node => node.type === "button" && String(node.props.children).includes("Running channel")).props.disabled, true);
assert.equal(findNode(mount(), node => node.type === "input" && node.props["aria-label"] === "Channel length (m)").props.disabled, true);

// Invoke the handler a second time to model a superseding request. Resolving the
// older request last must not replace the accepted result or surface its error.
findNode(mount(), node => node.type === "button" && String(node.props.children).includes("Running channel")).props.onClick();
assert.equal(pending.length, 2);
const newerResult = resultFor(pending[1].request.params.request, 0.5);
pending[1].resolve({ ok: true, result: newerResult });
await flush();
pending[0].resolve({ ok: false, error: "late obsolete failure" });
await flush();
let markup = renderToStaticMarkup(mount());
assert.match(markup, /0\.5 Pa/);
assert.doesNotMatch(markup, /late obsolete failure/);

// A current failure preserves the prior valid output; a later valid run clears
// the error and replaces it, demonstrating recovery without fabricated fields.
findNode(mount(), node => node.type === "button" && node.props.children === "Run channel screen").props.onClick();
pending[2].resolve({ ok: false, error: "solver unavailable for test" });
await flush();
markup = renderToStaticMarkup(mount());
assert.match(markup, /solver unavailable for test/);
assert.match(markup, /last valid result remains visible/);
assert.match(markup, /0\.5 Pa/);
findNode(mount(), node => node.type === "button" && node.props.children === "Run channel screen").props.onClick();
pending[3].resolve({ ok: true, result: resultFor(pending[3].request.params.request, 0.62) });
await flush();
markup = renderToStaticMarkup(mount());
assert.match(markup, /0\.62 Pa/);
assert.doesNotMatch(markup, /solver unavailable for test/);
assert.ok(statuses.some(message => message.includes("completed")));

const lengthControl = findNode(mount(), node => node.type === "input" && node.props["aria-label"] === "Channel length (m)");
lengthControl.props.onChange({ target: { value: "0.2" } });
assert.match(renderToStaticMarkup(mount()), /Inputs differ from the solved setup/);
lengthControl.props.onChange({ target: { value: "0.12" } });
states[5] = "velocity";
markup = renderToStaticMarkup(mount());
assert.match(markup, /internal-airflow-velocity-arrow/);
assert.match(markup, /Axial velocity arrows from returned transverse cell averages/);

console.log("internal airflow panel request, result admission, lifecycle, and visualization tests passed");
