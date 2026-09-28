import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const appRoot = resolve(import.meta.dirname, "..");
const app = readFileSync(resolve(appRoot, "src", "App.tsx"), "utf8");
const scene = readFileSync(resolve(appRoot, "src", "thermalScene.ts"), "utf8");

const requiredAppFragments = [
  'method: "validate_thermal"',
  'method: "prepare_thermal_case"',
  'method: "run_thermal_case"',
  'method: "estimate_thermal"',
  'engine_id: "external.openfoam"',
  "OPENFOAM CASE CONTROLS",
  "<ThermalHardwareEditor",
  "Potted block",
  "Vacuum disables convection",
  "Prepare a runnable OpenFOAM case before execution",
  "No result is marked validated here.",
  "Approximate independent RC sources only",
];

for (const fragment of requiredAppFragments) {
  if (!app.includes(fragment)) throw new Error(`Thermal workflow is missing: ${fragment}`);
}

if (!app.includes('disabled={busy !== null || !preparedCase?.can_run || activeBoundaries.length > 0}')) {
  throw new Error("OpenFOAM execution must remain gated by a prepared runnable case and unsupported surface boundaries");
}

for (const fragment of ["solver?:", "mesh?:", "run?:", "flow_rate_m3_s", "diameter_mm"]) {
  if (!scene.includes(fragment)) throw new Error(`Thermal viewport contract is missing: ${fragment}`);
}

console.log("thermal workflow UI contract passed");

