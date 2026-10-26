// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";

const bundle = async (entry, plugins = []) => (await build({ entryPoints: [entry], bundle: true, platform: "node", format: "esm", write: false,
  external: ["react/jsx-runtime"], loader: { ".css": "empty" }, plugins })).outputFiles[0].text;
const load = code => import(`data:text/javascript;base64,${Buffer.from(code.replaceAll('from "react/jsx-runtime"', `from ${JSON.stringify(new URL("../node_modules/react/jsx-runtime.js", import.meta.url).href)}`)).toString("base64")}`);
const model = await load(await bundle("src/siDeploymentWorkspace.ts"));
const endpoint = { text: "[IBIS Ver] 4.2", name: "owned.ibs", model: "owned-model", component: "owned", pin: "1", corner: "typ", capacitance_corner: "min", package_corner: "max" };
const request = { contract: "spike/ibis-behavioral-request/v1", driver: endpoint, receiver: { ...endpoint, pin: "2" },
  stimulus: { initial_state: "low", transitions: [{ time_s: 1e-9, state: "high", waveform_indices: [0, 1] }] },
  interconnect: { kind: "series_resistor", resistance_ohm: 50 }, analysis: { time_step_s: 1e-11, stop_time_s: 2e-9 } };
const ibisResult = { contract: "spike/ibis-behavioral-result/v1", status: "completed", model_status: "experimental", production_qualified: false,
  request_sha256: "a".repeat(64), time_s: [0, 2e-9], probes: { driver_pad_v: [0, 1], receiver_pad_v: [0, 1], driver_die_v: [0, 1], receiver_die_v: [0, 1] } };
const ibis = { contract: "spike/ibis-deployment-workspace/v1", request, result: ibisResult, resultRequest: structuredClone(request), draft: "editable pending JSON",
  compiled: { status: "ready" }, runtime: { status: "available", executable: "untrusted-path" }, trusted: true };
const reopened = model.coerceIbisDeploymentWorkspace(JSON.parse(JSON.stringify(ibis)));
assert.deepEqual(reopened.request, request); assert.deepEqual(reopened.result, ibisResult); assert.equal(reopened.draft, ibis.draft);
for (const key of ["compiled", "runtime", "trusted"]) assert.equal(Object.hasOwn(reopened, key), false, `reopen strips ${key}`);
assert.equal(model.coerceIbisDeploymentWorkspace({ ...ibis, request: { ...request, analysis: { ...request.analysis, stop_time_s: 3e-9 } } }).result, null, "a request edit revokes saved evidence");
for (const mutation of [{ time_s: [0, NaN] }, { time_s: [1, 0] }, { probes: {} }, { request_sha256: "unknown" }, { probes: { ...ibisResult.probes, driver_pad_v: [1] } }]) {
  assert.equal(model.coerceIbisDeploymentWorkspace({ ...ibis, result: { ...ibisResult, ...mutation } })?.result ?? null, null, "malformed result cannot restore");
}
for (const value of [null, [], {}, { ...ibis, contract: "future/v9" }, { ...ibis, request: { contract: request.contract } }, { ...ibis, draft: "x".repeat(model.SI_WORKSPACE_BYTES + 1) }]) assert.equal(model.coerceIbisDeploymentWorkspace(value), null);
const cyclic = {}; cyclic.self = cyclic;
for (const value of [cyclic, { number: Infinity }, { missing: undefined }, new Date(), { sparse: Array(4) }, { text: "\u20ac".repeat(9 * 1024 * 1024) }]) assert.equal(model.boundedSiWorkspaceJson(value), false);
const segments = [{ id: "victim-seg", occurrenceId: "board-A", netId: "victim", startMm: [0, 0, 0], endMm: [10, 0, 0] }];
const context = { designId: "design-1", designDigest: "sha256:current", requestId: "reviewed-request", occurrenceId: "board-A", aggressorNetId: "aggressor", victimNetId: "victim", traceSegments: segments };
const samples = { contract: "spike/si-spatial-noise/v1", status: "completed", modelStatus: "experimental",
  binding: { sourceDesignId: context.designId, sourceDesignDigest: context.designDigest, requestId: context.requestId, occurrenceId: "board-A", aggressorNetId: "aggressor", victimNetId: "victim" },
  sourceResult: { contract: "spike/si-coupled-channel-result/v1", rawPointer: "/spatial_noise", modelScope: { basis: "provided_rlgc", extracted: false, limitations: ["Supplied uniform line only"] } },
  frequenciesHz: [1e9], traceSamples: [{ segmentId: "victim-seg", fraction: .5, inducedVoltageV: [[.003, .004]] }] };
