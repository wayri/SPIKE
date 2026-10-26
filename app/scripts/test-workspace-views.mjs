// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";

const model = await importTestTypescript("workspaceViewModel");
const source = readFileSync(new URL("../src/useWorkspaceViews.tsx", import.meta.url), "utf8");
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const nativeRequire = createRequire(import.meta.url);
let closeAllCalls = 0;
const ScopedWorkspaceView = () => null;
const WorkspaceViewHost = () => null;
const WorkspaceViewTabs = () => null;

function makeRunner() {
  const slots = [];
  let cursor = 0;
  let pendingEffects = [];
  const same = (a, b) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
  const useState = initial => {
    const index = cursor++;
    if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
    return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
  };
  const useRef = initial => { const index = cursor++; if (!(index in slots)) slots[index] = { current: initial }; return slots[index]; };
  const useMemo = (factory, deps) => { const index = cursor++; if (!slots[index] || !same(slots[index].deps, deps)) slots[index] = { deps, value: factory() }; return slots[index].value; };
  const useEffect = (effect, deps) => { const index = cursor++; if (!slots[index] || !same(slots[index].deps, deps)) pendingEffects.push({ index, effect, deps }); };
  const react = { useState, useRef, useMemo, useCallback: (callback, deps) => useMemo(() => callback, deps), useEffect };
  const module = { exports: {} };
  new Function("require", "module", "exports", js)(name => {
    if (name === "react") return react;
    if (name === "./workspaceViewModel") return model;
    if (name === "./workspaceViewWindows") return { closeAllWorkspaceViewWindows: async () => { closeAllCalls++; } };
    if (name === "./ScopedWorkspaceView") return { __esModule: true, default: ScopedWorkspaceView };
    if (name === "./WorkspaceViewHost") return { __esModule: true, default: WorkspaceViewHost };
    if (name === "./WorkspaceViewTabs") return { __esModule: true, default: WorkspaceViewTabs };
    return nativeRequire(name);
  }, module, module.exports);
  return {
    render(options) {
      cursor = 0; pendingEffects = [];
      const result = module.exports.useWorkspaceViews(options);
      for (const pending of pendingEffects) {
        slots[pending.index]?.cleanup?.();
        slots[pending.index] = { deps: pending.deps, cleanup: pending.effect() };
      }
      return result;
    },
  };
}

