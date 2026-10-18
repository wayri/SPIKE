// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { solverSuiteCatalog as catalog, solverSuiteGroups, filterSolverSuite, solverSuiteStatusLabels } from "../src/solverSuiteCatalog.ts";
const root = new URL("../../", import.meta.url);
const actions = new Set(["spice", "pi", "si", "thermal", "em", "native-cfd", "machines", "extensions", "workers", "python"]);
assert.equal(new Set(catalog.map(item => item.id)).size, catalog.length, "Stable unique capability identities");
for (const item of catalog) {
  assert.ok(solverSuiteGroups.includes(item.group), item.id);
  assert.ok(item.status in solverSuiteStatusLabels, item.id);
  assert.ok(item.summary.length > 25 && item.limits.length > 25, `${item.id}: scope and limits required`);
  for (const path of [item.reference, item.source]) assert.ok(existsSync(new URL(path, root)), `${item.id}: missing evidence ${path}`);
  if (item.status === "planned") assert.equal(item.action, undefined, "Unavailable capability cannot be routed for execution");
  else assert.ok(actions.has(item.action), `${item.id}: known workspace entry route required`);
  if (item.extensionId) {
    const directory = item.extensionId.replace("spike.", "").replaceAll("-", "_");
    const manifest = JSON.parse(readFileSync(new URL(`extensions/${directory}/spike-extension.json`, root), "utf8"));
    assert.equal(manifest.id, item.extensionId, `${item.id}: actual extension identity`);
  }
}
for (const id of ["circuit-adaptive", "circuit-equations", "circuit-smps", "circuit-pdk", "circuit-tcad", "pi-dielectric-ac", "pi-reduction", "thermal-pwm", "cfd-native", "cfd-su2", "si-eye", "em-magnetic"]) assert.ok(catalog.some(item => item.id === id), `Recent capability missing: ${id}`);
assert.equal(catalog.find(item => item.id === "cfd-native").status, "experimental");
assert.match(catalog.find(item => item.id === "cfd-native").limits, /Isothermal.*no thermal\/CAD/);
assert.match(catalog.find(item => item.id === "circuit-tcad").limits, /no biased carrier transport/);
assert.match(catalog.find(item => item.id === "circuit-pdk").limits, /synthetic NMOS/);
assert.match(catalog.find(item => item.id === "em-palace").limits, /no live accuracy qualification/);
assert.ok(filterSolverSuite("  conservative CHARGE  ").some(item => item.id === "circuit-equations"));
assert.ok(filterSolverSuite("admittance", "Power integrity", "experimental").every(item => item.group === "Power integrity" && item.status === "experimental"));
assert.equal(filterSolverSuite("not-a-capability-xyz").length, 0);
assert.ok(filterSolverSuite("", "all", "planned").length > 0);
const bundle = await build({ entryPoints: [fileURLToPath(new URL("../src/SolverSuitePanel.tsx", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node", external: ["react", "react/jsx-runtime"], loader: { ".css": "empty" }, plugins: [{ name: "catalog-icons", setup(build) { build.onResolve({ filter: /\/icons$/ }, () => ({ path: "icons", namespace: "stub" })); build.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ contents: "export const Search = () => null; export const X = () => null; export const Boxes = () => null; export const GitBranch = () => null; export const Package = () => null;" })); } }] });
const code = bundle.outputFiles[0].text.replaceAll('from "react"', `from ${JSON.stringify(new URL("../node_modules/react/index.js", import.meta.url).href)}`).replaceAll('from "react/jsx-runtime"', `from ${JSON.stringify(new URL("../node_modules/react/jsx-runtime.js", import.meta.url).href)}`);
const { default: SolverSuitePanel } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
const html = renderToStaticMarkup(React.createElement(SolverSuitePanel, { onClose() {}, onOpenWorkflow() {}, initialView: "capabilities" }));
for (const label of ["Runtime availability has not been probed here", "Search solver capabilities", "Filter solver domain", "Filter solver status", "Evidence reference", "Scope limit:", "Open circuit / Studio handoff", "Open Python workspace", "Unavailable"]) assert.ok(html.includes(label), `Missing user state: ${label}`);
assert.equal((html.match(/class="solver-suite-card"/g) ?? []).length, catalog.length);
assert.equal((html.match(/disabled="">Unavailable/g) ?? []).length, catalog.filter(item => item.status === "planned").length);
assert.ok(!html.includes('href="docs/'), "References must not navigate to raw filesystem paths");
const modelBundle = await build({ entryPoints: [fileURLToPath(new URL("../src/solverManagerModel.ts", import.meta.url))], bundle: true, write: false, format: "esm", platform: "node" });
const manager = await import(`data:text/javascript;base64,${Buffer.from(modelBundle.outputFiles[0].text).toString("base64")}`);
assert.equal(manager.filterManagerCapabilities(catalog, "SPIKE 2.5D PI", "internal")[0].id, "pi-peec");
assert.equal(manager.filterManagerCapabilities(catalog, "spike.peec_2_5d", "all")[0].id, "pi-peec");
assert.ok(manager.filterManagerCapabilities(catalog, "", "external").every(item => item.status === "external"));
assert.equal(manager.runtimeSolverOrigin({ id: "spike.ngspice" }), "external");
assert.equal(manager.runtimeWorkflow({ id: "spike.fullwave_3d" }), undefined, "Declared unavailable kernel has no run route");
assert.equal(manager.runtimeWorkflow({ id: "spike.peec_2_5d" }).action, "pi");
assert.equal(new Set(catalog.map(manager.solverDisplayName)).size, catalog.length, "Unique user-facing names");
for (const text of ["SPIKE 3D PI - DC conduction", "SPIKE 3D Structural", "SPIKE Thermoelastic", "Filter solver provider", "Worker registry", "Internal solvers and models / Power integrity", "External engine adapters / Electromagnetics"]) assert.ok(html.includes(text), text);
const probedHtml = renderToStaticMarkup(React.createElement(SolverSuitePanel, {
  onClose() {}, onOpenWorkflow() {}, initialView: "capabilities", runtimeProbed: true,
  runtimeSolvers: [{ id: "spike.peec_2_5d", name: "Legacy name", state: "unavailable", model_status: "unsupported", runnable: false, reason: "Runtime missing" },
                   { id: "external.new-engine", name: "New adapter", state: "unavailable", model_status: "unsupported" }],
}));
assert.ok(probedHtml.includes("Worker catalog loaded; execution remains separately gated."));
assert.ok(probedHtml.includes("Reported state: unavailable"));
assert.ok(probedHtml.includes("Not runnable through the generic registry route."));
assert.ok(probedHtml.includes("external.new-engine"), "Unknown worker entries must remain discoverable");
console.log(`Solver suite: ${catalog.length} capability scopes, evidence files, extension identities, routes, filters and rendered admission notice passed.`);

