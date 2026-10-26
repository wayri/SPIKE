// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const require = createRequire(import.meta.url);
function load(name, mocks = {}, fixtureGlob = () => ({})) {
  const source = readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8").replaceAll("import.meta.glob(", "fixtureGlob(");
  const module = { exports: {} };
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function("require", "module", "exports", "fixtureGlob", code)(id => id.endsWith(".css") ? {} : id in mocks ? mocks[id] : require(id), module, module.exports, fixtureGlob);
  return module.exports;
}
const search = load("optionSearch.ts");
let assetReads = 0;
const assets = {};
function glob(pattern) {
  const directory = pattern.includes("snapshots") ? "examples/emerge/gallery/snapshots" : "examples/upstream-emerge/studies";
  const rows = {};
  for (const name of readdirSync(new URL(`../../${directory}/`, import.meta.url))) {
    if (!name.endsWith(".json")) continue;
    rows[`../../${directory}/${name}`] = async () => { assetReads++; return readFileSync(new URL(`../../${directory}/${name}`, import.meta.url), "utf8"); };
  }
  Object.assign(assets, rows); return rows;
}
const api = load("emergeExampleCatalog.ts", { "./optionSearch": search }, glob);
assert.equal(assetReads, 0, "Project and executable wrapper text is lazy, not evaluated at catalog load");
assert.equal(api.emergeExamples.length, 5);
assert.equal(api.advancedEMergeStudies.filter(row => row.status !== "suspended").length, 23);
assert.equal(api.advancedEMergeStudies.filter(row => row.status === "suspended").length, 5);
assert.equal(api.findEMergeExamples("near* field")[0].id, "patch-fields");
assert.ok(api.findAdvancedEMergeStudies("*filter*").length >= 3);
assert.equal(api.findEMergeExamples("", "Field probing").length, 1);
await assert.rejects(api.loadEMergeExampleSnapshot("../../arbitrary"), /not bundled/);
await assert.rejects(api.loadAdvancedEMergeStudy(api.advancedEMergeStudies.find(row => row.status === "suspended").id), /suspended/);
const projectApi = load("projectPackage.ts", { "./appVersion": { APP_VERSION: "0.4.1" } });
const analysis = load("analysisResults.ts", { "./numericRange": load("numericRange.ts") });
const uiMocks = { "./persistedEnginePython": { persistedEnginePython: () => "" }, "./emergeExampleEvent": { OPEN_EMERGE_EXAMPLES_EVENT: "spike-open-emerge-examples" }, "./DataTable": () => null, "./emergeRuntimePresentation": {}, "./PlotlyChart": () => null, "./emergePatternInterpolation": {}, "./icons": { Layers3: () => null }, "./emergeSetupSuggestions": {}, "./emergeNetworkReview": {}, "./EMergeNearField": {}, "./emergeSampleExport": {}, "./emergeCosimulationDraft": {} };
const emerge = load("EMergeExtension.tsx", uiMocks);
const settings = load("extensionWorkflowSettings.ts", { "./EMergeExtension": emerge, "./openEMSSetup": { defaultOpenEMSSetup: () => ({}), openEMSFields: {} } });
for (const row of api.emergeExamples) {
  const snapshot = await api.loadEMergeExampleSnapshot(row.id);
  const { project } = projectApi.parseProjectPackage(snapshot);
  assert.ok(project.design.source_board.length > 100);
  const setup = settings.normalizeEMergeSetup(project.analysis.extension_workflows.emerge_setup);
  const params = emerge.emergeParameters(setup);
  assert.equal(params.python_executable, undefined);
  if (row.id === "esp32-surrogate") {
    assert.deepEqual(params.shorting_via_ids, project.gallery.retained_parameters.shorting_via_ids);
    assert.equal(params.fragment_copper, false);
  }
  if (row.status === "setup_only") assert.equal(project.analysis.latest_result, null);
  else {
    const normalized = analysis.normalizeSolverResult(project.analysis.latest_result);
    assert.ok(normalized.em_fields.radiation.patterns_3d.length);
    assert.ok(normalized.em_networks.s_parameters.frequencies_hz.length);
    if (row.id === "patch-fields") assert.equal(normalized.em_fields.nearfield.planes[0].coordinates_mm.length, 121);
  }
}
const study = api.advancedEMergeStudies.find(row => row.status !== "suspended");
const exported = await api.loadAdvancedEMergeStudy(study.id);
assert.equal(exported.text, readFileSync(new URL(`../../${study.study_path}`, import.meta.url), "utf8"), "Existing wrapper exports byte-for-byte");
let cells = [], cursor = 0, opens = [];
const fakeReact = { ...React, useState: initial => { const index = cursor++; if (!(index in cells)) cells[index] = initial; return [cells[index], value => { cells[index] = value; }]; } };
const Component = load("EMergeExamples.tsx", { react: fakeReact, "./SectionHelpButton": () => React.createElement("button", { type: "button" }, "Help"), "./emergeExampleCatalog": api, "./workerBridge": { isDesktopShell: () => false }, "./emergeSampleExport": {} }).default;
function tree() { cursor = 0; return Component({ onOpen: id => opens.push(id) }); }
function elements(node) { if (!React.isValidElement(node)) return []; return [node, ...React.Children.toArray(node.props.children).flatMap(elements)]; }
const initial = tree();
assert.equal(opens.length, 0);
assert.match(renderToStaticMarkup(initial), /retained solver plot|Retained solver plot/);
const buttons = elements(initial).filter(node => node.type === "button");
buttons.find(node => node.props.className === "spike-control--primary").props.onClick(); assert.equal(opens.length, 1);
buttons.find(node => node.props.children === "Advanced studies").props.onClick();
const advanced = elements(tree());
assert.equal(advanced.filter(node => node.type === "button" && node.props.children === "Save study wrapper" && node.props.disabled).length, 5);
cells[0] = "not-an-example"; assert.match(renderToStaticMarkup(tree()), /Try a shorter search/);
for (const setup of [{ shorting_via_ids: "same same" }, { shorting_via_ids: "bad/path" }, { shorting_via_ids: Array.from({ length: 17 }, (_, i) => `via${i}`).join(" ") }]) assert.throws(() => emerge.emergeParameters({ ...emerge.defaultEMergeSetup("RF"), signal_pad_id: "s", return_pad_id: "r", ...setup }), /16 distinct/);
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
assert.match(app, /requestUnsavedAction\("open an EMerge example project"/);
assert.match(app, /await loadEMergeExampleSnapshot\(id\); load\.check\(\)/);
assert.match(app, /savedEMergeResultEnvelope\(savedEMerge\)/);
// Valid long via lists survive settings save/open without truncation.
const longIds = Array.from({ length: 16 }, (_, i) => `${i}-` + "a".repeat(100)).join(",");
assert.ok(longIds.length > 1024 && longIds.length <= 2048);
const longSetup = { ...emerge.defaultEMergeSetup("RF"), signal_pad_id: "s", return_pad_id: "r", shorting_via_ids: longIds, fragment_copper: false };
assert.equal(settings.normalizeEMergeSetup(JSON.parse(JSON.stringify(longSetup))).shorting_via_ids, longIds);
assert.equal(emerge.emergeParameters(settings.normalizeEMergeSetup(longSetup)).shorting_via_ids.length, 16);
// Open raw A, run newly identified B, save and reopen: no A arrays under B provenance.
const mergeApi = load("projectSnapshotState.ts");
const radiation = load("emergeRadiationView.ts");
const oldProject = JSON.parse(await api.loadEMergeExampleSnapshot("patch"));
const originalResultText = JSON.stringify(oldProject.analysis.latest_result);
const nextResult = structuredClone(JSON.parse(await api.loadEMergeExampleSnapshot("patch-fields")).analysis.latest_result);
nextResult.analysis_id = "fresh-run-B";
const normalizedB = analysis.normalizeSolverResult(nextResult);
const saved = mergeApi.mergeProjectSnapshot(oldProject, { analysis: { latest_result: normalizedB } });
const reopened = projectApi.parseProjectPackage(JSON.stringify(saved)).project.analysis.latest_result;
assert.equal(reopened.analysis_id, "fresh-run-B");
assert.equal(reopened.fields, undefined, "Raw A fields must not survive the new result");
const viewB = radiation.savedEMergeResultEnvelope(reopened).data.analysis_result;
assert.deepEqual(viewB.fields, nextResult.fields);
assert.deepEqual(viewB.networks, nextResult.networks);
assert.equal(viewB.provenance.design_digest_sha256, nextResult.provenance.design_digest_sha256);
assert.equal(JSON.stringify(oldProject.analysis.latest_result), originalResultText, "Saving leaves original A evidence unchanged");
console.log("EMerge gallery: lazy assets, all projects, preserved exceptions, exact wrappers, search, categories, open and suspended states passed");
