// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const appRoot = resolve(import.meta.dirname, "..");
const source = readFileSync(resolve(appRoot, "src", "PiReturnPathAssistant.tsx"), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const nodeRequire = createRequire(import.meta.url);
function loadModule(reactDependency, worker) {
  const loaded = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => {
    if (name === "react") return reactDependency;
    if (name === "react/jsx-runtime") return nodeRequire("react/jsx-runtime");
    if (name === "./numericRange") return { numericExtent: values => values.reduce((range, value) => ({ minimum: Math.min(range.minimum, value), maximum: Math.max(range.maximum, value) }), { minimum: Infinity, maximum: -Infinity }) };
    if (name === "./workerBridge") return { runLocalWorker: worker };
    if (name === "./PiReturnPathAssistant.css") return {};
    return nodeRequire(name);
  }, loaded, loaded.exports);
  return loaded.exports;
}

const design = {
  contract: "spike/v1",
  nets: [{ id: "1", name: "VIN" }, { id: "2", name: "POWER_RTN" }, { id: "3", name: "CHASSIS" }],
  pads: [
    { id: "J1.1", component: "J1", number: "1", net_id: "1", layer: "F.Cu", center_mm: [1, 1] },
    { id: "J1.2", component: "J1", number: "2", net_id: "2", layer: "F.Cu", center_mm: [1, 2] },
    { id: "U1.2", component: "U1", number: "2", net_name: "POWER_RTN", layer: "F.Cu", center_mm: [20, 4] },
    { id: "U2.2", component: "U2", number: "2", net_name: "POWER_RTN", layer: "B.Cu", center_mm: [27, 16] },
    { id: "MH1", component: "MH1", number: "1", net_name: "CHASSIS", layer: "F.Cu", center_mm: [5, 25] },
  ],
  tracks: [], vias: [], zones: [], layers: [], stackup: [],
};
const staticModule = loadModule(React, async () => { throw new Error("not used by static render"); });
const pads = staticModule.extractPiReturnPads(design);
assert.deepEqual(pads.filter(pad => pad.net === "POWER_RTN").map(pad => pad.id), ["J1.2", "U1.2", "U2.2"]);
assert.match(pads.find(pad => pad.id === "U2.2").label, /U2\.2 · B\.Cu · U2\.2/);

const requestInput = {
  design, occurrenceId: "board-main", forwardNet: "VIN", returnNet: "POWER_RTN",
  sourcePadId: "J1.2", loadPadIds: ["U1.2", "U2.2"], meshTargetMm: "0.4",
};
const request = staticModule.buildPiReturnPathRequest(requestInput);
assert.deepEqual(request, {
  contract: "spike/pi-return-path-request/v1", occurrence_id: "board-main", forward_net: "VIN",
  return_net: "POWER_RTN", source_pad_id: "J1.2", load_pad_ids: ["U1.2", "U2.2"], mesh_target_mm: 0.4,
});
assert.throws(() => staticModule.buildPiReturnPathRequest({ ...requestInput, returnNet: "VIN", sourcePadId: "J1.1" }), /must be different/);
assert.throws(() => staticModule.buildPiReturnPathRequest({ ...requestInput, sourcePadId: "MH1" }), /source return pad/);
assert.throws(() => staticModule.buildPiReturnPathRequest({ ...requestInput, loadPadIds: ["J1.2"] }), /cannot also be a load/);
assert.throws(() => staticModule.buildPiReturnPathRequest({ ...requestInput, loadPadIds: Array.from({ length: 33 }, (_, index) => `pad-${index}`) }), /1 to 32/);
assert.throws(() => staticModule.buildPiReturnPathRequest({ ...requestInput, meshTargetMm: "" }), /Mesh target is required/);
assert.throws(() => staticModule.buildPiReturnPathRequest({ ...requestInput, meshTargetMm: "0.049" }), /0\.05 to 1000/);
assert.throws(() => staticModule.buildPiReturnPathRequest({ ...requestInput, meshTargetMm: "1000.1" }), /0\.05 to 1000/);
assert.equal(staticModule.buildPiReturnPathRequest({ ...requestInput, meshTargetMm: "0.05" }).mesh_target_mm, 0.05);
assert.equal(staticModule.buildPiReturnPathRequest({ ...requestInput, meshTargetMm: "1000" }).mesh_target_mm, 1000);
assert.throws(() => staticModule.buildPiReturnPathRequest({ ...requestInput, design: { ...design, pads: [...design.pads, { ...design.pads[0] }] } }), /duplicate pad IDs/);

