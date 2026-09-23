import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const source = readFileSync(resolve(import.meta.dirname, "..", "src", "SpiceWorkbench.tsx"), "utf8");
const appSource = readFileSync(resolve(import.meta.dirname, "..", "src", "App.tsx"), "utf8");
assert.ok(source.includes('useState<RunEngine>(initialEngine)'), "workbench must honor the manager engine selection at mount");
assert.ok(appSource.includes('initialEngine={solverSelections.owned_circuit_workspace === "spike.owned_spice_workspace" ? "owned_spice" : "native_mna"}'), "persisted owned circuit selection must reach the workbench");
assert.ok(appSource.includes('workloadId === "owned_circuit_workspace" && selectedSolverId === "spike.owned_spice_workspace"'), "owned circuit selection must have an explicit workflow route");
for (const fragment of [
  'type RunEngine = "native_mna" | "peec_mna" | "owned_spice" | "ngspice"',
  'SPIKES owned engine (experimental)',
  'method: "validate_owned_spice_workspace"',
  'method: "run_owned_spice_workspace"',
  'contract: "spike/owned-spice-workspace-request/v1"',
  'resource_limits: ownedLimits',
  'assembly_scope: assemblyScope',
  'Explicit probe descriptors',
  'activeRunId.current',
  'exportOwnedResult',
  'saveNativeTextFile("spikes-owned-circuit-result.json", JSON.stringify(ownedResult, null, 2), "result")',
  'session-only',
]) assert.ok(source.includes(fragment), `owned SPIKES workbench integration is missing: ${fragment}`);

assert.ok(source.indexOf('method: "validate_owned_spice_workspace"') < source.indexOf('method: "run_owned_spice_workspace"'), "owned SPIKES must validate before execution");
assert.ok(!source.includes('normalizeSolverResult(payload.circuit_result)'), "owned circuit results must not be fabricated as board solver results");

const require = createRequire(import.meta.url);
const module = { exports: {} };
const componentSource = readFileSync(resolve(import.meta.dirname, "..", "src", "OwnedSpiceResult.tsx"), "utf8");
assert.ok(componentSource.includes("OWNED CIRCUIT RESULT"), "owned result renderer must identify its separate circuit-only result");
const compiled = ts.transpileModule(componentSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function("require", "module", "exports", compiled)(name => name === "react" ? React : require(name), module, module.exports);
const { OwnedCircuitResultView, parseOwnedProbeDescriptors } = module.exports;
assert.deepEqual(parseOwnedProbeDescriptors(" V(out) \nV(vplus,vminus)\n\n I(V1) "), ["V(out)", "V(vplus,vminus)", "I(V1)"], "one-line parsing must retain differential probe commas");
const html = renderToStaticMarkup(React.createElement(OwnedCircuitResultView, { result: {
  status: "completed", model_status: "experimental", netlist_sha256: "0123456789abcdef",
  circuit_result: {
    probes: { "V(vplus,vminus)": { descriptor: { quantity: "node_voltage" }, values: [0.1, 0.2, 0.3] } },
    measurements: { ripple: { value: 0.2, unit: "V" } },
    data: { time_s: [0, 1e-6, 2e-6], node_voltage_v: { out: [1, 1.1, 1.2] } },
  },
} }));
assert.match(html, /V\(vplus,vminus\)/);
assert.match(html, /3 samples: 0\.1000000, 0\.2000000, 0\.3000000/);
assert.match(html, /ripple/);
assert.match(html, /time_s/);
assert.match(html, /node_voltage_v/);
console.log("owned SPIKES workbench parser and rendered circuit result assertions passed");
