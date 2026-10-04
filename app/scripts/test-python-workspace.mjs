// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { webcrypto } from "node:crypto";
import React from "react";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";

globalThis.crypto ??= webcrypto;
const storage = new Map();
globalThis.sessionStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
const localStorageValues = new Map();
globalThis.localStorage = { getItem: key => localStorageValues.get(key) ?? null, setItem: (key, value) => localStorageValues.set(key, String(value)) };
globalThis.window = { innerWidth: 1440, innerHeight: 900, addEventListener() {}, removeEventListener() {}, setTimeout };
const model = await importTestTypescript("pythonWorkspaceModel");
const templates = await importTestTypescript("pythonWorkspaceTemplates");
const workspaceContext = await importTestTypescript("pythonWorkspaceContext");
const floatingWindow = await importTestTypescript("pythonFloatingWindow");
const geometryPreview = await importTestTypescript("emergeGeometryPreview");
const scriptDataViews = await importTestTypescript("scriptDataViews");
const viewportModel = await importTestTypescript("scriptResultViewportModel");
assert.equal(model.pythonParent("C:\\a.py"), "C:\\");
assert.equal(model.pythonParent("/a.py"), "/");
assert.equal(model.pythonPathKey("C:\\Scripts\\Run.py"), model.pythonPathKey("c:/scripts/run.py"));
assert.equal(model.pythonAbsolutePath("C:\\scripts", "sub/test.py"), "C:\\scripts/sub/test.py");
assert.equal(model.pythonRelativePath("C:\\scripts", "C:/scripts/sub/Test.py"), "sub/Test.py");
assert.throws(() => model.pythonRelativePath("C:/scripts", "C:/scripts-other/a.py"));
assert.deepEqual(model.togglePythonBreakpoint([3], 2, 5), [2, 3]);
assert.deepEqual(model.togglePythonBreakpoint([2, 3], 2, 5), [3]);
assert.deepEqual(model.remapPythonBreakpoints("a\nb\nc", "intro\na\nb\nc", [2, 3]), [3, 4]);
assert.deepEqual(model.remapPythonBreakpoints("a\nb\nc", "a\nc", [2, 3]), [2], "deleted line loses its breakpoint; suffix follows source");
const snapshot = model.newPythonDocument("print(1)");
const changedWhileSaving = { ...snapshot, code: "print(2)" };
const saved = model.savedPythonDocument(changedWhileSaving, { code: snapshot.code, path: "C:/scripts/a.py", root: "C:/scripts", sha256: "hash" });
assert.equal(saved.code, "print(2)"); assert.equal(model.pythonDirty(saved), true, "saving an older snapshot does not discard newer edits");
model.persistPythonWorkspace({ documents: [saved], activeId: saved.id, root: "C:/scripts" });
assert.deepEqual(model.restorePythonWorkspace("starter").documents[0], saved);
storage.clear();

