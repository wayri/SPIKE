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
const source = readFileSync(resolve(appRoot, "src", "PwmElectrothermalPanel.tsx"), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const nodeRequire = createRequire(import.meta.url);
const playbackProps = [];

function loadModule(reactDependency, bridge = {}) {
  const loaded = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => {
    if (name === "react") return reactDependency;
    if (name === "react/jsx-runtime") return nodeRequire("react/jsx-runtime");
    if (name === "./SavedFramePlaybackControls") return { default: props => {
      playbackProps.push(props);
      return React.createElement("div", { "data-testid": "saved-frame-playback" }, "Timestamp playback");
    } };
    if (name === "./numericRange") return { numericExtent: values => {
      let minimum = Infinity, maximum = -Infinity, count = 0;
      for (const value of values) { minimum = Math.min(minimum, value); maximum = Math.max(maximum, value); count += 1; }
      return { minimum, maximum, count };
    } };
    if (name === "./workerBridge") return {
      runLocalWorker: bridge.runLocalWorker ?? (async () => { throw new Error("not used"); }),
      subscribeWorkerProgress: bridge.subscribeWorkerProgress ?? (async () => () => undefined),
      cancelLocalWorker: bridge.cancelLocalWorker ?? (async () => false),
      cancelLocalWorkerCleanup: bridge.cancelLocalWorkerCleanup ?? (async () => false),
      saveNativeTextFile: bridge.saveNativeTextFile ?? (async () => null),
    };
    if (name === "./PwmElectrothermalPanel.css") return {};
    return nodeRequire(name);
  }, loaded, loaded.exports);
  return loaded.exports;
}

const panelModule = loadModule(React);
const defaultDraft = Object.fromEntries(Object.entries(panelModule.DEFAULT_PWM_ELECTROTHERMAL_PARAMETERS).map(([key, value]) => [key, String(value)]));
const defaults = panelModule.buildPwmElectrothermalRequest(defaultDraft);
assert.equal(defaults.contract, "spike/pwm-electrothermal-request/v1");
assert.equal(defaults.parameters.input_voltage_v, 12);
assert.equal(defaults.parameters.target_voltage_v, 5);
assert.equal(defaults.parameters.switching_frequency_hz, 20_000);
assert.equal(defaults.parameters.cycles, 400);
assert.equal(panelModule.validPwmElectrothermalRequest(defaults), true);
assert.equal(panelModule.validPwmElectrothermalRequest({ ...defaults, untrusted_path: "solver.dll" }), false);
assert.throws(() => panelModule.buildPwmElectrothermalRequest({ ...defaultDraft, target_voltage_v: "12" }), /below input/);
assert.throws(() => panelModule.buildPwmElectrothermalRequest({ ...defaultDraft, cycles: "2.5" }), /integer/);
assert.throws(() => panelModule.buildPwmElectrothermalRequest({ ...defaultDraft, maximum_step_s: "0.001" }), /quarter/);
assert.throws(() => panelModule.buildPwmElectrothermalRequest({ ...defaultDraft, maximum_step_s: "1e-9", cycles: "2000" }), /200,000/);

