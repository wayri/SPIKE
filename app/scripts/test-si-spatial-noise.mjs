// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const bundle = async entry => (await build({ entryPoints: [entry], bundle: true, platform: "node", format: "esm", write: false,
  external: ["react", "react/jsx-runtime"], loader: { ".css": "empty" } })).outputFiles[0].text;
const model = await import(`data:text/javascript;base64,${Buffer.from(await bundle("src/siSpatialNoise.ts")).toString("base64")}`);
const segments = [{ id: "victim-seg-4", occurrenceId: "board-A", netId: "victim", startMm: [10, 20, 1.6], endMm: [30, 20, 1.6] }];
const context = { designId: "design-1", designDigest: "sha256:abc", requestId: "request-7", occurrenceId: "board-A", aggressorNetId: "aggressor", victimNetId: "victim", traceSegments: segments };
const result = { contract: "spike/si-spatial-noise/v1", status: "completed", modelStatus: "experimental",
  binding: { sourceDesignId: "design-1", sourceDesignDigest: "sha256:abc", requestId: "request-7", occurrenceId: "board-A", aggressorNetId: "aggressor", victimNetId: "victim" },
  sourceResult: { contract: "spike/si-coupled-channel-result/v1", resultId: "result-3", rawPointer: "/spatial_noise", modelScope: { basis: "provided_rlgc", extracted: false, limitations: ["Reviewed uniform coupled line; not general board extraction."] } }, frequenciesHz: [1e9, 2e9],
  traceSamples: [{ segmentId: "victim-seg-4", fraction: .25, inducedVoltageV: [[.003, .004], [-.002, .001]] }],
  fieldSamples: [{ id: "field-9", positionMm: [18, 18, 2.1], electricFieldVM: [[[3, 4], [0, 0], [0, 0]], [[-2, 0], [0, 1], [0, 0]]] }], issues: [] };
const admitted = model.admitSiSpatialNoise(result, context);
assert.ok(admitted); assert.deepEqual(admitted.traceSamples[0].positionMm, [15, 20, 1.6], "trace coordinates come from authoritative segment geometry");
for (const change of [
  { binding: { ...result.binding, sourceDesignId: "other" } }, { binding: { ...result.binding, sourceDesignDigest: "sha256:other" } },
  { binding: { ...result.binding, requestId: "other" } }, { binding: { ...result.binding, occurrenceId: "other" } },
  { binding: { ...result.binding, victimNetId: "other" } },
]) assert.equal(model.admitSiSpatialNoise({ ...result, ...change }, context), null);
assert.equal(model.admitSiSpatialNoise({ ...result, traceSamples: [{ ...result.traceSamples[0], segmentId: "missing" }] }, context), null);
assert.equal(model.admitSiSpatialNoise({ ...result, fieldSamples: [{ ...result.fieldSamples[0], electricFieldVM: [[[NaN, 0],[0,0],[0,0]], [[0,0],[0,0],[0,0]]] }] }, context), null);
for (const key of ["traceSamples", "fieldSamples", "frequenciesHz"]) {
  for (const malformed of [null, {}, "bad", [null]]) {
    assert.doesNotThrow(() => assert.equal(model.admitSiSpatialNoise({ ...result, [key]: malformed }, context), null), `${key} malformed input must reject without throwing`);
  }
}
assert.equal(model.admitSiSpatialNoise({ ...result, traceSamples: [...result.traceSamples, ...result.traceSamples] }, context), null, "duplicate trace location rejects");
assert.equal(model.admitSiSpatialNoise({ ...result, fieldSamples: [...result.fieldSamples, ...result.fieldSamples] }, context), null, "duplicate field sample identity rejects");
assert.equal(model.admitSiSpatialNoise(result, { ...context, traceSegments: [...segments, ...segments] }), null, "ambiguous authoritative segment identity rejects");
assert.equal(model.admitSiSpatialNoise({ ...result, traceSamples: Array.from({ length: 200001 }, () => result.traceSamples[0]) }, context), null, "sample count is bounded");
assert.deepEqual(model.siSpatialNoiseScenePosition([15, 20, 1.6], { centerX: 10, centerY: 30, scale: 2 }), [10, 20, 3.2], "all three canonical mm coordinates convert once with Y flipped");
assert.deepEqual(model.siSpatialNoiseColor(-4, [0, 10]), [0, 0, 1]);
assert.deepEqual(model.siSpatialNoiseColor(10, [0, 10]), [1, 1, 0]);
assert.deepEqual(model.siSpatialNoiseColor(7, [7, 7]), [0, 1, .5], "constant samples receive the legend midpoint color");

