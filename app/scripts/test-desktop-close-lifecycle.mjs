// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.window = { __TAURI_INTERNALS__: {} };
const bridge = await import("../src/workerBridge.ts");
const calls = [];
let nativeListener, legacyListener, unlistens = 0, destroys = 0;
globalThis.__spikeWorkerListen = (event, listener) => {
  assert.equal(event, "spike:main-close-requested");
  nativeListener = listener;
  return () => { unlistens += 1; };
};
globalThis.__spikeCloseWindow = {
  onCloseRequested(listener) { legacyListener = listener; return () => { unlistens += 1; }; },
  destroy() { destroys += 1; },
};
const supported = command => {
  calls.push(command);
  return command === "main_close_recovery_supported" ? true : undefined;
};
globalThis.__spikeWorkerInvoke = (command, args) => {
  calls.push([command, args]);
  return command === "main_close_recovery_supported" ? true : undefined;
};

// The actual bridge acknowledges the handler's synchronous decision, including
// listener cleanup, malformed requests and exceptions that preserve recovery.
let stop = await bridge.subscribeDesktopCloseRequested(() => undefined);
nativeListener({ payload: { requestId: 1 } });
assert.deepEqual(calls.at(-1), ["respond_main_close", { requestId: 1, decision: "close" }]);
stop();
assert.equal(unlistens, 1);
stop = await bridge.subscribeDesktopCloseRequested(preventDefault => preventDefault());
nativeListener({ payload: { requestId: 2 } });
assert.deepEqual(calls.at(-1), ["respond_main_close", { requestId: 2, decision: "defer" }]);
const count = calls.length;
nativeListener({ payload: { requestId: "invalid" } });
assert.equal(calls.length, count);
stop();
const errors = [];
const originalError = console.error;
console.error = (...args) => errors.push(args);
stop = await bridge.subscribeDesktopCloseRequested(() => { throw new Error("renderer callback failed"); });
const beforeThrow = calls.length;
nativeListener({ payload: { requestId: 3 } });
assert.equal(calls.length, beforeThrow, "failed callback must leave native timeout pending");
assert.equal(errors.length, 1);
stop();
globalThis.__spikeWorkerInvoke = command => command === "main_close_recovery_supported"
  ? true : Promise.reject(new Error("IPC interrupted"));
stop = await bridge.subscribeDesktopCloseRequested(() => undefined);
nativeListener({ payload: { requestId: 4 } });
await new Promise(resolve => setImmediate(resolve));
assert.equal(errors.length, 2, "failed acknowledgement must be reported");
stop();
console.error = originalError;

// Explicit approval reaches native shutdown, including if assistant destruction
// rejects or hangs. Fake only the timeout, leaving the bridge under test intact.
globalThis.__spikeWorkerInvoke = supported;
await bridge.closeDesktopWindow();
assert.equal(calls.at(-1), "close_main_application");
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
  assert.equal(calls.at(-1), "close_main_application");
  assert.equal(warnings.length, 1);
  let rejectChild;
  const child = new Promise((_, reject) => { rejectChild = reject; });
  const pending = bridge.closeDesktopWindow(() => child);
  await Promise.resolve();
  timeout();
  await pending;
  assert.equal(calls.at(-1), "close_main_application");
  assert.equal(warnings.length, 2);
  assert.equal(cleared, 3);
  rejectChild(new Error("late child rejection"));
  await new Promise(resolve => setImmediate(resolve));
} finally {
  globalThis.setTimeout = originalSetTimeout;
  globalThis.clearTimeout = originalClearTimeout;
  console.warn = originalWarn;
}

// Hosts missing precisely the probe command retain the established API; other
// probe failures propagate instead of silently disabling recovery.
globalThis.__spikeWorkerInvoke = () => Promise.reject("Command main_close_recovery_supported not found");
stop = await bridge.subscribeDesktopCloseRequested(preventDefault => preventDefault());
let prevented = false;
legacyListener({ preventDefault() { prevented = true; } });
assert.equal(prevented, true);
stop();
await bridge.closeDesktopWindow();
assert.equal(destroys, 1);
globalThis.__spikeWorkerInvoke = () => false;
await bridge.closeDesktopWindow();
assert.equal(destroys, 2);
globalThis.__spikeWorkerInvoke = () => Promise.reject(new Error("IPC unavailable"));
await assert.rejects(bridge.subscribeDesktopCloseRequested(() => undefined), /IPC unavailable/);
await assert.rejects(bridge.closeDesktopWindow(), /IPC unavailable/);
assert.equal(destroys, 2);
delete window.__TAURI_INTERNALS__;
await bridge.subscribeDesktopCloseRequested(() => { assert.fail("browser callback"); });
await bridge.closeDesktopWindow(() => { assert.fail("browser cleanup"); });

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
assert.ok(app.includes("await closeDesktopWindow(closeOwnedAssistantWindow);"),
  "save/discard approval must use bounded assistant cleanup");
assert.ok(!app.includes("await closeOwnedAssistantWindow();"),
  "unbounded assistant shutdown must not block approved main close");
console.log("Desktop close decisions, native recovery acknowledgements, legacy fallback and bounded child cleanup passed");
