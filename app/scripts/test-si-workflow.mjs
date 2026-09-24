import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRequire } from "node:module";

const workflowUi = readFileSync(new URL("../src/SiWorkflowWorkbench.tsx", import.meta.url), "utf8");
assert.match(workflowUi, /<table className="si-endpoint-table">/);
assert.match(workflowUi, /<th scope="col">Port<\/th>/);
assert.match(workflowUi, /Bound IBIS values override matching editable parameters/);

// Render the actual endpoint page, not just markup string checks. Worker calls
// are not needed to edit the source/receiver setup.
const require = createRequire(import.meta.url);
const uiModule = { exports: {} };
const catalog = JSON.parse(readFileSync(new URL("../src/siWorkflowCatalog.json", import.meta.url), "utf8"));
const uiCode = ts.transpileModule(workflowUi, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
} }).outputText;
const updates = [];
new Function("require", "module", "exports", uiCode)(name => {
  if (name === "react") return { ...React, useEffect: () => {}, useState: initial => [typeof initial === "function" ? initial() : initial === "channel" ? "endpoints" : initial, update => updates.push(update)] };
  if (name.endsWith(".css")) return {};
  if (name === "./workerBridge") return { isDesktopShell: () => true };
  if (name === "./siWorkflowCatalog.json") return catalog;
  if (name === "./SiWorkflowPlots") return { __esModule: true, default: () => null, SiPlot: () => null };
  return require(name);
}, uiModule, uiModule.exports);
const tree = uiModule.exports.default({ design: null, onStatus() {} });
const html = renderToStaticMarkup(tree);
assert.equal((html.match(/class="si-endpoint-table"/g) ?? []).length, 2, 'source and receiver groups both use tables');
assert.match(html, /Primary source/);
assert.match(html, /Receiver 1/);
assert.ok(!html.includes('class="si-endpoint"'), 'legacy cards must not remain');
const nodes = node => !node || typeof node !== "object" ? [] : Array.isArray(node) ? node.flatMap(nodes) : [node, ...nodes(node.props?.children)];
nodes(tree).find(node => node.props?.["aria-label"] === "source 1 port (1-based)").props.onChange({ target: { value: "3" } });
assert.equal(updates[0](catalog.defaults).sources[0].port, 2, 'displayed ports preserve zero-based worker mapping');

// Exercise stateful workflow actions, including occupied ports, imports during
// a run, browser admission, partial results and operation defaults.
function mountWorkflow({ desktop = true, setup = catalog.defaults, worker } = {}) {
  const state = [], statuses = [];
  let cursor = 0;
  const module = { exports: {} };
  const request = structuredClone(setup);
  new Function("require", "module", "exports", uiCode)(name => {
    if (name === "react") return { ...React, useEffect: () => {}, useState: initial => {
      const index = cursor++;
      if (!(index in state)) state[index] = typeof initial === "function" ? initial() : initial;
      return [state[index], value => { state[index] = typeof value === "function" ? value(state[index]) : value; }];
    } };
    if (name.endsWith(".css")) return {};
    if (name === "./workerBridge") return { isDesktopShell: () => desktop, runLocalWorker: worker };
    if (name === "./siWorkflowCatalog.json") return { ...catalog, defaults: request };
    if (name === "./SiWorkflowPlots") return { __esModule: true, default: () => null, SiPlot: () => null };
    return require(name);
  }, module, module.exports);
  const render = () => { cursor = 0; return module.exports.default({ design: null, onStatus: s => statuses.push(s) }); };
  const button = label => nodes(render()).find(node => node.type === "button" && textOf(node.props.children).includes(label));
  const click = label => { const found = button(label); assert.ok(found, `button ${label} exists`); found.props.onClick(); };
  return { render, button, click, statuses, setup: () => state[0] };
}
function textOf(node) {
  if (Array.isArray(node)) return node.map(textOf).join("");
  return node && typeof node === "object" ? textOf(node.props?.children) : String(node ?? "");
}
const flow = mountWorkflow();
flow.click("Sources / receivers");
flow.click("Add source");
assert.equal(flow.setup().sources[1].port, 1);
flow.click("Add receiver");
assert.equal(flow.setup().receivers[1].port, 3, "new receivers must avoid every occupied source/receiver port");
assert.equal(flow.button("Add source").props.disabled, true, "full channel cannot add another endpoint");
assert.equal(flow.button("Add receiver").props.disabled, true);
const twoPortSetup = structuredClone(catalog.defaults);
twoPortSetup.channel.coupled = false;
twoPortSetup.receivers[0].port = 1;
const twoPort = mountWorkflow({ setup: twoPortSetup });
twoPort.click("Network edits");
nodes(twoPort.render()).find(node => node.type === "select" && node.props.value === "renormalize").props.onChange({ target: { value: "reorder" } });
assert.ok(nodes(twoPort.render()).some(node => node.type === "input" && node.props.value === "1,2"));
twoPort.click("Add operation");
assert.deepEqual(twoPort.setup().edits[0].ports, [0, 1]);
const browser = mountWorkflow({ desktop: false });
assert.equal(browser.button("Run loaded SI study").props.disabled, true);
assert.match(textOf(browser.render()), /Open the SPIKE desktop app/);
let finish;
const pending = mountWorkflow({ worker: () => new Promise(resolve => { finish = resolve; }) });
pending.click("Run loaded SI study");
assert.ok(pending.button("Stop SI study"));
assert.equal(nodes(pending.render()).find(node => node.type === "input" && node.props.accept === ".json").props.disabled, true);
finish({ ok: true, result: { contract: "spike/si-workflow-result/v1", request: catalog.defaults, status: "partial" } });
await new Promise(resolve => setImmediate(resolve));
assert.match(pending.statuses.at(-1), /partial results/);
assert.equal(pending.button("Run loaded SI study").props.disabled, false);

