// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const appRoot = resolve(import.meta.dirname, "..");
const source = readFileSync(resolve(appRoot, "src", "BoardThermalPanel.tsx"), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const module = { exports: {} };
const require = createRequire(import.meta.url);
const dependencies = {
  react: React,
  "react/jsx-runtime": require("react/jsx-runtime"),
  "./thermalResultFields": { thermalFieldColor: value => value < 35 ? [0, 0, 1] : [1, 0, 0] },
  "./boardThermalViewport": { boardThermalCuts: (grid, position, layers) => ({
    horizontal: [[5, grid.temperatures_c[0]], [15, grid.temperatures_c[1]]],
    vertical: [[5, grid.temperatures_c[0]]],
    throughStack: layers?.map(layer => [layer.thickness_mm / 2, layer.temperatures_c[0]]) ?? [],
  }) },
  "./numericRange": { numericExtent: values => ({ minimum: Math.min(...values), maximum: Math.max(...values) }) },
  "./workerBridge": { runLocalWorker: async () => { throw new Error("not used by static render"); } },
};
new Function("require", "module", "exports", compiled)(name => dependencies[name] ?? require(name), module, module.exports);
const BoardThermalPanel = module.exports.default;
const board = { bounds: { minX: 0, minY: 0, maxX: 20, maxY: 10 }, components: [{ ref: "U1", at: [5, 5] }], pads: [
  { ref: "U1", name: "1", width: 1, height: 1, drill: 0, layers: ["F.Cu"] },
  { ref: "U1", name: "2", width: 1, height: 1, drill: 0, layers: ["F.Cu"] },
  { ref: "U1", name: "hole", width: 1, height: 1, drill: 1, layers: ["*.Mask"] },
] };
const design = { contract: "spike/v1", components: [{ ref: "U1", at: [5, 5] }], pads: board.pads };
const request = {
  ambient_temperature_c: 25,
  board: { thickness_mm: 1, convection_top_w_m2k: 10, convection_bottom_w_m2k: 10, grid_step_mm: 10, model: "plate", conductivity_w_mk: 10 },
  components: [{ component_ref: "U1", power_w: 0.1, r_junction_case_k_w: 2, r_case_board_k_w: 3, contact_mode: "pads" }],
};
const result = {
  contract: "spike/board-thermal-result/v1", status: "completed", model_status: "approximate",
  grid: { origin_mm: [0, 0], spacing_mm: [10, 10], shape: [2, 1], temperatures_c: [30, 40], order: "x-fast" },
  layer_grids: [{ name: "F.Cu", thickness_mm: 0.035, temperatures_c: [31, 41], copper_coverage: [1, 0] }],
  components: [{ ...request.components[0], position_mm: [5, 5], board_temperature_c: 30, case_temperature_c: 30.3, junction_temperature_c: 30.5, pad_count: 2, pad_contacts: [
    { pad_name: "1", position_mm: [4, 5], area_mm2: 1, board_temperature_c: 30, heat_w: 0.05 },
    { pad_name: "2", position_mm: [6, 5], area_mm2: 1, board_temperature_c: 30, heat_w: 0.05 },
  ] }],
  summary: { minimum_board_temperature_c: 30, maximum_board_temperature_c: 40, maximum_junction_temperature_c: 30.5, total_power_w: 0.1, energy_balance_error_w: 0, linear_relative_residual: 0 },
};
function render(savedRequest, savedResult) {
  return renderToStaticMarkup(React.createElement(BoardThermalPanel, {
    board, design, ambientC: 25,
    workerAvailable: true, savedRequest, savedResult, onSave() {}, onStatus() {},
  }));
}
const complete = render(request, result);
assert.match(complete, /Board temperature grid, 2 by 1 cells, 30\.00 to 40\.00 degrees Celsius/);
assert.equal((complete.match(/<rect /g) ?? []).length, 2, "one drawn cell per returned temperature");
assert.match(complete, /Junction °C/);
assert.match(complete, /30\.30/);
assert.match(complete, /30\.50/);
assert.match(complete, /uniform 2D sheet/);
assert.match(complete, /Smooth displayed temperature colors/);
assert.match(complete, /feGaussianBlur stdDeviation="0.55"/);
assert.match(complete, /Temperature layer/);
assert.match(complete, /Horizontal X temperature profile/);
assert.match(complete, /Through stack Z temperature profile/);
assert.match(complete, /Pad contact resolution warning/);
assert.match(complete, /2 pads/);
assert.match(complete, /U1 pad heat paths \(2\)/);
assert.match(complete, /pad heat paths[\s\S]*0\.0500/);
assert.match(complete, /value="pads" selected=""/);
assert.doesNotMatch(complete, /U1 contact_size_mm" type="number"[^>]*value="2"/);
const invalid = render(request, { ...result, grid: { ...result.grid, temperatures_c: [30] } });
assert.doesNotMatch(invalid, /Board temperature grid, 2 by 1 cells/);
assert.doesNotMatch(invalid, /Junction °C/);
const fresh = render(undefined, undefined);
assert.doesNotMatch(fresh, /Board temperature grid/);
assert.match(fresh, /Effective board conductivity<span><input aria-label="Board conductivity" type="number"[^>]*value=""/);
assert.match(fresh, /Imported pads<\/option>/);
assert.match(fresh, /Layered mode is unavailable/);
assert.match(fresh, /<td>2<\/td>/);
assert.match(fresh, /U1 contact_size_mm" type="number"[^>]*disabled=""/);
const legacySquare = { ...request, components: [{ ...request.components[0], contact_mode: undefined, contact_size_mm: 2 }] };
assert.match(render(legacySquare, undefined), /value="square" selected=""/);
assert.doesNotMatch(render(request, { ...result, components: [{ ...result.components[0], pad_contacts: [] }] }), /Board temperature grid/);

// Exercise the run handler with the desktop parser's ``ref`` component shape.
const states = [];
let cursor = 0;
let workerRequest;
const interactive = { exports: {} };
new Function("require", "module", "exports", compiled)(name => name === "react" ? {
  useEffect() {},
  useState(initial) {
    const index = cursor++;
    if (!(index in states)) states[index] = typeof initial === "function" ? initial() : initial;
    return [states[index], value => { states[index] = typeof value === "function" ? value(states[index]) : value; }];
  },
} : name === "./workerBridge" ? { runLocalWorker: async value => { workerRequest = value; return { ok: true, result }; } } : dependencies[name] ?? require(name), interactive, interactive.exports);
const mount = (activeBoard = board, activeDesign = design, activeRequest = request, sourceText = null) => {
  cursor = 0;
  return interactive.exports.default({ board: activeBoard, design: activeDesign, sourceText,
    ambientC: 25, workerAvailable: true, savedRequest: activeRequest, onRequireAdmission: async () => null, onSave() {}, onStatus() {} });
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
const run = findNode(mount(), node => node.type === "button" && node.props.className === "run-btn");
run.props.onClick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(workerRequest.method, "run_board_thermal");
assert.equal(workerRequest.params.assembly_scope, null);
assert.deepEqual(workerRequest.params.design.metadata.board_bounds_mm, [0, 0, 20, 10]);
assert.equal(workerRequest.params.design.components[0].ref, "U1");
assert.equal(workerRequest.params.request.components[0].r_junction_case_k_w, 2);
assert.equal(workerRequest.params.request.components[0].contact_mode, "pads");
assert.equal("contact_size_mm" in workerRequest.params.request.components[0], false);
const mode = findNode(mount(), node => node.type === "select" && node.props["aria-label"] === "U1 contact mode");
mode.props.onChange({ target: { value: "square" } });
const width = findNode(mount(), node => node.type === "input" && node.props["aria-label"] === "U1 contact_size_mm");
assert.equal(width.props.disabled, false);
width.props.onChange({ target: { value: "2" } });
findNode(mount(), node => node.type === "button" && node.props.className === "run-btn").props.onClick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(workerRequest.params.request.components[0].contact_mode, "square");
assert.equal(workerRequest.params.request.components[0].contact_size_mm, 2);
assert.equal(workerRequest.params.request.board.model, "plate");
assert.equal("source_kicad_pcb" in workerRequest.params, false);
assert.equal("dielectric_conductivity_w_mk" in workerRequest.params.request.board, false);
states.length = 0;
const layeredRequest = { ...request, board: { ...request.board, model: "layered", conductivity_w_mk: undefined, dielectric_conductivity_w_mk: 0.3, copper_conductivity_w_mk: 380, via_plating_thickness_mm: 0.025, include_copper: true, include_vias: true, include_tracks: true, include_pads: true, include_zones: true, fuzzy_sigma_mm: 0.4 } };
const layeredBoard = { ...board, stackup: [
  { name: "F.Cu", type: "copper", thickness: 0.035 },
  { name: "core", type: "dielectric", thickness: 0.93 },
  { name: "B.Cu", type: "copper", thickness: 0.035 },
] };
const model = findNode(mount(layeredBoard, design, layeredRequest), node => node.type === "select" && node.props["aria-label"] === "Board thermal model");
assert.equal(model.props.value, "layered");
assert.match(renderToStaticMarkup(mount(layeredBoard, design, layeredRequest)), /Via plating thickness/);
assert.match(renderToStaticMarkup(mount(layeredBoard, design, layeredRequest)), /3 depth layers/);
findNode(mount(layeredBoard, design, layeredRequest, "(kicad_pcb fixture)"), node => node.type === "button" && node.props.className === "run-btn").props.onClick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(workerRequest.params.request.board.model, "layered");
assert.equal(workerRequest.params.source_kicad_pcb, "(kicad_pcb fixture)");
assert.equal(workerRequest.params.request.board.dielectric_conductivity_w_mk, 0.3);
assert.equal(workerRequest.params.request.board.fuzzy_sigma_mm, 0.4);
assert.equal("conductivity_w_mk" in workerRequest.params.request.board, false);
const layer = findNode(mount(layeredBoard, design, layeredRequest), node => node.type === "select" && node.props["aria-label"] === "Temperature layer");
layer.props.onChange({ target: { value: "0" } });
assert.match(renderToStaticMarkup(mount(layeredBoard, design, layeredRequest)), /F\.Cu temperature grid, 2 by 1 cells, 31\.00 to 41\.00 degrees Celsius/);
findNode(mount(layeredBoard, design, layeredRequest), node => node.type === "input" && node.props["aria-label"] === "Show copper coverage").props.onChange({ target: { checked: true } });
assert.match(renderToStaticMarkup(mount(layeredBoard, design, layeredRequest)), /White overlay indicates copper coverage/);
states.length = 0;
const sinkRequest = { ...layeredRequest, virtual_heatsinks: [{ id: "HS1", face: "top", x_mm: 10, y_mm: 5,
  width_mm: 4, height_mm: 4, interface_resistance_k_w: 1, sink_to_ambient_k_w: 8 }] };
const sinkMarkup = renderToStaticMarkup(React.createElement(BoardThermalPanel, { board: layeredBoard, design,
  ambientC: 25, workerAvailable: true, savedRequest: sinkRequest,
  savedResult: { ...result, virtual_heatsinks: [{ ...sinkRequest.virtual_heatsinks[0], temperature_c: 29,
    board_contact_temperature_c: 30, heat_flow_w: 0.5 }], summary: { ...result.summary, heatsink_outward_heat_w: 0.5 } },
  onSave() {}, onStatus() {} }));
assert.match(sinkMarkup, /VIRTUAL BOARD HEATSINKS/);
assert.match(sinkMarkup, /Virtual heatsink heat paths/);
assert.match(sinkMarkup, /0\.5000/);
findNode(mount(layeredBoard, design, sinkRequest), node => node.type === "button" && node.props.className === "run-btn").props.onClick();
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(workerRequest.params.request.virtual_heatsinks, sinkRequest.virtual_heatsinks);
states.length = 0;
const transientRequest = { ...layeredRequest, transient: { end_time_s: 20, time_step_s: 10, output_stride: 1,
  copper_volumetric_heat_capacity_j_m3k: 3.45e6, dielectric_volumetric_heat_capacity_j_m3k: 1.4e6 } };
const transientResult = { ...result, transient: [
  { time_s: 0, layer_temperatures_c: [[25, 25]], maximum_board_temperature_c: 25, storage_rate_w: 0, energy_balance_error_w: 0 },
  { time_s: 10, layer_temperatures_c: [[27, 28]], maximum_board_temperature_c: 28, storage_rate_w: 0.08, energy_balance_error_w: 0 },
], summary: { ...result.summary, transient_peak_board_temperature_c: 28, transient_final_stored_energy_j: 0.8,
  max_transient_energy_balance_error_w: 0 } };
const transientMarkup = renderToStaticMarkup(React.createElement(BoardThermalPanel, { board: layeredBoard, design,
  ambientC: 25, workerAvailable: true, savedRequest: transientRequest, savedResult: transientResult,
  onSave() {}, onStatus() {} }));
assert.match(transientMarkup, /TRANSIENT BOARD ANIMATION/);
assert.match(transientMarkup, /Maximum board temperature versus transient time/);
assert.match(transientMarkup, /Transient board time frame/);
findNode(mount(layeredBoard, design, transientRequest), node => node.type === "button" && node.props.className === "run-btn").props.onClick();
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(workerRequest.params.request.transient, transientRequest.transient);
states.length = 0;
const defaultLayered = findNode(mount(layeredBoard, design, null), node => node.type === "select" && node.props["aria-label"] === "Board thermal model");
assert.equal(defaultLayered.props.value, "layered");
states.length = 0;
workerRequest = undefined;
const oversized = { ...layeredRequest, board: { ...layeredRequest.board, grid_step_mm: 0.01 } };
findNode(mount(layeredBoard, design, oversized), node => node.type === "button" && node.props.className === "run-btn").props.onClick();
assert.match(findNode(mount(layeredBoard, design, oversized), node => node.props?.role === "alert").props.children, /above the 8,192-cell limit/);
assert.equal(workerRequest, undefined);
states.length = 0;
const mismatched = { ...layeredRequest, board: { ...layeredRequest.board, thickness_mm: 2 } };
findNode(mount(layeredBoard, design, mismatched), node => node.type === "button" && node.props.className === "run-btn").props.onClick();
assert.match(findNode(mount(layeredBoard, design, mismatched), node => node.props?.role === "alert").props.children, /agree with imported physical stackup thickness/);
assert.equal(workerRequest, undefined);
states.length = 0;
workerRequest = undefined;
const noPads = { ...board, pads: [] };
const noPadDesign = { ...design, pads: [] };
findNode(mount(noPads, noPadDesign), node => node.type === "button" && node.props.className === "run-btn").props.onClick();
const alert = findNode(mount(noPads, noPadDesign), node => node.props?.role === "alert");
assert.match(alert.props.children, /U1 has no eligible imported copper pads/);
assert.equal(workerRequest, undefined, "invalid pad mode must not reach the worker");
console.log("board thermal panel render and saved result validation passed");
