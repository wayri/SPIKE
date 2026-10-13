// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
const output = await build({ entryPoints: [fileURLToPath(new URL("../src/ExtensionWorkspacePanel.tsx", import.meta.url)), fileURLToPath(new URL("../src/ExtensionWorkspaceRoutes.ts", import.meta.url))], bundle: true, write: false, outdir: "out", format: "esm", platform: "node", external: ["react", "react-dom/server"], loader: { ".css": "empty" } });
const helperOutput = output.outputFiles.find(file => file.path.endsWith("ExtensionWorkspaceRoutes.js"));
const panelOutput = output.outputFiles.find(file => file.path.endsWith("ExtensionWorkspacePanel.js"));
const { extensionWorkspaceRoutes, extensionScalarFields, extensionScalarParameters } = await import(`data:text/javascript;base64,${Buffer.from(helperOutput.contents).toString("base64")}`);
// Resolve React from the repository before importing an in-memory bundle.
const panelCode = panelOutput.text.replaceAll('from "react/jsx-runtime"', `from ${JSON.stringify(new URL("../node_modules/react/jsx-runtime.js", import.meta.url).href)}`).replaceAll('from "react"', `from ${JSON.stringify(new URL("../node_modules/react/index.js", import.meta.url).href)}`);
const { default: Panel } = await import(`data:text/javascript;base64,${Buffer.from(panelCode).toString("base64")}`);
const React = await import("react"), { renderToStaticMarkup } = await import("react-dom/server");
const scalarSchema = { type: "object", required: ["mesh_mm", "enabled"], properties: { mesh_mm: { type: "number", minimum: .01, maximum: 10 }, enabled: { type: "boolean" }, backend: { type: "string", enum: ["native", "emcad"] }, count: { type: "integer", minimum: 1 } } };
const route = { id: "mesh-route", workspace: "mesh", operation: "mesh", label: "EMerge mesh", model_status: "unvalidated", mesh_kind: "tetrahedral", preview_contribution_id: "preview", compatible_solver_ids: ["emerge"] };
const catalog = [{ id: "spike.emerge", name: "EMerge", trusted: true, state: "loaded", contributes: { applications: [{ id: "mesh", name: "Mesh", input_schema: scalarSchema, workspace_routes: [route] }, { id: "preview", name: "Preview" }] } }];
const rows = extensionWorkspaceRoutes(catalog, "mesh", "mesh");
assert.equal(rows.length, 1); assert.equal(rows[0].contributionId, "mesh"); assert.equal(rows[0].previewContributionId, "preview");
assert.equal(rows[0].requiresBoard, true, "existing routes require a board unless explicitly declared independent");
assert.equal(extensionWorkspaceRoutes(catalog, "si", "solve").length, 0);
for (const patch of [{ preview_contribution_id: "unknown" }, { setup_contribution_id: "unknown" }, { workspace: "invented" }, { model_status: "" }, { compatible_solver_ids: "emerge" }, { operation: "shell" }, { requires_board: "false" }, { requires_board: null }]) {
  const altered = structuredClone(catalog); Object.assign(altered[0].contributes.applications[0].workspace_routes[0], patch);
  assert.equal(extensionWorkspaceRoutes(altered, "mesh").length, 0);
}
assert.equal(extensionScalarFields(scalarSchema).requiresDedicatedGui, false);
assert.equal(extensionScalarFields({ required: ["unknown"], properties: {} }).requiresDedicatedGui, true);
assert.equal(extensionScalarFields(JSON.parse('{"properties":{"__proto__":{"type":"string"}}}')).requiresDedicatedGui, true);
assert.deepEqual(extensionScalarParameters(scalarSchema, { mesh_mm: "0.5", enabled: "false", backend: "emcad", count: "2" }), { mesh_mm: .5, enabled: false, backend: "emcad", count: 2 });
assert.throws(() => extensionScalarParameters(scalarSchema, { mesh_mm: "0.5" }), /required/);
assert.throws(() => extensionScalarParameters(scalarSchema, { mesh_mm: "Infinity", enabled: "true" }), /invalid/);
assert.throws(() => extensionScalarParameters(scalarSchema, { mesh_mm: "20", enabled: "true" }), /range/);
assert.throws(() => extensionScalarParameters(scalarSchema, { mesh_mm: "1", enabled: "true", count: "1.5" }), /invalid/);
assert.throws(() => extensionScalarParameters({ properties: { geometry: { type: "object" } } }, {}), /dedicated GUI/);
assert.equal(extensionScalarFields({ allOf: [], properties: {} }).requiresDedicatedGui, true);
const props = { extensions: catalog, workspace: "mesh", operation: "mesh", selectedRouteId: rows[0].key, boardLoaded: true, onSelectRoute() {}, onConfigure() {}, onPreview() {}, onRun() {} };
const html = renderToStaticMarkup(React.createElement(Panel, props));
assert.match(html, /Qualification/); assert.match(html, /unvalidated/); assert.match(html, /Generate mesh/); assert.match(html, /mesh mm/); assert.doesNotMatch(html, /<textarea|installed ready/i);
for (const [trusted, state] of [[false, "loaded"], [true, "disabled"]]) {
  const altered = structuredClone(catalog); Object.assign(altered[0], { trusted, state });
  const blocked = renderToStaticMarkup(React.createElement(Panel, { ...props, extensions: altered }));
  assert.match(blocked, /<button disabled=""[^>]*>Generate mesh/);
}
const structured = structuredClone(catalog); structured[0].contributes.applications[0].input_schema = { properties: { geometry: { type: "array" } } };
assert.match(renderToStaticMarkup(React.createElement(Panel, { ...props, extensions: structured })), /structured inputs/);
const referenceCatalog = structuredClone(catalog);
referenceCatalog[0].contributes.applications[0].workspace_routes[0].requires_board = false;
const referenceRows = extensionWorkspaceRoutes(referenceCatalog, "mesh", "mesh");
assert.equal(referenceRows[0].requiresBoard, false);
const referenceProps = { ...props, extensions:referenceCatalog, boardLoaded:false };
const referenceHtml = renderToStaticMarkup(React.createElement(Panel, referenceProps));
assert.match(referenceHtml, /reference geometry independently of any loaded board/);
assert.doesNotMatch(referenceHtml, /Load a board/);
assert.match(referenceHtml, /<button>Preview generated case<\/button>/);
assert.match(referenceHtml, /<button>Generate mesh<\/button>/);
assert.match(renderToStaticMarkup(React.createElement(Panel,{...props,boardLoaded:false})), /<button disabled=""[^>]*>Generate mesh/);
for (const [trusted,state,busy] of [[false,"loaded",false],[true,"disabled",false],[true,"loaded",true]]) {
  const blockedCatalog=structuredClone(referenceCatalog); Object.assign(blockedCatalog[0],{trusted,state});
  const blocked=renderToStaticMarkup(React.createElement(Panel,{...referenceProps,extensions:blockedCatalog,busy}));
  assert.match(blocked, /<button disabled=""[^>]*>Preview generated case/);
  assert.match(blocked, /<button disabled=""[^>]*>Generate mesh/);
}
console.log("Extension workspace routes: declared IDs, trust/state, scalar GUI validation and structured-setup handoff passed.");

