// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const appRoot = resolve(import.meta.dirname, "..");
const source = readFileSync(resolve(appRoot, "src", "SmpsConverterPanel.tsx"), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const nodeRequire = createRequire(import.meta.url);

function loadModule(reactDependency, worker) {
  const loaded = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => {
    if (name === "react") return reactDependency;
    if (name === "react/jsx-runtime") return nodeRequire("react/jsx-runtime");
    if (name === "./workerBridge") return { runLocalWorker: worker };
    if (name === "./SmpsConverterPanel.css") return {};
    return nodeRequire(name);
  }, loaded, loaded.exports);
  return loaded.exports;
}

const components = [
  { occurrenceId: "board-main", reference: "Q1", label: "High-side MOSFET" },
  { occurrenceId: "board-main", reference: "Q2", label: "Low-side MOSFET" },
  { occurrenceId: "board-main", reference: "L1", label: "Power inductor" },
  { occurrenceId: "daughter-a", reference: "Q1", label: "Unrelated MOSFET" },
];
const staticModule = loadModule(React, async () => { throw new Error("not used by static render"); });

const boardDraft = staticModule.createSyntheticSmpsDraft(components);
assert.throws(() => staticModule.buildSmpsConverterRequest(boardDraft, components), /requires an occurrence and component reference/, "demo values must not silently bind loaded-board parts");
boardDraft.switches[0].devices[0] = { occurrence_id: "board-main", component_ref: "Q1" };
boardDraft.switches[1].devices[0] = { occurrence_id: "board-main", component_ref: "Q2" };
boardDraft.inductor.occurrence_id = "board-main";
boardDraft.inductor.component_ref = "L1";
const request = staticModule.buildSmpsConverterRequest(boardDraft, components);
assert.equal(request.contract, "spike/smps-converter-request/v1");
assert.equal(request.switches[0].rds_on_ohm, 0.015);
assert.deepEqual(request.switches.map(group => group.devices[0].component_ref), ["Q1", "Q2"]);
assert.equal(request.inductor.inductance_h, 1e-5);

