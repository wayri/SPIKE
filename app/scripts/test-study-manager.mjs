// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";

const require = createRequire(import.meta.url);
const studiesModel = await importTestTypescript("simulationStudies");
const workspaceModel = await importTestTypescript("studyWorkspaceModel");
let cells = [], cell = 0;
const mockReact = { ...React,
  useState(initial) { const index = cell++; if (!(index in cells)) cells[index] = typeof initial === "function" ? initial() : initial; return [cells[index], value => { cells[index] = typeof value === "function" ? value(cells[index]) : value; }]; },
  useRef(initial) { const index = cell++; return cells[index] ??= { current: initial }; },
  useMemo(factory) { return factory(); }, useEffect() {},
};
const icon = () => null;
const icons = new Proxy({}, { get: () => icon });
const source = readFileSync(new URL("../src/StudyManager.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", compiled)(name => {
  if (name === "react") return mockReact;
  if (name === "lucide-react" || name === "./icons") return icons;
  if (name === "./simulationStudies") return studiesModel;
  if (name === "./studyWorkspaceModel") return workspaceModel;
  if (name === "./workerBridge") return { isDesktopShell: () => false, saveNativeTextFile: async () => null };
  if (name.endsWith(".css")) return {};
  return require(name);
}, module, module.exports);
const StudyManager = module.exports.default;
const run = (id, status = "completed") => ({ id, association: "workspace-capture", capturedAt: "2026-09-28T10:00:00.000Z", scenario: {}, settings: {}, facts: { contract: "fixture/v1", status, modelStatus: "not_validated", designId: "board", units: { voltage: "V" } }, resultSnapshot: { voltage: 1.2 } });
const studies = [{ version: 1, id: "visible", name: "RF enclosure", notes: "alpha", tags: ["antenna"], archived: false, datasets: [], cases: [
  { id: "active", type: "em", mode: "port sweep", name: "Baseline case", notes: "", scenario: {}, settings: {}, runs: [run("run-a"), run("run-b")], datasetIds: [] },
  { id: "inactive", type: "em", mode: "near field", name: "Inactive recovery", notes: "", scenario: {}, settings: {}, runs: [], datasetIds: [] },
] }, { version: 1, id: "archived", name: "Archived study", notes: "", tags: [], archived: true, datasets: [], cases: [] }];
const calls = [];
const props = { studies, currentType: "em", activeCaseId: "active", caseTypes: [{ value: "em", label: "Electromagnetics" }, { value: "pi", label: "Power integrity", disabled: true }],
  onCreateStudy: () => "new", onUpdateStudy: (...args) => calls.push(["study", ...args]), onRemoveStudy: (...args) => calls.push(["remove-study", ...args]),
  onAddCase: (...args) => calls.push(["add", ...args]), onUpdateCase: (...args) => calls.push(["case", ...args]), onDuplicateCase() {}, onRemoveCase: (...args) => calls.push(["remove-case", ...args]), onMoveCase() {}, onActivateCase() {}, onSaveCaseSetup() {}, onCaptureCaseResult() {}, onImportStudies: items => calls.push(["import", items]), onClose() {} };
function all(node) { if (Array.isArray(node)) return node.flatMap(all); if (!React.isValidElement(node)) return []; return [node, ...all(node.props.children)]; }
const text = node => Array.isArray(node) ? node.map(text).join("") : React.isValidElement(node) ? text(node.props.children) : typeof node === "string" || typeof node === "number" ? String(node) : "";
let tree; const render = () => { cell = 0; tree = StudyManager(props); return tree; };
const button = label => { const found = all(tree).find(node => node.type === "button" && (text(node).trim() === label || node.props["aria-label"] === label)); assert.ok(found, `button ${label}`); return found; };
const input = label => { const found = all(tree).find(node => node.type === "input" && node.props["aria-label"] === label); assert.ok(found, `input ${label}`); return found; };

render();
assert.ok(text(tree).includes("RF enclosure")); assert.ok(!text(tree).includes("Archived study"), "archived studies start hidden");
const typeOptions = all(tree).filter(node => node.type === "option");
assert.equal(typeOptions.find(node => node.props.value === "pi").props.disabled, true, "inactive product case types remain visible but disabled");
input("Search studies").props.onChange({ target: { value: "missing" } }); render();
assert.ok(text(tree).includes("No studies match this view."), "search exposes a clear empty result");
input("Search studies").props.onChange({ target: { value: "antenna" } }); render(); assert.ok(text(tree).includes("RF enclosure"));

const name = input("Study name"); calls.length = 0; name.props.onChange({ target: { value: "RF enclosure revision B" } });
assert.equal(calls.length, 0, "names are staged while typing"); render(); input("Study name").props.onBlur();
assert.equal(calls[0][0], "study"); assert.equal(calls[0][2].name, "RF enclosure revision B");

const inactiveRow = all(tree).find(node => node.props.role === "row" && text(node).includes("Inactive recovery")); assert.ok(inactiveRow); inactiveRow.props.onClick(); render();
assert.equal(button("Record snapshot").props.disabled, true, "snapshot recording is disabled for an inactive case");
button("Delete Inactive recovery").props.onClick(); render(); assert.ok(all(tree).some(node => node.props.role === "alertdialog"));
calls.length = 0; button("Delete case").props.onClick(); assert.deepEqual(calls, [["remove-case", "visible", "inactive"]], "confirmed case removal targets only the selected case");

render();
const datasetInput = input("Attach dataset file"); calls.length = 0;
await datasetInput.props.onChange({ target: { files: [{ name: "too-large.csv", type: "text/csv", size: 2 * 1024 * 1024 + 1, text: async () => "a\n1" }] } }); render();
assert.equal(calls.length, 0, "oversized dataset import does not mutate studies"); assert.ok(text(tree).includes("exceeds 2 MiB"));

props.studies[0].datasets = [{ id: "shared", name: "Shared CSV", kind: "csv", rawText: "f,v\n1,2", units: {}, provenance: "fixture", createdAt: "2026-09-28T10:00:00Z", resultDerived: false }];
button("Datasets").props.onClick(); render(); calls.length = 0;
button("Link Shared CSV").props.onClick();
assert.deepEqual(calls[0], ["case", "visible", "inactive", { datasetIds: ["shared"] }], "existing study data can be linked without reimporting");
props.studies[0].cases.find(item => item.id === "inactive").datasetIds = ["shared"];
render(); calls.length = 0; button("Unlink Shared CSV").props.onClick();
assert.deepEqual(calls[0][3], { datasetIds: [] });
assert.equal(props.studies[0].datasets.length, 1, "unlinking leaves the study dataset available");
render(); calls.length = 0; button("Remove Shared CSV").props.onClick(); render();
assert.equal(calls.length, 0, "dataset removal waits for confirmation");
button("Delete dataset").props.onClick();
assert.deepEqual(calls[0], ["study", "visible", { datasets: [] }], "confirmed removal targets the study attachment");

const csvBody = `value\n${"x".repeat(1_100_000)}\n`;
const importText = JSON.stringify({ version: 1, studies: [{ version: 1, id: "large", name: "Two legal attachments", notes: "", tags: [], archived: false, cases: [], datasets: [
  { id: "data-a", name: "a.csv", kind: "csv", mediaType: "text/csv", provenance: "fixture", units: {}, createdAt: "2026-09-28T10:00:00.000Z", resultDerived: false, rawText: csvBody },
  { id: "data-b", name: "b.csv", kind: "csv", mediaType: "text/csv", provenance: "fixture", units: {}, createdAt: "2026-09-28T10:00:00.000Z", resultDerived: false, rawText: csvBody },
] }] });
assert.ok(Buffer.byteLength(importText) > 2 * 1024 * 1024, "fixture exceeds the per-dataset limit as a complete study document");
calls.length = 0;
input("Import study JSON").props.onChange({ target: { files: [{ name: "large-study.json", size: Buffer.byteLength(importText), text: async () => importText }] } });
await new Promise(resolve => setTimeout(resolve, 0));
assert.equal(calls[0][0], "import"); assert.equal(calls[0][1][0].datasets.length, 2, "a legal multi-dataset study imports intact");

const sourceChecks = readFileSync(new URL("../src/StudyManager.tsx", import.meta.url), "utf8");
assert.match(sourceChecks, /comparisonCompatibility\(compared\)/);
assert.match(sourceChecks, /role="alertdialog"/);
assert.match(sourceChecks, /preflightStudyDatasetUpdate\(datasets, study\)/);
assert.match(sourceChecks, /preflightStudyDocument\(study\)/);
console.log("Study manager search, staged editing, disabled actions, targeted deletion, and bounded import assertions passed");
