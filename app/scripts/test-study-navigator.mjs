// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
const require = createRequire(import.meta.url);
const source = readFileSync(new URL("../src/StudyNavigator.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const Icon = props => React.createElement("svg", props);
const icons = new Proxy({}, { get: () => Icon });
function load(react) {
  const module = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => name === "react" ? react : name === "./icons" ? icons : name.endsWith(".css") ? {} : require(name), module, module.exports);
  return module.exports.default;
}
const embeddedRun = { id: "run-1", association: "workspace-capture", capturedAt: "2026-10-10T09:00:00Z", caseType: "thermal", mode: "steady", scenario: {}, settings: {}, facts: { status: "completed", modelStatus: "approximate" }, resultSnapshot: { temperature: 42 } };
const externalRun = { ...embeddedRun, id: "run-2", facts: {}, resultSnapshot: undefined, resultRef: "results/external.json" };
const setupRun = { ...externalRun, id: "run-3", resultSnapshot: null, resultRef: undefined };
const item = { id: "case-a", type: "thermal", mode: "steady", name: "Warm ambient with unusually long fixture and enclosure description", notes: "", scenario: {}, settings: {}, resultSnapshot: { temperature: 42 }, runs: [embeddedRun, externalRun, setupRun], datasetIds: [] };
const externalCase = { ...item, id: "case-b", name: "Referenced case", resultSnapshot: null, resultRef: "case-result.json", runs: [] };
const study = { version: 1, id: "study-a", name: "Thermal enclosure study with a long name", notes: "", tags: [], archived: false, cases: [item, externalCase], datasets: [] };
const archived = { ...study, id: "study-archived", name: "Archived investigation", archived: true, cases: [] };
const events = [];
const props = { studies: [study, archived], activeCaseId: item.id, docked: true, projectResults: [{ id: "project-a", name: "Board result outside any study", detail: "Approximate saved payload", onOpen: () => events.push("project") }], onActivateCase: (id, value) => events.push(["case", id, value]), onOpenRun: (id, value, run) => events.push(["run", id, value, run]), onManage: () => events.push("manage"), onClose: () => events.push("close"), onFloat: () => events.push("float"), onDock: () => events.push("dock") };
const html = renderToStaticMarkup(React.createElement(load(React), props));
assert.match(html, /role="tree"/);
assert.match(html, /aria-level="3"/);
assert.doesNotMatch(html, /aria-level="4"|Recorded runs/);
assert.match(html, /Saved case result/);
assert.match(html, /External result - locate required/, "null case snapshot with a reference requires locating its payload");
const nullOnly = renderToStaticMarkup(React.createElement(load(React), { ...props, projectResults: [], studies: [{ ...study, cases: [{ ...item, resultSnapshot: null, runs: [] }] }] }));
assert.doesNotMatch(nullOnly, /Saved case result|Embedded captured payload/, "null snapshots cannot be presented as retained results");
assert.match(html, /Locate required: external payload is not embedded/);
assert.match(html, /Setup capture only; no result payload/);
assert.match(html, /approximate/);
assert.match(html, /Board result outside any study/);
assert.doesNotMatch(html, /Archived investigation/);
const empty = renderToStaticMarkup(React.createElement(load(React), { ...props, studies: [], projectResults: [] }));
assert.match(empty, /Use Manage studies/);
const values = [], refs = [];
let stateCursor = 0, refCursor = 0;
const hookReact = {
  useMemo: fn => fn(),
  useRef: initial => refs[refCursor++] ?? (refs[refCursor - 1] = { current: initial }),
  useState: initial => { const index = stateCursor++; if (!(index in values)) values[index] = typeof initial === "function" ? initial() : initial; return [values[index], value => { values[index] = typeof value === "function" ? value(values[index]) : value; }]; },
};
const Navigator = load(hookReact);
let currentProps = props;
const mount = () => { stateCursor = 0; refCursor = 0; return Navigator(currentProps); };
function all(element, predicate) {
  if (!element || typeof element !== "object") return [];
  if (Array.isArray(element)) return element.flatMap(child => all(child, predicate));
  return [...(predicate(element) ? [element] : []), ...all(element.props?.children, predicate)];
}
const treeRows = () => all(mount(), element => element.props?.role === "treeitem");
const row = text => treeRows().find(element => element.props["aria-label"].startsWith(text));
const click = element => { element.props.onClick({ detail: 1 }); element.props.onClick({ detail: 2 }); };
click(row(item.name));
assert.deepEqual(events.shift(), ["case", study.id, item]);
click(row("Saved case result"));
assert.deepEqual(events.shift(), ["case", study.id, item]);
click(row("Capture 1"));
assert.deepEqual(events.shift(), ["run", study.id, item, embeddedRun]);
click(row("Capture 2"));
assert.deepEqual(events.shift(), ["run", study.id, item, externalRun], "missing external payload is passed unchanged for admission/recovery");
click(row("Board result outside"));
assert.equal(events.shift(), "project");
assert.deepEqual(events, [], "second click of a double click must not repeat any open callback");
const focused = [];
for (const element of treeRows()) element.ref({ focus: () => focused.push(element.props["aria-label"]) });
function keyPress(element, key, repeat = false) {
  const target = {}; let prevented = false;
  element.props.onKeyDown({ key, repeat, target, currentTarget: target, preventDefault() { prevented = true; }, stopPropagation() {} });
  assert.equal(prevented, true);
}
keyPress(row(item.name), "ArrowRight");
assert.match(focused.pop(), /^Saved case result/);
keyPress(row("Saved case result"), "ArrowLeft");
assert.match(focused.pop(), new RegExp(`^${item.name}`));
keyPress(row(item.name), "ArrowLeft");
assert.equal(row("Saved case result"), undefined, "ArrowLeft collapses expanded case");
keyPress(row(item.name), "ArrowRight");
assert.ok(row("Saved case result"), "ArrowRight expands case");
keyPress(row("Saved case result"), "Enter");
keyPress(row("Saved case result"), "Enter", true);
assert.equal(events.length, 1, "held Enter must not repeat an open action");
events.length = 0;
const search = all(mount(), element => element.props?.["aria-label"] === "Search studies and results")[0];
search.props.onChange({ target: { value: "outside" } });
assert.equal(treeRows().length, 2, "search preserves only matching result and its parent branch");
search.props.onChange({ target: { value: "zzzz absent" } });
assert.equal(treeRows().length, 0);
assert.ok(all(mount(), element => element.props?.role === "status").length);
search.props.onChange({ target: { value: "" } });
all(mount(), element => element.type === "input" && element.props.type === "checkbox")[0].props.onChange({ target: { checked: true } });
assert.ok(row("Archived investigation"));
const button = name => all(mount(), element => element.type === "button" && element.props["aria-label"] === name)[0];
button("Float study navigator").props.onClick();
button("Close study navigator").props.onClick();
currentProps = { ...props, docked: false };
button("Dock study navigator").props.onClick();
assert.deepEqual(events, ["float", "close", "dock"]);
assert.equal(treeRows().filter(element => element.props.tabIndex === 0).length, 1, "one visible item participates in tab navigation");
console.log("Study navigator: hierarchy, exact callbacks, double clicks, arrow keys, search, archives, absent payloads and docking passed.");
