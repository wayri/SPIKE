// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const listeners = new Map(), windows = new Map(), cancellations = [], commands = [], workers = [];
let slowResolve;
let nativeCreated = 0, focused = 0, destroyed, revision = "r1", project = "p1";
globalThis.window = { location: { href: "http://localhost/", search: "" } };
const events = {
  async listen(name, handler, options) { const key = `${options.target.label}:${name}`; listeners.set(key, handler); return () => listeners.delete(key); },
  async emitTo(label, name, payload) { await listeners.get(`${label}:${name}`)?.({ payload }); },
};
class WebviewWindow {
  constructor(label, options) { this.label = label; this.options = options; windows.set(label, this); nativeCreated++; window.location.search = new URL(options.url, "http://localhost").search; }
  static async getByLabel(label) { return windows.get(label); }
  async once(name, handler) { if (name === "tauri://destroyed") destroyed = handler; }
  async unminimize() {} async show() {} async setFocus() { focused++; }
  async destroy() { windows.delete(this.label); destroyed?.(); }
}
const source = readFileSync(new URL("../src/assistantWindow.ts", import.meta.url), "utf8");
const rootSource = readFileSync(new URL("../src/AssistantWindowRoot.tsx", import.meta.url), "utf8");
const panelSource = readFileSync(new URL("../src/AssistantChatPanel.tsx", import.meta.url), "utf8");
assert.match(rootSource, /nativeWindow=\{"__TAURI_INTERNALS__" in window\}/, "assistant root marks native presentation explicitly");
assert.match(panelSource, /!nativeWindow && <button[^>]*aria-label="Close SPIKE Assistant"/, "native assistant relies on the guarded OS close control");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2021 } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", compiled)(name => {
  if (name === "@tauri-apps/api/event") return events;
  if (name === "@tauri-apps/api/webviewWindow") return { WebviewWindow };
  if (name === "./detachedToolWindows") return { awaitNativeWindowCreated: async () => {} };
  if (name === "./workerBridge") return { runLocalWorker: async request => { workers.push(request); if (request.id === "assistant-slow") return new Promise(resolve => { slowResolve = resolve; }); return { ok: true, result: { message: { role: "assistant", content: "Actual provider fixture" } } }; }, cancelLocalWorker: async id => { cancellations.push(id); if (id === "assistant-slow") slowResolve?.({ ok: false, error: "cancelled" }); return true; } };
  if (name === "./assistantSkills") return { assistantToolCatalog: [{ name: "inspect", command: "analysis_context" }], validateAssistantToolCall: (_, args) => { if (Object.keys(args).length) throw new Error("Unexpected arguments"); } };
  throw new Error(name);
}, module, module.exports);
const api = module.exports;
const owner = { getContext: () => ({ projectName: project }), getRevision: () => revision, getProjectIdentity: () => project, onCommand: async (command, args) => { commands.push({ command, args }); return { boardCount: 2 }; } };
await Promise.all([api.openAssistantWindow(owner, () => {}), api.openAssistantWindow(owner, () => {})]);
await api.openAssistantWindow(owner, () => {});
assert.equal(nativeCreated, 1); assert.equal(focused, 1, "reuse the live chat window");
assert.equal(windows.get("spike-assistant").options.skipTaskbar, false, "native assistant retains an independent Windows taskbar entry");
const bridge = await api.connectAssistantWindow();
// Native pickers wait for a human; keep ordinary provider requests bounded.
const nativeSetTimeout = globalThis.setTimeout;
const requestTimeouts = [];
globalThis.setTimeout = (callback, delay, ...args) => { requestTimeouts.push(delay); return nativeSetTimeout(callback, delay, ...args); };
try {
  await bridge.onCommand("assistant_choose_work_folder", {});
  assert.equal(requestTimeouts.at(-1), 30 * 60 * 1000, "folder picker has its own human interaction budget");
  await bridge.prepareContext();
  assert.equal(requestTimeouts.at(-1), 150000, "ordinary requests retain their bounded timeout");
} finally { globalThis.setTimeout = nativeSetTimeout; }
commands.length = 0;
assert.equal(bridge.getRevision(), "r1");
assert.equal(bridge.getContext().projectName, "p1");
assert.deepEqual(await bridge.onCommand("analysis_context", {}), { boardCount: 2 });
await assert.rejects(() => bridge.onCommand("arbitrary_shell", {}), /Unsupported/);
await assert.rejects(() => bridge.onCommand("analysis_context", { extra: true }), /Unexpected/);
await assert.rejects(() => bridge.runWorker({ id: "assistant-bad", method: "run_python", params: {} }), /Unsupported/);
await assert.rejects(() => bridge.runWorker({ id: "assistant-files", method: "assistant_work_files", params: { root: "C:/private", action: "list" } }), /Unsupported/, "child cannot inject a work-folder root through the worker channel");
await assert.rejects(() => bridge.cancelWorker("unowned"), /Unknown/);
assert.equal(cancellations.length, 0);
assert.equal(await bridge.cancelWorker(), false);
await bridge.runWorker({ id: "assistant-turn", method: "assistant_turn", params: {} });
assert.equal(workers.length, 1);
revision = "r2";
await assert.rejects(() => bridge.onCommand("analysis_context", {}), /Project changed/);
assert.equal(commands.length, 1, "stale requests never mutate the project");
await bridge.prepareContext(); assert.equal(bridge.getRevision(), "r2");
const forged = { token: "wrong", id: "fake", kind: "command", command: "analysis_context", args: {}, revision: "r2" };
await events.emitTo("main", "spike-assistant-request", forged);
assert.equal(commands.length, 1, "unbound windows cannot use the session");
project = "p2";
await assert.rejects(() => bridge.prepareContext(), /Project switched/);
await assert.rejects(() => bridge.runWorker({ id: "assistant-other", method: "assistant_turn" }), /Project switched/);
assert.equal(workers.length, 1, "old chats cannot transmit a new project's evidence");
bridge.dispose();
assert.equal(listeners.has("spike-assistant:spike-assistant-response"), false);
await api.closeOwnedAssistantWindow();
assert.equal(listeners.has("main:spike-assistant-request"), false);
await api.openAssistantWindow(owner, () => {});
const closingBridge = await api.connectAssistantWindow();
const large = "x".repeat(3 * 1024 * 1024);
await closingBridge.runWorker({ id: "assistant-media-budget", method: "assistant_turn", params: { mediaFixture: large } });
await assert.rejects(() => closingBridge.runWorker({ id: "assistant-setup-budget", method: "assistant_models", params: { fixture: large } }), /transport budget/);
await assert.rejects(() => closingBridge.runWorker({ id: "assistant-oversize-budget", method: "assistant_turn", params: { fixture: "x".repeat(30 * 1024 * 1024) } }), /transport budget/);

const pending = closingBridge.runWorker({ id: "assistant-slow", method: "assistant_turn", params: {} }).then(() => "resolved", error => error.message);
await new Promise(resolve => setImmediate(resolve));
await api.closeOwnedAssistantWindow();
closingBridge.dispose();
assert.equal(await pending, "Assistant closed.");
assert.ok(cancellations.includes("assistant-slow"), "closing cancels only the owned provider operation");
console.log("Assistant window: single session, provider broker, schema allowlist, stale revision, project isolation and cleanup passed.");