const pairDraft = JSON.stringify({ pair_request: { contract: "spike/rlgc-coupled-pair-request/v1" }, aggressor_segment_id: "source-seg", victim_segment_id: "victim-seg" });
const spatial = { contract: "spike/si-spatial-workspace/v1", candidate: samples, fileName: "samples.json", aggressor: "aggressor", victim: "victim", requestId: "reviewed-request", pairDraft,
  settings: { quantity: "induced_voltage", frequencyIndex: 0, projection: "real", component: "norm", phaseDeg: 20, opacity: .3, scaleLimit: .1 },
  capture: { data: samples }, admitted: true, context, display: { trusted: true } };
const restoredSpatial = model.coerceSpatialDeploymentWorkspace(JSON.parse(JSON.stringify(spatial)));
assert.deepEqual(restoredSpatial.candidate, samples); assert.equal(restoredSpatial.pairDraft, pairDraft); assert.deepEqual(restoredSpatial.settings, spatial.settings);
for (const key of ["capture", "admitted", "context", "display"]) assert.equal(Object.hasOwn(restoredSpatial, key), false, `reopen strips ${key}`);
assert.equal(model.coerceSpatialDeploymentWorkspace({ ...spatial, requestId: "independent-user-request" }).requestId, "independent-user-request", "imported identities cannot replace reviewed controls");
assert.equal(model.coerceSpatialDeploymentWorkspace({ ...spatial, settings: { opacity: 8, frequencyIndex: -4, projection: "invented" } }).settings.opacity, .72);
assert.equal(model.coerceSpatialDeploymentWorkspace({ ...spatial, contract: "future/v9" }), null);