let display = model.buildSiSpatialNoiseDisplay(admitted, model.defaultSiSpatialNoiseSettings);
assert.equal(display.unit, "V"); assert.equal(display.values[0], .005); assert.deepEqual(display.positionsMm, [[15, 20, 1.6]]);
display = model.buildSiSpatialNoiseDisplay(admitted, { ...model.defaultSiSpatialNoiseSettings, quantity: "electric_field", component: "norm" });
assert.equal(display.unit, "V/m"); assert.equal(display.values[0], 5); assert.deepEqual(display.positionsMm, [[18, 18, 2.1]]);
assert.equal(model.buildSiSpatialNoiseDisplay(admitted, { ...model.defaultSiSpatialNoiseSettings, quantity: "electric_field", component: "norm", projection: "real" }), null, "vector norm cannot claim signed phase");
display = model.buildSiSpatialNoiseDisplay(admitted, { ...model.defaultSiSpatialNoiseSettings, quantity: "electric_field", component: "x", projection: "real", scaleLimit: 2 });
assert.equal(display.values[0], 2); assert.match(display.notices.join(" "), /source samples are unchanged/);
assert.deepEqual(model.searchSiSpatialNoiseSamples(display, "field-9"), [0]);

// The admitted 200,000-point limit exceeds JavaScript's argument-list limit.
const dense = { ...admitted, traceSamples: Array.from({ length: 200000 }, (_, index) => ({
  ...admitted.traceSamples[0], inducedVoltageV: [[index - 100000, 0], [0, 0]],
})) };
const denseDisplay = model.buildSiSpatialNoiseDisplay(dense, {
  ...model.defaultSiSpatialNoiseSettings, projection: "real",
});
assert.ok(denseDisplay);
assert.deepEqual(denseDisplay.range, [-100000, 99999]);
assert.equal(model.buildSiSpatialNoiseDisplay({ ...admitted, traceSamples: [], fieldSamples: [] }, model.defaultSiSpatialNoiseSettings), null);
assert.equal(model.buildSiSpatialNoiseDisplay({ ...dense, traceSamples: [{ ...dense.traceSamples[0], inducedVoltageV: [[NaN, 0], [0, 0]] }] }, model.defaultSiSpatialNoiseSettings), null);
assert.equal(model.buildSiSpatialNoiseDisplay(admitted, { ...model.defaultSiSpatialNoiseSettings, projection: "unsupported" }), null);

