// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import ts from "typescript";

const require = createRequire(import.meta.url);
const icon = () => null;
const icons = new Proxy({}, { get: () => icon });

function loadComponent(name, mocks = {}) {
  const source = readFileSync(new URL(`../src/${name}.tsx`, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const module = { exports: {} };
  new Function("require", "module", "exports", compiled)(specifier => {
    if (specifier === "./icons") return icons;
    if (specifier.endsWith(".css")) return {};
    if (specifier in mocks) return mocks[specifier];
    return require(specifier);
  }, module, module.exports);
  return module.exports.default;
}

function descendants(node) {
  if (Array.isArray(node)) return node.flatMap(descendants);
  if (!React.isValidElement(node)) return [];
  if (typeof node.type === "function") return descendants(node.type(node.props));
  return [node, ...descendants(node.props.children)];
}

function label(node) {
  if (Array.isArray(node)) return node.map(label).join("");
  if (React.isValidElement(node)) return typeof node.type === "function" ? label(node.type(node.props)) : label(node.props.children);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}

function findButton(tree, text) {
  const buttons = descendants(tree).filter(node => node.type === "button");
  const result = buttons.find(node => label(node).trim() === text) ?? buttons.find(node => label(node).trim().startsWith(text));
  assert.ok(result, `button ${text}`);
  return result;
}

const ProjectManager = loadComponent("ProjectManager");
const projectCalls = [];
const projectProps = {
  projectName: "charger-controller-revision-c.spike",
  projectPath: "C:/designs/charger-controller-revision-c.spike",
  boardFile: "charger-controller-revision-c.kicad_pcb",
  counts: { layers: 8, nets: 144, components: 312, results: 4 },
  recent: [{ name: "Revision C", path: "C:/designs/revision-c.spike", openedAt: "2026-10-14T10:00:00Z" }],
  onNew: () => projectCalls.push("new"), onOpen: () => projectCalls.push("open"), onImport: () => projectCalls.push("import"),
  onSave: () => projectCalls.push("save"), onSaveAs: () => projectCalls.push("save-as"), onSaveWithoutResults: () => projectCalls.push("project-only"),
  onSaveResultsFile: () => projectCalls.push("results"), onStudies: () => projectCalls.push("studies"), onClose: () => projectCalls.push("close"),
};
const projectTree = ProjectManager(projectProps);
for (const [buttonText, call] of [["New project", "new"], ["Open", "open"], ["Import CAD", "import"], ["Studies", "studies"], ["Save", "save"], ["Save as", "save-as"], ["Project only", "project-only"], ["Results file", "results"]]) {
  findButton(projectTree, buttonText).props.onClick();
  assert.equal(projectCalls.at(-1), call, `${buttonText} keeps its action callback`);
}
assert.ok(descendants(projectTree).some(node => node.type === "button" && node.props["aria-label"] === "Close Project manager"), "Project manager has an accessible close control");
assert.ok(label(projectTree).includes("144 nets"), "project metadata remains visible");

let hookCells = [];
let hookIndex = 0;
const mockReact = { ...React,
  useState(initial) { const index = hookIndex++; if (!(index in hookCells)) hookCells[index] = typeof initial === "function" ? initial() : initial; return [hookCells[index], value => { hookCells[index] = typeof value === "function" ? value(hookCells[index]) : value; }]; },
  useMemo(factory) { return factory(); },
  useEffect() {},
};
let catalogProps;
const previewCalls = [];
const NetManager = loadComponent("NetManager", {
  react: mockReact,
  "./BoardViewport": { previewViewportTarget: value => previewCalls.push(value) },
  "./copperLayerSelection": { resolveBoardCopperLayers: (_layers, names) => names },
  "./NetCatalog": { default: props => { catalogProps = props; return React.createElement("div", { "data-net-catalog": true }); } },
});
const netCalls = [];
const board = {
  nets: { 1: "VCC_MAIN_LONG_NAME", 2: "GND" }, layers: ["F.Cu", "B.Cu"], tracks: [], vias: [], zones: [], components: [],
  pads: [{ id: "pad-1", net: "VCC_MAIN_LONG_NAME", ref: "U1", name: "1", at: [1, 2], layers: ["F.Cu"], layer: "F.Cu" }],
};
const netProps = {
  board, selectedNet: "VCC_MAIN_LONG_NAME", managedNets: [], setManagedNets: nets => netCalls.push(["nets", nets]),
  loopExtractions: [], setLoopExtractions: loops => netCalls.push(["loops", loops]), pathGroups: [],
  onSelectNet: net => netCalls.push(["select", net]), onOpenPowerPaths: () => netCalls.push(["tree"]),
  onOpenSeriesAnalysis: () => netCalls.push(["analyze"]), onStatus: status => netCalls.push(["status", status]), onClose: () => netCalls.push(["close"]),
};
const renderNet = () => { hookIndex = 0; const tree = NetManager(netProps); descendants(tree); return tree; };
let netTree = renderNet();
assert.deepEqual(catalogProps.rows.map(row => row.name), ["GND", "VCC_MAIN_LONG_NAME"], "imported catalog remains complete and naturally sorted");
findButton(netTree, "Use selected").props.onClick();
assert.deepEqual(netCalls[0], ["nets", ["VCC_MAIN_LONG_NAME"]], "viewport selection keeps the source-role assignment flow");
const role = catalogProps.role("GND");
role.props.onChange({ target: { value: "return" } });
assert.ok(netCalls.some(call => call[0] === "nets" && call[1].includes("GND")), "catalog role control remains interactive");
findButton(netTree, "Power tree").props.onClick();
assert.deepEqual(netCalls.at(-1), ["tree"], "Power tree action remains wired");
findButton(netTree, "Loop RLC").props.onClick();
netTree = renderNet();
findButton(netTree, "Add loop").props.onClick();
assert.ok(netCalls.some(call => call[0] === "loops" && call[1].length === 1), "loop creation remains available in the compact view");

const projectCss = readFileSync(new URL("../src/projectManager.css", import.meta.url), "utf8");
const netCss = readFileSync(new URL("../src/netManager.css", import.meta.url), "utf8");
assert.match(projectCss, /container:\s*project-manager\s*\/\s*inline-size/);
assert.match(projectCss, /@container project-manager \(max-width: 380px\)/);
assert.match(projectCss, /\.project-action-list\s*\{[^}]*repeat\(2, minmax\(0, 1fr\)\)/s);
assert.match(netCss, /container:\s*net-manager\s*\/\s*inline-size/);
assert.match(netCss, /@container net-manager \(max-width: 680px\)/);
assert.match(netCss, /table\.net-table > tbody > tr[^\{]*\{[^}]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/s);
assert.match(netCss, /td:nth-child\(8\)::before\s*\{\s*content:\s*"Parts"/);
assert.doesNotMatch(netCss, /minmax\(560px/);

console.log("Responsive Project and Net manager actions, role assignment, loop creation, and narrow container contracts passed");
