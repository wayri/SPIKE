// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/reportPreviewWindow.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

const groups = new Map();
class Channel {
  constructor(name) {
    this.name = name;
    this.listeners = [];
    this.closed = false;
    const peers = groups.get(name) ?? [];
    peers.push(this);
    groups.set(name, peers);
  }
  addEventListener(_, listener) { this.listeners.push(listener); }
  postMessage(data) {
    for (const peer of groups.get(this.name) ?? []) {
      if (peer !== this && !peer.closed) queueMicrotask(() => peer.listeners.forEach(listener => listener({ data })));
    }
  }
  close() { this.closed = true; }
}
globalThis.BroadcastChannel = Channel;

const popups = [];
globalThis.window = {
  location: { href: "http://localhost/index.html", search: "" },
  open(url) {
    const child = { url, closed: false, focusCount: 0, close() { this.closed = true; }, focus() { this.focusCount++; } };
    popups.push(child);
    return child;
  },
};

const nativeListeners = new Map();
const nativeEmissions = [];
const nativeEvents = {
  async listen(event, listener) {
    const listeners = nativeListeners.get(event) ?? [];
    listeners.push(listener);
    nativeListeners.set(event, listeners);
    return () => {
      const index = listeners.indexOf(listener);
      if (index >= 0) listeners.splice(index, 1);
    };
  },
  async emitTo(target, event, payload) {
    nativeEmissions.push({ target, event, payload });
    for (const listener of [...(nativeListeners.get(event) ?? [])]) listener({ payload });
  },
};
const nativeWindows = new Map();
const nativeCalls = [];
class NativeWindow {
  constructor(label, options) {
    this.label = label;
    this.options = options;
    this.handlers = new Map();
    nativeWindows.set(label, this);
  }
  static async getByLabel(label) { return nativeWindows.get(label) ?? null; }
  async once(event, handler) {
    const handlers = this.handlers.get(event) ?? [];
    handlers.push(handler);
    this.handlers.set(event, handlers);
    return () => {
      const index = handlers.indexOf(handler);
      if (index >= 0) handlers.splice(index, 1);
    };
  }
  async unminimize() { nativeCalls.push("unminimize"); }
  async show() { nativeCalls.push("show"); }
  async setFocus() { nativeCalls.push("setFocus"); }
  async destroy() {
    nativeCalls.push("destroy");
    nativeWindows.delete(this.label);
    for (const handler of [...(this.handlers.get("tauri://destroyed") ?? [])]) handler({ payload: undefined });
  }
}

const module = { exports: {} };
new Function("require", "module", "exports", js)(name => {
  if (name === "./detachedToolWindows") return { awaitNativeWindowCreated: async () => {} };
  if (name === "@tauri-apps/api/event") return nativeEvents;
  if (name === "@tauri-apps/api/webviewWindow") return { WebviewWindow: NativeWindow };
  throw new Error(`Unexpected module: ${name}`);
}, module, module.exports);
const api = module.exports;

const first = { fileName: "board-report.html", html: "<!doctype html><p>first</p>" };
const second = { fileName: "board-report-2.html", html: "<!doctype html><p>second</p>" };
const actions = [];
assert.equal(await api.focusReportPreviewWindow(), false);
assert.deepEqual(await api.openReportPreviewWindow(first, action => { actions.push(action); }), { mode: "browser", created: true });
assert.equal(popups.length, 1);
assert.match(popups[0].url, /spikeReportPreview=1/);
assert.match(popups[0].url, /reportToken=[a-f0-9]{48}/);

window.location.search = new URL(popups[0].url, window.location.href).search;
const snapshots = [];
const child = await api.connectReportPreviewChild(snapshot => snapshots.push(snapshot));
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(snapshots.at(-1), first, "child readiness receives the authoritative parent report");
await child.act({ type: "export" });
await new Promise(resolve => setImmediate(resolve));
assert.equal(actions.at(-1).type, "export");

await api.updateReportPreviewWindow(second);
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(snapshots.at(-1), second, "an existing preview receives regenerated HTML");
assert.deepEqual(await api.openReportPreviewWindow(second, action => { actions.push(action); }), { mode: "browser", created: false });
assert.equal(popups.length, 1, "repeat entry reuses the report window");
assert.equal(popups[0].focusCount, 1);

const forged = new Channel(groups.keys().next().value);
forged.postMessage({ event: "spike-report-preview-action", envelope: { token: "wrong", action: { type: "close" } } });
await new Promise(resolve => setImmediate(resolve));
assert.equal(actions.filter(action => action.type === "close").length, 0, "token mismatch is rejected");
forged.close();

assert.equal(api.isReportPreviewLocation(window.location.search), true);
assert.equal(api.isReportPreviewLocation("?spikeReportPreview=1&reportToken=bad"), false);
child.stop();
await api.closeReportPreviewWindow();
assert.equal(popups[0].closed, true);

