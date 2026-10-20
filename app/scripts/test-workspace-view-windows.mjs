// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";

const model = await importTestTypescript("workspaceViewModel");
const source = readFileSync(new URL("../src/workspaceViewWindows.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const module = { exports: {} };
const groups = new Map();
class Channel {
  constructor(name) { this.name = name; this.listeners = []; this.closed = false; const peers = groups.get(name) ?? []; peers.push(this); groups.set(name, peers); }
  addEventListener(_, listener) { this.listeners.push(listener); }
  postMessage(data) { for (const peer of groups.get(this.name) ?? []) if (peer !== this && !peer.closed) queueMicrotask(() => peer.listeners.forEach(listener => listener({ data }))); }
  close() { this.closed = true; }
}
globalThis.BroadcastChannel = Channel;
const popups = [];
let ownerFocuses = 0;
globalThis.window = {
  location: { href: "http://localhost/index.html", search: "" },
  focus() { ownerFocuses++; },
  open(url) { const popup = { url, closed: false, focused: 0, close() { this.closed = true; }, focus() { this.focused++; } }; popups.push(popup); return popup; },
};
new Function("require", "module", "exports", js)(name => name === "./workspaceViewModel" ? model
  : name === "./detachedToolWindows" ? { awaitNativeWindowCreated: async () => {} }
    : (() => { throw new Error(name); })(), module, module.exports);
const api = module.exports;

const boardScope = { kind: "board-occurrence", occurrenceId: "occ-A", designId: "design-A" };
const partScope = { kind: "assembly-part", partId: "case-lid" };
const target = { id: "occ-A", designId: "design-A", name: "Power board", active: false, widthMm: 20, heightMm: 10, localCenterMm: [10, 5, 0], transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] };
const snapshot = (id, scope, projectSession = "project-1", revision = "state-1") => ({
  viewId: id, projectSession, revision, viewportRevision: "viewport-1",
  descriptor: { id, title: id, scope, viewMode: "3D", detached: true }, valid: true,
  targetBoards: scope.kind === "board-occurrence" ? [target] : [], sourceDesignId: scope.kind === "board-occurrence" ? scope.designId : undefined,
  visibility: { "occ-A": true }, layerVisibility: { "occ-A": { "F.Cu": true } }, layerOpacity: { "occ-A": { "F.Cu": .8 } },
  layerFocus: { "occ-A": "F.Cu" }, linkedNets: {}, analysisDomain: "pi",
});
const viewport = { revision: "viewport-1", boards: { "design-A": { tracks: [], pads: [], vias: [], zones: [], components: [] } }, assemblyModels: [] };
assert.equal(model.validWorkspaceViewSnapshot(snapshot("board-view", boardScope)), true);
assert.equal(model.validWorkspaceViewViewportData(viewport), true);

const actionsA = [], actionsB = []; let hangA = false, hangLeaseB = false;
await api.openWorkspaceViewWindow("board-view", snapshot("board-view", boardScope), action => { actionsA.push(action); return hangA ? new Promise(() => {}) : "A"; }, viewport);
await api.openWorkspaceViewWindow("part-view", snapshot("part-view", partScope), action => { actionsB.push(action); return hangLeaseB && action.type === "lease" ? new Promise(() => {}) : "B"; }, viewport);
assert.equal(popups.length, 2, "distinct view IDs open independent windows");
assert.notEqual(api.workspaceViewWindowLabel("board-view"), api.workspaceViewWindowLabel("part-view"));
assert.equal(api.workspaceViewIdFromLocation(new URL(popups[0].url, window.location.href).search), "board-view");

window.location.search = new URL(popups[0].url, window.location.href).search;
const receivedA = [], ownerA = [];
const childA = await api.connectWorkspaceViewChild("board-view", { onSnapshot: value => receivedA.push(value), onOwnerConnection: value => ownerA.push(value) }, { leaseIntervalMs: 10000 });
window.location.search = new URL(popups[1].url, window.location.href).search;
const receivedB = [], ownerB = [];
const childB = await api.connectWorkspaceViewChild("part-view", { onSnapshot: value => receivedB.push(value), onOwnerConnection: value => ownerB.push(value) }, { leaseIntervalMs: 25, leaseTimeoutMs: 20 });
await new Promise(resolve => setImmediate(resolve));
assert.equal(receivedA.at(-1).viewId, "board-view"); assert.equal(receivedB.at(-1).viewId, "part-view");
assert.equal(await childA.act({ type: "select-object", occurrenceId: "occ-A", sourceObjectId: "track-17" }), "A");
assert.equal(actionsA.at(-1).sourceObjectId, "track-17", "exact source identity reaches only its owning session");
assert.equal(actionsB.some(action => action.type === "select-object"), false);
assert.equal(await childA.act({ type: "focus-owner" }), true);
assert.equal(ownerFocuses, 1, "show-owner is fulfilled by the transport owner window");
assert.equal(actionsA.some(action => action.type === "focus-owner"), false, "focus-owner is not delegated as a project mutation");
await assert.rejects(childA.act({ type: "select-object", partId: "case-lid", sourceObjectId: "face-4" }), /fixed view scope/);

// A dropped refresh must not authorize a stale revision or project session.
const channelA = groups.get([...groups.keys()].find(key => key.includes(new URL(popups[0].url, window.location.href).searchParams.get("workspaceViewToken"))))[0];
const originalPost = channelA.postMessage.bind(channelA); channelA.postMessage = data => { if (data.event !== "spike-workspace-view-snapshot") originalPost(data); };
await api.updateWorkspaceViewWindow("board-view", snapshot("board-view", boardScope, "project-2", "state-2"), viewport);
await assert.rejects(childA.act({ type: "select-net", occurrenceId: "occ-A", netId: "GND" }), /project view changed/);
channelA.postMessage = originalPost;

hangA = true; const pending = childA.act({ type: "status", value: "pending" }); await new Promise(resolve => setImmediate(resolve)); childA.stop();
await assert.rejects(pending, /closed/, "teardown rejects in-flight RPCs"); hangA = false;
await api.closeWorkspaceViewWindow("board-view");
assert.equal(popups[0].closed, true); assert.equal(popups[1].closed, false, "closing one scoped window preserves its sibling");
assert.equal(await childB.act({ type: "select-object", partId: "case-lid", sourceObjectId: "face-9" }), "B");

hangLeaseB = true;
await new Promise(resolve => setTimeout(resolve, 90));
assert.equal(ownerB.includes(false), true, "missed owner lease disables the child without transferring authority");
childB.stop(); await api.closeWorkspaceViewWindow("part-view");

// The hook's pure projection must never leak sibling board/model payloads.
const hookSource = readFileSync(new URL("../src/useWorkspaceViews.tsx", import.meta.url), "utf8");
const hookJs = ts.transpileModule(hookSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const hookModule = { exports: {} }, nativeRequire = createRequire(import.meta.url);
new Function("require", "module", "exports", hookJs)(name => name === "./workspaceViewModel" ? model
  : name === "./workspaceViewWindows" ? { closeAllWorkspaceViewWindows: async () => {} }
    : ["./ScopedWorkspaceView", "./WorkspaceViewHost", "./WorkspaceViewTabs"].includes(name) ? { default: () => null }
      : nativeRequire(name), hookModule, hookModule.exports);
const scopeOptions = {
  projectSession: "project-1", revision: "state-1", viewportRevision: "viewport-1",
  boards: { "design-A": viewport.boards["design-A"], "design-B": { tracks: [{ id: "secret-sibling" }] } },
  occurrences: [target, { ...target, id: "occ-B", designId: "design-B", name: "Sibling" }],
  assemblyModels: [{ partId: "case-lid", modelId: "lid", name: "Lid", modelType: "glb", url: "lid.glb", partTransform: target.transform, modelTransform: target.transform, visible: true, opacity: 1 },
    { partId: "case-base", modelId: "base", name: "Base", modelType: "glb", url: "base.glb", partTransform: target.transform, modelTransform: target.transform, visible: true, opacity: 1 }],
  parts: [{ partId: "case-lid", title: "Lid" }, { partId: "case-base", title: "Base" }], visibility: { "occ-A": true, "occ-B": true },
  layerVisibility: { "occ-A": { "F.Cu": true }, "occ-B": { "B.Cu": true } }, layerOpacity: { "occ-A": { "F.Cu": .8 }, "occ-B": { "B.Cu": .2 } },
  layerFocus: { "occ-A": "F.Cu", "occ-B": "B.Cu" }, linkedNets: { "occ-A::GND": ["occ-A::GND"], "occ-B::VCC": ["occ-B::VCC"] }, analysisDomain: "pi",
};
const boardDescriptor = snapshot("board-view", boardScope).descriptor;
const scopedBoard = hookModule.exports.deriveWorkspaceViewScope(scopeOptions, boardDescriptor);
assert.deepEqual(Object.keys(scopedBoard.viewport.boards), ["design-A"]); assert.deepEqual(scopedBoard.targetBoards.map(item => item.id), ["occ-A"]);
assert.equal(scopedBoard.targetBoards[0].active, true, "a fixed board view uses the primary scene instead of rendering a duplicate assembly occurrence");
assert.equal(target.active, false, "scope projection does not mutate the assembly occurrence");
assert.deepEqual(Object.keys(scopedBoard.layerVisibility), ["occ-A"]); assert.deepEqual(Object.keys(scopedBoard.linkedNets), ["occ-A::GND"]);
const partDescriptor = snapshot("part-view", partScope).descriptor;
const scopedPart = hookModule.exports.deriveWorkspaceViewScope(scopeOptions, partDescriptor);
assert.deepEqual(scopedPart.viewport.assemblyModels.map(item => item.partId), ["case-lid"]); assert.deepEqual(Object.keys(scopedPart.viewport.boards), []);
assert.equal(hookModule.exports.deriveWorkspaceViewScope({ ...scopeOptions, occurrences: [] }, boardDescriptor).valid, false, "removed occurrence invalidates its fixed view");

// StrictMode may close and reopen a host while its first native listener is
// still registering. The abandoned session must not create or destroy the
// replacement window, and every listener it acquired must be released.
const nativeModule = { exports: {} };
let releaseFirstListen;
let listenCount = 0, removedListeners = 0, failEmit = false, nativeLookups = 0, delayDestroy = false, releaseDestroy;
const activeNativeListeners = new Set(), nativeWindows = new Map(), createdNativeWindows = [];
const nativeEvent = {
  async listen(event, listener) {
    const registration = { event, listener }; activeNativeListeners.add(registration); listenCount++;
    const remove = () => { if (activeNativeListeners.delete(registration)) removedListeners++; };
    if (listenCount === 1) return new Promise(resolve => { releaseFirstListen = () => resolve(remove); });
    return remove;
  },
  async emitTo() { if (failEmit) throw new Error("initial emit failed"); },
};
class NativeWindow {
  static async getByLabel(label) { nativeLookups++; return nativeWindows.get(label) ?? null; }
  constructor(label, options) { this.label = label; this.options = options; this.destroyed = false; createdNativeWindows.push(this); nativeWindows.set(label, this); }
  async once(_, callback) { this.destroyedCallback = callback; return () => {}; }
  async destroy() {
    if (this.destroyPromise) return this.destroyPromise;
    this.destroyPromise = (async () => {
      if (delayDestroy) await new Promise(resolve => { releaseDestroy = resolve; });
      this.destroyed = true; if (nativeWindows.get(this.label) === this) nativeWindows.delete(this.label);
    })();
    return this.destroyPromise;
  }
  async unminimize() {} async show() {} async setFocus() {}
}
globalThis.window = { ...globalThis.window, __TAURI_INTERNALS__: {}, location: { href: "http://localhost/index.html", search: "" } };
new Function("require", "module", "exports", js)(name => name === "./workspaceViewModel" ? model
  : name === "./detachedToolWindows" ? { awaitNativeWindowCreated: async () => {} }
    : name === "@tauri-apps/api/event" ? nativeEvent
      : name === "@tauri-apps/api/webviewWindow" ? { WebviewWindow: NativeWindow }
        : (() => { throw new Error(name); })(), nativeModule, nativeModule.exports);
const nativeApi = nativeModule.exports;
const firstOpen = nativeApi.openWorkspaceViewWindow("strict-view", snapshot("strict-view", boardScope), () => {}, viewport);
await new Promise(resolve => setImmediate(resolve));
await nativeApi.closeWorkspaceViewWindow("strict-view");
const secondOpen = nativeApi.openWorkspaceViewWindow("strict-view", snapshot("strict-view", boardScope), () => {}, viewport);
await secondOpen;
releaseFirstListen();
await assert.rejects(firstOpen, /cancelled/);
assert.equal(createdNativeWindows.length, 1, "an abandoned initialization never creates a stale native window");
assert.equal(nativeWindows.get(nativeApi.workspaceViewWindowLabel("strict-view")), createdNativeWindows[0], "the replacement token owns the surviving native window");
assert.equal(activeNativeListeners.size, 2, "only the replacement action and viewport listeners remain");
assert.equal(removedListeners, 1, "the delayed listener acquired by the abandoned session is released");
await nativeApi.closeWorkspaceViewWindow("strict-view");

// Closing is bound to the exact child handle. It must not look up a label
// after yielding and accidentally destroy a replacement with the same ID.
await nativeApi.openWorkspaceViewWindow("close-race", snapshot("close-race", boardScope), () => {}, viewport);
const lookupsBeforeClose = nativeLookups;
delayDestroy = true;
const delayedClose = nativeApi.closeWorkspaceViewWindow("close-race");
await new Promise(resolve => setImmediate(resolve));
assert.equal(nativeLookups, lookupsBeforeClose, "close never resolves a mutable native-window label");
const replacementOpen = nativeApi.openWorkspaceViewWindow("close-race", snapshot("close-race", boardScope, "project-2"), () => {}, viewport);
releaseDestroy(); delayDestroy = false;
await delayedClose; await replacementOpen;
const replacement = nativeWindows.get(nativeApi.workspaceViewWindowLabel("close-race"));
assert.ok(replacement && !replacement.destroyed, "delayed teardown of the old handle preserves the replacement child");
assert.notEqual(replacement, createdNativeWindows.at(-2));
await nativeApi.closeWorkspaceViewWindow("close-race");

// A child connection that cannot send its initial ready event must unwind all
// native listeners because no connection object is returned to its caller.
window.location.search = "?workspaceViewToken=" + "a".repeat(48);
const listenersBeforeFailedConnect = activeNativeListeners.size;
failEmit = true;
await assert.rejects(nativeApi.connectWorkspaceViewChild("strict-view", { onSnapshot() {} }), /initial emit failed/);
failEmit = false;
assert.equal(activeNativeListeners.size, listenersBeforeFailedConnect, "failed child setup removes all partially registered listeners");
console.log("Workspace scoped views passed: isolated sessions/tokens, fixed source scope, stale project rejection, RPC teardown, sibling survival and owner-loss lease");
