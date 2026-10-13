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
for (const method of ['review_engineering', 'quick_engineering_tool', 'run_em_machine', 'run_magnetic_machine', 'prepare_assembly_em', 'run_assembly_em', 'run_assembly_field_transient', 'run_assembly_electrothermal', 'evaluate_electrical_heat_source', 'prepare_pcb_electrothermal_geometry', 'solve_fan_system_operating_point']) {
  assert.equal(bridge.isHeavyWorkerMethod(method), true, `${method} must receive heavy-worker supervision`);
}
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};

// Native progress frames preserve operation correlation and malformed frames
// never reach the active study listener.
{
  let nativeListener;
  const received = [];
  globalThis.__spikeWorkerListen = (event, listener) => {
    assert.equal(event, "spike-worker-progress");
    nativeListener = listener;
    return () => undefined;
  };
  const unlisten = await bridge.subscribeWorkerProgress(progress => received.push(progress));
  nativeListener({ payload: { operationId: "transient-1", method: "run_assembly_field_transient", frame: { step: 2 } } });
  nativeListener({ payload: { operationId: "", method: "run_assembly_field_transient", frame: { step: 3 } } });
  nativeListener({ payload: { operationId: "transient-1", method: "run_assembly_field_transient", frame: [] } });
  assert.deepEqual(received, [{ operationId: "transient-1", method: "run_assembly_field_transient", frame: { step: 2 } }]);
  unlisten();
}

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

// Initial package reads own a cancellable slot, including native project dispatch.
{
  const run = deferred();
  globalThis.__spikeWorkerInvoke = command => {
    if (command === "run_project_worker") return run.promise;
    if (command === "cancel_worker") return true;
    throw new Error(command);
  };
  const pending = bridge.runNativeProjectWorker({id:"package-open",method:"read_project_package",params:{path:"example.spike"}});
  const duplicate = await bridge.runNativeProjectWorker({id:"package-duplicate",method:"read_project_package"});
  assert.equal(duplicate.type,"WorkerBusyError");
  assert.equal(await bridge.cancelLocalWorker("package-open"),true);
  run.resolve({ok:true});
  assert.equal((await pending).type,"WorkerCancelledError");
}
