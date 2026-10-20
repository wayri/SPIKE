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

console.log("workspace view hook harness: ok");
