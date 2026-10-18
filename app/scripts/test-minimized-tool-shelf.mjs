// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";

const registry = await importTestTypescript("minimizedTools");
const changes = [];
const stop = registry.subscribeMinimizedTools(items => changes.push(items.map(item => item.id)));
const actions = [];
registry.minimizeTool({ id: "board-nets", label: "Board nets", restore: () => actions.push("restore-nets") });
registry.minimizeTool({ id: "em-results", label: "EM results", restore: () => actions.push("restore-em"), close: () => actions.push("close-em") });
assert.deepEqual(registry.minimizedToolSnapshot().map(item => item.id), ["board-nets", "em-results"], "multiple minimized tools retain stable order");
registry.minimizeTool({ id: "board-nets", label: "Controller board nets", restore: () => actions.push("restore-renamed") });
assert.equal(registry.minimizedToolSnapshot()[0].label, "Controller board nets", "a mounted minimized tool can refresh its bounded label");
await registry.restoreMinimizedTool("board-nets");
assert.deepEqual(actions, ["restore-renamed"]);
assert.deepEqual(registry.minimizedToolSnapshot().map(item => item.id), ["em-results"], "restore removes the shelf item before reopening the tool");
await registry.closeMinimizedTool("em-results");
assert.deepEqual(actions, ["restore-renamed", "close-em"]);
assert.equal(registry.minimizedToolSnapshot().length, 0, "close removes the minimized tool");
registry.minimizeTool({ id: "restore-failure", label: "Restore failure", restore: async () => { throw new Error("native focus failed"); } });
await assert.rejects(registry.restoreMinimizedTool("restore-failure"), /native focus failed/);
assert.equal(registry.minimizedToolSnapshot()[0].id, "restore-failure", "a rejected restore puts its action back in the shelf");
registry.removeMinimizedTool("restore-failure");
registry.minimizeTool({ id: "close-failure", label: "Close failure", restore() {}, close: async () => { throw new Error("native close failed"); } });
await assert.rejects(registry.closeMinimizedTool("close-failure"), /native close failed/);
assert.equal(registry.minimizedToolSnapshot()[0].id, "close-failure", "a rejected close keeps its action available");
registry.removeMinimizedTool("close-failure");
stop();
assert.ok(changes.some(ids => ids.length === 2), "subscribers receive simultaneous minimized state");
assert.equal(registry.minimizeTool({ id: "orphan", label: "Orphan", restore() {} }), false, "standalone fixtures cannot enter an unreachable minimized state");
assert.equal(registry.minimizedToolSnapshot().length, 0);

const shelfSource = readFileSync(new URL("../src/ToolRestoreShelf.tsx", import.meta.url), "utf8");
const shelfJs = ts.transpileModule(shelfSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const restored = [], closed = [];
const registered = { id: "registered", label: "A very long minimized tool label", restore() {}, close() {} };
const react = { ...React, useState(initial) { return [typeof initial === "function" ? initial() : initial, () => {}]; }, useEffect() {}, useMemo: fn => fn() };
const module = { exports: {} };
const require = createRequire(import.meta.url);
new Function("require", "module", "exports", shelfJs)(name => {
  if (name === "react") return react;
  if (name === "react/jsx-runtime") return { jsx: (type, props, key) => React.createElement(type, key === undefined ? props : { ...props, key }), jsxs: (type, props, key) => React.createElement(type, key === undefined ? props : { ...props, key }), Fragment: React.Fragment };
  if (name === "./navigationIcons") return { ShowControlIcon: () => null, CloseControlIcon: () => null };
  if (name === "./minimizedTools") return {
    minimizedToolSnapshot: () => [registered], subscribeMinimizedTools: () => () => {},
    restoreMinimizedTool: id => restored.push(id), closeMinimizedTool: id => closed.push(id),
  };
  if (name.endsWith(".css")) return {};
  return require(name);
}, module, module.exports);
const tree = module.exports.default({ items: [{ id: "window", label: "Detached results", restore: () => restored.push("window"), close: () => closed.push("window") }] });
function elements(node) { return React.isValidElement(node) ? [node, ...React.Children.toArray(node.props.children).flatMap(elements)] : []; }
const buttons = elements(tree).filter(node => node.type === "button");
assert.deepEqual(buttons.map(button => button.props["aria-label"]), ["Restore A very long minimized tool label", "Close A very long minimized tool label", "Restore Detached results", "Close Detached results"]);
buttons.forEach(button => button.props.onClick());
assert.deepEqual(restored, ["registered", "window"]);
assert.deepEqual(closed, ["registered", "window"]);
const errors = [];
const failedTree = module.exports.default({ items: [{ id: "failure", label: "Failure window", restore: async () => { throw new Error("focus denied"); } }], onError: message => errors.push(message) });
elements(failedTree).find(node => node.type === "button" && node.props["aria-label"] === "Restore Failure window").props.onClick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(errors.length, 1);
assert.match(errors[0], /\[SPIKE-FE-APP-E-0001\] Could not restore Failure window: focus denied/,
  "direct detached-window restore failures reach visible workspace status with a registered error code");
assert.match(errors[0], /Retry from the bottom bar/);

const css = readFileSync(new URL("../src/toolRestoreShelf.css", import.meta.url), "utf8");
assert.match(css, /max-width: min\(46vw, 560px\)/, "wide shelf remains bounded");
assert.match(css, /overflow-x: auto/, "multiple tools remain reachable without covering the viewport");
assert.match(css, /@media \(max-width: 760px\)/, "narrow widths use compact restore controls");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
assert.match(app, /<ToolRestoreShelf items=\{toolRestoreItems\}/);
assert.match(app, /detachedToolLabels/);
assert.match(app, /assembly-workspace-window/);
assert.match(app, /report-preview-window/);
assert.match(app, /workspace-tool-minimized/);
assert.match(app, /if \((?:quickRun \|\| )?panelCollapsed\) return null;/, "minimized PI setup no longer occupies a viewport edge");
assert.doesNotMatch(app, /classList\.toggle\("panel-collapsed"\)/, "generic panels no longer leave collapsed floating pills");
const emManager = readFileSync(new URL("../src/EMViewportResultManager.tsx", import.meta.url), "utf8");
assert.match(emManager, /if \(minimized\) return null;/);
assert.match(emManager, /minimizeTool\(\{ id: shelfId/);
const detached = readFileSync(new URL("../src/detachedToolWindows.tsx", import.meta.url), "utf8");
assert.match(detached, /await current\.unminimize\(\);\s*await current\.show\(\);\s*await current\.setFocus\(\)/, "restore unminimizes native detached windows before focusing them");
console.log("Minimized tool registry, restore/close controls, multiple entries, detached window restore and narrow shelf constraints passed");