const resultFor = (status = "connected", resistance = 0.003) => ({
  contract: "spike/pi-return-path-result/v1",
  status,
  paths: [
    { load_pad_id: "U1.2", connected: status === "connected", resistance_ohm: status === "connected" ? resistance : null,
      length_mm: status === "connected" ? 21.3 : null, points_mm: status === "connected" ? [[1, 2, 0], [9, 3, 0], [20, 4, 0]] : [] },
    { load_pad_id: "U2.2", connected: status === "connected", resistance_ohm: status === "connected" ? resistance * 2 : null,
      length_mm: status === "connected" ? 35.1 : null, points_mm: status === "connected" ? [[1, 2, 0], [14, 8, -0.2], [27, 16, -0.2]] : [] },
  ],
  issues: status === "connected" ? [{ severity: "info", code: "approximate", message: "Shortest-resistance route only." }] : ["No copper route reached every load."],
  proposals: status === "connected" ? [{ kind: "review_copper_bridge", start_mm: [8, 3, 0], end_mm: [9, 3, 0], gap_mm: 1 }] : [],
});
const connectedResult = resultFor();
assert.equal(staticModule.validPiReturnPathResult(connectedResult, request), true);
assert.equal(staticModule.validPiReturnPathResult({ ...connectedResult, paths: connectedResult.paths.slice(1) }, request), false, "every requested load requires exactly one path row");
assert.equal(staticModule.validPiReturnPathResult({ ...connectedResult, status: "connected", paths: connectedResult.paths.map((path, index) => index ? path : { ...path, connected: false }) }, request), false, "connected status cannot contain a disconnected path");
assert.equal(staticModule.validPiReturnPathResult({ ...connectedResult, paths: connectedResult.paths.map((path, index) => index ? path : { ...path, points_mm: [[1, 2, 0]] }) }, request), false, "connected route previews require returned route geometry");
assert.equal(staticModule.validPiReturnPathResult({ ...connectedResult, proposals: [{ ...connectedResult.proposals[0], gap_mm: -1 }] }, request), false);
assert.equal(staticModule.validPiReturnPathResult({ contract: "spike/pi-return-path-result/v1", status: "blocked", paths: [], issues: ["Geometry admission blocked."], proposals: [] }, request), true, "blocked plans may report issues before per-load routes exist");

const Panel = staticModule.default;
const initialMarkup = renderToStaticMarkup(React.createElement(Panel, { workerAvailable: true, design, occurrenceId: "board-main", forwardNet: "VIN" }));
assert.match(initialMarkup, /Return-path assistant/);
assert.match(initialMarkup, /without ground-name inference/);
assert.match(initialMarkup, /POWER_RTN/);
assert.match(initialMarkup, /CHASSIS/);
assert.doesNotMatch(initialMarkup, /value="VIN"/, "the forward net is not offered as its own return net");
assert.doesNotMatch(initialMarkup, /Returned resistance-route points/, "no browser-generated path is shown before a worker result");
const unavailable = renderToStaticMarkup(React.createElement(Panel, { workerAvailable: false, design, occurrenceId: "board-main", forwardNet: "VIN" }));
assert.match(unavailable, /Local solver worker unavailable/);
assert.match(unavailable, /<button[^>]*disabled=""[^>]*>Plan return paths<\/button>/);
const noDesign = renderToStaticMarkup(React.createElement(Panel, { workerAvailable: true, design: null, occurrenceId: "", forwardNet: "" }));
assert.match(noDesign, /No loaded design is available/);