const workbenchCode = ts.transpileModule(readFileSync(new URL("../src/SParameterWorkbench.tsx", import.meta.url), "utf8"), { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
} }).outputText;
let capturedGeometryRequest;
function mountProtocol(props = {}) {
  const state = [], effects = [];
  let cursor = 0;
  const module = { exports: {} };
  new Function("require", "module", "exports", workbenchCode)(name => {
    if (name === "react") return { ...React,
      useState: initial => { const index = cursor++; if (!(index in state)) state[index] = typeof initial === "function" ? initial() : initial; return [state[index], value => { state[index] = typeof value === "function" ? value(state[index]) : value; }]; },
      useEffect: effect => effects.push(effect), useMemo: read => read(), useRef: value => ({ current: value }),
    };
    if (name === "./workerBridge") return { isDesktopShell: () => true, runSiProtocolTestSuite: async () => { throw new Error("fixture worker failure"); }, runSiUniformChannel: async (_design, request) => { capturedGeometryRequest = request; return { ok: false, error: "fixture channel stop" }; } };
    if (["./sparameters", "./numericRange"].includes(name)) return {};
    if (["./SiChannelResultPanel", "./SiWorkflowWorkbench"].includes(name)) return { __esModule: true, default: () => null };
    return require(name);
  }, module, module.exports);
  const render = () => { cursor = 0; return module.exports.default({ assemblyDesigns: null, canonicalDesign: null, onClose() {}, onStatus() {}, ...props }); };
  render(); effects.splice(0).forEach(effect => effect());
  return { render, setProps(next) { Object.assign(props, next); effects.length = 0; render(); effects.splice(0).forEach(effect => effect()); } };
}
const reusedProtocol = mountProtocol();
assert.equal(nodes(reusedProtocol.render()).find(node => node.type === "button" && textOf(node.props.children) === "Source-to-receiver workflow").props.className, "primary-btn");
reusedProtocol.setProps({ suite: { id: "later", name: "Later suite", family: "DDR" } });
assert.equal(nodes(reusedProtocol.render()).find(node => node.type === "button" && textOf(node.props.children) === "Geometry / protocol / network inspection").props.className, "primary-btn", "opening a suite in the already mounted workbench must select its configuration");
const protocol = mountProtocol({ suite: { id: "fixture", name: "Fixture suite", family: "DDR" }, canonicalDesign: {
  contract: "spike/design-ir/v2", design_id: "fixture", nets: [{ id: "sig", name: "DQ0" }, { id: "gnd", name: "GND" }], layers: [{ id: "bottom", name: "B.Cu", layer_type: "copper" }],
} });
assert.equal(nodes(protocol.render()).find(node => node.type === "button" && textOf(node.props.children) === "Geometry / protocol / network inspection").props.className, "primary-btn", "selected protocol suites must open their own configuration");
nodes(protocol.render()).find(node => node.type === "button" && textOf(node.props.children).includes("Run experimental SI channel")).props.onClick();
assert.ok(nodes(protocol.render()).some(node => node.type === "button" && textOf(node.props.children).includes("Stop SI channel")), "running protocol work can be cancelled");
await new Promise(resolve => setImmediate(resolve));
assert.match(textOf(protocol.render()), /fixture worker failure/);
assert.ok(nodes(protocol.render()).some(node => node.type === "button" && textOf(node.props.children).includes("Run experimental SI channel")), "worker rejection must restore the run action");

const crosstalk = mountProtocol({ initialView: "geometry", initialFocus: "crosstalk", canonicalDesign: {
  contract: "spike/design-ir/v2", design_id: "coupled", nets: [{ id: "sig", name: "TX" }, { id: "victim", name: "RX" }, { id: "gnd", name: "GND" }], layers: [{ id: "bottom", name: "B.Cu", layer_type: "copper" }],
} });
const runCrosstalk = () => nodes(crosstalk.render()).find(node => node.type === "button" && textOf(node.props.children).includes("Run NEXT / FEXT"));
runCrosstalk().props.onClick();
assert.match(textOf(crosstalk.render()), /Choose a separate victim net/);
const victimSelect = nodes(crosstalk.render()).find(node => node.type === "select" && textOf(node.props.children).includes("No separate victim"));
victimSelect.props.onChange({ target: { value: "victim" } });
runCrosstalk().props.onClick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(capturedGeometryRequest.victim_net, "victim", "NEXT/FEXT sends the explicit victim to the existing coupled-line solver");

const source = readFileSync(new URL("../src/sparameters.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { parseTouchstone, trace } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const rowMajor = "# Hz S RI R 50\n0 " + Array.from({ length: 16 }, (_, i) => `${i / 20} 0`).join(" ");
const network = parseTouchstone("fixture.s4p", rowMajor);
assert.equal(network.matrices[0][0][1].re, 0.05);
assert.equal(network.matrices[0][1][0].re, 0.2);
assert.equal(trace(network, 1, 0)[0].magnitude, 0.2);
const legacy = parseTouchstone("fixture.s2p", "# Hz S RI R 50\n0 0 0 0.8 0 0.2 0 0 0");
assert.equal(legacy.matrices[0][1][0].re, 0.8);
assert.equal(legacy.matrices[0][0][1].re, 0.2);
console.log("SI workflow Touchstone direction assertions passed");