const require = createRequire(import.meta.url);
let cells = [], cell = 0, desktop = true, requests = [], nativeFile = null, savePath = "C:/scripts/copy.py", workerError = false, closed = 0, debugPending = false, writeGate = null;
let runGate = null, scriptResult = { contract: "spike/python-script-result/v1", status: "completed", stdout: "ran", return_code: 0 }, workspaceProps = {};
const interfaceActions = [];
const mockReact = { ...React,
  useState(initial) { const index = cell++; if (!(index in cells)) cells[index] = typeof initial === "function" ? initial() : initial; return [cells[index], value => { cells[index] = typeof value === "function" ? value(cells[index]) : value; }]; },
  useRef(initial) { const index = cell++; return cells[index] ??= { current: initial }; },
  useEffect() {}, useMemo: factory => factory(),
};
const stubs = Object.fromEntries(["PythonCodeEditor", "PythonDebugPanel", "PythonFileExplorer", "PythonTemplateLibrary", "PythonWorkspaceHelp", "PythonRecoveryPanel", "PythonNetBrowser", "PythonRunStatus"].map(name => [name, function Stub() { return null; }]));
const bridge = {
  isDesktopShell: () => desktop,
  openNativeTextFile: async () => nativeFile,
  saveNativeTextFile: async (...args) => { requests.push({ method: "save_as", args }); return savePath; },
  selectNativeImportFile: async () => ({ path: "C:/scripts", fileName: "scripts" }),
  cancelLocalWorker: async () => true, cancelLocalWorkerCleanup: async () => true,
  runLocalWorker: async request => {
    requests.push(request);
    if (request.method === "python_workspace_files" && request.params.action === "write" && writeGate) await writeGate;
    if (request.method === "python_workspace_files") return workerError ? { ok: false, error: "File changed outside SPIKE" } : { ok: true, result: request.params.action === "read" ? { root: request.params.root, path: request.params.path, contents: "print('helper')", sha256: "filehash" } : { sha256: "newhash" } };
    if (request.method === "start_python_debug") return { ok: true, result: { contract: "spike/python-debug/v1", session_id: "session", status: "paused", line: 1, filename: "C:/scripts/test.py", frames: [{ name: "<module>", line: 1, filename: "C:/scripts/test.py", locals: {} }] } };
    if (request.method === "python_debug_command") return { ok: true, result: { contract: "spike/python-debug/v1", session_id: "session", status: request.params.command === "stop" ? "stopped" : "paused", line: 2, filename: "C:/scripts/test.py", ...(debugPending && request.params.command !== "stop" ? { command_pending: 2, command_sequence: 2 } : {}) } };
    if (request.method === "run_python_script" && runGate) await runGate;
    return { ok: true, result: scriptResult };
  },
};
const compiled = ts.transpileModule(readFileSync(new URL("../src/PythonWorkspace.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", compiled)(name => {
  if (name === "react") return mockReact;
  if (name === "./icons") return require("lucide-react");
  if (name.endsWith(".css")) return {};
  if (name === "./workerBridge") return bridge;
  if (name === "./pythonWorkspaceContext") return workspaceContext;
  if (name === "./pythonWorkspaceModel") return model;
  if (name === "./pythonWorkspaceTemplates") return templates;
  if (name === "./pythonFloatingWindow") return floatingWindow;
  if (name === "./emergeGeometryPreview") return geometryPreview;
  if (name === "./scriptDataViews") return scriptDataViews;
  if (name === "./scriptResultViewportModel") return viewportModel;
  if (name === "./extensionAnalysisResult") return { extensionAnalysisResult: () => null };
  if (name.slice(2) in stubs) return { default: stubs[name.slice(2)] };
  return require(name);
}, module, module.exports);
const Workspace = module.exports.default;
function elements(node) { if (Array.isArray(node)) return node.flatMap(elements); if (!React.isValidElement(node)) return []; return [node, ...elements(node.props.children)]; }
const content = node => Array.isArray(node) ? node.map(content).join("") : React.isValidElement(node) ? content(node.props.children) : typeof node === "string" || typeof node === "number" ? String(node) : "";
let tree;
const render = () => { cell = 0; tree = Workspace({ design: null, results: null, onClose: () => closed++, onStatus() {}, onUiAction: action => interfaceActions.push(action), ...workspaceProps }); return tree; };
const button = label => { const found = elements(tree).find(node => node.type === "button" && (content(node).trim() === label || node.props["aria-label"] === label)); assert.ok(found, `button ${label} exists`); return found; };
const editor = () => elements(tree).find(node => node.type === stubs.PythonCodeEditor);
const interpreter = () => elements(tree).find(node => node.type === "input" && node.props["aria-label"] === "Python interpreter path");
const tabs = () => elements(tree).filter(node => node.props.role === "tab");
const flush = async (until = () => true) => {
  for (let attempt = 0; attempt < 100; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 10)); render();
    if (until()) return;
  }
  throw new Error("Asynchronous workspace action did not settle");
};

render(); assert.equal(tabs().length, 1);
assert.equal(interpreter().props.value, "", "worker default remains the initial interpreter");
interpreter().props.onChange({ target: { value: "C:/Python/python.exe" } }); render();
assert.equal(localStorageValues.get("spike-python-interpreter"), "C:/Python/python.exe");
assert.equal(button("Debug").props.disabled, true, "external interpreters do not silently enter the worker-default debugger");
interpreter().props.onChange({ target: { value: "" } }); render();
button("Add Python tab").props.onClick(); render(); assert.equal(tabs().length, 2);
button("Close untitled-2.py").props.onClick(); render(); assert.equal(tabs().length, 1);
const workspaceDialog = () => elements(tree).find(node => node.props.role === "dialog");
let stopped = false, prevented = false;
workspaceDialog().props.onKeyDown({ key: "c", ctrlKey: true, metaKey: false, stopPropagation() { stopped = true; }, preventDefault() { prevented = true; } });
assert.equal(stopped, true, "editor keys do not reach the main window's project/copy handlers");
assert.equal(prevented, false, "ordinary copy/paste keep the editor's default behavior");
button("New").props.onClick(); render(); assert.equal(tabs().length, 2);
editor().props.onChange("print('changed')"); render(); assert.ok(content(tree).includes("●"));
button("Close untitled-2.py").props.onClick(); render(); assert.ok(elements(tree).some(node => node.props.role === "alertdialog"));
button("Cancel").props.onClick(); render(); assert.equal(tabs().length, 2);
button("Close untitled-2.py").props.onClick(); render(); await button("Discard edits").props.onClick(); render(); assert.equal(tabs().length, 1);

