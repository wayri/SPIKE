import assert from "node:assert/strict";

const events = [];
globalThis.window = {
  __TAURI_INTERNALS__: {},
  dispatchEvent(event) { events.push(event.detail); },
};
globalThis.CustomEvent = class CustomEvent {
  constructor(_name, init) { this.detail = init.detail; }
};

const bridge = await import("../src/workerBridge.ts");
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};

// Cancellation wins over a late successful result and duplicate dispatch is rejected.
{
  events.length = 0;
  const run = deferred();
  let runCalls = 0;
  globalThis.__spikeWorkerInvoke = (command) => {
    if (command === "run_worker") { runCalls += 1; return run.promise; }
    if (command === "cancel_worker") return true;
    throw new Error(command);
  };
  const pending = bridge.runLocalWorker({ id: "late-success", method: "run_analysis" });
  const duplicate = await bridge.runLocalWorker({ id: "duplicate", method: "run_analysis" });
  assert.equal(duplicate.type, "WorkerBusyError");
  assert.equal(runCalls, 1);
  assert.equal(await bridge.cancelLocalWorker(), true);
  assert.equal(events.at(-1).phase, "cancelling");
  assert.equal(events.at(-1).heavy, true);
  run.resolve({ ok: true, result: { partial: true } });
  const result = await pending;
  assert.equal(result.type, "WorkerCancelledError");
  assert.equal(events.at(-1).phase, "cancelled");
  assert.equal(events.at(-1).heavy, true);
  assert.equal(events.some(event => event.phase === "completed" && event.operationId === "late-success"), false);
}

// A rejected/unknown cancellation is cleaned up and cannot poison a later request ID.
{
  globalThis.__spikeWorkerInvoke = (command) => command === "cancel_worker"
    ? false
    : { ok: true, result: { accepted: true } };
  assert.equal(await bridge.cancelLocalWorker("reused-id"), false);
  const result = await bridge.runLocalWorker({ id: "reused-id", method: "run_analysis" });
  assert.equal(result.ok, true);
}

// Repeated Stop calls do not let an older failed invocation erase a newer accepted one.
{
  const run = deferred();
  const firstCancel = deferred();
  let cancels = 0;
  globalThis.__spikeWorkerInvoke = (command) => {
    if (command === "run_worker") return run.promise;
    if (++cancels === 1) return firstCancel.promise;
    return true;
  };
  const pending = bridge.runLocalWorker({ id: "repeat-stop", method: "run_analysis" });
  const older = bridge.cancelLocalWorker();
  assert.equal(await bridge.cancelLocalWorker(), true);
  firstCancel.resolve(false);
  assert.equal(await older, false);
  run.resolve({ ok: true });
  assert.equal((await pending).type, "WorkerCancelledError");
}

console.log("Worker bridge cancellation races are bounded and stale results are suppressed");
