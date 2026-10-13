// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

globalThis.window = { __TAURI_INTERNALS__: {} };
const bridge = await import("../src/workerBridge.ts");
const calls = [];
let nativeListener, unlistens = 0;
globalThis.__spikeCloseWindow = {
  listen(event, listener) {
    assert.equal(event, "spike://desktop-close-requested");
    nativeListener = listener;
    return () => { unlistens += 1; };
  },
  destroy() { assert.fail("Closing only the main window strands child windows"); },
};
const supported = command => { calls.push(command); return true; };
globalThis.__spikeWorkerInvoke = (command, args) => {
  calls.push([command, args]);
  return args?.generation === 1;
};
const delivered = [];
let stop = await bridge.subscribeDesktopCloseRequested((_prevent, generation) => delivered.push(generation));
for (const generation of [1, 2, 0, -1, 1.5, NaN, "invalid"]) nativeListener({ payload: { generation } });
nativeListener({});
assert.deepEqual(delivered, [1, 2]);
assert.equal(await bridge.acknowledgeDesktopClose(1), true);
assert.equal(await bridge.acknowledgeDesktopClose(2), false, "stale ACK must not enter the save guard");
stop();
assert.equal(unlistens, 1);
// IPC failure propagates, preserving native watchdog recovery.
globalThis.__spikeWorkerInvoke = () => Promise.reject(new Error("IPC interrupted"));
await assert.rejects(bridge.acknowledgeDesktopClose(1), /IPC interrupted/);
// A renderer callback exception never fabricates an acknowledgement.
stop = await bridge.subscribeDesktopCloseRequested(() => { throw new Error("renderer callback failed"); });
const beforeThrow = calls.length;
assert.throws(() => nativeListener({ payload: { generation: 3 } }), /renderer callback failed/);
assert.equal(calls.length, beforeThrow);
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

// Missing or failed native close commands propagate; never destroy only one window.
globalThis.__spikeWorkerInvoke = () => Promise.reject(new Error("Command close_desktop_app not found"));
await assert.rejects(bridge.closeDesktopWindow(), /not found/);
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
console.log("Desktop close decisions, generation recovery acknowledgements, fail-safe native errors and bounded child cleanup passed");
