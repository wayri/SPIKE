// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";
const model = await importTestTypescript("guidedSimulationModel");
const { GuidedSimulationController, canLaunchGuidedRun } = model;
const context = { key: "project-A:thermal", revision: "1", workspace: "Thermal", title: "Assembly thermal" };
const blocker = { id: "contact", title: "Thermal contact missing", detail: "Declare the contact between the chosen solids.", severity: "blocker", route: "contacts" };
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
let checks = 0, runs = 0, supplied = [blocker];
const adapter = { check: async () => { checks++; return { requirements: supplied }; }, run: async () => { runs++; } };
const controller = new GuidedSimulationController(context, adapter);
await controller.launch(); assert.equal(checks, 0, "unchecked state cannot launch");
await controller.check(); assert.equal(controller.snapshot().phase, "blocked");
await controller.launch(); assert.equal(runs, 0, "required inputs cannot be bypassed");
supplied = []; await controller.check(); assert.equal(canLaunchGuidedRun(controller.snapshot()), true);
supplied = [blocker]; await controller.launch(); assert.equal(runs, 0, "Run rechecks even a previously ready setup");
supplied = [{ ...blocker, severity: "warning" }]; await controller.check();
await controller.launch(); assert.equal(runs, 1); assert.equal(controller.snapshot().phase, "launched");
await controller.launch(); assert.equal(runs, 1, "double launch is blocked");
const pending = deferred(); let staleRuns = 0, receivedSignal;
const stale = new GuidedSimulationController(context, { check: async (_context, signal) => { receivedSignal = signal; return pending.promise; }, run: async () => { staleRuns++; } });
const awaiting = stale.check(); stale.cancel(); pending.resolve({ requirements: [] }); await awaiting;
assert.equal(receivedSignal.aborted, true); assert.equal(stale.snapshot().phase, "cancelled"); assert.equal(staleRuns, 0);
const launchCheck = deferred(); let launchChecks = 0;
const changedWhileLaunching = new GuidedSimulationController(context, { check: async () => ++launchChecks === 1 ? { requirements: [] } : launchCheck.promise, run: async () => { staleRuns++; } });
await changedWhileLaunching.check(); const launching = changedWhileLaunching.launch(); changedWhileLaunching.dispose();
launchCheck.resolve({ requirements: [] }); await launching; assert.equal(staleRuns, 0, "late Run preflight cannot submit after context disposal");
const runFailure = new GuidedSimulationController(context, { check: async () => ({ requirements: [] }), run: async () => { throw new Error("Backend admission rejected the setup"); } });
await runFailure.check(); await runFailure.launch(); assert.equal(runFailure.snapshot().phase, "error"); assert.match(runFailure.snapshot().error, /Backend admission/);
const failing = new GuidedSimulationController(context, { check: async () => { throw new Error("Worker unavailable"); }, run: adapter.run });
await failing.check(); assert.equal(failing.snapshot().phase, "error"); assert.match(failing.snapshot().error, /Worker unavailable/);
const malformed = new GuidedSimulationController(context, { check: async () => ({ requirements: [{ ...blocker, severity: "success" }] }), run: adapter.run });
await malformed.check(); assert.equal(malformed.snapshot().phase, "error", "malformed adapter admission never looks ready");

// Execute the component with a small deterministic hook host, including cleanup replay.
const states = [], refs = [], memos = [], effects = []; let index = 0, queued = [], tree;
const same = (a, b) => a && b && a.length === b.length && a.every((value, i) => Object.is(value, b[i]));
const react = {
  useState(initial) { const at = index++; if (!(at in states)) states[at] = typeof initial === "function" ? initial() : initial; return [states[at], value => { states[at] = typeof value === "function" ? value(states[at]) : value; }]; },
  useRef(value) { return refs[index++] ??= { current: value }; },
  useMemo(fn, deps) { const at = index++; if (!same(memos[at]?.deps, deps)) memos[at] = { deps, value: fn() }; return memos[at].value; },
  useEffect(fn, deps) { const at = index++; if (!same(effects[at]?.deps, deps)) queued.push(() => { effects[at]?.cleanup?.(); effects[at] = { fn, deps, cleanup: fn() }; }); },
};
const jsx = (type, props) => ({ type, props: props ?? {} });
const compiled = ts.transpileModule(readFileSync(new URL("../src/GuidedSimulationRun.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", compiled)(name => name === "react" ? react : name === "react/jsx-runtime" ? { jsx, jsxs: jsx } : name === "./guidedSimulationModel" ? model : {}, module, module.exports);
let closed = 0, fixes = [], uiRuns = 0, uiRequirements = [blocker];
let uiChecks=0;
let props = { context, intent: "run", adapter: { check: async () => {uiChecks++;return { requirements: uiRequirements };}, run: async () => { uiRuns++; } }, onFix: item => fixes.push(item), onClose: () => closed++, steps: [{ id: "geometry", title: "Choose geometry", detail: "Select the assembly.", route: "geometry" }, { id: "values", title: "Define values", detail: "Apply material values.", route: "values" }] };
const nodes = node => !node || typeof node !== "object" ? [] : [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)];
const render = () => { index = 0; queued = []; tree = module.exports.default(props); queued.forEach(fn => fn()); return tree; };
const tick = async () => { await Promise.resolve(); await Promise.resolve(); render(); };
const button = label => nodes(tree).find(node => node.type === "button" && node.props.children === label);
render(); await tick(); assert.equal(button("Run simulation").props.disabled, true);
button("Resolve this item").props.onClick(); assert.equal(fixes[0].id, "contact");
uiRequirements = []; button("Recheck setup").props.onClick(); await tick(); assert.equal(button("Run simulation").props.disabled, false);
button("Run simulation").props.onClick(); button("Run simulation").props.onClick(); await tick(); assert.equal(uiRuns, 1);
const checksBeforeEdit=uiChecks;
props = { ...props, context: { ...context, revision: "2" }, intent: "tutor" }; uiRequirements = [blocker]; render(); await tick();
assert.equal(button("Run simulation").props.disabled, true, "changed revision discards readiness");
assert.equal(uiChecks,checksBeforeEdit,"draft edits invalidate readiness without rebuilding a mesh on every keystroke");
button("Next").props.onClick(); render(); assert.match(JSON.stringify(tree), /Define values/); assert.equal(button("Next").props.disabled, true);
button("Back").props.onClick(); render(); assert.match(JSON.stringify(tree), /Choose geometry/);
effects.forEach(effect => { if (effect) { effect.cleanup?.(); effect.cleanup = effect.fn(); } }); await tick();
assert.equal(button("Run simulation").props.disabled, true, "effect replay keeps checks working");
nodes(tree).find(node => node.props["aria-label"] === "Close simulation guide").props.onClick(); assert.equal(closed, 1);
effects.forEach(effect => effect?.cleanup?.());
console.log("Guided simulation controller and component checks passed.");