const backendScript = [
  "import importlib.util, json, sys",
  "spec = importlib.util.spec_from_file_location('spike_smps_converter', 'python/spike_core/smps_converter.py')",
  "module = importlib.util.module_from_spec(spec)",
  "spec.loader.exec_module(module)",
  "print(json.dumps(module.evaluate_smps_converter(json.load(sys.stdin)), allow_nan=False))",
].join("\n");
const localPython = resolve(appRoot, "..", process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const python = process.env.SPIKE_TEST_PYTHON ?? process.env.PYTHON ?? (existsSync(localPython) ? localPython : "python");
const backendResult = JSON.parse(execFileSync(python, ["-c", backendScript], {
  cwd: resolve(appRoot, ".."), input: JSON.stringify(request), encoding: "utf8",
}));
assert.deepEqual(backendResult.request_snapshot, request, "the backend returns the exact admitted request snapshot");
assert.equal(staticModule.validSmpsConverterResult(backendResult, request), true, "the UI admits a real backend result");
const changedVoltage = structuredClone(request);
changedVoltage.input_voltage_v = 13;
assert.equal(staticModule.validSmpsConverterResult(backendResult, changedVoltage), false, "a changed operating voltage invalidates the saved result");
const changedRds = structuredClone(request);
changedRds.switches[0].rds_on_ohm = 0.02;
assert.equal(staticModule.validSmpsConverterResult(backendResult, changedRds), false, "a changed per-device Rds(on) invalidates the saved result");
const changedInductance = structuredClone(request);
changedInductance.inductor.inductance_h = 2e-5;
assert.equal(staticModule.validSmpsConverterResult(backendResult, changedInductance), false, "a changed inductance invalidates the saved result");

const manual = staticModule.createSyntheticSmpsDraft();
assert.equal(staticModule.buildSmpsConverterRequest(manual).inductor.component_ref, "L1", "the explicitly labeled no-board demo may use manual synthetic references");
const duplicate = structuredClone(boardDraft);
duplicate.switches[1].devices[0] = { ...duplicate.switches[0].devices[0] };
assert.throws(() => staticModule.buildSmpsConverterRequest(duplicate, components), /reused across converter roles/);
const foreign = structuredClone(boardDraft);
foreign.inductor = { ...foreign.inductor, occurrence_id: "other", component_ref: "L1" };
assert.throws(() => staticModule.buildSmpsConverterRequest(foreign, components), /loaded board/);
const twoSeries = structuredClone(boardDraft);
twoSeries.switches[0].seriesCount = "2";
assert.throws(() => staticModule.buildSmpsConverterRequest(twoSeries, components), /slots must equal series count x parallel count/);
assert.throws(() => staticModule.buildSmpsConverterRequest({ ...manual, outputVoltageV: "6", inputVoltageV: "5" }), /buck requires/i);
const inverting = staticModule.buildSmpsConverterRequest({ ...manual, topology: "inverting_buck_boost", outputVoltageV: "-5" });
assert.equal(inverting.output_voltage_v, -5, "the inverting topology retains the required negative output polarity");
assert.throws(() => staticModule.buildSmpsConverterRequest({ ...manual, switches: [{ ...manual.switches[0], riseTimeS: "2e-7", fallTimeS: "1e-8" }, manual.switches[1]] }), /10%/);

const resultFor = (solvedRequest, totalLoss = 0.5) => {
  const ledgerLoss = totalLoss - 0.05;
  return {
    contract: "spike/smps-converter-result/v1", block_id: solvedRequest.block_id, topology: solvedRequest.topology,
    request_snapshot: structuredClone(solvedRequest),
    model_status: "approximate", temporal_scope: "steady_average_only", duty_cycle: 0.42,
    input_current_a: (10 + totalLoss) / solvedRequest.input_voltage_v, input_power_w: 10 + totalLoss,
    output_power_w: 10, total_loss_w: totalLoss, efficiency: 10 / (10 + totalLoss),
    inductor_average_current_a: 2.1, inductor_rms_current_a: 2.12, inductor_peak_current_a: 2.5,
    inductor_minimum_current_a: 1.7, inductor_ripple_current_a: 0.8,
    losses: [
      { ...solvedRequest.switches[0].devices[0], role: "on", conduction_power_w: ledgerLoss * 2 / 9, switching_power_w: ledgerLoss * 2 / 9, total_power_w: ledgerLoss * 4 / 9 },
      { ...solvedRequest.switches[1].devices[0], role: "off", conduction_power_w: ledgerLoss * 2 / 9, switching_power_w: ledgerLoss * 2 / 9, total_power_w: ledgerLoss * 4 / 9 },
      { occurrence_id: solvedRequest.inductor.occurrence_id, component_ref: solvedRequest.inductor.component_ref, role: "inductor", conduction_power_w: ledgerLoss / 9, switching_power_w: 0, total_power_w: ledgerLoss / 9 },
    ],
    auxiliary_loss_w: 0.05, auxiliary_loss_location: "unassigned_gate_drive",
    solver: { iterations: 41, duty_bracket_width: 1e-15, periodic_current_residual_a: 1e-12, energy_balance_residual_w: 0 },
    limitations: ["Approximate steady CCM estimate; no switching waveforms, control-loop stability or transient response."],
  };
};
const result = resultFor(request);
assert.equal(staticModule.validSmpsConverterResult(result, request), true);
assert.equal(staticModule.validSmpsConverterResult({ ...result, request_snapshot: undefined }, request), false, "results without request provenance are rejected");
assert.equal(staticModule.validSmpsConverterResult({ ...result, temporal_scope: "switching_waveform" }, request), false);
assert.equal(staticModule.validSmpsConverterResult({ ...result, total_loss_w: 0.4 }, request), false, "power balance and ledger drift must be rejected");
assert.equal(staticModule.validSmpsConverterResult({ ...result, losses: result.losses.slice(1) }, request), false, "all bound component rows are required");
assert.equal(staticModule.validSmpsConverterResult({ ...result, losses: [result.losses[0], result.losses[0], result.losses[2]] }, request), false, "duplicate ledger identities cannot conceal a missing device");

const Panel = staticModule.default;
const markup = renderToStaticMarkup(React.createElement(Panel, { workerAvailable: true, components, initialRequest: request, initialResult: result }));
assert.match(markup, /MOSFET and inductor loss estimate/);
assert.match(markup, /SPIKE does not look up or infer device properties/);
assert.match(markup, /APPROXIMATE · STEADY AVERAGE ONLY/);
assert.match(markup, /Input <b>10\.5 W<\/b>/);
assert.match(markup, /Efficiency/);
assert.match(markup, /Inductor ripple/);
assert.match(markup, /Supplied rating checks/);
assert.match(markup, /Component loss ledger/);
assert.match(markup, /Unassigned gate-drive heat/);
assert.match(markup, /No switching waveform, control-loop stability, transient response, or hardware qualification is claimed/);
assert.match(markup, /High-side MOSFET/);
assert.match(markup, /daughter-a/);
assert.doesNotMatch(renderToStaticMarkup(React.createElement(Panel, { workerAvailable: true, components })), /Component loss ledger/, "the browser must not synthesize results");
const unavailable = renderToStaticMarkup(React.createElement(Panel, { workerAvailable: false, components }));
assert.match(unavailable, /Local solver worker unavailable/);
assert.match(unavailable, /<button[^>]*disabled=""[^>]*>Run converter estimate<\/button>/);
const manualMarkup = renderToStaticMarkup(React.createElement(Panel, { workerAvailable: true, components: [] }));
assert.match(manualMarkup, /No board components loaded/);
assert.match(manualMarkup, /aria-label="on device 1 occurrence"/);

const states = [];
const refs = [];
let stateCursor = 0;
let refCursor = 0;
const pending = [];
const statuses = [];
const captured = [];
const hookReact = {
  useEffect() {},
  useRef(initial) { const index = refCursor++; if (!(index in refs)) refs[index] = { current: initial }; return refs[index]; },
  useState(initial) {
    const index = stateCursor++;
    if (!(index in states)) states[index] = typeof initial === "function" ? initial() : initial;
    return [states[index], value => { states[index] = typeof value === "function" ? value(states[index]) : value; }];
  },
};
const worker = value => new Promise(resolvePromise => pending.push({ request: value, resolve: resolvePromise }));
const InteractivePanel = loadModule(hookReact, worker).default;
const mount = (workerAvailable = true) => {
  stateCursor = 0; refCursor = 0;
  return InteractivePanel({ workerAvailable, components, initialRequest: request,
    onStatus: message => statuses.push(message), onResult: (requestValue, resultValue) => captured.push([requestValue, resultValue]) });
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

findNode(mount(), node => node.type === "button" && node.props.children === "Run converter estimate").props.onClick();
assert.equal(pending.length, 1);
assert.equal(pending[0].request.method, "run_smps_converter");
assert.deepEqual(pending[0].request.params.request, request);
assert.equal(findNode(mount(), node => node.type === "button" && String(node.props.children).includes("Running converter")).props.disabled, true);
assert.equal(findNode(mount(), node => node.type === "fieldset" && node.props.children?.[0]?.props?.children === "Operating point").props.disabled, true);

// A newer request owns the UI even if an older worker response arrives later.
findNode(mount(), node => node.type === "button" && String(node.props.children).includes("Running converter")).props.onClick();
assert.equal(pending.length, 2);
const newerResult = resultFor(request, 0.6);
pending[1].resolve({ ok: true, result: newerResult });
await flush();
pending[0].resolve({ ok: false, error: "late obsolete failure" });
await flush();
let interactiveMarkup = renderToStaticMarkup(mount());
assert.match(interactiveMarkup, /10\.6 W/);
assert.doesNotMatch(interactiveMarkup, /late obsolete failure/);
assert.equal(captured.length, 1);
assert.strictEqual(captured[0][0].contract, "spike/smps-converter-request/v1");
assert.strictEqual(captured[0][1], newerResult, "onResult uses request/result ordering");

// Current failure retains the last valid result, and the next success recovers.
findNode(mount(), node => node.type === "button" && node.props.children === "Run converter estimate").props.onClick();
pending[2].resolve({ ok: false, error: "rating check failed for test" });
await flush();
interactiveMarkup = renderToStaticMarkup(mount());
assert.match(interactiveMarkup, /rating check failed for test/);
assert.match(interactiveMarkup, /last valid result remains visible/);
assert.match(interactiveMarkup, /10\.6 W/);
findNode(mount(), node => node.type === "button" && node.props.children === "Run converter estimate").props.onClick();
pending[3].resolve({ ok: true, result: resultFor(request, 0.55) });
await flush();
interactiveMarkup = renderToStaticMarkup(mount());
assert.match(interactiveMarkup, /10\.55 W/);
assert.doesNotMatch(interactiveMarkup, /rating check failed for test/);
assert.ok(statuses.some(message => message.includes("completed")));

const voltage = findNode(mount(), node => node.type === "input" && node.props["aria-label"] === "Input voltage (V)");
voltage.props.onChange({ target: { value: "13" } });
assert.match(renderToStaticMarkup(mount()), /Inputs differ from the solved setup/);

console.log("SMPS converter panel binding, admission, lifecycle, stale-state, recovery, and result presentation tests passed");