const backendScript = [
  "import importlib.util, json, sys",
  "spec = importlib.util.spec_from_file_location('spike_pwm', 'python/spike_core/pwm_electrothermal.py')",
  "module = importlib.util.module_from_spec(spec)",
  "spec.loader.exec_module(module)",
  "print(json.dumps(module.validate_pwm_electrothermal(json.load(sys.stdin)), allow_nan=False))",
].join("\n");
const localPython = resolve(appRoot, "..", process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const python = process.env.SPIKE_TEST_PYTHON ?? process.env.PYTHON ?? (existsSync(localPython) ? localPython : "python");
const backendAdmission = JSON.parse(execFileSync(python, ["-c", backendScript], {
  cwd: resolve(appRoot, ".."), input: JSON.stringify(defaults), encoding: "utf8",
}));
assert.equal(panelModule.validPwmElectrothermalAdmission(backendAdmission, defaults), true, "the panel admits the actual backend preflight shape");
assert.equal(backendAdmission.parameters.cycles, 400);
assert.equal(panelModule.validPwmElectrothermalAdmission({ ...backendAdmission, maximum_electrical_steps: 200_001 }, defaults), false);

const request = panelModule.buildPwmElectrothermalRequest({ ...defaultDraft, cycles: "3" });
const hash = "a".repeat(64);
const cycleEnergy = value => ({ source_j: value, switch_j: value / 20, load_j: value / 2, winding_j: value / 30, ambient_j: value / 40, be_numerical_dissipation_j: value / 100 });
const windows = [1, 2, 3].map(cycle => ({
  cycle, time_s: cycle * 5e-5, duty: 0.42 + cycle * 0.001,
  output_voltage_v: 4.8 + cycle * 0.05, inductor_current_a: 0.8 + cycle * 0.04,
  winding_temperature_k: 300 + cycle * 0.03, on_start_s: (cycle - 1) * 5e-5,
  off_start_s: (cycle - 1) * 5e-5 + 2.1e-5,
  minimum_output_voltage_v: 4.7 + cycle * 0.05, maximum_output_voltage_v: 4.9 + cycle * 0.05,
  minimum_inductor_current_a: 0.7 + cycle * 0.04, maximum_inductor_current_a: 0.9 + cycle * 0.04,
  energy: cycleEnergy(cycle * 1e-4),
}));
const result = {
  contract: "spike/pwm-electrothermal-result/v1", status: "completed", model_status: "experimental",
  checkpoint: { contract: "spike/pwm-electrothermal-checkpoint/v1", completed_cycles: 3, configuration_sha256: hash, library_sha256: "b".repeat(64), state_sha256: "c".repeat(64) },
  restart: { method: "deterministic_replay", verified: true, no_replay_speedup_claim: true }, issue_codes: [],
  parameters: structuredClone(request.parameters), windows,
  energy: { ...cycleEnergy(3e-4), electrical_stored_j: 1e-5, thermal_stored_j: 2e-5, electrical_balance_j: 1e-14, thermal_balance_j: -1e-14 },
  request_sha256: "d".repeat(64), configuration_sha256: hash,
  runtime: { engine: "native_spikes_persistent_mna", integration: "backward_euler", library_sha256: "b".repeat(64), diagnostics: { completed_steps: 159, matrix_factorizations: 12, total_newton_iterations: 181, residual_inf_norm: 1e-13 } },
  quality: { maximum_step_electrical_balance_j: 1e-14, maximum_step_thermal_balance_j: 2e-14, maximum_element_power_balance_w: 3e-12 },
  limits: ["finite-conductance behavioral switches, not vendor transistor models", "winding-only lumped thermal feedback; switch/load heat is external", "no spatial thermal, EMI, measured correlation or release qualification"],
};
assert.equal(panelModule.validPwmElectrothermalResult(result, request, hash), true);
assert.equal(panelModule.validPwmElectrothermalResult({ ...result, parameters: { ...result.parameters, target_voltage_v: 4.5 } }, request, hash), false, "saved results must match the exact saved request");
assert.equal(panelModule.validPwmElectrothermalResult({ ...result, windows: windows.slice(0, 2) }, request, hash), false, "completed runs require every requested cycle");
assert.equal(panelModule.validPwmElectrothermalResult({ ...result, configuration_sha256: "e".repeat(64) }, request, hash), false, "preflight and result hashes stay bound");

const markup = renderToStaticMarkup(React.createElement(panelModule.default, { workerAvailable: true, initialRequest: request, initialResult: result }));
assert.match(markup, /PWM buck electrothermal/);
assert.match(markup, /finite R<sub>on<\/sub>\/R<sub>off<\/sub>/);
assert.match(markup, /Only winding Joule heat feeds the lumped thermal state/);
assert.match(markup, /does not claim vendor transistor behavior, spatial or 3D thermal fields, EMI/);
assert.match(markup, /Output voltage by completed PWM cycle/);
assert.match(markup, /Inductor current by completed PWM cycle/);
assert.match(markup, /Winding temperature by completed PWM cycle/);
assert.match(markup, /Timestamp playback/);
assert.deepEqual(playbackProps[0].timesS, windows.map(window => window.time_s), "playback must receive exact returned cycle timestamps");
assert.equal(playbackProps[0].playbackSpeed, 1, "default playback is honest 1x simulated time");
assert.equal(playbackProps[0].onExport, undefined, "the PWM panel does not expose an animation export surface");
assert.match(markup, /External switch loss/);
assert.match(markup, /Export request \+ result/);
assert.doesNotMatch(renderToStaticMarkup(React.createElement(panelModule.default, { workerAvailable: true })), /pwm-electrothermal-trace/, "the browser must not synthesize solver traces");
const unavailable = renderToStaticMarkup(React.createElement(panelModule.default, { workerAvailable: false }));
assert.match(unavailable, /Local solver worker unavailable/);
assert.match(unavailable, /<button[^>]*disabled=""[^>]*>Validate and run<\/button>/);
assert.doesNotThrow(() => renderToStaticMarkup(React.createElement(panelModule.default, {
  workerAvailable: true, initialRequest: { contract: "spike/pwm-electrothermal-request/v1", parameters: null },
})), "malformed persisted parameters must be rejected before draft initialization");

const states = [];
const refs = [];
let stateCursor = 0;
let refCursor = 0;
const calls = [];
let progressListener = null;
let resolveRun;
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
const bridge = {
  runLocalWorker: async value => {
    calls.push(value);
    if (value.method === "validate_pwm_electrothermal") return { ok: true, result: { ...backendAdmission, parameters: structuredClone(request.parameters), configuration_sha256: hash } };
    return new Promise(resolvePromise => { resolveRun = resolvePromise; });
  },
  subscribeWorkerProgress: async listener => { progressListener = listener; return () => { progressListener = null; }; },
};
const InteractivePanel = loadModule(hookReact, bridge).default;
const mount = () => {
  stateCursor = 0; refCursor = 0;
  return InteractivePanel({ workerAvailable: true, initialRequest: request, onResult: (requestValue, resultValue) => captured.push([requestValue, resultValue]) });
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
findNode(mount(), node => node.type === "button" && node.props.children === "Validate and run").props.onClick();
await flush();
assert.deepEqual(calls.map(call => call.method), ["validate_pwm_electrothermal", "run_pwm_electrothermal"]);
assert.deepEqual(calls[0].params, { request });
assert.deepEqual(calls[1].params, { request });
assert.equal(typeof calls[1].id, "string");
progressListener?.({ operationId: calls[1].id, method: "run_pwm_electrothermal", frame: { completed_cycles: 2, total_cycles: 3 } });
assert.deepEqual(states.find(value => value?.completed === 2), { completed: 2, total: 3 });
resolveRun({ ok: true, result });
await flush();
assert.equal(captured.length, 1);
assert.deepEqual(captured[0][0], request);
assert.strictEqual(captured[0][1], result);

function createHookHarness(bridge) {
  const hookStates = [], hookRefs = [], hookEffects = [];
  let stateIndex = 0, refIndex = 0, effectIndex = 0, scheduled = [];
  const react = {
    useState(initial) {
      const index = stateIndex++;
      if (!(index in hookStates)) hookStates[index] = typeof initial === "function" ? initial() : initial;
      return [hookStates[index], value => { hookStates[index] = typeof value === "function" ? value(hookStates[index]) : value; }];
    },
    useRef(initial) {
      const index = refIndex++;
      if (!(index in hookRefs)) hookRefs[index] = { current: initial };
      return hookRefs[index];
    },
    useEffect(callback, dependencies) {
      const index = effectIndex++;
      const prior = hookEffects[index];
      const changed = !prior || dependencies === undefined || prior.dependencies === undefined
        || dependencies.length !== prior.dependencies.length || dependencies.some((value, item) => !Object.is(value, prior.dependencies[item]));
      if (changed) scheduled.push({ index, callback, dependencies });
    },
  };
  const Panel = loadModule(react, bridge).default;
  return {
    render(props) {
      stateIndex = 0; refIndex = 0; effectIndex = 0; scheduled = [];
      const tree = Panel(props);
      for (const item of scheduled) {
        hookEffects[item.index]?.cleanup?.();
        hookEffects[item.index] = { dependencies: item.dependencies, cleanup: item.callback() };
      }
      return tree;
    },
  };
}

const replacementRequest = panelModule.buildPwmElectrothermalRequest({ ...defaultDraft, target_voltage_v: "4", cycles: "3" });
const replacementHash = "e".repeat(64);
const replacementResult = {
  ...structuredClone(result), parameters: structuredClone(replacementRequest.parameters), request_sha256: "f".repeat(64), configuration_sha256: replacementHash,
  checkpoint: { ...result.checkpoint, configuration_sha256: replacementHash, state_sha256: "1".repeat(64) },
};
assert.equal(panelModule.validPwmElectrothermalResult(replacementResult, replacementRequest, replacementHash), true);
assert.notEqual(panelModule.pwmElectrothermalPersistenceFingerprint(request, result), panelModule.pwmElectrothermalPersistenceFingerprint(replacementRequest, replacementResult));

const lifecycleCalls = [], cleanupCalls = [], lifecycleCaptured = [];
let resolveLifecycleRun;
const lifecycleHarness = createHookHarness({
  runLocalWorker: async value => {
    lifecycleCalls.push(value);
    if (value.method === "validate_pwm_electrothermal") return { ok: true, result: { ...backendAdmission, parameters: structuredClone(request.parameters), configuration_sha256: hash } };
    return new Promise(resolvePromise => { resolveLifecycleRun = resolvePromise; });
  },
  subscribeWorkerProgress: async () => () => undefined,
  cancelLocalWorkerCleanup: async id => { cleanupCalls.push(id); return true; },
});
const lifecycleProps = { workerAvailable: true, initialRequest: request, onResult: (...values) => lifecycleCaptured.push(values) };
let lifecycleTree = lifecycleHarness.render(lifecycleProps);
findNode(lifecycleTree, node => node.type === "button" && node.props.children === "Validate and run").props.onClick();
await flush();
assert.deepEqual(lifecycleCalls.map(call => call.method), ["validate_pwm_electrothermal", "run_pwm_electrothermal"]);
const supersededOperation = lifecycleCalls[1].id;
lifecycleHarness.render({ ...lifecycleProps, initialRequest: replacementRequest, initialResult: replacementResult });
lifecycleTree = lifecycleHarness.render({ ...lifecycleProps, initialRequest: replacementRequest, initialResult: replacementResult });
assert.equal(findNode(lifecycleTree, node => node.props?.legend === "Source and controller").props.draft.target_voltage_v, "4");
assert.deepEqual(cleanupCalls, [supersededOperation], "opening another persisted setup cancels the operation owned by the previous setup");
resolveLifecycleRun({ ok: true, result });
await flush();
assert.equal(lifecycleCaptured.length, 0, "a superseded worker response cannot overwrite the replacement project");
lifecycleTree = lifecycleHarness.render({ ...lifecycleProps, initialRequest: replacementRequest, initialResult: replacementResult });
assert.strictEqual(findNode(lifecycleTree, node => node.props?.result === replacementResult)?.props.result, replacementResult);

const echoCaptured = [];
const echoHarness = createHookHarness({
  runLocalWorker: async value => value.method === "validate_pwm_electrothermal"
    ? { ok: true, result: { ...backendAdmission, parameters: structuredClone(request.parameters), configuration_sha256: hash } }
    : { ok: true, result },
  subscribeWorkerProgress: async () => () => undefined,
});
const echoProps = { workerAvailable: true, initialRequest: request, onResult: (...values) => echoCaptured.push(values) };
let echoTree = echoHarness.render(echoProps);
findNode(echoTree, node => node.type === "button" && node.props.children === "Validate and run").props.onClick();
await flush();
assert.equal(echoCaptured.length, 1);
echoTree = echoHarness.render(echoProps);
findNode(echoTree, node => node.props?.legend === "Source and controller").props.patch("target_voltage_v", "4.7");
echoHarness.render({ ...echoProps, initialResult: result });
echoTree = echoHarness.render({ ...echoProps, initialResult: result });
assert.equal(findNode(echoTree, node => node.props?.legend === "Source and controller").props.draft.target_voltage_v, "4.7", "the parent's echo of the panel's own result must not reset newer local edits");

console.log("PWM electrothermal defaults, validation, admission, worker sequence, binding, and rendering tests passed");