// Actual bundled catalogs must remain reachable through the same strict UI parser.
const { readFile } = await import("node:fs/promises");
const bundled = await Promise.all(["emerge_suite", "openems_suite", "optycal_suite"].map(async folder => ({ ...JSON.parse(await readFile(new URL(`../../extensions/${folder}/spike-extension.json`, import.meta.url), "utf8")), trusted: true, state: "loaded" })));
assert.deepEqual(extensionWorkspaceRoutes(bundled, "mesh").map(row => row.extensionId).sort(), ["spike.emerge-suite", "spike.openems-suite"]);
assert.deepEqual(extensionWorkspaceRoutes(bundled, "em", "solve").map(row => row.extensionId).sort(), ["spike.emerge-suite", "spike.openems-suite", "spike.optycal-suite"]);
assert.deepEqual(extensionWorkspaceRoutes(bundled, "si", "solve").map(row => row.extensionId).sort(), ["spike.emerge-suite", "spike.openems-suite"]);
assert.equal(extensionWorkspaceRoutes(bundled, "pi", "solve")[0].extensionId, "spike.openems-suite");
assert.equal(extensionWorkspaceRoutes(bundled, "thermal").length, 0);

const volumeCatalog = await Promise.all(["calculix_suite", "gmsh_suite"].map(async folder => ({ ...JSON.parse(await readFile(new URL(`../../extensions/${folder}/spike-extension.json`, import.meta.url), "utf8")), trusted:true,state:"loaded" })));
const thermal = extensionWorkspaceRoutes(volumeCatalog,"thermal");
assert.equal(thermal.filter(row=>row.operation==="solve").length,1);
assert.equal(thermal.filter(row=>row.operation==="mesh").length,1);
for (const workspace of ["pi","si","em","thermal","mesh"]) assert.ok(extensionWorkspaceRoutes(volumeCatalog,workspace,"mesh").length);
const solver = thermal.find(row=>row.operation==="solve"), mesher = thermal.find(row=>row.operation==="mesh");
const independent = renderToStaticMarkup(React.createElement(Panel,{...props,workspace:"thermal",operation:undefined,extensions:volumeCatalog,selectedRouteId:mesher.key,selectedSolverRouteId:solver.key,selectedMeshRouteId:mesher.key}));
assert.match(independent,new RegExp(`<option value="${solver.key}" selected=""`));
assert.match(independent,new RegExp(`<option value="${mesher.key}" selected=""`));
assert.equal(extensionWorkspaceRoutes(volumeCatalog,"em","solve").length,0,"thermal engine cannot be advertised as an EM solver");

const su2Catalog = [{ ...JSON.parse(await readFile(new URL("../../extensions/su2_suite/spike-extension.json", import.meta.url), "utf8")), trusted:true,state:"loaded" }];
const su2Routes=extensionWorkspaceRoutes(su2Catalog,"thermal","solve");
assert.deepEqual(su2Routes.map(row=>row.contributionId).sort(),["su2-cfd","su2-cht"]);
for (const su2Route of su2Routes) {
  assert.equal(su2Route.requiresBoard,false);
  assert.equal(su2Route.previewContributionId,`${su2Route.contributionId}-preview`);
  assert.equal(extensionScalarFields(su2Route.schema).requiresDedicatedGui,false);
  const su2Html=renderToStaticMarkup(React.createElement(Panel,{...props,workspace:"thermal",operation:"solve",extensions:su2Catalog,selectedRouteId:su2Route.key,boardLoaded:false}));
  assert.match(su2Html, /reference geometry independently of any loaded board/);
  assert.match(su2Html, /<button>Preview generated case<\/button>/);
  assert.match(su2Html, /<button>Run selected engine<\/button>/);
  assert.doesNotMatch(su2Html,/Load a board|<textarea/);
}
for (const workspace of ["mesh","pi","si","em"]) assert.equal(extensionWorkspaceRoutes(su2Catalog,workspace).length,0);
console.log("SU2 CFD and CHT: thermal reference routes, scalar setup, board-independent preview/run and trust/busy gates passed.");
