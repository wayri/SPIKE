// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";

const source = readFileSync(resolve(import.meta.dirname, "../src/piQuickTune.ts"), "utf8"), module = { exports: {} };
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
new Function("module", "exports", output)(module, module.exports);
const { adjustPiLoadFromWheel, createPiQuickTuneScheduler } = module.exports;

const load = (id, net, value, anchorId = `${id}-pad`) => ({ id, name: id, net, value, anchorId, anchorType: "pad", x: "1", y: "2" });
const setup = { net: "VCC", loads: [load("L1", "VCC", "1.2")], untouched: true };
let result = adjustPiLoadFromWheel(setup, { net: "VCC", occurrenceId: "board-A", deltaY: -1, altKey: false }, "board-A");
assert.equal(result.currentA, 1.3); assert.equal(result.stepA, 0.1); assert.equal(result.setup.loads[0].value, "1.3"); assert.equal(setup.loads[0].value, "1.2");
result = adjustPiLoadFromWheel(result.setup, { net: "VCC", occurrenceId: "board-A", deltaY: 2, altKey: true }, "board-A");
assert.equal(result.currentA, 1.29); assert.equal(result.stepA, 0.01);
const zero = adjustPiLoadFromWheel({ ...setup, loads: [load("L1", "", "0.02")] }, { net: "VCC", occurrenceId: "A", deltaY: 1, altKey: false }, "A");
assert.equal(zero.currentA, 0, "decrement clamps at zero without inventing a maximum");
const ambiguous = { ...setup, loads: [load("a", "VCC", "1"), load("b", "VCC", "2")] };
assert.throws(() => adjustPiLoadFromWheel(ambiguous, { net: "VCC", occurrenceId: "A", deltaY: -1, altKey: false }, "A"), /ambiguous/);
assert.equal(adjustPiLoadFromWheel(ambiguous, { net: "VCC", occurrenceId: "A", terminalId: "b", deltaY: -1, altKey: false }, "A").terminalId, "b");
assert.throws(() => adjustPiLoadFromWheel({ ...setup, loads: [load("a", "VCC", "1", "")] }, { net: "VCC", occurrenceId: "A", deltaY: -1, altKey: false }, "A"), /anchored load/);
const coordinate = { ...load("coordinate", "", "0.5", ""), anchorType: "coordinate", x: "0", y: "-2.5" };
assert.equal(adjustPiLoadFromWheel({ ...setup, loads: [coordinate] }, { net: "VCC", occurrenceId: "A", deltaY: -1, altKey: false }, "A").currentA, 0.6);
assert.throws(() => adjustPiLoadFromWheel({ ...setup, loads: [{ ...load("a", "VCC", "1"), x: "" }] }, { net: "VCC", occurrenceId: "A", deltaY: -1, altKey: false }, "A"), /anchored load/);
assert.throws(() => adjustPiLoadFromWheel(setup, { net: "VCC", occurrenceId: "B", deltaY: -1, altKey: false }, "A"), /occurrence/);
assert.throws(() => adjustPiLoadFromWheel(setup, { net: "GND", occurrenceId: "A", deltaY: -1, altKey: false }, "A"), /net/);
assert.throws(() => adjustPiLoadFromWheel({ ...setup, loads: [load("L1", "VCC", "NaN")] }, { net: "VCC", occurrenceId: "A", deltaY: -1, altKey: false }, "A"), /finite nonnegative/);

assert.throws(() => adjustPiLoadFromWheel({ ...setup, loads: [load("same", "VCC", "1"), { ...load("same", "VCC", "2"), anchorId: "" }] }, { net: "VCC", occurrenceId: "A", terminalId: "same", deltaY: -1, altKey: false }, "A"), /unique/);

function fakeTimers() {
  let id = 0; const callbacks = new Map();
  return { setTimer(callback) { callbacks.set(++id, callback); return id; }, clearTimer(handle) { callbacks.delete(handle); }, fire() { const pending = [...callbacks.values()]; callbacks.clear(); pending.forEach(callback => callback()); }, count: () => callbacks.size };
}
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
let timers = fakeTimers(), runs = [];
let scheduler = createPiQuickTuneScheduler({ run: async value => { runs.push(value); }, setTimer: timers.setTimer, clearTimer: timers.clearTimer });
scheduler.schedule(1); scheduler.schedule(2); scheduler.schedule(3); assert.equal(timers.count(), 1); timers.fire(); await tick(); assert.deepEqual(runs, [3], "burst runs only the latest value");

timers = fakeTimers(); runs = []; const releases = [];
scheduler = createPiQuickTuneScheduler({ run: value => new Promise(resolve => { runs.push(value); releases.push(resolve); }), setTimer: timers.setTimer, clearTimer: timers.clearTimer });
scheduler.schedule("first"); timers.fire(); await tick(); assert.equal(scheduler.isBusy(), true);
scheduler.schedule("old"); scheduler.schedule("latest"); timers.fire(); await tick(); assert.deepEqual(runs, ["first"], "busy scheduler does not overlap runs");
releases.shift()(); await tick(); assert.deepEqual(runs, ["first", "latest"], "latest elapsed request runs after busy completion"); releases.shift()(); await tick();

timers = fakeTimers(); runs = []; const staleReleases = [];
scheduler = createPiQuickTuneScheduler({ run: value => new Promise(resolve => { runs.push(value); staleReleases.push(resolve); }), setTimer: timers.setTimer, clearTimer: timers.clearTimer });
scheduler.schedule("stale-running"); timers.fire(); await tick(); scheduler.invalidate(); scheduler.schedule("new-generation"); timers.fire(); await tick();
assert.deepEqual(runs, ["stale-running"], "invalidation does not permit overlap with a stale active run");
staleReleases.shift()(); await tick(); assert.deepEqual(runs, ["stale-running", "new-generation"]); staleReleases.shift()(); await tick();

timers = fakeTimers(); runs = [];
scheduler = createPiQuickTuneScheduler({ run: async value => { runs.push(value); }, setTimer: timers.setTimer, clearTimer: timers.clearTimer });
scheduler.schedule("stale"); scheduler.invalidate(); timers.fire(); await tick(); assert.deepEqual(runs, []);
scheduler.schedule("disposed"); scheduler.dispose(); timers.fire(); assert.equal(scheduler.schedule("ignored"), false); await tick(); assert.deepEqual(runs, []);

timers = fakeTimers(); runs = []; const errors = [];
scheduler = createPiQuickTuneScheduler({ run: async value => { runs.push(value); if (value === "bad") throw new Error("failed"); }, onError: error => errors.push(error.message), setTimer: timers.setTimer, clearTimer: timers.clearTimer });
scheduler.schedule("bad"); timers.fire(); await tick(); assert.deepEqual(errors, ["failed"]); assert.equal(scheduler.isBusy(), false);
scheduler.schedule("recovered"); timers.fire(); await tick(); assert.deepEqual(runs, ["bad", "recovered"]);

console.log("PI quick tune: anchored load selection, occurrence isolation, wheel steps, debounce, serialization, invalidation and recovery passed.");