nativeFile = { path: "C:/scripts/test.py", fileName: "test.py", contents: "value = 1\nprint(value)\n" };
button("Open").props.onClick(); await flush(() => tabs().length === 2); assert.equal(tabs().length, 2);
button("Open").props.onClick(); await flush(); assert.equal(tabs().length, 2, "opening an existing path activates its tab instead of replacing unsaved buffers");
editor().props.onChange("value = 2\nprint(value)\n"); render();
requests.length = 0; button("Save").props.onClick(); await flush();
assert.equal(requests[0].method, "python_workspace_files"); assert.equal(requests[0].params.action, "write"); assert.equal(requests[0].params.path, "test.py"); assert.equal(requests[0].params.expected_sha256.length, 64);
assert.ok(!content(tabs()[1]).includes("●"));
let releaseWrite;
writeGate = new Promise(resolve => { releaseWrite = resolve; });
editor().props.onChange("value = 20\n"); render();
button("Save").props.onClick(); render(); assert.ok(content(tabs()[1]).includes("Saving…"));
assert.equal(button("Close test.py").props.disabled, true);
editor().props.onChange("value = 21\n"); render(); releaseWrite(); writeGate = null; await flush();
assert.equal(editor().props.code, "value = 21\n"); assert.ok(content(tabs()[1]).includes("Unsaved"), "edits typed during save remain unsaved and are not overwritten");
editor().props.onChange("value = 3\n"); render(); workerError = true;
button("Save").props.onClick(); await flush(); assert.ok(content(tree).includes("File changed outside SPIKE")); assert.ok(content(tabs()[1]).includes("●")); assert.ok(content(tabs()[1]).includes("Save failed")); workerError = false;
requests.length = 0; button("Save as").props.onClick(); await flush(() => content(tabs()[1]).includes("copy.py")); assert.equal(requests[0].method, "save_as"); assert.ok(content(tabs()[1]).includes("copy.py"));

const explorer = elements(tree).find(node => node.type === stubs.PythonFileExplorer);
requests.length = 0; explorer.props.onOpenFile("sub/helper.py", "C:/scripts"); await flush(() => tabs().length === 3);
assert.equal(requests[0].params.path, "sub/helper.py", "tree reads use root-relative worker paths");
assert.equal(editor().props.code, "print('helper')");
button("Close helper.py").props.onClick(); render(); assert.equal(tabs().length, 2);
assert.ok(elements(tree).some(node => node.props.title === "C:/scripts/copy.py"), "editor documents keep full paths for running and save-as");

editor().props.onBreakpoint(1); render(); requests.length = 0;
button("Debug").props.onClick(); await flush();
const start = requests.find(request => request.method === "start_python_debug");
assert.deepEqual(start.params.breakpoints, [1]); assert.equal(start.params.working_directory, "C:/scripts");
assert.equal(editor().props.locked, true); assert.equal(button("Close copy.py").props.disabled, true);
button("Over").props.onClick(); await flush(); assert.equal(requests.at(-1).params.command, "step_over");
button("New").props.onClick(); render(); assert.equal(editor().props.code, "");
assert.equal(button("Continue").props.disabled, false, "a paused session can continue while another empty tab is active");
tabs().find(tab => content(tab).includes("copy.py")).props.onClick(); render();
button("Continue").props.onClick(); await flush(); assert.equal(requests.at(-1).params.command, "continue");
debugPending = true; button("Over").props.onClick(); await flush();
assert.equal(button("Continue").props.disabled, true, "commands wait for the previous command acknowledgment");
const pendingBreakpoints = [...editor().props.breakpoints];
editor().props.onBreakpoint(1); render(); assert.deepEqual(editor().props.breakpoints, pendingBreakpoints, "gutter edits cannot outrun an unacknowledged command");
elements(tree).find(node => node.type === stubs.PythonDebugPanel).props.onClear(); render();
assert.deepEqual(editor().props.breakpoints, pendingBreakpoints, "clear waits for the command acknowledgment too");
button("Stop").props.onClick(); await flush(); assert.equal(requests.at(-1).params.command, "stop"); assert.equal(editor().props.locked, false);
debugPending = false;
button("Close untitled-3.py").props.onClick(); render(); assert.equal(tabs().length, 2);

