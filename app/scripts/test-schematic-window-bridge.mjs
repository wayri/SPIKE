// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

let resolveDiscovery;
let resolveCreation;
const discovery = new Promise(resolve => { resolveDiscovery = resolve; });
const creation = new Promise(resolve => { resolveCreation = resolve; });
const nativeWindows = [];
let activeNative = null;
class MockWebviewWindow {
  constructor(label, options) { this.label = label; this.options = options; this.destroyed = false; this.handlers = new Map(); nativeWindows.push(this); activeNative = this; }
  static async getByLabel() { await discovery; return activeNative?.destroyed ? null : activeNative; }
  async once(name, handler) { this.handlers.set(name, handler); return () => this.handlers.delete(name); }
  async destroy() { if (this.destroyed) return; this.destroyed = true; this.handlers.get("tauri://destroyed")?.(); if (activeNative === this) activeNative = null; }
  async unminimize() {}
  async show() {}
  async setFocus() {}
}

const channels = [];
class MockBroadcastChannel {
  constructor(name) { this.name = name; this.closed = false; this.messages = []; this.listeners = []; channels.push(this); }
  addEventListener(name, listener) { if (name === "message") this.listeners.push(listener); }
  postMessage(message) { if (!this.closed) this.messages.push(message); }
  emit(message) { for (const listener of this.listeners) listener({ data: message }); }
  close() { this.closed = true; }
}
globalThis.BroadcastChannel = MockBroadcastChannel;
globalThis.window = { __TAURI_INTERNALS__: {}, location: new URL("http://localhost/app") };

const bundled = await build({
  entryPoints: [fileURLToPath(new URL("../src/schematicWindow.ts", import.meta.url))], bundle: true, write: false,
  format: "esm", platform: "node",
  plugins: [
    { name: "native-window-mock", setup(builder) {
      builder.onResolve({ filter: /^@tauri-apps\/api\/webviewWindow$/ }, () => ({ path: "native-window", namespace: "native-mock" }));
      builder.onLoad({ filter: /.*/, namespace: "native-mock" }, () => ({ contents: "export const WebviewWindow = globalThis.__MockWebviewWindow;", loader: "js" }));
    } },
    { name: "creation-mock", setup(builder) {
      builder.onResolve({ filter: /detachedToolWindows$/ }, () => ({ path: "creation", namespace: "creation-mock" }));
      builder.onLoad({ filter: /.*/, namespace: "creation-mock" }, () => ({ contents: "export const awaitNativeWindowCreated = async () => globalThis.__MockCreation;", loader: "js" }));
    } },
  ],
});
globalThis.__MockWebviewWindow = MockWebviewWindow;
globalThis.__MockCreation = creation;
const bridge = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].contents).toString("base64")}`);
const snapshot = { document: null, linked: false, boardName: "", selected: {}, busy: false, status: "ready" };
const actions = [];

const first = bridge.openSchematicWindow(snapshot, action => actions.push(action));
const second = bridge.openSchematicWindow({ ...snapshot, status: "new host" }, action => actions.push(action));
const staleCleanup = first.then(result => bridge.closeSchematicWindow(result.lease));
resolveDiscovery(null);
await new Promise(resolve => setImmediate(resolve));
assert.equal(nativeWindows.length, 1, "serialized second open must wait for deferred first creation");
resolveCreation(null);
const [firstLease, secondLease] = await Promise.all([first, second]);
await staleCleanup;
assert.equal(firstLease.created, true);
assert.equal(nativeWindows[0].options.skipTaskbar, false, "native schematic viewers retain independent Windows taskbar entries");
assert.equal(secondLease.created, false, "second StrictMode host must lease the existing window");
assert.equal(nativeWindows[0].destroyed, false, "stale cleanup must not destroy the replacement host lease");

const channel = channels[0];
const token = channel.name.split(":").at(-1);
channel.emit({ event: "spike-schematic-viewer-action", envelope: { token: "0".repeat(48), action: { type: "import" } } });
await new Promise(resolve => setImmediate(resolve));
assert.equal(actions.length, 0, "wrong-token actions must be ignored");
channel.emit({ event: "spike-schematic-viewer-action", envelope: { token, action: { type: "import" } } });
await new Promise(resolve => setImmediate(resolve));
assert.equal(actions.at(-1)?.type, "import");

await bridge.closeSchematicWindow(secondLease.lease);
assert.equal(channel.closed, true, "last lease must close its BroadcastChannel");
assert.equal(nativeWindows[0].destroyed, true, "last lease must destroy its native window");
channel.emit({ event: "spike-schematic-viewer-action", envelope: { token, action: { type: "import" } } });
assert.equal(actions.length, 1, "disposed sessions must ignore stale actions");

const reopened = await bridge.openSchematicWindow({ ...snapshot, status: "reopened" }, action => actions.push(action));
assert.equal(reopened.created, true);
assert.equal(nativeWindows.length, 2, "reopen after final release must create a fresh native window");
assert.notEqual(channels[1].name, channel.name, "reopened session must rotate its channel token");
await bridge.closeSchematicWindow(reopened.lease);
assert.equal(channels[1].closed, true);

// No broad native event permission is needed by the authenticated BC bridge.
const capability = JSON.parse(await (await import("node:fs/promises")).readFile(new URL("../src-tauri/capabilities/schematic-viewer.json", import.meta.url), "utf8"));
assert.deepEqual(capability.permissions, []);
assert.equal(channels.filter(item => !item.closed).length, 0, "bridge teardown must not leak channels");
console.log("Schematic bridge leases, deferred native creation, token checks, stale actions and teardown passed.");