const transform = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const occurrence = { id: "occ-A", designId: "design-A", name: "Power board", active: true, widthMm: 20, heightMm: 10, localCenterMm: [10, 5, 0], transform };
const board = { nets: { "net-1": "GND" }, tracks: [], pads: [], vias: [], zones: [], components: [] };
const errors = [], actions = [];
const sharedToolbarHost = {};
const base = {
  toolbarHost: sharedToolbarHost,
  projectSession: "project-1", revision: "state-1", viewportRevision: "viewport-1",
  boards: { "design-A": board }, occurrences: [occurrence], assemblyModels: [{ id: "model-lid", partId: "lid" }],
  parts: [{ partId: "lid", title: "Lid" }], visibility: { "occ-A": true }, layerVisibility: { "occ-A": { "F.Cu": true } },
  showNetNames: true, assemblyNetNameVisibility: { "occ-A": false, "occ-B": true },
  zoneDisplay: "transparent", assemblyZoneDisplay: { "occ-A": "outline", "occ-B": "filled" },
  layerOpacity: { "occ-A": { "F.Cu": .8 } }, layerFocus: { "occ-A": "F.Cu" }, linkedNets: {},
  onAction: action => actions.push(action), onError: message => errors.push(message),
};
const runner = makeRunner();
let ui = runner.render(base);
assert.equal(ui.candidates.length, 2);
ui.addView(ui.candidates[0]); ui = runner.render(base);
ui.addView(ui.candidates[0]); ui = runner.render(base);
assert.equal(ui.views.length, 2, "two independent scopes can be opened");
const boardView = ui.views.find(view => view.scope.kind === "board-occurrence");
const partView = ui.views.find(view => view.scope.kind === "assembly-part");
ui.setActiveViewId(boardView.id); ui = runner.render(base);
assert.equal(ui.activeRenderer.type, ScopedWorkspaceView);
assert.equal(ui.activeRenderer.props.toolbarHost,sharedToolbarHost,"scoped controls use the shared row without changing view ownership");
assert.equal(ui.activeRenderer.props.snapshot.targetBoards[0].id, "occ-A");
assert.equal(ui.activeRenderer.props.snapshot.showNetNames, true);
assert.deepEqual(ui.activeRenderer.props.snapshot.assemblyNetNameVisibility, { "occ-A": false });
assert.equal(ui.activeRenderer.props.snapshot.zoneDisplay, "transparent");
assert.deepEqual(ui.activeRenderer.props.snapshot.assemblyZoneDisplay, { "occ-A": "outline" }, "zone overrides stay occurrence scoped");
const viewportBeforeToggle = ui.activeRenderer.props.viewport;
const targetsBeforeToggle = ui.activeRenderer.props.snapshot.targetBoards;
ui = runner.render({ ...base, assemblyNetNameVisibility: { "occ-A": true, "occ-B": true } });
assert.deepEqual(ui.activeRenderer.props.snapshot.assemblyNetNameVisibility, { "occ-A": true }, "label changes invalidate scoped snapshot cache");
assert.equal(ui.activeRenderer.props.viewport, viewportBeforeToggle, "label changes reuse the geometry payload");
assert.equal(ui.activeRenderer.props.snapshot.targetBoards, targetsBeforeToggle, "label changes reuse scene occurrence inputs");
ui = runner.render({ ...base, zoneDisplay: "filled", assemblyZoneDisplay: { "occ-A": "transparent", "occ-B": "outline" } });
assert.equal(ui.activeRenderer.props.snapshot.zoneDisplay, "filled", "global zone changes invalidate the presentation snapshot");
assert.deepEqual(ui.activeRenderer.props.snapshot.assemblyZoneDisplay, { "occ-A": "transparent" });
assert.equal(ui.activeRenderer.props.viewport, viewportBeforeToggle, "zone changes reuse the geometry payload");
assert.equal(ui.activeRenderer.props.snapshot.targetBoards, targetsBeforeToggle, "zone changes reuse scene occurrence inputs");
ui.tabs.props.onMain(); ui = runner.render(base);
assert.equal(ui.activeViewId, null); assert.equal(ui.activeRenderer, null, "Main unmounts the scoped WebGL renderer");
ui.setActiveViewId(partView.id); ui = runner.render(base);
assert.equal(ui.activeRenderer.props.viewport.assemblyModels[0].partId, "lid");
ui.detachView(partView.id); ui = runner.render(base);
assert.equal(ui.activeRenderer, null, "detached active view is not also rendered in the owner");
const hosts = Array.isArray(ui.hosts.props.children) ? ui.hosts.props.children : [ui.hosts.props.children];
const host = hosts.find(child => child?.type === WorkspaceViewHost);
host.props.onDock(); ui = runner.render(base);
assert.equal(ui.views.find(view => view.id === partView.id).detached, false, "failed window creation redocks without deleting the descriptor");
ui.setActiveViewId(boardView.id); ui = runner.render(base);
ui.activeRenderer.props.onAction({ type: "select-net", occurrenceId: "occ-A", netId: "net-1" });
ui.activeRenderer.props.onAction({ type: "select-component", occurrenceId: "occ-A", componentId: "U1" });
ui.activeRenderer.props.onAction({ type: "select-net", occurrenceId: "occ-B", netId: "net-1" });
assert.deepEqual(actions.map(action => action.type), ["select-net", "select-component"], "only actions matching the fixed scope reach the owner");
assert.match(errors.at(-1), /fixed assembly view scope/);
ui.closeView(boardView.id); ui = runner.render(base);
assert.equal(ui.views.some(view => view.id === boardView.id), false, "closing a scope removes its renderer state");
ui = runner.render({ ...base, projectSession: "project-2" });
ui = runner.render({ ...base, projectSession: "project-2" });
assert.equal(ui.views.length, 0); assert.equal(ui.activeViewId, null); assert.ok(closeAllCalls >= 1, "project reset clears views and detached sessions");