const hookPlugin = { name: "si-deployment-harness", setup(builder) {
  builder.onResolve({ filter: /^react$/ }, () => ({ path: "hooks", namespace: "si-test" }));
  builder.onResolve({ filter: /\/workerBridge$/ }, () => ({ path: "worker", namespace: "si-test" }));
  builder.onResolve({ filter: /\/panelPresentation$/ }, () => ({ path: "panel", namespace: "si-test" }));
  builder.onResolve({ filter: /\/SiWorkflowPlots$/ }, () => ({ path: "plot", namespace: "si-test" }));
  builder.onResolve({ filter: /\/SolverSetupSteps$/ }, () => ({ path: "steps", namespace: "si-test" }));
  builder.onLoad({ filter: /.*/, namespace: "si-test" }, args => ({ contents: args.path === "hooks"
    ? ["useState", "useRef", "useMemo", "useEffect"].map(name => `export const ${name} = (...args) => globalThis.__siDeploymentHarness.${name}(...args);`).join("\n")
    : args.path === "worker" ? "export const isDesktopShell = () => true; export const runLocalWorker = request => globalThis.__siDeploymentHarness.request(request);"
    : args.path === "plot" ? "export const SiPlot = () => null;"
    : args.path === "steps" ? "export default function Steps() { return null; }"
    : "export const usePanelPresentation = () => ({ownerDocument: undefined});" }));
} };
const Ibis = (await load(await bundle("src/IbisBehavioralWorkbench.tsx", [hookPlugin]))).default;
const Spatial = (await load(await bundle("src/SiSpatialNoiseWorkbench.tsx", [hookPlugin]))).default;
function harness(Component, props) {
  const slots = [], effects = [], requests = [], saves = [], displays = []; let cursor = 0, dirty = true, tree;
  const same = (a, b) => a && b && a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
  const h = {
    useState(initial) { const index = cursor++; if (!slots[index]) slots[index] = { value: typeof initial === "function" ? initial() : initial,
      set(value) { const next = typeof value === "function" ? value(slots[index].value) : value; if (!Object.is(next, slots[index].value)) { slots[index].value = next; dirty = true; } } }; return [slots[index].value, slots[index].set]; },
    useRef(initial) { const index = cursor++; return slots[index] ??= { current: initial }; },
    useMemo(make, deps) { const index = cursor++; if (!slots[index] || !same(slots[index].deps, deps)) slots[index] = { deps, value: make() }; return slots[index].value; },
    useEffect(effect, deps) { const index = cursor++; if (!slots[index] || !same(slots[index].deps, deps)) { const old = slots[index]; slots[index] = { deps, effect }; effects.push(() => { old?.cleanup?.(); slots[index].cleanup = effect(); }); } },
    request(value) { return new Promise(resolve => requests.push({ value, resolve })); },
    render(change = {}) { props = { ...props, ...change }; dirty = true; globalThis.__siDeploymentHarness = h; let turns = 0;
      while (dirty) { assert.ok(++turns < 25, "changing callback identities never causes a persistence loop"); dirty = false; cursor = 0;
        tree = Component({ ...props, onWorkspaceChange: value => saves.push(value), onDisplay: value => displays.push(value) }); effects.splice(0).forEach(effect => effect()); } },
    replayEffects() { slots.filter(slot => slot.effect).forEach(slot => { slot.cleanup?.(); slot.cleanup = slot.effect(); }); h.render(); },
    unmount() { slots.forEach(slot => slot.cleanup?.()); }, get tree() { return tree; }, requests, saves, displays,
  }; h.render(); return h;
}
const children = node => Array.isArray(node) ? node.flatMap(children) : node && typeof node === "object" ? [node, ...children(node.props?.children)] : [];
const textOf = node => Array.isArray(node) ? node.map(textOf).join("") : node && typeof node === "object" ? textOf(node.props?.children) : String(node ?? "");
const button = (h, text) => children(h.tree).find(node => node.type === "button" && textOf(node).includes(text));
const settle = async h => { await new Promise(resolve => setImmediate(resolve)); h.render(); };
const changeStep = (h, value) => { children(h.tree).find(node => node.props?.label === "Behavioral IBIS steps").props.onChange(value); h.render(); };
const i = harness(Ibis, { workspace: ibis }); changeStep(i, "run");
assert.equal(i.requests.length, 0, "reopening does not compile, inspect or run");
assert.equal(i.saves.length, 0, "reopening IBIS is read-only"); i.replayEffects(); assert.equal(i.saves.length, 0, "StrictMode effect replay never dirties the IBIS project");
assert.equal(button(i, "Run behavioral").props.disabled, true, "saved readiness and native trust never restore");
assert.match(textOf(i.tree), /Restored saved evidence/);
const exampleRequest = { ...request, driver: { ...request.driver, model: "reviewed-example" } };
i.render({ stagedExample: { token: 1, requestText: JSON.stringify(exampleRequest) } });
assert.equal(i.saves.length, 0, "staging preserves the current setup and evidence without a save callback");
changeStep(i, "stimulus"); assert.equal(children(i.tree).find(node => node.type === "textarea" && !node.props.readOnly).props.value, ibis.draft); changeStep(i, "run");
button(i, "Apply staged behavioral").props.onClick(); i.render();
assert.deepEqual(i.saves.at(-1).request, exampleRequest); assert.equal(i.saves.at(-1).result, null); assert.equal(i.requests.length, 0);
assert.equal(i.saves.length, 1, "one explicit setup change publishes once"); i.render(); i.replayEffects(); assert.equal(i.saves.length, 1, "unchanged renders and effect replay do not republish");
button(i, "Compile and check").props.onClick(); i.render(); i.requests.at(-1).resolve({ ok: true, result: { status: "ready", diagnostics: [] } }); await settle(i);
const pathInput = children(i.tree).find(node => node.type === "input" && node.props.placeholder?.startsWith("Full path"));
pathInput.props.onChange({ target: { value: "C:/local/ngspice.exe" } }); i.render();
button(i, "Inspect local").props.onClick(); i.render(); assert.equal(i.requests.at(-1).value.params.executable, "C:/local/ngspice.exe");
i.requests.at(-1).resolve({ ok: true, result: { status: "available", executable: "C:/local/ngspice.exe", executable_sha256: "b".repeat(64) } }); await settle(i);
children(i.tree).find(node => node.type === "input" && node.props.type === "checkbox").props.onChange({ target: { checked: true } }); i.render();
assert.equal(button(i, "Run behavioral").props.disabled, false);
button(i, "Run behavioral").props.onClick(); i.render(); i.requests.at(-1).resolve({ ok: true, result: ibisResult }); await settle(i);
assert.deepEqual(i.saves.at(-1).resultRequest, exampleRequest, "new results retain the exact active request snapshot");
assert.equal(Object.hasOwn(i.saves.at(-1), "runtime"), false);
children(i.tree).find(node => node.type === "input" && node.props.placeholder?.startsWith("Full path")).props.onChange({ target: { value: "C:/other/ngspice.exe" } }); i.render();
assert.equal(button(i, "Run behavioral").props.disabled, true, "runtime path changes revoke native trust");
button(i, "Compile and check").props.onClick(); i.render(); const staleIbis = i.requests.at(-1); i.unmount(); const oldSaves = i.saves.length;
staleIbis.resolve({ ok: true, result: { status: "ready" } }); await new Promise(resolve => setImmediate(resolve)); assert.equal(i.saves.length, oldSaves, "unmounted responses never save into another project");

