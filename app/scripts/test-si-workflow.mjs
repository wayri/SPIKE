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
  if (name === "react") return { ...React, useState: initial => [typeof initial === "function" ? initial() : initial === "channel" ? "endpoints" : initial, update => updates.push(update)] };
  if (name.endsWith(".css") || name === "./workerBridge") return {};
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
