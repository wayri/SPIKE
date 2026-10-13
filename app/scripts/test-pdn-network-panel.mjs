// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import vm from "node:vm";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const source = readFileSync(new URL("../src/PdnNetworkPanel.tsx", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS,
  target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const localRequire = createRequire(import.meta.url), loaded = { exports: {} };
const requireComponent = name => {
  if (name.endsWith(".css")) return {};
  if (name === "./workerBridge") return { isDesktopShell: () => false, runLocalWorker: () => { throw Error("No fake solver execution"); } };
  if (name === "./InteractivePlot") return { default: () => React.createElement("div", null, "plot") };
  return localRequire(name);
};
vm.runInThisContext(`(function(require,module,exports){${code}\n})`)(requireComponent, loaded, loaded.exports);
const { default: Panel, examplePdnRequest, validPdnNetworkResult } = loaded.exports;
const request = examplePdnRequest("AGND");
assert.equal(request.reference, "AGND");
assert.equal(request.ports[0].negative, "AGND");
assert.equal(request.elements[0].negative, "AGND");
const html = renderToStaticMarkup(React.createElement(Panel, { groundNets: ["AGND"], availableNets: ["PGND", "CHASSIS"], onSave: () => {}, onClose: () => {} }));
for (const phrase of ["PDN ground reference", "AGND", "CHASSIS", "Add net", "Add DM choke", "Add coupled CM choke", "Add series capacitor leg", "leakage", "Browser preview"]) assert.ok(html.includes(phrase), phrase);
assert.ok(/disabled=""[^>]*>Run AC/.test(html), "browser authoring cannot claim a native run");
assert.ok(source.includes("operation.current !== id"), "late responses must be discarded after stop");
assert.ok(source.includes("version !== revision.current"), "setup edits must invalidate late results");
assert.ok(source.includes("setResult(null)"), "editing retires stale curves");
const root = resolve(".."), python = resolve(root, ".venv/Scripts/python.exe");
const result = JSON.parse(execFileSync(python, ["-c", "import json,sys; from python.spike_core.pdn_network import evaluate_pdn_network; print(json.dumps(evaluate_pdn_network(json.load(sys.stdin)),allow_nan=False))"],
  { cwd: root, input: JSON.stringify(request), encoding: "utf8" }));
assert.equal(result.contract, "spike/pdn-network-result/v1");
assert.equal(result.reference, "AGND");
assert.equal(result.ac.length, 6);
assert.equal(result.load_transient.points.length, 101);
assert.ok(result.diagnostics.max_ac_relative_residual < 1e-10);
assert.equal(validPdnNetworkResult(result), true, "actual backend result admitted");
assert.equal(validPdnNetworkResult({ ...result, ac: [{ frequency_hz: 1, impedance_ohm: [] }] }), false);
const nonfinite = structuredClone(result); nonfinite.ac[0].impedance_ohm[0][0].real = NaN;
assert.equal(validPdnNetworkResult(nonfinite), false, "nonfinite curves rejected");
assert.equal(validPdnNetworkResult({ ...result, ac: [null] }), false);
console.log("PDN panel ground defaults, authoring/templates, stale-result guards and actual Python backend passed; no native visual qualification claimed.");