// Exercise the actual wizard state and handlers with an isolated worker response.
// The worker's numerical correctness is covered by test_component_thermal.py.
const require = createRequire(import.meta.url);
const wizardSource = app.slice(app.indexOf("function ThermalWizard("), app.indexOf("function PiRunDialog("));
const compiled = ts.transpileModule(wizardSource, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const boundaryModule = { exports: {} };
new Function("require", "module", "exports", ts.transpileModule(readFileSync(resolve(appRoot, "src", "thermalBoundaries.ts"), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText)(require, boundaryModule, boundaryModule.exports);
const { normalizeThermalBoundaries, nativeThermalInputs } = boundaryModule.exports;
const emptyComponent = () => null;
function mountWizard(initialScenario, workerAvailable = true) {
  const states = [];
  let cursor = 0, saved, request;
  const dependencies = {
    require, exports: {},
    useState(initial) {
      const index = cursor++;
      if (!(index in states)) states[index] = typeof initial === "function" ? initial() : initial;
      return [states[index], value => { states[index] = typeof value === "function" ? value(states[index]) : value; }];
    },
    useMemo: callback => callback(), useEffect() {}, asThermalScenario: value => value,
    normalizeThermalElements: value => value ?? [], normalizeThermalLinks: value => value ?? [], normalizeThermalBoundaries, nativeThermalInputs,
    normalizeThermalFans: value => value ?? [], normalizeThermalHeatsinks: value => value ?? [],
    thermalAssemblyIssues: () => [], screenThermalElements: () => [], thermalSchematic: () => ({}),
    thermalMaterials: [], thermalSurfaceFinishes: [], WorkflowSchematic: emptyComponent,
    ThermalInputImport: emptyComponent, ThermalAssemblyEditor: emptyComponent, ThermalBoundaryEditor: emptyComponent, ThermalHardwareEditor: emptyComponent, ThermalEnvironmentPanel: emptyComponent, BoardThermalPanel: emptyComponent,
    ThermalTransientOverlay: emptyComponent,
    X: emptyComponent, Play: emptyComponent, AlertTriangle: emptyComponent,
    async runLocalWorker(value) {
      request = value;
      return { ok: true, result: { contract: "spike/component-thermal-result/v1", status: "completed", model_status: "approximate", nodes: [], transient: [], summary: {}, issues: [] } };
    },
  };
  const Wizard = new Function(...Object.keys(dependencies), `${compiled}\nreturn ThermalWizard;`)(...Object.values(dependencies));
  return {
    render() { cursor = 0; return Wizard({ initialScenario, componentBonds: [], board: null, design: null, workerAvailable,
      onRequireAdmission: async () => null, onClose() {}, onStatus() {}, onPreview() {}, onScenario(value) { saved = value; } }); },
    get saved() { return saved; }, get request() { return request; },
  };
}
function findNode(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) {
    const found = findNode(child, predicate);
    if (found) return found;
  }
  return null;
}
for (const thermal_elements of [[], [{ reference: "U1", kind: "pcb_component", enabled: true, power_w: 2, theta_top_c_per_w: 10, theta_bottom_c_per_w: 20, thermal_capacitance_j_per_c: 3, position: [0, 0, 0], dimensions_mm: { x: 1, y: 1, z: 1 } }]]) {
  const mounted = mountWizard({ mode: "transient", heat_sources: [{ power_w: 8, thermal_capacitance_j_per_c: 37 }], thermal_elements });
  const tree = mounted.render();
  const html = renderToStaticMarkup(tree);
  assert.ok(html.indexOf("Component transient duration") < html.indexOf("Optional OpenFOAM CFD"));
  const run = findNode(tree, node => node.type === "button" && node.props.className === "run-btn");
  assert.equal(run.props.disabled, false, "native runs need no board or OpenFOAM runtime");
  run.props.onClick();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(mounted.request.method, "run_component_thermal");
  if (!thermal_elements.length) assert.equal(mounted.request.params.components[0].thermal_capacitance_j_per_c, 37);
  assert.equal(mounted.saved.board_fallback_power_w, 8);
  const reopened = mountWizard(mounted.saved);
  assert.doesNotMatch(renderToStaticMarkup(reopened.render()), /Inputs changed/);
  const reopenedTree = reopened.render();
  findNode(reopenedTree, node => node.props?.["aria-label"] === "Component transient time step").props.onChange({ target: { value: "0.5" } });
  assert.match(renderToStaticMarkup(reopened.render()), /Inputs changed/);
}
const unavailable = mountWizard(null, false).render();
assert.equal(findNode(unavailable, node => node.type === "button" && node.props.className === "run-btn").props.disabled, true);
const coupled = mountWizard({ mode: "steady_state", thermal_elements: [
  { reference: "U1", kind: "pcb_component", enabled: true, power_w: 2, position: [0, 0, 0], dimensions_mm: { x: 2, y: 2, z: 1 } },
  { reference: "HS1", kind: "heatsink", enabled: true, power_w: 0, position: [0, 0, 0], dimensions_mm: { x: 10, y: 10, z: 2 } },
], thermal_boundaries: [
  { id: "contact", enabled: true, object_ref: "U1", surface: "+Z", kind: "conduction", target_ref: "HS1", resistance_c_per_w: 2 },
  { id: "air", enabled: true, object_ref: "HS1", surface: "whole", kind: "convection", area_mm2: 280, heat_transfer_coefficient_w_m2_k: 20 },
] });
const coupledTree = coupled.render();
assert.equal(findNode(coupledTree, node => node.props?.boundaries?.[0]?.id === "contact")?.props.elements.some(element => element.reference === "HS1"), true);
assert.equal(findNode(coupledTree, node => node.type === "button" && node.props.children === "Preflight")?.props.disabled, true, "optional CFD must not silently ignore object boundaries");
findNode(coupledTree, node => node.type === "button" && node.props.className === "run-btn").props.onClick();
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(coupled.request.params.components.map(item => item.component_ref), ["U1", "HS1"]);
assert.deepEqual(coupled.request.params.surfaces.map(item => item.id), ["contact", "air"]);
assert.equal(coupled.saved.thermal_boundaries.length, 2);
const coupledReopened = mountWizard(coupled.saved);
assert.doesNotMatch(renderToStaticMarkup(coupledReopened.render()), /Inputs changed/);
const boundaryEditor = findNode(coupledReopened.render(), node => node.props?.boundaries?.[0]?.id === "contact");
boundaryEditor.props.onBoundaries(boundaryEditor.props.boundaries.map(item => item.id === "air" ? { ...item, heat_transfer_coefficient_w_m2_k: 25 } : item));
assert.match(renderToStaticMarkup(coupledReopened.render()), /Inputs changed/);
const editorModule = { exports: {} };
const editorCode = ts.transpileModule(readFileSync(resolve(appRoot, "src", "ThermalBoundaryEditor.tsx"), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
new Function("require", "module", "exports", editorCode)(name => name === "react" ? { useState: initial => [initial, () => {}] } : name === "./thermalBoundaries" ? boundaryModule.exports : name === "lucide-react" ? { Plus: emptyComponent, Trash2: emptyComponent } : require(name), editorModule, editorModule.exports);
const Editor = editorModule.exports.default;
const boardObject = { id: "board", reference: "BOARD", kind: "board", enabled: true, emissivity: 0.8, dimensions_mm: { x: 10, y: 20, z: 2 } };
let editedBoundaries = [];
const editBoundaries = boundaries => { editedBoundaries = boundaries; };
let editorTree = Editor({ elements: [boardObject], boundaries: editedBoundaries, onBoundaries: editBoundaries });
findNode(editorTree, node => node.type === "button" && Array.isArray(node.props.children) && node.props.children.includes(" Add boundary")).props.onClick();
assert.equal(editedBoundaries[0].area_mm2, 520);
editorTree = Editor({ elements: [boardObject], boundaries: editedBoundaries, onBoundaries: editBoundaries });
findNode(editorTree, node => node.type === "select" && node.props.value === "whole").props.onChange({ target: { value: "+X" } });
assert.equal(editedBoundaries[0].area_mm2, 40, "selected face area is suggested from dimensions");
editorTree = Editor({ elements: [boardObject], boundaries: editedBoundaries, onBoundaries: editBoundaries });
findNode(editorTree, node => node.type === "select" && node.props.value === "+X").props.onChange({ target: { value: "custom" } });
assert.equal(editedBoundaries[0].area_mm2, undefined, "named CAD surfaces require an explicit measured area");
assert.equal(editedBoundaries[0].surface, "", "unnamed CAD surfaces must remain invalid until named");
editorTree = Editor({ elements: [boardObject], boundaries: editedBoundaries, onBoundaries: editBoundaries });
findNode(editorTree, node => node.type === "input" && node.props["aria-label"] === "Boundary 1 surface name").props.onChange({ target: { value: "fin-outer-7" } });
assert.equal(editedBoundaries[0].surface, "fin-outer-7");
console.log("Thermal wizard native run, transient controls, save/reopen, stale-result and unavailable-worker checks passed.");