const controlCode = (await bundle("src/SiSpatialNoiseControls.tsx")).replaceAll('from "react"', `from ${JSON.stringify(new URL("../node_modules/react/index.js", import.meta.url).href)}`).replaceAll('from "react/jsx-runtime"', `from ${JSON.stringify(new URL("../node_modules/react/jsx-runtime.js", import.meta.url).href)}`);
const Controls = (await import(`data:text/javascript;base64,${Buffer.from(controlCode).toString("base64")}`)).default;
const props = { settings: model.defaultSiSpatialNoiseSettings, selectedSample: 0, query: "", onSettings() {}, onSelectSample() {}, onQuery() {} };
const html = renderToStaticMarkup(React.createElement(Controls, { ...props, data: admitted, display: model.buildSiSpatialNoiseDisplay(admitted, model.defaultSiSpatialNoiseSettings) }));
for (const text of ["Spatial SI noise", "Victim trace voltage", "Surrounding E-field", "Frequency", "Projection", "Opacity", "Scale limit", "Find sample", "experimental", "0.00500000 V"]) assert.ok(html.includes(text), text);
assert.ok(renderToStaticMarkup(React.createElement(Controls, { ...props, data: null, display: null })).includes("No spatial SI samples"));
assert.ok(renderToStaticMarkup(React.createElement(Controls, { ...props, data: null, display: null, error: "Digest mismatch", onRetry() {} })).includes("Retry data"));
const css = await readFile("src/SiSpatialNoiseControls.css", "utf8");
assert.match(css, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/, "wide layout is bounded");
assert.match(css, /@media\(max-width:520px\).*grid-template-columns:minmax\(0,1fr\)/, "narrow layout becomes one column");
assert.doesNotMatch(css, /position:\s*(fixed|absolute)/, "controls do not create a global overlay");
const viewport = await readFile("src/BoardViewport.tsx", "utf8"), workbench = await readFile("src/SiSpatialNoiseWorkbench.tsx", "utf8");
assert.match(viewport, /positions\.set\(siSpatialNoiseScenePosition\(point, boardTransformRef\.current\)/, "viewport positions every actual returned sample");
assert.match(viewport, /siSpatialNoise\?\.binding\.occurrenceId === \(selectedBoardInstanceId \?\? "active-board"\)/, "viewport rejects another board occurrence");
assert.match(viewport, /virtualBoards\.length <= 1/, "multi-board spatial overlays stay withheld");
assert.match(viewport, /scene\.remove\(group\); clearGroup\(group\)/, "spatial geometry owns cleanup");
assert.match(viewport, /onSelectSample\(hit\.index\)/, "viewport points link selection to the source sample");
assert.match(workbench, /method: "inspect_si_spatial_context"/, "binding is inspected against the current canonical design");
assert.match(workbench, /sourceDesign\.design_id/, "response source identity checked independently of imported binding");
assert.match(workbench, /Review identities and bind samples/, "import requires an explicit reviewed action");
assert.match(workbench, /token === generation\.current/, "stale context responses cannot activate a dataset");
assert.match(workbench, /source authenticity and physical qualification are unverified/, "import does not claim authenticated solver provenance");

// A bounded hook harness exercises the component's async admission protocol without a browser or native runtime.
// JSX nodes are ordinary React elements; effects/state retain their dependencies between renders.
const hookedCode = (await build({ entryPoints: ["src/SiSpatialNoiseWorkbench.tsx"], bundle: true, platform: "node", format: "esm", write: false,
  external: ["react/jsx-runtime"], loader: { ".css": "empty" }, plugins: [{ name: "spatial-workbench-harness", setup(builder) {
    builder.onResolve({ filter: /^react$/ }, () => ({ path: "hooks", namespace: "spatial-test" }));
    builder.onResolve({ filter: /\/workerBridge$/ }, () => ({ path: "worker", namespace: "spatial-test" }));
    builder.onResolve({ filter: /\/panelPresentation$/ }, () => ({ path: "panel", namespace: "spatial-test" }));
    builder.onLoad({ filter: /.*/, namespace: "spatial-test" }, args => ({ contents: args.path === "hooks"
      ? ["useState", "useRef", "useMemo", "useEffect"].map(name => `export const ${name} = (...args) => globalThis.__siSpatialHarness.${name}(...args);`).join("\n")
      : args.path === "worker" ? "export const isDesktopShell = () => true; export const runLocalWorker = request => globalThis.__siSpatialHarness.request(request);"
      : "export const usePanelPresentation = () => ({ownerDocument: undefined});" }));
  } }] })).outputFiles[0].text.replaceAll('from "react/jsx-runtime"', `from ${JSON.stringify(new URL("../node_modules/react/jsx-runtime.js", import.meta.url).href)}`);
const Workbench = (await import(`data:text/javascript;base64,${Buffer.from(hookedCode).toString("base64")}`)).default;
function hookHarness(props) {
  const slots = [], effects = [], requests = [], notifications = [];
  let cursor = 0, dirty = true, tree;
  const same = (a, b) => a && b && a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
  const harness = {
    useState(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { value: typeof initial === "function" ? initial() : initial,
        set(value) { const next = typeof value === "function" ? value(slots[index].value) : value; if (!Object.is(next, slots[index].value)) { slots[index].value = next; dirty = true; } } };
      return [slots[index].value, slots[index].set];
    },
    useRef(initial) { const index = cursor++; return slots[index] ??= { current: initial }; },
    useMemo(make, deps) { const index = cursor++; if (!slots[index] || !same(slots[index].deps, deps)) slots[index] = { deps, value: make() }; return slots[index].value; },
    useEffect(effect, deps) { const index = cursor++; if (!slots[index] || !same(slots[index].deps, deps)) { const old = slots[index]; slots[index] = { deps }; effects.push(() => { old?.cleanup?.(); slots[index].cleanup = effect(); }); } },
    request(request) { return new Promise(resolve => requests.push({ request, resolve })); },
    render(change = {}) {
      props = { ...props, ...change }; dirty = true; globalThis.__siSpatialHarness = harness;
      let turns = 0;
      while (dirty) { assert.ok(++turns < 30, "hook rendering settles"); dirty = false; cursor = 0; tree = Workbench({ ...props, onDisplay: value => notifications.push(value) }); effects.splice(0).forEach(effect => effect()); }
      return tree;
    },
    unmount() { slots.forEach(slot => slot.cleanup?.()); },
    get tree() { return tree; }, requests, notifications,
  };
  return harness;
}
const children = node => Array.isArray(node) ? node.flatMap(children) : node && typeof node === "object" ? [node, ...children(node.props?.children)] : [];
const textOf = node => Array.isArray(node) ? node.map(textOf).join("") : node && typeof node === "object" ? textOf(node.props?.children) : String(node ?? "");
const button = (h, text) => children(h.tree).find(node => node.type === "button" && textOf(node).includes(text));
const settle = async h => { await new Promise(resolve => setImmediate(resolve)); h.render(); };
const sourceDesign = { contract: "spike/design-ir/v2", design_id: "design-1", nets: [{ id: "aggressor", name: "Source" }, { id: "victim", name: "Victim" }] };
const h = hookHarness({ design: sourceDesign, occurrenceId: "board-A" }); h.render();
assert.equal(h.requests.length, 0, "mount never executes a solver or context operation");
const importInput = children(h.tree).find(node => node.type === "input" && node.props.type === "file");
importInput.props.onChange({ target: { files: [{ name: "samples.json", size: 1024, text: async () => JSON.stringify(result) }], value: "" } });
await settle(h);
assert.equal(h.requests.length, 0, "import proposes identities without admitting data or calling worker");
assert.equal(h.notifications.at(-1), null);
assert.equal(button(h, "Review identities").props.disabled, false);
button(h, "Review identities").props.onClick(); h.render();
assert.equal(h.requests[0].request.params.design, sourceDesign);
assert.equal(h.requests[0].request.params.request_id, "request-7");
h.requests[0].resolve({ ok: true, result: context }); await settle(h);
assert.equal(h.notifications.at(-1).display.values[0], .005, "reviewed current context admits actual samples");
assert.equal(h.notifications.at(-1).origin, "imported");
const admittedPositions = h.notifications.at(-1).display.positionsMm;
h.notifications.at(-1).onSelectSample(0); h.render();
assert.equal(h.notifications.at(-1).display.positionsMm, admittedPositions, "probe selection reuses sample geometry");
const renderedControls = children(h.tree).find(node => typeof node.type === "function" && node.props.onSettings);
renderedControls.props.onSettings({ ...renderedControls.props.settings, opacity: .3 }); h.render();
assert.equal(h.notifications.at(-1).display.opacity, .3);
assert.equal(h.notifications.at(-1).display.positionsMm, admittedPositions, "opacity changes reuse sample geometry");
button(h, "Review identities").props.onClick(); h.render();
h.render({ design: { ...sourceDesign, design_id: "changed-revision" } });
h.requests[1].resolve({ ok: true, result: context }); await settle(h);
assert.equal(h.notifications.at(-1), null, "late previous-design response cannot reactivate samples");
h.unmount();

const pairHarness = hookHarness({ design: sourceDesign, occurrenceId: "board-A" }); pairHarness.render();
const inputs = children(pairHarness.tree);
inputs.find(node => node.type === "select" && node.props.children[0].props.children === "Choose current source net").props.onChange({ target: { value: "aggressor" } });
inputs.find(node => node.type === "select" && node.props.children[0].props.children === "Choose current victim net").props.onChange({ target: { value: "victim" } });
inputs.find(node => node.type === "input" && node.props.maxLength === 512).props.onChange({ target: { value: "request-7" } });
inputs.find(node => node.type === "textarea").props.onChange({ target: { value: JSON.stringify({ pair_request: { contract: "spike/rlgc-coupled-pair-request/v1" }, aggressor_segment_id: "source-1", victim_segment_id: "victim-seg-4" }) } });
pairHarness.render();
assert.equal(pairHarness.requests.length, 0, "editing a supplied pair never executes it");
button(pairHarness, "Run supplied pair").props.onClick(); pairHarness.render();
assert.equal(pairHarness.requests[0].request.method, "run_si_spatial_pair");
assert.equal(pairHarness.requests[0].request.params.design, sourceDesign);
assert.equal(pairHarness.requests[0].request.params.aggressor_net_id, "aggressor");
pairHarness.requests[0].resolve({ ok: true, result: { context, data: result } }); await settle(pairHarness);
assert.equal(pairHarness.notifications.at(-1).origin, "supplied_pair");
button(pairHarness, "Run supplied pair").props.onClick(); pairHarness.render();
pairHarness.unmount();
const notificationCount = pairHarness.notifications.length;
pairHarness.requests[1].resolve({ ok: true, result: { context, data: result } }); await new Promise(resolve => setImmediate(resolve));
assert.equal(pairHarness.notifications.length, notificationCount, "unmounted pair response has no callback or UI state effects");
delete globalThis.__siSpatialHarness;
console.log("SI spatial noise: strict binding, authoritative trace coordinates, separate V and V/m projections, probes and responsive controls passed.");