const design = { design_id: "design-1", nets: [{ id: "aggressor" }, { id: "victim" }] };
const s = harness(Spatial, { workspace: spatial, design, occurrenceId: "board-A" });
assert.equal(s.requests.length, 0); assert.equal(s.displays.at(-1), null, "saved samples remain unadmitted");
assert.equal(s.saves.length, 0, "reopening spatial data is read-only"); s.replayEffects(); assert.equal(s.saves.length, 0, "StrictMode replay never dirties the spatial workspace");
const nextSamples = { ...samples, sourceResult: { ...samples.sourceResult, resultId: "new-example" } };
s.render({ stagedExample: { token: 2, solverText: pairDraft, samplesText: JSON.stringify(nextSamples) } });
assert.equal(s.saves.length, 0, "staging cannot replace or republish the old candidate");
button(s, "Apply staged spatial").props.onClick(); s.render(); assert.equal(s.requests.length, 0); assert.deepEqual(s.saves.at(-1).candidate, nextSamples);
assert.equal(s.saves.length, 1, "one spatial apply publishes once"); s.render(); assert.equal(s.saves.length, 1, "read-only rerenders never republish");
assert.equal(s.saves.at(-1).requestId, spatial.requestId, "applying preserves independently reviewed controls");
button(s, "Review identities").props.onClick(); s.render(); assert.equal(s.requests.at(-1).value.params.request_id, spatial.requestId);
s.requests.at(-1).resolve({ ok: true, result: context }); await settle(s); assert.equal(s.displays.at(-1).display.opacity, .3, "rebound data retains saved display preferences");
button(s, "Review identities").props.onClick(); s.render(); const pending = s.requests.at(-1);
s.render({ design: { ...design, design_id: "changed-source" } }); pending.resolve({ ok: true, result: context }); await settle(s);
assert.equal(s.displays.at(-1), null, "late previous-source admission cannot activate an overlay"); s.unmount();
const run = harness(Spatial, { workspace: spatial, design, occurrenceId: "board-A" });
button(run, "Run supplied pair").props.onClick(); run.render(); run.requests.at(-1).resolve({ ok: true, result: { context, data: nextSamples } }); await settle(run);
assert.equal(run.saves.at(-1).candidate.sourceResult.resultId, "new-example", "latest solved raw samples replace an earlier imported candidate for reopen");
assert.equal(Object.hasOwn(run.saves.at(-1).candidate.traceSamples[0], "positionMm"), false, "derived geometry is recomputed from current source on rebind");
const reopenedRun = harness(Spatial, { workspace: run.saves.at(-1), design, occurrenceId: "board-A" });
assert.equal(reopenedRun.requests.length, 0); assert.equal(reopenedRun.displays.at(-1), null); assert.equal(reopenedRun.saves.length, 0);
const emptyIbis = harness(Ibis, {}), emptySpatial = harness(Spatial, { design, occurrenceId: "board-A" });
emptyIbis.replayEffects(); emptySpatial.replayEffects(); assert.equal(emptyIbis.saves.length, 0); assert.equal(emptySpatial.saves.length, 0, "opening empty SI panels never creates a saved workspace");
emptyIbis.unmount(); emptySpatial.unmount();
reopenedRun.unmount(); run.unmount(); delete globalThis.__siDeploymentHarness;
console.log("SI deployment workspace: bounded save/reopen, source invalidation, explicit staged apply, inert reopen and native trust revocation passed.");
