// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

globalThis.window = { __TAURI_INTERNALS__: {} };
register("./desktop-close-mock-loader.mjs", import.meta.url);
const bridge = await import("../src/workerBridge.ts");
const calls = [];
let nativeListener, legacyListener, unlistens = 0;
globalThis.__spikeCloseWindow = {
  listen(event, listener) { assert.equal(event, "spike://desktop-close-requested"); nativeListener = listener; return () => { unlistens += 1; }; },
  onCloseRequested(listener) { legacyListener = listener; return () => { unlistens += 1; }; },
};
const supported = (command, args) => {
  calls.push(command);
  if (command === "main_close_recovery_supported") return true;
  if (command === "acknowledge_desktop_close") return args?.generation === 1;
};
globalThis.__spikeWorkerInvoke = (command, args) => {
  calls.push([command, args]);
  if (command === "main_close_recovery_supported") return true;
  if (command === "acknowledge_desktop_close") return args?.generation === 1;
};

// The renderer first acknowledges the exact native generation, then applies
// its save/draft policy only while that generation remains accepted.
const delivered = [];
let stop = await bridge.subscribeDesktopCloseRequested((_prevent, generation) => delivered.push(generation));
nativeListener({ payload: { generation: 1 } });
assert.deepEqual(delivered, [1]);
assert.equal(await bridge.acknowledgeDesktopClose(1), true);
assert.deepEqual(calls.at(-1), ["acknowledge_desktop_close", { generation: 1 }]);
stop();
assert.equal(unlistens, 1);
stop = await bridge.subscribeDesktopCloseRequested((_prevent, generation) => delivered.push(generation));
const count = calls.length;
for (const generation of [0, -1, 1.5, NaN, "invalid"]) nativeListener({ payload: { generation } });
assert.equal(calls.length, count);
assert.deepEqual(delivered, [1]);
stop();

// Explicit approval reaches native shutdown, including if assistant destruction
// rejects or hangs. Fake only the timeout, leaving the bridge under test intact.
globalThis.__spikeWorkerInvoke = supported;
await bridge.closeDesktopWindow();
assert.equal(calls.at(-1), "close_desktop_app");
const originalSetTimeout = globalThis.setTimeout;
const originalClearTimeout = globalThis.clearTimeout;
const originalWarn = console.warn;
let timeout, cleared = 0;
const warnings = [];
console.warn = (...args) => warnings.push(args);
globalThis.setTimeout = (callback, delay) => {
  assert.equal(delay, 1000);
  timeout = callback;
  return 42;
};
globalThis.clearTimeout = timer => { assert.equal(timer, 42); cleared += 1; };
try {
  await bridge.closeDesktopWindow(async () => undefined);
  assert.equal(cleared, 1, "successful child cleanup clears its timeout");
  await bridge.closeDesktopWindow(async () => { throw new Error("child failed"); });
  assert.equal(calls.at(-1), "close_desktop_app");
  assert.equal(warnings.length, 1);
  let rejectChild;
  const child = new Promise((_, reject) => { rejectChild = reject; });
  const pending = bridge.closeDesktopWindow(() => child);
  await Promise.resolve();
  timeout();
  await pending;
  assert.equal(calls.at(-1), "close_desktop_app");
  assert.equal(warnings.length, 2);
  assert.equal(cleared, 3);
  rejectChild(new Error("late child rejection"));
  await new Promise(resolve => setImmediate(resolve));
} finally {
  globalThis.setTimeout = originalSetTimeout;
  globalThis.clearTimeout = originalClearTimeout;
  console.warn = originalWarn;
}

assert.equal(await bridge.acknowledgeDesktopClose(0), false, "generation zero is never a native close request");
globalThis.__spikeWorkerInvoke = () => Promise.reject(new Error("IPC unavailable"));
await assert.rejects(bridge.closeDesktopWindow(), /IPC unavailable/);
delete window.__TAURI_INTERNALS__;
await bridge.subscribeDesktopCloseRequested(() => { assert.fail("browser callback"); });
await bridge.closeDesktopWindow(() => { assert.fail("browser cleanup"); });

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
assert.ok(app.includes("await closeDesktopWindow(closeOwnedAssistantWindow);"),
  "save/discard approval must use bounded assistant cleanup");
assert.ok(!app.includes("await closeOwnedAssistantWindow();"),
  "unbounded assistant shutdown must not block approved main close");
console.log("Desktop close decisions, native recovery acknowledgements and bounded child cleanup passed");