const design = { design_id: "source", nets: [{ id: 7, name: "GND" }] };
const context = { boards: [{ id: "A", name: "Controller", design_id: "source", design }, { id: "B", name: "Shield", design_id: "source", design }], selected_board_id: "A", assembly: null };
workspaceProps = { workspace: context }; render();
scriptResult = { ...scriptResult, ui_actions: [{ action: "select_net", board_id: "B", net_id: 7 }] };
requests.length = 0; button("Run").props.onClick(); await flush();
assert.deepEqual(requests.find(request => request.method === "run_python_script").params.workspace, context, "run receives occurrence scoped board inventory");
assert.deepEqual(interfaceActions, scriptResult.ui_actions, "completed run applies admitted actions");
scriptResult = { ...scriptResult, status: "failed" };
button("Run").props.onClick(); await flush(); assert.equal(interfaceActions.length, 1, "failed run cannot change interface selection");
scriptResult = { ...scriptResult, status: "completed" };
let releaseRun;
runGate = new Promise(resolve => { releaseRun = resolve; });
button("Run").props.onClick(); render();
assert.ok(elements(tree).some(node => node.type === stubs.PythonRunStatus), "pending runs render elapsed progress");
workspaceProps = { workspace: { ...context, selected_board_id: "B" } }; render();
releaseRun(); runGate = null; await flush();
assert.equal(interfaceActions.length, 1, "context changes block stale run actions");
assert.ok(content(tree).includes("Board context changed during execution"));
scriptResult = { ...scriptResult, ui_actions: [{ action: "select_net", board_id: "missing", net_id: 7 }] };
button("Run").props.onClick(); await flush(); assert.equal(interfaceActions.length, 1, "invalid target cannot be dispatched");
assert.ok(content(tree).includes("Python interface target is unavailable"));

const physicalView = {
  contract: "spike/data-view/v1", id: "11111111-1111-1111-1111-111111111111", kind: "mesh", title: "Physical model",
  provenance: JSON.stringify({ scene_id: "a".repeat(64), run_id: "22222222-2222-2222-2222-222222222222", coordinate_frame: "emerge-global-xyz", coordinate_unit: "m", scene_role: "physical_geometry", phase: "solved", regions: [{ name: "model", material: "copper", triangle_start: 0, triangle_count: 1 }] }),
  coordinate_unit: "m", vertices: [[0, 0, 0], [1, 0, 0], [0, 1, 0]], triangles: [[0, 1, 2]],
};
const viewportCalls = [];
assert.equal(scriptDataViews.admitDataViews([physicalView]).length, 1, "physical fixture is an admitted data view");
assert.ok(viewportModel.physicalGeometry(physicalView), "physical fixture has valid scene provenance");
workspaceProps = { workspace: context, onShowViewport: (...args) => viewportCalls.push(args) };
scriptResult = { contract: "spike/python-script-result/v1", status: "completed", stdout: "solved", return_code: 0, views: [physicalView] };
render();
interpreter().props.onChange({ target: { value: "C:/EMerge/python.exe" } }); render();
requests.length = 0;
button("Run").props.onClick(); await flush();
assert.equal(requests.find(request => request.method === "run_python_script").params.python_executable, "C:/EMerge/python.exe", "Run forwards the selected interpreter explicitly");
assert.equal(viewportCalls.length, 1, "a completed physical model opens in the viewport");
assert.match(viewportCalls[0][1], /physical model$/); assert.equal(viewportCalls[0][2], true, "automatic viewport keeps the editor open");
assert.equal(button("Center Python window").props.disabled, undefined, "successful physical output floats the workspace");
button("Show in viewport").props.onClick(); assert.equal(viewportCalls.length, 2, "admitted completed output can be shown again");
scriptResult = { ...scriptResult, status: "failed" };
button("Run").props.onClick(); await flush();
assert.equal(button("Show in viewport").props.disabled, true, "failed output cannot be sent to the viewport");

desktop = false; render(); assert.equal(button("Run").props.disabled, true); assert.equal(button("Debug").props.disabled, true);
globalThis.document = { createElement: () => ({ click() {} }) };
button("Templates").props.onClick(); render();
const library = elements(tree).find(node => node.type === stubs.PythonTemplateLibrary);
library.props.onCreate(templates.PYTHON_TEMPLATES[0]); render(); assert.equal(tabs().length, 3);
assert.equal(editor().props.code, templates.PYTHON_TEMPLATES[0].code);
assert.ok(content(tabs()[2]).includes("●"), "a created template is an unsaved script");
button("Save").props.onClick(); await flush();
assert.ok(content(tree).includes("Download requested")); assert.ok(content(tabs()[2]).includes("Unsaved"), "browser downloads cannot establish a successful file save");
button("Close Python workspace").props.onClick(); render(); assert.equal(closed, 0);
assert.ok(elements(tree).some(node => node.props.role === "alertdialog"), "closing offers to save the new template");
await button("Discard edits").props.onClick(); render(); assert.equal(closed, 1);
console.log("Python workspace tabs, dirty-close protection, Save/Save as, external conflicts, debug controls, breakpoints and template creation passed");