const states = [];
const refs = [];
let stateCursor = 0;
let refCursor = 0;
const pending = [];
const statuses = [];
const applied = [];
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
  return InteractivePanel({ workerAvailable, design, occurrenceId: "board-main", forwardNet: "VIN",
    onStatus: message => statuses.push(message), onApply: selection => applied.push(selection) });
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

findNode(mount(), node => node.type === "select" && node.props["aria-label"] === "Return net").props.onChange({ target: { value: "POWER_RTN" } });
findNode(mount(), node => node.type === "select" && node.props["aria-label"] === "Source return pad").props.onChange({ target: { value: "J1.2" } });
findNode(mount(), node => node.type === "input" && node.props["aria-label"] === "Load return pad U1.2").props.onChange();
findNode(mount(), node => node.type === "input" && node.props["aria-label"] === "Load return pad U2.2").props.onChange();
findNode(mount(), node => node.type === "input" && node.props["aria-label"] === "Return-path mesh target (mm)").props.onChange({ target: { value: "0.4" } });
findNode(mount(), node => node.type === "button" && node.props.children === "Plan return paths").props.onClick();
assert.equal(pending.length, 1);
assert.equal(pending[0].request.method, "plan_pi_return_path");
assert.strictEqual(pending[0].request.params.design, design);
assert.deepEqual(pending[0].request.params.request, request);
assert.equal(findNode(mount(), node => node.type === "button" && String(node.props.children).includes("Planning return")).props.disabled, true);

// Only the latest request can own the displayed result.
findNode(mount(), node => node.type === "button" && String(node.props.children).includes("Planning return")).props.onClick();
assert.equal(pending.length, 2);
pending[1].resolve({ ok: true, result: connectedResult });
await flush();
pending[0].resolve({ ok: false, error: "late obsolete route failure" });
await flush();
let markup = renderToStaticMarkup(mount());
assert.match(markup, /Approximate shortest-resistance route/);
assert.match(markup, /Returned resistance-route points/);
assert.match(markup, /<polyline/);
assert.doesNotMatch(markup, /<circle/, "the preview does not invent pad or board geometry");
assert.match(markup, /Review-only copper bridge proposals/);
assert.match(markup, /do not modify the board/);
assert.match(markup, /does not solve full return-current distribution, loop inductance/);
assert.doesNotMatch(markup, /late obsolete route failure/);

const applyButton = findNode(mount(), node => node.type === "button" && node.props.children === "Apply reviewed terminals");
assert.equal(applyButton.props.disabled, false);
applyButton.props.onClick();
assert.deepEqual(applied, [{ returnNet: "POWER_RTN", sourcePadId: "J1.2", loadPadIds: ["U1.2", "U2.2"] }]);

const meshInput = findNode(mount(), node => node.type === "input" && node.props["aria-label"] === "Return-path mesh target (mm)");
meshInput.props.onChange({ target: { value: "0.5" } });
markup = renderToStaticMarkup(mount());
assert.match(markup, /Inputs differ from the planned setup/);
assert.equal(findNode(mount(), node => node.type === "button" && node.props.children === "Apply reviewed terminals").props.disabled, true);

// A current failure preserves the prior plan, and a later success clears it.
findNode(mount(), node => node.type === "button" && node.props.children === "Plan return paths").props.onClick();
pending[2].resolve({ ok: false, error: "mesh route failed for test" });
await flush();
markup = renderToStaticMarkup(mount());
assert.match(markup, /mesh route failed for test/);
assert.match(markup, /last valid plan remains visible/);
findNode(mount(), node => node.type === "button" && node.props.children === "Plan return paths").props.onClick();
const updatedRequest = { ...request, mesh_target_mm: 0.5 };
const updatedResult = resultFor("connected", 0.0032);
pending[3].resolve({ ok: true, result: updatedResult });
await flush();
markup = renderToStaticMarkup(mount());
assert.match(markup, /0\.0032 ohm/);
assert.doesNotMatch(markup, /mesh route failed for test/);
assert.deepEqual(pending[3].request.params.request, updatedRequest);
assert.ok(statuses.some(message => message.includes("completed")));

console.log("PI return-path assistant pad admission, worker lifecycle, route-only preview, stale apply gate, and recovery tests passed");
