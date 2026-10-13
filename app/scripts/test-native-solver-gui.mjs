// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fileURLToPath } from "node:url";
import { readFile } from "node:fs/promises";
async function load(name) {
  const bundle = await build({ entryPoints: [fileURLToPath(new URL(`../src/${name}`, import.meta.url))], bundle: true, write: false, format: "esm", platform: "node", external: ["react"], loader: { ".css": "empty" }, plugins: [{ name: "plot-render-only", setup(build) { build.onResolve({ filter: /InteractivePlot$/ }, () => ({ path: "plot", namespace: "stub" })); build.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ contents: "export default function Plot(){return null}" })); } }] });
  const code = bundle.outputFiles[0].text.replaceAll('from "react"', `from ${JSON.stringify(new URL("../node_modules/react/index.js", import.meta.url).href)}`).replaceAll('from "react/jsx-runtime"', `from ${JSON.stringify(new URL("../node_modules/react/jsx-runtime.js", import.meta.url).href)}`);
  return import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
}
const model = await load("solverExtensionModel.ts");
const x = model.defaultXyceParameters();
assert.throws(() => model.xyceParameters(x, "run"), /netlist/);
assert.equal(model.xyceParameters(x, "preflight").operation, "preflight");
assert.equal(model.xyceParameters({ ...x, netlist: "test\n.END", engine_options: { timeout_seconds: "10", memory_limit_mib: "256" } }, "run").engine_options.timeout_seconds, 10);
assert.throws(() => model.xyceParameters({ ...x, netlist: "circuit", engine_options: { timeout_seconds: Infinity, memory_limit_mib: 256 } }, "run"), /finite/);
const p = model.defaultPalaceParameters();
assert.throws(() => model.palaceParameters(p, "prepare"), /mesh/);
const mesh = { ...p, mesh_path: "C:\\case\\mesh.msh" };
assert.throws(() => model.palaceParameters(mesh, "run"), /SHA-256/);
assert.equal(model.palaceParameters({ ...mesh, expected_mesh_sha256: "a".repeat(64) }, "run").threads, 1);
assert.throws(() => model.palaceParameters({ ...mesh, threads: 2 }, "prepare"), /threads/);
assert.throws(() => model.palaceParameters({ ...mesh, config: { Problem: {} } }, "prepare"), /Model/);
assert.throws(() => model.parseSolverJson("[]", "config"), /object/);
const tables = model.solverTables({ data: { tables: [{ name: "mode", headers: ["f (Hz)", "value"], rows: [["1e9", "2"], ["NaN", "3"], ["", "4"], ["5", "Infinity"]] }] } });
assert.deepEqual(tables[0].rows, [[1e9, 2]]);
assert.deepEqual(model.solverTables({ waveforms: [{ name: "tran", columns: [{ name: "TIME", unit: "s" }, { name: "V(out)", unit: "V" }], rows: [[0, 1]] }] })[0].columns[1], { name: "V(out)", unit: "V" });
const props = { parameters: {}, onParameters() {}, onExecute() {}, disabled: true };
const { PalaceExtension } = await load("PalaceExtension.tsx");
const { XyceExtension } = await load("XyceExtension.tsx");
const palace = renderToStaticMarkup(React.createElement(PalaceExtension, props));
for (const label of ["BoundaryMode", "Domains native JSON", "Boundaries native JSON", "Solver native JSON", "Model.L0", "Run PALACE", "Reviewed mesh SHA-256"]) assert.ok(palace.includes(label), label);
assert.match(palace, /<fieldset disabled=""/);
const xyce = renderToStaticMarkup(React.createElement(XyceExtension, { ...props, result: { data: { status: "failed", solved: false, diagnostics: [{ severity: "error", code: "runtime_missing", message: "Choose executable" }], artifacts: [{ name: "log.txt", bytes: 42, sha256: "digest" }], waveforms: [{ name: "wave", columns: ["TIME", "V(out)"], rows: [[0, 1]] }] } } }));
for (const label of ["Native Xyce netlist", "Validate netlist", "Inspect retained case", "runtime_missing", "Choose executable", "No solved result returned", "log.txt", "Not production qualified", "Y axis"]) assert.ok(xyce.includes(label), label);
console.log("Native solver GUI: worker parameters, bounded resources, digest review, disabled controls, finite plots and truthful failure/results passed.");
const { NativeSolverFieldPreview } = await load("NativeSolverFieldPreview.tsx");
const field = renderToStaticMarkup(React.createElement(NativeSolverFieldPreview, { previews: [{ name: "electric.vtu", status: "available", points: [[0, 1, 2], [NaN, 0, 0]], coordinate_units_m: 0.001, source_point_count: 3000, sampled: true, arrays: [{ name: "E_real", components: 3, units: "V/m", values: [[1, 2, 3], [4, 5, 6]] }] }] }));
for (const label of ["1 finite displayed samples", "3000 native points", "Vector magnitude (displayed norm)", "Probe retained node", "0.001 m", "V/m", "no interpolation"]) assert.ok(field.includes(label), label);
const css = await readFile(new URL("../src/ExternalSolver.css", import.meta.url), "utf8");
assert.match(css, /\.external-solver \{[^}]*grid-template-columns: minmax\(0, 1fr\)/);
assert.match(css, /\.external-solver fieldset \{[^}]*min-inline-size: 0;[^}]*box-sizing: border-box/);
assert.match(css, /\.external-solver > \*, \.external-solver section \{[^}]*min-inline-size: 0/);
assert.match(css, /\.solver-fields \{[^}]*minmax\(min\(100%, 220px\), 1fr\)/);
assert.match(css, /\.solver-actions \{[^}]*flex-wrap: wrap/);
assert.match(css, /\.solver-scroll \{[^}]*overflow: auto;[^}]*max-width: 100%/);

const { extensionWorkspaceRoutes } = await load("ExtensionWorkspaceRoutes.ts");
for (const [directory, workspaces] of [["palace_suite", ["em", "pi", "si"]], ["xyce_suite", ["pi", "si"]]]) {
  const manifest = JSON.parse(await readFile(new URL(`../../extensions/${directory}/spike-extension.json`, import.meta.url), "utf8"));
  for (const workspace of workspaces) {
    const routes = extensionWorkspaceRoutes([{ ...manifest, trusted: true }], workspace, "solve");
    assert.equal(routes.length, 1, `${directory} must be selectable in ${workspace}`);
    assert.equal(routes[0].enabled, true);
    assert.equal(routes[0].trusted, true);
  }
}