// A manually closed browser child is stale: opening again must replace the
// token-bound channel and popup instead of reporting a reused window.
assert.deepEqual(await api.openReportPreviewWindow(first, action => { actions.push(action); }), { mode: "browser", created: true });
const stalePopup = popups.at(-1);
const staleUrl = stalePopup.url;
stalePopup.closed = true;
assert.deepEqual(await api.openReportPreviewWindow(second, action => { actions.push(action); }), { mode: "browser", created: true });
assert.equal(popups.length, 3, "a stale browser child is replaced");
assert.notEqual(popups.at(-1).url, staleUrl, "stale child recovery rotates the session token");
await api.closeReportPreviewWindow();

const openPopup = window.open;
window.open = () => null;
await assert.rejects(
  api.openReportPreviewWindow(first, action => { actions.push(action); }),
  /Allow local SPIKE popup windows/,
  "popup blocking is surfaced as a recoverable launch error",
);
assert.equal(await api.focusReportPreviewWindow(), false, "popup failure disposes its incomplete session");
window.open = openPopup;

// Exercise the native parent and child branches through mocked Tauri APIs.
window.__TAURI_INTERNALS__ = {};
const nativeActions = [];
assert.deepEqual(
  await api.openReportPreviewWindow(first, action => { nativeActions.push(action); }),
  { mode: "native", created: true },
);
const nativeWindow = nativeWindows.get("spike-report-preview");
assert.ok(nativeWindow, "native report window is created with the stable label");
assert.equal(nativeWindow.options.title, "SPIKE | Engineering report | board-report.html");
assert.equal(nativeWindow.options.resizable, true);
assert.equal(nativeWindow.options.decorations, true);
assert.equal(nativeWindow.options.skipTaskbar, false, "native report previews retain independent Windows taskbar entries");
assert.match(nativeWindow.options.url, /reportToken=[a-f0-9]{48}/);

window.location.search = new URL(nativeWindow.options.url, window.location.href).search;
const nativeSnapshots = [];
const nativeChild = await api.connectReportPreviewChild(snapshot => nativeSnapshots.push(snapshot));
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(nativeSnapshots.at(-1), first, "native child readiness routes the parent snapshot");
assert.ok(nativeEmissions.some(value => value.target === "main" && value.event === "spike-report-preview-action" && value.payload.action.type === "ready"));
assert.ok(nativeEmissions.some(value => value.target === "spike-report-preview" && value.event === "spike-report-preview-snapshot"));

await nativeChild.act({ type: "export" });
await new Promise(resolve => setImmediate(resolve));
assert.equal(nativeActions.at(-1).type, "export", "native child action reaches the parent handler");
await api.updateReportPreviewWindow(second);
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(nativeSnapshots.at(-1), second, "native report regeneration reaches the existing child");

const emissionsBeforeReuse = nativeEmissions.length;
assert.deepEqual(
  await api.openReportPreviewWindow(second, action => { nativeActions.push(action); }),
  { mode: "native", created: false },
);
assert.deepEqual(nativeCalls.slice(-3), ["unminimize", "show", "setFocus"], "native reuse restores and focuses a minimized window");
assert.equal(nativeWindows.get("spike-report-preview"), nativeWindow, "native reuse preserves the existing window and token");
assert.ok(nativeEmissions.length > emissionsBeforeReuse, "native reuse republishes the current snapshot");

nativeChild.stop();
await api.closeReportPreviewWindow();
assert.equal(nativeWindows.has("spike-report-preview"), false, "programmatic close destroys the native window");
assert.equal(nativeActions.filter(action => action.type === "closed").length, 0, "programmatic close does not duplicate an OS close callback");

const destroyedActions = [];
await api.openReportPreviewWindow(first, action => { destroyedActions.push(action); });
const osClosedWindow = nativeWindows.get("spike-report-preview");
await osClosedWindow.destroy();
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(destroyedActions, [{ type: "closed" }], "an OS-destroyed native window closes the parent session exactly once");
assert.equal(await api.focusReportPreviewWindow(), false, "OS destruction clears the native session");
delete window.__TAURI_INTERNALS__;

const previewSource = readFileSync(new URL("../src/ReportPreview.tsx", import.meta.url), "utf8");
const previewRootSource = readFileSync(new URL("../src/ReportPreviewWindowRoot.tsx", import.meta.url), "utf8");
assert.match(previewRootSource, /nativeWindow=\{"__TAURI_INTERNALS__" in window\}/, "report root marks native presentation explicitly");
assert.match(previewSource, /!nativeWindow && <button[^>]*aria-label="Close report preview"/, "native report preview relies on the OS close control");
assert.match(previewSource, /sandbox="allow-scripts allow-downloads allow-modals"/);
assert.doesNotMatch(previewSource, /allow-same-origin/);
assert.match(previewSource, /contentWindow\?\.postMessage\(PRINT_MESSAGE, "\*"\)/);
assert.match(source, /await child\.unminimize\(\)/);
assert.match(source, /await child\.show\(\)/);
assert.match(source, /await child\.setFocus\(\)/);
const capability = JSON.parse(readFileSync(new URL("../src-tauri/capabilities/report-preview.json", import.meta.url), "utf8"));
assert.deepEqual(capability.windows, ["spike-report-preview"]);
assert.deepEqual(capability.permissions, ["core:event:default"]);

console.log("Report preview browser/native sessions, recovery, reuse, routing, close lifecycle and iframe safety checks passed");