const maxRunner = makeRunner();
const many = { ...base, occurrences: [], assemblyModels: [], parts: Array.from({ length: 9 }, (_, index) => ({ partId: `part-${index}`, title: `Part ${index}` })) };
let maxUi = maxRunner.render(many);
for (const candidate of [...maxUi.candidates]) { maxUi.addView(candidate); maxUi = maxRunner.render(many); }
assert.equal(maxUi.views.length, model.MAX_WORKSPACE_VIEWS);
assert.match(errors.at(-1), /At most 8/);

// Exercise the actual scoped selector props and disconnected dispatch gate.
const scopedSource = readFileSync(new URL("../src/ScopedWorkspaceView.tsx", import.meta.url), "utf8");
const scopedJs = ts.transpileModule(scopedSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const scopedModule = { exports: {} };
const analysisResults = await importTestTypescript("analysisResults");
const Selector = () => null;
const BoardViewport = () => null;
new Function("require", "module", "exports", scopedJs)(name => {
  if (name === "react") return { useState: initial => [typeof initial === "function" ? initial() : initial, () => {}], useRef: initial => ({ current: initial }), useMemo: factory => factory(), useEffect() {} };
  if (name === "react-dom") return { createPortal: node => node };
  if (name === "react/jsx-runtime") return nativeRequire(name);
  if (name === "./analysisResults") return analysisResults;
  if (name === "./appSettings") return { loadAppSettings: () => ({}) };
  if (name === "./icons") return { SlidersHorizontal: () => null, X: () => null };
  if (name === "./ViewportLayerSelector") return { __esModule: true, default: Selector };
  if (name === "./BoardViewport") return { __esModule: true, default: BoardViewport };
  if (name.endsWith(".css")) return {};
  return { __esModule: true, default: () => null };
}, scopedModule, scopedModule.exports);
function findSelector(node, component = Selector) {
  if (!node || typeof node !== "object") return null;
  if (node.type === component) return node;
  const children = node.props?.children;
  for (const child of Array.isArray(children) ? children.flat(Infinity) : [children]) {
    const found = findSelector(child, component); if (found) return found;
  }
  return null;
}
const selectorActions = [];
const selectorSnapshot = { ...base, descriptor: { id: "board-view", title: "Power board", scope: { kind: "board-occurrence", occurrenceId: "occ-A", designId: "design-A" }, viewMode: "3D", detached: false }, valid: true, targetBoards: [occurrence] };
const renderedViewport = findSelector(scopedModule.exports.default({ snapshot: selectorSnapshot,
  viewport: { boards: base.boards, revision: "viewport-1" }, connected: true, onAction() {} }), BoardViewport);
assert.equal(renderedViewport.props.zoneDisplay, "transparent");
assert.deepEqual(renderedViewport.props.assemblyZoneDisplay, base.assemblyZoneDisplay);
assert.equal(renderedViewport.props.selectedBoardInstanceId, "occ-A", "the renderer resolves the fixed occurrence override ahead of global zone mode");
const renderSelector = connected => findSelector(scopedModule.exports.default({ snapshot: selectorSnapshot, viewport: null, connected, onAction: action => selectorActions.push(action) }));
const selector = renderSelector(true);
assert.deepEqual(selector.props.board.opacity, { "F.Cu": .8 });
selector.props.onOpacity("occ-A", "F.Cu", .25);
selector.props.onAllOpacity("occ-A", .5);
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(selectorActions, [
  { type: "layer-opacity", occurrenceId: "occ-A", layer: "F.Cu", value: .25 },
  { type: "layer-opacity-all", occurrenceId: "occ-A", value: .5 },
]);
const disconnectedSelector = renderSelector(false);
assert.equal(disconnectedSelector.props.disabled, true);
disconnectedSelector.props.onOpacity("occ-A", "F.Cu", .7);
disconnectedSelector.props.onAllOpacity("occ-A", .7);
await new Promise(resolve => setImmediate(resolve));
assert.equal(selectorActions.length, 2, "disconnected views cannot send opacity changes even through callbacks");
console.log("workspace view hook harness: ok");
